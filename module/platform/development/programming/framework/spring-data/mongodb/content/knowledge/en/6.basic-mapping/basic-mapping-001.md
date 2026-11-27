# Marking Entities with @Document and Choosing Collection Names

## 1. Context and Objectives

MongoDB organizes data by **database → collection → document**. A collection holds BSON documents; each document typically represents an entity or a group of data that shares a common lifecycle in the domain. When writing Java applications, Spring Data MongoDB maps Java objects to BSON for storing and reading data.

The **@Document** annotation in Spring Data MongoDB is used to declare a class as a root document type and, when needed, bind that class to a specific **collection name**. Within the **SPRING_DATA_MONGODB** module, this is the foundation for connecting, mapping, and interacting with MongoDB using **MongoTemplate** or **repositories**. Choosing a collection also relates to query design, aggregation, indexing, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Declare an entity using the `@Document` and `@Id` annotations along with Java fields.
2. Distinguish between a Java class name, a collection name, and a database name.
3. Understand the default collection name, how to choose an explicit name, and the risks of renaming a class.
4. Access the same collection using `MongoRepository` and `MongoTemplate`.
5. Decide collection boundaries based on business, querying, and operational requirements.
6. Inspect the actual collection and troubleshoot read/write target mismatches.

## 2. Relationship Between Java Entities and MongoDB Documents

Consider an order that has an order number, a customer name, and a creation timestamp. The Java object representing the order will be converted into BSON when saved:

~~~mermaid
flowchart LR
    A["OrderDocument (Java)"] --> B["MappingMongoConverter"]
    B --> C["BSON document"]
    C --> D["Database shop"]
    D --> E["Collection orders"]
~~~

A corresponding document viewed in **mongosh** might look like this:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  customerName: "Lan",
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

Different elements to distinguish:

| Component | Example | Role |
| --- | --- | --- |
| Java Class | OrderDocument | Model for programming and applying mapping. |
| Database | shop | Namespace containing multiple collections, usually determined by connection configuration. |
| Collection | orders | Group of documents sharing the same storage scope. |
| BSON Document | Record ORD-1001 | Actual data, with an `_id` identifier key. |
| Java Property | orderNumber | Can be mapped to a BSON field with the same name or a customized name. |

This document uses the term **entity** to refer to an object belonging to the MongoDB storage model. This is not a JPA entity in the relational-table sense. The `@Document` annotation does not create foreign keys or SQL joins, nor does it decide whether a field will be embedded or referenced simply by annotating the class.

## 3. Syntax of @Document

The annotation is imported from the Spring Data MongoDB package:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
~~~

Minimal example:

~~~java
@Document
public class ProductDocument {
    // Fields, constructors, and getters/setters.
}
~~~

In many cases, Spring Data MongoDB can still map a Java type without `@Document` when operating through `MongoTemplate`; however, **explicitly declaring `@Document`** for a root document helps express intent and avoids subtle reliance on default naming rules.

### 3.1. Choosing a Collection with the `collection` Attribute

~~~java
@Document(collection = "products")
public class ProductDocument {
    // Stored in the products collection.
}
~~~

The value **products** is the collection name, not the database name. An equivalent way of writing it via the annotation's alias attribute is:

~~~java
@Document(value = "products")
public class ProductDocument {
}
~~~

In documentation and project codebases, writing **collection = "products"** is usually clearer in meaning. Naming it explicitly also allows renaming the Java class while keeping the data storage location unchanged.

### 3.2. Default Name When Undeclared

When no collection name is specified, Spring Data MongoDB's common default rule is to take the class's simple name and lowercase the first letter:

| Java Class | Common Default Collection | Name if Explicitly Declared |
| --- | --- | --- |
| Customer | customer | customers |
| OrderDocument | orderDocument | orders |
| ProductCatalog | productCatalog | product_catalog |

This is mapping-layer behavior and can be affected by naming strategy configuration. In a project that needs long-term data persistence, check the name actually chosen by the framework via its API and **explicitly declare the collection** for stability.

