# Evaluating Decoration Overhead With a Very Small Number of Tasks

## 1. Goal and Framing the Problem Properly

In Spring Framework, `TaskDecorator` lets you wrap a `Runnable` callback before the executor runs it. This mechanism is commonly used to propagate context from the submitting thread to a worker (correlation ID/MDC, observation/tracing context), measure execution time, or clean up `ThreadLocal` after the task completes.

For an HTTP/JDBC task taking hundreds of milliseconds, the cost of creating a wrapper and capturing/restoring context may be tiny compared to I/O time. Yet for many tasks doing only a few calculations or reading a variable, scheduling and decoration time can take up a substantial portion of total runtime. Spring's Javadoc for `ContextPropagatingTaskDecorator` also warns that this operation adds overhead and **is not recommended when the application runs a huge number of very tiny tasks**.

The phrase "a very small number of tasks" also raises a measurement pitfall: if you only run **a few tasks** (such as 5 or 20), stopwatch results will be dominated by thread creation, JIT warm-up, GC, and OS noise. Therefore, we must separate **two cases**:

1. **Each task is very short** (*tiny task*), while total task count may be large: you must examine how many times decorator cost repeats and its relative overhead share.
2. **Total task count is very small** (*small sample count*): absolute cost may be negligible, while the benchmark lacks enough samples to conclude a few percent faster or slower.

This lesson presents how to classify costs, preserve exact context semantics, write a Java 17 program for observation and preliminary measurement, use JMH when more reliable numbers are needed, and establish criteria for configuring Spring based on real workloads.

**Rule:** do not conclude "TaskDecorator is slow" or "overhead = X ns" without knowing the task, context, JVM, executor, sample size, warm-up, and measurement methodology. There is no fixed nanosecond figure that applies to every environment.

## 2. Where Does TaskDecorator Run and Which Steps Incur Cost?

A Spring `TaskDecorator` has the basic contract:

```java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
```

This is an illustrative API signature, not a standalone source file. Spring may pass the decorator a callback already wrapped by the framework, not necessarily the exact user-supplied `Runnable`/`Callable`.

Manual context propagation example:

```java
TaskDecorator decorator = task -> {
    String capturedTrace = TRACE_ID.get();  // snapshot on submit thread

    return () -> {
        String previous = TRACE_ID.get();   // worker's existing context
        try {
            if (capturedTrace == null) {
                TRACE_ID.remove();
            } else {
                TRACE_ID.set(capturedTrace);
            }
            task.run();
        } finally {
            if (previous == null) {
                TRACE_ID.remove();
            } else {
                TRACE_ID.set(previous);
            }
        }
    };
};
```

This is an integration snippet with a `ThreadLocal<String>` variable `TRACE_ID` declared in an application class; it is not yet a standalone runnable program. For a single task, the following can happen:

```text
SUBMITTING THREAD                    WORKER THREAD
────────────────────────────────────────────────────────────────
read TRACE_ID
create wrapper / capturedTrace
submit to executor
                 ---- queue / dispatch ---->
                                     read old context
                                     set new context
                                     task.run()
                                     restore/remove context in finally
                                     wrapper returns
```

**Distinct costs to separate:**

| Stage | Types of Cost That May Arise | Location |
| --- | --- | --- |
| Capture context on task submit | `ThreadLocal.get`, snapshot, map copy, allocation | Submitter |
| Create wrapper | Lambda/object holding `Runnable` and context | Typically at decorate/submit time |
| Enqueue task in executor | Pool/queue checks, lock/CAS, contention | Submitter and executor |
| Thread handoff | Scheduler, context switch, cache locality | JVM/OS |
| Restore context | `ThreadLocal.get/set/remove`, scope allocation | Worker |
| Run business work | CPU, I/O, locks, DB, HTTP | Worker |
| Clean up context | `finally` restore/remove, resource cleanup | Worker |
| Monitoring inside decorator | Timer, histogram, log tags, MDC | Worker/caller |
| GC | Memory allocated by wrappers/context snapshots | JVM |

Not all of the items above are caused by the decorator. **Executor scheduling and task queuing exist even without a decorator**. A benchmark must separate total async cost from the **incremental cost** of enabling the decorator.

