# Committing by data size

In Spring Batch, a chunk is usually configured by item count, for example 100 items per chunk. This approach is easy to understand and works well when each item is of relatively uniform size. But if items vary greatly in size, the same commit interval can produce chunks that are very small or very large in actual data volume.

For example, 100 short CSV lines might take up only a few kilobytes, while 100 objects containing large JSON content or binary data might take up tens of megabytes. When item sizes are uneven, you may need to end a chunk based on the estimated total data volume while still limiting the maximum number of items.

Spring Batch supports changing the chunk termination condition through CompletionPolicy. You can use a built-in policy for item count or time, or write your own policy to track the data weight of each item. Whichever criterion you choose, a completed chunk is still the transaction boundary the framework uses to write and commit data.

## 1. The default commit interval counts items

The familiar configuration:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

The value 100 is the maximum number of items the framework gathers into a chunk under the default completion policy. It does not mean a chunk always has exactly 100 items: the last chunk can be smaller when the reader runs out of data, and filtering/skipping also affects the final number of items the writer receives.

With items of similar size, counting items is usually good enough. But if item sizes vary widely, the item count does not accurately reflect the memory or payload that the chunk produces.

For example:

| Chunk | Item count | Average size per item | Estimated volume |
|---|---:|---:|---:|
| A | 100 | 1 KB | 100 KB |
| B | 100 | 200 KB | 20 MB |
| C | 100 | 2 MB | 200 MB |

All three chunks have 100 items, but the memory and data-write costs are very different.

## 2. When do you need to commit by data size?

Committing by size is useful when item sizes vary significantly or the write target has a payload limit.

Some common situations:

- Reading a file whose lines have very different lengths.
- Processing JSON/XML where each document has a different size.
- Writing objects that contain large text content or binary data.
- Sending batch payloads to an API that has a request size limit.
- Writing to a database with BLOB/CLOB data or many large text columns.
- Wanting to limit the amount of data held temporarily in memory between writes.

Before choosing a policy, you need to be clear about which quantity "data size" refers to:

| Quantity | Meaning | How to estimate |
|---|---|---|
| Source bytes | The number of bytes read from a file or message | Actual byte length |
| Object size | The memory the object occupies in the JVM | Estimate from fields and object structure |
| Output payload | The size after serialization for writing/sending | Measure bytes after serialization or use an estimator |
| Database write cost | The data and overhead the database processes | Estimate from the schema, indexes, and driver |

These quantities are not the same. A 10 KB JSON can become a much larger Java object because of object headers, Strings, collections, and references. Conversely, a large object in the JVM may be serialized into a smaller payload.

If the goal is to avoid exceeding an API's request limit, you should measure the payload after serialization. If the goal is to limit memory when gathering a chunk, you need to use a memory estimate or a representative weight for each item. Don't call an estimated byte count an exact size if it is based only on the size of the input string.

## 3. CompletionPolicy controls when a chunk ends

Spring Batch uses CompletionPolicy to determine when an iteration that processes a chunk should complete. The default policy is usually based on item count. You can use a different policy to end a chunk under your own condition.

