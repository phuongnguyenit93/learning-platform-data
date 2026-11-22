# BigInteger Arithmetic Cost by Operand Length

## 1. Why Does the Same Operation Have Different Runtimes?

`int` and `long` have fixed widths (32 and 64 bits), whereas `java.math.BigInteger` stores arbitrary-precision integers, as long as there is enough memory and they stay within the library's representation limits. Two calls:

~~~java
BigInteger small = BigInteger.valueOf(123);
BigInteger large = BigInteger.ONE.shiftLeft(1_000_000);
BigInteger a = small.multiply(small);
BigInteger b = large.multiply(large);
~~~

both call `multiply`, yet **the amount of data to process is completely different**. The first number needs only a few bits, while the second has over one million bits; the product of the second has roughly two million bits. Beyond multiplication, the JVM also needs to store and manage the result data, temporary buffers, allocations, and garbage collection.

Therefore, saying "every BigInteger addition/multiplication/division takes O(1)" is false when inputs have varying lengths. The cost depends on **the number of bits or machine words (limbs) representing operand magnitude**, the operation type, operand shapes (one short vs. both long), the selected algorithm, and the runtime environment.

**Goal:** learn to estimate cost growth order by length, distinguish bit count from arithmetic value, avoid intermediate result bloat, and measure with proper benchmarks before optimizing.

## 2. Operand Length: `bitLength` and Limb Count

For a positive integer `x`, `x.bitLength()` is the minimum number of bits required to represent its magnitude in binary. For example:

| Value | Binary form (shortened) | `bitLength()` |
|---|---|---:|
| `0` | `0` | 0 |
| `1` | `1` | 1 |
| `7` | `111` | 3 |
| `8` | `1000` | 4 |
| `255` | `11111111` | 8 |
| `256` | `100000000` | 9 |

For **negative numbers**, `BigInteger.bitLength()` is defined to match two's complement representation, not simply the bit count of the absolute value. For example, `BigInteger.valueOf(-1).bitLength() == 0`, whereas `abs().bitLength() == 1`. When analyzing **cost depending on operand magnitude**, use `x.abs().bitLength()` for both negative and positive numbers if you want to measure the bit count of the absolute value.

In OpenJDK, BigInteger magnitude is held in groups of machine words (limbs, currently typically 32-bit `int` elements) along with a sign. For a nonzero value with `n` magnitude bits, the number of limbs is approximately:

~~~text
L = ceil(n / 32)
~~~

This is an **explanatory cost model for the OpenJDK implementation**, not a public contract requiring every JVM to store values in a 32-bit `int[]` array. Algorithms may work with temporary data, other arrays, and specialized code paths for special cases.

An important distinction is between two measures:

- **Arithmetic value:** `10^1000` is greater than `10^100` under comparison.
- **Representation size:** `10^1000` needs approximately `1000 × log2(10) ≈ 3322` bits. Algorithms process data according to this representation length.

A number with one million decimal digits is not merely "larger" than a ten-digit number; it demands vastly more operations over machine words and memory.

## 3. Estimating Complexity by Machine Words

Let `n` and `m` be the number of limbs (or bit counts up to a constant factor) of two operands, with `n ≥ m ≥ 1`. The following table describes **typical cost orders**, without promising exact timings across every JDK version:

| Operation | Typical cost scale | Things to remember |
|---|---|---|
| `signum()`, some metadata queries | Usually O(1) | Depends on stored/cached data |
| `compareTo(b)`, `equals(b)` | At most O(n) for comparable sizes | Can finish early based on sign, length, or first differing limb |
| `add(b)`, `subtract(b)` | O(max(n, m)) in typical cases | Must propagate carry/borrow across limbs |
| `negate()`, `abs()` | Has lightweight paths; do not assume full copy always | BigInteger is immutable; internal optimizations vary by implementation |
| `shiftLeft(k)`, `shiftRight(k)` | Depends on input/result limb counts and shift amount | Large left shifts can create very large numbers and memory regions |
| `and`, `or`, `xor`, `not` | Usually proportional to data length to process | Bitwise semantics for negatives follow two's complement |
| `multiply(b)` grade-school multiplication | O(nm), or O(n²) if n≈m | Faster algorithms may be chosen for large numbers |
| `pow(exponent)` | Depends on exponent, result length, and multiplication cost | Result can grow very rapidly |
| `divide`, `remainder` | Depends on both dividend and divisor; usually heavier than addition | Has multiple algorithms and special cases |
| `gcd`, `modInverse` | Many division/transformation steps depending on values | Not fixed solely by one common length |
| `modPow` | Depends on modulus length, exponent, and modular multiplications/reductions | Avoid creating a huge `base.pow(e)` directly |

These are rules of thumb to **identify potential hotspots**, not a latency lookup table. Inputs with special structure (0, 1, powers of 2, one very short operand) and JDK fast paths can make actual results differ from the average model.

**Distinguish `n` and `m`:** multiplying a 4096-bit number by an 8-bit number is a different problem from multiplying two 4096-bit numbers. Do not lump both together as "4096-bit multiplication" while forgetting the second operand's length.

## 4. Addition and Subtraction: Nearly Linear in Length

Adding two large numbers can be visualized as limb-by-limb addition carrying the carry bit:

~~~text
A = [a0, a1, a2, ..., an-1]
B = [b0, b1, b2, ..., bm-1]
=> add corresponding limbs and propagate carry
~~~

If two numbers have roughly `n` limbs, the typical case takes work linear in `n`. Cases with long carry chains (for example, adding 1 to an all-1-bits number) must touch many limbs.

Example:

~~~java
BigInteger allOnes = BigInteger.ONE.shiftLeft(256)
        .subtract(BigInteger.ONE);
BigInteger nextPowerOfTwo = allOnes.add(BigInteger.ONE);

System.out.println(allOnes.bitLength());      // 256
System.out.println(nextPowerOfTwo.bitLength()); // 257
~~~

Even when adding only **1**, the result changes all 256 low bits and adds a leading bit. You cannot infer from the very short operand `BigInteger.ONE` that addition always has constant cost, or that the result will not grow in length.

With `add/subtract` repeated millions of times on increasingly large numbers, each step can become more expensive than the previous one, even though the Java statement in the loop does not change. If you only need to count values that fit in `long`, `long` is usually simpler and lighter; only use `BigInteger` when the numeric range truly demands it.

## 5. Multiplication: From O(n²) to Karatsuba and Toom-Cook

Grade-school multiplication of each limb of the first number by each limb of the second costs **O(nm)**; when the two lengths are comparable, that is **O(n²)**. If you double the limb count of both operands, the grade-school model can increase the number of limb-pair operations roughly fourfold. This is an **order-of-complexity estimate**, not a claim that actual runtime is always exactly 4×.

Large-number algorithms can reduce the number of sub-multiplications:

- **Karatsuba:** splits operands in half and uses three sub-products instead of four, giving balanced-operand complexity around **O(n^log₂3) ≈ O(n^1.585)**.
- **3-way Toom-Cook:** can reach roughly **O(n^log₃5) ≈ O(n^1.465)** with suitable splitting.
- **Grade-school multiplication:** has low overhead and is typically favorable for small numbers.

OpenJDK 17 includes grade-school, Karatsuba, and Toom-Cook multiplication paths along with empirical selection thresholds. **Thresholds and selection logic are implementation details** that can change across JDK versions and distributions; do not build program correctness on a hard-coded threshold or guarantee a 4×/2× scaling ratio when increasing bit count.

For two nonzero positive numbers with bit lengths `a` and `b`, the product's bit length lies in the range:

~~~text
a + b - 1 <= product.bitLength() <= a + b
~~~

