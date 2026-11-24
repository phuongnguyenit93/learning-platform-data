# Retry limit

In Spring Batch, the retry limit specifies how many times the framework is allowed to retry an operation when an exception belonging to a retryable category occurs. Retrying is useful for transient errors such as deadlocks, timeouts, or flaky dependent services. After a bounded number of attempts, if the operation still fails, Spring Batch proceeds to the next handling step based on the skip configuration or marks the step as failed.

A retry limit prevents a single failing item from halting the job immediately, while preventing the system from retrying indefinitely and wasting resources. To use it properly, you must understand that this limit applies to retrying an item/operation, which exceptions are permitted to retry, what happens when the limit is exhausted, and how retry interacts with transactions, skip, and restart.

## 1. What is retry limit?

In a chunk-oriented step, the reader fetches items, the processor transforms items, and the writer persists groups of items. If an operation throws an exception classified as retryable, Spring Batch can re-attempt it according to the step's retry policy.

`retryLimit(n)` sets the limit on the number of retries for errors declared via `retry(...)`. The initial execution still takes place before retries begin. For example, `retryLimit(3)` allows up to three retry attempts after the initial attempt under how retry configuration is interpreted in Spring Batch.

```text
Initial execution
       |
       +-- success --> continue
       |
       +-- retryable exception
                 |
                 v
             Retry #1
                 |
                 +-- success --> continue
                 |
                 +-- failure --> Retry #2
                                  |
                                  +-- success --> continue
                                  |
                                  +-- failure --> Retry #3
                                                   |
                                                   +-- success --> continue
                                                   |
                                                   +-- failure --> retries exhausted
                                                                    |
                                                                    v
                                                        apply skip or fail
```

Important point: the retry limit is not the number of times the entire job can rerun, nor the number of times the step can be started. It is the retry limit for an operation/item governed by the retry policy in a fault-tolerant step.

## 2. Configuring retryLimit in Spring Batch 5

To enable retry, a chunk step must be configured as fault-tolerant. Then declare the retry limit and the exception types allowed to retry.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientPartnerException.class)
        .retryLimit(3)
        .build();
}
```

In this example, only `TransientPartnerException` is designated as retryable. If another exception occurs, it is not automatically retried merely because the step has `.faultTolerant()`.

`retryLimit(3)` bounds the number of retry attempts for an error/item under the retry policy. When retrying still does not succeed after the limit, the exception continues to the skip policy if that exception is also skippable; otherwise, the step fails.

## 3. Choosing the right exceptions to retry

Retrying is only useful when the next attempt has a chance to succeed without changing input data or code. Therefore, retry only errors that are transient in nature.

| Exception category | Example | Typically appropriate handling |
|---|---|---|
| Deadlock or lock contention | Database reports deadlock during update | Retry with limit and backoff |
| Temporary timeout | Reference service fails to respond in time | Retry with limit, timeout, and backoff |
| Short-lived connection error | Connection reset or transient network glitch | Retry if the operation is safe to re-invoke |
| Malformed data | Missing required field, negative quantity | Validate, skip, or fail per business rules; retrying usually does not help |
| Configuration error | Wrong URL, missing credentials, wrong schema | Fail fast to fix configuration |
| Programming error | NullPointerException, faulty mapping | Fail to investigate; do not retry blindly |

For example, if the processor always throws `InvalidOrderException` because quantity is 0, invoking the processor three more times still receives the same invalid data. Retrying only prolongs processing without improving the outcome.

Conversely, if the writer hits a deadlock while updating a record, retrying after the transaction rolls back can succeed once the competing transaction releases the lock.

## 4. Specifying retryable exceptions

Multiple exception types can be declared:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retry(TransientPartnerException.class)
.retryLimit(3)
```

In this configuration, exceptions belonging to the declared types are treated as retryable. Choose specific exception types or a superclass with clear semantics, avoiding overly broad exception groups.

Example to avoid:

```java
// Do not retry every error indiscriminately
.faultTolerant()
.retry(Exception.class)
.retryLimit(10)
```

Retrying every exception can delay detection of configuration errors, data errors, and programming bugs. It can also repeat unsafe operations or add heavier load to a failing service.

