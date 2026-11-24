# Exception classifier

In Spring Batch, an exception classifier is a mechanism for categorizing exceptions by error type or root cause to select the appropriate handling policy. A chunk Step can encounter per-item data errors, transient database access errors, configuration errors, or fatal system errors. Each category requires a different response: retry, skip, rollback, or stopping the Step.

Instead of treating every exception as the same kind of error, a classifier maps an exception to a category or policy. For example, `InvalidRecordException` may be allowed to skip; `DeadlockLoserDataAccessException` may be retried; `FatalImportException` must fail the Step. Proper classification helps the Job continue when recovery is possible and stop early when data or system state can no longer be trusted.

## 1. What is an exception classifier?

A classifier takes an input object—in this case a `Throwable`—and returns a classification result. The result can be an enum, a boolean, or a specific policy.

```text
Exception thrown
       |
       v
 Exception classifier
       |
       +-- Item data error ----------> SkipPolicy
       |
       +-- Transient error ----------> RetryPolicy
       |
       +-- Unsafe error -------------> Fail Step
       |
       +-- Non-rollback error -------> No-rollback rule (if appropriate)
```

The classifier only decides which category or policy applies to the exception. The policy executor determines the final action, such as whether to retry, whether the skip limit is exhausted, or whether the transaction rolls back.

A good classifier needs clear, stable, and testable rules. Avoid classifying based on exception message strings when you can use the exception type or structured error codes, because messages can change across library versions, databases, or locales.

## 2. Why do we need exception classification?

In an import Job, many different errors can occur:

| Exception or situation | Error category | Typical handling approach |
|---|---|---|
| `InvalidRecordException` | Individual item data is invalid | Skip if business rules allow and within limit. |
| `FlatFileParseException` | A source line cannot be parsed | Read skip if the reader can continue safely. |
| `DeadlockLoserDataAccessException` | Database contention that may be transient | Retry with a limit and backoff. |
| `TransientDataAccessException` | Temporary data access failure | Retry if the operation is safe to repeat. |
| `FatalImportException` | Unrecoverable business/system error | Fail Step. |
| `FileNotFoundException` for a required file | Missing Job-level input | Usually fail early; do not skip item by item. |

Without classification, applications easily fall into two opposite mistakes:

- Retrying permanent data errors, causing the same item to fail repeatedly with no chance of self-recovery.
- Skipping infrastructure errors, causing the Job to report completion even though part of the data was not processed due to a database or external service outage.

A classifier helps set policies based on the actual root cause rather than applying one generic handling rule to every exception.

## 3. Classifying by exception type

The simplest approach is checking the exception type with `instanceof` or configuring exception classes on the builder.

Example classification in Java:

```java
enum FailureKind {
    INVALID_DATA,
    TRANSIENT_INFRASTRUCTURE,
    FATAL,
    UNKNOWN
}

public class BatchExceptionClassifier {

    public FailureKind classify(Throwable throwable) {
        if (throwable instanceof FatalImportException) {
            return FailureKind.FATAL;
        }

        if (throwable instanceof InvalidRecordException) {
            return FailureKind.INVALID_DATA;
        }

        if (throwable instanceof TransientDataAccessException) {
            return FailureKind.TRANSIENT_INFRASTRUCTURE;
        }

        return FailureKind.UNKNOWN;
    }
}
```

Check order matters when exceptions share an inheritance hierarchy. For example, if a specific exception extends a general parent class, check the specific case first. If you check the parent class first, the specific branch may never execute.

In this example, `UNKNOWN` is not automatically treated as skippable or retryable. An unclassified error should be handled conservatively, typically failing the Step and adding a rule after understanding the cause.

## 4. Using built-in fault tolerance configuration

