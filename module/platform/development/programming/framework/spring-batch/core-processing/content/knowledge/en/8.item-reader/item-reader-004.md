# Restartable Readers and Save State

In Spring Batch, an `ItemReader` may need to remember the position it has read so that it can continue at the right place when a Job is interrupted. This mechanism is called the reader's *restartability*. Spring Batch provides the `ItemStream` contract and `ExecutionContext` so that a reader can save state, restore state, and continue processing on a restart.

A restartable reader must satisfy two requirements: save a checkpoint at the appropriate time during processing and restore that checkpoint when the Step runs again. If the reader keeps the read position only in a field of a Java object, the state is lost when the process is stopped. `saveState` is an important option in many built-in readers, allowing you to enable or disable saving state into the `ExecutionContext`.

## 1. What Problem Does a Restartable Reader Solve?

Suppose a Step reads a file with 10,000 lines and writes data to a database in chunks of 100 items. After processing and committing 4,000 lines, the application suddenly stops.

If the reader does not save the position it has read, when the Job is restarted, the reader may start again from the beginning. In that case the 4,000 committed lines risk being read and written again. If the reader saves a checkpoint, the restart can continue from the position corresponding to the last committed chunk.

```text
First run
  Read lines 1..100   -> commit
  Read lines 101..200 -> commit
  ...
  Read lines 3901..4000 -> commit
  Application stops before the next chunk completes

Restart
  Restore the saved checkpoint
  Continue from the portion of data that has not been committed
```

Restartability helps reduce reprocessing and keeps progress consistent. It is especially important for long Jobs, large data sources, or processes that must continue after a system failure.

However, restartability does not depend on the reader alone. The JobRepository must be able to store metadata, the Step must be restartable, the reader must restore the correct state, and the data source must be stable enough for the saved position to remain meaningful.

## 2. ItemStream: The Contract for Saving and Restoring State

`ItemReader` defines the item-reading operation through `read()`. To take part in the state-saving lifecycle, a reader typically also implements `ItemStream`, or uses the combined interface `ItemStreamReader`.

`ItemStream` has three main callbacks:

| Method | Role |
|---|---|
| `open(ExecutionContext)` | Opens the reader and restores previously saved state |
| `update(ExecutionContext)` | Writes the reader's current state into the context as a checkpoint |
| `close()` | Closes the reader and releases resources |

General call flow within a Step:

```text
Step starts
    |
    +--> open(saved context)
    |
    +--> read item -> process -> write
    |          |
    |          +--> update(context) at checkpoint points
    |          +--> commit the chunk's transaction
    |
    +--> ... repeat chunks ...
    |
    +--> close()
```

When the Step is restarted, `open()` receives the `ExecutionContext` that was saved from the previous execution. The reader uses the data in the context to restore the position, counters, or necessary state. `update()` is called by the framework while the Step state is being saved, usually tied to the chunk's commit boundary. `close()` is called when the Step ends to release resources.

`ItemStreamReader<T>` combines `ItemReader<T>` and `ItemStream`, so a reader implementing this interface has both `read()` and the state-management callbacks.

## 3. Where Does ExecutionContext Store the Checkpoint?

The reader runs within a `StepExecution`, so the reader's checkpoint is usually stored in the Step `ExecutionContext`. This is metadata attached to the Step execution, stored by the `JobRepository` so it can be restored on restart.

For example, the reader saves the sequence number of the next item to read:

```java
executionContext.putInt("ordersReader.currentIndex", currentIndex);
```

When the Step is restarted, the reader reads that key back:

```java
currentIndex = executionContext.getInt("ordersReader.currentIndex", 0);
```

The default value `0` is used when the key does not yet exist, meaning this is the first run or there is no corresponding checkpoint yet. When the key already exists, the reader continues from the saved position.

Do not confuse the reader's checkpoint with `JobParameters`. JobParameters are input data used to identify a JobInstance; the ExecutionContext stores progress that arises during execution. For example, the business date is a JobParameter, whereas the line position already read is the reader's checkpoint.

## 4. Implementing Your Own Restartable Reader

The following example illustrates a reader that reads a list with a stable order. The reader saves the index of the next element to read into the Step ExecutionContext:

```java
public class RestartableOrderReader implements ItemStreamReader<Order> {

    private static final String CURRENT_INDEX_KEY =
            "restartableOrderReader.currentIndex";

    private final OrderSource orderSource;
    private int currentIndex;
    private List<Order> orders;

    public RestartableOrderReader(OrderSource orderSource) {
        this.orderSource = orderSource;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        currentIndex = executionContext.getInt(CURRENT_INDEX_KEY, 0);
        orders = orderSource.loadOrdersInStableOrder();

        if (currentIndex > orders.size()) {
            throw new IllegalStateException(
                    "Saved reader position is beyond the available input"
            );
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
        executionContext.putInt(CURRENT_INDEX_KEY, currentIndex);
    }

    @Override
    public void close() {
        orders = null;
    }
}
```

