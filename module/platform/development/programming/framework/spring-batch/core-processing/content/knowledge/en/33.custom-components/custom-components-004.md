# Implementing ItemStream for Stateful Components

In Spring Batch, a stateful component that must retain progress or resources across invocations typically needs to participate in the `ItemStream` lifecycle. This interface lets the framework open the component before `Step` processing begins, save state at checkpoints, and close resources when the `Step` finishes.

`ItemStream` is especially important for custom `ItemReader` and `ItemWriter` implementations. For example, a reader fetching an API by offset needs to save the committed offset; a writer writing files needs to track position or write status; a processing component needs to retain certain durable state across restarts. If state is held only in Java fields, that data disappears when the application process stops and the `Job` cannot resume from the proper progress point.

## 1. What Is ItemStream?

`ItemStream` is Spring Batch's lifecycle contract for components that must open, update, and close state. The interface has three methods:

```java
public interface ItemStream {

    void open(ExecutionContext executionContext) throws ItemStreamException;

    void update(ExecutionContext executionContext) throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

Meaning of each method:

- `open(ExecutionContext)`: open resources and restore saved state from a previous run. If no checkpoint exists yet, initialize starting state.
- `update(ExecutionContext)`: write current state into `ExecutionContext` so Spring Batch can persist it at checkpoints.
- `close()`: release resources such as streams, cursors, file handles, or client sessions.

Reader and writer interfaces combining `ItemStream`:

```java
public interface ItemStreamReader<T> extends ItemReader<T>, ItemStream {
}

public interface ItemStreamWriter<T> extends ItemWriter<T>, ItemStream {
}
```

Accordingly, a stateful custom reader typically implements `ItemStreamReader<T>`, while a stateful writer implements `ItemStreamWriter<T>`. `ItemStream` does not replace `ItemReader` or `ItemWriter`; it adds lifecycle management and state persistence/restoration.

## 2. Why Do Stateful Components Need ItemStream?

A Spring singleton bean can live for the entire application context lifetime. Bean fields exist only in process memory. When a `Job` stops or the JVM crashes, those fields vanish.

Example reader reading an API by offset:

```java
public class ApiReader implements ItemReader<Customer> {

    private long nextOffset;

    @Override
    public Customer read() {
        Customer customer = api.fetch(nextOffset);
        nextOffset++;
        return customer;
    }
}
```

This reader can continue within the same process while `nextOffset` remains in memory. However, if the `Job` commits 500 items and the process stops, a new instance initializes `nextOffset` to 0. The reader restarts from the beginning and can produce duplicate data.

By implementing `ItemStream`, the reader can write the offset into `ExecutionContext` before each commit. On the next restart, `open()` reads the saved offset and resumes from the right position.

Common scenarios requiring `ItemStream`:

- Readers tracking read position in a file, cursor, API, or message source.
- Writers tracking write position, record counts written, or output metadata.
- Components needing to restore a business checkpoint across restarts.
- Components needing to open and close resources aligned with the `Step` lifecycle.
- Delegates inside composite readers/writers that hold their own state.

A stateless service does not need to implement `ItemStream` just to be injected by Spring. Implement it only when the component genuinely has a lifecycle or state that the `Step` must manage.

## 3. Where Does ExecutionContext Store State?

`ExecutionContext` is a key-value map managed by Spring Batch. There are two common scopes:

- **Step ExecutionContext:** state scoped to a single `StepExecution`, commonly used for reader/writer checkpoints.
- **Job ExecutionContext:** state scoped to a `JobExecution`, shareable across `Step`s within the same `JobExecution`.

For a `Step`'s `ItemStream`, the parameter passed to `open()` and `update()` is typically the Step `ExecutionContext`. Spring Batch persists metadata through `JobRepository`, enabling state restoration when a `Job` restarts.

Example reader state:

```java
private static final String OFFSET_KEY = "customerApiReader.nextOffset";

@Override
public void open(ExecutionContext context) {
    nextOffset = context.getLong(OFFSET_KEY, 0L);
}

