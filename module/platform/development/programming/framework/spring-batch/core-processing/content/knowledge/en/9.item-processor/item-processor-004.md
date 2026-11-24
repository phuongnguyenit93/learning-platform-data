# Stateless and stateful processors

In Spring Batch, `ItemProcessor<I, O>` receives an input item, performs a transformation or validation, and returns an output item. A processor can be designed as **stateless** (it holds no changing state that depends on previously processed items) or **stateful** (it holds data in the object and may depend on the processing history).

A stateless processor is typically easier to test, easier to run in parallel, and safer when Spring Batch retries an item. A stateful processor can be useful when you need to cache reference data, check ordering, or maintain information across items, but you need to design the lifecycle, checkpoint, rollback, and concurrency explicitly. A processor that has a field does not automatically become restartable; state that must survive a restart has to be stored using an appropriate mechanism.

## 1. The role of ItemProcessor

In chunk-oriented processing, Spring Batch reads items with `ItemReader`, passes each item through `ItemProcessor`, and then sends the remaining results to `ItemWriter`:

```text
ItemReader
    |
    v
ItemProcessor.process(item)
    |
    +--> Return a new or transformed object
    |          |
    |          v
    |       ItemWriter
    |
    +--> Return null: filter the item, do not send it to the writer
```

The basic interface:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

A processor typically takes on tasks such as normalizing data, checking business rules, computing derived fields, converting data types, or deciding whether an item is eligible to move forward.

`process()` can return an object of the same type or a different type. If it returns `null`, Spring Batch considers the item filtered and does not pass it to the writer. If the processor throws an exception, the Step handles it according to the fault-tolerance, retry, and skip configuration, if any.

## 2. What is a stateless processor?

A stateless processor does not keep changing state from one `process()` call to the next. The result of processing an item depends only on that item and on stable rules or configuration data.

For example, a processor that normalizes an order:

```java
public class NormalizeOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        String normalizedCustomerCode =
                order.getCustomerCode().trim().toUpperCase(Locale.ROOT);

        return new Order(
                order.getId(),
                normalizedCustomerCode,
                order.getAmount().setScale(2, RoundingMode.HALF_UP)
        );
    }
}
```

Each `process()` call is independent of the items processed before it. If Spring Batch calls the processor again for the same item because of a retry or rollback, the result remains consistent as long as the input and the processing rules do not change.

Another example is filtering out invalid orders:

```java
public class EligibleOrderProcessor
        implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.getAmount().signum() <= 0) {
            return null;
        }

        return order;
    }
}
```

The processor does not need to remember the number of items processed or the previous order ID. It only decides whether the current item is passed on.

### Characteristics of a stateless processor

- It has no mutable field that stores the progress or results of previous items.
- It does not depend on the order in which `process()` is called, unless the business requires an order.
- It is easy to unit test because each test can check one specific input and output.
- It is easy to reuse across multiple Steps or Jobs if its dependencies are safe to share.
- It is generally better suited to retry, multi-threaded Steps, and partitioning.

Stateless does not mean the processor may not have fields. Immutable dependencies such as configuration, a mapper, or a service can be injected. What matters is that the processor does not modify shared state on a per-item basis and does not let the result depend on the call history.

## 3. What is a stateful processor?

A stateful processor holds one or more values that persist between `process()` calls. The result can depend on items processed earlier, or the object can maintain a cache and resources that are opened throughout the Step's lifecycle.

Some cases may need state:

- Caching reference data to avoid repeated queries for each item.
- Checking whether a sequence of items is in the correct order.
- Detecting a business key that has already appeared in the same data stream.
- Computing accumulated figures or state that depends on previous items.
- Holding resources that are opened while the Step executes, such as a dedicated parser or client.

A simple example of accumulated state:

```java
public class RunningTotalProcessor
        implements ItemProcessor<Order, OrderWithRunningTotal> {

    private BigDecimal runningTotal = BigDecimal.ZERO;

    @Override
    public OrderWithRunningTotal process(Order order) {
        runningTotal = runningTotal.add(order.getAmount());

        return new OrderWithRunningTotal(order, runningTotal);
    }
}
```

