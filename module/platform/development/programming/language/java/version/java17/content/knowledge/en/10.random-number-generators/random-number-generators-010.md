# Generating Pseudo-Random Numbers in Java 17: Avoiding Unsafe Sharing of Generators Across Multiple Threads

Java programs frequently need random numbers for sampling, generating test data, simulations, distributing work, or generating tokens. When a program runs on multiple threads, how a random number generator (RNG) is used must align with the concurrency model.

An RNG object may be **unsafe when accessed concurrently by multiple threads**, or it may be thread-safe yet create **contention and performance degradation** when all threads share a single state. These are two distinct problems. Java provides several options such as `Random`, `ThreadLocalRandom`, `SplittableRandom`, and `SecureRandom`; each fits a specific purpose.

This lesson focuses on avoiding improper sharing of an RNG across multiple threads in Java 17, while choosing the right tool for general tasks, reproducible parallel computation, and security needs.

## 1. What Is an RNG and Why Does Its State Matter?

Most random number APIs in Java generate **pseudo-random numbers** (pseudorandom). An algorithm starts from an initial state (usually derived from a seed) and updates that state to produce a sequence of numbers with appropriate statistical characteristics.

Simple model:

```text
Seed / initial state
          |
          v
     RNG Algorithm
          |
          v
      Next number
          |
          v
     Update state
          |
          +------> next number ...
```

An RNG instance typically holds internal state. Calling `nextInt()`, `nextLong()`, or `nextDouble()` reads and updates that state.

If two threads share one instance:

```java
Random random = new Random();

Runnable job = () -> {
    int value = random.nextInt(100);
    System.out.println(value);
};

new Thread(job).start();
new Thread(job).start();
```

Two threads invoke methods on **the same object**. This raises two questions:

1. Are state updates protected so they do not corrupt the RNG state?
2. Even if safe, do multiple threads have to wait or contend over the same state?

Not every RNG has the same answer. Know the thread-safety contract of the class you are using rather than guessing from `next...()` method names.

## 2. Distinguishing Thread-Safety from Concurrent Performance

Two concepts are often conflated:

| Concept | Meaning | Consequence |
| --- | --- | --- |
| **Thread-safe** | Can be called concurrently by multiple threads under its contract without corrupting state or violating guaranteed correctness. | Sharing is valid for safety, though not necessarily fast. |
| **Contention** | Multiple threads compete to update or access a shared resource. | Can reduce throughput, increase latency, and negate parallel execution benefits. |
| **Not thread-safe** | The API does not guarantee proper behavior when multiple threads operate on one instance concurrently. | Requires per-thread/per-task instances or appropriate synchronization. |
| **Cryptographically secure** | Designed to produce output suited for security purposes, resisting prediction under the corresponding threat model. | Used when tokens/nonces/secrets are needed; typically more expensive than standard RNGs. |

Important example: `java.util.Random` is **thread-safe**. It does not immediately break when shared across threads. However, multiple threads sharing one `Random` can contend on its internal state, which is why Java provides `ThreadLocalRandom` for general multithreaded scenarios.

Conversely, `SplittableRandom` is designed for use by one thread at a time; do not share the same instance across multiple threads. Create independent instances with `split()` to distribute to separate tasks.

## 3. Random: Safe to Share, Subject to Contention

`java.util.Random` is a long-standing API still supported in Java 17:

```java
import java.util.Random;

Random random = new Random();
int number = random.nextInt(100); // 0 to 99
double ratio = random.nextDouble(); // from 0.0 to less than 1.0
```

### 3.1. Is Random Thread-Safe?

Yes. `Random`'s contract permits multiple threads to use the same instance concurrently. State updates are protected atomically, so calls do not corrupt RNG state.

This **does not mean** sharing is always a good performance choice. If multiple threads repeatedly call the same instance, they compete to update state. Update attempts may have to retry when another thread updates first.

```java
Random shared = new Random();

Runnable task = () -> {
    long total = 0;
    for (int i = 0; i < 1_000_000; i++) {
        total += shared.nextInt(100);
    }
    System.out.println(total);
};

new Thread(task).start();
new Thread(task).start();
```

The snippet above executes safely with respect to `Random`'s thread safety, yet both threads share one state update point. As thread count and call frequency grow, contention can become a bottleneck.

### 3.2. Creating One Random per Thread

One way to reduce sharing is for each thread to own a dedicated instance:

```java
Runnable task = () -> {
    Random random = new Random();
    for (int i = 0; i < 5; i++) {
        System.out.println(Thread.currentThread().getName()
                + ": " + random.nextInt(100));
    }
};

new Thread(task, "worker-1").start();
new Thread(task, "worker-2").start();
```

