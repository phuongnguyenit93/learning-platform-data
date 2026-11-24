# CPU Usage in Spring Batch Processors

## 1. How Does CPU in `ItemProcessor` Affect Performance?

In Spring Batch Core Processing, a chunk-oriented Step typically reads data with an **ItemReader**, transforms or validates it with an **ItemProcessor**, and writes the results with an **ItemWriter**. When the processor performs heavy per-item computation, it can become the primary bottleneck and dictate the throughput of the entire Job.

Suppose a Step processes **2,000,000 transactions**, and each item consumes an average of **2 ms of CPU** in the processor:

~~~text
2,000,000 items × 2 ms CPU/item
= 4,000,000 ms CPU
= 4,000 CPU seconds
≈ 66.7 CPU minutes on one core
~~~

That covers computation alone—excluding file reading, database access, writing, transactions, garbage collection, or resource waits. Increasing chunk size can trim commit overhead, but it does not reduce the number of operations executed per item.

The goal of this guide is to distinguish **CPU-bound** from **I/O-bound** processors, measure CPU accurately, locate resource-hungry code, optimize algorithms, choose sensible chunk sizes and parallelism, and preserve batch output correctness.

## 2. What Does `ItemProcessor` Do?

Processor contract:

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

For each item, **process** may:

- Return an output object for the writer to persist.
- Return **null** to filter out the item per business rules.
- Throw an exception; the Step may fail, skip, or retry depending on configuration.

~~~text
         ItemReader
             |
             v
      [RawOrder input]
             |
             v
       ItemProcessor
  +------------------------+
  | Normalize strings      |
  | Validate codes         |
  | Parse dates, amounts   |
  | Apply business rules   |
  | Compute, map           |
  +------------------------+
             |
       +-----+------+
       |            |
    output         null
       |            |
   ItemWriter    filterCount
~~~

Common CPU-intensive operations:

| Activity | Potential Cost | What to Check |
| --- | --- | --- |
| Regex validation | CPU, backtracking | Is `Pattern` being compiled repeatedly? |
| JSON/XML parsing | CPU and allocations | Is the same payload parsed multiple times? |
| String normalization | CPU and `String` churn | Are there unnecessary intermediate strings or `replace` calls? |
| DTO mapping | CPU, reflection, allocations | Are objects serialized/deserialized just to map fields? |
| Financial calculations | CPU, `BigDecimal` allocations | Are redundant calculations performed? |
| Hashing, encryption, compression | CPU | Does the algorithm fit the data? |
| Reference lookups | CPU or I/O | In-memory `Set`/`Map` lookup vs. per-item DB query? |
| Per-item logging | CPU, object allocations, I/O | Can log level be lowered or sampled? |

A slow processor is not necessarily consuming heavy CPU: it might simply be waiting on a database or HTTP response.

## 3. Distinguishing CPU Time from Wall-Clock Time

**Wall-clock time** measures actual elapsed time from calling `process` until it returns, including waiting on networks, locks, disk, and thread scheduling. **CPU time** is the time a CPU actually spends executing the thread, as measurable by the JVM/OS.

~~~text
Processor A: continuous computation
Wall time ≈ 100 ms
CPU time  ≈  95 ms

Processor B: external API calls
Wall time ≈ 100 ms
CPU time  ≈   5 ms
I/O wait  ≈  95 ms
~~~

Both show ~100 ms latency, yet require different fixes. Processor A needs faster algorithms or parallelism if CPU headroom exists; Processor B needs fewer round-trips, caching, batched requests, or I/O concurrency.

| Metric | What It Reveals | What It Does Not Prove |
| --- | --- | --- |
| JVM/process CPU usage | CPU used by the whole JVM | That all CPU belongs to the processor |
| Per-thread CPU time | CPU consumed by a single thread | CPU on other threads called indirectly |
| Process wall time | Latency of the processor invocation | That CPU was busy the entire time |
| Allocation rate | Object creation rate | That allocations alone are the bottleneck |
| GC CPU/pauses | Garbage collection cost | That the processor is the root cause |
| Step read/write throughput | Items processed per second | Which piece of code is slow |
| Chunk duration | Total time for one chunk cycle | Isolated processor time |

When overall process CPU is high, use a profiler to pinpoint the responsible threads and stack frames. When CPU is low yet the Step is slow, inspect databases, networks, connection pools, and locks.

## 4. How CPU/Item Affects Throughput

If one item requires **0.5 ms of CPU**, the ideal capacity of a single core dedicated entirely to the processor is:

~~~text
CPU/item = 0.0005 seconds
1 / 0.0005 ≈ 2,000 items / CPU second
~~~

This is not the real throughput of the whole Step, which also includes reading, writing, commits, GC, and other overhead.

You can estimate the minimum CPU time for N items across c genuinely available cores:

~~~text
T_cpu_ideal ≈ N × cpuSecondsPerItem / c
~~~

This formula is an idealized lower bound—not a promise of linear scaling with thread count. Container CPU quotas, locks, sequential readers, and writers are common bottlenecks.

For example, suppose a Step takes 100 seconds: 70 seconds in the processor and 30 seconds elsewhere. If you double processor speed while everything else stays constant:

~~~text
T_new ≈ 70 / 2 + 30 = 65 seconds
Whole-Step speedup ≈ 100 / 65 = 1.54x
~~~

This is the intuition behind **Amdahl's law**: speeding up one component does not speed up the entire system by the same factor.

## 5. Identifying CPU-Bound Work via Observation and Profiling

Before changing code, capture a **baseline**:

- Job/Step duration, `readCount`, `writeCount`, `filterCount`, and items/second.
- Chunk duration p50, p95, and p99.
- Process CPU usage relative to core count and container CPU quota.
- CPU throttling if running in Kubernetes.
- GC time, allocation rate, and heap usage.
- Database query latency, connection pool usage, and lock waits.
- HTTP/API latency if the processor calls external services.

**A `RUNNABLE` thread state does not always mean active CPU execution**. A thread waiting on I/O inside a native call can still report `RUNNABLE`. CPU sampling and thread CPU time distinguish the two reliably.

### Java Flight Recorder

On a JVM supporting **jcmd** and **Java Flight Recorder (JFR)**, capture a profile while the Job is actively processing:

~~~bash
jcmd 12345 JFR.start name=batch-cpu settings=profile duration=120s filename=/tmp/batch-cpu.jfr
~~~

Here **12345** is the JVM PID. Open the JFR file in **Java Mission Control** to inspect CPU samples, allocations, GC, and thread events.

Illustrative call tree:

~~~text
OrderProcessor.process                    70% CPU samples
  normalizeAddress                        28%
    String.replaceAll                     23%
  calculateFees                           24%
    BigDecimal.multiply                   18%
  validateReference                       12%
  mapping                                  6%

Reader, writer, JVM, and other work       30%
~~~

If `normalizeAddress` dominates CPU samples, optimizing that method is far more effective than randomly tweaking chunk size. **Async-profiler** and flame graphs can also locate CPU hotspots, allocations, and lock contention; choose a profiler appropriate for your environment.

Record the JVM version, dataset, CPU configuration, and capture timing. Profiling only during Job startup can show class loading and JIT compilation rather than steady-state workload behavior.

## 6. Measuring Processor Latency with Micrometer

A Micrometer **Timer** measures wall-clock duration; it is great for p50/p95/p99 latency, though it is **not pure CPU time**.

A decorator can wrap the processor:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.batch.item.ItemProcessor;

