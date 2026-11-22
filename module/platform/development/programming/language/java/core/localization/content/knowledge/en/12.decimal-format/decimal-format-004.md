# DecimalFormat: Percent, Per-Mille, and Multipliers

## 1. Objectives and problem statement

When a Java application displays a ratio, the **underlying data value** and the **user-visible string** often have different scales:

- A raw ratio of `0.256` corresponds to `25.6%` (percent).
- That same raw ratio corresponds to `256‰` (per-mille, *per mille*).
- If the raw data is already `25.6` meaning "25.6 percent" per the API contract, you must not multiply by 100 again when formatting: the output would wrongly become `2560%`.

`java.text.DecimalFormat` lets you format numbers by pattern, handle `Locale`-specific separators, round to the displayed digits, and **scale input data via a formatting multiplier**. When parsing a string with `parse`, the formatter typically **divides back by the multiplier** to return the underlying numeric value.

This lesson distinguishes `%` and `‰`, explains how `DecimalFormat` sets multipliers automatically, how to use `setMultiplier`, effects on `format`/`parse`, precision limits, locales, and common mistakes.

**Key principle:** `DecimalFormat` produces a human-readable representation; it **should not change the unit or business meaning** of variables in your model. Decide up front whether raw data is a **decimal ratio** (e.g., 0.256) or an **already-scaled percentage** (e.g., 25.6).

## 2. From decimal ratios to percent and per-mille

Basic ratio units:

| Raw ratio data | Percent (%) | Per-mille (‰) | Explanation |
| ---: | ---: | ---: | --- |
| `0` | `0%` | `0‰` | None |
| `0.001` | `0.1%` | `1‰` | One part per thousand |
| `0.01` | `1%` | `10‰` | One part per hundred |
| `0.125` | `12.5%` | `125‰` | One eighth |
| `0.256` | `25.6%` | `256‰` | Main illustrative value |
| `1` | `100%` | `1000‰` | Whole |
| `1.5` | `150%` | `1500‰` | Valid when ratio exceeds 100% |

Formulas:

```text
percentage = ratio × 100
perMille   = ratio × 1000

ratio = percentage ÷ 100
ratio = perMille ÷ 1000
```

One percent corresponds to **10 per-mille**: `1% = 10‰`. In statistics, interest rates, or changes over time, **percentage points** represent subtraction between two percentage values, not multiplication/formatting. For instance, moving from `20%` to `25%` is an increase of **5 percentage points**, whereas the relative increase is `(25-20)/20 = 25%`. `DecimalFormat` does not distinguish these two business concepts on its own.

Do not confuse the **per-mille symbol `‰` (U+2030)** with a numeric thousands grouping separator, such as the comma in `1,000` under `Locale.US`.

## 3. Two special symbols in patterns

When `DecimalFormat` parses a **pattern**, `%` and `‰` carry special meaning rather than being decorative characters:

| Pattern | Implicit multiplier | Effect on raw ratio `0.256` |
| --- | ---: | --- |
| `0.0%` | `100` | `25.6%` |
| `0%` | `100` | `26%` after rounding |
| `0.0‰` | `1000` | `256.0‰` |
| `0.0` | `1` | `0.3` after rounding |
| `0.0'%'` | `1` | `0.3%`, `%` sign is literal only |

With an **unquoted** `%` symbol, the pattern makes `DecimalFormat` use a multiplier of `100`; with an unquoted `‰`, the multiplier is `1000`. The printed character comes from the formatter's `DecimalFormatSymbols`. In Java, patterns can include prefixes/suffixes like `0.00 %`; depending on placement and quoting syntax, `%` still carries the 100× effect while the space is a literal part of the pattern.

**Pitfall:** the pattern `0.0'%'` intentionally quotes the percent sign as an ordinary character, so it **does not multiply by 100**. The output `0.3%` from `0.256` is misleading if read as "0.3 percent" in business contexts. Only use quoting when you truly want to print `%` without ratio scaling.

