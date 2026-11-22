# Distinguishing Minimum Digits, Maximum Digits, and Value Precision in Java

A system may require printing **at least two digits after the decimal point**, printing **at most four digits**, or computing with **three significant digits**. These three concepts are not the same. Java provides APIs to control the **display string** such as `DecimalFormat`, `String.format`, and `printf`, and APIs that produce **rounded decimal values** such as `BigDecimal.setScale` or `MathContext`.

Most importantly: **formatting fewer digits neither lowers nor raises the precision of the underlying stored value**. Conversely, a `double` value that already contains binary rounding error keeps the exact same error even when printed as `0.30`. This Knowledge lesson belongs to the **Representation and Formatting** section of Java Core, focusing on minimum/maximum digits, precision, scale, width, and how to avoid confusion when saving/outputting data.

## 1. Core concepts

| Concept | Purpose | Example |
| --- | --- | --- |
| Minimum fraction digits | Minimum number of digits *after the decimal point* when printing | `1.2` → `1.20` |
| Maximum fraction digits | Maximum number of digits after the decimal point when printing | `1.234567` → `1.2346` when max = 4 |
| Minimum integer digits | Pads *integer-part* digits when printing | `12.5` → `0012.50` |
| Maximum integer digits | Caps integer digits when formatting | Can **drop high-order digits**, very dangerous |
| Formatter width | Minimum **total string** width including sign, zeros, and spaces | `%8.2f` gives `"    1.20"` |
| Formatter precision | Digits after the decimal point for `%f`, or significant digits for `%g` | `%.2f` differs from `%.2g` |
| `BigDecimal.scale()` | Decimal exponent in `unscaledValue × 10^(-scale)` | `12.3456` has scale 4 |
| `BigDecimal.precision()` | Number of significant decimal digits of the unscaled value | `12.3456` has precision 6 |
| `MathContext.precision` | Limits significant digits of **a `BigDecimal` operation result** | Rounds `12.3456` to `12.3` when precision is 3 |

Formatting attributes determine output appearance; arithmetic precision also depends on data type, input representation, operation order, and rounding policy. An expression containing 10 digits after the decimal point does not by itself guarantee all 10 digits are trustworthy as measurements.

## 2. `DecimalFormat`: required `0` vs optional `#`

`java.text.DecimalFormat` builds a string representation of a number from a pattern. Two basic symbols:

- `0`: required digit position; pads with extra `0`s if missing.
- `#`: optional position; omits unnecessary `0`s.
- `.`: decimal separator position in the pattern expression.
- `,`: marks digit grouping; the actual character depends on `Locale` and `DecimalFormatSymbols`.

Example:

~~~java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.ROOT);
DecimalFormat formatter = new DecimalFormat("0.00##", symbols);
formatter.setRoundingMode(RoundingMode.HALF_EVEN);

System.out.println(formatter.format(1.2));      // 1.20
System.out.println(formatter.format(1.234567)); // 1.2346
System.out.println(formatter.format(12));       // 12.00
~~~

The pattern `0.00##` has **min = 2** and **max = 4** fractional digits. The number `1.2` is padded with a trailing zero to print `1.20`, while `1.234567` is rounded into the **string** `1.2346`.

Read the limits directly from the formatter:

~~~java
int minimum = formatter.getMinimumFractionDigits(); // 2
int maximum = formatter.getMaximumFractionDigits(); // 4
~~~

Pattern `0.0#` has min 1, max 2:

~~~java
DecimalFormat f = new DecimalFormat("0.0#", symbols);
f.format(1);     // "1.0"
f.format(1.23);  // "1.23"
f.format(1.234); // "1.23"
~~~

**Maximum differs from minimum:** when fractional digits are short, `0` positions are forced to appear; when trailing digits are unnecessary, `#` positions can be omitted. If excess digits must be rounded, the formatter obeys the configured `RoundingMode`. It does not mutate the source variable.

## 3. When to use minimum/maximum fraction digit setters?

Besides patterns, you can configure:

~~~java
DecimalFormat f = new DecimalFormat("0", symbols);
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(4);
f.setRoundingMode(RoundingMode.HALF_EVEN);
// f.format(1.2)      -> "1.20"
// f.format(1.234567) -> "1.2346"
~~~

