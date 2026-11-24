# Chunk Rollback When Processor Throws an Exception

In Spring Batch, a chunk-oriented step processes data in groups of items. A chunk typically consists of read, transform, and write operations; changes belonging to the chunk's transaction are committed when the chunk completes. If `ItemProcessor` throws an exception while processing an item, the exception propagates out of the pipeline and the current chunk's transaction is typically rolled back.

Rollback protects chunk consistency: uncommitted database changes in that transaction are not retained. The writer has typically not been called for this chunk because item processing stopped before the write phase. Previously committed chunks remain intact; the current chunk's transaction does not span the entire job.

What happens next depends on the fault-tolerance configuration. If the exception is not configured for retry or skip, the step fails. If the exception is configured for retry, Spring Batch can retry the processing operation. If the exception is skippable and `skipLimit` has not been exceeded, the failing item can be excluded from the output so valid items continue to be written. In any branch, it is essential to understand the transaction boundary, processor side effects, and reader checkpoints to avoid duplicate writes or data loss.

## How Does a Chunk Transaction Work?

With chunk-oriented processing, Spring Batch coordinates `ItemReader`, `ItemProcessor`, and `ItemWriter` within one transaction per chunk. For example, `chunk(3, transactionManager)` groups up to three input items for a single processing/commit unit.

```text
Start chunk transaction
             |
             v
       ItemReader.read()
             |
             v
    ItemProcessor.process()
       |       |       |
       v       v       v
      O1      O2      O3
             |
             v
       ItemWriter.write()
             |
             v
    Update checkpoint/metadata
             |
             v
           COMMIT
```

In the success case, output is written by the writer and the transaction commits. If an operation within the chunk throws an exception before commit, the transaction is handled according to the step's rollback rules and transaction manager.

`ItemProcessor<I, O>` processes one item at a time. The processor can return an output, return `null` to filter the item, or throw an exception if it cannot process it. Returning `null` is not an error and does not trigger a rollback on its own; only an exception enters the error-handling path.

## What Happens When the Processor Throws an Exception?

Suppose the chunk size is 3 and the reader supplies three orders. The processor processes the first two items successfully but throws `InvalidOrderException` on the third item.

```text
Current chunk: [Order-1, Order-2, Order-3]

Reader       Processor                 Writer
  |              |                       |
  |-- Order-1 -->|-- Order-1'            |
  |-- Order-2 -->|-- Order-2'            |
  |-- Order-3 -->|                       |
  |              |-- throw exception     |
  |              |                       |
  |              X  pipeline stops       |
                 |
                 v
        Rollback transaction
```

With the default configuration where that exception is not skipped or retried:

1. The processor throws an exception when processing the failing item.
2. The exception escapes chunk processing.
3. Spring Batch terminates the current chunk execution along the error path.
4. The current transaction rolls back according to the rollback rules.
5. The writer does not receive this chunk's outputs because the processing phase did not complete.
6. The step transitions to a failed state if the exception is not handled by a fault-tolerance policy.

Output objects already created in memory before the exception occurred are not automatically written to the database. If the processor performed side effects outside the transaction—such as sending an HTTP request or publishing a message—a database rollback cannot automatically undo those side effects.

### Is the Writer Called?

In a normal chunk flow, Spring Batch calls the writer only after the items in the chunk have been read and processed successfully according to policy. If the processor throws an unhandled exception, the pipeline stops before the writer; the current chunk is not written as a completed chunk.

With a fault-tolerant configuration, the framework may roll back and reprocess/scan items to identify the failing item, or perform retries according to policy. During that process, the processor may be called multiple times. Therefore, you should not claim that the writer is strictly never called in all fault-tolerant scenarios; what needs to be verified is that the writer only writes outputs accepted by the policy and that transaction rollback leaves no partial data behind.

## Rollback Scope: Current Chunk vs. Previous Chunks

