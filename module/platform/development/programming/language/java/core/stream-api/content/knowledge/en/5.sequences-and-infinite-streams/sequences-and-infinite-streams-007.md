# Generating Sequences for Reproducible Simulation and Testing

In the **Java Stream API**, a data source does not have to be an existing `List`, array, or file. You can **generate sequences by rule** using `IntStream.range`, `Stream.iterate`, `Stream.generate`, or the number-generating methods of `Random`. This capability is useful when you need to create simulation data, test multiple scenarios, verify algorithms, or reproduce a bug.

An important requirement is **reproducibility**: given the same input configuration, you can deliberately regenerate the same data sequence and the same verifiable result. Using infinite streams, pseudorandom numbers, lazy operations, or parallel processing all affect this capability.

## 1. What Does "Reproducible" Mean?

We should distinguish three situations:

| Sequence type | Example | Condition for reproducibility |
| --- | --- | --- |
| **Fully deterministic** | `0, 2, 4, 6, ...`; a model updating state via a formula | Keep the initial value, transition rule, step count, and processing order the same. |
| **Seeded pseudorandom** | Temperatures, failure rates, sample coordinates in a simulation | Keep the seed, number generation algorithm, sample count, and draw order the same. |
| **External-state dependent** | `Math.random()`, current time, I/O, shared counter | Must control or replace dependencies; otherwise, results are usually hard to reproduce. |

A **seed** is the initial state of a pseudorandom number generator. It helps reproduce a sequence, **does not** make the sequence truly random, and **does not** guarantee that operations depending on multi-threaded scheduling will yield the same result.

In this lesson, "reproducibility" is considered at multiple levels: identical generated data, identical statistical results, and identical test behavior. A few floating-point computations may differ slightly when changing the reduction order or execution environment.

## 2. Choosing the Appropriate Sequence Source

The following APIs create a stream from an element-generation rule without pre-allocating a collection holding all the data:

| API | Result type | Finite / unbounded | When to use |
| --- | --- | --- | --- |
| `IntStream.range(start, end)` | `IntStream` | Finite, excludes `end` | Trial indices, simulation loops with a fixed step count. |
| `IntStream.rangeClosed(start, end)` | `IntStream` | Finite, includes `end` | Integer checkpoints in a closed interval. |
| `Stream.iterate(seed, next)` | `Stream<T>` | Potentially infinite | Next state depends on previous state. |
| `IntStream.iterate(seed, next)` | `IntStream` | Potentially infinite | Integer sequence by recurrence formula. |
| `Stream.iterate(seed, hasNext, next)` | `Stream<T>` | Stops by condition, Java 9+ | Model with an explicit termination condition. |
| `Stream.generate(supplier)` | `Stream<T>` | Potentially infinite, unordered | Samples generated on demand. |
| `new Random(seed).ints(n, min, max)` | `IntStream` | Finite, exact `n` elements | Seeded pseudorandom integer data. |
| `new Random(seed).doubles(n, min, max)` | `DoubleStream` | Finite, exact `n` elements | Simulating continuous quantities in a range. |

`Stream.iterate` is a source with an *encounter order*; `Stream.generate` creates a stream with no guaranteed order. Intermediate operations such as `map` and `filter` are **lazy**; element generation typically begins when a terminal operation like `toArray`, `count`, `collect`, or `findFirst` is invoked.

### Sequence Determined by Index

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = IntStream.range(0, 6)
    .map(i -> 3 + 4 * i)
    .toArray();

System.out.println(Arrays.toString(values));
// [3, 7, 11, 15, 19, 23]
```

The element at position `i` is computed directly from `i`, without needing to remember the previous element. This form is convenient when each simulation trial needs to be tested independently, including when splitting work in parallel.

### Sequence Determined by a Recurrence Rule

```java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = IntStream.iterate(3, value -> value + 4)
    .limit(6)
    .toArray();

System.out.println(Arrays.toString(values));
// [3, 7, 11, 15, 19, 23]
```

The output matches the `range` example, but the meaning differs: `iterate` computes the next value from the previous value. When the rule genuinely has sequential state, this is the more natural representation.

With Java 9 and above, you can attach the stopping condition directly to the source:

```java
import java.util.stream.IntStream;

IntStream.iterate(3, value -> value < 25, value -> value + 4)
    .forEachOrdered(System.out::println);
