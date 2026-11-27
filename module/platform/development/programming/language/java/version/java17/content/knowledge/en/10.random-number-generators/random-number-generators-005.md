# LXM, Xoshiro, and Xoroshiro Algorithm Families in Java 17

**Topic:** Java 17 → Pseudo-Random Number Generation  
**Focus:** Understand how the LXM, Xoshiro, and Xoroshiro algorithm families provided by Java 17's pseudo-random number generation API are grouped; read algorithm names, compare state and period, choose the right split/jump mechanism, and use them through RandomGenerator.

Starting in Java 17, the JDK provides the common `RandomGenerator` API in the `java.util.random` package along with modern pseudo-random algorithms under JEP 356. The three families to know are **LXM**, **Xoroshiro**, and **Xoshiro**. These algorithms serve different requirements in speed, state memory, period, generation stream splitting, and statistical properties.

The examples in this lesson use standard Java SE 17 APIs without external libraries, incubator modules, or preview flags. One distinction to make from the start: **these algorithms are PRNGs (pseudorandom number generators), not cryptographic random number generators**. If you need to generate keys, tokens, nonces, or security data, use `SecureRandom`.

## 1. New Pseudo-Random Number Generation API in Java 17

Before Java 17, applications were often tied to a concrete class such as `java.util.Random`, `ThreadLocalRandom`, or `SplittableRandom`. Java 17 introduces the common `RandomGenerator` interface so consumer code can work with many algorithms without depending on the implementing class.

Key types:

| API | Role |
| --- | --- |
| `RandomGenerator` | Common interface for obtaining `int`, `long`, `float`, `double`, boolean, and streams of pseudo-random numbers. |
| `RandomGeneratorFactory` | Looks up, selects, and creates generators by algorithm name; provides metadata such as state bits, period, and split/jump capabilities. |
| `RandomGenerator.SplittableGenerator` | A generator that can create child generators via `split()`, suited for branching work or dynamically spawned tasks. |
| `RandomGenerator.JumpableGenerator` | A generator that can jump forward by a large step in its state cycle via `jump()`, suited for assigning sequence regions to a predetermined number of threads. |
| `RandomGenerator.LeapableGenerator` | Extends jumpable with the ability to leap a much larger distance. |
| `RandomGenerator.ArbitrarilyJumpableGenerator` | Supports jumping by a program-specified distance. |