For example, multiplying a 256-bit number by a 257-bit number usually requires up to 513 bits; that is the **result length**, not the number of CPU instructions. Even with faster multiplication algorithms, memory to hold the result still grows with the product's length.

### Squaring does not necessarily cost the same as multiplying two independent operands

`x.multiply(x)` can be optimized by a dedicated squaring algorithm in OpenJDK. Because many sub-products repeat when both operands are identical, library code can reduce overhead. However, do not state an assumed speed ratio that has not been measured on the actual deployed JDK. The results of `x.pow(2)` and `x.multiply(x)` are arithmetically identical, but code paths, special cases, and costs may differ.

## 6. Division, Remainder, and `gcd`: Cannot Be Judged Solely by Dividend Bit Length

Dividing a large `BigInteger` by a small number differs from dividing by a number close to its magnitude. Limb-based division algorithms may have to estimate quotient digits, multiply-subtract, and correct remainders repeatedly. OpenJDK 17 has classic and Burnikel–Ziegler division paths for sufficiently long operands.

With:

~~~java
BigInteger quotient = dividend.divide(divisor);
BigInteger remainder = dividend.remainder(divisor);
~~~

two independent calls can cause duplicated work. When **both quotient and remainder** are needed, use:

~~~java
BigInteger[] qr = dividend.divideAndRemainder(divisor);
BigInteger quotient = qr[0];
BigInteger remainder = qr[1];
~~~

This is a snippet used inside a method, where `dividend`/`divisor` are `BigInteger` and divisor is nonzero. `divideAndRemainder` allows the library to compute both results together, potentially reducing work compared to two independent calls; do not infer a fixed percentage speedup.

Several things to keep in mind:

1. Dividing by **0** throws `ArithmeticException`; performance analysis is meaningless when preconditions are unmet.
2. `divide` performs integer division, rounding the quotient **toward 0**; `remainder` keeps the sign matching the dividend (unlike `mod`, which requires a positive modulus and returns a non-negative remainder).
3. If the divisor is larger than the dividend in absolute value, the integer quotient is 0; this can be a cheap path.
4. `gcd` typically involves multiple transformation steps depending on intermediate values. Input bit lengths matter, but numeric structure and algorithm loop counts also affect runtime.

Do not replace `divide(x)` with `shiftRight(k)` unless **you have proven** `x` is a power of 2 and checked negative-number semantics: `shiftRight` performs signed arithmetic shift, whereas `divide` rounds toward 0. For example, `-3 >> 1` is `-2`, whereas `-3 / 2` is `-1`.

## 7. Exponentiation Explodes Result Length

If `a` has magnitude greater than 1, `a.pow(e)` can make the result bit count grow as **e × log₂|a|**. In the case `a = 2^k`, the result is `2^(ke)`, with bit length `ke + 1`. Multiplications may use exponentiation by squaring, yet **the massive result size cannot be avoided** if the goal is to retain the entire power.

Example:

~~~java
BigInteger two = BigInteger.TWO;
BigInteger huge = two.pow(1_000_000);
System.out.println(huge.bitLength()); // 1000001
~~~

This roughly one-million-bit number requires about 125 KB just to hold the minimum magnitude bits, not counting array, object, temporary results, and allocation/copying overhead. That is a bit-capacity estimate, **not an exact heap size**.

For problems needing only the **remainder** of `base^exponent mod modulus`, avoid building the full `base.pow(exponent)` and then calling `mod(modulus)`. Use:

~~~java
BigInteger result = base.modPow(exponent, modulus);
~~~

`modPow` computes modular exponentiation through optimized steps in which intermediate values are reduced modulo `modulus` instead of necessarily holding the entire colossal power. Cost still depends heavily on the bit count of `modulus`, the bit count of `exponent`, and the modular multiplication/reduction mechanism. Do not call `modPow` O(1) just because **result length** is bounded by `modulus`.

