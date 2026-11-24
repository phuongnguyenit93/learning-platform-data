# Saving State with ExecutionContext

In Spring Batch, a custom reader or writer often needs to remember progress across chunks and restore that progress when a job is restarted. For example, a reader needs to know the next record to read, a writer needs to know how far data has been written, or a component needs to remember the current file or partition.

Runtime values stored in Java fields do not survive after a process stops. Spring Batch provides `ExecutionContext` to store the state of a `StepExecution` or `JobExecution`, along with the `ItemStream` contract so components can open resources, update checkpoints, and close resources across the step lifecycle.

When configured properly, the framework persists `ExecutionContext` through `JobRepository` at chunk checkpoint boundaries. A subsequent execution of the same `JobInstance` can read back the saved context and resume work.

`ExecutionContext` is only a storage mechanism for recoverable state. It does not make a custom component restartable on its own. The component must define what state to save, restore that state in `open`, update it in `update`, and ensure the data source retains the same meaning on restart.

## 1. Why Do Custom Components Need to Save State?

A custom reader might read data from an API, file, database cursor, or internal source. After each chunk, Spring Batch needs to know what portion of the data has been committed so a restart neither drops items nor unexpectedly reprocesses them.

Example job reading 1,000 records with chunk size 100:

```text
Chunk 1: read records 1..100    -> write succeeded -> COMMIT
Chunk 2: read records 101..200  -> write succeeded -> COMMIT
Chunk 3: read records 201..300  -> error before commit

Restart same JobInstance:
  restore committed checkpoint at record 200
  resume from record 201
```

If the reader keeps `currentIndex` only in a Java field, that value is lost when the JVM or process terminates. `ExecutionContext` stores a durable representation of the checkpoint so the next execution can recover.

State commonly needing persistence includes:

- Committed read position, such as item index, page number, or last processed key.
- Current filename and position within a file list.
- Processed watermark or timestamp boundary.
- Serializable and reusable pagination/cursor tokens.
- Small state needed to resume a writer or custom tasklet.

Not every field in a component needs to be saved. Save only the information necessary to reconstruct runtime state after a restart.

## 2. What Is ExecutionContext?

`ExecutionContext` is a key/value map managed by Spring Batch. It lets components store serializable values and retrieve them in a later execution.

There are two main scopes:

| Context type | Scope | When to use |
|---|---|---|
| Step `ExecutionContext` | One `StepExecution` | Store checkpoints private to a reader, writer, or worker step |
| Job `ExecutionContext` | One `JobExecution` | Store data that needs to be shared across steps in the same job execution |

Readers and writers usually store checkpoints in the Step `ExecutionContext` passed to `ItemStream.open` and `ItemStream.update`. Because this context belongs to the running step, each worker/partition can hold independent state.

Job context is suitable for data passed from one step to another. Avoid using job context for item-level state when that data belongs only to a single step or partition.

## 3. ItemStream as the Lifecycle Contract

A custom component participating in checkpointing typically implements `ItemStream`. The interface has three primary callbacks:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Meaning:

| Callback | When invoked | Responsibility |
|---|---|---|
| `open` | When the step opens the component | Initialize resources and restore state from context |
| `update` | When the framework updates checkpoints | Write current state into context |
| `close` | When the step closes the component | Release resources and runtime state |

Readers typically implement `ItemStreamReader<T>`; writers typically implement `ItemStreamWriter<T>`. Both interfaces combine the read/write contract with `ItemStream`.

```java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}

public interface ItemStreamWriter<T>
        extends ItemWriter<T>, ItemStream {
}
```

A class implementing only `ItemReader<T>` or `ItemWriter<T>` without `ItemStream` will not automatically provide a checkpoint lifecycle to Spring Batch. If a custom component needs restartability, implement the appropriate stream interface or register the corresponding stream with the step.

## 4. The open, update, and close Lifecycle

General lifecycle of a custom reader in a chunk step:

```text
Step starts
    |
    v
reader.open(stepExecutionContext)
    |
    v
Read items and process chunk
    |
    v
reader.update(stepExecutionContext)
    |
    v
JobRepository saves checkpoint per appropriate transaction
    |
    +--> COMMIT: checkpoint is saved
    |
    +--> ROLLBACK: uncommitted chunk checkpoint does not become restart point
    |
    v
Repeat for next chunk
    |
    v
reader.close()
```

`open` must handle both situations: the context lacks state keys because this is the first run, or the context already contains keys because this is a restart.

`update` should write current state to the context deterministically. The framework may invoke this callback at multiple checkpoints; writing the same value to the same key should never create business side effects.

`close` is for closing cursors, streams, sockets, or runtime resources. Do not treat `close` as the sole place to persist checkpoints, since `close` is also invoked when a step ends in failure or is stopped.

## 5. Storing Namespaced Keys

A single `ExecutionContext` may hold state from multiple streams within the same step. Therefore, keys must be stable and collision-free.

Avoid overly generic keys such as:

```java
executionContext.putInt("index", currentIndex);
```

If two custom readers both write the `index` key, one component can overwrite the other's state.

Namespace keys by component name and state meaning:

```java
executionContext.putInt(
    "orderReader.currentIndex",
    currentIndex
);
```

You can use `ItemStreamSupport` to build keys scoped by the bean/component name. `ItemStreamSupport` also provides stream name management.

```java
public class IndexedOrderReader
        extends ItemStreamSupport
        implements ItemStreamReader<Order> {

    private static final String INDEX_KEY = "currentIndex";

    // ...
}
```

Assign a stable name in the constructor:

```java
public IndexedOrderReader(List<Order> orders) {
    this.orders = List.copyOf(orders);
    setName("indexedOrderReader");
}
```

Using `getExecutionContextKey(INDEX_KEY)`, the key is built from the stream name and the state suffix. This lets multiple streams share suffixes like `currentIndex` without overwriting each other.

Do not name streams using timestamps, random UUIDs, or values that change across restarts. If the name changes, the component may fail to locate its previous checkpoint key.

## 6. Example Custom Reader Saving Read Position

The following example demonstrates a reader reading from an immutable list. Its goal is to show how a custom component saves and restores an item index; in production, large datasets should be read via cursors, pages, or keysets rather than loaded entirely into a `List`.

```java
public class IndexedOrderReader
        extends ItemStreamSupport
        implements ItemStreamReader<Order> {

    private static final String INDEX_KEY = "currentIndex";

    private final List<Order> orders;
    private int currentIndex;

    public IndexedOrderReader(List<Order> orders) {
        this.orders = List.copyOf(orders);
        setName("indexedOrderReader");
    }

    @Override
    public void open(ExecutionContext executionContext) {
        String key = getExecutionContextKey(INDEX_KEY);

        if (executionContext.containsKey(key)) {
            currentIndex = executionContext.getInt(key);
        } else {
            currentIndex = 0;
        }
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }

        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(
            getExecutionContextKey(INDEX_KEY),
            currentIndex
        );
    }

    @Override
    public void close() {
        // No external resources to close in this example.
    }
}
```

How it works:

1. Initially, `open` does not find the key, so it sets `currentIndex = 0`.
2. Each time `read` returns an order, the index increments.
3. When the framework updates checkpoints, `update` saves the index into the Step `ExecutionContext`.
4. On restart of the same `JobInstance`, `open` reads the stored index and resumes from the matching position.

The sample reader keeps all data in memory for clarity. For databases, APIs, or large files, state should usually be a last key, page token, file position, or reproducible cursor marker.

## 7. Using AbstractItemCountingItemStreamItemReader

Spring Batch provides the base class `AbstractItemCountingItemStreamItemReader<T>` for custom readers that can recover by counting read items. It manages the counter and common state, reducing boilerplate code.

A custom reader extending this class typically implements:

- `doOpen()` to open the data source.
- `doRead()` to read the next item.
- `doClose()` to close the source.
- `jumpToItem(int itemIndex)` to reposition the source when restarting.

Skeleton example:

```java
public class CustomOrderReader
        extends AbstractItemCountingItemStreamItemReader<Order> {

    private final OrderSource source;

    public CustomOrderReader(OrderSource source) {
        this.source = source;
        setName("customOrderReader");
    }

    @Override
    protected void doOpen() throws Exception {
        source.open();
    }

    @Override
    protected Order doRead() throws Exception {
        return source.readNext();
    }

    @Override
    protected void doClose() throws Exception {
        source.close();
    }

    @Override
    protected void jumpToItem(int itemIndex) throws Exception {
        source.skip(itemIndex);
    }
}
```

`source.skip(itemIndex)` is illustrative. For databases, jumping to an item may require a stably ordered query or keyset pagination; for files, it may require skipping preceding records. Implement repositioning so the restored position matches the item order of the initial run.

If the source has a better native checkpoint mechanism—such as an API continuation token or database last ID—implementing `ItemStream` directly to store that token/key can be cleaner than converting it to an index.

## 8. Checkpointing by Item Count vs. Business Key

Not every source should store an item sequence number.

| Source type | State to store | Notes |
|---|---|---|
| Fixed list | Item index | List and order must remain unchanged |
| Sequential file | Record count or reader-supported position | File must be immutable between run and restart |
| Database | Last processed primary key or page marker | Query must have deterministic ordering |
| Paginated API | Continuation token/page cursor | Token must remain valid on restart |
| Partitioned data | Partition key and dedicated checkpoint | Each worker needs its own namespace/context |

For databases, storing the last processed ID is usually safer than an offset if records are ordered by a unique key:

```sql
SELECT ORDER_ID, CUSTOMER_ID, TOTAL
FROM ORDERS
WHERE ORDER_ID > ?
ORDER BY ORDER_ID
FETCH FIRST 500 ROWS ONLY
```

At checkpoint, store the last committed ID. On restart, the query resumes with `ORDER_ID > lastId`.

Row-limiting syntax depends on the database. What matters is deterministic ordering and that the checkpoint key is unique or paired with a stable tie-breaker.

## 9. Updating ExecutionContext in update

`update` is where a custom stream writes state needed for recovery. Example with last processed key:

```java
@Override
public void update(ExecutionContext executionContext) {
    if (lastCommittedOrderId != null) {
        executionContext.putLong(
            getExecutionContextKey("lastOrderId"),
            lastCommittedOrderId
        );
    }
}
```

When reopening:

```java
@Override
public void open(ExecutionContext executionContext) {
    String key = getExecutionContextKey("lastOrderId");

    if (executionContext.containsKey(key)) {
        lastCommittedOrderId = executionContext.getLong(key);
    } else {
        lastCommittedOrderId = null;
    }

    source.openAfter(lastCommittedOrderId);
}
```

The variable name `lastCommittedOrderId` emphasizes that checkpoints must represent committed data. Never save a read marker before the chunk finishes and treat it as successfully processed.

If a reader reads ahead multiple items to fill a chunk, runtime state can be further ahead than the committed checkpoint. `update` and Spring Batch's chunk mechanism must coordinate to persist only a transaction-consistent boundary. Custom readers must be tested under actual rollbacks and retries, not only happy-path runs.

## 10. Checkpoints Must Align with Commit Boundaries

Spring Batch processes chunks in transactions. When a chunk commits, `ItemStream` state is updated and persisted alongside metadata according to transaction and repository configuration. When a chunk rolls back, the uncommitted chunk's checkpoint must not become a completed restart point.

Example:

```text
Committed checkpoint: orderId = 200
Next chunk:
  read 201
  read 202
  read 203
  writer fails
  transaction rolls back

Restart:
  open context with lastOrderId = 200
  re-read starting after orderId 200
```

If the checkpoint advanced to 203 even though the chunk containing 201–203 did not commit, a restart would skip unwritten data. That is a critical bug: the checkpoint ran ahead of business data.

Conversely, if data commits while the checkpoint fails to save atomically, items may be re-read. Therefore, writers should have unique constraints, upserts, or proper idempotency to prevent duplicate writes.

## 11. JobRepository Persists ExecutionContext

