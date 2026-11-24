# SkipPolicy in Spring Batch

In Spring Batch, an item may fail during reading, processing, or writing. Not every error has to force the entire step to fail. For errors tied to a specific record that can be safely discarded, the application can allow the step to skip that item and continue processing the rest.

SkipPolicy is the component that decides whether an exception is allowed to be skipped. It helps distinguish acceptable data errors from infrastructure or critical errors that must stop the job. You can declare the policy using skip(), noSkip(), and skipLimit(), or implement a custom SkipPolicy when business rules are more complex.

## 1. What is SkipPolicy?

SkipPolicy is a Spring Batch contract used to evaluate exceptions thrown during chunk processing. The policy receives the exception and the number of items already skipped, and then decides whether to allow skipping the current exception.

Basic contract:

```java
public interface SkipPolicy {

    boolean shouldSkip(Throwable t, long skipCount)
        throws SkipLimitExceededException;
}
```

The two parameters mean:

- t: the exception under evaluation.
- skipCount: the number of items already skipped in the step prior to the current evaluation.

If the policy returns true, the exception is considered skippable and the framework can skip the corresponding item, depending on the stage where the error occurred. If the policy returns false, the exception is not skipped and usually causes the step to fail after any applicable retry mechanisms have run. The policy can also throw SkipLimitExceededException to signal that the skip limit has been exceeded.

SkipPolicy only decides whether skipping is permitted. It does not persist failed records, log on the application's behalf, or decide retries. Those responsibilities belong to the listener, writer, or retry policy respectively.

## 2. In which stages do skips occur?

In a chunk-oriented step, exceptions can occur in three stages:

| Stage | Example | Corresponding skip callback |
| --- | --- | --- |
| Read | File has a malformed line; reader cannot parse a record. | SkipListener.onSkipInRead(Throwable) |
| Process | Processor detects an invalid record and throws an exception. | SkipListener.onSkipInProcess(item, Throwable) |
| Write | Writer cannot write an output item due to a constraint or invalid data. | SkipListener.onSkipInWrite(item, Throwable) |

The policy evaluates exceptions according to the step configuration, regardless of which phase throws them. If the exception is skippable, Spring Batch updates the corresponding counter such as readSkipCount, processSkipCount, or writeSkipCount.

Do not confuse skip with two other cases:

- ItemReader.read() returning null means the end of input has been reached, not an exception and not a skip.
- ItemProcessor.process() returning null means the item was filtered according to business rules, not skipped.

For example, a cancelled order can be filtered by the processor returning null. A malformed CSV line can cause the reader to throw FlatFileParseException; if the policy allows it, that line is skipped. These two cases must be tracked separately.

## 3. When should you skip and when should you fail?

Skip is appropriate when an exception represents an isolated item, discarding that item does not impair the ability to process subsequent items, and business rules accept an outcome without that item.

Examples where skip may be considered:

- A malformed CSV line where other lines are independent.
- A record missing an optional field or violating a discardable rule.
- An output item violating a unique constraint due to duplicate data that business rules specify should be discarded.

Errors that generally should not be skipped:

- Database disconnection leaving the reader unaware of the next read position.
- Wrong credentials or lack of permission to access the data source.
- Missing required input file.
- Programming errors such as NullPointerException caused by a bug in the processor.
- Errors making all data after the current position impossible to interpret properly.

For transient errors such as timeouts or deadlocks, retry may be more suitable than skip. Skipping a connection error could leave the rest of the data unread while the job still reports completion. The decision must depend on the nature of the exception and the reader/writer's ability to continue safely.

## 4. Configuring skip with skip(), noSkip(), and skipLimit()

For simple rules, there is no need to write a custom SkipPolicy. You can declare them directly on a fault-tolerant step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderEntity> processor,
        ItemWriter<OrderEntity> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .noSkip(IllegalStateException.class)
        .skipLimit(20)
        .build();
}
```

Meaning:

- faultTolerant() enables fault-tolerance configuration for the chunk step.
- skip(FlatFileParseException.class) allows skipping file parsing errors.
- skip(InvalidOrderException.class) allows skipping specifically classified business errors.
- noSkip(IllegalStateException.class) marks an exception type as unskippable, even if a broader rule might match.
- skipLimit(20) sets the limit on the total number of items skipped in the step.

skip() and noSkip() operate on exception types, including exception inheritance hierarchies. Therefore, be careful when declaring a broad superclass. Allowing a skip on an overly general class may classify many unintended subclasses as skippable.

For example, if configuring skip(Exception.class), carefully review system errors such as authentication or state errors. It is better to list specific data exceptions and let unclassified errors fail the step.

## 5. How is skip limit calculated?

skipLimit bounds the total number of skips for the step. It applies cumulatively across read, process, and write errors, not as an independent limit per phase.

For example with:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(3)
```

