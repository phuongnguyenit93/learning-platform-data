# 17.3. Identifying CPU-Heavy Loops, Expensive Algorithms, and Unexpected Repeated Work

## Objectives

After this lesson, you will be able to:

- Distinguish **CPU actually busy executing code** from **wall-clock latency** caused by I/O, lock contention, GC, or the scheduler; avoid jumping to a root cause from a single CPU metric.
- Recognize three categories of issues: **hot loops/busy spins**, **high-complexity algorithms**, and **unexpectedly repeated work**.
- Use OS metrics, **JFR/JDK Mission Control**, thread dumps, counters, and input-size scaling tests to trace from symptom to code location.
- Understand the role of **JIT warm-up/inlining**, GC, native code, and multi-core environments in measurement results.
- Propose verified fixes: replace polling with proper blocking, reduce algorithmic complexity, hoist/cache valid invariant work, and use JMH or stable measurements to confirm gains.

Examples use **Java 17+**. Linux tools are noted explicitly; JDK Mission Control (JMC) UI labels may vary across versions.

## 1. Ask the Right Questions Before Hunting for a "Slow Line of Code"

**CPU-bound** means execution speed is limited primarily by the amount of CPU work: adding compute capacity or reducing computations can improve throughput/latency. **I/O-bound** or **contention-bound** workloads can exhibit high latency yet relatively low CPU because threads are waiting on disk/network/locks.

The three symptoms in this lesson differ:

| Problem Type | Description | Common Signs | Examples |
|---|---|---|---|
| **CPU-heavy loop** | Runs/spins continuously, possibly without proportional progress | One or a few threads frequently executing; samples repeat inside loop/predicate | `while (!ready) { }`, polling a queue without sleep/block |
| **Expensive algorithm** | Each call performs too many steps relative to input size | CPU grows non-linearly with `n`; hot stacks in comparisons, sorting, regex, parsing | Checking pairs with nested `O(n²)` loops instead of counting via hash map |
| **Unexpected repeated work** | Valid work performed far more times than business logic requires | Invocation counters spike, same stack across many requests/iterations; can drive CPU, I/O, or allocation | Loading config per item, N+1 queries, retry loops, duplicate scheduler runs |

A code path appearing "hot" in a profiler is not necessarily the **root cause**. It might be legitimate work handling high load, a framework hot path, GC triggered by allocations elsewhere, or a call multiplied in frequency by a caller.

**Fundamental relationship:**

```text
Total cost ≈ number of executions × cost per execution
           + memory / GC / synchronization / system overhead
```

You need to answer simultaneously: **which part is busy?** (where), **how much does each execution cost?** (cost), **why does it run so many times?** (frequency), **when?** (time window), and **is the output still required?** (correctness).

## 2. CPU Usage, CPU Time, and Elapsed Time Are Not the Same

### 2.1. Three Quantities Often Conflated

- **Process CPU usage**: the CPU share consumed by the *entire process* over an interval. Depending on tool/convention, a process running concurrently across multiple cores can display above **100%**.
- **Thread CPU time**: the time a thread actually spent executing on a CPU in user mode and/or kernel mode. On HotSpot, this can be observed via the OS or `ThreadMXBean` for **platform threads** when supported/enabled.
- **Wall-clock elapsed time**: real elapsed time from start to finish of work; includes CPU, waiting for I/O, locks, sleep, pauses, scheduler, and GC.

For example, an HTTP request takes **500 ms** due to 480 ms waiting on the network and 20 ms of computation. The request is **slow in wall time**, not 500 ms of CPU. Conversely, an unthrottled polling loop can keep a core busy nearly continuously even when throughput is 0.

### 2.2. Observing CPU Time in Java Code

In a **platform thread**, you can take measurements with `java.lang.management.ThreadMXBean` when supported by the JVM:

```java
// Illustrative snippet placed around work in a platform thread;
 // requires importing java.lang.management.* and actual processing logic.
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
if (bean.isCurrentThreadCpuTimeSupported()
        && bean.isThreadCpuTimeEnabled()) {
    long cpuBefore = bean.getCurrentThreadCpuTime();
    long wallBefore = System.nanoTime();

    // Run the section of work to observe here.

    long wallNanos = System.nanoTime() - wallBefore;
    long cpuNanos = bean.getCurrentThreadCpuTime() - cpuBefore;
    System.out.println("wallNs=" + wallNanos + ", cpuNs=" + cpuNanos);
}
```

This is an **illustrative snippet**, not a standalone Java file. Do not compute `cpuNanos` if the method is unsupported or returns `-1`. Nanosecond resolution in the API **does not guarantee nanosecond accuracy**. `System.nanoTime()` measures **elapsed-time deltas**, not calendar/wall-clock time.

**Modern Java note:** traditional `ThreadMXBean` reports CPU time for **platform threads**, not virtual threads; `getThreadCpuTime(id)` can return `-1` for virtual threads, terminated threads, or when measurement is disabled. If a workload uses virtual threads, do not infer "zero CPU" just because the MXBean does not report virtual-thread CPU time. Use JFR/OS/carrier profiling and appropriate observability mechanisms.

## 3. Outside-In Investigation Workflow

### Step 1 — Confirm the Symptom and Scope

Collect **per-process CPU**, **host/container CPU**, throughput, request rate, p95/p99 latency, error rate, allocation/GC, and active job counts together.

- Host at 90% CPU while JVM is at 5%: no evidence yet of a CPU hotspot inside the JVM; inspect other processes.
- JVM CPU rises along with a 4x traffic increase: may simply be legitimate load; compare **CPU/request** or **work/item**, not absolute CPU alone.
- JVM CPU rises while traffic stays flat and latency/queues grow: suspect a hot loop, non-linear algorithm, retry amplification, leaked tasks/jobs, or GC.
- Latency jumps sharply while JVM CPU stays low: prioritize I/O, lock contention, upstream dependencies, or starvation; do not immediately blame an algorithm.

### Step 2 — Check Which Thread Is Actually Consuming CPU

On **Linux**, once you know the JVM PID:

```bash
PID=12345                       # Replace with actual PID
top -H -p "$PID"               # Threads of the process
ps -L -p "$PID" -o pid,tid,pcpu,stat,comm
```

`%CPU` units and interpretation depend on the tool and sampling interval; do not infer core usage from a single snapshot. When using `top -H`, the PID column on thread rows typically corresponds to the Linux **TID/LWP**.

Take a thread dump around the same time:

```bash
jcmd "$PID" Thread.print -l
```

For **platform threads**, you can match the **decimal TID** in `top -H` with the **hex** `nid` in a HotSpot thread dump:

```bash
TID=12346
printf '%x\n' "$TID"          # nid is usually shown as 0x303a...
```

Only correlate when you know you are inspecting the exact PID/thread and the runtime supports that identifier mapping. Thread names can collide, IDs change across restarts, and the virtual-thread/carrier model removes the one-to-one mapping between OS threads and application tasks.

Take **multiple thread dumps spaced closely apart**, rather than relying on one snapshot. A stack repeating in the same loop on a thread consuming CPU is a much stronger clue than seeing `RUNNABLE` once. Java's `RUNNABLE` **does not mean** the thread is definitely holding a CPU at that instant; it can also include cases inside a native call.

### Step 3 — Capture CPU Sampling with JFR

When you have JVM access and a JDK available:

```bash
jcmd -l
jcmd <PID> JFR.start name=CpuCheck settings=profile duration=60s filename=cpu-check.jfr
jcmd <PID> JFR.check
```

**Replace `<PID>` with the actual PID** without typing literal `< >`. Choose a window **under load/incident**; the `profile` configuration typically captures more profiling samples than `default` and carries higher overhead. A command with `duration` stops automatically when the duration elapses and writes the recording to the filename. For long-running recordings, use `JFR.dump` to snapshot data without stopping the recording.

On a host with the file:

```bash
jfr summary cpu-check.jfr
jfr print --events jdk.ExecutionSample cpu-check.jfr
```

