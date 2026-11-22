# Reordering Operations to Reduce Information Loss in Java

With `float` and `double`, two expressions that are **equivalent in real-number mathematics** can yield different results in Java. The reason is that floating-point numbers have only a finite number of significand and exponent bits; after each operation, the result may be rounded, losing tiny contributions, or become infinite/zero due to overflow and underflow.

A classic example:

```java
double large = 1e16;

double lost = (large + 1.0) - large; // 0.0
double kept = (large - large) + 1.0; // 1.0
```

Mathematically, both equal 1. However, `large + 1.0` rounds back to `large`: the value 1 is lost before subtraction is performed. When cancelling the two large numbers first, the value 1 is preserved.

**Core point:** calculation order is part of numerical algorithm design. We can reduce information loss by summing/grouping appropriately, avoiding subtracting nearly equal values, using more stable formulas, and controlling the magnitude of intermediate operations. However, **there is no single reordering rule that is always best for all data**. You must examine the input domain and measure error.

This lesson belongs to the **Error and stability** section in the **Java core – numbers** module. The focus is on how to apply these techniques and their limitations in Java 17+.

## 1. Why Can Order Change the Result?

`float` and `double` use IEEE 754 binary floating-point representation:

| Type | Significand precision bits (including implicit bit) | Range of consecutive integers represented accurately |
| --- | ---: | --- |
| `float` | 24 | From `-2^24` to `2^24` |
| `double` | 53 | From `-2^53` to `2^53` |

When an exact result falls between two representable numbers, the machine must round. In many basic operations, Java applies round-to-nearest and when equidistant chooses the value with an even least significant bit (*round to nearest, ties to even*).

The spacing between consecutive `double` values varies with magnitude. For instance:

```java
double x = 1e16;
System.out.println(Math.ulp(x));   // 2.0
System.out.println(x + 1.0 == x);  // true
System.out.println(x + 2.0 == x);  // false
```

`Math.ulp(x)` (*unit in the last place*) indicates the resolution step at `x`. Around `1e16`, the number 1 is smaller than a single step between adjacent representable values.

### Addition Is Not Associative Like Ideal Real Numbers

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double first = (a + b) + c;  // 1.0
double second = a + (b + c); // 0.0
```

The operation `a+b` cancels to 0 and then adding 1 loses no information; however, `b+c` is rounded to `b` first. Therefore, `(a+b)+c` does not necessarily equal `a+(b+c)` in floating-point arithmetic.

Multiplication can also be non-associative when rounding, overflow, or underflow occurs. Changing parentheses can make the result better **or** worse.

### Java 17 always-strict Does Not Fix Non-Associativity

Since Java 17, Java has *always-strict* semantics for floating-point expressions. This enforces stricter evaluation rules, but **does not grant infinite precision** and does not turn `+`, `*` into strictly associative operations like mathematical real numbers. Do not use `strictfp` expecting error loss to vanish automatically.

## 2. When a Large Sum Swallows Small Terms

Suppose we have the data:

```java
double[] values = {1e16, 1.0, 1.0, -1e16};
```

The mathematical sum is **2**. Yet if summed sequentially from left to right:

```java
double sum = 0.0;
for (double value : values) {
    sum += value;
}
System.out.println(sum); // 0.0
```

Progression:

```text
0                  initially
1e16               add very large number
1e16               add 1.0, but rounded away
1e16               add 1.0 again, still lost
0                  add -1e16 and cancel out
```

The two 1s cannot reappear at the final step because information was already lost in the two intermediate additions.

### Grouping by Numerical Meaning

In this example, if operations are allowed to be reordered, we can group the two large numbers to cancel out and the two small numbers to sum together:

```java
double better = (values[0] + values[3])
              + (values[1] + values[2]);