The step can accept three skipped items. When a subsequent skippable item pushes the total past the limit, the step fails with SkipLimitExceededException.

| Skips already occurred | Outcome on one more skippable error |
| ---: | --- |
| 0 | Can skip the first error. |
| 1 | Can skip the next error. |
| 2 | Can skip the third error. |
| 3 | Next error exceeds the limit; step fails. |

If skipLimit is not configured, the default is 0; no items are allowed to be skipped under the default limit. The limit value should be based on business rules, data scale, and the system's error tolerance.

Do not set the limit too high just so the job always finishes. For example, a 100,000-line file with 30,000 skipped lines may indicate a widespread format mismatch. A reasonable limit helps the step stop early to avoid producing incomplete outputs undetected.

## 6. Skip count is shared across phases

Suppose skipLimit(5) and the step has already recorded:

- 2 read skips due to malformed CSV lines.
- 2 process skips due to invalid orders.
- 1 write skip due to data violating a constraint.

The total skip count is already 5. One more item needing a skip will exceed the limit, regardless of whether it occurs during read, process, or write.

This matters when setting thresholds. If you want to monitor read and process error rates separately, you can use StepExecution's individual counters or listener metrics; however, the standard skip limit remains the step-wide total limit.

Commonly used counters:

| Counter | Meaning |
| --- | --- |
| readSkipCount | Number of items skipped in the reader. |
| processSkipCount | Number of items skipped in the processor. |
| writeSkipCount | Number of items skipped in the writer. |
| readCount | Number of items successfully supplied by the reader. |
| filterCount | Number of items filtered by the processor returning null. |

Do not add filterCount to skip count. Filtering is not an error and does not invoke SkipPolicy.

## 7. Exception classification and rule precedence

Choosing the right exception types is the most important part of a skip policy. A superclass exception may represent many subclasses with different meanings. For example, DataAccessException can include transient errors, constraint errors, or data-access configuration errors.

Prefer specific classification:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.noSkip(AccessDeniedException.class)
.noSkip(IllegalStateException.class)
.skipLimit(25)
```

This example allows skipping known data errors while excluding certain unrecoverable errors. When combining a broad superclass with specific subclasses, check the classification rules of the Spring Batch version in use and write tests for exceptions with inheritance relationships.

A good classification should answer:

- Does the exception point to one specific item?
- Can the reader continue reading the next item?
- Can the item be discarded without distorting business results?
- Could the error go away after a retry?
- Is the error a configuration issue or bug that requires stopping immediately?

Do not rely on exception message text for classification when dedicated exception types can be used. Messages can change across drivers, locales, or library versions.

## 8. Implementing a custom SkipPolicy

When rules depend on multiple conditions, you can implement the SkipPolicy interface. Example policy allowing skips only for InvalidOrderException and FlatFileParseException, with a total limit of 10:

```java
public class ImportSkipPolicy implements SkipPolicy {

    private static final long SKIP_LIMIT = 10;

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (!isSkippable(throwable)) {
            return false;
        }

        if (skipCount >= SKIP_LIMIT) {
            throw new SkipLimitExceededException(
                "Skip limit of " + SKIP_LIMIT + " exceeded",
                skipCount
            );
        }

        return true;
    }

    private boolean isSkippable(Throwable throwable) {
        return throwable instanceof InvalidOrderException
            || throwable instanceof FlatFileParseException;
    }
}
```

This policy:

1. Classifies the exception first.
2. Returns false for error types not permitted to be skipped.
3. Checks the number of skips already occurred.
4. Throws SkipLimitExceededException once the limit is reached.
5. Returns true only for matching errors still within the limit.

When implementing a custom policy, the policy itself must handle the limit. Do not assume skipLimit() will automatically apply identically once a custom policy replaces the policy built from skip() declarations.

Registering the custom policy:

```java
@Bean
SkipPolicy importSkipPolicy() {
    return new ImportSkipPolicy();
}

