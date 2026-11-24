# RetryPolicy

`RetryPolicy` is the policy that decides whether an operation may be retried after an exception occurs and when retrying must stop. In Spring Batch, a retry policy is used in a fault-tolerant chunk step to control how transient errors in the reader, processor, or writer are handled.

Rather than merely declaring a simple retry limit, `RetryPolicy` allows describing richer rules: which exceptions are retried, which exceptions must stop immediately, the maximum number of attempts, how nested exceptions in the cause chain are classified, and how retry state is tracked. A retry policy should reflect the likelihood that the error will resolve on its own and the safety of re-executing the operation.

## 1. What does RetryPolicy decide?

When an operation in a step throws an exception, Spring Batch needs to decide whether to retry that operation or move to recovery. `RetryPolicy` answers the question of whether retry is still allowed based on the retry context and the recorded exception.

```text
Operation in chunk
        |
        v
     Exception
        |
        v
     RetryPolicy
        |
        +-- still retryable --> retry the operation
        |
        +-- no more retries --> recovery
                                  |
                                  +-- skip if exception is skippable
                                  |   and skip limit still permits
                                  |
                                  +-- otherwise --> step FAILED
```

`RetryPolicy` does not write data itself, does not modify items, and does not decide whether an item may be skipped. It only controls retrying. Once retrying is no longer allowed, the skip policy or the step's default failure mechanism decides what happens next.

## 2. RetryPolicy in the Spring Batch ecosystem

In Spring Batch 5, a fault-tolerant step integrates Spring Retry's retry mechanism. The commonly used interface is `org.springframework.retry.RetryPolicy`; the implementations reside in the `org.springframework.retry.policy` package.

`RetryPolicy` is used by Spring Retry inside a retry operation. It manages the retry context, registers exceptions, and determines whether further retries are permitted. Spring Batch provides APIs on `FaultTolerantStepBuilder` to attach a policy to a chunk step.

Example imports:

```java
import org.springframework.retry.RetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.batch.core.step.builder.StepBuilder;
```

To use Spring Retry policies, the application needs a Spring Retry dependency compatible with the version of Spring Batch/Spring Framework in use. With Spring Boot, let the Boot version's dependency management manage the corresponding version rather than pinning an incompatible version manually.

## 3. Configuring RetryPolicy for a chunk step

You can create a `RetryPolicy` bean and pass it to `.retryPolicy(...)` on the step builder.

```java
@Bean
RetryPolicy orderRetryPolicy() {
    Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
    retryable.put(TransientDataAccessException.class, true);
    retryable.put(TransientPartnerException.class, true);
    retryable.put(InvalidOrderException.class, false);

    return new SimpleRetryPolicy(4, retryable, true);
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer,
        RetryPolicy orderRetryPolicy) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retryPolicy(orderRetryPolicy)
        .build();
}
```

In this example, transient data access errors and partner errors are retried. `InvalidOrderException` is classified as non-retryable. The argument `4` of `SimpleRetryPolicy` is the maximum number of executions including the initial call: at most one initial attempt and three retries. The `true` parameter instructs the policy to examine the cause chain as well when classifying exceptions.

When using `.retryPolicy(...)`, configure the full exception rules and limits directly inside the policy. Do not simultaneously expect `.retry(...)` or `.retryLimit(...)` calls to add rules onto a custom policy; choose one clear configuration style and verify the API of the Spring Batch version in use.

## 4. SimpleRetryPolicy

`SimpleRetryPolicy` is a common implementation when you need a maximum number of attempts and a map of whether each exception is retryable.

Key components:

- `maxAttempts`: maximum number of executions, including the initial attempt.
- `retryableExceptions`: map from exception class to boolean indicating whether that exception can be retried.
- `traverseCauses`: enables classifying exceptions based on nested causes inside.

Example:

```java
Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(DeadlockLoserDataAccessException.class, true);
retryable.put(SocketTimeoutException.class, true);
retryable.put(InvalidCustomerException.class, false);

RetryPolicy policy = new SimpleRetryPolicy(5, retryable, true);
```

