# Separating input, transformation, and output

In Spring Batch, chunk-oriented processing divides a processing flow into three main responsibilities: reading input data, transforming each item, and writing the output results. These three responsibilities correspond to `ItemReader`, `ItemProcessor`, and `ItemWriter`.

`ItemReader` fetches data from a source such as a CSV file, database, message queue, or API. `ItemProcessor` validates, normalizes, filters, or transforms an item into the model the next stage needs. `ItemWriter` receives a group of processed items and writes them to a destination such as a database, file, or another system. Spring Batch combines the three components within a chunk transaction to manage commit, rollback, retry, skip, and restart.

Separating input, transformation, and output lets each component focus on one task. You can change the data source while keeping the business logic, change how data is written without modifying the reader, or test the transformation independently of the database and file system.

## The Reader – Processor – Writer model

A chunk-oriented step usually has this data flow:

```text
Data source
     |
     v
  ItemReader<I>
     |
     | reads each item I
     v
ItemProcessor<I, O>
     |
     | converts I to O, or returns null to filter
     v
  ItemWriter<O>
     |
     | writes a Chunk<O>
     v
Data destination
```

The notation `I` is the input data type and `O` is the output data type after the transformation. The two types can be the same if the processor only validates or normalizes in place, but it is usually better to use separate types to express the boundary between the source data and the business model.

| Component | Interface | Responsibility | Unit of work |
| --- | --- | --- | --- |
| Input | `ItemReader<I>` | Read items from the source and determine when the data has run out | One item per `read()` call |
| Transformation | `ItemProcessor<I, O>` | Validate, transform, enrich, or filter items | One item per `process()` call |
| Output | `ItemWriter<O>` | Write the processed items to the destination | A chunk of many items |

The reader and processor work item by item. The writer receives the items that have been processed by the processor in a chunk, so it can write in batches to reduce the number of calls to the database or target system.

## Input: ItemReader

`ItemReader<T>` is the abstraction for reading data. The `read()` method returns one item each time it is called. When there are no more items, the reader returns `null` to signal the end of input.

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

A reader can read from:

- CSV, fixed-width, XML, or JSON files.
- Database tables through JDBC or JPA.
- A message queue or an event source.
- An API, object storage, or an external system.
- A collection or a custom-built data source.

The reader is responsible for converting source data into the input type the processor understands. For example, `FlatFileItemReader` reads each CSV line and maps it to `OrderInput`; `JdbcCursorItemReader` reads each row of a query result and maps it to a Java object.

### The contract of read()

Some important rules:

- Each `read()` call returns one item, or `null` when the data has run out.
- `null` signals the end of input; it is not an empty item for the processor to handle.
- Read or parse errors can fail the step unless an appropriate skip/retry is configured.
- A reader with state needs to save its state to support restart, for example the line position, offset, or the last record key.
- The reader needs to follow the lifecycle and thread-safety rules of the type of step in use.

### Example of a CSV reader

Suppose the file `orders.csv` has this content:

```csv
orderId,customerId,amount,status
O-1001,C-01,125.50,NEW
O-1002,C-02,89.00,CANCELLED
O-1003,C-03,240.00,NEW
```

