# Choosing Between MongoRepository, MongoTemplate, or the Direct Driver

## 1. The problem to solve

When building a Java application with **Spring Data MongoDB**, there are three common ways to interact with MongoDB:

- **`MongoRepository`**: expresses data operations through a repository interface bound to a domain object type.
- **`MongoTemplate`** (via `MongoOperations`): writes queries and data operations using the Spring Data MongoDB API, supporting dynamic queries, partial document updates, aggregation, and many advanced operations.
- **Direct MongoDB Java Driver**: works directly with `MongoClient`, `MongoDatabase`, `MongoCollection`, BSON `Document`, and driver APIs, managing most data access details explicitly.

These three choices are **not three different databases**. They all access MongoDB, differing in level of abstraction, data representation, code maintenance effort, and operational control.

The goal of this lesson is to know how to **choose the right tool for each operation**, recognize when to drop to a lower level, and avoid simplistic rules of thumb such as "the direct driver is always faster." Examples use Spring Boot, synchronous (*imperative*) Spring Data MongoDB, and the MongoDB Java Sync Driver.

## 2. Comparing the options

| Criterion | MongoRepository | MongoTemplate | Direct Driver |
|---|---|---|---|
| Primary coding style | Declare an interface and methods | Call Spring Data query/update APIs | Call MongoDB Java Driver APIs |
| Result objects | Typically entities, projections, DTOs | Spring Data–mapped entities/DTOs; can operate lower-level | BSON `Document` or POJOs with custom codec setup |
| Common queries | Derived queries, `@Query`, `@Aggregation`, pagination | `Query`, `Criteria`, `Aggregation`, `Update` | `Filters`, `Aggregates`, `Updates`, BSON pipelines |
| Input-driven dynamic queries | Possible, though simple method names become hard to maintain | Very well suited | Possible; requires managing more details manually |
| Partial updates, bulk, specialized ops | Extensible via repository fragments or suitable repository features | Direct, flexible API | Low-level driver API control |
| Spring Data `@Document`, `@Field`, converter mapping | Yes | Yes, when operating through Spring Data's mapping layer | Does not automatically apply those annotations or converters |
| Typical maintenance cost | Low for entity-centric queries | Moderate; requires clean data-access layer design | Higher due to manual handling of BSON, collection structure, and conventions |
| When to prefer | CRUD and routine domain-model queries | Dynamic queries, conditional updates, aggregation, bulk writes | Driver-specific features or low-level operations not well covered by Spring Data |

Note: **`MongoRepository` is not limited to basic CRUD**. Repositories support `@Query`, aggregations, projections, and custom methods. Likewise, **`MongoTemplate` does not bypass Spring Data mapping**; it can read and write the exact same entities as repositories. Higher abstraction does not automatically mean lower performance: measure queries, indexes, network traffic, and conversion overhead in real context.

## 3. Decision workflow

~~~mermaid
flowchart TD
    A["Need a MongoDB data operation"] --> B{"Mostly CRUD and stable entity queries?"}
    B -->|"Yes"| C["Prefer MongoRepository"]
    B -->|"No"| D{"Need dynamic queries, aggregation, conditional updates, or bulk?"}
    D -->|"Yes"| E["Prefer MongoTemplate"]
    D -->|"No"| F{"Need specific driver APIs or explicit BSON/session control?"}
    F -->|"Yes"| G["Use direct driver, isolated in a dedicated adapter"]
    F -->|"No"| H["Re-evaluate requirements; start with the simplest API that fits"]
    C --> I["Measure and inspect real queries/indexes"]
    E --> I
    G --> I
    H --> I
~~~

You can follow a short checklist:

1. **Identify the use case and output type**: are you working with entities, aggregated reports, or raw BSON?
2. **Classify the query pattern**: fixed criteria, dynamically built filters, multi-field updates, aggregation pipelines, or driver-specific commands?
3. **Pick the API that keeps code clearest**: repository for routine queries, template for application-controlled complex operations, driver for genuine driver-tier requirements.
4. **Verify with data and metrics**: indexes, `explain`, documents examined, query latency, network round trips, and maintenance cost.

You do not have to pick one API for an entire service. One module can use a repository for standard operations, a template for a complex report, and the driver inside an isolated adapter. What matters is keeping responsibility boundaries clear.

