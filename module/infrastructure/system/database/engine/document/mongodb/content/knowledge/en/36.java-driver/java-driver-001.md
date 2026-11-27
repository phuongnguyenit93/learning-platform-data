# Choosing Sync or Reactive Streams Java Driver for MongoDB Applications

## 1. Architectural Question: Should You Choose the Sync Driver or the Reactive Streams Driver?

When a Java application connects to MongoDB, there are two common programming models with the official drivers:

- **MongoDB Java Sync Driver**: A synchronous API; calls typically return results only when the required MongoDB work has completed or failed. Code executes sequentially, making it convenient for traditional request/response flows, batch jobs, blocking libraries, and many Spring MVC applications.
- **MongoDB Java Reactive Streams Driver**: An API based on the **Reactive Streams** specification; database access operations return **`Publisher<T>`**, allowing composition with Reactor (`Mono`/`Flux`), RxJava, or a custom `Subscriber`. Work is executed **asynchronously**, with support for demand signaling (*demand/backpressure*) and *cancellation*.

Both connect to MongoDB Server/Atlas and use connection pools, authentication, TLS, BSON/codec mechanisms, and database features appropriate for the driver/version. This is **not** a choice between two different types of MongoDB Server.

**There is no rule that "Reactive is always faster than Sync."** The decision must be based on **the application's concurrency model, framework, concurrent request volume, I/O pipeline, codebase requirements, operational maintainability, and team capability**.

For example:

- REST API with Spring MVC, a few hundred requests/s, mostly sequential processing and blocking JDBC libraries: **the Sync Driver is usually more appropriate**.
- Spring WebFlux processing data streams, many asynchronous I/O tasks, and pipelines already using Reactor: **the Reactive Streams Driver** helps maintain a consistent non-blocking chain.
- Plain Java batch import/ETL requiring transactions and easy-to-debug code: **Sync** is a sensible default to consider.
- SSE/WebSocket pushing data from MongoDB Change Streams to many subscribers: **Reactive** has advantages in stream integration and subscriber cancellation.
- REST API on JDK 21+ using virtual threads: **Sync** can handle concurrency better than the traditional platform-thread model, though you still must benchmark connection pool and database limits.

### What Will You Learn?

1. Distinguish between **blocking**, **non-blocking**, **asynchronous**, **reactive**, **parallelism**, and **backpressure**.
2. Read and configure `mongodb-driver-sync` and `mongodb-driver-reactivestreams` dependencies properly.
3. Write the same CRUD problem using both APIs and compare how results are returned.
4. Understand **cold Publishers**, `subscribe()`, `request(n)`, `cancel()`, `Mono`, `Flux`, and error/completion signals.
5. Choose the right driver for Spring MVC, Spring WebFlux, Spring Data, Java virtual threads, batch jobs, and message consumers.
6. Manage `MongoClient`, connection pools, timeouts, transactions, contexts, and error handling.
7. Avoid calling `block()` or the Sync Driver directly on event-loop threads.
8. Define fair benchmarks based on p95/p99, throughput, CPU, heap, threads, connection pool, and DB load.
9. Have a checklist and scorecard to make decisions for production systems.

---

## 2. Where Do the Two Official APIs Live?

### 2.1. Java Sync Driver

Common namespaces:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.FindIterable;
```

Usage:

```java
Document doc = collection.find(eq("sku", "SKU-1")).first();
```

The return value is a `Document` or `null`. The calling thread **waits for the result** using blocking semantics. Errors are typically thrown as exceptions.

### 2.2. Java Reactive Streams Driver

Different namespaces:

```java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import com.mongodb.reactivestreams.client.MongoDatabase;
import com.mongodb.reactivestreams.client.MongoCollection;

import org.reactivestreams.Publisher;
```

Example:

```java
Publisher<Document> publisher =
    collection.find(eq("sku", "SKU-1")).first();
```

This is a **description of asynchronous work**. Obtaining a `Publisher` does not mean the query has been executed. In the current Reactive Streams driver, publishers are **cold**: the database operation begins when subscribed to.

### 2.3. Two Easily Confused Namespaces

| Sync | Reactive Streams |
| --- | --- |
| `com.mongodb.client.MongoClient` | `com.mongodb.reactivestreams.client.MongoClient` |
| `com.mongodb.client.MongoCollection` | `com.mongodb.reactivestreams.client.MongoCollection` |
| `FindIterable<Document>` | `FindPublisher<Document>` |
| `Document` returned directly on `first()` | `Publisher<Document>` from `first()` |
| `MongoClients.create(uri)` from sync package | `MongoClients.create(uri)` from reactive package |

In the same Java file, **do not import both `MongoClient` classes with the same simple name** and expect the compiler to distinguish them automatically. Use fully qualified names or organize modules cleanly if there is a reason to use both.

### 2.4. Why Does MongoDB Provide Both?

Applications using MongoDB can be structured in two different ways:

- **Imperative/synchronous**: calling MongoDB is a step in a running method, waiting for completion before processing the result. Optimized for simplicity, readability, and blocking integration.
- **Reactive/asynchronous**: describing a chain of work and passing data/results via publishers; threads do not need to be held waiting for network responses in the traditional way. Optimized for I/O orchestration and end-to-end event-driven pipelines.

Both must respect the resource limits of the MongoDB deployment. Reactive does not turn a `COLLSCAN` query into an `IXSCAN`, nor does it magically increase the throughput of a CPU-saturated shard.

---

## 3. How Do Synchronous, Asynchronous, Non-Blocking, and Reactive Differ?

### 3.1. Blocking

```text
Thread T1:
  receive request
  call MongoDB find()
      |
      | wait for network + server + response
      v
  receive Document
  process business logic
  return response
```

In the traditional thread-per-request model, a platform thread can be occupied while waiting on I/O. That increases thread and memory demands under high concurrency.

**Blocking is not a design flaw by default.** With reasonable workloads and well-managed thread pools, it can be very efficient and simple.

### 3.2. Non-blocking Asynchronous

```text
Request handler:
  create operation
  register callback/subscriber
  do not wait synchronously
      |
      v
Driver I/O layer:
  send MongoDB command
  receive response later
  emit onNext/onComplete
      |
      v
Handler continuation:
  transform + respond
