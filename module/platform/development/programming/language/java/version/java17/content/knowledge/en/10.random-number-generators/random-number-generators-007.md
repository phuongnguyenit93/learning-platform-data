# `ints`, `longs`, `doubles` Streams and Limiting Element Counts in Java 17

## 1. Lesson Objectives

Java provides APIs to generate a sequence of pseudo-random values as a **Stream**. With `Random` and generators belonging to the `RandomGenerator` API, you can create:

- `IntStream` from `int` values using `ints(...)`.
- `LongStream` from `long` values using `longs(...)`.
- `DoubleStream` from `double` values using `doubles(...)`.

Each API group has overloads that create a stream with an **unlimited requested element count** and overloads that create a stream with a **fixed size**. In addition, there are overloads that bound the value range to generate numbers within a specific domain.

Example:

```java
Random random = new Random();

int[] fiveNumbers = random.ints(5, 1, 7).toArray();
```

This snippet creates a stream of exactly 5 `int` values, each between 1 and 6. The lower bound `1` is inclusive, and the upper bound `7` is exclusive.

After this lesson, learners should be able to:

1. Distinguish `ints()`, `longs()`, and `doubles()` from overloads taking `streamSize`.
2. Choose the right overload bounded by `origin` and `bound`.
3. Understand unlimited streams, finite streams, and how to use `limit()`.
4. Know how the position of `limit()` in a pipeline affects the number of output elements.
5. Use terminal operations to consume streams, avoiding non-terminating operations on infinite streams.
6. Choose an appropriate number generator in Java 17 and understand the limits of pseudo-random numbers.

## 2. Number Stream Generation APIs in Java 17

### 2.1. `RandomGenerator` and `Random`

Java 17 provides the common `java.util.random.RandomGenerator` API, defining the contract for pseudo-random number generators. `java.util.Random`, `SplittableRandom`, and `ThreadLocalRandom` are classes usable through this API.

Declaration example:

```java
import java.util.Random;
import java.util.random.RandomGenerator;

RandomGenerator generator = new Random(12345L);
```

The `generator` variable has interface type `RandomGenerator`, so you can call the number and stream generation methods declared by the interface. `new Random(12345L)` sets a fixed seed so the result sequence can be repeated when repeating the same generator usage.

If you are only studying the stream API, you can also use directly:

```java
Random random = new Random();
IntStream integers = random.ints();
LongStream longValues = random.longs();
DoubleStream decimals = random.doubles();
```

Specialized stream types offer advantages:

| API | Return Type | Element Type |
|---|---|---|
| `ints(...)` | `IntStream` | `int` |
| `longs(...)` | `LongStream` | `long` |
| `doubles(...)` | `DoubleStream` | `double` |

They avoid boxing each element into `Integer`, `Long`, or `Double` during typical numeric operations, while providing specialized operations such as `sum()`, `average()`, `min()`, `max()`, and `summaryStatistics()`.

### 2.2. There Is No `floats()` Stream in This API Group

`RandomGenerator`'s stream API provides `ints`, `longs`, and `doubles`; there is no corresponding `floats()` method. If an API requires `float`, convert deliberately while considering the precision loss:

```java
float sample = (float) random.nextDouble();
```

Do not switch to `float` solely because the type uses less memory if the problem requires `double` precision.

## 3. Stream Creation Overloads

For each numeric type, there are four main forms:

| Type | Unlimited, Full Domain | Finite, Full Domain | Unlimited, Bounded | Finite, Bounded |
|---|---|---|---|---|
| `int` | `ints()` | `ints(long streamSize)` | `ints(int origin, int bound)` | `ints(long streamSize, int origin, int bound)` |
| `long` | `longs()` | `longs(long streamSize)` | `longs(long origin, long bound)` | `longs(long streamSize, long origin, long bound)` |
| `double` | `doubles()` | `doubles(long streamSize)` | `doubles(double origin, double bound)` | `doubles(long streamSize, double origin, double bound)` |

These methods return streams; they **do not return a single number** and do not allocate an array on their own. Element generation and processing take place when the pipeline is consumed by a terminal operation.

### 3.1. Unlimited Element Streams

```java
IntStream allInts = random.ints();
LongStream allLongs = random.longs();
DoubleStream allDoubles = random.doubles();
```

