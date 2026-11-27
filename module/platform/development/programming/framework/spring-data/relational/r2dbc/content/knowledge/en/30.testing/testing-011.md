# Testing Timeouts, Retries, Cancellation, and Connection Release

In Spring Data Relational R2DBC, a publisher can time out, be resubscribed during a retry, or be cancelled before completing. These signals directly affect statements, transactions, and connections in the pool. Therefore, testing reactive repositories/services goes beyond asserting return values; tests must prove that timeouts fire on schedule, retries are bounded, cancellations reach the source, and connections return to the pool after completion, error, or cancellation.

A test using only mocks and asserting that a `Mono` emits the expected DTO does not prove the driver cancelled the statement or the pool released the connection. You must combine two layers of testing:

- **Unit/reactive tests:** use `StepVerifier`, `TestPublisher`, `PublisherProbe`, and virtual time to check signals, subscription counts, retries, and cancellation without depending on a real database.
- **Integration tests:** run with the target R2DBC driver and database to verify real timeouts, transaction rollbacks, result/cursor cleanup, and the pool's ability to lease connections again.

## 1. Lifecycle to Test

A reactive database operation typically passes through these stages:

```text
Caller subscribes
       |
       v
Acquire connection from pool
       |
       v
Execute statement
       |
       v
Consume result / map rows
       |
       +--------------------------+
       |            |             |
       v            v             v
   onComplete     onError       cancel
       |            |             |
       v            v             v
  cleanup/close  rollback or   cancel/rollback
       |          cleanup        if needed
       +------------+-------------+
                    |
                    v
             Return connection
                    |
                    v
           Pool can lease again
```

Commit/rollback details depend on the transaction boundary. With Spring's reactive transactions, a normally completing publisher can commit; errors crossing the boundary or cancellation before completion are handled by the transaction manager according to rollback semantics. Even without a transaction, results/statements and connections still require cleanup.

Tests should verify both caller-observable signals and subsequent resource state. Seeing `onError` in `StepVerifier` does not automatically prove the connection returned to the pool; a separate pool/database check is required.

## 2. Distinguishing Timeout Types

No single timeout protects the entire R2DBC lifecycle. Each layer can enforce its own deadline:

| Timeout type | Target | Example error/outcome |
|---|---|---|
| Pool acquire timeout | Limits wait time for an idle connection | Acquire timeout from the pool |
| Connection creation timeout | Limits time to open a new connection | Connection error or timeout |
| Statement/query timeout | Limits time database spends executing a statement | Error from database/driver |
| Reactor `timeout` | Limits time a publisher emits no signal per operator | `TimeoutException` or fallback |
| Transaction timeout | Limits transaction lifetime per transaction manager | Transaction timeout/rollback |
| HTTP response timeout | Limits request/response time at server, gateway, or client | Request timeout or closed connection |
| Test verification timeout | Limits time `StepVerifier` waits for publisher in tests | Test fails because signals did not arrive in time |

These timeouts do not replace one another. For instance, Reactor `timeout` can cancel the subscription, while the driver/database must handle statement cancellation and cleanup. Pool acquire timeout only bounds waiting for a connection, not query execution time after acquiring one.

### 2.1. Per-Attempt Timeout vs. Whole-Workflow Timeout

When combining timeouts with retries, decide whether the deadline applies to each attempt or the whole use case.

Per-attempt timeout followed by retry:

```java
Mono<Customer> oneAttempt = customerRepository.findById(id)
    .timeout(Duration.ofSeconds(2));

return oneAttempt.retryWhen(retryPolicy);
```

Each resubscription to `oneAttempt` gets a two-second deadline. Total workflow duration can exceed two seconds due to multiple attempts and backoff delays.

Overall timeout for the entire retry sequence:

```java
return customerRepository.findById(id)
    .retryWhen(retryPolicy)
    .timeout(Duration.ofSeconds(5));
```

The outer deadline encompasses the initial attempt, retries, and backoff waits. After five seconds, the overall publisher times out and cancels the active attempt.

In real systems, both can be useful: a short timeout per query and an overall deadline per request. Pick values based on SLAs rather than arbitrarily.

### 2.2. StepVerifier Timeout Differs from Publisher Timeout

Example:

```java
StepVerifier.create(service.findCustomer(id))
    .expectNextCount(1)
    .verifyComplete(Duration.ofSeconds(3));
```

`verifyComplete(Duration)` limits how long the test waits for signals. It does not configure a query timeout or alter the production publisher. To test the `timeout` operator, place `timeout(...)` inside the tested pipeline and assert `TimeoutException`.

