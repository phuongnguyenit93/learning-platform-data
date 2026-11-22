# Formatting BigInteger, BigDecimal, and the Pitfalls of Converting Through double

## 1. Why Does Formatting Large Numbers Require Attention to Data Types?

Java applications frequently need to display numbers exceeding `long` range or decimal values demanding high precision. For example:

- A numeric identifier with value `9007199254740993`.
- An arithmetic calculation producing `12345678901234567890.123456789`.
- A monetary amount `1.005` that must be rounded according to business rules.
- The same value displayed under `en-US` or `de-DE` conventions with different thousands and decimal separators.

Java provides `BigInteger` and `BigDecimal` for **exact storage and arithmetic**, and `NumberFormat` and `DecimalFormat` for **locale-aware presentation**. A common mistake is converting the value to `double` before formatting:

```java
BigInteger value = new BigInteger("9007199254740993");
double converted = value.doubleValue(); // Loses 1 unit.
```

`double` has only 53 bits of significand precision (including the implicit bit); it cannot accurately represent all large integers or most finite base-10 decimals. If a formatting step relies on a `double` that has already been rounded, changing the `Locale` or adding fractional digits **cannot recover the lost data**.

Lesson goals: use the direct formatting path for `BigInteger`/`BigDecimal` without going through `double`, control digit counts and rounding, distinguish raw data from display strings, parse values by locale, and recognize practical formatter limitations.

## 2. Three Numeric Types and Their Precision Differences

| Type | Characteristics | Key points to remember |
| --- | --- | --- |
| `BigInteger` | Arbitrary-magnitude exact integer | No fractional part; converting to `long`/`double` can lose information |
| `BigDecimal` | Exact decimal based on an unscaled integer and scale | Does not automatically cap digits; requires rounding rules and scale suited to the domain |
| `double` | IEEE 754 binary floating-point, finite precision | Roughly 15–17 significant decimal digits; cannot represent most decimal fractions exactly |

### 2.1. BigInteger

`java.math.BigInteger` represents integers of arbitrary size, bounded primarily by system resources and implementation limits. It is ideal for large integers requiring exactness; `new BigInteger(String)` reads the value from a string without going through `double`.

```java
BigInteger exact = new BigInteger("9007199254740993");
System.out.println(exact);                    // 9007199254740993
System.out.println(exact.doubleValue());      // 9.007199254740992E15
```

The number `9007199254740993 = 2^53 + 1` cannot be represented exactly as a `double`. When converted to `double` via IEEE 754 rounding, the value becomes `9007199254740992`. Consecutive integers from `-2^53` to `2^53` can be represented exactly; beyond that range, **not every integer** is representable (some multiples of the representation step remain exact).

### 2.2. BigDecimal

`java.math.BigDecimal` stores a number in the form:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

For example, `new BigDecimal("123.4500")` has numeric value 123.4500, unscaled value 1234500, and scale 4. Two values can be numerically equal while having different scales:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

This distinction matters when controlling presentation such as digits after the decimal separator. `BigDecimal.toPlainString()` outputs standard decimal form without a locale; `DecimalFormat` can add separators and select displayed digit counts.

**Construct from strings when exactness is needed:**

```java
BigDecimal precise = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
```

- `precise` is the exact decimal value `0.1`.
- `fromDouble` takes the actual binary value of the `0.1` literal and creates an exact decimal representation of **that `double` value**, so it is not numerically equal to `0.1`.
- `BigDecimal.valueOf(0.1)` uses the canonical string form of `double` (via `Double.toString`), which yields `0.1` in this case. It is safer than `new BigDecimal(double)` in many situations, yet **cannot restore precision lost earlier**: if a large number was already coerced to `double`, `valueOf` only receives the rounded `double`.

## 3. Formatting by Locale with NumberFormat and DecimalFormat

`NumberFormat` is the high-level API for presenting numbers by locale:

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat germany = NumberFormat.getNumberInstance(Locale.GERMANY);
```

`DecimalFormat` is the very common implementation for decimal numbers, supporting patterns, grouping separators, digit bounds, and rounding modes:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);
DecimalFormat formatter = new DecimalFormat("#,##0.00", symbols);
```

