# Retryable exception

In Spring Batch, a retryable exception is a type of error where re-executing the operation has a reasonable chance of succeeding. For example, a database may temporarily return a deadlock, an HTTP service may time out during brief network instability, or a message broker may temporarily refuse connections. For such errors, a Step can retry instead of failing immediately.

Not every exception should be retried. Malformed data, business validation errors, invalid SQL syntax, missing files, or invalid credentials typically do not disappear when re-executed. Retrying these errors only increases execution time and system load. To configure retries safely, you must understand the nature of the error, bound the number of attempts, choose appropriate backoff, and ensure the operation can be re-executed without causing duplicate side effects.

## 1. What is a retryable exception?

An exception is retryable when its underlying cause is likely transient and a subsequent attempt has a chance to succeed without changing the input data or code.

Common examples:

- Database deadlock: the transaction may succeed when retried after locks are released.
- Lock acquisition timeout: another transaction is holding a resource briefly.
- Network timeout: the connection or target service may recover.
- Temporary service unavailable: an external system is overloaded or undergoing brief maintenance.
- Broker unavailable: a message broker is temporarily unable to accept or deliver messages.

Errors that normally should not be retried:

- Missing input file or wrong file path.
- Data not matching the schema or failing to parse.
- Deterministic business validation violations.
- SQL syntax errors or wrong table/column names.
- Expired credentials or unauthorized user.
- Programming errors such as NullPointerException caused by bugs.
- Constraint violations reflecting invalid data or business-level duplicate keys.

Classification is not based solely on the exception's class name. The same exception family can have different causes depending on the driver, framework, and target system. Examine the root cause, resource state, and the likelihood that the operation succeeds on retry.

## 2. Distinguishing retryable and non-retryable exceptions

A practical way to classify is determining whether an error can resolve on its own after some time or requires fixing data, configuration, or code.

| Error category | Examples | Retry? | Reason |
|---|---|---|---|
| Transient contention errors | Deadlock, lock timeout | Usually yes | The other transaction may finish and release the lock |
| Transient network errors | Connection reset, transient timeout | Possibly | Connectivity may recover |
| Temporarily overloaded service | HTTP 503, broker unavailable | Possibly | The service may become ready after backoff |
| Data errors | Parse error, validation error | Usually no | Retrying the same data will not fix its content |
| Configuration errors | Wrong URL, missing file, wrong schema | No | Configuration or resource needs fixing |
| Authentication/authorization errors | HTTP 401/403, wrong credentials | Usually no | Retrying with the same credentials will not help |
| Programming errors | NullPointerException, IllegalStateException from bugs | Not by default | Code or application state needs fixing |

These are guidelines, not absolute rules for every system. For instance, HTTP 429 may be retried after the server-specified interval, while HTTP 400 is usually an invalid request error. Some APIs return 500 for transient errors, while others use 500 for unrecoverable failures. Rely on the service's contract and specific error codes.

## 3. How retry differs from skip and fail

The three behaviors serve different purposes:

- **Retry:** re-execute the same operation because the error is likely transient.
- **Skip:** bypass a faulty item when business rules allow not processing that item.
- **Fail:** stop the Step because the error cannot safely continue or retry/skip limits have been exceeded.

Example:

~~~text
Read Order 42
    |
    v
Write to database
    |
    +--> Deadlock
    |       |
    |       v
    |    Retry after backoff
    |       |
    |       +--> success -> continue
    |       |
    |       +--> retries exhausted -> fail or skip if policy permits
    |
    +--> InvalidOrderException
            |
            +--> skip if configured
            |
            +--> fail if not skippable
~~~

Retrying is not synonymous with ignoring errors. When attempts are exhausted and the exception still occurs, the Step must apply the next policy: skip if the exception is skippable and skip budget remains, or fail otherwise.

Do not use skip to handle system-level errors such as database unavailable. If the entire database connection is broken, skipping items one by one causes missing data without resolving the underlying cause.

