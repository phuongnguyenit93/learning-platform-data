# Why `new BigDecimal(double)` Differs from `new BigDecimal(String)` in Java

When you write `new BigDecimal(0.1)`, Java does **not** directly receive the exact decimal number "one-tenth." The literal `0.1` is first processed by the compiler into a binary `double` value, and the constructor taking `double` converts **that exact stored binary value** into `BigDecimal`'s decimal representation. By contrast, `new BigDecimal("0.1")` reads the decimal string directly, so it represents **exact decimal 0.1**.

This is not merely a printing difference: the two objects can **differ in mathematical value**, differ in `scale`, and lead to different results in `equals`, `compareTo`, addition, subtraction, or rounding.

This lesson belongs to the **Floating-Point Parsing** group of Java Core. We will separate the three ways to construct a `BigDecimal` — from `double`, from `String`, and from `BigDecimal.valueOf(double)` — and then examine their impact on data parsing, rounding, monetary calculations, and real-world input handling.

## 1. Key example: both show “0.1” yet store different numbers

~~~java
double d = 0.1;

BigDecimal fromDouble = new BigDecimal(d);
BigDecimal fromString = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(d);

System.out.println(fromDouble);
// 0.1000000000000000055511151231257827021181583404541015625
System.out.println(fromString);
// 0.1
System.out.println(fromValueOf);
// 0.1
~~~

Step-by-step exact explanation:

1. The source literal `0.1` is converted into an IEEE 754 binary64 `double` bit pattern. The fraction `1/10` has no finite representation in base 2; the `double` bit pattern holds **a number close to 0.1**, not mathematically exact 0.1.
2. `new BigDecimal(d)` creates a decimal number **equal to the rounded binary64 value** stored in `d`. It does not guess the original "intent" of 0.1.
3. `new BigDecimal("0.1")` parses the decimal digits in the string `"0.1"`; its value is exact `1/10`.
4. `BigDecimal.valueOf(d)` uses the decimal representation via `Double.toString(d)` and creates the corresponding `BigDecimal`. For `d = 0.1`, that string is `"0.1"`, so the result matches the string constructor in this case.

Numerically: the value of `new BigDecimal(0.1)` is **greater than** `new BigDecimal("0.1")` by approximately `5.55 × 10^-18`. The `Double.toString(0.1)` form is only meant to allow reading back the exact binary `double` value; it **does not** claim the stored bit pattern corresponds to exact decimal 0.1.

A `double` is a numeric value; a `String` is characters passed by a user, file, or API. They carry different levels of information, so the constructors produce different results.

## 2. Background: decimal and binary represent fractions differently

A decimal number such as `0.5` = `1/2` has a finite representation in both base 10 and base 2. However, `0.1` = `1/10` = `1/(2 × 5)` has a factor of 5 in its denominator, so its binary representation is an infinite repeating sequence that must be truncated/rounded in binary64.

The `double` type typically preserves about 15–17 significant decimal digits, with **53 bits of significand precision**. That suffices for many scientific, graphics, and computational applications, yet does not make every decimal fraction exact.

| Value/expression | What to understand |
| --- | --- |
| `double d = 0.5` | Can store exact `1/2` in binary64 |
| `double d = 0.1` | Stores a binary number close to 0.1 |
| `System.out.println(0.1)` | Prints `0.1` — a short round-trip decimal form, not the full mathematical value of the bits |
| `new BigDecimal(0.1)` | Preserves the exact value of the `double` bits and prints a long string |
| `new BigDecimal("0.1")` | Preserves the exact decimal value described by the string |
| `BigDecimal.valueOf(0.1)` | Based on `Double.toString(0.1)`, so it creates `BigDecimal` equal to 0.1 in this case |

In its internal storage representation, `BigDecimal` consists of an **unscaled integer** (an arbitrary-length integer) and a **scale** (decimal digit position as a power of ten): the value equals `unscaledValue × 10^(-scale)`. For example, `new BigDecimal("0.1")` has unscaled value 1 and scale 1.

`BigDecimal` **is not limited to 53 bits of precision like `double`**, yet still requires scale/precision/rounding policies when operations produce long or non-terminating results, especially division.

