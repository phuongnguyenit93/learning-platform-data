# Chunk Too Large Causing Out-of-Memory in Spring Batch

## 1. The Problem and Warning Signs

**A chunk size that is too large causing out-of-memory** is a common pitfall when running **Spring Batch Core Processing** on large datasets. In chunk-oriented processing, Spring Batch buffers a group of items as one unit of processing and transaction commit. If each item consumes substantial memory or too many items remain live simultaneously, the JVM can suffer heavy garbage collection (GC) pressure, degraded throughput, heap exhaustion, or termination by the OS for exceeding its memory limit.

Example job importing one million orders:

~~~text
orders.csv (1,000,000 records)
            |
            v
       ItemReader
            |
            v
       ItemProcessor
            |
            v
        ItemWriter
            |
            v
         Database
~~~

With **chunk size = 100**, each chunk processes about 100 items before writing and committing. If you change it to **chunk size = 100,000** to reduce commit count, the Step may have to retain hundreds of thousands of results, auxiliary structures, and transaction state before completing a single chunk. With large objects, even several gigabytes of heap may not be enough.

Common symptoms:

- Heap usage spikes sharply within a chunk, drops after commit and GC, or climbs steadily across chunks.
- Long GC pauses, with CPU spending more time collecting garbage than doing business work.
- Later chunks run slower even though item counts match earlier chunks.
- The JVM throws **OutOfMemoryError: Java heap space** or **GC overhead limit exceeded**.
- Containers report **OOMKilled**, sometimes exiting with code 137 and no Java stack trace.
- Retries or rollbacks become slow because many items must be reprocessed inside one huge transaction.
- The job is killed before updating metadata, leaving a `JobExecution` stuck in `STARTED`.

Not every OOM is caused by chunk size. The reader might load an entire file into RAM; the processor might hold an unbounded cache; the JPA persistence context might retain too many entities; the writer might serialize the whole chunk into one massive JSON string; or multiple chunks might run in parallel. This lesson focuses on **identifying and fixing oversized chunks** while clearly distinguishing them from related causes.

## 2. How Chunk-Oriented Processing Works

A chunk-oriented Step typically executes:

1. Reader returns an item.
2. Processor transforms or filters the item by rules.
3. Spring Batch accumulates results for a batch of items.
4. Writer receives the batch of items to write.
5. `ItemStream`/`ExecutionContext` and metadata are updated at checkpoint boundaries per framework mechanics.
6. The transaction commits; the Step moves to the next chunk.

~~~text
Chunk #1: items 1..100
  read -> process -> write -> commit/checkpoint

Chunk #2: items 101..200
  read -> process -> write -> commit/checkpoint

Chunk #3: items 201..300
  read -> process -> write -> commit/checkpoint
~~~

In Spring Batch 5+ configuration:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, ProcessedOrder>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

The number **100** is the commit interval. It does not mean the job processes only 100 records, nor does it guarantee every writer call contains exactly 100 outputs: the processor can filter, errors can trigger skips or retries, and the final chunk may be shorter.

### Why Does Chunk Size Increase Footprint?

Before the writer finishes, Spring Batch usually has to hold the chunk's output items; with fault-tolerant processing, references for retry/skip may also be kept. Other objects can coexist:

- Input data and output object graphs.
- Collections holding items, intermediate DTOs, and references.
- JPA/Hibernate persistence context plus snapshots for dirty checking.
- JDBC parameter buffers and batching structures.
- JSON/XML serializer buffers or request bodies.
- Lookup caches from the processor.
- Retry context, exceptions, and transaction state.
- Multiple chunks active across different threads.

Not every implementation holds all of these simultaneously, yet **a large commit interval raises the maximum amount of data held within one unit of work**.

## 3. Approximate Memory Model

You can estimate:

\[
M_{\text{peak}} \approx M_{\text{baseline}}
+ C \times (M_{\text{input}} + M_{\text{output}} + M_{\text{overhead}})
+ M_{\text{buffers}} + M_{\text{parallel}}
\]

Where:

- **C**: target item count per chunk.
- **M_input**: memory of input items still retained.
- **M_output**: memory of processor outputs.
- **M_overhead**: references, collections, and framework state.
- **M_buffers**: drivers, writers, ORM, serialization, and I/O.
- **M_parallel**: other chunks/tasks running concurrently.
- **M_baseline**: Spring context, JVM, thread stacks, background caches, and non-chunk objects.

This is a capacity model, **not an exact heap measurement formula**. Input and output sometimes share objects, GC can run between allocations, and some buffers live off-heap.

Suppose one output object holds about **200 KiB** of payload, before overhead:

| Chunk size | Output payload alone |
|---:|---:|
| 10 | ~2 MiB |
| 100 | ~19.5 MiB |
| 500 | ~97.7 MiB |
| 1,000 | ~195.3 MiB |
| 5,000 | ~976.6 MiB |

At chunk size 5,000, nearly 1 GiB goes to output payloads alone. Adding object graphs, inputs, ORM, serializers, threads, and native memory easily breaks a 2 GiB container.

**Do not estimate Java object size solely from the byte length of a CSV line on disk.** A short line can spawn many `String`s, collections, and entities after parsing; large JSON may be copied again during serialization.

Tools like **Java Flight Recorder (JFR)**, heap dumps, or profilers measure allocations and retained sizes so data replaces guesswork.

## 4. Distinguishing Causes of High Memory Usage

| Location | Issue | Characteristic symptom |
|---|---|---|
| Chunk buffer | Too many results awaiting writer | Peak scales with chunk size |
| ItemReader | Loads entire file/query result into a `List` | Heap already high before first chunk |
| ItemProcessor | Creates huge payloads, nested graphs, unbounded cache | High allocation rate or heap climbs across chunks |
| ItemWriter | Copies entire chunk into JSON, byte arrays, batch buffers | Peak hits during write/serialize |
| JPA/Hibernate | Managed entities, relationships, and snapshots | Old-gen occupancy and flush/commit time climb |
| JDBC driver | Large fetch/batch buffers | Heap/native memory scales with driver settings |
| Retry/skip | Many items retained or reprocessed | Peak hits during error/rollback |
| Async processor | Queued `Future`s and pending results | Heap scales with queue depth |
| Multi-threaded Step | Many concurrent chunks | Peak scales with worker count |
| Logging | Payloads, stack traces, async appender queues | Memory scales with event volume |

If lowering chunk size still leaves heap climbing relentlessly across thousands of chunks, look for **long-lived references** instead of merely shrinking the commit interval further.

## 5. GC and Types of OutOfMemoryError

### Java heap space

~~~text
java.lang.OutOfMemoryError: Java heap space
~~~

Heap cannot satisfy a new object allocation. Chunks holding many DTOs or entities are a frequent culprit.

### GC overhead limit exceeded

~~~text
java.lang.OutOfMemoryError: GC overhead limit exceeded
~~~

The JVM spends most of its time in GC while reclaiming very little. Many reachable objects, unreleased caches, or an undersized heap can all contribute.

### Direct buffer memory

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
~~~

Involves off-heap direct buffers. Looking only at heap used can miss the root cause. HTTP clients, NIO, and some drivers use direct memory.

### OOMKilled in Containers

~~~text
Reason: OOMKilled
Exit code: 137
~~~

The container exceeded its memory limit across both heap and native allocations; the JVM may not even have time to log a Java OOM exception. Inspect memory working set/RSS and container limits, not only `-Xmx`.

### Two Chart Patterns to Distinguish

~~~text
Pattern A: peak rises with chunk, then recovers

heap ^
     |       /\         /\         /\
     |      /  \       /  \       /  \
     |_____/    \_____/    \_____/    \____> time
            commit     commit     commit

Pattern B: retained memory climbs across chunks

heap ^
     |                           ______
     |                   _______/
     |           _______/
     |__________/______________________> time
~~~

Pattern A points to chunks/buffers; Pattern B points to caches, JPA contexts, or long-lived references. Still, heap may not drop immediately on commit because GC does not necessarily run instantaneously; observe across multiple cycles and inspect retained objects.

## 6. Shrinking Chunk Size: The Direct Fix

When peak memory scales primarily with commit interval, try reducing from 10,000 down to 500 or 100 items:

~~~java
.chunk(100, transactionManager)
~~~

Benefits:

- Fewer items must coexist inside a single chunk.
- Smaller transactions, reducing records reprocessed on rollback.
- More frequent checkpoints, reducing work replayed on restart.
- Lower risk of writers allocating oversized buffers.

Trade-offs:

- More commits and `JobRepository` updates.
- Potentially more JDBC/database round-trips.
- Lower throughput if commit latency is the bottleneck.
- Too tiny a chunk can make per-transaction overhead dominate.

For one million records, approximate chunk counts:

| Chunk size | Chunk count |
|---:|---:|
| 10 | 100,000 |
| 100 | 10,000 |
| 500 | 2,000 |
| 1,000 | 1,000 |
| 10,000 | 100 |

There is no universal "standard" chunk size for every system. Benchmark to find the sweet spot balancing **peak heap, throughput, commit latency, rollback cost, and headroom**.

## 7. Example Order-Processing Step with Bounded Chunks

The following example uses Spring Batch 5+, streaming a CSV file line-by-line, transforming into small DTOs, and writing to a database. It shows how to avoid loading the entire input into a collection.

### 7.1. Data Definitions

~~~java
import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {
}

public record ProcessedOrder(
        String orderId,
        String customerId,
        BigDecimal netAmount) {
}
~~~

DTOs avoid retaining raw lines, binary attachments, or entire API responses unnecessarily. If records carry multi-megabyte payloads, consider passing object-storage references and loading content only where actually needed.

