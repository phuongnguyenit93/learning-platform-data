# Chunk Memory in Spring Batch

## 1. Purpose and Scope

In Spring Batch, chunk-oriented processing makes it possible to process millions of records without holding the entire dataset in memory. The reader fetches one item at a time, the processor transforms it, the writer writes in groups, and transactions commit at chunk boundaries. However, configuring `chunk(500, transactionManager)` does not mean the Java heap contains only 500 objects: a single item may be a large object graph, and the reader, writer, JDBC driver, Hibernate, caches, retries, and concurrent chunks all maintain their own memory.

This article on **Chunk Memory** is part of the *Performance* chapter in *Spring Batch Core Processing*. The goal is to understand **which objects stay on the heap, for how long, and how memory scales when changing chunk size**. After reading this guide, you will be able to:

- Explain the item lifecycle and memory usage within a chunk.
- Estimate working set size from item size, chunk size, and concurrency.
- Distinguish allocation pressure, retention, GC pressure, and memory leaks.
- Avoid accumulating entire datasets in readers, processors, writers, `ExecutionContext`, or persistence contexts.
- Choose chunk/page/fetch sizes balancing throughput, heap, GC, transactions, and restarts.
- Gather telemetry using Micrometer, JFR, and heap dumps, and design representative benchmarks.
- Handle memory spikes caused by large chunks, high worker counts, outlier records, or native memory.

Primary Java examples use **Java 17, Spring Boot 3.x, and Spring Batch 5.2.x**. Spring Batch 6.x introduces some package and API changes, so check the documentation for your exact version when adapting code.

---

## 2. What Does a Chunk Retain in Memory?

A typical step flow:

```text
Start transaction
        │
        ▼
 ItemReader.read() ───→ Input item / object graph
        │
        ▼
ItemProcessor.process() → Output item / object graph
        │                       │
        └───────────┬───────────┘
                    ▼
        Chunk holds items until
           commit threshold
                    │
                    ▼
       ItemWriter.write(Chunk)
                    │
                    ▼
        Checkpoint / commit
                    │
                    ▼
  Unreferenced objects become
       eligible for GC
                    │
                    ▼
               New chunk
```

The framework has more intricate details around retries, skips, transactions, and checkpoints. This diagram illustrates the **conceptual lifecycle** of data, not every internal call in exact order for all configurations.

### 2.1. Sources of Memory Consumption

| Retention Site | Examples | Scales with Chunk Size? |
|---|---|---|
| Input chunk | List of items read by the reader | Usually yes |
| Output chunk | Items produced by the processor | Usually yes |
| Reader buffer | CSV lines, JDBC fetch buffer, SQL pages, XML/JSON parsers | Can be independent |
| Writer buffer | Line aggregation, JDBC batches, serialization buffers | Usually yes |
| Transaction/retry | Metadata, retry state, callbacks, and related objects | Mechanism-dependent |
| JPA persistence context | Managed entities, proxies, and associations | Depends on page/transaction |
| `ExecutionContext` | Checkpoints and custom state | Not bounded by chunk |
| Bean-level caches | `List`, `Map`, static state, listeners | Not self-bounded |
| Concurrency | Multiple active chunks, partitions, futures, threads | Multiplies working sets |

An `Order` referencing a `Customer`, a `List<OrderLine>`, and numerous strings/`BigDecimal` instances can occupy tens of KiB, even if the raw CSV ID and amount are only a few dozen bytes. The **live reachable object graph** matters far more than the shallow size of a single object.

### 2.2. Why Doesn't Memory Drop Immediately After Commit?

Completing a chunk merely makes unreferenced objects **eligible** for garbage collection. The JVM may retain committed heap space for reuse; `heapUsed` drops when GC actually runs, not necessarily right at a chunk boundary.

If post-GC live heap climbs steadily across thousands of chunks, look for lingering references. Common causes include:

- A reader loading an entire file into a `List<String>`.
- A singleton processor appending items into an unbounded collection.
- A writer buffering records and flushing only at the end of the job.
- A `@StepScope` bean holding a cache across every chunk of a `StepExecution`.
- `ExecutionContext` storing lists of items instead of a compact checkpoint.
- Hibernate/JPA holding onto entities or lazy-loaded graphs.
- Unfinished async tasks/`Future`s retaining references to items.
- Executor queues backing up when producers outpace consumers.

`@StepScope` has a **step** lifecycle, not a **per-chunk** lifecycle. Moving an accumulating processor from singleton scope to step scope only shortens the cache's lifetime to the end of the step; it will not shrink between commits.

---

## 3. Chunk Size, Commit Interval, and Transactions

In Spring Batch 5.2, chunk configuration is typically written as:

```java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Input> reader,
        ItemProcessor<Input, Output> processor,
        ItemWriter<Output> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<Input, Output>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`chunk(500, ...)` generally means the step collects up to 500 **input items** per processing/transaction unit in a basic setup. Do not infer that heap usage is capped at exactly 500 objects. When the processor creates new output objects, both input and output objects can remain alive together; when the processor returns `null`, the item is filtered out and not passed to the writer.

### 3.1. Estimating Footprint

A starting analytical model:

```text
Peak heap ≈
    JVM/Spring baseline heap
  + total working set of active chunks
  + reader page/fetch buffer
  + writer batch/serialization buffer
  + ORM caches and transaction/retry state
  + collections living outside the chunk
  + headroom for allocation and GC
```

For a single chunk:

```text
chunkWorkingSet ≈
    chunkSize × (retainedInputGraph + retainedOutputGraph)
  + retained intermediate data
  + chunk-dependent buffers
```

This is an **estimation formula**, not a Spring Batch internal contract. Some inputs and outputs share objects; some buffers are not owned per chunk; actual peak heap also depends on sampling timing and GC cycles.

Suppose the input graph is ~8 KiB/item and output graph is ~6 KiB/item, coexisting until the writer completes:

| Chunk Size | Estimated Input + Output Footprint |
|---:|---:|
| 100 | ~1.37 MiB |
| 500 | ~6.84 MiB |
| 2,000 | ~27.34 MiB |
| 5,000 | ~68.36 MiB |

If four similar chunks run concurrently, the payload portion alone at chunk size 2,000 approaches 109 MiB—before counting reader, writer, JVM, cache, and thread memory.

For items carrying two copies of a 250 KiB `byte[]`, chunk size 2,000 can retain nearly one GiB in payload data alone. In that situation, stream data, eliminate copies, or split payloads rather than assuming raising heap size is enough.

### 3.2. Small Chunks: Pros and Cons

Advantages:

- Fewer items retained simultaneously.
- Shorter transactions and lock hold durations.
- More frequent checkpoints, aiding restarts on failure.
- Rollbacks typically affect fewer items.
- Reduced heap spikes and GC pressure when items are large.

Costs:

- More frequent commits and metadata updates.
- Higher JDBC/network/transaction overhead.
- Writers may not fully leverage batch inserts or block writes.
- Throughput can drop if fixed per-commit overhead is high.

### 3.3. Large Chunks: Pros and Cons

Advantages:

- Fewer commits.
- Better batch write efficiency and fewer DB round-trips.
- Often higher throughput when items are small and memory is ample.

Risks:

- Retains items and intermediate objects longer.
- Larger transactions, locks, undo logs, and rollback costs.
- Each failure can force reprocessing of more work.
- Under concurrency, peak memory climbs sharply.
- Longer GC pauses when live object counts grow large.

**The optimal chunk size comes from measuring on your specific workload.** No constant like 100, 500, or 1,000 is universally best for every job.

---

## 4. Memory Retained Outside the Chunk: `ItemReader`

### 4.1. Reading an Entire File Before Processing

A high-risk pattern for large files:

```java
List<String> allLines = Files.readAllLines(
        Path.of("/data/orders.csv"),
        StandardCharsets.UTF_8);

