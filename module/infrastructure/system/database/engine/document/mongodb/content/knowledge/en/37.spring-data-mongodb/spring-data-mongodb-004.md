# MongoRepository, Derived Query Methods, and @Query Queries in Spring Data MongoDB

## 1. Problem Statement: How Should You Write MongoDB Queries in a Spring Application?

A Java order-management application typically needs operations such as:

- Finding orders by `tenantId` and `status`.
- Fetching a single order by ID and checking existence.
- Filtering orders above a threshold amount, by creation date, or by shipping address.
- Sorting newest first, paginating, and fetching only a subset of fields.
- Checking duplicate order numbers within the same tenant.
- Matching complex MongoDB conditions that are awkward to express in a method name.
- Updating or deleting in a controlled manner while tracking affected document counts.

Spring Data MongoDB provides a **repository abstraction** to handle most of these tasks without writing `MongoTemplate` boilerplate for every query.

Three core concepts of this lesson:

1. **`MongoRepository<T, ID>`**: an interface for CRUD operations and default queries.
2. **Derived query methods**: Spring Data parses the method name—such as `findByTenantIdAndStatus`—and builds the corresponding MongoDB query.
3. **`@Query`**: declares a query using a MongoDB JSON string when you want explicit filters, complex operators, projections, or query options that do not fit comfortably in a method name.

Key takeaway: **`MongoRepository` does not replace the MongoDB query planner or indexes**. Spring Data only expresses and dispatches the query; actual speed still depends on indexes, data distribution, query shape, server capacity, and network latency.

### Learning Objectives

After this lesson, you will be able to:

- Create an `@Document` entity and a `MongoRepository` for MongoDB.
- Use `save`, `insert`, `findById`, `findAll`, `deleteById`, `count`, and `existsById` with proper semantics.
- Derive queries using `And`, `Or`, `GreaterThan`, `Between`, `In`, `IsNull`, `Exists`, `True`, `Containing`, `IgnoreCase`, `OrderBy`, and `Top`.
- Query nested properties via `findByShipping_City` and understand how underscores delimit property paths.
- Use `Pageable`, `Sort`, `Page`, `Slice`, `Stream`, and result limits.
- Write `@Query` with `?0`, `?1`, `fields`, `sort`, `collation`, `hint`, `count`, `exists`, and `delete`.
- Understand the distinction between **Java property names**, BSON field names, and `@Field`.
- Use interface/DTO projections to avoid loading entire documents.
- Recognize when to switch to `MongoTemplate`, `@Aggregation`, or a custom repository implementation.
- Write real tests and guard against query logic bugs, multi-tenancy leaks, deep pagination overhead, and slow queries.

---

## 2. Where Does MongoRepository Sit in the Architecture?

A Spring MVC request can flow through:

```text
HTTP /orders?status=PAID
            |
            v
       Controller
            |
            v
        Service
            |
            v
      OrderRepository
      extends MongoRepository
            |
            v
   Spring Data Repository Proxy
            |
            v
 MappingMongoConverter + MongoDB Java Driver
            |
            v
       MongoDB Server
       orders collection
```

When the application context starts, Spring Data scans for repository interfaces, generates runtime proxy implementations, and uses entity metadata for mapping and querying.

### 2.1. An Interface Without Manual Boilerplate for Basic CRUD

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, String> {
}
```

Even without writing `OrderRepositoryImpl`, the application can call:

```java
repository.save(order);
repository.findById("O-100");
repository.existsById("O-100");
repository.findAll();
repository.count();
repository.deleteById("O-100");
```

These operations are implemented by the framework.

### 2.2. What Does MongoRepository Inherit?

In modern Spring Data MongoDB versions, `MongoRepository` inherits capabilities including:

- CRUD via `ListCrudRepository`.
- Paging and sorting via `ListPagingAndSortingRepository`.
- Query by Example via `QueryByExampleExecutor`.
- MongoDB-specific methods such as `insert`.

This means `MongoRepository` exposes CRUD methods with the signatures and return types of your active version. When upgrading a Spring Data major version, check the interface API if your code relies on inherited methods.

### 2.3. The Repository Abstraction Is Not Active Record

`Order` is a domain/mapping object; it does not call `order.save()` on itself in this repository pattern. Data access logic belongs in the repository and service layers.

Example:

```java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<Order> findOne(String id) {
        return orders.findById(id);
    }
}
```

`OrderService` is a Spring service bean, while `OrderRepository` gets its runtime implementation generated by Spring Data.

---

## 3. Setting Up Spring Boot and MongoDB

### 3.1. Dependency

Use Spring Boot dependency management instead of manually mixing Spring Data and driver versions:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "<approved-boot-version>"
    id("io.spring.dependency-management") version "<approved-version>"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

This is a **Gradle Kotlin DSL template**; replace placeholders with approved actual versions. Do not run Gradle commands directly inside this lesson. A Spring Boot project that already has compatible plugins/BOM does not need to redeclare every block identically.

The Maven equivalent dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

### 3.2. Lab Database Configuration

In `src/main/resources/application.properties` for the **learning environment**:

```properties
spring.data.mongodb.uri=mongodb://127.0.0.1:27017/order_repository_lab
```

If using a Spring Boot version with different configuration properties, check the documentation for your exact version. Production must use a secrets manager or environment variables with TLS and credentials—never commit URIs containing passwords.

### 3.3. Repository Scanning

When repositories reside under the package of the `@SpringBootApplication` class, Spring Boot auto-configures Spring Data repositories automatically.

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Example package tree:

```text
com.example.orders
  OrdersApplication.java
  domain/Order.java
  repository/OrderRepository.java
  service/OrderService.java
```

If a repository lives outside the component/repository scan scope, you can use `@EnableMongoRepositories(basePackages = ...)`, while verifying multi-datasource or multiple `MongoTemplate` beans so repositories do not bind to the wrong database.

---

## 4. Entity: Mapping a Java Object to a MongoDB Document

Create the `Order` entity:

```java
package com.example.orders.domain;

import java.math.BigDecimal;
import java.util.Date;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.index.CompoundIndex;

@Document(collection = "orders")
@CompoundIndex(
    name = "ix_tenant_status_createdAt",
    def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1 }"
)
public class Order {

    @Id
    private String id;

    private String tenantId;
    private String orderNumber;
    private String status;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private Date createdAt;
    private boolean active;
    private List<String> tags;
    private Shipping shipping;

    public Order() {}

    // Getters/setters for remaining properties omitted
    // to keep focus on repository queries.

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public BigDecimal getAmount() { return amount; }
    public Date getCreatedAt() { return createdAt; }
    public Shipping getShipping() { return shipping; }

    public static class Shipping {
        private String city;
        private String district;

        public Shipping() {}

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
        public String getDistrict() { return district; }
        public void setDistrict(String district) {
            this.district = district;
        }
    }
}
```

This entity snippet is tailored for illustrating mapping and queries; in a real application, add complete constructors, getters/setters per your entity conventions (or use immutable types with proper constructor mapping).

### 4.1. Meaning of the Annotations

| Annotation | Effect |
| --- | --- |
| `@Document(collection = "orders")` | Maps the class to the `orders` collection |
| `@Id` | Maps the ID property to BSON `_id` |
| `@Field` | Customizes the field name or BSON target type |
| `@CompoundIndex` | Declares compound index metadata |
| `@Indexed` | Declares single-field index metadata |
| `@Version` | Supports optimistic locking when properly configured/mapped |

**Important:** `@CompoundIndex` does not guarantee MongoDB creates the index automatically in production. **Automatic index creation is disabled by default** in modern Spring Data MongoDB; manage indexes through controlled migrations/provisioning or enable auto-index creation deliberately in appropriate environments.

### 4.2. BigDecimal and Decimal128

Java `BigDecimal` should not be assumed identical to BSON `Decimal128` across every mapping configuration.

In the entity above:

```java
@Field(targetType = FieldType.DECIMAL128)
private BigDecimal amount;
```

requests mapping the field to BSON `Decimal128`. This matters for monetary range queries; test documents must store compatible types. Never use `double` for money when exact decimal precision is required.

### 4.3. @Id and Reserved Methods

`findById(id)` is a special base method that **targets the identifier property**, even if the entity has another regular Java field named `id` or a differently named ID field.

For example, if an entity has `@Id String primaryKey` and a regular `String id`:

- `findById(x)` queries `primaryKey` (BSON `_id`).
- A distinct query method such as `findUserById(x)` can target the regular `id` property.

Avoid naming non-ID properties similarly to ID and relying on guesswork; know repository reserved method names.

---

## 5. Lab Dataset for the Entire Lesson

Run the following commands in `mongosh` on your **lab MongoDB**—never run `drop()` in production.

```javascript
const lab = db.getSiblingDB("order_repository_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "O-101",
    tenantId: "A",
    orderNumber: "A-001",
    status: "PAID",
    amount: NumberDecimal("125.50"),
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    active: true,
    tags: ["vip", "online"],
    shipping: { city: "Hà Nội", district: "Ba Đình" }
  },
  {
    _id: "O-102",
    tenantId: "A",
    orderNumber: "A-002",
    status: "NEW",
    amount: NumberDecimal("49.90"),
    createdAt: ISODate("2026-11-02T08:00:00Z"),
    active: true,
    tags: ["online"],
    shipping: { city: "Đà Nẵng", district: "Hải Châu" }
  },
  {
    _id: "O-103",
    tenantId: "A",
    orderNumber: "A-003",
    status: "PAID",
    amount: NumberDecimal("300.00"),
    createdAt: ISODate("2026-11-03T08:00:00Z"),
    active: true,
    tags: ["priority"],
    shipping: { city: "Hà Nội", district: "Cầu Giấy" }
  },
  {
    _id: "O-104",
    tenantId: "B",
    orderNumber: "B-001",
    status: "PAID",
    amount: NumberDecimal("80.00"),
    createdAt: ISODate("2026-11-04T08:00:00Z"),
    active: true,
    tags: ["online"],
    shipping: { city: "TP. Hồ Chí Minh", district: "Quận 1" }
  },
  {
    _id: "O-105",
    tenantId: "A",
    orderNumber: "A-004",
    status: "CANCELLED",
    amount: NumberDecimal("10.00"),
    createdAt: ISODate("2026-11-05T08:00:00Z"),
    active: false,
    tags: [],
    shipping: { city: "Hà Nội", district: "Đống Đa" }
  },
  {
    _id: "O-106",
    tenantId: "B",
    orderNumber: "B-002",
    status: "NEW",
    amount: NumberDecimal("15.75"),
    createdAt: ISODate("2026-11-06T08:00:00Z"),
    active: true,
    tags: ["app"],
    shipping: { city: "Cần Thơ", district: "Ninh Kiều" }
  },
  {
    _id: "O-107",
    tenantId: "A",
    orderNumber: "A-005",
    status: "PAID",
    amount: NumberDecimal("9.95"),
    createdAt: ISODate("2026-11-07T08:00:00Z"),
    active: true,
    tags: ["online"],
    shipping: { city: "Hải Phòng", district: "Lê Chân" }
  },
  {
    _id: "O-108",
    tenantId: "B",
    orderNumber: "B-003",
    status: "PAID",
    amount: NumberDecimal("999.99"),
    createdAt: ISODate("2026-11-08T08:00:00Z"),
    active: true,
    tags: ["vip", "priority"],
    shipping: { city: "Hà Nội", district: "Long Biên" }
  }
]);