These streams are **effectively unlimited**: the API does not require stopping after a fixed number of elements. You cannot consume them entirely with a terminal operation that reads the whole stream, such as `toArray()`, `sum()`, or `count()`, and expect the program to terminate normally.

If you only need the first few elements, use `limit(n)`:

```java
int[] firstTen = random.ints()
        .limit(10)
        .toArray();
```

The pipeline above only consumes 10 values and stops. `limit` is a **short-circuiting stateful intermediate operation**: it caps the number of elements passed downstream to subsequent steps.

### 3.2. Finite Streams with `streamSize`

```java
int[] values = random.ints(5).toArray();
long[] ids = random.longs(3).toArray();
double[] samples = random.doubles(4).toArray();
```

These overloads create streams with the specified number of elements. `streamSize` is of type `long` and must be **non-negative**:

- `streamSize == 0`: empty stream, zero elements.
- `streamSize > 0`: stream with the exact requested element count.
- `streamSize < 0`: throws `IllegalArgumentException`.

Example:

```java
System.out.println(random.ints(0).count()); // 0
System.out.println(random.ints(5).count()); // 5
// random.ints(-1); // IllegalArgumentException
```

A finite size establishes the element limit upfront. However, this does not mean you should allocate a massive array; `toArray()` allocates memory for the entire result and can cause `OutOfMemoryError` or exceed array size limits.

## 4. Value Ranges: Inclusive Lower Bound, Exclusive Upper Bound

Overloads with `origin` and `bound` all use the **half-open** interval convention:

\[
[\text{origin}, \text{bound})
\]

That is:

- `origin` is included in the valid value domain.
- `bound` is excluded from the valid value domain.
- Validity precondition: `origin < bound`.

### 4.1. With `ints(origin, bound)`

```java
int[] dice = random.ints(10, 1, 7).toArray();
```

Each value belongs to `1, 2, 3, 4, 5, 6`. You can never get `0` or `7`. This is how you generate outcomes for a six-sided die when only simulating face numbers.

### 4.2. With `longs(origin, bound)`

```java
long[] ids = random.longs(8, 1_000_000L, 9_000_000L).toArray();
```

Each random ID lies in `[1_000_000, 9_000_000)`. The upper bound 9,000,000 never appears.

### 4.3. With `doubles(origin, bound)`

```java
double[] ratios = random.doubles(5, 0.0, 1.0).toArray();
```

Each value belongs to `[0.0, 1.0)`. Values can equal 0.0, but cannot equal 1.0 due to the exclusive upper bound. The no-argument `doubles()` also generates in `[0.0, 1.0)`.

For `doubles(origin, bound)`, both `origin` and `bound` must be finite numbers and `origin < bound`; do not use NaN or infinity as bounds. Generated values are distributed across the specified domain according to API rules.

### 4.4. Boundary Examples

| Call | Value Domain | Notes |
|---|---|---|
| `ints(1, 6)` | `1, 2, 3, 4, 5` | 6 is excluded |
| `longs(0L, 1L)` | Only `0L` | Interval contains a single integer |
| `doubles(0.0, 1.0)` | `0.0 <= x < 1.0` | Never generates exactly 1.0 |
| `ints(5, 10, 10)` | Invalid | Both bounds are equal |
| `ints(5, 11, 10)` | Invalid | Lower bound exceeds upper bound |

If you want to generate an integer in a **closed interval inclusive of both** `min` and `max`, compute the exclusive upper bound safely. For example, with small values:

```java
int min = 1;
int maxInclusive = 6;
int value = random.nextInt(min, maxInclusive + 1);
```

For ranges near `Integer.MAX_VALUE`, adding `maxInclusive + 1` can overflow. Handle that separately or use a suitable range-building helper; never blindly increment the upper bound.

## 5. Limiting Element Count with `limit()`

`limit(long maxSize)` is an intermediate operation of the Stream API. It creates a stream containing at most the first `maxSize` elements of the preceding stream.

```java
int[] firstFive = random.ints()
        .limit(5)
        .toArray();
```

In this example:

1. `ints()` creates a source that can keep generating numbers.
2. `limit(5)` lets at most five elements pass downstream.
3. `toArray()` consumes the pipeline and collects five values into an array.

`maxSize` must be non-negative. `limit(0)` yields an empty stream; negative values throw `IllegalArgumentException`.

