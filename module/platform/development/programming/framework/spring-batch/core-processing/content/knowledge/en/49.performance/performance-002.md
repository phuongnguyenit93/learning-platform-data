# Reader, Processor, and Writer Latency in Spring Batch

## 1. Understanding Latency Across the Three Stages of a Batch Step

A Spring Batch job may process data accurately yet fail to meet timing requirements: importing 2 million transactions takes 4 hours instead of 20 minutes, records per second is low, or progress stalls for several minutes before continuing. To optimize effectively, you must first know whether time is actually spent in the **reader**, **processor**, or **writer**, and what portion belongs to transactions, checkpoints, the framework, or external systems.

In a chunk-oriented step, the typical flow is:

```text
                      Chunk-oriented Step
                               |
                 +-------------v-------------+
                 | ItemReader.read()         |
                 | fetch one item or null    |
                 +-------------+-------------+
                               |
                 +-------------v-------------+
                 | ItemProcessor.process()   |
                 | transform/filter, or null |
                 +-------------+-------------+
                               |
                 | loop until chunk / EOF    |
                               |
                 +-------------v-------------+
                 | ItemWriter.write(Chunk)   |
                 | write entire output chunk |
                 +-------------+-------------+
                               |
                 +-------------v-------------+
                 | transaction commit,       |
                 | checkpoint, metadata...   |
                 +---------------------------+
```

In a standard synchronous configuration, the reader is called multiple times, each item is processed by the processor, and items are collected into a chunk before the writer is invoked. A chunk may contain fewer items than the chunk size if the processor filters items out or the input reaches EOF.

**Latency** is the time taken for a specific operation to complete. Define that operation before measuring:

- **Reader latency**: time for a single `ItemReader.read()` call to return an item/`null` or throw an exception.
- **Processor latency**: time for a single `ItemProcessor.process(item)` call to return an output/`null` or throw an exception.
- **Writer latency**: time for a single `ItemWriter.write(chunk)` call to process one **chunk**; this is not a per-item measurement.
- **Step wall time**: elapsed time from when the step starts until it finishes, including overhead that the three measurements above may not capture.

The goal of this article is to establish meaningful measurement practices, use those metrics to pinpoint bottlenecks and choose appropriate optimizations, while preserving checkpoints, restartability, and business correctness.

Examples use **Java 17+, Spring Boot 3.x, Spring Batch 5.x, Micrometer, and JUnit 5**. Spring Batch 6.x APIs introduce some changes; when upgrading, check imports and builders against your target version.

---

## 2. How Latency, Throughput, and Total Time Relate

### 2.1. Foundational Concepts

| Term | Meaning | Example Unit |
| --- | --- | --- |
| Reader latency | Duration of one `read()` call | ms/call or ms/item |
| Processor latency | Duration of one `process()` call | ms/call or ms/item |
| Writer latency | Duration of one `write(chunk)` call | ms/chunk |
| Effective writer cost | Writer time divided by written item count, for rough comparison | ms/output item |
| Throughput | Number of items completed per unit of time | items/s |
| End-to-end duration | Time for the entire step/job to finish | s, minutes, hours |
| Queue/wait time | Time spent waiting on connections, locks, threads, network, buffers | ms |
| Tail latency | Unusually slow invocations, typically observed via p95/p99 | ms |

**Do not directly sum the p95 values** of the reader, processor, and writer to infer the step's p95. Each stage's p95 comes from different invocations; summing them does not describe an accurate end-to-end distribution.

### 2.2. Timing Model for a Synchronous Step

Let:

- \(N_r\): number of times the reader is called.
- \(N_p\): number of times the processor is called.
- \(N_w\): number of times the writer is called, usually the number of chunks with output.
- \(\bar t_r\), \(\bar t_p\): mean duration of a single read/process call.
- \(\bar t_w\): mean duration of a single `write(chunk)` call.
- \(T_o\): remaining overhead (transaction commit/rollback, callbacks, checkpointing, scheduling, logging, etc.).

Approximate model in a single-threaded sequential step:

\[
T_{\mathrm{step}} \approx N_r\bar t_r + N_p\bar t_p + N_w\bar t_w + T_o
\]

This is a **diagnostic model**, not a strict equality in all cases. With retries, skips, item filtering, I/O prefetching, or parallel processing, call counts, wait times, and concurrency can cause these quantities to diverge significantly from output item counts.

### 2.3. Bottleneck Calculation Example

Suppose a step processes 10,000 items with chunk size 100, no filtering/skipping, and no retries; illustrative measurements:

| Component | Approximate Calls | Mean | Total Call Time |
| --- | ---: | ---: | ---: |
| Reader | 10,001 (including EOF) | 1.5 ms | ~15 s |
| Processor | 10,000 | 0.3 ms | 3 s |
| Writer | 100 | 40 ms/chunk | 4 s |
| Transaction + framework | — | — | 2 s |
| **Entire step** | — | — | **~24 s** |

Throughput is approximately \(10,000 / 24 \approx 417\) items/s. In this scenario, investigate the reader first because total reader time exceeds both processor and writer time, even though a single writer call takes 40 ms, which is longer than a single reader call.

Do not conclude "the writer is slowest" simply because 40 ms > 1.5 ms: **the measurement units are different**.

### 2.4. Writer Latency per Item Is Only a Normalization

If a 100-item chunk takes 40 ms to write, the approximate average cost is:

\[
40\ \mathrm{ms/chunk}\;/\;100\ \mathrm{items/chunk}
=0.4\ \mathrm{ms/item}
\]

However, this division does not mean each item actually took 0.4 ms to write. The writer may send a single JDBC batch command, wait on a lock, serialize a payload, or flush an entire buffer in bulk. A 1-item chunk and a 100-item chunk can have different fixed costs; therefore, retain **writer latency per chunk, chunk item count, and throughput together**.

---

