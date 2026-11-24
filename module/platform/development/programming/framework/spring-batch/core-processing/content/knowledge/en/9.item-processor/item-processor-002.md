# Processor returns null to filter an item

In Spring Batch chunk-oriented processing, `ItemProcessor<I, O>` receives each item supplied by the reader and decides what that item becomes as output. The processor can return a transformed object, or return `null` to remove the item from the processing flow. Returning `null` is called filtering.

When an item is filtered, Spring Batch does not pass it to `ItemWriter`. The item is still counted as read, but it does not contribute to the number of items written. This is the appropriate approach when a record is structurally valid but falls outside the scope of the result to be produced, for example a cancelled order in a job that exports only active orders.

Filtering differs from throwing an exception to skip an item. `null` expresses a deliberate business decision that the item needs no output; an exception indicates that processing encountered an error and must be handled according to the retry/skip policy or cause the step to fail.

## The ItemProcessor contract

`ItemProcessor<I, O>` has one `process` method that takes an input of type `I` and returns an output of type `O`:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

There are three main outcomes:

| Result of `process()` | Meaning | What happens next |
| --- | --- | --- |
| Returns an `O` object | The item is accepted and transformed | The output is placed in the chunk for the writer to write |
| Returns `null` | The item is deliberately filtered | The item is dropped from the output, and the writer does not receive it |
| Throws an exception | Processing the item encountered an error | Spring Batch applies the retry/skip policy if the step is configured for it; if it cannot be handled, the step fails |

A simple example:

```java
ItemProcessor<OrderInput, Order> processor = input -> {
    if ("CANCELLED".equalsIgnoreCase(input.status())) {
        return null;
    }

    return new Order(
            input.orderId(),
            input.customerId(),
            input.amount(),
            input.status());
};
```

In this example, orders with the `CANCELLED` status are dropped from the output. Other orders are converted to `Order` and continue to the writer. There is no need to throw an exception or configure skip just to discard an item that is valid under this business condition.

## How does Spring Batch handle a filtered item?

Within a chunk, Spring Batch reads items from `ItemReader`, calls the processor for each item, and then collects the non-`null` outputs to pass to the writer.

```text
ItemReader
   |
   +--> Order A --> ItemProcessor --> Order A' --+
   |                                             |
   +--> Order B --> ItemProcessor --> null       |  filtered
   |                                             |
   +--> Order C --> ItemProcessor --> Order C' --+
                                                 |
                                                 v
                                         ItemWriter
                                         [A', C']
```

Suppose the chunk size is 3 and the reader returns three items. If the processor returns an output for two items and `null` for the remaining one, the writer receives only two outputs. The chunk is still processed according to the step's transaction boundary; filtering does not create a separate chunk on its own, and it does not change the definition of the job's identifying parameters.

If all items in a chunk are filtered, there is no output to write. Spring Batch does not pass those items to the writer; the metadata updates and the transaction still follow the step's lifecycle.

### Example with orders

Suppose a job exports only orders with the `NEW` or `PAID` status. The `CANCELLED` and `DRAFT` statuses are valid in the source data but are not part of the result to be exported.

```java
public class ExportableOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        String status = input.status();

        if (!"NEW".equalsIgnoreCase(status)
                && !"PAID".equalsIgnoreCase(status)) {
            return null;
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new Order(
                input.orderId().trim(),
                input.customerId().trim(),
                input.amount(),
                status.toUpperCase(Locale.ROOT));
    }
}
```

Here there are two different decisions:

- A status outside the set to be exported: filter by returning `null`.
- An order within the set to be exported but with an invalid amount: throw a business exception.

Distinguishing the two cases clearly makes the filtering and skip statistics reflect the true nature of the data.

## Filtering is not the same as skipping

This is an important point when designing a processor and monitoring step results.

**Filtering** is a deliberate decision by the processor. The processor returns `null`, Spring Batch drops the item's output and increments `filterCount` in `StepExecution`. There is no exception, so the skip policy is not invoked for that filtering decision.

**Skipping** occurs when a read, process, or write operation throws an exception of a type configured as skippable. Spring Batch records the error in the corresponding skip counter, for example `processSkipCount` if the exception arises in the processor. Skip is typically used for bad records that the business allows to be ignored after the error is recorded.