## 3. Testing Timeouts with StepVerifier

With a source that never emits signals, you can verify the timeout operator:

```java
@Test
void emitsTimeoutWhenSourceDoesNotRespond() {
    Mono<String> publisher = Mono.<String>never()
        .timeout(Duration.ofMillis(100));

    StepVerifier.create(publisher)
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
```

This test verifies Reactor semantics without needing a database. `Mono.never()` emits neither `onNext`, `onComplete`, nor `onError`; when the timeout expires, the operator emits a timeout error and cancels upstream.

With a fallback:

```java
Mono<String> publisher = Mono.<String>never()
    .timeout(Duration.ofMillis(100), Mono.just("fallback"));

StepVerifier.create(publisher)
    .expectNext("fallback")
    .verifyComplete();
```

When a fallback is used, downstream observes normal completion. This may fit caches or optional data, but you should not turn a database write timeout into a fake success.

### 3.1. Using Virtual Time to Test Timers Quickly

You do not need to wait many real seconds to test retry backoff or timeouts. Reactor Test provides `StepVerifier.withVirtualTime`:

```java
@Test
void timeoutUsesVirtualTime() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofHours(1))
        )
        .thenAwait(Duration.ofHours(1))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));
}
```

The publisher must be constructed inside the supplier passed to `withVirtualTime` so the virtual scheduler is installed before operators create timers. If built beforehand and passed in, timers may already be bound to the real scheduler.

Virtual time works well for Reactor timers such as `timeout`, `delayElements`, `delaySubscription`, and retry backoffs using Reactor-managed schedulers. It does not speed up PostgreSQL execution, network I/O, or R2DBC driver work. With real databases, use bounded real-time timeouts in separate integration tests.

### 3.2. Verifying Upstream Cancellation on Timeout

You can use `TestPublisher` to verify that timeout cancels upstream:

```java
@Test
void timeoutCancelsUpstream() {
    TestPublisher<String> source = TestPublisher.create();

    StepVerifier.withVirtualTime(() ->
            source.flux().next()
                .timeout(Duration.ofSeconds(5))
        )
        .thenAwait(Duration.ofSeconds(5))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(2));

    source.assertCancelled();
}
```

`TestPublisher.assertCancelled()` confirms the subscriber sent cancellation to the test source. This proves behavior at the Reactive Streams layer; it does not yet prove the R2DBC driver closed cursors or the pool released connections cleanly.

## 4. Testing Real Database Timeouts

Unit tests with `Mono.never()` do not test the database or driver. Integration tests must use a database and driver compatible with the runtime environment, typically via Testcontainers or a dedicated test database.

An integration test should:

1. Create a query with controllable runtime or use a sufficiently slow test fixture query.
2. Execute through the real `DatabaseClient`/repository.
3. Apply the timeout at the layer under test.
4. Verify the caller receives the expected error.
5. Verify statements/results are cleaned up and connections return to the pool.
6. Run a subsequent query to prove the pool still leases connections.

PostgreSQL-specific example using `pg_sleep`:

```java
Mono<Integer> slowQuery() {
    return databaseClient.sql("SELECT 1 FROM pg_sleep(5)")
        .map((row, metadata) -> row.get(0, Integer.class))
        .one();
}

@Test
void cancelsSlowPostgresQueryOnReactorTimeout() {
    StepVerifier.create(slowQuery().timeout(Duration.ofMillis(200)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(3));
}
```

This is a PostgreSQL-specific example. `pg_sleep` and the SQL syntax are not portable. Tests must verify that your exact driver version handles cancellation as expected; do not conclude the database stopped immediately solely because the caller received `TimeoutException`.

### 4.1. Reactor Timeout vs. Statement Timeout

Reactor timeout limits how long signals are awaited at the publisher layer. Database statement timeout limits how long the database lets a statement execute. Both layers can complement each other:

- Statement timeout lets the database proactively abort queries exceeding the deadline.
- Reactor timeout protects callers and cancels subscriptions when application deadlines expire.
- Pool acquire timeout prevents requests from waiting indefinitely for a connection.

In PostgreSQL, `statement_timeout` can be configured at role/database/session level or via `SET LOCAL` inside a transaction depending on policy. Example:

```sql
SET LOCAL statement_timeout = '2s';
```

`SET LOCAL` applies only to the current transaction. Do not assume a `SET LOCAL` executed on one connection applies to a later query on another connection. If configuring at session level in a pool, ensure state resets when connections return so settings do not leak across requests.

## 5. Retry Means Resubscribing

In Reactor, retry does not "resume from the exact failing row." Retry resubscribes to the upstream publisher. For a cold/lazy database publisher, this typically means the query or write executes again.

