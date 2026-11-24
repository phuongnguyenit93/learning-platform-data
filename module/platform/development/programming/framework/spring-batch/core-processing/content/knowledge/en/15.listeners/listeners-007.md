# SkipListener in Spring Batch

In chunk-oriented processing, not every item can be read, processed, or written successfully. When an exception is permitted to be ignored by the skip policy, Spring Batch can continue processing the remaining items instead of failing the entire step. `SkipListener` is the listener notified when an item is skipped, helping the application record faulty data, persist details for reconciliation, or create quarantine records.

`SkipListener` focuses on **notifying about items that have been skipped**. It does not decide which exceptions are skipped; that decision belongs to the fault-tolerant step and `SkipPolicy`. Understanding the three callbacks—read, process, and write—helps record bad data accurately while avoiding confusion between skipping, filtering, and retrying.

## 1. What is Skip in Spring Batch?

In chunk processing, an item can encounter an exception at three stages:

1. **Read:** the reader cannot read or parse a record.
2. **Process:** the processor cannot process the input item.
3. **Write:** the writer cannot write the output item.

If that exception type is configured as skippable and the skip limit has not been exceeded, Spring Batch skips the failing item and continues according to the step's policy.

For example, a CSV file has 1,000 lines, and one line is malformed. If `FlatFileParseException` is skippable, the job can ignore the bad line, record it, and continue with the valid lines that follow.

```text
Reader -> Processor -> Writer
   |          |          |
   v          v          v
 Read       Process     Write
 exception  exception   exception
   |          |          |
   +----------+----------+
              |
              v
      SkipPolicy allows?
              |
        +-----+-----+
        |           |
       Yes          No
        |           |
        v           v
 SkipListener     Step fails
 is called        or retries per configuration
        |
        v
 Continue processing next item
```

Skipping is an intentional application decision. Do not configure every exception to be skipped just so the job always finishes successfully, as infrastructure errors or programming bugs can cause silent data loss.

## 2. What Role Does SkipListener Play?

`SkipListener` is a callback invoked by Spring Batch when an item is skipped. Applications commonly use this listener to:

- Log the error type and record location.
- Save faulty records to a quarantine table or dead-letter storage.
- Record business keys for later reconciliation and reprocessing.
- Increment metrics by error type and failing phase.
- Generate operational details so owners know why an item was not processed.

The listener is called only after the framework determines the item will be skipped under the policy. If an exception is retried and a subsequent attempt succeeds, the item is not skipped and the corresponding skip callback is not invoked for that transient failure.

`SkipListener` does not replace `ItemReadListener`, `ItemProcessListener`, or `ItemWriteListener`. Those listeners observe general read, process, and write events; `SkipListener` focuses solely on accepted skip outcomes.

## 3. Three Callbacks of SkipListener

In Spring Batch 5, the interface takes two generic types: input item type `I` and output item type `O`.

```java
public interface SkipListener<I, O> extends StepListener {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(I item, Throwable t);

    void onSkipInWrite(O item, Throwable t);
}
```

Each callback corresponds to a different phase:

| Callback | When is it called? | Does it receive an item? |
| --- | --- | --- |
| `onSkipInRead(Throwable t)` | An exception in the reader is allowed to be skipped by the policy. | No; the reader failed to produce a valid item. |
| `onSkipInProcess(I item, Throwable t)` | The processor throws an exception and the input item is skipped. | Yes, input item of type `I`. |
| `onSkipInWrite(O item, Throwable t)` | The writer cannot write an output item and that item is skipped. | Yes, output item of type `O`. |

The difference in item types is important. If the processor transforms `Order` into `OrderEntity`, `onSkipInProcess` receives `Order`, whereas `onSkipInWrite` receives `OrderEntity`.

## 4. onSkipInRead: Recording Errors in the Read Phase

`onSkipInRead(Throwable t)` is called when the reader throws an exception and that exception is determined to be skippable. The callback receives no item because the reader could not return a valid item.

For example, with `FlatFileItemReader`, `FlatFileParseException` can supply the line number and offending input content:

```java
public class OrderSkipListener
        implements SkipListener<Order, OrderEntity> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable t) {
        if (t instanceof FlatFileParseException parseException) {
            log.warn(
                "Skip invalid input at line {}: {}",
                parseException.getLineNumber(),
                parseException.getInput()
            );
            return;
        }

        log.warn("Skip input because reader failed", t);
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        log.warn("Skip order {} during processing", item.getId(), t);
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        log.warn("Skip order entity {} during writing", item.getOrderId(), t);
    }
}
```

