# ThreadLocalRandom.current(): Avoiding Contention, Reproducibility, and Security Limits

## 1. The Problem in Concurrent Programs

Many parallel Java tasks need pseudorandom numbers for bucket allocation, generating simulation data, sampling, or choosing retry jitter durations. A familiar approach is to create a shared `java.util.Random` and have threads call `nextInt()` on it. That approach is **thread-safe in terms of correctness**, but the calls must update the same number-generation state. In code running with a large number of threads and calling the PRNG very frequently, this coordination can become a point of contention.

`java.util.concurrent.ThreadLocalRandom` serves situations where multiple threads need to generate general-purpose pseudorandom numbers:

~~~java
int bucket = java.util.concurrent.ThreadLocalRandom.current().nextInt(10);
~~~

The core of this lesson covers three **distinct** requirements:

- **Reducing contention:** avoiding shared number-generation state across multiple threads when work calls the PRNG frequently.
- **Reproducibility:** if you want to repeat a simulation or test case identically, you need a seed and a stable generator assignment per task.
- **Security:** if values must be unpredictable to an attacker, you need a CSPRNG; `ThreadLocalRandom` makes no cryptographic security guarantees.

This lesson focuses on **JDK Java concurrency**, without using any frameworks.

## 2. Shared Random vs. Thread-Local State

### Why Can a Shared `Random` Create Contention?

Illustrative snippet (not a standalone runnable program):

~~~java
import java.util.Random;

final class SharedRandomSource {
    static final Random RANDOM = new Random();

    static int bucket() {
        return RANDOM.nextInt(100);
    }
}
~~~

`Random` allows multiple threads to use the same object without corrupting its state. In familiar JDK implementations, updating the internal seed of a shared `Random` uses atomic/CAS operations; multiple threads updating concurrently may have to retry due to contention. **Thread-safe does not mean contention-free.** However, if number generation is very infrequent or most time is spent on I/O, this may not be a significant bottleneck.

`ThreadLocalRandom.current()` uses PRNG state attached to the **current thread**, avoiding having threads collide on *one* shared number-generation state. Mental model:

~~~text
One shared Random                     ThreadLocalRandom
Producer A ──┐                        Worker A ──> RNG state A
Producer B ──┼──> RNG state X         Worker B ──> RNG state B
Producer C ──┘                        Worker C ──> RNG state C
       may experience contention      no contention on that shared seed
~~~

This does not mean every call fetches fresh entropy from the operating system. It is still **pseudorandom**: outputs are computed from internal state. Two threads can still generate the same number; generating numbers does not automatically guarantee ID uniqueness, does not synchronize application data, and does not prevent race conditions elsewhere.

### Calling `current()` in the Right Place

Write `ThreadLocalRandom.current().nextInt(...)` on the **thread that needs the number**. In a task running on a thread pool, call `current()` inside that unit of work. If calling it multiple times on the same thread, holding a local reference `ThreadLocalRandom random = ThreadLocalRandom.current();` is also fine.

In an executor, a worker thread may process multiple tasks consecutively. PRNG state is tied to the **thread**, not the task/request. Which task runs on which worker depends on the scheduler. Therefore, running the same set of tasks twice does not guarantee receiving the same sequence of numbers.

Do not instantiate it with `new ThreadLocalRandom()`, and do not treat a `ThreadLocalRandom` object as an independent generator with its own seed to pass from one thread to another. The typical and clearest usage is `current()` on the executing thread.

## 3. API and Range Rules

| API | Return Value and Conditions |
| --- | --- |
| `ThreadLocalRandom.current().nextInt()` | An `int` across the entire signed integer range, including negative values. |
| `nextInt(bound)` | An integer from `0` to `bound - 1`; `bound > 0`. |
| `nextInt(origin, bound)` | An integer in `[origin, bound)`; requires `origin < bound`. |
| `nextLong(origin, bound)` | A `long` in the half-open interval `[origin, bound)`. |
| `nextDouble(origin, bound)` | A `double` from origin (inclusive) to bound (exclusive), within valid bounds. |
| `nextBoolean()` | A pseudorandom boolean value. |

