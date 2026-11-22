# Generating Integers, Floating-Point Numbers, and Gaussian Distributions in Java

## 1. Goals and nature of random numbers

In Java applications, “generating random numbers” can mean several different things:

- **Uniform discrete integers:** every integer in a finite set has equal probability, such as simulating a six-sided die.
- **Uniform continuous floating-point numbers (approximated via floating-point):** generating values in an interval with probability proportional to sub-interval length, such as simulating coordinates or ratios.
- **Normally distributed floating-point numbers (Gaussian/normal):** values cluster around a mean, with spread determined by standard deviation, such as simulating measurement noise.
- **Security-grade random numbers:** requiring unpredictability, suitable for verification codes, salts, keys, or tokens. This is a requirement on **generator security**, distinct from distribution choice.

Ordinary generators produce **pseudorandom numbers**: internal state plus an algorithm generate a sequence with desired statistical properties. With the same seed and same call sequence, a deterministic algorithm can reproduce the sequence. “Random” does not mean “unpredictable”, and uniform distribution does not mean Gaussian distribution.

In Java 17+, you can use `java.util.Random`, `java.util.concurrent.ThreadLocalRandom`, `java.util.SplittableRandom`, generators via `java.util.random.RandomGenerator`, or `java.security.SecureRandom` depending on your needs.

## 2. Generating uniformly distributed integers

### 2.1. Half-open interval [0, bound)

With `Random`:

~~~java
import java.util.Random;

Random rng = new Random();
int index = rng.nextInt(10); // 0, 1, 2, ..., 9
~~~

`nextInt(10)` draws an integer **from 0 (inclusive) to 10 (exclusive)**, equivalent to mathematical notation `[0, 10)`. When the generator is adequate for simulation, values 0 through 9 are chosen roughly equally. `nextInt(0)` or `nextInt` with a negative bound throws `IllegalArgumentException`.

For a six-sided die:

~~~java
int dice = rng.nextInt(6) + 1; // 1..6, both ends inclusive
~~~

This accurately expresses the set `{1, 2, 3, 4, 5, 6}`. **Do not use** `rng.nextInt(6)` assuming you can get 6; the raw result only reaches 5.

### 2.2. Intervals [origin, bound) and [min, max]

In Java 17, the `RandomGenerator` interface provides methods taking both start and end bounds, and `Random` implements this interface:

~~~java
int level = rng.nextInt(1, 7);   // 1..6
int score = rng.nextInt(20, 81); // 20..80
~~~

Here `origin` is inclusive and `bound` is exclusive. `origin < bound` is required; otherwise `IllegalArgumentException` is thrown.

A common requirement is including both endpoints, e.g., `min=10`, `max=20`. You can use `rng.nextInt(min, max + 1)` **when you are sure `max + 1` does not overflow `int`**. When `max == Integer.MAX_VALUE`, adding 1 overflows, making that formula unsafe.

If either bound in a problem can reach `Integer.MAX_VALUE`, consider sampling via `long`:

~~~java
int min = 10;
int max = Integer.MAX_VALUE;
int sample = (int) rng.nextLong((long) min, (long) max + 1L);
~~~

The snippet above works in Java 17+ because `Random` inherits the bounded methods of `RandomGenerator`. The value falls within the requested `int` range, so casting back to `int` is valid. Validate `min <= max` on input data. This approach uses `long` to compute the upper bound and avoid overflow when adding 1.

### 2.3. Do not generate integers by rounding `nextDouble()`

The following expressions do not have the same distribution:

~~~java
int good = rng.nextInt(6);                // 0..5, aims for uniform distribution
int biased = (int) Math.round(rng.nextDouble() * 5); // 0..5, not uniform
~~~

In the second formula, the endpoint values (0 and 5) receive input intervals roughly **half** the length of those assigned to interior values. `Math.round` also has its own tie-breaking rule for halves, which does not fix this probability skew. To pick an integer uniformly, use bounded `int` generation APIs instead of transforming floats arbitrarily with `Math.round` or `Math.floor`.

