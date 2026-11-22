# BigDecimal Has No NaN or Infinity in Java

`BigDecimal` and `double` both represent numbers, yet they **do not share the same value set**. The IEEE 754 binary floating-point types `double`/`float` support three kinds of special values: **NaN** (*Not a Number*), **positive infinity** (`+Infinity`), and **negative infinity** (`-Infinity`). `java.math.BigDecimal` **has none of those three values**; it uses an unscaled integer and a scale to represent **finite decimal values**, with practical magnitude range limited by resources and the `int` type of scale.

Important consequences:

- You cannot construct a `BigDecimal` "containing NaN" or "containing Infinity" via constructors or `valueOf(double)`.
- `BigDecimal` operations do not use infinity to represent division by zero; they **throw `ArithmeticException`**.
- Very large/small `BigDecimal` values remain finite in the decimal model, yet calling `doubleValue()` can convert them to `Infinity` or `0.0` due to binary64 limits.
- When an API using `double` hands data to a `BigDecimal` layer, you must **validate finite numbers before converting** and choose an explicit error policy.

This Knowledge article belongs to the **BigDecimal Model** group of Java Core, presenting mechanisms and Java 17+ examples verifying each boundary.

## 1. Value Set: BigDecimal vs. double

A `BigDecimal` object is described by an `unscaledValue`, `scale` pair, with the formula:

~~~text
value = unscaledValue × 10^(-scale)
~~~

Here `unscaledValue` is a `BigInteger` and `scale` is an `int`. For a valid and constructible pair, the result is a finite decimal number; **there is no special code to represent NaN or infinity**.

| Property | `double` / `float` | `BigDecimal` |
| --- | --- | --- |
| Representation | IEEE 754 binary64/binary32 | Decimal via unscaled integer and scale |
| NaN | Yes | **No** |
| `+Infinity`, `-Infinity` | Yes | **No** |
| Signed zero `+0.0`/`-0.0` | Sign distinguishable in bit representation | **Does not retain a separate negative zero** |
| Very large finite numbers | Has binary exponent and precision limits | No binary64-style exponent limit; still subject to `int` scale and memory limits |
| `1.0 / 0.0` | `Infinity` | `divide(BigDecimal.ZERO)` throws `ArithmeticException` |
| `0.0 / 0.0` | `NaN` | `BigDecimal.ZERO.divide(BigDecimal.ZERO)` throws `ArithmeticException` |
| Exact 1/3 in finite decimal | Not represented exactly | `divide` without rounding throws error; can approximate with policy |
| Result data type | Primitive `double` or `float` | Immutable `BigDecimal` object |

One cannot infer that "BigDecimal is more accurate" means it supports every IEEE 754 state. **Precision and value set are two different concerns.** `BigDecimal` generally fits money and fixed decimals; `double` fits many measurements and numerical computations requiring wide exponent ranges alongside special values.

## 2. How Can NaN and Infinity Appear in double?

In Java, floating-point expressions can produce non-finite values:

~~~java
double nan = 0.0 / 0.0;         // NaN
double positive = 1.0 / 0.0;    // Infinity
double negative = -1.0 / 0.0;   // -Infinity

System.out.println(Double.isNaN(nan));       // true
System.out.println(Double.isInfinite(positive)); // true
System.out.println(Double.isFinite(negative));   // false
~~~

NaN can also arise from `Math.sqrt(-1.0)` or `Infinity - Infinity`. Infinity can arise when a `double` calculation overflows. These are valid results per floating-point semantics, **not necessarily Java exceptions thrown**.

Three utilities to remember:

- `Double.isNaN(x)`: detects NaN, instead of `x == Double.NaN` (which is always false for NaN).
- `Double.isInfinite(x)`: detects positive or negative infinity.
- `Double.isFinite(x)`: true if and only if neither NaN nor infinite.