A dangerous bug occurs when renaming class **Order** to **CustomerOrder** without declaring a collection. Operations may switch from the default collection **order** to **customerOrder**. Old data remains in the previous collection, while the new application may read an empty new collection.

### 3.3. The Annotation Is Not a Collection Creation Command

Declaring `@Document` does not automatically create a collection just by loading the Java class. A collection may be created by MongoDB upon the first write if configuration and permissions allow; the application can also proactively create the collection.

Similarly, `@Document` **does not automatically create indexes, validators, access permissions, or migrate data**. Those configurations have their own management lifecycles.

## 4. Complete Entity Example: OrderDocument

The following example chooses an explicit ID type, **ObjectId**. If the Java ID uses `String`, Spring Data has its own conversion rules when mapping to the `_id` field; choosing `ObjectId` below helps beginners focus on the collection.

~~~java
package com.example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class OrderDocument {

    @Id
    private ObjectId id;

    private String orderNumber;
    private String customerName;
    private Instant createdAt;

    public OrderDocument() {
    }

    public OrderDocument(String orderNumber, String customerName,
                         Instant createdAt) {
        this.orderNumber = orderNumber;
        this.customerName = customerName;
        this.createdAt = createdAt;
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Explanation:

- **@Document(collection = "orders")** specifies the collection of the root document.
- **@Id** marks the property mapped to the BSON **_id** field; it does not set the collection name.
- The ID can initially be left null when creating a new object; on insert, MongoDB/the driver can generate an `ObjectId` for the document.
- **Instant** is usually mapped to a BSON Date; an instant does not contain a time zone name.
- Java properties without the `@Field` annotation are usually stored under the property name.
- Spring Data may write **_class** metadata into BSON according to the default type mapper configuration. This is information used for Java type mapping, not a collection name or business schema version.

In a production model, input validation, business invariants, and identifier rules must be added. Those responsibilities are not solved by `@Document` alone.

## 5. Database Is Determined by Connection Configuration

Example Spring Boot configuration with MongoDB running in a development environment:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/shop
~~~

**shop** is the database in the URI, while **orders** is the collection from `@Document`. The corresponding structure is:

~~~text
MongoDB server
└── shop                         # database chosen by connection
    ├── orders                   # collection from @Document
    │   ├── document ORD-1001
    │   └── document ORD-1002
    └── customers
~~~

An `OrderDocument` class with the same annotation can be written to different databases if different `MongoTemplate` instances are configured to point to different databases. The annotation chooses the **collection within the active database**, rather than locking the class to one global database.

Therefore, when encountering a "missing data" issue, check **both the database and the collection**, especially after changing environment profiles, connection URIs, or `MongoTemplate` beans.

## 6. Using MongoRepository

Spring Data creates a repository based on the document type and identifier key type:

~~~java
package com.example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {

    OrderDocument findFirstByOrderNumber(String orderNumber);
}
~~~

The repository uses **OrderDocument** metadata to determine the **orders** collection. A service can create and look up orders:

~~~java
import java.time.Instant;

public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument create(String number, String customer) {
        OrderDocument order = new OrderDocument(
            number,
            customer,
            Instant.now()
        );
        return repository.save(order);
    }

    public OrderDocument findByNumber(String number) {
        return repository.findFirstByOrderNumber(number);
    }
}
~~~

Note that **findFirstByOrderNumber** returns one record if there are multiple duplicates. If the domain requires unique order numbers, a **real unique index on the orders collection** is needed; the repository method name does not automatically create a uniqueness constraint.

## 7. Using MongoTemplate

`MongoTemplate` can also resolve the collection from the same class:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderQueryService {
    private final MongoTemplate template;

    public OrderQueryService(MongoTemplate template) {
        this.template = template;
    }

    public OrderDocument findById(ObjectId id) {
        return template.findById(id, OrderDocument.class);
    }

    public OrderDocument findByNumber(String number) {
        Query query = Query.query(
            Criteria.where("orderNumber").is(number)
        );
        return template.findOne(query, OrderDocument.class);
    }

    public OrderDocument insert(OrderDocument order) {
        return template.insert(order);
    }
}
~~~

These methods access **orders** because they receive `OrderDocument.class` or an instance of that type. Given the same database and mapping metadata, `MongoRepository` and `MongoTemplate` can read and write consistently on the same collection.

However, `MongoTemplate` has overloads that allow **specifying a custom collection name per operation**:

~~~java
template.insert(order, "archived_orders");

// After the operation above, this still reads the "orders" collection:
OrderDocument found = template.findById(order.getId(), OrderDocument.class);
~~~

This snippet illustrates a common mistake: the document is written to **archived_orders**, while `findById` automatically selects **orders** from the annotation and may return null. If intentionally using a different collection, the name must be synchronized across all write, read, update, delete, and index-creation paths.

**Practical rule:** do not scatter collection names as raw strings throughout code when the entity metadata already describes the business collection accurately. If overriding is necessary, centralize the name-selection logic in one easily auditable place.

## 8. Collection Naming Conventions

The collection name is part of the long-term storage contract. There is no universal requirement for every project to use singular or plural names; what matters is having **one consistent convention**.

| Principle | Good Example | Reason |
| --- | --- | --- |
| Reflects the business set | orders, customers, products | Easy to understand collection contents. |
| Keep names stable | @Document(collection = "orders") | Renaming a class does not change where data is stored. |
| Use lowercase, easy-to-handle characters | order_events, inventory_movements | Easy to use in scripts, monitoring, and queries. |
| Avoid cryptic abbreviations | order_events instead of oe2 | Easier long-term maintenance. |
| Do not create collections from arbitrary input | Restrict names via trusted configuration | Prevents uncontrolled growth in collection count. |
| Follow MongoDB namespace rules | Avoid reserved names like system.* | Prevents conflicts with internal components. |

If a team chooses `snake_case` and plural names, they might standardize on:

~~~text
customers
orders
order_events
products
product_categories
inventory_movements
~~~

Avoid renaming a collection just to make a Java class name look nicer. Renaming a class can be a source-code refactoring; renaming a collection is a **database and data-access change** that requires an appropriate plan.

## 9. Choosing Collection Boundaries by Document Model

Do not decide on a "one Java class per collection" basis. Collection boundaries should be based on **data accessed and updated together**, document size, lifecycle, and indexing needs.

### 9.1. Embedding Data Within the Same Aggregate

An order with a few line items can be stored in the same document:

~~~javascript
{
  orderNumber: "ORD-1001",
  customerName: "Lan",
  items: [
    { sku: "BOOK-01", quantity: NumberInt(2) },
    { sku: "PEN-03", quantity: NumberInt(1) }
  ],
  createdAt: ISODate("2025-05-20T09:00:00Z")
}
~~~

**items** is an array of embedded documents inside the **orders** collection. In Java, you can create an **OrderItem** class to map these elements without marking each element as a root document or creating a separate collection.

Embedding lets you read and update data in the same aggregate in a single document, but you must keep MongoDB's document size limit and the risk of unbounded array growth in mind.

### 9.2. Splitting Collections When Lifecycles Differ

For example:

- **orders** stores the current state of an order.
- **order_events** stores status-change events whose count can grow over the long term.
- **customers** stores customer information that has an independent lifecycle from individual orders.

This split can be appropriate when each group requires different retention, indexes, access permissions, queries, or write frequencies. When splitting across multiple collections, the application must handle relationships and consistency across documents. Multi-document transactions should only be used when there are genuine business invariants to protect; they do not arise automatically from `@Document`.

### 9.3. Collections per Tenant or per Year

Naming like **orders_2025** or **orders_tenant_17** can serve a specialized design, but introduces extra costs:

1. Each collection has its own indexes and validation configuration to maintain.
2. Cross-year or cross-tenant queries become more complex.
3. A repository with a standard `@Document` defaults to one collection name from entity metadata.
4. The number of collections can grow very quickly as tenants or partitions increase.

Consider a **tenantId** field in the same collection with appropriate indexes, or a separate database per tenant if isolation is required, before choosing to create one collection per tenant. If using dynamic collections through `MongoTemplate`, validate names strictly and keep them consistent across all operations.

## 10. @Document and Other Mapping Annotations

Marking `@Document` is only one part of the mapping mechanism:

| Annotation | Role | Does it change the collection? |
| --- | --- | --- |
| @Document(collection = "orders") | Specifies the collection name for the root document | Yes. |
| @Id | Maps the identifier property to `_id` | No. |
| @Field("customer_name") | Renames the stored BSON field | No. |
| @Transient | Excludes the field from persistence mapping | No. |
| @Version | Supports Spring Data optimistic locking | No. |
| @Indexed | Declares index metadata for a field | No. |
| @TypeAlias | Customizes the alias for type metadata | No. |

For example, the Java field stays **customerName** while the BSON field is written as **customer_name**:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "orders")
public class OrderSummary {
    @Id
    private ObjectId id;

