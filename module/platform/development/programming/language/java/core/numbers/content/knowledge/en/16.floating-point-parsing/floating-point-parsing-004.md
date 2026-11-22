# Valid Floating-Point Inputs Can Still Be Rounded, Overflow, or Underflow in Java

## 1. Valid syntax does not mean the value is preserved exactly

`Float.parseFloat(String)` and `Double.parseDouble(String)` convert a valid character string into a `float` or `double` floating-point value. Both APIs validate the **string syntax**, then map the mathematical value described by the string onto the finite set of floating-point numbers that Java can represent.

There are three very different outcomes:

1. **Rounding:** the string describes a valid number that does not lie exactly on the `float`/`double` value grid; the parser returns a nearby representative value.
2. **Overflow:** the magnitude of the finite number described by the string is too large; the result can be `+Infinity` or `-Infinity`.
3. **Underflow:** the magnitude is too small for the resolution near 0; the result can be a **subnormal number** with reduced precision or be rounded all the way to `+0.0`/`-0.0`.

All three can happen **even when the string is completely valid** and no `NumberFormatException` is thrown.

```java
double a = Double.parseDouble("0.1");       // Finite, but not strictly exact 0.1
double b = Double.parseDouble("1e400");     // Infinity
double c = Double.parseDouble("1e-4000");   // 0.0
float d = Float.parseFloat("3.5e38");       // Infinity
float e = Float.parseFloat("1e-50");        // 0.0
```

This is a property of converting to fixed-width floating-point numbers, not inherently a parser bug. The application must decide for itself whether to accept rounded results, subnormals, zeros from underflow, or infinities.

### Three questions that must be kept separate

| Question | Example | How to verify |
| --- | --- | --- |
| Does the string have syntax supported by the parser? | `"1e400"` | Does `parseDouble` return a value or throw `NumberFormatException`? |
| Is the parsed value finite? | `"1e400"` → `Infinity` | `Double.isFinite(result)` |
| Is the original value represented exactly? | `"0.1"` → a `double` close to 0.1 | Compare the source mathematical value with the exact binary value without rounding the source again |

Do not conclude that "parsing succeeded" means "within the finite range" or "no digits were lost."

## 2. IEEE 754 background: a string can describe more numbers than the target type

Java `float` is binary32, having 32 total bits with **24 bits of effective significand precision**. Java `double` is binary64, having 64 total bits with **53 bits of effective significand precision**.

Each type has finite values, *normal* numbers, *subnormal* numbers, signed zeros, infinities, and `NaN`. The spacing between two adjacent representable numbers varies with magnitude.

| Property | `float` | `double` |
| --- | --- | --- |
| Significand precision | 24 bits | 53 bits |
| `MAX_VALUE` (largest finite positive) | Approx. `3.4028235E38` | Approx. `1.7976931348623157E308` |
| `MIN_NORMAL` (smallest positive normal) | Approx. `1.17549435E-38` | Approx. `2.2250738585072014E-308` |
| `MIN_VALUE` (smallest nonzero positive, subnormal) | Approx. `1.4E-45` | Approx. `4.9E-324` |
| Positive infinity symbol | `Float.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` |
| Finiteness check | `Float.isFinite(x)` | `Double.isFinite(x)` |

**Important:** `Float.MIN_VALUE` and `Double.MIN_VALUE` are **not the smallest negative numbers**. They are the **smallest nonzero positive** numbers representable by the corresponding type. The finite negative bound in numeric order is `-Float.MAX_VALUE` or `-Double.MAX_VALUE`.

Do not think of `MIN_NORMAL` as a threshold below which every value becomes 0. **Subnormal numbers** allow representing additional tiny positive values between 0 and `MIN_NORMAL`, though relative precision generally degrades compared to normal numbers.

### Representation range and precision are two different limits

A string `"9007199254740993"` is very far from `double`'s overflow bound. Yet that integer (`2^53 + 1`) **cannot** be represented exactly by `double`: it rounds to `9007199254740992`.

Meanwhile, the string `"1e400"` represents a mathematically finite number that is many times larger than `Double.MAX_VALUE`. The parser returns `Infinity`.