Corresponding APIs exist on `Float`. `Double.isFinite(-0.0)` is still true: 0, even with a negative sign in binary64, is a **finite** value.

Do not use `x != x` instead of `isNaN` in business code when a direct API exists; that style is harder to read and makes it easy for maintainers to miss validation intent.

## 3. Creating BigDecimal from NaN or Infinity Fails

Object creation methods cannot turn a non-finite state into a `BigDecimal` value:

~~~java
// Each of the following calls throws NumberFormatException:
new BigDecimal(Double.NaN);
new BigDecimal(Double.POSITIVE_INFINITY);
BigDecimal.valueOf(Double.NaN);
BigDecimal.valueOf(Double.NEGATIVE_INFINITY);
new BigDecimal("NaN");
new BigDecimal("Infinity");
~~~

**`NumberFormatException`** in these cases indicates that the input cannot be a valid `BigDecimal` representation. The `BigDecimal(double)` constructor rejects NaN/Infinity; `BigDecimal.valueOf(double)` uses `Double.toString(double)`, yet string forms `"NaN"` or `"Infinity"` are also rejected by `BigDecimal`'s string constructor.

Important distinction:

~~~java
Double.parseDouble("NaN");         // Double.NaN
Double.parseDouble("Infinity");    // Double.POSITIVE_INFINITY

// new BigDecimal("NaN");      // NumberFormatException
// new BigDecimal("Infinity"); // NumberFormatException
~~~

**The same text is not necessarily accepted by both parsers.** `Double.parseDouble` serves `double` with special values; `BigDecimal(String)` requires valid finite decimal number syntax. Do not attempt to parse special strings into decimal and assume an exception means a value of zero.

Nor is `BigDecimal.valueOf(Double.MAX_VALUE)` infinite. `Double.MAX_VALUE` is still a **finite** value (though very large) and can be converted to `BigDecimal`. An exception occurs only when **the input double value is already NaN or ±Infinity** or cannot be converted under other API limits.

## 4. Division by Zero: ArithmeticException Instead of Infinity or NaN

Compare division on the same mathematical expressions:

~~~java
double infinity = 1.0 / 0.0; // Infinity
double undefined = 0.0 / 0.0; // NaN

// BigDecimal.ONE.divide(BigDecimal.ZERO);  // ArithmeticException
// BigDecimal.ZERO.divide(BigDecimal.ZERO); // ArithmeticException
~~~

`BigDecimal` has no infinity/NaN element in its value set, so there is no valid object to represent those results. For division by zero, the behavior is to **throw an exception**.

For `BigDecimal.ZERO.divide(BigDecimal.ZERO)`, the exception message may differ from `BigDecimal.ONE.divide(BigDecimal.ZERO)`; do not rely on `getMessage()` as a stable business error code. Catch by **exception type** or — better yet — check the precondition `divisor.signum() == 0` before computing if an understandable message is needed.

Example denominator-checking method:

~~~java
static BigDecimal safeDivide(
        BigDecimal numerator,
        BigDecimal denominator,
        int scale,
        RoundingMode mode) {
    if (denominator.signum() == 0) {
        throw new IllegalArgumentException("denominator must be nonzero");
    }
    return numerator.divide(denominator, scale, mode);
}
~~~

This is an **illustrative method inside a class**; the caller must check for null or define an appropriate null policy. Passing `denominator = null` to `denominator.signum()` will still throw `NullPointerException`; validation cannot automatically replace a null contract.

**Another error of the same exception class:** division **without a finite decimal expansion** can also throw `ArithmeticException` when no rounding is specified. For example, `BigDecimal.ONE.divide(new BigDecimal("3"))` has no finite decimal solution; it throws an error even though the denominator is non-zero.

~~~java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        5,
        RoundingMode.HALF_UP);
// third = 0.33333
~~~

Specifying an appropriate scale and rounding mode handles **infinitely repeating decimal division results**, and does **not** make division by zero valid.

