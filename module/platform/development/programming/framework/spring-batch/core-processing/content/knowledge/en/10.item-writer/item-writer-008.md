# Writer and Item Order

In Spring Batch, ItemWriter receives the items that have been read and processed from a chunk and writes them to a destination. Item order can matter when creating files, exporting reports, sending messages, or writing data that must preserve a business sequence.

What needs to be distinguished are the **order of items within a chunk**, the **order in which chunks are processed**, and the **order in which data is seen at the destination system**. In a sequentially running Step, Spring Batch delivers items to the writer in the order of the read flow after the processor has processed and filtered them. When parallel processing is used, the completion order among chunks or partitions can differ from the original read order. With a database, insert order also does not guarantee query order if the SELECT statement has no ORDER BY.

Therefore, if the business requires a deterministic order, you need to design the order from the data source, the choice of execution model, and how data is written/read at the destination. Do not rely on the physical order of records in the database.

## 1. ItemWriter Receives Data in Chunks

In a chunk-oriented Step, the basic flow is:

~~~text
ItemReader
    |
    v
Read items in source order
    |
    v
ItemProcessor
    |
    +---- returns null: the item is filtered
    |
    v
Remaining items in the chunk
    |
    v
ItemWriter
    |
    v
Write data to the destination
~~~

ItemWriter does not automatically sort items by ID, time, or any attribute. The writer receives the chunk the framework delivers and performs the write operation. If the writer needs a different order, the application must define that order explicitly.

In Spring Batch 5, the ItemWriter contract receives a Chunk:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Older versions use List in the write method:

~~~java
void write(List<? extends T> items) throws Exception;
~~~

The difference in parameter type does not change the design principle: the writer receives a group of processed items, and the order within the group reflects the order in which items passed through the pipeline. With Spring Batch 5, you can iterate over the items in the chunk in order:

~~~java
public class OrderWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            writeOne(order);
        }
    }

    private void writeOne(Order order) {
        // Write one order according to the application's logic.
    }
}
~~~

If the writer writes each item sequentially as in the example, the write operations within one call follow the chunk's iteration order. If the writer batches commands, calls asynchronous services, or sends data across multiple threads, you need to consider the order the writer itself produces.

## 2. Order in a Sequentially Running Step

In a sequentially running chunk-oriented Step, whatever order the reader returns items in, the items remaining after the processor usually reach the writer in that same order. The processor is called on each item following the chunk's processing flow. An ItemProcessor can:

- Return an object of the same or a different type to change the item's representation.
- Return null to filter the item out of the result.
- Throw an exception to report an error, after which the Step applies the fail, retry, or skip policy.

A processor normally does not change an item's position in the sequence. However, a custom processor can hold items, group them, or emit data by its own logic; if it does so, the application is responsible for the output order.

For example, the reader returns order codes in the order 101, 102, 103, 104. The processor filters order 102:

~~~text
Reader:       101 -> 102 -> 103 -> 104
Processor:    101 -> null -> 103 -> 104
Writer:       [101, 103, 104]
~~~

The writer receives the remaining items in the order 101, 103, 104. A filter creates a gap in the sequence but does not reverse the order of the remaining items on its own.

If the reader is a FlatFileItemReader, the order usually follows the line order in the file. If the reader reads from a database, the order must be specified in the query. Do not assume the database returns records in ID order or insert order if the query has no ORDER BY.

## 3. Determining the Order Right at the ItemReader

If order is a business requirement, it is best to start by identifying a stable sort key at the data source.

### With a JDBC reader

The query needs an ORDER BY:

~~~sql
SELECT
    order_id,
    created_at,
    customer_code,
    total_amount
FROM orders
WHERE status = 'READY'
ORDER BY created_at ASC, order_id ASC;
~~~

Here created_at defines the time order. order_id is a secondary key to distinguish records with the same created_at. If you only ORDER BY created_at and many records have identical timestamps, the order among those records is not fully determined.

Choose a sort key that is:

- Clearly meaningful to the business.
- Stable throughout the run.
- Given an additional unique tie-breaker if the primary key is not unique.
- Backed by an appropriate index if the dataset is large and the query needs good performance.

