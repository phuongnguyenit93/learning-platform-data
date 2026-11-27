# @Transactional on Methods Returning a Publisher

> **Chapter:** Reactive Transactions  
> **Module:** `SPRING_DATA_MONGODB`

In Spring Data MongoDB, a service can return `Mono<T>` or `Flux<T>` instead of executing queries and returning values immediately. When multiple documents need to be written atomically, developers often add `@Transactional` to a reactive method. However, **merely adding the annotation does not guarantee that a transaction will work**: the application needs a matching `ReactiveMongoTransactionManager`, MongoDB operations must run within the **same reactive chain and Reactor Context**, and the Publisher must actually be **subscribed to**.

Unlike imperative transactions that typically bind state to `ThreadLocal`, Spring manages **reactive transactions** through **Reactor Context**. Consequently, `ReactiveMongoTemplate` or `ReactiveMongoRepository` operations composed into the returned Publisher can participate in the same session and transaction. A detached `subscribe()` call, a blocking operation, or the wrong transaction manager type can break atomicity even while the code looks correct on the surface.

This lesson belongs to the `SPRING_DATA_MONGODB` module: connecting and mapping documents, operating on MongoDB via repositories or templates, practicing queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics. The topic here is **how to use `@Transactional` accurately on methods returning a Publisher**, not merely an introduction to Reactor syntax.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why reactive `@Transactional` is tied to **subscription** rather than committing immediately when a method returns a `Mono`/`Flux`.
2. Distinguish `ReactiveMongoTransactionManager` from `MongoTransactionManager` and Reactor Context from `ThreadLocal`.
3. Configure a transaction manager for `ReactiveMongoTemplate` and reactive repositories sharing a `ReactiveMongoDatabaseFactory`.
4. Write a service returning `Mono<ReservationReceipt>` that performs two MongoDB writes **sequentially** and rolls back on error.
5. Spot pitfalls such as calling `subscribe()` inside a service, `block()`, self-invocation, `onErrorResume` swallowing errors, multi-scheduler processing, and accessing multiple MongoClients.
6. Explain commit/rollback behavior when a Publisher completes, errors, or is canceled, as well as the limits of long `Flux` streams and `take(1)`.
7. Compare `@Transactional` with `TransactionalOperator`, define propagation boundaries, and design safe retries.
8. Write integration tests with `StepVerifier` against a MongoDB replica set, verifying BSON state after commit/rollback and race conditions.

## 2. A Publisher Is an Execution Plan, Not Already-Written Data

In reactive systems, a `Publisher` is a source that emits `onNext`, `onComplete`, or `onError` signals when subscribed to. In Reactor, two familiar types are:

- `Mono<T>`: emits at most **one** value `T` and completes, or completes empty or with an error.
- `Flux<T>`: emits **0..N** values `T` and completes, or signals an error.

Code:

```java
Mono<OrderDocument> saved = reactiveMongoTemplate
    .insert(new OrderDocument("ORD-101", "TENANT-A", "NEW"));
```

normally **has not sent the insert command to MongoDB yet** at the moment Java constructs the `saved` Publisher. Actual I/O happens when the Publisher is subscribed to:

```java
saved.subscribe();
```

However, the line above is only meant to illustrate the subscription principle; **never call `subscribe()` inside a business service returning a Publisher**. Return the Publisher so WebFlux, `StepVerifier` tests, or the caller can coordinate subscription and errors properly.

### 2.1. Three Distinct Moments

```text
Caller calls reserve(cmd)
      |
      v
Java method assembles Publisher
      |    (usually no MongoDB I/O yet)
      v
Caller receives Mono<ReservationReceipt>
      |
      +-- no subscription ------> no reactive database work
      |
      +-- subscription
              |
              v
       Reactive tx starts
              |
              v
       MongoDB operations execute
              |
          +---+----+
          |        |
       complete   error/cancel
          |        |
          v        v
        commit   rollback/cleanup
```

Actual start and end timing also depends on interceptors, operators, and Publisher lifecycle. **Subscription is the coordination point for a reactive transaction**; completion of the transactional Publisher must pass through the transaction manager and commit successfully before the caller reports that the business action succeeded.

### 2.2. Code Running at Assembly Time Can Still Have Side Effects

```java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<String> createOrder() {
    System.out.println("Method invoked");
    return template.insert(new OrderDocument(
        "ORD-101", "TENANT-A", "NEW"))
        .map(OrderDocument::id);
}
```

`System.out.println(...)` is imperative Java and executes when the method **is called to assemble the Publisher**, without waiting for subscription or transaction start. Do not place non-rollbackable side effects there expecting them to be part of the transaction.

When you need to defer data construction until subscription as well:

```java
return Mono.defer(() -> {
    String id = java.util.UUID.randomUUID().toString();
    return template.insert(
            new OrderDocument(id, "TENANT-A", "NEW"))
        .map(OrderDocument::id);
});
```

However, generating a new UUID **on every subscription** can break idempotency if the caller retries. For sensitive business operations, preserve a **stable operation ID from the request** rather than generating a new ID per attempt.

## 3. Reactive Transactions Use Reactor Context, Not Imperative ThreadLocal

Spring imperative transactions normally read the transaction context bound to the calling thread. Reactive execution can hop threads via `publishOn`/`subscribeOn` while remaining one logical stream, so `ThreadLocal` is insufficient for carrying transaction state.

The **reactive transaction manager** propagates transaction/session metadata through `Reactor Context`. Spring Data MongoDB reads that context to associate reactive operations with the proper `ClientSession`.

```text
HTTP request
  |
  v
@Transactional reactive proxy
  |
  +-- Reactor Context contains transactional state
  |
  +-- ReactiveMongoTemplate.updateFirst(...)
  |       -> joins transaction/session
  |
  +-- ReactiveMongoTemplate.insert(...)
  |       -> joins same transaction/session
  |
  +-- Publisher completion -> manager commits
  +-- Publisher error       -> manager rolls back
```

### 3.1. Switching Schedulers Does Not Inherently Lose Reactor Context

A common misconception is that `publishOn(Schedulers.boundedElastic())` automatically breaks a transaction. Reactor Context **propagates across properly supported operators** even when threads change.

Real bugs typically come from **detaching from the Publisher chain** (manual `subscribe()`, non-Reactor async callbacks, creating an unconnected Publisher), using a **different client/template session**, or calling blocking APIs that the reactive transaction manager does not coordinate.

### 3.2. A Separate Publisher Does Not Automatically Share the Transaction

```java
// ANTI-PATTERN: detached branch.
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> process() {
    template.insert(new AuditDocument("A1"))
        .subscribe(); // independent subscription, not guaranteed to join

    return template.insert(new OrderDocument(
        "O1", "TENANT-A", "NEW")).then();
}
```

An immediately subscribed audit insert can run outside the returned Publisher's transaction or have an independent lifetime. If the order insert fails, the audit document may still be persisted.

The right approach is composition:

```java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> process() {
    return template.insert(new AuditDocument("A1"))
        .then(template.insert(new OrderDocument(
            "O1", "TENANT-A", "NEW")))
        .then();
}
```

When both operations use the same transactional factory and the composed Publisher chain is properly subscribed to, they participate in the same transaction.

## 4. What Conditions Are Required for Reactive @Transactional to Work?

| Condition | What Happens If Missing/Wrong? |
| --- | --- |
| Transaction-capable MongoDB deployment (replica set or supported sharded cluster) | Standalone servers generally do not support multi-document transactions |
| Configured `ReactiveMongoTransactionManager` | Reactive methods may not be transactionally managed properly |
| Method returns a supported `Publisher`/reactive type (`Mono`/`Flux`) | Reactive transactions cannot be applied like synchronous calls |
| Invocation goes through the Spring transactional proxy | Self-invocation can bypass interception |
| `ReactiveMongoTemplate`/repositories share `ReactiveMongoDatabaseFactory`/session binding | Commands on another factory run outside the transaction |
| Caller subscribes and observes terminal signals | Without subscription the pipeline does not run; errors/cancellations must be observed |
| MongoDB commands stay in the same reactive chain | Detached subscriptions may commit/roll back independently |
| Operation ordering within the same session is controlled | Parallel DB operations in a transaction may not be safely supported |
| Errors are not converted into normal completion before the transaction boundary | The transaction may commit instead of rolling back |

**Note:** `@Transactional` does not put arbitrary network I/O inside the transaction. HTTP calls, Kafka publishes, email sends, filesystem writes, and other databases do not join the MongoDB transaction just because they appear in the same Reactor chain.

## 5. Configuring ReactiveMongoTransactionManager

