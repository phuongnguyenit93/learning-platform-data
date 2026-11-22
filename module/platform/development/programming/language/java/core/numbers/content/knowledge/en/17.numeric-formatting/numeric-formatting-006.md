# `NumberFormat` for General Numbers, Percentages, and Currencies in Java

## 1. Why is `NumberFormat` needed?

A numeric value can be **represented differently depending on language and country**, even though its mathematical value stays the same. For example, **12345.67** in a US UI is typically **12,345.67**, whereas in a German UI it is **12.345,67**. Percentages and monetary amounts add further rules for the `%` sign, currency symbols, decimal digits, and whitespace.

In Java, **`java.text.NumberFormat`** is the API for formatting and parsing numbers according to **`Locale`**. It is an abstract class whose concrete instances are usually obtained via factory methods.

~~~java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
String shown = number.format(12345.67); // "12,345.67"
~~~

The snippet above is illustrative code placed inside a Java method. The API does not alter the input **value**; instead, it converts the value into a **display string**; when parsing an input string, the same matching `Locale` convention must be used.

Lesson objectives:

- Distinguish **`getNumberInstance`**, **`getIntegerInstance`**, **`getPercentInstance`**, and **`getCurrencyInstance`**.
- Understand the role of **`Locale`**, decimal digits, grouping, and displayed digit counts.
- Know that a ratio of **0.125** can display as **12.5%**, not **0.125%**.
- Know that currency formatting is **formatting**, not **exchange-rate conversion**.
- Round intentionally, distinguishing the **stored value** from the **rounded display string**.
- Parse strings by Locale, using **`ParsePosition`** and **`DecimalFormat.setParseBigDecimal(true)`** when exact decimals are required.
- Recognize pitfalls in multithreaded apps, currencies, machine data, and untrusted inputs.

**Scope:** examples use Java 17+, preferring **`Locale.US`** so stdout is easy to verify. With other Locales, symbols and whitespace may differ according to the JDK's localization data.

## 2. Important factory methods

| API | Kind of string to display | Example in `Locale.US` |
| --- | --- | --- |
| **`NumberFormat.getNumberInstance(locale)`** | General numbers | **12,345.67** |
| **`NumberFormat.getInstance(locale)`** | Equivalent to general number format | **12,345.67** |
| **`NumberFormat.getIntegerInstance(locale)`** | Integers, formatting fractional parts to whole numbers | **12,346** from 12345.6 |
| **`NumberFormat.getPercentInstance(locale)`** | Percentages | **12%** from 0.12 |
| **`NumberFormat.getCurrencyInstance(locale)`** | Currencies | **$1,234.56** from 1234.56 |

The factories return **`NumberFormat`**, a general overarching API, and do not necessarily return an instance of the exact same subclass across every JDK/provider. On common JDKs, general number, percentage, and currency formats are usually **`DecimalFormat`**; if you need `DecimalFormat`-specific APIs, check **`instanceof`** before casting.

To display large numbers compactly, Java 12+ also offers **`getCompactNumberInstance(locale, style)`**, though that is a supplementary feature and does not replace the three primary format types in this lesson.

### Which `Locale` is used if none is passed?

~~~java
NumberFormat implicit = NumberFormat.getNumberInstance();
NumberFormat explicit = NumberFormat.getNumberInstance(Locale.US);
~~~

The `implicit` variable uses the **default `Locale` belonging to `Locale.Category.FORMAT`** of the runtime environment. This `Locale` can depend on the host machine, JVM, container, or application configuration; hence stdout and UIs can vary across environments.

In multilingual products, you should **pass an explicit `Locale`** based on user selection or UI configuration. Do not assume every machine's JVM uses `Locale.US`, and do not change a process-wide default `Locale` just to handle a single request.

## 3. Formatting general numbers

~~~java
NumberFormat f = NumberFormat.getNumberInstance(Locale.US);
System.out.println(f.format(12345.67)); // "12,345.67"
~~~

In `Locale.US`, commas typically separate thousands groups, and a dot marks the decimal point. In `Locale.GERMANY`, the two roles are reversed: **12.345,67**.

