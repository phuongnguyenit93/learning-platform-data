# Creating Generators with RandomGenerator.of and RandomGeneratorFactory

## 1. Background: The Random Number Generation API in Java 17

Java 17 introduces a unified API for random number generators in the `java.util.random` package. Its centerpiece is the **`RandomGenerator`** interface: consumer code can call a common contract to obtain `int`, `long`, `float`, `double`, `boolean`, or streams of pseudo-random numbers without depending directly on a concrete generator class.

To create a generator, Java provides two common approaches:

- **`RandomGenerator.of(String name)`:** selects an algorithm by name and immediately creates an instance.
- **`RandomGeneratorFactory.of(String name)`:** retrieves a factory for an algorithm. A factory can create multiple instances, accept seeds, provide metadata, and help select algorithms based on properties.

Both APIs share the goal of selecting an algorithm, but serve different needs:

~~~text
Only need one generator
    RandomGenerator.of("L64X128MixRandom")
                |
                v
        RandomGenerator instance

Need a factory to create multiple instances / seed / inspect metadata
    RandomGeneratorFactory.of("L64X128MixRandom")
                |
                v
        RandomGeneratorFactory
                |
       +--------+---------+
       |        |         |
    create() create(seed) metadata
       |        |
       v        v
    RandomGenerator instance
~~~

This API is well suited for simulations, games, testing, data sampling, test-data generation, and computations requiring pseudo-random numbers. **Do not assume every algorithm under `RandomGenerator` is cryptographically secure.** If you need authentication tokens, password reset tokens, keys, or security nonces, use `SecureRandom`.

## 2. RandomGenerator: Common Contract for Value Generation

### 2.1. Creating an Instance Quickly with `RandomGenerator.of`

Example:

~~~java
import java.util.random.RandomGenerator;

public class RandomGeneratorQuickStart {
    public static void main(String[] args) {
        RandomGenerator random =
                RandomGenerator.of("L64X128MixRandom");

        int dice = random.nextInt(1, 7);
        double ratio = random.nextDouble(0.0, 1.0);
        boolean accepted = random.nextBoolean();

        System.out.println("Dice: " + dice);
        System.out.println("Ratio: " + ratio);
        System.out.println("Accepted: " + accepted);
    }
}
~~~

`RandomGenerator.of(name)` returns an instance using the specified algorithm. It corresponds to selecting an implementation by name and creating a generator using no-argument initialization.

Points to remember:

- `name` is the algorithm name, e.g. `"L64X128MixRandom"`.
- If `name == null`, the method throws `NullPointerException`.
- If no algorithm with that name is found, the method throws `IllegalArgumentException`.
- This method **does not accept a seed**. If you need an explicit seed, use `RandomGeneratorFactory`.

### 2.2. Commonly Used Generation Methods

Once you have a `RandomGenerator`, you can call these methods:

| Method | Result |
|---|---|
| `nextInt()` | A pseudo-random `int` over the type's domain |
| `nextInt(bound)` | An `int` from 0 inclusive to `bound` exclusive |
| `nextInt(origin, bound)` | An `int` from `origin` inclusive to `bound` exclusive |
| `nextLong()` | A pseudo-random `long` |
| `nextLong(origin, bound)` | A `long` in the half-open interval |
| `nextFloat()` | A `float` from 0.0 inclusive to 1.0 exclusive |
| `nextDouble()` | A `double` from 0.0 inclusive to 1.0 exclusive |
| `nextDouble(origin, bound)` | A `double` in the half-open interval |
| `nextBoolean()` | A boolean value |
| `nextBytes(byte[] bytes)` | Fills the array with pseudo-random bytes |
| `nextGaussian()` | A normally distributed value with mean 0 and standard deviation 1 |
| `nextExponential()` | A non-negative exponentially distributed value with mean 1 |

Example:

~~~java
RandomGenerator random =
        RandomGenerator.of("L64X128MixRandom");

int index = random.nextInt(0, 100);
long orderNumber = random.nextLong(1_000_000L, 9_000_000L);
double probability = random.nextDouble(0.0, 1.0);
double normalValue = random.nextGaussian();
~~~

For overloads taking `origin` and `bound`, the lower bound is included and the upper bound is excluded. For example, `nextInt(1, 7)` produces numbers from 1 to 6, suitable for simulating a six-sided die.

Invalid ranges (such as `origin >= bound`, or certain non-finite bounds for floating-point APIs) can cause the method to throw `IllegalArgumentException`. Define input domains clearly instead of computing them manually with modulo.