## 3. Choosing Measurement Boundaries to Avoid Misleading Conclusions

### 3.1. Measurable Boundaries

```text
read() ─┐  measured read latency
        └─> process() ─┐ measured process latency
                       └─> add to chunk
                            ...
                            write(chunk) ─┐ measured writer latency
                                         └─> ItemStream.update()
                                              DB commit
                                              Batch metadata update
                                              Step listener...
```

Measuring tightly around the three methods reveals the time **inside or spent waiting on the delegate calls**, but usually excludes commit time occurring after the writer.

For example, the writer calls `jdbcTemplate.batchUpdate(...)` in 20 ms; afterward, the transaction manager commit takes 300 ms because the database flushes its WAL. A timer wrapping only `writer.write(...)` reports 20 ms while the step remains slow due to commit. Combine transaction/JDBC metrics and step wall time to account for the missing time.

### 3.2. Each Metric Answers a Specific Question

| Question | Where to Measure |
| --- | --- |
| Where is a single read slow? | Around `ItemReader.read()`; internal JDBC/query/network profiling |
| Is the processor CPU-bound or I/O-bound? | Timer around `process()` paired with CPU profiler, network/client metrics |
| How long does writing one chunk take? | Timer around `ItemWriter.write(Chunk)` |
| Are commits slow? | Transaction/JDBC metrics, connection pool, database logs |
| How long does the step take end-to-end? | Step execution duration or wall-clock timer |
| Are retries/rollbacks inflating call counts? | `StepExecution` counts, retry metrics, per-stage errors |
| How many records/s does the job actually deliver? | Successful business records / end-to-end duration |
| Is the batch started late by the scheduler? | Scheduled time vs. actual `JobExecution` start time |

**No single metric represents the entire pipeline.** Examine latency, call counts, throughput, error/rollback counts, and system resources together.

---

## 4. Spring Batch Metadata Is Useful, Not a Profiler

`StepExecution` accumulates operational counters:

```java
StepExecution step = ...;

long read = step.getReadCount();
long write = step.getWriteCount();
long filtered = step.getFilterCount();
long readSkipped = step.getReadSkipCount();
long processSkipped = step.getProcessSkipCount();
long writeSkipped = step.getWriteSkipCount();
long rollback = step.getRollbackCount();
long commits = step.getCommitCount();
```

These counters report **processing outcomes under Spring Batch semantics**, not direct timing samples of `read()`, `process()`, or `write()`. Do not assume `readCount` always equals the exact number of Java method invocations when retries/rollbacks, EOF, or specialized reader mechanics are involved.

In many cases, `StepExecution.getStartTime()` and `getEndTime()` provide metadata start/end timestamps:

```java
import java.time.Duration;

StepExecution step = ...;
if (step.getStartTime() != null &&
    step.getEndTime() != null) {
    Duration duration =
        Duration.between(step.getStartTime(), step.getEndTime());

    System.out.println("Step elapsed = "
        + duration.toMillis() + " ms");
}
```

This calculation is useful for job history and SLA checks. When measuring fine-grained latency inside a Java process, use **`System.nanoTime()`** or a Micrometer `Timer` because it provides monotonic elapsed-time measurement, which is more reliable than `System.currentTimeMillis()` or subtracting low-resolution wall-clock timestamps.

Spring Batch 5.x provides Micrometer/observability integration depending on configuration. Built-in metric names, tags, and stage coverage can vary across minor versions; inspect your application's actual exposed metrics first and add custom timers only for unmet requirements to avoid emitting duplicate timers.

---

## 5. Measuring Latency with Micrometer `Timer`

### 5.1. Dependencies and Registry

In Spring Boot 3.x, Actuator is typically added to manage the Micrometer registry:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Used when exporting Prometheus via Actuator:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Spring Boot configures a `MeterRegistry` based on dependencies and observability settings. In unit tests you can use `SimpleMeterRegistry` without running Prometheus.

### 5.2. Application Timer Utility

A central utility simplifies timing delegate calls:

```java
package example.batch.metrics;

import java.util.concurrent.Callable;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class BatchStageTimer {

    private final MeterRegistry registry;

    public BatchStageTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> T measure(
            String stage,
            Callable<T> operation) throws Exception {

        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return operation.call();
        } catch (Exception exception) {
            outcome = "error";
            throw exception;
        } finally {
            sample.stop(registry.timer(
                "app.batch.stage.latency",
                "stage", stage,
                "outcome", outcome));
        }
    }
}
```

Usage:

```java
InputRow item = timer.measure("reader", delegate::read);

OutputRow output = timer.measure(
    "processor",
    () -> delegate.process(item));

timer.measure("writer", () -> {
    delegate.write(chunk);
    return null;
});
```

**What is recorded:** each `Timer` tracks count and total time; histograms/percentiles depend on configuration. `stage` should belong to a bounded label set: `reader`, `processor`, `writer`. `outcome` contains only `success` and `error` in this example.

A `read()` call returning `null` (EOF) or a `process()` call returning `null` (filtered item) is still a **successful call** for this timer. If you need to distinguish EOF/filtered items, add a separate bounded-tag counter; do not treat them as exceptions.

**Accuracy:** start the sample right before the delegate call and stop it in `finally` so calls throwing exceptions are also recorded. Severe `Error` throwables are not classified as errors by `catch (Exception)` in this example, although `finally` still runs; if you need to observe fatal JVM errors, design explicit handling for them.

### 5.3. Why Not Use a Shared Unsynchronized `StopWatch`?

If you create a single shared `StopWatch` or `startTime` field across all readers/processors/writers, multiple threads or concurrent steps will overwrite each other's timestamps.

A Micrometer `Timer.Sample` is allocated **fresh per invocation**, making it safer for isolating individual call durations. The `Timer`/registry is shared across threads and maintains aggregates. Recording every single item also incurs CPU/allocation cost; for steps with tens of millions of ultra-short calls, measure instrumentation overhead and consider sampling, per-chunk aggregation, or an appropriate profiler.