### 5.1. Comparing Sized Overloads and `limit`

Both approaches below can produce the same number of values:

```java
int[] a = random.ints(5).toArray();
int[] b = random.ints().limit(5).toArray();
```

However, they express different intents:

- `ints(5)`: requests a finite stream of five elements directly at the source.
- `ints().limit(5)`: truncates an unlimited source to at most five elements.

When the required element count is already known, the `streamSize` overload usually states the intent more clearly. `limit` is useful when the source is inherently unlimited or when the output count is determined mid-pipeline.

### 5.2. Placing `limit` Before or After `filter` Matters Greatly

Consider two pipelines:

```java
long atMostFiveMatches = random.ints()
        .limit(5)
        .filter(n -> n % 2 == 0)
        .count();

long fiveMatches = random.ints()
        .filter(n -> n % 2 == 0)
        .limit(5)
        .count();
```

The first pipeline:

- Takes at most 5 numbers from the source.
- Then filters for even numbers.
- The result can be 0, 1, 2, 3, 4, or 5 elements.

The second pipeline:

- Filters even numbers from an unlimited source.
- Takes at most the first 5 even numbers.
- With a standard pseudo-random source and a condition having positive match probability, the pipeline normally obtains 5 results; in principle, a predicate that never matches or a stream unable to yield further matching elements could prevent termination.

**Rule:** `limit(n)` counts elements passing through at the exact point where it appears in the pipeline, not always the number of source elements generated or final elements produced.

### 5.3. Limiting After `map`

```java
int[] squares = random.ints()
        .map(n -> n * n)
        .limit(10)
        .toArray();
```

The pipeline takes at most ten results after the `map` step; because each input produces exactly one output, it needs at most ten source numbers. Note that `n * n` on `int` can overflow; if the input domain is large, choose `long` or an appropriate overflow-handling rule.

### 5.4. `limit` Is Not an Overall Memory Limit

`limit(10)` caps the pipeline's output element count at that stage, but does not guarantee that every preceding step uses constant memory. An operation like `sorted()` must see the entire input before returning results; if placed before `limit` on an unlimited stream, the pipeline cannot finish:

```java
// Does not terminate: sorted must consume the entire unlimited source.
// random.ints().sorted().limit(10).toArray();

// Terminates: sorts only the first 100 numbers.
int[] smallestOfFirstHundred = random.ints()
        .limit(100)
        .sorted()
        .limit(10)
        .toArray();
```

The source-truncation step must precede any operation requiring all data when the source is unlimited.

## 6. Finite Streams After Filtering

When using an overload with `streamSize`, the number of elements **after filtering** can be smaller than the source count:

```java
long evenCount = random.ints(100)
        .filter(n -> n % 2 == 0)
        .count();
```

The source has exactly 100 numbers, yet the result only counts even numbers among those 100; there is no guarantee the count is 50. With an appropriate distribution, 50 is the approximate expectation, not a guaranteed count.

If exactly 20 even numbers are required, you can use:

```java
int[] twentyEvens = random.ints()
        .filter(n -> n % 2 == 0)
        .limit(20)
        .toArray();
```

The source is unlimited so it can continue generating until 20 matching results are obtained. Although the probability of falling short in practice is tiny for this predicate, this is still an algorithm whose stopping condition depends on producing enough matching results. For rare predicates, waiting for enough elements can take a long time or fail to terminate.

If strict resource control is needed, bound the source first and accept possibly fewer results, or write a loop with a maximum attempt limit and handle the insufficient-samples case.

## 7. Limits with `ints`, `longs`, `doubles` in Practice

### 7.1. Stream Size Uses `long`

Finite overloads take `long streamSize`, not `int`. This allows describing counts larger than the `int` range, though it does not mean every stream can be collected into an arbitrarily large Java array.

```java
long requested = 1_000_000L;
long count = random.ints(requested).count();
System.out.println(count); // 1000000
```

When processing very large results, use a streaming pipeline to compute aggregates or write incrementally instead of always calling `toArray()` or `toList()`.

### 7.2. `count()` and Terminal Operations

`count()` consumes the stream and returns the element count as a `long`. For a stream of known size whose pipeline contains only operations that do not alter element count, the implementation may optimize and avoid invoking the generator for every element. Do not rely on side effects in `peek` or lambdas to count generation calls.

