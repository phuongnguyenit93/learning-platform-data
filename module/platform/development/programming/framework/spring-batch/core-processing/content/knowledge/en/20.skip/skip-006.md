# SkipListener for recording skipped items

In Spring Batch, a Step can be configured to skip a number of failing items instead of stopping the entire Job. When an error is classified as skippable and the skip limit has not been exceeded, the framework drops that item from the processing pipeline and continues with the remaining items. `SkipListener` provides callbacks for the application to record the skipped item, its cause, and the stage where the error occurred.

This listener is especially useful in data import, reconciliation, or synchronization Jobs where some invalid records can be handled separately after the main batch finishes. Skip details can be saved to an error table, dead-letter store, audit log, or monitoring system so operators know which data requires fixing and reprocessing.

## 1. What does skip mean in Spring Batch?

In chunk-oriented processing, Spring Batch reads items, passes them through a processor if present, and writes output items using a writer. If an exception occurs in the reader, processor, or writer, the Step can:

- Fail immediately if the exception is not configured for retry or skip.
- Retry the operation if the exception is retryable.
- Skip the item if the exception is classified as skippable and the skip limit permits.

Skip is an intentional decision in Step configuration. It does not mean the framework ignores every exception. For example, an application may allow skipping a malformed CSV line while still stopping the Job on database disconnection or security failures.

Example of a file with 5 records:

```text
Input: A, B, C, D, E

A -> read, processed, written successfully
B -> validation error -> SKIP
C -> read, processed, written successfully
D -> parse error -> SKIP
E -> read, processed, written successfully

Result:
  3 items written
  2 items recorded as skipped
```

`SkipListener` is invoked once Spring Batch determines that an item is actually skipped under the skip policy. It helps record that final decision.

## 2. SkipListener provides three callbacks

The `SkipListener<I, O>` interface has three methods corresponding to the three stages of the pipeline:

```java
public interface SkipListener<T, S> extends StepListener {

    void onSkipInRead(Throwable t);

    void onSkipInProcess(T item, Throwable t);

    void onSkipInWrite(S item, Throwable t);
}
```

Where:

- `T` is the input item type provided by the reader to the processor.
- `S` is the output item type received by the writer.
- `Throwable` is the cause that led to the item being skipped.

| Callback | Stage | Item available? | Meaning |
|---|---|---|---|
| `onSkipInRead(Throwable)` | Reader | No successfully created item | Reader failed and the item could not be read |
| `onSkipInProcess(T, Throwable)` | Processor | Input item available | Item was read but processing failed and was skipped |
| `onSkipInWrite(S, Throwable)` | Writer | Output item available | Item was processed but could not be written and was skipped |

An important distinction is that `onSkipInRead()` receives no item. When the reader throws an exception, the framework may not have created an input object yet. The listener only receives the exception to identify the cause; depending on exception type, extra details such as line number or raw input can be extracted.

## 3. `onSkipInRead()` — recording read errors

`onSkipInRead()` is invoked when the reader throws an exception and that exception is accepted for skipping. A common scenario is reading a file containing a malformed line, missing columns, or unconvertible data types.

For example, with `FlatFileItemReader`, a parse error can be `FlatFileParseException`, which provides the line number and offending input:

```java
@Override
public void onSkipInRead(Throwable t) {
    if (t instanceof FlatFileParseException ex) {
        log.warn("Skipped input at line {}: {}",
                ex.getLineNumber(),
                ex.getMessage());
    } else {
        log.warn("Skipped item during read: {}", t.toString());
    }
}
```

Because there is no item object, the listener usually records:

- Name of the source or file being read.
- Line number, offset, or read position if provided by the exception.
- Exception type and sanitized error message.
- JobExecution ID, StepExecution ID, or batch ID if the application can attach that context.

Do not assume every read exception has raw input or a line number. With a JDBC reader, the error might be a connection or query issue; with an API reader, it might be an HTTP status or timeout. Record metadata appropriate to each source.

## 4. `onSkipInProcess()` — recording failing items during processing

`onSkipInProcess()` is invoked when the processor receives an item and throws an exception belonging to the skippable group. The listener receives both the input item and the exception, allowing it to save the business key to trace the record.

Example processor validating an order:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