System.out.println(better); // 2.0
```

Or add the two small numbers first:

```java
double smallFirst = 1.0 + 1.0 + 1e16 - 1e16;
System.out.println(smallFirst); // 2.0
```

These are two examples that **improve the result for this exact dataset**, not a rule that "every sum must be sorted in ascending order of absolute value." With both positive and negative terms, cancellation can make a different ordering better. If the data represents a time-dependent state sequence, sometimes the order cannot be arbitrarily changed.

## 3. Three Strategies for Summing Many Numbers

| Method | Approach | Benefits | Limitations |
| --- | --- | --- | --- |
| Sequential summation (*naive summation*) | Loop `sum += x` | Low overhead, easy to understand | Small terms can be lost |
| Pairwise summation (*pairwise summation*) | Sum in a balanced tree | Typically reduces rounding steps per computation path | Result still depends on grouping |
| Compensated summation (*compensated summation*) | Keep part of the rounding error in an extra variable | Can preserve small contributions better | Not always exact, more complex |

### 3.1. Pairwise Summation

Instead of summing a long sequence from left to right, the pairwise algorithm splits the sequence in half, sums each half, and then adds the two half-sums. This reduces the summation depth of each element from linear to logarithmic in a balanced tree.

```text
x0 + x1 + x2 + x3 + x4 + x5 + x6 + x7

Pairwise add: s01    s23    s45    s67
Group add:        s0123        s4567
Final add:               total
```

Pairwise summation is often useful for long sequences and can be combined with parallelism. However, two different groupings can yield different results; there is no guarantee that every pairwise tree reduces error for every dataset with heavy cancellation.

### 3.2. Kahan Summation

The Kahan algorithm stores `sum` and a `compensation` variable to compensate for errors incurred during addition:

```java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double value : values) {
        double corrected = value - compensation;
        double next = sum + corrected;
        compensation = (next - sum) - corrected;
        sum = next;
    }

    return sum;
}
```

This is a method that must be placed inside a class. For `{1e16, 1, 1, -1e16}`, Kahan can recover the sum **2.0** by retaining the 1 rounded away in the early step and compensating in a later step.

**Kahan is not strictly exact addition.** In some adverse cancellation sequences, such as `{1e16, 1.0, -1e16}`, standard Kahan may still fail to return 1.0. When higher accuracy or stability is needed, consider Neumaier summation, higher-order compensated summation algorithms, multi-precision arithmetic, or a different data representation.

### 3.3. How to Choose

Use sequential summation when data is small or error requirements allow it. With large measurements, many elements, and significant summation error, test pairwise/Kahan against representative test datasets. If the calculation involves **strictly exact integers**, use `long`, `Math.addExact`, or `BigInteger` matching the domain; if it is money requiring decimal exactness, consider `BigDecimal`. Do not turn an exactness requirement into a "double addition trick" problem.

## 4. Canceling Nearly Equal Numbers: Catastrophic Cancellation

When subtracting two nearly equal numbers, the small result may contain **very few reliable significant digits**, even though each operand on its own has many digits.

Consider the formula:

```text
sqrt(1 + x) - 1
```

with `x = 1e-16`:

```java
double x = 1e-16;
double naive = Math.sqrt(1.0 + x) - 1.0;
System.out.println(naive); // 0.0
```

`1.0 + 1e-16` is rounded to `1.0`; then taking the square root and subtracting 1 yields zero. The input `x` has been lost even though the mathematical value of the expression remains positive near `5e-17`.

### 4.1. Conjugate Transformation

Within the domain where the expression is defined and the denominator is nonzero:

```text
sqrt(1 + x) - 1
= [sqrt(1 + x) - 1] * [sqrt(1 + x) + 1]
  / [sqrt(1 + x) + 1]
