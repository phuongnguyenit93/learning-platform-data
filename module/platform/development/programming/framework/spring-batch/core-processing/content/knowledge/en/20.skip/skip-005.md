# Skip in read, process, and write

In Spring Batch, **skip** allows a Step to bypass an unprocessable item according to a configured policy and continue with the remaining items. Skip can occur in all three stages of the chunk pipeline:

- **Read skip**: the reader throws an exception while fetching or parsing source data.
- **Process skip**: the processor throws an exception while transforming or validating an item.
- **Write skip**: the writer throws an exception while writing one or more items of the chunk.

All three cases increment the Step's skip count, but the available information and how the framework isolates the failing item differ. Read skip may not have produced an input object; process skip has the input item; write skip has the output item that the writer could not write.

Skip is a controlled business decision. It does not mean every exception is ignored. You must choose the right exception types, limit the total number of skipped items, record failing data, and ensure skipping does not distort business results.

## 1. Where does skip sit in the chunk pipeline?

A chunk-oriented Step performs three main stages:

~~~text
Data source
     |
     v
  ItemReader
     |
     |  Read skip if reader throws an error
     v
 ItemProcessor
     |
     |  Process skip if processor throws an error
     v
  ItemWriter
     |
     |  Write skip if writer cannot write an item
     v
 Commit chunk
~~~

Example importing 100 orders:

- The reader encounters one malformed CSV line.
- The processor detects two orders missing a required ID.
- The writer cannot write one order violating a constraint.

If those exceptions are configured as skippable and the skip limit has not been exceeded, the Step can skip the corresponding items and continue processing.

Each skip type has its own callback in SkipListener:

| Stage | Callback | Data received by callback |
|---|---|---|
| Read | onSkipInRead | Exception, usually without a constructed item |
| Process | onSkipInProcess | Input item and exception |
| Write | onSkipInWrite | Output item and exception |

Do not confuse skip with filter. The processor returning null is filtering an item by business logic; the processor throwing an exception classified as skippable is a process skip.

## 2. Basic skip configuration for a Step

Spring Batch configures skip through a fault-tolerant chunk Step:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        OrderSkipListener skipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .listener(skipListener)
            .build();
}
~~~

In this example:

- The Step processes up to 100 items per chunk.
- File parse errors and business InvalidOrderException errors are allowed to be skipped.
- The total number of skipped items in the Step cannot exceed 50.
- OrderSkipListener records the excluded items.

Declare specific exceptions matching the error sources. Avoid broadly skipping Exception.class or RuntimeException.class because that can swallow programming bugs, configuration mistakes, and critical infrastructure errors.

Without a skip configuration, an unhandled exception fails the Step by default according to the rollback policy. Skip configuration must explicitly state which error types business rules agree to discard.

## 3. Read skip: errors occurring in ItemReader

Read skip occurs when the ItemReader throws an exception while fetching an item. Examples:

- A CSV line has too few columns.
- A numeric field cannot be converted to the target type.
- A source record has an invalid format.
- An isolated read error defined as skippable.

Example FlatFileItemReader parsing a CSV line:

~~~text
id,orderNumber,amount
1,ORD-001,100.00
2,ORD-002,not-a-number
3,ORD-003,250.00
~~~

If the reader converts amount to a numeric type and the second line raises FlatFileParseException, the Step can skip that line and continue reading the third line if the exception is configured as skippable.

Configuration:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
~~~

Read skip is special because the reader may not have built an input object. Therefore SkipListener.onSkipInRead receives only the exception, not an item.

### Do not use null to represent a bad line

In Spring Batch, a reader returning null means **end of data**. If a reader returns null itself upon hitting a malformed line, the Step may stop reading early and lose all subsequent lines.

Throw an appropriate exception when a record cannot be read and let the skip policy decide whether to bypass it. Only return null when genuinely reaching EOF.

## 4. Obtaining error line details in read skip

With FlatFileItemReader, FlatFileParseException typically carries useful details:

- Line number: the line sequence number.
- Input: the raw line content that caused the error.
- Cause: the underlying exception during parsing or conversion.

Example listener:

~~~java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedRecordRepository rejectedRepository;

    public OrderSkipListener(
            RejectedRecordRepository rejectedRepository) {
        this.rejectedRepository = rejectedRepository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        if (exception instanceof FlatFileParseException parseException) {
            rejectedRepository.save(
                    RejectedRecord.from(
                            parseException.getLineNumber(),
                            parseException.getInput(),
                            parseException.getMessage()));
        }
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        // Handled in the process skip section.
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        // Handled in the write skip section.
    }
}
~~~

This snippet illustrates saving the line number and original content. In real applications, consider security for sensitive input data, bound the stored content length, and avoid persisting the raw payload unless needed.

If a custom reader throws a custom exception, attach the source location or record key so the failing item can be traced. Do not store only a generic message like "read failed".

## 5. Process skip: errors occurring in ItemProcessor

Process skip occurs when the processor receives an input item and throws an exception during validation or transformation.

Example processor validating an order:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderNumber() == null
                || input.orderNumber().isBlank()) {
            throw new InvalidOrderException(
                    "Order number is required");
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Amount must be positive");
        }

        return new Order(
                input.id(),
                input.orderNumber(),
                input.amount());
    }
}
~~~

If InvalidOrderException is configured as skippable, that item is not passed to the writer. Other valid items can still be written.

Corresponding callback:

~~~java
@Override
public void onSkipInProcess(
        OrderInput item,
        Throwable exception) {

    rejectedOrderRepository.save(
            RejectedOrder.from(
                    item.id(),
                    item.orderNumber(),
                    exception.getMessage()));
}
~~~

Process skip is usually easier to record than read skip because the input object already exists. You can save the business key, key fields, and rejection reason for later correction or reprocessing.

### Distinguishing process skip from filter

A processor has two ways to finish without producing output:

~~~java
@Override
public Order process(OrderInput input) {
    if (input.isCancelled()) {
        return null; // Filter: excluded per business rules.
    }

    if (input.orderNumber() == null) {
        throw new InvalidOrderException("Missing order number");
    }

    return convert(input);
}
~~~

The two cases have different meanings:

| Behavior | Meaning | Counter |
|---|---|---|
| Returns null | Intentional item filter | filterCount increments |
| Throws skippable exception | Skip failing item | processSkipCount increments |
| Throws non-skippable exception | Step cannot continue per policy | Step fails |

Do not throw an exception just to filter an item. Conversely, do not return null to hide invalid data when rejection statistics and reasons must be recorded.

## 6. Write skip: errors occurring in ItemWriter

Write skip occurs when the writer fails to write one or more items. This is the most complex case because the writer usually receives an entire chunk rather than individual items.

Example writer persisting orders to a database where one item violates a unique constraint:

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

If one item causes the batch write to fail and the exception is skippable, Spring Batch can roll back the chunk write and execute the failing-item isolation process. Depending on configuration and writer type, the framework may invoke the writer again with subsets or single items to isolate the error.

Illustrative diagram:

~~~text
Writer receives [A, B, C, D]
          |
          v
Whole-chunk write fails
          |
          v
Framework isolates failing item
          |
          +--> A succeeds
          +--> B fails -> skip
          +--> C succeeds
          +--> D succeeds
~~~

This is a conceptual model. Not every writer or every batch error can be safely split down to individual items. If a writer receives only a generic error from an external system without identifying the failing item, item-level skip may be unsuitable.

### The writer may be invoked multiple times

During write-skip handling, the writer can be called again with different subsets of items. Therefore:

- Do not assume write() runs only once per chunk.
- The writer should participate in a transaction or be idempotent.
- Avoid sending emails, creating shipments, or calling non-idempotent APIs directly in the writer.
- If the failing item cannot be isolated, fail or use a separate reconciliation process.

## 7. SkipListener for all three stages

SkipListener provides three callbacks:

~~~java
public interface SkipListener<I, O> {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
~~~

Full listener example:

~~~java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderRepository repository;

    public OrderSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable exception) {
        repository.save(
                RejectedOrder.readFailure(
                        exception.getMessage()));
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        repository.save(
                RejectedOrder.processFailure(
                        item.id(),
                        exception.getMessage()));
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        repository.save(
                RejectedOrder.writeFailure(
                        item.id(),
                        exception.getMessage()));
    }
}
~~~