Not every read exception can provide record content. With database connection loss or file-open errors, only the exception and source metadata can be recorded. Do not assume `onSkipInRead` always has a raw item to save.

In particular, do not turn connection errors or configuration errors into read skips when the reader cannot safely continue. Read skips are best suited when an exception represents a specific bad record that can be discarded while continuing to read the rest.

## 5. onSkipInProcess: Recording Items Failing During Processing

`onSkipInProcess(I item, Throwable t)` is invoked when the processor throws an exception and the policy decides to skip the input item.

Example:

```java
@Override
public void onSkipInProcess(Order item, Throwable t) {
    log.warn(
        "Order {} cannot be processed: {}",
        item.getId(),
        t.getMessage()
    );
}
```

This callback receives the input item, so you can extract business keys to investigate or persist error information. However, record only necessary fields; avoid logging the whole object if it contains personal data, secrets, or large payloads.

Another example is writing the faulty record to a quarantine repository:

```java
@Override
public void onSkipInProcess(Order item, Throwable t) {
    rejectedOrderRepository.save(
        new RejectedOrder(item.getId(), "PROCESS", t.getMessage())
    );
}
```

If this repository uses the same datasource and transaction manager as the chunk step, the save operation can participate in the current transaction. If writing to another datasource or calling an external API, you need deduplication and dedicated error handling. The listener does not automatically create distributed transactions.

## 6. onSkipInWrite: Recording Items Failing During Writing

`onSkipInWrite(O item, Throwable t)` is invoked when the writer cannot persist an output item and that item is skipped.

Example:

```java
@Override
public void onSkipInWrite(OrderEntity item, Throwable t) {
    log.error(
        "Cannot persist order {}: {}",
        item.getOrderId(),
        t.getMessage()
    );
}
```

The callback receives the output type `O`, not the input type `I`. If the processor transformed or enriched the data, the listener can record properties of the post-processing object.

Write skipping has a notable characteristic: the writer typically receives an entire chunk, not a single item. If writing the chunk fails, the framework may roll back and re-attempt writing in a way that identifies the offending item. Consequently, the writer can be called multiple times while isolating the bad item. Do not assume a single writer failure always triggers a single immediate skip callback.

When the writer has non-transactional side effects, re-invoking it to isolate the failing item can duplicate effects. The writer needs proper transaction support or idempotency; do not rely on `SkipListener` to repair side effects that have already occurred.

## 7. Configuring Skip Policy in a Chunk Step

For `SkipListener` to be invoked, the step must allow skipping and the exception must be accepted by the policy. Example:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer,
                      OrderSkipListener skipListener) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .listener(skipListener)
        .build();
}
```

In the example, `FlatFileParseException` and `InvalidOrderException` are skippable. The total number of accepted skips in the step is capped by `skipLimit(20)`. When the limit is exceeded, the step fails instead of continuing to skip items.

The skip limit applies across read, process, and write errors combined in the step, not 20 errors per phase. For instance, if 12 read skips and 8 process skips have occurred, the limit of 20 is exhausted; another skip will cause the step to fail.

Do not configure `.skip(Exception.class)` indiscriminately. If you must declare a broad type, use `.noSkip(...)` for exceptions that must fail the step and verify ordering/classification rules for the API version in use.

## 8. How Retry, Skip, and Filter Differ

These three mechanisms have distinct meanings:

| Mechanism | What happens? | Is SkipListener called? |
| --- | --- | --- |
| Retry | The framework retries the failing operation per the retry policy. | No, if the retry succeeds. |
| Skip | The framework agrees to skip the failing item per the skip policy. | Yes, the callback matching the failing phase is invoked. |
| Filter | The processor returns `null` to exclude the item per business rules. | No; this is neither an exception nor a skip. |

For example, a cancelled order can be filtered by having the processor return `null`. An order with invalid data causes the processor to throw `InvalidOrderException`; if the exception is skippable, `onSkipInProcess` is called. A transient database error in the writer can be retried; if the retry succeeds, there is no write skip.

Distinguishing them properly keeps data quality statistics accurate. `filterCount` reflects filtered items, whereas skip count reflects skipped exceptions. Do not lump them together into a single "bad records" bucket when their business meanings differ.

## 9. Custom SkipPolicy

For complex classification rules, you can use `SkipPolicy` instead of a simple `.skip(...)` list. The policy receives the exception and the current skip count, then decides whether skipping is allowed.

```java
public class OrderSkipPolicy implements SkipPolicy {

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException) {
            return skipCount < 20;
        }

        if (throwable instanceof FlatFileParseException) {
            return skipCount < 20;
        }

        return false;
    }
}
```

Register the policy:

```java
.faultTolerant()
.skipPolicy(new OrderSkipPolicy())
.listener(skipListener)
```

When using a custom policy, the policy is responsible for deciding the limit and exception types. Throw `SkipLimitExceededException` or return the appropriate result per the API contract so the framework handles limit exhaustion. Do not combine a custom policy with `.skipLimit(...)` in a way that creates ambiguity about limit enforcement; pick one clear place to manage the limit.

A skip policy does not replace the listener. The policy decides **whether to skip**; the listener reports **which item was skipped and what error occurred**.

## 10. Registering SkipListener on a Step

You can implement the interface and register it directly on the step builder:

```java
@Bean
OrderSkipListener orderSkipListener(
        RejectedOrderRepository rejectedOrderRepository) {
    return new OrderSkipListener(rejectedOrderRepository);
}