### 7.2. Checkpointed FlatFileItemReader

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("importOrderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

The reader returns one record at a time instead of loading the entire file. **`saveState(true)`** lets the reader save state at Step checkpoints. **`@StepScope`** resolves `inputFile` when the Step runs and prevents sharing a stateful reader instance across executions.

### 7.3. Processor Without Retaining All Items

~~~java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
public ItemProcessor<RawOrder, ProcessedOrder> orderProcessor() {
    return order -> {
        BigDecimal netAmount = order.amount()
                .multiply(new BigDecimal("0.95"));

        return new ProcessedOrder(
                order.orderId(),
                order.customerId(),
                netAmount);
    };
}
~~~

The processor does not append every item to a `List` or `Map` that lives until the job ends. If a lookup cache is needed, enforce bounded size and eviction policies.

### 7.4. JDBC Batch Writer

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JdbcBatchItemWriter<ProcessedOrder> orderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO processed_order
                     (order_id, customer_id, net_amount)
                 VALUES (:orderId, :customerId, :netAmount)
                 """)
            .itemSqlParameterSourceProvider(item -> {
                var params = new org.springframework.jdbc.core
                        .namedparam.MapSqlParameterSource();
                params.addValue("orderId", item.orderId());
                params.addValue("customerId", item.customerId());
                params.addValue("netAmount", item.netAmount());
                return params;
            })
            .build();
}
~~~

This snippet uses `MapSqlParameterSource` to map Java record accessors explicitly. For standard JavaBean domain types, **`beanMapped()`** can be used when compatible. The JDBC writer needs the right `DataSource`/transaction manager to participate in the Step's transaction.

Illustrative schema:

~~~sql
CREATE TABLE processed_order (
    order_id    VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(64) NOT NULL,
    net_amount  DECIMAL(18, 2) NOT NULL
);
~~~

A plain `INSERT` only illustrates chunked writing. Jobs with restart/retry and replay risk require an idempotent or controlled upsert strategy keyed by business key.

### 7.5. Step and Job Configuration

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, ProcessedOrder> orderProcessor,
        JdbcBatchItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<RawOrder, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

These `@Bean` methods belong in a `@Configuration` class with Batch infrastructure configured. This demonstrates **bounding items per chunk**, not a guarantee that chunk size 100 fits every payload.

## 8. The Reader Must Truly Stream

A common mistake is choosing a small chunk size while the Reader already loaded the entire input into memory:

~~~java
// Anti-pattern for large files:
List<RawOrder> allOrders;
try (var lines = Files.lines(path)) {
    allOrders = lines.skip(1)
            .map(this::parse)
            .toList();
}

return new ListItemReader<>(allOrders);
~~~

By the time the first item is returned, the `List` already holds every record on the heap. With millions of records, **`chunk(10)`** still does not help because the source collection holds the entire input.

Appropriate options:

| Source | Reader / strategy |
|---|---|
| CSV/text | `FlatFileItemReader` line-by-line |
| Database | `JdbcCursorItemReader` or `JdbcPagingItemReader` |
| JPA | `JpaPagingItemReader` with configured page size |
| Large XML | StAX/streaming item reader |
| Large JSON | Streaming parser per record; avoid `readTree` of whole file |
| Object storage | Streaming download/range or controlled artifact staging |
| Message/queue | Backpressure-aware consumption, contract-based checkpoints |

### Chunk Size Differs from Page Size and Fetch Size

**Chunk size** controls the commit interval. **Page size** controls how many items a paging reader fetches per page. **Fetch size** is typically a hint to the JDBC driver for rows fetched per round-trip. These three parameters govern different memory layers.

Example paging reader (`queryProvider` configured for the database):

~~~java
JdbcPagingItemReader<RawOrder> reader =
        new JdbcPagingItemReaderBuilder<RawOrder>()
            .name("pagedOrdersReader")
            .dataSource(dataSource)
            .pageSize(200)
            .queryProvider(queryProvider)
            .rowMapper((rs, rowNum) -> new RawOrder(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
~~~

This is a configuration snippet; add imports and a `queryProvider` with a suitable sort key. When source data can mutate while the job runs, use snapshots or watermarks; a small page size **does not by itself prevent** missing or duplicate records.

## 9. JPA/Hibernate Persistence Context

JPA keeps managed entities in the **persistence context** for dirty checking, relationship tracking, and flushing. One entity can pull in many related entities or snapshots, making its memory footprint much larger than a plain DTO.

~~~text
JpaPagingItemReader
       |
       v
Order entity
  + Customer
  + List<OrderLine>
  + Address
       |
       v
Processor/Writer
       |
       v
Persistence context and flush/commit
~~~

Mitigations:

- Query projections/DTOs containing only needed fields.
- Avoid eager-loading large associations unused by the Step.
- Size page size and chunk size according to real record size.
- Understand how `JpaPagingItemReader`/`JpaItemWriter` in your version manage `EntityManager` and clear the persistence context.
- For custom JPA writers, call flush/clear at appropriate transaction points.
- Never keep an `EntityManager` or entity graph alive across all chunks unnecessarily.
- Never share a non-thread-safe `EntityManager` across multiple worker threads.

Illustrative example with a valid transaction-bound `EntityManager`:

~~~java
for (ProcessedEntity entity : batch) {
    entityManager.persist(entity);
}

entityManager.flush();
entityManager.clear();
~~~

This illustrates an idea for a **custom JPA writer**, not an instruction to put `clear()` inside every processor. Clearing detaches managed entities and can affect unflushed changes or logic expecting managed entities; design around your application's transactions and check `JpaItemWriter` semantics before adding similar logic.

## 10. Writer Creating Copies of the Chunk

A writer can accidentally double or triple memory footprint:

~~~java
// Anti-pattern when chunks are large:
String body = objectMapper.writeValueAsString(
        chunk.getItems());
httpClient.send(body);
~~~

At this moment, all of these may coexist:

1. The chunk holding Java objects.
2. The JSON `String` for the entire chunk.
3. The byte buffer for the HTTP request.
4. Temporary buffers created by the serializer/client.

If a partner accepts at most 100 items per request, you can split requests:

~~~java
List<? extends ProcessedOrder> items = chunk.getItems();
int maxItemsPerRequest = 100;

for (int start = 0; start < items.size();
        start += maxItemsPerRequest) {
    int end = Math.min(start + maxItemsPerRequest, items.size());
    externalApi.sendBatch(items.subList(start, end));
}
~~~

Splitting requests **only caps individual request sizes**; it does not reduce how many items Spring Batch holds in the chunk. To lower the Step's memory peak, you still need a smaller chunk size or a different processing model. If HTTP requests create side effects, design idempotency/reconciliation since they do not roll back automatically with the DB transaction.

With `JdbcBatchItemWriter`, the driver can also retain parameter buffers. Inspect database-specific driver settings rather than applying one uniform batching option across every database.

## 11. Retry, Skip, and Rollback Raise Memory Peaks

A fault-tolerant Step can retry items or reprocess data after a rollback:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(20)
~~~

This is an illustrative configuration snippet, with exceptions defined/imported by the application. If the writer fails near the end of a 10,000-item chunk, rolling back and reprocessing can cost significant CPU, memory, and DB I/O. Smaller chunks shrink the scope of work to reprocess, even though commit counts rise.

**`OutOfMemoryError` is not a business error to skip like a parse failure.** Once the JVM runs out of memory, even loggers and transaction managers may lack resources to finish. Never configure skip/retry for OOM as if it were a bad item; fix the memory root cause and perform post-incident recovery.

Do not use `skip(Exception.class)` or retry every exception just to make a job report `COMPLETED`: doing so masks system errors and can drop output.

## 12. Multi-Threaded Steps and Active Chunk Count

When running multiple chunks concurrently, memory peak depends on both commit interval and concurrency:

\[
M_{\text{active chunks}} \approx
\text{concurrent chunks} \times M_{\text{per chunk}}
\]

If each chunk takes ~50 MiB and eight workers are active, chunk data alone can approach 400 MiB. If task queues or `AsyncItemProcessor` hold many `Future`s, total footprint grows larger still.

Example executor configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public ThreadPoolTaskExecutor batchExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}
~~~

The corresponding Step can use:

~~~java
return new StepBuilder("parallelImportStep", jobRepository)
        .<RawOrder, ProcessedOrder>chunk(100, transactionManager)
        .reader(threadSafeReader)
        .processor(orderProcessor)
        .writer(threadSafeWriter)
        .taskExecutor(batchExecutor)
        .build();
~~~

`threadSafeReader` and `threadSafeWriter` represent components designed and tested for concurrency. Not every `ItemReader`/`ItemWriter` is thread-safe; multi-threaded configuration can also affect checkpoints and restarts, which must be addressed separately.

### Backpressure

If the reader/processor produces objects faster than the writer/DB consumes them, queues can grow. Control:

- Active worker count and pending task count.
- Executor queue capacity.
- Item counts and **total in-flight bytes**.
- JDBC/HTTP batch sizes.
- Number of concurrent partitions.
- Retry frequency and backoff durations.

Bounding by item count alone may be insufficient when a few payloads are hundreds of times larger than average.

## 13. Metrics and Logs for Measuring Memory

Important measurements:

| Metric | Purpose |
|---|---|
| JVM heap used/committed/max | Observe remaining heap headroom |
| Old-gen used | Detect long-lived objects |
| Allocation rate | See object creation rate |
| GC pause duration/count | Measure garbage collection cost |
| Direct buffer memory | Detect off-heap pressure |
| Process RSS | Total physical process memory |
| Container working set/limit | Risk of being OOMKilled |
| Step/chunk duration | See how commit interval affects latency |
| Read/write/skip/rollback counts | Assess progress and failures |
| DB commit latency/lock waits | Check impact of long transactions |

Spring Boot Actuator/Micrometer can export JVM metrics to Prometheus, such as common metric names:

~~~promql
jvm_memory_used_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
jvm_gc_pause_seconds_count
jvm_gc_pause_seconds_sum
~~~

Exact names and labels depend on version and registry; verify your application's metrics endpoint. Heap metrics alone are not enough to know container memory usage, since the process also allocates native memory.

### Listener Taking a Heap Snapshot After Each Chunk

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public class ChunkMemoryListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkMemoryListener.class);
    private final MemoryMXBean memory =
            ManagementFactory.getMemoryMXBean();

    @Override
    public void afterChunk(ChunkContext context) {
        MemoryUsage heap = memory.getHeapMemoryUsage();
        long usedMiB = heap.getUsed() / (1024L * 1024);
        long maxMiB = heap.getMax() / (1024L * 1024);

        log.debug(
                "event=chunk.committed stepName={} commitCount={} "
                + "heapUsedMiB={} heapMaxMiB={}",
                context.getStepContext().getStepName(),
                context.getStepContext().getStepExecution()
                        .getCommitCount(),
                usedMiB,
                maxMiB);
    }
}
~~~

Register the listener with the Step:

~~~java
.listener(new ChunkMemoryListener())
~~~

A snapshot **after a chunk** may miss the peak during writer serialization or when multiple tasks run concurrently. For benchmarks, pair with JFR/heap profilers or sufficiently granular sampling metrics. Do not log `INFO` on every chunk in jobs with hundreds of thousands of chunks, because logging itself adds CPU, I/O, and memory pressure.

## 14. Benchmarking to Pick the Right Chunk Size

A valid experiment must hold dataset, DB config, memory limits, JVM version, and concurrency constant while varying chunk size.

Example plan:

| Test | Chunk size | Workers | Goal |
|---|---:|---:|---|
| A | 50 | 1 | Baseline |
| B | 100 | 1 | Reduce commit overhead |
| C | 250 | 1 | Observe GC and heap |
| D | 500 | 1 | Find throughput saturation point |
| E | 100 | 4 | Concurrency impact |
| F | 250 | 4 | Bound in-flight memory |

Measure in each test:

- Job duration and throughput in records/second.
- Peak heap, old-gen occupancy, GC pauses, allocation rate.
- RSS and container memory peak.
- Chunk p50/p95 duration, commit latency, rollbacks/retries.
- Completeness/uniqueness of output after the job.

Illustrative figures, **not an executed benchmark**:

| Chunk | Throughput | Peak heap | GC pause |
|---:|---:|---:|---:|
| 50 | 6,000 items/s | 450 MiB | 12 s |
| 100 | 8,200 items/s | 510 MiB | 13 s |
| 250 | 9,300 items/s | 720 MiB | 17 s |
| 500 | 9,400 items/s | 1,250 MiB | 55 s |
| 1,000 | 7,100 items/s | 1,850 MiB | 110 s |

In this hypothetical scenario, chunk 250 can be better than chunk 500 because throughput is nearly identical while memory headroom is much larger. Production must measure against representative data, including large records, errors, retries, and concurrent load.

**You do not need to run until OOM to find the limit.** Stop increasing chunk size once peak heap or GC pauses no longer meet operational targets.

## 15. JVM Heap and Container Limits

Container memory limits must cover **heap + non-heap/native memory**:

- Metaspace and code cache.
- Thread stacks.
- Direct buffers.
- JVM/GC internal memory.
- JNI or compression/encryption libraries.
- Memory-mapped files and other environment-specific native allocations.

Illustrative JVM configuration:

~~~text
-Xms512m
-Xmx1536m
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/secure-diagnostics
~~~

If a container is allocated only 2 GiB, setting `-Xmx` close to 2 GiB may leave insufficient native headroom. Measure peak RSS, inspect cgroup limits, and tune against actual runtime behavior. Newer JVMs also support sizing heap as a percentage of container RAM; exact behavior depends on JVM version and options.

**Heap dumps can contain PII, secrets, and every record currently being processed.** Write them only to protected storage with adequate capacity, permissions, and retention. Never automatically upload production heap dumps to public locations for debugging.

## 16. Distinguishing Large Chunks from Cross-Chunk Memory Leaks

An anti-pattern:

~~~java
public class LeakyProcessor
        implements ItemProcessor<RawOrder, ProcessedOrder> {

    private final List<RawOrder> seen = new ArrayList<>();

    @Override
    public ProcessedOrder process(RawOrder item) {
        seen.add(item);
        return convert(item);
    }
}
~~~

If the processor is a singleton, the `seen` `List` retains every item for the lifetime of the job/JVM. Even if you cut chunk size from 1,000 to 10, memory still grows linearly with total records.

Similar cases:

- Unbounded `Map` caches without eviction.
- `static` collections left in for debugging.
- Listeners storing every event in RAM.
- `ThreadLocal`s holding objects/payloads without clearing.
- Executor queues holding many incomplete `Future`s.
- Long-lived `Session`/`EntityManager` instances.
- Writers building one master list of all outputs and writing only at the end of the job.

For leaks, use heap dumps/dominator trees to locate GC roots and retained sizes. If objects are no longer reachable yet heap does not drop immediately, that is not necessarily a leak; observe across multiple GC cycles.

## 17. Recovering After OOM: Checkpoints and Committed Data

Suppose:

~~~text
Chunk 1: COMMITTED
Chunk 2: COMMITTED
Chunk 3: processing/committing
         -> OOM or OOMKilled
~~~

After the incident, you cannot conclude from the last log line alone that chunk 3 rolled back. Possible states include:

- Prior chunks committed and their checkpoints were saved.
- The active chunk rolled back in the DB.
- `COMMIT` succeeded, yet the app lost the response.
- An API/Kafka/file already absorbed side effects outside the DB transaction.
- `JobRepository` metadata never transitioned from `STARTED` to `FAILED`.

Recovery procedure:

1. Pause automatic job retries from the scheduler while state is unclear.
2. Identify `jobExecutionId`, Step, target resources, memory limits, and error type.
3. Inspect `JobRepository`, checkpoints, and committed output; verify old workers/locks are gone.
4. Fix the root cause of OOM: chunk size, cache, JPA, buffers, or concurrency.
5. Ensure an immutable input snapshot and an idempotent writer.
6. Restart the exact `JobInstance` via Spring Batch when eligible.
7. Reconcile output by business keys, not counts alone.
8. Mark output `READY` only after both the job and data checks finish.

Do not add a random identifying `JobParameter` and call it a restart; that creates a new `JobInstance`, may re-read from the start, and risks duplicates. Do not manually `UPDATE` Spring Batch metadata in production DBs without an audited recovery runbook.

### Why Not Catch `OutOfMemoryError` and Continue?

OOM signals severe resource exhaustion in the process. The transaction manager, logging, serialization, and `JobRepository` may lack sufficient memory to proceed safely. Catching `Error` and skipping items like validation errors can leave data inconsistent. Fix the cause, restart the process cleanly, and recover from durable state.

## 18. Testing Memory Behavior and Restartability

Separate two kinds of tests:

**Functional integration tests:** Run a small job with Spring Batch Test and fixed fixture data, verifying `Job COMPLETED` and exact output rows. When injecting a pre-commit chunk failure, restart the same `JobInstance` and assert zero missing or duplicate records.

**Capacity/performance tests:** Run a dedicated process or container with representative memory limits, large datasets, and varied record sizes; measure peak heap/RSS, GC, throughput, and commit latency.

Example integration test skeleton:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.beans.factory.annotation.Autowired;

class ImportOrdersIT {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void processesAllRowsWithBoundedChunks() throws Exception {
        // Test context provides job, isolated DB, 1,001-record input fixture,
        // and JobParameters built by a test helper.
        JobExecution execution =
                jobLauncherTestUtils.launchJob(testParameters());

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        // Assert output contains all 1,001 distinct keys
        // with no missing or unexpected records.
    }
}
~~~

This skeleton requires adding `testParameters()`, `@SpringBatchTest`/`@SpringBootTest`, beans, and fixtures to run. Avoid asserting exact figures like "heap used must be 123 MiB" in routine unit tests: GC/JIT and CI load make those assertions flaky.

### Test Scenarios to Cover

| Scenario | What to prove |
|---|---|
| Small chunks, large input | Stable memory and complete output |
| Gradually increasing chunk size | Clear throughput/peak-heap curve |
| Unusually large items | No OOM, or explicit handling limits |
| Reader loading whole file | Benchmark exposes retained input |
| Processor with cache | Cache does not grow unboundedly |
| JPA with relationships | Entity graphs do not exceed budget |
| Serializing writer | Peak during write is measured |
| Retry/rollback | No broken replay or sustained memory spike |
| Four concurrent workers | Peak memory stays within budget |
| Mid-chunk failure | Accurate checkpoints and idempotent restart |
| Simulated OOMKilled separately | Recovery relies on repository and actual output |

You do not need to force real OOMs in daily CI pipelines. If process-kill fault injection or ambiguous commits need testing, run them in an isolated, controlled test environment with non-production data.

## 19. Runbook for Production Out-of-Memory Incidents

~~~text
Spring Batch OOM / OOMKilled
             |
             v
Identify heap vs. native/container pressure
             |
             +--> Heap peak scales with chunk
             |      -> Shrink chunk and writer buffers
             |
             +--> Heap climbs across chunks
             |      -> Hunt caches/retained references/JPA
             |
             +--> Heap stable, container exceeds limit
                    -> Inspect direct buffers, threads, native memory
             |
             v
Check JobRepository + checkpoints + output
             |
             v
Fix root cause and benchmark with memory headroom
             |
             v
Controlled restart -> reconcile -> READY
~~~

Operational details to capture:

~~~text
event=batch.memory.failure
jobName=importOrdersJob
jobExecutionId=8301
stepName=importOrdersStep
configuredChunkSize=10000
activeWorkers=4
jvmHeapMaxMiB=2048
containerMemoryLimitMiB=3072
failureClass=OutOfMemoryError
recoveryStatus=INVESTIGATING
~~~

Values are illustrative. Never log full item payloads or raw `JobParameters` to debug memory, as logs/traces carry data-leak risks and add memory pressure.

### Quick Diagnostic Questions

| Question | Priority direction |
|---|---|
| Does peak heap scale with chunk size? | Lower commit interval |
| OOM before the first writer call? | Inspect reader and processor |
| Does the reader build a `List` of all input? | Switch to streaming/paging |
| Does the processor keep an unbounded cache? | Bound or drop retention |
| Does JPA context hold many entities? | Projections, paging, flush/clear management |
| Does the writer build JSON/buffers for the whole chunk? | Bound requests/batches, avoid copies |
| Are there many workers/pending `Future`s? | Add backpressure and reduce concurrency |
| Heap not full yet pod OOMKilled? | Check native/direct memory and cgroups |
| `JobRepository` still `STARTED`? | Verify liveness, locks, and recovery |
| Could output already have committed? | Reconcile, use idempotent writer |

## 20. Common Misconceptions

**Treating chunk size as the total records a job can process.** A job can still process millions of items across many small chunks.

**Increasing chunk size to reduce commits without measuring GC.** Oversized chunks can lower throughput via GC pauses, locks, and rollbacks.

**Only raising `-Xmx`.** If code retains the entire input, more heap merely delays failure and can trigger container `OOMKilled`.

**Shrinking chunk size and assuming every memory leak is fixed.** References in static lists, caches, or thread pools remain.

**Equating CSV line size with Java object size.** DTOs, `String`s, entity graphs, and serializer buffers add major overhead.

**Ignoring the JPA persistence context.** Managed entities and snapshots can grow heap across chunks.

**Equating fetch size, page size, and chunk size.** They belong to different I/O and transaction layers.

**Adding workers when heap is already near capacity.** More active chunks multiply in-flight objects.

**Configuring retry/skip for OOM.** It is not a normal item failure; the JVM may lack resources to continue safely.

**Calling `System.gc()` after every chunk.** Forced GC cannot reclaim reachable objects and can introduce long pauses.

**Looking only at JVM heap inside a container.** Native/direct memory and thread stacks count toward container limits too.

**Re-running the job as a new instance without reconciliation.** Risks duplicates, dropped records, or repeated external side effects.

**Leaving heap dumps unprotected.** Dumps can hold sensitive data from every item in flight.

**Benchmarking only on small records.** A handful of huge payloads or retries can spike higher than the happy path.

## 21. Design Principles for Memory-Stable Batch Jobs

To avoid **oversized chunks causing out-of-memory** in Spring Batch:

1. **Choose commit intervals based on item footprint and memory budget**, not raw row counts alone.
2. **Stream or page in readers**, avoiding materializing the entire source.
3. **Keep processors stateless when possible**, never caching every item in collections.
4. **Minimize object graphs**, avoiding unnecessary raw payloads, relationships, or DTOs.
5. **Manage JPA/JDBC/HTTP buffers** at appropriate transaction boundaries.
6. **Bound concurrency, queues, and total in-flight bytes**.
7. **Monitor heap, GC, native memory, container RSS, and chunk duration**.
8. **Benchmark multiple chunk sizes on representative workloads**, leaving headroom.
9. **Design checkpoints and idempotent replay** to recover from OOM/kills.
10. **Protect logs and heap dumps**, never treating sensitive data as ad hoc debug material.

A good chunk size is not the largest number the JVM survives on a lucky run. It is the setting that gives the job **steady throughput, acceptable transaction latency, memory headroom, and accurate data recovery** when volume grows or failures occur. When reader, processor, and writer all bound concurrently retained data, Spring Batch can process massive datasets without keeping the whole dataset on the heap.
