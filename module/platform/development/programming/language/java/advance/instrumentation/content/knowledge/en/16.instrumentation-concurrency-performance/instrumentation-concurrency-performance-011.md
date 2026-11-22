# Evaluating Correctness Alongside Throughput and Latency Percentiles

## 1. Why Fast Instrumentation Is Not Necessarily Correct Instrumentation

A Java agent evaluated solely by **throughput** (operations per second) and **p50/p95/p99 latency** percentiles may look great on paper while silently corrupting application behavior or dropping observability data.

For example:

- A tracing hook skips 8% of events to reduce overhead. **Throughput improves**, but the system no longer satisfies the contract that *every valid request must produce an event*.
- A hook throws a `RuntimeException` **after** the business logic has already persisted data. The caller sees a failure and retries, yet the side effect has already occurred; duplicate payments or inconsistent records may appear.
- A queued exporter does not block business threads so request p99 remains low, but a full queue drops traces. Measuring p99 without measuring dropped events misses the bug.
- A transformer injects code into its own helper classes, causing **reentrancy** or class-loading recursion under heavy load. Single-threaded tests may pass, while concurrent load hangs the JVM.
- Installing an agent alters timing, causing a hard-to-observe race condition to surface more often—or conversely masking the race due to accidental locking.

**Conclusion:** performance is only one axis of evaluation. Instrumentation must **preserve the business contract, concurrency consistency, and telemetry completeness/semantic correctness** before comparing speed.

This article belongs to the **Concurrency and Performance** group of Java instrumentation. The goal is to build a testing methodology that combines correctness + throughput + latency distributions, without confusing "a fast benchmark" with "correct behavior."

### 1.1. Four Result Categories to Report Separately

| Evaluation Category | Question |
|---|---|
| **Business correctness** | Do return values, exceptions, side effects, ordering, and state match the contract prior to instrumentation? |
| **Telemetry correctness** | Do event counts, payloads, correlation IDs, ordering, sampling, and exporter errors match the observability contract? |
| **Concurrency correctness** | Do concurrent operations preserve atomicity, happens-before, visibility, liveness, and avoid deadlock/livelock or reentrant recursion? |
| **Performance** | How do throughput, p50/p95/p99/p99.9, error rate, resource consumption, GC, and latency under saturation change? |

Evaluating an agent is an **AND condition**: business logic remains correct **and** telemetry is correct **and** concurrency is correct **and** performance is acceptable. Do not use a high performance score to "compensate" for data errors.

## 2. Defining Metrics Before Running Benchmarks

### 2.1. What Count per Second Does Throughput Measure?

There are at least two different ways to report it:

~~~text
offeredRate    = number of requests issued to the system / time
completedRate  = number of requests with a completed result / time
successRate    = number of requests succeeding per contract / time
~~~

An agent that causes 20% of requests to fail fast can report high **completed throughput** but low **successful throughput**. If charts do not distinguish between them, it is easy to misjudge.

In the demo below, `throughput` is **attempted completed operations per second** over a batch of 1,200 request IDs. The result **includes requests that throw an exception**. This value is not synonymous with the number of successful business transactions.

Under concurrent load:

- If more work is submitted than the system can process, queues can grow unboundedly.
- If the client blocks and stops issuing new requests until the previous one completes, the issue rate automatically drops when the system slows down; latency results may look "pretty" because requests that should have been issued are omitted.
- If requests time out, are cancelled, or are rejected before the server receives them, the denominator and status must be recorded explicitly.
- High throughput over a short burst does not prove that load can be sustained long-term.

### 2.2. What Do p50, p95, and p99 Mean?

Given the observed durations (covering the operations defined in the measurement set), sorted in ascending order:

~~~text
sorted = sort(latencies)
p50 = value at approximately the 50% position of the distribution
p95 = value at approximately the 95% position of the distribution
p99 = value at approximately the 99% position of the distribution
~~~

An **illustrative** example with 100 operations: p99 is the region near the slowest operation. It represents the "tail" better than the mean, but **does not by itself prove** the absence of deadlocks or rare pauses.

Libraries and statistical tools have multiple percentile interpolation definitions. The demo chooses **nearest-rank**:

~~~text
index(p) = max(0, ceil(p * numberOfSamples) - 1)  // zero-based
percentile(p) = sorted[index(p)]
~~~

Use the same definition when comparing runs; do not compare p99 values from two tools with different sampling methodologies without stating it explicitly.

### 2.3. Know Which Latency You Are Measuring

| Latency Type | Start / End | Interpretation Risk |
|---|---|---|
| **Service-method latency** | Immediately before and immediately after the instrumented business method | Excludes the time the request spent waiting in a queue before the method ran |
| **Server end-to-end** | Server receives request until it returns response | May exclude network/client-side queuing |
| **Client observed** | Client issues request until it receives response, timeout, or failure | May be affected by client, network, retries, and connection pool |
| **Exporter/event pipeline latency** | Event creation until collector stores/acks | Not identical to business request latency |
| **Class-load/transform latency** | Start → end of `ClassFileTransformer.transform` | Only measures cost at load/redefine/retransform time, not per-invocation hook cost |

