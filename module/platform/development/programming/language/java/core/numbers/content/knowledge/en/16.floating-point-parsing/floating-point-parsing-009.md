# Validating Finiteness and Range After Parsing in Java

## 1. Why does successful parsing not mean valid data?

When a program receives floating-point numbers from forms, configuration files, CSV, or APIs, the first step is usually `Double.parseDouble(String)` or `Float.parseFloat(String)`. However, **successful string conversion proves only that the string was accepted under Java's floating-point syntax**; it does not guarantee that the result fits the data range, business meaning, or precision requirements.

Example:

~~~java
double normal = Double.parseDouble("12.5");
double nan = Double.parseDouble("NaN");
double inf = Double.parseDouble("Infinity");
double overflow = Double.parseDouble("1e309");
double tiny = Double.parseDouble("1e-400");
~~~

All of the calls above can complete **without throwing `NumberFormatException`**. Yet:

- `normal` equals 12.5 and is finite.
- `nan` holds `NaN` (*Not a Number*).
- `inf` and `overflow` hold `+Infinity`.
- `tiny` equals `0.0` because the nonzero decimal result is too small to represent as a `double`.

Accordingly, a reliable workflow is **read string → parse → check finiteness → check business range → check additional precision conditions if needed → use**. This lesson focuses on each step and subtle bugs in Java 17+ code.

## 2. Two common floating-point parsing methods

| API | Returns | Representation range | Response to invalid syntax |
| --- | --- | --- | --- |
| `Double.parseDouble(text)` | `double` primitive | IEEE 754 binary64 | Throws `NumberFormatException` |
| `Float.parseFloat(text)` | `float` primitive | IEEE 754 binary32 | Throws `NumberFormatException` |
| `Double.valueOf(text)` | `Double` wrapper | Same as `double` | Throws `NumberFormatException` |
| `Float.valueOf(text)` | `Float` wrapper | Same as `float` | Throws `NumberFormatException` |

Example:

~~~java
double a = Double.parseDouble("3.14");
float b = Float.parseFloat("3.14");
Double wrapped = Double.valueOf("3.14");
~~~

This is an illustrative snippet placed inside a method, not a complete Java program. `parseDouble` and `parseFloat` return **primitives**; `valueOf` returns **wrappers**. Regardless of which API is used, out-of-range business data or `NaN`/`Infinity` still requires separate validation.

`NumberFormatException` indicates only that string conversion failed due to syntax; you should not treat **not** catching this exception as validation of "clean" data.

### Strings that Java can parse

~~~java
System.out.println(Double.parseDouble("-12.5"));  // -12.5
System.out.println(Double.parseDouble("1e3"));    // 1000.0
System.out.println(Double.parseDouble("0x1.8p2")); // 6.0
System.out.println(Double.parseDouble("NaN"));    // NaN
System.out.println(Double.parseDouble("-Infinity")); // -Infinity
~~~

`0x1.8p2` is a hexadecimal floating-point number: base-16 `1.8` multiplied by `2²`, which equals 6.0. This shows that `Double.parseDouble` accepts **more than simple decimal number syntax**.

In Java, `"NaN"` and `"Infinity"` are accepted special strings, yet they are **not finite numbers**. If your API permits only ordinary decimal numbers, enforce a dedicated input format policy; do not confuse "Java's parser accepts it" with "business API allows it."

## 3. Finite values, Infinity, and NaN

There are three important result groups after parsing:

| Group | Examples | `Double.isFinite(x)` | `Double.isNaN(x)` | `Double.isInfinite(x)` |
| --- | --- | --- | --- | --- |
| Finite | `0.0`, `-0.0`, `12.5`, `Double.MAX_VALUE` | `true` | `false` | `false` |
| Not a Number | `Double.NaN` | `false` | `true` | `false` |
| Infinity | `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` | `false` | `false` | `true` |

Use `Double.isFinite(x)` to accept **only finite numbers**:

~~~java
double parsed = Double.parseDouble("NaN");

if (!Double.isFinite(parsed)) {
    throw new IllegalArgumentException("Value must be finite");
}
~~~

