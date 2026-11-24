# Filtering processor

In Spring Batch, an `ItemProcessor` can both transform data and decide which items are passed along to the Writer. When a Processor returns `null`, Spring Batch understands that the item is **filtered** and will not write it to the Step's output.

Filtering is appropriate when an item is structurally valid but falls outside the scope of processing—for example, cancelled orders, out-of-period transactions, customers not belonging to a tenant, or records that do not satisfy business conditions. This is a normal processing decision, not an error. Therefore, filtering differs from skipping: filtering returns `null`, whereas skipping typically occurs when an exception is configured to be skipped.

## 1. Filtering in chunk processing

A chunk Step typically follows this flow:

```text
ItemReader
    |
    v
ItemProcessor
    |
    +--> returns object -> adds item to chunk output
    |
    +--> returns null   -> filters item, does not pass to Writer
    |
    v
ItemWriter receives remaining items
```

For example, the Reader reads 5 orders. The Processor keeps 3 active orders and returns `null` for 2 cancelled orders. The Writer only receives the 3 retained orders.

```text
Reader:      A   B   C   D   E
Processor:   A  null C  null E
Writer:      A       C       E
```

A filtered item has still been read and processed by the Processor, but it does not become an output item of the chunk. In a normal Step execution without skips, `readCount` includes the read items, `filterCount` counts filtered items, and `writeCount` counts written items. With retry/skip, counters can be more complex because an item may be retried.

## 2. Returning null to filter an item

The `ItemProcessor<I, O>` API allows returning an object of type `O` or `null`. The `null` value is the filter signal:

```java
import org.springframework.batch.item.ItemProcessor;

public class ActiveOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.isCancelled()) {
            return null;
        }

        return order;
    }
}
```

In this example, cancelled orders are not sent to the Writer. The Processor does not throw an exception because this is an expected business exclusion condition.

A lambda can be used for simple logic:

```java
ItemProcessor<Order, Order> activeOrderProcessor = order ->
        order.isCancelled() ? null : order;
```

Do not return an empty object to represent filtering. The Writer would still receive that object and could write invalid data. Use `null` when you want to exclude an item from the pipeline output.

## 3. Example of filtering by business status

Suppose a Job only exports orders with status `PAID` or `READY_TO_SHIP`:

```java
public class ExportableOrderProcessor
        implements ItemProcessor<Order, ExportOrder> {

    @Override
    public ExportOrder process(Order order) {
        if (order.getStatus() != OrderStatus.PAID
                && order.getStatus() != OrderStatus.READY_TO_SHIP) {
            return null;
        }

        return new ExportOrder(
                order.getId(),
                order.getCustomerId(),
                order.getAmount());
    }
}
```

The Processor simultaneously filters and transforms: ineligible items return `null`; eligible items are converted into `ExportOrder`.

Filter conditions should reflect clear business rules. If an unsupported status is a data error, throw a business exception instead of automatically filtering it. If any status outside those two values is allowed to be excluded, returning `null` is appropriate.

## 4. Combining a Filtering Processor with a Step

Example chunk Step configuration in Spring Batch 5:

```java
@Bean
public Step exportPaidOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ExportOrder> exportableOrderProcessor,
        ItemWriter<ExportOrder> exportWriter) {

    return new StepBuilder("exportPaidOrdersStep", jobRepository)
            .<Order, ExportOrder>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(exportableOrderProcessor)
            .writer(exportWriter)
            .build();
}
```

Spring Batch invokes the Processor for each item returned by the Reader. Items yielding `null` are removed from the chunk output; the Writer only receives the remaining `ExportOrder` instances. If all items in a chunk are filtered, the Writer may not be invoked with empty data; the Step still continues and checkpoints according to the chunk mechanism.

The commit interval determines the chunk cadence based on the number of input items read/processed, not a guarantee that the Writer always receives that exact count. For example, with a chunk size of 200 where 35 items are filtered, the Writer receives at most 165 items in that chunk.

## 5. Filtering vs. skip

Both filtering and skipping can prevent an item from appearing in the output, but their semantics and configurations differ.

| Criterion | Filtering | Skip |
|---|---|---|
| Signal | Processor returns `null` | Exception configured as skippable |
| Meaning | Valid item that does not need further processing | Error allowed to be bypassed by policy |
| `faultTolerant()` configuration | Not needed just for filtering | Typically used to configure skip/retry |
| Counter | `filterCount` | `readSkipCount`, `processSkipCount`, `writeSkipCount` |
| Skip limit | Does not consume skip limit | Consumes skip limit |
| Example | Cancelled order does not need to be exported | Malformed date or invalid data allowed to be rejected |

Filtering example:

```java
if (order.isCancelled()) {
    return null;
}
```

