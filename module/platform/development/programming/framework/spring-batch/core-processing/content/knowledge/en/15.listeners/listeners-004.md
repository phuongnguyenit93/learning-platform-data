# ItemReadListener

In Spring Batch, `ItemReader` is responsible for retrieving individual items from a data source. When you need to observe the reading process, write logs, measure duration, or record read errors, you can use **ItemReadListener**. This listener provides callbacks before the reader is called, after an item is read successfully, and when the reader throws an exception.

`ItemReadListener` is part of the listener mechanism in a chunk-oriented Step. It adds observability around reading without embedding all that logic inside the reader. The listener does not replace `ItemReader`, does not transform items, and does not itself decide whether an error is skipped or retried.

## 1. Where Does ItemReadListener Sit in Chunk Processing?

A chunk-oriented Step typically follows this flow:

~~~text
ItemReader
    |
    +-- beforeRead()
    |
    +-- reader.read()
    |
    +-- afterRead(item) if an item is returned
    |
    +-- or onReadError(exception) if reader throws an error
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

`ItemReadListener` observes the boundary of `ItemReader` invocations. The three callbacks align with the read lifecycle:

- **beforeRead()**: invoked before Spring Batch calls `read()` on the reader.
- **afterRead(item)**: invoked after the reader returns an item successfully.
- **onReadError(exception)**: invoked when the reader throws an exception during reading.

The reader returns `null` to signal the end of data. `null` is not an item forwarded to the processor or writer, so there is no item to handle in `afterRead`. `beforeRead` may still be called for the final read attempt used to detect end-of-data.

The listener does not decide which item the reader reads or in what order. Those responsibilities still belong to `ItemReader` and the data source configuration.

## 2. The ItemReadListener Contract

The `ItemReadListener` interface has three methods:

~~~java
public interface ItemReadListener<T> {

    void beforeRead();

    void afterRead(T item);

    void onReadError(Exception ex);
}
~~~

The listener is parameterized by the item type returned by the reader. If the reader reads `OrderInput`, the listener should implement `ItemReadListener<OrderInput>`.

### beforeRead()

This callback runs before each reader invocation. It can be used to:

- Log the start of a read operation.
- Start measuring read time if there is a mechanism to store the corresponding timestamp.
- Track how many times the reader has been invoked.
- Add diagnostic context for a specific read source.

Do not use `beforeRead()` to alter the state of the data source or pre-read items yourself. The reader must remain the sole component responsible for fetching items.

### afterRead(item)

This callback receives the item just read successfully. It can be used to:

- Log the item's identifier.
- Count items returned by the reader.
- Record data size or type.
- Emit metrics for pipeline observability.

Do not modify the item inside the callback. If you need to normalize or transform data, use `ItemProcessor` to keep responsibilities clear and easy to test.

### onReadError(exception)

This callback receives the exception thrown by the reader. It can be used to:

- Log the error type and stack trace.
- Attach read source or Job/Step metadata to logs.
- Increment read error metrics.
- Send observability signals to a monitoring system.

`onReadError` only reports that a read encountered an exception. It does not itself decide whether the exception is retried, skipped, or fails the Step. That decision depends on the fault-tolerant mechanism, retry/skip policies, and exception type.

## 3. Writing an ItemReadListener

Example listener for a reader reading orders from a file:

~~~java
import org.springframework.batch.core.ItemReadListener;

public class OrderReadListener
        implements ItemReadListener<OrderInput> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderReadListener.class);

    @Override
    public void beforeRead() {
        log.debug("About to read an order record");
    }

    @Override
    public void afterRead(OrderInput item) {
        log.debug("Read orderId={}", item.getOrderId());
    }

    @Override
    public void onReadError(Exception ex) {
        log.error("Failed to read an order record", ex);
    }
}
~~~

`beforeRead` and `afterRead` observe the normal read path. `onReadError` logs the exception so operators know what issue the reader encountered.

In production systems, log identifiers and technical details sufficient for investigation. Avoid logging full objects if items contain personal information, financial data, or large payloads. Never log credentials, tokens, or sensitive content.

## 4. Registering the Listener on a Step

You can register the listener directly when configuring the Step. Example for Spring Batch 5 and later:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        OrderReadListener orderReadListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener(orderReadListener)
            .build();
}
~~~