```

A thread can handle other work while waiting on the network. That **is not free**: you must manage callbacks, demand, state, errors, and lifecycle.

### 3.3. Reactive Streams Also Adds Backpressure

Reactive Streams standardizes the protocol between the **data producer** and the **data consumer**:

- `Publisher<T>`: the source emitting items.
- `Subscriber<T>`: the receiver.
- `Subscription`: the control link.
- `request(n)`: the subscriber signals the maximum number of next items it wants to receive.
- `cancel()`: the subscriber indicates it no longer wants to receive items.

A reactive stream can emit multiple documents via multiple `onNext` calls, then terminate with `onComplete` or `onError`.

### 3.4. Reactive Does Not Mean Parallel

`Flux.from(collection.find(...))` is an asynchronous stream of results. However:

- A single query does not necessarily run in parallel across multiple CPU cores.
- Multiple `flatMap` calls can launch many database operations concurrently, creating fan-out.
- MongoDB is still subject to connection pool limits, read/write capacity, and transaction constraints.
- Backpressure regulates demand per publisher; it does not automatically distribute load fairly across all tenants.

**Parallelism** is the number of tasks that can genuinely make progress simultaneously; **asynchrony** is not having to wait synchronously to proceed.

---

## 4. Quick Comparison by Architectural Criteria

| Criterion | Java Sync Driver | Reactive Streams Driver |
| --- | --- | --- |
| Style | Imperative, call and wait | Publisher, composition, subscription |
| Results | `Document`, `List`, `MongoCursor`, update result | `Publisher<T>`, commonly wrapped in `Mono`/`Flux` |
| Caller-side I/O | Blocking | Non-blocking/asynchronous |
| Concurrency management | Threads, executors, virtual threads | Scheduler/event loop + demand |
| Spring MVC integration | Natural | Usable, but usually increases complexity |
| Spring WebFlux integration | Must avoid blocking event loop | Natural via Spring Data Reactive |
| Batch/CLI | Clear, easy sequential flow | Often more abstraction overhead |
| Streaming | Blocking/iterative cursor | Publisher and backpressure |
| Cancellation | Interrupt/timeout and cursor cleanup | Cancellation signal; cleanup is not rollback |
| Transactions | Imperative session/`withTransaction` | Reactive session propagated along the reactive chain |
| Debugging | Sequential stack traces | More complex asynchronous stack/context |
| Resource risk | Thread saturation | Unbounded flatMap, buffers, event-loop blocking |
| MongoDB performance | Depends on query/pool/server | Depends on query/pool/server |
| Connectivity | Connection pool | Connection pool |
| Best fit | Blocking frameworks | End-to-end non-blocking pipelines |

**Practical takeaway:** Choose the driver based on **how the system is written and deployed**, not based on labels like "newer", "more modern", or a single-query microbenchmark.

---

## 5. Maven/Gradle Dependencies and Versions

MongoDB recommends using the **MongoDB Driver BOM** to keep related artifacts on compatible versions. You can use one MongoDB BOM for both drivers, though you do not necessarily need to add both artifacts to a single application.

**Versions in the examples below are configuration placeholders**: replace `<mongo-driver-version>` with an approved current version compatible with your JDK, MongoDB Server, and accompanying libraries. Do not copy the placeholder verbatim and expect Maven to build.

### 5.1. Maven — Sync Driver

```xml
<properties>
    <mongodb.driver.version>5.x.y</mongodb.driver.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.mongodb</groupId>
            <artifactId>mongodb-driver-bom</artifactId>
            <version>${mongodb.driver.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.mongodb</groupId>
        <artifactId>mongodb-driver-sync</artifactId>
    </dependency>
</dependencies>
```

In this example, `5.x.y` is a placeholder, **not a valid Maven version**. Choose a real version and let the BOM manage related artifacts.

**Syntax note:** Maven uses `${mongodb.driver.version}` syntax to reference the declared property. Replace the `5.x.y` property value with a verified numeric version; do not rename the property in the reference.

### 5.2. Gradle Kotlin DSL — Sync Driver

```kotlin
val mongodbVersion = "5.x.y" // Replace with an actual version.

dependencies {
    implementation(platform("org.mongodb:mongodb-driver-bom:$mongodbVersion"))
    implementation("org.mongodb:mongodb-driver-sync")
}
```

### 5.3. Gradle Kotlin DSL — Reactive Streams Driver

```kotlin
val mongodbVersion = "5.x.y" // Replace with an actual version.

dependencies {
    implementation(platform("org.mongodb:mongodb-driver-bom:$mongodbVersion"))
    implementation("org.mongodb:mongodb-driver-reactivestreams")

    // Only if you want to use Project Reactor:
    implementation("io.projectreactor:reactor-core:<approved-version>")
}
```

`reactor-core` requires an appropriately managed version or Reactor BOM/Spring Boot dependency management. The driver **does not force the application to use Reactor**: it exposes Reactive Streams `Publisher`; Reactor is a convenient library for composition.

### 5.4. Maven — Reactive Streams Driver

```xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-reactivestreams</artifactId>
</dependency>
```

Add the dependency above inside `<dependencies>` in a `pom.xml` that imports the BOM, and configure the Reactor BOM if the application uses `reactor-core`. You do not need to add `mongodb-driver-sync` just to use the reactive driver.

### 5.5. When Using Spring Boot

With Spring Boot:

- `spring-boot-starter-data-mongodb` typically brings in **Spring Data MongoDB imperative** (backed by the sync driver).
- `spring-boot-starter-data-mongodb-reactive` brings in **Spring Data MongoDB reactive** (backed by the reactive streams driver).
- Spring Boot manages the versions of Spring Data, MongoDB Java Driver, and Reactor in its corresponding dependency BOM.

**Prefer the Boot BOM** if you are using Boot. Do not override the MongoDB driver version manually without checking compatibility across the Spring Data release train, Spring Boot, and the driver.

### 5.6. Where to Check Versions and Compatibility?

- MongoDB Java Sync Driver docs: `https://www.mongodb.com/docs/drivers/java/sync/current/`.
- MongoDB Reactive Streams Driver docs: `https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/`.
- Driver compatibility/release notes for the exact major version.
- Spring Boot dependency versions and Spring Data MongoDB compatibility.

MongoDB may update its leading recommended versions in documentation. This article does not assume the version used today will remain the optimal choice for a project a year from now.

---

## 6. Designing a Shared Lab Dataset for Both Drivers

Use an authorized local MongoDB instance or Atlas development cluster. The goal is to have the exact same database, collection, and query to compare the APIs.

Open `mongosh` and run **on the lab environment only**:

```javascript
const lab = db.getSiblingDB("java_driver_choice_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "O-101",
    tenantId: "A",
    status: "PAID",
    amount: NumberDecimal("150.00"),
    createdAt: ISODate("2026-11-14T08:00:00Z")
  },
  {
    _id: "O-102",
    tenantId: "A",
    status: "NEW",
    amount: NumberDecimal("29.99"),
    createdAt: ISODate("2026-11-14T08:10:00Z")
  },
  {
    _id: "O-103",
    tenantId: "B",
    status: "PAID",
    amount: NumberDecimal("450.50"),
    createdAt: ISODate("2026-11-14T09:00:00Z")
  },
  {
    _id: "O-104",
    tenantId: "A",
    status: "PAID",
    amount: NumberDecimal("12.00"),
    createdAt: ISODate("2026-11-14T09:15:00Z")
  }
]);

lab.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_tenant_status_createdAt" }
);
```

Business query:

> "Find up to 10 `PAID` orders for tenant A, newest first, returning only the fields the application needs."

Expected fixture output (excluding `_id` if dropped by projection):

```text
O-104  PAID  2026-11-14T09:15:00Z
O-101  PAID  2026-11-14T08:00:00Z
```

Both drivers must execute **the exact same filter, sort, limit, and projection**; otherwise, any benchmark is unfair.

---

## 7. Java Sync Driver: Complete CRUD Example

This is a simple Java application that connects to MongoDB, fetches orders, counts matching documents, performs a sample operation, and closes the client. Set `MONGODB_URI` in the process environment variables rather than hardcoding credentials.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class SyncMongoExample {
    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGODB_URI", "mongodb://127.0.0.1:27017"
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("java_driver_choice_lab");
            MongoCollection<Document> orders =
                database.getCollection("orders");

            FindIterable<Document> result = orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "A"),
                        Filters.eq("status", "PAID")
                    ))
                .sort(Sorts.descending("createdAt"))
                .limit(10)
                .projection(Projections.include(
                    "tenantId", "status", "createdAt", "amount"
                ));

            for (Document order : result) {
                System.out.println(order.toJson());
            }

            long paidCount = orders.countDocuments(
                Filters.and(
                    Filters.eq("tenantId", "A"),
                    Filters.eq("status", "PAID")
                )
            );

            System.out.println("PAID orders: " + paidCount);
        }
    }
}
```

### 7.1. Key Takeaways

- `MongoClients.create(uri)` creates a client with a connection pool; **never create a new client per query or request**.
- `getDatabase` and `getCollection` are APIs for accessing database/collection handles and do not necessarily trigger an immediate network round trip.
- `find(...)` builds a `FindIterable`; execution happens when iterating, calling `first()`, etc.
- `for (Document order : result)` reads from the cursor. The current thread waits for the required I/O.
- `try-with-resources` fits **CLI/demo** programs. For an application server, create `MongoClient` once aligned with the service/container lifecycle and close it on shutdown.
- You can use BSON codecs/POJO mapping instead of `Document`.
- Exceptions can be caught via appropriate `MongoException` subclasses; do not swallow errors or retry indefinitely.

### 7.2. Fetching a Single Document

```java
Document order = orders.find(
    Filters.eq("_id", "O-101")
).first();

if (order == null) {
    System.out.println("Not found");
} else {
    System.out.println(order.getString("status"));
}
```

Advantage: the expression is intuitive for developers used to imperative code. However, `first()` is an I/O blocking point; do not call it directly on WebFlux's Netty event loop.

### 7.3. WriteResult and Errors

```java
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Updates;

UpdateResult updated = orders.updateOne(
    Filters.eq("_id", "O-102"),
    Updates.set("status", "PAID")
);