`jfr print` can output very many lines. `jdk.ExecutionSample` must be **enabled and actually emit events** to have samples; a file with few or no samples does not prove code did not run.

Open `cpu-check.jfr` in **JDK Mission Control** and inspect **Code / Method Profiling / Hot Methods / Call Tree** (labels vary by version). Select the time range right when CPU climbed. Read:

- **Hot Methods / execution samples**: methods or stacks appearing frequently when CPU is executing code; this is a **sample distribution**, not an absolute timing table per invocation.
- **Call Tree / Stack Trace**: who calls the hot method; trace from `for`/`while` or expensive operations up to the caller generating the frequency.
- **`jdk.CPULoad` / `jdk.ThreadCPULoad`** if present: JVM and thread load trends; verify events exist in the file with enough samples.
- **GC / Compilation / Allocation**: separate CPU executing business code from GC, JIT compiler, or allocation cost.
- **Threads / Locks / I/O**: inspect wait time when wall latency is high.

Per Oracle documentation, execution sampling focuses on threads actively executing code and typically does not sample threads sleeping, waiting on I/O, or blocked on locks. **Few CPU samples may mean threads are waiting**, not that requests are fast. Read stacks and time windows alongside OS metrics.

### Step 4 — Turn a Hot Stack into a Testable Hypothesis

An example stack:

```text
OrderService.search()
  -> OrderMatcher.findDuplicates()
     -> OrderMatcher.comparePairs()
```

If `comparePairs()` dominates samples, do not stop at the method name. Ask:

1. How large is `n`? Are there nested loops, regex backtracking, or repeated parsing/sorting?
2. Is there a cache/index/hash map more suitable than an exhaustive scan?
3. How many times is this method called per request/batch?
4. Is there caller retry, duplicate scheduled execution, cache misses, or a repeated pipeline multiplying the cost?
5. Are there outputs or side effects that must be preserved when optimizing?

Add **counters for invocation count, items scanned, pairs compared, and retry count**, then compare against business expectations. This data usually distinguishes "one call is too expensive" from "a normal call is invoked too many times."

## 4. Identifying CPU-Heavy Loops

### 4.1. Busy Spin: Waiting Without Truly Sleeping

Contrasting example:

```java
// Illustrates an ANTI-PATTERN, not a standalone program:
while (!ready.get()) {
    // No blocking/wait; continuously reads the same state.
}
```

If `ready` does not flip to `true`, the loop runs millions of iterations and can occupy nearly an entire core while **making no progress**. Using `Thread.onSpinWait()` can give a hint to the CPU in certain intentional spin loops, but it **does not turn a busy spin into blocking**; it still consumes CPU resources.

A better option when wait times are not ultra-short is a primitive capable of **waiting for a signal**:

```java
// Illustrative: requires declaring the latch and the signaling side;
 // this is a snippet, not a standalone program.
CountDownLatch readySignal = new CountDownLatch(1);

// Thread that needs to wait:
readySignal.await();

// Thread completing initialization:
readySignal.countDown();
```

In real code, you can use `BlockingQueue.take()`, `Semaphore.acquire()`, `Lock/Condition.await()`, `CompletableFuture`, or asynchronous I/O. Pick the right primitive and handle **interrupt/timeout/cancellation**; do not swap in `Thread.sleep(1)` as a default fix because it still polls while altering latency.

### 4.2. Loops with Wrong Exit Conditions or Abnormal Inputs

Common examples:

- `while` with a condition that stays true because state is not updated or lacks cross-thread visibility guarantees.
- Faulty retries: error results immediately retry without limit, backoff, jitter, or circuit breaking.
- A consumer reading an empty queue and retrying continuously.
- Polling a state with a tiny interval and no budget.
- A loop making progress while input grows unboundedly due to a bug.

How to distinguish: inspect **loop-iteration counters, retry rate, exit condition, per-iteration outcome**, and **thread CPU**; run a short sampling/timeboxed check. Fix termination logic and synchronization before optimizing instructions. For retries, cap attempts/budget, use controlled backoff, and avoid creating a storm when a dependency fails.