### 2.3. Creating Streams of Pseudo-Random Numbers

`RandomGenerator` also provides `ints()`, `longs()`, and `doubles()`:

~~~java
import java.util.random.RandomGenerator;
import java.util.List;

public class RandomStreams {
    public static void main(String[] args) {
        RandomGenerator random =
                RandomGenerator.of("L64X128MixRandom");

        List<Integer> sample = random.ints(10, 1, 7)
                .boxed()
                .toList();

        System.out.println(sample);

        double average = random.doubles(1_000, 0.0, 1.0)
                .average()
                .orElseThrow();

        System.out.println("Average: " + average);
    }
}
~~~

In the example:

- `ints(10, 1, 7)` creates a stream of 10 integers, each in `[1, 7)`.
- `boxed()` converts the `IntStream` to `Stream<Integer>` to collect into a list.
- `doubles(1_000, 0.0, 1.0)` creates 1,000 doubles in `[0.0, 1.0)`.
- `average()` returns an `OptionalDouble`, because an empty stream has no average.

A stream created from a generator can be used with a Stream API pipeline. However, a stream of numbers and a stream of **generator instances** are two distinct concepts: `ints()` produces integers, whereas `rngs()`/`splits()` on specialized interfaces produce new generators.

## 3. RandomGeneratorFactory: Creating Multiple Generators of the Same Algorithm

### 3.1. Obtaining a Factory with `of(String name)`

`RandomGeneratorFactory<T>` is the factory class for a specific algorithm. Example:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class FactoryQuickStart {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create();
        RandomGenerator second = factory.create();

        System.out.println(first.nextInt(1, 101));
        System.out.println(second.nextInt(1, 101));
    }
}
~~~

A factory is not a generator holding sequence state. It is an object that describes and instantiates **a kind of generator**. Each call to `create()` creates a new instance of the chosen algorithm.

This is useful when:

- An application needs multiple generators of the same algorithm.
- Each worker/thread needs its own instance.
- Seeded generators are needed for reproducible testing.
- Metadata needs to be inspected before selecting an algorithm.
- You want to change the algorithm in configuration without modifying logic that uses `RandomGenerator`.

### 3.2. Three Ways a Factory Creates Instances

Java 17 provides three overloads:

| Creation Method | Meaning |
|---|---|
| `factory.create()` | Creates a generator with no-argument initialization, using the implementation's seeding mechanism |
| `factory.create(long seed)` | Requests creating a generator from a `long` seed |
| `factory.create(byte[] seed)` | Requests creating a generator from a `byte[]` seed |

Example:

~~~java
RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.of("L64X128MixRandom");

RandomGenerator randomA = factory.create();
RandomGenerator randomB = factory.create(20261115L);
RandomGenerator randomC = factory.create(
        new byte[] { 10, 20, 30, 40, 50, 60, 70, 80 }
);
~~~

Not every algorithm supports every form of seed. Under the API contract, if an algorithm does not support a `long` seed or `byte[]` seed, `create(seed)` may fall back to the behavior of `create()`. Therefore, **do not assume that passing a seed always produces a reproducible sequence**.

For deterministic PRNG algorithms that support seeding (such as an explicitly chosen LXM algorithm), the same algorithm, same seed, and same sequence of calls will produce a reproducible sequence within the same implementation contract. If you need bit-for-bit results long-term across environments, fix the algorithm, runtime/provider version, and call sequence; do not rely on a default choice that may change.

### 3.3. Comparing `RandomGenerator.of` and `RandomGeneratorFactory.of`

| Criterion | `RandomGenerator.of(name)` | `RandomGeneratorFactory.of(name)` |
|---|---|---|
| Return value | A `RandomGenerator` | A `RandomGeneratorFactory` |
| Instance creation | Creates one instance immediately | Call `create()` or `create(seed)` |
| Specifying a seed | No seed parameter | Has `long` and `byte[]` overloads |
| Creating multiple instances | Call `of(name)` again | Reuse the factory and call `create` multiple times |
| Reading algorithm metadata | Not directly via a factory | Has `name()`, `group()`, `period()`, `stateBits()`, etc. |
| Discovering algorithms by properties | No | Combine `all()` with metadata |
| When to use | Need a quick generator with simple code | Need configuration, seeds, multiple instances, or algorithm selection |

A practical rule: if you only need one generator inside a method, `RandomGenerator.of` is usually enough. If the application needs seeding, algorithm configuration, or managing multiple generators, use `RandomGeneratorFactory`.

