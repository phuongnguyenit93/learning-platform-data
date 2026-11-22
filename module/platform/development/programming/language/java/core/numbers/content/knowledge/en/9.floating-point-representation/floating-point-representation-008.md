# Positive Zero, Negative Zero, Infinity, and NaN in Java

In Java, `float` and `double` do not represent only ordinary finite real numbers. Under IEEE 754 binary floating-point mechanics, they also represent **two signed zeros** (`+0.0`, `-0.0`), **positive/negative infinity** (`+Infinity`, `-Infinity`), and **NaN** (*Not a Number*).

These values are not Java exceptions, nor do they necessarily trigger an error when they appear. For example:

```java
double positiveZero = 0.0;
double negativeZero = -0.0;
System.out.println(positiveZero == negativeZero); // true

System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
System.out.println(0.0 / 0.0);          // NaN
```

These three floating-point divisions **do not throw `ArithmeticException`**. If a program processes measurements, simulations, statistics, sorting, data persistence, or JSON payloads without accounting for special values, results can fail silently.

This lesson belongs to the **Floating-Point Representation** section of **Java core – numbers**, explaining the representation and operations of these values, distinguishing `==` from `Double.compare`/`Double.equals`, and providing practical data validation patterns.

## 1. Why Does a Numeric Type Have Multiple “Special Values”?

`float` (32-bit) and `double` (64-bit) use a binary floating-point format. For finite values, the representation has sign, exponent, and significand components. Certain bit combinations are reserved for **zero**, **infinity**, and **NaN**.

| Feature | `float` | `double` |
| --- | --- | --- |
| Total bits | 32 | 64 |
| Sign bit | 1 | 1 |
| Exponent bits | 8 | 11 |
| Stored significand bits | 23 | 52 |
| Significand precision with implicit bit | 24 bits | 53 bits |
| Two zero forms | `+0.0f`, `-0.0f` | `+0.0d`, `-0.0d` |
| Infinity | `Float.POSITIVE_INFINITY`, `Float.NEGATIVE_INFINITY` | `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` |
| NaN | `Float.NaN` | `Double.NaN` |

When a finite number overflows the magnitude of the floating-point format, standard operations can produce infinity. When an operation has no meaningful real-number result under IEEE 754 rules, it can produce NaN. When a result is too small, it can become a very small number, a **subnormal**, or a signed zero depending on magnitude and rounding.

Do not confuse this with Java integers: `int`/`long` **have no** `NaN`, `Infinity`, or two differently signed zeros. Integer overflow and integer division by 0 follow different rules.

## 2. Positive Zero (+0.0) and Negative Zero (-0.0)

In ordinary mathematics, 0 does not have two distinct values. In IEEE 754, `+0.0` and `-0.0` have **two distinct bit encodings**:

```text
double +0.0 = 0x0000000000000000
double -0.0 = 0x8000000000000000

float  +0.0 = 0x00000000
float  -0.0 = 0x80000000
```

The difference lies in the sign bit. Because both the significand and exponent represent zero, the two values are considered equal to 0 under the numeric comparison `==`, yet **the sign of zero can still affect subsequent operations**.

```java
double plusZero = 0.0;
double minusZero = -0.0;

System.out.println(plusZero == minusZero); // true
System.out.println(plusZero < minusZero);  // false
System.out.println(minusZero < plusZero);  // false
```

Under numeric comparison operators, `+0.0` and `-0.0` occupy the same position on the number line. Still, Java preserves the sign, allowing it to be observed via division or raw bit representation.

### 2.1. Two Divisions by Zero Yield Opposite Signs

```java
double plus = 1.0 / +0.0;  // Infinity
double minus = 1.0 / -0.0; // -Infinity
```

The sign of the result follows operand signs in floating-point division. Similarly:

```java
double negativeOverPositive = -1.0 / +0.0; // -Infinity
double negativeOverNegative = -1.0 / -0.0; // Infinity
```

Thus, a check like `value == 0.0` **cannot distinguish the sign**, even though both zeros can lead to different behavior in subsequent operations.

### 2.2. Detecting Negative Zero

An illustrative approach is reading bits via `Double.doubleToRawLongBits`:

```java
double z = -0.0;
boolean negativeZero =
        z == 0.0 && Double.doubleToRawLongBits(z) < 0;
// true because the sign bit is in the highest bit position.
```

If you also need to check `float`, use `Float.floatToRawIntBits`. Comparing `1.0 / z` against `Double.NEGATIVE_INFINITY` also distinguishes negative zero, though checking bits directly usually expresses intent more clearly when zero's sign genuinely matters.

Do not take `-0.0 == 0.0` as proof that the bit codes are identical. Do not assume converting through a text format or intermediate data pipeline always preserves zero's sign: verify library and protocol contracts.

### 2.3. Math.abs, signum, copySign, min/max

Several APIs distinguish or preserve the sign of zero:

```java
Math.abs(-0.0);            // +0.0
Math.signum(-0.0);         // -0.0
Math.copySign(1.0, -0.0);  // -1.0
Math.min(+0.0, -0.0);      // -0.0
Math.max(+0.0, -0.0);      // +0.0
```

`Math.min` and `Math.max` have special rules for signed zero: `-0.0` is treated as smaller than `+0.0` when selecting the result. This is why these methods are **not strictly equivalent** to a hand-written conditional expression using only `<` or `>` when zero's sign must be preserved.

**Note:** `Math.signum(-0.0)` prints `-0.0`, not `-1.0`; `signum` returns signed zero for zero inputs.

## 3. Positive Infinity and Negative Infinity

Java defines the constants:

```java
double positive = Double.POSITIVE_INFINITY;
double negative = Double.NEGATIVE_INFINITY;
float positiveFloat = Float.POSITIVE_INFINITY;
float negativeFloat = Float.NEGATIVE_INFINITY;
```

Infinity can arise from dividing a nonzero finite number by zero or from an operation whose result is too large to represent:

```java
double a = 1.0 / 0.0;               // Infinity
double b = -1.0 / 0.0;              // -Infinity
double c = Double.MAX_VALUE * 2.0; // Infinity
```

Infinities are not “the largest representable number.” `Double.MAX_VALUE` is the **largest positive finite number**, whereas `Double.POSITIVE_INFINITY` is a special value greater than every finite value in ordinary comparisons.

```java
Double.MAX_VALUE < Double.POSITIVE_INFINITY; // true
Double.NEGATIVE_INFINITY < -Double.MAX_VALUE; // true
```

Selected operations with infinity:

| Expression | Result | Meaning |
| --- | --- | --- |
| `1.0 / 0.0` | `Infinity` | Positive finite number divided by positive zero |
| `-1.0 / 0.0` | `-Infinity` | Negative finite number divided by positive zero |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Finite value range overflow |
| `1.0 / Double.POSITIVE_INFINITY` | `+0.0` | Result approaches positive zero |
| `-1.0 / Double.POSITIVE_INFINITY` | `-0.0` | Result approaches negative zero |
| `Double.POSITIVE_INFINITY + 10.0` | `Infinity` | Infinity plus finite number |
| `Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY` | `NaN` | Adding two opposite-signed infinities |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` | Indeterminate form under IEEE 754 arithmetic |

These expressions do not automatically throw `ArithmeticException` merely because `Infinity` or `NaN` appears.

### 3.1. Comparing with Infinity

`Infinity` compares in order with finite numbers:

```java
double x = Double.POSITIVE_INFINITY;

x > 1e300;                           // true
x == Double.POSITIVE_INFINITY;       // true
Double.NEGATIVE_INFINITY < -1e300;   // true
```

However, do not use infinity as a default “missing data” sentinel unless the API specification explicitly defines it. An aggregation, average, or normalization can inadvertently propagate infinity into final results.

## 4. NaN: Value Representing an Operation Without a Defined Real Result

`NaN` stands for *Not a Number*. It is a special floating-point value that can be produced by operations such as:

```java
double a = 0.0 / 0.0;           // NaN
double b = Math.sqrt(-1.0);     // NaN
double c = Double.POSITIVE_INFINITY
        - Double.POSITIVE_INFINITY; // NaN
double d = Double.NaN;
```

Do not think of `NaN` as merely a “syntax error” or an exception. Once NaN enters floating-point operations, the result of many subsequent arithmetic operations continues to be NaN:

```java
double unknown = Double.NaN;
double result = unknown + 100.0; // NaN
```

Thus, NaN can propagate through a data processing pipeline. If a program stores it as a valid measurement, statistics or models relying on the results can become uncontrollable.

### 4.1. Why Is NaN != NaN?

Under Java's numeric comparison rules:

```java
double x = Double.NaN;

