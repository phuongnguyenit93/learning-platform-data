# The Role of Seed, State, and PRNG Algorithms in Java 17

When calling `nextInt()`, `nextDouble()`, or other random number generation methods in Java, a program does not usually receive a value generated completely randomly from scratch. Instead, a **pseudo-random number generator** (*PRNG*) computes a sequence of values using a deterministic algorithm, starting from an initial state.

Three concepts need to be distinguished:

- **Seed:** data used to initialize the generator's initial state.
- **State:** internal state that changes after each number generation or each step of the algorithm.
- **Algorithm:** rules that transform the current state into the next state and produce an output value.

Understanding these three concepts helps you reproduce results during testing, generate different sequences across runs, use PRNGs properly in multithreaded environments, and choose the right tool when security is needed.

## 1. How Does a PRNG Work?

A PRNG can be modeled as:

\[
S_{n+1} = f(S_n)
\]

\[
X_n = g(S_n)
\]

Where:

- \(S_n\) is the internal state at step \(n\).
- \(f\) is the state transition function defined by the algorithm.
- \(g\) is the rule for producing an output value from the state.
- \(X_n\) is the pseudo-random value received by the program.

The seed is used to initialize \(S_0\). Then, each time a value is requested, the generator updates its state and produces the next result.

```text
seed
  |
  v
Initialize state S0
  |
  v
PRNG Algorithm
  |
  +----> produce X0
  |
  v
Update state S1
  |
  +----> produce X1
  |
  v
Update state S2
  |
  +----> produce X2
  |
  v
...
```

Because the algorithm is deterministic, **the same algorithm, the same seed, and the same sequence of calls will reproduce the same sequence of results**, provided the generator's compatibility rules are preserved. This is a very useful property for testing and simulation.

A PRNG is not a *true random number generator*. It generates a sequence that appears random according to the algorithm's statistical properties, but that sequence is determined by its state and algorithm.

## 2. Seed: The Starting Point of the Sequence

The seed is the input used to initialize the generator. For a deterministic PRNG:

- The same seed usually produces the same initial state.
- Different seeds usually produce different sequences.
- The seed is not the only value emitted; it is initialization data.
- A seed does not guarantee good statistical quality if the PRNG algorithm is weak.

### 2.1. Example with java.util.Random

`java.util.Random` is a familiar PRNG in Java:

```java
import java.util.Random;

public class SeedDemo {
    public static void main(String[] args) {
        Random first = new Random(12345L);
        Random second = new Random(12345L);

        for (int i = 0; i < 5; i++) {
            int a = first.nextInt(100);
            int b = second.nextInt(100);

            System.out.println(a + " == " + b + " ? " + (a == b));
        }
    }
}
```

Both objects are created with the same seed and receive the same sequence of `nextInt(100)` calls, so each corresponding pair of results is equal.

Example output:

```text
51 == 51 ? true
80 == 80 ? true
41 == 41 ? true
28 == 28 ? true
55 == 55 ? true
```

The important property is not that the specific numbers are 51 or 80, but the ability to **reproduce the sequence** when initializing the same generator and repeating the same usage pattern.

### 2.2. Different Seeds, Different Sequences

```java
Random a = new Random(100L);
Random b = new Random(200L);

System.out.println(a.nextInt());
System.out.println(b.nextInt());
```

Two different seeds usually produce two different sequences. However, you should not assume that **every distinct seed always produces a completely unrelated or statistically independent sequence**. That depends on the state space and algorithm quality.

An algorithm with finite state has only finitely many initial states. Multiple seeds may map to the same internal state, or produce sequences with certain relationships.

### 2.3. No Explicit Seed: Self-Initialized Generator

You can write:

```java
Random random = new Random();
```

In this case, `Random` initializes its own seed using the Java implementation's mechanism. Using the no-argument constructor is suitable when you do not need to reproduce an exact known sequence.

For repeatable testing, it is usually best to provide an explicit seed:

```java
Random random = new Random(202617L);
```

Logging the seed when running simulations or randomized tests also helps reproduce bugs later.

## 3. State: State Changes After Each Generation

The seed only initializes the generator. Once number generation starts, the PRNG maintains its own **state** and updates that state across algorithm steps.

Conceptual example:

```text
Seed = 42
  |
  v
State S0
  | nextInt()
  v
State S1 ----> output 1
  | nextDouble()
  v
State S2 ----> output 2
  | nextInt()
  v
State S3 ----> output 3
```

With the same seed but a different number of calls or a different call order, the program can receive different values at corresponding positions.

### 3.1. Same Seed, Different Call Order

```java
import java.util.Random;

public class CallOrderDemo {
    public static void main(String[] args) {
        Random first = new Random(42L);
        Random second = new Random(42L);

        int firstA = first.nextInt();
        int firstB = first.nextInt();

        int secondA = second.nextInt();
        double extra = second.nextDouble();
        int secondB = second.nextInt();

        System.out.println(firstA == secondA); // true
        System.out.println(firstB == secondB); // usually false
        System.out.println(extra);
    }
}
```

The `nextDouble()` call on the second generator consumed state according to the algorithm's rules, so the subsequent `nextInt()` value no longer corresponds to the second call on the first generator.

For methods that may require multiple internal steps—for example, `nextInt(bound)`, which uses rejection sampling to avoid skewed distribution—the number of state updates may not be fixed for all inputs. Therefore, to reproduce results, you must preserve **the entire call sequence**, not just the seed.

### 3.2. State Is Not the Same as Seed

The seed is the initialization input. The state is the internal data after the generator has progressed through some number of steps.

Some APIs allow resetting a generator with a seed, for example:

```java
Random random = new Random(10L);

int first = random.nextInt();
int second = random.nextInt();

random.setSeed(10L); // Reinitialize the sequence with the given seed.
int repeatedFirst = random.nextInt();
```

With `Random`, calling `setSeed` resets the generator's state so the sequence is regenerated. However, not every PRNG API has a `setSeed` method; for instance, `SplittableRandom` does not provide a way to reseed an existing instance.

Do not assume you can read, save, or restore the internal state of every generator simply by keeping the seed. For some applications that need simulation checkpoints, you must choose an API/design that explicitly supports saving state or manage generation progress in your own way.

## 4. The PRNG Algorithm Determines Sequence Characteristics

The same seed with **different algorithms** can produce different sequences. The algorithm determines:

- How state is updated.
- The size of the state space.
- The period before the sequence repeats.
- Distribution quality and correlation between values.
- Computational cost.
- Ability to run in parallel or split generation streams.
- Suitability for security purposes.

There is no single best algorithm for every situation. A generator used for simulation may prioritize speed and reproducibility; a generator used for keys or tokens requires security properties.

### 4.1. Random's Linear Congruential Generator

`java.util.Random` in Java uses a form of **Linear Congruential Generator (LCG)** with a 48-bit state. The state transition rule is specified by the formula:

\[
S_{n+1} = (S_n \times 0x5DEECE66D + 0xB)
            \bmod 2^{48}
\]

When initialized with a seed, `Random` scrambles the input seed and maintains the state in 48 bits. The `next(...)` methods extract bits from the state to produce values.

Example:

```java
Random random = new Random(123L);
int a = random.nextInt();
double b = random.nextDouble();
long c = random.nextLong();
```

Key characteristics to remember:

- The algorithm is specified so that conforming Java implementations produce the same sequence when given the same seed and the same sequence of calls.
- The state is only 48 bits, so the state space is finite.
- `Random` is suitable for many general-purpose simulation and testing needs.
- Do not use `Random` to generate passwords, authentication tokens, keys, or data that must resist prediction.

One consequence of a 48-bit state is that different input seeds are not guaranteed to correspond to distinct 48-bit states; bits beyond the effective state width cannot enlarge the state space.

