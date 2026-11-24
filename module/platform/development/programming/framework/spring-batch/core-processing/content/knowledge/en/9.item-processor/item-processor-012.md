# Distinguishing filter from skip

In Spring Batch, both **filter** and **skip** can prevent an item from being written by `ItemWriter`, but they represent two different situations. Filter is a deliberate decision of `ItemProcessor`: the item is valid for processing but does not belong to the result to be produced, so the processor returns `null`. Skip is a fault-tolerance mechanism: an exception that occurs while reading, processing, or writing an item is configured as skippable, allowing the Step to continue with other items within a set limit.

Distinguishing the two mechanisms properly ensures accurate data reporting. For example, a cancelled order can be filtered out of a report; an order missing a required code is bad data and can be skipped if the business allows it. If you use filter to hide data errors, the system loses information about invalid records. If you use skip for every item that does not need processing, the skip count will misrepresent data quality.

## 1. Filter and skip in chunk processing

In a chunk-oriented Step, the basic processing flow is:

```text
ItemReader
    |
    v
ItemProcessor
    |
    +-- Returns an object ---> ItemWriter
    |
    +-- Returns null --------> Filter (not sent to writer)
    |
    +-- Throws an exception -> Skip policy / Retry / Step failure
```

`ItemProcessor` can return an output object or `null`. When it returns `null`, Spring Batch treats the item as filtered and does not pass it to the writer. No exception is thrown merely because of filtering.

By contrast, skip begins with an exception. If the exception is of a type configured to be skippable and the skip limit has not been exceeded, Spring Batch skips the failed item under the fault-tolerance policy and continues processing. If the exception is not allowed to be skipped or exceeds the limit, the Step can fail.

| Criterion | Filter | Skip |
|---|---|---|
| Meaning | Drop an item under a deliberate business rule. | Skip an item due to an allowed error. |
| Common trigger | Processor returns `null`. | Reader, processor, or writer throws a skippable exception. |
| Is there an exception? | No exception needed. | There is an exception as the basis for the skip. |
| Counter | `filterCount`. | `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `skipCount`. |
| Counted toward `skipLimit`? | No. | Yes. |
| Can `SkipListener` be used? | No, because filter is not a skip event. | Yes, to record skipped items. |
| Example | Drop cancelled orders from a report. | Skip a malformed CSV line under an approved policy. |

## 2. Filter: the processor returns null

Filter is appropriate when an item does not need to appear in the result and dropping it is a normal business decision.

For example, a Job exports only confirmed orders. Unconfirmed orders are not corrupted data; they simply fall outside the scope of the report:

```java
public class ConfirmedOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (!item.confirmed()) {
            return null;
        }

        return new Order(
                item.orderId(),
                item.customerId(),
                item.amount());
    }
}
```

When the processor returns `null`:

- The item was read by the reader.
- The processor decided not to produce output for that item.
- The writer does not receive that item.
- `StepExecution`'s `filterCount` is incremented.
- There is no skip event and no skip limit is consumed.

A processor can both filter and convert the remaining items. For example, filtering cancelled orders and converting active orders to the output model:

```java
@Override
public Order process(OrderInput item) {
    if (item.cancelled()) {
        return null;
    }

    return toOrder(item);
}
```

Use filter when the drop condition is a clear, stable rule accepted by the business. You can record the filter reason using a metric or a separate audit mechanism if reports need to explain why the number of input items is greater than the number of written items.

## 3. Skip: ignoring an item due to an exception

Skip is used for errors that have been identified as safe to ignore without stopping the whole Step. In a chunk step, exceptions can arise at three stages:

- **Read:** the reader cannot read a record, for example a malformed CSV line.
- **Process:** the processor cannot process an item, for example an invalid business code.
- **Write:** the writer cannot write an item, for example a data-constraint violation that policy allows ignoring.

For example, an order missing an order ID is invalid data. The processor throws an exception instead of returning `null`:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        return toOrder(item);
    }
}
```

If `InvalidOrderException` is configured as a skippable exception and the limit has not been exceeded, Spring Batch can skip the bad item and continue processing the remaining items.

Skip does not mean the exception is treated as if it never happened. It is a controlled error-handling decision. The application should record the cause, the item type, and the information needed to fix the data or reconcile later.

## 4. Configuring skip and skip limit