## 4. Configuring retry in a chunk-oriented Step

In Spring Batch, you can enable fault tolerance and specify retryable exception types on StepBuilder.

Example:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

In this example:

- faultTolerant() enables error-handling configuration such as retry and skip for the Step.
- retry(TransientDataAccessException.class) specifies the transient database error group to retry.
- retryLimit(3) sets the retry limit according to the API semantics of the Spring Batch version in use.
- Reader, processor, and writer still execute following the normal chunk lifecycle.

Verify the semantics of retry limit in your specific version. Some retry APIs express the maximum number of attempts including the first call, whereas documentation or application-level configuration may express the number of retries after the first call. Do not deduce the total call count solely from the configured number; write an integration test to confirm the actual number of attempts.

Declare only specific exceptions that the application identifies as transient. Avoid retrying all Exception.class or Throwable.class, as doing so can repeatedly execute data errors, programming bugs, and configuration mistakes.

## 5. Choosing appropriate exceptions

Spring provides a database error-translation hierarchy, such as the TransientDataAccessException family for potentially transient errors. Specific exceptions may include deadlock or temporary resource unavailability, depending on the driver and how Spring translates SQLException.

Example retrying deadlock:

~~~java
.faultTolerant()
.retry(DeadlockLoserDataAccessException.class)
.retryLimit(3)
~~~

Or retrying the transient data access error family:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
~~~

Keep in mind:

- Specific exceptions depend on the database and driver.
- A SQL error may be wrapped inside a Spring exception.
- The same general exception may contain different root causes.
- If classifying by cause, check how the retry policy traverses the exception chain in your version.
- Do not retry a broad exception merely because it occasionally represents a transient failure.

For HTTP clients, classify by status code and network error type. For example, timeouts or 503 may be retried; 400 from a bad request normally should not be retried; 429 should honor Retry-After if provided by the service. If a client throws only a generic exception, you may need an adapter that translates errors into distinct domain exceptions before they reach the Step.

## 6. Excluding non-retryable exceptions

If a broad error group is marked retryable, you must exclude errors that cannot recover by retrying. Some StepBuilder versions support noRetry(...); if the current API lacks it or rules are complex, use a custom RetryPolicy.

Illustrative example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(Exception.class)
        .noRetry(InvalidOrderException.class)
        .noRetry(DataIntegrityViolationException.class)
        .retryLimit(3)
        .build();
~~~

The configuration above should only be used when there is a clear reason to retry the broad Exception group and exclude the remaining errors precisely. In most cases, declaring specific retryable exceptions is clearer and safer.

If exceptions have inheritance relationships, check the classification rules and precedence of a specific exception versus its superclass in the Spring Batch/Spring Retry version in use. Do not assume a noRetry(...) setting always overrides other policies if a custom RetryPolicy is also supplied.

## 7. Retry limit and execution count

Retries must be bounded so a Job does not loop indefinitely. If a target service cannot recover, continuous retrying consumes threads, connections, and time without offering a meaningful chance of success.

When choosing a limit, distinguish:

- **Initial attempt:** the first execution.
- **Retry attempt:** a re-execution after failure.
- **Total attempts:** total invocations, including the initial attempt and retries.

For example, if a system allows 3 retries after the first attempt, total attempts may be 4. Yet an API configuring maxAttempts might include the first attempt within the number 3. Read the documentation of the specific API and verify with tests.

Consider:

- Expected recovery time of the resource.
- Timeout of each invocation.
- Maximum total duration of the Step or Job.
- Additional load that retries place on the target system.
- Safety level of repeating the operation.
- Retry policies of external services.

A small limit usually fits deadlocks or brief network glitches. For services with long recovery windows, consider backoff, overall timeouts, or offloading work to a queue for later reprocessing rather than keeping a worker thread blocked for too long.