### With a paging reader

A JDBC paging reader divides data into pages. The sort keys must define a stable order across pages. If the sort key is not unique, records with the same value may be returned at unstable positions between page queries, especially when the source data changes while the Job runs.

For example, the sort key can consist of created_at and order_id. You need to ensure the sorting used is consistent on every page. With continuously changing data, consider a fixed data range, a snapshot, or a watermark-based filter condition to prevent new records from inserting themselves into the middle of paging.

### With a file reader

FlatFileItemReader usually reads in line order in the file. If the file is created from multiple sources or has been sorted beforehand, the input order reflects how the file was created. If you need a business order, define it at the file-creation step or read the data into a source with a deterministic order.

## 4. Chunk Boundaries and Order Between Chunks

Chunk size divides the item stream into groups for processing and committing. In a sequential Step, Spring Batch processes chunks in the sequence of the read flow:

~~~text
Source: 1 2 3 4 5 6 7 8
Chunk size = 3

Chunk 1: [1, 2, 3] -> Writer -> Commit
Chunk 2: [4, 5, 6] -> Writer -> Commit
Chunk 3: [7, 8]    -> Writer -> Commit
~~~

In this case, the writer is called in the order chunk 1, chunk 2, then chunk 3. The order of items within each chunk also follows the read flow after processing.

Chunk size is not a sorting parameter. Increasing or decreasing chunk size changes the commit boundaries and the number of items the writer receives each time, but does not change the read order of a sequential Step on its own.

If a chunk fails, a retry or restart can cause the items in the chunk to be executed again. Side effects in the writer need to be designed so they can be safely written again. The re-execution order should not be used as a mechanism to create business sequence numbers.

## 5. Order in Parallel Processing

When concurrency is enabled, you cannot assume the completion order among chunks is the same as the read order. A chunk may process faster than the previous chunk and finish writing first. This is a natural consequence of multiple threads working at the same time.

~~~text
Order chunks were created:

Chunk 1 ----------- long processing ----------------> write done
Chunk 2 ----- fast processing ----> write done
Chunk 3 -------- medium processing --------> write done

The completion order can be:
Chunk 2 -> Chunk 3 -> Chunk 1
~~~

In a multi-threaded Step, chunks are processed on different threads. Spring Batch does not guarantee a global completion order among chunks. If chunks write to the same file or a non-thread-safe resource, you need to synchronize the writer or design separate output for each worker.

In addition, an ItemReader shared among threads must support concurrent access or be protected appropriately. Many readers are not thread-safe. Synchronizing a reader can protect the read state but does not by itself create a guarantee about the commit order of chunks.

### Partitioning

With a partitioned Step, data is divided into independently processed ranges or partitions:

~~~text
Master Step
    |
    +-- Partition 1: order_id 1-1000
    |
    +-- Partition 2: order_id 1001-2000
    |
    +-- Partition 3: order_id 2001-3000
~~~

Each partition can run on a different worker. The order inside each partition can be preserved according to that partition's reader and Step, but the completion order among partitions is not guaranteed. If the shared output needs a global order, you need a merge or sort step after the partitions complete.

### Choosing concurrency when order is a mandatory requirement

If the business requires writing sequentially in exactly the source order, the simplest choice is usually to keep the Step sequential. If you need to increase throughput, you can divide the data into partitions with clear ranges, write separate output for each partition, and then merge by the sort key afterward.

Do not sacrifice business order by enabling multiple threads without an appropriate output and merge design.

## 6. AsyncItemProcessor and AsyncItemWriter

Spring Batch provides AsyncItemProcessor and AsyncItemWriter to handle the processor asynchronously. AsyncItemProcessor submits the processing work to an executor and returns a Future. AsyncItemWriter waits for the Futures and then passes the results to the delegate writer.

Within a chunk, AsyncItemWriter iterates over the Futures in the order they appear in the chunk and collects the corresponding results. Therefore, the time at which a Future completes does not necessarily determine the position of the result in the output chunk. A fast-processing item may finish before the item ahead of it, but its result is still collected in the order of the Future list.

~~~text
Input chunk: [A, B, C]