File `ReactiveMongoTransactionConfiguration.java`:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class ReactiveMongoTransactionConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
```

In this example, `factory` is provided by the application or Spring Boot according to the reactive MongoDB configuration. When multiple factories exist, use `@Qualifier` and matching managers; never put a repository on factory A while the transaction manager uses factory B.

### 5.1. Reactive and Imperative Transaction Managers Differ

| Component | Imperative | Reactive |
| --- | --- | --- |
| Transaction manager | `MongoTransactionManager` | `ReactiveMongoTransactionManager` |
| Template | `MongoTemplate` | `ReactiveMongoTemplate` |
| Repository | `MongoRepository` | `ReactiveMongoRepository` |
| Primary return type | Value/`void` | `Mono<T>`, `Flux<T>`, supported Publishers |
| Typical context | Thread-bound transaction | Reactor Context-bound transaction |
| Execution model | Method executes immediately | Publisher executes upon subscription |
| Testing style | Call method + assert | `StepVerifier`/subscribe until terminal signal |

If an application declares **both transaction managers**, explicitly specify the right manager on each call path:

```java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserve(...) {
    // ReactiveMongoTemplate / ReactiveMongoRepository only
}
```

Do not use `MongoTransactionManager` on a reactive pipeline expecting it to manage sessions via Reactor Context. Likewise, do not call blocking `MongoTemplate` inside a reactive callback expecting it to join a reactive transaction.

### 5.2. @EnableTransactionManagement and Boot Configuration

In a Spring application with transaction infrastructure enabled (typically via configuration or appropriate auto-configuration), Spring AOP creates interceptors for `@Transactional`. In manual setups, `@EnableTransactionManagement` or equivalent configuration may be needed.

However, **do not assume** that merely adding the annotation and manager bean will always work identically across every Spring Boot version. Verify context startup, bean names, proxy creation, selected manager type, and run an integration test confirming two MongoDB writes actually roll back on error.

### 5.3. URIs and Transaction Deployments

A test MongoDB replica set URI looks like:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/shop?replicaSet=rs0
```

These hostnames are examples. For transactions to work, the cluster must support sessions, elect a primary, and be properly configured. When deploying on MongoDB Atlas or managed clusters, use the official environment connection URI, TLS, and credentials. Do not assume a standalone MongoDB instance or mock server is sufficient for testing multi-document transactions.

## 6. End-to-End Scenario: Reserving and Deducting Stock

A sales service needs to reserve a product quantity:

1. Locate the stock record by `tenantId` and `stockId`, deducting only if `available >= quantity`.
2. Save a reservation with a stable `operationId`.
3. If both succeed, commit; otherwise, do not leave stock deducted without a reservation.

Example:

```javascript
// Collection stock_items
{
  _id: "STOCK-101",
  tenantId: "TENANT-A",
  available: NumberLong(10)
}

// Collection reservations after successfully reserving 3 items
{
  _id: "RES-001",
  tenantId: "TENANT-A",
  stockId: "STOCK-101",
  quantity: NumberLong(3)
}
```

Expected outcome: stock has `7` remaining and reservation `RES-001` exists. If inserting the reservation hits a duplicate key or server error, the stock update must roll back within the same transaction.

### 6.1. Entities and DTOs

File `StockDocument.java`:

```java
package com.example.shop.reservation;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "stock_items")
public record StockDocument(
    @Id String id,
    String tenantId,
    long available
) {}
```

File `ReservationDocument.java`:

```java
package com.example.shop.reservation;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "reservations")
public record ReservationDocument(
    @Id String id,
    String tenantId,
    String stockId,
    long quantity
) {}
```

File `ReserveCommand.java`:

```java
package com.example.shop.reservation;

public record ReserveCommand(
    String tenantId,
    String operationId,
    String stockId,
    long quantity
) {}
```

File `ReservationReceipt.java`:

```java
package com.example.shop.reservation;

public record ReservationReceipt(
    String operationId,
    String state
) {}
```

File `InsufficientStockException.java`:

```java
package com.example.shop.reservation;

public final class InsufficientStockException
        extends RuntimeException {
    public InsufficientStockException() {
        super("Stock does not exist or has insufficient quantity");
    }
}
```

Assume `tenantId` is derived or verified by authentication/authorization, rather than trusting arbitrary client-supplied values. `operationId` is a stable business ID preventing HTTP request retries from creating brand-new reservations.

### 6.2. Service with @Transactional Returning Mono

File `ReservationService.java`:

```java
package com.example.shop.reservation;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReservationService {

    private final ReactiveMongoTemplate template;

    public ReservationService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager")
    public Mono<ReservationReceipt> reserve(
            ReserveCommand command) {

        return Mono.defer(() -> {
            validate(command);

            Query stockQuery = Query.query(
                Criteria.where("_id").is(command.stockId())
                    .and("tenantId").is(command.tenantId())
                    .and("available").gte(command.quantity()));

            Update decrement = new Update()
                .inc("available", -command.quantity());

            return template.updateFirst(
                    stockQuery, decrement, StockDocument.class)
                .flatMap(result -> {
                    if (result.getModifiedCount() != 1) {
                        return Mono.error(
                            new InsufficientStockException());
                    }

                    ReservationDocument reservation =
                        new ReservationDocument(
                            command.operationId(),
                            command.tenantId(),
                            command.stockId(),
                            command.quantity());

                    return template.insert(reservation)
                        .map(saved -> new ReservationReceipt(
                            saved.id(), "RESERVED"));
                });
        });
    }

    private static void validate(ReserveCommand command) {
        if (command == null
                || command.tenantId() == null
                || command.tenantId().isBlank()
                || command.operationId() == null
                || command.operationId().isBlank()
                || command.stockId() == null
                || command.stockId().isBlank()
                || command.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid reservation request");
        }
    }
}
```

The method **returns `Mono<ReservationReceipt>`** and is wrapped by Spring's transactional interceptor. The reactive MongoDB commands are composed into one pipeline using the same `ReactiveMongoTemplate`/factory. There is no `subscribe()` or `block()` inside.

### 6.3. Step-by-Step Breakdown

| Step | Operation | On Error |
| --- | --- | --- |
| 1 | `Mono.defer` defers validation/query construction until subscribe | `IllegalArgumentException` emitted as error signal; no writes occur |
| 2 | `updateFirst` decrements `available` when stock and tenant match | MongoDB error fails the Publisher |
| 3 | Check `modifiedCount` | Insufficient stock -> `Mono.error`, transaction rolls back |
| 4 | `insert` reservation with stable ID | Duplicate key/server error -> rolls back stock update as well |
| 5 | `map` builds `ReservationReceipt` | Result only signifies success once transaction commits |

Here `flatMap` invokes the insert **only after** `updateFirst` emits its result; it does not run two DB operations in parallel on the same session. This respects the MongoDB reactive driver's transaction execution constraints.

### 6.4. Why Put the Condition Inside the Update?

Do not design it like this:

```java
// ANTI-PATTERN idea: read available, then update unconditionally.
template.findById(stockId, StockDocument.class)
    .flatMap(stock -> template.updateFirst(
        Query.query(Criteria.where("_id").is(stockId)),
        new Update().inc("available", -quantity),
        StockDocument.class));
```

This snippet merely illustrates a flawed pattern and is not a complete method. Under concurrent updates, checking `available >= quantity` **directly inside the update statement** is safer than reading first and issuing an unconditional update. Transactions can still hit write conflicts and need controlled retries, but that is no reason to omit the business precondition.

### 6.5. Outcome Flows on Success and Error

```text
Subscribe reserve(RES-001, qty=3)
    |
    v
BEGIN transaction
    |
    +-- stock_items: available 10 -> 7
    |
    +-- reservations: insert RES-001
    |
    v
COMMIT
    |
    v
Mono emits ReservationReceipt("RES-001", "RESERVED")
and successfully completes
```

When inserting `RES-001` fails (e.g., duplicate key):

```text
BEGIN transaction
    |
    +-- stock_items: available 10 -> 7 (uncommitted)
    |
    +-- reservations: duplicate key
    |
    v
ERROR -> ROLLBACK
    |
    v
stock_items.available stays 10
reservation insert from failed attempt is not committed
```

With reactive transactions, the transaction manager emits an error signal if it cannot complete. **Never trigger downstream business success logic just because `map(saved -> receipt)` ran**; the subsequent commit can still fail or end with an unknown outcome.

## 7. Subscription Is the Boundary: Who Subscribes and Who Handles Errors?

### 7.1. WebFlux Controller Returns Mono Directly

```java
package com.example.shop.reservation;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReservationController {

    private final ReservationService reservationService;

    public ReservationController(
            ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    @PostMapping("/reservations")
    public Mono<ResponseEntity<ReservationReceipt>> reserve(
            @RequestBody ReserveCommand request) {

        // Tenant and user permissions must be verified
        // by the security layer before calling the service.
        return reservationService.reserve(request)
            .map(ResponseEntity::ok);
    }
}
```

WebFlux subscribes to the Publisher to serve the HTTP response. The controller does not call `subscribe()` itself, as doing so would create a second subscription and lose error/response propagation.

### 7.2. Unit/Integration Tests Must Subscribe

```java
StepVerifier.create(
        reservationService.reserve(
            new ReserveCommand(
                "TENANT-A", "RES-001", "STOCK-101", 3)))
    .expectNextMatches(receipt ->
        receipt.operationId().equals("RES-001")
            && receipt.state().equals("RESERVED"))
    .verifyComplete();
```

`verifyComplete()` makes the test wait for **completion**, not just an `onNext` value. If a commit failure is signaled after the body builds the receipt, the test can still catch it; calling `expectNext` followed by `thenCancel()` is not enough to prove a successful commit.

### 7.3. Without Subscribe, No Transaction Completes

```java
// Anti-pattern: building a Mono and forgetting it.
Mono<ReservationReceipt> pipeline =
    reservationService.reserve(command);

// Not returned, not subscribed, no StepVerifier.
// Do not expect any data to be written.
```

Tests like `assertThat(pipeline).isNotNull()` only verify that a Publisher object was created; they **do not verify** MongoDB commands, sessions, commits, or rollbacks.

