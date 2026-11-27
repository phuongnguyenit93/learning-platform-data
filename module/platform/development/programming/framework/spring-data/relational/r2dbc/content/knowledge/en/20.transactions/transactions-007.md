# Rollback Rules by Exception Type and Configuration

In Spring Data Relational R2DBC, a transaction groups multiple database operations into a single unit: either all are committed, or changes are rolled back according to the transaction policy. However, not every exception causes Spring to roll back. The outcome depends on the error type, rollback rule configuration, how errors traverse the reactive pipeline, and the transaction manager managing the connection.

With declarative transactions via the `@Transactional` annotation, Spring rolls back by default when a method terminates with a `RuntimeException` or `Error`. Checked exceptions do not trigger rollback under the default rule. You can alter this behavior with `rollbackFor` and `noRollbackFor`.

In reactive code, it is essential that exceptions are emitted as `onError` signals in the `Publisher` so the transaction interceptor observes them. If the application catches an error and turns it into normal completion inside the transaction boundary, Spring may commit. Cancellation of a reactive transaction also requires attention because cancelling a subscription leads to rollback.

## 1. Transactions and rollback in R2DBC

A transaction typically consists of operations such as:

1. Reading an account balance.
2. Debiting the source account.
3. Crediting the target account.
4. Recording transaction history.
5. Committing when all operations succeed.

If crediting or recording history fails, the application usually needs to roll back so an incomplete state is not persisted.

~~~text
BEGIN
  |
  v
Read data
  |
  v
UPDATE source account
  |
  v
UPDATE target account
  |
  v
INSERT history
  |
  +---- All succeeded -----------> COMMIT
  |
  +---- Error requiring rollback --> ROLLBACK
~~~

R2DBC is a reactive database access API. Spring uses `ReactiveTransactionManager` to manage transactions and connections along the reactive context. With Spring Data R2DBC, the common transaction manager is `R2dbcTransactionManager`.

Rollback ends the transaction and discards uncommitted changes. It does not automatically undo side effects outside the database such as sending emails, calling HTTP services, writing files, or publishing messages to systems not participating in the same transaction.

## 2. Configuring ReactiveTransactionManager

Spring requires a `ReactiveTransactionManager` matching the `ConnectionFactory` used by repositories and `DatabaseClient`.

Example configuration:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    public ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

`R2dbcTransactionManager` manages transactions on a single R2DBC `ConnectionFactory`. When starting a transaction, the manager acquires a connection and binds that resource to the Reactor Context so participating database operations can reuse it.

Key requirements:

- Repositories and `DatabaseClient` must use the same `ConnectionFactory` managed by the transaction manager.
- Reactive methods must return a `Publisher` such as `Mono` or `Flux` so Spring applies reactive transaction semantics.
- Operations must be chained in the same reactive chain so the transaction context propagates forward.
- Do not call `subscribe()` inside a service to run a detached database operation.

In Spring Boot, the transaction manager can be auto-configured when the application has appropriate R2DBC configuration. If you declare multiple `ConnectionFactory` beans or multiple transaction managers manually, specify the right manager for each use case.

You can specify the transaction manager bean in the annotation:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> process() {
    // Reactive database operations
    return Mono.empty();
}
~~~

If an incompatible transaction manager is used, the annotation may fail to manage R2DBC operations properly. Check the manager type, `ConnectionFactory`, and method transaction boundaries.

## 3. Default rollback rules of @Transactional

For declarative transactions, Spring defaults to:

- Rolling back when the exception is a `RuntimeException` or a subclass of `RuntimeException`.
- Rolling back when the exception is an `Error` or a subclass of `Error`.
- Not rolling back by default when the exception is a checked exception—that is, a `Throwable` not extending `RuntimeException` or `Error`.

Example:

~~~java
public class InventoryUnavailableException extends RuntimeException {
}

public class ExportFormatException extends Exception {
}
~~~

If these two exceptions are emitted from a `@Transactional` method:

| Error type | Default rule | Typical outcome |
|---|---|---|
| `RuntimeException` | Rollback | Transaction rolls back |
| `IllegalArgumentException` | Rollback | Transaction rolls back |
| `Error` | Rollback | Transaction rolls back |
| Checked exception | No rollback | Spring attempts commit and propagates the error |