With this configuration, an exception classified as retryable can be attempted up to five times in total. When the fifth attempt still fails, the policy does not permit another attempt.

`SimpleRetryPolicy` fits well when rules can be expressed with an attempt count and exception classification. If you need time-based limits, dynamic classification, or a combination of multiple conditions, consider another policy or a custom policy.

## 5. Exception classification

Not every exception should be retried. A good policy distinguishes transient errors from permanent errors:

| Exception | Example | Typically appropriate classification |
|---|---|---|
| `TransientDataAccessException` | Deadlock or transient database error | Bounded retry |
| `SocketTimeoutException` | Partner connection timeout | Retry if the operation is safe to invoke again |
| `TransientPartnerException` | External service temporarily unavailable | Retry with backoff |
| `InvalidOrderException` | Order missing required fields | Do not retry; may skip or fail |
| `AuthenticationException` | Expired or invalid credentials | Do not retry blindly; fix configuration/credentials |
| `NullPointerException` | Programming bug | Do not retry; fix the code |

Example of a policy that should not retry data errors:

```java
Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(TransientPartnerException.class, true);
retryable.put(InvalidOrderException.class, false);

RetryPolicy policy = new SimpleRetryPolicy(4, retryable, true);
```

When classifying by superclass, pay attention to inheritance relationships. If a superclass is marked retryable, subclasses may be classified according to the policy's exception lookup rules. Check ordering/priority and test with real exceptions, especially when the framework wraps the original exception in another exception.

## 6. Cause traversal and exception wrapping

In Spring applications, the original exception is often wrapped across multiple layers. For example, a socket error might be wrapped into `ResourceAccessException`, and then into an adapter business exception.

```text
TransientPartnerException
        caused by
ResourceAccessException
        caused by
SocketTimeoutException
```

If only the outermost exception is classified, the policy may fail to recognize that the underlying error is a timeout. `SimpleRetryPolicy` provides the `traverseCauses` option to inspect the cause chain during classification.

```java
RetryPolicy policy = new SimpleRetryPolicy(
    4,
    retryableExceptions,
    true // inspect the cause chain as well
);
```

Enable cause traversal only when cause exceptions are classified deliberately. Do not retry every exception just because a generic error type appears deep in the cause chain; inspect how adapters wrap errors to avoid mistakenly retrying business or configuration errors.

## 7. ExceptionClassifierRetryPolicy

When each group of exceptions needs a different policy, you can use `ExceptionClassifierRetryPolicy`. This policy selects a retry policy based on the current exception type.

Conceptual example: deadlock errors have their own attempt count and backoff, partner timeout errors have a different limit, and validation errors are not retried.

```java
Map<Class<? extends Throwable>, RetryPolicy> policies = new HashMap<>();
policies.put(
    DeadlockLoserDataAccessException.class,
    new SimpleRetryPolicy(5)
);
policies.put(
    TransientPartnerException.class,
    new SimpleRetryPolicy(3)
);
policies.put(
    InvalidOrderException.class,
    new NeverRetryPolicy()
);

ExceptionClassifierRetryPolicy policy = new ExceptionClassifierRetryPolicy();
policy.setPolicyMap(policies);
```

This snippet illustrates mapping exceptions to specific policies; in a real application, configure a default policy for exception types absent from the map and verify that the classifier handles subclasses/causes as intended.

`ExceptionClassifierRetryPolicy` is useful when a job calls multiple dependent systems with different failure characteristics. However, keep the policy map concise and use clear exception names; if the rules become overly complex, separate error classification in the adapter/service before exceptions reach the batch layer.

## 8. NeverRetryPolicy and AlwaysRetryPolicy

Spring Retry provides policies for two boundary behaviors:

- `NeverRetryPolicy`: does not allow retrying after the initial execution.
- `AlwaysRetryPolicy`: always allows retrying; must be combined with another limiting mechanism if you do not want infinite retries.