Rollback only affects uncommitted changes in the current transaction. Previously committed chunks are not automatically rolled back when a later chunk fails.

For example, a step processes 7 items with `chunk(3, transactionManager)`:

```text
Chunk 1: Item 1, 2, 3  -> writer succeeds -> COMMIT
Chunk 2: Item 4, 5, 6  -> processor fails at Item 6 -> ROLLBACK
Chunk 3: Item 7        -> not yet processed
```

Typical outcome:

| Processing Unit | Data State |
| --- | --- |
| Chunk 1 | Committed data remains intact |
| Chunk 2 | Changes participating in the transaction are rolled back |
| Chunk 3 | Not yet processed because the step already failed |

This is why you should not treat an entire job as a single transaction. A long-running job may commit hundreds or thousands of chunks. When a chunk fails, previously committed chunks are preserved and a restart typically resumes from the appropriate checkpoint.

If business requirements demand that the entire job be atomic, default chunk processing does not provide a single transaction spanning all chunks. Consider staging/publishing, compensating transactions, or a different business workflow.

## Example Step Configuration Where the Processor Throws an Exception

Suppose an order import job runs. An order with an invalid amount causes the processor to throw `InvalidOrderException`.

```java
public record OrderInput(String orderId, BigDecimal amount) {
}

public record Order(String orderId, BigDecimal amount) {
}

public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

The processor validates and transforms:

```java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Amount must be positive for order " + input.orderId());
        }

        return new Order(input.orderId(), input.amount());
    }
}
```

Declaring the chunk step in Spring Batch 5:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(3, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

In this configuration there is no `.faultTolerant().skip(...)` or `.retry(...)`. Therefore, `InvalidOrderException` is not handled by a policy; the step fails and the active chunk transaction rolls back. If the writer uses the same datasource and transaction manager as the step, the chunk's writes are protected by that transaction.

## The Transaction Manager Determines Which Data Is Rolled Back

Rollback only applies to resources that actually participate in the transaction. If the processor calls a service that uses the same transaction manager and the same database resource as the step, the service's JDBC/JPA statements typically participate in the chunk transaction.

Example service:

```java
@Service
public class OrderEnrichmentService {

    private final JdbcTemplate jdbcTemplate;