**Note:** agent `premain` startup, class transformation, and per-invocation probes are **three distinct forms of overhead**. A benchmark measuring only method calls can miss startup delay, attach/retransform pauses, or transformer cost. Conversely, if a test only measures class loading, do not extrapolate business p99 from it.

### 2.4. Error Rate Must Have a Taxonomy

Do not count every "fast completion" as a success:

- **Functional error:** value does not match the oracle.
- **Application exception:** exception type or throw timing differs from the contract.
- **Timeout/cancellation:** request does not complete within the deadline.
- **Rejected/backpressure:** not accepted for processing; may be valid if explicitly specified.
- **Telemetry drop/duplicate:** business logic is still correct, but observability data is wrong.
- **Partial commit:** side effect occurred, yet the caller receives an error; very dangerous upon retry.
- **Transformer/install error:** invalid classfile, verify/load failure, or missing coverage.
- **Liveness failure:** deadlock, livelock, thread starvation, or infinite wait.

You can define **quality gates** based on requirements, for example:

~~~text
businessWrongResponses  = 0
businessMissingIDs       = 0
businessDuplicateIDs     = 0
unexpectedExceptions     = 0
unexpectedPartialCommits = 0

telemetryMissingEvents   = 0  // only if the contract requires full coverage
telemetryDuplicateEvents = 0  // only if the contract requires exactly once

throughputSuccess        >= project threshold
p99ClientLatency         <= approved SLO
resourceOverhead         <= approved budget
~~~

This is a **sample gate**, not a default threshold for every organization. If the design uses **sampling**, requiring `telemetryMissingEvents=0` across all requests is wrong; the oracle must verify the exact **set of IDs selected for sampling**, the probability, and the allowed data loss limit.

## 3. What Does Instrumentation "Correctness" Include?

### 3.1. Preserving Business Behavior

With the same inputs and preconditions, compare before and after the agent:

1. **Return value:** do values, types, metadata, and edge-case values match?
2. **Exception contract:** is the exception type/cause/ordering altered by the hook?
3. **Side effects:** are the number of commits, DB writes, sent messages, and state updates accurate?
4. **Idempotency:** do retries or timeouts create duplicate side effects?
5. **Transaction context:** does the hook run between commit and response and then throw an error, misleading the caller?
6. **Resource lifecycle:** are streams, locks, connections, and files closed on all return/throw paths?
7. **Security context:** do principal, thread context class loader, or transaction/tracing context leak to other requests?

A hook meant "only for measurement" should never become the reason business logic fails. **Fail-open** is a common choice for non-essential telemetry: observability errors are handled separately, tracked with metrics so they are not lost, and never replace the original exception. However, do not blindly catch every `Throwable` everywhere: `VirtualMachineError` and severe errors require their own policy.

### 3.2. Telemetry Correctness

If **one event per operation** is required, you can verify:

- Every request ID has a corresponding event, with **none missing**.
- No two events share the same logical event ID when there should only be one.
- Payloads contain the right request ID, span/trace ID, timestamp semantics, status, error details, and parent relationships.
- Ordering along **a causal chain** is valid, without demanding an unreasonable total order across threads.
- Events are confirmed at the final sink if the contract promises **delivered**, not merely "enqueued."
- When sampling/dropping is allowed, the `dropped` metric and actual observations match the policy.
- Privacy/security: do not accidentally capture tokens, passwords, PII, or data beyond the permitted scope.

Do not equate "hook invoked," "event enqueued," and "event persisted by collector." Those are three different milestones.

### 3.3. Concurrent Correctness

When multiple threads concurrently invoke an instrumented method, test for:

- Data races in counters or mutable configuration.
- Never using unsynchronized `HashMap`/`ArrayList` as a shared event sink.
- Never holding business locks while waiting on a network exporter, avoiding deadlocks and tail latency.
- Never re-invoking the instrumented method itself from helpers/logging, causing recursion.
- Proper `ThreadLocal`/trace context across task handoff, virtual threads, or executor thread reuse.
- Not losing `InterruptedException`, cancellation flags, or deadlines.
- Not breaking happens-before, visibility, and publication when changing runtime configuration.
- Not assuming callbacks across multiple class loaders have a fixed global order.
- Correct behavior under slow collectors, full queues, CPU saturation, or GC pauses.

**Special note on `ClassFileTransformer`:** a transformer callback used during class load/redefine/retransform is not a request hook. If a transformer throws an exception, the `ClassFileTransformer` Javadoc states that subsequent transformers are still called, and the load/redefine/retransform is still attempted; throwing an exception here has the same effect as returning `null` for that transform. That is **different** from a method hook injected into business bytecode: an unhandled exception from a hook can propagate to the caller and alter semantics.

## 4. Comparing Fairly: Baseline, Safe Agent, and Failure Modes

To demonstrate why gates are necessary, consider four modes:

| Mode | Instrumentation Behavior | Business Correctness | Telemetry Correctness |
|---|---|---|---|
| `BASELINE` | Emits no events | Must be correct | Events not required |
| `SAFE` | Records one event per request using thread-safe structures | Must be correct | Complete events, no duplicates |
| `DROP` | Silently drops every ID divisible by 13 | Business logic still correct | **Wrong** if contract requires full events |
| `THROW` | Hook throws an exception for every ID divisible by 11 **after commit** | **Wrong**: caller sees error after side effect | **Wrong**: missing events for those IDs |

It is possible for `DROP` or `THROW` to achieve higher throughput than `SAFE` because they **do less work or exit early via exception**. That is not a performance victory: such a comparison changes the class of completed work and violates quality gates.

### 4.1. Invariants in the Demo

With `REQUESTS = 1200` and `THREADS = 4`, each worker receives 300 distinct IDs, from 0 to 1199:

~~~text
For every id:
    business executes exactly once
    correct response is id + 1

For SAFE:
    one telemetry event per id

For BASELINE:
    no telemetry required

For DROP:
    no telemetry event if id % 13 == 0

For THROW:
    business commits, then hook throws if id % 11 == 0
~~~

The count of IDs divisible by 13 in `[0,1199]` is **93**, including ID 0. The count of IDs divisible by 11 is **110**, including ID 0. These two numbers are independent of scheduler timing, making them stable oracles for negative tests.

We will measure **both successful requests and requests that throw exceptions**; in `THROW`, 110 operations are counted as failed even though their business side effects already occurred. That is the test that detects **partial commits**.

## 5. Complete Java 17+ Example: Running Concurrent Load and Checking Invariants

### 5.1. Experiment Scope

The following example is a **standalone** Java program requiring no Maven, Java agent JAR, or external libraries. The "instrumentation" is **simulated via an explicit hook in `Service.handle`** to focus on measuring correctness and latency without bytecode rewriting.

In a real system, `ClassFileTransformer` or another instrumentation tool would insert the hook at the same location; the invariants to verify **remain unchanged**. **Do not call this example a demonstration of bytecode injection**: it does not register a transformer, modify classfiles, measure class-loading callback cost, or inspect GC-root graphs.

Using `ConcurrentHashMap.newKeySet()`, `AtomicIntegerArray`, `AtomicInteger`, and `CountDownLatch`, the program reproducibly exercises concurrent logic conditions. Throughput and percentile figures are printed, but **only for observing the mechanics**, not as a production benchmark with warm-up, fork/isolation, and statistical rigor.

### 5.2. File `InstrumentationQualityDemo.java`

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicIntegerArray;

public final class InstrumentationQualityDemo {
    private static final int THREADS = 4;
    private static final int REQUESTS = 1200;
    private static final int PER_THREAD = REQUESTS / THREADS;

    enum Mode { BASELINE, SAFE, DROP, THROW }

    private static final class Service {
        final Mode mode;
        final AtomicIntegerArray executed = new AtomicIntegerArray(REQUESTS);
        final Set<Integer> events = ConcurrentHashMap.newKeySet();
        final AtomicInteger emissions = new AtomicInteger();

        Service(Mode mode) { this.mode = mode; }

        int handle(int id) {
            // Business operation: one commit per ID.
            executed.incrementAndGet(id);

            // Simulated instrumentation starts after the business commit.
            if (mode == Mode.THROW && id % 11 == 0) {
                throw new IllegalStateException("observer failed");
            }
            if (mode == Mode.SAFE || mode == Mode.THROW
                    || (mode == Mode.DROP && id % 13 != 0)) {
                emissions.incrementAndGet();
                events.add(id);
            }
            return id + 1;
        }
    }

    private static final class WorkerResult {
        final int successes;
        final int errors;
        final int wrongResponses;
        final int errorsAfterCommit;
        final long[] latencies;

        WorkerResult(int successes, int errors, int wrongResponses,
                int errorsAfterCommit, long[] latencies) {
            this.successes = successes;
            this.errors = errors;
            this.wrongResponses = wrongResponses;
            this.errorsAfterCommit = errorsAfterCommit;
            this.latencies = latencies;
        }
    }

    private static WorkerResult processPartition(Service service, int worker,
            CountDownLatch ready, CountDownLatch go) throws InterruptedException {
        ready.countDown();
        go.await();
        int successes = 0, errors = 0, wrong = 0, afterCommit = 0;
        long[] durations = new long[PER_THREAD];

        for (int j = 0; j < PER_THREAD; j++) {
            int id = worker * PER_THREAD + j;
            long began = System.nanoTime();
            try {
                int result = service.handle(id);
                successes++;
                if (result != id + 1) wrong++;
            } catch (RuntimeException ex) {
                errors++;
                if (service.executed.get(id) != 0) afterCommit++;
            } finally {
                durations[j] = Math.max(0L, System.nanoTime() - began);
            }
        }
        return new WorkerResult(successes, errors, wrong, afterCommit, durations);
    }

    private static double percentileMillis(long[] sorted, double p) {
        int index = Math.max(0, (int) Math.ceil(p * sorted.length) - 1);
        return sorted[index] / 1_000_000.0;
    }

