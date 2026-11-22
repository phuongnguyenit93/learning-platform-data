# Why Can Arbitrary Use of % Create Bias When Generating Random Numbers?

When you need a random value from `0` to `n - 1`, code like `randomNumber % n` looks reasonable: the modulo operator reduces a large integer into a number smaller than `n`. However, **constraining the value range is not the same as producing a uniform distribution**. If the original range of values cannot be divided evenly into groups of equal size, some outcomes will occur more often than others. That is **modulo bias** (bias from taking the remainder).

Example simulating a die face from a hypothetical source that uniformly generates one of the eight integers `0, 1, ..., 7`:

```java
int face = source % 6; // source is in [0, 8), uniform
```

This code always returns one of `0..5`, yet the outcome is **not uniform**: `0` and `1` have two preimages, while the rest have one. If the goal is a fair six-sided die, you cannot apply `% 6` directly like this.

## 1. Proof by counting: source has 8 values, target has 6 values

Suppose the source is truly uniform on `[0, 8)`, meaning every integer from 0 to 7 has probability `1/8`. Mapping table:

| Source value `x` | `x % 6` | Final outcome |
|---:|---:|---|
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 3 | 3 | 3 |
| 4 | 4 | 4 |
| 5 | 5 | 5 |
| 6 | 0 | 0 (duplicates outcome of 0) |
| 7 | 1 | 1 (duplicates outcome of 1) |

Distribution after mapping:

| Outcome | Number of source values producing it | Probability after `% 6` | Desired probability |
|---:|---:|---:|---:|
| 0 | 2 | 2/8 = 25% | 1/6 ≈ 16.67% |
| 1 | 2 | 2/8 = 25% | 1/6 ≈ 16.67% |
| 2 | 1 | 1/8 = 12.5% | 1/6 ≈ 16.67% |
| 3 | 1 | 1/8 = 12.5% | 1/6 ≈ 16.67% |
| 4 | 1 | 1/8 = 12.5% | 1/6 ≈ 16.67% |
| 5 | 1 | 1/8 = 12.5% | 1/6 ≈ 16.67% |

Thus outcome `0` appears **twice as often** as outcome `2`, even though all input numbers have equal probability. Increasing the number of simulations only drives measured frequencies closer to the **biased** distribution; running more trials does not fix the algorithm.

### General condition

Suppose a uniform source consists of `N` consecutive integers from `0` to `N - 1`, and must be mapped onto `n` outcomes from `0` to `n - 1`. Write:

```text
N = q × n + r, where 0 ≤ r < n
q = N / n (integer division)
r = N % n
```

If you take `x % n` directly:

- The first `r` outcomes (`0 .. r - 1`) have `q + 1` source values mapping to them.
- The remaining `n - r` outcomes (`r .. n - 1`) have `q` source values mapping to them.
- When `r = 0`, every outcome has the same `q` preimages: **there is no modulo bias from this mapping**, provided the source itself is truly uniform.
- When `r ≠ 0`, the distribution is biased.

For `N = 8`, `n = 6`: `q = 1`, `r = 2`. Two outcomes (`0`, `1`) receive two preimages each; the other four outcomes receive one preimage each.

The counting argument above is a proof in **a finite uniform domain**; it does not prove that a pseudorandom source in general has high quality, independence, or cryptographic security.

## 2. Familiar case: random byte followed by `% 10`

A uniformly random byte has `256` possibilities: `0..255`. Suppose you want to generate a decimal digit `0..9`:

```java
int digit = unsignedByte % 10; // unsignedByte in [0, 255]
```

We have:

```text
256 = 25 × 10 + 6
```

Therefore, digits `0..5` have **26** corresponding source values, while `6..9` have only **25** corresponding source values:

| Digit | Number of preimages | Probability |
|---|---:|---:|
| 0, 1, 2, 3, 4, 5 | 26 per digit | 26/256 ≈ 10.15625% |
| 6, 7, 8, 9 | 25 per digit | 25/256 ≈ 9.765625% |

A fair distribution should be `10%` for **each** digit. The skew here is smaller than in the `8 → 6` example, yet it is still a systematic bias. This matters when generating many tokens, selecting rewards, statistical sampling, or when security requirements forbid predictable biases.

**The magnitude of bias depends on both the source domain size and the number of outcomes**; you cannot conclude every `%` is heavily biased or always biased. For instance, a 256-value source with `% 16` gives exactly 16 preimages per outcome; `% 10` is biased because 256 is not divisible by 10.

## 3. Fixing it with rejection sampling

A standard way to preserve uniformity is to **accept only an input range whose size is divisible by `n`**, and redraw if a value falls outside that range.