`ExecutionContext` is persisted by Spring Batch through `JobRepository`. With a JDBC `JobRepository`, state is stored in step/job execution metadata tables and restored when a new execution starts.

In a standard design:

- Step context holds step-specific checkpoints.
- Job context holds data shared across steps in the same `JobExecution`.
- `JobRepository` stores metadata and contexts to support restarts.
- Transaction configuration defines the commit relationship between metadata and business data.

Do not use a static `HashMap` or singleton field in place of `ExecutionContext`. In-memory values do not survive process restarts and can mix across concurrent executions.

If `JobRepository` and the business database use separate datasources/transaction managers, do not assume checkpoints and business data commit atomically. Evaluate partial commit failure scenarios and design appropriate idempotency and reconciliation.

## 12. Step ExecutionContext vs. Job ExecutionContext

Ordinary readers and writers receive the Step `ExecutionContext` in `open` and `update`. This is the proper place for state meaningful only to that step.

Example:

```java
executionContext.putLong("orderReader.lastOrderId", 9001L);
```

If one step produces data needed by a subsequent step, store it temporarily in Step context and promote selected keys to Job context using a mechanism like `ExecutionContextPromotionListener`.

Job context should not be used as an uncontrolled shared write area for parallel workers. If multiple steps or partitions update the same key simultaneously, race conditions or overwrites can occur. Use distinct keys, immutable values, or synchronized storage.

## 13. What Values Should Be Stored?

`ExecutionContext` should hold compact, serializable state sufficient to reconstruct progress.

Should store:

- `String`, `Long`, `Integer`, `Boolean`, and appropriate scalar types.
- Last processed ID or watermark.
- Page number or continuation token.
- Filename/version and record count needed for recovery.
- State schema version numbers to support upgrades.

Should not store:

- JDBC `Connection`, `ResultSet`, `PreparedStatement`.
- File handles, `InputStream`, sockets, or open parsers.
- Spring beans, services, or non-serializable runtime objects.
- Large collections containing all read items.
- Unnecessary sensitive payloads.
- Complex objects coupled to class versions hard to keep compatible across deployments.

Runtime resources must be reopened in `open`; never serialize open resources themselves into the context.

## 14. Serialization and State Compatibility

`ExecutionContext` must be serialized to persist in the repository. Therefore, types placed in the context must work with the configured serializer.

A safe approach is storing primitive/simple values:

```java
executionContext.putString("orderReader.sourceVersion", sourceVersion);
executionContext.putLong("orderReader.lastId", lastId);
executionContext.putInt("orderReader.page", pageNumber);
```

If storing custom objects, those objects must remain compatible with the serializer and class versions when the job restarts. A newer deployment may read a context written by an older deployment; changing class structures or packages can break deserialization.

For checkpoints, scalars and well-formatted tokens are typically much easier to maintain than complex Java objects.

## 15. Versioning Keys and State Schemas

Key names are part of the restart contract. When renaming a key or changing the meaning of its value, older executions may fail to restore state properly.

You can include versions in keys:

```java
private static final String LAST_ID_KEY = "orderReader.v1.lastId";
```

If the state structure must evolve, establish a compatibility strategy:

- Read legacy keys when new keys are absent.
- Migrate legacy values to the new representation if possible.
- Retain legacy reader support for restartable `JobInstance`s if migration is too complex.
- Never silently treat an unrecognized checkpoint as a fresh run from the start.

Example intentional fallback:

```java
@Override
public void open(ExecutionContext context) {
    String newKey = getExecutionContextKey("v2.lastId");
    String oldKey = getExecutionContextKey("v1.lastId");

    if (context.containsKey(newKey)) {
        lastId = context.getLong(newKey);
    } else if (context.containsKey(oldKey)) {
        lastId = context.getLong(oldKey);
    } else {
        lastId = 0L;
    }
}
```

This example is appropriate only when `v1.lastId` and `v2.lastId` share identical semantics. If their meanings differ, perform explicit migration or reject the restart with an actionable error message.

## 16. Saving State for Custom Writers

Writers can also implement `ItemStream` when needing to restore state such as current file, record count, last written key, or output marker.