In Spring Batch 5, you can enable fault tolerance and declare skippable exceptions on a chunk step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(100)
            .build();
}
```

In this example, up to 100 errors belonging to the skippable group are accepted under the Step's limit. When the skip count exceeds the limit, the Step fails. Exceptions outside the skip policy can also cause the Step to fail.

`skipLimit` is a combined limit for skips across the read, process, and write stages, not an independent limit for each stage. `filterCount` does not count toward the skip limit.

For example, if the skip limit is 10 and the Step has already skipped 10 items, one more skippable error will cause the limit to be exceeded and the Step cannot continue under that policy.

### Specifying non-skippable exceptions

You can configure a specific exception not to be skipped using `noSkip`, even when a superclass of it has been declared skippable:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(FatalImportException.class)
.skipLimit(50)
```

This is only an example illustrating the classification rule. In a real application, you should not declare `skip(Exception.class)` overly broadly because it can hide serious system errors, programming errors, or infrastructure errors. Specify the business exceptions that can be skipped.

### Using a custom SkipPolicy

If the skip decision depends on the error type, the error count, or the context, you can use a custom `SkipPolicy` instead of listing many simple exception types. The policy must make a clear decision for each exception and the number of skips already taken; if it does not allow skipping, it throws an exception per the `SkipPolicy` contract.

A custom policy is useful when business rules are complex, but keep the logic easy to understand and test. Do not use a policy to turn every unknown error into a skip.

## 5. Skipping at the read stage (read skip)

Read skip occurs when `ItemReader` throws an exception while reading an item and that exception is allowed to be skipped.

For example, a reader reading CSV encounters a line with invalid structure. If `FlatFileParseException` is configured to be skippable, the Step can ignore the bad line and continue with the next line, depending on the behavior of the reader and the data source.

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(25)
```

Read skip suits errors whose position can be identified and where reading can continue safely, such as an unparseable input line. If the reader loses its database connection or hits an unrecoverable system error, skipping a broad exception can let the Job continue in an unreliable data state. You need to distinguish an error in a single record from an error in the data source.

With read skip, the reader may not be able to produce a complete item. Therefore, the `SkipListener.onSkipInRead` callback receives only the exception, with no input item to record. If you need to know the failed line or raw content, the reader's exception may provide position or data details; handle them safely and avoid writing full sensitive data into logs.

## 6. Skipping at the process stage (process skip)

Process skip occurs when `ItemProcessor.process` throws an exception configured to be skippable.

For example, the item was read successfully but fails a data rule:

```java
@Override
public Invoice process(InvoiceInput item) {
    if (item.amount() == null || item.amount().signum() <= 0) {
        throw new InvalidInvoiceException("Invoice amount must be positive");
    }

    return toInvoice(item);
}
```

If `InvalidInvoiceException` is allowed to be skipped, that item is not passed to the writer, while the Step can continue with other items.

Process skip is appropriate when:

- The error is tied to one specific item.
- The bad item cannot be fixed by automatic retry.
- The business allows continuing to process the remaining items.
- The application can store the reason for correction or reconciliation.

If the error is only transient, such as a reference service timing out, retry may be more appropriate than skip. If you skip a transient error, the business result may miss data that should have been processed.

## 7. Skipping at the write stage (write skip)

Write skip occurs when `ItemWriter` throws an exception and that exception is configured to be skippable. For example, the database rejects writing a record due to a unique-constraint violation, while business policy allows ignoring duplicate records.

```java
.faultTolerant()
.skip(DuplicateOrderException.class)
.skipLimit(100)
```

A writer usually receives a group of items, so a write error can relate to a single item or the whole batch. Spring Batch may have to roll back the chunk and analyze items again to identify the offending element under its fault-tolerance mechanism. This can cause the reader/processor/writer to be called again during error handling.

Therefore, the writer must be designed appropriately for transactions and repeated calls. Do not perform side effects outside the transaction in the writer without an idempotency mechanism. If the database returns an error for the whole batch and the offending record cannot be identified safely, the Step may fail instead of skipping arbitrarily.

## 8. Recording skips with SkipListener

SkipListener lets the application record skipped items to produce error reports, save details into a reject table, or send them to a separate bad-data handling flow.

The interface has the main callbacks:

```java
public interface SkipListener<I, O> {
    void onSkipInRead(Throwable t);
    void onSkipInProcess(I item, Throwable t);
    void onSkipInWrite(O item, Throwable t);
}
```

Example of a listener that logs by stage:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Could not read an input record: {}", exception.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable exception) {
        log.warn("Skipping order input {}: {}",
                item.orderId(), exception.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable exception) {
        log.warn("Skipping order {} during write: {}",
                item.orderId(), exception.getMessage());
    }
}
```