### 4.3. When Spinning May Be Intentional

Some ultra-low-latency mechanisms may spin very briefly in a specifically designed and benchmarked region. However, you must prove the latency gain outweighs monopolizing a core, enforce a **bounded spin**, and fall back to blocking. Do not generalize optimizations from runtime/lock-free libraries to ordinary business loops.

## 5. Expensive Algorithms: Using Work Units and Complexity to Explain

### 5.1. Example: Finding All Equal Value Pairs

Suppose you need to count index pairs `(i, j)` with `i < j` and `a[i] == a[j]`.

The direct approach uses two loops:

```java
for (int i = 0; i < values.length; i++) {
    for (int j = i + 1; j < values.length; j++) {
        if (values[i] == values[j]) {
            pairs++;
        }
    }
}
```

This is an **illustrative snippet**; `values` and `pairs` must exist. There are exactly `n(n - 1)/2` comparisons, i.e., `O(n²)`. When `n` doubles, the number of pairs compared **roughly quadruples** (not always an exact 4x due to constants and the `-1` term).

Instead of comparing all pairs, use a map recording how many times each value has appeared. When reading a value `v`, if it has already been seen `k` times, exactly `k` new pairs are formed. That requires only **a single pass**, expected `O(n)` assuming efficient average hash map operations, trading extra memory proportional to the number of distinct values.

### 5.2. When `O(n log n)`/`O(n²)` Is Not Enough to Decide

Two nested loops are not automatically a bug. If inputs are always tiny or an algorithm genuinely needs every pair, the cost can be acceptable. Conversely, a single regex or backtracking algorithm can run extremely slowly even from one call site. Check:

- **Actual** input size bounds and data shapes.
- Worst-case and pathological inputs; e.g., regexes can suffer **catastrophic backtracking** on certain inputs.
- DB or network queries triggered inside the loop (N+1): latency may be dominated by I/O even when the code looks `O(n)`.
- Temporary object creations; allocation/GC also consume CPU.
- Proper `HashMap` trade-offs: `hashCode`/`equals`, collisions, memory, and key stability; average complexity is not an invariant for every input.

A good test keeps **business results unchanged**, measures `n` and work units, and compares CPU/wall time on a representative workload. Avoid micro-optimizing code that is not on the hot path.

## 6. Unexpected Repeated Work: "Right Once" Called Too Many Times

In real systems, the flaw is not necessarily inside the hot method itself:

```text
1 request
  -> 100 items
     -> loadRules() per item
     -> normalize() per item even for identical inputs
     -> lookupUser() repeatedly for the same key
     -> unbounded retry operation on error
```

This is a **diagram**, not Java source code. Each `loadRules` call might look fast in a microbenchmark, yet when called thousands of times per request across hundreds of requests/second, CPU, allocations, lock contention, or I/O all climb.

Patterns to investigate:

- **Loop-invariant work:** the result of a computation/parse/config lookup never changes across a batch yet is recomputed each iteration. It can be computed **before the loop**.
- **N+1 access:** querying data item-by-item instead of using batch fetches or valid caching.
- **Abnormal cache misses** from wrong keys/TTLs or overly broad invalidation; inspect hit/miss rates and cost.
- **Duplicate scheduling:** the same job running on multiple instances or triggered concurrently unexpectedly.
- **Retry amplification:** a failing dependency multiplies execution attempts; enforce budgets and idempotency.
- **Repeated transformation/serialization:** parsing the same JSON, compiling the same regex, or mapping the same object across layers.
- **Unmemoized recursive traversal:** recomputing the same subproblems in a tree/graph (e.g., naive Fibonacci or dynamic programming missing memoization).

**Do not cache unconditionally:** data may vary per tenant/request and requires proper isolation, TTL/invalidation, thread safety, memory bounds, and freshness guarantees. Hoisting `loadRules()` outside a loop is only valid when rules genuinely **do not need to be re-read per item**. With side effects, skipping calls can alter behavior.