Each time `task` runs, `random` is a local variable and the instance is used only by that thread. However, if many short tasks are created or a thread pool is used, constructing an RNG inside every task may be unnecessary; multiple tasks can run sequentially on the same worker thread.

`ThreadLocalRandom` is usually a simpler choice for general-purpose pseudo-random numbers across multiple threads.

## 4. ThreadLocalRandom: The Standard Choice for Multithreading

`java.util.concurrent.ThreadLocalRandom` provides a generator bound to the **current thread**. Call `ThreadLocalRandom.current()` to retrieve the instance for the running thread:

```java
import java.util.concurrent.ThreadLocalRandom;

int number = ThreadLocalRandom.current().nextInt(100);
double rate = ThreadLocalRandom.current().nextDouble();
```

Each thread uses its own RNG state, avoiding having all workers contend on a shared `Random` instance.

### 4.1. Generating Numbers in a Range

Bounded methods take an inclusive lower bound and an exclusive upper bound:

```java
ThreadLocalRandom random = ThreadLocalRandom.current();

int a = random.nextInt(1, 7);           // 1, 2, 3, 4, 5, or 6
long b = random.nextLong(100L, 200L);   // 100 to 199
double c = random.nextDouble(0.0, 1.0); // 0.0 <= c < 1.0
```

If the lower bound is greater than or equal to the upper bound, bounded overloads throw `IllegalArgumentException`. Define the target range clearly before calling.

### 4.2. Using with a Thread Pool

There is no need to pass a shared RNG object into each task:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;