@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer,
                      SkipPolicy importSkipPolicy) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(importSkipPolicy)
        .build();
}
```

When using skipPolicy(), place all classification and limit logic inside that policy. Avoid mixing multiple skip configuration styles that make it hard for readers to tell which rules take effect.

## 9. Business-data-dependent SkipPolicy

Some systems must decide skips based on error type and context. For example, allow skipping validation errors only if the file belongs to non-mandatory data; whereas a financial reconciliation file must stop on any validation error.

Not every SkipPolicy has direct access to StepExecution or the input item. The standard contract only receives Throwable and skipCount. If the decision depends on business data, you can:

- Encode the error category into a dedicated exception, such as OptionalRecordValidationException.
- Use distinct exception subclasses for different data groups.
- Create policy beans with fixed per-step configuration.
- Put decision rules in the service/processor and throw clearly classified exceptions.
- Use a StepExecutionListener or context to set state beforehand, if the policy is designed to read that information safely.

Avoid casually using static variables or ThreadLocal to pass items into the policy. Those approaches easily break when the step runs multi-threaded or partitioned.

For example, the processor can throw two exception types:

```java
if (order.isOptionalRecord() && !order.isValid()) {
    throw new OptionalRecordValidationException(order.getId());
}

if (!order.isValid()) {
    throw new MandatoryRecordValidationException(order.getId());
}
```

The policy can permit skipping the optional type and reject the mandatory type. The rule is expressed through clear types, easy to test, and independent of message strings.

## 10. Combining RetryPolicy and SkipPolicy

Retry and skip solve two different situations:

- Retry re-attempts an operation likely to succeed if a transient error disappears.
- Skip accepts discarding a failing item when business rules allow continuing without it.

Both can be configured in a fault-tolerant step:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(20)
```

In this example:

- TransientDataAccessException can be retried up to the retry limit.
- InvalidOrderException is allowed to be skipped within the skip limit.
- Errors matching neither retry nor skip policy cause the step to fail.

Do not configure the same exception type for both retry and skip without clear intent. If a transient connection error is retried and still fails, skipping it could leave the reader unable to continue. Only combine both policies for the same exception when you understand how the reader/writer recovers and the business accepts discarding that item.

When a retry succeeds, the item is not skipped and SkipListener is not invoked for the recovered transient error. If retries fail, the framework continues handling according to the remaining policy matching the configuration and exception type.

## 11. SkipPolicy and rollback

Skip does not mean the transaction is always committed at the moment an exception occurs. Chunk processing still protects transaction boundaries. Depending on the phase and exception type, Spring Batch may roll back the transaction to isolate the failing item and then continue processing the chunk.

For example, the writer receives a multi-item chunk and fails while writing one item. The framework may roll back the chunk and re-execute write operations using a mechanism that identifies the failing item. If that item is allowed to be skipped, the remaining items can be written successfully in the reprocessed chunk.

Key points to remember:

- Previously committed chunks remain intact.
- The current chunk may roll back before the skip completes.
- The writer may be re-invoked during write-skip handling.
- Side effects outside the transaction do not automatically roll back.
- Custom readers must be able to continue or restore position after a rollback.

noRollback() is a separate configuration designating exceptions that do not trigger transaction rollback under step policy. It does not replace SkipPolicy and does not automatically allow skipping. Only use noRollback when you understand the exception's impact on transactional data and want to keep the current transaction going.

## 12. How do SkipPolicy and SkipListener work together?

The two components have complementary responsibilities:

| Component | Question answered |
| --- | --- |
| SkipPolicy | Is this exception allowed to be skipped? |
| SkipListener | Which item was skipped, in which phase, and due to which exception? |

Example listener:

```java
public class OrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        repository.save(RejectedOrder.fromReadException(t));
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        repository.save(RejectedOrder.fromOrder(item, "PROCESS", t));
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        repository.save(RejectedOrder.fromEntity(item, "WRITE", t));
    }
}
```

Registering both the policy and the listener:

```java
.faultTolerant()
.skipPolicy(importSkipPolicy)
.listener(orderSkipListener)
```

The policy decides whether the item can be skipped; the listener records the skip result. If persisting to quarantine is required for reconciliation, ensure the listener writes to an appropriately transactional resource or implements idempotency when writing outside the transaction.

## 13. SkipPolicy in multi-threaded steps and partitioning

When a step runs multi-threaded or partitioned, the policy may be called concurrently from multiple workers depending on the architecture. A SkipPolicy registered as a singleton should be stateless or thread-safe.

Avoid storing skipCount in an internal field of the policy:

```java
// Avoid: this state can be shared across workers.
private long skipped;
```

Use the skipCount parameter passed by the framework on each shouldSkip() call. If per-partition or per-phase metrics are needed, use StepExecution counters, listeners, or tagged metrics.

In partitioning, each worker step has its own execution and skip count. Skip limits typically apply per worker step execution, not automatically as a global limit across the entire manager job. If business rules require a job-wide total limit, a dedicated aggregation and coordination mechanism with safe concurrency handling is needed.

