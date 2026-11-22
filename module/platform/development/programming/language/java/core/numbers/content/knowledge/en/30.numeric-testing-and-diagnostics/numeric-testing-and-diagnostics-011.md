# Printing Bit Patterns, Expression Types, and Precision to Investigate Unexpected Results in Java

## 1. Why Can a Numeric Expression Produce an “Unexpected” Result?

When investigating number-related bugs in Java, printing only the final value with `System.out.println(result)` is often insufficient. The same surprising result can stem from different root causes:

- **Expression type differs from expectations:** `5 / 2` is a division between two `int`s, yielding `2`, even if subsequently assigned to a `double`.
- **Overflow before widening:** `int * int` is computed as `int`, potentially overflowing before being assigned to a `long` variable.
- **Approximate binary representation:** `0.1` and `0.2` have no exact finite representation in IEEE 754 binary, so their `double` sum can print as `0.30000000000000004`.
- **Type conversion losing significant bits:** `long` can hold a large integer, yet `double` cannot represent every integer in that same range exactly.
- **Confusing precision with scale:** `BigDecimal("1.2300")` has precision `5` and scale `4`; stripping trailing zeros or rounding alters the representation.
- **Confusing value and bit pattern:** `+0.0` and `-0.0` compare equal under `==` yet have different bit patterns.

To find the root cause, collect **value + expression type + bit pattern/representation + precision and conversion point**. This is a diagnostic workflow, not a mandate to analyze bits manually for every calculation.

## 2. Read Expression Types Properly Before Looking at Values

Java determines the **type of an expression at compile time** according to conversion and *numeric promotion* rules. The type of the receiving variable does not retroactively change the kind of operation performed earlier.

Example:

```java
double a = 5 / 2;    // int / int division => int 2, then becomes double 2.0.
double b = 5 / 2.0;  // Has a double operand => double division => 2.5.

int x = 50_000;
int y = 50_000;
long wrong = x * y;        // int * int overflows before assigning to long.
long right = (long) x * y; // Cast x to long BEFORE multiplication.
```

Corresponding results:

| Expression | Computation type | Result |
|---|---|---|
| `5 / 2` | `int` | `2` |
| `(double) (5 / 2)` | `int` during division; converted to `double` afterward | `2.0` |
| `5 / 2.0` | `double` | `2.5` |
| `x * y` with both `int = 50_000` | `int` | `-1794967296` (overflow) |
| `(long) x * y` | `long` | `2500000000` |
| `Integer.MAX_VALUE + 1` | `int` | `-2147483648` (wraparound overflow) |

Ordinary binary numeric operations apply **binary numeric promotion**: `byte`, `short`, and `char` are normally promoted to `int`; if one operand is `long`, many operations compute as `long`; if `float` or `double` is present, the operation takes that type per promotion order. Do not infer operation types solely from the declared types of narrow operands.

For instance, `byte left = 10; byte right = 20;` yet `left + right` has expression type **`int`**, not `byte`. And `var total = left + right;` infers `total` as `int` because `var` takes the compile-time expression type.

### Diagnosing Types Using Overloads

Primitives like `int`/`double` have no `getClass()`. If you cast to `Object` and call `getClass()`, **boxing** creates `Integer`/`Double`, showing the wrapper class rather than directly revealing the original primitive expression. An effective teaching and checking technique is overloading:

```java
static String kind(int value)    { return "int"; }
static String kind(long value)   { return "long"; }
static String kind(double value) { return "double"; }

// kind(5 / 2) => "int"
// kind(5 / 2.0) => "double"
// kind(left + right), with two bytes => "int"
```

This is an **illustrative snippet placed inside a class**, not a standalone program. The compiler selects the overload from the expression type at the call site; thus you can use this in a small test snippet to confirm type predictions.

Remember: the receiving variable's type, a subexpression's type, and the post-cast type can all differ. Inspect starting from the **first expression that loses information**, not just the variable printed at the end.

## 3. Printing Integer Bit Patterns: Two's Complement and Fixed Width

`int` is a 32-bit signed integer; `long` is a 64-bit signed integer. Java uses **two's-complement** representation for signed integers. When diagnosing overflow, printing numbers in hexadecimal or binary lets you directly see the stored bits:

```java
int n = -1;
System.out.printf("%08X%n", n); // FFFFFFFF
System.out.println(Integer.toBinaryString(n));
// 11111111111111111111111111111111
```