Likewise, `Math.abs(rng.nextInt()) % n` is not a good way to pick an index: `Math.abs(Integer.MIN_VALUE)` stays negative due to overflow, and modulo can introduce **modulo bias** when the input state count is not divisible by `n`. `nextInt(n)` handles bounded distribution properly for the standard case.

## 3. Generating uniformly distributed floating-point numbers

### 3.1. `nextDouble()` and `nextFloat()`

~~~java
double unit = rng.nextDouble(); // from 0.0 (inclusive) to 1.0 (exclusive)
float unitFloat = rng.nextFloat(); // same interval form, float precision
~~~

`nextDouble()` generates a pseudorandom `double` in `[0.0, 1.0)`, while `nextFloat()` generates a `float`. These are finite sets of floating-point representable values, **not** every mathematical real number in the interval. Do not treat them as arbitrary precision or decimal numbers with an exact chosen number of decimal places.

`Math.random()` is a concise choice when you only need a `double` in `[0.0, 1.0)`:

~~~java
double x = Math.random();
~~~

However, `Math.random()` does not let you pass a seed directly at the call site and is not an API for security. When reproducibility or algorithm control is needed, managing your own generator is clearer.

### 3.2. Interval [min, max)

Java 17+ offers bounded variants:

~~~java
double temperature = rng.nextDouble(-10.0, 35.0); // [-10.0, 35.0)
float fraction = rng.nextFloat(0.0f, 1.0f);      // [0.0f, 1.0f)
~~~

With valid `min < max`, values follow an approximate uniform distribution on the respective interval; results are strictly less than the upper bound. The classic calculation is:

~~~java
double min = 2.0;
double max = 5.0;
double sample = min + (max - min) * rng.nextDouble();
~~~

This formula expresses the idea of `U(min, max)` from `U(0, 1)`. However, `double` multiplication and addition can round; for some bounds, intermediate values may overflow or rounded values may hit the upper bound. Thus, when a direct bounded API is available, prefer `nextDouble(min, max)` with valid finite bounds. Avoid expecting floating-point transforms to automatically preserve every mathematical property at interval edges.

### 3.3. Precision and decimal digits

`double` does not store decimal numbers exactly in general; for instance, many numbers like `0.1` have no finite binary representation. Do not mistake a `nextDouble()` result for a “random monetary amount” exact to the cent.

To pick a monetary amount as an integer number of smallest units (like cents), simply **draw a bounded integer first** and convert:

~~~java
int cents = rng.nextInt(100, 501); // 100..500 cents
java.math.BigDecimal amount =
        java.math.BigDecimal.valueOf(cents, 2); // 1.00..5.00
~~~

`BigDecimal.valueOf(cents, 2)` represents `cents × 10^-2`, keeping cent units exact. This fits discrete currency simulations; it does not replace `SecureRandom` if the goal is creating secrets.

## 4. Gaussian distribution (normal distribution)

### 4.1. How does it differ from uniform distribution?

In a uniform distribution, sub-intervals of equal length have roughly equal probability. In a Gaussian distribution, probability density forms a bell curve, concentrated around the mean `μ` and tapering off on both sides.

The normal distribution is written `X ~ N(μ, σ²)`, where:

- `μ`: the mean, determining the center of the distribution.
- `σ`: the standard deviation, which must be non-negative. `σ²` is the variance. Larger `σ` spreads the distribution wider.
- **Standard normal distribution** `Z ~ N(0, 1)` has mean 0 and standard deviation 1.

Density formula for `σ > 0`:

\[
f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^2}{2\sigma^2}\right).
\]

`f(x)` is a **density**, not the probability at the exact point `x`; probability over an interval is the area under the curve on that interval. Floating-point outputs from a PRNG are discrete, while the target probability model is continuous.