### Evidence of Duplicated Work

Place counters/traces at entry points: `jobsStarted`, `batchSize`, `configLoads`, `queriesPerRequest`, `retriesPerKey`, `cacheHits/cacheMisses`. Compare against expected ratios; e.g., expecting one config load per batch while observing **3,000 loads for 3,000 items** is stronger evidence than just looking at `loadRules` on a stack.

## 7. Runnable Java 17+: Same Result, Different Complexity and Call Counts

The example below demonstrates **both anomaly patterns with deterministic counts**: `O(n²)` pair comparison versus hash-map counting, and loading rules per request instead of once per batch. It also includes a mode that creates an **intentional CPU hot loop** so you can practice with the JFR profiler.

Create **`CpuPatternDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CpuPatternDemo {
    private static volatile long blackhole;

    private record Result(long pairs, long operations) {}

    private static Result quadratic(int[] input) {
        long pairs = 0;
        long comparisons = 0;
        for (int i = 0; i < input.length; i++) {
            for (int j = i + 1; j < input.length; j++) {
                comparisons++;
                if (input[i] == input[j]) pairs++;
            }
        }
        return new Result(pairs, comparisons);
    }

    private static Result linear(int[] input) {
        Map<Integer, Integer> previous = new HashMap<>();
        long pairs = 0;
        long visits = 0;
        for (int value : input) {
            int seen = previous.getOrDefault(value, 0);
            pairs += seen;
            previous.put(value, seen + 1);
            visits++;
        }
        return new Result(pairs, visits);
    }

    private static int loadRules(AtomicInteger calls) {
        calls.incrementAndGet();
        return 7;
    }

    private static void profileHotLoop(int seconds) {
        if (seconds < 1 || seconds > 60) {
            throw new IllegalArgumentException("seconds must be 1..60");
        }
        long until = System.nanoTime() + TimeUnit.SECONDS.toNanos(seconds);
        long accumulator = 1;
        while (System.nanoTime() < until) {
            for (int i = 0; i < 100_000; i++) {
                accumulator = (accumulator * 1664525L + 1013904223L) & 0x7fffffffL;
            }
            blackhole = accumulator;
        }
        System.out.println("Profile run done");
    }

    public static void main(String[] args) {
        if (args.length == 2 && "profile".equals(args[0])) {
            profileHotLoop(Integer.parseInt(args[1]));
            return;
        }

        int n = 6000;
        int distinct = 200;
        int[] input = new int[n];
        for (int i = 0; i < input.length; i++) {
            input[i] = i % distinct;
        }

        Result slow = quadratic(input);
        Result fast = linear(input);
        if (slow.pairs() != fast.pairs()) {
            throw new AssertionError("Results differ");
        }

        System.out.println("Equal pairs: " + slow.pairs());
        System.out.println("Quadratic comparisons: " + slow.operations());
        System.out.println("Linear visits: " + fast.operations());

        int requests = 3000;
        AtomicInteger repeatedCalls = new AtomicInteger();
        long repeatedTotal = 0;
        for (int i = 0; i < requests; i++) {
            repeatedTotal += loadRules(repeatedCalls);
        }

        AtomicInteger cachedCalls = new AtomicInteger();
        int rule = loadRules(cachedCalls);
        long cachedTotal = 0;
        for (int i = 0; i < requests; i++) {
            cachedTotal += rule;
        }

        System.out.println("Repeated rule loads: " + repeatedCalls.get());
        System.out.println("Once-per-batch rule loads: " + cachedCalls.get());
        System.out.println("Same rule result: " + (repeatedTotal == cachedTotal));
    }
}
```

### 7.1. Run the Operation-Count Comparison

```bash
javac CpuPatternDemo.java
java CpuPatternDemo
```

**Exact stdout** of the default run:

```text
Equal pairs: 87000
Quadratic comparisons: 17997000
Linear visits: 6000
Repeated rule loads: 3000
Once-per-batch rule loads: 1
Same rule result: true
```

Explanation:

- `n = 6000`, with `200` distinct values repeating evenly, each appearing `30` times. Total matching pairs: `200 × 30 × 29 / 2 = 87,000`.
- `quadratic` checks `6000 × 5999 / 2 = 17,997,000` pairs, even though only 87,000 pairs match.
- `linear` visits exactly 6,000 inputs, updating the `Map` to count new pairs; both approaches return the **same result**.
- `loadRules` here simply returns a constant, **not a real CPU-heavy config operation**. The counter illustrates **3,000 calls versus 1 call**; it does not prove a specific production CPU savings.
- Only hoist the load before the loop when rules and side effects permit; if config varies per request, caching like this would be a **business-logic bug**.

**Do not treat 17,997,000 / 6,000 as a CPU speedup ratio.** The operation counts in the two algorithms have *different units* (integer comparisons vs. hash map lookups) as well as different JIT, allocation, and memory-locality behavior. It demonstrates **work shape**, not exact runtime speed.

### 7.2. Capture JFR to See the CPU Hot Loop

Run **profiling mode** of the same program:

```bash
java -XX:StartFlightRecording=filename=cpu-pattern.jfr,settings=profile,dumponexit=true CpuPatternDemo profile 15
jfr summary cpu-pattern.jfr
jfr print --events jdk.ExecutionSample cpu-pattern.jfr
```

The program runs the compute loop for about **15 seconds**, then prints:

```text
Profile run done
```

With `dumponexit=true`, the JVM writes the recording on normal exit; `cpu-pattern.jfr` can be opened in JMC to inspect Code/Hot Methods/Call Tree. The code uses a `volatile` `blackhole` variable so results from the compute chunks remain observable, reducing the chance that JIT eliminates the computation as dead code. It is a **synthetic workload for learning the profiler**, not code to put into a real application.

A test run on OpenJDK 24 with **`profile 2`** produced a valid file and `jfr summary` recorded **188 `jdk.ExecutionSample`** events; sample counts vary with JDK, hardware, duration, CPU load, and configuration. **Do not treat 188 as a fixed number** or expect identical sample counts. If the file has no `jdk.ExecutionSample` events, check the template, duration, and tooling before drawing conclusions about the code.

When opening the recording, select the region with the CPU loop and find `profileHotLoop` in the sampled stacks. If in a real problem the profiler shows `Thread.sleep` or similar taking wall time, do not use a CPU flame graph to infer blocked time.

### 7.3. Why Not Print "Faster by X ms" as Expected Output?

`System.nanoTime()` or CPU time from MXBeans depends on hardware, JIT warm-up, OS scheduling, CPU thermals, GC, and input data. A single fast/slow run is not a meaningful benchmark. To measure real gains:

1. Prepare representative inputs across multiple sizes and distributions (few vs. many duplicate keys).
2. **Warm up** the JVM/JIT; run multiple measurement iterations after warm-up.
3. Keep results consumed/checked to prevent dead-code elimination.
4. Track correctness, operation counts, throughput, CPU time, wall time, allocations, and p95/p99 separately when needed.
5. Use **JMH** for Java microbenchmarks; evaluate end-to-end under realistic load to confirm the improvement holds.

## 8. Reading "Hot CPU" Without Being Misled by JIT, GC, or Profilers

### 8.1. JIT Warm-Up and Code Shape

HotSpot/JIT can optimize code after a number of executions: **inlining**, loop optimizations, escape analysis, constant folding, or deoptimization when assumptions no longer hold. Therefore:

- Startup/warm-up phases can show CPU spent on **JIT compilation** and class loading; do not attribute all of that CPU to business loops.
- Methods appearing in stack profiles may be **inlined**; reconstructed names/stacks depend on the profiler and JDK. Never assume a method missing from samples was never called.
- Two simple benchmarks run back-to-back can be biased by execution order, progressive JIT warm-up, and caches; do not declare one algorithm faster from a single run.
- Hot code is not automatically worth changing: measure **cost relative to SLO targets** and ability to preserve semantics.

Use JFR JVM compilation events if needed along a timeline, without turning on verbose JIT logging in production just to inspect one method.