= x / [sqrt(1 + x) + 1]
```

A more stable formulation around `x=0`:

```java
double x = 1e-16;
double stable = x / (Math.sqrt(1.0 + x) + 1.0);
System.out.println(stable); // 5.0E-17
```

The numerator directly retains `x`, so even if `1.0+x` rounds to 1.0, the division still preserves the small contribution.

This illustrates the principle: **avoid computing the difference of two nearly equal quantities if a more stable equivalent formula exists**. However, you must consider the domain: the square root requires `1+x >= 0` in real numbers; at `x=-1` the denominator is still 1, while for extremely large values or special values like Infinity/NaN, evaluation must be checked separately.

### 4.2. Computation Cannot Be Fixed After Data Has Already Been Rounded Away

If two distinct mathematical values have already been stored as **the exact same `double` value**, subtracting them only sees the two stored values. Casting after subtraction or swapping operands will not recover the original information.

The fix must happen **before the information-losing step**: change the formula, keep small terms separate, use a higher-precision type, or work directly with the original data.

## 5. Choosing Math.log1p and Math.expm1 When x Is Near 0

The Java library provides functions to prevent information loss in two very common expressions.

### Math.log1p(x): Natural Log of 1+x

```java
double x = 1e-16;
double naive = Math.log(1.0 + x); // 0.0
double stable = Math.log1p(x);    // Positive number near 1e-16
```

When `x` is very small, `1.0+x` can round to 1, making `Math.log(1.0)` equal to 0. `Math.log1p` is designed for `ln(1+x)` and preserves accuracy much better in that region.

### Math.expm1(x): exp(x)-1

```java
double x = 1e-16;
double naive = Math.exp(x) - 1.0; // 0.0
double stable = Math.expm1(x);    // Positive number near 1e-16
```

In the direct calculation, `exp(x)` can round to 1 and then subtraction wipes out the result. `Math.expm1` avoids this kind of cancellation.

Both functions are useful in probability, statistics, growth models, and certain financial formulas; however, substitute them only when **the exact mathematical quantity needed is `ln(1+x)` or `exp(x)-1`**.

## 6. Regrouping Multiplication/Division to Avoid Intermediate Overflow and Underflow

An expression whose mathematical result lies within the `double` range can still fail if an **intermediate result** goes out of range.

### 6.1. Premature Overflow to Infinity

```java
double x = Double.MAX_VALUE;

double overflowFirst = (x * 2.0) / 2.0; // Infinity
double scaleFirst = x * (2.0 / 2.0);    // Double.MAX_VALUE
```

Mathematically both equal `x`. Yet `x*2` on the first line overflows to infinity; dividing infinity by 2 does not bring it back to finite. The second line forms the ratio 1 first and therefore does not overflow.

### 6.2. Premature Underflow to Zero

```java
double tiny = 1e-300;

double underflowFirst = (tiny * tiny) / tiny; // 0.0
double ratioFirst = tiny * (tiny / tiny);     // 1.0E-300
```

`tiny*tiny` has magnitude `1e-600`, too small to store in `double`; the value rounds to 0. Computing the ratio `tiny/tiny=1` first avoids the problem for this dataset.

**Note:** "dividing first" is not always good. When a denominator may be zero, very small, very large, or contain NaN/Infinity, changing order can introduce new bugs. You must verify the domain, sign, bounds, and error policy.

### 6.3. Math.hypot Avoids Squaring Before Taking the Square Root

Length of a 2D vector:

```text
sqrt(x² + y²)
```

If computed directly:

```java
double x = 1e200;
double y = 1e200;
double naive = Math.sqrt(x * x + y * y); // Infinity
```

Because `x*x` already exceeds the finite range of `double`, the result is infinity, even though the true length around `1.414e200` is still finite.

`Math.hypot(x, y)` uses a more stable computation for the square root of the sum of squares, avoiding unnecessary intermediate overflow/underflow:

```java
double better = Math.hypot(1e200, 1e200);
System.out.println(Double.isFinite(better)); // true
```

`Math.hypot` does not guarantee a finite result for every input: if the **mathematical length** exceeds the representable range, the result can still be infinite.

## 7. Math.fma: Reducing One Rounding in Multiply-Add

`Math.fma(a, b, c)` computes `a*b+c` using a *fused multiply-add*, with a single rounding at the end. In contrast, the expression `a*b+c` may round after multiplication and round again after addition.

```java
double u = Math.ulp(1.0);
double a = 1.0 + u;
double b = 1.0 - u;