System.out.println("Matched: " + updated.getMatchedCount());
System.out.println("Modified: " + updated.getModifiedCount());
```

The result is meaningful only in the context of write concern/transaction semantics and application conditions. You may see `matchedCount=1` and `modifiedCount=0` if the value was already identical.

### 7.4. Sync Cursor and Resource Ownership

When you want direct control over the cursor:

```java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor =
         orders.find(Filters.eq("tenantId", "A")).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        // Process a single document.
    }
}
```

Closing the cursor releases client/server resources when terminating early. For libraries processing large datasets, avoid unbounded `into(new ArrayList<>())` without controlling result size.

---

## 8. Java Reactive Streams Driver with Project Reactor

The reactive driver returns a `Publisher`. Project Reactor provides `Mono` (0–1 item) and `Flux` (0–N items) to turn a Publisher into an ergonomic composable pipeline.

### 8.1. Query Example

```java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import com.mongodb.reactivestreams.client.MongoCollection;
import com.mongodb.reactivestreams.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveMongoExample {
    public static void main(String[] args) {
        String uri = System.getenv().getOrDefault(
            "MONGODB_URI", "mongodb://127.0.0.1:27017"
        );

        MongoClient client = MongoClients.create(uri);

        MongoDatabase database =
            client.getDatabase("java_driver_choice_lab");

        MongoCollection<Document> orders =
            database.getCollection("orders");

        Flux<Document> paidOrders = Flux.from(
            orders.find(
                    Filters.and(
                        Filters.eq("tenantId", "A"),
                        Filters.eq("status", "PAID")
                    ))
                .sort(Sorts.descending("createdAt"))
                .limit(10)
                .projection(Projections.include(
                    "tenantId", "status", "createdAt", "amount"
                ))
        );

        // In a real reactive application:
        // return paidOrders.map(Document::toJson);
        // The framework will subscribe and manage lifecycle.

        // CLI demo ONLY: subscribe/wait for completion so main does not exit early.
        try {
            java.util.List<Document> result =
                paidOrders.collectList().block(
                    java.time.Duration.ofSeconds(10)
                );

            if (result != null) {
                result.forEach(doc -> System.out.println(doc.toJson()));
            }
        } finally {
            client.close();
        }
    }
}
```

**Important warning:** `.block()` at the end of the example is used solely to keep the **CLI/main** program waiting for results. Inside a WebFlux endpoint/reactive pipeline, **you must not call `block()` on an event-loop thread**. Instead, **return `Mono`/`Flux` to the framework**.

### 8.2. Querying a Single Document

```java
Mono<Document> byId = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

Mono<String> status = byId
    .map(doc -> doc.getString("status"))
    .defaultIfEmpty("NOT_FOUND");
```

If no document matches, the publisher completes **empty**; it does not emit `null` via `onNext` (Reactive Streams forbids `null`). This differs from Sync `first()`, which can return `null`.

### 8.3. Update

```java
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

Mono<UpdateResult> update = Mono.from(
    orders.updateOne(
        Filters.eq("_id", "O-102"),
        Updates.set("status", "PAID")
    )
);

Mono<Long> matched = update.map(UpdateResult::getMatchedCount);
```

Creating `update` or `matched` **does not send a DB command immediately**. The MongoDB operation runs only when a subscription occurs.

### 8.4. Do Not Subscribe Manually Inside a Service When the Framework Is the Subscriber

Dangerous example in WebFlux:

```java
public Mono<String> updateStatus() {
    Mono.from(
        orders.updateOne(
            Filters.eq("_id", "O-102"),
            Updates.set("status", "PAID")
        )
    ).subscribe(); // STARTS a side effect without wiring it into the response.

    return Mono.just("accepted");
}
```

The endpoint can return `accepted` before the write succeeds. Write exceptions are handled on a disconnected chain and are very hard to correlate with the request.

The right way:

```java
public Mono<String> updateStatus() {
    return Mono.from(
        orders.updateOne(
            Filters.eq("_id", "O-102"),
            Updates.set("status", "PAID")
        )
    ).map(result ->
        result.getMatchedCount() > 0 ? "updated" : "not-found"
    );
}
```

The framework subscribes when an HTTP request arrives; error signals travel along the same pipeline so they can be mapped to HTTP errors and traces.

---

## 9. Cold Publishers and the "Nothing Happens" Bug

The reactive driver returns **cold publishers**: constructing a Publisher does not execute the query until `subscribe` is called.

```java
Mono<Document> query = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

// Up to this point, no query has been issued because nobody has subscribed.
```

Once:

```java
query.subscribe(
    doc -> System.out.println(doc.toJson()),
    error -> System.err.println(error.getMessage()),
    () -> System.out.println("Completed")
);
```

only then does the driver execute the work and emit signals to the Subscriber.

### 9.1. Subscribing Twice Usually Runs Two Database Operations

```java
Mono<Document> query = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

query.subscribe(doc -> System.out.println("A: " + doc));
query.subscribe(doc -> System.out.println("B: " + doc));
```

Each subscription to a publisher created by the reactive driver represents a separate operation; it can trigger **two reads**. In Reactor, operators like `cache()` can change these semantics and share results, but they carry trade-offs in memory, staleness, and error caching. Do not cache sensitive or rapidly changing data without a TTL and tenant-isolation strategy.

### 9.2. A Publisher Is Not a Future

An unsubscribed `Publisher` is not equivalent to a `CompletableFuture` that has already launched a task. To interoperate, you must convert lifecycle, ownership, cancellation, and timeouts properly. Calling `subscribe` manually and returning a `CompletableFuture` without propagating cancellation or errors can cause leaks.

### 9.3. Reactor Signals

```text
onSubscribe(subscription)
    |
request(n)
    |
onNext(document) 0..n times
    |
onComplete()  or  onError(error)
```

After a terminal signal (`onComplete` or `onError`), the stream emits no further `onNext` events.

---

## 10. Backpressure in Practice

### 10.1. The Fast-Producer, Slow-Consumer Problem

Suppose MongoDB returns many documents, while the application needs to call a slow HTTP API for each item:

```text
MongoDB finds: 1000 documents/s
Remote service: 20 requests/s
```

If the application materializes all documents and opens thousands of network requests, memory and connection pools can become saturated.

Reactive Streams allows the Subscriber/Operator to propagate **demand** and limit items in flight in the pipeline. However, **backpressure does not automatically decide business concurrency**; developers still have to set explicit bounds.

### 10.2. Bounding Concurrent Work

```java
Flux<Document> source = Flux.from(
    orders.find(Filters.eq("status", "PAID"))
);

Flux<String> transformed = source.flatMap(
    order -> callRemoteService(order), // Non-blocking Mono<String>.
    16                                 // At most 16 inner subscriptions.
);
```

`callRemoteService` is a **hypothetical** function returning `Mono<String>`. In a real application, it must use a non-blocking HTTP client such as Reactor Netty/WebClient, not a blocking Java HTTP call inside the lambda.

Raising concurrency to 1000 can overload downstream services without improving throughput. Tuning must measure pool usage, latency, errors, and retry rates.

### 10.3. Buffers and Memory Limits

Operators such as `collectList()`, `buffer()`, and `onBackpressureBuffer()` can accumulate data. For example:

```java
Mono<java.util.List<Document>> all = Flux.from(
    orders.find()
).collectList();
```

This snippet can load **the entire collection into RAM** if the query is unbounded. Reactive code can still hit `OutOfMemoryError`.

Better for a bounded list endpoint:

```java
Flux<Document> page = Flux.from(
    orders.find(Filters.eq("tenantId", "A"))
      .sort(Sorts.descending("createdAt", "_id"))
      .limit(50)
);
```

For infinite streaming, you must design demand, queues, timeouts, and cancellation.

### 10.4. Backpressure Does Not Turn MongoDB into a Broker

When using Change Streams or tailable cursors, backpressure helps regulate how much data the application pulls, but **it does not replace** durable offsets/resume tokens, consumer checkpoints, data retention, and recovery policies. MongoDB still has its own oplog/change-stream retention and server cursor behavior.

---

## 11. The Web Framework Is the Most Important Driver Selection Criterion

### 11.1. Spring MVC / Servlet

```text
HTTP request -> servlet worker thread
    -> service method
    -> Sync MongoDB driver
    -> result
    -> HTTP response
```

Pros:

- Easy-to-follow code flow.
- Fits JDBC, legacy SDKs, and many blocking libraries.
- Validation, transactions, and thread-bound security context are usually straightforward.
- Easy onboarding for Java developers familiar with imperative style.

Cons:

- If each request holds a platform thread while waiting on the DB, thread/memory usage can climb under high concurrency.
- Requires thread pool, timeout, and backpressure controls at ingress.
- Cannot solve database pool saturation simply by increasing servlet threads.

**Best when** the service processes sequentially, concurrency is low/moderate, the team prioritizes simplicity, or dependencies are already blocking.

### 11.2. Spring WebFlux / Reactor Netty

```text
HTTP request -> event loop
    -> Mono/Flux service
    -> Reactive MongoDB publisher
    -> async completion
    -> HTTP response