Familiar approximations for an ideal Gaussian: roughly 68% lie within `μ ± σ`, roughly 95% within `μ ± 2σ`, and roughly 99.7% within `μ ± 3σ`. These are theoretical approximations, not a guarantee that every batch of 100 generated values hits those exact proportions.

### 4.2. Generating standard normal values with `nextGaussian()`

~~~java
Random rng = new Random();

double z = rng.nextGaussian(); // N(0, 1), approximately normally distributed
~~~

Unlike `nextDouble()`, `nextGaussian()` **does not lie in `[0,1)`**. It can be negative, positive, greater than 1, or less than -1. The ideal normal distribution has infinite tails on both sides, though computer implementations only return finite `double` values representable by the machine.

In `java.util.Random`, `nextGaussian()` uses a Box–Muller/Marsaglia polar transformation from uniform draws and caches a second Gaussian value for the next call. Because one call may consume multiple underlying draws due to retry logic, **never infer that each Gaussian call always consumes one `nextDouble()` call**. Interleaving `nextInt`, `nextDouble`, or `nextGaussian` calls also alters state and subsequent sequences.

### 4.3. Gaussian with custom mean and standard deviation

If `Z ~ N(0,1)`, then the transformation:

\[
X = \mu + \sigma Z
\]

yields `X ~ N(μ, σ²)` when `σ > 0`. For example, simulating measurement error around 100 with standard deviation 15:

~~~java
double mean = 100.0;
double standardDeviation = 15.0;

double measurement = mean + standardDeviation * rng.nextGaussian();
~~~

Java 17+ also defines a method on `RandomGenerator` accepting mean and standard deviation:

~~~java
double measurement2 = rng.nextGaussian(100.0, 15.0);
~~~

Both express the same target distribution model, but **do not assume bit-for-bit identical results with the same seed** because implementations may use different algorithms or different numbers of generation steps. If exact reproducibility is required, store the algorithm/generator type, seed, and call sequence.

**Parameter note:** `15.0` is the **standard deviation**, not the variance. `N(100, 225)` has `σ = 15`. Mistaking variance 225 for standard deviation makes the simulation 15 times wider than intended.

### 4.4. Gaussian has no hard bounds

If a requirement says “simulate exam scores from 0 to 100 centered at 70”, a Gaussian with `μ = 70` and `σ = 15` **can still produce negative numbers or values above 100**. Never assume a Gaussian obeys bounds automatically just because most values cluster near the mean.

There are at least three handling strategies depending on the model:

- **Accept out-of-range values** if the physical quantity or experiment allows them.
- **Reject and resample** values outside the interval; this creates a **truncated normal distribution** on the interval, no longer the original untruncated Gaussian. Limit retry counts if the interval is very narrow or far in the tail.
- **Clamp to bounds** using `Math.max(lower, Math.min(upper, sample))`; this piles probability mass onto the two bounds themselves, **not equivalent to a truncated normal**.

Example of intentional clamping:

~~~java
double raw = 70.0 + 15.0 * rng.nextGaussian();
double bounded = Math.max(0.0, Math.min(100.0, raw));
~~~

This is an **illustrative snippet inside a method**, not a standalone program. Choose the handling based on what the data means; do not silently alter distributions inside shared helper classes.

## 5. Runnable Java 17+ program

Example using a fixed seed for learning and testing. Save the full file as `RandomDistributionsDemo.java`:

~~~java
import java.util.Locale;
import java.util.Random;

