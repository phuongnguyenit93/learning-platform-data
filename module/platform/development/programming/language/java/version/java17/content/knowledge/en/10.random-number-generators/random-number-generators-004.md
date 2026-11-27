# Listing, Inspecting Properties, and Choosing Pseudo-Random Number Generator Algorithms in Java 17

## 1. Why Do We Need to Choose a Generator Algorithm?

A Java application may need pseudo-random numbers for simulations, games, data sampling, load distribution, testing, or generating security data. Generators differ in speed, state size, period, ability to create separate streams, and cryptographic security level. **There is no single algorithm suited for every situation.**

For example:

- Monte Carlo simulations need pseudo-random sequences with good statistical properties that can be reproduced with a seed.
- Parallel computations need separate generators for each task, avoiding shared state that causes contention.
- Games may need integers in the range 1 to 6.
- Login tokens, password reset codes, or nonces in security protocols need a random source that is cryptographically unpredictable.

Java 17 adds a unified API in the `java.util.random` package via JEP 356. The `RandomGenerator` interface standardizes how generators are used, while `RandomGeneratorFactory` lets you **list, inspect properties of, and instantiate algorithms by name**.

> Distinguish **PRNG** (*pseudo-random number generator*) from **CSPRNG** (*cryptographically secure PRNG*). A PRNG meant for simulation is not automatically suitable for generating security secrets. For sensitive data, use `SecureRandom`.

## 2. Number Generation API in Java 17

### 2.1. `RandomGenerator` — The Common Interface

`RandomGenerator` is the primary interface for obtaining pseudo-random values. It includes methods for integers, floating-point numbers, booleans, normal distribution, exponential distribution, and streams:

~~~java
import java.util.random.RandomGenerator;

RandomGenerator random = RandomGenerator.getDefault();

int anyInt = random.nextInt();
int dice = random.nextInt(1, 7);       // 1 to 6
long idPart = random.nextLong();
double unit = random.nextDouble();    // [0.0, 1.0)
boolean enabled = random.nextBoolean();
double normal = random.nextGaussian();
double exponential = random.nextExponential();
~~~

Ranges have an inclusive lower bound and an exclusive upper bound. For example, `nextInt(1, 7)` can return 1, 2, 3, 4, 5, or 6; it will not return 7. `nextDouble()` returns a value from 0.0 (inclusive) to 1.0 (exclusive).

You can also create streams:

~~~java
random.ints(10, 1, 7).forEach(System.out::println);
~~~

This statement generates 10 integers in `[1, 7)`. Limit the stream size when you only need a fixed amount of data; overloads without a count can produce an effectively infinite stream.

### 2.2. `RandomGeneratorFactory` — Finding and Creating Algorithms

`RandomGeneratorFactory<T>` is the factory class for a specific algorithm. Key operations:

| Method | Meaning |
|---|---|
| `RandomGeneratorFactory.all()` | Returns a stream of factories available in the runtime. |
| `RandomGeneratorFactory.of(name)` | Looks up a factory by algorithm name. |
| `factory.create()` | Creates a generator with an automatically initialized seed. |
| `factory.create(seed)` | Creates a generator with a `long` seed. |
| `factory.name()` | Algorithm name. |
| `factory.group()` | Algorithm group. |
| `factory.stateBits()` | Number of state bits of the algorithm. |
| `factory.period()` | Period, of type `BigInteger`. |

Example selecting an explicitly named algorithm:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator random = factory.create(2026L);
System.out.println(random.nextInt(1, 7));
~~~

The algorithm name passed to `of` must exist in the runtime. If not found, the method throws `IllegalArgumentException`. `create(long)` uses the provided seed if supported by the algorithm; per the API contract, if the algorithm does not support that seed type, the factory may fall back to no-argument creation.

### 2.3. Familiar Classes Still Work