Example JDBC writer saving data and tracking the last written ID:

```java
public class CheckpointingOrderWriter
        extends ItemStreamSupport
        implements ItemStreamWriter<Order> {

    private static final String LAST_ID_KEY = "lastOrderId";

    private final JdbcTemplate jdbcTemplate;
    private Long lastOrderId;

    public CheckpointingOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        setName("checkpointingOrderWriter");
    }

    @Override
    public void open(ExecutionContext context) {
        String key = getExecutionContextKey(LAST_ID_KEY);
        lastOrderId = context.containsKey(key)
            ? context.getLong(key)
            : null;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                "INSERT INTO PROCESSED_ORDERS (ORDER_ID, TOTAL) VALUES (?, ?)",
                order.id(),
                order.total()
            );
            lastOrderId = order.id();
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (lastOrderId != null) {
            context.putLong(
                getExecutionContextKey(LAST_ID_KEY),
                lastOrderId
            );
        }
    }

    @Override
    public void close() {
        // JdbcTemplate does not hold an open resource here.
    }
}
```

This example assumes inserts and `JobRepository` updates coordinate transactionally per application configuration. If business data and metadata do not share a transaction boundary, do not treat the two checkpoints as atomic.

In practice, writers often do not need to save a last ID if the database enforces unique keys and writes are safely repeatable. Persist writer state only when actually required to restore output.

## 17. File Writers and Checkpointing

Custom file writers require more care than JDBC writers because filesystems do not automatically join JDBC transactions.

File state may include:

- Immutable resource/file ID.
- Write position or committed record count.
- Temporary filename currently in use.
- Whether the header has been written.
- Output format version.

However, storing a byte offset in `ExecutionContext` alone does not guarantee atomic commits between the file and `JobRepository`. The process can crash between flushing the file and persisting metadata, or vice versa.

For critical outputs, consider:

1. Writing to a unique temporary filename per `JobInstance`.
2. Using a writer with appropriate restart support and transaction-aware behavior.
3. Verifying contents/record counts after the step completes.
4. Using a final step to publish/rename the file once the job meets success criteria.
5. Retaining temporary files or manifests for investigation if the job fails.

Do not treat `close()` as a signal that the file is ready for publication. `close()` is merely lifecycle cleanup; publishing should be an explicit business step.

## 18. Registering ItemStream in a Step

Spring Batch needs to know which components should receive `open`, `update`, and `close` callbacks.

