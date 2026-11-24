# Cancellation or Errors in Reactive Transactions and Connection Release Responsibility

**Module:** Spring Framework – reactive  
**Parent topic:** Ecosystem integrations  
**Lesson:** Cancellation or errors in transactions and connection release responsibility

## Learning objectives

After this lesson, you will be able to:

1. Distinguish the three Reactive Streams termination signals `onComplete`, `onError`, and `cancel`; understand why cancel is not an ordinary exception.
2. Explain that reactive transactions bind to **Reactor Context and subscription**, rather than ThreadLocal as in imperative JDBC transactions.
3. Describe the connection lifecycle: acquire → begin transaction → execute statements → commit/rollback → reset/close or return to pool.
4. Use `R2dbcTransactionManager`, `TransactionalOperator`, or `@Transactional` so Spring takes responsibility for completing the transaction.
5. Understand the Spring Framework 5.3+ rule: **cancellation in a reactive transaction triggers rollback**, not commit.
6. Recognize failures caused by `take`, `next`, `timeout`, client disconnects, or downstream subscription cancellation.
7. Distinguish transaction rollback from connection release; do not assume rolling back already closes/returns the connection.
8. Use `Mono.usingWhen`/`Flux.usingWhen` for manually managed reactive resources, avoiding `doFinally` to fire-and-forget async cleanup.
9. Test commit, rollback on error, rollback on cancel, and returning connections to the pool with Spring Boot 3.3.5, R2DBC H2, and Reactor Test.
10. Set timeouts, pool limits, logs, and metrics to detect connection leaks in production.

## 1. Context: a transaction in progress

Consider a service saving two records:

```text
HTTP/WebSocket/RSocket client
          |
          v
Reactive service (Mono/Flux)
          |
          v
TransactionalOperator or @Transactional
          |
          v
R2dbcTransactionManager
          |
          v
ConnectionFactory -> R2DBC Connection -> Database
```

A transaction is only correct when it has a clear completion boundary. If both write statements succeed and the publisher completes normally, it commits; if the work fails, it rolls back; if the subscriber cancels midway, the transaction must also be terminated and the resource returned.

The tricky part is that Reactive Streams allows the caller **not to consume all data**. A browser closing the connection, a client timeout, or the `take(1)` operator can all cause the subscription to be cancelled. That is not necessarily a database failure; it is a signal that downstream no longer needs the remaining upstream data.

If cancel is ignored, the connection may stay in an open transaction state, occupying a pool slot. When many such requests happen, the entire service can run out of connections even while the database itself is healthy.

## 2. Three ways a publisher ends

A subscription can encounter:

| Outcome | Meaning | Observable in Reactor via | Expected impact on transaction |
| --- | --- | --- | --- |
| **Complete** | The Publisher finished successfully (with or without data) | `doOnComplete` on Flux, `doOnSuccess` on Mono, `doFinally(ON_COMPLETE)` | Commits if the transaction was not marked rollback-only. |
| **Error** | The Publisher terminated with a terminal `onError` signal | `doOnError`, `doFinally(ON_ERROR)` | Rolls back per transaction policy; with `TransactionalOperator`, an error from the publisher triggers rollback. |
| **Cancel** | The Subscriber proactively stops wanting more data | `doOnCancel`, `doFinally(CANCEL)` | Spring reactive transactions since 5.3 roll back on cancel. |

Note: `cancel` is **not** an `onError` and carries no failure cause. Reactor cannot tell whether cancellation came from a user leaving a page, a `timeout`, `take(1)`, `next()`, or downstream stopping consumption. Therefore, the transaction infrastructure cannot treat cancel as success.

Example observing signals:

```java
Flux<Integer> source = Flux.range(1, 10)
        .doOnCancel(() -> System.out.println("cancel observed"))
        .doFinally(signal ->
                System.out.println("finally=" + signal));

source.take(2).collectList();
```

This is only **declaring the pipeline**; there is no subscription yet, so nothing is printed. When subscribing to the publisher produced by `take(2)`, downstream collects two elements and cancels upstream. `doOnCancel` and `doFinally` on the **source** will record cancel. If `doFinally` is placed **after** `take(2)`, it may observe COMPLETE because the pipeline was bounded into finite work. Operator placement is therefore crucial when reading logs.

`Mono.empty()` completes normally and usually leads to commit; “no item” does **not automatically** mean “must roll back”.

## 3. Reactive transactions differ from imperative transactions

### 3.1. Transaction context lives in Reactor Context

With standard JDBC, a transaction is bound to ThreadLocal and the running thread. With Spring reactive transactions, the infrastructure uses Reactor Context bound to the subscriber and subscription.

```text
Subscriber
   |
   +--- Reactor Context: TransactionContext
             |
             +--- resource holder: R2DBC Connection
             |
             +--- TransactionSynchronization
   |
   +--- db.queryA() ----+
   |                    | same transaction context
   +--- db.queryB() ----+
```

R2DBC operations executed through Spring `DatabaseClient` or Spring Data R2DBC can join the connection bound in the transaction context. Two methods do not need to run on the same Java Thread as long as the pipeline preserves the Reactor Context in the framework-supported way.

Notes:

- Reactor's `publishOn` and `subscribeOn` do not automatically lose the Reactor Context when used properly. The real issue is usually **splitting the pipeline into a separate subscription**, calling `subscribe()` manually inside a service, or leaving the reactive context.
- An application's own `ThreadLocal` cannot replace `Reactor Context` for reactive transactions.
- A reactive `@Transactional` method must return a `Publisher` or compatible reactive type so the interceptor can wrap the subscription. A method returning `void` or calling `subscribe()` internally is not a valid reactive transaction boundary.
- Proxy-based `@Transactional` does not apply when one method in the same object calls a transactional method via `this`, bypassing the proxy.

### 3.2. Who holds the connection?

`ConnectionFactory` creates R2DBC `Connection`s. `R2dbcTransactionManager` acquires a connection, begins a transaction, attaches the connection to the transaction context, and manages completion.

`DatabaseClient`/Spring Data R2DBC operate through a transaction-aware connection acquisition mechanism. Therefore, within a valid pipeline, database calls belonging to the same transaction can reuse the transaction-bound connection instead of each statement opening an independent connection.

`ConnectionFactoryUtils.getConnection` and `releaseConnection` are APIs supporting transaction-bound resources for low-level integration code. Do not call `ConnectionFactory.create()` directly inside a Spring transaction and assume the new connection joined the current transaction: it may be a **different connection** outside Spring's commit/rollback boundary.

## 4. Lifecycle of a transaction and connection

Expected path:

```text
subscribe
  |
  v
Acquire R2DBC Connection from pool/driver
  |
  v
Begin transaction
  |
  v
Reactive SQL statements
  |
  +---- onComplete ---> COMMIT --------+
  |                                    |
  +---- onError ------> ROLLBACK ------+
  |                                    |
  +---- cancel -------> ROLLBACK ------+
                                       |
                                       v
                             Cleanup transaction state
                                       |
                                       v
                         Release connection / return to pool
```

**Commit/rollback** decides the fate of data changes in the transaction. **Release/close** decides the fate of the connection resource. They are two distinct operations; to guarantee resources are not held forever, both must happen along the appropriate lifecycle.

In an R2DBC pool, calling `Connection.close()` on the connection wrapper usually **returns the connection to the pool** for reuse; it does not necessarily close the physical socket. For an unpooled connection, close usually closes the driver resource. Do not equate “close” with “tear down TCP”.

`Connection.close()` in R2DBC returns a `Publisher<Void>`; merely creating the publisher without subscribing/composing will not execute cleanup reactively. Spring's transaction manager already handles this lifecycle for Spring-managed connections. Application code should not manually close a connection owned by the transaction manager.

### 4.1. Must still release after rollback

When a transaction fails:

1. Detect the terminal error or cancellation.
2. Request rollback.
3. Unbind the resource from the transaction context.
4. Reset any state needed so the connection can be reused.
5. Release the connection to the pool or close the driver connection.

In real operations, rollback or cleanup itself can also fail if the connection dropped or the database is unresponsive. Do not promise every connection will always be cleanly reused after every network failure; you need metrics, timeouts, and pool checks to detect cleanup failures.

### 4.2. Responsibilities at each layer

| Layer | Responsibility |
| --- | --- |
| Caller / HTTP handler | Subscribe/return publisher with proper lifecycle; set timeouts, avoid swallowing errors unintentionally, cancel when no longer needed. |
| Service | Define business boundaries; do not manually subscribe or detach database calls from the transaction; do not block the event loop. |
| Spring transaction manager | Begin, commit, rollback, transaction context, and cleanup of the transaction-bound connection. |
| R2DBC driver | Execute statements, rollback/commit, and close per SPI. |
| Connection pool | Issue bounded connections, accept released connections, validate/reset/evict broken connections per configuration. |
| Low-level code author | If acquiring connections manually, must compose cleanup for complete, error, and cancel. |
| Operations / observability | Monitor acquired/idle/pending, slow queries, timeouts, rollback failures, leaks, and shutdown. |

## 5. Spring TransactionalOperator: the safe default approach

`TransactionalOperator` is the operator for framing a `Mono` or `Flux` inside a reactive transaction. It is the recommended choice for programmatic transaction management.

```java
Mono<Void> operation =
        insertFirst()
                .then(insertSecond())
                .as(transactionalOperator::transactional);
```

The transaction starts on subscription, statements run in order, and when the publisher completes it commits. If any statement emits an error, the operator enters rollback. If the subscriber cancels the transactional publisher, the operator executes rollback per Spring Framework 5.3+ semantics.

There are two styles:

**Operator-style:**

```java
return repo.debit(accountId, amount)
        .then(repo.credit(otherId, amount))
        .as(transactionalOperator::transactional);
```

**Callback-style:**

```java
return transactionalOperator.execute(status ->
        repo.debit(accountId, amount)
                .then(repo.credit(otherId, amount)))
        .then();
```

`execute` can receive `ReactiveTransaction status` and call `status.setRollbackOnly()` if business logic decides not to commit without emitting an error. Avoid building transactions by calling individual methods on `ReactiveTransactionManager` manually unless necessary, as you will have to handle far more error paths, rollback failures, and cancellations yourself.

### 5.1. Configuring TransactionalOperator

```java
@Configuration
class TxConfig {
    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

For R2DBC, Boot normally configures `R2dbcTransactionManager` when `ConnectionFactory` and the matching dependencies are present. If multiple transaction managers exist, specify the right manager so you do not accidentally use an imperative transaction manager.

### 5.2. @Transactional for reactive services

The annotation can also be used:

```java
@Service
class PaymentService {
    private final PaymentRepository repository;

