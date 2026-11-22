# BigInteger, BigDecimal, and Floating-Point Representation Limits in Java

## 1. Why Care About Precision When Converting from String?

When receiving data as a `String`, such as a transaction ID `"9007199254740993"` or a monetary amount `"10.005"`, converting through `double` or `float` can **lose information before the program even starts computing**.

In Java:

- `BigInteger` represents **integers of arbitrary magnitude** at the API level; practical limits come from memory, array sizes, and computation cost. It preserves exact integer digits that `int`, `long`, or `double` cannot hold.
- `BigDecimal` represents **exact decimal values** via an unscaled integer (`unscaledValue`) and a `scale`; very useful when the input string is a monetary amount, rate, or decimal measurement needing explicit rounding rules.
- `float` and `double` are **binary floating-point numbers**, which can only represent a finite set of values exactly. Many familiar decimal fractions like `0.1` have no finite binary representation, even though the printed value may look like `0.1`.

**Guiding principle:** If a source string holds a decimal number requiring exactness, parse the **string directly** into `BigDecimal`; if it holds a large integer, parse directly into `BigInteger`. Avoid the round-trip `String → double → BigDecimal` or `String → double → BigInteger`, because information lost at the `double` step will not come back on its own.

## 2. Representation Models: Big Integers, Exact Decimals, and Binary Floating-Point

### 2.1. BigInteger: exact in the integer domain

`BigInteger` stores integers with arbitrary precision and provides operations like `add`, `subtract`, `multiply`, `divide`, `mod`, `pow`, etc. For example:

```java
BigInteger population = new BigInteger("9007199254740993");
BigInteger next = population.add(BigInteger.ONE);

System.out.println(next); // 9007199254740994
```

`new BigInteger("9007199254740993")` reads every digit of the string completely. `BigInteger` is **immutable**: `add` returns a new result object; the value of `population` is unchanged. For integer strings with a `-` sign, the constructor reads the negative sign properly; for different bases, you can use `new BigInteger(text, radix)`.

### 2.2. BigDecimal: decimal value = unscaled × 10^(-scale)

`BigDecimal` describes a value using the formula:

```text
value = unscaledValue × 10^(-scale)

"123.4500" → unscaledValue = 1234500, scale = 4
"1.23"    → unscaledValue = 123,     scale = 2
"1E+3"    → unscaledValue = 1,       scale = -3
```

Example:

```java
BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.unscaledValue()); // 1234500
System.out.println(amount.scale());         // 4
System.out.println(amount.toPlainString()); // 123.4500
```

`scale` is not the number of significant digits (`precision`). Two values `new BigDecimal("1.0")` and `new BigDecimal("1.00")` compare equal in **numerical value**, yet have different scales.

### 2.3. double: finite bits and binary rounding rules

`double` uses the standard IEEE 754 binary64 format, which has **53 bits of significand precision** (including the implicit bit). Thus, it represents **every integer with absolute value up to `2^53 = 9_007_199_254_740_992` exactly**. Beyond this threshold, **not every consecutive integer** can be represented accurately; this does not mean all numbers above the threshold are inaccurate.

`float` has 24 bits of significand precision, so its guaranteed limit for consecutive integers is `2^24 = 16_777_216`. Both also have **range** limits; precision and range are two distinct concepts.

Example:

```java
BigInteger original = new BigInteger("9007199254740993");
double rounded = original.doubleValue();

System.out.println(original);                            // 9007199254740993
System.out.println(BigDecimal.valueOf(rounded)
        .toPlainString());                                 // 9007199254740992
```

The value shifted to the adjacent integer after passing through `double`. Converting back to `BigInteger` or `BigDecimal` only retains **the rounded value**; the original number is unknown.

## 3. Parsing Directly from String to Preserve Data

### 3.1. Integer string → BigInteger

```java
String rawId = "9007199254740993";
BigInteger exactId = new BigInteger(rawId);

System.out.println(exactId);  // 9007199254740993
System.out.println(exactId.add(BigInteger.ONE));
// 9007199254740994
```

For hexadecimal:

```java
BigInteger hex = new BigInteger("FF", 16);
System.out.println(hex); // 255
```

The `BigInteger(String)` constructor requires valid integer syntax; `"1.5"`, `"1e3"`, or strings with extra whitespace are not valid decimal integer forms for this constructor. You may normalize with `strip()` if the data protocol allows leading/trailing whitespace; do not strip grouping or thousands separators automatically without a defined format.

### 3.2. Decimal string → BigDecimal

```java
String rawMoney = "0.10";
BigDecimal money = new BigDecimal(rawMoney);

System.out.println(money.toPlainString()); // 0.10
System.out.println(money.scale());         // 2
```