Example of skipping a recoverable record-level business error:

```java
if (order.getAmount() == null) {
    throw new InvalidOrderException("amount is required");
}
```

A Step can configure skipping for specific exceptions:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

Do not use skip to express a normal business exclusion condition. Conversely, do not filter an item just because its data is corrupt; doing so can hide poor data quality and make the Job look like it succeeded.

## 6. Tracking the number of filtered items

Spring Batch records the number of filtered items in `StepExecution`. You can read `filterCount` after the Step completes:

```java
long filtered = stepExecution.getFilterCount();
long read = stepExecution.getReadCount();
long written = stepExecution.getWriteCount();
long skipped = stepExecution.getSkipCount();
```

Commonly used counters:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items read by the Reader per Step metadata. |
| `writeCount` | Number of items successfully written per Step metadata. |
| `filterCount` | Number of items excluded by the Processor returning `null`. |
| `readSkipCount` | Number of read errors skipped. |
| `processSkipCount` | Number of Processor errors skipped. |
| `writeSkipCount` | Number of Writer errors skipped. |
| `skipCount` | Total skips across all phases. |

You can use `StepExecutionListener.afterStep()` to record counts after the Step ends:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class FilterMetricsListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        long filtered = stepExecution.getFilterCount();
        long written = stepExecution.getWriteCount();

        log.info("Step {} filtered={}, written={}",
                stepExecution.getStepName(), filtered, written);

        return null;
    }
}
```

`afterStep()` runs when the Step finishes. If persistent statistics broken down by filter reason are needed, `filterCount` alone is insufficient because it does not store the reason for each item. Design appropriate audit/reject output accordingly.

## 7. Observing filtered items with ItemProcessListener

`ItemProcessListener.afterProcess(item, result)` receives the Processor result. When `result == null`, you can detect that the item was filtered:

```java
import org.springframework.batch.core.ItemProcessListener;

public class FilterObservationListener
        implements ItemProcessListener<Order, ExportOrder> {

    @Override
    public void beforeProcess(Order item) {
    }

    @Override
    public void afterProcess(Order item, ExportOrder result) {
        if (result == null) {
            log.debug("Filtered order {}", item.getId());
        }
    }

    @Override
    public void onProcessError(Order item, Exception e) {
        log.warn("Processing failed for order {}", item.getId(), e);
    }
}
```

Register the listener in the Step:

```java
return new StepBuilder("exportPaidOrdersStep", jobRepository)
        .<Order, ExportOrder>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(exportableOrderProcessor)
        .writer(exportWriter)
        .listener(filterObservationListener)
        .build();
```

Listeners are useful for observation or logging. However, do not perform a non-idempotent side effect such as sending an email or calling an API just because an item was filtered. The callback may be invoked during a chunk that later rolls back/retries; logs or external effects may be repeated even though the chunk data has not committed.

If you need persistent auditing for filtered items, put the filter decision into a result object and write the audit within an appropriate transaction, as shown in the next section.

## 8. Storing filter reasons instead of only incrementing filterCount

A Processor returning `null` only indicates that the item was excluded. It does not pass a reason to the Writer because the item is dropped from the output. If you need to report why each record was filtered, you can use a result type wrapping the processing decision:

```java
public record OrderDecision(
        Order order,
        boolean accepted,
        String reason) {
}
```

The Processor always returns a decision:

```java
ItemProcessor<Order, OrderDecision> decisionProcessor = order -> {
    if (order.isCancelled()) {
        return new OrderDecision(order, false, "CANCELLED");
    }
    if (order.getAmount().signum() <= 0) {
        return new OrderDecision(order, false, "NON_POSITIVE_AMOUNT");
    }
    return new OrderDecision(order, true, null);
};
```

Then, a routing Writer can send valid decisions to the business Writer and excluded decisions to the audit/reject Writer. Conceptual example:

```java
ClassifierCompositeItemWriter<OrderDecision> decisionWriter =
        new ClassifierCompositeItemWriterBuilder<OrderDecision>()
                .classifier(decision -> decision.accepted()
                        ? acceptedOrderWriter
                        : filteredOrderAuditWriter)
                .build();
```

This example illustrates per-item routing; delegate Writers matching the `OrderDecision` type must be declared and their transaction/lifecycle configured properly. Unlike `null` filtering, both decision types remain output items of the Processor and are then routed to the corresponding Writer.

If audit records must commit together with business data, the Writers should use the same database and transaction manager. If the audit target is a separate system, idempotency or an outbox is needed to prevent audit state from diverging from primary data.

## 9. Combining multiple Processors with CompositeItemProcessor

A pipeline can consist of multiple Processors: filter first, then enrich and transform. `CompositeItemProcessor` invokes delegates in order; if a delegate returns `null`, the item is filtered and subsequent delegates do not receive that item.

```java
ItemProcessor<Order, Order> filterCancelled = order ->
        order.isCancelled() ? null : order;