`NeverRetryPolicy` fits permanent data errors or operations unsafe to invoke repeatedly. `AlwaysRetryPolicy` must be used with extreme caution because without another stopping condition, retrying can continue indefinitely.

```java
RetryPolicy noRetry = new NeverRetryPolicy();
```

In production batch jobs, a clearly bounded policy is usually preferable to `AlwaysRetryPolicy`. A service that is down should not be called endlessly by multiple workers.

## 9. TimeoutRetryPolicy

`TimeoutRetryPolicy` limits retries by elapsed time rather than only attempt count. It can be useful when the recovery window of a system matters more than a fixed number of attempts.

Example:

```java
TimeoutRetryPolicy policy = new TimeoutRetryPolicy();
policy.setTimeout(10_000L); // milliseconds
```

A timeout policy does not replace timeouts on the HTTP client, JDBC driver, or transaction manager. If a single call hangs for a long time, the retry policy cannot abort that call on its own just because total elapsed time exceeded the threshold. You must configure timeouts at the I/O layer so that each attempt finishes in a finite amount of time.

When combining a timeout policy with backoff, calculate the total wait time and execution time per attempt to ensure compatibility with the job's deadline.

## 10. RetryPolicy and BackOffPolicy are two separate responsibilities

`RetryPolicy` decides whether retrying is allowed. `BackOffPolicy` decides how long to wait before the next attempt. The two policies work together, but neither replaces the other.

```text
Exception
   |
   v
RetryPolicy: attempts remaining?
   |
   +-- No --> recovery
   |
   +-- Yes
       |
       v
BackOffPolicy: how long to wait?
       |
       v
Re-execute the operation
```

Example configuring exponential backoff:

```java
ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(5_000L);

return new StepBuilder("callPartner", jobRepository)
    .<Request, Response>chunk(20, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retryPolicy(retryPolicy)
    .backOffPolicy(backOff)
    .build();
```

The wait interval increases from 500 ms by a factor of 2 and does not exceed 5 seconds. Values should be chosen based on SLA, client timeouts, and load limits of the dependent system. For APIs returning `Retry-After`, a custom backoff policy may be needed to honor the server-requested wait time.

## 11. RetryContext and retry state

Spring Retry uses `RetryContext` to store information about a retry sequence, such as the retry count and the most recent exception. `RetryPolicy` creates or uses the context, records exceptions, and decides whether the operation may still be retried.

`RetryContext` differs from Spring Batch's `ExecutionContext`:

| Context | Purpose | Lifecycle |
|---|---|---|
| `RetryContext` | Tracks state of a single retry sequence | Bound to the retry operation and retry mechanism |
| Step `ExecutionContext` | Stores step checkpoints for restart | Persisted in the JobRepository per step execution |
| Job `ExecutionContext` | Shares required state across steps in a job execution | Persisted in the JobRepository per job execution |

Do not use `RetryContext` as durable checkpoint storage for a job. When the JVM process stops, an ordinary retry context cannot replace the metadata and state needed for restart.

## 12. Stateless and stateful retry

With stateless retry, retrying is performed within the same processing context of the operation. With stateful retry, retry state is associated with an item that has a stable key so the same item can be recognized across rollbacks/recoveries.

In batch processing, stateful retry can be useful when a transaction rollback causes a chunk to be fed back through recovery and the framework needs to remember the item's attempt count. For that to work, the item needs a stable identifier; otherwise, each re-read could be treated as a new item.

Considerations:

- Choose the key from a stable business identifier; do not use `hashCode()` of a mutable object.
- Ensure two distinct items never share the same retry key.
- Determine where the retry context cache is held and when it is evicted.
- Do not confuse retry state with restart checkpoints in `ExecutionContext`.
- Test retrying across rollbacks, skips, and multiple chunks.

Stateful retry does not guarantee that external operations happen only once. The writer/processor still need idempotency for non-transactional side effects.

