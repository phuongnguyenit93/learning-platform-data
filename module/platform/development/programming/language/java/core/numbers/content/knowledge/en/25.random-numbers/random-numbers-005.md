# SplittableRandom and Splitting Random Sources in Java

## 1. The problem: why do we need to “split” a random number source?

When a program executes only a single sequence of operations, you can create one pseudorandom number generator (*PRNG*) and call `nextInt()`, `nextLong()`, or `nextDouble()` sequentially. In real applications, work may branch into multiple paths: simulating multiple scenarios, processing a dataset across independent tasks, or using `ExecutorService` / fork-join for parallel execution.

If multiple tasks share **a single stateful generator object**, they can contend on state, make results hard to reproduce, or violate thread-safety contracts. `java.util.SplittableRandom` solves this problem via **`split()`**: creating a new generator object for a child branch. Each branch owns its own generator and draws subsequent numbers without accessing the same generator instance.

`SplittableRandom` has been available since Java 8 and is present in Java 17+, fitting high-performance random data generation and branching computations. It is a **pseudorandom generator**, not a cryptographic source of randomness; its output depends on internal state and algorithm, and does not guarantee secrecy or unpredictability if an attacker knows the seed or state.

Lesson goals: understand what `split()` does; how to organize a parent-child generator tree; how to supply seeds for reproducibility; how to assign one generator per task; how to use the API's value ranges; and when another solution must be chosen.

## 2. Creating SplittableRandom and calling basic methods

Two common ways to create an instance:

```java
import java.util.SplittableRandom;

// Explicit seed: suitable for reproducible experiments.
SplittableRandom reproducible = new SplittableRandom(2026L);

// Without passing a seed: the system generates an initial seed.
SplittableRandom ordinary = new SplittableRandom();
```

Commonly used APIs:

| Method | Meaning | Range |
|---|---|---|
| `nextInt()` | Pseudorandom 32-bit integer | Full `int` range |
| `nextLong()` | Pseudorandom 64-bit integer | Full `long` range |
| `nextDouble()` | Floating-point number from 0 up to below 1 | `[0.0, 1.0)` |
| `nextInt(10)` | Integer from 0 up to below 10 | `0..9` |
| `nextInt(5, 15)` | Integer from 5 up to below 15 | `5..14` |
| `nextLong(10L, 20L)` | `long` from 10 up to below 20 | `10..19` |
| `ints(5, 0, 10)` | `IntStream` with 5 elements from 0 up to below 10 | Each element `0..9` |
| `split()` | Produces a child `SplittableRandom` to assign to a work branch | New generator |

Intervals have **exclusive** upper bounds. Therefore, `nextInt(10)` never returns 10. For overloads with `origin` and `bound`, `origin < bound` must hold; `nextInt(0)` or `nextInt(10, 10)` is an invalid request and throws `IllegalArgumentException`.

`ints(...)` creates a stream of `int` values for processing with the Stream API. This is a **stream of numbers drawn from one generator**, different from `splits(...)` (Java 17+) which produces a stream of **child generators**. When a number stream is consumed, the associated generator advances its state as values are generated.

## 3. How does split() work?

`SplittableRandom` is a **stateful** object. Every call to `nextInt()` or other generation methods advances its state. `split()` also uses and updates the parent generator's state to create a **new child generator with its own state**. After `split()`:

1. The parent generator **can still be used** to generate numbers or create other branches.
2. The child generator is a **separate object** whose state can advance independently of the parent and other children.
3. Do not treat a child as a clone producing the same sequence as the parent; the goal of splitting is to produce pseudorandom streams **designed to have low correlation**, not exact duplicates.
4. Calling `split()` affects the parent's state. Therefore, **splitting order**, the number of splits, and the draw order are part of the generator's progression.

Illustrating how generators are assigned to a task tree:

```text
root = new SplittableRandom(seed)
   |
   +-- root.split() --> generator A --> task A's own nextInt calls
   |
   +-- root.split() --> generator B --> task B's own nextInt calls
   |
   +-- root.split() --> generator C --> task C's own nextInt calls
   |
   +-- root can still split further or generate numbers itself
```

Key rule: **split generators before handing work to each task**. Once handed over, each task only uses its own generator. Never call `root.split()` concurrently on the same `root` object from multiple threads.