`%08X` prints an `int` as a hex string at least 8 characters wide; `%016X` is suitable for viewing all 16 hex digits of a 64-bit `long`. Uppercase `X` uses uppercase hex letters, and `%n` prints a platform newline.

For an `int` value, `Integer.toHexString(n)` and `Integer.toBinaryString(n)` are also helpful, though they do not automatically pad leading zeros for positive numbers, so formatting is needed when comparing bit positions side by side.

For example, `Integer.MAX_VALUE` is `0x7FFFFFFF`. After adding `1` in `int`, the bit pattern becomes `0x80000000`, interpreted as `Integer.MIN_VALUE`. This is a 32-bit range overflow, **not a printing bug**.

To **detect overflow rather than silently accepting wrapped results**, use `Math.addExact(int,int)` or `Math.multiplyExact(int,int)`. These methods throw `ArithmeticException` when the mathematical result cannot be represented in the target type. If a larger range is needed, widen to `long` **before computing** or use `BigInteger` as required. Casting after an `int` operation has already overflowed cannot restore lost bits.

### Note on Arbitrary-Magnitude Integers

`BigInteger` is not fixed to 32 or 64 bits. `big.toString(2)` prints a base-2 value string, yet for negative values it places a minus sign in front; this is **not** a fixed machine-width two's-complement dump. When you need to inspect 32-bit/64-bit two's complement, operate on `int`/`long` or explicitly define the desired bit width.

`BigInteger.bitLength()` reports the minimum bit length per the API's definition; it differs from printing the full fixed-width bit string of a machine word.

## 4. Floating Point: Inspecting Decimal Value and IEEE 754 Bit Patterns Together

`float` in Java uses IEEE 754 binary32 (32 bits); `double` uses binary64 (64 bits). The bit fields consist of:

| Type | Sign bit | Exponent bits | Stored fraction bits | Effective binary precision of normal numbers |
|---|---:|---:|---:|---:|
| `float` | 1 | 8 | 23 | 24 bits |
| `double` | 1 | 11 | 52 | 53 bits |

For finite *normal* numbers, there is an implicit leading significant bit; thus effective precision exceeds the stored fraction bits. Subnormal values use a different mechanism and have lower relative precision near zero.

Decimal fractions such as `0.1` and `0.2` have non-terminating expansions in binary. The JVM stores the nearest representable binary value in the chosen format. When adding approximations and rounding back to `double`, the result may not equal `0.3` exactly.

How to inspect bit patterns without altering the value:

```java
double value = 0.1;
long bits = Double.doubleToRawLongBits(value);
System.out.printf("0.1 double bits: %016X%n", bits);

float small = 0.1f;
int floatBits = Float.floatToRawIntBits(small);
System.out.printf("0.1f float bits: %08X%n", floatBits);
```

`Double.doubleToRawLongBits` returns the **actual 64-bit pattern** of a `double` as a `long`; `Float.floatToRawIntBits` returns the **actual 32-bit pattern** of a `float` as an `int`. Even though the `long` value may appear signed when viewed as an integer, the bits remain intact, making hex formatting convenient for inspection.

The two methods without `Raw` — `Double.doubleToLongBits` and `Float.floatToIntBits` — **normalize NaN forms** to a canonical NaN pattern; if investigating NaN payload bits, clearly distinguish raw from non-raw methods. For ordinary finite numbers, the outputs are identical.

**Important distinction:** the IEEE 754 bit pattern describes **bit positions within the value**, not directly **byte order in memory**. Endianness during byte serialization is a separate concern.

### What Do the Bits of Decimal Numbers Reveal?

In this concrete example:

- `0.1` has pattern `3FB999999999999A`.
- `0.2` has pattern `3FC999999999999A`.
- `0.1 + 0.2` has pattern `3FD3333333333334`, and `Double.toString` renders it as `0.30000000000000004`.

The difference in bit patterns explains why `sum == 0.3` can return `false` even when two displayed numbers look almost alike. `Double.toString` picks a decimal string short enough to round-trip back to the `double` value, **not a measure of how many digits of the mathematical value are exact**.

When debugging, print `Double.toString(value)`, raw bit patterns, and if needed, the difference from the expected value. Do not force an explanation of an arbitrary bit pattern based solely on decimal digits without accounting for binary representation.

