# RandomGenerator and RandomGeneratorFactory Since Java 17

## 1. Why did Java 17 add a new random number API?

Before Java 17, many programs relied on `java.util.Random`, `ThreadLocalRandom`, `SplittableRandom`, or `SecureRandom`. Each choice had its strengths, yet swapping algorithms and querying generator characteristics lacked a unified API. **Java 17 introduced `java.util.random.RandomGenerator` and `RandomGeneratorFactory`** as a common interface and algorithm selection mechanism in `java.base` (JEP 356).

This lesson focuses on two components:

- **`RandomGenerator`**: the common interface for **using** a random number generator, typically *pseudorandom*.
- **`RandomGeneratorFactory<T extends RandomGenerator>`**: the factory for **discovering, selecting, inspecting properties, and creating** instances of a specific algorithm.

The two roles complement each other: business code should depend on `RandomGenerator` when it only needs to draw numbers; configuration, initialization, or algorithm-selection code deals with `RandomGeneratorFactory`.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");
RandomGenerator rng = factory.create();

int die = rng.nextInt(1, 7); // 1, 2, 3, 4, 5, or 6
```

This is an **illustrative snippet** meant to go inside a Java method or class, not a standalone program. A complete example with `javac`/`java` commands appears in section 7.

### What does pseudorandom mean?

A pseudorandom algorithm produces a sequence of results from **internal state**. Each call like `nextInt()` typically advances the generator to its next state. The sequence is designed to have useful statistical properties, but in principle is determined by the algorithm and initial state/seed.

Therefore, “random” here **does not mean cryptographically secure randomness**. Predictable seeds or algorithms lacking resistance to prediction are unsuitable for login tokens, keys, OTP codes, or session secrets. For security requirements, use `java.security.SecureRandom` and dedicated security design; `SecureRandom` also implements `RandomGenerator` in Java 17, yet cannot be replaced by any fast PRNG.

## 2. Distinguishing interface, factory, and algorithm

`RandomGenerator` is an **interface**, so you cannot write `new RandomGenerator()`. It provides methods such as `nextInt()`, `nextLong()`, `nextDouble()`, and streams for applications to consume results.

`RandomGeneratorFactory` is a **generic factory class**, where each factory corresponds to a specific algorithm. For example, `RandomGeneratorFactory.of("L64X128MixRandom")` looks up the factory for the chosen algorithm name; `factory.create()` creates an instance to use.

```text
Algorithm name ──→ RandomGeneratorFactory ──create()──→ RandomGenerator
                    │                         │
                    │ name(), stateBits()     └── nextInt(), nextDouble(), ...
                    │ period(), isSplittable()
                    └── algorithm info and capabilities
```

Options for creating a generator:

| Creation method | Effect | When to use |
| --- | --- | --- |
| `RandomGenerator.getDefault()` | Creates a generator with the runtime's default algorithm. | No specific requirement on algorithm identity. |
| `RandomGenerator.of("L64X128MixRandom")` | Creates a generator by algorithm name. | Want a named algorithm without managing a factory. |
| `RandomGeneratorFactory.getDefault().create()` | Gets the default factory and creates a generator. | Need additional factory metadata or want to create multiple instances. |
| `RandomGeneratorFactory.of(name).create()` | Creates a generator from the selected algorithm. | Initialization configurable by algorithm name. |
| `RandomGeneratorFactory.of(name).create(seed)` | Requests creating a generator from a `long` seed. | Experiments, reproducible results, and tests with a fixed algorithm. |
| `RandomGeneratorFactory.all()` | Streams available factories, excluding algorithms marked deprecated. | Discovering/filtering algorithms by capability and metadata. |

**Do not assume the default algorithm is invariant across JDKs or versions.** The `getDefault()` specification allows the chosen algorithm to change over time. If you need to reproduce a sequence from a specific algorithm, specify the **algorithm name**, control the seed, and fix the call order.

With `RandomGeneratorFactory.of(name)`, a nonexistent name throws `IllegalArgumentException`; do not assume every algorithm present in one runtime exists in yours.

## 3. Obtaining and using generators in Java 17

### 3.1. Default choice

```java
RandomGenerator rng = RandomGenerator.getDefault();