    public OrderEnrichmentService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void recordEnrichment(String orderId) {
        jdbcTemplate.update(
                "INSERT INTO order_enrichment(order_id, status) VALUES (?, ?)",
                orderId,
                "CHECKED");
    }
}
```

If the service uses `REQUIRED` propagation with the same transaction manager and resource, it joins the active chunk transaction. If the processor subsequently throws an exception, the insert in `recordEnrichment` can roll back along with the chunk.

If the service uses `REQUIRES_NEW`, it opens an independent transaction. The service may commit successfully before the processor throws an exception; rolling back the chunk transaction cannot undo that already-committed transaction. Carefully consider propagation when calling a service from a processor.

| Operation Type in Processor | Rolls Back with the Chunk? |
| --- | --- |
| JDBC/JPA using the same transaction resource and manager | Typically yes |
| Service `@Transactional(REQUIRED)` using the same manager | Joins current transaction; typically yes |
| Service `@Transactional(REQUIRES_NEW)` | Independent transaction may have committed; does not roll back with the chunk |
| Direct file write | Does not automatically roll back with a JDBC transaction |
| Sending an HTTP request | Does not automatically roll back |
| Publishing a message to a broker not in a shared transaction | Does not automatically roll back |
| Writing to a different datasource with a separate local transaction manager | No atomic rollback by default |

Do not assume every operation invoked from a processor rolls back just because the processor runs inside a chunk transaction. Check the transaction manager, datasource, propagation, and external system protocol.

## Exception Types and Rollback Rules

`ItemProcessor.process` declares `throws Exception`, so a processor can throw either checked or unchecked exceptions. Spring Batch configures the step's transaction to handle exceptions according to the step's rollback rules; by default, a chunk transaction rolls back when chunk processing fails. If the application customizes transaction attributes or configures non-rollback exceptions, verify the actual behavior.

In a fault-tolerant step, settings such as `skip`, `retry`, and `noRollback` affect how the framework handles exceptions. Do not infer behavior solely from whether an exception is checked or runtime while ignoring the step configuration.

Example of configuring no-rollback for a selected exception:

```java
.faultTolerant()
.skip(AlreadyProcessedException.class)
.noRollback(AlreadyProcessedException.class)
.skipLimit(20)
```

`noRollback` is a specialized configuration and should only be used when the exception semantics and processing state allow continuing without rolling back the chunk. It does not mean every processor exception can safely skip rollback. Test the actual transaction and output before using it, especially when the writer or processor has side effects.

## Rollback Without Skip or Retry Configured

This is the most basic case. If the processor throws an exception not handled by any policy:

- The current chunk is not committed.
- Database operations participating in the chunk transaction roll back.
- The step typically ends in `FAILED`.
- The job typically ends in `FAILED` if the flow has no dedicated error-handling branch.
- Previously committed chunks remain intact.
- The same `JobInstance` can be restarted if the job and step allow restarts.

For example, a test can assert that the step failed and data from the uncommitted chunk does not appear in the target table. If the test uses a chunk size larger than the total input, no business rows may be written at all. If the test spans multiple chunks, rows from earlier chunks remain.

## Rollback When Processor Exceptions Are Retried

Retry is appropriate for transient errors likely to resolve on their own, such as deadlocks or service timeouts. When the processor throws an exception covered by the retry policy, Spring Batch can retry the operation as configured.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientLookupException.class)
        .retryLimit(3)
        .build();
```

With this configuration, `TransientLookupException` is retried according to the retry policy. The number of attempts and how `retryLimit` is interpreted should be verified against your project's API/version; in standard Spring Batch configurations, the retry limit specifies the maximum number of retry attempts after the initial try.

When a retry occurs, the processor may be called again for the same item. A chunk may be rolled back before the framework performs the next attempt depending on the retry type and transaction boundary. Therefore:

- The processor should be deterministic for the same input and reference data.
- Avoid writing files, sending messages, or calling APIs with non-idempotent side effects inside the processor.
- If an external service must be called, use an idempotency key or an API that supports status lookup.
- Only retry recoverable errors; deterministic data errors usually should not be retried.

If a retry succeeds, the item is processed and the chunk can proceed to the writer and commit. If retries are exhausted, the exception follows the remaining policies: it may be skipped if configured and classified appropriately, or it causes the step to fail.

## Rollback When Processor Exceptions Are Skipped

Skip is appropriate for data errors that business rules allow ignoring. If the processor's exception is declared in the skip policy and the total skip count has not exceeded the limit, the failing item can be excluded from the output so remaining items are written.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

With fault-tolerant processing, Spring Batch may roll back the chunk and then reprocess/scan items to identify the failing item. Once the failing item is skipped, valid items can be written in the appropriate transaction. Thus, the final result differs from having no skip policy: the entire chunk is not necessarily discarded just because one item failed.