lab.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true, name: "uq_tenant_orderNumber" }
);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt" }
);

lab.orders.countDocuments({});
// 8
```

### 5.1. Verifying Types and Indexes

```javascript
lab.orders.getIndexes();

lab.orders.aggregate([
  {
    $project: {
      orderNumber: 1,
      amountType: { $type: "$amount" },
      createdAtType: { $type: "$createdAt" }
    }
  }
]).toArray();
```

Expected: `amountType` is `decimal` and `createdAtType` is `date`. Document order without an explicit sort **has no business guarantee**.

---

## 6. MongoRepository: Basic CRUD

Minimal repository:

```java
package com.example.orders.repository;

import com.example.orders.domain.Order;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, String> {
}
```

### 6.1. Find by ID

```java
Optional<Order> found = repository.findById("O-101");

found.ifPresent(order ->
    System.out.println(order.getStatus())
);
```

`findById` returns `Optional<Order>`. When no document matches, it returns `Optional.empty()`, not a "not found" exception.

### 6.2. Checking Existence and Counting

```java
boolean exists = repository.existsById("O-101");
long total = repository.count();
```

`existsById` avoids loading the full document like `findById` when you only need a boolean answer.

### 6.3. Save vs. Insert

```java
Order saved = repository.save(order);
Order inserted = repository.insert(newOrder);
```

- `save`: persists an entity with insert-or-update/replace semantics depending on ID, mapping, and concurrency settings.
- `insert`: intended for new entities; if the ID already exists, it throws a duplicate key exception.
- Do not assume `save` performs a partial `$set` on a few fields. Saving an entity with missing fields can overwrite the stored document unexpectedly.
- For concurrent updates, consider `@Version` optimistic locking or targeted updates via `MongoTemplate`/`@Update`.

### 6.4. Delete

```java
repository.deleteById("O-105");
```

**Data-deleting command**: run only in the lab or approved workflows. Never expose delete endpoints in production without authorization, auditing, and tenant scoping.

### 6.5. findAll() and findAll(Pageable)

```java
List<Order> all = repository.findAll();
```

This is dangerous on large collections: `findAll()` materializes all documents into memory and spikes RAM and network usage.

Prefer:

```java
Pageable pageRequest = PageRequest.of(
    0, 20,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<Order> firstPage = repository.findAll(pageRequest);
```

`PageRequest` requires imports from `org.springframework.data.domain`. In a multi-tenant service, `findAll(pageRequest)` still **lacks a tenant filter**; always use a repository method scoped by tenant.

---

## 7. What Are Derived Query Methods?

Spring Data parses the **method name** and translates it into a MongoDB query.

Example:

```java
List<Order> findByTenantIdAndStatus(
    String tenantId,
    String status
);
```

logically corresponds to:

```javascript
db.orders.find({
  tenantId: "A",
  status: "PAID"
});
```

To let Spring Data generate the method, simply declare it on the repository interface:

```java
public interface OrderRepository
        extends MongoRepository<Order, String> {

    List<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

You write no implementation class.

### 7.1. Method Name Structure

```text
find   Orders   By    TenantId   And   Status   OrderByCreatedAtDesc
 |       |      |        |        |       |              |
prefix subject delim   field     AND    field          sort
```

Common prefixes:

- `find...By`, `read...By`, `get...By`, `query...By`, `search...By`.
- `count...By`.
- `exists...By`.
- `delete...By`, `remove...By`.

The segment between `find` and `By` is generally descriptive, except for meaningful keywords like `Distinct`, `Top`, and `First`.

### 7.2. Query Lookup Strategy

Spring Data supports three strategies:

| Strategy | Meaning |
| --- | --- |
| `CREATE` | Build the query solely from the method name |
| `USE_DECLARED_QUERY` | Require an explicitly declared query; fail if missing |
| `CREATE_IF_NOT_FOUND` | Prefer a declared query; fall back to deriving from the method name |

`CREATE_IF_NOT_FOUND` is the common default. It lets you transition gradually from derived queries to `@Query` without writing new implementations.

### 7.3. Property Names Are Java Names, Not Arbitrary BSON Fields

If an entity has `customer.email`, you can write:

```java
List<Order> findByCustomer_Email(String email);
```

Spring Data uses mapping metadata to resolve the right BSON field, even if Java properties are renamed via `@Field`. Consequently, refactoring Java property names can affect derived query methods.

---

## 8. Common Derived Query Operators

The following table uses the lab `Order` entity.

| Method | MongoDB Logic | Notes |
| --- | --- | --- |
| `findByStatus("PAID")` | `{status:"PAID"}` | Equality |
| `findByTenantIdAndStatus("A","PAID")` | `{$and:[...] }` | Logical AND |
| `findByStatusOrActive("PAID",true)` | `{$or:[...] }` | Logical OR |
| `findByAmountGreaterThan(x)` | `{amount:{$gt:x}}` | Strictly greater than `x` |
| `findByAmountGreaterThanEqual(x)` | `{amount:{$gte:x}}` | Greater than or equal to |
| `findByAmountLessThan(x)` | `{amount:{$lt:x}}` | Strictly less than |
| `findByCreatedAtAfter(date)` | `{createdAt:{$gt:date}}` | After timestamp |
| `findByCreatedAtBefore(date)` | `{createdAt:{$lt:date}}` | Before timestamp |
| `findByStatusIn(list)` | `{status:{$in:list}}` | Value in set |
| `findByStatusNotIn(list)` | `{status:{$nin:list}}` | Value excluded |
| `findByActiveTrue()` | `{active:true}` | Boolean true |
| `findByActiveFalse()` | `{active:false}` | Boolean false |
| `findByShipping_City(city)` | `{"shipping.city":city}` | Nested path |
| `findByOrderNumberStartingWith(prefix)` | Prefix regex | Mind index usage |
| `findByOrderNumberEndingWith(suffix)` | Suffix regex | Usually index-unfriendly |
| `findByOrderNumberContaining(text)` | Contains regex | May scan many docs |
| `findByOrderNumberRegex(pattern)` | `$regex` | Check input safety |
| `findByShippingExists(flag)` | `{shipping:{$exists:flag}}` | Field existence |
| `findByStatusIsNull()` | `{status:null}` | Matches missing fields too per MongoDB semantics |
| `findByStatusNot("PAID")` | `{status:{$ne:"PAID"}}` | May also match missing fields |
| `findByTagsContaining("vip")` | Collection membership | Verify semantics by field type and version |

These methods **illustrate syntax**; to compile, each method requires a matching property type on the entity.

### 8.1. Writing a Practical Repository

```java
import java.math.BigDecimal;
import java.util.Collection;
import java.util.Date;
import java.util.List;

public interface OrderRepository
        extends MongoRepository<Order, String> {

    List<Order> findByTenantIdAndStatus(
        String tenantId, String status);

    List<Order> findByTenantIdAndAmountGreaterThanEqual(
        String tenantId, BigDecimal min);

    List<Order> findByTenantIdAndStatusIn(
        String tenantId, Collection<String> statuses);

    List<Order> findByTenantIdAndActiveTrue(String tenantId);

    List<Order> findByShipping_City(String city);

    List<Order> findByCreatedAtAfter(Date after);

    List<Order> findByOrderNumberStartingWith(String prefix);

    long countByTenantIdAndStatus(String tenantId, String status);

    boolean existsByTenantIdAndOrderNumber(
        String tenantId, String orderNumber);
}
```

Imports for `Order` and `MongoRepository` were shown in the previous section.

### 8.2. Inspect "Between" Carefully

Spring Data MongoDB documentation describes certain `Between` usages with two scalar arguments as open bounds:

```java
List<Order> findByAmountBetween(
    BigDecimal from, BigDecimal to);
```

Do not assume "between" is always **inclusive on both ends**. Verify whether it maps to `$gt`/`$lt` or uses `Range<T>` with explicit bounds in your version.

To eliminate ambiguity when inclusive bounds are required:

```java
List<Order>
findByAmountGreaterThanEqualAndAmountLessThanEqual(
    BigDecimal min, BigDecimal max);
```

In a multi-tenant context, include `TenantId` in the method or use `@Query` so data partitioning is never bypassed.

### 8.3. "IsNull" and "Exists" Are Not the Same

In MongoDB:

```javascript
{ status: null }
```

matches documents where `status` is `null` **or the field is missing**.

By contrast:

```javascript
{ status: { $exists: false } }
```

matches only documents **lacking the field**.

If you want documents where **the field explicitly exists and is `null`**, add an appropriate condition (such as `$type`) rather than assuming `findByStatusIsNull()` is exact.

---

## 9. AND/OR: Avoiding Broken Query Logic

Suppose you want:

> Find all orders for tenant A where status is PAID **or NEW**.

Correct filter:

```javascript
{
  tenantId: "A",
  status: { $in: ["PAID", "NEW"] }
}
```

In the repository:

```java
List<Order> findByTenantIdAndStatusIn(
    String tenantId,
    Collection<String> statuses
);
```

An easily misread method name:

```java
List<Order> findByTenantIdAndStatusOrActive(
    String tenantId,
    String status,
    boolean active
);
```

evaluates as `(tenantId = A AND status = PAID) OR active = true`, which can return **tenant B's records** whenever `active = true`. That is a severe cross-tenant data leak.

### 9.1. Use @Query When Logical Grouping Matters

```java
@Query("""
    {
      'tenantId': ?0,
      '$or': [
        { 'status': ?1 },
        { 'active': ?2 }
      ]
    }
    """)
List<Order> findByTenantAndStatusOrActive(
    String tenantId, String status, boolean active
);
```

Here, the tenant predicate applies to **both OR branches**, unlike the broken derived method above.

If your project uses Java earlier than 15, **text blocks `"""` are unavailable**; use concatenated regular strings while preserving the JSON structure.

### 9.2. Multi-Tenant Rules

For multi-tenant data:

- Every business query must carry a tenant scope or a verified defense at the data/authorization layer.
- Never accept a client-supplied tenant ID without verifying it against the authenticated principal.
- Never expose `findAll()` directly over a REST API.
- Test "tenant A cannot see tenant B" for every query shape, including `OR`, `delete`, and `count`.
- Putting `tenantId` as an appropriate index prefix can be critical for both performance and access patterns.

**Spring Data repositories do not automatically enforce tenant isolation** merely because an entity has a `tenantId` field.

---

## 10. Nested Properties and Underscores

Entity:

```java
public static class Shipping {
    private String city;
    private String district;
    // constructors/getters/setters...
}
```

MongoDB document:

```javascript
{
  shipping: {
    city: "Hà Nội",
    district: "Ba Đình"
  }
}
```

Method:

```java
List<Order> findByShipping_City(String city);
```

Spring Data resolves `Shipping_City` to the property path `shipping.city`.

### 10.1. Can You Omit the Underscore?

Normally you can write:

```java
List<Order> findByShippingCity(String city);
```

The parser attempts camel-case splitting, but if the class also defines a top-level `shippingCity` property, resolution can become **ambiguous**. An underscore defines the traversal boundary explicitly.

### 10.2. Avoid Arbitrary Underscores in Java Property Names

Spring Data reserves underscores for property traversal. If domain fields contain underscores, special escaping rules apply; stick to Java camelCase when designing entities.

### 10.3. @Field Mapping

Suppose:

```java
@Field("shipping_city")
private String shippingCity;
```

A derived query still references the Java property `shippingCity`, and the Spring Data mapping layer translates it to BSON `shipping_city`.

In `@Query`, query fields are also mapped through `MappingMongoConverter` in supported cases; do not mix Java property names and BSON field names without inspecting the generated MongoDB query—especially when field names contain dots or during schema migrations.

---

## 11. Return Types: Optional, List, Page, Slice, Stream

Repository methods differ not just in their filters. The **return type** dictates how many records are read and with what semantics.

| Return type | When to use | Considerations |
| --- | --- | --- |
| `Optional<Order>` | Zero or one result | Unexpected multiple matches can throw an error |
| `Order` | Expected single result | Missing document returns null/nullable per config |
| `List<Order>` | Small, reasonably bounded set | Can exhaust RAM if unbounded |
| `Page<Order>` | Need both content and total count | Count query can be expensive |
| `Slice<Order>` | Only need to know if a next page exists | Avoids total count query |
| `Stream<Order>` | Sequential processing of large datasets | Must close stream/cursor |
| `long` | Count / delete count | Avoids loading full entities |
| `boolean` | Existence check | Fast existence check |
| `Mono/Flux` | `ReactiveMongoRepository` | Not synchronous `MongoRepository` |

### 11.1. What Does Optional Mean?

```java
Optional<Order> order =
    repository.findByTenantIdAndOrderNumber(
        "A", "A-001"
    );
```

If a business rule requires uniqueness yet MongoDB lacks a unique index, duplicate matching records can exist. A single-result method **does not enforce uniqueness**; create an index:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true }
);
```

### 11.2. findFirst / Top to Limit Results

```java
Optional<Order> findFirstByTenantIdAndStatusOrderByCreatedAtDesc(
    String tenantId,
    String status
);
```

`First`/`Top` limits the result count. Combining with `OrderBy` intentionally retrieves the "latest" record.

**To remain deterministic when timestamps tie**, append `IdDesc` or sort by a unique key:

```java
Optional<Order> findFirstByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
    String tenantId, String status
);
```

Without a sort, "first" is not guaranteed to be the newest document.

### 11.3. Top N

```java
List<Order> findTop5ByTenantIdAndStatusOrderByCreatedAtDesc(
    String tenantId, String status
);
```

This caps results at 5 after filtering and sorting. For general-purpose APIs with dynamic page sizes, `Pageable` is more flexible.

### 11.4. Streams Must Be Closed

```java
try (Stream<Order> stream =
         repository.streamByTenantId("A")) {

    stream.forEach(order -> process(order));
}
```

`process(order)` is your business handler. A `Stream` can hold an open database cursor; **always use try-with-resources** and never let the stream outlive its transaction or method scope.

---

## 12. Dynamic Sorting and Static Sorting

### 12.1. Static Sort in the Method Name

```java
List<Order> findByTenantIdOrderByCreatedAtDesc(
    String tenantId
);
```

### 12.2. Dynamic Sort via Parameter

```java
List<Order> findByTenantId(
    String tenantId,
    Sort sort
);
```

Usage:

```java
List<Order> results = repository.findByTenantId(
    "A",
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"))
);
```

`Sort` takes **domain property names**, and Spring Data mapping resolves the corresponding BSON fields.

### 12.3. Sorting by Multiple Keys

Why add a second sort key?

```text
createdAt can collide across two orders:
2026-11-07T08:00Z, O-101
2026-11-07T08:00Z, O-102
```

Sorting solely by `createdAt` can return unstable ordering across index, plan, or write changes. Adding `id` provides a deterministic tie-breaker.

### 12.4. Never Let Clients Pass Arbitrary Sort Fields

An API like:

```text
GET /orders?sort=anyNestedField
```

can be abused to sort on unindexed fields, traverse expensive paths, or infer data via timing. Enforce an **allow-list**:

```java
Set<String> allowedSortFields =
    Set.of("createdAt", "amount", "orderNumber");