    private static void runOnce(Mode mode) throws Exception {
        Service service = new Service(mode);
        ExecutorService pool = Executors.newFixedThreadPool(THREADS);
        CountDownLatch ready = new CountDownLatch(THREADS);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<WorkerResult>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < THREADS; worker++) {
                final int w = worker;
                futures.add(pool.submit((Callable<WorkerResult>)
                        () -> processPartition(service, w, ready, go)));
            }
            ready.await();
            long wallStart = System.nanoTime();
            go.countDown();

            int successes = 0, errors = 0, wrong = 0, afterCommit = 0;
            long[] latencies = new long[REQUESTS];
            int copied = 0;
            for (Future<WorkerResult> future : futures) {
                WorkerResult r = future.get();
                successes += r.successes;
                errors += r.errors;
                wrong += r.wrongResponses;
                afterCommit += r.errorsAfterCommit;
                System.arraycopy(r.latencies, 0, latencies, copied,
                        r.latencies.length);
                copied += r.latencies.length;
            }
            long elapsedNs = System.nanoTime() - wallStart;

            int missingBusiness = 0, duplicateBusiness = 0;
            for (int id = 0; id < REQUESTS; id++) {
                int times = service.executed.get(id);
                if (times == 0) missingBusiness++;
                if (times > 1) duplicateBusiness += times - 1;
            }

            boolean telemetryRequired = mode != Mode.BASELINE;
            int missingEvents = telemetryRequired
                    ? REQUESTS - service.events.size() : 0;
            int duplicateEvents = service.emissions.get()
                    - service.events.size();
            boolean passed = successes + errors == REQUESTS
                    && errors == 0 && wrong == 0
                    && missingBusiness == 0 && duplicateBusiness == 0
                    && (!telemetryRequired
                        || (missingEvents == 0 && duplicateEvents == 0));

            Arrays.sort(latencies);
            System.out.printf(Locale.ROOT,
                    "%s pass=%s success=%d errors=%d afterCommitErrors=%d"
                    + " missingBusiness=%d duplicateBusiness=%d"
                    + " missingEvents=%d duplicateEvents=%d%n",
                    mode, passed, successes, errors, afterCommit,
                    missingBusiness, duplicateBusiness, missingEvents,
                    duplicateEvents);

            System.out.printf(Locale.ROOT,
                    "%s throughput=%.0f ops/s p50=%.3f ms"
                    + " p95=%.3f ms p99=%.3f ms%n",
                    mode, REQUESTS / (elapsedNs / 1_000_000_000.0),
                    percentileMillis(latencies, 0.50),
                    percentileMillis(latencies, 0.95),
                    percentileMillis(latencies, 0.99));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        for (Mode mode : Mode.values()) {
            runOnce(mode);
        }
    }
}
~~~

### 5.3. Compiling and Running

Open a terminal in the folder containing `InstrumentationQualityDemo.java`. With JDK 17 or newer:

~~~bash
javac --release 17 InstrumentationQualityDemo.java
java InstrumentationQualityDemo
~~~

No `--enable-preview`, `--add-opens`, or JVM agent is required; the `java.util.concurrent` and `System.nanoTime()` APIs are included in Java 17. The fact that the demo tool **does not require a real agent** is deliberate: the test harness focuses on **hook behavior after invocation**, without assuming a transformer creation API.

### 5.4. Verified Deterministic Correctness Results

The program was compiled with `javac --release 17` and actually run on JDK 24; the four **correctness** lines printed:

~~~text
BASELINE pass=true success=1200 errors=0 afterCommitErrors=0 missingBusiness=0 duplicateBusiness=0 missingEvents=0 duplicateEvents=0
SAFE pass=true success=1200 errors=0 afterCommitErrors=0 missingBusiness=0 duplicateBusiness=0 missingEvents=0 duplicateEvents=0
DROP pass=false success=1200 errors=0 afterCommitErrors=0 missingBusiness=0 duplicateBusiness=0 missingEvents=93 duplicateEvents=0
THROW pass=false success=1090 errors=110 afterCommitErrors=110 missingBusiness=0 duplicateBusiness=0 missingEvents=110 duplicateEvents=0
~~~

Alongside each line above, the program prints **a throughput/p50/p95/p99 line** of the form:

~~~text
BASELINE throughput=<varies per run> ops/s p50=<varies> ms p95=<varies> ms p99=<varies> ms
SAFE throughput=<varies per run> ops/s p50=<varies> ms p95=<varies> ms p99=<varies> ms
DROP throughput=<varies per run> ops/s p50=<varies> ms p95=<varies> ms p99=<varies> ms
THROW throughput=<varies per run> ops/s p50=<varies> ms p95=<varies> ms p99=<varies> ms
~~~

**The four lines above illustrate the format, not literal stdout and not fixed benchmark numbers.** Throughput and percentiles are influenced by the scheduler, CPU, JIT, GC, and timer resolution. Do not take numbers from a single run as default thresholds. The correctness results are deterministically determined by the number of request IDs and the drop/throw conditions.

### 5.5. Why `DROP` Must Fail Even Though All Business Operations Succeed