---

## 6. `ItemReader` Decorator: Measuring While Preserving Checkpoints

### 6.1. Why Not Simply Replace the Reader with a Lambda?

Stateful readers normally implement `ItemStream` so the framework can invoke `open`, `update`, and `close`. If you wrap a reader using a class that implements only `ItemReader` without forwarding `ItemStream`, you can inadvertently drop the delegate's checkpoint/restart logic.

A latency-measuring decorator should:

1. Measure around `read()`.
2. Return the exact item/`null` and propagate exceptions unchanged.
3. Forward `ItemStream` lifecycle callbacks.
4. Be properly registered with the step.

Example:

```java
package example.batch.metrics;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemStream;
import org.springframework.batch.item.ItemStreamReader;

public final class TimedReader<T> implements ItemStreamReader<T> {

    private final ItemReader<T> delegate;
    private final BatchStageTimer timer;

    public TimedReader(
            ItemReader<T> delegate,
            BatchStageTimer timer) {
        this.delegate = delegate;
        this.timer = timer;
    }

    @Override
    public T read() throws Exception {
        return timer.measure("reader", delegate::read);
    }

    @Override
    public void open(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.open(context);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.update(context);
        }
    }

    @Override
    public void close() {
        if (delegate instanceof ItemStream stream) {
            stream.close();
        }
    }
}
```

Because the wrapper implements `ItemStreamReader`, the step manages lifecycle callbacks on the wrapper. When the delegate also implements `ItemStream`, callbacks are forwarded to the delegate. Do not register both the wrapper and the delegate as separate streams if doing so causes `open/update/close` to run twice.

### 6.2. Understanding Latency of Buffered Readers

A `JdbcCursorItemReader` or a reader with a page/fetch buffer may read rows in batches from JDBC while returning one item per call:

```text
read #1   -> fetch 200 rows from JDBC and return 1st item -> 120 ms
read #2   -> serve from buffer                           -> 0.05 ms
read #3   -> serve from buffer                           -> 0.04 ms
...
read #201 -> fetch next batch                            -> 115 ms
```

This is not necessarily a bug: reader call latency exhibits a multimodal distribution due to batched fetching. Inspect **total read time, query count, fetch/page size, network round-trips, and p95/p99** rather than expecting every call to have uniform latency.

---

## 7. `ItemProcessor` Decorator: Measuring Filtered Items Too

A processor may transform an item or return `null` so Spring Batch filters it out. Both paths consume time and should be included in stage latency.

```java
package example.batch.metrics;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemStream;

public final class TimedProcessor<I, O>
        implements ItemProcessor<I, O>, ItemStream {

    private final ItemProcessor<I, O> delegate;
    private final BatchStageTimer timer;

    public TimedProcessor(
            ItemProcessor<I, O> delegate,
            BatchStageTimer timer) {
        this.delegate = delegate;
        this.timer = timer;
    }

    @Override
    public O process(I item) throws Exception {
        return timer.measure(
            "processor",
            () -> delegate.process(item));
    }

    @Override
    public void open(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.open(context);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.update(context);
        }
    }

    @Override
    public void close() {
        if (delegate instanceof ItemStream stream) {
            stream.close();
        }
    }
}
```

Here the wrapper intentionally implements `ItemStream` to forward callbacks if the underlying processor is stateful. When configuring the step, **register the wrapper with `.stream(timedProcessor)`** if you want Spring Batch to invoke the processor's lifecycle callbacks; merely having a processor implement `ItemStream` should not be assumed to auto-register it across every builder style.

This measurement covers validation, mapping, service calls, or queries executed directly by the processor. When the processor returns `null`, the timer still records outcome `success`; use `StepExecution.getFilterCount()` or a dedicated counter to track filtered item counts.

### 7.1. Distinguishing CPU-Bound vs. I/O-Bound Processors

Two processors with the same 4 ms mean can behave very differently:

- Processor A parses/serializes JSON and computes pure functions: primarily consumes CPU and heap.
- Processor B calls an HTTP endpoint to fetch exchange rates per item: primarily waits on network I/O, often exhibiting tail latency and rate-limiting.

For A: use a CPU profiler and allocation profiler, optimize expressions, cache immutable reference data, or batch computations.

For B: avoid per-item network calls whenever possible, preload or batch lookups, use caches with explicit TTLs, and enforce concurrency limits, timeouts, and retries. Increasing threads indiscriminately can push the bottleneck onto the downstream API.

---

## 8. `ItemWriter` Decorator: Measuring per Chunk

In Spring Batch 5.x, `ItemWriter.write` receives a `Chunk<? extends T>`. A single invocation may contain dozens, hundreds, or thousands of output items. Measurements must explicitly state the **call/chunk** unit.

```java
package example.batch.metrics;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;
import org.springframework.batch.item.ItemStreamWriter;
import org.springframework.batch.item.ItemWriter;

public final class TimedWriter<T> implements ItemStreamWriter<T> {

    private final ItemWriter<T> delegate;
    private final BatchStageTimer timer;

    public TimedWriter(
            ItemWriter<T> delegate,
            BatchStageTimer timer) {
        this.delegate = delegate;
        this.timer = timer;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        timer.measure("writer", () -> {
            delegate.write(chunk);
            return null;
        });
    }

    @Override
    public void open(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.open(context);
        }
    }

    @Override
    public void update(ExecutionContext context) {
        if (delegate instanceof ItemStream stream) {
            stream.update(context);
        }
    }

    @Override
    public void close() {
        if (delegate instanceof ItemStream stream) {
            stream.close();
        }
    }
}
```

A `write()` call can return before Spring Batch performs the transaction commit. Therefore, if the writer timer is low while the step remains slow, inspect JDBC transaction metrics, database commits, WAL/fsync, connection pools, and checkpoint updates.

