# Decimal Separators, Grouping, and Numbering Systems by Locale

## 1. Why Does the Same Number Have Multiple Written Forms?

The numeric value `1234567.89` does not change when a user switches languages or regions, but its **textual representation** can change completely. In Java Core Localization, `java.text.NumberFormat` and `java.text.DecimalFormat` are responsible for using locale data to determine the decimal separator, grouping separator, digits, grouping rules, numbering system, and other formatting characteristics.

Several corresponding representations (with typical CLDR data):

| Locale | Example representation of `1234567.89` | Decimal separator | Grouping separator |
| --- | --- | --- | --- |
| `en-US` | `1,234,567.89` | `.` | `,` |
| `vi-VN` | `1.234.567,89` | `,` | `.` |
| `de-DE` | `1.234.567,89` | `,` | `.` |
| `fr-FR` | `1 234 567,89` | `,` | narrow no-break space U+202F |
| `ar-EG` | `١٬٢٣٤٬٥٦٧٫٨٩` | U+066B (`٫`) | U+066C (`٬`) |

The `fr-FR` row in the table **does not use an ordinary ASCII space** between groups; it uses character U+202F, even though the naked eye may struggle to tell them apart. The `ar-EG` row uses **Arabic-Indic digits** and its own separators. Specific characters and rules may vary across Java versions, locale data providers, and numbering system options; the examples above were verified on a JDK runtime using CLDR data.

**The most important rule:** there is no universal rule that "a period is always the decimal separator" or "a comma is always the grouping separator" for every locale. Nor can you assume displayed digits are always `0`–`9` (U+0030–U+0039).

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **decimal separator**, **grouping separator**, and **grouping pattern**.
2. Use `NumberFormat`/`DecimalFormatSymbols` to format numbers for a specific locale.
3. Understand Unicode numbering systems and BCP 47 tags with the `u-nu-*` extension.
4. Avoid confusing human-facing number representations with machine storage/communication representations.
5. Parse numbers with separators in a controlled manner, detect trailing content, and avoid precision loss.
6. Understand the differences among general number, currency, and percentage formatting, as well as cross-runtime limitations.

## 2. Three Components That Must Be Kept Separate

### 2.1. Decimal Separator

The decimal separator divides the integer part and the fractional part.

```text
en-US:  12.5
vi-VN:  12,5
ar-EG:  ١٢٫٥
```

Thus `12,5` can mean twelve point five in one locale, while another locale's parser will not interpret it the same way. In the Java API, the decimal separator for general number formatting can be inspected via `DecimalFormatSymbols.getDecimalSeparator()`.

Do **not** use `String.replace(",", ".")` to convert arbitrary international number strings to canonical form: a comma may be a grouping separator, a decimal separator, or part of malformed input.

### 2.2. Grouping Separator

The grouping separator separates digit groups to make large numbers easier to read.

```text
en-US: 1,234,567
vi-VN: 1.234.567
fr-FR: 1 234 567
ar-EG: ١٬٢٣٤٬٥٦٧
```

The grouping separator is not part of the **numeric value**. It is a presentation character inserted according to the locale, and some format styles may omit grouping. Java lets you disable grouping via `formatter.setGroupingUsed(false)`; doing so does **not** change the decimal separator or turn the number into a canonical storage string.

A grouping separator may be a **Unicode non-breaking space** such as U+00A0 or U+202F. Therefore:

- `"1 234"` containing U+0020 (ASCII space) may not be accepted by a locale's parser the same way as `"1 234"` containing U+202F.
- `trim()`, `split(" ")`, and manual "space" replacements are not reliable ways to process localized numeric data.
- When output looks right on screen but fails to parse, inspect the **code points** rather than relying solely on how the font renders them.

### 2.3. Grouping Pattern

Not all linguistic systems divide numbers into groups of three from right to left. For example, grouping in the Indian numbering convention:

```text
12,34,567.89
```

The three rightmost digits (`567`) are accompanied by two-digit groups (`34`, `12`). This is the **grouping pattern**, which is completely distinct from the grouping separator character. Two formats can use the same comma character yet produce different results if their patterns differ.

