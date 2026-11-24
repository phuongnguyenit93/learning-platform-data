# Writers for Files, Databases, or Messages

In Spring Batch, `ItemWriter<T>` is responsible for writing the items that have been read and processed to the output destination. In a chunk-oriented step, the writer receives a chunk's group of items in a single `write` call, which allows writing in batches instead of opening a separate operation for each item.

The destination can be a file, a database, or a messaging system such as Kafka or JMS. Each type of destination differs in transactions, restart, performance, and error handling. Spring Batch provides many built-in writers for common cases; when you need to integrate with your own system, you can implement a custom `ItemWriter`.

## The ItemWriter Contract

In Spring Batch 5, `ItemWriter<T>` receives a `Chunk` containing the output items:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

In older versions of Spring Batch, the `write` signature may accept `List<? extends T>`. Use the correct API for the framework version your project is using.

The writer is called after the reader has provided the items and the processor has transformed them. Items that the processor filters by returning `null` are not in the chunk passed to the writer.

```text
ItemReader
    |
    v
  Input items
    |
    v
ItemProcessor
    |
    v
 Output items
    |
    v
ItemWriter.write(chunk)
    |
    +----> File
    +----> Database
    +----> Message broker
```

Some principles of a writer:

- Receive the entire output of the current chunk and write it in the designed order or rules.
- Throw an exception if the write operation cannot be completed; Spring Batch can roll back, retry, skip, or mark the step as failed according to the configuration.
- Do not decide on its own when the input ends; that belongs to `ItemReader`.
- Should not depend on the source format; the writer should only understand the normalized output model.
- Needs a transaction and idempotency strategy appropriate to the write destination.

## Choosing a Writer by Destination Type

| Output destination | Commonly used writer | Key characteristics |
| --- | --- | --- |
| Text, CSV, or fixed-width file | `FlatFileItemWriter` | Sequential writes, supports header/footer and saves state for restart |
| Relational database via JDBC | `JdbcBatchItemWriter` | Executes batch SQL per chunk and participates in the step's JDBC transaction |
| Database via JPA | `JpaItemWriter` | Writes entities through `EntityManager` and the JPA transaction manager |
| Message broker | Custom writer using a Kafka/JMS client or an integration adapter | Need to define send acknowledgment, transactions, and handling of duplicate sends |
| Multiple destinations | `CompositeItemWriter` or a routing writer | One chunk is passed to multiple writers, or to the appropriate writer by condition |

There is no single writer suitable for every destination. Choose based on the output data type, the transactions the destination supports, restart requirements, and how the system consumes the results.

## Writing Files with FlatFileItemWriter

`FlatFileItemWriter<T>` is a common writer for exporting data to a text file. It can write each item as a line through a `LineAggregator`, and it also supports options such as encoding, header, footer, and saving state for restart.

### CSV writing example

Suppose the processor produces `Order` objects:

```java
public record Order(
        String orderId,
        String customerId,
        BigDecimal amount,
        String status) {
}
```

You can configure the writer with the builder:

```java
@Bean
FlatFileItemWriter<Order> orderFileWriter(
        @Value("${batch.output.orders}") Resource outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .delimited()
            .delimiter(",")
            .names("orderId", "customerId", "amount", "status")
            .headerCallback(writer ->
                    writer.write("orderId,customerId,amount,status"))
            .build();
}
```

`delimited()` sets up the mapping of properties into delimited fields. `names(...)` specifies which properties to export. With real CSV data that may contain commas, quotes, or newline characters, you need to configure appropriate escaping/quoting or provide a dedicated `LineAggregator`; simply joining fields with commas does not by itself guarantee the file complies with all CSV rules.

Illustrative result:

```csv
orderId,customerId,amount,status
O-1001,C-01,125.50,NEW
O-1003,C-03,240.00,NEW
```

### LineAggregator

`LineAggregator<T>` converts an item into a `String` line. For simple formats, the builder can create an aggregator from a list of properties. For complex formats, you can implement your own aggregator to control how dates, decimals, delimiters, padding, or escaping are formatted.

```java
LineAggregator<Order> orderLineAggregator = order -> String.join(
        ",",
        csvEscape(order.orderId()),
        csvEscape(order.customerId()),
        order.amount().toPlainString(),
        csvEscape(order.status()));
```

In the example, `csvEscape` is an application-defined function to quote and escape according to CSV rules. If the data may contain the delimiter or quotes, do not use a simple `String.join` without handling escaping.

### Header and footer

`headerCallback` can write column names or file description information. `footerCallback` can write the total record count or a checksum if the application has computed the necessary value.