### 7.4. Multiple Subscriptions Can Re-Execute Business Logic

Most Publishers returned by `ReactiveMongoTemplate` are **cold**: each subscription can re-execute the operations.

```java
Mono<ReservationReceipt> publisher =
    reservationService.reserve(command);

// Subscribing to this publisher twice triggers two business attempts.
// The second attempt may hit a duplicate operationId.
```

Do not use `cache()` on a `Mono` as a production idempotency mechanism. An in-JVM cache does not survive across instances or restarts and cannot replace unique indexes/`operationId`. Reservation APIs must use a **stable idempotency key** and handle duplicates per contract.

### 7.5. @Transactional Does Not Run on Self-Invocation

```java
@Service
public class ReservationFacade {

    public Mono<ReservationReceipt> entry(ReserveCommand cmd) {
        return reserveInternal(cmd); // internal call via this
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager")
    public Mono<ReservationReceipt> reserveInternal(
            ReserveCommand cmd) {
        // ...
    }
}
```

In standard proxy-based `@Transactional` mode, internal calls do not pass through the transaction interceptor, so the annotation on `reserveInternal` may **have no effect**. Place the transactional method in a separate Spring-injected bean and call it through the bean proxy, or use `TransactionalOperator` explicitly within the same class where appropriate.

Do not call `this.reserveInternal(...)` expecting the framework to detect the transaction simply because the return type is `Mono`.

## 8. Complete, Error, and Cancel: What Triggers Commit or Rollback?

A reactive transaction does not inspect method names like "reserve" or "delete" to decide outcomes. It manages the transaction lifecycle based on the **Publisher's terminal signals** and **rollback rules**.

| Signal from Transactional Publisher | Expected Behavior |
| --- | --- |
| `onComplete` after all valid operations | Manager attempts to **commit** the transaction |
| `Mono.empty()`/`Flux.empty()` completing normally | Still a **completion**; does not imply rollback |
| `onError` with `RuntimeException`/`Error` under default rollback rules | Manager **rolls back/aborts** the transaction |
| `onError` with a checked exception | Depends on rollback rules; check/configure `rollbackFor` when needed |
| `cancel` from subscriber | In modern Spring reactive transactions, cancellation typically triggers **rollback** |
| Commit returns error or uncertain outcome | Never report business success just because the body emitted `onNext` |

**Note:** Spring transactions use **rollback rules**. In standard setups, unchecked exceptions and `Error` trigger rollback by default; checked exceptions are not automatically rolled back in all cases. If a publisher emits a checked exception meant to roll back, explicitly configure `@Transactional(rollbackFor=...)` or convert it to an intentional unchecked domain exception.

### 8.1. Proper Failure: Let the Exception Reach the Transaction Boundary

In `ReservationService`, when stock is insufficient:

```java
if (result.getModifiedCount() != 1) {
    return Mono.error(new InsufficientStockException());
}
```

`InsufficientStockException` extends `RuntimeException`. When that signal crosses the transaction interceptor, the transaction rolls back under default rules. Any earlier MongoDB commands in the same transaction will not be committed separately either.

### 8.2. Pitfall: onErrorResume Inside a @Transactional Method

Anti-pattern:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserveWrong(
        ReserveCommand command) {

    return updateStock(command)
        .then(insertReservation(command))
        .onErrorResume(error ->
            Mono.just(new ReservationReceipt(
                command.operationId(), "IGNORED_ERROR")));
}
```

This is method-level Java pseudocode (assuming `updateStock` returns `Mono<?>` and `insertReservation` returns `Mono<ReservationReceipt>`). If inserting the reservation fails after stock was decremented, `onErrorResume` converts the error into a normal completion **before the transaction manager sees it**, so the transaction may **commit the stock decrement**.

**Fix:** if errors must trigger rollback, let the error signal pass through the transactional boundary:

```java
return updateStock(command)
    .then(insertReservation(command))
    .onErrorMap(error ->
        new ReservationFailedException(
            "Unable to reserve stock", error));
```

Here `ReservationFailedException` is an application-defined `RuntimeException`. `onErrorMap` transforms the exception type while preserving the **error signal**, allowing the transaction to roll back under default rules.

### 8.3. Place API Fallbacks Outside the Transaction

A facade/controller outside the proxy can translate failures into an appropriate response:

```java
public Mono<ReservationResponse> tryReserve(
        ReserveCommand command) {

    return reservationService.reserve(command)
        .map(receipt ->
            new ReservationResponse(true, receipt.operationId()))
        .onErrorResume(InsufficientStockException.class,
            ex -> Mono.just(
                new ReservationResponse(false, null)));
}
```

In this example, `ReservationResponse` is an illustrative DTO. Crucially, `reservationService.reserve(...)` is invoked **through the bean proxy**; recovery sits **outside** the transactional Publisher so the error crosses the transaction interceptor and triggers rollback before the facade converts it into a response.

Do not mechanically turn every error (especially unknown commit outcomes) into `false`. An uncertain commit failure requires a pending-reconciliation state, not an assurance that "nothing was written."

### 8.4. Mono.empty Does Not Mean Rollback

```java
return template.updateFirst(query, update, StockDocument.class)
    .flatMap(result -> {
        if (result.getModifiedCount() == 0) {
            return Mono.empty();
        }
        return template.insert(reservation);
    });
```

If `Mono.empty()` is returned, the transactional Publisher completes normally and the manager may **commit** any earlier successful statements. If insufficient stock is an error requiring rollback, use `Mono.error(...)` instead of silently returning empty.

For read-only methods, `Mono.empty()` can be a valid contract. The business meaning of empty vs. error must be explicitly defined, not guessed from the framework.

### 8.5. Errors After onNext Can Still Cause Commit to Fail

```text
Transactional Mono:
  database statements succeed
  -> application maps to Receipt (onNext may occur)
  -> transaction manager attempts commit
  -> commit errors
  -> Publisher fails
```

Therefore, never emit a "reservation succeeded" notification or call an external API inside `doOnNext(receipt -> ...)` **inside** the transactional chain before completion. For post-commit side effects, use explicit orchestration or a transactional outbox.

## 9. Cancel and Flux: Risk of Unintended Rollbacks

Reactive Streams includes a **cancel** signal when a subscriber wants no more items. In modern Spring reactive transactions (particularly since Spring Framework 5.3), **cancellation is treated as rollback** because once the stream is canceled, the framework cannot be sure all transactional work finished.

### 9.1. The take(1) Trap

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Flux<ReservationDocument> reserveBatch(
        Flux<ReserveCommand> commands) {

    return commands.concatMap(this::reserveOneWithinTransaction);
}
```

Suppose a caller writes:

```java
reservationService.reserveBatch(commands)
    .take(1);
```

`take(1)` normally **cancels upstream** after the first element. If the upstream transaction has not completed yet, cancellation can cause a **rollback**, even though the subscriber received the first `ReservationDocument`. This is very dangerous if the UI assumes receiving one item means data has committed.

**Do not use `Flux.take(1)` on a multi-write transaction treating the first item as confirmation.** If multiple writes must share one transaction, a `Mono<BatchReceipt>` representing full completion is a much clearer contract.

### 9.2. Long-Running Flux Streams Keep Transactions Open Too Long

```text
BEGIN TRANSACTION
    -> Flux emits 1st row
    -> Flux emits 2nd row
    -> ... streams for minutes ...
    -> complete -> COMMIT
```

The longer a transaction stays open, the greater the risk of lock/write conflicts, timeouts, memory/resource pressure, and awkward cancellations. Never wrap an infinite stream, continuously changing results, or a slow file export in a MongoDB multi-document transaction expecting it to scale automatically.

For read-only reporting/exports, evaluate whether a transaction is actually needed or if snapshot reads/consistency policies suffice. For large batch writes, split work into independent transactions with explicit IDs/checkpoints instead of holding one transaction open across hundreds of thousands of items.

### 9.3. Cancellation Is Not onError

`cancel` does not necessarily emit an `onError` to the subscriber, so `doOnError` hooks will not observe cancellations. You can use `doFinally(signalType -> ...)` to record metrics by terminal signal:

```java
return reservationService.reserve(command)
    .doFinally(signal ->
        metrics.recordTermination(signal.name()));
```

`metrics` in this snippet is a hypothetical monitoring service. Do not rely on `doFinally` to manually drive commit/rollback or perform independent database side effects. To verify cancellation, use an integration test with `StepVerifier`/timeouts and re-read the BSON documents.

### 9.4. Timeouts Can Also Trigger Cancellation

```java
reservationService.reserve(command)
    .timeout(java.time.Duration.ofSeconds(2));
```

When the timeout expires, `timeout` can **cancel upstream** and emit a timeout error downstream. The transaction manager handles cancellation/rollback; however, if the timeout or connection loss occurs **during the commit phase**, the client may not know whether the commit actually succeeded. Never treat every timeout as guaranteed proof of rollback.

Align timeouts with transaction/session/network SLAs; when the commit outcome is unknown, rely on operation IDs and reconciliation.

## 10. Ordering Within the Same Session: Avoid Parallel MongoDB Statements

Inside a single MongoDB transaction, operations sharing the same session **must not run concurrently**. This is an important limitation of the MongoDB Driver and reactive transactions.

### 10.1. Do Not Use zip/when to Run Transactional Writes in Parallel

