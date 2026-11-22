# `ThreadLocalRandom` When Multiple Threads Generate Random Numbers Concurrently

## 1. The problem: multiple tasks, frequent number generation

A Java application may concurrently run multiple simulations, pick random wait times (jitter), distribute work into buckets, or generate test data. When each task repeatedly needs random values, how you organize the generator can affect throughput and thread contention.

Consider a thread pool with four threads, each simulating 10,000 die rolls. Questions to answer:

- How does each thread draw numbers from `1` to `6` without updating the state of a single shared `Random` object?
- How do you ensure correct range boundaries and avoid unsynchronized access to a shared counter array?
- Which results can be reliably tested when random values change on every run?
- When should `ThreadLocalRandom` not be used, such as when exact seed reproducibility or cryptographic values are required?

The `java.util.concurrent.ThreadLocalRandom` class was introduced in Java 7 and remains well suited for Java 17+. It is a **pseudorandom number generator bound to the executing thread**, useful when multiple threads need to generate numbers frequently.

## 2. How does `ThreadLocalRandom` work per thread?

Common usage:

```java
import java.util.concurrent.ThreadLocalRandom;

int number = ThreadLocalRandom.current().nextInt(1, 7);
// number is in {1, 2, 3, 4, 5, 6}.
```

`current()` returns the `ThreadLocalRandom` instance for the **calling thread**. Typically, each worker calls `current()` itself inside its running task. According to the API documentation, methods on this object **should only be called by the thread that obtained it**, never passed to another thread.

```java
Runnable task = () -> {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    int sample = rng.nextInt(100); // 0 <= sample < 100
    // Process sample directly inside the worker.
};
```

The code above illustrates writing a `Runnable`; to execute it, submit `task` to a `Thread` or `ExecutorService`. You can call `ThreadLocalRandom.current()` each time a number is needed, or hold the `rng` variable *locally within the worker scope* for repeated calls in the same task.

### Why is it often preferable to a shared `Random`?

A `java.util.Random` instance can be used by multiple threads, but concurrent calls update the state of the **same generator**, which can cause contention and increase overhead under heavy parallel load. `ThreadLocalRandom` avoids having threads update a single shared `Random` generator like this; this often reduces overhead and contention in continuous number-generation tasks.

This is a benefit in **state organization and potential performance**, not a promise that every program using `ThreadLocalRandom` will run faster. If tasks are mostly I/O-bound, wait on other locks, or generate very few numbers, the difference may be negligible. Measure under realistic workloads with proper benchmarks before deciding to optimize.

`ThreadLocalRandom` does not create threads on its own and does not replace `ExecutorService`: threads/tasks still must be organized by the application.

## 3. Essential APIs and range semantics

These methods return **pseudorandom** values, with no guarantee of distinct values across consecutive calls.

| Call | Range or result |
| --- | --- |
| `nextInt()` | `int` value across the entire integer range |
| `nextInt(10)` | Integer from `0` to `9` |
| `nextInt(1, 7)` | Integer from `1` to `6` |
| `nextLong(100L)` | `long` from `0` to `99` |
| `nextLong(10L, 20L)` | `long` from `10` to `19` |
| `nextDouble()` | `double` from `0.0` (inclusive) to `1.0` (exclusive) |
| `nextDouble(1.5, 2.5)` | `double` in `[1.5, 2.5)` |
| `nextBoolean()` | Pseudorandom `boolean` value |

For overloads taking `origin` and `bound`:

- The lower bound is **inclusive** (`origin`).
- The upper bound is **exclusive** (`bound`).
- For `nextInt(origin, bound)` and `nextLong(origin, bound)`, `origin < bound` must hold; violating this throws `IllegalArgumentException`.
- For `nextInt(bound)` or `nextLong(bound)`, `bound` must be positive.
- For `nextDouble(origin, bound)`, both bounds must be finite and `origin < bound`; do not pass `NaN` or infinity as bounds.

For example, to pick an index of a list with `size` elements:

```java
int size = items.size();
if (size == 0) {
    throw new IllegalArgumentException("List must not be empty");
}
int index = ThreadLocalRandom.current().nextInt(size);
// index is in [0, size): safe to use items.get(index).
```

This is an **embedded snippet** where `items` is an existing `List`. If the list can be modified concurrently, the application still must handle thread safety for the list; `ThreadLocalRandom` does not solve that.

### Avoid using modulo to bound random numbers

```java
// Should not be used to generate an index in [0, 9]:
int bad = ThreadLocalRandom.current().nextInt() % 10;

// Also avoid Math.abs(nextInt()) % 10:
// Math.abs(Integer.MIN_VALUE) is still negative.
int good = ThreadLocalRandom.current().nextInt(10);
```

