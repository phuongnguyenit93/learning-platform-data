# Testing Concurrency Conflicts, Optimistic Locking, and Idempotency

## 1. Why Test Concurrency?

Spring Data Relational R2DBC applications frequently process multiple requests simultaneously. Each request may read and mutate the same record, even when every request's code runs properly when tested in isolation.

A simple example is updating inventory stock:

- Two requests both read the remaining quantity as 5.
- Request A sets the quantity to 4.
- Request B sets the quantity to 3 based on the stale read.
- If both writes are accepted without appropriate control, A's change can be overwritten.

Another problem arises when a client resends the same request due to a timeout or retry. For instance, the client calls an order creation API, the server saves successfully, but the response is lost in transit. Not knowing the request succeeded, the client sends it again. If the server treats it as a new request, the application can create two orders or charge twice.

Three concepts to distinguish:

- **Concurrency conflict:** multiple operations competing on the same data at the same time.
- **Optimistic locking:** detecting that a record changed since it was read, usually using a version property.
- **Idempotency:** ensuring that resending the same business intent does not create unintended extra effects.

Tests must prove all three behaviors at both the database and service layers. Pure Java unit tests cannot prove that a version-conditional UPDATE executes properly through the driver, how unique constraints guard idempotency keys, or how two real transactions compete on separate connections.

## 2. Distinguishing Optimistic Locking from Idempotency

These two mechanisms solve different problems.

| Mechanism | Question answered | Typical protection mechanism |
|---|---|---|
| Optimistic locking | Is the data I am editing still the version I read? | Version column and version predicate in UPDATE/DELETE |
| Idempotency | Is this a retry of the same business request? | Idempotency key with unique constraint and stored processed result |
| Database constraint | Does the data violate an invariant enforced by the database? | UNIQUE, CHECK, NOT NULL, FOREIGN KEY |
| Transaction | Which database changes must commit or roll back together? | Reactive transaction manager |

Examples:

- Two users edit an order's status from two different screens: optimistic locking catches the stale edit.
- A client resends POST /orders with the same idempotency key: idempotency returns the result of the earlier execution.
- Two different requests submit the same order code: a unique constraint enforces uniqueness.
- Updating order, inventory, and outbox must succeed together: a transaction enforces atomicity within the same database.

Do not substitute one mechanism for all others. A single API may require transactions, @Version, unique constraints, and idempotency keys together.

## 3. Preparing Versioned Data

Spring Data Relational supports optimistic locking via the @Version annotation.

Entity example:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Corresponding schema:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

When an entity is saved through Spring Data's mapping infrastructure, the framework uses the version to detect concurrent updates. Conceptually, the update operation is equivalent to:

~~~sql
UPDATE orders
SET status = :status,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
~~~

If no row matches the expected ID and version, Spring Data can emit OptimisticLockingFailureException.

The initial version value and exact data type must align with Spring Data configuration and schema. Use the entity returned from save because that object carries the updated version after a successful operation. Do not increment the version manually before calling save.

## 4. Testing Optimistic Locking with Two Stale Entity Snapshots

This is the most basic test to prove optimistic locking.

### 4.1. Reading the Same Version Twice

The test creates two independent objects from the same database state:

~~~java
@Test
void shouldRejectSecondSaveFromStaleEntity() {
    Mono<Void> test = orderRepository.findById(orderId)
        .flatMap(firstRead ->
            orderRepository.findById(orderId)
                .flatMap(secondRead -> {
                    assertThat(firstRead.getVersion())
                        .isEqualTo(secondRead.getVersion());

                    firstRead.setStatus("PAID");
                    secondRead.setStatus("CANCELLED");

                    return orderRepository.save(firstRead)
                        .then(orderRepository.save(secondRead))
                        .then();
                })
        );

    StepVerifier.create(test)
        .expectError(OptimisticLockingFailureException.class)
        .verify();
}
~~~

Test sequence:

1. Read the entity the first time.
2. Read the entity a second time before any write occurs.
3. Verify both reads carry the same version.
4. Save the first snapshot, incrementing the version in the database.
5. Save the second snapshot, which still holds the stale version.
6. Verify the second save emits an optimistic locking error.

This test verifies stale-entity behavior deterministically. It is useful and fast, though not yet a true concurrent race: the two saves execute sequentially.

### 4.2. Verifying the Final Data

Do not check only the exception. Read back from the database to verify:

- The status from the winning save is preserved.
- Version incremented only by the number of successful writes.
- The record was not deleted or partially overwritten.