## 4. Shared example: querying orders

Suppose the `orders` collection stores documents with `customerId`, `status`, `totalCents`, and `createdAt`. A feature needs the **20 most recent PAID orders for a customer**.

In a Spring Boot application with `spring-boot-starter-data-mongodb`, a development connection can be configured as:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/shop
~~~

In production environments, supply the URI and credentials from a proper secrets/configuration mechanism—never hardcode passwords in source code.

Shared entity definition used by the repository and template examples:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {
    @Id
    private String id;
    private String customerId;
    private String status;
    private long totalCents;
    private Instant createdAt;

    public Order() {}

    public Order(String customerId, String status, long totalCents, Instant createdAt) {
        this.customerId = customerId;
        this.status = status;
        this.totalCents = totalCents;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public long getTotalCents() { return totalCents; }
    public void setTotalCents(long totalCents) { this.totalCents = totalCents; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
~~~

Spring Data MongoDB uses mapping metadata to bind the entity to documents. The `@Id` field corresponds to `_id` in MongoDB; in appropriate cases, Spring Data can convert between `String` and `ObjectId`. For fields requiring a specific BSON type, define the mapping strategy explicitly.

### 4.1. MongoRepository: when queries map tightly to entities

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
    List<Order> findTop20ByCustomerIdAndStatusOrderByCreatedAtDesc(
            String customerId, String status);
}
~~~

~~~java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final OrderRepository orders;

    public OrderLookupService(OrderRepository orders) {
        this.orders = orders;
    }

    public List<Order> latestPaidOrders(String customerId) {
        return orders.findTop20ByCustomerIdAndStatusOrderByCreatedAtDesc(
                customerId, "PAID");
    }
}
~~~

Spring Data parses the method name to build the filter, descending sort on `createdAt`, and limit of 20 results. For `save`, `findById`, `deleteById`, and routine queries, service-layer code stays concise and easy to test.

Repositories can also express queries with annotations:

~~~java
import java.util.List;
import org.springframework.data.mongodb.repository.Query;

public interface OrderSearchRepository extends MongoRepository<Order, String> {
    @Query("{ 'status': ?0, 'totalCents': { $gte: ?1 } }")
    List<Order> findByStatusWithMinimumTotal(String status, long minimumCents);
}
~~~

Avoid stretching method names indefinitely when filters have many optional combinations. When assembling criteria dynamically from inputs, building a single query with `MongoTemplate` is usually much clearer. If you want to keep a unified repository API for callers, create a **custom repository fragment** and implement the complex query inside that fragment.

### 4.2. MongoTemplate: when you need explicit query construction

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderTemplateLookup {
    private final MongoTemplate template;

    public OrderTemplateLookup(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> latestPaidOrders(String customerId) {
        Query query = new Query(
                Criteria.where("customerId").is(customerId)
                        .and("status").is("PAID"));
        query.with(Sort.by(Sort.Direction.DESC, "createdAt"));
        query.limit(20);
        return template.find(query, Order.class);
    }
}
~~~

The result is still `List<Order>`, converted via Spring Data's mapping metadata and converters. The difference is that code constructs `Query` explicitly, which is convenient when the number of criteria depends on runtime input.

Dynamic query example:

~~~java
public List<Order> search(String customerId, String optionalStatus, Long minimumCents) {
    Criteria criteria = Criteria.where("customerId").is(customerId);
    if (optionalStatus != null && !optionalStatus.isBlank()) {
        criteria = criteria.and("status").is(optionalStatus);
    }
    if (minimumCents != null) {
        criteria = criteria.and("totalCents").gte(minimumCents);
    }

    return template.find(new Query(criteria).limit(100), Order.class);
}
~~~

The snippet above is an additional method inside a class that already holds `template`. The limit of 100 prevents unbounded queries in the example; real data requires pagination, a hard maximum limit, and a deterministic sort order.

**Atomic conditional updates** are another strong fit for `MongoTemplate`. For example, transition an order from `NEW` to `PAID` only if its current status matches expectations:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

public boolean markPaidIfNew(String orderId) {
    Query query = new Query(
            Criteria.where("id").is(orderId).and("status").is("NEW"));
    Update update = new Update().set("status", "PAID");

    UpdateResult result = template.updateFirst(query, update, Order.class);
    return result.getModifiedCount() == 1;
}
~~~

Here, the update executes on the server against a matching document, avoiding the read–modify–`save` pattern without concurrency protection. The `id` field in `Query` is mapped to `_id` using `Order`'s metadata. For more complex workflows, also design version checks, idempotency, and error handling.

Beyond `find` and `updateFirst`, `MongoTemplate` supports `findAndModify`, `updateMulti`, `bulkOps`, and aggregations via `Aggregation`. This is a major advantage whenever an operation cannot be expressed cleanly as a repository method name.

### 4.3. MongoDB Java Driver: when low-level control is required

The MongoDB Java Sync Driver works directly with BSON and MongoDB APIs. Example performing the same query while returning `Document` objects:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.springframework.stereotype.Service;

@Service
public class RawOrderLookup {
    private final MongoCollection<Document> collection;

    public RawOrderLookup(MongoClient client) {
        // Matches the database and collection names configured for the examples.
        this.collection = client.getDatabase("shop").getCollection("orders");
    }

    public List<Document> latestPaidOrders(String customerId) {
        return collection.find(and(
                    eq("customerId", customerId),
                    eq("status", "PAID")))
                .sort(descending("createdAt"))
                .limit(20)
                .into(new ArrayList<>());
    }
}
~~~

This is the **synchronous** driver. In a standard Spring Boot application, inject the container-managed `MongoClient` instead of creating a new client per request. This example only reads BSON documents; if you want `Order` instances, you must apply your own conversion—such as configuring a POJO codec or an application-defined mapper.

The direct driver makes sense when you need a specific driver API, BSON option, or command feature not conveniently wrapped by the current abstraction, or when measurements prove a low-level path is beneficial. In return, your code must manage actual MongoDB field names, BSON types, sessions, errors, and payload consistency itself.

**Never assume the direct driver is automatically faster.** With the same command sent to the server and the same indexes, most latency typically comes from MongoDB scanning, sorting, or transferring documents. Measure latency before switching APIs.

## 5. How can the three options work together?

Suppose an e-commerce system has the following requirements:

| Requirement | Reasonable Starting API | Rationale |
|---|---|---|
Creating orders, looking up by ID, listing by customer | `MongoRepository` | Tied directly to the entity with stable query contracts |
Searching orders by optional UI filters | `MongoTemplate` | Composes `Criteria` from parameters without declaring combinatorial methods |
Conditional status transitions, bulk updates | `MongoTemplate` | Expresses `Update`, bulk ops, and affected document counts cleanly |
Multi-stage summary reports | `MongoTemplate` with `Aggregation`; or `@Aggregation` when the pipeline is fixed | Keeps pipelines maintainable in code |
Highly specialized driver operation lacking a Spring Data API | Direct driver | Exact control over driver APIs and BSON options |

Within one application, the first two options normally share the same `MongoDatabaseFactory` and Spring Data mapping layer. Put data access inside repository/adapter classes with clear boundaries so business services do not care whether `MongoTemplate` or the driver is used underneath.

If mixing the direct driver with repositories or templates, avoid these integration pitfalls:

- **Wrong collection or field names**: `@Document(collection = "orders")` and `@Field` are only processed along Spring Data's mapping path. The driver uses raw collection and BSON field names.
- **Type mismatches**: `_id` may be stored as `ObjectId` rather than a BSON String; timestamps, decimals, and enums also need consistent mapping rules.
- **Skipped lifecycle hooks**: calling the driver directly bypasses Spring Data entity callbacks, auditing, and custom converters.
- **Session/transaction mismatch**: a direct driver call must not be assumed to automatically join a Spring Data–managed session/transaction. When combining them, pass/manage the `ClientSession` explicitly or keep operations inside a transaction-managed abstraction.
- **Execution model mismatch**: sync APIs block threads; if the application is end-to-end WebFlux/reactive, use `ReactiveMongoRepository`, `ReactiveMongoTemplate`, and the Reactive Streams Driver instead of calling the sync driver inside reactive pipelines.

## 6. Factors that matter more than API choice

### 6.1. Designing indexes around real queries

The example query filters by `customerId` and `status`, then sorts descending by `createdAt`. A candidate compound index is:

~~~javascript
db.orders.createIndex({ customerId: 1, status: 1, createdAt: -1 });
~~~

This is a **candidate** index for the example query, not a blanket recommendation for every collection. Evaluate read/write ratios, selectivity, storage overhead, and execution plans. Annotations like `@Indexed` or `@CompoundIndex` on entities do not guarantee automatic index creation in every environment: index deployment depends on configuration and the project's migration/index management policy.

### 6.2. Observing queries and pagination

Inspect MongoDB's `explain` output in an appropriate environment:

~~~javascript
db.orders.find({ customerId: "c01", status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and documents returned. At large data volumes, deep `skip` pagination becomes expensive; consider sort-value-based pagination (*keyset/cursor pagination*) with a deterministic sort order and matching index. Repository `Page<T>` may issue a total count query; if total count is unnecessary, prefer `Slice<T>` or bounded limits.

### 6.3. Atomicity and transactions

Updating **a single document** executes atomically at the document level and is often sufficient for many workflows. Multi-document transactions are a separate topic: MongoDB transactions require a supporting topology (e.g., replica set or sharded cluster), sessions, and a properly configured transaction manager. Do not expect `@Transactional` to pull arbitrary direct driver calls into the same transaction automatically.

### 6.4. Testing

- For repositories: verify method-derived queries, entity mapping, sorting, and limits against a real MongoDB instance.
- For templates: test optional filter branches, conditional updates, and aggregation results—especially cases where zero documents match.
- For the direct driver: test BSON types, manual mapping, session propagation, and compatibility across MongoDB/driver versions.

`@DataMongoTest` helps create a focused Spring Data MongoDB test slice. Testcontainers with MongoDB is ideal for integration tests requiring real database behavior; configure a replica set when testing transactions. Unit tests mocking a `Query` call do not replace real query and index verification.

## 7. Common mistakes and how to avoid them

| Claim or Practice | Issue | Better Approach |
|---|---|---|
"Repositories are only for CRUD" | Ignores `@Query`, `@Aggregation`, projections, and custom fragments | Prefer repository APIs whenever queries remain clear |
"Template doesn't support entity mapping" | Misunderstands Spring Data | Use `find(query, Order.class)` and proper mapping metadata |
"Direct driver is always fastest" | Ignores query plans, indexes, network, and real data | Measure with profiling, `explain`, and fair benchmarks |
"Everything should use the driver directly" | Duplicates mapping, validation, and error handling everywhere | Isolate driver usage in adapters and standardize return models |
"Switching APIs fixes a slow query" | Query still lacks an index or scans too many documents | Tune queries/indexes and inspect execution plans |
"Repositories and templates can't be mixed" | Creates artificial architectural barriers | Share domain models with clean data-access boundaries |
"Driver calls inside `@Transactional` join automatically" | May execute outside the managed session | Define explicit session/transaction boundaries per API |

## 8. Practice exercises

**Scenario A.** A profile management app needs to save, edit, delete profiles, and look them up by email. Choose `MongoRepository` as the default, add a query method, and verify the email index (unique if business rules require it).

**Scenario B.** An admin screen filters orders by multiple optional parameters: customer, status, amount range, and start/end dates. Build a `Query` with `Criteria` in `MongoTemplate`, supporting sorting and result limits. Test at least three cases: no optional filters, one filter, and multiple filters.

**Scenario C.** A feature needs a newer MongoDB option that the current Spring Data version does not wrap conveniently. Verify driver compatibility, encapsulate the call in a dedicated adapter, keep output types stable, and test actual behavior.

**Scenario D.** A repository query takes several seconds. Before rewriting with the direct driver, inspect the execution plan, indexes, examined documents, sort behavior, payload size, and query count. Only change APIs when there is a functional need or measured benefit.

## 9. Key takeaways

**`MongoRepository`** is the right starting point for CRUD and well-defined entity queries. **`MongoTemplate`** fits when queries or updates must be assembled and controlled programmatically. The **direct MongoDB Java Driver** is reserved for specific low-level needs requiring full control over driver APIs and BSON. All three can coexist in one system when mapping, indexes, transactions, and data-access boundaries are managed consistently. Correctness, maintainability, and measurements on real workloads are the deciding criteria.