If the skip count exceeds `skipLimit`, the step fails. The current chunk may roll back, while previously committed chunks are preserved. Check `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `skipCount` to see where errors occurred.

### Filtering vs. Skipping

A processor returns `null` to filter a valid item that does not require output. This is not an exception and does not trigger a rollback solely because the result is `null`.

| Processor Result | Meaning | Impact |
| --- | --- | --- |
| Returns an object | Processed successfully | Output is included in the chunk |
| Returns `null` | Intentional item filtering | Item does not reach writer; increments `filterCount` |
| Throws a retryable exception | Recoverable error | Framework retries per retry policy |
| Throws a skippable exception | Allowable error | Item is skipped if within limit |
| Throws an unhandled exception | Unrecoverable error | Chunk rolls back and step fails |

Do not use `null` to mask data errors. If an item is invalid and needs to be recorded as rejected, throw an appropriate exception and use a skip policy/`SkipListener`.

## Reader State After Rollback

Readers often maintain state such as file position, offset, or page. Readers integrated with `ItemStream` can store state in the step `ExecutionContext` at checkpoints. When a chunk rolls back, the previously committed checkpoint remains a safe point for restart.

Do not assume every reader automatically rewinds its in-memory cursor as soon as a transaction rolls back. How already-read items are handled depends on the reader and data source:

- For non-transactional readers, the framework typically buffers read items so they can be reprocessed without re-reading from the source in certain rollback/fault-tolerant paths.
- For transactional sources such as message queues, rollback may return messages to the source per resource semantics.
- For stateful file/database readers, checkpoints are saved at commit points; restart uses the saved state.
- For custom readers, follow `ItemStream` and design state to restore accurately after rollback/restart.

If a reader updates an instance field on read, that field may have already advanced even though the chunk has not committed. Ensure the framework or reader has a way to restore or re-read uncommitted items. Do not persist checkpoints in an independent transaction before the corresponding data commits.

## ExecutionContext and Restart After Processor Failure

`ExecutionContext` stores step checkpoints. When a chunk commits successfully, readers and writers can update state and Spring Batch persists the context along with metadata according to the configured transaction/lifecycle.

Example reader storing the last processed key:

```java
public class OrderReader implements ItemStreamReader<OrderInput> {

    private long lastProcessedId;

    @Override
    public void open(ExecutionContext context) {
        lastProcessedId = context.getLong("lastProcessedId", 0L);
    }

    @Override
    public OrderInput read() {
        return readNextAfter(lastProcessedId);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastProcessedId", lastProcessedId);
    }

    @Override
    public void close() {
    }
}
```

`readNextAfter(...)` represents the query implemented by the application. This example only illustrates the minimal state to persist. A real reader must update `lastProcessedId` according to rules aligned with processed/committed items, not merely the most recently read item if rollback can occur.

When the processor throws an exception and the chunk rolls back:

1. Data in the uncommitted chunk is rolled back if using the same transaction resource.
2. Previously committed checkpoints remain intact.
3. The step fails if the exception is not retried or skipped.
4. On restart with the same identifying parameters, the reader restores the valid checkpoint.
5. Items from the uncommitted chunk can be re-read/reprocessed according to reader semantics.

Keep identifying parameters unchanged when restarting the same `JobInstance`. Adding a new identifying timestamp creates a different instance and may cause the job to run from the beginning.

## Side Effects in the Processor Do Not Automatically Roll Back

`ItemProcessor` should focus on validating and transforming data. If the processor performs side effects before throwing an exception, those side effects may persist after the chunk rolls back.

Risky example:

```java
public Order process(OrderInput input) {
    notificationClient.send("Processing " + input.orderId());

    if (input.amount().signum() <= 0) {
        throw new InvalidOrderException("Invalid amount");
    }

    return map(input);
}
```

If the notification was sent and then the processor throws an exception, a database rollback does not retract the notification. On retry or restart, the notification may be sent again.

Safer alternatives:

- Keep the processor pure, only producing output or throwing exceptions.
- Move the side effect to the writer so it sits within an appropriate transaction if the target supports it.
- Write events to a transactional outbox alongside business data and have a separate publisher send messages.
- Use idempotency keys for APIs or messages to handle duplicate deliveries.
- Cache reusable lookup results if needed to avoid repeated external service calls.

Do not rely on chunk rollback to undo files, HTTP requests, emails, or messages already accepted by external systems.

## Testing Rollback When Processor Throws an Exception

Tests need to prove three things:

1. A processor exception rolls back the current chunk when no handling policy is configured.
2. Data from previously committed chunks remains intact.
3. Uncommitted data from the failing chunk does not appear in the target if the writer shares the transaction resource.

Use integration tests with `JobRepository`, a transaction manager, and a real test database. A processor unit test only proves that the processor throws an exception; it does not prove that Spring Batch transactions roll back properly.

### Fixture Example

```java
public record OrderInput(String orderId, boolean invalid) {
}

