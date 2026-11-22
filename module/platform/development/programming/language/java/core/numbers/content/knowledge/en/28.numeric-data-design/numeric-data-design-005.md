# Validating Inputs Before Potentially Lossy Conversions in Java

## 1. The Problem: A Successful Conversion Can Still Produce Wrong Data

In Java, a numeric conversion can compile and run successfully yet **fail to preserve the input value**. For example:

~~~java
int truncated = (int) 12.9;          // 12: fractional part lost
int overflowed = (int) 2147483648L; // -2147483648: high bits lost
int invalid = (int) Double.NaN;      // 0: non-numeric input
~~~

If you only inspect the result after casting, the information needed to detect the error has already vanished. This is why inputs must be validated **before** conversions that can truncate fractions, overflow ranges, underflow, or round.

Before a conversion, you must answer: what is the valid value range, can the target type represent that value, must exact precision be preserved, and if it cannot be preserved, should it be **rejected** or **rounded per an explicit policy**?

This lesson focuses on Core Java numeric data: `int`, `long`, `float`, `double`, `BigInteger`, `BigDecimal`, and numeric strings. The goal is keeping data faithful to the application contract, not merely avoiding exceptions.

## 2. Classifying Common Losses

| Conversion | What Can Happen? | Example | Prevention |
| --- | --- | --- | --- |
| `long → int` | High bits lost, sign flip | `2147483648L → -2147483648` | `Math.toIntExact` |
| `double → int` | Truncates fractional part toward 0 | `12.9 → 12` | Verify integer value before casting |
| `double → int` | NaN becomes 0, out-of-range saturates at bounds | `NaN → 0` | `Double.isFinite`, range check |
| `int → float` | Significant digits lost | `16777217 → 16777216` | Check exact representability |
| `long → double` | Large integer rounded | `9007199254740993 → 9007199254740992` | Keep `long` or use an exact type |
| `double → float` | Reduced precision, possible infinity/zero | `0.1d → float` | Check finiteness and round-trip |
| `BigDecimal → int/long` | Fractional part lost or range overflow | `12.75.intValue() → 12` | `intValueExact`, `longValueExact` |
| `BigDecimal → double` | Binary approximation, overflow/underflow | `0.1`, `1E+400` | Keep `BigDecimal` if exactness is required |
| String → number | Invalid syntax or value outside business domain | `"NaN"`, `"-5"`, `"1e100"` | Multi-layer parsing and validation |

Distinguish **range**, **precision**, and **rounding rules**. A value inside the target type's range still may not be represented exactly. Conversely, `12.000` has three digits after the decimal point yet converts to integer `12` **with zero loss**.

## 3. From long to int: Use Math.toIntExact

`int` is a 32-bit signed integer, from `-2147483648` to `2147483647`; `long` is a 64-bit signed integer.

~~~java
long source = 2_147_483_648L;
int wrong = (int) source; // -2147483648: still runs without error
~~~

Java does not throw an exception when narrowing a primitive from `long` to `int`. To guarantee exactness:

~~~java
int safe = Math.toIntExact(source);
// ArithmeticException because source exceeds Integer.MAX_VALUE
~~~

`Math.toIntExact(long)` returns `int` if the numeric value is preserved, otherwise it throws `ArithmeticException`.

Manual validation is valid when you need a specific error message:

~~~java
static int toIntChecked(long value) {
    if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Out of int range");
    }
    return (int) value;
}
~~~

The snippet above is a **method fragment**; place it inside a Java class to run. The cast on the final line occurs only after both bounds have been checked.

**Note:** `Math.toIntExact` cannot repair an operation that has already overflowed earlier. If `int a + int b` overflowed, promoting that wrong sum to `long` cannot recover the original value either.

## 4. From double to int: Finite, In Range, and No Fractional Part

With the cast `(int) doubleValue`, Java truncates the fractional part **toward 0**. Thus `12.9 → 12`, `-12.9 → -12`. Furthermore:

- `Double.NaN` is converted to 0.
- Values that are too large or `Double.POSITIVE_INFINITY` saturate to `Integer.MAX_VALUE`; values too small or negative infinity saturate to `Integer.MIN_VALUE`.
- `-0.0` becomes integer 0, without preserving the sign of zero.

If the requirement is an **exact integer value**, validate beforehand:

~~~java
static int doubleToIntChecked(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Not a finite number");
    }
    if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) {
        throw new IllegalArgumentException("Out of int range");
    }
    if (value != Math.rint(value)) {
        throw new IllegalArgumentException("Has fractional part");
    }
    return (int) value;
}
~~~

`Math.rint(value)` is used to detect whether the value is an integer; the code **does not use the result of `rint` to silently round**. This function accepts `-0.0` as the numeric value 0. If the problem requires preserving the negative zero sign bit, `int` cannot store that information; you must forbid it or record it separately.

If the source is a decimal number entered by a user, **do not parse through `double` first** and check integrality afterward, because large values or many digits may already have been rounded. Use `BigDecimal` from the string and `intValueExact()` when exact decimal values must be preserved.

## 5. Why Can Converting Integers to float/double Still Lose Precision?

Even though `float` or `double` can hold very large magnitudes, they have a finite number of bits dedicated to **significant digits**.

- IEEE 754 binary32 `float` has 24 bits of binary precision. Every integer in `[-2^24, 2^24]` is represented exactly, but not every integer outside that interval.
- IEEE 754 binary64 `double` has 53 bits of binary precision. Every integer in `[-2^53, 2^53]` is represented exactly, but not every integer outside that interval.

Example runnable inside a method:

~~~java
int number = 16_777_217;
float asFloat = (float) number;

System.out.println((int) asFloat); // 16777216
// Lost 1 compared to number=16777217.
~~~

With `long`:

~~~java
long number = 9_007_199_254_740_993L;
double asDouble = (double) number;

System.out.println((long) asDouble); // 9007199254740992
// Lost 1 compared to the original long.
~~~

A **trap when double-checking**:

~~~java
long original = 9_007_199_254_740_993L;
double converted = (double) original;
boolean looksEqual = converted == original; // Can be true!
~~~

In the comparison `double == long`, Java **converts the `long` operand to `double` as well**. Because both sides can be rounded identically, `looksEqual` can be true even though the original integer lost precision. The same applies when comparing `float` and `int`.

If the goal is to ensure every value in a domain stays exact, design the domain within the exact interval. If you need to verify a specific `long` outside that interval, you can compare via the exact representation of the actual `double` value:

~~~java
static boolean exactlyRepresentableAsDouble(long value) {
    double asDouble = (double) value;
    return java.math.BigDecimal.valueOf(value)
            .compareTo(new java.math.BigDecimal(asDouble)) == 0;
}
~~~

In this method, `new BigDecimal(asDouble)` is used **intentionally** to reconstruct the exact binary value represented inside `double`; do not confuse it with `BigDecimal.valueOf(double)`, which uses `double`'s canonical decimal string. You can also use `BigInteger` to verify integer values in an equivalent design.

## 6. From double to float: Narrowing Can Round

A finite `double` may not be exactly representable in `float`; very large numbers become infinity, and tiny non-zero numbers become 0.

To require **no further value loss compared to the current `double`**:

~~~java
static float doubleToFloatChecked(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Not finite");
    }
    float result = (float) value;
    if (!Float.isFinite(result) || (double) result != value) {
        throw new IllegalArgumentException("Precision loss when casting to float");
    }
    return result;
}
~~~

Every finite `float` value is represented exactly when widened back to `double`. Therefore, comparing the cast `float` widened back against the pre-cast `double` checks for **new loss introduced at this conversion step**. This check cannot recover original decimal digits that were already rounded earlier during parsing or `double` arithmetic.

This is a numeric-value check. If representation details like the sign of zero must also be preserved, inspect/record the sign bit separately.

