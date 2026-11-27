# Splitting Generators for Parallel Tasks in Java 17

When multiple tasks need to generate pseudo-random numbers concurrently, a critical question is **where each task gets its number sequence and whether generator state is shared**. If all threads call a single stateful generator, the program can suffer contention, lose control over consumption order, and fail to reproduce results. If each task creates its own generator from arbitrary seeds, sequences may not be separated intentionally.

Java offers options suited to different situations:

- **SplittableRandom** is designed for parallel computing: a parent generator can split into child generators, each used independently within one task.
- **RandomGenerator** and **RandomGeneratorFactory** from Java 17 provide a unified interface and a way to discover/select algorithms.
- **ThreadLocalRandom** fits when multiple threads need fast numbers without manual per-task seed management for replay.
- **Random** remains useful in some compatibility scenarios, though sharing a single instance can cause contention when many threads use it.
- **SecureRandom** is for security purposes; never substitute standard simulation generators when creating tokens or secrets.

The focus of this lesson is how to **partition generators by logical task**, avoid sharing mutable state, and preserve reproducibility when needed. Examples use Java 17 without preview features.

## 1. Why Should Multiple Tasks Not Share a Single Generator?

Standard pseudo-random generators do not generate fresh entropy on every call. They maintain internal state; each time a number is drawn, state updates to produce the next value.

Suppose multiple threads access one variable:

~~~java
Random random = new Random();

IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> {
            int value = random.nextInt();
            process(value);
        });
~~~

This snippet is not necessarily wrong in terms of thread safety: java.util.Random is designed for multithreaded use. However, all threads update the state of a single instance. Under heavy load, synchronizing state updates can become a contention hotspot. Moreover, which number is given to which task depends on the order threads invoke calls; rerunning with the same seed does not guarantee the same logical task receives the exact same values if consumption order shifts.

With SplittableRandom, sharing is outright unsafe:

~~~java
SplittableRandom random = new SplittableRandom(1234L);

IntStream.range(0, 1_000_000)
        .parallel()
        .forEach(i -> process(random.nextInt()));
~~~

**SplittableRandom is not thread-safe.** Multiple threads must not call methods concurrently on the same instance. State updates can race, and results are no longer guaranteed.

Another mistake is calling split() on the same parent generator directly inside parallel tasks:

~~~java
SplittableRandom root = new SplittableRandom(1234L);

IntStream.range(0, 100)
        .parallel()
        .forEach(i -> {
            SplittableRandom child = root.split(); // Unsafe
            process(child.nextInt());
        });
~~~

Even though each lambda obtains a child, the split() operation itself still accesses root concurrently from multiple threads. Splitting must be performed in a controlled place before handing each child generator to a dedicated task.

## 2. SplittableRandom: A Generator Suited for Parallel Computing

SplittableRandom has existed since Java 8 and remains supported in Java 17. It is designed to split a generator into child generators with independent state. Each child generator can be used by a thread or task without synchronizing with the parent or sibling generators.

~~~java
import java.util.SplittableRandom;

SplittableRandom parent = new SplittableRandom(2026L);

SplittableRandom firstTask = parent.split();
SplittableRandom secondTask = parent.split();

int firstValue = firstTask.nextInt();
int secondValue = secondTask.nextInt();
~~~

Meaning:

1. Create a root generator with a chosen seed.
2. Call split() on the thread owning parent to produce a child generator.
3. Keep calling split() to create additional generators as needed.
4. Hand each child generator to a single task, and let only that task use it.

Split generators do not share mutable state. The API describes generated sequences as having statistical independence suited for parallel computing; this is **not an absolute mathematical guarantee or cryptographic security**.

### Creating Seeded and Unseeded Generators

You can initialize with a seed:

~~~java
SplittableRandom reproducible = new SplittableRandom(987654321L);
~~~

Or let the library choose an initial seed:

~~~java
SplittableRandom automaticallySeeded = new SplittableRandom();
~~~

A fixed seed is useful for simulations, tests, and bug investigations because the same seed, same call pattern, and same split structure can reproduce the result sequence within the same implementation. Automatic seeding is useful when you do not need to reproduce a specific run.

Do not treat the seed as a secret or security mechanism. Anyone who knows the seed and algorithm can reproduce the sequence. Do not use SplittableRandom to generate passwords, session tokens, reset codes, keys, or security nonces.

