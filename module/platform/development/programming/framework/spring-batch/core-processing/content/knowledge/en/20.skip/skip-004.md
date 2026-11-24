# Skippable exception

In Spring Batch, an exception raised while reading, processing, or writing an item normally causes the chunk to fail and can stop the Step. However, some errors only pertain to an individual record, such as a malformed CSV line or data failing a business rule. If business requirements permit skipping that record and continuing to process the remaining records, you can configure a **skippable exception**.

A skippable exception is an exception type that the Step's skip policy allows to be bypassed once the error is detected. Spring Batch records the number of skipped items or errors, continues processing according to the configured policy, and invokes SkipListener when an error is actually accepted for skipping.

Do not treat skip as a way to hide all errors. Only skip errors that can be bypassed without compromising target data consistency. Infrastructure, configuration, or programming errors generally need to fail the Step or be retried under a dedicated policy.

## 1. What is a skippable exception?

In a chunk-oriented Step, data passes through three main stages:

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Commit chunk
~~~

Exceptions can arise at any stage:

- **Read:** source data cannot be parsed or converted into an item.
- **Process:** an item violates business rules or cannot be transformed.
- **Write:** data cannot be written to the target, such as a constraint violation or per-record error.

If the exception is skippable and the Step is still within its skip limit, Spring Batch can skip the corresponding error and continue processing. Non-skippable exceptions, or errors exceeding the limit, cause the Step to fail unless another handling mechanism applies.

For example, an order-file import Job has 100,000 lines. A few lines have negative quantities or malformed dates. If business rules allow placing those lines into a rejected list and continuing to import valid lines, you can skip the defined data exceptions.

~~~text
Line 1: valid           -> process
Line 2: valid           -> process
Line 3: invalid format  -> SKIP
Line 4: valid           -> process
Line 5: missing orderId -> SKIP
Line 6: valid           -> process
~~~

Skip does not mean the exception never happened. Spring Batch still tracks skip counts and can invoke listeners so the application logs rejection reasons.

## 2. Configuring skippable exceptions

With Spring Batch 5, you can configure skippable exceptions on a fault-tolerant chunk Step using skip and skipLimit:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
~~~

In this example:

- The Step runs in chunks of 100 items.
- FlatFileParseException is allowed to be skipped when the reader cannot parse a file line.
- InvalidOrderException is allowed to be skipped when the processor detects an invalid record.
- Total skipped errors in the Step are limited to 50.

You must call faultTolerant() before retry/skip configurations. Without a skip policy, a Step does not skip business exceptions by default. When an exception is not classified as skippable, the Step fails under the framework's error handling.

Choose skippable exceptions specifically. Avoid broadly configuring skip for Exception.class or RuntimeException.class because it can bypass connection errors, programming bugs, or system errors.

## 3. Meaning of skipLimit

skipLimit specifies the maximum number of errors allowed to be skipped in a Step. This limit applies cumulatively across read, process, and write errors, not as a separate quota per exception type.

Example:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skipLimit(10)
~~~

The Step can continue after up to 10 skips belonging to the declared exception types. When a subsequent skippable error pushes the total over the limit, the Step fails.

| Recorded skip errors | Result |
| ---: | --- |
| 0 to 9 | Within limit |
| 10 | Limit exhausted |
| Next skippable error | Limit exceeded, Step fails |

Therefore, skipLimit(10) does not mean the Step skips indefinitely after skipping 10 errors. The 11th skippable error causes the Step to fail.

### Choosing a limit based on data requirements

Do not pick a skip limit just so the Job always reaches the end of the file. Consider:

- Acceptable data error rate.
- Expected total record count.
- Severity of each error type.
- Ability to reconcile and fix rejected data.
- Output data quality requirements.

For a 1,000,000-line file, a 50-error limit means something very different from a 100-line file. You may need to combine an absolute limit with an error-rate check in a post-import aggregation step.

## 4. Distinguishing skip and noSkip

skip declares an exception or exception group allowed to be bypassed. noSkip declares exceptions that must not be skipped, even if they fall under a broader group configured for skip.

Example:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(Exception.class)
        .noSkip(IllegalStateException.class)
        .skipLimit(100)
        .build();
~~~

This example illustrates excluding an exception from a skippable group. In real applications, avoid using skip(Exception.class) unless there is a very specific reason and dangerous exceptions are thoroughly classified. Broad configurations make policies unpredictable and easily hide errors.

A clearer design is declaring only specific data error types:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.noSkip(DatabaseUnavailableException.class)
.skipLimit(50)
~~~