### 4.2. Modern PRNGs in Java 17

Java 17 introduces the `java.util.random` package through JEP 356 — Enhanced Pseudo-Random Number Generators. The new API provides the `RandomGenerator` interface and an implementation selection mechanism via `RandomGeneratorFactory`.

Some algorithm families provided in JDK 17 include:

- **LXM:** combines an LCG component with an xor/multiply-style mixer; available in multiple state configurations.
- **Xoroshiro:** a family of algorithms using XOR, bit-shift, and bit-rotate operations.
- **Xoshiro:** a related family with variants of different state sizes and properties.
- **Legacy generators:** such as `Random` and `SplittableRandom`, which remain usable through the compatibility API.

Specific algorithm names can be inspected through `RandomGeneratorFactory`. Do not guess names from the family name; use the factory to retrieve the list of implementations provided by the runtime.

## 5. RandomGenerator: Java 17's Common API

Java 17 adds the `java.util.random.RandomGenerator` interface. It defines common generation operations such as `nextInt()`, `nextLong()`, `nextDouble()`, and bounded variants.

Thanks to this common interface, code can work with many algorithms without depending directly on a concrete class.

```java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorDemo {
    public static void main(String[] args) {
        RandomGenerator generator =
                RandomGeneratorFactory
                        .of("L64X128MixRandom")
                        .create(12345L);

        System.out.println(generator.nextInt(100));
        System.out.println(generator.nextDouble());
        System.out.println(generator.nextLong());
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 RandomGeneratorDemo.java
java RandomGeneratorDemo
```

In the example:

1. `RandomGeneratorFactory.of(...)` selects an implementation by algorithm name.
2. `create(12345L)` creates a generator with the specified seed.
3. The `generator` variable depends only on the `RandomGenerator` interface; you can swap implementations without changing how basic generation methods are called.

The name `L64X128MixRandom` is one implementation included among JDK 17's PRNG algorithms. When deploying to another runtime, verify that the algorithm is available on the target runtime.

### 5.1. Listing Provided Algorithms

You can discover available factories:

```java
import java.util.random.RandomGeneratorFactory;

public class ListGenerators {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
                .map(RandomGeneratorFactory::name)
                .sorted()
                .forEach(System.out::println);
    }
}
```

The list depends on the implementations provided by the runtime. When writing an application that requires a specific algorithm, choose an explicit name and check availability in the deployment environment.

### 5.2. When to Use the Common API?

`RandomGenerator` is useful when:

- You want to select an algorithm via configuration.
- You want to write functions accepting a generator for deterministic seeded testing.
- You want to share generation logic across `Random`, `SplittableRandom`, or other generators.
- You want to leverage modern algorithms in JDK 17.

Example of injecting a generator into a method:

```java
import java.util.random.RandomGenerator;

static int rollDie(RandomGenerator random) {
    return random.nextInt(1, 7);
}
```

The method does not need to know which concrete class the generator is. During testing, pass a generator with a fixed seed; when running simulations, choose an appropriate implementation.

## 6. Common Generators and How to Choose

| API | Characteristics | Use Case |
| --- | --- | --- |
| `Random` | 48-bit LCG; thread-safe; long-standing compatibility | Examples, general-purpose applications, and code needing `Random`-compatible sequences |
| `SplittableRandom` | Designed for splitting generators; not thread-safe | Simulations or parallel tasks that can split number generation sources |
| `ThreadLocalRandom` | Generator bound to the current thread; reduces contention across many threads | Multithreaded tasks needing general-purpose pseudo-random numbers without manual seed management |
| `RandomGenerator` + factory | Common interface and modern algorithms in Java 17 | Applications wanting explicit algorithm selection and decoupling from concrete implementations |
| `SecureRandom` | Security-oriented generator, typically drawing entropy from providers/OS | Tokens, nonces, salts, keys, and sensitive values |

