# Bounded Retries, Backoff, and Retryable Error Conditions

In Spring Data Relational R2DBC, queries and write operations execute asynchronously through `Mono` or `Flux`. Some failures are strictly transient, such as a brief database connectivity interruption, temporary pool exhaustion, or the database rejecting a transaction due to concurrent contention. For suitable failures, the application can resubscribe to the publisher to attempt the operation again.

Retries must not be applied to every exception. SQL syntax errors, type mismatches, constraint violations, insufficient privileges, or invalid input data will not disappear after waiting. Retrying those failures only repeats the same error and creates unnecessary load. A sound retry policy requires a maximum retry count, backoff between attempts, a predicate identifying retryable errors, and an overall time limit.

In Reactor, the `Retry` API combined with `retryWhen` expresses those rules. When used with R2DBC, you must also consider transaction boundaries and idempotency: retrying a write operation can re-run SQL after the database already executed it successfully while the client simply lost the response.

## 1. What Does Retry Mean in a Reactive Pipeline?

Retrying means resubscribing to the source publisher after it emits `onError`. Reactor does not resume from the exact failing statement; it resubscribes upstream according to how that publisher was constructed.

Example:

```java
Mono<Customer> customer = customerRepository.findById(42L)
        .retry(2);
```

If the query fails, Reactor can resubscribe to the source up to two additional times. With a cold Spring Data R2DBC publisher, each subscription typically re-executes the database operation. If the source completes normally—including an empty completion—retry does not trigger.

With `retry(2)`, `2` is the number of resubscriptions after the initial attempt, not the total execution count. At most three executions occur: the initial attempt plus two retries.

### Retry does not handle empty completion

A repository `findById` that finds no row usually returns `Mono.empty()`. That is a normal completion, not an error. Therefore:

```java
customerRepository.findById(id)
        .retry(3);
```

will not re-query simply because no customer was found. If action is needed when data does not exist, use `switchIfEmpty`. Retries apply to error signals classified as recoverable.

### Retry does not automatically create a new transaction

`retryWhen` resubscribes to the upstream publisher. Whether each attempt gets a fresh transaction depends on where retry sits relative to the transaction boundary. This is especially critical in R2DBC and is covered in the transaction section below.

## 2. Distinguishing Transient from Unrecoverable Errors

No single retryable error list fits every database. Decisions must be based on the exception types emitted by the driver, Spring's exception translation, and database semantics.

Common categories:

| Error category | Examples | Should you retry? |
| --- | --- | --- |
| Transient resource error | Connection temporarily unavailable, interrupted resource | Maybe, with time and attempt limits |
| Temporary timeout | Query timeout from brief overload or slow link | Maybe, if retries still fit within the business deadline |
| Transaction conflict | Deadlock or serialization conflict | Maybe, usually requires re-running the entire transaction |
| Connection loss | Connection reset, database failover | Maybe, though write outcomes may be ambiguous |
| SQL syntax error | Wrong table/column name, invalid SQL | No |
| Data error | Type mismatch, out-of-range value, invalid JSON | No |
| Constraint violation | Duplicate key, foreign key, check constraint | Usually no; handle per business rules |
| Auth/privilege error | Invalid credentials, missing privileges | No, unless a dedicated credential refresh flow exists |
| Row not found | `Mono.empty()` or update count of 0 | Not a retryable error by default |

### Exception types useful for classification

The R2DBC SPI defines exception classes including:

- `R2dbcTransientException`: error classified as transient.
- `R2dbcTransientResourceException`: transient resource failure, a subtype of transient exception.
- `R2dbcTimeoutException`: timeout failure expressed by the driver via the SPI.
- `R2dbcNonTransientException`: error classified as non-transient.

Spring also provides a DAO exception hierarchy, such as `TransientDataAccessException` for potentially transient data access failures. Exactly which Spring type an error translates to depends on the translator, driver, and version. Some drivers may nest the root exception inside the cause chain.

Do not inspect class names via string matching or catch every `DataAccessException`. Verify actual exceptions in your application's environment, then write retry predicates matching confirmed error types.

## 3. Bounded Retries with `Retry.max`

Reactor provides `Retry.max(maxAttempts)` to retry up to a fixed count without intentional delay:

```java
Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(Retry.max(2));
```

`Retry.max(2)` allows up to two retries after the initial attempt. This is concise, but attempts fire back-to-back. When a database is overloaded or just lost connectivity, immediate retries can amplify load and create feedback pressure.

You can use `Retry.fixedDelay` for a constant pause:

```java
Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(Retry.fixedDelay(
                3,
                Duration.ofMillis(250)
        ));
```

This example allows three retries spaced about 250 ms apart. For sustained outages or many concurrent failing requests, exponential backoff is usually more suitable.

## 4. Exponential Backoff

Exponential backoff increases the wait duration after each retry. Reactor provides `Retry.backoff(maxAttempts, minBackoff)`:

```java
Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(Retry.backoff(
                3,
                Duration.ofMillis(100)
        ));
```

Wait durations grow with each attempt, starting from the configured minimum. The policy can also enforce an upper bound:

```java
Retry retryPolicy = Retry.backoff(
            4,
            Duration.ofMillis(100)
        )
        .maxBackoff(Duration.ofSeconds(2));
```

Backoff gives the database breathing room to recover instead of absorbing rapid-fire attempts. However, delays should not grow without limit. `maxBackoff` caps the maximum wait between retries.

### Jitter prevents concurrent client retry storms

If thousands of requests fail together and all retry after exactly 100 ms, they can strike the database simultaneously again. This phenomenon is known as a *thundering herd*.

Jitter adds random variance to wait durations:

```java
Retry retryPolicy = Retry.backoff(
            4,
            Duration.ofMillis(100)
        )
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5);
```

`jitter(0.5)` allows Reactor to vary the wait around the computed backoff within the configured jitter factor, making simultaneous retries far less likely. Choose a jitter level suited to your system's deadlines and load profile.

## 5. Only Retry Allowed Exceptions

A retry policy should include a filter predicate. For instance, retry only exceptions identified as transient:

```java
private boolean isRetryable(Throwable error) {
    for (Throwable cause = error;
         cause != null;
         cause = cause.getCause()) {

        if (cause instanceof R2dbcTransientException
                || cause instanceof TransientDataAccessException
                || cause instanceof TimeoutException) {
            return true;
        }
    }

    return false;
}
```

Relevant imports:

```java
import io.r2dbc.spi.R2dbcTransientException;
import org.springframework.dao.TransientDataAccessException;

import java.util.concurrent.TimeoutException;
```

This snippet walks the cause chain because real exceptions may be wrapped across multiple layers. The list above is only a starting point; add or remove types based on your application's driver and exception translation behavior. Not every `TimeoutException` is safe to retry, especially when a timeout happens after a write command may already have been executed by the database.

Applying the predicate:

```java
Retry retryPolicy = Retry.backoff(
            3,
            Duration.ofMillis(150)
        )
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isRetryable);

Mono<Customer> result = customerRepository.findById(id)
        .retryWhen(retryPolicy);
```

If an error fails the predicate, Reactor forwards it downstream immediately without waiting or retrying.

### Do not mechanically retry duplicate keys

A duplicate key usually indicates existing data or a race condition. Retrying the same `INSERT` with the same key normally triggers the same error again. Instead, choose clear semantics: return conflict, read the existing record, use upsert, or handle an idempotency key.

### Do not retry validation or SQL grammar errors

Type mismatches, SQL syntax bugs, missing columns, or constraint violations require code or data fixes. Retrying will not make an invalid statement valid.

## 6. Creating a Reusable Retry Policy

Centralize configuration in a method or bean rather than scattering magic numbers across services:

```java
@Configuration
public class RetryConfiguration {

    @Bean
    Retry r2dbcRetryPolicy() {
        return Retry.backoff(3, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isRetryable)
                .doBeforeRetry(signal -> log.warn(
                        "Retry R2DBC attempt={}, cause={}",
                        signal.totalRetries() + 1,
                        signal.failure().getClass().getSimpleName()
                ));
    }

    private boolean isRetryable(Throwable error) {
        for (Throwable cause = error;
             cause != null;
             cause = cause.getCause()) {
            if (cause instanceof R2dbcTransientException
                    || cause instanceof TransientDataAccessException) {
                return true;
            }
        }
        return false;
    }
}
```