@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer,
                      OrderSkipListener orderSkipListener) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(20)
        .listener(orderSkipListener)
        .build();
}
```

Spring Batch detects the listener by interface and invokes the matching callbacks. Using a Spring bean makes it easy to inject required repositories, loggers, or metric services. If a listener is shared across multiple steps, ensure its internal state is safe for the scope and concurrency of those steps.

## 11. Using Annotations for Skip Callbacks

In addition to implementing the interface, Spring Batch supports listener annotations:

- `@OnSkipInRead` for exceptions while reading.
- `@OnSkipInProcess` for input item and exception while processing.
- `@OnSkipInWrite` for output item and exception while writing.

Example:

```java
public class OrderSkipAnnotationListener {

    @OnSkipInRead
    public void onReadError(Throwable t) {
        // Record reader error; no valid item available.
    }

    @OnSkipInProcess
    public void onProcessError(Order item, Throwable t) {
        // Record skipped input item.
    }

    @OnSkipInWrite
    public void onWriteError(OrderEntity item, Throwable t) {
        // Record skipped output item.
    }
}
```

Register the listener object on the step with `.listener(annotationListener)`. Method parameter types must match the phase and generic types of the step. If a method signature is incompatible, the listener may not be invoked as expected or configuration may fail at startup.

For listeners with multiple dependencies or needing strict generic type checking, implementing `SkipListener<I,O>` is usually easier to read and test.

## 12. Callback Timing and Transactions

Spring Batch designs skip callbacks to be invoked right before the chunk transaction commits. This matters when the listener writes an error record to the same database and transaction manager as the step: the quarantine record can commit alongside the chunk containing the skip decision.

Example:

```text
Chunk transaction
    |
    +-- Reader/Processor/Writer encounters failing item
    |
    +-- SkipPolicy allows skip
    |
    +-- SkipListener writes rejected-item record
    |
    +-- Update metadata and counters
    |
    +-- COMMIT