The listener can record:

- The stage where the error occurred: READ, PROCESS, or WRITE.
- The item's business key if available.
- Exception type and message.
- Source file, line number, or partition.
- Timestamp and associated JobExecution/StepExecution.

Do not store full stack traces or large payloads in the rejected table unless necessary. You can store the exception class, a normalized message, and a correlation ID to detailed logs.

### Timing of SkipListener invocation

Spring Batch invokes SkipListener just before the chunk transaction commits so the listener can use transactional resources. This is useful when the listener saves rejected records to the same database and wants error records committed alongside the chunk.

If the chunk rolls back before committing, saving a rejected record participating in that transaction may also roll back. Do not emit side effects to external systems from SkipListener assuming a database rollback will revoke the side effect.

## 8. skipLimit applies to total skips

skipLimit bounds the total number of items allowed to be skipped in the Step, summed across read, process, and write. It is not three independent limits.

Example:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(DuplicateOrderException.class)
.skipLimit(10)
~~~

Suppose the Step has:

| Stage | Items skipped |
|---|---:|
| Read | 2 |
| Process | 5 |
| Write | 3 |
| Total | 10 |

With skipLimit equal to 10, the Step can accept 10 skipped items in total. The next skipped item exceeds the limit and causes the Step to fail.

This means you must monitor total skips rather than looking at a single error category. A file with 4 parse errors, 4 validation errors, and 3 write errors exceeds a limit of 10 even though no single category exceeds 10.

If you need different limits per error category, you can build a custom SkipPolicy. Even then, keep an overall cap or clear stop policy to protect the Job from mass corrupt data.

## 9. Which exceptions should be skipped?

A skip policy should separate per-item data errors from system errors.

| Error type | Common handling approach |
|---|---|
| CSV missing columns or wrong type | Read skip if individual lines can be discarded |
| Missing business key | Process skip or fail per business rules |
| Business value out of allowed range | Process skip if a rejection workflow exists |
| Duplicate key from input record | Write skip if business rules permit |
| Database connection loss | Bounded retry or fail |
| Database out of disk space | Fail and fix infrastructure |
| Invalid SQL or schema mismatch | Fail |
| Programming bug in processor | Fail, do not skip broadly |

Example allowing only specific exceptions to be skipped:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(DuplicateOrderException.class)
.noSkip(FatalImportException.class)
.skipLimit(50)
~~~

Choose the actual exception types thrown by the reader, processor, or writer. If an exception is wrapped inside another exception, check the cause and skip classifier against the exact exception types the framework sees.

Avoid configuring skip for Exception.class. Doing so can treat a NullPointerException or configuration error as bad data and let the Job continue.

## 10. Using a custom SkipPolicy

When skip rules depend on multiple conditions, you can use a SkipPolicy instead of declaring a simple class list.

Example policy capping total errors and permitting only specific data errors:

~~~java
public class OrderSkipPolicy implements SkipPolicy {

    private static final int LIMIT = 50;

    @Override
    public boolean shouldSkip(
            Throwable exception,
            long skipCount) throws SkipLimitExceededException {

        if (skipCount >= LIMIT) {
            throw new SkipLimitExceededException(
                    LIMIT, exception);
        }

        Throwable cause = exception;

        while (cause.getCause() != null && cause.getCause() != cause) {
            cause = cause.getCause();
        }

        return cause instanceof InvalidOrderException
                || cause instanceof FlatFileParseException;
    }
}
~~~

Registering the policy:

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy())
        .listener(skipListener)
        .build();
~~~

This example illustrates classifying by root cause. In real applications, decide explicitly how to unwrap exceptions; the deepest cause is not always the type to classify. Sometimes a wrapper exception carries more important semantics than its inner cause.

Do not configure multiple skip policies simultaneously with unclear precedence. When using a custom SkipPolicy, let that policy be the primary decision source and test representative exceptions.

## 11. Combining retry with skip

An error may be both retryable and skippable. For example, the writer encounters a temporary connection issue; the application retries a few times, and if it still fails and business rules permit discarding the item, it skips.