System.out.println(x == x); // false
System.out.println(x != x); // true
System.out.println(x < 1.0);  // false
System.out.println(x > 1.0);  // false
System.out.println(x <= 1.0); // false
System.out.println(x >= 1.0); // false
```

Every ordering comparison with NaN using `<`, `>`, `<=`, `>=` returns `false`. `==` with NaN also returns `false`, even when comparing a variable with itself; `!=` returns `true`.

Therefore, `x != x` technically detects NaN, yet **you should use `Double.isNaN(x)` or `Float.isNaN(x)`** to make intent clear and avoid confusing readers.

### 4.2. NaN Breaks Range Checks

Suppose a system accepts temperatures in the range -50 to 150:

```java
static boolean badValidation(double temperature) {
    return !(temperature < -50.0 || temperature > 150.0);
}
```

With `temperature = Double.NaN`, both `<` and `>` evaluate to `false`; the negation causes the method to **return `true`** even though NaN is not a valid temperature.

Correct check when only finite values are accepted:

```java
static boolean validTemperature(double value) {
    return Double.isFinite(value)
            && value >= -50.0
            && value <= 150.0;
}
```

This check excludes `NaN`, `+Infinity`, and `-Infinity`, and only then checks the range. If the data domain permits infinity or NaN with a specific meaning, design an explicit handling branch rather than accidentally treating them as normal measurements.

## 5. APIs for Checking NaN, Infinity, and Finiteness

Java provides explicit predicate methods:

| Method | Returns `true` when? |
| --- | --- |
| `Double.isNaN(value)` | Value is NaN |
| `Double.isInfinite(value)` | Value is positive or negative infinity |
| `Double.isFinite(value)` | Value is neither NaN nor infinity |
| `Float.isNaN(value)` | `float` value is NaN |
| `Float.isInfinite(value)` | `float` value is infinity |
| `Float.isFinite(value)` | `float` value is finite |

Example:

```java
Double.isFinite(0.0);                 // true
Double.isFinite(-0.0);                // true
Double.isFinite(Double.NaN);         // false
Double.isFinite(Double.POSITIVE_INFINITY); // false