@Override
public void update(ExecutionContext context) {
    context.putLong(OFFSET_KEY, nextOffset);
}
```

`open()` retrieves the saved value; if the key does not exist, it starts at offset 0. `update()` records the current position so the repository saves it at checkpoints.

Do not treat `ExecutionContext` as storage for arbitrary application data. Store only state needed to resume processing—never large object graphs, open streams, JDBC connections, iterators, or data that can easily be re-queried.

## 4. The open, update, and close Lifecycle in a Step

In a chunk-oriented `Step`, Spring Batch manages the lifecycle of registered streams. Conceptually, the sequence runs as follows:

```text
Step starts
    |
    v
open(executionContext)
    |
    v
read -> process -> write
    |
    v
update(executionContext)
    |
    v
Commit chunk and save checkpoint
    |
    +----> next chunk
    |          |
    |          +--> read -> process -> write
    |          +--> update -> commit
    |
    v
Step ends
    |
    v
close()
```

`open()` is called when the `Step` starts, before the component processes items. `update()` is called at checkpoints, typically before the chunk transaction commits, so state in `ExecutionContext` is saved alongside progress. `close()` releases resources when the `Step` ends.

Crucially: do not use `close()` to save the final checkpoint. `close()` is primarily for releasing resources. Saving state belongs in `update()`.

If `open()`, `read()`/`write()`, `update()`, or `close()` throws an error, the `Step` may fail depending on timing and exception handling. Do not catch and ignore lifecycle errors, as doing so can lose checkpoints or leave resources in an indeterminate state.

## 5. Checkpoints Saved at the Commit Boundary

During chunk processing, a reader may read many items before the writer finishes writing. `update()` allows the component to write state into `ExecutionContext` at the chunk checkpoint. `JobRepository` persists the context alongside `Step` progress according to transaction and repository configuration.

Example with chunk size 100:

```text
Chunk 1: read items 1..100
  update: nextOffset=100
  commit

Chunk 2: read items 101..200
  update: nextOffset=200
  commit

Chunk 3: read items 201..300
  writer fails -> rollback
```

If chunk 3 rolls back, the durable checkpoint must still reflect the last committed chunk—offset 200. On restart, the reader resumes from item 201.

Within the same process, Spring Batch may buffer read items to replay on rollback, depending on reader type and transaction behavior. After a process restart, the in-memory buffer is gone; the reader must use the persisted checkpoint to reposition the source.

Do not persist durable checkpoints on every `read()` call if the goal is chunk-level checkpointing. Writing state to `ExecutionContext` and committing metadata must align with transaction boundaries so state does not move ahead of committed business data.

## 6. Implementing ItemStreamReader Yourself

A stateful custom reader typically implements `ItemStreamReader<T>`. The example below reads data from an API supporting offsets and page sizes. The API is assumed to return a stable page by offset; an empty list means end of data.

```java
public class CustomerApiItemReader implements ItemStreamReader<Customer> {

    private static final String NEXT_OFFSET_KEY = "customerApiReader.nextOffset";
    private static final int PAGE_SIZE = 100;

    private final CustomerApiClient client;

    private long nextOffset;
    private Iterator<Customer> currentPage = Collections.emptyIterator();
    private boolean exhausted;

    public CustomerApiItemReader(CustomerApiClient client) {
        this.client = client;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        nextOffset = context.getLong(NEXT_OFFSET_KEY, 0L);
        currentPage = Collections.emptyIterator();
        exhausted = false;
    }

    @Override
    public Customer read() throws Exception {
        while (!currentPage.hasNext() && !exhausted) {
            List<Customer> page = client.fetch(nextOffset, PAGE_SIZE);

            if (page.isEmpty()) {
                exhausted = true;
                return null;
            }

            currentPage = page.iterator();
        }

        if (!currentPage.hasNext()) {
            return null;
        }

        Customer customer = currentPage.next();
        nextOffset++;
        return customer;
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        context.putLong(NEXT_OFFSET_KEY, nextOffset);
    }

