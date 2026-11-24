# TransactionalOperator, Reactive @Transactional, and the Same Execution Chain

## 1. The problem: multiple operations, one transaction

A business workflow may need to update multiple records under an all-or-nothing rule. For example, creating an order requires writing to two tables:

1. `purchase_orders` stores the order.
2. `audit_events` stores the order creation history.

If the order INSERT succeeds and then the audit INSERT fails, the application must **roll back both**. A database transaction provides the commit/rollback boundary to keep data consistent.

In Spring WebFlux, Spring Data R2DBC, and Project Reactor, repository methods typically return `Mono<T>` or `Flux<T>`. A Publisher only describes work; SQL actually begins when the Publisher is **subscribed to**. Therefore, a reactive transaction must wrap the **subscription and reactive pipeline**, not merely a few lines of Java constructing the Publisher.

Spring supports:

- `@Transactional`: declarative transactions via a Spring AOP proxy for methods returning a reactive Publisher.
- `TransactionalOperator`: programmatic transactions, wrapping a `Mono/Flux` or using the `execute` callback.

**Central principle:** all operations intended to share a transaction must belong to one returned Publisher chain, the same Reactor subscriber Context, and the same resource manager (for instance, one R2DBC ConnectionFactory).

### Learning objectives

After this lesson, you will:

- Distinguish `ReactiveTransactionManager` from `PlatformTransactionManager`.
- Understand that reactive transactions use **Reactor Context** instead of ThreadLocal.
- Write `@Transactional` on methods returning `Mono` or `Flux` correctly.
- Use `TransactionalOperator.create(...)`, `.as(operator::transactional)`, and `execute(...)`.
- Place transaction boundaries so INSERT and UPDATE steps commit/roll back together.
- Handle errors, `onErrorResume`, cancellation, `take`, timeouts, and retries properly.
- Implement and test on Spring Boot 3.5.7, Java 17, and H2 R2DBC.
- Recognize the limits of database transactions when combined with HTTP, Kafka, and multiple resources.

## 2. How reactive transactions work

### 2.1. Transaction manager and resources

| Criterion | Imperative transaction | Reactive transaction |
| --- | --- | --- |
| Interface | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| Examples | `DataSourceTransactionManager`, `JpaTransactionManager` | `R2dbcTransactionManager` |
| State | Thread-bound, typically using ThreadLocal | Subscriber-bound, using Reactor Context |
| Access technology | JDBC/JPA | R2DBC, compatible reactive drivers |
| Declaration style | `@Transactional`/`TransactionTemplate` | `@Transactional`/`TransactionalOperator` |
| Triggered | When the imperative method executes | When the Publisher is subscribed to |

`R2dbcTransactionManager` manages R2DBC `Connection` instances obtained from a `ConnectionFactory`. Spring binds the transaction-bound connection into the subscriber Context; `DatabaseClient` and Spring Data R2DBC can then use that exact connection within the reactive chain.

If a method opens a different connection via `ConnectionFactories.get(...)` or calls `JdbcTemplate`, that operation **does not automatically join** the current R2DBC transaction.

### 2.2. Transactions use Reactor Context, not ThreadLocal

~~~text
Caller subscribes
       |
       v
  TransactionInterceptor / TransactionalOperator
       |
       +-- begin transaction
       |      |
       |      v
       |  R2DBC Connection bound in Reactor Context
       |      |
       |      +--> INSERT purchase_orders
       |      |
       |      +--> INSERT audit_events
       |
       +-- onComplete --> COMMIT
       |
       +-- onError ----> ROLLBACK
       |
       +-- cancel -----> ROLLBACK
       |
       v
   cleanup resource
~~~

Reactor Context travels with the subscriber and propagates across compatible operators. Switching threads with `publishOn` or `subscribeOn` **does not automatically drop** the Context as long as it remains in the same pipeline. However, calling `subscribe()` internally creates an independent subscriber that may run outside the caller's transaction.

You cannot inspect a reactive transaction simply by checking a ThreadLocal variable on the same thread.

### 2.3. Transactions begin on subscription

~~~java
Mono<Void> work = store.insertOrder(1L, "Linh")
    .then(store.insertAudit(1L, "CREATED"));

Mono<Void> transactional =
    work.as(operator::transactional);
