# R2DBC and Reactive Spring Data Libraries in Overall Architecture

## 1. Goal and context

Spring WebFlux builds the HTTP layer on `Mono`, `Flux`, and non-blocking I/O. However, an endpoint returning Mono can still block the event-loop if the underlying service calls JDBC, JPA, or a synchronous SDK. Reactive architecture must be examined **from HTTP, service, data client, driver, all the way to the database**, not just at the controller's return type.

**R2DBC** (Reactive Relational Database Connectivity) is a specification for accessing relational databases using Reactive Streams. **Spring Framework R2DBC** provides `DatabaseClient`, connection, and transaction infrastructure. **Spring Data R2DBC** adds entity mapping, `R2dbcEntityTemplate`, and repositories. Other reactive Spring Data modules support MongoDB, Redis, Elasticsearch, Cassandra, or other datastores, with varying feature levels and semantics.

After completing this lesson, you should be able to:

1. Distinguish JDBC/JPA from R2DBC and Spring Data R2DBC.
2. Know when to choose `ReactiveCrudRepository`, `R2dbcEntityTemplate`, or `DatabaseClient`.
3. Understand entity mapping, queries, Reactor Context transactions, and optimistic locking.
4. Coordinate R2DBC with WebFlux, WebClient, caches, document DBs, search indexes, and message brokers.
5. Design proper transaction boundaries when multiple datastores are involved.
6. Build a Java 17+ Spring Boot example with R2DBC H2, a REST API, transactions, and tests.

## 2. The architectural picture

~~~text
Browser / API client
         |
         v
Spring WebFlux Controller -- Mono / Flux
         |
         v
Application Service (validation / domain logic)
         |
         +----------------------+-----------------+
         |                      |                 |
         v                      v                 v
Spring Data R2DBC      Spring Data MongoDB   Spring Data Redis
         |                      |                 |
         +-- Reactive repository +                 |
         +-- R2dbcEntityTemplate |           ReactiveRedisTemplate
         +-- DatabaseClient      |                 |
         |                      v                 v
         v                 Mongo reactive       Lettuce
   ConnectionFactory         driver               |
         |                      |                 v
    R2DBC driver               MongoDB            Redis
         |
         v
 PostgreSQL / H2 / SQL
         |
  R2DBC transaction
~~~

Outside these branches, there are also message brokers, search indexes, metrics, and tracing. Using Mono/Flux across components **does not mean** a SQL transaction automatically spans Redis, MongoDB, or Kafka.

A good data flow preserves the publisher from repository to controller:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> get(@PathVariable long id) {
    return productService.findById(id);
}
~~~

~~~java
public Mono<Product> findById(long id) {
    return productRepository.findById(id);
}
~~~

WebFlux subscribes to the publisher to send the response. The service does not call `subscribe()` or `block()` itself just to trigger the query.

## 3. JDBC, JPA, R2DBC, and Spring Data R2DBC

| Technology | Nature | I/O/API style | Highlights |
| --- | --- | --- | --- |
| JDBC | Standard SQL query API in Java | Blocking API | DataSource, Connection, PreparedStatement |
| Spring JDBC | Abstraction over JDBC | Blocking | JdbcTemplate, JdbcClient |
| JPA/Hibernate | ORM and persistence context | Primarily blocking | EntityManager, JpaRepository, lazy loading |
| R2DBC SPI | Reactive API for SQL | Publisher/non-blocking depending on driver | ConnectionFactory, Connection |
| Spring Framework R2DBC | Fluent SQL client, transactions, exception translation | Reactive | DatabaseClient, R2dbcTransactionManager |
| Spring Data R2DBC | Entity mapping and repositories | Reactive | R2dbcEntityTemplate, ReactiveCrudRepository |

Points not to confuse:

- Wrapping JDBC with `Mono.fromCallable` and running on `Schedulers.boundedElastic()` only **isolates blocking work** onto a thread pool; it does not turn JDBC into a non-blocking protocol.
- R2DBC is not “reactive JPA”. Spring Data R2DBC does not have Hibernate's EntityManager, dirty checking, or JPA-style lazy relationship loading.
- `spring.jpa.hibernate.ddl-auto` is not the table creation mechanism for Spring Data R2DBC. You need `schema.sql` or migrations.
- Reactor types are only part of the model. If SQL queries are slow, the pool runs out of connections, or indexes are missing, reactive cannot fix that on its own.

**When should you consider R2DBC?** When the application has heavy concurrent I/O workloads, already uses WebFlux, has strong database driver support, and the workload fits the reactive model. If an existing application uses JPA with complex relationships and moderate load, migration costs may outweigh benefits; measure first.