Adjustment methods:

| API | Function |
| --- | --- |
| **`setGroupingUsed(true/false)`** | Toggles digit grouping without changing the number |
| **`setMinimumIntegerDigits(n)`** | Minimum integer digits, potentially adding leading zeros |
| **`setMaximumIntegerDigits(n)`** | Maximum integer digits in the formatted string; be aware of leading truncation risk |
| **`setMinimumFractionDigits(n)`** | Minimum fractional digits displayed, adding zeros if needed |
| **`setMaximumFractionDigits(n)`** | Maximum fractional digits displayed, potentially rounding |
| **`setRoundingMode(mode)`** | Rounding rule when digits need to be dropped |

Display control example:

~~~java
NumberFormat f = NumberFormat.getNumberInstance(Locale.US);
f.setGroupingUsed(true);
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(2);
f.setRoundingMode(java.math.RoundingMode.HALF_UP);

System.out.println(f.format(12345.678)); // "12,345.68"
System.out.println(f.format(12));        // "12.00"
~~~

**`setMinimumFractionDigits(2)`** enforces at least two digits after the decimal point. **`setMaximumFractionDigits(2)`** limits to at most two digits; when the value has further digits, formatting may round according to `RoundingMode`. The passed value **12345.678** itself is not modified.

### Ordering of min/max settings

The minimum fraction digits cannot exceed the maximum fraction digits. In standard subclasses, if you set `min` above the current `max`, `max` may be automatically adjusted accordingly; similarly when setting `max` below `min`. Therefore, set **both** explicitly per your configuration and inspect `getMinimumFractionDigits`/`getMaximumFractionDigits` if reusing a formatter passed in from elsewhere.

**`setGroupingUsed(false)`** is mainly useful for display when you want to omit digit grouping, but it is not enough to guarantee Locale-independent machine data syntax: the decimal separator still follows the `Locale`.

## 4. Integers: `getIntegerInstance` does not mean the input is `int`

~~~java
NumberFormat f = NumberFormat.getIntegerInstance(Locale.US);
String result = f.format(12345.6); // "12,346"
~~~

The integer formatter **rounds the output representation** according to its configured rule. As of Java 17, the integer factory defaults to **`RoundingMode.HALF_EVEN`** when formatting floating-point numbers; therefore, do not assume it always truncates the fractional part toward zero.

Important points:

- **`getIntegerInstance`** accepts `double`/`long` and suitable `Number` instances; it is a **formatting style**, not an input data-type check.
- When **parsing**, the integer formatter is configured to parse only the integer part (*parseIntegerOnly*). Do not use it to parse a complete currency or decimal string without checking.
- If the goal is arithmetic type conversion, use bounds-checked conversion rather than inferring a new data type solely from a formatted string.

When integer rounding behavior such as `RoundingMode.DOWN`, `UP`, `HALF_EVEN`, or `HALF_UP` must be controlled, choose the rule matching business requirements and call **`setRoundingMode`** when supported by the subclass.

## 5. Percent: percentages multiply the value by 100 when displaying

**`getPercentInstance(locale)`** displays a ratio as a percentage. The input value is typically in the form **0..1** when expressing rates from 0% to 100%:

| Numeric value | Expected percentage string in `Locale.US` |
| ---: | --- |
| 0 | **0%** |
| 0.12 | **12%** |
| 0.5 | **50%** |
| 1 | **100%** |
| 1.25 | **125%** |

It does not restrict the input value to `[0,1]`. A growth rate of 125% can be valid in the domain; negative rates can also be represented.

~~~java
NumberFormat pct = NumberFormat.getPercentInstance(Locale.US);
pct.setMinimumFractionDigits(1);
pct.setMaximumFractionDigits(1);
pct.setRoundingMode(java.math.RoundingMode.HALF_UP);

System.out.println(pct.format(0.1234)); // "12.3%"
System.out.println(pct.format(1.0));    // "100.0%"
~~~

**Common pitfall:** if data already stores **12.5** meaning **12.5%**, calling **`format(12.5)`** will display **1250%**. You need to convert it to the ratio **0.125** first or redefine the data contract.

