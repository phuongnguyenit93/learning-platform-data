# ReactiveTransactionManager and Subscription-Scoped Transaction Context

**Module:** Spring Framework – reactive  
**Parent topic:** Ecosystem integrations  
**Goal:** Understand why reactive transactions follow `Reactor Context` instead of `ThreadLocal`, when a transaction starts/ends, how to use `ReactiveTransactionManager`, `@Transactional`, and `TransactionalOperator` with R2DBC, while avoiding pitfalls from subscription, cancellation, retries, and resource ownership.

## 1. Core summary

In traditional imperative transactions, Spring uses `PlatformTransactionManager` and typically binds transaction state to the current thread via `ThreadLocal`. JDBC code on the same thread can locate the connection participating in the transaction.

In reactive code, execution can switch threads after `publishOn`, network callbacks, or async operations. Therefore, **thread identity cannot serve as the transaction boundary**. Spring uses `ReactiveTransactionManager` to attach transaction state and resources to the **subscriber's Reactor Context**, and reactive database operations in the same pipeline access that resource.

Three points to remember:

1. **Declaration is not execution.** Calling a method returning `Mono`/`Flux` or creating a `TransactionalOperator` does not open a transaction on its own; the transaction is triggered when the publisher is subscribed to.
2. **One subscription is one execution.** Re-subscribing to a cold transactional publisher generally initiates a new execution and a new transaction, rather than “re-reading” the previous commit's result.
3. **Transactions follow the reactive chain.** Data access steps must remain inside the transactionally wrapped pipeline and preserve the same Reactor Context. Manually calling `subscribe()` creates an independent flow; blocking JDBC does not automatically participate in an R2DBC transaction.

A typical transaction: **subscription → begin → acquire/bind connection → SQL publisher → commit or rollback → release connection**.

## 2. What is ReactiveTransactionManager?

`org.springframework.transaction.ReactiveTransactionManager` is Spring's reactive contract for managing transactions. Instead of immediately returning `TransactionStatus` or performing blocking operations, its methods return publishers:

```java
public interface ReactiveTransactionManager extends TransactionManager {

    Mono<ReactiveTransaction> getReactiveTransaction(
            TransactionDefinition definition);

    Mono<Void> commit(ReactiveTransaction transaction);

    Mono<Void> rollback(ReactiveTransaction transaction);
}
```

This is an **abbreviated signature for learning**, not the complete interface source. It expresses three actions: obtaining or joining a transaction, committing, and rolling back. An implementation must manage resources, propagation, synchronization, and cleanup per the backend's contract.

Common implementations/concepts:

| Backend | Transaction manager or mechanism | Scope |
|---|---|---|
| R2DBC | `R2dbcTransactionManager` | A `ConnectionFactory` and the connections it provides |
| Reactive MongoDB | `ReactiveMongoTransactionManager` | A MongoDB session; requires server configuration supporting transactions |
| JDBC/JPA | `JdbcTransactionManager`, `JpaTransactionManager` | Imperative; not used to turn JDBC calls into R2DBC |
| Custom code | `ReactiveTransactionManager` implementation | Only when custom transactional resource management is required |

Use the right manager for the resource you operate on. An R2DBC transaction does not automatically encompass MongoDB, Kafka, HTTP, or another database.

### 2.1. ReactiveTransactionManager vs PlatformTransactionManager

| Criterion | PlatformTransactionManager | ReactiveTransactionManager |
|---|---|---|
| Model | Imperative | Reactive Publisher |
| Default context | Thread-bound via `ThreadLocal` | Subscriber-bound via `Reactor Context` |
| Start | During imperative method/proxy invocation | Upon subscribing to the transactional publisher |
| Resource | JDBC `Connection`, JPA `EntityManager`... | R2DBC `Connection`, reactive session... |
| Programmatic API | `TransactionTemplate` | `TransactionalOperator` |
| Declarative methods | Mostly return objects/`void` | Return `Publisher`/`Mono`/`Flux` |
| Works cleanly across thread switches | ThreadLocal does not automatically propagate | Context travels with the reactive subscription |
| Blocking SQL | Can be used | Avoid; use the reactive driver matching the backend |

The same `@Transactional` annotation applies in both models, but the **transaction manager and context propagation differ**. Do not infer that just because a method returns `Mono`, a `DataSourceTransactionManager` will automatically create an R2DBC transaction.

## 3. Why must the context follow the subscriber?

Reactive Streams consists of `Publisher`, `Subscriber`, and `Subscription`. `Publisher` merely describes work. `Subscriber` triggers the work and holds request/cancel signals. Reactor adds `Context` to store metadata tied to the **subscription**, not fixed to a worker thread.

Diagram:

```text
Service method creates Mono/Flux
           |
           |  no subscription yet
           v
  Transactional publisher
           |
           |  subscriber subscribes
           v
 TransactionalOperator/Interceptor
           |
           +-- obtain transaction from manager
           +-- bind context/resources to subscriber
           |
           v
    R2DBC query publisher 1
           |
           v
    R2DBC query publisher 2
           |
           +-- onComplete  --> commit
           +-- onError     --> rollback / apply rollback rules
           +-- cancel      --> rollback since Spring 5.3
           |
           v
  Release transaction resource
```

`Reactor Context` can propagate across operators and across thread switches as long as they remain in the same reactive subscription. For example, `publishOn(Schedulers.parallel())` does not inherently drop the context when using Reactor APIs properly.

Do not confuse `Context` with `ThreadLocal`. One thread can serve many subscriptions; a single subscription can run callbacks on multiple threads. Context values also depend on where `contextWrite` is placed and the direction of context propagation in the chain.

### 3.1. What does subscription-scoped mean?

```java
Mono<Void> operation = service.savePair("invoice-A");

// Creating the publisher does not perform DB inserts yet.
Mono<Void> sameOperation = operation;

// First subscription: runs transaction #1.
operation.subscribe();

// Second subscription: runs transaction #2.
sameOperation.subscribe();
```

This snippet illustrates the concept, not production style. Two separate `subscribe()` calls can produce two writes. If an operation has side effects, design for idempotency and avoid accidental resubscription.

In a WebFlux application, the controller usually **returns the publisher** to Spring so the framework subscribes along the HTTP lifecycle:

```java
@PostMapping("/payments")
public Mono<ResponseEntity<Void>> create(
        @RequestBody Mono<PaymentCommand> body) {

    return body.flatMap(paymentService::save)
            .thenReturn(ResponseEntity.accepted().build());
}
```

Do not call `paymentService.save(...).subscribe()` and return success immediately: the HTTP request will have no idea if the inner task failed or was cancelled.

### 3.2. Defer and lazy execution

`Mono.defer` is useful when you need to compute or read data at subscription time:

```java
Mono<Void> transactionFlow = Mono.defer(() ->
        repository.insertFirst()
                .then(repository.insertSecond()))
        .as(transactionalOperator::transactional);
```

`Mono.defer` creates child publishers per subscription. With repository APIs that are already lazy, you do not need to wrap everything in `defer`; use it when publisher creation logic depends on state at subscribe time.

Do not perform side effects outside the reactive publisher:

```java
// Wrong: runs an imperative call before subscription.
sendEmailNow();
return repository.save(entity).as(operator::transactional);
```

The email will be sent before the DB transaction executes and cannot be rolled back with the R2DBC transaction.

## 4. R2dbcTransactionManager binds connections via Context

`R2dbcTransactionManager` manages transactions for **one** `io.r2dbc.spi.ConnectionFactory`. When a transaction starts, the manager acquires a `Connection` from the factory, sets transaction state, and binds the connection into the subscriber Context. R2DBC operations in the same context should use that connection.

Spring Framework requires data access to integrate via:

- `DatabaseClient` or Spring Data R2DBC repositories/templates, which are transaction-aware.
- `ConnectionFactoryUtils.getConnection(factory)` if writing a low-level R2DBC client manually.
- `TransactionAwareConnectionFactoryProxy` when you must supply a compatible factory to an external consumer without built-in integration.

Do **not** directly call `connectionFactory.create()` inside a transactional method and expect it to be the transaction-bound connection. That can open a new connection outside the bound transaction. With custom APIs, use `ConnectionFactoryUtils` or an appropriate wrapper.

`ConnectionFactory` acts as a connection creator, not a single shared connection. `R2dbcTransactionManager` and `DatabaseClient` must reference compatible factories; if an application has multiple factories, clearly distinguish which manager and data access components use which.

### 4.1. Do not share one connection across multiple subscriptions

A transaction-bound R2DBC `Connection` is generally not designed to run multiple concurrent queries freely from multiple subscribers. Let Spring manage its lifecycle; do not store a transaction connection in a singleton field or manually stuff it into the Reactor context.

Use `then` or `concatMap` when SQL steps must happen sequentially. Avoid high-concurrency `flatMap` on operations sharing the same transaction if the driver does not support parallel queries on a single connection.

An R2DBC pool can grant multiple connections to independent transactions, but within a single transaction, SQL operations are coordinated to use the single bound resource.

## 5. @Transactional in reactive services

`@Transactional` is the declarative choice when a transaction is an attribute of a service method. The method must return a reactive type for Spring to take the reactive transaction path:

```java
@Service
class OrderService {

    private final OrderRepository orders;
    private final AuditRepository audit;

    OrderService(OrderRepository orders, AuditRepository audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public Mono<Void> place(Order order) {
        return orders.save(order)
                .flatMap(saved -> audit.record(saved.getId()))
                .then();
    }
}
```