### Do Not Confuse TaskDecorator With API Invocation Logic

Decorating only wraps a callback to run extra code. It does not make `@Async` more parallel, does not increase pool size, does not guarantee DB connections, and does not make tasks cancellable. With `@Async`, the call must go through a Spring-managed proxy; self-invocation `this.method()` can bypass the async interceptor, causing the test to stop measuring the intended executor.

## 3. Cost Model: Absolute and Relative

For a batch of N tasks, we can write a mental model:

```text
T_batch ≈ T_setup
        + T_submission_and_queue
        + T_worker_execution
        + T_context_capture_and_restore
        + T_metrics/logging
        + T_scheduler_and_GC
        + interaction/contention effects
```

This is a **qualitative model**, not a linear additive formula for each component: steps can overlap across threads and suffer contention. To compare a workload:

```text
ΔT_batch = T_batch(decorated) - T_batch(plain)

Relative (%) = ΔT_batch / T_batch(plain) × 100%
```

Be careful when using the formula above:

- If tasks are very short, `T_context_capture_and_restore` repeats for every task; its relative share can grow substantially.
- If a task waits on DB for 200 ms, decorator overhead may be small in terms of latency, **yet** it still consumes CPU/allocations if requests per second are very high.
- With **N=5**, variance from a single thread creation or JIT compilation can exceed the entire decorator cost. Computing an "80% increase" from a short run does not prove the decorator consistently slows work by 80%.
- If the decorator logs synchronously per task, the cost may come mostly from logger formatting/I/O rather than `ThreadLocal.set` itself. Never compare a logging-enabled branch against a non-logging branch and blame context propagation alone.
- If tasks are short and the queue is saturated, queue waiting can dwarf execution time. You must separate **wait** time, **execution** time, and **total submit-to-complete** time.

Hypothetical example for illustration, **not actual Java/Spring measurements**: a task running 5 µs with 1 µs added overhead sees a ~20% relative increase; a task running 50 ms with that same 1 µs added increases by only ~0.002%. This calculation illustrates the idea that "fixed overhead looms larger when tasks are short", **without** claiming real cost is always 1 µs.

### Why Must Throughput and Latency Be Measured Together?

A decorator may add allocations on the **submit thread** whose final impact shows up as **GC pauses**, or increase worker CPU so queue wait lengthens. Measuring a single task is insufficient to know whether the system loses throughput under high load. Conversely, a high-throughput benchmark does not prove p99 latency of critical requests stays healthy.

## 4. Fair Measurement Conditions Before Writing a Benchmark

To compare "no decorator", "very light wrapper", and "copy/restore context", keep the following identical:

1. **Executor type**: use one fixed thread-pool configuration; do not compare `SimpleAsyncTaskExecutor` spawning new threads against `ThreadPoolTaskExecutor` reusing threads and attribute the entire difference to the decorator.
2. **Task length**: identical work and observable side effects; avoid branches completely eliminated by JIT optimization.
3. **Warm-up**: let JIT and class loading settle before formal measurement, or use JMH.
4. **JVM/host**: same JDK version, heap flags, logging/tracing configuration, CPU limits, and background load.
5. **Sample count**: measure multiple rounds and rotate mode order to reduce bias from cache/JIT/CPU frequency.
6. **Measurement boundaries**: clearly define whether measuring from submit start until all tasks complete, or solely decorate/per-`run()` time.
7. **Observability**: verify all tasks actually finished; use `CountDownLatch`/Future and timeouts, never `Thread.sleep(...)` guesses.
8. **No dropped tasks**: a full queue can reject tasks; if errors are silently ignored, the "fastest" mode might just be the mode doing less work.
9. **No semantic drift**: when disabling context propagation, tasks needing context may fail or use the wrong context. Only drop a decorator if business logic/tracing remains valid.
10. **Allocation tracking**: remember wrappers and snapshots can allocate objects per task; count allocations/GC under high throughput.

**Validity criterion for a measurement:** the difference must exceed natural noise, repeat across rounds/hosts, and be explained in terms of resource usage. Otherwise, the right conclusion is usually **"no significant cost difference observed under the measured conditions"**, not "zero overhead".