Example:

~~~java
StepVerifier.create(orderRepository.findById(orderId))
    .assertNext(saved -> {
        assertThat(saved.getStatus()).isEqualTo("PAID");
        assertThat(saved.getVersion()).isEqualTo(initialVersion + 1);
    })
    .verifyComplete();
~~~

The test must ensure initialVersion is the version saved before the scenario runs. Do not hard-code version values if the project's insert mechanism or fixtures follow a different initialization convention.

## 5. Testing a Real Race Condition with Two Transactions

A two-snapshot test proves stale writes are rejected. To verify two genuinely competing requests, let two separate transactions read the same version before either is allowed to write.

Never use Thread.sleep to try to force a race. Sleep depends on machine speed, CI load, and schedulers, making tests flaky.

Use a reactive barrier to synchronize the two publishers.

### 5.1. Preconditions for the Test

A reliable race test requires:

- Two independent subscriptions.
- Two independent transactions.
- Two available connections in the pool.
- Both transactions finish reading the same version before the barrier opens.
- Both proceed to save once the barrier signals.
- The test must not be wrapped in an outer transaction sharing a single connection.
- Results are materialized so one error does not cancel the other publisher before results are collected.

If the connection pool allows only one connection, the first transaction can hold that connection while waiting at the barrier and the second transaction cannot read to reach the barrier. The test will deadlock. Configure a pool with at least two connections for this scenario.

### 5.2. Non-Blocking Barrier Example

Use Reactor Sinks to wait until both transactions finish reading:

~~~java
private Mono<Order> updateAfterBothReads(
        Long orderId,
        String status,
        Sinks.One<Void> release,
        AtomicInteger arrivals) {

    Mono<Order> work = orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(orderId)
        ))
        .flatMap(order -> {
            if (arrivals.incrementAndGet() == 2) {
                release.tryEmitEmpty();
            }

            return release.asMono()
                .then(Mono.defer(() -> {
                    order.setStatus(status);
                    return orderRepository.save(order);
                }));
        });

    return transactionalOperator.transactional(work);
}
~~~

Each call to updateAfterBothReads builds a separate transactional publisher. Both transactions read the entity, then wait on the same Sinks.One. When the second transaction reaches the barrier, the sink signals and both proceed.

Test example:

~~~java
@Test
void onlyOneConcurrentUpdateCanSaveTheSameVersion() {
    Sinks.One<Void> release = Sinks.one();
    AtomicInteger arrivals = new AtomicInteger();

    Mono<Signal<Order>> first =
        updateAfterBothReads(
            orderId, "PAID", release, arrivals
        ).materialize();

    Mono<Signal<Order>> second =
        updateAfterBothReads(
            orderId, "CANCELLED", release, arrivals
        ).materialize();

    StepVerifier.create(Mono.zip(first, second))
        .assertNext(result -> {
            List<Signal<Order>> signals =
                List.of(result.getT1(), result.getT2());

            long successes = signals.stream()
                .filter(Signal::isOnNext)
                .count();

            long failures = signals.stream()
                .filter(Signal::isOnError)
                .count();

            assertThat(successes).isEqualTo(1);
            assertThat(failures).isEqualTo(1);

            Throwable error = signals.stream()
                .filter(Signal::isOnError)
                .findFirst()
                .orElseThrow()
                .getThrowable();

            assertThat(Exceptions.unwrap(error))
                .isInstanceOf(OptimisticLockingFailureException.class);
        })
        .verifyComplete();
}
~~~

This illustrative snippet requires importing relevant types such as Signal, Sinks, AtomicInteger, List, Exceptions, and TransactionalOperator. Replace repository, entity, and exception names per your project.

Materialize converts onNext/onError signals into Signal values. Thus Mono.zip can wait for both outcomes instead of terminating immediately when one publisher emits an error.

### 5.3. Verifying State After the Race

Once both signals are collected, read the order again in a fresh query:

~~~java
StepVerifier.create(orderRepository.findById(orderId))
    .assertNext(saved -> {
        assertThat(saved.getVersion()).isEqualTo(initialVersion + 1);
        assertThat(List.of("PAID", "CANCELLED"))
            .contains(saved.getStatus());
    })
    .verifyComplete();
~~~

Only one update succeeds, so the version increments once. The final status belongs to the winning request; tests should not assume beforehand which request wins because scheduling order can vary.

