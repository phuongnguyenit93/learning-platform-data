# RandomGenerator as a Common Contract Starting in Java 17

Before Java 17, when developers needed to generate pseudo-random numbers, they typically had to choose a concrete class directly, such as `Random`, `ThreadLocalRandom`, or `SplittableRandom`. These classes have different purposes and characteristics, even though they all provide familiar operations like generating integers, floating-point numbers, booleans, or bytes.

Starting in **Java 17**, the `java.util.random` package provides **`RandomGenerator`** as a common contract for pseudo-random number generators (PRNGs). Thanks to this interface, application code can accept a generator via an abstract type, while selecting the concrete algorithm is handled separately through `RandomGeneratorFactory` or an appropriate implementation.

This is an official extension in Java 17 under **JEP 356 – Enhanced Pseudo-Random Number Generators**. This lesson focuses on the current Java 17 API: how to create generators, select algorithms, set seeds, generate bounded values, use streams, split generators for parallel work, and distinguish standard PRNGs from `SecureRandom`.

## 1. Why Do We Need a Common Contract?

Previously, a method might depend directly on `Random`:

~~~java
import java.util.Random;

static int rollDice(Random random) {
    return random.nextInt(6) + 1;
}
~~~

If you later wanted to switch to `SplittableRandom` or another algorithm, the method signature and call sites might have to change.

`RandomGenerator` provides a common type:

~~~java
import java.util.random.RandomGenerator;

static int rollDice(RandomGenerator random) {
    return random.nextInt(1, 7);
}
~~~

Any implementation fulfilling this contract can be passed into the method, as long as it meets the application's requirements.

Key benefits:

- **Decouple API from algorithm:** business code depends on `RandomGenerator` rather than a concrete class.
- **Easy implementation replacement:** you can choose a generator suited to the application, benchmarks, or parallelism style.
- **Support for new algorithms:** Java 17 adds many PRNG algorithms and a mechanism to discover them.
- **Easy seed control:** you can create a generator from a fixed seed to reproduce a sequence of values in tests or simulations.
- **APIs for streams and parallel tasks:** specialized implementations can support split, jump, or other capabilities.

`RandomGenerator` is a contract for value generation operations. It **does not mean every generator has the same algorithm, the same result sequence, the same thread-safety guarantees, or the same security level**.

## 2. Package and Core APIs

The APIs reside in the package:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;
~~~

`RandomGenerator` defines common generation operations. `RandomGeneratorFactory` helps find, inspect, and create algorithm instances.

| Component | Role |
| --- | --- |
| `RandomGenerator` | Common interface for pseudo-random number generators |
| `RandomGeneratorFactory` | Discover algorithms and create generators |
| `Random` | Familiar implementation, compatible with the common contract |
| `SplittableRandom` | Generator capable of splitting into child generators |
| `ThreadLocalRandom` | Generator bound to the current thread |
| `SecureRandom` | Random number generator for security purposes, also usable through the generator contract |
| `Math.random()` | Convenience API returning a `double` from 0.0 (inclusive) to 1.0 (exclusive) |

Some commonly used methods of `RandomGenerator`:

| Method | Meaning |
| --- | --- |
| `nextInt()` | Generates an arbitrary `int` |
| `nextInt(bound)` | Generates an `int` in `[0, bound)` |
| `nextInt(origin, bound)` | Generates an `int` in `[origin, bound)` |
| `nextLong()` | Generates a `long` |
| `nextLong(bound)` | Generates a `long` in `[0, bound)` |
| `nextDouble()` | Generates a `double` in `[0.0, 1.0)` |
| `nextDouble(bound)` | Generates a `double` in `[0.0, bound)` |
| `nextDouble(origin, bound)` | Generates a `double` in `[origin, bound)` |
| `nextBoolean()` | Generates a boolean |
| `nextBytes(bytes)` | Fills an array with pseudo-random bytes |
| `nextGaussian()` | Generates a value following a Gaussian normal distribution |
| `ints()`, `longs()`, `doubles()` | Creates streams of pseudo-random values |