    PaymentService(PaymentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Void> transfer(long from, long to, long amount) {
        return repository.subtract(from, amount)
                .then(repository.add(to, amount));
    }
}
```

This snippet only illustrates declaring the boundary; `PaymentRepository` and its methods are hypothetical business APIs, not part of the runnable program at the end of the lesson.

Do not call `transfer(...).subscribe()` inside the service and return `Mono.empty()`, because the work is detached onto a separate subscription. The external caller will see a different transaction from the actual database work.

With annotations, `@Transactional`'s rollback rules (defaulting to RuntimeException/Error; checked exceptions requiring `rollbackFor` rules where appropriate) must still be considered. Do not infer from `TransactionalOperator` examples that every exception rollback policy in annotations behaves identically.

## 6. Errors in transactions: rollback and the risk of swallowing errors

### 6.1. An error genuinely exiting the transaction boundary

```java
Mono<Void> tx =
        insertRecord(10L)
                .then(Mono.<Void>error(
                        new IllegalStateException("forced failure")))
                .as(transactionalOperator::transactional);
```

The insert completes before `Mono.error` emits the error signal. TransactionalOperator sees the error, rolls back, and propagates the error signal to the caller. Querying again from a new transaction shows record 10 does not exist if rollback succeeded.

`onErrorMap` only changes the error type; if it still emits an error, the transaction generally still rolls back. `doOnError` is used for logging or metrics and does not consume the error.

### 6.2. Swallowing an error inside the boundary can cause a commit

```java
Mono<Void> tx =
        insertRecord(11L)
                .then(Mono.<Void>error(
                        new IllegalStateException("recoverable")))
                .onErrorResume(error -> Mono.empty())
                .as(transactionalOperator::transactional);
```

`onErrorResume` handles the error **before** the transaction operator observes it. From TransactionalOperator's perspective, the publisher terminated normally. Without `setRollbackOnly`, it can commit record 11. This is an important logic bug.

If you need a fallback after rollback, place the handler **outside** the transaction:

```java
return insertRecord(12L)
        .then(Mono.<Void>error(
                new IllegalStateException("rejected")))
        .as(transactionalOperator::transactional)
        .onErrorResume(IllegalStateException.class,
                error -> Mono.empty());
```

Then the error crosses the transaction boundary, rollback is executed, and only afterward does the caller receive the fallback result. Do not treat all exceptions identically; rollback failures, connection failures, and business validation need distinct policies.

### 6.3. setRollbackOnly when returning a business result

If you want to return a valid result without committing:

```java
Mono<String> result = transactionalOperator
        .execute(status -> performChecks()
                .flatMap(accepted -> {
                    if (!accepted) {
                        status.setRollbackOnly();
                        return Mono.just("REJECTED");
                    }
                    return persistChanges().thenReturn("ACCEPTED");
                }))
        .single();
```

`performChecks` and `persistChanges` are illustrative methods, not part of the runnable project in section 11. With `Flux`-like flows, do not call `single()` if the callback can emit 0 or multiple items.

### 6.4. Errors after commit cannot automatically roll back

If a transaction has already committed and the caller later fails while sending the HTTP response, writing logs, or calling another API, you cannot “roll back” the committed database merely by emitting `Mono.error` downstream. Design outbox, business states, and idempotency when a transaction must coordinate with external systems.

## 7. Cancellation in transactions: Spring Framework 5.3+ rolls back

Spring Framework documentation confirms: since version **5.3**, a cancel signal in a reactive transaction triggers rollback. The reason is that cancellation gives no indication of whether the transaction finished enough work, nor why it was cancelled.

Operators that commonly trigger cancellation:

- `Flux.take(n)`: takes n items and then cancels upstream.
- `Flux.next()`: takes the first item and cancels the source Flux.
- `Mono.timeout(Duration)`/`Flux.timeout(Duration)`: on expiration, cancels the upstream source and emits TimeoutException downstream.
- WebFlux client disconnecting or stream closing: can lead to pipeline cancellation, depending on adapter lifecycle and timing.
- `Disposable.dispose()` or `Subscription.cancel()`: application proactively cancels.

### 7.1. Trap: returning a Flux in a data-writing transaction

```java
Flux<Long> tx = insertRecord(20L)
        .thenMany(Flux.just(1L, 2L, 3L))
        .as(transactionalOperator::transactional);

Mono<Long> first = tx.next();
```

`next()` takes the first element and cancels the rest of the transaction Flux. Even though the SQL insert may have executed, the transaction can **roll back** because the publisher never completed. Do not infer that receiving an item means the transaction committed.

Check operator placement:

```java
Flux<Long> risky = expensiveFlux()
        .as(transactionalOperator::transactional)
        .take(1); // downstream take can cancel the transaction.
```

If you only want one record, change the query to return one record and let the transaction complete naturally—such as `DatabaseClient...one()` or database SQL `LIMIT 1`—instead of running a long stream and cancelling it.

### 7.2. Do not wrap an infinite live stream in a transaction

```java
Flux<Event> live =
        databaseChanges()
                .concatWith(liveNotifications())
                .as(transactionalOperator::transactional);
```

This illustrative snippet can hold the connection and transaction until the client cancels or the source completes; if `liveNotifications` is an infinite stream, the transaction stays open for a very long time. That is usually a bad design.

A generally better approach: keep the transaction bounded to a finite read/write operation, commit and release the connection **before** emitting live data:

```java
Mono<List<Event>> initialSnapshot =
        readFiniteSnapshot()
                .collectList()
                .as(transactionalOperator::transactional);

Flux<Event> feed =
        initialSnapshot.flatMapMany(snapshot ->
                Flux.fromIterable(snapshot)
                        .concatWith(liveNotifications()));
```

This example illustrates the boundary-separation principle; the `Event` methods are hypothetical APIs. Use only when the snapshot is bounded in size; for large data, use paging/chunked transactions and an appropriate consistency mechanism instead of buffering unboundedly into a list.

### 7.3. Cancel is not a magical rollback

If a transaction has already committed before cancellation arrives, cancellation does not undo the commit. If the database/driver loses connection mid-commit, the state can be indeterminate from the caller's viewpoint. Avoid promising that “if the client times out, the database definitely did not change”.

For critical operations, return an ID/idempotency key and provide a status-check mechanism; do not blindly auto-retry due to the risk of double writes.

## 8. Releasing connections: use Spring-managed APIs first

Spring `DatabaseClient` and Spring Data R2DBC are already integrated with the transaction manager. This is the safe default choice for database operations in reactive services.

```java
Mono<Void> insert = databaseClient
        .sql("INSERT INTO audit_events(event_id, label) "
                + "VALUES (:id, :label)")
        .bind("id", 100L)
        .bind("label", "hello")
        .fetch()
        .rowsUpdated()
        .then();

return insert.as(transactionalOperator::transactional);
```

The code above needs no manual acquire/close of connections. TransactionOperator and DatabaseClient coordinate to acquire the transaction-bound connection, roll back or commit, clean up, and release.

### 8.1. ConnectionFactoryUtils

When you must integrate a low-level R2DBC library yet still want to participate in a Spring transaction, you can use:

```java
ConnectionFactoryUtils.getConnection(connectionFactory);
ConnectionFactoryUtils.releaseConnection(connection, connectionFactory);
```

These methods return publishers; compose them into the reactive chain. `releaseConnection` knows which connection is bound to the transaction context and **will not accidentally close** a connection the transaction manager is still using.

Do not call `connection.close()` directly mid-Spring-transaction to “release early”; that can break subsequent statements or corrupt the transaction.

### 8.2. Acquiring connections manually: Flux/Mono.usingWhen

If code genuinely creates connections itself **outside a Spring-managed transaction**, use `usingWhen` to clean up on complete, error, and cancel:

```java
public Mono<Integer> readConstant(ConnectionFactory factory) {
    return Mono.usingWhen(
            Mono.from(factory.create()),
            connection -> Flux.from(
                    connection.createStatement("SELECT 1").execute())
                    .flatMap(result -> Flux.from(
                            result.map((row, metadata) ->
                                    ((Number) row.get(0)).intValue())))
                    .single(),
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close()));
}
```

This is an illustrative Java method needing imports for `ConnectionFactory`, `Mono`, and `Flux`; it is not a standalone class in the section 11 project. Among the three cleanup callbacks:

1. The third argument runs when the resource closure completes.
2. The fourth argument runs when the resource closure errors.
3. The fifth argument runs when the subscription is cancelled.

Reactor subscribes/coordinates the cleanup publisher. If cleanup fails, the final signal the caller sees depends on `usingWhen` semantics; do not assume the business error is always preserved unchanged.

**Note:** `usingWhen` above only manages **closing the connection**; it does not automatically begin/commit/roll back a SQL transaction. If you call `beginTransaction()` yourself, you must also implement commit on success, rollback on error/cancel, and close on every branch (including when commit/rollback errors). Because missing an error path is very easy, prefer `R2dbcTransactionManager` and `TransactionalOperator`.

### 8.3. Why does doFinally not replace usingWhen?

Dangerous example:

```java
Mono<Result> result = doWork(connection)
        .doFinally(signal -> connection.close());