`DROP` skips the event when `id % 13 == 0`, dropping 93 IDs out of 1,200 IDs. All business operations remain correct, responses remain correct, and no exceptions occur.

If a benchmark only reports request throughput or `p99` of `Service.handle`, `DROP` may look equal to or faster than `SAFE`, yet **the telemetry contract is violated**. The valid result is:

~~~text
businessCorrect = true
telemetryComplete = false
overallPass = false
~~~

This is an example of **silent data loss**. In production, if sampling is intentional, you must test against an oracle of "which IDs are **expected** to be recorded," rather than demanding all IDs when the policy only samples 10%.

### 5.6. Why `THROW` Is Dangerous Even Though Business Committed All 1,200

`THROW` always executes `executed.incrementAndGet(id)` before running the hook. For the 110 IDs divisible by 11, the hook throws `IllegalStateException` **after commit**:

- `businessMissing=0`: all IDs executed once.
- `errors=110`: callers receive an exception from the observer.
- `afterCommitErrors=110`: the side effect already happened before the failure.
- `missingEvents=110`: the hook never emitted events for the failing IDs.
- `overallPass=false` because the return/exception contract is not met.

This is a very hard failure mode to spot if you only watch a throughput dashboard: callers may automatically retry because they think the business request was not processed. If the request is not idempotent, retries can create duplicate side effects.

**API distinction:** `THROW` here is an exception from a **hook inside a business method**. It is not an exception thrown by `ClassFileTransformer.transform` during class definition; the two places have different exception-handling contracts.

### 5.7. Measurement Timing and Scope of the Small Benchmark

- `CountDownLatch ready/go` ensures all four worker tasks are ready before the start mark, reducing skew from thread creation during measurement.
- Each worker processes a disjoint set of IDs, with one outcome per ID.
- `System.nanoTime()` wraps **`Service.handle`**; percentile calculations receive all 1,200 samples, **including calls that throw exceptions**.
- Elapsed wall time is measured from releasing the latch until all `Future`s are collected; throughput here is **completed attempted operations/time**, not successful outcomes/time.
- `AtomicIntegerArray` lets us verify that every business ID executed the exact expected number of times.
- `ConcurrentHashMap.newKeySet` stores event IDs by value identity; this stores **logical integer IDs**, not heap object identity. `emissions` helps detect cases where the same ID is emitted multiple times that a `Set` would otherwise hide.
- `Arrays.sort` and nearest-rank make `p50/p95/p99` interpretation transparent.
- The `Service` class, collections, and counters **also introduce overhead**; this is an intentional test harness, not a pure overhead measurement of a real Java agent.

**Measurement pitfall to avoid:** `p99` of 1,200 very fast calls has high noise. A single run without warm-up/forks/repetitions is insufficient to conclude that a 2–3% difference is statistically significant. Use appropriate benchmarking tools and procedures when making production decisions.

## 6. Translating the Demo to a Real Agent

### 6.1. Three-Layer Agent Testing

A Java agent typically consists of:

~~~text
Agent startup/attach
       |
       v
ClassFileTransformer.transform(...) 
       |  produces/copies valid bytes, returns byte[] or null
       v
Class definition / retransform accepted by JVM
       |
       v
Instrumented business method is called
       |
       +--> probe/hook handles context and telemetry
       |
       +--> business return/exception/side effects
       v
Async queue / exporter -> collector / backend
~~~

Each layer has a different quality gate:

1. **Agent installation:** Can `premain/agentmain` be invoked? Is the transformer registered properly? Are `isRetransformClassesSupported`/`isModifiableClass` checked if loaded classes need modification?
2. **Bytecode correctness:** Are bytes valid, accepted by the verifier, with correct labels/StackMapTable/exception handlers, and are helpers visible to the target class loader and modules?
3. **Runtime correctness:** Do methods still return correct results, preserve exceptions/locks/context, emit complete and accurate events, and does the exporter behave under saturation?

**Do not use `addTransformer` returning or `transform` being called as proof that all business methods were instrumented.** A load-time transformer may not have touched classes loaded before agent attach; retransformation is needed if capabilities and scope permit.

### 6.2. Special Checks for `ClassFileTransformer`

Tests should cover:

- Classes loaded concurrently across multiple threads, multiple class loaders, and named modules.
- Transformer filters that select only needed classes and do not recurse into the agent's own helper/logging packages.
- Never mutating the input `classfileBuffer` in-place; creating a new byte array when modifying, and returning `null` when unchanged.
- Never inserting duplicate hooks across multiple retransformations (idempotency).
- Never altering return/exception/finally/monitor semantics when rewriting bytecode.
- Testing classes with overloads, bridge methods, constructors, synchronized methods, `try/finally`, and early returns.
- If `transform` throws an exception, logging/classifying the error rather than assuming the JVM will block class loading: the specification allows continuing with other transformers.
- Verifying helper visibility per target loader/module; a `NoClassDefFoundError` after instrumentation is a correctness failure, regardless of how good p99 looked earlier.

### 6.3. Testing Hooks with Lifecycle and Backpressure