Mathematical example with positive exponent and positive modulus:

~~~java
BigInteger base = BigInteger.TWO;
BigInteger modulus = BigInteger.valueOf(97);
BigInteger e = BigInteger.valueOf(1_000);

boolean same = base.modPow(e, modulus)
        .equals(base.pow(1_000).mod(modulus));
System.out.println(same); // true
~~~

This snippet is only for cross-checking results with an exponent **small enough for illustration**. In a real program with an extremely large exponent, computing `pow` and then `mod` can consume severe time and memory.

## 8. Java 17+ Program to Observe Result Sizes

Save as **`BigIntegerLengthDemo.java`**:

~~~java
import java.math.BigInteger;

public class BigIntegerLengthDemo {
    private static int magnitudeBits(BigInteger x) {
        return x.abs().bitLength();
    }

    public static void main(String[] args) {
        BigInteger one = BigInteger.ONE;
        BigInteger a = one.shiftLeft(256).subtract(one);
        BigInteger b = one.shiftLeft(257).subtract(one);

        System.out.println("a bits = " + magnitudeBits(a));
        System.out.println("b bits = " + magnitudeBits(b));
        System.out.println("a+a bits = " + magnitudeBits(a.add(a)));
        System.out.println("a*b bits = " + magnitudeBits(a.multiply(b)));
        System.out.println("a^3 bits = " + magnitudeBits(a.pow(3)));

        BigInteger modulus = BigInteger.valueOf(97);
        BigInteger base = BigInteger.valueOf(2);
        BigInteger exponent = BigInteger.valueOf(1_000);
        boolean sameModularResult = base.modPow(exponent, modulus)
                .equals(base.pow(1_000).mod(modulus));
        System.out.println("modPow matches = " + sameModularResult);

        System.out.println("negative -1 magnitude bits = "
                + magnitudeBits(BigInteger.valueOf(-1)));
        System.out.println("negative -1 bitLength = "
                + BigInteger.valueOf(-1).bitLength());
    }
}
~~~

Run:

~~~bash
javac BigIntegerLengthDemo.java
java BigIntegerLengthDemo
~~~

Verified stdout:

~~~text
a bits = 256
b bits = 257
a+a bits = 257
a*b bits = 513
a^3 bits = 768
modPow matches = true
negative -1 magnitude bits = 1
negative -1 bitLength = 0
~~~

Since `a = 2^256 - 1` and `b = 2^257 - 1`, the product has bit length 513. Squaring/cubing numbers near powers of 2 also produces results whose bit count grows roughly linearly with the exponent. This program **does not measure time**; it illustrates the size of data that arithmetic algorithms must process.

## 9. Immutable `BigInteger`, Allocation, and Memory Pressure

`BigInteger` is immutable. Most operations generate new result values; the JVM may reuse constants, return the same reference in certain branches, or optimize allocations, so do not claim **every call is guaranteed to allocate exactly one new object**. Even so, a loop continuously creating large values can lead to:

- Many result data buffers and temporary limb arrays.
- Copying/writing limbs even when the operation looks like a single line of Java.
- Increased allocation rate, greater heap occupancy, and higher GC frequency.
- Cache/memory bandwidth pressure when operands are long.
- Timing variance due to the JIT compiler, CPU, GC, and input size distribution.

Accumulation example:

~~~java
BigInteger sum = BigInteger.ZERO;
for (int i = 1; i <= 1_000_000; i++) {
    sum = sum.add(BigInteger.valueOf(i));
}
~~~

This is an illustrative snippet inside a method (`import java.math.BigInteger`). `sum` is updated through many immutable values, potentially creating many temporary objects. If the sum is guaranteed to fit in `long`, summing with `long` and converting to BigInteger at the boundary can reduce cost; **only do so when non-overflow is proven** and domain requirements permit it.