When clearer classification is needed, create dedicated exceptions in the integration layer, such as `TransientPartnerException` for temporary partner errors and `InvalidPartnerResponseException` for contract-violating responses. That allows the retry policy to express business semantics accurately.

## 5. What happens when the retry limit is exceeded?

When a retryable exception keeps occurring and the retry policy has exhausted its allowed attempts, Spring Batch stops retrying infinitely. The framework transitions to the chunk's recovery path.

There are two main outcomes:

- If the exception is also configured as skippable and the skip limit still permits, the item may be skipped and the step continues.
- If the exception is not skippable, or the skip limit has been exceeded, the step fails.

Example of retry followed by skip:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPartnerException.class)
    .retryLimit(3)
    .skip(TransientPartnerException.class)
    .skipLimit(20)
    .build();
```

In this example, if the partner error persists after retries, the exception can be handled as a skip provided the skip policy permits it and the skip limit has not been reached. This is appropriate only when business rules accept discarding that item and an auditing mechanism records it for later handling.

If data must not be dropped, do not configure skip for that exception. Once retries are exhausted, the step will fail rather than reporting completion with missing data.

## 6. Distinguishing retryLimit and skipLimit

`retryLimit` and `skipLimit` control two different things:

| Configuration | Question | Meaning |
|---|---|---|
| `retryLimit(n)` | How many times should this error be retried? | Limits retry attempts under the retry policy |
| `skipLimit(n)` | How many faulty items are allowed to be discarded? | Limits total skips for the step execution |

Retrying attempts to re-execute the operation so the item succeeds. Skipping accepts not processing that item and moves on to other items.

Example of an item encountering a timeout:

1. The first service call times out.
2. Spring Batch retries up to the configured limit.
3. If a subsequent attempt succeeds, the item proceeds to the writer and is not skipped.
4. If retries are exhausted and the exception is skippable, the item may be discarded.
5. If the exception is not skippable, the step fails.

Do not set a high skip limit to compensate for an imprecise retry policy. Decide separately which errors can be retried and which errors can be discarded.

## 7. Retry differs from job restart

Retry happens during a step execution to re-attempt a failing operation/item. Restart creates a new `JobExecution` for the same `JobInstance` after a previous execution failed or stopped and is restartable.

| Mechanism | Scope | Purpose |
|---|---|---|
| Retry | An operation/item in a fault-tolerant step | Recover from transient errors within the current execution |
| Restart | A failed or stopped JobInstance | Resume the job from saved metadata/checkpoints |
| `startLimit` | Number of times a step is permitted to start | Limits how many times the step can be launched |
| `JobParametersIncrementer` | Generates parameters for the next instance | Creates a new JobInstance |

Do not increment `run.id` merely to bypass the retry limit. Doing so creates a new JobInstance, does not resume from the same checkpoint, and may reprocess already-committed data.

## 8. Retry and transaction rollback

In a chunk-oriented step, each chunk is processed inside a transaction. When an error occurs in the reader, processor, or writer, Spring Batch may roll back the chunk transaction before recovery/retry depending on exception type and configuration.

```text
Chunk transaction begins
        |
        v
Processor or Writer
        |
        +-- success --> commit chunk
        |
        +-- retryable error
                 |
                 v
            rollback/recovery
                 |
                 v
             retry per policy
                 |
                 +-- success --> continue to commit
                 |
                 +-- retries exhausted --> skip or fail
```

The exact number of times the reader/processor/writer are re-invoked depends on the failure phase, retry policy, skip policy, and step recovery mechanism. Do not assume each item is read or processed exactly once.

Changes inside the chunk's database transaction can roll back if the transaction manager properly manages the datasource. Side effects outside the transaction such as sending emails, calling HTTP APIs, or publishing messages are not automatically rolled back.

## 9. Retry when the writer writes the whole chunk

The writer receives a batch of items at once. If the writer throws an exception, the framework may need to recover and isolate the offending item, especially when combining retry with skip. Consequently, a writer call may be re-executed for the same chunk or subsets of the chunk depending on fault-tolerance mechanics.

This affects writer design:

- Write operations must be safe when invoked repeatedly.
- Do not swallow exceptions to pretend a chunk succeeded.
- Use unique keys, upserts, or idempotency keys where duplicate writes could occur.
- Avoid calling non-idempotent external APIs inside the writer if the operation may be retried.
- If the writer performs multiple side effects, define how to recover when only part of the operations succeeded.

Do not rely on the retry limit to guarantee exactly-once behavior. Retry only controls attempt counts; write idempotency remains the responsibility of data and integration design.

## 10. Configuring backoff between retries

Continuous retrying without a pause can overload a dependent system further, especially when an external service is experiencing issues. Backoff inserts a wait interval between attempts.

Example configuring exponential backoff:

```java
ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5000L);