Java 17 continues to support `Random`, `ThreadLocalRandom`, `SplittableRandom`, and `SecureRandom`. These classes are compatible with the `RandomGenerator` interface in Java 17. New code can accept `RandomGenerator` as a parameter type so it does not depend on a concrete implementation.

~~~java
static int roll(RandomGenerator random) {
    return random.nextInt(1, 7);
}
~~~

The `roll` method can be used with a generator created from a factory, `Random`, `SplittableRandom`, or `SecureRandom` depending on requirements. Choosing the concrete type should happen where dependencies are wired, rather than scattering algorithm names throughout business logic.

## 3. Listing Algorithms Available in the Runtime

Do not guess which algorithms are available on a user's machine. `RandomGeneratorFactory.all()` provides the list of factories registered by the runtime. According to Java SE 17, this stream excludes algorithms marked deprecated; a specific JDK or provider may also add its own algorithms.

Create the file `RandomInventory.java`:

~~~java
import java.util.random.RandomGeneratorFactory;

public final class RandomInventory {
    private RandomInventory() {
    }

    public static void main(String[] args) {
        System.out.println("Default factory: "
                + RandomGeneratorFactory.getDefault().name());
        System.out.println();

        System.out.printf(
                "%-25s %-12s %7s %5s %10s %7s %7s %7s %7s%n",
                "NAME", "GROUP", "STATE", "EQ", "PERIOD",
                "SPLIT", "JUMP", "LEAP", "STREAM");

        RandomGeneratorFactory.all().forEach(factory ->
                System.out.printf(
                        "%-25s %-12s %7d %5d %10s %7s %7s %7s %7s%n",
                        factory.name(),
                        factory.group(),
                        factory.stateBits(),
                        factory.equidistribution(),
                        factory.period(),
                        factory.isSplittable(),
                        factory.isJumpable(),
                        factory.isLeapable(),
                        factory.isStreamable()));
    }
}
~~~

Compile and run with JDK 17:

~~~text
javac --release 17 -encoding UTF-8 RandomInventory.java
java RandomInventory
~~~

The program displays the default factory name, each algorithm's name and group, number of state bits, equidistribution level, period, and split/jump/leap/stream capabilities. `period` can be huge, so it is represented as `BigInteger`. Some algorithms or providers whose period is undetermined may return `BigInteger.ZERO`.

If you want to sort by name:

~~~java
var factories = RandomGeneratorFactory.all()
        .sorted((left, right) -> left.name().compareTo(right.name()))
        .toList();

factories.forEach(factory -> System.out.println(factory.name()));
~~~

`Stream.toList()` has existed since Java 16 and works in Java 17. The returned list is unmodifiable; here we only iterate over it to print names.

## 4. List of Algorithms Specified by Java SE 17

The Java SE 17 documentation lists the following algorithms in the `java.util.random` package. This is the standard required list of algorithms; a specific runtime may provide additional ones via providers.

| Group | Algorithm Name | `stateBits` | Equidistribution |
|---|---|---:|---:|
| LXM | `L32X64MixRandom` | 96 | 1 |
| LXM | `L64X128MixRandom` | 192 | 2 |
| LXM | `L64X128StarStarRandom` | 192 | 2 |
| LXM | `L64X256MixRandom` | 320 | 4 |
| LXM | `L64X1024MixRandom` | 1088 | 16 |
| LXM | `L128X128MixRandom` | 256 | 1 |
| LXM | `L128X256MixRandom` | 384 | 1 |
| LXM | `L128X1024MixRandom` | 1152 | 1 |
| Xoroshiro | `Xoroshiro128PlusPlus` | 128 | 1 |
| Xoshiro | `Xoshiro256PlusPlus` | 256 | 3 |
| Legacy | `Random` | 48 | 0 |
| Legacy | `SplittableRandom` | 64 | 1 |
| Legacy | `ThreadLocalRandom` | 64 | 1 |

LXM algorithms combine a linear congruential generator (LCG), an XOR-based generator (XBG), and an output mixing function. The name usually reflects the state size of the two components. `Mix` and `StarStar` describe the output mixing/scrambling style.