Proper handling must start from the **meaning of the data field**:

- **Fraction/rate** contract: `0.125` represents 12.5%; use the percent formatter directly.
- **Percentage points** contract: `12.5` represents 12.5%; to use a percent formatter, convert it to `0.125` by dividing by 100, or format it explicitly another way.

### Rounding ratios

If maximum fraction digits is 1, the value **0.12345** may display as **12.3%** even though the exact corresponding value is 12.345%. The displayed string no longer retains all original digits. Do not store ratios back by parsing a rounded string and treating it as raw source data.

### Parsing percentage strings

A percent formatter normally parses **"12.5%"** into the ratio value **0.125** according to the corresponding Locale rules. Distinguish this operation from parsing a plain number **"12.5"**. Also check the `%` sign, whitespace, and numeric notation used by the Locale; do not assume every country places the `%` sign in the exact same position.

## 6. Currency: formatting money is not currency exchange

~~~java
NumberFormat usd = NumberFormat.getCurrencyInstance(Locale.US);
System.out.println(usd.format(1234.56)); // "$1,234.56"
~~~

A currency formatter uses symbol placement, grouping separators, decimal separators, and digit counts according to the Locale/currency formatter's metadata.

With `Locale.US`, the default currency is usually **USD** and displays the **`$`** symbol. In other Locales, the symbol may appear **after the number**, separated by a non-breaking space, or use a different currency form per localization settings. Do not manually concatenate **`"$" + formattedNumber`** and assume it is right for every country.

### Rounding and currency decimal digits

Each currency can have a different standard number of fractional digits (for example, USD typically uses 2; JPY typically uses 0). **`Currency.getDefaultFractionDigits()`** provides information per currency unit; however, it is **not the entirety of a transaction's rounding rules**. Settlements, taxes, cash handling, and legal regulations may have their own rules.

For example, when outputting USD with 2 digits, use:

~~~java
NumberFormat money = NumberFormat.getCurrencyInstance(Locale.US);
money.setMinimumFractionDigits(2);
money.setMaximumFractionDigits(2);
money.setRoundingMode(java.math.RoundingMode.HALF_UP);

String shown = money.format(new java.math.BigDecimal("1234.567"));
// "$1,234.57"
~~~

**Do not use the formatted string as the place to store monetary values.** In the example, the `BigDecimal` value remains 1234.567, whereas the display string has only 2 digits after the decimal point.

### `Currency.getInstance` and `setCurrency`

~~~java
java.util.Currency euro = java.util.Currency.getInstance("EUR");
NumberFormat formatter = NumberFormat.getCurrencyInstance(Locale.US);
formatter.setCurrency(euro);
~~~

Calling **`setCurrency(euro)`** changes the currency metadata used by the formatter; **it does not convert an exchange rate from USD to EUR**. A value of 100 remains 100 according to the passed data. Converting requires an exchange rate, timestamp, rounding policy, and corresponding business logic.

**Important API note:** **`NumberFormat.setCurrency(...)` does not automatically update minimum/maximum fraction digits**. If you change the `Currency` of an already-created formatter, review and reconfigure the digit counts when needed instead of expecting them to update automatically for the new currency.

### ISO codes vs non-unique symbols

**`Currency.getCurrencyCode()`** returns codes like **USD**, **EUR**, or **VND**. The symbol **`$`** can mean different things in different countries. When data flows across services/APIs, pass the **ISO currency code** as a separate field rather than relying solely on a user-facing symbol.

## 7. `Locale` governs display and parsing semantics

`NumberFormat.getNumberInstance(Locale.US)` typically uses a comma for grouping and a dot for the decimal point; `Locale.GERMANY` typically uses a dot for grouping and a comma for the decimal point. Do not use `Locale.getDefault()` for data with a fixed contract or repeatable tests. For inputs containing regional separators, `Double.parseDouble` does not understand locales automatically. In-depth verification of signs, numeric characters, negative signs, and grouping is covered in `Locale, decimal separator, digit grouping, and negative signs`.

## 8. Digits and rounding when formatting