| Criterion | Filtering (`return null`) | Skipping (exception + skip policy) |
| --- | --- | --- |
| Meaning | The item is valid but needs no output | The item hit an error that is allowed to be ignored |
| How it is expressed | The processor returns `null` | The processor/reader/writer throws an exception |
| Skip limit | Does not consume the skip limit | Can consume the skip limit |
| Counter | `filterCount` | `readSkipCount`, `processSkipCount`, or `writeSkipCount` depending on the layer |
| Error recording | Does not create a skip record on its own | Can be recorded through `SkipListener` |
| Example | Do not export a cancelled order | A badly formatted date value that is allowed to be skipped |

You should not return `null` for bad data just to keep the job going. Doing so makes the record disappear from the output without being counted as a skip error, which makes auditing and reconciliation difficult.

### Example of skip for invalid data

If an order is missing a required ID, the application can throw `InvalidOrderException` and configure skip if the business allows continuing:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

In this example, up to 50 exceptions of the specified type can be skipped according to the step's policy. Errors that exceed the limit or are not of an allowed type can cause the step to fail. Filtering is still expressed separately with `return null` and does not increase the skip count.

## Distinguishing the processor's null from the reader's null

These two cases have completely different meanings:

- `ItemReader.read()` returns `null`: the data source is exhausted, and the step has no more items to read.
- `ItemProcessor.process(item)` returns `null`: only the current item is filtered, and the reader continues to supply subsequent items.

For example, the reader has 1,000 orders. If the processor filters 200 orders, the job still continues processing the remaining 800 orders. A processor returning `null` does not end the job and does not signal EOF to the reader.

A reader should not return `null` to indicate a record that is invalid or that it does not want to process. Under the reader contract, `null` signals the end of input. If a reader returns `null` in the middle of the data source, Spring Batch may consider the data finished and not read the records that follow.

## Filter in the Reader or in the Processor?

Not every filter condition should be placed in the processor. Where to filter depends on the data source and the business meaning.

| Situation | Commonly suitable place | Reason |
| --- | --- | --- |
| Read only orders with the `NEW` status from the database | The `WHERE` condition in the reader/query | The database eliminates data early, reducing I/O and the number of items to read |
| Need to read all statuses to count how many records were dropped | The reader reads everything, the processor filters | Preserves the input figures and `filterCount` |
| The filter condition needs computation from multiple fields after mapping | Processor | The rule operates on the normalized input model |
| The condition depends on business logic shared across multiple sources | Processor | Separates the logic from how the source is accessed |
| Data outside the query scope from the start | Reader | No need to bring unrelated items into the pipeline |

Filtering in the database can be more efficient because it reduces the amount of data transferred over the network and processed in the JVM. However, if you need to report the number of items dropped by a processor rule, filtering early in the query means those items will not appear in the step's `readCount` or `filterCount`.

A useful principle: the condition that defines the set of data to read can be placed in the reader; the condition that decides whether an already-read item is converted into output is usually placed in the processor.

## Filtering in CompositeItemProcessor

Spring Batch provides `CompositeItemProcessor` to chain multiple processors. The delegates are called in sequence; the output of the previous processor becomes the input of the next. If a delegate returns `null`, the processing chain stops for that item and the item is filtered. The delegates that follow do not receive this item.

```text
OrderInput
    |
    v
NormalizeProcessor
    |
    v
ValidateProcessor
    |
    v
FilterCancelledProcessor
    |
    +---- null -----------------> item filtered
    |
    v
MapToOrderProcessor
    |
    v
Order output
```

For example:

```java
public class FilterCancelledProcessor
        implements ItemProcessor<NormalizedOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(NormalizedOrder order) {
        if (order.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return order;
    }
}
```

If `FilterCancelledProcessor` returns `null`, the final mapping processor is not called for that item. This helps avoid unnecessary transformation or data access for a record that has already been dropped.

When ordering a processor chain, place the necessary normalization steps before the filter condition, and place enrichment or transformation steps that are expensive after the filter condition if they do not need to run for dropped items. However, any validation required to establish that the data is valid must be performed before that value is used as the basis for filtering.

## Monitoring the number of filtered items