### Two Signed Zeros

`+0.0` and `-0.0` compare `true` with `==`, yet have different sign bits:

```text
+0.0 bits: 0000000000000000
-0.0 bits: 8000000000000000
```

Thus, checking only `a == b` is insufficient when investigating the sign of zero. The two zeros can also yield different results in certain operations, such as `1.0 / +0.0` giving positive infinity and `1.0 / -0.0` giving negative infinity.

Likewise, `Double.NaN == Double.NaN` is `false`; use `Double.isNaN(value)` to detect NaN and `Double.isFinite(value)` when requiring finite numbers. When logging NaN bit patterns, remember intermediate operations can alter NaN payloads, and canonical APIs can erase distinctions between payloads.

## 5. Precision, ULP, and Accuracy of Floating-Point Numbers

You should not loosely state that `double` “has 16 exact decimal digits” and assume every 16-digit number is representable. Binary64 has **53 bits of binary precision**, typically corresponding to about 15–17 significant decimal digits depending on conversion and problem. Binary32 has **24 bits of binary precision**, typically around 6–9 decimal digits. Precision and spacing between representable numbers **depend on magnitude**.

**ULP** (*unit in the last place*) is the step size at the least significant bit position in the value region under consideration. In Java:

```java
System.out.println(Math.ulp(1.0));
// 2.220446049250313E-16
```

Just above `1.0`, the distance to the next representable `double` is \(2^{-52}\), approximately `2.22 × 10^-16`. At other magnitudes, ULP changes. Hence a single absolute epsilon does not fit all `double` comparisons across widely differing scales.

When comparing floating-point numbers with an allowed error, define tolerance from **problem requirements** while accounting for magnitude and boundary cases, for example:

```java
static boolean approximatelyEqual(double a, double b,
                                  double absTol, double relTol) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return a == b; // +Infinity/-Infinity compare via ==; NaN is false.
    }
    double delta = Math.abs(a - b);
    return delta <= Math.max(absTol,
            relTol * Math.max(Math.abs(a), Math.abs(b)));
}
```

This is an **illustrative function**, suitable when data ranges and tolerances are chosen per requirements; for huge numbers, subtracting `a - b` can overflow to infinity even though both operands are finite. A production comparison algorithm must handle those boundaries, zero, NaN, infinity, and domain rules. Never pick `1e-9` mechanically for every quantity.

### Very Large `long` Integers Passing Through `double`

A `double` has 53 bits of precision, so it represents every integer with absolute value **at most \(2^{53}\)** exactly; yet not every integer above that threshold is exactly representable. Example:

```java
long exact = 9_007_199_254_740_993L;   // 2^53 + 1
long after = (long) (double) exact;      // 9007199254740992
```

Here casting `long → double` rounds the value to the nearest representable integer and casting back to `long` yields an off-by-1 discrepancy. Printing exact `double` bits or comparing back against `long` exposes where information was lost. If an algorithm requires exact integers, do not route through `float`/`double` without a clear reason.

### Widening `float` to `double` Does Not Restore Lost Precision

`float f = 0.1f` stores a binary32 approximation. When cast via `(double) f`, that binary32 value is represented **exactly as a `double`**, yet the information lost relative to decimal `0.1` when assigned to `float` is not “recovered”. Therefore:

- `Float.toString(0.1f)` usually prints `0.1`.
- `Double.toString((double) 0.1f)` prints `0.10000000149011612`.
- Float bits of `0.1f` are `3DCCCCCD`.

When investigating, print the **source type, conversion point, and bit pattern**, not just the final `double` variable.

## 6. `BigDecimal`: Decimal Precision Differs from Bit Precision

`BigDecimal` holds an integer **unscaled value** and a `scale`; its numerical value is:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Here `precision()` is the **number of decimal digits in the unscaled value** (0 has precision 1), **not the 53 bits of `double`**. Example:

```java
BigDecimal number = new BigDecimal("1.2300");

System.out.println(number.precision()); // 5
System.out.println(number.scale());     // 4
```

`"1.2300"` has unscaled value `12300` and scale `4`; hence precision is `5`. Calling `stripTrailingZeros()` gives `1.23` with precision `3` and scale `2`: the numerical value stays equal while representation/scale changes.

When diagnosing unexpected `BigDecimal` results, print:

- `toString()` or `toPlainString()` to see the current written form.
- `precision()` and `scale()` to see digit count and decimal point position.
- `unscaledValue()` if you need to verify the underlying integer behind the representation.
- `MathContext` or `RoundingMode` used in the calculation: significant digits to keep and rounding rule.

A `MathContext(3, RoundingMode.HALF_EVEN)` asks for **3 significant digits**, unlike `setScale(3, ...)` which asks for **3 digits after the decimal point**. For example, `new BigDecimal("12.35").round(new MathContext(3, HALF_EVEN))` gives `12.4`. Do not loosely call both concepts “3 digits of precision” without clarifying whether you mean significant digits or decimal places.

### `BigDecimal` Constructed from `double` Inherits Binary Error

`new BigDecimal(0.1)` represents the exact **actual binary value** of `double` `0.1`, which differs from mathematical decimal `0.1`. `new BigDecimal("0.1")` represents exact decimal `0.1`. Thus:

```java
BigDecimal fromBinary = new BigDecimal(0.1);
BigDecimal fromDecimal = new BigDecimal("0.1");

System.out.println(fromBinary.equals(fromDecimal)); // false
System.out.println(BigDecimal.valueOf(0.1));        // 0.1
```

`BigDecimal.valueOf(double)` uses the decimal representation via `Double.toString` and is usually preferable to the direct `double` constructor if you already have a `double`. However, it **does not restore exact data** already lost in prior `double` calculations. When the data source is a business-meaningful decimal string, prefer constructing `BigDecimal` directly from the string.

Check this rounding example:

```java
BigDecimal precise = new BigDecimal("1.005");
System.out.println(precise.setScale(2, RoundingMode.HALF_UP));
// 1.01
```

Replacing the string with a `double` literal and calling `new BigDecimal(1.005)` can make the actual binary approximation produce a different result. Investigate the **number source and conversion point before blaming the rounding mode**.

## 7. Standalone Java 17+ Example: Printing Types, Bits, and Precision

The following exercise intentionally chooses reproducible values so outputs do not depend on thread scheduling or randomness. Save the program as **`NumericDiagnostics.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class NumericDiagnostics {
    static String kind(int x)    { return "int"; }
    static String kind(long x)   { return "long"; }
    static String kind(double x) { return "double"; }

    public static void main(String[] args) {
        byte left = 10;
        byte right = 20;
        System.out.println("byte + byte expression: " + kind(left + right));
        System.out.println("5 / 2 expression: " + kind(5 / 2));
        System.out.println("5 / 2 = " + (5 / 2));
        System.out.println("double assigned 5 / 2 = " + (double) (5 / 2));
        System.out.println("5 / 2.0 = " + (5 / 2.0));

        int a = 50_000;
        int b = 50_000;
        long wrong = a * b;
        long rightResult = (long) a * b;
        System.out.println("int multiplication assigned to long: " + wrong);
        System.out.println("cast before multiplication: " + rightResult);
        System.out.println("int overflow: " + (Integer.MAX_VALUE + 1));
        System.out.printf("minus one int bits: %08X%n", -1);
        try {
            Math.multiplyExact(a, b);
        } catch (ArithmeticException e) {
            System.out.println("multiplyExact: overflow detected");
        }

        double p = 0.1;
        double q = 0.2;
        double sum = p + q;
        System.out.println("0.1 + 0.2 = " + sum);
        System.out.printf("0.1 double bits: %016X%n",
                Double.doubleToRawLongBits(p));
        System.out.printf("0.2 double bits: %016X%n",
                Double.doubleToRawLongBits(q));
        System.out.printf("sum double bits: %016X%n",
                Double.doubleToRawLongBits(sum));
        System.out.printf("+0.0 bits: %016X%n",
                Double.doubleToRawLongBits(+0.0));
        System.out.printf("-0.0 bits: %016X%n",
                Double.doubleToRawLongBits(-0.0));
        System.out.println("+0.0 == -0.0: " + (+0.0 == -0.0));
        System.out.println("Math.ulp(1.0): " + Math.ulp(1.0));

        float f = 0.1f;
        System.out.printf("0.1f float bits: %08X%n",
                Float.floatToRawIntBits(f));
        System.out.println("0.1f promoted to double: " + (double) f);

        long exact = 9_007_199_254_740_993L;
        System.out.println("long after double roundtrip: "
                + (long) (double) exact);

        BigDecimal value = new BigDecimal("1.2300");
        System.out.println("BigDecimal 1.2300 precision/scale: "
                + value.precision() + "/" + value.scale());
        System.out.println("stripTrailingZeros precision/scale: "
                + value.stripTrailingZeros().precision() + "/"
                + value.stripTrailingZeros().scale());
        System.out.println("new BigDecimal(0.1) equals decimal 0.1: "
                + new BigDecimal(0.1).equals(new BigDecimal("0.1")));
        System.out.println("BigDecimal.valueOf(0.1): "
                + BigDecimal.valueOf(0.1).toPlainString());
        System.out.println("HALF_UP 1.005 to scale 2: "
                + new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("MathContext precision 3 for 12.35: "
                + new BigDecimal("12.35").round(
                        new MathContext(3, RoundingMode.HALF_EVEN)));
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac NumericDiagnostics.java
java NumericDiagnostics
```