public class ThreadLocalRandomDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            for (int taskId = 0; taskId < 8; taskId++) {
                int id = taskId;
                pool.submit(() -> {
                    int value = ThreadLocalRandom.current()
                            .nextInt(1, 101);
                    System.out.println("Task " + id + ": " + value
                            + " on " + Thread.currentThread().getName());
                });
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Each task calls `current()` **on the actual worker thread executing the task**. If a worker runs multiple different tasks over time, those tasks share that worker's thread-local state; it does not mean every task gets a fresh RNG.

### 4.3. ThreadLocalRandom Is Not a Security RNG

`ThreadLocalRandom` is optimized for generating pseudo-random numbers in concurrent environments. Do not use it to generate:

- passwords or password reset codes;
- session IDs, access tokens, or API keys;
- nonces/secrets used in security protocols;
- verification codes that an attacker could predict to take over an account.

For those purposes, use `SecureRandom` and design an appropriate security workflow.

### 4.4. Do Not Manually Seed ThreadLocalRandom

`ThreadLocalRandom` manages seeds/state per thread. The API does not support users setting seeds in the usual way; calling `setSeed()` on this instance is not designed for reproducing number sequences. If you need deterministic seeded pseudo-random sequences for simulations or testing, consider `Random` or `SplittableRandom` with controlled seeds.

## 5. SplittableRandom: Splitting Generators for Parallel Tasks

`java.util.SplittableRandom` is designed for pseudo-random number generation in parallel computations. Instances are not thread-safe; the primary pattern is **one thread uses one instance**, then splits child instances via `split()` for independent tasks.

```java
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(12345L);
SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

int a = taskA.nextInt(100);
int b = taskB.nextInt(100);
```

`split()` creates a new generator with its own state. Perform the split on a single thread owning `root`, then distribute `taskA` and `taskB` so each child instance is used by only one thread at a time.

### 5.1. Example Distributing Generators to Two Tasks

```java
import java.util.SplittableRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SplittableRandomDemo {
    public static void main(String[] args) throws Exception {
        SplittableRandom root = new SplittableRandom(2026L);

        // Split before handing instances to workers.
        SplittableRandom randomA = root.split();
        SplittableRandom randomB = root.split();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> resultA =
                    pool.submit(() -> randomA.nextInt(1, 101));
            Future<Integer> resultB =
                    pool.submit(() -> randomB.nextInt(1, 101));

            System.out.println("A = " + resultA.get());
            System.out.println("B = " + resultB.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Each child generator is handed to a separate task. Do not pass `root`, `randomA`, or `randomB` to multiple concurrent tasks. If more computation branches are needed, keep splitting on the thread currently owning the parent generator before distributing.

### 5.2. When to Choose SplittableRandom?

- Monte Carlo simulations or large-scale numerical computations.
- Parallel tasks needing dedicated generators to avoid shared state.
- Needing seed control so experiments are reproducible by work-splitting structure.
- Each worker/task can own a dedicated RNG throughout execution.

`SplittableRandom` is not a choice for security tokens. Nor does it automatically guarantee every parallel program yields identical results across runs if task-splitting order, scheduling, or number consumption pattern changes. Reproducing results requires controlling the seed, split strategy, task structure, and consumption order.

## 6. SecureRandom: When Unpredictability Is a Security Requirement

`java.security.SecureRandom` produces pseudo-random numbers with properties suited for security applications. It is the choice for tokens, nonces, and secret values when used properly.

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] token = new byte[32];
        secureRandom.nextBytes(token);

        System.out.println(HexFormat.of().formatHex(token));
    }
}
```

`HexFormat` has existed since Java 17. A 32-byte array provides 256 bits of random data; practical token usage still requires considering entropy, expiration, storage, safe comparison, and the authentication protocol.

### 6.1. Can SecureRandom Be Shared Across Threads?

The `SecureRandom` API is specified as thread-safe. One instance can be used concurrently by multiple threads per the API contract. However, performance and synchronization behavior can depend on the provider/implementation; do not assume every provider has the same throughput characteristics.

In many applications, a centrally managed or shared instance is normal practice. If the system handles very high loads, benchmark with real workloads and review provider/configuration settings instead of arbitrarily creating many `SecureRandom` instances. Creating multiple instances does not automatically improve randomness quality.

### 6.2. Do Not Replace SecureRandom with Random for Speed in Security Contexts

`Random`, `ThreadLocalRandom`, and `SplittableRandom` serve general pseudo-random needs and are not designed to resist prediction under an attack model. An obscure seed or a clock-derived seed does not turn these classes into security RNGs.

If output data could allow an attacker to determine internal state or predict the next token, use a security API such as `SecureRandom`, and follow library and protocol guidelines.

## 7. Choosing the Right Generator by Purpose

| API | Instance Thread-Safety | Recommended Usage Pattern | Suitable Purpose |
| --- | --- | --- | --- |
| `Random` | Thread-safe | Can be shared; if many threads call frequently, consider contention. | Legacy compatibility, simple tasks, or deterministic seeded sequences. |
| `ThreadLocalRandom` | Generator bound to the current thread | Each worker obtains `ThreadLocalRandom.current()`. | General number generation in multithreaded applications. |
| `SplittableRandom` | Not thread-safe | Each thread/task owns a dedicated instance; use `split()` for branches. | Simulations and parallel computations needing split generators. |
| `SecureRandom` | Thread-safe per API | Can be shared; evaluate provider and performance under real load. | Tokens, nonces, and data requiring cryptographic unpredictability. |

There is no single best RNG class for every scenario. Choose based on three questions:

1. Must outputs resist prediction by an adversary?
2. Will the instance be accessed concurrently by multiple threads?
3. Is a reproducible result sequence needed for debugging/simulation?

If the first answer is yes, prioritize `SecureRandom`. If you only need general pseudo-random numbers across multiple worker threads, `ThreadLocalRandom` is a natural fit. If you need to split generators for independent parallel tasks, `SplittableRandom` fits better. If maintaining legacy code or needing a seeded `Random` instance, you can continue using `Random`, while avoiding turning it into a hot contention point.

## 8. The RandomGenerator API in Java 17

Java 17 adds extended APIs for pseudo-random generators under JEP 356. `java.util.random.RandomGenerator` provides a common interface for many generators:

```java
import java.util.random.RandomGenerator;

RandomGenerator generator = RandomGenerator.getDefault();
int value = generator.nextInt(100);
double fraction = generator.nextDouble();
```

`RandomGenerator.getDefault()` returns the runtime's default generator. A common interface lets code depend on number generation operations rather than a concrete class.

Different generators still have their own contracts and properties. Using the `RandomGenerator` interface **does not automatically make an instance thread-safe**. Check the documentation of the chosen implementation before sharing it across threads.

Example accepting a generator as a parameter:

```java
import java.util.random.RandomGenerator;

static int rollDie(RandomGenerator random) {
    return random.nextInt(1, 7);
}
```

The method above does not decide which generator is used. The caller is responsible for providing an implementation and ensuring ownership/concurrency patterns fit that generator type.

### 8.1. Choosing a Generator by Name with RandomGeneratorFactory

Java 17 also provides `RandomGeneratorFactory` to query and instantiate generators by algorithm name:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator generator = factory.create(12345L);
System.out.println(generator.nextLong());
```

The algorithm name must exist in the target runtime. You can list supported factories:

```java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
```

This API is helpful when an application requires deliberate algorithm selection. Do not pick names based on guesswork; inspect the algorithms provided by the runtime and their documentation.

`RandomGenerator` is an abstraction for number generation, not a general security guarantee. When unpredictability is required, still choose `SecureRandom` and proper mechanisms.

## 9. Common Multithreaded Design Mistakes

### 9.1. Sharing One SplittableRandom Across All Workers

Flawed design:

```java
// Do not share this instance across threads.
SplittableRandom shared = new SplittableRandom();

Runnable task = () -> {
    int value = shared.nextInt(100);
    System.out.println(value);
};
```

`SplittableRandom` is not thread-safe. Multiple threads calling `nextInt()` concurrently on the same instance can invalidate behavior under the class contract.

Fix by splitting generators before handing them off:

```java
SplittableRandom root = new SplittableRandom(123L);
SplittableRandom forWorkerA = root.split();
SplittableRandom forWorkerB = root.split();
```

Then assign each child instance exclusively to one owning worker.

### 9.2. Sharing Random in a Hot Loop

Correct in safety, but causes contention:

```java
Random shared = new Random();

IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> shared.nextInt());
```

`Random` is thread-safe, yet all workers update the state of one instance. When random numbers are needed in a parallel stream, consider:

```java
IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> {
            int value = ThreadLocalRandom.current().nextInt();
            // Process value
        });
