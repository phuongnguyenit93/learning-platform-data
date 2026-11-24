# ItemReader, ItemProcessor, and ItemWriter

In Spring Batch, **chunk processing** is a model for processing data in groups of items. A step following this model typically reads data from a source, optionally transforms or filters each item, and then writes the results as a chunk to a destination. The three abstractions responsible for those tasks are `ItemReader`, `ItemProcessor`, and `ItemWriter`.

These three components clearly separate the responsibilities of a batch processing flow. The reader focuses on fetching data, the processor focuses on applying processing rules to each item, and the writer focuses on writing the results. Spring Batch coordinates them according to the chunk size, manages transactions, and stores metadata to support monitoring as well as restart.

## 1. The read-process-write flow in a chunk

A chunk-oriented step is typically configured with three components:

```text
Data source
     |
     v
  ItemReader
     |
     | item by item
     v
ItemProcessor (optional)
     |
     | transformed or filtered item
     v
   ItemWriter
     |
     v
Data destination

Spring Batch groups items into chunks, manages transactions,
checkpoints, and the StepExecution state.
```

Suppose the chunk size is 100. Spring Batch calls the reader repeatedly to get up to 100 items. Each item is passed through the processor if the step has a processor configured. The results are collected and passed to the writer in a single chunk write. When the transaction commits successfully, the framework continues reading the next chunk.

```text
Chunk 1: read up to 100 items
         -> process each item
         -> write the group of results
         -> commit

Chunk 2: read up to the next 100 items
         -> process each item
         -> write the group of results
         -> commit

Last chunk: may have fewer than 100 items
            -> write the remainder
            -> commit
            -> end the step when the reader reports no more data
```

Chunk size is the number of input items the step gathers for one processing cycle, and it is not necessarily equal to the number of items the writer receives. If the processor filters out some items by returning `null`, the output chunk will have fewer items than the input chunk.

## 2. The contract of the three interfaces

The core interfaces can be understood through the following method signatures:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}

public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}

public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

This is the API for Spring Batch 5 and later. In Spring Batch 4 and earlier versions, the `ItemWriter.write` signature uses `List` instead of `Chunk`, so older writer code may differ from current code.

| Component | Input | Output | Responsibility |
|---|---|---|---|
| `ItemReader<T>` | The data source or read state | One item of type `T` per call | Fetch the next item; return `null` when there is no more data. |
| `ItemProcessor<I, O>` | One item of type `I` | An item of type `O`, or `null` to filter | Validate, transform, enrich, or exclude the item. |
| `ItemWriter<T>` | A `Chunk` of items of type `T` | No return value | Write a group of items to the destination. |

The processor is an optional component. If you do not need to transform or filter data, the step can connect the reader directly to the writer. When there is a processor, the processor's output type `O` must match the item type the writer accepts.

## 3. ItemReader: reading items one by one from a data source

`ItemReader<T>` is responsible for supplying the input data for the step. Each time the framework calls `read()`, the reader returns the next item. When there is no more data, the reader returns `null` to signal the end.

For example, a reader can return orders read from a CSV file one at a time:

```text
read() 1st call -> OrderInput(orderId="O-001", ...)
read() 2nd call -> OrderInput(orderId="O-002", ...)
read() 3rd call -> OrderInput(orderId="O-003", ...)
read() 4th call -> null
```

The `null` value has a special meaning: it signals that there are no more items to read. If the business data has a nullable field, represent that field inside the item object; do not use a `null` item to represent a record with an empty field.

### Common data sources

Spring Batch has many ready-made readers for different data sources:

| Reader | Data source and how it works |
|---|---|
| `FlatFileItemReader` | Reads text files, CSV, or line-delimited data. |
| `JdbcCursorItemReader` | Reads JDBC query results using a cursor. |
| `JdbcPagingItemReader` | Reads data page by page through paged queries. |
| `JpaPagingItemReader` | Reads JPA entities page by page. |
| `RepositoryItemReader` | Reads data through a Spring Data repository that supports paging. |
| `StaxEventItemReader` | Reads XML elements using a streaming mechanism. |

Choose a reader based on the data size, paging capability, resource management, restart requirements, and the characteristics of the source. For large files, read as a stream instead of loading the whole file into memory. For large tables, a cursor or paging may be suitable depending on the database, transaction, and query plan.

### A reader should not do the processor's job

