# Mistake: Formatting Then Parsing Back to Perform Arithmetic Rounding

## 1. The Core Problem

An anti-pattern in Java is **formatting a number into a string with N decimal places, parsing that string back into a number, and using the result for further calculations**. For example:

~~~java
// Illustrative snippet only, not a standalone program.
String text = String.format(java.util.Locale.US, "%.2f", amount);
double rounded = Double.parseDouble(text);
~~~

This looks like rounding, yet it mixes three distinct responsibilities: **presentation**, **text parsing**, and **arithmetic transformation**. A formatted display string can contain thousands separators, locale-specific decimal separators, currency symbols, padded zeros, or dropped digits. Parsing it back also depends on parser type and configuration, and can return a `double` carrying binary rounding error.

If business logic needs to round a `BigDecimal` value, use **`setScale(scale, RoundingMode)`** or **`round(MathContext)`**; if rounding a quotient, use a `divide` overload with scale/`MathContext` and a rounding mode. Format only after the final value to display has been determined. If business logic must preserve the original unrounded value, format the original for display and never feed that string back into calculations.

## 2. Three Operations with Different Purposes

| Operation | Goal | Example | Characteristics |
| --- | --- | --- | --- |
| **Format** | Display a number to users | `NumberFormat.format(value)` | Involves locale, grouping, currency symbols, zero padding, and may round the text |
| **Parse** | Read text into a numeric type | `DecimalFormat.parse(text)` | Depends on syntax/locale; may accept only a valid prefix |
| **Round** | Apply an arithmetic rule to a value | `value.setScale(2, HALF_EVEN)` | Requires no String conversion; explicit policy |

For example, the exact number `1234.567` may be formatted by a US formatter as `1,234.57`. The thousandths digit has been dropped: parsing it back **cannot reconstruct `1234.567`**. Formatting is a presentation-boundary operation; it does not establish a rounding policy for an entire calculation.

`BigDecimal` is immutable: `setScale`, `round`, and add/subtract/multiply operations return a new `BigDecimal` without mutating the original object. Locale is not a property of `BigDecimal` either. Computed numbers should have consistent meaning before being displayed for the US, Germany, or Vietnam.

## 3. Illustrating the Anti-Pattern: Precision Lost Even When Parsing Succeeds

The following program intentionally performs format→parse to demonstrate how data changes. The US pattern `#,##0.00` adds grouping separators and keeps two fractional digits. The parser is configured to return `BigDecimal` so no extra `double` error is introduced, yet **digits lost during formatting still never come back**.

Save as `FormatParseTrapDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class FormatParseTrapDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234.567");

        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);

        String shown = format.format(original);
        ParsePosition position = new ParsePosition(0);
        BigDecimal parsed = (BigDecimal) format.parse(shown, position);

        System.out.println("original = " + original.toPlainString());
        System.out.println("formatted = " + shown);
        System.out.println("parsed = " + parsed.toPlainString());
        System.out.println("fully parsed = "
                + (position.getIndex() == shown.length()));
        System.out.println("same value = "
                + (original.compareTo(parsed) == 0));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac FormatParseTrapDemo.java
java FormatParseTrapDemo
~~~

Output:

~~~text
original = 1234.567
formatted = 1,234.57
parsed = 1234.57
fully parsed = true
same value = false
~~~

The parser consumes the entire string and returns a `BigDecimal`, yet the value was already rounded for **display** requirements. If `parsed` is then summed into a report, used to calculate fees, or rounded again, the program has altered the input to downstream math without an explicit arithmetic policy.

Moreover, `new BigDecimal("1,234.57")` throws `NumberFormatException`, because `BigDecimal`'s constructor does not understand locale grouping separators. Thus a display-formatted string is not a canonical decimal string for storage or constructor parsing.

## 4. Locale: The Same String Can Have Different Meanings

Decimal and grouping separators depend on locale. `1,234` normally means one thousand two hundred thirty-four in the US, whereas in Germany it is one point two three four. Germany typically displays `1234.57` as `1.234,57`.

Locales can also use Unicode spaces, different digit characters, or distinct currency layouts. Never blindly run `replace(",", ".")`, as that can turn a grouping separator into a decimal point. Never format with `Locale.getDefault()` and parse with another locale; OS and JVM settings can differ between development and deployment machines.

### Java 17 Example: Two Values from the Same String

Save as `LocaleNumberDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberDemo {
    static BigDecimal parseEntire(String text, Locale locale)
            throws ParseException {
        NumberFormat nf = NumberFormat.getNumberInstance(locale);
        if (!(nf instanceof DecimalFormat df)) {
            throw new IllegalStateException("DecimalFormat unavailable");
        }
        df.setParseBigDecimal(true);
        ParsePosition pos = new ParsePosition(0);
        Number parsed = df.parse(text, pos);

        if (!(parsed instanceof BigDecimal result)
                || pos.getIndex() != text.length()) {
            throw new ParseException("Invalid decimal",
                    Math.max(0, pos.getIndex()));
        }
        return result;
    }

    public static void main(String[] args) throws ParseException {
        String input = "1,234";
        System.out.println("US = " + parseEntire(input, Locale.US));
        System.out.println("DE = " + parseEntire(input, Locale.GERMANY));
    }
}
~~~