```

Pros:

- Maintains an end-to-end non-blocking pipeline.
- Fits reactive WebClient, message streams, and SSE.
- Does not require holding a platform thread for every request waiting on MongoDB.
- Easy to compose timeout/cancel/retry at the pipeline level.

Cons:

- Debugging, context propagation, and transaction lifetimes are more complex.
- A single blocking call can stall the event loop.
- Misused operators can cause fan-out, unbounded buffering, and subscription leaks.
- The development team must understand error, demand, and scheduler semantics.

**Best when** the application already uses WebFlux and all major dependencies are non-blocking.

### 11.3. Spring WebFlux Using the Sync Driver?

You must not call the Sync Driver directly in code executing on the event loop:

```java
// WRONG in a WebFlux handler if running on the event loop:
public Mono<String> findStatus() {
    Document doc = syncOrders.find(eq("_id", "O-101")).first();
    return Mono.just(doc == null ? "missing" : doc.getString("status"));
}
```

The `first()` operation blocks before `Mono.just` is even created, tying up the event loop.

**Transitional workaround** when you cannot switch drivers yet:

```java
import reactor.core.scheduler.Schedulers;

public Mono<String> findStatus() {
    return Mono.fromCallable(() -> {
        Document doc =
            syncOrders.find(Filters.eq("_id", "O-101")).first();
        return doc == null ? "missing" : doc.getString("status");
    }).subscribeOn(Schedulers.boundedElastic());
}
```

This is a **bridge** to offload blocking I/O onto `boundedElastic` threads; it does not make the Sync Driver non-blocking and should not be treated as equivalent to the native reactive driver under heavy load. `boundedElastic` also has thread and queue limits.

### 11.4. Using the Reactive Driver in Spring MVC?

It is possible, but you must decide whether requests return `Mono`/`Flux` via MVC async support or block to wait. If you call `block()` and return a DTO in an MVC controller, you are reverting to a blocking model while adding reactive complexity.

That is not automatically wrong for temporary integration, but ask: **what is the concrete benefit and is there a benchmark proving it?** If the framework and application are primarily blocking, Sync is usually easier to operate.

---

## 12. Spring Data MongoDB: Choosing a Consistent Abstraction Layer

In Spring Boot, teams rarely call the raw driver directly and instead use Spring Data:

| Imperative | Reactive |
| --- | --- |
| `MongoTemplate` | `ReactiveMongoTemplate` |
| `MongoRepository<T, ID>` | `ReactiveMongoRepository<T, ID>` |
| Returns `T`, `List<T>`, `Optional<T>` | Returns `Mono<T>`, `Flux<T>` |
| `MongoTransactionManager` | `ReactiveMongoTransactionManager` |
| `spring-boot-starter-data-mongodb` | `spring-boot-starter-data-mongodb-reactive` |

### 12.1. Imperative Repository

```java
import org.springframework.data.mongodb.repository.MongoRepository;
import java.util.List;

public interface OrderRepository
        extends MongoRepository<Order, String> {
    List<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

`Order` is a domain entity defined by the application with appropriate ID/type mapping. The method returns a `List` and interacts synchronously using Spring Data imperative semantics.

### 12.2. Reactive Repository

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<Order, String> {
    Flux<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );
}
```

Service:

```java
public Flux<Order> paidOrders(String tenantId) {
    return repository.findByTenantIdAndStatus(
        tenantId, "PAID"
    );
}
```

In a Spring WebFlux controller, return `Flux<Order>` or `Mono<Response>` so the framework subscribes. Do not call `subscribe()` inside the repository or service.

### 12.3. Do Not Confuse a Reactive Repository with a Fully Non-Blocking System

An endpoint that uses a reactive repository yet:

- makes blocking JDBC calls,
- makes REST calls with `RestTemplate`,
- reads large files synchronously,
- runs CPU-heavy transforms directly on the event loop,

means **the overall pipeline is no longer truly non-blocking**.

Examine **every I/O component on the critical path**, not just the MongoDB driver.

---

## 13. Do Java Virtual Threads Change the Choice?

**Virtual threads** are stable in Java **21+** (Project Loom). They make writing **imperative blocking code** while serving many concurrent tasks far more practical than the one-platform-thread-per-request model.

### 13.1. Java 21+ Example

```java
import java.util.concurrent.Executors;

try (var executor =
         Executors.newVirtualThreadPerTaskExecutor()) {

    for (String orderId : java.util.List.of(
            "O-101", "O-102", "O-103")) {

        executor.submit(() -> {
            Document order =
                orders.find(Filters.eq("_id", orderId)).first();

            System.out.println(
                orderId + " -> " +
                (order == null ? "missing" : order.getString("status"))
            );
        });
    }
}
```

Here `orders` is a Sync Driver `MongoCollection<Document>` created beforehand and kept alive while tasks execute. Calling `close()` on the executor waits for tasks to finish under current Java semantics.

**Core idea:** Keep readable imperative code without necessarily pinning an OS thread for every waiting request.

### 13.2. What Do Virtual Threads Not Do?

They **do not**:

- Reduce the number of MongoDB operations.
- Increase server connection limits.
- Make an unindexed query run fast.
- Eliminate network latency.
- Replace timeouts or circuit breaking.
- Guarantee zero pinning or CPU saturation.
- Automatically make every blocking library cooperate cleanly with the scheduler.

If 5,000 virtual threads wait simultaneously on 100 connections, the pool still enforces its limit; request queues and p99 latency can still rise.

### 13.3. When Is Sync + Virtual Threads a Strong Choice?

- JDK 21+ application.
- Imperative codebase with many blocking libraries.
- High concurrency where each request is not CPU-heavy.
- Team wants to avoid reactive composition complexity.
- Thread/memory overhead was previously the primary bottleneck.
- Benchmarks confirm the DB pool and server still meet SLOs.

Reactive still holds an advantage when **Reactor/stream composition is already used end-to-end**, or when deep stream backpressure and cancellation are required. Virtual threads do not simply replace all `Publisher` semantics.

---

## 14. MongoClient and Connection Pools in Both Drivers

Both the Sync and Reactive Streams Drivers use **connection pooling**.

### 14.1. Never Create a Client per Request

**Wrong**:

```java
public Document loadOne(String uri, String id) {
    try (com.mongodb.client.MongoClient client =
             com.mongodb.client.MongoClients.create(uri)) {
        return client.getDatabase("app")
            .getCollection("orders")
            .find(Filters.eq("_id", id))
            .first();
    }
}
```

If called on every request, the code creates clients, pools, and monitoring threads only to tear them down immediately, increasing connection setup overhead, TLS handshakes, and latency.

**Right:** The application creates a single `MongoClient` scoped to the service/container lifecycle, shares it across requests, and closes it on shutdown.

### 14.2. Pools Are Managed per Server

According to the MongoDB Java Sync Driver documentation, each `MongoClient` maintains a connection pool per server matching the topology. The driver monitors servers using dedicated monitoring connections.

Pool options can be configured via URI:

```text
mongodb://localhost:27017/?maxPoolSize=100&minPoolSize=0&maxConnecting=2
```

These values are **examples**, not universal optimal settings.

- `maxPoolSize`: maximum number of connections per pool.
- `minPoolSize`: minimum number of connections.
- `maxConnecting`: limits concurrent connection creation.
- `maxIdleTimeMS`: idle duration before a connection may be closed.
- Other timeouts are defined according to driver version.

In many driver versions, `maxPoolSize` defaults to **100 per server**. Verify the defaults for your exact version; do not treat it as an application-wide concurrency cap.

### 14.3. Calculating Total Connections

Suppose:

- 4 application instances.
- 1 MongoClient per instance.
- Connecting to 3 servers.
- `maxPoolSize=100`.

The **theoretical maximum** number of pooled connections:

\[
4 \times 3 \times 100 = 1200
\]

This is the theoretical ceiling if every pool grows to maximum, excluding monitoring sockets and other topology factors. It does not mean MongoDB immediately opens 1,200 connections at startup.

Even with reactive code, concurrent in-flight operations remain bounded by pool and server capacity. Asynchrony reduces blocking-thread cost; **it does not create infinite database connections**.

### 14.4. Pool Checkout Wait

If all connections for the target server are busy:

```text
Incoming request
    |
    +-- Pool full
    |
    +-- Wait/queue
    |
    +-- Checkout connection
    |
    +-- MongoDB operation