The result for the current item depends on the total of the previously processed items. This is a genuinely stateful processor. However, this example only illustrates the concept; it does not handle checkpoint storage, rollback, or concurrent calls. You should not use this prototype in a Job that needs retry, restart, or multiple threads.

## 4. Distinguishing object state from state that needs restart

Not all state in a processor needs to be saved to the `ExecutionContext`. You need to distinguish at least two kinds:

| State type | Example | How to handle it |
|---|---|---|
| A cache that can be rebuilt | A product map loaded from a catalog table when the Step opens | Reload it within the Step's lifecycle; there is no need to serialize the cache |
| State that depends on item progress | The last processed sequence, the set of keys already seen | Needs a checkpoint, or must be stored in a suitable data store if it must be recovered after a restart |

A processor can have a field and still produce stable results if that field is a read-only cache built from reference data that does not change during the run. Conversely, a processor that holds a counter or a list of items already seen can change its results depending on history and needs more careful handling.

`@StepScope` helps create a bean bound to a `StepExecution` and allows injecting JobParameters or the StepExecutionContext. It does not automatically serialize the bean's fields, does not automatically create a checkpoint, and does not automatically make the processor safe when multiple threads call it. To make state survive a restart, you need to store it using the `ExecutionContext` or another durable mechanism.

## 5. A stateful processor that uses a read-only cache

A safer way to use state is to load reference data once when the Step opens, then only read the cache in `process()`. For example, each order needs to be enriched with the product group name from a catalog table.

```java
public class ProductEnrichmentProcessor
        implements ItemProcessor<Order, EnrichedOrder>, ItemStream {

    private final ProductRepository productRepository;
    private Map<String, Product> productsById = Map.of();

    public ProductEnrichmentProcessor(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        Map<String, Product> loaded = productRepository.findAll().stream()
                .collect(Collectors.toMap(Product::getId, Function.identity()));
        productsById = Map.copyOf(loaded);
    }

    @Override
    public EnrichedOrder process(Order order) {
        Product product = productsById.get(order.getProductId());
        if (product == null) {
            throw new IllegalArgumentException("Unknown product: " + order.getProductId());
        }

        return new EnrichedOrder(order, product.getCategory());
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // The cache is reloaded in open(), so there is no need to store the whole Map in the context.
    }

    @Override
    public void close() {
        productsById = Map.of();
    }
}
```

In this example, the processor holds the cache in a field but does not change the cache while processing each item. `Map.copyOf()` creates a map that cannot be modified through this reference. When the Step is restarted, `open()` reloads the cache from the repository. Because the cache is rebuilt, there is no need to put the entire catalog data into the ExecutionContext.

Register the processor as a stream of the Step so the framework calls the `ItemStream` callbacks:

```java
@Bean
public Step enrichOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ProductEnrichmentProcessor processor,
        ItemWriter<EnrichedOrder> writer) {

    return new StepBuilder("enrichOrdersStep", jobRepository)
            .<Order, EnrichedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .stream(processor)
            .build();
}
```

With a large cache, loading the whole table into memory may not be appropriate. You can use a size-bounded cache, a lookup service with caching, or join the data in the reader's query. You also need to determine whether the reference data is allowed to change between restarts; if the result must be absolutely consistent, use a version or snapshot of the reference data.

## 6. A stateful processor that depends on item history

A processor may need to know the previous item to check ordering or detect duplicate data. For example, the data source is required to be sorted by ascending sequence. The processor holds the last processed sequence:

```java
public class IncreasingSequenceProcessor
        implements ItemProcessor<Order, Order>, ItemStream {

    private static final String LAST_SEQUENCE_KEY = "sequenceProcessor.lastSequence";
    private long lastSequence;

    @Override
    public void open(ExecutionContext executionContext) {
        lastSequence = executionContext.getLong(LAST_SEQUENCE_KEY, 0L);
    }

    @Override
    public Order process(Order order) {
        if (order.getSequence() <= lastSequence) {
            throw new IllegalStateException("Input sequence is not increasing");
        }

        lastSequence = order.getSequence();
        return order;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(LAST_SEQUENCE_KEY, lastSequence);
    }

    @Override
    public void close() {
        // There are no external resources to close.
    }
}
```