## 4. Listing Available Algorithms with `RandomGeneratorFactory.all()`

### 4.1. The `all()` API

`RandomGeneratorFactory.all()` returns a stream of available factories. This is the right way to discover which algorithms the current runtime provides:

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

Exact results depend on the running JDK/provider. `all()` returns available factories and **excludes generators marked deprecated**. A specific JDK implementation or provider may include additional algorithms beyond Java SE's mandatory list.

Do not hardcode a guessed list and treat it as complete. If a program allows configuring the algorithm, validate the name via the factory and handle errors explicitly.

### 4.2. Algorithm Groups Provided in Java SE 17

The Java SE 17 documentation describes three main algorithm groups:

| Group | Example Names | General Characteristics |
|---|---|---|
| Legacy | `Random`, `SplittableRandom`, `ThreadLocalRandom` | APIs/implementations existing before Java 17; remain usable through appropriate contracts |
| LXM | `L64X128MixRandom`, `L64X256MixRandom`, `L128X256MixRandom` | Combines a Linear Congruential Generator (LCG), an Xor-Based Generator (XBG), and a mixing function |
| Xoroshiro/Xoshiro | `Xoroshiro128PlusPlus`, `Xoshiro256PlusPlus` | XBG algorithm family with large state and period, supporting jump/leap depending on implementation |

Algorithm names mandated by Java SE 17 can be found in the `java.util.random` package documentation. Other LXM names include:

- `L32X64MixRandom`
- `L64X128StarStarRandom`
- `L64X1024MixRandom`
- `L128X128MixRandom`
- `L128X1024MixRandom`

The algorithm list and deprecation status may change in future Java versions. Therefore, when writing applications intended to run across multiple JDKs/providers, use `all()` or handle `IllegalArgumentException` when calling `of(name)`.

**Important exception:** `ThreadLocalRandom` is part of the `RandomGenerator` ecosystem, but should only be accessed via `ThreadLocalRandom.current()`; do not treat it like an ordinary algorithm whose instances can be freely created via constructor/factory.

### 4.3. Choosing an Algorithm by Goal

There is no single best algorithm for all situations. Properties commonly considered include:

- Generation speed.
- State size and memory footprint.
- Period.
- Equidistribution of consecutive tuples.
- Split or jump capabilities for organizing multiple threads.
- Suitability for the workload and statistical requirements.

For applications without special requirements, the Java 17 documentation suggests `L64X128MixRandom` as a balanced choice across speed, space, and period. For single-threaded applications needing small state and high speed, `Xoroshiro128PlusPlus` may fit. For many dynamically spawned tasks, splittable LXM algorithms such as `L64X128MixRandom` or `L64X256MixRandom` are worth considering.

These are selection guidelines by workload type, not benchmark guarantees for every machine. Measure on your actual workload if performance is a critical criterion.

## 5. Using Seeds to Reproduce Number Sequences

### 5.1. What Is a Seed?

For a deterministic PRNG, the seed is the data that initializes its starting state. From that state, the algorithm computes the subsequent sequence of values.

Example:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SeededGenerator {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of("L64X128MixRandom");

        RandomGenerator first = factory.create(123456789L);
        RandomGenerator second = factory.create(123456789L);

        for (int i = 0; i < 5; i++) {
            System.out.println(
                    first.nextInt() + " | " + second.nextInt()
            );
        }
    }
}
~~~

Both generators are initialized with the same LXM algorithm and the same seed. When they receive the same call sequence, corresponding values are generated along the same pseudo-random sequence of the implementation.

### 5.2. When Is a Fixed Seed Needed?

Fixed seeds are useful when:

- Reproducing a bug that occurred during a simulation run.
- Making test data repeatable.
- Comparing two algorithm versions on the same input.
- Debugging a rare situation in a game or simulation.
- Recording experiment parameters so another team can rerun it.

In testing systems, record the seed together with the algorithm, JDK version, and relevant configuration. Saving only the seed without saving the algorithm name may not be enough to reproduce the sequence.

### 5.3. Same Seed Does Not Mean Every Call Returns the Same Result

Generator state changes after producing a value. If two pieces of code call methods in different orders, they consume the sequence differently:

~~~java
RandomGenerator a =
        RandomGeneratorFactory.of("L64X128MixRandom").create(42L);
RandomGenerator b =
        RandomGeneratorFactory.of("L64X128MixRandom").create(42L);

int a1 = a.nextInt();
int a2 = a.nextInt();