At runtime, beyond synthetic `SAFE`/`DROP`/`THROW`, create scenarios for:

| Fault Injection | What to Confirm |
|---|---|
| Collector 10–100x slower | Do requests remain correct? Does the queue/sink apply backpressure/drop per policy? |
| Queue hits capacity | No OOM/unbounded growth; dropped metric is accurate |
| Exporter throws exception | Exception does not alter the business contract if telemetry is best-effort |
| Event serialization fails | Error is counted, never sending an empty payload and reporting success |
| Thread is interrupted | Interrupt/cancellation semantics are not lost |
| Sink needs a lock held by business code | No lock inversion/deadlock |
| Helper calls an instrumented method | No infinite recursion/reentrancy |
| Config reload under live traffic | Config visibility and policy remain consistent |
| Duplicate delivery/retry | Deduplication/idempotency matches contract |
| Shutdown/redeploy | Reasonable flush deadline, no class loaders/threads kept alive indefinitely |

If telemetry is defined as **at-most-once** or **best effort**, do not test for "exactly-once delivery" against the contract. The key requirement is **writing down the contract first**, then testing against that exact contract, including dropped samples when permitted.

## 7. Designing Fair Experiments for Throughput and Latency

### 7.1. Put All Variables into the Same Configuration Matrix

A basic matrix:

| Factor | Example |
|---|---|
| JVM/JDK | Same vendor, version, GC, heap, CPU limits |
| Workload | Same request mix, payload sizes, read/write ratio |
| Offered load | 100, 500, 1,000 req/s or a rate suited to the system |
| Concurrency | 1, 4, 16, 64 in-flight; same queue/connection policy |
| Instrumentation | Baseline, agent enabled, agent disabled, sampling, export enabled |
| Test phase | Warm-up, steady-state measurement, cooldown |
| Data dependencies | Same DB/cache state or reset fixtures |
| Metrics | Success/errors, wrong outputs, p50/p95/p99, throughput, GC/CPU |
| Telemetry | Offered events, emitted, queued, dropped, exported, acknowledged |
| Repetitions | Multiple runs/forks, alternating order when appropriate to reduce bias |

**Do not run the baseline once on an idle CPU and the agent once during peak load and call the difference instrumentation overhead.** Experiments must compare under equivalent conditions.

### 7.2. Warm-up and JIT Affect Results

Java has tiered compilation, profiling, class initialization, and GC. Running the first few hundred operations can measure many costs that are not steady-state. This article's runnable example **is intentionally not a scientific benchmark**, because it tests logic first and then observes varying measurements.

To microbenchmark a small hook, use **OpenJDK JMH** to manage warm-up, forks, iterations, and blackhole/escape-analysis issues. JMH does not replace concurrency correctness or telemetry completeness testing.

For end-to-end tests, use an external load generator with offered-load control and server metrics, warm up sufficiently, capture GC/JFR, repeat, and inspect confidence intervals/distributions.

### 7.3. p99 Can Look "Artificially Good" by Measuring Only Successes

Suppose there are 1,000 requests:

~~~text
900 succeed quickly
100 fail immediately due to hook

If reporting only p99 of the 900 successes:
    it may be lower than baseline.

If reporting the full summary properly:
    failure rate = 10%
    business contract = FAIL
~~~

Similarly, if **timeouts** are not recorded as latency samples or requests sitting in a queue are never accepted, the tail can be hidden. Separate metrics by **attempted**, **succeeded**, **failed**, **timed-out**, and **dropped/rejected**, and document the sample set used for percentiles.

### 7.4. Coordinated Omission

A closed-loop load generator typically waits for a response before sending the next request. When the server pauses for 1 second, it stops issuing new requests during that 1 second. If latency is computed only on requests that were actually sent, many delayed requests that "should have arrived" are missing. This is a form of **coordinated omission**.

To measure an SLO against a fixed offered rate, you need to:

- Record **scheduled/request creation time** or use an open-loop model suited to the goal.
- Separate queue waiting time from service time.
- Include timeouts, rejections, and missed scheduled requests in reports rather than hiding them.
- Use histograms/profilers with explicit accounting; some libraries like HdrHistogram support correction based on the expected sampling interval, provided you understand the assumptions.

A low `p99` from a client that stops sending when the backend slows down does not prove a good user experience.

### 7.5. Checking Measurement Accuracy

- Measure elapsed duration with `System.nanoTime` instead of `currentTimeMillis`; wall-clock time can be adjusted by the system.
- Timers have overhead, especially for microsecond/nanosecond methods; measure/subtract overhead when needed.
- Percentiles require enough samples: p99.9 is unstable with only a few hundred operations.
- If using histogram buckets, tail detail depends on bucket resolution/boundaries.
- GC, safepoints, CPU throttling, and scheduling affect the tail; log sources of noise.
- When multiple threads update a global histogram, contention on the metric itself can slow down the app; consider per-thread buffers/aggregation with bounded memory.
- Async exporter latency must not be hidden by measuring only enqueue; track delivered/ack latency if the contract requires it.