int anyInt = rng.nextInt();
long anyLong = rng.nextLong();
double unit = rng.nextDouble(); // [0.0, 1.0)
boolean flag = rng.nextBoolean();
```

These calls provide primitive types. `nextInt()` without range arguments can produce any `int` value; `nextDouble()` produces a non-negative value strictly less than 1.0. Actual values **change with generator state**. Do not hardcode a specific stdout sequence for a generator without a controlled seed.

### 3.2. Selecting an algorithm by name

```java
RandomGenerator rng = RandomGenerator.of("L64X128MixRandom");
System.out.println(rng.nextInt(100)); // an integer from 0 to 99
```

`L64X128MixRandom` is an algorithm belonging to the **LXM** family introduced in Java 17. The algorithm name is a technical configuration identifier and should not be confused with an implementation class name that might change or the identity of a single instance.

### 3.3. Factory and seed

```java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator first = factory.create(12345L);
RandomGenerator second = factory.create(12345L);

boolean sameSequence = true;
for (int i = 0; i < 10; i++) {
    sameSequence &= first.nextInt() == second.nextInt();
}
System.out.println(sameSequence); // true
```

For **the same algorithm supporting `long` seeds**, the same seed, and the same **call sequence**, two generators start from the same state and yield matching corresponding values. This is useful when reproducing a simulation or test failure.

Understand the factory's limitations: the API has three overloads `create()`, `create(long seed)`, and `create(byte[] seed)`. The specification permits `create(long)` to **fall back to behavior equivalent to `create()` if the algorithm does not support `long` seeds**; the `byte[]` overload also has its own support conditions. Thus, for reliable reproducibility, pick an algorithm verified to support your chosen seed type rather than assuming all providers behave alike.

## 4. Number ranges, data types, and streams

A key strength of the common interface is a consistent API across numeric types and distributions:

| Call | Result range / meaning |
| --- | --- |
| `rng.nextInt()` | `int` value drawn from the entire `int` value range. |
| `rng.nextInt(10)` | Integer from **0 to 9**; upper bound 10 is **not** in range. |
| `rng.nextInt(5, 10)` | Integer from **5 to 9**, i.e., `[5, 10)`. |
| `rng.nextLong(100L, 200L)` | `long` value in `[100, 200)`. |
| `rng.nextDouble()` | `double` value in `[0.0, 1.0)`. |
| `rng.nextDouble(2.0, 5.0)` | `double` value in `[2.0, 5.0)`. |
| `rng.nextBoolean()` | Boolean value `true` or `false`. |
| `rng.nextGaussian()` | Normally distributed value with mean 0 and standard deviation 1. |
| `rng.nextExponential()` | Non-negative exponentially distributed value with mean 1. |
| `rng.ints(5, 1, 7)` | `IntStream` **of 5 values**, each in `[1, 7)`. |
| `rng.longs(...)`, `rng.doubles(...)` | Stream variants for `long` and `double`. |

**Left bound inclusive, right bound exclusive** for overloads taking `origin` and `bound`. This design is convenient: simulate a six-sided die with `nextInt(1, 7)`, rather than `nextInt(1, 6)` where face 6 would never appear.

```java
int die = rng.nextInt(1, 7);
int zeroToNine = rng.nextInt(10);

int[] fiveDice = rng.ints(5, 1, 7).toArray();
double[] tenFractions = rng.doubles(10).toArray();
```

Stream overloads accepting `streamSize` have a finite number of elements. Overloads without a size argument create effectively unlimited streams that must be bounded via `limit(n)` or a short-circuiting operation. **Never collect an unbounded stream into a list or array.**

Invalid arguments can throw `IllegalArgumentException`: `rng.nextInt(0)` has a non-positive bound; `rng.nextInt(10, 10)` has an origin not less than bound; `rng.ints(-1)` has a negative element count. Validate inputs before calling.

Numbers produced by `nextDouble()` are not exact decimal numbers for accounting; multiplying by 100 and converting to `BigDecimal` does not turn it into an auditable or financially safe random source.

## 5. RandomGeneratorFactory: discovering and evaluating algorithms

The factory provides metadata to help choose an algorithm based on **usage requirements**.

```java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

