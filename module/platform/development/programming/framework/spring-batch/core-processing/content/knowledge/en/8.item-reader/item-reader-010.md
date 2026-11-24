# Reader Thread Safety

In Spring Batch, an `ItemReader` usually keeps state to know which item needs to be read next. That state can be the current position in a file, a query cursor, the number of pages already read, or an iterator advancing through a data set. When a Step runs on multiple threads, multiple calls to `read()` can happen concurrently. If the reader is not designed to be safe for concurrent access, threads may read duplicate items, skip items, or corrupt internal state.

Therefore, when enabling multi-threaded processing, you must determine how the reader is used: each thread has its own reader, all threads share a synchronized reader, or reading still happens sequentially on one thread. Choosing a strategy affects correctness, processing order, performance, and restartability.

## 1. Why Can an ItemReader Be Non-Thread-Safe?

`ItemReader<T>` provides the `read()` method to return the next item or `null` when data is exhausted. This interface does not guarantee that every implementation is thread-safe. Many readers have state that changes after each read.

Example of a reader that manages its own position in a list:

```java
public class SimpleListReader implements ItemReader<String> {

    private final List<String> items;
    private int index = 0;

    public SimpleListReader(List<String> items) {
        this.items = items;
    }

    @Override
    public String read() {
        if (index >= items.size()) {
            return null;
        }
        return items.get(index++);
    }
}
```

On one thread, `index` is incremented sequentially and the reader can return items in order. But if two threads call `read()` at the same time, checking `index` and incrementing `index` is not an atomic operation. Both threads can read the same position before one thread updates the index, leading to returning the same item or corrupting the next position.

For readers that read from files, databases, or APIs, internal state can be more complex:

- A file reader may hold a line number, a buffer, and stream state.
- A cursor reader may hold a cursor and the current position in a `ResultSet`.
- A paging reader may hold the page number, sort key, or query information for the next page.
- A custom reader may hold an iterator, a cache, counters, or temporary data.

If multiple threads modify these states simultaneously without proper synchronization, the read results may be nondeterministic. A reader running correctly in a sequential test does not prove it is safe when run concurrently.

## 2. When Does Spring Batch Call a Reader from Multiple Threads?

A common case is a multi-threaded Step. A Step configured with a `TaskExecutor` can process chunks on different threads. Depending on the configuration and Step type, read, process, and write operations may be performed by worker threads.

General configuration example:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .taskExecutor(taskExecutor)
        .build();
```

When multiple chunks execute concurrently, the reader shared by the Step can receive `read()` calls from multiple threads. If the reader has mutable state and does not support concurrent access, this is a point at risk of errors.

Illustrative diagram:

```text
                  Multi-threaded Step
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Thread 1    Thread 2    Thread 3
             |           |           |
             +-----------+-----------+
                         |
                         v
                Shared ItemReader
                 concurrent read()
```

Common symptoms include:

- A record appears twice in the results.
- Some records are not processed even though the source has complete data.
- Errors like `ConcurrentModificationException`, cursor errors, or stream access errors.
- Item order at the Writer differs from the source order.
- Errors appear only when increasing the thread count or processing speed.
- Results differ between runs with the same data.

## 3. Approach 1: Synchronize read Calls with SynchronizedItemStreamReader

If multiple threads need to share a single reader, you can wrap the reader with `SynchronizedItemStreamReader`. This decorator synchronizes `read()` calls so that at any given time only one thread performs the read operation on the delegate.

Example with `FlatFileItemReader`:

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.support.SynchronizedItemStreamReader;
import org.springframework.core.io.FileSystemResource;

@Bean
public SynchronizedItemStreamReader<Customer> customerReader() {
    FlatFileItemReader<Customer> delegate =
            new FlatFileItemReaderBuilder<Customer>()
                    .name("customerFileReader")
                    .resource(new FileSystemResource("data/customers.csv"))
                    .delimited()
                    .names("id", "name")
                    .targetType(Customer.class)
                    .build();

    SynchronizedItemStreamReader<Customer> reader =
            new SynchronizedItemStreamReader<>();
    reader.setDelegate(delegate);
    return reader;
}
```

After wrapping, the Step uses `customerReader` like a normal `ItemStreamReader`. Threads can request items concurrently, but the `read()` operation on the delegate is executed sequentially.

```text
Thread 1 ----+
             |
Thread 2 ----+----> SynchronizedItemStreamReader
             |          |
Thread 3 ----+          v
                    lock / read()
                         |
                         v
                    Delegate Reader
```

