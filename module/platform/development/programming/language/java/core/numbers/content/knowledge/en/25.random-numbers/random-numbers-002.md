# Random and Seed-Based Value Sequences in Java

## 1. What is a seed and why can the same seed replay the same sequence?

`java.util.Random` is a **pseudorandom number generator** (PRNG). Instead of producing true randomness, the object maintains an **internal state**; each time the program requests the next number, the algorithm updates the state and computes a result. The value used to initialize the state is called the **seed**.

~~~java
Random random = new Random(42L);
int value = random.nextInt(100);
~~~

In this example, `42L` is the seed; `nextInt(100)` generates an integer from **0 (inclusive) to 100 (exclusive)**, meaning from 0 to 99.

Key property:

> With **the same algorithm implementation, the same seed, and the same calls in the same order with the same arguments**, we obtain the exact same result sequence.

This is the foundation for replaying simulations, reproducing bugs, generating test data, and comparing two experiment runs. A fixed seed provides **reproducibility**; it does not make the generated values secret or cryptographically secure.

It is important to distinguish:

- **Seed** is the input used to set up the initial state.
- **Current state** changes as random numbers are consumed. After calling a number-generation method, the object is usually no longer in its initial state.
- **Value sequence** is determined by the seed **and** the sequence of generator usage, not by the seed alone.

## 2. Two Random instances with the same seed: same sequence, no shared state

Consider two independent objects:

~~~java
Random first = new Random(42L);
Random second = new Random(42L);
~~~

If both call `nextInt(100)` five times in a row, the results at each position match:

| Call | `first.nextInt(100)` | `second.nextInt(100)` |
| ---: | ---: | ---: |
| 1 | 30 | 30 |
| 2 | 63 | 63 |
| 3 | 48 | 48 |
| 4 | 84 | 84 |
| 5 | 70 | 70 |

The two objects **are not the same object**: advancing the state of `first` does not automatically advance `second`. They only produce the same sequence when initialized from the same seed and consuming matching calls.

Conversely, if one object has made one extra call, the next read position of the two objects can differ:

~~~text
Random A (seed 42): nextInt(100) -> 30, then -> 63
Random B (seed 42): not called yet -> 30 on the first call
~~~

Therefore, a more accurate question than “is the seed the same?” is: **are the two generators in the same state before the call and using the same methods/arguments?**

## 3. Complete Java 17 example with deterministic output

