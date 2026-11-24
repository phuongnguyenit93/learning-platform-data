# ItemProcessListener in Spring Batch

In a chunk-oriented Step, **ItemProcessor** receives each item from the reader, validates or transforms it, and returns the result to the writer. When you need to observe the processing of individual items, Spring Batch provides **ItemProcessListener**. This listener lets you run logic before the processor is invoked, after the processor returns a result, or when the processor throws an exception.

`ItemProcessListener` is useful for logging, metrics, auditing, and tracking cases where items are filtered or fail processing. It does not replace `ItemProcessor` and is not the right place for data transformation rules. Understanding the exact timing of each callback helps the application record accurate statuses, especially when the processor returns `null`, when the Step uses skip/retry, or when the Job runs concurrently.

## 1. What is ItemProcessListener?

`ItemProcessListener` is an item-level listener invoked around `ItemProcessor` processing. The interface has three main callbacks:

~~~java
public interface ItemProcessListener<T, S> extends StepListener {

    void beforeProcess(T item);

    void afterProcess(T item, S result);

    void onProcessError(T item, Exception e);
}
~~~

Where:

- `T` is the input item type provided by the reader to the processor.
- `S` is the result type returned by the processor to the writer.
- `beforeProcess(...)` runs before invoking the processor for an item.
- `afterProcess(...)` runs after the processor returns a result.
- `onProcessError(...)` runs when processing throws an exception.

For example, an order import Step may read `OrderInput`, convert it to `Order` in the processor, and write the result to the database. The listener can log the order ID before processing, record whether the item was processed successfully or filtered, and log the error when the processor fails.

~~~mermaid
flowchart TD
    A["ItemReader returns item"] --> B["ItemProcessListener.beforeProcess"]
    B --> C["ItemProcessor.process(item)"]
    C --> D{"Result"}
    D -- "Output" --> E["ItemProcessListener.afterProcess(item, output)"]
    D -- "null" --> F["ItemProcessListener.afterProcess(item, null)"]
    C -- "Exception" --> G["ItemProcessListener.onProcessError(item, exception)"]
    E --> H["Chunk continues"]
    F --> H
    G --> I["Step handles error per policy"]
~~~

The listener observes each processor invocation. It does not decide whether an item is written or discarded, nor does it handle exceptions in place of the Step.

## 2. Three Callbacks of ItemProcessListener

### beforeProcess(item)

`beforeProcess` is invoked before Spring Batch calls `ItemProcessor.process(item)` for an item.

Suitable tasks include:

- Logging the start of processing for an item.
- Incrementing a metric for started processing attempts.
- Attaching a correlation ID or trace metadata to the logging context.
- Recording a start timestamp if measuring processing duration.
- Capturing item identifier details for troubleshooting.

Example:

~~~java
@Override
public void beforeProcess(OrderInput item) {
    log.debug(
        "Starting to process orderId={}",
        item.orderId()
    );
}
~~~

Do not place business logic such as credit limit checks, order state changes, or payment service calls in this callback. Those rules belong in the processor or a business service invoked by the processor.

### afterProcess(item, result)

`afterProcess` is invoked after the processor returns a result. The `result` parameter can be an output object or `null` if the processor intentionally filtered the item.

Example:

~~~java
@Override
public void afterProcess(OrderInput item, Order result) {
    if (result == null) {
        log.info(
            "Order filtered out orderId={}",
            item.orderId()
        );
        return;
    }

    log.debug(
        "Successfully processed orderId={}",
        item.orderId()
    );
}
~~~

Important point: the processor returning `null` is a valid processing outcome used to filter an item. In that case, `afterProcess` is still invoked with a `null` result. The item was read and processed but is not forwarded to the writer.

If the processor returns an output object, `afterProcess` receives that object. The listener can record the outcome or metrics, but cannot alter the object returned to the writer. The callback return type is `void`.

### onProcessError(item, exception)

`onProcessError` is invoked when item processing raises an exception.

