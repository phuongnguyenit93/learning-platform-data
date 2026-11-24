# Item memory in a chunk

In Spring Batch, a **chunk** is a group of items read, processed, and written as one unit of work. When a Step processes a chunk, the items and intermediate results are kept in memory until the framework finishes writing and ends the chunk's transaction. Therefore, chunk size directly affects the amount of heap the Step may need at a given moment.

The larger the chunk size, the more items are usually held simultaneously. However, actual memory does not depend solely on item count. Object graph size, processors creating new objects, reader page prefetching, writer buffers, retries, and the number of concurrently running chunks can all increase memory usage.

Understanding an item's lifecycle inside a chunk helps you choose an appropriate commit policy, avoid holding data for too long, and process large data sets more stably.

## 1. How does an item pass through a chunk?

With a chunk-oriented Step, Spring Batch coordinates three main components:

- **ItemReader** reads an item from the source.
- **ItemProcessor** validates, filters, or transforms the item.
- **ItemWriter** writes the output items of the chunk.

Basic flow:

~~~text
Data source
     |
     v
 ItemReader
     |
     v
 Input items gathered
 in the current chunk
     |
     v
 ItemProcessor
     |
     v
 Valid output items
     |
     v
 ItemWriter
     |
     v
 Commit transaction
     |
     v
 Next chunk
~~~

Suppose the Step is configured with a chunk size of 100:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> reader,
        ItemProcessor<RawCustomer, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Spring Batch reads at most 100 items for a normal chunk, processes them, and then passes the results to the writer. When the chunk completes successfully, the transaction is committed and the Step moves to the next chunk.

Chunk size is the maximum number of input items gathered for one processing pass under this configuration. It is not the exact number of items guaranteed to be written, because the processor can filter items and the skip policy can remove faulty items.

## 2. Which objects can reside in memory?

While a chunk is being processed, the heap can contain many kinds of objects:

| Component | Data that may be held |
|---|---|
| Reader | Just-read item, prefetched data page, character buffer, or cursor state |
| Input chunk | Items read for the current chunk |
| Processor | Intermediate objects, DTOs, new entities, or auxiliary data |
| Output chunk | Items that have been transformed and will be received by the writer |
| Writer | Batch parameters, file write buffers, or lists waiting to be written |
| Framework | Execution metadata, contexts, exceptions, and chunk state |
| Application | Caches, collections, or references retained by services/listeners |

Example processor converting RawCustomer into a new Customer:

~~~java
public Customer process(RawCustomer input) {
    return new Customer(
            input.id(),
            input.name().trim(),
            normalizeEmail(input.email())
    );
}
~~~

During transformation, the input item and output object can coexist in memory. If each Customer retains a large object graph as well, heap usage can be much higher than the string data size seen in the file.

If the processor only modifies the input object and returns that same object, creating an extra large output object can be avoided. However, this approach is only appropriate when mutating the object is safe and does not affect source data or other components.

You should not assume each item occupies only the exact size of its data fields. An object can reference lists, maps, related entities, byte arrays, or other objects. When 100 items simultaneously hold large object graphs, total heap can grow quickly.

## 3. How long does a chunk hold items?

A simple way to picture it:

~~~text
Chunk starts
     |
     v
Read item 1
Read item 2
...
Read item N
     |
     v
Process items
     |
     v
Writer receives results
     |
     v
Update checkpoint/metadata
     |
     v
Transaction commits
     |
     v
Chunk completes
     |
     v
Chunk references are
released when no longer used
~~~

During processing, the framework needs to hold items long enough for the processor and writer to use them. After the chunk completes, internal chunk references can be dropped when the framework moves on to the next work.

However, **chunk commit does not mean the JVM immediately reclaims all memory of the items**. The Garbage Collector can only reclaim objects when there are no live references left pointing to them. If the application stores items in a global collection, cache, singleton service field, or listener, the objects remain retained after the chunk ends.

Example of a processor accidentally accumulating data:

~~~java
@Component
public class CustomerProcessor
        implements ItemProcessor<RawCustomer, Customer> {

    private final List<Customer> allCustomers = new ArrayList<>();

    @Override
    public Customer process(RawCustomer input) {
        Customer customer = convert(input);
        allCustomers.add(customer);
        return customer;
    }
}
~~~