`getMinimumFractionDigits` and `getMaximumFractionDigits` let you inspect the final configuration. `NumberFormat` maintains consistency between minimum and maximum; when setting one value beyond the opposing bound, the setter may adjust the opposite limit as well. Therefore, if settings are changed dynamically, **re-read both min and max** to verify.

`DecimalFormat` is mutable and is not guaranteed to be safe when sharing the same instance concurrently across threads without synchronization. You can create separate instances per usage scope or manage their lifecycle appropriately.

**Note:** "max = 2" does not mean the `double` type is stored accurately to two decimal places. It only produces a representation that looks like it has at most two digits after the decimal point.

## 4. Integer digits: zero-padding can be right, dropping high digits is dangerous

`minimumIntegerDigits` specifies the minimum number of integer positions:

~~~java
DecimalFormat padded = new DecimalFormat("0000.00", symbols);
System.out.println(padded.format(12.5)); // 0012.50
~~~

In the example, the integer part `12` is padded with two leading zeros. This is presentation only; it does not turn the numeric type into an object carrying four fixed integer digits. If `0012` is an identifier code and leading zeros carry meaning, store the code **as a string**, not merely as `int 12`.

`maximumIntegerDigits` is another trap. When capped, `DecimalFormat` can **drop high-order digits**:

~~~java
DecimalFormat limited = new DecimalFormat("0", symbols);
limited.setMaximumIntegerDigits(3);
System.out.println(limited.format(12345)); // 345
~~~

Do not use `setMaximumIntegerDigits(3)` to "round" or "shorten" large numbers. If the screen is too narrow, handle layout or use an explicit convention (such as expressing in thousands with a unit), rather than silently turning `12345` into `345`.

Maximum integer digits is also not for checking overflow or validating input. Value-range contracts must be enforced on the **original numeric value**, not a truncated string.

## 5. `Formatter` width differs from precision

`String.format` and `System.out.printf` use `java.util.Formatter`. The basic syntax is `%[flags][width][.precision]conversion`:

| Format | Meaning | Example result |
| --- | --- | --- |
| `%.2f` | Exact two digits **after the decimal point in the string** | `1.23456` → `"1.23"` |
| `%8.2f` | Minimum 8 characters, 2 fractional digits | `1.2` → `"    1.20"` |
| `%.3g` | Three significant digits of the floating-point string (general format) | `12345.678` → `"1.23e+04"` |
| `%d` | Integer | Does not accept dot-precision like `%f` |

~~~java
String width = String.format(Locale.ROOT, "%8.2f", 1.2);
String fixed = String.format(Locale.ROOT, "%.2f", 1.23456);
String significant = String.format(Locale.ROOT, "%.3g", 12345.678);
~~~

The results are `"    1.20"`, `"1.23"`, and `"1.23e+04"`, respectively.

**Width** is the minimum character width of the entire printed field, including sign, fractional digits, and spaces; if the numeric string is longer than `width`, the formatter prints it longer rather than truncating data by default.

**Precision for `%f`** is digits after the decimal point; **precision for `%g`** is significant digits in the presentation. Do not use them interchangeably. In particular, `%.2f` does not mean the original value `1.23456` has been reassigned to the number `1.23`.

Formats using `Locale` may pick dots or commas by region. When machine-readable content requires stable output, specify an appropriate locale such as `Locale.ROOT`. For human-facing UIs, use the locale matching the language/market.

## 6. Storage precision of `float` and `double`

`float`/`double` are IEEE 754 binary floating-point types with finite precision: binary32 has 24 significand precision bits, and binary64 has 53 bits. Decimal numbers like `0.1` and `0.2` cannot be represented exactly with this finite number of bits.

~~~java
double sum = 0.1 + 0.2;

System.out.println(sum); // 0.30000000000000004
System.out.println(
        String.format(Locale.ROOT, "%.2f", sum)); // 0.30
System.out.println(sum); // still 0.30000000000000004
~~~