public final class TimedProcessor<I, O>
        implements ItemProcessor<I, O> {

    private final ItemProcessor<I, O> delegate;
    private final Timer timer;

    public TimedProcessor(
            ItemProcessor<I, O> delegate,
            MeterRegistry registry,
            String job,
            String step) {

        this.delegate = delegate;
        this.timer = Timer.builder("app.batch.processor.duration")
                .description("Wall time per processor invocation")
                .tags("job", job, "step", step)
                .register(registry);
    }

    @Override
    public O process(I item) throws Exception {
        long start = System.nanoTime();

        try {
            return delegate.process(item);
        } finally {
            timer.record(
                    System.nanoTime() - start,
                    TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Wiring the wrapped processor into a Step:

~~~java
ItemProcessor<RawOrder, NormalizedOrder> measured =
        new TimedProcessor<>(
                rawOrderProcessor,
                meterRegistry,
                "importOrdersJob",
                "importOrdersStep");

return new StepBuilder("importOrdersStep", jobRepository)
        .<RawOrder, NormalizedOrder>chunk(500, transactionManager)
        .reader(reader)
        .processor(measured)
        .writer(writer)
        .build();
~~~

Because recording sits in **finally**, the Timer captures invocations that return an output, return **null**, or throw an exception. Under retries, a single item may be measured multiple times because the metric tracks **invocations**, not unique business items.

**Never use `customerId`, `orderId`, UUIDs, or `jobExecutionId` as long-lived metric tags**, as cardinality explodes with every item or execution. Keep those IDs in logs or traces. Across millions of items, per-item instrumentation also adds overhead; consider sampling and measure instrumentation cost.

## 7. Measuring Thread CPU Time with `ThreadMXBean`

Java provides **`ThreadMXBean`** to read the current thread's CPU time on supported platforms.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

public final class ProcessorCpuProbe {

    private final ThreadMXBean bean =
            ManagementFactory.getThreadMXBean();

    public long measureCpuNanos(Runnable operation) {
        if (!bean.isCurrentThreadCpuTimeSupported()
                || !bean.isThreadCpuTimeEnabled()) {
            throw new IllegalStateException(
                    "Thread CPU time unavailable or disabled");
        }

        long before = bean.getCurrentThreadCpuTime();
        operation.run();
        long after = bean.getCurrentThreadCpuTime();

        return after - before;
    }
}
~~~

Measuring an operation:

~~~java
ProcessorCpuProbe probe = new ProcessorCpuProbe();
long nanos = probe.measureCpuNanos(
        () -> normalizationService.normalize(sampleOrder));
~~~

Limitations:

1. Measures CPU only on the **current thread**. If the processor offloads work to a thread pool, helper-thread CPU is excluded.
2. The JVM or OS may not support thread CPU timing, or it may be disabled.
3. Measuring individual tiny items incurs notable overhead; measure batches of items, sample, or use JFR.
4. I/O waits, sleeps, and lock waits are not counted the same way as CPU time.
5. Warm-up, JIT compilation, and background JVM work can skew measurements.

A CPU probe is suited for controlled diagnostics; it does not belong on the production hot path for every item.

## 8. Example: Optimizing a Regex-Bound CPU Processor

Suppose each input carries a customer code, amount, and timestamp. Models:

~~~java
public record RawOrder(
        String orderId,
        String customerCode,
        String amount,
        String occurredAt) {}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        OffsetDateTime occurredAt) {}
~~~

### Implementation with Redundant Work

~~~java
public final class SlowOrderProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    @Override
    public NormalizedOrder process(RawOrder item) {
        String code = item.customerCode()
                .trim()
                .toUpperCase(Locale.ROOT);

        // Recompiles the regex for every item.
        if (!Pattern.compile("[A-Z0-9]{6,20}")
                .matcher(code)
                .matches()) {
            return null;
        }

        BigDecimal amount =
                new BigDecimal(item.amount().trim());

        OffsetDateTime occurredAt =
                OffsetDateTime.parse(item.occurredAt());

        return new NormalizedOrder(
                item.orderId(), code, amount, occurredAt);
    }
}
~~~

### Reusing Immutable Objects

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.batch.item.ItemProcessor;

public final class EfficientOrderProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    private static final Pattern CUSTOMER_CODE =
            Pattern.compile("[A-Z0-9]{6,20}");

    @Override
    public NormalizedOrder process(RawOrder item) {
        String code = item.customerCode()
                .trim()
                .toUpperCase(Locale.ROOT);

        if (!CUSTOMER_CODE.matcher(code).matches()) {
            return null;
        }

        BigDecimal amount =
                new BigDecimal(item.amount().trim());

        OffsetDateTime occurredAt =
                OffsetDateTime.parse(item.occurredAt());

        return new NormalizedOrder(
                item.orderId(), code, amount, occurredAt);
    }
}
~~~

A compiled **`Pattern`** is safe to share across threads. Each call still creates a fresh **`Matcher`** because `Matcher` is stateful and not thread-safe. For `java.time` formatting, share an immutable **`DateTimeFormatter`** instance—unlike mutable **`SimpleDateFormat`**.

Eliminating repeated regex compilation can yield gains, yet you must **benchmark** before claiming specific speedups. On small datasets or writer-bound jobs, the end-to-end difference may be negligible.

Additional optimization ideas:

- Avoid parsing the same payload multiple times across the pipeline.
- Avoid serializing DTOs to JSON and parsing back just to map fields.
- Avoid unnecessary chains of **`replaceAll`** calls.
- Use `Set`/`Map` for repeated reference lookups when data fits safely.
- Eliminate redundant calculations and intermediate objects.
- Preserve exact `BigDecimal` rounding rules in financial calculations.
- Avoid per-item logging unless strictly necessary.

Code optimizations must never alter **filter**, **skip**, output data, or transaction semantics.

## 9. Algorithms and Outlier Inputs

### Regex Backtracking

Patterns with nested quantifiers and ambiguous matches can burn massive CPU on pathological inputs. Across millions of items, even a handful of unusually long strings can spike processor p99 latency.

Best practices:

- Enforce input length limits where business rules permit.
- Write simple, unambiguous regexes.
- Test valid inputs, invalid inputs, and extreme edge cases.
- Use dedicated parsers for complex grammars.
- Verify with a CPU profile that regex matching is actually a hotspot.

### Lookup Data Structure Complexity

If a processor checks whether a code exists in a 100,000-element list:

~~~java
// Searching a List may require a linear scan.
boolean allowed = allowedCodesList.contains(code);
~~~

For a fixed set of codes, a **`HashSet`** dramatically reduces average lookup cost:

~~~java
private final Set<String> allowedCodes =
        Set.copyOf(referenceCodes);

public boolean allowed(String code) {
    return allowedCodes.contains(code);
}
~~~

Consider memory and consistency: if reference data mutates mid-run, items within the same Job could be evaluated against different rule versions. A fixed snapshot per processing cycle is usually cleaner to reason about and test.

### Allocations and GC

Millions of short-lived objects can force the JVM to burn substantial CPU in GC. Frequent culprits are intermediate `String`s, repeated mapping, temporary collections, and parsing JSON into huge object trees.

Use an allocation profiler to find allocation hotspots before optimizing. Never reuse a single mutable output object across items: the writer may retain references and write multiple rows reflecting only the final mutated state.

## 10. Processors Calling Databases or APIs Are I/O-Bound

A processor like this can be slow even with low CPU usage:

~~~java
@Override
public Output process(Input item) {
    Customer customer = repository.findById(item.customerId())
            .orElseThrow();
    return convert(item, customer);
}
~~~

Every item triggers a database query—creating an **N+1 lookup** across large datasets. If each query takes 5 ms wall-clock time, adding CPU cores will not resolve the bottleneck.

Depending on business rules, better approaches include:

- Performing joins/lookups directly in the reader's query.
- Batching queries instead of querying per item.
- Preloading small reference datasets into a `Map`/`Set`.
- Using a bounded cache with explicit refresh/TTL policies.
- Checking indexes, query plans, connection pools, and network latency.
- For HTTP APIs, using batch endpoints and bounding concurrency.

An **unbounded cache** keyed by millions of customer IDs can bloat heap/GC and degrade performance. If cached data can mutate, define clear consistency rules across items and restarts.

## 11. Does Chunk Size Help CPU-Bound Processors?

Simple model:

~~~text
T_total ≈ N × T_cpu_per_item
        + ceil(N / chunkSize) × T_fixed_per_chunk
        + T_other
~~~

Suppose the processor needs **1 ms of CPU/item** across one million items, and fixed per-chunk overhead is ~**10 ms**:

~~~text
Processor CPU cost ≈ 1,000 seconds

Chunk size 100:
  10,000 chunks × 10 ms ≈ 100 seconds overhead

Chunk size 500:
   2,000 chunks × 10 ms ≈  20 seconds overhead
~~~

Increasing chunk size from 100 to 500 cuts ~80 seconds of assumed overhead, yet leaves the 1,000 seconds of computation intact. When processor CPU dominates, optimizing the algorithm is far more impactful.

Oversized chunks also carry costs:

- More items retained in memory per chunk.
- Longer-lived transactions and database locks.
- More items reprocessed on rollback/retry.
- Coarser checkpoints, increasing rework after crashes.
- Progress metrics update only when chunks complete.

Benchmark several chunk sizes on a real workload with identical reader, processor, and writer implementations, then balance throughput, memory, and recovery cost.

## 12. Parallel Processing When CPU Headroom Exists

If profiling confirms the processor is CPU-bound and items are independent, processing multiple chunks concurrently can utilize multiple CPU cores. Spring Batch lets you attach a `TaskExecutor` to a Step:

~~~java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(16);
    executor.setThreadNamePrefix("batch-worker-");
    executor.initialize();
    return executor;
}