```

Or organize dedicated `SplittableRandom` generators per task via splitting. Which option to pick depends on reproducibility requirements and how work is divided.

### 9.3. Creating a New Generator on Every Call

Inefficient design:

```java
static int randomNumber() {
    return new Random().nextInt(100);
}
```

If called millions of times, continually allocating RNG objects is unnecessary. In multithreaded code, use `ThreadLocalRandom.current()` for general tasks; in seeded simulations, manage generators per worker or task.

### 9.4. Manual Clock-Based Seeding per Thread

Example prone to seed collisions:

```java
Random random = new Random(System.currentTimeMillis());
```

If multiple threads initialize at nearly the same instant, seeds can collide or have predictable relationships depending on creation timing. Clock-based seeds are not a secure entropy source and do not ensure independent sequences across threads.

Do not build manual seeding schemes for `ThreadLocalRandom`. With `SplittableRandom`, create one root generator and call `split()` for branches. For security tokens, use `SecureRandom` instead of combining timestamps, thread IDs, or counters.

### 9.5. Confusing Thread-Safe with Cryptographically Secure

`Random` being thread-safe does not mean its output resists prediction. Similarly, `ThreadLocalRandom` reduces contention but is not a security tool. Choose an API by **security purpose**, not by whether it supports multithreading.

## 10. Comprehensive Example: Generating Data Across Multiple Workers

The following example uses `ThreadLocalRandom` in a thread pool to generate general-purpose pseudo-random numbers:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadLocalRandom;

public class ConcurrentRandomDemo {
    public static void main(String[] args) {
        int workerCount = 4;
        int tasks = 12;

        ExecutorService pool = Executors.newFixedThreadPool(workerCount);
        try {
            for (int i = 0; i < tasks; i++) {
                int taskId = i;
                pool.submit(() -> {
                    ThreadLocalRandom random = ThreadLocalRandom.current();
                    int quantity = random.nextInt(1, 51);
                    System.out.printf(
                            "task=%d, worker=%s, quantity=%d%n",
                            taskId,
                            Thread.currentThread().getName(),
                            quantity
                    );
                });
            }
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac ConcurrentRandomDemo.java
java ConcurrentRandomDemo
```

On each run, task order, workers, and values may vary. This is normal in concurrent programs. `ThreadLocalRandom` handles per-thread generator usage; it does not make thread pool scheduling deterministic.

### If Reproducible Results Are Needed

In testing or simulation, you sometimes want the same seed to produce the same sequence. In that case, use a deterministic seeded generator with clear ownership:

```java
SplittableRandom root = new SplittableRandom(2026L);
SplittableRandom generatorForA = root.split();
SplittableRandom generatorForB = root.split();
```

To make results reproducible across runs, besides the seed you must preserve the split strategy, task distribution, number consumption order, and algorithm. If tasks are dynamically assigned to workers on a non-deterministic schedule, associating results with specific tasks can shift even if the overall generator source has a fixed seed.

## 11. Understanding Math.random() Properly

`Math.random()` is a convenience API returning a pseudo-random `double` from `0.0` (inclusive) to `1.0` (exclusive):

```java
double value = Math.random();
int die = (int) (Math.random() * 6) + 1;
```

For simple code with minimal generator control requirements, this can suffice. However, when algorithm selection, seeding, explicit bounds, or multithreaded performance are needed, use a dedicated RNG API. `Math.random()` is not a security API and should not be chosen to generate tokens.