The value of `bad` can be negative. Manual `%` can also introduce distribution bias when dividing a range whose size is not evenly divisible by the bucket count; use the overloads taking `bound`/`origin, bound` so the library handles the range properly.

`nextInt(1, 7)` is appropriate for simulating a six-sided die roll; do not write `nextInt(1, 6)` if you want `6` to appear.

## 4. Ownership rules in multithreaded applications

### 4.1. Obtain `current()` inside the worker

**Do:**

```java
executor.submit(() -> {
    ThreadLocalRandom rng = ThreadLocalRandom.current();
    for (int i = 0; i < 1_000; i++) {
        int value = rng.nextInt(100);
        // Process value using task-local data.
    }
});
```

This is an *embedded* example; `executor` is an `ExecutorService` created by the caller.

**Do not keep an instance and pass it across threads:**

```java
// Misuses the API when multiple threads call on this object:
static final ThreadLocalRandom SHARED = ThreadLocalRandom.current();
```

`SHARED` is obtained on the class-initialization thread; passing that reference to be called from other workers violates the per-thread ownership guideline. Also avoid capturing `ThreadLocalRandom.current()` on the main thread and passing the `rng` variable into every task via a lambda.

Do not add synchronization around a shared `ThreadLocalRandom` to “fix” incorrect usage. The proper approach is to **call `current()` inside the executing thread itself**.

### 4.2. Lifecycle is per worker thread, not per task

`ExecutorService` commonly reuses threads. If 100 tasks run on a pool of 4 workers, multiple tasks will run sequentially on the same worker, and each task calling `ThreadLocalRandom.current()` uses that thread's generator. Therefore:

- Do not assume each task has an independent seed or a fixed random sequence.
- Do not infer the number of generators from the number of tasks.
- Task execution schedules may vary between runs.
- You do not call `new ThreadLocalRandom()`; normal usage is via `current()`.

If the primary requirement is **each task having a reproducible pseudorandom sequence**, design the RNG and seed by **task identifier** (see section 8); thread-local is not equivalent to task-local.

### 4.3. An RNG does not make shared data thread-safe

Example where multiple workers update together:

```java
long[] counts = new long[6];
executor.submit(() -> {
    int face = ThreadLocalRandom.current().nextInt(1, 7);
    counts[face - 1]++; // Race condition if other workers also update counts.
});
```

The increment `counts[i]++` is not an atomic operation. Multiple threads can lose increments even though they draw numbers from independent generators. Three common solutions exist: each task writes to a **local counter and merges upon completion**; or use `AtomicLongArray` / `LongAdder` per slot if sharing is required; or apply appropriate synchronization. The complete example in the next section chooses local counting.

Do not confuse **thread-safe RNG usage** with **thread-safe business data**.

## 5. Complete Java 17+ program: simulating 40,000 die rolls

Create the file **`ThreadLocalRandomDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;

public class ThreadLocalRandomDemo {
    // Each worker owns its counts array, then transfers the result to the aggregation thread.
    record Result(long[] counts, long outOfRange) {}

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        int workers = 4;
        int drawsPerWorker = 10_000;
        ExecutorService executor = Executors.newFixedThreadPool(workers);

        try {
            List<Future<Result>> futures = new ArrayList<>();

            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    // Must obtain the RNG inside the thread executing the task.
                    ThreadLocalRandom rng = ThreadLocalRandom.current();
                    long[] counts = new long[6];
                    long outOfRange = 0;

                    for (int j = 0; j < drawsPerWorker; j++) {
                        int face = rng.nextInt(1, 7);
                        if (face >= 1 && face <= 6) {
                            counts[face - 1]++;
                        } else {
                            outOfRange++;
                        }
                    }
                    return new Result(counts, outOfRange);
                }));
            }

            // Main only aggregates after receiving each Future result.
            long[] totals = new long[6];
            long invalid = 0;
            for (Future<Result> future : futures) {
                Result result = future.get();
                invalid += result.outOfRange();
                for (int i = 0; i < totals.length; i++) {
                    totals[i] += result.counts()[i];
                }
            }

            long counted = Arrays.stream(totals).sum() + invalid;
            System.out.println("workers=" + workers);
            System.out.println("draws=" + counted);
            System.out.println("outOfRange=" + invalid);
            System.out.println("buckets=" + totals.length);
            System.out.println("countMatches="
                    + (counted == (long) workers * drawsPerWorker));

        } finally {
            executor.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac ThreadLocalRandomDemo.java
java ThreadLocalRandomDemo
```

**Exactly verifiable stdout** (assuming tasks complete normally and the API adheres to its contract):