```java
// ANTI-PATTERN: two operations may execute concurrently.
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> writeWrong() {
    return Mono.when(
        template.insert(new AuditDocument("A1")),
        template.insert(new OrderDocument("O1", "TENANT-A", "NEW"))
    );
}
```

`Mono.when` subscribes to multiple sources at the same time. When those sources share a transaction/session, this is not a safe pattern for parallel database operations. It can lead to driver/server errors or unpredictable behavior.

### 10.2. Correct: Chain DB Operations Sequentially

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> writeSequentially() {
    return template.insert(new AuditDocument("A1"))
        .then(template.insert(
            new OrderDocument("O1", "TENANT-A", "NEW")))
        .then();
}
```

`then(...)` ensures the second insert begins only after the first completes. For `Flux`, `concatMap` is appropriate when executing MongoDB writes sequentially; avoid default `flatMap` with concurrency > 1 sharing the same session.

### 10.3. concatMap Does Not Turn a Transaction Into an Unbounded Batch

```java
return Flux.fromIterable(commands)
    .concatMap(cmd -> template.insert(
        new ReservationDocument(
            cmd.operationId(),
            cmd.tenantId(),
            cmd.stockId(),
            cmd.quantity())));
```

The inserts execute sequentially, yet if there are tens of thousands of commands, the transaction can become too long and hit limits. Design batch sizes, checkpoints, and idempotency/outbox per business requirements; do not try to execute a massive migration in one long-lived transaction.

### 10.4. publishOn Is Not a Tool for Parallelizing a Transaction

`publishOn` changes the scheduler for downstream signals and Reactor Context normally propagates across compatible operators, but it **does not make parallel operations safe** inside a transaction. Avoid spawning threads manually, `CompletableFuture.supplyAsync`, or calling `subscribe()` inside a transactional flow when doing so breaks session affinity or executes outside control.

## 11. @Transactional vs. TransactionalOperator: Choosing the Right Boundary

Spring Framework provides `TransactionalOperator` for reactive code. Rather than annotating an entire method, developers can **wrap a specific Publisher in a transaction** via the programmatic API.

### 11.1. Configuring TransactionalOperator

File `ReservationTransactionOperatorConfiguration.java`:

```java
package com.example.shop.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration(proxyBeanMethods = false)
public class ReservationTransactionOperatorConfiguration {

