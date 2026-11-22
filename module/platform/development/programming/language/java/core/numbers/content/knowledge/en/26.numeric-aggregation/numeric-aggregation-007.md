# How Addition Order Affects Floating-Point Sums in Java

## 1. Problem and Goal

In mathematics, real-number addition is associative: \((a+b)+c=a+(b+c)\). With `double` or `float` in Java, **changing the order of addition can change the stored result**. The reason is that computers store floating-point numbers using a finite number of bits and must round intermediate results that cannot be represented exactly.

This property matters when aggregating millions of records, computing scores, gathering statistics, processing values of widely differing magnitudes, reordering elements, or combining results from parallel tasks.

After this lesson, you will be able to explain the source of the error, reproduce order-dependent results in Java 17, distinguish strategies for improving accuracy, and decide when to use `BigDecimal` instead of `double`.

## 2. Limits of Floating-Point Representation

Java uses the IEEE 754 binary floating-point format for `float` (32 bits) and `double` (64 bits). `float` has roughly 24 bits of significand precision, while `double` has 53 bits (approximately 15–17 significant decimal digits).

Values like `0.1` and `0.2` have no exact finite binary representation. When creating a `double` with the literal `0.1`, the machine stores the nearest binary value. Every subsequent addition can produce a result lying between representable values and therefore must be rounded.

**The spacing between two consecutive representable numbers varies with the magnitude of the number.** When a running sum is very large, adding a small number may not change the sum at all. `Math.ulp(x)` gives the size of one step (*unit in the last place*) at `x`.

### Java 17 Example: A Small Term Is Lost

Save as `FloatingUlpDemo.java`:

~~~java
public class FloatingUlpDemo {
    public static void main(String[] args) {
        double large = 1.0e16;

        System.out.println("ulp = " + Math.ulp(large));
        System.out.println("unchanged = " + (large + 1.0 == large));
        System.out.println("add before cancel = "
                + ((large + 1.0) - large));
        System.out.println("cancel before add = "
                + ((large - large) + 1.0));
    }
}
~~~

Run with JDK 17 or newer:

~~~bash
javac FloatingUlpDemo.java
java FloatingUlpDemo
~~~

Output:

~~~text
ulp = 2.0
unchanged = true
add before cancel = 0.0
cancel before add = 1.0
~~~

Both `large` and `1.0` are exactly representable in `double`. Yet around `1.0e16`, the representable step size is `2.0`. When adding `1.0`, the exact result falls halfway between two representable values; rounding pushes the result back to `large`. Thus the `1.0` contribution is gone and cannot be recovered by the later subtraction.

## 3. Non-Associativity: Grouping and Order Change the Sum

Denoting rounding to the floating-point type by `fl`, the two expressions

\[
\mathrm{fl}(\mathrm{fl}(a+b)+c)
\quad\text{and}\quad
\mathrm{fl}(a+\mathrm{fl}(b+c))
\]

have different intermediate steps. They do not necessarily produce the same result.

### Java 17 Example: Same Three Numbers, Two Sums

Save as `FloatingAssociativityDemo.java`:

~~~java
public class FloatingAssociativityDemo {
    public static void main(String[] args) {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        double left = (a + b) + c;
        double right = a + (b + c);

        System.out.println("left = " + left);
        System.out.println("right = " + right);
        System.out.println("same = " + (left == right));
    }
}
~~~

~~~bash
javac FloatingAssociativityDemo.java
java FloatingAssociativityDemo
~~~

Output:

~~~text
left = 1.0
right = 0.0
same = false
~~~

The mathematical sum is `1`. The left-hand side cancels the two large numbers first and then adds `1`. The right-hand side adds `1` to the large negative number first, causing the small contribution to be rounded away. Changing the **element order** from `[1e16, 1, -1e16]` to `[1e16, -1e16, 1]` in a left-to-right loop can likewise change the result from `0.0` to `1.0`.

**Consequence:** you cannot arbitrarily apply algebraic transformations of real-number addition to `double` and expect bit-identical results. Java evaluates expressions with specific intermediate operations; each step can lose information.

## 4. Accumulated Error When Adding Repeatedly

Even without huge numbers, repeating addition can accumulate error differently than an equivalent multiplication. For instance, `0.1` is an approximate binary number; ten additions round differently than `10 * 0.1`.

Save as `RepeatedFloatingSumDemo.java`:

~~~java
public class RepeatedFloatingSumDemo {
    public static void main(String[] args) {
        double sum = 0.0;
        for (int i = 0; i < 10; i++) {
            sum += 0.1;
        }
        double product = 10 * 0.1;

        System.out.println("repeated = " + sum);
        System.out.println("product = " + product);
        System.out.println("equal = " + (sum == product));
    }
}
~~~