## 5. Standalone Java 17 Example: Verify Correct Context Before Measuring Performance

Before comparing speed, verify the decorator **preserves semantics**. The code below is a standalone JDK 17 program needing neither Maven nor Spring. It creates three modes:

- `PLAIN`: submits the original `Runnable`.
- `WRAPPED`: adds exactly one wrapper calling `original.run()`, with no context propagation.
- `CONTEXT`: snapshots a `ThreadLocal<String>` on the submitter; sets/restores on the worker.

**Model note:** this is a pure-JDK *analog* of TaskDecorator. It does not directly measure the implementation cost of Spring's `ContextPropagatingTaskDecorator`, Micrometer Context Propagation, or real MDC. The goal is a transparent, reproducible baseline.

Create file **`TinyTaskDecorationDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class TinyTaskDecorationDemo {
    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();

    enum Mode { PLAIN, WRAPPED, CONTEXT }

    private static void setTrace(String value) {
        if (value == null) {
            TRACE.remove();
        } else {
            TRACE.set(value);
        }
    }

    private static Runnable decorate(Runnable original, Mode mode) {
        return switch (mode) {
            case PLAIN -> original;
            case WRAPPED -> () -> original.run();
            case CONTEXT -> {
                String captured = TRACE.get(); // snapshot on submitter
                yield () -> {
                    String previous = TRACE.get(); // worker context
                    try {
                        setTrace(captured);
                        original.run();
                    } finally {
                        setTrace(previous); // no leak across reused workers
                    }
                };
            }
        };
    }

    private static void verifyContext() throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            setTrace("request-173");

            CompletableFuture<String> observed = new CompletableFuture<>();
            worker.execute(decorate(
                    () -> observed.complete(TRACE.get()), Mode.CONTEXT));

            // Read only after the first job has completed its value.
            String value = observed.get(5, TimeUnit.SECONDS);

            CompletableFuture<Boolean> leaked = new CompletableFuture<>();
            worker.execute(() -> leaked.complete(TRACE.get() != null));

            // Single-thread executor guarantees the check job runs after
            // the prior wrapper returns control to the worker.
            System.out.println("workerTrace=" + value);
            System.out.println(
                    "contextLeaked=" + leaked.get(5, TimeUnit.SECONDS));
        } finally {
            setTrace(null);
            worker.shutdownNow();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not terminate");
            }
        }
    }

    private static long runBatch(Mode mode, int taskCount)
            throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch done = new CountDownLatch(taskCount);
        LongAdder completed = new LongAdder();
        setTrace("request-173");

        try {
            long start = System.nanoTime();

            for (int i = 0; i < taskCount; i++) {
                Runnable work = completed::increment;
                Runnable decorated = decorate(work, mode);
                pool.execute(() -> {
                    try {
                        decorated.run();
                    } finally {
                        // Signal completion after decorator has restored context.
                        done.countDown();
                    }
                });
            }

            if (!done.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Batch timed out: " + mode);
            }
            long elapsed = System.nanoTime() - start;

            if (completed.sum() != taskCount) {
                throw new IllegalStateException(
                        "Missing tasks: " + mode + "/" + taskCount);
            }
            return elapsed;
        } finally {
            setTrace(null);
            pool.shutdownNow();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }

    private static double medianMillis(long[] durations) {
        long[] copy = durations.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2] / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        verifyContext();

        // 20 tasks: illustrates small sample; 30,000 tasks: many short tasks.
        for (int n : new int[] { 20, 30_000 }) {
            long[][] measurements = new long[Mode.values().length][5];

            // Two warm-up rounds + five measurement rounds; rotate mode order.
            for (int round = 0; round < 7; round++) {
                for (int offset = 0; offset < Mode.values().length; offset++) {
                    Mode mode = Mode.values()[
                            (round + offset) % Mode.values().length];
                    long elapsed = runBatch(mode, n);
                    if (round >= 2) {
                        measurements[mode.ordinal()][round - 2] = elapsed;
                    }
                }
            }

            System.out.println("taskCount=" + n);
            for (Mode mode : Mode.values()) {
                System.out.printf(Locale.ROOT,
                        "%s medianBatchMs=%.3f%n", mode,
                        medianMillis(measurements[mode.ordinal()]));
            }
        }

        System.out.println("allBatchesVerified=true");
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 TinyTaskDecorationDemo.java
java TinyTaskDecorationDemo
```

