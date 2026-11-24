# Processor throws an exception when an item is invalid

In chunk-oriented processing, `ItemProcessor` receives each item from the reader to validate, normalize, or transform it before the writer writes the data. When an item violates a business rule, the processor can throw an exception to signal that the item cannot be processed under the current contract.

Spring Batch treats an exception raised in the processor as an error in the item-processing stage. Depending on the fault-tolerance configuration, the exception can fail the chunk, be retried, or be treated as a skipped item. Therefore, you need to choose an exception type and handling policy that match the meaning of the error.

The key point is to distinguish invalid data that can be discarded from system errors that require stopping the job. If skip is too broad, the batch can complete but silently drop important data. If every data error stops the job, a few bad records can prevent an entire batch of data from being processed.

## 1. When should a processor throw an exception?

A processor should throw an exception when it cannot produce a valid output item from the input item under the defined rules. For example:

- A required order identifier is missing.
- A quantity or monetary value falls outside the allowed business domain.
- The source status is not supported.
- Required reference data does not exist.
- A business condition prevents the item from being converted safely.

An example processor that validates an order:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

@Bean
ItemProcessor<OrderRow, Order> orderProcessor() {
    return row -> {
        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        if (row.quantity() <= 0) {
            throw new InvalidOrderException(
                "Quantity must be greater than zero for " + row.orderId());
        }

        return new Order(
            row.orderId().trim(),
            row.productCode().trim(),
            row.quantity()
        );
    };
}
```

When an invalid condition is detected, the processor throws `InvalidOrderException`. That item is not passed to the writer in this processing attempt. The step then applies the configured exception policy to decide whether to continue, retry, skip, or fail.

## 2. Choose the exception based on the meaning of the error

You should create business exceptions with specific names instead of throwing a generic `RuntimeException` for every situation. The exception type is the input Spring Batch uses to classify errors and apply skip or retry.

| Error type | Example | Commonly suitable handling |
|---|---|---|
| Invalid data that can be discarded | Missing required field, negative quantity | Limited skip and record the bad item |
| Business error requiring manual handling | Customer ID does not exist, disallowed status | Depends on requirements: skip with audit, or stop the job |
| Transient infrastructure error | Timeout, deadlock, reference service temporarily unavailable | Limited retry |
| System configuration or contract error | Wrong schema, missing required configuration, mass mapping errors | Usually stop the job to investigate |

You should not use a single exception for both validation errors and connection errors. If everything is a generic `RuntimeException`, the skip/retry configuration cannot easily tell which cases are safe to continue past.

An example of defining dedicated exceptions:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class ReferenceServiceUnavailableException extends RuntimeException {
    public ReferenceServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

`InvalidOrderException` can represent invalid data, while `ReferenceServiceUnavailableException` represents a transient error when calling a reference service. The two kinds of errors can be configured differently.

## 3. Default: an exception fails the step

If the step does not declare a suitable skip or retry policy, an exception that is not handled in the processor will fail the step. The current chunk does not complete as a successful chunk; the transaction is rolled back according to the step's transaction configuration.

A basic flow example:

```text
Reader -> Processor -> Writer
                 |
                 +-- exception
                       |
                       v
                 Chunk rollback
                       |
                       v
                  Step FAILED
```

This is usually the safe behavior when the error indicates that the data or configuration cannot be processed reliably. The job stops so that operators can investigate and fix the cause before restarting.

When an exception occurs in the processor, the writer does not receive the failed item. Other items in the same chunk may have been read or processed before the error was detected, but the uncommitted chunk transaction is rolled back. With a stateful reader, Spring Batch can restore the checkpoint through the restart mechanism.

## 4. Allowing invalid items to be skipped

When a kind of data error is determined to be ignorable, you can configure fault tolerance and a skip policy for that exception.

An example using the Spring Batch 5 builder API:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
}
```

In this example, `InvalidOrderException` is treated as a skippable error. The step can continue processing the remaining items as long as the skip count has not exceeded the limit. Other exceptions not covered by the skip policy can still fail the step.

### How is the skip limit counted?

`skipLimit(n)` sets a limit on the total number of items allowed to be skipped in the step execution. This limit is counted across errors in the read, process, and write stages, rather than being a separate quota for each stage.

For example, `skipLimit(50)` allows at most 50 skips under the policy. When a skip occurs that exceeds the limit, the step fails. The limit is useful so that a file with too many bad records is not treated as an ordinary successful batch.