The Xoroshiro/Xoshiro group consists of algorithms based on XOR and bit-rotation operations. The Legacy group comprises classes predating Java 17. `SecureRandom` is an important security API, but it is not listed as a fixed algorithm row in this PRNG table; it uses its own provider mechanism and security algorithms.

### 4.1. Typical Periods

The *period* is the number of states in a cycle before a generator returns to a previously visited state. Some values from the Java SE 17 table:

| Algorithm | Period |
|---|---|
| `Random` | \(2^{48}\) |
| `SplittableRandom` | \(2^{64}\) |
| `ThreadLocalRandom` | \(2^{64}\) |
| `Xoroshiro128PlusPlus` | \(2^{128} - 1\) |
| `Xoshiro256PlusPlus` | \(2^{256} - 1\) |
| `L64X128MixRandom` | \(2^{64}(2^{128} - 1)\) |
| `L64X256MixRandom` | \(2^{64}(2^{256} - 1)\) |
| `L64X1024MixRandom` | \(2^{64}(2^{1024} - 1)\) |

A large period does not imply cryptographic security, does not guarantee every application will get better results, and does not mean a program will actually traverse every state during its lifetime. Read properties alongside workload characteristics.

## 5. Looking Up and Understanding Factory Properties

`RandomGeneratorFactory` exposes many properties for comparing algorithms. These properties describe technical characteristics; do not use a single metric as a general quality ranking.

### 5.1. `name()` and `group()`

- `name()` returns the algorithm name, e.g. `L64X128MixRandom`.
- `group()` returns the algorithm group, e.g. `LXM`, `Xoroshiro`, `Xoshiro`, or `Legacy`.

The name is the value passed to `RandomGeneratorFactory.of(name)`. If you want explicit algorithm control in an experiment or configuration, save this name along with the run configuration.

### 5.2. `stateBits()`

`stateBits()` indicates how many bits the algorithm uses to maintain its state. For example, `Random` has 48 bits, `Xoroshiro128PlusPlus` has 128 bits, and `L64X256MixRandom` has 320 state bits.

This is **not** the number of entropy bits guaranteed from a seed, nor is it a security certification. If a generator is initialized with a `long` seed, the seed input only has 64 bits; a larger internal state does not turn that seed into a 320-bit entropy source.

### 5.3. `period()`

The period is the number of states before the generator returns to an already visited state. The factory returns `BigInteger` because the period can be far larger than `long`.

Period is useful when simulations produce huge numbers of values, generate large permutations, or compare repetition potential. However, a large period does not replace evaluating statistical quality, cross-instance correlation, or security requirements.

### 5.4. `equidistribution()`

This property indicates the *k-equidistribution* level declared by the algorithm. Simply put, it describes how uniformly tuples of consecutive values are distributed across the period, according to the algorithm's definition.

For example, the Java 17 docs state `L64X128MixRandom` has level 2, `L64X256MixRandom` has level 4, and `L64X1024MixRandom` has level 16. A high equidistribution level can be useful when the algorithm is used for tuples of consecutive values. It does not mean the algorithm is automatically faster, better in all simulations, or cryptographically safer.

### 5.5. `isStatistical()`, `isStochastic()`, and `isHardware()`

| Property | Meaning |
|---|---|
| `isStatistical()` | The generator is computed arithmetically and is statistically deterministic. |
| `isStochastic()` | The generator uses an external source or entropy as input. |
| `isHardware()` | The generator uses a hardware device to generate entropy input. |

A purely algorithmic PRNG is typically statistical: given the same initial state and the same call sequence, it can reproduce the sequence. A stochastic source depends on external entropy sources and does not share the same reproducibility model.

These properties describe how values are produced, not a certification that you can use the generator as a source of keys or tokens. If cryptographic security is needed, choose `SecureRandom` and follow security API guidelines.