This means a checked exception can be propagated to the caller while database changes are still committed. This behavior often surprises developers who assume every exception triggers rollback.

The default rule is a policy of Spring's transaction abstraction. The database or driver may still mark the transaction as failed and reject commit after a SQL error. Thus, the final outcome also depends on the transaction state maintained by the database.

## 4. Using rollbackFor to roll back on checked exceptions

If a checked exception must roll back the transaction, declare `rollbackFor`:

~~~java
@Transactional(rollbackFor = ExportFormatException.class)
public Mono<Void> createExportRecord() {
    return exportRepository.save(new ExportRecord())
        .then(Mono.error(new ExportFormatException()));
}
~~~

In this example, `ExportFormatException` extends `Exception`. By default, this checked exception does not trigger rollback. With `rollbackFor`, Spring applies the rollback rule for that exception type.

Multiple types can be declared:

~~~java
@Transactional(
    rollbackFor = {
        ExportFormatException.class,
        BusinessValidationException.class
    }
)
public Mono<Void> executeExport() {
    return performExport();
}
~~~

`rollbackFor` accepts exception classes. Prefer concrete class literals over class-name strings to avoid typos or unexpected pattern matches.

You can use `rollbackFor = Exception.class` to roll back on both checked and unchecked exceptions. However, such a broad rule may not fit if your domain has exceptions where the transaction should still commit. Select the exact error types requiring rollback.

## 5. Using noRollbackFor to avoid rollback on a specific error

Sometimes an exception signals a business warning while database changes still need to be committed. You can use `noRollbackFor`:

~~~java
@Transactional(noRollbackFor = NotificationPendingException.class)
public Mono<Customer> activateCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ))
        .flatMap(customer -> {
            customer.activate();
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            notificationService.sendActivationNotice(saved)
                .thenReturn(saved)
                .onErrorMap(error ->
                    new NotificationPendingException(
                        "Customer activated but notification failed",
                        error
                    )
                )
        );
}
~~~

If `NotificationPendingException` exits the transactional method, Spring applies `noRollbackFor` and does not request rollback solely due to this exception. The exception can still propagate to the caller; `noRollbackFor` does not mean swallowing the error or returning a successful result.

This only illustrates rollback policy. If notification is an HTTP call or email send, a database transaction cannot roll back that external effect. In real systems, consider the outbox pattern or an independent retry mechanism for reliable notification delivery.

## 6. When both rollbackFor and noRollbackFor match

Spring picks the rule most specifically matching the actual exception type. Effectively, the rule with the closest inheritance distance in the exception hierarchy takes precedence.

Example:

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = NotificationPendingException.class
)
public Mono<Void> process() {
    return performWork();
}
~~~

If the error is `NotificationPendingException`, the `noRollbackFor` rule is more specific than the broad `rollbackFor = Exception.class`, so the transaction does not roll back under that rule. If the error is another checked exception, `rollbackFor = Exception.class` applies and the transaction rolls back.

Illustrative table:

| Actual exception | Matching rule | Outcome |
|---|---|---|
| `NotificationPendingException` | Specific `noRollbackFor` | No rollback |
| `ExportFormatException` | `rollbackFor = Exception.class` | Rollback |
| `IllegalStateException` | `rollbackFor = Exception.class` and runtime default | Rollback |

Avoid declaring overlapping rules unnecessarily. When multiple rules exist, check the actual exception type and the most specific matching rule to prevent surprises.

## 7. Configuring rollback in reactive methods

With R2DBC, transactional methods typically return `Mono` or `Flux`:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferRepository transferRepository;

    @Transactional
    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        return accountRepository.debit(fromId, amount)
            .then(accountRepository.credit(toId, amount))
            .then(transferRepository.record(
                fromId, toId, amount
            ))
            .then();
    }
}
~~~

If an operation emits a `RuntimeException` or `Error` out of the reactive chain, the transaction rolls back by default. Earlier operations in the same transaction are not committed.

If business logic uses a checked exception:

~~~java
@Transactional(rollbackFor = InsufficientFundsException.class)
public Mono<Void> transfer(
        Long fromId,
        Long toId,
        BigDecimal amount) {

    return accountRepository.findById(fromId)
        .switchIfEmpty(Mono.error(
            new AccountNotFoundException(fromId)
        ))
        .flatMap(account -> {
            if (account.getBalance().compareTo(amount) < 0) {
                return Mono.error(
                    new InsufficientFundsException()
                );
            }

            return performTransfer(account, toId, amount);
        });
}
~~~

`InsufficientFundsException` may extend `Exception`. `rollbackFor` explicitly declares that this error must roll back the transaction.

Do not and must not call `subscribe()` inside the service method to kick off the operation. Spring's transaction interceptor wraps the returned publisher and manages the transaction when the caller subscribes to that publisher.

## 8. Reactive error signals determine the rollback boundary

In reactive programming, errors are emitted via the `onError` signal. Spring must receive this signal at the transaction boundary to apply rollback policies.

Example preserving the error:

~~~java
return repository.save(entity)
    .then(Mono.error(new IllegalStateException("failed")));
~~~

The error exits the publisher, so the transaction interceptor can apply rollback rules.

### onErrorMap still emits an error

~~~java
return repository.save(entity)
    .then(Mono.error(new IllegalArgumentException("invalid")))
    .onErrorMap(
        IllegalArgumentException.class,
        error -> new BusinessOperationException(error)
    );
~~~

`onErrorMap` transforms the exception type while still emitting `onError`. Spring evaluates rollback based on the mapped exception if that is the exception exiting the transactional boundary.

### onErrorResume can turn an error into normal completion

~~~java
@Transactional
public Mono<Void> process() {
    return repository.save(entity)
        .then(Mono.error(new IllegalStateException("failed")))
        .onErrorResume(error -> Mono.empty());
}
~~~

Here `onErrorResume` catches the error and replaces it with `Mono.empty()`. The publisher finishes normally. The transaction interceptor may consider the method completed successfully and commit.

If rollback is wanted, do not swallow errors inside the transaction. You can log with `doOnError` and let the error continue propagating out:

~~~java
return repository.save(entity)
    .then(Mono.error(new IllegalStateException("failed")))
    .doOnError(error -> log.error("Operation failed", error));
~~~

`doOnError` only performs a side effect; it does not replace `onError` with a successful outcome.

## 9. Placement of onErrorResume affects the transaction

With `TransactionalOperator`, where recovery is placed can alter the commit/rollback outcome.

### Recovering inside the transaction

~~~java
Mono<Void> work =
    debit()
        .then(credit())
        .onErrorResume(error -> Mono.empty());

return transactionalOperator.transactional(work);
~~~

The error is handled before reaching `TransactionalOperator`. The operator sees the publisher complete normally and may commit.

### Recovering outside the transaction

~~~java
Mono<Void> work =
    debit().then(credit());

return transactionalOperator.transactional(work)
    .onErrorResume(error -> {
        log.error("Transaction rolled back", error);
        return Mono.empty();
    });
~~~

In this approach, the error crosses the `TransactionalOperator` boundary first. The operator performs rollback and then propagates the error outward. The subsequent `onErrorResume` then converts the error into a completed result for the caller.

If you need to return a fallback yet still roll back, place recovery after the transaction boundary or mark the transaction rollback-only via the appropriate status API. Avoid accidentally recovering an error before the transaction manager observes it.

## 10. Cancellation in reactive transactions

A reactive transaction can terminate via complete, error, or cancel. Cancellation happens when a subscriber cancels the subscription, for example:

- An HTTP client disconnects.
- A timeout operator cancels upstream.
- `take()` or `next()` stops consuming a `Flux` before the source completes.
- The caller explicitly disposes the subscription.

For reactive transactions, cancellation leads to rollback to avoid committing a stream interrupted mid-way.

Example:

~~~java
Flux<Customer> result =
    transactionalOperator.transactional(
        customerRepository.findAll()
            .doOnNext(this::process)
    );
~~~

If the subscriber takes only part of the data and cancels, the transaction can roll back. Do not use `next()`, `take(1)`, or early cancellation inside a transactional `Flux` when the intent is to commit all operations.

For queries needing only one result, use `Mono` and suitable APIs. For tasks needing to process an entire dataset, consume the publisher to completion or split deliberately into separate transactions/batches.