For bounded methods, the lower bound is inclusive and the upper bound is exclusive. For example, `nextInt(1, 7)` can return 1, 2, 3, 4, 5, or 6; it will not return 7. Bounds must be valid and the upper bound must be greater than the lower bound; otherwise, the method throws `IllegalArgumentException`.

## 3. Creating a Generator the Simple Way

### 3.1. Using the Default Generator

`RandomGenerator.getDefault()` creates the default generator provided by the JDK:

~~~java
import java.util.random.RandomGenerator;

public class DefaultGeneratorDemo {
    public static void main(String[] args) {
        RandomGenerator random = RandomGenerator.getDefault();

        int dice = random.nextInt(1, 7);
        double ratio = random.nextDouble();
        boolean enabled = random.nextBoolean();

        System.out.println("dice = " + dice);
        System.out.println("ratio = " + ratio);
        System.out.println("enabled = " + enabled);
    }
}
~~~

This approach is convenient when the application only needs a general-purpose generator and does not need to bind to a specific algorithm.

However, if the algorithm is part of the technical requirements (such as reproducing simulations, synchronizing result sequences across components, or benchmarking), do not assume the default choice is always the application's algorithmic contract. Choose an explicit algorithm name via the factory.

### 3.2. Creating with the Static `of` Method

You can create a generator by algorithm name:

~~~java
RandomGenerator random =
        RandomGenerator.of("L64X128MixRandom");
~~~

The algorithm name must exist in the runtime being used. If the name is unsupported, the method throws `IllegalArgumentException`. You can check the list of available factories before choosing.

### 3.3. Using `RandomGeneratorFactory` When Seeds or Metadata Are Needed

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class FactoryDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(12345L);
        RandomGenerator second = factory.create(12345L);

        System.out.println(first.nextInt());
        System.out.println(second.nextInt());
    }
}
~~~

Two generators created with the same algorithm and the same seed start from the same initial state; when invoking the same sequence of methods in the same order, they can reproduce that algorithm's corresponding sequence of results.

The factory also provides metadata describing the implementation, such as its name, number of state bits, and supported capabilities. This is how an application separates **algorithm selection** from **generator usage logic**.

## 4. Discovering Algorithms with RandomGeneratorFactory

Java 17 provides many new PRNG algorithms. Do not assume every JDK or provider has the exact same list; discover the factories that the runtime actually provides.

~~~java
import java.util.random.RandomGeneratorFactory;

public class ListGenerators {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
                .map(RandomGeneratorFactory::name)
                .sorted()
                .forEach(System.out::println);
    }
}
~~~

`RandomGeneratorFactory.all()` returns a stream of available factories. From there, you can retrieve algorithm names, sort them, or display them for configuration purposes.

Some algorithm names you may encounter in JDK 17 include:

- `L32X64MixRandom`
- `L64X128MixRandom`
- `L64X128StarStarRandom`
- `L64X256MixRandom`
- `L64X1024MixRandom`
- `L128X128MixRandom`
- `L128X256MixRandom`
- `L128X1024MixRandom`
- `Xoshiro256PlusPlus`
- `Xoroshiro128PlusPlus`

The exact list should be obtained from `RandomGeneratorFactory.all()` at runtime. Do not copy a list from another environment and assume every name exists on every JDK/provider.

### 4.1. Inspecting Factory Metadata

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

System.out.println("name = " + factory.name());
System.out.println("stateBits = " + factory.stateBits());
System.out.println("isSplittable = " + factory.isSplittable());
System.out.println("isJumpable = " + factory.isJumpable());
System.out.println("isLeapable = " + factory.isLeapable());
~~~

Capability properties such as `isSplittable()`, `isJumpable()`, and `isLeapable()` indicate whether the implementation supports the corresponding specialized interfaces/behaviors. Not every algorithm supports every capability.

The factory also provides statistical/algorithmic properties such as `isStatistical()`, `isStochastic()`, `isHardware()`, `isStreamable()`, and attributes related to period/equidistribution. This is metadata describing the generator, not a guarantee that an algorithm is suitable for every problem.