int b1 = b.nextInt();
double extra = b.nextDouble(); // consumes state before the next call
int b2 = b.nextInt();
~~~

`a1` and `b1` correspond to the same position in the sequence. However, `a2` and `b2` are no longer at the same position because generator `b` had an extra `nextDouble()` call.

A seemingly minor change such as adding a random call in logging, a conditional branch, or a helper can alter all subsequent results. If experiments must be reproducible, control random consumption order and avoid sharing one generator across unrelated parts of logic.

### 5.4. Do Not Treat Seeds as a Security Mechanism

A fixed seed enables reproducibility, while also making the sequence predictable to anyone who knows the algorithm and seed. Do not use fixed seeds, timestamps, order IDs, or public data as the source for security tokens.

For verification codes, session secrets, reset tokens, or keys, use `SecureRandom` and manage entropy according to security requirements. `RandomGenerator` is a common interface, **not a guarantee of cryptographic security**.

## 6. Reading Algorithm Metadata

`RandomGeneratorFactory` does more than create instances. It also provides information to help evaluate algorithms.

| Method | Meaning |
|---|---|
| `name()` | Algorithm name |
| `group()` | Algorithm group |
| `stateBits()` | Number of bits used by the algorithm to maintain state |
| `period()` | Period of the algorithm, returned as `BigInteger`; may be zero if unknown |
| `equidistribution()` | Documented equidistribution level of the algorithm |
| `isStatistical()` | Generator is computed arithmetically and is statistically deterministic |
| `isStochastic()` | Generator uses an external/entropy source as input |
| `isHardware()` | Generator uses hardware devices to produce entropy |
| `isSplittable()` | Can create separate generators via the split mechanism |
| `isJumpable()` | Can jump ahead in the period via the jump mechanism |
| `isLeapable()` | Capable of leaping farther than jumping |
| `isArbitrarilyJumpable()` | Can jump by a user-specified distance |
| `isStreamable()` | Can create a stream of generators |
| `isDeprecated()` | Whether the algorithm has been marked deprecated |

### 6.1. Distinguishing State Bits, Period, and Equidistribution

These three metrics are not synonymous:

- **State bits** is the number of bits used to maintain state. More state bits usually allow a larger state space, but do not suffice to conclude algorithm quality.
- **Period** is the number of states / cycle length before the sequence repeats. Because this number can be enormous, the API returns `BigInteger`.
- **Equidistribution** describes the uniform distribution property of consecutive tuples across a certain number of dimensions. For instance, a 4-equidistributed generator has a proven property regarding tuples of four consecutive values according to the algorithm's definition.

Do not pick a generator based on a single number. A very long period does not automatically prove an algorithm fits statistical requirements, and large state bits do not automatically imply high speed.

### 6.2. Printing Metadata for Inspection

~~~java
import java.util.random.RandomGeneratorFactory;

public class GeneratorMetadata {
    public static void main(String[] args) {
        RandomGeneratorFactory.all()
                .filter(factory -> factory.isSplittable())
                .sorted((left, right) ->
                        left.name().compareTo(right.name()))
                .forEach(factory -> {
                    System.out.println("Name: " + factory.name());
                    System.out.println("Group: " + factory.group());
                    System.out.println("State bits: " + factory.stateBits());
                    System.out.println("Period: " + factory.period());
                    System.out.println(
                            "Equidistribution: " +
                                    factory.equidistribution()
                    );
                    System.out.println();
                });
    }
}
~~~

This example filters splittable factories and prints several properties. The actual list depends on the factories available in the runtime.

## 7. Selecting a Factory by Properties Instead of Hardcoding Names

### 7.1. Selecting the Generator with the Largest Period Among Splittable Ones

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class SelectByPeriod {
    public static void main(String[] args) {
        RandomGeneratorFactory<RandomGenerator> selected =
                RandomGeneratorFactory.all()
                        .filter(factory -> factory.isSplittable())
                        .max((left, right) ->
                                left.period().compareTo(right.period()))
                        .orElseThrow(() ->
                                new IllegalStateException(
                                        "No splittable generator available"
                                ));

        System.out.println("Selected: " + selected.name());
        System.out.println("Period: " + selected.period());

        RandomGenerator random = selected.create();
        System.out.println(random.nextLong());
    }
}
~~~

`max` compares the `BigInteger` returned by `period()`. This is an example illustrating metadata-based selection; in a real application, define requirements first—such as needing splittability, minimum period, or appropriate equidistribution.