Even though each chunk commits, the allCustomers list retains every Customer processed. As input data grows, memory grows with the total number of items across the entire Job instead of only the current chunk.

For large batches, avoid retaining all processed items in long-lived fields or collections. If you need to aggregate results, use counters, bounded accumulators, staging tables, or batch result writing mechanisms.

## 4. How does chunk size affect heap?

Chunk size is one of the most important factors determining how many items are held in one processing pass.

Suppose each item has an average real size equivalent to 20 KB after accounting for its related object graph. If a chunk holds 500 items, the item data portion alone can take about 10 MB. This is only an illustrative estimate; real heap also includes object headers, references, collections, output objects, and buffers of other components.

| Chunk size | Max items gathered | Memory trend |
|---:|---:|---|
| 10 | 10 | Small working set |
| 100 | 100 | Larger working set |
| 500 | 500 | Can grow significantly if items are heavy |
| 2,000 | 2,000 | Higher heap risk with large object graphs |

A smaller chunk usually reduces the number of items held simultaneously, but increases the number of transactions and commits. A larger chunk can use batch writes more efficiently, but increases the working set, transaction duration, and amount of data that may have to be reprocessed on rollback.

There is no single chunk size that is good for every Job. Measure with representative data, especially the largest items or those with the most complex object graphs, rather than relying only on average size.

## 5. Estimating memory for one chunk

You can use the following conceptual model to think about peak memory:

\[
M_{peak} \approx
C \times (S_{in} + S_{out} + S_{temp})
+ M_{reader}
+ M_{writer}
+ M_{framework}
\]

Where:

- \(C\): number of input items in the chunk.
- \(S_{in}\): average size of the input object along with its retained object graph.
- \(S_{out}\): average size of the output object.
- \(S_{temp}\): intermediate objects created by the processor or mapper.
- \(M_{reader}\): memory the reader uses for pages, prefetch, or buffers.
- \(M_{writer}\): memory the writer uses for batches and output buffers.
- \(M_{framework}\): other objects and metadata.

This is not an exact heap measurement formula. Some objects may be shared across multiple items; some temporary objects already become unreachable before the chunk ends; the processor may return the input object itself. The purpose of the formula is to remind you that chunk size is only one part of the total working set.

Example:

- Chunk size: 500.
- Each input item and retained object graph: about 20 KB.
- Each new output item: about 12 KB.
- Intermediate objects: about 4 KB per item.

Rough estimate for the item portion:

\[
500 \times (20 + 12 + 4)\text{ KB}
= 18\text{ MB}
\]

The actual number may be higher due to collections, strings, buffers, page prefetch, writer, and other objects. If 4 partitions run concurrently with a similar working set, total memory for active chunks can grow roughly with the number of workers, in addition to shared parts.

## 6. Does returning null from the processor reduce memory?

In Spring Batch, a processor returning null means the item is filtered and not passed to the writer:

~~~java
@Bean
public ItemProcessor<RawCustomer, Customer> processor() {
    return raw -> {
        if (!raw.isActive()) {
            return null;
        }

        return convert(raw);
    };
}
~~~

If a chunk reads 100 items but 30 items are filtered, the writer may only receive 70 items:

~~~text
Input chunk:       100 items
                       |
                       v
Processor:
  70 valid items
  30 items return null
                       |
                       v
Output chunk:       70 items
                       |
                       v
Writer writes 70 items
~~~

Filtering reduces the number of output objects that need to be written, but does not mean input memory is freed immediately when the processor returns null. The framework still needs to complete chunk processing and manage state, skip, and retry according to policy.

If input items are very large, filtering early can reduce output volume and writer work, but you should not rely on filtering as a substitute for controlling chunk size or avoiding loading unnecessary object graphs.

If records that do not need processing can be identified right in the source query, filtering at the query sometimes reduces both the number of items read and held in the chunk. Ensure query conditions accurately reflect the business logic and do not exclude data by mistake.

## 7. Reader prefetch can make memory larger than chunk size

Chunk size does not limit all data held by the reader. Some readers prefetch by page or buffer to reduce the number of accesses to the source.

Examples:

- **FlatFileItemReader** reads files line by line and uses a character buffer underneath.
- **JdbcPagingItemReader** fetches data page by page.
- **JdbcCursorItemReader** reads through a cursor; the JDBC driver may fetch in batches depending on configuration.
- Custom readers may prefetch a number of items into a collection before returning them one by one.