@Bean
Step parallelImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawOrder> reader,
        ItemProcessor<RawOrder, NormalizedOrder> processor,
        ItemWriter<NormalizedOrder> writer,
        ThreadPoolTaskExecutor batchTaskExecutor) {

    return new StepBuilder("parallelImportStep", jobRepository)
            .<RawOrder, NormalizedOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(batchTaskExecutor)
            .build();
}
~~~

This snippet demonstrates syntax and is **not production-ready as-is**. Before enabling it, verify:

1. Is the reader thread-safe, and do checkpoints remain valid when chunks finish out of order?
2. Is the processor stateless or restricted to immutable shared state?
3. Does the writer support concurrent chunks with proper transactions and idempotency?
4. Must output order match input order?
5. Can the JDBC pool, `JobRepository`, DB, and CPU quota sustain the added concurrency?
6. Under retries and restarts, do results stay accurate with zero duplicates?

Many cursor/stateful readers are not inherently thread-safe. Wrapping them in `synchronized` does not automatically guarantee accurate checkpoint/restart semantics. **Partitioning by disjoint key ranges** is often a cleaner fit in such architectures.

### Choosing Worker Count

For purely CPU-bound work, start with worker count near the CPU cores actually allocated, then measure. If a container is capped at 2 vCPUs, spawning 16 CPU-bound workers typically increases context switching and contention.