```

Validate the requested sort property and direction before constructing `Sort`.

---

## 13. Paging with Pageable

Declaration:

```java
Page<Order> findByTenantIdAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

Invocation:

```java
Pageable pageable = PageRequest.of(
    0,                                     // first page, zero-based
    20,                                    // max 20 items
    Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by("id").descending())
);

Page<Order> page = repository.findByTenantIdAndStatus(
    "A", "PAID", pageable
);

System.out.println(page.getContent().size());
System.out.println(page.getTotalElements());
System.out.println(page.getTotalPages());
System.out.println(page.hasNext());
```

### 13.1. Page vs. Slice

- `Page<T>` contains content, page index, and **total elements/pages**. The framework may execute an **additional count query**, depending on optimization.
- `Slice<T>` contains content and **whether a next page exists**, avoiding the total count query.
- `List<T>` with `Pageable` applies skip/limit/sort without returning pagination metadata.

Example:

```java
Slice<Order> findByTenantIdAndStatus(
    String tenantId, String status, Pageable pageable
);
```

**Java overload note:** you cannot declare two methods with the exact same name and parameter types differing only by `Page` vs. `Slice` return type in the same Java interface. Give them distinct names such as `findPageByTenantIdAndStatus` and `findSliceByTenantIdAndStatus`, or pick one return type per method.