This is an illustrative configuration; declare the appropriate logger and imports in your project. Never log full SQL, bind values, tokens, or sensitive data in retry logs. Exception class and attempt count are usually enough for initial triage.

`Retry` is a reusable strategy; never store mutable per-request business state inside a shared retry bean. Each subscription maintains its own retry signal state.

## 7. Attempt Counts: Retry Count vs. Total Attempts

Reactor uses `maxAttempts` for the maximum number of retries, excluding the initial subscription.

| Configuration | Maximum executions |
| --- | ---: |
| No retry | 1 |
| `Retry.max(1)` | 2 |
| `Retry.max(2)` | 3 |
| `Retry.backoff(3, ...)` | 4 |

If business requirements say "try at most 3 times total," the max retry count is usually `2`, because the initial execution already counts as one attempt. Name variables and log fields clearly to prevent confusion.

`RetrySignal.totalRetries()` starts at 0 for the first retry. When logging retry numbers for operators, add 1 so the first retry reads as 1.

## 8. Logging and Observing Retries

Retries must be observable. Without logs or metrics, a system could be retrying continuously while operators only notice rising latency.

Reactor exposes hooks like `doBeforeRetry` and `doAfterRetry` on retry specs:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isRetryable)
        .doBeforeRetry(signal -> log.warn(
                "Database operation failed; retry={}, errorType={}",
                signal.totalRetries() + 1,
                signal.failure().getClass().getSimpleName()
        ));
```

Track:

- Retry count by operation and exception type.
- Requests that ultimately succeed after retrying.
- Requests that fail after exhausting retries.
- Backoff wait times and total latency.
- Rates of timeouts, connection failures, deadlocks, or serialization conflicts.
- Connection pool pending acquisitions and connection wait time.

Never put sensitive IDs, SQL text containing user data, or secrets into metric labels; high cardinality can also overload metrics backends.

### Placing `doOnError` before vs. after retry

Operator order determines which errors are observed:

```java
source
    .doOnError(error -> log.warn("Single source attempt failed", error))
    .retryWhen(retryPolicy)
    .doOnError(error -> log.error("Finally failed", error));
```

`doOnError` before `retryWhen` observes each failing upstream execution. `doOnError` after `retryWhen` observes the final failure emitted downstream, whether an unretryable error or a failure after exhausting retries.

Avoid logging full stack traces on every retry during a major outage if doing so adds log I/O pressure. Log concise summaries per retry and full diagnostics on the final failure.

## 9. Handling Exhausted Retries

When retries are exhausted, Reactor by default emits a `RetryExhaustedException` wrapping the final failure. You can configure it to re-emit the last underlying failure for upper layers to handle:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(100))
        .filter(this::isRetryable)
        .onRetryExhaustedThrow((spec, signal) -> signal.failure());
```

To emit a specific business error, map it after retry:

```java
return repository.findById(id)
        .retryWhen(retryPolicy)
        .onErrorMap(this::isRetryable,
                error -> new CustomerStoreUnavailableException(error));
```

Map remaining retryable errors only when that matches what the service intends to expose. Never turn every error into "database unavailable," because validation or constraint failures need distinct semantics.

To preserve the original exception, use `onRetryExhaustedThrow` as in the earlier example. Keep the choice between propagating the last error and wrapping it consistent across your API and observability layers.

## 10. Retries and Timeouts: Bounding Overall Time

Capping retry count alone does not guarantee a request completes within an acceptable timeframe. Each attempt can run up to the driver or query timeout, plus backoff delays.

You can place a per-attempt timeout and an overall chain timeout:

```java
Mono<Customer> result = Mono.defer(() ->
            customerRepository.findById(id)
        )
        .timeout(Duration.ofSeconds(2))
        .retryWhen(retryPolicy)
        .timeout(Duration.ofSeconds(7));
```

In this example:

- The 2-second timeout precedes `retryWhen`, bounding each individual subscription to the source.
- `retryWhen` can resubscribe after a timeout error if the predicate allows it.
- The 7-second timeout follows `retryWhen`, bounding the total duration of the retry sequence.

The outer timeout can cancel the pipeline while waiting on backoff or executing an attempt. Cancellation propagates upstream; for transactions, ensure the transaction manager handles cleanup and rollback properly.

