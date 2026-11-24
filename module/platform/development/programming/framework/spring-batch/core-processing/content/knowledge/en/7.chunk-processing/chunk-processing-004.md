# Reading, processing, and writing in a transaction

In Spring Batch, a **chunk-oriented Step** reads data, processes each item, and writes the results in groups. Each chunk is typically executed in **its own transaction**: the transaction begins when the chunk is processed, covers the read/process/write operations coordinated by the Step, and commits when the chunk completes successfully. If an error occurs that forces the chunk to roll back, the changes belonging to that transaction are undone and the chunk can be retried or reprocessed according to the configuration.

The key point is that a transaction usually surrounds **one chunk**, not the entire Step. With a chunk size of 100, a Step processing 10,000 records can produce roughly 100 transactions. Chunks that have already committed are retained when a later chunk fails.

This organization makes it possible to process large datasets without holding all the data in memory or opening a very long transaction. To understand exactly what gets rolled back, you need to distinguish database transactions from operations such as reading files, calling APIs, or writing to external resources.

## 1. The three components in chunk processing

Chunk-oriented processing has three main components:

| Component | Responsibility |
|---|---|
| **ItemReader** | Reads items one at a time from a data source and returns the next item |
| **ItemProcessor** | Validates, filters, or transforms the item |
| **ItemWriter** | Writes the set of processed items in the chunk |

Example of importing customer data:

~~~text
Data source
     |
     v
  ItemReader
  reads each customer
     |
     v
  ItemProcessor
  validates and transforms
     |
     v
  The chunk's list of items
     |
     v
  ItemWriter
  writes to the database
     |
     v
  COMMIT transaction
~~~

A basic processing cycle:

1. The reader reads items one at a time.
2. The processor receives an item and produces the corresponding result.
3. The valid results are collected into a chunk.
4. The writer receives the chunk and writes the data.
5. When the operations in the chunk complete, the transaction is committed.
6. The Step begins the next chunk until the reader reports no more data.

The reader usually returns **null** when there are no more items. The processor can return **null** to exclude an item from the results to be written. Therefore, the number of items read can differ from the number of items the writer receives.

## 2. One transaction per chunk

The chunk size, also called the commit interval, defines the maximum number of items gathered in a chunk before commit.

For example:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> customerReader,
        ItemProcessor<RawCustomer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

**chunk(100, transactionManager)** configures the chunk size as 100 and the transaction manager used to manage the Step's transactions.

Suppose the source has 250 items:

| Chunk | Items read | Commit time |
|---|---:|---|
| Chunk 1 | 1–100 | After the writer writes successfully |
| Chunk 2 | 101–200 | After the writer writes successfully |
| Chunk 3 | 201–250 | The last chunk, committed after a successful write |

The last chunk can be smaller than the chunk size because the data source has run out.

With 250 items, the Step does not open a single transaction for all 250 items. It creates three chunk transactions. If chunk 3 fails, the first two committed chunks are retained, while the changes in chunk 3's transaction can be rolled back.

### The phases within a transaction

At a conceptual level, a chunk typically proceeds as follows:

~~~text
Begin transaction
        |
        v
Reader reads items
        |
        v
Processor processes each item
        |
        v
Writer writes the chunk
        |
        v
Update stream state and metadata
        |
        v
COMMIT
~~~

If there is an exception that requires rollback:

~~~text
Begin transaction
        |
        v
Reader -> Processor -> Writer
                         |
                         v
                       ERROR
                         |
                         v
                      ROLLBACK
                         |
                         v
           Retry / Skip / End the Step
~~~

Spring Batch coordinates the chunk loop and the transaction. When the writer completes, the framework updates the state of the **ItemStream** components and the execution metadata before the transaction ends. With an appropriate transaction configuration, the checkpoint state and the business data can be committed consistently.

## 3. How does the reader read items within a transaction?

The reader is called to fetch each item for the current chunk. However, you need to distinguish **the `read()` call happening within the scope of chunk processing** from whether the data source supports rollback.