With a processor like this, you need to register it as a stream so that `open()` and `update()` are called. `open()` restores the saved sequence; `update()` writes the current state to the Step ExecutionContext at the checkpoint.

This is an illustrative example of the state-saving mechanism, not a safe pattern for every fault-tolerance configuration. If the chunk rolls back or the processor is called again due to a retry, the in-memory `lastSequence` field may have advanced even though the transaction has not committed. An `ExecutionContext` that is rolled back with the transaction does not automatically return the Java field in the processor to its old value. The processor needs a rollback-aware strategy, such as separating the chunk's temporary state from the committed state, or avoiding holding history-dependent state in the processor when the Step has complex retry/skip.

For important duplicate-detection or uniqueness-check logic, consider using a unique constraint, a staging table, or a state store with an appropriate transaction. Do not rely entirely on a `HashSet` in the processor to guarantee uniqueness across runs and restarts.

## 7. How do retry and rollback affect a stateful processor?

Spring Batch can call the processor again in some fault-tolerance situations. For example, an item may be reprocessed on a retry after an exception, or the whole chunk may be re-executed after a rollback depending on the error type and configuration.

A stateless processor has an advantage here: calling it again with the same input and the same rules usually produces the same output. A stateful processor may have changed a field in the previous call, so the repeated call can produce a different result or cause a counter to be incremented twice.

For example, a processor that increments a counter in `process()`:

```java
private long processedCount;

@Override
public Order process(Order order) {
    processedCount++;
    return order;
}
```

If the chunk rolls back and the item is reprocessed, `processedCount` may include uncommitted processing attempts. This is not necessarily the number of items successfully processed. You should not use a field like this to report official figures; use counters managed by `StepExecution` or update the figures after the chunk commits.

Some principles when a processor has state:

- Avoid side effects that cannot be rolled back in `process()`, such as sending email, calling an API that creates a transaction, or writing data directly outside the transaction.
- If a side effect must be performed, design an idempotency key or move the operation to a suitable writer/after-commit/outbox.
- Distinguish committed state from state that is changing in the current chunk.
- Do not assume that writing the ExecutionContext will automatically roll back in-memory fields.
- Test the case where the writer fails after the processor has processed the whole chunk, item retry, and restart after the process is stopped.

## 8. Stateful processors and multi-threaded execution

In a multi-threaded Step, multiple threads can call the same processor instance. If the processor contains a mutable field, the threads can read and write that field concurrently, causing a race condition or results that depend on thread ordering.

A dangerous example:

```java
public class UnsafeCounterProcessor implements ItemProcessor<Order, Order> {

    private long count;

    @Override
    public Order process(Order order) {
        count++;
        return order.withSequence(count);
    }
}
```

With multiple threads, two items can receive the same sequence or the sequence order may not reflect the business order. Using `AtomicLong` only protects the increment operation; it does not guarantee business ordering, restartability, or rollback correctness.

Design options:

- Prefer a stateless processor and immutable dependencies.
- If the state is only a cache, load an immutable cache before processing and ensure it is safe for multiple threads to read.
- If state must be separated per worker, use partitioning so each partition has its own `StepExecution` and state; design the bean scope and stream for each partition.
- If state must be shared among multiple threads, use a synchronization mechanism or a state store with a clear transaction, while weighing the performance impact.
- Do not assume `@StepScope` automatically makes a bean safe when multiple threads in the same Step call it.

## 9. Processor scope in Spring

A processor is usually declared as a singleton bean. If it is stateless and its dependencies are safe to share, a singleton can be appropriate. If the processor needs configuration or state specific to each StepExecution, you can use `@StepScope`:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> orderProcessor(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return order -> enrichForBusinessDate(order, businessDate);
}
```

Step scope allows injecting JobParameters at the time the Step runs and creates a target bound to the StepExecution. However:

- Scope does not automatically store fields in the JobRepository.
- To store state across restarts, the processor still needs `ItemStream` or its own persistence mechanism.
- With a multi-threaded Step, multiple threads can use the processor of that StepExecution together; mutable state still needs concurrency handling.
- With partitioning, each partition has its own StepExecution, so state can be organized per partition.

If the processor only needs to read JobParameters and holds no changing state, you can keep the stateless design and use Step scope only to obtain parameters at runtime.

## 10. Composite processors and delegate state

Spring Batch lets you chain multiple processors with `CompositeItemProcessor`. Each delegate processes the output of the previous delegate:

```text
Order
  |
  v