**Deterministically predictable output lines:**

```text
workerTrace=request-173
contextLeaked=false
taskCount=20
PLAIN medianBatchMs=...
WRAPPED medianBatchMs=...
CONTEXT medianBatchMs=...
taskCount=30000
PLAIN medianBatchMs=...
WRAPPED medianBatchMs=...
CONTEXT medianBatchMs=...
allBatchesVerified=true
```

The `...` in the output above **is a placeholder denoting machine-dependent values**, not fixed stdout to copy into tests. Actual code prints millisecond numbers, e.g., formatted with `%.3f`. **Do not fabricate timing numbers**; true results must come from running on the target machine, multiple measurement rounds, and noise analysis.

### Why Is This Demo Meaningful?

- `verifyContext()` checks real worker context using a 1-thread pool. It also confirms the worker does not retain `TRACE` after the decorator finishes.
- `PLAIN` is the unwrapped baseline; `WRAPPED` isolates the idea of "adding one `Runnable` layer"; `CONTEXT` adds `ThreadLocal.get/set/remove` and snapshotting.
- `CountDownLatch` sits **outside the decorator** and only counts down after `decorated.run()` finishes, so the measurement includes the `finally` restoration step. Every mode uses the same completion-reporting wrapper for a fair comparison; `LongAdder` verifies the count of executed tasks.
- `shutdownNow/awaitTermination` cleans up the pool after each batch; if tasks fail to stop or the environment is overloaded, the program throws an error instead of silently dropping work.
- Testing N=20 and N=30,000 highlights the risk of inferring from tiny samples. Even N=30,000, though larger, is still **not a professional nanosecond microbenchmark**.
- Rotating execution order helps reduce some bias from JIT, CPU temperature, and caches; it does not replace proper statistical/benchmark methodology.
- Ultra-short work loops accentuate scheduling and wrapper overhead; real I/O workloads will yield different ratios.

### What the Demo Cannot Fully Isolate

`runBatch` creates a new pool each round, so timing also includes thread creation, queue traversal, scheduler wait, `LongAdder`/`CountDownLatch`, and per-`Runnable` allocation. The difference between modes **is not "the decorator's pure nanosecond cost"**. Moreover, workers execute concurrently while `main` submits, so total batch time does not equal the sum of N task durations. To measure each operation accurately, use JMH or profiling after defining the exact measurement question.

## 6. Interpreting Results: Avoid Turning Noisy Measurements Into Architecture Decisions

Do not assume `CONTEXT` is always slowest on every run. Thread scheduling noise, JIT, GC, CPU throttling, or other applications running on the machine can produce unexpected orderings.

| Observation | Possible Explanation | Verification Action |
| --- | --- | --- |
| At N=20, modes differ by a few milliseconds | Mostly startup/scheduling/GC | Repeat multiple batches, inspect distribution, do not conclude from one run |
| At large N, CONTEXT is consistently slower | Snapshot/restore/allocations may be significant | Profile allocations/CPU, vary task workload, check with JMH |
| WRAPPED roughly equals PLAIN | Simple wrapper may be well-optimized by JIT | Do not generalize to MDC/Micrometer snapshots |
| Enabling decorator raises p99 latency | Could be GC, contention, logging, or queue delay | Inspect JFR, GC logs, queue depth, worker utilization |
| Throughput drops while average latency barely changes | Bottleneck on submitter or processing resources | Measure CPU, submission time, per-instance saturation |
| Context propagates in small tests, fails in prod | Missing capture on a submit path or missing cleanup | Test with async callbacks, cancellation, exceptions, multiple threads |
| Disabling decorator speeds things up yet loses traces | Changed operational semantics | Keep minimal context or use a different integration mechanism |