For `float`, use `Float.isFinite(value)`, `Float.isNaN(value)`, and `Float.isInfinite(value)`. These methods operate on primitive values regardless of how the input string was written.

**Note:** `Double.isFinite` returns `true` for `0.0`, `-0.0`, and very small `subnormal` numbers. It excludes only `NaN` and `±Infinity`; it does not mean the number lies in a valid range or was converted without losing information.

## 4. Overflow case: valid parse that produces Infinity

`double` has a largest finite value of `Double.MAX_VALUE`, approximately `1.7976931348623157E308`. `float` has a lower limit, `Float.MAX_VALUE`, approximately `3.4028235E38`.

~~~java
double farTooLarge = Double.parseDouble("1e309");
float tooLargeFloat = Float.parseFloat("1e39");

System.out.println(farTooLarge); // Infinity
System.out.println(tooLargeFloat); // Infinity
System.out.println(Double.isFinite(farTooLarge)); // false
System.out.println(Float.isFinite(tooLargeFloat)); // false
~~~

The outcome is not `NumberFormatException`. The strings have valid floating-point syntax, yet the values exceed the representation range and round to infinity.

If an application accepts a finite positive number in the range 0 to 100, then `"1e309"` must be rejected even though parsing succeeded. If data is not allowed to be infinite, **catching `NumberFormatException` is not enough**.

A negative number of enormous magnitude such as `"-1e309"` can yield `-Infinity`. `Double.isFinite` rejects both signs.

## 5. Underflow, subnormals, and zero values after parsing

At the end near 0, floating-point systems have representation limits:

- `Double.MIN_NORMAL` is the smallest positive *normal* `double`, approximately `2.2250738585072014E-308`.
- `Double.MIN_VALUE` is the **smallest positive nonzero `double`**, approximately `4.9E-324`, belonging to the *subnormal* group.
- Positive numbers smaller than `Double.MIN_VALUE` can round to `0.0`; corresponding negative numbers can become `-0.0`.

~~~java
double subnormal = Double.parseDouble("4.9e-324");
double tiny = Double.parseDouble("1e-400");
double negativeTiny = Double.parseDouble("-1e-400");

System.out.println(subnormal == Double.MIN_VALUE); // true
System.out.println(tiny); // 0.0
System.out.println(negativeTiny); // -0.0
System.out.println(Double.isFinite(tiny)); // true
~~~

Notably, `"1e-400"` is mathematically a **nonzero positive** number, yet when stored in `double` it becomes **0.0**. Because `0.0` is still finite, `isFinite` does not detect this loss of value.

**Do not equate two separate questions:**

1. Is the final `double` value finite?
2. Was the numeric value in the original string preserved accurately enough when converted to `double`?

The second question cannot always be answered using only an already-parsed `double`. If there is a strict requirement never to turn a nonzero decimal value into 0, inspect the input string or use a type with suitable precision before converting.

## 6. Checking data range after confirming finiteness

Suppose an API accepts temperatures in the range −40°C to 85°C, inclusive at both endpoints. Basic validation:

~~~java
double value = Double.parseDouble(text);

if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Temperature must be a finite number");
}
if (value < -40.0 || value > 85.0) {
    throw new IllegalArgumentException("Temperature outside [-40, 85]");
}
~~~

This is an **illustrative snippet inside a method**, where `text` was supplied earlier. The check order is not decorative: checking finiteness first makes the policy rejecting `NaN`/`Infinity` explicit.

### Why is checking only x < min || x > max not enough?

Every ordering comparison `<`, `>`, `<=`, `>=` with `NaN` evaluates to `false`. Therefore:

~~~java
double value = Double.NaN;
boolean outside = value < -40.0 || value > 85.0;

System.out.println(outside); // false
~~~

If you write only `if (outside) reject`, the program will **mistakenly accept NaN**. This is a critical validation bug when parsing floating-point data.

You can write `if (!Double.isFinite(value) || value < min || value > max) reject`. The expression uses short-circuiting `||`; writing separate check steps is often easier to read and gives clearer error causes.

### Closed vs. open bounds

Depending on business requirements:

- `min <= value && value <= max`: closed interval, includes both endpoints.
- `min < value && value < max`: open interval, excludes both endpoints.
- `value > 0`: accepts strictly positive values, rejects `0.0` and `-0.0`.
- `value >= 0`: accepts both `0.0` and `-0.0` because the two zeros compare equal under arithmetic operators.

Checking finiteness **does not replace** choosing closed/open bounds, integer requirements, or rules for zero.

## 7. A practical parseFiniteInRange helper on Java 17

A simple reusable design:

~~~java
static double parseFiniteInRange(String text, double min, double max) {
    if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
        throw new IllegalArgumentException("Invalid finite bounds");
    }
    if (text == null) {
        throw new IllegalArgumentException("Missing numeric text");
    }

    final double value;
    try {
        value = Double.parseDouble(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Malformed numeric text", ex);
    }

    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Value must be finite");
    }
    if (value < min || value > max) {
        throw new IllegalArgumentException("Value outside bounds");
    }
    return value;
}
~~~

This method is a **class-level method**, not a standalone runnable program. It enforces four contracts:

1. Configured bounds must be two finite values with `min <= max`.
2. The input string must not be `null`.
3. The text must be parseable by `Double.parseDouble`.
4. The parsed result must be finite and within the closed interval `[min, max]`.

`IllegalArgumentException` is an appropriate error signal at API boundaries; you may also define a custom exception if the system needs to classify configuration/validation errors. Note that `NumberFormatException` is itself a subclass of `IllegalArgumentException`, so callers can catch the base type if they want to display a unified error message.

### Java pattern for Float