## 13. RetryPolicy, skip policy, and rollback

The three mechanisms have distinct roles:

| Mechanism | Question |
|---|---|
| `RetryPolicy` | Can the operation be retried after this exception? |
| Skip policy | If retrying does not continue, is the item allowed to be discarded? |
| Rollback classification | Does this exception cause the current transaction to roll back? |

Example of an item encountering a timeout from a partner service:

1. `RetryPolicy` permits a retry.
2. Spring Retry applies backoff if configured.
3. If an attempt succeeds, the item continues through the pipeline.
4. Once retries are exhausted, the skip policy is evaluated.
5. If the exception is not skippable, the step fails.

A chunk may roll back during retry/recovery depending on the failure phase and transaction semantics. The fact that an exception is retryable does not mean the transaction will not roll back. Similarly, a skippable exception can still cause the chunk to roll back before the offending item is isolated.

## 14. When is RetryPolicy used in a chunk?

Retrying can occur when errors arise in the reader, processor, or writer, provided the step is configured for fault tolerance and the exception is recognized by the policy.

| Phase | Example | Design considerations |
|---|---|---|
| Read | Timeout when reading data from a remote source | The reader must have a suitable way to restore its read position |
| Process | Timeout when calling a data enrichment service | Avoid non-idempotent side effects in the processor |
| Write | Deadlock or connection error during writes | The writer may be invoked again; use unique keys/upsert/idempotency |

Do not retry deterministic data parsing errors or mapping bugs in code. If an exception indicates the source contract has changed, retrying multiple times only slows down the job and masks the problem.

## 15. Custom policies

When built-in implementations cannot express the required rules, you can implement your own `RetryPolicy`. The policy must manage the retry context consistently and have a clear stopping condition.

The basic responsibilities of a policy include:

- Creating a context when a retry operation begins.
- Inspecting the context and deciding whether retrying is still permitted.
- Recording the exception that just occurred.
- Cleaning up resources or state when the retry operation finishes.

Do not implement a custom policy just to check a single exception class or a simple attempt limit; `SimpleRetryPolicy` is usually sufficient. A custom policy is more appropriate when the decision depends on business state, a deadline, or a specialized classification rule.

When a policy relies on an external service or time-varying data, ensure retry decisions remain predictable and do not create excessive overhead. Avoid making a network API call on every `canRetry` invocation without appropriate caching/timeouts.

## 16. Retry key and RetryContextCache

In stateful retry, the retry mechanism must correlate attempts for the same item. The retry key must remain stable throughout recovery.

Example keying by order ID:

```java
public record OrderRow(String orderId, BigDecimal total) {
}

// Illustrative key logic: orderId must be unique within the job's scope.
String retryKey(OrderRow row) {
    return row.orderId();
}
```

For the retry context cache, bound both its capacity and state retention duration. If the cache is not evicted on time, long-running jobs can grow memory usage. If keys collide, retry states of two different items can get mixed up.

In Spring Batch, a key generator or retry context cache configuration should only be added when retry behavior needs to be stateful and item semantics are clearly defined. For most simple transient errors, a bounded stateless policy is easier to operate.

## 17. RetryPolicy does not replace timeouts and circuit breakers

A retry policy controls the number of retries, but it does not bound the duration of each I/O call. An HTTP call without a timeout can hang indefinitely even if the retry policy allows only one attempt.

Retrying can also send additional requests to an already overloaded service. For a dependent system with a high error rate, a circuit breaker may be needed to temporarily pause calls for a period, combined with timeouts, backoff, and concurrency limits.

| Mechanism | Responsibility |
|---|---|
| Timeout | Bounds the duration of a single call |
| RetryPolicy | Decides whether to retry |
| BackOffPolicy | Determines how long to wait between attempts |
| Circuit breaker | Temporarily halts calls when a dependent system shows widespread failures |
| Rate limiter/bulkhead | Limits the request rate or number of concurrent calls |