    @Field("customer_name")
    private String customerName;

    // Constructors and accessors omitted.
}
~~~

The collection of `OrderSummary` is still **orders**. The `@Field` annotation only changes the field name; it does not create a **customer_name** collection.

Do not use JPA's **@Table** annotation to specify a MongoDB collection. Relational ORM mechanisms and document mapping mechanisms have separate metadata.

## 11. Creating Collections and Indexes

### 11.1. Creating a Collection Explicitly

`MongoTemplate` provides APIs to check and create a collection from entity metadata:

~~~java
if (!mongoTemplate.collectionExists(OrderDocument.class)) {
    mongoTemplate.createCollection(OrderDocument.class);
}
~~~

This is an example in a controlled context; if multiple instances start concurrently, two instances could both check and attempt to create it at the same time. In production, there should be a consistent provisioning/migration mechanism that handles the case where the collection already exists.

For collections needing special settings like validation or a specialized collection type, writing `@Document` alone is not enough to apply those options.

### 11.2. Indexes Are Separate Configuration

For example, `orderNumber` must be unique. You can declare:

~~~java
import org.springframework.data.mongodb.core.index.Indexed;

@Indexed(unique = true)
private String orderNumber;
~~~

However, **@Indexed does not prove that the index has been created in MongoDB**. Automatic index creation depends on Spring Data configuration; many systems manage indexes via migrations. Indexes can be created explicitly using `MongoTemplate`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