For instance, when merely counting requests (not needing unbounded integers), `long` or corresponding primitive/atomic types may be more appropriate. When computing factorials, combinatorics, or cryptography where numbers exceed `long`, BigInteger is valuable for keeping exact results, but step counts and intermediate sizes must be controlled.

### Avoid string conversions inside hot loops

~~~java
// Avoid re-parsing the same decimal constant in a hot loop:
BigInteger a = new BigInteger("123456789012345678901234567890");

// When the argument fits in long, representation is simpler:
BigInteger b = BigInteger.valueOf(42L);
~~~

Converting a long decimal string to binary/limbs carries data-processing cost. Converting back via `toString()` also takes time and can produce an enormous string. Do not use `toString().length()` to "measure magnitude" inside a loop; use `abs().bitLength()` when a binary measure is needed, and avoid unnecessary measurement calls inside performance-critical computation code.

Do not let `System.out.println(hugeBigInteger)` become part of a multiplication/division benchmark: formatting and console output time can then dominate the operation you intended to measure.

## 10. Result Representation Cost and Keeping Intermediates at Reasonable Lengths

Some approximate rules when operands are positive:

| Operation | Result length |
|---|---|
| `a.add(b)` | At most `max(bits(a), bits(b)) + 1` |
| `a.subtract(b)` | Absolute value of result can be small or close to the largest operand |
| `a.multiply(b)` with nonzero a, b | From `bits(a) + bits(b) - 1` to `bits(a) + bits(b)` |
| `a.shiftLeft(k)` with positive nonzero a, k≥0 | `bits(a) + k` |
| `a.mod(m)` with positive m | Result from 0 to `m - 1`, so bit length does not exceed `bits(m)` |
| `a.pow(e)` with non-negative e | Length can grow proportionally to e |

The `bits()` formulas in the table use **the bit length of the absolute value**. Cases involving 0, 1, negative numbers, and special optimizations must be considered separately. `BigInteger` has practical implementation and memory limits; the phrase "arbitrary precision" does not mean unlimited allocation is possible.

When processing multiple steps, think about the **largest intermediate value**, not just input/output values. For example, to compute `(a × b) mod m`, if both `a` and `b` are near the modulus length, an intermediate product can be nearly twice as long as the modulus before reduction. Specialized modular algorithms can represent and reduce intermediates more efficiently across many iterations.

When bit count grows across loop iterations, the total cost of the process is the sum of each step's cost:

~~~text
TotalCost = Cost(size_1) + Cost(size_2) + ... + Cost(size_k)
~~~

Do not simply multiply the loop count by a constant if operand sizes are growing. For instance, factorial `n!` grows in digit count with `n`; it uses the same multiplication call while one operand's length keeps growing with `n`.

## 11. Measuring Real Performance: JMH and Benchmark Pitfalls

O(n) and O(n²) analyses are growth-order models, **not a substitute for measuring on real workloads**. The JVM has JIT, inlining, escape analysis, region-based allocation, GC, and internal size-dependent code paths. For reliable comparisons, use **Java Microbenchmark Harness (JMH)** with proper forks, warmup, measurement, and `Blackhole`.

A good benchmark design:

1. **Control both operands:** e.g., 64/64, 256/256, 1024/1024, 4096/4096 bits; include 4096/64 to compare the case with one short operand.
2. **Control content:** numbers with the same bit length yet very different structure (all 1 bits, random numbers, powers of 2) may follow different paths. Do not use 0 or 1 to stand in for large random numbers.
3. **Separate operations:** benchmark add, multiply, divide, and modPow in separate groups; exclude BigInteger construction, string parsing, random generation, formatting, or console output from the measured region if the target is the arithmetic operation.
4. **Prevent the JIT from eliminating results:** consume results via `Blackhole` or an appropriately designed sink; do not write loops with unused results.
5. **Avoid cross-iteration growth dependency:** if each iteration updates an ever-growing result, you are measuring a **size-growing algorithm**, not comparing the cost of a single multiplication at fixed sizes. Both kinds are useful, but they answer different questions.
6. **Record the environment:** JDK version, CPU, heap, GC, JMH version, forks/iterations, measurement counts, input distribution, data source, and algorithm thresholds.
7. **Report results with variance:** ns/op or ops/s along with error/dispersion; do not use a single `System.nanoTime()` call to promise "4096-bit multiplication takes exactly X ns".