## 4. ConnectionFactory, drivers, and Boot configuration

JDBC has `DataSource`; R2DBC has `ConnectionFactory`. A ConnectionFactory creates R2DBC Connections through a driver. Spring Boot configures it via `spring.r2dbc.*`.

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/inventory
spring.r2dbc.username=inventory_app
spring.r2dbc.password=\${INVENTORY_DB_PASSWORD}
~~~

The string `\${INVENTORY_DB_PASSWORD}` is Spring's placeholder mechanism for an environment variable, not an actual password. Do not commit credentials to source control.

Key notes:

- R2DBC URLs start with `r2dbc:`, distinct from `jdbc:`.
- You need the R2DBC driver dependency corresponding to H2/PostgreSQL/the target DB.
- Spring Boot automatically detects the driver via R2DBC Connection Factory discovery; `driver-class-name` is not necessarily required.
- When a ConnectionFactory is present, standard JDBC DataSource auto-configuration may back off.
- Having an R2DBC application does not mean a JDBC DataSource is already configured for Flyway or Liquibase.
- Drivers do not guarantee every JDBC feature has an R2DBC equivalent.

Responsibility diagram:

~~~text
Repository / Template / DatabaseClient
              |
              v
      ConnectionFactory
              |
              v
       R2DBC driver
              |
              v
     Database connections
              |
              v
        SQL database
~~~

The driver and pool must be selected based on support for the database version, TLS, data types, generated keys, transactions, and timeouts.

## 5. Three Spring API layers: Repository, Template, and SQL

Choose the abstraction based on need; not every operation has to use raw SQL.

### 5.1. ReactiveCrudRepository

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByStockLessThan(int stock);

    Mono<Product> findByName(String name);
}
~~~

The repository provides methods such as:

| Method | Result |
| --- | --- |
| `findById(id)` | `Mono<Product>`, empty when absent |
| `findAll()` | `Flux<Product>` |
| `save(product)` | `Mono<Product>` |
| `deleteById(id)` | `Mono<Void>` |
| `existsById(id)` | `Mono<Boolean>` |
| `count()` | `Mono<Long>` |

The library generates the implementation from the interface and mapping metadata. Query methods are suitable for simple CRUD, conditional finders, and readable method names.

### 5.2. R2dbcEntityTemplate

~~~java
Flux<Product> lowStock =
    template.select(Product.class)
        .matching(
            Query.query(
                Criteria.where("stock").lessThanOrEquals(5)
            )
        )
        .all();
~~~

The template supports dynamic queries, criteria, entity-based insert/update/delete, and mapping metadata. Terminals like `all()` return Flux, while `one()` or `first()` return Mono. `one()` requires at most one row; if the query returns multiple rows, it can emit an error about result count.

### 5.3. DatabaseClient

~~~java
Mono<Integer> currentStock = databaseClient
    .sql("SELECT stock FROM products WHERE id = :id")
    .bind("id", 42L)
    .map((row, metadata) ->
        row.get("stock", Integer.class)
    )
    .one();
~~~

`DatabaseClient` belongs to `org.springframework.r2dbc.core`; it manages statements, connection lifecycles, errors, and row mapping with SQL you write. Suitable for SQL joins, projections, or specifically tuned queries.

**Always bind parameters** for client-supplied values. Never concatenate `"... WHERE id = " + userInput`, as that creates a SQL injection risk.

| Need | Choose |
| --- | --- |
| Simple CRUD/finders | ReactiveCrudRepository |
| Criteria/dynamic queries and object mapping | R2dbcEntityTemplate |
| Complex SQL, joins, projections/bulk queries | DatabaseClient |

## 6. Entity mapping is not like JPA

Spring Data R2DBC provides mapping metadata for relational aggregates. Common annotations:

| Annotation | Meaning |
| --- | --- |
| `@Table("products")` | Mapped table |
| `@Id` | Primary key |
| `@Column("product_id")` | Custom column name |
| `@Version` | Optimistic locking |
| `@Embedded` | Value object into columns in the same row |
| `@MappedCollection` | Collection relationship within an aggregate |
| `@Transient` | Excluded from persistence |
| `@ReadOnlyProperty` | Read but not written back |

Java 17 record example:

~~~java
@Table("products")
public record Product(
    @Id Long id,
    String name,
    int stock,
    @Version Long version
) {
}
~~~

With a null id, a new entity can be inserted and receive a DB-generated id when an identity column is configured. `@Version` is used to detect concurrent updates. When updating from an object with a stale version, Spring Data may emit `OptimisticLockingFailureException`.

