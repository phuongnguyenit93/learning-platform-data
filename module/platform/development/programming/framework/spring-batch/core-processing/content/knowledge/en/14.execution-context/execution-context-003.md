# Stable Keys for Reader State

In Spring Batch, a reader can save its read progress into the Step `ExecutionContext` so it can continue from the correct position when the Job is restarted. Each value is stored as a key/value pair. **Reader state keys must remain stable across runs and application deployments**, because the reader uses that very key to find the saved checkpoint again.

If the reader name or key is changed, the new code may not be able to read the old checkpoint. The reader may think this is the first run and start over from the beginning, leading to duplicate reads or incorrect data processing. If multiple stream components write to the same key, one component's state may overwrite another component's state.

Designing stable keys requires attention to the scope of the `ExecutionContext`, the reader name, the namespace of each component, the data type, compatibility during upgrades, and how to handle in-flight executions.

## 1. Reader State Is Stored in the ExecutionContext

A restartable reader typically implements `ItemStream` or `ItemStreamReader`. During the Step lifecycle, Spring Batch calls these callbacks:

| Callback | Role |
|---|---|
| `open(ExecutionContext)` | Receives the saved context and restores the read position |
| `update(ExecutionContext)` | Writes the reader's current state into the context |
| `close()` | Closes the stream and releases resources |

For example, a reader that saves its current position:

```java
private static final String CURRENT_INDEX_KEY = "ordersReader.currentIndex";

@Override
public void open(ExecutionContext context) {
    currentIndex = context.getInt(CURRENT_INDEX_KEY, 0);
}

@Override
public void update(ExecutionContext context) {
    context.putInt(CURRENT_INDEX_KEY, currentIndex);
}
```

When the Step is restarted, `open()` reads back the saved value. If the key does not exist yet, the reader starts from the default position. If the key already exists, the reader continues from the corresponding checkpoint.

A key is not just a variable name in code. It is part of the metadata stored in the `JobRepository`, which typically outlives Java objects and may be read by an application version deployed later. Therefore, a key change should be treated as a change to the checkpoint data format.

## 2. Key Scope: Step ExecutionContext and Job ExecutionContext

Spring Batch has an ExecutionContext at the JobExecution and StepExecution scopes. Reader state typically belongs to the Step context because the read position is tied to a specific Step execution.

```text
JobExecution
  |
  +-- Job ExecutionContext
  |      +-- report.outputLocation
  |
  +-- StepExecution: importOrdersStep
  |      +-- Step ExecutionContext
  |             +-- ordersReader.currentIndex
  |             +-- ordersReader.resourceIndex
  |
  +-- StepExecution: importCustomersStep
         +-- Step ExecutionContext
                +-- customersReader.currentIndex
```

Two StepExecutions have separate ExecutionContexts, so the same key can appear in two different contexts without conflict. However, within the same StepExecution, stream components need to avoid using duplicate keys.

Do not store a reader's read position in the Job context just because you want other Steps to see it. A reader's checkpoint belongs to the Step lifecycle and should be stored in the Step ExecutionContext. The Job context is suitable for data that needs to be shared between Steps; it is not a common namespace for all readers.

## 3. Naming Keys with a Stable Namespace

A key should describe the component and the meaning of the value. A simple convention:

```text
<reader-name>.<state-name>
```

Examples:

```text
ordersFileReader.currentLine
ordersFileReader.resourceIndex
ordersPagingReader.lastOrderId
customerReader.currentPage
```

The reader name helps identify the source that produced the state; the suffix describes the specific checkpoint. If you write your own reader, you can declare the keys as constants:

```java
public class OrdersReader implements ItemStreamReader<Order> {

    private static final String CURRENT_LINE_KEY =
            "ordersFileReader.currentLine";
    private static final String RESOURCE_INDEX_KEY =
            "ordersFileReader.resourceIndex";

    // Other reader fields and methods.
}
```

Do not use keys that are too generic, such as `index`, `count`, `position`, or `state`, when a Step has multiple components. Generic names easily conflict and are hard to understand when investigating metadata.

The namespace should remain stable across application versions. Avoid creating keys based on values that change on every run, such as a timestamp, a random UUID, or the `JobExecutionId`, because the reader will not find the old checkpoint on restart.

## 4. Built-in Component Reader Names Also Need to Be Stable

Many of Spring Batch's built-in readers use the configured name to create a namespace for internal keys in the ExecutionContext. For this reason, builders typically require `.name(...)` when save state is enabled.

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

The name `ordersFileReader` must remain stable between the first run and the restart. If it is changed to `orderFileReaderV2`, the implementation may create a different key and not find the checkpoint saved under the old name.

Similarly with a database paging reader:

```java
@Bean
public JdbcPagingItemReader<Order> ordersPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> rowMapper) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("ordersPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .rowMapper(rowMapper)
            .pageSize(200)
            .saveState(true)
            .build();
}
```

Besides the reader name, the query and sort key must also keep compatible semantics. If the key is stable but the query changes so the data order differs, the checkpoint can still point to a position that is no longer correct.

## 5. Using Stable Names with ItemStreamSupport