Application code typically only needs to reference the `RandomGenerator` type:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorIntro {
    public static void main(String[] args) {
        RandomGenerator random =
            RandomGeneratorFactory.of("L64X128MixRandom").create(2025L);

        int die = random.nextInt(1, 7); // 1 to 6; upper bound excluded.
        double sample = random.nextDouble();

        System.out.println("Die: " + die);
        System.out.println("Sample: " + sample);
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 RandomGeneratorIntro.java
java RandomGeneratorIntro
~~~

`RandomGeneratorFactory.of(name)` locates the factory with the matching name. `create(2025L)` creates a generator with the specified seed; the same algorithm and same seed yield a deterministic result sequence within the same algorithm implementation. For repeatable tests or simulations, specify the algorithm name and seed explicitly rather than relying on a default algorithm that may change across versions.

## 2. Standard Algorithm List in Java SE 17

Java SE 17 requires the following algorithms to be present. A specific JDK or provider may supply additional algorithms; therefore, the runtime list discovered via `RandomGeneratorFactory.all()` may be broader than this table.

### 2.1. LXM Group

| Algorithm Name | State bits | Period |
| --- | ---: | --- |
| `L32X64MixRandom` | 96 | \(2^{32}(2^{64}-1)\) |
| `L64X128MixRandom` | 192 | \(2^{64}(2^{128}-1)\) |
| `L64X128StarStarRandom` | 192 | \(2^{64}(2^{128}-1)\) |
| `L64X256MixRandom` | 320 | \(2^{64}(2^{256}-1)\) |
| `L64X1024MixRandom` | 1088 | \(2^{64}(2^{1024}-1)\) |
| `L128X128MixRandom` | 256 | \(2^{128}(2^{128}-1)\) |
| `L128X256MixRandom` | 384 | \(2^{128}(2^{256}-1)\) |
| `L128X1024MixRandom` | 1152 | \(2^{128}(2^{1024}-1)\) |

### 2.2. Xoroshiro/Xoshiro Group

| Algorithm Name | State bits | Period |
| --- | ---: | --- |
| `Xoroshiro128PlusPlus` | 128 | \(2^{128}-1\) |
| `Xoshiro256PlusPlus` | 256 | \(2^{256}-1\) |

This is the list of algorithms required by Java SE 17. Do not automatically assume an algorithm name found in an article about another library or another Java version is a standard Java 17 name. Check the JDK in use or query factories through the API.

## 3. LXM Family: Combining LCG, XBG, and Mixer

The name **LXM** stands for three components:

- **L — Linear Congruential Generator (LCG):** a linear congruential generator.
- **X — Xor-Based Generator (XBG):** a generator based on XOR, bit-shift, and bit-rotate operations.
- **M — Mixer:** a mixing function combining the output states of both generators into the result.

Instead of relying on a single generator, LXM combines an LCG and an XBG. Each time a result is produced, the algorithm combines the states of both components through the mixer, then updates the states of both.

### 3.1. LCG Inside LXM

An LCG update step has the general form:

\[
s' = m \times s + a \pmod {2^p}
\]

Where:

- `s` is the current state.
- `m` is the fixed multiplier of the algorithm.
- `a` is the additive parameter of the generator instance.
- `p` is the number of LCG state bits, indicated by the `L` part of the algorithm name.

LXM chooses parameters so that the LCG has a long period. The LCG component provides one state sequence with its own characteristics, while the XBG supplies another sequence for the mixer to combine.

### 3.2. XBG Inside LXM

An XBG is a generator based on bit operations. In Java 17's LXM algorithms, the XBG may use the `xoroshiro64`, `xoroshiro128`, `xoshiro256`, or `xoroshiro1024` families depending on configuration.

The number of XBG state bits is the `X` part of the name:

- `L32X64MixRandom`: 32-bit LCG, 64-bit XBG.
- `L64X128MixRandom`: 64-bit LCG, 128-bit XBG.
- `L64X256MixRandom`: 64-bit LCG, 256-bit XBG.
- `L64X1024MixRandom`: 64-bit LCG, 1024-bit XBG.
- `L128X256MixRandom`: 128-bit LCG, 256-bit XBG.

Thus, total `stateBits()` usually equals the sum of LCG and XBG state bits. This is algorithmic state memory, not the exact Java object size on the heap.

### 3.3. Reading the Mix and StarStar Suffixes

In LXM names:

- `Mix` denotes variants using a stronger mixing function with good avalanche properties.
- `StarStar` denotes variants using a shorter, faster scrambler that mixes less thoroughly than `Mix` variants.

For example, `L64X128MixRandom` and `L64X128StarStarRandom` have the same state bits and the same period, but use different output processing functions. Do not infer that two algorithms produce the same number sequence merely because the `L64X128` prefix matches.

### 3.4. Period of LXM

If the LCG has period \(2^p\) and the XBG has period \(2^q-1\), these two periods are coprime. The period of LXM is their product:

\[
P = 2^p(2^q-1)
\]

For example:

\[
P_{\text{L64X128}} = 2^{64}(2^{128}-1)
\]

A long period means the state sequence takes an enormous number of steps before repeating. However, **a long period does not imply cryptographic security**, nor does it guarantee that every application uses the generator properly.

### 3.5. Statistical Properties

The LXM algorithms in JDK 17 are designed for strong output distribution. Some configurations have *k-equidistribution* properties for groups of consecutive values:

| Algorithm | Documented `nextLong()` Property |
| --- | --- |
| `L64X128MixRandom` | 2-equidistributed |
| `L64X256MixRandom` | 4-equidistributed |
| `L64X1024MixRandom` | 16-equidistributed |

Broadly speaking, k-equidistribution describes the uniformity of tuples of k consecutive values across the period. This is a useful statistical property for certain simulations and tuple processing; it is not the sole criterion for picking a generator.

## 4. Xoroshiro and Xoshiro Families

Xoroshiro and Xoshiro are established bit-manipulation-based PRNG families that typically combine:

- XOR between parts of state.
- Left or right *shifts*.
- Bit *rotations*.
- A *scrambler/output function*.

The names hint at combining XOR, shift, and rotate. The number in the algorithm name indicates the state size:

- `Xoroshiro128PlusPlus`: 128-bit state.
- `Xoshiro256PlusPlus`: 256-bit state.

In Java SE 17, these two algorithms are provided in the `PlusPlus` variant. The `PlusPlus` part is the name of the output function variant, not an increment operator in Java code and not a Java version number.

### 4.1. Xoroshiro128PlusPlus

`Xoroshiro128PlusPlus` uses a 128-bit state and has period \(2^{128}-1\). It has a small state size, suited when a compact and fast generator is needed, such as in single-threaded applications.

### 4.2. Xoshiro256PlusPlus

`Xoshiro256PlusPlus` uses a 256-bit state and has period \(2^{256}-1\). It has a larger state, longer period, and also supports the jump mechanism to create distinct starting points in the period.

### 4.3. Comparing the Two Families

| Feature | Xoroshiro128PlusPlus | Xoshiro256PlusPlus |
| --- | --- | --- |
| State bits | 128 | 256 |
| Period | \(2^{128}-1\) | \(2^{256}-1\) |
| Stream partitioning mechanism | `JumpableGenerator` | `JumpableGenerator` |
| Typical advantages | Small state, high speed | Larger state and period |
| Choose when | Single thread or few threads, small footprint needed | Many jumped streams or larger period needed |

Do not choose solely by the number of state bits. Consider how many generators are created, how many values each generator will produce, statistical requirements, and the parallel processing model.

## 5. Comparing the Three Algorithm Families

| Criterion | LXM | Xoroshiro | Xoshiro |
| --- | --- | --- | --- |
| Structure | Combines LCG + XBG + mixer | XOR/shift/rotate generator | XOR/shift/rotate generator |
| Standard Java 17 variants | Multiple `L...X...MixRandom` configs and one `StarStar` config | `Xoroshiro128PlusPlus` | `Xoshiro256PlusPlus` |
| State | 96 to 1152 bits in standard list | 128 bits | 256 bits |
| Stream creation mechanism | Standard LXMs implement `SplittableGenerator` | `JumpableGenerator` | `JumpableGenerator` |
| Notable traits | Balances quality, period, split, and state size | Compact, fast, jump-capable | Larger state and period, jump-capable |
| Selection example | `L64X128MixRandom` for general needs | `Xoroshiro128PlusPlus` when small state is needed | `Xoshiro256PlusPlus` when a larger period is needed |

LXM still uses an XBG derived from the xoroshiro/xoshiro families internally. Thus, these three groups are not completely unrelated approaches; the difference is that **LXM combines an LCG with an XBG and a mixer**, whereas Xoroshiro/Xoshiro directly use an XOR-based generator with its output variant.

## 6. Selecting a Generator via RandomGeneratorFactory

`RandomGeneratorFactory` is a flexible way to choose an algorithm by name and inspect its properties.

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class ListRandomAlgorithms {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
            .sorted((a, b) -> a.name().compareTo(b.name()))
            .forEach(factory -> System.out.printf(
                "%-26s group=%-12s state=%4d period=%s split=%s jump=%s%n",
                factory.name(),
                factory.group(),
                factory.stateBits(),
                factory.period(),
                factory.isSplittable(),
                factory.isJumpable()
            ));
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 ListRandomAlgorithms.java
java ListRandomAlgorithms
~~~

Results depend on the implementations/providers present in the running JDK. The output above may also include legacy generators like `Random`, `SplittableRandom`, and `ThreadLocalRandom`, alongside the new algorithms. Do not hardcode assumptions that every JDK or provider has only the exact ten names from the standard algorithm list.

### 6.1. Important Factory Properties

| Method | Meaning |
| --- | --- |
| `name()` | Algorithm name. |
| `group()` | Algorithm group, e.g. `LXM`, `Xoroshiro`, `Xoshiro`, or `Legacy`. |
| `stateBits()` | Number of state bits used by the algorithm. |
| `period()` | Period, returned as `BigInteger`; may be `BigInteger.ZERO` if undetermined. |
| `equidistribution()` | Documented equidistribution dimension. |
| `isSplittable()` | Whether the generator supports splitting. |
| `isJumpable()` | Whether the generator supports jumping. |
| `isLeapable()` | Whether the generator supports leaping. |
| `isArbitrarilyJumpable()` | Whether the generator can jump by arbitrary distances. |
| `isDeprecated()` | Whether the algorithm is marked deprecated. |

These properties are useful when writing libraries that select a generator by capability rather than solely by name.

## 7. Creating an LXM Generator with an Explicit Seed

Example using `L64X128MixRandom`:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class LxmDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
            RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator random = factory.create(123456789L);

        System.out.println(random.nextLong());
        System.out.println(random.nextInt(100));
        System.out.println(random.nextDouble(10.0, 20.0));
    }
}
~~~

`create(seed)` lets you specify an explicit seed. This is useful for:

- Reproducible testing.
- Scientific simulations requiring recorded input configuration.
- Debugging a sequence of behaviors dependent on random numbers.
- Comparing algorithms in a benchmark under consistent conditions.

If you want a self-initialized seed, you can call the no-argument `create()`. For experiments requiring reproducibility, save the algorithm name, seed, runtime version, and simulation configuration. Do not rely on `RandomGeneratorFactory.getDefault()` for a long-term data format because the default algorithm may change over time.

## 8. Using Split with LXM

Java 17's standard LXMs implement `RandomGenerator.SplittableGenerator`. The `split()` method creates a new generator split off from the current generator. This pattern suits dynamically branching tasks, such as a task splitting into two subtasks.

~~~java
import java.util.random.RandomGenerator;

public class SplitDemo {
    public static void main(String[] args) {
        RandomGenerator.SplittableGenerator parent =
            RandomGenerator.SplittableGenerator.of("L64X128MixRandom");

        RandomGenerator.SplittableGenerator child = parent.split();

        System.out.println("Parent: " + parent.nextLong());
        System.out.println("Child:  " + child.nextLong());
    }
}
~~~

Each generator should be exclusively owned by a single processing thread. Do not share a normal PRNG instance across multiple threads and call it concurrently if the implementation does not guarantee thread safety.

### 8.1. Example Splitting Generators for Subtasks

~~~java
import java.util.random.RandomGenerator;
import java.util.stream.IntStream;

public class SplitTasksDemo {
    public static void main(String[] args) {
        RandomGenerator.SplittableGenerator root =
            RandomGenerator.SplittableGenerator.of("L64X128MixRandom");

        IntStream.range(0, 4).forEach(task -> {
            RandomGenerator.SplittableGenerator child = root.split();
            System.out.println(
                "Task " + task + ": " + child.nextLong()
            );
        });
    }
}
~~~

This example creates a separate child generator for each task. When used in a real parallel application, pass each child generator to its corresponding task and ensure one generator is never used concurrently by multiple threads.

Statistical independence between child generators is a design goal; the API documentation frames it in terms of statistical expectation or approximation, not an absolute mathematical promise that all sequences are completely independent.

## 9. Using Jump with Xoroshiro and Xoshiro

`Xoroshiro128PlusPlus` and `Xoshiro256PlusPlus` in Java 17 implement `RandomGenerator.JumpableGenerator`. The `jump()` method advances the generator's state forward by a large, fixed distance in the period.

Unlike `split()`, jump does not build a generator tree by deriving bits from a parent; it distributes starting points far apart along the period of the same algorithm.

~~~java
import java.util.random.RandomGenerator;

public class JumpDemo {
    public static void main(String[] args) {
        RandomGenerator.JumpableGenerator source =
            RandomGenerator.JumpableGenerator.of("Xoshiro256PlusPlus");

        // Take a copy at the current position, then advance source.
        RandomGenerator first = source.copyAndJump();

        // Take a copy at the new position, then advance source again.
        RandomGenerator second = source.copyAndJump();

        System.out.println("First stream:  " + first.nextLong());
        System.out.println("Second stream: " + second.nextLong());
    }
}
~~~

`copyAndJump()` copies the current state, jumps the original generator forward, and returns the copy in the pre-jump state. Repeated calls on the same source generator create starting points separated by the implementation's jump distance.

Do not assume a specific jump distance is always \(2^{64}\) or \(2^{128}\) for every algorithm. Read `jumpDistance()` and the implementation documentation if that distance is an important part of the design.

### 9.1. When to Split, When to Jump?

| Scenario | Suitable Mechanism |
| --- | --- |
| A single-threaded generation task | One `RandomGenerator` is enough. |
| Branching tasks or dynamically spawned workers | Use `SplittableGenerator.split()` if supported by the algorithm. |
| A known large number of threads needing widely separated sequence segments | Use `JumpableGenerator` and jump/jumps operations if supported by the algorithm. |
| Choosing a generator across multiple implementations | Check `isSplittable()` or `isJumpable()` before casting. |

Split and jump are different protocols. Do not cast an arbitrary generator to `SplittableGenerator` or `JumpableGenerator` without confirming it implements that interface.

## 10. Checking Capabilities Before Casting

Not every `RandomGenerator` supports split or jump. You can check via the factory:

~~~java
import java.util.random.RandomGeneratorFactory;

public class GeneratorCapabilities {
    public static void main(String[] args) {
        var lxm = RandomGeneratorFactory.of("L64X128MixRandom");
        var xoshiro = RandomGeneratorFactory.of("Xoshiro256PlusPlus");

        System.out.println(lxm.name());
        System.out.println("Splittable: " + lxm.isSplittable());
        System.out.println("Jumpable:   " + lxm.isJumpable());

        System.out.println(xoshiro.name());
        System.out.println("Splittable: " + xoshiro.isSplittable());
        System.out.println("Jumpable:   " + xoshiro.isJumpable());
    }
}
~~~

Among Java 17's standard algorithms, LXM is the splittable group; `Xoroshiro128PlusPlus` and `Xoshiro256PlusPlus` are the jumpable choices. If using additional providers, inspect actual properties rather than inferring from names.

## 11. Choosing an Algorithm by Problem

The Java SE 17 documentation offers several practical guidelines:

| Need | Candidates to Consider | Reason |
| --- | --- | --- |
| General-purpose application, no special requirements | `L64X128MixRandom` | Good balance of speed, state memory, and period. |
| Single thread, wanting a small and fast generator | `Xoroshiro128PlusPlus` | 128-bit state, period long enough for many applications. |
| 32-bit hardware environment, one or few threads | `L32X64MixRandom` | Smaller state than larger LXM configurations. |
| Spawning a predetermined number of threads | `Xoroshiro128PlusPlus` or `Xoshiro256PlusPlus` with jump; or LXM with split | Provides mechanisms to create separate starting points/generators. |
| Spawning dynamic tasks, e.g. fork/join | `L64X128MixRandom` or `L64X256MixRandom` | Supports recursive splitting. |
| Extremely large number of dynamic generators | `L128X128MixRandom` or `L128X256MixRandom` | 128-bit LCG parameter reduces the chance of instances sharing the same state cycle. |
| Needing consecutive tuples with strong distribution | Look at `L64X256MixRandom` or `L64X1024MixRandom` | Has documented 4- or 16-equidistribution guarantees. |
| Need to generate security keys, tokens, or nonces | `java.security.SecureRandom` | Requires a cryptographically secure pseudo-random number generator. |

These are selection guidelines based on algorithm properties, not performance rankings for every CPU or workload. If performance is decisive, benchmark with real data and usage patterns.

## 12. Long Period Does Not Mean Security

LXM, Xoroshiro, and Xoshiro algorithms are PRNGs with deterministic state. Once state and algorithm are known, the output sequence can be predicted. They are designed for simulations, games, computations, and statistical tasks, **not for protecting secrets**.

For example, do not use:

~~~java
RandomGenerator tokenGenerator =
    RandomGeneratorFactory.of("L64X128MixRandom").create();

String resetToken = Long.toHexString(tokenGenerator.nextLong());
~~~

to generate password reset tokens or verification codes. Use `SecureRandom`:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();
        byte[] tokenBytes = new byte[32];
        secureRandom.nextBytes(tokenBytes);

        String token = HexFormat.of().formatHex(tokenBytes);
        System.out.println(token);
    }
}
~~~