With Spring Batch 5, StepBuilder supports passing a CompletionPolicy together with the transaction manager:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy orderChunkPolicy,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(orderChunkPolicy, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

CompletionPolicy decides whether the current chunk is eligible to end. When the policy reports completion, the framework passes the items already read through the processor/writer as configured, and then completes the chunk's transaction.

Some built-in policies:

- **SimpleCompletionPolicy:** ends after a number of iterations, usually corresponding to the item count.
- **TimeoutTerminationPolicy:** ends when a time limit is reached.
- **CompositeCompletionPolicy:** combines multiple policies, for example limiting both item count and time.

Not every built-in policy measures bytes. If you want to commit by data volume, you usually need a custom CompletionPolicy that has a way to obtain the size of the items already read.

With Spring Batch 4, the StepBuilder API and the way the transaction manager is passed may differ. Use the overload that matches the version you are deploying.

## 4. Designing a size-based completion policy

A size-based policy needs to know the total weight of the items the reader has provided for the current chunk. You can design it with this model:

1. The reader reads an item.
2. A wrapper measures or estimates the size of that item.
3. The wrapper records the item's weight in a tracker shared with the policy.
4. The CompletionPolicy adds the weight to the chunk's total.
5. When the total reaches the byte threshold or the item count reaches the limit, the policy ends the chunk.

Diagram:

~~~text
ItemReader.read()
      |
      v
Size-aware reader wrapper
      |
      +--> return the item to the framework
      |
      +--> record estimated size in the tracker
                  |
                  v
          CompletionPolicy.update()
                  |
                  v
          Accumulate bytes / item count
                  |
          +-------+-------+
          |               |
   threshold reached?   not reached
          |               |
          v               v
   end the chunk     read next item
          |
          v
   ItemWriter.write(chunk)
          |
          v
        commit
~~~

For example, you can set a threshold of 5 MB and a maximum limit of 500 items. The chunk ends when the total weight reaches or exceeds 5 MB, or when it has 500 items. The item count limit is still needed because many very small items could make the chunk contain too many objects even though the estimated total bytes are low.

The size threshold is usually an approximate target, not an absolute hard limit. The item that pushes the total over the threshold stays in the current chunk; the policy can only end the chunk after that item has been read. If a single item is larger than the threshold, the chunk may contain only that item and still exceed the threshold.

## 5. Tracking item size in the reader

One way to separate responsibilities is to wrap the ItemReader with a size-measuring reader. The reader wrapper still returns each item under the normal contract; it only additionally records the item's weight in the tracker.

Example abstraction:

~~~java
public class ItemSizeTracker {

    private final ThreadLocal<Long> lastSize = new ThreadLocal<>();

    public void record(long size) {
        if (size < 0) {
            throw new IllegalArgumentException("Item size must not be negative");
        }
        lastSize.set(size);
    }

    public OptionalLong takeLastSize() {
        Long size = lastSize.get();
        lastSize.remove();

        return size == null
                ? OptionalLong.empty()
                : OptionalLong.of(size);
    }

    public void clear() {
        lastSize.remove();
    }
}
~~~

Reader wrapper:

~~~java
public class SizeTrackingItemReader<T> implements ItemReader<T> {

    private final ItemReader<T> delegate;
    private final ToLongFunction<T> sizeEstimator;
    private final ItemSizeTracker tracker;

    public SizeTrackingItemReader(
            ItemReader<T> delegate,
            ToLongFunction<T> sizeEstimator,
            ItemSizeTracker tracker) {
        this.delegate = delegate;
        this.sizeEstimator = sizeEstimator;
        this.tracker = tracker;
    }

    @Override
    public T read() throws Exception {
        T item = delegate.read();

        if (item == null) {
            tracker.clear();
            return null;
        }

        tracker.record(sizeEstimator.applyAsLong(item));
        return item;
    }
}
~~~

The size estimator depends on the item type. For a String, you can measure the number of UTF-8 bytes:

~~~java
ToLongFunction<String> utf8Size =
        value -> value.getBytes(StandardCharsets.UTF_8).length;
~~~

For an Order object, you can estimate by field:

~~~java
ToLongFunction<Order> orderSize =
        order -> estimateOrderBytes(order);
~~~

The estimateOrderBytes function is application logic that you need to define according to the actual data structure. If the writer serializes Order to JSON, a more accurate way to measure the payload is to measure the bytes of the JSON after serialization. If you only use the lengths of String fields, treat that as an estimate and add the appropriate numeric fields, delimiters, encoding, and overhead.

The tracker needs to be shared between the reader wrapper and the CompletionPolicy within the same execution. The example above uses ThreadLocal to store the size of the item just read on the current thread; when implementing a multi-threaded Step or an asynchronous reader, you need to ensure the reader and the policy read from the same execution context/thread, or use an appropriate safe mechanism to pass the weight.

## 6. Example of a CompletionPolicy by bytes and item count

The example below illustrates a custom CompletionPolicy. The policy ends a chunk when the estimated byte threshold or the item limit is reached, while also honoring the EOF signal.

~~~java
public class EstimatedBytesCompletionPolicy implements CompletionPolicy {

    private static final String TOTAL_BYTES = "estimatedBytes.total";
    private static final String ITEM_COUNT = "estimatedBytes.items";

    private final long maxBytes;
    private final long maxItems;
    private final ItemSizeTracker tracker;

    public EstimatedBytesCompletionPolicy(
            long maxBytes,
            long maxItems,
            ItemSizeTracker tracker) {
        if (maxBytes <= 0 || maxItems <= 0) {
            throw new IllegalArgumentException("Limits must be positive");
        }

        this.maxBytes = maxBytes;
        this.maxItems = maxItems;
        this.tracker = tracker;
    }

    @Override
    public RepeatContext start(RepeatContext parent) {
        tracker.clear();
        return new RepeatContextSupport(parent);
    }

    @Override
    public void update(RepeatContext context) {
        OptionalLong size = tracker.takeLastSize();

        if (size.isEmpty()) {
            return;
        }

        long bytes = value(context, TOTAL_BYTES) + size.getAsLong();
        long items = value(context, ITEM_COUNT) + 1;

        context.setAttribute(TOTAL_BYTES, bytes);
        context.setAttribute(ITEM_COUNT, items);
    }

    @Override
    public boolean isComplete(RepeatContext context) {
        return value(context, TOTAL_BYTES) >= maxBytes
                || value(context, ITEM_COUNT) >= maxItems;
    }

    @Override
    public boolean isComplete(
            RepeatContext context,
            RepeatStatus result) {
        return result == RepeatStatus.FINISHED || isComplete(context);
    }

    private long value(RepeatContext context, String key) {
        Object value = context.getAttribute(key);
        return value instanceof Number
                ? ((Number) value).longValue()
                : 0L;
    }
}
~~~

The classes RepeatContextSupport, RepeatContext, RepeatStatus, and CompletionPolicy belong to the Spring Batch Repeat API. The example shows an implementation idea for Spring Batch 5; you need to place the reader wrapper and the policy in the same Step scope, and register the beans correctly according to the application's configuration.

The policy keeps two counters in the chunk's RepeatContext:

- TOTAL_BYTES is the total weight of the items read.
- ITEM_COUNT is the number of items read.

On each update(), the policy takes the latest weight from the tracker and adds it to the context. When either threshold is reached, isComplete() returns true. If the reader returns null and the loop ends, the overload that takes a RepeatStatus also ends the chunk so the framework can process the remaining items.

If you use this policy, the reader wrapper must record the tracker for every non-null item. Do not let the tracker retain the size of the previous item before EOF or before the next read fails.

## 7. Attaching the reader wrapper and policy to the Step

When configuring Spring, the reader wrapper and the policy must use the same ItemSizeTracker. You can split the original reader into its own bean and then wrap it.

Example configuration structure:

~~~java
@Bean
ItemSizeTracker orderItemSizeTracker() {
    return new ItemSizeTracker();
}

@Bean
@StepScope
ItemReader<Order> sizeTrackingOrderReader(
        @Qualifier("delegateOrderReader") ItemReader<Order> delegate,
        ItemSizeTracker orderItemSizeTracker) {

    return new SizeTrackingItemReader<>(
            delegate,
            this::estimateOrderBytes,
            orderItemSizeTracker);
}

@Bean
@StepScope
CompletionPolicy orderSizeCompletionPolicy(
        ItemSizeTracker orderItemSizeTracker) {

    return new EstimatedBytesCompletionPolicy(
            5L * 1024 * 1024,
            500L,
            orderItemSizeTracker);
}
~~~

In the example, estimateOrderBytes is an estimation function supplied by the application. The delegateOrderReader bean is the original reader, not the reader wrapper itself, to avoid a circular dependency.

The Step that uses the policy:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy orderSizeCompletionPolicy,
        ItemReader<Order> sizeTrackingOrderReader,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(orderSizeCompletionPolicy, transactionManager)
            .reader(sizeTrackingOrderReader)
            .writer(orderWriter)
            .build();
}
~~~