When a custom reader/writer is passed directly to a step and implements `ItemStreamReader` or `ItemStreamWriter`, the framework automatically registers the stream lifecycle with the step.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<Order> orderReader,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
}
```

Declaring specific bean return types also helps infrastructure detect stream interfaces. If a `@Bean` method declares an overly broad interface, some lifecycle metadata may not be discovered as expected.

## 19. Delegates and Composite Components

A wrapper or composite can contain multiple delegate readers or writers. If the wrapper does not forward the `ItemStream` lifecycle to its delegates, Spring Batch may invoke lifecycle methods only on the wrapper and miss delegate state.

For example, suppose a step uses a composite writer where an inner file writer needs to save checkpoints. If the composite does not forward `open`, `update`, and `close`, register the delegate stream with the step:

```java
return new StepBuilder("exportOrders", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .writer(compositeWriter)
    .stream(fileDelegateWriter)
    .build();
```

Register a delegate separately only when the wrapper does not manage/forward stream lifecycles itself. If the delegate is already registered and forwarded by the wrapper, double registration can invoke lifecycle callbacks twice.

For custom composites, you can implement `ItemStreamWriter` and forward the three callbacks to delegate streams. Ensure each delegate is opened, updated, and closed exactly once.

## 20. Scoped Beans and Per-Execution State

Custom readers often need `@StepScope` when accepting `JobParameters` or execution-specific state per `StepExecution`.

```java
@Bean
@StepScope
ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        OrderSourceFactory sourceFactory) {

    OrderSource source = sourceFactory.open(inputFile);
    return new CustomOrderReader(source);
}
```

The scoped target is created for the active `StepExecution`, giving each execution isolated reader state. A proxy does not replace `ItemStream`; the reader still needs to implement the stream lifecycle for checkpointing.

With partitioning, each worker `StepExecution` receives its own context and custom readers must save state under keys inside that worker's context. Do not use static fields or mutable singletons to hold shared indexes across partitions.

## 21. Rollbacks and In-Memory State

An important subtlety when writing custom readers: `ExecutionContext` checkpoints are managed transactionally, whereas Java fields like `currentIndex` do not automatically roll back with JDBC transactions.

For example, a reader increments its index while reading items, and then the writer throws an exception. The transaction rolls back, yet the `currentIndex` variable in the object remains incremented. Spring Batch provides chunk buffering/recovery mechanisms, but custom readers must be compatible with how step retry, skip, and rollback operate.

Therefore:

- Do not treat runtime fields as committed checkpoints.
- Write checkpoints only in `update` per framework lifecycle.
- Ensure `open` can recover from the durable checkpoint.
- Test mid-chunk writer failures, retries, skips, and restarts.
- For complex readers, consider extending Spring Batch base classes with item-counting/restart support rather than reimplementing everything from scratch.

If a custom reader must continue within the same execution after rollback, understand how step buffering and fault tolerance interact with your source. You may need source-level reset/reposition support, not only process-restart recovery.

## 22. Data Sources Must Be Stable

Checkpoints are meaningful only when state is applied to the same data source in the same logical order.

For example, a reader stores `lastOrderId = 500`. If source rows are deleted, updated, or reordered before restart, subsequent queries may yield a different set of items than the initial run.

Safeguards:

- Use input snapshots or immutable files.
- Choose stable, unique ordering keys.
- Save source ID/version/checksum if input verification is needed.
- Use watermarks or snapshot timestamps for continuously changing data.
- Keep a fixed manifest when a step reads multiple resources.

Do not save offsets/indexes and assume the source can mutate arbitrarily while restarts remain accurate.

## 23. Step Restart and Reader Checkpoints Are Separate Mechanisms

Spring Batch uses metadata to determine which steps need to rerun. A reader's `ExecutionContext` determines where the reader resumes when the step restarts.

| Mechanism | Question answered |
|---|---|
| `JobInstance`/`JobExecution` metadata | Is this the same business execution? |
| `StepExecution` status | Did the step complete, fail, or stop? |
| Step `ExecutionContext` | What state must the reader/writer restore? |
| Job `ExecutionContext` | What data must be shared between steps? |

To restart the same `JobInstance`, keep identifying `JobParameters` unchanged. Adding a new identifying parameter causes Spring Batch to create a new `JobInstance` without reusing the old instance's checkpoints.

`ExecutionContext` does not itself make a completed job or a non-restartable step restartable. Restart policies and metadata rules still govern execution.

## 24. Do Not Store Oversized State

`ExecutionContext` is persisted in `JobRepository` and incurs serialization and metadata write overhead. Never put tens of thousands of items, entire file contents, or large object graphs into the context.

Instead of storing the list of read items:

```java
// Do not store all processed data in ExecutionContext
executionContext.put("processedOrders", processedOrders);
```

Store a compact checkpoint:

```java
executionContext.putLong("orderReader.lastOrderId", lastOrderId);
```

On restart, re-query data after the checkpoint. If the source cannot be re-queried, consider staging or storing state in a dedicated table instead of bloating metadata contexts.

## 25. ExecutionContext and Sensitive Data

`JobRepository` may persist contexts inside metadata database tables. Never store credentials, access tokens, payment information, or sensitive payloads in contexts unnecessarily.

If a component needs credentials to open a resource, retrieve them from a secret/configuration provider at runtime and store only a non-sensitive reference or version in the context if needed to verify restart configuration.

Do not log entire `ExecutionContext` contents in production. Log only needed keys or sanitized correlation IDs.

## 26. Testing Restartable Custom Components

Unit tests for `open`, `read`, and `update` verify key handling, while integration tests with Spring Batch prove checkpoints are persisted and restored properly through `JobRepository`.

Scenarios to test:

1. Initial empty context: reader starts from the beginning.
2. Context containing key: `open` restores the exact item index/last key.
3. `update` writes state to the proper namespaced key.
4. Two streams with the same suffix but different names do not overwrite each other.
5. Chunk commit: checkpoint is persisted.
6. Chunk rollback: uncommitted chunk checkpoint does not become the restart marker.
7. Restart same `JobInstance`: reader resumes after the latest committed checkpoint.
8. Changing identifying `JobParameters`: job creates a new instance.
9. Source version changes: job detects or rejects unsafe restarts.
10. Delegates in composites: lifecycle callbacks fire the expected number of times.
11. Multiple partitions: each worker maintains isolated state.
12. State values serialize and deserialize cleanly via `JobRepository`.

Example testing context logic directly:

```java
@Test
void restoresReaderPositionFromExecutionContext() throws Exception {
    IndexedOrderReader reader = new IndexedOrderReader(orders);

    ExecutionContext context = new ExecutionContext();
    context.putInt("indexedOrderReader.currentIndex", 2);

    reader.open(context);

    assertThat(reader.read().id()).isEqualTo(orders.get(2).id());

    reader.close();
}
```

Key names in tests must match the stream's `getExecutionContextKey` convention. Integration tests should use real reader beans and a `JobRepository` to confirm Spring Batch invokes the lifecycle automatically.

## 27. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Keeping index only in a Java field | Progress lost on process restart | Persist state via `ItemStream.update` |
| Not restoring in `open` | Restart starts from wrong position | Read keys from `ExecutionContext` |
| Not implementing `ItemStream` | Framework unaware of checkpoint lifecycle | Use `ItemStreamReader`/`ItemStreamWriter` |
| Using generic keys like `index` | Streams overwrite each other's state | Namespace by component name |
| Renaming streams between runs | Cannot find prior checkpoint | Keep names stable |
| Storing non-serializable runtime objects | Cannot save/read context | Store only small scalars/tokens |
| Saving checkpoints ahead of commits | Restarts may skip uncommitted data | Update state at lifecycle checkpoints |
| Not testing rollbacks | Runtime fields diverge from checkpoints | Test rollbacks, retries, skips, and restarts |
| Wrapper omitting `ItemStream` | Delegate never opened/updated/closed | Forward lifecycle or register `.stream(delegate)` |
| Using Job context for worker-private state | State shared/overwritten across workers | Use isolated Step contexts |
| Modifying source data across restarts | Checkpoints point to shifted data | Snapshot/version inputs |
| Storing full items in context | Bloated metadata and serialization cost | Store last key/page token and re-query |

## 28. State Design Workflow for Custom Components

When building a restartable reader, writer, or tasklet, proceed in this order:

1. Identify exactly what runtime state must survive a restart.
2. Choose Step `ExecutionContext` or Job `ExecutionContext` based on data scope.
3. Choose a small, stable checkpoint representation: item index, last key, page token, or file marker.
4. Implement `ItemStream` with `open`, `update`, and `close`.
5. Assign a stable stream name and namespace every key.
6. Register the component/delegates with the step so the lifecycle is invoked.
7. Ensure state is serializable and compatible across deployments.
8. Keep inputs stable or store a source version to validate restarts.
9. Align checkpoints with transaction/commit boundaries and writer idempotency.
10. Integration test success, rollback, retry, skip, restart, and concurrency.

## Conclusion

`ExecutionContext` is where Spring Batch persists recoverable state for a step or job. Custom readers and writers participate via `ItemStream`: `open` restores state, `update` saves checkpoints, and `close` releases resources. Spring Batch persists contexts through `JobRepository` aligned with step checkpoint lifecycles.

Use Step context for component/worker-specific state, use namespaced keys with stable stream names, store only small serializable values, and ensure checkpoints reflect committed data. Register streams properly, verify composite delegates, keep data sources stable, and test actual rollbacks and restarts. `ExecutionContext` does not make a custom component restartable by itself; the component must define and enforce the complete state-recovery rules.