## 7. BigDecimal: Exact Conversions

For exact decimal values, `BigDecimal` provides two groups of conversion APIs:

| Method | Policy |
| --- | --- |
| `intValue()`, `longValue()` | May truncate fractional parts and/or drop high bits |
| `intValueExact()`, `longValueExact()` | Throws `ArithmeticException` if fractional part is non-zero or out of range |
| `toBigInteger()` | Truncates fractional part toward 0 |
| `toBigIntegerExact()` | Throws `ArithmeticException` if there is a non-zero fractional part |

Example:

~~~java
BigDecimal a = new BigDecimal("12.000");
BigDecimal b = new BigDecimal("12.001");

System.out.println(a.intValueExact()); // 12
// b.intValueExact();                   // ArithmeticException
~~~

`12.000` is still an integer in value; `BigDecimal.scale() == 3` does not mean converting to `int` necessarily loses data. Check exactness by **value**, rather than forbidding all positive scales by default.

With `BigDecimal.doubleValue()`, you do not have the same exactness guarantee. Decimal `0.1` is not represented exactly in binary64; huge values like `1E+400` become infinity. If you need to keep money or exact decimal data, continue computing with `BigDecimal` and avoid detouring through `double`.

`BigDecimal` does not automatically validate business ranges. A value can convert exactly to `long` yet still violate "non-negative amount" or "maximum 1,000 units." Validate both **semantics** and **representability**.

## 8. Numeric String Input Validation Pipeline

When data arrives from JSON, forms, CSV, or HTTP requests, keep the **original string** when format control is needed and the target numeric type is not yet guaranteed. A pipeline can include:

1. **Presence and length:** null, blank, overly long string.
2. **Permitted syntax:** minus sign, plus sign, whitespace, decimal point, exponent, thousands separators, special characters.
3. **Parse with sufficiently exact type:** e.g., `BigDecimal(String)` for decimals; `BigInteger(String)` for very large integers.
4. **Business domain:** non-negative, allowed range, unit of measure, integer quantity, precision/scale.
5. **Representability in target type:** exact methods, min/max bounds, and precision-loss checks if needed.
6. **Policy when not exact:** reject or round per the specified `RoundingMode`.
7. **Store/use only validated results.**

Never equate "parsed successfully" with "valid data." For instance, `Double.parseDouble("NaN")` and `Double.parseDouble("Infinity")` produce special values, so when accepting only finite numbers you must still check `Double.isFinite`.

`new BigDecimal("1E+3")` parses to 1000, yet if the input format forbids scientific notation, it must still be rejected at the **syntax layer**. Similarly, `"-0.00"` has numeric value 0 in `BigDecimal`; if the contract forbids a leading minus sign even for zero, check the string before parsing.

## 9. Business Example: Converting Decimal Money to the Smallest Unit

Suppose the input is a **string monetary amount**, stored as a `long` representing cents. Rules:

- The value must be non-negative.
- Accept only values that convert exactly to integer cents. `12.340` is permitted because the dropped trailing digit is 0.
- The cent count must fit in `long`.
- Malformed, negative, over-precise, or oversized data is rejected.

Implementation:

~~~java
static long toCents(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Missing amount");
    }
    BigDecimal amount = new BigDecimal(raw.strip());
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("Negative amount");
    }
    return amount.movePointRight(2).longValueExact();
}
~~~

`movePointRight(2)` multiplies the decimal value by 100 without rounding; `longValueExact()` requires the scaled value to be an integer within the `long` range. Thus `12.34 → 1234`, `12.340 → 1234`; `12.345` is rejected because it corresponds to 1234.5 cents.

This specification checks that **the value is preserved**. If the rule requires the input representation to have **at most two digits after the decimal point**, then even `12.340` must be rejected by additional syntax/scale checks. These two rules are different.

This is a technical example, not a claim that every currency has a minor unit of 1/100; units and rounding policies must come from business requirements.

