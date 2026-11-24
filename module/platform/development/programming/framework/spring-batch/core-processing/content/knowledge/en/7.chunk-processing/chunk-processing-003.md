# Commit interval and chunk size

In Spring Batch, chunk-oriented processing divides data into small groups of items to read, process, and write one round at a time. The **commit interval** defines the number of items processed in a chunk before the chunk's transaction is committed. This value is usually called the **chunk size**.

For example, with the configuration `chunk(500, transactionManager)`, the Step processes up to 500 items in a chunk, then writes the results and commits the transaction. For a Job processing 100,000 items, if all items are read in full and no errors change the processing flow, you can picture roughly 200 chunks being committed. The last chunk may be smaller if the data is not evenly divisible by 500.

Choosing the chunk size directly affects performance, memory usage, how long transactions are held, database locks, and the amount of work that must be redone when an error occurs. There is no single optimal number for every Job; it must be based on the characteristics of the data, the writer, the database, and operational requirements.

## 1. How does chunk-oriented processing work?

A chunk-processing Step usually has three components:

- **ItemReader:** reads items one at a time from a data source such as a file, database, or message queue.
- **ItemProcessor:** optional, validates, transforms, or filters each item.
- **ItemWriter:** writes a group of processed items to a destination such as a database or file.

The general processing flow:

```text
                Begin transaction
                         |
                         v
                   ItemReader
                reads each item
                         |
                         v
                 ItemProcessor
                processes each item
                         |
                         v
             Commit interval reached?
                    /       \
                 Not yet    Yes
                    |          |
                    +-- read --+
                               v
                          ItemWriter
                  writes the chunk's items
                               |
                               v
                            Commit
                               |
                               v
                     Begin the next chunk
```

Spring Batch reads and processes items to form a chunk. When the commit interval is reached or the data source ends, the framework calls the writer for that chunk and commits the transaction if all operations complete successfully. After that, the Step continues with the next chunk until the reader reports no more data.

A transaction usually surrounds a chunk: the write operations belonging to the chunk are committed together. If an error causes the transaction to roll back, the changes belonging to that transaction are undone according to the capabilities of the transaction manager and the participating resources. Chunks that were committed earlier are retained.

## 2. What do commit interval and chunk size mean?

In modern Java configuration for Spring Batch, the chunk size is set on `StepBuilder`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

With `chunk(500, transactionManager)`, Spring Batch gathers up to 500 input items for a chunk before calling the writer and committing the transaction. If the processor filters items by returning `null`, the writer will receive fewer items than were read. If the data source has only 120 items left, the last chunk contains only 120 items instead of waiting to reach 500.

In older documentation and configuration, this concept is usually called `commit-interval`. Although the API name differs between the old XML configuration and Java configuration, the operational meaning remains the number of items processed in one chunk transaction.

### Example of chunk count and commits

Suppose the reader supplies 2,350 items and the chunk size is 500:

| Chunk | Items in chunk | Result |
|---|---:|---|
| 1 | 500 | Write and commit |
| 2 | 500 | Write and commit |
| 3 | 500 | Write and commit |
| 4 | 500 | Write and commit |
| 5 | 350 | Write and commit the last chunk |
| **Total** | **2,350** | **5 successful chunk commits** |

This is a simple calculation when there are no errors, retries, or special handling mechanisms. The actual number of commits can change when there are rollbacks, retries, skips, or when the Step stops midway.

## 3. How does chunk size affect transactions?

Chunk size is exactly the size of the Step's transaction unit under the chunk processing model. A larger chunk usually means the transaction stays open longer because more items need to be read and processed before writing and committing.

### Small chunks

For example `chunk(50, transactionManager)`:

- Transactions are usually shorter.
- Each rollback affects a smaller group of items.
- Commits are more frequent, so there is additional overhead for transaction management and writing metadata.
- The writer may receive small groups, increasing the number of calls to the database or target service.

Small chunks suit cases where each item takes a long time to process, transactions need to be short, or the target system is sensitive to the amount of data written at once. However, if the chunk is too small, the cost of commits and round trips can account for a large share of the total time.

### Large chunks

For example `chunk(2_000, transactionManager)`:

- The number of commits drops if the data volume stays the same.
- The writer can write in large groups and take advantage of the database's batch operations.
- The transaction may hold connections and locks longer.
- The chunk needs to hold more items in memory.
- When an error occurs before commit, the amount of the chunk's work that may need to be redone is larger.

