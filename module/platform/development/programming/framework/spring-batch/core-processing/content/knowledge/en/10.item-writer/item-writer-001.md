# ItemWriter Writes a Chunk of Items

In Spring Batch, ItemWriter is the component that receives data that has been read and processed and writes it to a destination. In a chunk-oriented Step, the framework gathers multiple items into a chunk and then calls the writer to write the whole group. Therefore, a single call to write() usually represents one chunk-based write unit, not a separate write for each individual item.

This organization lets Spring Batch coordinate reading, processing, writing, and transaction commits for each portion of data. A writer can write to a database, a file, a message broker, or another system, as long as it implements the contract correctly and handles transactions, errors, and rerunnability appropriately.

## 1. The ItemWriter Contract

In Spring Batch 5, the ItemWriter<T> interface has the following method:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

The Chunk parameter contains the items that the framework passes to the writer for the current write. The writer can iterate over the items in the chunk and perform the write operation appropriate to the data destination.

A few points to remember:

- A writer receives a chunk of multiple items, which may be fewer than the commit interval.
- A writer is usually called after the reader has read and the processor has processed the items of the chunk.
- A writer does not decide on its own when a chunk ends.
- A writer does not commit the chunk's transaction on its own.
- If writing fails, the writer can throw an exception so the framework handles rollback, retry, or skip according to the Step configuration.

In Spring Batch 4.x, the old ItemWriter signature accepted List<? extends T>. When moving to Spring Batch 5, the API changed to Chunk<? extends T>. Use the correct signature for the version you are running, and do not mix examples from the two API generations.

## 2. The Chunk Is Created Before the Writer Is Called

Suppose the Step has a commit interval of 3. The reader reads item by item, the processor may transform or filter items, and then the writer receives the remaining results.

~~~text
ItemReader
  read A
  read B
  read C
      |
      v
ItemProcessor
  A -> A'
  B -> null (filter)
  C -> C'
      |
      v
Output chunk
  [A', C']
      |
      v
ItemWriter.write(chunk)
      |
      v
Commit transaction
~~~

In this example, the reader provided three items, but the processor filtered out item B by returning null. The writer receives only the two remaining items, A' and C'.

Therefore, the number of items the writer receives is not necessarily equal to the commit interval or to the number of items the reader read. The last chunk of the data source may also be smaller than the commit interval, because the reader returns null when the data runs out.

Example with eight items and a commit interval of three:

~~~text
Chunk 1: [A, B, C] -> write -> commit
Chunk 2: [D, E, F] -> write -> commit
Chunk 3: [G, H]    -> write -> commit
~~~

The writer does not need to count the number of items read since the start of the Job. The framework manages the read loop and chunk gathering based on the Step configuration.

## 3. Declaring a Chunk-Oriented Step

The following example uses the Spring Batch 5 Java API:

~~~java
@Bean
Step exportCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("exportCustomersStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

The chunk(100, transactionManager) configuration tells the framework to gather up to 100 input items for a chunk in the normal processing flow. When the chunk is processed, the writer receives the processor's output items.

The transaction manager is passed to the StepBuilder to manage the chunk's transaction. If the writer writes to a database using the same transaction resource, the write operation can participate in that transaction.

Avoid creating a new transaction and committing separately inside the writer for each item if the goal is to keep the transaction boundary at the chunk level. Doing so can leave some already-written items impossible to roll back when another item in the same chunk fails.

## 4. Writing a Custom ItemWriter

When no suitable built-in writer exists, you can implement ItemWriter<T>.

Example of writing audit information for the Customers in a chunk:

~~~java
public class CustomerAuditWriter implements ItemWriter<Customer> {

    private final CustomerAuditService auditService;

    public CustomerAuditWriter(CustomerAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        for (Customer customer : chunk) {
            auditService.record(customer);
        }
    }
}
~~~

On each write(), the writer iterates over the items in the chunk and passes each item to the audit service. The framework is responsible for calling write() with the appropriate chunk.

This is a simple example. If auditService writes to the same database and the same transaction resource, the changes can be rolled back together with the chunk. If the service calls an API or writes to another system, the Step's database transaction does not automatically undo those effects.

A writer should focus on writing the items it is given. Avoid having a writer read additional data from the source, launch another Step, or control the Job lifecycle on its own. Those responsibilities belong to other components of the application or to the Job flow.

## 5. Writing a Chunk to a Database with JdbcBatchItemWriter

Spring Batch provides JdbcBatchItemWriter to perform batch updates/inserts into a database. The writer receives a chunk and executes the SQL statements for the items in the group.

Example:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerDatabaseWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                insert into customer (id, name, email)
                values (:id, :name, :email)
                """)
            .beanMapped()
            .build();
}
~~~

With bean mapping, placeholders such as id, name, and email are mapped from the corresponding properties of Customer. JdbcBatchItemWriter performs the JDBC operations for the items in the chunk.

In a real application, you need to determine clearly:

- Whether the target table has an appropriate primary key or unique constraint.
- Whether to insert, update, or upsert when a record already exists.
- Whether batch updates are suitable for the driver and database in use.
- Whether the Step's transaction manager manages the same DataSource that the writer uses.
- Whether the number of items per chunk is appropriate for parameter limits, memory, and database performance.

If the writer and the JobRepository use two different databases or transaction managers, do not assume by default that the metadata and the business data are committed atomically together. Design restart and idempotency for the case where the two places have out-of-sync state.

### Insert or update?

The writer needs to reflect the business rules correctly. Some common options:

| Write approach | Behavior |
|---|---|
| INSERT | Creates a new record; may fail if the key already exists |
| UPDATE | Updates an existing record; may update no rows |
| UPSERT | Insert or update depending on the key and database syntax |
| MERGE | Combines insert/update based on a condition, depending on the database |
| Stored procedure | Moves the write logic into a database-side procedure |

If the Job can be restarted or launched multiple times, use a stable business key and write rules that are safe on rerun. Relying only on the fact that the previous chunk has been committed is not enough to guarantee there are no duplicates in every situation, especially when the source and destination are not in the same transaction.

## 6. Writing a Chunk to a File with FlatFileItemWriter

FlatFileItemWriter is a built-in writer for writing items as lines of text. You can configure a LineAggregator to convert each object into a line.

Simple example:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Customer> customerFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Customer>()
            .name("customerFileWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(customer ->
                    customer.getId() + "," + customer.getName())
            .saveState(true)
            .build();
}
~~~

When the Step runs, FlatFileItemWriter receives a chunk, maps each Customer to a line, and writes it to the file. saveState(true) allows the writer to save the state needed for restart, such as the write position in the file.

The lineAggregator example above only illustrates how to join fields. If the data contains commas, double quotes, or line breaks, use an appropriate formatter/CSV library to escape the format correctly. Do not naively concatenate CSV for real data that may contain special characters.

### Safely writing intermediate files

If the file is an important business output, you need to decide how to handle the file when the Step fails or restarts:

- Use a file name tied to the JobInstance or a business key.
- Do not let two JobInstances unintentionally overwrite the same output file.
- Keep the intermediate file long enough for a restart to continue.
- Publish the complete file only after the Step has written successfully.
- You can write to a temporary file and then rename it on completion, if the filesystem and deployment environment support an appropriate rename operation.

Writing a file does not implicitly participate in the database transaction. You need to distinguish the transactional buffering mechanism that a specific writer supports from the atomicity of the filesystem and the database as a whole.

## 7. The Writer and the Chunk's Transaction Boundary

In a chunk-oriented Step, the writer is called during chunk processing. After the writer completes and the necessary stream states are updated, the framework commits the chunk's transaction.

General flow:

~~~text
Begin chunk transaction
       |
       v
Read items
       |
       v
Process items
       |
       v
ItemWriter.write(chunk)
       |
       v
Update checkpoint / stream state
       |
       v
Commit transaction
~~~

If the writer throws an exception and that error causes the transaction to roll back, the changes on resources participating in the current transaction are undone. Chunks that were committed earlier are kept.

For example, with a chunk size of 100 and a writer that writes to a database:

~~~text
Chunk 1: insert 100 customers -> commit
Chunk 2: insert 100 customers -> commit
Chunk 3: insert customer hits an error -> rollback chunk 3
~~~

After the rollback, the data committed in chunks 1 and 2 still exists. On restart, the Step can continue from the nearest checkpoint if the reader and writer support restart.

A transaction only protects resources that participate in the same transaction. If the writer writes to a database and then sends an HTTP request to another service, a database rollback cannot retract an HTTP request that has already succeeded.

For effects outside the transaction, consider:

- An idempotency key at the receiving system.
- A transactional outbox to record the intent to publish a message within the database transaction.
- A business status table to detect operations that have already completed.
- A compensation mechanism when external actions cannot be rolled back.

## 8. The Writer May Receive a Retried Chunk or Handle Skips

In a Step with fault tolerance configured, a write error can cause the chunk to roll back and be retried or handled according to the skip policy.

This means the writer can be called again with the same or nearly the same data as the previous call. The writer must be designed to withstand that situation.

For example, if the writer sends an email for each item and a later email fails, a retry may resend the emails that were already sent successfully. The database transaction cannot recall emails that have already gone out.

To avoid duplicate effects:

- Prefer writers that write to a database with a unique key or upsert when appropriate.
- Use an idempotency key for the API or message.
- Store the send status by business key if needed.
- Distinguish transient errors that can be retried from business errors that need handling.
- Record skipped items so they can be reconciled after the Job.

A skip during write may require the framework to roll back and then identify the failing item using the Step's fault-tolerant mechanism. Do not catch every exception in the writer and silently ignore it, because the framework will not know an error occurred, and the counters/skip policy will not reflect it correctly.

## 9. ItemWriter and ItemStreamWriter

A writer that only needs to receive a chunk can implement ItemWriter<T>. If the writer needs to manage resources or save state for restart, it can implement ItemStreamWriter<T>.

ItemStreamWriter combines the write contract of ItemWriter with the lifecycle of ItemStream:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

The meaning of the callbacks:

- **open:** opens resources and restores state when the Step starts or restarts.
- **update:** writes the current state into the ExecutionContext before the checkpoint is saved.
- **close:** closes resources and releases them when the Step ends.

FlatFileItemWriter is an example of a writer that manages state/resources. When you write your own writer that holds a file handle, cursor, or write state, you need to implement the appropriate lifecycle and make sure the delegate ItemStream is registered correctly if the writer is wrapped in a composite.

Do not store large business objects or credentials in the writer's ExecutionContext. Store only the information needed to restore the write position or state.

## 10. Stateful Writers and Restart

A restartable writer must be able to determine the most recent committed write position or state. For example, FlatFileItemWriter can store the write position so that on restart it continues writing at the right place according to its own mechanism.

For a custom writer, you need to design the state yourself:

~~~java
public class CountingWriter<T> implements ItemStreamWriter<T> {

    private static final String WRITTEN_COUNT = "countingWriter.writtenCount";

    private long writtenCount;

    @Override
    public void open(ExecutionContext context) {
        writtenCount = context.containsKey(WRITTEN_COUNT)
                ? context.getLong(WRITTEN_COUNT)
                : 0L;
    }

    @Override
    public void write(Chunk<? extends T> chunk) {
        for (T item : chunk) {
            // Perform the actual write operation here.
            writtenCount++;
        }
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(WRITTEN_COUNT, writtenCount);
    }

    @Override
    public void close() {
        // Close resources if the writer has opened any.
    }
}
~~~

This is only an example to illustrate the lifecycle. An in-memory counter does not restore the write effects on the target system on its own. In a real writer, the state must match the committed data; if the writer writes to a database, it is usually better to let the transaction and business key ensure consistency rather than relying on a self-made counter.

If the writer writes to a file or an external system, you need to define clearly how to roll back or continue after an error. You cannot simply store a count and assume that every previous item has definitely been durably written.

## 11. Composite Writers and Writing to Multiple Destinations

Some processes need to write the same chunk to multiple places, for example a database and an audit file. You can use CompositeItemWriter to coordinate multiple delegate writers.

Example:

~~~java
@Bean
CompositeItemWriter<Customer> customerCompositeWriter(
        JdbcBatchItemWriter<Customer> customerDatabaseWriter,
        FlatFileItemWriter<Customer> customerFileWriter) {

    return new CompositeItemWriterBuilder<Customer>()
            .delegates(customerDatabaseWriter, customerFileWriter)
            .build();
}
~~~

When the Step calls the composite writer, the delegates receive the chunk in the configured order. Make sure every delegate that needs the ItemStream lifecycle is registered and its callbacks are called correctly. With nested composites/delegates, check the stream registration mechanism of the Spring Batch version you are using.

Writing to multiple destinations does not mean an automatic distributed transaction. If the database commits but the file cannot be completed, or vice versa, the two destinations can end up out of sync. Consider:

- Use the same transaction manager if the delegates participate in one suitable transaction resource.
- Write the primary data to the database, then generate the file from the committed data in a separate Step.
- Use an outbox or staging to produce secondary data after the commit.
- Have a mechanism to detect and fix out-of-sync state on restart.

If the destinations cannot commit atomically together, the recovery design needs to be stated clearly in the process.

## 12. Chunk Size and Write Performance

The commit interval affects the number of items the writer receives each time. A chunk that is too small can increase the number of writer calls and commits; a chunk that is too large can increase memory, lock hold time, and the cost of reprocessing after a rollback.

| Small chunk | Large chunk |
|---|---|
| More write() calls | Fewer write() calls |
| Transactions are usually shorter | Transactions can last longer |
| Fewer items to reprocess on rollback | More items may be reprocessed |
| Higher commit cost | Commit cost per item may be lower |
| Usually uses less memory | May need more memory |

Do not choose the chunk size based only on write speed. Measure with real data sizes, the database driver, indexes, network, processor time, and the system's transaction limits.

If the writer calls an external API, a large chunk size can also increase the number of requests or the payload per run. Consider the target API's batch limits and split within the contract the writer supports, but do not arbitrarily break the Step's transaction semantics.

## 13. Common Mistakes When Implementing ItemWriter

**Assuming the writer receives one item at a time.** In a chunk-oriented Step, write() receives the whole Chunk. Iterate over the items in the chunk or use a built-in writer.

**Committing inside the writer.** Manual commits can break the chunk's rollback. Let the Step's transaction manager manage the transaction.

**Catching an exception and ignoring it.** The framework cannot apply the retry/skip policy correctly if the writer hides errors. Throw an appropriate exception or configure skip explicitly.

**Not idempotent.** On retry or restart, the writer may write duplicates. Use a unique constraint, upsert, or idempotency key.

**Holding the chunk after write finishes.** Do not store references to the Chunk or mutable items for asynchronous processing after the method ends, unless the data has been copied and transaction/ownership is managed clearly.

**Writing to multiple destinations without a recovery plan.** Systems outside the transaction can fall out of sync after an error. You need an outbox, staging, or a compensation mechanism.

**Not managing resources.** Files or connections must be closed according to the proper lifecycle. Use ItemStreamWriter when the writer has state or resources that need managing.

## 14. Testing an ItemWriter

You can test a writer in isolation by creating a Chunk with sample items and verifying that the writer performs the write operation as expected.

Example with a custom writer:

~~~java
@Test
void writesEveryItemInChunk() throws Exception {
    Customer first = new Customer(1L, "An", "an@example.test");
    Customer second = new Customer(2L, "Binh", "binh@example.test");

    Chunk<Customer> chunk = new Chunk<>(List.of(first, second));

    CustomerAuditService auditService = mock(CustomerAuditService.class);
    CustomerAuditWriter writer = new CustomerAuditWriter(auditService);

    writer.write(chunk);

    verify(auditService).record(first);
    verify(auditService).record(second);
}
~~~

Beyond unit tests, integration tests of the Step should verify:

- The writer receives the correct output items from the processor.
- A final chunk smaller than the commit interval is still written.
- When the writer fails, the current transaction rolls back according to the configuration.
- Retry or skip works correctly with the chosen exception types.
- Restart does not create unintended duplicate data.
- The writer closes resources and restores state correctly on restart.
- The composite writer handles an error in one delegate according to the designed recovery policy.

For a JDBC writer, you should verify the results in the database using transactions and realistic test data. For a file writer, check the file content, encoding, delimiter, escaping, and behavior on restart.

## 15. Choosing a Writer Suited to the Data Destination

Before implementing a writer, determine:

1. Is the write destination a database, a file, a message broker, an API, or multiple systems?
2. How many items can each write receive?
3. Do the write operations participate in the Step's transaction?
4. If one item in the chunk fails, do you need to roll back, retry, or skip?
5. Does the writer need to save state for restart?
6. Can duplicate writes occur on retry or restart?
7. If writing to multiple destinations, how do you recover when only one destination succeeds?
8. Do you need to limit the payload, batch size, or call rate to the target system?

For a database, prefer a suitable JDBC/JPA writer and the correct transaction manager. For a file, use FlatFileItemWriter or a specialized writer with a clear lifecycle. For an API or message broker, design idempotency and a safe replay mechanism. For multiple destinations, evaluate atomicity and the recovery plan before going into operation.

The core principle is that ItemWriter receives a chunk created by the framework and writes the items in that chunk. Spring Batch manages the chunk lifecycle, transactions, checkpoints, and Step state. When the writer keeps to its responsibility of writing, throws errors transparently, and is designed for retry/restart, the batch process can write data efficiently while still keeping consistency under control.