### 6.1. Random: Simple and Reproducible

`Random` can be shared across threads because seed updates are synchronized in a thread-safe manner. However, when multiple threads call the same instance concurrently, which thread receives which value depends on execution scheduling. The overall per-thread sequences can vary across parallel runs even with the same initial seed.

If each thread needs its own generator, you can choose `ThreadLocalRandom` or create separate generators with intentionally managed seeds.

### 6.2. SplittableRandom: Splitting Generators for Tasks

`SplittableRandom` is designed for algorithms that split work across tasks. A generator can create child generators via `split()`:

```java
import java.util.SplittableRandom;

public class SplitDemo {
    public static void main(String[] args) {
        SplittableRandom parent = new SplittableRandom(2026L);

        SplittableRandom firstTask = parent.split();
        SplittableRandom secondTask = parent.split();

        System.out.println(firstTask.nextInt(100));
        System.out.println(secondTask.nextInt(100));
    }
}
```

Each task uses its own generator, avoiding multiple threads updating the same state. The generated streams are designed for good statistical independence in typical use, though this should not be interpreted as an absolute mathematical guarantee that all substreams are completely independent.

`SplittableRandom` is **not thread-safe**. Do not share the same instance across multiple threads operating concurrently. Split beforehand or ensure each instance is owned by only one thread at a time.

### 6.3. ThreadLocalRandom: Per-Thread Generator

Example:

```java
import java.util.concurrent.ThreadLocalRandom;

public class ThreadLocalDemo {
    public static void main(String[] args) {
        int value = ThreadLocalRandom.current().nextInt(1, 7);
        System.out.println(value);
    }
}
```

`ThreadLocalRandom.current()` returns the generator bound to the current thread. This is a practical choice for many multithreaded tasks that need pseudo-random numbers without manually managing seeds per thread.

This API does not expose a public seeding mechanism like `Random(long seed)`; do not choose it if your primary goal is reproducing a sequence from an application-specified seed.

### 6.4. SecureRandom: When Unpredictability Is Required

`SecureRandom` is the choice for security-sensitive data:

```java
import java.security.SecureRandom;
import java.util.HexFormat;

public class SecureRandomDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();
        byte[] token = new byte[32];
        secureRandom.nextBytes(token);

        System.out.println(HexFormat.of().formatHex(token));
    }
}
```

`SecureRandom` is typically initialized with entropy from providers and the environment's random sources. Do not use a fixed seed expecting security; supplying a weak or predictable seed can reduce the unpredictability of the generated data.

## 7. Reproducibility: The Same Seed Is Not Enough if Usage Changes

Reproducibility is useful in:

- Unit testing.
- Scientific simulations.
- Benchmarks with stable input data.
- Replaying a bug scenario.
- Comparing two algorithms on the same dataset.

To reproduce a run, you need to record more than just the seed:

1. **PRNG name/type:** `Random`, `SplittableRandom`, or a specific algorithm.
2. **Seed:** the value used for initialization.
3. **Runtime/API version:** especially if using a factory-provided algorithm and needing cross-environment compatibility.
4. **Call sequence:** method types, call counts, bounds, and execution order.
5. **Parallel structure:** how generators are split, how they are assigned to tasks, and processing order.

For example, saving only the seed and later inserting an extra `nextInt()` call before data generation will shift all subsequent values in the sequence.

### 7.1. Injecting a Generator into Code Instead of Creating Them Scattered Throughout

A convenient design for testing:

```java
import java.util.random.RandomGenerator;

public class DiceService {
    private final RandomGenerator random;

    public DiceService(RandomGenerator random) {
        this.random = random;
    }

    public int roll() {
        return random.nextInt(1, 7);
    }
}
```

In a test environment:

```java
RandomGenerator testGenerator =
        RandomGeneratorFactory
                .of("L64X128MixRandom")
                .create(123L);

DiceService service = new DiceService(testGenerator);
```