`setMinimumFractionDigits`/`setMaximumFractionDigits`, `setMinimumIntegerDigits`, `setGroupingUsed`, and `setRoundingMode` change how a **value** is printed, without altering the source number. For instance, `getNumberInstance(Locale.US)` configured with at most two fractional digits may print `12.35` from source `12.345` under an appropriate mode, while the source variable remains `12.345`. The number of displayed digits differs from the binary precision of `double` and differs from the scale of `BigDecimal`. The two lessons on digit limits and `RoundingMode` detail these policies.

## 9. Parsing via `NumberFormat` requires a data contract

`NumberFormat.parse(String)` can consume a **valid prefix** and ignore the trailing portion without throwing `ParseException`. When an input field must contain only a number, use `parse(text, new ParsePosition(0))` and check `result != null` together with `position.getIndex() == text.length()`; this check alone still does not guarantee strict grouping compliance.

```java
java.text.ParsePosition pos = new java.text.ParsePosition(0);
java.text.NumberFormat nf = java.text.NumberFormat.getNumberInstance(java.util.Locale.US);
String input = "123abc";
Number n = nf.parse(input, pos);
System.out.println(n != null && pos.getIndex() == input.length()); // false
```

The lesson `ParsePosition and whole-string validation` goes deeper into error indices, UTF-16 indices, and strict validation.

## 10. When exact decimals are needed

`NumberFormat.parse` returns `Number`, which may be `Long`, `Double`, or another type depending on configuration. When you need to parse localized strings directly into finite `BigDecimal`, `DecimalFormat.setParseBigDecimal(true)` is an option; check the actual subtype because `NaN`/`Infinity` tokens can return `Double`. Do not go through `doubleValue()` before constructing a decimal that needs exactness. The lesson `setParseBigDecimal and thread-safety limits when using formatters concurrently` thoroughly discusses return types, `-0.0`, and safety across threads.

## 11. Compilable/runnable Java 17+ program

Create the file **NumberFormatDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberFormatDemo {
    static BigDecimal parseWhole(String text, DecimalFormat format) {
        ParsePosition pos = new ParsePosition(0);
        Number parsed = format.parse(text, pos);
        if (!(parsed instanceof BigDecimal)
                || pos.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid localized number");
        }
        return (BigDecimal) parsed;
    }

    public static void main(String[] args) {
        NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
        number.setGroupingUsed(true);
        number.setMinimumFractionDigits(2);
        number.setMaximumFractionDigits(2);
        number.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("number: " + number.format(12345.678));

        NumberFormat noGrouping = NumberFormat.getNumberInstance(Locale.US);
        noGrouping.setGroupingUsed(false);
        noGrouping.setMaximumFractionDigits(0);
        System.out.println("no grouping: " + noGrouping.format(12345));

        NumberFormat integer = NumberFormat.getIntegerInstance(Locale.US);
        System.out.println("integer: " + integer.format(12345.6));

        NumberFormat percent = NumberFormat.getPercentInstance(Locale.US);
        percent.setMinimumFractionDigits(1);
        percent.setMaximumFractionDigits(1);
        percent.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("percent: " + percent.format(0.1234));
        System.out.println("percent one: " + percent.format(1.0));

        NumberFormat money = NumberFormat.getCurrencyInstance(Locale.US);
        money.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("currency: "
                + money.format(new BigDecimal("1234.567")));
        System.out.println("currency code: "
                + money.getCurrency().getCurrencyCode());

        NumberFormat candidate = NumberFormat.getNumberInstance(Locale.US);
        if (!(candidate instanceof DecimalFormat)) {
            throw new IllegalStateException("DecimalFormat is required");
        }
        DecimalFormat parser = (DecimalFormat) candidate;
        parser.setParseBigDecimal(true);

        BigDecimal parsed = parseWhole("1,234.50", parser);
        System.out.println("parsed exact: " + parsed.toPlainString());
        try {
            parseWhole("1,234.50 xyz", parser);
        } catch (IllegalArgumentException e) {
            System.out.println("trailing text: rejected");
        }

        BigDecimal precise = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal sum: " + number.format(precise));

        NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);
        german.setMinimumFractionDigits(2);
        german.setMaximumFractionDigits(2);
        System.out.println("de number: " + german.format(12345.67));
    }
}
~~~