Do not continuously retry every network error across multiple workers. Total retried requests can far exceed the item count, causing a load amplification effect.

## 18. Common mistakes when using RetryPolicy

| Mistake | Consequence | Remedy |
|---|---|---|
| Retrying all `Exception`s | Data errors and configuration errors are retried unnecessarily | Classify specific exceptions |
| Confusing `maxAttempts` with additional retry count | Actual call count differs from expectations | Remember `SimpleRetryPolicy.maxAttempts` includes the initial attempt |
| Not inspecting the cause chain | Wrapped exceptions are not recognized as retryable | Configure cause traversal deliberately |
| Using an unbounded policy | Job may never terminate | Use an attempt limit or timeout |
| Not configuring backoff | Rapid retries overload the dependent service | Combine with a BackOffPolicy |
| Using retry instead of validation | Invalid data is retried repeatedly | Validate and skip/fail per business rules |
| Confusing RetryContext with ExecutionContext | Expecting retry state to survive a JVM restart | Save required checkpoints in ExecutionContext |
| Writer/processor with non-idempotent side effects | Retries cause duplicate writes or repeated actions | Use idempotency keys, outbox, or compensation |
| Custom policy without a stopping condition | Step gets stuck retrying | Design a deadline/attempt limit and test it |

## 19. Testing RetryPolicy

Policies should be tested both in isolation and through an actual step. For `SimpleRetryPolicy`, verify retryable, non-retryable, and wrapped exceptions.

Cases to include:

1. Retryable exception: policy permits retries up to the exact limit.
2. Non-retryable exception: policy stops immediately after the first attempt.
3. Cause chain containing a retryable exception: policy classifies properly when traversal is enabled.
4. Maximum attempts: confirm `maxAttempts` includes the initial execution.
5. Retryable exception followed by success: step completes and does not skip the item.
6. Retries exhausted: item is skipped if policy permits; otherwise the step fails.
7. Backoff: confirm wait intervals do not exceed configuration.
8. Stateful retry: same item uses the same key and state is cleaned up after recovery.
9. Restart: checkpoint is restored from JobRepository; do not rely on old RetryContext.
10. Writer retry: does not create duplicate data or duplicate side effects.

A simple unit test for `SimpleRetryPolicy` can verify the maximum retry count via a `RetryTemplate` or a step integration test. With Spring Batch, also verify `StepExecution` status, retry/skip counts, and committed transaction data after recovery.

## 20. Process for choosing a RetryPolicy for production

When designing retries for a step, clarify:

1. Which exceptions are genuinely transient and likely to succeed on retry?
2. Which exceptions must fail immediately or be handled by skip?
3. What is the maximum number of attempts including the initial attempt?
4. Is classification by cause chain or exception hierarchy needed?
5. Are the per-call backoff and timeout compatible with the SLA?
6. Are the reader, processor, and writer safe to invoke repeatedly?
7. Does stateful retry require a stable key or context cache?
8. Once retries are exhausted, should the item be skipped or should the step fail?
9. Which metrics indicate retries are climbing and a dependent service is degrading?
10. Do integration tests simulate rollback, retry, skip, and restart?

Start with a simple policy, clear limits, and a short exception list. Only add classifiers or custom policies when concrete requirements arise that basic configuration cannot express.

## Conclusion

`RetryPolicy` decides whether an operation may be retried after an exception and when retrying must stop. In Spring Batch 5, a Spring Retry policy can be attached to a fault-tolerant chunk step using `.retryPolicy(...)`. `SimpleRetryPolicy` works well for attempt limits and exception classification; classifier or custom policies fit when different error groups require different rules.

Keep responsibilities separate among RetryPolicy, BackOffPolicy, skip policy, and rollback classification. Only retry transient errors, set finite limits, traverse causes deliberately, and ensure operations are safe when re-invoked. RetryContext tracks retry attempts, whereas ExecutionContext persists checkpoints for restart; these two kinds of state are not interchangeable.
