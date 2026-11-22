# Standard Patterns vs. Localized Patterns in Java `DecimalFormat`

## 1. Two kinds of patterns, one goal: locale-accurate number formatting

`java.text.DecimalFormat` turns a numeric value into a string or parses a string into a number based on a **pattern** and **`DecimalFormatSymbols`** (the symbol set). When formatting numbers across multiple languages, distinguish:

- **Standard / non-localized pattern:** syntax characters such as `.` for the decimal position and `,` for grouping are interpreted by **`DecimalFormat`'s fixed rules**, regardless of the active locale. For example, `#,##0.00`.
- **Localized pattern:** the corresponding syntax characters are represented using the symbols inside the formatter's `DecimalFormatSymbols`. For the German locale `de-DE`, the pattern with the same meaning is typically written `#.##0,00`: `.` is the grouping symbol, `,` is the decimal separator.

Do not confuse **pattern syntax** with **separators in the output string**. Setting a German locale does not force you to rewrite a standard pattern to `#.##0,00` when using `applyPattern` or the `DecimalFormat(String, DecimalFormatSymbols)` constructor. `DecimalFormat` will use German symbols to produce `1.234.567,89` from the standard pattern `#,##0.00`.

```text
Standard pattern:     #,##0.00
         |                         DecimalFormatSymbols(de-DE)
         +--- applyPattern(...)  --------------------------+
                                                          |
                                                    format(1234567.89)
                                                          |
                                               "1.234.567,89"

Localized pattern de-DE: #.##0,00
         |
         +--- applyLocalizedPattern(...), symbols(de-DE) -- same meaning
```

**Golden rule:** patterns used in **source code / shared config** should normally be in standard form; patterns that users **enter using local symbols** must be decoded via `applyLocalizedPattern` and the matching `DecimalFormatSymbols`.

## 2. APIs commonly misused

| API | Meaning | Note |
| --- | --- | --- |
| `new DecimalFormat(pattern, symbols)` | Creates a formatter from a **standard pattern**, using `symbols` for display | Do not pass a localized pattern to this constructor |
| `applyPattern(String)` | Applies a **standard pattern** | Does not infer meanings of `.`/`,` from locale |
| `applyLocalizedPattern(String)` | Applies a **localized pattern** using current symbols | Must set the right symbols **before** calling |
| `toPattern()` | Returns the formatter's **standard** pattern representation | May be a normalized form, not character-for-character identical to input |
| `toLocalizedPattern()` | Returns the pattern representation using **current symbols** | Not suitable to reuse verbatim for another locale |
| `DecimalFormatSymbols.getInstance(locale)` | Retrieves local symbols for numbers, currency, percent, etc. | Supplies symbols; does not mean locale chooses business logic |
| `setDecimalFormatSymbols(symbols)` | Replaces the formatter's symbol set | Affects output and how subsequent **localized patterns** are interpreted |

The two important conversion directions are:

```text
String canonical = formatter.toPattern();
String localized = formatter.toLocalizedPattern();

formatter.applyPattern(canonical);             // reads standard syntax
formatter.applyLocalizedPattern(localized);    // reads local syntax
```

These two `apply...` operations are **not interchangeable**. In particular, `applyLocalizedPattern` reads using the symbols on **the formatter itself at the moment of the call**, not by guessing whether the string "looks" German, French, or US.

## 3. Standard pattern syntax: `.` and `,` carry structural meaning only

In a **standard pattern** of `DecimalFormat`:

| Symbol | Primary role |
| --- | --- |
| `0` | Required digit position; pads with 0 when needed |
| `#` | Optional digit position |
| `.` | **Decimal position marker in the pattern** |
| `,` | **Digit grouping marker in the pattern** |
| `%` | Multiplies value by 100 and represents percent |
| `‰` | Multiplies value by 1000 and represents per-mille |
| `¤` | Currency symbol in the pattern, depending on symbols/currency |
| `E` | Scientific notation exponent component |
| `;` | Separates positive and negative subpatterns |
| `'` | Quotes literal characters in pattern prefixes/suffixes |

For example, `#,##0.00` means: use thousands grouping, at least one integer digit, and exactly two fractional digits.

**Crucial:** a `.` in a standard pattern **does not guarantee** the output has a period decimal point. Output uses the actual decimal separator from `DecimalFormatSymbols`, for instance:

| Value | Standard pattern | Symbols | Output |
| ---: | --- | --- | --- |
| `1234567.89` | `#,##0.00` | `Locale.US` | `1,234,567.89` |
| `1234567.89` | `#,##0.00` | `Locale.GERMANY` | `1.234.567,89` |

The examples only illustrate **separators**, not unit or currency conversion. `1234567.89` remains the same numeric value; language/region only affects presentation.

## 4. Java 17+ program: same standard pattern, two locales