Register the listener on the Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .listener(orderSkipListener)
        .build();
```

The example above focuses on registration and callbacks; the application needs to declare a logger, data types, and an appropriate error-storage policy. `onSkipInRead` has no item because the reader may not have produced one. `onSkipInProcess` receives the input item, while `onSkipInWrite` receives the output item created by the processor.

SkipListener is for skips caused by exceptions. When the processor returns `null`, this listener is not invoked. If you want to audit filtering as well, create a separate metric or listener/recording mechanism for filter decisions.

## 9. How do filter and skip affect the counters?

`StepExecution` stores counters that help distinguish items read, items filtered, and items skipped:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items successfully read by the reader. |
| `filterCount` | Number of items dropped by the processor returning `null`. |
| `writeCount` | Number of items written by the writer. |
| `readSkipCount` | Number of items skipped due to exceptions while reading. |
| `processSkipCount` | Number of items skipped due to exceptions while processing. |
| `writeSkipCount` | Number of items skipped due to exceptions while writing. |
| `skipCount` | Total number of skips across the stages. |

Example of a Step with these metrics:

| Metric | Value |
|---|---:|
| `readCount` | 1,000 |
| `filterCount` | 100 |
| `processSkipCount` | 15 |
| `writeSkipCount` | 5 |
| `readSkipCount` | 0 |
| `writeCount` | 880 |

This example shows 100 items filtered under business rules, 20 items skipped due to errors, and 880 items written by the writer. This is an illustrative set of numbers; in a real application, the counters can be affected by retry, rollback, a writer writing multiple outputs for one item, or how the reader/writer is implemented.

Do not apply a simple formula to every Step such as `readCount = writeCount + filterCount + skipCount`. The counters reflect the activity of each stage, but a writer may write multiple outputs for one input, or rollbacks/retries can make the flow more complex. Read the metrics together with the logs and data results.

## 10. Combining filter, skip, and retry

A Step can use filter, skip, and retry at the same time because they solve different cases:

- Filter valid items that are outside the scope to be written.
- Retry transient errors that can recover.
- Skip item errors that have been determined to be ignorable.
- Fail the Step when an error is serious or exceeds the skip/retry limit.

For example:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .noSkip(FatalImportException.class)
        .build();
```

The processor can return `null` for cancelled orders. If an item has invalid data, the processor throws `InvalidOrderException`; if the reader cannot parse a line, it can throw `FlatFileParseException`; if the writer encounters a transient database access error, the exception can be retried. `FatalImportException` is excluded from the skip policy.

The order and classification of exceptions should reflect the meaning of the error. Do not configure retry and skip for the same exception arbitrarily; define the desired behavior when retries are exhausted and verify the final handling policy.

## 11. Choosing filter or skip by scenario

### Cancelled order

If the Job only produces a report of active orders, a cancelled order is a valid item outside the scope of the report. Having the processor return `null` is appropriate. This is filtering.

### Order missing an identifier

If the order ID is required, an item missing the ID is bad data. The processor can throw `InvalidOrderException`. If the business allows continuing and storing the bad record, configuring skip is appropriate.

### Malformed CSV line

If the reader cannot parse a line but can continue reading subsequent lines, you can configure skip for the specific parse exception. This is a read skip. If the file is severely structurally corrupted or the reader cannot continue safely, let the Step fail.

### Transaction hits a database timeout

A timeout can be a transient error. Retry with an appropriate limit and backoff is usually worth considering. Skipping immediately can cause missing transactions. If the error persists, the Step should fail so the system can restart or investigate.

### Record with a duplicate unique key

This may be duplicate data to skip, or a serious error if the business requires every record to be unique. The decision depends on business rules. If skipped, store the key and reason for reconciliation.

| Scenario | Commonly suitable handling | Reason |
|---|---|---|
| Item is valid but not needed in the result | Filter (`return null`) | Deliberate business decision. |
| Malformed item that can be ignored | Skip | Known and allowed exception. |
| Transient recoverable error | Retry | Likely to succeed on a later attempt. |
| System error or data where it is unsafe to continue | Fail Step | Serious errors should not be hidden. |
| Dropped item needs auditing as a business decision | Filter + dedicated metric/audit | Not a skip event. |
| Item dropped due to exception and needs an error report | Skip + SkipListener | There is an exception and a matching callback. |

## 12. Impact of transactions and rollback