Example:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();

    if (attempt < 3) {
        return Mono.error(new TransientDataAccessResourceException(
            "Temporary failure"
        ));
    }

    return Mono.just("ok");
});

Mono<String> result = source.retry(2);
```

`Mono.defer` builds a fresh source on each subscription. `retry(2)` allows at most two retries after the initial attempt, meaning up to three total executions.

Do not retry every exception. Validation errors, unique violations, foreign key errors, invalid SQL, or business errors will not disappear on retry. Retries belong on clearly classified transient failures such as certain connection errors, deadlocks, or serialization conflicts per system policy.

## 6. Bounded Retries with Backoff

Immediate continuous retries can worsen overload on a struggling database. Use backoff to pause between attempts:

```java
Retry retryPolicy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .filter(this::isRetryableDatabaseFailure)
    .onRetryExhaustedThrow((spec, signal) -> signal.failure());

Mono<Customer> loadCustomer(Long id) {
    return customerRepository.findById(id)
        .retryWhen(retryPolicy);
}
```

`Retry.backoff(3, ...)` allows up to three retries beyond the first attempt. Backoff grows up to the maximum. You can add jitter so multiple instances do not retry in lockstep; exact APIs depend on the Reactor version.

Classification predicates should rely on structured exception types, SQLSTATE, or vendor codes:

```java
boolean isRetryableDatabaseFailure(Throwable error) {
    return error instanceof TransientDataAccessResourceException
        || error instanceof R2dbcTransientResourceException;
}
```

This is an illustrative example. Actual exception classes depend on Spring exception translation and the driver. Never use `error.getMessage().contains("timeout")` as the primary classifier because messages vary across drivers, versions, and locales.

### 6.1. Retry Count Differs from Total Attempt Count

If you configure three retries, total attempts can reach four:

| Attempt | Meaning |
|---:|---|
| 1 | Initial execution |
| 2 | First retry |
| 3 | Second retry |
| 4 | Third retry |

State clearly in configuration and documentation whether limits specify retry count or total attempts. This avoids accidentally generating double or multiplied load.

### 6.2. Testing Attempt Counts

```java
@Test
void retriesOnlyUpToConfiguredLimit() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.error(new TransientDataAccessResourceException("temporary"));
    });

    StepVerifier.withVirtualTime(() ->
            source.retryWhen(Retry.backoff(2, Duration.ofSeconds(1)).jitter(0))
        )
        .thenAwait(Duration.ofSeconds(5))
        .expectError(TransientDataAccessResourceException.class)
        .verify(Duration.ofSeconds(2));

    assertEquals(3, attempts.get());
}
```

The test verifies one initial attempt plus two retries. Virtual time avoids waiting for real backoff. Build `source` with `Mono.defer` so the counter increments on each subscription; creating side effects before subscription causes wrong counts.

## 7. Retrying Writes Requires Idempotency

Retrying a SELECT carries less side-effect risk than retrying an INSERT/UPDATE, though it can still return newer data on subsequent attempts. Retrying writes is riskier because failure can happen after the database committed and before the application received confirmation.

Example:

```text
Client sends INSERT
       |
       v
Database commits successfully
       |
       v
Connection drops before response reaches application
       |
       v
Application sees connection error and retries
       |
       v