This snippet requires the corresponding repositories/DTOs and imports. Both repositories must use the same transaction-capable reactive backend/resource. Spring's proxy/interceptor wraps the returned publisher; when the framework or caller subscribes, the transaction opens and data access operations share the same context.

**Must be invoked through the Spring-managed proxy.** Calling `this.place(...)` within the same class normally bypasses transaction advice in proxy mode. Call a method on another bean, refactor the service, or use `TransactionalOperator` for explicit boundaries.

### 5.1. @Transactional does not turn imperative code into reactive

An example unsuitable for a reactive manager:

```java
@Transactional
public void writeNow() {
    jdbcTemplate.update("UPDATE account SET balance = ...");
}
```

Methods returning `void` with blocking JDBC require `PlatformTransactionManager`, not `ReactiveTransactionManager`. Conversely, a method returning `Mono<Void>` operating on R2DBC must select the reactive manager.

If an application has both JDBC and R2DBC, specify the bean via `@Transactional("r2dbcTransactionManager")` or configure an appropriate qualifier; do not let the same manager name be picked by the wrong model.

### 5.2. Annotation rollback rules

`@Transactional` defaults to `REQUIRED` propagation, default isolation, and rolling back on `RuntimeException` or `Error`; checked exceptions typically do not trigger rollback unless configured via `rollbackFor` or an equivalent rule.

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public Mono<Void> performReactiveTask() {
    return executeSteps();
}
```

This snippet assumes `BusinessCheckedException` and `executeSteps` exist. With programmatic `TransactionalOperator`, an error signal in the transactional publisher triggers rollback; with declarative annotations, the annotation's rollback rules must be considered per exception type.

Do not convert an error into a successful completion with `onErrorResume` **inside** the transaction and expect the transaction to roll back automatically. If the error is handled as success before the transaction boundary sees the error, Spring may commit. To roll back even if you return a fallback afterwards, place the fallback **after** the boundary or use `ReactiveTransaction#setRollbackOnly()` in a callback.

## 6. TransactionalOperator: explicit boundaries

`TransactionalOperator` is the programmatic counterpart to `TransactionTemplate` in imperative code. It can be created from a manager:

```java
@Bean
TransactionalOperator transactionalOperator(
        ReactiveTransactionManager manager) {
    return TransactionalOperator.create(manager);
}
```

Spring Boot can auto-provide a `TransactionalOperator` bean when a suitable `ReactiveTransactionManager` exists in the context; if one is already present, do not declare a duplicate. The bean example above is for explicit configuration or running outside Boot.

Two usage styles:

**Operator-style** — wraps an existing publisher:

```java
Mono<Void> workflow = debit(accountA, 100)
        .then(credit(accountB, 100))
        .as(transactionalOperator::transactional);
```

**Callback-style** — transaction wraps only what is created inside the callback:

```java
Flux<Receipt> results = transactionalOperator.execute(status ->
        reserveStock()
                .thenMany(loadReceipts()));
```

Inside the callback, you can mark rollback-only:

```java
Mono<Void> workflow = transactionalOperator
        .execute(status ->
                validateAndWrite()
                        .doOnNext(result -> {
                            if (!result.accepted()) {
                                status.setRollbackOnly();
                            }
                        }))
        .then();
```

These snippets assume the domain methods exist. With `execute(...)`, the return type is `Flux<T>`; use `.then()` if the final logic does not need to emit a value.

### 6.1. Where the operator is placed determines scope

Both steps inside the transaction:

```java
return firstWrite()
        .then(secondWrite())
        .as(transactionalOperator::transactional);
```

Only `firstWrite` inside the transaction; `secondWrite` is outside:

```java
return firstWrite()
        .as(transactionalOperator::transactional)
        .then(secondWrite());
```

The difference is the placement of `as(...)`. Place the transactional boundary around the entire unit of work that must be atomic, not around a single repository call followed by out-of-transaction steps.

### 6.2. TransactionalOperator is not a single fixed connection

`TransactionalOperator` can be a singleton bean shared across many requests; it is a **boundary configuration**, not an open connection. Each subscription creates an appropriate transaction context, receives resources from the manager, and cleans up on completion.

Do not create a new `R2dbcTransactionManager` per request. Create the manager/operator once in configuration and reuse it.

## 7. Complete, Error, and Cancel signals

A transaction's lifecycle depends on publisher signals:

| Signal | Typical behavior | Meaning |
|---|---|---|
| `onComplete` after steps succeed | Commit | Unit of work completed |
| `onError` | Rollback per manager policy/rollback rules | Error occurred in transaction |
| `cancel` | Rollback in Spring 5.3+ | Subscriber stopped receiving, transaction incomplete |
| No subscription | Does not begin | Publisher was only declared |
| Second subscription | A new execution/transaction | Cold publisher runs again |

In particular, **cancel is not onError**. It can come from the client closing the connection, a user leaving the page, a downstream timeout, or an operator no longer wanting items.