### 4.2. Selecting an Algorithm by Configuration Name

If the application allows configuring the algorithm, validate the name and report errors clearly:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

static RandomGenerator createGenerator(String algorithm, long seed) {
    RandomGeneratorFactory<RandomGenerator> factory =
            RandomGeneratorFactory.of(algorithm);
    return factory.create(seed);
}
~~~

Do not silently fall back to the default generator if the configured name does not exist. Falling back can change the result sequence, performance characteristics, and reproducibility of the application.

## 5. Seed and Result Reproducibility

A **seed** is the value that initializes the state of a pseudo-random number generator. A PRNG is a deterministic algorithm: the same algorithm, the same initial state, and the same call sequence produce the same result sequence.

Example:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SeedDemo {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator a = factory.create(2026L);
        RandomGenerator b = factory.create(2026L);

        for (int i = 0; i < 5; i++) {
            System.out.println(a.nextInt() + " == " + b.nextInt());
        }
    }
}
~~~

Each line shows that two generators with the same seed and the same usage produce identical corresponding values.

### 5.1. Fixed Seeds Are Useful in Tests and Simulations

Fixed seeds help:

- Reproduce a test scenario involving randomness.
- Compare two versions of an algorithm on the same input sequence.
- Generate repeatable simulation data for analysis.
- Debug an issue that appeared in a specific run.

For example, a test can create its own generator for each case:

~~~java
RandomGenerator random =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(123456L);

int sample = random.nextInt(0, 100);
~~~

When a test fails, record the algorithm, seed, and sequence of operations needed to reproduce it. Recording only the seed may not be enough if the test also depends on execution order, shared state, or other random calls.

### 5.2. A Seed Does Not Make a PRNG Truly Random

If the seed is fixed, the result sequence is reproducible. If the seed comes from time or a varying source, the initial sequence changes, but that **does not turn an ordinary PRNG algorithm into a cryptographically secure generator**.

Do not use predictable seeds or the default generator to create passwords, session tokens, recovery codes, or secret keys.

### 5.3. Do Not Share a Stateful Generator Across Independent Tests

If multiple tests share one instance and call generation methods on it, execution order will affect the state. An earlier test can cause a later test to receive a different sequence.

Create a separate generator with an explicit seed in each test, or pass the generator into the object under test to control the dependency.

## 6. Generating Bounded Values Properly

### 6.1. Integers in a Range

~~~java
RandomGenerator random = RandomGenerator.getDefault();

int value = random.nextInt(10, 21);
~~~

The value lies in `[10, 21)`, meaning from 10 to 20.

To simulate a six-sided die:

~~~java
int dice = random.nextInt(1, 7);
~~~

There is no need to write `random.nextInt() % 6 + 1`. Use the bounded overload to avoid skewed distribution caused by modulo when the number of input values is not divisible by the number of faces.

### 6.2. Floating-Point Numbers in a Range

~~~java
double ratio = random.nextDouble();          // [0.0, 1.0)
double priceFactor = random.nextDouble(0.8, 1.2); // [0.8, 1.2)
~~~

The upper bound is exclusive. If you need to map to a range, use the origin/bound overload instead of manually adding/subtracting without checking the domain.

### 6.3. Avoid Hand-Written Modulo

Example to avoid:

~~~java
int dice = Math.abs(random.nextInt()) % 6 + 1;
~~~

There are two issues:

- Modulo distribution can be non-uniform when the source domain is not divisible by 6.
- `Math.abs(Integer.MIN_VALUE)` remains negative because its positive counterpart cannot be represented in `int`.

Use:

~~~java
int dice = random.nextInt(1, 7);
~~~

The bounded API is designed to produce results in the valid domain without modulo tricks.

## 7. Generating Data with the Stream API

`RandomGenerator` provides methods to create streams of pseudo-random numbers.

~~~java
RandomGenerator random = RandomGenerator.getDefault();