**How to report results responsibly:** record JDK/Spring versions, CPU/vCPU, worker count, queue policy, N, rounds, warm-up, GC, and logging state; report median and p95 when sample counts allow. Present absolute **and** relative differences along with spread/error bounds. If the difference is smaller than run-to-run variance, state "no difference confirmed".

Never use a single benchmark run as proof that the application will be faster if correlation IDs are disabled; losing traceability can incur operational costs far exceeding the CPU saved.

## 7. When Real Micro-Overhead Measurement Is Needed: JMH Instead of a Crude Stopwatch

OpenJDK's Java Microbenchmark Harness (**JMH**) is designed to mitigate distortions from JIT compilation, dead-code elimination, constant folding, warm-up, forking, and flawed timing. It is far better suited when comparing tiny overheads of two decorator implementations.

A benchmark design should separate **at least two questions**:

### 7.1. Cost of Creating Wrapper/Capturing on the Submitter

Measure the cost of calling `decorate(original)`: capturing context and allocating the wrapper. The goal is detecting allocations/task and preparation time. Ensure the resulting wrapper is not optimized away; in JMH use `Blackhole.consume(wrapper)` or an equivalent strategy.

### 7.2. Cost of Running the Wrapper on the Worker

Pre-create the wrapper or structure state to separate allocation from execution; measure `wrapper.run()` with context set/restore and ultra-short task logic. Ensure the business code is not optimized away by JIT.

### 7.3. End-to-End Cost of a Spring Executor

Single-threaded JMH does not replace measuring **submit → queue → worker → completion** in Spring. With async dispatch involving blocking, examine thread contention, queuing, parallel execution, pool saturation, and timeouts. A "10 ns/op" JMH result for a wrapper cannot simply be added to p99 latency while ignoring queues and CPU contention.

To use JMH properly:

- Use separate JVM forks, warm-up iterations, and measurement iterations; do not merely call a method a few times in `main`.
- Configure *state scope* (per-thread or shared) to match intent; watch out for contention on shared `ThreadLocal`s or counters.
- Avoid writing manual loops inside benchmark methods when JMH already measures per operation. Use `Blackhole` to keep side effects observable.
- Check allocations with a supported profiler such as JFR or JMH's GC profiler. Run under the same Java version and host configuration.
- Vary task size: no-op/tiny CPU, real computations, and I/O tasks with realistic mocked latency; never test only no-op.
- Measure "very few tasks" separately from "very many tiny tasks"; tiny counts make setup overhead dominate while lacking statistical power.
- When measuring MDC/Micrometer, register real accessors and populate contexts of production-like size. An empty context does not reflect the cost of copying a map with many entries.