// read() pulls elements sequentially from allLines.
```

Even if the step uses `chunk(100)`, all of `allLines` remains in memory until its reference is released. A 10-million-line file does not become streaming just by configuring a commit interval.

For CSV inputs, prefer a line-by-line streaming reader:

```java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding(StandardCharsets.UTF_8.name())
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("id", "amount")
            .fieldSetMapper(fs -> new Order(
                    fs.readLong("id"),
                    fs.readBigDecimal("amount")))
            .build();
}
```

The reader reads one line at a time as the step requests it rather than building an in-memory list of the entire file. Still, an individual oversized line can allocate a huge temporary `String`/array. A single 100 MiB JSON line can cause a spike even at chunk size 1.

### 4.2. JDBC Cursors

`JdbcCursorItemReader` iterates sequentially over a `ResultSet`. Example:

```java
@Bean
JdbcCursorItemReader<Order> jdbcReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<Order>()
            .name("jdbcReader")
            .dataSource(dataSource)
            .sql("select id, amount from orders order by id")
            .rowMapper((rs, rowNum) -> new Order(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")))
            .fetchSize(500)
            .build();
}
```

`fetchSize(500)` is a **hint to the JDBC driver**, not a hard memory cap. Some drivers require specific auto-commit, transaction, or streaming-mode settings; otherwise, the driver may buffer far more rows than expected. Monitor heap usage and consult your actual JDBC driver's documentation.

Cursors can also hold connections open for long periods. Account for timeouts, transactions, restarts, and concurrent source mutations during reading.

### 4.3. JDBC Paging

`JdbcPagingItemReader` fetches one page at a time, typically using memory proportional to page size plus the chunk's objects:

```java
@Bean
JdbcPagingItemReader<Order> pagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {
    return new JdbcPagingItemReaderBuilder<Order>()
            .name("pagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .rowMapper((rs, n) -> new Order(
                    rs.getLong("id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .build();
}
```

`PagingQueryProvider` must use a deterministic sort key so paging and restarts do not unexpectedly drop or duplicate rows. `pageSize` and `chunkSize` are separate knobs:

| `pageSize` | `chunkSize` | What to Observe |
|---:|---:|---|
| 100 | 100 | Page and commit sizes match |
| 1,000 | 100 | How many buffered page items does the reader retain after commit? |
| 100 | 1,000 | Multiple queries executed per chunk |
| 1,000 | 1,000 | How do throughput and peak heap move together? |

Setting a large `pageSize` reduces query count at the expense of a larger working set. There is no rule requiring `pageSize` to equal `chunkSize`.

### 4.4. JPA and Hibernate

JPA entities can remain managed in the persistence context. A page of 500 root entities with deeply accessed eager or lazy associations can pull in thousands or tens of thousands of child entities.

Mitigation approaches:

- Use `JpaPagingItemReader` with an appropriate page size; review documentation on persistence context lifecycle and how the reader detaches entities per page.
- Prefer DTO projections if you only need an ID, amount, and a few fields.
- Avoid loading unused relationship collections.
- Align batch flush/clear behavior with the writer's transaction boundaries.
- Audit first-level and second-level caches.
- Measure the full object graph, not just root entity counts.

**Never call `entityManager.clear()` casually inside a processor**: doing so can detach entities the writer relies on or discard pending modifications. Only flush/clear through well-understood configuration and transaction boundaries.

### 4.5. JSON, XML, and Compressed Data

Loading an entire JSON file into `List<Map<String,Object>>` or building a full XML DOM for huge files defeats chunking. Consider streaming parsers, StAX/event-based readers, or splitting files into smaller resources. For GZIP inputs, remember decompressed payloads can be many times larger than the compressed file size; never estimate heap from compressed bytes on disk.

---

## 5. `ItemProcessor`, Writers, and Memory Retention

### 5.1. Accumulating Processors

An anti-pattern:

```java
@Component
public class CollectingProcessor
        implements ItemProcessor<Order, Order> {

    private final List<Order> allOrders = new ArrayList<>();

    @Override
    public Order process(Order item) {
        allOrders.add(item);
        return item;
    }
}
```

`allOrders` grows with total record count regardless of chunk size. If the processor is a singleton, the collection can even survive across multiple `JobExecution`s. Even with `@StepScope`, the collection stays alive until the step ends.

Stateless alternative:

```java
@Bean
ItemProcessor<Order, Invoice> invoiceProcessor() {
    return order -> new Invoice(
            order.id(),
            order.amount().multiply(new BigDecimal("1.10")));
}
```

If statistics are needed, maintain counters or compact aggregates. If sorting or grouping the entire dataset is required, consider database aggregation, partitioning, disk-backed intermediate stores, or external sorting.

### 5.2. Writers Buffering Output Until Job Completion

Anti-pattern:

```java
public class AccumulatingWriter implements ItemWriter<Invoice> {
    private final List<Invoice> buffered = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Invoice> chunk) {
        buffered.addAll(chunk.getItems());
    }

    public void finishJob() {
        // Only flushes the entire buffer at the end of the job.
    }
}
```

This writer scales memory linearly with total record count, even with a tiny chunk size. With `FlatFileItemWriter` or `JdbcBatchItemWriter`, write chunk by chunk and inspect how the concrete writer flushes, batches, and buffers.

For large output files, write sequentially to a temporary file and publish it upon job completion. For remote APIs, bound in-flight requests and retries. Never accumulate the entire output inside a `StringBuilder` or `ByteArrayOutputStream` until the end of the job.

### 5.3. Allocation Pressure vs. Memory Leaks

A processor creating millions of short-lived objects can force the CPU to spend heavy time in GC even though post-GC live heap stays flat. That is **allocation pressure**.

By contrast, if a `List` retains every item, post-GC live heap climbs continuously with total items read. That is **retention**, or an application memory leak caused by holding references too long.

| Phenomenon | Symptom | Optimization Direction |
|---|---|---|
| High allocation rate | Frequent GC; objects die quickly | Cut copies, avoid round-trip serialization, use lean DTOs |
| High retention | Post-GC baseline climbs steadily | Trace GC roots; find caches/listeners/ORM/futures holding refs |
| Temporary spikes | High peaks returning to baseline | Smaller chunks/batches; cap record or buffer sizes |
| Off-heap growth | RSS rises while Java heap stays flat | Check direct buffers, native libraries, thread stacks, drivers |

Do not call `System.gc()` after every chunk as a workaround: it cannot reclaim live referenced objects and can trigger stop-the-world pauses.

---

## 6. `ExecutionContext` and Checkpoints

Spring Batch's `ExecutionContext` stores restart state: reader position, paging keys, offsets, flags, or small totals. It is serialized and persisted via `JobRepository` at checkpoints.

Avoid writing:

```java
// Storing hundreds of thousands of objects in metadata: very expensive in RAM and I/O.
executionContext.put("processedRows", allRows);
```

Keep checkpoints compact:

```java
executionContext.putLong("lastProcessedOrderId", lastId);
executionContext.putString("businessDate", "2026-11-15");
```

An oversized context can:

- Inflate live heap.
- Slow serialization and deserialization.
- Bloat metadata tables.
- Repeatedly incur heavy I/O costs on frequent commits.
- Cause deserialization failures when types evolve across deployments.

`saveState(false)` is **not** a default memory-tuning trick: depending on the reader/writer, disabling state persistence can break restartability. Fix the root cause of memory retention and keep checkpoints lean while preserving restart semantics.

---

## 7. Example Batch Reading and Writing Chunks with Bounded Memory

Problem: read an orders CSV, compute new totals, and write an output CSV without accumulating all records. The beans below target Spring Batch 5.2.

**Input:**

```csv
id,amount
101,100.00
102,200.50
103,20.00
```

**Output:** produced by `BigDecimal.multiply(new BigDecimal("1.10"))`:

```csv
id,total
101,110.0000
102,220.5500
103,22.0000
```

If business rules require exactly two decimal places, add `setScale(2, RoundingMode...)` explicitly; do not assume scale normalizes automatically.

### 7.1. Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

In production, configure an appropriate DataSource and metadata schema; H2 is only for local testing here.

### 7.2. Complete Configuration

```java
package com.example.batch;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class InvoiceBatchConfig {

    public record Order(long id, BigDecimal amount) {}
    public record Invoice(long id, BigDecimal total) {}

    @Bean
    @StepScope
    public FlatFileItemReader<Order> orderReader(
            @Value("#{jobParameters['inputFile']}") String file) {
        return new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource(file))
                .encoding(StandardCharsets.UTF_8.name())
                .strict(true)
                .linesToSkip(1)
                .delimited()
                .names("id", "amount")
                .fieldSetMapper(fs -> new Order(
                        fs.readLong("id"),
                        fs.readBigDecimal("amount")))
                .build();
    }

    @Bean
    @StepScope
    public FlatFileItemWriter<Invoice> invoiceWriter(
            @Value("#{jobParameters['outputFile']}") String file) {
        return new FlatFileItemWriterBuilder<Invoice>()
                .name("invoiceWriter")
                .resource(new FileSystemResource(file))
                .encoding(StandardCharsets.UTF_8.name())
                .headerCallback(w -> w.write("id,total"))
                .lineAggregator(invoice ->
                        invoice.id() + ","
                        + invoice.total().toPlainString())
                .shouldDeleteIfExists(true)
                .build();
    }

    @Bean
    public Step invoiceStep(
            JobRepository repository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Order> orderReader,
            FlatFileItemWriter<Invoice> invoiceWriter,
            @Value("${app.batch.chunk-size:500}") int chunkSize) {

        if (chunkSize <= 0) {
            throw new IllegalArgumentException("chunkSize must be > 0");
        }

        return new StepBuilder("invoiceStep", repository)
                .<Order, Invoice>chunk(chunkSize, transactionManager)
                .reader(orderReader)
                .processor(order -> new Invoice(
                        order.id(),
                        order.amount().multiply(new BigDecimal("1.10"))))
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    public Job invoiceJob(
            JobRepository repository, Step invoiceStep) {
        return new JobBuilder("invoiceJob", repository)
                .start(invoiceStep)
                .build();
    }
}
```

In `application.yml`:

```yaml
app:
  batch:
    chunk-size: 500

spring:
  batch:
    job:
      enabled: false
```

Why memory stays bounded:

- The reader streams the CSV line by line instead of loading the entire file.
- The processor creates one `Invoice` per `Order` without storing them in a long-lived list.
- The writer writes each chunk to disk rather than buffering until job completion.
- `chunk-size` is externalized for benchmarking without modifying code.
- `@StepScope` resolves resources from `JobParameters` at step runtime.
- Input/output objects are small with no unnecessary object graphs.

`shouldDeleteIfExists(true)` suits fresh single-run demonstrations; design file handling carefully for restarts, appends, or atomic final-file publishing. It does not by itself provide atomicity between files and database transactions.

### 7.3. Launching the Job

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputFile", "/data/orders.csv")
        .addString("outputFile", "/data/invoices.csv")
        .addString("runId", UUID.randomUUID().toString())
        .toJobParameters();

JobExecution execution = jobLauncher.run(invoiceJob, params);
```

A random `runId` creates distinct `JobInstance`s for benchmarking. In production, identifying parameters should reflect business keys like `businessDate` to prevent duplicate runs.

---

## 8. Concurrency Multiplies Working Sets

A single-threaded 500-item chunk may fit comfortably in a 512 MiB heap, while 16 concurrent chunks could exceed it. Watch:

- Number of concurrently active tasks/workers.
- Number of in-flight chunks.
- Per-worker reader pages, transactions, and persistence contexts.
- Writer/driver buffers and connection pools.
- Executor queues holding tasks or `Future`s.
- Other jobs running in the same JVM.

### 8.1. Estimation

Suppose each input/output item pair retains 12 KiB:

```text
chunkSize = 2000

1 chunk  ≈ 2000 × 12 KiB = 23.4 MiB
4 chunks ≈ 93.8 MiB
8 chunks ≈ 187.5 MiB
16 chunks ≈ 375 MiB
```

These figures count only the assumed item graphs. If the JVM already uses 400 MiB at baseline plus reader/ORM buffers, 16 concurrent chunks can leave a 1 GiB heap without sufficient headroom.

### 8.2. Multi-Threaded Steps

Example task executor setup with Spring Batch 5.2:

```java
@Bean
TaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("batch-");
    executor.initialize();
    return executor;
}

@Bean
Step parallelStep(
        JobRepository repository,
        PlatformTransactionManager manager,
        ItemReader<Input> reader,
        ItemProcessor<Input, Output> processor,
        ItemWriter<Output> writer,
        TaskExecutor batchTaskExecutor) {

    return new StepBuilder("parallelStep", repository)
            .<Input, Output>chunk(500, manager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(batchTaskExecutor)
            .build();
}
```

This is a configuration snippet rather than a complete runnable step, as `Input`, `Output`, and related beans must be defined. **Always verify reader/writer thread safety.** Not every Spring Batch reader is safe when multiple workers share a single instance. Synchronized wrappers or partitioning with dedicated readers may be required depending on constraints.

An unbounded or oversized executor queue worsens backlogs, whereas zero queue capacity requires tuning rejection policies, effective parallelism, and dispatch behavior. Threads also consume stack memory and may open separate DB connections.

### 8.3. Partitions and Remote Workers

Partitioning normally creates independent `StepExecution`/reader state per partition. When eight partitions execute inside the same JVM, account for the sum of all eight footprints; across multiple JVMs, enforce per-worker memory limits while remembering that total DB/storage/network load still aggregates.

### 8.4. Async Processors

In async designs, pending `Future`s/tasks retain input graphs. If the producer outpaces the writer, queue/future backlogs grow unboundedly even with a small chunk size. Cap in-flight tasks, queue capacity, timeouts, backpressure, and ordered-result buffers.

---

## 9. JVM Heap and Container Memory

Not all memory lives inside the Java heap.

| Memory Area | Examples | Inside Java Heap? |
|---|---|---|
| Heap | Items, chunks, DTOs, caches, persistence context | Yes |
| Metaspace | Class metadata | No |
| Thread stacks | Worker and GC thread stacks | No |
| Direct / off-heap | NIO buffers, some drivers/clients | No |
| JVM native / JIT | Code cache, GC internals, native libraries | No |
| OS / page cache | Filesystem cache, memory mappings | Not in heap; can count toward container limits |

With a 2 GiB container limit, setting `-Xmx2g` can get the container `OOMKilled` because native memory still needs room. Example heap sizing:

```text
JAVA_TOOL_OPTIONS="-Xms256m -Xmx1024m"
```

Or proportional to container-visible memory:

```text
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0"
```

These values are examples; measure off-heap usage, thread counts, direct buffers, and actual workload behavior before finalizing limits.

Distinguish the failure symptoms:

- `OutOfMemoryError: Java heap space`: exhausted Java heap.
- `OutOfMemoryError: Direct buffer memory`: exhausted direct buffer limit.
- `GC overhead limit exceeded`: GC spending excessive CPU reclaiming tiny space (JDK/GC dependent).
- Kubernetes `OOMKilled` / exit code 137: kernel/container killed process for exceeding memory limits, often with no Java stack trace.

If RSS grows while heap used stays flat, investigate direct, native, and thread memory rather than merely shrinking chunk size.

---

## 10. Measure Instead of Guessing

### 10.1. Metrics to Collect

| Metric | Purpose |
|---|---|
| Heap used, committed, max | Current heap consumption and ceiling |
| Post-GC live heap | Detects long-lived retained data |
| Allocation rate | Detects excessive object churn |
| GC count, pauses, CPU | Quantifies collector latency overhead |
| Container RSS / working set | Tracks true process/container footprint |
| Chunk duration | Spots abnormally slow or large chunks |
| Read/write/filter/skip counts | Confirms pipeline progress |
| Throughput (items/s) | Evaluates overall efficiency |
| JDBC batch/query time | Separates DB time from Java processing |
| Retained object graph | Pinpoints leak references |

### 10.2. Logging Heap After Each Chunk

Example listener for Spring Batch 5.x:

```java
package com.example.batch.monitoring;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.ChunkContext;

public class ChunkHeapLogger implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(ChunkHeapLogger.class);

    private static final long MIB = 1024L * 1024L;

    private final MemoryMXBean memoryBean =
            ManagementFactory.getMemoryMXBean();

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution step =
                context.getStepContext().getStepExecution();

        MemoryUsage heap = memoryBean.getHeapMemoryUsage();

        log.info(
                "step={} read={} write={} heapUsedMiB={} "
                + "heapCommittedMiB={} heapMaxMiB={}",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                heap.getUsed() / MIB,
                heap.getCommitted() / MIB,
                heap.getMax() < 0 ? "unknown"
                        : String.valueOf(heap.getMax() / MIB));
    }
}
```

Registering the listener on the builder:

```java
return new StepBuilder("invoiceStep", repository)
        .<Order, Invoice>chunk(chunkSize, transactionManager)
        .reader(orderReader)
        .processor(invoiceProcessor)
        .writer(invoiceWriter)
        .listener(new ChunkHeapLogger())
        .build();
```

A post-chunk snapshot is **not** an exact peak memory reading for the chunk: temporary objects may already have been collected, `heapUsed` still includes uncollected dead objects, and off-heap memory is excluded. With millions of chunks, avoid logging every chunk due to I/O overhead; sample periodically or rely on aggregated metrics.

### 10.3. Micrometer and Actuator

Illustrative dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Common JVM Prometheus series:

```promql
jvm_memory_used_bytes{area="heap"}
jvm_memory_committed_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
rate(jvm_gc_pause_seconds_sum[5m])
process_resident_memory_bytes
```

Exact names and labels vary by registry and version; inspect your live metrics endpoint. Spring Batch metrics expose job/step/item/chunk timings, but do not automatically report exact retained bytes per chunk.

Do not attach `jobExecutionId` or individual item IDs as metric tags because cardinality grows unboundedly; stick to job name, step name, environment, and other low-cardinality tags.

### 10.4. Java Flight Recorder

JFR profiles allocation hotspots, GC, threads, locks, and I/O:

```text
java -XX:StartFlightRecording=filename=/tmp/batch-memory.jfr,settings=profile,duration=300s -jar app.jar
```

Or on a running JVM:

```text
jcmd <pid> JFR.start name=batch-memory settings=profile duration=300s filename=/tmp/batch-memory.jfr
```

Open recordings in JDK Mission Control. JFR recording incurs modest overhead and disk usage; pick an appropriate duration and environment.

### 10.5. Heap Dumps

```text
jcmd <pid> GC.heap_dump /tmp/batch-heap.hprof
```

Analyze dumps with Eclipse MAT or an equivalent tool, looking for:

- `List`/`Map` structures accumulating millions of items.
- Classes and collections with large retained sizes.
- Paths to GC roots keeping objects alive.
- Unreleased entities/persistence contexts, thread-locals, or `Future`s.
- Object counts after 100 chunks vs. after 10,000 chunks.

Heap dumps can be massive, contain sensitive business data, pause the JVM, and consume disk space. Capture them strictly under proper operational procedures.

### 10.6. Recognizing Sawtooth Patterns vs. Leaks

Normal heap usage rises during allocation and drops after GC:

```text
Heap
 ▲       /|        /|        /|
 │      / |       / |       / |
 │_____/  |______/  |______/  |____
 └───────────────────────────────► time
        GC         GC         GC
```

If the post-GC baseline remains relatively flat, that indicates healthy transient allocation. If the baseline climbs steadily after every GC with record count and heap dumps show retained objects, suspect retention/leaks. Distinguish bounded warm-up/cache growth that plateaus from unbounded growth.

---

## 11. Systematic Chunk Size Benchmarking

A practical benchmark workflow:

1. Prepare a sufficiently large, representative input: average rows, oversized rows, malformed rows, JPA relations, and realistic DB latency.
2. Hold heap, thread count, JVM/GC flags, database, indexes, processor/writer logic, and competing load fixed.
3. Sweep chunk sizes such as 50, 250, 500, 1,000, and 2,000, scaled to item size.
4. Measure total runtime, items/s, peak heap, post-GC live heap, GC pauses, and p95 chunk duration.
5. Repeat runs to filter out cache, JIT, cold-start, and background-load noise.
6. Re-test with production-like concurrency, writer errors/retries, and oversized outlier items.
7. Pick a setting that meets SLAs and throughput targets with healthy memory headroom.

Sample template table to populate with real measurements:

| Chunk | Workers | Items/s | Peak Heap | GC Pause / min | p95 Chunk Duration | Total Time |
|---:|---:|---:|---:|---:|---:|---:|
| 50 | 1 | Measure | Measure | Measure | Measure | Measure |
| 250 | 1 | Measure | Measure | Measure | Measure | Measure |
| 500 | 1 | Measure | Measure | Measure | Measure | Measure |
| 1000 | 1 | Measure | Measure | Measure | Measure | Measure |
| 2000 | 1 | Measure | Measure | Measure | Measure | Measure |
| 500 | 4 | Measure | Measure | Measure | Measure | Measure |

Do not extrapolate from a few hundred test rows to a multi-million-record workload. Reference-retention bugs often become obvious only after running thousands of chunks.

### 11.1. Trade-Off Analysis

If raising chunk size from 250 to 1,000 increases throughput by 8% while tripling peak heap and pushing GC pauses past SLA, the larger setting is not optimal. Conversely, dropping chunk size to 50 merely to minimize heap while exploding commits and DB round-trips is equally counterproductive.

### 11.2. Testing Failure Paths

Include test cases for:

- Reader encountering an abnormally huge record.
- Processor throwing an exception near the end of a chunk.
- Writer failing, rolling back, and retrying.
- Slow source I/O or slow database responses.
- Inputs where 100% of items are filtered out.
- Job restarts from a saved checkpoint.
- Multiple partitions/jobs executing concurrently.
- Production-equivalent container memory limits.

Failure paths allocate exception objects/stack traces, retry buffers, and retain data differently from happy paths.

---

## 12. How Restarts and Fault Tolerance Affect Memory

### 12.1. Checkpoints

Chunk size governs spacing between checkpoints. Larger chunks can force more items to be reprocessed after a crash; smaller chunks generate more commits and metadata writes.

Accurate restarts depend on `ItemStream`, `ExecutionContext`, transactions, and output idempotency. Shrinking chunk size alone never guarantees safe restarts.

### 12.2. Retries and Skips

Fault-tolerant steps may retain or re-read items during retries/skips. If failures occur near the end of a large chunk, memory pressure and rollback work can spike. Configure bounded retry/skip limits so malformed data never loops indefinitely.

If a skip listener stores every failed item:

```java
public class RetainingSkipListener
        implements SkipListener<Order, Invoice> {

    private final List<Order> skipped = new ArrayList<>();

    @Override
    public void onSkipInProcess(Order item, Throwable error) {
        skipped.add(item); // Can grow unboundedly.
    }
}
```

Instead, record summary counts or persist error records to external storage with clear transaction/idempotency rules. Never buffer all error payloads or stack traces in an in-memory collection until the job finishes.

### 12.3. Do Not Optimize Memory by Blindly Disabling Restarts

`saveState(false)` may trim a bit of overhead, but it rarely fixes heap OOMs caused by item retention and can break checkpoint-based restartability. Only disable state persistence when the job is explicitly designed to restart from scratch or uses an alternative verified checkpoint mechanism.

---

## 13. Diagnosing by Symptom

| Symptom | Hypothesis | What to Inspect |
|---|---|---|
| Peak heap rises with chunk size | Input/output items retained per chunk | Measure peak, lower chunk size, compare throughput |
| Heap spikes right after opening reader | Reader loads entire dataset | `readAllLines`, `queryForList`, JSON DOM, driver buffering |
| Post-GC baseline rises with record count | List/cache/ORM retaining objects | Heap dump, GC roots |
| Memory spike inside writer | JDBC batch or serialization buffers | Writer duration, driver buffers, output graph |
| High GC CPU with flat baseline | High allocation rate | JFR allocation profile, string/JSON copies |
| Heap looks fine but container OOMs | Native/direct memory, thread stacks | RSS, container limits, direct buffers |
| OOM only when adding threads | Concurrency × working set | In-flight chunks, queues, thread/connection counts |
| OOM only on a specific input file | Abnormally large record | Max line/object size, parser, decompression |
| Long retry streaks inflate memory | Retry/log/listener holding objects | Fault-tolerance config and error handling |
| Memory only drops at step end | Bean holding state across whole step | Bean fields, caches, `ExecutionContext` |
| Partitions slow overall when adding workers | Saturated DB/IO or GC | CPU, DB locks, latency, GC, throughput |

A practical diagnostic flow:

```text
High job memory
     │
     ├─ Heap or RSS/native?
     │      ├─ Heap → GC/JFR/heap dump
     │      └─ Native → direct/stacks/driver/container
     │
     ├─ Does heap grow per chunk or with total records?
     │      ├─ Per chunk → chunk/item graph/buffer
     │      └─ With total records → cache/list/ORM retention
     │
     ├─ Are multiple chunks running concurrently?
     │      └─ Cap threads/partitions/queues
     │
     └─ Re-measure throughput, GC pauses, and headroom
```

---

## 14. Common Mistakes

| Misconception | Correct Understanding |
|---|---|
| "Chunk 100 holds at most 100 objects" | Each item is an object graph; buffers and outputs coexist |
| "Bigger chunks are always faster" | Throughput trades off against GC, locks, rollbacks, and memory |
| "Shrinking chunk size fixes every OOM" | Readers, processors, or ORMs can retain the entire dataset |
| "`@StepScope` clears state every chunk" | Its lifecycle spans the entire `StepExecution` |
| "`fetchSize` always caps memory" | The JDBC driver decides actual buffering behavior |
| "`pageSize` must always equal `chunkSize`" | They are independent knobs tuned via measurement |
| "`ExecutionContext` is for storing all records" | Keep only compact checkpoints for restart |
| "Calling `System.gc()` fixes memory leaks" | GC cannot free strongly referenced objects |
| "Post-commit `heapUsed` is the chunk's peak" | It is only a single point-in-time snapshot |
| "Set `-Xmx` equal to the container memory limit" | Native, direct buffers, and stacks also need memory |
| "Only test that the job finishes `COMPLETED`" | Verify throughput, heap, GC, output, and restarts |
| "8 workers use the same memory as 1 worker" | Total in-flight working set scales with concurrency |

---

## 15. Practice Exercises

### Exercise 1 — Estimation

An input graph averages 4 KiB, output graph 6 KiB, chunk size 1,000, and 8 chunks run concurrently. Estimate the memory used by input/output graphs, then list what components are omitted from that estimate.

### Exercise 2 — Chunk Benchmarking

Generate a one-million-record input. Run the step with chunk sizes 50, 250, 500, 1,000, and 2,000. Collect total time, throughput, peak heap, GC pauses, and p95 chunk duration. Select an appropriate size from the data.

### Exercise 3 — Reader Retaining All Input

Compare a reader using `Files.readAllLines()` against `FlatFileItemReader` on progressively larger files. Observe live heap before processing begins and after every 100 chunks.

### Exercise 4 — Processor Leak

Write a processor that intentionally stores every item in an `ArrayList`. Use JFR/heap dumps to trace the reference path keeping the list alive; refactor to stateless and re-measure.

### Exercise 5 — JDBC Paging

Test `pageSize=100, 500, 1000` across different chunk sizes. Track SQL query counts, memory, DB waits, and throughput. Explain why page size and chunk size do not have to match.

### Exercise 6 — Concurrency

Run the same job with 1, 4, and 8 workers; measure in-flight chunks, heap, RSS, throughput, and connection pool usage. Identify the inflection point where adding concurrency stops helping.

### Exercise 7 — Retries and Checkpoints

Make the writer fail at the end of a chunk; test retry/rollback at chunk sizes 100 and 1,000. Verify output after restart, checkpoint frequency, and memory cost.

### Exercise 8 — `ExecutionContext`

Compare storing 50,000 objects in `ExecutionContext` versus storing only `lastProcessedId`. Observe context size, metadata write duration, and restart correctness.

### Exercise 9 — Heap and Container Limits

Cap heap at 512 MiB and container at 768 MiB; monitor RSS and `jvm_memory_used_bytes` as threads and driver buffers increase. Distinguish a Java heap OOM from a container `OOMKilled` termination.

---

## 16. References

- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): read/process/write lifecycle and commits.
- [Spring Batch — Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html): configuring commit intervals.
- [Spring Batch — Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers.html): selecting readers and writers.
- [Spring Batch — Database Readers and Writers](https://docs.spring.io/spring-batch/reference/readers-and-writers/database.html): JDBC cursor/paging and JPA.
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`/`update`/`close` and checkpoints.
- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): concurrency and partitioning.
- [Spring Batch — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): monitoring jobs, steps, and chunks.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer and JVM metrics.
- [Java 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): JVM heap usage API.
- [JDK Mission Control](https://openjdk.org/projects/jmc/): analyzing JFR recordings.
- [Java 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JFR and heap dumps.

Chunk memory depends on the **total live object graph retained across the reader, processor, writer, transactions, and caches**, multiplied by the number of concurrently running chunks. Effective optimization requires streaming or paginated reads, avoiding unbounded accumulation, keeping checkpoints compact, and measuring peak heap, GC, throughput, and rollbacks on representative data. Chunk size is an important tuning lever, but it must be chosen alongside your I/O architecture and JVM/container memory limits.