If a factory has `period() == BigInteger.ZERO`, it means the period is unknown according to the API. Do not interpret zero as a period of length zero or treat it as the shortest period in an algorithmic sense.

### 7.2. Selecting by Capability

Suppose you want a generator for a workload with many dynamically created tasks:

~~~java
RandomGeneratorFactory<RandomGenerator> selected =
        RandomGeneratorFactory.all()
                .filter(RandomGeneratorFactory::isSplittable)
                .filter(factory -> factory.stateBits() >= 128)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException(
                                "No matching generator found"
                        ));
~~~

The condition `stateBits() >= 128` here is only an example configuration criterion, not a universal optimal threshold. Determine the capabilities actually needed and verify the selected algorithm on the target JDK/provider.

### 7.3. Validating a Factory Before Creation

`of(name)` throws `IllegalArgumentException` when no matching algorithm exists:

~~~java
static RandomGeneratorFactory<RandomGenerator> findFactory(
        String algorithmName
) {
    try {
        return RandomGeneratorFactory.of(algorithmName);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException(
                "RNG algorithm unavailable: " + algorithmName,
                ex
        );
    }
}
~~~

If the algorithm name comes from a configuration file, admin API, or environment variable, validate it at application startup so configuration errors are caught early.

Do not catch a generic `RuntimeException` and silently switch to an arbitrary algorithm. Falling back can alter reproducibility, statistical properties, or operational requirements.

## 8. Choosing LXM Algorithms in General Applications

### 8.1. LXM Naming Structure

Names like:

```text
L64X128MixRandom
L64X256MixRandom
L128X128MixRandom
```

reflect the main parameters of the algorithm:

- `L` is the Linear Congruential Generator (LCG) component.
- `X` is the Xor-Based Generator (XBG) component.
- The number after `L` indicates the number of state bits in the LCG subgenerator.
- The number after `X` indicates the number of state bits in the XBG subgenerator.
- `Mix` indicates the use of a mixing function; `StarStar` indicates the corresponding scrambler.

LXM combines the states of two subgenerators to produce output and update state. The goal is to improve statistical quality, period, and scalability compared to relying on a single simple LCG.

### 8.2. Workload-Based Suggestions

| Workload | Algorithms/Groups to Consider | Reason |
|---|---|---|
| General-purpose application, no special requirements | `L64X128MixRandom` | Balances speed, memory, and period according to Java 17 docs |
| Single-threaded, needing small footprint and high speed | `Xoroshiro128PlusPlus` | Small state and high speed in algorithm selection guidance |
| 32-bit hardware environment, one or few threads | `L32X64MixRandom` | State configuration better suited to this environment |
| Multiple predetermined threads | Jumpable or splittable generators | Provides mechanisms to separate generator regions/instances |
| Many dynamically created tasks | Splittable LXM such as `L64X128MixRandom` | Can split to create child generators |
| Creating very many generators, millions of instances | Consider LXM with a 128-bit LCG subgenerator like `L128X128MixRandom` | Reduces the chance of multiple instances sharing the same state cycle |
| Generating consecutive tuples requiring equidistribution | Select by `equidistribution()` value | Needs distribution properties matching tuple dimension |
| Cryptography, tokens, secrets | `SecureRandom` | Requires a generator with cryptographic security properties |

These are initial selection guidelines and do not replace statistical testing, performance measurement, or security review against application requirements.

## 9. Generators in Multithreaded Environments

### 9.1. Do Not Assume an Instance Is Thread-Safe

Objects implementing `RandomGenerator` **are not required to be thread-safe**. Many implementations are not designed for multiple threads calling the same instance concurrently.

Do not blindly write:

~~~java
private static final RandomGenerator RANDOM =
        RandomGenerator.of("L64X128MixRandom");

// Multiple threads calling RANDOM.nextInt() simultaneously without a strategy.
~~~

Common approaches:

- Give each thread its own generator.
- Use a splittable generator to create child instances.
- For jumpable/leapable generators, partition period regions according to an appropriate model.
- Use `ThreadLocalRandom.current()` in cases suited to that API.

### 9.2. SplittableGenerator

`RandomGenerator.SplittableGenerator` is a sub-interface for generators capable of **splitting** into other generators. New instances are split from the source instance; the goal is for generated sequences to have approximate statistical independence per the algorithm's design.

Several LXM generators implement this interface, such as `L64X128MixRandom`.

~~~java
import java.util.random.RandomGenerator;