Therefore, a value can be:

- Finite and exact, such as `0.5`.
- Finite but rounded, such as `0.1` or `2^53 + 1`.
- Finite, very small, subnormal, and possibly rounded.
- So small that it becomes `0.0`.
- So large that it becomes infinity.

## 3. Valid strings that get rounded

### 3.1. The decimal value `0.1`

The decimal number `0.1` has no finite binary representation. The parser selects a `double` close to it:

```java
double x = Double.parseDouble("0.1");

System.out.println(x);                         // 0.1
System.out.println(new java.math.BigDecimal(x));
// 0.1000000000000000055511151231257827021181583404541015625
```

`Double.toString` chooses a short decimal form that parses back to the same `double` value, so printing `0.1` **does not prove** `1/10` is stored exactly.

Here `new BigDecimal(x)` is **a technique to inspect the exact binary value of an existing `double`**, not the recommended way to initialize decimal monetary amounts. To keep the exact original decimal, use `new BigDecimal("0.1")`.

For `float`:

```java
float x = Float.parseFloat("0.1");
System.out.println((double) x); // 0.10000000149011612
```

Casting the parsed `float` to `double` helps reveal the approximated `float` value (since every finite `float` can be represented exactly in `double`); the cast does not recover the mathematical `0.1`.

### 3.2. Large integers can still be rounded

```java
double x = Double.parseDouble("9007199254740993");
double y = Double.parseDouble("9007199254740992");

System.out.println(x);      // 9.007199254740992E15
System.out.println(x == y); // true
```

The first string is valid, but the integer value `2^53 + 1` has no exact `double` representation. The two strings describe **two different integers**, yet after parsing they become the exact same value.

If these are IDs, fine-grained integer timestamps, quantities, or keys that must distinguish individual units, do not store them in `double`. Use `Long.parseLong` when within `long` range, or `BigInteger` when a wider range is required.

### 3.3. What rule does the parser use for rounding?

Java converts valid decimal and hexadecimal floating-point numbers to a representable value of the target type, rounding to the nearest value. If the exact value lies halfway between two representable values, the one with an even least-significant significand bit is chosen (*round to nearest, ties to even*).

A binary hex example that represents the exact value at **half a ULP** above `1.0`:

```java
double halfway = Double.parseDouble("0x1.00000000000008p0");
System.out.println(halfway); // 1.0
```

Here the hex string describes `1 + 2^-53`, halfway between `1.0` and `Math.nextUp(1.0)`; the `1.0` side has an even least-significant significand bit, so it is chosen.

This differs from `Math.round`, which has its own rules and returns an integer type. It also differs from `BigDecimal.setScale`, where the caller explicitly chooses a `RoundingMode`.

**Note:** `Float.parseFloat` targets `float` precision directly. Do not assume that `Double.parseDouble(text)` followed by a cast to `float` is equivalent in every case near a rounding boundary, because **double rounding** can differ from rounding directly once.

## 4. Valid strings that overflow to infinity

Overflow occurs when a value's magnitude exceeds the finite representable capacity of the target type. The parser can still return a valid IEEE 754 value: `+Infinity` or `-Infinity`.

```java
double positive = Double.parseDouble("1e400");
double negative = Double.parseDouble("-1e400");
float tooBigForFloat = Float.parseFloat("3.5e38");

System.out.println(positive);       // Infinity
System.out.println(negative);       // -Infinity
System.out.println(tooBigForFloat); // Infinity
```

There is no `NumberFormatException` in the three strings above. They **have valid syntax** and represent very large finite decimal numbers, but they cannot be represented as finite values of the chosen type.

```java
System.out.println(Double.isInfinite(positive)); // true
System.out.println(Double.isFinite(positive));   // false
System.out.println(Double.isNaN(positive));      // false
```

### Explicit `Infinity` in a string is also valid input

The parser supports the tokens `"Infinity"`, `"-Infinity"`, and `"NaN"`:

```java
System.out.println(Double.parseDouble("Infinity")); // Infinity
System.out.println(Double.isNaN(Double.parseDouble("NaN"))); // true
```