    @Override
    public void close() throws ItemStreamException {
        currentPage = Collections.emptyIterator();
        exhausted = true;
    }
}
```

The example demonstrates three core responsibilities:

- `open()` restores the committed offset and resets the in-memory buffer.
- `read()` gets the next item and increments the offset after returning it.
- `update()` stores the current offset in `ExecutionContext`.
- `close()` releases temporary state in the reader.

This illustrates an API with stable offsets. If an API uses continuation tokens, store both the token and the position within the page so restarts do not drop items. If a fetched page is only partially processed, storing only the next page's token is insufficient; you must store the position to resume inside the current page or use an API capable of fetching from the next item.

Furthermore, offset pagination is safe only when source ordering and the dataset remain stable. If new records are inserted before the current offset, offsets can shift and cause duplicates or missed items. You may need a snapshot ID, watermark, unique sort key, or snapshot-bound continuation token.

## 7. Implementing ItemStreamWriter Yourself

A stateful writer can also implement `ItemStreamWriter<T>`. For instance, a writer may need to persist output metadata such as the number of written records or a logical file position.

```java
public class CountingOrderWriter implements ItemStreamWriter<Order> {

    private static final String WRITTEN_COUNT_KEY = "countingOrderWriter.writtenCount";

    private long writtenCount;

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        writtenCount = context.getLong(WRITTEN_COUNT_KEY, 0L);
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        // Write Orders to destination with appropriate transaction/resource.
        // Increment counter only after write operations in this call succeed.
        writtenCount += chunk.size();
    }

    @Override
    public void update(ExecutionContext context) throws ItemStreamException {
        context.putLong(WRITTEN_COUNT_KEY, writtenCount);
    }

    @Override
    public void close() throws ItemStreamException {
        // Close output resource if writer holds any.
    }
}
```

This illustrates lifecycle state, not a complete file writer. For a real file writer, you must synchronize file position, written contents, and transaction checkpoints. If a file is written outside a transaction and the chunk rolls back, the file may already contain data while `ExecutionContext` reverts to the earlier checkpoint. On restart, the writer could write duplicate records.

For file output, prefer `FlatFileItemWriter` or built-in Spring Batch implementations that already handle state and restarts. If you must build a custom writer, design append/overwrite, truncate/seek, temporary files, atomic publishing, and idempotency explicitly. For database writers, use a proper transaction manager so data and metadata commit consistently.

## 8. Stateful ItemProcessors Can Use ItemStream

Processors should usually be stateless: identical inputs produce identical outputs without depending on prior call order. Still, a processor may need to open resources or hold dedicated state, such as a lookup reference loaded per `StepExecution`.

When that lifecycle is needed, a processor can implement `ItemStream` alongside `ItemProcessor`:

```java
public class ReferenceEnrichmentProcessor
        implements ItemProcessor<Order, EnrichedOrder>, ItemStream {

    private static final String VERSION_KEY = "referenceProcessor.version";

    private final ReferenceService referenceService;
    private String referenceVersion;

    public ReferenceEnrichmentProcessor(ReferenceService referenceService) {
        this.referenceService = referenceService;
    }

    @Override
    public void open(ExecutionContext context) {
        referenceVersion = context.containsKey(VERSION_KEY)
                ? context.getString(VERSION_KEY)
                : referenceService.currentVersion();
    }

    @Override
    public EnrichedOrder process(Order order) {
        return referenceService.enrich(order, referenceVersion);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putString(VERSION_KEY, referenceVersion);
    }

    @Override
    public void close() {
        // Release resource if processor opened any.
    }
}
```

In this example, the processor retains the reference data version so a restart does not accidentally switch to a different version. If a processor simply calls a stateless service, it does not need to implement `ItemStream`.

Stateful processors require special care with retries and rollbacks. A `process()` call may be repeated. Avoid incrementing counters, writing to databases, or sending non-idempotent messages inside a processor just because it holds state.

## 9. Keep ExecutionContext Keys Stable and Collision-Free

`ExecutionContext` is a shared map scoped to a `StepExecution`. If two components write to the same key, the later component overwrites the earlier one's state.

Avoid overly generic keys:

```java
context.putLong("offset", nextOffset);
context.putLong("count", count);
```

Namespace keys by component:

```java
context.putLong("customerApiReader.nextOffset", nextOffset);
context.putLong("orderWriter.writtenCount", writtenCount);
```

Base classes such as `ItemStreamSupport` provide a mechanism to generate execution context keys from a component name. Set a stable component name with `setName(...)` to avoid key collisions when multiple readers or writers exist.

Conceptual example:

```java
public class CustomerReader extends ItemStreamSupport
        implements ItemStreamReader<Customer> {

    private static final String OFFSET = "nextOffset";

    @Override
    public void open(ExecutionContext context) {
        String key = getExecutionContextKey(OFFSET);
        nextOffset = context.getLong(key, 0L);
    }

    @Override
    public void update(ExecutionContext context) {
        String key = getExecutionContextKey(OFFSET);
        context.putLong(key, nextOffset);
    }
}
```

Verify method names and name configuration against your base class and version, though the principle remains: keys must be unique within a `StepExecution` and stable across restarts.

Do not arbitrarily rename readers or state keys while `JobExecution`s remain restartable. If state structure changes, prepare a compatibility or metadata migration strategy.

## 10. Store Only Necessary Data in ExecutionContext

`ExecutionContext` is persisted via `JobRepository`. Consequently, values stored there must be serializable with the configured serializer and small enough for efficient metadata writes.

Appropriate values typically include:

- Committed line or item counts.
- Offsets, page numbers, or continuation tokens.
- Last processed ID.
- Input version/checksum.
- Small business state needed for subsequent `Step`s.

Avoid storing:

- Open `InputStream`, `BufferedReader`, `ResultSet`, `Connection`, or file handles.
- Iterators or parsers holding in-memory state.
- Entire lists of thousands or millions of items.
- Non-serializable objects or unnecessarily large object graphs.
- Sensitive secrets/tokens without appropriate protection.

Open resources must be recreated inside `open()`. `ExecutionContext` stores only enough information to reconstruct the position or state, never the resource handle itself.

## 11. Registering ItemStream with a Step

When a reader or writer is passed directly to a `Step` and its implementation also implements `ItemStream`, standard Spring Batch `Step` configurations register that component's lifecycle automatically.

Example:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerApiItemReader)
        .writer(customerWriter)
        .build();
```