A large chunk can improve throughput if the writer and database handle batched statements well. But if the transaction is too long, the database may hold locks for a long time, the transaction log grows, timeouts become more likely, or online requests are affected.

## 4. The relationship between chunk size, memory, and throughput

Within a chunk, Spring Batch needs to hold the items being processed until the writer runs. Therefore, a larger chunk size usually increases the amount of temporary data in memory. The increase also depends on the size of each item, the intermediate data produced by the processor, and how the reader is implemented.

For example, if each item after conversion occupies an average of 4 KB in memory, a chunk of 500 items needs about 2 MB of raw item data. A chunk of 5,000 items may need about 20 MB, not counting object overhead, buffers, collections, and other resources. This is only an estimate to help you picture it; the actual object size in the JVM can be considerably larger.

Throughput is the number of items processed per unit of time. Chunk size can affect throughput in the following ways:

- When the chunk is too small, the time spent on commits, writer calls, and round trips can account for a large share.
- When the chunk increases, the fixed cost per item can decrease and the writer has a chance to write more efficiently.
- Beyond a threshold, throughput may not increase further because the limit shifts to CPU, I/O, the database, the network, or the target system.
- If the chunk is too large, long transactions and memory pressure can reduce performance or increase the risk of timeouts.

Therefore, do not assume by default that the larger the chunk, the faster the Job. The goal is to find a size range that achieves good throughput within the limits of memory, transaction time, and database load.

## 5. Effects on rollback, retry, and skip

Chunk size also determines the scope of work protected by a transaction. Suppose the Step processes a chunk of 500 items. After the reader and processor have processed 500 items, the writer starts writing but hits an error that causes the transaction to roll back.

The database changes belonging to that chunk's transaction will be rolled back. Chunks committed earlier are retained. Depending on the retry/skip configuration and the type of error, Spring Batch may retry the chunk or the item, skip the failing item if allowed, or mark the Step as failed.

```text
Chunk 1: 500 items -> COMMIT
Chunk 2: 500 items -> COMMIT
Chunk 3: 500 items -> WRITER ERROR -> ROLLBACK
                                      |
                                      v
                           Retry / Skip / Fail
```

A chunk size of 5,000 can make a single rollback involve a larger group of items than a chunk size of 100. This does not mean all the items in the chunk will definitely be re-read in every configuration, because reader buffering, the retry policy, and checkpoints can affect the behavior. However, when designing, you should assume the items in a failed chunk may be processed again.

Some notes:

- **Retry:** only retry errors that are likely to resolve themselves, such as transient connection errors. A retry should not create repeated side effects.
- **Skip:** only skip an item when the business allows it; you need to save the failing item and the reason so it can be handled later.
- **Rollback:** understand clearly which resources participate in the transaction. Calling an external API, sending an email, or writing a file may not be rolled back along with the database.
- **Idempotency:** the writer and external tasks should have a unique processing key or a duplicate-prevention mechanism if an item may be retried.
- **Checkpoint:** with a reader that supports saving state, Spring Batch can continue from the committed checkpoint after a restart.

In particular, if the processor performs side effects such as calling a payment service or sending a notification, retrying the chunk can repeat that action. Keep the processor a pure data transformation where possible, and perform side effects at the write step with an idempotent mechanism or through a transactional outbox.

## 6. Chunk size is not the same as fetch size or JDBC batch size

Some other configurations also have a record-count value, but they control different layers:

| Concept | What does it control? | Example |
|---|---|---|
| Chunk size / commit interval | The number of items processed in one chunk transaction | `chunk(500, transactionManager)` |
| JDBC fetch size | A hint for the number of rows the driver fetches from the database each time | `fetchSize=1_000` |
| Reader page size | The number of records the reader gets in one query page | `pageSize=1_000` |
| JDBC batch size | The number of write statements grouped to send to the database as a batch | `JdbcBatchItemWriter` or driver/framework configuration |
| Partition size | The data range assigned to one partition to process | ID ranges or file segments |

These values can be coordinated but do not need to be equal. For example, the chunk size is 500, the reader page size is 1,000, and the JDBC batch writer groups statements in its own way. The reader may fetch more items than one chunk to buffer; that does not change the chunk's commit boundary.

Chunk size is also not the file size, the number of threads, or the number of partitions. Each concept solves a different performance problem.

## 7. How do you choose a chunk size?

There is no standard value for every system. You can start with a moderate value, then measure and adjust based on real data.

### Step 1: Understand the item and processing characteristics

Determine how large each item is, how much CPU the processor consumes, and how many operations the writer performs. If items contain a lot of data or the processing is complex, a chunk that is too large can create memory pressure.