Spring Framework explicitly states: since 5.3, a cancel signal triggers rollback for reactive transactions. This means operators such as `take(n)`, `next()`, and `timeout(...)` require careful thought when placed **after a transactional publisher**.

### 7.1. next() and take() can cause a transaction to roll back

Example with multiple results:

```java
Flux<Row> rows = fetchRowsAndUpdateAudit()
        .as(transactionalOperator::transactional);

// next() takes the first item and cancels the rest.
Mono<Row> first = rows.next();
```

If the source has not completed yet, `next()` cancels upstream. The transaction receives cancel and rolls back, even though the caller already saw one `Row`. Do not treat an emitted `onNext` as proof the transaction committed.

If you need to complete the entire workflow and only return the first item, redesign so the query/transaction completes before emitting the final result; consider `collectList` for a small finite set or a query returning exactly one value. Never aggregate large/infinite streams.

### 7.2. onNext can emit before commit

A `Flux<T>` inside a transaction can emit items downstream while the transaction is still open. If the final commit fails, the caller may have already observed partial data.

When you need to guarantee the caller only receives “success” after commit, use a `Mono<Void>`/`Mono<Receipt>` computed from the completed unit of work, or buffer finite results inside the boundary and emit the aggregate only after commit. Watch the placement of `.as(transactionalOperator::transactional)` and downstream operators.

Example:

```java
Mono<List<Item>> result = loadAndUpdate()
        .collectList()
        .as(transactionalOperator::transactional);
```

`Mono<List<Item>>` only emits the list after the source `Flux` completes, though edge cases can still occur during transaction commit at operator boundaries; check `TransactionalOperator` semantics and test real commit failures. Do not use this example to promise exactly-once or distributed delivery.

## 8. Inspecting the transaction Context at runtime

For diagnostics inside a reactive chain, Spring provides:

```java
Mono<Boolean> active = TransactionSynchronizationManager
        .forCurrentTransaction()
        .map(TransactionSynchronizationManager::isActualTransactionActive);
```

`forCurrentTransaction()` returns the manager attached to the current transaction context or errors if no context exists. Call it **inside** a managed pipeline; do not call it outside and stash it in a `ThreadLocal` for later use.

Try wrapping it:

```java
Mono<Boolean> active = TransactionSynchronizationManager
        .forCurrentTransaction()
        .map(TransactionSynchronizationManager::isActualTransactionActive)
        .as(transactionalOperator::transactional);
```

Upon subscription, the callback runs inside the transaction context and normally sees `true`. This value indicates a transaction is active; it does not prove two queries share the same connection if you manually open raw connections bypassing helpers.

Use this context API for specialized diagnostics/integrations. Business logic should let Spring Data R2DBC enlist resources via `DatabaseClient`, rather than touching the transaction context directly in every repository method.

## 9. When switching threads, is the context lost?

Reactor operators such as `publishOn` and `subscribeOn` can switch execution threads while still propagating the Reactor Context of the same subscription:

```java
Mono<Void> flow = repository.writeOne()
        .publishOn(Schedulers.parallel())
        .then(repository.writeTwo())
        .as(transactionalOperator::transactional);
```

This configuration remains **one reactive pipeline**. However, you should not move DB queries onto `parallel()` just to “speed them up” when they share a single transaction-bound connection. The driver may not support concurrent queries on the same connection.

Operations that break the subscription or drop the context:

- Manually calling `subscribe()` on another publisher.
- Spawning callbacks outside the Reactor pipeline that execute independent DB calls.
- Switching to `CompletableFuture`/executors without an explicit context-bridging mechanism.
- Calling a repository in a listener or scheduled job and assuming the HTTP request's transaction is still present.

`Reactor Context` differs from logging MDC `ThreadLocal`. To use MDC/tracing across a reactive chain, configure proper context propagation; do not assume MDC preserves transaction resources on its own.

## 10. Transaction boundaries with retries, timeouts, and fallbacks

### 10.1. Retries can create a new transaction per attempt

```java
Mono<Void> attempt = writeSteps()
        .as(transactionalOperator::transactional);

return attempt.retryWhen(
        Retry.backoff(2, Duration.ofMillis(100)));
```

If the first execution emits an error, the transaction rolls back, and then `retryWhen` resubscribes to the entire transactional publisher to start a new attempt. Only retry appropriate transient errors; side effects outside the database may already have happened.

Do not carelessly place retries inside a transaction and expect the DB transaction to remain valid after a SQL error. For example, PostgreSQL can mark a transaction aborted after a statement failure and require a rollback before running further queries.

### 10.2. Timeouts can trigger cancel and rollback

```java
Mono<Void> result = writeSteps()
        .as(transactionalOperator::transactional)
        .timeout(Duration.ofSeconds(3));
```