## 8. Backoff to avoid retry storms

If retries happen immediately, multiple workers may retry at the same instant and prolong overload. Backoff inserts a waiting interval between attempts.

Common strategies:

- **Fixed backoff:** wait a constant interval between retries.
- **Exponential backoff:** progressively increase the wait time after each failure.
- **Exponential backoff with jitter:** add randomness so multiple workers do not synchronize retries simultaneously.
- **Server-directed backoff:** use a duration specified by the target service, such as HTTP Retry-After.

Example configuring exponential backoff:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    ExponentialBackOffPolicy backOff =
            new ExponentialBackOffPolicy();
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(5000L);

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .backOffPolicy(backOff)
            .build();
}
~~~

This example uses Spring Retry APIs integrated in the corresponding Spring Batch versions. Packages and configuration methods may vary by version. The illustrative backoff increases the wait interval from 500 ms, doubling each time up to a cap of 5 seconds.

Do not set overly long backoff intervals if transactions or connections remain held during the wait. Review the Step's transaction boundaries, exception types, and framework retry mechanics. For network errors calling external APIs, set per-request timeouts so an attempt cannot hang indefinitely.

## 9. Retry and transaction rollback

In a chunk-oriented Step, the writer typically writes data within the chunk's transaction. When a write operation throws an exception causing the transaction to roll back, Spring Batch can retry according to configuration.

General flow:

~~~text
Begin chunk transaction
       |
       v
Read / Process
       |
       v
Write chunk
       |
       +--> transient exception
                 |
                 v
              rollback
                 |
                 v
             backoff
                 |
                 v
              retry
                 |
           +-----+------+
           |            |
        success       exhausted
           |            |
           v            v
        commit       fail / skip
~~~

Database operations participating in the current transaction are rolled back when the transaction rolls back. However, some non-database operations such as sending emails, making HTTP calls, or publishing messages may already have occurred and cannot be undone by a database transaction.

During retry, the reader or processor may also be invoked again depending on the failure phase and how the framework recovers the chunk. Do not assume only a single line of code in the writer is re-executed. Design the entire processing path to tolerate repeated execution.

## 10. Idempotency: a crucial condition for safe retry

An idempotent operation can be executed multiple times while yielding the same final outcome as executing it once. This property is critical when it is impossible to know for certain whether a prior request succeeded.

For example, a client sends a request to create an invoice. The server finishes processing, but the response is lost due to a network timeout. The client retries and resends the request. If the server has no mechanism to detect duplicate requests, two invoices may be created.

Ways to improve idempotency:

- Use unique business keys and unique constraints in the database.
- Use upserts when appropriate for business rules.
- Send a stable idempotency key to APIs.
- Record processed message IDs so consumers deduplicate.
- Use a transactional outbox to emit events after commit.
- Maintain a status table keyed by business key to track completed operations.

Example idempotency key:

~~~java
String idempotencyKey =
        "order-" + order.getId() + "-invoice-v1";

paymentClient.createInvoice(
        order,
        idempotencyKey);
~~~

The key must remain stable across retries and restarts of the same logical operation. Do not generate a new UUID for each retry, because the server will treat each request as a separate operation.

Idempotency does not mean silently ignoring every duplicate. The receiving system should verify that repeated requests carry the same content and business intent; if the same key arrives with a different payload, return an explicit error.

## 11. Retrying with HTTP clients and external services

When a processor or writer calls an API, classify errors according to the HTTP contract.

A common classification approach:

| Outcome | Action typically considered |
|---|---|
| Connect timeout / read timeout | Bounded retry if the request is safe |
| Connection reset | Retry if the request is idempotent |
| HTTP 429 | Honor Retry-After and backoff |
| HTTP 502/503/504 | May retry with bounds |
| HTTP 400 | Usually do not retry; fix request/data |
| HTTP 401/403 | Do not retry with same credentials; fix auth/permissions |
| HTTP 404 | Depends on contract; usually do not retry if resource does not exist |
| HTTP 409 | Depends on conflict semantics and idempotency |