A reader should focus on fetching data and mapping source data into items. For example, `FlatFileItemReader` can parse a CSV line into `OrderInput`. Rules such as whether an order has a valid amount or whether a customer is allowed to buy usually belong in the processor or a business service that the processor calls.

Separating responsibilities lets you change the data source without rewriting business rules. The same processor can be used with a reader from a file, database, or API as long as the input item types are compatible.

### Readers and read state

Many of Spring Batch's built-in readers support restart by saving the read state in the `ExecutionContext`. Components that implement `ItemStream` have a lifecycle of `open`, `update`, and `close`:

- `open`: open resources and restore the saved state if any.
- `update`: write the current state into the `ExecutionContext` for a checkpoint.
- `close`: release resources such as streams or cursors.

For example, a file reader can save the line position it has read. After a chunk commits, Spring Batch saves a checkpoint. If the step fails, a restart can reopen the file and continue from an appropriate position.

Not every reader can restart. A custom reader that wants to support this capability usually needs to implement `ItemStream` or `ItemStreamReader`, save the necessary state in `update`, and restore the state in `open`. For a reader that does not support saving state, a restart may have to read again from the beginning, or may need a recovery mechanism built by the application itself.

### Readers must handle re-reading

When a chunk rolls back, the framework may re-read items that have not been committed. Therefore, you should not assume each item has `read()` called exactly once over the entire job lifecycle. A reader needs consistent behavior when a transaction rolls back and when a restart happens.

If the reader gets data from a source whose consumption state cannot be undone, such as a queue where receiving a message is acknowledged immediately, you need to design an appropriate acknowledgment and transaction mechanism. Otherwise, the job may lose data on rollback or receive unexpected items again.

## 4. ItemProcessor: transforming or filtering each item

`ItemProcessor<I, O>` receives an item of type `I` and returns an item of type `O`. The input and output types may be the same or different.

A processor typically handles these tasks:

- Validating business rules.
- Normalizing data such as codes, strings, dates, or amounts.
- Converting an input DTO into a business domain object.
- Adding data needed before writing.
- Filtering out items that do not need to go to the writer.

An example converting data imported from a file into an order object:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Order amount must be greater than zero");
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount());
    };
}
```

Here, the processor receives `OrderInput`, checks the amount, and then creates an `Order`. The reader and writer do not need to know the specific conversion rules.

### Returning null to filter an item

An important characteristic of `ItemProcessor` is that it can return `null`. Spring Batch interprets this as a request to filter out the item: that item is not forwarded to the writer.

```java
@Bean
ItemProcessor<OrderInput, Order> orderFilter() {
    return input -> {
        if (input.amount().signum() <= 0) {
            return null;
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount());
    };
}
```

In the example, orders with a non-positive amount are excluded from the processor's output. This is a filter, not a skip caused by an exception.

### Distinguishing filter from skip

These two mechanisms serve different purposes:

| Mechanism | How it is done | Meaning |
|---|---|---|
| Filter | The processor returns `null` | The item is deliberately excluded from the results and not passed to the writer. |
| Skip | An exception is thrown and the skip policy allows it | The failing item or operation is ignored according to the step's error policy. |

If an item does not meet the conditions for processing but this is a normal business case, a filter may be appropriate. If an item has malformed data, a mapping error, or a violation that needs to be recorded as a processing error, you can throw an exception and configure skip along with a listener or an error-recording mechanism.

You should not return `null` for every kind of error just to let the job continue. That loses information about the cause and can cause invalid data to be silently dropped.

### The processor should focus on item processing

A processor is usually called once per item in the chunk. Keep the processing logic controllable and easy to test. Avoid side effects that cannot be undone, such as sending emails, unless an appropriate idempotency design is in place. If the chunk rolls back or the step restarts, the processor may be called again for the same item.

For complex business rules, the processor can call a separate service. This lets you reuse the logic and keeps the batch layer focused on coordinating items.

### Chaining multiple processors

When you need several sequential transformations, you can use `CompositeItemProcessor` to chain small processors together. For example:

```text
OrderInput
    |
    v
NormalizeOrderProcessor
    |
    v
ValidateOrderProcessor
    |
    v
CalculateTaxProcessor
    |
    v