Async processing:
    A ----------- finishes last
    B --- finishes first
    C ------ finishes second

AsyncItemWriter collects results by the Future list:
    [result(A), result(B), result(C)]
~~~

This helps preserve order within a chunk when using the AsyncItemProcessor and AsyncItemWriter pair as designed. However, you need to distinguish this from running multiple chunks concurrently: the order among chunks can still differ. Also, an exception in a Future is usually detected when AsyncItemWriter gets the result, so you need to configure and observe errors at the right place.

Abbreviated configuration example:

~~~java
@Bean
public AsyncItemProcessor<OrderInput, Order> asyncProcessor(
        ItemProcessor<OrderInput, Order> delegate,
        TaskExecutor taskExecutor) {

    AsyncItemProcessor<OrderInput, Order> processor =
            new AsyncItemProcessor<>();
    processor.setDelegate(delegate);
    processor.setTaskExecutor(taskExecutor);
    return processor;
}

@Bean
public AsyncItemWriter<Order> asyncWriter(
        ItemWriter<Order> delegate) {

    AsyncItemWriter<Order> writer = new AsyncItemWriter<>();
    writer.setDelegate(delegate);
    return writer;
}
~~~

When using this pair, the output data type of AsyncItemProcessor is Future<Order>, so the writer in the Step must be declared corresponding to the item type the async writer receives. Check against the specific API of the Spring Batch version in use.

Async processing does not automatically make the writer thread-safe. AsyncItemWriter usually collects the results first and then calls the delegate writer; if the delegate or the underlying resource has its own concurrency mechanism, the application must still ensure safety.

## 7. Order in the Writer and the Destination System

Preserving order when calling the writer does not mean the data stored at the destination will always be read back in that order. This is especially important with databases.

### A database does not guarantee row order without ORDER BY

Even if the writer inserts item 1 before item 2, the query:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders;
~~~

is not guaranteed to return in insert order, primary key order, or physical on-disk order. The optimizer may choose a different execution plan, a different index, or a different way of reading.

If you need ordered results, query:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at ASC, order_id ASC;
~~~

Order must be expressed through sortable data, not by relying on the physical position of rows.

### Storing a sequence or business sort key

If the processing order needs to be preserved across multiple reads, store a sequence field or a sort key:

~~~java
public class Order {
    private String orderId;
    private LocalDateTime createdAt;
    private long sourceSequence;
}
~~~

sourceSequence can be the line number in a file, the position in the source, or a sequence number issued by a data-creation process. The writer writes this value along with the record. When reading back, the query uses:

~~~sql
SELECT order_id, created_at, source_sequence
FROM orders
ORDER BY source_sequence ASC;
~~~

If multiple files or multiple partitions create sequences, you need to add a file ID, partition ID, or a unique key to create a stable global order. Do not use each worker's in-memory counter if you need a unique order across the whole Job.

### File writer

With a FlatFileItemWriter running in a sequential Step, items are written in the order the writer receives them. If output is written concurrently from multiple workers, consider synchronization or writing to a separate file per partition. You can then merge the files by sort key.

Do not let multiple threads write into one sequential file if the writer does not support concurrency. Even if each write receives an ordered chunk, the write calls can interleave or complete in a different order when there is concurrency.

## 8. Can Sorting in the Writer Solve It?

The writer can sort the items in a chunk before writing:

~~~java
public class SortedOrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public SortedOrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        List<Order> sorted = chunk.getItems().stream()
                .sorted(Comparator.comparing(Order::getCreatedAt)
                        .thenComparing(Order::getOrderId))
                .toList();

        repository.saveAll(sorted);
    }
}
~~~

This example only sorts **within each chunk**. If chunk 2 contains a createdAt earlier than an item in chunk 1, sorting each chunk separately does not create a global order between the two chunks.

To sort the entire dataset, you need one of these strategies:

- Read a source that already has a stable global order via ORDER BY.
- Write data to a staging table together with a sort key, and then export or process further using an ORDER BY query.
- Write separate output for each partition, and then merge with a controlled sort step.
- Use an external sort or an out-of-memory sorting mechanism if the data is too large to load entirely into the heap.