~~~java
static float parseFiniteFloat(String text, float min, float max) {
    if (!Float.isFinite(min) || !Float.isFinite(max) || min > max) {
        throw new IllegalArgumentException("Invalid bounds");
    }
    if (text == null) {
        throw new IllegalArgumentException("Missing numeric text");
    }

    final float value;
    try {
        value = Float.parseFloat(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Malformed float text", ex);
    }
    if (!Float.isFinite(value) || value < min || value > max) {
        throw new IllegalArgumentException("Float outside valid range");
    }
    return value;
}
~~~

This is an alternative example when the required storage type is `float`. Do not parse into `double` and cast `(float)` if you want exact conversion behavior directly in the target type; if you must cast, re-check the `float` result after casting.

## 8. Complete Java 17+ program

Save as `FiniteParseDemo.java`:

~~~java
public class FiniteParseDemo {
    static double parseFiniteInRange(String text, double min, double max) {
        if (!Double.isFinite(min) || !Double.isFinite(max) || min > max) {
            throw new IllegalArgumentException("Invalid finite bounds");
        }
        if (text == null) {
            throw new IllegalArgumentException("Missing numeric text");
        }

        final double value;
        try {
            value = Double.parseDouble(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Malformed numeric text", ex);
        }
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Value must be finite");
        }
        if (value < min || value > max) {
            throw new IllegalArgumentException("Value outside bounds");
        }
        return value;
    }

    public static void main(String[] args) {
        System.out.println("normal=" +
                parseFiniteInRange("37.5", 0.0, 100.0));
        System.out.println("negative zero=" +
                parseFiniteInRange("-0.0", 0.0, 100.0));

        String[] rejected = {
            "NaN", "Infinity", "-Infinity", "1e309", "101", "not-a-number"
        };
        for (String text : rejected) {
            try {
                parseFiniteInRange(text, 0.0, 100.0);
                System.out.println("accepted=" + text);
            } catch (IllegalArgumentException ex) {
                System.out.println("rejected=" + text);
            }
        }

        System.out.println("underflow=" +
                parseFiniteInRange("1e-400", 0.0, 100.0));
        System.out.println("float overflow finite=" +
                Float.isFinite(Float.parseFloat("1e39")));
        System.out.println("subnormal=" +
                (Double.parseDouble("4.9e-324") == Double.MIN_VALUE));
        System.out.println("hex float=" +
                Double.parseDouble("0x1.8p2"));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 FiniteParseDemo.java
java FiniteParseDemo
~~~

Stdout:

~~~text
normal=37.5
negative zero=-0.0
rejected=NaN
rejected=Infinity
rejected=-Infinity
rejected=1e309
rejected=101
rejected=not-a-number
underflow=0.0
float overflow finite=false
subnormal=true
hex float=6.0
~~~

Reading the output accurately:

- `"37.5"` is finite and inside `[0, 100]`, so it is accepted.
- `"-0.0"` still falls in this closed interval because under arithmetic comparison `-0.0 == +0.0`. If zero's sign has business meaning, check it separately.
- `"NaN"`, `"Infinity"`, and `"1e309"` are accepted by the parser as special floating-point values, yet rejected by validation.
- `"101"` is finite yet **out of range**, so it is rejected.
- `"not-a-number"` fails parsing syntax and is converted into a validation error.
- `"1e-400"` yields `0.0` and is **still accepted** because the logic here requires only *finite* and *in [0, 100]*. This needs an extra check if business rules require preserving all tiny positive values.
- `Float.parseFloat("1e39")` returns Infinity, so `Float.isFinite` returns false.
- `"4.9e-324"` rounds to the smallest positive subnormal; hexadecimal float `0x1.8p2` equals 6.0.

## 9. When must underflow to zero be rejected?

Suppose you are handling a probability that **must be strictly greater than 0**. Then:

~~~java
double probability = Double.parseDouble("1e-400");
if (!Double.isFinite(probability) ||
        probability <= 0.0 || probability > 1.0) {
    throw new IllegalArgumentException("Probability must be in (0, 1]");
}
~~~

The snippet above rejects the input because the result became 0.0, matching the contract "the final `double` value must be greater than 0." However, if the goal is to store **every nonzero positive decimal probability** no matter how tiny, `double` lacks the representation range.

### Use BigDecimal if exact tiny decimal values must be preserved

~~~java
java.math.BigDecimal exact = new java.math.BigDecimal("1e-400");
double narrowed = exact.doubleValue();

System.out.println(exact.signum() > 0); // true
System.out.println(narrowed);           // 0.0
~~~

`BigDecimal` preserves the decimal value in this example; narrowing to `double` loses information. Using `BigDecimal` must be decided **before parsing** the data into `double` — you cannot use `BigDecimal.valueOf(0.0)` to recover the original `1e-400` value.

If you must use `double` yet want to enforce a policy that "nonzero decimal input must not become 0," you can parse `BigDecimal` from the string initially, check `signum()`, and compare against `doubleValue()`. This must be paired with defining accepted formats: `BigDecimal` does not support `"NaN"`/`"Infinity"` strings like `Double.parseDouble`.

## 10. Do not rely solely on Double.isFinite when checking precision

A finite number can still lose significant digits during parsing:

~~~java
double rounded = Double.parseDouble("9007199254740993");
System.out.println(rounded == 9007199254740992.0); // true
~~~

`9007199254740993 = 2⁵³ + 1` cannot be represented exactly in binary64 and rounds to `9007199254740992`. `Double.isFinite(rounded)` still returns true.

If a data field is an identifier, countable integer, monetary amount, or decimal quantity requiring absolute exactness, use the appropriate data type:

- `long` or `BigInteger` for integers (depending on range and validation rules).
- `BigDecimal` for decimal numbers needing decimal exactness.
- `double`/`float` when approximate floating-point modeling is acceptable and tolerances are defined.

**Do not confuse finiteness with exactness.** These are two independent validation axes: a number can be finite yet rounded; a string can parse validly yet yield Infinity; a number can be finite and exact in `double` yet still outside the business domain.

## 11. Checking input strings: null, empty, whitespace, and format

`Double.parseDouble`/`Float.parseFloat` have their own syntax rules. On Java 17, the parser accepts leading/trailing whitespace stripped like `String.trim()` before parsing, yet does not accept underscores used in source-code literals:

~~~java
System.out.println(Double.parseDouble(" 12.5 ")); // 12.5
// Double.parseDouble("1_000"); // Throws NumberFormatException.
~~~

This leads to a design choice:

- If the system allows users to include surrounding spaces, you can accept the parser's behavior.
- If the system demands strict format such as "only decimal digits, dot, and minus sign" or forbids hex, NaN, and suffixes, you must **validate syntax** under a dedicated contract.
- If data may be `null`, check first; `Double.parseDouble(null)` throws `NullPointerException`, not `NumberFormatException`.
- For empty or malformed strings, catch `NumberFormatException` and supply an appropriate error message.

Do not apply an untested custom regex and assume it covers all Unicode, exponent, sign, or decimal forms. Define the API's exact grammar and use the appropriate parser.

### Do not use locale to guess the decimal point

`Double.parseDouble("12.5")` uses a dot per Java syntax, and does not automatically recognize strings using a localized decimal comma. In multilingual applications, normalize data systematically or use `NumberFormat` matching the locale and requiring *full-string* parsing. Whichever method is used, the **finiteness and range check** must still run once a numeric result is obtained.

## 12. Valid ranges: from business requirements to Java conditions

Example table (illustrative limits, not imposed on every system):

| Field | Assumed range | Check |
| --- | --- | --- |
| Percentage | 0 to 100, inclusive | `isFinite(x) && x >= 0 && x <= 100` |
| Probability | 0 to 1, inclusive | `isFinite(x) && x >= 0 && x <= 1` |
| Strictly positive probability | Greater than 0, up to 1 | `isFinite(x) && x > 0 && x <= 1` |
| Device temperature | −40 to 85 | `isFinite(x) && x >= -40 && x <= 85` |
| Product weight | Greater than 0, not exceeding max | `isFinite(x) && x > 0 && x <= max` with validated finite max |
| Coordinates / vector | Range defined by business domain | Validate each component and overall validity |

The expressions above **cannot be used verbatim** if `x` or `max` is a wrapper that might be `null`: a null guard is required before unboxing.

Beyond numeric range, check other business rules such as requiring an integer, measurement resolution, sum limits across components, cross-field constraints, and units. For instance, `37.5` may be valid for temperature yet inappropriate for "integer device count."

### Regarding ±0.0

`Double.parseDouble("-0.0")` is a **finite** number, and `-0.0 == 0.0` is true. If business logic forbids "negative" at the bit level, `value >= 0` does not distinguish `-0.0`; you can inspect the sign using `Double.doubleToRawLongBits(value)` or apply a policy normalizing to `0.0`. Handle zero's sign specially only when it genuinely matters; most ordinary counting/measurement tasks do not need it.

## 13. Common validation mistakes

| Mistake | Why is it wrong? | Fix |
| --- | --- | --- |
| Catching only `NumberFormatException` | `"NaN"`, `"Infinity"`, `"1e309"` parse without throwing | Add `Double.isFinite`/`Float.isFinite` |
| Checking only `x < min || x > max` | `NaN` fails all ordering comparisons and can slip through | Check `isFinite` first |
| Thinking `isFinite` means in range | `1e100` is finite yet may exceed business limits | Check range independently |
| Thinking `isFinite` guarantees exactness | Finite numbers can still be rounded | Choose suitable data type and precision check |
| Using `Double.MIN_VALUE` as the smallest negative number | It is the smallest **nonzero positive** number | Use `-Double.MAX_VALUE` for the negative finite bound by magnitude |
| Assuming `0.0` after parsing is always exact 0 from text | `1e-400` can round to 0.0 | Inspect original decimal string when needed |
| Using `value >= 0` to forbid `-0.0` | The two zeros compare equal | Specify zero-sign inspection if needed |
| Calling `Double.parseDouble(null)` inside catch NumberFormatException | `null` raises `NullPointerException` | Null guard |
| Using `Float.parseFloat` with double's range | `float` has a different range and precision | Validate against the actual storage type |
| Failing to validate min/max passed to validator | NaN/Infinity bounds can break logic | Check both bounds are finite and `min <= max` |
| Using `double` for money or large integer IDs and relying on isFinite | Precision is lost despite being finite | `BigDecimal`, `BigInteger`, or `long` |
| Ignoring locale/units | Strings differ in format or scale | Specify grammar, locale, and units explicitly |

## 14. Building testable validation

A test suite should include at least these categories:

**Syntax:** `"12.5"`, `"-12.5"`, `"abc"`, `""`, `null`, leading/trailing spaces, invalid numeric separators.

**Special values:** `"NaN"`, `"Infinity"`, `"-Infinity"`, and a large number producing Infinity such as `"1e309"`.

**Data range:** exact min/max, just inside, just outside, negative numbers, zero, and out-of-bounds values.

**Representation boundaries:** `"1e-400"` becoming 0.0, smallest subnormal, `Double.MAX_VALUE`, values larger than `MAX_VALUE`, and numbers with many digits needing rounding.

**Semantics:** strictly positive requirements, forbidding NaN, integer requirements, distinguishing missing data from 0, decimal data requiring exactness.

Suggested assertions once `parseFiniteInRange` exists:

~~~java
assert parseFiniteInRange("0", 0, 100) == 0.0;
assert parseFiniteInRange("100", 0, 100) == 100.0;
assert Double.doubleToRawLongBits(
        parseFiniteInRange("-0.0", 0, 100)) ==
        Double.doubleToRawLongBits(-0.0);

// NaN, Infinity, "101", and "abc" cases must be rejected.
// With a test framework, use assertThrows(...) to verify exceptions.
~~~

These are illustrative statements inside a method. Java's `assert` keyword executes only when running the JVM with `-ea`; for automated testing, use framework assertions like JUnit 5. Cases expecting exceptions need dedicated test cases; do not infer from testing only the "happy path" that all invalid inputs are handled.

## 15. Self-check questions

**1.** Does `Double.parseDouble("NaN")` throw `NumberFormatException`?

**Answer:** No. It returns `Double.NaN`; you must use `Double.isNaN` or `!Double.isFinite` to reject it under a finite-only policy.

**2.** What values do `Double.parseDouble("1e309")` and `Double.parseDouble("1e-400")` produce?

**Answer:** In binary64, the first yields `Infinity` due to exceeding range; the second yields `0.0` due to being too small. Both strings have valid numeric syntax.

**3.** Why is `if (x < 0 || x > 100) reject` insufficient if x came from parsing?

**Answer:** If `x` is `NaN`, both conditions are false, causing the code not to reject it. Add `Double.isFinite(x)` before comparing.

**4.** What do `Double.isFinite(0.0)` and `Double.isFinite(Double.MIN_VALUE)` evaluate to?

**Answer:** Both are true. Zero and the smallest positive subnormal are both finite numbers.

**5.** If the input is a positive probability `"1e-400"` and the program must store a **nonzero decimal value**, is `double` alone enough?

**Answer:** No. That string rounds to 0.0 when converted to binary64. Use an appropriate representation such as `BigDecimal` or a specialized probability/logarithmic model depending on the application.

**6.** If parsing yields 101 while the valid range is `[0, 100]`, do you need to worry about `NumberFormatException`?

**Answer:** Parsing already succeeded and 101 is finite. This is a **business range error**; validate after parsing and report an appropriate error.

**7.** When you need to forbid `-0.0` yet allow `0.0`, can you use `value >= 0`?

**Answer:** No, because `-0.0 == 0.0` under primitive comparison. You need to check zero's sign via bits or normalize input according to an explicit policy.

## 16. Takeaways and references

- `Double.parseDouble`/`Float.parseFloat` handle **converting string syntax to floating point**, without automatically checking finiteness, business range, or precision.
- `Double.isFinite`/`Float.isFinite` exclude `NaN` and `±Infinity`, yet do not exclude zero or subnormals.
- Check **numeric range** after finiteness, with min/max and endpoints clearly defined; otherwise `NaN` can pass through a filter using only comparison operators.
- Understand overflow to Infinity, underflow to ±0.0, and rounding of very large/small numbers. Do not treat "parsing succeeded" as proof of no data loss.
- Choose `double` for approximate computation by design, or use `BigDecimal`/`BigInteger`/`long` according to exact representation requirements.

Official Java documentation:

- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `parseDouble`, `isFinite`, `isNaN`, `isInfinite`, and boundary values.
- [Java SE 17 — Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): `parseFloat`, `isFinite`, and binary32 range.
- [JLS 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): NaN, Infinity, normal/subnormal, signed zero.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): exact decimal numbers with arbitrary precision.