System.out.println(factory.name());       // L64X128MixRandom
System.out.println(factory.isSplittable()); // true
```

Important metadata methods:

| Method | Meaning |
| --- | --- |
| `name()` | Identifying name of the algorithm created by the factory. |
| `group()` | Algorithm group, such as LXM or Legacy. |
| `stateBits()` | Number of bits representing the algorithm's state; **not synonymous with seed entropy bits**. |
| `period()` | Algorithm period as a `BigInteger`; returns `BigInteger.ZERO` if indeterminate. |
| `equidistribution()` | Information on the algorithm's `k`-equidistribution level. |
| `isSplittable()` | Whether it supports creating new generators via `split`. |
| `isJumpable()` | Whether it supports long jumps within its period. |
| `isLeapable()` | Whether it supports very large leaps. |
| `isArbitrarilyJumpable()` | Whether it supports arbitrary jump distances. |
| `isStreamable()` | Whether it supports streaming new **generators** through the specialized interface. |
| `isDeprecated()` | Whether the algorithm has been marked as deprecated. |
| `isStatistical()`, `isStochastic()`, `isHardware()` | Properties classifying the source or generation method. |

**Metadata is not a comprehensive quality score.** A long `period` or large `stateBits()` does not prove cryptographic security, suitability for every simulation, or absolute independence across seeds.

### Filtering factories instead of guessing algorithm names

Example selecting a non-deprecated factory that supports splitting and has at least 128 state bits:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

RandomGeneratorFactory<RandomGenerator> chosen = RandomGeneratorFactory.all()
        .filter(f -> !f.isDeprecated())
        .filter(RandomGeneratorFactory::isSplittable)
        .filter(f -> f.stateBits() >= 128)
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "No suitable algorithm found"));

System.out.println(chosen.name());
RandomGenerator generator = chosen.create();
```

This is a **snippet inside a method body**, not a standalone program. `all()` already excludes deprecated algorithms under the Java 17 specification, so `!f.isDeprecated()` here simply makes the requirement explicit. There is no guarantee which algorithm gets picked: the list of available algorithms can vary across JDKs/providers, and stream order should not be relied upon to lock in a long-term choice.

If **result reproducibility** matters, store the **algorithm name + seed + required version/parameters + API call schedule**. Do not filter and call `findFirst()` on every run while assuming the selection stays the same.

### Default factory

`RandomGeneratorFactory.getDefault()` returns the factory of an algorithm satisfying at least **`stateBits() >= 64`**, without guaranteeing the algorithm name stays identical across versions. `RandomGenerator.getDefault()` has the same intent at the instance level. Do not hardcode stdout values from the default generator.

## 6. Algorithm groups and practical selection

Java 17 describes the main groups:

- **Legacy**: long-standing generators such as `Random`, `ThreadLocalRandom`, `SplittableRandom`, and `SecureRandom` in the Java ecosystem. Some remain appropriate for compatibility or specialized cases.
- **LXM**: combines *linear congruential generator* and *xor-based generator* ideas, with variants such as `L64X128MixRandom` and `L64X256MixRandom`. Suitable for many simulation workloads and supports splitting in corresponding variants.
- **Xoroshiro/Xoshiro**: includes algorithms like `Xoroshiro128PlusPlus` and `Xoshiro256PlusPlus`, providing performance characteristics and jumping support in corresponding Java 17 implementations.

Choosing by problem:

| Need | Selection approach |
| --- | --- |
| General code with no algorithm constraints | `RandomGenerator.getDefault()` or default factory. |
| Simulations needing sequence replay | Fixed algorithm name + fixed seed + controlled call order. |
| Multiple parallel tasks needing dedicated generators | Algorithm supporting `SplittableGenerator` or `JumpableGenerator`; design generator allocation per worker/task. |
| Compatibility with legacy `java.util.Random` sequences | Keep `Random`/compatible algorithm, test critical cases. |
| Security-sensitive tokens, verification codes, keys, nonces | `SecureRandom`; do not pick LXM/Xoshiro just for speed or large period. |

In most numerical exercises, start with the `RandomGenerator` interface, and add requirements for seeds, algorithms, and splitting only if the problem truly needs them. A complex algorithm does not automatically make software “more random” in every sense.

## 7. Complete Java 17+ program and verifiable output

Save the following program into **`RandomGeneratorDemo.java`**:

```java
import java.util.Arrays;
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(2026L);
        RandomGenerator second = factory.create(2026L);

        boolean repeatable = true;
        for (int i = 0; i < 20; i++) {
            repeatable &= first.nextInt() == second.nextInt();
        }

        RandomGenerator rng = factory.create(42L);
        int die = rng.nextInt(1, 7);
        long sampleLong = rng.nextLong(100L, 200L);
        double fraction = rng.nextDouble();

        int[] fiveDice = rng.ints(5, 1, 7).toArray();
        boolean validDice = Arrays.stream(fiveDice)
                .allMatch(n -> n >= 1 && n < 7);

        RandomGeneratorFactory<RandomGenerator> defaultFactory =
                RandomGeneratorFactory.getDefault();

        System.out.println("algorithm = " + factory.name());
        System.out.println("same seed and calls = " + repeatable);
        System.out.println("splittable = " + factory.isSplittable());
        System.out.println("die in [1, 7) = " + (die >= 1 && die < 7));
        System.out.println("long in [100, 200) = "
                + (sampleLong >= 100 && sampleLong < 200));
        System.out.println("double in [0, 1) = "
                + (fraction >= 0.0 && fraction < 1.0));
        System.out.println("stream size = " + fiveDice.length);
        System.out.println("stream bounds valid = " + validDice);
        System.out.println("default state bits >= 64 = "
                + (defaultFactory.stateBits() >= 64));
    }
}
```

Compile and run in the directory containing the file, with **JDK 17 or higher**:

```bash
javac RandomGeneratorDemo.java
java RandomGeneratorDemo
```

Expected output for the specified API and algorithm:

```text
algorithm = L64X128MixRandom
same seed and calls = true
splittable = true
die in [1, 7) = true
long in [100, 200) = true
double in [0, 1) = true
stream size = 5
stream bounds valid = true
default state bits >= 64 = true
```

The example intentionally prints **the algorithm name and boolean conditions** instead of specific values from each draw. Random values still vary across calls or seeds, yet every draw in the code must satisfy the declared range. Two instances with the same algorithm and seed `2026L`, called the same number of times in the same order, yield matching sequences.

If you replace it with `getDefault()` or let the factory pick an algorithm dynamically via `all()`, do not rely on the default algorithm identity or number sequence as a fixed application contract.

## 8. Splittable and Jumpable: creating number streams for parallel computing

When multiple tasks share pseudorandom generation, **a single shared `RandomGenerator` may not be thread-safe**. The base interface does not guarantee synchronization. Using a separate generator per worker or an appropriate allocation strategy is the standard approach.

Java 17 introduces nested interfaces inside `RandomGenerator` to describe specialized capabilities:

- `RandomGenerator.SplittableGenerator`: creates a new generator via `split()`, serving work branching.
- `RandomGenerator.JumpableGenerator`: provides `jump()` to advance to a distant position in the state cycle.
- `RandomGenerator.LeapableGenerator` and `ArbitrarilyJumpableGenerator`: additional variants for jump distances.
- `RandomGenerator.StreamableGenerator`: provides ways to create streams of multiple generators.

These capabilities are **algorithm-dependent**, not present on every `RandomGenerator`. Only cast when you have verified the type or know the exact algorithm.

### Example of split() with an LXM algorithm

This is a standalone Java 17+ program; save as `SplitDemo.java`:

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SplitDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator.SplittableGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator.SplittableGenerator parent =
                factory.create(2026L);
        RandomGenerator.SplittableGenerator child = parent.split();

        int parentValue = parent.nextInt(1, 7);
        int childValue = child.nextInt(1, 7);

        System.out.println("parent valid = "
                + (parentValue >= 1 && parentValue < 7));
        System.out.println("child valid = "
                + (childValue >= 1 && childValue < 7));
        System.out.println("different objects = " + (parent != child));
    }
}
```

Compile and run:

```bash
javac SplitDemo.java
java SplitDemo
```

Output:

```text
parent valid = true
child valid = true
different objects = true
```

`split()` returns a separate generator that can be handed to another task. **Do not treat `split()` as an absolute mathematical proof that all generated sequences are independent in every scenario.** The algorithmic idea is to minimize overlap and support work division. When parallel simulation reproducibility is needed, you must also control **generator split order, task-to-generator mapping, and call scheduling**, because changing execution schedules can alter which slice of the sequence each task consumes.

Similarly, if you need `jump()`, choose an algorithm with `factory.isJumpable() == true` and use `RandomGenerator.JumpableGenerator`. Calling `jump()` does not “ask for stronger random numbers”; it shifts the generator's position in its cycle according to algorithm rules to support work partitioning.

### How does ThreadLocalRandom relate?

`ThreadLocalRandom.current()` remains useful in multithreaded code when each thread needs access to its own generator. It is a long-standing API and implements `RandomGenerator`. For flexible task-splitting architectures or fork/join, generators supporting `split()` may be more appropriate. Sharing an arbitrary instance must not be assumed safe merely because its variable type is `RandomGenerator`.

## 9. Seeds, reproducibility, and limits to understand

### 9.1. Why do seeds matter?

A seed initializes the starting state of a generator. The same algorithm and an appropriate seed, combined with the same call schedule, typically yield the same sequence of numbers, which is very useful when reproducing bugs. For example:

```java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator a = factory.create(1234L);
RandomGenerator b = factory.create(1234L);