With a paging reader, the following can exist simultaneously:

1. Items in the page the reader has fetched.
2. Items already moved into the current chunk.
3. Output objects created by the processor.
4. Writer buffers.

Therefore, page size and chunk size are two separate concepts:

| Configuration | Controls |
|---|---|
| Chunk size / commit interval | Number of items gathered for one processing and transaction unit |
| Page size | Number of items the reader fetches in one page query |
| JDBC fetch size | Hint to the driver on how many rows to fetch each time; effectiveness depends on the driver |
| Writer batch size | Number of records the writer sends to the target system per batch, if the writer has a separate configuration |

Page size is not required to equal chunk size. However, too large a discrepancy can make the reader hold more items than necessary. Measure and choose configurations appropriate for the data source.

### Example of a reader prefetching all data itself

A custom reader can cause a memory error if written like this:

~~~java
public class InMemoryCustomerReader
        implements ItemReader<Customer> {

    private final Iterator<Customer> iterator;

    public InMemoryCustomerReader(CustomerRepository repository) {
        List<Customer> all = repository.findAll();
        this.iterator = all.iterator();
    }

    @Override
    public Customer read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
~~~

Even though the Step uses a chunk size of 100, the constructor loaded all customers into the heap. The chunk cannot limit the memory of a reader that holds the entire source itself.

For large data, use cursors, paging, keyset pagination, or appropriate streaming readers. Avoid calling findAll() on unbounded data sets.

## 8. Cursor readers and paging readers

The two reading strategies usually have different memory characteristics.

### Cursor reader

A cursor reader usually maintains an open cursor or result set and reads items gradually. The driver may use fetch size to retrieve data in batches, without necessarily loading the entire result into the heap.

Points to note:

- The cursor and connection may remain open for the duration of the Step.
- Fetch size is a hint to the driver, not an absolute memory guarantee.
- Transactions and isolation affect how long connections/cursors are held.
- Some databases or drivers have their own buffering behavior.

### Paging reader

A paging reader queries data page by page. Page size affects how many items the reader fetches at once.

Points to note:

- A page size that is too large can hold many items at the same time.
- Query ordering must be stable to avoid missing or duplicating items between pages.
- Source data changing between pages can affect consistency.
- On restart, the reader needs to save page state or an appropriate continuation key.

For both types, check the documentation of the specific reader and JDBC driver. Do not infer merely from the names cursor or paging that memory is always bounded to a fixed number.

## 9. Writers also consume memory

After the processor creates outputs, the writer may need extra memory to write in batches or buffer data.

Examples:

- A JDBC batch writer may hold batch parameters until sending the statement.
- A file writer has character buffers or transaction buffers.
- A composite writer may pass the same items to multiple delegates.
- A custom writer may accumulate items in a collection before writing.

If the writer copies the entire chunk into another list, at one point both the original chunk and the copy may exist. If the writer keeps references to written items in a field, memory can grow with the total number of chunks.

Example of a writer accumulating data without limit:

~~~java
public class UnsafeWriter implements ItemWriter<Customer> {

    private final List<Customer> written = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        written.addAll(chunk.getItems());
    }
}
~~~

This writer does not write data to the destination but keeps all received items in a list. After many chunks, the list grows without bound.

If statistics are needed, keep only small values like counters or group aggregations. If details need to be saved, write them to a database/file or an appropriate storage system instead of keeping all objects in the heap.

## 10. Retry and rollback can hold items longer

When a chunk hits an error and is retried, the framework may need to hold or restore already-read items to try again. The specific behavior depends on reader type, exception location, and fault-tolerant configuration.

Some situations:

- The reader already read items, then the writer hits an error.
- The processor hits an exception and the item is retried.
- The skip policy requires identifying the item causing the error.
- Chunk rollback forces the reader to re-provide data.
- The reader has buffering or its own transactional resource.

In these cases, items can stay alive longer than one normal processor call. If items contain large data, retrying many times can increase heap pressure and object retention time.

Keep the retry policy bounded, only retry transient errors, and avoid saving extra copies of items in listeners or exception handlers.

## 11. Multiple chunks or partitions running in parallel

When a Job processes in parallel, memory does not depend on just one chunk. Each active worker or partition may have its own reader, chunk, processor, and writer.