Therefore, when the result is infinite, checking `Double.isInfinite(result)` alone **cannot tell**:

1. Whether the user sent the token `"Infinity"`, or
2. Whether the user sent a finite number such as `"1e400"` that overflowed.

If the contract needs to distinguish the cause, examine the **source string and source syntax/value before information is lost**, not only the returned `double` value.

The application may reject all non-finite values; however, that is a **post-parse business range check**, not a syntax error that Java catches for you automatically.

### Overflow does not happen only during parsing

Even two finite `double` values can produce `Infinity` when multiplied or added; thus checking `isFinite` at input only validates the input, **not that all subsequent operations remain finite**. If an algorithm requires a finite domain, verify at the appropriate boundaries.

## 5. Valid strings that underflow to subnormal or zero

Near zero, `double` resolution has a limit. The **smallest nonzero positive** number is `Double.MIN_VALUE`, approximately `4.9406564584124654 × 10^-324`. For `float`, the corresponding value is approximately `1.401298464324817 × 10^-45`.

When a positive number is much smaller than the minimum representable level, rounding can produce `0.0`. If an extremely small negative number is parsed, the result can be `-0.0` — negative zero still carries a **sign bit**.

```java
double tiny = Double.parseDouble("1e-4000");
double tinyNegative = Double.parseDouble("-1e-4000");

System.out.println(tiny);           // 0.0
System.out.println(tinyNegative);   // -0.0
System.out.println(tinyNegative == 0.0); // true
```

Both `"1e-4000"` and `"-1e-4000"` are valid strings, and both describe mathematically **nonzero** numbers, yet after parsing their magnitude is lost. No exception is thrown.

Checking the sign of zero:

```java
long bits = Double.doubleToRawLongBits(tinyNegative);
System.out.println(Long.toHexString(bits)); // 8000000000000000
```

Although `-0.0 == +0.0` is `true`, the sign can affect operations such as `1.0 / -0.0` (yielding `-Infinity`) and the behavior of `Double.compare` and `Double.equals`.

### Subnormal region

Not every number smaller than `Double.MIN_NORMAL` is rounded to 0:

```java
double subnormal = Double.parseDouble("1e-320");
System.out.println(subnormal); // 1.0E-320
```

This is a positive, nonzero `double` value, yet **smaller than `Double.MIN_NORMAL`**. It lies in the subnormal region. In this region, the absolute step between two adjacent values remains very small, but relative precision decreases as magnitude approaches 0.

For `float`:

```java
System.out.println(Float.parseFloat("1e-44")); // 9.8E-45
System.out.println(Float.parseFloat("1e-50")); // 0.0
```

The string `"1e-44"` produces a nonzero subnormal number after rounding, whereas `"1e-50"` is too small and becomes 0. Under strict IEEE 754 terminology, the *underflow* signal relates to tiny magnitude and loss of accuracy; in application programming, "underflow" is often used more broadly to mean the result enters the subnormal region or rounds to 0. When writing test documentation, separate **SUBNORMAL** and **ROUNDED_TO_ZERO** clearly rather than treating them as identical.

### Why `result == 0.0` is not enough to detect underflow

Both strings:

```java
Double.parseDouble("0.0");
Double.parseDouble("1e-4000");
```

return `0.0`, yet **their origins differ**. From the final `double` value alone, you cannot tell with certainty whether the original input was 0 or a nonzero number that underflowed. To detect this, keep the original string and inspect the source value with sufficient range/precision.

## 6. How does `NumberFormatException` differ from overflow/underflow?

The parsers accept strings conforming to the syntax supported by Java. If a string **does not have a valid form**, the parser typically throws `NumberFormatException`. For example:

```java
Double.parseDouble("not-a-number"); // NumberFormatException
Double.parseDouble("1_000.0");      // NumberFormatException
```

Underscores in Java literals like `1_000.0` are **source-code** syntax, and do not automatically become string syntax accepted by `Double.parseDouble`.

Some valid strings can surprise beginners:

| String | `Double.parseDouble` | Why |
| --- | --- | --- |
| `"0.5"` | `0.5` | Exact binary fraction |
| `"0.1"` | Prints `0.1`, but binary-rounded | Finite, does not represent the source decimal exactly |
| `"9007199254740993"` | `9.007199254740992E15` | Value exceeds `double`'s exact consecutive integer range |
| `"1e400"` | `Infinity` | Overflow |
| `"-1e400"` | `-Infinity` | Overflow |
| `"1e-4000"` | `0.0` | Rounded down to 0 because it is too small |
| `"1e-320"` | `1.0E-320` | Finite, nonzero subnormal value |
| `"Infinity"` | `Infinity` | Token supported by the parser |
| `"NaN"` | `NaN` | Token supported by the parser |
| `"0x1.8p1"` | `3.0` | Hex floating-point syntax |
| `"1_000.0"` | `NumberFormatException` | `_` is invalid in parser strings |
| `"1,5"` | `NumberFormatException` | Not `parseDouble` decimal syntax |

`Double.parseDouble(" 1.25 ")` is accepted after trimming whitespace characters per the parser's rules, but **do not infer that all locale formats are accepted**. Inputs using a comma as a decimal separator or thousands grouping require a specifically configured locale-aware parser. For `null` input, the API may throw `NullPointerException`, which is not how overflow is reported.

Also distinguish `Integer.parseInt("99999999999999999999")` from `Double.parseDouble` on very large numbers: integer parsers can throw `NumberFormatException` for exceeding `int` range, whereas floating-point parsers can return `Infinity` when a finite decimal value is too large. Do not apply integer-parser error-reporting rules to floating-point parsers.

## 7. Complete Java 17 demo: four outcomes from valid strings

Create the file `FloatingParseDemo.java`:

```java
import java.math.BigDecimal;

public class FloatingParseDemo {
    public static void main(String[] args) {
        double preciseHalf = Double.parseDouble("0.5");
        double roundedDecimal = Double.parseDouble("0.1");

        System.out.println("half = " + preciseHalf);
        System.out.println("decimal printed = " + roundedDecimal);
        System.out.println("decimal exact binary value = "
                + new BigDecimal(roundedDecimal));

        double roundedInteger = Double.parseDouble("9007199254740993");
        double adjacentInteger = Double.parseDouble("9007199254740992");
        System.out.println("large integer = " + roundedInteger);
        System.out.println("two parsed integers equal = "
                + (roundedInteger == adjacentInteger));

        System.out.println("double overflow = "
                + Double.parseDouble("1e400"));
        System.out.println("negative overflow = "
                + Double.parseDouble("-1e400"));
        System.out.println("float overflow = "
                + Float.parseFloat("3.5e38"));

        double tiny = Double.parseDouble("1e-4000");
        double negativeTiny = Double.parseDouble("-1e-4000");
        System.out.println("double underflow = " + tiny);
        System.out.println("negative underflow bits = "
                + Long.toHexString(
                        Double.doubleToRawLongBits(negativeTiny)));
        System.out.println("double subnormal = "
                + Double.parseDouble("1e-320"));
        System.out.println("float underflow = "
                + Float.parseFloat("1e-50"));
        System.out.println("float subnormal = "
                + Float.parseFloat("1e-44"));

        System.out.println("hex floating point = "
                + Double.parseDouble("0x1.8p1"));
        System.out.println("explicit infinity = "
                + Double.isInfinite(Double.parseDouble("Infinity")));
        System.out.println("explicit NaN = "
                + Double.isNaN(Double.parseDouble("NaN")));

        try {
            Double.parseDouble("1_000.0");
            System.out.println("unexpected success");
        } catch (NumberFormatException ex) {
            System.out.println("invalid syntax: NumberFormatException");
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac FloatingParseDemo.java
java FloatingParseDemo
```

Output:

```text
half = 0.5
decimal printed = 0.1
decimal exact binary value = 0.1000000000000000055511151231257827021181583404541015625
large integer = 9.007199254740992E15
two parsed integers equal = true
double overflow = Infinity
negative overflow = -Infinity
float overflow = Infinity
double underflow = 0.0
negative underflow bits = 8000000000000000
double subnormal = 1.0E-320
float underflow = 0.0
float subnormal = 9.8E-45
hex floating point = 3.0
explicit infinity = true
explicit NaN = true
invalid syntax: NumberFormatException
```