// The nextLong() sequences of a and b will match if the corresponding call order is identical.
```

If one side calls an extra `nextInt()` beforehand, its state can advance differently; subsequent values will no longer match pairwise as expected. Likewise, stream calls versus individual calls with the same sample count are not always specified to return **the exact same position-by-position sequence**; Java only guarantees values follow the same distribution/range selection. Do not treat equivalence between stream methods and single-call loops as a reproducibility contract unless guaranteed by the specific algorithm/implementation.

### 9.2. Is a fixed seed secure?

**No.** A fixed seed makes the sequence repeatable and potentially predictable. Even a seed from the current clock does not guarantee enough entropy for security. Use fixed seeds deliberately for testing/simulation; never use them to generate session tokens, passwords, recovery codes, or keys.

`RandomGeneratorFactory.create()` without a seed is generally fine when repeating the same sequence is not desired, yet it **does not turn an ordinary algorithm into a CSPRNG**. Security relies on algorithms and entropy sources designed for that purpose; use `SecureRandom`.

### 9.3. What should be logged to reproduce results?

If a simulation must be rerun for comparison, log:

1. Algorithm name, e.g., `L64X128MixRandom`.
2. Value and type of the seed used.
3. JDK/provider version when cross-environment reproducibility is required.
4. Method call sequence, value counts, and bound/origin parameters.
5. For parallel programs, the `split()` topology, worker count, and task distribution scheme.

**A seed is not a full snapshot of state after many draws.** It describes initialization; to return to the middle of a sequence, you must replay the exact steps or use a provided/verified state-saving mechanism. Never assume every implementation supports serialization or provides a state-restoration API.

## 10. Common mistakes when migrating from Random to the Java 17 API

1. **Wrong package import.** `RandomGenerator` and `RandomGeneratorFactory` live in `java.util.random`, separate from `java.util.Random`.
2. **Trying to call `new RandomGenerator()`.** It is an interface; instantiate via `getDefault()`, `of(name)`, or a factory.
3. **Confusing upper range bounds.** `nextInt(1, 7)` generates 1–6, not 7; `nextInt(6)` generates 0–5.
4. **Using `getDefault()` and expecting the same algorithm on every JDK.** The default algorithm can change. Fix `name` when needed.
5. **Using the same seed while changing the call sequence.** Reproducibility depends on the algorithm and consumption order.
6. **Assuming every algorithm supports `long` seeds identically.** Factories have a fallback mechanism if an algorithm does not support the requested seed type. Pick a specific verified algorithm.
7. **Checking `factory.isSplittable()` and assuming the base interface has `split()`.** `split()` belongs to `RandomGenerator.SplittableGenerator`; use the proper type.
8. **Sharing a generator across threads without checking thread safety.** `RandomGenerator` does not promise thread safety; give each worker its own generator or use a dedicated mechanism.
9. **Using ordinary PRNGs for security.** Choose `SecureRandom` for sensitive tokens/keys/secrets regardless of how long a PRNG's period is.
10. **Creating an unbounded stream and collecting all elements.** For unsized `ints()`/`doubles()`, use `limit(n)` or a bounded consumption condition.
11. **Thinking `stateBits` equals seed entropy or “security level”.** It is the state size, not a measure of cryptographic unpredictability.
12. **Testing with hardcoded random values.** For code not using a named algorithm + seed with fixed call order, test invariants such as range, stream length, and uniqueness per appropriate statistical requirements; avoid tests asserting only that “today's number differs from yesterday's”.

## 11. Application: reproducible dice simulation

In tests or simulations, you can pass a `RandomGenerator` into a function instead of instantiating it directly, letting tests control the random input.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class DiceSimulation {
    static int roll(RandomGenerator generator) {
        return generator.nextInt(1, 7);
    }

    static int totalOfThreeRolls(RandomGenerator generator) {
        return roll(generator) + roll(generator) + roll(generator);
    }

    public static void main(String[] args) {
        var factory = RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(17L);
        RandomGenerator again = factory.create(17L);

        int result1 = totalOfThreeRolls(first);
        int result2 = totalOfThreeRolls(again);

        System.out.println("same total = " + (result1 == result2));
        System.out.println("total in [3, 18] = "
                + (result1 >= 3 && result1 <= 18));
    }
}
```