Patterns `0`, `0.0`, and `0.00` control minimum/maximum digits after the decimal point in these examples. `#` is an optional digit, as in `0.##%` (at most two decimal digits). Keep **display precision patterns** distinct from **multipliers**; `0.0%` and `0%` both multiply by 100, yet round differently.

## 4. Standalone Java 17+ example: formatting % and ‰

Create the file `PercentPerMilleDemo.java`:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class PercentPerMilleDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat percent =
                new DecimalFormat("0.0%", symbols);
        DecimalFormat perMille =
                new DecimalFormat("0.0‰", symbols);

        double ratio = 0.256;

        System.out.println("ratio: " + ratio);
        System.out.println("percent: " + percent.format(ratio));
        System.out.println("per mille: " + perMille.format(ratio));
        System.out.println("percent factor: " + percent.getMultiplier());
        System.out.println("per mille factor: " + perMille.getMultiplier());
    }
}
```

Compile and run from the directory containing the file (saved in UTF-8):

```bash
javac -encoding UTF-8 PercentPerMilleDemo.java
java PercentPerMilleDemo
```

Stdout:

```text
ratio: 0.256
percent: 25.6%
per mille: 256.0‰
percent factor: 100
per mille factor: 1000
```

Explanation:

1. `symbols` comes from `Locale.US` so separators and symbols match the illustrative output.
2. `new DecimalFormat("0.0%", symbols)` creates a percentage pattern with an implicit multiplier of `100`.
3. `new DecimalFormat("0.0‰", symbols)` creates a per-mille pattern with an implicit multiplier of `1000`.
4. Both receive **the same raw value 0.256**, yet render in two different units.
5. `getMultiplier()` inspects the multiplier the formatter is currently using; the value lives on the formatter object, **not on the `ratio` variable**.

If the `‰` character causes encoding issues in a compiler or editor, you can use Java Unicode escape `"\u0030\u002e\u0030\u2030"` for the pattern `0.0‰`; however, in modern Java 17+ projects, saving UTF-8 directly is clearer to read.

## 5. `setMultiplier`: scaling by a factor without special symbols

You can set a custom multiplier via `setMultiplier(int)` without using `%` or `‰`. For example, to print **quantity per 1,000 units** without a symbol:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ManualMultiplierDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat formatter =
                new DecimalFormat("0.00", symbols);
        formatter.setMultiplier(1000);

        System.out.println("factor: " + formatter.getMultiplier());
        System.out.println("format: " + formatter.format(0.256));
        System.out.println("parse: " +
                formatter.parse("256.00").doubleValue());
    }
}
```

To compile, the example must handle the checked exception `ParseException` from `parse`. The complete, runnable version is:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class ManualMultiplierDemo {
    public static void main(String[] args) throws ParseException {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormat formatter =
                new DecimalFormat("0.00", symbols);
        formatter.setMultiplier(1000);

        System.out.println("factor: " + formatter.getMultiplier());
        System.out.println("format: " + formatter.format(0.256));
        System.out.println("parse: " +
                formatter.parse("256.00").doubleValue());
    }
}
```

Save **only the second complete version** to `ManualMultiplierDemo.java`, then run:

```bash
javac -encoding UTF-8 ManualMultiplierDemo.java
java ManualMultiplierDemo
```

Stdout:

```text
factor: 1000
format: 256.00
parse: 0.256
```

Difference from `‰`: the formatter here **does not automatically append a per-mille symbol**. `setMultiplier(1000)` alters value scaling, while suffix rendering depends on the pattern. If you want `‰` in the output, use a pattern with `‰` from the start rather than concatenating strings after formatting.

**Avoid:** calling `setMultiplier(1000)` on a formatter using the pattern `0.0%`. The formatter would then print `%` while multiplying by 1000; the result carries a false "percent" meaning. Multiplier and symbol must stay consistent with the data contract.

## 6. Parsing strings with % and ‰: why is the value divided back?

`DecimalFormat` does not only format numbers into strings; it can parse strings back into numbers. With a percentage formatter, the parser reads the numeric part and symbol and computes the **original ratio** by dividing by 100. Similarly, a per-mille parser divides by 1000.

Standalone example:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParseException;
import java.util.Locale;

public class ParseScaleDemo {
    public static void main(String[] args) throws ParseException {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);
        DecimalFormat percent = new DecimalFormat("0.0%", symbols);
        DecimalFormat perMille = new DecimalFormat("0.0‰", symbols);

        Number fromPercent = percent.parse("25.6%");
        Number fromPerMille = perMille.parse("256.0‰");

        System.out.println("from percent: " +
                fromPercent.doubleValue());
        System.out.println("from per mille: " +
                fromPerMille.doubleValue());
    }
}
```