Do not set an overall timeout shorter than a single attempt plus backoff while expecting multiple retries to run. Budget deadlines using query duration, retry count, backoff, and application processing time.

### Retry budget

HTTP requests usually carry a deadline from the gateway or client. Retries must fit inside the remaining time budget. For example, if only 1 second remains before the deadline while the next backoff is 2 seconds, retrying helps no one and wastes held resources.

Cap `maxBackoff`, total timeout, and retry counts; in complex systems, propagate deadline/cancellation budgets across services so layers do not retry past the shared budget.

## 11. Retries Can Re-Execute the Entire Upstream

Where `retryWhen` sits matters greatly. Reactor resubscribes to everything upstream of the retry operator, so any step there can run again.

Example:

```java
return repository.findById(id)
        .flatMap(customer -> externalService.loadDetails(customer))
        .retryWhen(retryPolicy);
```

If `externalService.loadDetails` fails and the predicate permits retrying, the repository query also runs again. If you want to retry only a specific step, attach retry directly to that publisher:

```java
return repository.findById(id)
        .flatMap(customer ->
                externalService.loadDetails(customer)
                        .retryWhen(externalRetryPolicy)
        );
```

Similarly, if a chain of read, compute, and write is wrapped in retry, the entire chain can repeat. Define clear boundaries for retryable operations and evaluate every side effect upstream.

### `defer` rebuilds work on each attempt

When a fresh publisher must be constructed per subscription, use `Mono.defer`:

```java
return Mono.defer(() -> customerRepository.findById(id))
        .retryWhen(retryPolicy);
```

Standard R2DBC publishers are already lazy, yet `defer` remains useful when factory methods, statement building, or fresh state lookups must re-run per attempt. Ensure data/commands are rebuilt intentionally; never generate a new business identifier per retry if the operation requires a stable idempotency key.

## 12. Retrying Reads vs. Writes

### Read operations

Reads are generally easier to retry because reading again creates no new data. Example:

```java
public Mono<Customer> getCustomer(Long id) {
    return Mono.defer(() -> customerRepository.findById(id))
            .retryWhen(readRetryPolicy);
}
```

Still, a retried read can observe different data if changes occurred between attempts. If business logic requires a consistent snapshot, consider transaction isolation and timing.

### Write operations

Retrying writes demands greater caution. Suppose the application sends an `INSERT`, the database commits successfully, and the connection drops before the client receives the response. The client sees an error and cannot tell whether the row was created. Retrying the same statement can trigger a duplicate key error.

Likewise, retrying a balance increment or payment submission can execute side effects twice if the first attempt committed.

Before retrying a write, answer:

- Could the database have executed the statement before the error appeared?
- Would re-sending the command produce additional side effects?
- Is there a unique key or idempotency key identifying the same request?
- Can state be queried to check whether the previous attempt succeeded?
- Does each retry attempt run inside a fresh transaction?

Never treat a connection failure as proof that the database did not write the data.

## 13. Idempotency Protects Writes During Retries

An operation is idempotent if executing the same request multiple times leaves the final business state identical to executing it once.

Example setting status to a fixed value:

```sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = 42;
```

Repeating the same command leaves `status` as `ACTIVE`, making it idempotent at that data level. By contrast:

```sql
UPDATE account
SET balance = balance + 100
WHERE id = 42;
```

executed twice adds 200 rather than 100. This operation is not idempotent.

### Using an idempotency key

For commands that create transactions, attach a unique request key and persist it alongside the outcome:

```sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Every logical request keeps the same `idempotency_key` across retries. The database unique constraint prevents creating two rows for the same request. Upon a duplicate key conflict, the service can read the record by key and return the stored outcome if the payload matches.

Generate the idempotency key once at request intake and reuse it across retries. Never generate a new key inside `defer` when each retry represents the same logical request.

### Upsert and conflict handling

Some databases support upsert syntax such as PostgreSQL `INSERT ... ON CONFLICT`. Upserts can make create-or-update steps more atomic than read-then-insert. However, conflict-update semantics must be carefully designed; an upsert does not automatically make external side effects idempotent.

## 14. Retries and Reactive Transactions: A New Transaction per Attempt

This is a vital rule when retrying writes in R2DBC.

If retry sits inside an already open transaction, subsequent attempts can continue running in the same transaction context. After a SQL failure, the database may mark the current transaction as failed/aborted, or the connection may no longer be usable. Merely resubscribing to a statement inside a broken transaction is not equivalent to starting a clean transaction.

For transactional operations, place the transaction boundary **inside** the retried publisher so each retry subscription opens a fresh transaction. When an attempt fails, its transaction rolls back and cleans up before the next attempt begins.

### Using `TransactionalOperator`

```java
public Mono<Customer> updateCustomer(Long id, String name) {
    return Mono.defer(() ->
            transactionalOperator.transactional(
                    customerRepository.findById(id)
                            .switchIfEmpty(Mono.error(
                                    new CustomerNotFoundException(id)
                            ))
                            .flatMap(customer -> {
                                customer.setName(name);
                                return customerRepository.save(customer);
                            })
            )
    ).retryWhen(writeRetryPolicy);
}
```

`Mono.defer` builds a transactional publisher per upstream subscription. `retryWhen` wraps `TransactionalOperator`, so each retry resubscribes to `defer` and starts a new transaction. When an attempt errors, the transaction operator intercepts it and rolls back before the retry policy schedules the next attempt.

This remains safe only when the write operation is safe to retry in business terms and errors are properly classified. Creating a new transaction does not solve the case where a previous write committed yet the response was lost; idempotency is still required.

### Using a separate bean with `@Transactional`

Another pattern isolates the transactional unit into its own bean:

```java
@Service
public class CustomerWriteTransaction {

    @Transactional
    public Mono<Customer> update(Long id, String name) {
        return customerRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(id)
                ))
                .flatMap(customer -> {
                    customer.setName(name);
                    return customerRepository.save(customer);
                });
    }
}
```

An outer service applies retry:

```java
public Mono<Customer> updateWithRetry(Long id, String name) {
    return Mono.defer(() -> transactionWorker.update(id, name))
            .retryWhen(writeRetryPolicy);
}
```

Calling `transactionWorker.update(...)` goes through the Spring proxy. Whenever `defer` invokes the proxy method and subscribes to the returned publisher, the transaction interceptor can open a new transaction. Avoid self-invocation of `@Transactional` methods within the same object because internal calls typically bypass the proxy.

### Do not place retry inside a transactional method when a fresh transaction is needed

Error-prone pattern:

```java
@Transactional
public Mono<Customer> updateWithRetry(Long id, String name) {
    return doUpdate(id, name)
            .retryWhen(writeRetryPolicy);
}
```

Here the retry operator sits inside the publisher wrapped by the transaction interceptor. Upstream resubscriptions can remain inside the existing transaction context depending on transaction boundaries and driver behavior. For errors that abort or roll back transactions, do not rely on this pattern to open a fresh transaction per attempt.

When each attempt requires its own transaction, wrap the transaction operator inside `defer` with retry outside, or invoke a transactional bean through its proxy from the retried publisher.

## 15. Retrying Deadlocks and Serialization Conflicts

Deadlocks or serialization conflicts happen when concurrent transactions contend for the same data. Databases typically abort one transaction to break a deadlock or preserve isolation. Retrying the entire transaction often succeeds once execution timing shifts.

When retrying these errors:

- Retry the entire transaction unit, not just the last statement.
- Open a fresh transaction for each attempt.
- Keep transactions short to minimize lock duration.
- Access resources in a consistent order across transactions whenever possible.
- Cap retries and apply backoff/jitter.
- Do not retry if the operation triggers external side effects without idempotency/outbox protection.

Exact exception classes and SQL states for deadlocks/serialization vary by database. Rely on exception types or error codes verified against your active driver; do not assume all databases share the same codes.

## 16. Do Not Retry Every Error Across a Large Pipeline

Suppose a pipeline reads from the database, charges a payment provider, and writes an audit record:

```java
return customerRepository.findById(id)
        .flatMap(paymentService::charge)
        .flatMap(payment -> auditRepository.save(toAudit(payment)))
        .retryWhen(retryPolicy);