```

In R2DBC, `close()` returns `Publisher<Void>`. Calling the method and discarding the result as above **does not reliably execute cleanup**. The following variant is also uncontrolled:

```java
.doFinally(signal ->
        Mono.from(connection.close()).subscribe());
```

It spawns a separate subscription, detaching cleanup from the main lifecycle; close errors may be ignored and the caller does not wait for close to finish. `doFinally` is great for metrics/logging/signal inspection, but it is not a replacement for structured async resource management.

Use `usingWhen` for manually managed resources or let the Spring transaction manager handle it.

### 8.4. Do not close/commit twice

Do not both let Spring manage the transaction and manually call `commitTransaction()`, `rollbackTransaction()`, or `close()` on the same transactional connection. That breaks ownership: the manager may still need the connection to run more SQL, roll back, or clean up.

Only one layer is responsible for the final lifecycle of each connection. Data access code inside services only builds the work Publisher; it does not close manager-owned resources.

## 9. Operator order changes semantics

Compare:

| Pipeline | What does the transaction see? | Possible outcome |
| --- | --- | --- |
| `work.as(tx::transactional)` | Complete/error/cancel from work | Commits on complete; rolls back on error/cancel. |
| `work.onErrorResume(...).as(tx::transactional)` | May only see complete | May commit after swallowing the error. |
| `work.as(tx::transactional).onErrorResume(...)` | Error passes through tx before fallback | Rolls back then falls back. |
| `work.as(tx::transactional).take(1)` | Downstream cancels the transaction Flux | Rolls back even though the first item reached the client. |
| `work.take(1).as(tx::transactional)` | Tx sees a Flux that completed normally | May commit, **but work was not fully consumed**; only safe if that is the business intent. |
| `work.as(tx::transactional).timeout(d)` | On expiration, timeout cancels upstream | Rolls back if transaction is still active; does not undo an already-completed commit. |
| `work.timeout(d).as(tx::transactional)` | Timeout becomes an error inside tx | Rolls back on error; only observation point/timeout scope differs. |

Do not move operators just to “force a commit” while work is still unfinished. Define the business boundary properly: all operations needing atomicity stay inside the transaction; outside only receives results once the transaction has ended.

An overused `onErrorContinue` can drop per-element errors and let the pipeline complete. For transactions requiring atomicity, avoid `onErrorContinue` unless you have a very clear analysis of what data was written and the rollback policy.

## 10. Connection pool, timeouts, and starvation

In a reactive application, a transaction holds a connection until complete, error, or cancel is handled and cleaned up. Even though the code does not block a Java thread, it can still hold a **finite connection**.

Example pool with max three connections:

```text
Pool max = 3