int[] values = random.ints(10, 0, 100).toArray();
long[] ids = random.longs(5, 1_000L, 10_000L).toArray();
double[] ratios = random.doubles(4, 0.0, 1.0).toArray();
~~~

Overloads with an element count produce finite streams:

- `ints(streamSize, origin, bound)`
- `longs(streamSize, origin, bound)`
- `doubles(streamSize, origin, bound)`

Overloads without `streamSize` create effectively unlimited streams; when using them, you need a limiting operation like `limit(n)` to keep the pipeline from running indefinitely.

~~~java
random.ints(0, 100)
        .limit(5)
        .forEach(System.out::println);
~~~

Random streams are lazy: the generator is consumed as the pipeline executes. Avoid parallel calls or reusing streams in ways that make state consumption order unclear when results must be reproduced accurately.

## 8. Choosing an Implementation: Random, ThreadLocalRandom, SplittableRandom

`RandomGenerator` is the common contract; in practice, you still need to pick an implementation based on usage.

| Implementation | Where It Fits | Notes |
| --- | --- | --- |
| `Random` | Legacy code compatibility, familiar API and seeding needed | Can experience state contention when used concurrently by many threads |
| `ThreadLocalRandom` | Many independent threads needing fast random numbers | Obtained via `current()`; not designed for manual seeding from application code |
| `SplittableRandom` | Simulations or computations split into subtasks | Has `split()`; instances are not designed for concurrent state mutation by multiple threads |
| LXM/Xoroshiro/Xoshiro algorithms via factory | Wanting a specific algorithm and leveraging the new API | Check capabilities and algorithm name in the runtime |
| `SecureRandom` | Data requiring unpredictability and security purposes | Explicitly choose the security API; do not substitute with standard statistical PRNGs |

### 8.1. Random

`Random` is a class from earlier Java versions and implements `RandomGenerator`:

~~~java
import java.util.Random;

Random random = new Random(1234L);
int value = random.nextInt(1, 7);
~~~

You can keep `Random` in legacy APIs and pass it wherever `RandomGenerator` is accepted. When writing new code, depending on the interface makes it easier to swap implementations if needed.

### 8.2. ThreadLocalRandom

~~~java
import java.util.concurrent.ThreadLocalRandom;

int value = ThreadLocalRandom.current().nextInt(1, 7);
~~~

`ThreadLocalRandom.current()` returns the generator bound to the current thread. This is a convenient choice when processing across multiple independent threads, reducing contention compared to multiple threads accessing a single `Random` instance.

Do not try to call `setSeed` on `ThreadLocalRandom` to reproduce a sequence; this mechanism is not designed for manual seeding from application code.

### 8.3. SplittableRandom and Splitting Generators

`SplittableRandom` is designed for scenarios where a workflow splits into multiple branches needing separate generators. Child generators can be created using `split()`:

~~~java
import java.util.SplittableRandom;

public class SplitDemo {
    public static void main(String[] args) {
        SplittableRandom parent = new SplittableRandom(2026L);

        SplittableRandom taskA = parent.split();
        SplittableRandom taskB = parent.split();

        System.out.println(taskA.nextInt(1, 7));
        System.out.println(taskB.nextInt(1, 7));
    }
}
~~~

The idea is to split the generator before handing off work branches to independent tasks. Do not share the same mutable instance across multiple threads. If reproducible results are needed, keep the seed and the split/call structure fixed in the same way.

`SplittableRandom` also implements `RandomGenerator.SplittableGenerator`, so variables can be declared with the specialized contract when `split()` needs to be called:

~~~java
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;

RandomGenerator.SplittableGenerator generator =
        new SplittableRandom(123L);

RandomGenerator.SplittableGenerator child = generator.split();
~~~

Not every `RandomGenerator` implementation supports splitting. Use the sub-interface or check factory metadata rather than assuming.

## 9. Distinguishing PRNGs from SecureRandom

The name "random" easily creates the impression that every generator is suitable for tokens or secret codes. In reality, **`RandomGenerator` is not a guarantee of cryptographic security**.