public class RandomDistributionsDemo {
    public static void main(String[] args) {
        Random rng = new Random(12345L);

        System.out.println("int [0,10): " + rng.nextInt(10));
        System.out.println("dice [1,6]: " + (rng.nextInt(6) + 1));

        System.out.printf(Locale.ROOT,
                "double [0,1): %.6f%n", rng.nextDouble());
        System.out.printf(Locale.ROOT,
                "scaled [2,5): %.6f%n",
                2.0 + 3.0 * rng.nextDouble());

        System.out.printf(Locale.ROOT,
                "gaussian Z: %.6f%n", rng.nextGaussian());
        System.out.printf(Locale.ROOT,
                "gaussian N(100,15^2): %.6f%n",
                100.0 + 15.0 * rng.nextGaussian());
    }
}
~~~

Run from a terminal:

~~~bash
javac RandomDistributionsDemo.java
java RandomDistributionsDemo
~~~

Output (for `java.util.Random`, seed `12345L`, and the exact call order in the program):

~~~text
int [0,10): 1
dice [1,6]: 5
double [0,1): 0.932993
scaled [2,5): 4.499274
gaussian Z: -0.742381
gaussian N(100,15^2): 83.027545
~~~

`Locale.ROOT` ensures a decimal dot in `printf`, avoiding dependence on the machine's locale. `%.6f` specifies **six digits after the decimal point for display**, without changing the underlying random data inside the generator. The Gaussian values are not fixed “nice numbers” of the distribution: they are simply six specific values from a pseudorandom sequence for the chosen seed and call order.

The `Random` specification requires two instances with the same seed and same method call sequence to generate the same sequence per the class's standard algorithm. If you insert an extra `rng.nextInt(...)` call between lines, subsequent numbers may change; that is not a bug. Other generators may yield different sequences even with the same seed value.

## 6. Generating many elements and statistical verification

### 6.1. Streams for integers and floating-point numbers

`Random` provides convenient stream methods when a sample collection is needed:

~~~java
Random rng = new Random(42L);

// Generate exactly 10 integers, each in [1, 7).
int[] diceRolls = rng.ints(10, 1, 7).toArray();

// Generate exactly 5 doubles, each in [2.0, 5.0).
double[] points = rng.doubles(5, 2.0, 5.0).toArray();
~~~

These two lines sit in a method context with `import java.util.Random`. If very many elements are needed, consider processing as a stream rather than always loading everything into an array. When passing streams through parallel pipelines, consumption order and generator usage can affect reproducibility; consider splittable generators and avoid uncontrolled shared mutable state.

### 6.2. Checking a histogram instead of judging from a few calls

You can generate many die rolls and count occurrences of each face:

~~~java
import java.util.Random;

Random rng = new Random(2026L);
int[] counts = new int[6];

for (int i = 0; i < 60_000; i++) {
    int die = rng.nextInt(6) + 1;
    counts[die - 1]++;
}

// counts[0] counts face 1, ..., counts[5] counts face 6.
// Each face is expected around 10_000 times, not necessarily equal.
~~~

This is a snippet inside a method, not standalone. Under an ideal uniform model, the expected count per face is `60000/6 = 10000`, yet actual counts fluctuate. Do not write a test like `counts[0] == 10000`; even a good generator usually will not hit 10000 exactly.

For Gaussian samples, you can take many draws to measure empirical mean and standard deviation; with finite sample sizes, results will be **close to**, not **exactly equal to**, theoretical parameters. When testing random data, verify bounds, value forms, and distributions within properly designed statistical tolerances, rather than picking a few fixed samples and claiming “randomness is proven”.

## 7. Choosing a generator: Random, ThreadLocalRandom, SplittableRandom, RandomGenerator, and SecureRandom

| API | Suitable when | Notes |
| --- | --- | --- |
| `Random` | Learning, examples, seeded tests, legacy code needing sequence replay | Thread-safe, but sharing one instance across threads can cause contention; **not cryptographically secure**. |
| `ThreadLocalRandom.current()` | Multithreaded programs needing number generation per thread | Per-thread generator reducing contention; cannot set seed with `setSeed` in ordinary usage; not cryptographically secure. |
| `SplittableRandom` | Simulations and branching tasks needing separate generators for independent tasks | Do not share an instance across threads without synchronization; use `split()` to create independent branch generators. |
| `RandomGenerator` and `RandomGeneratorFactory` (Java 17+) | Abstracting over an interface and selecting an appropriate PRNG algorithm | Multiple algorithms exist with different properties; algorithm name and seed handling affect reproducibility. |
| `SecureRandom` | Tokens, salts, nonces, unpredictable security values | Derives security from cryptographic generator/provider; different overhead and seeding behavior; do not replace with `Random` just for speed. |