## 11. Using TransactionalOperator

`TransactionalOperator` is the programmatic API for wrapping a reactive pipeline in a transaction:

~~~java
public Mono<Void> transfer(Long fromId, Long toId, BigDecimal amount) {
    Mono<Void> work =
        accountRepository.debit(fromId, amount)
            .then(accountRepository.credit(toId, amount))
            .then(transferRepository.record(fromId, toId, amount))
            .then();

    return transactionalOperator.transactional(work);
}
~~~

Configuring the operator:

~~~java
@Bean
public TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

`TransactionalOperator` is suitable when:

- Only part of a service needs a transaction.
- You want the transaction boundary visible right inside the reactive chain.
- You need to compose transactions with other operators explicitly.
- You want to handle errors outside the transaction boundary after rollback.

When using `TransactionalOperator` with a passed-in pipeline, reactive errors exiting the pipeline and cancellation are treated by the operator as rollback paths. Unlike the `@Transactional` annotation, `TransactionalOperator` does not configure `rollbackFor`/`noRollbackFor` via method annotations; it manages transactions through the programmatic API and transaction definitions.

If rollback-only control is needed inside a callback, use the transaction status supplied to the callback to mark rollback-only. Do this only when business logic truly needs the publisher to complete without committing.

## 12. Detailed @Transactional configuration

The `@Transactional` annotation allows configuring several aspects:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false,
    rollbackFor = InsufficientFundsException.class
)
public Mono<Void> transfer(...) {
    return performTransfer(...);
}
~~~

Common attributes:

| Attribute | Meaning |
|---|---|
| `transactionManager` | Selects the transaction manager |
| `propagation` | How to join or create a transaction |
| `isolation` | Transaction isolation level |
| `timeout` | Maximum duration as supported by manager configuration |
| `readOnly` | Read-only hint or mode depending on manager/database |
| `rollbackFor` | Exception classes triggering rollback |
| `noRollbackFor` | Exception classes not requiring rollback |

### Propagation

Propagation defines how an operation joins an existing transaction or creates a new one.

- `REQUIRED` is the common default: join the current transaction if present; otherwise create a new transaction.
- `REQUIRES_NEW` requests a new transaction as supported by the transaction manager; the current transaction may be suspended.
- `SUPPORTS` can run inside an existing transaction or without a transaction.
- `MANDATORY` requires an existing current transaction.
- `NEVER` requires running without a transaction.

Do not pick propagation modes merely to work around a rollback bug. First determine which operations must commit or roll back together.

### Isolation

Isolation controls how concurrent transactions observe each other's changes. Common levels include `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE`, though support and semantics depend on the database.

If a method joins an existing transaction, the isolation setting on the inner call normally does not change the isolation chosen when the outer transaction started. Configure isolation at the boundary that actually starts the transaction.

### Timeout

Timeout helps cap transaction duration according to transaction manager and driver capabilities. It does not replace timeouts on HTTP clients, pool acquisition, or individual SQL statements. Understand that timeouts at any layer can cancel publishers and cause reactive transactions to roll back.

### Read-only

`readOnly` is a hint or transaction attribute depending on manager/database capabilities. Do not treat it as an authorization mechanism or guarantee that every write statement will be rejected by the database. If writes must be prevented, use database permissions and appropriate application rules.

## 13. Transaction boundaries and Reactor Context

Reactive transactions do not rely on `ThreadLocal` like the traditional imperative model. Spring binds transaction resources into the Reactor Context, and participating operations retrieve resources from that context.

Therefore, keep operations in the same reactive chain:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            orderLineRepository.saveAll(saved.getLines())
                .then()
        );
}
~~~

Avoid:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
~~~

`subscribe()` creates an independent subscription. The transactional method may finish before the save operation actually ends; the new subscription may also lack the same transaction context. Return the publisher and chain via `then`, `flatMap`, `concatMap`, or suitable operators.

### Self-invocation

Spring typically applies `@Transactional` through proxies. If a method in the same class calls another `@Transactional` method directly, the internal call can bypass the proxy and the annotation will not be applied as expected.

