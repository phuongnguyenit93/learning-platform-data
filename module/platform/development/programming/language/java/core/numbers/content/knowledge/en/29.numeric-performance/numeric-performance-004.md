# BigDecimal Cost by Precision and Scale

## 1. Why Does `BigDecimal` Performance Depend on Data?

`BigDecimal` in Java is used to compute decimal values with arbitrary precision. It supports addition, subtraction, multiplication, division, and rounding under controllable rules, but usually requires more memory and work than primitive `long` or `double`. Two `add` calls that look identical in source code can differ dramatically in cost: adding two numbers with a few digits and adding `1E+1000000` with `1` both call `add`, yet the exact result of the second case requires roughly one million integer digits.

To analyze performance, you need to understand **precision**, **scale**, the size of the unscaled integer before placing the decimal point, scale differences, intermediate results, rounding modes, and string formatting. This lesson uses Java 17+ examples, highlights correctness/incorrectness boundaries when optimizing, and shows how to measure in practice.

## 2. Precision, Scale, and Unscaled Value

`BigDecimal` represents a value according to the formula:

\[
\text{value} = \text{unscaledValue}\times10^{-\text{scale}}.
\]

- **Unscaled value** is the integer carrying the digits of the value. For example, `123.4500` has unscaled value `1234500`.
- **Scale** is an `int` integer: `123.4500` has scale 4; `1E+6` has scale -6; `1000` has scale 0. Scale can be negative.
- **Precision** is the number of decimal digits in the absolute unscaled value, excluding leading zeros. For zero, precision is 1. `123.4500` has precision 7, and `1E+6` has precision 1.
- **`MathContext` precision** is the limit on significant digits after an operation when `MathContext` is specified; it is **not** the number of digits after the decimal point.

Precision = 1 does not mean a small value: `1E+1000000` has precision 1 yet a gigantic magnitude. Large scale does not mean large precision: `1E-1000000` has precision 1 and scale 1000000.

### Example 1: reading `BigDecimal` metadata

Save as `BigDecimalMetaDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalMetaDemo {
    private static void inspect(String source) {
        BigDecimal x = new BigDecimal(source);
        System.out.println(source + ": p=" + x.precision()
                + ", s=" + x.scale());
    }

    public static void main(String[] args) {
        inspect("123.4500");
        inspect("1000.00");
        inspect("1E+6");
        inspect("0.000001");
        inspect("0.00");
    }
}
~~~

Compile/run with JDK 17:

~~~bash
javac BigDecimalMetaDemo.java
java BigDecimalMetaDemo
~~~

Output:

~~~text
123.4500: p=7, s=4
1000.00: p=6, s=2
1E+6: p=1, s=-6
0.000001: p=1, s=6
0.00: p=1, s=2
~~~

Numbers with **equal arithmetic value** can still differ in representation. `2.0` and `2.00` have `compareTo(...) == 0` but `equals(...) == false` because their scales differ; normalizing scale can affect map keys and displayed data.

## 3. Internal Representation and the Cost of Large Integers

`BigDecimal` stores an unscaled value and a scale. In JDK 17, small unscaled values can go through a compact `long`-like representation; larger values may require a large-integer structure such as `BigInteger`. Internal details and optimization thresholds can change across JDK versions, so this is an explanation of common mechanics, **not a runtime API contract**.

In principle, arithmetic on integers with hundreds or thousands of digits takes more work than operations on small integers. Multiplying/dividing large numbers may also use different algorithms depending on size. `BigDecimal` is **immutable**: new logical results, intermediate representations, and large integers can cause memory allocations/GC. Implementations may reuse certain objects or optimize fast paths in some cases, but a program must not assume every addition is "zero-allocation".

Therefore, real cost must be measured on **specific digit lengths, scales, and operations**, not guessed from the number of `BigDecimal` objects or a generic formula.

## 4. Addition and Subtraction: Scale Alignment

For exact addition, operands must be aligned to a compatible decimal unit:

\[
1.20 + 0.003 = 1.203.
\]

In exact addition/subtraction, the result scale is usually the larger scale of the two operands. A large scale difference can force the JDK to compute large powers of 10 and a long resulting integer.

Example:

- `1E+6`: precision 1, scale -6.
- `1`: precision 1, scale 0.
- **Exact** sum: `1000001`, precision 7, scale 0.

If `1E+6` is replaced with `1E+1000000`, the exact result of adding `1` requires roughly one million integer digits. Even though both operands have small precision, **the scale difference dictates how much data must be represented**.

### Example 2: comparing exact addition and `MathContext` addition

Save as `BigDecimalAddDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalAddDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1E+6");
        BigDecimal b = BigDecimal.ONE;

        BigDecimal exact = a.add(b);
        BigDecimal rounded = a.add(b,
                new MathContext(4, RoundingMode.HALF_UP));

        System.out.println("a scale = " + a.scale());
        System.out.println("exact = " + exact.toPlainString());
        System.out.println("exact p = " + exact.precision());
        System.out.println("rounded = " + rounded.toPlainString());
        System.out.println("rounded p = " + rounded.precision());
    }
}
~~~

