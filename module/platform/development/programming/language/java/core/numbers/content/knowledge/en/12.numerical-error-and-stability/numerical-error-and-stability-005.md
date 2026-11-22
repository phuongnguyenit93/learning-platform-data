# Compensated Summation and the Idea Behind Kahan Summation

When summing many floating-point numbers in Java using `double`, a loop `sum += x` can accumulate rounding error. In particular, a small number added to an already very large sum can **fail to change the sum at all**, even though that small number is practically meaningful. **Kahan summation** (*compensated summation*) uses an extra variable to record part of the discrepancy during additions and then compensates for it in subsequent additions.

Example:

```java
double sum = 0.0;
for (int i = 0; i < 10; i++) {
    sum += 0.1;
}
System.out.println(sum); // 0.9999999999999999
```

With the same elements, the Kahan version in this lesson produces `1.0`. However, **Kahan does not turn `double` into strictly exact arithmetic**: it reduces one kind of error during summation, and cannot fix every input error or every cancellation scenario.

## 1. Sources of Error When Computing a Sum

`double` is a 64-bit binary floating-point type with **53 bits of effective significand precision**. Not every decimal number is representable in finite binary: `0.1` is stored only as an approximate value. Then each addition on `double` can also round the result to the nearest representable number.

There are two error sources to distinguish:

1. **Representation error:** an entered value such as `0.1` has already been converted to an approximate binary number. Kahan does not recover the exact original decimal meaning.
2. **Addition error:** some low-order bits of the mathematical result can be lost after each `+` operation. Kahan is designed to limit this accumulated error component.

Computer floating-point addition is **not strictly associative**:

```java
double a = 1e16;
double b = 1.0;
double c = -1e16;

double first = (a + b) + c;  // 0.0
double second = (a + c) + b; // 1.0
```

Mathematically, the sum is `1` in both cases. However, at magnitude `1e16`, the spacing (ULP) between two consecutive `double` numbers is **2**. Thus `1e16 + 1.0` falls between two representable numbers and rounds back to `1e16`. If the two large numbers cancel first, the `1.0` contribution is preserved.

A more practical example: adding `10_000` values of `1.0` to `1e16` in the ordinary way, each `1.0` can be dropped one by one due to rounding. The result remains `1e16` instead of the mathematical sum `1e16 + 10000`.

## 2. The Idea: Do Not Discard the Small Part After Each Addition

If `sum` is very large and `x` is small, `sum + x` can return `sum` itself because `double` lacks sufficient resolution there. Kahan attempts to capture **the portion of the change that the addition failed to fold into the sum**, in order to adjust the next term.

The algorithm has two state variables:

- `sum`: the current approximate sum.
- `compensation` (often denoted `c`): a signed compensation quantity tracking part of the rounding loss. This is **not the true absolute error** relative to the ideal mathematical sum.

For each element `x`, execute in exact order:

```java
double y = x - compensation;
double t = sum + y;
compensation = (t - sum) - y;
sum = t;
```

Interpretation:

1. `y = x - compensation`: adjusts the new term by the accumulated compensation.
2. `t = sum + y`: performs ordinary floating-point addition, which may still round.
3. `compensation = (t - sum) - y`: determines the discrepancy between the reflected increment and the intended term `y`.
4. `sum = t`: accepts the new sum for the next iteration.

**Do not update `sum` before the line computing `compensation`**. The third line needs the value of `sum` before it changes.

### Intuitive Example with `1e16` and `1`s

Suppose `sum = 1e16` and `compensation = 0`:

- For `x = 1`, `y = 1`. Adding `1e16 + 1` rounds back to `1e16`, so `t - sum = 0` and `compensation = -1`.
- For the next `x = 1`, `y = 1 - (-1) = 2`. At magnitude `1e16`, an increment of `2` is representable, and the contribution from the two `1`s will be reflected.
- The process continues, instead of dropping each small number like an ordinary `sum += 1` loop.

The negative sign of the compensation in this example means the missing addition will be **added back** in a later step. Do not assume `compensation` is always positive.

## 3. Basic Kahan Function in Java 17+

```java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double x : values) {
        double y = x - compensation;
        double t = sum + y;
        compensation = (t - sum) - y;
        sum = t;
    }

    return sum;
}
```

This is an **illustrative method** to be placed inside a class. An empty array gives `0.0` with this initialization. The basic version assumes **finite** inputs and intermediate results; handling `NaN`, infinity, and overflow requires a separate policy.

Reference function using ordinary addition:

```java
static double naiveSum(double[] values) {
    double sum = 0.0;
    for (double x : values) {
        sum += x;
    }
    return sum;
}
```

Both functions pass over the elements once, having **`O(n)` time complexity** and **`O(1)` auxiliary memory**. Kahan incurs a few extra subtractions/additions per element, in exchange for potentially reducing accumulated error significantly.

**What Kahan does not guarantee:** a `double` result with 53 effective significand bits may still be unable to represent the mathematical sum. For instance, `1e16 + 1` has no exact `double` representation; even if the algorithm knows "the lost part," a single returned `double` cannot hold all the information of this sum. Kahan is especially useful when **many** small parts can accumulate and compensate gradually.

## 4. Complete Java Program: Comparing Naive, Kahan, and Neumaier Summation

Save the file `KahanDemo.java`:

```java
public class KahanDemo {
    static double naive(double[] values) {
        double sum = 0.0;
        for (double x : values) {
            sum += x;
        }
        return sum;
    }

    static double kahan(double[] values) {
        double sum = 0.0;
        double compensation = 0.0;

        for (double x : values) {
            double y = x - compensation;
            double t = sum + y;
            compensation = (t - sum) - y;
            sum = t;
        }
        return sum;
    }

    static double neumaier(double[] values) {
        double sum = 0.0;
        double correction = 0.0;

        for (double x : values) {
            double t = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - t) + x;
            } else {
                correction += (x - t) + sum;
            }
            sum = t;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        double[] tenths = new double[10];
        java.util.Arrays.fill(tenths, 0.1);
        System.out.println("0.1 x 10 naive: " + naive(tenths));
        System.out.println("0.1 x 10 Kahan: " + kahan(tenths));

        double[] mixed = new double[10_001];
        mixed[0] = 1e16;
        java.util.Arrays.fill(mixed, 1, mixed.length, 1.0);
        System.out.println("large + ones naive extra: " + (naive(mixed) - 1e16));
        System.out.println("large + ones Kahan extra: " + (kahan(mixed) - 1e16));

        double[] cancel = {1e16, 1.0, -1e16};
        System.out.println("cancellation naive: " + naive(cancel));
        System.out.println("cancellation Kahan: " + kahan(cancel));
        System.out.println("cancellation Neumaier: " + neumaier(cancel));

        double[] finite = {1.0, 2.0, 3.0};
        System.out.println("simple Kahan: " + kahan(finite));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac KahanDemo.java
java KahanDemo
```

Stdout:

```text
0.1 x 10 naive: 0.9999999999999999
0.1 x 10 Kahan: 1.0
large + ones naive extra: 0.0
large + ones Kahan extra: 10000.0
cancellation naive: 0.0
cancellation Kahan: 0.0
cancellation Neumaier: 1.0
simple Kahan: 6.0
```

The results show:

- **Ten additions of `0.1`:** the naive version prints a value slightly less than 1.0, while Kahan prints 1.0.
- **A sum of `1e16` followed by 10,000 `1`s:** the naive version fails to keep the increment; Kahan retains the full `10000.0` in this test.
- **Sequence `[1e16, 1, -1e16]`:** the mathematical sum is 1, yet both naive addition and basic Kahan return 0.0. The Neumaier version returns 1.0.
- **Simple sequence `[1,2,3]`:** addition has no issue and Kahan also returns the exact sum.

Do not conclude that Kahan always yields more accurate digits in every example just because the initial cases succeed.

## 5. Important Limitation: Large-Number Cancellation Can Defeat Kahan

The case `[1e16, 1, -1e16]` has a mathematical sum of 1.0, yet basic Kahan returns 0.0. The cause lies in how the compensation is updated: when the term `-1e16` arrives, **the adjustment `y = x - compensation` itself** can round and lose the information of `1`. Then the two large numbers cancel out, and the small part is no longer in the sum.

This is why Kahan is not a general-purpose "exact summation algorithm." Error on sequences with **sign changes, heavy cancellation, or abrupt magnitude changes** can be more subtle than when summing only positive numbers.

A related method is **Neumaier summation**, which uses a `correction` variable to accumulate compensation separately from the sum:

```java
static double neumaierSum(double[] values) {
    double sum = 0.0;
    double correction = 0.0;

    for (double x : values) {
        double t = sum + x;
        if (Math.abs(sum) >= Math.abs(x)) {
            correction += (sum - t) + x;
        } else {
            correction += (x - t) + sum;
        }
        sum = t;
    }

    return sum + correction;
}
```