Create the file `SeededRandomDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class SeededRandomDemo {
    private static List<Integer> generate(long seed, int count) {
        Random random = new Random(seed);
        List<Integer> values = new ArrayList<>();

        for (int i = 0; i < count; i++) {
            values.add(random.nextInt(100));
        }
        return values;
    }

    public static void main(String[] args) {
        List<Integer> first = generate(42L, 5);
        List<Integer> replay = generate(42L, 5);

        System.out.println("Seed 42: " + first);
        System.out.println("Replay identical: " + first.equals(replay));

        Random random = new Random(42L);
        System.out.println("Draw 1: " + random.nextInt(100));
        System.out.println("Draw 2: " + random.nextInt(100));

        random.setSeed(42L);
        System.out.println("After setSeed, draw 1: "
                + random.nextInt(100));

        Random restartedEachTime = new Random(42L);
        int fixedFirst = restartedEachTime.nextInt(100);
        int sameFirst = new Random(42L).nextInt(100);
        System.out.println("Two fresh generators: "
                + fixedFirst + ", " + sameFirst);

        Random anotherSeed = new Random(123L);
        Random replayAnotherSeed = new Random(123L);
        System.out.println("Seed 123 reproducible: "
                + (anotherSeed.nextLong()
                    == replayAnotherSeed.nextLong()));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac SeededRandomDemo.java
java SeededRandomDemo
~~~

Output:

~~~text
Seed 42: [30, 63, 48, 84, 70]
Replay identical: true
Draw 1: 30
Draw 2: 63
After setSeed, draw 1: 30
Two fresh generators: 30, 30
Seed 123 reproducible: true
~~~

Explanation:

1. Two calls to `generate(42L, 5)` create two new `Random` objects, but apply **the same seed and five `nextInt(100)` calls in the same order**, so the two lists are equal.
2. A continuously used `Random` does not keep returning the first value: the next call uses the next state.
3. `setSeed(42L)` **resets the sequence** of that object. After resetting to the same seed, the first call returns `30` again.
4. Creating `new Random(42L)` on every loop iteration **restarts from the beginning**, which easily yields the value `30` repeatedly; this is a common bug when trying to generate multiple distinct numbers.
5. With seed 123, the first `nextLong()` calls on two new objects return the same result. The example only checks reproducibility; there is no need to memorize the actual `long` value.

The values in the example belong to `java.util.Random`, not a general guarantee for all other random generators in Java.

## 4. Inside java.util.Random: how does a seed determine the sequence?

For the classic `java.util.Random` class, the core algorithm is a **linear congruential generator (LCG)** using a **48-bit** state. Conceptually, it performs:

~~~text
Initial 48-bit state = (seed XOR 0x5DEECE66D) AND (2^48 - 1)

Next state =
    (current state * 0x5DEECE66D + 0xB) mod 2^48

Output is read from the high bits of the new state.
~~~

In the `Random` specification, the state-update details and how the core `next(int bits)` method extracts bits are specified, allowing sequences with the same seed and call pattern to be reproducible across compatible Java implementations of **this specific class**.

You should not implement an LCG yourself just to call `nextInt`; use the standard API. However, understanding the mechanism helps explain several properties:

- The same seed establishes the same initial state, and thus the same state trajectory given the same consumption pattern.
- Each method may consume one or more state updates.
- The seed passed to the constructor has type `long`, yet the core state has only 48 bits. Two seeds that differ only outside the lowest 48 bits can produce **the same sequence**. For example, `42L` and `42L + (1L << 48)` create the same initial state in standard `Random`.
- Because it has a finite state space and a predictable algorithm, it is **not** a suitable generator for creating security tokens.

When speaking of a “fixed sequence”, understand it as **the algorithmic sequence of a specific generator**; passing the same seed into a different algorithm (such as `SplittableRandom`) does not mean it produces the same numbers as `Random`.

## 5. Call order matters just as much as the seed

A `Random` object has mutable state. How you consume it affects the values that appear later.

~~~java
Random a = new Random(42L);
Random b = new Random(42L);

int aFirst = a.nextInt(100); // 30
int aSecond = a.nextInt(100); // 63

int bFirst = b.nextInt(100); // 30
// If b is called elsewhere, subsequent draws will
// no longer correspond to the aSecond position under this call pattern.
~~~

Notes on different methods:

| Method | Meaning | Sequence notes |
| --- | --- | --- |
| `nextInt()` | Generates an `int` across the full int range | Consumes state |
| `nextInt(bound)` | Generates an `int` in `[0, bound)` | For a bound that is not a power of 2, it may need to redraw to avoid distribution bias |
| `nextLong()` | Generates a `long` | Typically combines multiple internal bit generations |
| `nextDouble()` | Generates a `double` in `[0.0, 1.0)` | Consumes bits to build double precision |
| `nextBoolean()` | Generates `true` or `false` | Consumes state |
| `nextGaussian()` | Generates a normally distributed value | Buffers one Gaussian value for the next call, making call history even more important |

`nextInt(bound)` should not be assumed to **always** consume exactly one state step in every case: the algorithm may have to retry if a candidate value falls outside the accepted range. `nextDouble()`, `nextLong()`, and `nextGaussian()` should also not be treated as equivalent to a single `nextInt()` call.

Consequently, replacing a `nextInt(100)` with `nextDouble()`, adding a debug call, or moving where a random number is drawn in the program can cause **the rest of the sequence to differ from the previous run** even when the seed stays the same.

## 6. Same seed but different calls: illustrating state

Suppose a game uses one `Random(42)` for every decision. First version:

~~~java
Random random = new Random(42L);
int enemyMove = random.nextInt(100);
int lootRoll = random.nextInt(100);
~~~

A later version adds a number draw before computing `lootRoll`:

~~~java
Random random = new Random(42L);
int enemyMove = random.nextInt(100);
int weatherRoll = random.nextInt(100);
int lootRoll = random.nextInt(100);
~~~

In this specific example, `enemyMove` is still `30`; `lootRoll` was previously `63`, whereas after adding `weatherRoll`, `lootRoll` becomes `48`. There is no bug in `Random`: the two runs **consumed the sequence at different positions**.

To simulate multiple relatively independent parts (such as weather and loot), you can give each part its own `Random` with an explicitly managed seed. Then drawing extra numbers in the weather part will not advance the state of the generator in the loot part.

~~~java
Random weatherRandom = new Random(1001L);
Random lootRandom = new Random(2002L);
~~~

The seeds here are pre-selected examples for easy reproducibility; they are not a formula guaranteeing two completely statistically independent sequences. For large simulations, choose an appropriate stream-splitting strategy and algorithm, and clearly record each stream's seed.

## 7. setSeed(): replay from the start, not rewind one step

An object that has already produced many values can be reinitialized:

~~~java
Random random = new Random(42L);

int first = random.nextInt(100);  // 30
int second = random.nextInt(100); // 63

random.setSeed(42L);

int replayFirst = random.nextInt(100); // 30
~~~

`setSeed(42L)` does not “subtract one step” from the current state. It **resets the state from the provided seed**. That means calls consumed earlier no longer determine the sequence after reseeding.

Specifically, `Random.nextGaussian()` uses a buffer to store an unreturned Gaussian result; calling `setSeed()` also clears this buffer state according to the class contract. This matters if you need to replay a Gaussian sequence from the beginning.

You should not call `setSeed` between draws just to “increase randomness”. Repeatedly reseeding with the same value makes the sequence repeat from the start.

## 8. Chosen seeds and default seeds

Two common ways of initializing:

~~~java
Random reproducible = new Random(2026L);
Random automatic = new Random();
~~~

**`new Random(2026L)`** uses a public, fixed seed chosen by the program. When an experiment needs to be reproducible, record the seed and how the numbers are consumed.

**`new Random()`** uses Java's automatic seed initialization mechanism. Two created instances may have different seeds and different sequences, but the program should not rely on that as a guarantee of secrecy, absolute uniqueness, or cryptographic quality. Without recording the conditions to recreate the state, it will be hard to replay an exact run.

Using `System.currentTimeMillis()` as a seed can be convenient for quick experiments, yet multiple generators created within the same millisecond can receive the same seed. For automated tests, a fixed seed is usually easier to investigate when failures occur.

A useful practice is to **print or log the seed of a failing run**, along with the code version and options that affect the number of calls. When a bug only happens in a random scenario, rerunning with the same data helps reproduce it.

## 9. Generating numbers in a range and avoiding pitfalls

`random.nextInt(bound)` requires `bound > 0` and returns a number in the half-open interval `[0, bound)`. If `bound <= 0`, the method throws `IllegalArgumentException`.

~~~java
Random random = new Random(42L);
int die = random.nextInt(6) + 1; // 1..6
~~~

To draw an integer from `min` to `max` **inclusive of both ends** when you are sure the calculation will not overflow `int`:

~~~java
int value = min + random.nextInt(max - min + 1);
~~~

This is only an **expression pattern** when `min`, `max`, and the interval width are valid and `max - min + 1` fits in `int`. For wide ranges, you can use an appropriate origin/bound API in modern Java or compute with `long`, and you must check whether the upper bound overflows.

Java 17 provides APIs from `RandomGenerator`, but do not automatically assume that a different API call will consume state identically to the old `nextInt(bound)` formula. For exact replay, keep the call pattern and program version fixed.

Another point: a fixed seed does not turn the first five numbers into a “uniform sample” over 0..99. Sequence reproducibility and statistical distribution evaluation are two different problems. Do not judge PRNG correctness by demanding that every number in a short segment appear exactly once.

## 10. Random, ThreadLocalRandom, SplittableRandom, and SecureRandom

Related classes address different needs.

| Class/API | Common use case | Seed notes |
| --- | --- | --- |
| `java.util.Random` | Examples, tests, and simple simulations needing reproducibility | Accepts an explicit seed; traditional `Random` algorithm sequence is specified |
| `java.util.SplittableRandom` | Number generation for splittable simulation tasks | Has a constructor taking a seed, but **algorithm/sequence differs from `Random`** |
| `java.util.concurrent.ThreadLocalRandom` | Convenient number generation across multiple threads | Obtained via `current()`; does not support external `setSeed` for replay like `Random` |
| `java.security.SecureRandom` | Tokens, salts, nonces, and data needing unpredictability | Intended for cryptographic security; seeding/algorithm depends on implementation, not used as a `Random` sequence replay tool |

`Random` can be used by multiple threads, yet **the actual order of calls** from threads can vary due to scheduling. Therefore, **the same seed is not enough to guarantee each thread receives the exact same sequence** if threads share one generator and interleave differently.

`ThreadLocalRandom.current().setSeed(...)` is not a valid way to seed the thread's generator: `setSeed` is designed to throw `UnsupportedOperationException`. For independent per-thread reproducibility, design explicit seed/generator allocation per task; consider `SplittableRandom` or generators from `java.util.random` according to project contracts.

**Never use `new Random(fixedSeed)` to create login tokens, keys, OTPs, or secret values.** The outputs can be predicted because the algorithm and seed are not protected for this purpose. Use `SecureRandom` and follow appropriate security guidelines.

## 11. Streams, consumption counts, and reproducibility

`Random` also supports creating streams of integers:

~~~java
Random random = new Random(42L);

List<Integer> values = random.ints(5, 0, 100)
        .boxed()
        .toList();
~~~

In Java 17, Stream's `toList()` returns a list following the encounter order of an ordered stream. In the example above, we generate five integers in `[0, 100)` from a seeded generator.

Important point: the stream consumes the `random` object itself. If you make an extra call to `random.nextInt()` before processing the stream, the retrieved results can change. If you need easily comparable test results, consume the stream sequentially and keep calls outside the stream fixed.

Do not assume that sharing one generator across parallel streams, multithreaded tasks, or changing pipeline structure will preserve the mapping of random numbers to elements. Results depend on consumption, and execution scheduling may be nondeterministic.

## 12. Reproducible testing with a fixed seed

For an algorithm that uses random numbers, instead of scattering `new Random()` calls everywhere, you can accept a `Random` as a parameter:

~~~java
static int rollDie(Random random) {
    return random.nextInt(6) + 1;
}
~~~

This is a **method snippet** inside a Java class with `import java.util.Random;`.

Advantage: the caller controls the seed and state, making tests reproducible. For example:

~~~java
Random experiment = new Random(500L);
int firstRoll = rollDie(experiment);
int secondRoll = rollDie(experiment);
~~~

If replay is needed, create a new `Random(500L)` and call `rollDie` twice in the same order. To compare two implementations, you can create **two separate objects** with the same seed, then ensure both implementations consume the same number and types of calls. If a new algorithm adds an extra number draw, verify that it is an intentional change before comparing step-by-step outputs.

When logging to reproduce a bug, useful information usually includes: **seed**, **PRNG class/algorithm**, **code version**, **generation parameters (like bound)**, and **sequence of consumption events**. For parallel runs, also include how seeds are distributed and the work-processing order.

## 13. Common mistakes

**Mistake 1 — Creating `new Random(42L)` inside every loop iteration.** Each object starts at the beginning of the sequence, so the first `nextInt(100)` call always returns `30`. Better practice is to initialize one object outside the loop and use it continuously.

**Mistake 2 — Thinking the same seed is enough.** If one code branch makes an extra `nextInt`, `nextLong`, `nextDouble`, or `nextGaussian` call, consumption positions no longer align; the same seed will not guarantee the same result at the corresponding business step.

**Mistake 3 — Using `nextInt(10)` and expecting 10.** The bound is **exclusive**. `nextInt(10)` only returns 0..9. For a 1..6 die, use `nextInt(6) + 1`.

**Mistake 4 — Passing a zero or negative bound.** `nextInt(0)` and `nextInt(-3)` throw `IllegalArgumentException`; you must validate input preconditions.

**Mistake 5 — Mixing results from multiple threads and expecting exact replay.** The same seed on a shared object does not fix thread interleaving order. Design one generator per task with independently managed seeds when reproducibility is required.

**Mistake 6 — Using `Random` for security codes.** Seeds can be guessed and the LCG state is only 48 bits; use `SecureRandom` for values that must be hard to predict.

**Mistake 7 — Logging only the seed without the algorithm or consumption order.** When changing PRNG types, changing bounds, or adding calls, the number sequence can change. Logs need enough context to reproduce.

**Mistake 8 — Assuming every `long` seed produces a unique sequence.** For standard `java.util.Random`, the seed is transformed and truncated to 48 bits; different `long` seeds can produce the same sequence.

**Mistake 9 — Equating “same sequence” with “guaranteed good distribution in all scenarios”.** Reproducibility does not prove uniformity or statistical independence. If simulation outputs demand high statistical quality, algorithm selection must be evaluated separately.

## 14. Self-check exercises

**Question 1.** What does the following program print?

~~~java
Random a = new Random(42L);
Random b = new Random(42L);

System.out.println(a.nextInt(100));
System.out.println(b.nextInt(100));
System.out.println(a.nextInt(100));
~~~

**Answer:**

~~~text
30
30
63
~~~

Each object maintains its own state. The first two calls take the first number of two identical sequences; the last call gets the second number of `a`.

**Question 2.** If a `nextInt(100)` call is added before computing the result of a simulation, does the seed change? Can subsequent results change?

**Answer:** The initial seed does not change, but the state has advanced. Therefore, the numbers received by subsequent steps can change.

**Question 3.** Do two `Random` instances created with `new Random(42L)` and `new Random(42L + (1L << 48))` produce the same `nextInt(100)` sequence?

**Answer:** Yes, for the 48-bit `java.util.Random` algorithm described above: the difference lies outside the lower 48 bits, so the initial states are equivalent.

**Question 4.** To reproduce a bug that only occurs with pseudorandom data, what minimum information should be recorded besides the seed?

**Answer:** The generator and program version/behavior, along with the methods and parameters consuming the sequence in the exact order. If parallel execution is involved, you must control sequence splitting and scheduling or record enough information to reproduce them.

**Question 5.** Should `Random(42L)` be used to generate a 6-digit verification code for users?

**Answer:** No. A fixed seed leads to a reproducible sequence, and `Random` is not a cryptographic generator. Use `SecureRandom` when unpredictability is required.

**Key takeaway:** The seed is the starting point of a **stateful pseudorandom sequence**. With `java.util.Random`, the same seed, same calls, and same consumption order yield the same results; `setSeed` reinitializes the sequence. Use this property for reproducible tests/simulations while keeping in mind the limits regarding multithreading, algorithm changes, and security.