Request A: transaction waiting on infinite upstream -> holds 1 connection
Request B: transaction reading a long-lived stream  -> holds 1 connection
Request C: slow-processing transaction              -> holds 1 connection
Request D: acquire connection -> must wait
Request E: acquire connection -> must wait
```

Consequences: pool wait time increases, requests time out, throughput drops; adding more threads cannot solve connection exhaustion.

Configuration to consider:

- `spring.r2dbc.pool.max-size`: connection pool cap.
- `spring.r2dbc.pool.initial-size` and `min-idle`: minimum connections created/kept.
- `spring.r2dbc.pool.max-acquire-time`: timeout waiting to acquire a connection.
- `spring.r2dbc.pool.max-idle-time` and `max-life-time`: connection age policies.
- Database statement timeout and transaction timeout: cap overly long work.
- Service concurrency thresholds: avoid too many simultaneous transactions.

Do not use a huge pool to mask a transaction leak; that shifts pressure onto the database. Monitor acquired/allocated/idle/pending and acquire errors.

### 10.1. Pool wait timeout vs transaction timeout

- **Pool acquire timeout:** failed to get a new/free connection within the time limit. The transaction may not even have started.
- **Connect timeout:** failed to establish a physical connection to the database.
- **Statement/query timeout:** a SQL command ran too long.
- **Transaction timeout:** how long a transaction is allowed to live per policy and driver/manager support.
- **Publisher timeout:** downstream received no signal within the preset window, causing error/cancel at that point.

Do not assume a Reactor `timeout(Duration)` replaces timeouts at the driver, database, connection pool, or protocol layer.

## 11. Spring Boot 3.3.5 example: commit, error, cancel, release

The demo application uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, **Spring Data R2DBC**, **in-memory H2**, **r2dbc-pool**, and **Reactor Test**.

To verify lifecycle behavior, the pool intentionally sets **max-size = 1**. After a cancelled transaction, a new test query must still be able to acquire the connection, exposing any held-resource leak. This configuration is strictly for the demo, **not a production recommendation**.

### 11.1. Project structure

```text
reactive-tx-cancel/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ReactiveTxCancelApplication.java
    │   │   ├── TransactionConfig.java
    │   │   └── LedgerService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/demo/
        └── LedgerServiceTest.java
```

### 11.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-tx-cancel</artifactId>
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
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-pool</artifactId>
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

The Spring Boot BOM manages compatible dependency versions. When using a different Spring/driver version, re-verify APIs and rollback/cancel rules before deploying.

### 11.3. application.properties

```properties
spring.application.name=reactive-tx-cancel
spring.main.web-application-type=none

spring.r2dbc.url=r2dbc:h2:mem:///txdemo?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE
spring.r2dbc.pool.enabled=true
spring.r2dbc.pool.initial-size=1
spring.r2dbc.pool.max-size=1
spring.r2dbc.pool.max-acquire-time=5s

spring.sql.init.mode=always
```

`DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive when the last physical connection closes during the demo process. `spring.sql.init.mode=always` runs `schema.sql` when the context starts. The single-connection pool ensures the verification query after cancel must wait for the resource to be returned.

### 11.4. schema.sql

```sql
CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id BIGINT PRIMARY KEY,
    label VARCHAR(100) NOT NULL
);
```

This SQL only initializes the schema. No external database or credentials are required.

### 11.5. ReactiveTxCancelApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTxCancelApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTxCancelApplication.class, args);
    }
}
```

### 11.6. TransactionConfig.java

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class TransactionConfig {
    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
```

Spring Boot configures a reactive transaction manager from the R2DBC ConnectionFactory. The bean above supplies TransactionalOperator for explicit use by the service. Do not create a `TransactionTemplate` for a reactive pipeline because that is the API for imperative transactions.

### 11.7. LedgerService.java