~~~

The code above only constructs a Publisher. When the caller subscribes to `transactional`, the manager begins the transaction; the SQL statements execute; when the Publisher terminates, the manager commits or rolls back.

Consequences:

- Calling a method that creates a Mono does not mean SQL has already run.
- Each new subscription can start a new transaction and re-execute side effects.
- `retry` and `repeat` can cause duplicate INSERTs without idempotency.
- A transaction requires a completing source; do not wrap an infinite `Flux` in a transaction.
- When a Publisher emits an item without completing yet, that does not prove the data has committed.

### 2.4. Resource scope

A database transaction coordinates the resources belonging to its manager. `R2dbcTransactionManager` cannot roll back an HTTP request already sent via `WebClient`, an email already sent, or a Kafka message already published. To ensure cross-system business consistency, consider transactional outbox, sagas, retries, and idempotency.

## 3. Reactive @Transactional

### 3.1. Common syntax

~~~java
@Service
public class OrderService {

    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    @Transactional
    public Mono<Long> create(long id, String customer) {
        return store.insertOrder(id, customer)
            .then(store.insertAudit(id, "CREATED"))
            .thenReturn(id);
    }
}
~~~

Spring's `TransactionInterceptor` inspects the return type. If the method is invoked through a proxy and a `ReactiveTransactionManager` is configured, Spring decorates the Publisher with a transaction boundary. A subscriber then triggers the logic inside the transaction.

### 3.2. Return type must be reactive

With a reactive manager, the method should return `Mono<T>`, `Flux<T>`, `Mono<Void>`, or a compatible reactive type. A `void` method or synchronous DTO return does not provide a reactive pipeline for Spring to manage; those require the imperative branch and an appropriate `PlatformTransactionManager`.

Wrong example:

~~~java
@Transactional
public void createWrong(long id) {
    store.insertOrder(id, "Linh").subscribe();
}
~~~

The method returns `void` and subscribes internally. It does not establish the expected reactive transaction. The right approach is to return the Publisher to the caller or framework.

### 3.3. Spring AOP proxy and self-invocation

In proxy mode, `@Transactional` only intercepts calls **passing through the Spring proxy**. If a bean calls its own annotated method directly, the annotation on the target method may have no effect:

~~~java
@Service
public class BadService {

    public Mono<Void> outer() {
        return inner(); // this.inner(): bypasses proxy
    }

    @Transactional
    public Mono<Void> inner() {
        return doReactiveDatabaseWork();
    }
}
~~~

Fix this by placing the transaction on a public service method called from another bean, moving the transactional method to a separate service bean, or using `TransactionalOperator` where the Publishers are composed. Do not expect private methods to be intercepted by Spring AOP.

### 3.4. Defaults and rollback rules

By default, `@Transactional` uses `Propagation.REQUIRED`, `Isolation.DEFAULT`, read-write mode, the transaction system's default timeout, and rollback on `RuntimeException`/`Error`. Checked exceptions do not trigger rollback by default; you can specify `rollbackFor`.

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    rollbackFor = IOException.class
)
public Mono<Void> update(...) {
    return store.update(...);
}
~~~

This snippet illustrates another method, not a standalone runnable file. Isolation, timeout, and propagation must be supported by the driver/manager. Spring Framework 6.2 offers a global `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` option if the application explicitly configures it.

`@Transactional(readOnly = true)` is a hint/setting; whether writes are rejected depends on the backend, and it does not replace authorization.

## 4. TransactionalOperator: programmatic transactions

### 4.1. Creating the bean

~~~java
@Configuration(proxyBeanMethods = false)
public class TxConfig {

    @Bean
    TransactionalOperator transactionalOperator(
        ReactiveTransactionManager manager
    ) {
        return TransactionalOperator.create(manager);
    }
}
~~~

The correct package is `org.springframework.transaction.reactive.TransactionalOperator`. Spring recommends `TransactionTemplate` for imperative code and `TransactionalOperator` for reactive code.

### 4.2. Operator style: placing the boundary in the right position

~~~java
Mono<Long> businessWork = store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .thenReturn(id);

return businessWork.as(operator::transactional);
~~~

`.as(operator::transactional)` wraps the upstream Publisher. Both INSERTs run inside the transaction.

Wrong:

~~~java
return store.insertOrder(id, customer)
    .as(operator::transactional)
    .then(store.insertAudit(id, "CREATED"));
~~~

In the wrong example, the transaction wraps only the first INSERT; the audit sits after the transactional Publisher and does not participate in that boundary. If the audit fails, the order may already be committed.

Right:

~~~java
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional);
~~~

### 4.3. Callback style: execute

`execute` allows using `ReactiveTransaction` to control transaction status:

~~~java
Flux<Long> result = operator.execute(status ->
    store.insertOrder(id, customer)
        .then(store.insertAudit(id, "CREATED"))
        .thenReturn(id)
);
~~~

`execute` returns `Flux<T>` even if the callback only emits one item. When guaranteed to emit a single item, you can convert it to a Mono with:

~~~java
Mono<Long> result = operator.execute(status ->
    store.insertOrder(id, customer).thenReturn(id)
).single();
~~~

Do not use `single()` if the Publisher can complete empty. Be careful with `next()` because it can cancel after the first item, triggering rollback instead of commit.

### 4.4. Marking rollback-only

~~~java
Flux<String> outcome = operator.execute(status ->
    store.insertOrder(id, customer)
        .then(Mono.fromSupplier(() -> {
            status.setRollbackOnly();
            return "not committed due to business policy";
        }))
);
~~~

`status.setRollbackOnly()` requests a rollback even though the callback emitted no error. For typical business errors, emitting `Mono.error(new BusinessException(...))` can make the control flow clearer.

### 4.5. TransactionDefinition

~~~java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();

definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
definition.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(10);

TransactionalOperator operator =
    TransactionalOperator.create(manager, definition);
~~~

Not every R2DBC driver supports all isolation levels and propagation behaviors identically. Test on the actual production database.

### 4.6. Choosing annotation or operator?

| Criterion | `@Transactional` | `TransactionalOperator` |
| --- | --- | --- |
| Configuration | Declarative | Programmatic |
| Requires proxy | Yes, in proxy mode | No |
| Boundary | Wraps the Publisher returned by the method | Explicitly wraps a Publisher segment |
| Rollback-only callback | Not directly via annotation | Has `execute(status -> ...)` |
| Useful when | Business service methods | Workflows composing multiple segments needing explicit boundary control |
| Common pitfalls | Self-invocation and wrong return type | Placing `.as(...)` too early |

Avoid wrapping the same segment with both annotation and operator just to “be safer”; nested transaction boundaries can make propagation and rollback-only harder to reason about.

## 5. Same execution chain: right and wrong

### 5.1. Using then to chain Mono<Void>

~~~java
public Mono<Void> create(long id, String customer) {
    return store.insertOrder(id, customer)
        .then(store.insertAudit(id, "CREATED"))
        .as(operator::transactional);
}
~~~

`then` waits for the first INSERT to complete before starting the second INSERT. Both publishers are composed within the same subscriber transaction context.

Wrong:

~~~java
public Mono<Void> createWrong(long id, String customer) {
    store.insertOrder(id, customer).subscribe(); // detached subscriber
    return store.insertAudit(id, "CREATED")
        .as(operator::transactional);
}
~~~

The first statement runs on an independent subscription; an error/rollback on the audit cannot roll it back.

### 5.2. Mono<Void>.flatMap does not run the callback

~~~java
// WRONG: Mono<Void> completes without onNext
return store.insertOrder(id, customer)
    .flatMap(ignored -> store.insertAudit(id, "CREATED"));
~~~

`flatMap` only runs on `onNext`, whereas `Mono<Void>` completes empty. Therefore the audit never runs. Use `then`:

~~~java
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"));
~~~

When the first step returns an actual ID, `flatMap` is appropriate:

~~~java
return store.createAndReturnId(customer)
    .flatMap(id -> store.insertAudit(id, "CREATED")
        .thenReturn(id))
    .as(operator::transactional);
~~~

### 5.3. Multiple sequential operations

A transaction-bound R2DBC connection generally should not run multiple SQL statements concurrently when the driver/connection does not support it. For ordered commands, use `concatMap`:

~~~java
return Flux.fromIterable(commands)
    .concatMap(store::applyCommand)
    .then()
    .as(operator::transactional);
~~~