### One Child Generator Should Belong to One Logical Task

Safe pattern:

~~~java
SplittableRandom root = new SplittableRandom(2026L);

SplittableRandom taskA = root.split();
SplittableRandom taskB = root.split();

// Task A uses only taskA.
// Task B uses only taskB.
~~~

Unsafe pattern:

~~~java
SplittableRandom shared = new SplittableRandom(2026L);

// Do not pass shared into multiple concurrent tasks.
~~~

Do not confuse **one generator per thread** with **one generator per task**. A thread can execute many tasks over time; a task can migrate to another thread in a ForkJoinPool. When reproducible results per unit of work are needed, bind the generator to a **task/chunk with a stable identifier**, rather than binding it to a physical thread.

## 3. Splitting Generators Before Running in Parallel

For a fixed number of tasks, you can create child generators sequentially first, then each parallel task receives exactly one generator.

~~~java
import java.util.SplittableRandom;
import java.util.stream.IntStream;

public class SplitBeforeParallel {

    static int simulate(SplittableRandom random) {
        return random.nextInt(1_000);
    }

    public static void main(String[] args) {
        int taskCount = 8;
        SplittableRandom seedSource = new SplittableRandom(2026L);
        SplittableRandom[] generators = new SplittableRandom[taskCount];

        // Only the current thread accesses seedSource in this loop.
        for (int task = 0; task < taskCount; task++) {
            generators[task] = seedSource.split();
        }

        int[] results = new int[taskCount];

        IntStream.range(0, taskCount)
                .parallel()
                .forEach(task -> {
                    // Each task has its own generator.
                    results[task] = simulate(generators[task]);
                });

        for (int task = 0; task < taskCount; task++) {
            System.out.println("Task " + task + ": " + results[task]);
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 SplitBeforeParallel.java
java SplitBeforeParallel
~~~

Because each task writes to its own array slot, no two tasks write to the same element. Generators are already created before the parallel stream starts, and only one task uses each generator. Completing the stream's terminal operation also ensures all tasks finish before reading the results array.

This pattern has these properties:

- Generator creation order is determined by the sequential loop.
- Which worker thread runs which task does not affect which generator is bound to a task index.
- The same seed, task count, split order, and generation logic can reproduce per-task results on the same implementation.
- Changing data partitioning, task count, or generator call count can alter results.

Do not call split() inside a parallel lambda on a shared root. Pre-splitting keeps state ownership explicit.

## 4. Monte Carlo Simulation Example with Dedicated Generators

Monte Carlo methods often repeat a randomized trial many times. This is an ideal case for dividing work into fixed chunks and assigning one generator per chunk.

We estimate π by sampling random points inside the square [-1, 1] × [-1, 1]. The proportion of points falling inside the unit circle approximates the circle's area divided by the square's area, i.e., π/4.

~~~java
import java.util.SplittableRandom;
import java.util.stream.IntStream;

public class ParallelMonteCarloPi {

    static long countInsideCircle(int samples, SplittableRandom random) {
        long inside = 0;

        for (int i = 0; i < samples; i++) {
            double x = 2.0 * random.nextDouble() - 1.0;
            double y = 2.0 * random.nextDouble() - 1.0;

            if (x * x + y * y <= 1.0) {
                inside++;
            }
        }

        return inside;
    }

    public static void main(String[] args) {
        long seed = 2026L;
        int taskCount = 8;
        int samplesPerTask = 250_000;

        SplittableRandom seedSource = new SplittableRandom(seed);
        SplittableRandom[] generators = new SplittableRandom[taskCount];

        for (int task = 0; task < taskCount; task++) {
            generators[task] = seedSource.split();
        }

        long[] hits = new long[taskCount];

        IntStream.range(0, taskCount)
                .parallel()
                .forEach(task -> {
                    hits[task] = countInsideCircle(
                            samplesPerTask,
                            generators[task]);
                });

        long totalHits = 0;
        for (long taskHits : hits) {
            totalHits += taskHits;
        }

        long totalSamples = (long) taskCount * samplesPerTask;
        double estimate = 4.0 * totalHits / totalSamples;

        System.out.println("Seed: " + seed);
        System.out.println("Samples: " + totalSamples);
        System.out.println("Estimated pi: " + estimate);
    }
}
~~~

Run:

~~~bash
javac --release 17 ParallelMonteCarloPi.java
java ParallelMonteCarloPi
~~~

The estimated value changes when you change the seed or task partitioning. With the same seed, task count, samples per task, and implementation, results are repeatable. Do not expect the estimate to equal π exactly; statistical error is inherent to Monte Carlo simulations.

The key point of this example is not the π formula, but that:

1. The root generator is used only sequentially to create child generators.
2. Each chunk has its own generator.
3. Each chunk has a deterministic sample count.
4. Each chunk writes its result to its own slot.
5. Summing the counts of points inside the circle uses integers, avoiding an unnecessary parallel floating-point double reduction.

If the number of tasks changes, per-task results also change because the split tree changes. If you need reproducible simulation results across varying parallelism levels, design fixed logical work units, or store each chunk's seed/ID rather than just the machine's thread count.

## 5. Recursive Splitting in ForkJoinTask

For recursively halved work, you can pass a generator into each node of a Fork/Join tree. Each node owns its own generator; when splitting a node, it creates generators for child branches before forking.

~~~java
import java.util.SplittableRandom;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.ForkJoinPool;

public class SplitForkJoinSum {

    static final class RandomSumTask extends RecursiveTask<Long> {
        private final int count;
        private final int threshold;
        private final SplittableRandom random;

        RandomSumTask(int count, int threshold, SplittableRandom random) {
            this.count = count;
            this.threshold = threshold;
            this.random = random;
        }

        @Override
        protected Long compute() {
            if (count <= threshold) {
                long sum = 0;
                for (int i = 0; i < count; i++) {
                    sum += random.nextInt(100);
                }
                return sum;
            }

            int leftCount = count / 2;
            int rightCount = count - leftCount;

            // Current node creates generators for both child nodes.
            SplittableRandom leftRandom = random.split();
            SplittableRandom rightRandom = random.split();

            RandomSumTask left =
                    new RandomSumTask(leftCount, threshold, leftRandom);
            RandomSumTask right =
                    new RandomSumTask(rightCount, threshold, rightRandom);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();

            return leftResult + rightResult;
        }
    }

    public static void main(String[] args) {
        int count = 1_000_000;
        SplittableRandom root = new SplittableRandom(42L);

        long result = ForkJoinPool.commonPool().invoke(
                new RandomSumTask(count, 10_000, root));

        System.out.println(result);
    }
}
~~~

In this example:

- Each task receives a generator via its constructor.
- A task uses only its own generator.
- Before creating two child branches, the parent task calls split() sequentially to create two generators.
- After handing generators to children, the parent does not use the child generators.
- Which worker executes which task never causes two tasks to share a generator.

The integer result here depends on the seed and task-splitting structure. Changing the threshold or branching changes the number generation order and may alter the sum. This demonstrates random state management, not an optimal algorithm for every workload. Spawning too many tiny tasks adds overhead, so the threshold should be chosen according to work cost.

### Ownership Rule During Recursive Splitting

~~~text
Parent task owns generator P
        |
        +-- P.split() --> Generator L --> used only by child L
        |
        +-- P.split() --> Generator R --> used only by child R
~~~

Calls to split() happen while the parent owns P. After handing L and R to the children, never pass the same generator to two branches or keep using one generator across multiple threads.

## 6. Reproducing Results in Parallel Programs

Reproducibility is a separate requirement and does not automatically emerge merely from using a fixed seed.

To reproduce a run, fix at least:

- Root seed.
- Chosen algorithm/generator.
- Order of split() calls and split tree structure.
- Logical task identifiers and counts.
- Number of generator calls in each task.
- Control flow and number consumption order inside each task.
- Environment version if results must match across multiple JDK versions or implementations.

### Reproducibility by Task Rather Than by Thread

Suppose there are 8 data chunks. Create 8 child generators indexed 0 to 7 and assign generator i to chunk i. If ForkJoinPool runs chunk 3 on worker-1 today and worker-5 next time, chunk 3 still uses the 3rd generator.

Conversely, if each worker thread keeps its own generator and processes chunks assigned by the scheduler, which chunk gets which sequence can vary with scheduling. That works when only throughput matters, but is unsuitable when reproducibility by work ID is required.

### Root Seed and Per-Task Seeds

An easy approach that should not be applied mechanically is creating seeds via addition:

~~~java
long taskSeed = rootSeed + taskId;
SplittableRandom random = new SplittableRandom(taskSeed);
~~~

This can work in simple designs if the algorithm and seed domain are analyzed, but it does not clearly express splitting one state stream into child streams and can create unwanted seed relationships as designs scale.

If the goal is to partition a pseudo-random source across parallel branches, use SplittableRandom's split() or a splittable generator selected via RandomGeneratorFactory. Do not invent custom seed-splitting schemes without domain expertise and statistical testing.

### Recording Seeds for Debugging

For repeatable simulations or tasks, record the necessary metadata:

~~~text
algorithm = SplittableRandom
rootSeed = 2026
taskCount = 8
samplesPerTask = 250000
partitionVersion = 1
~~~

If the split structure or algorithm changes, bump the partition version or record additional details so you know which runs are comparable. Do not treat simulation seeds like security secrets; a simulation seed is not a credential.

## 7. RandomGenerator in Java 17

Java 17 introduces the java.util.random package with the RandomGenerator interface and factory system to work with many pseudo-random algorithms under a unified API. Random, SplittableRandom, ThreadLocalRandom, and other generators can be used through this interface.

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class GeneratorFactoryDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator random = factory.create(2026L);
        System.out.println(random.nextInt(100));
        System.out.println(random.nextDouble());
    }
}
~~~

The factory allows selecting an algorithm by name and initializing it with a seed. The algorithm name must exist in the target runtime. Do not assume algorithm names across all JDKs/vendors are identical beyond those guaranteed by the specification; you can list available algorithms:

~~~java
RandomGeneratorFactory.all()
        .map(RandomGeneratorFactory::name)
        .sorted()
        .forEach(System.out::println);
~~~

### Choosing a Generator Capable of Splitting

If you want to use an algorithm other than SplittableRandom for parallel work, check whether the factory supports splitting before using it:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

if (!factory.isSplittable()) {
    throw new IllegalStateException("Selected generator cannot be split");
}

RandomGenerator generator = factory.create(2026L);
if (!(generator instanceof RandomGenerator.Splittable splittable)) {
    throw new IllegalStateException("Generator does not implement Splittable");
}

RandomGenerator.Splittable child = splittable.split();
int value = child.nextInt();
~~~

Pattern matching for instanceof has been standard since Java 16, so this example is valid in Java 17. Checking split capability matters because not every RandomGenerator provides the splitting contract. When writing general-purpose libraries, accept RandomGenerator.Splittable or explicitly check the capability rather than casting blindly.

### Decoupling the Generation API from the Algorithm

When a method only needs random numbers, it can accept RandomGenerator instead of depending directly on a concrete class:

~~~java
import java.util.random.RandomGenerator;

static int chooseIndex(RandomGenerator random, int size) {
    if (size <= 0) {
        throw new IllegalArgumentException("size must be positive");
    }
    return random.nextInt(size);
}
~~~

This design lets tests pass a fixed-seed generator and applications pick algorithms as required. If a method needs to split the generator itself, the parameter type must express that capability, e.g. RandomGenerator.Splittable.

## 8. Comparing Random, ThreadLocalRandom, SplittableRandom, and RandomGenerator

| Generator / API | Ownership and Multithreaded Usage | Seed Control | Best Suited For |
| --- | --- | --- | --- |
| Random | Thread-safe; sharing across many threads can cause contention | Has seed constructor | Legacy API compatibility, simple tasks, or moderate-load sharing |
| ThreadLocalRandom | Per-thread generator, no shared locks needed | Does not let applications set seed via setSeed; unsuitable for per-task replay | Parallel tasks needing fast random numbers without per-job seeds |
| SplittableRandom | Not thread-safe; split generators and give each instance to one task | Has seed constructor | Simulations and parallel computations with explicit splitting structure |
| RandomGenerator | Unified interface; thread-safety depends on implementation | Depends on implementation/factory | Writing APIs decoupled from a specific algorithm |
| RandomGeneratorFactory | Selects and instantiates implementations; not a generator used directly | Factory supports create(seed) | Discovering algorithms, checking capabilities, and choosing generators |
| SecureRandom | Designed for cryptographic purposes; separate contract | Supports seed/reseed via API/provider, though never self-seed with predictable values | Tokens, nonces, keys, and data needing unpredictability |

### Random

Random is stateful and supports multithreaded use. This prevents race conditions during seed updates, though one shared instance can experience contention. If threads need independent pseudo-random streams for heavy tasks, partitioning generators per task is usually cleaner.

### ThreadLocalRandom

ThreadLocalRandom.current() returns the generator bound to the current thread. It is useful when tasks do not need dedicated generators passed in and do not need sequence replay per job. You cannot arbitrarily seed ThreadLocalRandom using setSeed; that method does not support it.

ThreadLocalRandom is bound to threads, so the same task can receive different values if run on another thread or if execution order changes. Do not use it when mapping a fixed seed to each work chunk is needed.

### SecureRandom

SecureRandom is used for data requiring unpredictability, such as authentication tokens or cryptographic values. It is not a replacement for SplittableRandom in parallel simulations. Do not generate tokens using Random, ThreadLocalRandom, or SplittableRandom simply because those APIs are faster.

## 9. Parallel Streams: Patterns to Use and Avoid

### Avoid Sharing a Non-Thread-Safe Generator

~~~java
SplittableRandom shared = new SplittableRandom(10L);

IntStream.range(0, 1000)
        .parallel()
        .map(i -> shared.nextInt())
        .sum();
~~~

Unsafe because multiple workers access shared concurrently.

### Avoid Splitting the Root Inside a Parallel Lambda

~~~java
SplittableRandom root = new SplittableRandom(10L);

IntStream.range(0, 1000)
        .parallel()
        .map(i -> root.split().nextInt())
        .sum();
~~~

Also unsafe because root.split() is invoked concurrently.

### Split First, Use Later

~~~java
int taskCount = 16;
SplittableRandom root = new SplittableRandom(10L);
SplittableRandom[] randoms = new SplittableRandom[taskCount];

for (int i = 0; i < taskCount; i++) {
    randoms[i] = root.split();
}

int[] values = new int[taskCount];
IntStream.range(0, taskCount).parallel().forEach(i -> {
    values[i] = randoms[i].nextInt(100);
});
~~~

Each generator is owned by a task index. If each task needs multiple calls, execute all of them inside the same lambda/task without sharing the generator with other tasks.

### When Is ThreadLocalRandom Enough?

If you only need to process each element with a random value without per-element or per-chunk reproducibility:

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.stream.IntStream;

IntStream.range(0, 100_000)
        .parallel()
        .forEach(i -> {
            int sample = ThreadLocalRandom.current().nextInt(100);
            process(i, sample);
        });
~~~

ThreadLocalRandom is a convenient fit for this kind of work. However, you cannot simply pass a seed and expect every run to generate the exact same sample for each i. If reproducibility by task ID is required, allocate generators by ID rather than by thread.

## 10. Result Aggregation Order Can Also Affect Reproducibility

Splitting generators properly only solves number generation. Result aggregation also needs attention.

If each task produces an integer count, summing long results is numerically associative within non-overflowing ranges. If each task produces a floating-point double sum, combining results differently across reduction trees can alter the trailing bits.

Example:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

For simulations, you can store hit counts as long and sum sequentially or use a fixed-order aggregation. If double values must be aggregated, establish acceptable error bounds and an appropriate summation algorithm. Reproducing random sequences does not imply identical final floating-point results if reduction order changes.

## 11. Testing Generator Splitting Strategies

Tests should verify **ownership structure and reproducibility**, not try to prove statistical independence from a few runs.

### Testing Reproducibility with the Same Seed and Same Split Order

~~~java
import java.util.SplittableRandom;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SplitRandomTest {
    @Test
    void sameSeedAndSameSplitOrderReproduceTaskSequences() {
        long seed = 2026L;
        int taskCount = 4;
        int valuesPerTask = 10;

        SplittableRandom rootA = new SplittableRandom(seed);
        SplittableRandom rootB = new SplittableRandom(seed);

        for (int task = 0; task < taskCount; task++) {
            SplittableRandom a = rootA.split();
            SplittableRandom b = rootB.split();

            for (int i = 0; i < valuesPerTask; i++) {
                assertEquals(a.nextInt(), b.nextInt());
            }
        }
    }
}
~~~

This test verifies that two initializations with the same seed, same split order, and same call count yield identical sequences on the running implementation. It does not prove the streams are statistically independent.

### Testing Results by Task Index

You can write a function taking a fixed task count, allocating generators by index, and returning a results array. Call the function twice with the same seed and configuration and compare the arrays. This helps catch accidental generator sharing or altered allocation order.

### Testing Statistical Distribution

If the algorithm is used for simulation, examine:

- Mean, variance, and expected occurrence proportions within intervals.
- Whether buckets/value groups have reasonable distribution.
- Correlation between subsequences in representative workloads.
- Statistical tests tailored to the algorithm and application.

A test like assertNotEquals(sequenceA, sequenceB) does not prove random quality. Two distinct sequences can still have poor distribution, high correlation, or exposed patterns. Statistical testing is meaningful only when criteria, sample sizes, and acceptance thresholds are defined upfront.

### Do Not Use Unseeded Random Tests When Bug Replay Is Needed

When a test uncovers a bug during a run, log the seed and task-splitting metadata. A test that does not save its seed can make bugs hard to reproduce on reruns. Conversely, fixed-seed tests exercise only one data path; multiple seeds or boundary inputs are still needed when exploring robustness.

## 12. Common Mistakes When Splitting Generators

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Sharing one SplittableRandom across threads | Race conditions because the class is not thread-safe | Split before running in parallel; one child per task |
| Calling split() on root inside a parallel lambda | Multiple threads access root concurrently | Split on the thread owning root, then pass child |
| Creating generators per worker thread when per-task replay is needed | Chunks can receive different sequences when scheduling changes | Bind generators to stable task/chunk IDs |
| Arbitrarily using seed + taskId | No clear stream-splitting design | Use split or algorithms designed for that purpose |
| Assuming the same seed guarantees identical results after changing partitioning | Split tree and consumption counts change | Fix the task graph or store per-chunk seeds |
| Using SplittableRandom for security tokens | Sequences can be predicted if seed/state is known | Use SecureRandom |
| Using ThreadLocalRandom when replay is required | No per-task seed control | Use SplittableRandom or seeded generators |
| Checking only that two sequences differ to conclude independence | Does not verify statistical quality | Apply appropriate statistical evaluation |
| Using shared Random for heavy workloads | Contention on shared state | Pick per-task or per-thread generators as required |
| Creating too many tiny tasks and generators | Task/split overhead exceeds computation work | Choose appropriate chunk sizes/thresholds |
| Parallel double reduction expecting identical bits | Reduction order can alter results | Fix order or choose error-tolerant summation algorithms |

## 13. Requirement-Based Selection Guide

| Need | Suggested Choice |
| --- | --- |
| Parallel simulation needing clear seeding and sequence splitting | SplittableRandom, one child per task |
| Recursive Fork/Join work | Pass generator into task; split at parent node before fork |
| Parallel stream needing reproducible per-chunk results | Split generators sequentially by chunk ID, then run chunks in parallel |
| Parallel stream needing fast random numbers without per-task replay | ThreadLocalRandom.current() |
| Library API accepting multiple algorithms | RandomGenerator |
| Selecting algorithms by name/capability in Java 17 | RandomGeneratorFactory |
| Tokens, nonces, or secrets needing unpredictability | SecureRandom |

## 14. Design Principles

When splitting generators for parallel tasks in Java 17:

1. Choose a generator matching the goal: simulation, throughput, or security.
2. Do not share one SplittableRandom across multiple threads.
3. Perform split() while the parent generator is owned by a single thread; then hand each child to a dedicated task.
4. Bind generators to **logical units of work** if per-task reproducibility is required, not merely to worker threads.
5. Fix seed, split structure, call count, and partitioning if results must be reproducible.
6. Use RandomGenerator to abstract APIs; verify capabilities before requiring split.
7. Test reproducibility and statistical quality with separate criteria; neither replaces the other.
8. Pay attention to result aggregation order, especially when reductions involve float/double.

SplittableRandom cleanly solves the problem of partitioning pseudo-random state for parallel computations when each task owns a dedicated generator. RandomGenerator and RandomGeneratorFactory make designs more flexible in Java 17. Most importantly, establish clearly **who owns the generator, when the generator is split, and which unit consumes the sequence**; doing so avoids contention while keeping reproducibility under control.