~~~java
@Override
public void onProcessError(
        OrderInput item,
        Exception exception) {

    log.warn(
        "Failed to process orderId={}",
        item.orderId(),
        exception
    );
}
~~~

The callback receives the input item and the exception. This is the right place to log the item identifier and error type, helping pinpoint which record caused the failure.

The listener must not swallow the exception or treat the item as processed successfully. The exception continues into Spring Batch's error-handling mechanism. Depending on configuration, the Step may retry, skip, or fail.

If the listener callback itself throws an exception, it can disrupt the Step. Therefore, logging and metrics logic inside a listener should be simple, resilient, and free of unintended errors.

## 3. Distinguishing Normal Output, Filtering, and Process Errors

The three outcomes of a processor have distinct meanings:

| Result from Processor | Related Callback | Meaning |
|---|---|---|
| Returns object | `afterProcess(item, result)` | Item is forwarded to the writer |
| Returns `null` | `afterProcess(item, null)` | Item is filtered out, not forwarded to the writer |
| Throws exception | `onProcessError(item, exception)` | Processing failed; Step applies policy |

Processor example:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return null;
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new IllegalArgumentException(
                "Invalid amount"
            );
        }

        return new Order(
            input.orderId(),
            input.customerId(),
            input.amount()
        );
    };
}
~~~

The listener can distinguish:

- Cancelled order: the processor returns `null`, and `afterProcess` receives `null`.
- Valid order: the processor returns `Order`, and `afterProcess` receives the output.
- Invalid amount: the processor throws an exception, and `onProcessError` is called.

### Filtering is not an exception

If an item is excluded by normal business rules, the processor should return `null`. Do not throw an exception just to indicate that an item does not need to be written.

For example, a cancelled order may be a valid business case for filtering. Throwing an exception forces the application to configure skip/retry and can unnecessarily inflate error metrics.

### An error is not filtering

If data cannot be processed due to invalid format or a mandatory rule violation, do not return `null` to hide the error. Throw an appropriate exception so the Step records the failure and applies its policy.

Clearly distinguishing these three cases ensures `filterCount`, process skip count, and error logs accurately reflect the true nature of the data.

## 4. Registering the Listener on a Step

In Spring Batch 5, you can register `ItemProcessListener` directly when building the Step using `.listener(...)`.

Example of a listener implementing the interface:

~~~java
@Bean
ItemProcessListener<OrderInput, Order> orderProcessListener() {
    return new ItemProcessListener<>() {

        @Override
        public void beforeProcess(OrderInput item) {
            log.debug("Starting orderId={}", item.orderId());
        }

        @Override
        public void afterProcess(OrderInput item, Order result) {
            if (result == null) {
                log.info("Filtered orderId={}", item.orderId());
            } else {
                log.debug("Processed orderId={}", item.orderId());
            }
        }

        @Override
        public void onProcessError(
                OrderInput item,
                Exception exception) {
            log.warn(
                "Error processing orderId={}",
                item.orderId(),
                exception
            );
        }
    };
}
~~~

Attach the listener to the Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        ItemProcessListener<OrderInput, Order> orderProcessListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(orderProcessListener)
        .build();
}
~~~

The listener's generic types should match the input and output types of the processor. In the example, the listener takes `OrderInput` and `Order`, matching `.<OrderInput, Order>chunk(...)`.

If a Step has no `ItemProcessor`, `ItemProcessListener` has no item processing invocations to observe. When you need to monitor reading or writing, use the corresponding `ItemReadListener` or `ItemWriteListener`.

## 5. Using Annotations Instead of the Interface

Spring Batch also supports declaring listeners via annotations. This is useful when grouping callbacks in a class without directly implementing the interface.

~~~java
public class OrderProcessAuditListener {

    @BeforeProcess
    public void before(OrderInput item) {
        log.debug("Starting orderId={}", item.orderId());
    }

    @AfterProcess
    public void after(OrderInput item, Order result) {
        if (result == null) {
            log.info("Order filtered orderId={}", item.orderId());
        } else {
            log.debug("Order processed orderId={}", item.orderId());
        }
    }