`String.format` creates a new `String` and **does not modify the stored `double` value**. Hence downstream comparisons, sums, and algorithms still use the original value. Printing more or fewer digits cannot fix errors caused by binary representation and order of operations.

`Double.toString` produces a short decimal representation suitable for round-trip per the API contract, rather than printing every decimal digit of the stored binary64 value. You can use `new BigDecimal(double)` to examine the exact decimal expansion of the bit value, though that is not the same concept as the decimal number a user intended to enter.

When floating-point numbers cross from one system to another, exporting data with an arbitrary digit limit can lose information. To round-trip a `double` value, use `Double.toString` paired with the matching parser or a protocol with equivalent guarantees; do not pick `%.2f` just because it looks readable.

## 7. `BigDecimal.precision()` and `scale()` are not min/max digits

`BigDecimal` stores a decimal number via an unscaled integer and a scale: `value = unscaledValue × 10^(-scale)`.

With:

~~~java
BigDecimal number = new BigDecimal("12.3456");
System.out.println(number.precision()); // 6
System.out.println(number.scale());     // 4
~~~

- **`precision() = 6`**: six significant digits of the unscaled value per `BigDecimal` rules.
- **`scale() = 4`**: the decimal exponent needed to interpret the unscaled value as `12.3456`.

Scale is not always "the number of digits after the decimal point" in string terms: scale can be **0 or negative**, for instance after normalizing a number with trailing zeros. Precision is not the actual measurement uncertainty or the number of display digits. These properties live inside the **`BigDecimal` value**, while `DecimalFormat` manages the **printed string**.

If a measurement states "accuracy ±0.01", that is metadata about the instrument and measurement error/uncertainty; do not infer it from `precision()`. Model that constraint in the domain logic.

## 8. `setScale` vs `MathContext` precision

A `BigDecimal` can be rounded and stored as a new value by two criteria:

~~~java
BigDecimal value = new BigDecimal("12.3456");

BigDecimal byFractionPosition =
        value.setScale(2, RoundingMode.HALF_UP); // 12.35

BigDecimal bySignificantDigits =
        value.round(new MathContext(3, RoundingMode.HALF_UP)); // 12.3
~~~

**`setScale(2, ...)`** retains two fractional positions per the rounding rule. **`MathContext(3, ...)`** retains three significant digits in the result, counting the integer part as well. For numbers of different magnitudes, the corresponding rounding position shifts.

This is an **operation on the value**, unlike `DecimalFormat.format`:

~~~java
BigDecimal original = new BigDecimal("12.3456");
DecimalFormat f = new DecimalFormat("0.00", symbols);
f.setRoundingMode(RoundingMode.HALF_UP);
String shown = f.format(original); // "12.35"
// original is still 12.3456
~~~

`BigDecimal` is immutable: `round` and `setScale` return a new object without modifying the source object. To record a scale-2 value in a ledger, you must **store the resulting object** rather than merely formatting the original object.

`RoundingMode.HALF_EVEN` and `HALF_UP` do not always produce the same result at midpoints. If business logic involves money, taxes, or allocations, clearly specify when rounding occurs and which rounding mode applies. With `RoundingMode.UNNECESSARY`, a conversion that requires rounding will throw `ArithmeticException` instead of silently losing information.

## 9. Standalone Java 17+ program and exact stdout