Chunk processing usually processes each chunk in a transaction. When an exception occurs, the transaction may roll back before the framework determines whether the item can be retried or skipped. Therefore, part of the logic in the chunk can be called again during fault tolerance.

This affects filter and skip:

- Filter does not throw an exception, yet the processor can still be called again if the chunk rolls back because of an error on another item.
- Skip starts from an exception and may require rolling back/replaying the chunk to identify the bad item or continue safely.
- The writer can be called again when the framework handles retries or scans for bad items.
- Side effects outside the transaction do not roll back with the database automatically.

Therefore, the processor should focus on computation and producing results. Avoid sending email, writing files, or calling non-idempotent APIs in the processor. If you need to store bad data, design the storage mechanism to align with the transaction and listener lifecycle so that retries do not create duplicate reject records.

## 13. Designing reporting for filtered and skipped data

A production Job often needs to explain how the input items became the output. You can report separately:

- Total number of items read.
- Number of items filtered by each business reason.
- Number of items skipped by read, process, or write stage.
- Exception type and identifying information for failed records.
- Number of items written successfully by the writer.
- Number of retries, rollbacks, and the final Step status.

`StepExecution` provides aggregate counters, but it does not store full business reasons for every filtered item. If you need statistics by reason such as `CANCELLED`, `OUT_OF_SCOPE`, or `DUPLICATE`, the processor can emit tagged metrics or update an appropriate audit report.

For skips, `SkipListener` can record the exception and item details. Consider the transaction: the reject record should be saved in a way consistent with the chunk commit, avoiding cases where the error record is written to the reject table but the chunk transaction later rolls back and the listener is called again.

You should not write the full sensitive payload of an item into logs. Store only the business key, error type, source position, and the information needed to fix the data.

## 14. Common mistakes

### Using return null for every kind of bad data

This turns a data error into a filter, increasing `filterCount` and not triggering `SkipListener`. When you need to investigate or report bad records, throw a specific exception and configure skip if allowed.

### Using skip for an item that is simply out of scope

This increases the skip count and makes data quality look poor even though the item is completely valid. Use filter for business-exclusion decisions.

### Overly broad skip configuration

Skipping `Exception.class` or an overly general exception class can hide programming errors, lost connections, configuration errors, or transaction errors. Skip only exception types that are understood and safe to ignore.

### Setting the skip limit too high or unlimited

A Job can complete even after dropping a large number of important records. Choose a limit based on business requirements and monitor the error rate, not just the total count.

### Thinking skips do not need recording

Skip means the record was not processed successfully through the main pipeline. Consider `SkipListener`, a reject table, or an error report so it can be fixed and reconciled.

### Thinking filter does not affect report results

Filtering reduces the number of items the writer receives. If you do not record the filter reason, users may not understand why the number of input items differs from the number of output items.

### Retrying a fixed data error

Retry cannot fix an item missing a required field or having an invalid format. Classify data errors and transient errors to choose skip or retry appropriately.

## 15. Workflow for deciding filter, skip, or fail

When handling an item that is not written, determine the cause in sequence:

1. Is the item valid and simply outside the scope of the result to produce? If yes, filter by returning `null`.
2. Did an exception occur in the reader, processor, or writer? If not, do not call it a skip.
3. Is the exception an error specific to that item that the business allows ignoring? If yes, configure skip for the specific exception.
4. Is the error likely transient and can the operation be repeated safely? If yes, consider retry with a limit.
5. Does the error make the data or system state unreliable? If yes, let the Step fail and handle it under the recovery procedure.
6. Does the filtered or skipped item need to be audited, reported, or fixed? If yes, record the reason and business key using an appropriate mechanism.

| Desired outcome | Mechanism |
|---|---|
| Drop a valid item from the output | Processor returns `null` (filter). |
| Ignore an allowed item error | Configure `.skip(...)` and `.skipLimit(...)`. |
| Record a skipped item | Register a `SkipListener`. |
| Retry a transient error | Configure `.retry(...)` and `.retryLimit(...)`. |
| Stop on an error not allowed to be ignored | Do not configure skip for that exception or use `.noSkip(...)`. |

## Conclusion

Filter is a business decision of `ItemProcessor`: return `null` to drop an item from the writer and increment `filterCount`. Skip is a fault-tolerance mechanism triggered by an exception in the reader, processor, or writer; it is controlled by the skip policy/skip limit, increments the skip counts, and can be recorded via `SkipListener`. Use filter for items that are valid but unneeded in the result, use skip for item errors that are allowed to be ignored, use retry for transient errors, and let the Step fail when it is unsafe to continue.