Place transaction boundaries on `public` service methods invoked through a Spring bean proxy, or move the transactional work to a separate bean. Also inspect proxy configuration and method visibility according to how Spring transaction management is set up.

## 14. Multiple transaction managers or multiple ConnectionFactories

An R2DBC transaction manager manages connections belonging to the `ConnectionFactory` it is configured with. If an application has two databases or two `ConnectionFactory` instances, one transaction manager does not automatically create a distributed transaction across both.

Example:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> updateOrder(...) {
    return ordersRepository.save(...);
}
~~~

The manager name must match the bean configured for that database. A repository or `DatabaseClient` accessing a different database may not participate in the same transaction.

If business logic needs to update multiple independent databases, design an appropriate consistency model—such as saga, outbox, or compensating workflows. Do not assume one `@Transactional` annotation will roll back every database and external service.

## 15. Database errors and transaction state

Some SQL errors can cause the database to mark the transaction as aborted. In that state, even if Spring's rollback rule does not require rolling back on a specific exception, the database may still reject subsequent statements or refuse to commit.

Example of a unique constraint violation:

~~~java
return repository.save(entity)
    .onErrorResume(DuplicateKeyException.class, error ->
        repository.findByNaturalKey(entity.getNaturalKey())
            .then()
    );
~~~

If a duplicate error occurs inside a transaction, recovering and continuing to query depends on the database and the transaction state after the error. Some databases require rolling back the transaction after a statement error. Do not assume `onErrorResume` always allows a transaction to continue.

For database errors, it is usually better to let the transaction roll back and handle retries or fallback responses outside the transaction boundary, unless the database and driver guarantee the transaction state remains usable.

## 16. Retries and rollback

Retries can re-execute a publisher after a transaction fails. Placement of the retry operator is critical.

~~~java
return transactionalOperator.transactional(
        performTransfer()
    )
    .retryWhen(
        Retry.max(2)
            .filter(this::isTransientFailure)
    );
~~~

With this structure, each retry can re-subscribe to the transactional publisher and start a fresh transaction execution, depending on how the operator and subscription are set up. This is generally far better than retrying a statement inside a transaction already marked rollback-only.

Only retry transient errors such as specific connection issues or serialization failures according to system policy. Never retry validation errors, duplicate-key errors, or business errors unconditionally.

Ensure operations are idempotent or protected by an idempotency key if re-execution could cause side effects. A database transaction does not by itself guarantee a request is processed only once.

## 17. Common rollback scenarios table

| Scenario | Default or configured behavior | Notes |
|---|---|---|
| `RuntimeException` exits `@Transactional` | Rollback | Default |
| `Error` exits `@Transactional` | Rollback | Default |
| Checked exception exits `@Transactional` | No rollback by default | Use `rollbackFor` if needed |
| Exception listed in `noRollbackFor` | No rollback requested by that rule | Error can still propagate to caller |
| `onErrorMap` translates exception | Still `onError` | Rules apply to the outgoing error |
| `onErrorResume` inside transaction turns error into empty | May commit | Transaction sees normal completion |
| Error recovered outside `TransactionalOperator` | Operator sees error before recovery | Rolls back first, then recovers |
| Subscriber cancels reactive transaction | Rollback | Avoid cancelling mid-stream when commit is needed |
| SQL error causes database to abort transaction | Usually requires rollback | Depends on database/driver |
| Self-subscribing via `subscribe()` inside service | Can detach from transaction | Return publisher to caller |
| Two different `ConnectionFactory` beans | Do not share transaction by default | Requires separate managers and architecture |

## 18. Common configuration mistakes

### Using @Transactional without a ReactiveTransactionManager

The annotation does not create an R2DBC transaction manager on its own. Configure an appropriate manager or verify auto-configuration created the right bean.

### Picking the wrong transaction manager

An application may have both `PlatformTransactionManager` and `ReactiveTransactionManager`. Specify `transactionManager` explicitly when multiple managers or databases exist.

### Using checked exceptions while forgetting rollbackFor

The exception propagates out, yet the transaction can commit by default. Declare `rollbackFor` for checked exception types that must roll back.

### Swallowing errors with onErrorResume

If an error is turned into normal completion inside a transaction, rollback rules never see that error. Keep the `onError` signal or mark rollback-only explicitly.