```java
package demo;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class LedgerService {

    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public LedgerService(DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    private Mono<Void> insert(long id, String label) {
        return db.sql(
                    "INSERT INTO ledger_entries(entry_id, label) "
                    + "VALUES (:id, :label)")
                .bind("id", id)
                .bind("label", label)
                .fetch()
                .rowsUpdated()
                .then();
    }

    // Complete -> COMMIT.
    public Mono<Void> saveTwo(long firstId, long secondId) {
        return insert(firstId, "first")
                .then(insert(secondId, "second"))
                .as(tx::transactional);
    }

    // Error -> ROLLBACK.
    public Mono<Void> failAfterInsert(long id) {
        return insert(id, "before-error")
                .then(Mono.<Void>error(
                        new IllegalStateException("intentional failure")))
                .as(tx::transactional);
    }

    // Cancel -> ROLLBACK.
    // Emit one item and intentionally never complete.
    public Flux<Long> insertThenNeverComplete(long id) {
        return insert(id, "before-cancel")
                .thenMany(
                        Flux.just(id).concatWith(Flux.<Long>never()))
                .as(tx::transactional);
    }

    // Error handled before tx sees it -> may COMMIT.
    public Mono<Void> recoverInside(long id) {
        return insert(id, "recovered-inside")
                .then(Mono.<Void>error(
                        new IllegalStateException("handled error")))
                .onErrorResume(IllegalStateException.class,
                        error -> Mono.empty())
                .as(tx::transactional);
    }

    // Query from a separate subscription: outside the transaction above.
    public Mono<Boolean> exists(long id) {
        return db.sql(
                    "SELECT entry_id FROM ledger_entries "
                    + "WHERE entry_id = :id")
                .bind("id", id)
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .first()
                .hasElement();
    }

    public Mono<Long> countAll() {
        return db.sql("SELECT COUNT(*) FROM ledger_entries")
                .map((row, metadata) ->
                        ((Number) row.get(0)).longValue())
                .one();
    }

    // Test-only reset: outside the transaction under test.
    public Mono<Void> clearAll() {
        return db.sql("DELETE FROM ledger_entries")
                .fetch()
                .rowsUpdated()
                .then();
    }
}
```

Key points to note:

- `saveTwo` uses `then`, avoiding uncontrolled concurrent SQL statements on the same transactional connection.
- `failAfterInsert` writes one row and then emits an error so the transaction rolls back.
- `insertThenNeverComplete` writes a row, emits one item, and **never emits completion**. The test cancels after the item to verify cancellation.
- `recoverInside` swallows the error directly inside the transaction; the data still commits. This is an important control case.
- `exists` and `countAll` use `DatabaseClient` to borrow connections from the pool in a transaction-aware manner. They do not close connections manually or call `subscribe()`.

### 11.8. LedgerServiceTest.java

```java
package demo;

import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import reactor.test.StepVerifier;

@SpringBootTest
class LedgerServiceTest {

    @Autowired
    LedgerService service;

    @BeforeEach
    void reset() {
        // Block only on the unit/integration test runner thread.
        service.clearAll().block(Duration.ofSeconds(5));
    }

    @Test
    void completeCommitsAndConnectionIsReusable() {
        StepVerifier.create(service.saveTwo(1L, 2L))
                .verifyComplete();

        StepVerifier.create(service.countAll())
                .expectNext(2L)
                .verifyComplete();

        StepVerifier.create(service.exists(1L))
                .expectNext(true)
                .verifyComplete();
    }

    @Test
    void terminalErrorRollsBack() {
        StepVerifier.create(service.failAfterInsert(3L))
                .expectErrorMatches(error ->
                        error instanceof IllegalStateException
                        && "intentional failure".equals(
                                error.getMessage()))
                .verify();

        StepVerifier.create(service.exists(3L))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void cancellingOpenTransactionRollsBackAndReleasesConnection() {
        StepVerifier.create(
                        service.insertThenNeverComplete(4L))
                .expectNext(4L)
                .thenCancel()
                .verify();

        // Pool max-size=1: this check only runs once the connection
        // has been returned. Timeout detects cleanup/pool leaks.
        StepVerifier.create(
                        service.exists(4L)
                                .timeout(Duration.ofSeconds(5)))
                .expectNext(false)
                .verifyComplete();
    }

    @Test
    void suppressingErrorInsideTransactionMayCommit() {
        StepVerifier.create(service.recoverInside(5L))
                .verifyComplete();

        StepVerifier.create(service.exists(5L))
                .expectNext(true)
                .verifyComplete();
    }
}
```

In the cancel test, `StepVerifier.thenCancel()` emits cancellation after the first item. `TransactionalOperator` handles rollback when cancelled. Because the pool has only one connection, the subsequent `exists(4L)` query must wait for the connection to return to the pool; if the transaction held the connection forever, the query would time out.

Checking `exists(false)` shows the insert did not commit. This check and single-connection pool provide useful integration evidence, though analyzing serious production incidents still requires metrics, transaction logs, traces, and verifying real driver/database behavior.

### 11.9. Running and expected results

In the project directory, run:

```bash
mvn test
```

Expected result: JUnit runs **4 tests, 0 failures, 0 errors** (assuming compatible Java/Maven environment and dependencies, and successful DB initialization). The assertions respectively verify:

| Test | Transaction signal | Final data |
| --- | --- | --- |
| `completeCommitsAndConnectionIsReusable` | Complete | Two records committed. |
| `terminalErrorRollsBack` | Error | Record 3 does not exist. |
| `cancellingOpenTransactionRollsBackAndReleasesConnection` | Cancel | Record 4 does not exist; a new query can acquire the connection. |
| `suppressingErrorInsideTransactionMayCommit` | Complete after fallback | Record 5 exists. |

`mvn spring-boot:run` boots the context and creates the schema, though this demo application opens no HTTP endpoints and does not run the tests automatically; to observe results, run `mvn test`. Do not assume starting the application runs the test transactions on its own.

## 12. Complex scenarios: multiple repositories and the reactive ecosystem

### 12.1. Multiple repositories on one ConnectionFactory