### 13.2. Offset Pagination Has a Cost

`PageRequest.of(100000, 20, sort)` translates into a large `skip`. MongoDB must walk past many records before returning the requested page, and concurrent inserts or deletes shift offsets between requests.

For large datasets or infinite scrolling, consider:

- Keyset/cursor-based pagination.
- `ScrollPosition`/`Window` in supporting Spring Data versions.
- Sorting on a stable compound key such as `(createdAt, _id)`.
- Seek predicates using the last-seen key.
- An index aligned with both filter and sort.

**Never use deep offsets** as a default when an endpoint may scan millions of documents.

### 13.3. Pageable, Sort, and Limit Cannot Be Combined Arbitrarily

Spring Data repository infrastructure recognizes special parameters such as `Pageable`, `Sort`, and `Limit`, but many combinations are **invalid**:

- `Pageable` already carries a `Sort`; do not add a second `Sort` parameter.
- `Pageable` already carries a page size limit; do not combine it arbitrarily with `Limit`.
- `Top`/`First` have their own limiting semantics.

Check the Query Methods documentation for your exact Spring Data release before defining new signatures.

---

## 14. When Should You Switch from a Derived Query to @Query?

Derived queries are convenient for simple filters, but hit limits when:

- Method names grow too long and unreadable.
- `$or` conditions require explicit grouping parentheses.
- `$elemMatch` is needed for arrays of subdocuments.
- Explicit `$exists` combined with `$type` is required.
- Specific field projections, sorts, hints, or collations are needed.
- MongoDB operators not cleanly expressed via derivation must be used.
- You want a fixed query shape easy to cross-check with `mongosh` and `explain`.

Example complex query:

```javascript
{
  tenantId: "A",
  active: true,
  $or: [
    { status: "PAID", amount: { $gte: NumberDecimal("100.00") } },
    { tags: "vip" }
  ]
}
```

A method named `findByTenantIdAndActiveTrueAndStatusAndAmountGreaterThanEqualOrTagsContaining` is hard to read and highly prone to **logical precedence bugs**.

With `@Query`, the structure is explicit.

---

## 15. @Query: Declaring a MongoDB JSON Filter

Import:

```java
import org.springframework.data.mongodb.repository.Query;
```

Example:

```java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
List<Order> findExplicitlyByTenantAndStatus(
    String tenantId, String status
);
```

Mechanics:

- `?0` binds the **first method argument**.
- `?1` binds the **second method argument**.
- Parameter indices are **zero-based**.
- Spring Data binds and converts values to the appropriate BSON query types.

### 15.1. @Query JSON Filters Are Not SQL

**Correct:**

```java
@Query("{ 'amount': { '$gte': ?0 } }")
List<Order> amountAtLeast(BigDecimal min);
```

**Wrong:**

```java
@Query("SELECT * FROM orders WHERE amount >= ?0")
List<Order> amountAtLeastSql(BigDecimal min);
```

Spring Data MongoDB uses the **MongoDB query language**, not JDBC SQL, HQL, or JPQL.

### 15.2. String Binding Automatically Escapes Values

Spring Data MongoDB documentation notes that `String` parameters are **escaped during binding**; you cannot inject MongoDB operators into a query merely by passing a JSON string into `?0`.

Example:

```java
@Query("{ 'status': ?0 }")
List<Order> findStatus(String status);
```

Passing `"{ '$ne': null }"` does not turn it into a `$ne` operator—it is treated as a **literal String value**.

This **does not make SpEL or manual JSON string concatenation safe**. Never build JSON queries via string concatenation from user input.

### 15.3. Dynamic Queries with SpEL

```java
@Query("{ 'status': ?#{[0]} }")
List<Order> findStatusWithSpEL(String status);
```

Here `?#{[0]}` accesses the first argument via Spring Expression Language. SpEL is more powerful than indexed parameters: it can invoke functions, evaluate conditionals, and build subdocuments.

**Warning:** Spring Data docs warn that inputs used in SpEL must be sanitized because expressions can alter query structure unexpectedly. For straightforward filters, **prefer `?0` and `?1`**.

### 15.4. Applying the Tenant Predicate Across the Entire OR

```java
@Query("""
    {
      'tenantId': ?0,
      'active': true,
      '$or': [
        {
          'status': ?1,
          'amount': { '$gte': ?2 }
        },
        { 'tags': ?3 }
      ]
    }
    """)
List<Order> findBusinessCandidates(
    String tenantId,
    String status,
    BigDecimal minAmount,
    String requiredTag
);
```

Note that `tags: ?3` matches arrays containing that element via MongoDB array equality semantics without custom regex. Always test tenant A/B isolation before exposing the API.

---

## 16. @Query fields: Returning Fewer Fields

When you only need `status`, `amount`, and `createdAt`, avoid fetching entire documents packed with notes, addresses, and large arrays.

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    fields = "{ 'status': 1, 'amount': 1, 'createdAt': 1 }"
)
List<Order> findStatusAndAmount(
    String tenantId, String status
);
```

MongoDB projections **include `_id` by default** unless explicitly excluded.

### 16.1. Important: Returned Entities May Be Partial

With return type `Order`, fields **excluded from the projection** receive Java default values (`null`/`false` depending on type).

Never fetch a partial entity and blindly call `save`:

```java
// Avoid: this is a partial Order, not the full aggregate.
Order partial = repository.findStatusAndAmount("A", "PAID").get(0);
repository.save(partial);
```

You risk overwriting the stored document with missing fields, causing data loss or business bugs.

### 16.2. Fields Projection and @Field Mapping

`fields` accepts a MongoDB JSON projection document. When using `@Field` or custom conversions, verify how field names are mapped so properties are not unexpectedly omitted. Do not confuse `fields` with the `$project` stage of an aggregation pipeline.

### 16.3. Exclusion Projections

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    fields = "{ 'largePayload': 0, 'privateNotes': 0 }"
)
List<Order> findWithoutLargeFields(String tenantId);
```

Excluding large fields does not prevent data leaks if other sensitive fields remain. **Use explicit DTOs or projections for API responses** rather than returning raw entities.

---

## 17. Interface-Based Projections and DTOs

### 17.1. Closed Interface Projection

```java
public interface OrderSummary {
    String getId();
    String getStatus();
    BigDecimal getAmount();
}
```

Repository:

```java
List<OrderSummary> findByTenantIdAndStatus(
    String tenantId, String status
);
```

Spring Data determines the exact properties required and optimizes the fetched fields when using a **closed projection**.

If the repository already declares a method with the same signature returning `List<Order>`, you cannot add an overload differing only in return type. Use a distinct name such as:

```java
List<OrderSummary> findSummaryByTenantIdAndStatus(
    String tenantId, String status
);
```

### 17.2. DTO Projection with a Record

```java
public record OrderCard(
    String status,
    BigDecimal amount
) {}
```

The repository can return:

```java
List<OrderCard> findByTenantIdAndStatus(
    String tenantId, String status
);
```

Constructor/property mapping, version compatibility, and field selection must align. For DTO classes with multiple constructors, apply `@PersistenceCreator` appropriately.

### 17.3. Dynamic Projection

```java
<T> List<T> findByTenantId(
    String tenantId, Class<T> type
);
```

Usage:

```java
List<Order> entities =
    repository.findByTenantId("A", Order.class);

List<OrderSummary> summaries =
    repository.findByTenantId("A", OrderSummary.class);
```

**Constraint:** Spring Data recognizes the `Class<T>` argument as the dynamic projection type parameter. Once recognized as such, it cannot be referenced as an arbitrary filter argument inside `@Query`.

### 17.4. Open Projections and Performance

Projections using `@Value` with SpEL to compute derived values are called **open projections**. Because they may reference arbitrary properties on the target entity, Spring Data cannot always optimize field projection as it does with closed projections.

Never assume every interface projection automatically reduces network transfer; verify actual query output and profiler metrics.

### 17.5. API Safety

In REST APIs, return a dedicated response DTO:

```java
public record OrderResponse(
    String id,
    String status,
    BigDecimal amount
) {}
```

instead of serializing the raw `Order` entity containing internal fields, tokens, or sensitive metadata. The service maps projections/domain models to response DTOs under authorization rules.

---

## 18. @Query sort: Static and Customizable Sorting

### 18.1. Default Sort in the Annotation

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    sort = "{ 'createdAt': -1, '_id': -1 }"
)
List<Order> findSortedPaidOrders(
    String tenantId, String status
);
```

The JSON `sort` clause fixes the field sort order.

### 18.2. Overriding with a Sort Parameter

```java
@Query(
    value = "{ 'tenantId': ?0 }",
    sort = "{ 'createdAt': -1 }"
)
List<Order> findWithDefaultSort(
    String tenantId, Sort sort
);
```

According to Spring Data docs, `Sort.unsorted()` preserves the default sort from `@Query`; `Sort.by(ASC, "createdAt")` overrides the direction of that property; additional properties in `Sort` can append to the default sort.

If an API lets users specify sorting, **allow-list fields** and ensure pagination includes a deterministic tie-breaker.

### 18.3. Pageable with @Query

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    fields = "{ 'orderNumber': 1, 'status': 1, 'amount': 1 }"
)
Page<Order> pageByTenantAndStatus(
    String tenantId,
    String status,
    Pageable pageable
);
```