    @Bean("reservationTransactionalOperator")
    TransactionalOperator reservationTransactionalOperator(
            @Qualifier("reactiveMongoTransactionManager")
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
```

`ReactiveMongoTransactionManager` from section 5 is already registered; do not instantiate a new transaction manager per request.

### 11.2. Using the Operator Instead of the Annotation

File `ReservationWithOperatorService.java`:

```java
package com.example.shop.reservation;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ReservationWithOperatorService {

    private final ReactiveMongoTemplate template;
    private final TransactionalOperator operator;

    public ReservationWithOperatorService(
            ReactiveMongoTemplate template,
            @Qualifier("reservationTransactionalOperator")
            TransactionalOperator operator) {
        this.template = template;
        this.operator = operator;
    }

    public Mono<ReservationReceipt> reserve(
            ReserveCommand command) {

        Mono<ReservationReceipt> work = Mono.defer(() -> {
            if (command == null
                    || command.tenantId() == null
                    || command.tenantId().isBlank()
                    || command.operationId() == null
                    || command.operationId().isBlank()
                    || command.stockId() == null
                    || command.stockId().isBlank()
                    || command.quantity() <= 0) {
                return Mono.error(new IllegalArgumentException(
                    "Invalid request"));
            }

            Query query = Query.query(
                Criteria.where("_id").is(command.stockId())
                    .and("tenantId").is(command.tenantId())
                    .and("available").gte(command.quantity()));

            return template.updateFirst(
                    query,
                    new Update().inc(
                        "available", -command.quantity()),
                    StockDocument.class)
                .flatMap(result -> {
                    if (result.getModifiedCount() != 1) {
                        return Mono.error(
                            new InsufficientStockException());
                    }

                    return template.insert(
                        new ReservationDocument(
                            command.operationId(),
                            command.tenantId(),
                            command.stockId(),
                            command.quantity()))
                        .map(saved -> new ReservationReceipt(
                            saved.id(), "RESERVED"));
                });
        });

        return operator.transactional(work);
    }
}
```

The example validates basic fields; production still requires tenant authorization, idempotency, and business limits prior to processing. The key point here is **changing how the transaction boundary is defined**: `operator.transactional(work)` instead of `@Transactional`.

### 11.3. Comparison

| Criterion | `@Transactional` on Publisher Method | `TransactionalOperator` |
| --- | --- | --- |
| Declaration style | Annotation on method API | Wrapping a Publisher in code |
| Applied boundary | Publisher returned by the proxied method | Specific Publisher passed to `transactional(...)` |
| AOP proxy dependency | Yes, in standard proxy-based mode | No proxy required for the operator itself |
| Ease of use for standard services | Yes | Yes, though adds an object/config bean |
| Transaction for only part of a pipeline | Requires splitting into another method/bean | Explicit by choosing what to wrap |
| Session in reactive pipeline | Reactor Context | Reactor Context |
| Automatic exactly-once external side effects | No | No |
| Automatic retry on unknown commit / full body | Not by default | Not by default |

Do not put both on the same workflow just "to be extra safe" without understanding propagation and transaction nesting. That can create nested transactions, join an active transaction unexpectedly, or make boundaries hard to predict depending on configuration.

### 11.4. Wrap Only the Writes; Run Out-of-Transaction Work After Commit

```java
Mono<ReservationReceipt> mongoWork =
    reservationMongoOperations.createReservation(command);

Mono<ReservationReceipt> committed =
    operator.transactional(mongoWork);

return committed.flatMap(receipt ->
    reportingCache.invalidate(receipt.operationId())
        .thenReturn(receipt));
```

This is composition pseudocode in a service with injected `operator`, `reservationMongoOperations`, and `reportingCache`. `invalidate(...)` is placed **after** the transactional Publisher, so it only runs when the transaction completes successfully. If commit fails, the chain emits an error and skips invalidation.

**However:** between a successful commit and invalidation, a process crash can still occur. If an event must be reliably emitted even across crashes, use a **transactional outbox** and idempotent consumers instead of treating post-commit operations as risk-free.

### 11.5. TransactionalOperator.execute and Callbacks With Status

The programmatic API also provides `operator.execute(...)`:

```java
Flux<ReservationReceipt> result =
    operator.execute(transactionStatus ->
        reservationMongoOperations.createReservation(command)
            .flux());
```

This is a conceptual pattern; `reservationMongoOperations` returns a suitable reactive Publisher. `transactionStatus` can be used per Spring API to request an intentional rollback when needed, but do not turn domain failures into silent completions if the caller still expects an error.

For straightforward workflows, `operator.transactional(Mono)` is usually easier to read.

## 12. Transaction Propagation and Nested Calls

Another issue arises when two annotated methods call each other:

```text
OrderService.placeOrder()        @Transactional (reactive)
    |
    +-- ReservationService.reserve()   @Transactional (reactive)
    |
    +-- PaymentRecordService.record()  @Transactional (reactive)
```

If all three use the **same reactive transaction manager/factory** and properly participate in Reactor Context, default `REQUIRED` propagation can join operations into the **same logical transaction**. Never guess solely from annotation names: verify proxy calls, selected managers, and framework version behavior.

### 12.1. REQUIRED Does Not Mean an Independent Transaction Per Method

`@Transactional(propagation = Propagation.REQUIRED)` generally joins an existing transaction if appropriate, or creates a new one if none exists. Therefore, if `reserve()` is called inside `placeOrder()`'s transaction, `reserve()` completing **does not prove it committed independently**.

If these methods share an outer transaction and a subsequent payment write fails, the reservation operations can roll back together with it.

### 12.2. REQUIRES_NEW and NESTED Must Account for MongoDB Support

`REQUIRES_NEW` requests an independent transaction scope when supported by the transaction infrastructure; this may require a separate session/resource and affects visibility of the outer transaction's uncommitted data.

`NESTED` relies on savepoint semantics in some transaction managers; MongoDB multi-document transactions **should not be assumed to have JDBC-equivalent savepoints**. Check propagation support for `ReactiveMongoTransactionManager` and your Spring Data version; do not add `NESTED` simply because the `Propagation.NESTED` enum exists.

### 12.3. Do Not Use a Different Transaction Manager for Half the Pipeline

```text
ReactiveMongoTemplate A ---> ReactiveMongoDatabaseFactory A
                             |
                             +-- ReactiveMongoTransactionManager A

ReactiveMongoTemplate B ---> ReactiveMongoDatabaseFactory B
                             |
                             +-- TransactionManager B or no manager
```

If a method is annotated with manager A yet one branch writes via template B, there is **no guarantee** branch B commits or rolls back with A. The same applies when mixing reactive MongoDB and R2DBC/PostgreSQL in one method: a single `@Transactional` does not become a distributed transaction.

If a workflow must synchronize MongoDB with Kafka/HTTP/RDBMS, consider outbox, saga, or explicit eventual consistency patterns. Never assume every Publisher inside `zip`/`flatMap` forms a cross-system transaction.

### 12.4. readOnly = true Does Not Enforce Read-Only Authorization

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager",
    readOnly = true)
public Flux<OrderDocument> findOrders(...) {
    // ...
}
```

`readOnly` is a transaction hint/specification for the framework that can affect handling, but it **does not replace MongoDB RBAC**. Do not rely on this annotation to block other code from writing to collections. In MongoDB transactions, reading across multiple documents from a secondary is also not automatically allowed simply by setting `readOnly`; verify read preference and transaction support per driver/server.

## 13. Using ReactiveMongoRepository Inside @Transactional

Not every operation has to go through the template. Reactive repositories can participate in the same transaction when using the matching factory, manager, and session:

```java
package com.example.shop.reservation;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReservationRepository
        extends ReactiveMongoRepository<
            ReservationDocument, String> {
}
```

Illustrative service:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserveViaRepository(
        ReserveCommand cmd) {

    return reactiveMongoTemplate.updateFirst(
            stockQuery(cmd),
            stockDecrement(cmd),
            StockDocument.class)
        .flatMap(result -> {
            if (result.getModifiedCount() != 1) {
                return Mono.error(
                    new InsufficientStockException());
            }
            return reservationRepository
                .save(new ReservationDocument(
                    cmd.operationId(),
                    cmd.tenantId(),
                    cmd.stockId(),
                    cmd.quantity()))
                .map(saved -> new ReservationReceipt(
                    saved.id(), "RESERVED"));
        });
}
```

This snippet is extracted from a service with configured `reactiveMongoTemplate`, `reservationRepository`, `stockQuery`/`stockDecrement`, validation, and manager. Key takeaway: **reactive repositories and reactive templates participate in the same transaction when backed by the same factory/context**; a repository does not spin up a separate transaction merely because it is a distinct interface.

### 13.1. save Is Not Always Insert

`ReactiveMongoRepository.save(...)` performs a save (which may insert or update depending on entity/ID/mapping). With idempotency keys, calling `save` alone does not enforce "a reservation may only be created once" semantics.

If business logic requires **create-only**, choose `insert` or a unique conditional create strategy and handle duplicate keys explicitly; do not assume calling `save` on an entity with an existing ID will fail.

In this lesson, `ReservationService` in section 6 uses `template.insert(...)` to express **create-only**. If replaced with repository `save`, re-verify the idempotency contract.

### 13.2. @Version and Optimistic Locking

Spring Data MongoDB supports `@Version` mapping across many compatible save/update paths. Optimistic locking helps detect concurrent updates, yet it does not replace `available >= qty` when deducting stock, nor does it replace a transaction when two documents must commit atomically.

Do not rely solely on a DTO version you read earlier and then issue an unconditional `available` update. Enforce matching conditions in the **MongoDB statement** and inspect matched/modified counts.

## 14. Reactive Transactions and External Side Effects

A side effect like sending an email or calling a third-party payment API **does not roll back** when a MongoDB transaction aborts:

```java
// ANTI-PATTERN: external API called inside the transaction.
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> reserveAndNotify(
        ReserveCommand command) {

    return reactiveMongoTemplate.insert(
            new ReservationDocument(
                command.operationId(),
                command.tenantId(),
                command.stockId(),
                command.quantity()))
        .flatMap(saved -> webClient.post()
            .uri("/external-notify")
            .retrieve()
            .bodyToMono(Void.class));
}
```

This is an illustrative anti-pattern, not a standalone compilable class. The external HTTP request may succeed before MongoDB commits, and then the transaction aborts. If the callback/Publisher retries, HTTP may be called repeatedly. If the remote call is slow, the transaction stays open too long and risks timing out.

### 14.1. Transactional Outbox

A safer design:

```text
Transactional Publisher:
  update stock_items
  insert reservations
  insert outbox(eventId, operationId, payloadRef)
         |
         v
     COMMIT MongoDB
         |
         v
Outbox worker reads committed events
         |
         +-- sends message / HTTP
         +-- marks dispatched with retry and deduplication
```

If the transaction rolls back, neither the reservation nor the outbox event appears. If commit succeeds and the process crashes before sending, the outbox record remains for the worker to process.

Note that an outbox **does not automatically make external delivery exactly-once**: the dispatcher and consumer still need idempotency via `eventId` and handling for cases where sending succeeded but the ACK was lost.

### 14.2. When Outbox Is Unnecessary

If the side effect is only cache invalidation that self-heals and missing one invalidation does not violate invariants, post-commit processing with accepted risk may suffice. Required side effects like issuing invoices, charging payments, and updating external systems require explicit delivery/reconciliation models rather than attaching `doOnSuccess` inside a transactional Publisher.

## 15. Retrying a Transactional Publisher: Resubscribe Is Not Retrying Commit Alone

Reactor provides `retry(...)` and `retryWhen(...)` to re-subscribe to a Publisher upon error. Placed outside a `@Transactional` method returning `Mono`, a retry creates a **new subscription** and therefore a **new transaction attempt**.

This is **not equivalent** to resending `commitTransaction` for the previous transaction. In MongoDB, two error labels matter most:

| Error Label | Meaning | Primary Handling |
| --- | --- | --- |
| `TransientTransactionError` in transactional body | Current attempt hit a transient failure and cannot continue normally | Can retry the **entire transaction** on a new attempt within a budget |
| `UnknownTransactionCommitResult` during commit | Client cannot tell whether commit succeeded | Retry **commit of the same transaction/session**, do not replay body |

### 15.1. Unconditional retryWhen Is Dangerous

```java
// ANTI-PATTERN: never apply blindly to sensitive write transactions.
return reservationService.reserve(command)
    .retryWhen(reactor.util.retry.Retry.max(3));
```

When commit succeeds yet the acknowledgment is lost, the Publisher can emit an error after MongoDB has already persisted the changes. `retryWhen` around the whole method re-subscribes to run a **new business attempt**, risking duplicate reservations or side effects without idempotency.

### 15.2. Retry the Whole Transaction Only After Classifying the Error

When a body failure carries `TransientTransactionError` and the operation is safe to rerun, an orchestration layer can retry the whole transaction within a budget. For `UnknownTransactionCommitResult`, however:

1. Do not use an outer Publisher retry to replace commit retry.
2. While holding the session/transaction identity, handle **commit retry at the transaction boundary** per driver semantics.
3. Once the session is lost or the deadline expires, **reconcile by operation ID** against real persisted state.

With Spring's `ReactiveMongoTransactionManager`, inspect **how commit and exception propagation work** in your active release. `@Transactional` or `TransactionalOperator` **must not be assumed** to act like the MongoDB driver's callback API that automatically retries commits. If your business strictly requires retrying commit on the same session, build a tested session-aware hook/layer rather than slapping `retryWhen` around the publisher.

### 15.3. Classifying Error Labels Without Parsing Error Messages

In Spring Data applications, errors can be translated into Spring `DataAccessException` wrapping `MongoException` in the cause chain. Example helper:

```java
package com.example.shop.reservation;

import com.mongodb.MongoException;

public final class MongoTransactionErrorLabels {
    private MongoTransactionErrorLabels() {}

    public static boolean contains(
            Throwable error, String label) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof MongoException mongo
                    && mongo.hasErrorLabel(label)) {
                return true;
            }
        }
        return false;
    }
}
```

This helper only inspects labels if `MongoException` remains in the cause chain. It does not tell you **whether the error occurred in the body or during commit**, nor can it retry commit without owning the session/transaction identity. Label inspection is only **one part** of a retry strategy.

### 15.4. When Commit Outcome Is Uncertain, Never Say "Failed"

Scenario:

```text
reserve("RES-001")
  -> stock decremented inside transaction
  -> reservation inserted inside transaction
  -> commit sent
  -> MongoDB may have committed
  -> network ACK lost
  -> UnknownTransactionCommitResult
```

Do not conclude "the transaction rolled back" and ask the client to generate a new operation ID. The API can return **`PENDING_CONFIRMATION`** along with the operation ID for reconciliation. Read the ledger/reservation from a source with suitable freshness (typically primary) and check the payload, keeping in mind that **not seeing the record once does not always prove the prior transaction will not commit**.

### 15.5. @Transactional Does Not Provide Idempotency Automatically

In the example, `ReservationDocument.id` is the operation ID, and `_id` has a unique index. When a client retries with the same ID:

- If the earlier attempt committed, the duplicate insert fails and the new transaction rolls back its stock update.
- However, the illustrative service simply propagates the duplicate error; **it is not yet a complete idempotent API**.
- An orchestration layer must compare existing committed state/payload to return the matching receipt or flag a reconciliation/conflict case.
- If a request reuses the same operation ID with a different quantity or stock ID, never treat it as an equivalent retry.

For HTTP/gateway retries, use a stable idempotency key and canonical request fingerprint. Never generate a new reservation ID on every subscription or retry.

## 16. Do Not Call Out-of-Transaction APIs or Mix Imperative and Reactive

The following snippet is a design flaw:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> writeWithBlockingCall() {
    return Mono.fromRunnable(() -> {
        mongoTemplate.save(new AuditDocument("A1"));
    }).then(reactiveMongoTemplate.insert(
        new ReservationDocument(
            "R1", "TENANT-A", "S1", 1))).then();
}
```

Here `mongoTemplate` is the **imperative `MongoTemplate`**. Even though wrapped in a `Mono` to defer execution, it **does not automatically join the MongoDB reactive transaction session**. It can also block threads serving the reactive chain.

**Correct:** use `ReactiveMongoTemplate`/`ReactiveMongoRepository` with a single session/context, or move blocking operations into a separate workflow with an explicit consistency contract. Offloading the blocking call to `Schedulers.boundedElastic()` only mitigates thread starvation; **it does not make it join the reactive transaction**.