### Advantages and Limitations

- Easy to apply when you need to protect a shared reader and cannot yet split the source into multiple parts.
- Avoids concurrent `read()` calls on the delegate.
- Processing steps after reading can still run concurrently depending on the Step configuration.
- Reading is serialized, so the reader can become a performance bottleneck.
- The decorator does not automatically make `ItemProcessor`, `ItemWriter`, caches, or other mutable state thread-safe.

`SynchronizedItemStreamReader` primarily synchronizes `read()` calls. You should not assume it makes the entire delegate and all related state thread-safe in every situation. You need to consider how the delegate manages `open`, `update`, `close`, and checkpoints based on the type of reader being used.

An important limitation is restartability. Spring Batch documentation notes that using a synchronized reader can make a Job non-restartable if re-reading an already-processed item is a problem. When threads read items in order but process and commit out of that order, a checkpoint may not simply represent a contiguous position in the source. Consider carefully before using this approach for a Job that requires exact restart.

## 4. Approach 2: Partitioning So Each Worker Has Its Own Reader

For large data requiring true parallel processing, partitioning is usually a better fit. Instead of letting multiple threads access a single reader, Spring Batch splits the data source into partitions. Each partition runs its own worker StepExecution and has its own reader, reading only the assigned portion of data.

Example splitting customers by ID range:

```text
Manager Step
    |
    +--> Partition 1: customerId 1 - 1000
    |        Worker StepExecution 1
    |        Reader instance 1
    |
    +--> Partition 2: customerId 1001 - 2000
    |        Worker StepExecution 2
    |        Reader instance 2
    |
    +--> Partition 3: customerId 2001 - 3000
             Worker StepExecution 3
             Reader instance 3
```

Each reader accesses only one range of data, so there is no need to share a cursor or index between workers. Partitions must be non-overlapping and must cover the exact data set to be processed.

With partitioning, you can use `@StepScope` to create a reader per worker StepExecution and retrieve bounds from `stepExecutionContext`:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<Customer> partitionReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("partitionCustomerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "name")
            .targetType(Customer.class)
            .build();
}
```

In the example, each partition has its own `inputFile` in the `ExecutionContext`. When a worker StepExecution is created, Spring Batch supplies the corresponding value so the reader opens the right source. For database data, you can pass `minId` and `maxId` and build a query bounded to that range.

`@StepScope` allows the bean to be created per StepExecution scope and supports late binding of parameters. However, merely adding `@StepScope` to a reader in a multi-threaded Step does not automatically create one reader per thread: threads within the same StepExecution can still share the bean's target. Reader isolation comes from separate StepExecutions in partitioning.

## 5. Approach 3: Keep Reading Sequential, Run Processing Asynchronously

If the time-consuming part is mainly in business processing, you can keep the `ItemReader` on a single sequential reading thread and offload the processing work to other threads. This avoids multiple threads calling the reader simultaneously.

An option in the Spring Batch ecosystem is `AsyncItemProcessor` combined with `AsyncItemWriter` (from the Spring Batch Integration module). The reader reads items in order, the processor processes items asynchronously, and the writer receives the corresponding results to write.

```text
Single Reader
     |
     v
Read items sequentially
     |
     v
AsyncItemProcessor
     |
     +----> Worker thread 1: process item A
     +----> Worker thread 2: process item B
     +----> Worker thread 3: process item C
     |
     v
AsyncItemWriter
     |
     v