Create the file `DigitFormatDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DigitFormatDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.ROOT);
        DecimalFormat range = new DecimalFormat("0.00##", symbols);
        range.setRoundingMode(RoundingMode.HALF_EVEN);

        System.out.println("min fraction = "
                + range.getMinimumFractionDigits());
        System.out.println("max fraction = "
                + range.getMaximumFractionDigits());
        System.out.println("range 1.2 = " + range.format(1.2));
        System.out.println("range 1.234567 = "
                + range.format(1.234567));
        System.out.println("range 12 = " + range.format(12));

        DecimalFormat padded = new DecimalFormat("0000.00", symbols);
        System.out.println("padded 12.5 = " + padded.format(12.5));

        DecimalFormat optional = new DecimalFormat("0.0#", symbols);
        System.out.println("optional 1 = " + optional.format(1));
        System.out.println("optional 1.23 = " + optional.format(1.23));
        System.out.println("optional 1.234 = "
                + optional.format(1.234));

        DecimalFormat group = new DecimalFormat("#,##0.###", symbols);
        System.out.println("group 12345.6789 = "
                + group.format(12345.6789));

        System.out.println("width = |"
                + String.format(Locale.ROOT, "%8.2f", 1.2)
                + "|");
        System.out.println("f 1.23456 = "
                + String.format(Locale.ROOT, "%.2f", 1.23456));
        System.out.println("g 12345.678 = "
                + String.format(Locale.ROOT, "%.3g", 12345.678));

        BigDecimal original = new BigDecimal("12.3456");
        System.out.println("decimal original = " + original);
        System.out.println("formatted decimal = " + range.format(original));
        System.out.println("decimal after format = " + original);
        System.out.println("setScale(2) = "
                + original.setScale(2, RoundingMode.HALF_UP));
        System.out.println("MathContext(3) = "
                + original.round(new MathContext(3, RoundingMode.HALF_UP)));
        System.out.println("decimal precision = " + original.precision());
        System.out.println("decimal scale = " + original.scale());

        double sum = 0.1 + 0.2;
        System.out.println("double raw = " + sum);
        System.out.println("double display = "
                + String.format(Locale.ROOT, "%.2f", sum));
        System.out.println("double still raw = " + sum);

        DecimalFormat limited = new DecimalFormat("0", symbols);
        limited.setMaximumIntegerDigits(3);
        System.out.println("max integer 3 of 12345 = "
                + limited.format(12345));
    }
}
~~~

Compile and run:

~~~bash
javac DigitFormatDemo.java
java DigitFormatDemo
~~~

Output:

~~~text
min fraction = 2
max fraction = 4
range 1.2 = 1.20
range 1.234567 = 1.2346
range 12 = 12.00
padded 12.5 = 0012.50
optional 1 = 1.0
optional 1.23 = 1.23
optional 1.234 = 1.23
group 12345.6789 = 12,345.679
width = |    1.20|
f 1.23456 = 1.23
g 12345.678 = 1.23e+04
decimal original = 12.3456
formatted decimal = 12.3456
decimal after format = 12.3456
setScale(2) = 12.35
MathContext(3) = 12.3
decimal precision = 6
decimal scale = 4
double raw = 0.30000000000000004
double display = 0.30
double still raw = 0.30000000000000004
max integer 3 of 12345 = 345
~~~

The first two lines show the actual min/max configuration. The `range`, `optional`, and `group` lines illustrate formatter behavior. `width` and `g` distinguish precision/width types. The `BigDecimal` lines show that the formatter does not modify the object, while `setScale`/`MathContext` create new results. The `double raw`/`double display` pair proves that shortening printed output does not alter the underlying data.

## 10. Is formatting and parsing back rounding the value?

Suppose:

~~~java
double original = 1.234567;
String displayed = String.format(Locale.ROOT, "%.2f", original);
// displayed = "1.23"
double reparsed = Double.parseDouble(displayed);
// reparsed represents an approximation near 1.23, differing from original
~~~

If you **assign `reparsed` to a variable**, the program does end up with a new value, but that is a consequence of **formatting and then parsing back**, not the formatter mutating the old variable. This approach also carries risks:

- Losing information because multiple original values collapse into one shortened string.
- Introducing dependencies on locale, digit grouping, and decimal separators.
- Still having binary64 error in the re-parsed value.
- Altering algorithm behavior if string-based rounding is applied after every calculation step.

Do not use this trick as a general method for improving accuracy. If the requirement is decimal quantization, use decimal types and calculation policies; if the requirement is display, format only at the output step.

## 11. Application scenarios and right decisions

**Displaying scores:** Raw score `9.5`, report requires two digits after the decimal point. `DecimalFormat("0.00")` displays `9.50`. The added zero does not prove grading was more precise, nor does it alter the raw score.

**Sensor UI:** Measurement `12.3456` when the screen only has room to display `12.35`. The formatter can use maximum fraction digits = 2. The system must still retain the raw value and device uncertainty if the goal is engineering analysis.

**Invoices:** Decimal data `12.3456` must be rounded to `12.35` before saving. Choose `BigDecimal#setScale(2, roundingMode)` and save the **resulting value**, not merely formatting the source. Financial rules must state whether rounding happens per line item, at the total, or at payment time.

