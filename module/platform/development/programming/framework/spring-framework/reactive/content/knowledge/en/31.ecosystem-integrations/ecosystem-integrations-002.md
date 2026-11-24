# Distinguishing Blocking JDBC/JPA from Reactive Data Drivers in Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Parent topic:** Ecosystem integrations  
> **Focus:** distinguishing the SQL access nature of JDBC/JPA (imperative, blocking) and R2DBC (Reactive Relational Database Connectivity); impact on the event loop, threads, connection pools, transactions, and API design; how to temporarily integrate legacy systems; Java 17+ example with Spring Boot 4.0.9, H2, WebFlux, Spring Data R2DBC, and HTTP integration tests.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain which layer JDBC, JPA, Hibernate, Spring Data JDBC, Spring Data JPA, R2DBC, and Spring Data R2DBC belong to.
2. Distinguish a **thread-blocking** call from **non-thread-blocking** processing while waiting for I/O.
3. Recognize why `Mono.just(jpaRepository.findById(...))` still blocks the event-loop and why `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` is only a bridge.
4. Write a reactive repository returning `Mono<T>`/`Flux<T>` using an R2DBC driver instead of using JDBC inside an operator.
5. Understand the differences between `DataSource`/`java.sql.Connection` and `ConnectionFactory`/`io.r2dbc.spi.Connection`.
6. Distinguish thread-bound `PlatformTransactionManager` transactions from Reactor Context-bound `ReactiveTransactionManager` transactions.
7. Know that JPA features such as persistence context, dirty checking, and lazy loading do not automatically appear when switching to R2DBC.
8. Choose a stack based on workload, driver availability, and business complexity instead of assuming “reactive is always faster”.
9. Limit concurrency and observe JDBC pools, R2DBC pools, the event-loop, latency, and timeouts.
10. Run a non-blocking REST API with Spring WebFlux + Spring Data R2DBC + H2 and test its actual behavior.

**Foundational conclusion:** WebFlux is a reactive web runtime; it does not automatically turn JDBC/JPA calls into non-blocking operations. To have an end-to-end reactive SQL access path, you must use a truly reactive driver/API (such as R2DBC) and build a pipeline free of unisolated blocking operations. Conversely, when a JPA system is stable and needs a rich ORM, Spring MVC + JDBC/JPA or a controlled blocking boundary can still be a sensible choice.

## 2. Defining the concepts accurately

### 2.1. JDBC

**JDBC** (Java Database Connectivity) is the standard `java.sql` API for SQL databases. Calls such as `DataSource.getConnection()`, `PreparedStatement.executeQuery()`, and `ResultSet.next()` are used in a synchronous model. When the database is slow, the thread making the call must wait for it to finish or fail/time out.

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id, name FROM items WHERE id = ?")) {

    statement.setLong(1, id);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            return new ItemView(
                rows.getLong("id"),
                rows.getString("name")
            );
        }
        return null;
    }
}
~~~

This is a **plain JDBC illustrative fragment**, assuming `DataSource dataSource`, `long id`, and DTO `ItemView` exist. JDBC statements block the thread while waiting on the driver/database; `try-with-resources` ensures the connection/statement/result set are closed according to lifecycle.

**Spring JDBC** such as `JdbcTemplate` or `JdbcClient` reduces SQL boilerplate and manages resources, but still relies on blocking JDBC. **Spring Data JDBC** adds aggregate mapping/repositories yet also relies on JDBC. Do not confuse Spring Data JDBC with Spring Data R2DBC just because both are part of Spring Data.

### 2.2. JPA, Hibernate, and Spring Data JPA

**JPA** (Jakarta Persistence) is a specification for ORM and persistence lifecycle. **Hibernate ORM** is a popular JPA implementation; **Spring Data JPA** provides a repository abstraction over JPA/Hibernate.

~~~java
public interface ItemJpaRepository
        extends JpaRepository<LegacyItemEntity, Long> {
}
~~~

Standard `findById(id)`, `save(entity)`, `flush()`, and lazy relation loading in Spring Data JPA/Hibernate ultimately use JDBC and are blocking. JPA adds entity state, persistence context, dirty checking, cascades, relationship mapping, and a query language; this does **not** make database I/O reactive.

There are separate “reactive ORM” technologies in the ecosystem, but they must not be equated with default Spring Data JPA. This lesson compares JDBC-based Spring Data JPA/Hibernate ORM with Spring Data R2DBC.

### 2.3. R2DBC

**R2DBC** (Reactive Relational Database Connectivity) is a specification for SQL access via reactive streams. It uses:

- `io.r2dbc.spi.ConnectionFactory` instead of `javax.sql.DataSource`.
- `io.r2dbc.spi.Connection` instead of `java.sql.Connection`.
- `Publisher` for connection results, statement execution, and row retrieval.
- Support for composition, cancellation, and demand per the reactive contract.

`ConnectionFactory.create()` returns a Publisher; connecting and executing are not forced to block the calling thread while waiting for network I/O. Actual effectiveness depends on the driver, server, and how you use the API.

**Spring Data R2DBC** adds `ReactiveCrudRepository`, `R2dbcEntityTemplate`, object mapping, and repository query methods on top of the R2DBC driver. **Spring Framework R2DBC** includes `DatabaseClient`, `R2dbcTransactionManager`, and `ConnectionFactoryUtils`.

### 2.4. Do not compare the wrong layers

~~~text
              Imperative SQL                 Reactive SQL

HTTP layer    Spring MVC                     Spring WebFlux
                     |                               |
Data API      Spring Data JPA/JDBC            Spring Data R2DBC
                     |                               |
Mapper/SQL    Hibernate ORM, JdbcTemplate    R2dbcEntityTemplate, DatabaseClient
                     |                               |
Driver SPI    JDBC / java.sql                R2DBC / io.r2dbc.spi
                     |                               |