This is an illustrative structure showing how to connect the components. In a real configuration, you need to ensure the tracker is shared correctly between the policy and the reader within the same StepExecution. If the application runs multiple JobExecutions concurrently, you should use beans with an appropriate scope or a tracker with its own per-execution state instead of sharing one global mutable accumulator.

## 8. Combining byte, item count, and time limits

Using only a byte threshold may not be enough.

If items are very small, a chunk can hold a very large number of items before reaching the byte threshold. This increases the number of objects, the processing cost, and the time the writer has to iterate.

If items are very large, a single item can exceed the threshold immediately. No chunk policy can automatically split one business item into multiple items.

A practical configuration usually combines:

- An estimated byte threshold to limit the payload or amount of data in the chunk.
- A maximum item count to limit the number of objects.
- A maximum time if you need to avoid holding a transaction for too long.

Example goals:

| Condition | Illustrative threshold |
|---|---:|
| Total estimated size | 5 MB |
| Maximum item count | 500 |
| Maximum time | 10 seconds |

A chunk completes when any one of the termination conditions is satisfied. You can use CompositeCompletionPolicy to combine built-in policies, or write a single policy with multiple conditions. Check the semantics of the composite policy in the Spring Batch version you are using, especially which policy ends the whole chunk and how policies are reset between chunks.