**Order codes:** Code `0012` needs leading zeros preserved for matching. Store `String` instead of storing `int 12` and trying to reconstruct it with `minimumIntegerDigits`.

**Large numbers:** `setMaximumIntegerDigits(3)` turns `12345` into the printed string `345`. If a compact view is needed, write explicit units (e.g., 12.3k) with clear UI rules instead of silently dropping significant high-order digits.

**Data exchange:** If the receiver must get exact `double` numeric data, prefer a format with guaranteed round-trip. If the receiver expects a decimal amount with a required scale, define explicit `BigDecimal`/serialization rules. A two-decimal display string cannot replace either of those two contracts.

## 12. Common mistakes

1. **Thinking minimum fraction digits = 2 makes the value more accurate.** It only appends zeros to the string if needed.
2. **Confusing maximum fraction digits with the precision of `double`.** A shorter string does not fix the stored value.
3. **Confusing `%.2f` with `%.2g`.** `%f` controls fractional digits; `%g` controls significant digits in the output.
4. **Confusing `%8.2f` with eight digits.** Eight is the minimum width in characters.
5. **Setting maximum integer digits too small.** It can drop leading digits, displaying a misleading numeric value.
6. **Confusing `BigDecimal.scale()` with `precision()`.** One property is the decimal exponent, while the other counts significant digits of the unscaled value.
7. **Thinking `MathContext(3)` means three fractional digits.** It means three total significant digits.
8. **Calling `BigDecimal#setScale` without capturing the return value.** `BigDecimal` is immutable.
9. **Omitting the rounding mode at critical points.** `HALF_EVEN` and `HALF_UP` can differ.
10. **Sharing a formatter across multiple threads carelessly.** `DecimalFormat` is mutable and not thread-safe under unprotected concurrent sharing.
11. **Using format/parse to "fix" errors.** It can discard information and still produce an approximate `double`.
12. **Failing to control locale.** Different decimal separators can break protocols or tests.
13. **Thinking stored precision equals measurement quality.** Measurement uncertainty is not automatically represented by an object's digit count.

## 13. Self-check

**1.** How does `DecimalFormat("0.00##")` print `1.2`, and what are the fractional limits?

**Answer:** `1.20`; minimum = 2, maximum = 4. If more than 4 fractional digits are needed to represent the value, the formatter rounds when building the string.

**2.** Does `String.format(Locale.ROOT, "%8.2f", 1.2)` contain eight digits or eight characters?

**Answer:** At least eight **characters**; the result consists of four spaces and `1.20`.

**3.** Why does `%.3g` differ from `%.3f`?

**Answer:** `%g` focuses on three significant digits, whereas `%f` focuses on three digits after the decimal point.

**4.** What are the precision and scale of `new BigDecimal("12.3456")`?

**Answer:** Precision = 6 and scale = 4. Formatting with fewer digits does not change the object's properties.

**5.** Compare `setScale(2, HALF_UP)` and `round(new MathContext(3, HALF_UP))` on `12.3456`.

**Answer:** Results are `12.35` and `12.3`. One keeps 2 decimal places, while the other keeps 3 significant digits.

**6.** Why is `setMaximumIntegerDigits(3)` unsuitable for shortening `12345`?

**Answer:** It can print `345`, dropping high-order digits and misleading users into seeing a different number.

**7.** Does `String.format("%.2f", 0.1 + 0.2)` make the addition become exact `0.3`?

**Answer:** No. It only prints `0.30`; the original `double` value remains `0.30000000000000004`.

## References

- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): `0`/`#` patterns, digit limits, rounding behavior.
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): minimum/maximum integer/fraction digits.
- [Java SE 21 — Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html): width and precision for `%f` and `%g` conversions.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, `setScale`.
- [Java SE 21 — MathContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html): precision as significant digits for operations.
- [JLS `4.2.3 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).