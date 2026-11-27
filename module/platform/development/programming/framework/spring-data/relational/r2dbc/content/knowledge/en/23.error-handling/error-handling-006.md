# Placing Retry at the Right Scope to Open a New Transaction When Needed

In Spring Data R2DBC applications, a business operation often spans multiple database statements inside a single reactive transaction. When a transaction fails due to a deadlock, serialization conflict, or temporary resource failure, the application sometimes needs to re-run the entire unit of work. Crucially, **retry must sit outside the transaction boundary** whenever each attempt requires a fresh transaction.

Reactor retries work by resubscribing to the source publisher. Consequently, where `retryWhen` sits relative to `TransactionalOperator.transactional(...)` determines which publisher gets resubscribed and whether a new transaction is created. Retrying inside a transaction can re-run statements on the same failed or rollback-only transaction. Retrying outside the transaction allows the failed attempt to roll back completely before the next subscription opens a fresh transaction.

## 1. How Retry Works in a Reactive Pipeline

Reactor retry operators do not "resume from the failing line." When upstream emits an error and the retry policy permits retrying, Reactor resubscribes to the source publisher:

~~~java
Mono<Result> result = operation()
        .retryWhen(Retry.max(3));
~~~

The `operation()` publisher is resubscribed whenever an accepted error occurs. If side effects happen while constructing the publisher rather than during subscription, they may not re-run properly. Therefore, work that must be rebuilt per attempt should be wrapped in `Mono.defer` or `Flux.defer`.

Example:

~~~java
Mono<Result> operation = Mono.defer(() -> callDatabase());
~~~

Each subscription invokes the supplier again and constructs a publisher for that execution. With Spring Data R2DBC, repository publishers are typically lazy, yet `defer` remains useful when building commands, reading clocks, creating objects, or selecting parameters must happen freshly on every attempt.

## 2. Why a Failed Transaction Usually Cannot Be Reused

A database transaction maintains its own state and lifecycle. Upon errors like deadlocks or serialization failures, the database may abort or mark the current transaction for rollback. Some databases, such as PostgreSQL, place a transaction into an aborted state after any statement error; all subsequent statements in that transaction continue failing until rollback.

Therefore, retrying only the failing statement inside the same transaction rarely solves the problem. To retry a business operation after a transaction error, you must:

1. Let the current transaction receive the failure.
2. Roll back that transaction and release its resources.
3. Start a new transaction.
4. Re-run the entire consistent unit of work.

This is especially critical for serialization failures and deadlocks: the database typically requires re-running the entire transaction because earlier reads may no longer be valid.

## 3. Placing Retry Outside TransactionalOperator

This is the standard pattern with `TransactionalOperator`:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> oneAttempt = transactionalOperator.transactional(
            Mono.defer(() -> createOrderWork(command))
    );

    return oneAttempt.retryWhen(retryPolicy);
}

private Mono<Order> createOrderWork(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(saved ->
                    orderLineRepository.saveAll(
                            toLines(saved.id(), command.items())
                    ).thenReturn(saved)
            )
            .flatMap(saved ->
                    auditRepository.save(toAudit(saved.id()))
                            .thenReturn(saved)
            );
}
~~~

The sequence here is:

1. `transactional(...)` creates a publisher representing one transactional execution.
2. `retryWhen(...)` wraps that transactional publisher.
3. If an attempt emits a retryable error, the transaction operator performs rollback and finishes the attempt.
4. Retry resubscribes to the transactional publisher.
5. The new subscription begins a new transaction and re-runs `createOrderWork`.

Because retry sits outside the transactional publisher, the new attempt gets a fresh connection/transaction from the same transaction manager. Not only the final statement is retried; the entire `createOrderWork` runs again to preserve business consistency.

## 4. What Goes Wrong When Placing Retry Inside a Transaction?

Error-prone example:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work = Mono.defer(() -> createOrderWork(command))
            .retryWhen(retryPolicy);

    return transactionalOperator.transactional(work);
}
~~~

In this structure, the transaction operator wraps a publisher that already embeds retry. When `work` fails, the inner `retryWhen` catches the error and resubscribes to `work` before the error reaches the transaction operator. Retries can stay inside the same transaction context and reuse the same transaction.

If the database already marked the transaction rollback-only or aborted, the next attempt executes on an unusable transaction. Even if the inner publisher later completes, the transaction may still roll back or fail on commit.