If a custom reader extends `ItemStreamSupport`, you can set the component name with `setName()` and use that namespace when creating keys:

```java
public class OrdersItemReader extends AbstractItemCountingItemStreamItemReader<Order> {

    public OrdersItemReader() {
        setName("ordersItemReader");
    }

    @Override
    protected Order doRead() {
        // Read the next item from the data source.
        return readNextOrder();
    }

    @Override
    protected void doOpen() {
        // Open the data source.
    }

    @Override
    protected void doClose() {
        // Close the data source.
    }
}
```

Support classes such as `AbstractItemCountingItemStreamItemReader` manage the counter and state according to framework conventions. The component name is used to distinguish the reader's keys. Keep this name stable and do not reuse the same name for independent readers within the same Step context scope.

If you implement `ItemStream` yourself without using a support class, you need to declare keys explicitly and ensure they do not collide with other components' keys.

## 6. Keys Must Be Stable in Both Name and Meaning

Keeping the key string unchanged is not enough. The meaning and data type of the value must also be compatible.

For example, the first version stores:

```java
context.putInt("ordersReader.position", 1200);
```

A later version changes the interpretation of `position` from a line number to a byte offset. The key string is unchanged, but the same value `1200` carries a different meaning. The new reader may restore the wrong position.

When designing state, keep in mind:

- The key clearly describes the unit and meaning, for example `currentLineNumber`, `lastCommittedOrderId`, or `resourceIndex`.
- The data type needs to be stable, for example `Long` for large IDs instead of `Integer`.
- The default value must be meaningful for the first run and must not cause the reader to skip data.
- Do not store complex objects if only an ID, offset, or small index is needed.
- Do not store runtime resources such as `InputStream`, `ResultSet`, connections, or threads.
- If the state structure changes, have a plan to read old data or convert the checkpoint.

Naming with units also helps prevent new code from misinterpreting old values. For example, `byteOffset` is clearer than `position` if the reader actually stores the offset in bytes.

## 7. Avoiding Collisions Between Readers and Delegates

A Step can have multiple stream components: a main reader, delegate readers, a stateful writer, or a listener that implements ItemStream. If two components write to the same key, the component that writes later may overwrite the earlier component's value.

A bad example:

```java
// Reader A
context.putLong("position", currentOrderId);

// Reader B
context.putLong("position", currentCustomerId);
```

After saving, the context has only one `position` value; it is impossible to tell which reader it belongs to.

Use separate namespaces:

```java
// Reader A
context.putLong("ordersReader.lastOrderId", currentOrderId);

// Reader B
context.putLong("customersReader.lastCustomerId", currentCustomerId);
```

With a composite reader or multi-resource reader, check both the outer component and the delegate. If a delegate implements `ItemStream`, you need to register the delegate with the Step when the framework does not manage it automatically through a wrapper:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(compositeReader)
        .writer(orderWriter)
        .stream(fileDelegateReader)
        .build();
```

If the delegate does not receive the `open()` and `update()` callbacks, its state will not be restored or saved even if the key is set correctly. A stable key name and correct stream registration are two different requirements, and both are necessary.

## 8. Keys Stable Across Restart and Deployment

ExecutionContext is typically stored in the database together with the JobRepository metadata. Therefore, an execution may be created by an old application version and restarted by a new version. If the new version changes the reader name, key, data type, or checkpoint semantics, it may not be able to read the old metadata.

Example:

```text
Version 1
  reader name: ordersReader
  key: ordersReader.currentLine
  value: 5000 (the next line to read)
       |
       v
  Job is stopped, checkpoint saved in the repository
       |
       v
Version 2 is deployed
  reader name: orderInputReader
  new key: orderInputReader.offset
       |
       v
  The new reader does not find the old key
```

If the new reader defaults to the starting position, data that has already been processed may be read again. If it misinterprets the type or meaning of the old value, data may be skipped.

### Key Change Strategies

When you need to rename or restructure a checkpoint, you can choose one of these approaches:

1. **Keep compatibility:** continue using the old key if the semantics have not changed.
2. **Read both old and new keys:** when opening the context, prefer the new key; if it is not present, read the old key, convert the value, and then write it using the new schema.
3. **Controlled migration:** convert the metadata of in-flight executions using a migration tool that has been tested and has a backup.
4. **Complete old executions before deployment:** if you cannot support the old checkpoint, stop accepting new Jobs, let the old Jobs complete, or handle them through a defined operational procedure.

Do not silently change keys and hope that all in-flight Jobs will start over safely on their own. The decision to restart from the beginning or continue should be based on business rules and the writer's ability to avoid duplicate processing.

## 9. Versioning the Checkpoint When the State Structure Changes

With a custom reader that has multiple state fields, you can store an additional version to identify the checkpoint format:

```java
private static final String STATE_VERSION_KEY = "ordersReader.stateVersion";
private static final String LAST_ID_KEY = "ordersReader.lastCommittedId";
private static final int CURRENT_STATE_VERSION = 2;