    @OnProcessError
    public void onError(OrderInput item, Exception exception) {
        log.warn(
            "Error processing orderId={}",
            item.orderId(),
            exception
        );
    }
}
~~~

Register the listener class on the Step:

~~~java
@Bean
OrderProcessAuditListener orderProcessAuditListener() {
    return new OrderProcessAuditListener();
}
~~~

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .listener(orderProcessAuditListener)
    .build();
~~~

The corresponding annotations:

| Annotation | Invocation Timing | Parameters |
|---|---|---|
| `@BeforeProcess` | Before processor | Input item |
| `@AfterProcess` | After processor returns result | Input item and result |
| `@OnProcessError` | When processor throws exception | Input item and exception |

Method signatures must be compatible with the corresponding callbacks. When using annotations, make methods `public` and declare explicit parameter types so Spring Batch can detect and invoke the right callbacks.

### Choosing interface or annotations?

Use the interface when you want an explicit Java contract, easy mocking, and compiler verification of all three callbacks. Use annotations when you want a class to declare only the callbacks it actually needs or when organizing listeners by annotation groups.

Both approaches are listener registration mechanisms. Do not register the same logic twice via both interface and annotations, as callbacks could run repeatedly.

## 6. ItemProcessListener and SkipListener

`ItemProcessListener` observes every time the processor is called. `SkipListener` reflects items actually skipped due to a skip policy.

The two listeners have different purposes:

| Listener | Callback | Meaning |
|---|---|---|
| `ItemProcessListener` | `onProcessError(item, exception)` | Processor encountered an exception during a call |
| `SkipListener` | `onSkipInProcess(item, exception)` | Item was skipped in the process phase per policy |
| `ItemProcessListener` | `afterProcess(item, null)` | Processor intentionally filtered the item |
| `SkipListener` | `onSkipInRead(...)` | Item was skipped due to a read error |
| `SkipListener` | `onSkipInWrite(...)` | Item was skipped due to a write error |

For example, the processor throws an exception due to a retryable data issue. On each failed processor call, `onProcessError` can be called. If the exception is ultimately skipped per configuration, `SkipListener` records the skipped item.

Example `SkipListener`:

~~~java
@Bean
SkipListener<OrderInput, Order> orderSkipListener(
        RejectedOrderService rejectedOrderService) {

    return new SkipListener<>() {

        @Override
        public void onSkipInProcess(
                OrderInput item,
                Throwable throwable) {
            rejectedOrderService.record(
                item.orderId(),
                throwable.getMessage()
            );
        }

        @Override
        public void onSkipInRead(Throwable throwable) {
            // Record read error if needed.
        }

        @Override
        public void onSkipInWrite(
                Order item,
                Throwable throwable) {
            // Record write error if needed.
        }
    };
}
~~~

Attach `SkipListener` to the Step similarly using `.listener(...)`.

### Why not use onProcessError instead of SkipListener?

`onProcessError` indicates that a single call to the processor failed. It does not confirm that the item will ultimately be skipped. The item may be retried and processed successfully on the next attempt.

`SkipListener` is appropriate when recording the final skip decision. If you write a rejection record or send a notification on every `onProcessError`, the same item could be recorded multiple times due to retries.

## 7. How Does the Listener Behave with Retry?

When a Step is configured with retry, the processor may be called again for the same item. `ItemProcessListener` callbacks are tied to each processor invocation.

Example of an item hitting a transient error on the first two attempts and then succeeding:

~~~text
Attempt 1:
  beforeProcess(item)
  process(item) -> exception
  onProcessError(item, exception)

Attempt 2:
  beforeProcess(item)
  process(item) -> exception
  onProcessError(item, exception)

Attempt 3:
  beforeProcess(item)
  process(item) -> output
  afterProcess(item, output)
~~~

This is why the listener must distinguish **processing attempt count** from **final successful item count**.

If you increment a success counter in `beforeProcess`, the metric will count failed attempts too. If you write a "processed" audit in `onProcessError`, the information will be wrong. Place each metric in the right callback:

- Started attempts: `beforeProcess`.
- Times processor returned a result: `afterProcess`.
- Times processor returned `null`: `afterProcess` with `null` result.
- Processing exceptions: `onProcessError`.
- Finally skipped items: `SkipListener`.

If you want to count unique logical items, use an item key and an appropriate deduplication strategy. You cannot use callback counts as unique item counts when retries occur.

## 8. The Listener Does Not Replace ItemProcessor

`ItemProcessListener` only receives notifications about processing. It does not return output and has no mechanism to modify the result produced by the processor.

Do not write business logic inside a listener, such as:

- Converting amounts.
- Normalizing customer IDs.
- Deciding whether an item is valid.
- Calculating taxes or fees.
- Changing order status.
- Calling services to update business data.

Those tasks belong in `ItemProcessor` or a business service invoked by the processor.

Example of separating responsibilities:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor(
        OrderValidationService validationService) {

    return input -> {
        validationService.validate(input);

        if ("CANCELLED".equals(input.status())) {
            return null;
        }

        return new Order(
            input.orderId(),
            input.customerId().trim(),
            input.amount().setScale(2, RoundingMode.HALF_UP)
        );
    };
}
~~~

The listener only observes the result:

~~~java
@Override
public void afterProcess(OrderInput item, Order result) {
    if (result == null) {
        log.info("Order filtered out orderId={}", item.orderId());
    } else {
        log.debug("Order ready to write orderId={}", item.orderId());
    }
}
~~~

This separation keeps business logic easy to test in the processor while the listener focuses on observability and operational integration.

## 9. Logging and Auditing in a Listener

A listener is a convenient place to record events around processing. However, each item can trigger multiple callbacks and a Job can process millions of items. Overly verbose logging can inflate log volume and degrade performance.

### Log identifiers

Prefer logging business IDs or correlation IDs rather than the whole object:

~~~java
@Override
public void beforeProcess(OrderInput item) {
    log.debug(
        "Processing orderId={}",
        item.orderId()
    );
}
~~~

Avoid logging full item contents if they include email addresses, phone numbers, payment details, or personal data.

### Log errors with context

~~~java
@Override
public void onProcessError(
        OrderInput item,
        Exception exception) {

    log.error(
        "Process failed for orderId={}, exceptionType={}",
        item.orderId(),
        exception.getClass().getSimpleName(),
        exception
    );
}
~~~

Useful details include the item ID, Step name, batch ID or `JobExecution` ID if safely accessible, exception type, and an appropriate stack trace.

Do not log tokens, secrets, or full sensitive parameters.

### Auditing differs from logging

Logs serve operations and diagnostics. Audits are typically structured data that must be queried and retained according to policy.

If processed items need auditing, define clearly which events are stored:

- Processing attempt started.
- Processor returned output.
- Item was filtered.
- A processing attempt failed.
- Item was actually skipped.
- Item was committed successfully by the writer.

`ItemProcessListener` only observes up to the processor's result. It does not prove the item was written by the writer or that the transaction committed. If auditing requires confirmed writes, use `ItemWriteListener` or an audit mechanism tied to the transaction/target store.

## 10. Measuring Per-Item Processing Time

You can use a listener to measure how long the processor takes. However, do not store the start timestamp in a single shared field if the Step can process concurrently.

For a single-threaded Step, a simple option is a per-item structure or `ThreadLocal`. A safer approach, however, is using timer-capable metrics or recording timing directly in a processor decorator.

Illustrative listener example for a single-threaded Step:

~~~java
public class TimedOrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    private long startedAt;

    @Override
    public void beforeProcess(OrderInput item) {
        startedAt = System.nanoTime();
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        long elapsed = System.nanoTime() - startedAt;

        log.debug(
            "orderId={}, processTimeNanos={}",
            item.orderId(),
            elapsed
        );
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        long elapsed = System.nanoTime() - startedAt;

        log.warn(
            "orderId={}, process failed after {} ns",
            item.orderId(),
            elapsed
        );
    }
}
~~~