When downstream times out, `timeout` can cancel the source, causing the transaction to roll back. A timeout does not guarantee an external HTTP call or side effect that already occurred is undone. If you need separate DB statement or lock timeouts, configure them at the driver/database level as supported.

### 10.3. Fallbacks behave differently before vs after the boundary

Catching an error **inside** and returning success:

```java
Mono<Void> result = writeSteps()
        .onErrorResume(error -> Mono.empty())
        .as(transactionalOperator::transactional);
```

The transaction sees a successful completion and may commit writes prior to the error.

Catching an error **after** the boundary has rolled back:

```java
Mono<Void> result = writeSteps()
        .as(transactionalOperator::transactional)
        .onErrorResume(error -> fallbackAfterRollback(error));
```

The fallback runs after the previous transaction has ended; if the fallback writes to the database, it needs its own transaction when business logic requires one. The two snippets are not equivalent in atomicity.

## 11. Transaction settings and propagation

Common parameters:

- `propagation`: REQUIRED, REQUIRES_NEW, SUPPORTS, MANDATORY, NOT_SUPPORTED...
- `isolation`: READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE... depending on backend.
- `timeout`: transaction time budget per manager/driver.
- `readOnly`: read-only hint or policy; enforcement depends on DB/driver.
- `rollbackFor` / `noRollbackFor`: rollback rules in declarative transactions.

Annotation example:

```java
@Transactional(
        transactionManager = "transactionManager",
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 5)
public Mono<Void> applyChanges() {
    return updateA().then(updateB());
}
```

Programmatic example:

```java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
definition.setTimeout(5);

TransactionalOperator operator =
        TransactionalOperator.create(manager, definition);
```

These snippets require the manager dependency and illustrative methods. Verify which isolation levels and propagation modes your manager/driver supports. **REQUIRES_NEW** requires appropriate independent resources and enough pool connections; **NESTED** or savepoints cannot be assumed supported on every reactive backend.

`readOnly=true` is not an authorization mechanism: applications must not use it as a substitute for SQL access permissions. Higher isolation levels can increase locking and contention, requiring throughput/latency measurement.

## 12. Ecosystem integrations: R2DBC, MongoDB, and other systems

### 12.1. Spring Data R2DBC

R2DBC is the reactive API for relational databases. `R2dbcTransactionManager` paired with `DatabaseClient`, `R2dbcEntityTemplate`, or repositories ensures the same subscription uses the right connection.

In Spring Boot, the `spring-boot-starter-data-r2dbc` dependency, a driver like `r2dbc-postgresql` or `r2dbc-h2`, and `spring.r2dbc.*` are usually enough for Boot to auto-configure `ConnectionFactory` and the manager (when conditions match).

The R2DBC connection pool has its own lifecycle. Do not keep a transaction open while waiting on slow HTTP calls or heavy CPU work. While a transaction is open, a connection is typically held, reducing pool capacity.

### 12.2. Reactive MongoDB

`ReactiveMongoTransactionManager` works with a MongoDB `ClientSession` in the reactive context. The MongoDB deployment must support transactions (e.g., a replica set/sharded cluster of an appropriate version). You cannot simply add an annotation to turn a non-transactional standalone MongoDB into an ACID transactional system.

R2DBC transactions and MongoDB transactions are two independent resources. If a workflow writes to both, you need patterns like Saga/Outbox/compensation; a single `@Transactional` on the R2DBC manager does not create a distributed two-phase commit across MongoDB too.

### 12.3. WebClient, Kafka, and message brokers

HTTP calls, Kafka publishes, or emails are not part of the same R2DBC database transaction. If the DB commit fails after sending a Kafka message, the message is not automatically recalled. If the DB commit succeeds but sending the message fails, data and events can diverge.

**Transactional Outbox** is often the appropriate pattern:

1. Within one DB transaction, write the business entity **and** an outbox row.
2. Commit both together.
3. A separate publisher/relay reads the outbox and sends the event.
4. Mark published with retries/idempotency and monitoring.

Do not write a `doOnSuccess` callback to send an event and consider that send protected by DB rollback. Choose clear boundaries and accept at-least-once semantics with duplicate handling at the consumer.

## 13. Complete example: Java 17 + Spring Boot 3.5.16 + R2DBC H2

The example uses in-memory H2 via the R2DBC driver, with Spring Boot auto-configuring `ConnectionFactory` and `ReactiveTransactionManager`. One service demonstrates two styles:

- `savePair(...)` and `saveThenFail(...)` use `TransactionalOperator`.
- `saveWithAnnotation(...)` uses `@Transactional`.

Integration tests verify that writes only execute upon subscription, commits persist data, errors roll back, each subscription runs anew, and declarative transactions work. No HTTP server is needed.

### 13.1. Project structure

```text
reactive-tx-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ReactiveTxApplication.java
    │   ├── java/demo/LedgerService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/demo/LedgerServiceTest.java
```