public class SplitExample {
    public static void main(String[] args) {
        RandomGenerator generator =
                RandomGenerator.of("L64X128MixRandom");

        if (!(generator instanceof
                RandomGenerator.SplittableGenerator root)) {
            throw new IllegalStateException(
                    "Generator does not support split"
            );
        }

        RandomGenerator workerA = root.split();
        RandomGenerator workerB = root.split();

        System.out.println(workerA.nextInt());
        System.out.println(workerB.nextInt());
    }
}
~~~

Checking with `instanceof` keeps code from assuming every selected algorithm is splittable. If the algorithm name is a known constant and documentation guarantees the capability, the configuration can be designed more specifically.

### 9.3. Creating a Stream of Child Generators

Because `SplittableGenerator` is also a `StreamableGenerator`, you can create multiple generators:

~~~java
import java.util.random.RandomGenerator;

public class SplitStreamExample {
    public static void main(String[] args) {
        RandomGenerator candidate =
                RandomGenerator.of("L64X128MixRandom");

        if (!(candidate instanceof
                RandomGenerator.SplittableGenerator root)) {
            throw new IllegalStateException("Splittable generator required");
        }

        long[] totals = root.splits(4)
                .parallel()
                .mapToLong(workerRandom ->
                        workerRandom.ints(1_000, 0, 100).sum())
                .toArray();

        for (long total : totals) {
            System.out.println(total);
        }
    }
}
~~~

Each task receives its own generator; no single generator instance is called concurrently by multiple workers. This pattern fits work that can be divided into independent parts, such as Monte Carlo simulations.

Do not mistakenly think split guarantees absolute mathematical independence in every situation. The API speaks in terms of expected statistical independence; actual quality depends on the algorithm and usage.

### 9.4. Jumpable and Leapable

Some algorithms provide these capabilities:

- **JumpableGenerator:** jumps ahead to a farther position in the period, typically by a large algorithm-defined distance.
- **LeapableGenerator:** capable of leaping farther than a jump.
- **ArbitrarilyJumpableGenerator:** allows jumping by a user-specified distance.

These capabilities are useful when partitioning a sequence into separate regions for a predetermined number of workers. They differ from `split()`: jump/leap advances position along an algorithm's period, whereas split creates new instances according to the generator's mechanism.

Check `factory.isJumpable()`, `isLeapable()`, and `isArbitrarilyJumpable()` before relying on the capability. Do not cast an arbitrary generator to a sub-interface without verifying the implementation.

## 10. Seeding and Reproducibility in Real Systems

### 10.1. Recording Generator Configuration

When running an experiment or simulation that needs reproducibility, you can record:

~~~text
algorithm = L64X128MixRandom
seed = 20261115
jdk = 17
call-sequence-version = simulation-v3
~~~

This information is far more useful than saving only a seed value. If you change the algorithm while keeping the same seed, the sequence will differ. If you insert a random call in the middle of a pipeline, subsequent values will also change.

### 10.2. Do Not Confuse `getDefault()` with Fixed Algorithm Selection

There are two default APIs:

~~~java
RandomGenerator random = RandomGenerator.getDefault();

RandomGeneratorFactory<RandomGenerator> factory =
        RandomGeneratorFactory.getDefault();
RandomGenerator another = factory.create();
~~~

`getDefault()` selects a generator meeting a minimum state-bit requirement (at least 64). The documentation explicitly states **there is no guarantee the method returns the same algorithm across Java versions** because algorithms may be improved.

Therefore:

- Use the default when there is no requirement tied to a specific algorithm name.
- Specify an explicit name with `of(name)` when algorithm control is needed.
- Use `create(seed)` with a seed-supporting algorithm if reproducibility is required.
- Do not record default generator output into a golden file and assume all future JDKs will produce the exact same sequence.

### 10.3. Creating a Generator from Configuration

Example:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class ConfiguredRandom {
    static RandomGenerator create(String algorithm, long seed) {
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(algorithm);
        return factory.create(seed);
    }

    public static void main(String[] args) {
        String algorithm = "L64X128MixRandom";
        long seed = 12345L;

        RandomGenerator random = create(algorithm, seed);
        System.out.println(random.nextLong());
    }
}
~~~

In real applications, validate `algorithm` when loading configuration and report clearly if the algorithm is unavailable in the runtime. If the seed is input data, define its source, access permissions, and storage; a testing seed should not be confused with a security secret.

## 11. Distinguishing Standard PRNGs from SecureRandom