If 80% of runtime is parallelizable, four ideal workers hit a theoretical ceiling of:

~~~text
Speedup <= 1 / (0.2 + 0.8/4)
        = 2.5x
~~~

Sequential sections, I/O, locks, and synchronization overhead keep real speedup below the theoretical bound.

## 13. Processors Must Be Thread-Safe

A singleton processor holding mutable state causes race conditions when a Step uses multiple threads:

~~~java
public class UnsafeProcessor
        implements ItemProcessor<RawOrder, NormalizedOrder> {

    private int processedCount;
    private String lastCode;

    @Override
    public NormalizedOrder process(RawOrder item) {
        processedCount++;
        lastCode = item.customerCode();

        // Transform and return result...
        return ...;
    }
}
~~~

**`processedCount++`** is non-atomic, and **`lastCode`** gets overwritten by competing workers. Never store per-item business state in shared fields.

Safe patterns:

- Keep intermediate variables local to `process`.
- Share immutable **`Pattern`** and **`DateTimeFormatter`** instances.
- Create a fresh `Matcher` per invocation.
- Store read-only reference data in immutable collections.
- If per-`StepExecution` state is needed, use appropriate scoping and verify safety if multiple threads share one `StepExecution`.
- Never write to `ExecutionContext` from multiple threads without a proper checkpointing design.
- Rely on `StepExecution`-managed counters for tracking rather than mutating metadata manually.

**`@StepScope`** scopes a bean to a `StepExecution`, which does not make mutable fields thread-safe when a single `StepExecution` processes multiple chunks concurrently.

## 14. Benchmarking Processor CPU

### Method-Level Benchmarking with JMH

**JMH** handles warm-up, multi-iteration runs, and common JVM/JIT pitfalls. Example:

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
public class OrderProcessorBenchmark {

    private final EfficientOrderProcessor processor =
            new EfficientOrderProcessor();

    private final RawOrder input = new RawOrder(
            "ORD-001",
            " abc12345 ",
            "123.45",
            "2026-11-15T10:30:00Z");

    @Benchmark
    public NormalizedOrder normalize() throws Exception {
        return processor.process(input);
    }
}
~~~

This example assumes the model and processor from above and JMH dependencies/runner setup in the project. For real benchmarks, vary across representative inputs; repeating one constant input benefits artificially from CPU caches and JIT specialization.

JMH measures only the targeted code—excluding transactions, JDBC, writers, and Spring Batch end-to-end overhead.

### Step Integration Benchmarking

A trustworthy experiment should record:

~~~text
dataset_version
processor_version
chunk_size
worker_threads
cpu_limit
read_count / write_count / filter_count / skip_count
duration_seconds
output_items_per_second
processor_wall_p50 / p95 / p99
cpu_seconds_per_item
gc_pause_ms / allocation_rate
rollback_count
database_latency
~~~

Procedure:

1. Fix the dataset, reader, writer, and infrastructure.
2. Warm up appropriately before measuring.
3. Run multiple iterations for each processor version.
4. Compare median, p95, throughput, and CPU time.
5. Change only one primary variable per experiment group.
6. Verify output correctness with zero dropped or duplicate items.
7. Test errors, rollbacks, and restarts if used in production.

Do not hardcode absolute throughput assertions such as "must achieve 10,000 items/sec" as CI pass/fail gates on shared infrastructure unless the benchmark environment is strictly controlled.

## 15. Verifying Correctness After Optimization

After optimizing a processor, confirm output values and filtering rules remain identical.