```text
workers=4
draws=40000
outOfRange=0
buckets=6
countMatches=true
```

Specific counts for each die face will change across runs, so the example intentionally prints only **invariants**: total draw count, range validity, and bucket count.

Step-by-step mechanism:

1. `newFixedThreadPool(4)` creates an executor with up to four workers to process tasks. Four `Callable<Result>` tasks are submitted to the executor.
2. Each callable invokes `ThreadLocalRandom.current()` **while running in the worker**, then generates 10,000 calls to `nextInt(1, 7)`.
3. Each task uses its own counter array, with no shared increments across workers.
4. `Future.get()` waits for a task to finish or report an error; collecting results in submission order **does not force tasks to execute in order**.
5. Main merges the completed data to compute totals, then closes the executor with `shutdown()` in `finally`.

In Java 17, `ExecutorService` should not yet be assumed to support `try-with-resources` in all target compilation environments. The pattern above uses explicit `try/finally`; in real applications, provide cancellation/await-termination policies suited to your system.

If each run prints the occurrence counts of faces 1..6, the numbers will not be completely identical, and that **is not a bug**. Even a good RNG does not guarantee equal bucket counts in a finite sample.

## 6. Performance: practical benefits and limits

In programs where multiple threads generate numbers at high frequency, using `ThreadLocalRandom` typically reduces contention compared to sharing a single `Random`. However, an accurate measurement also depends on:

- **Workload composition:** generating a few numbers per request is usually cheaper than network, DB, logging, and other synchronization operations.
- **How results are recorded:** if every thread still writes to a shared variable/structure behind a lock, contention may simply move rather than disappear.
- **Thread count and pool size:** adding threads beyond CPU capacity can increase context switching; an appropriate pool size depends on the workload rather than assuming bigger is always faster.
- **JVM/JIT warmup, GC, scheduling variation:** a single benchmark using `System.nanoTime()` rarely proves a meaningful difference.
- **Output requirements:** if seed-based determinism or security is required, prioritize correctness criteria over reducing overhead.

When benchmarking generators, use JMH or a rigorous measurement methodology: run warmup iterations, measure multiple samples, use an appropriate thread count, ensure results are not optimized away by the compiler, and inspect both throughput and latency. Do not claim a fixed speedup factor across all JDKs/hardware.

### What happens with `parallelStream()`?

Obtain the RNG on the thread *actually* processing the element:

```java
long count = java.util.stream.IntStream.range(0, 10_000)
        .parallel()
        .filter(i -> ThreadLocalRandom.current().nextInt(10) == 0)
        .count();
```

This snippet produces a varying hit count; only the bound `0 <= count <= 10_000` is invariant. Across different pools and workload partitioning, results also change. Do not grab a `ThreadLocalRandom.current()` in main and make every branch of a parallel stream reuse that reference.

Do not assume a parallel stream always spawns a separate thread per element. Parallelization, batch sizes, and the thread pool are decided by the runtime.

## 7. Common exceptions and mistakes

| Issue | Cause | Solution |
| --- | --- | --- |
| `nextInt(0)` or `nextInt(-1)` | Non-positive `bound` | Validate the bound and handle empty input sets |
| `nextInt(10, 10)` | `origin >= bound` | Use an upper bound strictly greater than the lower bound |
| Simulating a die with `nextInt(1, 6)` | Upper bound is *exclusive* | Use `nextInt(1, 7)` |
| Using `Math.abs(nextInt()) % bound` | `MIN_VALUE` stays negative; `%` can introduce bias | Use `nextInt(bound)` |
| Storing RNG in a `static final` field for all workers | Obtained on one thread and called on others | Call `current()` inside each worker |
| Calling `setSeed(...)` | `ThreadLocalRandom.setSeed(long)` always throws `UnsupportedOperationException` | Use an explicitly seeded RNG if reproducibility is needed |
| Trusting `ThreadLocalRandom` for security | It is a non-cryptographic PRNG | Use `SecureRandom` for tokens, keys, verification codes |
| Using per-thread RNGs while writing `counts[i]++` to a shared array | Race condition on shared data | Use local counters or synchronized structures |
| Tests expecting fixed sequences / equal buckets | Results depend on seed, thread, and randomness | Test value ranges, counts, invariants, or use a seeded RNG |
| Expecting a task to have a fixed thread/seed in a thread pool | Executors reuse workers and may alter scheduling | Map RNG/seed per task if reproducibility is required |

Another mistake is using random numbers to generate **mandatory unique IDs**. A PRNG can produce the same number multiple times. When unique IDs are required, use an appropriate uniqueness strategy (such as ID allocation, UUIDs with collision probability understood, or datastore unique constraints); `ThreadLocalRandom` does not guarantee uniqueness.