In production, you can provide an appropriately configured generator. This dependency-injection approach makes where the seed is created explicit and lets tests control the pseudo-random number source.

### 7.2. Reproducibility in Parallel Processing

For parallel tasks, results also depend on how work is partitioned. If threads share a single `Random`, scheduling can determine which thread receives which element of the sequence.

For better reproducibility:

- Split generators according to task structure instead of sharing a single instance.
- Use `SplittableRandom` or a splittable generator where appropriate.
- Assign child generators to tasks deterministically.
- Do not let results depend on thread completion order if that order is uncontrolled.
- Record the split/seed configuration and how work is partitioned.

Merely setting a fixed seed on a shared generator does not automatically make an entire multithreaded program reproducible.

## 8. PRNG Quality and the Limits of Seeds

A seed cannot turn a weak algorithm into a good one. Sequence quality depends on:

- The *period* before the state repeats.
- Distribution of output bits.
- Correlation between consecutive values.
- Correlation between sequences when using multiple seeds or splits.
- Behavior under parallel execution.
- Unpredictability, if the goal involves security.

A PRNG with a large period can still have statistical structure unsuitable for certain simulations. Conversely, a very fast generator is not necessarily secure against an attacker.

### 8.1. Do Not Generate Numbers in a Range with Arbitrary Modulo

Example:

```java
int value = random.nextInt() % 10;
```

The value can be negative, and the remainder distribution can be uneven because the count of source values is not divisible by 10. Use the bounded API instead:

```java
int value = random.nextInt(10); // 0 to 9
int dice = random.nextInt(1, 7); // 1 to 6
```

Bounded overloads are designed to produce values within the requested range with proper distribution, avoiding common modulo pitfalls.

### 8.2. Low-Entropy Seeds Are Unsuitable for Generating Secrets

A fixed seed like `12345L` is great for tests but easy to guess. If an application uses a non-cryptographic PRNG to generate tokens, someone who knows the algorithm and state can predict subsequent values.

For secret data, use `SecureRandom`. Do not substitute it with:

```java
new Random(System.currentTimeMillis())
```

The current time can usually be guessed within a range, and `Random` is not designed to resist prediction. Increasing seed complexity does not turn a non-cryptographic algorithm into a CSPRNG.

## 9. Choosing a PRNG by Scenario

| Scenario | Recommendation | Reason |
| --- | --- | --- |
| Tests needing repeatable results | `Random(seed)` or a deterministic generator via factory | Sequence can be reproduced when keeping the seed, algorithm, and call sequence. |
| Standard sequential simulation | `RandomGenerator` with an appropriate algorithm or `Random` | Choose the API based on quality and compatibility requirements. |
| Parallel tasks needing child generators | `SplittableRandom` or a splittable generator | Each task has its own source, avoiding shared state. |
| Multithreaded application needing general per-thread random numbers | `ThreadLocalRandom.current()` | Reduces contention when multiple threads generate numbers. |
| Random tokens, nonces, keys, salts | `SecureRandom` | Targets unpredictability and security requirements. |
| Need to swap algorithms via configuration on Java 17 | `RandomGeneratorFactory` | Select implementations by name and use through the common interface. |

Do not choose a PRNG just because an example runs fast. Consider the goal, reproducibility, parallelism pattern, statistical quality, and security requirements.

## 10. Comprehensive Example: Reproducible Simulation

Suppose you want to simulate 10,000 dice rolls and count how many times each face appears. A fixed seed gives test runs the same results:

```java
import java.util.Arrays;
import java.util.Random;

public class DiceSimulation {
    static int[] simulate(long seed, int rolls) {
        Random random = new Random(seed);
        int[] counts = new int[6];

        for (int i = 0; i < rolls; i++) {
            int face = random.nextInt(6);
            counts[face]++;
        }

        return counts;
    }

    public static void main(String[] args) {
        int[] first = simulate(2026L, 10_000);
        int[] second = simulate(2026L, 10_000);

        System.out.println(Arrays.toString(first));
        System.out.println(Arrays.equals(first, second));
    }
}
```