This table cannot be treated as a universal rule for every API. For example, a service might return 404 while a resource has not yet finished syncing, or use 409 for a retryable operation. Rely on the API documentation.

For rate-limited APIs, backoff should honor the wait time requested by the server. If the wait duration exceeds the Job's operational limits, consider stopping and placing the item into a separate retry queue rather than keeping the Step running for a long time.

## 12. Stateful and stateless retry

Retries may keep attempt state within the scope of a single execution or maintain state across item rollbacks and re-presentations.

- **Stateless retry:** retry state is tied to a single current execution; suitable for errors that can be retried immediately in the same context.
- **Stateful retry:** requires recognizing the same item across rollbacks and reprocessing, typically using a stable key to retain the retry context.

In Spring Batch, chunk and transaction retry mechanics may require stateful behavior so an item is recognized after a transaction rolls back and the item is fed back into the flow. Exact details depend on the error type, reader, transaction manager, and framework version.

If using stateful retry or a custom RetryPolicy, define a key for the item. The key must be stable and distinguish between different items; using mutable objects or an unstable toString() can cause retry contexts to be mismatched.

Do not build a global retry cache yourself if the framework already manages the retry context. Improperly evicted caches can retain objects too long, leak memory, or mix state across different JobExecutions.

## 13. Combining retry and skip

An exception can be configured to retry first, and only after retries are exhausted be evaluated against the skip policy if it is also skippable.

Example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
~~~

In this example, deadlocks are retried; validation errors are skipped. If a deadlock persists past the retry limit and is not configured as skippable, the Step fails. Do not add skip for all database errors just so a Job can keep running.

Verify the interaction among the retry policy, skip policy, and rollback classifier of the Spring Batch version in use. An exception may be classified differently in the read, process, and write phases. Write integration tests for actual failures rather than testing each policy only in isolation.

## 14. Do not catch exceptions and self-retry inside components

A common design mistake is writing a custom retry loop inside a processor or writer:

~~~java
// Avoid implementing your own retry loop if the Step already manages retries.
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        remoteClient.send(item);
        break;
    } catch (RuntimeException exception) {
        if (attempt == 3) {
            throw exception;
        }
    }
}
~~~

This prevents Spring Batch from knowing the attempt count, applying Step-configured backoff/skip policies, and observing retries cleanly. It can also keep a transaction open while waiting.

Let the fault-tolerant Step manage retries if the operation sits within the reader/processor/writer lifecycle. If retries are needed inside an independent client or service, use a clearly configured retry mechanism and avoid uncoordinated nested retry layers. For example, an HTTP client retrying 3 times inside a Step that also retries 3 times can produce far more requests than expected.

Do not swallow exceptions and return a dummy result so the Step continues. Let appropriate exceptions propagate so the retry policy or skip policy can decide.

## 15. Retry and time limits

Retry count alone is not enough to bound total duration. If each request times out after 30 seconds and there are multiple attempts, a single item can tie up a worker for a long time.

Determine:

- Connect timeout.
- Response read timeout.
- Total request timeout.
- Backoff between attempts.
- Maximum attempt count.
- Job deadline or operational schedule.
- How long transactions and connections remain held.

For instance, 3 attempts with a 20-second timeout and increasing backoff can stretch past one minute for a single item. Across a chunk of many items, total duration can rise substantially.

Set timeouts at the client/resource layer and retry limits at the Step layer. Do not use retries as a substitute for timeouts. If a service cannot recover within an acceptable window, stop the Step and allow a scheduler or external retry mechanism to reprocess later.

## 16. Observing retries in operations

Retries can slow a Job down without increasing skip counts or final write errors, because the item eventually succeeds. Therefore, merely checking for a COMPLETED status is insufficient to tell whether the system is retrying excessively.