Calling `listener(orderReadListener)` registers the listener on the Step. Spring Batch invokes the appropriate callbacks when the reader executes.

The listener can be declared as a bean:

~~~java
@Bean
public OrderReadListener orderReadListener() {
    return new OrderReadListener();
}
~~~

When sharing a listener across multiple Steps, ensure the listener does not hold per-run state if the bean can be used concurrently. If per-`StepExecution` information is needed, design the scope and state access accordingly.

## 5. Using Annotations Instead of the Interface

Spring Batch also supports listener methods through annotations. You can write a POJO with methods annotated with:

- `@BeforeRead`
- `@AfterRead`
- `@OnReadError`

Example:

~~~java
public class OrderReadAnnotationListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderReadAnnotationListener.class);

    @BeforeRead
    public void beforeRead() {
        log.debug("Starting to read an order");
    }

    @AfterRead
    public void afterRead(OrderInput item) {
        log.debug("Read orderId={}", item.getOrderId());
    }

    @OnReadError
    public void onReadError(Exception exception) {
        log.error("Order read failed", exception);
    }
}
~~~

The POJO listener is registered on the Step with `listener(...)` just like an interface-based listener:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(orderReadAnnotationListener)
        .build();
~~~

Annotations make listeners concise when only a few callbacks are needed. The interface is suited when you want an explicit contract, type parameters, or structured logic. Pick one approach consistently within the same component so code remains easy to read.

## 6. ItemReadListener and Read Errors

Read errors can arise in many places:

- Failing to open a file or resource.
- A CSV line with invalid formatting or type conversion errors.
- Interrupted database connection.
- Reader query failure.
- Source data not matching the structure expected by the reader.
- Source API returning an error or timing out.

When the reader throws an exception during `read()`, `onReadError` is called to observe the error. The exception then continues through the Step's execution handling. Depending on configuration, the Step may fail, retry, or skip the error.

Example:

~~~java
public class OrderReadListener
        implements ItemReadListener<OrderInput> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderReadListener.class);

    @Override
    public void beforeRead() {
        log.debug("Reading next order input");
    }

    @Override
    public void afterRead(OrderInput item) {
        log.debug("Successfully read orderId={}", item.getOrderId());
    }

    @Override
    public void onReadError(Exception ex) {
        log.error(
                "Reader failed; exceptionType={}",
                ex.getClass().getSimpleName(),
                ex);
    }
}
~~~

Do not catch exceptions inside the listener and treat the read as successful. The listener should observe and let the Step apply its error policy. If a callback itself throws an exception, an exception from the listener can also interrupt the Step; therefore, callbacks should be short, stable, and free of unnecessarily failure-prone operations.

## 7. Distinguishing ItemReadListener and SkipListener

These two listeners are related when handling read errors, but have different purposes:

| Listener | Callback | Meaning |
| --- | --- | --- |
| `ItemReadListener` | `onReadError(Exception ex)` | Observes an exception occurring during a read |
| `SkipListener` | `onSkipInRead(Throwable t)` | Invoked when a read exception is actually classified and handled as a skip |

`onReadError` does not mean the item was skipped. The exception could fail the Step or be retried. `onSkipInRead` reflects only cases accepted by the skip policy.

Example registering a skip listener:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable t) {
        // Record read error when no item was successfully created.
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        // Record invalid input in the processor.
    }

    @Override
    public void onSkipInWrite(Order item, Throwable t) {
        // Record error when writing output.
    }
}
~~~

The Step can configure skips for a specific read exception:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .listener(orderReadListener)
        .listener(orderSkipListener)
        .build();
~~~

The example allows skipping up to 50 parse errors of the configured type. Identify the exact exceptions thrown by the reader in your application and only skip data errors that business requirements allow ignoring. Do not skip every `Exception`, as that can hide system failures.

For read errors, there is often no valid item to pass to `onSkipInRead`; the listener receives the exception and can extract line or source details if the exception carries them. With `FlatFileParseException`, the input line and line number may be available for reconciliation.

## 8. ItemReadListener Does Not Replace the Retry Policy

The retry policy decides whether an error is retried and how many times at most. `ItemReadListener` only provides observation callbacks.