Second INSERT can create duplicate record
```

The application cannot always tell whether the previous operation committed simply from seeing a client exception. For write retries, design idempotency:

- Use idempotency keys with unique constraints.
- Use unique business keys where appropriate.
- Use conditional upserts per domain semantics.
- Store operation outcomes so retries can return the prior result.
- Avoid sending external non-database side effects before transaction commit.

Request table example:

```sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    CONSTRAINT uk_payment_request_key
        UNIQUE (account_id, idempotency_key)
);
```

When retrying with the same key, the service checks the hash and status to return the prior result or continue the workflow according to rules. Never allow the same key to be reused with a different payload undetected.

## 8. Where Should Retry Sit Relative to Transactions?

The placement of `retryWhen` relative to the transaction boundary determines how transactions are recreated.

### 8.1. Retry Inside the Transaction Boundary

```java
return transactionalOperator.transactional(
    repository.save(entity)
        .retryWhen(retryPolicy)
);
```

Retry applies to the publisher inside the transaction. Attempts may run within the same transaction context/connection depending on the transaction manager and how the driver handles errors. In databases like PostgreSQL, after a statement error, the transaction can enter an aborted state and reject subsequent statements until rollback. Therefore, retrying a statement inside the same transaction is rarely safe for errors that poisoned the transaction.

### 8.2. Retrying the Entire Transaction

```java
Mono<Order> createOrderWithRetry(Order order) {
    return Mono.defer(() ->
            transactionalOperator.transactional(
                orderRepository.save(order)
                    .flatMap(saved -> saveLines(saved))
                    .thenReturn(order)
            )
        )
        .retryWhen(retryPolicy);
}
```

Here retry wraps the outside of the transactional publisher. Each resubscription can start a fresh transaction and re-execute the entire use case. `Mono.defer` constructs a fresh transactional publisher per attempt. This fits when transient errors require rolling back the current transaction before trying again.

However, a fresh transaction does not automatically make external side effects idempotent. If the workflow invokes HTTP, sends emails, or publishes messages, those side effects can still repeat. Only retry whole use cases when operations are safe to repeat or backed by outbox/idempotency mechanisms.

### 8.3. Do Not Hold Connections During Backoff

When retry sits outside the transactional publisher, the failed attempt's transaction can roll back and clean up before `Retry` waits through backoff and resubscribes. This avoids holding transaction-bound connections idle while sleeping between attempts.

Verify in practice using pool metrics or integration tests, especially with custom transaction managers or drivers performing asynchronous cancellation/cleanup.

## 9. Do Not Retry Cancellation as a Transient Error

Cancellation means downstream no longer wants results. It is not a regular error signal that applications should automatically retry.

Example:

```java
return repository.findAll()
    .retryWhen(retryPolicy);
```

If the caller cancels the subscription, the retry operator must not keep launching new attempts for a cancelled subscriber. Tests should confirm cancellation propagates upstream and no new subscription follows.

Do not use `doOnError` to handle cancellation; cancellation does not emit `onError`. Use `doFinally` to observe the `CANCEL` signal:

```java
return repository.findAll()
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            metrics.counter("r2dbc.query.cancelled").increment();
        }
    });
```

This callback should be lightweight and non-blocking. Never call `subscribe()` for another cleanup operation inside `doFinally`; use `usingWhen` or an appropriate lifecycle API when cleanup itself is asynchronous.

## 10. Testing Retries and Fallbacks with PublisherProbe

`PublisherProbe` helps confirm whether a fallback or composed publisher was subscribed to, requested, or cancelled.

Example fallback after a cache miss:

```java
@Test
void subscribesToDatabaseFallbackWhenCacheIsEmpty() {
    PublisherProbe<Customer> databaseProbe =
        PublisherProbe.of(Mono.just(customer));

    Mono<Customer> result = Mono.<Customer>empty()
        .switchIfEmpty(databaseProbe.mono());

    StepVerifier.create(result)
        .expectNext(customer)
        .verifyComplete();

    databaseProbe.assertWasSubscribed();
    databaseProbe.assertWasRequested();
}
```

Probes are helpful for verifying whether a branch was activated. For retries, you can use `Mono.defer` and `AtomicInteger` to count attempts; for fallbacks, `PublisherProbe` verifies the branch was subscribed to.

## 11. Testing Cancellation with StepVerifier

A basic test verifying cancellation:

```java
@Test
void cancelsInfiniteSource() {
    StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
        .expectNext(0L)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
}
```

`thenCancel()` sends cancellation after receiving the expected element. `verify(...)` bounds how long the test waits for verification to complete.

### 11.1. Using TestPublisher to Confirm Upstream Cancellation

```java
@Test
void cancellationReachesUpstream() {
    TestPublisher<Integer> source = TestPublisher.create();

    StepVerifier.create(source.flux())
        .thenCancel()
        .verify(Duration.ofSeconds(2));

    source.assertCancelled();
}
```

This is a Reactive Streams unit test. It confirms the source publisher receives cancellation, but does not test real database connection cleanup.

### 11.2. Confirming No Retry Occurs After Cancellation

```java
@Test
void doesNotStartAnotherAttemptAfterCancellation() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.<String>never();
    }).retryWhen(Retry.max(3));

    StepVerifier.create(source)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

    assertEquals(1, attempts.get());
}
```

`never()` emits no error, so it does not trigger retry; cancellation terminates the subscription. This test confirms no further attempt starts after subscriber cancellation.

## 12. Testing Cleanup with usingWhen

When code manages reactive resources directly, `usingWhen` provides cleanup callbacks for complete, error, and cancel paths:

```java
Mono<Result> executeWithResource() {
    return Mono.usingWhen(
        resourceFactory.create(),
        resource -> resource.execute(),
        Resource::close,
        (resource, error) -> resource.close(),
        Resource::close
    );
}
```

This example illustrates three cleanup callbacks: complete, error, and cancel. Exact overloads depend on the resource type and Reactor version. For connections managed by Spring Data/R2DBC, normally do not acquire and close raw connections manually unless needed; let `DatabaseClient`, `R2dbcEntityTemplate`, or the transaction manager handle lifecycles.

### 12.1. Testing Cleanup for Complete/Error/Cancel

You can use a fake resource counting cleanup invocations:

```java
AtomicInteger closed = new AtomicInteger();