~~~bash
javac RepeatedFloatingSumDemo.java
java RepeatedFloatingSumDemo
~~~

Output:

~~~text
repeated = 0.9999999999999999
product = 1.0
equal = false
~~~

`println(double)` prints a short decimal string that converts back to the same `double`, not all of its binary bits. Seeing `println(0.1)` print `0.1` **does not mean `0.1` is stored exactly**.

Rounding error does not necessarily grow monotonically: sometimes errors point in the same direction, and sometimes they cancel out. The outcome depends on the magnitudes, signs, and order of the numbers being added.

## 5. Swamping and Cancellation

Two phenomena should be separated:

1. **Swamping:** a term very small relative to the current sum can be smaller than `double`'s resolution there, leaving the sum unchanged after addition.
2. **Cancellation:** two nearly opposite values produce a small sum. Pre-existing errors in the terms or intermediate steps can become large relative to that small result.

When summing only positive numbers, placing smaller numbers first can often reduce the loss of small contributions. With datasets containing both negative and positive numbers, **no single sort order is always optimal**, because the positions of cancelling pairs also shift.

Error must be evaluated in context. A sum of `0.0` instead of `1.0` is a huge error if the true sum is 1, even if individual input terms had magnitude `1e16`.

## 6. Kahan Compensated Summation

**Kahan summation** adds a `correction` variable to estimate the low-order contribution dropped during addition. That compensation is folded into the next addition to reduce accumulated error in many cases.

Mechanism:

~~~text
sum = 0
correction = 0
for each x:
    adjusted = x - correction
    next = sum + adjusted
    correction = (next - sum) - adjusted
    sum = next
return sum
~~~

This is pseudocode, not a complete Java program. Every step still runs in `double`, so **Kahan does not guarantee exactness for every input**.

### Java 17 Example: Kahan Improves a Repeated Sum

Save as `KahanSummationDemo.java`:

~~~java
public class KahanSummationDemo {
    static double naive(int count, double value) {
        double sum = 0.0;
        for (int i = 0; i < count; i++) {
            sum += value;
        }
        return sum;
    }

    static double kahan(int count, double value) {
        double sum = 0.0;
        double correction = 0.0;
        for (int i = 0; i < count; i++) {
            double adjusted = value - correction;
            double next = sum + adjusted;
            correction = (next - sum) - adjusted;
            sum = next;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("naive = " + naive(10, 0.1));
        System.out.println("kahan = " + kahan(10, 0.1));
    }
}
~~~

~~~bash
javac KahanSummationDemo.java
java KahanSummationDemo
~~~

Output:

~~~text
naive = 0.9999999999999999
kahan = 1.0
~~~

This input set illustrates the benefit of compensated summation. However, getting `1.0` does not prove the algorithm recovered the exact decimal inputs; `0.1` was already approximated when converted to `double`.

## 7. Neumaier: Improvement When Large and Small Numbers Alternate

**Neumaier summation** is a compensated summation variant. It compares the relative magnitudes of the running sum and the new term to compute the compensation. On `[1e16, 1, -1e16]`, both naive addition and basic Kahan can yield `0.0`, whereas Neumaier can preserve `1.0`.

### Java 17 Example: Three Different Results

Save as `CompensatedSummationDemo.java`:

~~~java
public class CompensatedSummationDemo {
    static double naive(double[] values) {
        double sum = 0.0;
        for (double x : values) {
            sum += x;
        }
        return sum;
    }

    static double kahan(double[] values) {
        double sum = 0.0;
        double correction = 0.0;
        for (double x : values) {
            double adjusted = x - correction;
            double next = sum + adjusted;
            correction = (next - sum) - adjusted;
            sum = next;
        }
        return sum;
    }

    static double neumaier(double[] values) {
        double sum = 0.0;
        double correction = 0.0;
        for (double x : values) {
            double next = sum + x;
            if (Math.abs(sum) >= Math.abs(x)) {
                correction += (sum - next) + x;
            } else {
                correction += (x - next) + sum;
            }
            sum = next;
        }
        return sum + correction;
    }