`BigDecimal(String)` preserves **the decimal value represented in the text** and its corresponding scale. There is no need to go through `Double.parseDouble(rawMoney)`. For `"00123.4500"`, the numeric value is stored accurately, but **original formatting details** such as leading `0`s are not preserved in `BigDecimal`; if you must restore the exact original string, store the input string separately.

Some valid and invalid cases:

| String | Handling |
| --- | --- |
| `"123456789012345678901234567890"` | `new BigInteger(text)` preserves the large integer accurately |
| `"-100.0250"` | `new BigDecimal(text)` preserves the decimal number and scale accurately |
| `"1.23E+4"` | `new BigDecimal(text)` accepts scientific notation |
| `"1,25"` | Not the dot-decimal syntax expected by the constructor; requires a locale-aware parser if data genuinely uses decimal commas |
| `"NaN"` or `"Infinity"` | Not finite decimal numbers for `BigDecimal(String)` |
| `" 42 "` | Must decide whether to `strip()` both ends or treat as invalid data |

`NumberFormatException` is the typical exception when a string is invalid. For user input, handle it explicitly rather than assuming every string parses successfully.

## 4. Difference Between new BigDecimal(0.1) and BigDecimal.valueOf(0.1)

Classic example:

```java
System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(BigDecimal.valueOf(0.1));
// 0.1

System.out.println(new BigDecimal("0.1"));
// 0.1
```

Three different cases:

1. `new BigDecimal(0.1)` receives **the binary64 value of the literal `0.1`**, i.e., the binary value closest to `0.1`. The constructor represents **the exact double value it received**, exposing the long tail.
2. `BigDecimal.valueOf(0.1)` relies on the decimal representation returned by `Double.toString(0.1)`, which here is `"0.1"`; hence the result is readable and the decimal value is `0.1`.
3. `new BigDecimal("0.1")` reads the decimal text directly, with no intermediate `double` step. This is the right choice when you need to preserve exact decimal numbers from source data.

**Warning about `valueOf(double)`:** It cannot recover information already lost in a prior `double` calculation:

```java
double sum = 0.1 + 0.2;

System.out.println(sum);                       // 0.30000000000000004
System.out.println(BigDecimal.valueOf(sum));   // 0.30000000000000004
System.out.println(new BigDecimal("0.1")
        .add(new BigDecimal("0.2")));           // 0.3
```

Therefore `BigDecimal.valueOf(double)` is useful when you are **forced** to interface with an API returning `double`, but it does not mean "perfectly convert a double back into the original decimal". If the original input is a `String`, parse it directly.

## 5. Exact, Truncating, and Lossy Conversions

### 5.1. BigInteger → int/long

`BigInteger.intValue()` and `BigInteger.longValue()` can **lose high-order bits** when the value does not fit the target type, without necessarily throwing an exception. When business logic requires integrity, use `intValueExact()` and `longValueExact()`:

```java
BigInteger small = new BigInteger("123");
System.out.println(small.intValueExact()); // 123

BigInteger oversized = new BigInteger("9223372036854775808");
// oversized.longValueExact() throws ArithmeticException
```

The value `9223372036854775808` is greater than `Long.MAX_VALUE` by exactly 1. Use `longValueExact()` to detect the issue before writing to a database table or calling an API that only accepts `long`. Likewise, do not use `Integer.parseInt(...)` or `Long.parseLong(...)` for strings that may exceed the respective ranges; they throw `NumberFormatException` on overflow.

### 5.2. BigDecimal → BigInteger: losing the fractional part

`BigDecimal.toBigInteger()` **truncates the fractional part toward zero**, without rounding `HALF_UP` and without throwing an error for having a fraction:

```java
System.out.println(new BigDecimal("99.9").toBigInteger()); // 99
System.out.println(new BigDecimal("-99.9").toBigInteger()); // -99
```

Conversely, `toBigIntegerExact()` throws `ArithmeticException` if the fractional part is non-zero. For example, `new BigDecimal("99.0").toBigIntegerExact()` is valid because the fractional part is 0, whereas `new BigDecimal("99.9").toBigIntegerExact()` is invalid.

To round before extracting an integer, choose an explicit policy:

```java
BigInteger rounded = new BigDecimal("99.9")
        .setScale(0, RoundingMode.HALF_UP)
        .toBigIntegerExact();
System.out.println(rounded); // 100
```

### 5.3. BigDecimal → int/long