Double.isInfinite(-1.0 / 0.0);       // true
Double.isNaN(0.0 / 0.0);             // true
```

**Signed zeros are still finite values.** If an application has a specific requirement that “negative zero is disallowed,” checking `isFinite` alone is insufficient; you must detect zero's sign bit or normalize intentionally.

At data/API ingress layers, a simple and effective rule is to **check `isFinite` before computing** when input semantics represent a finite measurement.

## 6. Operator ==, Double.compare, and Double.equals Are Not the Same

This is one of the easiest traps to trigger bugs.

### 6.1. The == Operator on double

```java
+0.0 == -0.0;             // true
Double.NaN == Double.NaN; // false
```

`==` applies floating-point numeric comparison, not bit equality, and does not define a total ordering for NaN.

### 6.2. Double.compare Provides Ordering for Sorting

`Double.compare(a, b)` defines a total order handling special cases. Specifically:

- `Double.compare(-0.0, +0.0) < 0`: negative zero is ordered before positive zero.
- `Double.compare(Double.NaN, Double.NaN) == 0`: two NaN values are considered equal in this ordering.
- NaN is considered **greater than** `Double.POSITIVE_INFINITY` in `Double.compare`'s ordering, which does not mean NaN is a numeric quantity larger than infinity.

```java
Double.compare(-0.0, +0.0); // Negative value (specifically -1).
Double.compare(Double.NaN, Double.NaN); // 0
Double.compare(Double.NaN, Double.POSITIVE_INFINITY); // Positive.
```

`Float.compare` handles `float` analogously. Sorting and boxed wrapper APIs rely on this comparison to provide deterministic ordering for data containing NaN and signed zeros.

### 6.3. Double.equals Compares Contents Under Wrapper Rules

```java
Double.valueOf(-0.0).equals(Double.valueOf(+0.0)); // false
Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN)); // true
```

This can be surprising:

| Comparison | Result |
| --- | --- |
| `+0.0 == -0.0` | `true` |
| `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` | `false` |
| `Double.compare(-0.0, +0.0) < 0` | `true` |
| `Double.NaN == Double.NaN` | `false` |
| `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` | `true` |
| `Double.compare(Double.NaN, Double.NaN) == 0` | `true` |

`Double.equals` uses rules based on `Double.doubleToLongBits`: **it distinguishes signed zeros and canonicalizes NaNs for equality comparison**. Because a wrapper's `equals` and `hashCode` must remain consistent, a `HashSet<Double>` can treat `+0.0` and `-0.0` as two distinct elements, whereas `==` between the two primitives returns true.

**How to choose:** use `==` when you truly want numeric comparison; `isNaN` to detect NaN; `Double.compare` when you want deterministic sort ordering; `equals` when working under wrapper object contracts. Do not treat these comparisons as substitutes for **approximate comparison with domain error tolerances**.

## 7. Operations That Commonly Produce Special Values

| `double` Expression | Result | Common Pitfall |
| --- | --- | --- |
| `1.0 / +0.0` | `Infinity` | No exception |
| `1.0 / -0.0` | `-Infinity` | Zero's sign affects infinity's sign |
| `-1.0 / -0.0` | `Infinity` | Two negative signs cancel |
| `0.0 / 0.0` | `NaN` | Not 0 |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` | Indeterminate form |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` | Not 0 |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Floating-point overflow |
| `-1.0 / Double.POSITIVE_INFINITY` | `-0.0` | Underflow to signed zero |
| `Math.sqrt(-1.0)` | `NaN` | Input outside real domain |
| `Double.NaN + 3.0` | `NaN` | NaN propagation |

### 7.1. Comparison with Integer Division by Zero

```java
int denominator = 0;
// int q = 1 / denominator; // If run: ArithmeticException.