### 8.2. Allocations and the Garbage Collector Also Consume CPU

A loop creating many short-lived objects can drive allocation rate/GC high. Approach:

1. Inspect GC pause/time, collection counts, and allocation rate in JFR/JMC.
2. Find **allocation call sites**; check whether parsing, boxing, or new buffers happen on every iteration.
3. Distinguish GC CPU from business-thread CPU and JIT/native CPU.
4. Change code structure to reduce **necessary work**, rather than rushing to tweak heap/GC flags when the root is wasteful allocation.

If a request takes 200 ms waiting on the network, trimming a small amount of allocation may not fix p99 latency. Conversely, when GC CPU is high from creating millions of temporary objects in a loop, fixing the code can matter more than adding hardware resources.

### 8.3. Native Code, Synchronization, and Virtual Threads

- JFR `jdk.ExecutionSample` primarily shows where Java threads were sampled while running; native hotspots may require `jdk.NativeMethodSample` or a dedicated OS/native profiler, depending on platform/recording.
- A `RUNNABLE` Java thread inside native I/O is not enough to conclude CPU is burning inside Java.
- With **virtual threads**, the OS observes carrier/platform threads. Do not map virtual thread IDs 1:1 to Linux TIDs; use JFR, virtual-thread-aware thread dumps, and measurements in the right place.
- Lock contention increases wall time while many threads do **not** burn CPU; custom spin locks written by an application, however, can burn real CPU. Distinguish these two cases before choosing a fix.

## 9. Real-World Scenario Analysis

| Symptom | Primary Hypothesis | How to Prove | Remediation Direction |
|---|---|---|---|
| One core near 100%, empty queue, same `while` stack repeating in dumps | Busy spin with no progress | Thread CPU, JFR samples, loop count, queue depth | Replace with conditional blocking/signal/timeout |
| CPU surges sharply when list grows from 1,000 to 10,000 items | `O(n²)` or worse algorithm | Count comparisons, profile inner loop, scaling vs. `n` | Use map/index, batch processing, avoid duplicate scans |
| CPU rises after release while request rate is flat | Retry amplification, duplicate scheduler, cache misses, hot loop | Request/job/retry counters, thread profiles, code diff | Bound retries, idempotency, dedupe, fix cache |
| `loadRules` appears heavily in samples | Loop-invariant work called repeatedly | Abnormally high `configLoads / requests` or `/ batch` | Hoist/cache after verifying freshness and side effects |
| High JVM CPU alongside frequent GC and rising allocation rate | Object creation in loop, churn | JFR Allocation/GC + CPU samples | Reduce excess allocation, tune memory/GC later |
| Low JVM CPU yet high latency | Waiting on I/O, locks, downstream | JFR Thread/Lock/I/O events, traces, timing | Fix dependency/contended resource; do not optimize CPU |
| High host CPU, low JVM CPU | Another process/container uses CPU | Host/process/cgroup metrics | Address the actual CPU owner |
| Profile shifts drastically between first and later runs | JIT warm-up, class loading, GC, caches | Warm-up, JFR compilation, repeated JMH runs | Measure after warm-up; avoid single-run conclusions |

### Case A — Core-Hogging Polling Loop

**Before:** a worker uses `while(queue.isEmpty()) { }`. During idle hours, CPU remains high; OS metrics identify the hot thread, and JFR plus consecutive thread dumps show the worker stuck in the same loop. **After:** the worker waits on `BlockingQueue.take()`, processes items as they arrive, and preserves shutdown/cancellation handling. Re-measure idle CPU and item-arrival latency; do not verify only that CPU dropped while ignoring responsiveness.

### Case B — Algorithm Scaling with Input Size

**Before:** a method compares every pair of products to find duplicates: for 6,000 items there are 17,997,000 comparisons. **After:** counting via a map in 6,000 expected visits returns the exact same 87,000 matching pairs for the example data. Verify `equals/hashCode` correctness, input distribution, and memory overhead; small-data results may not reflect large workloads.