When combining skip and noSkip, consider inheritance relationships between exceptions. A subclass exception may be classified differently from its superclass. Test the actual exception classes thrown by the reader, processor, and writer to ensure the policy produces the intended outcome.

## 5. Where are exceptions classified?

Skip policy applies to exceptions arising across the stages of chunk processing. Each stage provides different context:

| Stage | Example exception | Is there an item to record? |
| --- | --- | --- |
| Read | FlatFileParseException | No successfully parsed item may exist; exception may hold the source line |
| Process | InvalidOrderException | Parsed OrderInput is available |
| Write | DataIntegrityViolationException | Output item or group of items being written is available |

### Errors in ItemReader

A reader can throw FlatFileParseException when a CSV line is malformed. Spring Batch can skip the exception if configured and if the reader can continue reading after the bad line.

Example:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
~~~

For file readers, check whether the exception includes the input line and line number. That information helps persist a rejected record even though an OrderInput object was not created.

### Errors in ItemProcessor

Processors typically detect business errors on a read item:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.getQuantity() == null || input.getQuantity() <= 0) {
            throw new InvalidOrderException(
                    "Quantity must be greater than zero");
        }

        return transform(input);
    }
}
~~~

If InvalidOrderException is declared skippable, that item can be skipped and other items continue processing under Step policy.

### Errors in ItemWriter

A writer can throw exceptions when persisting data, such as constraint violations. However, write skips are more complicated because a writer usually receives an entire chunk rather than a single item.

Spring Batch may need to roll back the chunk and isolate the failing item through fault-tolerant handling. This depends on whether the writer can be safely re-invoked, transaction behavior, and how the exception is thrown. Do not assume a writer exception always affects only a single item.

If a writer persists multiple items in a batch statement, the database may report a failure for the entire batch. Test failing-item isolation, rollback, and retry/skip with the exact writer and database in use.

## 6. SkipListener records skipped items

When an exception is actually skipped, SkipListener allows the application to record the item or exception along with the reason:

~~~java
public interface SkipListener<I, O> {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
~~~

The three callbacks correspond to read, process, and write failures.

Example listener recording order processing failures:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository rejectedRepository;

    public OrderSkipListener(
            RejectedOrderRepository rejectedRepository) {
        this.rejectedRepository = rejectedRepository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        rejectedRepository.save(
                RejectedOrder.fromReadFailure(t));
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        rejectedRepository.save(
                RejectedOrder.fromInput(item, t.getMessage()));
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        rejectedRepository.save(
                RejectedOrder.fromOrder(item, t.getMessage()));
    }
}
~~~

Registering the listener on the Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
~~~

SkipListener differs from ItemReadListener or ItemProcessListener. Read/process listeners observe an error as it happens; SkipListener is invoked when the framework determines that the error has been skipped. Therefore, SkipListener is more appropriate for recording the list of records excluded from the final result.

### Information to store

A rejected record typically needs:

- JobInstance or JobExecution ID to trace the run.
- Step name and failure stage.
- Business key if already read.
- Source line number or position if available.
- Exception type or stable error code.
- Sanitized error message.
- Timestamp and input version.

Do not rely solely on free-form message text as a classification key because message wording can change across versions. Use a stable error code when statistics and reconciliation are required.

If rejected records are written to the same database and transaction manager as the Step, the save operation can participate in the corresponding transaction. If written to another database or external system, do not assume it commits with the chunk. Design transactions and idempotency explicitly.

## 7. Skip vs. filter

Both skip and filter can prevent an item from reaching the writer, but their semantics differ:

| Mechanism | How it works | Meaning |
| --- | --- | --- |
| Skip | Exception allowed to be bypassed by policy | Failing item or operation can be excluded from processing |
| Filter | Processor returns null | Item is excluded under normal processing conditions |

Examples:

- An order has status CANCELLED and reporting rules exclude cancelled orders: the processor can return null to filter.
- A CSV line lacks delimiters preventing parsing: the reader throws FlatFileParseException and the Step can skip if policy allows.
- An order has negative quantity: the processor throws InvalidOrderException to skip and record as rejected.

Filter count and skip count are distinct counters in StepExecution. Do not use filtering to conceal data errors that must be audited.

## 8. Skip vs. retry

Retry and skip serve two different scenarios:

- **Retry:** re-attempt an operation that failed due to a potentially transient or recoverable error.
- **Skip:** bypass an error defined as acceptable to skip by business rules.

Examples:

| Situation | Usually appropriate handling |
| --- | --- |
| Malformed file line | Skip if rejection details can be saved and processing can continue |
| Negative order quantity | Skip or fail per data quality rules |
| Temporary database disconnection | Bounded retry or fail |
| Missing index making queries slow | Investigate and optimize; retry does not fix root cause |
| NullPointerException due to bug | Fail and fix code |

Spring Batch supports configuring both retry and skip on the same Step. When an exception matches both policies, the order and outcome depend on fault-tolerant configuration and retry limit. A common strategy is retrying transient errors first, then considering skip after attempts are exhausted if business rules permit. Test the exact exception classification and behavior of the Spring Batch version in use.

Example:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(50)
~~~

In this configuration, transient data-access errors can be retried up to the retry policy limit; InvalidOrderException data errors are handled by the skip policy. Do not put the same exception in both policies without clarifying the intent and desired behavior.

## 9. Skip and transaction rollback

Chunk processing usually runs inside a transaction. When an exception occurs, the transaction may roll back depending on exception type and rollback policy. In a fault-tolerant Step, the framework coordinates retry/skip to decide whether to continue or fail.

Points to understand:

- Exceptions in the processor can trigger chunk rollback before the framework processes the skip.
- Exceptions in the writer can roll back the entire chunk.
- The framework may re-invoke the reader, processor, or writer while isolating the failing item.
- Writers and processors must be safe under re-invocation when retry/skip can occur.
- Side effects outside the database transaction may not roll back.

For instance, if a writer sends an HTTP request per item and throws an exception on the last item, rolling back the database transaction cannot undo requests already sent. When the framework retries or skips, earlier requests may be sent again.

Therefore, avoid placing non-idempotent side effects inside processors/writers if retry/skip can re-invoke them. Use idempotency keys, outbox patterns, or separate side effects into another processing step.

## 10. How can a read skip continue reading?

Not every reader can continue after an exception. With file readers, a parse error is usually tied to a specific line and the reader can advance to the next line depending on implementation.

With custom readers, if an exception occurs before read state is updated, the next call may read the same item again and repeat the failure. A reader needs clear rules for advancing position after a skippable error.

If a reader queries an API or remote stream, determine:

- Does the exception occur before or after the source has consumed the item?
- Can the same item be re-read via offset or cursor?
- Can a bad message be skipped and the next message consumed?
- Is the checkpoint updated consistently when an error is skipped?

Do not declare an exception as skippable for a reader that cannot continue safely. If the source does not support recovery after an error, the Step may need to fail to prevent dropping data.

## 11. Write skip and isolating the failing item

Writers typically receive a chunk rather than individual items. When a batch insert fails, the database may return only a generic error for the whole batch or constraint information insufficient to pinpoint a specific item.

Spring Batch has fault-tolerant handling for write exceptions and may retry writing item-by-item in certain scenarios to isolate the failing item. However, this increases writer invocations and requires the writer to be safely re-invocable.

Example custom writer:

~~~java
public class OrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        repository.saveAll(chunk.getItems());
    }
}
~~~

If saveAll fails because one record violates a unique constraint, the framework may need to re-evaluate items to pinpoint the error. How the writer and repository execute batch inserts affects failing-item isolation.

If a writer cannot be re-invoked safely, or has external side effects outside the database, redesign it before enabling write skips. You can use a staging table, validate data before writing, or structure writes so errors can be isolated.

## 12. Custom skip policy

When exception classification cannot be expressed concisely via skip/noSkip, you can use a custom SkipPolicy. The policy receives the exception and current skip count, then decides whether skipping is permitted.

~~~java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException;
}
~~~

Simple policy example:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private final long skipLimit;

    public OrderSkipPolicy(long skipLimit) {
        this.skipLimit = skipLimit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        if (throwable instanceof InvalidOrderException) {
            if (skipCount < skipLimit) {
                return true;
            }
            throw new SkipLimitExceededException(
                    "Order skip limit exceeded",
                    throwable);
        }

        return false;
    }
}
~~~

Registering the custom policy:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy(50))
        .build();
~~~

The example above illustrates deciding skips based on exception type and current skip count. In practice, the policy must unwrap exception causes or wrappers matching real reader/writer exceptions, while avoiding throwing SkipLimitExceededException for errors outside the skippable group.

Only use a custom SkipPolicy when rules involve complex conditions, such as limits by tenant, file type, or error rate. For simple rules, skip and noSkip configurations are usually easier to read and maintain.

## 13. Monitoring skip counts and Step results

StepExecution stores counters that help track errors:

- readSkipCount: number of errors skipped while reading.
- processSkipCount: number of errors skipped while processing.
- writeSkipCount: number of errors skipped while writing.
- skipCount: total skips in the Step.
- readCount, process count, filterCount, and writeCount: counters at other stages.

Observable via StepExecution:

~~~java
@Component
public class SkipSummaryListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {} skips: read={}, process={}, write={}, total={}",
                stepExecution.getStepName(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount());

        return null;
    }
}
~~~

Returning null preserves the current ExitStatus. The listener only observes and records metrics; do not force the Step status to COMPLETED when skip counts are high without business confirmation that the result is acceptable.

A Step can finish COMPLETED even with skips, provided all errors fall within policy and limits. That does not automatically mean output data meets quality standards. The application may need a summary step to verify rejection rates and decide whether the Job may publish outputs.

## 14. Testing skippable exceptions

Test both skippable and non-skippable exception cases:

1. A skippable parse error occurs in the reader.
2. An InvalidOrderException occurs in the processor.
3. An undeclared exception causes the Step to fail.
4. Skip count equals the exact limit.
5. The next skippable error fails the Step for exceeding the limit.
6. SkipListener invokes the right callback.
7. Rejected records are stored with enough detail for reconciliation.
8. Restart creates no duplicate data and does not miss checkpoints.

Example Step test with data errors:

~~~java
@Test
void skipsInvalidOrderAndWritesValidOrders() throws Exception {
    // Reader returns a valid item, an item causing InvalidOrderException,
    // and then another valid item.
    // Step is configured to skip InvalidOrderException.

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "importOrdersStep",
            new JobParametersBuilder()
                    .addString("inputId", "test-file-01", true)
                    .toJobParameters());

    StepExecution stepExecution =
            execution.getStepExecutions().iterator().next();

    assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
    assertEquals(1, stepExecution.getProcessSkipCount());
    assertEquals(2, stepExecution.getWriteCount());
}
~~~

This is an illustrative skeleton; configure test reader, processor, writer, and Job appropriately for your application. Verify both target data contents and the rejected store, not just BatchStatus.

## 15. Common mistakes

### Skipping all exceptions

Skipping Exception.class or RuntimeException.class can hide database errors, configuration issues, and bugs. Declare only exception types skippable per business rules.

### Omitting skipLimit

Without an error bound, input data could fail en masse while the Job keeps going. Use an appropriate limit and check error rates.

### Confusing skip with filter

Filter is the normal outcome of a processor returning null. Skip handles an exception permitted to be bypassed by policy. Use the right semantics for accurate metrics.

### Assuming onReadError means already skipped

Read error callbacks only observe exceptions. Use SkipListener to record exceptions that were actually skipped.

### Skipping writer errors without checking safety

A writer may perform partial writes or external side effects outside the transaction. Test rollback and re-invocation before enabling write skips.

### Skipping infrastructure errors

Database unavailability or network timeouts are usually not bad data on one item. Bounded retry or failing is generally more suitable.

### Failing to store rejected records

The Job may finish COMPLETED while failing records vanish without trace. Use SkipListener or a quarantine mechanism to store reasons and sources.

### Setting skip limit too high

A large limit can let the Job complete with severely incomplete output data. Base thresholds on data quality requirements.

### Ignoring interactions between retry and skip

One exception can be affected by both policies. Clarify which errors retry first, which skip after retries exhaust, and test actual behavior.

## 16. Workflow for designing a skip policy

When configuring skip for a Step, follow these steps:

1. List exceptions that can arise in read, process, and write.
2. Separate skippable data errors from system errors that must stop or retry.
3. Choose specific exception classes for skip.
4. Use noSkip to exclude critical errors if needed.
5. Choose skipLimit based on acceptable business error counts and rates.
6. Register SkipListener to persist rejection info and failure stage.
7. Verify the writer can roll back and be re-invoked safely.
8. Define how exceeding the skip limit is handled.
9. Monitor read/process/write skip counts and rejection rates.
10. Test retry, skip, rollback, and restart with representative data.

A good skip policy explains why that error type can be skipped, where skipped records are stored, and what the system does when errors exceed the threshold.

## Conclusion

A skippable exception is an exception that a fault-tolerant Step allows to be bypassed under a configured policy. Use skip and skipLimit to control data errors in read, process, or write; use noSkip to exclude errors that must fail the Step; and use SkipListener to record failed records along with skip reasons. Distinguish skip from filter and retry, bound acceptable error counts, and ensure writers, transactions, and side effects remain safe when the framework rolls back or re-invokes operations.