| Structure | Retry targets | Transaction outcome |
| --- | --- | --- |
| `transactional(work).retryWhen(retry)` | Transactional publisher | Each new subscription can open a new transaction |
| `transactional(work.retryWhen(retry))` | Work publisher inside transaction | Attempts may reuse the existing transaction |

Whenever each attempt needs a fresh transaction, place retry outside `transactional(...)`.

## 5. Example Retry Policy with Backoff and Limits

Never retry indefinitely or instantaneously. Use `Retry.backoff` to cap attempts and progressively increase wait times:

~~~java
private Retry retryPolicy() {
    return Retry.backoff(3, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(2))
            .jitter(0.5)
            .filter(this::isRetryable)
            .doBeforeRetry(signal ->
                    log.warn(
                            "Retrying transaction, attempt={}, cause={}",
                            signal.totalRetries() + 1,
                            signal.failure().toString()
                    )
            )
            .onRetryExhaustedThrow((spec, signal) ->
                    signal.failure()
            );
}
~~~

In Reactor, the `maxAttempts` parameter of `Retry.backoff(maxAttempts, ...)` specifies the maximum retries after the initial execution. For instance, `3` allows up to one initial run plus three retries. When capping total attempts, count the initial run plus retries explicitly.

Backoff eases database pressure when many requests fail together. Jitter adds randomness so requests do not retry in lockstep. `maxBackoff` caps the maximum delay.

## 6. Only Retry Potentially Transient Errors

Not every error clears up when retried. Classify failures before configuring retries:

| Error category | Usually retry? | Reason |
| --- | --- | --- |
| Deadlock victim | Maybe | Transaction was aborted due to contention; a fresh attempt may succeed |
| Serialization failure | Maybe | Database requires re-running the transaction against a new snapshot |
| Transient resource/connection error before commit | Maybe | Resources may recover |
| Lock unavailable with NOWAIT | Depends on business rules | Retry with backoff if waiting is desired |
| Unique constraint violation | Usually no | Input data or state already conflicts; repeating verbatim usually fails again |
| Foreign key violation | No | Typically invalid data or wrong business ordering |
| SQL syntax/column mapping error | No | Retrying cannot fix broken SQL |
| Authentication/permission error | No | Requires fixing configuration or privileges |
| Validation error | No | Requires fixing input data |
| Query canceled or client cancellation | Not by default | Caller canceled or query was aborted; do not restart unconditionally |

Spring can translate R2DBC errors into `DataAccessException` types; drivers also have their own exceptions. Retry predicates should rely on translated types, SQLSTATE/vendor codes, or an application classifier. Avoid matching message strings since messages vary across drivers and versions.

Skeleton predicate example:

~~~java
private boolean isRetryable(Throwable error) {
    if (error instanceof TransientDataAccessException) {
        return true;
    }

    // Add classification by SQLSTATE or error code
    // for the database/driver your application uses.
    return isKnownTransientDatabaseFailure(error);
}
~~~

`isKnownTransientDatabaseFailure` is an application-defined classifier, not a built-in Spring API. Include only errors confirmed to be recoverable and safe to re-run.

## 7. SQLSTATE and Database Transaction Errors

In PostgreSQL, several SQLSTATE codes are relevant when designing retries:

| SQLSTATE | Error name | Common handling |
| --- | --- | --- |
| `40001` | serialization_failure | Roll back and retry the entire transaction |
| `40P01` | deadlock_detected | Roll back and consider retrying the entire transaction |
| `55P03` | lock_not_available | Retry only if business NOWAIT/lock policy allows |
| `57014` | query_canceled | Do not auto-retry if caused by timeout or caller cancellation |

These are PostgreSQL codes; other databases use different error codes and semantics. Some connection errors fall under SQLSTATE `08xxx`, yet connection errors near commit time can yield ambiguous outcomes: the server may have committed while the client lost the response.

When drivers or Spring wrap exceptions, SQLSTATE may live on an inner root cause or driver metadata. Inspect the exception chain and driver documentation instead of assuming every exception preserves the same class or fields.

## 8. Opening Fresh Transactions with TransactionalOperator and Retry

Complete example:

~~~java
@Service
public class PaymentService {

    private final TransactionalOperator transactionalOperator;
    private final PaymentRepository paymentRepository;
    private final LedgerRepository ledgerRepository;

    public PaymentService(
            TransactionalOperator transactionalOperator,
            PaymentRepository paymentRepository,
            LedgerRepository ledgerRepository) {
        this.transactionalOperator = transactionalOperator;
        this.paymentRepository = paymentRepository;
        this.ledgerRepository = ledgerRepository;
    }