In those two lines, the comma and period in the **pattern** are non-localized syntax tokens; `DecimalFormatSymbols` defines the actual output characters for the locale. Do not concatenate `","`/`"."` onto numbers manually to simulate formatting.

Related APIs:

| API | Function |
| --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Obtain a general number formatter for the locale |
| `NumberFormat.getIntegerInstance(locale)` | Obtain an integer formatter; typically rounds fractions when formatting |
| `NumberFormat.getCurrencyInstance(locale)` | Obtain a currency formatter using the locale's default conventions |
| `DecimalFormat(pattern, symbols)` | Create a formatter from a pattern and symbol set |
| `setGroupingUsed(boolean)` | Enable/disable digit grouping |
| `setMinimumFractionDigits(int)` | Minimum digits after the decimal separator |
| `setMaximumFractionDigits(int)` | Maximum digits after the decimal separator |
| `setMinimumIntegerDigits(int)` | Minimum integer digits |
| `setMaximumIntegerDigits(int)` | Limit on displayed integer digits per formatter |
| `setRoundingMode(RoundingMode)` | Rounding policy during formatting |
| `format(Object)` | Format a number object; `DecimalFormat` supports `BigInteger`/`BigDecimal` |
| `DecimalFormat.setParseBigDecimal(true)` | Parse locale decimals into `BigDecimal` instead of mostly `Long`/`Double` |

**Key takeaway:** `DecimalFormat` supports formatting `BigInteger` and `BigDecimal` objects directly, without forcing a call to `doubleValue()`. When you write:

```java
BigDecimal amount = new BigDecimal("12345678901234567890.123456789");
String display = formatter.format(amount);
```

the call can take the `format(Object)` path to process the `BigDecimal` value directly. Avoid converting to `double` merely out of a belief that formatters only accept primitive `double` or `long`.

However, **direct formatting does not mean printing infinite digits**. Patterns and minimum/maximum digit bounds determine display length; the formatter may round or truncate display digits according to its rules. "Supporting `BigDecimal` without precision loss from casting to `double`" does **not** mean "printing every original fractional digit by default."

### 3.1. Be Careful When Casting NumberFormat to DecimalFormat

On runtimes with the JDK's default formatting provider, `NumberFormat.getNumberInstance(Locale.US)` usually returns a `DecimalFormat`. However, the `NumberFormat` API only promises an object implementing `NumberFormat`; environments with custom providers may substitute another class. If you explicitly need `DecimalFormat`-specific APIs, instantiate it directly:

```java
DecimalFormat f = new DecimalFormat(
        "#,##0.000", DecimalFormatSymbols.getInstance(Locale.US)
);
```

To start from a locale's standard pattern and customize it, check the runtime type before casting rather than assuming every formatter is a `DecimalFormat`.

## 4. Why Converting BigInteger to double Corrupts the Value

`double` is a binary floating-point format with a 53-bit significand. Around `2^53`, consecutive `double` values are 2 units apart. Thus the odd integer `9007199254740993` rounds to `9007199254740992` upon conversion.

Create **`BigNumberFormattingDemo.java`** — a complete program using Java 17+:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class BigNumberFormattingDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols us =
                DecimalFormatSymbols.getInstance(Locale.US);

        BigInteger hugeInteger =
                new BigInteger("9007199254740993");
        DecimalFormat integerFormat =
                new DecimalFormat("0", us);

        System.out.println("BigInteger direct: "
                + integerFormat.format(hugeInteger));
        System.out.println("BigInteger through double: "
                + integerFormat.format(hugeInteger.doubleValue()));

        BigDecimal hugeDecimal =
                new BigDecimal("12345678901234567890.123456789");
        DecimalFormat decimalFormat =
                new DecimalFormat("0.000000000", us);
        decimalFormat.setRoundingMode(RoundingMode.HALF_EVEN);

        System.out.println("BigDecimal direct: "
                + decimalFormat.format(hugeDecimal));
        System.out.println("BigDecimal through double: "
                + decimalFormat.format(hugeDecimal.doubleValue()));

        BigDecimal amount = new BigDecimal("1.005");
        DecimalFormat twoDigits =
                new DecimalFormat("0.00", us);

        twoDigits.setRoundingMode(RoundingMode.HALF_EVEN);
        System.out.println("HALF_EVEN: "
                + twoDigits.format(amount));

        twoDigits.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("HALF_UP: "
                + twoDigits.format(amount));

        System.out.println("Original: " + amount.toPlainString());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BigNumberFormattingDemo.java