`flatMap` can run concurrently and reorder items. For dependent operations, preserve ordering or reduce concurrency appropriately.

### 5.4. Publishers must be lazy

~~~java
return Mono.defer(() -> store.insertOrder(id, customer))
    .then(Mono.defer(() -> store.insertAudit(id, "CREATED")))
    .as(operator::transactional);
~~~

`Mono.defer` creates the source at subscription time; do not run side-effecting code beforehand and then wrap a transaction around it. Do not take a hot Publisher already running outside and expect the operator to “reach back” around work that already occurred.

### 5.5. Switching schedulers does not automatically lose Context

~~~java
return store.insertOrder(id, customer)
    .publishOn(Schedulers.parallel())
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional);
~~~

Within the same Reactor chain, the subscriber Context can propagate across schedulers. However, calling blocking JDBC on that scheduler does not make JDBC a resource of the R2DBC transaction. Do not use ThreadLocal to check a reactive transaction.

### 5.6. Subscribing twice means executing twice

~~~java
Mono<Void> operation = store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional);

operation.subscribe();
operation.subscribe(); // potentially duplicate INSERT
~~~

This is code you **should not use** in a service. Each subscription can start a new transaction. Let the framework/caller manage subscriptions and design for idempotency on retries or restarts.

## 6. Errors, recovery, cancellation, and retries

### 6.1. Error signals trigger rollback

~~~java
return store.insertOrder(id, customer)
    .then(Mono.error(
        new IllegalStateException("audit failed")))
    .as(operator::transactional);
~~~

After the first insert completes, `onError` occurs inside the boundary. The manager rolls back the transaction; the caller receives the error signal.

### 6.2. onErrorResume inside the boundary can commit

~~~java
// WRONG: swallowing the error before TransactionalOperator sees it
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .onErrorResume(ex -> Mono.empty())
    .as(operator::transactional);
~~~

The error is turned into `onComplete` inside the transaction. The operator may commit the INSERT that already ran.

If you want to roll back first and then return a fallback:

~~~java
return store.insertOrder(id, customer)
    .then(store.insertAudit(id, "CREATED"))
    .as(operator::transactional)
    .onErrorResume(ex -> {
        // Transaction has already observed the error.
        return Mono.empty();
    });
~~~

Or re-emit `Mono.error(ex)` from the inner handler branch. If you intentionally want to roll back while still returning a value, use the `execute` callback and `setRollbackOnly()`.

### 6.3. Cancel signals also roll back

Spring Framework 5.3+ rolls back a reactive transaction when the subscription is cancelled. Downstream operators such as `take(n)`, `next()`, `timeout(Duration)`, or caller disposal can emit cancellation.

~~~java
Flux<Event> transactionalStream =
    store.findAndUpdateAll()
        .as(operator::transactional);

Mono<Event> first = transactionalStream.next();
~~~

`next()` may cancel the Flux after the first item, causing the transaction to roll back. An emitted item does not prove commit. With a transactional Flux, you usually must let the source **complete fully** to commit.

### 6.4. Do not hold a transaction around an infinite stream

~~~java
// Anti-pattern: do not use this long-lived transaction
@Transactional
public Flux<Event> forever() {
    return eventSource.events();
}
~~~

If the stream never completes, the transaction holds a connection and possibly locks for too long, eventually getting cancelled and rolled back. Better is to split into finite transactions per item or batch:

~~~java
return eventSource.events()
    .concatMap(event ->
        store.persist(event).as(operator::transactional));
~~~

This snippet is illustrative, assuming `store.persist` returns the corresponding Publisher. In production, limit throughput and define duplicate-delivery semantics.

### 6.5. Place retries outside the boundary

~~~java
return performWork()
    .as(operator::transactional)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure)
    );
~~~

Placing retry outside the boundary creates a fresh transaction per attempt. If placed inside the transaction, partial work could re-run when the transaction/connection is already broken. Only retry transient errors, cap attempts and deadlines, and ensure idempotency.

### 6.6. Timeouts and side effects

`timeout` can cancel the transaction while waiting for results. If an HTTP call already executed outside the database transaction, the HTTP side effect may still have completed even though the database rolled back. Do not treat a timeout as proof that “nothing happened”.

## 7. Propagation, isolation, and the data ecosystem