### 8.1. Also Measuring Items per Chunk

If needed, add a `DistributionSummary` to observe the distribution of chunk sizes received by the writer:

```java
DistributionSummary chunkItems =
    DistributionSummary.builder("app.batch.writer.chunk.items")
        .baseUnit("items")
        .register(registry);

chunkItems.record(chunk.size());
```

With Micrometer, `chunk.size()` counts **output items in the writer call**, which may be lower than the configured chunk size if the processor filtered items or input reached EOF. It also does not necessarily equal the number of database rows actually affected by SQL when using upserts or constraints.

When comparing writer latency across deployments, check whether actual chunk sizes changed. A writer taking 60 ms/chunk for 1,000 items can deliver higher throughput than one taking 20 ms/chunk for 10 items.

---

## 9. Integrating the Three Decorators into `StepBuilder`

Assume the application already has business components `ItemReader<InputRow>`, `ItemProcessor<InputRow,OutputRow>`, and `ItemWriter<OutputRow>`; `InputRow`/`OutputRow` are application-defined model classes.

Configuring a Spring Batch 5.x chunk step:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputRow> businessReader,
        ItemProcessor<InputRow, OutputRow> businessProcessor,
        ItemWriter<OutputRow> businessWriter,
        BatchStageTimer stageTimer) {

    TimedReader<InputRow> timedReader =
        new TimedReader<>(businessReader, stageTimer);

    TimedProcessor<InputRow, OutputRow> timedProcessor =
        new TimedProcessor<>(businessProcessor, stageTimer);

    TimedWriter<OutputRow> timedWriter =
        new TimedWriter<>(businessWriter, stageTimer);

    return new StepBuilder("importStep", jobRepository)
        .<InputRow, OutputRow>chunk(100, transactionManager)
        .reader(timedReader)
        .processor(timedProcessor)
        .writer(timedWriter)
        .stream(timedProcessor)
        .build();
}
```

Key points:

- The reader/writer wrappers implement `ItemStreamReader`/`ItemStreamWriter`, allowing the framework to manage their lifecycles accordingly.
- The processor wrapper is explicitly registered via `.stream(timedProcessor)` to support delegates that implement `ItemStream`.
- `chunk(100, transactionManager)` sets a commit interval of 100 for this example; do not assume 100 is always optimal.
- The timers measure delegate invocations without altering return values, exceptions, or `ExecutionContext` contents.
- If the underlying component uses `@StepScope`, ensure the proxy/delegate bean is resolved properly within the active execution scope. Never instantiate a `@StepScope` component arbitrarily outside its active scope.
- If a delegate is already registered via `.stream(delegate)` elsewhere, avoid double registration that triggers duplicate callbacks.

In real projects you may need `@Qualifier` or bean names to distinguish raw readers from timed readers in the application context. Keep import/step and metric names stable across releases for historical comparison.

---

## 10. Observing Metrics via Actuator

### 10.1. YAML Configuration

To expose metrics and Prometheus in a secured observability environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus

  metrics:
    distribution:
      percentiles-histogram:
        app.batch.stage.latency: true
      slo:
        app.batch.stage.latency: 10ms,50ms,100ms,500ms,1s
```

Configuring SLO buckets/histograms increases the number of time series; consider monitoring backend capacity. If the application lacks the Prometheus registry dependency, the `prometheus` endpoint may not appear as expected.

In production environments, expose Actuator endpoints strictly under appropriate authentication and network policies. Never emit sensitive data in meter tags.

### 10.2. Reading Count and Mean

In a test or service:

```java
Timer readerSuccess = registry.get("app.batch.stage.latency")
    .tag("stage", "reader")
    .tag("outcome", "success")
    .timer();

long calls = readerSuccess.count();
double totalSeconds =
    readerSuccess.totalTime(java.util.concurrent.TimeUnit.SECONDS);

double meanMs =
    calls == 0 ? 0.0
        : readerSuccess.mean(java.util.concurrent.TimeUnit.MILLISECONDS);
```

This is the mean of **successful** calls. Read the `error` outcome separately; retries can significantly increase error call counts.

In Prometheus, metric names may be translated from dots to underscores and exposed as `_seconds_count`, `_seconds_sum`, and histogram `_bucket` series according to registry conventions. Do not assume Prometheus metric names match the Java strings verbatim; inspect the actual endpoint output before writing dashboards or queries.

### 10.3. How to Interpret p95 and p99

- **p50**: half of all calls do not exceed this value.
- **p95**: 95% of calls do not exceed this value; highlights the slowest 5% of calls.
- **p99**: helps inspect the tail latency of rare slow calls.
- **mean**: reflects average time consumption but can mask spikes.
- **max**: useful when investigating brief incidents, though volatile and dependent on the measurement window.

With Prometheus histograms, quantiles can be computed using `rate` over a time window. Ensure units are consistent and filter labels match the appropriate stage/job; do not add reader p95, processor p95, and writer p95 to claim an overall step p95.

### 10.4. Which Tags Should You Use?

| Tag | Recommendation | Why |
| --- | --- | --- |
| `stage` | `reader` / `processor` / `writer` | Extremely low cardinality |
| `job.name` | Bounded list of job names | Compare different workloads |
| `step.name` | Bounded list of step names | Pinpoint bottlenecks per step |
| `outcome` | `success` / `error` | Classify failures |
| `environment` | `test` / `staging` / `prod` | Distinguish runtime environments when needed |
| `jobExecutionId` | **Avoid as a meter tag** | Every execution creates new time series |
| `customerId`/`orderId` | **Avoid** | High cardinality and potentially sensitive |
| `inputFilePath` | **Avoid** | Dynamic paths, may leak information |

If a single `BatchStageTimer` shares the registry as shown in the example, consider adding **stable job/step tags configured at the bean/wrapper level**, rather than attaching unique per-item or per-execution IDs.

---

