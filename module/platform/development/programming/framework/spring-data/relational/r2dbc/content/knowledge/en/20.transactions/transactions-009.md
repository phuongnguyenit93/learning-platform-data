# Savepoints, Nested Transactions, and Support Verification

A savepoint is a marker inside an open transaction. An application can roll back operations performed after that marker while keeping the outer transaction active. Spring represents this concept through `PROPAGATION_NESTED` when the transaction manager and R2DBC driver support savepoints.

Nested transactions are not the same as independent transactions. With `NESTED`, the inner work typically uses the same physical transaction and a savepoint; if the inner scope rolls back to the savepoint, the outer scope can still continue. However, when the outer transaction rolls back, all changes made in the nested scope also roll back. With `REQUIRES_NEW`, Spring suspends the outer transaction and opens a separate physical transaction; the new transaction can commit independently.

In Spring Data Relational R2DBC, this capability depends on the Spring transaction manager, the R2DBC driver, and the database. Do not assume savepoints work merely because `@Transactional(propagation = NESTED)` compiles. Verify with integration tests on your exact target driver and database version.

## 1. What is a savepoint?

A standard transaction groups multiple write operations into an atomic unit: either commit everything or roll back everything. A savepoint creates a checkpoint inside that unit.

For example, processing an order involves three steps:

1. Save the order.
2. Attempt to apply an optional part such as a voucher or gift message.
3. Save the order lines and finalize the order.

If the optional step fails while business logic still allows creating the order, you can roll back just that step and continue with the remaining steps. Savepoints fit this situation when all operations must still belong to the same outer transaction.

Model:

~~~mermaid
flowchart TD
    A[Begin outer transaction] --> B[Save order]
    B --> C[Create savepoint]
    C --> D[Run optional operation]
    D --> E{Operation succeeds?}
    E -->|Yes| F[Release savepoint]
    E -->|No| G[Rollback to savepoint]
    G --> H[Handle optional failure]
    F --> I[Continue outer work]
    H --> I
    I --> J{Outer transaction succeeds?}
    J -->|Yes| K[Commit all remaining changes]
    J -->|No| L[Rollback entire transaction]
~~~

If rolling back to the savepoint succeeds, changes after the savepoint are discarded. Changes before the savepoint remain in the outer transaction. They are not committed yet; the outer transaction still determines the final outcome.

## 2. Savepoint operations at the database level

The R2DBC SPI provides savepoint operations on `Connection`:

- `createSavepoint(name)`: creates a marker inside the current transaction.
- `rollbackTransactionToSavepoint(name)`: rolls the transaction back to the marker.
- `releaseSavepoint(name)`: releases the marker when it is no longer needed.

At the SQL level, many databases use similar syntax:

~~~sql
BEGIN;

INSERT INTO orders (id, status)
VALUES (1001, 'NEW');

SAVEPOINT optional_step;

INSERT INTO order_notes (order_id, note)
VALUES (1001, 'Optional note');

ROLLBACK TO SAVEPOINT optional_step;

INSERT INTO order_lines (order_id, product_id, quantity)
VALUES (1001, 501, 2);

COMMIT;
~~~

The expected result is that the order and order line are retained, while the optional note is discarded. Statement names, release details, and certain limits can vary across database engines. The SQL above illustrates semantics, not a portable script meant to run verbatim on every database.

Savepoints are meaningful only inside an active transaction. You cannot use a savepoint to independently commit part of a transaction. `RELEASE SAVEPOINT` also does not commit data; it only discards the savepoint marker.

### Rollback scope

Suppose a transaction contains these operations:

~~~text
A: insert order
SAVEPOINT S1
B: insert optional detail
SAVEPOINT S2
C: update inventory
ROLLBACK TO S2
D: insert order line
COMMIT
~~~

After `ROLLBACK TO S2`, operation C is undone; operations A and B remain in the transaction. Operation D runs after rolling back to S2. When the outer transaction commits, A, B, and D are committed.

If the outer transaction later rolls back, A, B, and D are all undone. A savepoint does not create a sub-transaction capable of independent commit.

## 3. Distinguishing REQUIRED, NESTED, and REQUIRES_NEW

These three propagation modes are often confused because all three can appear when one service calls another.

| Propagation | When a transaction already exists | Independent rollback capability | Can commit independently? |
| --- | --- | --- | --- |
| `REQUIRED` | Joins the current transaction. | No separate savepoint by default. | No. |
| `NESTED` | Creates a savepoint inside the current transaction if supported by manager/driver. | Can roll back to the savepoint. | No. |
| `REQUIRES_NEW` | Suspends the current transaction and opens a new transaction. | The new transaction rolls back independently. | Yes, if the new transaction commits successfully. |