double floating = 1.0 / denominator; // Infinity, no exception.
```

In `double floating`, because `1.0` has type `double`, Java promotes `denominator` to `double` and performs floating-point division. Hence **a small change in operand type can alter the entire error behavior**.

### 7.2. Remainder on Floating-Point Numbers

Java supports the `%` operator for `float`/`double`, yet it does not share the exception rules of integer `%`:

```java
double r = 1.0 % 0.0; // NaN
```

While `int r = 1 % 0;` throws `ArithmeticException` if evaluated, floating-point remainder with divisor zero returns NaN. Do not mechanically apply integer `%` reasoning to floating-point `%`.

## 8. Sign of Zero During Rounding, Printing, and Casting

### 8.1. Printing and Converting to String

```java
System.out.println(+0.0); // 0.0
System.out.println(-0.0); // -0.0
System.out.println(Double.POSITIVE_INFINITY); // Infinity
System.out.println(Double.NaN); // NaN
```

This output is Java's standard string representation. It helps inspection, yet **does not prove that external exchange protocols** (such as JSON or databases) will preserve the same string or value.

### 8.2. Converting from double to int/long

When narrowing `double`/`float` to a Java integer, the fractional part is truncated according to conversion rules and special values receive special handling:

- `(int) Double.NaN` is `0`.
- `(int) Double.POSITIVE_INFINITY` is `Integer.MAX_VALUE`.
- `(int) Double.NEGATIVE_INFINITY` is `Integer.MIN_VALUE`.
- `(int) -0.0` is `0`, losing zero's sign bit.

```java
int fromNaN = (int) Double.NaN; // 0
int fromInfinity = (int) Double.POSITIVE_INFINITY; // 2147483647
int fromNegativeZero = (int) -0.0; // 0
```

These casts **do not throw errors on their own**. If application inputs must not be NaN/infinity, check `Double.isFinite` before casting; then check `int`/`long` range and explicit rounding requirements. In particular, casting NaN to 0 can hide corrupt data and make the system treat an invalid value as a valid one.

### 8.3. Negative Zero Can Appear After Very Small Results

```java
double x = -Double.MIN_VALUE;
double y = x / 2.0;
System.out.println(y); // -0.0
```

`Double.MIN_VALUE` is the **smallest nonzero positive double**, not the lowest negative number like `Integer.MIN_VALUE`. Negating it and dividing by two drops the magnitude below the smallest representable subnormal; the result rounds to negative zero.

This shows why signed zero is not merely something a programmer writes explicitly as `-0.0`; it can be produced by valid floating-point operations.

## 9. Data Transfer and Validation: Do Not Silently Accept NaN or Infinity

### 9.1. Input Data Can Contain Special Strings

Some Java methods parse special strings into `double` values:

```java
Double.parseDouble("NaN");       // NaN
Double.parseDouble("Infinity");  // Infinity
Double.parseDouble("-Infinity"); // -Infinity
```

If an input API expects a “finite number,” calling `Double.parseDouble` alone is not enough. After parsing, verify `Double.isFinite` and domain constraints.

Example:

```java
static double parseFinite(String text) {
    double value = Double.parseDouble(text);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Finite number required");
    }
    return value;
}
```

This method can still accept `-0.0`, because it is a finite value. If the application needs to forbid or normalize negative zero, handle that as an **additional policy**. Furthermore, `parseDouble` can throw `NumberFormatException` when the string does not match accepted numeric syntax.

### 9.2. Standard JSON and APIs

In standard JSON, bare tokens `NaN`, `Infinity`, and `-Infinity` **are not valid number literals**. How different Java libraries react when serializing special values can vary: rejecting, replacing with `null`, encoding as strings, or using a non-standard JSON extension. **Do not assume** they transmit safely as valid numbers.

If NaN/infinity is a domain state that must be preserved, design an explicit schema, such as a `status` field alongside an optional value, instead of sneaking special strings into a numeric field. If only finite measurements are accepted, validate before serializing.

### 9.3. BigDecimal Does Not Support NaN and Infinity

`BigDecimal` represents finite decimal numbers; it has no equivalent NaN/infinity values:

```java
// BigDecimal.valueOf(Double.NaN) or
// BigDecimal.valueOf(Double.POSITIVE_INFINITY)
// throws NumberFormatException.
```

Do not convert `double` data to `BigDecimal` expecting all special values to survive; validate finiteness first. When money or exact decimals are required, prefer creating `BigDecimal` from **original decimal strings** and applying business validation/rounding.

## 10. When Should Zero's Sign Be Preserved or Stripped?

It depends on the application:

- For measurements, simulations, and IEEE 754 algorithms, zero's sign can convey the **direction of approach to 0** or the sign of a tiny result. Arbitrarily normalizing `-0.0` to `+0.0` can alter subsequent division results.
- For user interfaces or reports, `-0.0` can confuse users when it is merely the rounded result of a negative value very close to 0. You can choose to display `0.0`, while separating **display formatting** from raw underlying data.
- For data keys and object equality, `Double.equals` distinguishes `-0.0`/`+0.0`, so a `Set<Double>` or hash key can treat them as distinct. If the business logic intends them to share one key, normalize explicitly **before creating the key**.
- For statistics, establish an explicit policy for NaN: drop samples, mark missing data, or abort processing. Do not assume sums/averages automatically ignore NaN.

Example zero-normalization helper when and only when the domain contract permits losing the sign:

```java
static double normalizeZero(double value) {
    return value == 0.0 ? 0.0 : value;
}
```

The method leaves NaN and infinity untouched; if the goal also includes excluding them, combine with `Double.isFinite`. It intentionally turns `-0.0` into `+0.0`. **Do not apply by default** to numerical algorithms that must preserve sign direction.

## 11. Standalone Runnable Java 17+ Program

Save the file as **`FloatingSpecialValuesDemo.java`**. The program uses `println` instead of locale-dependent formatting, and cleanly separates signed zero, infinity, NaN, wrapper comparison, validation, casting, and underflow to negative zero.

```java
public class FloatingSpecialValuesDemo {
    static boolean validTemperature(double value) {
        return Double.isFinite(value)
                && value >= -50.0
                && value <= 150.0;
    }