**Important JDK limitation:** traditional `java.text.DecimalFormat` does not provide a general mechanism to express *two different group sizes* solely with a pattern like `#,##,##0`. Multiple grouping markers in a pattern are normalized based on the final group; testing `#,##,##0.00` on the JDK yields `#,##0.00` and formats `1,234,567.89`. Additionally, `NumberFormat.getNumberInstance(Locale.forLanguageTag("hi-IN"))` on a JDK runtime may still output three-digit grouping `1,234,567.89`. **Do not claim that simply setting `hi-IN` guarantees lakh/crore grouping on every JDK**; if the business requires Indian grouping, test the target runtime's provider/version and consider the ICU library, which supports the appropriate pattern data.

## 3. Numbering System Is More Than Just Separators

The familiar Latin digits:

```text
0 1 2 3 4 5 6 7 8 9
```

are only **one set of digit characters**. Some locales use a different numbering system to represent the same values:

| System / `nu` code | Example digits 0–4 | Purpose |
| --- | --- | --- |
| `latn` | `0 1 2 3 4` | Latin digits |
| `arab` | `٠ ١ ٢ ٣ ٤` | Arabic-Indic digits |
| `arabext` | `۰ ۱ ۲ ۳ ۴` | Extended Arabic-Indic digits |
| `deva` | `० १ २ ३ ४` | Devanagari digits |
| `thai` | `๐ ๑ ๒ ๓ ๔` | Thai digits |

These are **display characters**, not different arithmetic values. In Java, `Character.digit(...)` can recognize many Unicode digits, but that does **not guarantee** every parsing API supports every numbering system or every combination of separators. Use an appropriate locale-aware API and check your input policy.

### Unicode Locale Extension `nu` in BCP 47

A `Locale` can carry a Unicode locale extension to select a numbering system:

```text
en-US-u-nu-arab
ar-EG-u-nu-latn
th-TH-u-nu-thai
```

- `en-US-u-nu-arab`: US English requesting numbers to be represented using the `arab` system.
- `ar-EG-u-nu-latn`: Egyptian Arabic requesting Latin digits.
- `th-TH-u-nu-thai`: Thai (Thailand) requesting the Thai digit system.

These objects are created with `Locale.forLanguageTag(tag)`; the value can be retrieved with `locale.getUnicodeLocaleType("nu")`. For example:

```java
Locale locale = Locale.forLanguageTag("en-US-u-nu-arab");
System.out.println(locale.getUnicodeLocaleType("nu")); // arab
```

This is an **illustrative snippet inside a method** with `import java.util.Locale;`, not a standalone program.

**Limitation:** having `nu` in the tag is **not a guarantee** that every `NumberFormat`, JDK version, and locale provider supports the requested numbering system. Some numbering systems are not contiguous base-10 decimal digits; some APIs will fall back to defaults or fail to format as the user expects. Test on the actual runtime, especially when `nu` comes from user input.

## 4. Core Java APIs: Which Class to Use?

| Class / method | Role | Notes |
| --- | --- | --- |
| `NumberFormat.getNumberInstance(locale)` | Format/parse general numbers by locale | Factory taking an explicit `Locale` |
| `NumberFormat.getIntegerInstance(locale)` | Format/parse integer style | May round when formatting; do not use as a substitute for input validation |
| `NumberFormat.getCurrencyInstance(locale)` | Format currency by locale | Includes currency symbol, fractional rules, and currency-specific signs |
| `NumberFormat.getPercentInstance(locale)` | Format percentages | Typically multiplies value by 100 when formatting |
| `DecimalFormat` | Custom patterns, rounding, parsing `BigDecimal` | Common implementation for decimal numbers |
| `DecimalFormatSymbols.getInstance(locale)` | Retrieve separators/digits/symbols by locale | Inspect `getZeroDigit()`, `getDecimalSeparator()`, `getGroupingSeparator()` |
| `NumberFormat.setGroupingUsed(...)` | Enable/disable grouping separator display | Does not change numeric value |
| `NumberFormat.setMinimumFractionDigits(...)` | Minimum fractional digits | May pad zeros |
| `NumberFormat.setMaximumFractionDigits(...)` | Maximum fractional digits | May round to shorten |
| `DecimalFormat.setParseBigDecimal(true)` | Parse real numbers into `BigDecimal` | Check full string consumption if strict input is needed |