Simple example:

```java
long count = random.ints(1_000)
        .count();
```

The result is `1000`; there is no need to allocate a 1000-element array just to get the size.

### 7.3. Do Not Reuse a Stream

A stream can only be consumed once. Example:

```java
IntStream numbers = random.ints(5);
long count = numbers.count();

// numbers.sum(); // IllegalStateException: stream has already been operated upon.
```

If you need two independent results, create two new streams from the generator or collect the data into a suitable structure and process that structure.

### 7.4. Avoid Side Effects in Pipelines

Intermediate operations are typically executed lazily. A snippet like:

```java
random.ints(10)
        .peek(System.out::println);
```

has not consumed the stream yet, so ten numbers have not been printed. A terminal operation is needed:

```java
random.ints(10)
        .forEach(System.out::println);
```

Even with a terminal operation, do not use `peek` to perform required business work. Use `map`, `forEach`, or an explicit processing construct aligned with the intent.

## 8. Choosing a Number Generator in Java 17

### 8.1. `Random`

`java.util.Random` is a simple, familiar choice that provides the stream overloads studied here. You can specify a fixed seed:

```java
Random random = new Random(2026L);
int[] sample = random.ints(5, 1, 100).toArray();
```

With the same seed and same ordered call sequence, `Random` has a contract to produce a reproducible pseudo-random sequence; useful for examples, tests, and repeatable simulations. A fixed seed does not turn results into cryptographically secure randomness.

`Random` is safe when shared across threads, though it can cause contention when multiple threads access a single instance.

### 8.2. `ThreadLocalRandom`

`ThreadLocalRandom.current()` returns the generator bound to the current thread:

```java
import java.util.concurrent.ThreadLocalRandom;

int[] values = ThreadLocalRandom.current()
        .ints(10, 1, 7)
        .toArray();
```

This is a convenient option for multithreaded code needing independent per-thread pseudo-random numbers without sharing one `Random` instance. You cannot arbitrarily seed the instance retrieved from `current()` the way you do with `new Random(seed)`.

### 8.3. `SplittableRandom`

`SplittableRandom` is designed to support splitting a generator into child generators, suited for computations divisible into independent parts:

```java
import java.util.SplittableRandom;

SplittableRandom random = new SplittableRandom(2026L);
int[] values = random.ints(10, 1, 7).toArray();
```

You can use `split()` to create child generators for individual tasks. This is helpful in parallel computation when each branch needs its own number source. Do not share one mutable generator state arbitrarily across tasks if reproducibility and result ordering matter.

### 8.4. `RandomGenerator` and Chosen Algorithms

Java 17 introduces `java.util.random.RandomGenerator` and factories to work with multiple algorithms. You can program against the interface:

```java
import java.util.random.RandomGenerator;

RandomGenerator generator = RandomGenerator.getDefault();
int[] values = generator.ints(10, 1, 7).toArray();
```

`getDefault()` provides the runtime's default generator. If you need a specific algorithm, look up a factory and choose an algorithm name supported by the Java environment rather than assuming every JDK or configuration uses the same default implementation.

When reproducibility across runs or environments is required, record the algorithm, seed, and usage sequence explicitly. Do not rely on the default generator if the application contract requires a stable result sequence across versions.

### 8.5. Pseudo-Random Numbers Are Not Cryptographic Random Numbers

`Random`, `SplittableRandom`, and `ThreadLocalRandom` suit simulations, sampling, games, or load distribution depending on requirements. Do not use them to generate passwords, session tokens, keys, or values that must resist prediction.

For security purposes, use `SecureRandom` and appropriate security APIs. Do not mistake having a long seed or visually unpredictable output for cryptographic guarantees.

## 9. Reproducibility and Ordering in Streams

### 9.1. Fixed Seeds for Tests

A test example can use a fixed seed:

```java
Random first = new Random(123L);
Random second = new Random(123L);

int[] a = first.ints(5, 0, 100).toArray();
int[] b = second.ints(5, 0, 100).toArray();

System.out.println(java.util.Arrays.equals(a, b)); // true
```

Two generators with the same seed and same call sequence reproduce results under `Random`'s contract. This is helpful when reproducing bugs or generating deterministic sample data.