// Prints in order: 3, 7, 11, 15, 19, 23
```

The `hasNext` condition is checked on the candidate element **before** admitting it into the stream; the first value that fails the condition will not appear. For rules that can overflow `int` or `long`, design appropriate bounds, because integer addition in Java can overflow silently without throwing an exception.

## 3. Simulating a Time-Based Process with `iterate`

Consider an object with an initial temperature of 100°C in a 20°C environment. After each time step, its temperature moves 25% of the remaining distance toward the ambient temperature:

\[
T_{k+1} = T_k + 0.25(20-T_k)
\]

We can express this rule in a `DoubleStream`:

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

double[] temperatures = DoubleStream.iterate(
        100.0,
        current -> current + 0.25 * (20.0 - current)
    )
    .limit(5)
    .toArray();

System.out.println(Arrays.toString(temperatures));
// [100.0, 80.0, 65.0, 53.75, 45.3125]
```

Each element represents the **state at a point in time**, including the initial state. Running the same pipeline again with the same number of steps produces the exact same sequence, provided the formula and execution environment do not change. The sequence is lazy until `toArray()` is called, and `limit(5)` clearly specifies how many states are taken.

Some practical notes when applying this:

- The update rule should depend only on the current state and model parameters; avoid reading the system clock or mutating global variables inside the lambda.
- `iterate` has a data dependency between steps. Adding `parallel()` does not remove this dependency and usually does not bring the same benefit as splitting independent trials.
- With multiple state variables like position, velocity, and energy, you can use an immutable data type as the element of `Stream.iterate`, so each step returns a **new state**.
- `DoubleStream` avoids `Double` boxing when you only need to work on floating-point numbers.

## 4. Generating Seeded Pseudorandom Data

In simulations, we often need data that looks random yet can be regenerated to compare algorithms or reproduce bugs. `java.util.Random` lets you provide an explicit seed:

```java
import java.util.Arrays;
import java.util.Random;

long seed = 20261118L;

int[] run1 = new Random(seed)
    .ints(8, 0, 100)
    .toArray();

int[] run2 = new Random(seed)
    .ints(8, 0, 100)
    .toArray();

System.out.println(Arrays.equals(run1, run2)); // true
System.out.println(Arrays.toString(run1));      // Both regenerations are identical
```

`ints(8, 0, 100)` requests **8** numbers in the range `[0, 100)`: inclusive of 0 and exclusive of 100. `Random` in Java uses a deterministic specified algorithm; with the same seed and the **same sequence of method calls** in a sequential context, it produces the same result sequence.

This does not mean every usage of `Random` is reproducible. If you share one `Random` instance and call `nextInt` or `nextDouble` from different places, changing the call order changes the observed sequence. To keep each test case independent, create a dedicated generator from a seed stored with the test case.

### Sampling and Computing Statistics

```java
import java.util.Random;

long seed = 77L;
int trials = 10_000;
double failureProbability = 0.02;

long failures = new Random(seed)
    .doubles(trials, 0.0, 1.0)
    .filter(value -> value < failureProbability)
    .count();

System.out.println("Failure count: " + failures);
```

Each sample `value` is compared against a 2% threshold. When re-running with the same configuration, the failure count is reproduced. You **cannot** conclude that every 10,000 trials will have exactly 200 failures: 2% is a model probability, not an exact quota for a single sample run.

If you need to generate samples via a `Supplier`, you can use:

```java
import java.util.Random;
import java.util.stream.Stream;

Random random = new Random(77L);

double[] values = Stream.<Double>generate(random::nextDouble)
    .limit(5)
    .mapToDouble(Double::doubleValue)
    .toArray();
```

The `random::nextDouble` supplier reads and mutates the state of a generator. This usage is easily reproducible only when **traversed sequentially**, creating a new generator with the same seed before each run and keeping the exact same sampling request sequence. Do not share a stateful generator across tasks and then rely on call order to assign results to individual trials.

### APIs Unsuitable as a Default Reproducible Source

`Math.random()` accepts no seed argument, and `ThreadLocalRandom.current()` is designed for multi-threaded use without offering a direct way to set a seed like `new Random(seed)`. Therefore, they are not convenient choices when an exact test case must be reproduced.

`SplittableRandom` can be useful for parallel computation because it supports splitting generators via `split()`, yet reproducibility still requires a stable splitting and seeding strategy; splitting based on thread scheduling can cause different runs to receive different samples. Also, do not use `Random` or `SplittableRandom` to generate secret keys or security tokens; cryptographic tasks require the `SecureRandom` API and separate testing requirements.

## 5. Distinguishing Three Levels of Reproducibility in Parallel Runs

A fixed-seed source is **not enough** to guarantee reproducible results when applying `parallel()`. Separate three requirements:

1. **Unchanged data per simulation trial:** trial `i` always receives the same input, regardless of which thread executes it.
2. **Unchanged aggregated result:** independent trials are combined using an operation compatible with parallel reduction.
3. **Unchanged side-effect order:** logging, writing files, or updating shared variables occurs in a fixed order.