## 11. Interpreting Total Time and Distribution Metrics

Example dashboard for a completed step:

| Metric | Reader | Processor | Writer |
| --- | ---: | ---: | ---: |
| Successful calls | 100,001 | 100,000 | 1,000 |
| Mean per call | 2 ms | 0.2 ms | 18 ms |
| p95 per call | 7 ms | 0.5 ms | 45 ms |
| Total duration of successful calls | ~200 s | ~20 s | ~18 s |
| Error calls | 35 | 0 | 4 |

This is **illustrative** data. Although writer p95 (45 ms) is higher than reader p95 (7 ms), the reader totals ~200 seconds and is likely the primary throughput limiter.

However, investigate the 35 read errors: retries can generate many extra calls. If the retry policy uses backoff, sleep time between attempts is outside `read()`'s timer and can dominate step duration.

### 11.1. Why Total Timer Duration Can Differ from Wall Time

- Transaction commits, rollbacks, checkpoints, and metadata updates are not inside the three timers.
- Step startup/teardown, reader `open/close`, and writer flushes during `close` take separate time.
- Retry backoffs, thread-pool queues, throttling, or lock acquisition may sit outside the wrappers.
- For client libraries doing asynchronous work, a timer around the method may measure **request submission time** rather than remote completion time.
- In multi-threaded steps, summed timer duration across threads can **exceed step wall time**.
- Readers with prefetch/background fetching perform some I/O outside `read()`.
- GC pauses or CPU scheduling can interrupt any stage.

Do not treat the gap between the sum of the three timers and step wall time as "lost time" without knowing whether the pipeline is synchronous or concurrent.

### 11.2. Measuring Wait Time

If the reader waits on a JDBC connection, a timer around `read()` may include connection acquisition. To pinpoint the exact cause, add connection pool metrics such as HikariCP, JDBC spans, database slow query logs, or thread dumps. Similarly, a processor making HTTP calls should monitor HTTP client metrics, timeouts, retries, and downstream latency.

**Stage timers show where slowness manifests; component-specific metrics/profilers show why it is slow.**

---

## 12. Optimizing Reader Latency

### 12.1. SQL Readers

Common issues:

- Queries missing indexes for filter conditions or `ORDER BY`.
- Queries returning too many columns or too many rows per batch.
- N+1 lookups caused by the reader/processor issuing extra SQL per item.
- Inappropriate `fetchSize` or `pageSize`.
- Paging queries using an unstable sort order, causing missed or duplicate items when source data changes.
- Database locks, network round-trips, or connection pool contention.
- Heavy row mapping or deserializing large payloads.

Remediation:

1. Inspect query plans/`EXPLAIN` and slow query logs using production-like data.
2. Choose indexes matching `WHERE`/`ORDER BY`; avoid `SELECT *` when unnecessary.
3. Measure fetch time, rows/query, and waiting connections.
4. Tune `fetchSize`/`pageSize` in controlled increments.
5. For paging, use a unique/stable sort key and handle source mutations according to consistency requirements.
6. If the data source supports it, consider key-range partitioning instead of bottlenecking on a single reader.

`chunk size`, `fetch size`, and `page size` are **three distinct parameters**. `chunk size` defines the transaction/writer boundary; fetch/page size governs reader data retrieval. Do not assume increasing chunk size reduces reader query count.

### 12.2. File Readers

For large CSV/JSON/XML files, latency can stem from:

- Disk or object storage with low I/O throughput.
- Line-by-line decompression and parsing.
- Overly complex encoding, line tokenizers, or mapping/validation.
- Reading files over network shares with high tail latency.
- Many small files incurring repeated open/close overhead.

Measure resource opening, parsing, read buffering, and network download times separately. Proper buffering reduces syscalls at the cost of memory; monitor heap usage and GC as well.

### 12.3. Watch Out for Stateful Readers

Switching readers or wrappers for optimization must preserve `ItemStream.open/update/close` and `ExecutionContext` keys. A faster reader that drops checkpoints can force millions of records to be reprocessed after a failure. Performance and restart correctness must be evaluated together.

---

## 13. Optimizing Processor Latency

### 13.1. CPU-Bound Processors

Examples include computing hashes, parsing JSON, evaluating rule engines, and constructing new objects. When CPU is the bottleneck:

- Use a CPU profiler to locate hotspots in parsing/mapping/validation.
- Avoid re-deserializing the same payload or compiling regexes on every item.
- Cache immutable config/rules at the job/step level when semantics permit.
- Reduce unnecessary allocations, especially large temporary objects and string conversions.
- Monitor GC pauses, heap pressure, and CPU saturation.
- Evaluate vectorization or batch-level processing if the algorithm allows.

**Do not assume adding threads always boosts throughput**: when CPU is already saturated, extra threads can increase context switching and latency.

### 13.2. I/O-Bound Processors

A processor calling HTTP/Redis/SQL per item often suffers from high tail latency. Check:

- Requests per item; can they be replaced with a batch API?
- Timeouts and retries: are slow requests being retried excessively?
- Connection pooling, rate limits, and circuit breakers.
- Caches with bounded TTLs, eviction policies, and consistency guarantees.
- Can small lookup tables be preloaded before the step starts?
- Does the downstream system support idempotency keys and backpressure?

If using async processing, `ItemProcessor` may execute outside the main Step thread; measure the method doing actual work, not just the time to enqueue a future. With `AsyncItemProcessor`/`AsyncItemWriter`, `process()` typically returns a future quickly while transforming on another thread; a stage timer wrapping only the submit call **will not reflect true processing latency** unless it tracks future execution/completion.

### 13.3. Processors Returning `null`

Returning `null` is a valid item-filtering mechanism. If 80% of inputs are filtered out, the writer receives far fewer outputs than read/process calls. When comparing `readCount` to `writeCount`, factor in `filterCount`, skips, and rollbacks instead of mistaking this for "abnormally low writer throughput."