```

p95/p99 latency can spike even when server query execution time is low. You must measure:

- Connection checkout wait.
- Connections checked out/available.
- Wait queue.
- Server selection time.
- Socket/network latency.
- MongoDB execution time.
- Application end-to-end latency.

Increasing pool size indefinitely can overload the server even more. Tune based on measured capacity.

---

## 15. Timeouts and Cancellation: Different but Equally Critical

### 15.1. Types of Wait Times and Timeouts

| Type | Role |
| --- | --- |
| Server selection timeout | Waiting to find a server matching read preference/topology |
| Connection establishment timeout | Waiting to open a TCP/TLS connection |
| Pool checkout wait | Waiting for an available connection |
| Socket timeout | Waiting to send/receive on a socket |
| Operation timeout / CSOT (when supported by driver) | End-to-end operation time limit |
| Server `maxTimeMS` | Requests the server to limit operation execution time |
| Reactive `timeout(Duration)` | Pipeline-level timeout; can trigger cancellation |

Defaults and semantics vary across driver releases; consult documentation for your exact version.

### 15.2. Sync Query with maxTime

```java
Document result = orders
    .find(Filters.eq("tenantId", "A"))
    .maxTime(2, java.util.concurrent.TimeUnit.SECONDS)
    .first();
```

`maxTime` applies a server-side processing limit based on operation support. It does not replace network timeouts and does not guarantee a business SLA in every scenario.

### 15.3. Reactive Timeout

```java
Mono<Document> result = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
).timeout(java.time.Duration.ofSeconds(2));
```

On timeout, Reactor typically cancels the upstream subscription; however, **cancellation is not a transaction rollback or a guarantee that a write never reached the server**. For writes, a client can time out while the server still applied the change. Designing for idempotency and verifying outcomes is mandatory.

### 15.4. Retries Can Cause Duplicate Writes

```java
Mono<UpdateResult> operation = Mono.from(
    orders.updateOne(
        Filters.eq("_id", "O-101"),
        Updates.inc("retryCounter", 1)
    )
);
```

If you blindly attach Reactor `retry(3)`, an `$inc` update may be sent multiple times under ambiguous error scenarios or when a new subscription is created. Do not assume pipeline `retry` is equivalent to the driver's retryable writes.

To stay safe:

- Use idempotent operations whenever possible.
- Use unique/idempotency keys.
- Distinguish transient vs. permanent errors.
- Design explicit timeout and retry budgets.
- Avoid cascading retry storms from HTTP proxy → app → driver → database.
- Emit telemetry for retry counts.

---

## 16. Exceptions and Error Signals

### 16.1. Sync: Direct Exceptions

```java
try {
    Document order =
        orders.find(Filters.eq("_id", "O-101")).first();
    // Use the result.
} catch (com.mongodb.MongoTimeoutException e) {
    // Log with request context and return an appropriate error.
} catch (com.mongodb.MongoException e) {
    // Handle categorized database error.
}
```

Do not catch `Exception` and return a default success response. Categorize errors such as timeout, authentication, duplicate key, validation, write concern, and so on.

### 16.2. Reactive: onError Signal

```java
Mono<Document> query = Mono.from(
    orders.find(Filters.eq("_id", "O-101")).first()
);

return query
    .doOnError(error -> logDatabaseError(error))
    .onErrorMap(error -> toApplicationException(error));
```

`logDatabaseError` and `toApplicationException` are two **illustrative** helper functions you define yourself. The goal is for errors to travel through the same pipeline so the framework maps HTTP responses, tracing, and metrics.

Do not write:

```java
query.subscribe(
    doc -> process(doc),
    error -> System.out.println("ignored")
);
return Mono.just("OK");
```

inside a handler, because it **detaches side effects from the request lifecycle**, loses propagation, and easily reports false success.

### 16.3. Do Not Use onErrorResume to Swallow All Errors

```java
// BE CAREFUL: an empty fallback can mask a database outage.
Mono<Document> result = query.onErrorResume(
    error -> Mono.empty()
);
```

If you return "not found" when the DB actually timed out, the system can make incorrect business decisions. Only fall back when business semantics allow it and with proper metrics/logging.

---

## 17. Reactive Context and ThreadLocal

In imperative Spring MVC, several libraries rely on `ThreadLocal` to hold:

- Request ID.
- Security context.
- Transaction state.
- MDC logging.
- Locale.

In a reactive pipeline, execution can hop across multiple threads. Do not assume `ThreadLocal` automatically propagates accurately to every operator.

### 17.1. Reactor Context

Reactor supports a **Context** bound to the subscription rather than a specific thread:

```java
Mono<String> message = Mono.deferContextual(ctx -> {
    String requestId =
        ctx.getOrDefault("requestId", "unknown");
    return Mono.just("request=" + requestId);
});

Mono<String> requestScoped = message.contextWrite(
    ctx -> ctx.put("requestId", "req-123")
);
```

Data is read inside the reactive chain when subscription happens. In Spring, use official security and tracing context-propagation mechanisms instead of mixing MDC/`ThreadLocal` in uncontrolled ways.

### 17.2. Impact on Transactions

Imperative transactions typically bind context to a thread; reactive transactions bind to the Reactor subscriber context and session lifecycle via the framework. Do not place imperative `@Transactional` on a reactive repository and expect it to act as a reactive transaction.

---

## 18. Transactions: Shared Capability, Different Organization

MongoDB supports multi-document transactions on eligible deployments. Both Sync and Reactive Streams drivers provide session/transaction APIs, but lifecycle management differs.

### 18.1. Sync Transaction

Conceptual example using two collections belonging to the same `MongoClient`:

```java
import com.mongodb.client.ClientSession;
import org.bson.Document;

try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        orders.insertOne(
            session,
            new Document("_id", "O-TX-1")
                .append("status", "NEW")
        );

        audit.insertOne(
            session,
            new Document("event", "ORDER_CREATED")
                .append("orderId", "O-TX-1")
        );

        session.commitTransaction();
    } catch (RuntimeException error) {
        session.abortTransaction();
        throw error;
    }
}
```

`client`, `orders`, and `audit` are **previously initialized** variables, and the code assumes the server topology supports transactions.

This is a minimal example to understand sessions; production code must handle retryable transaction errors, `UnknownTransactionCommitResult`, commit/abort edge cases, and timeouts according to the driver API.

### 18.2. Reactive Transactions Require Proper Session Composition

In the Reactive Streams Driver:

- `startSession()` returns a Publisher of `ClientSession`.
- Operations inside the transaction must pass **the exact same session** and belong to the same `MongoClient`.
- `startTransaction` manages session state; `commitTransaction`/`abortTransaction` participate in the asynchronous flow.
- Do not open a session in one place, call `subscribe()` separately on individual writes elsewhere, and expect transaction guarantees to hold.
- Do not run parallel operations on the same session/transaction if the API does not support it; MongoDB transaction operations require proper sequencing.

Pipeline flow:

```text
subscribe
   |
startSession publisher
   |
startTransaction
   |
write A with session
   |
write B with same session
   |
commitTransaction publisher
   |
close session
   |
complete / error
```

In Spring Data Reactive, prefer `ReactiveMongoTransactionManager` and Spring's `TransactionalOperator` / reactive transaction management mechanisms. Do not hand-roll complex transaction pipelines when the framework already provides the proper abstraction.

### 18.3. Should You Choose a Driver Solely for Transactions?

No. Both support transactions subject to MongoDB Server/version requirements. The deciding factor is **your application's transaction boundaries** and how error handling, retries, and context are implemented.

---

## 19. Streaming Large Results and Change Streams

### 19.1. Sync Cursor

```java
try (MongoCursor<Document> cursor =
         orders.find().batchSize(100).iterator()) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        processDocument(doc); // Blocking/imperative function.
    }
}
```

If `processDocument` is slow, the current thread waits. You must control cursor lifetime, `batchSize`, timeouts, and memory.

### 19.2. Reactive Cursor

```java
Flux<Document> stream = Flux.from(
    orders.find().batchSize(100)
);

