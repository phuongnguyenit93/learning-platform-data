# Write Receives a List of Items

In chunk-oriented processing, `ItemWriter` receives a group of items that the reader has read and the processor has processed. The writer writes that group of items to a destination such as a database, a file, or an external service. It is not normally called separately for each item; Spring Batch gathers the items into a chunk and then passes the chunk to the writer.

Therefore, when reading or implementing the `write` method, two points need to be understood: the writer works on groups, and the parameter type of the method depends on the Spring Batch version. In Spring Batch 5, the writer receives a `Chunk`; in Spring Batch 4, the old API receives a `List`.

## 1. ItemWriter Receives a Group of Items

In a chunk-oriented step, Spring Batch reads items, passes each item through the processor (if any), and then calls the writer with the output items of the current chunk.

```text
ItemReader
    |
    v
Read item 1, item 2, ... item N
    |
    v
ItemProcessor (per item)
    |
    v
Group of output items of the chunk
    |
    v
ItemWriter.write(chunk)
    |
    v
Write data to the destination
    |
    v
Transaction commit
```

For example, if the commit interval is 100, the step usually gathers up to 100 output items to write in one chunk. The writer is called once for that group, and then the chunk's transaction is committed if the operations succeed. As processing of the source continues, Spring Batch creates subsequent chunks and calls the writer multiple times.

The writer needs to handle all items in the group passed to it. Do not assume that one call to `write` corresponds to all of the job's data.

## 2. The write Parameter Type in Spring Batch 5

In Spring Batch 5, the `ItemWriter<T>` interface defines a method that receives a `Chunk`:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

`Chunk<? extends T>` contains the output items that the writer needs to write. You can iterate over the chunk directly or get the list of items through `getItems()`.

Example of a writer that writes orders:

```java
public class OrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public OrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL) VALUES (?, ?, ?)",
                order.id(),
                order.customerId(),
                order.total()
            );
        }
    }
}
```

The example above illustrates how to iterate over each item in the chunk. In an application with a large volume of data, you can use JDBC batch operations or Spring Batch's built-in writers to reduce the number of round-trips to the database. Whether the internal write is done statement by statement or as a SQL batch, the external contract remains receiving the whole chunk.

### Getting the List of Items from a Chunk

If the API or library that writes the data needs a `List`, you can use `chunk.getItems()`:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    List<? extends Order> orders = chunk.getItems();

    for (Order order : orders) {
        // Map and write the order
    }
}
```

`getItems()` returns the list of items in the current chunk. The writer can pass this list to a persistence library or use it to build a batch request. Avoid modifying the list or changing items in a way that affects state other components are using.

## 3. Differences from the Spring Batch 4 API

In Spring Batch 4, the `ItemWriter` method receives a `List` directly:

```java
// Old API in Spring Batch 4
public interface ItemWriter<T> {
    void write(List<? extends T> items) throws Exception;
}
```

When moving to Spring Batch 5, the method signature changes to `Chunk<? extends T>`:

```java
// Spring Batch 5 API
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Therefore, a custom writer implemented against the old API needs to be updated when upgrading versions. Code that implements `write(List<? extends T>)` no longer overrides the `ItemWriter` method in Spring Batch 5. In the new implementation, get the list with `chunk.getItems()` if the current logic needs to work with a List.

| Version | Writer signature |
|---|---|
| Spring Batch 4.x | `write(List<? extends T> items)` |
| Spring Batch 5.x | `write(Chunk<? extends T> chunk)` |

Do not confuse the `List` type that the application obtains from a `Chunk` with the interface signature. A writer using a List internally does not change the Spring Batch 5 API contract.

## 4. Declaring a Writer in a Chunk Step