Define the input model:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount,
        String status) {
}
```

The reader uses `FlatFileItemReader` to read the file, split the columns, and map each line to `OrderInput`:

```java
@Bean
FlatFileItemReader<OrderInput> orderReader(
        @Value("${batch.input.orders}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount", "status")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount"),
                    fields.readString("status")))
            .build();
}
```

The reader handles file access, column splitting, and converting raw data into a Java type. Business rules such as whether an order may be written are placed in the appropriate processor or validator.

### Readers with state and restart

Many readers provided by Spring Batch can save state into the `ExecutionContext`. For a file reader, the state can include the read position or the number of lines processed. When the step is restarted, the reader restores the state to continue from an appropriate position.

A custom reader that wants to support restart usually needs to implement a state save and restore mechanism through the Spring Batch lifecycle, such as `ItemStream` with the `open`, `update`, and `close` methods. If the reader does not save state, you need to understand clearly that a restart may re-read from the beginning or may not be able to continue from the desired position.

For a reader that reads from a database, there should be a stable order and a suitable paging/cursor approach. If the source data changes while the job runs, determine the snapshot or query conditions to avoid missing or duplicate records.

## Transformation: ItemProcessor

`ItemProcessor<I, O>` receives an input item of type `I` and returns an output item of type `O`. This is the appropriate place to perform per-record conversion logic before writing.

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

A processor typically performs:

- Validating data against business rules.
- Normalizing strings, codes, dates, or units of measure.
- Converting a source DTO into a domain object or output DTO.
- Computing, mapping statuses, or enriching data.
- Filtering items that do not need to be written by returning `null`.

The processor should focus on the item's transformation. Accessing a database or calling an external system in the processor can increase processing time, cause side effects on retry, and make the logic hard to test. If you need reference data, consider preloading it, using a controlled cache, or designing a service that fits transactions and retry.

### Example of converting OrderInput to Order

Define a separate output model:

```java
public class Order {
    private final String orderId;
    private final String customerId;
    private final BigDecimal amount;
    private final String status;

    public Order(
            String orderId,
            String customerId,
            BigDecimal amount,
            String status) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.amount = amount;
        this.status = status;
    }

    public String getOrderId() { return orderId; }
    public String getCustomerId() { return customerId; }
    public BigDecimal getAmount() { return amount; }
    public String getStatus() { return status; }
}
```

The processor converts the input, validates the data, and filters out cancelled orders:

```java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return new OrderProcessor();
}

public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("amount must be positive");
        }

        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return null;
        }

        return new Order(
                input.orderId().trim(),
                input.customerId().trim(),
                input.amount(),
                input.status().trim().toUpperCase(Locale.ROOT));
    }
}
```

The example assumes `customerId` and `status` already have valid values after reading; in a real application you need to check for null and business rules for these fields. `InvalidOrderException` is a business exception defined by the application.

### Filtering an item by returning null

If `process()` returns `null`, Spring Batch drops that item from the output flow. The filtered item is not passed to the writer. This is how to express a record that is structurally valid but does not need to be output to the destination, for example a cancelled order or a transaction outside the report's scope.

Distinguish two cases:

| Processor result | Meaning | Does the writer receive the item? |
| --- | --- | --- |
| Returns an object | The item was converted successfully | Yes |
| Returns `null` | The item is deliberately filtered | No |
| Throws an exception | Processing the item hit an error | Depends on the retry/skip configuration; if it cannot be handled, the step fails |

Do not use `null` to hide bad data. If an item is invalid and needs to be recorded or handled per an error policy, throw an appropriate exception and configure skip, retry, or separate error handling.

### Processor chain

When the transformation has multiple independent stages, you can combine processors in a chain. For example:

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
EnrichOrderProcessor
    |
    v
Order
```

Spring Batch provides `CompositeItemProcessor` to combine processors. The output type of the previous processor must be compatible with the input type of the next processor.

```java
@Bean
CompositeItemProcessor<OrderInput, Order> orderProcessorChain(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, ValidatedOrder> validateProcessor,
        ItemProcessor<ValidatedOrder, Order> mapProcessor) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, Order>()
            .delegates(
                    normalizeProcessor,
                    validateProcessor,
                    mapProcessor)
            .build();
}
```

The types `NormalizedOrder` and `ValidatedOrder` represent intermediate results. This split is useful when each stage has clear logic and can be reused or tested separately. For a simple transformation, a single processor is usually easier to read.

## Output: ItemWriter

`ItemWriter<T>` receives a group of items that have been processed by the processor and writes them to the destination. In Spring Batch 5, the `write` method receives a `Chunk`:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

In older versions, the signature of `ItemWriter` may use `List<? extends T>`; use the API that matches the project's framework version. In terms of processing, the writer always receives the set of items of the current chunk rather than being called separately for each item.

A writer can write to:

- A database through `JdbcBatchItemWriter`, `JpaItemWriter`, or a custom-implemented writer.
- A file through `FlatFileItemWriter` or a dedicated writer.
- A message broker or an external system.
- A storage service or a target API.