If a reader/writer is wrapped inside a delegate or composite and the stateful component is hidden behind the wrapper, the `Step` may not automatically discover the delegate as a stream. In that case, register the stream explicitly:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(compositeReader)
        .writer(compositeWriter)
        .stream(delegateReader)
        .stream(delegateWriter)
        .build();
```

Alternatively, the wrapper/composite can implement `ItemStream` itself and forward the three callbacks to its delegates:

```java
@Override
public void open(ExecutionContext context) {
    delegateReader.open(context);
}

@Override
public void update(ExecutionContext context) {
    delegateReader.update(context);
}

@Override
public void close() {
    delegateReader.close();
}
```

If a composite has multiple delegates, ensure every stream is opened, updated, and closed exactly once. If a delegate fails in `open()`, close any previously opened resources.

## 12. What Happens If You Forget to Register a Stream?

If a component implements `ItemStream` but is not registered with the `Step`, Spring Batch may never call `open()`, `update()`, or `close()` on it.

Consequences can include:

- The reader does not restore its offset from `ExecutionContext`.
- The writer does not save checkpoints.
- Resources are not closed properly in the lifecycle.
- Restarts begin from the start or resume at the wrong position.
- Delegate state is not saved even though the outer wrapper runs.

A common symptom is that the first run succeeds, yet a restart after failure re-reads already committed data. When investigating, check whether the component implements `ItemStream` and is registered directly or via `.stream(...)`.

Do not rely merely on a class having methods named `open`, `update`, and `close`. It must implement the actual interface and have its lifecycle managed by the `Step`.

## 13. Using AbstractItemCountingItemStreamItemReader

Spring Batch provides `AbstractItemCountingItemStreamItemReader<T>` to reduce boilerplate for custom readers that can recover by item count. This base class manages the item count and saves/restores it in `ExecutionContext`; subclasses focus on opening the source, reading items, and repositioning the source.

A custom reader can follow this pattern:

```java
public class CustomOrderReader
        extends AbstractItemCountingItemStreamItemReader<Order> {

    private BufferedReader reader;

    public CustomOrderReader(Resource resource) {
        setName("customOrderReader");
        setSaveState(true);
        this.resource = resource;
    }

    @Override
    protected void doOpen() throws Exception {
        // Open resource and prepare reader.
    }

    @Override
    protected Order doRead() throws Exception {
        // Read and return next item; null on EOF.
        return null;
    }

    @Override
    protected void doClose() throws Exception {
        // Close reader/resource.
    }

    @Override
    protected void jumpToItem(int itemIndex) throws Exception {
        // Reposition source to itemIndex on restart.
    }
}
```

This is an illustrative skeleton. Declare the `resource` field and implement methods according to the Spring Batch version in your project. The base class manages counts and checkpoints; `jumpToItem(...)` must actually position the input source to the corresponding index.

This base class fits sources addressable by item count, such as line-based files or stably ordered lists. If the source uses continuation tokens or complex cursors, implementing `ItemStreamReader` directly can be a better fit.

## 14. In-Memory State vs. Committed State

Components typically have two forms of state:

- **In-memory state:** fields changing inside the process while reading/writing items.
- **Checkpoint state:** values written to `ExecutionContext` and durably persisted by the repository.

These two can diverge while a chunk is in flight. For example, the reader may have read up to item 250 in memory while the last checkpoint is only at item 200 because the current chunk has not committed yet.

```text
Committed checkpoint: item 200
          |
          v
