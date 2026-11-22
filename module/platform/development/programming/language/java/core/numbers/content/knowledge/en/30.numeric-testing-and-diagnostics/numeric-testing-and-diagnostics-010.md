# Testing Random Numbers Using Seeds or Injected Sources in Java

## 1. Why Is Code with Randomness Hard to Test?

A feature using random numbers might pick an element, simulate dice, sample telemetry, decide an A/B branch, generate test data, or add *jitter* latency. If every test run creates a fresh random source, a test can pass many times and then fail in CI even without code changes. This is called a **flaky test**: unstable results caused by tests depending on uncontrolled data.

Hard-to-test example:

~~~java
public static int rollDie() {
    return new java.util.Random().nextInt(6) + 1;
}
~~~

Each call creates a new `Random` object and generates an arbitrary value from 1 to 6. Writing `assertEquals(4, rollDie())` has no basis: 4 is only one possible outcome.

Two essential techniques:

1. **Fixing the seed** of a pseudo-random number generator (PRNG) so the sequence repeats given the same algorithm, seed, and call order.
2. **Injecting the random number source from outside** (*dependency injection*) so business code does not create the source itself; tests can provide a fixed-seed PRNG or a fake source with predetermined results.

This lesson covers **test design and diagnostics**, not how to generate random numbers for security. For tokens, passwords, cryptographic keys, or security nonces, you must use `SecureRandom` and dedicated rules (see section 9).

## 2. From Seed to Reproducibility

`java.util.Random` is a PRNG. It produces a sequence of values from internal state, so two independent `Random` instances with the same seed produce the same sequence if called with the same methods in the same order.

~~~java
import java.util.Random;

Random first = new Random(2026L);
Random second = new Random(2026L);

System.out.println(first.nextInt(10) == second.nextInt(10)); // true
System.out.println(first.nextInt(10) == second.nextInt(10)); // true
~~~

Here seed `2026L` does not make the two objects share state; it initializes equivalent states. Two sequential calls yield two matching pairs of values. You do not need to memorize specific numbers to understand the mechanism.

Conditions for useful reproducibility:

- Same **algorithm**: `Random`, `SplittableRandom`, or an algorithm from `RandomGeneratorFactory` do not necessarily produce the same sequence even with the same seed.
- Same **seed**, call count, and invoked methods: adding one extra `nextInt()` call before the step under test shifts all subsequent values.
- Same value distribution: `nextInt(6)` and `nextInt()` do not mean the same thing.
- No multiple threads competing to call the same source in non-deterministic order.

Seeds are a very helpful bug-reproduction tool: record the seed along with algorithm name, test configuration, and input data. If a test case fails on a specific seed, re-running with that exact information helps investigate.

**Do not equate reproducibility with business predictability.** A fixed seed helps repeat a sequence, yet a test overly coupled to “the 37th call must return 6” easily breaks whenever code adds one valid random draw.

## 3. Java 17+: Passing `RandomGenerator` into Business Logic

Java 17 provides the `java.util.random.RandomGenerator` interface. `java.util.Random` is one implementation of this interface; thus you can accept the dependency via the interface while the caller decides which implementation to supply.

Example:

~~~java
import java.util.Objects;
import java.util.random.RandomGenerator;

public final class Dice {
    private final RandomGenerator random;

    public Dice(RandomGenerator random) {
        this.random = Objects.requireNonNull(random, "random");
    }

    public int roll() {
        return random.nextInt(6) + 1;
    }
}
~~~

This is a standalone illustrative class; section 7 contains a complete Java program with multiple tests. `random.nextInt(6)` returns an `int` in **0 to 5**; adding 1 yields **1 to 6**. Using the bounded overload avoids manual modulo tricks that can easily cause biased distributions or negative numbers.

Benefits of dependency injection:

- Production can supply a PRNG source chosen by application policy.
- Unit tests can supply a `Random` with a fixed seed to replay a sequence.
- Unit tests targeting a specific branch can supply a *fake* source returning exact chosen values.
- The business class expresses only how random numbers are used, without deciding how seeds are initialized or needing to know the algorithm.

Usage example:

~~~java
// Example within method scope:
Dice productionDice = new Dice(new java.util.Random());
Dice repeatableDice = new Dice(new java.util.Random(2026L));
~~~

You can use `RandomGenerator.getDefault()` when application policy accepts the default algorithm. If stable reproducibility across environments is needed, **explicitly specify the implementation/algorithm and seed**; an environment's default is not a fixed sequence contract.

Many applications also need to inject a *factory* that creates an RNG per session or per worker rather than one shared instance. This decision is especially important when multiple threads are involved and consumption order must be reproducible.

## 4. Seed-Based Testing: What Should Be Asserted?

### Checking That the Same Seed Produces the Same Sequence

A reasonable test compares two independent instances using the same seed and same number of steps:

~~~java
import java.util.Arrays;
import java.util.Random;

Random a = new Random(2026L);
Random b = new Random(2026L);

int[] sequenceA = new int[10];
int[] sequenceB = new int[10];

for (int i = 0; i < sequenceA.length; i++) {
    sequenceA[i] = a.nextInt(100);
    sequenceB[i] = b.nextInt(100);
}

System.out.println(Arrays.equals(sequenceA, sequenceB)); // true
~~~

The test proves reproducibility for the same algorithm and call sequence. To test **business logic**, assert the business conditions you actually care about rather than only testing the JDK's PRNG.

For example, with `Dice`, you can run many iterations and assert `1 <= roll && roll <= 6`. Trying 10,000 times increases the chance of catching bound or transformation bugs, though it still does not prove a completely uniform distribution.

### Reproducing a Bug by Seed

Suppose a pipeline fails on seed `58723L`. Record:

~~~text
generator: java.util.Random
seed: 58723
scenario: choose promotion after reading customer category
input fixture: customer-group-A
~~~

Seed information **alone** may be insufficient if the algorithm, call order, or dataset changed. A reliable reproduction fixture records both the drawing rules and test conditions.

Do not hard-code a fixed seed in production systems when the goal is unpredictable behavior. Fixed seeds are for testing, reproducible simulations, or business features that explicitly require a pseudo-random sequence.

### Limitations of Seeded Tests

Seed-only tests might fail to hit a needed case, such as drawing exactly 0 or the maximum boundary value. “Run 1,000 times and hope to hit that condition” creates hard-to-read tests with flakiness risk. To test a specific branch, inject a fake source with controlled outputs.

## 5. Testing with Injected Sources: Creating a Scripted Fake

Suppose an application has:

~~~java
boolean shouldSample(int percent) {
    return random.nextInt(100) < percent;
}
~~~

With `percent = 0`, the result is always `false`; with `percent = 100`, always `true`; with `percent = 25`, draws in 0–24 yield `true`, while 25–99 yield `false`.

Instead of guessing which seed produces 24 or 25 at the exact position, a fake can provide an explicit list of values. Because `Random` implements `RandomGenerator`, we can subclass `Random` and override `nextInt(int bound)` for the case under test:

~~~java
import java.util.Random;

final class ScriptedRandom extends Random {
    private final int[] values;
    private int cursor;

    ScriptedRandom(int... values) {
        super(0L);
        this.values = values.clone();
    }

    @Override
    public int nextInt(int bound) {
        if (bound <= 0) {
            throw new IllegalArgumentException("bound must be positive");
        }
        if (cursor >= values.length) {
            throw new AssertionError("Scripted values exhausted");
        }
        int value = values[cursor++];
        if (value < 0 || value >= bound) {
            throw new AssertionError(
                    "Invalid scripted value " + value
                            + " for bound " + bound);
        }
        return value;
    }

    int calls() {
        return cursor;
    }
}
~~~