@Component
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Order amount must be positive: " + input.orderId());
        }

        return new Order(input.orderId(), input.amount());
    }
}
```

The listener can record the order ID and reason:

```java
@Override
public void onSkipInProcess(OrderInput item, Throwable t) {
    skippedOrderService.record(
            "PROCESS",
            item.orderId(),
            t.getClass().getSimpleName(),
            t.getMessage());
}
```

The input item passed to the callback is the record that was read but could not be transformed into valid output. If later reprocessing is needed, store sufficient business keys and references to the data source to locate the record again.

## 5. `onSkipInWrite()` — recording failing items during writing

`onSkipInWrite()` is invoked when the writer fails to persist an item and Spring Batch determines that the item is skippable. The listener receives the output item of type `S` along with the exception.

For example, a writer persisting orders to a database where one record violates a constraint configured as skippable:

```java
@Override
public void onSkipInWrite(Order item, Throwable t) {
    skippedOrderService.record(
            "WRITE",
            item.orderId(),
            t.getClass().getSimpleName(),
            t.getMessage());
}
```

When a chunk write fails, the writer initially receives a whole group of items. To isolate the failing item, Spring Batch may have to retry or isolate items within the chunk under fault-tolerance handling. Therefore, the writer must behave compatibly with retry/rollback and must not create uncontrolled side effects when re-invoked.

`onSkipInWrite()` receives each item actually skipped, not the entire list of items in the chunk. If the whole chunk fails and the exception is not skippable or exceeds the limit, the listener is not a substitute for writer error handling; the Step will fail.

## 6. Configuring skip and registering SkipListener

For callbacks to be invoked, the Step must be configured with fault tolerance and skip rules. Then register the listener on the Step.

Spring Batch 5 example:

```java
@Bean
Step importOrdersStep(
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
```

In this example:

- File parse errors and order validation errors are allowed to be skipped.
- Total skips are capped at 50.
- The listener is registered to record items that are actually skipped.
- Exceptions not classified as skippable can still fail the Step.

`skipLimit(50)` permits up to 50 skips under the Step's policy. When a subsequent skip exceeds the limit, the Step fails instead of continuing to skip. This limit applies globally to skips in read, process, and write stages, not 50 per callback.

Without skip configuration for the relevant exceptions, merely registering a `SkipListener` will not automatically skip exceptions. The listener only observes skip decisions already allowed by the Step.

## 7. Implementing a complete SkipListener

A listener can implement all three callbacks and forward error details to a persistence service:

```java
@Component
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final SkippedItemService skippedItemService;

    public OrderSkipListener(SkippedItemService skippedItemService) {
        this.skippedItemService = skippedItemService;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        skippedItemService.recordReadFailure(
                t.getClass().getName(),
                safeMessage(t),
                extractLineNumber(t));
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        skippedItemService.recordItemFailure(
                "PROCESS",
                item.orderId(),
                t.getClass().getName(),
                safeMessage(t));
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        skippedItemService.recordItemFailure(
                "WRITE",
                item.orderId(),
                t.getClass().getName(),
                safeMessage(t));
    }

    private String safeMessage(Throwable t) {
        return t.getMessage() == null
                ? "No error message"
                : t.getMessage();
    }

    private Long extractLineNumber(Throwable t) {
        if (t instanceof FlatFileParseException ex) {
            return (long) ex.getLineNumber();
        }
        return null;
    }
}
```

`recordReadFailure()` and `recordItemFailure()` are illustrative error-storage service APIs. In a real implementation, records can be saved into a `BATCH_SKIPPED_ITEM` table or a dedicated business table with columns such as:

| Field | Meaning |
|---|---|
| `job_execution_id` | Job execution that produced the skip |
| `step_execution_id` | Step that produced the skip |
| `stage` | READ, PROCESS, or WRITE |
| `item_key` | Business key of the item if available |
| `source_location` | File, line, offset, or source reference |
| `exception_type` | Exception class |
| `error_message` | Sanitized error message |
| `created_at` | Recording timestamp |
| `retry_status` | Reprocessing status if a replay workflow exists |

For read errors, `item_key` may be absent because no item was constructed. In that case, `source_location` such as file and line number helps locate the data.

## 8. Recording skips to a database or dead-letter store

A common approach is using a service or repository to write failing items into a dedicated table. This table supports operators in inspecting errors, fixing data, and rerunning items handled separately.

Example of a simple record:

```java
public record SkippedItemRecord(
        String stage,
        String itemKey,
        String exceptionType,
        String errorMessage,
        Instant skippedAt) {
}
```

Service:

```java
@Service
public class SkippedItemService {