### 16.1. Be Careful With WebClient Inside a Transaction

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<ReservationReceipt> reserveAndCharge(
        ReserveCommand cmd) {
    return webClient.post()
        .uri("/payments/charge")
        .retrieve()
        .bodyToMono(ChargeReceipt.class)
        .then(reservationService.reserve(cmd));
}
```

This is an anti-pattern: although `WebClient` is reactive, the remote payment API **is not part of the MongoDB transaction**. It may charge the customer before MongoDB rolls back. Furthermore, if `reservationService.reserve` is another transactional method, propagation/routing can make boundaries even harder to reason about.

Instead, use a payment workflow with idempotency, outbox/saga, `PENDING`/`CONFIRMED` states, and proper compensation/reconciliation. Never fold un-rollbackable network calls into a MongoDB transaction.

### 16.2. Do Not Manually Create Another ClientSession in the Flow

When using `ReactiveMongoTransactionManager`, let Spring Data coordinate the session via Reactor Context. Manually opening a `ClientSession` through the MongoDB driver for a separate branch does not join the template's transaction. Only use manual reactive driver sessions when intentionally managing the entire transaction lifecycle via driver APIs without mixing in a session-owning manager.

### 16.3. Reactive Transactions Do Not Span Kafka or RDBMS Simply by Sharing a Publisher

`Flux`/`Mono` orchestrates async operations; it is not a distributed transaction coordinator. When one Publisher calls MongoDB, Postgres R2DBC, and Kafka:

- The MongoDB manager manages MongoDB sessions for its factory.
- An R2DBC transaction manager manages its separate SQL connection if configured.
- The Kafka producer has its own transactions/acknowledgments.

There is no cross-system atomicity across all three unless the application implements explicit coordination. For multi-resource workflows, outboxes and sagas are far more practical operationally than assuming one annotation can roll back everything.

## 17. Read-Only, Sessions, and Queries Inside Transactions

With reactive MongoDB:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager",
    readOnly = true)
public Flux<StockDocument> listStocks(String tenantId) {
    return reactiveMongoTemplate.find(
        Query.query(Criteria.where("tenantId").is(tenantId)),
        StockDocument.class);
}
```

This is an illustrative method inside a bean with an injected template, not a standalone Java file. Consider whether a **multi-document transaction is truly needed to read a list**. For large reporting queries, use appropriate read concerns, snapshots, or causal consistency instead of holding a transaction open until the entire stream finishes.

### 17.1. Read Preference and Transactions

MongoDB transactions place restrictions on read preferences and sessions; in practice, multi-document transaction operations generally target the primary under supported configurations. Do not pass a `secondaryPreferred` reporting template into a reactive transaction assuming MongoDB will execute transactional reads/writes on a secondary.

### 17.2. Do Not Confuse readOnly Transactions With Constraints

`readOnly=true` does not prevent negative stock across other write paths. `available >= quantity` preconditions, unique `reservationId` indexes, tenant authorization, and MongoDB schema validation are separate mechanisms. Transactions govern atomicity/consistency scope as configured; they do not automatically enforce domain constraints.

## 18. When Should You Avoid @Transactional on a Publisher?

Not every reactive API needs a multi-document transaction:

| Scenario | Should You Use a Transaction? | Reason |
| --- | --- | --- |
| Reading a single document by ID | Usually unnecessary | A single atomic read already has clear semantics |
| Conditional `updateFirst` on one document | Usually no multi-document transaction needed | MongoDB supports atomic single-document updates |
| Deducting stock and creating a reservation across **two documents/collections** atomically | Usually yes | Requires multi-document atomicity |
| A `Flux` API streaming millions of report rows | Usually avoid long transactions | Resource, cancellation, and transaction lifetime issues |
| Importing 100,000 records with checkpoints | Split into smaller batches/transactions as needed | Easier retries and avoids overly long transactions |
| Calling an external payment API and writing to DB | Cannot rely solely on MongoDB transactions | Remote APIs do not participate in commit/rollback |
| Consistent reads across multiple collections | Depends on snapshot/read concern contract | Transactions are a tool, not the default for every read |

If data can be modeled within a single document while satisfying business needs, atomic single-document updates are simpler and faster than multi-document transactions. Do not use transactions as a Band-Aid for an unsuitable schema without evaluating the trade-offs.

## 19. Integration Testing With StepVerifier on a Real Replica Set

A unit test mocking `ReactiveMongoTemplate` verifies that the service called `updateFirst` followed by `insert`, yet **cannot prove** that both commands shared a session/transaction or that the server rolled back the update when the insert failed.

To verify atomicity:

1. Configure a **TEST MongoDB replica set** supporting multi-document transactions, not standalone MongoDB.
2. Provision **collections before the first transaction runs**, especially if server/driver versions restrict implicit collection creation inside transactions.
3. Use `@SpringBootTest` (or a test slice importing the right manager/service) so the transaction proxy is actually created.
4. Seed BSON outside transactions, then invoke the annotated method via the injected bean.
5. Use `StepVerifier.verifyComplete()` or `expectError(...)` to await the terminal signal.
6. **Re-read MongoDB afterward** to verify persisted state rather than only asserting emitted return values.

### 19.1. Test Preparation

The example below uses Java 17+, JUnit 5, Reactor Test, and Spring Boot with reactive MongoDB configuration. Before running, point the test environment/profile to an **isolated test database**, never shared development or production. The test profile must initialize `ReactiveMongoTransactionManager` from section 5.

File `ReservationReactiveTransactionIntegrationTest.java`:

```java
package com.example.shop.reservation;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ReservationReactiveTransactionIntegrationTest {

    @Autowired
    ReactiveMongoTemplate template;

    @Autowired
    ReservationService service;

    // Use ONLY on an isolated test MongoDB database.
    private Mono<Void> ensureCollections() {
        Mono<Void> stockReady =
            template.collectionExists(StockDocument.class)
                .flatMap(exists -> exists
                    ? Mono.<Void>empty()
                    : template
                        .createCollection(StockDocument.class)
                        .then());

        Mono<Void> reservationReady =
            template.collectionExists(ReservationDocument.class)
                .flatMap(exists -> exists
                    ? Mono.<Void>empty()
                    : template
                        .createCollection(ReservationDocument.class)
                        .then());

        return stockReady.then(reservationReady);
    }

    private static Query byId(String id) {
        return Query.query(Criteria.where("_id").is(id));
    }

    private Mono<Void> cleanup(String stockId, String operationId) {
        return template.remove(
                byId(operationId), ReservationDocument.class)
            .then(template.remove(
                byId(stockId), StockDocument.class))
            .then();
    }

    @Test
    void successCommitsStockAndReservationTogether() {
        String suffix = UUID.randomUUID().toString();
        String stockId = "STOCK-" + suffix;
        String operationId = "RES-" + suffix;

        try {
            StepVerifier.create(
                    ensureCollections().then(
                        template.insert(new StockDocument(
                            stockId, "TENANT-TEST", 10L))))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(service.reserve(
                    new ReserveCommand(
                        "TENANT-TEST", operationId, stockId, 3)))
                .assertNext(receipt -> {
                    assertThat(receipt.operationId())
                        .isEqualTo(operationId);
                    assertThat(receipt.state())
                        .isEqualTo("RESERVED");
                })
                .verifyComplete();

            StepVerifier.create(
                    template.findById(
                        stockId, StockDocument.class))
                .assertNext(stock ->
                    assertThat(stock.available()).isEqualTo(7L))
                .verifyComplete();

            StepVerifier.create(
                    template.findById(
                        operationId, ReservationDocument.class))
                .assertNext(reservation -> {
                    assertThat(reservation.stockId())
                        .isEqualTo(stockId);
                    assertThat(reservation.quantity())
                        .isEqualTo(3L);
                })
                .verifyComplete();
        } finally {
            StepVerifier.create(cleanup(stockId, operationId))
                .verifyComplete();
        }
    }

    @Test
    void duplicateReservationRollsBackEarlierStockUpdate() {
        String suffix = UUID.randomUUID().toString();
        String stockId = "STOCK-" + suffix;
        String operationId = "RES-" + suffix;

        try {
            StepVerifier.create(
                    ensureCollections()
                        .then(template.insert(new StockDocument(
                            stockId, "TENANT-TEST", 10L)))
                        .then(template.insert(
                            new ReservationDocument(
                                operationId, "TENANT-TEST",
                                stockId, 1L))))
                .expectNextCount(1)
                .verifyComplete();

            // Stock update runs first; insert fails with duplicate _id.
            StepVerifier.create(service.reserve(
                    new ReserveCommand(
                        "TENANT-TEST", operationId, stockId, 3)))
                .expectError()
                .verify();

            // If transaction works properly, stock update rolled back.
            StepVerifier.create(
                    template.findById(
                        stockId, StockDocument.class))
                .assertNext(stock ->
                    assertThat(stock.available())
                        .isEqualTo(10L))
                .verifyComplete();

            // Existing reservation remains 1, not overwritten.
            StepVerifier.create(
                    template.findById(
                        operationId, ReservationDocument.class))
                .assertNext(reservation ->
                    assertThat(reservation.quantity())
                        .isEqualTo(1L))
                .verifyComplete();
        } finally {
            StepVerifier.create(cleanup(stockId, operationId))
                .verifyComplete();
        }
    }

    @Test
    void insufficientStockDoesNotCreateReservation() {
        String suffix = UUID.randomUUID().toString();
        String stockId = "STOCK-" + suffix;
        String operationId = "RES-" + suffix;

        try {
            StepVerifier.create(
                    ensureCollections().then(
                        template.insert(new StockDocument(
                            stockId, "TENANT-TEST", 1L))))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(service.reserve(
                    new ReserveCommand(
                        "TENANT-TEST", operationId, stockId, 3)))
                .expectError(InsufficientStockException.class)
                .verify();

            StepVerifier.create(
                    template.findById(
                        stockId, StockDocument.class))
                .assertNext(stock ->
                    assertThat(stock.available())
                        .isEqualTo(1L))
                .verifyComplete();

            StepVerifier.create(
                    template.findById(
                        operationId, ReservationDocument.class))
                .verifyComplete(); // Mono.empty: no reservation created.
        } finally {
            StepVerifier.create(cleanup(stockId, operationId))
                .verifyComplete();
        }
    }
}
```