mongoTemplate.indexOps(OrderDocument.class).ensureIndex(
    new Index().on("orderNumber", Sort.Direction.ASC).unique()
);
~~~

In this example, **indexOps(OrderDocument.class)** selects the **orders** collection based on metadata. If the collection already contains duplicate order numbers, creating the unique index can fail; actual data must be checked before enabling the constraint.

### 11.3. Collection Validation Is Another Mechanism

MongoDB can use **$jsonSchema** to require fields to have matching BSON types. Example creating a separate illustrative collection:

~~~javascript
db.createCollection("orders_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNumber", "createdAt"],
      properties: {
        orderNumber: { bsonType: "string" },
        createdAt: { bsonType: "date" }
      }
    }
  }
});
~~~

The validator in the example only applies to **orders_validated**. If entity `OrderDocument` uses **orders**, that collection must have validation configured separately. Choosing the collection name, creating indexes, and setting schema validation are **three independent decisions**.

## 12. Inspecting the Collection Name at Runtime

`MongoTemplate` provides APIs to confirm the actual mapping:

~~~java
String name = mongoTemplate.getCollectionName(OrderDocument.class);
boolean exists = mongoTemplate.collectionExists(OrderDocument.class);

System.out.println(name);   // orders
System.out.println(exists); // true if the collection already exists.
~~~

The **getCollectionName** method returns the collection name according to mapping metadata; **collectionExists** checks existence. Neither guarantees that the collection already contains documents.

With `mongosh`, confirm the database and collection before analyzing data:

~~~javascript
db.getName();                  // Currently selected database.
db.getCollectionNames();       // List of collections.
db.orders.findOne();           // One sample document, if any.
db.orders.countDocuments({});  // Document count.
db.orders.getIndexes();        // Actual indexes.
~~~

During testing or diagnostics, you can compare the collection name reported by Spring Data against the list of collections actually present in MongoDB. If data does not appear, check the URI, database, collection name, query filter, and MongoDB account permissions simultaneously.