If two R2DBC repositories both participate in `R2dbcTransactionManager` and the same connection context, their statements can share one transaction. Compose them:

```java
return orderRepository.save(order)
        .flatMap(saved -> inventoryRepository.reserve(saved))
        .then()
        .as(tx::transactional);
```

These repositories are illustrative business APIs. Do not call `subscribe()` separately on `inventoryRepository.reserve`; doing so can run it outside the original transaction.

### 12.2. Database + HTTP API does not create a distributed transaction

An R2DBC transaction does not bundle both the database and an HTTP service into one atomic commit:

```java
return db.insertOrder(order)
        .then(webClient.post()
                .uri("/charge")
                .retrieve()
                .bodyToMono(Void.class))
        .as(tx::transactional);
```

This is an anti-pattern if you assume the charge and DB will roll back together. The remote HTTP side effect may have already completed even if the DB transaction later cancels/rolls back. Use **transactional outbox, sagas/compensation, and idempotency keys**, depending on business requirements.

Do not hold a DB transaction open while waiting on slow HTTP unless necessary; it occupies a connection for a long time and raises the risk of pool starvation.

### 12.3. Kafka/RabbitMQ/RSocket do not share the R2DBC transaction

A message publisher over Kafka, RabbitMQ, or RSocket has its own lifecycle. R2DBC rollback does not automatically recall an already-published message. If you need “publish only if DB commits”, consider an outbox table in the same database transaction, followed by a separate publisher reading the outbox and emitting messages with idempotency.

Do not use fire-and-forget or unacknowledged sends as proof the external system received/processed the business event.

### 12.4. WebFlux client disconnect and cancellation

When an HTTP client disconnects, the server can usually cancel the response pipeline's subscriber. However, when cancellation reaches the transaction depends on the framework adapter, buffering, whether the response has committed, and where the transaction sits in the pipeline.

Test disconnect scenarios directly with integration tests matching your runtime; do not assume every TCP disconnect rolls back every completed transaction. For critical resource-creating operations, ensure correctness through durable state and idempotency, not solely through cancellation.

## 13. Observability and troubleshooting

### 13.1. Recommended metrics

| Metric | Warning signal |
| --- | --- |
| Acquired/active connections | Constantly near `max-size` even at low request rates. |
| Idle connections | Near 0 for an abnormally long period. |
| Pending acquires / acquire latency | New requests waiting increasingly long for the pool. |
| Transaction duration | Transactions running longer than SLA. |
| Rollback on error/cancel | Sudden spike in rollback rate. |
| DB query duration | Slow statements or locks blocking transactions. |
| Connection create/close failures | Broken driver/network/DB or cleanup failures. |
| Timed-out subscriptions | Downstream timeout too low or DB too slow. |

If Micrometer/Actuator is present, enable the metrics actually exported by the driver/pool and configure appropriate alerts. Do not assume metric names are identical across all drivers and versions.

### 13.2. How to trace a leaked/held connection

1. Identify the symptom: high pool acquired count, rising pending acquires, or timeout errors?
2. Check whether any transaction has an unterminated Flux or calls `block()` on the event loop.
3. Look for `take`, `next`, `timeout`, `onErrorResume`, and manual `subscribe()` calls around transactions.
4. Check whether code manually calls `ConnectionFactory.create()` or `close()` without composing cleanup.
5. Correlate request/transaction IDs with borrow/release times, driver errors, and DB locks.
6. Write a cancel/timeout integration test with a small pool to reproduce.
7. Fix ownership and transaction boundaries; do not just raise pool size to hide leaks.

Do not log passwords, sensitive SQL data, bind parameters containing PII, or connection URLs with credentials. Keep logs bounded and preserve correlation IDs.

### 13.3. Timeouts and shutdown

During application shutdown, stop accepting new requests, wait a bounded period for active transactions, cancel unnecessary streams, and close the ConnectionPool/ConnectionFactory per Spring Boot's lifecycle. Do not dispose the pool while transactions are still actively using connections.

Do not create extra ConnectionPool beans outside Spring and forget to call `dispose()`. If managing a pool manually, wire shutdown to dispose at the right time and check for still-acquired connections.