The first two requirements can be achieved by mapping each trial to deterministic data and combining results properly. The third requirement is hard to guarantee with `parallel().forEach(...)`; when each lambda runs is decided by the scheduler.

### Example: Monte Carlo Simulation Runnable Sequentially or in Parallel

We estimate π by generating `n` points in a unit square and counting how many fall inside a quarter-circle of radius 1. To ensure **trial `i` always gets the same point**, each trial receives its own seed derived from `baseSeed` and index `i`:

```java
import java.util.Random;
import java.util.stream.IntStream;

public class ReproducibleMonteCarlo {
    // Mix bits using a deterministic formula to derive a seed for each trial.
    static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }

    static long countInside(int trials, long baseSeed, boolean parallel) {
        IntStream indexes = IntStream.range(0, trials);
        if (parallel) {
            indexes = indexes.parallel();
        }

        return indexes.filter(index -> {
            Random sampleRandom = new Random(mix64(baseSeed + index));
            double x = sampleRandom.nextDouble();
            double y = sampleRandom.nextDouble();
            return x * x + y * y <= 1.0;
        }).count();
    }

    public static void main(String[] args) {
        int trials = 100_000;
        long seed = 20261118L;

        long sequential = countInside(trials, seed, false);
        long parallel = countInside(trials, seed, true);

        System.out.println(sequential == parallel); // true
        double pi = 4.0 * sequential / trials;
        System.out.println("Estimated pi = " + pi);
    }
}
```

Here, each predicate only uses `index`, `baseSeed`, and a **local** generator. There is no shared `Random` object consumed concurrently across threads. `count()` aggregates integers deterministically, so the count of points inside the circle is identical between both modes for the same algorithm and data. The `mix64` function is a deterministic bit-mixing step to disperse seeds; it **does not prove** statistical independence of samples and has no cryptographic purpose.

This approach also has a cost: allocating a `Random` for **every** simulation trial. For problems requiring very high performance, you can design an index-based number generator or partition work into chunks with pre-assigned seeds, though you must re-verify reproducibility and statistical quality.

You **should not** replace `sampleRandom` with a shared `Random` in the snippet above. Even if the generator is synchronized to prevent state corruption, which numbers trial `i` receives would still depend on the order in which threads call the generator. Nor should you expect `parallel().forEach(System.out::println)` to print in the same order across runs; if you must preserve encounter order for display, consider `forEachOrdered`, accepting the coordination overhead.

### Note on Floating-Point Arithmetic

`count()` in the example yields an exact integer result. However, `double` addition is not strictly associative mathematically due to binary rounding. Therefore, `parallel().mapToDouble(...).sum()` or `reduce` on floating-point numbers can produce tiny differences compared to sequential execution when reduction order changes. When testing floating-point results, define an appropriate tolerance threshold rather than always requiring identical bit patterns.

## 6. Bounding Sequences to Guarantee Program Termination

`Stream.iterate(seed, next)` and `Stream.generate(supplier)` can create infinite sources. Terminal operations like `count()`, `collect(...)`, and `toArray()` that need **all data** cannot terminate without a finite boundary.

```java
import java.util.stream.IntStream;

// Stop after exactly 100 samples.
long count = IntStream.iterate(0, n -> n + 1)
    .limit(100)
    .count();

System.out.println(count); // 100
```

For fixed-length sources, `IntStream.range(0, 100)` is usually clearer than `iterate(...).limit(100)`. When bounding by sequence content, Java 9+ provides `takeWhile` or the three-argument overload of `iterate`. Understand clearly the difference between `filter` and `takeWhile`:

```java
import java.util.stream.IntStream;

int[] prefix = IntStream.of(2, 4, 7, 8, 10)
    .takeWhile(n -> n % 2 == 0)
    .toArray();
// [2, 4] — stops taking prefix at 7.

int[] allEven = IntStream.of(2, 4, 7, 8, 10)
    .filter(n -> n % 2 == 0)
    .toArray();
// [2, 4, 8, 10] — also inspects elements after 7.
```

**A short-circuiting operation does not always guarantee termination.** For example, `Stream.generate(() -> 0).filter(n -> n == 1).findFirst()` will keep searching without ever encountering the required element. `sorted()` before `limit()` may force reading the entire source to sort; thus `infiniteStream.sorted().limit(10)` is not a safe way to produce 10 values.

For long simulations, store only the necessary statistics instead of calling `toArray()` on all samples. A finite stream containing hundreds of millions of elements can still cause an out-of-memory error if collected entirely into a collection.

## 7. Designing Reproducible Tests That Randomness Won't Make "Flaky"

A simulation data test should record the **seed, step count, model parameters, and expectations**. There are two common types of expectations:

- **Exact results:** run the same seed and pipeline to verify identical generated output; suitable for reproducing a specific bug.
- **Model invariants:** all values fall within a valid range, counts are non-negative, success counts do not exceed total trials; useful for testing many seeds without tying expectations to a single random sequence.

Example test independent of any testing library:

```java
import java.util.Arrays;
import java.util.Random;

public class ReproducibleDataTest {
    static int[] samples(long seed) {
        return new Random(seed).ints(100, 0, 50).toArray();
    }

    public static void main(String[] args) {
        long seed = 123456L;
        int[] first = samples(seed);
        int[] second = samples(seed);

        if (!Arrays.equals(first, second)) {
            throw new AssertionError("Same seed but different data");
        }
        if (first.length != 100) {
            throw new AssertionError("Wrong sample count");
        }
        if (Arrays.stream(first).anyMatch(x -> x < 0 || x >= 50)) {
            throw new AssertionError("Value outside [0, 50)");
        }
    }
}
```

Do not require a small random sample to have an error rate, mean, or frequency **exactly equal** to the probabilistic expectation: such a test can fail even when the algorithm is valid. When testing statistical properties, choose an appropriate sample size, acceptance interval, and confidence level; for regression testing, you can use a fixed set of seeds.

If a bug is discovered with a specific seed, record:

```text
baseSeed=20261118
trials=100000
generator=java.util.Random
mode=sequential
modelVersion=1
```

This is a **configuration example**, not program output. For more complex models, also record input data, processing order, parameters, and relevant runtime or library versions.

## 8. Common Errors and How to Prevent Them

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Re-running a test produces different data | Using `new Random()` without a seed, `Math.random()`, system clock, or external state | Fix the seed and inputs; create a new generator per test case. |
| Same seed yields different per-index results when switching to `parallel()` | Multiple trials drawing from a shared generator in non-deterministic order | Generate data independently by index or pre-assign seeds per chunk. |
| Stream runs forever without output | Infinite sequence paired with `count`, `collect`, or an unreachable short-circuit condition | Use a finite source, `limit`, or an actually reachable stopping condition. |
| Test checking random rates passes intermittently | Checking probability with exact equality or overly tight thresholds | Check invariants; use statistics and reasonable error margins. |
| Data or sum changes due to processing order | Side effects in `map`, `peek`, `forEach`; non-associative combiner | Use pure lambdas and contract-compliant reductions. |
| `limit` returns an unexpected sample set | Unstable encounter order or using `unordered()` | Assign sample indices explicitly, preserve encounter order when business logic requires it. |
| `iterate` loop unexpectedly repeats values | Integer overflow, zero step size, or rule failing to reach stopping point | Bound step count and verify termination condition and value range. |
| Out of memory during sampling | Collecting the entire stream into a huge array or list | Stream-process elements and compute statistics with an appropriate terminal operation. |

### Self-Review Checklist Before Running a Simulation

1. Is each trial determined by its index or by the previous state?
2. Are the seed and generation algorithm passed explicitly and saved?
3. Does the stream have an element limit or a genuinely reachable stopping condition?
4. Do any lambdas depend on the clock, I/O, shared variables, or thread scheduling order?
5. Does result ordering need to be preserved, and is the aggregation safe in parallel?
6. Which parts must be compared for exact equality, and which must allow floating-point error or statistical variance?
7. Can a failing case be reproduced solely from the seed, parameters, step count, and model version?

## 9. Mini Practice Exercises

**Exercise 1 — Deterministic Sequence.** Generate 20 integers of the form `5 + 3 * i` using `IntStream.range`, then recreate them using `IntStream.iterate` combined with `limit`. Compare the two arrays with `Arrays.equals`. Explain why an index-based formula is more convenient when each element is computed independently.

**Exercise 2 — Reproducing a Bug.** Write `samples(seed)` to generate 1,000 integers in `[0, 100)`. Run it twice with seed `42L` and verify the two arrays are equal; change the seed and observe the result. Do not write a test assuming that any two different seeds **must** produce different arrays, because the API provides no such guarantee.

**Exercise 3 — Independent Simulation.** From the `ReproducibleMonteCarlo` example, test `10_000` and `100_000` trials. Verify `countInside(n, seed, false) == countInside(n, seed, true)` for the same `n` and seed, and confirm the point count is always within `[0, n]`. Observe that the estimate of π can vary when changing `n` or the seed.

**Key takeaway:** The Java Stream API helps express simulation sequences with lazy pipelines, from finite to infinite sources. For reproducible testing, make explicit the generator source, seed, step count, independence of each sample, stopping condition, and reduction contract. Those factors determine reproducibility far more than merely calling `parallel()` or setting a fixed seed alone.