### Conceptual JMH example

This is a **benchmark snippet requiring the JMH dependency and JMH annotation processor**; it cannot compile with only the JDK unless JMH is added to the project. Save in `BigIntegerMultiplyBenchmark.java` within the project's benchmark sources:

~~~java
import java.math.BigInteger;
import java.util.Random;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class BigIntegerMultiplyBenchmark {
    @Param({"128", "512", "2048", "4096"})
    public int bits;

    private BigInteger left;
    private BigInteger right;

    @Setup(Level.Trial)
    public void setup() {
        Random random = new Random(12345L);
        left = new BigInteger(bits, random).setBit(bits - 1);
        right = new BigInteger(bits, random).setBit(bits - 1);
    }

    @Benchmark
    public void multiply(Blackhole blackhole) {
        blackhole.consume(left.multiply(right));
    }
}
~~~

`@Param` makes JMH run separate size configurations, `@Setup` excludes data generation from the measured section, and `Blackhole` consumes the result. Across different sizes, throughput may change non-smoothly as the JDK switches algorithmic strategies, CPU/JVM optimizations, and GC activity. This is only an illustrative benchmark **multiplying two operands of equal bit length**; it does not cover division, modular exponentiation, or skewed-size multiplication. Do not compare JDKs/CPUs using measurements taken from different machines.

To actually run the JMH benchmark, the project needs `org.openjdk.jmh:jmh-core` and the `jmh-generator-annprocess` annotation processor configured, then run with an appropriate build-tool JMH launcher. Do not claim the class above runs standalone via `javac` with only the standard JDK.

## 12. Optimization Strategies Matched to the Real Cost Source

**Keep the value range actually required.** If requirements only reach `long`, use primitives with overflow checks. If the domain can exceed `long`, use BigInteger; do not switch to `double` for speed when exact integers are needed because `double` cannot represent all large integers accurately.

**Prefer better algorithms over local micro-tricks.** Avoid repeated BigInteger multiplications when a better mathematical expression exists: for example, exponentiation by squaring, divide-and-conquer, computing combinations with common-factor cancellation, or reducing early via modulus when mathematically valid. However, preserve exact operation semantics (especially negative numbers, integer division, remainders, and overflow if converting types).

**Reuse constants and avoid redundant parsing.** Use `BigInteger.ZERO`, `ONE`, `TWO`, and `valueOf(long)`; construct large data once outside the hot loop if it does not change. Avoid going through strings when direct mathematical APIs exist.

**Assess intermediate number costs properly.** A problem with a short output does not automatically mean a cheap computation path; `base.pow(hugeExponent).mod(modulus)` can build a massive result before reduction, whereas `modPow` is the proper design for modular exponentiation.

**Separate concurrency from arithmetic algorithms.** If multiple threads update a `BigInteger` via a shared variable, object immutability does not make `current = current.add(ONE)` atomic. Synchronization or atomic operations with appropriate conditional updates are needed; lock/GC contention and growing bit lengths both affect overall throughput.

**Pay attention to resource safety.** With external inputs, limit input/bit lengths, loop counts, exponents, and operations that can make results explode. With huge left shifts, large powers, or million-character decimal strings, the risk of exhausting memory/time is not caused by wrong arithmetic. Check bounds before allocating and apply system-level timeouts/quotas if needed.

**For cryptography:** BigInteger serves exact arithmetic, yet the runtime of many operations depends on operand size and content; do not assume regular operations are constant-time. When handling secrets, choose cryptographic libraries/implementations vetted for timing side channels and other security requirements; raw performance alone is insufficient as a criterion.

