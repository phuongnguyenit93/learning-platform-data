# Binary Representation Error When Computing with `float` or `double` — Java 17+

## 1. The Phenomenon: Why Isn't 0.1 + 0.2 Exactly Equal to 0.3?

In Java, `float` and `double` store floating-point numbers in **IEEE 754 binary floating-point** format. Many finite decimal fractions — such as `0.1`, `0.2`, and `0.3` — **cannot be represented exactly with a finite number of binary bits**.

~~~java
double a = 0.1;
double b = 0.2;
double sum = a + b;

System.out.println(sum);         // 0.30000000000000004
System.out.println(sum == 0.3);  // false
~~~

The result **is not a Java bug**. The input values were already rounded to representable binary numbers; addition also follows floating-point rounding rules. Therefore the represented result of `0.1 + 0.2` differs slightly from the representation of the literal `0.3`.

Three things to grasp:

1. **The mathematical number** `0.1` differs from **the closest binary value** stored in `double`.
2. `double` has **more precision than `float`**, yet still does not represent every decimal fraction exactly.
3. Error can **propagate, accumulate, or be amplified** across operations. If business logic requires exact decimal calculations, choose an appropriate data model rather than merely increasing displayed decimal digits.

## 2. Why Does Error Occur? Finite Binary Representation

A fraction has a finite representation in base 2 when its reduced denominator has only **2** as a prime factor. For example:

| Mathematical Fraction | In Binary | Has Finite Base-2 Representation? |
|---|---|---|
| `1/2 = 0.5` | `0.1₂` | Yes |
| `1/4 = 0.25` | `0.01₂` | Yes |
| `3/8 = 0.375` | `0.011₂` | Yes |
| `1/10 = 0.1` | Infinite repeating bit sequence | No |
| `1/5 = 0.2` | Infinite repeating bit sequence | No |
| `3/10 = 0.3` | Infinite repeating bit sequence | No |

For instance, `0.1` in base 2 requires infinitely repeating bits. `float` and `double` have a finite number of bits, so they store **the closest approximation** according to the applicable rounding rule.

~~~mermaid
flowchart TD
    A["Decimal literal: 0.1"] --> B["Convert to closest representable binary value"]
    B --> C["Store in finite-bit float or double"]
    C --> D["Perform floating-point arithmetic"]
    D --> E["Round result according to format"]
    E --> F["Print enough decimal digits for round-trip"]
~~~

**Note:** printing `0.1` does not mean the machine stores **the exact** decimal number 0.1. Java uses a string conversion that can be parsed back into the exact same `double`/`float` value, so the printed string can be shorter than the exact decimal expansion of the internal binary value.

## 3. `float` and `double`: Bit Counts and Precision

| Property | `float` | `double` |
|---|---|---|
| Format | IEEE 754 binary32 | IEEE 754 binary64 |
| Total bits | 32 | 64 |
| Exponent bits | 8 | 11 |
| Significand precision | 24 bits, including implicit bit for normalized numbers | 53 bits, including implicit bit for normalized numbers |
| Approximate exact decimal digits | 6–9 significant digits | 15–17 significant digits |
| Common literals | `0.1f` | `0.1`, `0.1d` |
| Bit-size constant | `Float.SIZE` | `Double.SIZE` |
| Best suited for | Data tolerating larger error / saving storage | General floating-point math needing higher precision |

`double` does **not** mean "absolute precision," and `float` is not always wrong: both have valid domains when tolerances are defined.

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println((double) f); // 0.10000000149011612
System.out.println(d);          // 0.1
~~~

When converting `float` to `double`, you **widen the representational capacity without restoring** the decimal value 0.1 that was already rounded into a `float` value. The string of `double d` prints as 0.1, yet the binary value stored in `d` is also only an approximation of 0.1.

## 4. Literals, Operations, and Expression Types Affect Error

~~~java
var a = 0.1;     // Inferred as double
var b = 0.1f;    // Inferred as float
var c = 0.1d;    // Explicit double

System.out.println(a + 0.2); // 0.30000000000000004
~~~

In mixed arithmetic expressions, Java applies *binary numeric promotion*. For example:

~~~java
float f = 0.1f;
double d = 0.2;
double mixed = f + d; // float is widened to double, then added
~~~

`mixed` has type `double`, yet the operand `f` **still carries the error it had when stored as a float**. Do not assume that because "the result type is double," both inputs suddenly had 53 bits of precision from the start.

For large integers, conversion to floating-point can also lose detail:

~~~java
double exactLimit = 9_007_199_254_740_992d; // 2^53
System.out.println(exactLimit + 1.0 == exactLimit); // true
~~~

At magnitude `2^53`, `double` can no longer distinguish every pair of consecutive integers; adding 1 rounds right back to the same value.

## 5. ULP and Magnitude-Dependent Resolution

**ULP** (*unit in the last place*) denotes the spacing between adjacent floating-point values in a given region. As a number's magnitude grows, the representational spacing generally grows accordingly.

~~~java
System.out.println(Math.ulp(1.0));          // 2.220446049250313E-16
System.out.println(Math.ulp(16_777_216f));  // 2.0
~~~

`Math.ulp(1.0)` describes the `double` step at 1.0. For `float`, around `2^24 = 16_777_216`, the step is 2, so adding 1 may leave the value unchanged:

~~~java
float x = 16_777_216f;
System.out.println(x + 1f == x); // true
~~~

**No single fixed epsilon is guaranteed to work well across all numeric ranges.** For very large values, valid absolute differences can be large; for values very close to 0, comparing strictly by relative error may be inappropriate.

Also, `Float.MIN_VALUE`/`Double.MIN_VALUE` is the **smallest positive non-zero** value, not the most negative number. To bound finite magnitude, look at `MAX_VALUE`; for negative bounds, you can use `-MAX_VALUE`.

## 6. `==`: Compares Exact Binary Values, Not Proximity

~~~java
double calculated = 0.1 + 0.2;
double expected = 0.3;

System.out.println(calculated == expected); // false
System.out.println(calculated - expected);  // 5.551115123125783E-17
~~~

The `==` operator compares **floating-point values per language rules**, with no "implicit tolerance" for computational error.

However, you must **not** claim that every `==` comparison on floating-point numbers is wrong:

- Comparing against a **special constant with exact meaning** (such as `value == 0.0` when you genuinely want exact zero) can be a valid requirement, though you should check how the data is produced.
- Comparing equality of **represented values** is sometimes intentional in an algorithm.
- If you need **"nearly equal" for measurements or business logic**, you must define an appropriate error threshold instead of `==`.

**Do not pick an arbitrary threshold like `1e-9` and assume it works for every numeric domain.** A threshold must reflect units, magnitude, input error, and system requirements.

## 7. Approximate Comparison: Absolute and Relative Tolerance

An illustrative helper for problems needing **"nearly equal"** comparison:

~~~java
static boolean nearlyEqual(
        double a, double b, double absTol, double relTol) {
    if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
            || absTol < 0 || relTol < 0) {
        throw new IllegalArgumentException("invalid tolerance");
    }
    if (a == b) {
        return true; // Covers +0.0/-0.0 and two infinities of the same sign
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false; // NaN or mismatched finite/infinite values
    }
    double diff = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return diff <= absTol || diff <= relTol * scale;
}
~~~

Example:

~~~java
System.out.println(nearlyEqual(0.1 + 0.2, 0.3, 1e-12, 1e-12)); // true
System.out.println(nearlyEqual(1.0, 1.1, 1e-12, 1e-12));       // false
~~~

**Understand the sample method's limits:** the subtraction `a-b` and multiplication `relTol*scale` are also `double` arithmetic, which can overflow/underflow at extremes; this method is suitable for illustration, not as a general-purpose numerical library. For Infinity values, returning `true` for identical Infinities on the `a == b` line is an **intentional policy choice**, which can be changed to false if business rules only permit comparing finite data.

For strict precision comparisons (science, simulation, statistics), explicitly determine an *error budget* and pick a suitable comparison algorithm — sometimes using ULP, relative error, absolute error, or a combination.

## 8. Error Accumulated Across Loops

A single addition has a small error; many additions can accumulate error:

~~~java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}
System.out.println(total); // 0.9999999999999999
System.out.println(0.1 * 10); // 1.0
~~~

The two operations differ in their rounding paths:

- **Adding 10 times:** each addition may round the intermediate value.
- **Multiplying once:** uses a single floating-point multiplication, so it has a different rounding sequence.

Do not conclude that multiplication is always more accurate than addition for every dataset; this is an example of **algorithm and calculation order** affecting error.

For large sums or many numbers of varying magnitudes, consider **compensated summation** algorithms (such as Kahan summation) or appropriate numerical libraries/functions, and test on representative data.

## 9. Floating-Point Addition Is Not Fully Associative

In mathematical arithmetic: `(a+b)+c = a+(b+c)`. With finite `double`, step-by-step rounding rules can cause the two groupings to return different results:

~~~java
double left = (1.0e16 + -1.0e16) + 1.0;
double right = 1.0e16 + (-1.0e16 + 1.0);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

Reason:

1. The `left` side cancels the two large numbers to 0 first, then adds 1.
2. The `right` side adds 1 to `-1e16`; the value 1 is too small compared to the spacing between `double` numbers around `1e16`, so it is rounded away, and then adding `1e16` yields 0.

**Do not arbitrarily change addition order** when refactoring a floating-point algorithm under the assumption that addition is completely associative. Order, parentheses, and summation algorithms can all affect the result.

## 10. Loss of Significant Digits (*Catastrophic Cancellation*)

Another type of error appears when **subtracting two very large numbers that are close together**:

~~~java
double a = 1.0e16 + 1.0;
double b = 1.0e16;

System.out.println(a - b); // 0.0
~~~

Mathematically, if `a` were truly `10^16 + 1` and `b` were `10^16`, the difference would be 1. But **when `a` was computed and stored in a double**, the added 1 was already rounded away, so `a` and `b` have the same representation and subtract to 0.

This situation often matters when computing differences of very large, nearly equal quantities. **You cannot recover lost digits merely by casting `double` to another type afterward.** Consider changing the formula, normalizing values, using higher precision from **the input**, or choosing another numeric model.

## 11. Check Special Floating-Point Results Before Comparing

`double` also has `NaN`, `Infinity`, `-Infinity`, and two signed zero forms. They can appear from dividing by 0 or operations exceeding the finite range:

~~~java
System.out.println(Double.isNaN(0.0 / 0.0));    // true
System.out.println(Double.isFinite(1.0 / 0.0)); // false
System.out.println(0.0 == -0.0);                // true
~~~

`Double.isFinite` **does not check precision**: `0.1 + 0.2` is still finite, yet approximate. When validating inputs, separate invalid data from acceptable error. The previous lesson covered NaN rules, wrapper comparison, zero signs, and underflow in detail.

## 12. Display Formatting Does Not Fix the Computed Value

~~~java
double sum = 0.1 + 0.2;

System.out.println(sum); // 0.30000000000000004
System.out.printf(java.util.Locale.ROOT, "%.2f%n", sum); // 0.30
~~~

`printf("%.2f")` or `String.format` only **rounds the text representation** according to the chosen format. The `sum` variable still holds the original `double` value.

Mistakes to avoid:

- Displaying `0.30` does **not** mean the stored number equals mathematical 0.30 exactly.
- Calling `Math.round(...)` does not replace a decimal-based monetary calculation model.
- Casting `float` to `double` **after** error has occurred does not recover lost data.

Distinguish between **the stored number**, **the calculation rules**, and **the output formatting**.

## 13. From Binary Floating-Point Error to an Exact Decimal Model

When business logic needs `0.1 + 0.2` to be **decimally exact 0.3**, preserve exact decimal sources from the beginning:

~~~java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");
System.out.println(a.add(b)); // 0.3.
~~~

How the object is constructed determines the input value:

| Construction | Meaning |
| --- | --- |
| `new BigDecimal("0.1")` | Stores the exact decimal number 0.1 |
| `BigDecimal.valueOf(0.1)` | Based on the decimal form of `Double.toString(0.1)` |
| `new BigDecimal(0.1)` | Stores the **exact approximate binary value** currently held in `double` |

