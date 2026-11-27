# ReactiveMongoTemplate, Reactive Repositories, and Avoiding Blocking Threads

A WebFlux API receiving hundreds of concurrent requests can perform smoothly with **a small number of event-loop threads** if the entire I/O chain is truly **non-blocking**. Yet it only takes one service calling `MongoTemplate.find(...)` or `Mono.block()` directly on an event loop to stall other requests sharing that worker significantly. Changing a controller return signature from `Order` to `Mono<Order>` **does not automatically make the logic inside reactive**.

This lesson, **"ReactiveMongoTemplate, Reactive Repositories, and Avoiding Blocking Threads"**, in the **Spring Data MongoDB** chapter of the *Database Engine Document MongoDB* module, shows how to build applications querying MongoDB with **Reactive Streams / Project Reactor** from controller to database. The two primary APIs covered are:

- **`ReactiveMongoTemplate`**: controls queries, updates, aggregations, streaming, and specialized operations through Spring Data APIs returning `Mono<T>` / `Flux<T>`.
- **`ReactiveMongoRepository<T, ID>`**: declares CRUD/query methods aligned with the domain model so Spring Data generates reactive implementations.

The core focus extends beyond CRUD syntax to the **requirement to avoid blocking**: distinguishing async from blocking, understanding subscriptions and backpressure, bounding concurrency, integrating legacy libraries, handling transactions, timeouts/cancellation, testing, and performance monitoring.

> **Version note:** Examples target **Spring Boot 3.x/4.x, Spring Data MongoDB 4.x/5.x, and Reactor 3.x** with a compatible MongoDB Java Reactive Streams Driver provided via dependency management. Specific packages, builders, repository APIs, and configuration properties evolve across releases. Follow your running Spring Boot BOM rather than mixing Spring Data 5.x with incompatible driver or Spring Framework versions. All URIs, collections, timeouts, and concurrency values in this lesson are illustrative lab figures.

## 1. Learning Outcomes

After completing this lesson, you will be able to:

1. Explain **Reactive Streams Publisher/Subscriber/Subscription**, laziness, demand signaling, cancellation, and non-blocking I/O.
2. Distinguish `MongoTemplate`/`MongoRepository` (imperative) from `ReactiveMongoTemplate`/`ReactiveMongoRepository` (reactive).
3. Configure `spring-boot-starter-data-mongodb-reactive` and WebFlux, defining `@Document`/`@Id`/`@Indexed` domain classes.
4. Write CRUD, queries, updates, and aggregations using `ReactiveMongoTemplate` and derived/annotated methods in reactive repositories.
5. Build controllers accepting/returning `Mono`/`Flux` and propagating errors, empty results, not-found states, and validation cleanly.
6. Identify anti-patterns such as **`block()`, `blockFirst()`, `toIterable()`, `Thread.sleep()`, JDBC, and blocking HTTP clients** inside an event-loop chain.
7. Use `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` when forced to wrap legacy blocking calls, while bounding concurrent tasks.
8. Control `flatMap` concurrency, `buffer`/`collectList`, pagination, batch sizes, and downstream backpressure.
9. Understand `ReactiveMongoTransactionManager`/`TransactionalOperator`, Reactor Context, and session boundaries.
10. Test publishers with `StepVerifier`, WebFlux endpoints with `WebTestClient`, monitor latency/cancellation/connection pools, and plan deployment rollbacks.

## 2. Why Reactive? Thread and I/O Models

### 2.1. Imperative Blocking Model

~~~text
HTTP request A
   |
   v
Servlet thread #1
   |
   v
MongoTemplate.findOne() -----> MongoDB
   |    (thread #1 WAITING for response)
   |
   v
HTTP response A
~~~

When a Java thread waits on a blocking socket read, it continues holding a worker slot and thread stack, forcing the service to allocate many threads to handle high request concurrency.

### 2.2. Reactive Non-Blocking Model

~~~text
HTTP request A          HTTP request B
      |                       |
      +------ event loop -----+
                 |
                 v
          WebFlux Controller
                 |
                 v
         Mono/Flux pipeline
                 |
                 v
      Reactive MongoDB Driver
                 |
            async network I/O
                 |
             (no event-loop
              thread blocked)
                 |
                 v
          signal onNext/onComplete
                 |
                 v
          HTTP response stream
~~~

While MongoDB has not yet responded, the event loop can continue serving other connections. Once data arrives, the reactive publisher emits **signals** to advance the pipeline.

**Reactive does not make MongoDB itself faster** or reduce a query's CPU or index cost. Its primary role is **avoiding tying up a Java thread waiting on every socket operation**, paired with backpressure and composition to manage data flow.

### 2.3. Non-Blocking vs Parallel

- **Non-blocking:** threads are not held idle waiting for I/O; it does not necessarily mean multiple operations run in parallel.
- **Concurrency:** multiple operations are in flight or awaiting responses during the same window.
- **Parallelism:** executing work simultaneously across multiple CPU cores/threads.
- **Asynchronous:** results arrive later; if an async wrapper calls blocking JDBC on an event loop, the chain still blocks.

A `Flux` can execute operations sequentially via `concatMap` or concurrently via `flatMap`. Choose based on ordering dependencies and capacity—never enable unbounded concurrency simply because a pipeline is "reactive".

### 2.4. When Does Reactive Actually Deliver Value?

| Scenario | Potential Benefit | Trade-offs to Evaluate |
|---|---|---|
| I/O-heavy HTTP APIs with high concurrency | Fewer blocked threads, better I/O efficiency. | Must maintain a fully non-blocking chain. |
| Streaming queries returning many records | `Flux` supports demand and cancellation, reducing full buffering. | DB cursors, HTTP serializers, memory, and timeouts still bound capacity. |
| Services calling MongoDB plus multiple HTTP APIs | Natural reactive composition. | All downstream clients should be non-blocking. |
| Long-lived change streams | Signal-driven subscribe/cancel processing. | Resume tokens, retries, lifecycle, retention. |
| CPU-bound aggregation inside the app | Does not shrink CPU work automatically. | Scheduling must be isolated and bounded. |
| Small MVC app adequately served by blocking stack | Reactive may yield no net gain. | No obligation to migrate just because it is "newer". |
| Systems tightly coupled to JDBC/blocking SDKs | Requires thread isolation or staying imperative. | Reactive wrappers do not erase blocking work. |

### 2.5. Reactive Does Not Replace Database Optimization

If a MongoDB query performs a `COLLSCAN` across 10 million documents due to a missing index, switching from `MongoTemplate` to `ReactiveMongoTemplate` fixes nothing. You still need:

- `explain("executionStats")` and proper indexes.
- Projections and bounded limits.
- Shard-key filters when sharded.
- Elimination of N+1 queries, appropriate batching, and policy-backed caching.
- Server-side CPU, IOPS, cache, and connection pool monitoring.

## 3. Reactive Streams and Reactor: Essential Concepts

### 3.1. Publisher, Subscriber, Subscription

Under Reactive Streams:

- **Publisher** emits data and signals once subscribed to.
- **Subscriber** receives `onSubscribe`, `onNext`, `onError`, and `onComplete`.
- **Subscription** lets the subscriber send `request(n)` (demand) and `cancel()`.
- Publishers emit elements only within valid demand and follow strict terminal signal semantics.

~~~text
Subscriber                  Publisher
    |---- subscribe --------->|
    |<--- onSubscribe --------|
    |---- request(2) -------->|
    |<--- onNext(value1) -----|
    |<--- onNext(value2) -----|
    |---- request(1) -------->|
    |<--- onNext(value3) -----|
    |<--- onComplete ---------|
~~~

In practice, Reactor operators employ **prefetching, buffering, and operator fusion**, so upstream request counts may differ from downstream HTTP demand. Do not interpret this diagram as a guarantee that MongoDB always fetches **exactly n documents per socket round trip**.

### 3.2. Mono and Flux

| Type | Max `onNext` Signals | Used For |
|---|---:|---|
| `Mono<T>` | 0 or 1 | `findById`, `save`, `count`, `exists`, delete/update results. |
| `Mono<Void>` | 0 | Workflows signaling only completion or error. |
| `Flux<T>` | 0 to N | `findAll`, search results, aggregation rows, change streams. |

**Empty is not automatically an error**: `repository.findById("missing")` normally returns `Mono.empty()`. The controller must translate empty into HTTP 404 rather than expecting `null` to represent "not found".

### 3.3. Lazy Pipelines: Assembly Is Not Execution

~~~java
Mono<Order> workflow = repository.save(order);

// Only builds a Publisher; no downstream subscription yet.
~~~

When a WebFlux controller **returns** `Mono<Order>`, the framework subscribes to execute and emit the response. In standalone batch jobs, an explicit lifecycle owner must manage subscriptions.

### 3.4. Each Subscription Can Re-Trigger I/O

~~~java
Mono<Order> lookup = repository.findById("O-100");

// Two subscriptions can trigger two separate DB reads.
lookup.subscribe();
lookup.subscribe();
~~~

Do not treat a reactive publisher like an already-running `CompletableFuture` caching one result. Repository and template publishers are typically **cold**; subscribing multiple times re-executes the operation. This is especially hazardous for **writes** if `subscribe()` is invoked repeatedly:

~~~java
Mono<Order> saveOncePerSubscription = repository.save(order);
~~~

`saveOncePerSubscription` does **not** give `save` system-wide "exactly-once" semantics. Keep business idempotency keys and never retry writes blindly.

### 3.5. Three Signal Outcomes: Data, Error, Completion

~~~text
Mono.just(value):        onNext(value), onComplete
Mono.empty():            onComplete
Mono.error(exception):   onError(exception)
Flux.just(a,b):          onNext(a), onNext(b), onComplete
~~~

Once `onError` or `onComplete` fires, the subscription ends. Operators like `onErrorResume` switch errors to a fallback Publisher; avoid unintentionally swallowing errors.

### 3.6. `map`, `flatMap`, `then`, and `switchIfEmpty`

~~~java
Mono<OrderDto> result = repository.findById("O-100")
    .map(OrderDto::fromEntity)
    .switchIfEmpty(Mono.error(
        new OrderNotFoundException("O-100")));
~~~

- `map`: performs a **synchronous/fast** transformation returning a plain value without spawning a publisher.
- `flatMap`: chains an operation **returning a Mono/Publisher**, such as a follow-up DB call.
- `then`: waits for upstream completion, **discards upstream values**, and continues to the next task.
- `switchIfEmpty`: substitutes when a publisher finishes **empty** (does not handle errors).

**Specifically:** `map(order -> repository.save(order))` produces `Mono<Mono<Order>>` without flattening; you almost always want `flatMap(order -> repository.save(order))`.

### 3.7. `defer` to Compute Actions at Subscription Time

~~~java
Mono<Instant> nowAtSubscribe =
    Mono.defer(() -> Mono.just(Instant.now()));
~~~

`Mono.just(Instant.now())` evaluates the timestamp during **pipeline assembly**; `defer` postpones publisher construction and side effects until subscription. This helps capture request context, fresh timestamps, or per-subscription resources at the right moment—though it does not replace `ReactiveMongoTemplate` or start transactions.

### 3.8. `subscribe()` Is Not a "Free Background Execution Command"

Calling `subscribe()` inside a service and immediately returning `Mono.just("OK")` can send an HTTP success response **before the DB write finishes**; write errors never reach the caller, and cancellation/transaction boundaries disconnect. On request paths, **return the composed pipeline** instead of manually subscribing.

## 4. Spring Boot Dependencies and Configuration

### 4.1. Gradle Dependencies

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Tokens `<boot-version>` and `<compatible-version>` are placeholders chosen from your project's BOM/Gradle setup, not a ready-to-run build file. When using the Spring Boot plugin's BOM management, adhere to its managed versions instead of manually mixing dependencies. This guide **does not execute Gradle**; these snippets illustrate project setup.

### 4.2. Maven Dependencies

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
  </dependency>
  <dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Let the Spring Boot BOM/parent manage versions. **Do not add the imperative starter `spring-boot-starter-data-mongodb`** if you only want reactive data access; having both starters on the classpath complicates auto-configuration and bean selection.

### 4.3. MongoDB URI

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

In real deployments, URIs injected from a secret manager or environment variable may look like:

~~~text
mongodb+srv://<user>:<password>@cluster.example.mongodb.net/shop
~~~

Never commit real credentials to repositories. For local replica sets, ensure the URI configures the proper replicaSet/topology and reachable hostnames; avoid slapping `directConnection=true` on just to mask HA topology errors.

### 4.4. Boot Auto-Configuration

With the reactive MongoDB starter and valid properties, Spring Boot typically auto-configures a reactive Mongo client/database factory, `ReactiveMongoTemplate`, and reactive repository scanning. Use **explicit configuration** whenever an app connects to multiple MongoDB databases/clients, spans profiles, or combines imperative and reactive stacks.

### 4.5. Manual Configuration When Needed

~~~java
@Configuration
@EnableReactiveMongoRepositories(basePackages = "com.example.orders")
class ReactiveMongoConfig {
    // Let Boot auto-configure MongoClient and ReactiveMongoTemplate,
    // or declare custom beans with ReactiveMongoDatabaseFactory
    // when multiple databases/clients are genuinely required.
}
~~~

**Do not** declare a custom `@Bean ReactiveMongoTemplate` while assuming auto-configuration automatically wires every repository and transaction manager identically. Verify the resulting bean graph with integration tests.

### 4.6. Reactive Java Driver vs Sync Java Driver

Reactive Spring Data MongoDB builds on the **MongoDB Reactive Streams driver**, not the Java Sync driver's `MongoClient` wrapped inside `Mono.fromCallable`. The reactive driver enables non-blocking MongoDB I/O throughout the pipeline. A DAO using blocking `MongoTemplate` wrapped in `Mono.just(...)` **still blocks the thread**.

## 5. Domain Model and Mapping Rules

Let's model a simple order system:

~~~json
{
  "_id": "ORD-1001",
  "tenantId": "tenant-a",
  "customerId": "C-100",
  "status": "OPEN",
  "amountMinor": 250000,
  "createdAt": "2026-11-14T00:00:00Z",
  "version": 0
}
~~~

Store integer minor units (`amountMinor`) to avoid floating-point rounding errors in monetary math. In real MongoDB, `createdAt` is a BSON Date—the JSON above is illustrative; Spring Data's `@Version` manages optimistic locking.

### 5.1. Entity

~~~java
package com.example.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
    name = "tenant_status_created_id",
    def = "{'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': 1}")
public class Order {
    @Id
    private String id;
    private String tenantId;
    private String customerId;
    private String status;
    private long amountMinor;
    private Instant createdAt;
    @Version
    private Long version;

    // Getters/setters or constructor suitable for Spring Data mapping.
}
~~~

The snippet omits boilerplate getters/setters; in real projects provide full constructors/accessors or immutable mapping matching your Spring Data version. Declaring `@CompoundIndex` **does not mean the index exists in production**: modern Spring Data MongoDB leaves auto-index creation off by default and production typically manages indexes explicitly via migrations.

### 5.2. Why Indexes Still Matter in Reactive Stacks

For the query:

~~~text
tenantId = "tenant-a"
status = "OPEN"
sort createdAt descending
limit 20
~~~