## 8. When reproducibility or security is required

### 8.1. Deterministic tests with seeds

`ThreadLocalRandom` is initialized with a runtime-managed seed; the `setSeed(long)` API is unsupported. Therefore, it is unsuitable when the same test must consistently reproduce the exact same number sequence across runs.

In Java 17, you can use `SplittableRandom` to create separate generators per task from a root seed. Each instance **must not be shared across threads**; split them before submitting tasks:

```java
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(2026L);
SplittableRandom firstTaskRng = root.split();
SplittableRandom secondTaskRng = root.split();

// Assign firstTaskRng and secondTaskRng to two separate tasks;
// each instance must only be used inside one task.
```

This is illustrative code showing how to split generators, not a full runnable program. When each task receives its own generator and performs the same call order with the same algorithm/seed, task results can be reproduced much more conveniently, independent of which worker thread runs the task. You must control RNG allocation order, draw counts, and version/algorithm if the contract requires cross-environment reproducibility. Do not share a `SplittableRandom` across two workers without proper synchronization design.

`java.util.random.RandomGenerator` (Java 17) also defines an abstraction over many RNG algorithms; choose an implementation based on performance, distribution, and reproducibility requirements rather than assuming all generators behave identically.

For unit tests with fixed outputs, another option is to inject a `RandomGenerator` or a number-generation interface into the component under test, then supply a fake/deterministic generator in the test.

### 8.2. Security-sensitive values

`ThreadLocalRandom` is **not cryptographically secure**. Do not use it to generate temporary passwords, OTP codes, session tokens, API secrets, nonces that must be unpredictable, or security keys. For those cases, use `java.security.SecureRandom` and design appropriate security workflows. Multiple threads needing to generate tokens does not turn `ThreadLocalRandom` into a secure choice; sharing/creating `SecureRandom` instances must be evaluated separately based on throughput and provider requirements.

## 9. Designing tests for multithreaded correctness

**Deterministic assertions:**

- With `rng.nextInt(1, 7)`, check that each result lies between 1 and 6.
- With `workers × drawsPerWorker`, the total counted samples must equal the requested count (assuming no task errors).
- The number of out-of-range samples must be 0.
- Results from workers are only combined after completion, or via proper synchronization.
- If a task throws an exception, `Future.get()` surfaces the failure rather than reporting success.

**Do not test:**

- “Face 6 must definitely appear within 100 rolls.”
- “Total even faces equal total odd faces.”
- “Two runs must produce the exact same sequence.”
- “Each thread always generates different values from every other thread.”

These assertions are not guaranteed by the API. If distribution statistics need testing, use an appropriate sample size and statistical analysis method with a quantified failure probability. Statistical checks do not replace boundary and race-condition checks.

Concurrency testing tools can evaluate shared-state updates, while checking that `nextInt` stays in range only verifies the RNG; it does not prove the rest of the workflow is thread-safe.

## 10. Practice exercises

1. Ten tasks use a four-worker thread pool. Should you store one `ThreadLocalRandom` in main and pass it to all tasks? Why is calling `ThreadLocalRandom.current()` inside each task correct?
2. Write a function to randomly pick an index of a `List<String>`, rejecting empty lists. Specify the exact lower and upper bounds.
3. Replace the dice program with a simulation of 100,000 coin flips across multiple workers; keep local counters and print only `total == 100000`, `invalid == 0`.
4. If a product manager asks for a simulation test that reproduces exact results for the same seed, is `ThreadLocalRandom` suitable? Propose a design using per-task RNGs with explicit seeds.
5. A system generating login verification codes uses `nextInt(100000, 1000000)`. Why is having the right range still **not enough** to make this approach secure?

**Suggested answers:** (1) Do not pass an instance obtained from another thread; call `current()` inside the worker. (2) `nextInt(list.size())` gives `[0, size)` after checking `size > 0`. (3) Each task returns its own counter, and main aggregates via `Future.get()`. (4) Use `SplittableRandom`/a seeded per-task generator and fix the usage order. (5) `ThreadLocalRandom` lacks cryptographic unpredictability, even though the output is a six-digit number.

## 11. Technical decision summary

Use `ThreadLocalRandom.current().nextX(...)` **directly inside the executing thread** when multiple workers must generate pseudorandom numbers frequently and do not need seed-reproducible sequences. Use exclusive upper bounds properly and keep accumulated data local or properly synchronized. If sequences must be reproducible per task, choose a seeded generator with an explicit lifecycle; if outputs must resist prediction, switch to `SecureRandom`.

Reference documentation (Java SE 17): [ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html), [SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html), [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).