## 14. Common mistakes and how to fix them

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Treating cancel like complete | Can commit unfinished work | Spring reactive 5.3+ rolls back cancel; design pipelines for clear completion. |
| Thinking cancel is always `onError` | Error handlers do not run on cancel | Use `doFinally` to observe, transaction manager/usingWhen for cleanup. |
| Using `Flux.next()` outside a transaction Flux | Cancels upstream and rolls back | Query one record or place the transaction at the right boundary. |
| Holding a transaction around an infinite live stream | Holds connection until cancelled | Commit a short snapshot-read transaction then stream outside the transaction. |
| Swallowing errors with `onErrorResume` before tx | Transaction sees complete and may commit | Let the error cross the boundary or call `setRollbackOnly` explicitly. |
| Using `Mono.empty()` to signify rollback | Empty is normal completion | Use error/rollbackOnly per contract. |
| Thinking client timeout guarantees DB did not change | Commit may already have happened | Use IDs, idempotency, and state queries. |
| Calling `subscribe()` manually in a transactional service | Detaches subscription and Reactor Context | Compose and return the entire publisher to the caller. |
| Using blocking JDBC inside an R2DBC pipeline | Blocks event loop and uses a different transaction | Use a reactive driver or isolate blocking on a dedicated scheduler, without assuming shared transactions. |
| Calling `ConnectionFactory.create()` and treating it as the tx connection | May open a connection outside the context | Use DatabaseClient or ConnectionFactoryUtils. |
| Manually closing a Spring-managed connection | Manager loses the resource mid-transaction | Let the transaction manager handle cleanup. |
| Calling `connection.close()` and ignoring the publisher | Cleanup is never subscribed to | Use `usingWhen` or compose close properly. |
| `doFinally(...subscribe(close))` | Out-of-pipeline cleanup, hard to handle errors | Use structured async cleanup. |
| Rolling back but forgetting to release | Pool exhaustion | Ensure cleanup/reset/close on every termination path. |
| Assuming rollback can never fail | Broken connection can obstruct rollback | Monitor rollback failures, DB state, and connection health. |
| Retrying POST/transfer infinitely after timeout | Duplicate side effects | Bounded retries, backoff, and idempotency keys. |
| Increasing pool size to hide leaks | Increases DB pressure without fixing root cause | Fix transaction scope and lifecycle, add metrics. |
| Using `@Transactional` with self-invocation | Proxy does not intercept | Call via bean/proxy or use TransactionalOperator directly. |
| Writing tests that only check exceptions | Misses wrong commit/rollback behavior | Query data after the transaction and verify pool return. |

## 15. Self-check questions

**Question 1.** How do `onError` and `cancel` differ?  
**Answer:** onError is a publisher terminal error; cancel is the subscriber stopping the subscription and carries no cause. Spring 5.3+ handles cancel on a reactive transaction by rolling back.

**Question 2.** When a transaction emits one item and the client uses `take(1)`, is it guaranteed to have committed?  
**Answer:** No. `take` can cancel the upstream transaction Flux and trigger rollback, even though the item was already emitted.

**Question 3.** Does `Mono.empty()` automatically roll back?  
**Answer:** No; it is normal completion, usually leading to commit unless the transaction is marked rollback-only.

**Question 4.** Why is `onErrorResume` before `TransactionalOperator` dangerous?  
**Answer:** It can turn an error into completion; the operator never sees the error and may commit the statements that ran.

**Question 5.** Does a Spring reactive transaction bind to ThreadLocal or Reactor Context?  
**Answer:** Subscription-bound Reactor Context. Manually subscribing to a child pipeline can detach the transaction context.

**Question 6.** Are rollback and close synonymous?  
**Answer:** No. Rollback handles data changes; close/release returns the resource to the pool or driver.

**Question 7.** What does R2DBC's `Connection.close()` require to execute?  
**Answer:** It returns a Publisher; it must be composed/subscribed via the reactive lifecycle. For Spring-managed connections, let the manager handle it.

**Question 8.** Why use `usingWhen` instead of `doFinally` to close connections manually?  
**Answer:** `usingWhen` coordinates async cleanup on complete/error/cancel and manages cleanup error signals; `doFinally` is only a synchronous callback and does not await a close publisher.

**Question 9.** When is a connection returned to the pool?  
**Answer:** After the manager completes commit/rollback and cleanup, or after low-level code closes the resource properly; exact timing depends on the driver/pool.

**Question 10.** Does wrapping an HTTP call inside a DB transaction guarantee everything is atomic together?  
**Answer:** No. HTTP/Kafka/RSocket do not automatically participate in R2DBC atomic commits; use outbox, sagas, or idempotency when coordinating.

## 16. Key takeaways

- In Spring Framework **5.3+**, cancellation in a reactive transaction leads to **rollback**; complete commits unless rollback-only, and error rolls back per policy.
- **Transaction completion** and **connection release** are two related yet distinct responsibilities. A held connection exhausts the pool even if threads are not blocked.
- Prefer `DatabaseClient`/Spring Data R2DBC with `R2dbcTransactionManager`, `TransactionalOperator`, or `@Transactional`; do not manually begin/commit/close Spring-managed connections.
- `onErrorResume` **inside** a transaction can cause a commit after an error; `take`, `next`, and `timeout` **outside** a transaction can cancel and roll back.
- Use `usingWhen` for manually managed connections. `doFinally` is good for observing signals, not replacing structured async cleanup.
- Design transactions to be short, finite, and resource-bounded; do not wrap infinite live streams and do not treat client timeouts as proof the DB did not commit.
- Always test all three paths—complete, error, and cancel—and verify data **after the transaction** while monitoring the connection pool.

## 17. References

1. [Spring Framework 6.2 – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html): `TransactionalOperator` and Cancel Signals; since Spring 5.3 cancel leads to rollback.
2. [Spring Framework – Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): reactive Publisher, Reactor Context, and transaction manager.
3. [Spring Framework – @Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): rollback rules and propagation.
4. [Spring Framework – Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): `DatabaseClient`, connection management, and `ConnectionFactoryUtils`.
5. [R2DBC SPI 1.0 – Connection API](https://r2dbc.io/spec/1.0.0.RELEASE/api/io/r2dbc/spi/Connection.html): `commitTransaction`, `rollbackTransaction`, `close`.
6. [Project Reactor – Mono.usingWhen API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): cleanup on complete/error/cancel.
7. [Spring Boot 3.3 – Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.r2dbc.pool.*`.
8. [Spring Boot – Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql` for R2DBC ConnectionFactory.
9. [R2DBC H2 – Supported Connection URLs](https://github.com/r2dbc/r2dbc-h2): `r2dbc:h2:mem:///...` and H2 options.