- `REQUIRED`: join the current transaction when possible, or create a new one.
- `REQUIRES_NEW`: require an independent transaction, depending on manager/driver support.
- `SUPPORTS`: join if a transaction exists.
- `MANDATORY`: require an existing transaction.
- `NOT_SUPPORTED`: execute outside a transaction when the manager supports suspending.

Isolation levels such as `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE` behave differently by database. Do not copy JPA assumptions over to R2DBC without testing.

`DatabaseClient`, `R2dbcEntityTemplate`, and `ReactiveCrudRepository` can participate in an R2DBC transaction when sharing the same ConnectionFactory and appropriate framework integration. `JdbcTemplate`, `JpaRepository`, or `ReactiveMongoTransactionManager` use different resources and are not automatically merged into an R2DBC transaction.

An R2DBC transaction does not cover `WebClient`, Kafka, email, object storage, or another database. When DB writes and messages must stay in sync, use a **transactional outbox**: write the business record and the outbox row in the same transaction, then have a worker publish after commit; consumers handle duplicates idempotently. For multi-service workflows, consider **sagas/compensation** rather than assuming distributed ACID.

## 8. Complete example: Spring Boot 3.5.7 + Java 17 + R2DBC H2

The project creates a purchase order and an audit event in the same transaction. Both styles are tested: `@Transactional` and `TransactionalOperator`. When the audit step emits an error, the initial order must roll back.

### 8.1. Project structure

~~~text
reactive-tx-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── schema.sql
├── src/main/java/example/tx/
│   ├── ReactiveTxApplication.java
│   ├── ReactiveTxConfig.java
│   ├── PurchaseStore.java
│   └── PurchaseService.java
└── src/test/java/example/tx/
    └── PurchaseTransactionTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>reactive-tx-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

The R2DBC starter provides Spring Data R2DBC and DatabaseClient. `r2dbc-h2` provides the in-memory driver. The AOP starter explicitly supplies the proxy dependency needed for the annotation example.

### 8.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.r2dbc.url=r2dbc:h2:mem:///txdemo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.sql.init.mode=always
~~~

`spring.sql.init.mode=always` runs `schema.sql` when Boot starts; the H2 options keep the in-memory database alive across short-lived connection closes. This is a learning example, not a production database configuration.

### 8.4. schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS purchase_orders (
    id BIGINT PRIMARY KEY,
    customer VARCHAR(160) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    order_id BIGINT PRIMARY KEY,
    action VARCHAR(80) NOT NULL
);
~~~

### 8.5. ReactiveTxApplication.java

~~~java
package example.tx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
~~~

### 8.6. ReactiveTxConfig.java

~~~java
package example.tx;

import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration(proxyBeanMethods = false)
public class ReactiveTxConfig {

    @Bean
    public ReactiveTransactionManager transactionManager(
        ConnectionFactory connectionFactory
    ) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean
    public TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager
    ) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Spring Boot can auto-configure an R2DBC manager when the application has not declared one; the example creates the beans explicitly to make it clear the manager uses the same ConnectionFactory. `TransactionalOperator` is a bean that can be shared across services.

### 8.7. PurchaseStore.java

~~~java
package example.tx;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class PurchaseStore {

    private final DatabaseClient db;

    public PurchaseStore(DatabaseClient db) {
        this.db = db;
    }

    public Mono<Void> insertOrder(long id, String customer) {
        return db.sql(
                "INSERT INTO purchase_orders(id, customer) " +
                "VALUES (:id, :customer)"
            )
            .bind("id", id)
            .bind("customer", customer)
            .fetch().rowsUpdated().then();
    }

    public Mono<Void> insertAudit(long id, String action) {
        return db.sql(
                "INSERT INTO audit_events(order_id, action) " +
                "VALUES (:id, :action)"
            )
            .bind("id", id)
            .bind("action", action)
            .fetch().rowsUpdated().then();
    }

    public Mono<Long> countOrders(long id) {
        return db.sql(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = :id"
            )
            .bind("id", id)
            .map((row, metadata) ->
                ((Number) row.get(0)).longValue())
            .one();
    }

    public Mono<Long> countAudits(long id) {
        return db.sql(
                "SELECT COUNT(*) FROM audit_events WHERE order_id = :id"
            )
            .bind("id", id)
            .map((row, metadata) ->
                ((Number) row.get(0)).longValue())
            .one();
    }
}
~~~