The output above clarifies four states: an exactly representable value (`0.5`), a rounded value (`0.1` or a large integer), overflow to infinity (`1e400`), and underflow to 0 or a subnormal number. Only the last case in the example — a string containing `_` — causes the parser to report a syntax error.

## 8. Post-parse checks: `isFinite`, `isInfinite`, `isNaN`, and subnormal classification

If the data contract accepts only **finite numbers**, check *after* parsing:

```java
static double parseFiniteDouble(String text) {
    double result = Double.parseDouble(text);

    if (!Double.isFinite(result)) {
        throw new IllegalArgumentException(
                "Expected a finite number: " + text);
    }

    return result;
}
```

This is a standalone method snippet that can be placed inside a Java class. It excludes both `NaN` and infinities, whether they came from explicit tokens or overflow. However, it does **not** detect precision loss from rounding or nonzero numbers rounded to `0.0`, because 0 and subnormals are still finite values.

For positive/negative nonzero finite values:

```java
static boolean isSubnormal(double x) {
    return Double.isFinite(x)
            && x != 0.0
            && Math.abs(x) < Double.MIN_NORMAL;
}
```

The method above checks **whether a resulting value lies in the subnormal region**, not whether the source string was rounded. Some subnormals accurately described by an appropriate binary or decimal form can still be represented exactly.

If the application domain forbids subnormal results due to precision limitations, reject them explicitly; do not assume `Double.isFinite` already covers this requirement.

### Be careful with negative zero

`-0.0` is finite and `-0.0 == 0.0` is `true`. When the sign needs to be distinguished:

```java
double x = Double.parseDouble("-1e-4000");
boolean negativeZero =
        Double.doubleToRawLongBits(x)
        == Double.doubleToRawLongBits(-0.0);
```

There are two cases that yield the same `-0.0`: the string genuinely described negative zero (`"-0.0"`) or a nonzero negative number underflowed. Reading the sign bit only shows the **final state**; it cannot recover the cause.

## 9. Detecting whether rounding occurred requires keeping the source value

After `Double.parseDouble("0.1")` returns a `double`, the result no longer carries full information about the original string. `Double.toString(result)` prints a short representation that round-trips to the same value, **not** an indication that the source decimal was preserved with absolute exactness.

For a **purely decimal** input within the range that `BigDecimal(String)` can parse, you can compare the exact original decimal value against the **exact binary value** that was parsed:

```java
import java.math.BigDecimal;

BigDecimal source = new BigDecimal("0.1");
double parsed = Double.parseDouble("0.1");

// The BigDecimal(double) constructor preserves the exact existing binary value.
// It is used here for diagnostics, not for initializing currency amounts.
BigDecimal storedExactly = new BigDecimal(parsed);

boolean unchanged = source.compareTo(storedExactly) == 0;
// unchanged is false: decimal 0.1 differs from the binary value of parsed.
```

For `"0.5"`, the two values are equal because `1/2` has a finite binary representation. For `"9007199254740993"`, the results differ because integer rounding occurred. You must ensure `parsed` is finite before calling `new BigDecimal(parsed)` because that constructor does not accept infinity or `NaN`.

**Special note:** `BigDecimal.valueOf(parsed)` is not equivalent to `new BigDecimal(parsed)` in the diagnostic task above. `valueOf(double)` uses the decimal representation from `Double.toString`, which suits many ordinary needs but can print `0.1` again and **mask the difference** between the binary number and the exact decimal. Use `new BigDecimal(double)` **only when you need to see the entire exact binary value**; for money or exact decimal inputs, prefer `new BigDecimal(String)`.

### Simple classification for decimal input

If the input contract accepts only finite decimal numbers written as strings, a diagnostic algorithm can work as follows:

1. Parse the source value with `new BigDecimal(text)` to retain the exact decimal value.
2. Parse to `double` using `Double.parseDouble(text)`.
3. If the result is infinite → **overflow** (since `"Infinity"`/`"NaN"` tokens were already excluded in step 1).
4. If the source is nonzero while the result is `0.0` or `-0.0` → **underflow to zero**.
5. If the result is nonzero and has magnitude less than `Double.MIN_NORMAL` → the output value is **subnormal**; you can compare further to tell whether it is exact or rounded.
6. If the result is finite, use `source.compareTo(new BigDecimal(parsed))` to check **whether rounding occurred** compared to the source decimal value.

Applied examples:

| Decimal string | Target value | Conclusion |
| --- | --- | --- |
| `"0.5"` | `0.5` | Exact |
| `"0.1"` | Value near `0.1` | Finite but rounded |
| `"9007199254740993"` | `9007199254740992` | Integer value rounded |
| `"1e400"` | `Infinity` | Overflow |
| `"1e-4000"` | `0.0` | Underflow to 0 |
| `"1e-320"` | Subnormal near `1e-320` | Subnormal; further error inspection needed to know if exact |

This approach is a **diagnostic for decimal sources**, not a general parser for hex strings, `"Infinity"`/`"NaN"` tokens, or arbitrarily huge inputs: `BigDecimal(String)` has its own syntax domain and exponent/scale limits, and can consume significant resources on excessively large strings. Set appropriate input size limits.

## 10. Choosing numeric types and handling policies by problem

| Requirement | Recommendation |
| --- | --- |
| Accept only strings with Java floating-point syntax | `Float.parseFloat` / `Double.parseDouble`, catch `NumberFormatException` |
| Require all results to be **finite** | After parsing, use `Float.isFinite` / `Double.isFinite` |
| Explicitly forbid `NaN` and infinity | Use `isNaN`/`isInfinite` or `isFinite`; report a specific business error message |
| Detect nonzero numbers that parsed to 0 | Keep and inspect the **pre-rounding source**, e.g., `BigDecimal(String)` for decimals |
| Detect/block the subnormal region | Check finite, nonzero, and `abs(x) < MIN_NORMAL` |
| Exact decimals such as monetary amounts | `BigDecimal(String)` with appropriate rounding/arithmetic rules |
| Store large integers distinguishing every unit | `long` / `BigInteger`, do not convert to `double` as keys |
| Strict JSON/API integration | Clearly specify allowed numeric syntax, whether NaN/Infinity is allowed, value thresholds, and how overflow/underflow is reported |
| Binary scientific computing | Use `double`/`float` if precision is adequate; check arithmetic errors and result range |

A reliable input pipeline should have **three validation layers**:

**(1) Syntax:** does the string conform to the grammar supported by the application? This may differ from Java's broad grammar, since many protocols forbid `"NaN"`, `"Infinity"`, or hex number forms.

**(2) Range and finiteness:** is the result within the business domain and finite? Check after parsing and consider how to detect overflow.

**(3) Precision:** is rounding deviation acceptable? If not, keep the original data and use an appropriate numeric type; do not expect the parser to report every precision loss automatically.

### Why `try/catch NumberFormatException` is not enough

```java
try {
    double value = Double.parseDouble(text);
    // Must continue validating value per the application contract.
} catch (NumberFormatException ex) {
    // Handles only invalid syntax; does not represent all precision loss.
}
```

If `text = "1e400"`, the `catch` block does not run even though `value == Infinity`; if `text = "1e-4000"`, the `catch` block also does not run even though the nonzero source value is rounded to 0. A system that accepts those results without checking can introduce hard-to-detect bugs.

## 11. Common mistakes

