# How chunk size affects throughput and memory

In Spring Batch, chunk-oriented processing reads, processes, and writes data in groups of items. The group size is configured with the **chunk size** or **commit interval**. This value directly affects the number of transaction commits, the amount of data held in memory, the processing time of each transaction, and recoverability when errors occur.

A large chunk size can help increase throughput by reducing the repeated cost of commits, but it can also make transactions longer and increase the memory required. A small chunk size usually limits the amount of data being held and reduces the rollback scope, but creates more transactions. There is no single optimal number for every Job; choose it based on the characteristics of the items, reader, processor, writer, database, and the application's level of concurrency.

## 1. What is chunk size?

A chunk is a group of items that Spring Batch reads and processes before passing the group of results to the ItemWriter. In a chunk-oriented Step, the standard flow consists of:

- **ItemReader** reads items from the data source.
- **ItemProcessor** processes, transforms, or filters items; this component can be omitted if not needed.
- **ItemWriter** writes the chunk's items to the destination.
- Spring Batch manages the transaction and commits the chunk according to the configured size.

For example, a chunk size of 100 means the Step gathers up to about 100 read items for a chunk before calling the writer and completing the transaction. If the data source has only 35 items left at the end, the last chunk can contain 35 items.

~~~text
Chunk size = 3

Reader          Processor           Writer
  |                 |                  |
  +-- item 1 ------>+                  |
  +-- item 2 ------>+                  |
  +-- item 3 ------>+                  |
                    |                  |
                    +-- chunk [1,2,3] ->+--> write data
                                       |
                                       +--> commit transaction

  +-- item 4 ------>+
  +-- item 5 ------>+
                    |
                    +-- chunk [4,5] --->+--> write data
                                       |
                                       +--> commit transaction
~~~

The last chunk does not necessarily have as many items as configured. In addition, the number of items the writer receives can be smaller than the number of items the reader read because ItemProcessor can return null to filter an item. Therefore, you need to distinguish read count, process count, filter count, and write count when observing StepExecution.

### Declaring the chunk size

With the Spring Batch 5 and later API, the chunk size is passed into StepBuilder along with the transaction manager:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

In the example, 100 is the commit interval. Spring Batch gathers items into chunks according to this value and manages the Step's transaction through the transaction manager passed in.

You can externalize the chunk size value so it can change between environments without modifying code. For example, declaring a configuration class:

~~~java
@ConfigurationProperties(prefix = "batch.orders")
public class BatchOrderProperties {

    private int chunkSize = 100;

    public int getChunkSize() {
        return chunkSize;
    }

    public void setChunkSize(int chunkSize) {
        this.chunkSize = chunkSize;
    }
}
~~~