`Pageable` applies skip, limit, and sort. `Page` may issue an extra count query for total elements. If totals are unnecessary, return `Slice`.

---

## 19. @Query count and exists

Beyond derived `countBy...` and `existsBy...` names, `@Query` provides flags for counting and existence checks.

### 19.1. Derived Count

```java
long countByTenantIdAndStatus(
    String tenantId, String status
);
```

On the lab fixture, tenant A with `PAID` has **3** records (`O-101`, `O-103`, `O-107`).

### 19.2. Annotated Count

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    count = true
)
long countMatchingOrders(
    String tenantId, String status
);
```

`count = true` executes the query as a **count operation** instead of loading an entire `List<Order>` and calling `size()` in Java.

### 19.3. Derived Exists

```java
boolean existsByTenantIdAndOrderNumber(
    String tenantId, String orderNumber
);
```

Before creating a new order, an `exists` check helps produce friendly validation errors, **but never replaces a unique index**. Two concurrent requests can both observe `false` and attempt inserts simultaneously; only a unique index enforces uniqueness at the database level.

### 19.4. Annotated Exists

```java
@Query(
    value = "{ 'tenantId': ?0, 'orderNumber': ?1 }",
    exists = true
)
boolean orderNumberExists(
    String tenantId, String orderNumber
);
```

Use this when the filter is awkward to derive from a method name or you want the JSON query explicit.

---

## 20. Deleting with Derived Methods and @Query(delete = true)

### 20.1. Derived Delete

```java
long deleteByTenantIdAndStatus(
    String tenantId,
    String status
);
```

Per MongoDB repository docs, a delete method returning a numeric count deletes matching documents and returns the **number of deleted documents**.

### 20.2. Returning List Has Different Semantics

```java
List<Order> deleteByTenantIdAndStatus(
    String tenantId,
    String status
);
```

When returning `List<Order>`, Spring Data MongoDB **fetches matching entities before deleting them and returns the deleted entities**. This consumes more memory and has different concurrency behavior than returning a delete count.

**Do not declare both methods with the same name and parameters differing only in return type** in one Java interface; the snippets above show mutually exclusive alternatives.

### 20.3. Annotated Delete

```java
@Query(
    value = "{ 'tenantId': ?0, 'active': false }",
    delete = true
)
long deleteInactiveForTenant(String tenantId);
```

**Test only in a lab environment.** Always enforce the tenant predicate; production APIs must verify delete permissions, audit actions, and evaluate soft deletes.

### 20.4. Deletions and Transactions / Auditing

Repository deletion does not automatically execute an entire business workflow:

- Emitting audit events.
- Cleaning up references in other collections.
- Invalidating caches.
- Coordinating multi-document transactions.
- Enforcing legal retention policies.
- Checking user/tenant permissions.
- Updating counters in external systems.

Those belong in service/domain transaction logic or an outbox pattern, not automatically in `deleteBy...`.

---

## 21. @Update and Query-Based Updates

**Alongside `@Query`**, Spring Data MongoDB provides `@Update` for repository update methods. Understanding it prevents the misconception that `@Query` modifies data on its own.

### 21.1. @Query Is the Filter, @Update Is the Action

```java
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

@Query("{ 'tenantId': ?0, '_id': ?1 }")
@Update("{ '$set': { 'status': ?2 } }")
long updateStatusForTenant(
    String tenantId,
    String orderId,
    String newStatus
);
```

Per Spring Data docs, repository update methods can return `void` or a numeric count indicating modified documents. `@Update` defines the update document while `@Query` provides the filter.

### 21.2. Derived Update Method Naming

```java
@Update("{ '$inc': { 'visits': 1 } }")
long findAndIncrementVisitsByLastname(String lastname);
```

This pattern follows repository update semantics: the method uses a finder prefix like `find...By` while the update action is declared via `@Update`.

A name like `updateAllByLastname` **is not parsed as a derived query in this way** unless paired with an appropriate `@Query`. Verify against your exact Spring Data version.

### 21.3. Do Not Confuse Update with Save

`repository.save(entity)` performs replacement/merge semantics with mapping and optimistic locking. `@Update` applies MongoDB update operators such as `$set` and `$inc` directly to targeted fields. Under high concurrency, targeted updates help avoid lost updates, though idempotency and atomicity rules still apply.

### 21.4. Lifecycle Events and @Version

Spring Data MongoDB documentation notes that repository update methods **do not trigger persistence/mapping lifecycle events** the way entity save paths do. If your project relies on auditing callbacks or `@Version`, verify update semantics before migrating from `save` to repository update methods.

---

## 22. @Query with Nested Arrays and $elemMatch

Suppose a document contains an array of subdocuments:

```javascript
{
  _id: "O-200",
  tenantId: "A",
  lineItems: [
    { sku: "PEN", quantity: 2 },
    { sku: "BOOK", quantity: 5 }
  ]
}
```

Requirement:

> Find orders having **at least one line item** with both `sku = BOOK` and `quantity >= 3`.

Using two independent dot-notation predicates can match **two different elements** inside the array.

Use `$elemMatch`:

```java
@Query("""
    {
      'tenantId': ?0,
      'lineItems': {
        '$elemMatch': {
          'sku': ?1,
          'quantity': { '$gte': ?2 }
        }
      }
    }
    """)
List<Order> withItemAtLeast(
    String tenantId, String sku, int minQuantity
);
```

**Prerequisite:** The `Order` entity must map a `lineItems` property (e.g., `List<LineItem>`). The initial fixture lacks this field, so seed appropriate lab data before running the query.

### 22.1. When Multiple Aggregation Stages Are Needed

`@Query` is a JSON find query; it is **not** where you write a multi-stage pipeline with `$match`, `$group`, `$lookup`, and `$unwind`.

Use:

- `@Aggregation` on a repository method for relatively fixed pipelines.
- `MongoTemplate.aggregate` for complex or dynamic pipelines.
- A custom repository implementation when business queries require branching logic, reusable criteria, or dynamic options.

---

## 23. @Query with @Meta, hint, and collation

### 23.1. @Meta Execution Time Limits

```java
import org.springframework.data.mongodb.repository.Meta;

@Meta(maxExecutionTimeMs = 3000)
@Query("{ 'tenantId': ?0, 'status': ?1 }")
List<Order> guardedQuery(String tenantId, String status);
```

`@Meta` configures query options such as `maxExecutionTimeMs`, comments, and `allowDiskUse` where supported. `maxExecutionTimeMs` enforces a server-side MongoDB execution limit; it does not replace client socket timeouts or overall API deadlines.

### 23.2. Index Hints

```java
@Query(
    value = "{ 'tenantId': ?0, 'status': ?1 }",
    hint = "ix_tenant_status_createdAt"
)
List<Order> withSpecificIndex(
    String tenantId, String status
);
```

Or use the `@Hint` annotation on the method where supported by the API.

**Do not add hints out of habit.** If an index is renamed, dropped, or mismatched in selectivity, a hint can trigger errors or worse performance. Letting the query planner choose an index is usually the right starting point.

### 23.3. Collation

```java
@Query(
    value = "{ 'shipping.city': ?0 }",
    collation = "en_US"
)
List<Order> byCityWithCollation(String city);
```

Collation governs locale-specific string comparison and sorting. For Vietnamese text, choose a locale matching your business requirements and verify collation/index support; `en_US` here is purely an API syntax example, not a recommendation for Vietnamese names.

**Note:** A query using a different collation from an index's collation may fail to use that index for string comparisons or sorts as expected.

### 23.4. Read Preference

Repositories and query methods can specify read preference via `@ReadPreference` or `@Query(readPreference = ...)` when supported by the framework version.

Reading from secondaries can return **stale data** due to replication lag. Never switch `readPreference` to secondary solely to offload the primary without accounting for read-your-writes and consistency requirements.

---

## 24. Regex, IgnoreCase, and Input Safety

### 24.1. Derived IgnoreCase

```java
List<Order> findByOrderNumberIgnoreCase(String orderNumber);
```

Spring Data MongoDB typically implements `IgnoreCase` via regex with the `i` flag. While convenient, it will not use indexes as efficiently as exact equality.

### 24.2. StartsWith, Contains, and Indexes

```java
List<Order> findByOrderNumberStartingWith(String prefix);