~~~java
System.out.println(
        new java.math.BigDecimal("0.1")
                .compareTo(new java.math.BigDecimal(0.1)) == 0); // false.
~~~

`BigDecimal` also does not make every division terminate on its own. `1/3` has an infinite decimal expansion, so you must specify scale/rounding or a `MathContext`:

~~~java
java.math.BigDecimal third = java.math.BigDecimal.ONE.divide(
        new java.math.BigDecimal("3"), 2,
        java.math.RoundingMode.HALF_UP);
System.out.println(third); // 0.33.
~~~

`BigDecimal.equals` checks **both value and scale**: `new BigDecimal("1.00").equals(new BigDecimal("1.0"))` returns false; `compareTo` on that pair returns 0. This boundary is enough to understand **why you cannot recover exact decimals from an already-imprecise `double`**; the `Math.*Exact`/`BigDecimal` lesson at the end of the chapter goes deeper into scale, precision, rounding, division, and exact conversions.

`BigDecimal` is not automatically better than `double` in every application. Scientific computations that tolerate approximation may prefer `double` and stable algorithms. Choose based on domain, precision, units, and rounding policy.


## 14. Process for Choosing Numeric Types by Problem

| Need | Usually Appropriate Choice | Points to Check |
|---|---|---|
| Integer counter within 32-bit range | `int` | Integer overflow |
| Counter larger than 32-bit | `long` | Still has a 64-bit limit |
| Scientific measurement, error-tolerant math | `double` | Tolerance, NaN, Infinity, algorithm |
| Float data for API/hardware requiring binary32 | `float` | ~24-bit significand precision |
| Money stored in a fixed smallest unit | `long` when range suffices | Unit, conversion, and overflow |
| Decimal values that must be exact | `BigDecimal` | Construct from text, scale, rounding |
| Sum of very many floating-point numbers | `double` + suitable algorithm | Accumulated error and calculation order |
| Checking approximate equality | Business-driven tolerance | Absolute/relative error, extremes |

**There is no "right type for every real number."** The design rule is to identify **value range, required precision, units of measurement, tolerance, and rounding rules**, and only then choose the type and algorithm.

## 15. Standalone Runnable Java 17 Example

Create the exact file **`BinaryFloatingPointErrorDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public final class BinaryFloatingPointErrorDemo {
    private BinaryFloatingPointErrorDemo() {}

    static boolean nearlyEqual(
            double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0 || relTol < 0) {
            throw new IllegalArgumentException("invalid tolerance");
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.println("double sum=" + sum);
        System.out.println("sum == 0.3=" + (sum == 0.3));
        System.out.println("difference=" + (sum - 0.3));
        System.out.println("hex 0.1=" + Double.toHexString(0.1));

        float floatApprox = 0.1f;
        System.out.println("float 0.1 as double=" + (double) floatApprox);
        System.out.println("double literal printed=" + 0.1);
        System.out.println("float ulp at 2^24=" + Math.ulp(16_777_216f));
        System.out.println("float loses one="
                + (16_777_216f + 1f == 16_777_216f));
        double limit = 9_007_199_254_740_992d;
        System.out.println("double loses one=" + (limit + 1 == limit));

        double total = 0.0;
        for (int i = 0; i < 10; i++) {
            total += 0.1;
        }
        System.out.println("sum ten times=" + total);
        System.out.println("multiply ten=" + (0.1 * 10));

        double left = (1.0e16 + -1.0e16) + 1.0;
        double right = 1.0e16 + (-1.0e16 + 1.0);
        System.out.println("group left=" + left);
        System.out.println("group right=" + right);
        System.out.println("cancellation=" + ((1.0e16 + 1.0) - 1.0e16));

        System.out.println("near 0.3="
                + nearlyEqual(sum, 0.3, 1e-12, 1e-12));
        System.out.println("far from 1.1="
                + nearlyEqual(1.0, 1.1, 1e-12, 1e-12));
        System.out.println("NaN equals itself=" + (Double.NaN == Double.NaN));
        System.out.println("is NaN=" + Double.isNaN(0.0 / 0.0));
        System.out.println("infinite finite=" + Double.isFinite(1.0 / 0.0));
        System.out.println("signed zero ==" + (0.0 == -0.0));
        System.out.println("signed zero compare="
                + (Double.compare(0.0, -0.0) == 0));

        System.out.println("formatted="
                + String.format(Locale.ROOT, "%.2f", sum));

        BigDecimal decimal = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal exact=" + decimal);
        System.out.println("valueOf decimal="
                + BigDecimal.valueOf(0.1).add(BigDecimal.valueOf(0.2)));
        System.out.println("double constructor exact decimal="
                + (new BigDecimal(0.1)
                        .compareTo(new BigDecimal("0.1")) == 0));
        System.out.println("decimal division="
                + new BigDecimal("1").divide(
                        new BigDecimal("3"), 2, RoundingMode.HALF_UP));
        BigDecimal scaleA = new BigDecimal("1.00");
        BigDecimal scaleB = new BigDecimal("1.0");
        System.out.println("BigDecimal equals=" + scaleA.equals(scaleB));
        System.out.println("BigDecimal compare="
                + (scaleA.compareTo(scaleB) == 0));
    }
}
~~~

**Requirements:** JDK 17 or later, terminal in the directory containing the file. No Maven, Gradle, or libraries outside the JDK needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BinaryFloatingPointErrorDemo.java
java -cp . BinaryFloatingPointErrorDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BinaryFloatingPointErrorDemo.java
java -cp . BinaryFloatingPointErrorDemo
~~~

**Exact expected output:**

~~~text
double sum=0.30000000000000004
sum == 0.3=false
difference=5.551115123125783E-17
hex 0.1=0x1.999999999999ap-4
float 0.1 as double=0.10000000149011612
double literal printed=0.1
float ulp at 2^24=2.0
float loses one=true
double loses one=true
sum ten times=0.9999999999999999
multiply ten=1.0
group left=1.0
group right=0.0
cancellation=0.0
near 0.3=true
far from 1.1=false
NaN equals itself=false
is NaN=true
infinite finite=false
signed zero ==true
signed zero compare=false
formatted=0.30
decimal exact=0.3
valueOf decimal=0.3
double constructor exact decimal=false
decimal division=0.33
BigDecimal equals=false
BigDecimal compare=true
~~~

### Reading the Output by Group

1. `double sum` and `difference` show small yet observable discrepancies; `Double.toHexString` represents the stored value in hex floating-point form.
2. `float 0.1 as double` shows that widening a float value to double **does not restore** the original decimal number.
3. `float ulp at 2^24` and `double loses one` illustrate resolution shrinking as magnitude grows.
4. Adding 0.1 ten times differs from multiplying 0.1 once; order and rounding steps affect the result.
5. `group left/right` and `cancellation` illustrate non-associativity and loss of significant digits.
6. `nearlyEqual` only returns true for two numbers close within the illustrative tolerance; it is **not an exact mathematical comparison**.
7. `NaN`, Infinity, and signed zero have special rules requiring explicit handling.
8. `formatted=0.30` is only a display string; `BigDecimal` constructed from strings performs exact decimal addition in the example.
9. The last two results remind you that `BigDecimal.equals` distinguishes scale, whereas `compareTo` compares numeric value.

## 16. Common Mistakes and Fixes

| Misconception / Error | Issue | How to Handle It |
|---|---|---|
| `0.1 + 0.2 == 0.3` must be true | Decimal numbers are not exactly represented in binary64 | Use tolerance if the problem allows it, or exact decimal |
| Switching `float` to `double` removes error | The float value is already rounded | Choose appropriate precision **from the start** |
| Printing `0.1` means decimal 0.1 is stored exactly | `toString` uses a round-trip string | Distinguish display string from binary value |
| `double` stores every large integer | Above 2^53 it does not distinguish all adjacent integers | Use `long`/`BigInteger` per range |
| One `epsilon` fits every problem | Error depends on units and magnitude | Define absolute/relative tolerance |
| Adding 0.1 many times always equals multiplying once | Different rounding steps | Test summation algorithm and accuracy |
| Floating-point additions can be regrouped arbitrarily | Floating-point is not fully associative | Preserve algorithm order/business semantics |
| `(1e16 + 1) - 1e16` is always 1 | 1 is lost when added to a huge number | Choose another algorithm/type beforehand |
| Comparing NaN to itself with `==` | `NaN == NaN` is false | Use `Double.isNaN` |
| Formatter `%.2f` fixes calculation error | Only changes text representation | Specify actual data type and rounding |
| `new BigDecimal(0.1)` gives decimal 0.1 | The constructor reads the exact approximate double value | `new BigDecimal("0.1")` or `valueOf` |
| `BigDecimal.divide(1/3)` always runs automatically | Infinite decimals require rounding rules | Use appropriate scale/MathContext |
| `BigDecimal("1.00").equals(BigDecimal("1.0"))` | `equals` checks scale as well | `compareTo == 0` if you want to compare numeric value |

## 17. Exercises and Answers

### Exercise A — Observing Basic Error

~~~java
double a = 0.1 + 0.2;
System.out.println(a);
System.out.println(a == 0.3);
~~~

**Answer:**

~~~text
0.30000000000000004
false
~~~

### Exercise B — `float` Does Not Become More Accurate When Cast

~~~java
float value = 0.1f;
double promoted = value;
System.out.println(promoted);
~~~

**Answer:** `0.10000000149011612`. Converting to double preserves the approximate value already held in float.

### Exercise C — Large Integers

~~~java
double x = 9_007_199_254_740_992d;
System.out.println(x + 1.0 == x);
~~~

**Answer:** `true`. At `2^53`, binary64 cannot represent every adjacent integer.

### Exercise D — Using Exact Decimals

~~~java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");
System.out.println(a.add(b));
~~~

**Answer:** `0.3`.

### Exercise E — Why Does `BigDecimal` Division Need Rounding?

~~~java
// new BigDecimal("1").divide(new BigDecimal("3"))
~~~

**Answer:** `1/3` is an infinite decimal; it cannot be represented as an exact finite decimal. Specify scale and `RoundingMode`, or `MathContext`, per business requirements.

### Exercise F — Floating-Point Parentheses

~~~java
System.out.println((1e16 + -1e16) + 1.0);
System.out.println(1e16 + (-1e16 + 1.0));
~~~

**Answer:**

~~~text
1.0
0.0
~~~

The difference comes from rounding at intermediate steps.

## 18. Checklist and Conclusion

- [ ] Understand that `float`/`double` represent **finite binary numbers**, not arbitrary decimal numbers.
- [ ] Know that `0.1` and `0.2` have no exact finite binary representation.
- [ ] Distinguish binary32 (float) and binary64 (double), and their finite precision.
- [ ] Know that literal `0.1f` is float and `0.1` is double.
- [ ] Understand that converting from float to double **does not restore** error that already occurred.
- [ ] Understand the meaning of ULP and that larger numbers have larger representation steps.
- [ ] Do not compare measurements/approximate calculations with `==` if a tolerance is required.
- [ ] Know how to choose absolute/relative tolerances according to business domain and units.
- [ ] Recognize accumulated error and results that depend on addition order.
- [ ] Recognize catastrophic cancellation when subtracting nearly equal numbers.
- [ ] Handle NaN/Infinity/signed zero explicitly when needed.
- [ ] Know that number formatting affects only the **display string**.
- [ ] Know how to construct `BigDecimal` from String when exact decimals are needed.
- [ ] Know that `BigDecimal.divide` needs rounding when the quotient does not terminate.
- [ ] Distinguish `BigDecimal.equals` from `compareTo` regarding scale.
- [ ] Compile and run `BinaryFloatingPointErrorDemo.java` on JDK 17+, and compare against exact expected output.

**Conclusion:** Errors in `float`/`double` are a natural consequence of finite binary floating-point representation, not Java computing randomly. Choose data types based on **precision level and value range**, avoid comparing approximate numbers mechanically with `==`, consider the effect of operation order, and use `BigDecimal` or fixed-unit integers when business logic demands exact decimal numbers.