## 3. Three ways to construct BigDecimal: different contracts

### Approach A — constructor taking `double`

~~~java
BigDecimal exactStoredDouble = new BigDecimal(0.1);
~~~

Contract: represent **the exact floating-point value stored in the `double` argument** in decimal form. This constructor is useful when you deliberately need to inspect a binary64 value, store exact existing numeric content, or handle bit/floating-point conversions per specific requirements.

It is generally **not** suitable when you want to create a monetary price of `0.10` from the literal `0.1`. The issue is not that the constructor malfunctions: it faithfully converts an existing `double` to `BigDecimal` **without rounding back to decimal intent**.

### Approach B — constructor taking `String`

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal amount = new BigDecimal("19.99");
BigDecimal measured = new BigDecimal("1.2300");
~~~

Contract: parse valid text into an **exact decimal number** and record the scale from the string representation. For example, `"1.2300"` has scale 4, whereas `"1.23"` has scale 2, even though they are equal in decimal value.

If data arrives from JSON/CSV/user forms as a reliable decimal string, **avoid converting the string to `double` first and only then creating `BigDecimal`**:

~~~java
String input = "19.99";
BigDecimal correct = new BigDecimal(input);

// Avoid if you need to preserve the exact decimal from input:
BigDecimal potentiallyDifferent =
        new BigDecimal(Double.parseDouble(input));
~~~

The second approach already passed through an approximated binary64 number before the `double` constructor was called. At that point `BigDecimal` can only preserve the **post-approximation value**, with no knowledge of which decimal number the user meant to enter.

### Approach C — factory `BigDecimal.valueOf(double)`

~~~java
double d = 0.1;
BigDecimal commonConversion = BigDecimal.valueOf(d);
~~~

Contract: uses the canonical string form of `Double.toString(d)` to construct a `BigDecimal`. For `d = 0.1`, it creates the number `0.1`; this avoids many unexpected "trailing" digits when converting an existing `double` value to decimal.

**However, `valueOf` does not fix errors that have already accumulated:**

~~~java
double sum = 0.1 + 0.2;             // 0.30000000000000004
BigDecimal fromSum = BigDecimal.valueOf(sum);
// fromSum is 0.30000000000000004, not 0.3
~~~

`Double.toString(sum)` is literally `"0.30000000000000004"`, because that is the form required to round-trip the sum's bit pattern. The factory cannot deduce that the original calculation was "supposed to be 0.3."

**Intent-based recommendation:** New exact decimal data should start from an appropriate `String`/`char[]` or `BigDecimal` source. When you already have a `double` and need to convert it to `BigDecimal` via its corresponding short decimal form, `BigDecimal.valueOf` is usually more convenient than the `double` constructor. When you need the exact current binary64 value, the `double` constructor is the deliberate choice.

## 4. Why can `equals` and `compareTo` give different results?

For `0.1`:

~~~java
BigDecimal a = new BigDecimal(0.1);
BigDecimal b = new BigDecimal("0.1");

boolean sameByEquals = a.equals(b);      // false
int numericOrder = a.compareTo(b);       // > 0
~~~

`a` is actually **numerically greater than b**, because `double 0.1` is rounded slightly above `1/10`. Hence neither `equals` nor `compareTo == 0` considers them equal.

A **separate** issue is scale:

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

boolean equalObjects = x.equals(y);    // false: scale 1 differs from scale 2
boolean equalValues = x.compareTo(y) == 0; // true: mathematical values are equal
~~~

- `BigDecimal.equals` considers two numbers equal when both **value and scale** match appropriately. This is object equality, important for `HashMap`/`HashSet`.
- `BigDecimal.compareTo` compares **numeric value** and considers `1.0` and `1.00` equal.
- `stripTrailingZeros` can normalize part of the decimal representation (`new BigDecimal("1.00").stripTrailingZeros()` prints `1`), yet changing scale does not fix the real value difference between `new BigDecimal(0.1)` and `new BigDecimal("0.1")`.