@Override
public void open(ExecutionContext context) {
    int version = context.getInt(STATE_VERSION_KEY, 1);

    if (version == 1) {
        // Convert the old value to the current format if needed.
        long oldPosition = context.getLong("ordersReader.position", 0L);
        lastCommittedId = convertLegacyPosition(oldPosition);
    } else if (version == CURRENT_STATE_VERSION) {
        lastCommittedId = context.getLong(LAST_ID_KEY, 0L);
    } else {
        throw new IllegalStateException(
                "Unsupported reader state version: " + version
        );
    }
}

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_ID_KEY, lastCommittedId);
    context.putInt(STATE_VERSION_KEY, CURRENT_STATE_VERSION);
}
```

This illustrates the migration logic; `convertLegacyPosition()` must be defined according to the true meaning of the old checkpoint. It is not possible to convert safely if there is not enough information to map the old position to the new data.

If multiple versions are supported, clearly limit the version range, log when converting, and delete the old key only after ensuring the new state has been written successfully. Do not over-complicate versioning if the state has only a few simple keys and there is no requirement to keep executions alive across multiple versions.

## 10. Stable Keys Do Not Replace a Stable Data Source

A reader can restore the correct key and still read the wrong data if the input source changes.

For example, `FlatFileItemReader` saves the current line. If the file is replaced or lines are inserted before the checkpoint position, the same line number 5000 may be a different record. With `JdbcPagingItemReader`, if the query sorts by a non-unique column or the data changes during a restart, the page position may no longer point to the same set of records.

For reliable restart:

- Keep the input file unchanged, or validate the file's checksum/version before resuming.
- Use a unique, stable sort key for database paging.
- Consider a snapshot or watermark if the source data changes continuously.
- Store the business key or the last committed ID instead of only an ambiguous position.
- Verify that the query and filter conditions are still compatible with the old checkpoint.

The key determines where the state is stored; the value and the data source determine whether that state is still correct.

## 11. saveState and the Reader Name

With built-in readers, `saveState(true)` allows restart state to be saved into the ExecutionContext. When enabling this feature, set a clear and stable reader name:

```java
return new FlatFileItemReaderBuilder<Order>()
        .name("ordersFileReader")
        .resource(resource)
        .delimited()
        .names("orderId", "amount")
        .targetType(Order.class)
        .saveState(true)
        .build();
```

If you set `saveState(false)`, the reader does not save its own checkpoint. In that case, keeping the name stable does not help restore that reader's read position, and the application must accept re-reading from the beginning or have another mechanism.

Do not rename a reader merely to reflect a new class name or new code naming conventions if you still need to restart old executions. The reader name is part of the state's identity, not just a display label.

## 12. Checking Keys When Investigating Restart Failures

When a reader unexpectedly starts from the beginning or reads data twice, look at the StepExecution metadata before and after the restart:

- Does the old StepExecution's `ExecutionContext` contain the expected key?
- Is the reader name in the new version still the same as the name that created the checkpoint?
- Did the key change in case, prefix, or suffix?
- Did the data type or meaning of the value change?
- Is the reader registered as an `ItemStream` so that `open()`/`update()` are called?
- Is `saveState` enabled?
- Did the data source, sort order, file version, or query change?
- Is the Step restarting the correct JobInstance with the old identifying JobParameters?

In logs, you can record the reader name, state version, and the restored checkpoint ID/offset. Avoid logging the entire ExecutionContext if it may contain sensitive data or unnecessary objects.

Do not directly edit metadata records in the JobRepository to force a reader to a different position if you do not yet understand the relationship between StepExecution, transactions, and business data. Use operational APIs or a controlled migration procedure.

## 13. Common Misconceptions

**Renaming a reader without thinking about old executions.** The name may be used as a prefix for internal keys. Renaming may cause the reader to not find the old checkpoint.

**Using a generic key such as `position` for multiple components.** Streams may overwrite each other's state. Use a separate namespace for each reader/delegate.

**Keeping only the key while the value's meaning changes.** The same key with its unit changed from lines to byte offset can still cause the reader to restore the wrong position.

**Using a timestamp or random UUID in a key.** A new key on each run will not point to the old checkpoint. Use a dynamic component only when it is truly a stable identifier of a resource within the same execution.

**Assuming a stable key is enough for accurate restart.** A changed file, query, or data order can still make the checkpoint incorrect.

**Forgetting to register the ItemStream delegate.** If a component has the right key but does not receive the save/restore callbacks, the state is not maintained.

**Storing large objects in the ExecutionContext.** The context is checkpoint metadata. Store small values that are serializable and have a stable format.

## 14. Key Design Rules for Reader State

Choose a stable reader name, set keys that have a namespace and accurately describe their meaning, keep the data type and unit consistent across versions, and store only the state needed for restoration. With built-in readers, set a clear `.name(...)` and enable `.saveState(true)` when restart is needed. With custom readers, declare keys as constants, use a dedicated prefix, implement `ItemStream`, and register it fully with the Step.

Before renaming or changing the key schema, determine whether any in-flight JobExecution needs to be restarted. If so, keep compatibility or implement a controlled migration. Combining stable keys with a stable data source, checkpoints at the correct commit boundary, and a maintained JobRepository will help the reader restore the correct progress across restarts and deployments.