### REQUIRED: single transaction

If both outer and inner methods use `REQUIRED`, both join the same physical transaction.

If the inner method emits an error matching a rollback rule, the transaction can be marked rollback-only. If the outer method catches the error and continues, upon commit it may receive `UnexpectedRollbackException` because the transaction was already marked rollback-only.

There is no automatic savepoint to undo only the inner method's work.

### NESTED: same transaction, with a savepoint

If a transaction already exists, `NESTED` asks the transaction manager to create a savepoint. When the nested scope rolls back, the manager rolls back to the savepoint and the outer transaction can continue if the error is handled appropriately.

If no current transaction exists, a `NESTED` call typically has to start a new transaction; there is no outer transaction in which to create a savepoint.

Success of the nested scope only means its work stays in the outer transaction. It can still be undone if the outer transaction rolls back.

### REQUIRES_NEW: separate physical transaction

`REQUIRES_NEW` suspends the current transaction and begins an independent transaction. The new transaction can commit even if the outer transaction later rolls back.

This approach requires its own connection resource while the outer transaction's connection may still be held. The connection pool must have enough capacity for concurrently nested transactions. If the pool is too small, the call may wait for a connection and time out.

### Example comparing outcomes

Suppose the outer step saves order A, the inner step saves auxiliary data B, and then the outer step emits an error:

| Mechanism for inner step | When inner step succeeds and outer step fails | Final outcome |
| --- | --- | --- |
| `REQUIRED` | B shares transaction with A. | A and B roll back. |
| `NESTED` | B sits after a savepoint in the outer transaction. | A and B roll back with the outer transaction. |
| `REQUIRES_NEW` | B commits in a separate transaction. | A rolls back; B persists. |

If the inner step fails while the outer step catches the error and continues:

- `REQUIRED`: the outer transaction may already be marked rollback-only; catching the error does not automatically recover the transaction.
- `NESTED`: the inner scope can roll back to the savepoint, after which the outer transaction continues.
- `REQUIRES_NEW`: the inner transaction rolls back independently; the outer transaction can still continue.

This is why `NESTED` is useful for work that may fail operationally on its own yet must still commit together with the outer business unit.

## 4. Spring R2dbcTransactionManager and savepoint support

`R2dbcTransactionManager` is the reactive transaction manager for a `ConnectionFactory`. Spring Data R2DBC uses this transaction manager to coordinate connections and transaction contexts for repositories, `DatabaseClient`, and `R2dbcEntityTemplate`.

Spring Framework supports nested transactions backed by R2DBC savepoints, but successful usage depends on the framework version, the actual transaction manager, and driver/database capabilities. The driver must implement the required savepoint operations. Certain drivers or configurations may reject these operations.

When configuring, distinguish:

- Having a `ReactiveTransactionManager` does not guarantee savepoint support.
- Having an R2DBC driver does not guarantee all savepoint operations are supported.
- A database supporting SQL savepoint syntax does not guarantee the driver version in use exposes that full API.
- `PROPAGATION_NESTED` is not a mechanism for creating an independent connection.
- Using multiple `ConnectionFactory` beans does not form a distributed transaction.

Manager configuration example:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

You do not need a separate transaction manager solely for savepoints if your current manager is configured and supports nested transactions. If the application has multiple `ConnectionFactory` beans, select the corresponding manager for each service and do not assume savepoints can span multiple databases.

## 5. Using @Transactional(propagation = NESTED)

The simplest declaration is placing `NESTED` on a `public` method of another bean. Calls from the outer service must go through the Spring proxy.

Example service performing the optional step:

~~~java
@Service
public class OptionalOrderStepService {

    private final OrderNoteRepository notes;

    public OptionalOrderStepService(OrderNoteRepository notes) {
        this.notes = notes;
    }

    @Transactional(propagation = Propagation.NESTED)
    public Mono<Void> addOptionalNote(
            Long orderId,
            String note) {
        return notes.save(new OrderNote(orderId, note))
            .then();
    }
}
~~~