Example with 4 partitions, each using chunk size 500:

~~~text
Worker 1: chunk 500 + reader/writer buffers
Worker 2: chunk 500 + reader/writer buffers
Worker 3: chunk 500 + reader/writer buffers
Worker 4: chunk 500 + reader/writer buffers
                  |
                  v
       Total concurrent working set
       scales with the number of workers
~~~

If each chunk needs about 18 MB for items and intermediate objects per the earlier estimate, 4 concurrent chunks can need about 72 MB for that part alone, not counting buffers, framework, thread stacks, and shared objects.

Therefore, increasing the number of partitions or threads can increase throughput but also increases peak heap. Do not multiply chunk size and concurrency at the same time without measuring memory headroom.

With partitioning, each worker has its own StepExecution and ExecutionContext. Avoid sharing mutable objects between workers without appropriate synchronization. Each partition's reader and writer should have independent resources and data ranges.

## 12. CompletionPolicy and commit interval

In typical configurations, a fixed chunk size decides when a chunk has enough items to complete. Spring Batch also supports CompletionPolicy to decide when a chunk ends according to other conditions.

For example, a policy can complete a chunk by item count or by time. When using a time-based policy, the number of items in a chunk can vary with read and processing speed.

This affects memory:

- Fixed chunk size creates a clearer limit on item count.
- A time-based policy can gather many items if the source reads fast during that window.
- A custom policy needs an item count limit if you want to control heap.
- If a policy relies solely on time without an item count limit, high source speed can make chunks larger than expected.

Therefore, when using CompletionPolicy, specify both a time limit and a count limit. Do not assume a chunk has a fixed size if the policy allows ending on dynamic conditions.

## 13. Small or large chunk size?

Choosing chunk size is a balance between memory, performance, and transactions.

| Chunk size | Advantages | Trade-offs |
|---|---|---|
| Small | Lower working set; short transactions; fewer items rolled back | More commits; increased overhead |
| Large | Can utilize batch writes; fewer commits | Higher heap; long transactions; costlier rollbacks |
| Too large | Can reduce some overhead in suitable workloads | Prone to increased GC, holding locks long, and OutOfMemoryError |

Examples:

- Items consisting of only a few short primitive/string fields: larger chunks may fit.
- Items containing images, large JSON, or deep entity graphs: smaller chunks are needed.
- Writer performs batch writes efficiently: chunks may need to be large enough to utilize batching.
- Paging reader: need to coordinate page size and chunk size.
- Multiple partitions: must calculate total working set across workers.

There is no default number like 100, 500, or 1,000 that is right for every system. Start at a moderate level, measure heap and processing time, and then adjust.

## 14. How to reduce item memory footprint

### Read only necessary fields

If the processor only needs ID, name, and status, do not read the entire entity with many relationships or blobs.

With JDBC, explicitly select the needed columns:

~~~sql
SELECT customer_id, customer_name, status
FROM customer
WHERE status = 'ACTIVE'
ORDER BY customer_id
~~~

With JPA, consider projections or DTOs instead of loading the entire entity graph if not needed.

### Avoid eager loading of large data

One item can pull in many eager relationships or collections. Hundreds of items can cause tens of thousands of related objects to be loaded.

Only load relationships that are used. Avoid letting the processor accidentally access lazy relations, causing extra queries and object graphs to be created.

### Do not keep items in global collections

Processors, writers, and listeners should not accumulate all items in singleton bean fields. Use counters, aggregate statistics, or save results outside the heap.

### Process via streaming

For large files or sources, read line by line or page by page. Avoid loading an entire file or query result into a List before forming chunks.

### Reduce intermediate objects

If item transformation creates many large DTOs/lists/maps, consider creating only objects needed for the writer. Avoid copying the same payload multiple times.

### Keep only necessary state

ExecutionContext should hold small checkpoints like line numbers, pages, last ID, or reader position. Do not store all items of a chunk in the ExecutionContext.

## 15. Monitoring memory while the Job runs

StepExecution counters such as readCount, writeCount, filterCount, commitCount, and rollbackCount help understand progress, but do not directly measure item heap.

To monitor memory, you can use:

- JVM heap metrics via Micrometer or Spring Boot Actuator.
- Garbage collection metrics and GC logs.
- Java Flight Recorder (JFR) to observe allocation and object retention.
- Heap dumps when OutOfMemoryError occurs or heap levels rise abnormally.
- Profiling to find objects holding long-lived references.
- Dashboards by JobExecution ID, StepExecution ID, and partition.