    public static void main(String[] args) {
        double[] data = {1.0e16, 1.0, -1.0e16};

        System.out.println("naive = " + naive(data));
        System.out.println("kahan = " + kahan(data));
        System.out.println("neumaier = " + neumaier(data));
    }
}
~~~

~~~bash
javac CompensatedSummationDemo.java
java CompensatedSummationDemo
~~~

Output:

~~~text
naive = 0.0
kahan = 0.0
neumaier = 1.0
~~~

Neumaier can retain the small term in the compensation variable in cases where basic Kahan still loses it. Even so, neither guarantees the exact mathematical sum in every case, especially with `NaN`, `Infinity`, overflow, underflow, or inputs that already carry prior rounding error. Algorithms must be tested against realistic data characteristics.

## 8. Pairwise Summation and Chunking

**Pairwise summation** replaces a long left-to-right addition chain with a tree of additions: split the array into two halves, sum each half, then add the two results. In many non-negative summation problems, this reduces the number of sequential additions along any branch and can reduce accumulated error.

Pseudocode:

~~~text
pairwise(values):
    if empty: return 0
    if only one value: return value
    split into left and right halves
    return pairwise(left) + pairwise(right)
~~~

Every addition in the tree still rounds. **Pairwise is not better than every other order** for all mixed-sign datasets, because grouping can shift where cancellation happens. If a system needs bit-reproducible results, you must fix **the addition tree, block sizes, and element order**, rather than merely specifying "use pairwise".

## 9. Streams, reduce, and Parallel Sums

In Java, summing with Streams has several forms that do not necessarily use the same order:

- A `for` loop over an array has a deterministic sequence adding in loop order.
- `Arrays.stream(values).reduce(0.0, Double::sum)` reduces values by addition. Parallel reduction contracts assume the combiner is associative; `double` addition is not associative in machine arithmetic, so different reduction trees can yield different results.
- `DoubleStream.sum()` per the Java API uses a compensated summation algorithm, improving many cases without eliminating order effects or precision limits.
- `Collectors.summingDouble(...)` can likewise be affected by element order and magnitudes.

### Java 17 Example: Same Data, Different APIs

Save as `FloatingStreamDemo.java`:

~~~java
import java.util.Arrays;

public class FloatingStreamDemo {
    public static void main(String[] args) {
        double[] data = {1.0e16, 1.0, -1.0e16};

        double reduce = Arrays.stream(data)
                .reduce(0.0, Double::sum);
        double specialized = Arrays.stream(data).sum();
        double parallel = Arrays.stream(data).parallel()
                .reduce(0.0, Double::sum);

        System.out.println("reduce = " + reduce);
        System.out.println("sum finite = " + Double.isFinite(specialized));
        System.out.println("parallel finite = " + Double.isFinite(parallel));
    }
}
~~~

~~~bash
javac FloatingStreamDemo.java
java FloatingStreamDemo
~~~

Output:

~~~text
reduce = 0.0
sum finite = true
parallel finite = true
~~~

The two `isFinite` checks avoid assuming a specific sum for algorithms and partitioning schemes that may vary. The example's inputs are finite and do not overflow. Do not conclude that a specific `parallel().reduce(...)` sum will always match a loop sum across all systems or input sizes.

When parallelizing and needing deterministic results, fix the partitioning and merging scheme or use an accumulator meeting your precision requirements. Determinism must be verified with real tests.

## 10. BigDecimal When Exact Decimal Addition Is Required

If the problem requires exact arithmetic on **decimal input values**, such as money, `BigDecimal` is usually the right solution. Construct `BigDecimal` from decimal strings and use `add(...)` without a `MathContext` to sum stored decimal values exactly.

### Java 17 Example: Order-Independent Sum with Exact Decimal Addition

Save as `BigDecimalOrderDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalOrderDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("10000000000000000");
        BigDecimal b = BigDecimal.ONE;
        BigDecimal c = new BigDecimal("-10000000000000000");

        BigDecimal first = a.add(b).add(c);
        BigDecimal second = a.add(c).add(b);

        System.out.println("first = " + first.toPlainString());
        System.out.println("second = " + second.toPlainString());
        System.out.println("same value = "
                + (first.compareTo(second) == 0));
    }
}
~~~

~~~bash
javac BigDecimalOrderDemo.java
java BigDecimalOrderDemo
~~~

Output:

~~~text
first = 1
second = 1
same value = true
~~~

Understand the scope of this conclusion:

- `new BigDecimal("0.1")` keeps the exact decimal value 0.1. `new BigDecimal(0.1)` keeps the exact **binary approximation of `double`**, not the ideal decimal 0.1.
- `BigDecimal.valueOf(double)` uses the canonical string representation of `double` but cannot recover information already lost in earlier `double` arithmetic.
- If you use `add(other, MathContext)` with bounded precision, **each addition can round**, making `BigDecimal` sums depend on grouping as well.
- `BigDecimal` has higher overhead than `double` in many workloads. Do not automatically convert all floating-point statistics to `BigDecimal` when tolerances and performance permit `double`.

For money, define when rounding happens according to business rules. **Rounding each line item then summing can differ from summing exactly first and rounding the total.**

## 11. Measuring Error and Writing Proper Tests

Absolute error compared to a higher-precision reference:

\[
E_{\mathrm{abs}} = |S_{\mathrm{computed}}-S_{\mathrm{reference}}|.
\]

Relative error equals absolute error divided by \(|S_{\mathrm{reference}}|\), but is unsuitable when the reference sum is zero or very close to zero. Datasets with cancellation typically require checking both absolute error and domain-specific criteria.

A common approximate tolerance formula:

\[
|a-b| \le \epsilon_{\mathrm{abs}}+
\epsilon_{\mathrm{rel}}\max(|a|,|b|).
\]

Do not pick `1e-9` as a universal default threshold: tolerance must depend on data magnitude, operation count, and goals. Check `NaN`, infinity, overflow, underflow, and signed zero per the problem contract if inputs may contain them.

A useful test plan runs the same dataset in original order, reversed order, sorted by magnitude, and chunked; compare against a higher-precision reference. Include `[1e16, 1, -1e16]`, many repeated small numbers, and nearly cancelling positive/negative numbers.

## 12. When to Choose Which Approach?

| Requirement | Approach | Limitation |
| --- | --- | --- |
| Simple double sum, tolerance acceptable | Loop adding in fixed order | Can accumulate error |
| Many double additions | Kahan, pairwise, or other compensated method | Does not guarantee exactness |
| Alternating large/small positive/negative numbers | Neumaier or suitable accumulator | Test cancellation and edge cases |
| Parallel computation | Fix split and merge tree if reproducibility needed | Changing partitions can change sum |
| Money/decimals must be exact | BigDecimal from decimal source, exact sum before rounding | Higher CPU and memory cost |
| Exact sum needed regardless of order | Exact accumulator algorithm matching contract | Needs specialized solution and verification |

No single summation method is best for every dataset. Results must fit the acceptable error, latency, reproducibility, and data characteristics.

## 13. Common Mistakes

1. **Assuming `double` addition is strictly associative:** each intermediate addition can round.
2. **Thinking sums always match when only element order changes:** small terms can be lost at different positions.
3. **Using `parallel().reduce` and expecting bit-exact match with a sequential loop:** reduction trees can differ.
4. **Thinking `DoubleStream.sum()` produces exact real-number results:** compensated summation is still bound by binary floating point.
5. **Sorting all small numbers first and assuming everything is solved:** mixed signs and cancellation complicate outcomes.
6. **Assuming Kahan is always enough:** inputs like `[1e16, 1, -1e16]` may need stronger compensation.
7. **Thinking `println(0.1)` proves `double` stores 0.1 exactly:** the printed string is a suitable decimal representation, not the stored bits.
8. **Converting an already-inaccurate `double` to `BigDecimal` expecting data recovery:** lost information does not return.
9. **Letting `MathContext` round between `BigDecimal` additions without considering order:** addition with rounding can also be non-associative.
10. **Ignoring `NaN`, `Infinity`, overflow, or extreme magnitude disparities:** these can break approximation assumptions.
11. **Comparing approximate numbers with `==` in every test:** only valid if bit-exact `double` equality is genuinely required.
12. **Using relative error when the true sum is `0`:** division in the relative error formula is undefined.

## 14. Exercises and Answers

**Question 1.** Why does `(1e16 + (-1e16)) + 1` differ from `1e16 + ((-1e16) + 1)` in `double` arithmetic?

**Answer:** The first expression cancels the two large numbers first, returning `1.0`. The second loses the `1` contribution when adding it to the large negative number, returning `0.0`.

**Question 2.** Why does adding `0.1` ten times not necessarily equal `0.1 * 10`?

**Answer:** `0.1` is an approximate binary value; ten additions round differently than a single multiplication.

**Question 3.** Does Kahan always recover a lost small term in `[1e16, 1, -1e16]`?

**Answer:** No. Basic Kahan can return `0.0`; for example, Neumaier returns `1.0`.

**Question 4.** When should `BigDecimal` be used?

**Answer:** When exact sums of decimal input values (such as money) are required, constructing objects from exact decimal data and avoiding per-addition rounding when the goal is an exact total.

**Question 5.** Should relative error be used when the reference sum is `0`?

**Answer:** No, because dividing by 0 is undefined; use absolute error or another domain-appropriate criterion.

## 15. Takeaways

- **Addition order can change `float`/`double` results** because intermediate operations must round.
- Small terms are easily swamped when added to a large sum; large cancelling terms can expose prior rounding errors.
- Kahan, Neumaier, and pairwise improve many cases, but do not turn `double` into infinite-precision real arithmetic.
- Parallel streams can use different addition trees; fix the algorithm and merge order when reproducibility is required.
- When exact decimal sums are required, use `BigDecimal` from decimal sources and manage when rounding occurs.

References: Java SE 17 API `Double`, `Math.ulp`, `DoubleStream.sum`, `Collectors.summingDouble`, `BigDecimal`, and IEEE 754.