`rowsUpdated().then()` creates a `Mono<Void>` that completes once the INSERT finishes. The Boot-created `DatabaseClient` uses the ConnectionFactory matching the transaction manager. SQL uses bind parameters instead of concatenating input directly into strings.

### 8.8. PurchaseService.java

~~~java
package example.tx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PurchaseService {

    private final PurchaseStore store;
    private final TransactionalOperator tx;

    public PurchaseService(
        PurchaseStore store,
        TransactionalOperator tx
    ) {
        this.store = store;
        this.tx = tx;
    }

    @Transactional
    public Mono<Long> createAnnotated(
        long id, String customer, boolean failAudit
    ) {
        return savePair(id, customer, failAudit);
    }

    public Mono<Long> createProgrammatic(
        long id, String customer, boolean failAudit
    ) {
        return savePair(id, customer, failAudit)
            .as(tx::transactional);
    }

    private Mono<Long> savePair(
        long id, String customer, boolean failAudit
    ) {
        return store.insertOrder(id, customer)
            .then(Mono.defer(() ->
                failAudit
                    ? Mono.<Void>error(new IllegalStateException(
                        "simulated audit failure"))
                    : store.insertAudit(id, "CREATED")
            ))
            .thenReturn(id);
    }
}
~~~

`savePair` is just a helper assembling the Publisher. In the failure case, it INSERTs the order and then emits an error; the annotation/operator on the outer method must roll back. There is no internal `subscribe()` or `block()`.

### 8.9. PurchaseTransactionTest.java

~~~java
package example.tx;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class PurchaseTransactionTest {

    @Autowired
    PurchaseService service;

    @Autowired
    PurchaseStore store;

    @Test
    void annotationCommitsBothWrites() {
        StepVerifier.create(
                service.createAnnotated(1001L, "Linh", false))
            .expectNext(1001L)
            .verifyComplete();

        assertCounts(1001L, 1L, 1L);
    }

    @Test
    void annotationRollsBackBothWritesOnError() {
        StepVerifier.create(
                service.createAnnotated(1002L, "An", true))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException &&
                error.getMessage().contains("simulated audit failure"))
            .verify();

        assertCounts(1002L, 0L, 0L);
    }

    @Test
    void operatorCommitsBothWrites() {
        StepVerifier.create(
                service.createProgrammatic(2001L, "Binh", false))
            .expectNext(2001L)
            .verifyComplete();

        assertCounts(2001L, 1L, 1L);
    }

    @Test
    void operatorRollsBackBothWritesOnError() {
        StepVerifier.create(
                service.createProgrammatic(2002L, "Hoa", true))
            .expectErrorMatches(error ->
                error instanceof IllegalStateException &&
                error.getMessage().contains("simulated audit failure"))
            .verify();

        assertCounts(2002L, 0L, 0L);
    }

    private void assertCounts(
        long id, long expectedOrders, long expectedAudits
    ) {
        StepVerifier.create(store.countOrders(id))
            .expectNext(expectedOrders)
            .verifyComplete();

        StepVerifier.create(store.countAudits(id))
            .expectNext(expectedAudits)
            .verifyComplete();
    }
}
~~~

Tests call the Spring bean service so the `@Transactional` proxy gets a chance to intercept. Each test uses a separate ID to avoid collisions. After the Publisher finishes, the test queries the DB **outside the transaction** and compares row counts: commit = 1/1, rollback = 0/0.

### 8.10. How to run

Install JDK 17+ and Maven, then:

~~~bash
mvn test
~~~

Expected result: 4 integration tests pass and Maven prints `BUILD SUCCESS`. This is expected from the project structure, **not output executed inside this article**.

You can start the Spring process:

~~~bash
mvn spring-boot:run
~~~

Because of `spring.main.web-application-type=none`, the project creates no HTTP endpoints. To exercise the business flow, use integration tests or a suitable runner; do not curl non-existent URLs.

## 9. Testing transactions and advanced scenarios

### 9.1. An error alone is not enough to prove rollback

A rollback test must prove both the error signal and the database state. Verification order:

1. The Publisher emits the expected error.
2. The boundary has finished processing the rollback.
3. A fresh query outside the transaction does not see the inserted order.
4. No partial audit record is visible.

In the example, `assertCounts(id, 0L, 0L)` is a critical postcondition. If you only assert `expectError`, the transaction could be misconfigured while the test still passes.

### 9.2. Real SQL errors

You can add a test creating a duplicate primary key on `audit_events.order_id` so the driver emits a data-access exception. After the second failure, the transaction must roll back the first INSERT too. Between H2 and PostgreSQL, exception messages and wrapper classes may differ; avoid asserting overly specific driver message strings.

### 9.3. @DataR2dbcTest is not transactional by default

Unlike many JDBC/JPA tests, Spring Boot's `@DataR2dbcTest` is **not transactional** by default. To test actual service transactions, use `@SpringBootTest` or manually configure the service, manager, and Publisher properly, then query results after completion.

Do not put `@Transactional` on a test just to get automatic rollback and mistake that for proof that the service's transaction works.

### 9.4. Reactive TransactionSynchronizationManager

`org.springframework.transaction.reactive.TransactionSynchronizationManager` differs from the imperative `org.springframework.transaction.support.TransactionSynchronizationManager` class. You can use it to debug a subscriber's transaction state when genuinely needed. Do not embed transaction internals into business code if annotations/operators already suffice.

## 10. Common mistakes

**1. Using PlatformTransactionManager for R2DBC.** Reactive pipelines require `ReactiveTransactionManager`.

**2. Thinking calling a method returning Mono runs the transaction.** Transactions only activate on subscription.

**3. @Transactional self-invocation.** Calls not passing through the Spring proxy may not have the annotation applied.

**4. Putting @Transactional on private/void methods.** Proxy and return type are incompatible with reactive transactions.

**5. Calling subscribe() in a service.** Independent subscriptions can detach from the transaction and hide errors.

**6. Calling block() on the event loop.** Risks blocking and breaks reactive composition.

**7. Wrapping `.as(...)` before the last operation.** Operations after the boundary will not roll back with the preceding ones.

**8. flatMap after Mono<Void>.** Mono<Void> does not emit onNext; use `then`.

**9. Swallowing errors with onErrorResume inside a transaction.** The operator may see completion and commit earlier writes.

**10. Using next()/take(n) on a transactional Flux and expecting commit.** Cancellation can trigger rollback.

**11. Transaction wrapping an infinite Flux.** Holds connections/locks too long; split into finite transactions.

**12. Concurrent flatMap running SQL on one connection.** Can cause driver errors or wrong ordering; use concatMap when needed.

**13. Mixing JDBC/JPA and R2DBC.** They do not automatically join the same transaction context.

**14. Using two different ConnectionFactories.** Resource managers do not automatically coordinate together.

**15. Retrying without idempotency.** Re-subscription can cause duplicate side effects.

**16. Thinking readOnly forbids writes.** Behavior depends on the database and driver.

**17. Thinking R2DBC rolls back WebClient/Kafka.** You need outbox, sagas, or another consistency policy.

**18. Tests only checking errors without querying the DB.** Does not prove atomicity.

**19. Not testing actual isolation/propagation.** Drivers/managers may not support every mode fully.

**20. Wrapping with both annotation and operator unintentionally.** Nested boundaries make rollbackOnly/propagation confusing.

**21. Using a hot Publisher already running before the boundary.** Side effects may have occurred before subscribing to the transaction.

**22. Holding a DB transaction while waiting on slow HTTP.** Increases contention and connection pool pressure.

## 11. Production checklist

1. Is the repository R2DBC or JDBC? Is the manager the right type?
2. Are annotations invoked through the proxy?
3. Do methods return Mono/Flux instead of void/synchronous DTOs?
4. Do all DB operations stay inside the same returned Publisher?
5. Are there any internal `subscribe()` calls creating independent subscribers?
6. Do the repositories use the same ConnectionFactory/transaction manager?
7. Do `then`/`concatMap` preserve ordering where required?
8. Is `TransactionalOperator` placed after all work needing atomicity?
9. Could `onErrorResume` unintentionally turn an error into a commit?
10. Are cancellation/timeouts managed and rollback-on-cancel understood?
11. Is any transactional Flux finite and completing?
12. Are retries bounded, scoped to transient errors, and idempotent?
13. Have isolation/propagation/readOnly been tested on the production DB?
14. Are there remote side effects outside the transaction needing an outbox?
15. Do integration tests verify DB state after both commit and rollback?
16. Are transaction duration, rollback rate, connection pool, and lock contention monitored?
17. Are schema migrations, timeouts, and pool sizing properly configured?

