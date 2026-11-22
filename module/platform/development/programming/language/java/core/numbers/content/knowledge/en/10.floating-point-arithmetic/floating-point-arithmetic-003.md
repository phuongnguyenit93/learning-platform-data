# Overflow, Underflow, and Subnormal Values in Java Floating-Point Arithmetic

## 1. Objectives and Big Picture

Java's `float` and `double` types use binary floating-point numbers according to IEEE 754. They can represent many very large and very small numbers, but their **finite value range** and **precision** are limited. An operation with a valid mathematical result can still yield `Infinity`, `0.0`, or a *subnormal* number when stored into `float`/`double`.

This lesson focuses on three phenomena:

- **Overflow:** the magnitude of the result exceeds the representable finite range; in ordinary Java operations, the result can become `+Infinity` or `-Infinity`.
- **Underflow:** a mathematically non-zero result is too close to 0 to be kept at normal precision; Java may round it to a subnormal number, or to `+0.0`/`-0.0`.
- **Subnormal:** a finite non-zero number whose magnitude is smaller than the smallest positive *normal* number, helping represent values near 0 via *gradual underflow*.

Do not confuse these phenomena with **integer overflow** (integers wrapping around modulo $2^n$) or a compile-time error when a literal has an unrepresentable exponent.

## 2. IEEE 754 Ranges in `float` and `double`

| Property | `float` (binary32) | `double` (binary64) |
| --- | --- | --- |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent bits | 8 | 11 |
| Stored fraction bits | 23 | 52 |
| Effective precision of normal numbers | 24 bits | 53 bits |
| Smallest positive normal number | 2⁻¹²⁶ ≈ 1.17549435 × 10⁻³⁸ | 2⁻¹⁰²² ≈ 2.2250738585072014 × 10⁻³⁰⁸ |
| Smallest positive subnormal number | 2⁻¹⁴⁹ ≈ 1.4 × 10⁻⁴⁵ | 2⁻¹⁰⁷⁴ ≈ 4.9 × 10⁻³²⁴ |
| Largest positive finite number | ≈ 3.4028235 × 10³⁸ | ≈ 1.7976931348623157 × 10³⁰⁸ |

Java provides built-in useful constants:

~~~java
Float.MAX_VALUE
Float.MIN_NORMAL
Float.MIN_VALUE
Double.MAX_VALUE
Double.MIN_NORMAL
Double.MIN_VALUE
~~~

**Very easy to confuse:** `Double.MIN_VALUE` **is not the smallest negative value**. It is the **smallest positive non-zero number**, i.e. the lowest positive subnormal number. The finite negative value with the largest magnitude is `-Double.MAX_VALUE`. The same applies to `Float.MIN_VALUE`.

The finite domain of `double` has a negative interval, zero, and a positive interval; in addition, there are `-Infinity`, `+Infinity`, and `NaN` (*Not a Number*). IEEE 754 distinguishes **`+0.0` and `-0.0`** by their sign bit even though the `==` operator considers them equal.

## 3. Why Are There Normal and Subnormal Numbers?

A non-zero *normal* binary number conceptually has the form:

\[
(-1)^s \times (1.f)_2 \times 2^e
\]

Where `s` is the sign bit, `f` represents the fraction bits, and `e` is the decoded exponent. The leading `1` of the significand of a normal value is an **implicit** bit. Therefore, `double` stores 52 fraction bits but has 53 significant bits for normal numbers (and `float` has 23 + 1 = 24 bits).

At the lowest exponent, the normal exponent cannot be decreased any further. The IEEE 754 standard allows **subnormal** numbers to use a significand without the implicit leading `1` bit:

\[
(-1)^s \times (0.f)_2 \times 2^{e_{\min}}
\]

Specifically, for binary64: the smallest positive normal number is 2⁻¹⁰²²; a subnormal number has the form `k × 2⁻¹⁰⁷⁴`, with integer `k` from 1 to 2⁵²−1. The gap between two consecutive positive subnormal numbers is always `Double.MIN_VALUE`.

Therefore, Java can represent numbers smaller than `Double.MIN_NORMAL` without immediately rounding to 0. In return, **the number of effective significant bits decreases** as the magnitude of a subnormal approaches 0.