public record Order(String orderId) {
}

public class FailingOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.invalid()) {
            throw new InvalidOrderException(input.orderId());
        }
        return new Order(input.orderId());
    }
}
```

With a chunk size of 2, provide four items: the first two valid and the third failing. The writer inserts into the `processed_order` table via JDBC and uses the same transaction manager as the step.

```text
Input: [O-1 valid, O-2 valid] [O-3 invalid, O-4 valid]
Chunk 1: write O-1, O-2 -> COMMIT
Chunk 2: processor fails at O-3 -> ROLLBACK
Expected rows: O-1, O-2
```

The test can use `JobLauncherTestUtils` to run the job and `JdbcTemplate` to verify the target table:

```java
@SpringBootTest
@SpringBatchTest
class ProcessorRollbackIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("processorRollbackJob")
    private Job processorRollbackJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void configureJob() {
        jobLauncherTestUtils.setJob(processorRollbackJob);
        jdbcTemplate.update("DELETE FROM processed_order");
    }

    @Test
    void rollsBackChunkWhereProcessorThrows() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, execution.getStatus());

        List<String> orderIds = jdbcTemplate.queryForList(
                "SELECT order_id FROM processed_order ORDER BY order_id",
                String.class);

        assertEquals(List.of("O-1", "O-2"), orderIds);
    }
}
```

The illustrative test assumes the job fixture has a reader returning exactly four items, chunk size 2, a writer inserting into `processed_order`, and all using the same datasource/transaction manager. If chunk size or input order differs, expected results must adjust to the actual transaction boundary.

### Verifying the Failure Exception

Beyond `BatchStatus.FAILED`, you can inspect `StepExecution.getFailureExceptions()` to confirm the cause is `InvalidOrderException` or a wrapped exception with a matching cause. Avoid comparing only error messages since messages can change or be augmented by the framework.

```java
StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.FAILED, stepExecution.getStatus());
assertFalse(stepExecution.getFailureExceptions().isEmpty());
```

If you need to find the root exception in the cause chain, write a helper that traverses `Throwable.getCause()` and checks exception types rather than relying on a fixed index in the list.

## Testing Rollback with Skip/Retry

Have separate tests to confirm how configuration changes behavior.

| Configuration | Processor Exception | Behavior to Verify |
| --- | --- | --- |
| No skip/retry | Unhandled exception | Chunk rolls back, step `FAILED` |
| Retry | Transient exception then succeeds | Retried per policy; chunk can complete and commit |
| Skip | Skippable exception within limit | Failing item skipped; valid outputs written per policy |
| Skip limit exceeded | Total skips exceed limit | Step `FAILED`; current chunk rolls back per fault-tolerance semantics |
| `noRollback` configured | Exception marked non-rollback | Behavior per configuration; verify specific data and counters |

Do not use a single test to prove every branch. Each policy has different semantics and needs its own fixture, especially when the processor has side effects or the writer writes to multiple resources.

## Testing Processor Re-invocation

With retry or skip scanning, a processor can be called multiple times for the same item. Tests should count invocations or use mocks to verify behavior when configuration requires retries.

Example of a processor failing transiently once and then succeeding:

```java
public class RetryOnceProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Order process(OrderInput input) {
        if (attempts.getAndIncrement() == 0) {
            throw new TransientLookupException("Temporary lookup failure");
        }
        return new Order(input.orderId());
    }
}
```

An integration test with `.retry(TransientLookupException.class).retryLimit(1)` can verify that the processor is called again and the step completes if the next attempt succeeds. In production applications, do not use a field counter as a retry mechanism; the example only creates a controlled failure for testing. Real processors should be stateless and independent of invocation counts.

If the processor depends on an external service, use deterministic mocks or stubs. Do not use `Thread.sleep` to simulate failures; throw controlled exceptions for stable tests.

## Checking Data on Partial Rollback

Chunk rollback does not mean all step data disappears. With multiple chunks, tests should verify:

- Rows from chunks committed before the error remain.
- Rows belonging to the rolled-back chunk are absent if the writer shares the transaction.
- Rows from chunks not yet reached do not appear.
- Metadata reflects the failed step and the last committed checkpoint.
- Side effects outside the transaction are verified separately.

If the writer writes files or messages, test them separately because a JDBC transaction cannot prove those resources rolled back. For files, use temporary outputs and verify cleanup/rename workflows. For messages, use event IDs and verify that consumers handle duplicates safely.

## Common Mistakes

### Thinking a Processor Exception Only Breaks One Item

Without skip or retry configured, an exception can roll back the entire current chunk and fail the step. To discard only the failing item, configure an explicit skip policy.

### Thinking the Entire Job Rolls Back

Previously committed chunks remain intact. The transaction boundary is per chunk, not the entire job.

### Assuming the Writer Already Wrote Part of the Chunk

In a standard pipeline, a processor exception occurs before the writer is invoked for that chunk. If a writer or listener has other side effects, analyze them by their individual callbacks and transactions.

### Calling APIs or Writing Files Inside the Processor

Side effects outside the database do not automatically roll back. Retries may repeat side effects. Keep the processor pure or use idempotency/outbox patterns.

### Unintentionally Using REQUIRES_NEW

A service may commit independently and then the processor throws an exception. Chunk rollback does not erase data already committed by the service. Check transaction propagation.

### Failing to Persist Checkpoints Properly

A reader may have already read items while the chunk has not yet committed. Use a reader supporting `ItemStream` or proper buffering/restart mechanisms; do not persist checkpoints independently ahead of the data.

### Catching Exceptions and Returning Normal Output

If a processor swallows an error and returns a dummy object or `null`, the framework may not know the chunk encountered an error. Only turn errors into filters or defaults when it is an explicit business decision; if an item cannot be processed, throw an exception.

### Testing Only for FAILED Status

`FAILED` does not prove business data rolled back properly. Verify the target table, committed chunks, checkpoints, and root exceptions.

## Processor Design Principles for Safe Rollback

When writing processors for production jobs, consider:

1. Keep the processor focused on validation, transformation, and enrichment that can be safely repeated.
2. Throw clearly typed exceptions so skip/retry policies classify them accurately.
3. Do not use `null` to hide errors; return `null` only when intentionally filtering valid items.
4. Avoid non-idempotent side effects in the processor.
5. When calling transactional services, verify propagation and the transaction manager.
6. Ensure database writes that must roll back share the same transaction resource as the step.
7. Design reader state and `ExecutionContext` to restart from committed checkpoints.
8. Clearly define which exceptions are retried, which are skipped, and which fail the step.
9. Verify that previously committed chunks are preserved when a later chunk fails.
10. Test both database rollback and external system side effects.

## Key Takeaways

When `ItemProcessor` throws an unhandled exception, processing of the current chunk stops and the chunk's transaction typically rolls back; the writer does not write outputs for the incomplete chunk. Previously committed chunks remain intact. If the exception is configured for retry, the processor may be called again; if configured for skip and within `skipLimit`, the failing item can be excluded so valid outputs continue to be written. Rollback only covers resources participating in the same transaction manager: JDBC/JPA on the same resource can roll back, whereas files, HTTP requests, messages, or `REQUIRES_NEW` transactions are not automatically undone. Keep processors safe for re-invocation, store checkpoints properly in `ExecutionContext`, and test both step status and actual data after rollback/restart.