### Step 2: Determine the transaction limits

Check whether the database has limits on timeout, lock duration, transaction log, or connections. If a chunk takes too long to complete, you need to reduce its size or optimize the queries and the writer.

### Step 3: Measure performance with multiple sizes

You can try values such as 100, 250, 500, and 1,000 in turn on representative data. For each run, record:

- The total Job completion time.
- The number of items read, processed, written, filtered, and skipped.
- Throughput (items/second).
- The average and longest time of a chunk.
- The number of commits, rollbacks, and retries.
- Heap usage, garbage collection, and CPU.
- Database CPU, I/O, lock waits, connection usage, and transaction duration.

Do not measure time only on a very small dataset. Use a volume and data distribution close to production, including large records or slow-writer cases.

### Step 4: Balance performance and recoverability

If a larger chunk increases throughput only slightly but memory and rollback time increase significantly, choose a smaller chunk. If a small chunk creates too many commits and writer round trips, increase it gradually to find a suitable level.

### Step 5: Set the configuration per type of Job

There is no need to force every Step to share one chunk size. A file import Step, a database-writing Step, and a Step that calls an external system can have different characteristics. Choose a separate value for each Step based on the resources and transaction the Step uses.

## 8. Example comparing two configurations

Suppose a Job imports 100,000 customers. The writer writes to a database and each commit has a significant fixed cost.

| Attribute | Chunk 100 | Chunk 1,000 |
|---|---:|---:|
| Number of input items | 100,000 | 100,000 |
| Theoretical number of chunks if run to completion | 1,000 | 100 |
| Number of successful chunk commits in the ideal case | 1,000 | 100 |
| Maximum number of items per chunk by configuration | 100 | 1,000 |
| Memory pressure for items sitting in a chunk | Lower | Higher |
| Transaction time per chunk | Usually shorter | Usually longer |
| Scope of items that may need reprocessing when a chunk rolls back | Smaller | Larger |

A chunk of 1,000 can reduce the number of commits and increase batch write efficiency. However, if each item is slow to process or the database holds locks for a long time, a chunk of 100 may be more stable. Actual results must be measured; the table only describes common trends.

## 9. Notes when running in parallel or with partitioning

In a sequential Step, chunks are usually processed one after another. When multi-threading or partitioning is enabled, multiple chunks or partitions may be processed concurrently depending on the configuration and the Spring Batch version.

When you increase the level of parallelism:

- Each chunk still has its own transaction boundary according to the configuration.
- The total number of items sitting in concurrent chunks can grow significantly.
- Multiple transactions writing to the database at the same time can contend for locks and connections.
- The reader, processor, and writer must meet the thread-safety requirements of the execution model.
- A large chunk size combined with many threads can create load spikes on the database.

For example, if 4 workers process concurrently and each worker has a chunk size of 1,000, there may be thousands of items held in chunks at the same time. Therefore, you need to tune the chunk size, the number of workers, the connection pool, and the resource limits of the target system together.

Partitioning divides the dataset into independent ranges; the chunk size inside each partition still determines the number of items in each transaction. Do not confuse partition size with commit interval.

## 10. Common mistakes when choosing the commit interval

**Choosing a chunk size that is too large just to reduce commits:** long transactions, increased memory, lock duration, and retry scope can make the Job slower or harder to recover.

**Choosing a chunk size that is too small:** the number of commits and writer calls increases, making transaction management overhead account for a large share.

**Assuming chunk size equals JDBC fetch size:** the two configurations serve different layers. The reader may fetch in pages larger or smaller than the chunk.

**Assuming a chunk always writes exactly the number of items read:** the processor may filter items, skips may occur, and the last chunk may be smaller than the commit interval.

**Ignoring side effects outside the transaction:** a database rollback does not automatically recall an email that was sent or an HTTP request that has completed.

**Measuring only by total time:** you need to observe throughput, heap, GC, transaction duration, lock waits, rollbacks, and writer errors as well.

**Using one chunk size for all Steps:** different data sources and writers have different characteristics; the configuration should be based on each Step.

## Conclusion

The commit interval, or chunk size, defines the number of items gathered into a chunk before the writer writes and the transaction is committed. A small chunk keeps transactions short and limits the amount of work in each rollback, but increases the number of commits. A large chunk can improve throughput and batch writing, but increases memory pressure, transaction hold time, and the amount of data that may have to be reprocessed. Start with a reasonable size, measure on representative data, and balance performance against recoverability, database load, and the business requirements of each Step.