Both calls to `simulate` create a new generator with the same seed, the same number of `nextInt(6)` calls, and the same order. Thus, the result array is reproducible.

If you change the seed or add a random call before the loop, the simulation results change. That is expected PRNG behavior.

When evaluating probabilities, a single run of 10,000 rolls is only a simulation sample. Do not expect all six faces to appear the exact same number of times; random variation is normal.

## 11. Common Misconceptions

**"The seed is the first random number."**  
Incorrect. The seed is data used to initialize the state. Output values are computed by the algorithm from that state.

**"The same seed always produces the same sequence even if you change the PRNG type."**  
Incorrect. Different algorithms have different state transition rules and output mappings.

**"The same seed is enough to reproduce a program."**  
Not enough. You need the same algorithm, the same call sequence, and matching processing structure. Parallel runs also depend on how generators are split and assigned.

**"Different seeds guarantee independent sequences."**  
You cannot conclude that. Statistical independence depends on the algorithm and initialization scheme.

**"Random is thread-safe, so the order of results per thread is always stable."**  
Incorrect. Thread safety protects state consistency, but the order in which threads receive values depends on execution scheduling.

**"Sharing SplittableRandom across threads is safe."**  
Incorrect. `SplittableRandom` is not thread-safe; split it and assign separate generators to tasks.

**"Random is secure enough to generate tokens."**  
Incorrect. `Random` and general-purpose PRNGs are not designed to resist prediction. Use `SecureRandom` for sensitive data.

**"Current time is a good security seed."**  
Incorrect. Time can be guessed within a window; predictable seeds make sequences easier to predict.

## 12. Self-Check Questions

**1. What is the role of the seed in a PRNG?**  
To initialize the initial state so the algorithm can start generating a sequence.

**2. How does state differ from seed?**  
The seed is the initialization input; state is the internal state that changes as the PRNG generates numbers.

**3. Why can the same seed with a different call sequence produce different results?**  
Because each call consumes/updates state; an extra call shifts subsequent values.

**4. Which algorithm does `Random` use in Java?**  
An LCG with a 48-bit state, with specified state transition rules.

**5. Which API was added in Java 17 to standardize using multiple PRNGs?**  
The `java.util.random` package, including `RandomGenerator` and `RandomGeneratorFactory`.

**6. Why use `SplittableRandom` in some parallel tasks?**  
Generators can be split into separate sources for tasks, avoiding multiple threads updating one state; each instance must still follow non-thread-safe usage rules.

**7. When is `SecureRandom` needed?**  
When generating data that must be unpredictable, such as tokens, nonces, or keys.

**8. Why should you not use `random.nextInt() % 10` to generate numbers from 0 to 9?**  
It can return negative numbers and have an uneven distribution; use `nextInt(10)`.

**9. What should you record to reproduce a bug from a randomized run?**  
Seed, generator type/algorithm, relevant runtime, call sequence, and task-splitting structure.

**10. Is a PRNG a true random source?**  
No. A PRNG is a deterministic generator based on state and algorithm; it produces a pseudo-random sequence.

## Official References

- [JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): new PRNG API in Java 17, `RandomGenerator`, factories, and algorithms.
- [Java SE 17 API — `java.util.random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): overview of generator and factory APIs.
- [Java SE 17 API — `RandomGenerator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): pseudo-random number generator interface.
- [Java SE 17 API — `RandomGeneratorFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): selecting and creating implementations by name.
- [Java SE 17 API — `Random`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): algorithm, seed, and compatibility of `Random`.
- [Java SE 17 API — `SplittableRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): splittable generator and usage rules in parallel environments.
- [Java SE 17 API — `ThreadLocalRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): generator bound to the current thread.
- [Java SE 17 API — `SecureRandom`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): random number generator for security purposes.