Neumaier compares the magnitudes of the two operands to choose how to estimate the addition loss, and then **adds the correction when returning the result**. This helps in some cancellation cases where basic Kahan fails. Nevertheless, `correction` is still a `double` and can also round; **Neumaier does not always achieve the exact mathematical sum**.

The differences can be summarized:

| Method | How compensation is kept | Strengths | Limitations |
| --- | --- | --- | --- |
| `sum += x` | No compensation variable | Simple, fast | Easily loses small numbers |
| Kahan | Adjusts next term using `compensation` | Reduces accumulated error on many sequences | Still fails on difficult cancellation sequences |
| Neumaier | Accumulates `correction` separately, adds to sum at the end | Can handle some cancellation cases better | Also limited by `double` and arithmetic order |

## 6. Error, Stability, and Summation Order

A fundamental property of computer floating-point summation is that **order affects the result**. Consider `[1e16, 1, -1e16]`: changing the order to `[1e16, -1e16, 1]` can yield the exact result 1.0 even with naive addition. However, you should not arbitrarily reorder inputs if order carries business meaning, nor assume there is one optimal order for every sequence.

Algorithmically, distinguish between:

- **Absolute error:** `|computed - reference|` when a sufficiently accurate reference value is known.
- **Relative error:** absolute error divided by the magnitude of the reference sum, often not very meaningful if the true sum is near 0.
- **Problem conditioning:** the sum of many large numbers with opposite signs can be near 0; even a tiny change in input data causes relative error to spike.
- **Operation error:** the extra portion introduced when the algorithm uses floating-point operations, which is what Kahan tries to limit.

You can choose Kahan to be **more stable** over a data domain while still having no "absolute exactness" guarantee. If inputs were already rounded during measurement or when converting large integers to `double`, compensated summation cannot recover the exact original input values.

### Performance and Reproducibility

Sequential Kahan summation uses **`O(n)` time** and **`O(1)` auxiliary memory**. It performs more operations than naive summation, and the compensation state depends on **order**. Therefore, multiple threads must never arbitrarily update shared `sum`/`compensation`: besides data races, it breaks the compensation sequence.

In parallel reduction, separate partial sums can be computed and combined in a controlled manner. However, the final result may differ at the bit level from sequential summation due to different operation grouping. If reproducibility is required, specify the exact reduction order/strategy and test with that exact algorithm.

## 7. When Should Kahan Not Be Used as the Sole Solution?

### `NaN`, Infinity, and Overflow

The compensation formula contains the subtraction `t - sum`. If `sum` or `t` becomes infinite, `Infinity - Infinity` can produce NaN and subsequently turn `compensation` or the final result into NaN. Kahan is **not responsible** for handling floating-point data exceptions.

For applications accepting only finite numbers:

```java
for (double x : values) {
    if (!Double.isFinite(x)) {
        throw new IllegalArgumentException("non-finite input");
    }
}
```

This is a snippet inside a method. Checking finite inputs does not guarantee that **intermediate additions will not overflow**; you must evaluate the data domain and validate outputs per system requirements. Do not turn NaN into 0 unless data policy permits it.

### Exact Decimal Numbers: Use an Appropriate Representation

If the problem requires exact summation of decimal numbers from strings (such as currency), consider `BigDecimal`:

```java
java.math.BigDecimal total = java.math.BigDecimal.ZERO;
for (int i = 0; i < 10; i++) {
    total = total.add(new java.math.BigDecimal("0.1"));
}
System.out.println(total); // 1.0
```

This is an **illustrative snippet** to be placed inside a method. `new BigDecimal("0.1")` holds the exact one-tenth decimal value per the string. **`new BigDecimal(0.1)` is not equivalent** because the `double` constructor reflects the stored binary value near `0.1`; if the source is a decimal string, parse directly from the string to preserve source meaning.

For integer quantities, you can use `long`, `BigInteger`, or an appropriate integer unit, and check for overflow. Using the right data type from the beginning can be simpler than trying to compensate for `double` errors.

### More Accurate Summation with Other Algorithms

Besides Neumaier, **pairwise summation** splits the sequence into groups and sums sub-sums in a balanced tree; it generally improves error over naive summation, especially for long sequences, and fits some divide-and-conquer models better. Yet results still depend on grouping and are not strictly exact.

Libraries/systems with **extended-precision accumulators** can be considered if the domain has very strict requirements; basic compensated summation does not guarantee every input bit pattern is summed exactly before rounding the final result.