Save `ParseScaleDemo.java` in UTF-8, then run:

```bash
javac -encoding UTF-8 ParseScaleDemo.java
java ParseScaleDemo
```

Stdout:

```text
from percent: 0.256
from per mille: 0.256
```

Comparison table:

| Formatter | String to parse | Returned number |
| --- | --- | ---: |
| `0.0%` | `"25.6%"` | `0.256` |
| `0.0‰` | `"256.0‰"` | `0.256` |
| `0.00` with multiplier `1000` | `"256.00"` | `0.256` |

**Parsing notes:**

- `parse(String)` can throw `ParseException` on failure; code must handle the exception.
- The parser depends on `DecimalFormatSymbols` and pattern structure; strings using decimal or percent symbols from another locale may be misinterpreted or unreadable.
- `DecimalFormat.parse` by default **does not require consuming the entire input**. When validating user data, use the `parse(String, ParsePosition)` overload and check `position.getIndex() == input.length()`, as well as `errorIndex`, before accepting. Avoid treating a parsed prefix as completely valid data.
- `format` can round; hence `parse(format(x))` does not necessarily equal `x`. For instance, with `0%`, ratio `0.256` displays as `26%`; parsing `26%` back yields roughly `0.26`, not `0.256`.
- When working with currency rates, interest rates, or calculations requiring decimal precision, manage data with `BigDecimal` and control rounding. `DecimalFormat` primarily addresses presentation.

## 7. Distinguishing quoted % from scaling %

The patterns `"0.0%"` and `"0.0'%'"` look nearly identical, yet have completely different meanings.

A clear program:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class LiteralPercentDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat scaled =
                new DecimalFormat("0.0%", symbols);
        DecimalFormat literal =
                new DecimalFormat("0.0'%'", symbols);

        System.out.println("scaled: " + scaled.format(0.256));
        System.out.println("scaled factor: " + scaled.getMultiplier());
        System.out.println("literal: " + literal.format(0.256));
        System.out.println("literal factor: " + literal.getMultiplier());
    }
}
```

Save `LiteralPercentDemo.java`, run:

```bash
javac -encoding UTF-8 LiteralPercentDemo.java
java LiteralPercentDemo
```

Stdout:

```text
scaled: 25.6%
scaled factor: 100
literal: 0.3%
literal factor: 1
```

The quoted percent case may fit a few specialized technical labels, but should **not** be used to display percentages from ratio data. The `0.3%` in the output above is really just the rounded number `0.3` with a literal `%` appended; it does not represent \(0.3\%\) of the original data in the usual sense.

Symbols outside single quotes in a pattern carry formatting meaning; inside quotes, they become literals. Single quotes are part of pattern syntax, not printed by Java automatically.

## 8. Patterns, precision, and rounding

The `0` and `#` symbols in a pattern control digit display:

```text
0%       -> rounds to whole percent units
0.0%     -> one digit after the decimal point
0.00%    -> two digits after the decimal point
0.##%    -> at most two digits after the decimal point
0.0‰     -> one digit after the decimal point on the per-mille scale
```

With the same ratio `0.256`:

| Pattern | Result under Locale.US | Multiplier |
| --- | --- | ---: |
| `0%` | `26%` | 100 |
| `0.0%` | `25.6%` | 100 |
| `0.00%` | `25.60%` | 100 |
| `0.##%` | `25.6%` | 100 |
| `0.0‰` | `256.0‰` | 1000 |

`DecimalFormat` typically uses `RoundingMode.HALF_EVEN` by default for this formatting style; however, **do not rely on the default** when rounding results carry business significance. Configure it explicitly:

```java
formatter.setRoundingMode(java.math.RoundingMode.HALF_UP);
```

The statement above is an **illustrative snippet** and requires a `formatter` object of type `DecimalFormat`. Choose `HALF_UP`, `HALF_EVEN`, `DOWN`, or another mode based on product rules, not on "what looks nicer".

**Do not round source data just for UI formatting.** Whenever possible, preserve sufficient precision in the calculation layer and let `DecimalFormat` round only the **display copy**. Saving formatted/parsed values back can discard information.

## 9. Locale controls numeric separators and percent symbols

In `DecimalFormat`, patterns use conventional symbols (`.`, `,`, `%`, `‰`), while output is further governed by the locale's `DecimalFormatSymbols`. Thus, the same ratio and display intent can result in different digit separators, spacing, and symbols across locales.

Common initialization:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
DecimalFormat formatter = new DecimalFormat("0.0%", symbols);
String text = formatter.format(0.256);
```

The snippet above is **illustrative code**, assuming imports of `Locale`, `DecimalFormatSymbols`, and `DecimalFormat`. Exact formatted output may vary with the JDK's locale data/provider. That is why standalone examples in this lesson intentionally use `Locale.US` when explaining exact stdout.

Besides constructing `DecimalFormat` directly, you can use the platform-provided ratio formatter factory:

```java
java.text.NumberFormat percent =
        java.text.NumberFormat.getPercentInstance(Locale.US);
String text = percent.format(0.256);
```

`NumberFormat.getPercentInstance(locale)` selects the appropriate percent format for the locale. Its output can differ from a hand-written `0.0%` pattern in decimal digits, whitespace, and symbol placement. Do not force-cast to `DecimalFormat` if aiming for portable code across providers; `NumberFormat` provides the needed API for `format` and `parse`.

**Scale warning:** if a user enters `25.6%`, parsing with a percent formatter produces roughly `0.256`. Passing `0.256` into a `0.0%` formatter then produces `25.6%`. But if you store `25.6` directly and format it as a ratio, the result becomes `2560.0%`. Data scale must be documented in field/API names; it cannot be inferred from the formatter alone.

## 10. `DecimalFormatSymbols` and custom symbols

`DecimalFormatSymbols` stores symbols used during format/parse, such as decimal separator, grouping separator, percent symbol, and per-mille symbol. You can inspect or customize them:

```java
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(Locale.US);