Create the file **`StandardPatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class StandardPatternDemo {
    private static DecimalFormat create(Locale locale) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(locale);
        return new DecimalFormat("#,##0.00", symbols);
    }

    public static void main(String[] args) {
        DecimalFormat us = create(Locale.US);
        DecimalFormat de = create(Locale.GERMANY);

        double value = 1234567.89;

        System.out.println("US=" + us.format(value));
        System.out.println("DE=" + de.format(value));
        System.out.println("US standard=" + us.toPattern());
        System.out.println("DE standard=" + de.toPattern());
        System.out.println("DE localized=" + de.toLocalizedPattern());
    }
}
```

Run with JDK 17+:

```bash
javac -encoding UTF-8 StandardPatternDemo.java
java -cp . StandardPatternDemo
```

Output on JDKs with standard German/US locale data:

```text
US=1,234,567.89
DE=1.234.567,89
US standard=#,##0.00
DE standard=#,##0.00
DE localized=#.##0,00
```

Observe the two lines `US standard` and `DE standard`: they match because **the standard pattern does not change with locale**. Only `toLocalizedPattern()` reflects `de-DE` symbols. Output lines differ thanks to symbols.

Here the constructor accepts `DecimalFormatSymbols.getInstance(locale)` to cleanly isolate configuration. `new DecimalFormat("#,##0.00")` takes no locale and uses the environment's default symbols; avoid that style when stable per-user-language output is required.

## 5. `applyLocalizedPattern`: reading syntax for the selected locale

A configuration form in Germany might let users type the pattern `#.##0,00` directly. That string is **not** a standard pattern. When loading it:

1. Instantiate `DecimalFormat`.
2. Set `DecimalFormatSymbols` for the German locale.
3. Call `applyLocalizedPattern("#.##0,00")`.
4. Use `toPattern()` to obtain the standard version for storage/sharing or inspection.

Create **`LocalizedPatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LocalizedPatternDemo {
    public static void main(String[] args) {
        DecimalFormat formatter = new DecimalFormat();
        formatter.setDecimalFormatSymbols(
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        formatter.applyLocalizedPattern("#.##0,00");

        System.out.println("canonical=" + formatter.toPattern());
        System.out.println("localized=" + formatter.toLocalizedPattern());
        System.out.println("number=" + formatter.format(1234567.89));

        DecimalFormat wrong = new DecimalFormat();
        wrong.setDecimalFormatSymbols(
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        try {
            // Wrong: German pattern passed into the standard parser.
            wrong.applyPattern("#.##0,00");
            System.out.println("wrong accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("wrong: IllegalArgumentException");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 LocalizedPatternDemo.java
java -cp . LocalizedPatternDemo
```

Output with the example syntax above:

```text
canonical=#,##0.00
localized=#.##0,00
number=1.234.567,89
wrong: IllegalArgumentException
```

**Analysis:** when using `applyLocalizedPattern`, `.` in the German string is understood as grouping and `,` as decimal. When erroneously calling `applyPattern("#.##0,00")`, the standard parser must interpret `.` as decimal and `,` as grouping; that combination is invalid in the example, throwing `IllegalArgumentException`.

Do not generalize that **every** localized pattern passed to the wrong API throws an exception. Some strings may **be accepted yet carry the wrong meaning**, especially when separators and symbols in the two dialects partially overlap. Therefore, always record pattern provenance and test the output; never treat the absence of an exception as proof of valid configuration.

## 6. `toPattern()` and `toLocalizedPattern()`: representations, not two different formatters

Both methods return ways of writing the **same pattern configuration held by the formatter**:

```text
formatter:
  pattern logic  = grouping + 2 decimal digits
  symbols        = de-DE

  toPattern()          => "#,##0.00"
  toLocalizedPattern() => "#.##0,00"
```

**Do not store a localized pattern as a "universal cross-locale pattern".** For example, `#.##0,00` parsed with US symbols will have different syntax/meaning or be rejected. If an application lets users edit patterns in their own locale:

- Store the **standard pattern** using `toPattern()` after loading and validating.
- Store the **associated locale/symbol-set** when the formatting rule itself has regional significance.
- When reopening the configuration UI for the user, create a formatter with the active locale's symbols, call `applyPattern(storedCanonical)`, and then call `toLocalizedPattern()` to display it in local syntax.

**Note on round-tripping:** `toPattern()` and `toLocalizedPattern()` may return **normalized patterns**. They do not guarantee preserving exact characters, whitespace, or synonymous forms originally typed by the user. Test **formatting semantics and outputs** rather than comparing raw input strings in every case.

## 7. Format output differs from pattern input

Three layers are often conflated:

```text
             Pattern logic
     standard or localized syntax
                   |
        DecimalFormatSymbols
       (decimal, grouping, %, ...)
                   |
                DecimalFormat
                   |
              format(number)
                   |
         Localized numeric string
```