This is a **test-only** fake. It validates `bound` to catch production code calling the API with unexpected ranges. It does not simulate all of `Random`'s behavior, must never be used as a production PRNG, and replaces only the exact `nextInt(int)` call that business code actually invokes.

If production code switches to `nextLong()` or another RNG method, the fake must support that call or you can design a narrower domain interface, for example:

~~~java
@FunctionalInterface
interface IndexSource {
    int nextIndex(int exclusiveUpperBound);
}
~~~

In domain design, injecting `IndexSource` is often better if a service only needs to draw indices. Tests can pass the lambda `bound -> 0` to always pick the first element; production passes `random::nextInt`. A narrow interface reduces coupling to the entire RNG API.

**Choose the right level of abstraction:** use `RandomGenerator` when logic needs general RNG operations; use a small domain interface when you want to allow only one or a few business-meaningful random operations.

## 6. Branches to Force with a Fake

Suppose `chooseIndex(int size)` picks an index in `[0, size)` and `shouldSample(int percent)` accepts a percentage from 0 to 100.

| Case | Fake return value | What to assert |
| --- | ---: | --- |
| `chooseIndex(6)` | `0` | Selects first element |
| `chooseIndex(6)` | `5` | Selects last element |
| `shouldSample(25)` | `24` | `true` |
| `shouldSample(25)` | `25` | `false` |
| `shouldSample(0)` | `0` | `false` |
| `shouldSample(100)` | `99` | `true` |
| `chooseIndex(0)` | Source not called | Throws `IllegalArgumentException` before drawing |

With a fake, these tests **do not depend on probability** and produce identical results on every run.

Distinguish **inclusive/exclusive bounds**. For `nextInt(bound)`, `bound` is **exclusive**: `nextInt(6)` cannot return 6. For `RandomGenerator.nextInt(origin, bound)`, `origin` is inclusive and `bound` is exclusive. Avoid hand-rolling `Math.abs(random.nextInt()) % size`: `Math.abs(Integer.MIN_VALUE)` stays negative and modulo can skew the distribution.

## 7. Standalone Runnable Java 17+ Program