### Case C — Caller Repeats Work, Not a Slow Callee

**Before:** 3,000 requests/items each call `loadRules()` even though the batch only needs one rule version. **After:** one load per batch sharing the result when the invariant holds. The counter drops from 3,000 to 1; CPU may drop if loading is truly expensive, but the key lesson is **diagnosing abnormal call frequency**. If rules differ per tenant or change immediately, blindly batch-caching is a severe bug.

### Case D — Retry Storm During an Incident

**Before:** a failing dependency triggers immediate retries that repeatedly encrypt/sign/parse payloads, driving CPU up while success rate is 0. **After:** retry budgets, exponential backoff with jitter, concurrency limits, and appropriate circuit breakers/idempotency. Track `attempts / original request`, CPU/request, queue depth, and error rate; lower CPU is **not enough** if you accidentally drop valid requests.

## 10. Reaching a Root-Cause Conclusion with Evidence

A technical report should separate **observation**, **hypothesis**, **experiment**, and **result**:

```text
Observation: JVM CPU rises from baseline as items/batch grows,
             while request rate stays nearly constant.

Evidence:    CPU samples cluster in OrderMatcher.comparePairs;
             logs/counters show n = 6000 and ~18 million comparisons.

Hypothesis:  The O(n²) pair-scanning algorithm is the excess CPU work.

Experiment:  Replace with Map-based counting preserving business output;
             run correctness tests + comparable workload after warm-up.

Conclusion:  Compare CPU/batch, throughput, p95/p99, allocation, GC before/after.
             Only call it an improvement when both metrics and correctness pass.
```

Do not blur the steps: a method at the top of Hot Methods is only a **location indicator**, not proof by itself of **why** it runs so much or whether changing it helps users.

### Execution Checklist

1. Identify the **process and time window** of high CPU; compare process CPU against host CPU, throughput, and request rate.
2. Capture **JFR `profile`** under load; inspect Hot Methods/Call Tree, distinguishing execution samples from blocked latency.
3. If needed, map hot Linux TIDs to **platform threads** in `jcmd Thread.print`, taking multiple consecutive snapshots.
4. At the hotspot, check **loop termination/progress**, iteration counts, `n`, call counts, retries, and cache hits/misses.
5. Distinguish an **expensive algorithm per call** from **repeated work across calls**, GC/JIT/OS contention.
6. Apply conditional fixes that **preserve exact results**; avoid caching/hoisting that serves stale data or drops side effects.
7. Verify with tests, matching workload conditions, post-warm-up JFR/OS measurements, and JMH benchmarks for micro-level checks.
8. Report CPU/request, total CPU, throughput, latency, and memory/GC; never rely on a single CPU percentage.

### Self-Check Questions

- Why does a 500 ms slow request not necessarily consume 500 ms of CPU?
- Why are three consecutive thread dumps pointing to the same loop usually more useful than a single `RUNNABLE` snapshot?
- For `n = 6000`, why do two nested loops comparing all pairs perform 17,997,000 comparisons, while Map-based counting can visit only 6,000 items?
- Why does a method appearing heavily in JFR samples not necessarily have a flawed algorithm itself?
- Why does reducing `loadRules` calls from 3,000 → 1 not prove "3,000x faster CPU"?
- When JVM CPU is high, how do you distinguish CPU from application code, JIT compiler, GC, and native code?
- With virtual threads, why do `ThreadMXBean` and OS TIDs not directly represent per-virtual-thread CPU?

## References

- [Oracle Java SE 17 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): CPU load, execution samples, Method Profiling/Hot Methods, and stack interpretation.
- [Oracle JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html): creating/opening recordings, inspecting Code/Memory/Threads, and selecting events.
- [Java SE 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread CPU time, supportability, enabled state, and virtual-thread limitations.
- [Java SE 21 — `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `Thread.print`.
- [Java SE 21 — `jfr`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): reading, filtering, and summarizing events in `.jfr` files.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): Java microbenchmark harness reducing warm-up, JIT, and compiler-optimization pitfalls.