Refer to [OpenJDK JMH](https://github.com/openjdk/jmh) to set up a benchmark project. Never "invent" JMH figures without actually running in the target environment.

## 8. Configuring TaskDecorator in Spring ThreadPoolTaskExecutor

Below is an **integration configuration class** for Spring Framework 6.2 or Spring Boot using `ThreadPoolTaskExecutor`. It illustrates capturing a correlation ID via `ThreadLocal` and restoring it after the task completes.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TinyTaskExecutorConfiguration {
    public static final ThreadLocal<String> CORRELATION_ID =
            new ThreadLocal<>();

    @Bean("contextAwareExecutor")
    public ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("tiny-work-");

        executor.setTaskDecorator(task -> {
            String captured = CORRELATION_ID.get();

            return () -> {
                String previous = CORRELATION_ID.get();
                try {
                    if (captured == null) {
                        CORRELATION_ID.remove();
                    } else {
                        CORRELATION_ID.set(captured);
                    }
                    task.run();
                } finally {
                    if (previous == null) {
                        CORRELATION_ID.remove();
                    } else {
                        CORRELATION_ID.set(previous);
                    }
                }
            };
        });

        return executor;
    }
}
```

This configuration code is **not standalone** with only the JDK: it requires the `spring-context` dependency and an application context. The static `ThreadLocal` in the example serves illustration; real systems should use a context mechanism with clear ownership, lifecycle, and data policies, avoiding spreading sensitive context beyond needed processing paths.

**Key points:**

- Capture `CORRELATION_ID.get()` at decoration time to snapshot the submitter; set it on the worker before `task.run()` and restore in `finally`.
- Capture/restore runs **for every task**; with very many short tasks, cumulative cost can become noticeable.
- Even when `CORRELATION_ID` is `null`, the example still creates a wrapper and performs get/remove; if most tasks need no context, consider a selective strategy with verified semantics.
- `queueCapacity=64` and 4 workers are illustrative parameters only, not a recommendation for every project. Experimentally change one variable at a time and test rejection.
- If a task is rejected on submit, the callback never runs; do not use the decorator as the place to catch `TaskRejectedException` on the submitter.
- If a task is wrapped by `FutureTask`, business exceptions may sit in `Future.get()` rather than passing through a decorator `catch`; design error observation separately.

### Enabling ContextPropagatingTaskDecorator

When logging/observation context via Micrometer Context Propagation (Spring Framework 6.1+) is needed, you can use:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Inside the created executor bean configuration:
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

The snippet above requires the **`io.micrometer:context-propagation`** dependency, proper `ThreadLocalAccessor`/context registry configuration, and a supported Spring version. Do not assume it automatically copies every `ThreadLocal` or security info; what gets propagated depends on registered accessors.

Spring Javadoc states directly: this decorator has **overhead** and is not recommended for applications handling a huge volume of very small tasks. The reason is repeated context snapshotting/restoration, potentially creating extra scopes/objects. If only a single correlation ID is needed and explicit parameter passing already exists, running full context snapshot machinery may not be worth the cost—though tracing/observation requirements must be weighed.

### CompositeTaskDecorator and Stacked Wrappers

If using multiple decorators (MDC, observation, custom timer, security context), each layer can do extra work and allocate wrappers. Do not mechanically sum estimated overheads of individual decorators: they may share contexts or create nested restorations. Measure **the real combined configuration**, verify application order, exception/cleanup behavior, and avoid duplicating copies of the same context.

## 9. Where Can You Optimize If Tasks Are Too Small?

### 9.1. Group Work Into Appropriately Sized Batches

Suppose there are 10,000 tasks, each updating only one tiny value. If every task goes through submit/queue/decorator, per-task cost repeats 10,000 times. Grouping 100 operations into one task can reduce decorate/submit calls from 10,000 down to 100.

However, batching is not free:

- Larger tasks can increase latency for individual items, hurting fairness.
- Batch size/time limits, memory footprint, and retry mechanisms are needed.
- One failing item may force reprocessing the whole batch; idempotency or checkpoints are required.
- With differing per-request contexts, never merge multiple tenant/user contexts and accidentally run under one shared context.
- Avoid holding locks/DB transactions too long when batching.

### 9.2. Propagate Minimal Context

Capture only essential values. If a task needs a correlation ID, passing the ID as a command/DTO parameter can be clearer than snapshotting an entire MDC map or multiple ThreadLocal accessors. However, some logging/tracing libraries require context in ThreadLocal; removing propagation when it is a business/observability requirement is wrong. Optimize only after establishing a baseline.

### 9.3. Separate Executor Types by Requirement

One executor for fully traced tasks and another for ultra-short calculations needing no context can reduce overhead; yet verify no path bypasses required context. Do not introduce this split merely for a pretty benchmark score if it adds concurrency and queue management complexity.

### 9.4. Avoid Synchronous Logging on Every Task

Logging INFO on every task can cost more CPU/I/O than the tiny task itself. Prefer aggregate metrics or controlled sampling; watch tag cardinality and sensitive data. Never drop critical error logs or mandatory tracing simply because a test showed higher throughput.

### 9.5. Choose the Right Execution Model

Not every 1–2 µs operation is worth dispatching through an executor. If the computation is cheap, nonblocking, and already on an appropriate thread, running directly can be simpler. However, never push blocking I/O onto an event-loop or request thread just to avoid a decorator. Decisions must rest on latency, isolation, response behavior, and downstream capacity.

## 10. Be Careful With Virtual Threads, Pools, and Spring @Async

Java 21+ has virtual threads, whereas **Java 17 does not have virtual threads**. Spring 6.1+ supports `SimpleAsyncTaskExecutor.setVirtualThreads(true)` on JDK 21+. Comparing a platform-thread pool with a virtual-thread executor changes thread creation, queuing, context lookup, and scheduling costs. Those are **two different execution architectures**, not a clean benchmark isolating TaskDecorator overhead.

With `@Async`, the typical path is:

```text
Caller
  |
  v