## 5. A Huge BigDecimal Is Still Finite — Yet double Can Be Infinity

A `BigDecimal` can represent `10^400` via:

~~~java
BigDecimal huge = new BigDecimal("1E+400");
System.out.println(huge); // 1E+400
~~~

It has a finite unscaled value and a negative scale, so it is a valid decimal number. However, `double` only has a finite exponent range. When converting:

~~~java
double narrowed = huge.doubleValue();
System.out.println(narrowed);                 // Infinity
System.out.println(Double.isFinite(narrowed)); // false
~~~

**There is no contradiction** with the article's title: the `BigDecimal` object still holds the finite value `1E+400`; only the **result of converting to `double`** is Infinity because it exceeds the finite range of binary64.

Conversely, a tiny decimal can also lose information when converted to binary64:

~~~java
BigDecimal tiny = new BigDecimal("1E-400");
double narrowed = tiny.doubleValue();
System.out.println(narrowed); // 0.0
~~~

Here `tiny` is mathematically non-zero, yet after narrowing to `double` it underflows to 0.0. A **finite** `double` result (such as 0.0) does not necessarily preserve the input decimal value.

`BigDecimal.floatValue()` carries the same risk, with an even narrower finite range. When a contract requires preserving exact decimal values, **keep computing with BigDecimal** and output in an appropriate decimal form instead of narrowing to `float`/`double`.

There is no `doubleValueExact()` like `intValueExact()` for integers. If you need to verify a decimal→double conversion, you must set appropriate criteria for range, allowable precision loss, and non-finite states.

## 6. Do Not Equate "Finite Value" with "Exact Value After Passing Through double"

Three independent situations must be distinguished:

1. **Finite `double` yet approximating the expected decimal value**, e.g., literal `0.1` is a binary64 representation near 1/10.
2. **Finite `BigDecimal` and exact per decimal string**, e.g., `new BigDecimal("0.1")` holds exact 1/10.
3. **Finite `BigDecimal` yet converting to `double` overflows/underflows/rounds**, e.g., `1E+400` becomes Infinity or `1E-400` becomes 0.0.

~~~java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal binaryExact = new BigDecimal(0.1);
BigDecimal canonical = BigDecimal.valueOf(0.1);
~~~

`exact` is exact decimal 0.1; `binaryExact` keeps the exact binary64 value of `double 0.1`, hence a long tail; `canonical` relies on the round-trip string form of `Double.toString(0.1)`, generally a sensible choice when data unavoidably arrives as a finite `double`. None of those approaches "upgrades" NaN or Infinity into a valid `BigDecimal`.

**Watch the data source:** if an input string is `"1E+400"`, `new BigDecimal("1E+400")` represents the large finite number directly. If parsed into `double` first, `Double.parseDouble("1E+400")` may return Infinity, and you have lost the chance to forward that exact decimal value through a `double` pipeline.

## 7. Designing Safe API Boundaries

When a `double` input is permitted to convert to `BigDecimal` **only when finite**, validate at the boundary:

~~~java
static BigDecimal requireFinite(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("value must be finite");
    }
    return BigDecimal.valueOf(value);
}
~~~

The method above indeed creates a decimal when the `double` value is finite. It **does not guarantee** the created decimal equals the human-intended decimal value prior to `double` calculations; nor does it guarantee an error-free decimal. It only prevents NaN/infinity from being passed into a constructor that does not support them.

When input comes from a string, you can construct `new BigDecimal(text)` directly, after validating null, syntax, length, scale, digit count, and business range. String parsing can throw `NumberFormatException` for many reasons, not just NaN/infinity.

When a decimal result is about to go to an API taking `double`, consider both steps:

~~~java
BigDecimal amount = new BigDecimal("1E+400");
double output = amount.doubleValue();
if (!Double.isFinite(output)) {
    throw new IllegalArgumentException("result cannot fit in finite double");
}
~~~