```

A trailing retry can re-run the read, the payment charge, and the audit write whenever any upstream step emits a matching error. If the payment provider already captured funds yet timed out on the response, retrying could charge the customer again.

Scope retries tightly and pass idempotency keys to external services:

```java
return customerRepository.findById(id)
        .flatMap(customer -> paymentService.charge(
                customer,
                requestId
        ).retryWhen(paymentRetryPolicy))
        .flatMap(payment -> auditRepository.save(toAudit(payment)));
```

Even when retry wraps only `paymentService.charge`, the charge call still requires a provider-supported idempotency key or equivalent safeguard. Database writes require separate transaction boundary design as discussed earlier.

## 17. Combining `timeout`, `retryWhen`, and Cancellation

A complete policy often combines:

- Per-query/attempt timeout.
- Bounded retries with backoff.
- Overall request timeout.

Example:

```java
Mono<Customer> result = Mono.defer(() ->
            customerRepository.findById(id)
        )
        .timeout(Duration.ofSeconds(2))
        .retryWhen(readRetryPolicy)
        .timeout(Duration.ofSeconds(6));
```

The inner timeout caps each source execution. The outer timeout caps total duration including retries and backoff. When the outer timeout fires, the pipeline cancels; there is no reason to keep retrying after the request deadline expires.

For transactional writes, cancellation must reach the transaction manager for rollback/cleanup. Never swallow cancellation or launch detached subscriptions that keep running after the caller stops waiting.

### Do not confuse timeout with proof an operation never ran

A timeout only proves the caller did not receive a result in time. It does not prove the database never executed the statement. An insert/update may have committed while the response arrived late or dropped. Treat write timeouts as uncertain outcomes until the application reconciles state via an idempotency key or lookup query.

## 18. Retries and Backpressure

`retryWhen` governs resubscribing upon errors; it is not a global concurrency throttle. If many concurrent requests retry simultaneously, total database load can still spike sharply.

Combine protective measures:

- Cap retries per request.
- Use backoff and jitter.
- Bound batch concurrency using `flatMap` with an explicit concurrency limit or `concatMap` when sequential execution is needed.
- Cap connection pool wait times.
- Set overall timeouts and caller deadlines.
- Monitor retry rates to spot incidents before a retry storm forms.
- Consider circuit breakers or load shedding at appropriate layers to stop hammering a persistently failing dependency.

Do not raise concurrency to compensate for an overloaded database. Excessive retries and concurrency drain the pool even faster.

## 19. Testing Bounded Retries and Backoff

Tests should verify subscription counts, which error types are retried, wait durations, and final failure behavior.

### Succeeding after transient failures

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> operation = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new R2dbcTransientException("temporary"));
    }
    return Mono.just("ok");
});

StepVerifier.create(operation.retryWhen(Retry.max(3)))
        .expectNext("ok")
        .verifyComplete();

assertThat(attempts).hasValue(3);
```

The publisher uses `defer` so each subscription increments the counter and simulates a fresh execution.

### Not retrying disallowed errors

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> operation = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.error(new IllegalArgumentException("invalid input"));
});

StepVerifier.create(operation.retryWhen(
                Retry.max(3).filter(this::isRetryable)
        ))
        .expectError(IllegalArgumentException.class)
        .verify();

assertThat(attempts).hasValue(1);
```

Errors rejected by the predicate propagate immediately with zero retries.

### Verifying retry limit

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> operation = Mono.defer(() -> {
    attempts.incrementAndGet();
    return Mono.error(new R2dbcTransientException("still unavailable"));
});

StepVerifier.create(operation.retryWhen(Retry.max(2)))
        .expectError()
        .verify();

assertThat(attempts).hasValue(3);
```

One initial execution plus two retries occur.

### Testing backoff with virtual time

Do not slow down tests by sleeping hundreds of milliseconds per retry. Reactor Test supports virtual time:

```java
AtomicInteger attempts = new AtomicInteger();

StepVerifier.withVirtualTime(() ->
        Mono.defer(() -> {
            attempts.incrementAndGet();
            return Mono.<String>error(
                    new R2dbcTransientException("temporary")
            );
        }).retryWhen(Retry.backoff(
                2,
                Duration.ofSeconds(1)
        ).jitter(0))
)
        .thenAwait(Duration.ofSeconds(5))
        .expectError()
        .verify();

assertThat(attempts).hasValue(3);
```