## 10. Complete Java 17 Program and Exact Output

Create the file `CheckedConversionDemo.java`:

~~~java
import java.math.BigDecimal;

public class CheckedConversionDemo {
    static long toCents(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Missing amount");
        }
        BigDecimal amount = new BigDecimal(raw.strip());
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        return amount.movePointRight(2).longValueExact();
    }

    static void showCents(String raw) {
        try {
            System.out.println(raw + " -> " + toCents(raw) + " cents");
        } catch (IllegalArgumentException | ArithmeticException ex) {
            System.out.println(raw + " -> REJECTED");
        }
    }

    static int toIntChecked(double value) {
        if (!Double.isFinite(value)
                || value < Integer.MIN_VALUE
                || value > Integer.MAX_VALUE
                || value != Math.rint(value)) {
            throw new IllegalArgumentException("Not exact int");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        showCents("12.34");
        showCents("12.340");
        showCents("12.345");
        showCents("-1.00");
        showCents("92233720368547758.08");

        System.out.println("long 42 -> " + Math.toIntExact(42L));
        try {
            Math.toIntExact(2_147_483_648L);
        } catch (ArithmeticException ex) {
            System.out.println("int overflow -> REJECTED");
        }

        System.out.println("unsafe 42.9 -> " + (int) 42.9);
        System.out.println("checked 42.0 -> " + toIntChecked(42.0));
        try {
            toIntChecked(42.9);
        } catch (IllegalArgumentException ex) {
            System.out.println("fraction -> REJECTED");
        }
        System.out.println("NaN finite -> " + Double.isFinite(Double.NaN));
        System.out.println("NaN cast -> " + (int) Double.NaN);
        System.out.println("exact decimal int -> "
                + new BigDecimal("12.000").intValueExact());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac CheckedConversionDemo.java
java CheckedConversionDemo
~~~

Output:

~~~text
12.34 -> 1234 cents
12.340 -> 1234 cents
12.345 -> REJECTED
-1.00 -> REJECTED
92233720368547758.08 -> REJECTED
long 42 -> 42
int overflow -> REJECTED
unsafe 42.9 -> 42
checked 42.0 -> 42
fraction -> REJECTED
NaN finite -> false
NaN cast -> 0
exact decimal int -> 12
~~~

Interpreting the key points:

- `12.345 × 100 = 1234.5`, which cannot convert to `long` exactly.
- `92233720368547758.08 × 100 = 9223372036854775808`, exceeding `Long.MAX_VALUE` by one unit.
- `Math.toIntExact(2_147_483_648L)` rejects instead of silently becoming negative.
- `42.9` is cast directly to 42; `toIntChecked(42.9)` rejects because of the fractional part.
- `Double.NaN` is not finite, yet casting directly to `int` yields 0.
- `new BigDecimal("12.000").intValueExact()` succeeds because all fractional digits are zero.

## 11. When Rounding Is Allowed: State Timing and Mode

"Zero data loss" and "controlled rounding" are **two different contracts**.

When you must keep exactly two digits after the decimal point or reject:

~~~java
BigDecimal value = new BigDecimal("12.345");
BigDecimal exact = value.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
// ArithmeticException: rounding required, not permitted.
~~~

When policy permits rounding:

~~~java
BigDecimal value = new BigDecimal("12.345");
BigDecimal rounded = value.setScale(
        2, java.math.RoundingMode.HALF_EVEN);
// 12.34: exact tie case, last kept digit is 4 (even).
~~~

These are **illustrative snippets** inside a class with `BigDecimal` imported. Choose `HALF_UP`, `HALF_EVEN`, `UP`, `DOWN`, or another mode based on real business rules, not by the name alone.

`setScale(2, UNNECESSARY)` still allows `12.340` to become `12.34`, because dropping trailing zeros does not change numeric value. If you must preserve or validate the **original text format**, store/validate the string before normalization.

Do not automatically round after every intermediate step. "Round each term then sum" and "sum exactly then round" can yield different results. The specification must explicitly state **when** rounding occurs.

## 12. Data Loss Before Conversion: Arithmetic Overflow and Integer Division

Sometimes the target type is wide enough, yet the calculation **already went wrong before assignment**:

~~~java
int a = 2_000_000_000;
int b = 2_000_000_000;

long wrong = a + b;       // int addition already overflowed beforehand
long correct = (long) a + b; // 4000000000
~~~

`long wrong` does not hold the exact mathematical sum because the operands were added in the `int` domain. If the result must stay within `int` without overflowing, use `Math.addExact(a, b)`, `Math.multiplyExact`, `Math.subtractExact`, or appropriate APIs.

Similarly:

~~~java
int numerator = 5;
int denominator = 2;

double wrong = numerator / denominator;          // 2.0
double approximate = (double) numerator / denominator; // 2.5
~~~

The expression `numerator / denominator` performs integer division first, so the fractional part is already lost before assigning to `double`. If you need **exact** decimal computation or rounding under clear rules, use `BigDecimal.divide(..., scale, roundingMode)`; if inputs and outputs allow approximation, converting to `double` before dividing can be appropriate.

Checking `Math.toIntExact` **after** an overflowing `int` operation or converting to `BigDecimal` **after** integer division cannot recover already-lost values.

## 13. Range Checks and Format Checks: Do Not Conflate Them

Input `"12.000"` has scale 3 yet has integer value 12. Therefore:

- To guarantee the value converts to `int` unchanged: use `intValueExact()`.
- To guarantee a monetary value converts to cents without losing fractional cents: use `movePointRight(2).longValueExact()`.
- To enforce **a string with at most two digits after the decimal point**: validate the input string structure or scale per permitted syntax.
- To enforce a range like `0 <= amount <= 1000`: compare `BigDecimal.compareTo` against both bounds.
- To limit significant digits: specify handling of precision, trailing zeros, and scientific notation, then validate separately.

`BigDecimal.scale()` is not synonymous with the number of significant digits. For example, `new BigDecimal("12.000")` has scale 3 and precision 5. A string using an exponent can produce a `BigDecimal` with a negative scale, so never infer lexical input rules from `scale` alone.

Notably, `new BigDecimal("-0.00").signum() == 0`; if an input string with a minus sign is invalid **even when equal to 0**, validation must inspect the original string before converting to `BigDecimal`.

## 14. Common Mistakes

**1. Casting before checking bounds.** After `(int) longValue`, high bits are already gone. Validate on `long` or use `Math.toIntExact`.

**2. Using `BigDecimal.intValue()` when exactness is required.** It can drop fractions or overflow; use `intValueExact()`.

**3. Assuming successful parsing means valid.** `Double.parseDouble("NaN")` can return NaN; a negative `BigDecimal` parses fine even if business rules forbid negatives.

**4. Using `value == Double.NaN` to detect NaN.** Under IEEE 754 rules, NaN is not equal to itself. Use `Double.isNaN`; to reject both NaN and infinity, use `Double.isFinite`.

**5. Assuming numbers represented by `double`/`float` are exact.** Very large integers and decimals like `0.1` can be rounded. A wide magnitude range does not mean infinite precision.

**6. Converting back and comparing with `==` without considering promotion rules.** `doubleValue == longValue` can convert both to `double`, hiding data loss.

**7. Creating `new BigDecimal(0.1)` and expecting exact decimal 0.1.** The literal `0.1` is already an approximate `double`. For exact decimal inputs, use `new BigDecimal("0.1")`; when receiving an existing `double`, understand the source's precision limits.

**8. Rounding by default without a policy.** `HALF_UP` vs. `DOWN` is a business decision. If value loss is forbidden, use exact methods or `RoundingMode.UNNECESSARY`.

**9. Confusing value rules with representation rules.** `12.340` converts exactly to 1234 cents yet violates a string policy allowing at most two digits after the decimal point.

**10. Checking only the final result while ignoring intermediate operations.** `int` addition overflow or fractions dropped by integer division cannot be recovered by a wider target type.

**11. Automatically replacing parse errors with 0.** Missing or malformed data does not necessarily mean numerical zero. Apply defaults only when explicitly specified in the contract.

**12. Skipping boundary tests.** Exact extrema, one unit past extrema, near zero, tiny fractions, NaN, infinity, and scientific notation expose bugs that ordinary numbers never reveal.

## 15. Exercises and Answers

### Exercise 1: Spot Where Data Is Lost

~~~java
long original = 2_147_483_648L;
System.out.println((int) original);

double fraction = -12.9;
System.out.println((int) fraction);

BigDecimal price = new BigDecimal("8.010");
System.out.println(price.movePointRight(2).longValueExact());
~~~

Output when placed in a program importing `BigDecimal`:

~~~text
-2147483648
-12
801
~~~

The first two cases lose data: `long → int` overflows the range and `double → int` truncates the fraction. The last case preserves the value: `8.010 × 100 = 801.0`, which converts exactly to `long`.

### Exercise 2: Choose Valid Inputs for toCents

| String | Result per `toCents` in Section 9 | Explanation |
| --- | --- | --- |
| `"0"` | `0` | Valid zero value |
| `"9.9"` | `990` | Exact conversion |
| `"9.999"` | Rejected | `999.9` cents has a fractional part |
| `"9.990"` | `999` | Dropping trailing zero does not alter value |
| `"-0.00"` | `0` | BigDecimal represents zero, `signum == 0` |
| `"-0.01"` | Rejected | Violates non-negative condition |
| `"abc"` | Rejected | Unparseable |

If the API forbids a leading `-` character even for 0, add an input string check.

### Exercise 3: Why Can the Comparison Be Misleading?

~~~java
long original = 9_007_199_254_740_993L;
double narrowed = (double) original;
boolean same = narrowed == original;
~~~

`same` can be true because `original` is promoted to `double` right inside the comparison. It **does not** prove the conversion was lossless. Keep the input domain within `[-2^53, 2^53]` for a simple guarantee across all integers, or check using an exact representation of each value.

### Exercise 4: Design Temperature Validation

An API receives Celsius temperature strings in `[-100.00,100.00]`, stored as an `int` count of hundredths of a degree. Sound design: validate format, parse `BigDecimal`, compare range against both bounds, call `movePointRight(2).intValueExact()`, and return an error if exact conversion fails. If policy limits digits **in the string**, add a lexical check beforehand.

### Exercise 5: Choose the Right API

- `long → int` forbidding overflow: `Math.toIntExact`.
- `BigDecimal → long` forbidding fractional loss: `longValueExact()`.
- `BigDecimal → BigInteger` forbidding fractional truncation: `toBigIntegerExact()`.
- Checking finite `double`: `Double.isFinite`.
- Shrinking scale while forbidding value-changing rounding: `setScale(target, RoundingMode.UNNECESSARY)`.
- Integer arithmetic forbidding overflow: `Math.*Exact` methods.

## 16. Pre-Conversion Acceptance Checklist

1. Is the original data still preserved with enough precision to validate?
2. Have syntax, range, unit, and policies for sign, zero, digits, and exponents been validated?
3. Have target-type range and exact representability been checked?
4. If the source is floating-point, have NaN/infinity been rejected and fractions, underflow, and overflow accounted for?
5. If using `BigDecimal`, have `*ValueExact` or an explicit `RoundingMode` policy been selected?
6. Could operations prior to conversion already have lost data?
7. Do tests cover boundary values, just-out-of-bounds values, invalid numbers, and rounding cases?

**Key takeaway:** Validate **before data is transformed**. A valid `int`, `long`, `float`, or `double` result does not prove equality to the source value. Use exact APIs, check finiteness/range/precision first, and only then convert; if rounding intentionally, document the policy and timing explicitly.