**There is no Hibernate session automatically tracking every change.** Multi-table relationships require aggregate design, `@MappedCollection`, or explicit SQL queries. For large lists, avoid N+1 queries. A SQL JOIN projection may be better than calling a repository per item and composing Monos hundreds of times.

### 6.1. Optimistic locking against lost updates

~~~text
A reads product id=5: stock=10, version=3
B reads product id=5: stock=10, version=3
A saves stock=8 -> version=4
B saves stock=7 with version=3 -> conflict
~~~

Do not rely solely on an `if (stock >= qty)` check in the application under concurrency; combine constraints, transactions, and optimistic locking or conditional atomic UPDATEs at the database.

## 7. Query methods, paging, and large datasets

Derived query:

~~~java
Flux<Product> findByNameContainingIgnoreCase(String keyword);
~~~

Query with custom SQL:

~~~java
@Query("""
    SELECT id, name, stock, version
    FROM products
    WHERE stock < :threshold
    ORDER BY stock, id
    """)
Flux<Product> lowStock(@Param("threshold") int threshold);
~~~

With Spring Data R2DBC, string-based `@Query` methods do not automatically rewrite arbitrary SQL to apply Pageable/Sort. If pagination is needed, prefer derived queries accepting Pageable, fluent `R2dbcEntityTemplate` Queries with limit/offset, or SQL with explicit bound limit/offset.

Reactive repositories typically return `Flux<T>` for multiple rows; constructing a full Page requires a count query and related metadata. Do not assume a Flux automatically carries `Page<T>`.

Specifically, `repository.findAll().take(20)` **is not equivalent** to SQL LIMIT 20 in limiting database work. Apply limits directly in the query, with a stable ORDER BY and appropriate indexes. For continuously updated data, cursor/keyset pagination can outperform large offsets.

## 8. Reactive transactions and Reactor Context

Spring Framework provides `R2dbcTransactionManager`, a `ReactiveTransactionManager` for ConnectionFactory. Unlike JDBC transactions based on ThreadLocal, reactive transactions bind to the **Reactor subscriber Context** and a publisher chain.

### 8.1. @Transactional with Publishers

~~~java
@Service
public class InventoryService {
    private final ProductRepository products;
    private final InventoryAuditRepository audits;

    public InventoryService(
            ProductRepository products,
            InventoryAuditRepository audits) {
        this.products = products;
        this.audits = audits;
    }

    @Transactional
    public Mono<Product> reserve(long id, int quantity) {
        return products.findById(id)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Unknown product")
            ))
            .flatMap(current -> {
                if (current.stock() < quantity) {
                    return Mono.error(
                        new IllegalStateException("Insufficient stock")
                    );
                }
                return products.save(new Product(
                    current.id(),
                    current.name(),
                    current.stock() - quantity,
                    current.version()
                ));
            })
            .flatMap(saved ->
                audits.save(
                    new InventoryAudit(null, saved.id(), quantity)
                ).thenReturn(saved)
            );
    }
}
~~~

This snippet focuses on the transaction; a real API must validate positive quantity. When both repositories use the same ConnectionFactory and reactive transaction manager, updating the product and inserting the audit can belong to the same SQL transaction. If the audit insert fails, the transaction rolls back.

### 8.2. TransactionalOperator

Programmatic transactions can be used:

~~~java
Mono<Product> workflow =
    products.save(product)
        .flatMap(saved ->
            audits.save(
                new InventoryAudit(null, saved.id(), 1)
            ).thenReturn(saved)
        );

Mono<Product> transactionalWorkflow =
    workflow.as(transactionalOperator::transactional);
~~~

`TransactionalOperator` creates a clear transaction boundary around a Mono/Flux. The transaction begins on subscription, not when creating the Mono variable.

### 8.3. Things to avoid

Do not do this:

~~~java
@Transactional
public Mono<Void> wrong() {
    products.findAll().subscribe(System.out::println);
    return Mono.empty();
}
~~~

An independent subscription can lose the Reactor Context, transaction, error, and request cancellation. Do not call `block()` in a WebFlux service to wait for commit.

Also watch out for `@Transactional` proxies: a method in the same class calling another transactional method via `this.method()` typically bypasses the interceptor in proxy mode. Place transaction boundaries on public service methods called from other beans, or use TransactionalOperator.

Do not open a transaction around an infinite Flux. A long-lived publisher can hold a connection for too long; prefer finite transactions, committing before pushing long-running streaming data.

## 9. Atomicity across multiple datastores: keep boundaries clear