## 8. Use in Statistical Sums and Averages

To compute the average of a sequence with `n > 0`, writing:

```java
double mean = kahanSum(values) / values.length;
```

improves the summation step over an ordinary loop on suitable sequences. However, the final division still produces a rounded `double`. If the intermediate sum could overflow to infinity even though the mean is within range, use an averaging method designed to avoid intermediate overflow; basic Kahan does not solve that case.

In sensor data, simulation statistics, time accumulation, or summing quantities of varying magnitudes, Kahan can be a good choice thanks to its tiny auxiliary memory. Still, distinguish **numerical accuracy** from **measurement reliability**: the algorithm does not remove sensor error, NaN, or input data errors.

### Useful Test Plan

Evaluate the algorithm on sequences with clear expected behavior:

1. Short exact sequence: `[1, 2, 3]` → 6.
2. Decimal sequence: ten `0.1`s.
3. Large magnitude gap: `1e16` plus many `1.0`s.
4. Heavy cancellation: `[1e16, 1, -1e16]`.
5. Negative/positive sequences, long sequences, data sorted in various orders.
6. Data with NaN, Infinity, and near-boundary values (if possible inputs).

Whenever possible, use a reference sum computed with exact arithmetic or high precision from **trustworthy source data**, and measure absolute and relative error. Never assume an algorithm is right just because it matches another algorithm's output.

## 9. Common Misconceptions

1. **"`double` always adds small integers accurately."** False: even though each `1` is represented accurately, `1e16 + 1` still rounds.
2. **"Kahan gives `0.1` an exact decimal representation."** False: it does not alter the bits of input values.
3. **"Just adding a `compensation` variable makes every sequence sum exact."** False: `[1e16, 1, -1e16]` still yields 0.0 with basic Kahan.
4. **"`compensation` is the total absolute error."** False: it is a signed correction state, not a mathematical reference value.
5. **"You can update `sum` before computing `compensation`."** False: the formula needs the old `sum`.
6. **"Kahan does not depend on summation order."** False: operations still round and results can depend on order.
7. **"Neumaier is always strictly exact."** False: it still involves `double` operations and error.
8. **"`BigDecimal` constructed from an arbitrary `double` recovers lost digits."** False: an already rounded source cannot invert itself automatically.
9. **"Kahan is suitable for silently ignoring NaN and infinity."** False: an explicit input handling policy is required.
10. **"Kahan can safely update a shared `sum` from multiple threads."** False: it depends on compensation order and suffers from data races.
11. **"Printing `1.0` proves every calculation step was exact."** False: it is merely a final formatted value.
12. **"Sum accuracy and sensor data accuracy are the same thing."** False: a summation algorithm cannot fix initial measurement error.

## 10. Self-Check Questions

**1. Why can `1e16 + 1` equal `1e16` in `double`?** Because ULP near `1e16` is 2, so adding 1 can be rounded away.

**2. What is the role of `compensation`?** It stores part of the discrepancy caused by rounding in addition, to adjust the term in the next addition.

**3. Why must `compensation = (t - sum) - y` be computed before `sum = t`?** Because the formula needs the old `sum`.

**4. Does a sequence of ten `0.1` values get stored as exact decimals in `double` thanks to Kahan?** No; the input values remain binary numbers close to `0.1`.

**5. For `[1e16, 1, -1e16]`, what are the mathematical sum and Kahan sum?** The mathematical sum is 1; basic Kahan in the example gives 0.0, while Neumaier gives 1.0.

**6. How does Kahan's auxiliary memory depend on `n`?** `O(1)` for sequential summation because only one compensation variable is added.

**7. If you need the exact sum of decimal values from strings, what should you use?** An appropriate exact decimal representation such as `BigDecimal` from strings, or integers in a standard unit if suitable.

**8. If the input contains infinity, can you trust Kahan to give a more reasonable result than naive addition?** No. Compensated additions/subtractions can turn `compensation` into NaN; you must check the domain and handle exceptions per problem requirements.

**Takeaway:** Kahan summation uses **a `sum` and a `compensation`** to reduce the harm of accumulated rounding error. It is often better than naive summation on long sequences with disparate magnitudes, still runs in `O(n)` time, and uses `O(1)` auxiliary memory. However, it **does not turn computer floating point into exact arithmetic**, nor does it guarantee handling heavy cancellation, NaN/Infinity, or overflow. Choose Kahan, Neumaier, pairwise, or exact numeric representations based on **error requirements, data, and value domain**.