This check detects overflow to Infinity, yet **is insufficient** to rule out finite conversions that lose precision or underflow to 0.0. If an *exact round-trip* is required, maintain an explicit contract on value and representation; for example, convert back and compare per data domain, keeping scale semantics and special values in mind.

If the receiving layer still needs to represent NaN or infinity as a business state, **do not use BigDecimal as a "container" for those states**. Create a result type that distinguishes *finite value*, *missing data*, *undefined*, or *out of range*.

## 8. Compilable and Runnable Java 17+ Program

Create file `DecimalFiniteDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalFiniteDemo {
    static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " = OK");
        } catch (RuntimeException ex) {
            System.out.println(label + " = "
                    + ex.getClass().getSimpleName());
        }
    }

    static BigDecimal requireFinite(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("value must be finite");
        }
        return BigDecimal.valueOf(value);
    }

    public static void main(String[] args) {
        System.out.println("Double NaN detected = "
                + Double.isNaN(Double.NaN));
        System.out.println("Double +Infinity detected = "
                + Double.isInfinite(Double.POSITIVE_INFINITY));
        System.out.println("Double -Infinity finite = "
                + Double.isFinite(Double.NEGATIVE_INFINITY));
        System.out.println("finite decimal = "
                + new BigDecimal("12.50"));

        attempt("NaN double constructor",
                () -> new BigDecimal(Double.NaN));
        attempt("+Infinity double constructor",
                () -> new BigDecimal(Double.POSITIVE_INFINITY));
        attempt("NaN valueOf",
                () -> BigDecimal.valueOf(Double.NaN));
        attempt("-Infinity valueOf",
                () -> BigDecimal.valueOf(Double.NEGATIVE_INFINITY));
        attempt("NaN string", () -> new BigDecimal("NaN"));
        attempt("Infinity string", () -> new BigDecimal("Infinity"));

        System.out.println("double 1/0 = " + (1.0 / 0.0));
        System.out.println("double 0/0 is NaN = "
                + Double.isNaN(0.0 / 0.0));
        attempt("decimal 1/0",
                () -> BigDecimal.ONE.divide(BigDecimal.ZERO));
        attempt("decimal 0/0",
                () -> BigDecimal.ZERO.divide(BigDecimal.ZERO));
        attempt("decimal 1/3 exact",
                () -> BigDecimal.ONE.divide(BigDecimal.valueOf(3)));
        System.out.println("decimal 1/3 rounded = "
                + BigDecimal.ONE.divide(
                        BigDecimal.valueOf(3),
                        5, RoundingMode.HALF_UP));

        BigDecimal huge = new BigDecimal("1E+400");
        BigDecimal tiny = new BigDecimal("1E-400");
        System.out.println("huge BigDecimal = " + huge);
        System.out.println("huge to double = " + huge.doubleValue());
        System.out.println("huge to double is finite = "
                + Double.isFinite(huge.doubleValue()));
        System.out.println("tiny BigDecimal = " + tiny);
        System.out.println("tiny to double = " + tiny.doubleValue());
        System.out.println("tiny to double is finite = "
                + Double.isFinite(tiny.doubleValue()));

        System.out.println("negative zero decimal = "
                + new BigDecimal("-0.00"));
        System.out.println("negative zero decimal scale = "
                + new BigDecimal("-0.00").scale());
        System.out.println("finite guard 2.5 = " + requireFinite(2.5));
        attempt("finite guard Infinity",
                () -> requireFinite(Double.POSITIVE_INFINITY));
    }
}
~~~

Run on Java 17 or higher:

~~~bash
javac DecimalFiniteDemo.java
java DecimalFiniteDemo
~~~

Exact stdout:

~~~text
Double NaN detected = true
Double +Infinity detected = true
Double -Infinity finite = false
finite decimal = 12.50
NaN double constructor = NumberFormatException
+Infinity double constructor = NumberFormatException
NaN valueOf = NumberFormatException
-Infinity valueOf = NumberFormatException
NaN string = NumberFormatException
Infinity string = NumberFormatException
double 1/0 = Infinity
double 0/0 is NaN = true
decimal 1/0 = ArithmeticException
decimal 0/0 = ArithmeticException
decimal 1/3 exact = ArithmeticException
decimal 1/3 rounded = 0.33333
huge BigDecimal = 1E+400
huge to double = Infinity
huge to double is finite = false
tiny BigDecimal = 1E-400
tiny to double = 0.0
tiny to double is finite = true
negative zero decimal = 0.00
negative zero decimal scale = 2
finite guard 2.5 = 2.5
finite guard Infinity = IllegalArgumentException
~~~

Reading the output by mechanism:

- Constructors/factories from NaN and Infinity throw **`NumberFormatException`**, because there is no corresponding `BigDecimal` value.
- `BigDecimal` divisions not allowed under finite decimal semantics throw **`ArithmeticException`**; a `1/3` division with a specific scale and rounding can produce an approximate finite decimal number.
- `huge` and `tiny` are **two valid, finite BigDecimals**; the issue only appears when calling `doubleValue()`. The sub-zero-magnitude yet tiny case turns into 0.0 while `Double.isFinite` stays true, showing that **a finite check is not an exactness check**.
- `new BigDecimal("-0.00")` keeps a two-digit scale yet prints `0.00`; there is no separate negative-zero code per IEEE 754.
- `requireFinite` intercepts Infinity **before** calling `BigDecimal.valueOf`; in the example it reports an application-defined `IllegalArgumentException`, not a default parser error.

The `attempt` method catches `RuntimeException` **solely to demonstrate exception types in a controlled way**. In real applications, do not use overly broad catches to swallow errors or default to returning 0; catch purposefully at communication boundaries, state the error source clearly, and preserve appropriate context.

## 9. Distinguishing NumberFormatException, ArithmeticException, and Validation Errors

| Situation | Result/Error type | Suggested handling |
| --- | --- | --- |
| `new BigDecimal(Double.NaN)` | `NumberFormatException` | Reject non-finite input |
| `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` | `NumberFormatException` | Check `Double.isFinite` beforehand |
| `new BigDecimal("NaN")` or `"Infinity"` | `NumberFormatException` | Report invalid syntax for decimal |
| `BigDecimal.ONE.divide(BigDecimal.ZERO)` | `ArithmeticException` | Check non-zero denominator |
| `BigDecimal.ZERO.divide(BigDecimal.ZERO)` | `ArithmeticException` | Handle indeterminate operation |
| `BigDecimal.ONE.divide(new BigDecimal("3"))` | `ArithmeticException` | Use overload with rounding if business permits |
| `new BigDecimal("1E+400").doubleValue()` | `Infinity` as `double` | Check overflow and design output data |
| `new BigDecimal("1E-400").doubleValue()` | `0.0` as `double` | Check precision loss/underflow if important |
| `requireFinite(Double.NaN)` in example | `IllegalArgumentException` | Application-defined validation error |

**Key point:** `NumberFormatException` says the input **cannot create a valid BigDecimal**; `ArithmeticException` says the **requested decimal operation cannot be performed under the current contract**. Do not write `catch (NumberFormatException)` expecting to catch division by zero as well. Conversely, do not equate every `ArithmeticException` with division by zero: infinite decimal division without rounding can throw the same exception type.

Do not rely on `getMessage()` text as a stable classification code. When needing to identify the "division by 0" business condition, check `denominator.signum() == 0` before division and translate into a clear error.

## 10. Missing Data, NaN, and Invalid States Should Be Modeled Separately

`null`, `NaN`, infinity, and 0 carry **different meanings**. Do not use a sentinel decimal like `0` or `-1` to simultaneously represent all these states if they could be valid business values.

An API returning calculation results can use a discriminated result type:

~~~java
sealed interface AmountResult
        permits AmountResult.Finite,
                AmountResult.Missing,
                AmountResult.Invalid {
    record Finite(BigDecimal value) implements AmountResult {}
    record Missing() implements AmountResult {}
    record Invalid(String reason) implements AmountResult {}
}
~~~

This is an **illustrative declaration snippet** that must be placed in a valid file and class/package context of a Java 17+ application, not a standalone program with `main`. When used in a system, place `BigDecimal` into `Finite` **only after validation**, require a non-null object (e.g., check `Objects.requireNonNull` in the constructor), and optionally add overflow/undefined states if needed.

You may choose `Optional<BigDecimal>` if only "is there a finite value or not" is needed, yet `Optional.empty()` **does not tell the reason**. For applications needing diagnostics on invalid data, a result type carrying error information is usually better.

For APIs accepting `double`, the usual choice is to **reject all non-finite values** (fail fast) before decimal calculation. If a scientific problem needs NaN/Infinity propagation per IEEE 754, you may need to keep the pipeline in `double` or build an explicit state model — `BigDecimal` does not natively provide NaN propagation.

## 11. Storing and Exchanging Data Between JSON, CSV, Database, and BigDecimal

When connecting systems, define the **representation contract**:

- If a field is a valid decimal number, read it directly as a decimal string or exact decimal type into `BigDecimal`; do not coerce through `double` if precision/scale must be preserved.
- If source data can be NaN/Infinity, normalize it to a **separate state** or report an error per contract, without pretending it is a `BigDecimal`.
- Standard JSON number syntax does not include NaN or Infinity tokens as numbers; if a provider sends strings `"NaN"` or `"Infinity"`, those strings are still not valid decimals and need a separate policy. A library may support non-standard extensions, but do not assume every parser behaves that way.
- In CSV, blank values, `"NaN"`, and `"0"` must be handled according to data rules — they are not automatically equivalent.
- When querying databases, distinguish `NULL` from a decimal 0; the behavior of special numeric types depends on the DBMS and column type, and should not be inferred from Java.

`BigDecimal.toString()` output format may use scientific notation for very large/small numbers; `toPlainString()` avoids scientific notation yet can produce an extremely long string for large scales. When storing decimal numeric data, limit size/scale per business rules to control resources.

## 12. Common Mistakes to Avoid

1. **"BigDecimal is more precise than double, so it must have a more precise Infinity."** False: `BigDecimal` does not represent Infinity/NaN.
2. **"BigDecimal divided by zero produces Infinity."** False: it throws `ArithmeticException`.
3. **"0/0 equals 0 because BigDecimal has no NaN."** False: division by zero is invalid and does not silently turn into 0.
4. **"BigDecimal.valueOf(NaN) returns null."** False: it throws `NumberFormatException`.
5. **"new BigDecimal("NaN") gives a special decimal number."** False: the string is invalid for the decimal parser.
6. **"Every `BigDecimal` division throwing ArithmeticException is due to a zero denominator."** False: non-terminating decimal expansions without rounding can also throw it.
7. **"Setting a rounding mode allows division by zero."** False: rounding only handles precision of valid division, and does not produce a value for a zero denominator.
8. **"If BigDecimal is finite, doubleValue is also finite."** False: large decimals can overflow to Infinity.
9. **"A finite doubleValue means no information was lost."** False: it can round or underflow to 0.0.
10. **"A `Double.isFinite` true result proves the original decimal was preserved."** False: a non-zero decimal can turn into 0.0 and remain finite.
11. **"Very large decimal number strings must go through double first."** False: parsing directly to `BigDecimal` can preserve the decimal data.
12. **"BigDecimal keeps `-0.0` like double."** False: BigDecimal has no separate negative zero code; it can still keep the scale of `"-0.00"`.
13. **"NaN is synonymous with null/missing value."** False: the states carry different meanings; do not merge them arbitrarily.
14. **"Catching every exception and returning BigDecimal.ZERO is safe."** False: it hides error signals and can cause incorrect financial results.
15. **"No need to validate input limits because BigDecimal has arbitrary precision."** False: unscaled integer, scale, string construction, and operations still have resource and specification limits.
16. **"BigDecimal can be used to fully emulate IEEE 754 decimal floating point."** False: IEEE 754 decimal has additional special value classes and format/exponent constraints unlike the BigDecimal model.

## 13. Safe Integration Checklist

1. Determine whether the input field is an **exact decimal** or a `double` that may contain NaN/Infinity.
2. If the source is `double`, check `Double.isFinite` before converting; choose a policy when NaN/infinity appears.
3. If the source is a string, parse directly to `BigDecimal` after checking syntax and input limits; catch `NumberFormatException` at the boundary.
4. If computing decimal division, verify a non-zero denominator; choose `scale`, `precision`, and `RoundingMode` if the result cannot be represented exactly.
5. Do not assume every `ArithmeticException` means division by 0.
6. Before outputting `BigDecimal` as `double`/`float`, assess risks of overflow, underflow, and precision loss.
7. Distinguish null, malformed data, 0, NaN, and infinity per the API contract; do not use an ambiguous sentinel.
8. For money and critical figures, keep calculations in `BigDecimal` up to the appropriate output layer; do not pass through binary64 unnecessarily.
9. Design boundary tests for `NaN`, `±Infinity`, 0, zero denominator, `1/3`, very large decimals, and very small decimals.
10. When reporting errors to users, use clear business messages and avoid logging sensitive data unnecessarily.

## 14. Self-Practice Questions

**Question 1.** What does `new BigDecimal(Double.NaN)` return? What about `BigDecimal.valueOf(Double.POSITIVE_INFINITY)`?

**Answer:** Both throw `NumberFormatException` because `BigDecimal` has no value corresponding to NaN or infinity.

**Question 2.** Do `BigDecimal.ONE.divide(BigDecimal.ZERO)` and `1.0/0.0` behave similarly?

**Answer:** No. BigDecimal throws `ArithmeticException`; `double` produces positive Infinity.

**Question 3.** Why can `BigDecimal.ONE.divide(new BigDecimal("3"))` throw `ArithmeticException` even though the denominator is non-zero?

**Answer:** The quotient 1/3 has no finite decimal representation; the exact division overload does not allow automatic rounding. You must specify precision/scale and rounding if business logic permits approximation.

**Question 4.** Is `new BigDecimal("1E+400")` infinite? What about its `doubleValue()` result?

**Answer:** The BigDecimal is a valid finite number; narrowing to `double` can become `Infinity` due to binary64 overflow.

**Question 5.** Does `new BigDecimal("1E-400").doubleValue()` produce a finite number and preserve the value?

**Answer:** It produces finite `0.0` in the example, yet does not preserve the non-zero decimal value 10^-400.

**Question 6.** If a service returns the string `"NaN"` instead of a monetary amount, should `new BigDecimal("NaN")` be used or should it be replaced with 0?

**Answer:** No. You should define an "invalid/undefined data" state in the contract and handle it separately, instead of assigning an unfounded 0 amount.

**Question 7.** Does `Double.isFinite(amount.doubleValue())` being true suffice to prove the conversion did not lose precision?

**Answer:** No. Finiteness does not verify an exact round-trip; underflow and rounding can still occur.

## References

- [Oracle Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): unscaled/scale model, differences from IEEE 754 on NaN/infinity/negative zero, errors on division by 0, `doubleValue`, and constructors.
- [Oracle Java SE 21 — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `isNaN`, `isInfinite`, `isFinite`, `parseDouble`.
- [Oracle Java SE 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): rounding policies when computing decimal numbers.
- [Oracle Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision and rounding in BigDecimal operations.
- [RFC 8259 — JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON number grammar without NaN/Infinity.