java BigNumberFormattingDemo
```

**Stdout on Java 17+ with `Locale.US` symbols:**

```text
BigInteger direct: 9007199254740993
BigInteger through double: 9007199254740992
BigDecimal direct: 12345678901234567890.123456789
BigDecimal through double: 12345678901234567000.000000000
HALF_EVEN: 1.00
HALF_UP: 1.01
Original: 1.005
```

Observations:

1. `DecimalFormat.format(hugeInteger)` preserves the exact integer. Simply calling `hugeInteger.doubleValue()` alters the value to `9007199254740992`.
2. `DecimalFormat` can directly format `BigDecimal` with 9 fractional digits. Casting that large value through `double` loses information in both the integer and fractional parts; appending `.000000000` only makes the **output look 9 digits wide**, without making the data any more accurate.
3. `HALF_EVEN` and `HALF_UP` differ on `1.005` when displaying two fractional digits.
4. `amount` remains `1.005` after both `format` calls. Formatting only creates **new strings**; it does not mutate the original `BigDecimal` object.

The example's output is designed not to depend on the machine's grouping or decimal separator defaults: the formatter uses `DecimalFormatSymbols` from `Locale.US` and an ungrouped pattern.

## 5. Limits of double: Understand Exactly What Is Lost

### 5.1. For Integers

The contiguous integer range that `double` can represent exactly is:

\[
-2^{53} \le n \le 2^{53}
\]

Outside this range, **some** integers remain representable (such as even numbers near `2^53`), but not all. Whenever a `BigInteger` exceeding this range is converted to `double`, treat it as a **potentially lossy** conversion—never use it for IDs, numeric keys, money, or data requiring absolute exactness.

Beyond precision loss, `BigInteger.doubleValue()` can also yield `Double.POSITIVE_INFINITY` or `Double.NEGATIVE_INFINITY` when the value exceeds `double`'s finite range. A formatter cannot reconstruct the original integer from infinity.

### 5.2. For Decimal Numbers

In binary, numbers like `0.1` have no exact finite representation. To see this clearly:

```java
System.out.println(new BigDecimal("0.1").toPlainString());
// 0.1