## 12. Review questions

1. Does a reactive transaction start when creating the Mono or on subscription? **On subscription.**
2. Does a reactive manager use ThreadLocal or Reactor Context? **Reactor Context.**
3. Which resource does R2dbcTransactionManager manage? **An R2DBC Connection.**
4. Why does @Transactional need a Spring proxy? **An AOP interceptor manages the boundary through the proxy.**
5. When does self-invocation happen? **When a method in the same object calls an annotated method bypassing the proxy.**
6. What return types suit a reactive manager? **Mono/Flux or a compatible Publisher.**
7. How is operator style used? **`publisher.as(operator::transactional)`.**
8. What Publisher type does `execute` return? **Flux<T>.**
9. How do you mark rollback-only inside a callback? **`status.setRollbackOnly()`.**
10. What happens if `as` is placed before the audit step? **The audit runs outside the wrapped transaction.**
11. Why does Mono<Void>.flatMap not run? **Mono<Void> does not emit onNext.**
12. When should `then` be used? **When waiting for one Publisher to complete before executing the next step.**
13. Does `publishOn` automatically erase Reactor Context? **No, as long as it remains in the same chain.**
14. Why is internal `subscribe()` dangerous? **It creates a subscription with a detached lifecycle/context.**
15. What can `onErrorResume` before the operator cause? **Turning an error into completion and committing prior work.**
16. What does cancelling a reactive transaction in Spring 5.3+ lead to? **Rollback.**
17. Should a transaction be held across an infinite Flux? **No.**
18. What can an outer retry around the boundary do? **Start a new transaction for each attempt.**
19. Does an R2DBC transaction roll back HTTP requests? **No.**
20. What is the common pattern linking DB commit and message publication? **Transactional outbox + idempotent consumer.**
21. Does a rollback test need to query the DB after the transaction? **Yes, to verify the state rolled back.**
22. Is `@DataR2dbcTest` transactional by default? **No.**

## 13. Conclusion and references

- Both reactive `@Transactional` and `TransactionalOperator` manage transactions on the Publisher, not on the Java lines assembling the Publisher.
- Transactions live in the **Reactor subscriber Context**, not passed through ThreadLocal as in the imperative model.
- All DB operations must stay in the same reactive chain/subscription and resource manager when atomicity is needed.
- `@Transactional` must be called through a proxy; `TransactionalOperator` needs its boundary placed accurately.
- `then` fits chaining after `Mono<Void>`; use `concatMap` for ordered SQL sequences.
- `onError` normally rolls back; swallowing errors inside the boundary can cause commits; cancellation also rolls back.
- Infinite Fluxes, non-idempotent retries, internal subscribes, and HTTP side effects inside transactions are major risks.
- Test commit/rollback with out-of-transaction DB queries after the Publisher finishes.
- For Kafka/HTTP/multi-system flows, use outbox or sagas rather than expecting one R2DBC transaction to manage everything.

**Official documentation**

1. [Spring Framework 6.2 — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): TransactionalOperator, operator/callback styles, rollback on cancellation, TransactionDefinition.
2. [Spring Framework 6.2 — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html): AOP proxy, ReactiveTransactionManager, and Reactor Context.
3. [Spring Framework 6.2 — Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): annotations, return types, rollback rules, proxy mode.
4. [Spring Framework 6.2 — R2DBC Data Access](https://docs.spring.io/spring-framework/reference/6.2/data-access/r2dbc.html): DatabaseClient, R2dbcTransactionManager, and ConnectionFactoryUtils.
5. [Spring Boot 3.5 — SQL Databases / R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): ConnectionFactory, embedded H2, DatabaseClient.
6. [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): schema.sql and spring.sql.init.mode.
7. [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@DataR2dbcTest` is not transactional by default.
8. [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, Context, then, retry, concatMap, cancellation, StepVerifier.