Mono<String> work = Mono.usingWhen(
    Mono.just(new TestResource()),
    resource -> Mono.just("ok"),
    resource -> {
        closed.incrementAndGet();
        return Mono.empty();
    },
    (resource, error) -> {
        closed.incrementAndGet();
        return Mono.empty();
    },
    resource -> {
        closed.incrementAndGet();
        return Mono.empty();
    }
);
```

Write three separate tests to verify the right cleanup callback runs for complete, error, and cancel. Never share one counter across multiple subscriptions inside the same test without resetting explicitly.

## 13. Verifying Connections Return to the Pool

This is the most critical part of integration testing. A caller receiving `onComplete`, `onError`, or `cancel` does not automatically prove the connection is ready for the next request.

A useful testing strategy is creating a connection pool with `maxSize = 1` in the test environment:

1. Start a streaming query and keep it incomplete.
2. Confirm a second query must wait because the sole connection is busy.
3. Cancel or complete the first query.
4. Wait for cleanup within a bounded timeout.
5. Execute the second query and verify it acquires a connection.

If the connection is not returned to the pool, the second query will wait until acquire timeout. Using a single-connection pool makes lifecycle leaks easy to observe.

### 13.1. Configuring a Small Pool in Tests

Conceptual example with R2DBC Pool:

```java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(1)
        .maxSize(1)
        .maxAcquireTime(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofMinutes(1))
        .build();

ConnectionPool pool = new ConnectionPool(configuration);
```

This is an illustrative configuration; builder APIs and packages must match your project's `r2dbc-pool` version. Tests should close the pool after finishing so resources do not linger across tests.

### 13.2. Testing Connections After Cancellation

Example with PostgreSQL and a sufficiently large stream:

```java
Flux<Long> slowRows = databaseClient.sql("""
        SELECT generate_series(1, 1000000) AS id
        """)
    .map((row, metadata) -> row.get("id", Long.class))
    .all()
    .delayElements(Duration.ofMillis(10));

StepVerifier.create(slowRows)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));

StepVerifier.create(databaseClient.sql("SELECT 1")
        .map((row, metadata) -> row.get(0, Integer.class))
        .one())
    .expectNext(1)
    .verifyComplete(Duration.ofSeconds(3));
```

`generate_series` is PostgreSQL-specific. `delayElements` slows downstream consumption in the test so there is an opportunity to cancel while results are being consumed. The subsequent `SELECT 1` query confirms the pool can lease a connection for the next operation. In real tests, configure a `maxSize = 1` pool, finite acquire timeout, and explicit test data cleanup.

Do not assert that the connection is released the exact instant `thenCancel()` returns if driver cleanup is asynchronous. What matters is that within the designed window, the pool can lease a connection again and active/acquired metrics return to expected values.

### 13.3. Testing Connections After Error

Execute an intentionally failing query, verify the caller receives the exception, and then run `SELECT 1` on the same pool. This test catches cases where a failing statement/result prevents connection return or the pool marks a connection broken without provisioning a replacement per configuration.

### 13.4. Testing Connections After Completion

Read the entire result stream, verify completion, and then execute a second query. This is the baseline lifecycle path and deserves its own dedicated test, not just cancel/error tests.

## 14. Testing Cancellation Inside a Transaction

When a reactive transaction is open, cancellation before publisher completion must be handled by the transaction manager. You can test this by writing data and then keeping the publisher incomplete:

```java
Mono<Void> transactionalWork = transactionalOperator.transactional(
    customerRepository.save(customer)
        .then(Mono.never())
);

StepVerifier.create(transactionalWork)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

After cancellation and cleanup complete, read the customer back in a fresh transaction/query and verify the record was not committed. This is an integration test requiring a real database; mock publishers cannot prove transaction rollback.

### 14.1. Do Not Let an Outer Test Transaction Mask Results

If the test framework automatically opens a transaction for the test method and rolls back afterward, results may not reflect the service's own commit/rollback behavior. When testing transaction cancellation, ensure the verification query runs after the service transaction has been cleaned up and is not shadowed by an outer transaction.

### 14.2. Timeout Inside a Transaction

If a timeout sits inside the transaction boundary:

```java
Mono<Customer> work = transactionalOperator.transactional(
    customerRepository.save(customer)
        .timeout(Duration.ofMillis(100))
);
```

The timeout emits an error inside the operator's publisher; the transaction manager can roll back. If a fallback sits inside the boundary and converts the error into completion, the transaction could commit. Tests must verify the placement of `onErrorResume`/fallbacks to ensure rollback happens as intended.

## 15. Testing Retries and Connection Release Between Attempts

Retrying an entire transaction should terminate the failed attempt before starting backoff and the next attempt. You can use a `maxSize = 1` pool, a simulated transient failure on the first attempt, and then a probe query or metrics to confirm no connection is held during backoff.

In unit tests, use `Mono.defer` and virtual time to verify:

- Attempt count is accurate.
- Backoff intervals are applied.
- Non-retryable errors do not trigger retries.
- Cancellation during backoff prevents subsequent attempts.

In integration tests, use database fault injection or a test wrapper around `ConnectionFactory` to simulate failures at the desired point. Never intentionally break a production database to test retries.

### 15.1. Verifying Business Errors Are Not Retried

```java
@Test
void doesNotRetryUniqueViolation() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.error(new DuplicateKeyException("duplicate"));
    });

    StepVerifier.create(source.retryWhen(
            Retry.max(3).filter(this::isRetryableDatabaseFailure)))
        .expectError(DuplicateKeyException.class)
        .verify();

    assertEquals(1, attempts.get());
}
```

The test assumes `isRetryableDatabaseFailure` does not classify duplicate keys as transient failures. This prevents futile retries and avoids amplifying load.

### 15.2. Verifying Cancellation During Backoff

After an initial failure, the retry operator may be waiting on a timer. If the subscriber cancels during that wait, no next attempt may start:

```java
@Test
void cancellationDuringBackoffStopsFurtherAttempts() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> source = Mono.defer(() -> {
        attempts.incrementAndGet();
        return Mono.error(new TransientDataAccessResourceException("temporary"));
    }).retryWhen(Retry.backoff(5, Duration.ofSeconds(10)).jitter(0));

    StepVerifier.withVirtualTime(() -> source)
        .thenAwait(Duration.ofSeconds(1))
        .thenCancel()
        .verify(Duration.ofSeconds(2));

    assertEquals(1, attempts.get());
}
```

This test uses virtual time and cancels before the first backoff expires. If backoff timings change, adjust `thenAwait` so cancellation always occurs inside the wait window.

## 16. Testing WebFlux When an HTTP Client Disconnects

Publisher unit tests do not prove the HTTP server actually propagates cancellation when a client closes its socket. You need integration tests through a WebFlux server and HTTP client.

With `WebTestClient`, you can consume a streaming response and cancel the consumer:

```java
FluxExchangeResult<CustomerView> result = webTestClient.get()
    .uri("/customers/stream")
    .accept(MediaType.APPLICATION_NDJSON)
    .exchange()
    .expectStatus().isOk()
    .returnResult(CustomerView.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
```

This test cancels the client-side response body subscription. Depending on test client/server setup, this may not be 100% identical to closing a real TCP socket. For end-to-end verification, use a client capable of closing a real connection or a test harness running the server on a random port and actively aborting the HTTP request.

After the client cancels, verify:

- The server receives cancellation or disconnect per connector support.
- The service publisher observes `doFinally(CANCEL)` if cancellation reaches the pipeline.
- R2DBC results/statements are cleaned up.
- Connections return to the pool within a reasonable deadline.
- Subsequent requests can still acquire connections.
- No new retries or side effects continue running after cancellation.

## 17. Testing Connection Leaks with a Small Pool

A `maxSize = 1` pool is a simple way to surface resource leaks in tests:

```text
Test starts
   |
   v
Query A acquires the only connection
   |
   v
Query A is held / incomplete
   |
   v
Query B requests connection -> must wait
   |
   v
Cancel / complete Query A
   |
   v
Query B must acquire connection
   |
   v
Test ends and closes pool
```

If query B fails to acquire a connection after A finishes, there may be a cleanup bug, connection leak, or connection marked invalid without the pool creating a replacement. Inspect pool metrics/logs to distinguish these cases.

### 17.1. Do Not Conclude a Leak from a Single Acquire Timeout

An acquire timeout can happen because:

- Query A is legitimately still running.
- The database is unresponsive and the driver has not cleaned up yet.
- The pool failed to provision a replacement connection.
- The pool exhausted `maxSize` under multiple concurrent requests.
- The test did not allow enough time for cleanup.