<text>Visualizing approaching 0:</text>

~~~text
... normal ...  2^-1022  |  subnormal ...  2^-1074  |  +0.0
                 ↑                         ↑
           MIN_NORMAL                 MIN_VALUE
~~~

The diagram is a conceptual illustration; spacing along the number line is not drawn to scale.

### Normal/Subnormal Boundary

~~~java
double smallestNormal = Double.MIN_NORMAL;
double largestSubnormal = Math.nextDown(smallestNormal);
double smallestSubnormal = Double.MIN_VALUE;

System.out.println(largestSubnormal < smallestNormal); // true
System.out.println(largestSubnormal > 0.0);            // true
System.out.println(Math.nextUp(0.0) == smallestSubnormal); // true
~~~

The short code snippets in this lesson, except the complete program in Section 8, are written to be placed inside a method or `main`.

## 4. Overflow: Result Exceeds the Largest Finite Number

Consider multiplication:

~~~java
double x = Double.MAX_VALUE;
double overflow = x * 2.0;
System.out.println(overflow);                 // Infinity
System.out.println(Double.isInfinite(overflow)); // true
~~~

`Double.MAX_VALUE` is the largest positive finite `double`. The mathematical result of doubling it is far larger than the finite range, so the multiplication is rounded according to floating-point rules and returns `+Infinity`.

For a negative result exceeding the limit, you can get `-Infinity`:

~~~java
double negativeOverflow = -Double.MAX_VALUE * 2.0;
System.out.println(negativeOverflow); // -Infinity
~~~

Several important points:

1. Ordinary Java floating-point operations **do not throw `ArithmeticException`** on overflow/underflow.
2. `Infinity` is a special floating-point value. Subsequent calculations can keep yielding `Infinity` or produce `NaN`, such as `Infinity - Infinity`.
3. Overflow can happen even when the **final result of an algebraic transformation** should be finite: an intermediate result may overflow first.

~~~java
double a = 1e200;
double b = 1e200;

double unstable = (a * b) / b;
double rearranged = a * (b / b);

System.out.println(unstable);   // Infinity
System.out.println(rearranged); // 1.0E200
~~~

In real arithmetic, the two expressions are equal when `b != 0`. In floating-point arithmetic, the intermediate multiplication `a * b` overflowed. Changing the order of computation is only appropriate when you understand the value range, rounding rules, handling of zero/Infinity/NaN, and the accuracy requirements of the problem.

### Infinity Differs from NaN

~~~java
double inf = Double.MAX_VALUE * 2.0;
double undefined = inf - inf;

System.out.println(Double.isInfinite(inf)); // true
System.out.println(Double.isNaN(undefined)); // true
~~~

`NaN` represents an undefined result in floating-point semantics; it is not an infinite number. Another example: `0.0 / 0.0` yields `NaN`, while `1.0 / 0.0` yields `Infinity`. None of these three results throws an arithmetic exception.

## 5. Underflow: Result Too Small to Keep Full Precision

For floating-point numbers, underflow happens at the **near-zero** end of the number range. You must distinguish a *subnormal result that is still non-zero* from a *result that has been rounded to 0*.

~~~java
double smallButRepresentable = Double.MIN_NORMAL / 2.0;
double tooSmall = Double.MIN_VALUE / 2.0;

System.out.println(smallButRepresentable > 0.0); // true
System.out.println(smallButRepresentable < Double.MIN_NORMAL); // true
System.out.println(tooSmall); // 0.0
~~~

`Double.MIN_NORMAL / 2` equals 2⁻¹⁰²³ and is representable as a subnormal number. `Double.MIN_VALUE / 2` equals 2⁻¹⁰⁷⁵, lying exactly halfway between 0 and the smallest positive subnormal number. **Round to nearest, ties to even** produces `+0.0`.

**Note on IEEE 754 terminology:** underflow as a technical exception condition relates to *tininess* and loss of accuracy. In Java programming lessons, "underflow to subnormal/zero" describes behavior in the very small magnitude region. You should not claim that **every** subnormal result is a bug or an inaccurate underflow operation: many subnormal results (such as dividing `MIN_NORMAL` by 2) are still exact.

### Gradual Underflow