Register the configuration class with **@EnableConfigurationProperties(BatchOrderProperties.class)** and inject BatchOrderProperties into the Step declaration method:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        BatchOrderProperties properties,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(properties.getChunkSize(), transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

The value can be set in application.properties:

~~~properties
batch.orders.chunk-size=100
~~~

You should validate the configuration value at startup to avoid a chunk size of 0 or an invalid value. Externalizing the chunk size also helps you try different levels in a performance-testing environment.

## 2. How does chunk size affect throughput?

**Throughput** is the amount of work completed per unit of time, for example the number of records written successfully per second or per minute. Chunk size affects throughput because it determines how often transaction-based operations are performed.

Each chunk usually incurs some fixed or near-fixed costs:

- Beginning and completing the transaction.
- Writing the Step's metadata and checkpoint.
- Performing round trips to the database.
- Calling the writer and handling batch statements.
- Synchronizing or flushing data according to the resource's mechanism.

When the chunk size is small, these costs repeat frequently. If the database has significant commit latency, the time spent on commits can account for a large share of the total processing time.

When you increase the chunk size, the same number of items is divided into fewer chunks. The commit cost and some per-chunk operations are spread across more items, so throughput can increase.

However, the benefit does not grow without limit. When the bottleneck shifts to CPU, I/O, database queries, the network, or the speed of the target system, increasing the chunk size may not help further. If the chunk is too large, long transactions and prolonged locks can even reduce throughput.

### A simple cost model

Suppose each item needs an average processing time of t and each chunk has a fixed cost of c. With chunk size n, you can picture the approximate time of a chunk as:

~~~text
T_chunk = n × t + c

Approximate throughput = n / T_chunk
~~~

As n increases, the fixed cost c is divided among more items. But this model does not account for contention, GC, locks, batch writes, timeouts, and costs that grow with transaction size. In a real system, t and c can also change with load.

A hypothetical illustrative example:

| Chunk size | Time per chunk | Approximate throughput |
| ---: | ---: | ---: |
| 50 | 1.2 seconds | 41.7 items/second |
| 100 | 1.8 seconds | 55.6 items/second |
| 250 | 3.5 seconds | 71.4 items/second |
| 500 | 8 seconds | 62.5 items/second |

The numbers above only illustrate the calculation and are not a Spring Batch benchmark. In this example, increasing from 50 to 250 improves throughput because the commit cost is spread better. Increasing further to 500 makes the transaction and the processing of each chunk longer, causing throughput to drop.

### When can increasing the chunk size improve throughput?

Increasing the chunk size is usually worth trying when:

- Each commit has significant latency.
- The writer supports batch writes and can handle many items more efficiently in one call.
- CPU and the database have spare resources.
- Items have a small memory footprint and fairly stable processing time.
- The current transaction is short and has not caused locks or timeouts.

If the writer performs a separate INSERT statement for each item and does not take advantage of batch writes, increasing the chunk size can reduce the number of transactions but does not necessarily reduce the number of write round trips. You need to look at how the writer actually interacts with the database.

### When does increasing the chunk size not help?

Increasing the chunk size usually does not resolve the bottleneck if:

- Each item has to call a remote API with high latency.
- A database query is taking up most of the processing time.
- CPU is already saturated by the data transformation.
- The database is limited by IOPS or lock contention.
- The writer is already limited by the speed of the target system.
- GC frequently has to collect large objects.

In these situations, you need to find the real bottleneck. Optimizing queries, reducing the number of remote service calls, using a batch writer, tuning the connection pool, or improving the algorithm can bring greater benefit than increasing the chunk size.

## 3. How does chunk size affect memory?

Chunk-oriented processing needs to hold the chunk's items during reading and processing, and then pass the results to the writer. Therefore, a large chunk size usually increases the number of objects that can exist simultaneously in the heap.

A rough way to estimate:

~~~text
Chunk memory
    ≈ number of items in the chunk
      × average footprint of each item
      + collection and framework overhead
~~~

An item's footprint is not just the size of a few data fields. It can include the referenced object graph, strings, child collections, binary data, output objects created by the processor, and buffers inside the reader or writer.

For example, suppose an item together with its object graph takes about 20 KB:

| Chunk size | Estimated raw memory for items |
| ---: | ---: |
| 100 | About 2 MB |
| 500 | About 10 MB |
| 1,000 | About 20 MB |
| 5,000 | About 100 MB |

This is only an illustrative estimate. Actual memory can be higher due to object headers, references, collections, intermediate data, buffers, the reader, and the writer. If the processor creates new output objects or holds references to the input data, the footprint can increase further.

### The memory of the whole Step is not just the chunk

Chunk size is one factor, but total memory also depends on:

- Whether the reader pre-buffers many items.
- Whether the reader uses paging and holds a page of results in memory.
- Whether the processor creates large object graphs or caches data.
- Whether the writer has its own buffer before writing.
- Whether the ORM keeps entities in the persistence context.
- Whether the ExecutionContext or listeners hold large data.
- How many chunks or workers are active concurrently.

Therefore, do not infer that a chunk size of 100 always needs only the memory of 100 objects. A paging reader may hold an extra page, the writer may create additional batches, and the ORM may keep managed entities in the persistence context.

### Chunk size and the number of concurrent workers

If the application runs multiple partitions or multiple workers in parallel, each worker may have its own chunk in progress. The memory for chunks can grow with the number of concurrent workers:

~~~text
Memory for items being processed
    ≈ number of concurrent workers
      × chunk size
      × average item footprint
~~~

For example, four workers processing a chunk size of 500, with an average footprint of 20 KB per item:

~~~text
4 × 500 × 20 KB ≈ 40 MB
~~~

The roughly 40 MB is only the raw item portion under the assumptions. It does not include reader/writer buffers, intermediate objects, the framework, thread stacks, connections, the ORM, and JVM overhead. If you increase the chunk size to 2,000 in the same four-worker configuration, the raw item portion can rise to about 160 MB.

Chunk size does not by itself decide the number of workers or chunks running concurrently. Concurrency comes from the task executor configuration, partitioning, or another parallel execution mechanism. When tuning, you must evaluate the chunk size together with the level of parallelism.

## 4. Chunk size and transaction time

In a chunk-oriented Step, a chunk is the normal commit boundary. The transaction begins for processing the chunk and is completed after the writer finishes along with the related updates.

A large chunk size usually lengthens the transaction time because many items are read, processed, and written before commit. This can cause:

- Database locks being held longer.
- Transaction timeouts or query timeouts.
- An increased risk of deadlocks when multiple Jobs access the same data.
- An increased amount of work to roll back when a chunk fails.
- Other transactions having to wait for resources.

A small chunk size creates shorter transactions but increases the number of commits. With a database that has a high commit cost, this can reduce throughput.

| Aspect | Small chunk | Large chunk |
| --- | --- | --- |
| Number of commits | More | Fewer |
| Time per transaction | Usually shorter | Usually longer |
| Memory of items held | Usually lower | Usually higher |
| Rollback scope | Usually smaller | Can be larger |
| Per-chunk metadata cost | Repeated more | Spread across more items |
| Lock/timeout risk | Can be lower | Can be higher |
| Throughput | May be limited by commit overhead | Can be higher until another bottleneck is hit |

Do not set a large chunk size just to reduce the number of commits while ignoring transaction timeouts, locks, and recoverability.

## 5. Chunk size and the reprocessing scope on errors

Chunk size also affects recovery cost. If the writer fails before the transaction commits, the current chunk's transaction can roll back. Chunks that were committed earlier are still saved.

With a large chunk, many items may be in the failing chunk. On retry or restart, part of the work may have to be redone depending on the exception type, the fault-tolerant configuration, the reader, the processor, and the writer.

For example:

~~~text
Chunk size = 4

Chunk 1: [1, 2, 3, 4] -> written successfully -> COMMIT
Chunk 2: [5, 6, 7, 8] -> writer error -> ROLLBACK
Chunk 3: not yet processed

When continuing:
  chunk 1's data has been committed
  chunk 2 needs to be processed according to the retry/restart policy
~~~

With a larger chunk size, the scope of items involved in a failed transaction can be larger. This can increase reprocessing time, especially when the processor performs a CPU-intensive transformation or the reader has to access a slow data source.

However, not every error causes the entire chunk to always be reprocessed in the same way. Spring Batch has retry and skip mechanisms; the behavior depends on when the error occurs, the type of writer, whether the reader can be reset, and the fault-tolerant configuration. When designing, test real-world errors and ensure side effects are idempotent.

With a small chunk size, the number of items in a transaction is usually smaller, so rollback and recovery usually have a narrower scope. In return, more transactions create additional overhead in the normal run case.

## 6. Chunk size is not the same as fetch size or the writer's batch size

A common confusion is to think chunk size controls all the database's batch sizes. In reality, these are different parameters:

| Parameter | What does it control? |
| --- | --- |
| **Chunk size / commit interval** | The number of items in a chunk and the Step's commit boundary |
| **JDBC fetch size** | A hint to the JDBC driver about the number of rows fetched from the ResultSet each time |
| **Paging page size** | The number of rows a paging query fetches per page |
| **JDBC batch size** | The number of statements or parameter sets sent in one write batch, depending on the writer/driver |
| **ORM flush/clear interval** | How often entities in the persistence context are synchronized and released |

These values are related but do not always need to be equal. For example, a chunk size of 500 can use a reader fetch size of 100 and a writer JDBC batch size of 100. In that case, a chunk can be read through multiple fetches and written as multiple small batches within the same transaction.

### A reader using a cursor or paging

With a JDBC cursor reader, the fetch size is a hint to the driver about how to fetch data from the database. The chunk size still determines the number of items gathered for a write/commit. Depending on the driver and configuration, the fetch size can affect client-side memory and the number of round trips.

With a paging reader, the page size determines the number of rows each page is queried for. If the page size is smaller than the chunk size, a chunk may need to read through multiple pages. If the page size is larger than the chunk size, the reader may retain items not yet used in the current page.

Do not increase the fetch size or page size just because you increased the chunk size. Measure the number of queries, the amount of buffered data, the read time, and the memory footprint separately.

### A writer using JDBC batch

A writer can group many write statements to send to the database as a batch. The JDBC batch size affects the number of statements sent in each execution, while the chunk size affects the transaction containing the write operations.

If the chunk size is 1,000 but the writer sends batches in groups of 100, a chunk can produce multiple executeBatch calls within the same transaction. This configuration can balance packet size, driver limits, and transaction duration.

With ORM/JPA, check whether the writer flushes or clears the persistence context. If entities are retained for a long time, the persistence context can become a significant source of heap consumption even when the chunk size seems reasonable.

## 7. How to choose an initial chunk size

There is no general formula that applies to every application. You can choose a starting value based on the item type and the cost of the reader/writer, then measure with data close to reality.

Some ways of thinking:

- Small items, light processing, a writer that supports batching well: you can try a medium or larger chunk size.
- Items with large object graphs, a processor that uses a lot of memory: start with a small chunk to limit the heap.
- A writer that performs slow operations or transactions at risk of timeout: avoid a chunk that is too large.
- A database with high commit latency: try increasing the chunk size to reduce commit frequency.
- Complex retry/skip or frequent data errors: consider the reprocessing cost of a large chunk.
- Many parallel workers: start cautiously because each worker may hold a chunk at the same time.

For example, you can start measuring with levels 50, 100, 250, and 500. This is only an illustrative test range. With large items or a small heap, the suitable range can be much lower; with very small items and a good batch writer, you can try higher values if the transaction and the database allow.

## 8. A metrics-driven tuning process

Tuning the chunk size should be a controlled experiment. Changing many parameters at once makes it hard to identify what caused the results to change.

### Step 1: Choose representative data

Use a dataset with a size, distribution, and characteristics similar to production. Include small and large items, cases where the processor filters data, real write data, and error scenarios if they occur frequently.

Do not measure only a few dozen items if the real Job processes millions of records. Startup overhead, JIT, caches, and connection pools can make the result of a short run unrepresentative.

### Step 2: Establish a baseline

Choose an initial chunk size and record:

- Total Job and Step time.
- Read count, write count, filter count, skip count.
- The number of chunks or commits that can be observed.
- The average and high-percentile time of a chunk if there is instrumentation.
- Heap usage, GC pauses, and the number of GCs.
- CPU usage and I/O wait level.
- Database latency, lock waits, deadlocks, connection usage, and transaction log.

These metrics help distinguish whether the Job is limited by CPU, memory, the database, or transaction cost.

### Step 3: Change one factor

Keep the dataset, concurrency, reader, processor, writer, and database configuration unchanged. Change the chunk size level by level, running repeatedly enough times to reduce the influence of caches, JIT, and system variation.

An example results table:

| Chunk size | Step time | Throughput | Heap peak | GC pause | DB commit latency |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | Record the measurement | Computed from items/time | Record the measurement | Record the measurement | Record the measurement |
| 100 | Record the measurement | Computed from items/time | Record the measurement | Record the measurement | Record the measurement |
| 250 | Record the measurement | Computed from items/time | Record the measurement | Record the measurement | Record the measurement |
| 500 | Record the measurement | Computed from items/time | Record the measurement | Record the measurement | Record the measurement |

Throughput should be computed on the number of items actually completed under the same definition across runs. If one run skips more items, do not compare only the write count while ignoring that difference.

### Step 4: Observe the saturation point

If throughput rises as the chunk size increases while the heap peak, GC pause, and transaction duration stay within limits, you can continue trying to increase in a controlled way.

If throughput barely increases while heap, GC, or locks rise noticeably, you have reached the region of diminishing returns. In that case, choosing a lower chunk size is usually more reasonable.

### Step 5: Test with real concurrency

After choosing a few suitable values for a single worker, re-check at the expected level of concurrency. Multiple workers can increase total memory, connection usage, and contention on the database.

Do not choose a chunk size based on a single-threaded experiment and then apply it as-is to a Job running dozens of partitions.

### Step 6: Test error and restart scenarios

Try writer failures, transient errors, skips, and restarts in a test environment. Measure the amount of work that has to be reprocessed, the rollback time, and the ability to restore the checkpoint. A chunk size that gives high throughput under ideal conditions may not be suitable if the recovery cost is too large.

## 9. A real-world example: importing orders

Suppose a Job imports 1,000,000 orders from a file into PostgreSQL. Each item is read, validated, converted into an entity, and written to the orders table.

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
Chunk buffer
   |
   v
JDBC batch writer
   |
   v
PostgreSQL
~~~

An initial configuration might be:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, businessTransactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

Suppose each item after parsing and conversion has a footprint of about 8 KB. A chunk size of 100 produces about 800 KB of raw item data for one worker, not counting overhead. If you increase it to 1,000, the raw item portion can be about 8 MB for one worker.

If the Job runs 8 workers in parallel, the corresponding raw item portion can be about 6.4 MB with a chunk of 100 or 64 MB with a chunk of 1,000. This is still only a simple estimate; you need to measure the actual heap.

If the database has high commit latency and the writer supports JDBC batch well, increasing from 100 to 250 or 500 can reduce the number of commits and improve throughput. But if each order has many entity relationships, the processor creates large object graphs, or the transaction holds locks on a shared table, a large chunk can make the heap and locks rise sharply.

An option you can try:

| Component | Test value | Role |
| --- | ---: | --- |
| Chunk size | 100, then try 250 and 500 | Number of items in a chunk transaction |
| JDBC fetch size | 100 | Hinted number of rows fetched each time |
| JDBC batch size | 100 | Number of write operations grouped in a batch |
| Worker concurrency | 1 first, then test the expected level | Number of concurrent processing threads |

The numbers are only a starting point for experiments. Adjust them according to the driver, writer, database, item size, and the heap limit of the environment.

## 10. Signs that the chunk size is too small or too large

### Signs the chunk size is too small

- The number of commits is very high relative to the number of items.
- Transactions are short but commit overhead accounts for a large share.
- The database receives many small commit operations.
- The application's CPU is not high but throughput is low due to waiting on I/O or commits.
- The writer is capable of batching but receives very few items each time.

In this case, try increasing the chunk size and observe throughput, commit latency, and transaction duration.

### Signs the chunk size is too large

- The heap peak rises sharply with the chunk size.
- GC pauses are prolonged or many Full GCs appear.
- Transaction duration exceeds the desired limit.
- Lock waits, deadlocks, or timeouts increase.
- When errors occur, the rollback or reprocessing time is large.
- Throughput does not increase further or begins to drop.

When you see these signs, reduce the chunk size and further identify the cause in the reader, processor, writer, or concurrency.

## 11. Practical principles

**Measure before optimizing.** Throughput needs to be measured on representative data. Do not choose a chunk size based only on a number that is common in examples or documentation.

**Account for intermediate memory too.** Do not just multiply the number of items by the original object size. Consider the object graph, output objects, reader/writer buffers, and the persistence context.

**Tune together with concurrency.** Each worker may hold its own chunk. Increasing the chunk size and the number of concurrent workers can make memory grow with the product of the two factors.

**Keep transactions within limits.** Check timeouts, locks, and deadlocks when increasing the chunk size. A large transaction can reduce the ability to coordinate with other data-writing flows.

**Distinguish the kinds of batch size.** Chunk size, JDBC fetch size, page size, and JDBC batch size have different purposes. Change each value according to the bottleneck it addresses.

**Design for restart and idempotency.** A large chunk can make the rollback or reprocessing scope larger. The writer and processor need to be safe when items are processed again by the retry/restart mechanism.

**Externalize configuration.** You can configure the chunk size per environment, but you need validation and reasonable value limits to prevent a configuration change from overloading the heap or the database.

## 12. A process for choosing the chunk size for a Step

When designing or optimizing a Step, determine in turn:

1. The average and largest size of an item after the reader and processor create the data.
2. The number of items to process and the target throughput.
3. The read, process, and write cost per item.
4. The commit latency and transaction limits of the database.
5. The writer's batching capability and the reader's fetch/page configuration.
6. The available heap, GC behavior, and the number of concurrent workers.
7. The retry/skip policy and the reprocessing cost when a chunk fails.
8. Benchmark results with a few chunk sizes on representative data.

Choose the value that meets the target throughput within the limits of memory, transactions, and recoverability. If increasing the chunk size no longer improves throughput, stop at a lower level that has a safety margin on resources.

## Conclusion

Chunk size determines the number of items gathered into a chunk and affects commit frequency, throughput, memory in use, transaction time, and the reprocessing scope on errors. A large chunk can reduce commit overhead but usually holds more data and lengthens transactions. A small chunk limits memory and the rollback scope but can increase commit cost. Tune based on metrics for throughput, heap, GC, database latency, transaction duration, and concurrency on the application's representative data.