Save `DiceSimulation.java` and run:

```bash
javac DiceSimulation.java
java DiceSimulation
```

Output:

```text
same total = true
total in [3, 18] = true
```

The `roll()` function depends only on the `RandomGenerator` interface, making it easy to swap algorithms or inject a preconfigured generator from outside. In larger applications, this also separates **simulation business logic** from **algorithm-selection and seed-management policy**.

## 12. Self-check questions

**Question 1. How do `RandomGenerator` and `RandomGeneratorFactory` differ?**

`RandomGenerator` provides value-generation methods; `RandomGeneratorFactory` selects algorithms, queries metadata, and creates instances.

**Question 2. Why is `rng.nextInt(1, 7)` suitable for simulating a die?**

Because values lie in `[1, 7)`, i.e., 1 through 6, covering every possible value of a six-sided die.

**Question 3. If you use `RandomGenerator.getDefault()` with an implicit seed, can you test against an invariant hardcoded sequence?**

You should not. The default algorithm can change and the initial state is not fixed across runs.

**Question 4. What is needed to reproduce a sequence in a test?**

At minimum, control an algorithm supporting seeds, the seed value, and **the exact method call order**; if running in parallel, also add stream splitting and distribution policies.

**Question 5. What is `factory.isSplittable()` used for?**

To determine whether the factory creates an algorithm that supports splitting into generators for branching work; `split()` belongs to `RandomGenerator.SplittableGenerator`.

**Question 6. Can an algorithm with a huge `period()` be used to generate security keys?**

You cannot draw that conclusion. A large period and many `stateBits` do not guarantee unpredictability; use `SecureRandom` per security standards.

**Question 7. Does `factory.create(123L)` guarantee the seed is applied for every algorithm?**

No. Per the factory contract, when an algorithm does not support `long` seeds, the call may fall back to parameterless `create()`.

**Question 8. What does `RandomGeneratorFactory.all()` return?**

A `Stream<RandomGeneratorFactory<RandomGenerator>>` of available algorithms (excluding algorithms marked deprecated in Java 17), used for filtering or inspecting metadata; the actual set may differ across JDKs/providers.

**Question 9. Why should an arbitrary generator not be shared across multiple tasks?**

Because `RandomGenerator` does not promise thread safety; concurrent use can cause races or non-reproducible sequence consumption schedules. Depending on workload, use dedicated generators, `split()`/`jump()`, or `ThreadLocalRandom`.

**Question 10. When should `RandomGenerator` be passed as a function parameter?**

When you want to decouple logic consuming random numbers from algorithm/seed selection logic, making it easy to swap implementations and reproduce tests.

## 13. Official references

- [Oracle Java SE 17 — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): interface, range bounds, generation methods, and streams.
- [Oracle Java SE 17 — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): factory, `all()`, `of()`, `create()`, algorithm info, and seed limits.
- [Oracle Java SE 17 — java.util.random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): algorithm families and selection advice.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): goals of the API additions in Java 17.

**Key takeaway:** Since Java 17, **`RandomGenerator` is the number-generation contract**, while **`RandomGeneratorFactory` is the mechanism to select and instantiate algorithms**. Explicitly choose seed/algorithm when reproducibility is needed, choose `SplittableGenerator` or `JumpableGenerator` for corresponding workloads, watch `[origin, bound)` bounds, and **always use `SecureRandom` for security-sensitive data**.