Flux<String> transformed = stream.map(
    doc -> doc.getString("status")
);
```

Downstream controls subscription and demand according to Reactor semantics. This does not mean all results are buffered into RAM at once.

### 19.3. Change Streams

Change events can power auditing, event propagation, SSE, and near-real-time processing.

Sync (conceptual):

```java
try (var cursor = collection.watch().iterator()) {
    while (cursor.hasNext()) {
        var event = cursor.next();
        // Process event.
    }
}
```

Reactive:

```java
Flux<?> changes = Flux.from(collection.watch());
```

`collection` in the two snippets above refers to the collection type of each respective driver; they are not imported together in the same class.

**Key considerations for Change Streams:**

- Resume tokens for recovering after interruptions.
- Oplog/change stream retention window.
- Consumer checkpoints and duplicate processing.
- Retry/backoff strategies by error type.
- Never subscribe indefinitely without shutdown/cancellation handling.
- Reactive backpressure does not create a durable queue.

### 19.4. SSE/WebSocket: Reactive Is Worth Considering

An endpoint keeping a continuous stream open for many clients is a strong fit for Reactive + WebFlux, because subscriptions can be canceled when clients disconnect and no platform thread is tied up per socket waiting on I/O.

However, you still need fan-out control, buffering, slow-consumer handling, and reconnect policies; a `Flux` alone does not turn a Change Stream into a complete pub/sub system.

---

## 20. Choosing a Driver by Application Type

| Application | Sensible Default Driver | Rationale |
| --- | --- | --- |
| Spring MVC CRUD service | Sync | Aligns with servlet/request lifecycle |
| Plain, simple Java REST API | Sync | Less abstraction, easier to debug |
| Spring WebFlux with WebClient/Reactor | Reactive Streams | End-to-end non-blocking |
| SSE or WebSocket streaming | Reactive Streams | Publisher, cancellation, backpressure |
| Single-threaded or low-thread batch ETL | Sync | Easy ordering/error control |
| Async fan-out batch ETL with non-blocking downstream | Reactive Streams | Composition and bounded concurrency |
| Sequential Kafka consumer | Sync or Reactive | Depends on consumer model/backpressure |
| Java 21 virtual-thread REST | Sync | Imperative code with lower concurrency overhead |
| Quarkus/Micronaut non-blocking app | Follow extension/framework | Maintain integration consistency |
| Legacy app using blocking JDBC/HTTP | Sync | Reactive DB alone yields little benefit |
| Multi-stream event processing pipeline | Reactive Streams | Good fit for operators/composition |
| CLI tooling/migration script | Sync | Simple, finite lifecycle |
| Complex imperative transaction workflow | Sync | Session/exception flow easier to trace |
| Microservice already using Spring Data Reactive | Reactive Streams | Avoid blocking the event loop |

**Rule of thumb:** If you have to call `block()` almost everywhere to use the reactive driver, **the Sync Driver is likely a better fit** or the architecture needs a genuine redesign.

---

## 21. Simple Decision Tree

```text
Is the application currently reactive/non-blocking end-to-end?
    |
    +-- Yes ---> Are major dependencies non-blocking?
    |                |
    |                +-- Yes -> Prefer Reactive Streams Driver
    |                |
    |                +-- No  -> Consider refactoring or bridging
    |                           with boundedElastic limits;
    |                           benchmark first.
    |
    +-- No  ---> Are there clear long-lived streaming / multi-I/O
                  non-blocking pipeline requirements?
                    |
                    +-- Yes -> Consider designing the whole pipeline
                    |         reactively, not just the DB layer.
                    |
                    +-- No  -> Prefer Sync Driver,
                                 especially Spring MVC/CLI.
                                 Java 21 virtual threads
                                 are worth benchmarking.