`R2dbcTransactionManager` manages the ConnectionFactory of a single SQL database. It does not automatically create a distributed transaction across Redis, MongoDB, Elasticsearch, Kafka, or HTTP APIs.

The following example **does not guarantee atomicity** across the whole system:

~~~java
@Transactional
public Mono<Void> completeOrder() {
    return orderRepository.save(order)
        .then(reactiveRedisTemplate.opsForValue()
            .set(cacheKey, value))
        .then(publisher.send(event))
        .then();
}
~~~

Suppose the broker receives the event but the SQL commit fails: consumers may see an event that does not correspond to committed data. Or SQL commits and sending the event fails: the business action succeeded, yet downstream never learns about it.

### 9.1. Transactional outbox

~~~text
In one R2DBC SQL transaction:
  UPDATE orders
  INSERT outbox_events
         |
         v
       COMMIT
         |
         v
  Worker publishes events from outbox
         |
         +--> Message broker
         +--> Elasticsearch projector
         +--> Redis cache invalidator
         |
         v
  Mark delivered / retry / dedupe
~~~

The outbox row must be saved in the same SQL database and transaction as the business row. A worker reads after commit and sends to the broker with an idempotency key, retry/backoff, and metrics. Do not promise end-to-end exactly-once merely by using an outbox; you usually need idempotent consumers and at-least-once handling.

When a workflow spans multiple services and cannot share a single database transaction, you can choose sagas/compensation.

## 10. Other reactive Spring Data modules in the same architecture

| Store | Characteristic reactive API | Role | Notes |
| --- | --- | --- | --- |
| R2DBC SQL | ReactiveCrudRepository, R2dbcEntityTemplate | Relational/transactional data | SQL driver, aggregate mapping |
| MongoDB | ReactiveMongoRepository, ReactiveMongoTemplate | Document | Document mapping, session/transaction depends on topology |
| Redis | ReactiveRedisTemplate, ReactiveStringRedisTemplate | Cache/pub-sub/key-value | Reactive Lettuce, serialization, cache consistency |
| Elasticsearch | ReactiveElasticsearchOperations, ReactiveElasticsearchRepository | Search/index | Index consistency/rebuild |
| Cassandra | ReactiveCassandraTemplate, reactive repositories where supported | Wide-column | Partition-key-driven queries |
| Neo4j | Reactive driver / reactive repositories where supported | Graph | Graph modeling and driver compatibility |

Do not assume traditional Redis repository APIs are automatically reactive; reactive Redis typically uses template/operations with Lettuce. A store having a reactive API does not mean it participates in an R2DBC transaction.

### 10.1. Reading multiple stores with Mono.zip

~~~java
return Mono.zip(
    productRepository.findById(productId),
    customerRepository.findById(customerId)
).map(pair ->
    new ProductCustomerView(pair.getT1(), pair.getT2())
);
~~~

If one Mono branch is empty, zip can complete without emitting a result. Handle empty explicitly if both product and customer are required to exist.

This aggregates a **read model**, not a cross-database transaction.

### 10.2. Redis cache-aside

~~~java
return redis.opsForValue().get(cacheKey)
    .switchIfEmpty(
        products.findById(productId)
            .map(Product::name)
            .flatMap(name ->
                redis.opsForValue()
                    .set(cacheKey, name, Duration.ofMinutes(5))
                    .thenReturn(name)
            )
    );
~~~

Handle cache invalidation, stampedes, Redis errors, stale values, and fallback strategies. Do not write to Redis and assume a SQL transaction rollback will roll back the cache as well.

### 10.3. Search indexes and event-driven updates

SQL source data can be fed into Elasticsearch via outbox/broker:

~~~text
R2DBC PostgreSQL -> SQL outbox -> Broker -> Elasticsearch
                          |
                          +-------> Redis invalidation
~~~

Projections may update with lag: the system should define eventual consistency, reconciliation/replay, and idempotency.

## 11. Backpressure, connection pools, and concurrency limits

Reactive does not mean the DB has infinite connections or memory.

Spring Boot can use `r2dbc-pool` when the dependency is present. Illustrative configuration:

~~~properties
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=5
spring.r2dbc.pool.max-size=20
spring.r2dbc.pool.max-acquire-time=5s
spring.r2dbc.pool.max-idle-time=30m
~~~

These values are illustrative only, not a universal optimal configuration. Total connections can reach instance count multiplied by `pool.max-size`. For example, 10 pods * 20 connections = 200 connections potentially contending on the database.

Monitor:

- Pool acquired, idle, pending, and timeouts.
- Query latency per statement/operation.
- SQL locks, CPU, I/O, and index usage.
- Transaction duration and rollback rate.
- Concurrent inbound HTTP requests.
- Driver/network errors and retry counts.