This example is suitable only for sequential processing, because the `startedAt` field is overwritten if multiple threads call the listener simultaneously. For concurrent processing, use timer metrics or store timestamps in a thread-safe per-thread/per-item structure.

If the processor is retried, the duration above measures each attempt. To measure total time from the first attempt until completion or skip, you need a dedicated tracking mechanism with explicit retry state handling.

## 11. Listener and Transaction Boundaries

`ItemProcessListener` is invoked within the chunk processing flow. Thus, callbacks usually run inside the chunk's transaction scope, though effects outside the transaction do not automatically roll back.

For example, a listener writing audit records via `JdbcTemplate` using the same `DataSource` as the Step can participate in the current transaction. If the chunk rolls back, that audit record can also roll back.

Conversely, if the listener:

- Sends an email.
- Calls an HTTP API.
- Sends a message to a non-transactional broker.
- Writes a file to the filesystem.
- Writes to a database in an independent transaction.

then that side effect can persist even if the chunk rolls back or the processor is retried.

### Do not send success notifications in afterProcess

`afterProcess` only indicates that the processor returned a result. The writer may fail afterward, or the chunk transaction may roll back.

If you send an "order imported successfully" email directly in `afterProcess`, the notification could be sent even though the order was never durably persisted.

If notifications are needed only after data commits, use an appropriate post-commit mechanism, the outbox pattern, or a separate publishing Step after the data-writing Step completes.

### Do not write success audits before commit

Similarly, `afterProcess` does not prove the writer persisted the item successfully. If audits must reflect committed data, place the audit in the same transaction as the writer or derive it from committed state.

## 12. Exception Handling in a Listener

The `onProcessError` callback receives the exception raised during processing. The listener should record it and let Spring Batch continue handling the exception.

Avoid doing this:

~~~java
@Override
public void onProcessError(OrderInput item, Exception exception) {
    log.error("Processing error", exception);
    // There is no way to turn an error into success via this callback alone.
}
~~~

Do not try to fix the item or re-invoke the processor yourself inside the callback. Retries belong to the Step's fault-tolerant configuration.

### Listeners can also throw exceptions

If a listener calls an external audit or metrics service and that service fails, an exception from the listener can fail the Step. Therefore:

- Prefer fast, simple operations.
- Do not make slow API calls in callbacks for each item.
- Use timeouts when calling external services.
- Handle telemetry errors under a separate policy if possible.
- Do not let logging failures break data processing when logging is not a strict business requirement.

If auditing is mandatory, design it as part of the data flow with explicit transactions and retries rather than relying on a best-effort callback.

## 13. Thread Safety and Listener State

Listeners are commonly declared as Spring beans and can outlive a single item processing call. If a Step uses a `TaskExecutor`, partitioning, or another concurrency mechanism, multiple callbacks can execute concurrently depending on configuration.

Avoid unsynchronized mutable fields:

~~~java
public class UnsafeListener
        implements ItemProcessListener<OrderInput, Order> {

    private long processedCount;

    @Override
    public void afterProcess(OrderInput item, Order result) {
        processedCount++;
    }
}
~~~

Under concurrent execution, the increment above can lose updates. Use `MeterRegistry`, `LongAdder`, or an appropriate thread-safe counter.

Example:

~~~java
public class OrderMetricsListener
        implements ItemProcessListener<OrderInput, Order> {

    private final LongAdder processed = new LongAdder();
    private final LongAdder filtered = new LongAdder();
    private final LongAdder failures = new LongAdder();

    @Override
    public void afterProcess(OrderInput item, Order result) {
        if (result == null) {
            filtered.increment();
        } else {
            processed.increment();
        }
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        failures.increment();
    }

    public long processedCount() {
        return processed.sum();
    }

    public long filteredCount() {
        return filtered.sum();
    }

    public long failureCount() {
        return failures.sum();
    }
}
~~~