Run on JDK 17 or newer:

~~~bash
javac --release 17 NumberFormatDemo.java
java NumberFormatDemo
~~~

Stdout verified on the JDK with the Locales listed above:

~~~text
number: 12,345.68
no grouping: 12345
integer: 12,346
percent: 12.3%
percent one: 100.0%
currency: $1,234.57
currency code: USD
parsed exact: 1234.50
trailing text: rejected
decimal sum: 0.30
de number: 12.345,67
~~~

Points to explain:

- **number**: groups thousands, keeps exact two digits on display, and rounds `HALF_UP` from 12345.678.
- **integer**: the integer factory produces a string with no fractional part, yet accepts a `double` input.
- **percent**: the ratio 0.1234 is multiplied per percent semantics and displayed as 12.3%.
- **currency**: `BigDecimal("1234.567")` itself is unchanged; the formatter outputs two digits for USD.
- **parsed exact**: `DecimalFormat` returns a `BigDecimal` retaining 1234.50 (including scale matching the parsed string in this case).
- **trailing text**: parsing can stop before the last character, and `parseWhole` proactively rejects it because the whole string was not consumed.
- **decimal sum**: `BigDecimal("0.1") + BigDecimal("0.2")` yields exact 0.3; the `number` configuration with minimum 2 digits outputs 0.30.
- **de number**: grouping and decimal separators swap positions compared to `Locale.US`.

With specialized Locales or custom providers, spelling and whitespace may differ. When writing real tests, fix the `Locale` and understand the runtime's localization data.

## 12. `NumberFormat` and exact money: separated responsibilities

A financial system typically needs to distinguish:

1. **Business value**: exact decimal number, currency unit, scale/precision, and conversion rules if applicable.
2. **Calculation and rounding by business rules**: e.g., rounding unit prices, taxes, and invoice totals in a specific order.
3. **Display**: using `NumberFormat`/`DecimalFormat` matching the `Locale` to create human-readable strings.
4. **Input parsing from UI**: parsing per `Locale` and verifying currency unit, range, and established rules.

If you compute with `double`, decimals often cannot be represented completely accurately; formatting into a pretty string does not fix errors that already occurred. For money, you can use **`BigDecimal` from strings** and **`RoundingMode`** per contract, leaving `NumberFormat` solely for display.

Do not confuse these two operations:

- **`format(new BigDecimal("1.235"))`** producing **`"1.24"`** under `HALF_UP` with two digits: **rounding at the presentation stage**.
- **`value.setScale(2, HALF_UP)`**: creating a **new `BigDecimal` value** rounded by business rules for use in calculations/persistence.

Both operations may show the same number on screen, yet when the rule applies inside the system can be very different. All data must satisfy monetary policies before posting to ledgers.

## 13. Formatters are mutable objects

`NumberFormat` and `DecimalFormat` have many setters, so do not share one mutable instance across concurrent requests without proper synchronization. Use local instances, thread-confined mechanisms, or well-designed synchronization. The lesson `setParseBigDecimal and thread-safety limits when using formatters concurrently` presents code and trade-offs for each approach.

## 14. Display format differs from data-exchange format

Locale-formatted strings like `1,234.56` or `1.234,56` suit UIs, whereas a machine-to-machine protocol must specify explicit syntax and numeric types. Do not use `NumberFormat` to generate JSON numbers or canonical CSV. The lesson `Do not use human-formatted strings as the default data-exchange format` explains schemas and serializers in detail.