---

## 14. Optimizing Writer Latency

### 14.1. JDBC Writers

Common causes:

- Row-by-row SQL instead of batch updates.
- Network round-trips per item.
- Indexes, foreign keys, or constraint triggers slowing writes.
- Lock contention, deadlocks, and long transaction durations.
- Commit/fsync/WAL bottlenecks.
- Unique key/upsert contention across concurrent jobs.
- Undersized connection pools or time spent waiting to acquire connections.

For JDBC, use `JdbcBatchItemWriter` or appropriate batching. However, jumping chunk size from 100 to 10,000 is not guaranteed to be better: oversized statements, memory pressure, lock duration, and rollback cost can all rise.

### 14.2. File Writers

Key influencing factors:

- Encoding and serialization.
- Buffer size and flush frequency.
- Block-level compression.
- Local filesystem vs. network filesystem.
- Atomic rename/fsync and required durability guarantees.

A file writer can return quickly due to OS buffering while actual disk flushing occurs at checkpoint or close. Combine `write()` timing with flush/close and end-to-end timing to understand true durability overhead.

### 14.3. API-Calling Writers

When writing to an external service, account for batch API size, timeouts, rate limits, idempotency, and retries. Sending 1,000 items in one request saves network round-trips, but increases payload size, timeout risk, and partial-failure blast radius.

In particular, Spring Batch's `JobRepository` transaction does not automatically enlist a remote API in the same transaction. On restart, chunks may be reprocessed, so outputs require deduplication/idempotency by business key.

---

## 15. Data-Driven Chunk Size Tuning

`chunk(size)` determines the maximum number of input items per chunk transaction under default processing. After a read/process cycle, the writer is called with an output chunk and the framework performs checkpoint/commit.

| Chunk Size | Potential Benefits | Costs / Risks |
| --- | --- | --- |
| 10 | Short transactions, few items on rollback, low memory | Many write/commit calls, high overhead |
| 100 | Common moderate baseline | May not be optimal for real workloads |
| 1,000 | Fewer commits and write calls | Higher heap usage, lock duration, rollback cost |
| 10,000 | Can amortize overhead with efficient batch writers | Long, large transactions; timeout risk and memory pressure |

These values are **benchmark candidates**, not fixed recommendations.

### 15.1. Example of Fixed Overhead Impact

Assume a writer has 15 ms/chunk fixed overhead plus 0.05 ms/item:

\[
T_{\mathrm{writer}}(c) \approx 15 + 0.05c\ \mathrm{ms}
\]

At 10 items per chunk, the writer takes ~15.5 ms/chunk, or ~1.55 ms/item. At 100 items, it takes 20 ms/chunk, or 0.20 ms/item. At 1,000 items, it takes 65 ms/chunk, or 0.065 ms/item.

This model is hypothetical to illustrate **amortizing fixed overhead**. In practice, SQL batch limits, network behavior, database constraints, transaction logs, and memory prevent linear scaling forever.

### 15.2. How to Tune Chunk Size

An empirical workflow:

1. Run a baseline with a fixed dataset and environment.
2. Pick candidate sizes such as 20, 100, 500, 1,000, or values suited to your workload.
3. For each size, measure total wall time, writer mean/p95, read/process mean/p95, commit duration, rollbacks, heap/GC, and throughput.
4. Test mid-chunk failures to verify restartability and writer idempotency.
5. Select the size that meets SLA with acceptable resource headroom and recovery reliability.

Do not pick chunk size solely from mean writer latency. A larger chunk size sometimes makes individual writer calls slower while shortening total step duration; other times the opposite happens due to lock contention.

---

## 16. How Retries, Skips, and Rollbacks Skew Latency

### 16.1. Timers Count Invocations, Counters Track Outcomes

When processing an item fails and retries:

```text
process(item 42) attempt 1 -> error, 80 ms
retry backoff                    200 ms
process(item 42) attempt 2 -> error, 70 ms
retry backoff                    400 ms
process(item 42) attempt 3 -> success, 5 ms
```

The custom processor timer records **3 calls** with latencies of 80, 70, and 5 ms; the 600 ms of backoff sits outside those three timer samples. Yet `StepExecution` may ultimately record only one successfully written output item.

Therefore, when latency rises, inspect simultaneously:

- `success/error` timer counts for each stage.
- Retry counts, backoff durations, and exception types (tag error types only if cardinality is bounded).
- `readSkipCount`, `processSkipCount`, `writeSkipCount`.
- `rollbackCount` and `commitCount`.
- End-to-end duration and actual successfully written output items.

### 16.2. Rollbacks Cause Repeated Work

Already read/processed chunks may be reprocessed after a rollback, depending on the reader, transaction, and retry policy. Total method invocations can exceed `readCount`, `writeCount`, or unique business records. When reporting throughput, state whether the numerator is **attempts** or **unique completed records**.

### 16.3. When Tail Timeouts Matter More Than the Mean

If a downstream API usually responds in 5 ms but 1% of requests take 30 seconds, the mean may look acceptable in small test runs. In a batch job processing millions of items, those outliers recur frequently and can break SLAs. p95/p99, timeouts, error rates, and retry policies often matter far more than shaving a Java operation from 1 ms to 0.8 ms.

---

## 17. Parallelism and the Limits of Summing Latency

### 17.1. Single-Threaded Step

In a single-threaded chunk step, read/process/write run largely sequentially. Summing stage call times gives a rough breakdown of bottlenecks and non-stage overhead, subject to the caveats noted earlier.

### 17.2. Multi-Threaded Step

Spring Batch can use a `TaskExecutor` on a step to process chunks concurrently (depending on builder/version mechanics). When doing so:

- Multiple chunks read, process, or write simultaneously.
- Summing timer durations across threads can **exceed step wall time**.
- Stateful readers/writers with shared state may not be thread-safe.
- Item ordering and checkpointing can be harder to guarantee than in single-threaded execution.
- Database contention and connection pool waits can emerge as the new bottleneck.