If using `BigDecimal` as a key, decide in the contract **whether scale is significant**. `HashSet<BigDecimal>` relies on `equals`, while `TreeSet<BigDecimal>` uses `compareTo` by default; the two collections can treat `1.0` and `1.00` differently. This is not a bug in the constructor, but the combination of *value* and *decimal representation*.

## 5. Rounding: a difference at construction can become a business difference

A classic example is rounding `1.005` to two decimal places using `RoundingMode.HALF_UP`:

~~~java
BigDecimal a = new BigDecimal(1.005);
BigDecimal b = new BigDecimal("1.005");
BigDecimal c = BigDecimal.valueOf(1.005);

System.out.println(a.setScale(2, RoundingMode.HALF_UP)); // 1.00
System.out.println(b.setScale(2, RoundingMode.HALF_UP)); // 1.01
System.out.println(c.setScale(2, RoundingMode.HALF_UP)); // 1.01
~~~

Because the binary64 value of the literal `1.005` is **slightly less than decimal 1.005**, the `double` constructor preserves that slightly smaller value, so HALF_UP rounding to two digits gives `1.00`. With the string constructor, the value is right at the midpoint `1.005`, so HALF_UP gives `1.01`.

This is why the same UI displaying `1.005` can produce different results in pricing/tax algorithms when passing through `double`. **Displayed digits do not prove exactness or the rounding policy.**

The `setScale` methods return a **new `BigDecimal`**, because `BigDecimal` is immutable. You must use the returned value rather than assuming calling the method mutates the existing object.

`RoundingMode.HALF_UP` is only one policy. Other domains may require `HALF_EVEN`, `DOWN`, `UP`, or special handling; define this clearly at the business level.

## 6. Complete Java 17+ program for side-by-side comparison