You should not set the skip limit too high just so the job always completes. If 40% of the data is dropped, that may indicate a badly formatted source file, a changed mapping, or an upstream error affecting data en masse. You should monitor both the number and the ratio of skipped items.

## 5. Skip only specific exceptions

A skip policy should allow-list the exceptions that truly represent items that can be discarded. Avoid configuring skip for every exception:

```java
// Not recommended: can hide programming errors and infrastructure errors
.faultTolerant()
.skip(Exception.class)
.skipLimit(100000)
```

A broad configuration can turn database connection errors, configuration errors, programming errors, or data contract errors into skipped items. The job may report completion even though the business result is not reliable.

Instead, declare specific business error types:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skip(MissingOptionalReferenceException.class)
.noSkip(CriticalBatchConfigurationException.class)
.skipLimit(50)
```

`noSkip` can be used to exclude an exception from a general skip policy. If possible, avoid declaring an overly broad skip from the start so the configuration is easier to understand. In particular, schema errors, configuration errors, or system errors should not be ignored just because they are wrapped in a generic exception.

## 6. Distinguishing throwing an exception from filtering with null

A processor has two common ways to avoid sending an item to the writer, but they mean different things:

| Handling | Meaning | Counted as skip? |
|---|---|---|
| Return `null` | Deliberately filter the item according to a business rule | No |
| Throw an exception accepted by the skip policy | The bad item is discarded under the fault-tolerance policy | Yes |
| Throw an exception that is not skippable | The error fails the step | Not considered a successful skip |

A filter example:

```java
ItemProcessor<OrderRow, Order> processor = row -> {
    if (row.isCancelled()) {
        return null; // Deliberately ignored
    }
    return convert(row);
};
```

A skip example:

```java
ItemProcessor<OrderRow, Order> processor = row -> {
    if (row.quantity() <= 0) {
        throw new InvalidOrderException("Invalid quantity");
    }
    return convert(row);
};
```

Filtering is typically for cases where the item is outside the dataset to be processed but is still valid under the rules, for example a cancelled order or a record outside the reporting scope. Skipping is for items that cannot be processed due to errors that are allowed to be discarded and that need to be counted or audited.

You should not return `null` to hide validation errors. In that case the skip figures do not reflect the bad records, and operators find it hard to distinguish validly filtered data from data dropped because it was wrong.

## 7. Recording skipped items with SkipListener

When you need to store dropped records, you can use `SkipListener`. For errors in the processor, the appropriate callback is `onSkipInProcess(item, throwable)`.

```java
public class OrderSkipListener implements SkipListener<OrderRow, Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInProcess(OrderRow item, Throwable error) {
        log.warn("Skipping order {}: {}", item.orderId(), error.getMessage());
    }

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("Skipping unreadable input: {}", error.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable error) {
        log.warn("Skipping order {} during write: {}", item.orderId(), error.getMessage());
    }
}
```

Register the listener in the step:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(50)
.listener(orderSkipListener)
```

`onSkipInProcess` receives the processor's input item, here `OrderRow`. `onSkipInWrite` receives the output item `Order`. This helps distinguish bad source data from errors that arise when writing the target data.

A listener is useful for writing logs, metrics, or storing reject information. If the listener writes to a database or calls an external service, you need to design the transaction and idempotency carefully. The reject-recording mechanism should not cause an error that destroys the job's main processing ability or creates duplicate side effects on retry/restart.

For bad data that needs to be reprocessed, you can write a reject record containing the source identifier, line number, business key, exception type, and reason. Avoid storing the entire sensitive payload unless necessary; apply the corresponding data protection policy.

## 8. Retry is for transient errors

Skip and retry address two different situations. Skip removes the item from the pipeline; retry re-attempts an operation that may succeed if the transient error goes away.

For example, a processor calls an address-lookup service. A timeout may be only a transient error, while a badly formatted address is a data error that cannot be fixed by trying again.

```java
return new StepBuilder("enrichOrders", jobRepository)
    .<OrderRow, EnrichedOrder>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .build();
```

The code snippet illustrates limited retry for transient errors and skip for a specific data error. Classify exceptions clearly; do not configure the same error as both retry and skip unless you have determined exactly the behavior you want once the retries are exhausted.

Retry can cause the processor to be called again for the same item. Therefore, the processor should avoid non-idempotent side effects. If the processor writes data or calls an external API, a retry may perform that operation multiple times.

## 9. Chunk rollback and behavior on skip

In chunk processing, items are read and processed before the writer writes the group of output items in the step's transaction. When the processor throws an exception, Spring Batch can roll back the chunk and then apply retry/skip according to the fault-tolerance configuration.