    private final SkippedItemRepository repository;

    public SkippedItemService(SkippedItemRepository repository) {
        this.repository = repository;
    }

    public void recordItemFailure(
            String stage,
            String itemKey,
            String exceptionType,
            String errorMessage) {

        repository.save(new SkippedItemRecord(
                stage,
                itemKey,
                exceptionType,
                errorMessage,
                Instant.now()));
    }
}
```

This example illustrates the structure; the repository and database mapping must be implemented according to the application's schema. Also store the JobExecution/StepExecution ID or a business batch ID to link error records back to the original run.

### Why callback timing matters

Spring Batch invokes `SkipListener` right before the chunk transaction commits. This lets the listener record the skip once the item is confirmed to be skipped and avoids repeated callback invocations caused by chunk rollbacks in normal processing scenarios.

If the skip-record repository uses the same DataSource and transaction manager as the Step, skip records can commit together with the chunk transaction. Thus valid output data and skip information remain consistent within the same transaction.

If the listener writes to another database, calls an HTTP API, or publishes a message directly, that operation does not automatically belong to the chunk transaction. A situation can arise where the external system received the error record yet the chunk transaction later rolled back due to another error. For durable auditing requirements, consider a transactional outbox or a separate idempotent recording mechanism.

If saving the skip record fails and an exception escapes the listener, the chunk may fail/roll back. This is usually desirable when business rules mandate every skipped item must be persisted. If losing some technical logs is acceptable, design a separate logging/metrics channel and define an explicit policy instead of silently swallowing errors.

## 9. Distinguishing SkipListener from Item Listeners

Spring Batch provides listeners to observe errors at each stage. They serve different purposes:

| Listener | Error callback | When is it invoked? |
|---|---|---|
| `ItemReadListener` | `onReadError(Exception)` | When the reader throws an exception during a read attempt |
| `ItemProcessListener` | `onProcessError(item, Exception)` | When the processor throws an exception |
| `ItemWriteListener` | `onWriteError(Exception, items)` | When the writer throws an exception for a group of items |
| `SkipListener` | `onSkipInRead/Process/Write` | When the exception is classified as skippable and the item is actually skipped |

Item listeners observe errors as they happen. SkipListener records the fault-tolerant Step's final decision to skip that item. An exception may be retried first; if the retry succeeds, the item is not skipped and `SkipListener` is not invoked for that item.

Example:

```text
Processor encounters error
       |
       v
Is exception retryable?
    /         \
  Yes          No
   |             |
   v             v
 Retry        Check skip policy
   |             |
   v             +---- Not skippable -> Step FAILED
Succeeded       |
   |             +---- Skippable and within limit
   v                         |
Continue                     v
No SkipListener          SkipListener callback
```

If an exception is both retryable and skippable, final behavior depends on retry/skip classification and fault-tolerance configuration. Once retries are exhausted and the exception is skippable, the listener records the skipped item. Design a clear policy to prevent a transient error from being skipped too early.

## 10. Distinguishing skip from filter

A processor can return `null` to intentionally exclude an item from output:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.isCancelled()) {
            return null; // Filter, not skip
        }
        return convert(input);
    };
}
```

This is **filtering**, not skipping. No exception is thrown and `SkipListener` is not invoked. Spring Batch records this via `filterCount`.

Conversely, if the processor throws `InvalidOrderException` and the Step configures that exception as skippable, the item is skipped due to an error and `onSkipInProcess()` is called. Skip counters reflect this case.

| Situation | How it is expressed | Relevant counter | SkipListener? |
|---|---|---|---|
| Intentionally excluding item | Processor returns `null` | `filterCount` | No |
| Failing item permitted to be skipped | Reader/processor/writer throws skippable exception | Per-stage skip count | Yes |
| Failing item not permitted to be skipped | Non-skippable exception or limit exceeded | Step fails | No successful skip callback for a rejected decision |
| Error retried and then succeeds | Retry succeeds | Retry metrics/logs per configuration | No |