`ThreadLocalRandom` example:

~~~java
import java.util.concurrent.ThreadLocalRandom;

int index = ThreadLocalRandom.current().nextInt(0, 100);
double u = ThreadLocalRandom.current().nextDouble(0.0, 1.0);
double z = ThreadLocalRandom.current().nextGaussian();
~~~

`SplittableRandom` and task splitting example:

~~~java
import java.util.SplittableRandom;

SplittableRandom parent = new SplittableRandom(2026L);
SplittableRandom child = parent.split();

int parentRoll = parent.nextInt(1, 7);
int childRoll = child.nextInt(1, 7);
~~~

Java 17 `RandomGenerator` interface example:

~~~java
import java.util.random.RandomGenerator;

RandomGenerator generator =
        RandomGenerator.of("L64X128MixRandom");
int integer = generator.nextInt(1, 7);
double real = generator.nextDouble(0.0, 1.0);
double gaussian = generator.nextGaussian();
~~~

These snippets illustrate usage inside a method/class with corresponding imports; fixed output is not guaranteed since some examples are unseeded. Using `RandomGenerator.of` selects an algorithm by name and does not make the generator cryptographically secure. Java 17 introduces several new PRNG families; when choosing for real applications, weigh statistical properties, stream-splitting capabilities, and reproducibility requirements.

For security data, for example:

~~~java
import java.security.SecureRandom;

SecureRandom secure = new SecureRandom();
byte[] tokenBytes = new byte[32];
secure.nextBytes(tokenBytes);
~~~

`32` bytes create random material for a token; how the token is encoded, stored, and compared must fit the protocol. Do not use `new Random(System.currentTimeMillis())` to create secrets: attackers can more easily guess the seed or sequence. `SecureRandom` also has `nextInt(bound)` when choosing a secure value in a range; however, the number of possible values in the range must be large enough for required entropy. Gaussian distributions are generally **unsuitable** for generating tokens because the value set is non-uniform and can leak structure.

## 8. Seeds, reproducibility, and thread safety

A **seed** is input that initializes generator state, not proof that a generator is “more random”. With two `new Random(12345L)` instances and the same call sequence, results match. This is useful for unit tests, reproducible simulations, and debugging. If you change call order or swap generators, expect the sequence to change.

~~~java
Random first = new Random(123L);
Random second = new Random(123L);

System.out.println(first.nextInt(100) == second.nextInt(100)); // true
System.out.println(first.nextDouble() == second.nextDouble()); // true
~~~

A fixed seed in tests is a feature. A predictable seed in an authentication system is a vulnerability. In parallel work, give each task its own generator with properly managed seeds (or a splittable generator family); **never use the same `Random` both for fully reproducible test reports and for issuing secret tokens**.

`Random` is thread-safe, yet when multiple threads call it together, interleaving order can be nondeterministic, making per-thread reproducibility hard to achieve. `ThreadLocalRandom` reduces contention but is not designed to easily recreate an entire workload from a user-supplied seed. `SplittableRandom` supports splitting generators and is helpful when building clearly structured parallel simulations.

## 9. Common practical mistakes