Do not annotate the test method itself with @Transactional if doing so merges both service calls into one shared test transaction. The goal is two independent transactions mimicking two real requests. Read data back after both transactions finish.

## 6. Testing Conditional Updates to Enforce Invariants

Optimistic locking fits versioned entity updates. Some invariants can be enforced directly by a single conditional SQL statement.

Example deducting stock:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
~~~

If rowsUpdated equals 1, stock reservation succeeded. If 0, either stock is insufficient or no matching product exists.

Service example:

~~~java
public Mono<Void> reserve(Long productId, int quantity) {
    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity
            WHERE product_id = :productId
              AND available >= :quantity
            """)
        .bind("quantity", quantity)
        .bind("productId", productId)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.empty();
            }

            return Mono.error(
                new InsufficientInventoryException(productId)
            );
        });
}
~~~

This is an atomic database operation: the predicate and subtraction occur in the same UPDATE statement. Two competing requests cannot both deduct if their combined quantity exceeds available inventory.

When writing custom SQL like this, the application must manage any version predicate manually if optimistic locking is also needed. @Version does not automatically inject predicates into arbitrary DatabaseClient SQL.

### 6.1. Testing Two Concurrent Stock Reservations

Suppose initial inventory is 5. Two requests each reserve 4:

- At most one request can update successfully.
- The other request receives rowsUpdated equal to 0 once the predicate no longer holds.
- Final inventory is non-negative.
- Total reserved quantity does not exceed 5.

The test can run two independent publishers:

~~~java
Mono<Signal<Void>> first =
    inventoryService.reserve(productId, 4).materialize();

Mono<Signal<Void>> second =
    inventoryService.reserve(productId, 4).materialize();

StepVerifier.create(Mono.zip(first, second))
    .assertNext(pair -> {
        List<Signal<Void>> signals =
            List.of(pair.getT1(), pair.getT2());

        assertThat(signals.stream().filter(Signal::isOnComplete).count())
            .isEqualTo(1);

        assertThat(signals.stream().filter(Signal::isOnError).count())
            .isEqualTo(1);
    })
    .verifyComplete();
~~~

Then read inventory and verify available equals 1. Exact structure depends on the service's return type and how rowsUpdated is mapped.

## 7. Idempotency in APIs

### 7.1. The Problem of Resubmitted Requests

A request can be resent due to:

- Client timeout after the server already succeeded.
- Gateway retry when no response was received.
- Users clicking a button multiple times.
- A message broker redelivering a message before consumer acknowledgment.
- A worker restarting after completing partial work.

If every submission creates a new order, the system is not idempotent.

An idempotency key represents a single business intent. The client creates a key for the initial attempt and resends that exact key when retrying.

Request example:

~~~http
POST /orders
Idempotency-Key: 2f4b2b9a-7a70-4b3d-91b0-8d4d25a63f02
Content-Type: application/json
~~~

If the client resends the same request with the same key, the server recognizes the retry and returns the previously recorded outcome instead of creating a second order.

### 7.2. Idempotency Key Storage Table

A simple schema:

~~~sql
CREATE TABLE idempotency_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    client_id VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(150) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    resource_id BIGINT,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uq_idempotency_client_key
        UNIQUE (client_id, idempotency_key)
);
~~~

The unique constraint on client_id and idempotency_key is the decisive safeguard when two requests with the same key arrive concurrently.

Typical field meanings:

- client_id: caller or tenant scope.
- idempotency_key: identifier for the logical operation.
- request_hash: payload fingerprint to detect same key with differing contents.
- status: states such as IN_PROGRESS, COMPLETED, or FAILED.
- resource_id: ID of the created order or resource.
- response_body: saved result to replay if the API replays responses.
- created_at/completed_at: start and completion timestamps.

Do not rely solely on checking the key with SELECT before INSERT. Two requests can both SELECT and both observe the key does not exist yet. A unique constraint must guard the race in the database.

### 7.3. Same Key with Different Payload

If a client reuses an idempotency key with a different payload, do not silently return the old payload's result or process the new payload as a brand new request.

Compare request_hash:

- Same key, same hash, already COMPLETED: return the prior result.
- Same key, same hash, currently IN_PROGRESS: return an in-progress status or let the client retry per API contract.
- Same key, different hash: return a conflict or invalid request error per API contract.
- Key does not exist yet: attempt to claim the key and execute business logic.

The hash should be computed from a canonical request representation covering all business-significant fields. Do not hash raw JSON strings if property order or formatting can vary while logical content stays identical.

## 8. Handling Two Requests with the Same Idempotency Key

### 8.1. Do Not Use SELECT Then INSERT as a Uniqueness Mechanism

Error-prone pattern:

~~~java
return idempotencyRepository.findByKey(key)
    .flatMap(existing -> Mono.just(existing.getResponse()))
    .switchIfEmpty(
        createOrder(command)
            .flatMap(order -> idempotencyRepository.save(
                new IdempotencyRecord(key, order.getId())
            ))
    );
~~~

Two concurrent requests can both see that the key does not exist and then both create orders. Checking before inserting does not prevent race conditions.

You need a claim operation protected by a database unique constraint or an INSERT statement handling conflicts.

### 8.2. Claiming the Key with an Atomic INSERT

With PostgreSQL, you can use:

~~~sql
INSERT INTO idempotency_records (
    client_id,
    idempotency_key,
    request_hash,
    status,
    created_at
)
VALUES (
    :clientId,
    :key,
    :requestHash,
    'IN_PROGRESS',
    CURRENT_TIMESTAMP
)
ON CONFLICT (client_id, idempotency_key) DO NOTHING;
~~~

Check rowsUpdated:

- 1: this request claimed the key.
- 0: the key already exists and the request should inspect current state.

ON CONFLICT syntax is PostgreSQL-specific. Other databases use different upsert/ignore syntax. Use the syntax of your deployment engine and test on the actual driver.

After claiming successfully, create the resource and mark the idempotency record COMPLETED inside the same database transaction:

~~~text
BEGIN
  INSERT idempotency key
  INSERT order
  INSERT outbox event
  UPDATE idempotency record -> COMPLETED
COMMIT
~~~

If the transaction rolls back, both the key claim and the order/outbox roll back. A retried request can attempt to claim again.

### 8.3. Handling an Existing Key

If INSERT fails to claim the key:

1. Read the existing record by client_id and idempotency_key.
2. Compare request_hash.
3. If the hash differs, return conflict.
4. If COMPLETED, return the stored resource/response.
5. If IN_PROGRESS, return an in-progress status or apply a bounded wait/retry policy.
6. If FAILED, apply an explicit business policy: return the stored error, allow retrying the same operation, or require a new key.

In PostgreSQL, if you run a plain INSERT and let a unique constraint violation occur, the current transaction may enter an aborted state. Do not catch the unique error and continue issuing SELECTs inside the same transaction as if it were still healthy. Using INSERT ... ON CONFLICT DO NOTHING handles conflicts without aborting the transaction that way.

### 8.4. Two Requests with the Same Key Can Wait on Each Other

If the first request has inserted the key but not yet committed, the second request inserting the same key may block waiting for the uniqueness check to resolve. Once the first transaction commits, the second learns of the conflict/zero rows inserted. If the first transaction rolls back, the second can claim the key.

This is behavior that must be tested on a real database. Mock repository tests cannot prove database unique constraints and locking behavior.

## 9. Idempotency Is Not Equivalent to Exactly-Once

Idempotency lets an operation be retried without creating duplicate effects for a key. It does not by itself guarantee that a distributed system executes every side effect exactly once.

Example:

1. Server calls a payment gateway.
2. Gateway processes the payment successfully.
3. The connection times out before the server receives the response.
4. The server does not know whether the payment succeeded.

If the server sends a new payment request, it may double-charge. Use a gateway-supported idempotency key or query transaction status before retrying.

With message brokers, a consumer may receive the same event multiple times. Consumers should record processed event IDs using a unique constraint or equivalent deduplication mechanism.

The common pattern is at-least-once delivery combined with idempotent consumers. Do not rely on vague promises of exactly-once unless every participating system provides those semantics.

## 10. Combining Idempotency with Transactions and Outbox

When creating an order requires emitting an event, store all three pieces in a single transaction:

- Idempotency record.
- Order.
- Outbox event.

Flow example:

~~~text
POST /orders + Idempotency-Key
             |
             v
      Service layer
             |
             v
      R2DBC transaction
             |
             +-- claim idempotency key
             |
             +-- create order
             |
             +-- create outbox event
             |
             +-- mark idempotency COMPLETED
             |
             v
           COMMIT
             |
             v
       Return response
             |
             v
       Outbox worker
             |
             v
     Publish event / call external system
~~~

If order creation succeeds but writing the outbox fails, the transaction rolls back both the order and the idempotency record. A client retrying with the same key can run again.

If the transaction commits but the response is lost, a client retrying with the same key reads the COMPLETED idempotency record and receives the prior outcome.

An outbox worker may publish duplicates if it crashes after sending a message but before marking the event sent. Therefore, consumers or downstream systems also need idempotency by event ID.

## 11. Testing Idempotency

### 11.1. Sequential Resubmission with the Same Key

First test sending the same request twice:

~~~java
@Test
void repeatedRequestWithSameKeyReturnsSameOrder() {
    Mono<OrderResponse> first =
        orderService.create(command, idempotencyKey);

    Mono<OrderResponse> second =
        orderService.create(command, idempotencyKey);

    StepVerifier.create(first)
        .assertNext(firstResponse ->
            StepVerifier.create(second)
                .assertNext(secondResponse -> {
                    assertThat(secondResponse.orderId())
                        .isEqualTo(firstResponse.orderId());
                })
                .verifyComplete()
        )
        .verifyComplete();
}
~~~

Nesting StepVerifier inside assertNext only illustrates the idea; in real tests, chain the two publishers with flatMap or collect results via Tuple to avoid hard-to-read nested subscriptions.

A cleaner approach:

~~~java
Mono.zip(
    orderService.create(command, idempotencyKey),
    orderService.create(command, idempotencyKey)
).as(StepVerifier::create)
    .assertNext(pair ->
        assertThat(pair.getT1().orderId())
            .isEqualTo(pair.getT2().orderId())
    )
    .verifyComplete();
~~~

If both publishers are subscribed concurrently, this test also exercises a same-key race. To separate sequential and concurrent tests cleanly, write two distinct tests.

### 11.2. Verifying Resource Counts

After sending the same key multiple times, confirm the database has only one order:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE idempotency_key = :key;
~~~

If idempotency keys live in a dedicated table, count records by client_id/key and check resource_id. Do not check only that two responses look identical; two distinct resources could accidentally return identical response fields due to a mapping bug.

### 11.3. Same Key with Different Payload

Tests must verify that the same key with a different request hash is rejected:

~~~java
StepVerifier.create(
    orderService.create(differentCommand, idempotencyKey)
)
.expectError(IdempotencyKeyReuseException.class)
.verify();
~~~

Then confirm the first resource remains intact and no second order was created.

### 11.4. Two Concurrent Requests with the Same Key

Use a barrier similar to optimistic locking tests:

- Two requests start with the same key and payload.
- Both reach the claim step.
- The unique constraint permits only one record.
- One request creates the order.
- The other reads the completed result or receives an IN_PROGRESS status per policy.
- In the end, only one order and one matching outbox event exist.

API responses of the two requests may differ in HTTP status if the contract allows the second request to receive 202 Accepted while the first is still processing. What must hold is that no duplicate business effect is created.

### 11.5. Simulating Lost Response After Commit

This is an important scenario:

1. Service commits the order, idempotency record, and outbox.
2. Test simulates a lost response or client failing to receive it.
3. Client resends the same key.
4. Server returns the stored outcome.
5. Database still contains only one order and one outbox event.

You do not need to physically sever the network in every test. You can decouple business processing from HTTP response delivery and test same-key retry directly. HTTP-level integration tests can add timeout simulation when needed.

## 12. Testing Idempotent Consumers and Duplicate Delivery

An outbox worker or message consumer may receive the same event multiple times. A processed_events table can record processed event IDs:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_processed_event
        UNIQUE (consumer_name, event_id)
);
~~~

Inside one transaction, the consumer:

1. Attempts to insert the processed event ID.
2. If insert succeeds, applies the business state change.
3. Commits both the processed marker and the change.
4. If the event ID already exists, skips the duplicate effect.

Two concurrent consumer deliveries of the same event ID must be guarded by the unique constraint. If you only SELECT before INSERT, both can observe the event as unprocessed.

Conceptual logic example:

~~~java
public Mono<Void> handle(OrderConfirmed event) {
    return transactionalOperator.transactional(
        processedEventRepository.claim(
                "inventory-consumer",
                event.eventId()
            )
            .flatMap(claimed -> {
                if (!claimed) {
                    return Mono.empty();
                }

                return inventoryRepository.reserveForOrder(event.orderId());
            })
    );
}
~~~

claim must be an atomic operation guarded by a unique constraint or matching upsert. When claim and inventory update share the same transaction, a failure during the inventory step rolls back the processed marker so the event can be retried.

If you mark the event processed before the business transaction and the second transaction fails, the event may be skipped forever. Therefore, the processed marker and database side effects must share the same local transaction.

## 13. Testing Retries After Optimistic Locking Conflicts

Retrying optimistic locking conflicts requires reloading the latest entity and reapplying the business intent. Never retry the same stale object.

Example incrementing a counter:

~~~java
public Mono<Inventory> addStock(Long productId, int amount) {
    return updateOnce(productId, amount)
        .retryWhen(
            Retry.max(2)
                .filter(
                    OptimisticLockingFailureException.class::isInstance
                )
        );
}

private Mono<Inventory> updateOnce(Long productId, int amount) {
    return inventoryRepository.findById(productId)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(productId)
        ))
        .flatMap(inventory -> {
            inventory.setAvailable(
                inventory.getAvailable() + amount
            );
            return inventoryRepository.save(inventory);
        });
}
~~~

Each time updateOnce is resubscribed, the pipeline reads the fresh entity and recalculates the quantity from the latest version.

However, retrying is safe only if the operation can genuinely be reapplied. Do not place external side effects like sending emails or charging payments inside updateOnce if retries could repeat them.

### 13.1. Testing Retry Limits

Tests should verify:

- The first conflict causes the pipeline to reload.
- The retry succeeds with the new version.
- Retries do not exceed the configured maximum.
- If every attempt conflicts, the final error is returned.
- Errors other than optimistic locking are not retried mistakenly.

You can use mocks with call counts to test retry logic, alongside separate integration tests confirming the real database emits optimistic locking errors.

### 13.2. Do Not Retry Constraint or Connection Errors Indiscriminately

Unique constraint violations, validation failures, timeouts, and connection failures have different semantics. Retry only errors classified as recoverable per business policy.

When retrying after a timeout of an external side effect, the outcome may be ambiguous. Use idempotency keys and status reconciliation instead of blindly issuing a fresh command.

## 14. Test Data, Transaction Tests, and Isolation

### 14.1. Using a Production-Compatible Database

Concurrency behavior depends on the database:

- Row locking during UPDATE.
- Unique constraint handling when two transactions insert the same key.
- Default isolation level.
- Upsert semantics.
- rowsUpdated behavior.
- R2DBC driver data types and conversions.

An in-memory database may fail to mimic PostgreSQL or your production engine faithfully. For concurrency and idempotency tests, use the same engine and R2DBC driver as live environments, typically via Testcontainers.

### 14.2. Do Not Wrap the Entire Race Test in One Transaction

If a test class or method carries an outer transaction, the two service calls may share a transaction context or fail to establish two independent connections as intended.

To test a race:

- Create and commit fixtures before the test begins.
- Invoke two independent service publishers.
- Each publisher opens its own transaction.
- Await both to complete.
- Read back state with a fresh query.
- Clean up data after assertions finish.

If using test transaction management, explicitly check how transaction context propagates and verify it does not compromise independence of the two requests.

### 14.3. Ensure the Pool Has Enough Connections

A race test with two transactions holding connections simultaneously needs at least two connections. If more transactions wait at a barrier, size the pool accordingly.

A test hanging at a barrier is often caused by a pool with only one connection rather than a bug in optimistic locking.

Do not enlarge the global application pool just to fix a test. Configure a test-specific pool and ensure it closes cleanly.

### 14.4. Do Not Use Thread.sleep for Synchronization

Thread.sleep only delays for a duration; it never proves both requests read the same version. Outcomes depend on machine load and scheduler timing.

Prefer:

- Reactor Sinks or reactive barriers.
- Non-blocking latches used properly only on test threads, never on event loops.
- Test hooks right after reading data.
- Explicit synchronization mechanisms in fixtures.

The goal is synchronizing on actual events—such as "both transactions finished reading"—rather than "wait 100 milliseconds and hope."

## 15. Testing Failure and Recovery Scenarios

A solid test suite covers multiple failure paths:

| Scenario | Expected outcome to verify |
|---|---|
| Two entities with same version saved sequentially | First succeeds, second conflicts |
| Two transactions concurrently update stale version | Only one update succeeds |
| Two requests deduct more than available stock | No negative inventory |
| Two requests with same idempotency key and payload | Only one business resource created |
| Same key with different payload | Second request rejected |
| Retry after commit when response was lost | Stored result returned |
| Worker receives same event twice | Consumer applies database side effect once |
| Transaction writes order but outbox fails | Both order and outbox roll back |
| Optimistic locking retry | Reloads fresh entity before next write |
| Retry encounters validation error | Does not retry endlessly or swallow error |
| Consumer crashes before commit | Processed marker and business changes both roll back |
| Consumer crashes after commit before ack | Redelivered event is deduplicated |

Inspecting data after failures is crucial. An exception of the expected type does not prove no partial writes occurred.

## 16. Testing API Idempotency with WebFlux

At the HTTP layer, verify that the idempotency header is accepted and passed to the service.

Controller example:

~~~java
@PostMapping("/orders")
public Mono<ResponseEntity<OrderResponse>> create(
        @RequestHeader("Idempotency-Key") String key,
        @RequestBody CreateOrderRequest request) {

    return orderService.create(request, key)
        .map(response -> ResponseEntity.ok(response));
}
~~~

Some APIs return 201 Created on initial creation and 200 OK on replay, or keep the same status/response. What matters is that the contract is consistent and tested.

HTTP tests should verify:

- Missing key is handled per API policy.
- Malformed key is rejected.
- Same key with same payload returns the same resource ID.
- Same key with different payload returns conflict.
- Header is forwarded properly to the service.
- Replayed responses do not emit duplicate outbox events.
- Concurrent requests with the same key do not create duplicate resources.

Do not derive idempotency keys from IP addresses or user agents. Keys should represent a client-generated business action scoped by the authenticated client/tenant.

## 17. Distinguishing Idempotency Keys from Optimistic Versions in APIs

An API can use both:

~~~text
POST /orders
Idempotency-Key: request-abc
       |
       +-- prevents duplicate order creation when retrying the same request


PUT /orders/42
If-Match: "order-42-v7"
       |
       +-- prevents overwriting when a client edits a stale version
~~~

Idempotency keys apply to re-sending the same logical request. ETag/If-Match or versions apply to updating an existing resource based on the version the client observed.

Examples:

- Client sends POST to create an order, times out, and resends with the same key: server replays the result.
- Two users edit order 42, and the second sends If-Match version 7 after the first saved version 8: server rejects the stale update.
- Client sends POST with a new key: this is a new intent and can create a new resource if business rules permit.

Do not use idempotency keys to replace optimistic locking. Nor should order versions serve as idempotency keys for creation operations.

## 18. Common Mistakes

| Mistake or misconception | Consequence | Fix |
|---|---|---|
| Testing only two sequential saves and calling it a race test | Fails to test two genuinely competing transactions | Add a barrier so both read before writing |
| Running race test inside one shared test transaction | Calls may not be independent | Use two separate transactions and verify connection/pool |
| Using Thread.sleep to induce a race | Tests become flaky under varying machine load | Synchronize with reactive barriers |
| Pool has only one connection in test | First transaction holds connection waiting; second cannot reach barrier | Provide at least two connections for race tests |
| Asserting only the exception | Does not prove final database state is valid | Query database and verify version/status |
| Retrying the same stale entity | Repeats stale version condition | Reload and reapply changes |
| Retrying every exception | Repeats permanent failures or side effects | Filter by error type and bound retries |
| Only SELECT key before INSERT | Two requests can both observe key absent | Use unique constraints and atomic claims |
| Same idempotency key with different payload still replays | Returns wrong outcome for a different intent | Store request hash and reject mismatched reuse |
| Catching unique violation and querying inside aborted transaction | Transaction may be unusable | Use upsert/ON CONFLICT or handle in a fresh transaction |
| Storing key only after creating order | Crash can leave duplicate order before key is saved | Claim key, create resource, and save result in one transaction |
| Calling payment gateway inside transaction and retrying everything | May double-charge | Use gateway idempotency keys and outbox/saga |
| Marking event processed before updating data | Event may be skipped if write fails | Share one transaction for marker and business changes |
| Assuming message brokers guarantee exactly-once | Side effects can still repeat across system boundaries | At-least-once delivery + idempotent consumers |
| Using a test database different from production | Fails to reproduce real lock/upsert/driver semantics | Run integration tests on target database and driver |

## 19. Workflow for Building a Concurrency and Idempotency Test Suite

You can implement this in sequence:

1. Identify entities that multiple requests can update concurrently.
2. Add @Version to appropriate entities and migrations for version columns.
3. Identify invariants needing protection via atomic SQL statements or database constraints.
4. Identify endpoints/commands clients may resend after timeouts.
5. Scope idempotency keys by tenant/client and operation type.
6. Create idempotency tables with unique constraints and request hashes.
7. Write idempotency records, business data, and outbox rows in the same transaction when needed.
8. Write stale-entity tests using two reads of the same version.
9. Write barrier-based race tests with two independent transactions and two connections.
10. Verify database state after one operation wins and the other conflicts.
11. Write tests for two requests with the same idempotency key and same payload.
12. Write tests for the same key with a different payload.
13. Test duplicate event delivery and consumer deduplication.
14. Test timeouts, cancellations, crash/retry, and external side effects.
15. Run integration tests against the target R2DBC driver and database.
16. Monitor conflict rates, duplicate key rates, retry counts, and processing latency in production.

## 20. Self-Check Exercises

### Exercise 1: Stale Entity

Two reads of the same Order both receive version 4. The first save succeeds. What result should the second save receive?

Hint: The second save uses the stale version and therefore emits OptimisticLockingFailureException. The database keeps the first save's changes.

### Exercise 2: Race Test

Why are two sequential saves insufficient to prove two transactions truly compete?

Hint: They do not run concurrently and do not prove both transactions read the same version before writing. Use a barrier after the read step to synchronize two independent publishers.

### Exercise 3: Connection Pool

A race test has two transactions waiting at a barrier, but the pool has only one connection. What can happen?

Hint: The first transaction holds the connection while waiting. The second transaction cannot acquire a connection to read and reach the barrier, causing the test to hang.

### Exercise 4: Idempotency

A client resends the same POST request with the same key after a response was lost. What should the server do?

Hint: Read the idempotency record and return the completed result without creating a new resource.

### Exercise 5: Different Payload

Two requests use the same idempotency key with different request hashes. Should the server return the old result?

Hint: No. That is improper key reuse and must be rejected according to the API contract.

### Exercise 6: Unique Constraint

Why does SELECT followed by INSERT for an idempotency key still have a race condition?

Hint: Two transactions can both execute SELECT before either executes INSERT. Only a unique constraint and atomic claim protect against the race.

### Exercise 7: Duplicate Event

A consumer processes an event and crashes before acking. The broker redelivers the event. How do you avoid applying business changes twice?

Hint: Store the event ID in processed_events with a unique constraint and update the marker inside the same transaction as the database side effects.

### Exercise 8: Retrying Optimistic Locking

Should you call retry(3) on the exact same Mono already holding the stale entity?

Hint: No. Each retry must re-execute the read step to obtain the new version and reapply the business intent.

### Exercise 9: Exactly-Once

Does an idempotency record in the database guarantee a payment gateway charges only once?

Hint: No, if the gateway does not participate in the same transaction. You need gateway-supported idempotency keys, status queries, and reconciliation processes.

### Exercise 10: Testing Rollback

After a transaction writes an order and fails while writing the outbox, what must be verified?

Hint: Neither the order nor the outbox record exists after rollback. Asserting the exception alone is insufficient.

## 21. Key Takeaways

- Concurrency conflicts, optimistic locking, and idempotency are three related yet distinct problems.
- @Version lets Spring Data detect entities that changed since they were read.
- Stale-entity tests should read two snapshots before saving the first, then verify the second is rejected.
- Real race tests need two independent transactions and two connections reading before writing.
- Use reactive barriers instead of Thread.sleep to synchronize contention points.
- Never wrap race tests in an outer transaction that removes independence between requests.
- Check database state after a race: only one update succeeds, version increments accurately, and final state matches the winner.
- Conditional UPDATE statements protect invariants such as non-negative inventory.
- Idempotency keys represent resubmitted business intents; unique constraints are the critical race guard.
- Store request hashes to detect same-key requests with differing payloads.
- Claim keys, write business data, and store outbox/results in the same transaction when atomicity is required.
- Duplicate messages must be handled via idempotent consumers and processed event IDs with unique constraints.
- Optimistic locking retries must reload the latest entity; never retry the same stale object.
- A timeout does not prove external side effects did not occur. Use idempotency and reconciliation for operations such as payments.
- Exactly-once does not emerge automatically from Reactor, R2DBC, or message brokers; design for at-least-once delivery with safe duplicate handling.
- Integration tests should run on the target database and R2DBC driver to verify locking, unique constraints, and upsert behavior.

A good test suite does more than prove a service throws the right exception. It must reproduce two competing transactions, prove the database accepts only valid changes, and verify that resent requests or events do not trigger duplicate business effects. Combining @Version, atomic statements, unique constraints, idempotency keys, and transactions according to their proper responsibilities enables an R2DBC application to handle concurrency and retries predictably.