ItemProcessor<Order, EnrichedOrder> enrichOrder = order ->
        new EnrichedOrder(
                order,
                customerService.findSegment(order.getCustomerId()));

CompositeItemProcessor<Order, EnrichedOrder> processor =
        new CompositeItemProcessorBuilder<Order, EnrichedOrder>()
                .delegates(List.of(filterCancelled, enrichOrder))
                .build();
```

Order matters: `filterCancelled` runs first to avoid calling `customerService` for cancelled orders. If reversed, the application might perform expensive queries or enrichment for an item that gets dropped anyway.

If a delegate throws an exception, that is a processing error and is handled according to the Step's retry/skip policy. If a delegate returns `null`, the pipeline stops for that item without treating it as an exception.

## 10. Filtering by JobParameters

A Job can accept filter criteria at launch time, such as exporting only orders with a minimum amount or belonging to a specific tenant. Use `@StepScope` to inject the values:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> minimumAmountProcessor(
        @Value("#{jobParameters['minimumAmount']}") BigDecimal minimumAmount) {

    if (minimumAmount == null) {
        throw new IllegalArgumentException("minimumAmount is required");
    }

    return order -> order.getAmount().compareTo(minimumAmount) >= 0
            ? order
            : null;
}
```

Launching the Job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("minimumAmount", "100.00", true)
        .toJobParameters();