`intValue()` and `longValue()` may drop the fractional part and/or lose bits due to overflow. `intValueExact()` and `longValueExact()` throw `ArithmeticException` if there is a non-zero fractional part or if the integer part does not fit the target type. Use the `Exact` versions at the boundaries of APIs requiring fixed-width integer types.

### 5.4. BigInteger/BigDecimal → float/double

`doubleValue()` and `floatValue()` are **potentially lossy** conversions. If the magnitude exceeds the binary floating-point range, the result can be `Infinity` or `-Infinity`; if the value is too small (for `BigDecimal`), conversion may round to `0.0`. Do not use `doubleValue()` for identifiers, monetary amounts, or comparisons requiring exactness.

There is no guarantee that `new BigDecimal(...).doubleValue()` followed by `BigDecimal.valueOf(...)` will preserve the original `BigDecimal`.

## 6. Standalone Runnable Java 17+ Example

Create file **`BigNumbersFromStringDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class BigNumbersFromStringDemo {
    public static void main(String[] args) {
        BigInteger id = new BigInteger("9007199254740993");
        System.out.println("integer exact = " + id);
        System.out.println("double roundtrip = "
                + BigDecimal.valueOf(id.doubleValue()).toPlainString());

        System.out.println("new BigDecimal(0.1) = " + new BigDecimal(0.1));
        System.out.println("valueOf(0.1) = " + BigDecimal.valueOf(0.1));

        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("double sum = " + binarySum);
        System.out.println("decimal sum = " + decimalSum);

        BigDecimal rounded = new BigDecimal("10.005")
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println("round = " + rounded);

        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"), 4, RoundingMode.HALF_UP);
        System.out.println("third = " + third);

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal anotherOne = new BigDecimal("1.00");
        System.out.println("equals = " + one.equals(anotherOne));
        System.out.println("compareTo = " + one.compareTo(anotherOne));

        BigDecimal fractional = new BigDecimal("99.9");
        System.out.println("truncated = " + fractional.toBigInteger());
        try {
            fractional.toBigIntegerExact();
        } catch (ArithmeticException ex) {
            System.out.println("fraction rejected");
        }

        System.out.println("plain = " + new BigDecimal("1000.00")
                .stripTrailingZeros().toPlainString());
        System.out.println("scientific = " + new BigDecimal("1000.00")
                .stripTrailingZeros().toString());
    }
}
```

Compile and run commands:

```bash
javac --release 17 BigNumbersFromStringDemo.java
java BigNumbersFromStringDemo
```

Expected stdout (expressions verified with the JDK, using APIs available on Java 17):

```text
integer exact = 9007199254740993
double roundtrip = 9007199254740992
new BigDecimal(0.1) = 0.1000000000000000055511151231257827021181583404541015625
valueOf(0.1) = 0.1
double sum = 0.30000000000000004
decimal sum = 0.3
round = 10.01
third = 0.3333
equals = false
compareTo = 0
truncated = 99
fraction rejected
plain = 1000
scientific = 1E+3
```

Explanation:

- `id` is read accurately from `String`. Passing through `doubleValue()` turns `9007199254740993` into `9007199254740992`: off by exactly 1 unit.
- `new BigDecimal(0.1)` expresses the exact **binary64** value approximating `0.1`; `valueOf(0.1)` picks the corresponding short decimal string. `new BigDecimal("0.1")` does not go through binary64.
- Adding two `BigDecimal`s created from strings yields `0.3`; adding doubles yields `0.30000000000000004`.
- `setScale(2, HALF_UP)` rounds `10.005` to `10.01`. `1 / 3` requires a scale and rounding mode because it has no exact finite decimal representation.
- `equals` compares both value and scale, so `1.0` differs from `1.00` under `equals`. `compareTo` compares numerical value, returning `0`.
- `toBigInteger` truncates the fractional part; `toBigIntegerExact` guards against silently dropping fractions.
- `stripTrailingZeros()` can make the scale negative, so `toString()` prints `1E+3`; `toPlainString()` prints `1000`.

## 7. Scale, Precision, and Rounding in BigDecimal

### 7.1. Scale differs from precision

`scale` indicates the decimal point position by powers of 10. `precision()` indicates the **number of significant digits** of the unscaled value. For example:

```java
BigDecimal x = new BigDecimal("12.3400");
System.out.println(x.scale());     // 4
System.out.println(x.precision()); // 6
```

Mathematical precision and number of displayed digits are separate concerns: `"1.00"` and `"1.0"` are equal in value, but have different scales.

### 7.2. Choosing a rounding policy explicitly

`setScale(targetScale, mode)` changes the scale and may round:

```java
BigDecimal price = new BigDecimal("10.005");

System.out.println(price.setScale(2, RoundingMode.HALF_UP));  // 10.01
System.out.println(price.setScale(2, RoundingMode.HALF_EVEN)); // 10.00
```

`HALF_UP` rounds away from zero on exact ties (such as positive 10.005 at scale 2), whereas `HALF_EVEN` chooses the even final digit on exact ties. Which policy is right depends on the system's calculation rules; there is no single rounding mode always right for every currency and tax rule.

If rounding is strictly **forbidden**, use `RoundingMode.UNNECESSARY`. Whenever a significant digit would have to be discarded, the operation throws `ArithmeticException`.

### 7.3. Non-terminating division

`new BigDecimal("1").divide(new BigDecimal("3"))` throws `ArithmeticException` because `1/3` has no finite decimal representation. Specify scale + rounding, or use `MathContext`:

```java
BigDecimal a = new BigDecimal("1");
BigDecimal b = new BigDecimal("3");

System.out.println(a.divide(b, 2, RoundingMode.HALF_UP)); // 0.33

MathContext mc = new MathContext(5, RoundingMode.HALF_EVEN);
System.out.println(a.divide(b, mc)); // 0.33333
```

`MathContext(5, ...)` limits to **5 significant digits (precision)**, not 5 digits after the decimal point (scale). Remember `import java.math.MathContext;` when using this snippet in a separate class.

### 7.4. Comparing values and keys in collections

`BigDecimal.equals` considers both value and scale, whereas `compareTo` considers only numerical ordering:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

As a result, `HashSet<BigDecimal>` and `TreeSet<BigDecimal>` may disagree on whether these two values are duplicates, due to their different equality rules. Define a scale normalization policy and comparison policy before using them in maps, sets, or business keys.

## 8. Converting Exact Numbers Back to String

| API | Result / meaning |
| --- | --- |
| `bigInteger.toString()` | Exact decimal integer text |
| `bigInteger.toString(16)` | Text in base 16, without losing value |
| `bigDecimal.toString()` | Canonical form of the object, may contain scientific notation `E` |
| `bigDecimal.toPlainString()` | Decimal form without exponent |
| `bigDecimal.toEngineeringString()` | May use powers of 10 with exponents that are multiples of 3 |
| `bigDecimal.stripTrailingZeros()` | Removes trailing `0`s; may change scale and how `toString()` displays it |

Example:

```java
BigDecimal raw = new BigDecimal("1000.00");

System.out.println(raw.toPlainString()); // 1000.00
System.out.println(raw.stripTrailingZeros().toString()); // 1E+3
System.out.println(raw.stripTrailingZeros().toPlainString()); // 1000
```

If input data requires a **fixed display format of two decimal places**, you can use `setScale(2, roundingMode)` before output, but only after defining the rounding rule. Do not conflate preserving **numerical value** with preserving **the verbatim input string** (`+` signs, leading `0`s, `E` notation, grouping separators). Store the original string if those details are required.

## 9. Conversion Flows to Use and to Avoid

### 9.1. Correct: String → BigInteger/BigDecimal → exact arithmetic

```text
"9007199254740993" --BigInteger(String)--> 9007199254740993
"0.1" --BigDecimal(String)--> decimal 0.1
"0.2" --BigDecimal(String)--> decimal 0.2
decimal 0.1 + decimal 0.2 --> decimal 0.3
```

No intermediate conversion through `float` or `double`. Use `BigDecimal` for monetary amounts requiring decimal units, and `BigInteger` for large integers with no fractional part.

### 9.2. Potentially lossy: String → double → BigDecimal

```text
"9007199254740993"
    -> Double.parseDouble(...)
    -> 9007199254740992 (rounded)
    -> BigDecimal.valueOf(...) = 9007199254740992
```

Even if converted afterward into `BigInteger`, the original number is already lost. If you already receive a `double` from an external system, you must accept and document the input precision of that system; `BigDecimal` cannot "fix" calculation history.

### 9.3. Potentially lossy: BigDecimal → BigInteger, long, or double

- `toBigInteger()` drops the fractional part.
- `longValue()` may truncate the fractional part or lose bits.
- `doubleValue()` may round, overflow to Infinity, or underflow very small values.
- Use `toBigIntegerExact()` / `longValueExact()` when you need to reject inputs that cannot be preserved.

### 9.4. When forced to work with float/double

Some scientific libraries and legacy APIs accept `double`; when converting, check range, finiteness (`Double.isFinite(value)`), and acceptable precision. `BigDecimal.valueOf(Double.NaN)` / `BigDecimal.valueOf(Double.POSITIVE_INFINITY)` cannot create a finite `BigDecimal` object and throw `NumberFormatException`.