You should neither expect nor require each child generator to produce numbers that **never collide**. Two independent branches can still happen to produce the same number, such as both getting `7` from `nextInt(10)`. “Splitting a source” is about organizing state and the statistical quality of random streams, **not guaranteeing that every output value is unique**.

### Why not create generators manually with the same seed?

The following is a common mistake:

```java
SplittableRandom a = new SplittableRandom(2026L);
SplittableRandom b = new SplittableRandom(2026L);
```

If two objects have the same seed and make the same call sequence, they produce **the exact same value sequence**. That is useful for reproducible testing, but not how you provision two distinct pseudorandom streams for two tasks. If you already have a root generator, call `root.split()` to obtain each child source.

Also avoid simulating `split()` via `new SplittableRandom(root.nextLong())`. The `split()` API is specifically designed to create child generators and manage stream splitting; use the proper API.

## 4. Java 17+ example: two branches and two parallel tasks

Create the file **`RandomSplitDemo.java`** with the standalone program below:

```java
import java.util.Arrays;
import java.util.SplittableRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RandomSplitDemo {
    private static int[] draw(SplittableRandom rng) {
        // Exactly 5 numbers, each in [0, 10).
        return rng.ints(5, 0, 10).toArray();
    }

    private static int[][] makePair(long seed) {
        SplittableRandom root = new SplittableRandom(seed);

        // Fixed splitting order.
        SplittableRandom childA = root.split();
        SplittableRandom childB = root.split();

        return new int[][] {draw(childA), draw(childB)};
    }

    private static int[] parallelSums(long seed) throws Exception {
        SplittableRandom root = new SplittableRandom(seed);

        // Create both sources on the coordinating thread before submitting.
        SplittableRandom rngA = root.split();
        SplittableRandom rngB = root.split();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> a = pool.submit(
                    () -> rngA.ints(1000, 0, 10).sum());
            Future<Integer> b = pool.submit(
                    () -> rngB.ints(1000, 0, 10).sum());

            // Read in task order A then B.
            return new int[] {a.get(), b.get()};
        } finally {
            pool.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        int[][] first = makePair(2026L);
        int[][] again = makePair(2026L);

        System.out.println("repeatable: "
                + Arrays.deepEquals(first, again));

        System.out.println("two children, five numbers each: "
                + (first.length == 2
                && first[0].length == 5
                && first[1].length == 5));

        System.out.println("range [0, 10): "
                + Arrays.stream(first)
                        .flatMapToInt(Arrays::stream)
                        .allMatch(n -> n >= 0 && n < 10));

        int[] p1 = parallelSums(2026L);
        int[] p2 = parallelSums(2026L);

        System.out.println("parallel repeatable: "
                + Arrays.equals(p1, p2));
    }
}
```

Compile and run on JDK 17+:

```bash
javac RandomSplitDemo.java
java RandomSplitDemo
```

Output:

```text
repeatable: true
two children, five numbers each: true
range [0, 10): true
parallel repeatable: true
```

Step-by-step explanation:

- `makePair(2026L)` creates a parent generator with a fixed seed, then **splits A before B**, and each child generates 5 numbers. Calling it again with the same seed and the same creation/execution order produces the same two arrays; comparison uses `Arrays.deepEquals` because the data has type `int[][]`.
- `ints(5, 0, 10)` draws exactly 5 elements in `[0,10)`. The `allMatch` check verifies the range rule; this is not a statistical quality test.
- `parallelSums` provisions separate `rngA` and `rngB` **before** calling `submit`. Each task sums 1,000 integers using its own generator. No two tasks access the same `SplittableRandom`.
- `Future.get()` waits for results to finish. The results match across runs because of the same seed, same split order, and fixed draw counts per branch. The order in which the OS schedules the two tasks does not affect the other branch's generator state.
- `pool.shutdown()` in `finally` shuts down the executor after use. This is resource management, unrelated to the random number generation algorithm.

The program intentionally prints **verifiable properties** rather than hardcoding ten specific pseudorandom numbers. To view the actual values, add `System.out.println(Arrays.deepToString(first));`. Numbers may repeat between the two branches, which does not mean `split()` is broken.

## 5. Reproducibility: a seed is necessary but not sufficient

With `new SplittableRandom(seed)`, a single thread making a **fixed** sequence of calls reproduces the generated sequence. When building a generator tree, results also depend on how splits are structured and how each branch is used.

For a test to reproduce reliably, keep all factors fixed:

1. **Root seed**: same seed when initializing the parent generator.
2. **Branching structure**: same number of `split()` calls and same creation order A, B, C.
3. **Source assignment**: each work branch receives its exact corresponding child generator.
4. **Call sequence and count within each branch**: for instance, each branch calls `nextInt(100)` exactly 1,000 times.
5. **Data and processing algorithm**: if conditions or random draw ordering change, outputs can also change.

This example **does not guarantee reproducibility** even with the same seed:

```java
SplittableRandom shared = new SplittableRandom(2026L);

// Do not use the same shared instance in two parallel tasks.
// Which thread calls nextInt() first depends on execution timing.
```

Beyond reproducibility, sharing as shown above violates thread safety. Another subtle bug is having each task call `root.split()` concurrently: the parent generator becomes shared mutable state. The simple and correct approach is to create child sources **on the coordinating thread** and pass each source to one task.

If work splits dynamically (such as fork-join spawning subtasks based on data), the spawning branch can call `split()` on **the generator owned by that branch itself** and pass the child to the new subtask. The requirement is that no two tasks operate on the same generator at the same time. To remain reproducible across runs, the splitting structure and consumption amounts must also be deterministic, or you need an explicit seeding strategy tied to task identifiers.

### Same seed does not mean results stay identical across code changes

If you add a `nextInt()` call before `split()`, reorder `split()` calls, or change how many numbers a branch consumes, subsequent sequences can change. Therefore, do not treat a single seed as a “snapshot” of the entire state of a parallel computation.

A test suite can record the seed, branching structure, and algorithm version if sequence replay is a critical requirement. For examples running in a single run on the same JDK, fixing the seed and operation sequence can be verified as shown in the program above.

## 6. Thread safety and performance: one generator per task

The Java API documentation states clearly that `SplittableRandom` instances are **not thread-safe**: do not treat one instance as a resource safe for concurrent use across multiple threads. They are designed to be **split and owned exclusively**, fitting branching computations, especially fork-join.

Organization rules:

| Usage pattern | Assessment | Reason |
|---|---|---|
| Single thread using one `SplittableRandom` | Appropriate | No concurrent access |
| Parent `split()` sequentially, then each task gets one child | Appropriate | Each generator's state is independent by owner |
| Two tasks calling `nextInt()` on the same instance | Avoid | `SplittableRandom` is not thread-safe |
| Multiple tasks calling `split()` concurrently on the same parent | Avoid | Mutates parent state concurrently, causing races |
| Each task creating `new SplittableRandom(2026L)` | Usually inappropriate | Tasks may generate identical sequences if operations match |
| Each task holds its own generator and spawns smaller work via `split()` | Appropriate with strict ownership | Creates a recursive split tree without sharing objects |

**Performance:** splitting sources helps eliminate synchronization around a single shared generator in parallel workloads. However, it **does not automatically make every algorithm faster**: task creation, result aggregation, and computation volume still govern real performance. When work items are tiny, parallel overhead can outweigh the gains. You do not need to call `split()` for every single random number; create one generator per **independent unit of work** and reuse it repeatedly.

## 7. Comparison with Random, ThreadLocalRandom, and SecureRandom

| API | Management model | When appropriate |
|---|---|---|
| `java.util.Random` | Sequential PRNG; shareable but concurrent use can cause contention | Legacy code, simple tasks, older API requirements |
| `ThreadLocalRandom.current()` | Dedicated generator bound to the executing thread, managed by the library | Convenient multithreaded code without manual per-task seed control |
| `SplittableRandom` | PRNG splittable into child generators via `split()` | Branching algorithms, fork-join, multi-task simulations, reproducibility via seed + stable split structure |
| `java.security.SecureRandom` | Generator for security requirements | Tokens, nonces, keys, and values needing unpredictability per security requirements |

`ThreadLocalRandom.current()` is useful when each thread simply wants numbers without sharing a global `Random`, but a thread-bound generator is not the same as a generator bound to a **logical task**: a task may run on different threads. `SplittableRandom` lets you hand **a specific instance to a specific task**, making branching models easier to control.

Never use `SplittableRandom` to generate passwords, session tokens, recovery codes, keys, or secret data. Knowing the seed or guessing the state can make pseudorandom sequences predictable; for security cases, use an appropriate `SecureRandom` API.

### Relationship to RandomGenerator in Java 17