## 11. Skip limit and exception classification policy

`skipLimit(n)` bounds the total number of skipped items in the Step. When the skip count exceeds the limit, the Step fails. For example, `skipLimit(10)` allows at most 10 skipped items; the next skip exceeds the limit and fails the Step.

You can configure skippable exception types:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skipLimit(10)
```

Or specify non-skippable exception types to exclude them from a broader group:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(DeadlockLoserDataAccessException.class)
.skipLimit(20)
```

The second example should only be used with a clear rationale. If all `Exception` types are skipped, many infrastructure or programming errors can be skipped unintentionally. Normally, declare specific business exceptions that may be skipped and let unknown errors fail the Step.

When classification rules depend heavily on exception details, data types, or context, you can implement a custom `SkipPolicy`. The policy decides whether an exception can be skipped; `SkipListener` records the item after the skip decision is accepted.

## 12. SkipListener and retry: avoiding recording at the wrong time

An item may encounter an error without necessarily being skipped. For instance, the processor hits a timeout calling an external service. Spring Batch retries the item; if the next attempt succeeds, the item is still processed normally.

Therefore, do not write the item to a dead-letter store immediately inside `ItemProcessListener.onProcessError()` if the goal is recording items that are ultimately skipped. Error callbacks can fire during an attempt that later succeeds.

`SkipListener` is better suited for recording the final outcome: the item was dropped from the pipeline under the skip policy. This is also why the framework provides a dedicated listener instead of requiring applications to infer skips from error callbacks.

When retry is enabled, distinguish:

- **Attempt error:** a single attempt encounters an error.
- **Retry:** the framework re-attempts the operation or item.
- **Skip:** the item is accepted as skipped after applying policy.
- **Step failure:** an error is neither retried nor skipped, or exceeds limits.

Retry and skip metrics should be monitored separately. A Job with many retries and zero skips may still process every item; conversely, many skips can leave business results incomplete even if the Job finishes `COMPLETED`.

## 13. Designing dead-letter records for reprocessing

If skipped items need reprocessing, error records should store enough information to reconstruct inputs and understand the failure cause.

A design can include:

| Info group | Examples |
|---|---|
| Identity | JobExecution ID, StepExecution ID, batch ID, item key |
| Source | File, line number, source system, input version |
| Failure | Stage, exception type, error code, sanitized message |
| Payload | Necessary content or reference to source record |
| Reprocess status | NEW, INVESTIGATING, READY_TO_REPLAY, REPLAYED, PERMANENT_FAILURE |
| Audit | Fixer, fix timestamp, replay execution ID |

It is not always necessary to save the entire payload in the error table. If the data contains personal or sensitive details, you can store the business key and a reference to the protected source. If storing payloads is required, apply encryption, access control, and an appropriate retention policy.

The replay workflow should create a traceable execution, keep business keys stable, and ensure an idempotent writer. Do not edit JobRepository metadata directly to force items to be reread; use a dead-letter table or managed input source.

## 14. Can listeners use annotations?

Besides implementing the interface, Spring Batch supports corresponding listener annotations:

- `@OnSkipInRead`
- `@OnSkipInProcess`
- `@OnSkipInWrite`

Example:

```java
public class AnnotatedOrderSkipListener {

    @OnSkipInRead
    public void onReadSkip(Throwable t) {
        log.warn("Read skip: {}", t.toString());
    }

    @OnSkipInProcess
    public void onProcessSkip(OrderInput item, Throwable t) {
        log.warn("Process skip for order {}: {}",
                item.orderId(), t.toString());
    }

    @OnSkipInWrite
    public void onWriteSkip(Order item, Throwable t) {
        log.warn("Write skip for order {}: {}",
                item.orderId(), t.toString());
    }
}
```

Register the object containing the annotated methods on the Step with `.listener(annotatedOrderSkipListener)`. Method parameters must match the callback type: read takes the exception; process and write take the item and the exception. The `SkipListener` interface is usually easier to read and more type-safe when implementing all three callbacks.

## 15. Thread safety and parallel Step execution

If a Step or Job uses parallel processing, the listener bean may be invoked from multiple threads. Do not store the current item or current exception in a mutable field of a singleton listener:

```java
// Unsafe when multiple threads invoke the listener concurrently
private String currentOrderId;
```