### Calling subscribe() manually

A detached subscription can run outside the transaction context and is not awaited by the transaction boundary. Compose publishers instead.

### Putting transaction annotations on methods not returning a Publisher

Reactive transactions require methods to return a reactive type. For `void` or synchronous return types, a reactive transaction manager cannot manage the lifecycle as intended.

### Thinking readOnly blocks all writes

`readOnly` is not a security boundary. Use database permissions and proper validation when writes must be forbidden.

## 19. Testing rollback

Use integration tests with a real R2DBC driver and database or Testcontainers. Rollback tests must verify database state after the publisher completes, not only assert that an exception was emitted.

Scenarios to test:

1. `RuntimeException` after a save operation: earlier data in the transaction is not committed.
2. Checked exception without `rollbackFor`: confirm default declarative transaction behavior.
3. Checked exception with `rollbackFor`: data is rolled back.
4. Exception with `noRollbackFor`: confirm the transaction is allowed to commit if the database still permits commit.
5. Error recovered inside the transaction: check whether the transaction commits due to normal pipeline completion.
6. Error recovered outside `TransactionalOperator`: verify rollback occurs before returning the fallback.
7. Cancellation before completion: verify the transaction rolls back.
8. Multiple repository operations using the same `ConnectionFactory`: confirm they share the same transaction.
9. Multiple `ConnectionFactory` beans: verify the right transaction manager is selected.
10. SQL constraint errors: check whether the database marks the transaction aborted.

Conceptual test example:

~~~java
StepVerifier.create(service.createThenFail())
    .expectError(IllegalStateException.class)
    .verify();

StepVerifier.create(repository.findByNaturalKey("test-key"))
    .verifyComplete();
~~~

The first assertion confirms the publisher emitted an error. The second confirms the data was not committed. Checking `expectError` alone is insufficient to prove rollback occurred.

When testing cancellation, construct a publisher that keeps the transaction open, cancel the subscription, and then query again in a new transaction to confirm data was not committed. Do not use a read inside the cancelled transaction itself as proof.

## 20. Rollback policy decision workflow

Before configuring transactions for a use case:

1. Identify which database operations must commit or roll back together.
2. Identify the transaction manager and `ConnectionFactory` managing those operations.
3. List exceptions that can exit the reactive pipeline.
4. Classify `RuntimeException`, `Error`, and checked exceptions.
5. Choose `rollbackFor` for checked exceptions that genuinely require rollback.
6. Use `noRollbackFor` only when business logic accepts committing even though the exception propagates out.
7. Check whether any `onErrorResume`/`onErrorComplete` swallows errors inside the transaction.
8. Check cancellation, timeouts, and operators that could cancel upstream.
9. Review transaction propagation, isolation, and timeout requirements.
10. Write integration tests verifying data after commit and rollback.

Do not use `rollbackFor = Exception.class` or `noRollbackFor = Exception.class` mechanically. Overly broad rules can alter behavior for unexpected errors.

## 21. Key takeaways

- With `@Transactional`, Spring rolls back `RuntimeException` and `Error` by default; checked exceptions do not roll back by default.
- Use `rollbackFor` to specify checked exceptions that must roll back.
- Use `noRollbackFor` when a specific exception type is still permitted to commit; the error can still propagate to the caller.
- When multiple rollback rules match, the rule most specific to the actual exception takes precedence.
- Reactive methods must return `Mono`/`Flux` or `Publisher` for Spring to apply reactive transactions.
- Errors must exit as `onError` signals for the transaction boundary to apply rollback rules.
- `onErrorResume` inside a transaction can turn an error into completion and cause the transaction to commit.
- Recovering outside `TransactionalOperator` lets the operator roll back before the caller receives a fallback.
- Cancellation of a reactive transaction leads to rollback; avoid early cancellation when full-stream commit is needed.
- `TransactionalOperator` manages transactions programmatically; it does not configure `rollbackFor`/`noRollbackFor` via annotations.
- `R2dbcTransactionManager` manages connections by `ConnectionFactory` and Reactor Context.
- Do not self-subscribe inside services, and do not assume multiple `ConnectionFactory` instances or external services participate in one transaction.
- Tests must verify database state after the transaction, not just check exceptions.