### 5.6. `isSplittable()`, `isJumpable()`, `isLeapable()`, and `isArbitrarilyJumpable()`

- **Splittable:** can split a generator into a new generator, with state placed in a different region of the period.
- **Jumpable:** can jump to a distant position in the period using an algorithm-defined jump step.
- **Leapable:** supports jump as well as leap with a much larger distance.
- **Arbitrarily jumpable:** supports jumping by a user-specified distance.

These are useful when a computation is divided into multiple tasks and each task needs its own pseudo-random number source. Do not share a single non-thread-safe instance across multiple threads just because the interface is named `RandomGenerator`.

### 5.7. `isStreamable()` and `isDeprecated()`

- `isStreamable()` indicates whether the generator can create streams of random values via the corresponding interface.
- `isDeprecated()` indicates whether the implementation/algorithm has been marked deprecated.

`RandomGeneratorFactory.all()` does not return deprecated factories per the Java 17 contract. The deprecated property remains useful when looking up a factory by name or inspecting metadata of a specific implementation.

## 6. Using Factories to Filter by Need

Once you understand the properties, you can find algorithms with matching characteristics instead of picking names by intuition.

List splittable generators:

~~~java
RandomGeneratorFactory.all()
        .filter(RandomGeneratorFactory::isSplittable)
        .forEach(factory ->
                System.out.println(factory.name()
                        + " stateBits=" + factory.stateBits()));
~~~

Find algorithms with at least 128 state bits:

~~~java
RandomGeneratorFactory.all()
        .filter(factory -> factory.stateBits() >= 128)
        .forEach(factory ->
                System.out.println(factory.name()));
~~~

Such filtering only narrows down the list. You still need to review period, equidistribution, split/jump capabilities, and actual purpose. For instance, an algorithm with 128 state bits is not inherently better than a 96-bit algorithm in every scenario.

### 6.1. Selecting by Explicit Name

If application requirements already specify an algorithm, create the generator by name:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator generator = factory.create(987654321L);
~~~

If you want to use the default generator:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.getDefault();

System.out.println("Selected: " + factory.name());
RandomGenerator generator = factory.create();
~~~

`getDefault()` chooses a factory meeting a minimum requirement of at least 64 state bits. The default algorithm name **is not guaranteed to stay the same across Java versions**, because algorithms may be improved. If results must be reproducible per experiment configuration, specify an explicit algorithm name.

## 7. Choosing an Appropriate Algorithm by Scenario

Java SE 17 documentation offers several recommendations by workload type. You can use the following table as a starting point:

| Need | Candidates to Consider | Reason |
|---|---|---|
| General purpose, non-cryptographic simulations or games | `L64X128MixRandom` | Good balance of speed, memory, and period per Java 17 docs. |
| Single-threaded, prioritizing small size and high speed | `Xoroshiro128PlusPlus` | Smaller state and good speed for single-threaded workloads. |
| 32-bit devices, few threads | `L32X64MixRandom` | May suit 32-bit hardware environments better. |
| Multiple threads created in batches | Jumpable generators like `Xoroshiro128PlusPlus` or `Xoshiro256PlusPlus`; or splittable generators | Creates distinct state regions for threads. |
| Many dynamically spawned tasks/threads | `L64X128MixRandom` or `L64X256MixRandom` | Belongs to the splittable group, suited for splitting generators per task. |
| Creating a very large number of instances | `L128X128MixRandom` or `L128X256MixRandom` | 128-bit LCG parameter reduces the chance of instances sharing the same state cycle. |
| Needing high equidistribution for long tuples | `L64X256MixRandom` or `L64X1024MixRandom` | Has level 4 or 16 per Java 17 docs. |
| Secret codes, tokens, security nonces | `SecureRandom` | API designed for cryptographically secure randomness requirements. |

These are directional recommendations, not benchmark results for every CPU or application. For performance-critical workloads, benchmark in the actual deployment environment and apply appropriate statistical test suites.