## 8. Run Correctness Tests First, Then Make Performance Decisions

A decision flow can follow this process:

~~~text
A. Run functional oracle and concurrency stress
       |
       +-- any business invariant broken? --> REJECT
       |
       +-- telemetry completeness/contract wrong? --> REJECT
       |
       +-- deadlock, starvation, leak, recursion? --> REJECT
       |
       v
B. Run benchmark with warm-up + repeated runs
       |
       +-- successful throughput below SLO? --> REJECT/OPTIMIZE
       |
       +-- p95/p99/p99.9 exceeds SLO? --> REJECT/OPTIMIZE
       |
       +-- CPU, GC, allocations, native memory exceed budget? --> REJECT/OPTIMIZE
       |
       v
C. Run fault injection + deploy/rollback test
       |
       +-- results still satisfy contract? --> ACCEPT
       +-- do not satisfy?               --> REJECT/REDESIGN
~~~

**Step A is not a single single-threaded run.** It includes multi-threaded stress, property-based tests, and fault injection for exception paths, full queues, down collectors, retransformation, and shutdown under traffic.

### 8.1. "Pass" Thresholds Depend on the Contract

For example, a critical service might specify:

~~~text
Mandatory:
- wrong outputs = 0
- duplicate side effects = 0
- unexpected exceptions = 0
- required telemetry events missing = 0 (if full coverage)
- no deadlocks / leaked executor threads

Performance budget:
- p99 end-to-end latency increase no more than X%
- successful throughput decrease no more than Y%
- CPU overhead increase no more than Z%
- exporter queue bounded, drops within quota if sampling
~~~

The letters `X/Y/Z` here are **placeholders representing project budgets**, **not thresholds prescribed by Java/JVM**. In practice, replace them with owned SLOs, load conditions, and clear collection methods.

## 9. Common Instrumentation Benchmark Anti-Patterns

### 9.1. Measuring Only Throughput Without Checking Output

A hook that skips work or returns early can improve throughput while breaking business logic. You always need separate correctness oracles (return/exception/side effects) and telemetry oracles.

### 9.2. Looking Only at p99 of Successful Requests

If a hook makes requests fail fast, the percentiles of the remaining successes can look better. Report error rates, partial commits, timeouts, and failure latencies by cohort.

### 9.3. Summing Total Event Count and Concluding "Complete"

Suppose events are needed for IDs 1..100, but ID 7 is sent twice and ID 8 is never sent. The total count is still 100, yet **one event is missing and one is duplicated**. Track per-ID coverage and uniqueness.

### 9.4. Using a Non-Thread-Safe `HashMap` as a Shared Sink

Under concurrency, a shared non-thread-safe map/list can cause data loss, corruption, or exceptions. Choose appropriate data structures/concurrency policies and test under real load. Also note that `ConcurrentHashMap` does not make multi-step check-then-act sequences automatically atomic without proper atomic operations.

### 9.5. Logging from Inside the Logging Hook Itself

If a hook calls a method that is itself instrumented, it can trigger recursion, stack overflow, or deadlock. Ignore internal packages/helpers and guard against reentrancy as required.

### 9.6. Benchmarking Only Once Without Warm-up

Results may reflect class initialization, JIT compilation, GC, or host load differences. Do not use a single p99 number from a tiny benchmark to make release decisions.

### 9.7. Not Measuring the Queue/Exporter

An async agent can keep requests fast while the queue grows endlessly and then loses data or OOMs. Measure backlog, enqueue/reject, drops, flushes, export errors, and acknowledged delivery.

### 9.8. Ignoring Active Frames and Class Transformation Boundaries

After retransform/redefine, active frames may continue executing old bytecode; when comparing immediately after rollout, pay attention to when the hook takes effect. Classes loaded before attach may not be transformed if only `addTransformer` was called.

### 9.9. Counting Sampling Drops as Corruption Without Understanding Policy

If the contract allows 10% sampling, missing 90% of events is **policy**, not automatically a bug. However, verify that the policy is applied correctly, unbiased by request error/latency, and with clear metadata/loss metrics.

### 9.10. "No Deadlock Observed Once" Means Deadlock-Free

Deadlocks may require rare thread scheduling. Run stress tests, fault injection, and thread-dump watchdogs; where possible, use appropriate race/lock analysis tools. Do not promise formal proof from a single stress test.

## 10. Experimental Checklist

### 10.1. Before Running

- [ ] Document the business return/exception/side effects contract.
- [ ] Document the telemetry contract: 1:1, sampled, at-most-once, or best effort.
- [ ] Define which latency is measured: client/server/method/exporter.
- [ ] Distinguish offered requests, completed attempts, and successful outcomes.
- [ ] Use the same workload, JVM/JDK, GC, heap, CPU quotas, and backend fixtures.
- [ ] Choose concurrency and offered load levels, not just thread count.
- [ ] Design per-request-ID oracles for duplicates/missing events, payloads, and status.
- [ ] Plan fault scenarios: exporter timeout, queue full, reentrant hooks, shutdown.

### 10.2. During Execution