Spring proxy (must go through proxy to trigger @Async)
  |
  v
Executor submit
  |
  +--> decorate actual callback
  |
  +--> queue / worker or virtual thread
            |
            v
        decorator wrapper
            |
            +--> set context
            +--> original callback.run()
            +--> restore context
```

To measure realistically, identify the exact executor bean via `@Async("contextAwareExecutor")`, thread names, active counts, and config. Never take an app calling `this.asyncMethod()` on itself and conclude the decorator has zero overhead: self-calls usually bypass the proxy and never submit tasks as intended.

Note: if a task returns `CompletableFuture` or has internal callbacks, the decorator wraps **the execution callback submitted to that executor**; it does not automatically cover the entire chain of asynchronous stages running on other executors or the common pool. If a reactive/CompletionStage chain needs context at multiple boundaries, design propagation at each appropriate boundary.

## 11. Testing Correctness While Reducing Overhead

Before "optimizing", write tests:

| Test | Scenario | What to Verify |
| --- | --- | --- |
| A | Context has value at submit | Worker sees exact ID |
| B | Submitter has no context | Worker does not use leftover old context |
| C | Multiple requests on same worker | Previous request's ID does not leak to next request |
| D | Task throws RuntimeException | `finally` restore/remove still executes |
| E | Task cancelled or rejected | Do not report task as having run; clean up properly where executed |
| F | `@Async` from another bean | Call genuinely goes through proxy and decorated executor |
| G | `CompletableFuture` stages | Context at each stage is verified, not assumed propagated |
| H | Slow task or lock contention | Decorator does not hold locks/ThreadLocal beyond scope too long |
| I | Real logging/tracing enabled | Correlation/observation remains complete after optimization |
| J | N=20, N=30,000, varying CPU/I/O tasks | Performance conclusions do not rest on a single case |

Use `CountDownLatch` to synchronize task start/finish checkpoints and verify completion counters. Tests must have timeouts so they cannot hang. Only measure latency after verifying zero dropped tasks and zero context errors.

**A dangerous bug:** toggling a decorator on/off via a context flag without a clear contract; tasks spawned from different background/HTTP threads can lose traces or inherit wrong context. Configuration changes should be rolled out with metrics and regression tests.

## 12. Production Measurement: Separating Context Cost From Other Bottlenecks

Metrics to record in real environments:

- **Throughput**: tasks/second, accepted/completed/rejected counts.
- **Queue**: depth and wait time; do not blame queue wait on TaskDecorator.
- **Worker**: active thread count, pool size, CPU utilization, contention.
- **Latency**: p50/p95/p99 from submit to completion, and callback duration alone.
- **GC/allocation**: allocations per task, GC pauses, heap pressure.
- **Context correctness**: requests missing correlation ID, broken traces/spans, cross-request leakage.
- **Downstream**: pending JDBC connections, HTTP connection pools, 429/503s, and retries.
- **Log/observation**: synchronous formatting/export cost and metric tag cardinality.

Use JFR/async-profiler/JMH at the appropriate measurement level. In Spring Boot, Micrometer/Actuator can expose executor metrics when bindings/configuration are in place; exact metric names depend on version and registry—do not assume every executor is automatically instrumented in full.

A safe production experiment can compare **two equivalent traffic groups** toggling an optimization already proven to preserve semantics, watching both error rates and tracing completeness. Never strip tracing from financial/sensitive transactions just for a better benchmark without reviewing audit/security requirements.

## 13. Common Mistakes

**"Decorate just creates one lambda, so overhead must be zero."** Lambdas can be optimized away in some contexts, yet snapshot/restore, wrapper allocation, context accessors, MDC, and metrics incur real cost. Measure your workload.

**"With 5 tasks, each task is 30% slower."** Not necessarily; 5 samples are easily noisy. Report absolute time and variance, run multiple rounds, and only then conclude.

**"With 50,000 tasks, TaskDecorator must be the bottleneck."** Do not assume; the bottleneck might be the queue, LongAdder/locks, CPU, DB, or logging. Profile first.

**"Turning off the decorator for speed won't affect correctness."** False if business logic/logging/observability relies on context. Test correlation IDs, cleanup, and security context first.

**"ThreadLocal automatically propagates to a thread pool."** False; `ThreadLocal` is normally per-thread. Reused worker threads can retain old values without cleanup. `InheritableThreadLocal` is also not a reliable solution for pooled workers.

**"ContextPropagatingTaskDecorator copies everything."** It propagates contexts registered and supported by Micrometer accessors; it does not automatically copy every object or guarantee transaction/secret isolation.

**"One `nanoTime` measurement equals JMH."** No. `nanoTime` is useful for measuring elapsed time in a program, yet microbenchmarks require warm-up/forking/statistics and guarding against unintended optimizations.

**"Using `Thread.sleep(1)` to simulate a tiny task."** `sleep` puts the task in waiting/blocked state rather than reflecting a short CPU computation; results reflect timer granularity and scheduling instead.

**"Removed the decorator and still saw MDC on the worker, so propagation works."** The worker may be **leaking stale context**. Test with a different request and verify `ThreadLocal.get()==null` after cleanup.

**"`@Async` method was called so the decorator always ran."** Self-invocation, using the wrong executor bean, submitting directly to another executor, or running `CompletableFuture.supplyAsync` on the common pool can all bypass the measured decorator.

**"The decorator catches all exceptions so error metrics are always accurate."** For Future-backed callbacks, errors can stay inside the Future without escaping `Runnable.run()`. Observe errors on Future/caller or a dedicated handler; do not miscount and base performance decisions on wrong metrics.

## 14. Decision Process and References

A short, evidence-based process:

1. **Define the workload:** truly few tasks or huge volumes of very tiny tasks? Is the workload CPU, blocking I/O, or mixed?
2. **Define context requirements:** need MDC/tracing/security/transaction? What must be propagated, and what must never be copied?
3. **Verify correctness:** right context on workers and zero leaks afterward, including on errors/cancellations/rejections.
4. **Measure baseline:** real executor and config without decorator; confirm tasks complete rather than being silently discarded.
5. **Measure light wrapper and real decorator:** keep pool/task identical, warm up, run multiple rounds, multiple N sizes, and multiple task sizes.
6. **Analyze metrics:** median/p95/p99, throughput, allocation/GC, and queuing, not just a percentage from a single run.
7. **Identify drivers:** wrapper allocation, MDC copy, ContextSnapshot, logging/export, scheduling, or downstream.
8. **Pick optimization:** batching, minimal context propagation, sampling, separate executors, or leave as-is if overhead is insignificant.
9. **Test regressions and roll out:** context, trace completeness, overload behavior, and exception handling must stay intact.
10. **Record measurement conditions:** JDK/Spring versions, hardware, thread count, warm-up, repetitions, and uncertainty in results.

### Official Documentation

1. [Spring Framework 6.2 – TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/TaskDecorator.html): execution callback, context/monitoring, and exception visibility limits.
2. [Spring Framework 6.2 – ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): context propagation and overhead warning for many very small tasks.
3. [Spring Framework 6.2 – ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): configuring `setTaskDecorator` and pool/queue resources.
4. [Micrometer Context Propagation – Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): `ThreadLocalAccessor`, `ContextSnapshot`, and propagation across thread boundaries.
5. [OpenJDK – Java Microbenchmark Harness](https://github.com/openjdk/jmh): warm-up, forking, measurement, and microbenchmarking.
6. [Java SE 17 – ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread scope, `get/set/remove`.
7. [Java SE 17 – ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submission, worker lifecycle, shutdown, and Future.

**Conclusion:** TaskDecorator cost depends on **how often decoration runs, how short each task is, and what context types must be captured/restored**. If there are only very few tasks, measurements are also noisy and absolute overhead may be negligible. Preserve correct context semantics first, measure with a baseline and sufficient samples second, and then optimize selectively rather than disabling tracing or guessing from a single stopwatch number.