### 9.2. Parallel Streams and Processing Order

You can request parallel processing:

```java
random.ints(1_000, 0, 100)
        .parallel()
        .forEach(System.out::println);
```

Print actions may appear in varying order because threads execute concurrently. If you need to respect the stream's encounter order:

```java
random.ints(10, 0, 100)
        .parallel()
        .forEachOrdered(System.out::println);
```

However, `forEachOrdered` can reduce parallelism. For large workloads, measure performance and only use parallel streams when tasks are sufficiently large, independent, and appropriate.

Do not assume that running with the same seed in an arbitrary parallel pipeline will produce the same output display order or the same execution schedule across environments. If strict reproducibility is required, explicitly define the generator, data partitioning strategy, combination order, and avoid depending on scheduling.

## 10. Integrated Example: Sampling, Filtering, and Limiting

The following program generates a finite number of samples, filters matching numbers, collects statistics, and illustrates truncating an unlimited stream with `limit`.

Create the file `Main.java`:

```java
import java.util.Arrays;
import java.util.Random;
import java.util.stream.IntStream;

public class Main {
    public static void main(String[] args) {
        Random random = new Random(2026L);

        // Generate exactly 12 integers in [10, 100).
        int[] samples = random.ints(12, 10, 100).toArray();
        System.out.println("Samples: " + Arrays.toString(samples));

        // Take at most 5 even numbers from the 12-element source.
        int[] evenFromSamples = Arrays.stream(samples)
                .filter(value -> value % 2 == 0)
                .limit(5)
                .toArray();
        System.out.println("Even: " + Arrays.toString(evenFromSamples));

        // Take 5 even numbers from an effectively unlimited source.
        int[] fiveEvens = random.ints()
                .filter(value -> value % 2 == 0)
                .limit(5)
                .toArray();
        System.out.println("Five evens: " + Arrays.toString(fiveEvens));

        // Take 4 doubles in [0.0, 1.0).
        double[] ratios = random.doubles(4).toArray();
        System.out.println("Ratios: " + Arrays.toString(ratios));

        // Empty stream because streamSize is 0.
        System.out.println(random.longs(0).count()); // 0
    }
}
```

Compile and run on JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

A fixed seed makes results repeatable when executing the same call sequence. The key point is not a particular sequence of numbers, but how limits are defined:

- `ints(12, 10, 100)` generates 12 numbers in `[10, 100)`.
- `filter(...).limit(5)` returns at most five even elements from the 12 samples.
- `ints().filter(...).limit(5)` continues pulling from an unlimited source until five matching elements are obtained.
- `doubles(4)` generates exactly four values in `[0.0, 1.0)`.
- `longs(0)` is an empty stream.

## 11. Common Mistakes

### 11.1. Calling a Terminal Operation on an Unlimited Stream

```java
// Does not terminate normally:
// long count = random.ints().count();
```

Add `limit` or choose a finite overload:

```java
long count = random.ints(1_000).count();
// Or:
long countLimited = random.ints().limit(1_000).count();
```

### 11.2. Misunderstanding the Upper Bound

```java
int value = random.ints(1, 10).findFirst().orElseThrow();
```

Values can be 1 to 9, excluding 10. If you need a different range, carefully check the `[origin, bound)` bound contract.

### 11.3. Placing `limit` Before `filter` When You Want Enough Matching Elements

```java
// May yield fewer than 10 even numbers:
int[] maybeTen = random.ints().limit(10)
        .filter(n -> n % 2 == 0).toArray();

// Takes at most 10 even numbers from the source:
int[] tenEvens = random.ints()
        .filter(n -> n % 2 == 0)
        .limit(10)
        .toArray();
```

The two pipelines are not equivalent. Choose the order based on whether you want to limit **input samples** or **filtered results**.

### 11.4. Calling `toArray` on a Huge Stream

A finite stream does not mean it is always safe to materialize the entire stream into an array. For large counts, use chunked processing, write to storage, or reduce data with appropriate operations.

### 11.5. Reusing a Stream

Each stream can only be consumed once. Calling a second terminal operation on the same instance typically throws `IllegalStateException`. Create a new stream for subsequent processing.

### 11.6. Assuming `limit` Guarantees the Pipeline Always Terminates