`StepExecution` provides counters for tracking processing results. These include:

- `readCount`: the number of items the reader has read.
- `writeCount`: the number of items the writer has written successfully according to the step metadata.
- `filterCount`: the number of items the processor has filtered by returning `null`.
- `readSkipCount`, `processSkipCount`, `writeSkipCount`: the number of items skipped at each stage due to an exception and the skip policy.

For example, a step that reads 1,000 items, filters 120 items, and writes 880 items successfully might have these figures:

| Counter | Illustrative value |
| --- | ---: |
| `readCount` | 1,000 |
| `filterCount` | 120 |
| `writeCount` | 880 |
| `processSkipCount` | 0 |

If 5 more items are skipped due to processor errors, `processSkipCount` reflects that group of errors separately from the 120 filtered items. The counters can relate to each other differently when retry, rollback, or skip occurs in the reader/writer; you need to read them together with the execution status and the step's log.

You can read the figures in a `StepExecutionListener`:

```java
public class FilterStatisticsListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        long read = stepExecution.getReadCount();
        long written = stepExecution.getWriteCount();
        long filtered = stepExecution.getFilterCount();

        System.out.printf(
                "Read=%d, written=%d, filtered=%d%n",
                read, written, filtered);

        return stepExecution.getExitStatus();
    }
}
```

The listener above illustrates how to read the counters after the step finishes. In production, you should write these figures to structured logging/metrics and tag them with the job name, job execution ID, step name, and business date for easy tracing.

`filterCount` only tells you how many items were dropped. It does not automatically store the specific reason or the content of the item. If you need to know why each record was filtered, you must design an additional recording mechanism.

## When you need to store the filter reason or the dropped data

`ItemProcessor` only returns an output or `null`. When it returns `null`, the item's information and the filter reason are not automatically passed to the writer. If a business requirement calls for storing dropped records in a reject file, an audit table, or a report, you should not just use `null` and expect the writer to be able to retrieve that item.

One design approach is to create a result type that expresses the processing decision:

```java
public record OrderDecision(
        Order acceptedOrder,
        OrderInput originalInput,
        String decision,
        String reason) {

    public boolean accepted() {
        return acceptedOrder != null;
    }
}
```

The processor always returns an `OrderDecision`, even when the record is dropped:

```java
public class OrderDecisionProcessor
        implements ItemProcessor<OrderInput, OrderDecision> {

    @Override
    public OrderDecision process(OrderInput input) {
        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return new OrderDecision(
                    null, input, "FILTERED", "Order is cancelled");
        }

        Order order = new Order(
                input.orderId(),
                input.customerId(),
                input.amount(),
                input.status());

        return new OrderDecision(order, input, "ACCEPTED", null);
    }
}
```

The writer can then route `ACCEPTED` to the main writer and `FILTERED` to an audit/reject writer. With this approach, the filter decisions are expressed as normal output, so Spring Batch's `filterCount` does not increase on its own for those cases. If you need separate statistics, the application must record the accepted/filtered counts in the writer or in a statistics mechanism that is consistent with the transaction.

Another option is to split into separate steps or processing flows if the requirement to store dropped records is complex. Avoid writing side effects directly from the processor if a transaction rollback or retry could cause the audit to be written twice. Coordinate the audit with the step's transaction or use an idempotency key.

## Filtering and the skip listener

`SkipListener` is invoked when an item is skipped due to an exception under the skip policy. It is not a listener for items filtered by `return null`.

If you need to store skipped items, you can use `SkipListener` to receive the item and the corresponding exception. If you need to store filtered items, you need a separate design such as `OrderDecision` above or a deliberate tracking mechanism. Do not expect `onSkipInProcess` to be called when the processor returns `null`, because that is not a skip error.

Separating the two kinds of events keeps operational reporting clear:

| Event | Source of information | Suitable place to record it |
| --- | --- | --- |
| Filtered item | Processor returns `null` | `filterCount`, metrics, or a separate decision output |
| Skipped item | An exception accepted by the skip policy | Skip counters and `SkipListener` |
| Successfully processed item | Processor returns an output and the writer writes it successfully | `writeCount` and the target data |

## Filtering and transaction, retry, restart

