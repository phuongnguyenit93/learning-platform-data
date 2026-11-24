# Loading Data from Non-Reactive Stores and Consequences When Integrating into Spring WebFlux

> **Context:** Spring Boot web runtime, parent menu **Reactive execution**. This lesson analyzes what happens when an HTTP handler returns `Mono`/`Flux` yet must read data from stores exposing **synchronous, thread-blocking** APIs, such as JDBC, JPA/Hibernate, file-reading SDKs, search libraries, or synchronous HTTP clients. Runnable examples use Spring Boot **4.1.2**, Java **17+**, Maven, and H2 via `JdbcTemplate`. Principles apply to Spring Boot 3.x as well, using matching starters/versions.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why a **reactive controller does not turn a blocking repository into a non-blocking source**, even when signatures return `Mono<T>` or `Flux<T>`.
2. Pinpoint the effects of calling JDBC/JPA directly on the WebFlux **event loop**: latency, throughput, queue wait time, thread resources, and cascading stalls.
3. Correctly apply `Mono.fromCallable(() -> blockingRepository.find(...)).subscribeOn(Schedulers.boundedElastic())`, understanding which parts remain blocking.
4. Bound load across **database connection pools**, concurrent queries, queues, backpressure, timeouts, and payload sizes.
5. Properly handle empty results, exceptions, cancellation, and **transaction boundaries** when crossing from Reactor into imperative repositories.
6. Choose sensibly between a **temporary blocking bridge**, Spring MVC suited for blocking workloads, or migrating to a genuine reactive driver such as R2DBC.

## 1. What Is a "Non-Reactive Store"?

A **non-reactive data store** in this lesson is a data source exposed via an **imperative/synchronous** API: a call returns only after finishing or throwing an exception. While waiting, the calling thread may sit blocked.

Familiar examples:

| Technology/API | Illustrative signature | Property to understand |
| --- | --- | --- |
| JDBC, `JdbcTemplate` | `Book findById(long id)` or `List<Book> findAll()` | Waits for connection, sends SQL, awaits results; uses calling thread to wait |
| Spring Data JPA/Hibernate | `Optional<Book> findById(Long id)` | Imperative repository; lazy loading and transactions/JPA sessions raise separate concerns |
| Spring Data JDBC | `CrudRepository<T, ID>` returning objects/collections | Lighter ORM than JPA yet still built on blocking JDBC |
| Synchronous HTTP client | `restClient.get()...body(...)` | Thread waits on network I/O |
| Legacy files/SDKs | `InputStream.read()`, libraries with synchronous-only APIs | Thread waits on I/O or other resources |
| R2DBC/Spring Data R2DBC | `Mono<T> findById(ID id)` | Reactive SQL access model, **when driver and I/O path truly support it** |

**Reactive Streams** is a `Publisher`, `Subscriber`, `Subscription` contract with demand, emission, completion, error, and cancellation signals. It does not magically turn wrapped calls into non-blocking I/O. If `JdbcTemplate.query(...)` still waits synchronously for DB responses, JDBC still occupies a thread throughout that wait even inside a `Mono`.

Distinguish three terms:

- **Non-blocking I/O:** waiting on network/disk does not force an application thread to sit idle; the runtime notifies when progress can resume.
- **Asynchronous execution:** work runs deferred or on another thread; that work **may still be blocking**.
- **Reactive API:** expresses computation chains as Publishers/operators with demand, errors, and cancellation; return types alone do not guarantee the entire data source is non-blocking.

The `boundedElastic` bridge isolates synchronous work from the event loop, yet **does not replace JDBC with R2DBC**.

## 2. Why Is WebFlux Sensitive to Blocking Calls?

Spring WebFlux is built for non-blocking request pipelines. In the common Reactor Netty deployment, **a small set of event-loop threads** handles connection events, executes I/O callbacks, and advances pipelines.

If a handler runs a JDBC query directly on the event loop:

~~~java
// WRONG: illustrative WebFlux controller; repository.findById uses blocking JDBC.
@GetMapping("/api/books/{id}")
Mono<Book> get(@PathVariable long id) {
    Book book = repository.findById(id); // blocks the event-loop thread
    return Mono.justOrEmpty(book);       // Mono created only after query finishes
}
~~~

If SQL takes 300 ms, the event-loop thread is pinned at the JDBC call for that duration. Meanwhile, that thread cannot serve other ready requests assigned to it. When many concurrent requests wait on DB, timeouts, tail latency (p95/p99), and queues climb sharply.

Comparison:

~~~text
UNSAFE (JDBC directly on event loop)