Output:

```text
byte + byte expression: int
5 / 2 expression: int
5 / 2 = 2
double assigned 5 / 2 = 2.0
5 / 2.0 = 2.5
int multiplication assigned to long: -1794967296
cast before multiplication: 2500000000
int overflow: -2147483648
minus one int bits: FFFFFFFF
multiplyExact: overflow detected
0.1 + 0.2 = 0.30000000000000004
0.1 double bits: 3FB999999999999A
0.2 double bits: 3FC999999999999A
sum double bits: 3FD3333333333334
+0.0 bits: 0000000000000000
-0.0 bits: 8000000000000000
+0.0 == -0.0: true
Math.ulp(1.0): 2.220446049250313E-16
0.1f float bits: 3DCCCCCD
0.1f promoted to double: 0.10000000149011612
long after double roundtrip: 9007199254740992
BigDecimal 1.2300 precision/scale: 5/4
stripTrailingZeros precision/scale: 3/2
new BigDecimal(0.1) equals decimal 0.1: false
BigDecimal.valueOf(0.1): 0.1
HALF_UP 1.005 to scale 2: 1.01
MathContext precision 3 for 12.35: 12.4
```

Reading the output by group:

1. **Types:** `byte + byte` becomes `int`; `5 / 2` is `int`. Casting after division already truncated the remainder, yielding only `2.0`; putting `2.0` inside the expression itself yields `2.5`.
2. **Overflow:** `a*b` runs as `int` and overflows to `-1794967296` before assignment to `long`. Casting `a` before multiplication yields `2500000000`. `Math.multiplyExact` catches it instead of silently overflowing.
3. **IEEE 754:** `0.1+0.2` produces `0.30000000000000004` and a bit pattern different from the decimal `0.3` a reader expects. Sign bits of the two zeros differ even though `==` considers them equal.
4. **Precision:** `Math.ulp(1.0)` gives the step near 1; when `float 0.1f` is promoted to `double`, the decimal digits of the actual value stored in `float` become visible.
5. **BigDecimal:** `precision/scale` of `1.2300` is `5/4`; stripping trailing zeros changes it to `3/2`. Constructing from decimal strings and using the right `MathContext`/`RoundingMode` diagnoses rounding differences.

## 8. Process for Investigating an Unexpected Numeric Result

A practical checklist to go from symptom to root cause:

1. **Record the original input before any type conversion.** Is it a string, integer, JSON number, `float`, or `double`? If the source is decimal, record sign, digits, and expected scale.
2. **Write out subexpressions, each operand's type, and the operation's type.** Check integer division rules, numeric promotion, `var`, overload resolution, and literal types such as `2` vs `2.0` or `2L`.
3. **Check for overflow points before assignment.** For `int`/`long`, compare against bounds, print hex, or use `Math.addExact`/`Math.multiplyExact` when detection is required.
4. **If floating-point, print the value along with raw bits.** Use `Float.floatToRawIntBits` for `float`; `Double.doubleToRawLongBits` for `double`. Inspect NaN/infinity, signed zero, and ULP near the region of interest.
5. **If conversions occur, print values both before and after.** Watch carefully for `long → double`, `double → float`, `int` arithmetic assigned to `long`, or creating `BigDecimal` from `double`.
6. **If `BigDecimal`, print `precision`, `scale`, `unscaledValue`, `MathContext`, and `RoundingMode`.** Distinguish rounding by significant digits from rounding by decimal places.
7. **Create the smallest reproducible test case.** Prefer deterministic outputs with clear assertions/expected values. Test boundary values: max, min, negative signs, zero, rounding half-steps, and values near representable limits.
8. **Choose the fix according to the data contract**, not by changing output formatting to “look nicer”. For example, fix by casting to `long` before multiplication, using `BigDecimal(String)` for exact decimal data, or designing an appropriate tolerance if binary error is acceptable.