The writer is attached to the step through the builder. The chunk's output generic must match the type the writer receives.

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
        .build();
}
```

In this example, the reader provides `OrderRow`, the processor converts it to `Order`, and the writer receives a chunk of `Order`. If no processor is used, the input and output types can be the same.

Declaring generics explicitly helps the compiler detect cases where the writer receives the wrong type. Avoid raw types or manual casts just to make the code compile, because they hide contract errors.

## 5. The Size of the List the Writer Receives

The writer receives the items remaining after the processor completes. The number of items in the chunk can be smaller than the commit interval because:

- It is the last chunk and the data source has run out.
- The processor returns `null` to filter some items.
- Some items are skipped according to the fault-tolerance policy.
- The data source does not have enough items to fill the chunk.

For example, with a commit interval of 5, the reader reads five items but the processor filters one item. The writer may receive four output items. For the last chunk, if the source has only two valid items left, the writer receives a smaller group.

| Scenario | Items the reader read | Items the processor passed to the writer |
|---|---:|---:|
| Full chunk, no filter/skip | 5 | 5 |
| One item filtered with `null` | 5 | 4 |
| Two items filtered with `null` | 5 | 3 |
| Last chunk with only two valid items left | 2 | 2 |

Therefore, do not write code that depends on `chunk.size()` always being equal to the commit interval. Handle the actual number of items in the call correctly.

## 6. Iterating a Chunk and Handling the List Safely

There are two commonly used ways to access the items:

```java
// Iterate over the Chunk directly
for (Order order : chunk) {
    process(order);
}

// Or get the List
List<? extends Order> orders = chunk.getItems();
for (Order order : orders) {
    process(order);
}
```

Choose the approach that fits the API the writer needs to use. If the target library accepts a `Collection`, a `List`, or a batch request, you can take `getItems()` and pass it in. If you only need to iterate, using the chunk directly avoids creating an extra reference variable.

Do not store the chunk or the list of items in a field to process after the method ends. A chunk belongs to a specific processing run; keeping a reference can increase memory use, leak data, or create a race condition if the step runs multi-threaded.

## 7. Batch Writing to a Database

When writing to a database, batch operations are usually more efficient than sending a separate statement for each item. Spring JDBC supports batch updates; the writer can map each element in the list into a prepared statement.

```java
public class JdbcOrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        List<? extends Order> orders = chunk.getItems();
        if (orders.isEmpty()) {
            return;
        }

        jdbcTemplate.batchUpdate(
            "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL) VALUES (?, ?, ?)",
            new BatchPreparedStatementSetter() {
                @Override
                public int getBatchSize() {
                    return orders.size();
                }

                @Override
                public void setValues(PreparedStatement ps, int index) throws SQLException {
                    Order order = orders.get(index);
                    ps.setString(1, order.id());
                    ps.setString(2, order.customerId());
                    ps.setBigDecimal(3, order.total());
                }
            }
        );
    }
}
```

The code snippet assumes the `JdbcTemplate` uses the same datasource that the step's transaction manager manages. In practice, you need to handle duplicate keys according to business policy, for example insert new, update, or upsert. If the writer encounters an SQL error, the exception needs to be propagated so Spring Batch can decide on rollback, retry, or skip according to the configuration.

## 8. Built-in Spring Batch Writers

You do not always need to write your own `ItemWriter`. Spring Batch provides many specialized writers, for example:

- `JdbcBatchItemWriter`: writes items to a database using JDBC batch update.
- `FlatFileItemWriter`: writes data to a text file.
- `StaxEventItemWriter`: writes XML data using StAX events.
- `CompositeItemWriter`: passes the same chunk to multiple delegate writers.

Built-in writers help standardize resource handling, transactions, or state depending on the writer type. Configure the item type, SQL/field mapping, encoding, append/overwrite, and lifecycle according to the requirements of the destination data.

Example of declaring a `JdbcBatchItemWriter` in builder style:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL)
            VALUES (:id, :customerId, :total)
            """)
        .beanMapped()
        .build();
}
```

This example assumes `Order` has the corresponding `id`, `customerId`, and `total` properties. If you use a record or a data type that does not fit property mapping, choose `itemPreparedStatementSetter` or another mapping approach the writer supports. Do not use `.beanMapped()` if the property names do not match the placeholders.

## 9. Transactions and Rollback When write Fails

In a chunk-oriented step, the writer is usually called within the chunk's transaction. If the writer writes to a database in the same transaction resource as the step's transaction manager, the changes can be committed together with the chunk when all processing succeeds.

If the writer throws an exception before commit, the transaction can roll back. Spring Batch then applies the configured fault-tolerance policy. Depending on the type of error, the chunk may be retried, an item may be skipped, or the step may end in failure.

```text
Writer writes item A
Writer writes item B
Writer hits an error at item C
        |
        v
Transaction rollback
        |
        v
Chunk is recovered according to the retry/skip policy
```

This does not mean every effect of the writer is rolled back automatically. If the writer calls an HTTP API, sends an email, or writes to another database that does not participate in the transaction, the side effect may already have happened even though the chunk's transaction rolled back. These operations need an idempotency key, an outbox, or a reconciliation mechanism to avoid duplicate execution on retry/restart.