### 7.1. When to Use `Random`?

`Random` remains valid and useful for legacy code needing compatibility or simple examples. However, its LCG algorithm is the weakest among the PRNGs listed in Java 17's package. For new code without compatibility constraints, consider modern generators in `java.util.random`.

### 7.2. When to Use `ThreadLocalRandom`?

`ThreadLocalRandom.current()` provides a generator bound to the current thread, convenient for independent operations in multithreaded applications:

~~~java
import java.util.concurrent.ThreadLocalRandom;

int portSuffix = ThreadLocalRandom.current().nextInt(1000, 10000);
~~~

It reduces contention when multiple threads need to generate values simultaneously. It is unsuitable when you need to manage seeds to reproduce a specific simulation sequence; do not instantiate it with a constructor or attempt to set a seed manually.

### 7.3. When to Use `SplittableRandom`?

`SplittableRandom` is designed for splittable pseudo-random computations, such as parallel computation. It is not thread-safe; typically each task uses its own instance:

~~~java
import java.util.SplittableRandom;

SplittableRandom root = new SplittableRandom(2026L);

SplittableRandom workerA = root.split();
SplittableRandom workerB = root.split();

int sampleA = workerA.nextInt(1, 100);
int sampleB = workerB.nextInt(1, 100);
~~~

`split()` creates a new generator of the same type with split-off state for independent use. This is much more appropriate than sharing one mutable instance across multiple workers.

### 7.4. When to Use `SecureRandom`?

When generating password reset tokens, session keys, nonces, or data requiring unpredictability, use `SecureRandom`:

~~~java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
byte[] token = new byte[32];
secureRandom.nextBytes(token);
~~~

`SecureRandom` is a Java Security API and is also a `RandomGenerator` in Java 17. It uses platform providers and entropy sources. Do not replace it with `Random`, `SplittableRandom`, or an LXM algorithm just because they have large periods or high speed.

## 8. Example: Selecting an Algorithm by Properties

Suppose a simulation application wants a generator capable of splitting. We can filter factories and select an algorithm by an agreed-upon criterion:

~~~java
import java.util.Comparator;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public final class SelectGenerator {
    private SelectGenerator() {
    }

    public static void main(String[] args) {
        var selected = RandomGeneratorFactory.all()
                .filter(RandomGeneratorFactory::isSplittable)
                .filter(factory -> !factory.isDeprecated())
                .max(Comparator.comparingInt(
                        factory -> factory.stateBits()))
                .orElseThrow(() ->
                        new IllegalStateException(
                                "No splittable generator available"));

        System.out.println("Selected: " + selected.name());
        System.out.println("Group: " + selected.group());
        System.out.println("State bits: " + selected.stateBits());
        System.out.println("Period: " + selected.period());

        RandomGenerator random = selected.create(2026L);
        System.out.println("Sample: " + random.nextDouble());
    }
}
~~~

This example picks the factory with the most state bits among splittable factories. It is an **illustration of querying metadata**, not an optimal formula for every application. If a concrete design decision has already been made, an explicit algorithm name is easier to control than automatically picking the "largest".

`all()` already excludes deprecated algorithms per the API contract, so the `!factory.isDeprecated()` filter is a readable safeguard that typically does not alter the list.

## 9. Seed and Result Reproducibility

With a deterministic PRNG, the seed is the initial state or the data used to initialize state. When using the same algorithm, same seed, and same call sequence, you can reproduce the sequence of values in the same environment/implementation version.

~~~java
RandomGenerator first =
        RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(12345L);

RandomGenerator second =
        RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(12345L);

System.out.println(first.nextInt());
System.out.println(second.nextInt());
~~~

Two instances created with the same algorithm and seed will yield the same value on corresponding calls within a consistent implementation. When writing tests, fixed seeds help reproduce bug scenarios.

### 9.1. Record Enough Information to Reproduce