Verify that query A has completed/errored/cancelled, observe active/acquired metrics, and verify a subsequent query after a finite cleanup window.

### 17.2. Counting Acquisitions and Releases

For deeper diagnostics, you can wrap `ConnectionFactory`/`Connection` in tests to count:

- How many times `create()` was called.
- How many connections were leased from the pool.
- How many times `close()`/release was called.
- How many connections remain currently held.
- Observed `cancel`/cleanup calls if supported by the wrapper.

Do not use wrapper tests as proof that the real driver always behaves like a mock. Combine wrapper unit tests with integration tests against the real driver.

## 18. When to Use TestPublisher vs. PublisherProbe

| Tool | Used to verify |
|---|---|
| `StepVerifier` | `onNext`, `onComplete`, `onError`, request, and cancel signals |
| `withVirtualTime` | Virtual-scheduler-based timeouts/backoffs/delays |
| `TestPublisher` | Driving source signals and asserting cancellation |
| `PublisherProbe` | Whether a publisher was subscribed, requested, or cancelled |
| `AtomicInteger` + `Mono.defer` | Counting source executions/subscriptions |
| R2DBC pool metrics | Active, idle, pending acquire, and release behavior |
| Testcontainers/real database | Real driver, SQL timeout, transactions, cursors, and cleanup |
| WebTestClient/real HTTP client | Cancellation from the HTTP layer down to the publisher |

You do not need every tool in every test. Pick the tool matching the question you need answered.

## 19. Common Mistakes When Testing Timeouts, Retries, and Cleanup

| Mistake | Consequence | Fix |
|---|---|---|
| Testing only `TimeoutException` in Reactor | Unknown whether driver/database actually cancelled | Add integration tests with real R2DBC and a follow-up query |
| Confusing `verify(Duration)` with query timeout | Test timeout does not verify production operator | Place `timeout()` in the publisher and test explicitly |
| Using virtual time for real database queries | Virtual scheduler does not drive network/database I/O | Use virtual time for timers; integration tests use bounded real time |
| Creating publisher before `withVirtualTime` | Timers may capture real scheduler | Build publisher inside the supplier |
| Using unbounded retries | Can loop endlessly and amplify overload | Bound retries, backoff, jitter, and overall deadline |
| Retrying every exception | Repeats unrecoverable business/constraint errors | Filter by structured transient error types/codes |
| Retrying non-idempotent INSERTs | Can create duplicates when commit confirmation is lost | Use idempotency keys/unique constraints/conditional upserts |
| Retrying statements inside an aborted transaction | Database rejects every subsequent statement | Roll back transaction and retry whole use case in a fresh transaction |
| Keeping backoff inside a long transaction | Can hold connections idle while waiting | Place retry outside transactional publisher for fresh transaction per attempt |
| Retrying after cancellation | Work continues even though caller left | Test cancellation and ensure no follow-up attempt starts |
| Testing only complete, skipping error/cancel | Misses cleanup bugs on other termination paths | Write separate tests for complete, error, and cancel |
| Treating `doFinally(CANCEL)` as proof of connection release | Callback observes pipeline signals only | Check pool metrics and run a follow-up query |
| Using mock connections as proof of real driver behavior | Misses driver protocol/cursor/cleanup behavior | Run integration tests with target database/driver |
| Using a large pool in leak tests | Small leaks stay hidden | Use a `maxSize = 1` pool in lifecycle tests |
| Failing to close pools in tests | Resources linger across tests | Close pools/clients/containers in teardown |
| Wrapping tests in outer test transactions | Can mask service commit/rollback results | Verify with a fresh query after the service transaction ends |
| Using only in-process WebTestClient | May not simulate real TCP socket disconnects | Add end-to-end tests with a real HTTP client when needed |

## 20. Workflow for Building the Test Suite

For an R2DBC service with timeouts, retries, and cancellation, proceed in order:

1. **Test basic signals:** verify success, empty, and errors with `StepVerifier`.
2. **Test timeout logic:** use `Mono.never()` or `TestPublisher` and virtual time.
3. **Test cancellation logic:** use `thenCancel()` and `TestPublisher.assertCancelled()`.
4. **Test retries:** use `Mono.defer`/`AtomicInteger`, verifying attempt count and backoff.
5. **Test retry filters:** confirm transient errors retry while duplicate/validation errors do not.
6. **Test cancellation during backoff:** cancel subscription and confirm no next attempt starts.
7. **Test idempotency:** resend the same command/key and verify no duplicate side effects occur.
8. **Integration test timeouts:** run queries on a real database and verify errors/cleanup.
9. **Integration test pool release:** use a `maxSize = 1` pool, complete/cancel a query, and run a new query.
10. **Integration test transactions:** verify rollback on timeout/cancel and commit on completion.
11. **HTTP cancellation test:** close response consumer/request and observe server cleanup.
12. **Observe metrics:** check active/idle/pending acquires and acquire duration return to expected levels.