    public Mono<Payment> process(PaymentCommand command) {
        Retry retry = Retry.backoff(3, Duration.ofMillis(150))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isRetryable)
                .onRetryExhaustedThrow((spec, signal) ->
                        signal.failure()
                );

        Mono<Payment> oneTransaction = transactionalOperator.transactional(
                Mono.defer(() ->
                        paymentRepository.save(toPayment(command))
                                .flatMap(payment ->
                                        ledgerRepository.save(
                                                toLedgerEntry(payment)
                                        ).thenReturn(payment)
                                )
                )
        );

        return oneTransaction.retryWhen(retry);
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof TransientDataAccessException;
    }
}
~~~

Each resubscription to `oneTransaction` activates the transaction operator anew. If the error is a classified deadlock or serialization conflict, the previous attempt rolls back before the retry begins.

The predicate here is purely illustrative. In production applications, verify Spring Data and driver exception translation and add database-specific error codes. Never assume every `TransientDataAccessException` is safe to retry if the operation has non-idempotent side effects or an ambiguous commit outcome.

## 9. Using `@Transactional`: Placing Retry in an Outer Service

With declarative transactions, extract the single-attempt execution into a separate `@Transactional` bean while the orchestrating bean applies retry outside:

~~~java
@Service
public class OrderTransaction {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;

    public OrderTransaction(
            OrderRepository orderRepository,
            OrderLineRepository lineRepository) {
        this.orderRepository = orderRepository;
        this.lineRepository = lineRepository;
    }

    @Transactional
    public Mono<Order> executeOnce(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command))
                .flatMap(order ->
                        lineRepository.saveAll(toLines(order.id(), command))
                                .thenReturn(order)
                );
    }
}
~~~

Facade:

~~~java
@Service
public class OrderFacade {

    private final OrderTransaction orderTransaction;
    private final Retry retryPolicy;

    public OrderFacade(
            OrderTransaction orderTransaction,
            Retry retryPolicy) {
        this.orderTransaction = orderTransaction;
        this.retryPolicy = retryPolicy;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        return orderTransaction.executeOnce(command)
                .retryWhen(retryPolicy);
    }
}
~~~

Calls across Spring beans pass through the transaction proxy. The publisher returned by `executeOnce` is wrapped in a transaction; the facade's retry resubscribes to that publisher, so each new subscription can open a fresh transaction.

Avoid putting `@Transactional` on the facade itself while also placing `retryWhen` inside that method if you want a new transaction per attempt. Doing so puts retry inside the publisher owned by the facade's transaction.

Additionally, self-invocation (one method calling another `@Transactional` method on `this`) usually bypasses the proxy and skips the annotation. Separating beans or using `TransactionalOperator` makes boundaries explicit.

## 10. Retry the Entire Business Unit, Not Only the Last Statement

Suppose a transaction performs:

1. Read account balance.
2. Check limits.
3. Debit source account.
4. Credit destination account.
5. Write audit log.

If a serialization error occurs at step 4, the balance read at step 1 may already be stale. Retrying only step 4 would act on business decisions computed from stale reads. The right approach is rolling back and re-running the entire workflow from step 1 in a fresh transaction.

Example retry scope:

~~~java
Mono<TransferResult> oneAttempt =
        transactionalOperator.transactional(
                Mono.defer(() -> readValidateAndTransfer(command))
        );

return oneAttempt.retryWhen(retryPolicy);
~~~

Never attach retry solely around `ledgerRepository.save(...)` if its outcome depends on values read earlier inside the failed transaction.

## 11. Idempotency Before Retrying Write Operations

Retries can execute an operation multiple times. The riskiest case is losing connectivity after the server committed yet before the client received the response:

1. Database commits successfully.
2. Connection drops before the application gets the result.
3. Application sees a connection error and cannot know whether commit succeeded.
4. Retry creates a second record or repeats a side effect.

This is an ambiguous outcome. Increasing retry counts cannot solve it.

For critical writes, design for idempotency:

- Accept a stable idempotency key from the request.
- Store the key with a unique constraint in the same database.
- Associate the business result with that key.
- When the request is resent, read the stored outcome instead of executing the business effect a second time.
- Ensure idempotency records and business data update within the same transaction.

Example schema:

~~~sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    payment_id BIGINT NOT NULL,
    result_status VARCHAR(30) NOT NULL
);
~~~

A retried request carrying the same key finds the already-processed outcome. Duplicate insert handling should match your database and domain—such as querying the existing result or using appropriate upsert syntax.