## 15. Common mistakes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `NumberFormat` without a fixed `Locale` for snapshot tests | Runner machines have different default Locales | Pass `Locale` explicitly |
| Using `getNumberInstance` to display percentages | Does not multiply ratio by 100 or add `%` | Use `getPercentInstance` if data is a ratio |
| Passing 12.5 into a percent formatter expecting 12.5% | Becomes 1250% | Pass 0.125 or align the data contract |
| Concatenating `"$"` with a formatted number | Wrong position/symbol in many countries | Use `getCurrencyInstance(locale)` |
| Calling `setCurrency` and thinking it converted exchange rates | It only changes metadata/display | Convert currency in separate business logic |
| Changing `Currency` and assuming fraction digits update automatically | `setCurrency` does not update min/max fraction digits | Reconfigure digit counts appropriately |
| Assuming formatting does not round | Digit limits can trigger rounding | Choose `RoundingMode` and max digits explicitly |
| Using `double` for exact decimal monetary math | Binary error can accumulate | Use `BigDecimal` + rounding rules |
| Parsing a string and ignoring the rest | `"123abc"` can be partially parsed | Check `ParsePosition.getIndex()` |
| Believing `ParsePosition` alone validates all syntax | Parsers can be lenient with grouping | Add business grammar validation |
| Casting `NumberFormat.parse` result directly to `BigDecimal` | Result can be `Long`/`Double` | `DecimalFormat.setParseBigDecimal` or dedicated parser |
| Sharing a mutable `NumberFormat` across all threads | Thread safety is not guaranteed | One instance per thread/request |
| Converting numbers to UI strings and storing them as source numbers | Loses digits/scale and becomes Locale-dependent | Store numeric data per domain model |
| Swapping dots and commas with `String.replace` | Can swap decimal and grouping separators by mistake | Parse with the proper `Locale` |

## 16. Self-check exercises

**Exercise 1:** What does **`getPercentInstance(Locale.US).format(0.25)`** mean? What if you pass 25?

*Answer:* `0.25` displays `25%`. Passing `25` gives `2500%`, because the formatter treats the argument as a raw ratio and multiplies by 100 when formatting.

**Exercise 2:** How do **`getNumberInstance(Locale.US)`** and **`getNumberInstance(Locale.GERMANY)`** differ when formatting 12345.67?

*Answer:* US uses **12,345.67**, while Germany typically uses **12.345,67**. Same numeric value, different presentation.

**Exercise 3:** A value `BigDecimal("1234.567")` is formatted in USD as `"$1,234.57"`. Does the original `BigDecimal` change?

*Answer:* No. Formatting creates a rounded display **string**; the immutable `BigDecimal` still represents 1234.567.

**Exercise 4:** Why does calling `setCurrency(EUR)` on a currency formatter displaying USD not mean 100 USD has been converted to EUR?

*Answer:* The API only switches the currency used for labeling/formatting; it has no exchange rate or conversion calculation.

**Exercise 5:** Why is `NumberFormat.parse("1,234.50 extra")` insufficient for full-string validation?

*Answer:* The parser may stop at the end of the numeric part and ignore the remainder. Use **`ParsePosition`** to verify the whole string was read, and still validate syntax/range per business rules.

**Exercise 6:** When you need to parse decimal digits into `BigDecimal`, which method is used?

*Answer:* On `DecimalFormat`, call **`setParseBigDecimal(true)`**; check both the parse result and the entire input. You cannot assume every `NumberFormat` returns a `DecimalFormat` or that default parsing always returns `BigDecimal`.

**Exercise 7:** In a multithreaded server, why should you not mutate the configuration of a static `NumberFormat` on each request?

*Answer:* Formatters are mutable and generally unsynchronized; threads may observe partially modified state. Use separate instances per thread/request.

**Exercise 8:** When writing numbers to JSON and CSV for other machines to read, should you use a user-locale `NumberFormat` as the data transport format?

*Answer:* No. Use standard types/strings specified by the protocol and an appropriate serializer; `NumberFormat` is for Locale-based presentation.

## 17. Official references

- [NumberFormat Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): Locale factories, NumberFormat, percent, currency, parsing, rounding, and synchronization.
- [DecimalFormat Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): format symbols, `DecimalFormatSymbols`, `setParseBigDecimal`, parsing.
- [ParsePosition Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): parse position, checking remaining text.
- [Currency Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): currency codes and default fraction digits.
- [RoundingMode Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) and [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal rounding behavior and exact decimal number model.