### Knowing When Not to Print the Entire Number

With huge `BigInteger` or `BigDecimal` values, `toString()` and especially `toPlainString()` can generate enormous strings. In real systems, cap log/output length; you can log `signum`, `bitLength`, `precision`, `scale`, and a size-checked prefix/suffix cleanly. Do not print entire untrusted payloads just for debugging. Even diagnostic operations consume resources if the input object is already huge; input-layer limits remain necessary.

## 9. Common Diagnostic Mistakes

### Merely Increasing `printf` Digits and Thinking the Error Was Fixed

`System.out.printf("%.17f", value)` can show more digits, revealing the approximated binary64 value clearly. It **does not change the bits** of `value` and does not restore lost precision. Displaying fewer digits does not fix an arithmetic bug either. To understand precisely, print raw bits or a round-trippable decimal representation.

### Thinking the Target Variable Determines Multiplication/Division Type

`long product = x*y` when `x` and `y` are `int` still multiplies as `int`. `double ratio = 5/2` still performs integer division. Put the right type **into the expression before the operation**, rather than casting after information is already lost.

### Misunderstanding Signed Zero and NaN

`+0.0 == -0.0` is true yet bits differ; `NaN == NaN` is false. Do not rely solely on `==` to inspect every floating-point property. Use `Double.isNaN`, `isFinite`, and raw bits according to your goal.

### Assuming `BigDecimal` Is Always Error-Free

`BigDecimal` can represent decimals exactly, yet if constructed from an already-approximated `double`, the object reflects the supplied value. Division may also require `MathContext` or `RoundingMode`. Storage precision does not automatically fix mistakes in **value origin and calculation policy**.

### Using `equals` to Compare All `BigDecimal`s

`BigDecimal.equals` checks both value and scale; `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` returns `false`, whereas `compareTo` returns `0` because the numerical values match. When investigating why a comparison fails, print `scale()` and distinguish value comparison contracts from representation comparison contracts.

### Using Epsilon Comparisons Without Regard to Data Range

A single absolute error threshold can be too strict for huge numbers and too loose for tiny numbers. Check ULP and problem units, handle NaN/infinity separately, and build boundary tests. Never mechanically replace all `==` checks with approximate comparisons without first establishing requirements.

## 10. Self-Check

**Question 1:** Why does `long result = 50_000 * 50_000;` give a negative value, while `long result = 50_000L * 50_000;` gives `2500000000`? Because two `int` literals make the first multiplication execute in `int` and overflow; the `L` suffix on the first operand makes the multiplication run as `long` from the start.

**Question 2:** If `double result = 7 / 2;`, what does `result` equal? **`3.0`**. To get `3.5`, use `7 / 2.0` or `(double) 7 / 2`.

**Question 3:** `0.1f` prints as `0.1`, yet casting to `double` prints `0.10000000149011612`. Did casting corrupt the number? **No**. The value was already rounded when stored in `float`; casting to `double` preserves that exact `float` value, whose decimal representation can be longer.

**Question 4:** `new BigDecimal("1.2300")` has precision 5, scale 4. After `stripTrailingZeros()`, it becomes precision 3, scale 2; does this change the numerical value? **No**, only the representation and trailing zeros after the decimal point change.

**Question 5:** A check `0.1 + 0.2 == 0.3` returns `false`. What should you inspect? Print bit patterns and actual `double` values of both sides, determine whether the discrepancy is acceptable for the problem, and apply an appropriate comparison policy; if exact decimals like currency are required, consider `BigDecimal` constructed from strings.

**Takeaway:** When a numeric result surprises you, check **expression types before the operation executes**, **bit patterns afterward**, and **precision/scale alongside the value source**. Step-by-step diagnostics distinguish integer overflow, type-conversion data loss, IEEE 754 representation error, and decimal rounding, leading to a fix at the true root cause.