When handling thousands of operations:

~~~java
Flux<Product> saved = incomingProducts
    .flatMap(repository::save, 12);
~~~

The concurrency argument `12` caps in-flight saves in this example; do not treat it as a universal default for every system. SQL tuning, proper batching, and pool sizing matter more than just tweaking Reactor operators.

Backpressure propagates through publishers, but drivers/databases have their own buffer/prefetch limits. Do not call `collectList()` on infinite or huge datasets, and do not keep a transaction open across infinite streaming.

## 12. Errors, timeouts, and retries in the right places

| Situation | Common symptom | How to handle |
| --- | --- | --- |
| No row found | Mono.empty | switchIfEmpty to NotFound |
| Unique constraint | DataIntegrityViolationException | 409 or validation response |
| Concurrent update | OptimisticLockingFailureException | 409, bounded reload/retry |
| Pool exhausted | Acquire timeout | Pool/traffic tuning |
| DB disconnected | Driver/connection exception | Retry with backoff if safe |
| Bad SQL/schema | Corresponding DataAccessException | Fix query/migration |
| Transaction rollback | Mono error | Return error and preserve consistency |

To map optimistic locking:

~~~java
return service.reserve(id, quantity)
    .onErrorMap(
        OptimisticLockingFailureException.class,
        error -> new ResponseStatusException(
            HttpStatus.CONFLICT,
            "Product changed concurrently",
            error
        )
    );
~~~

**Do not retry every INSERT/UPDATE.** If the DB already committed but the response was lost, a retry can create duplicate transactions. Identify retryable errors, use idempotency keys, and place retries outside the transaction boundary when re-running an entire workflow.

Reactor's `timeout` on Mono and the driver's connection/query timeouts are different mechanisms. `timeout(Duration)` does not make a blocking JDBC task immediately cancellable.

## 13. Schema migration: Spring Data R2DBC does not create JPA tables

Demos/tests can use `schema.sql` and `data.sql` with Spring Boot SQL initialization. Production should generally manage schemas with Flyway/Liquibase or a controlled migration job:

- Maintain versioning and migration history.
- Verify indexes/constraints and data types.
- Ensure backward/forward compatibility during rolling deployments.
- Do not let every replica run uncoordinated migrations simultaneously.
- Maintain a rollback/forward-fix plan and backups.

Traditional Flyway/Liquibase typically use a JDBC connection, even when runtime SQL uses R2DBC. If using both, configure migrations explicitly with a dedicated JDBC driver/connection. Do not assume `ConnectionFactory` automatically provides a JDBC DataSource.

## 14. Testing and observability

Testing layers:

- Unit: test validation and reactive composition with mock repositories or fake publishers.
- `@DataR2dbcTest`: test mapping/repositories in a sliced application context.
- `StepVerifier`: test values, empty, errors, cancellation, and virtual-time logic.
- WebTestClient: test WebFlux HTTP + service + database.
- Testcontainers + real PostgreSQL: test dialect, transactions, concurrency, constraints, generated keys, SQL, and migrations.

H2 is only suitable for demos or fast tests; passing on H2 does not guarantee PostgreSQL/MySQL will pass on SQL syntax, locking/isolation, and driver behavior.

Observability should include SQL query latency, pool wait, transaction duration, error rate, and correlation IDs. Do not log SQL parameters containing tokens, PII, or credentials. Reactor Context is commonly used to propagate context through asynchronous pipelines; do not rely solely on ThreadLocal.

## 15. Runnable demo: Java 17 + Spring Boot 3.5 + WebFlux + R2DBC H2

The demo builds an inventory API: create a product, fetch by ID, filter low stock, reserve quantity, and write an audit inside a transaction.

### 15.1. Project structure

~~~text
inventory-r2dbc-demo/
  settings.gradle
  build.gradle
  src/main/
    java/demo/inventory/
      InventoryApplication.java
      Product.java
      InventoryAudit.java
      ProductRepository.java
      InventoryAuditRepository.java
      CreateProductRequest.java
      ProductService.java
      ProductController.java
    resources/
      application.properties
      schema.sql
      data.sql
  src/test/java/demo/inventory/
      ProductApiTest.java
~~~

### 15.2. settings.gradle

~~~groovy
rootProject.name = 'inventory-r2dbc-demo'
~~~

### 15.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 15.4. application.properties

~~~properties
spring.application.name=inventory-r2dbc-demo
spring.r2dbc.url=r2dbc:h2:mem:///inventory?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.sql.init.mode=always
~~~