If simulation results need long-term reproducibility, record the algorithm name, seed, JDK version and execution environment, call sequence or stream/task splitting strategy, and simulation input parameters.

Do not save only the seed if the program uses `getDefault()`, because the default algorithm can change across versions. The factory API also does not promise that every algorithm/provider produces identical sequences across all JDKs.

### 9.2. A Seed Is Not a Password

Do not use fixed seeds or predictable seeds to generate security tokens. If an attacker knows the algorithm and seed, they can reproduce the deterministic PRNG sequence. For security purposes, use `SecureRandom` and let the provider handle entropy collection.

## 10. Generating Numbers in Ranges and Distributions

Choosing the algorithm is one decision; choosing the data **distribution** is another. `RandomGenerator` offers several methods:

| Method | Result |
|---|---|
| `nextInt()` | A pseudo-random `int` across the full range of the type. |
| `nextInt(bound)` | Integer from 0 (inclusive) to bound (exclusive). |
| `nextInt(origin, bound)` | Integer in `[origin, bound)`. |
| `nextDouble()` | Floating-point number from 0.0 to less than 1.0. |
| `nextDouble(origin, bound)` | Floating-point number in `[origin, bound)`. |
| `nextGaussian()` | Normally distributed value with mean 0, standard deviation 1. |
| `nextGaussian(mean, stddev)` | Normal distribution with specified mean and standard deviation. |
| `nextExponential()` | Exponentially distributed value with mean 1. |

To get an integer in a range, use the bounded overload instead of manual modulo:

~~~java
int safe = random.nextInt(10, 21); // 10 to 20
~~~

Avoid:

~~~java
int unsafe = Math.abs(random.nextInt()) % 11 + 10;
~~~

The modulo approach can produce a skewed distribution when the count of source values is not divisible by the range size; `Math.abs(Integer.MIN_VALUE)` also remains negative due to integer representation limits. Using the bounded API avoids both bugs.

If the problem requires a normal distribution, use `nextGaussian` or a sampling method suited to the target distribution.

## 11. Common Mistakes When Listing and Choosing Algorithms

| Mistake | Why Is It Wrong? | Proper Approach |
|---|---|---|
| Assuming the algorithm with the largest period is always best. | Period does not measure overall quality, speed, correlation, or security. | Evaluate workload, state, equidistribution, split/jump, and benchmarks together. |
| Using `Random` for all new applications. | `Random` uses an LCG and is noted in Java 17 docs as the weakest among the package's PRNGs. | Consider LXM or another suitable algorithm. |
| Using LXM/Xoshiro to generate security tokens. | Simulation PRNGs are not designed as CSPRNGs. | Use `SecureRandom`. |
| Using `getDefault()` while expecting the algorithm to stay fixed. | The default name can change as algorithms improve. | Specify an explicit name if reproducibility is needed. |
| Sharing a mutable generator across multiple threads. | Most `RandomGenerator`s are not thread-safe. | Give each thread/task its own instance; use split or jump when appropriate. |
| Using a time-based seed as a security seed. | Predictable seeds can make the PRNG sequence predictable. | Use `SecureRandom` for secrets. |
| Treating `stateBits` as the number of entropy bits. | It is internal state size, not guaranteed seed entropy. | Treat seed and state as distinct concepts. |
| Looking only at `isSplittable` and concluding streams are strictly independent. | Split helps create instances in different state regions; it does not replace computational and statistical evaluation. | Follow algorithm guidance, reasonable seeding, and verify results. |
| Using `nextInt() % bound` to get numbers in a range. | Can cause modulo bias and bugs with negative values. | Use `nextInt(origin, bound)` or `nextInt(bound)`. |

## 12. Practice Exercises

### Exercise 1 — Listing Generators

Write a program using `RandomGeneratorFactory.all()` to print the name and group of every available factory. Sort results by name and ignore deprecated factories.

### Exercise 2 — Reading Metadata