System.out.println(new BigDecimal(0.1).toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625
```

This is a **snippet** inside a method with `import java.math.BigDecimal;`. The issue has nothing to do with locale; it happens because the literal `0.1` is already a `double` before constructing the `BigDecimal`.

If your application's calculations require 20–30 exact decimal digits, converting to `double` at any intermediate step can break that guarantee. Keep computations in `BigDecimal` with a well-defined `MathContext`/`RoundingMode`, and format only at the output boundary.

### 5.3. Do Not Confuse double Limits with Formatter Limits

There are three distinct layers of limits:

| Layer | Limit / policy | Example |
| --- | --- | --- |
| Storage type | `double` has finite bit precision | `9007199254740993` gets rounded through `double` |
| Arithmetic rounding rules | `BigDecimal` has scale and `MathContext` per operation | `divide` may require a rounding mode |
| Display rules | `DecimalFormat` limits integer/fraction digits, grouping, rounding mode | `1.005` displays as `1.00` or `1.01` |

When specifying `setMaximumFractionDigits(2)`, you are constraining the **display string**, not converting the `BigDecimal` into a new object with scale 2. If you need to persist money with a specific scale, use an operation like `setScale(2, roundingMode)` per business policy.

## 6. RoundingMode When Formatting BigDecimal

`DecimalFormat` can round a value when fewer fractional digits are displayed than exist in the number. Two very common modes:

- `RoundingMode.HALF_EVEN`: when equidistant between two representable outcomes, chooses the one whose final digit is even (banker's rounding).
- `RoundingMode.HALF_UP`: when equidistant, rounds away from 0.

With **exact** decimal data:

| Value | Two decimals, HALF_EVEN | Two decimals, HALF_UP |
| ---: | ---: | ---: |
| `1.005` | `1.00` | `1.01` |
| `1.015` | `1.02` | `1.02` |
| `2.225` | `2.22` | `2.23` |
| `-1.005` | `-1.00` | `-1.01` |

These are exact arithmetic results when the input is a string-constructed `BigDecimal`. If the value previously went through `double`, the "exact midpoint" condition may no longer hold as expected.

To configure:

```java
DecimalFormat decimal = new DecimalFormat(
        "0.00", DecimalFormatSymbols.getInstance(Locale.US)
);
decimal.setRoundingMode(RoundingMode.HALF_UP);
String result = decimal.format(new BigDecimal("1.005"));
// result is "1.01"
```

This is a **snippet**, not a standalone Java program; it requires `import java.text.DecimalFormat;`, `DecimalFormatSymbols`, `java.math.BigDecimal;`, `RoundingMode;`, and `java.util.Locale;`.

**Never use formatted strings for further calculations.** For instance, rounding two amounts of `1.005` and `1.005` per line before summing can produce a different result than summing accurately first and rounding the total. Rounding order must follow business and regulatory rules, not be implicitly dictated by a formatter.

### Minimum and Maximum Digit Bounds

`setMinimumFractionDigits(2)` forces at least two fractional digits, padding zeros if needed. `setMaximumFractionDigits(2)` caps fractional digits at two and may round. When both are 2, `1.2` displays as `1.20`, while `1.234` displays rounded to two fractional digits.

`setMaximumIntegerDigits(...)` directly affects how many integer digits are printed; never set an arbitrary limit on IDs or very large exact integers. Internal bounds applying to `double`/`long` formatting differ from `DecimalFormat`'s direct `BigInteger`/`BigDecimal` formatting path. To preserve all required digits in output, verify your patterns, bounds, and realistic input values.

Specifically, if you need a format with **at most nine fractional digits** without forcing all nine trailing zeros, use a pattern like `0.#########`. If you need to keep all nine digits for a fixed-layout UI, use `0.000000000` as in the demo.

## 7. Formatting BigInteger by Language/Region

`BigInteger.toString()` returns an ungrouped integer representation without locale separators. In a user interface, you can use `NumberFormat`:

```java
BigInteger population = new BigInteger("12345678901234567890");

NumberFormat english = NumberFormat.getIntegerInstance(Locale.US);
NumberFormat german = NumberFormat.getIntegerInstance(Locale.GERMANY);

String a = english.format(population);
String b = german.format(population);
```

This is a **snippet**. With standard locale data, the two formatters can use different grouping separators—for example, a comma in `en-US` and a period in `de-DE`. However, formatting depends on the JDK's locale data and provider. Do not hardcode per-region output expectations when the runtime environment is not pinned.

**Watch out:** `NumberFormat.getIntegerInstance(...)` configures integer-style formatting. If the input is a `BigDecimal` with a fractional part, this formatter can **round the fractional part**; it is not `toBigIntegerExact()` and does not prove the original value is an integer. To guarantee data has no fractional part, verify with `toBigIntegerExact()` before formatting or check the fractional part explicitly.

When the default formatter is the JDK's `DecimalFormat`, it handles `BigInteger` directly. If using a custom `NumberFormat` provider, verify the implementation's contract; do not assume every implementation supports every arbitrary-precision path.

## 8. Formatting BigDecimal by Locale While Preserving Business Semantics

For decimal numbers:

```java
BigDecimal value = new BigDecimal("12345.6789");

NumberFormat localeNumber =
        NumberFormat.getNumberInstance(Locale.GERMANY);
localeNumber.setMinimumFractionDigits(4);
localeNumber.setMaximumFractionDigits(4);

String formatted = localeNumber.format(value);
```

This is a **snippet**; the fraction settings express the desire to show four digits, while the actual rendering (separators, grouping) depends on the locale and implementation. When precise format control is needed, use `DecimalFormat` and `DecimalFormatSymbols` explicitly.

### When Formatting Currency

`NumberFormat.getCurrencyInstance(locale)` selects **regional currency display conventions**, not the transaction currency. For example, a USD order for a user in Germany may use `Locale.GERMANY` while the currency remains `USD`.

```java
NumberFormat money = NumberFormat.getCurrencyInstance(Locale.GERMANY);
money.setCurrency(Currency.getInstance("USD"));
String label = money.format(new BigDecimal("1234.50"));
```

This snippet illustrates formatting a `BigDecimal` directly **without calling `doubleValue()`**. Currency code/symbol rendering, symbol placement, grouping separators, and fractional digits are governed by the formatter and currency. Certain accounting rules, currency units, or payment workflows have dedicated rounding policies: set them explicitly rather than relying on defaults.

Note that calling `setCurrency` does not automatically update previously configured fraction digit bounds in every implementation; check `getMinimumFractionDigits()`, `getMaximumFractionDigits()`, and the rounding mode if the business requires an exact digit count.

## 9. Locale-Aware Parsing: Avoiding Precision Loss on Input

From a display string, `NumberFormat.parse(...)` typically returns `Long` or `Double` depending on the value and implementation. When exact decimals must be preserved in financial applications, a `DecimalFormat` can be configured as follows:

```java
DecimalFormat parser = (DecimalFormat)
        NumberFormat.getNumberInstance(Locale.US);
parser.setParseBigDecimal(true);
```

`parse` then returns a `BigDecimal` for normal finite values instead of forcing the value through `double`. However, because alternative providers may exist, check the formatter's type before casting or construct an explicit `DecimalFormat` with `DecimalFormatSymbols`.

**To avoid accepting a string that was only partially parsed**, use `ParsePosition`:

Create **`ParsePreciseDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParsePreciseDecimalDemo {
    public static void main(String[] args) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.#########", 
                DecimalFormatSymbols.getInstance(Locale.US)
        );
        parser.setParseBigDecimal(true);

        String input = "12,345.678";
        ParsePosition position = new ParsePosition(0);
        Number number = parser.parse(input, position);

        if (!(number instanceof BigDecimal parsed)
                || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid number: " + input);
        }

        System.out.println("Type: " + parsed.getClass().getSimpleName());
        System.out.println("Value: " + parsed.toPlainString());
        System.out.println("Complete: " 
                + (position.getIndex() == input.length()));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ParsePreciseDecimalDemo.java
java ParsePreciseDecimalDemo
```

Output:

```text
Type: BigDecimal
Value: 12345.678
Complete: true
```

`setParseBigDecimal(true)` is appropriate for ordinary finite values; special cases like NaN/Infinity can produce other return types. Beyond verifying full string consumption, the application must still enforce rules for grouping acceptance, signs, scale limits, input length, and value range. **Successful parsing does not mean the input is valid under business rules.**

Additionally, never use `new BigDecimal("12,345.678")` to read locale-formatted strings: that constructor is not a locale-aware parser and will throw a format exception. When exchanging data between services over machine protocols, prefer a locale-independent canonical representation (such as decimal string `12345.678`) rather than parsing user-facing formatted strings.

## 10. Preserving Precision and Display Limits: Choosing the Right API

| Requirement | Preferred solution | Avoid |
| --- | --- | --- |
| Store and compute integers beyond `long` | `BigInteger` | Casting to `long`/`double` before computing |
| Store money or decimals requiring exactness | `BigDecimal(String)` or exact decimal source | `new BigDecimal(double)` for decimal business data |
| Display `BigInteger` by locale | Pass directly to a formatter supporting `BigInteger` | `format(bigInteger.doubleValue())` |
| Display `BigDecimal` with fixed digits | `DecimalFormat` with locale symbols, clear pattern/rounding | Converting `BigDecimal` through `double` first |
| Perform arithmetic rounding for persistence | `setScale`/`MathContext` per policy | Formatting to string and parsing back to compute |
| Read locale-formatted UI decimals | `DecimalFormat.setParseBigDecimal(true)`, check full consumption | `Double.parseDouble(...)` after ad-hoc grouping removal |
| Machine-to-machine data needing neutral format | `BigDecimal.toPlainString()` or agreed canonical form | Using a locale formatter as a serialization format |
| Display money to users in another region | `NumberFormat.getCurrencyInstance(locale)`, explicit transaction currency | Inferring transaction currency solely from locale |

### Common Mistakes

1. **Converting `BigInteger` to `double` just to call `format(double)`.** Output can already be wrong in the ones digit. `DecimalFormat` has a direct object-formatting path for large numbers.
2. **Using `new BigDecimal(0.1)` thinking the value is exactly one-tenth.** The `0.1` literal is an approximated `double`; use `new BigDecimal("0.1")` for decimal values supplied by business logic.
3. **Increasing `maximumFractionDigits` after precision has already been lost.** The formatter cannot reconstruct digits lost in an earlier type cast.
4. **Assuming default `NumberFormat` prints all digits.** Defaults usually cap fractional digits and enable grouping; configure per display requirements.
5. **Confusing formatter rounding with business data rounding.** `format` returns a string and does not mutate the `BigDecimal`.
6. **Formatting money in one locale and using the formatted string in calculations.** Display strings depend on grouping/decimal marks and may be rounded; keep numeric values in the model.
7. **Parsing another locale's string with `Double.parseDouble`.** It does not understand user grouping or decimal separators; use a locale-aware parser.
8. **Treating `Double.toString` as proof that all source digits were preserved.** That string is the round-trip representation of the current `double`, not the original decimal source.
9. **Sharing a mutable `DecimalFormat` across requests while changing settings.** `NumberFormat`/`DecimalFormat` are not guaranteed thread-safe; create separate instances or synchronize when sharing.
10. **Treating large identifiers as numbers to format.** IDs are typically tokens that may have leading zeros or require stable representation; never insert grouping separators or alter their form. Format as numbers only when the data truly has numeric quantity semantics.

## 11. Self-Check Exercises

**Question 1.** Why does `new BigInteger("9007199254740993").doubleValue()` differ from the original value?

**Answer:** `double` has 53 bits of precision; the integer `2^53+1` cannot be represented exactly and rounds to `2^53`. `BigInteger` does not suffer from this loss.

**Question 2.** Given `new BigDecimal("12345678901234567890.123456789")`, which API should you use to print nine fractional digits without losing precision?

**Answer:** `DecimalFormat` with a pattern or configuration for 9 fractional digits, passing the `BigDecimal` directly into `format(Object)`. Do not cast to `double`.

**Question 3.** How does `DecimalFormat("0.00")` format `BigDecimal("1.005")` under `HALF_EVEN` vs. `HALF_UP`?

**Answer:** `HALF_EVEN` → `1.00`; `HALF_UP` → `1.01`. In both cases, the input `BigDecimal` remains `1.005`.

**Question 4.** Why do `new BigDecimal(0.1)` and `new BigDecimal("0.1")` differ?

**Answer:** The `double` constructor captures the approximated binary value, whereas the `String` constructor parses the exact specified decimal digits.

**Question 5.** When parsing `"12,345.678"` with `Locale.US` and needing to preserve exact decimal type, what should you do?

**Answer:** Use `DecimalFormat` with `Locale.US` symbols, enable `setParseBigDecimal(true)`, and verify `ParsePosition` consumed the entire string; then validate business constraints.

**Question 6.** If a formatter prints `1.20` from `BigDecimal("1.2")`, does the original object's scale change?

**Answer:** No. The formatter produces a display string; to change a number's scale, use `setScale(...)` per policy.

**Question 7.** A formatter prints a large number as `12345678901234567000.000000000`. Should those nine trailing zeros be taken as proof of exact decimal data?

**Answer:** No. That can be output from a rounded `double`; the zeros added by the pattern are purely cosmetic presentation.

## 12. Conclusion and References

- `BigInteger` preserves large integers; `BigDecimal` preserves exact decimals when constructed and manipulated properly. `double` is a binary approximation with finite range and precision.
- `DecimalFormat` can format `BigInteger` and `BigDecimal` directly; **you do not need to and should not cast to `double`** just for display.
- Control `Locale`, `DecimalFormatSymbols`, grouping, minimum/maximum digits, and `RoundingMode`. Each of these decisions affects the **display string**, not the underlying source data.
- Keep calculations in exact types, perform arithmetic rounding according to business rules, and format only at the UI/report output layer.
- When parsing locale-formatted user numbers, use `DecimalFormat.setParseBigDecimal(true)` and verify the entire string was consumed.

Official documentation:

- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 21 — BigInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)