~~~bash
javac BigDecimalAddDemo.java
java BigDecimalAddDemo
~~~

Output:

~~~text
a scale = -6
exact = 1000001
exact p = 7
rounded = 1000000
rounded p = 4
~~~

`MathContext(4, HALF_UP)` limits the result to four significant digits and discards the contribution of `1`. This is a **semantic change**, not merely a speedup. Some algorithms can save work thanks to finite precision, but one cannot claim every operation with `MathContext` is faster.

## 5. Multiplication: Digit Length and Scale Can Grow

With exact `a.multiply(b)`, the result scale normally equals the sum of the two operands' scales, provided it remains within the valid range. The length of the product's unscaled value generally grows with the digit counts of both operands. The cost of multiplying numbers of a few digits differs substantially from multiplying two numbers with thousands of digits.

### Example 3: product scale preserves trailing zeros

Save as `BigDecimalMultiplyDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalMultiplyDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("12.3400");
        BigDecimal b = new BigDecimal("0.010");
        BigDecimal product = a.multiply(b);

        System.out.println("a scale = " + a.scale());
        System.out.println("b scale = " + b.scale());
        System.out.println("product = " + product.toPlainString());
        System.out.println("product scale = " + product.scale());
        System.out.println("product p = " + product.precision());
    }
}
~~~

~~~bash
javac BigDecimalMultiplyDemo.java
java BigDecimalMultiplyDemo
~~~

Output:

~~~text
a scale = 4
b scale = 3
product = 0.1234000
product scale = 7
product p = 7
~~~

The trailing zeros in `0.1234000` do not change the value, yet they are preserved in the scale-7 representation of exact multiplication. Repeating multiplication many times can produce ever-larger intermediate precisions and scales. Choose rounding only when the problem's precision policy allows it.

## 6. Division: Precision, Scale, and Rounding Mode Directly Affect Cost

`divide(divisor)` does not pick a rounding level automatically. If the decimal expansion is non-terminating, such as `1/3`, the method throws `ArithmeticException`. Overloads accepting parameters provide control:

- `divide(divisor, scale, roundingMode)`: number of digits **after the decimal point** and rounding mode.
- `divide(divisor, MathContext)`: number of **significant** digits and rounding mode.
- `divide(divisor)`: accepts only exact terminating decimal results.

Requesting more quotient digits typically increases work, memory, and rounding cost. However, actual runtime also depends on the size and structure of the divisor; do not state a fixed speed factor without benchmarking.

### Example 4: comparing two division contracts

Save as `BigDecimalDivideDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDivideDemo {
    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");

        try {
            one.divide(three);
            System.out.println("unexpected exact result");
        } catch (ArithmeticException ex) {
            System.out.println("exact division rejected");
        }

        System.out.println("scale 2 = " + one.divide(
                three, 2, RoundingMode.HALF_UP));
        System.out.println("precision 6 = " + one.divide(
                three, new MathContext(6, RoundingMode.HALF_UP)));
    }
}
~~~