Use local variables inside callbacks and pass data directly to services. The repository storing skip records must tolerate concurrent writes; include an appropriate unique key to avoid duplicate records upon retries or when the system re-emits the same event.

If you need to record Job name, Step name, or execution ID, obtain the current Step context via an appropriate scope or `StepSynchronizationManager` while the callback executes. Avoid holding a `StepExecution` or one thread's context in a field for use on another thread.

When multiple workers write to the same dead-letter table, add indexes on batch ID, execution ID, and item key to support lookups, and design a business unique key if an item should have only one skip record per logical run.

## 16. Logging, metrics, and security

SkipListener is a good place to produce logs or metrics for skipped items. Useful metrics include:

- Total skips broken down by READ, PROCESS, and WRITE.
- Skip rate relative to total items read.
- Common exception groups.
- Top source files or source systems with errors.
- Count of items awaiting replay and backlog age.
- Associated JobExecution/StepExecution.

Do not log full raw lines or objects if they contain emails, phone numbers, account details, or sensitive data. Log only the business key and minimal information needed for investigation. Exception messages can contain SQL, internal paths, or input values; sanitize them before storing where many users have access.

If the skip rate exceeds a business threshold, you can let the Step fail via `skipLimit` or check the error rate in a summary Step. A `COMPLETED` Job does not mean error-free data; evaluate both skip count and skip rate before publishing results.

## 17. Testing SkipListener

Test each callback as well as overall Step behavior:

1. Reader throws a skippable exception: verify `onSkipInRead()` is called.
2. Processor throws a skippable exception: verify the input item is passed to `onSkipInProcess()`.
3. Writer fails to write a skippable item: verify `onSkipInWrite()` receives the correct output item.
4. Exception is retried and then succeeds: verify the item is not recorded as skipped.
5. Processor returns `null`: verify this is a filter and SkipListener is not called.
6. Exceeding `skipLimit`: verify the Step fails and does not keep skipping indefinitely.
7. Failing to persist a dead-letter record: verify transaction behavior and Step status match the desired policy.
8. Parallel execution: verify the listener and repository have no race conditions or unintended duplicate writes.

You can use a mock service to verify callbacks and Spring Batch test utilities to run the Job/Step in a test environment. For write skips, also verify that the writer can be re-invoked during item isolation and that all write operations are retry-safe.

## 18. Common mistakes

**Registering SkipListener without configuring skip:** the listener alone does not permit skipping exceptions. `.faultTolerant()` and `.skip(...)` rules or a `SkipPolicy` are required.

**Confusing errors with skips:** an exception occurring does not mean the item was skipped. A retry may succeed or the Step may fail.

**Using `onSkipInRead()` to get an item:** this callback receives no item because the reader may not have constructed an object. Extract position or data from the exception if available.

**Using ItemProcessListener to write final dead-letter records:** process error callbacks can occur during a retry attempt that later succeeds. Use SkipListener to record items that are actually skipped.

**Treating filter as skip:** returning `null` from a processor is a filter, not an exception skip; the listener is not called.

**Skipping all exceptions:** this can conceal infrastructure errors, programming bugs, or data-loss errors. Only allow skipping exceptions with clear business meaning.

**Ignoring skip limit:** the limit lets the Job stop when corrupt data exceeds acceptable bounds. Do not let a Job complete with an uncontrolled error rate.

**Calling APIs or sending emails directly in callbacks:** external side effects do not automatically roll back with the transaction. Use an outbox or idempotency when delivery guarantees are needed.

**Logging sensitive payloads:** this can expose data. Only store sanitized minimal info and business keys.

## Conclusion

`SkipListener` records items that Spring Batch has decided to skip in a fault-tolerant Step. `onSkipInRead()` receives the exception when an item cannot be read; `onSkipInProcess()` receives the input item and exception when processing fails; `onSkipInWrite()` receives the output item and exception when writing fails. The listener is invoked only when an exception is actually skipped under policy and limits, not on every error, successful retry, or filtered item. Store the business key, stage, and cause in a dead-letter/audit store, understand that callbacks fire right before the chunk transaction commits, and ensure error persistence is safe under retries or parallel execution. Configuring bounded skips and monitoring skip rates enables the Job to continue processing valid data while retaining the ability to investigate and reprocess failing items.