Formatters like `DecimalFormat`/`NumberFormat` are **not guaranteed to be thread-safe**. On a multi-user server, avoid holding a mutable formatter instance in a static singleton shared across requests; create per request/operation, or manage lifecycle separately without concurrent sharing. `Locale` itself is immutable and can be passed safely across threads.

**Do not call `Locale.setDefault(userLocale)` per request.** The default locale is shared JVM-wide state and can cause language bleed across requests. Pass the proper `Locale` into the factory instead.

## 5. Java 17+ Example: Comparing Separators Across Locales

Create `NumberLocaleDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberLocaleDemo {
    private static String code(char symbol) {
        return String.format("U+%04X", (int) symbol);
    }

    private static void show(String languageTag) {
        Locale locale = Locale.forLanguageTag(languageTag);
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        String result = formatter.format(new BigDecimal("1234567.89"));
        // Make U+202F explicit in output so it is easy to inspect.
        String visible = result.replace("\u202F", "<NNBSP>");
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);

        System.out.println(languageTag + ": " + visible);
        System.out.println("  digits-zero=" + code(symbols.getZeroDigit())
                + ", decimal=" + code(symbols.getDecimalSeparator())
                + ", grouping=" + code(symbols.getGroupingSeparator()));
    }

    public static void main(String[] args) {
        show("en-US");
        show("vi-VN");
        show("fr-FR");
        show("ar-EG-u-nu-latn");
        show("ar-EG");
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 NumberLocaleDemo.java
java NumberLocaleDemo
```

Reference output on a JDK using CLDR with verified symbols:

```text
en-US: 1,234,567.89
  digits-zero=U+0030, decimal=U+002E, grouping=U+002C
vi-VN: 1.234.567,89
  digits-zero=U+0030, decimal=U+002C, grouping=U+002E
fr-FR: 1<NNBSP>234<NNBSP>567,89
  digits-zero=U+0030, decimal=U+002C, grouping=U+202F
ar-EG-u-nu-latn: 1,234,567.89
  digits-zero=U+0030, decimal=U+002E, grouping=U+002C
ar-EG: ١٬٢٣٤٬٥٦٧٫٨٩
  digits-zero=U+0660, decimal=U+066B, grouping=U+066C
```

`<NNBSP>` is only an **illustrative marker substituted by the program for U+202F to print clearly**, not part of the originally formatted number. The actual character inside the string is U+202F. Character differences can make two strings look nearly identical while `String.equals` returns `false`.

Explanation:

- For `en-US`, the decimal separator is U+002E (`.`), and the grouping separator is U+002C (`,`).
- For `vi-VN`, the two separators swap roles; the display matches `de-DE` for the example data.
- For `fr-FR`, the grouping separator is U+202F (*narrow no-break space*); preserve Unicode intact when presenting and testing data.
- For `ar-EG-u-nu-latn`, the `nu=latn` extension requests Latin digits and separators on the tested environment.
- For `ar-EG`, the `arab` numbering system uses digits starting at U+0660, U+066B for decimal, and U+066C for grouping.

Exact locale data results depend on the runtime/provider; when building snapshot tests, pin the Java version and provider or assert business-relevant properties rather than assuming every JDK behaves identically.

## 6. Grouping Can Be Toggled Independently

On some UI screens, grouping separators improve readability; in some code formats or technical input fields, you may want to omit grouping:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class GroupingToggleDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;
        NumberFormat formatter = NumberFormat.getNumberInstance(locale);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        BigDecimal value = new BigDecimal("1234567.89");
        System.out.println(formatter.format(value));

        formatter.setGroupingUsed(false);
        System.out.println(formatter.format(value));
    }
}
```

```bash
javac GroupingToggleDemo.java
java GroupingToggleDemo
```

```text
1,234,567.89
1234567.89
```

Disabling grouping does not mean you are producing canonical serialization for all situations: the locale may still use a `,` decimal separator or non-Latin digits. A value used for a JSON number, technical config, or API protocol needs a **locale-independent** storage contract.

### Be Careful with `DecimalFormat` Patterns

A standard pattern:

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
```

The pattern `#,##0.00` has:

- `#`: optional digit.
- `0`: required digit.
- `,`: grouping position in a **non-localized pattern**.
- `.`: decimal position in a **non-localized pattern**.

The `.`/`,` symbols in a standard pattern are **not necessarily the characters emitted in output**. Output characters come from the locale's `DecimalFormatSymbols`. `applyPattern(...)` uses standard pattern syntax; `applyLocalizedPattern(...)` uses localized pattern symbols. Do not manually swap every dot/comma in a pattern expecting exact results.

In this example, the snippet is **illustrative** with `import java.text.DecimalFormat;`, `import java.text.DecimalFormatSymbols;`, and `import java.util.Locale;`. If you just need a simple locale-specific formatter, prefer the `NumberFormat.getNumberInstance(locale)` factory rather than authoring patterns unnecessarily.

## 7. Parsing: Same String, Different Meaning by Locale

The following two strings cannot be interpreted reliably without knowing the source's language policy:

```text
1,234
1.234
```

Example with `NumberFormat`:

- `en-US` typically interprets `1,234` as one thousand two hundred thirty-four.
- `de-DE` typically interprets `1,234` as one point two three four.

Simply swapping symbols with `replace` can cause serious errors when processing monetary amounts, measurements, statistics, or transaction data. What matters is **parsing with the locale in which the data was entered**, not necessarily the server's locale. If the data is already stored as a JSON number, locale-based parsing is not needed.

### Java 17+ Example: Parsing Both Ways and Checking the Full String

Create `LocaleParsingDemo.java`:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParsingDemo {
    public static void main(String[] args) throws Exception {
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat germany =
                NumberFormat.getNumberInstance(Locale.GERMANY);

        System.out.println("en-US: " + us.parse("1,234"));
        System.out.println("de-DE: " + germany.parse("1,234"));

        String input = "1,234.56xyz";
        DecimalFormat decimal = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
        decimal.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = decimal.parse(input, position);

        boolean fullyConsumed = parsed != null
                && position.getIndex() == input.length();

        System.out.println("value: " + parsed);
        System.out.println("type: " + parsed.getClass().getSimpleName());
        System.out.println("consumed: " + position.getIndex());
        System.out.println("fully valid: " + fullyConsumed);
    }
}
```

```bash
javac LocaleParsingDemo.java
java LocaleParsingDemo
```

Output:

```text
en-US: 1234
de-DE: 1.234
value: 1234.56
type: BigDecimal
consumed: 8
fully valid: false
```

Here:

1. The same input `1,234` produces different values when parsed under different locales.
2. `setParseBigDecimal(true)` yields a `BigDecimal` instead of a binary floating-point number that might lose precision.
3. `parse(input, position)` **can successfully parse a prefix** and ignore an invalid suffix. Does `"1,234.56xyz"` have nine characters in its numeric part? In the example, the parser consumes exactly **8 characters** (`"1,234.56"`), leaving `"xyz"`; checking `position.getIndex() == input.length()` catches the trailing garbage.

**Important note on validation:** consuming the entire string also **does not automatically verify that grouping separator placement complies with all business rules**. A number parser can accept grouping separator combinations that do not match the expected pattern. For high-security/high-precision inputs, define a clear locale policy, allowed characters, value ranges, and precision, and validate formatting thoroughly or normalize according to the source standard before using the data. Avoid assuming that merely calling `NumberFormat.parse(...)` suffices to validate financial fields.

## 8. Precision and Rounding: Right Characters Does Not Mean Exact Value

`NumberFormat` does two things that affect data presentation: it determines **how characters are displayed**, and it can **round** when a maximum number of fractional digits is set.

Example:

```java
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);
```

Two digits after the decimal separator are always shown where possible, while values with more than two fractional digits are rounded according to the current `RoundingMode`. Do not mistake the formatted result for a number more exact than the original data.

For money in particular, use `BigDecimal` constructed from a string or exact arithmetic (`new BigDecimal("0.1")`), not `new BigDecimal(0.1)` if you want to represent the exact decimal 0.1 entered by a user. Set rounding according to business rules rather than implicitly relying on the formatter's default.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingLocaleDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println(formatter.format(new BigDecimal("1234.565")));
    }
}
```