You should not set the threshold so low that the writer and database must commit continuously. You also should not set it so high that one chunk holds too much data or the transaction runs long.

## 9. Hard limits and items that exceed the threshold

A typical size-based policy only checks after an item has been read. Therefore, it creates a target limit whose maximum overshoot usually depends on the size of the largest item.

Example with a 5 MB threshold:

~~~text
Current chunk: 4.7 MB
Next item:     0.8 MB
New total:     5.5 MB
                |
                v
Policy ends the chunk after this item
~~~

The chunk will be about 5.5 MB, not exactly 5 MB.

If you need a hard limit, you need to handle oversized items separately:

- Check the size before putting the item into the chunk.
- Reject oversized items or route them to a separate processing flow.
- Split the payload into valid business units before the reader returns the item.
- Use an API or writer that supports streaming if you don't need to hold the whole payload in the chunk.
- Limit the maximum size of a single record at the input.

Don't arbitrarily split a business item just to meet the chunk threshold if that breaks data integrity.

## 10. Impact on transactions and the database

Even if CompletionPolicy ends a chunk by bytes, the transaction semantics remain the same as for a normal chunk:

1. The framework begins a transaction.
2. The reader provides items until the policy ends the chunk or the source runs out.
3. The processor processes items.
4. The writer writes the remaining items.
5. The framework updates the stream state and checkpoint.
6. The transaction manager commits or rolls back according to the outcome.

A larger chunk can hold the transaction and locks longer. A smaller chunk can increase the number of commits and the database round-trip cost.

Data size is one factor, but you also need to consider:

- The number of SQL statements issued.
- The number of bind parameters in a batch update.
- The driver's packet or request size.
- The database's or API's payload limits.
- Processor and writer time.
- Lock contention and connection hold time.
- The temporary memory held by the reader, processor, and writer.

If the writer uses JDBC batching, the chunk size can affect the number of statements in the batch. If the driver has a limit on the number of parameters or the packet size, you need to choose a threshold that fits that limit.

## 11. Impact on retry, rollback, and restart

CompletionPolicy only decides when a chunk ends. It does not by itself provide restart capability for the reader or writer.

When a chunk rolls back:

- Changes in the database that participate in the transaction are undone.
- The chunk's items may be read or processed again, depending on the reader and the retry mechanism.
- The reader and writer need to support appropriate state if the Step is restarted.
- If the writer has effects outside the transaction, idempotency or a reconciliation mechanism is needed.

When restarting a JobInstance, the checkpoint must correctly describe the committed chunk boundary. If the size tracker only holds temporary in-memory data, it is not a checkpoint and does not need to be persisted. CompletionPolicy will create a new accumulator for a new chunk; durable read/write state is managed through the reader/writer's ExecutionContext if the components support it.

With a custom reader or writer, don't store the chunk's total bytes in a shared key and then assume it represents the whole progress of the Job. A chunk's total bytes is only meaningful within the current chunk; a long-term checkpoint needs to store the source position or an appropriate target state.

## 12. Common mistakes

**Confusing bytes with item count.** chunk(100) is a limit on the number of reads, not 100 KB or 100 MB.

**Measuring the wrong quantity.** The size of a UTF-16 String, the number of UTF-8 bytes, the JSON size, and the object memory are different numbers. Choose the metric that fits the goal.