### 13.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
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
```

`spring-boot-starter-data-r2dbc` provides R2DBC integration; `spring-boot-starter-aop` ensures proxy infrastructure for the `@Transactional` example. `r2dbc-h2` is a demo driver, not a default choice for production. The Boot BOM manages compatible dependency versions.

### 13.3. application.properties

```properties
spring.application.name=reactive-tx-demo
spring.main.web-application-type=none
spring.r2dbc.url=r2dbc:h2:mem:///txdemo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.username=sa
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
```

H2 `DB_CLOSE_DELAY=-1` keeps the in-memory database alive after the last connection closes while the JVM is still running. It ensures `schema.sql` is initialized before tests use other connections. This configuration is only for demos/tests; do not use in-memory H2 as a persistent data store.

### 13.4. schema.sql

```sql
CREATE TABLE ledger_entries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label VARCHAR(200) NOT NULL
);
```

Spring Boot executes the script during SQL initialization according to `spring.sql.init.*`. In production, manage schemas with a migration tool and avoid running test scripts against real databases.

### 13.5. ReactiveTxApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxApplication.class, args);
    }
}
```

### 13.6. LedgerService.java

```java
package demo;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionSynchronizationManager;
import org.springframework.transaction.reactive.TransactionalOperator;

import reactor.core.publisher.Mono;

@Service
public class LedgerService {

    private final DatabaseClient db;
    private final TransactionalOperator operator;

    public LedgerService(
            DatabaseClient db,
            ReactiveTransactionManager manager) {

        this.db = db;
        this.operator = TransactionalOperator.create(manager);
    }

    private Mono<Void> insert(String label) {
        return db.sql(
                "INSERT INTO ledger_entries(label) VALUES (:label)")
                .bind("label", label)
                .then();
    }

    // Success -> commit both inserts.
    public Mono<Void> savePair(String key) {
        return insert(key + "-A")
                .then(insert(key + "-B"))
                .as(operator::transactional);
    }

    // Error -> roll back the first insert.
    public Mono<Void> saveThenFail(String key) {
        return insert(key + "-A")
                .then(Mono.<Void>error(
                        new IllegalStateException("planned failure")))
                .as(operator::transactional);
    }

    // Spring AOP applies the reactive transaction advice.
    @Transactional
    public Mono<Void> saveWithAnnotation(String key) {
        return insert(key + "-A")
                .then(insert(key + "-B"));
    }

    // Read-only diagnostic query outside transactional boundary.
    public Mono<Long> count(String label) {
        return db.sql(
                "SELECT COUNT(*) AS total "
                + "FROM ledger_entries WHERE label = :label")
                .bind("label", label)
                .map((row, metadata) ->
                        ((Number) row.get("total")).longValue())
                .one();
    }

    // Context is inspected inside a new reactive transaction.
    public Mono<Boolean> transactionIsActive() {
        return TransactionSynchronizationManager
                .forCurrentTransaction()
                .map(TransactionSynchronizationManager::
                        isActualTransactionActive)
                .as(operator::transactional);
    }
}
```

Explanation of key points:

1. The constructor receives a `ReactiveTransactionManager` auto-configured by Boot; initialize the operator once for reuse.
2. `insert` returns a lazy `Mono<Void>` from `DatabaseClient`, not executing SQL immediately when called.
3. `savePair` places both inserts into the same transactional publisher using `then` and `as`.
4. `saveThenFail` emits `IllegalStateException` after the first insert, causing the entire transaction to roll back.
5. `saveWithAnnotation` returns a publisher from a Spring-managed service bean; AOP handles the transaction upon subscription.
6. `count` does not participate in the preceding write transaction, because the test subscribes to it **after** the transactional publisher completes.
7. `transactionIsActive` reads the transaction context directly inside the boundary and must return `true` when running properly.