1. **Confusing successful parsing with preserving the value.** The parser can round a syntactically valid finite number.
2. **Thinking floating-point overflow throws `NumberFormatException`.** Valid strings exceeding the upper bound can return `Infinity`.
3. **Thinking underflow is always 0.** The subnormal region still contains many nonzero values.
4. **Thinking `MIN_VALUE` is the most negative number.** For `Float`/`Double`, it is the smallest nonzero positive number.
5. **Looking at `Double.toString(0.1)` and concluding binary stores 0.1 exactly.** That is a short string capable of round-tripping to the same `double`.
6. **Using `BigDecimal.valueOf(double)` to check whether the source decimal was preserved exactly.** It does not reflect the full exact binary value and can mask differences; this diagnostic purpose requires `new BigDecimal(double)` on finite inputs.
7. **Converting the source to `double` and only then wrapping in `BigDecimal`.** Already lost information does not recover on its own.
8. **Using `result == 0` to conclude the original string represented 0.** It could be a nonzero number that underflowed.
9. **Using `isFinite(result)` to conclude no rounding occurred.** Finiteness and exactness are two different properties.
10. **Using floating-point numbers as large integer IDs.** Distinct integer values can parse to the exact same `double`.
11. **Assuming the string parser accepts every Java literal.** Source literals with `_` are not accepted that way by `parseDouble`; protocol/locale syntax can also differ.
12. **Ignoring `-0.0`.** Losing magnitude can still preserve the sign, affecting some operations and bit representations.
13. **Comparing the input string character-by-character against `Double.toString`.** An exact decimal value may print in a different form without changing the number; conversely, matching short strings does not prove the binary number equals the mathematical decimal value.
14. **Validating only finite inputs while ignoring subsequent calculations.** Overflow/underflow can also arise during internal arithmetic.
15. **Applying `BigDecimal` unconditionally to extremely long strings.** Length and exponent-size limits are needed to guard against excessive resource consumption.

## 12. Exercises with answers

**Question 1.** Does `Double.parseDouble("1e400")` throw `NumberFormatException`? What is the result?

**Answer:** No. The string has valid syntax and represents a mathematically finite value that is too large for the finite `double` range, so the parser returns `Infinity`.

**Question 2.** Can you distinguish the results of `Double.parseDouble("0")` and `Double.parseDouble("1e-4000")` if you keep only the two returned `double` values?

**Answer:** No. Both can equal `+0.0`. To know the second number was originally nonzero, you must retain and inspect the source string before information is lost.

**Question 3.** Why do `Float.parseFloat("0.1")` and `Double.parseDouble("0.1")` not store the exact real number `1/10`?

**Answer:** `0.1` has no finite binary representation. Both `float` and `double` must choose a nearby value on their representation grid. `double` has higher significand precision so it is usually closer.

**Question 4.** Does the string `"1e-320"` parse to `0.0` in `double`?

**Answer:** Not for the given value: the parser returns a nonzero subnormal number (printing `1.0E-320`). It is smaller than `Double.MIN_NORMAL` yet larger than the minimum resolution near 0.

**Question 5.** If all parsed results must be finite, what condition should you use?

**Answer:** After `double x = Double.parseDouble(text)`, use `Double.isFinite(x)`. If it returns `false`, the data is `NaN` or infinity. However, this check does **not** guarantee no rounding or underflow to 0 occurred.

**Question 6.** When checking decimal discrepancy between `"0.1"` and the parsed `double` result, why does `new BigDecimal(parsed)` diagnose better than `BigDecimal.valueOf(parsed)`?

**Answer:** `new BigDecimal(parsed)` converts the **exact binary value** of a finite `double` into decimal, exposing the true deviation. `BigDecimal.valueOf(parsed)` relies on the short decimal form `Double.toString`, which can yield `"0.1"` and hide the discrepancy from the source mathematical value.

**Question 7.** Why can a syntactically valid integer string lose information when parsed with `Double.parseDouble`?

**Answer:** `double` has 53 bits of significand precision; it cannot consecutively represent every integer beyond `2^53`. For example, `"9007199254740993"` rounds to `9007199254740992` even though that number is far from the overflow threshold.

**Question 8.** `Double.parseDouble("-1e-4000")` can yield `-0.0`. What does `-0.0 == 0.0` return, and does it prove the negative sign is gone?

**Answer:** Primitive `==` comparison returns `true`, yet the negative sign bit still exists; `Double.doubleToRawLongBits` lets you observe the sign bit. `1.0/-0.0` produces `-Infinity`.

**Conclusion:** Floating-point parsers return **a value representable by `float`/`double`**, rather than promising to preserve every mathematical number in a string. Separate syntax errors from overflow, underflow, and rounding; check `isFinite` when required, distinguish subnormal numbers from 0, and keep the source value in an appropriate representation when exactness is mandatory.