`SecureRandom` is the choice for security purposes; do not equate it with LXM/Xoroshiro/Xoshiro algorithms simply because all of them produce values that look random.

## 13. Thread Safety and Parallel Usage

Most `RandomGenerator` implementations are not thread-safe. If multiple threads call the same instance concurrently, results and performance may be unexpected; some implementations may have their own synchronization, but do not assume that.

Principles:

1. Each independent thread or task should own its own generator.
2. If supported by the algorithm, create child generators via split or starting points via jump.
3. Do not use the same generator in both the parent thread and child threads.
4. Do not treat different seeds as an absolute guarantee of independent sequences; use mechanisms designed for stream splitting.
5. With parallel streams or fork/join, carefully design how generators are passed and owned by each task.

The `RandomGenerator.StreamableGenerator` API also provides `rngs()` to create a stream of generators. `SplittableGenerator` has `splits()` to create a stream of child generators; `JumpableGenerator` has `jumps()` to create a stream of generators from jump points. These APIs help model generator distribution, though thread ownership and lifecycle must still be designed clearly.

## 14. Common Mistakes

| Mistake | Why You Should Not | Proper Approach |
| --- | --- | --- |
| Choosing a generator because its name sounds modern | The name does not tell the full state, period, or split/jump capabilities. | Inspect `group()`, `stateBits()`, `period()`, and capabilities. |
| Thinking LXM is just a variant of Xoshiro | LXM combines an LCG, an XBG, and a mixer. | Understand the hybrid structure before comparing. |
| Thinking `L64X128` has 128 total state bits | The L and X parts represent two separate components. | Total state bits equal 64 + 128 = 192 bits. |
| Thinking `MixRandom` and `StarStarRandom` produce the same sequence | They use different output processing functions. | Choose the exact algorithm name and seed when reproducibility is needed. |
| Casting every generator to `SplittableGenerator` | Not every implementation supports splitting. | Check `isSplittable()` or use appropriately typed APIs. |
| Sharing one generator across all threads | Most implementations are not thread-safe. | Each task uses its own split/jumped generator. |
| Using the default seed for tests requiring reproducibility | Self-initialized seeds cause sequences to vary between runs. | Specify the seed and algorithm name explicitly. |
| Using `getDefault()` as part of a long-term storage protocol | The default algorithm may change over time. | Choose an explicit algorithm and manage versions. |
| Using LXM/Xoshiro/Xoroshiro to generate secrets | They are not designed for cryptographic security. | Use `SecureRandom`. |
| Thinking a large period guarantees generating every permutation | Seed count and period both constrain the set of possible sequences. | Compare period, seed count, and the problem's result space. |