~~~java
new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
~~~

Retry and skip have different goals:

- Retry tries to complete the same operation.
- Skip agrees to discard the item.
- Once retries hit their limit, skipping is only possible if the exception is allowed by the skip policy.
- If the exception is not skippable, the Step fails.

Do not configure a broad infrastructure error as both retryable and skippable just so the Job always finishes. A database outage is not a single bad item to discard; the Step must stop to prevent data loss.

## 12. Rollback and skip at each stage

When a skippable exception occurs, the framework may roll back the current transaction and then continue through the fault-tolerant workflow. Details depend on the stage and the reader/writer types.

### Read skip

The reader throws an exception when parsing a line. The framework classifies the error, rolls back if needed, records the skip, and continues reading. With file readers, line position and restartability must be managed properly to avoid duplicating or dropping lines.

### Process skip

The processor throws an exception for an item. That item is not passed to the writer. Other items in the chunk can continue processing once the framework completes the skip flow.

### Write skip

The writer throws an exception for the chunk. The framework may roll back the write, then isolate the failing item by retrying the writer with subsets. The failing item is skipped, and writable items can be persisted in an appropriate transaction.

Remember that a chunk rollback does not mean the whole Job resets to the beginning. Previously committed chunks remain intact. If the Step fails because the skip limit is exceeded, the Job can restart from the last saved checkpoint.

## 13. Side effects and idempotency when skipping

The writer may be called multiple times during retries or while isolating the failing item for a write skip. If the writer sends requests to an external API, a request that already succeeded could be sent again when the chunk rolls back or the framework retries.

Unsafe example:

~~~java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        shippingClient.createShipment(order);
    }
}
~~~

If the shipment creation API succeeds for the first item but the next item fails, the retry may create a second shipment for the same order.

Safeguards:

- Use a stable idempotency key derived from the order ID.
- Write shipment creation requests to an outbox table in the same database transaction.
- Have a dedicated worker read the outbox and send requests.
- Store the external request ID for reconciliation.
- Avoid side effects in the writer that cannot be safely repeated.

Skip does not guarantee that an item's side effects were undone. If an item is skipped after an external system already received a request, a separate compensation or reconciliation mechanism is needed.

## 14. Inspecting results with StepExecution counters

Spring Batch provides per-stage counters:

| Counter | Meaning |
|---|---|
| readSkipCount | Number of items skipped during reading |
| processSkipCount | Number of items skipped during processing |
| writeSkipCount | Number of items skipped during writing |
| filterCount | Number of items intentionally filtered by the processor returning null |
| readCount | Number of items successfully read per Step statistics |
| writeCount | Number of items written per Step statistics |
| rollbackCount | Number of rollbacks recorded |

Counters can be read after the Step completes:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    long readSkips = stepExecution.getReadSkipCount();
    long processSkips = stepExecution.getProcessSkipCount();
    long writeSkips = stepExecution.getWriteSkipCount();

    long totalSkips = readSkips + processSkips + writeSkips;

    log.info(
            "Skip summary: read={}, process={}, write={}, total={}",
            readSkips,
            processSkips,
            writeSkips,
            totalSkips);

    return stepExecution.getExitStatus();
}
~~~

Counters help distinguish whether errors concentrate in the read source, processing rules, or write target. For example, a spike in readSkipCount may show a source file schema mismatch; rising writeSkipCount may indicate constraint or target database issues.

Do not rely solely on total skip count. Record the exception type and business key to pinpoint specific causes.

## 15. Testing read skip

A read skip test should create a source containing an invalid line among valid lines, then verify the reader continues reading subsequent lines.

Sample data:

~~~csv
id,orderNumber,amount
1,ORD-001,100.00
2,ORD-002,not-a-number
3,ORD-003,250.00
~~~

Required assertions:

- Item 1 is read and written.
- Line 2 is skipped due to the parse exception.
- Item 3 is still read and written.
- readSkipCount equals 1.
- SkipListener receives FlatFileParseException and the corresponding line number.
- The Step completes if the skip limit has not been exceeded.