These counters reflect callbacks over the listener's lifetime. If a listener bean is shared across multiple `JobExecution` or `StepExecution` instances, define when counters are reset and read. Never assume a field counter always corresponds to exactly one Job.

### Do not hold the current item in a shared field

Do not assign the item in `beforeProcess` to a field and read it back in `afterProcess` if the listener can be called concurrently. Callbacks for other items can overwrite the field.

If you need to measure time or correlate callbacks by item, use appropriate metrics or a per-thread/per-identifier structure with a clear lifecycle and cleanup.

## 14. Accessing StepExecution Information When Needed

`ItemProcessListener` receives the item and result, but does not receive `StepExecution` directly in its callbacks. If you need Step details such as Step name or `JobExecution` ID, combine `StepExecutionListener` with the process listener, or obtain metadata via appropriate scope/context mechanisms.

For example, a single listener can implement both interfaces:

~~~java
public class OrderStepListener
        implements StepExecutionListener,
                   ItemProcessListener<OrderInput, Order> {

    private String stepName;

    @Override
    public void beforeStep(StepExecution stepExecution) {
        this.stepName = stepExecution.getStepName();
    }

    @Override
    public void beforeProcess(OrderInput item) {
        log.debug(
            "step={}, orderId={}",
            stepName,
            item.orderId()
        );
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        // Record processing outcome.
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        log.warn(
            "step={}, orderId={} failed",
            stepName,
            item.orderId(),
            exception
        );
    }
}
~~~

Attach the listener to the Step with `.listener(...)`. When the same object implements multiple listener interfaces, Spring Batch registers the corresponding callbacks from that object.

The example above assumes the listener instance belongs to a compatible single Step execution. If the same singleton instance is shared across parallel Steps, the `stepName` field can be overwritten. In that case, use Step scope or a stateless listener design to avoid shared state.

## 15. Combining ItemProcessListener with Metrics

A large batch system often needs to track:

- Total number of processor invocations.
- Number of times the processor returned output.
- Number of filtered items.
- Number of processing attempts throwing an exception.
- Average and percentile processing duration.
- Error rate by data type or exception type.

You can use Micrometer `MeterRegistry` to record metrics. Illustrative example:

~~~java
public class OrderProcessMetricsListener
        implements ItemProcessListener<OrderInput, Order> {

    private final Counter processed;
    private final Counter filtered;
    private final Counter errors;

    public OrderProcessMetricsListener(MeterRegistry registry) {
        this.processed = registry.counter("batch.order.processed");
        this.filtered = registry.counter("batch.order.filtered");
        this.errors = registry.counter("batch.order.process.errors");
    }

    @Override
    public void afterProcess(OrderInput item, Order result) {
        if (result == null) {
            filtered.increment();
        } else {
            processed.increment();
        }
    }

    @Override
    public void onProcessError(
            OrderInput item,
            Exception exception) {
        errors.increment();
    }
}
~~~

Note that retries increase the `onProcessError` count without necessarily increasing the final skipped item count. Therefore, metric names should clearly indicate whether they count failed attempts or unique failing items.

Avoid putting `orderId`, `customerId`, or unbounded values into metric tags, as this creates very high cardinality. Use tags with small value sets such as job name, step name, exception type, or processing status.

## 16. Testing ItemProcessListener

Test the listener at both the callback level and the Step integration level.

### Testing callbacks in isolation

You can call each method directly to confirm the listener logs or updates metrics accurately for the input:

| Scenario | Expected Callback |
|---|---|
| Starting item processing | `beforeProcess(item)` |
| Processor returns object | `afterProcess(item, result)` |
| Processor returns `null` | `afterProcess(item, null)` |
| Processor throws exception | `onProcessError(item, exception)` |

Direct tests are useful for verifying logic inside the listener. However, they do not prove the listener has been registered on the Step.

### Step integration testing

In a Spring Batch test context, run the Step with test reader, processor, and writer. Use a mock or spy listener to verify callbacks are invoked in the real flow.

Scenarios to cover:

1. Processor returns output for a valid item.
2. Processor returns `null` for a filtered item.
3. Processor throws an exception and the Step fails.
4. Processor throws an exception but the item succeeds on retry.
5. Processor throws an exception and the item is skipped.
6. The listener is registered exactly once.
7. The listener does not alter processor results or writer data.
8. Callbacks are invoked the expected number of times when there are no retries.

If a test involves retries, do not expect every item to have only one callback pair. Check attempt counts and the final outcome against the configured policy.

### Testing errors inside the listener

If the listener writes audits or metrics via a service, test behavior when that service fails. Clarify whether the application accepts continuing processing or requires the Step to fail when auditing cannot be recorded.

For mandatory audits, test transactions and restarts to prevent lost or duplicate audit events.

## 17. Common Design Mistakes

### Using a listener to transform data

`ItemProcessListener` returns no output item. Normalization, filtering, and validation logic must live in the processor.

### Confusing filtering with a process error

A processor returning `null` is intentional filtering and goes through `afterProcess`. A processor throwing an exception goes through `onProcessError` and is handled by the Step per policy.

### Using onProcessError to record skipped items

An error may be retried and succeed. Use `SkipListener` to record items that are actually skipped.

### Sending success notifications in afterProcess

The processor returning output does not mean the writer has written or the transaction has committed. Publish notifications after commit or via an outbox/dedicated Step.

### Writing duplicate audits on retry

A single item can trigger `onProcessError` multiple times. If you need a single rejection record, use a deduplication key or `SkipListener` for the final skip event.

### Slowing down every item in the listener

Making synchronous API calls or heavy database queries in callbacks per item can drastically reduce throughput. Keep callbacks lightweight or use an appropriate metrics collection mechanism.

### Using non-thread-safe mutable fields

A listener may be invoked concurrently in parallel processing configurations. Use stateless design, thread-safe counters, or appropriate bean scope.

### Logging the entire item

Items can contain sensitive data. Log only required identifiers and controlled error details.

### Registering the same listener twice

If the same logic is registered through multiple mechanisms, callbacks can run repeatedly. Register each listener explicitly once per Step.

## 18. Workflow for Implementing ItemProcessListener

When adding a listener to a Step, follow this sequence:

1. **Define the purpose:** logging, metrics, audit, or tracing.
2. **Identify callbacks:** before, after, or error; implement only what is needed.
3. **Distinguish outcomes:** output, `null` filter, and exception.
4. **Separate responsibilities:** keep business logic in `ItemProcessor`.
5. **Register the listener:** use interface or annotations and attach to the right Step.
6. **Handle retry/skip:** distinguish failed attempts from finally skipped items.
7. **Control side effects:** do not send success notifications before commit.
8. **Protect data:** log only necessary identifying fields.
9. **Ensure thread safety:** avoid unsynchronized shared mutable state.
10. **Test:** verify callbacks across success, filter, exception, retry, and skip flows.

## 19. Key Takeaways

- `ItemProcessListener` observes `ItemProcessor` invocations for each item.
- `beforeProcess` runs before the processor.
- `afterProcess` runs when the processor returns a result; `result` can be `null` if the item is filtered.
- `onProcessError` runs when the processor raises an exception.
- The listener does not alter input, output, or filter decisions.
- Use `ItemProcessor` for business logic and `SkipListener` for items actually skipped.
- Retries can cause callbacks to be invoked multiple times for the same item.
- `afterProcess` does not prove the writer wrote successfully or the transaction committed.
- External side effects in a listener may not roll back with the chunk.
- Keep callbacks lightweight, avoid logging sensitive data, and ensure thread safety.
- Register the listener on the Step with `.listener(...)` or the corresponding annotation mechanism.
- Test both isolated callbacks and Step integration with filtering, exceptions, retry, and skip.

`ItemProcessListener` provides clear visibility into the per-item processing lifecycle in Spring Batch. When the right logic is placed in each callback and processing outcomes are distinguished from chunk commit decisions, the listener delivers useful logs, metrics, and audits without making the business flow difficult to control.