Reader continues reading items 201..250
          |
          v
Writer fails, transaction rolls back
          |
          v
Durable checkpoint remains item 200
```

When restarting after a process failure, the reader must use the committed checkpoint, not in-memory fields from the old process. If the component reads from a non-replayable source, you need source-level transactions or an appropriate offset/idempotency mechanism.

Do not write `ExecutionContext` to another store after every `read()` without coordinating transactions with `JobRepository`. Doing so can push the offset ahead of committed business outputs.

## 15. Rollback and ItemStream

`ItemStream.update()` is called at the checkpoint before committing a chunk. When a chunk transaction rolls back, checkpoint metadata stored under the same transaction/repository configuration is normally rolled back to the previous checkpoint.

However, a database rollback does not automatically rewind all external resources. A custom reader may have consumed a queue message, called an API, or advanced a cursor. Determine whether the reader is transactional:

- Non-transactional readers typically have their read items buffered by Spring Batch for in-process replay on rollback.
- Transactional readers like queues can return items to the source on transaction rollback; configure the reader and transaction properly so you do not both buffer and redeliver the same item.
- After a process restart, the in-memory buffer is lost and the reader recovers from the persisted checkpoint.

For non-transactional sources, design replay/idempotency or store a checkpoint capable of reconstructing the exact next item. Do not assume implementing `ItemStream` alone undoes source-side effects.

## 16. Restart Requires the Same JobInstance and a Stable Source

To restore `StepExecution` properly, the `Job` must restart within the same `JobInstance`. That normally requires keeping the identifying `JobParameters` unchanged.

Beyond `JobParameters`, the data source must also remain stable:

- Files must not be overwritten or reordered.
- Queries must have a deterministic `ORDER BY`, and datasets must not shift unexpectedly.
- API offsets/tokens must point to the same snapshot or data version.
- Reader names and `ExecutionContext` keys must not change arbitrarily.
- The `ExecutionContext` serializer must still be able to read state saved by previous versions.

For example, suppose a reader stores `lastProcessedId=500`. If on restart the query order changes or ID 500 no longer represents the same boundary, the reader may skip or duplicate items. For mutable sources, use a snapshot ID, watermark, or manifest to pin the dataset.

If state format changes across deployments, consider adding a version key:

```java
context.putInt("customerReader.stateVersion", 2);
context.putLong("customerReader.nextOffset", nextOffset);
```

In `open()`, check the version and handle compatibility or fail explicitly if legacy state is unusable. Never interpret an old key using a new format without migration.

## 17. Handling Exceptions in the Lifecycle

`ItemStream` methods declare `ItemStreamException`. Wrap I/O or state-restoration errors with this exception so Spring Batch recognizes lifecycle failures:

```java
@Override
public void open(ExecutionContext context) throws ItemStreamException {
    try {
        openRemoteSession();
        nextOffset = context.getLong(NEXT_OFFSET_KEY, 0L);
    } catch (RuntimeException ex) {
        closeRemoteSessionQuietly();
        throw new ItemStreamException("Cannot open customer API reader", ex);
    }
}
```

Principles:

- If `open()` fails after partially opening resources, attempt to release already opened resources.
- Do not swallow exceptions in `update()`; if the checkpoint failed to write properly, the `Step` should not proceed as if state were saved.
- `close()` should release resources and tolerate repeated close calls safely if the lifecycle invokes it after an error.
- Do not write new checkpoints in `close()` instead of `update()`.
- Exception messages should identify the relevant component and resource while avoiding exposing secrets or sensitive data.

## 18. Thread Safety of ItemStream

`ItemStream` does not automatically make a component thread-safe. If multiple threads call `read()` or `write()` on the same instance, state fields like offset, iterator, or file position can suffer concurrent updates.

In a multi-threaded `Step`, a component bound to `StepExecution` can be shared across multiple worker threads. Check whether the reader/writer supports concurrent access.

Design options:

- Prefer per-partition state via a partitioned `Step`, where each partition gets its own `StepExecution` and target bean.
- Use stateless components or immutable state where possible.
- If mutable state must be shared, use proper synchronization/atomics and preserve business ordering.
- Do not share a single file cursor or API offset across multiple threads if the source does not support concurrent partitioning.
- Do not let multiple partitions write to the same `ExecutionContext` key or the same output file without clear partitioning.

`@StepScope` creates a target instance per `StepExecution`; it does not create one instance per thread. Scope and thread safety are separate concerns.

## 19. ItemStream and Delegate/Composite Components

A composite reader may coordinate multiple delegate readers. If the delegates are stateful, the composite must manage each delegate's lifecycle or the `Step` must register each delegate stream.

Example:

```java
public class CustomerCompositeReader
        implements ItemStreamReader<Customer> {

    private final ItemStreamReader<Customer> first;
    private final ItemStreamReader<Customer> second;

    public CustomerCompositeReader(
            ItemStreamReader<Customer> first,
            ItemStreamReader<Customer> second) {
        this.first = first;
        this.second = second;
    }

    @Override
    public void open(ExecutionContext context) {
        first.open(context);
        second.open(context);
    }

    @Override
    public Customer read() throws Exception {
        Customer item = first.read();
        return item != null ? item : second.read();
    }

    @Override
    public void update(ExecutionContext context) {
        first.update(context);
        second.update(context);
    }

    @Override
    public void close() {
        first.close();
        second.close();
    }
}
```

This is a conceptual example; a real composite must handle partial open/close failures if a delegate throws and avoid duplicate `ExecutionContext` keys. If both delegates use identical keys, their state will overwrite each other. Each delegate needs its own name/key.

Another option is having the composite only read data while registering the delegates via `.stream(first).stream(second)` on the `Step`. Pick one place to own the lifecycle and avoid calling `open/update/close` twice on the same delegate.

## 20. Common Misconceptions

**Assuming implementing ItemStream automatically persists all fields.** Only values written into `ExecutionContext` inside `update()` are saved across checkpoints.

**Saving state inside close().** `close()` is for releasing resources; checkpoints belong in `update()`.

**Storing InputStream or Connection in ExecutionContext.** Open handles cannot be restored across process restarts. Store only the data needed to reopen and reposition the resource.

**Forgetting to register delegate streams.** If a stream is hidden inside a wrapper, the `Step` may never call its lifecycle. Register via `.stream(...)` or forward the lifecycle from the composite.

**Using generic keys across components.** Components can overwrite each other's state. Use namespaced keys and stable component names.

**Updating checkpoints after every read and treating that as a commit.** In-memory state can advance ahead of committed data. Update `ExecutionContext` at framework-managed checkpoints.

**Assuming rollback automatically rewinds all sources.** Files, APIs, and message sources behave differently. Design appropriate replay, transactions, or idempotency.

**Assuming @StepScope makes a stream thread-safe.** One target bean can be shared by multiple threads within the same `StepExecution`.

**Changing keys or state formats incompatibly.** In-flight jobs may fail to read old checkpoints. Keep keys stable or version state explicitly.

## 21. Testing ItemStream

A restart test must verify both that state is written and that a new instance restores it.

Example unit test for an offset-based reader:

```java
@Test
void restoresOffsetFromExecutionContext() throws Exception {
    CustomerApiClient client = new FakeCustomerApiClient();
    CustomerApiItemReader reader = new CustomerApiItemReader(client);

    ExecutionContext firstContext = new ExecutionContext();
    reader.open(firstContext);

    reader.read();
    reader.read();
    reader.update(firstContext);
    reader.close();

    CustomerApiItemReader restartedReader = new CustomerApiItemReader(client);
    restartedReader.open(firstContext);

    Customer next = restartedReader.read();

    assertEquals(3L, next.getId());
    restartedReader.close();
}
```

This illustrates testing the offset contract. The fake API must return stable data by offset, and the test should adjust sample IDs accordingly.

Cases worth testing:

1. `open()` with no key: component starts from the beginning.
2. `open()` with a checkpoint: component restores the right position.
3. `update()` writes expected state and avoids non-serializable objects/resources.
4. Creating a new instance and opening with the old `ExecutionContext`: reads the next item without repeating committed items.
5. `close()` releases resources when the `Step` completes and when an error occurs.
6. Two components in the same `Step` use distinct keys.
7. Delegate streams are registered and lifecycle methods are invoked the exact expected number of times.
8. Rolling back a chunk does not advance the durable checkpoint past committed data.
9. Restarting with a different input version is detected or handled per policy.
10. Running partitioned/multi-threaded tests confirms state is not improperly shared.

Unit tests with `ExecutionContext` verify open/update logic. Integration tests against a real `JobRepository` and transaction manager confirm checkpoints save alongside chunk commits and are reused on `Job` restart.

## 22. How to Design Stateful Components

First, determine whether state needs to live across a single chunk, across a `StepExecution`, or across a `JobExecution`. If data is temporary within one call, do not put it in `ExecutionContext`. If restartability is needed, implement `ItemStream` and save a small, stable, serializable checkpoint.

Use `open()` to create resources and restore state; use `update()` to save state at commit boundaries; use `close()` to release resources. Use namespaced keys and keep component names stable. Ensure the `Step` recognizes the stream directly or registers delegates explicitly.

When implementing a reader, ensure the source can be repositioned from the checkpoint or supports transaction/replay semantics. When implementing a writer, ensure side effects and checkpoints do not drift apart after rollbacks. For processors, prefer statelessness and use `ItemStream` only when a dedicated lifecycle/state is truly necessary.

Test by saving `ExecutionContext`, instantiating a fresh component, and confirming it resumes at the right position. Then run integration tests across rollbacks and restarts with a real `JobRepository`. `ItemStream` provides the lifecycle and checkpoint foundation; final correctness still depends on how the component manages its own resources, transactions, data sources, and side effects.