Monitor:

- Retry attempts by Job and Step.
- Exception types being retried.
- Rate of succeeded retries vs. exhausted retries.
- Backoff wait durations.
- Item/chunk processing times.
- Number of transaction rollbacks.
- Final errors leading to fail or skip.

You can use listeners or Spring Retry/Micrometer observability features suitable for your deployed version. Keep metric tags low-cardinality; do not put Order ID, request ID, or JobExecution ID into tags. Put detailed identifiers into logs/audits when investigation is needed.

Retry logs should include JobExecution ID, Step name, exception class, and attempt number. Do not log sensitive payloads or full request/response bodies.

## 17. Testing retryable exceptions

Test both exception classification and actual execution behavior.

Key scenarios:

| Scenario | What to verify |
|---|---|
| Transient failure occurring once | Retries and then succeeds |
| Persistent transient failure | Stops after the attempt limit |
| Non-retryable exception | Does not repeat the operation |
| Exception wrapped in cause | Policy classifies properly as configured |
| Backoff | Wait intervals follow policy |
| Writer failure in transaction | Rolls back and retries properly |
| Processor failure | Item is reprocessed per lifecycle |
| API response lost after server processing | Idempotency prevents duplicate effects |
| Retries exhausted and exception skippable | Skip policy is applied properly if configured |
| Retries exhausted and exception non-skippable | Step FAILED |
| Restart after failure | No duplicate or missing data |
| Multiple workers retrying concurrently | Backoff prevents retry storms |

A unit test can use a mock client to throw exceptions on the first two attempts and succeed on the third. Integration tests should run the Step with a real transaction manager and writer or a test database environment to confirm rollback/retry behavior.

When asserting invocation counts, distinguish the initial attempt from retry attempts. Do not assert only the total call count without checking the semantics of retryLimit or maxAttempts in the API you use.

## 18. Common mistakes when configuring retry

**Retrying all exceptions.** Data errors, programming bugs, and configuration errors do not resolve themselves. Select only transient error groups.

**Unbounded attempt counts.** A Job may run far too long or generate repeated load on a failing service.

**Immediate retries.** Multiple workers can trigger a retry storm. Use backoff and jitter where appropriate.

**Missing timeouts.** A single attempt can hang longer than the entire allowed operational window.

**Confusing retry with skip.** Retry retains the item to try again; skip discards the item under business policy.

**Non-idempotent operations.** A request may have succeeded while the response was lost; retrying can create duplicate effects.

**Nesting multiple retry layers.** Client, service, and Step retrying together can multiply request counts severalfold.

**Swallowing exceptions.** The framework never receives the error to apply retry policies or update metadata accurately.

**Not measuring retries.** The Job still ends COMPLETED while processing time and system load spike abnormally.

## 19. Process for selecting retryable exceptions

When configuring retries for a Step, follow this order:

1. Identify actual exceptions and root causes from the reader, processor, or writer.
2. Assess whether the cause is likely transient or requires fixing data, configuration, or code.
3. Choose specific exceptions or an appropriate classifier; exclude non-retryable errors.
4. Set a retry limit and clarify whether total attempts include the initial attempt.
5. Choose backoff, jitter, and timeouts suited to the target service.
6. Verify transaction rollbacks and whether components can safely be invoked repeatedly.
7. Ensure operations are idempotent or protected against duplicates.
8. Decide whether exhausting retries fails the Step or permits skipping.
9. Emit metrics/logs for attempts, exhausted retries, and backoff duration.
10. Test transient errors, permanent errors, restarts, partitioning, and effects outside transactions.

A retryable exception is a decision based on whether the root cause can recover, not merely on a class name. By choosing the right exceptions, bounding attempts, applying backoff, setting timeouts, and protecting operations with idempotency, Spring Batch can recover gracefully from transient errors while still stopping clearly when data or systems hit issues that retrying cannot fix.

