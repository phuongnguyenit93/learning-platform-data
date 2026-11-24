# GC and Object Allocation in Spring Batch

## 1. Objectives

A Spring Batch job can process millions of records slowly even when SQL queries and business algorithms are relatively simple. Sometimes the cause lies in **object allocation** and **garbage collection (GC)**: every record creates many temporary objects, forcing the JVM to spend CPU allocating, tracking, and reclaiming them. If the job holds references too long, live data grows and GC must work even harder.

Consider an import step processing 5 million CSV lines. Each line becomes an `InputRow`, gets strings sanitized, allocates a new DTO, builds SQL parameters, and writes to the database. If an average of 2 KB of objects is allocated per line, total allocation across one run can reach roughly **10 GB** even though heap size is capped at a few GB. This is not necessarily a memory leak: many objects are short-lived and promptly collected.

This lesson belongs to the **Performance** section of **Spring Batch Core Processing** and focuses on these objectives:

- Understand the heap, object lifecycles, and GC in the Reader → Processor → Writer pipeline.
- Distinguish **allocation rate**, **live retained memory**, **peak heap usage**, and **GC pause time**.
- Identify where objects are heavily allocated or retained too long in chunk-oriented jobs.
- Use GC logs, Java Flight Recorder (JFR), profilers, and Spring Batch counters to diagnose root causes.
- Improve processors, readers, writers, chunk size, concurrency, and state management without corrupting data or breaking restarts.
- Design comparable before/after measurements rather than relying on intuition or a single lucky run.

Examples assume Java 17+, Spring Boot 3.x, and Spring Batch 5.x. Other JVM or Spring Batch versions may differ in GC behavior, observability tools, and configuration APIs.

## 2. Object Allocation and GC: A Mental Model

**Object allocation** is the JVM reserving memory for a new object such as a `String`, `ArrayList`, `BigDecimal`, DTO, array, or library-internal structure. Most ordinary Java objects live on the heap, though the JIT compiler can eliminate physical heap allocation for some via escape analysis and scalar replacement.

**GC** identifies objects no longer reachable from GC roots and reclaims reusable heap space. GC does not immediately destroy an object when it leaves expression scope; collection timing is decided by the collector and heap state.

Illustrative processing flow:

```text
             Data source
                  |
                  v
         ItemReader.read()
            | creates InputRow, String, arrays...
            v
         ItemProcessor.process()
            | creates OutputRow, normalized values...
            v
         Chunk holds up to N output items
            |
            v
         ItemWriter.write(chunk)
            | SQL binding, serialization, buffers...
            v
         Commit chunk / release references
            |
            v
         Unreferenced objects become
         eligible for GC when needed
```

From a performance standpoint, distinguish four quantities:

| Metric | Meaning | Example Issue |
| --- | --- | --- |
| **Allocation rate** | Bytes of objects allocated per second | Continuously creating `String`/DTO objects triggers frequent GC |
| **Live set / retained heap** | Data still referenced and uncollectable | Caches or `ExecutionContext` retain all records |
| **Heap occupancy / peak heap** | Heap consumption over time | Chunks, pages, queues, and caches drive memory peaks high |
| **GC overhead / pauses** | CPU and pause time spent on GC | Job spends time waiting on collection instead of reading/writing data |

A job with a **high allocation rate** is not automatically bad if objects die young and GC handles them efficiently. Conversely, a job with a modest allocation rate can still run out of memory if it appends all records into a collection kept alive for the entire job.

### Allocation Rate Example

Suppose:

- The job processes 20,000 items/second.
- On average, each item allocates 1,500 bytes of heap objects.
- Long-lived retained data stays flat.

Approximate allocation rate:

```text
20,000 items/s × 1,500 bytes/item
    = 30,000,000 bytes/s
    ≈ 30 MB/s (decimal units)
```

If the job runs for 10 minutes, total allocations reach ~18 GB. This **does not mean an 18 GB heap is required**: if most objects die quickly, they are reclaimed repeatedly as the job runs.

By contrast, if the job appends every item into a list kept until the end, the live set grows nearly linearly with record count. Increasing heap size then merely delays running out of memory.

## 3. How JVM GC Impacts Spring Batch