```

If the transaction rolls back, transactional operations of the listener on the same resource can also roll back. When the chunk is retried, let the framework execute the callback lifecycle properly. Spring Batch provides guarantees that skip callbacks are notified according to skip processing semantics, though that is not a distributed exactly-once guarantee for emails, HTTP APIs, or message brokers.

If the listener writes to an external system outside the transaction, the callback can produce side effects the database cannot undo. Use an idempotency key, outbox, or an appropriate durable recording mechanism. Avoid sending emails directly from the listener if duplicate sends are unacceptable.

The listener must also handle its own errors. If writing the quarantine record fails, the skip decision may not complete as intended and the chunk/job may fail. Do not swallow persistence errors if rejected data must be stored for reconciliation.

## 13. Storing Skipped Items in a Quarantine Table

A common use case is saving failing item details into a separate table so operators can inspect and reprocess them.

Example entity:

```java
public record RejectedOrder(
    String orderId,
    String phase,
    String errorType,
    String errorMessage
) {}
```

Listener:

```java
public class OrderQuarantineSkipListener
        implements SkipListener<Order, OrderEntity> {

    private final RejectedOrderRepository repository;

    public OrderQuarantineSkipListener(RejectedOrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        if (t instanceof FlatFileParseException parseException) {
            repository.save(new RejectedOrder(
                "line-" + parseException.getLineNumber(),
                "READ",
                t.getClass().getSimpleName(),
                parseException.getMessage()
            ));
        }
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        repository.save(new RejectedOrder(
            item.getId(),
            "PROCESS",
            t.getClass().getSimpleName(),
            t.getMessage()
        ));
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        repository.save(new RejectedOrder(
            item.getOrderId(),
            "WRITE",
            t.getClass().getSimpleName(),
            t.getMessage()
        ));
    }
}
```

This is an illustrative example; a real model may need `jobExecutionId`, `stepExecutionId`, batch ID, file name, line number, event ID, and error timestamp. For read errors, `orderId` may be unknown, so store a source identifier such as file/line or raw record if provided by the exception.

If the quarantine table lives in the same database and uses the same transaction manager, the save operation can commit with the chunk. Include an appropriate unique key to prevent duplicate inserts if the job restarts or faulty data is reprocessed in another execution. Decide whether to store the full stack trace or only a sanitized error code/message, and avoid writing sensitive data into the error table.

## 14. SkipListener and Chunk-Based Writer Errors

Writer errors can be more complex than read or process errors because the writer normally receives multiple items at once. For instance, a chunk contains `[A, B, C, D]`, and the writer fails when writing one item. The framework can roll back the chunk and attempt writing item by item or scan to pinpoint the failing item.

```text
Writer receives [A, B, C, D]
          |
          v
      write fails
          |
          v
      rollback chunk
          |
          v
Framework isolates failing item via write-skip handling
          |
          +-- A written
          +-- B written
          +-- C fails and is skipped -> onSkipInWrite(C, exception)
          +-- D written
```

The diagram is conceptual; the actual number of writer calls and operation order depend on step configuration and error-handling mechanics. What matters is that the writer must tolerate being called again. If the writer calls an external API or partially writes to a non-rollbackable resource, isolating the bad item can repeat side effects.

For database writers participating in the same transaction, rollback clears partial changes before the framework isolates the failing item. For custom writers, ensure write operations have appropriate atomicity or idempotency keys.

## 15. SkipListener Can Be Used for Metrics and Auditing

In addition to quarantine storage, the listener can update metrics by phase and exception type:

```java
public class SkipMetricsListener implements SkipListener<Order, OrderEntity> {

    private final Counter readSkips;
    private final Counter processSkips;
    private final Counter writeSkips;

    public SkipMetricsListener(MeterRegistry registry) {
        this.readSkips = registry.counter("batch.skip", "phase", "read");
        this.processSkips = registry.counter("batch.skip", "phase", "process");
        this.writeSkips = registry.counter("batch.skip", "phase", "write");
    }

    @Override
    public void onSkipInRead(Throwable t) {
        readSkips.increment();
    }

    @Override
    public void onSkipInProcess(Order item, Throwable t) {
        processSkips.increment();
    }

    @Override
    public void onSkipInWrite(OrderEntity item, Throwable t) {
        writeSkips.increment();
    }
}
```

Metrics help monitor error trends over time. If read skips spike suddenly, the input file format may have changed; if write skips increase, target constraints or data quality may have an issue.

With in-memory metrics or external metrics systems outside the transaction, a callback can increment counters even if the chunk transaction later rolls back. Therefore, callback metrics are suitable for operational observability, but should not be used alone as an accounting-grade business data source. If durable auditing is needed, persist a record within the transaction or use an outbox.

## 16. Testing SkipListener

Test all three callbacks as well as integration behavior with the skip policy. Direct unit tests on the listener are suitable for verifying how it extracts details and saves quarantine records:

```java
@ExtendWith(MockitoExtension.class)
class OrderSkipListenerTest {

    @Mock
    RejectedOrderRepository repository;