```

The final decision also depends on SLOs, throughput, team skills, and operational risk.

---

## 22. Performance: Why Reactive Does Not Guarantee Lower Latency

A MongoDB query taking 30ms on the server does not become 10ms just because the driver is non-blocking. Database-side query execution still depends on:

- Indexes and the query planner.
- Data size/cardinality.
- Read concern/read preference.
- Write concern/transactions.
- CPU, disk, network, and caching.
- Connection pools/queues.
- Batch sizes, document count, and serialization.

Reactive can help **use threads more efficiently when many requests are waiting on I/O**, potentially improving throughput or tail latency at a given concurrency level. However, it can also be slower if the pipeline generates excessive work, heavy buffering, or uncontrolled scheduler switching.

### 22.1. Simple Modeling with Little's Law

In steady state:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests in the system.
- \(\lambda\): throughput (requests/s).
- \(W\): average response time (s).

With 200 requests/s and an average of 100ms:

\[
L = 200 \times 0.1 = 20
\]

Roughly 20 requests in flight on average. However, this **is not a guarantee** that only 20 connections, 20 threads, or 20 subscribers are needed: real traffic involves spikes, parallel queries, retries, and tail latency.

### 22.2. Connection Pool Limits Are an Independent Axis

Suppose:

- 500 concurrent HTTP requests.
- MongoDB max pool size = 100 on the target node.
- Each request requires one DB operation at a time.

Whether the app uses 500 platform threads, 500 virtual threads, or 500 reactive subscriptions, operations can still **wait for a connection**. No concurrency model lets you bypass server capacity.

### 22.3. CPU-Heavy Work Does Not Benefit from Reactive I/O

If every document must be decompressed, encrypted, or run through CPU-heavy hashing, placing that work directly on the Netty event loop can cause stalls. You need an appropriate CPU executor/scheduler, bounded concurrency, and performance measurements. Reactive excels at I/O orchestration, not automatically accelerating CPU computation.

---

## 23. Benchmarking Both Drivers Fairly

Do not benchmark where:

- The Sync driver runs with a cold cache while Reactive runs with a warm cache.
- The Sync query returns 50 documents while Reactive returns 1.
- Sync reads from primary while Reactive reads from secondary.
- Sync uses an index while Reactive lacks an index.
- The Reactive benchmark only measures creating the Publisher **without subscribing**.
- The Reactive benchmark calls `subscribe()` and stops the timer immediately before `onComplete`.
- Sync creates a new client per query while Reactive reuses a singleton client.
- Errored/timed-out requests are excluded from the latency report.

### 23.1. Experimental Setup

Use identical:

- MongoDB deployment/server version.
- Dataset/corpus and index definitions.
- Query filters, sort, projection, and batch size.
- Read preference and read/write concern.
- Network latency/region.
- MongoDB credentials/TLS.
- `maxPoolSize` and corresponding connection settings.
- JVM version, heap, GC, and runtime container resources.
- Warmup and query mix.
- Concurrency levels.

Compare applications at the point where **work actually completes**, not just when the API call returns.

### 23.2. What to Measure?

| Metric | Why? |
| --- | --- |
| Achieved throughput (RPS/QPS) | Actual processing capacity |
| End-to-end p50/p95/p99 | User experience |
| Database command latency | Isolate the DB portion |
| Driver pool checkout wait | Detect connection bottlenecks |
| JVM threads/platform threads | Concurrency overhead/benefit |
| CPU utilization | Efficiency |
| Heap/RSS/GC pauses | Memory pressure |
| Database CPU/IOPS/ops/s | Load pushed down to MongoDB |
| Error/timeout/retry rates | Never ignore failures |
| p99 under high concurrency | Tail behavior |
| Streaming memory per request | Buffering/backpressure |
| Cancellation propagation | Shedding work no longer needed |

### 23.3. Concurrency Sweep

For example:

```text
1, 10, 50, 100, 200, 500 concurrent requests
```

At each level, record actual throughput, latency distribution, errors, pool waits, CPU/memory, and database utilization.

When throughput plateaus and p99 spikes sharply, adding more subscribers or threads usually just builds larger queues. Limiting ingress concurrency or applying load shedding can help stabilize tail latency.

### 23.4. Verifying Data Fairness

When benchmarking queries by `tenantId`, include both small and large tenants as well as varied filter selectivity. Caching, shard targeting, and index cardinality dictate performance far more than driver syntax.

---

## 24. Observability and Tracing for Both Sync and Reactive

A well-instrumented system should answer:

- Which request triggered the query?
- Which query is slow?
- How long did connection checkout wait take?
- How long did server execution take?
- Were there retries or timeouts?
- Is the reactive pipeline fanning out too aggressively?
- Is the event loop blocked or is a scheduler queue growing too long?

### 24.1. Command Monitoring

MongoDB Java drivers provide **`CommandListener`** for command started/succeeded/failed events. You can record metrics:

- Command type and namespace/collection.
- Duration.
- Error category.
- Request/trace correlation.
- Server address.

**Do not log full command documents**, as they may contain PII, sensitive filters, or credentials. Redact literals and collect only necessary metadata.

### 24.2. Pool Monitoring

Connection pool events reveal:

- Connections created/closed.
- Checkout started/succeeded/failed.
- Pool cleared.
- Pool size and wait behavior.

Never assume "async code is slow because of MongoDB Server"; the delay may be inside the driver pool.

### 24.3. Reactive Tracing

Reactive pipelines can switch threads, so context propagation must be properly integrated with OpenTelemetry/Spring Reactor. Thread names are not reliable request IDs. Use trace/span IDs in official context propagation rather than relying purely on `ThreadLocal`.

### 24.4. Security

- TLS and certificate verification.
- Least privilege for application database users.
- Never hardcode connection URIs containing passwords.
- Keep PII out of profiler and command logs.
- Never dump raw production `Document` objects into uncontrolled logs.

---

## 25. Migrating from Sync to Reactive and Vice Versa

Switching drivers **is not just changing imports**.

### 25.1. Steps to Migrate Sync → Reactive

1. Define the objective: reduce platform threads, keep WebFlux non-blocking, enable streaming, or handle concurrency?
2. Measure baseline throughput, p95/p99, CPU/heap/pool before migration.
3. Map the service/repository call graph: which parts are still blocking?
4. Update dependencies using the BOM/framework.
5. Change direct return APIs to `Mono`/`Flux`/`Publisher`.
6. Adapt control flow, error propagation, and timeout semantics.
7. Move transaction boundaries to reactive sessions/managers.
8. Manage Reactor Context/security/tracing propagation.
9. Never call `subscribe()` in the service layer unless lifecycle ownership is explicitly justified.
10. Do not abuse `block()`; any bridges must be bounded and metered.
11. Test idempotency, retries, and cancellation.
12. Load-test with realistic corpus and traffic.
13. Perform a canary rollout with a rollback plan.

### 25.2. Migrating Reactive → Sync

This can make sense when:

- The project moves from WebFlux to Spring MVC/virtual threads.
- Primary dependencies are blocking.
- The team frequently hits context/subscription/cancellation bugs.
- Benchmarks show reactive yields no meaningful benefit.
- The goal is simplifying maintenance.

**Never block indefinitely on an infinite Publisher** (e.g., Change Streams `collectList().block()`), because it may never complete and will accumulate unbounded data in RAM.

### 25.3. Can Both Be Used in One Application?

Yes—for instance, an application with an imperative batch module and a reactive real-time module. However, you must manage:

- Two separate `MongoClient` instances and **two connection pools** if both are instantiated.
- Consistent TLS/auth/read preference/timeout configuration.
- Total memory and thread resources.
- Sessions/transactions cannot be arbitrarily shared across the two client APIs.
- Driver-specific logging and metrics.
- Avoiding dependency conflicts from mismatched versions.

Before choosing a hybrid approach, weigh complexity and operational cost; often, cleanly separating services or modules is better.

---

## 26. Common Pitfalls and How to Fix Them

| Pitfall | Why It Happens | How to Fix |
| --- | --- | --- |
| Creating a Reactive Publisher yields no result | Nobody subscribed | Return the pipeline to the framework or subscribe at the right boundary |
| Calling `subscribe()` in service and returning success immediately | Side effect detached from request lifecycle | Compose using `map`/`flatMap` |
| Calling `block()` on WebFlux event loop | Blocks the event loop | Return `Mono`/`Flux`; bridge with `boundedElastic` only when necessary |
| Sync MongoDB call directly inside `Mono.just(...)` | Eager blocking before subscription | `Mono.fromCallable(...).subscribeOn(boundedElastic())` |
| Reactive `collectList()` over an entire collection | Large in-memory materialization | Apply limits, pagination, or bounded streaming |
| Unbounded `flatMap` concurrency | Too many concurrent operations | Bound concurrency and queues |
| Assuming reactive is automatically faster | Server/pool/query is the real bottleneck | Benchmark p95/p99 |
| Creating a MongoClient per request | Connection churn | Use a singleton client lifecycle |
| Increasing maxPoolSize indefinitely | Server saturation | Measure checkout waits and server capacity |
| Catching or `onErrorResume` swallowing all errors | Masks outages and consistency errors | Categorize errors, log, and emit metrics |
| Retrying an entire write pipeline blindly | Can duplicate side effects | Enforce idempotency and targeted retry policies |
| Using ThreadLocal as reactive context | Thread switching | Use Reactor Context and tracing integration |
| Subscribing to transaction operations separately | Breaks sequencing/session lifetime | Compose inside a single reactive transaction |
| Failing to close cursors/clients | Resource leaks | Manage lifecycle and cleanup properly |
| Using virtual threads without measuring pool | Pool limits still apply | Benchmark resource usage |
| Benchmarking only Publisher creation | No network I/O measured | Measure until terminal signal |
| Mixing up `com.mongodb.client` and reactive packages | Type/import mismatch | Separate imports/modules |
| Copying version `5.x.y` into build config | Dependency fails to resolve | Use an approved real version/BOM |
| Reactive MongoDB with blocking JDBC on event loop | Event loop still stalls | Use non-blocking alternative or offload |
| Missing timeouts | Requests can hang indefinitely | Configure proper timeout budgets |
| Assuming subscriber cancellation rolls back a write | Cancellation is not rollback | Ensure write idempotency and verification |

---

## 27. Decision Scorecard

Consider two options:

- **S:** Spring MVC + Java Sync Driver (optionally with virtual threads).
- **R:** Spring WebFlux + Java Reactive Streams Driver + Reactor.

Define mandatory criteria first:

1. Does it meet concurrency at peak traffic?
2. Are end-to-end p95/p99 latencies under SLO?
3. Can the team operate and debug it?
4. Do all dependencies on the critical path fit the execution model?
5. Do the connection pool and DB throughput sustain the load?
6. Are transactions, authorization, and observability correct?
7. Are migration cost and rollback acceptable?

**Illustrative** scorecard, not a MongoDB benchmark:

| Criterion | S | R |
| --- | --- | --- |
| Existing Spring MVC and blocking JDBC | Strong fit | Requires offloading/redesign |
| WebFlux + WebClient already in use | Requires bridge | Strong fit |
| Large imperative codebase | Low transition cost | Major migration |
| Continuous SSE/streams | Requires thread/cursor planning | Easy stream composition |
| High non-blocking I/O fan-out | Virtual threads worth testing | Natural model |
| Imperative transactions | Straightforward | Needs reactive session/context |
| Very high request concurrency | Benchmark platform/virtual threads | Benchmark Reactor/DB pool |
| Team inexperienced with Reactor | Easy to adopt | Higher bug risk |
| Single fast/slow MongoDB query | Inconclusive | Inconclusive |

**Never decide using an arbitrary total score if mandatory requirements are violated**, such as security, transaction correctness, or SLOs.

---

## 28. Hands-On Exercises

### Exercise 1 — Basic Driver Selection

A Spring MVC CRUD application with blocking JDBC libraries and moderate traffic. Which driver should you start with?

**Guidance Answer:** Sync Driver, because it matches the execution model and is simpler.

### Exercise 2 — WebFlux End-to-End

A Spring WebFlux application uses WebClient and SSE. What is the risk of calling the Sync Driver on the event loop?

**Answer:** Blocking the event loop while waiting on MongoDB, stalling many other requests.

### Exercise 3 — Namespaces

Distinguish between `com.mongodb.client.MongoClient` and `com.mongodb.reactivestreams.client.MongoClient`.

### Exercise 4 — Cold Publisher

Does the snippet:

```java
Publisher<Document> p =
    collection.find(Filters.eq("_id", "O-101")).first();