### 11.1. RandomGenerator Does Not Mean Cryptographically Secure

`RandomGenerator` is a general-purpose interface. Many implementations are designed for statistical quality, performance, period, and splittability, not to resist an adversary able to observe or predict outputs.

Uses typically suited to standard PRNGs:

- Generating sample data.
- Simulations and games.
- Randomizing test order.
- Monte Carlo methods and statistics.
- Generating numbers for algorithms with no security requirements.

Uses requiring `SecureRandom`:

- Password reset tokens.
- Session IDs or bearer tokens.
- Nonces, challenges, salts, or key material subject to security requirements.
- Values that attackers must not be able to predict.

### 11.2. Using SecureRandom When Security Is Required

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public class SecureTokenExample {
    public static void main(String[] args) {
        SecureRandom secureRandom = new SecureRandom();

        byte[] tokenBytes = new byte[32];
        secureRandom.nextBytes(tokenBytes);

        String token = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(tokenBytes);

        System.out.println(token);
    }
}
~~~

`SecureRandom` also implements `RandomGenerator`, but picking an LXM or Xoshiro algorithm does not satisfy cryptographic security requirements. Use `SecureRandom` and follow platform/provider guidance for security use cases.

Do not manually seed `SecureRandom` with a timestamp or predictable value. Nor should you carry fixed test seeds into production just to make output repeatable.

## 12. Common Mistakes When Using RandomGeneratorFactory

| Mistake | Consequence | Resolution |
|---|---|---|
| Misspelling the algorithm name | `of(name)` throws `IllegalArgumentException` | Use the exact name, verify with `all()` |
| Passing a null name | `NullPointerException` | Validate configuration before calling the factory |
| Using `RandomGenerator.of` expecting to pass a seed | The API has no seed overload | Use `RandomGeneratorFactory.create(seed)` |
| Assuming every factory supports `long`/`byte[]` seeds | May fall back to `create()`, not producing the expected seeded sequence | Check algorithm docs; choose an algorithm with appropriate seed support |
| Sharing one instance across multiple threads | Race conditions or unpredictable results if the implementation is not thread-safe | Use separate instances, split, or jump |
| Creating multiple workers with the same seed | Deterministic generators may emit the same sequence | Use split or distinct seed/state allocation strategies |
| Using the default expecting a fixed algorithm | Default may change across versions | Choose an explicit algorithm name when stability is needed |
| Picking the generator with the largest period without considering workload | May be suboptimal for speed, memory, or concurrency | Choose based on multiple metadata attributes and real benchmarks |
| Using a statistical PRNG for security tokens | May leak the sequence or allow prediction | Use `SecureRandom` |
| Mistaking a factory for a stateful generator | Calling generation in the wrong place; hard to manage lifecycle | Distinguish factory (creates instances) from generator (holds state and produces numbers) |
| Assuming `all()` always has the exact same list on every JDK | Missing providers or changed algorithms | Discover at runtime, handle unavailable names |

## 13. Comprehensive Example: Configuring a Generator, Seeding, and Inspecting Metadata

Save the code into **`RandomGeneratorFactoryDemo.java`**:

~~~java
import java.util.random.RandomGenerator;
import java.util.random.RandomGeneratorFactory;

public class RandomGeneratorFactoryDemo {

    private static final String ALGORITHM = "L64X128MixRandom";
    private static final long SEED = 20261115L;

    public static void main(String[] args) {
        // 1. Obtain the factory by algorithm name.
        RandomGeneratorFactory<RandomGenerator> factory =
                RandomGeneratorFactory.of(ALGORITHM);

        // 2. Inspect metadata before creating the generator.
        System.out.println("Algorithm: " + factory.name());
        System.out.println("Group: " + factory.group());
        System.out.println("State bits: " + factory.stateBits());
        System.out.println("Period: " + factory.period());
        System.out.println("Splittable: " + factory.isSplittable());

        // 3. Create a generator from a fixed seed.
        RandomGenerator random = factory.create(SEED);

        // 4. Generate values within defined domains.
        int dice = random.nextInt(1, 7);
        double probability = random.nextDouble(0.0, 1.0);
        long sampleId = random.nextLong(10_000L, 20_000L);

        System.out.println("Dice: " + dice);
        System.out.println("Probability: " + probability);
        System.out.println("Sample ID: " + sampleId);

        // 5. Create a numeric stream for statistics.
        double average = random.doubles(1_000, 0.0, 1.0)
                .average()
                .orElseThrow();
        System.out.println("Average: " + average);
    }
}
~~~