Write results
```

This approach fits when the reader needs to maintain order or has non-thread-safe state, while the processor can run independently. Note that asynchronous processing results may complete in a different order than the read order. If the business requires output order, you need an ordering mechanism or sequence numbers to sort before writing.

Async processor also does not automatically make dependencies called inside the processor thread-safe. If the processor shares a client, cache, or mutable service, those components must still support concurrent access or be scoped appropriately.

## 6. Does @StepScope Solve Thread Safety?

`@StepScope` is commonly used with readers that need to receive JobParameters or `ExecutionContext` when the Step starts. It creates a bean scoped to a StepExecution, rather than creating a shared instance at application context startup.

The important thing is that this scope is tied to the StepExecution, not automatically tied to each thread:

| Configuration | Behavior |
|---|---|
| A singleton reader used in a multi-threaded Step | Multiple threads may access the same instance concurrently. |
| A `@StepScope` reader in a multi-threaded Step | Threads of the same StepExecution can still share that target reader. |
| A `@StepScope` reader in a partitioned Step | Each worker StepExecution can have its own target reader and its own scoped data. |

Therefore, `@StepScope` solves bean lifecycle and late binding. It does not replace synchronization or data partitioning design.

## 7. Other Components Also Need Concurrency Safety

Although this lesson focuses on the reader, thread safety must be considered for the entire pipeline:

- **ItemProcessor:** avoid shared mutable instance fields if multiple threads call `process()`. Shared dependencies must support concurrent access.
- **ItemWriter:** ensure the writer and the resources it uses are safe when multiple threads write. Transactions and write order need to be clearly designed.
- **Listeners:** listeners may be called from multiple threads; shared counters or collections need appropriate synchronization.
- **ExecutionContext:** do not share keys or mutable objects across partitions in a way that causes state overwrites.
- **Data source:** connections, cursors, file streams, or API clients must be used within the thread-safety limits of their implementation.

You should not assume that a thread-safe reader means the entire Step is thread-safe. Similarly, using `synchronized` on `read()` does not guarantee chunk completion order or write order.

## 8. Which Strategy to Choose?

| Need | Suitable strategy | Points to consider |
|---|---|---|
| Shared reader needing quick protection on read calls | `SynchronizedItemStreamReader` | Reading is serialized; evaluate restartability and processing order. |
| Data can be split into independent parts | Partitioning with a separate reader per StepExecution | Need to design non-overlapping partitions and cover all data. |
| Reader must run sequentially, Processor is the slow part | Async processor/writer | Need to manage result order and processor thread safety. |
| Small data, no parallelism needed | Sequential Step | Simplest, avoids unnecessary synchronization complexity. |

Prefer a strategy that reflects the data structure. If data can be divided into independent ranges, partitioning usually increases parallelism without making multiple threads contend over one cursor. If the source cannot be split and a reader must be shared, a synchronized wrapper is an option, though you must accept the performance limit and evaluate restart.

## 9. Testing a Reader in a Concurrent Environment

A reader running correctly sequentially is not enough to prove it is safe when multiple threads use it concurrently. When designing or choosing a reader for a concurrent Step, you should test these scenarios:

1. **No lost items:** total items processed matches the number of eligible items in the source.
2. **No duplicate reads:** each business key appears only the expected number of times.
3. **No state corruption:** no cursor, stream, iterator errors, or race conditions as load increases.
4. **Restartable:** stop the Job midway, restart the same JobInstance, and verify the checkpoint does not lose or reprocess data.
5. **Understood ordering:** if order matters, verify written results comply with required ordering rules.
6. **Proper resource closure:** readers, streams, and connections are closed after the Step finishes or fails.

Use test data with unique keys and large enough volume so threads actually overlap while running. Also test midway failure scenarios, because race conditions or inaccurate checkpoints may only surface during rollback and restart.

## 10. Common Mistakes

| Mistake | Cause | How to handle |
|---|---|---|
| Items duplicated or lost | Multiple threads mutate cursor/index without synchronization. | Use a thread-safe reader, synchronized wrapper, or partitioning. |
| Only adding `@StepScope` yet race condition persists | Multiple threads still share the reader within the same StepExecution. | Distinguish StepExecution scope from thread safety; isolate readers by partition or synchronize reads. |
| Speed does not increase when using a synchronized reader | Threads must wait on the lock to read sequentially. | Evaluate partitioning or keep reader sequential and run only processor asynchronously. |
| Job does not restart safely | Checkpoints and commit order are incompatible with how multiple threads read/write. | Check `ExecutionContext`, delegate restartability, and processing order; consider partitioning. |
| Reader is safe but writer still fails | Writer or shared dependency is not thread-safe. | Evaluate the whole pipeline, not just the reader. |
| Output results out of order | Chunks or processors complete in a different order than read order. | Use partition keys, sequence numbers, or a sorting mechanism if business requires it. |

## Conclusion

Thread safety of `ItemReader` matters when Spring Batch processes chunks across multiple threads because concurrent `read()` calls can mutate the reader's internal state at the same time. Non-thread-safe readers can lose, duplicate, or scramble item order. You can synchronize `read()` with `SynchronizedItemStreamReader`, split data with partitioning so each worker has its own reader, or keep the reader sequential and run the processor asynchronously. `@StepScope` creates beans per StepExecution but does not automatically create a separate instance per thread within the same Step. When choosing a solution, consider performance, transactions, checkpoints, restartability, and the thread safety of the processor, writer, and shared dependencies.