```

guarantee that a DB command has been sent?

**Answer:** No; reactive driver publishers are cold and require a subscription.

### Exercise 5 — Two Subscriptions

Subscribing to the same Publisher twice can trigger how many DB operations?

**Answer:** Two independent operations if there is no caching/sharing layer.

### Exercise 6 — Empty Mono

Sync `first()` with no matching record can return `null`. What will reactive `Mono.from(first())` do?

**Answer:** Complete empty; it never emits `null`.

### Exercise 7 — map and flatMap

In Reactor, when a helper method returns `Mono<String>`, should you use `map` or `flatMap` to avoid `Mono<Mono<String>>`?

**Answer:** `flatMap`.

### Exercise 8 — WebFlux block

Why is `Mono.from(publisher).block()` in an event-loop handler a bug? How do you fix it?

**Answer:** It blocks the event loop. Return `Mono` to the framework; if a blocking library is unavoidable, offload it with bounded limits.

### Exercise 9 — fromCallable Bridge

Write a bridge to call the Sync Driver in WebFlux via `Mono.fromCallable` and `Schedulers.boundedElastic()`. Does it make the I/O natively non-blocking?

**Answer:** No, it only shifts blocking execution onto bounded worker threads.

### Exercise 10 — Backpressure

The producer can emit 1,000 items/s while the consumer handles 20 items/s. How do you bound concurrency and avoid holding all items in RAM?

### Exercise 11 — collectList

Why is `Flux.from(collection.find()).collectList()` dangerous if a collection has tens of millions of documents?

### Exercise 12 — Connection Pools

With 4 app instances, 3 servers, and `maxPoolSize` 100/server, what is the theoretical maximum number of pooled connections?

**Answer:** 1,200, excluding monitoring/connection overhead.

### Exercise 13 — Singleton Client

Why shouldn't you create and close `MongoClient` on every HTTP request?

### Exercise 14 — Virtual Threads

Why do Java 21 virtual threads make the Sync Driver worth considering in high-concurrency systems? Which limits do not change?

**Answer:** They reduce platform-thread overhead for blocking tasks, but DB pool and server limits still apply.

### Exercise 15 — Query Plan

If the same MongoDB query performs a `COLLSCAN` on both drivers, will switching from Sync to Reactive guarantee lower latency?

**Answer:** No; you need query/index optimization.

### Exercise 16 — Retry

Why can adding Reactor `retry(3)` to `updateOne($inc)` cause business logic issues?

### Exercise 17 — Timeouts

Distinguish between server selection timeout, pool checkout wait, socket timeout, `maxTimeMS`, and Reactor `timeout`.

### Exercise 18 — Cancellation

An HTTP client cancels a reactive subscription immediately after sending a MongoDB write. Can you guarantee the write was rolled back?

**Answer:** No. You need idempotency, verification, and transaction semantics.

### Exercise 19 — Transactions

Why must reactive transactions preserve the same `ClientSession` and sequencing? Should you manually `subscribe()` to each write command individually?

### Exercise 20 — Reactive Context

Why can plain `ThreadLocal` lose `requestId` in a reactive chain? What does Reactor Context solve?

### Exercise 21 — Change Streams

A service streams MongoDB changes to SSE clients. Which driver should be considered, and what else is needed besides backpressure?

**Hint:** Reactive for streaming, plus resume tokens, retention planning, slow-consumer policies, and checkpoints.

### Exercise 22 — Benchmark

Design a comparison table between Sync and Reactive with identical dataset, indexes, read preference, `maxPoolSize`, concurrency, TLS, JVM, and warmup. List at least seven metrics.

### Exercise 23 — Flawed Benchmark

A Reactive benchmark measures only the time to invoke `collection.find(...)` and concludes it is faster than Sync `first()`. What is the flaw?

**Answer:** It did not subscribe or await a terminal signal, so it never measured the MongoDB operation.

### Exercise 24 — Spring Data

Distinguish between `MongoTemplate` and `ReactiveMongoTemplate`, and between `MongoRepository` and `ReactiveMongoRepository`.

### Exercise 25 — Mixed Drivers

A service uses both Sync and Reactive. What resource and configuration issues must be monitored?

**Hint:** Two clients/pools, timeout/TLS/auth alignment, dependency versions, transaction ownership, monitoring, and memory.

### Exercise 26 — Single-Query Service

An API spends most of its time waiting on MongoDB, but concurrency is low and latency is 15ms. Should it be rewritten to Reactor?

**Guidance Answer:** Not enough evidence; measure concurrency, SLOs, and maintenance cost first.

### Exercise 27 — Proper Reactive Output

Write a service method returning `Mono<String>` chained from `find().first()` and handling not-found without calling `block()`.

### Exercise 28 — onErrorResume Bug

A piece of code converts all MongoDB errors into `Mono.empty()`. What are the consequences for HTTP 404/200 responses and incident monitoring?

### Exercise 29 — Ownership Cost

A team of 5 Java developers unfamiliar with Reactor has a Spring MVC app with many blocking dependencies. List the learning, migration, testing, and debugging costs of switching drivers.

### Exercise 30 — Making the Decision

Given three products:

1. A batch migration CLI tool.
2. A Spring WebFlux API integrating with multiple reactive downstreams.
3. Spring MVC running on Java 21 virtual threads.

Choose a sensible default driver for each application and justify using SLOs, execution models, and resource limits.

---

## 29. Production Checklist

### Architecture

- [ ] Driver matches the Spring MVC/WebFlux/virtual-thread execution model.
- [ ] No unexpected blocking calls on the event loop.
- [ ] No manual `subscribe()` calls in services without clear ownership.
- [ ] Session/transaction lifecycle managed consistently.
- [ ] Reactive context/security/tracing propagation controlled.
- [ ] Streaming pipelines have cancellation and backpressure policies.

### Connections and Data

- [ ] Singleton `MongoClient` aligned with application lifecycle.
- [ ] Pool size, `maxConnecting`, and timeouts benchmarked.
- [ ] URI/TLS/auth managed via secrets.
- [ ] Query filters, sorts, projections, and indexes match workload.
- [ ] Batch sizes and pagination do not materialize unbounded datasets.
- [ ] Retries have an idempotency strategy and do not swallow errors.

### Monitoring

- [ ] API p50/p95/p99 latency, RPS, and error rates tracked.
- [ ] MongoDB command durations and pool checkout waits tracked.
- [ ] JVM CPU, heap, GC, thread count, and scheduler queues tracked.
- [ ] Atlas/server CPU/disk, query targeting, and replica lag tracked.
- [ ] Tracing carries `requestId` across async boundaries.
- [ ] Log redaction prevents exposing query literals or credentials.

### Delivery

- [ ] Driver/JDK/MongoDB Server/Spring Data versions pinned and compatible.
- [ ] Integration tests cover success, not-found, duplicate, timeout, and cancellation.
- [ ] Load tests use realistic concurrency and data.
- [ ] Rollback plan in place when changing driver or architecture.
- [ ] Write latency, pool/DB CPU, and application memory impact measured.
- [ ] Team has runbooks for investigating reactive deadlocks/event-loop blocking.

---

## 30. Summary

Both the **MongoDB Java Sync Driver** and the **Reactive Streams Driver** are valid tools for accessing MongoDB; the difference lies in their programming and concurrency models:

1. **Sync** returns results directly via a blocking API and suits Spring MVC, CLI/batch, imperative code, and blocking integrations; it is also worth considering with Java 21 virtual threads.
2. **Reactive** returns cold `Publisher`s that execute upon subscription; it suits Reactor/WebFlux, streaming, and non-blocking I/O pipelines.
3. **Non-blocking does not automatically mean faster.** Query plans, indexes, connection pools, MongoDB Server, and network still determine much of the latency.
4. **Reactive requires understanding demand, cancellation, and error signals.** Do not call `block()` on event loops, and do not subscribe to side effects outside the request lifecycle.
5. **Both require a reused `MongoClient`, connection pooling, TLS, timeouts, proper transactions, and monitoring.**
6. **Fair benchmarks** must measure completion/end-to-end p95/p99, throughput, errors, CPU, memory, and pool waits—not merely Publisher instantiation time.
7. **Choosing a consistent execution model across the entire request path** matters more than picking an API that looks modern.

A good driver choice is one that **meets SLOs, preserves data correctness, is easy to operate, and carries an acceptable maintenance cost** in your system.

### Official Documentation and References

- [MongoDB Java Sync Driver — Overview](https://www.mongodb.com/docs/drivers/java/sync/current/) — synchronous API, support, and compatibility.
- [MongoDB Java Sync Driver — Get Started](https://www.mongodb.com/docs/drivers/java/sync/current/get-started/) — BOM, dependencies, MongoClient, and queries.
- [MongoDB Java Sync Driver — CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/) — reads, writes, and BSON mapping.
- [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — maxPoolSize, connections, and pool settings.
- [MongoDB Java Sync Driver — Limit Server Execution Time](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/) — timeouts and CSOT.
- [MongoDB Reactive Streams Driver — Overview](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/) — asynchronous API.
- [MongoDB Reactive Streams Driver — Download and Install](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/get-started/download-and-install/) — BOM, reactive artifact, and Reactor.
- [Reactive Streams Driver — Sample Subscriber Implementations](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/custom-implementations/) — cold publishers, demand, and subscriptions.
- [Reactive Streams Driver — Query Documents](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/read/) — find, queries, and result publishers.
- [Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/crud/transactions/) — sessions and transaction management.
- [MongoDB — Connection Pool Tuning](https://www.mongodb.com/docs/manual/tutorial/connection-pool-performance-tuning/) — pool checkout and concurrency.
- [MongoDB — Explain](https://www.mongodb.com/docs/manual/reference/explain-results/) — performance and query plans.
- [Spring Data MongoDB — Reference](https://docs.spring.io/spring-data/mongodb/reference/) — imperative/reactive templates, repositories, and transactions.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/) — Mono, Flux, schedulers, backpressure, and Context.
- [Reactive Streams Specification](https://www.reactive-streams.org/) — Publisher/Subscriber/Subscription protocol.
- [Java Virtual Threads — OpenJDK JEP 444](https://openjdk.org/jeps/444) — Java 21 virtual threads.