Orchestrating service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final OrderLineRepository lines;
    private final OptionalOrderStepService optionalStep;

    public OrderService(
            OrderRepository orders,
            OrderLineRepository lines,
            OptionalOrderStepService optionalStep) {
        this.orders = orders;
        this.lines = lines;
        this.optionalStep = optionalStep;
    }

    @Transactional
    public Mono<Order> createOrder(CheckoutCommand command) {
        return orders.save(Order.from(command))
            .flatMap(order ->
                optionalStep.addOptionalNote(
                    order.id(),
                    command.optionalNote()
                )
                .onErrorResume(OptionalStepException.class, error ->
                    Mono.empty()
                )
                .then(lines.saveAll(
                    OrderLine.from(order.id(), command.items())
                ).then(Mono.just(order)))
            );
    }
}
~~~

When `optionalStep.addOptionalNote` is invoked through the proxy, Spring applies `NESTED`. If writing the note emits an error matching rollback rules, the nested scope rolls back to the savepoint. After the error exits the nested transactional publisher, `onErrorResume` in the caller can handle the error and continue saving order lines in the outer transaction.

This example assumes the exception is classified as an optional failure and not a fatal error that renders the outer database transaction unusable. If the driver or database marks the entire transaction failed after an error, whether continuation works depends on database semantics and whether rolling back to the savepoint succeeds.

### Why catch errors outside the nested boundary?

Place error recovery after the transaction-wrapped call:

~~~java
optionalStep.addOptionalNote(orderId, note)
    .onErrorResume(OptionalStepException.class, error -> Mono.empty());
~~~

Downstream `onErrorResume` receives the error after the nested method's transactional interceptor has handled rollback/cleanup. If you swallow the error inside the method before the transaction boundary observes it, the transaction manager may see normal completion and fail to roll back the nested scope as intended.

If the error is not of an ignorable type, let it continue propagating out so the outer transaction rolls back according to policy.

### Do not self-invoke a NESTED method in the same bean

The following example does not create a savepoint via proxy:

~~~java
@Service
public class OrderService {

    @Transactional
    public Mono<Order> createOrder(CheckoutCommand command) {
        return saveOptionalPart(command)
            .then(orders.save(Order.from(command)));
    }

    @Transactional(propagation = Propagation.NESTED)
    public Mono<Void> saveOptionalPart(CheckoutCommand command) {
        return notes.save(OrderNote.from(command)).then();
    }
}
~~~

Calling `saveOptionalPart` is self-invocation. The `NESTED` annotation is not applied by the proxy, so no new savepoint is created by that call. Move the nested step to another bean or use `TransactionalOperator` with `NESTED` propagation.

## 6. Using TransactionalOperator with NESTED propagation

If you want to express a nested boundary directly inside a reactive chain, you can create a `TransactionalOperator` using a transaction definition with `NESTED` propagation.

~~~java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

DefaultTransactionDefinition nestedDefinition =
    new DefaultTransactionDefinition();

nestedDefinition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_NESTED
);

TransactionalOperator nestedOperator =
    TransactionalOperator.create(
        transactionManager,
        nestedDefinition
    );
~~~

Then wrap only the publisher needing the savepoint:

~~~java
Mono<Void> optionalStep =
    nestedOperator.transactional(
        notes.save(OrderNote.from(orderId, note)).then()
    );

return outerOperator.transactional(
    orders.save(order)
        .flatMap(saved ->
            optionalStep
                .onErrorResume(OptionalStepException.class, error ->
                    Mono.empty()
                )
                .then(lines.saveAll(
                    OrderLine.from(saved.id(), items)
                ).thenReturn(saved))
        )
);
~~~

Here:

- `outerOperator` uses the default or `REQUIRED` transaction definition.
- `nestedOperator` uses `PROPAGATION_NESTED`.
- `optionalStep` is subscribed inside the outer publisher's transaction context.
- If an outer transaction exists, the nested operator requests a savepoint.
- If the nested step errors, the transactional operator handles rolling back to the savepoint before downstream recovery continues.

Do not subscribe to `optionalStep` separately before wrapping the outer transaction. Keep the publisher in the same composition so the nested operator sees the active transaction context.

If `nestedOperator` is invoked when no outer transaction exists, the manager may open a new transaction for that publisher. In that case, it is not a savepoint nested inside another transaction. If business logic specifically requires a savepoint, ensure the outer transaction has started before the nested publisher executes.

## 7. What happens when a nested scope fails?

The outcome depends on where errors are handled and the type of error.

### Nested scope errors, caller handles and continues

Desired flow:

1. Outer transaction begins.
2. Primary data is written.
3. Savepoint is created.
4. Nested scope writes secondary data.
5. Nested scope emits an error.
6. Transaction manager rolls back to the savepoint.
7. Caller receives the error and handles it with `onErrorResume`.
8. Outer transaction continues with the remaining work.
9. Outer transaction commits.

The result is that primary data and remaining work commit while the nested part is rolled back.

### Nested scope errors and caller does not handle it

If the error continues propagating out of the outer transaction, the outer transaction rolls back. Both data before the savepoint and data after the savepoint are undone.

### Rollback to savepoint fails

If the driver/database does not support savepoints or the rollback-to-savepoint operation fails, the transaction manager cannot guarantee the outer work can continue safely. The rollback error may replace or supplement the original error. Let the outer transaction terminate on the error path and check database state.

Do not catch all exceptions and continue. Recover only errors that business logic defines as ignorable and only after the transaction manager has successfully completed rolling back the nested scope.

## 8. Savepoints do not replace transaction boundaries

A savepoint only creates a rollback point inside a transaction. It does not:

- Commit a portion of data.
- Create a new connection.
- Separate locks or isolation like an independent transaction.
- Guarantee nested data survives if the outer transaction rolls back.
- Automatically recover a transaction if the database has marked the outer transaction unusable.
- Replace compensating mechanisms across services or databases.

If an operation needs to commit independently, consider `REQUIRES_NEW`. If two databases need to commit atomically together, a regular `R2dbcTransactionManager` does not provide distributed transactions. Look into outbox, saga, or architectural compensating workflows.

## 9. Database and driver support

Savepoint support is a property of the entire stack:

~~~text
Spring Framework / Spring Data R2DBC
            |
ReactiveTransactionManager
            |
R2DBC SPI
            |
R2DBC driver
            |
Database server and version
~~~

One unsupported link prevents nested transactions from working as expected.

### Verification checklist

| Component | What to check |
| --- | --- |
| Spring Framework | Does this version support nested transactions for the active reactive manager? |
| Transaction manager | Is it `R2dbcTransactionManager` or a custom manager? Does it allow nested transactions? |
| R2DBC SPI | How does the driver implement `createSavepoint`, `rollbackTransactionToSavepoint`, and `releaseSavepoint`? |
| Driver | Does this specific version have known savepoint bugs or limitations? |
| Database | Does the server version support savepoints in the transaction mode being used? |
| Transaction state | After a statement error, does rolling back to a savepoint return the transaction to a usable state? |
| Connection pool | Are enough connections available for separate `REQUIRES_NEW` flows? |

Do not verify support merely by looking up the database product name. Different driver versions can expose different capabilities even against the same database server.

### Checking via documentation and runtime

Follow these steps:

1. Identify the exact Spring Framework and Spring Data R2DBC versions in the dependency tree.
2. Identify the exact R2DBC driver and version running.
3. Read driver documentation on savepoints and limitations.
4. Cross-check the database server version and savepoint semantics.
5. Write an integration test exercising create, rollback-to, and release savepoint inside a real transaction.
6. Test nested rollback followed by continuing operations and committing the outer transaction.
7. Test outer rollback after a successful nested scope.
8. Test behavior when the nested scope is cancelled or errors during rollback.

If the driver lacks support, do not assume Spring can emulate savepoints with multiple connections. Choose an alternative business flow or restrict supported databases/drivers.

## 10. Integration tests verifying savepoints

A practical test must prove that rolling back to a savepoint cancels only the nested part while the outer transaction still commits.

Suppose we have `orders` and `order_notes` tables with matching repositories. The test service runs:

~~~java
@Transactional
public Mono<Long> saveOrderWithOptionalNote() {
    return orders.save(new Order(null, "NEW"))
        .flatMap(order ->
            optionalNoteService.addNote(order.id())
                .onErrorResume(OptionalStepException.class, error ->
                    Mono.empty()
                )
                .thenReturn(order.id())
        );
}
~~~

Nested service:

~~~java
@Transactional(propagation = Propagation.NESTED)
public Mono<Void> addNote(Long orderId) {
    return notes.save(new OrderNote(orderId, "optional"))
        .then(Mono.error(new OptionalStepException()));
}
~~~

Test:

~~~java
@Test
void rollsBackNestedWorkAndCommitsOuterTransaction() {
    StepVerifier.create(orderService.saveOrderWithOptionalNote())
        .assertNext(orderId -> {
            StepVerifier.create(orders.findById(orderId))
                .expectNextCount(1)
                .verifyComplete();

            StepVerifier.create(notes.findByOrderId(orderId))
                .verifyComplete();
        })
        .verifyComplete();
}
~~~