- [ ] Count every request ID: submitted, completed, failed, timed out, rejected.
- [ ] Verify payloads, return values, exception classes, and side effects.
- [ ] Do not compare total event counts alone: reconcile per-ID coverage.
- [ ] Collect p50/p95/p99 over a clearly defined sample set, including failures where appropriate.
- [ ] Collect CPU, allocations, GC, thread contention, queue backlog, and memory.
- [ ] If sampling is intentional, use expected sampled IDs/rates as the oracle.
- [ ] Record the Java agent version, transformer config, and target classloader.
- [ ] Prevent harness logging/metrics from skewing the workload itself.
- [ ] Detect timeouts/deadlocks with a watchdog instead of letting tests hang indefinitely.

### 10.3. After Execution

- [ ] Did all business invariants pass?
- [ ] Did all telemetry invariants pass per contract?
- [ ] Were liveness and data races stressed deeply enough?
- [ ] Were there enough warm-up/repeats/forks to trust performance differences?
- [ ] Were offered rate, queueing, and coordinated omission accounted for?
- [ ] Were baseline and agent compared under identical conditions?
- [ ] Were completion throughput and success throughput separated?
- [ ] Were config reload, attach/retransform, and rollback verified?
- [ ] Are benchmark limitations clearly stated: small workload, single host, no collector, network unmeasured?

## 11. Knowledge Self-Check

**1.** Why can `DROP` in the demo achieve high throughput yet have `pass=false`?

> Because it drops 93 telemetry events in violation of the full-coverage contract. Business logic remains correct, but telemetry is wrong; performance cannot compensate for a correctness failure.

**2.** In `THROW`, `businessMissing=0` but `errors=110`; what does this mean?

> Business operations recorded their side effects, yet the hook threw an exception afterward, causing 110 callers to see a failure. This is a partial commit and carries a risk of duplicate retries.

**3.** Does a low p99 prove that no data loss occurred?

> No. p99 only describes the distribution of measured latencies; it does not check event identity/coverage or content.

**4.** Why not just count total events?

> Duplicating one ID and missing another can leave the total unchanged. You must compare each logical ID and its uniqueness.

**5.** Why separate completed throughput from successful throughput?

> A program can complete quickly by failing fast. Only successful throughput reflects the capacity to serve requests successfully per contract.

**6.** Does `System.nanoTime` wrapping `Service.handle` measure the time a request waits in a queue?

> No. That is method latency starting when the worker begins the call. Client end-to-end latency and queue waiting are separate scopes.

**7.** Is `ClassFileTransformer.transform` throwing an exception the same as an exception from a hook injected into a method?

> No. The Javadoc allows the transformer pipeline to continue when a transform callback throws; an exception from a hook executing in business code can propagate to the caller and alter behavior if not handled properly.

**8.** Does "Safe" in the demo prove a production agent is safe?

> Not yet. The demo only tests a small model without bytecode rewriting, an exporter, GC/JFR impact, module/classloader complexity, or shutdown/race/deadlock fault paths.

**9.** In a system with 10% sampling, should the telemetry oracle require events for all IDs?

> No, unless the contract requires full capture. You must verify the exact selected sample set, rate, and drop policy, rather than applying the wrong gate.

**10.** Why is a small benchmark without warm-up unsuitable for deciding a 2% overhead?

> JIT compilation, GC, scheduler, cache warm-up, and timer overhead can exceed the difference; repeated runs/forks and distribution analysis are required.

**11.** What is coordinated omission?

> When a slow system causes a load generator to pause or issue fewer requests, the requests that would have arrived during the slowdown are omitted from the latency sample, making the tail look lower than the experience under the offered load.

**12.** Instrumentation measured successfully, but the telemetry exporter has not yet sent to the collector: is it "delivered"?

> Not yet. Hook invoked, enqueued, and export acknowledged are different milestones; status must follow the actual delivery contract.

**13.** If a Java agent uses a transformer and only calls `addTransformer` after attach, are already-loaded classes automatically instrumented?

> No. Registration does not automatically replay loaded classes; to process existing classes, you must use retransform/redefine mechanisms appropriate for the capability and target.

**14.** When `DROP` has better throughput/p99 than `SAFE`, what is the right decision?

> Do not treat DROP as a win if full telemetry is required. Fix the data loss first, then benchmark the contract-compliant configuration.

## 12. References

- Java SE 17 — `java.lang.instrument.Instrumentation`: `addTransformer`, `retransformClasses`, agent runtime lifecycle: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Java SE 17 — `ClassFileTransformer`: callbacks at load/redefine/retransform, exception semantics, `return null`, and byte array constraints: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- Java SE 17 — `java.util.concurrent`: `CountDownLatch`, `ExecutorService`, `Future`, `ConcurrentHashMap`, `AtomicIntegerArray`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 17 — `System.nanoTime()`: elapsed-time measurements: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- OpenJDK JMH — Java Microbenchmark Harness: https://github.com/openjdk/jmh
- HdrHistogram — histogram recording and coordinated omission correction concept: https://hdrhistogram.github.io/HdrHistogram/JavaDoc/