    public static void main(String[] args) {
        double positiveZero = 0.0;
        double negativeZero = -0.0;

        System.out.println("zero-equal=" + (positiveZero == negativeZero));
        System.out.println("positive-zero-bits=" +
                Long.toHexString(Double.doubleToRawLongBits(positiveZero)));
        System.out.println("negative-zero-bits=" +
                Long.toHexString(Double.doubleToRawLongBits(negativeZero)));
        System.out.println("positive-reciprocal=" + (1.0 / positiveZero));
        System.out.println("negative-reciprocal=" + (1.0 / negativeZero));
        System.out.println("min-zero=" + Math.min(positiveZero, negativeZero));
        System.out.println("max-zero=" + Math.max(positiveZero, negativeZero));
        System.out.println("signum-negative-zero=" + Math.signum(negativeZero));

        double infinity = 1.0 / positiveZero;
        double nan = 0.0 / 0.0;
        System.out.println("infinity=" + infinity);
        System.out.println("opposite-infinities=" +
                (infinity + Double.NEGATIVE_INFINITY));
        System.out.println("zero-over-zero=" + nan);
        System.out.println("nan-equal-self=" + (nan == nan));
        System.out.println("nan-is-nan=" + Double.isNaN(nan));
        System.out.println("infinity-is-finite=" + Double.isFinite(infinity));
        System.out.println("negative-zero-is-finite=" +
                Double.isFinite(negativeZero));

        System.out.println("compare-zero=" +
                Double.compare(negativeZero, positiveZero));
        System.out.println("boxed-zero-equal=" +
                Double.valueOf(negativeZero).equals(Double.valueOf(positiveZero)));
        System.out.println("boxed-nan-equal=" +
                Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));

        System.out.println("nan-temperature-valid=" + validTemperature(nan));
        System.out.println("normal-temperature-valid=" +
                validTemperature(25.0));
        System.out.println("cast-nan=" + (int) nan);
        System.out.println("cast-infinity=" + (int) infinity);