Example of a Step configured with retry for transient data access errors:

~~~java
return new StepBuilder("readOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .listener(orderReadListener)
        .build();
~~~

If the reader throws `TransientDataAccessException` and the error is retried, the read-error callback may be called for the failing read attempt. When a subsequent attempt succeeds, `afterRead` is called for the returned item.

Do not use a listener to loop and re-invoke the reader or implement custom retries with your own loop. Doing so can break the transaction management, retry context, and metadata provided by Spring Batch.

Retries can also cause a read operation to execute again. The reader should behave appropriately on re-reads, especially if the data source is stateful or modified between attempts.

## 9. ItemReadListener and Transactions

In a chunk-oriented Step, read callbacks occur during chunk processing and typically execute within the chunk's transaction. Therefore, the listener should avoid long auxiliary operations or creating external side effects outside the transaction.

For example, if `afterRead` calls a REST API for every item, chunk processing time can grow and the database transaction stays open while waiting on the network. If the API times out, the callback can fail the Step even though reading the item succeeded.

Practical principles:

- Keep callbacks short, preferring lightweight logging and metrics.
- Do not perform unnecessary database writes inside callbacks.
- Do not make synchronous remote service calls per item if they can be handled in another step.
- Do not assume external side effects will roll back with the Step transaction.
- If durable auditing is needed, choose appropriate transaction boundaries and an outbox mechanism.

A listener is not the right place to implement critical business logic whose outcome must commit alongside the item. Place that logic in a processor, writer, or service with explicit transactions.

## 10. Thread Safety and Listener Scope

In a sequential Step, callbacks are normally invoked on a single processing thread. When a Step runs multi-threaded, however, the reader or parts of the pipeline can be called from multiple threads depending on configuration.

If a listener holds state such as a counter, item list, or timestamp in a field, threads can access it concurrently. Incrementing a plain `long` variable is not thread-safe when multiple threads update it simultaneously.

Example of a stateful listener prone to race conditions:

~~~java
public class CountingReadListener
        implements ItemReadListener<OrderInput> {

    private long readCount;

    @Override
    public void afterRead(OrderInput item) {
        readCount++;
    }
}
~~~

If callbacks run concurrently, updates can be lost. If you genuinely need a custom counter in the listener, use `AtomicLong` or appropriate synchronization:

~~~java
private final AtomicLong readCount = new AtomicLong();

@Override
public void afterRead(OrderInput item) {
    readCount.incrementAndGet();
}
~~~

However, if the goal is simply to know how many items were read, prefer the counters on `StepExecution` or metrics provided by Spring Batch rather than maintaining a parallel counter.

Do not assume `@StepScope` automatically makes a listener safe for every concurrency model. Scope controls bean lifecycle; thread safety still depends on how the listener is invoked and what state it holds. Stateless listeners are generally easier to use safely.

## 11. Recording Read Metrics

`ItemReadListener` can be used to emit metrics or logs, though `StepExecution` already provides useful counters:

- `readCount`: number of items read.
- `readSkipCount`: number of read errors skipped.
- `filterCount`: number of items filtered by the processor.
- `writeCount`: number of items written.
- `processSkipCount` and `writeSkipCount`: number of skipped errors at the respective stages.

These counters help distinguish the items returned by the reader from the items ultimately written. For example, if `readCount` is high but `writeCount` is low, the processor may have filtered many items or skips may have occurred.

You can inspect `StepExecution` via Step lifecycle listeners or `JobExplorer`. Do not rely solely on the number of `beforeRead` calls to infer valid items, because the final read returning `null` may also be preceded by the pre-read callback.

If you need dedicated read latency metrics, you can measure the elapsed interval between pre- and post-read callbacks. For multi-threaded listeners, do not use a single shared timestamp variable across all reads; use per-thread state or thread-safe instrumentation.

## 12. Complete Example: Configuring Reader and Listener

The following example illustrates a Step that reads a file, transforms data, and writes to a destination:

~~~java
@Configuration
public class OrderImportConfiguration {

    @Bean
    public OrderReadListener orderReadListener() {
        return new OrderReadListener();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<OrderInput> orderReader,
            ItemProcessor<OrderInput, Order> orderProcessor,
            ItemWriter<Order> orderWriter,
            OrderReadListener orderReadListener) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<OrderInput, Order>chunk(100, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .listener(orderReadListener)
                .build();
    }
}
~~~

The listener observes three points:

1. Before each call to the reader.
2. After the reader returns an `OrderInput`.
3. When the reader throws an exception.

It does not alter data and does not decide how errors are handled. Those decisions belong to the reader, processor, writer, and the Step's fault-tolerant configuration.

## 13. Testing ItemReadListener

You can test the listener in isolation by calling callbacks directly:

~~~java
class OrderReadListenerTest {

    @Test
    void afterReadAcceptsReadItem() {
        OrderReadListener listener = new OrderReadListener();
        OrderInput input = new OrderInput();
        input.setOrderId("ORD-1001");

        assertDoesNotThrow(() -> listener.afterRead(input));
    }

    @Test
    void onReadErrorAcceptsReaderException() {
        OrderReadListener listener = new OrderReadListener();
        Exception exception = new IllegalStateException("Read failed");

        assertDoesNotThrow(() -> listener.onReadError(exception));
    }
}
~~~

If the listener emits metrics or writes audit records, you can mock collaborators to verify the callback invokes the right dependency with the expected data.

At the Step test level, verify:

- `beforeRead` is called when the reader is asked to read.
- `afterRead` receives the exact item returned by the reader.
- `onReadError` receives the exception from the reader.
- Read errors are handled according to the skip/retry policy.
- `onSkipInRead` is called only when an exception is actually skipped.
- The listener does not alter items or business outcomes.

Do not only test callbacks manually and conclude the entire Step wiring is correct. A Step test with a stub or mock reader confirms that the listener is registered and invoked by the framework at the right points.

## 14. Common Mistakes

### Using afterRead to transform items

A listener should only observe. If you need to modify an item, use `ItemProcessor` so transformation logic is explicit.

### Thinking onReadError means the item was skipped

The callback only reports a read error. The exception may fail the Step or be retried. Use `SkipListener.onSkipInRead` to record items that were actually skipped.

### Catching exceptions and hiding errors from the Step

If a listener swallows errors or interferes with execution flow, the Step status may fail to reflect real issues. Let the reader and fault-tolerant policy handle exceptions.

### Logging the entire item

Payloads can be large or contain sensitive data. Log only identifiers and details necessary for troubleshooting.

### Making API calls inside afterRead

Calling a remote service per item slows down the pipeline and can keep transactions open. Move that business work to a processor/writer or a dedicated Step.

### Holding non-thread-safe state

Shared listeners in multi-threaded environments can suffer race conditions. Prefer stateless listeners or appropriate synchronization.

### Using a listener instead of a reader

A listener is not the place to fetch data, perform custom retries, or directly drive the read source. Those responsibilities belong to `ItemReader` and Step execution.

### Assuming callbacks are called once per business item

Retries, rollbacks, and restarts can cause a read operation to be retried. Listeners observe actual invocations; do not use callbacks as the sole source for generating durable business sequence numbers.

## 15. How to Design an ItemReadListener

When adding a listener to a Step, determine:

1. Do you need to observe before reading, after reading, or on read errors?
2. What details are sufficient for investigation without exposing sensitive payloads?
3. Are custom metrics needed, or do `StepExecution` counters already suffice?
4. Which read errors should be retried, which should be skipped, and which must fail the Step?
5. Is a `SkipListener` needed to store rejected records?
6. Does the callback perform I/O or long-running side effects?
7. Does the listener hold state, and can it be called concurrently?
8. Can the listener be unit-tested independently and verified via Step wiring tests?

A well-designed `ItemReadListener` keeps callbacks small, does not modify data, does not swallow exceptions, and provides sufficient observability to operate the Step.

## Conclusion

`ItemReadListener` provides three callbacks—`beforeRead`, `afterRead`, and `onReadError`—to observe the item read lifecycle in Spring Batch. It is suitable for logging, metrics, and error diagnostics around `ItemReader`. The listener does not replace retry/skip policies: `onReadError` only records errors, while `SkipListener` confirms exceptions that were actually skipped. Keep callbacks short, avoid mutating items or unnecessary side effects, and ensure thread safety when Steps run concurrently.