~~~bash
javac LocaleNumberDemo.java
java LocaleNumberDemo
~~~

Output with standard JDK 17 locale data:

~~~text
US = 1234
DE = 1.234
~~~

`NumberFormat.parse` can return `Long` or `Double` under default configuration; do not cast directly to `BigDecimal` without enabling `DecimalFormat.setParseBigDecimal(true)` and checking the type. `DecimalFormat` can still parse fairly leniently, especially with grouping separators. Checking `ParsePosition.getIndex() == text.length()` only confirms the entire string was consumed—**it does not enforce strict grouping structure**. If a UI requires strict syntax, add locale-appropriate validation. Java 17 does not yet have a `DecimalFormat.setStrict` API.

In particular, `BigDecimal` cannot represent `NaN` or infinity; always inspect parse results and handle exceptional inputs according to the data contract.

## 5. Use setScale for Arithmetic Rounding

When the requirement is **rounding to two decimal places**, the right operation is:

~~~java
// Illustrative example; value must be declared beforehand.
BigDecimal rounded = value.setScale(2, RoundingMode.HALF_EVEN);
~~~

`setScale(2, ...)` retains exactly two digits after the decimal point. When reducing scale discards significant digits, Java applies the provided rounding mode. When increasing scale, it appends zeros without changing the mathematical value.

Modes:

| RoundingMode | Meaning |
| --- | --- |
| `HALF_UP` | Nearest neighbor; ties round away from 0 |
| `HALF_DOWN` | Nearest neighbor; ties round toward 0 |
| `HALF_EVEN` | Nearest neighbor; ties round toward even last kept digit |
| `UP` | Away from 0 whenever discarded part is nonzero |
| `DOWN` | Toward 0 whenever discarded part is nonzero |
| `CEILING` | Toward positive infinity |
| `FLOOR` | Toward negative infinity |
| `UNNECESSARY` | Forbids discarding nonzero digits; throws `ArithmeticException` if rounding is needed |

Choose the mode per business requirements; `UP` is not synonymous with `HALF_UP`. For negative numbers, `CEILING` and `FLOOR` differ from away-from-zero or toward-zero rules. In currency, tax, and billing, rounding policies must be explicitly specified rather than relying on a formatter's default.

### Java 17 Example: Round Then Format

Save as `RoundThenFormatDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class RoundThenFormatDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234.567");
        BigDecimal rounded = original.setScale(
                2, RoundingMode.HALF_UP);

        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);
        formatter.setGroupingUsed(true);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        System.out.println("original = " + original.toPlainString());
        System.out.println("rounded = " + rounded.toPlainString());
        System.out.println("display = " + formatter.format(rounded));
        System.out.println("source remains = " + original.toPlainString());
    }
}
~~~

~~~bash
javac RoundThenFormatDemo.java
java RoundThenFormatDemo
~~~

Output:

~~~text
original = 1234.567
rounded = 1234.57
display = 1,234.57
source remains = 1234.567
~~~

If business rules truly require the two-decimal-place value, continue computing with `rounded`. If the UI only needs to **display** two digits while calculations must still keep `1234.567`, continue using `original` and format only at UI output. Which one to use must never be decided implicitly by a formatter.

## 6. MathContext: Precision Is Not Scale

Another source of confusion is `MathContext`. `setScale(2, HALF_EVEN)` keeps two digits **after the decimal point**; `round(new MathContext(4, HALF_EVEN))` keeps at most four **significant digits**.

Example with `123.45`:

- `setScale(2, HALF_EVEN)` ⇒ `123.45`.
- `round(MathContext(4, HALF_EVEN))` ⇒ `123.4`.

### Java 17 Example: Two Different Concepts

Save as `ScalePrecisionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class ScalePrecisionDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("123.45");
        System.out.println("source = " + x);
        System.out.println("scale 2 = " + x.setScale(
                2, RoundingMode.HALF_EVEN));
        System.out.println("precision 4 = " + x.round(
                new MathContext(4, RoundingMode.HALF_EVEN)));
    }
}
~~~