H2 uses an in-memory database that does not persist across restarts. `spring.sql.init.mode=always` applies SQL initialization from resources on startup.

### 15.5. schema.sql

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    stock INTEGER NOT NULL,
    version BIGINT
);

CREATE TABLE inventory_audit (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_audit_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

### 15.6. data.sql

~~~sql
INSERT INTO products (name, stock, version)
VALUES ('USB-C Hub', 7, 0);

INSERT INTO products (name, stock, version)
VALUES ('Mechanical Keyboard', 12, 0);
~~~

### 15.7. InventoryApplication.java

~~~java
package demo.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

### 15.8. Product.java

~~~java
package demo.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
    @Id Long id,
    String name,
    int stock,
    @Version Long version
) {
}
~~~

### 15.9. InventoryAudit.java

~~~java
package demo.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("inventory_audit")
public record InventoryAudit(
    @Id Long id,
    @Column("product_id") Long productId,
    int quantity
) {
}
~~~

### 15.10. ProductRepository.java

~~~java
package demo.inventory;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

### 15.11. InventoryAuditRepository.java

~~~java
package demo.inventory;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface InventoryAuditRepository
        extends ReactiveCrudRepository<InventoryAudit, Long> {
}
~~~

### 15.12. CreateProductRequest.java

~~~java
package demo.inventory;

public record CreateProductRequest(
    String name,
    int stock
) {
}
~~~

### 15.13. ProductService.java

~~~java
package demo.inventory;

import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {
    private final ProductRepository products;
    private final InventoryAuditRepository audits;
    private final R2dbcEntityTemplate template;

    public ProductService(
            ProductRepository products,
            InventoryAuditRepository audits,
            R2dbcEntityTemplate template) {
        this.products = products;
        this.audits = audits;
        this.template = template;
    }

    public Mono<Product> create(CreateProductRequest request) {
        if (request.name() == null || request.name().isBlank()
                || request.stock() < 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Name must be nonblank and stock nonnegative"
            ));
        }

        return products.save(new Product(
            null, request.name().strip(), request.stock(), null
        ));
    }

    public Mono<Product> findById(long id) {
        return products.findById(id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Product not found"
                )
            ));
    }

    public Flux<Product> findAll() {
        return products.findAll();
    }

    public Flux<Product> findLowStock(int threshold) {
        if (threshold < 0) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "maxStock must be nonnegative"
            ));
        }

        return template.select(Product.class)
            .matching(Query.query(
                Criteria.where("stock")
                    .lessThanOrEquals(threshold)
            ))
            .all();
    }

    @Transactional
    public Mono<Product> reserve(long id, int quantity) {
        if (quantity <= 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Quantity must be positive"
            ));
        }

        return products.findById(id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "Product not found"
                )
            ))
            .flatMap(product -> {
                if (product.stock() < quantity) {
                    return Mono.error(
                        new ResponseStatusException(
                            HttpStatus.CONFLICT,
                            "Insufficient stock"
                        )
                    );
                }

                Product updated = new Product(
                    product.id(),
                    product.name(),
                    product.stock() - quantity,
                    product.version()
                );

                return products.save(updated);
            })
            .flatMap(saved ->
                audits.save(new InventoryAudit(
                    null, saved.id(), quantity
                )).thenReturn(saved)
            )
            .onErrorMap(
                OptimisticLockingFailureException.class,
                error -> new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Product updated concurrently",
                    error
                )
            );
    }
}
~~~

The controller calls the service through the Spring bean proxy. With a reactive transaction manager and the same ConnectionFactory, saving the product and saving the audit execute within one transaction.

### 15.14. ProductController.java

~~~java
package demo.inventory;

import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Product> all() {
        return service.findAll();
    }

    @GetMapping("/low-stock")
    public Flux<Product> lowStock(
            @RequestParam(defaultValue = "5") int maxStock) {
        return service.findLowStock(maxStock);
    }

    @GetMapping("/{id}")
    public Mono<Product> byId(@PathVariable long id) {
        return service.findById(id);
    }

    @PostMapping
    public Mono<ResponseEntity<Product>> create(
            @RequestBody Mono<CreateProductRequest> body) {
        return body
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Request body required"
                )
            ))
            .flatMap(service::create)
            .map(saved -> ResponseEntity
                .created(URI.create("/api/products/" + saved.id()))
                .body(saved));
    }

    @PutMapping("/{id}/reserve")
    public Mono<Product> reserve(
            @PathVariable long id,
            @RequestParam int quantity) {
        return service.reserve(id, quantity);
    }
}
~~~

### 15.15. ProductApiTest.java