### 13.7. LedgerServiceTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class LedgerServiceTest {

    @Autowired
    LedgerService service;

    @Test
    void commitsAllWritesOnNormalCompletion() {
        StepVerifier.create(service.savePair("success"))
                .verifyComplete();

        StepVerifier.create(service.count("success-A"))
                .expectNext(1L)
                .verifyComplete();

        StepVerifier.create(service.count("success-B"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void rollsBackWhenPublisherFails() {
        StepVerifier.create(service.saveThenFail("failure"))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && error.getMessage().equals("planned failure"))
                .verify();

        StepVerifier.create(service.count("failure-A"))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void doesNotOpenTransactionUntilSubscription() {
        Mono<Void> notYetSubscribed =
                service.savePair("deferred");

        StepVerifier.create(service.count("deferred-A"))
                .expectNext(0L)
                .verifyComplete();

        StepVerifier.create(notYetSubscribed)
                .verifyComplete();

        StepVerifier.create(service.count("deferred-A"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void everySubscriptionRunsAgain() {
        Mono<Void> cold = service.savePair("repeated");

        StepVerifier.create(cold).verifyComplete();
        StepVerifier.create(cold).verifyComplete();

        StepVerifier.create(service.count("repeated-A"))
                .expectNext(2L)
                .verifyComplete();

        StepVerifier.create(service.count("repeated-B"))
                .expectNext(2L)
                .verifyComplete();
    }

    @Test
    void transactionalAnnotationUsesReactiveManager() {
        StepVerifier.create(service.saveWithAnnotation("annotated"))
                .verifyComplete();

        StepVerifier.create(service.count("annotated-A"))
                .expectNext(1L)
                .verifyComplete();

        StepVerifier.create(service.count("annotated-B"))
                .expectNext(1L)
                .verifyComplete();
    }

    @Test
    void transactionContextExistsDuringExecution() {
        StepVerifier.create(service.transactionIsActive())
                .expectNext(true)
                .verifyComplete();
    }
}
```

Run from the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result based on test logic:** all six `@Test` methods complete successfully with no assertion failures; `mvn` exits with code `0`. The tests verify DB results through real queries rather than merely mocking methods. Spring Boot/H2 log lines may vary across environments; do not assume fixed stdout beyond successful test results.

You can start the application with:

```bash
mvn spring-boot:run
```

The demo application does not start an HTTP server due to `web-application-type=none`, so there are no REST endpoints to call with `curl`. For this project, `mvn test` is the clearest way to demonstrate transaction correctness.

**Limitations of the example:** it uses a single in-memory database and a single transaction manager. It does not demonstrate distributed transactions, rolling back HTTP/Kafka side effects, support for every isolation/propagation mode across other drivers, or behavior under production load.

## 14. Extension exercises after the example

You can add the following tests for deeper understanding:

### 14.1. Test error after two inserts

Modify `saveThenFail` to perform two inserts and then emit `Mono.error`. Neither row should appear after rollback. This proves the entire unit of work shares one boundary, not just the first statement.

### 14.2. Test placing the operator in the wrong position

Create a method:

```java
public Mono<Void> partialTransaction(String key) {
    return insert(key + "-A")
            .as(operator::transactional)
            .then(insert(key + "-B"));
}
```

If step B emits an error, step A has already committed and will not automatically roll back. Place the operator outside both steps to achieve atomicity. Do not add this method to production logic; use a test to illustrate scope.

### 14.3. Test cancellation after the first item

Create a `Flux` inside a transaction with at least two items, then apply `next()` downstream. Observe that cancellation can lead to rollback. Use a test with a deadline and a verification query rather than relying solely on `doOnCancel` logs. Separate the moment an item is emitted from the moment the transaction commits.

### 14.4. Test switching threads

Insert `publishOn(Schedulers.parallel())` between two DB operations in a sequential pipeline. The transaction should still propagate via Reactor Context. Do not use high-concurrency `flatMap` on the same transaction connection.

### 14.5. Test outer retry

Wrap a transactional publisher that may fail transiently with `retryWhen` **outside** the boundary. Each attempt should be a new subscription with a new transaction. Check write counts, lock timeouts, and idempotency rather than only checking the final response.

## 15. Common mistakes

1. **Thinking calling a method returning Mono has already committed.** A reactive transaction only begins upon subscription.
2. **Confusing ThreadLocal with Reactor Context.** Reactive transaction context travels with the subscriber, not pinned to a thread.
3. **Calling subscribe manually in a service.** Creates a subscription outside the boundary and strips the caller of error/cancel control.
4. **Using blocking JDBC under ReactiveTransactionManager.** JDBC does not automatically use the transaction-bound R2DBC connection.
5. **Using PlatformTransactionManager for a reactive service.** Pick the right manager for the backend and return type.
6. **Opening raw connections directly with ConnectionFactory.create().** Can bypass context-bound resources; use DatabaseClient or ConnectionFactoryUtils.
7. **Re-subscribing to a cold publisher with side effects.** Can run two transactions and write twice; idempotency is required.
8. **Placing TransactionalOperator before the final DB step.** The final step sits outside the transaction and is no longer atomic.
9. **Catching errors with onErrorResume inside the transaction.** The transaction may see completion and commit data prior to the error.
10. **Assuming onError always rolls back identically across all annotations.** `@Transactional` has rollback rules; checked exceptions behave differently by default from RuntimeException.
11. **Assuming onNext means commit.** A Flux can emit items before the transaction finishes.
12. **Using next/take downstream without considering cancellation.** Spring reactive transactions roll back on cancel.
13. **Thinking timeout always rolls back every side effect.** DB cancel/rollback does not undo sent emails, Kafka messages, or HTTP requests.
14. **Thinking publishOn loses the transaction.** Reactor Context is preserved within the same subscription; the real issue is splitting the pipeline or using blocking calls.
15. **Running concurrent DB queries on a single transaction-bound connection.** The driver may forbid it; execute sequentially where appropriate.
16. **Calling a @Transactional method via `this` in proxy mode.** Self-invocation normally bypasses AOP advice.
17. **Defining multiple transaction managers without qualifiers.** May select the wrong resource or fail with ambiguity.
18. **Thinking @Transactional creates a distributed transaction.** An R2DBC manager only protects the resources it manages.
19. **Opening a transaction and then calling a slow HTTP API.** Holds connections and locks too long, increasing pool contention.
20. **Placing retries inside a transaction after a SQL error.** The transaction may already be marked aborted by the DB; roll back and retry in a new transaction.
21. **Assuming readOnly is a security permission.** It is a flag/policy with varying support, not a replacement for authorization.
22. **Assuming every driver supports NESTED/REQUIRES_NEW identically.** Check savepoints, connections, and propagation support.
23. **Storing ReactiveTransaction in a singleton field.** Transaction status/resources are per-execution and must not be shared across requests.
24. **Reading the transaction context outside the boundary and guessing an active transaction exists.** Use `forCurrentTransaction` inside the managed pipeline.
25. **Not testing rollback with real data.** A mocked unit test does not prove the DB server rolls back.
26. **Mixing @Transactional and TransactionalOperator unintentionally.** Can create confusing nested/participating boundaries; pick one business owner.
27. **Missing timeouts/cleanup for connections.** Transactions can occupy the pool for too long or hang if external I/O has no deadline.
28. **Not checking schema init or migrations.** In-memory H2 differs from PostgreSQL/MySQL in isolation/DDL/SQL syntax.
29. **Confusing reactive transactions with exactly-once delivery.** A DB commit does not guarantee external events are delivered once.
30. **Testing only the happy path.** You must test rollback, cancellation, error handling, retries, timeouts, and context boundaries.

## 16. Production checklist

Before deploying reactive transactions, check:

- Is data access using R2DBC, reactive MongoDB, or JDBC/JPA?
- Does `ReactiveTransactionManager` match the right resource and have only one matching candidate?
- Do `@Transactional` methods return `Mono`/`Flux` and get called via a Spring proxy?
- Do all data access steps share the same Reactor Context and the same transaction boundary?
- Are there any manual `subscribe()`, out-of-pipeline callbacks, or `block()` calls in reactive services?
- Are any connections created manually outside `ConnectionFactoryUtils` or Spring Data integration?
- Is the operator boundary placed around **all** writes that must be atomic?
- When handling exceptions, does the boundary see the error to roll back or only see success?
- With `Flux`, can callers use `take`/`next`/timeouts that cancel before commit?
- Is there resubscription due to retry, repeat, caching, HTTP retries, or duplicate messages?
- Do retries run in a new transaction and target only transient/idempotent errors?
- Does the backend support the declared isolation/timeout/propagation settings?
- Are any transactions held open too long because of external HTTP/Kafka calls or heavy CPU processing?
- Does the R2DBC pool have enough capacity for concurrent transactions and reasonable lock times?
- Does communication between DB and Kafka/HTTP need a transactional outbox or Saga?
- Are there metrics for active transactions, connection pool, pending acquires, locks, and timeouts?
- Are there real-DB tests for commit, rollback, cancellation, concurrency, and startup/shutdown?
- Are transaction manager qualifiers tested if the app uses multiple backends?
- Are payloads/query results bounded, avoiding infinite Flux transactions?

**Key takeaway:** Reactive transactions share the **same atomicity goal** as imperative transactions, but differ in lifecycle binding: transactions start on **subscription**, state/resources travel via **Reactor Context**, and each resubscription can open a new transaction. `R2dbcTransactionManager` manages connections for one `ConnectionFactory`; `@Transactional` and `TransactionalOperator` define boundaries so Spring R2DBC queries sharing the same context participate together. Completion normally commits, errors roll back per policy, and cancellation triggers rollback. Do not detach subscriptions, do not substitute blocking JDBC for R2DBC, and do not treat a single-database transaction as a distributed transaction.

## References

- Spring Framework — [Declarative Transactions: Reactive return types and Reactor context](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Spring Framework — [Programmatic Transaction Management: TransactionalOperator, cancellation, transaction settings](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html).
- Spring Framework — [Using @Transactional and rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Framework — [Data Access with R2DBC: ConnectionFactoryUtils and R2dbcTransactionManager](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html).
- Spring Framework — [TransactionalOperator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionalOperator.html).
- Spring Framework — [TransactionSynchronizationManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronizationManager.html).
- Spring Boot 3.5 — [R2DBC database configuration](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html).
- Spring Boot 3.5 — [SQL script initialization with R2DBC](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html).
- Spring Boot 3.5.16 — [TransactionAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/transaction/TransactionAutoConfiguration.html).
- R2DBC H2 — [Driver connection URL and options](https://github.com/r2dbc/r2dbc-h2).
- Project Reactor — [Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html).