Virtual time makes scheduler-based delay tests fast and deterministic. When testing jitter, set jitter to 0 in unit tests or assert within expected bounds.

### Testing a fresh transaction per attempt

For writes, integration tests are needed to prove each retry gets a new transaction and the prior failed attempt rolled back. Use a test service with `TransactionalOperator`, count work invocations, and inspect final database state. Mocked repositories cannot prove connections/transactions reopen properly.

## 20. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Empty query result does not trigger retry | Empty completion is not `onError` | Use `switchIfEmpty` for missing data |
| Validation errors are retried repeatedly | Overly broad predicate or unfiltered `retry()` | Retry only confirmed transient exceptions |
| Database overload worsens | Immediate retries or synchronized client retries | Use backoff, jitter, caps, and retry monitoring |
| More executions than expected | Confusing `maxAttempts` with total attempts | Account for the initial subscription |
| Writes produce duplicates | Retrying after timeout even though first attempt committed | Idempotency keys, unique constraints, or upserts |
| Retries inside a transaction keep failing | Retry executes inside an aborted transaction | Place transaction boundary inside the retried publisher |
| Entire side-effect chain repeats | Retry attached too far downstream | Narrow retry scope and protect side effects |
| Requests exceed deadlines | Missing overall timeout or excessive backoff | Enforce overall timeout/deadline budgets |
| Final error masked by retry exhaustion | Default exhaustion exception hides cause | Configure `onRetryExhaustedThrow` or map explicitly |
| Individual retries missing from logs | Logger placed after retry or missing hook | Use `doBeforeRetry`; log final failure downstream |
| Wrapped exceptions fail to retry | Predicate checks only the outer exception | Walk cause chain or rely on exception translation |
| Retrying write timeout duplicates side effects | Timeout does not prove database skipped execution | Design idempotency and state reconciliation |

## 21. R2DBC Retry Design Workflow

When adding retries to a repository or SQL operation, follow these steps:

1. Identify real driver/Spring errors and classify them as transient or permanent.
2. Determine whether the operation is a read or write; verify side effects are safe to repeat.
3. Identify the exact upstream steps that will resubscribe if retry is placed at the chosen spot.
4. Choose max retry count, backoff, max backoff, and jitter.
5. Write a predicate permitting only verified exceptions.
6. Set per-attempt timeouts and an overall timeout matching the deadline.
7. For transactional writes, ensure each attempt opens a new transaction if errors can invalidate the current transaction.
8. Use unique constraints, idempotency keys, or upserts for writes that may be resent after ambiguous outcomes.
9. Log and record metrics for each retry and final failure without leaking sensitive data.
10. Test transient recovery, permanent failures, exhaustion, backoff, timeouts, cancellation, and transaction rollbacks against the real driver/database.

## 22. Key Takeaways

- Retrying means resubscribing to the upstream publisher after `onError`; it does not trigger on empty completion.
- `Retry.max(n)` and `Retry.backoff(n, ...)` treat `n` as maximum retries after the initial attempt.
- Exponential backoff eases pressure on recovering dependencies; `maxBackoff` caps wait times.
- Jitter spreads retry timing, reducing thundering herd spikes.
- Use `.filter(...)` to retry only verified transient errors; never mechanically retry SQL grammar, validation, constraint, or authorization failures.
- Inspect the cause chain and driver/Spring exception translation; concrete exception types depend on the database and version.
- `retryWhen` can re-run the entire upstream pipeline; scope it carefully and audit repeatable side effects.
- Retrying writes requires idempotency because timeouts or dropped connections do not prove the database failed to commit.
- For transactional work, keep the transaction boundary inside the retried publisher so every attempt can open a fresh transaction.
- Per-attempt timeouts and overall timeouts serve distinct roles; retries must stay within the business deadline.
- Monitor retry counts, error types, latency, exhaustion, and pool metrics to detect retry storms early.
- Test backoff using virtual time and test transactions/idempotency against the real database and driver.

A sound retry policy for R2DBC is more than tacking on `retryWhen`. It requires knowing which failures are recoverable, which operations are safe to repeat, whether each attempt has an appropriate transaction, and whether total execution fits the deadline. Bounded retries, backoff, jitter, and idempotency help systems recover smoothly instead of amplifying database outages.