This example outlines the test idea; do not nest subscriptions inside `assertNext` in real tests. Write the test as a sequential reactive chain so all assertions finish before the test ends:

~~~java
@Test
void nestedRollbackKeepsOuterOrder() {
    StepVerifier.create(
        orderService.saveOrderWithOptionalNote()
            .flatMap(orderId ->
                orders.findById(orderId)
                    .switchIfEmpty(Mono.error(
                        new AssertionError("Outer order was not committed")
                    ))
                    .flatMap(order ->
                        notes.findByOrderId(orderId)
                            .hasElements()
                            .flatMap(hasNote -> {
                                assertFalse(hasNote);
                                return Mono.just(order.id());
                            })
                    )
            )
    )
    .expectNextMatches(Objects::nonNull)
    .verifyComplete();
}
~~~

Tests must invoke the service through the Spring-injected bean so the transaction proxy operates. Do not instantiate `new OrderService(...)` manually and expect annotations to apply.

### Testing outer rollback

An additional test confirms that nested success still depends on the outer transaction:

1. Outer transaction saves an order.
2. Nested scope saves a note and completes.
3. Outer publisher emits an error after the nested scope.
4. After termination, verify neither the order nor the note exists.

This proves a savepoint does not commit independently.

### Testing REQUIRES_NEW for comparison

To demonstrate the difference from an independent transaction:

1. Outer transaction begins.
2. Another bean is called through the proxy with `REQUIRES_NEW`.
3. The new transaction writes data and commits.
4. The outer transaction emits an error and rolls back.
5. Data from the new transaction still exists.

This test needs a connection pool large enough to supply a connection for the new transaction while the outer transaction is suspended.

## 11. Testing the R2DBC driver directly

Beyond testing through Spring's transaction manager, you can write a driver-level integration test to verify the savepoint API. Concept:

~~~java
Mono.usingWhen(
    connectionFactory.create(),
    connection ->
        connection.beginTransaction()
            .then(connection.createSavepoint("sp_optional"))
            .then(runOptionalStatement(connection))
            .then(connection.rollbackTransactionToSavepoint("sp_optional"))
            .then(connection.releaseSavepoint("sp_optional"))
            .then(connection.commitTransaction()),
    connection -> connection.close()
);
~~~

This only sketches the sequence of operations. Real tests must handle rollback on errors, close the connection safely, and adapt to the exact `Publisher` types returned by the driver. Do not run this concurrently with other operations on the same connection.

When Spring's transaction manager manages the connection, avoid manually acquiring a new connection or manually committing/rolling back. Let the manager own the transaction lifecycle. Keep SPI-level tests separate from `@Transactional` tests so connection ownership does not conflict.

## 12. Limitations and differences across database engines

Savepoints are widely supported across relational databases, yet important limitations exist:

- Some DDL statements may implicitly commit or have distinct savepoint semantics.
- Some kinds of operations cannot roll back the way users expect.
- After a statement error, a database may mark the transaction requiring rollback to a savepoint before continuing.
- Savepoint naming and savepoint nesting rules may have limits.
- Releasing a savepoint may be semantically optional in some systems, yet the API/driver must still follow contract rules.
- Some databases do not support savepoints in all transaction types or storage engines.
- Locks acquired after a savepoint may or may not be released when rolling back to the savepoint depending on the database engine.

Therefore, do not generalize behavior from one database to another. Read the documentation for your exact server version and test against your deployment configuration.

### Savepoints and DDL

Do not use nested transactions as a way to guarantee DDL can roll back on every database. Schema migrations are usually managed by dedicated tools and have distinct transaction semantics. Some engines implicitly commit before/after certain DDL statements or restrict statements allowed in transactions.

If the nested work alters schema, test DDL behavior separately. For application business logic, savepoints are generally meant for DML operations such as `INSERT`, `UPDATE`, and `DELETE`.

## 13. Connection pools and nested transactions

`NESTED` uses a savepoint on the active transaction, so it usually does not require a new physical connection. `REQUIRES_NEW` needs its own transaction and may require another connection while the outer transaction is suspended.

This difference affects pooling:

| Mechanism | Connection | Pool impact |
| --- | --- | --- |
| `REQUIRED` | Uses the current transaction connection. | No extra connection needed for the joining scope. |
| `NESTED` | Uses the current connection and a savepoint. | Usually no extra connection needed. |
| `REQUIRES_NEW` | Opens a separate transaction while outer transaction is suspended. | Requires ability to allocate an extra connection. |