For an 8-value source and `n = 6`:

1. Draw a number uniformly from `0..7`.
2. If it is `6` or `7`, **discard it and draw again**.
3. If it is `0..5`, return that number as-is.

Among **accepted** draws, each outcome `0..5` has exactly one preimage, so its probability is `1/6`. Each attempt has acceptance probability `6/8 = 75%`, and the expected number of attempts for one valid result is `8/6 = 4/3`.

Code illustrating the algorithm:

```java
int value;
do {
    value = rng.nextInt(8);
} while (value >= 6);
// value is uniform in [0, 6), if each rng.nextInt(8)
// is uniform and draws satisfy the source's assumptions
```

This is a **snippet in a context where `rng` is already declared**; in ordinary Java, the simpler solution is to **call `rng.nextInt(6)` directly**.

### General rejection formula for an unsigned byte

For a uniform integer source `[0, 256)`, if `n` outcomes are needed with `1 ≤ n ≤ 256`, set:

```text
limit = 256 - (256 % n)
```

`limit` is the largest multiple of `n` not exceeding 256. Loop:

```java
static int uniformFromByte(java.util.Random rng, int n) {
    if (n < 1 || n > 256) {
        throw new IllegalArgumentException("n must be in [1, 256]");
    }

    int limit = 256 - (256 % n);
    int sample;
    do {
        sample = rng.nextInt(256); // uniform source 0..255
    } while (sample >= limit);

    return sample % n; // now every outcome has the same number of preimages
}
```

This is a **method** to place inside a class; it illustrates the mathematics rather than something you need to implement manually for most Java programs. For `n = 10`: `limit = 250`; discard `250..255`, accept `0..249`. Each digit gets exactly **25** preimages, so every probability equals `1/10`. Acceptance probability per attempt is `250/256`, and expected attempts are `256/250 ≈ 1.024`.

Why is `% n` still used at the end? Because **after rejecting the leftover samples, the number of accepted values is now divisible by `n`**. Taking the remainder at that point introduces no bias. The issue lies in applying `%` before trimming the remainder from the input domain, not in the `%` operator under all circumstances.

### What to check when implementing yourself

- Know the exact **input domain** and uniformity assumptions; do not guess the source from an API name.
- The accepted domain's size must be a multiple of `n`.
- You must **draw a fresh sample** after rejection, never map a rejected sample to an arbitrary outcome.
- Avoid integer overflow when computing multiples, thresholds, or absolute values on large domains like 32/64-bit integers.
- If the source is not uniform to begin with, simple rejection sampling over preimages will **not cure** all source flaws on its own.

For real applications, use the JDK's **bounded random APIs** that already handle these cases instead of rolling your own algorithm.

## 4. Which API should Java code use?

When you need a random integer **within a range**, prefer APIs that accept the range or upper bound directly:

```java
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

Random random = new Random();

// Uniform over 0..5 per the API contract:
int zeroBasedDie = random.nextInt(6);

// Die face 1..6:
int die = random.nextInt(6) + 1;

// Generate in [10, 20) = 10..19:
int value = ThreadLocalRandom.current().nextInt(10, 20);
```

The snippet above illustrates calls inside a method; it is not a standalone `main` program. In Java 17 and above, `java.util.random.RandomGenerator` also defines bounded variants such as `nextInt(bound)` and `nextInt(origin, bound)`.

| Need | Typical API | Output range |
|---|---|---|
| Picking an index for a `List` with `size > 0` | `random.nextInt(size)` | `0..size-1` |
| 6-sided die | `random.nextInt(6) + 1` | `1..6` |
| Any integer interval with `origin < bound` | `ThreadLocalRandom.current().nextInt(origin, bound)` | `[origin, bound)` |
| Many ordinary concurrent tasks | `ThreadLocalRandom` or a generator suited to state-sharing needs | Per bounded arguments |
| Unpredictable values for security | `new SecureRandom().nextInt(bound)` | `0..bound-1` from a cryptographic random source |

**`bound` is an exclusive upper bound**: `nextInt(6)` returns 0 through 5, not 1 through 6. Passing `nextInt(0)` or invalid bounds does not mean “pick any number”; it normally throws `IllegalArgumentException`.

`Random` and `ThreadLocalRandom` serve general pseudorandom generation and **must not be used for secret codes, authentication tokens, or unpredictable security values**. For security cases, choose `SecureRandom`:

```java
import java.security.SecureRandom;

SecureRandom secureRandom = new SecureRandom();
int secureDigit = secureRandom.nextInt(10); // 0..9
```