```bash
javac RoundingLocaleDemo.java
java RoundingLocaleDemo
```

```text
1,234.57
```

This example illustrates the **specified rounding rule**; it does not mean the `en-US` locale always mandates `HALF_UP`. Locale describes display conventions; rounding is chosen by the domain and API.

## 9. Display Data Differs from Storage Format

Two processing paths must be clearly separated:

### 9.1. Data for Human Readers

```text
BigDecimal("1234567.89") + Locale vi-VN
                ↓ NumberFormat
            1.234.567,89
```

This string is used in UIs, localized reports, invoices, or translated content. It may contain subtle Unicode characters or non-Latin digits. This is **display output**, not a standard for transmitting numbers between services.

### 9.2. Data for Machines / Protocols

```text
BigDecimal("1234567.89").toPlainString()
                ↓
            1234567.89
```

In JSON, numbers are represented according to JSON number syntax, **not** according to the default `Locale`. For data requiring precision preservation, consider a number type, decimal string, or integer minor units in the schema depending on the domain; never send `"1.234.567,89"` and force the server to guess.

Avoid:

```java
// Not recommended for locale-independent number storage:
String stored = NumberFormat.getNumberInstance(
        Locale.getDefault()).format(amount);
```

Reason: if the default locale changes across machines, JVMs, or users, the same numeric value will be serialized into different strings. When parsed back later without the original locale, the data becomes ambiguous.

Separate two layers:

- **Domain layer:** use `int`/`long`/`BigDecimal` with standard types and operations.
- **Presentation layer:** obtain the user's `Locale` and format for display; when receiving localized string input, parse with the verified locale.

## 10. Currency, Percentages, and Cases Requiring Caution

`NumberFormat.getNumberInstance(locale)` is not synonymous with every number in every context. The following factories serve different conventions:

```java
NumberFormat amount = NumberFormat.getNumberInstance(locale);
NumberFormat money = NumberFormat.getCurrencyInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
```

This is an **illustrative snippet** assuming `locale` and `import java.text.NumberFormat;` are declared.

- **Currency:** currency symbol, symbol position, fractional digits, and separators can depend on both locale and currency. In multi-currency domains, you must also specify the exact **`Currency`**; a locale is not a transaction currency code.
- **Percentages:** many formatters convert `0.12` into a 12% representation; do not pass `12` directly if the domain stores 12 percent as `0.12` without checking the contract. The percent symbol and spacing can also vary.
- **Negative numbers:** minus signs, sign order, and patterns can vary by locale and formatter style.
- **Compact / scientific modes:** `NumberFormat.getCompactNumberInstance(...)` and scientific formats have their own semantics. Do not use a general-number grouping algorithm to build all these formats.
- **Bidirectional text (RTL):** when displaying Arabic numbers in UIs mixing Latin and Arabic text, account for text direction and Unicode bidi controls; do not strip Unicode characters via manual `replace` just because the visual ordering looks unexpected.

From an i18n perspective, **digits, separators, and grouping belong to locale data and formatting options**, whereas **units of measure, currencies, and precision** belong to application domain semantics.

## 11. Checklist for Handling Locale-Aware Numbers in Applications

1. **Resolve locale per user/request:** use reliable preferences, validate, and restrict to supported locales. Never mutate `Locale.setDefault` on a server.
2. **Know the exact data type:** integer, exact decimal, currency, percentage, or measurement. Choose `BigDecimal` when decimal precision matters.
3. **Choose the right formatter factory:** general number, currency, percentage, or a tested custom pattern.
4. **Pass locale explicitly:** `getNumberInstance(locale)`, independent of machine configuration.
5. **Configure grouping and fraction digits per UI goal**, rather than forcing one default across the whole app.
6. **Choose rounding mode when rounding has business impact**; distinguish display rounding from values used in calculations.
7. **Verify separators by code point** when encountering Unicode spaces or non-Latin digits.
8. **Respect `u-nu`** when supported by the provider, without assuming every numbering system is universally supported.
9. **Parse using the input source's locale**, use `ParsePosition` to check full consumption, and add domain validation.
10. **Separate locale-independent storage formats** from display strings.
11. **Test actual locales on the target JDK/provider**, especially Indian grouping, Arabic digits, RTL, and non-breaking spaces.
12. **Do not share mutable `DecimalFormat` across threads** without proper isolation.