For simple rules, you do not need to write a custom classifier. Spring Batch lets you declare retryable, skippable, and non-rollback exceptions directly on a fault-tolerant Step.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(InvalidRecordException.class)
            .skip(FlatFileParseException.class)
            .skipLimit(50)
            .noSkip(FatalImportException.class)
            .build();
}
```

In this example:

- `TransientDataAccessException` is selected for retries up to the retry limit.
- `InvalidRecordException` and `FlatFileParseException` are allowed to be skipped up to a total limit of 50 items.
- `FatalImportException` is excluded from the skippable exception group.

This is how type-based classification is configured using the Step builder API. If there are only a few clear exception groups, this approach is usually more readable and easier to maintain than a custom classifier.

Do not broadly configure `.skip(Exception.class)` and then try to exclude every serious error with `.noSkip(...)`. Start from the list of specific exceptions approved by business rules.

## 5. Classifying retries with ExceptionClassifierRetryPolicy

When each exception group needs a different retry policy, Spring Retry provides `ExceptionClassifierRetryPolicy`. This policy selects a `RetryPolicy` based on the exception thrown.

For example, deadlocks are retried up to 4 times, optimistic locking errors up to 2 times, and exceptions not in the map are not retried:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.classify.SubclassClassifier;
import org.springframework.retry.RetryPolicy;
import org.springframework.retry.policy.ExceptionClassifierRetryPolicy;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;

@Bean
RetryPolicy classifiedRetryPolicy() {
    Map<Class<? extends Throwable>, RetryPolicy> policies =
            new HashMap<>();

    policies.put(
            DeadlockLoserDataAccessException.class,
            new SimpleRetryPolicy(4));

    policies.put(
            OptimisticLockingFailureException.class,
            new SimpleRetryPolicy(2));

    ExceptionClassifierRetryPolicy classifierPolicy =
            new ExceptionClassifierRetryPolicy();

    classifierPolicy.setExceptionClassifier(
            new SubclassClassifier<>(policies, new NeverRetryPolicy()));

    return classifierPolicy;
}
```

`SubclassClassifier` selects a policy based on the exception type and its superclasses. The default `NeverRetryPolicy` means exceptions not matching the map will not be retried. `SimpleRetryPolicy` caps the number of attempts; in Spring Retry, `maxAttempts` includes the initial execution.

Registering the policy on the Step:

```java
return new StepBuilder("updateOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retryPolicy(classifiedRetryPolicy)
        .build();
```

When using `.retryPolicy(...)`, the custom policy governs retry behavior; avoid declaring additional `.retry(...)`/`.retryLimit(...)` rules at the same time without understanding how the builder combines configurations. Check the API for your application's Spring Batch and Spring Retry versions.

### When to use ExceptionClassifierRetryPolicy?

It is useful when:

- Different exception groups have different maximum attempt counts.
- Some errors need retries while others must fail immediately.
- The retry policy depends on error type or an explicit classification rule.
- You want to reuse built-in Spring Retry policies instead of writing an entire `RetryPolicy` from scratch.

If all retryable exceptions share the same limit and backoff, configuring `.retry(...)` with `.retryLimit(...)` may be sufficient.

## 6. Classifying skips with SkipPolicy

A skip policy decides whether an exception can be skipped. For simple rules, use `.skip(...)`, `.noSkip(...)`, and `.skipLimit(...)`. When classification across multiple groups is needed, you can implement `SkipPolicy`.

Basic contract:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException;
}
```

Example policy that only skips item-specific data errors within the limit:

```java
public class ClassifiedOrderSkipPolicy implements SkipPolicy {

    private final long skipLimit;

    public ClassifiedOrderSkipPolicy(long skipLimit) {
        this.skipLimit = skipLimit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        if (throwable instanceof FatalImportException) {
            return false;
        }

        if (!(throwable instanceof InvalidRecordException)
                && !(throwable instanceof FlatFileParseException)) {
            return false;
        }

        return skipCount < skipLimit;
    }
}
```

The policy returns `true` when the exception is allowed to be skipped and the limit has not been exceeded. When returning `false`, the exception is not skipped and propagates according to the Step's mechanism. If you need to distinguish limit exhaustion explicitly with `SkipLimitExceededException`, a custom policy can throw that exception per Spring Batch's contract.

Registering the custom policy:

```java
.faultTolerant()
.skipPolicy(new ClassifiedOrderSkipPolicy(50))
```

When using a custom `SkipPolicy`, the policy is responsible for deciding which exceptions are skipped. Do not mix `.skip(...)`, `.noSkip(...)`, and a custom policy without verifying the builder's combination rules.

## 7. ExceptionClassifierSkipPolicy

Spring Batch also provides `ExceptionClassifierSkipPolicy` to delegate skip decisions to a policy classified by exception. The idea is similar to `ExceptionClassifierRetryPolicy`: different exceptions can be routed to different `SkipPolicy` instances.

Example policy organization:

```text
Exception
   |
   v