Reactor Netty event loop
  -> route/controller
  -> JDBC query: WAIT 300 ms  [event loop held]
  -> build Mono/response
  -> write bytes

BETTER WHEN JDBC CANNOT YET BE REPLACED

Reactor Netty event loop
  -> route/controller -> build Mono.fromCallable(...).subscribeOn(...)
  -> return Publisher to WebFlux
  -> event loop continues handling other work

boundedElastic worker
  -> acquire JDBC connection -> run SQL -> map result
  -> emit onNext/onComplete or onError to pipeline
  -> WebFlux writes HTTP response
~~~

The second path keeps the event loop free during DB waiting; **a boundedElastic worker is still occupied** and JDBC connections remain finite resources.

### Specific Consequences of Doing It Wrong

- **Head-of-line blocking:** one slow request stalls the thread and delays unrelated requests, even ones never touching the database.
- **Degraded tail latency:** p95/p99 spikes well before CPU saturates because time goes to I/O waiting.
- **Thread starvation:** pinned event loops delay header parsing, body reading, response writing, and even health checks.
- **Connection starvation:** more concurrent queries than available connections elongate pool wait times even after offloading.
- **Loss of low-thread scalability:** if all workload is blocking, throughput is ultimately capped by worker and connection counts.
- **Poor load regulation:** huge queues absorb incoming requests only to postpone timeouts and inflate memory.

A quick back-of-the-envelope capacity check: if 50 requests/sec on average execute a **200 ms** query, the system needs around **10 concurrent queries** just to keep up ideally, before accounting for latency variance, queues, and other overhead. With only 5 connections in the pool, raising thread counts into the hundreds will not let the DB run 10 concurrent queries. This is an estimation model, not a benchmark prediction.

## 3. Wrapping a Blocking Repository Properly

Reactor's standard pattern:

~~~java
Mono<Book> result = Mono.fromCallable(() -> repository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

**Why is this right?**

1. `Mono.fromCallable(...)` **defers the call** until subscription. JDBC has not run while the controller assembles the pipeline.
2. `subscribeOn(Schedulers.boundedElastic())` moves subscribing and executing the callable source onto a worker built for blocking tasks.
3. `Mono` emits **one** result and completes; if the callable returns `null`, `Mono` completes empty; if it throws, `Mono` emits `onError`.
4. WebFlux owns the HTTP subscription; the controller **returns** the Publisher without calling `subscribe()`.
5. When the callback finishes, downstream operators continue in the appropriate scheduler context; never assume all operators automatically run on the event loop.

**What does NOT happen:** the thread executing JDBC does not vanish; it still waits for the result set or connection. Nor can backpressure tell an active `queryForObject` call to "return half a row".

### Common Broken Patterns

~~~java
// 1. WRONG: runs JDBC immediately when building Mono.
Mono<Book> a = Mono.just(repository.load(id));

// 2. WRONG: JDBC already ran; publishOn afterward cannot rescue the event loop.
Mono<Book> b = Mono.just(repository.load(id))
        .publishOn(Schedulers.boundedElastic());

// 3. WRONG: block() stalls right inside the WebFlux handler.
Book c = reactiveService.fetch(id).block();

// 4. WRONG: manual subscribe returns early and detaches from HTTP lifecycle.
repositoryMono.subscribe();
return Mono.empty();
~~~

Sometimes `publishOn` is appropriate to switch **subsequent operators** to another scheduler. For a blocking synchronous source, `subscribeOn` right after `fromCallable` states intent clearly. Placing `publishOn` **after** a blocking call that already executed cannot undo event-loop blocking.

### When Dealing with `Optional<T>`

~~~java
// Right: Optional resolves inside the callable, preventing pre-subscribe execution.
Mono<Book> result = Mono.fromCallable(() ->
        repository.findById(id).orElse(null))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` treats `null` as an empty completion. Yet "not found" may require HTTP 404; the application decides via `switchIfEmpty(Mono.error(...))` at the HTTP boundary.

### When Data Has More Than One Element

~~~java
// Illustrative: repository.findPage() returns List<Book> via JDBC.
Mono<List<Book>> page = Mono.fromCallable(() -> repository.findPage(0, 50))
        .subscribeOn(Schedulers.boundedElastic());

Flux<Book> items = page.flatMapMany(Flux::fromIterable);
~~~

An entire **page** is fetched by JDBC and materialized as a list on the worker before `Flux` emits elements. `Flux` expresses demand-driven downstream processing/encoding, yet does not make that JDBC query stream non-blocking.

Never write `Flux.fromIterable(repository.findAll())` directly on the event loop if `findAll()` executes a blocking query immediately. Likewise, avoid `Flux.fromStream(...)` over a connection-bound JPA/ResultSet stream without explicit transaction, resource-closing, and scheduler management; closing the connection before the subscriber finishes fails reads, while holding a connection open across a long streaming response starves the pool.

## 4. Schedulers, Pools, and Queues: Real-World Limits

`Schedulers.boundedElastic()` is a useful default scheduler for isolating legacy blocking calls. It **bounds thread count and queue size**, making it safer than an unbounded thread pool, though it does not eliminate overload. Under certain Java 21+ configurations, Reactor can back boundedElastic with virtual threads; the Java 17 examples here use platform threads.

| Resource | Role | What to measure / limit |
| --- | --- | --- |
| Netty event loops | Non-blocking HTTP I/O | Never run JDBC/JPA, sleep, or block on event loops |
| boundedElastic workers | Execute blocking callables | Running tasks, queue depth, scheduling wait time |
| HikariCP connection pool | Provide JDBC connections | Maximum pool size, active/idle/pending connections, connection timeout |
| Database server | Execute SQL and maintain transactions | Slow queries, locks, query plans, actual connections, CPU/I/O |
| Reactor operators | Compose requests and results | `flatMap` concurrency, prefetch, buffering, error/cancel |
| HTTP clients and gateways | Await responses | Timeouts, retries, connection/latency limits, disconnects |

**Never** raise boundedElastic thread counts endlessly just because the DB is slow. Queued threads pile onto connection-acquisition queues, then DB locks/query queues. Each layer adds latency and timeouts, hurting p99 and masking problems until saturation hits.

One throttling technique is bounding concurrent JDBC queries:

~~~java
// Illustrative inside a service; findOne(id) is a properly wrapped JDBC Mono<Book>.
Flux<Book> findMany(List<Long> ids) {
    return Flux.fromIterable(ids)
            .flatMapSequential(this::findOne, 4);
}
~~~

`flatMapSequential` subscribes to at most **4** inner Publishers concurrently and **preserves input emission order** (potentially buffering early completions). `flatMap` also accepts concurrency, though output order may vary. Concurrency 4 is illustrative; choose based on pool and query load rather than CPU count alone. If multiple HTTP requests execute this concurrently, **total** concurrent queries exceed 4: per-request caps are not global caps. Add global bulkheads/semaphores or ingress throttling when required.

### Three Non-Interchangeable Timeout Layers

1. **Connection acquisition timeout:** time spent waiting for a pool connection; e.g., `spring.datasource.hikari.connection-timeout=2000` tells Hikari to wait up to ~2 seconds for a connection before failing. Not the maximum query duration.
2. **Query/statement timeout:** SQL execution limit enforced by JDBC/driver/database (e.g., `JdbcTemplate.setQueryTimeout(...)` or DB settings). Whether drivers actually cancel active queries depends on driver support.
3. **Reactive response timeout:** `.timeout(Duration.ofSeconds(3))` errors the Reactor chain after the deadline; it may cancel the subscription yet **cannot guarantee interrupting an already-blocked JDBC call** or rolling back prior side effects.

Align timeouts across layers: do not give an API a 500 ms deadline while DB connection acquisition hangs far longer unmonitored; and never hammer an already-saturated DB with retries. Base deadlines on real SLOs and test under slow queries and exhausted pools.

## 5. Runnable Example: WebFlux Reading H2 via `JdbcTemplate`

Demo goal: observe **reactive controller**, **blocking JDBC repository**, and **scheduler handoff**. No external DB install needed: H2 creates tables and seed data at startup. Example uses Spring Boot 4.1.2 from Maven Central and JDK 17+.

Project structure:

~~~text
webflux-blocking-store/
  pom.xml
  src/main/java/com/example/blockingstore/
    BlockingStoreApplication.java
    BookDto.java
    BookRepository.java
    BookService.java
    BookController.java
  src/main/resources/
    application.properties
    schema.sql
    data.sql
~~~

### 5.1. Maven Dependencies

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-blocking-store</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-webflux` provides the reactive web runtime with Reactor Netty when no MVC web starter overrides it; `spring-boot-starter-jdbc` provides Spring JDBC/HikariCP without creating a reactive database driver. `h2` is an in-memory SQL store for the demo. JSON bodies are handled by codecs configured by WebFlux/Boot.

### 5.2. Startup and DTO

**`src/main/java/com/example/blockingstore/BlockingStoreApplication.java`**

~~~java
package com.example.blockingstore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BlockingStoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(BlockingStoreApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/blockingstore/BookDto.java`**

~~~java
package com.example.blockingstore;

public record BookDto(long id, String title, int priceCents) {}
~~~

A Java 17 `record` defines an immutable DTO for JSON serialization. `priceCents` uses integers to avoid floating-point rounding when representing prices.

### 5.3. Imperative Repository

**`src/main/java/com/example/blockingstore/BookRepository.java`**

~~~java
package com.example.blockingstore;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookRepository {
    private final JdbcTemplate jdbcTemplate;

    public BookRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<BookDto> findById(long id) {
        List<BookDto> rows = jdbcTemplate.query(
                "select id, title, price_cents from books where id = ?",
                (rs, rowNum) -> new BookDto(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getInt("price_cents")),
                id);
        return rows.stream().findFirst();
    }
}
~~~

This method is **blocking**: `jdbcTemplate.query(...)` waits for the query and builds `List<BookDto>` before returning. Because `id` is the primary key, at most one row returns, fitting the example. Queries returning thousands of rows must paginate/limit results rather than loading unbounded sets like this.

**Query security note:** `where id = ?` uses a bind parameter, avoiding concatenating user input directly into SQL. Real endpoints still require authorization and input validation per business rules.

### 5.4. Service Acting as Blocking → Reactive Bridge

**`src/main/java/com/example/blockingstore/BookService.java`**

~~~java
package com.example.blockingstore;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<BookDto> findById(long id) {
        return Mono.fromCallable(() -> repository.findById(id).orElse(null))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

This is the **most important boundary** in the example. `findById(...)` immediately returns a Publisher description; when WebFlux subscribes, the callable runs on a boundedElastic worker. Inside the callable, JDBC still blocks that worker. No manual `Thread` creation or `subscribe()` is needed.

### 5.5. Reactive Controller

**`src/main/java/com/example/blockingstore/BookController.java`**

~~~java
package com.example.blockingstore;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<BookDto> findById(@PathVariable long id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Book not found")));
    }
}
~~~

The controller **knows nothing of SQL details** and **never blocks**. If the book exists, `Mono<BookDto>` emits one DTO for WebFlux to JSON-encode and write. If no row exists, `switchIfEmpty` turns empty into an HTTP 404 error. Unexpected DB failures propagate via `onError`; production apps need an explicit error-mapping policy.

### 5.6. H2, Connection Pool, and Sample Data

**`src/main/resources/application.properties`**

~~~properties
server.port=8080

spring.datasource.url=jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=

spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.connection-timeout=2000

spring.sql.init.mode=always
~~~

Pool size is capped at 5 JDBC connections to make DB limits easy to observe (illustrative value only). `connection-timeout=2000` is a **2,000 ms connection-acquisition wait limit**, not a query timeout. The `catalog` DB resides in memory and disappears when the process exits; never use this config for persistent data.

**`src/main/resources/schema.sql`**

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price_cents INTEGER NOT NULL
);
~~~

**`src/main/resources/data.sql`**

~~~sql
INSERT INTO books (id, title, price_cents) VALUES
    (1, 'Reactor in Practice', 2500),
    (2, 'SQL Basics', 1800),
    (3, 'Web Runtime', 3100);
~~~

Boot runs the schema/data initialization scripts against H2 as configured; in real apps, prefer **one** schema mechanism (Flyway/Liquibase migrations or controlled scripts) to avoid colliding with Hibernate DDL.

### 5.7. Build, Run, Verify

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Expect HTTP 200 with the following JSON body:

~~~json
{"id":1,"title":"Reactor in Practice","priceCents":2500}
~~~

Query the second record:

~~~bash
curl -i http://localhost:8080/api/books/2
~~~

Expected body:

~~~json
{"id":2,"title":"SQL Basics","priceCents":1800}
~~~

Query a non-existent ID:

~~~bash
curl -i http://localhost:8080/api/books/999
~~~

Expect HTTP 404; exact error body JSON depends on Spring Boot configuration, so this lesson does not hardcode error JSON structure.

On PowerShell, use `curl.exe -i http://localhost:8080/api/books/1` or `Invoke-RestMethod http://localhost:8080/api/books/1`. `mvn package` followed by `java -jar target/webflux-blocking-store-0.0.1-SNAPSHOT.jar` also runs once Maven downloads dependencies.

### 5.8. Pinpointing Exactly Which Part Is Blocking

| Moment | Component | Can a thread be held? |
| --- | --- | --- |
| Server receives `GET /api/books/1` | Reactor Netty, WebFlux routing | No JDBC call; non-blocking web runtime handling |
| Controller calls `service.findById(1)` | Builds `Mono.fromCallable` + `subscribeOn` | Query has not executed yet |
| Runtime subscribes to pipeline | Reactor schedules callable | Event loop does not wait directly on JDBC |
| Worker calls `repository.findById(1)` | boundedElastic → HikariCP → JDBC → H2 | **Yes:** worker waits for connection/query |
| Callable returns `BookDto` | Mono emits value and completes | Worker is freed when callable finishes |
| Framework encodes DTO | WebFlux HTTP codec | Response written via web runtime |

The result **stays reactive at the HTTP layer**, yet **the overall data path still ties up a thread whenever JDBC waits**. Never describe it as "end-to-end non-blocking".

## 6. JDBC/JPA Transactions Do Not Automatically Follow Reactor Context

This is a subtle pitfall: **imperative transactions** and **reactive transactions** use different context-propagation mechanisms.

- With `PlatformTransactionManager` for JDBC/JPA, Spring typically binds transaction/connection state to the **current thread** via `ThreadLocal`.
- With `ReactiveTransactionManager` for R2DBC, Spring uses **Reactor Context** bound to the subscription instead of a fixed thread.
- Moving a callable to boundedElastic switches threads. A transaction opened on the event loop **does not follow** onto the worker via `subscribeOn`.
- Placing `@Transactional` on a method **returning `Mono`** that merely builds a Publisher misleads imperative transactions: the method returns before JDBC even runs. Do not rely on it to span JDBC I/O.

### Proper Design for a JDBC Transaction

Place all operations sharing a transaction inside **one imperative `@Transactional` method**, invoked **inside the callable** on boundedElastic. The transaction must open, execute, and close on that same synchronous thread. Example:

~~~java
// Illustrates transaction boundary; OrderDto/OrderRow/Dao types assumed
// defined in project. Not a standalone program.
@Service
public class LegacyOrderReader {
    private final JdbcOrderDao dao;

    public LegacyOrderReader(JdbcOrderDao dao) {
        this.dao = dao;
    }

    @Transactional(readOnly = true)
    public OrderDto load(long id) {
        OrderRow row = dao.findById(id);
        return new OrderDto(row.id(), row.totalCents());
    }
}
~~~

Then invoke it from **another bean** so Spring's AOP proxy enforces the transaction:

~~~java
// Illustrative in a reactive service; reader is an injected LegacyOrderReader bean.
public Mono<OrderDto> findOrder(long id) {
    return Mono.fromCallable(() -> reader.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

When multiple queries belong to one transaction, keep the whole sequence `dao.loadA(); dao.loadB(); ...` inside that imperative `@Transactional` method. Never split operations requiring the same transaction across `flatMap` branches that might run on different workers, or the thread-bound transaction is lost. With JPA, never return uninitialized proxy entities/lazy collections outside the closed transaction/session to serialize in WebFlux; map to DTOs **inside** the transaction scope.

**Self-invocation:** when a method in the same bean calls `this.load(...)`, Spring's proxy-based `@Transactional` may be bypassed. Place the transaction boundary on a separate injected bean or use `TransactionTemplate` inside the callable for explicit control.

### If You Want Genuine Reactive Transactions

Migrate data access to R2DBC with a compatible driver and use `ReactiveTransactionManager`/`TransactionalOperator`. This is more than swapping repository return types: review schema mapping, queries, transaction semantics, driver support, database compatibility, and app dependencies. Spring Data R2DBC differs from Spring Data JPA/Hibernate and cannot be treated as a feature-for-feature drop-in replacement.

## 7. Reading Multiple Records: Paging, Buffering, and Backpressure

Even when the HTTP layer returns `Flux<BookDto>`, **JDBC still waits synchronously** at the query layer. Never assume `Flux` makes JDBC fetch row-by-row upon `request(1)`.

### How Can a Large List Consume RAM?

~~~java
// WRONG if query returns huge data: findAll() still blocks
// and may materialize the entire result into a List before Flux sees one item.
return Flux.fromIterable(repository.findAll());
~~~

Even when written as:

~~~java
// Better for the event loop, yet still buffers the entire dataset.
return Mono.fromCallable(repository::findAll)
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(Flux::fromIterable);
~~~

the event loop stays free, yet the entire list sits in RAM and the query holds a JDBC worker and connection while reading. For large datasets, prefer **keyset pagination or bounded pagination** with capped page sizes.

A pagination approach:

~~~java
// Illustrative; repo.readPage(pageNo, 100) returns List<BookDto> via JDBC.
// All pages are read sequentially, capped at 100 rows per page.
// Real implementations need stop conditions and stable ordering.
Flux<BookDto> books = Flux.range(0, 10)
    .concatMap(pageNo ->
        Mono.fromCallable(() -> repo.readPage(pageNo, 100))
            .subscribeOn(Schedulers.boundedElastic()))
    .concatMapIterable(page -> page);
~~~

This snippet uses **10 known pages** for illustration; real applications paginate until data ends using cursors/keysets rather than hardcoding page counts. `concatMap` preserves order and avoids running all queries concurrently. While `Flux` can stream pages downstream, **each page is still materialized blocking via JDBC** first.

### Bounding Parallel Access

If processing a list of 100 IDs where each uses its own `Mono.fromCallable`, use `flatMapSequential(id -> lookup(id), concurrency)` or `flatMap(..., concurrency)` to cap in-flight queries **within one pipeline**. Add global load caps across concurrent HTTP requests; align limits with the Hikari pool and database capacity.

When fetching a batch of IDs, a single parameterized `WHERE id IN (...)` query, sensible batching, or well-indexed joins often beat 100 separate queries; avoid **N+1 queries** in JPA. Fix query plans, indexes, and pagination before simply adding scheduler threads.

### How Far Does Backpressure Reach?

`request(n)` controls how many elements reactive downstream wants. It can pace consumption and subsequent query launches when pipelines are structured properly. Once a synchronous `JdbcTemplate.query` starts, however, demand **has no general way to pause mid-way at row 37**. Similarly, Netty enforcing backpressure does not mean a JDBC driver supports Reactive Streams. Document this **non-reactive boundary** clearly in your design.

## 8. Errors, Timeouts, Cancellation, and Retries When the Source Is Still Blocking

With `Mono.fromCallable`, exceptions thrown by JDBC or the pool become `onError` signals. Example:

~~~java
// Illustrative in a service; dao.readById(id) uses JDBC.
return Mono.fromCallable(() -> dao.readById(id))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(
                java.sql.SQLTransientException.class,
                ex -> new DataAccessTemporarilyUnavailableException(ex));
~~~

This is an illustrative snippet requiring imports and a project-defined `DataAccessTemporarilyUnavailableException`; `JdbcTemplate` also translates `SQLException` into Spring's `DataAccessException` hierarchy, so match the **actual runtime exception types** rather than assuming `SQLException` always appears directly.

### Why Is Reactor's Timeout Not Enough?

Suppose `timeout(3s)` errors after 3 seconds. Upstream receives cancel, yet the JDBC thread may still be waiting on a query or socket; the query may keep running until driver/DB timeouts fire or interruption/cancellation succeeds. Therefore combine:

- **Connection acquisition** timeout in Hikari.
- **Statement** and **network/socket** timeouts in the JDBC driver/database.
- **Reactive request** deadline at HTTP.
- **Concurrency and queue** caps, especially when the DB slows down.
- Selective retries only for transient errors, with backoff/jitter, capped attempts, and **idempotency**.

**Never blindly retry DB writes.** If a client times out after an INSERT already committed, retrying duplicates the write. Apply idempotency keys, DB constraints, transactions/outboxes, or reconciliation workflows per business requirements.

### Does Client Disconnect Automatically Stop SQL?

Never guarantee it. The HTTP layer can cancel the subscription so **not-yet-started** tasks never execute. Yet a JDBC call already inside the driver stops only if the API/driver genuinely supports cancellation. Cancel also never rolls back already-committed transactions or external side effects.

### Which Errors Map to Which HTTP Statuses?

- Record not found: `Mono.empty()` can map to **404** when defined by the contract.
- Invalid input: normally **400** with clear validation messages.
- Exhausted connection pool, database unreachable, or query error: server error or **503** when service is unavailable (per app policy), with internal logs/traces and without leaking SQL/stack traces to clients.
- Timeout: return an appropriate error status when the response has not committed; do not force one rigid code across unrelated causes/contracts.

Once a streaming response commits partially, you cannot rewrite headers/status to "return a fresh 503"; clients must handle mid-stream termination.

## 9. Observing and Testing So "Reactive" Is Not Just Skin-Deep

### Proving the Event Loop Does Not Block

Log thread names at two points:

~~~java
// Illustrative inside a service, not standalone source.
return Mono.fromCallable(() -> {
    log.info("JDBC thread={}", Thread.currentThread().getName());
    return repository.load(id);
}).subscribeOn(Schedulers.boundedElastic());
~~~

With the default platform-thread scheduler, JDBC thread names typically relate to `boundedElastic-...`; exact names are not an API contract, so do not assert thread names in tests. When inspecting controller entry or `doOnSubscribe`, remember operators/schedulers can run callbacks on different threads.

Test **real behavior**, not just thread names:

1. Inject controlled query slowness; send concurrent requests and measure p50/p95/p99.
2. While the DB is slow, call a non-DB endpoint; confirm the HTTP event loop still serves lightweight requests promptly.
3. Measure active/pending Hikari connections, boundedElastic queue depth, DB CPU, lock waits, and concurrency.
4. Shrink maximum pool size to force contention; verify requests time out / hit concurrency limits cleanly rather than queuing unboundedly.
5. Trigger client cancellation/timeout mid-query; check when the query actually stops and whether connections return cleanly to the pool.
6. Verify 404/5xx contracts, large payloads, cache misses, N+1 queries, and SQL injection resistance.
7. With JPA, test lazy loading/transactions across scheduler hops and fetch configurations.

### How to Interpret Measurements

| Observation | Hypothesis to check |
| --- | --- |
| Lightweight HTTP requests slow down when JDBC is slow | Blocking on the event loop or overloaded event loop |
| Hikari pending connections climb steadily | Submitting DB tasks faster than the pool can serve |
| boundedElastic queue swells | Blocking source saturated; add admission control, cut query latency, or scale capacity |
| Low DB CPU yet high latency | Waiting on pool, locks, network, query planning, or threads |
| Many workers stuck on the same query | N+1 queries, tiny pool, DB/lock contention, or unthrottled retries |
| RSS/heap climbs when returning `Flux` | Large dataset materialized, buffering, prefetch, or caching |
| HTTP times out while DB query keeps running | Cancellation failed to interrupt blocking I/O; enforce driver/DB timeouts |

In projects with Reactor debugging, tools like BlockHound can catch certain illegal blocking calls on non-blocking threads in dev/test. Use version-compatible tooling and never treat it as a replacement for load testing and DB monitoring; not every JDBC wait is detected automatically.

## 10. Choosing the Right Integration Strategy

| Situation | Practical choice | Trade-off |
| --- | --- | --- |
| WebFlux app must call an existing JDBC/JPA repository | `Mono.fromCallable(...).subscribeOn(boundedElastic())` + concurrency/timeout caps | Preserves Publisher contracts at web layer, yet queries still hold workers and JDBC connections |
| Most requests use JPA/JDBC and logic is synchronous | Consider **Spring MVC** with suitable container thread pool | Simpler model for blocking workloads; gives up non-blocking event-loop efficiency |
| High I/O concurrency, DB and driver support reactive | R2DBC/Spring Data R2DBC | Requires rewriting repositories, transactions, mappings, drivers, and re-benchmarking |
| Store has no reactive driver, API rarely changes | Blocking adapter isolated behind a service boundary | Allows gradual migration, requires managing scheduler/capacity |
| Continuous large reads | Pagination/keyset/batching or lifecycle-managed streaming | Cannot promise non-blocking JDBC streaming; must manage connections and lifecycles |
| Complex JPA transactions, lazy-loading, ORM features | Keep imperative JPA in dedicated transactions; consider MVC | "Returning Mono" does not transform ORM/transaction semantics |
| Long heavy read jobs or background work | Jobs/batch or separate service, bounded-concurrency queues | Shifts processing model / eventual consistency; avoids tying up long HTTP connections |

**Spring MVC + JDBC is not an anti-pattern.** WebFlux shines when multiple layers are truly non-blocking. If the main bottleneck is a synchronous database and concurrency demands are modest, Spring MVC can be easier to operate and debug. Choose based on workload shape, resource limits, and real measurements.

**R2DBC is not "reactive JPA".** Spring Data R2DBC has its own repository/template model and mapping rules, without lazy loading/cascades/sessions or full Hibernate features. Before migrating, evaluate transaction isolation, SQL drivers, complex schemas, and migration tooling.

## 11. Safe Step-by-Step Implementation Workflow

1. **Inventory every blocking point:** repository methods, JDBC/JPA, synchronous HTTP clients, filesystem, cache clients, SDKs, synchronous logging; mark boundaries clearly.
2. **Isolate clear adapters:** keep blocking calls in imperative DAO/service beans; wrap them in a reactive service using `fromCallable` and `subscribeOn(boundedElastic())`.
3. **Keep transactions atomic on one worker:** steps sharing a JDBC transaction sit in one imperative `@Transactional` method invoked through a proxy; never leak lazy entities outside.
4. **Enforce source limits:** connection pool, concurrent task cap, queue/bulkhead, page size, JDBC/query timeouts, and HTTP deadlines.
5. **Preserve error/empty semantics:** map 404, 400, 503 appropriately; never swallow exceptions or call `block()` in controllers.
6. **Measure under load:** verify event-loop responsiveness, connection acquisition waits, throughput, p99, memory, and disconnect cancellation behavior.
7. **Evaluate alternatives:** optimize SQL first, then assess whether workload justifies R2DBC or whether Spring MVC is simpler.
8. **Protect data contracts:** when changing persistence technology, verify mappings, transactions, caching, paging, ordering, and JSON output to prevent regressions.

## 12. Common Misconceptions

- **"Repository returns `Mono`, so JDBC is non-blocking."** False: a wrapper changes the API signature, not the underlying I/O mechanism.
- **"`Mono.just(jdbc.query(...))` is safe because Mono is lazy."** False: `Mono.just` arguments evaluate eagerly before creating the Mono; the query already ran.
- **"Putting `publishOn` after the query moves the query to a worker."** False: the query has already run or blocked on the calling thread before `publishOn` takes effect.
- **"`boundedElastic` makes the database reactive."** False: it offloads blocking calls, still tying up threads waiting for connections/queries.
- **"Adding worker threads increases DB throughput."** Not when the bottleneck is the pool, locks, or database capacity.
- **"`Flux.fromIterable(allRows)` streams from the DB."** Not when `allRows` was materialized upfront by a synchronous query.
- **"HTTP cancellation guarantees stopping JDBC."** False: depends on driver, query state, and cancellation support.
- **"`@Transactional` outside `Mono.fromCallable` always covers the query."** Not guaranteed for imperative thread-bound transactions; boundaries must sit in the right place.
- **"R2DBC and Spring Data JPA are identical apart from `Mono`."** False: transactions, mapping, ORM semantics, and drivers differ fundamentally.
- **"WebFlux is always faster than MVC."** False: outcomes depend on workload profile, concurrency, resource caps, DB, real I/O, and implementation.

## 13. Self-Check Scenarios with Answers

**Scenario A:** A WebFlux endpoint calls `jdbcTemplate.query(...)` directly and wraps the result in `Mono.just(...)`. What is wrong?

**Answer:** SQL runs immediately on the handler thread before the Mono exists; if that thread is a Netty event loop, it blocks. Use `Mono.fromCallable(() -> jdbcTemplate.query(...)).subscribeOn(Schedulers.boundedElastic())` and return the Publisher to the runtime.

**Scenario B:** Hikari pool has 5 connections, and you raise boundedElastic workers to 100. Do concurrent DB queries automatically rise to 100?

**Answer:** No. Concurrency is normally capped around the pool's available connections on that instance; the rest wait for connections or time out. The database may also impose its own limits.

**Scenario C:** Does `Mono.fromCallable(repository::findAll).flatMapMany(Flux::fromIterable)` read non-blocking row-by-row from the DB?

**Answer:** No. `findAll()` still builds a list synchronously; adding `subscribeOn` moves blocking onto a worker instead of the event loop. To cut memory usage, use bounded pagination/batching.

**Scenario D:** You put `@Transactional` on a reactive method returning `Mono<Order>`, while JDBC later runs on boundedElastic. Why might the transaction fail to cover the query?

**Answer:** Imperative transactions use `ThreadLocal`, whereas the method already returned a Mono and execution later runs on another thread. Place the transaction on an imperative method called **inside** `fromCallable` and ensure it goes through a Spring proxy.

**Scenario E:** A client cancels a request while a query is running. Is the query guaranteed to stop and return the connection immediately?

**Answer:** No. Cancellation stops the reactive chain where possible, while an active JDBC call depends on driver/timeout/interruption support. Measure and configure multi-layer timeouts.

**Scenario F:** When should you replace JDBC with R2DBC instead of merely offloading?

**Answer:** When the database/driver and most downstream dependencies support reactive I/O, the workload benefits from high-concurrency non-blocking execution, the team accepts the mapping/transaction trade-offs, and benchmarks confirm the gain. If business logic remains largely blocking, MVC or a bounded blocking adapter may be preferable.

## Official Reference Documentation

- [Spring Framework — Spring WebFlux Overview and concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Project Reactor — Threading and Schedulers, boundedElastic](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — FAQ: Wrap a synchronous, blocking call](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Spring Boot — SQL Databases (JDBC, connection pooling)](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Framework — Declarative transaction implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Data — JDBC and R2DBC Reference](https://docs.spring.io/spring-data/relational/reference/)
- [Spring Data — R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)

**Core principle:** when data originates from a non-reactive repository, keep **the reality of blocking** explicit in your architecture. `fromCallable + subscribeOn(boundedElastic)` shields the event loop, while DB queries still consume workers and connections. For true end-to-end reactivity, underlying data sources and drivers must also support non-blocking I/O, paired with backpressure, transaction, timeout, and resource-limit controls.