~~~java
package demo.inventory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ProductApiTest {

    @Autowired
    WebTestClient client;

    @Autowired
    InventoryAuditRepository audits;

    private Product create(String name, int stock) {
        Product product = client.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateProductRequest(name, stock))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody(Product.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(product);
        assertNotNull(product.id());
        return product;
    }

    @Test
    void createsAndReadsProduct() {
        Product created = create(
            "New-" + UUID.randomUUID(),
            5
        );

        client.get()
            .uri("/api/products/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(Product.class)
            .value(saved -> {
                assertEquals(created.id(), saved.id());
                assertEquals(5, saved.stock());
            });
    }

    @Test
    void reservationWritesAudit() {
        Product created = create(
            "Stock-" + UUID.randomUUID(),
            5
        );

        client.put()
            .uri("/api/products/{id}/reserve?quantity=2",
                created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(Product.class)
            .value(saved ->
                assertEquals(3, saved.stock())
            );

        StepVerifier.create(
            audits.findAll()
                .filter(audit ->
                    audit.productId().equals(created.id()))
                .count()
        ).expectNext(1L).verifyComplete();
    }

    @Test
    void insufficientStockDoesNotCreateAudit() {
        Product created = create(
            "Low-" + UUID.randomUUID(),
            2
        );

        client.put()
            .uri("/api/products/{id}/reserve?quantity=3",
                created.id())
            .exchange()
            .expectStatus().isEqualTo(409);

        client.get()
            .uri("/api/products/{id}", created.id())
            .exchange()
            .expectStatus().isOk()
            .expectBody(Product.class)
            .value(saved ->
                assertEquals(2, saved.stock())
            );

        StepVerifier.create(
            audits.findAll()
                .filter(audit ->
                    audit.productId().equals(created.id()))
                .count()
        ).expectNext(0L).verifyComplete();
    }

    @Test
    void lowStockEndpointRespondsWithJson() {
        client.get()
            .uri("/api/products/low-stock?maxStock=7")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBodyList(Product.class);
    }
}
~~~

Tests create isolated products with random names, independent of seed IDs. Assertions verify HTTP 201/Location, GET, stock deduction, and audit creation. This is an HTTP + database integration test; it does not replace real PostgreSQL tests if production uses PostgreSQL.

### 15.16. Running the demo

In the project directory:

~~~bash
gradle bootRun
~~~

Try:

~~~bash
curl -s http://localhost:8080/api/products
~~~

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Laptop Stand","stock":9}'
~~~

The POST response returns HTTP 201 Created with Location. The generated ID depends on database state.

Use the ID from the response to reserve:

~~~bash
curl -i -X PUT \
  "http://localhost:8080/api/products/1/reserve?quantity=2"
~~~

Here `1` is only an example ID; use the actual ID from the list or POST response.

Filter low stock:

~~~bash
curl -s "http://localhost:8080/api/products/low-stock?maxStock=7"
~~~

Run tests:

~~~bash
gradle test
~~~

If a Gradle Wrapper is present in the project, replace `gradle` with `./gradlew`. Do not record fixed JSON stdout because generated ID/version and SELECT order may vary.

## 16. Production checklist

1. Does the R2DBC driver well support the database and required features?
2. Is there any unisolated JDBC/JPA/blocking SDK on the WebFlux path?
3. Do queries have proper indexes, limits, and ORDER BY?
4. Are concurrency and pool size controlled relative to the number of instances?
5. Are aggregate roots, `@Id`, `@Version`, and relationships mapped properly?
6. Are reactive transactions scoped to one ConnectionFactory without manual subscribe/block?
7. Are rollbacks, constraints, optimistic locking, and idempotency handled?
8. Is there a schema migration plan independent of the R2DBC runtime?
9. If using Redis/MongoDB/Elasticsearch, are consistency and source of truth defined?
10. Is there an outbox/saga when emitting events and updating a second datastore?
11. Are there Testcontainers tests against a real DB and concurrent update tests?
12. Are there metrics/logs/tracing for pools, SQL latency, and transactions?

## 17. Common errors

| Error | Why it is dangerous | How to fix |
| --- | --- | --- |
| Calling JPA/JDBC directly in a WebFlux handler | Blocks the event loop | R2DBC or boundedElastic with architectural review |
| Thinking Mono makes JDBC non-blocking | Wrapper does not change driver | Use R2DBC where appropriate |
| Using JpaRepository for a reactive service | Wrong persistence model | Spring Data ReactiveCrudRepository |
| Expecting Hibernate ddl-auto to create R2DBC tables | No JPA schema lifecycle | Migrations/SQL init |
| Assuming EntityManager/lazy loading exists | Does not exist in the R2DBC model | Explicit aggregates/projections/SQL |
| Calling subscribe inside a @Transactional method | Detaches the transaction context | Return the publisher to compose |
| Creating an infinite Flux inside a transaction | Holds the connection too long | Short, finite transactions |
| Reading the whole table then calling take(20) | Unoptimized SQL load | DB LIMIT/pagination |
| Concatenating user input into SQL | Injection | Bind parameters |
| Missing @Version on concurrent writes | Lost updates | Optimistic locking/atomic SQL |
| Retrying every failed write | Duplicate data | Idempotency/selective retries |
| Thinking Redis shares the SQL transaction | Divergence | Outbox/cache invalidation |
| Thinking reactive Redis repository always exists | Misunderstood module capabilities | Use ReactiveRedisTemplate |
| Trusting H2 tests as sufficient for PostgreSQL | Dialect and locking differences | Testcontainers with a real DB |
| Increasing pool indefinitely to fix latency | DB overload | Optimize queries and sizing |
| Logging sensitive parameters | Leaks secrets/PII | Redaction and bounded metrics |

## 18. Review questions with answers

**Question 1. How does R2DBC differ from JDBC?** R2DBC defines a reactive API for SQL via ConnectionFactory and publishers; traditional JDBC provides a blocking API.

**Question 2. Is Spring Data R2DBC reactive JPA?** No. It provides mapping, repositories, and templates, but lacks Hibernate's persistence context/lazy loading.

**Question 3. When should R2dbcEntityTemplate be used?** When queries need criteria/ad-hoc operations with entity mapping beyond derived repository methods.

**Question 4. How does DatabaseClient differ from R2dbcEntityTemplate?** DatabaseClient works directly with SQL and row mapping; the template adds an entity-oriented abstraction.

**Question 5. What does findById return when no row is found?** Mono.empty, which can be converted to 404 via switchIfEmpty.

**Question 6. What does @Version solve?** Optimistic locking for concurrent updates, preventing silent lost updates.

**Question 7. Where do reactive transactions bind?** Reactor subscriber Context, rather than traditional JDBC ThreadLocal.

**Question 8. Does R2dbcTransactionManager roll back Redis/cache?** No. It manages transactions on the ConnectionFactory of a single SQL datastore.

**Question 9. Does Mono.zip across MongoDB and SQL create a shared transaction?** No. It only composes the results of the publishers.

**Question 10. Why not use Flux.take(20) instead of SQL LIMIT?** Because limiting at the publisher layer does not guarantee reduced database work/query/row fetching.

**Question 11. Why is Testcontainers Postgres needed?** H2 differs in SQL dialect, locking, migrations, and generated values.

**Question 12. What makes publishing events after a SQL commit more reliable?** A transactional outbox with a worker, retries, and idempotent consumers.

## 19. Summary and official documentation

- R2DBC is a reactive specification for SQL, **not** an ORM or reactive Hibernate.
- ConnectionFactory connects the driver; DatabaseClient runs SQL; R2dbcEntityTemplate and repositories map entities.
- Reactive transactions require Reactor Context and a unified publisher chain.
- SQL transactions do not automatically cover Redis, MongoDB, Elasticsearch, or message brokers.
- Use migrations, indexes, query limits, pools, optimistic locking, and real-DB integration tests.
- Reactive Spring Data modules vary; pick a module by its actual semantics rather than inferring from method names.
- Combine outbox/saga and idempotency in multi-datastore systems.

Official documentation:

1. [Spring Data Relational — R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc.html): template/repository and architecture.
2. [Spring Framework — Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): DatabaseClient/ConnectionFactory/transactions.
3. [Spring Data — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-persistence.html): ID, version, and optimistic locking.
4. [Spring Data — Query Methods](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html): @Query, Pageable, and repository queries.
5. [Spring Data — Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html): @Table, @Id, @Column, @Version, aggregates.
6. [Spring Framework — @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): reactive transaction semantics.
7. [Spring Boot 3.5 — SQL/R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): auto-config and R2DBC properties.
8. [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql/data.sql.
9. [Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/): reactive document store.
10. [Spring Data Redis — Templates](https://docs.spring.io/spring-data/redis/reference/redis/template.html): ReactiveRedisTemplate and serialization.
11. [Spring Data Elasticsearch](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html): reactive index/search.
12. [Spring Data Cassandra](https://docs.spring.io/spring-data/cassandra/reference/): Cassandra mapping/repositories.
13. [Spring Boot 3.5 — R2DBC Pool Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): max-size, acquire timeout, and pooling.