    @Test
    void recordsProcessSkip() {
        OrderSkipListener listener = new OrderSkipListener(repository);
        Order order = new Order("ORDER-42");
        InvalidOrderException error =
            new InvalidOrderException("Missing customer id");

        listener.onSkipInProcess(order, error);

        verify(repository).save(argThat(rejected ->
            rejected.orderId().equals("ORDER-42")
                && rejected.phase().equals("PROCESS")
        ));
    }
}
```

Unit tests do not prove Spring Batch will invoke the callbacks. Add integration tests with a fault-tolerant step.

For example, the processor throws an exception for a specific item:

```java
ItemProcessor<Order, OrderEntity> processor = order -> {
    if ("ORDER-BAD".equals(order.getId())) {
        throw new InvalidOrderException("Invalid order");
    }
    return new OrderEntity(order.getId());
};
```

Configure the step with `.skip(InvalidOrderException.class).skipLimit(5).listener(skipListener)`. When running the test job with items `[ORDER-1, ORDER-BAD, ORDER-2]`, you can verify:

- The job/step completes if no other error occurs and the skip limit is not exceeded.
- `readCount` reflects the items supplied by the reader.
- `processSkipCount` increments by one.
- `writeCount` reflects only the written outputs.
- `onSkipInProcess` is invoked with `ORDER-BAD` and the corresponding exception.
- The quarantine table holds a record for the skipped item if the listener persists to a test database.

To test read skips, use a test reader that throws a controlled exception on a specific read and configure that exception as skippable. For write skips, use a test writer that fails on a specific output item and verify `onSkipInWrite` receives the right output type. Do not test only one phase and assume the other two receive the same input data.

## 17. Testing Skip Limits and Retries

Tests should include both scenarios below the limit and scenarios exceeding the limit. For instance, with `skipLimit(2)`, two eligible exceptions can be skipped; the next exception fails the step according to the skip limit rule.

If retry is configured alongside skip, test both branches:

- A transient exception is retried and succeeds: no skip is recorded.
- An exception persists and is covered by the skip policy: the item is skipped, and the corresponding callback is invoked.
- An exception is not covered by the skip policy: the step fails when retries are exhausted or the policy rejects it.

When testing callback counts, use items with distinct identifiers and inspect the repository or a recording listener. For writer errors, remember the framework may invoke the writer multiple times while isolating the item; the number of `write()` calls does not equal the number of `onSkipInWrite()` calls.

## 18. Common Mistakes When Using SkipListener

**Assuming the listener decides skips:** the listener only receives notifications. You must configure `.faultTolerant()`, `.skip(...)`, `.skipLimit(...)`, or a `SkipPolicy`.

**Confusing phases and item types:** `onSkipInProcess` receives input `I`; `onSkipInWrite` receives output `O`; `onSkipInRead` receives only the exception.

**Using skip for infrastructure errors:** connection failures, credential errors, or an unusable source are generally not isolated bad items. Retrying or failing may be more appropriate.

**Configuring skips too broadly:** `.skip(Exception.class)` can hide programming bugs and system errors. Allow only exceptions that have been evaluated as safe to skip.

**Confusing filtering with skipping:** a processor returning `null` does not invoke `SkipListener`. That is filtering, not an exception.

**Assuming read skips have an item:** the reader did not return a valid item, so the callback receives only the exception. Extract line/input from the exception if the reader provides it.

**Performing non-idempotent side effects in the listener:** callbacks can interact with transactions and retries; emails or external APIs outside the database may be duplicated or fail to roll back. Use an outbox or deduplication keys.

**Swallowing errors when saving quarantine records:** if persisting rejected records is mandatory, do not ignore repository exceptions without a fallback plan.

**Storing excessive sensitive data:** logs or quarantine records should hold only necessary details and comply with data protection policies.

## 19. Designing SkipListener in Production

First, clearly identify which exceptions are permitted to be skipped in each phase. Use `.skip(...)` and `.noSkip(...)` for simple cases or `SkipPolicy` when complex rules are required. Set the skip limit based on acceptable business error rates; when exceeded, let the step fail and alert operators.

Next, implement the listener by phase. For read skips, record source metadata such as file, line, or cursor since no valid item exists. For process skips, save input item identifiers. For write skips, save identifiers and output fields needed for investigation. Separate logs/metrics from durable quarantine data when operational needs differ.

Finally, test each callback against the real skip policy, confirming skip counts and error records are persisted accurately. Ensure quarantine persistence joins the proper transaction or is idempotent if external to the transaction. Monitor skip rates by phase and exception type to spot changes in source data quality.

`SkipListener` helps Spring Batch turn skipped items into observable, actionable information. When phase-appropriate listeners are paired with clear skip policies, sensible limits, and safe persistence, applications can continue processing valid data while retaining a trace of every item that could not be processed.