Without subnormals, a positive result smaller than `MIN_NORMAL` would abruptly become 0. Subnormals provide a **gradual** transition: many small values remain non-zero, though relative accuracy degrades progressively.

Example:

~~~java
double halfNormal = Double.MIN_NORMAL / 2.0;
double smaller = halfNormal / 2.0;

System.out.println(halfNormal != 0.0); // true
System.out.println(smaller != 0.0);    // true
~~~

This behavior is useful when subtracting two close positive numbers yields a very small value; information about the difference can still be preserved if the result lies within the representable subnormal range.

## 6. Sign of Zero on Underflow

`double` distinguishes `+0.0` and `-0.0`. A positive operation that is too small usually rounds to `+0.0`; the corresponding negative operation can round to `-0.0`.

~~~java
double positiveZero = Double.MIN_VALUE / 2.0;
double negativeZero = -Double.MIN_VALUE / 2.0;

System.out.println(positiveZero); // 0.0
System.out.println(negativeZero); // -0.0
System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
~~~

Therefore, do not conclude that two floating-point values have identical bit representations just because `a == b`. When you need to inspect the sign of zero or the bits of NaN, you can use `Double.doubleToRawLongBits`; for `float`, use `Float.floatToRawIntBits`. Floating-point comparison, sorting, and serialization mechanisms must explicitly define whether `-0.0` matters.

## 7. Java APIs to Detect Floating-Point Conditions

| API | Purpose |
| --- | --- |
| `Double.isFinite(x)`, `Float.isFinite(x)` | Check if x is a finite number (including ±0, normal, and subnormal) |
| `Double.isInfinite(x)`, `Float.isInfinite(x)` | Check for ±Infinity |
| `Double.isNaN(x)`, `Float.isNaN(x)` | Check for NaN |
| `Double.MIN_NORMAL`, `Float.MIN_NORMAL` | Smallest positive threshold of normal numbers |
| `Double.MIN_VALUE`, `Float.MIN_VALUE` | Smallest positive non-zero number: lowest subnormal |
| `Math.ulp(x)` | Unit in the last place spacing at x |
| `Math.nextUp(x)`, `Math.nextDown(x)` | Adjacent upper/lower floating-point value |

Function to detect finite, non-zero subnormals:

~~~java
static boolean isSubnormal(double x) {
    return Double.isFinite(x)
            && x != 0.0
            && Math.abs(x) < Double.MIN_NORMAL;
}
~~~

This is a standalone Java 17 method inside a class body (without `main`). The condition `x != 0.0` excludes both `+0.0` and `-0.0`. The condition `isFinite` excludes Infinity/NaN; `Math.abs(x) < MIN_NORMAL` separates the subnormal range from the normal range. A similar expression applies to `float` using `Float.MIN_NORMAL` and `Float.isFinite`.

In particular:

~~~java
System.out.println(Math.ulp(0.0) == Double.MIN_VALUE); // true
System.out.println(Math.ulp(Double.MIN_NORMAL) == Double.MIN_VALUE); // true
System.out.println(Math.nextUp(0.0) == Double.MIN_VALUE); // true
~~~

A *normal* finite floating-point number has a step size depending on its magnitude. In the positive subnormal region, consecutive values are spaced apart by exactly `Double.MIN_VALUE`.

You should not use `Math.getExponent(x)` alone to detect subnormals, because it returns `Double.MIN_EXPONENT - 1` for **both zero and subnormals** (−1023 for `double`).

## 8. Complete Java 17+ Program: Compile and Observe

Create the file `FloatingRangeDemo.java`:

~~~java
public class FloatingRangeDemo {
    private static boolean isSubnormal(double x) {
        return Double.isFinite(x)
                && x != 0.0
                && Math.abs(x) < Double.MIN_NORMAL;
    }