```java
new FlatFileItemWriterBuilder<Order>()
        .name("orderFileWriter")
        .resource(outputFile)
        .lineAggregator(orderLineAggregator)
        .headerCallback(writer -> writer.write("orderId,customerId,amount,status"))
        .footerCallback(writer -> writer.write("# end-of-file"))
        .build();
```

The header and footer must follow the format that the consuming system expects. For example, if the file is plain CSV to be loaded into another system, an arbitrary footer line may be mistaken for data; only add a footer when the file contract allows it.

### Restart and file writing

`FlatFileItemWriter` can save its write state into the `ExecutionContext` to support restart. You need to set a stable `.name(...)` and enable state management with an appropriate configuration. On restart, the writer relies on metadata to continue the file already created rather than treating it as a completely new export.

Some notes:

- Use a stable output path for the same logical job when restart is needed.
- Do not delete the old file each time it is opened if the goal is to continue a failed execution.
- If each business run must create a new file, include the output identifier in the path or configure the resource by `JobParameters`.
- Ensure the directory exists and the process has write permission.
- Choose an explicit encoding, usually UTF-8, and agree on newline/format with the receiving system.
- Do not let a consumer read the final file while the job is still partially writing it.

A safe implementation pattern is to write to a temporary file per execution, and only publish or rename it to the official file name after the job completes successfully. The rename needs to be designed for the actual filesystem/object storage; not every storage system supports an atomic rename operation.

## Writing to a Database with JdbcBatchItemWriter

`JdbcBatchItemWriter<T>` is suitable when output needs to be written to a relational database using JDBC. The writer receives a chunk and uses batch updates to reduce the number of round trips to the database.

### Batch insert example

```java
@Bean
JdbcBatchItemWriter<Order> orderDatabaseWriter(DataSource dataSource) {
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

`beanMapped()` maps named parameters in the SQL to the corresponding properties of the object. You can use `columnMapped()` when the item is a `Map`, or provide a custom `ItemSqlParameterSourceProvider` when a different mapping is needed.

With a chunk of 100 items, the writer can send a batch containing the corresponding statements for the 100 outputs. The actual batch size and performance also depend on the JDBC driver, the database, the SQL, and the transaction configuration.

### Update or upsert

If the job synchronizes data that already exists, you can use an `UPDATE` statement, `MERGE`, or upsert syntax depending on the database. Example with PostgreSQL:

```sql
INSERT INTO orders (order_id, customer_id, amount, status)
VALUES (:orderId, :customerId, :amount, :status)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    amount = EXCLUDED.amount,
    status = EXCLUDED.status;
```

An upsert allows the write operation to be re-executed with the same business key without creating additional duplicate records. However, you need to define clearly when data is allowed to be updated, whether it overwrites newer state, and how to handle conflicts according to the business.

### The database writer's transaction

In a chunk-oriented step, the writer usually participates in the transaction managed by the step's `PlatformTransactionManager`. If the writer and `JobRepository` use the same database resource and an appropriate transaction manager, the business data and the checkpoint can commit or roll back together.

If the writer uses a different datasource or transaction manager, there is no default atomic commit guarantee between the business data and the batch metadata. In that case, you need to design idempotency, a unique key, an upsert, or a reconciliation process to handle the situation where one side commits while the other fails.

Do not open a new transaction in the writer without a specific requirement. A `REQUIRES_NEW` transaction can commit the writer's data independently of the chunk; if the chunk rolls back, the already-committed data still exists and may be written again on restart.

### JpaItemWriter

If the application works with entities through JPA, you can use `JpaItemWriter` to write a chunk of entities through `EntityManager`. You need to configure the `EntityManagerFactory` and the JPA transaction manager appropriate for the step. Choosing `persist` or `merge` depends on whether the entity is new or already exists and on the semantics the application expects.

With a large chunk, consider the persistence context and flush/clear to avoid holding too many entities in memory. Measure performance and define clearly the behavior when an entity violates a constraint or errors during flush.

## Writing Messages to Kafka, JMS, or Another Broker

Some jobs do not write directly to a database or file but publish events for other systems to process. For example, after normalizing orders, a batch job publishes `OrderImported` to Kafka or sends a message to a JMS queue.

Spring Batch does not impose a particular message broker. You can implement a custom `ItemWriter` using a client such as `KafkaTemplate`, `JmsTemplate`, or the application's messaging adapter.

### Example of a message-publishing writer

Define a small abstraction to separate the writer from the broker library:

```java
public interface OrderEventPublisher {
    void publish(OrderImported event) throws Exception;
}

public class OrderMessageWriter implements ItemWriter<OrderImported> {

    private final OrderEventPublisher publisher;