For each factory, print `stateBits()`, `period()`, and `equidistribution()`. Find the algorithm with the largest state bits and the one with the highest equidistribution. Explain why these two algorithms are not necessarily the fastest choices.

### Exercise 3 — Choosing a Splittable Generator

Filter the factory list by `isSplittable()`. Choose a specific algorithm name, create an instance with a fixed seed, and call `nextInt(1, 7)` ten times. Rerun the program to observe reproducibility.

### Exercise 4 — Splitting Streams for Two Workers

Use `SplittableRandom` with a fixed seed, call `split()` to create two generators for two tasks. Generate 5 numbers from each generator and store the results. Explain why two workers should not call the same instance concurrently.

### Exercise 5 — Distinguishing PRNG and CSPRNG

Write an example generating 32 bytes with `SecureRandom` and compare its intended use with `L64X128MixRandom`. State which example is suitable for simulation and which is suitable for security tokens.

### Self-Check Hints

- Exercise 1: Use `RandomGeneratorFactory.all().sorted((a, b) -> a.name().compareTo(b.name()))` and `forEach`.
- Exercise 2: `stateBits` measures state, `period` measures cycle length, `equidistribution` describes tuple distribution; none of these metrics is a speed benchmark.
- Exercise 3: Use `RandomGeneratorFactory.of("L64X128MixRandom").create(12345L)`.
- Exercise 4: Each worker uses its own split instance rather than sharing a single mutable object.
- Exercise 5: `SecureRandom` is for secrets; LXM is for simulations or workloads without cryptographic requirements.

## 13. Algorithm Selection Workflow in Real Projects

When starting a feature that needs pseudo-random number generation, follow this sequence:

1. **Identify security requirements.** If values are tokens, nonces, or secret data, choose `SecureRandom`.
2. **Identify workload pattern.** Single-threaded, batch-created multithreaded, or dynamically spawned tasks lead to different split/jump choices.
3. **Identify reproducibility needs.** If tests/simulations need replay, choose an explicit algorithm and seed; record the runtime version.
4. **List available factories.** Use `RandomGeneratorFactory.all()` to inspect actual names and properties.
5. **Filter by required characteristics.** Check `stateBits`, `period`, `equidistribution`, `isSplittable`, `isJumpable`, and related properties.
6. **Select a few candidates.** Use Java 17 documentation recommendations as a starting point, then benchmark on real workloads.
7. **Verify output distribution.** Choose `nextInt`, `nextDouble`, `nextGaussian`, or a sampling algorithm matching the model.
8. **Document the decision.** Save the algorithm name, seed, and configuration so others can reproduce results.

You do not need the most complex algorithm for a simple feature. A clear, workload-appropriate choice tested in the deployment environment is usually more valuable than picking solely by a single metadata number.

## 14. Key Takeaways

- Java 17 provides the `java.util.random` package and `RandomGenerator` interface to standardize pseudo-random value generation.
- `RandomGeneratorFactory.all()` lists available factories; `of(name)` looks up an algorithm; `create(seed)` creates an instance.
- You can inspect `name`, `group`, `stateBits`, `period`, `equidistribution`, and split/jump/leap/stream flags to understand algorithm properties.
- `getDefault()` selects a generator meeting at least 64 state bits; the default algorithm name can change across versions.
- LXM and Xoroshiro/Xoshiro are modern PRNG groups in Java SE 17; `Random`, `ThreadLocalRandom`, and `SplittableRandom` remain usable legacy choices.
- `SecureRandom` is for cryptographic security requirements; do not replace it with simulation PRNGs.
- Generators are generally not thread-safe. For parallel processing, consider per-worker instances, split, or jump.
- Use bounded overloads like `nextInt(origin, bound)` instead of manual modulo arithmetic.
- Period, state bits, and equidistribution describe different aspects; none is the sole measure of security or speed.

### References

- [Java SE 17 API — Package java.util.random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html).
- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html).
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html).
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html).
- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356).