Here `SecureRandom` protects **unpredictability**, while `nextInt(10)` maps to the result range under the bounded API contract. The two requirements—**unpredictability** and **uniform distribution**—are related but not identical. Drawing a cryptographically random byte and immediately taking `% 10` still introduces modulo bias by the `256 = 25×10 + 6` argument.

## 5. Standalone, easily verifiable Java 17+ example

Save the program as `ModuloBiasDemo.java`. The example **counts all states exhaustively** rather than relying on chance-based simulation, so it produces deterministic output on every run.

```java
import java.util.Arrays;
import java.util.Random;

public class ModuloBiasDemo {
    private static int fromByteWithRejection(Random random, int bound) {
        if (bound < 1 || bound > 256) {
            throw new IllegalArgumentException("bound must be 1..256");
        }
        int limit = 256 - (256 % bound);
        int value;
        do {
            value = random.nextInt(256);
        } while (value >= limit);
        return value % bound;
    }

    public static void main(String[] args) {
        int[] eightModuloSix = new int[6];
        int[] eightAcceptedSix = new int[6];
        for (int value = 0; value < 8; value++) {
            eightModuloSix[value % 6]++;
            if (value < 6) {
                eightAcceptedSix[value]++;
            }
        }

        System.out.println("8 states % 6: "
                + Arrays.toString(eightModuloSix));
        System.out.println("8 states after rejection: "
                + Arrays.toString(eightAcceptedSix));
        System.out.println("Rejected from 8: " + (8 - 6));

        int[] byteModuloTen = new int[10];
        int[] byteAcceptedTen = new int[10];
        for (int value = 0; value < 256; value++) {
            byteModuloTen[value % 10]++;
            if (value < 250) {
                byteAcceptedTen[value % 10]++;
            }
        }

        System.out.println("256 states % 10: "
                + Arrays.toString(byteModuloTen));
        System.out.println("256 states after rejection: "
                + Arrays.toString(byteAcceptedTen));
        System.out.println("Rejected from 256: " + (256 - 250));

        Random rng = new Random(12345);
        for (int i = 0; i < 10_000; i++) {
            int bounded = rng.nextInt(6);
            int rejection = fromByteWithRejection(rng, 10);
            if (bounded < 0 || bounded >= 6
                    || rejection < 0 || rejection >= 10) {
                throw new AssertionError("Value outside expected range");
            }
        }
        System.out.println("10,000 bounded draws: ranges OK");

        System.out.println("-5 % 6 = " + (-5 % 6));
        System.out.println("floorMod(-5, 6) = " + Math.floorMod(-5, 6));
    }
}
```

Run:

```bash
javac ModuloBiasDemo.java
java ModuloBiasDemo
```

Stdout:

```text
8 states % 6: [2, 2, 1, 1, 1, 1]
8 states after rejection: [1, 1, 1, 1, 1, 1]
Rejected from 8: 2
256 states % 10: [26, 26, 26, 26, 26, 26, 25, 25, 25, 25]
256 states after rejection: [25, 25, 25, 25, 25, 25, 25, 25, 25, 25]
Rejected from 256: 6
10,000 bounded draws: ranges OK
-5 % 6 = -5
floorMod(-5, 6) = 1
```

**How to read the output:**

1. The two `8 states` arrays confirm by counting that direct `% 6` favors two outcomes, whereas rejecting `6, 7` produces uniform preimage counts.
2. The two `256 states` arrays show the exact bias of `% 10` and how the `250` threshold removes the six excess values.
3. The `10_000` loop checks **result bounds** of the API and rejection example, not an empirical proof that an arbitrary PRNG is uniform. The proof of eliminating modulo bias lies in **counting preimages**.
4. The `-5 % 6` line shows that Java's `%` operator is a **signed remainder**, not guaranteed to return 0 through 5 when the dividend is negative.

## 6. Related Java pitfalls

### Pitfall A: `random.nextInt() % n` can be negative

`Random.nextInt()` without arguments returns a signed 32-bit integer. In Java, `%` preserves the sign of the dividend:

```java
int remainder = -5 % 6;        // -5
int wrapped = Math.floorMod(-5, 6); // 1
```

`Math.floorMod(x, n)` when `n > 0` solves the **negative result** issue, yet **does not eliminate modulo bias** on a source domain not divisible by `n`. Never mistake “non-negative” for proof of uniform distribution.

### Pitfall B: `Math.abs(random.nextInt()) % n` is not a fix

`Math.abs(Integer.MIN_VALUE) == Integer.MIN_VALUE` because the positive magnitude of `-2147483648` cannot be represented in `int`. Consequently, the result can still be negative, even before `% n`. Moreover, taking absolute values folds opposite values together and can create an uneven distribution; it does not ensure balanced frequencies.