With remote partitioning, the policy must be configured consistently across workers. Do not assume the manager's policy is automatically serialized to workers over messaging; worker steps must have the proper skip configuration in the worker application.

## 14. Unit testing SkipPolicy in isolation

A custom policy can be unit-tested without launching Spring Batch. Test allowed exceptions, rejected exceptions, and limits:

```java
class ImportSkipPolicyTest {

    private final ImportSkipPolicy policy = new ImportSkipPolicy();

    @Test
    void allowsKnownDataExceptionsBelowLimit() throws Exception {
        assertThat(policy.shouldSkip(
            new InvalidOrderException("Invalid order"), 0
        )).isTrue();
    }

    @Test
    void rejectsUnexpectedException() throws Exception {
        assertThat(policy.shouldSkip(
            new IllegalStateException("Programming error"), 0
        )).isFalse();
    }

    @Test
    void throwsWhenLimitHasAlreadyBeenReached() {
        assertThatThrownBy(() -> policy.shouldSkip(
            new InvalidOrderException("Invalid order"), 10
        )).isInstanceOf(SkipLimitExceededException.class);
    }
}
```

This test verifies the policy's logic. Supplement it with integration tests verifying the policy is attached properly to the step and Spring Batch updates skip counts/status as expected.

## 15. Testing skip in a chunk step

An integration test can use a reader providing three orders, a processor throwing an exception for one order, and a writer persisting the remaining orders. Configure the step with the corresponding policy or skip().

Useful assertions:

- The job/step completes if skips remain within the limit and no other errors occur.
- readCount reflects the number of items supplied by the reader.
- processSkipCount increments by the exact number of processor-failed items skipped.
- writeCount reflects the number of output items successfully written.
- SkipListener.onSkipInProcess() receives the expected item and exception.
- The quarantine repository contains the error record if recorded by the listener.

Also test exceeding the limit. For example, skipLimit(2) when three items trigger policy-allowed errors; the step must fail when the next skip exceeds the limit. Verify JobExecution/StepExecution have FAILED status and the appropriate failure exception.

For read skips, use a mock/stub reader throwing an exception at a resumable position. For write skips, use a test writer capable of isolating a failing output item. Do not test only the processor and assume read and write skips behave identically.

## 16. Common mistakes when configuring SkipPolicy

**Skipping all Exceptions:** an overly broad policy can swallow connection errors, authentication failures, or bugs. Only permit classified data exceptions.

**Omitting skip limit:** when using the DSL, the default limit is 0; declaring exceptions without setting a limit may prevent any item from being skipped.

**Treating the limit as per-phase:** the standard skip limit is the combined total of read, process, and write in the step.

**Using skip instead of retry:** transient errors should be retried if the operation can be repeated safely; skip is a decision to discard an item.

**Using skip for non-resumable reader errors:** losing a connection or cursor can leave the reader unable to locate the next item. Failing is usually safer.

**Confusing filter with skip:** a processor returning null does not invoke the policy and does not increment skip count.

**Custom policy failing to check the limit:** when implementing a custom policy, it must explicitly decide when to throw SkipLimitExceededException.

**Keeping mutable state in a singleton policy:** multi-threaded/partitioned steps can invoke the policy concurrently. Use the passed skipCount instead of an internal counter.

**Assuming the listener decides skips:** SkipListener only receives notifications; the policy decides which exceptions can be skipped.

**Ignoring transactions when persisting quarantine records:** error records may roll back with the chunk or be duplicated on retry. Choose appropriate transactions and idempotency.

## 17. Designing SkipPolicy for production

First, list the exceptions that can occur in the reader, processor, and writer. For each type, classify whether it is an item-level data error, a transient retryable error, or an infrastructure error/bug requiring a stop. Prefer specific exception classes and avoid using message text as the primary rule.

For simple rules, use skip(), noSkip(), and skipLimit() directly on the step. When decisions require multiple conditions or reusable classification logic, implement a custom SkipPolicy and have it manage limits clearly. In partitioned environments, keep the policy stateless/thread-safe and understand that skip limits apply per worker execution.

Combine the policy with SkipListener to trace skipped items, without placing hard-to-rollback side effects inside callbacks. Monitor read/process/write skip counts, filter counts, and error rates; set thresholds so the job stops when data quality crosses acceptable boundaries.

SkipPolicy helps Spring Batch continue processing when some erroneous items can be safely discarded. A sound policy classifies exceptions clearly, bounds skip counts, and coordinates with retry, listeners, and transaction boundaries so the job neither hides system errors nor silently produces incomplete data.