~~~bash
javac ScalePrecisionDemo.java
java ScalePrecisionDemo
~~~

Output:

~~~text
source = 123.45
scale 2 = 123.45
precision 4 = 123.4
~~~

If a decimal division is non-terminating, like `1/3`, exact `BigDecimal.divide(divisor)` throws `ArithmeticException`. Use `divide(divisor, 2, RoundingMode.HALF_UP)` for two decimal places or `divide(divisor, MathContext)` for significant-digit precision. **Do not format and parse the quotient** to dodge choosing a rounding mode.

## 7. Parsing Back to double Reintroduces Binary Error

`double` is a binary floating-point type with finite bits. Many decimal numbers like `0.1` are not represented exactly. Therefore, formatting a two-decimal string and calling `Double.parseDouble` **does not create an exact decimal number with two decimal places**. It creates the nearest binary value, which can keep introducing error in subsequent additions and multiplications.

Even constructing `BigDecimal` from `double` has a trap: `new BigDecimal(2.675)` represents the exact `double` passed in, which is slightly less than the ideal decimal 2.675. `new BigDecimal("2.675")` represents the exact decimal 2.675.

### Java 17 Example: Divergence at a Rounding Boundary

Save as `DoubleSourceTrapDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DoubleSourceTrapDemo {
    public static void main(String[] args) {
        BigDecimal decimal = new BigDecimal("2.675");
        BigDecimal binary = new BigDecimal(2.675);

        System.out.println("decimal = " + decimal.setScale(
                2, RoundingMode.HALF_EVEN));
        System.out.println("from double = " + binary.setScale(
                2, RoundingMode.HALF_EVEN));
        System.out.println("double sum = " + (0.1 + 0.2));
    }
}
~~~

~~~bash
javac DoubleSourceTrapDemo.java
java DoubleSourceTrapDemo
~~~

Output:

~~~text
decimal = 2.68
from double = 2.67
double sum = 0.30000000000000004
~~~

The exact decimal 2.675 lies halfway between 2.67 and 2.68; `HALF_EVEN` picks the even last digit 8. The value originating from `double` is slightly below the midpoint, so it rounds down to 2.67. `BigDecimal.valueOf(double)` uses the canonical string representation of `double` and can be a better choice than `new BigDecimal(double)` when forced to accept a `double`, yet it **cannot recover** precision already lost in earlier calculations.

## 8. Formatting Then Parsing Can Change Scale Without Changing Value

`BigDecimal` stores both value and scale. `2.0` has scale 1, whereas `2.00` has scale 2. Both are numerically equal under `compareTo`, yet distinct under `equals`. A formatter can append trailing zeros due to `minimumFractionDigits` or drop digits/zeros due to `maximumFractionDigits`, so a round-trip can alter scale even when mathematical value stays unchanged.

### Java 17 Example: Two Numerically Equal Values Differing Under equals

Save as `FormatScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class FormatScaleDemo {
    public static void main(String[] args) {
        BigDecimal source = new BigDecimal("2.0");
        DecimalFormat formatter = new DecimalFormat(
                "0.00", DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setParseBigDecimal(true);

        String text = formatter.format(source);
        BigDecimal parsed = (BigDecimal) formatter.parse(
                text, new ParsePosition(0));

        System.out.println("source = " + source);
        System.out.println("display = " + text);
        System.out.println("parsed = " + parsed);
        System.out.println("source scale = " + source.scale());
        System.out.println("parsed scale = " + parsed.scale());
        System.out.println("numeric equal = "
                + (source.compareTo(parsed) == 0));
        System.out.println("equals = " + source.equals(parsed));
    }
}
~~~

~~~bash
javac FormatScaleDemo.java
java FormatScaleDemo
~~~

Output:

~~~text
source = 2.0
display = 2.00
parsed = 2.00
source scale = 1
parsed scale = 2
numeric equal = true
equals = false
~~~

If you intentionally want to normalize scale to 2, use `source.setScale(2, roundingMode)`. Changing scale can affect `equals`/`hashCode` and `BigDecimal` keys in a `HashMap`, so it is a data decision rather than a harmless formatting trick.

## 9. At Which Stage Should Rounding Happen?

Rounding **each line** and summing can differ from summing **exact values** and rounding once at the end. Suppose three values of `1.005` use `HALF_EVEN` to keep two fractional digits:

- Each value rounded first: `1.00`, sum `3.00`.
- Exact sum: `3.015`, rounded afterward: `3.02`.

### Java 17 Example: Two Summation Policies

Save as `RoundingStageDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingStageDemo {
    public static void main(String[] args) {
        BigDecimal[] entries = {
            new BigDecimal("1.005"),
            new BigDecimal("1.005"),
            new BigDecimal("1.005")
        };
        BigDecimal exact = BigDecimal.ZERO;
        BigDecimal sumOfRounded = BigDecimal.ZERO;

        for (BigDecimal x : entries) {
            exact = exact.add(x);
            sumOfRounded = sumOfRounded.add(
                    x.setScale(2, RoundingMode.HALF_EVEN));
        }

        System.out.println("exact total = " + exact);
        System.out.println("sum rounded lines = " + sumOfRounded);
        System.out.println("round after sum = " + exact.setScale(
                2, RoundingMode.HALF_EVEN));
    }
}
~~~

~~~bash
javac RoundingStageDemo.java
java RoundingStageDemo
~~~

Output:

~~~text
exact total = 3.015
sum rounded lines = 3.00
round after sum = 3.02
~~~

Both rounding steps follow `HALF_EVEN`. The difference comes from **when** it is applied. In currency, taxes, invoices, and reports, you must specify whether business rules require rounding per line, per transaction, or on the total. Never let two-decimal display formatting silently alter intermediate calculation data.

## 10. When Should You Reject Instead of Rounding?

Sometimes rules forbid automatic rounding; data exceeding the allowed significant decimal places must be rejected. `RoundingMode.UNNECESSARY` helps verify whether a `BigDecimal` can be converted to the desired scale **without losing numeric information**.

### Java 17 Example: Checking Exact Cents

Save as `RequireExactScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RequireExactScaleDemo {
    static BigDecimal requireCents(BigDecimal value) {
        return value.setScale(2, RoundingMode.UNNECESSARY);
    }

    public static void main(String[] args) {
        System.out.println(requireCents(new BigDecimal("12.5")));
        System.out.println(requireCents(new BigDecimal("12.5000")));

        try {
            System.out.println(requireCents(new BigDecimal("12.345")));
        } catch (ArithmeticException ex) {
            System.out.println("Rejected: rounding required");
        }
    }
}
~~~

~~~bash
javac RequireExactScaleDemo.java
java RequireExactScaleDemo
~~~

Output:

~~~text
12.50
12.50
Rejected: rounding required
~~~

`12.5000` has four fractional digits in the **input string**, yet its value converts cleanly to `12.50` because the dropped digits are only zeros. If requirements forbid inputs with more than two fractional digits even when trailing zeros, validate **input syntax**, not just numeric representability.

## 11. A Clean Data Flow for Applications

A reliable decimal processing pipeline separates these steps:

1. **Identify input format:** machine-readable canonical decimal string or locale-specific user input? For locale input, use a locale-matching parser and validate the entire string plus allowed rules.
2. **Keep numeric values in `BigDecimal`** if business logic requires exact decimals. Avoid intermediate `double`s or display-formatted strings.
3. **Validate constraints:** min/max, negative signs, precision, scale, currency codes, and whether to reject or round.
4. **Compute on the source numbers** using `BigDecimal` APIs. If an operation requires `MathContext` or `RoundingMode`, provide an explicit policy.
5. **Round at the exact business boundary** using `setScale` or `MathContext`, never driven by a formatter.
6. **Format only at the output boundary** per locale and UI requirements. Persist and exchange values in a machine-readable decimal format with a clear contract.

`NumberFormat` and `DecimalFormat` hold mutable state and are not thread-safe by default. Do not share a mutable formatter instance across threads without proper synchronization. For computation logic, avoid depending on `Locale.getDefault()` when results must be consistent across machines.

## 12. Common Mistakes

1. **Format→parse for arithmetic rounding:** mixes calculation logic with presentation logic.
2. **Parsing grouped strings with `BigDecimal(String)`:** `"1,234.57"` is not a valid decimal literal.
3. **Formatting and parsing in different locales:** commas and dots can be swapped, misparsed, or rejected.
4. **Casting `NumberFormat.parse` directly to `BigDecimal`:** without `setParseBigDecimal(true)`, it can return `Long`/`Double`.
5. **Assuming parse success means the whole string was valid:** parsers can stop after a prefix or accept loose grouping; use `ParsePosition` and validation.
6. **Using `double` after formatting `BigDecimal`:** binary approximation remains and can lose precision.
7. **Confusing formatting max 2 fractional digits with `setScale(2)`:** the former controls text output, the latter produces an arithmetic result.
8. **Confusing precision and scale:** `MathContext` counts significant digits; `setScale` counts digits after the decimal point.
9. **Omitting `RoundingMode`:** relies on defaults or triggers `ArithmeticException`.
10. **Round-trip changing scale:** `2.0` and `2.00` differ under `equals`/`hashCode`.
11. **Rounding intermediate steps to match UI display:** can alter totals or business formulas.
12. **Using `UNNECESSARY` to count digits typed by the user:** it only checks for value loss, not trailing zeros in text.
13. **Sharing a static formatter across concurrent threads:** `DecimalFormat` is not thread-safe.
14. **Storing human-readable formatted strings in APIs/databases as numbers:** locale-dependent and lossy.

## 13. Self-Check Exercises

**Question 1.** If `1234.567` is formatted to `"1,234.57"` and parsed back, does it still equal the source value?

**Answer:** No. The thousandths digit was dropped during formatting; the parsed value is `1234.57`.

**Question 2.** What should you do to round `1234.567` to two decimal places using `HALF_UP`?

**Answer:** `new BigDecimal("1234.567").setScale(2, RoundingMode.HALF_UP)` gives `1234.57`. No intermediate string is needed, and it is locale-independent.

**Question 3.** Why can `"1,234"` have two meanings?

**Answer:** The US uses comma as a grouping separator ⇒ 1234; Germany uses comma as the decimal separator ⇒ 1.234.

**Question 4.** Why can formatting `2.0` as `2.00` and parsing back to `BigDecimal` make `equals` return false?

**Answer:** The source has scale 1 while the parsed value has scale 2; `compareTo` still treats them as numerically equal.

**Question 5.** Three values of `1.005` rounded per line give what total, and summed first give what total?

**Answer:** With `HALF_EVEN` scale 2: sum of rounded lines is `3.00`; exact sum then rounded is `3.02`.

**Question 6.** Why is `12.5000.setScale(2, UNNECESSARY)` not rejected?

**Answer:** Only zeros are dropped, so no value is lost. To forbid entering more than two fractional digits, validate the input string.

## 14. Key Takeaways

- **Format is presentation; parse is reading text; round is arithmetic transformation.** Never format and parse back just to round for a calculation.
- Use `BigDecimal.setScale` for decimal places, `MathContext` for significant digits, and `divide` overloads for quotients requiring rounding.
- Always specify `RoundingMode` and **the stage of rounding** per business rules, independent of UI locale.
- Keep the original `BigDecimal` when full precision is needed; format at output and parse once at input.
- Watch out for `double`, grouping separators, partial-string parsing, scale changes, and formatters shared across threads.

Java SE 17 API references: `java.math.BigDecimal`, `java.math.MathContext`, `java.math.RoundingMode`, `java.text.DecimalFormat`, `java.text.NumberFormat`, and `java.text.ParsePosition`.