List<Order> findByOrderNumberContaining(String fragment);
```

- Anchored prefix regexes can leverage B-tree indexes under appropriate conditions.
- Substring/contains regexes usually cannot use B-tree indexes efficiently.
- Case-insensitive regexes and collations do not always use indexes as expected.
- For full-text search use cases, evaluate MongoDB text search or Atlas Search instead of slow regex scans.

### 24.3. @Query with Regex

```java
@Query("{ 'orderNumber': { '$regex': ?0, '$options': 'i' } }")
List<Order> regexOrderNumber(String pattern);
```

**Never** allow clients to submit arbitrary unbounded regexes. Catastrophic backtracking and unbounded patterns can exhaust server resources. Enforce input length/rate limits, validate allowed pattern syntax, prefer literal searches when possible, and set execution timeouts.

If you only want a **literal substring search**, properly escape regex metacharacters in Java (such as `Pattern.quote(userInput)` per your project's semantics) before passing the pattern.

### 24.4. @Query String Binding Does Not Make SpEL Safe

`?0` is safely escaped as a bound parameter, whereas `?#{...}` is a full expression layer. Never concatenate operators or SpEL fragments from user-supplied input.

---

## 25. How Does @Aggregation Differ from @Query?

`@Query` handles find filters, projections, and sorts. When you need an aggregation pipeline:

```javascript
[
  { $match: { tenantId: "A" } },
  { $group: { _id: "$status", total: { $sum: 1 } } },
  { $sort: { total: -1 } }
]
```

use `@Aggregation`:

```java
import org.springframework.data.mongodb.repository.Aggregation;

public interface OrderRepository
        extends MongoRepository<Order, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { '_id': '$status', 'total': { '$sum': 1 } } }",
        "{ '$sort': { 'total': -1 } }"
    })
    List<StatusCount> countByStatusForTenant(String tenantId);
}

public interface StatusCount {
    String getId();
    long getTotal();
}
```

This is an **illustrative projection/mapping example**; depending on version, mapping `_id` from aggregation output to an interface getter may require DTO or projection adjustments. Always verify with an integration test.

### 25.1. Aggregation Pagination Differs from Find Queries

Per Spring Data MongoDB docs, repository methods using `@Aggregation` **do not support returning `Page` directly** the way find queries do in documented versions; you can pass `Pageable` and return `Slice` where supported. If you need a total count, use a separate count query or `$facet` depending on the use case.

### 25.2. When to Use MongoTemplate?

Use `MongoTemplate` or a custom repository when:

- Query filters are built dynamically from many optional inputs.
- Complex nested `$and`/`$or` trees are needed.
- Multi-stage updates or aggregations are required.
- Fine-grained cursor, hint, or client-session controls are needed.
- Reusable `Criteria` helpers are shared across queries.
- Derived method names become unreadable or unmaintainable.

`@Query` is not the right tool for every MongoDB operation.

---

## 26. Query by Example (QBE): Another Option

Alongside derived queries and `@Query`, `MongoRepository` supports `QueryByExampleExecutor`:

```java
Order probe = new Order();
// Set probe fields using appropriate setters.
// Example: probe.setStatus("PAID");

Example<Order> example = Example.of(probe);
List<Order> matches = repository.findAll(example);
```

QBE is handy for simple equality filters built from a "probe" entity. However:

- `null` fields are ignored by default.
- Primitive `boolean`/`int` fields may silently enter the query because they always hold default values.
- It lacks flexible nested grouped `OR` conditions like `@Query`/`Criteria`.
- String matching via `ExampleMatcher` has datastore limitations.
- Tenant scoping requires extra care.

Do not pick QBE solely to reduce method count when business queries need range conditions or grouped `OR` logic.

---

## 27. Query Correctness: Especially Tenant Isolation, Nulls, and Result Limits

### 27.1. Enforce Tenant Checks Before Querying the Database

```java
public List<Order> paidOrders(String requestedTenant) {
    String allowedTenant = principalTenantId();

    if (!allowedTenant.equals(requestedTenant)) {
        throw new AccessDeniedException("Tenant mismatch");
    }

    return repository.findByTenantIdAndStatus(
        allowedTenant, "PAID"
    );
}
```

`principalTenantId()` illustrates retrieving the tenant from the authenticated principal. Simply accepting a tenant from an HTTP header or query parameter and passing it straight to the repository **is insufficient for isolation**.

### 27.2. Missing vs. Null

MongoDB evaluates `{field: null}` differently from SQL `IS NULL`. When you must distinguish missing fields from explicit nulls, use `$exists`/`$type` and write explicit tests.

### 27.3. Method Names Do Not Bound Resource Usage

`List<Order> findByTenantId("A")` can return millions of documents. Use `Page`/`Slice`, explicit limits, or a properly lifecycle-managed streaming cursor.

### 27.4. Stable Sorting

Sorting solely on a non-unique `createdAt` causes duplicate or skipped items across pages when data mutates. Pair `createdAt` with `id` when implementing keyset paging.

### 27.5. Unique Business Keys

`existsByTenantIdAndOrderNumber` is a precheck; it **never replaces** a unique index and proper duplicate-key exception handling under concurrent race conditions.

---

## 28. Performance: Do @Query and Derived Queries Differ?

These two methods:

```java
List<Order> findByTenantIdAndStatus(
    String tenantId, String status
);
```

and:

```java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
List<Order> withQueryAnnotation(
    String tenantId, String status
);
```

typically emit equivalent MongoDB filters. Given the same projection, sort, and options, the MongoDB query planner chooses the same execution plan.

**Never assume `@Query` is faster simply because you wrote the JSON manually.** Performance depends primarily on:

- Which index is used.
- Query selectivity.
- Sort and pagination strategy.
- Document size and projection.
- Result count.
- Cache and working set fit.
- Network latency.
- Read preference and consistency level.
- Database and server resources.