Network       DB connection                  DB connection
                     |                               |
DB            PostgreSQL/H2/...              PostgreSQL/H2/...
~~~

**Spring MVC can still use R2DBC**, and **WebFlux can still call JPA**, but mixing them must be intentional. A layer returning `Mono` does not prove the layer underneath is non-blocking.

## 3. Overall comparison table

| Criterion | JDBC / Spring JDBC | JPA / Spring Data JPA | R2DBC / Spring Data R2DBC |
| --- | --- | --- | --- |
| I/O interface | Synchronous, blocking | Synchronous, via JDBC, blocking | Reactive Publisher |
| Common return types | `List<T>`, `T`, `Optional<T>` | Entity, `Optional<T>`, `List<T>`, `Page<T>` | `Mono<T>`, `Flux<T>` |
| Connection | `DataSource`, `java.sql.Connection` | JDBC connection via ORM | `ConnectionFactory`, R2DBC connection |
| Mapping | Manual or mapper | Powerful ORM/entity graph | Row/aggregate mapping, not JPA |
| Lazy loading | Decided manually in code | Supports lazy relationships via Hibernate | No JPA-style lazy entity proxies by default |
| Persistence context / dirty checking | No | Yes | No JPA persistence context |
| Transaction | `PlatformTransactionManager`, usually ThreadLocal | `JpaTransactionManager`, ThreadLocal | `ReactiveTransactionManager`, Reactor Context |
| Direct use on Netty event-loop | Not directly | Not directly | Suitable when the entire pipeline is non-blocking |
| Client-side backpressure | Not in JDBC API | Not in JPA API | Reactive stream, though still depends on driver/DB |
| ORM level | Low to moderate | High | Different from JPA, simpler mapping |
| Strengths | Mature, straightforward API | Complex domain models, large ecosystem | Optimizes concurrency for I/O-bound reactive services |
| Stack migration cost | Low for legacy code | Low if already using JPA | Requires revisiting repositories, transactions, mapping, queries, and tests |

Do not conclude that “R2DBC is faster than JDBC in every benchmark”. For simple queries, low concurrency, or applications with heavy blocking business logic, a well-configured JDBC/JPA system can be simpler and have comparable or better throughput. R2DBC primarily reduces the cost of holding **threads waiting on I/O**, rather than making SQL or the database execute faster.

## 4. What gets blocked when using JDBC in WebFlux?

Suppose the Netty event-loop only has a small number of threads to handle a large number of sockets. If one request uses that thread to call JDBC and waits 300 ms for the database, the thread cannot process other requests/sockets during that time.

~~~text
Wrong: blocking JDBC directly on the event-loop

reactor-http-nio-1:
  accept request A -> JDBC query [wait DB 300ms] -> response A
  accept request B -> delayed because the thread is occupied
  accept request C -> delayed because the thread is occupied

Right when still using JDBC:
  reactor-http-nio-1:
    request A -> schedule blocking task -> return to serve sockets
  boundedElastic-1:
    JDBC query [wait DB 300ms] -> send result back to pipeline

Right with reactive DB access:
  reactor-http-nio-1:
    request A -> subscribe to R2DBC publisher -> await I/O without holding thread
  DB/driver callback:
    emit row -> continue pipeline -> response
~~~

### 4.1. Wrong example: `Mono.just()` does not make a call asynchronous

~~~java
@GetMapping("/bad/{id}")
Mono<ItemView> bad(@PathVariable long id) {
    ItemView item = legacyJpaService.load(id); // JDBC already ran and blocked.
    return Mono.just(item);
}
~~~

Even written on a single line, it is still wrong:

~~~java
return Mono.just(legacyJpaService.load(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

**Why?** Java must evaluate the argument to `Mono.just(...)` immediately when creating the Mono. `legacyJpaService.load(id)` has already run on the current thread before `subscribeOn()` gets a chance to take effect.

### 4.2. Right example when JDBC/JPA cannot be removed yet

~~~java
Mono<ItemView> loadViaLegacy(long id) {
    return Mono.fromCallable(() -> legacyJpaService.load(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`fromCallable` defers calling `legacyJpaService.load(id)` until subscription; `subscribeOn(boundedElastic())` shifts execution of the blocking source onto the scheduler dedicated to blocking work.

`boundedElastic` has a cap on threads and queued tasks. This is **blocking isolation**, not turning JDBC into non-blocking. Each JDBC query still occupies a worker thread and a JDBC connection while waiting.

If `legacyJpaService.load()` can return `null`, `Mono.fromCallable` completes empty when returning null; use `switchIfEmpty` or map to 404 according to the API contract.

### 4.3. Keep JPA transactions at a synchronous boundary

A subtle mistake is putting `@Transactional` on a method returning `Mono` while using Spring Data JPA inside, hoping the JPA transaction automatically crosses Reactor operators.

Better is to keep the blocking transaction in a separate synchronous service:

~~~java
@Service
public class LegacyJpaService {

    private final ItemJpaRepository repository;

    public LegacyJpaService(ItemJpaRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ItemView load(long id) {
        return repository.findById(id)
            .map(item -> new ItemView(item.getId(), item.getName()))
            .orElse(null);
    }
}
~~~

This is a **fragment for a separate JPA module**; it requires the corresponding entity/repository and the `spring-boot-starter-data-jpa` dependency. A reactive wrapper sits outside and calls it through the Spring proxy:

~~~java
@Service
public class LegacyBridge {

    private final LegacyJpaService legacyJpaService;

    public LegacyBridge(LegacyJpaService legacyJpaService) {
        this.legacyJpaService = legacyJpaService;
    }

    public Mono<ItemView> load(long id) {
        return Mono.fromCallable(() -> legacyJpaService.load(id))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Crucially, the synchronous `@Transactional` opens, uses, and closes the transaction **within the same call on the worker thread**. Do not return a JPA entity with unloaded lazy associations outside the boundary and try to read lazy properties on another reactive thread. Map to DTOs before closing the transaction.

### 4.4. When is WebFlux not needed?

If most operations are blocking JDBC/JPA, a thread-per-request MVC system can be simpler: configure the servlet thread pool, HikariCP, timeouts, and database capacity. Switching to WebFlux just to return `Mono` in controllers is not mandatory.

Java virtual threads on JDK versions that support them can lower the cost of blocking threads, but they **do not turn JDBC into a non-blocking API** and do not free up database capacity. The runnable example in this lesson uses Java 17.

## 5. How does R2DBC execute queries?

Example using Spring Framework's `DatabaseClient`:

~~~java
public Mono<ItemView> findOne(DatabaseClient db, long id) {
    return db.sql("""
            SELECT id, name
            FROM items
            WHERE id = :id
            """)
        .bind("id", id)
        .map((row, metadata) ->
            new ItemView(
                row.get("id", Long.class),
                row.get("name", String.class)))
        .one();
}
~~~

This is an **illustrative fragment** using `DatabaseClient`, assuming an `items` table and a matching `ItemView(Long id, String name)` record. `sql(...).bind(...).map(...).one()` creates a reactive `Mono` and does not execute SQL eagerly on the event-loop.

`DatabaseClient` manages acquiring/releasing connections, executing statements, and mapping errors to the appropriate `DataAccessException` hierarchy. When using Spring Data R2DBC at a higher layer, you typically do not need to write every SQL statement manually.

### 5.1. ReactiveCrudRepository

~~~java
public interface ItemRepository
        extends ReactiveCrudRepository<ItemEntity, Long> {
}
~~~

Commonly used methods:

| Method | Return type | Meaning |
| --- | --- | --- |
| `findById(id)` | `Mono<ItemEntity>` | One row or empty |
| `findAll()` | `Flux<ItemEntity>` | Stream of results |
| `save(entity)` | `Mono<ItemEntity>` | Insert or update |
| `deleteById(id)` | `Mono<Void>` | Completes the delete operation |
| `existsById(id)` | `Mono<Boolean>` | Whether it exists |
| `count()` | `Mono<Long>` | Row count |

**`Flux` does not mean infinite DB streaming.** Results depend on the query, fetch strategy, and driver. Do not use `findAll().collectList()` on very large tables; use paging/keyset pagination or bounded streaming as required by the business logic.

### 5.2. The R2DBC API does not use JPA EntityManager

There is no:
- Calling `EntityManager.flush()` to “push R2DBC changes”.
- Automatic dirty checking like Hibernate's persistence context.
- Keeping a lazy entity graph and accessing a property to trigger implicit SQL.
- Bringing JPA's `@ManyToOne` annotations into R2DBC and expecting Hibernate-style lazy ORM.

Spring Data R2DBC supports entity/aggregate mapping, repositories, templates, and some relationship/aggregate semantics of Spring Data Relational. For complex relationships, proactively design explicit queries/joins, DTO mapping, multiple queries, or appropriate aggregate boundaries.

## 6. `DataSource` vs `ConnectionFactory`

| JDBC | R2DBC |
| --- | --- |
| `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| `PreparedStatement.executeQuery()` | `Statement.execute()` emitting Publisher |
| `ResultSet.next()` | Publisher of `Result`/rows |
| `HikariDataSource` commonly pools JDBC | `r2dbc-pool` can manage R2DBC connections |
| `spring.datasource.*` | `spring.r2dbc.*` |

Configuration example:

~~~properties
# JDBC (when using JDBC/JPA module)
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_user
spring.datasource.password=${DB_PASSWORD}
~~~

~~~properties
# R2DBC (when using R2DBC module)
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/shop
spring.r2dbc.username=shop_user
spring.r2dbc.password=${DB_PASSWORD}
~~~

`jdbc:` and `r2dbc:` are two different URL protocols. You cannot point a JDBC repository at an R2DBC URL and expect it to become reactive on its own.

A production driver must properly support the database/dialect and the features actually needed such as transactions, cancellation, generated keys, parameter binding, and TLS. Verify compatibility across driver, server, and framework before deploying.

### 6.1. Pools and resource limits

Reactive does not mean no connection pool is needed:

- JDBC: a connection pool such as HikariCP; the thread waits while the JDBC call runs.
- R2DBC: a connection pool such as `r2dbc-pool` when configured; requests can wait for a connection via a reactive publisher.
- Both are constrained by max connections, DB CPU/IOPS, row locks, and transaction duration.

With R2DBC Pool, when the `io.r2dbc:r2dbc-pool` dependency is present and pooling is enabled via Boot configuration, you can configure:

~~~properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=2
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-idle-time=30m
~~~

This is a **production configuration example**, not needed for the H2 demo. Connection count must be sized according to replica count and the database's connection capacity; 50 instances x 20 connections can open up to around 1,000 connections.

## 7. Transactions: two different models

### 7.1. JDBC/JPA: thread-bound transactions

In the imperative stack, `PlatformTransactionManager` (typically `DataSourceTransactionManager` or `JpaTransactionManager`) binds transaction resources to the thread for the duration of the method call.

~~~java
@Transactional
public Receipt placeOrderBlocking(Command command) {
    inventoryRepository.reserve(command.productId());
    return orderJpaRepository.save(mapToEntity(command)).toReceipt();
}
~~~

This is a **conceptual fragment** in a synchronous JPA/JDBC service, not a file belonging to the R2DBC demo. Both calls run inside the synchronous transaction opened/closed by the Spring AOP proxy.

Do not spawn `subscribe()` or hop threads inside a JPA transaction and assume the same ThreadLocal transaction is carried over to the new thread.

### 7.2. R2DBC: Reactor Context-bound transactions

Reactive transactions use `ReactiveTransactionManager` (e.g. `R2dbcTransactionManager`) and store the transaction-bound connection in the subscriber `Context`, rather than relying on a fixed thread.

~~~java
public Mono<Receipt> placeOrderReactive(Command command) {
    return inventoryRepository.reserve(command.productId())
        .then(orderRepository.save(mapToEntity(command)))
        .map(this::toReceipt)
        .as(transactionalOperator::transactional);
}
~~~

This is an **illustrative fragment**: it assumes the repositories are reactive and `transactionalOperator` is a bean created from `ReactiveTransactionManager`. Operations must remain within the same reactive chain/Context; do not call `.block()` or manually `.subscribe()` mid-transaction.

Minimal bean once `ReactiveTransactionManager` is available:

~~~java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

Given a `ConnectionFactory`, Spring provides `R2dbcTransactionManager`; in a compatible Boot application, the transaction manager can be auto-configured based on existing dependencies and beans.

### 7.3. Reactive `@Transactional` and its traps

A method returning a reactive type can use `@Transactional` if Spring selects the right `ReactiveTransactionManager`:

~~~java
@Transactional
public Mono<ItemEntity> createReactive(ItemEntity item) {
    return repository.save(item);
}
~~~

- The transaction starts when the Publisher is subscribed to, not simply when the method is called to build the Mono.
- All DB operations in the transaction must pass through the pipeline carrying the transaction's Reactor Context.
- Do not run a JDBC operation directly inside a reactive transaction and expect it to enlist in the R2DBC connection automatically.
- `@Transactional` works via a Spring proxy; self-invocation typically bypasses the interceptor.
- Cancellation can cause a reactive transaction to roll back; you must define transaction semantics when a stream is cancelled early.
- When an app has both JDBC/JPA and R2DBC transaction managers, choose the manager explicitly for each boundary; do not let Spring guess.

### 7.4. No automatic distributed transaction between JDBC and R2DBC

A method updating both JPA and R2DBC **does not create an atomic transaction** merely by adding `@Transactional`. Each manager governs different connections/resources and execution contexts.

If you must coordinate multiple systems, consider:
- Outbox pattern.
- Idempotency keys.
- Sagas/compensating actions.
- Clear transaction boundaries.
- Eventual consistency if business rules allow.

Do not create the illusion of “one transaction” with `Mono.zip(jpaWrite, r2dbcWrite)`. Running concurrently does not mean atomicity.

## 8. Backpressure, schedulers, and blocking sources

### 8.1. Where is backpressure useful?

`Flux` supports demand: downstream can request items incrementally instead of the application holding the entire result in RAM. That is an advantage for queries returning many rows.

~~~java
Flux<ItemEntity> items = repository.findAll();

return items
    .filter(item -> item.priceCents() > 0)
    .map(this::toView);
~~~

However, the database may not support every kind of demand at the same granularity; the driver may prefetch or buffer data. Backpressure does not replace `LIMIT`, keyset pagination, indexes, and query tuning.

### 8.2. `subscribeOn` vs `publishOn`

- `subscribeOn(scheduler)` chooses the execution context when subscribing to the source.
- `publishOn(scheduler)` switches the execution context for operators **downstream of it** in the pipeline.
- For blocking JDBC/JPA sources, the standard pattern is `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- Placing `publishOn(boundedElastic())` after `Mono.just(jdbcCall())` does not fix the fact that JDBC already ran eagerly.

~~~java
// Wrong: blocking operation runs before building the Publisher.
Mono<ItemView> wrong = Mono.just(legacyJpaService.load(id))
    .publishOn(Schedulers.boundedElastic());

// Right: defer the operation, run the source on a dedicated scheduler.
Mono<ItemView> correct = Mono.fromCallable(
        () -> legacyJpaService.load(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

### 8.3. `boundedElastic` is bounded, not infinite

For a batch calling JDBC:

~~~java
Flux<ItemView> loadBatch(Flux<Long> ids) {
    return ids.flatMap(
        id -> Mono.fromCallable(
                () -> legacyJpaService.load(id))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
}
~~~

`flatMap(..., 8)` only limits concurrency **within this batch's subscription**. It does not impose a global limit across all requests in the service. If 100 requests each run 8 JDBC calls, total in-flight work can still be high. Use a bulkhead/semaphore, Hikari pool, and appropriate request limits.

When the boundedElastic queue fills up, tasks may be rejected. Once the DB is overloaded, increasing threads/connections indefinitely only increases queuing and tail latency.

### 8.4. Do not block inside an R2DBC mapping callback

This is wrong code even though the repository is reactive:

~~~java
return reactiveRepository.findAll()
    .map(row -> blockingRestClient.fetch(row.id()));
~~~

The `map` operator runs on the thread emitting the signal, and `blockingRestClient.fetch` can block the event-loop. Either use reactive WebClient inside `flatMap`, or isolate the blocking operation with `fromCallable(...).subscribeOn(boundedElastic())`.

A truly non-blocking pipeline needs control over **all** dependencies, not just the database.

## 9. Runnable example: Spring WebFlux + Spring Data R2DBC + H2

The demo uses in-memory H2 so no Docker/PostgreSQL is required. H2 is suitable for learning mapping, repositories, and HTTP contracts; performance benchmarks must use the corresponding production database/driver because H2 does not accurately reflect PostgreSQL network I/O.

Illustrative API:
- `POST /api/items` creates an item.
- `GET /api/items/{id}` finds an item, returning 404 when not found.
- `GET /api/items` returns a small JSON list for learning semantics; production needs pagination.
- Data access goes entirely through `ReactiveCrudRepository`, without JDBC/JPA.

### 9.1. Project structure

~~~text
reactive-sql-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/resources/schema.sql
├── src/main/java/com/example/reactivesql/
│   ├── ReactiveSqlApplication.java
│   ├── ItemEntity.java
│   ├── ItemRepository.java
│   ├── CreateItemRequest.java
│   ├── ItemView.java
│   ├── ItemService.java
│   └── ItemController.java
└── src/test/java/com/example/reactivesql/
    └── ItemApiIntegrationTest.java
~~~

### 9.2. pom.xml

Spring Boot `4.0.9` has been released; Boot 4 uses dedicated WebFlux and Data R2DBC starters. The Maven parent manages Spring, Reactor, and `r2dbc-h2` versions.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-sql-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
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

The demo project does **not** add `spring-boot-starter-data-jpa` or a JDBC driver. This helps prevent accidentally using a blocking repository.

### 9.3. application.properties

~~~properties
spring.application.name=reactive-sql-demo

spring.r2dbc.url=r2dbc:h2:mem:///reactive_demo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.r2dbc.password=

spring.sql.init.mode=always
~~~

`spring.r2dbc.url` declares the R2DBC ConnectionFactory. `spring.sql.init.mode=always` lets Spring Boot run `schema.sql` at startup. With in-memory H2, the DB is created per process. For production, use a suitable migration tool; do not use demo DDL as a production schema management strategy.

### 9.4. schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price_cents BIGINT NOT NULL
);
~~~

`id` is auto-generated by the database. `price_cents` uses an integer to avoid binary rounding errors when representing the smallest currency unit; in real business logic, consider monetary units and currency.

### 9.5. ReactiveSqlApplication.java

~~~java
package com.example.reactivesql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSqlApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSqlApplication.class, args);
    }
}
~~~

### 9.6. ItemEntity.java

~~~java
package com.example.reactivesql;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("items")
public record ItemEntity(
    @Id Long id,
    String name,
    long priceCents
) {}
~~~

Note the import `org.springframework.data.annotation.Id`, not `jakarta.persistence.Id`. With Spring Data Relational, the `priceCents` property is mapped by default to the `price_cents` column via the naming strategy; you can add `@Column("price_cents")` if you want it explicit.

A `record` is an immutable object. When `save(new ItemEntity(null, ...))` succeeds, the repository emits a resulting entity with the new `id`; use the emitted object rather than assuming the input record is mutated.

### 9.7. ItemRepository.java

~~~java
package com.example.reactivesql;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ItemRepository
        extends ReactiveCrudRepository<ItemEntity, Long> {
}
~~~

There is no blocking `JpaRepository` or `CrudRepository` here. This interface returns reactive publishers and is implemented by Spring Data R2DBC on top of the R2DBC driver.

### 9.8. CreateItemRequest.java and ItemView.java

`CreateItemRequest.java`:

~~~java
package com.example.reactivesql;

public record CreateItemRequest(
    String name,
    long priceCents
) {}
~~~

`ItemView.java`:

~~~java
package com.example.reactivesql;

public record ItemView(
    Long id,
    String name,
    long priceCents
) {
    public static ItemView from(ItemEntity entity) {
        return new ItemView(
            entity.id(),
            entity.name(),
            entity.priceCents());
    }
}
~~~

The API DTO is separated from the persistence entity so the DB schema does not automatically become the public contract.

### 9.9. ItemService.java

~~~java
package com.example.reactivesql;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ItemService {

    private final ItemRepository repository;

    public ItemService(ItemRepository repository) {
        this.repository = repository;
    }

    public Mono<ItemView> create(CreateItemRequest request) {
        if (request == null ||
                request.name() == null ||
                request.name().isBlank() ||
                request.priceCents() < 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "invalid item"));
        }

        ItemEntity entity = new ItemEntity(
            null, request.name().trim(), request.priceCents());

        return repository.save(entity)
            .map(ItemView::from);
    }

    public Mono<ItemView> find(long id) {
        return repository.findById(id)
            .map(ItemView::from);
    }

    public Flux<ItemView> all() {
        return repository.findAll()
            .map(ItemView::from);
    }
}
~~~

`repository.save` returns `Mono`, while `findAll` returns `Flux`. There is no `.block()` or manual `.subscribe()`. `Mono.error` remains a reactive error signal and is handled by WebFlux as HTTP 400 when the service is subscribed to.

Validation is kept simple for the demo; production can use Bean Validation, input limits, stable error codes, and centralized exception handling.

### 9.10. ItemController.java

~~~java
package com.example.reactivesql;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> create(
            @RequestBody Mono<CreateItemRequest> request) {

        return request.flatMap(service::create)
            .map(item -> ResponseEntity
                .created(URI.create("/api/items/" + item.id()))
                .body(item));
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<ItemView>> find(
            @PathVariable long id) {

        return service.find(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<ItemView> all() {
        return service.all();
    }
}
~~~

The controller does not execute JDBC and does not choose schedulers on its own. It returns `Mono`/`Flux` to WebFlux so the request lifecycle manages subscription and cancellation. With `application/json`, `Flux<ItemView>` may be encoded into a JSON array; the response does not necessarily flush each row. If you need to stream rows record by record, use a streaming-capable media type and bound the query appropriately.

### 9.11. ItemApiIntegrationTest.java

The tests use a real HTTP server (random port), H2 R2DBC, and `WebTestClient`. A separate repository test uses `StepVerifier` to verify insert followed by query completion.

~~~java
package com.example.reactivesql;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ItemApiIntegrationTest {

    @Value("${local.server.port}")
    int port;

    @Autowired
    ItemRepository repository;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void createThenReadItemOverHttp() {
        String name = "Book-" + UUID.randomUUID();

        ItemView created = client().post()
            .uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest(name, 1250))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueMatches(
                "Location", "/api/items/[0-9]+")
            .expectBody(ItemView.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(created);
        assertNotNull(created.id());
        assertEquals(name, created.name());
        assertEquals(1250, created.priceCents());

        client().get()
            .uri("/api/items/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(ItemView.class)
            .value(item -> {
                assertEquals(created.id(), item.id());
                assertEquals(name, item.name());
            });
    }

    @Test
    void missingItemReturnsNotFound() {
        client().get()
            .uri("/api/items/{id}", Long.MAX_VALUE)
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void invalidInputReturnsBadRequest() {
        client().post()
            .uri("/api/items")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateItemRequest("  ", -1))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void repositoryPublisherPersistsAndReadsReactively() {
        String name = "Repo-" + UUID.randomUUID();

        StepVerifier.create(
            repository.save(new ItemEntity(null, name, 99))
                .flatMap(saved -> repository.findById(saved.id()))
        )
            .assertNext(found -> {
                assertNotNull(found.id());
                assertEquals(name, found.name());
                assertEquals(99, found.priceCents());
            })
            .verifyComplete();
    }
}
~~~

The tests use HTTP results rather than assuming fixed database IDs. `StepVerifier` subscribes to the reactive pipeline and verifies elements/terminal signals; there is no `.block()` in production classes.

### 9.12. Running the project

Requires JDK 17+, Maven 3.6.3+, and network access to download Maven dependencies the first time.

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Create an item (Windows CMD; using `^` for line continuation):

~~~bat
curl -i -X POST http://localhost:8080/api/items ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Notebook\",\"priceCents\":12900}"
~~~

Illustrative response (ID is DB-generated):

~~~http
HTTP/1.1 201 Created
Location: /api/items/1
Content-Type: application/json

{"id":1,"name":"Notebook","priceCents":12900}
~~~

Read an item:

~~~bash
curl -i http://localhost:8080/api/items/1
~~~

List:

~~~bash
curl -i http://localhost:8080/api/items
~~~

Test error status:

~~~bash
curl -i http://localhost:8080/api/items/999999
~~~

Expected results: HTTP 404 for a non-existent ID. For invalid data (blank `name` or negative `priceCents`), HTTP 400. Output and ID sequence depend on existing data; tests do not depend on fixed IDs.

### 9.13. Why does the demo prove R2DBC and not just reactive return types?

Check dependencies:
- `spring-boot-starter-data-r2dbc` is present.
- `io.r2dbc:r2dbc-h2` is present.
- The URL starts with `r2dbc:`.
- The repository extends `ReactiveCrudRepository`.
- Repository methods return `Mono` or `Flux`.
- No `JpaRepository`, `JdbcTemplate`, `EntityManager`, `java.sql.Connection`, or `.block()` exists in production code.

Tests prove the HTTP and persistence paths work. To **measure actual non-blocking behavior/performance**, you also need load tests on a production database/driver, thread profilers, database pool metrics, and checks that all other dependencies are non-blocking.

## 10. Comparing the same business task in JDBC, JPA, and R2DBC

Suppose we need to find an item by ID.

### 10.1. Spring JDBC (blocking)

~~~java
public ItemView findWithJdbc(JdbcClient jdbc, long id) {
    return jdbc.sql("""
            SELECT id, name
            FROM items
            WHERE id = :id
            """)
        .param("id", id)
        .query((rs, rowNum) -> new ItemView(
            rs.getLong("id"),
            rs.getString("name")))
        .optional()
        .orElse(null);
}
~~~

This is an **illustrative fragment**, using the two-field `ItemView(Long id, String name)` type for the comparison example. It requires `spring-boot-starter-jdbc`, a JDBC driver, and a `DataSource`. The `query` call still blocks.

### 10.2. Spring Data JPA (blocking)

~~~java
public ItemView findWithJpa(ItemJpaRepository repository, long id) {
    return repository.findById(id)
        .map(entity -> new ItemView(
            entity.getId(),
            entity.getName()))
        .orElse(null);
}
~~~

This is an **illustrative fragment**, using `JpaRepository`/entity and an appropriate transaction. JPA mapping/ORM does not make the `findById` call non-blocking.

### 10.3. Spring Data R2DBC (reactive)

~~~java
public Mono<ItemView> findWithR2dbc(
        ItemRepository repository, long id) {

    return repository.findById(id)
        .map(entity -> new ItemView(
            entity.id(), entity.name()));
}
~~~

This is an **illustrative fragment** with a two-field `ItemView` to compare syntax; the runnable demo in section 9 uses `ItemView(Long id, String name, long priceCents)`. The difference is not just the return type: `ItemRepository` must be backed by an R2DBC driver, not JPA.

### 10.4. Costs do not disappear on their own

| Scenario | JDBC/JPA | R2DBC |
| --- | --- | --- |
| Query takes 500 ms at the database | Thread blocks waiting for I/O | Thread does not wait on I/O in the reactive model |
| DB only allows 20 connections | Still only 20 connections | Still only 20 connections |
| SQL lacks an index | Still slow | Still slow |
| Transaction holds a row lock long | Still blocks other DB transactions | Still blocks other DB transactions |
| Heavy CPU mapping/JSON | Uses CPU | Still uses CPU |
| Repository called 100,000 times unbounded | Pool/DB overloaded | Pool/DB still overloaded |
| Code uses another blocking HTTP client | Adds blocking | Overall pipeline is still blocked |

R2DBC optimizes **thread utilization while waiting for results**, not query design, indexes, pools, timeouts, or concurrency limits.

## 11. When migrating from JPA to R2DBC

### 11.1. Inventory the current state

Before changing dependencies, list:
- Which repositories are using `JpaRepository`/`EntityManager`.
- Entity graphs, relationships, lazy loading, cascades, dirty checking.
- JPQL/HQL, Criteria API, query hints, and database-specific SQL.
- Required transaction boundaries and propagation/isolation.
- Auditing, optimistic locking/version columns.
- Batch updates, pagination, fetch joins, N+1 queries.
- Concurrent request count, DB connection pools, p95/p99 latency, and timeouts.

Do not migrate by swapping `JpaRepository` for `ReactiveCrudRepository` while keeping the same entity lifecycle assumptions.

### 11.2. Redesign the persistence contract

1. Identify aggregate roots and transaction boundaries.
2. Move data access to reactive repositories/templates.
3. Verify the driver supports the required column/SQL types and transactions.
4. Separate REST DTOs from DB records.
5. Write explicit queries or multiple composed operations where lazy ORM is absent.
6. Choose how to load associations explicitly.
7. Replace blocking `Page<T>` with a suitable paging strategy; use LIMIT/keyset to bound memory.
8. Replace the transaction manager and verify rollback/cancellation.
9. Add integration tests on a real DB for critical queries.
10. Load test to compare effectiveness, not just single-request latency.

### 11.3. Incremental migration roadmap

| Phase | What to do | Risks to verify |
| --- | --- | --- |
| 1. Measure baseline | JDBC/JPA latency, Hikari pool, thread dump, CPU | Understand real bottlenecks |
| 2. Isolate legacy | `Mono.fromCallable` + boundedElastic + bulkhead | Do not block Netty event-loop |
| 3. Pick a vertical slice | One endpoint/query with minimal ORM relations | Clear contract and transaction |
| 4. Write R2DBC repository | Driver, `ReactiveCrudRepository`, `R2dbcEntityTemplate` | Mapping and SQL semantics |
| 5. Convert service chain | `Mono`/`Flux`, error and cancellation | No `.block()`/`.subscribe()` |
| 6. Verify transactions | `ReactiveTransactionManager`/operator | Rollback and context |
| 7. Verify production DB | Migrations, indexes, locks, pool | Differences between H2 and real DB |
| 8. Canary and observe | p95/p99, throughput, pool, errors | Fail-fast and rollback plan |

You can keep JDBC/JPA for certain bounded contexts while using R2DBC for high-I/O paths. Mixing stacks requires separating beans/transactions and ensuring no single transaction is assumed across both technologies.

## 12. Common pitfalls

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `Mono.just(jpaRepo.findById(id))` | JDBC already ran eagerly | `fromCallable` + `subscribeOn(boundedElastic)` |
| Running JDBC directly inside `map`/`flatMap` | Can block the signal-emitting thread | Offload at the boundary or use an R2DBC driver |
| Changing method return type to `Mono` then calling JPA underneath | Reactive wrapper does not change I/O | Distinguish a bridge from end-to-end non-blocking |
| Using `publishOn` after an eager blocking call | Switches threads too late | Use a lazy source and `subscribeOn` |
| `.block()` in a WebFlux controller | Blocks the event-loop | Return a publisher |
| Separate `.subscribe()` in a service | Detaches errors, cancel, transaction from request | Compose and return the publisher |
| Using JPA `@Transactional` around `Mono` | Wrong execution/context boundary | Close transaction in sync service or switch to reactive manager |
| Sharing a transaction between JPA and R2DBC | Not automatically atomic | Separate boundaries, outbox/saga |
| Passing a lazy JPA entity out of a method | Risks lazy initialization/thread errors | Map DTO inside the sync transaction |
| Expecting R2DBC to have JPA dirty checking/cascade | Different mapping model | Explicit repository/template operations |
| Not paginating `findAll()` | Can stream huge volumes of data | Limit/keyset/paging |
| Creating a new connection per item | Pool/DB saturation | Reuse ConnectionFactory/pool |
| Increasing pool size unboundedly | DB overload, lock contention | Load test and cap total connections |
| Retrying write transactions infinitely | Duplicate writes and DB overload | Idempotency and retry budget |
| Testing only with H2 | Hides dialect/locking/index differences | Integration tests against a production-like DB |
| Logging SQL parameters/PII indiscriminately | Information leakage | Redact and configure safe logging |
| Judging reactivity by a single thread name | Threads can change | Profile/block detector/metrics and end-to-end tests |

## 13. Observability and performance

### 13.1. JDBC/JPA

Monitor:
- `hikaricp.connections.active`, `idle`, `pending`, `max` (per meter registry).
- The thread pool running JDBC calls and its queue.
- JDBC query duration, transaction duration, and connection acquisition time.
- Deadlocks/lock waits, slow SQL, DB CPU/IOPS.
- WebFlux/Netty event-loop blocking or unusual latency spikes.

A thread dump with many `reactor-http-nio-*` threads in `java.sql`/Hibernate stacks is a dangerous sign.

### 13.2. R2DBC

Monitor:
- Active/idle/pending/max connections from the R2DBC pool if pool metrics are enabled and supported by the exporter.
- R2DBC driver/DB query duration, p95/p99.
- In-flight reactive DB operations and cancellations/timeouts.
- Database CPU/IOPS, connection limits, lock waits, and slow queries.
- Netty event-loop latency and number of non-DB blocking calls.

An R2DBC service can still exhaust database connections when concurrency is too high. Reactive does not eliminate the need for bulkheads and backpressure.

### 13.3. Choosing workloads to benchmark

Run at least:
1. **Single request latency:** latency of a single query.
2. **Steady concurrency:** moderate concurrent requests, p95/p99.
3. **High concurrency:** when DB wait time rises; watch thread/connection pools.
4. **Slow query:** simulate a slow DB, verify the event-loop stays responsive.
5. **Cancellation:** client cancels the request; observe connection/transaction cleanup.
6. **Memory and CPU:** heap, direct memory, GC, context switching.

Compare under identical SQL, indexes, DB capacity, replica count, and HTTP workload. If R2DBC achieves higher throughput while DB errors/lock waits increase, that is not an overall improvement.

## 14. How to choose in real-world architecture

Choose JDBC/JPA when:
- The application is primarily business CRUD with complex ORM relationships/dirty checking.
- The team already has many stable JPA entities and transactions.
- Concurrency is well served by Spring MVC/HikariCP or bounded blocking boundaries.
- A reactive driver for the database is unavailable or lacks critical features.

Choose R2DBC when:
- WebFlux handles many concurrent I/O-bound requests.
- A non-blocking pipeline to a relational database is needed.
- The R2DBC database/driver is fully supported, operated, and tested.
- Mapping/transaction semantics do not require JPA ORM features or can be redesigned.
- The team is capable of managing publishers, backpressure, cancellation, and reactive transactions.

Choose a hybrid model when:
- A legacy JPA module must be retained.
- Specific endpoints need reactive DB streaming and concurrency scaling.
- Transaction boundaries, connection pools, and schedulers are clearly separated.
- There is a plan to gradually remove blocking I/O from critical WebFlux request paths.

**Decision-making principle:** measure bottlenecks, pick the right abstraction, preserve transaction correctness, and run production-like tests. Do not switch to R2DBC merely to change the word `Optional` into `Mono`.

## 15. Hands-on exercises

1. **Locate blocking:** in a WebFlux endpoint, call `JpaRepository.findById` directly and observe the thread. Switch to `fromCallable(...).subscribeOn(boundedElastic())` and measure the difference in event-loop responsiveness.
2. **Catch the Mono.just bug:** write a unit test with an incrementing counter inside a blocking method; prove `Mono.just(fn())` invokes immediately while `Mono.fromCallable(fn)` invokes on subscription.
3. **R2DBC CRUD:** run the section 9 demo, POST a new item, GET the newly created item, and GET a non-existent ID.
4. **Reactive query:** add `findByName(String name)` to `ReactiveCrudRepository`, using `Flux`/`Mono` with the right cardinality.
5. **Transaction rollback:** perform two consecutive R2DBC operations inside `TransactionalOperator`, intentionally emit an error after the first operation, and verify rollback.
6. **Lazy loading migration:** pick a JPA entity with `@ManyToOne`; design an explicit R2DBC query/DTO instead of expecting JPA lazy loading to work automatically.
7. **Pool saturation:** cap the R2DBC pool small, raise concurrency, and observe pending acquires/timeouts on the client alongside CPU/connection counts on the DB.
8. **Pagination:** replace full-table `findAll()` with a LIMIT and keyset pagination query; inspect memory when the table has many rows.
9. **Mixed stack:** build a synchronous transactional `LegacyJpaService`, wrap it with `LegacyBridge`, and cap concurrency. Do not fake a transaction across JPA + R2DBC.
10. **Benchmark:** compare Spring MVC + JPA, WebFlux + offloaded JPA, and WebFlux + R2DBC on identical SQL/indexes/DB, reporting p50/p95/p99, throughput, errors, CPU, threads, and DB connections.

## 16. Production checklist

- [ ] Identified all blocking sources in the WebFlux request path.
- [ ] JDBC/JPA does not run directly on the Netty event-loop.
- [ ] If blocking DB remains, use a lazy Publisher + bounded scheduler and a finite bulkhead.
- [ ] No arbitrary `.block()` or `.subscribe()` calls in services/controllers.
- [ ] Distinguished `spring.datasource.*` from `spring.r2dbc.*`.
- [ ] Selected an R2DBC driver matching the database and required features.
- [ ] Spring Data R2DBC repository is genuinely backed by `ConnectionFactory`.
- [ ] Mapping, generated IDs, joins, lazy associations, and transaction semantics have been verified.
- [ ] JDBC/JPA transactions stay at synchronous boundaries; R2DBC transactions stay in Reactor Context.
- [ ] Do not assume atomic transactions between JDBC/JPA and R2DBC.
- [ ] Configured DB connection pool, timeouts, and max concurrent operations.
- [ ] Large queries have LIMIT/keyset pagination or bounded streaming.
- [ ] SQL migrations are managed by a proper process; do not rely on demo schema init.
- [ ] Integration tests against a production-like database cover critical queries.
- [ ] Rollback, cancellation, timeout, and data integrity are tested.
- [ ] Observability monitors the event loop, thread pool, DB pool, DB latency, and error rate.
- [ ] No uncontrolled logging of PII, credentials, or raw SQL parameters.
- [ ] Canary/rollback plan exists if migrating from JPA to R2DBC.

## 17. References

1. Spring Framework – R2DBC Data Access, `DatabaseClient`, `R2dbcTransactionManager`: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
2. Spring Framework – Transaction management and `TransactionalOperator`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
3. Spring Framework – Declarative transactions (thread-bound vs Reactor Context): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
4. Spring Data Relational – R2DBC reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
5. Spring Data Relational – R2DBC mapping conventions: https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html
6. Spring Boot 4.0 – R2DBC configuration: https://docs.spring.io/spring-boot/4.0/reference/data/sql.html
7. Spring Boot – Schema initialization for `ConnectionFactory`: https://docs.spring.io/spring-boot/how-to/data-initialization.html
8. Spring Boot – Managed dependencies, including R2DBC and WebFlux starters: https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html
9. Reactor Core – Blocking call bridge with `Mono.fromCallable` and `Schedulers.boundedElastic`: https://projectreactor.io/docs/core/release/reference/
10. R2DBC specification and drivers: https://r2dbc.io/
11. Spring Boot 4.0.9 release: https://spring.io/blog/2026/10/23/spring-boot-4-0-9-available-now/

**Self-check:** At what moment does `Mono.just(jpaRepo.findById(...))` block? Does `boundedElastic` change where the blocking call runs or turn JDBC into non-blocking? Why do JPA transactions use ThreadLocal while R2DBC transactions use Reactor Context? Why does an R2DBC entity not automatically have dirty checking/lazy loading like Hibernate? When should you keep Spring MVC + JPA? If you can answer accurately and run the R2DBC demo along with its integration tests, you understand the real difference between blocking JDBC/JPA and reactive data drivers.