You do not need to run every scenario end-to-end when unit tests already verify Reactor logic clearly. At minimum, however, behaviors depending on the driver, pool, and transactions must have matching integration tests.

## 21. Metrics to Observe in Tests and Production

Metrics reveal whether timeouts, retries, or cancellations destabilize the pool:

- Active/acquired connections.
- Idle connections.
- Pending acquires and acquire duration.
- Acquire timeout count.
- Connection creation/validation failures.
- Query/statement duration.
- Retry counts by operation and error category.
- Timeout counts by layer: pool, statement, Reactor, HTTP.
- Cancellation counts by endpoint/query.
- Time from cancellation until connection returns to the pool.
- Transaction duration and rollback counts if supported by instrumentation.

Exact metric names depend on the R2DBC Pool, Spring Boot, and Micrometer versions. Never assume identical metric names across every application. In tests, inspect pool metrics before and after scenarios; in production, alert on rising pending acquires, timeouts, and connection hold durations.

Retries require close monitoring because they multiply total query volume. A minor transient hiccup can become a retry storm if many instances share identical backoff timing. Log attempt counts, operations, and error categories; avoid logging sensitive data or raw SQL bind values.

## 22. Example Service with Controlled Timeout and Retry

The example below illustrates a read query that retries on transient resource failures:

```java
@Service
public class CustomerQueryService {

    private final CustomerRepository repository;

    private final Retry retryPolicy = Retry.backoff(
            2,
            Duration.ofMillis(100)
        )
        .maxBackoff(Duration.ofSeconds(1))
        .filter(this::isRetryable);

    public CustomerQueryService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> findById(Long id) {
        return Mono.defer(() -> repository.findById(id))
            .timeout(Duration.ofSeconds(2))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(5));
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof TransientDataAccessResourceException
            || error instanceof R2dbcTransientResourceException;
    }
}
```

In this example:

- `Mono.defer` constructs a fresh repository publisher per subscription.
- A two-second timeout bounds a single attempt.
- Retries occur at most twice after the initial attempt for the selected error types.
- A five-second timeout bounds the overall workflow.
- Caller cancellation propagates through the pipeline and stops active attempts or backoff waits.

This example covers a read operation. For write operations, add idempotency and consider retrying the whole transaction at the right boundary. Adjust exception types to match your real driver and exception translation.

## 23. Principles to Remember

- Verify both reactive signals and connection/transaction state after complete, error, and cancel.
- Distinguish pool acquire timeouts, statement timeouts, Reactor timeouts, transaction timeouts, and HTTP timeouts.
- `StepVerifier.verify(Duration)` limits test waiting time; it does not set a timeout on production publishers.
- Use `withVirtualTime` for Reactor timers and create publishers inside the supplier.
- Virtual time does not control real database/network I/O.
- `retry` resubscribes to the source; with R2DBC, queries/writes can re-execute.
- Bound retries, use backoff/jitter, and filter on structured transient errors.
- Retry count differs from total attempts: three retries can mean four executions.
- Retrying writes requires idempotency because failures can occur after database commit.
- Place retries outside transactional publishers when failed attempts must roll back and start fresh transactions.
- Never blindly retry business/constraint errors or cancellations.
- Use `thenCancel()` and `TestPublisher.assertCancelled()` to verify cancellation at the Reactive Streams layer.
- `doFinally(CANCEL)` observes cancellation only; it does not prove connections were released.
- Use a `maxSize = 1` pool and a follow-up query to confirm connections return to the pool.
- Test timeouts, cancellation, and transactions against a real database and R2DBC driver.
- Test HTTP disconnects when streaming endpoints must abort queries upon client departure.
- Close pools/containers after tests and avoid outer test transactions masking service commit/rollback.
- Monitor active/idle/pending connections, acquire latency, retry counts, timeouts, and cleanup duration.

A trustworthy R2DBC test suite proves that timeouts prevent unbounded execution, retries do not repeat unintended side effects, cancellation halts active work, and connections return to the pool so subsequent requests continue running smoothly. `StepVerifier` with virtual time tests signal logic rapidly and deterministically; Testcontainers or integration databases verify real drivers, transactions, and connection pools. Combining these two layers with bounded retries, idempotency, and lifecycle metrics equips applications to handle transient failures without turning them into pool exhaustion or cascading retry storms.