## 12. Common Mistakes and Fixes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| `Double.parseDouble("1,5")` assuming vi-VN locale applies | `Double.parseDouble` requires locale-independent syntax without a `,` decimal mark | Use locale-aware `NumberFormat` for user input |
| Using `replace(",", ".")` on all strings | `,` can be a grouping separator; `1,234` is ambiguous | Parse using the source locale |
| Treating French grouping whitespace as ASCII space | Data may use U+202F/U+00A0 | Check code points; use locale formatter/parser |
| Using `#,##,##0` assuming the JDK always produces Indian grouping | Traditional `DecimalFormat` has multi-size grouping limitations | Test on runtime; use a supporting library if required |
| Always expecting U+0030–U+0039 digits | Some numbering systems use different digits | Use APIs honoring locale/`u-nu` |
| Assuming `u-nu-arab` guarantees every API switches to Arabic digits | Support depends on provider/API | Test actual support and output |
| Using `NumberFormat.format` to store numbers in DB/API | Output depends on locale | Store numbers or decimal strings with a standard schema |
| Parsing a string with trailing characters unchecked | `parse` may stop before end of string | Check `ParsePosition.getIndex()` and add extra validation |
| Using `double` for all monetary math | Binary floating-point rounding errors | Use `BigDecimal` or integer minor units per domain |
| Using one static `DecimalFormat` for all threads | Mutable formatter is not guaranteed thread-safe | Create a separate instance per request/operation |
| Treating `Locale` as currency code or time zone | These are distinct concepts | Use `Currency` and `ZoneId` appropriately |
| Forgetting to test negatives, small numbers, 0, decimals, and large numbers | Formatting can differ at edge cases | Write a test matrix across locales and domain cases |

## 13. Self-Check Questions

1. For `1,234`, do `en-US` and `de-DE` interpret it the same way? **No.** It can be `1234` in en-US but `1.234` in de-DE.
2. Which character does `vi-VN` typically use for decimal and which for grouping? **Comma `,` for decimal, period `.` for grouping** in the example data.
3. Why shouldn't you write `replace(" ", "")` when handling `fr-FR` grouping separators? **Because the grouping separator may be U+202F, not U+0020; moreover, the operation risks altering other data.**
4. What does `u-nu-latn` in `ar-EG-u-nu-latn` indicate? **A request for the Latin numbering system; the formatter can honor it when supported by the provider.**
5. Does `DecimalFormatSymbols.getGroupingSeparator()` tell you the grouping size? **No.** It only specifies the grouping character; the grouping pattern is a separate rule.
6. Why doesn't `#,##,##0` on `DecimalFormat` necessarily produce `12,34,567`? **Because traditional `DecimalFormat` does not support two arbitrary grouping sizes in the same pattern; it only stores the last group interval.**
7. Does `NumberFormat.setGroupingUsed(false)` guarantee the string always uses `.` as the decimal separator? **No.** The locale still determines the decimal separator character.
8. What is the bug with `parse("1,234.56xyz")` without `ParsePosition`? **It can parse the leading number and silently ignore `xyz` without throwing an error.**
9. Why is `BigDecimal("1234.56")` better for monetary values than `new BigDecimal(1234.56)`? **The string constructor avoids capturing binary representation error from the double literal.**
10. What is the difference between formatting `1.234,56` for users and storing `1234.56` in an API? **One is locale-specific presentation; the other is serialization with a locale-independent contract.**

## 14. References

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): locale-aware format/parse factories, grouping, fractional digits.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): patterns, `BigDecimal` parsing, rounding, thread safety, and grouping.
- [Java SE 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html): character codes for zero digit, decimal separator, and grouping separator.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): BCP 47 language tags, Unicode extension `nu`.
- [Unicode CLDR — Numbers](https://cldr.unicode.org/translation/number-currency-formats): numeric/currency pattern data and formatting conventions.
- [Unicode TR35 — Numbers](https://unicode.org/reports/tr35/tr35-numbers.html): numbering systems, number patterns, and localized symbols.