char percentSymbol = symbols.getPercent();
char perMilleSymbol = symbols.getPerMill();
```

This is an **illustrative snippet** used after importing `java.text.DecimalFormatSymbols` and `java.util.Locale`. `getPerMill()` returns the per-mille symbol, distinct from the thousands grouping separator (`getGroupingSeparator()`).

Useful methods include:

| API | Role |
| --- | --- |
| `getPercent()` / `setPercent(char)` | Formatter's percent symbol |
| `getPerMill()` / `setPerMill(char)` | Per-mille symbol |
| `getDecimalSeparator()` | Decimal separator character |
| `getGroupingSeparator()` | Digit grouping separator character |
| `getInstance(locale)` | Creates symbols for a locale |

**Clear distinction:** changing the symbol via `setPercent(char)` does not change the mathematical multiplier from 100 to another value. Likewise, `setPerMill(char)` only handles the symbol and does not alter business scale usage. If the pattern contains `%`, the formatter still uses multiply-by-100 semantics unless you deliberately change `DecimalFormat`'s own multiplier.

Avoid customizing symbols merely to make output "look as expected"; usually selecting the right `Locale` and formatter type suffices. Symbols can be configured manually when a specific protocol or display style has an explicit specification.

## 11. `setMultiplier`, `applyPattern`, and configuration order

`DecimalFormat` holds state: pattern, symbols, digit counts, rounding mode, and multiplier. Certain configuration calls can affect other properties. Therefore, do not mix steps haphazardly.

Practical order:

1. Select `Locale` and `DecimalFormatSymbols`.
2. Create the formatter with a pattern matching the **display unit**.
3. Call `setMultiplier` only if business logic needs a factor **different** from the pattern's implicit multiplier.
4. Configure digit counts and rounding mode.
5. Write tests for both `format` and `parse` (if the application parses).

`applyPattern` changes the pattern and can reset the multiplier based on `%`/`‰` symbols in the new pattern. If you must use a custom multiplier, define the configuration sequence explicitly and verify with `getMultiplier()`.

In particular, **never** combine the `0.0%` pattern with a multiplier of `1000` when the real intent is per-mille: the displayed symbol and mathematical transform diverge. For per-mille, use a pattern with `‰` and its default multiplier.

## 12. Strict parsing and external data

When users submit ratio strings through input fields, the input may contain whitespace, symbols from another locale, or invalid suffixes. `parse(String)` may consume only part of a string, so manage parse position when full validation is needed.

Standalone example:

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class StrictPercentParseDemo {
    static double parseAll(String input) {
        DecimalFormat fmt = new DecimalFormat(
                "0.0%",
                DecimalFormatSymbols.getInstance(Locale.US));

        ParsePosition pos = new ParsePosition(0);
        Number number = fmt.parse(input, pos);

        if (number == null || pos.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid percent input");
        }
        return number.doubleValue();
    }

    public static void main(String[] args) {
        System.out.println(parseAll("25.6%"));

        try {
            System.out.println(parseAll("25.6%extra"));
        } catch (IllegalArgumentException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

Save `StrictPercentParseDemo.java` with UTF-8 and run:

```bash
javac -encoding UTF-8 StrictPercentParseDemo.java
java StrictPercentParseDemo
```

Stdout:

```text
0.256
Invalid percent input
```

The condition `pos.getIndex() == input.length()` ensures the parser read the entire input; `number == null` catches unparseable strings. Depending on policy, you can also check value bounds (e.g., 0 to 1 for a probability), `NaN`/infinity, mandatory format, or rounding. Those are **business validations**, not implicit duties of `DecimalFormat`.

For financial inputs requiring exact digits, you can enable `fmt.setParseBigDecimal(true)` and use `BigDecimal`, combined with format/scale/rounding checks. Even then, parsing into BigDecimal cannot recover digits that were rounded away in the input string.

## 13. When NOT to use DecimalFormat to transform data?

`DecimalFormat` is a formatter **for locale-aware presentation and re-parsing**. Cases where you should not rely on text formatting:

- **Calculating interest and monetary amounts:** use business formulas and appropriate numeric types (`BigDecimal` when needed), then format for display.
- **Machine-to-machine protocols:** JSON numbers, standard CSVs, API payloads, timestamps, etc. require typed data and serializers per spec, not strings with `%`/`‰` appended unless the contract permits.
- **Comparing data:** do not compare `"9.9%"` with `"10%"` lexicographically; compare the underlying ratio values.
- **Changing storage scale:** do not take a formatted result and strip `%` to store it as a new number. Converting ratios to percentage points requires explicitly named data formulas.
- **Security and validation:** `DecimalFormat` is not a full input validator against business grammar, and does not replace range checks or source validation.

In multi-locale systems, calculation code should be locale-independent. Only select `Locale` and formatting patterns when presenting data to users.

## 14. Common mistakes and fixes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Passing `25.6` to `0.0%` when 25.6 is already percent | Displays `2560.0%` | Normalize ratio data to `0.256` or change display contract |
| Using `%` instead of `‰` | Off by a factor of 10 | Use the right symbol and implicit multiplier |
| Thinking `‰` is a thousands separator | Confuses mathematical meaning | `‰` is ratio per 1000; grouping separator is a different symbol |
| Quoting `'%'` while expecting 100× multiplication | Prints `0.3%` from `0.256` | Use `0.0%` to actually multiply by 100 |
| Calling `setMultiplier(1000)` on a `%` pattern | Wrong multiplication even though label says `%` | Match multiplier with unit/pattern |
| Assuming `parse(format(x)) == x` strictly | Digits lost to rounding | Retain source value and check desired scale |
| Picking `Locale.getDefault()` based on server | Strings vary across environments | Pass the user's intended locale |
| Ignoring `ParseException` / partial input parsing | Invalid strings accepted | Handle exceptions and check `ParsePosition` |
| Using `double` for all financial math | Floating-point errors | Use `BigDecimal` with clear rounding rules |
| Sharing a mutable `DecimalFormat` across threads | State can be mutated concurrently | Create per request/call or use a safe synchronization strategy |
| Using formatted text as API data | Dependent on locale and symbols | Keep standard numeric types/serializers |

**Thread safety:** `DecimalFormat` is a mutable formatter and should not be freely shared across threads when concurrent updates are possible. If caching is needed, consider cloning or appropriate thread/concurrency management.

## 15. Testing checklist and exercises

A basic test suite should cover at least:

1. **Units:** `0.256` -> `25.6%`, `256.0‰`; `getMultiplier()` equals `100` and `1000`.
2. **Boundaries:** `0`, `0.01`, `1`, `1.5`, and negative numbers if business rules permit.
3. **Precision:** `0%`, `0.0%`, `0.00%` on the same data to observe different rounding.
4. **Quoted symbols:** `0.0'%'` must have multiplier `1`, not `100`.
5. **Custom multiplier:** `setMultiplier(1000)` with `0.00` formats/parses consistently and does not add `‰` automatically.
6. **Conditional round-trip:** only expect parsed output to match up to display precision; do not lose source data.
7. **Locale:** verify formatting and parsing across all locales the app actually supports; do not hardcode decimal points from `Locale.US` in multilingual code.
8. **Invalid input:** missing/wrong symbol, trailing characters, invalid characters, out-of-range business values.
9. **Concurrency:** avoid sharing a mutable formatter whose pattern is changed across requests.

Practice exercises:

- Write a `"0.00%"` formatter for `ratio = 0.0425`. Predict how it rounds and verify in Java.
- Change `"0.0‰"` to `"0‰"` for `0.2568`; explain the displayed value and the information discarded.
- Create `DecimalFormat("0.00", symbols)`, call `setMultiplier(100)`, and verify why the output lacks `%` when the pattern omits the symbol.
- Parse `"12.5%"` with a ratio formatter, then multiply by 100 once to present "percentage points". Explain why you should **not** multiply again inside another ratio formatter.
- Create an input `"25.6%unexpected"`; test `parse(String)` and `parse(String, ParsePosition)` to understand partial parsing.

## 16. Conclusion

In `DecimalFormat`, **unquoted** `%` and `‰` symbols in a pattern set multipliers of `100` and `1000`, respectively. `setMultiplier` allows a different factor without implicitly adding a symbol. When formatting, data is multiplied and then rendered per pattern; when parsing, the value is scaled back to the original unit by the multiplier. Locale, symbols, digit counts, and rounding also affect the result.

To avoid precision errors and unit bugs, **define the data's scale first**, pick an appropriate pattern for display, parse with validation when accepting external input, and never use formatted strings as the source for calculations.

## References

- [Oracle Java 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html)
- [Oracle Java 21 — DecimalFormatSymbols](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormatSymbols.html)
- [Oracle Java 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html)
- [Oracle Java 21 — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