    public OrderMessageWriter(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void write(Chunk<? extends OrderImported> chunk) throws Exception {
        for (OrderImported event : chunk) {
            publisher.publish(event);
        }
    }
}
```

The `OrderEventPublisher` adapter will use Kafka, JMS, or another broker according to the application configuration. Separating the adapter makes it possible to test the writer with a fake publisher and swap the broker without changing the chunk step logic.

### Synchronous or asynchronous sending?

Many messaging clients provide an asynchronous send API. If the writer returns right after creating a future without waiting for the result, the step may commit before the broker acknowledges the message. A send error that occurs afterward may not be reflected in the chunk transaction.

When you require the job to continue only after the broker acknowledges, the writer needs to wait for the send result or use an appropriate transaction/acknowledgment mechanism. How to wait on the future and the specific API differ between client versions. Avoid swallowing exceptions or only logging and then treating the chunk as successful.

Synchronous sending can reduce throughput. You can optimize with batch send, an async producer with managed completion, or an appropriate broker transaction configuration, but you need to keep a clear rule: when the writer is allowed to return success and when the chunk is allowed to commit.

### Transactions with a message broker

A database transaction does not automatically roll back a message already sent to the broker. If the writer publishes a message and then another operation in the chunk fails, the message may still exist even though the database rolled back.

Some brokers support their own transactions. Some platforms can coordinate database and messaging transactions through distributed transactions/XA, but that approach has operational costs and limits. Do not assume that just because a producer is configured with a transaction, that transaction is atomic with Spring Batch's JDBC transaction.

Common design options:

- **Transactional outbox:** write the event into an outbox table in the same transaction as the business data; a separate publisher reads the outbox and sends to the broker. You can mark it as sent after the broker acknowledges, and use an event ID to prevent duplicates.
- **Idempotent consumer:** accept that a message may be resent and let the consumer deduplicate by event ID or business key.
- **Broker transaction:** use the broker's transaction when the requirement and configuration really involve only that resource.
- **Distributed transaction:** consider XA when the requirement for atomicity across multiple resources is strong enough to accept the operational complexity.

For many business systems, an outbox combined with an idempotent consumer is easier to recover from than trying to assume the database and broker always commit together.

### Designing messages for safe retry

An event should have a stable identifier, an event type, a timestamp, a business key, and the necessary payload. For example:

```json
{
  "eventId": "order-import:O-1001:v1",
  "eventType": "OrderImported",
  "orderId": "O-1001",
  "businessDate": "2026-11-15",
  "amount": 125.50
}
```

A stable `eventId` helps the consumer recognize repeated messages. Do not create a new UUID for the same event on each retry if the consumer needs to detect duplicates; the ID must be tied to the business event or the appropriate logical processing run.

Partition key, message key, ordering, and delivery guarantee need to be determined per broker. For example, if events of the same order must keep their order, you can use `orderId` as the key in a partitioned log system that supports key-based partitioning.

## Combining Multiple Writers

In some cases a chunk needs to be written to multiple destinations, for example saving orders to a database and also exporting a report file. Spring Batch provides `CompositeItemWriter` to call multiple delegate writers on the same chunk.

```java
@Bean
CompositeItemWriter<Order> compositeOrderWriter(
        JdbcBatchItemWriter<Order> orderDatabaseWriter,
        FlatFileItemWriter<Order> orderFileWriter) throws Exception {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(orderDatabaseWriter, orderFileWriter)
            .build();
}
```

The composite writer calls the delegates in the configured order. If a delegate fails, the exception is returned to the step and the transaction is handled according to the configuration. However, this does not by itself give multiple kinds of resources a shared atomic transaction. The database may roll back while the file has been written, or vice versa, depending on the transaction mechanism and the resource.

When a chunk needs multiple destinations:

- Define the write order and the behavior when a delegate fails.
- Determine whether the writers share a transaction resource.
- Design how to recover the file/message if the database has committed, or vice versa.
- Ensure each delegate is safe when called again after retry/restart.
- Consider an outbox or splitting into separate steps if coordination between systems is needed.

If you need to choose a writer per item, you can use `ClassifierCompositeItemWriter` or implement your own routing writer. When routing, understand that an item is sent only to the chosen delegate; the write counts at each destination should be tracked separately if reporting is needed.

## Writer Transactions, Rollback, and Restart

The writer is where side effects are usually created, so transactions need careful consideration.

### Database writer

If it writes to the same database resource as the step's transaction manager, the write operations usually roll back when the chunk fails. On restart, the items of the uncommitted chunk can be reprocessed and the writer called again.

### File writer

`FlatFileItemWriter` supports saving state and coordinating with the step's transaction to restore the write position through the framework's mechanism. However, a file is not a general-purpose database transaction. An external consumer can still see a file that is being created if it reads that path directly. Use a temporary file and only publish the file after the job completes if the requirements do not allow reading partial output.

### Message writer

A message already received by the broker may not be retracted when the chunk rolls back. A retry can resend the message. Use a stable event ID, an idempotent consumer, or an outbox to handle repeated delivery and restore state.

### Custom stateful writer

If the writer holds internal state such as a line count, checksum, or write position, you may need to implement `ItemStream` to save/restore state through `ExecutionContext`. The stream name must be stable and the state must be sufficient to continue accurately after restart. Do not store a large payload in the execution context; store only a checkpoint or small metadata.

## Common Errors When Writing Output

### No write permission or the directory does not exist

Check the resource path, the process's access permissions, disk space, and creating the directory before running. For jobs running in a container, determine the mounted volume and whether the path exists on the execution node.

### The file is overwritten on restart

Check the writer name, `ExecutionContext`, append/delete configuration, and the resource path. If you want to restart the same logical job, keep the resource and state stable. If you want to create a new file, use a new export identifier deliberately.

### Constraint or duplicate key error in the database

Check the business key, the input data, the insert/update policy, and the behavior when the writer is called again. Use an upsert or a unique key according to business rules if retry/restart may send the same item multiple times.

### The message is sent but the step still fails

The broker may have received the message before a later operation in the chunk failed. Check the broker transaction, the transaction manager, acknowledgment, and the event ID. Design an idempotent consumer to handle the case where the message is resent.

### Asynchronous writer that does not wait for errors

If the writer returns before the send operation completes, the step may commit while the send task is still failing. Manage the future/acknowledgment and only return success when the completion condition the business requires has been met.

### A chunk that is too large or a writer that is too slow

A large chunk can create a large SQL batch, hold a transaction for a long time, or create many messages at once. Measure read/write time, throughput, memory, connection pool, and broker latency; adjust the commit interval and batch size appropriately.

### Swallowing exceptions in the writer

If the writer only logs the error and continues, Spring Batch may mark the chunk as successful even though the data was not fully written. Throw an exception when the success condition is not met and let the step apply the designed transaction/retry/skip policy.

## Testing Writers

A writer needs to be tested according to the characteristics of the write destination.

### Testing a file writer

- Use a temporary directory and small files to verify encoding, header, delimiter, quoting, and line order.
- Test data containing commas, quotes, newlines, and Unicode characters.
- Check the file after the step completes and after a simulated restart.
- Verify that the temporary file is not published when the job fails if the system requires complete output.

### Testing a database writer

- Use a test database to verify batch insert/update is correct.
- Test rollback when a statement in the chunk fails.
- Test unique constraints, upserts, and the ability to safely write repeatedly.
- Verify that the writer's transaction manager and datasource match the step configuration.

### Testing a message writer

- Use a fake publisher or a test broker to verify the key, payload, headers, and message count.
- Simulate send errors before and after the broker acknowledges.
- Verify that the writer waits for acknowledgment as required.
- Resend the same event ID and verify that the consumer can drop duplicates.
- Test the case where the database rolls back after the message has been published.

### Testing a composite writer

Test the delegate order, errors at each delegate, and the result when one destination has been written successfully while another fails. Do not only test the case where every writer succeeds; failure scenarios are what clearly reveal the recovery strategy.

## Principles for Designing Writers in Production

1. Choose the writer by the actual destination and protocol: file, JDBC, JPA, or broker.
2. Write per chunk/batch to take advantage of the destination's performance.
3. Determine the transaction manager and resource the writer uses.
4. Design idempotency for retry, rollback, and restart.
5. For files, use a clear path and clear output-publishing rules.
6. For messages, determine acknowledgment, key, event ID, and delivery semantics.
7. Do not swallow exceptions or report success before the write operation meets its completion condition.
8. Use `ItemStream` when a custom writer needs to save state for restart.
9. Measure throughput, write time, errors, retries, and resource consumption.
10. Test partial-failure scenarios when writing to multiple resources.

## Key Takeaways

`ItemWriter` receives a chunk of output and writes it to the destination. Use `FlatFileItemWriter` for files, `JdbcBatchItemWriter` or `JpaItemWriter` for databases, and a custom writer based on a Kafka/JMS client or an adapter for message brokers. The writer needs to coordinate with the step's transaction, handle exceptions properly, and have a restart/idempotency strategy. A database can roll back within an appropriate transaction; a file needs state management and publishing of complete output; a message may already have been received by the broker even though the chunk rolled back, so you need an event ID, an outbox, or an idempotent consumer. When writing to multiple destinations, you must design clearly the behavior if one destination succeeds while another fails.