return new StepBuilder("callPartnerStep", jobRepository)
    .<Request, Response>chunk(20, transactionManager)
    .reader(requestReader)
    .processor(partnerProcessor)
    .writer(responseWriter)
    .faultTolerant()
    .retry(TransientPartnerException.class)
    .retryLimit(3)
    .backOffPolicy(backOffPolicy)
    .build();
```

With these values, the wait interval starts at 500 ms, multiplies by 2, and is capped at 5 seconds. The actual duration of the overall job also depends on retry counts, duration per request, and how many items fail.

Backoff must align with client timeouts, transaction timeouts, and the job deadline. Avoid holding transactions or connections open across long wait intervals if the operation can be structured to avoid it.

## 11. Retries may need limits by error type

In real applications, some errors should only be retried once or twice, whereas others can be retried more times. A custom retry policy or exception classifier can be used to express complex policies.

Example rules:

| Exception | Suggested retry limit | Backoff |
|---|---:|---|
| Database deadlock | 3 | Short, increasing |
| Partner API timeout | 2–3 | Exponential, capped |
| API rate limit | Per `Retry-After` if supported by client | Honor server-requested interval |
| Validation exception | 0 | Do not retry |
| Authentication/configuration error | 0 | Fail fast and alert |

These numbers are only design examples. Choose values based on SLAs, service characteristics, and load capacity; do not apply them mechanically to every job.

## 12. Stateful and stateless retry

Retrying may need to retain information about previous attempts. In batch processing, an item can be identified by a key so the framework links retry state across calls during recovery.

- **Stateless retry:** retrying occurs within the same invocation context and does not need to keep long-lived per-item state beyond the current retry context.
- **Stateful retry:** retry state is associated with an item via a key and can persist across chunk rollbacks/recoveries within the same execution.

For readers/writers involving transaction rollbacks, stateful retry can help prevent an item from looping infinitely across chunk recovery attempts. However, the item needs a stable identifier and the retry context must be managed appropriately. Do not confuse the retry context with durable checkpoints in `ExecutionContext` or a JobInstance restart.

If configuring a custom retry policy, understand where retry state is kept, whether the item key is stable, and when the retry context is cleared. Custom policies must be tested against real rollbacks and skips.

## 13. Retry in the processor vs. retry in the writer

Retries can originate at different phases:

| Phase | Example | Considerations |
|---|---|---|
| Read | Transient error querying source or reading a file over the network | The reader may need state support to restore the exact position |
| Process | Timeout calling an enrichment service | The processor should avoid non-idempotent side effects |
| Write | Deadlock or timeout writing to a database/API | The writer may be re-invoked with the chunk or relevant items |

Choose exception classes based on actual failures in each phase. Do not retry deterministic data parsing errors or mapping bugs in code. For file read errors, verify whether the reader can re-read the same record after rollback.

## 14. Retry limit and non-retryable errors

When an exception is not on the retry list, the framework does not retry it under that retry policy. It is passed on to skip/fail handling as configured.

`noRetry` can be used to exclude an exception from a broader retry policy:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.noRetry(InvalidOrderException.class)
.retryLimit(3)
```

The example above indicates that data errors are not retried even if a superclass or general policy might otherwise match them. Check inheritance relationships among exceptions so a broad configuration does not inadvertently include unsuitable errors.

## 15. Monitoring retry counts

Retries can mask transient failures if you only observe final status. A job may complete while having retried heavily, signaling that a database or dependent service is unstable.

Monitor:

- Retry counts by job, step, and exception category.
- Items that ultimately succeed after retry.
- Items that exhaust retries and are skipped.
- Items that exhaust retries and fail the step.
- Backoff wait times and total processing time.
- Retry rate over time to spot upward trends.

Do not use order IDs or personal data as high-cardinality metric labels. Logs should include JobExecution ID, StepExecution ID, and safe identifiers to correlate attempts.

## 16. Common mistakes when configuring retry limit

| Mistake | Consequence | Remedy |
|---|---|---|
| Retrying all `Exception`s | Data, configuration, and programming errors are retried needlessly | Retry only identified transient exceptions |
| Setting retry limit too high | Prolongs the job and increases load on a failing system | Choose limits based on SLA and backoff |
| Not configuring backoff | Rapid retries overload the service further | Use bounded backoff for suitable errors |
| Assuming exhausting retries auto-skips items | Step still fails if the exception is not skippable | Configure skip separately if business rules allow |
| Confusing retry limit with restart limit | Creates a new JobInstance or restarts improperly | Distinguish item retry from JobExecution restart |
| Non-idempotent writer | Retries can write duplicates or repeat side effects | Use unique keys, upsert, idempotency, or outbox |
| Swallowing exceptions in processor/writer | Framework cannot detect errors to retry | Let exceptions propagate per contract |
| Looking only at final job status | Misses rising transient error trends | Collect retry metrics and logs with correlation IDs |

## 17. Testing retry limit

You can test retries with a processor or writer that simulates failing a number of times before succeeding.

Example processor that fails twice and then succeeds:

```java
public class FlakyProcessor implements ItemProcessor<Request, Response> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Response process(Request request) {
        int attempt = attempts.incrementAndGet();
        if (attempt <= 2) {
            throw new TransientPartnerException("Temporary failure");
        }
        return new Response(request.id(), "OK");
    }
}
```

With `retryLimit(3)` and the exception configured as retryable, a test can verify that the item ultimately succeeds after the attempts. Also test persistent failures exceeding the limit and verify the step transitions to skip or fail according to policy.

Cases to verify:

1. Retryable exception succeeds on the first attempt: no retries occur.
2. Retryable exception fails a few times then succeeds: item is processed successfully.
3. Retryable exception fails past the limit: skips or fails per policy.
4. Non-retryable exception: no additional retry attempts occur.
5. Retry combined with backoff: attempt counts and wait intervals match configuration.
6. Retry in the writer: no duplicate data created when writer is called again.
7. Restart after step failure: JobRepository and checkpoint resume the right JobInstance.

Integration tests should check processor/writer invocation counts, step status, skip count, and committed data. Checking only that JobExecution completed is not enough to prove retries work correctly.

## 18. Process for choosing a retry limit for production

When designing a retry policy, follow this sequence:

1. Identify exceptions representing transient errors likely to succeed on retry.
2. Check whether the operation is safe under repeated calls or needs an idempotency key.
3. Choose the retry limit based on SLA, timeouts, and service capacity.
4. Configure backoff to avoid retry storms.
5. Decide separately what happens after retries are exhausted: audited skip or job failure.
6. Check transaction rollbacks and checkpoints in each phase: reader, processor, writer.
7. Collect metrics on retries, exhaustion, and wait duration.
8. Test sustained errors, brief errors, and concurrent load before deployment.

The retry policy must coordinate with client timeouts and overall deadlines. If each call has a 30-second timeout, three retries plus backoff can make one item take substantial time. Calculate the worst-case total duration and ensure it does not breach the job's SLA.

## Conclusion

`retryLimit` limits how many times Spring Batch retries an operation/item when an exception declared via `retry(...)` occurs in a fault-tolerant chunk step. Once the limit is exhausted, the exception is evaluated against the skip policy if permitted; otherwise, the step fails. Retry differs from skip and restart: retry re-attempts the operation, skip discards the item, and restart resumes a JobInstance from saved metadata.

Retry only transient errors, set sensible limits, use backoff when needed, and ensure readers/processors/writers are safe when re-invoked. Track retry metrics to detect degrading dependencies, and design clear skip or failure behavior when retries are no longer effective.