## 12. Retries and Unique Constraints

Unique constraint violations are usually not transient failures. Retrying the same `INSERT` with identical data typically hits the same constraint again.

However, a unique constraint can be part of an idempotency strategy: when inserting an already-present key fails, the application reads the existing record and returns the previous result. That is intentional conflict recovery, not blind retrying.

Distinguish:

- **Retry:** re-running work after a verified transient error.
- **Conflict recovery:** detecting a record already exists and reading its existing outcome.
- **Upsert:** using database semantics to insert or update on constraint conflict.

Do not merge all three mechanisms into a single generic `retryWhen(Retry.max(...))`.

## 13. Backoff, Jitter, and Overall Deadlines

Retries must fit within the request or job time budget. If each attempt takes 3 seconds, with 3 retries and 2 seconds total backoff, total duration can exceed the HTTP deadline.

A policy should define:

- Maximum retry attempts.
- Initial and maximum backoff.
- Jitter.
- Retryable error filter.
- Overall deadline.
- Exhaustion behavior.

Example:

~~~java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.5)
        .filter(this::isRetryable)
        .doBeforeRetry(signal ->
                log.warn(
                        "Retry attempt {} after {}",
                        signal.totalRetries() + 1,
                        signal.failure().getClass().getSimpleName()
                )
        );

return oneTransaction
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(8));
~~~

The outermost timeout caps total retry duration. When timeout triggers, the active subscription cancels; any open transaction should be handled by the transaction manager upon cancellation. Do not automatically retry timeouts unless explicitly permitted by policy and safe for the operation.

If you need separate per-attempt timeouts and an overall deadline, place timeouts at two positions while understanding which publisher cancels and which transaction is open. Avoid unintended overlapping timeouts.

## 14. Retrying on Deadlocks or Serialization Failures

Deadlocks and serialization failures generally require re-running the entire transaction. General pattern:

~~~java
Mono<Result> oneAttempt = transactionalOperator.transactional(
        Mono.defer(() -> executeBusinessUnit(command))
);

Retry retry = Retry.backoff(3, Duration.ofMillis(50))
        .maxBackoff(Duration.ofSeconds(1))
        .filter(this::isDeadlockOrSerializationFailure);

return oneAttempt.retryWhen(retry);
~~~

Each attempt gets its own transaction, giving the database a chance to pick a different execution order or fresh snapshot on the next try.

Do not retry aggressively under heavy contention. If every request retries relentlessly, load spikes and creates even more deadlocks. Use backoff, jitter, concurrency limits, and consistent row access ordering.

## 15. Do Not Retry Cancellation as a Normal Transient Error

Cancellation usually signals that the subscriber no longer wants the result. Reactor retries handle error signals, not normal cancellation signals. Do not turn cancellations into retryable errors by arbitrarily mapping every outcome to an exception.

A timeout can cancel the source publisher and emit a timeout error downstream. If a predicate allows retrying timeouts, verify:

- The previous attempt's transaction has rolled back and cleaned up before retrying.
- The statement can stop cleanly or will not trigger duplicate side effects.
- Enough overall deadline remains.
- The client still wants the result.

If an HTTP client has already disconnected, re-running a write operation wastes resources and causes unwanted effects. Background jobs may have different cancellation semantics and explicit resumption rules.

## 16. Avoid Nested Retries Across Layers

Suppose the repository layer retries 3 times and the service layer also retries 3 times. A single request could generate up to 4 × 4 = 16 executions depending on attempt counting and operator placement.

Nested retries increase:

- Total queries and connection usage.
- Request latency.
- Difficulty reading logs and counting attempts.
- Risk of duplicate effects.
- Pressure on a struggling database.

Choose one layer to own the retry policy for a given unit of work. For transaction errors like deadlocks or serialization conflicts, the service/use-case layer is usually best because it understands the entire transaction that must re-run.

If an underlying client or driver already retries internally, factor that into your overall retry budget. Avoid letting each layer retry independently without a shared cap.

## 17. Logging and Observing Retries

Each attempt should provide enough context for analysis:

- Correlation ID or request/job ID.
- Business operation and transaction name.
- Current retry attempt number.
- Exception type and SQLSTATE/vendor code if available.
- Execution time and backoff duration.
- Final outcome: success, exhausted, timeout, or cancellation.

Example:

~~~java
.doBeforeRetry(signal ->
        log.warn(
                "Retrying createOrder, attempt={}, exception={}",
                signal.totalRetries() + 1,
                signal.failure().getClass().getName()
        )
)
~~~

Never log full payment payloads, personal data, or sensitive fields. Keep metric labels bounded in cardinality; do not use user IDs or request IDs as metric tags.

## 18. Testing to Confirm Each Retry Opens a New Transaction

Unit tests with stubbed publishers can verify resubscription counts, yet they do not prove the transaction manager created a fresh transaction. Integration tests against a database are needed:

1. Seed initial data.
2. On the first attempt, perform a mutation and emit a retryable transaction error.
3. Verify the first attempt rolled back.
4. Let the next attempt run and complete.
5. Verify final database state reflects only one successful execution.
6. Observe transactions/connections appropriately to confirm the new attempt used a fresh transaction.

You can use `AtomicInteger` to simulate a first-attempt error:

~~~java
AtomicInteger attempts = new AtomicInteger();

Mono<Result> oneTransaction = transactionalOperator.transactional(
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            return repository.save(createRow(attempt))
                    .flatMap(saved -> attempt == 1
                            ? Mono.error(new SimulatedTransientFailure())
                            : Mono.just(toResult(saved))
                    );
        })
);

return oneTransaction.retryWhen(Retry.max(1));
~~~

This test illustrates resubscription mechanics rather than fully reproducing real database deadlocks or serialization failures. To verify true rollback, query database state after each scenario or trigger reproducible real database errors.

Scenarios worth testing:

- Retryable failure on first attempt followed by success.
- Non-retryable failure stopping after one attempt.
- Exhausting max retries.
- Transaction rolling back before the next attempt starts.
- Failure at the final step of a multi-statement workflow.
- Timeout/cancellation while an attempt is running.
- Connection loss near commit time and idempotency behavior.
- Concurrent requests triggering a deadlock or serialization conflict.

## 19. Common Mistakes

1. **Placing retry inside a transaction.** Attempts can reuse the same failed or rollback-only transaction.
2. **Retrying only the final statement.** Prior reads and business decisions may be stale.
3. **Retrying every exception.** Validation, SQL syntax, unique, and foreign key errors rarely clear up on retry.
4. **Infinite retries or no backoff.** Amplifies load on an unhealthy database.
5. **No jitter.** Requests retry simultaneously and cause a retry storm.
6. **No overall deadline.** Total execution can exceed request timeouts.
7. **Retrying non-idempotent writes.** Losing a response after commit can run business logic twice.
8. **Assuming connection loss means rollback.** The client cannot know whether the server committed.
9. **Swallowing errors inside the transaction and retrying outside.** Once recovered to completion, outer retry sees no error to trigger on.
10. **Combining `@Transactional` and retry in the same method at the wrong scope.** The proxy may wrap the publisher outside retry, preventing fresh transactions per attempt.
11. **Self-invoking `@Transactional` methods.** Internal calls typically bypass Spring proxies.
12. **Nesting retries across repository, service, and client.** Actual execution counts multiply exponentially.
13. **Retrying cancellations.** Callers may have abandoned the request; never restart unconditionally.
14. **Not logging attempts and causes.** Makes distinguishing root errors from post-retry failures hard.

## Quick Selection Rules

- When transaction failures require re-running the entire business operation, place retry **outside** `TransactionalOperator.transactional(...)`.
- Use `Mono.defer` or `Flux.defer` to rebuild work for each attempt when needed.
- With `@Transactional`, place retry on an outer caller/bean outside the transaction proxy so every subscription crosses a fresh transaction boundary.
- Retry with caps, backoff, jitter, and a predicate accepting only confirmed transient failures.
- Re-run the entire transaction when earlier reads may have become stale.
- Design idempotency for writes and handle ambiguous commit outcomes.
- Never generically retry validation, SQL syntax, permission, or constraint violations.
- Coordinate retries with deadlines, cancellation, and connection pool limits.
- Avoid nested retries across layers; assign policy ownership to one layer.
- Test rollbacks and fresh transactions against the target database and driver.

Retries are safe only when scoped properly and paired with accurate error classification. In Spring Data R2DBC, whenever each attempt needs a fresh transaction, keep the transactional publisher inside the retried publisher: `transactional(work).retryWhen(policy)`. Each resubscription opens a fresh transaction attempt after the previous one closes. Combining this operator placement with bounded retries, error filtering, backoff, idempotency, and integration tests handles deadlocks and serialization conflicts without reusing broken transactions or creating duplicate writes.