Because `DecimalFormat` supports both `format` and `parse`, keep a fourth layer in mind when **parsing user-entered strings**: the parser must know the matching symbols and settings.

Example:

```java
DecimalFormat de = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));

String output = de.format(1234567.89);
// output: "1.234.567,89"
```

This is an **illustrative snippet**, requiring imports `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, and `java.util.Locale`. When parsing user data, `DecimalFormat.parse(...)` can parse **part** of a string and stop; to catch trailing garbage, use `ParsePosition` and verify the index consumed the whole string.

Do not confuse:

- `applyPattern` parses **syntax describing how to format**.
- `format` generates **numeric text**.
- `parse` reads **numeric text** into a numeric value.
- `toLocalizedPattern` does not format values itself; it only expresses the pattern using local symbols.

A number like `1.234` can mean one thousand two hundred thirty-four in Germany or one point two three four in the US. You must know the locale of the **numeric text**, not guess by counting periods and commas.

## 8. Standard vs. localized patterns with percent, currency, and suffixes

Differences are not limited to decimal and grouping separators. `DecimalFormatSymbols` holds symbols for percent, per-mille, minus sign, zero digit, negative pattern separator, and currency symbol; exact localization details depend on data and configuration.

### 8.1. Percent

Standard pattern:

```text
#,##0.0%
```

With German symbols, `format(0.1234)` gives:

```text
12,3%
```

And `toLocalizedPattern()` in the corresponding example is:

```text
#.##0,0%
```

The `%` symbol in `DecimalFormat` is not just a printed suffix: it **multiplies the numeric value by 100 when formatting** and has the corresponding inverse effect when parsing. Do not multiply by 100 in data and also apply a `%` pattern, or you will scale twice.

Standalone example program **`PercentPatternDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PercentPatternDemo {
    public static void main(String[] args) {
        DecimalFormat percent = new DecimalFormat(
                "#,##0.0%",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        System.out.println(percent.format(0.1234));
        System.out.println(percent.toPattern());
        System.out.println(percent.toLocalizedPattern());
    }
}
```

Run:

```bash
javac -encoding UTF-8 PercentPatternDemo.java
java -cp . PercentPatternDemo
```

Output:

```text
12,3%
#,##0.0%
#.##0,0%
```

### 8.2. Currency

`¤` is the special currency pattern symbol, e.g., `¤#,##0.00`. Displayed results vary with `Currency` and `DecimalFormatSymbols` (currency symbol, separators, layout). **Patterns do not perform exchange-rate conversion.** If the input is 12.5 USD, switching the locale to Germany does not turn 12.5 USD into EUR.

A payment application should manage the **currency code** and **business precision/rounding** separately, never inferring currency solely from UI language. For displaying money according to default locale conventions, `NumberFormat.getCurrencyInstance(locale)` is typically a good starting point; if customizing `DecimalFormat`, configure currency properly.

### 8.3. Quoting literals

`DecimalFormat` patterns provide single-quote quoting for literal characters in prefixes/suffixes, such as a unit label after a number. Do not assume `DecimalFormat`'s special characters act as plain text when appending units, percentages, or currency symbols.

Likewise, do not conflate `DecimalFormat` quoting syntax with `MessageFormat`: both share the concept of single quotes, but they are **two different parsers and two different pattern contracts**. When embedding `DecimalFormat` inside a message-formatting system, verify each layer independently.

## 9. Using `DecimalFormatSymbols` intentionally

`DecimalFormatSymbols.getInstance(Locale.GERMANY)` is a straightforward way to obtain locale symbols. You can inspect them:

```java
DecimalFormatSymbols german =
        DecimalFormatSymbols.getInstance(Locale.GERMANY);

System.out.println(german.getDecimalSeparator());  // ,
System.out.println(german.getGroupingSeparator()); // .
```

This is a snippet requiring importing the corresponding classes; with standard German data, it prints a comma and a period. `DecimalFormatSymbols` also has setter methods such as `setDecimalSeparator`, `setGroupingSeparator`, `setMinusSign`, `setPercent`, etc.

When **customizing symbols manually**, interpret localized patterns according to **those custom symbols**, not assuming standard German or English defaults. For example, with `de-DE` where the grouping separator was modified, `toLocalizedPattern()` reflects the currently configured symbol.

**Proper sequence if accepting localized patterns from users:**

```text
Identify the user's locale / symbol set
      ↓
Create DecimalFormat + matching DecimalFormatSymbols
      ↓
applyLocalizedPattern(userPattern)
      ↓
Validate pattern and format sample values
      ↓
toPattern() for internal canonical representation
```

If you want the same standard pattern rendered with a different symbol set, **do not** convert it to a localized pattern via `String.replace`. Simply configure the right symbols on the formatter.

## 10. Common mistakes and fixes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Passing German `#.##0,00` to `applyPattern` | Misreads separators or throws `IllegalArgumentException` | Use `applyLocalizedPattern` with German symbols |
| Passing standard `#,##0.00` to German `applyLocalizedPattern` | Separators may be interpreted backwards | Use `applyPattern` for standard patterns |
| Storing `toLocalizedPattern()` as a universal pattern | Fails/misreads on other runtimes/locales | Store standard `toPattern()`, plus locale metadata when needed |
| Using `new DecimalFormat(pattern)` for all users | Depends on environment's default locale | Pick `DecimalFormatSymbols` for the user's locale |
| Manually replacing all `,` with `.` and vice versa | Easily breaks syntax, suffixes, percent, literals | Use the appropriate pattern parser/API |
| Seeing `.` in pattern and assuming output has a decimal dot | Standard pattern and output follow two separate rules | Separate `applyPattern` from symbols used during `format` |
| Multiplying by 100 before using a `%` pattern | Displays percentage 100× too large | Use the raw ratio value and let `DecimalFormat` handle scaling |
| Changing locale assuming it converts currency | Locale does not convert exchange rates | Manage `Currency`, amount, and FX independently |
| Only checking that pattern throws no exception | Can still format unintended output | Test output with 0, negatives, decimals, and large numbers |
| Sharing one mutable `DecimalFormat` across threads | `DecimalFormat` is unsynchronized/unsafe for arbitrary sharing | Create per-task/thread instances or control synchronization |
| Assuming all JDKs share identical locale symbols/defaults | Locale provider/CLDR data can change | Pin/document runtime and test target locales |

## 11. Testing both patterns and results

In an application that configures number patterns, test:

1. **Standard patterns:** load `#,##0.00` via `applyPattern` across at least two locales; assert `toPattern()` preserves intent.
2. **Localized patterns:** load `#.##0,00` with German symbols via `applyLocalizedPattern`; assert formatted output and resulting standard pattern.
3. **Initialization order:** symbols must be set before parsing a localized pattern. If symbols change later, decide whether localized configs must be re-parsed.
4. **Round-trip:** read localized pattern → `toPattern()` → restore another formatter with the same symbols → compare formatted outputs on sample numbers. Do not require the original pattern string to stay character-identical.
5. **Boundary values:** 0, negatives, small numbers, grouped values, large numbers, values needing rounding; when high precision is required, use `BigDecimal` and an explicit `RoundingMode`.
6. **Other locales:** symbols in Germany, the US, and other locales differ. In some numbering systems, localized patterns also use non-ASCII digits and separators.
7. **Parsing user input:** when using `parse`, verify full string consumption; do not treat `NumberFormat` as a strict text validator by default.
8. **Invalid configs:** catch `IllegalArgumentException` from `applyPattern`/`applyLocalizedPattern` and show appropriate guidance rather than guessing/swapping characters with replace.
9. **Environment:** record JDK version, locale-data provider, and custom symbols to avoid false conclusions when outputs shift.

You can write a small Java test verifying the locale contract:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalPatternAssertions {
    private static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected " + expected + ", received " + actual);
        }
    }

    public static void main(String[] args) {
        DecimalFormat de = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));

        check("#,##0.00", de.toPattern());
        check("#.##0,00", de.toLocalizedPattern());
        check("1.234.567,89", de.format(1234567.89));

        DecimalFormat copy = new DecimalFormat();
        copy.setDecimalFormatSymbols(
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        copy.applyLocalizedPattern("#.##0,00");

        check(de.toPattern(), copy.toPattern());
        check(de.format(1234567.89), copy.format(1234567.89));
        System.out.println("5 checks passed");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 DecimalPatternAssertions.java
java -cp . DecimalPatternAssertions
```

Output when rules and symbols match properly:

```text
5 checks passed
```

The program self-checks via `AssertionError`, without needing Java `-ea`. This is intentional pattern/symbol testing; if an application supports multiple locales and custom business formatting rules, expand the test suite accordingly.

## 12. Key takeaways

- **Standard patterns** use `DecimalFormat`'s fixed syntax such as `#,##0.00`, regardless of whether the formatted number uses commas or periods.
- **Localized patterns** use the symbols in `DecimalFormatSymbols`, such as `#.##0,00` for German symbols.
- `applyPattern` is strictly for **standard** patterns; `applyLocalizedPattern` is strictly for **localized** patterns matching the active symbols.
- `toPattern()` returns a standard representation suited for shared configuration; `toLocalizedPattern()` is suited for **displaying** patterns in the user's symbols.
- **Pattern syntax, number formatting, and number parsing are three distinct tasks.** Test with real locales, symbols, and runtimes; never swap separators with arbitrary string manipulation.