1. **Wrong upper bound:** `nextInt(10)` never returns `10`; to pick `1..10`, use `nextInt(1, 11)` (Java 17+) or `nextInt(10)+1`.
2. **Assuming floating-point bounds are both inclusive:** `nextDouble()` targets `[0,1)`; do not treat the probability of hitting exactly `1` as equal to interior points.
3. **Confusing Gaussian with uniform:** `nextGaussian()` can be negative or exceed `1`; only `nextDouble()` is bounded to `[0,1)`.
4. **Confusing variance with standard deviation:** in `N(50, 9)`, `σ = 3`, not `9`. When writing `mean + sd * nextGaussian()`, use `sd`.
5. **Assuming Gaussian automatically respects business bounds:** it has no hard bounds; apply truncation, clamping, or another model choice intentionally.
6. **Using `Math.round(rng.nextDouble()*n)` for uniform integers:** boundary values generally have different probabilities from middle values; use `nextInt(n)`.
7. **Using `Math.abs(nextInt()) % bound`:** hits `Integer.MIN_VALUE` and modulo bias risks; use bounded methods directly.
8. **Instantiating `new Random()` repeatedly inside a loop:** working with one properly managed generator keeps state clear, is cheaper, and is easier to reproduce. For multithreaded apps, consider thread-local or splittable generators.
9. **Assuming the same seed alone guarantees identical results:** the algorithm and **order of every call** must also match; `nextGaussian()` may consume a different amount of state than uniform generation.
10. **Using `Random` or `Math.random()` for security tokens:** they are not CSPRNGs; use `SecureRandom`, and assess required entropy bits.
11. **Testing probabilities with a single fixed value:** one draw proves nothing about distribution. Use seeds to verify reproducibility, and proper sample sizes and statistical criteria to verify distributions.
12. **Forgetting floating-point effects and bound overflow:** `bound + 1` can overflow `int`, and `min + (max-min)*u` can cause rounding or overflow effects. Prefer bounded APIs when appropriate.

## 10. Self-check

**Question 1.** In `rng.nextInt(4)`, what are the valid return values?  
**Answer:** `0,1,2,3`. Not `4`.

**Question 2.** How do you uniformly generate an integer from `5` to `9`, inclusive of both ends?  
**Answer:** `rng.nextInt(5, 10)` (Java 17+) or `rng.nextInt(5) + 5`.

**Question 3.** Can `rng.nextGaussian()` return `-2.3`?  
**Answer:** Yes. The standard normal distribution is not bounded to `[0,1)`.

**Question 4.** To generate `X ~ N(80, 25)`, how do you write it?  
**Answer:** `80.0 + 5.0 * rng.nextGaussian()` because variance 25 means standard deviation 5.

**Question 5.** Why should you not simulate a die using `Math.round(rng.nextDouble() * 5) + 1`?  
**Answer:** The first and last faces receive shorter interval widths than the middle faces, skewing the distribution.

**Question 6.** One feature needs tests that rerun the exact same results, while another issues secret tokens. Can both use the same `new Random(12345L)`?  
**Answer:** No. Fixed seeds are useful in tests; secret tokens must use a cryptographically secure generator such as `SecureRandom`, with a token design providing sufficient entropy.

**Question 7.** Does clamping a `Gaussian` to `[0,100]` produce a true truncated Gaussian on that interval?  
**Answer:** No. Clamping maps every out-of-range sample to `0` or `100`, adding probability spikes at both endpoints. A truncated distribution via rejection and resampling has different properties.

## 11. Official documentation

- [`java.util.Random` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): `nextInt`, `nextDouble`, `nextGaussian`, seeding, and reproducibility.
- [`java.util.random` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/package-summary.html): PRNG algorithm families and generator selection notes.
- [`ThreadLocalRandom` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html): per-thread generators.
- [`SecureRandom` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): generator for data needing unpredictability.

**Key takeaway:** For **uniform integers**, use bounded `nextInt`; for **uniform floating-point numbers**, use `nextDouble`/`nextFloat`; for **Gaussian**, use `nextGaussian` and apply `μ + σZ`. Clarify distribution properties, value ranges, reproducibility, and security requirements before picking a generator.