Create file `RandomSourceTestingDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;
import java.util.random.RandomGenerator;

public class RandomSourceTestingDemo {

    static final class Picker {
        private final RandomGenerator random;

        Picker(RandomGenerator random) {
            this.random = Objects.requireNonNull(random, "random");
        }

        int chooseIndex(int size) {
            if (size <= 0) {
                throw new IllegalArgumentException("size must be positive");
            }
            return random.nextInt(size);
        }

        int rollDie() {
            return random.nextInt(6) + 1;
        }

        boolean shouldSample(int percent) {
            if (percent < 0 || percent > 100) {
                throw new IllegalArgumentException(
                        "percent must be between 0 and 100");
            }
            return random.nextInt(100) < percent;
        }
    }

    static final class ScriptedRandom extends Random {
        private final int[] values;
        private int cursor;

        ScriptedRandom(int... values) {
            super(0L);
            this.values = values.clone();
        }

        @Override
        public int nextInt(int bound) {
            if (bound <= 0) {
                throw new IllegalArgumentException("Invalid bound");
            }
            if (cursor >= values.length) {
                throw new AssertionError("No more scripted values");
            }
            int value = values[cursor++];
            if (value < 0 || value >= bound) {
                throw new AssertionError("Scripted value outside bound");
            }
            return value;
        }

        int calls() {
            return cursor;
        }
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        // Two PRNGs with the same seed and same call order produce the same sequence.
        Picker first = new Picker(new Random(2026L));
        Picker second = new Picker(new Random(2026L));
        int[] valuesA = new int[5];
        int[] valuesB = new int[5];

        for (int i = 0; i < 5; i++) {
            valuesA[i] = first.chooseIndex(10);
            valuesB[i] = second.chooseIndex(10);
        }

        boolean reproducible = Arrays.equals(valuesA, valuesB);
        require(reproducible, "Seeded sequences must match");
        System.out.println("same seed, same sequence: " + reproducible);

        // Fake forces first, last, and two percentage branches.
        ScriptedRandom scripted = new ScriptedRandom(0, 5, 0, 99);
        Picker predictable = new Picker(scripted);

        int firstIndex = predictable.chooseIndex(6);
        int lastIndex = predictable.chooseIndex(6);
        boolean zeroPercent = predictable.shouldSample(0);
        boolean fullPercent = predictable.shouldSample(100);

        require(firstIndex == 0, "Expected first index");
        require(lastIndex == 5, "Expected last index");
        require(!zeroPercent, "0 percent must be false");
        require(fullPercent, "100 percent must be true");
        require(scripted.calls() == 4, "Wrong number of random draws");

        System.out.println("scripted first index: " + firstIndex);
        System.out.println("scripted last index: " + lastIndex);
        System.out.println("sample at 0%: " + zeroPercent);
        System.out.println("sample at 100%: " + fullPercent);
        System.out.println("scripted calls: " + scripted.calls());

        // Check range invariant without hard-coding the sequence.
        Picker die = new Picker(new Random(7L));
        boolean inRange = true;
        for (int i = 0; i < 10_000; i++) {
            int rolled = die.rollDie();
            if (rolled < 1 || rolled > 6) {
                inRange = false;
                break;
            }
        }
        require(inRange, "A die roll must be between 1 and 6");
        System.out.println("die range verified: " + inRange);
    }
}
~~~

Compile and run:

~~~bash
javac RandomSourceTestingDemo.java
java RandomSourceTestingDemo
~~~

Stdout:

~~~text
same seed, same sequence: true
scripted first index: 0
scripted last index: 5
sample at 0%: false
sample at 100%: true
scripted calls: 4
die range verified: true
~~~

The fake is tested with values `0, 5, 0, 99` corresponding to bounds `6, 6, 100, 100`. Every value lies within the valid range. The test also checks the exact count of RNG consumptions to detect unexpected changes in how the code draws numbers.

Lesson on test structure:

- **Seeded PRNG** tests reproducibility of a sequence across the same algorithm and call order.
- **Scripted fake** tests specific branches and boundary points deterministically.
- **Property/bound test** checks invariants across many samples without requiring one specific random sequence.

All three serve different roles; do not use a single seeded test to replace all branch testing.

## 8. Designing JUnit 5 Unit Tests

For projects using JUnit Jupiter, tests can be structured as follows. This **snippet** assumes `Picker` and `ScriptedRandom` from the program in section 7 are accessible to the test, such as placing the test in the same package or moving them to an appropriate class:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Random;
import org.junit.jupiter.api.Test;

class PickerTest {
    @Test
    void sameSeedReproducesDraws() {
        var a = new RandomSourceTestingDemo.Picker(new Random(42L));
        var b = new RandomSourceTestingDemo.Picker(new Random(42L));
        for (int i = 0; i < 100; i++) {
            assertEquals(a.chooseIndex(1_000), b.chooseIndex(1_000));
        }
    }

    @Test
    void fakeForcesBoundaryBranches() {
        var fake = new RandomSourceTestingDemo.ScriptedRandom(0, 5);
        var picker = new RandomSourceTestingDemo.Picker(fake);
        assertEquals(0, picker.chooseIndex(6));
        assertEquals(5, picker.chooseIndex(6));
        assertEquals(2, fake.calls());
    }

    @Test
    void invalidSizeRejectedBeforeDraw() {
        var fake = new RandomSourceTestingDemo.ScriptedRandom(0);
        var picker = new RandomSourceTestingDemo.Picker(fake);
        assertThrows(IllegalArgumentException.class,
                () -> picker.chooseIndex(0));
        assertEquals(0, fake.calls());
    }

    @Test
    void everyDieResultStaysInsideDomain() {
        var picker = new RandomSourceTestingDemo.Picker(
                new Random(1001L));
        for (int i = 0; i < 10_000; i++) {
            int rolled = picker.rollDie();
            assertTrue(rolled >= 1 && rolled <= 6);
        }
    }
}
~~~

The JUnit snippet above requires the JUnit Jupiter dependency in the build and runs through the project's test runner (Gradle/Maven/IDE). It is **not** a JDK-only program to be run with `java PickerTest`.

If production specifies a different PRNG/algorithm, create an appropriate constructor/factory so tests explicitly select that same implementation. Do not directly compare sequences from two different algorithms merely because they were initialized with the same seed.

## 9. Distinguishing Testing PRNGs from Cryptographic Randomness

`Random`, `SplittableRandom`, and many `RandomGenerator` implementations are **non-cryptographic pseudo-random** sources. Seeds make sequences repeatable and predictable; that is useful for simulation tests yet dangerous for login tokens, random passwords, recovery codes, keys, or values requiring secrecy.

For security purposes, use `java.security.SecureRandom` following security guidelines and an appropriate algorithm/provider:

~~~java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
byte[] token = new byte[32];
secure.nextBytes(token);
~~~

**Do not fix the seed of `SecureRandom` in production** hoping to generate repeatable tokens. `SecureRandom.setSeed(...)` is not an interface guaranteeing “set state to exactly this seed to replay the same sequence” like the simple assumption with `Random`; details depend on the provider and initialization. When testing security-related code, separate token/nonce processing logic from the byte generator: tests can inject scripted bytes **only in test environments** to verify formatting, validation, and error paths; production continues using the secure source.

Never replace `SecureRandom` with `new Random(seed)` just to make testing easier. If the system requires unpredictability, that is an essential functional requirement to preserve.

## 10. Seeds, Shared Sources, and Multiple Threads

A seeded source can generate a deterministic sequence when run sequentially, yet **the same seed does not guarantee the same business outcome if thread consumption order changes**.

For example, multiple threads calling the same `Random`:

- Run 1: thread A draws the 1st value, B draws the 2nd.
- Run 2: B draws the 1st value, A draws the 2nd.

Even if the PRNG produces the same overall sequence, results tied to each thread or record can differ. Contention also hurts performance. APIs like `ThreadLocalRandom.current()` provide per-thread RNGs, yet `ThreadLocalRandom.setSeed(long)` does not support setting a seed for replay in the usual way; it throws `UnsupportedOperationException`.

If a parallel simulation must be stably reproducible, you can:

1. Define a rule assigning seeds based on a stable **work identifier**, e.g., combining task ID with a saved master seed.
2. Create a separate RNG per task/partition from that policy.
3. Ensure each task performs the same draw order or design order-independent draws.
4. If using `SplittableRandom.split()` or a splittable generator, document the splitting rule; changing split order can alter each task's sequence.

Do not assume any arbitrary instance shared across threads is thread-safe: check the contract of the chosen implementation. Even when an implementation supports concurrent calls, **per-task reproducibility** remains a separate concern.

## 11. Test Patterns That Cause Flakiness or Mask Bugs

### Mistake 1: Asserting One Specific Result from an Unseeded Real RNG

~~~java
int x = new Random().nextInt(6) + 1;
// Wrong: assert x == 4. That is only true by chance.
~~~

Replace with an output invariant test or a branch-forcing fake.

### Mistake 2: Unnecessarily Depending on a Fixed Sequence

A test hard-coding 100 PRNG outputs for a feature that only requires values in `[0, 6)` breaks easily when changing algorithms or adding one draw. If you truly need to cross-check a PRNG algorithm, fixed standard sequences can serve as *golden vectors*. For business logic, prefer asserting outcomes and business branches.

### Mistake 3: Creating an RNG Inside a Method Where It Cannot Be Replaced

~~~java
int pick() {
    return new Random().nextInt(10);
}
~~~

There is no simple way to inject a fake into this method. Extract it into a dependency via constructor, method parameter, or factory if lifecycle control is needed.

### Mistake 4: Resetting the Seed Between Calls

~~~java
Random random = new Random(42L);
for (int i = 0; i < 5; i++) {
    random.setSeed(42L); // repeats the initial state
    System.out.println(random.nextInt(10));
}
~~~

Resetting the seed before **every draw** reuses the initial state and can emit the same value repeatedly, unlike a sequence of consecutive draws. Reproducibility tests typically set the seed **once when creating the source for each test**.

### Mistake 5: Sharing an Instance Across Tests

If multiple unit tests share one `static Random`, one test mutates the state read by another. Execution order or parallel execution can alter outcomes. Each test should own its own source (or fixture) with an explicit seed.

### Mistake 6: Using Crude Statistics to “Prove Randomness”

Checking that 10 die rolls must show all 6 faces is a flaky test even with a correct PRNG. Statistical tests require a hypothesis, sample size, and proper error bounds; do not make them mandatory unit tests without analyzing false-positive probability. Testing transformation/bound logic with fakes and dedicated statistical testing are two separate tasks.

## 12. Test Strategy Selection Guide

| Objective | Suitable approach | What to verify |
| --- | --- | --- |
| Reproduce a specific bug | Recorded seed, algorithm, fixture, and draw order | Same context reproduces bug |
| Hit first/last branches | Scripted fake | Code handles `0` and `bound - 1` properly |
| Guarantee output in range | Invariant/property check | Never exits value domain |
| Test distribution | Dedicated statistical test with grounded thresholds | Deviation within set bounds |
| Test concurrency | Per-task RNG/seed and deterministic scheduling | Correctness independent of schedule |
| Test security flow | Inject fake bytes at logic boundary, production uses `SecureRandom` | Formatting, error handling, and security rules |

You do not have to force every application component to accept the full `RandomGenerator` interface when it needs only a narrow decision. You can inject a dedicated domain interface such as `IndexSource` or `BooleanDecision` to keep unit tests concise and reduce coupling to PRNG details.

## 13. Self-Check

**Question 1.** Are two `new Random(123L)` instances guaranteed to return the same values over 20 `nextInt(10)` calls when invoked in the same order? What if one instance has an extra `nextLong()` call before the 10th draw?

**Question 2.** Why should you not test `rollDie() == 6` by calling it 10 times and hoping for 6? Give a proactive way to test the 6 branch.

**Question 3.** A method decides sampling using `random.nextInt(100) < 25`. What values must the fake return to test both sides of the boundary?

**Question 4.** Why should multiple tests not share one `static Random`, even when initialized with a fixed seed?

**Question 5.** Why must `SecureRandom` not be replaced by `Random(42L)` in production token generation?

**Question 6.** If one parallel simulation run and the next run share the same master seed yet partition work in a different order, are per-task results guaranteed to be identical?

### Answers

1. Yes, when using the same `java.util.Random`, same seed, and same call sequence. If one source consumes an extra value, subsequent draws no longer align by position.
2. That is testing by luck; provide a fake whose `nextInt(6)` returns 5, then assert `rollDie()` returns 6.
3. The fake returns 24 for the `true` branch and 25 for the `false` branch; both are within `[0,100)`.
4. Each test consumes shared state, so run order and parallel execution affect random inputs.
5. `Random` is a general PRNG and a fixed-seed sequence is predictable, failing security requirements.
6. No. Reproducibility also requires deterministic source/seed assignment, split order, consumption order, and work mapping.

**Key point:** fixed seeds help **replay a sequence**, while dependency injection helps **precisely control business branches**. Combine seeded tests, scripted fakes, and invariant checks to write clear, stable tests; keep them strictly separate from cryptographic randomness requirements.