## 13. Common Mistakes

- **Treating BigInteger as an infinite-length `int` with O(1) cost:** large operands increase limb counts and allocations.
- **Timing 0/1 inputs and generalizing to all long numbers:** special values take different fast paths.
- **Assuming multiplication is always O(n²):** that is grade-school multiplication; the JDK may switch to faster algorithms at large sizes.
- **Claiming Karatsuba starts at one exact fixed bit length:** thresholds live inside the implementation, measured in limbs and other conditions, not as an API contract.
- **Considering only one operand:** multiplication/division depend on the shape of both operands.
- **Computing an enormous `pow` just to take modulo:** lack of intermediate result control; see `modPow`.
- **Calling `divide` and `remainder` separately when both are needed:** may duplicate work; see `divideAndRemainder`.
- **Benchmarking `new BigInteger(String)`, `toString`, or `println` inside the loop:** accidentally measuring conversion and I/O costs.
- **Using a single `System.nanoTime()` call to conclude algorithm complexity:** JIT, GC, noise, and code-path switches can dominate the sample.
- **Forgetting memory:** results and temporary buffers can be huge even when an API returns a single variable.
- **Taking `bitLength()` directly on negative numbers to measure absolute-value bits:** e.g., -1 gives bitLength 0; use `abs().bitLength()` when that is the desired measure.
- **Replacing negative division by a power of 2 with `shiftRight`:** different rounding direction.

## 14. Exercises and Hints

**Exercise 1.** Two positive numbers are both 1024 bits, and then each is increased to 2048 bits. Considering only grade-school O(n²) multiplication for balanced operands, roughly how much does the relative work change? Why must that ratio not be turned into an actual measured guarantee?

**Exercise 2.** Why can adding `(2^256 - 1) + 1` require touching many limbs even though the second operand is very short? What is the result's bit length?

**Exercise 3.** To compute `2^100000000 mod 97`, should you use `pow().mod()` or `modPow()`? Explain in terms of intermediate data size.

**Exercise 4.** For multiplying a 4096-bit operand and a 32-bit operand, why should you not directly compare it with multiplying two 4096-bit numbers and conclude all "4096-bit" multiplications behave the same?

**Exercise 5.** What is `BigInteger.valueOf(-1).bitLength()`? If you want to estimate the bit length of operand magnitude, what expression should you write?

**Exercise 6.** Design a JMH benchmark measuring multiplication times for 128×128, 1024×1024, and 4096×64 bit pairs. What must be excluded from the measured section to isolate multiplication as closely as possible?

**Answer hints:**

1. The O(n²) model predicts roughly **4×** when both lengths double; the implementation may use Karatsuba/Toom-Cook, different caches, and GC, so benchmarking is needed for the real ratio.
2. Carry can propagate across the limb chain; the result equals `2^256`, which has **257 bits**.
3. Use `modPow` to avoid constructing and holding the full `2^100000000` number when only the remainder is needed.
4. Grade-school multiplication costs O(nm), so both operands matter; real optimization paths may also differ.
5. `-1.bitLength()` by object semantics is **0**; use `x.abs().bitLength()` to measure magnitude (returns 1 for -1).
6. Pre-generate operands in `@Setup`, consume results via `Blackhole`, configure warmups/forks, and avoid parsing/formatting/logging in the measured region; document JDK/CPU/config.

## References

- Java SE 17, BigInteger API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html
- OpenJDK 17, BigInteger source code (multiplication/division paths and selection thresholds): https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/math/BigInteger.java
- OpenJDK JMH project: https://github.com/openjdk/jmh

**Takeaway:** the length of **both operands and intermediate results** heavily dictates `BigInteger` cost. Estimate using bit/limb counts to choose algorithms, and measure with proper benchmarks on real workloads to make optimization decisions.