## 12. Common Errors and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Multiple threads sharing `SplittableRandom` | Instance is not thread-safe. | Create separate generators per worker/task; split with `split()`. |
| Shared `Random` works correctly but throughput is low | One shared RNG state can cause contention. | Use `ThreadLocalRandom` for general multithreaded random numbers or split generators per task. |
| Using `ThreadLocalRandom` when seeds are needed for replay | API manages state per thread and does not support normal manual seeding. | Use `Random` or `SplittableRandom` with controlled seeds. |
| Using `Random` to generate security tokens | General RNGs are not designed to resist prediction. | Use `SecureRandom`. |
| Repeatedly calling `new Random()` in a loop | Unnecessary object allocation and poor concurrency handling. | Manage RNGs per worker or use `ThreadLocalRandom.current()`. |
| Tasks receive different sequences across runs | Scheduling, consumption order, or task partitioning changed. | Control both the seed and work-partitioning structure if reproducibility is needed. |
| Seeding per thread with timestamps | Seeds can collide or be predictable. | Use appropriate RNG seed/split mechanisms; use `SecureRandom` for security. |
| Assuming `RandomGenerator` is inherently thread-safe | Common interface does not override an implementation's specific contract. | Read thread-safety docs of the actual generator. |
| Creating multiple `SecureRandom` instances hoping for higher speed | Initialization/seeding has cost and depends on the provider. | Benchmark real load; use `SecureRandom` per API and security policy. |

## 13. Practice Exercises

### Exercise 1 — Distinguishing Safety and Performance

An application has 16 worker threads. All call `nextInt()` on a single `Random` instance.

1. Is this usage guaranteed thread-safe by `Random`?
2. Can contention occur?
3. Which API is more suitable if only general pseudo-random numbers are needed?

**Hint:** `Random` is thread-safe, yet a shared instance can experience state contention. Consider `ThreadLocalRandom.current()`.

### Exercise 2 — Fixing SplittableRandom Usage

The following snippet is improper:

```java
SplittableRandom random = new SplittableRandom();

Runnable task = () -> {
    System.out.println(random.nextInt(100));
};
```

Create a root generator, split two child generators with `split()`, and assign each child generator to a separate task. Explain why two tasks must not share one child generator.

### Exercise 3 — Choosing an API by Requirement

Select the most appropriate API for each scenario:

| Scenario | Reference Choice |
| --- | --- |
| Generating random numbers per request on a thread pool | `ThreadLocalRandom` |
| Splitting generators across parallel simulation branches | `SplittableRandom` |
| Generating random tokens used in authentication | `SecureRandom` |
| Legacy code needing a deterministic seeded generator | `Random` or an appropriately seeded generator |

Also explain why `SecureRandom` cannot be replaced by `ThreadLocalRandom` merely because the latter is more convenient in multithreaded environments.

### Exercise 4 — Finding Causes of Hard-to-Reproduce Sequences

A parallel stream uses `SplittableRandom`, yet results bound to individual elements change across runs. List the factors that must be controlled: initial seed, split order, how branches are assigned to tasks, generator call order, and result processing.

### Exercise 5 — Using the RandomGenerator Abstraction

Write a method accepting `RandomGenerator` that generates a number from 1 to 6. Call it with a deterministic seeded generator, then explain why the common abstraction does not itself determine whether that generator may be shared across threads.

## 14. Takeaways When Designing RNGs for Multithreaded Programs

- Before sharing a generator, verify whether that instance is **thread-safe**.
- `Random` is thread-safe, yet a shared instance can become a contention hotspot when many workers call it repeatedly.
- `ThreadLocalRandom.current()` is the standard choice for non-security pseudo-random numbers in multithreaded code.
- `SplittableRandom` is not thread-safe; each thread/task needs to own its own generator, usually created with `split()`.
- `SecureRandom` is for security needs and is thread-safe per the API; evaluate providers and performance under real load.
- Seeds help reproduce number sequences, yet reproducing a parallel program's results also depends on how numbers are split and consumed.
- `RandomGenerator` is an abstraction, not a promise that all implementations share the same thread safety or security level.
- Do not use timestamps, thread IDs, or counters as ad-hoc substitutes for `SecureRandom` when generating secrets.

### References

- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html) — thread-safety contract and generation methods of `Random`.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html) — generator bound to the current thread.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html) — non-thread-safe generator and `split()` mechanism.
- [Java SE 17 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) — random number generation API for security purposes.
- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html) — common abstraction for generators in Java 17.
- [JEP 356: Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356) — generator APIs added in Java 17.