    public static void main(String[] args) {
        double overflow = Double.MAX_VALUE * 2.0;
        double subnormal = Double.MIN_NORMAL / 2.0;
        double lost = Double.MIN_VALUE / 2.0;
        double negativeZero = -Double.MIN_VALUE / 2.0;

        System.out.println("overflow=" + overflow);
        System.out.println("overflow finite=" + Double.isFinite(overflow));
        System.out.println("subnormal=" + subnormal);
        System.out.println("is subnormal=" + isSubnormal(subnormal));
        System.out.println("min normal=" + Double.MIN_NORMAL);
        System.out.println("min positive=" + Double.MIN_VALUE);
        System.out.println("underflow to zero=" + lost);
        System.out.println("negative zero=" + negativeZero);
        System.out.println("negative reciprocal=" + (1.0 / negativeZero));
        System.out.println("ulp zero=" + Math.ulp(0.0));

        double parsedBig = Double.parseDouble("1e309");
        double parsedSmall = Double.parseDouble("1e-400");
        System.out.println("parsed big=" + parsedBig);
        System.out.println("parsed small=" + parsedSmall);

        float fSubnormal = Float.MIN_NORMAL / 2.0f;
        float fOverflow = Float.MAX_VALUE * 2.0f;
        System.out.println("float subnormal=" +
                (fSubnormal > 0.0f && fSubnormal < Float.MIN_NORMAL));
        System.out.println("float infinity=" + Float.isInfinite(fOverflow));

        double nan = overflow - overflow;
        System.out.println("NaN detected=" + Double.isNaN(nan));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 FloatingRangeDemo.java
java FloatingRangeDemo
~~~

Stdout output:

~~~text
overflow=Infinity
overflow finite=false
subnormal=1.1125369292536007E-308
is subnormal=true
min normal=2.2250738585072014E-308
min positive=4.9E-324
underflow to zero=0.0
negative zero=-0.0
negative reciprocal=-Infinity
ulp zero=4.9E-324
parsed big=Infinity
parsed small=0.0
float subnormal=true
float infinity=true
NaN detected=true
~~~

Analysis of each group of results:

- `MAX_VALUE * 2` overflows to Infinity; `isFinite` reports false.
- `MIN_NORMAL / 2` falls in the subnormal region while remaining non-zero; the program checks by value range rather than relying only on print formatting.
- `MIN_VALUE / 2` is smaller than the smallest non-zero positive value, so it rounds to 0.
- Underflow of a negative number can produce `-0.0`; taking the reciprocal demonstrates that the sign is meaningful.
- `Double.parseDouble` converts out-of-range strings to Infinity/0 per floating-point conversion rules; parsing does not replace **range validation** if the application requires non-zero finite results.
- `float` also has a subnormal range and overflow, but with different thresholds near 0/Infinity compared to `double`.
- `Infinity - Infinity` produces NaN.

## 9. Literals That Are Too Large/Small: Different from Runtime Operation Results

Floating-point literals in Java source code have compile-time rules. These examples **do not compile**:

~~~java
// double tooLarge = 1e309; // double literal out of range
// double tooSmall = 1e-400; // non-zero double literal too small to remain nonzero
// float alsoTooLarge = 1e39f; // float literal out of range
~~~

When you need to demonstrate runtime overflow/underflow, perform operations from valid values or parse from strings at runtime:

~~~java
double overflowRuntime = 1e308 * 10.0;
double underflowRuntime = 1e-300 * 1e-300;

System.out.println(overflowRuntime);  // Infinity
System.out.println(underflowRuntime); // 0.0
~~~

`Double.parseDouble("1e309")` returns Infinity and `Double.parseDouble("1e-400")` returns 0.0; when string values come from configuration or users, developers need to validate them to avoid silently accepting out-of-range data.

Special note: the literal `0.0` is completely valid; `0x0.0p0` is as well. The restriction on overly small *non-zero* literals reflects compile-time rules, not that the language forbids zero.

## 10. Underflow Is Not the Same as Ordinary Loss of Precision

Most decimal numbers have no finite binary representation, such as `0.1`. That produces **rounding error**, but not necessarily underflow:

~~~java
double x = 0.1 + 0.2;
System.out.println(x); // 0.30000000000000004
~~~

`0.30000000000000004` is the rounded result of normal numbers and addition; it is **not** in the subnormal region. Underflow concerns magnitudes too small near 0, not every floating-point error.

A subnormal result can still be an **exact** representation of an operation. For example, `Double.MIN_NORMAL / 2.0` is 2⁻¹⁰²³ and can be represented exactly as a subnormal. The distinction between **range** and **precision** is fundamental to floating-point analysis.

Additionally, do not confuse underflow of a **value** with exponent underflow in `Math.exp`: for instance, `Math.exp(-1000)` can return 0.0 because the mathematical result is too small to represent as a `double`, not because a machine integer exponent "wrapped around".

## 11. Common Issues and How to Handle Them

### 11.1. Intermediate Overflow Even When the Desired Result Is Finite

The vector length formula:

\[
\sqrt{x^2 + y^2}
\]

can overflow in `x*x`/`y*y` even though the final result is still smaller than `Double.MAX_VALUE`.

~~~java
double x = 1e308;
double y = 1e308;

double naive = Math.sqrt(x * x + y * y);
double stable = Math.hypot(x, y);

System.out.println(naive);  // Infinity
System.out.println(stable); // 1.4142135623730951E308
~~~

`Math.hypot` is designed to reduce the risk of intermediate overflow/underflow. It still returns Infinity when the final magnitude truly exceeds the representable range.

### 11.2. Product of Many Very Small Numbers Rounded to 0

~~~java
double a = 1e-200;
double b = 1e-200;
double c = 1e200;

double lostFirst = (a * b) * c;
double keptFirst = a * (b * c);

System.out.println(lostFirst); // 0.0
System.out.println(keptFirst); // 1.0E-200
~~~

When computing products or probabilities of many very small numbers, sometimes moving to the **log-domain** (summing logarithms instead of multiplying directly, then applying stable transformations when needed) helps avoid intermediate underflow. Special care is needed for zero, negative values, NaN, and whether the final returned value is representable.

### 11.3. Print Formatting Differs from Exactness

Java prints `Double.MIN_VALUE` as `4.9E-324`; that expression is a short decimal string sufficient to round-trip back to the same `double` value, not a claim that the binary value is strictly equal to the two-digit decimal rational 4.9 × 10⁻³²⁴.

Similarly, `System.out.println(0.1)` prints `0.1`, while internal storage is a binary64 approximation of 0.1. Do not infer exactness solely from the displayed digits.

### 11.4. Validate Results Before Use

Example receiving a floating-point number from a computation:

~~~java
static double requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Result must be finite");
    }
    return value;
}
~~~