### 28.1. Suggested Index for the Lab

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt" }
);
```

Supports:

```javascript
db.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 });
```

This index **does not** optimize every query involving `amount`, `shipping.city`, or regexes. Design indexes around overall workload, cardinality, and write overhead.

### 28.2. Explain in mongosh

```javascript
db.orders.find({
  tenantId: "A",
  status: "PAID"
}).sort({ createdAt: -1 }).explain("executionStats");
```

Inspect:

- `winningPlan`, `IXSCAN` vs. `COLLSCAN`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- `executionTimeMillis`.

Even an `IXSCAN` scanning 100,000 keys to return 5 documents can still be inefficient.

### 28.3. Page Count Queries Can Be Expensive

Endpoints returning `Page<Order>` need total elements, often triggering a count query. Under high traffic with poorly indexed filters, the count query can cost more than fetching the 20 documents themselves.

If the UX only needs a "Load more" button, use `Slice<Order>` or keyset/scroll pagination.

### 28.4. Reactive Is Not Automatically Faster

Spring Data provides `ReactiveMongoRepository` returning `Flux`/`Mono`. It differs from synchronous `MongoRepository` in execution model, **not by making unindexed MongoDB queries run faster**. Choose based on WebFlux vs. MVC and your overall concurrency architecture.

---

## 29. @Query, Spring Data Mapping, and Conversion Pitfalls

### 29.1. String IDs and ObjectId

With an entity field:

```java
@Id
private String id;
```

MongoDB `_id` may actually be stored as a String or an `ObjectId` depending on data origin and conversion. Spring Data converts valid 24-character hex `String` IDs to `ObjectId` in standard mapping configurations.

The fixture in this lesson uses non-hex String `_id` values like `"O-101"` to avoid ambiguity. When migrating systems, verify the actual BSON type of `_id` using `$type`.

### 29.2. Date and Timezones

This lab uses `java.util.Date` to minimize converter differences. If your domain uses `Instant`, `LocalDateTime`, or `OffsetDateTime`, verify Java Time codecs/converters and timezone policies.

Avoid ambiguous local timezones when defining query ranges:

```javascript
{ createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") } }
```

MongoDB BSON Date stores UTC timestamps; `Date`/`Instant` mappings must align with explicit business timezone boundaries.

### 29.3. Decimal128

`@Field(targetType = FieldType.DECIMAL128)` maps `BigDecimal` to BSON `Decimal128`. If older documents in the collection stored monetary amounts as `double` or `string`, range queries can yield surprising results under BSON type comparison rules. Clean up data and validate types before switching.

### 29.4. Projections Do Not Replace Access Control

`fields = "{'amount':1}"` is not an authorization boundary. Another caller might invoke a different repository method returning the full entity. Service and API security must control field visibility.

### 29.5. Saving an Entity Loaded from a Partial Projection

Reading an entity with omitted fields and calling `save` can wipe out the unloaded fields. Use read-only DTOs/projections for list endpoints and load the full aggregate—or use a targeted update—when modifying state.

---

## 30. Integration Tests for Repository Query Methods

Never rely on H2/JPA SQL tests to prove MongoDB query derivation works; test against a real MongoDB instance or compatible test container.

### 30.1. @DataMongoTest

Spring Boot provides `@DataMongoTest` to test MongoDB mapping and repositories without booting the entire web stack.

Illustrative test logic (assuming a connected test database and per-test isolated seed data):

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsTenantPaidOrders() {
        var result =
            repository.findByTenantIdAndStatus("A", "PAID");

        assertThat(result)
            .allMatch(order ->
                "A".equals(order.getTenantId())
                && "PAID".equals(order.getStatus())
            );
    }
}
```

**Important:** The test requires fixture data to be seeded before asserting specific document counts. `@DataMongoTest` does not automatically insert this lesson's sample data.

### 30.2. Testcontainers and Real MongoDB

A complete integration test strategy:

1. Start a MongoDB test container or ephemeral deployment matching your target version.
2. Point Spring Boot's `spring.data.mongodb.uri` at the container.
3. Seed data via `MongoTemplate` or `mongosh`.
4. Create indexes matching your migration/lifecycle setup.
5. Test derived methods, `@Query`, pagination, `count`, `exists`, and `delete`.
6. Verify typed fields (`Date`, `Decimal128`, `ObjectId`/`String`).
7. Test tenant isolation, range boundaries, and concurrent uniqueness.
8. Ensure cleanup and container shutdown after tests complete.

Avoid testing repository query methods solely by mocking the repository, because mocks never execute query parsing or mapping.

### 30.3. Essential Test Cases

| Case | Expectation |
| --- | --- |
| `findByTenantIdAndStatus("A","PAID")` | Returns only tenant A's PAID orders |
| `countByTenantIdAndStatus("A","PAID")` | Returns `3` on the fixture |
| `existsByTenantIdAndOrderNumber("A","A-001")` | Returns `true` |
| `findByShipping_City("Hà Nội")` | Returns orders matching `shipping.city` |
| `findTop2...OrderByCreatedAtDesc` | Returns the exact 2 newest results |
| `@Query` with `OR` and outer tenant filter | Does not leak tenant B records |
| `@Query(fields=...)` | Loads only requested fields |
| `Pageable` sorting by `createdAt` and `id` | Deterministic ordering |
| Amount range boundaries | Inclusive/exclusive matches query intent |
| Empty result | Returns `Optional.empty()` / empty list |
| Input containing special characters | Parameter binding does not turn values into operators |
| Concurrent unique inserts | Duplicate insert is rejected |
| Reading partial entity then saving | Guarded against destructive overwrites |
| `@Query(delete=true)` | Deletes only within target tenant with audit/approval |

### 30.4. Inspecting Generated Queries

Depending on framework and driver version, use Spring Data MongoDB debug logging and the MongoDB Driver `CommandListener` to inspect generated query shapes. **Never log full query literals containing sensitive values.** When tuning, run `explain("executionStats")` in MongoDB with an equivalent query and representative dataset.

---

## 31. When Not to Cram Everything into a Method Name

You may encounter derived method names like:

```java
findTop25ByTenantIdAndActiveTrueAndStatusInAndAmountGreaterThanEqualAndCreatedAtBeforeOrderByCreatedAtDesc(...)
```

Such names become unmaintainable when:

- There are 5–10 optional filters.
- Complex `OR` grouping is required.
- Regexes, projections, and dynamic sorts combine.
- Business filter logic repeats across endpoints.
- MongoDB operators not supported by derivation are needed.
- Query planner hints or aggregations are required.

### 31.1. Tool Selection Guide

| Complexity | Recommended Approach |
| --- | --- |
| Basic CRUD and 1–3 field filters | `MongoRepository` + derived methods |
| Fixed filter with `OR`, grouping, or nested operators | `@Query` |
| Only a few fields needed for list endpoints | Projection interface/DTO, `@Query(fields)` |
| Dynamic optional filters from UI | `MongoTemplate` + `Criteria` / custom repository |
| Grouping, joins, facets | `@Aggregation` or `MongoTemplate` aggregation |
| Bulk updates or complex write semantics | `MongoTemplate`/bulk operations or `@Update` where appropriate |
| Multi-tenant security | Service/authorization layer + tenant-scoped repositories |
| Specialized search features | Dedicated MongoDB/Spring Data search APIs & indexes |
| Large query-driven exports | `Stream`/`Scroll` with explicit resource cleanup |

**Takeaway:** A repository describes data access cleanly. Never turn the interface into a mini-programming language of hundred-character method names.

---

## 32. Common Pitfalls

| Pitfall | Cause | Fix |
| --- | --- | --- |
| Repository complains property not found | Name does not match Java entity | Fix name; check nested path |
| `findByShippingCity` picks wrong field | Camel-case path ambiguity | Use `Shipping_City` |
| Using BSON field name in derived method | Parser inspects Java properties | Use entity property name and let mapping translate |
| `findById` queries unexpected field | Reserved ID method | Distinguish `@Id` property from regular `id` field |
| `findFirst...` without sort | "First" is undefined | Add `OrderBy` or `Sort` |
| `findAll()` on a large collection | Materializes too many docs | Use pagination, `Stream`, or limits |
| Slow `Page` endpoint | Expensive total count query | Consider `Slice`, keyset paging, or index |
| Putting SQL inside `@Query` | MongoDB does not use SQL | Write BSON JSON queries |
| Wrong `?0`/`?1` index | Zero-based indexing | Match method parameter indices |
| Concatenating JSON strings from input | Injection / malformed queries | Use parameter binding and validation |
| Dynamic SpEL from user input | Expression injection / logic flaws | Sanitize and restrict expressions |
| Loading partial `fields` then calling `save` | Overwrites unloaded fields | Use DTOs or read-only projections |
| `@Query(fields)` returns sensitive data | Projection is not authorization | Enforce API authorization and DTOs |
| Slow contains regex | Cannot use B-tree index effectively | Use search indexes or different query shapes |
| `IgnoreCase` misses expected index | Regex collation/index semantics | Check `explain` and index strategy |
| `@CompoundIndex` declared but missing in DB | Auto-index creation off by default | Run migrations/provisioning |
| Sort lacks a tie-breaker | Duplicate or skipped rows across pages | Append unique key (`id`) to sort |
| Using `countBy...` to enforce uniqueness | Race condition | Create a unique index |
| Delete query missing tenant filter | Cross-tenant deletion | Scope filter + auth + tests |
| Returning `Optional` on non-unique query | Multiple matches throw exception | Add unique index or `First`/`Top` |
| Ignoring null vs. missing semantics | MongoDB `null` matches missing | Use `$exists`/`$type` when needed |
| Calling `save` on detached/partial entity | Unintended field overwrites | Use optimistic locking or targeted updates |
| Using `@Query` for an aggregation pipeline | Find JSON != pipeline | Use `@Aggregation` or `MongoTemplate` |
| Passing both `Pageable` and `Sort` | Conflicting special parameters | Use one mechanism |
| Comparing derived vs. `@Query` via 1 request | Different cache/data state | Benchmark identical shapes and indexes |
| Using `@DataMongoTest` without seeding data | Test asserts on empty data | Use Testcontainers + explicit seeding |
| Upgrading Spring Data major blindly | API/mapping/driver changes | Align BOM + run integration tests |
| Logging raw production query JSON | Leaks PII / tenant data | Redact literals and log tracing metadata |

---

## 33. Practice Exercises

### Exercise 1 — CRUD

Create `OrderRepository extends MongoRepository<Order, String>`, and call `findById`, `existsById`, and `count`. What does `findById` return when an ID does not exist?

**Answer:** `Optional.empty()`.

### Exercise 2 — Derived AND

Write a method to retrieve orders for tenant A with status PAID.

**Answer:**

```java
List<Order> findByTenantIdAndStatus(
    String tenantId, String status);
```

### Exercise 3 — Count Fixture

On the 8 lab documents, what is `countByTenantIdAndStatus("A", "PAID")`?

**Answer:** `3`.

### Exercise 4 — Exists

Write a method checking whether tenant A already has order number `A-001`. Why is an `exists` check alone insufficient to prevent concurrent duplicates?

### Exercise 5 — Range

Write a method fetching orders with `amount >= min` for tenant A. Distinguish `GreaterThan` from `GreaterThanEqual`.

### Exercise 6 — Between

Is `findByAmountBetween(min, max)` always inclusive?

**Answer:** No. Verify how `Between` maps in your Spring Data MongoDB version or use `GreaterThanEqualAndLessThanEqual`.

### Exercise 7 — In

Write a method fetching tenant A orders whose status is in `NEW`/`PAID`.

### Exercise 8 — OR Security

Analyze the bug in `findByTenantIdAndStatusOrActive` in a multi-tenant app. Write a `@Query` that applies the tenant filter across the entire `OR`.

### Exercise 9 — Nested

What method name corresponds to `shipping.city` in MongoDB? Why might an underscore be needed?

**Answer:** `findByShipping_City`; it unambiguously separates property path segments.

### Exercise 10 — @Field

An entity has `@Field("shipping_city")` on Java property `shippingCity`. Which name does a derived method use?

**Answer:** The Java property name `ShippingCity` in the method name.

### Exercise 11 — Null

Compare `findByStatusIsNull()` against `{status: {$exists: false}}`.

### Exercise 12 — Top

Write a method retrieving the 3 newest PAID orders for tenant A with an ID tie-breaker.

### Exercise 13 — Pageable

Create a `PageRequest` for the second page, page size 20, sorted by `createdAt DESC, id DESC`. What page index does Spring Data start from?

**Answer:** `0`; the second page has index `1`.

### Exercise 14 — Page vs. Slice

A mobile app only has a "Load more" button. Why can `Slice` be better than `Page`?

### Exercise 15 — Deep Offset

Why can `PageRequest.of(100000, 20)` be slow and return shifted results when data changes? Propose a keyset strategy.

### Exercise 16 — @Query JSON

Write a `@Query` fetching orders with `amount >= 100` and `status = PAID` for tenant A using `?0`, `?1`, and `?2`.

### Exercise 17 — Zero-Based Binding

In `@Query("{ 'tenantId': ?0, 'status': ?1 }")`, which argument does `?1` bind?

**Answer:** The second argument.

### Exercise 18 — JSON vs. SQL

Why does `@Query("SELECT * FROM orders")` not work with `MongoRepository`?

### Exercise 19 — @Query(fields)

Use `fields` to return only `status` and `amount`. Why should you never call `save` on an entity loaded with missing fields?

### Exercise 20 — Projection

Create an `OrderSummary` interface with `getId`, `getStatus`, and `getAmount`, and return `List<OrderSummary>` from the repository.

### Exercise 21 — Dynamic Projection

Write `<T> List<T> findByTenantId(String tenantId, Class<T> type)` and call it for both `Order` and `OrderSummary`.

### Exercise 22 — @Query Sort

Write `@Query(sort="{ 'createdAt': -1 }")`. When the method also accepts a dynamic `Sort` ascending on the same property, what happens?

**Answer:** Dynamic `Sort` can override the annotation's default sort per documentation.

### Exercise 23 — Count Projection

Contrast `@Query(count = true) long count...` with `repository.find...().size()`.

### Exercise 24 — Exists Projection

Contrast `@Query(exists = true)` with `@Query(count = true)`.

### Exercise 25 — Delete Safety

Write a `@Query(delete = true)` that deletes only inactive documents for a specific tenant; propose audit and authorization checks.

### Exercise 26 — Update

Use `@Query` as the filter and `@Update` to set an order's `status` by tenant + ID. Why check the matched/modified count?

### Exercise 27 — $elemMatch

A `lineItems` array holds `sku` and `quantity`. Why can't you use two independent dot-notation conditions if a single item must satisfy both?

### Exercise 28 — Regex

Compare `StartingWith`, `Containing`, and `Regex`. Which one can use a B-tree index better? What are the risks of user-supplied regexes?

### Exercise 29 — Index

Consider `findByTenantIdAndStatusOrderByCreatedAtDesc`. Design a matching compound index and compare `explain("executionStats")`.

### Exercise 30 — @CompoundIndex

Why does placing `@CompoundIndex` on an entity not guarantee the index exists in production?

**Answer:** Auto-index creation is off by default; migrations/provisioning or explicit configuration are required.

### Exercise 31 — Null and Missing

If business logic needs to check for documents where a field exists and equals `null`, what operator is needed beyond `{field: null}`?

### Exercise 32 — Optional and Uniqueness

When querying by `orderNumber` while the database contains two duplicate documents, does `Optional<Order>` guarantee picking one arbitrarily?

**Answer:** No; a single-result query can throw an error on multiple matches. A unique index is the right fix.

### Exercise 33 — Transactions

A service creates an order and writes an audit event in another collection. Do two `MongoRepository.save` calls automatically form an atomic multi-document transaction?

**Answer:** No. You need a transaction/session on a supporting deployment if atomicity is required.

### Exercise 34 — Integration Test

Write a `@DataMongoTest` with seeded data verifying that a derived method and `@Query` return the same orders. Why doesn't a mocked repository prove the JSON query is valid?

### Exercise 35 — Tenant Isolation

Design tests proving a request from tenant A cannot read or delete `O-104` belonging to tenant B—including via `OR`, `Pageable`, and `delete` methods.

### Exercise 36 — When to Use MongoTemplate?

For a search page with 12 optional filters, grouped `OR` clauses, and variable sorts and projections, should you write a massive derived method name or use `Criteria`/`MongoTemplate`? Explain.

### Exercise 37 — Performance

A derived method and a `@Query` emit the exact same filter, index, and sort. Is there any reason `@Query` is guaranteed to be faster?

**Answer:** No. Measure the execution plan and real workload.

### Exercise 38 — Comparing Page and Slice

A listing page has 1 million orders and the UI only shows a "More" button. Explain the cost of the count query and how to avoid it.

### Exercise 39 — Date / Decimal128

Why must `BigDecimal`/`Date` mappings stay consistent with stored BSON types? Use `$type` to inspect the lab data.

### Exercise 40 — Capstone Exercise

Design the repository layer for the endpoint:

```text
GET /orders?status=PAID&minAmount=100&page=0&size=20
```

Requirements: derive tenant from the authenticated principal, cap page size, enforce stable sorting, project only needed fields, design a matching index, and test multi-tenancy and p95 latency. Choose between derived queries and `@Query` and justify your choice.

---

## 34. Production Readiness Checklist for Repositories

### Correctness and Data Access

- [ ] `@Document`/`@Id`/`@Field` mappings align with the BSON schema.
- [ ] Derived method names match Java properties accurately.
- [ ] Nested paths are explicit with no ambiguity.
- [ ] `@Query` uses zero-based parameter binding correctly.
- [ ] `@Query` JSON filters and projections are verified.
- [ ] Null vs. missing field semantics match business requirements.
- [ ] `Optional` is only used when uniqueness or result limits are guaranteed.
- [ ] Tenant filters apply across all `OR` branches and all delete operations.
- [ ] Uniqueness relies on unique indexes, not `exists` prechecks alone.
- [ ] Clients cannot inject arbitrary sort fields or filter operators.

### Performance

- [ ] No unbounded `findAll()` exposed on public APIs.
- [ ] `Page` vs. `Slice` chosen to fit UX needs.
- [ ] Page size has an enforced upper bound.
- [ ] Sorting includes a unique tie-breaker.
- [ ] Deep pagination uses keyset/scroll strategies.
- [ ] Compound indexes align with filters and sorts without bloat.
- [ ] `explain`/profiler metrics reviewed: `docs`/`keys` examined and `nReturned`.
- [ ] Projections exclude unnecessary large payloads.
- [ ] Impact of regex and `IgnoreCase` on indexes evaluated.
- [ ] `Page` count query cost monitored.

### Security and Operations

- [ ] URI, TLS, and credentials managed via a secrets manager.
- [ ] Repository methods never bypass authorization checks.
- [ ] Query literals containing PII are never logged.
- [ ] Updates and deletes have proper auditing and approvals.
- [ ] Partial entities loaded via projections are never passed to `save`.
- [ ] Optimistic locking and transaction strategies are tested.
- [ ] Dependency BOM and Spring Data versions are compatible.
- [ ] Testcontainers/integration tests run against real MongoDB in CI.
- [ ] Load tests and rollback plans exist for query/index changes.

---

## 35. Summary

**`MongoRepository`** lets Spring applications access MongoDB through a clean interface, provided you understand every layer underneath:

1. **CRUD repositories** provide `save`, `insert`, `findById`, `existsById`, `count`, and `deleteById`.
2. **Derived query methods** parse Java property names and keywords like `And`, `Or`, `GreaterThan`, `In`, `IsNull`, `IgnoreCase`, `OrderBy`, and `Top` into filters and sorts.
3. **`@Query`** lets you declare MongoDB JSON with `?0`/`?1` parameters, `fields` projections, `sort`, `collation`, `hint`, and `count`/`exists`/`delete` flags.
4. **Neither derived queries nor `@Query` are inherently faster** if MongoDB executes the same query plan. Indexes, selectivity, pagination, projections, and server resources govern performance.
5. **`Page` differs from `Slice`**: `Page` computes total counts, while `Slice` suits UIs that only need to know whether a next page exists.
6. **Projections reduce payload size**, but are never an access control boundary, and partial entities must never be passed back to `save`.
7. **Multi-tenancy, uniqueness, and transactions** must be enforced at the service and database layers—they do not come free with repository abstractions.
8. For complex queries, prefer `@Query`, `MongoTemplate`, or `@Aggregation` over excessively long method names.
9. **Integration tests on real MongoDB** are essential to validate query derivation, mapping, indexes, and runtime semantics.

The key lesson: **use repositories to keep application code clean, while always understanding the actual MongoDB query generated underneath**.

### Official References

- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived methods, `@Query`, fields, sort, SpEL, `@Meta`.
- [Spring Data — Defining Query Methods](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html) — lookup strategies, property traversal, reserved methods, paging/sorting.
- [Spring Data — Repository Query Keywords](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-keywords-reference.html) — supported prefixes and predicate modifiers.
- [Spring Data MongoDB — MongoRepository API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/MongoRepository.html) — methods and inherited interfaces.
- [Spring Data MongoDB — @Query Annotation](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/repository/Query.html) — count/exists/delete/fields/sort/collation/hint.
- [Spring Data MongoDB — Modifying Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/modifying-methods.html) — `@Update` and derived deletions.
- [Spring Data — Projections](https://docs.spring.io/spring-data/mongodb/reference/repositories/projections.html) — closed/open, DTO, and dynamic projections.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `@Document`, `@Id`, `@Field`, indexes.
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html) — auto-index defaults and management.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `MongoTemplate`/`Criteria`.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — pipelines and aggregation alternatives.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — sessions and transaction managers.
- [Spring Boot — Data MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — Boot MongoDB integration.
- [Spring Boot — Auto-configured Data MongoDB Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@DataMongoTest` and testing support.
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `IXSCAN`/`COLLSCAN` and execution stats.