For example, choosing a die face from **1 to 6**, inclusive on both ends: `nextInt(1, 7)`. Choosing jitter from **50 to 150 ms**: `nextLong(50, 151)`. Invalid arguments such as `nextInt(0)` or `nextInt(7, 7)` throw `IllegalArgumentException`.

Do not manually compute `Math.abs(nextInt()) % n` instead of the bounded API. `Math.abs(Integer.MIN_VALUE)` remains negative due to `int` overflow; modulo division can also produce a biased distribution if the input range does not divide evenly by `n`. Use `nextInt(n)` or `nextInt(origin, bound)` directly.

Stream-producing APIs such as `ints(...)` and `longs(...)` are useful, but do not assume that the order of generated numbers in a **parallel stream** will be stable across all execution schedules. For reproducibility, you must manage the generator and call sequence at the task level.

## 4. Java 17 Example: Multiple Workers, No Shared Random Contention

The program below creates 4 callables, each calling `ThreadLocalRandom.current()` on the worker thread running it, generating 1,000 values in `[10, 20)` and checking the bounds. We do **not** print the random values because those values change between runs; we only check an invariant with a deterministic result.

Save **ThreadLocalRandomDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

public class ThreadLocalRandomDemo {
    public static void main(String[] args) throws Exception {
        int workerCount = 4;
        int drawsPerWorker = 1_000;
        ExecutorService pool = Executors.newFixedThreadPool(workerCount);

        try {
            List<Callable<Integer>> jobs = new ArrayList<>();

            for (int i = 0; i < workerCount; i++) {
                jobs.add(() -> {
                    ThreadLocalRandom rng = ThreadLocalRandom.current();
                    int outOfRange = 0;

                    for (int n = 0; n < drawsPerWorker; n++) {
                        int value = rng.nextInt(10, 20);
                        if (value < 10 || value >= 20) {
                            outOfRange++;
                        }
                    }
                    return outOfRange;
                });
            }

            List<Future<Integer>> futures = pool.invokeAll(jobs);
            int outOfRange = 0;

            for (Future<Integer> future : futures) {
                outOfRange += future.get();
            }

            System.out.printf(
                    "tasks=%d, draws=%d, outOfRange=%d%n",
                    workerCount,
                    workerCount * drawsPerWorker,
                    outOfRange);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile/run on JDK 17 or later:

~~~bash
javac ThreadLocalRandomDemo.java
java ThreadLocalRandomDemo
~~~

Expected stdout:

~~~text
tasks=4, draws=4000, outOfRange=0
~~~

All 4,000 values are generated by `nextInt(10, 20)`, so there are no out-of-range values. Each callable only mutates its own local variables, creating no shared mutable counter. `Future.get()` waits for the task to complete and surfaces any callable errors; finishing `submit` or `invokeAll` does not mean all business processing is automatically safe.

This test demonstrates **proper API and bound usage**, not a statistical proof that the distribution is perfect or that results are unpredictable. When you want to prove performance improvements, you need a dedicated benchmark with realistic load.

## 5. Why `ThreadLocalRandom` Cannot Be Used to Reproduce Sequences

`ThreadLocalRandom` inherits several methods from `Random`, but **`setSeed(long)` is not supported**. Calling `ThreadLocalRandom.current().setSeed(42L)` throws `UnsupportedOperationException`. There is no supported standard way to tell all workers to start from a user-specified seed.

Even if a single generator produces a predictable sequence for a given seed, if multiple tasks draw numbers from it, which task receives the 1st, 2nd, or 3rd value can still change depending on execution scheduling. In a thread pool, `ThreadLocalRandom` state belongs to the worker thread and advances across prior tasks as well; merely fixing the number of tasks or workers is still not enough to determine the **task → number sequence mapping**.

For meaningful reproducibility, you must fix:

1. The initial seed and PRNG algorithm.
2. The input data and the sequence of number-generation operations for **each task**.
3. A stable rule mapping task IDs to generators or seeds.
4. The order of combining results if the computation is order-dependent, such as summing floating-point numbers in parallel.

`java.util.SplittableRandom` has a constructor that takes a seed and is suitable for general-purpose pseudorandom simulations and tests. It is **not thread-safe**. Therefore, it is best to provide **a separate instance per task** and not share an instance when tasks draw numbers concurrently.

## 6. Java 17 Example: Reproducible Regardless of Worker Order

Each task has an ID from 0 to 7. The `simulate(taskId)` method creates a new `SplittableRandom` with seed `20261028L + taskId`, generates 1,000 dice rolls, and sums them. `main` runs the same tasks in two ways: sequentially and in parallel. If the ID/seed mapping and call sequence are fixed, each task's sum is identical even when the executor schedules them differently.

Save **ReproducibleTasks.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ReproducibleTasks {
    private static int simulate(int taskId) {
        SplittableRandom rng = new SplittableRandom(20261028L + taskId);
        int total = 0;

        for (int n = 0; n < 1_000; n++) {
            total += rng.nextInt(1, 7);
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        int taskCount = 8;
        int[] sequential = new int[taskCount];

        for (int id = 0; id < taskCount; id++) {
            sequential[id] = simulate(id);
        }

        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Callable<Integer>> jobs = new ArrayList<>();
            for (int id = 0; id < taskCount; id++) {
                final int taskId = id;
                jobs.add(() -> simulate(taskId));
            }

            List<Future<Integer>> futures = pool.invokeAll(jobs);
            boolean reproducible = true;

            for (int id = 0; id < taskCount; id++) {
                if (futures.get(id).get() != sequential[id]) {
                    reproducible = false;
                }
            }

            System.out.printf(
                    "tasks=%d, reproducible=%b%n",
                    taskCount, reproducible);
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

~~~bash
javac ReproducibleTasks.java
java ReproducibleTasks
~~~

Stdout:

~~~text
tasks=8, reproducible=true
~~~

`simulate(3)` creates a new RNG with the same seed, then calls `nextInt(1, 7)` exactly 1,000 times in a single fixed order. It does not share an instance with `simulate(7)`. `invokeAll` returns a list of `Future` objects in the same order as the task list, so results can be compared by ID regardless of which worker finishes first.

**Do not over-interpret reproducibility:**

- The `baseSeed + taskId` formula here is simple for illustration. Large applications need seed/ID generation conventions that avoid unintended reuse and may use an appropriate seed-mixing function.
- `SplittableRandom.split()` creates a new generator for a computation branch. For reproducibility, the split order and split tree must be deterministic; do not let multiple threads call `split()` concurrently on the same instance.
- If tasks use shared mutable state, accumulate floating-point numbers in different orders, or read wall-clock/real time, a fixed seed does **not** guarantee fixed business results.
- For reproducibility across environments or over long periods, record the seed, generator algorithm/version, JDK, task ID, and inputs. Do not assume all algorithms across libraries or JVM versions will always produce the exact same byte sequence forever.
- A seeded generator used for testing must **not** be used to generate secrets just because tests want to assert fixed values.

Java 17 includes the `java.util.random.RandomGenerator` interface family. This is a unified interface for many generators; the interface name does not prove that every implementation meets cryptographic requirements.

## 7. Security Limits: Pseudorandom vs. Cryptographically Secure

`ThreadLocalRandom` is designed for **general-purpose pseudorandom numbers with good multithreaded performance**. It is **not a CSPRNG** and does not provide sufficient unpredictability guarantees if an attacker observes part of the output or infers state.

Never use `ThreadLocalRandom` to generate:
- Login tokens, password reset tokens, session IDs, API keys, or values representing access privileges.
- Secret keys, random passwords, recovery codes, or cryptographic material.
- IVs/nonces that must meet an algorithm's security standards, or secret names/paths that the system relies on unpredictability to protect.

Using more digits does not fix predictability weaknesses. A 64-character string generated by an insecure PRNG does **not automatically** have 64 characters of cryptographically secure entropy.

In Java, `java.security.SecureRandom` is the appropriate source of random numbers for cryptographic use cases, via the JDK's configured provider. It has stronger security properties, but its initialization cost, entropy gathering, and throughput depend on the environment/provider, and it should not be assumed to always be as fast as `ThreadLocalRandom`.

### Java 17 Example: 32-Byte Token from `SecureRandom`

Save **SecureTokenDemo.java**:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secure = new SecureRandom();
        byte[] token = new byte[32];
        secure.nextBytes(token);

        String tokenHex = HexFormat.of().formatHex(token);

        // Only print the length, do not print the secret value.
        System.out.printf(
                "bytes=%d, hexChars=%d%n",
                token.length, tokenHex.length());
    }
}
~~~

~~~bash
javac SecureTokenDemo.java
java SecureTokenDemo
~~~

Stdout:

~~~text
bytes=32, hexChars=64
~~~

The 32-byte content changes across runs; only the length is deterministic. `HexFormat` converts each byte into two hex characters, so 32 bytes correspond to 64 characters. Hex/Base64 encoding only changes the **representation**, without adding entropy. When building applications, secrets must be protected during storage, transmission, and verification; never print them to logs.

Notes:
- `new SecureRandom()` is usually sufficient for application needs; `SecureRandom.getInstanceStrong()` is not mandatory in all cases and may block waiting for entropy depending on the provider.
- Do not hardcode a public seed for production tokens. `SecureRandom.setSeed(...)` has provider-dependent semantics and is not a contract for reproducing a test sequence.
- `SecureRandom` supports concurrent use, though providers may have internal synchronization and varying costs; if speed matters, benchmark the exact provider and target environment.
- When designing URL-safe tokens, you can use a Base64 URL encoder with `byte[]` from `SecureRandom`; all security properties still come from the CSPRNG, not the encoder.

**Rule:** Data that needs to "look random" for load distribution is different from data that needs to be "unpredictable" to protect accounts. Choose the source based on business requirements, not speed alone.

## 8. Choosing the Right API

| Java Tool | Suitable Use Case | Controllable Seed? | Cryptographically Secure? | Multithreading Notes |
| --- | --- | --- | --- | --- |
| `Random` | General-purpose pseudorandom numbers; simple simulations | Yes (`new Random(seed)`) | No | Thread-safe when shared, but may suffer contention. |
| `ThreadLocalRandom.current()` | Many workers need numbers frequently without requiring a fixed sequence | No via `setSeed` | No | Generation state is tied to the thread. |
| `SplittableRandom` | Simulations, branching, reproducible tests by seed/task ID | Yes | No | Not thread-safe; one instance per task/worker. |
| `SecureRandom` | Secrets, tokens, cryptographic material under security rules | Fixed seed should not be treated as a test contract | Yes, per provider/algorithm | Usable concurrently; cost depends on provider. |

A **separate** `Random` instance per worker can also eliminate contention from a shared `Random`, so you cannot claim "`ThreadLocalRandom` is faster than every way of using `Random`". `SplittableRandom` is often useful when creating independent branches with explicit seeds or splits; it does not replace a CSPRNG.

If the goal is **non-colliding IDs**, do not infer uniqueness from a PRNG. You must design an ID allocation scheme, check for duplicates, or choose an ID type with a collision probability appropriate for your system; unpredictability and uniqueness are two different properties.

## 9. Measuring Performance Properly

Situations that typically favor `ThreadLocalRandom`: many threads continuously drawing numbers while the work per draw is very short. A shared `Random` forces threads to update the same state. However, do not automatically conclude that `ThreadLocalRandom` is "N times faster": that varies by JDK, CPU, concurrency level, warmup, bound type, and workload.

Experiments should compare at least:
1. **One** shared `Random` across all workers.
2. `ThreadLocalRandom.current()` in each worker.
3. **One** separate `Random` per worker.
4. **One** separate `SplittableRandom` per worker/task, if the problem allows.

Use **JMH** for JVM benchmarking with warmup, multiple forks, throughput or latency measurement modes, and varying thread counts. Be sure to **consume the output** so the JIT does not optimize away the computation. Measure CPU/GC and end-to-end task time as well, because microbenchmark gains can disappear when most time is spent on I/O or business logic.

Do not benchmark with a single `System.nanoTime()` loop and treat the result as truth. JIT compilation, dead-code elimination, caches, GC, and scheduling introduce noise. Do not reduce every goal to throughput: if the application requires replayable results or security, the fastest PRNG is not necessarily the right choice.

### ThreadLocalRandom Does Not Solve Other Bottlenecks

It does not fix lock contention on business data, does not speed up databases, does not prevent deadlocks, does not guarantee fairness, and does not provide synchronization for any shared map/list. Measure where contention actually occurs and optimize that component.

## 10. Practical Scenario: Retry Jitter

When a service just recovers, hundreds of workers retrying at the exact same timestamp can continue to overload it. Non-cryptographic jitter helps spread out retry attempts:

~~~java
long jitterMillis = java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(50, 151); // 50 to 150 ms, inclusive of 150
~~~

This is an **illustrative snippet**, not a complete program. Real-world retries need attempt limits, an overall deadline, backoff, cancellation/interruption handling, and special care for non-idempotent operations. If using `Thread.sleep(jitterMillis)`, the executing thread is occupied while waiting; consider a scheduler if there are many delayed tasks. Jitter only reduces synchronized bursts; it does not guarantee success or eliminate overload.

To make retry timing testable, **inject a replaceable random source** or pass fixed test jitter values. Do not call `setSeed` on `ThreadLocalRandom`.

## 11. Testing and Common Pitfalls

**Testing bounds:** for `nextInt(5, 12)`, assert that every value lies in `[5, 12)`; do not assert a specific sequence. **Testing reproducibility:** use the same seed, algorithm, task ID, and call sequence. **Testing concurrency:** test different thread counts, use `CountDownLatch` to coordinate when needed, and use `Future.get(timeout, unit)` so tests do not hang forever; do not rely on `Thread.sleep` to assume a schedule has reached a race state. **Testing CSPRNGs:** check format/length and security policy; do not assert fixed token values.

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `ThreadLocalRandom.current().setSeed(42L)` | Throws `UnsupportedOperationException`. | Use `Random(seed)` or `SplittableRandom(seed)` for reproducibility. |
| Assuming a thread pool has a fixed execution schedule | Each task may receive a different sequence. | Assign a separate seed/generator per stable task ID. |
| Sharing `SplittableRandom` across threads | Not thread-safe. | One instance per task or split before running. |
| Using `ThreadLocalRandom` to generate login tokens | No cryptographic unpredictability guarantees. | `SecureRandom`. |
| Using `Math.abs(nextInt()) % n` | Value overflow and potential distribution bias. | `nextInt(n)`. |
| Treating random numbers as unique | Collisions can occur. | Design proper IDs and duplicate checks. |
| Measuring once in a very short loop | JVM warmup/scheduler/JIT skews results. | Use JMH and multi-threaded benchmarks. |
| Asserting worker log order | The scheduler does not guarantee order. | Compare results by task ID or invariants. |
| Swapping generators while ignoring contention elsewhere | No application improvement. | Profile end-to-end before and after. |

### Self-Check Questions

**1.** 32 threads randomly pick a bucket for load distribution, with no reproducibility needed and no secret involved. What should you choose?

**Answer:** `ThreadLocalRandom.current().nextInt(bucketCount)` with `bucketCount > 0`; measure if the code path is very hot.

**2.** A test has 16 tasks and needs identical results whether run on a 2-worker or 8-worker pool. What should you choose?

**Answer:** Give each task a stable ID/seed and its own `SplittableRandom`, keeping the same call sequence; check results by ID.

**3.** Is generating a token with 32 calls to `ThreadLocalRandom.current().nextInt(256)` secure because it produces 32 bytes?

**Answer:** No. Length does not prove unpredictability. Use `SecureRandom.nextBytes(byte[32])` and protect the token.

**4.** Why is a shared `Random` thread-safe yet still potentially slow?

**Answer:** Correct state updates do not mean zero coordination cost; multiple threads contend on one state, whereas `ThreadLocalRandom` avoids that shared point.

## 12. Application Checklist

1. Determine whether **cryptographic security is required**: if yes, choose `SecureRandom` and appropriate cryptographic practices.
2. If only general-purpose pseudorandomness is needed, determine whether **reproducibility is required**: if yes, use a generator with a fixed seed and a clear task ID mapping.
3. If multiple threads need fast number generation without reproducible sequences: use `ThreadLocalRandom.current()` on the executing thread.
4. Verify half-open bounds, do not manually use `abs % n`, and do not assume random outputs are always unique.
5. Measure performance under realistic workloads; never use speed as an excuse to drop reproducibility or security requirements.

`ThreadLocalRandom.current()` solves a specific problem: reducing contention when **multiple threads simultaneously need pseudorandom numbers**. It has no seed contract for exact reproducibility and no unpredictability guarantees for secret data. For reproducibility, assign generators/seeds per task; for cryptographic security, use `SecureRandom`.