NormalizeProcessor
  |
  v
ValidateProcessor
  |
  v
EnrichProcessor
  |
  v
ItemWriter
```

An example configuration:

```java
@Bean
public CompositeItemProcessor<Order, EnrichedOrder> orderProcessor(
        ItemProcessor<Order, Order> normalizeProcessor,
        ItemProcessor<Order, Order> validateProcessor,
        ItemProcessor<Order, EnrichedOrder> enrichProcessor) {

    return new CompositeItemProcessorBuilder<Order, EnrichedOrder>()
            .delegates(normalizeProcessor, validateProcessor, enrichProcessor)
            .build();
}
```

If a delegate needs the `ItemStream` lifecycle, you must ensure that delegate is registered with the Step so the `open`, `update`, and `close` callbacks are invoked. Depending on the composite's structure and the framework version, you should not assume that every delegate stream is detected automatically. You can register it explicitly with `.stream(delegate)` in the Step configuration.

The state of each delegate needs to be evaluated separately. A composite made up of stateless processors is still simple to run concurrently; a single unsafe stateful delegate can make the whole pipeline not thread-safe or not restart correctly.

## 11. Testing stateless and stateful processors

For a stateless processor, a unit test usually only needs an input and the expected output:

```java
@Test
void normalizesCustomerCode() {
    NormalizeOrderProcessor processor = new NormalizeOrderProcessor();
    Order input = new Order(10L, "  ab-01 ", new BigDecimal("12.345"));

    Order output = processor.process(input);

    assertEquals("AB-01", output.getCustomerCode());
    assertEquals(new BigDecimal("12.35"), output.getAmount());
}
```

For a stateful processor, in addition to each item's result, you need to test the lifecycle and the state:

- `open()` with an empty context creates the correct initial state.
- `update()` writes the correct checkpoint to the ExecutionContext.
- A new instance that calls `open()` with a saved context can restore the state.
- After a restart, the next item is processed correctly according to the committed state.
- Chunk rollback and retry do not push the state beyond the committed progress.
- Multiple threads do not corrupt the state if the Step is configured to run in parallel.

Testing a stateful processor should include writer-error scenarios as well, because an error can occur after the processor has already updated a field. Testing only a sequence of consecutive successful items is not enough to prove that the processor is safe on restart.

## 12. Common misconceptions

**Believing every processor must be stateless.** Stateless is a good default choice, but stateful can be useful with caches, sequence checks, or logic that needs history. What matters is managing the state correctly across its lifecycle.

**Believing that having a field means the state has been saved.** A field exists only in the Java object. To recover after a restart, you must store the state in the ExecutionContext or another durable store.

**Believing `@StepScope` automatically makes a processor restartable.** Step scope manages the bean's scope per StepExecution; it does not automatically serialize fields or store checkpoints.

**Believing `AtomicLong` solves every multi-threading problem.** Atomic only protects atomic operations. It does not solve business ordering, rollback, checkpointing, or idempotency.

**Creating side effects in `process()`.** The processor can be called again due to retry/rollback. A side effect outside the transaction can occur multiple times or fail to match the committed result.

**Using state in the processor as the official committed figure.** A field can increase during a chunk rollback. Use StepExecution counters or record after commit for actual figures.

## 13. Choosing the right processor type

Prefer a stateless processor when each item can be processed independently. If you need a cache, use immutable reference data and rebuild the cache within the Step's lifecycle. If the business genuinely depends on item history, clearly define that the state belongs to a single StepExecution, store a checkpoint when restart is needed, and handle rollback, retry, skip, and multi-threaded execution separately.

A good processor does not merely produce the correct output in one favorable run. It must also keep its behavior consistent when an item is reprocessed, a chunk rolls back, the Job restarts, or the Step runs in parallel. A stateless design usually makes those requirements simpler; stateful can still be used when the state's scope and lifecycle are clearly managed.