If financial logic requires absolute accuracy in the smallest unit, consider an **integer minor-unit model** (`BigInteger` or `long` with sufficient range) or `BigDecimal` with a uniformly defined scale and rounding policy.

## 10. Common Mistakes

1. **Parsing to double first and then creating BigDecimal.** `new BigDecimal(Double.parseDouble(text))` may hold a binary approximation; `BigDecimal.valueOf(Double.parseDouble(text))` also cannot recover all digits if the double already rounded. Use `new BigDecimal(text)`.
2. **Using BigDecimal.valueOf(0.1) and concluding double addition is exact.** `valueOf` only converts the representation of an existing double value; `valueOf(0.1 + 0.2)` still yields `0.30000000000000004`.
3. **Using double for large IDs/counters.** Once integers exceed the exact consecutive representation threshold, two distinct values can collapse into the same double. Keep them as `String` or `BigInteger`.
4. **Using BigInteger to represent fractions.** `new BigInteger("12.34")` throws `NumberFormatException`. Use `BigDecimal` if fractions are needed.
5. **Believing `BigInteger.longValue()` is always exact.** On overflow, the conversion can lose bits. Use `longValueExact()` when data loss is an error.
6. **Believing `BigDecimal.toBigInteger()` rounds.** It truncates the fractional part toward zero. Choose `setScale(0, mode)` first, or use `toBigIntegerExact()`.
7. **Calling `divide` without specifying a division rule.** For non-terminating fractions like `1/3`, the default throws `ArithmeticException`. Specify `scale`/`RoundingMode` or `MathContext`.
8. **Confusing `equals` and `compareTo`.** `1.0` and `1.00` have the same numerical value, yet `equals` returns false. Be careful when using them as collection keys.
9. **Confusing precision with scale.** `MathContext(5)` does not mean keeping 5 decimal places; it means 5 significant digits.
10. **Expecting BigDecimal to preserve input formatting.** `"0001.2300"` can preserve decimal scale, but not leading `0`s. Store the original string separately if character restoration is needed.
11. **Ignoring invalid input.** Strings with whitespace, locale commas, NaN, or malformed exponents can throw `NumberFormatException`. Define valid syntax up front.
12. **Assuming BigInteger/BigDecimal are "infinite" in memory or speed.** They still consume resources proportional to number length and operation complexity; bound input sizes, especially when accepting untrusted data.

## 11. Self-Check Exercises

**Exercise 1 — Preserve a large integer from a string.**

The input `"9007199254740993"` needs `1` added without losing digits. Write:

```java
BigInteger result = new BigInteger("9007199254740993")
        .add(BigInteger.ONE);
System.out.println(result); // 9007199254740994
```

Do not cast through `double` at any step.

**Exercise 2 — Sum decimal monetary amounts.**

Given two strings `"0.10"` and `"0.20"`, the desired result is `0.30`:

```java
BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");

BigDecimal total = a.add(b);
System.out.println(total.toPlainString()); // 0.30
```

The scale of a standard sum matches the larger scale of the two operands in this example. If formatting with two decimal places is required for other inputs, set an explicit scale/rounding policy.

**Exercise 3 — Reject fractional loss.**

The input `"42.1"` needs to be converted to an integer, but must report an error if there is a fractional part:

```java
BigDecimal input = new BigDecimal("42.1");
// input.toBigIntegerExact() will throw ArithmeticException.
```

Do not choose `toBigInteger()`, because it silently returns `42`.

**Exercise 4 — Compare two monetary values.**

Why does `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` return false while `compareTo` returns 0? Because `equals` considers scale as well, whereas `compareTo` considers numerical value. Choose one criterion fitting the business logic and stay consistent.

**Exercise 5 — Spot an incorrect conversion flow.**

```java
String source = "9007199254740993";
double d = Double.parseDouble(source);
BigDecimal x = BigDecimal.valueOf(d);
```

`x` cannot equal the exact value in `source`: `double` already rounded it to `9007199254740992`. The fix is `new BigDecimal(source)`, or `new BigInteger(source)` if the data is an integer.

## 12. Key Takeaways

`BigInteger` is for **exact integers beyond the range of primitive integer types**; `BigDecimal` is for **exact decimal values and explicit scale/rounding policies**. When the source is a `String`, parse directly to the desired type. `float`/`double` have bit limits, range limits, and can lose digits; going through them can make converting to `BigInteger`/`BigDecimal` unable to preserve the original data. Before any potentially lossy conversion, use `Exact` methods or make an explicit rounding decision.

**Official documentation:** [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html), [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).