Do not assume every `ItemReader` is thread-safe. Synchronized wrappers like `SynchronizedItemStreamReader` exist for some cases, but synchronizing the reader can also introduce contention and affect restart/ordering semantics when chunks execute concurrently. Verify reader type and required semantics carefully.

### 17.3. Partitioning and Remote Chunking

When a step is partitioned by key range or file, multiple independent `StepExecutions` run. To compare latency:

- Use bounded-cardinality stage/job/step tags.
- Watch for skew between fast and slow partitions.
- Inspect data skew, partition sizes, and database access patterns.
- Do not rely solely on the average across partitions if one straggler partition prolongs the entire job.

In remote chunking, network, serialization, message broker overhead, queue time, and worker backlog can dominate wall time; timers around local reader/processor/writer will not capture the full picture.

### 17.4. Throughput Behavior Under Concurrency

If work is CPU-bound and cores are available, concurrency can increase items/s until CPU saturates. If work is I/O-bound, higher concurrency can hide wait latency only up to downstream connection limits, rate limits, DB locks, and memory.

**Throughput is not always inversely proportional to single-call latency** when concurrent requests are in flight. Optimizing effectively requires measuring active concurrency, whole-job throughput, and resource limits together.

---

## 18. Designing Benchmarks for Reliable Conclusions

### 18.1. Data and Environment Variables to Control

A meaningful Spring Batch benchmark should record:

- Input item count and record size.
- Filtered/skipped/retried rates.
- Java/JVM, Spring Batch, Spring Boot, and JDBC driver versions.
- Chunk size, reader fetch/page size, DB pool size, and thread count.
- Source dataset and indexes/schema at measurement time.
- CPU cores, RAM, GC settings, disk/network specs, and concurrent load.
- Logging/tracing/metrics configuration.
- Warm-up duration, cold vs. warm cache state, and results across multiple runs.

If Run A reads 100,000 already-cached items while Run B reads 500,000 items from a cold database, comparing mean reader latency between A and B does not prove B's code is slower.

### 18.2. Baseline and Single-Variable Changes

Good experimentation typically follows these steps:

1. Fix dataset and baseline configuration.
2. Measure baseline with full latency/call-count/throughput data.
3. Target the largest bottleneck.
4. Change **one deliberate parameter** (e.g., fetch size or JDBC batching).
5. Re-run multiple times; compare median, tail latency, and total duration.
6. Verify business outputs, memory usage, and restart correctness.
7. Only after obtaining reliable results should you change another parameter.

If you change chunk size, thread count, queries, caching, and timeouts simultaneously, it is hard to tell which change helped or introduced regressions.

### 18.3. Avoiding Out-of-Context Microbenchmarks

A simple processor running in a JUnit loop does not represent a real Batch step with databases, transactions, and GC. To microbenchmark Java code, consider **JMH** for proper JIT warm-up and measurement. If the goal is a 20-minute job SLA, run integration/performance tests on a representative workload.

### 18.4. Where to Place Thresholds

Do not put a JUnit assertion like "reader always under 2 ms" into shared-resource CI and treat it as a functional test. Absolute latency is heavily influenced by VMs, CI load, databases, and networks.

Use dedicated performance regression tests in a controlled environment with statistical thresholds, separate from unit tests that verify instrumentation logic.

---

## 19. Testing Latency Instrumentation

### 19.1. Unit Testing Timers Without Sleeping

Testing `BatchStageTimer` with `SimpleMeterRegistry`:

```java
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BatchStageTimerTest {

    @Test
    void recordsSuccessfulProcessorCall() throws Exception {
        try (SimpleMeterRegistry registry =
                new SimpleMeterRegistry()) {

            BatchStageTimer timer = new BatchStageTimer(registry);

            String result = timer.measure(
                "processor",
                () -> "normalized");

            assertEquals("normalized", result);

            Timer sample = registry.get("app.batch.stage.latency")
                .tag("stage", "processor")
                .tag("outcome", "success")
                .timer();

            assertEquals(1L, sample.count());
            assertTrue(sample.totalTime(
                java.util.concurrent.TimeUnit.NANOSECONDS) >= 0);
        }
    }

    @Test
    void recordsFailureAndPropagatesException() {
        try (SimpleMeterRegistry registry =
                new SimpleMeterRegistry()) {

            BatchStageTimer timer = new BatchStageTimer(registry);

            IllegalStateException thrown = assertThrows(
                IllegalStateException.class,
                () -> timer.measure("writer", () -> {
                    throw new IllegalStateException("database down");
                }));

            assertEquals("database down", thrown.getMessage());

            Timer failures = registry.get("app.batch.stage.latency")
                .tag("stage", "writer")
                .tag("outcome", "error")
                .timer();

            assertEquals(1L, failures.count());
        }
    }
}
```

This test verifies that instrumentation does not alter return values, exceptions still propagate, and the timer records calls. Do not use `Thread.sleep` and assert exact millisecond counts, because timing on CI machines fluctuates.

### 19.2. Integration Testing Around a Spring Batch Step

With a fixture of 5 input items, a pass-through processor, and chunk size 3, a test can:

- Launch the job using `JobLauncherTestUtils.launchJob` against a test repository.
- Assert `BatchStatus.COMPLETED`.
- Assert `StepExecution.getReadCount() == 5` and `getWriteCount() == 5`.
- Query `MeterRegistry` and verify timers exist for reader, processor, and writer.
- Check that successful call counts match the fixture, accounting for the `read()` call that hits EOF.
- Inspect actual output to verify decorators did not corrupt results.
- If the reader/writer implements `ItemStream`, run a failure/restart test to ensure `open/update` are forwarded and checkpoints are preserved.

An integration test against a real DB also catches wiring bugs where a wrapper's lifecycle was accidentally left unregistered with Spring Batch; pure-Java timer unit tests cannot catch this wiring mistake.