If the reader reads from a database through the same transaction manager, the read operation can participate in the database transaction depending on the configuration and the type of reader. If the reader reads a CSV file, advancing the read position in the file is not a database operation that can be rolled back.

For example:

- **FlatFileItemReader** reads a line from a file.
- **JdbcCursorItemReader** reads results from a database cursor.
- **JdbcPagingItemReader** fetches data page by page.
- A reader using JMS can receive messages from a queue that supports transactions.

For sources that cannot roll back, such as files, Spring Batch can buffer the items already read to avoid re-reading the physical source in some rollback scenarios within the same run. For a reader based on a transactional queue, rollback can return the message to the queue; how the reader is handled on rollback is therefore different from a file reader.

Do not assume file pointers, database cursors, and message queues behave the same when a transaction rolls back. Consult the documentation and configuration of the specific reader.

### Stateful readers and checkpoints

Many readers support **ItemStream**, which allows saving the read state in the **ExecutionContext**:

- **open(ExecutionContext)**: restore or initialize the read position.
- **update(ExecutionContext)**: save the state at a checkpoint.
- **close()**: release resources.

With a stateful reader, the checkpoint is usually updated when the chunk completes. When the Job restarts, the reader can continue from the state saved at the most recent commit.

If the reader is custom-written, does not save state, or has the ItemStream contract hidden by a wrapper, Spring Batch cannot infer a safe read position on its own. In that case, the reader may start over from the beginning or need its own recovery mechanism.

## 4. The processor handles items in a chunk

**ItemProcessor<I, O>** receives an input item and returns an output item. A processor typically performs:

- Validating the input data.
- Normalizing strings, dates, or identifiers.
- Mapping a DTO to an entity.
- Applying business rules.
- Dropping items that do not need to be written.

For example:

~~~java
@Bean
public ItemProcessor<RawCustomer, Customer> customerProcessor() {
    return raw -> {
        if (raw.email() == null || raw.email().isBlank()) {
            return null;
        }

        return new Customer(
                raw.id(),
                raw.name().trim(),
                raw.email().trim().toLowerCase()
        );
    };
}
~~~

If the processor returns a **Customer** object, that item is passed to the writer. If the processor returns **null**, the item is filtered and not passed to the writer.

For example, a chunk reads 100 items, of which 5 have no email:

~~~text
Reader:      100 items
                 |
                 v
Processor:   95 valid results
              5 items returned null
                 |
                 v
Writer:       95 items
                 |
                 v
Commit transaction
~~~

The processor should usually focus on data transformation and validation logic. Avoid sending emails, calling APIs with side effects, or performing an operation that cannot be rolled back inside the processor. If the chunk is retried or rolled back, the processor may be called again for the same item.

A processor can read data from a database or call a service, but those operations are rolled back only if they participate in the same appropriate transaction. A plain HTTP call or file write is not automatically undone along with the Step's database transaction.

## 5. The writer writes the whole chunk

The writer receives the chunk's set of output items and writes them. With Spring Batch 5, the **ItemWriter** API receives a **Chunk**:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

An example using a JDBC batch writer:

~~~java
@Bean
public JdbcBatchItemWriter<Customer> customerWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO customer (id, name, email)
                VALUES (:id, :name, :email)
                """)
            .beanMapped()
            .build();
}
~~~

The writer receives a chunk and writes the items in that chunk. With a JDBC writer that uses the same DataSource and transaction manager as the Step, the write statements participate in the chunk transaction. If an error causes the transaction to roll back, the database changes belonging to that transaction are undone.

A writer can also write to a file, call a service, or send data to another system. But these kinds of resources do not necessarily participate in the database transaction. You need to clearly understand each writer's transaction boundary before relying on rollback to protect data.

### The writer writes part of the data and then hits an error

Suppose the writer performs many insert statements in a chunk:

~~~text
Chunk containing 100 customers
       |
       v
INSERT customer 1  -> success
INSERT customer 2  -> success
...
INSERT customer 60 -> error
       |
       v
Exception is thrown
       |
       v
ROLLBACK transaction
       |
       v
The inserts in the transaction are undone
~~~

When all write statements participate in the same database transaction, the inserts performed before the error are also rolled back. If the writer uses a different transaction, **REQUIRES_NEW**, a different database, or an external API, the result may differ. Do not assume that every operation the writer performs is rolled back automatically.

## 6. The transaction manager determines the rollback scope

When building the Step, the transaction manager is passed into the builder:

~~~java
new StepBuilder("importCustomersStep", jobRepository)
        .<RawCustomer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
~~~

The transaction manager determines the transaction the Step uses. For a JDBC application, you typically use the transaction manager tied to the DataSource that holds the business data.

For business data and checkpoint metadata to be committed consistently, consider:

- Whether the writer and the JobRepository use the same database.
- Whether they participate in the same transaction manager.
- Whether a different transaction propagation such as **REQUIRES_NEW** is used.
- Whether there are multiple DataSources or external resources.

If the business data and the metadata are in the same managed transaction, a single commit can confirm both. If they are in independent transactions or resources, a situation can occur where the business data has been written but the checkpoint has not been saved, or vice versa. In that case you need to design idempotency, reconciliation, or an appropriate transaction coordination mechanism.

**A transaction manager does not automatically turn every resource Java calls into a transactional resource.** It only manages the resources that participate in the corresponding transaction.

## 7. What happens when a chunk succeeds?

Suppose a chunk has 100 items and all are valid:

1. The Step begins a transaction.
2. The reader reads 100 items.
3. The processor processes each item.
4. The writer writes the results produced.
5. The framework updates the state of the streams and the Step metadata.
6. The transaction commits.
7. The Step moves on to the next chunk.

After commit, the data written in the transaction is confirmed. The corresponding checkpoint can be used on restart if the Job fails in a later chunk.

If all items are filtered by the processor, no corresponding items are passed to the writer. The chunk still needs to be processed, and the read state/checkpoint is updated according to the Step's mechanism.

Do not look only at the number of items written to conclude how much data a chunk has processed. Cross-check the read count, filter count, skip count, write count, and commit count.

## 8. What happens when a chunk rolls back?

Suppose the chunk size is 100 and the Step has processed:

~~~text
Chunk 1: 1   - 100  -> COMMIT
Chunk 2: 101 - 200  -> COMMIT
Chunk 3: 201 - 300  -> Writer hits an error
                         |
                         v
                       ROLLBACK
~~~

Result:

- The data committed in chunks 1 and 2 is retained.
- The changes in chunk 3's transaction are rolled back if they belong to the same transaction.
- The Step can end as FAILED if the exception is not handled by retry or skip.
- When the JobInstance is restarted, the Step can continue from the most recent saved checkpoint, usually after chunk 2.

Within the same run, the behavior after a rollback also depends on the retry/skip configuration and the type of reader. Spring Batch can buffer the items already read so they can be reprocessed without re-reading the physical source. With a transactional data source such as a message queue, a rollback can return items to the source so they can be received again.

For a source with no checkpoint or one that does not support recovery, the application may have to read again from the beginning. Therefore, restartability also depends on how the reader saves its state.

## 9. Retry and skip in a chunk transaction

Not every exception forces the whole Job to end immediately. Spring Batch supports configuring retry and skip to handle transient errors or invalid records according to business policy.

### Retrying transient errors

Retry suits errors that are likely to disappear on retry, such as deadlocks or transient resource access errors.

An illustrative configuration example:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> customerReader,
        ItemProcessor<RawCustomer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

Here, errors in the **TransientDataAccessException** group can be retried up to the configured limit. How the framework restarts the transaction and calls the component again depends on where the exception occurs, the retry policy, and the type of reader/writer.

Do not retry every exception. Invalid data errors or configuration errors usually do not go away on retry.

### Skipping invalid items

Skip suits cases where the business allows ignoring some failing items and continuing to process the remaining ones.

~~~java
.faultTolerant()
.skip(InvalidCustomerException.class)
.skipLimit(100)
.build();
~~~

In the example, the Step allows skipping at most 100 items of type **InvalidCustomerException**. When the limit is exceeded, the Step fails.

The skip count is recorded in the StepExecution. There should be a listener or a recording mechanism for skipped records so they can be investigated and reprocessed later.

Retry and skip do not change the meaning of a chunk transaction: changes are only confirmed when the corresponding transaction commits. Test the error policy with the real reader and writer, especially when the writer has side effects outside the database.

## 10. Retry, rollback, and idempotency

A chunk can be processed again after a rollback or retry. Therefore, the operations in the reader, processor, and writer need to be designed to tolerate being called again.

An unsafe example:

~~~java
public Customer process(RawCustomer raw) {
    notificationService.sendWelcomeEmail(raw.email());
    return convert(raw);
}
~~~

If the writer later hits an error and the chunk is retried, the email may be sent again. A database rollback cannot recall an email that has been sent.

A safer design is to:

- Keep the processor focused on data transformation.
- Write the business data and the request to send a notification in the same transaction if possible, for example through an outbox table.
- Have a separate worker read the outbox and send the notification.
- Use a unique identifier so the recipient can prevent duplicate processing.

For an external API, you can use an idempotency key tied to the business code. If the same request is sent again, the target system recognizes it as the same operation and does not create additional side effects.

**A rollback only undoes the changes managed within that transaction.** It does not automatically undo an HTTP request, an email, a file that was written, or changes in another database.

## 11. Transactions and chunk listeners

Spring Batch provides listeners to observe each phase of processing:

- **ItemReadListener**: monitors item reads and read errors.
- **ItemProcessListener**: monitors item processing, results, or errors.
- **ItemWriteListener**: monitors chunk writes and write errors.
- **ChunkListener**: monitors the chunk lifecycle.

For example:

~~~java
@Component
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        log.info("Starting a chunk");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.info("Chunk completed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.error("Chunk failed");
    }
}
~~~

Registering the listener:

~~~java
new StepBuilder("importCustomersStep", jobRepository)
        .<RawCustomer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .listener(importChunkListener)
        .build();
~~~

Listeners are useful for logging, metrics, and monitoring. However, you need to distinguish a listener callback from a transaction commit. For example, a callback after a chunk does not mean that every external operation has been durably committed. Choose the right callback and an event-storage mechanism if you need to guarantee a notification after commit.

Do not put important side effects in a listener without considering retry, rollback, and the possibility that the listener is called again.

## 12. Reading and writing across multiple resources

A Step can read from one source and write to another, for example:

- Read CSV and write to a database.
- Read a database and write to a file.
- Read a REST API and write to a database.
- Read a message queue and write to a business system.

In these cases, the transaction does not necessarily cover both the read source and the write destination.

An example of reading CSV and writing to a database:

~~~text
CSV file
   |
   v
ItemReader
   |
   v
ItemProcessor
   |
   v
JdbcBatchItemWriter
   |
   v
Database transaction
   |
   v
COMMIT / ROLLBACK
~~~

A database writer can participate in the transaction. But the read position in the file is not directly managed by the database transaction. Spring Batch needs to save the reader's checkpoint to restore progress.

An example of reading a message queue and writing to a database:

~~~text
Message Queue
      |
      v
ItemReader
      |
      v
Processor
      |
      v
Database Writer
      |
      v
Transaction resources
~~~

If the message queue and the database participate in one supported transaction, they can coordinate commit/rollback according to the configuration. If not, you need to consider the possibility that a message is received again while the database has already written, or the database rolls back but the message has already been acknowledged. Idempotency and reconciliation mechanisms are very important in this case.

## 13. Choosing an appropriate chunk size

Chunk size affects:

- The number of times transactions begin and commit.
- The amount of data held in memory.
- How long each transaction stays open.
- The amount of work that needs to be retried or reprocessed on error.
- The load on the database and the target system.

| Chunk size | Common characteristics |
|---|---|
| Small | Shorter transactions, frequent commits, fewer items in each rollback |
| Large | Fewer transactions, can increase batch write performance, but holds more items and has longer transactions |

There is no chunk size that suits every application. Start with a moderate size, measure processing time, commit time, memory usage, and database load. Then adjust based on real data.

If the writer can write in batches, an appropriate chunk size can help take effective advantage of batch insert/update. But increasing the chunk size too much can make transactions run long, hold locks for a long time, and increase the rollback cost when an error occurs.

## 14. Monitoring transactions and processing results

**StepExecution** provides metrics that help observe progress:

| Attribute | Meaning |
|---|---|
| **readCount** | Number of items read |
| **writeCount** | Number of items written |
| **filterCount** | Number of items dropped by the processor |
| **readSkipCount** | Number of items skipped during read |
| **processSkipCount** | Number of items skipped during processing |
| **writeSkipCount** | Number of items skipped during write |
| **commitCount** | Number of commits |
| **rollbackCount** | Number of rollbacks |

An example of a Step with these results:

~~~text
readCount        = 1000
writeCount       = 940
filterCount      = 40
processSkipCount = 10
writeSkipCount   = 10
commitCount      = 10
rollbackCount    = 1
~~~

These numbers help detect discrepancies between data read and data written. However, they do not replace detailed logs or per-record error reports.

When a chunk rolls back and then retries successfully, the read, processing, or rollback counts can reflect the attempts depending on the component and how the framework records them. Do not interpret a single counter as complete evidence of how many times an item has been processed.

## 15. Common misconceptions

### Thinking the whole Step runs in a single transaction

With a chunk-oriented Step, each chunk usually has its own transaction. Chunks that have committed still exist if a later chunk fails.

### Thinking file reads can roll back like a database

The read position in a file does not automatically go back when a database transaction rolls back. The reader needs to support buffering or checkpoints to restore the right state.

### Thinking a processor returning null is an error

Returning null is a valid way to filter an item. That item is not passed to the writer.

### Thinking a successful writer write means the data has been committed

The writer completes before the transaction commits. An error that occurs afterward within the same transaction can still cause the data to be rolled back.

### Thinking every operation in Java is rolled back

The transaction manager only rolls back resources that participate in the transaction. Emails, HTTP requests, or files written outside are not automatically undone.

### Thinking chunk size equals the number of records the writer will definitely write

The processor can filter items and the skip policy can skip failing items. The number read and the number written can therefore differ.

### Thinking retry always re-reads from the source

Spring Batch can buffer the items already read to reprocess them after a rollback. A transactional reader such as a message queue behaves differently. Check the actual configuration and reader type.

## 16. A process for designing a safe chunk transaction

When building a Step that reads, processes, and writes data, clearly define the source, destination, and transaction boundaries.

1. Choose a reader that fits the data source and its ability to save state.
2. Write a processor focused on validating and transforming items.
3. Choose a writer that can write in batches and participates in the Step's transaction if it needs to roll back together with the business data.
4. Configure the chunk size based on performance measurements and resources.
5. Choose the transaction manager that matches the DataSource or the resource that needs protection.
6. Decide which exception types need retry, which are skipped, and the corresponding limits.
7. Save the reader's checkpoint to support restart after errors.
8. Design the operations outside the transaction to be idempotent.
9. Monitor the read/write/filter/skip counts, commits, and rollbacks.
10. Test the scenario of an error occurring while the writer is writing to understand exactly which part is rolled back.

When reading a chunk Step configuration, trace **chunk(size, transactionManager)**, **reader(...)**, **processor(...)**, and **writer(...)**. Then determine which resource the writer uses, whether that resource participates in the transaction, and how the reader saves its checkpoint. That way you will know clearly which data is committed together, which data can be rolled back, and what will happen when a chunk has to run again.