Order
```

Each processor has a clear responsibility. The output type of the previous processor must be compatible with the input type of the next processor. If a processor returns `null`, the item is filtered and does not continue through the remaining processors.

## 5. ItemWriter: writing a chunk to the destination

`ItemWriter<T>` receives a group of processed items and writes them to the destination. Unlike the reader and processor, which work item by item, the writer receives the entire chunk in a single call.

Some common writers:

- `JdbcBatchItemWriter`: writes many records to the database using a JDBC batch.
- `FlatFileItemWriter`: writes data to a file in a configured format.
- `RepositoryItemWriter`: writes through a Spring Data repository.
- `JsonFileItemWriter`: writes items to a JSON file according to the configuration for the corresponding version.

A writer should focus on persisting results. Computation or checking the main business rules usually belongs in the processor. This division lets the writer change the storage destination without changing the data transformation logic.

### The writer receives a Chunk instead of a single item

In Spring Batch 5 and later, the `write` method receives a `Chunk`:

```java
public void write(Chunk<? extends Order> chunk) throws Exception {
    for (Order order : chunk) {
        // Write the order to the destination.
    }
}
```

The framework collects the results from the processor and then calls the writer. With a chunk size of 100 and no items filtered, the writer usually receives a chunk of 100 items. If some items are filtered, the actual number of items in the output chunk can be smaller.

A writer can use batch insert/update to reduce the number of round trips to the database. For example, `JdbcBatchItemWriter` supports executing one SQL statement for many items using the parameters of each object.

### Writing data and transactions

In a chunk-oriented step, the write operation usually takes place within the chunk's transaction. If the writer throws an exception before commit, the transaction manager can roll back the changes belonging to the same transaction. Spring Batch then applies retry, skip, or marks the step as failed depending on the configuration.

However, rollback only applies to resources participating in the corresponding transaction. If the writer calls an HTTP API, sends an email, or writes to a system that does not participate in the transaction, the external operation may have already succeeded even though the chunk later rolls back. In that case, a retry may resend the same request.

For a writer that integrates with external systems, consider:

- An idempotency key or a unique business code so the receiving system can recognize a repeated request.
- A mechanism to look up the recorded status before resending.
- The outbox pattern or a separate event publishing process when you need to synchronize the database with other systems.
- How to handle a timeout when you are not sure whether the destination system has received the request.

A writer should not assume that a `write` call always happens exactly once over the entire job lifecycle. A retry or restart may cause the same data to be written again.

## 6. Combining the reader, processor, and writer in a Step

In Spring Batch 5 and later, a chunk-oriented step is typically configured with `StepBuilder` and `JobRepository`. The `chunk` method takes the chunk size along with a `PlatformTransactionManager`.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

The generic declaration `.<OrderInput, Order>` indicates:

- The reader supplies `OrderInput`.
- The processor receives `OrderInput` and returns `Order`.
- The writer receives a chunk of `Order` objects.

If you do not need a processor, you can configure the reader and writer with the same item type:

```java
return new StepBuilder("copyOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
```

In this case, items from the reader are passed straight to the writer. There is no need to create a processor just to return the item unchanged.

## 7. Example: reading CSV, transforming, and writing to the database

Suppose the input file has this content:

```csv
order_id,customer_id,amount
O-001,C-101,250000
O-002,C-102,180000
O-003,C-103,99000
```

The application needs to read each line into `OrderInput`, check the amount and convert it to `Order`, and then write it to the `orders` table.

To illustrate the data types, you can use two records:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {
}

public record Order(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

### Configuring the reader

`FlatFileItemReader` reads the file line by line and maps the columns to `OrderInput`:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readString("customerId"),
                    fieldSet.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`@StepScope` allows the reader to receive the file path from JobParameters when the step execution is created. `saveState(true)` lets the reader save its read state to support restart. The input file should be immutable throughout the processing and restart lifecycle.

### Configuring the processor

The processor checks the amount and converts the input object into the object used for writing:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Invalid amount for order " + input.orderId());
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount());
    };
}
```

This example throws an exception when the data is invalid. The step can be configured with a skip policy if the business allows skipping records of that error type. If the business treats such a record as a normal case to filter, the processor can return `null` instead of throwing an exception.

### Configuring the writer

The writer uses `JdbcBatchItemWriter` to write each chunk to the database table:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders (order_id, customer_id, amount)
                    VALUES (:orderId, :customerId, :amount)
                    """)
            .itemSqlParameterSourceProvider(order ->
                    new MapSqlParameterSource()
                            .addValue("orderId", order.orderId())
                            .addValue("customerId", order.customerId())
                            .addValue("amount", order.amount()))
            .build();
}
```

The writer receives the `Order`s converted by the processor and performs a batch insert. In the example, `order_id` needs a unique constraint that matches the business, or the writer needs to be designed to write idempotently if the same data may be run again.

### Putting the components together

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        JdbcBatchItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

This is an illustrative configuration using the Spring Batch 5 and later API. The exception classes, imports, database schema, and infrastructure beans such as JobRepository, transaction manager, and DataSource must be declared appropriately in the application.

## 8. Handling errors with skip and retry

The reader, processor, or writer can all throw exceptions. Spring Batch lets you configure an error policy on the step to decide when to retry, when to skip, and when to end the step with a failed status.

For example, if some orders have invalid data and the business allows skipping at most 20 records of that kind:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
```

When an exception is of a type configured for skip, Spring Batch records the skipped item and continues according to the step's policy. When the skip limit is exceeded, the step fails. In a real application, you should register a listener or an error-recording mechanism to store the order code, the cause, and the data to investigate.

Retry suits some transient errors, such as recoverable connection errors. An example configuration can use `.retry(TransientDataAccessException.class).retryLimit(3)`. However, retry means the operation may be performed again, so the writer and external integrations must be safe to repeat.

You should not skip every exception. System errors such as losing the database connection usually need a retry or to fail the step for later handling, while business data errors can be skipped if there is a process for recording and reconciling them.

## 9. How chunk size affects the reader, processor, and writer

Chunk size is configured in the step, for example `.chunk(100, transactionManager)`. This value affects the number of items gathered into one write-and-commit cycle.

| Chunk size | Common characteristics |
|---:|---|
| Small | Short transactions and few items in memory, but can increase the number of commits and the cost of writer calls. |
| Moderate | Balances commit cost, memory, and throughput in many cases. |
| Large | Can reduce the number of commits, but increases the amount of data in one transaction, memory usage, and rollback time. |

There is no optimal chunk size for every application. Consider the item size, the source speed, the destination's batching capability, memory limits, transaction time, and recovery requirements.

For example, if the processor filters 10 out of 100 items, the writer receives only the remaining items. Chunk size still controls the processing cycle based on input items; it is not a commitment that the writer always receives exactly 100 items.

## 10. Restart and ExecutionContext

Restartability depends on whether Spring Batch and the reading/writing components can save and restore an appropriate state.

Some readers and writers implement `ItemStream`, which allows saving state to the `ExecutionContext`. For a file reader, the state may include the read position. For a file writer, the state may include the write position or the information needed to continue the file.

In chunk processing, state is usually updated at the commit boundary. If a chunk that has not been committed is rolled back, the items in that chunk may be read and processed again. If the reader does not save state or the data source cannot be restored, the application needs a different strategy.

Some points to note:

- Use a stable reader name so checkpoint metadata is associated consistently.
- Do not change the input file's content between the first run and the restart if the identity still points to the same logical file.
- For a custom reader, implement `ItemStream` if you need to save restart state.
- `saveState(false)` can disable state saving for readers that support this option; use it only when you clearly understand the consequences.
- Do not store large amounts of data in the ExecutionContext; store only the small metadata needed for restoration.
- Design the writer to tolerate data being written again if there are retry scenarios or side effects outside the transaction.

## 11. Thread safety and parallel processing

Some readers or writers keep internal state such as a cursor, file position, counter, or buffer. Not every implementation is safe when multiple threads call it concurrently.

When using a multi-threaded step or splitting into partitions, check the documentation of the reader/writer in use:

- Does the reader support multiple threads, or does it need to be synchronized?
- Is each partition given its own reader and its own data range?
- Can the writer receive multiple chunks concurrently without corrupting data?
- Are the ExecutionContext and file/database resources separated per step execution?
- Does the item order need to be preserved?

`SynchronizedItemStreamReader` can help synchronize read calls with a non-thread-safe reader in some configurations. However, synchronization does not by itself solve every problem with ordering, checkpoints, or restart when processing in parallel. Partitioning with dedicated resources and data ranges is usually a clearer approach when you need to divide the work.

## 12. Testing each component individually

Separating the reader, processor, and writer makes it possible to test them independently before testing the whole step.

### Testing the reader

- Provide a small data source with known content.
- Call `read()` multiple times and check that the items come in the expected order.
- Check that the call after the last item returns `null`.
- Check how it handles an empty file, malformed lines, and non-existent resources.
- If it supports restart, check that state is saved and restored correctly.

### Testing the processor

- Check that valid input is transformed correctly.
- Check boundary data and business rules.
- Check the case that returns `null` for filtering.
- Check that exceptions are thrown for the kinds of bad data that need handling.
- If the processor calls a service, check how it handles results and errors from the service.

### Testing the writer

- Pass in a small chunk and confirm the data is written correctly to the destination.
- Check an empty chunk if the implementation can receive that case.
- Check write errors and the transaction/rollback behavior in an integration test.
- Check whether the writer handles data that has already been written safely when it receives it again.

Spring Batch Test can help run a whole step or job with test data. Unit-testing each component helps identify whether the error lies in data mapping, processing rules, or the write operation; integration tests confirm the components work correctly when orchestrated by Spring Batch.

## 13. Common mistakes when implementing the three components

| Problem | Common cause | Solution |
|---|---|---|
| The step stops as soon as the reader returns `null` | `null` is the end-of-data signal per the ItemReader contract. | Do not return `null` to represent a record with an empty field. |
| An item does not reach the writer | The processor returned `null` and Spring Batch filtered that item. | Check the filter condition; if you need to record an error, use an exception and an appropriate skip policy. |
| The writer receives fewer items than the chunk size | Some items were filtered or the last chunk is not full. | This is normal behavior; do not assume the writer always receives exactly the chunk size. |
| Data is written twice after a restart | The writer has non-idempotent side effects or operations outside the transaction. | Use a business key, an idempotency key, or a reconciliation mechanism. |
| The reader re-reads items after an error | A chunk rollback or step restart causes uncommitted items to be processed again. | Design the reader with appropriate state and safe reprocessing. |
| Restart reads from the wrong position | The reader does not save a checkpoint or the input source has changed. | Use a reader that supports ItemStream and keep the data source immutable. |
| Memory grows high | The reader loads all data or the chunk is too large. | Use streaming/paging and choose an appropriate chunk size. |
| Data order changes when running in parallel | Multiple threads process items concurrently. | Determine the ordering requirements; consider partitioning or sequential processing when needed. |
| The writer is slow | Writing item by item with many round trips or lacking batch operations. | Use a batch writer, optimize the SQL, and check indexes/transactions. |

## 14. How to read the code of a chunk-oriented step

When you come across a step in a project, trace the three components in this order:

1. **Find the reader:** identify the data source, the paging/streaming approach, the item type, and the input parameters.
2. **Find the processor:** identify the validation, transformation, enrichment, or filtering rules.
3. **Find the writer:** identify the write destination, how it writes per chunk, and the transaction resources used.
4. **Read the chunk size:** understand how many items are gathered in one processing and commit cycle.
5. **Check fault tolerance:** look at skip, retry, rollback, and the related listeners.
6. **Check restart:** determine whether the reader/writer support ItemStream, what state is saved in the ExecutionContext, and whether the input data is stable.
7. **Check concurrency:** if the step runs in parallel, determine whether the components are thread-safe and whether resources are partitioned appropriately.

Once you understand the read-process-write flow, you can trace back up to the Job to see where the step runs, what input the JobParameters provide, and how the JobRepository stores state.

## 15. Points to remember

- `ItemReader` reads and returns items one at a time; it returns `null` when there is no more data.
- `ItemProcessor` receives an item, can convert the data type, and returns `null` to filter.
- `ItemWriter` receives a chunk of processed items and writes them to the destination.
- The processor is optional; the reader can connect directly to the writer if no intermediate processing is needed.
- Chunk size controls the number of input items in one processing cycle, and does not guarantee the writer always receives exactly that number of items.
- In Spring Batch 5, `ItemWriter.write` receives a `Chunk`; Spring Batch 4 code may use `List`.
- Filtering with `null` differs from skipping due to an exception; choose the mechanism that fits the business meaning.
- Readers/writers that support `ItemStream` can save checkpoints in the `ExecutionContext` to support restart.
- Rollback and restart can cause items to be processed again; the writer and external integrations need appropriate idempotency.
- Check thread safety when using a multi-threaded step or partitioning.

When designing a chunk-oriented step, keep the reader focused on fetching data, the processor focused on per-item processing rules, and the writer focused on writing the chunk. This division makes it easier for the application to change data sources or destinations, to test, to control errors, and to recover after an execution fails.