Classifier<Throwable, SkipPolicy>
   |
   +-- InvalidRecordException --> LimitCheckingItemSkipPolicy
   |
   +-- FlatFileParseException --> LimitCheckingItemSkipPolicy
   |
   +-- FatalImportException ---> NeverSkipItemSkipPolicy
   |
   +-- Unknown exception ------> NeverSkipItemSkipPolicy
```

In this design, each exception group maps to an appropriate skip policy. The default policy should be no-skip so unknown errors are never bypassed unintentionally. The exact configuration of the classifier and policy map depends on the Spring Batch version; when you only need a few straightforward rules, a custom `SkipPolicy` can be easier to read than wiring multiple adapter classes.

## 8. Exception classification and the cause chain

In Spring applications, the actual exception may be wrapped inside another exception. For example, a database error may appear inside `DataAccessException`, `RetryException`, or a service-layer exception.

```text
BatchProcessingException
        |
        +-- cause: DataAccessException
                   |
                   +-- cause: SQLException
```

If a classifier checks only the outermost exception type, it may miss the underlying error. Conversely, always taking the root cause can discard the meaning of the outer domain exception.

One approach is traversing the cause chain in order and prioritizing explicitly defined exception types:

```java
public FailureKind classify(Throwable throwable) {
    for (Throwable current = throwable;
            current != null;
            current = current.getCause()) {

        if (current instanceof FatalImportException) {
            return FailureKind.FATAL;
        }

        if (current instanceof InvalidRecordException) {
            return FailureKind.INVALID_DATA;
        }

        if (current instanceof TransientDataAccessException) {
            return FailureKind.TRANSIENT_INFRASTRUCTURE;
        }
    }

    return FailureKind.UNKNOWN;
}
```

This is an example of cause-chain classification. Priority order must reflect application policy. If the outermost exception is a fatal error while the inner cause is a transient error, the application should usually honor the fatal classification of the domain exception rather than automatically retrying just because a transient cause was found.

Do not traverse the cause chain indefinitely without cycle detection. In practice, standard cause structures do not form cycles, but a shared helper should still guard against `cause == current` or unusual wrappers.

## 9. Classifying by exception type or error code?

Type-based classification is usually the first choice because exception classes express error categories in code. However, some systems use the same exception type for multiple database or external service error codes.

For example, `DataIntegrityViolationException` can represent a unique constraint, foreign key constraint, or another data violation. If business rules only allow skipping duplicate keys, the classifier must inspect the SQL state, vendor error code, or a pre-mapped domain exception.

Avoid matching message strings such as `"duplicate key"` when the driver provides structured error codes. Messages can change across databases or driver versions.

A good design direction:

1. In the repository/service layer, translate understood technical errors into specific domain exceptions when appropriate.
2. Preserve the original cause to investigate the root issue.
3. The Batch-layer classifier classifies domain exceptions or structured error codes.
4. The policy decides retry, skip, or fail.

For example, a service can throw `DuplicateOrderException` when detecting a duplicate unique key per a verified rule. The Batch Step only needs to know whether `DuplicateOrderException` should be skipped, without parsing SQL messages inside the processor.

## 10. Classifier and rollback policy

Retry, skip, and rollback are three related but distinct decisions:

- **Retry:** should the operation be re-attempted after the exception?
- **Skip:** can the failing item be bypassed so processing continues?
- **Rollback:** must the current transaction roll back when the exception occurs?

Spring Batch allows configuring exceptions not to roll back via `.noRollback(...)` in a fault-tolerant Step:

```java
.faultTolerant()
.noRollback(NonCriticalValidationException.class)
```

`noRollback` does not mean the exception is skipped or retried. It only changes rollback behavior for the specified exception type. If the Step does not handle that exception under another policy, the exception can still cause the Step to fail.

Use `noRollback` only after verifying that the transaction can continue consistently after the exception. For errors occurring after the writer has already modified partial data, avoid disabling rollback if doing so could leave an incomplete state.

## 11. Exception classifier decision table

A policy matrix helps development teams standardize error handling:

| Group | Example | Retry | Skip | Result when unrecoverable |
|---|---|---|---|---|
| Invalid item data | `InvalidRecordException` | Usually no | Yes, if business permits | Fail when skip limit exceeded. |
| Single-line parse error | `FlatFileParseException` | Usually no | Yes, if reader continues safely | Fail when skip limit exceeded. |
| Database deadlock | `DeadlockLoserDataAccessException` | Bounded | Usually no | Fail Step after retry exhaustion. |
| Temporary service error | Classified timeout exception | Bounded/backoff | Usually no | Fail Step if retries exhausted. |
| Missing required file | `FileNotFoundException` | Usually no | No | Fail early. |
| Configuration or programming error | Exception marked fatal | No | No | Fail Step/Job. |
| Unknown exception | `UNKNOWN` | Not by default | Not by default | Fail for investigation. |

This table is only a design template. A specific exception may be handled differently depending on business rules, reader/writer type, and operation idempotency.

## 12. Precedence when multiple rules apply

When an exception can match multiple rules, precedence rules must be defined. For example:

```java
class InvalidRecordException extends RuntimeException { }
class FatalImportException extends RuntimeException { }
```

If a classifier uses a class-hierarchy map, the specific exception should be selected before a general parent class. For a custom classifier using `instanceof`, `if` order also affects the result.

Principles to follow:

- Check specific domain exceptions before general parent classes.
- Set the default policy to fail/no retry/no skip.
- Never let a broad rule like `RuntimeException` swallow every case.
- When inspecting the cause chain, explicitly define precedence between outer exceptions and inner causes.
- Test multi-level exception inheritance and wrapped exceptions.

## 13. A classifier is not a listener

Both classifiers and listeners may be invoked when an exception occurs, but their responsibilities differ:

| Component | Role |
|---|---|
| Exception classifier | Classifies an exception or selects a policy. |
| RetryPolicy | Decides whether retrying is still allowed. |
| SkipPolicy | Decides whether a failing item can be skipped. |
| RetryListener | Observes retry operations and failed attempts. |
| SkipListener | Records items that were actually skipped. |
| StepExecutionListener | Observes state before/after the Step. |

Do not place retry decisions inside `RetryListener.onError` or skip decisions inside `SkipListener`. Listeners are meant for logging, metrics, and auditing; classifiers/policies decide fault-tolerance behavior.

## 14. Thread safety and performance

A classifier can be called many times and from multiple threads if a Step runs concurrently or multiple Jobs share the same bean. Therefore:

- Prefer stateless and thread-safe classifiers.
- Do not store the current exception in a mutable singleton field.
- Do not make database or HTTP calls inside `classify`.
- Do not parse stack traces or long messages unnecessarily.
- Keep policy maps immutable after initialization.
- Use `RetryContext` or execution context for per-operation state, not shared fields.

Classification is normally a small operation per exception. However, retry/skip can cause a classifier to be invoked multiple times within a single chunk. Keeping the logic deterministic and fast avoids increasing error-handling latency.

## 15. Logging and metrics by exception category

After classification, the application can record error counts by category to monitor data quality and infrastructure health.

Useful metrics:

- Retry count by exception category.
- Skipped item count by error type and read/process/write phase.
- Failed Step count by error category.
- Retry exhaustion count.
- Average recovery time after transient errors.

Use low-cardinality tags such as Job name, Step name, and exception category. Do not use customer ID, order ID, or arbitrary messages as metric tags because they can create an enormous number of time series.

Logs should include JobExecution ID, StepExecution ID, exception type, and an allowable business key. Avoid logging passwords, tokens, personal data, or full payloads.

## 16. Testing the exception classifier

Classifiers must be tested independently because a small mistake can cause data to be skipped or a transient error not to be retried.

Cases to test:

- Data exceptions are classified as skip.
- Transient exceptions are classified as retry.
- Fatal exceptions are neither retried nor skipped.
- Unknown exceptions fall into a safe default policy.
- Subclasses are classified under specific rules rather than an overly broad parent class.
- Wrapped exceptions are handled according to the chosen cause-chain rules.
- Skip limit is enforced accurately at the boundary value.
- Retry max attempts and backoff match configuration.
- Concurrent use of the classifier across multiple threads does not mix state.

Simple classifier unit test example:

```java
class BatchExceptionClassifierTest {