## 13. Renaming a Collection When the Application Already Has Data

Consider the old version:

~~~java
@Document(collection = "order")
public class OrderDocument {
}
~~~

Later the code is updated to:

~~~java
@Document(collection = "orders")
public class OrderDocument {
}
~~~

The change above **does not move documents** from the **order** collection to **orders**. The new API may return an empty list while all old records still sit in the old collection.

Renaming a collection must be handled as a planned migration:

1. Check all readers, writers, jobs, reports, and services depending on the old name.
2. Inventory documents, indexes, validators, permissions, and administrative operations using the collection.
3. Choose a data transfer approach or `renameCollection` operation appropriate for the deployment conditions.
4. Handle old and new instances running concurrently to avoid writing to two different collections.
5. Reconcile data and verify all queries and indexes after the switch.
6. Retain a rollback capability according to policy before completely retiring the old name access path.

MongoDB has a **renameCollection** operation, but using it must match server capabilities, access permissions, and application impact. In a system under continuous writes, do not rename with an ad-hoc command without defining the cutover window and affected consumers.

If only renaming the Java class, keeping **@Document(collection = "orders")** usually avoids changing the storage target. However, if using **_class** type metadata, you still need to consider reading back documents written under the old class name.

## 14. Common Issues and How to Fix Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Insert succeeds but queries find nothing | Collection was overridden on insert | Check template overloads and target names on both read and write paths. |
| List is empty after renaming a class | Collection name was inferred from class name | Declare the name explicitly and plan for legacy data. |
| Unexpected collection appears | Typo in collection name | Check mappings and written data before fixing. |
| Repository and MongoTemplate return different results | Different database, collection, or query | Verify URI, `getCollectionName`, and query criteria. |
| No unique constraint despite @Indexed | Index has not been created in MongoDB | Check `getIndexes` and run the appropriate index provisioning process. |
| Document fields have unexpected names | `@Field` or custom mapping is in use | Inspect raw BSON and check metadata. |
| ID lookup mismatches | BSON `ObjectId`/`String` type mismatch | Check `_id` type and `@Id` mapping behavior. |
| Nested class has no collection | The object is being embedded | Review embedded vs. reference decision and aggregate boundaries. |

When evaluating performance, **do not assume a nicer collection name makes queries faster**. Inspect indexes, document sizes, query patterns, and **explain("executionStats")** output. Collection boundaries affect index and query design; the name itself does not replace optimization work.

## 15. Testing Collection Mapping

A useful integration test verifies both metadata and round-trip operations. The example below uses JUnit 5 and Spring Boot Test, with the repository and `MongoTemplate` configured to connect to a **test database**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class OrderMappingTest {

    @Autowired
    private MongoTemplate mongoTemplate;

    @Autowired
    private OrderRepository repository;

    @Test
    void repositoryAndTemplateUseSameCollection() {
        assertThat(mongoTemplate.getCollectionName(OrderDocument.class))
            .isEqualTo("orders");

        OrderDocument saved = repository.save(new OrderDocument(
            "TEST-" + UUID.randomUUID(),
            "Lan",
            Instant.parse("2025-05-20T09:00:00Z")
        ));

        try {
            OrderDocument loaded = mongoTemplate.findById(
                saved.getId(),
                OrderDocument.class
            );
            assertThat(loaded).isNotNull();
            assertThat(loaded.getOrderNumber())
                .isEqualTo(saved.getOrderNumber());
        } finally {
            repository.deleteById(saved.getId());
        }
    }
}
~~~

Tests must not run against production; a dedicated test datasource/URI configuration is mandatory. This test verifies that the repository and `MongoTemplate` read and write the same collection in the same database; it does not replace tests for unique indexes, validation, or access permissions.

## 16. Connection to Aggregation and Reactive Access

`@Document` collection mapping is used by Spring Data across many APIs:

- **MongoTemplate.find** and **MongoTemplate.aggregate** have overloads accepting a class to infer the input collection.
- **MongoRepository** uses document metadata when building queries.
- **MongoTemplate.indexOps(OrderDocument.class)** selects the collection for managing indexes.
- **ReactiveMongoTemplate** and **ReactiveMongoRepository** still use the corresponding collection metadata, while accessing data asynchronously through reactive publishers.

Example aggregation counting orders per customer:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.group("customerName").count().as("orders")
);

AggregationResults<Document> result = mongoTemplate.aggregate(
    aggregation,
    OrderDocument.class,
    Document.class
);
~~~

The **OrderDocument.class** argument resolves the **orders** collection through mapping. An overload accepting a collection name string uses the exact string passed, so keep naming consistent when mixing different APIs.

Reactive repository example:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {
}
~~~

Reactive access changes how data-access streams execute, cancel, and handle backpressure, **without changing the meaning of `@Document(collection = "orders")`.**

## 17. Practice Exercises

### Exercise 1: Choosing a Collection

Given three classes:

~~~java
@Document
class Customer {}

@Document(collection = "purchase_orders")
class PurchaseOrder {}

@Document(collection = "product_catalog")
class Catalog {}
~~~

**Question:** Which classes have an explicit collection? If `PurchaseOrder` is renamed to `OrderAggregate` while keeping the annotation, does the collection name change?

**Answer Hint:** `PurchaseOrder` and `Catalog` have explicit names. `Customer` uses the default name, typically `customer`. Renaming class `PurchaseOrder` does not change the **purchase_orders** collection when keeping the annotation. Check type metadata if existing documents already store the old class information.

### Exercise 2: Finding a Mismatched Read/Write Collection Bug

~~~java
@Document(collection = "orders")
class OrderDocument { /* ... */ }

mongoTemplate.insert(order, "archived_orders");
OrderDocument found =
    mongoTemplate.findById(order.getId(), OrderDocument.class);
~~~

**Question:** Why might `found` be null?

**Answer Hint:** The `insert` command uses the **archived_orders** collection, whereas `findById` uses class metadata to read **orders**. You must use the same database and the right collection when reading back a newly written record.

### Exercise 3: Embed or Split Collections?

An order has 5 product lines and a status-change history that grows to thousands of records. Which collections would you create?

**Answer Hint:** Small line items can be kept within the `orders` document, and long history entries can be split into `order_events` if they have independent query/retention requirements. Define indexes, relationships, and write consistency across the two collections.

### Exercise 4: Investigating a Post-Deployment Issue

Before deployment, the code used class `Order` without `@Document(collection)`. After deployment, the class was renamed to `CustomerOrder` and the order lookup API returns empty results. Describe how to investigate.

**Answer Hint:** Check `getCollectionName` for the old and new mappings, verify the database, list actual collections, and compare data and queries. Restore a stable collection configuration or execute a planned migration, and avoid dropping the old collection before verifying the data.

### Exercise 5: Difference Between Annotations and Real Indexes

~~~java
@Document(collection = "customers")
class CustomerDocument {
    @Id ObjectId id;
    @Indexed(unique = true) String email;
}
~~~

**Question:** What is the collection name, and what conditions actually ensure `email` is unique?

**Answer:** The collection name is **customers** in the current database. The annotation alone does not prove a unique index exists; you must verify the index has been successfully created in MongoDB, that existing data has no conflicts, and that all writers write to this collection.

## 18. Key Takeaways

1. **@Document** is the declaration point for a root document and its collection name; **@Id** declares the document identifier.
2. **The database is determined by the connection/template**; the collection is determined by entity mapping or the name passed to the API.
3. **Declare collection names explicitly** so refactoring a class does not accidentally change the data storage target.
4. **Repositories and MongoTemplate can share the same mapping**, though overloads taking a collection name can override the target locally.
5. **Collection boundaries must come from the domain model and query patterns**, not the number of Java classes.
6. **Indexes, validation, and data migrations are managed separately**. Annotations do not automatically replace these operational steps.

Mastering entity marking with `@Document` and collection name selection gives you a stable mapping foundation in **SPRING_DATA_MONGODB** before moving on to queries, aggregations, indexes, transactions, reactive access, and advanced data processing.