Key parts:

- `open()` reads the old checkpoint. If there is no key yet, the reader starts from index `0`.
- `read()` returns the next item and increments `currentIndex`. When there is no more data, it returns `null` according to the `ItemReader` contract.
- `update()` writes the current position into the ExecutionContext so that Spring Batch saves the checkpoint.
- `close()` releases the reference to the list in the example. A real reader needs to close the streams, cursors, or resources it has opened.

This example assumes `loadOrdersInStableOrder()` returns the same data set in the same order on restart. In a real application, you should not load a very large list into memory just to illustrate a checkpoint; use a reader appropriate to the data source, such as a file reader or a database paging reader.

### Keys in ExecutionContext Must Be Stable and Unique

The key name is part of the checkpoint format. When the key name is changed between two application versions, the new reader may not find the old state and may start again from the beginning. Keep keys stable across deployments or provide compatible conversion logic when needed.

If a Step has multiple stream components that each save state, each component must have its own key to avoid overwriting each other's data. For built-in readers based on `ItemStreamSupport`, giving the reader a unique name usually helps the framework generate execution-context keys with their own namespace. When writing your own reader, use a clear prefix such as `ordersReader.` or a stable component name.

## 5. Enabling saveState on Built-in Readers

Many Spring Batch readers already implement `ItemStream` and save checkpoints on their own. For these readers, the `saveState` configuration determines whether state is written into the ExecutionContext. You should give the reader a stable name and enable `saveState(true)` when restart is needed.

Example with `FlatFileItemReader`:

```java
@Bean
public FlatFileItemReader<Order> ordersFileReader(
        @Value("${batch.orders-file}") Resource resource) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("ordersFileReader")
            .resource(resource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

The reader saves read progress into the ExecutionContext and reuses that progress when it is reopened on a restart. For the checkpoint to be meaningful, the file must keep its content and order throughout the period from the first run to the restart. If the file is replaced or has lines inserted/deleted, the saved line position may point to different data.

For a paging-style database reader, you need to configure a stable sort order. For example, the sort key should uniquely identify each row, usually the primary key:

```java
@Bean
public JdbcPagingItemReader<Order> ordersPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> orderRowMapper) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("ordersPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .rowMapper(orderRowMapper)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

`queryProvider` needs a stable sort key and must define a consistent order across pages. If you sort by only a single column with duplicate values, the order of records between queries may change, causing the reader to miss or repeat records on restart.

The specific builders and APIs may differ by Spring Batch version. Use the readers and builders available in your project's dependencies, and also check the `saveState` API of the implementation you are using.

## 6. The Meaning of saveState(true) and saveState(false)

| Configuration | Behavior | Consequence on restart |
|---|---|---|
| `saveState(true)` | The reader saves the necessary state into the ExecutionContext | The reader can restore the checkpoint if the data source and configuration remain appropriate |
| `saveState(false)` | The reader does not save its own state into the ExecutionContext | The reader cannot rely on its own checkpoint to continue from the previous position |

`saveState(true)` does not by itself guarantee that every data source restarts accurately. The reader must implement the contract correctly, the checkpoint must be saved at an appropriate boundary, and the input data must allow the position to be restored.

`saveState(false)` may be appropriate when the reader does not need a checkpoint, or when the application deliberately accepts starting again from the beginning and the writer has an idempotent mechanism to avoid creating duplicate data. It may also be necessary in some parallel-execution configurations where sharing the reader's state is not appropriate. However, disabling state saving means the application must handle the consequences itself when the Step is restarted.

Do not disable `saveState` just to avoid a metadata error. If you need to restart at the exact position, look for the cause of the problem, such as an unstable reader name, duplicate keys, a changing data source, or a component that is not registered as an ItemStream.

## 7. When Does Spring Batch Call open, update, and close?

Within a Step, the registered `ItemStream`s take part in the processing lifecycle:

1. Before reading items, the framework calls `open()` with the Step's ExecutionContext. The reader can open the file/cursor and restore the checkpoint.
2. During chunk processing, the reader provides items through `read()`.
3. When it is time to save state, the framework calls `update()` so that the streams write their current state into the ExecutionContext.
4. The Step metadata and ExecutionContext are saved along with the commit process according to the repository/transaction configuration.
5. When the Step ends, the framework calls `close()` to close resources.

`update()` is a state-saving callback, not a place to perform the main business work. Do not put output data writes or external API calls in this callback. It should update the small values needed to restore the reader or writer.

If a chunk rolls back, that chunk's checkpoint is not considered committed progress. On restart, the reader needs to continue from the checkpoint saved at the previous commit boundary. This helps keep the committed data and the reader position restored consistently.

## 8. Make Sure the Reader Is Registered as an ItemStream

When the reader is passed directly into the Step configuration and that reader itself implements `ItemStream`, Spring Batch can manage its lifecycle callbacks. However, if the reader is wrapped inside a delegate or wrapper, the framework may see only the outermost object.

For example, a composite reader has a delegate inside it. If the delegate itself implements `ItemStream`, make sure the delegate is also registered with the Step so that `open`, `update`, and `close` are called. In Java configuration you can use `.stream(delegate)` when appropriate:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(compositeReader)
        .writer(orderWriter)
        .stream(fileDelegateReader)
        .build();
```

If the delegate does not receive the `update()` callback, its state will not be saved even though the class itself implements `ItemStream`. On restart, the reader may start at the wrong position or be unable to restore the correct state.

Multi-source readers such as `MultiResourceItemReader` must also save both the current resource and the delegate's state. Use the framework's standard builder or configuration and give the delegate its own name to avoid key conflicts.

## 9. Conditions for an Exact Restart

A reader restarts exactly only when the checkpoint and the data source remain compatible. The important conditions include:

- The Job is relaunched with the same Job name and identifying JobParameters to continue the same JobInstance.
- The previous JobInstance is in a restartable state and has no execution still running.
- The Step can be restarted according to the Job's configuration.
- The JobRepository still has the metadata of the previous JobExecution/StepExecution.
- The reader supports `ItemStream` and saves state if it needs to continue from a checkpoint.
- The reader name and the keys in the ExecutionContext are stable between runs.
- The file, query, or data source keeps its order and identifiers stable enough for the checkpoint position to still point to the intended data.
- The writer and business operations safely handle the case where an item is re-read because of a rollback or an error outside the transaction.

For example, a file reader may save the number of lines read. If the file is replaced with new content but has the same path, the checkpoint line number no longer points to the same record. Similarly, a database paging reader needs a stable sort order; data inserted/deleted during the restart may change the page positions.

For continuously changing data, consider a point-in-time snapshot, a business key, a watermark, or a fixed query condition to ensure the restart sees the same logical data set.

## 10. Distinguishing Restart, Retry, and Skip

These mechanisms are related but solve different problems:

| Mechanism | Scope | Purpose |
|---|---|---|
| Restart | A JobInstance after a JobExecution fails or stops | Continue the Job/Step in a new execution based on the saved metadata |
| Retry | An item/chunk operation that encounters an error and can be retried within the same run | Handle transient errors such as connection errors or lock contention |
| Skip | An item that encounters an error of a type allowed to be skipped | Continue processing the remaining items according to the skip policy |

A restartable reader does not mean every read error is automatically retried. Retry/skip configuration belongs to the fault-tolerant Step; `ItemStream` and ExecutionContext serve saving/restoring state when the Step or Job is restarted.

## 11. Common Misconceptions

**Saving the read position only in a reader field.** A field exists only in the object's memory. When the application restarts, the field is not automatically restored. Save the checkpoint in the ExecutionContext through `ItemStream.update()`.

**Assuming every ItemReader can automatically restart.** `ItemReader` only defines the read operation. The reader needs to support `ItemStream` and save state, or have an appropriate separate recovery mechanism.

**Enabling saveState but not giving the reader a stable name.** Some readers use the name to generate keys in the ExecutionContext. A changed name may cause the reader to not find the old checkpoint.

**Changing the key name or checkpoint structure without supporting old data.** The ExecutionContext is stored across many deployments. The new code must be able to read old metadata or have a plan for handling in-flight executions.

**Disabling saveState and still expecting to continue from the old position.** When state is not saved, the reader has no checkpoint of its own to restore. You must accept rerunning from the beginning or build another safe mechanism yourself.

**The data source changes between two runs.** The old line position or offset may point to a different record. Ensure the snapshot, order, and data identifiers are stable.

**A delegate reader is not registered as a stream.** If the framework does not call `open`, `update`, and `close` for the delegate, the delegate's state will not be saved or restored.

## 12. Designing Restartable Readers in Real Applications

When using a built-in reader, prefer configuring a stable name and enabling `saveState(true)` if the Job needs to restart. For a self-written reader, implement `ItemStreamReader`, read the checkpoint in `open()`, update the checkpoint in `update()`, and release resources in `close()`. Choose unique keys, keep the checkpoint format compatible, and ensure the data source has a stable order.

Test the behavior when an error occurs in the middle of a chunk: the chunk's uncommitted transaction must roll back, the reader must restore from the most recently saved checkpoint, and the writer must safely handle data that may be read again. Correctly combining `ItemStream`, `ExecutionContext`, the JobRepository, and a stable data source will help the reader continue accurately after a restart instead of depending on temporary in-memory state.