Standard PRNGs are optimized for generating pseudo-random sequences with appropriate statistical properties. If the algorithm and state are known or predictable, an attacker can predict subsequent values.

`SecureRandom` is designed for cryptographic needs and is the appropriate choice when generating sensitive data such as security tokens or nonces:

~~~java
import java.security.SecureRandom;

public class SecureTokenDemo {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] token = new byte[32];
        secureRandom.nextBytes(token);

        for (byte value : token) {
            System.out.printf("%02x", value);
        }
        System.out.println();
    }
}
~~~

`SecureRandom` also provides operations compatible with `RandomGenerator` in Java 17. However, keep the `SecureRandom` type wherever the security contract matters, so readers immediately recognize the requirement from the signature and avoid replacing it with an insecure generator.

Do not use `RandomGenerator.getDefault()`, `Random`, `SplittableRandom`, or `ThreadLocalRandom` to generate:

- Passwords or PINs.
- Session IDs, reset tokens, or access tokens.
- Encryption keys or nonces requiring unpredictability.
- Verification codes or other security-sensitive values.

## 10. Creating a Small Abstraction in an Application

A business service can accept `RandomGenerator` through its constructor:

~~~java
import java.util.Objects;
import java.util.random.RandomGenerator;

public final class DiceService {
    private final RandomGenerator random;

    public DiceService(RandomGenerator random) {
        this.random = Objects.requireNonNull(random, "random");
    }

    public int roll() {
        return random.nextInt(1, 7);
    }
}
~~~

Application runtime code can select the default generator or a configured algorithm:

~~~java
RandomGenerator random =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(2026L);

DiceService service = new DiceService(random);
System.out.println(service.roll());
~~~

Tests can inject a generator initialized with a fixed seed:

~~~java
RandomGenerator random =
        RandomGeneratorFactory.of("L64X128MixRandom")
                .create(1234L);

DiceService service = new DiceService(random);
int firstRoll = service.roll();
~~~

This makes the dependency explicit. It also avoids having business methods call `RandomGenerator.getDefault()` deep inside, which makes it difficult for tests to control the result sequence.

If a test only needs to verify logic reacting to specific values, you can use a fake implementation or a mock `RandomGenerator` instead of relying on an actual random sequence.

## 11. Split, Jump, and Leap Capabilities

Some generators provide sub-interfaces to support specialized state advancement strategies:

- **Splittable:** splits one generator into child generators, suitable when partitioning tasks.
- **Jumpable:** advances state forward by a large fixed distance defined by the algorithm.
- **Leapable:** jumps even farther according to the implementation's rules, useful in certain sequence partitioning schemes.

These capabilities are not present on all generators. In Java 17, the sub-interfaces are nested under `RandomGenerator`, such as `RandomGenerator.SplittableGenerator`, `RandomGenerator.JumpableGenerator`, and `RandomGenerator.LeapableGenerator`.

You can check capabilities before requesting one from a factory:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

if (factory.isSplittable()) {
    System.out.println("Generator supports split");
}
if (factory.isJumpable()) {
    System.out.println("Generator supports jump");
}
~~~

Do not choose an algorithm just because it has a memorable name. Identify your requirements first: generating independent data for tasks, reproducing simulations, performance, or statistical requirements. Then inspect the metadata and documentation of the concrete implementation.

## 12. Thread-Safety and Parallel Usage

`RandomGenerator` does not guarantee that every implementation is thread-safe. Behavior depends on the concrete class.

- `Random` can be shared across multiple threads, but contention on state can impact performance.
- `ThreadLocalRandom` provides a separate generator for the current thread.
- `SplittableRandom` fits splitting generators into separate instances per branch; do not use the same mutable instance across multiple threads.
- Other implementations have their own contracts and characteristics; read the documentation of the chosen algorithm.

Example using `ThreadLocalRandom` in a task running across multiple threads:

~~~java
import java.util.concurrent.ThreadLocalRandom;

Runnable task = () -> {
    int sample = ThreadLocalRandom.current().nextInt(0, 100);
    System.out.println(Thread.currentThread().getName() + ": " + sample);
};
~~~