```text
Chunk begins
  read A -> process A -> valid
  read B -> process B -> InvalidOrderException
                         |
                         v
              rollback / recovery
                         |
                         v
              classify the exception
                  /          \
               skip          fail
                |              |
                v              v
        continue next item   Step FAILED
```

The details of how many times the reader/processor is called again depend on the reader, the transaction, the retry/skip policy, and the step's recovery mechanism. You should not assume an item is always read or processed exactly once.

When an exception is skipped, the bad item is not passed to the writer. The remaining valid items can be written in subsequent chunks. If the skip limit is exceeded or the exception is not allowed to be skipped, the step ends in failure.

## 10. Errors arising in the reader differ from errors in the processor

Not every data error occurs in the processor. For example, a CSV line that cannot be parsed into a number can arise right in the reader. In that case the exception is classified as a read error, not a process error.

| Stage | Example | Corresponding skip callback |
|---|---|---|
| Read | A CSV line with a format error when parsed | `onSkipInRead(Throwable)` |
| Process | Quantity equal to 0 or missing business code | `onSkipInProcess(item, Throwable)` |
| Write | Constraint violation when writing the output record | `onSkipInWrite(item, Throwable)` |

Choosing the correct stage helps logs and audits point to the origin of the error. If the parser throws an exception in the reader, add a skip policy for that exception if you want to ignore the bad line. You should not convert every read error into a processor error just to consolidate handling in one place.

## 11. Do not skip widespread errors or contract errors

Some errors appear on the surface to occur on individual items but actually reflect a system-wide problem. For example:

- Every record is missing a column because the source file changed its schema.
- The reference service returns an authentication error because the credential has expired.
- A new mapping reads the wrong timezone for all the data.
- The writer cannot connect to the database.
- A code change causes every item to throw the same exception.

These cases usually require stopping the job rather than skipping item by item. If it continues, the job may produce a completed result in which most of the data is dropped or missing.

You can set a skip threshold by both count and ratio using a custom `SkipPolicy` if business requirements call for limiting the error ratio. With a ratio policy, you need to determine how the denominator is calculated, because the number of items read can change and skips in read/process/write have different meanings.

## 12. Common mistakes when configuring processor exceptions

| Mistake | Consequence | Remedy |
|---|---|---|
| Throwing a generic `RuntimeException` for every error | Hard to distinguish bad data from system errors | Use exceptions specific to the error domain |
| Not configuring skip but expecting the job to ignore errors on its own | The step fails as soon as the exception escapes the processor | Declare a limited skip policy if the business allows |
| Skipping `Exception.class` | Can hide system errors or programming errors | Skip only the identified data exceptions |
| Using `null` to signal an error | The item is filtered and not counted as a skip | Throw an exception or return a clear result type |
| Setting the skip limit too high | The job can complete with significantly missing data | Choose a threshold based on data quality and alert on the error ratio |
| Not recording skipped items | Cannot investigate or fix the bad data | Use SkipListener, logs, and an appropriate reject store |
| Retrying a validation error that will not go away on its own | Wastes time and load without improving the result | Retry only errors that are likely to be transient |
| A processor with non-idempotent side effects | A retry can repeat the operation | Move the side effect to the writer or use idempotency/outbox |

## 13. Workflow for choosing how to handle an exception

When a processor detects a bad item, decide by following these steps:

1. Determine whether the error is a data error specific to that item or an infrastructure/contract error affecting many items.
2. If the item is outside the processing scope but still valid, consider returning `null` to filter it.
3. If the item is invalid and allowed to be discarded, throw a specific business exception and configure a skip limit.
4. If the error may go away transiently, configure a limited retry for the corresponding exception.
5. If the error is serious or exceeds the quality threshold, let the step fail and require investigation.
6. Record the skipped items, their causes, and their count; do not let bad data disappear silently.
7. Ensure the processor is safe when called again and that the writer can handle retry/restart under idempotent rules.

## Conclusion

A processor throws an exception when an item cannot be safely transformed under the data contract. Without a suitable fault-tolerance policy, the exception fails the step. When the error represents an item that can be discarded, configure skip for a specific exception with a reasonable limit and use `SkipListener` to record it. For transient errors, use limited retry; for system errors or widespread contract errors, you should stop the job to investigate.

Distinguishing an exception from filtering with `null`, choosing the right exception type, and ensuring the processor does not create repeated side effects will let the batch handle bad data in a controlled way while preserving correctness under retry or restart.