### Example of writing to a database

With `JdbcBatchItemWriter`, you can write a group of `Order`s using batch SQL:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders
                        (order_id, customer_id, amount, status)
                    VALUES
                        (:orderId, :customerId, :amount, :status)
                    """)
            .beanMapped()
            .build();
}
```

`beanMapped()` maps the named parameters in the SQL to the properties of the output object. The writer does not need to know whether the original data came from CSV or a database; it only needs to receive the correct `Order` type.

If you need to update instead of insert, you can use an update/upsert SQL statement appropriate to the database management system. You need to determine the business key and the behavior when the writer is called again due to retry or restart.

### Example of a custom writer

In Spring Batch 5, a custom writer can receive a `Chunk`:

```java
public class AuditItemWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            System.out.printf(
                    "Writing order %s for customer %s%n",
                    order.getOrderId(),
                    order.getCustomerId());
        }
    }
}
```

The example only illustrates the writer contract; `System.out` is not a place to store production data. A real writer should use a repository, a file writer, or a client to the target system and handle errors according to the step's transaction policy.

## Connecting the three components in a chunk step

When declaring a step, Spring Batch receives the reader, processor, and writer and orchestrates them according to the commit interval. The example below uses the Spring Batch 5 builder API:

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

The generic types in `.<OrderInput, Order>chunk(...)` indicate that the reader produces `OrderInput`, the processor converts to `Order`, and the writer receives `Order`. `chunk(100, transactionManager)` configures up to 100 input items per chunk before committing in the normal processing flow.

In a real application, you need to declare the reader, processor, and writer beans with appropriate names, and configure the input resource, datasource, and target schema. The code focuses on how to combine the three components in a step.

## How is a chunk processed?

Suppose the `commit-interval` is 3 and the source has five items. The general processing flow:

```text
Chunk 1
  Reader: I1, I2, I3
  Processor: O1, null, O3
  Writer: [O1, O3]
  COMMIT

Chunk 2
  Reader: I4, I5, EOF
  Processor: O4, O5
  Writer: [O4, O5]
  COMMIT
```

Item `I2` is filtered by the processor returning `null`, so the writer receives only `O1` and `O3`. The number of items read and the number of items written can differ because the processor can filter items.

The steps at a conceptual level:

1. Open a transaction for the chunk.
2. The reader is called multiple times to get the input items for the chunk.
3. For each item, the processor is called to produce an output or filter the item.
4. The writer receives the remaining outputs in the chunk and writes them.
5. Spring Batch updates the metadata and execution context according to the step's configuration.
6. The transaction commits; if an error makes the transaction roll back, the changes participating in the transaction are rolled back.
7. Continue with the next chunk until the reader reports no more data.

The details of the lifecycle and when listeners are called can differ by step type and version, but the chunk transaction boundary is the foundation for understanding commit, rollback, and restart.

## Transactions and consistency

In a chunk-oriented step, the reader, processor, writer, and metadata updates are orchestrated around the chunk's transaction. When the writer writes to the same database resource and uses an appropriate transaction manager, the business data and the checkpoint can commit or roll back together.

If the writer writes to a system outside the database's transaction, such as calling HTTP or publishing a message, that side effect is not automatically rolled back when the chunk fails. A retry may send the message or call the API again. In that case you need an idempotency key, the outbox pattern, or an appropriate reconciliation mechanism.

The reader also needs to be considered according to the data source. With a database cursor or paging reader, transactions and snapshot isolation can affect the data read. With a file reader, the read position is saved in the execution context for restart. Not every reader can roll back external effects of reading; you need to rely on the state management of the specific reader.

### Why should the writer be idempotent?

Suppose the writer writes a chunk successfully to the target system, but the process stops before the checkpoint is saved. On restart, the same items may be sent to the writer again. If the writer inserts without duplicate control, the result can create duplicates.

Ways to reduce the risk:

- Use a stable business key and a unique constraint.
- Use an upsert or a conditional write operation per business rules.
- Attach an idempotency key when calling an API or publishing a message.
- Store processing status at the target system to recognize requests that have already been applied.
- Reconcile cases where the transactions of the batch metadata and the target data do not commit simultaneously.

## Skip, retry, and errors at each layer

Errors can appear during reading, transformation, or writing. You need to distinguish the source of the error to configure an appropriate policy.

| Layer | Example error | Handling approaches to consider |
| --- | --- | --- |
| Reader | Malformed CSV line, source connection error | Skip recoverable parse errors; retry transient errors if the read operation is safe |
| Processor | Invalid data, reference service transiently failing | Skip data errors per rules; retry transient errors if the processor creates no side effects |
| Writer | Deadlock, database timeout, target system error | Retry transient errors; skip only if the business allows dropping the record |

An example skip configuration for a specific kind of data error:

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

With this configuration, at most 20 errors of type `InvalidOrderException` are skipped per the step's fault-tolerance rules. Errors exceeding the limit or errors not of a declared type can fail the step. Do not broadly skip every exception because it can hide infrastructure errors or lose data.

Retry suits transient errors such as deadlocks or timeouts if the operation can be safely re-performed. The processor and writer need to avoid side effects that cannot be safely repeated. For fixed business errors such as a non-existent customer code, retry usually does not help resolve the problem.

## Restart and ExecutionContext

When a job is stopped or fails, Spring Batch can restart the `JobInstance` if the configuration and state allow it. A reader with restart capability saves read progress into the `ExecutionContext`, while the repository stores metadata so that a new run knows where to continue.

In the model that separates input, transformation, and output:

- The reader needs to restore the correct position or continuation key.
- The processor should have deterministic results from the input and stable reference state within the scope of a run.
- The writer needs to handle safely if items are sent again due to retry or restart.
- The identifying parameters need to remain unchanged when restarting the same logical job.

If the processor depends on the current time, changing reference data, or an external API with side effects, the restart result may differ from the first run. Consider passing business values through `JobParameters`, saving the necessary reference snapshot, or designing a processor that is safe to repeat.

Do not increment an identifying timestamp on every restart. Doing so creates a new `JobInstance` and separates the history from the previous execution.

## Separating components for independent testing

A major benefit of the Reader–Processor–Writer model is that you can test each layer with small data without running the entire job.

### Testing the processor

The processor is usually the easiest part to test because its input and output are Java objects:

```java
@Test
void filtersCancelledOrders() throws Exception {
    OrderProcessor processor = new OrderProcessor();

    OrderInput input = new OrderInput(
            "O-1002", "C-02", new BigDecimal("89.00"), "CANCELLED");

    assertNull(processor.process(input));
}
```

Other tests can check string normalization, calculations, status conversions, and exceptions for invalid data.

### Testing the reader

For a file reader, use a small sample file and check each returned item in the same order. Also check the header, blank lines, encoding, delimiters, missing values, and EOF behavior. For a reader with state, you need to check the ability to save state and then reopen to continue.

### Testing the writer

For a database writer, you can use a test database or an appropriate test slice to confirm that many items in a chunk are written correctly. Check constraints, rollback on errors, upsert behavior, and the ability to handle repetition.

### Step integration testing

Finally, test the step with the real reader, processor, and writer or test doubles. Confirm the number of items read, the number of items written, items filtered/skipped, the step status, and the result after restart. Integration testing helps confirm that the three components cooperate correctly across the transaction boundary.

## Changing the source or destination without changing the business logic

When the three responsibilities are clearly separated, you can reuse a processor for multiple sources and a writer for multiple jobs.

For example:

```text
CSV Reader --------+
                   |
Database Reader ---+----> Order Processor ----> Database Writer
                   |                    |
API Reader --------+                    +------> File Writer
```

`OrderProcessor` can be shared if the readers produce the same `OrderInput` type. If another source has a different schema, you only need to write an adapter reader to map to the same input model. Similarly, multiple writers can receive the same output type if the application needs to write to multiple destinations, but you must clearly determine the transaction and the behavior when one destination succeeds while another fails.

It is not always appropriate to reuse a processor for every flow. If the business rules differ, use a separate processor or configure a clear chain to avoid one class containing too many branches per data source.

## Points to consider when designing each layer

### Designing input

- Choose an input type that reflects the structure of the source data and does not depend too much on the target database.
- Determine a stable read order, the source filter conditions, and how to handle data that changes while the job runs.
- Use a reader with state if you need restart; configure a unique and stable reader name.
- Decide which parse errors are skipped and which must stop the job.
- Avoid loading all large data into memory; prefer an appropriate cursor, paging, or streaming.

### Designing transformation

- Keep the processor focused on one clear task.
- Distinguish malformed data, data that violates business rules, and valid data that does not need output.
- Return `null` only when you want to filter an item deliberately.
- Avoid non-idempotent side effects in the processor.
- Keep the transformation deterministic and easy to test; pass the needed configuration via constructor or job parameters.
- Split the processor into a chain when each stage is independent enough and has reuse benefits.

### Designing output

- Write in batches to take advantage of batch insert/update if the target system supports it.
- Determine the transaction manager and how the writer participates in the chunk transaction.
- Design idempotency so retry/restart does not create duplicate data.
- Clearly specify how to handle per-item errors and whole-chunk errors.
- Avoid performing side effects that cannot be rolled back without a compensation or reconciliation mechanism.
- Monitor throughput, write time, the number of retries, and errors from the target system.

## Common design mistakes

### Putting all the logic in the reader

A reader that queries, applies business rules, and writes auxiliary data at the same time is hard to reuse and test. The reader should focus on fetching data and mapping to the input type. Transformation belongs to the processor; writing data belongs to the writer.

### The processor calls an API or writes to the database for each item

This can create a huge number of small requests, slow down the job, and cause side effects on retry. If you need to enrich data, consider batch lookup, a bounded cache, or designing a service with appropriate transaction/idempotency.

### The writer re-handles parsing of the source data

If the writer has to understand the CSV format or the column names of the source system, the boundary between input and output is not clear. The writer should receive a stable output model, independent of the input format.

### Using null for every kind of error

Returning `null` deliberately filters an item. Using it for bad data or system errors makes the record disappear without statistics or explanatory information. Use an exception and a skip policy when you need to record errors.

### Not accounting for the target system's transaction

A writer that calls an API or publishes a message may have already created a side effect even if the chunk rolls back. Design idempotency, an outbox, or a confirmation mechanism to handle retry safely.

### Choosing a chunk size without measuring load

A chunk that is too small increases the number of commits and writer calls; a chunk that is too large holds the transaction longer and increases locks and the rollback scope. Measure performance with data close to reality and then choose an appropriate value.

## When is this model suitable?

The Reader–Processor–Writer model suits a job that needs to process a set of items as a stream, can be divided into chunks, and where each item can be read, transformed, and written independently. It is especially useful when input and output have different formats or are in different systems.

For example:

| Problem | Reader | Processor | Writer |
| --- | --- | --- | --- |
| Importing CSV orders | Read CSV lines | Parse, validate, normalize orders | Insert/upsert into the database |
| Synchronizing customers | Read customers from the source database | Normalize addresses, map statuses | Write to the target database or API |
| Generating reports | Read transactions by period | Compute and group data | Write CSV or a report file |
| Converting legacy data | Read old records | Map to the new model | Write to the new schema |

If the work is just a simple operation that does not need to process each item, a `Tasklet` may be more suitable. If you need to handle multiple sources/destinations with complex logic, you can split into multiple steps or use a separate flow. Chunk processing shows its value when you need to manage commit, restart, skip/retry, and throughput for a set of items.

## Takeaways

In chunk processing, `ItemReader` is responsible for fetching each input item, `ItemProcessor` transforms or filters each item, and `ItemWriter` writes a group of the chunk's outputs. Separating the three layers lets you change the source and destination independently, test the logic clearly, and manage transactions per chunk. The reader needs appropriate state for restart; the processor should focus on a testable transformation; the writer needs batch writes and idempotency for retry or restart. Returning `null` from the processor means filtering the item, while errors that need handling must be expressed as exceptions along with an appropriate skip/retry policy.