`limit(10)` waits for up to ten elements at its position. If preceded by a `filter` that never lets any element pass, the pipeline can run forever. If the predicate is very rare, collecting enough samples can take a very long time.

### 11.7. Using a Pseudo-Random Generator for Security

Do not use `Random` to generate login tokens or cryptographic secrets. Use `SecureRandom` and an appropriate security design.

## 12. Practice Exercises

### Exercise 1 — Generating an Exact Number of Elements

Write a program generating 20 integers in `[100, 200)`, converting them to an array, and printing the length.

Solution:

```java
int[] values = new Random().ints(20, 100, 200).toArray();
System.out.println(values.length); // 20
```

Explanation: the first overload argument takes `streamSize = 20`, followed by lower bound and upper bound.

### Exercise 2 — Generating Doubles in a Domain

Generate 8 doubles in `[-2.5, 2.5)`; write a condition checking each number.

```java
double[] values = new Random().doubles(8, -2.5, 2.5).toArray();
for (double value : values) {
    if (value < -2.5 || value >= 2.5) {
        throw new AssertionError("Out of range: " + value);
    }
}
```

### Exercise 3 — Distinguishing Sample Count and Result Count

Given a source of 100 integers. Count the even elements:

```java
long evenCount = new Random().ints(100)
        .filter(n -> n % 2 == 0)
        .count();
```

The result does not necessarily equal 50. Explain that 50 is the expected value when even/odd distribution is balanced, whereas the actual count is determined by the specific random sample.

### Exercise 4 — Getting Exactly 10 Numbers Divisible by 3

Write a pipeline from an unlimited source, filter numbers divisible by 3, and take the first 10 elements.

```java
int[] divisibleByThree = new Random().ints()
        .filter(n -> n % 3 == 0)
        .limit(10)
        .toArray();
```

Explain why placing `limit(10)` before `filter` can yield fewer than 10 numbers.

### Exercise 5 — Limiting the Number of Attempts

Suppose you need to find 5 numbers matching a potentially rare predicate, but must not try infinitely. Use a finite stream:

```java
int[] matches = new Random().ints(10_000)
        .filter(value -> value == 0)
        .limit(5)
        .toArray();
```

The result may contain fewer than 5 elements, including 0. Design a way to report "insufficient samples found" rather than assuming the stream always produces enough.

### Exercise 6 — Reproducing Results

Create two `Random` objects with the same seed, generate 10 numbers in the same domain, and use `Arrays.equals` to compare both arrays. Explain why a fixed seed is useful for testing but does not create a secure random source.

## 13. Completion Criteria

Learners complete this lesson when they can:

1. State the stream types and element types corresponding to `ints`, `longs`, and `doubles`.
2. Pick the right unlimited, finite, and range-bounded overload.
3. Explain that `streamSize` is the source element count, accepts 0, and rejects negative numbers.
4. Correctly predict the `[origin, bound)` range, validate bound preconditions, and avoid overflow when incrementing the upper bound.
5. Use `limit(n)` to truncate an unlimited source and explain how `limit` position interacts with `filter`, `map`, and `sorted`.
6. Distinguish source element count from post-filter element count; recognize that a pipeline might not produce enough matching results.
7. Explain lazy streams, terminal operations, single-consumption restrictions, and the risk of materializing overly large arrays.
8. Choose an appropriate `Random`, `ThreadLocalRandom`, `SplittableRandom`, or `RandomGenerator` for the context.
9. Know that ordinary pseudo-random numbers are not used for tokens or security-sensitive data.
10. Compile examples with JDK 17 using `javac --release 17`.

## 14. Official Documentation

- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): API contract and `ints`, `longs`, `doubles` overloads.
- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): traditional pseudo-random number generator and streams.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator bound to the current thread.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): generator supporting split for independent tasks.
- [Java SE 17 API — `IntStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html), [`LongStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html), and [`DoubleStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html): terminal operations, intermediate operations, and consuming primitive streams.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): generator APIs and improvements introduced in Java 17.

**Takeaway:** overloads with `streamSize` specify the source element count; unsized overloads create effectively unlimited streams; `limit(n)` caps the maximum elements at its pipeline stage; `origin` is inclusive while `bound` is exclusive. Understanding these four points helps generate the right sample count, the right value domain, and avoid non-terminating pipelines.