double separate = a * b - 1.0;     // 0.0
double fused = Math.fma(a, b, -1.0); // A very small negative number.
```

The exact product is `(1+u)(1-u)=1-u²`. Separate multiplication rounds to 1, and then subtracting 1 yields 0. FMA retains the value before final rounding and can produce a nonzero negative result.

FMA is helpful in some vector, polynomial, and multiply-accumulate algorithms, but **it does not mean every computation is strictly exact**. Because it produces different results from separate multiply/add, do not substitute it arbitrarily if the system requires bit-for-bit compatibility.

## 8. Reordered Computation Must Still Respect Types and Ranges

Operation order is not only a floating-point issue; an integer operation can **overflow before converting to `double`**:

```java
int count = 1_500_000_000;

double wrong = count * 3;          // int product overflows before assignment.
double floating = (double) count * 3; // double multiplication, no int overflow.
long exact = (long) count * 3;     // 4_500_000_000L, exact integer.
```

If an **exact integer** result is required, `long` is better when its range suffices, or `Math.multiplyExact`/`BigInteger` can be used when checking is needed. Converting to `double` avoids overflow in this example, but can lose unit precision for integers larger than `2^53`.

Division must also be watched: `int/int` drops the fractional part before assigning to `double`; cast **one operand to `double` before division** if you want an approximate ratio.

## 9. Measure Error Instead of Eyeballing Results

An ordering should only be called "better" when there is a **reference value** or an error criterion.

Two common metrics:

```text
absolute_error = |result - reference|
relative_error = absolute_error / |reference|
```

Relative error cannot be used directly when the reference is 0. When the true result is near 0, an absolute threshold with units, sensitivity analysis, or a clear domain rule is needed.

For example, the sum of `{1e16,1,1,-1e16}` has an exact mathematical reference of 2. Sequential summation gives 0 so the absolute error is 2; grouping and Kahan give 2 so the error is 0 **for this specific dataset**.

Distinguish between:

- **Problem conditioning** (*conditioning*): a tiny change in input can cause a relatively large change in the mathematical result; especially with the difference of two nearly equal numbers.
- **Numerical stability** (*numerical stability*): does the algorithm amplify error unnecessarily due to operation order and intermediate representation?

A more stable algorithm cannot eliminate error already present in measured data. You need to know the source precision and acceptable error before changing formulas.

### Checklist for Evaluating a Transformation

1. Identify data meaning: approximate measurement, exact integer sum, currency, or index?
2. Read the type of **each subexpression**: which operation already overflowed or rounded before assignment?
3. Check if many very small numbers are added to a large sum; can grouping, pairwise, or compensated summation replace it?
4. Check if two nearly equal values are subtracted; is there an equivalent formula avoiding cancellation?
5. For multiplication/division, check intermediate overflow/underflow and denominator domain.
6. Use `Math.log1p`, `Math.expm1`, `Math.hypot`, `Math.fma` when matching the purpose and applicability conditions.
7. Write tests with ground-truth results and evaluate unit-aware absolute/relative error.
8. Test positive/negative cases, heavy cancellation, zero, very large/very small numbers, NaN, and Infinity.
9. Control computation order in parallel tasks if bit-for-bit reproducibility is needed.
10. Do not assume a parenthesization that looks reasonable on sample data is always good across the whole domain.

## 10. Complete Java 17+ Program

Create the file **`CalculationOrderDemo.java`**:

```java
public class CalculationOrderDemo {
    static double naiveSum(double[] values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static double kahanSum(double[] values) {
        double sum = 0.0;
        double compensation = 0.0;
        for (double value : values) {
            double corrected = value - compensation;
            double next = sum + corrected;
            compensation = (next - sum) - corrected;
            sum = next;
        }
        return sum;
    }

    public static void main(String[] args) {
        double large = 1e16;

        System.out.println("lost=" + ((large + 1.0) - large));
        System.out.println("kept=" + ((large - large) + 1.0));
        System.out.println("ulp=" + Math.ulp(large));

        double[] values = {1e16, 1.0, 1.0, -1e16};
        System.out.println("naive-sum=" + naiveSum(values));
        System.out.println("grouped-sum=" +
                ((values[0] + values[3]) + (values[1] + values[2])));
        System.out.println("kahan-sum=" + kahanSum(values));

        double max = Double.MAX_VALUE;
        System.out.println("overflow-first=" +
                Double.isInfinite((max * 2.0) / 2.0));
        System.out.println("scale-first=" +
                (max * (2.0 / 2.0) == max));

        double tiny = 1e-300;
        System.out.println("underflow-first=" +
                ((tiny * tiny) / tiny));
        System.out.println("ratio-first=" +
                (tiny * (tiny / tiny)));

        double x = 1e-16;
        System.out.println("root-naive=" +
                (Math.sqrt(1.0 + x) - 1.0));
        System.out.println("root-stable=" +
                (x / (Math.sqrt(1.0 + x) + 1.0)));
        System.out.println("log-naive=" + Math.log(1.0 + x));
        System.out.println("log1p-positive=" + (Math.log1p(x) > 0.0));
        System.out.println("expm1-positive=" + (Math.expm1(x) > 0.0));

        double huge = 1e200;
        double naiveHypot = Math.sqrt(huge * huge + huge * huge);
        System.out.println("hypot-naive-infinite=" +
                Double.isInfinite(naiveHypot));
        System.out.println("hypot-stable-finite=" +
                Double.isFinite(Math.hypot(huge, huge)));

        double ulp = Math.ulp(1.0);
        double a = 1.0 + ulp;
        double b = 1.0 - ulp;
        System.out.println("fma-separate-zero=" +
                (a * b - 1.0 == 0.0));
        System.out.println("fma-negative=" +
                (Math.fma(a, b, -1.0) < 0.0));
    }
}
```

Compile and run:

```bash
javac CalculationOrderDemo.java
java CalculationOrderDemo
```

Stdout:

```text
lost=0.0
kept=1.0
ulp=2.0
naive-sum=0.0
grouped-sum=2.0
kahan-sum=2.0
overflow-first=true
scale-first=true
underflow-first=0.0
ratio-first=1.0E-300
root-naive=0.0
root-stable=5.0E-17
log-naive=0.0
log1p-positive=true
expm1-positive=true
hypot-naive-infinite=true
hypot-stable-finite=true
fma-separate-zero=true
fma-negative=true
```

**How to read the output:** `lost`/`kept` and the three summation approaches show how small data can be lost or preserved; `overflow-first`/`underflow-first` show how intermediate values determine the result; `root-stable`, `log1p-positive`, and `expm1-positive` show more stable formulas/functions near 0; `Math.hypot` avoids squaring overflow; and the two FMA lines show that removing one rounding step can make the result differ from separate multiplication and subtraction.

## 11. Common Mistakes

| Mistake | Harm | Remedy |
| --- | --- | --- |
| Assuming `(a+b)+c` always equals `a+(b+c)` | Small terms lost or different results | Analyze ULP and test boundary data |
| Adding all small numbers after the sum is already huge | Small contributions can be swallowed | Try grouping, pairwise, or Kahan |
| Claiming you must always sum in ascending order of magnitude | Not true for all signed sequences; can alter semantics | Reorder only when the domain allows, and measure error |
| Assuming Kahan is always exact | Some cancellation cases still fail under Kahan | Test, consider Neumaier or higher precision |
| Taking the difference of two nearly equal numbers without checking error | Loss of many significant digits | Use a cancellation-avoiding formula, e.g., conjugate |
| Computing `log(1+x)` or `exp(x)-1` when x is too small | Result can collapse to zero | Use `log1p` and `expm1` for their intended purpose |
| Computing `sqrt(x*x+y*y)` for large x, y | Squaring can become infinite | Use `Math.hypot` |
| Thinking dividing first is always safe | Can divide by 0 or fail in other domains | Prove conditions and test |
| Thinking `Math.fma` and `a*b+c` must always match bit-for-bit | Different number of rounding steps | Choose per algorithm, watch compatibility |
| Casting after an integer multiplication has already overflowed | Value is already lost before the cast | Widen type first, use checked arithmetic |
| Using `double` for quantities/money that must be exact | Cannot guarantee preserving every unit | Use exact integer or decimal types |
| Looking at only a few plausible output lines | Misses near-limit and cancellation cases | Use reference results and error metrics |

## 12. Practice Exercises

**Exercise 1 – Order and ULP.** Compute `Math.ulp(1e16)`; predict `(1e16+1)-1e16` and `(1e16-1e16)+1`. Why do the two answers differ?

**Exercise 2 – Sum of four numbers.** Given `{1e16, 1.0, 1.0, -1e16}`, compute the mathematical sum, sequential sum, grouped sum, and Kahan sum. Permute the data and observe changes.

**Exercise 3 – Counterexample for Kahan.** Try `{1e16, 1.0, -1e16}`. Can using Kahan alone guarantee an exact sum of 1.0? Explain.

**Exercise 4 – Cancellation near zero.** Prove via conjugate that `sqrt(1+x)-1 = x/(sqrt(1+x)+1)`. Test `x=1e-16`; state the domain.

**Exercise 5 – Stable library functions.** Use `Math.log1p` and `Math.expm1` to compute expressions equivalent to `log(1+x)` and `exp(x)-1` when x is near 0. Compare errors against high-precision results.

**Exercise 6 – Intermediate overflow/underflow.** Explain the difference between `(Double.MAX_VALUE*2)/2` and `Double.MAX_VALUE*(2/2)` with double literals. Do the same for `1e-300` multiplication/division.

**Exercise 7 – Vector length.** Compare `Math.sqrt(x*x+y*y)` with `Math.hypot(x,y)` when `x=y=1e200` and when `x,y` are very small. Does the mathematical result lie within the double range?

**Exercise 8 – FMA and reproducibility.** Write a test for `Math.fma(a,b,-1)` with `a=1+ulp(1)`, `b=1-ulp(1)`. Why can using FMA change the bitwise result?

**Exercise 9 – Real-world design.** A system aggregating millions of measurements across parallel workers needs stable and repeatable results. How would you fix the reduction tree, which summation algorithm would you choose, how would you handle NaN/Infinity, and how would you measure error?

## 13. Key Takeaways

- Floating-point addition and multiplication are **not generally associative**; changing order can affect the result.
- Terms too small relative to the running sum can be rounded away; grouping, pairwise, or Kahan can improve results but do not guarantee strict exactness.
- Subtracting two nearly equal numbers can lose significant digits; prefer transforming the formula to avoid cancellation when possible.
- `Math.log1p`, `Math.expm1`, and `Math.hypot` solve common forms of intermediate information loss.
- Multiplying/dividing in an unsuitable order can overflow to Infinity or underflow to zero before the final result is computed.
- `Math.fma` differs from separate multiply-and-add expressions because it rounds only once.
- Choose a type sufficiently accurate for the data domain; **no reordering trick replaces `BigInteger`, `BigDecimal`, or checked arithmetic when business logic requires exactness**.
- Every stability optimization should be backed by **reference results, boundary tests, and error criteria**.

**Conclusion:** changing operation order can reduce information loss in Java, but only once you understand the error source and data domain. Choose a more stable formula/algorithm based on verification, rather than changing parentheses out of habit.