    private final BatchExceptionClassifier classifier =
            new BatchExceptionClassifier();

    @Test
    void classifiesInvalidRecordAsDataError() {
        assertEquals(
                FailureKind.INVALID_DATA,
                classifier.classify(new InvalidRecordException("bad row")));
    }

    @Test
    void classifiesTransientDatabaseFailure() {
        assertEquals(
                FailureKind.TRANSIENT_INFRASTRUCTURE,
                classifier.classify(new TransientDataAccessException("timeout") { }));
    }

    @Test
    void unknownExceptionIsNotAutomaticallyRetryable() {
        assertEquals(
                FailureKind.UNKNOWN,
                classifier.classify(new IllegalStateException("unexpected")));
    }
}
```

The exception classes in this example are the application's domain classes or corresponding Spring exceptions. Step-level integration tests should verify that the classifier/policy actually affects retry count, skip count, transaction rollback, and `BatchStatus` as expected.

## 17. Common mistakes

### Classifying every RuntimeException as retryable

Many programming errors and data errors are also unchecked exceptions. Retrying them can repeat the exact same error with no chance of recovery. Retry only transient error types.

### Skipping every unknown exception

This hides infrastructure errors or programming bugs. The default classifier should fail/no skip/no retry for unrecognized exceptions.

### Checking parent classes before specific exceptions

A general rule can intercept specific branches. Prioritize specific domain exceptions and test classification order.

### Checking only the outermost exception

Wrapped exceptions can obscure the root cause. Explicitly decide whether to traverse the cause chain; do not assume every classifier checks the root cause automatically.

### Relying on messages to identify errors

Messages can change by driver, locale, or version. Prefer classes, SQL state, vendor codes, or domain exceptions.

### Confusing classifiers with listeners

Listeners observe events; classifiers/policies decide behavior. Do not put skip/retry decision logic inside listeners.

### Sharing mutable state in a classifier

A singleton classifier can be called concurrently. Keep classifiers stateless or use thread-safe structures.

### Ignoring idempotency when retrying

A classifier may choose retry properly while the underlying operation still creates duplicate side effects. Writers and external services need idempotency keys, unique keys, or an outbox.

## 18. Exception classifier design workflow

When building a fault-tolerance policy, you can follow this sequence:

1. List exceptions that can arise in the reader, processor, and writer.
2. Distinguish per-item data errors, transient errors, configuration errors, and fatal errors.
3. Create specific domain exceptions at the business layer when technical exceptions are too generic.
4. Choose simple classification via `.retry(...)`, `.skip(...)`, and `.noSkip(...)` if sufficient.
5. Use `ExceptionClassifierRetryPolicy` when each group needs a separate retry policy.
6. Use a custom `SkipPolicy` or exception classifier skip when complex skip rules are needed.
7. Set the default to no retry/no skip for unknown exceptions.
8. Define how wrappers/cause chains are handled and the precedence of specific exceptions.
9. Check transaction rollback and idempotency of retried operations.
10. Add listeners, logs, and metrics for observability without using listeners in place of policies.
11. Test the exception hierarchy, retry exhaustion, skip limit, and concurrency.

| Need | Suitable mechanism |
|---|---|
| A few exceptions sharing the same retry limit | `.retry(...)` and `.retryLimit(...)` |
| Each exception type needs its own retry policy | `ExceptionClassifierRetryPolicy` |
| A few data exceptions allowed to skip | `.skip(...)`, `.noSkip(...)`, `.skipLimit(...)` |
| Skip rules based on multiple conditions | Custom `SkipPolicy` or classifier skip policy |
| Observing each retry attempt | `RetryListener` |
| Recording skipped items | `SkipListener` |
| An exception should not roll back the transaction | `.noRollback(...)`, after verifying consistency |

## Conclusion

An exception classifier maps exceptions to error categories or policies so Spring Batch can handle them appropriately. Use `.retry(...)`, `.skip(...)`, `.noSkip(...)`, and `.noRollback(...)` for simple rules; use `ExceptionClassifierRetryPolicy` or a custom `SkipPolicy` when each exception group requires a different policy. Prefer exception types or structured error codes, handle exception hierarchies and cause chains explicitly, default to failing on unknown causes, test retry/skip limits, and ensure retried operations are idempotent. The classifier decides categorization; listeners only observe and record events.