If many concurrent requests hold an outer connection while waiting for a connection for `REQUIRES_NEW`, the pool can be exhausted. Measure concurrency and size pools accordingly; avoid unbounded nesting of new transactions.

Do not run multiple SQL statements concurrently on the same transaction connection unless clearly supported by the driver/database. In reactive chains, use `concatMap`, `then`, or `flatMap` with appropriate concurrency when statements must be sequential. A savepoint is state on a single transactional connection; interleaving multiple command streams on that connection makes operation ordering unpredictable.

## 14. Subscription cancellation and errors in reactive transactions

Reactive transactions depend on subscription lifecycles. If a subscriber cancels before the publisher completes, the transaction manager must perform cleanup and rollback according to Spring's reactive transaction mechanics.

With savepoints, cancellation while a nested scope is running is an important edge case to test: whether the nested scope rolls back cleanly, whether the outer transaction remains usable, and whether the connection returns to the pool after cleanup.

Scenarios worth testing:

- Cancelling before the nested publisher begins.
- Cancelling after the savepoint is created but before the statement completes.
- Statement emits an error and rollback-to-savepoint succeeds.
- Rollback-to-savepoint itself emits an error.
- Outer publisher is cancelled after the nested scope succeeds.
- Driver timeout or connection closure mid-savepoint operation.

Do not catch cancellation and turn it into normal completion just to keep the transaction alive. Let the transaction infrastructure complete cleanup and verify behavior with integration tests against a real driver.

## 15. Common mistakes

| Mistake | Cause | Resolution |
| --- | --- | --- |
| `PROPAGATION_NESTED` reports unsupported | Transaction manager/driver does not support savepoints or config disallows nested | Check Spring version, manager, and driver; run integration tests |
| Nested annotation does not create a savepoint | Method was self-invoked so proxy did not intercept | Extract a bean or use `TransactionalOperator` with `NESTED` |
| Assuming nested commits independently | Confusing savepoints with new transactions | Remember outer rollback still undoes nested changes |
| Catching error yet outer transaction still rolls back | Transaction was already marked rollback-only or database cannot recover from error | Check error, savepoint rollback, and transaction state before continuing |
| Using `REQUIRES_NEW` when partial rollback is wanted | Choosing an independent physical transaction instead of a savepoint | Use `NESTED` if savepoint semantics fit and are supported |
| Pool exhausted when using `REQUIRES_NEW` | Outer transaction holds a connection while inner needs another | Size pool for concurrency and avoid unnecessary nesting |
| Issuing manual SQL `SAVEPOINT` inside Spring-managed transaction | Manually interfering with connection state owned by manager | Use `NESTED` propagation or managed savepoint APIs |
| Testing with mocks only | Fails to verify driver and database savepoint support | Use integration tests on the real R2DBC driver/database |
| Assuming DDL always rolls back to savepoint | DDL semantics differ across databases | Check database docs and test DDL separately; use migration tools |

## 16. Workflow for deciding whether to use savepoints

When designing a step that may fail inside a larger transaction, answer in order:

1. Does the inner work need to commit independently?
2. If the outer transaction rolls back, must the inner data also roll back?
3. If the inner work fails, is the outer work allowed to proceed?
4. Is `REQUIRED` sufficient, or is partial rollback needed?
5. Do the target driver and database support savepoints?
6. Does your Spring transaction manager version support `PROPAGATION_NESTED`?
7. Can the nested error actually be recovered after rollback-to-savepoint?
8. Is a separate bean needed so the call passes through a proxy?
9. Are there connection pool or transaction concurrency risks?
10. Have integration tests confirmed both nested rollback and outer rollback?

Choose based on semantics:

- Use `REQUIRED` when all operations must succeed or roll back together.
- Use `NESTED` when the inner part can roll back to a savepoint while the outer transaction continues; everything still commits or rolls back together.
- Use `REQUIRES_NEW` when the inner part must have an independent commit result.
- Use outbox/saga or compensating workflows when work spans multiple databases or services.

Savepoints allow a transaction to recover from a failed step without immediately discarding all work. In Spring Data Relational R2DBC, use `PROPAGATION_NESTED` or `TransactionalOperator` with the corresponding transaction definition when supported by the transaction manager and driver. Always distinguish savepoints from independent transactions, keep errors at the right reactive boundary, and verify behavior via integration tests on the exact database/driver before relying on it in business logic.