Compile with JDK 17:

~~~shell
java -version
javac --release 17 RandomGeneratorFactoryDemo.java
java RandomGeneratorFactoryDemo
~~~

The algorithm name is chosen explicitly so metadata and configuration can be cross-checked. If run again with the same JDK, same algorithm, same seed, and same call sequence, PRNG results are reproducible per the implementation. Statistical values like the average will reflect the exact sequence generated.

## 14. Practice Exercises

### Exercise 1 — Creating a Generator by Name

Write a program using:

~~~java
RandomGenerator random =
        RandomGenerator.of("L64X128MixRandom");
~~~

Generate 20 integers in `[1, 101)`. Explain why the upper bound 101 never appears and what happens if the algorithm name does not exist.

### Exercise 2 — Creating a Factory and Reproducing with a Seed

Create two generators using the same factory and the same seed. Generate 10 values from each generator in the same order and compare them. Then insert a `nextDouble()` call in the middle of the second generator's sequence; observe how subsequent values change.

### Exercise 3 — Discovering Available Factories

Use `RandomGeneratorFactory.all()` to print:

- Name and group.
- State bits and period.
- Whether it is splittable or jumpable.
- Equidistribution.

Filter splittable factories and explain why the list may differ across runtimes/providers.

### Exercise 4 — Selecting by Metadata

Find factories with `isSplittable() == true`, then choose the factory with the largest period in that group. Print its name and period. Explain why choosing only the largest period is not enough to conclude it is the best choice for an application.

### Exercise 5 — Creating Child Generators

Create `L64X128MixRandom`, verify the instance supports `RandomGenerator.SplittableGenerator`, call `split()` twice, and generate values from each child generator. Explain why you should not use the same generator instance across multiple workers.

### Exercise 6 — Distinguishing Default vs. Fixed Algorithm

Compare:

~~~java
RandomGenerator.getDefault();
RandomGenerator.of("L64X128MixRandom");
~~~

Explain when the default is sufficient, when an explicit algorithm name is needed, and why you should not rely on the default's output sequence across all Java versions.

### Exercise 7 — Choosing a PRNG vs. SecureRandom

For each scenario, decide the generator type:

1. Simulating one million dice rolls.
2. Generating fake data for integration tests.
3. Creating a password reset token.
4. Running a parallel Monte Carlo simulation.
5. Generating an unpredictable session identifier.

Clearly explain the statistical, performance, reproducibility, and security requirements of each scenario.

## 15. Self-Check Questions

1. What common contract does `RandomGenerator` provide?
2. What is the difference between `RandomGenerator.of(name)` and `RandomGeneratorFactory.of(name)`?
3. What `create` overloads does a factory have?
4. Why does `create(seed)` not always guarantee that the seed is used?
5. What does `all()` return, and does it include deprecated generators?
6. Does `getDefault()` guarantee the same algorithm across JDK versions?
7. What do `stateBits`, `period`, and `equidistribution` describe?
8. Which components does the LXM algorithm group combine?
9. Why is `L64X128MixRandom` often a reasonable starting choice for general applications?
10. How do splittable, jumpable, and leapable differ?
11. Why should many `RandomGenerator` implementations not be shared concurrently across threads?
12. How do you create separate generators for parallel tasks?
13. How can the same seed with different method call orders produce different subsequent results?
14. When must `SecureRandom` be used instead of LXM or Xoshiro?

## 16. Official References

- [Java SE 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): value generation contract, streams, and specialized sub-interfaces.
- [Java SE 17 API — RandomGeneratorFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGeneratorFactory.html): `of`, `all`, `getDefault`, `create`, and algorithm metadata.
- [Java SE 17 — java.util.random package summary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): algorithm groups, generator list, workload-based selection, and multithreading model.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): goals of unifying the API and adding PRNG types in Java 17.
- [Oracle Java 17 Core Libraries — Pseudorandom Number Generators](https://docs.oracle.com/en/java/javase/17/core/pseudorandom-number-generators.html): usage guide, algorithm selection, seeding, and multithreading.
- [Java SE 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): API for cryptographically secure pseudo-random number generation requirements.

When building generators in Java 17, choose an **algorithm name** when explicit control is needed, use a **factory** when creating multiple instances, seeding, or reading properties, and use **capabilities** such as split/jump when designing parallel processing. Most importantly, pick the right kind of generator for the goal: standard PRNGs serve simulation/statistics, while data that must resist prediction must rely on `SecureRandom`.