For parallel computations requiring reproducible results, how generators are split and the order in which tasks are assigned must be designed explicitly. Using the same seed while leaving thread scheduling unconstrained can cause numbers to be consumed in different orders across runs.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Code tightly coupled to `Random` | Choosing a concrete class directly in business APIs | Accept `RandomGenerator` via parameter or constructor |
| Unsupported algorithm name | Runtime does not provide that factory | Discover with `RandomGeneratorFactory.all()` and handle configuration errors |
| Test results change every run | Using a different seed or a shared stateful generator | Create an isolated generator with a fixed seed |
| Manually computing `nextInt() % bound` | Can produce skewed distribution; also has the `Math.abs(MIN_VALUE)` trap | Use `nextInt(bound)` or `nextInt(origin, bound)` |
| Using the default generator to create tokens | Statistical PRNGs are not cryptographic guarantees | Use `SecureRandom` |
| Sharing `SplittableRandom` across multiple threads | Stateful instance not designed for concurrent sharing | Split into child generators or use a thread-local option |
| Assuming every generator has `split()` | Only generators implementing the splittable interface have it | Use `SplittableGenerator` or check the factory |
| Fixed seed yet tests still differ | Random calls or execution schedule changed | Isolate generators, fix ordering and seed |
| Assuming `RandomGenerator` guarantees identical sequences | Common interface does not mandate identical algorithms | Pick a specific algorithm and control the environment for reproducibility |
| Creating an infinite stream without bounding it | Using `ints()`/`doubles()` without stream size | Use sized overloads or `limit()` |

## 14. Practice Exercises

### Exercise 1 — Using the Common Contract

Write a method `rollDice(RandomGenerator generator)` returning a value in `[1, 7)`. Call the method with the default generator and with a `Random` instance. Explain why the method signature does not need to change.

### Exercise 2 — Discovering Factories

Use `RandomGeneratorFactory.all()` to print the names of algorithms available in the runtime. Pick a name, get its factory, and print `name()`, `stateBits()`, and `isSplittable()`. Do not assume the list on another machine is identical.

### Exercise 3 — Reproducing with a Seed

Create two generators with the same algorithm and seed. Generate 20 values from each generator and compare the two resulting arrays. Change one seed and explain why the sequence changes.

### Exercise 4 — Bounded Stream

Create a stream of 10 integers from 1 to 100. Convert it to an array, print it, and verify that all values satisfy `value >= 1 && value < 100`.

### Exercise 5 — Splitting Generators

Use `SplittableRandom` to create child generators for two tasks. Do not share the same instance across tasks. Try a fixed seed and note how the split order affects the results.

### Exercise 6 — Choosing a Generator by Requirement

Compare three needs: a Monte Carlo simulation with a reproducible seed, many independent requests on a thread pool, and generating login tokens. Choose the suitable implementation for each case and explain why.

## 15. Usage Guidelines in Java 17

`RandomGenerator` establishes a **common contract** for applications to use various pseudo-random number generators without hard-coding dependencies on a single implementation. `RandomGeneratorFactory` adds a way to discover algorithms, create generators by name and seed, and inspect metadata about their capabilities.

When designing:

- Use `RandomGenerator` as the common dependency type in business code.
- Choose the default generator when no algorithm constraint is needed; choose a factory by name when the algorithm is part of the contract.
- Use fixed seeds to reproduce tests and simulations, and isolate state between test cases.
- Use bounded overloads instead of hand-written modulo operations.
- Choose `SplittableRandom`/`SplittableGenerator` for work needing split generation streams; choose `ThreadLocalRandom` for appropriate per-thread needs.
- Use `SecureRandom` for data requiring cryptographic unpredictability; the `RandomGenerator` interface name itself does not guarantee that.

Separating the **number generation contract** from the **concrete algorithm** makes Java 17 code easier to change, test, and configure. However, quality, splittability, thread safety, and security must still be decided based on the concrete implementation and actual requirements.