## 10. Do Not Assume the Writer Is Called Only Once

The writer can be called again when a chunk is retried or recovered after an error. A write may already have created an external side effect before the error occurred in a later step. Therefore, the writer needs safe behavior when it receives the same item again.

Ways to reduce risk:

1. Use a unique business key to prevent creating duplicate records.
2. Use an upsert or a conditional update statement when appropriate.
3. Use an idempotency key for requests sent to external systems.
4. Write an outbox within the same database transaction, then process the messages separately.
5. Store the processing status and design reconciliation to detect missing or duplicate data.

Do not catch every exception in `write` and ignore it. If the writer swallows exceptions, Spring Batch may treat the chunk as successful and commit the checkpoint even though the data has not been fully written.

## 11. Item Order and Consistency

Normally, the writer receives items in the order the pipeline produced them. If order has business meaning, for example time-ordered events or records that depend on each other, the writer needs to preserve the order when writing or define clearly how to sort.

When the writer sends a chunk to a system whose API accepts batches, you need to ensure that the order of responses or errors can be mapped back to the correct item. If the API returns only a single overall result for the whole batch, understand the partial success mechanism clearly: some items may have been written successfully even though the overall request reports an error.

With a database, unique key and foreign key constraints are usually an important layer of protection. However, do not rely on SQL execution order if the database does not guarantee that order; model the relationships and transactions explicitly.

## 12. Writers in Multi-Threaded Processing and Partitioning

When a step runs multi-threaded or with partitioning, multiple threads may call the writer depending on the configuration. A writer with mutable state or that uses non-thread-safe resources needs to be protected.

- Use a stateless writer if possible.
- Do not keep the chunk's list of items in shared state.
- Ensure JDBC connections are managed through the transaction manager; do not share a manually created connection between threads.
- Check the write order and data constraints when multiple partitions write to the same table.
- If each partition uses its own writer, ensure resources are opened/closed according to the corresponding lifecycle.

`SynchronizedItemStreamWriter` can help synchronize some non-thread-safe writers when running multi-threaded, but synchronization can reduce throughput. Prefer designing state and partitioning the data appropriately.

## 13. Common Mistakes When Implementing write

| Mistake | Consequence | Resolution |
|---|---|---|
| Implementing `write(List)` in Spring Batch 5 | Does not correctly override the `ItemWriter` API | Use `write(Chunk<? extends T>)` and `chunk.getItems()` when you need a List |
| Assuming each write receives the full commit interval | Errors on the last chunk or when the processor filters items | Use the actual size of the chunk |
| Writing each item over a new connection | Increases overhead and reduces throughput | Use the transaction manager and an appropriate batch JDBC writer |
| Swallowing exceptions when a write fails | Metadata may commit even though the data was not fully written | Throw the exception so the step's recovery handles it |
| Calling an external API that is not idempotent | Retry can create duplicate side effects | Use an idempotency key or an outbox |
| Sharing a mutable writer across multiple threads | Race condition or incorrect data | Use a thread-safe writer or separate state |
| Wrong property or column mapping | Wrong or missing data written | Verify the contract and test the mapping |

## 14. Testing ItemWriter

A writer should be tested in isolation with representative scenarios:

1. A chunk containing multiple valid items and all of them are written.
2. A chunk with fewer items than the commit interval.
3. A last chunk smaller than the configured size.
4. An item with a null value or one that violates a constraint per the contract.
5. The database raises an error in the middle of a batch write and the transaction rolls back correctly.
6. The same item is sent again due to retry/restart and does not create unexpected duplicate data.
7. Multiple threads/partitions write concurrently if the job is configured to run in parallel.

Integration tests should use a database or a test environment compatible with real transactions. Check not only the number of rows written but also the commit/rollback state and the idempotency of the write operation.

## Conclusion

`ItemWriter` receives a group of items that have passed through the processor and writes that group to the destination. With Spring Batch 5, the `write` method receives `Chunk<? extends T>`; you can iterate over the chunk directly or get the list with `chunk.getItems()`. The old Spring Batch 4 API receives `List<? extends T>`, so the signature needs to be updated when upgrading versions.

The writer must handle the actual number of items correctly, preserve the data type contract, participate in the transaction appropriately, and propagate errors outward when it cannot write successfully. For side effects outside the transaction or multi-threaded processing, you need additional idempotency and state control so that retry/restart does not create incorrect or duplicate data.