an index such as `{tenantId:1,status:1,createdAt:-1,_id:1}` supports filtering and sorting depending on query shape and cardinality. The reactive driver cannot turn a `COLLSCAN` into an `IXSCAN`. Under heavy traffic, slow queries pile up **in-flight operations** and connection pool contention even without blocked Java threads.

### 5.3. Multi-Tenant Fields and Security

Repository `findById(id)` **does not enforce tenant authorization automatically**. Knowing another tenant's order ID would expose cross-tenant data unless the application filters by tenant and checks permissions.

Prefer:

~~~java
Mono<Order> findByTenantIdAndId(String tenantId, String id);
~~~

Obtain `tenantId` from a **server-validated auth context**, never trusting client-supplied query parameters. Reactive context propagation must preserve authentication identity across operators and threads without falling back to `ThreadLocal`.

### 5.4. Mapping and Nulls

MongoDB documents may omit fields; a primitive Java `long amountMinor` defaults to 0 when missing under many mapping configs, blurring "0 currency units" with "missing data". Handle schema evolution via `@Field`, validation, nullable boxed types/records, defaults, and migrations—never expect reactive streams to repair missing schema fields.

## 6. Reactive Repositories: Domain-Driven CRUD and Queries

### 6.1. Basic Interface

~~~java
package com.example.orders;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderRepository
        extends ReactiveMongoRepository<Order, String> {

    Mono<Order> findByTenantIdAndId(String tenantId, String id);

    Flux<Order> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId, String status);

    Mono<Long> countByTenantIdAndStatus(String tenantId, String status);

    Mono<Boolean> existsByTenantIdAndCustomerId(
        String tenantId, String customerId);
}
~~~

Spring Data generates implementations from **method names** and domain metadata. Returning a **Publisher** (`Mono`/`Flux`) does not block when the method constructs the pipeline. Execution waits for subscription, so services and controllers must **return** the publisher.

### 6.2. Inherited CRUD Methods

| Method | Reactive Return | Notes |
|---|---|---|
| `findById(id)` | `Mono<Order>` | Emits `empty` if absent. |
| `findAll()` | `Flux<Order>` | Can emit an unbounded stream; never expose unfiltered over an API. |
| `save(order)` | `Mono<Order>` | Inserts or replaces/updates per entity state/version; not a field-level patch by default. |
| `deleteById(id)` | `Mono<Void>` | Completes without returning deleted count; tenant authorization must be checked separately. |
| `count()` | `Mono<Long>` | Expensive on large collections or broad filters. |
| `existsById(id)` | `Mono<Boolean>` | Separate read; does not eliminate check-then-write races. |

For reactive MongoDB, `ReactiveMongoRepository` inherits standard reactive CRUD operations, yet **not every imperative `MongoRepository` method carries an identical reactive counterpart**. Verify exact signatures for your Spring Data version when adding features like custom pagination.

### 6.3. Derived Queries

~~~java
Flux<Order> findByTenantIdAndStatus(String tenantId, String status);

Flux<Order> findByTenantIdAndAmountMinorGreaterThan(
    String tenantId, long amountMinor);

Mono<Order> findFirstByTenantIdAndCustomerIdOrderByCreatedAtDesc(
    String tenantId, String customerId);
~~~

Method names read nicely at small scale, though they quickly become **unwieldy** or unable to express complex aggregations. Reach for `@Query` or `ReactiveMongoTemplate` whenever filters, sorts, or updates grow complex.

### 6.4. Using `@Query` and Parameter Binding

~~~java
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends ReactiveMongoRepository<Order, String> {

    @Query(
        value = "{ 'tenantId': ?0, 'status': ?1 }",
        sort = "{ 'createdAt': -1, '_id': 1 }")
    Flux<Order> findVisibleByState(String tenantId, String status);
}
~~~

Spring Data binds `?0` and `?1` positionally. Never concatenate raw user-supplied fragments into query JSON strings; bind parameters or build `Criteria` to prevent injection and malformed queries. Never accept an unverified client-supplied `tenantId` in filters.

### 6.5. Reactive Queries Accepting Publisher Parameters

Some Spring Data repository methods accept **reactive parameters** (such as `Mono<String>`) to resolve arguments prior to querying, depending on API/version. Never abuse this pattern to disguise a blocking call: `Mono.just(blockingLookup())` still executes `blockingLookup()` **synchronously when building the `Mono`**.

### 6.6. Reactive Repositories and Pagination

In reactive code, do not try to declare `Page<Order> findAll(Pageable p)` as in imperative code. Instead, define:

~~~java
Flux<Order> findByTenantId(String tenantId, Pageable pageable);
~~~

And if the UI genuinely requires a total count:

~~~java
Mono<Long> countByTenantId(String tenantId);
~~~

`Flux` delivers the page contents; `count` runs as a **separate query** that does not necessarily share a snapshot timestamp with the list query during concurrent writes. Combine them with `Mono.zip(...)` when totals are required (or skip totals for infinite scrolling).

### 6.7. Why `findAll().collectList()` Is Hazardous

~~~java
Mono<List<Order>> everyOrder =
    repository.findAll().collectList();
~~~

While non-blocking at the I/O wait layer, this **loads the entire result set into RAM**. Across millions of documents, heap exhaustion, OOM crashes, and GC pauses still occur. Reactive does not eliminate memory bounds. Always apply tenant filters, indexed queries, `limit`/pagination, projections, or bounded streaming.

### 6.8. Repositories Do Not Cover Every Operation

When you need conditional atomic updates, complex aggregations, index hints, dynamic runtime sorts/limits, explicit write concerns/read preferences, or change streams, **`ReactiveMongoTemplate`** is usually clearer. Both repositories and templates can coexist **within the same service** sharing the same reactive MongoDB connection infrastructure.

## 7. ReactiveMongoTemplate: Flexible Querying

### 7.1. Injecting the Reactive Template

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final ReactiveMongoTemplate template;

    public OrderQueryService(ReactiveMongoTemplate template) {
        this.template = template;
    }
}
~~~

`ReactiveMongoTemplate` is the primary implementation of `ReactiveMongoOperations`, providing mapping, conversion, update/aggregation helpers, and driver integration. Always inject it via DI rather than constructing new `ReactiveMongoClient`/template instances per request.

### 7.2. `findOne` and `find`

~~~java
import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

public Mono<Order> findOne(String tenantId, String orderId) {
    Query q = query(where("tenantId").is(tenantId)
        .and("_id").is(orderId));
    return template.findOne(q, Order.class);
}

public Flux<Order> listOpen(String tenantId) {
    Query q = query(where("tenantId").is(tenantId)
        .and("status").is("OPEN"))
        .with(Sort.by(Sort.Direction.DESC, "createdAt"))
        .limit(20);
    return template.find(q, Order.class);
}
~~~

`findOne` returns `Mono<Order>` and `find` returns `Flux<Order>`. Java-to-MongoDB field mapping runs through Spring Data's mapping context; when `@Field("...")` aliases exist, use Java property paths in DSL builders and verify generated BSON if assembling raw JSON.

### 7.3. Fluent API

~~~java
Flux<Order> openOrders = template.query(Order.class)
    .matching(query(where("tenantId").is(tenantId)
        .and("status").is("OPEN")))
    .all();

Mono<Order> first = template.query(Order.class)
    .matching(query(where("tenantId").is(tenantId)))
    .one();
~~~

The fluent `template.query(Order.class)` API cleanly separates entity type, filter, projection, and terminal operator (`one()`/`first()`/`all()` depending on version). Do not mistake `one()` for guaranteeing database uniqueness if multiple docs match; enforce uniqueness via a **unique index** when required.

### 7.4. Projections Shrink Network and Heap Usage

~~~java
Query q = query(where("tenantId").is(tenantId)
    .and("status").is("OPEN"));
q.fields().include("_id").include("status").include("amountMinor");
q.limit(30);

Flux<Order> partial = template.find(q, Order.class);
~~~

Mapping a projection into a full entity class leaves unprojected fields `null` or defaulted; accidentally calling `save(partialEntity)` risks wiping existing fields. Prefer DTO projections (`template.query(...).as(OrderSummary.class)` or dedicated projection types) and **never pass a partial projection to `save`**.

### 7.5. Query Parameters and Indexes

~~~javascript
// MongoDB index matching the example filter + sort:
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: 1
})
~~~

Avoid unanchored regexes like `.*keyword.*` or deep `skip` offsets. For full-text search requirements, consider MongoDB Search indexes when supported by your deployment—a separate capability orthogonal to reactive execution.

## 8. ReactiveMongoTemplate: Inserting, Updating, and Deleting

### 8.1. Insert and Save

~~~java
public Mono<Order> create(Order order) {
    return template.insert(order);
}

public Mono<Order> save(Order order) {
    return template.save(order);
}
~~~

`insert` targets new documents; duplicate `_id` or unique keys raise errors (translated by Spring Data into data-access exceptions). `save` performs insert or replace/upsert depending on ID/version/mapping—do not assume it **patches only modified fields** across every case.

### 8.2. Atomic Conditional Updates

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

public Mono<UpdateResult> markPaid(
        String tenantId, String orderId) {

    Query q = query(where("_id").is(orderId)
        .and("tenantId").is(tenantId)
        .and("status").is("OPEN"));

    Update update = new Update().set("status", "PAID");
    return template.updateFirst(q, update, Order.class);
}
~~~

This performs a **single-document atomic write**, preventing the race condition of `findById -> mutate -> save` for state transitions. `UpdateResult.getMatchedCount()` and `getModifiedCount()` distinguish "no match" from "matched without field change" during idempotent updates.

### 8.3. Checking Update Outcomes Properly

~~~java
public Mono<Void> pay(String tenantId, String orderId) {
    return markPaid(tenantId, orderId)
        .flatMap(result -> {
            if (result.getMatchedCount() == 0) {
                return Mono.error(
                    new OrderConflictException("not OPEN or not found"));
            }
            return Mono.<Void>empty();
        });
}
~~~

`OrderConflictException` is an illustrative application exception you define. In multi-tenant APIs, deciding between HTTP 404 and 409 depends on security policy: never leak whether an order exists under a different tenant. Remember that `flatMap` code runs only upon subscription, not eagerly when `pay()` is called.

### 8.4. Multi-Document Updates and Resource Cost

~~~java
Query q = query(where("tenantId").is(tenantId)
    .and("status").is("EXPIRED"));

Mono<UpdateResult> updated = template.updateMulti(
    q, new Update().set("status", "ARCHIVED"), Order.class);
~~~

`updateMulti` can touch many documents and consume heavy server resources; switching to reactive does not permit firing hundreds of unbounded bulk updates concurrently. Keep bounded concurrency, proper indexes, and scheduling. When multi-collection atomicity is needed, use a transaction under supported topology.

### 8.5. Tenant-Scoped Deletes

~~~java
import com.mongodb.client.result.DeleteResult;

Mono<DeleteResult> deleted = template.remove(
    query(where("_id").is(orderId).and("tenantId").is(tenantId)),
    Order.class);
~~~

Inspect `deleted.getDeletedCount()` to confirm deletions. Never expose `repository.deleteById(orderId)` in a multi-tenant endpoint without verifying tenant authorization.

### 8.6. Atomic Find-and-Modify

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query q = query(where("_id").is(orderId)
    .and("tenantId").is(tenantId)
    .and("status").is("OPEN"));

Update u = new Update().set("status", "PAID");

Mono<Order> after = template.findAndModify(
    q, u,
    FindAndModifyOptions.options().returnNew(true),
    Order.class);
~~~

`findAndModify` atomically updates and returns a document in **one single-document operation**, avoiding races between separate update and read queries. If nothing matches, it returns `Mono.empty()`. Do not mistake this name for an implicit multi-document transaction.

### 8.7. Optimistic Locking with `@Version`

When an entity has `@Version`, Spring Data detects stale saves and raises `OptimisticLockingFailureException`. Exact guarantees still depend on the update path, version field, write concern, server support, and API:

- Retain `@Version` and handle optimistic-lock exceptions when using optimistic concurrency.
- Avoid `findById` followed by `save` without `@Version` under concurrent writes.
- Use explicit version predicates in `Query` for CAS updates when needed.
- Combine bounded retries with idempotency for transient failures.

**Never** assume custom `updateMulti` queries perform the same automatic version checks as `save(entity)`.

## 9. End-to-End WebFlux Services: Return Publishers, Do Not Self-Subscribe

A clean reactive request path looks like:

~~~text
HTTP client
   |
   v
WebFlux Router/Controller
   |
   v
Reactive Service (Mono/Flux)
   |
   +--> ReactiveMongoRepository
   |           |
   |           +--> Reactive MongoDB Driver
   |
   +--> ReactiveMongoTemplate
   |           |
   |           +--> Reactive MongoDB Driver
   |
   v
WebFlux subscribes/serializes with demand
   |
   v
HTTP response
~~~

**Core rule:** Controllers and services **return pipelines**; the framework subscribes and manages lifecycle and cancellation. Never call `subscribe()` to "fire and forget" or `block()` to "wait for completion" on request threads.

### 9.1. Tenant-Scoped Service

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class OrderService {
    private final OrderRepository repo;
    private final ReactiveMongoTemplate template;

    public OrderService(
            OrderRepository repo,
            ReactiveMongoTemplate template) {
        this.repo = repo;
        this.template = template;
    }

    public Mono<Order> get(String tenantId, String id) {
        return repo.findByTenantIdAndId(tenantId, id);
    }

    public Flux<Order> listOpen(String tenantId) {
        return repo.findByTenantIdAndStatusOrderByCreatedAtDesc(
            tenantId, "OPEN");
    }

    public Mono<Order> create(Order order) {
        return template.insert(order);
    }
}
~~~

Java snippets omit full imports and DTO validation to highlight reactive patterns; production code requires constructors, exception mapping, tenant authorization, input validation, and idempotency.