**Limiting bytes without limiting items.** Many small items can still produce a chunk that contains too many objects.

**Believing the byte threshold is a hard limit.** The last item can push the total over the threshold; a single item can be larger than the whole threshold.

**Measuring the payload after the chunk has been created.** If you need to use size to decide where the chunk ends, the weight must be available while the framework is gathering items. Measuring in the writer is too late to decide the current chunk's boundary.

**The tracker is not shared correctly.** If the reader wrapper writes to a different tracker than the one the CompletionPolicy reads, the total bytes is always wrong or zero.

**Using global state for multiple concurrent Jobs.** Executions may accumulate or overwrite each other's weights. State needs to be isolated per StepExecution or per appropriate thread/execution.

**Ignoring oversized items.** A record that exceeds the threshold needs to be handled according to a business rule; don't silently skip it or truncate the data.

**Optimizing based on volume alone.** The database may be limited more by the number of SQL statements, locks, indexes, or latency than by byte count. Measure on a real workload.

## 13. When is a custom size-based policy not needed?

Not every Job needs to commit by bytes.

Using a commit interval by item count is usually appropriate when:

- Item sizes are fairly uniform.
- The writer handles each item at a similar cost.
- Database batch updates work well with a fixed number of items.
- There is no byte-based payload limit.
- The item count is enough to control memory and transaction time.

You can start with SimpleCompletionPolicy or a fixed chunk size, measure processing time, memory, and commit time, and only then switch to a weight-based policy if there is evidence that size variation causes problems.

A custom policy adds complexity because you have to measure sizes, pass information between the reader and the policy, manage scope, and test edge cases. Use it only when a byte-based metric brings clear operational benefits.

## 14. Testing commit by data size

When testing a custom CompletionPolicy, you need to check both the termination condition and the Step's transaction behavior.

| Scenario | What to confirm |
|---|---|
| Total bytes below the threshold | The reader continues providing items |
| An item makes the total reach the threshold | The chunk ends after that item |
| An item makes the total exceed the threshold | The item is kept in the chunk; the chunk ends afterwards |
| Max items reached before max bytes | The chunk ends on the item limit |
| Source runs out before the threshold | The final chunk, smaller than the threshold, is still written |
| A single item larger than the threshold | The item is handled according to the chosen oversize policy |
| An item of size 0 | Does not corrupt the item counter |
| Reader returns null | The tracker does not retain the previous item's weight |
| Two concurrent JobExecutions | The tracker does not mix state between executions |
| Writer error | The chunk rolls back according to the transaction manager |
| Restart after a failure | The reader/writer continues from the committed checkpoint |

You should use data with varying size distributions, not just items of the same length. You can log the item count and the estimated total bytes of each chunk to observe how the policy behaves; avoid logging the full content of items or sensitive data.

Beyond unit tests for the CompletionPolicy, run integration tests with a JobRepository and an appropriate database to confirm that transactions really commit per chunk. Mocking the policy or the transaction manager does not prove the database's rollback behavior.

## 15. Process for choosing a commit threshold

When implementing commit by size, you can follow this sequence:

1. Measure the real item size distribution, including the median, high percentiles, and the largest item.
2. Determine which metric to limit: source bytes, serialized payload, or memory estimate.
3. Choose an initial byte threshold based on the limits of the writer, database, or API.
4. Also set a max item count to avoid chunks containing too many small objects.
5. If needed, set a timeout to limit transaction time.
6. Test items that exceed the threshold and the source running out mid-chunk.
7. Measure read, processing, write, and commit times, memory, and lock contention.
8. Adjust the threshold based on the real workload.
9. Test rollback, retry, and restart with data of varying size.

The commit threshold should not be chosen solely based on the maximum volume the database allows. A 5 MB transaction that runs for several minutes can still cause locks and affect the system. Conversely, many 50 KB chunks can increase commit overhead without bringing significant benefit.

Committing by data size is a way to adjust the chunk boundary when item sizes are uneven. CompletionPolicy provides the extension point to apply that criterion; the reader or a measurement component supplies the item weight; the transaction manager still manages the commit/rollback of each chunk. When you also combine an item count limit, a timeout, oversized-item handling, and restart testing, a Job can control the volume of each write better while still keeping Spring Batch's recovery behavior.