```java
int value = Math.abs(random.nextInt()) % 6; // avoid
int correct = random.nextInt(6);            // prefer
```

Do not use the `(x % n + n) % n` trick as a solution for modulo bias either: that expression only normalizes **negative remainders** when arithmetic does not overflow and `n` is valid; it still fails to fix unequal preimage counts.

### Pitfall C: Testing a few thousand draws and concluding “uniform”

Even an unbiased algorithm exhibits random fluctuation in finite samples; a slightly biased algorithm can also look fairly even over a few trials. To evaluate properly, you need:

- Reasoning over **the input domain, preimage counts, and mapping algorithm**.
- Verification of the API contract and generator quality appropriate for the purpose.
- Statistical hypothesis tests when empirical evaluation is needed, with suitable hypotheses and sample sizes. Statistical results do not replace a proof of the mapping.

### Pitfall D: Divisible `%` alone does not prove the whole generator is good

If `N` is divisible by `n`, the mapping step `x % n` itself introduces no frequency skew **assuming a uniform source**. However, if a generator produces predictable periodic patterns, correlations, or weak low-order bits, simply taking the remainder (especially for powers of 2) can expose those flaws. Therefore, use the bounded API of a generator suited to your application and do not assume `%` is “safe” just because `n` is a power of 2.

### Pitfall E: Every rounding/mapping alters distribution

Other shortcuts like `Math.round(Math.random() * 5)` can also be non-uniform: points at the edges of the range receive rounding interval widths different from interior points. Avoid jumping from “output lies in range” to “output is uniform”. When bounded integers are needed, call integer APIs directly.

## 7. Practical cases and appropriate choices

| Scenario | Approach |
|---|---|
| Randomly picking an element from a list with `size > 0` | `list.get(rng.nextInt(list.size()))` |
| Simulating a fair 1-to-6 die | `rng.nextInt(6) + 1` |
| Generating integers in `[min, max)` | `nextInt(min, max)` API; watch exclusive upper bound and valid domain |
| Generating secure verification codes/tokens from a character alphabet | Use `SecureRandom` and bounded API; also manage length, entropy, and token policy |
| Having uniform random bytes and needing digits `0..9` | Reject `250..255` before `% 10`, or directly use an API generating in `[0, 10)` |
| Intentionally skewed sample data | Define and implement the desired distribution; do not accidentally introduce bias via remainder |

Keep two requirements distinct:

- **Uniformity:** outcomes in the target domain share equal probability.
- **Unpredictability:** an observer cannot deduce the next outcome with meaningful practical probability.

`Random.nextInt(bound)` may fit ordinary simulations without providing `SecureRandom`'s security guarantees. Conversely, an unpredictable source can still be mapped into a biased distribution if `%` is applied carelessly.

## 8. Self-check

**Question 1.** Uniform source `0..9`, using `x % 4`: which outcomes appear more often?  
**Answer:** `10 = 2×4 + 2`; outcomes `0` and `1` each have three preimages, while `2` and `3` each have two preimages. Probabilities are 30%, 30%, 20%, 20% respectively; the distribution is biased.

**Question 2.** Uniform source `0..15`, using `x % 4`: is there modulo bias?  
**Answer:** No bias from this mapping because `16` is divisible by `4`. Every outcome has exactly four preimages. By itself, this does not speak to the source's overall quality or security.

**Question 3.** Why is discarding `250..255` before taking `% 10` on a uniform random byte valid?  
**Answer:** The accepted domain `0..249` has 250 values, divisible by 10; each digit `0..9` has 25 preimages. Rejected samples must be **redrawn**.

**Question 4.** Does `Math.floorMod(random.nextInt(), 6)` eliminate modulo bias?  
**Answer:** No. It fixes negative remainders; the 32-bit signed integer domain has `2^32` values, which is not divisible by 6, so mapping frequency skew remains.

**Question 5.** Why does `Math.abs(random.nextInt())` not guarantee a non-negative result?  
**Answer:** `Integer.MIN_VALUE` has no representable positive absolute value in `int`, so `Math.abs(Integer.MIN_VALUE)` remains negative.

**Question 6.** In Java, what should you write to uniformly select an index from a 10-element list?  
**Answer:** `rng.nextInt(10)`. If the choice involves secrets or security, use an appropriate generator such as `SecureRandom.nextInt(10)`.

**Key takeaway:** `x % n` reduces a value to a remainder, but **does not automatically ensure a uniform distribution**. Whenever the source state count is not divisible by `n`, remainders with more preimages are favored. Use Java's **bounded RNG APIs** or proper **rejection sampling** to avoid this bias.