### 19.2. Warnings When Running Tests

The tests insert and delete **against the database configured by Spring**. Apply profiles and credentials exclusively for an **isolated test MongoDB instance**, provision a replica set with session support, and ensure no other application shares that test database. Cleanup deletes **only by randomized test IDs**, never calling `dropDatabase` or `deleteMany({})` on shared environments.

The `ensureCollections()` helper is kept simple for learning; if multiple tests run concurrently against a database without pre-existing collections, check-then-create can race. In real CI pipelines, create collections via migrations/test fixtures beforehand or use a dedicated database per job.

`@SpringBootTest` provides a valid integration test only if:

- The service is component-scanned by Spring and invoked through its transaction proxy.
- The reactive manager is registered and repositories/templates share its factory.
- The test connection actually targets a transaction-capable MongoDB replica set.
- Transactions are not disabled by another test configuration.

If a test runs against standalone MongoDB and fails with `Transaction numbers are only allowed on a replica set member or mongos`, that is a **topology issue**, not something fixed by adding `retryWhen`.

### 19.3. What These Tests Prove and What They Do Not

| Test | Proves | Does Not Prove |
| --- | --- | --- |
| Success | Both writes coexist after completion | Every network commit failure scenario succeeds |
| Duplicate rollback | Stock does not decrease despite reservation insert error | Idempotent HTTP API automatically returns prior receipt |
| Insufficient stock | Neither stock nor reservation changes when stock is low | Concurrent contention is automatically retried |

To verify behavior under **cancellation**, **failover**, `TransientTransactionError`, or `UnknownTransactionCommitResult`, add dedicated controlled tests. Do not assume the three tests above cover transaction retries.

## 20. Testing Cancellation, Error Recovery, and Concurrency

### 20.1. Testing Cancellation Behavior on Your Spring Version

Create a test service that intentionally emits multiple documents inside one transaction and cancels upstream after the first item:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Flux<ReservationDocument> reserveTwo(
        ReservationDocument a,
        ReservationDocument b) {

    return Flux.just(a, b)
        .concatMap(template::insert);
}
```

Caller:

```java
StepVerifier.create(service.reserveTwo(a, b).take(1))
    .expectNextCount(1)
    .verifyComplete();
```

**Do not treat `verifyComplete` on a `take(1)` Publisher as proof that the transaction committed.** Under reactive transaction cancellation rollback semantics, upstream can be canceled after the first item and the transaction rolled back. Re-read MongoDB after cleanup to confirm which documents were actually persisted. Do not assert exact timing behavior without controlling cancellation and how `TransactionalOperator` handles it in your specific Spring release.

### 20.2. Testing Swallowed Errors With onErrorResume

Write a test service variant:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<String> wrongRecoveringMethod() {
    return template.updateFirst(query, update, StockDocument.class)
        .then(Mono.<String>error(
            new IllegalStateException("Failure after update")))
        .onErrorResume(ex -> Mono.just("RECOVERED"));
}
```

Here `query`/`update` are variables constructed in scope. Inspect stock after completion: if the update matched and no commit error occurred, the transaction may have **committed the update** because the final signal was success. Then fix the method to propagate the error and verify that stock rolls back.

This is an **anti-pattern demonstration test**, never code for production.

### 20.3. Testing Concurrency and Parallel Statement Limits

Do not run a lucky parallel test and conclude "`Mono.when` worked a few times so it must be safe." MongoDB transactions do not support arbitrary parallel operations on the same session; keep transactions sequential via `then`/`concatMap` and review data flows/race risks in code reviews.

When **multiple distinct transactions** update the same stock concurrently, the server can raise write conflicts; the application must classify transaction errors and perform bounded retries per business semantics. Never add an infinite retry loop just to make a test pass.

### 20.4. Testing Session/Factory Mismatches

In an application with two `ReactiveMongoTemplate` beans pointing to two factories, write a test writing to two collections via the two templates under **one** `@Transactional`. Verify that you **must not assume** both writes join the same transaction. The goal of the test is to catch misconfiguration, not to turn two independent MongoClients into a distributed transaction.

## 21. Troubleshooting When @Transactional Does Not Work

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| Method returning `Mono` is called yet MongoDB has no record | Not subscribed | Return Publisher from WebFlux or use `StepVerifier.verifyComplete()` |
| Only one of two writes rolls back | One operation left the reactive chain or used a different factory/client | Look for internal `subscribe()`, blocking MongoTemplate, wrong `@Qualifier` bean |
| `@Transactional` is present yet method is not atomic | Missing reactive manager/proxy, or self-invocation | Verify manager bean, AOP interception, and integration tests |
| Transaction unsupported / transaction numbers error | Connected to standalone or unsupported topology | Use a transaction-capable replica set/sharded cluster |
| Transaction fails due to read preference | Secondary routing incompatible with transactions | Inspect client/factory read preference and transaction options |
| Method errors internally yet stock still decrements | `onErrorResume` turned error into normal completion | Propagate unchecked errors to the transactional boundary |
| Publisher emitted receipt yet commit is uncertain | Side effect sent in `doOnNext` before terminal completion | Confirm only after completion; use outbox when needed |
| `take(1)` returns one item yet DB has no writes | Upstream cancel triggered transaction rollback | Avoid canceling transactional `Flux` before completion; re-read DB |
| `Mono.when`/`zip` triggers driver session/transaction error | DB statements ran in parallel on the same transaction | Use sequential `then` or `concatMap` |
| `retryWhen` re-executes reservations | Re-subscribed entire Publisher, possibly after unknown commit | Classify TTE/UTCR; add idempotency and reconciliation |
| Service has two managers and picks the wrong one | Imperative and reactive managers confused | Specify `transactionManager="reactiveMongoTransactionManager"` |
| `save` does not fail even though reservation ID exists | `save` may update rather than enforce create-only | Use `insert` or create-only unique logic matching contract |
| Reactive app blocks/times out unexpectedly | Calling blocking `MongoTemplate` on the event loop | Use reactive driver/template; never mix blocking MongoDB |
| Transaction stays open too long | Unbounded `Flux`, waiting on network/external services | Shorten transactions; separate side effects and batch work |
| Mock tests pass yet production rollback fails | Mocks do not verify session/server semantics | Run real tests on a MongoDB replica set and inspect BSON |
| Returned "failed" for an operation that committed | Commit ACK lost; client retried whole workflow | Reconcile by operation ID; do not treat timeout as guaranteed abort |

### 21.1. Observing Reactor Context Safely

To debug propagation, you can use `Mono.deferContextual(...)`:

```java
return Mono.deferContextual(contextView -> {
    diagnostics.recordContextPresent(
        !contextView.isEmpty());
    return reactiveMongoTemplate.findById(
        id, StockDocument.class);
});
```

This snippet assumes `diagnostics` and `id` are in scope. **A non-empty Reactor Context does not prove a transaction exists**; many libraries store tracing or security state in context. Do not read Spring's internal transaction keys and depend on unpublished structures as stable APIs.

A far better check is an integration test that performs a write followed by an error, then reads back to verify **everything rolled back**. Context logging is only a secondary signal.

### 21.2. Monitoring Transaction Lifecycle

Useful metrics:

- `reactive_tx_started_total`, `reactive_tx_committed_total`, `reactive_tx_rolled_back_total`.
- `reactive_tx_cancelled_total` distinguishing HTTP client disconnects, timeouts, and `take`.
- `reactive_tx_duration_seconds`, active transaction count, write conflict rate.
- `mongo_tx_commit_unknown_total` and reconciliation backlog by operation type.
- Server selection wait time and commit latency.
- Number of MongoDB commands running outside a transaction when expected inside one (via tracing/tests/command monitoring).

Never attach user IDs or operation IDs as **high-cardinality metric labels**. For controlled logs/traces, use safe correlation IDs; never log raw session identifiers, tokens, or sensitive data.

### 21.3. Do Not Enable Secret-Exposing Debug Logs

Driver/MongoDB logs can expose collection names, queries, or parameter values depending on configuration. When investigating transactions, enforce redaction, access restrictions, and retention policies. Never turn on full MongoDB traffic debug logging in production and accidentally persist sensitive payloads.

## 22. Evaluating Performance of Reactive Transactions

Reactive execution helps applications use threads efficiently with non-blocking I/O, yet **it does not make MongoDB transactions execute faster on the server**. Operations are still processed under server transaction semantics and incur snapshot, logging, replication, and commit costs.