Some common symptoms:

| Symptom | Possibility to check |
|---|---|
| Heap rises steadily after each chunk | Processor/writer/listener is retaining references |
| Heap spikes sharply when Step starts | Reader loads the whole source or prefetch is too large |
| Heap grows with partition count | Each worker has its own working set |
| GC runs frequently yet heap stays high | High allocation rate or live set is too large |
| OutOfMemoryError in writer | Batch buffers or accumulating collections |
| Heap does not drop after Job completes | Live references from caches, singletons, or static collections |

After a chunk ends, used heap does not necessarily drop immediately on charts. The JVM can hold allocated heap regions for reuse. What to observe is the **live set** after GC and the upward trend over many chunks, not just total committed heap.

## 16. Estimating and measuring chunks in a real environment

A practical workflow:

1. Choose a representative data set, including both small and large items.
2. Run with a small chunk size, such as 50 or 100.
3. Observe heap before, during, and after several chunks.
4. Record allocation rate, GC pauses, and commit times.
5. Increase chunk size step by step and re-measure.
6. Test with the number of partitions/threads expected in production.
7. Test cases where the processor creates new output objects and the writer buffers batches.
8. Check memory after many chunks to detect accumulating collections.

Do not measure only the first chunk. Some retention bugs only appear after thousands of chunks, when the application accumulates unbounded references or caches.

## 17. Example of choosing chunk size by data type

Suppose there are two Jobs:

**Job A — importing product codes**

- Small items: ID, code, short name.
- Processor normalizes a few strings.
- Writer writes via JDBC batch.
- Reader pages by ID.

This Job can try larger chunks to leverage batch inserts, as long as heap and transactions remain within limits.

**Job B — processing customer profiles**

- Items contain large JSON and many relationships.
- Processor creates new DTOs with collections.
- Writer calls external services.
- Multiple partitions run in parallel.

This Job should start with smaller chunks and limit the number of workers. If large payloads need processing, you can keep only IDs in the chunk and fetch details right when needed, or stream the payload.

Do not use the same chunk size for two Jobs just because they run on the same application.

## 18. Common misunderstandings

### Thinking chunk size limits the entire heap

Chunk size only limits the number of items in one processing unit according to policy. Readers can prefetch, writers can buffer, and applications can retain objects outside the chunk.

### Thinking commit frees memory immediately

Commit ends the transaction; it does not force the JVM to reclaim objects. Objects can only be GC'd when no live references remain.

### Thinking filtered items use no memory

Input items have still been read and may be held while the chunk is processed. Filtering mainly reduces output sent to the writer.

### Thinking page size and chunk size are the same

Page size belongs to the reader; chunk size belongs to the Step's commit policy. The two values can differ and together affect the working set.

### Thinking a streaming reader is guaranteed to use very little memory

Drivers, cursors, page buffers, or custom readers can prefetch data. You need to measure and verify the actual configuration.

### Thinking increasing chunk size always improves performance

Large chunks can reduce commit overhead but increase GC, transaction duration, and rollback risk. Performance must be measured holistically.

### Thinking garbage collection will fix a memory leak

GC only reclaims objects that are no longer referenced. Global collections or unbounded caches still keep objects alive.

## 19. Process for controlling memory for a chunk

When designing a chunk-oriented Step, check in order:

1. How does the chunk size or CompletionPolicy limit the number of items?
2. What are the average and maximum sizes of an input item?
3. Does the processor create new output objects or object graphs?
4. Does the reader prefetch by page or buffer the whole source?
5. Does the writer keep its own batches or collections?
6. Are there retries/skips causing items to be retained longer?
7. How many chunks/partitions can be active concurrently?
8. Do services, listeners, or singletons keep references across chunks?
9. Does ExecutionContext store only small checkpoints or is it holding payloads?
10. How do heap, allocation rate, and live set change over time?

Memory of a chunk is not just multiplying chunk size by the size of one object. It is the total working set of the reader, inputs, outputs, processor, writer, and concurrent workers. By keeping objects scoped to the chunk, avoiding excessive prefetching, and not accumulating references across chunks, Spring Batch can process large data sets with more stable heap usage.