Modern JVMs offer several GC strategies; in Java 17, G1 is the common default on server-class HotSpot configurations. Other collectors such as ZGC or Shenandoah make different trade-offs across pause times, CPU, and memory. Before switching collectors, identify the **actual bottleneck**.

A simplified view of generational heap regions:

```text
            Java Heap
   +----------------------------+
   |     Young / newly          |
   |     allocated objects      |
   |   (typically collected     |
   |     after a short time)    |
   +----------------------------+
   |      Longer-lived          |
   |        objects             |
   |   (caches, state, buffers) |
   +----------------------------+
```

In G1, the heap is divided into regions and collection steps are not simply a full sweep of young then old every cycle. Even so, the **short-lived objects** vs. **long-lived objects** mental model remains useful for understanding allocation pressure and memory retention.

### What Slows a Job Down?

- **Frequent collections:** allocating heavy temporary objects every second forces constant GC cycles.
- **Objects retained across many chunks:** queues, caches, collections, or contexts keeping references inflate the live set.
- **Long pauses:** collectors require pause phases for certain work; big pauses stretch batch runtimes, cause timeouts, or make scheduled runs overlap.
- **Allocation failures / OOM:** running out of allocatable heap, or native memory pressure causing OS/container termination.
- **CPU contention:** GC threads, application threads, and JDBC/network threads compete for CPU; adding threads may not increase throughput.

Heap usage typically rises and falls in a sawtooth pattern as GC reclaims objects. Never diagnose a memory leak merely because heap climbs before each GC cycle. A stronger warning sign is **post-GC retained heap rising continuously across phases of equal workload**, indicating data that should be freed remains referenced.

## 4. Why Spring Batch Easily Allocates Many Objects

Chunk processing allocates many small objects repeatedly:

| Stage | Examples of Allocated Objects | Common Risks |
| --- | --- | --- |
| `ItemReader` | Row DTOs, `String`, arrays, maps, tokens, mapper objects | Repeated parsing; loading entire source into memory |
| `ItemProcessor` | New DTOs, `BigDecimal`, `LocalDate`, normalized strings, regex matchers | Creating formatters/parsers or copying collections per item |
| `ItemWriter` | SQL parameter maps, batch arrays, JSON payloads, HTTP buffers | Buffering whole-job output; building huge JSON trees before sending |
| Chunk infrastructure | Items collected in chunks and retry/error state | Oversized chunks; heavy output objects kept alive longer |
| `ExecutionContext` | Restart state, serialized objects | Storing full item lists/references in context |
| Partitioning / parallel steps | Queues, tasks, partition contexts, connections | Buffers and in-flight items multiply with parallelism |
| Logging / observability | Log strings, stack traces, metric tags, exceptions | Per-item logging, huge payloads, or unnecessary allocations |

In particular, using `ListItemReader` with a multi-million-element list to mimic a production reader holds the entire source in RAM up front. For large datasets, prefer streaming or paginated readers paired with tuned fetch sizes and proper restart state.

### Transient Objects vs. Retained Objects

Example:

```java
public ProcessedRow process(InputRow item) {
    String cleaned = item.name().trim().toUpperCase();
    return new ProcessedRow(item.id(), cleaned);
}
```

Each invocation creates a new object. Yet if the writer persists it and drops references after commit, these objects are short-lived and GC reclaims them efficiently.

By contrast:

```java
private final List<ProcessedRow> allRows = new ArrayList<>();

public void write(Chunk<? extends ProcessedRow> chunk) {
    allRows.addAll(chunk.getItems());
}
```

If the writer is a singleton and this list persists across executions, data is retained indefinitely, inflating heap and leaking state across jobs. In real writers, flush to the target store per chunk instead of accumulating everything in RAM.

## 5. Identifying Allocation Anti-Patterns in Processors

The mistakes below may seem harmless in tiny jobs, but their cost multiplies by record count in large jobs.

### 5.1. Compiling Regexes or Creating Formatters per Item

Allocation-heavy code:

```java
public String normalize(String raw) {
    Pattern pattern = Pattern.compile("[^A-Za-z0-9]");
    String sanitized = pattern.matcher(raw).replaceAll("");
    DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd");
    return sanitized + formatter.format(LocalDate.now());
}
```

This recompiles the regex and constructs a formatter on every call, while also using current wall time so results vary with execution time.

A better approach when patterns and formats are static:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.regex.Pattern;