### 22.1. Comparing Write Strategies

| Problem | Typical Appropriate Approach |
| --- | --- |
| Conditional update of one stock record | Single-document atomic update; transaction not necessarily needed |
| Updating stock and inserting reservation atomically | Short reactive transaction |
| Writing thousands of independent events | Batch writes with checkpoints/idempotency; consider bulk writes |
| Publishing broker events after commit | Outbox and dispatcher; keep broker calls out of transaction |
| Flux report over millions of documents | Paged/streaming queries with proper read consistency; avoid long transactions |

### 22.2. Factors to Measure

1. Session/transaction startup time and number of inner operations.
2. Commit latency under the chosen write concern.
3. Write-conflict rate and whole-transaction retry count.
4. Cancellation rate from client disconnects.
5. Memory/backpressure behavior of long `Flux` streams.
6. Document size and indexes supporting conditional updates.
7. Connection pool saturation and server selection timeouts.
8. Rate of unknown commit outcomes and reconciliation duration.

Do not "optimize" by adding `parallel()` or `flatMap(..., concurrency=16)` to statements sharing **one transaction session**. For DB transactions, proper ordering and safe retryability matter far more than maximizing concurrency inside a single transaction.

### 22.3. Conditional Updates Need Proper Indexes

If stock is looked up by `_id`, MongoDB already has the `_id` index. When using a different business key:

```javascript
db.stock_items.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_tenant_sku" }
)
```

This index speeds up tenant+sku lookups/conditional updates while enforcing business key uniqueness. It **does not** replace a transaction across two documents, nor does it handle retries or unknown commits.

## 23. Pre-Merge Code Checklist

1. **Method contract:** transactional methods return `Mono<T>`/`Flux<T>` or a supported Publisher.
2. **Reactive manager:** `ReactiveMongoTransactionManager` uses the right factory; not confused with the imperative manager.
3. **Proxy:** calls pass through the Spring bean proxy; no self-invocation.
4. **Subscription:** the Publisher is subscribed to by the controller/caller/test, never abandoned.
5. **No detachment:** no `subscribe()` inside transactional business methods.
6. **No blocking:** no `block()`, blocking `MongoTemplate`, or blocking external APIs in reactive flows.
7. **Shared factory:** repositories and templates share the same Reactor Context/session.
8. **Sequential:** DB statements inside a transaction are composed sequentially with `then`/`flatMap`/`concatMap`.
9. **No swallowed errors:** domain failures reach the transaction boundary to trigger rollback.
10. **Checked error rules:** if checked exceptions must roll back, `rollbackFor` or unchecked domain exceptions are configured.
11. **Cancellation:** impact of `take`, timeouts, disconnects, and long `Flux` streams is understood.
12. **Receipts after commit:** never emit externally visible "success" before terminal completion.
13. **Idempotency:** the same operation ID is reused across HTTP retries and intentional resubscriptions.
14. **No blind retries:** distinguish body TTE from commit UTCR; do not `retryWhen` all errors.
15. **Outbox:** external side effects needing durable delivery stay outside MongoDB transaction callbacks.
16. **Read preference:** transactions are not routed to unsupported secondaries.
17. **Transaction scope:** never hold transactions open over infinite streams or remote API waits.
18. **Real tests:** MongoDB replica set tests verify persisted data after both commit and rollback.
19. **Edge-case tests:** duplicate key, insufficient stock, cancellation, failover, concurrent writers, and unknown commits.
20. **Observability:** logs/metrics distinguish started/committed/rolledback/cancelled/unknown states.

## 24. Practice Exercises

A room booking application has `rooms` and `bookings` collections. The API receives a stable `bookingId`, `roomId`, `tenantId`, and date range to reserve.

### Exercise 1 — Distinguishing Eager and Lazy

Consider:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<Booking> book(BookingRequest request) {
    audit.log("method invoked");
    return reactiveMongoTemplate.insert(
        new Booking(request.bookingId(), request.roomId()));
}
```

Explain:

1. When can `audit.log(...)` execute?
2. When does the MongoDB insert normally execute?
3. What happens if the caller stores the Publisher in a variable without subscribing?
4. If two subscribers subscribe to the cold Publisher, how many booking attempts can occur?
5. Fix the code using `Mono.defer` when computation must be deferred while keeping `bookingId` stable.

### Exercise 2 — Writing a Transactional Service

Requirements within **one** reactive MongoDB transaction:

- Conditionally update `rooms.available >= requestedRooms`, decrementing available rooms.
- Insert into `bookings` with `bookingId` from the request.
- Return `Mono<BookingReceipt>` on success.
- If rooms are insufficient, emit an unchecked error; if the booking insert hits a duplicate, roll back the room update.

Implement with both:

1. `@Transactional` on a method returning `Mono<BookingReceipt>`.
2. `TransactionalOperator.transactional(work)`.

Do not use `subscribe()`/`block()`, do not run the two MongoDB statements via `Mono.when`, and do not send emails inside the transaction.

### Exercise 3 — Fixing Anti-Patterns

Code:

```java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager")
public Mono<BookingReceipt> bookWrong(BookingRequest req) {
    reactiveMongoTemplate.insert(
        new AuditEvent("start")).subscribe();

    return Mono.when(
        decrementAvailableRooms(req),
        insertBooking(req)
    )
    .thenReturn(new BookingReceipt(req.bookingId()))
    .onErrorResume(ex ->
        Mono.just(new BookingReceipt("ignored-error")));
}
```

Identify at least **four bugs**:

- Detached subscribe for the audit insert.
- Two concurrent DB operations in the same transaction.
- `onErrorResume` swallows errors, allowing partial updates to commit.
- Returning an "ignored-error" receipt despite business failure.
- Missing retry/idempotency and duplicate booking ID handling.

Fix using sequential `then`/`flatMap`, error propagation, an idempotency key, and an outbox if durable audit/events are required.

### Exercise 4 — Cancellation and WebFlux

Write a `@Transactional` method returning `Flux<Booking>` that creates three bookings sequentially. Then compare:

```java
StepVerifier.create(service.bookThree(requests))
    .expectNextCount(3)
    .verifyComplete();
```

with:

```java
StepVerifier.create(service.bookThree(requests).take(1))
    .expectNextCount(1)
    .verifyComplete();
```

Read MongoDB back after each test. Explain why receiving one element must not be taken as proof that the transaction committed. Redesign the API as `Mono<BatchBookingReceipt>` when all-or-nothing semantics across all three bookings are required.

### Exercise 5 — Retries and Unknown Commit Outcomes

A booking command sends commit and loses the connection:

```text
body writes complete
commitTransaction sent
acknowledgment lost
UnknownTransactionCommitResult
```

Explain why the following is dangerous:

```java
service.book(request)
    .retryWhen(Retry.max(5));
```

Propose how to use `bookingId`/unique key, commit retry in the right transaction/session when supported by the driver/manager, and reconciliation with `PENDING_CONFIRMATION` state when the outcome cannot be determined. Contrast this with `TransientTransactionError` in the body, where retrying the whole transaction on a new attempt is valid if idempotent and within budget.

### Exercise 6 — Integration Testing

Set up an isolated replica set test environment and write `StepVerifier` tests verifying:

1. Successful booking: room count decreases and booking document exists.
2. Duplicate booking ID: room count does not decrease further.
3. Insufficient rooms: no booking is created.
4. Misplaced `onErrorResume` inside the method can commit an unwanted update.
5. `take(1)`/cancellation is handled per actual transaction semantics.
6. Self-invoked methods lack proxy transaction guarantees.
7. Two templates bound to two database factories do not automatically share a transaction.
8. Unknown commit errors require dedicated fault-injection tests rather than relying on arbitrary timeouts.

Never run failpoints or `dropDatabase` in production; test only when the cluster and permissions are strictly controlled.

## 25. References

- Spring Framework — [Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, interception, and rollback rules.
- Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionalOperator` and reactive transaction scope.
- Spring Framework — [Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): controlling rollback for unchecked/checked exceptions.
- Spring Data MongoDB — [Client Session & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `ReactiveMongoTransactionManager`, sessions, and transactions.
- Spring Data MongoDB — [Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `ReactiveMongoTemplate` and Spring Data mapping.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): subscription, Reactor Context, error handling, cancellation, and backpressure.
- Project Reactor Test — [StepVerifier](https://projectreactor.io/docs/test/release/reference/): testing Publishers through terminal signals.
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/): topology, atomicity, limits, and sessions.
- MongoDB Java Reactive Streams Driver — [Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write-operations/transactions/): transaction sessions and driver behavior.

## Key Takeaways

**`@Transactional` on methods returning `Mono` or `Flux` establishes a transaction scope when the Publisher is subscribed to and is managed by Spring via Reactor Context, not when the method merely assembles the pipeline.** `ReactiveMongoTemplate`/repository operations must stay in the **same reactive chain, same factory/session, and execute sequentially**. Completion instructs the manager to commit; rollback-triggering errors or cancellation can trigger rollback. Avoid internal `subscribe()`, `block()`, self-invocation, `Mono.when` for DB statements within the same transaction, and `onErrorResume` swallowing errors. Never use unconditional `retryWhen` to replay full business logic when commit outcomes are unknown. Production readiness requires a replica set, `StepVerifier` tests that re-read BSON after commit/rollback, idempotency keys, an outbox for external side effects, and monitoring for errors, cancellations, and unknown commits.