Save the file `BigDecimalConstructionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalConstructionDemo {
    public static void main(String[] args) {
        double d = 0.1;
        BigDecimal fromDouble = new BigDecimal(d);
        BigDecimal fromString = new BigDecimal("0.1");
        BigDecimal fromValueOf = BigDecimal.valueOf(d);

        System.out.println("double d = " + d);
        System.out.println("new BigDecimal(d) = " + fromDouble);
        System.out.println("new BigDecimal(\"0.1\") = " + fromString);
        System.out.println("BigDecimal.valueOf(d) = " + fromValueOf);
        System.out.println("double constructor equals string = "
                + fromDouble.equals(fromString));
        System.out.println("valueOf equals string = "
                + fromValueOf.equals(fromString));
        System.out.println("double constructor compareTo string = "
                + fromDouble.compareTo(fromString));
        System.out.println("double constructor scale = " + fromDouble.scale());
        System.out.println("string constructor scale = " + fromString.scale());

        System.out.println("sum as double = " + (0.1 + 0.2));
        System.out.println("valueOf(double sum) = "
                + BigDecimal.valueOf(0.1 + 0.2));
        System.out.println("decimal string sum = "
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));

        System.out.println("new BigDecimal(1.005) rounded = "
                + new BigDecimal(1.005)
                .setScale(2, RoundingMode.HALF_UP));
        System.out.println("new BigDecimal(\"1.005\") rounded = "
                + new BigDecimal("1.005")
                .setScale(2, RoundingMode.HALF_UP));
        System.out.println("BigDecimal.valueOf(1.005) rounded = "
                + BigDecimal.valueOf(1.005)
                .setScale(2, RoundingMode.HALF_UP));

        System.out.println("equals 1.0 and 1.00 = "
                + new BigDecimal("1.0")
                .equals(new BigDecimal("1.00")));
        System.out.println("compareTo 1.0 and 1.00 = "
                + new BigDecimal("1.0")
                .compareTo(new BigDecimal("1.00")));
        System.out.println("stripTrailingZeros 1.00 = "
                + new BigDecimal("1.00").stripTrailingZeros());

        System.out.println("BigDecimal.valueOf(-0.0) = "
                + BigDecimal.valueOf(-0.0));
        System.out.println("new BigDecimal(\"-0.0\") = "
                + new BigDecimal("-0.0"));

        try {
            new BigDecimal(Double.NaN);
        } catch (NumberFormatException ex) {
            System.out.println("NaN constructor = NumberFormatException");
        }
        try {
            BigDecimal.valueOf(Double.POSITIVE_INFINITY);
        } catch (NumberFormatException ex) {
            System.out.println("Infinity valueOf = NumberFormatException");
        }
        try {
            new BigDecimal("0.1").divide(new BigDecimal("3"));
        } catch (ArithmeticException ex) {
            System.out.println("0.1 / 3 exact = ArithmeticException");
        }
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalConstructionDemo.java
java BigDecimalConstructionDemo
~~~

Exact stdout of the program:

~~~text
double d = 0.1
new BigDecimal(d) = 0.1000000000000000055511151231257827021181583404541015625
new BigDecimal("0.1") = 0.1
BigDecimal.valueOf(d) = 0.1
double constructor equals string = false
valueOf equals string = true
double constructor compareTo string = 1
double constructor scale = 55
string constructor scale = 1
sum as double = 0.30000000000000004
valueOf(double sum) = 0.30000000000000004
decimal string sum = 0.3
new BigDecimal(1.005) rounded = 1.00
new BigDecimal("1.005") rounded = 1.01
BigDecimal.valueOf(1.005) rounded = 1.01
equals 1.0 and 1.00 = false
compareTo 1.0 and 1.00 = 0
stripTrailingZeros 1.00 = 1
BigDecimal.valueOf(-0.0) = 0.0
new BigDecimal("-0.0") = 0.0
NaN constructor = NumberFormatException
Infinity valueOf = NumberFormatException
0.1 / 3 exact = ArithmeticException
~~~

Key takeaways from the output:

- `fromDouble.scale() == 55` while `fromString.scale() == 1`; those are two completely different decimal representations.
- `BigDecimal.valueOf(0.1)` and `new BigDecimal("0.1")` are equal in this example, **but do not generalize that `valueOf(double)` always recovers the intended decimal of every calculation**.
- `0.1 + 0.2` in `double` becomes `0.30000000000000004` before converting to `BigDecimal`; no constructor infers the intent of decimal addition backward.
- Two `1.005` rounding calls return different results because the input data differed beforehand.
- `BigDecimal` does not support NaN and infinity like `double`. Passing NaN or infinity to `BigDecimal` does not create a valid number, instead raising `NumberFormatException` in the example.
- `BigDecimal` number representation **does not keep a separate negative sign for the value 0**: `"-0.0"` when parsed yields value 0 with scale 1, printing `0.0`.

## 7. `valueOf(double)` is not a “cure” for arithmetic error

Consider two pipelines:

~~~java
double computed = 0.1 + 0.2;
BigDecimal convertedLater = BigDecimal.valueOf(computed);

BigDecimal computedAsDecimal = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
~~~

The result `convertedLater` is `0.30000000000000004`, while `computedAsDecimal` is exact `0.3`. You cannot take the result of an addition already rounded in binary64 and assume the factory knows the two original decimal numbers exactly.

Good practice for decimal data with strict calculation contracts:

1. Receive decimal numbers as original strings or `BigDecimal` right at the input layer; if strings, validate the format before constructing objects.
2. Perform calculations with `BigDecimal`'s `add`, `subtract`, `multiply`, and `divide` operations, without passing through `double` mid-way.
3. Specify precision/scale and `RoundingMode` at the exact business step where quantization is needed.
4. Output using `toPlainString`, `toString`, a formatter, or serialization per the receiver's contract; do not rely on arbitrary `double` digits.

If the source **provides only a `double`**, you cannot be certain of the human-intended decimal value from the stored bits. `BigDecimal.valueOf(d)` is usually a reasonable conversion based on `double`'s round-trip string; `new BigDecimal(d)` is the choice when you want the exact existing binary value. Document the policy explicitly instead of hiding the data's origin.

## 8. Things to watch out for when parsing a String to BigDecimal

`new BigDecimal(String)` requires a string with valid decimal number syntax, not just any number display string. For example:

~~~java
BigDecimal ok = new BigDecimal("-12.3400");
BigDecimal scientific = new BigDecimal("1.25E+3");

// new BigDecimal("12,34"); // NumberFormatException
// new BigDecimal("1_000"); // NumberFormatException
// new BigDecimal("");      // NumberFormatException
~~~

In Java code, `1_000` is a valid integer literal; in runtime text passed to `BigDecimal(String)`, underscores are **not** valid numeric characters. Strings containing thousands separators or language-specific decimal separators must be handled by a dedicated **locale contract** before invoking the parser, rather than arbitrarily deleting all commas.

Unlike `double`, `BigDecimal` can represent very large or very small decimals of arbitrary length (within resource bounds and internal scale/precision limits). Still, the constructor can throw `NumberFormatException` when data is syntactically invalid or exceeds processable structural limits.

Validate input, catch exceptions at communication boundaries, and provide appropriate business error messages rather than swallowing errors and substituting 0. For sensitive data, do not log the entire raw string verbatim unless necessary.

## 9. BigDecimal arithmetic still requires designing precision and rounding

`BigDecimal` lets finite decimal addition/subtraction/multiplication run accurately when precision is not intentionally bounded; **it does not make every division produce a finite decimal result**.

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException: non-terminating decimal expansion
BigDecimal approx = one.divide(three, 4, RoundingMode.HALF_UP);
// approx is 0.3333
~~~

If you use `MathContext`, operations can be rounded to the required precision:

~~~java
java.math.MathContext context =
        new java.math.MathContext(4, RoundingMode.HALF_EVEN);
BigDecimal roundedByPrecision =
        new BigDecimal("123.456").round(context);
// 123.5 (4 significant digits)
~~~

**Distinction:**

- `setScale(2, ...)` primarily adjusts the number of digits by scale, usually referring to digits after the decimal point.
- `MathContext(4, ...)` specifies **4 significant digits**, not four digits after the decimal point.
- `round`/`setScale` return a new object; `BigDecimal` is immutable.
- `RoundingMode.UNNECESSARY` demands that no rounding occur; if data requires rounding, it can throw `ArithmeticException`. This is a way to detect unexpected rounding.

For currency, beyond creating `BigDecimal` from strings, you also must define when rounding occurs (per line item or on the total), scale, rounding mode, currency unit, and reconciliation rules. The right constructor is a **necessary condition**, not a guarantee that the whole billing system is accurate.

## 10. Integers and constructors free from this double decimal issue

If the source is genuinely an exact integer in `int` or `long`, you can construct `BigDecimal` directly:

~~~java
BigDecimal units = BigDecimal.valueOf(42L);
BigDecimal alsoUnits = new BigDecimal("42");
~~~

Because `long` represents every integer in its range exactly, `BigDecimal.valueOf(long)` is direct and unsurprising. `BigDecimal.valueOf(long)` and `BigDecimal.valueOf(double)` are **two different overloads**; do not equate their mechanisms.

For large integers exceeding `long`, `BigInteger` and the `BigDecimal(BigInteger)` constructor preserve exact values:

~~~java
java.math.BigInteger huge =
        new java.math.BigInteger("9223372036854775808");
BigDecimal exactHuge = new BigDecimal(huge);
~~~

Do not cast `BigInteger` to `double` and then construct `BigDecimal`, because that conversion can lose precision bits or overflow to infinity.

## 11. Common misconceptions

1. **“`new BigDecimal(0.1)` is more exact than `new BigDecimal("0.1")`, so it's always better.”** It is exact **with respect to the rounded `double`**, not exact with respect to the decimal intent `1/10`.
2. **“Printing `double` as `0.1` means 0.1 is stored exactly inside.”** `Double.toString` creates a short string capable of round-tripping; it does not display all decimal digits of the stored bit value.
3. **“`BigDecimal.valueOf` always removes arithmetic errors.”** It only uses `Double.toString` of the **existing value**; `0.1 + 0.2` is still `0.30000000000000004`.
4. **“Two BigDecimals that print almost identically must be `equals`.”** Both value and scale must be considered; `1.0` and `1.00` are not equal under `equals`, yet `compareTo == 0`.
5. **“`setScale(2)` rounds silently without needing a policy.”** If digits must be dropped and no rounding mode is specified, the operation can throw `ArithmeticException`. Use `setScale(2, mode)` with an explicit policy.
6. **“Passing NaN/Infinity into BigDecimal works because they are all numbers.”** `BigDecimal` does not represent NaN or infinity; conversion raises an error.
7. **“Creating BigDecimal from `double` and then handling money is enough.”** If the input went through binary64 arithmetic, the original decimal may be unrecoverable. Keep decimal data from the source.
8. **“Rounding at the display step means the actual monetary amount is rounded.”** A formatter only outputs a string. Business values must be quantized and stored per policy.
9. **“Use an epsilon to make BigDecimal.equals approximate.”** `BigDecimal` models specific decimal values and scales; if business logic needs approximate comparison, define a separate rule without breaking the equality/hash contract.
10. **“Any user string that looks like a number is always accepted by the constructor.”** Grouping formats, locales, invalid characters, or missing values still require validation and handling `NumberFormatException`.

## 12. Quick selection guide

| Data source / purpose | Preferred approach | Why? |
| --- | --- | --- |
| Original decimal string `"0.10"` | `new BigDecimal("0.10")` | Preserves exact entered value and scale |
| Decimal literal for money in source code | `new BigDecimal("19.99")` | Does not pass through binary64 |
| Already have `double` and want short round-trip decimal | `BigDecimal.valueOf(double)` | Based on `Double.toString` |
| Already have `double` and need exact decimal of bit pattern | `new BigDecimal(double)` | Preserves exact binary64 value |
| Exact `long` integer | `BigDecimal.valueOf(long)` | No binary64 fractional error |
| Very large integer `BigInteger` | `new BigDecimal(bigInteger)` | Preserves integers beyond long range |
| Decimal needing rounding to 2 digits | `setScale(2, RoundingMode.…)` | Explicitly specifies quantization |
| Compare two BigDecimals by numeric value | `compareTo(...) == 0` | Independent of scale |
| Compare BigDecimals by object representation | `equals(...)` | Includes scale |
| NaN/Infinity input | Handle before creating BigDecimal | This decimal type does not represent them |

## 13. Self-check questions

**Question 1.** Why does `new BigDecimal(0.1)` print more digits than `new BigDecimal("0.1")`?

**Answer:** The literal `0.1` was already rounded to a binary `double` value; the `double` constructor represents that approximated value exactly in decimal. The `String` constructor directly represents the exact decimal number.

**Question 2.** Does `BigDecimal.valueOf(0.1)` equal `new BigDecimal("0.1")`? Does `BigDecimal.valueOf(0.1 + 0.2)` also equal `new BigDecimal("0.3")`?

**Answer:** In the first case, yes. In the second case, no: `double` addition produces `0.30000000000000004`, and the factory retains the round-trip string form of that result.

**Question 3.** Why does `new BigDecimal(1.005).setScale(2, HALF_UP)` differ from the `String` constructor's result?

**Answer:** The stored binary64 value is less than decimal 1.005, so the `double` constructor rounds to `1.00`; the `"1.005"` constructor preserves the exact decimal midpoint and HALF_UP gives `1.01`.

**Question 4.** What does `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` return? Does `compareTo` return 0?

**Answer:** `equals` returns false because the scales differ; `compareTo` returns 0 because the decimal values are equal.

**Question 5.** Why is converting JSON decimal `"19.99"` to `double` before constructing `BigDecimal` risky?

**Answer:** Parsing into `double` can lose decimal accuracy and original scale information. If exact decimals are needed, parse string data directly into `BigDecimal`.

**Question 6.** Should you use `new BigDecimal(Double.NaN)` or expect `BigDecimal.ONE.divide(new BigDecimal("3"))` to return an infinite decimal?

**Answer:** No. `BigDecimal` does not support NaN so that constructor throws `NumberFormatException`; division yielding a non-terminating decimal without a rounding policy throws `ArithmeticException`.

## References

- [Java SE 21 — BigDecimal: constructor(double), constructor(String), valueOf, scale, rounding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
- [Java SE 21 — Double.toString and IEEE 754](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html).
- [Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html) and [RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html).
- [Java Language Specification `4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).