~~~bash
javac BigDecimalDivideDemo.java
java BigDecimalDivideDemo
~~~

Output:

~~~text
exact division rejected
scale 2 = 0.33
precision 6 = 0.333333
~~~

Blindly capping precision can make results wrong, while setting an enormous precision "to be safe" can waste resources. You must define the rounding policy per business requirements and measure on real data.

## 7. `setScale` Is Not Always Cheap

`setScale(newScale)` can:

- **Increase scale:** multiplies the unscaled value by a power of 10 to preserve value, increasing the number of unscaled digits.
- **Decrease scale:** divides the unscaled value, potentially requiring rounding if dropped digits are nonzero.
- **Keep scale:** usually less work, though the API does not promise the result is always zero-allocation.
- **Use negative scale:** for example, `1E+3` has scale -3 and value 1000.

### Example 5: increasing scale increases precision

Save as `ScaleExpansionDemo.java`:

~~~java
import java.math.BigDecimal;

public class ScaleExpansionDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("12.3");
        BigDecimal b = a.setScale(5);

        System.out.println("original = " + a);
        System.out.println("expanded = " + b);
        System.out.println("before p = " + a.precision());
        System.out.println("after p = " + b.precision());
        System.out.println("after s = " + b.scale());
    }
}
~~~

~~~bash
javac ScaleExpansionDemo.java
java ScaleExpansionDemo
~~~

Output:

~~~text
original = 12.3
expanded = 12.30000
before p = 3
after p = 7
after s = 5
~~~

The numeric value remains 12.3, but the unscaled representation is longer. Increasing scale by hundreds of thousands of orders of magnitude can trigger huge allocations; do not allow arbitrary input to dictate unbounded scale in resource-constrained applications.

## 8. `stripTrailingZeros` and Comparisons

`stripTrailingZeros()` removes trailing zeros in the unscaled value and adjusts the scale. It can shorten the representation, yet it can also turn the scale negative. For example, `1000.00` becomes `1E+3`, scale -3.

`BigDecimal.equals` and `compareTo` differ:

- `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` is `false` because the scales differ.
- `compareTo` on these two numbers returns `0` because their arithmetic values are equal.

Do not treat `stripTrailingZeros` as a free optimization in every loop; normalization also processes the unscaled value and alters the representation contract. The `equals`/`compareTo` difference also affects `HashMap` keys and `TreeSet` sets. With large data, comparison cost can depend on length and scale; do not assume every `compareTo` is O(1).

### Example 6: normalization can produce negative scale

Save as `NormalizeDemo.java`:

~~~java
import java.math.BigDecimal;

public class NormalizeDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1000.00");
        BigDecimal normalized = original.stripTrailingZeros();
        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");

        System.out.println("before s = " + original.scale());
        System.out.println("after s = " + normalized.scale());
        System.out.println("normalized = " + normalized);
        System.out.println("compare = " + x.compareTo(y));
        System.out.println("equals = " + x.equals(y));
    }
}
~~~

~~~bash
javac NormalizeDemo.java
java NormalizeDemo
~~~

Output:

~~~text
before s = 2
after s = -3
normalized = 1E+3
compare = 0
equals = false
~~~

Strip trailing zeros only when the problem contract permits changing scale. For monetary data requiring two decimal places, preserve the appropriate scale convention instead of normalizing unconditionally.

## 9. Strings Can Be Very Long Even When Precision Is 1

`toString()` can represent a value using scientific notation, whereas `toPlainString()` outputs the decimal number without an exponent. Consequently, `new BigDecimal("1E+1000000")` has precision 1, yet `toPlainString()` creates a string consisting of the digit 1 followed by roughly one million zeros.

### Example 7: string creation cost

Save as `StringRepresentationDemo.java`:

~~~java
import java.math.BigDecimal;

public class StringRepresentationDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("1E+6");

        System.out.println("precision = " + x.precision());
        System.out.println("scale = " + x.scale());
        System.out.println("toString = " + x.toString());
        System.out.println("plain = " + x.toPlainString());
        System.out.println("plain length = " + x.toPlainString().length());
    }
}
~~~

~~~bash
javac StringRepresentationDemo.java
java StringRepresentationDemo
~~~

Output:

~~~text
precision = 1
scale = -6
toString = 1E+6
plain = 1000000
plain length = 7
~~~

Creating long strings consumes memory proportional to the output string length even when the `BigDecimal` value itself is compact. Do not call `toPlainString` repeatedly in loops or log numbers with extreme scales without bounding length and display needs.

## 10. `MathContext` and Precision Trade-Offs

`MathContext` holds precision and a rounding mode. It **does not directly specify scale**. For example, `new MathContext(4, HALF_UP)` keeps four significant digits; `setScale(4, HALF_UP)` keeps four digits after the decimal point.

Limiting precision can let some operations process shorter results, but it can also introduce rounding steps. Cost depends on the algorithm and JDK; **a small `MathContext` is not guaranteed to be faster**. More importantly, low precision can drop the contribution of small numbers or alter the result.

Exact addition followed by rounding can also differ from rounding at **every addition step**, so this policy must be designed from precision requirements. For money, taxes, and accounting ledgers, never change when rounding happens merely because it looks faster.

## 11. Allocation, Memory, and Data Design

Because `BigDecimal` is immutable, an accumulation loop like the following illustrative snippet creates a logical result after each addition:

~~~java
BigDecimal total = BigDecimal.ZERO;
for (BigDecimal item : values) {
    total = total.add(item);
}
~~~

This is only an illustrative snippet; `values` must be declared when used in a standalone program. At runtime, the implementation may optimize or reuse certain objects, yet operations on large unscaled values can still create substantial intermediate data.

Reasonable improvement directions:

- Use `BigDecimal.ZERO`, `ONE`, `TEN`, and `BigDecimal.valueOf(long)` when appropriate; avoid parsing strings on every step if the data is already exact decimal numbers.
- For decimal literals, use `new BigDecimal("0.1")` when exact 0.1 is needed; `new BigDecimal(0.1)` retains the binary approximation of `double`.
- Limit calls to `setScale`, `stripTrailingZeros`, and string formatting inside hot loops if only the final representation is needed.
- For domains with fixed scale and a permissible numeric range, consider storing in minor units using `long`; you must strictly control overflow and rounding. Do not apply this trick to arbitrary scale/precision problems.
- Profile memory and evaluate allocation/GC with a profiler or benchmark when there is evidence it is a bottleneck.

## 12. Proper Benchmarking to Avoid Wrong Conclusions

Using a single `System.nanoTime()` around one `BigDecimal` call is usually unreliable because of JVM warmup/JIT, GC, CPU scheduling, and optimizations eliminating computations whose results are unused.

**JMH (Java Microbenchmark Harness)** is the appropriate tool for microbenchmarks and must be added as a dependency in a separate test project; it is not bundled in the JDK. Measurement procedures should:

1. Prepare operands outside the measured region if the goal is solely measuring `add` or `multiply`.
2. Warm up sufficiently, run multiple iterations, and report distributions, not just a single number.
3. Consume results using `Blackhole` or an equivalent JMH mechanism to avoid dead-code elimination.
4. Measure both time/op and allocation/op; observe GC if relevant.
5. Test data with short/long unscaled values, equal/far-apart scales, precision 16/100/1000, and short/long formatted outputs.
6. Verify output values and scales before comparing speeds; an optimization that breaks arithmetic is not an equivalent optimization.

A useful benchmark matrix:

| Scenario | Example | What to measure |
| --- | --- | --- |
| Same-scale addition | `1234.56 + 78.90` | Baseline cost |
| Widely differing scale addition | `1E+1000 + 1` | Alignment and allocation |
| Long-number multiplication | Two thousand-digit numbers | Product length and CPU |
| High-precision division | `1/7` precision 16, 100, 1000 | Quotient/rounding cost |
| Formatting exponents | `1E+100000` | `toString` vs `toPlainString` |

This table is a **testing suggestion**, not measured results. Do not claim "BigDecimal is N times slower than double" without comparing the exact same task and dataset.

## 13. Extreme Inputs and Resource Safety

Scale is of type `int`, yet operations with extreme scales can still demand allocating millions of digits. For example:

- Adding `1E+1000000 + 1` creates a huge exact decimal result.
- `setScale` increasing by many orders of magnitude can create a long unscaled value.
- Repeated `multiply` can cause precision/scale to grow.
- `divide` with very high precision must compute many quotient digits.
- `toPlainString` can produce a much larger string than scientific notation.
- Operations can raise `ArithmeticException` for invalid scale, non-terminating division without rounding, or `UNNECESSARY` mode; excessive memory load can even cause `OutOfMemoryError`.

Validate input string length, precision, scale, element counts, and result sizes before executing calculations on external input. Limits must derive from application requirements and available resources.

## 14. Common Mistakes

1. **Confusing precision with scale:** `1E+6` has precision 1 and scale -6.
2. **Thinking low precision means every operation is cheap:** scale differences can still produce long results.
3. **Thinking `setScale` only changes metadata:** it can multiply/divide the unscaled value by powers of 10.
4. **Using low `MathContext` precision just for speedup:** can cause data loss.
5. **Using `divide` without rounding for 1/3:** will throw `ArithmeticException`.
6. **Assuming `stripTrailingZeros` preserves scale:** can produce a negative scale.
7. **Confusing `equals` and `compareTo`:** `equals` checks scale, `compareTo` checks value.
8. **Calling `toPlainString` on huge exponents:** can generate huge strings.
9. **Switching to `double` for speed:** can lose decimal exactness.
10. **Using `long` minor units without checking overflow:** corrupts the value range.
11. **Benchmarking without warmup or including parsing:** fails to isolate operation cost.
12. **Ignoring user-supplied precision/scale:** can cause memory/CPU exhaustion.

## 15. Self-Check

**Question 1.** What are the precision and scale of `new BigDecimal("123.4500")`?

**Answer:** Precision 7, scale 4 because the unscaled value is 1234500.

**Question 2.** Why is `1E+1000000 + 1` resource-intensive even though the first operand has precision 1?

**Answer:** Exact addition requires aligning scales and representing a result with roughly one million integer digits.

**Question 3.** What value does `new BigDecimal("12.3").setScale(5)` produce?

**Answer:** `12.30000`; precision increases from 3 to 7 and scale becomes 5; the arithmetic value does not change.

**Question 4.** What scale can `new BigDecimal("1000.00").stripTrailingZeros()` have?

**Answer:** -3, represented as `1E+3`.

**Question 5.** Why is low `MathContext` precision not a free optimization?

**Answer:** It rounds, potentially dropping required digits and changing business results.

**Question 6.** What should you pay attention to when measuring the isolated performance of `add`?

**Answer:** Prepare operands outside the benchmarked section, warm up, consume results, measure multiple samples across varying precisions/scales, and verify correctness.

## 16. Conclusion

- Precision measures the significant digits of the unscaled value; scale determines decimal point placement and can be negative.
- `BigDecimal` cost depends on **precision, scale, scale difference, operation, intermediate allocations, and output formatting**.
- Widely skewed scale addition and `toPlainString` on large exponents can cause very high load even when initial precision is small.
- High-precision division/multiplication costs more work, yet early rounding is only valid when business rules permit it.
- Measure on target data with tools such as JMH and verify correctness before optimizing.

References: Java SE 17 API `BigDecimal`, `BigInteger`, `MathContext`, `RoundingMode`.