Java 17 provides the `java.util.random.RandomGenerator` interface family. `SplittableRandom` implements `RandomGenerator.SplittableGenerator`, supporting splitting capabilities under the unified API. `SplittableRandom.split()` returns a `SplittableRandom`, so a child can be assigned directly to a variable of the same type. Java 17+ also provides `splits()` / `splits(long)` methods to produce a stream of child generators.

Example creating three child generators:

```java
import java.util.List;
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(2026L);
List<SplittableRandom> children = root.splits(3).toList();

// 3 separate sources; then assign each source to a task.
```

The snippet above is **illustrative code placed inside a method** (not a standalone program). Stream's `toList()` is available since Java 16. `splits(3)` creates a stream of three generators; consuming the stream executes the splits, so an explicit ownership strategy is required, especially if using a parallel pipeline. For a fixed number of tasks where clear ordering matters, a sequential `root.split()` loop is often easier to follow.

## 8. Common mistakes and how to check

### Confusing splitting sources with splitting value ranges

`root.split()` does **not** mean A only generates numbers in 0–4 while B only generates 5–9. Both A and B can still call `nextInt(0, 10)` and produce any number in `[0,10)`. Splitting separates **PRNG state**, not output value partitions.

If your problem requires non-duplicate IDs or exact value partitioning, use an ID-allocation strategy, value-set partitioning, or appropriate locks/transactions. Independent random sources do not replace uniqueness guarantees.

### Assuming split “clones” parent state

If you create `child = root.split()` and call `child.nextInt()` and `root.nextInt()`, there is no requirement for the two results to match. `split()` produces a new generator; it is not `clone()`, not an object copy, and not a “bookmark” that leaves the parent's state unchanged.

### Using the same generator across threads and seeing it “sometimes work”

A program not failing under light load does not prove sharing a generator is safe. Concurrent access to a non-thread-safe generator can corrupt data expectations and break reproducibility. Always establish single-task ownership for each generator.

### Changing branch creation order while expecting identical results

If on run one A receives the first `split()` child and on run two A receives the second child, A's sequence can change. When building parallel tests, fix the mapping **task → child generator**. A fixed seed alone is insufficient if the splitting schedule or source consumption changes.

### Confusing pseudorandom with security or “true randomness”

`SplittableRandom` has useful PRNG quality for many simulations and branching tasks, but provides no cryptographic properties. Even with separate branches, there is no promise that each generated number differs from all previous ones. Validate data by probability, distribution, range, and application requirements; do not draw statistical conclusions from a handful of samples.

### Creating too many generators or tasks

You can split a deep tree of generators matching a task tree, yet each generator and task has overhead. If you only need a sequence of 10,000 numbers on one thread, a single generator is usually simpler. Only split when you genuinely have **independent work**, especially for parallel execution.

## 9. How to apply and self-check

To use `SplittableRandom` for a job with N branches:

1. Create `root`. Use a fixed seed for testing; consider an appropriate seed source for production simulations.
2. Identify which branches can compute independently and which need their own generator.
3. On the coordinating thread, call `root.split()` once per branch and **bind each child to a branch identifier**.
4. Pass each child to one task; the task operates exclusively on its own generator.
5. When a task subdivides itself, only that task's generator may be used to `split()` further.
6. If reproducibility is needed, keep the seed, split tree, mapping order, and call counts fixed; write a test comparing outputs of two runs.
7. Never use `SplittableRandom` for cryptographic purposes.

**Self-check 1:** Two tasks both use `new SplittableRandom(7L)` and both call `nextInt(100)` three times. Do they produce two different streams? **No:** the same seed and call sequence lead to the exact same result sequence. Split from a parent generator if you want two distinct streams.

**Self-check 2:** After calling `SplittableRandom child = root.split()`, is it valid for task A to use `root` while task B uses `child`? **Yes**, provided no other thread touches those objects while running. The parent remains usable; however, for easier management, it is common to issue separate children and keep the parent as coordinator.

**Self-check 3:** Task A and task B both return `5` from `nextInt(10)`. Does this prove `split()` is broken? **No**. Two pseudorandom streams can output the same value. What matters is that state and access are managed separately.

**Key takeaway:** `SplittableRandom` is a **splittable** PRNG. Call `split()` on the branch that owns the generator and **assign the child to an independent task**. The same seed with the same split structure and consumption pattern enables reproducible tests; splitting does not guarantee unique values, does not automatically guarantee speedups, and provides no cryptographic security.