### 9.2. Controller Returning `Mono<ResponseEntity<...>>`

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Order>> get(
            @PathVariable String id,
            @RequestHeader("X-Verified-Tenant") String tenantId) {
        return service.get(tenantId, id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping
    public Flux<Order> list(
            @RequestHeader("X-Verified-Tenant") String tenantId) {
        return service.listOpen(tenantId).take(50);
    }
}
~~~

**Security warning:** `X-Verified-Tenant` is solely a placeholder for an **identity verified and stripped/signed by an API gateway or security filter**. Never trust raw tenant headers sent arbitrarily by clients. In real applications, extract the principal/tenant from **Spring Security's reactive context** (`ReactiveSecurityContextHolder`) and filter every DB query by tenant.

### 9.3. HTTP 404 for Empty

When `findById` finds nothing, it emits `Mono.empty()` rather than an exception. With:

~~~java
return repo.findById(id)
    .map(ResponseEntity::ok)
    .defaultIfEmpty(ResponseEntity.notFound().build());
~~~

WebFlux observes the `Mono<ResponseEntity<Order>>` and returns HTTP 404 when empty. Replacing this with `repo.findById(id).block()` breaks the non-blocking event-loop model.

### 9.4. Validation and Response Types

When creating an order:

~~~java
@PostMapping
public Mono<ResponseEntity<Order>> create(
        @Valid @RequestBody Mono<CreateOrderRequest> request) {
    return request
        .map(dto -> toEntity(dto)) // small, non-blocking CPU work
        .flatMap(service::create)
        .map(saved -> ResponseEntity
            .status(HttpStatus.CREATED)
            .body(saved));
}
~~~

`toEntity` is a placeholder mapper; validate inputs at the boundary, bind tenant from authentication, enforce unique keys, initial status, and business rules. Consult Spring Framework documentation if your WebFlux/Bean Validation version handles `@Valid` on reactive bodies differently, and verify endpoints via `WebTestClient`.

### 9.5. Never Self-Subscribe Inside a Controller

**Wrong:**

~~~java
@PostMapping("/bad")
public Mono<String> bad(@RequestBody Mono<Order> body) {
    body.flatMap(repo::save).subscribe();
    return Mono.just("Saved");
}
~~~

The controller returns `Saved` before the DB write finishes, write failures never reach the HTTP response, and cancellation/transaction scope are lost.

**Right:**

~~~java
@PostMapping("/good")
public Mono<Order> good(@RequestBody Mono<Order> body) {
    return body.flatMap(repo::save);
}
~~~

WebFlux subscribes once per HTTP request lifecycle on the returned `Mono<Order>`. Note that **at-least-once client retries** can still replay requests, so keep stable business idempotency keys.

### 9.6. Chaining Sequential Operations with `flatMap`

Suppose creating an order and saving an audit event in MongoDB:

~~~java
public Mono<Order> createWithAudit(Order input) {
    return repo.save(input)
        .flatMap(saved ->
            auditRepo.save(new AuditEvent(saved.getId(), "CREATED"))
                .thenReturn(saved));
}
~~~

This enforces **execution order** ("save order, then save audit") within one subscription, **not** a multi-document atomic transaction. If saving the audit fails, the order remains persisted. For all-or-nothing atomicity, use **`ReactiveMongoTransactionManager`** on a replica set/sharded cluster or a transactional outbox pattern.

### 9.7. `Mono.zip` for Independent Reads

~~~java
public Mono<OrderDetailsDto> getDetails(String tenantId, String id) {
    Mono<Order> order = repo.findByTenantIdAndId(tenantId, id);
    Mono<Long> activeCount = repo.countByTenantIdAndStatus(
        tenantId, "OPEN");

    return Mono.zip(order, activeCount)
        .map(tuple -> new OrderDetailsDto(
            tuple.getT1(), tuple.getT2()));
}
~~~

`Mono.zip` subscribes to both publishers concurrently, issuing **2 simultaneous DB operations**. If `order` completes empty, `zip` completes empty and cancels the sibling branch; if HTTP 404 is needed, handle empty beforehand or chain via `flatMap` so counting only happens when the order exists. Under concurrent writes, count and order reflect **two separate read timestamps**—`zip` does not create a transaction or snapshot.

### 9.8. When to Prefer `concatMap` Over `flatMap`

~~~java
Flux<Order> savedInOrder = Flux.fromIterable(inputs)
    .concatMap(repo::save);
~~~

`concatMap` preserves strict sequential execution and completion ordering, fitting writes with sequential dependencies. `flatMap(repo::save, 8)` offers higher concurrency though completion order may vary. **Never** pass tens of thousands of documents into an unbounded `flatMap` against a busy database.

## 10. Never Block on the WebFlux Event Loop

### 10.1. `block()` Crosses from Reactive Back to Blocking

**Severe anti-pattern:**

~~~java
@GetMapping("/{id}/bad")
public Order bad(@PathVariable String id) {
    return repo.findById(id).block();
}
~~~

`block()` waits synchronously until the `Mono` completes; when invoked on a Reactor Netty event-loop thread or non-blocking scheduler, Reactor throws:

~~~text
IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Even on threads where Reactor does not throw an exception, blocking still **pins a worker thread** and degrades throughput. Never take "it didn't throw" as proof that code is non-blocking.

### 10.2. Operations That Block

| Operation | Hazard | Replacement |
|---|---|---|
| `Mono.block()` / `Flux.blockFirst()` | Pins thread waiting on Publisher. | Return/compose `Mono`, `Flux`. |
| `Flux.toIterable()` / `toStream()` | Pulls elements synchronously via iterator/stream. | `map`/`flatMap`/streaming response. |
| `Thread.sleep(...)` | Blocks the executing thread. | `Mono.delay(...)`/`delayElement(...)`. |
| `MongoTemplate.find(...)` | Synchronous Java MongoDB I/O. | `ReactiveMongoTemplate.find(...)`. |
| `JdbcTemplate` / blocking JDBC driver | Pins worker waiting on DB. | R2DBC driver if supported, or isolated blocking wrapper. |
| `RestTemplate` / Apache blocking HTTP | Blocking network I/O. | `WebClient`. |
| Large `Files.readAllBytes(...)`, sync disk I/O | Blocks thread, spikes memory. | Async file I/O or `boundedElastic` + size caps. |
| Blocking S3/payment SDKs | Blocking network I/O. | Async SDK or `boundedElastic` with capped concurrency. |
| Long `synchronized`/locks | Thread contention/blocking, serialization. | Avoid long critical sections; immutable/async design. |
| Heavy CPU JSON/crypto/image work | Stalls event loop even without I/O. | Bounded CPU scheduler/worker with capped concurrency. |

Note: **CPU-heavy work is not blocking I/O**; `Schedulers.boundedElastic()` targets blocking tasks, whereas pure CPU work fits `parallel()` or bounded worker pools. Whichever scheduler you offload to, total queued/active tasks must be bounded.

### 10.3. `Mono.just(blockingCall())` Still Blocks Before Subscription

**Wrong:**

~~~java
Mono<User> user = Mono.just(legacyDao.loadUser(id));
~~~

Java evaluates `legacyDao.loadUser(id)` **immediately while constructing the `Mono`**, blocking the caller thread. Wrapping in `Mono.defer` only postpones evaluation; if subscribed on the event loop, it **still blocks**.

**When forced to wrap a legacy blocking API:**

~~~java
Mono<User> user = Mono.fromCallable(() -> legacyDao.loadUser(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` defers invocation until subscription, and `subscribeOn` shifts execution onto a scheduler sized for blocking tasks. Treat this as a **temporary compatibility bridge**, not a replacement for `ReactiveMongoRepository`/`ReactiveMongoTemplate`.

### 10.4. BoundedElastic Does Not Have a Safe Infinite Queue

Reactor's `Schedulers.boundedElastic()` caps **backing threads**, yet carries a **large internal task queue capacity** (version-dependent default per Reactor docs). If 20,000 concurrent requests invoke a legacy blocking API, you still suffer:

- Long queuing delays on `boundedElastic`.
- HTTP deadline expiration while tasks sit waiting.
- Elevated heap and queue pressure.
- Overload on the legacy service or database.

Place **admission limits, global/per-tenant concurrency caps, timeouts, and retry limits** ahead of it. For substantial blocking workloads, create a dedicated bounded scheduler via `Schedulers.newBoundedElastic(...)` with explicit limits and **dispose of it on shutdown** to isolate bulkheads.

### 10.5. `publishOn` vs `subscribeOn`

~~~java
Mono.fromCallable(() -> legacyDao.loadUser(id))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::mapToDto);
~~~

`subscribeOn` dictates where upstream subscription and source execution run—ideal when **the source itself blocks**.

~~~java
repository.findById(id)
    .publishOn(Schedulers.parallel())
    .map(this::cpuHeavyTransformation);
~~~

`publishOn` switches the scheduler for **downstream operators** from that point onward—useful when moving heavy CPU transformations off the event loop. If `cpuHeavyTransformation` is truly expensive, cap concurrency rather than treating `parallel()` as unlimited CPU cores.

**Mistake:** appending `publishOn(boundedElastic())` **after** `.map(x -> legacyBlocking())` does not travel backward in time to prevent the earlier `map` from blocking.

### 10.6. Replace `Thread.sleep` with Timer Publishers

**Wrong:**

~~~java
return repo.findById(id)
    .map(order -> {
        Thread.sleep(1000); // won't compile uncaught; still blocks
        return order;
    });
~~~

**Right when delaying a signal:**

~~~java
return repo.findById(id)
    .delayElement(Duration.ofSeconds(1));
~~~

`delayElement` postpones the signal without pinning an event-loop thread in `sleep()` for a full second. For retry backoff, use `retryWhen(Retry.backoff(...))` with caps and retryable-error filters—never add arbitrary delays to normal requests.

### 10.7. Blocking Inside a Mapper Still Blocks

~~~java
return repo.findById(id)
    .map(order -> blockingPaymentGateway.check(order));
~~~

`map` runs on the thread emitting the signal, often an I/O or event-loop thread. Even though the method returns `Mono<Result>`, blocking inside `map` stalls that worker. Prefer an async gateway:

~~~java
return repo.findById(id)
    .flatMap(order -> asyncPaymentGateway.check(order));
~~~

If only a blocking SDK exists, wrap with `fromCallable + subscribeOn(boundedElastic())` **and an admission cap**, while separating idempotency and timeouts for external side effects.

### 10.8. Testing with BlockHound

In test/diagnostic environments, **BlockHound** helps detect blocking calls on non-blocking schedulers. However, BlockHound support depends on JDK/Reactor/framework versions and instrumentation compatibility. Some blocking patterns go undetected or rely on allowlists; **never** treat "BlockHound passed" as 100% end-to-end non-blocking proof.

Pair it with Reactor event-loop lag metrics, thread dumps, CPU profiles, and load tests.

### 10.9. When Is Calling `block()` Acceptable?

At **imperative boundaries** such as CLI entry points, unit tests, or startup scripts explicitly outside event loops, `block()` (preferably with a timeout) can be appropriate. **Never** call `block()` mid-pipeline inside a WebFlux request handler, and never assume `block()` somehow "forces a publisher to finish faster".

## 11. Backpressure and Concurrency Caps: Reactive Is Not Infinite

### 11.1. Subscriber Demand and MongoDB Cursors

When an HTTP client reads slower than MongoDB emits documents, Reactor propagates demand and cancellation upstream. However, the MongoDB driver/server fetches data in **cursor batches** and operators apply **prefetching**, so there is no guarantee that "requesting 1 HTTP item reads only 1 BSON document from disk".

~~~text
MongoDB cursor -> Reactive Driver -> Flux<Order> -> JSON encoder -> HTTP socket
                         ^                        |
                         |        demand/backpressure
                         +------------------------+
~~~

**Backpressure is a flow-control mechanism**, not zero-RAM execution, not a substitute for query `limit`, and not protection against 10,000 simultaneous subscriptions overloading the service.

### 11.2. Bounding `flatMap`

**Risky:**

~~~java
Flux<Order> all = Flux.fromIterable(ids)
    .flatMap(id -> repo.findById(id));
~~~

`flatMap` uses Reactor-version-dependent concurrency/prefetch defaults. With large lists, it can launch far more concurrent MongoDB calls than intended.

**Explicit:**

~~~java
Flux<Order> bounded = Flux.fromIterable(ids)
    .flatMap(id -> repo.findById(id), 8);
~~~

`8` caps the number of **concurrently subscribed inner publishers within that single pipeline**, not a "global limit of 8 MongoDB operations". If 100 HTTP requests run that pipeline simultaneously, up to ~800 in-flight queries can fire depending on conditions. Enforce global limits at the service/gateway layer to protect the cluster.

### 11.3. `concatMap`, `flatMapSequential`, and Ordering

| Operator | Concurrency | Ordering | Use When |
|---|---|---|---|
| `concatMap` | Strictly sequential per source. | Preserves result order. | Order-dependent writes or ordered side effects. |
| `flatMap(fn, n)` | Up to `n` inner publishers. | Completion order may interleave. | Bounded independent reads/updates. |
| `flatMapSequential(fn, n)` | Subscribes concurrently; emits in source order. | Preserves output order; may buffer early completions. | Need concurrency plus ordered output within memory budget. |

`flatMapSequential` does not execute operations sequentially; it only **reorders emissions**, buffering early completions in memory—so still cap `n` and output sizes.

### 11.4. Batch Instead of N+1 Queries

**Inefficient:**

~~~java
return Flux.fromIterable(ids)
    .flatMap(repo::findById, 16);
~~~

For 1,000 IDs, even concurrency=16 executes up to 1,000 separate MongoDB round trips.

**Consider a bounded `$in` query:**

~~~java
Query q = query(where("_id").in(ids));
q.limit(200); // illustrative; align with API policy
return template.find(q, Order.class);
~~~

Never feed millions of IDs into `$in`, never omit the tenant filter, and always cap responses. Note that MongoDB `$in` **does not guarantee input-list ordering**; sort or remap in memory if order matters.

### 11.5. `buffer` and `window`

~~~java
Flux<List<Order>> batches = ordersFlux.buffer(100);
~~~

`buffer(100)` groups items into lists of up to 100 elements, yet multiple batches can remain in flight if downstream keeps requesting. `window(100)` splits into sub-publishers without materializing a `List` immediately; both require resource, error, and cancellation planning.

Do not call `buffer(100)` followed by `collectList()` over an unbounded stream assuming memory is bounded—you still accumulate the whole stream.

### 11.6. `onBackpressureBuffer` Is Not a Cure-All

~~~java
flux.onBackpressureBuffer(10_000);
~~~

This operator **buffers extra elements in RAM**, masking slow consumers while increasing heap pressure. Use bounded variants with explicit overflow strategies only when justified, and weigh alternatives:

- Truly backpressure-aware sources.
- Bounded in-memory queues with rejection/degradation.
- Durable message brokers for long job queues.
- `onBackpressureLatest`/`onBackpressureDrop` strictly when **data loss is acceptable** (live telemetry/UI)—never for payments or orders.

### 11.7. Reactive Stacks Still Use MongoDB Connection Pools

The MongoDB Reactive Streams driver uses async connections, yet still maintains **per-server pools** governed by `maxPoolSize` and `maxConnecting` depending on driver version. Subscriptions do not pin one socket forever, nor does event-loop thread count equal DB concurrency. If thousands of `flatMap` queries launch together, the driver still hits **checkout waits and server resource contention**.

### 11.8. Defense in Depth Across Layers

~~~text
API Gateway quota
        |
        v
Request concurrency / tenant admission
        |
        v
Reactor flatMap(..., maxConcurrency)
        |
        v
Reactive MongoDB Driver pool
        |
        v
mongos/mongod CPU, I/O and locks
~~~

A local `flatMap(..., 8)` is not a global ceiling. Scaling from 5 to 50 pods multiplies peak cluster pressure 10x without changing a line of code. Size budgets by **max pods x per-pod DB in-flight x query fanout** and validate under realistic load.

## 12. Streaming, Pagination, and Large Result Sets

### 12.1. `Flux` Does Not Automatically Cap Document Counts

~~~java
@GetMapping("/all")
public Flux<Order> all() {
    return repository.findAll();
}
~~~

This can serialize an enormous stream, tie up HTTP connections, and strain MongoDB. Production endpoints should enforce:

- Tenant and status filters.
- Maximum page sizes or `limit`.
- Indexes aligned with filter and sort.
- HTTP output size and duration budgets.
- Cancellation on client disconnect.

### 12.2. Offset Pagination with Repositories

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

public Flux<Order> listPage(
        String tenantId, int page, int size) {

    int safeSize = Math.min(Math.max(size, 1), 100);
    int safePage = Math.max(page, 0);

    Pageable pageable = PageRequest.of(
        safePage,
        safeSize,
        Sort.by(Sort.Direction.DESC, "createdAt")
            .and(Sort.by("_id")));

    return repo.findByTenantId(tenantId, pageable);
}
~~~

Declare `Flux<Order> findByTenantId(String tenantId, Pageable pageable);` on the repository. **Do not declare `Mono<Page<Order>>` on derived reactive finders** as in imperative code: Spring Data MongoDB reactive docs state that `Page` wrappers are unsupported in that manner; construct a custom DTO pairing `Flux` + `count` if totals are needed.

### 12.3. Count Is a Second Query

~~~java
record OrderPage(List<Order> items, long total) { }

Mono<OrderPage> page = repo.findByTenantId(tenantId, pageable)
    .collectList()
    .zipWith(repo.countByTenantId(tenantId))
    .map(t -> new OrderPage(t.getT1(), t.getT2()));
~~~

Here `collectList()` aggregates **only one bounded page**, not the entire collection. `zipWith` runs the two queries concurrently, though list and count **do not share a single consistent snapshot** during concurrent writes; if strict snapshot alignment is required, design a snapshot/transactional read weighing its cost.

### 12.4. Keyset Pagination

Deep offset `skip(page * size)` slows down as page numbers grow and shifts under concurrent inserts/deletes. For `createdAt DESC, _id DESC`, use seek pagination:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  $or: [
    { createdAt: { $lt: ISODate("2026-11-14T00:00:00Z") } },
    { createdAt: ISODate("2026-11-14T00:00:00Z"),
      _id: { $lt: "ORD-1000" } }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(50)
~~~

Pass an opaque signed **cursor token** carrying the last `createdAt`/ID and enforce page-size bounds; keep the tenant filter intact. Back the query with a matching composite index. Ensure comparator types match your ID's BSON type/collation (ObjectId, UUID, string).

Newer Spring Data versions offer scroll/keyset abstractions depending on repository API version, yet understanding the underlying `$or` query keeps you independent of any single wrapper.

### 12.5. Cursor Batch Size

~~~java
Query q = query(where("tenantId").is(tenantId))
    .cursorBatchSize(100)
    .limit(500);

Flux<Order> stream = template.find(q, Order.class);
~~~

`cursorBatchSize(100)` tunes the *target batch size* fetched from the server per MongoDB cursor protocol; it is not `Flux.request(100)` and imposes no total limit without `limit(500)`. Tune batch size to balance network round trips, memory, and time-to-first-element.

### 12.6. Streaming JSON and NDJSON

For multi-item streams, HTTP endpoints can emit `application/x-ndjson` line by line:

~~~java
@GetMapping(
    value = "/stream",
    produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<OrderSummary> stream() {
    return service.streamSummaries();
}
~~~

`streamSummaries()` is a placeholder service enforcing tenant filters, bounded queries, and projections. True end-to-end streaming and backpressure depend on the HTTP stack, codecs, proxies, and clients: intermediate CDNs or proxies may buffer whole responses regardless of NDJSON headers.

### 12.7. HTTP Client Disconnect and Cancellation

When a client aborts an HTTP request, WebFlux propagates `cancel` up the publisher chain. The reactive MongoDB driver can close/kill the cursor and stop pulling batches, yet **this never rolls back an already-dispatched server write**. Ensure:

- Proper lifecycle cleanup of subscriptions, cursors, and resources.
- No orphaned long-running background tasks after cancel.
- Stable idempotency keys on writes.
- Timeouts and tracing to surface lingering operations.

### 12.8. Backpressure Is Not Durability

Slow SSE/NDJSON consumption does not make MongoDB retain events indefinitely until the client resumes. When zero event loss is required, rely on **change stream resume tokens + durable checkpoints** or a durable message broker. `Flux` is a signal/demand abstraction, not a persistent event log.

## 13. Aggregation with ReactiveMongoTemplate

### 13.1. Example Aggregating Order Statuses

~~~java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

record StatusSummary(String status, long total) { }

public Flux<StatusSummary> countByStatus(String tenantId) {
    Aggregation pipeline = newAggregation(
        match(where("tenantId").is(tenantId)),
        group("status").count().as("total"),
        project("total").and("_id").as("status")
    );

    return template.aggregate(
        pipeline, Order.class, StatusSummary.class);
}
~~~

This snippet assumes Spring Data maps `_id` to `status` and the record constructor cleanly; verify field mapping if production uses custom `@Field` names. Filter by tenant in the leading `$match` with a supporting index; aggregation executes **on the MongoDB server**, so client-side reactivity does not make `$group` cheaper.

### 13.2. Streaming Rows vs `Mono<List<...>>`

`Flux<StatusSummary>` streams grouped buckets individually, whereas:

~~~java
Mono<List<StatusSummary>> all = countByStatus(tenantId).collectList();
~~~

materializes every bucket in RAM. For a small bounded number of status values, collecting into a `List` is fine. Grouping by `customerId` across millions of customers requires bounds, streaming, pagination, or async export.

### 13.3. Updates with Aggregation Pipelines

MongoDB supports aggregation-pipeline updates in supported server versions, expressed via `AggregationUpdate` in Spring Data. With the reactive template, account for:

- Single-document atomicity, not implicit multi-document transactions.
- Mapping of `@Version` fields.
- Tenant predicates and index usage in the match filter.
- `UpdateResult` and `onError` semantics.
- Server CPU/IOPS impact and timeouts on broad updates.

Never assume every read-aggregation stage works inside update pipelines; MongoDB restricts supported update-pipeline stages.

### 13.4. "Aggregate Then Write" Pattern

~~~java
return template.aggregate(pipeline, Order.class, StatusSummary.class)
    .flatMap(summary -> statsRepository.save(
        toStatsDocument(summary)), 4)
    .then();
~~~

An aggregation yielding thousands of groups followed by `flatMap` writes produces N separate writes; concurrency `4` is only a **local pipeline cap**, offering neither atomic transactions nor snapshot consistency across collections. For atomic workflows use transactions; for analytics materialization consider idempotent scheduled backfills.

### 13.5. Spring Data Mapping Does Not Replace Manual `explain`

Optimize performance using `explain("executionStats")` on actual query shapes, inspecting `IXSCAN`/`COLLSCAN`, sorts, stages, and examined docs. A slow reactive pipeline often stems from MongoDB server execution rather than Reactor scheduling—measure both **command duration** and **event-loop lag**.

## 14. Reactive Transactions: Reactor Context Instead of ThreadLocal

When a use case must update two collections atomically, reactive execution can hop across threads, so transaction/session binding **cannot rely on `ThreadLocal`** as imperative frameworks do.

### 14.1. `ReactiveMongoTransactionManager`

Spring Data MongoDB provides `ReactiveMongoTransactionManager` backed by `ReactiveMongoDatabaseFactory`, attaching the MongoDB `ClientSession` to the **Reactor subscriber Context**. Operations executed through the reactive template join the transaction via that context.

The MongoDB deployment must support transactions (eligible replica set or sharded cluster), database users need permissions, and the Spring context must register the transaction manager. Adding the reactive Mongo starter alone **does not automatically enable transactions** in all setups.

### 14.2. Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;

@Configuration
public class MongoTransactionsConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Ensure participating templates and repositories share the exact configured **`ReactiveMongoDatabaseFactory`** and manager rather than spinning up secondary clients/factories expecting shared transactions.

### 14.3. `TransactionalOperator`

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.transaction.ReactiveTransactionManager;

@Bean
TransactionalOperator mongoTxOperator(
        ReactiveTransactionManager manager) {
    return TransactionalOperator.create(manager);
}
~~~

Then compose:

~~~java
public Mono<Order> createWithAudit(
        Order order, TransactionalOperator tx) {
    return template.insert(order)
        .flatMap(saved ->
            template.insert(new AuditEvent(saved.getId(), "CREATED"))
                .thenReturn(saved))
        .as(tx::transactional);
}
~~~

`as(tx::transactional)` scopes the transaction around the **upstream pipeline**. Both inserts must be subscribed **within** that chain; never detach `auditRepo.save(...).subscribe()` or `block()`. If either write fails, the transaction manager aborts according to MongoDB transaction semantics and constraints.

### 14.4. `@Transactional` with Publishers

~~~java
@Service
public class OrderWorkflow {
    private final ReactiveMongoTemplate template;

    @Transactional
    public Mono<Order> createAndRecord(Order order) {
        return template.insert(order)
            .flatMap(saved ->
                template.insert(new AuditEvent(saved.getId(), "CREATED"))
                    .thenReturn(saved));
    }
}
~~~

A **reactive transaction manager** must be configured, calls must flow through the Spring AOP proxy (avoid **self-invocation**), and the method must return a reactive type so subscription drives the transaction lifecycle. Annotating a `void` method that calls `subscribe()` manually does not create the intended reactive transaction scope.

### 14.5. Do Not Confuse Reactor Context with ThreadLocal

~~~text
Subscriber Context:
   ClientSession / transaction metadata
          |
          v
 Reactor operators
          |
     [thread switches]
          |
          v
 ReactiveMongoTemplate operations
          |
          v
  Same transaction context
~~~

Custom `ThreadLocal<Session>` variables break or bleed across requests when `publishOn` switches threads. Rely on Spring's reactive transaction manager/context integration, and propagate metadata like `correlationId` or `tenantId` via **Reactor Context** or Spring Security's reactive context.

### 14.6. Reactive Repositories and Explicit `ClientSession`

Spring Data MongoDB documentation separates **explicit session support on `ReactiveMongoTemplate`** from reactive repository methods: do not assume arbitrary repository methods accept a `ClientSession` parameter like the raw driver. For explicit session control, use `ReactiveMongoTemplate.withSession(...)` callbacks per documentation; for declarative reactive transactions, configure the reactive transaction manager and context properly.

### 14.7. Transactions and Parallel Operations

Never write:

~~~java
Flux.fromIterable(steps)
    .flatMap(step -> template.save(step), 64)
    .as(tx::transactional);
~~~

expecting **64 concurrent operations on one MongoDB `ClientSession`** to work safely. The MongoDB Java driver and sessions do not support arbitrary concurrent operations within one transaction; run dependent steps **sequentially**:

~~~java
Flux.fromIterable(steps)
    .concatMap(template::save)
    .then()
    .as(tx::transactional);
~~~

Production transactions also require bounded retries with backoff, tight lifetime limits, and zero blocking external calls inside the transaction.

### 14.8. Ambiguous Commits and External Side Effects

If a client times out or drops the network after sending `commitTransaction`, the transaction **may have committed** without the app receiving the ACK. Never re-run the whole business operation under a fresh ID. Use stable idempotency keys, MongoDB error labels/transaction retry helpers, and state reconciliation. When sending emails or charging payment gateways, prefer a transactional outbox over executing non-idempotent external side effects inside a retryable transaction callback.

## 15. Tailable Cursors and Change Streams: Long-Lived Publishers

For continuous data feeds, `Flux` excels—yet **capped-collection tailable cursors** and **MongoDB change streams** are fundamentally different mechanisms.

### 15.1. Tailable Cursors on Capped Collections

A capped collection enforces fixed size and preserves insertion order, enabling tailable cursors that await newly inserted documents:

~~~java
import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;

Flux<LogEvent> events = template.tail(
    query(where("level").is("WARN")),
    LogEvent.class);
~~~

Key conditions:

- The collection must be **capped**; never expect tailable cursors on regular collections.
- Streams run indefinitely until canceled or failed.
- Tailable cursors can terminate if cursor positions become invalid or in edge cases with empty collections.
- Capped collections overwrite older documents; they provide **no infinite durable event replay**.

### 15.2. Reactive Repository `@Tailable`

~~~java
import org.springframework.data.mongodb.repository.Tailable;

public interface LogEventRepository
        extends ReactiveMongoRepository<LogEvent, String> {

    @Tailable
    Flux<LogEvent> findByLevel(String level);
}
~~~

`@Tailable` only applies to methods returning **multi-element reactive types** such as `Flux`. For critical event logs requiring durability, replay, and ordering, prefer change streams or a dedicated message broker rather than an uncheckpointed capped collection.

### 15.3. Change Streams on Replica Sets and Sharded Clusters

MongoDB change streams deliver change notifications for supported collections/databases and require a **replica set or sharded cluster** (not plain standalone `mongod`). Reactive Spring Data API:

~~~java
import org.springframework.data.mongodb.core.ChangeStreamEvent;

Flux<ChangeStreamEvent<Order>> changes = template
    .changeStream(Order.class)
    .watchCollection("orders")
    .listen();
~~~

This fits CQRS projections, cache invalidation, and notifications—though do **not assume events are retained forever**. Oplog/history windows, resume tokens, namespace drops/renames, and server versions govern resumability.

### 15.4. Processing and Persisting Resume Tokens

~~~java
Flux<Void> processing = template.changeStream(Order.class)
    .watchCollection("orders")
    .listen()
    .concatMap(event ->
        projectionService.applyIdempotently(event)
            .then(checkpointStore.save(event.getResumeToken()))
    );
~~~

`projectionService.applyIdempotently` and `checkpointStore.save` are **reactive** application methods you implement. `concatMap` maintains ordering between processing and checkpointing within a subscription.

**There is no automatic end-to-end exactly-once guarantee**: crashing after applying an external side effect yet before saving the checkpoint causes replay upon restart. Design **idempotent consumers deduplicating by event/document version** and persist checkpoints only after side effects are durable.

### 15.5. Never `subscribe()` and Lose the `Disposable`

When a background worker subscribes manually:

~~~java
Disposable handle = changes.subscribe(
    event -> handleEvent(event),
    error -> logFailure(error));
~~~

Dispose via `handle.dispose()` on shutdown, add retry/backoff/resume handling, and bound concurrency; in production manage lifecycle via a Spring bean/`SmartLifecycle`/supervised service—never open a background subscription per HTTP request.

### 15.6. Streaming via Server-Sent Events

~~~java
@GetMapping(
    value = "/orders/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<OrderDto>> events() {
    return changeService.eventsForAuthenticatedTenant()
        .map(order -> ServerSentEvent.builder(order).build());
}
~~~

HTTP clients can disconnect anytime. Enforce tenant filtering, authentication, throttling, rate limits, resume/reconnect protocols, and caps on concurrent change stream subscriptions. Long-lived streams still consume cursors and sockets even with minimal Java threads.

### 15.7. `Flux` Does Not Create a Durable Queue

If a slow consumer falls behind MongoDB's oplog history window, resuming fails. For long-term replay guarantees, bridge into Kafka/RabbitMQ/SQS or dedicated retention logs; change streams provide bounded-window change feeds, not infinite data warehouses.

## 16. Error Handling: Distinguishing Empty, Failure, and Retry

### 16.1. Empty Documents Are Not Exceptions

~~~java
return repo.findByTenantIdAndId(tenantId, id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
~~~

`switchIfEmpty` triggers only when upstream **completes without emitting a value**—not when a query fails over the network. For HTTP 404, map `OrderNotFoundException` via `@ControllerAdvice` or return `ResponseEntity.notFound()`.

### 16.2. `onErrorReturn` Can Mask Incorrect Data

~~~java
// ANTI-PATTERN for monetary/order counts:
repo.countByTenantId(tenantId)
    .onErrorReturn(0L);
~~~

If MongoDB times out, returning `0` misleads the UI into showing "no orders" instead of "failed to load". For business-critical paths, **propagate the error** or return an explicitly flagged degraded DTO.

### 16.3. Conditional `onErrorResume`

~~~java
Mono<OrderSummary> summary = template.findOne(q, Order.class)
    .map(OrderSummary::from)
    .onErrorResume(
        MongoException.class,
        ex -> cachedSummaryService.getIfFresh(tenantId, id));
~~~

Fallbacks are valid only when cached data is **authorized and sufficiently fresh per business policy**. `cachedSummaryService.getIfFresh` is an illustrative reactive helper. If unavailable, surface a clear error rather than hiding bugs or permission denials.

### 16.4. Always Cap `retryWhen`

~~~java
Mono<Order> read = repo.findByTenantIdAndId(tenantId, id)
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(1))
        .filter(this::isTransientMongoError));
~~~

`isTransientMongoError` is an application predicate inspecting exception types/error labels for your version; **never retry all `RuntimeException`s** (validation, duplicate key, auth failures, etc.). Bound total attempts and **remaining deadline**; remember the MongoDB driver may already perform internal retries, so measure total command attempts.

### 16.5. Retrying Writes Can Duplicate Business Operations

~~~text
Attempt 1: insert order _id=ORD-101
Server writes document
Network response lost
Client retries request
Attempt 2: generates new _id=ORD-102
=> duplicate business order
~~~

Applying `retryWhen` across an entire reactive creation flow is **unsafe** if each subscription mints a new ID or fires external payments/emails. Use stable idempotency keys, unique indexes, and proper retryable-write/transaction reconciliation.

### 16.6. Reactor Operator Timeouts

~~~java
Mono<Order> result = repo.findByTenantIdAndId(tenantId, id)
    .timeout(Duration.ofMillis(500));
~~~

Reactor's `timeout` emits an error and cancels upstream if completion/emission misses the deadline. However:

- It is a **Reactor operator-level timeout**, not MongoDB server-side `maxTimeMS`.
- Cancellation does not roll back a server write already sent.
- A 500 ms timer might start only after waiting in an HTTP queue.
- Driver/server timeouts and CSOT have separate semantics that interact with Reactor timers.

Bound server execution using `Query.maxTime(...)`/supported driver options, and align HTTP deadlines and CSOT by version. **Never mistake `Mono.timeout` for full admission control and cancellation safety**.

### 16.7. `doOnError` Does Not Swallow Errors

~~~java
return repo.findById(id)
    .doOnError(ex -> metrics.increment("mongo.read.error"))
    .onErrorMap(ex -> new OrderDataAccessException(ex));
~~~

`doOnError` is an observation hook that leaves the error signal intact. If `metrics.increment(...)` throws, it can mask the root cause—ensure telemetry side effects never crash pipelines.

### 16.8. `doFinally` for Cleanup and Metrics

~~~java
return repo.findById(id)
    .doFinally(signalType ->
        metrics.recordTermination(signalType.name()));
~~~

`doFinally` runs on complete, error, or cancel per Reactor lifecycle—useful for recording metrics. Never execute **blocking DB/network cleanup** inside `doFinally` on an event loop; use `usingWhen` or managed reactive resources for async cleanup.

## 17. Timeouts and Connection Pools in Reactive MongoDB

### 17.1. Reactive Does Not Bypass Connection Pools

The Reactive Streams driver still opens pools to `mongod`/`mongos`; concurrent reactive subscriptions contend for pooled connections. Monitor:

- Pool in-use/size, checkout waits and failures.
- Server selection failures.
- Command execution latencies.
- Connection creation, close, and clear rates.
- MongoDB server CPU, IOPS, cache, and lock queues.
- Reactor event-loop lag and HTTP p95/p99.

### 17.2. Layers of Timeouts

| Timeout | Layer | Does NOT Guarantee |
|---|---|---|
| HTTP/API deadline | Gateway / WebFlux app | Does not automatically roll back MongoDB writes. |
| Reactor `timeout(Duration)` | Publisher pipeline | Does not cancel an already-committed server command. |
| MongoDB server selection timeout | Reactive driver topology | Does not solve pool exhaustion after server selection. |
| Connection checkout/wait timeout | Reactive driver pool | Does not replace server command execution limits. |
| Connect/socket timeout | Network / driver | Does not guarantee the HTTP response meets its deadline. |
| `maxTimeMS` | MongoDB server execution | Excludes client queuing, selection, and pool checkout wait. |
| Driver CSOT (if supported by version) | MongoDB operation | Excludes earlier HTTP pipeline queuing prior to DB call. |

**Do not copy Java Sync Driver defaults blindly onto another MongoDB Reactive Streams Driver release.** While option names look similar, defaults, behaviors, and CSOT support vary by driver version.

### 17.3. Pool Size Is Not `Flux` Parallelism

~~~text
100 HTTP requests
  each does flatMap(..., 10)
       |
  up to ~1,000 inner subscriptions
       |
Reactive MongoDB Driver pool maxSize=100/server
       |
  queued/checked-out operations
       |
MongoDB server CPU/IOPS
~~~

These numbers are illustrative; actual scheduling depends on `flatMap` and driver behavior. If command execution slows sharply under concurrency, blindly inflating pool size worsens tail latency. Cap concurrency/admission and optimize queries instead.

### 17.4. Client Lifecycle in Reactive Stacks

Spring Boot's reactive MongoDB starter manages a shared reactive `MongoClient` bean. Never instantiate a new client per subscription:

~~~java
Mono.defer(() -> {
    // ANTI-PATTERN:
    // MongoClients.create(uri) on every subscription
    // -> spawns a new topology monitor and pool each time.
    return somePublisher;
});
~~~

Keep the client reusable and close it on shutdown. Separate clients for distinct clusters or workload bulkheads are fine when intentional, provided total connections across all pods stay within budget.

### 17.5. Netty Event-Loop Threads vs Driver Threads

WebFlux/Reactor Netty workers and the MongoDB Reactive Streams driver's I/O/callback threads may use different thread pools depending on version. **Never assume callbacks always execute on a Reactor Netty thread**—yet every callback thread is shared across requests, so blocking inside `map` or `doOnNext` still causes contention. Inspect thread names in traces when debugging without hardcoding thread assumptions into business logic.

### 17.6. Connection Storms During Deploys and Failovers

When 30 pods boot simultaneously, each with its own reactive `MongoClient` and a sizable `minPoolSize`, the cluster faces hundreds of concurrent TLS/auth handshakes. Mitigations:

- Rolling or canary deployments.
- Conservative `minPoolSize`.
- Deliberate `maxConnecting` tuning.
- Readiness warmup and paced startup.
- Capped retries with jitter during primary elections.
- Admission limits while MongoDB recovers.

Reactive programming **does not eliminate** SDAM server selection or pool clearing during primary failovers.

## 18. Logging, Tracing, and Reactor Context

### 18.1. Why `ThreadLocal`/MDC Drops Across Operators

~~~java
MDC.put("tenantId", tenantId);
return repo.findById(id)
    .publishOn(Schedulers.parallel())
    .doOnNext(order -> log.info("Found {}", order.getId()));
~~~

`MDC` relies on `ThreadLocal`; when Reactor hops threads, MDC can **lose `tenantId`** or leak stale values from prior requests unless properly propagated and cleared. Never base **authorization decisions** on `MDC` values.

### 18.2. Reactor Context

~~~java
Mono<Order> pipeline = repo.findById(id)
    .flatMap(order ->
        Mono.deferContextual(ctx -> {
            String tenant = ctx.get("tenantId");
            return auditRepo.save(
                new AuditEvent(tenant, order.getId()))
                .thenReturn(order);
        }))
    .contextWrite(ctx -> ctx.put("tenantId", tenantId));
~~~

`Reactor Context` travels with the **subscriber** rather than binding to a physical thread. Always derive `tenantId` from a **trusted authenticated context**; this snippet demonstrates metadata propagation, not complete authorization.

### 18.3. Spring Security Reactive Context

`ReactiveSecurityContextHolder.getContext()` exposes the `SecurityContext` reactively:

~~~java
Mono<String> trustedTenant = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(auth -> extractTenantFromValidatedPrincipal(auth));
~~~

Implement `extractTenantFromValidatedPrincipal` against your security model. **Never copy auth context into a static variable** or `ThreadLocal` hoping it survives reactive thread switches.

### 18.4. OpenTelemetry and Micrometer

In production, monitor:

- HTTP routes and request latency p50/p95/p99.
- Reactor event-loop lag and scheduler queue depths.
- MongoDB command durations, errors, and command names.
- Driver pool checked-out counts, wait times, and server selection failures.
- DB query plans, CPU, and IOPS.
- Retry, cancellation, and active subscription counters.

Correlate HTTP trace spans with MongoDB command spans. Never log raw BSON payloads containing PII or secrets, and keep high-cardinality IDs (`userId`, `requestId`) out of Prometheus metric labels.

### 18.5. Telemetry in `doOnEach` Must Not Block

~~~java
return repo.findById(id)
    .doOnEach(signal -> telemetry.observe(signal));
~~~

`telemetry.observe` must be fast, thread-safe, and non-blocking on event loops; observability SDKs export asynchronously via dedicated buffers and sampling. Never log full document bodies across million-record streams.

### 18.6. Detecting a Blocked Event Loop

Symptoms include:

- High Reactor Netty event-loop lag under normal load.
- Thread dumps showing `reactor-http-nio-*` parked in `WAITING` inside JDBC, sync MongoDB, blocking HTTP clients, or `Thread.sleep`.
- Rising HTTP p99 while MongoDB command latency remains low.
- High app CPU/GC caused by `collectList()` on massive results.
- BlockHound flagging blocking calls on non-blocking threads.

Fix the **blocking call or unbounded buffer** directly rather than reflexively increasing the MongoDB connection pool.

## 19. Testing Reactive Code: `StepVerifier` and `WebTestClient`

Reactive tests cover three main outcomes: **onNext**, **onComplete empty**, and **onError**, plus signal ordering, cancellation, concurrency, and ensuring zero eager side effects prior to subscription.

### 19.1. `StepVerifier` for a Succeeding `Mono`

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void monoEmitsOneValueThenCompletes() {
    Mono<String> source = Mono.just("OPEN");

    StepVerifier.create(source)
        .expectNext("OPEN")
        .verifyComplete();
}
~~~

`StepVerifier` handles **subscription** and asserts signals; avoid `.block()` in pure reactive unit tests.

### 19.2. Testing Empty / Missing Documents

~~~java
@Test
void missingOrderCompletesEmpty() {
    Mono<Order> lookup = Mono.empty();

    StepVerifier.create(lookup)
        .verifyComplete();
}
~~~

When a service converts empty into a domain error via `switchIfEmpty`:

~~~java
@Test
void missingOrderBecomesNotFoundError() {
    Mono<Order> lookup = Mono.<Order>empty()
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException("O-404")));

    StepVerifier.create(lookup)
        .expectError(OrderNotFoundException.class)
        .verify();
}
~~~

### 19.3. Testing Fallbacks Only for Appropriate Errors

~~~java
Mono<String> source = Mono.<String>error(
        new IllegalStateException("temporary"))
    .onErrorResume(IllegalStateException.class,
        ex -> Mono.just("FALLBACK"));

StepVerifier.create(source)
    .expectNext("FALLBACK")
    .verifyComplete();
~~~

Unit tests must distinguish **transient MongoDB errors** from validation, auth, or duplicate-key errors; never catch `Throwable` broadly to return a "success" fallback.

### 19.4. Verifying Zero Eager Side Effects Before Subscription

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> source = Mono.defer(() -> {
    calls.incrementAndGet();
    return Mono.just(42);
});

assertEquals(0, calls.get());

StepVerifier.create(source)
    .expectNext(42)
    .verifyComplete();

assertEquals(1, calls.get());
~~~

This catches mistakes like `Mono.just(legacyDao.load())` running blocking work **before subscription**.

### 19.5. `StepVerifier.withVirtualTime`

~~~java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(1)))
    .expectSubscription()
    .thenAwait(Duration.ofHours(1))
    .expectNext(0L)
    .verifyComplete();
~~~

Virtual time tests **Reactor timers/delays** and pure operator logic; it does not virtualize MongoDB network I/O. Never claim virtual-time unit tests prove real server query speed.

### 19.6. Mocking Reactive Repositories

~~~java
when(repo.findByTenantIdAndId("tenant-a", "O-100"))
    .thenReturn(Mono.just(orderFixture));

Mono<Order> result = service.get("tenant-a", "O-100");

StepVerifier.create(result)
    .expectNext(orderFixture)
    .verifyComplete();
~~~

This JUnit/Mockito snippet assumes `repo`, `service`, and `orderFixture` are initialized. Mocks verify **composition and control flow**, not BSON query mapping, indexes, or server failover behavior.

### 19.7. `WebTestClient` for Controllers

~~~java
webTestClient.get()
    .uri("/api/orders/{id}", "O-100")
    .header("X-Verified-Tenant", "tenant-a")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo("O-100");
~~~

This WebFlux controller test mocks an already **gateway-validated header policy**—never trust client-sent tenant headers in production. For HTTP 404:

~~~java
webTestClient.get()
    .uri("/api/orders/{id}", "O-missing")
    .header("X-Verified-Tenant", "tenant-a")
    .exchange()
    .expectStatus().isNotFound();
~~~

### 19.8. MongoDB Integration Tests

Mocks cannot verify:

- Actual MongoDB JSON queries and `Criteria`.
- Mapping of `@Document`, `@Field`, and `@Version`.
- Unique/compound indexes and optimistic locking.
- Multi-document transactions.
- Change streams and capped collections.
- Driver pooling, read preferences, and timeouts.

Run integration tests against a **Testcontainers MongoDB replica set** or a dedicated test Atlas cluster matching your target version, with isolated fixtures, cleanups, and zero production connections. Check Testcontainers module/API docs for your exact version's replica-set configuration.

### 19.9. Testing Transaction Atomicity

In a replica-set lab integration test:

1. Write an order and an audit event inside the same `TransactionalOperator` scope.
2. Inject a failure **after the first write and before completion/commit**.
3. Verify the publisher emits the error.
4. Query the database from outside to confirm both writes rolled back.
5. Test retries and ambiguous commit handling separately rather than relying on one forced-exception test.

A local standalone MongoDB lacks transaction support, causing tests to fail due to topology rather than reactive code.

### 19.10. Testing Detection of Blocking Behavior

Where BlockHound supports your JDK and Reactor versions, enable it in a test suite and run a known blocking anti-pattern to prove detection works. Combine with:

- Thread dumps under peak load.
- Event-loop latency metrics.
- CPU and GC profiles.
- Load tests matching realistic client concurrency and query shapes.

**Never equate "no exception thrown" with "non-blocking"**: many blocking calls emit no `IllegalStateException` if executed outside marked non-blocking threads.

## 20. Optimizing Reactive MongoDB Performance: Where Is the Bottleneck?

### 20.1. Break Down Latency by Stage

~~~text
HTTP request accepted
     |
     v
Auth/validation/context extraction
     |
     v
Reactive pipeline subscription
     |
     v
Driver server selection / pool checkout
     |
     v
MongoDB server executes command
     |
     v
Publisher emits BSON / Spring mapping
     |
     v
JSON encoder / HTTP send
     |
     v
Client receives response
~~~

Never assume "5 ms DB command p95 means 5 ms HTTP p95": queuing, cancellations, mapping CPU, JSON serialization, network RTT, scheduler saturation, and driver pool waits all contribute.

### 20.2. Little's Law and Concurrency

In a reasonably steady system:

\[
L = \lambda W
\]

At 800 MongoDB operations/s averaging 25 ms **from pool checkout to check-in**:

\[
L \approx 800 \times 0.025 = 20
\]

On average ~20 operations hold connections simultaneously. **Do not** set `maxPoolSize=20` literally: traffic bursts, p99 tails, retries, transactions, and pod counts all demand headroom. Reactive eliminates idle blocked threads—it **does not eliminate queueing theory**.

### 20.3. When the Database Is Saturated

If MongoDB CPU sits at 98%, IOPS is maxed out, and command p99 climbs while WebFlux event loops sit mostly idle, the bottleneck is the **DB**. Raising `flatMap` concurrency from 8 to 256 makes latency worse by deepening pool checkout and server queues. Instead:

- Tune indexes, queries, and projections.
- Throttle batch and reporting concurrency.
- Cache with explicit TTL, tenant isolation, and freshness policies.
- Denormalize or materialize summaries where domain-appropriate.
- Shard or scale database capacity when sustained demand exceeds hardware.

### 20.4. When the Event Loop Is Blocked

If MongoDB command p95 is low while HTTP p95 balloons and thread dumps reveal JDBC, `Thread.sleep`, or massive JSON parsing on event-loop threads:

- Swap blocking libraries for async/reactive alternatives.
- Offload unavoidable legacy calls via `fromCallable + subscribeOn` with caps.
- Isolate heavy CPU steps.
- Bound buffers and concurrency.
- Monitor event-loop lag.

**Never enlarge the MongoDB connection pool** to fix a stalled event loop.

### 20.5. When Pool Checkout Wait Is High

If driver checked-out connections hover near `maxPoolSize` while DB CPU remains low, inspect:

- Long-lived cursors or transactions.
- Excessive concurrent `flatMap` fanout.
- Slow `maxConnecting` ramp-up after cold starts or failovers.
- Connection churn, TLS handshakes, or re-authentication.
- Total `MongoClient` instances and pod count.

If the server has clear headroom, try cautiously stepping up pool size **alongside admission limits** and measuring p95/p99—never remove limits altogether.

### 20.6. Avoiding N+1 Queries

~~~java
return customerRepo.findByTenantId(tenantId)
    .flatMap(c ->
        orderRepo.findByTenantIdAndCustomerId(tenantId, c.getId())
            .collectList()
            .map(orders -> new CustomerWithOrders(c, orders)),
        16);
~~~

This is an N+1 pattern: 1 customer query plus N order queries. For large N, network and DB overhead soar. Replace with batched `$in` lookups, targeted `$lookup` aggregations, materialized views, or embedded document models aligned with access patterns. `flatMap(..., 16)` only limits peak concurrency; it **does not reduce the N queries**.

### 20.7. Reactive Memory Traps

| Operator / Code | Risk |
|---|---|
| `findAll().collectList()` | Buffers an entire collection in RAM. |
| `buffer(Integer.MAX_VALUE)` | Effectively unbounded memory accumulation. |
| `groupBy` on high-cardinality keys | Spawns excessive groups and memory overhead. |
| `cache()` on infinite/large `Flux` | Retains emitted items indefinitely, risking OOM. |
| `replay().autoConnect()` on event streams | Holds large history unless size/time bounded. |
| High `flatMap` concurrency | Accumulates pending DB operations and buffers. |
| JSON-encoding huge items | Heap and network frame spikes. |

**Non-blocking I/O** and **bounded memory** are orthogonal goals. Reactive code can easily satisfy the first while violating the second.

### 20.8. Connection Pools Across Apps and Pods

Suppose 24 pods each hold a reactive `MongoClient` with `maxPoolSize=80` targeting the primary:

\[
24 \times 80 = 1{,}920
\]

That represents the **potential pooled connection ceiling** against the primary, not constant active usage. Multiple clients per pod multiply it further, and HPA pod autoscaling can overwhelm the DB even when each pod's event loop looks lightly loaded.

### 20.9. Adaptive Admission and Overload Shedding

An API with a 300 ms p95 SLO should reject multi-second pool queues. Consider explicit budgets:

~~~text
API per-pod in-flight MongoDB operations: 40
HTTP queue capacity: 80
Admission wait: at most 30ms
MongoDB operation timeout: based on remaining deadline
Reports: separate gate and async jobs
~~~

These are **illustrative figures**—calibrate via load tests. When saturated, return HTTP 429/503 or degrade gracefully rather than letting requests pile up indefinitely inside pools. Even async reactive tasks consume RAM, context, and DB slots.

### 20.10. Load Testing Both Overload and Recovery

A thorough load test steps up arrival rates and measures:

1. Incoming vs completed throughput.
2. HTTP p50/p95/p99 latency.
3. DB command p50/p95/p99 and pool checkout waits.
4. Event-loop lag, app CPU/GC/heap, scheduler queues.
5. Error, timeout, retry, and rejection rates.
6. Queue drain behavior as traffic drops.
7. Failover reconnection and stream resume behavior.

**A well-engineered reactive service does not just chase peak QPS on a toy benchmark**; it delivers **sustainable throughput, predictable latency, and clean failure handling** when MongoDB or downstreams slow down.

## 21. Security, Resource Lifecycle, and Testing Edge Cases

### 21.1. Trusted Tenant Context

In WebFlux, user and tenant identity live in Reactor's `SecurityContext`. Filter every query using **validated principals and permissions**, never unverified client IDs:

~~~java
return trustedTenant()
    .flatMap(tenantId -> repository.findByTenantIdAndId(
        tenantId, orderId));
~~~

Never stash tenant context in a mutable singleton or `ThreadLocal` across reactive thread switches—contexts can leak between users. `ReactiveMongoRepository.findById(id)` offers no built-in tenant isolation.

### 21.2. Controller-Only Checks Are Insufficient

Validating tenant only in a controller while a service calls raw `repository.findById` leaves a gap if another caller invokes that service directly. Enforce tenant scoping at the **data-access/service boundary** and cover cross-tenant access attempts plus background jobs in integration tests.

### 21.3. Mapping and Field-Level Access Control

Projections are not ACLs. Returning a full `Order` entity can expose internal notes or payment tokens. Always return response DTOs or explicit projections instead of serializing raw domain documents. For encryption/CSFLE, verify reactive driver compatibility and avoid blocking key resolvers on event-loop threads.

### 21.4. Resource Lifecycle

A reactive `MongoClient` is a long-lived shared resource; never create and close it per request or subscription. Manage cancellation and disposal for change streams and cursors. Every background subscription needs clear ownership, error handling, and shutdown cleanup.

### 21.5. HTTP Disconnects Mid-Write

Canceling a subscription on client disconnect does not imply a dispatched DB write rolled back. Never treat cancel signals as **database rollback**. Support stable idempotency keys and state lookup endpoints for safe client retries.

### 21.6. Operational Readiness

Readiness and liveness probes must distinguish **brief MongoDB primary elections** from a **dead JVM**. If a short election causes Kubernetes to kill-restart all WebFlux pods simultaneously, the synchronized reboot creates a far worse connection storm. Configure separately:

- Liveness: process health only.
- Readiness: ability to serve current traffic.
- Dependency/SDAM health: connectivity and eligible server visibility.
- Graceful shutdown: drain active requests and close clients/cursors cleanly.

### 21.7. Logging and PII

Never log raw MongoDB connection strings with credentials, sensitive BSON fields, auth headers, or unneeded resume tokens. Keep trace/metric labels low-cardinality (`route`, `commandName`, `operationClass`, `outcome`, `cluster`); keep high-cardinality `requestId` in trace contexts/logs with retention controls, never in Prometheus labels.

### 21.8. Testing Race Conditions

`Mono.zip(read1, read2)` reads at independent timestamps; `findById(...).flatMap(save)` is vulnerable to concurrent write races; `@Version` catches stale saves on supported paths yet does not replace **atomic conditional updates** or transactions. Write integration tests covering concurrent writes, duplicate keys, optimistic lock failures, and client disconnects/retries.

## 22. Common Misconceptions and Pitfalls

| Misconception / Anti-Pattern | Why It Is Wrong | Better Practice |
|---|---|---|
| "Returning `Mono` makes calling `MongoTemplate` non-blocking." | Sync I/O still blocks the worker thread. | Use `ReactiveMongoTemplate` / reactive repositories. |
| "`Mono.just(blockingCall())` defers execution to subscription." | Arguments evaluate eagerly when constructing the `Mono`. | Use `fromCallable + subscribeOn(boundedElastic)`. |
| "`Mono.defer(blockingCall)` is automatically non-blocking." | It only defers; it still blocks the subscribing thread unless offloaded. | Use an appropriate scheduler with bounded admission. |
| "`block()` is required in a controller to execute queries." | WebFlux subscribes automatically when controllers return publishers. | Return `Mono`/`Flux`. |
| "Manual `subscribe()` is great for fire-and-forget." | Errors miss the HTTP response and break lifecycle/transactions. | Compose and return; background work needs an owner/durable queue. |
| "`doOnNext` is where to run a second DB write." | Async side effects do not compose and ignore errors/backpressure. | Chain via `flatMap` returning a `Mono`, using tx/outbox if needed. |
| "Reactive makes MongoDB queries execute faster." | Server indexes, CPU, and IOPS costs stay identical. | Run `explain` and tune queries and schema. |
| "`Flux` fetches only 1 document per DB round trip." | Drivers use cursor batches and operators prefetch. | Tune limits, batch sizes, and demand metrics. |
| "`findAll().collectList()` keeps memory bounded." | Materializes every document into heap RAM. | Filter, limit, paginate, or stream. |
| "`flatMap(repo::save)` with unbounded concurrency is fastest." | Saturates pools/servers and reorders writes. | Cap concurrency or use `concatMap`. |
| "`flatMap(...,8)` sets a global DB concurrency limit." | Applies per subscription/pipeline only. | Add global/per-tenant admission and pod budgets. |
| "`Schedulers.boundedElastic` makes blocking calls infinitely safe." | Queues still back up and cause timeouts/heap pressure. | Cap tasks/concurrency, set deadlines, migrate to async. |
| "`publishOn` after a blocking mapper fixes the mapper." | `publishOn` only switches threads for downstream stages. | Use `subscribeOn` for blocking sources or place `publishOn` before the step. |
| "`Schedulers.parallel` is meant for blocking JDBC." | It is sized for CPU work with few threads. | Use `boundedElastic` for blocking, or R2DBC/reactive APIs. |
| "WebFlux event-loop count equals MongoDB pool size." | Completely separate resource pools. | Monitor driver CMAP metrics and event-loop lag separately. |
| "Reactive `findById` validates tenant ownership." | ID lookups carry no implicit tenant filter. | Include tenant from security context in every query. |
| "Client-sent tenant HTTP headers are trustworthy." | Clients can spoof headers trivially. | Read verified principals from reactive `SecurityContext`. |
| "`@Transactional` on a `void` method using `subscribe()` works." | Reactive transactions follow returned publisher subscriptions/proxies. | Return the publisher and wire reactive tx manager. |
| "Adding `@Transactional` alone guarantees atomicity." | Requires `ReactiveMongoTransactionManager`, shared factory, and replica set. | Verify configuration and test rollback on a replica set. |
| "`flatMap` of 100 writes inside one transaction is always safe." | Concurrent ops on one `ClientSession` are unsupported. | Compose sequentially with `concatMap`. |
| "Reactive transactions bind via `ThreadLocal`." | They bind through the Reactor subscriber Context. | Rely on Spring reactive manager/context integration. |
| "`Mono.zip` reads share a snapshot." | It composes parallel calls without snapshots/transactions. | Use transactions/read concerns if cross-read consistency is required. |
| "`save(entity)` patches only modified fields." | Replaces/updates entity state per mapping and `@Version`. | Use atomic `updateFirst`/`findAndModify` for field updates. |
| "`@Version` protects custom `updateMulti` automatically." | Custom updates follow different paths from entity saves. | Include explicit version predicates and updates. |
| "`onErrorReturn(0)` is a safe fallback everywhere." | Turns timeouts into plausible-looking business zeros. | Propagate errors or surface verified degraded states. |
| "`retryWhen` on every exception is safe." | Retries validation/auth/duplicate errors or duplicates writes. | Filter transient errors, cap attempts, use stable IDs. |
| "`Mono.timeout` rolls back canceled DB writes." | The server may have already committed. | Use idempotency keys and verify outcomes. |
| "`StepVerifier.withVirtualTime` benchmarks MongoDB I/O." | Only virtualizes Reactor scheduler clocks, not network DBs. | Run real integration and load tests. |
| "`@Tailable` works on normal collections." | Tailable cursors require capped collections. | Use capped collections or change streams. |
| "Change streams guarantee infinite replay." | Bounded by oplog history and resume windows. | Persist checkpoints and use durable brokers where needed. |
| "Change stream callbacks are automatically exactly-once." | Crashing before checkpointing replays events. | Build idempotent consumers. |
| "Zero BlockHound errors proves 100% non-blocking code." | Instrumentation coverage and allowlists have gaps. | Verify with metrics, thread dumps, and load tests. |
| "Returning `Flux` always streams through every proxy." | Proxies and clients may still buffer responses. | Verify codecs, proxies, and NDJSON end-to-end. |
| "Reactive drivers eliminate connection pools." | Per-server pools, checkout, and SDAM still govern connections. | Monitor CMAP, pools, and server health. |
| "Scaling pods via HPA automatically scales DB capacity." | Increases connection/query load without adding DB CPU/IOPS. | Enforce global admission and scale MongoDB separately. |
| "`@Document`/`@CompoundIndex` always builds indexes automatically." | Governed by auto-index settings and migration policies. | Manage and verify indexes explicitly. |
| "Projections can safely be saved back as full entities." | Unloaded fields become null/default and risk overwriting data. | Project into DTOs; never save partial projections. |

### 22.1. Five Questions to Ask During a Reactive PR Review

1. Does any controller or service call `.block()`, `.subscribe()`, or `Thread.sleep()`?
2. Is any **blocking** library hidden inside `map`, `doOnNext`, mappers, or validators?
3. Are `flatMap` concurrency, page sizes, and buffer memory explicitly bounded?
4. Are reactive transactions, tenant security contexts, errors, and retries **composed** cleanly?
5. Do integration tests and metrics prove the event loop stays unblocked, cursors do not leak, and the DB is protected from overload?

## 23. Real-World Scenarios: Picking the Right Fix

### 23.1. Case A — High WebFlux API p99 Despite Fast MongoDB

~~~text
HTTP p99:          1,400 ms
MongoDB command:      15 ms
Driver checkout:       3 ms
Event-loop lag:      900 ms
Thread dump:
  reactor-http-nio-X -> Thread.sleep(...)
~~~

Figures are illustrative. The bottleneck is **event-loop blocking**, not MongoDB queries or pools. Replace `Thread.sleep` with timer publishers, remove blocking SDKs or offload with bounded caps. Increasing `maxPoolSize` will not unblock the event loop.

### 23.2. Case B — `flatMap` Reading 10,000 IDs Saturates the DB

~~~text
One HTTP request:
  10,000 IDs -> flatMap(repo.findById)
  many concurrent DB operations

Driver checkout wait p99: 500 ms
MongoDB CPU:            98%
HTTP requests timeout/retry
~~~

**Remediation:**

1. Enforce input list caps and tenant/ACL checks.
2. Batch IDs with bounded `$in` queries or redesign access patterns.
3. Cap `flatMap(..., n)` based on measurement.
4. Enforce bounded admission and tight HTTP deadlines.
5. Optimize MongoDB indexes around actual query shapes.
6. Never multiply `maxPoolSize` by 10 while DB CPU sits at 98%.

### 23.3. Case C — Controller Returns "Saved" Yet DB Has No Document

~~~java
public Mono<String> saveBad(Order o) {
    repository.save(o).subscribe();
    return Mono.just("Saved");
}
~~~

If the write hits a duplicate-key error or election failure, HTTP already returned success. **Fix:**

~~~java
public Mono<Order> saveGood(Order o) {
    return repository.save(o);
}
~~~

WebFlux drives the subscription and routes errors properly to the HTTP response. Keep stable idempotency keys for client retries.

### 23.4. Case D — Transaction Fails to Roll Back Two Writes

~~~java
@Transactional
public Mono<Void> bad(Order order) {
    repo.save(order).subscribe();
    auditRepo.save(new AuditEvent(order.getId(), "NEW")).subscribe();
    return Mono.empty();
}
~~~

Two manual `subscribe()` calls spawn detached subscriptions outside the returned publisher's transaction scope. **Fix:**

~~~java
@Transactional
public Mono<Void> good(Order order) {
    return repo.save(order)
        .flatMap(saved ->
            auditRepo.save(
                new AuditEvent(saved.getId(), "NEW")))
        .then();
}
~~~

Pair with `ReactiveMongoTransactionManager`, replica-set/sharded topology, and a real rollback integration test.

### 23.5. Case E — `Mono.zip` Completes Unexpectedly Empty

~~~java
Mono<Order> order = repo.findById("missing");
Mono<Long> count = repo.count();
return Mono.zip(order, count);
~~~

When `order` emits empty, `zip` completes empty and cancels the sibling branch. **Fix per business semantics:**

~~~java
return repo.findById("missing")
    .switchIfEmpty(Mono.error(new OrderNotFoundException("missing")))
    .flatMap(order -> repo.count()
        .map(count -> new OrderAndCount(order, count)));
~~~

If you intentionally still want a count when the order is missing (e.g., analytics), design that flow explicitly rather than expecting `zip` to emit a partial tuple with `null`.

### 23.6. Case F — Change Stream Disconnects and Replays Duplicate Events

~~~text
Consume event E101
Apply projection in S3
Crash before resume-token checkpoint
Restart from E100
Receive E101 again
~~~

This represents **at-least-once** delivery. Deduplicate projections using event IDs/resume tokens and checkpoint only after side effects persist; cross-system exactly-once requires protocol/transactional design rather than Reactor operators alone.

### 23.7. Case G — High Memory Usage Despite Idle Threads

~~~java
Mono<List<Order>> response = repo.findAll().collectList();
~~~

Across millions of orders, heap usage balloons quickly. **Fix** with indexed tenant filters, `Pageable`/seek pagination, DTO projections, and response-size caps. Being "reactive" does not make storing millions of objects in a `List` free.

### 23.8. Case H — Blocking Payment SDK Inside `map`

~~~java
return repo.findById(orderId)
    .map(order -> paymentSdk.charge(order)); // blocking call
~~~

Blocking SDKs stall event-loop or driver callback threads. Appending `.publishOn(boundedElastic())` **after** `map` does not help. Prefer an async payment SDK; if unavailable:

~~~java
return repo.findById(orderId)
    .flatMap(order ->
        Mono.fromCallable(() -> paymentSdk.charge(order))
            .subscribeOn(Schedulers.boundedElastic()));
~~~

**Important:** charging payments is non-idempotent. Require a payment-provider idempotency key, configure dedicated timeouts/retries, and never blindly retry the outer `Mono`.

### 23.9. Case I — Reactive Repository Inside Spring MVC

Spring MVC and WebFlux are distinct models. While Spring MVC supports returning reactive types under certain configurations, **Servlet request handling does not magically become a full WebFlux event-loop runtime** merely by injecting a reactive DAO. Conversely, WebFlux apps calling JDBC still block. Choose your stack intentionally and verify Boot's precedence when both `spring-boot-starter-web` and `spring-boot-starter-webflux` sit on the classpath.

### 23.10. Case J — Mixing Imperative and Reactive Transaction Managers

An app registering both `MongoTransactionManager` and `ReactiveMongoTransactionManager` (or a JDBC manager) risks `@Transactional` resolving the wrong manager and failing to attach reactive `ClientSession`s to the Reactor Context. Specify bean names/qualifiers explicitly, test end-to-end, and never assume "@Transactional on the method" guarantees atomicity.

### 23.11. Case K — Retry Storm After Primary Election

When a new primary is elected and the driver performs SDAM reconnection, 20 pods firing un-jittered `retryWhen` loops simultaneously hammer the new primary. Use capped retries, exponential backoff with jitter, global admission control, and separate read vs write idempotency rules.

### 23.12. Case L — Misdiagnosing Bottlenecks by Reading the Wrong Metric

~~~text
HTTP p99 = 1,000ms
MongoDB command p99 = 30ms
Pool checkout wait p99 = 500ms
Event-loop lag p99 = 10ms
~~~

Figures are illustrative. Pressure is overwhelmingly in **pool checkout/concurrency**, not event-loop blocking. Check checked-out vs `maxPoolSize`, `maxConnecting`, long-running cursors/transactions, connection churn, server headroom, and client/pod counts before cautiously raising pool limits.

## 24. Practice Exercises and Solutions

Each exercise stands alone; sample snippets use reactive Spring Data MongoDB + Reactor without claiming live cluster execution. Transaction and change-stream exercises require an authorized replica set or sharded lab. Verify exact Spring Boot, Spring Data, Reactor, driver, and security configurations before applying in production.

### Exercise 1 — What Is a Reactive Repository?

**Prompt:** Compare `MongoRepository<Order,String>` and `ReactiveMongoRepository<Order,String>`.

**Solution:** `MongoRepository` is an imperative CRUD abstraction returning entities/collections synchronously. `ReactiveMongoRepository` returns **reactive publishers** (`Mono`/`Flux`), runs on the MongoDB Reactive Streams driver, and executes pipelines only upon subscription. Swapping the interface does not automatically make surrounding blocking code non-blocking.

### Exercise 2 — `Mono` vs `Flux`

**Prompt:** Which return type suits fetching one order by ID? Which suits fetching a tenant's orders?

**Solution:** `Mono<Order>` for 0 or 1 item; `Flux<Order>` for multiple items. Endpoints returning `Flux` must apply tenant filtering, pagination/`limit`, or bounded streaming rather than dumping an entire collection unbounded.

### Exercise 3 — Empty vs Error

**Prompt:** `repo.findById("missing")` finds no document. Does it emit `MongoException` by default?

**Solution:** Normally no: it returns `Mono.empty()`, completing with `onComplete`. Controllers convert empty into 404 via `defaultIfEmpty(ResponseEntity.notFound().build())` or `switchIfEmpty(Mono.error(...))` when business rules require an error.

### Exercise 4 — Cold Publishers

**Prompt:** You invoke `Mono<Order> m = repo.save(order);` without subscribing or returning it to WebFlux. Has the write executed?

**Solution:** Repository publishers are typically **cold**; without subscription, no I/O happens. Return `m` to WebFlux or assign a clear lifecycle subscriber—never call `m.block()` just to kick off work in a request handler.

### Exercise 5 — Two Subscriptions

**Prompt:** `Mono<Order> m = repo.save(order); m.subscribe(); m.subscribe();`. Does this guarantee exactly-once writes?

**Solution:** No. Two subscriptions trigger two execution attempts; depending on stable `_id` and entity state, the second may overwrite or fail with a version conflict, yet this is never "exactly-once". Avoid duplicate manual subscriptions and enforce idempotency keys.

### Exercise 6 — `map` or `flatMap`?

**Prompt:** What type does `repo.findById(id).map(repo::save)` produce and how should it be fixed?

**Solution:** It creates a nested `Mono<Mono<Order>>`. Use `flatMap(repo::save)` to flatten the inner publisher, reserving `map` strictly for synchronous DTO/value transformations.

### Exercise 7 — `Mono.just(blocking())`

**Prompt:** Does `Mono.just(legacyDao.load())` defer blocking I/O until subscription?

**Solution:** No. Java evaluates `legacyDao.load()` eagerly before passing the result into `just`. Wrap legacy blocking APIs with `Mono.fromCallable(legacyDao::load).subscribeOn(Schedulers.boundedElastic())`.

### Exercise 8 — Is `Mono.defer` Automatically Non-Blocking?

**Prompt:** Is `Mono.defer(() -> Mono.just(legacyDao.load()))` safe to run on an event loop?

**Solution:** Not by itself. Evaluation is deferred until subscription, yet it still blocks whichever thread subscribes. Offload onto an appropriate scheduler with concurrency/queue caps, or switch to a native reactive DAO.

### Exercise 9 — `block()` in WebFlux

**Prompt:** A controller returns `Order` by calling `repo.findById(id).block()`. What happens?

**Solution:** It can throw `IllegalStateException` on Reactor non-blocking threads or stall the event loop, degrading throughput and p99 latency. Return `Mono<Order>` or `Mono<ResponseEntity<Order>>` so WebFlux drives subscription.

### Exercise 10 — `Thread.sleep`

**Prompt:** Inside `map`, code calls `Thread.sleep(500)`. How should a response delay be written properly?

**Solution:** Use `delayElement(Duration.ofMillis(500))` or `Mono.delay` so event-loop threads never sleep. For retry backoff, use `Retry.backoff` scoped to transient errors rather than delaying normal requests.

### Exercise 11 — `subscribe()` Inside a Controller

**Prompt:** A controller invokes `repo.save(o).subscribe()` and returns `Mono.just("OK")`. Why is this dangerous?

**Solution:** It returns OK before the DB write finishes; write failures never propagate to HTTP, and cancellation/transaction scopes are lost. Return `repo.save(o)` and map the HTTP response upon completion.

### Exercise 12 — Derived Query

**Prompt:** Write a repository method fetching a tenant's orders in `OPEN` status.

**Solution:**

~~~java
Flux<Order> findByTenantIdAndStatus(
    String tenantId, String status);
~~~

Obtain `tenantId` from the authenticated principal/server-side authorization, never trusting raw client parameters.

### Exercise 13 — `@Query` Annotation

**Prompt:** How do you filter status dynamically without concatenating user input into raw JSON?

**Solution:** Use `@Query("{ 'tenantId': ?0, 'status': ?1 }")` or `Query`/`Criteria` parameter binding so Spring Data binds values safely. Retain the tenant filter and verify index alignment.

### Exercise 14 — `ReactiveMongoTemplate.findOne`

**Prompt:** Write a query filtering by tenant and order ID.

**Solution:**

~~~java
Query q = query(where("tenantId").is(tenantId)
    .and("_id").is(orderId));
Mono<Order> result = template.findOne(q, Order.class);
~~~

Emits `Mono.empty()` when absent without calling `block()`.

### Exercise 15 — Atomic State Transition

**Prompt:** Two concurrent requests attempt to transition an order from `OPEN` to `PAID`. Should you use `findById -> setStatus -> save` or a conditional update?

**Solution:** Prefer an **atomic conditional update**:

~~~java
Query q = query(where("_id").is(id)
    .and("tenantId").is(tenantId)
    .and("status").is("OPEN"));
Mono<UpdateResult> result = template.updateFirst(
    q, new Update().set("status", "PAID"), Order.class);
~~~

Inspect `matchedCount`; map zero matches to conflict or not-found per security policy. For multi-document/collection updates, use a transaction.

### Exercise 16 — Saving Partial Projections

**Prompt:** `template.find` projects only `_id` and `status` into `Order`, followed by `repo.save(order)`. What is the risk?

**Solution:** Unloaded fields default to `null`/zero and can overwrite persisted fields upon `save`. Project into a separate DTO type and never save partial entities; use `updateFirst` for targeted field updates.

### Exercise 17 — `@Version`

**Prompt:** Why place `@Version` on `Order`?

**Solution:** Enables optimistic locking across supported save/update paths to catch stale concurrent writes. Do not assume custom `updateMulti` queries check versions automatically; verify exception handling and integration tests.

### Exercise 18 — Reactive Pagination

**Prompt:** Can a derived reactive repository method return `Mono<Page<Order>>` just like imperative Spring Data?

**Solution:** Spring Data MongoDB reactive repository docs do not support returning `Mono<Page>` that way. Return `Flux<Order>` with `Pageable`, execute a separate `Mono<Long>` count query if totals are required, and combine into a DTO—keeping in mind list and count are not automatically from one snapshot.

### Exercise 19 — Unbounded `findAll`

**Prompt:** Is `repo.findAll().collectList()` across 2 million documents safe because it is reactive?

**Solution:** No. Despite non-blocking I/O, `collectList` buffers all 2 million documents on the JVM heap, risking OOM crashes and GC storms. Apply filters, limits, pagination, streaming, and DTO projections.

### Exercise 20 — `flatMap` Concurrency

**Prompt:** `Flux.fromIterable(ids).flatMap(repo::findById, 8)` runs across 100 concurrent requests. Is global DB concurrency capped at 8?

**Solution:** No. `8` caps inner subscriptions **per pipeline instance**; 100 concurrent requests can produce ~800 in-flight queries alongside other endpoints. Enforce global/per-tenant admission and cluster capacity budgets.

### Exercise 21 — `concatMap`

**Prompt:** A batch must persist order B before creating order C, which depends on B's state. Should you use `flatMap(repo::save, 32)`?

**Solution:** No when writes depend on sequential order. Use `concatMap(repo::save)` or explicit sequential composition. `flatMapSequential` only reorders **emissions**, still allowing concurrent execution of inner operations.

### Exercise 22 — `buffer`

**Prompt:** Does `repo.findAll().buffer(100).collectList()` cap memory at 100 objects?

**Solution:** No. `buffer(100)` groups items into batches of 100, and `collectList()` then collects **all batches** into one master `List`. Unbounded streams hang forever and large collections risk OOM.

### Exercise 23 — `Schedulers.boundedElastic`

**Prompt:** Once a blocking JDBC call is wrapped in `boundedElastic`, can the service safely accept 100,000 concurrent tasks with no admission gate?

**Solution:** No. `boundedElastic` caps worker threads yet maintains a **task queue**, leading to queue buildup, timeouts, and heap exhaustion. Enforce admission caps and deadlines, and prefer R2DBC/async SDKs where feasible.

### Exercise 24 — Misplaced `publishOn`

**Prompt:**

~~~java
repo.findById(id)
    .map(o -> legacyBlockingCall(o))
    .publishOn(Schedulers.boundedElastic());
~~~

Does `publishOn` move the blocking mapper off the event loop?

**Solution:** No. `publishOn` affects only **downstream** operators; the preceding `map` still executes on the upstream thread. Place the scheduler shift **before** the blocking work or use `flatMap(o -> Mono.fromCallable(...).subscribeOn(boundedElastic()))` with concurrency caps.

### Exercise 25 — `Mono.zip` and Empty

**Prompt:** Does `Mono.zip(repo.findById("missing"), repo.count())` emit a tuple with `null` for the missing order?

**Solution:** No. When either `Mono` completes empty, `zip` **completes empty** and cancels the sibling—no `null` element is emitted. Use `switchIfEmpty` or restructure with `flatMap` per business requirements.

### Exercise 26 — `Mono.zip` and Consistency

**Prompt:** Two read publishers sit inside `Mono.zip`. Do they read at a single MongoDB snapshot timestamp?

**Solution:** No. `zip` composes concurrent operations without creating a transaction or snapshot. When cross-read consistency is required, use appropriate read concerns/transactions while factoring in server overhead.

### Exercise 27 — Reactive Transaction Manager

**Prompt:** A project places `@Transactional` on a method returning `Mono<Void>` without registering `ReactiveMongoTransactionManager`. Are two MongoDB writes guaranteed atomic?

**Solution:** No. Reactive MongoDB transactions require the matching manager/factory, supported replica-set/sharded topology, Spring AOP proxy invocation, and proper subscription composition. Verify rollback on a lab replica set.

### Exercise 28 — Manual Subscription Inside a Transaction

**Prompt:** Inside a `@Transactional` method, a service calls `repo.save(o).subscribe()` and returns `Mono.empty()`. Does the write join the transaction?

**Solution:** No. Manual `subscribe()` detaches the write from the returned publisher and Reactor Context managed by the transaction interceptor. Compose and return the chain without self-subscribing.

### Exercise 29 — Parallel Operations on the Same Session

**Prompt:** `flatMap(..., 64)` executes 64 updates inside one reactive transaction/session. Is this always safe?

**Solution:** No. MongoDB `ClientSession`/transactions do not permit arbitrary concurrent operations on the same session. Compose sequentially with `concatMap` and keep transactions short.

### Exercise 30 — Transaction + Payment Gateway

**Prompt:** A transaction callback invokes a payment SDK to charge a card, then retries after a transient MongoDB error. What is the risk?

**Solution:** The customer may be **charged multiple times**. Never execute non-idempotent external side effects inside retryable transaction callbacks unprotected; use payment-provider idempotency keys, transactional outboxes, and reconciliation.

### Exercise 31 — Change Streams

**Prompt:** Opening `template.changeStream` against a local standalone MongoDB—will it behave like a replica set?

**Solution:** No. MongoDB change streams require a **replica set or sharded cluster**; standalone servers do not provide change stream semantics. Test against a replica set lab.

### Exercise 32 — `@Tailable`

**Prompt:** `@Tailable Flux<Log> findByLevel(...)` targets a regular collection. Are prerequisites met?

**Solution:** No. Tailable cursors require a **capped collection**. For change events on standard collections, use change streams with lifecycle and resume-token management.

### Exercise 33 — Resume Tokens and Checkpoints

**Prompt:** A consumer applies side effect E101 and crashes before persisting the resume-token checkpoint. Can it receive E101 again on restart?

**Solution:** Yes—replay will occur. Build idempotent consumers deduplicating by stable event ID and persist checkpoints **after durable side-effect completion**. `Flux` does not grant cross-system exactly-once delivery.

### Exercise 34 — HTTP Client Disconnect

**Prompt:** A client cancels a POST request after 200 ms, though MongoDB already received the insert. Does subscription cancellation roll back the insert?

**Solution:** No. Client-side cancellation/timeout **never proves the server write aborted**. Use stable idempotency keys, status verification endpoints, and retryable-write semantics.

### Exercise 35 — `onErrorReturn(0)`

**Prompt:** A revenue-total API returns `0` whenever MongoDB times out. Why is this unsafe?

**Solution:** Timeouts get disguised as plausible business data, driving flawed downstream decisions. Propagate the error or return an explicitly marked degraded state rather than fabricating zero.

### Exercise 36 — `StepVerifier.withVirtualTime`

**Prompt:** A virtual-time test for `Mono.delay(1h)` passes in milliseconds. Does that prove MongoDB `find` p99 stays under 10 ms?

**Solution:** No. Virtual time mocks Reactor's timer schedulers—it **does not** exercise MongoDB networking or server queries. Measure real performance with integration and load tests.

### Exercise 37 — `WebTestClient` and Security

**Prompt:** A controller trusts an arbitrary HTTP tenant header and filters queries with it; HTTP 200 tests pass. Is multi-tenant isolation secure?

**Solution:** No. Any client can forge that header to access another tenant's records. Extract tenant strictly from authenticated principals or gateway-verified contexts, and write negative cross-tenant tests.

### Exercise 38 — Low DB Command Latency, High HTTP Latency

**Prompt:** MongoDB command p99=12 ms, driver checkout=3 ms, HTTP p99=900 ms, event-loop lag=700 ms. Where do you investigate?

**Solution:** Symptoms point to **event-loop blocking, heavy CPU mapping/serialization, GC pauses, or app queuing**. Capture thread dumps, run BlockHound/traces, and eliminate blocking SDKs, `block()`, or unbounded buffers—enlarging the MongoDB pool will not help.

### Exercise 39 — DB CPU Near 100%, Reactive Threads Idle

**Prompt:** WebFlux event loops have plenty of headroom, while MongoDB CPU sits at 99% with 2 s query p99. Should you boost `flatMap` concurrency from 8 to 200?

**Solution:** Generally no. The database is saturated; adding concurrent queries deepens server queues and contention. Tune indexes/queries, throttle bulk jobs, enforce admission control, and scale database hardware if sustained load exceeds capacity.

### Exercise 40 — End-to-End Reactive Orders API Design

**Prompt:** Design an order-creation endpoint with tenant auth, MongoDB persistence, and an audit event, requiring non-blocking event loops, duplicate protection on retries, p95 under 300 ms, and safe production rollout. Detail design and verification.

**Suggested Solution:**

1. Use `spring-boot-starter-webflux` + `spring-boot-starter-data-mongodb-reactive` with BOM-managed versions.
2. Inject singleton reactive MongoDB beans; use `ReactiveMongoRepository` for CRUD and `ReactiveMongoTemplate` for atomic conditional updates and aggregations.
3. Resolve tenant exclusively from a **reactive authenticated principal**, never from spoofable headers.
4. Validate inputs, attach a stable `idempotencyKey`, and enforce a per-tenant unique index.
5. Return `Mono<Order>` from services with zero `block()` or manual `subscribe()` calls inside request paths.
6. If order + audit must be atomic, configure `ReactiveMongoTransactionManager`/`TransactionalOperator` and compose both writes **inside one sequential publisher**; verify rollback on a replica set.
7. Offload external side effects (Kafka, payments) via an outbox or idempotent async workers; never invoke blocking SDKs inside transactions.
8. Wrap unavoidable legacy blocking calls in `fromCallable(...).subscribeOn(boundedElastic())` **with concurrency caps**, planning async migration.
9. Bound in-flight MongoDB queries, request queues, and timeouts against the **remaining HTTP deadline**; apply capped jittered retries strictly to transient errors.
10. Verify via `StepVerifier`, `WebTestClient`, and replica-set MongoDB integration tests: success, 404, duplicate keys, transaction rollback, timeout/cancellation, and cross-tenant isolation.
11. Monitor HTTP p95/p99, event-loop lag, driver pool waits, and MongoDB command latency, CPU, IOPS, retries, and heap.
12. Roll out via canary and open-loop load testing with realistic query mixes, backed by a clear rollback gate if p99, error rates, or correctness regress.

Never pick magic constants like `flatMap=16` or `pool=100` out of habit; calibrate from **workload measurements, SLOs, and DB headroom**. Sound design keeps event loops unblocked while ensuring MongoDB and downstreams only receive work they can finish accurately within deadline.

## 25. Official References by Version

This guide covers general patterns and **does not replace official API documentation for your exact versions of Spring Data MongoDB, Reactor, and the MongoDB Java Reactive Streams Driver**. Links pointing to `current` evolve across new releases. Always cross-check compatibility across the Spring Boot BOM, Spring Data MongoDB, Reactor, Java driver, and MongoDB Server.

### 25.1. Spring Data MongoDB Reactive API

1. [Spring Data MongoDB — Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/) — overview of mapping, repositories, templates, sessions, transactions, and streaming.
2. [ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html) — `find`, `findOne`, `insert`, `save`, `updateFirst`, `findAndModify`, `aggregate`, and reactive overloads.
3. [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Criteria`, `Query`, projections, `cursorBatchSize`, sort, limit, and keyset/scroll patterns.
4. [Saving, Updating and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — updates/filters, `findAndModify`, `@Version`, and mapping.
5. [MongoDB-specific Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — derived methods, `@Query`, `Flux` + `Pageable`, and unsupported `Mono<Page>` note.
6. [Spring Data Repositories — Core Concepts](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html) — repository abstractions, reactive repository types, and lifecycle.
7. [Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking) — `@Version`, stale writes, and optimistic-lock exception semantics.
8. [Mapping Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — `@Document`, `@Id`, `@Field`, constructors, and entity conversion.

### 25.2. Transactions and Streaming

9. [Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `ReactiveMongoTransactionManager`, `TransactionalOperator`, Reactor Context, explicit `ClientSession`, and repository session caveats.
10. [Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html) — reactive `changeStream(...).listen()`, resume tokens, server time, and long-lived streams.
11. [Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html) — capped collections, `ReactiveMongoTemplate.tail`, and `@Tailable` repository methods.
12. [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — replica set/sharded prerequisites, transaction atomicity, and constraints.
13. [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — oplog/history/resume semantics and deployment requirements.
14. [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — query planning and reducing server execution time equally for reactive and imperative stacks.

### 25.3. Reactor and WebFlux

15. [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — `Mono`/`Flux`, publishers, operators, subscription, and backpressure.
16. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) — `subscribeOn`, `publishOn`, `boundedElastic`, and why `block()` fails on non-blocking schedulers.
17. [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — `StepVerifier` and virtual time.
18. [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — `onErrorResume`, `retryWhen`, and error signals.
19. [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html) — non-blocking I/O, event-loop model, and Reactive Streams backpressure.
20. [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html) — `Mono`/`Flux` return types, request binding, and HTTP responses.
21. [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — testing reactive HTTP endpoints.
22. [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html) — reactive security context, authentication, and authorization.

### 25.4. Boot, MongoDB Driver, and Observability

23. [Spring Boot — MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.mongodb) — auto-configuration, configuration properties, reactive starter, and connections.
24. [MongoDB Java Reactive Streams Driver](https://www.mongodb.com/docs/drivers/reactive-streams/) — Reactive Streams driver concepts, APIs, and version compatibility.
25. [MongoDB Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — server selection, TLS, pool, and network timeout options by driver/version.
26. [MongoDB Java Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — CMAP/SDAM/Command event concepts and instrumentation; verify listener APIs for your reactive driver version.
27. [MongoDB serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server connections, locks, queues, CPU, and storage metrics.
28. [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `executionStats`, `IXSCAN`/`COLLSCAN`, and keys/docs examined for slow-query tuning.
29. [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retries and ambiguous write outcomes.
30. [Micrometer Observation](https://micrometer.io/docs/observation) — instrumentation and tracing context; check Spring Boot/Actuator version compatibility.

**Note:** Official URLs may redirect as Spring Data, Boot, and Reactor reorganize docs. Verify `ReactiveMongoTemplate`, repositories, transactions, and schedulers against docs for your **exact release line**. This lesson makes no claim of having executed the snippets, benchmarks, or tests in a live environment.

### 25.5. Pre-Production Checklist for Reactive APIs

1. **Dependencies & versions:** BOM-aligned reactive starter, driver, and Reactor; no duplicate `MongoClient` beans.
2. **Non-blocking path:** zero `block()`, `Thread.sleep()`, sync `MongoTemplate`, or JDBC calls on WebFlux event loops.
3. **Security:** resolve tenant/ACL from a trusted reactive authentication context and enforce on every query.
4. **Resource bounds:** cap page sizes, batch sizes, `flatMap` concurrency, queue depths, timeouts, and response sizes.
5. **Correctness:** atomic conditional updates, `@Version`, properly scoped transactions, idempotent retries, and zero fire-and-forget writes.
6. **Streaming:** cursor/change-stream cancellation, resume checkpoints, and no false exactly-once assumptions.
7. **Tests:** `StepVerifier`, `WebTestClient`, replica-set MongoDB integration tests covering races, cancellations, timeouts, and cross-tenant isolation.
8. **Observability:** HTTP p95/p99, event-loop lag, driver pool checkouts, MongoDB command latency/`explain`/CPU/IOPS, error and retry counters.
9. **Rollout:** canary release, realistic-mix load tests, failover/recovery drills, and rollback plan.
10. **Business SLO:** embrace controlled load shedding at capacity rather than letting unbounded queues trigger cascading timeouts.

## 26. Conclusion

**`ReactiveMongoTemplate` and `ReactiveMongoRepository`** provide Spring Data's two primary interfaces for accessing MongoDB under the non-blocking Reactive Streams model. Repositories excel at **domain CRUD and derived queries**, while `ReactiveMongoTemplate` excels at **complex criteria, atomic updates, aggregations, projections, and streaming**. Both coexist cleanly in a WebFlux application backed by a properly configured reactive MongoDB driver and connection pool.

What matters most is not merely returning `Mono` or `Flux` from every method, but **never blocking the shared threads serving concurrent requests**. **Return composed pipelines** rather than calling `block()` or `subscribe()` inside request paths; replace synchronous I/O with reactive APIs; and when legacy blocking integration is unavoidable, isolate it via `fromCallable + boundedElastic` with **strict concurrency and deadline caps**. Reactive backpressure never replaces `limit`, pagination, bounded memory, or well-designed MongoDB indexes.

For multi-write workflows, master **transactions via Reactor subscriber Context, optimistic locking, cancellation, and commit ambiguity**. An HTTP timeout never proves a MongoDB write aborted; a change stream never guarantees cross-system exactly-once delivery. Only by pairing **end-to-end non-blocking execution, strict resource bounds, data consistency, security, and load-tested observability** does reactive MongoDB deliver lasting value.

**Sound design keeps event loops free to serve high concurrency while ensuring MongoDB and downstream resources only receive work they can complete accurately, safely, and within deadline.**