Filtering is the processor's decision during a single processing of an item. It still sits within the chunk flow and is affected by chunk-level transaction/retry/restart behavior.

Some notes:

- A processor should have deterministic results: the same input and the same reference data within the scope of the job should lead to the same filter decision.
- Avoid calling APIs or writing non-idempotent audit records in the processor, because the processor can be called again on retry or chunk rollback.
- If the filter condition depends on the business date, configuration state, or rule version, pass that information through `JobParameters` or an immutable configuration for the run.
- On restart, keep the identifying parameters unchanged to continue the same `JobInstance`.
- Do not use filtering to hide infrastructure errors or bad data that should be handled by the skip/retry policy.

For example, a job that exports data by day accepts only orders whose `createdDate` falls within the period. The start and end dates should be determined from `JobParameters`; if `LocalDate.now()` is used in the processor, a restart on a different day may produce different filter decisions from the first run.

If the processor filters an item before the writer runs, the writer does not need to handle that item. However, if the processor has already called an external system or written a log/audit record with side effects, those effects are not necessarily rolled back with the chunk. Keep the processor purely transformational when possible.

## Testing a processor with filtering

A processor can be tested independently with a unit test. You should test the kept case, the filtered case, and the bad-data case.

```java
class ExportableOrderProcessorTest {

    private final ExportableOrderProcessor processor =
            new ExportableOrderProcessor();

    @Test
    void filtersCancelledOrder() throws Exception {
        OrderInput input = new OrderInput(
                "O-1002", "C-02", new BigDecimal("89.00"), "CANCELLED");

        assertNull(processor.process(input));
    }

    @Test
    void keepsNewOrder() throws Exception {
        OrderInput input = new OrderInput(
                "O-1001", "C-01", new BigDecimal("125.50"), "NEW");

        Order result = processor.process(input);

        assertNotNull(result);
        assertEquals("O-1001", result.getOrderId());
        assertEquals("NEW", result.getStatus());
    }

    @Test
    void rejectsInvalidAmount() {
        OrderInput input = new OrderInput(
                "O-1003", "C-03", BigDecimal.ZERO, "NEW");

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

In addition to the processor unit test, the step's integration test should confirm that:

- A filtered item does not appear in the target table/file.
- `filterCount` increases by the number of items for which the processor returns `null`.
- `writeCount` reflects only the items the writer actually wrote successfully.
- The skip counters increase only when the exception is accepted by the skip policy.
- When all items are filtered, the step can still complete with 0 items written.
- When a chunk rolls back or the job restarts, no duplicate audit records or side effects arise.

## Common mistakes

### Returning null because the data is invalid

This causes the item to be counted as filtered rather than skipped. If invalid data needs to be recorded as an error, throw a business exception and configure the skip policy/SkipListener appropriately.

### Thinking that returning null ends the step

A `null` from the processor only drops the current item. The reader continues reading subsequent items. Only a `null` from `ItemReader.read()` signals the end of input.

### Expecting the writer to receive filtered items

The writer receives only non-`null` outputs. If you need to store dropped items, return a decision/result object and route it in the writer, or use a separate audit flow.

### Using SkipListener to catch filtering

Filtering is not a skip exception, so `SkipListener` does not receive that event. Use `filterCount` to count, or design a separate output to store the reason.

### Filtering in the processor even though the database can filter earlier

Reading all the data and then dropping most of it in the processor can waste I/O and CPU. If the filter condition can be expressed exactly in the source query and you do not need statistics on the items dropped within the step, consider filtering right at the reader.

### A processor with side effects before returning null

If the processor sends a message, calls an API, or writes data before returning `null`, the side effect has still occurred even though the item never reaches the writer. If there is a retry or rollback, the side effect may be repeated. Keep the processor pure or use an appropriate idempotent/transactional mechanism.

## Key takeaways

In Spring Batch, an `ItemProcessor` returns `null` to filter the current item out of the output flow. The item was read by the reader but is not passed to the writer; Spring Batch records this with `filterCount`, not the skip count. A `null` from the reader, by contrast, means the end of input. Use filtering for items that are valid but need no result, and handle bad data with exceptions and the skip/retry policy. If you need to store the reason or content of dropped items, design a decision output or a separate audit flow instead of just returning `null`.