This function rejects Infinity/NaN but **allows 0 and subnormals**. If business rules forbid a non-zero result from collapsing to 0, there is no way to tell **merely by looking at the final `0.0` result** whether an earlier step had a value smaller than the storage range. You need to control input data, use a more numerically stable method, or use a wider-precision model.

### 11.5. When to Use `BigDecimal`?

`BigDecimal` represents base-10 numbers with arbitrary precision (bounded by resources and scale range) and controlled rounding rules. It fits currency, exact decimal data, or calculations needing more digits than `double`:

~~~java
import java.math.BigDecimal;

// Illustrative snippet inside a method:
BigDecimal x = new BigDecimal("1e400");
BigDecimal y = x.multiply(BigDecimal.TEN);
System.out.println(y.toEngineeringString()); // 10E+400
~~~

`BigDecimal` has no `NaN`/`Infinity` values like `double`; it is not a drop-in replacement for `double` across all scientific problems. When constructing a `BigDecimal` from a decimal number that must be preserved verbatim, prefer the string constructor (`new BigDecimal("0.1")`) or `BigDecimal.valueOf(double)` as appropriate; `new BigDecimal(0.1)` preserves the exact **binary value that was already approximated** beforehand.

Data type selection depends on the problem: engineering measurements that tolerate error typically still use `double`; finance and exact decimal data typically use `BigDecimal`; extremely large/small problems may require scaling, log-domain, or specialized numerical libraries.

## 12. Boundary Values and Things Not to Confuse