### 19.3. Measuring Instrumentation Overhead

For a processor taking only a few microseconds, recording a metric per item can become a noticeable fraction of total runtime. Compare throughput on the same workload with custom metrics toggled on/off or use fixed-rate sampling; avoid attaching dynamic tags per record. For ultra-hot loops, you can time a group of items/chunks and report the mean rather than creating a timer sample per call, while documenting the sampling policy clearly.

---

## 20. Common Bottleneck Signatures

| Observation | Likely Cause | What to Check |
| --- | --- | --- |
| Reader p95 spikes periodically | Fetch/page/database query or network | Query plan, fetch size, connection pool |
| Reader mean is low but step is slow | Commit/metadata/retry/backoff/GC | Step wall time vs. timer sum, DB transactions |
| Processor mean grows with dataset size | CPU or allocations | CPU/heap profiler, rule evaluation |
| Processor p99 rises with traffic | Downstream HTTP/Redis/SQL waiting | Client metrics, rate limits, N+1 queries |
| Writer call latency is high but throughput is good | Writer is writing large chunks | ms/chunk alongside items/chunk |
| Writer is fast but commits are slow | WAL/fsync/locks | Transaction timing, DB logs |
| Speed rises then falls as chunk size grows | Commit overhead drops while locks/heap grow | Compare across multiple chunk sizes |
| Latency rises and throughput stalls when adding threads | Resource saturation or contention | CPU, pool, DB locks, queue depth |
| Processor calls surge after errors | Retries/rollbacks reprocessing items | Retry count, exceptions, step counters |
| Every job starts slowly | Cold start, JIT, caches, resource initialization | Warm-up, `reader.open`, connection setup |
| Timer sum exceeds step wall time | Parallel execution | Concurrency and aggregation |
| High read count but low write count | Filtering/skipping or writer logic | `filterCount`, skip counts, business output |

### 20.1. Step-by-Step Investigation Workflow

Suppose a job processes 5 million items in 90 minutes:

1. Record **job/step wall time** and unique completed items to establish actual throughput.
2. Measure or inspect stage timers for reader, processor, and writer.
3. For the writer, always check items/chunk alongside write call counts.
4. If stage times do not explain wall time, measure commits, backoffs, queues, and thread/connection pools.
5. Use a CPU profiler for CPU-bound work, slow query logs/JDBC spans for DB-bound work, and network metrics for I/O-bound work.
6. Change one setting, run a comparable baseline, and compare p95, throughput, memory, and rollbacks.
7. Re-verify correctness: unique output, checkpoints, and restartability.

An optimization that reduces latency while introducing duplicate records on retry is not a valid batch processing improvement.

---

## 21. Practice Exercises

### Exercise 1 — Compute Stage Contributions

A step has 20,000 input items, 10% filtered out, and chunk size 200. Reader mean is 0.8 ms/call; processor mean is 2 ms/call; writer mean is 30 ms/chunk; transaction overhead is 5 ms/commit.

Requirements: estimate read/process/write calls, total time per stage, and the first area to investigate. Explain why writer call count depends on **output item count** and how estimates can diverge under retries/skips/EOF.

### Exercise 2 — Instrument Without Losing Restartability

Implement `TimedReader<T>` wrapping a reader that implements `ItemStream`. Use a fixture reader that restores its offset in `open` and writes to `ExecutionContext` in `update`.

Requirements: read through the wrapper, save a checkpoint, instantiate a new wrapper/reader pair, and assert that the reader resumes at the exact offset. Also verify read success/error timers.

### Exercise 3 — Distinguish Writer Call vs. Commit Time

Set up `JdbcBatchItemWriter` with chunk sizes 20 and 200. Measure the `write(chunk)` timer, step duration, database transaction timings, and write throughput.

Requirements: explain the case where the writer timer drops while total step duration fails to drop due to commits or locks.

### Exercise 4 — I/O-Bound Processor

Simulate a processor calling an HTTP service that takes 50 ms per item. Measure request counts, p95, throughput, and retries when the service returns 429.

Requirements: propose batch lookups/caching/timeouts, and verify idempotency and the downstream impact of increasing concurrency.

### Exercise 5 — Workload Benchmarking

Prepare a 100,000-record fixture. Test chunk sizes 20, 100, and 500 while keeping the dataset, fetch size, thread count, and pool size constant.

Requirements: build a table of per-stage mean/p95, wall time, throughput, commit count, peak heap, and rollback count. Choose a configuration based on SLA targets and restart reliability.

### Exercise 6 — Measure Custom Metrics Overhead

Write a pure-Java processor performing a very fast mapping operation, and benchmark the batch with and without a per-item Micrometer timer.

Requirements: document the environment, run multiple iterations, and conclude when sampling or per-chunk aggregation should be used.

---

## 22. Summary of Measurement Methodology

When analyzing the performance of a Spring Batch step, keep three metric layers in mind:

1. **Stage call latency** for reader, processor, and writer: measures delegate calls and time distribution. Reader/processor are typically per item; writer is per chunk.
2. **Batch execution metadata**: `readCount`, `writeCount`, `filterCount`, skips, rollbacks, commits, and lifecycle status.
3. **End-to-end and infrastructure**: step wall time, throughput, transaction commits, database/network waits, CPU/GC, and scheduler delays.

Optimize only where measurements point to the dominant time consumer. A slow reader requires inspecting queries/fetching; a slow processor requires separating CPU vs. I/O; a slow writer requires inspecting batch size, transactions, and target systems. Every change must preserve business contracts, idempotency, and restartability.

## 23. References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html).
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html).
- [Spring Batch Reference — Scalability and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html).
- [Spring Batch Reference — ItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-reader.html).
- [Spring Batch Reference — ItemWriter](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-writer.html).
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html).
- [Micrometer Documentation — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