```

If `minimumAmount` changes the set of items belonging to the batch, decide whether it should be an identifying parameter. If the same JobInstance is restarted with a different filter condition, the results may become inconsistent with checkpoints and already committed data. Typically, parameters affecting business scope should be identifying or persisted fixedly in batch metadata.

## 11. Should you filter in the Reader or the Processor?

Not every condition needs to live in the Processor. If the data source supports efficient filtering, you can push the condition down to the Reader/query to reduce the volume of data read and passed through the pipeline.

| Where to place the condition | When appropriate | Impact |
|---|---|---|
| Reader/query | Simple conditions expressible in SQL or source queries | Fewer items read; reduces I/O and processing. |
| Processor | Conditions requiring Java logic, enriched data, or multiple business rules | Items are read and counted in `readCount`; excluded items increment `filterCount`. |
| Writer/routing | Need to send items to different outputs or persist both accepted/rejected decisions | Items are retained as decisions and routed. |

For example, if only fetching orders with `status = 'PAID'`, the condition can be added to the SQL Reader. However, if you need to check a combination of multiple fields, reference data, or policies varying per JobParameter, the Processor may be clearer.

Pushing filters down to the Reader can improve performance, but excluded items will not appear in `filterCount` because the Processor never sees them. If reporting on business-excluded counts is needed, separate query statistics or auditing is required.

## 12. Filtering and chunk size

Chunk size determines the number of items read/processed before committing according to the Step configuration. Filtering reduces the number of items the Writer receives, but does not necessarily change the number of items that must be read to reach the commit interval.

For example, with a chunk size of 5:

```text
Reader:      A   B   C   D   E
Processor:   A  null C  null E
Writer:      A       C       E
Commit:      after the input chunk is processed
```

The chunk has 5 input items, but only 3 items are written. If all 5 items are filtered, no items are sent to the Writer, yet the Step still manages checkpoints/transactions according to the chunk lifecycle.

Do not increase chunk size merely to compensate for filtered items without measuring performance. Larger chunks increase rollback scope, transaction duration, and memory usage. If the filter rate is high, consider filtering in the Reader/query when the condition can be pushed down to the source.

## 13. Filtering must be deterministic across retries and restarts

A Processor may be invoked again if a chunk retries or a Job restarts. Filter conditions should be deterministic for the same item and the same batch parameters.

For example, filtering by `order.status` stored in the item is fairly stable. Filtering by status from a constantly changing API could include an item in the output on the first run but exclude it on restart.

To keep results consistent:

1. Use the same identifying JobParameters on restart.
2. Keep a snapshot/version of source data if the filter condition depends on source state.
3. Persist the rule or policy version if filter rules can change.
4. Avoid calling external services with volatile state per item if results must remain stable.
5. Do not produce side effects in the Processor just to mark an item as filtered.

If you need to filter against a reference table that can change, snapshot the reference data or store the policy version/time cutoff. That way, the same JobInstance can apply the exact same rule set across restarts.

## 14. Side effects in the Processor and transactions

A Processor should primarily perform calculations, mapping, controlled enrichment, and filter decisions. It should not send emails, call APIs to create transactions, or write independent audits directly inside `process()`.

Reason: the Processor may be called again due to retries or rollbacks. The chunk's database transaction can roll back, whereas side effects in external systems are not automatically undone. An item could be filtered after a side effect has already occurred, or the chunk could fail after the Processor processes some items.

If filtered items need to be recorded:

- Return a decision object and write the audit via a Writer in an appropriate transaction.
- Write an event to an outbox in the same database transaction.
- Use a stable idempotency key based on the business item and batch.
- Only publish notifications after the transaction/Step succeeds.

Listeners can also be invoked during a chunk attempt that later rolls back. Using listeners for observational logs/metrics is appropriate; using them as the sole place to persist durable business data requires careful consideration.

## 15. Filtering all items and Step outcome

A Step may read many items and filter all of them. In that case, the Writer writes no records, yet the Step can still complete normally if no other errors occur.

Example:

```text
readCount   = 1000
filterCount = 1000
writeCount  = 0
skipCount   = 0
BatchStatus = COMPLETED
```

This can be a valid outcome if no items match the processing criteria. However, in some systems, `writeCount = 0` might indicate a misconfigured filter or anomalous source data.

You can check after the Step:

```java
if (stepExecution.getReadCount() > 0
        && stepExecution.getWriteCount() == 0
        && stepExecution.getFilterCount() > 0) {
    log.info("All input items were filtered");
}
```

If the business requires at least one output item, validate that condition in a listener/validation Step and end the Job with an appropriate status. Do not assume every Step with `writeCount = 0` is a failure.

## 16. Testing a Filtering Processor

Tests should verify both per-item decisions and Step metrics after execution.

Unit test for the Processor:

```java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Test
void filtersCancelledOrder() throws Exception {
    Order cancelled = new Order("ORD-1", OrderStatus.CANCELLED);
    Order paid = new Order("ORD-2", OrderStatus.PAID);

    assertNull(processor.process(cancelled));
    assertNotNull(processor.process(paid));
}
```

Integration tests with Job/Step should verify:

1. The Reader reads the expected number of input items.
2. The Processor returns `null` for the exact expected conditions.
3. The Writer only receives non-filtered items.
4. `StepExecution.filterCount` increments accurately.
5. `skipCount` does not increase solely due to filtering.
6. If the Processor throws an exception, the skip/retry policy is applied separately.
7. Restarting the same JobInstance yields consistent filter results.
8. If auditing of filtered items is enabled, audit and business outputs are not duplicated after retries.

Example assertions:

```java
assertEquals(10, stepExecution.getReadCount());
assertEquals(3, stepExecution.getFilterCount());
assertEquals(7, stepExecution.getWriteCount());
assertEquals(0, stepExecution.getSkipCount());
```

These numbers assume no retries, skips, or other errors, and that the Writer successfully writes all retained items. For Steps with retry/skip, verify counters according to the semantics of your Spring Batch version and specific test scenario.

## 17. Common pitfalls

| Pitfall | Consequence | How to handle |
|---|---|---|
| Returning an empty object instead of `null` | Writer still receives the item and may write invalid data. | Return `null` to filter. |
| Using exceptions for normal exclusion conditions | Adds fault-tolerance overhead and inflates skip count. | Use null-return filtering. |
| Filtering corrupt data as if it were unnecessary data | Hides data quality errors. | Throw a business exception and use a clear reject/skip policy. |
| Confusing `filterCount` with `skipCount` | Operational reporting misattributes exclusion causes. | Track filters and skip categories separately. |
| Expecting the Writer to receive filtered items | Items returning `null` are no longer in the chunk output. | Use a decision object and routing Writer if auditing is needed. |
| Writing audits/calling APIs inside the Processor | Retries/rollbacks can produce duplicate or inconsistent side effects. | Write via Writer/outbox with idempotency. |
| Filtering based on mutable external data | Restarts may produce different decisions. | Use a stable snapshot/version/cutoff. |
| Filtering too late after expensive enrichment | Increases queries and processing cost for items that will be dropped. | Place cheap, deterministic filters early in the chain. |
| Filtering in the Reader while expecting `filterCount` to increase | Items never pass through the Processor so they are not counted as filtered. | Track Reader conditions separately or filter in the Processor. |
| Assuming a Step with 0 writes always failed | Can misinterpret a valid batch with no matching items. | Define clear business rules for empty output. |

## Conclusion

A Filtering Processor removes items from output by returning `null`. This is the standard way to express a normal business decision; filtered items do not reach the Writer and are counted in `filterCount`, not `skipCount`. Use filtering for valid records outside the processing scope, while data errors should be classified using exceptions and skip/fail policies. Place filter conditions early when possible, keep rules deterministic across restarts, and avoid side effects in the Processor. If you need to store filter reasons, return a decision object and route it to an appropriate audit Writer instead of returning `null` and losing item details.