| Expression (placed inside a method) | Result/Meaning |
| --- | --- |
| `Double.MAX_VALUE * 2.0` | `Infinity`: positive overflow |
| `-Double.MAX_VALUE * 2.0` | `-Infinity`: negative overflow |
| `Double.MIN_NORMAL / 2.0` | Positive non-zero subnormal, **exact** |
| `Double.MIN_VALUE / 2.0` | `+0.0` by round-to-nearest ties-to-even |
| `-Double.MIN_VALUE / 2.0` | `-0.0` |
| `Math.nextUp(0.0)` | `Double.MIN_VALUE` |
| `Math.nextDown(0.0)` | `-Double.MIN_VALUE` |
| `Double.isFinite(Double.MIN_VALUE)` | `true`: subnormals are still finite |
| `Double.isNaN(Double.POSITIVE_INFINITY)` | `false` |
| `Double.NaN == Double.NaN` | `false` under IEEE 754 `==` |
| `Double.compare(-0.0, +0.0) < 0` | `true`: ordering via `Double.compare` distinguishes signed zero |
| `1.0 / 0.0` | `Infinity`, does not throw `ArithmeticException` |
| `1 / 0` | Integer division error: differs from floating-point division rules |

### Java 17 and Strict Floating Point

Starting in **Java 17**, floating-point semantics are always strict under the Java Language Specification (JEP 306). The `strictfp` keyword still exists for backward compatibility with older code, but is no longer needed to enforce strict behavior on Java 17+. This gives `float`/`double` code deterministic language rules, but **does not eliminate** overflow, underflow, subnormals, or rounding error.

Java does not provide, through ordinary floating-point operations, a mechanism that automatically throws exceptions on every overflow/underflow or an IEEE 754 status flag that programmers can always access directly. If a system needs to detect risks, combine value checks (`isFinite`, subnormal range) with algorithm design and input data control.

## 13. Self-Check

**Question 1.** Why is `Double.MIN_VALUE` greater than 0 yet smaller than `Double.MIN_NORMAL`?

Because `MIN_VALUE` is the smallest positive subnormal number (2⁻¹⁰⁷⁴), whereas `MIN_NORMAL` is the smallest positive normal number (2⁻¹⁰²²). The name `MIN_VALUE` here refers to **positive non-zero** magnitude, not the minimum negative point on the number line.

**Question 2.** Must `Double.MIN_NORMAL / 2.0` become 0 or lose precision?

No. 2⁻¹⁰²³ is a subnormal value that can be represented **exactly** in binary64.

**Question 3.** Why does `Double.MIN_VALUE / 2.0` yield `0.0`?

Because the mathematical value 2⁻¹⁰⁷⁵ lies halfway between 0 and the smallest non-zero positive value; the default round-to-nearest ties-to-even chooses +0.0.

**Question 4.** Can you rely on `Double.isFinite(result)` to detect all underflow?

No. Both `0.0` and subnormal numbers are **finite**. `isFinite` detects NaN/Infinity; detecting subnormals additionally requires checking non-zero and `abs(result) < MIN_NORMAL`, while rounding to 0 must be detected using knowledge of the problem or earlier computation steps.

**Question 5.** Why is `Math.hypot(x, y)` usually safer than `Math.sqrt(x*x + y*y)`?

It is designed to mitigate intermediate overflow and underflow when computing distance; direct squaring can produce Infinity/0 before the square root is applied.

**Question 6.** Should every `double` calculation be replaced with `BigDecimal`?

No. `BigDecimal` is useful when decimal exactness and rounding control are required; it changes the data model, speed, memory footprint, and algorithms. For scientific/engineering problems, choosing `double` and numerically stable algorithms may be the better option.

## 14. Summary and References

- **Overflow:** magnitude exceeds finite range → typically `±Infinity`; check `isFinite`/`isInfinite`.
- **Underflow:** magnitude too close to 0 → subnormal result or rounded to `±0.0`; not necessarily a Java exception.
- **Subnormal:** non-zero value with `abs(x) < MIN_NORMAL`; provides *gradual underflow* but has fewer effective significant bits.
- `MIN_VALUE` is the smallest non-zero positive number, whereas `MIN_NORMAL` is the smallest positive normal number.
- Write algorithms to avoid overly large/small intermediate results and check NaN, Infinity, signed zero, and accuracy as needed.

Reference documentation:

- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) and [Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): `MAX_VALUE`, `MIN_NORMAL`, `MIN_VALUE`, and inspection APIs.
- [Java SE 17 — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `ulp`, `nextUp`, `nextDown`, `hypot`.
- [JLS SE 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): finite numbers, subnormals, NaN, Infinity, and zero.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): strict semantics change in Java 17.