        double tinyNegative = -Double.MIN_VALUE;
        System.out.println("tiny-negative-half=" + (tinyNegative / 2.0));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac FloatingSpecialValuesDemo.java
java FloatingSpecialValuesDemo
```

Expected stdout:

```text
zero-equal=true
positive-zero-bits=0
negative-zero-bits=8000000000000000
positive-reciprocal=Infinity
negative-reciprocal=-Infinity
min-zero=-0.0
max-zero=0.0
signum-negative-zero=-0.0
infinity=Infinity
opposite-infinities=NaN
zero-over-zero=NaN
nan-equal-self=false
nan-is-nan=true
infinity-is-finite=false
negative-zero-is-finite=true
compare-zero=-1
boxed-zero-equal=false
boxed-nan-equal=true
nan-temperature-valid=false
normal-temperature-valid=true
cast-nan=0
cast-infinity=2147483647
tiny-negative-half=-0.0
```

Reading the output by group:

1. **The two zeros compare equal via `==` yet have different bits.** Dividing by them yields opposite-signed infinities; `Math.min` and `Math.max` preserve signed-zero selection rules.
2. **Infinity and NaN are not exceptions.** Adding opposite-signed infinities yields NaN; NaN does not equal itself under `==`.
3. **Changing the comparison API changes semantics.** `Double.compare(-0.0,+0.0)` is negative; boxed `Double.equals` distinguishes the two zeros yet treats two NaNs as equal.
4. **Data validation must be explicit.** `Double.isFinite` rejects NaN/infinity, whereas casting NaN to `int` returns 0 and can conceal invalid data.
5. **Very small negative numbers can become negative zero.** The last line is not a literal negative zero written directly, but the result of underflow.

## 12. Testing and Common Pitfalls

| False Assumption | Why Is It Dangerous? | How to Check / Prevent |
| --- | --- | --- |
| “Zero has only one representation.” | `+0.0` and `-0.0` have different bits and produce opposite-signed divisions | Use raw bits, `Double.compare`, or an explicit normalization policy when needed |
| “`x == 0.0` detects negative zero.” | Both `+0.0` and `-0.0` equal 0.0 | Use `Double.doubleToRawLongBits` if zero's sign matters |
| “Floating-point division by 0 throws ArithmeticException.” | It can produce infinity or NaN | Validate finite inputs and outputs |
| “NaN can be checked with `x == Double.NaN`.” | `NaN == NaN` is always false | Use `Double.isNaN(x)` |
| “If `x` is neither less than nor greater than bounds, x is valid.” | Ordering comparisons with NaN are all false | Check `Double.isFinite` and range conditions |
| “`Double.equals` is like `==`.” | `equals` distinguishes signed zeros yet treats NaNs as equal | Choose the API matching your intended semantics |
| “Infinity is just a very large finite number.” | Infinity is a special value | `Double.isInfinite` and `Double.isFinite` |
| “`Double.MAX_VALUE` is infinity.” | It is the largest positive finite number | Use `Double.POSITIVE_INFINITY` when infinity is truly meant |
| “Casting NaN to int must throw an error.” | The cast produces 0 | Check finiteness and range before casting |
| “Any JSON supports NaN/Infinity as numbers.” | Standard JSON forbids those literals | Design schema/serializer with validation |
| “`Double.MIN_VALUE` is the smallest negative number.” | It is the smallest nonzero positive number | Distinguish from `-Double.MAX_VALUE` or `Double.NEGATIVE_INFINITY` |
| “All signed zeros can be merged freely.” | Some arithmetic operations rely on preserving zero's sign | Normalize only when the business domain permits |

Test suites should include `+0.0`, `-0.0`, `Double.MIN_VALUE`, `-Double.MIN_VALUE`, `Double.MAX_VALUE`, both infinities, NaN, and positive/negative finite values. When testing comparison APIs, verify all three of `==`, `Double.compare`, and `Double.equals`, as their results differ on signed zero and NaN.

## 13. Applied Exercises

**Exercise 1 – Predict Results.** Without running Java, evaluate `1.0 / +0.0`, `1.0 / -0.0`, `0.0 / 0.0`, `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY`. Which throws an exception, and which returns a special value?

**Exercise 2 – Comparisons.** Given `a = +0.0`, `b = -0.0`, `c = Double.NaN`, build a table for `a == b`, `Double.compare(a,b)`, `Double.valueOf(a).equals(Double.valueOf(b))`, `c == c`, `Double.isNaN(c)`. Explain the purpose of each.

**Exercise 3 – Validation.** Write a method accepting a temperature string and allowing only finite values in `[-50,150]`. Test `"25.5"`, `"NaN"`, `"Infinity"`, `"-Infinity"`, `"abc"`, `"-0.0"`. Specify the parser's exception rules and explicit policy for negative zero.

**Exercise 4 – Buckets and Keys.** An application uses `HashSet<Double>` to deduplicate measurement results. Predict how many elements exist after adding `+0.0`, `-0.0`, `Double.NaN` twice. Why does `HashSet` not apply primitive `==` directly?

**Exercise 5 – Computation Pipeline.** Analyze an input causing an operation to return infinity and subsequently produce NaN in the next step. Design detection and error reporting so users never see NaN presented as a valid result.

**Exercise 6 – Underflow.** Compute `-Double.MIN_VALUE / 2.0`. Why does the printed result show `-0.0` rather than a nonzero negative number? What value will `1.0 / result` have?

**Exercise 7 – JSON.** Propose an API response structure allowing either a finite measurement or an uncomputable state while remaining valid standard JSON. Why is encoding bare number `NaN` not a safe contract?

## 14. Checklist for Safe Floating-Point Usage

- Understand that `float`/`double` have **two signed zeros, two infinities, and NaN**, unlike integer types.
- If the data domain requires finite numbers, check **`Float.isFinite`/`Double.isFinite`** before critical calculations, before casting, and before serializing.
- Use **`isNaN`** to detect NaN; never use `== Double.NaN`.
- Distinguish `==`, `Double.compare`, and `Double.equals` regarding signed zero and NaN.
- Do not assume every division by 0 throws an exception; it depends on **operand types**.
- Do not abuse `double → int/long` casts as validation: NaN can turn into 0, and infinity clamps to boundaries.
- If zero's sign must be preserved, do not normalize automatically; if both zeros must merge in data keys, normalize intentionally.
- Check serializers/APIs because **standard JSON forbids NaN and Infinity as numbers**.
- For money and exact decimals, choose business-appropriate types and rounding policies rather than treating NaN/infinity like ordinary `BigDecimal` values.

**Conclusion:** `+0.0`, `-0.0`, infinity, and NaN are **values with well-defined behavior** in Java floating-point arithmetic, not all exceptions. Correctness depends on understanding evaluation rules, choosing appropriate comparisons, and explicitly validating what values are allowed through the system.