## 15. Comprehensive Example: Selecting an Algorithm, Inspecting Metadata, and Generating Values

File **`PrngFamiliesDemo.java`**:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class PrngFamiliesDemo {
    private static void show(String algorithm, long seed) {
        RandomGeneratorFactory<RandomGenerator> factory =
            RandomGeneratorFactory.of(algorithm);

        RandomGenerator random = factory.create(seed);

        System.out.printf(
            "%s | group=%s | state=%d | period=%s | split=%s | jump=%s%n",
            factory.name(),
            factory.group(),
            factory.stateBits(),
            factory.period(),
            factory.isSplittable(),
            factory.isJumpable()
        );

        System.out.println("  nextLong = " + random.nextLong());
        System.out.println("  nextInt  = " + random.nextInt(1, 7));
    }

    public static void main(String[] args) {
        show("L64X128MixRandom", 2025L);
        show("Xoroshiro128PlusPlus", 2025L);
        show("Xoshiro256PlusPlus", 2025L);
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 PrngFamiliesDemo.java
java PrngFamiliesDemo
~~~

This example shows that the same `RandomGenerator` interface can be used across all three algorithm groups. Factory metadata indicates which group the generator belongs to, how many state bits it uses, its period, and whether it supports split/jump. The specific numbers generated depend on the algorithm and seed; the key takeaway is how an application selects and uses generators through the common API.

## 16. Frequently Asked Questions

**What does LXM stand for?**  
LXM stands for LCG + XBG + Mixer: a linear congruential generator combined with an XOR-based generator, whose states are mixed to produce output.

**What does the L64X128 part in L64X128MixRandom mean?**  
The LCG has 64 state bits and the XBG has 128 state bits; total state bits are 192 bits.

**How do MixRandom and StarStarRandom differ?**  
They use different output mixer/scrambler variants. According to Java SE 17 docs, Mix uses a stronger mixer, whereas StarStar uses a shorter and faster scrambler.

**Can Xoshiro and Xoroshiro split?**  
Java 17's two standard algorithms `Xoroshiro128PlusPlus` and `Xoshiro256PlusPlus` are jumpable. Use `jump()`/`jumps()` to distribute starting points; LXM is the splittable group and uses `split()`/`splits()`.

**Can one algorithm be used for every application?**  
There is no optimal choice for everything. `L64X128MixRandom` is a balanced starting point for general needs; parallel workloads, small state, huge generator counts, or specialized statistical requirements may call for other choices.

**Does a seed turn a PRNG into a true random number generator?**  
No. A seed initializes the state of a deterministic algorithm. A PRNG remains pseudo-random; fixed seeds are useful for reproducing results.

**Can these families be used for passwords or tokens?**  
No. Use `SecureRandom` for data requiring cryptographic security.

## 17. Official References

- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): design of the `RandomGenerator` API, factories, and algorithms added in Java 17.
- [Java SE 17 API — Package java.util.random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): algorithm list, LXM/Xoroshiro/Xoshiro groups, properties, and selection guidance.
- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): common interface for generators.
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): looking up algorithms, creating generators, and inspecting metadata.
- [Java SE 17 API — RandomGenerator.SplittableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.SplittableGenerator.html): `split()` and `splits()`.
- [Java SE 17 API — RandomGenerator.JumpableGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.JumpableGenerator.html): `jump()`, `copyAndJump()`, and `jumps()`.
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): pseudo-random generator for security purposes.

**Selection rule:** Use `RandomGenerator` as the common interface type; choose LXM when splitting and general balance are needed; consider Xoroshiro/Xoshiro when a jumpable generator with compact state or larger period is needed; and use `SecureRandom` when the requirement is cryptographic security.