Unit test example with JUnit 5 and AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class EfficientOrderProcessorTest {

    private final EfficientOrderProcessor processor =
            new EfficientOrderProcessor();

    @Test
    void normalizesValidOrder() throws Exception {
        RawOrder input = new RawOrder(
                "ORD-001",
                " abc12345 ",
                "123.45",
                "2026-11-15T10:30:00Z");

        NormalizedOrder output = processor.process(input);

        assertThat(output).isNotNull();
        assertThat(output.customerCode()).isEqualTo("ABC12345");
        assertThat(output.amount()).isEqualByComparingTo("123.45");
    }

    @Test
    void filtersInvalidCode() throws Exception {
        RawOrder input = new RawOrder(
                "ORD-002",
                "bad!",
                "20.00",
                "2026-11-15T10:30:00Z");

        assertThat(processor.process(input)).isNull();
    }
}
~~~

This test verifies business rules, **not performance**. In integration tests, also assert `BatchStatus`, read/write/filter/skip counts, and target data. For multi-threaded runs, test correctness under concurrent threads within the Step. Across restarts and retries, outputs must remain consistent.

## 16. Common Symptoms and Diagnostic Matrix

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| CPU near quota; processor dominates CPU profile | CPU-heavy algorithm | Optimize hot methods; re-measure CPU/item |
| High CPU and high GC time | Heavy allocations | Capture allocation profile; reduce temporary objects |
| Low CPU, high processor wall p95 | Waiting on DB/API/locks | Measure latency and reduce I/O round-trips |
| High CPU; adding threads fails to boost items/s | CPU saturation or contention | Check CPU quota/throttling, locks, and memory |
| Raising chunk size leaves throughput flat | CPU/item dominates | Optimize processor instead of commit overhead |
| A few items have very high p99 | Regex, parsing, or outlier inputs | Test boundary inputs; profile call stacks |
| Adding logging slows the Job | Per-item logging | Reduce log volume or sample |
| Processor is fast yet Job is slow | Reader, writer, or commits | Measure pipeline stages separately |
| CPU spikes after restart | Retries or re-reading uncheckpointed chunks | Inspect rollbacks and checkpoint behavior |
| Corrupted output after enabling parallelism | Shared mutable state or ordering drift | Make processor stateless; audit reader/writer |

## 17. Workflow for Optimizing Processor CPU

A practical workflow for Spring Batch in production:

**Step 1 — Establish a baseline.** Record Job duration, read/write throughput, processor wall time, CPU usage, GC, and database metrics.

**Step 2 — Confirm the bottleneck.** Use a CPU profiler to distinguish processor computation from threads waiting on I/O or GC.

**Step 3 — Target hotspots.** Focus on methods dominating CPU samples, allocations, or edge-case input handling.

**Step 4 — Make small, targeted improvements.** Eliminate repeated parsing/compilation, choose better data structures, and cut unnecessary work while preserving business rules.

**Step 5 — Re-benchmark.** Using the exact same workload, compare CPU seconds/item, output items/second, wall p95, GC, and memory.

**Step 6 — Verify correctness.** Assert target data, filter/skip counts, exception behavior, and retry/restart results.

**Step 7 — Evaluate concurrency.** Add workers only when CPU headroom exists and reader/processor/writer are safe under concurrency.

**Step 8 — Monitor continuously.** Track processor p95 duration, CPU throttling, throughput, and rollbacks as workloads evolve.

Illustrative dashboard snapshot:

~~~text
Job: importOrdersJob               Status: STARTED
Step: normalizeOrdersStep          Chunk size: 500
StepExecution: 4972

Read count:            80,000
Write count:           77,500
Filter count:           2,500
Rollback count:             0

Output throughput:     3,100 items/s
Processor wall p50:    0.18 ms
Processor wall p95:    0.65 ms
JVM CPU usage:         82% of CPU quota
GC time:               1.5% of elapsed
Chunk duration p95:    190 ms
~~~

These numbers are illustrative only. **82% JVM CPU usage does not mean the processor uses 82% of CPU**; per-thread and call-stack profiling is required to assign blame accurately.

Optimizing **CPU in the processor** requires treating the actual cause: cut CPU/item when computation is slow, cut I/O waits when calling external services, cut allocations when GC steals cycles, and scale concurrency only when the rest of the pipeline can sustain the load. Success is measured by **real throughput, accurate business data, and reliable rollback/restart behavior**—not raw thread counts or CPU percentages.