Do not gather all data into a List in the writer just to sort it if the dataset can be large. That defeats the memory-bounding benefit of chunk-oriented processing and can cause OutOfMemoryError.

## 9. Skip, Retry, and Item Order

In a sequential Step, skipping an item usually creates a gap in the output stream but does not reverse the order of the remaining items. For example, if item 2 is skipped, the writer may receive [1, 3, 4].

A retry may cause an item to be read or processed again depending on the error type and configuration. For the writer, an error when writing a chunk can cause the transaction to roll back; the retry needs to write the data in a safe way. If the writer sends messages or calls an API outside the database transaction, a retry can create duplicate side effects.

When order is a business requirement, note that:

- A skip can leave some sequences missing; this is not necessarily an error if the rejected record has been recorded.
- A retry should not cause an item to be applied twice at the destination system.
- The writer needs to be idempotent or have a business key to prevent duplicate writes.
- Do not number items with a simple incrementing variable in the writer if multiple chunks run in parallel.
- When you need to audit order, store the source sequence and the processing status instead of inferring from the commit time.

## 10. Example: Exporting a File in Business Order

Suppose you need to export orders by creation time. The reader queries the database with a stable sort key:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'READY'
ORDER BY created_at ASC, order_id ASC;
~~~

The Step runs sequentially with a chunk size of 100:

~~~java
@Bean
public Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

If the writer is a FlatFileItemWriter configured to write sequentially, the output file keeps the order of the items the reader provides, except for items filtered or skipped by policy.

If the Step later moves to parallel execution, you need to reassess the requirements. You can write each partition to a separate file, add the sort key to each line, and then run a merge Step to create the final file ordered by createdAt and orderId. This is a way to separate increasing throughput from the global order requirement.

## 11. Common Mistakes

### Assuming the database returns data in insert order

Physical order is not part of the SQL contract. Use ORDER BY with a clear sort key.

### ORDER BY on a single non-unique column

If many rows have the same sort key value, the order among them may change. Add a unique tie-breaker such as the primary key.

### Thinking chunk size determines order

Chunk size controls group size and commit boundaries. It does not sort items and does not create business order.

### Enabling a multi-threaded Step and still expecting global order

Chunks may complete in a different order. If order is mandatory, keep processing sequential or design partitioning and a merge with a sort key.

### Using a non-thread-safe writer

Multiple workers writing to one resource can cause interleaved data, errors, or corrupted output. Use separate resources, a thread-safe writer, or a subsequent merge step.

### Sorting each chunk but thinking everything is sorted

Sorting in the writer only creates order inside each chunk. For a global order, you need to sort the source or merge/sort after all chunks have completed.

### Relying on commit time to infer business order

Transaction completion time is affected by concurrency, locks, and system load. Store a sequence or a business sort key.

### Writing non-idempotent side effects on retry

A retry can resend a message or write duplicate data if the writer calls a system outside the transaction. Use an appropriate idempotency key or outbox.

## 12. How to Design Item Order

When item order matters, answer these questions:

1. Which source determines the order: file line order, time, ID, or a business sequence?
2. Is the sort key unique and stable? If not, which tie-breaker is needed?
3. Does the reader have an ORDER BY or a mechanism to maintain the input order?
4. Does the processor filter, buffer, or change the order of items?
5. Does the Step run sequentially, multi-threaded, or partitioned?
6. Does the writer write sequentially and is it thread-safe?
7. Does the destination system preserve order, or do you need to store a sort key to query it back?
8. How are the sequence and idempotency managed during retry/skip/restart?

With a sequential flow, the design is usually simple: a source with stable order, a processor that does not reorder, and a writer that writes in the order received. With a parallel flow, you need to accept an undetermined completion order or add a sequence and a merge step to create output with a global order.

## Conclusion

ItemWriter receives items in the order the pipeline provides within each chunk; in a sequential Step, this order follows the reader's flow after the processor has processed and filtered. Chunk size does not sort items on its own. When running in parallel, the completion order among chunks or partitions can change. A database also does not guarantee query order without an ORDER BY. To preserve business order, define a stable sort key at the source, understand the effect of concurrency, write a sequence when needed, and query or merge the data by that key.