Also test a missing file. A missing file is typically a Step/Job-level resource error and should not automatically be treated as a skippable data line.

## 16. Testing process skip

Create a processor that throws InvalidOrderException for a specific business key.

Example input:

~~~text
ORD-001 -> valid
ORD-002 -> missing order number
ORD-003 -> valid
~~~

Verify:

- The processor is called for each item in the processing flow.
- The failing item is not sent to the writer.
- The two valid items are written.
- processSkipCount equals 1.
- filterCount does not increase because the item was excluded via exception, not by returning null.
- SkipListener.onSkipInProcess receives the exact item and exception.

If the processor calls an external service, the test should verify that retry or skip does not produce duplicate side effects.

## 17. Testing write skip

Write skip needs testing with a writer capable of isolating failing items and a real database transaction.

Example:

- Writer receives A, B, C.
- B violates a unique constraint.
- The framework rolls back the chunk write.
- The framework isolates B as the failing item via its fault-tolerant mechanism.
- A and C are written if policy permits.
- writeSkipCount equals 1.
- SkipListener.onSkipInWrite receives B.

Do not just mock the writer and invoke the listener directly; that does not verify the Step's fault-tolerant behavior. Use a Step integration test with a dedicated test database, a real writer, or a test double with equivalent transaction behavior.

If the writer writes to an external API or plain file, tests must check side effects that occurred before rollback and ensure idempotency or cleanup.

## 18. Testing skip limit

With skipLimit equal to 2, test at least three cases:

| Skipped items | Expected outcome |
|---:|---|
| 0 | Step can complete |
| 2 | Step can complete if other conditions succeed |
| 3 | Step fails due to exceeding limit |

Also test when skips are distributed across stages. For example, 1 read skip and 1 process skip already exhaust the limit of 2; a subsequent write skip must fail the Step.

When the limit is exceeded, the current chunk's transaction may roll back per the error-handling policy. Previously committed chunks remain intact.

## 19. Common mistakes

### Returning null when a reader hits a bad line

null signals EOF. Returning null early can drop all remaining data. Throw a skippable exception for malformed records.

### Treating filter as skip

A processor returning null increments filterCount, not processSkipCount. Use an exception when a failing item must be recorded.

### Using skip Exception.class

This can hide bugs and infrastructure errors. Only skip specific exceptions permitted by business rules.

### Thinking skipLimit applies separately to each stage

skipLimit is the Step's total read/process/write skip limit. Track individual counters as well as the total.

### Assuming write skip invokes the writer only once

The framework may re-invoke the writer to isolate the failing item. The writer must be transactional or idempotent.

### Not recording skipped items

Failing data cannot be investigated, fixed, or rerun. Use SkipListener and persist the business key along with the cause.

### Skipping broad database errors

A database outage or full disk is not an isolated item error. Use bounded retry or fail the Step.

### Emitting side effects inside SkipListener

Database writes can participate in the transaction, but emails/APIs do not roll back automatically. Use an outbox or idempotency for external effects.

## 20. Workflow for designing skip in a Step

When implementing skip, identify:

1. Which exceptions can occur in read, process, and write.
2. Which exception types are truly permitted to be skipped by business rules.
3. Whether the reader throws exceptions properly instead of mistakenly returning null on bad data.
4. Whether process skip can store the input item and business key.
5. Whether write skip can accurately isolate the failing item.
6. Whether the writer is safe under re-invocation.
7. Whether the total skipLimit matches the data scale and acceptable variance.
8. Whether SkipListener stores the stage, cause, and source location.
9. Whether rejected-record writes participate in the intended transaction.
10. Whether side effects outside the transaction have idempotency or an outbox.
11. Whether readSkipCount, processSkipCount, and writeSkipCount metrics are monitored.
12. Whether integration tests cover each stage and exceeding the skip limit.

Read skip handles errors when fetching data, process skip handles errors when transforming items, and write skip handles items that cannot be written to the target. All three consume the Step's single skip limit while providing different information for recovery and investigation. By selecting narrow exceptions, recording complete error entries, bounding total skips, and protecting the writer from duplicate side effects, the Step can proceed with valid data while maintaining control over input quality.