public final class OrderNormalizer {

    private static final Pattern UNSAFE_CHARS =
        Pattern.compile("[^A-Za-z0-9]");

    private static final DateTimeFormatter DATE_FORMAT =
        DateTimeFormatter.ISO_LOCAL_DATE;

    public String normalize(String raw, LocalDate businessDate) {
        String code =
            UNSAFE_CHARS.matcher(raw).replaceAll("");

        return code + DATE_FORMAT.format(businessDate);
    }
}
```

Compiled `Pattern` and `DateTimeFormatter` instances are immutable and thread-safe to share. `Matcher` is stateful and unsafe to share across threads; creating a `Matcher` per call is appropriate.

If business logic does not need regexes, a direct character loop or dedicated parser can be cheaper, though refactor only when profiling confirms it as a hotspot.

### 5.2. Creating `ObjectMapper` or JSON Parsers per Invocation

Suboptimal:

```java
public Customer parseCustomer(String json) throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.readValue(json, Customer.class);
}
```

When configuration is static, configure a single `ObjectMapper` Spring bean, finalize its setup before use, and reuse it inside the processor:

```java
@Component
public class CustomerProcessor
        implements ItemProcessor<String, Customer> {

    private final ObjectMapper mapper;

    public CustomerProcessor(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Customer process(String item) throws Exception {
        return mapper.readValue(item, Customer.class);
    }
}
```

For huge JSON documents, use a streaming API instead of loading an entire JSON tree into memory. However, do not blindly replace every DTO with a streaming parser: complexity should match measured benefit.

### 5.3. Using `String.format` and Per-Item Logging

Example:

```java
log.info(
    "Processed order {} with amount {}",
    item.id(),
    item.amount()
);
```

At millions of items, emitting millions of log lines can burn more CPU, I/O, and memory than business processing itself. Prefer chunk/step summary metrics and log failing items selectively. Use SLF4J placeholders for necessary logs; avoid `String.format(...)` or expensive string concatenation regardless of whether the log level is enabled.

If detailed logging is mandatory, evaluate logging backend throughput and async appender queues. Unbounded log queues can also create heap pressure.

### 5.4. Copying Collections Repeatedly and Unnecessary Wrappers

Example:

```java
List<Order> copy = new ArrayList<>(items);
List<Order> another = new ArrayList<>(copy);
List<Order> result = another.stream().filter(this::valid).toList();
```

A stream pipeline is not inherently slow, but allocating multiple intermediate lists per chunk adds noticeable churn. When profiling flags it, consolidate into a single pass and a properly sized output collection, preserving correctness, ordering, and filter rules.

**Never "optimize" by reusing a single mutable DTO across all items.** Since a chunk holds references to multiple items, every slot can end up pointing to the same object overwritten by the latest read—causing subtle data corruption. Guarantee per-item independence and thread safety first; optimize allocations safely afterward.

## 6. Example `ItemProcessor` Reducing Unnecessary Allocations

Suppose a CSV source provides payment IDs, amounts, and business dates. The processor normalizes IDs, validates amounts, and parses dates. Reaching "zero allocations" is unnecessary; the goal is allocating only objects required for the result.

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

record RawPayment(
    String paymentId,
    String amountText,
    String businessDateText
) {}

record AcceptedPayment(
    String paymentId,
    BigDecimal amount,
    LocalDate businessDate
) {}

@Component
public class PaymentProcessor
        implements ItemProcessor<RawPayment, AcceptedPayment> {

    private static final DateTimeFormatter DATE_FORMATTER =
        DateTimeFormatter.ISO_LOCAL_DATE;

    private static final BigDecimal ZERO = BigDecimal.ZERO;

    @Override
    public AcceptedPayment process(RawPayment item) {
        // Do not create a new formatter per item.
        String paymentId = item.paymentId().trim();
        BigDecimal amount =
            new BigDecimal(item.amountText().trim());

        // Parsing produces results required for business data.
        LocalDate date =
            LocalDate.parse(item.businessDateText(), DATE_FORMATTER);

        if (paymentId.isEmpty() || amount.compareTo(ZERO) <= 0) {
            return null; // Filter according to this example's policy.
        }

        return new AcceptedPayment(paymentId, amount, date);
    }
}
```

Explanation:

- `DateTimeFormatter` and `BigDecimal.ZERO` are reused.
- Each `AcceptedPayment` is an independent output object; no mutable record is shared across items.
- `trim()` can return the original string when no characters are stripped depending on JDK implementation; no manual extra copy is needed.
- `new BigDecimal(...)` and `LocalDate.parse(...)` are still needed to construct valid business types. Stripping them purely to save allocations risks correctness.
- If amount or date strings are malformed, the processor may throw an exception. Configure skip/retry per business policy rather than assuming all parse errors are transient.
- Returning `null` from the processor filters the item; it does not increment skip counts.

In practice, before tuning the processor, measure whether the bottleneck lies in parsing, the database, or the network. If 90% of job time is spent waiting on the database, shaving a few processor objects will barely move total runtime.

## 7. Chunk Size, Page Size, and Memory

In chunk-oriented processing, Spring Batch collects a batch of items and calls the writer inside a transaction. Example config:

```java
Step step = new StepBuilder("paymentStep", jobRepository)
    .<RawPayment, AcceptedPayment>chunk(200, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .build();
```

**Chunk size** influences:

- How many input/output objects coexist before the writer finishes.
- Writer invocation count and transaction/commit frequency.
- Rollback scope if an error occurs.
- Reader/writer buffer sizes and memory pressure.
- How long transactions hold resources and locks.

Suppose one processed item plus related objects occupies an average of 4 KB on the heap while held in a chunk. Raising chunk size from 100 to 2,000 increases **chunk item memory alone** from roughly 400 KB to 8 MB. This illustrative math excludes inputs, writer buffers, persistence sessions, database drivers, and multiple concurrent chunks.

A rough guiding formula:

```text
Working-set ≈
    active chunks ×
    items / chunk ×
    bytes retained / item
  + reader/page buffer
  + writer/driver buffers
  + state, caches, framework, and other overhead
```

Do not use this formula to compute an exact `-Xmx`: actual footprint depends on object graphs, heap layout, collector behavior, concurrency, and GC timing. It highlights the trend: large chunks paired with many workers multiply memory pressure.

### Small vs. Large Chunk Sizes

| Small Chunks | Large Chunks |
| --- | --- |
| Fewer items coexisting per chunk | Fewer commits |
| Easier to keep peak heap low | Can improve batch write efficiency |
| More commits / writer invocations | Longer transactions and longer object retention |
| Higher transaction overhead | Larger volume of work reprocessed on rollback |

No single chunk size fits every job. Test candidates like 50, 200, 500, and 1,000 on the same dataset and resources, measuring both throughput and heap/GC while verifying business output.

Besides chunk size, `JdbcPagingItemReader` has **page size**, JDBC drivers have **fetch size**, and writers may have **batch size**. These are separate concepts. Coordinating them properly cuts I/O calls while keeping footprint bounded.

## 8. Readers: Do Not Hold the Entire Dataset in Heap

### 8.1. In-Memory Lists

Suitable for small test datasets:

```java
List<Order> allOrders = repository.findAll();
ItemReader<Order> reader = new ListItemReader<>(allOrders);
```

On a multi-million-row table, `findAll()` forces the app to instantiate and retain every entity and collection before Batch even starts processing. This is usually a far more severe **retained heap** problem than temporary allocation overhead.

### 8.2. Cursor / Paging Readers

Common readers for large datasets:

- `JdbcCursorItemReader`: reads via a JDBC `ResultSet`/cursor; manage connections, fetch size, transactions, and restartability.
- `JdbcPagingItemReader`: reads page by page; requires stable, unique sort keys to avoid missing or duplicating rows.
- `JpaPagingItemReader`: pages via JPA; watch entity lifecycles and persistence context management per configuration.
- `FlatFileItemReader`: streams files line by line and maps each record without loading the entire file into a list.
- Custom readers: obey the `ItemReader.read()` contract returning `null` at EOF; manage resources via `ItemStream` when needed.

For JDBC, `fetchSize` is a hint to the driver; actual behavior varies by database, driver, and query mode. Do not blindly set `fetchSize` to huge values without weighing heap and connection lifetimes.

### 8.3. JPA and the Persistence Context

If a processor or writer uses `EntityManager` and keeps entities managed across pages/chunks, the persistence context grows with referenced entities. Depending on reader and transaction setup, manage `clear()`/detachment appropriately so unneeded entities are released. Never call `clear()` carelessly while unflushed changes are pending, as doing so can silently drop updates.

Evaluate **retained heap** and **transaction correctness** together: never trade data integrity for lower memory usage.

## 9. Writers: Batch Writes and Avoiding Output Accumulation

Writers often allocate substantial intermediate objects: SQL parameter maps, bind arrays, JSON payloads, byte buffers, or persistence structures.

When writing to JDBC, consider `JdbcBatchItemWriter` for batch operations:

```java
@Bean
JdbcBatchItemWriter<AcceptedPayment> paymentWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<AcceptedPayment>()
        .dataSource(dataSource)
        .sql("""
             INSERT INTO accepted_payment (
                 payment_id, amount, business_date
             ) VALUES (
                 :paymentId, :amount, :businessDate
             )
             """)
        .beanMapped()
        .build();
}
```

This example assumes the target table exists and `AcceptedPayment` exposes getters/properties recognized by Spring. In real projects, Java records may need property-accessor handling matching your library version; you can use a DTO bean or explicit `itemSqlParameterSourceProvider`. Primary keys, duplicate handling, and transactions must still be designed carefully.

Batch writes often cut database round-trips, yet do not automatically eliminate allocations. Measure overall throughput, memory, and I/O time.

**Avoid buffering all outputs in a writer list until the end of the job**, unless the dataset is genuinely tiny and business logic requires global aggregation. Also avoid unbounded HTTP/JSON buffers assembling massive single requests.

If the writer sends data outside the database transaction, use an idempotency key or outbox pattern because retries/restarts can replay already-sent effects.

## 10. `ExecutionContext` and Long-Lived State

Spring Batch uses `ExecutionContext` to store restart state—such as reader positions, checkpoint counters, or compact status codes. It is not a warehouse for entire inputs or outputs.

Avoid:

```java
executionContext.put("allProcessedRows", allRows);
```

If `allRows` holds millions of DTOs, the heap retains the entire object graph long-term; serializing it to the metadata repository also slows checkpoint writes and can fail.

Store compact state instead:

```java
executionContext.putLong("lastCommittedOrderId", lastId);
executionContext.putString("sourceFileKey", sourceFileKey);
```

Ensure checkpoints match reader mechanics, transactions, and restart policies. Storing `lastId` alone is insufficient if read ordering is unstable or source rows mutate mid-run. With standard Spring Batch readers, prefer built-in state/restart support before inventing custom checkpoints.

Objects stored in fields of singleton components—such as caches, maps, listeners, or writers—are another source of retained heap. Unless shared state is explicitly required, keep components stateless; scope execution-specific state cleanly so it is freed when the execution ends.

## 11. Partitioning and Multithreading Multiply Memory Pressure

Parallel processing raises throughput when neither CPU nor I/O is saturated, though it is not free:

```text
               Manager step
              /     |       \
        Worker 1  Worker 2  Worker 3
          chunk     chunk     chunk
           N         N         N
              \      |       /
                Writer(s)
```

With 8 workers each holding a 500-item chunk and associated buffers, simultaneously live data is dramatically higher than with one worker—plus thread stacks, work queues, database connections, deserialization buffers, state, and executor objects.

Risks include:

- Non-thread-safe readers or writers accessed concurrently.
- Unbounded queues holding unprocessed tasks or items.
- Database connection pools too small for active workers.
- Faster allocation rates driving GC CPU up so net throughput stalls.
- Harder-to-reason-about errors and rollbacks when partitions write to a shared table or file.

Scale concurrency incrementally while measuring **items/s, CPU, GC time, peak heap, and database latency** alongside business correctness. More threads do not automatically mean a faster job.

## 12. Observing GC with JVM Unified Logging

Since JDK 9, HotSpot supports unified logging via `-Xlog`. When investigating performance, enable GC logs over representative runs.

Java 17 example:

```bash
java \
  -Xms512m \
  -Xmx2g \
  -Xlog:gc*,safepoint:file=/var/log/batch/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar batch-app.jar
```

This command targets Unix/container environments; ensure the log directory exists and is writable. Adjust paths for Windows or other platforms. Keep log verbosity sensible so logs do not fill disks or degrade performance.

In GC logs, watch:

- **GC frequency:** how many GC events occur per minute?
- **Pause durations:** how long does each pause stop application threads?
- **Pre/post-GC heap:** does post-collection memory settle back to a stable level?
- **Old-generation pressure:** is long-lived data climbing steadily?
- **Full GC / evacuation failures / allocation failures:** signs of severe memory stress.
- **GC time vs. wall-clock time:** what fraction of runtime is consumed by collection?

Illustrative excerpt:

```text
[12.345s][info][gc] GC(15) Pause Young (Normal) (G1 Evacuation Pause) 850M->310M(2048M) 18.2ms
[13.102s][info][gc] GC(16) Pause Young (Normal) (G1 Evacuation Pause) 860M->315M(2048M) 17.4ms
```

This log shows a young pause reclaiming heap from ~850 MB down to ~310 MB in ~18 ms. Two lines alone cannot judge job health—examine trends over many minutes alongside Spring Batch throughput.

**GC logs do not tell you which line of code allocated the objects.** Use JFR or an allocation profiler to pinpoint allocation-heavy classes and methods.

## 13. Java Flight Recorder (JFR) for Finding Allocation Hotspots

JFR is built into the JVM and captures GC, CPU, and allocation events with configurable, bounded overhead. Capture recordings during a representative processing window.

Starting JFR at launch:

```bash
java \
  -XX:StartFlightRecording=filename=/tmp/batch-profile.jfr,settings=profile,dumponexit=true \
  -jar batch-app.jar
```

Or triggering a 120-second recording on a running JVM via `jcmd`:

```bash
jcmd <pid> JFR.start name=batch-sample settings=profile duration=120s filename=/tmp/batch-profile.jfr
```

Open the file in **JDK Mission Control (JMC)** and inspect:

| Observation Group | Questions to Answer |
| --- | --- |
| Object allocation samples | Which classes allocate most? Which stack traces create them? |
| GC events | Do collection spikes align with slowdowns? |
| CPU profiling | Is CPU spent in parsers, mappers, converters, JDBC, GC, or logging? |
| Thread activity | Are threads waiting on I/O, locks, or running on CPU? |
| Heap/object statistics (when enabled) | Which objects stay retained long-term? |

Not every allocation event is recorded by default; JFR uses sampling to keep overhead low. Hence **sample counts are not exact total allocated object counts**. Focus on relative proportions and top stack traces under consistent capture settings.

If profiling reveals heavy allocations from `Pattern.compile` inside `PaymentProcessor.process()`, reusing a compiled `Pattern` is backed by data. If most allocations come from the JDBC driver or JSON parser, investigate elsewhere.

Additional tools like `async-profiler` can generate **allocation flame graphs** highlighting allocation-heavy call stacks. Heap dumps and class histograms help when investigating retained objects, though they pause the JVM, consume memory, and expose sensitive data—capture them cautiously.

## 14. Correlating GC with Spring Batch Metadata

Do not tune the JVM in isolation. Place GC metrics right beside Spring Batch processing counters.

Fields on `StepExecution`:

- `getReadCount()`: items successfully read according to metadata.
- `getWriteCount()`: items recorded as written by the writer.
- `getFilterCount()`: items for which processor returned `null`.
- `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`: skipped error counts.
- `getCommitCount()`, `getRollbackCount()`: transaction counts.
- Execution start/end timestamps for total duration.

A `StepExecutionListener` can log a summary metric:

```java
import java.time.Duration;
import java.time.LocalDateTime;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchPerformanceListener
        implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchPerformanceListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        LocalDateTime started = step.getStartTime();
        LocalDateTime ended = step.getEndTime();

        Long elapsedMs = null;
        Double itemsPerSecond = null;

        if (started != null && ended != null) {
            long ms = Duration.between(started, ended).toMillis();
            elapsedMs = ms;

            if (ms > 0) {
                itemsPerSecond =
                    step.getReadCount() * 1000.0 / ms;
            }
        }

        log.info(
            "event=batch.step.performance " +
            "jobExecutionId={} step={} status={} " +
            "readCount={} writeCount={} filterCount={} " +
            "skipCount={} rollbackCount={} elapsedMs={} " +
            "itemsPerSecond={}",
            step.getJobExecutionId(),
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getSkipCount(),
            step.getRollbackCount(),
            elapsedMs,
            itemsPerSecond
        );

        return null; // Preserve the step's ExitStatus.
    }
}
```

This `itemsPerSecond` formula uses metadata `readCount`, not physical reader invocation counts. With skips, retries, and rollbacks, those two differ. Label clearly that the metric tracks **metadata items read / StepExecution duration**, not unique business throughput.

When comparing two runs, also capture:

- CPU utilization during the run.
- Allocation rate from profiling or JVM metrics.
- Total GC time and pause distribution.
- Post-GC live heap and peak heap.
- SQL query times, batch write times, and API call counts.
- Actual input and output volumes, plus skips and filters.

If throughput falls while GC time surges, investigate allocations and retention. If GC is quiet while database queries lag, enlarging the heap will not help.

## 15. Heap Tuning and Collector Selection

Common JVM flags:

| Option | Effect | Caveat |
| --- | --- | --- |
| `-Xms` | Initial heap size | Does not fix high allocation rates |
| `-Xmx` | Maximum heap limit | Must leave room for native overhead inside container limits |
| `-XX:MaxRAMPercentage` | Fraction of RAM used for max heap when `-Xmx` is unset | Behavior depends on JVM and container detection |
| `-XX:+UseG1GC` | Selects G1 GC | Solid default for many batch jobs; verify by measurement |
| `-XX:MaxGCPauseMillis=...` | Pause-time goal for supporting collectors | A **hint/target**, not a hard ceiling |
| `-XX:+UseZGC` | Selects ZGC on supported JDKs | Targets ultra-low pauses; trades off CPU, throughput, and memory |

Fixed-heap launch example:

```bash
java -Xms512m -Xmx2g -jar batch-app.jar
```

In memory-capped containers, **`-Xmx` is not the process's total memory consumption**. The JVM also allocates metaspace, thread stacks, code cache, direct buffers, native driver/library memory, and GC structures. In a 2 GB container, setting `-Xmx2g` risks container OOM kills once off-heap memory is added.

Raising `-Xmx` can lower GC frequency while increasing footprint or shifting pause characteristics. Never rely solely on raising heap when millions of objects are being retained in a list. Tune collectors or pause targets **after** gathering data on allocation rate, live set, GC pauses, CPU, and throughput.

**Never call `System.gc()` inside a processor or after every chunk to "clean up garbage."** It is not proper lifecycle management, hurts performance, and cannot free objects that remain strongly referenced.

## 16. Before-and-After Optimization Workflow

A reliable experiment keeps inputs, database, job configuration, and host resources fixed across runs.

### Step 1: Set Measurable Targets

Example:

> A 2-million-row import batch must finish in under 8 minutes on a 4 vCPU / 4 GB RAM container with zero OOMs, exact output accuracy, and GC consuming only a small fraction of runtime.

Exact GC thresholds depend on your SLA and measurements; no universal "good" percentage fits every system.

### Step 2: Run a Baseline

Record:

| Metric | Illustrative Baseline |
| --- | ---: |
| Input | 2,000,000 items |
| Total duration | 640 seconds |
| Throughput | 3,125 items/second |
| Peak heap | 2.6 GB |
| Allocation rate | 180 MB/second |
| Total GC time | 75 seconds |
| Max GC pause | 210 ms |
| Output result | 2,000,000 valid items |

These numbers are **simulated to illustrate reading a report**, not real Spring Batch benchmarks.

### Step 3: Locate Hotspots

Open JFR and inspect allocation stacks, GC events, and CPU profiles. Suppose top allocations come from compiling regexes in the processor and a cache retaining all outputs in the writer. Those require two distinct fixes: the cache causes retained heap; regex compilation causes repeated CPU and allocation churn.

### Step 4: Fix One Group of Causes

For example:

- Compile regexes once and reuse them.
- Write outputs per chunk, removing whole-job output buffering.
- Adjust chunk size from 500 to 200 if measurements show excessive peak heap.
- Leave business algorithms, rounding rules, and skip policies untouched unless necessary.

### Step 5: Re-Measure and Compare

| Metric | Simulated Baseline | Simulated Post-Change |
| --- | ---: | ---: |
| Input | 2,000,000 | 2,000,000 |
| Total duration | 640 s | 440 s |
| Throughput | 3,125 items/s | 4,545 items/s |
| Peak heap | 2.6 GB | 1.3 GB |
| Allocation rate | 180 MB/s | 95 MB/s |
| Total GC time | 75 s | 21 s |
| Valid outputs | 2,000,000 | 2,000,000 |

Run enough iterations to smooth out JIT warm-up, database caches, CPU contention, and environmental noise. For I/O-heavy jobs, always monitor database and downstream load too. A change counts as an improvement only if **business outputs remain exact**, with zero dropped or duplicated items and intact restartability.

## 17. Common Issues and Diagnostic Guide

| Symptom | Likely Cause | Investigation Path |
| --- | --- | --- |
| Very frequent GC with flat post-GC heap | Heavy short-lived allocations | JFR allocation stacks; check parsers, regexes, DTOs, logs |
| Post-GC heap climbs with record count | Long-lived retained objects | Heap dump/dominator tree; check lists, caches, context |
| OOM when raising chunk size | Larger chunk working sets and buffers | Lower chunk size; measure live set and writer buffers |
| OOM when adding threads | Multiple concurrent chunks/pages/queues | Reduce concurrency, bound queues, check connection pools |
| Slow batch with minimal GC | Bottleneck in DB, I/O, or locks | CPU profile, JDBC tracing, I/O latency |
| Frequent long pauses | Heap pressure, retained data, or collector tuning | GC logs/JFR; check Old GC, live set, collector choice |
| Heap looks fine yet container gets killed | Native/direct buffers, thread stacks, container cap | Monitor RSS, native memory, and cgroup limits |
| Reader retains millions of entities | Using `findAll()` or growing persistence context | Switch to streaming/paging; manage `EntityManager` |
| Writer heap grows over time | Buffering whole-job output or unbounded cache | Write per chunk; bound caches |
| Slow first run, fast restarts | JIT warm-up, caches, I/O, differing data | Benchmark repeated runs on identical inputs |
| Heavy logging spikes heap/CPU | Item-level INFO logs, huge async log queues | Aggregate logs, sample, bound log queues |
| Allocation tweak corrupts output | Unsafe reuse of mutable DTOs or buffers | Verify item isolation, thread safety, rollbacks |
| Heavy retries inflate allocations | Repeated item parsing/serialization and stack traces | Profile fault-tolerant paths; compare across retry counts |

## 18. Practice Exercise

Build an `importPaymentsJob` reading from CSV or an H2 table, processing 200,000 valid records, and writing to a target table. Use a chunk-oriented step and a `StepExecutionListener` to capture duration and read/write/filter/skip counts. Use fixed record counts and string lengths so runs remain comparable.

Implement three processor variants:

1. A processor creating a regex and formatter per item.
2. A processor reusing `Pattern` and `DateTimeFormatter` without unnecessary intermediate collections.
3. Same processor as variant 2, paired with a test writer intentionally buffering all output in memory to observe retained-heap growth. Run variant 3 only in a test environment on bounded data to avoid destabilizing your host.

Enable GC logs/JFR and measure throughput, allocation rate, post-GC heap, and total GC time. Test chunk sizes 50, 200, and 1,000; if running multiple workers, isolate the impact of concurrency separately. Finally, verify written database counts, output contents, and restartability after injecting a mid-chunk failure.

When presenting findings, distinguish changes that reduce **allocation rate** from changes that reduce **retained heap**. Explain why cutting allocations may not cut wall-clock time if the job is I/O-bound, and why raising heap cannot rescue an ever-growing collection.

## 19. Conclusion

In Spring Batch, object allocation is a natural byproduct of reading, transforming, and writing each item; GC lets the JVM reuse heap, yet can consume CPU or cause pauses when allocation rates and live sets outpace efficient collection. Effective optimization starts with **measuring the right problem**: GC logs reveal collection behavior, JFR and allocation profilers pinpoint allocation sites, and `StepExecution` metadata reports how much data the job actually processed and how long it took.

High-impact improvements usually include streaming/paging instead of holding full inputs, never buffering all outputs in writers, keeping `ExecutionContext` lean, reusing immutable config/helper objects, and tuning chunk size and concurrency from measurements. Always preserve data correctness, transaction boundaries, and restartability when reducing allocations. The ultimate goal is **steady throughput, bounded memory, and reliable SLA completion**.
