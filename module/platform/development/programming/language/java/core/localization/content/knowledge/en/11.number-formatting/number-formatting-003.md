# CompactNumberFormat with Short or Long Styles in Java

## 1. When Is Compact Number Formatting Needed?

In space-constrained UI components such as stat cards, dashboards, charts, mobile apps, or view count lists, displaying large numbers in full can reduce readability. Instead of showing `1,000` or `1,000,000`, US English users easily recognize forms like `1K` or `1M`. In prose where more space is available, fuller forms such as `1 thousand` or `1 million` can read more naturally.

Java provides **compact number formatting** through `java.text.CompactNumberFormat`, a concrete subclass of `NumberFormat` introduced in **Java 12** and available in **Java 17+**.

Unlike manually writing `if (value >= 1000) value / 1000 + "K"`, a compact formatter uses **locale-specific patterns**. For the same magnitude, different languages and regions can have different words, unit abbreviations, thresholds, and pluralization rules.

This lesson focuses on:

- Distinguishing `NumberFormat.Style.SHORT` and `NumberFormat.Style.LONG`.
- Creating a formatter properly via `NumberFormat.getCompactNumberInstance(locale, style)`.
- Understanding compaction thresholds, fractional digits, rounding, signs, and locale dependence.
- Distinguishing the **presentation string** from the **raw numeric value**; caveats when parsing compact text.
- Choosing appropriate usage in the UI, identifying common mistakes, and writing tests.

## 2. How Do SHORT and LONG Differ?

Java supports two styles in `NumberFormat.Style`:

| Style | Goal | Example with `Locale.US` | Best suited for |
| --- | --- | --- | --- |
| `SHORT` | Short symbol, minimal space | `10000 → 10K` | KPIs, chart labels, badges, cards |
| `LONG` | Concise phrase in words | `10000 → 10 thousand` | Stat summaries, reports, prose |
| `NumberFormat.getNumberInstance(locale)` | Not compact: standard number | `10000 → 10,000` with `Locale.US` | Detailed data tables, data needing full display precision |

The long form (`LONG`) does **not** mean printing digits individually or spelling out the entire number in words ("ten thousand"); it is a *compact long form* defined by the locale's patterns. In the US, `10 thousand` still keeps the numeric part `10`, with only the unit written out longer than `10K`.

Likewise, the short form (`SHORT`) does **not necessarily** use only K/M/B characters; each locale has its own symbols and phrasing. Suffixes, prefixes, spacing, scripts, and plural forms are determined by localization data. `1K` is a US English example, not a mandatory rule for Vietnamese, Hindi, or every other language.

### Two Things to Distinguish

1. **Style**: does the user want the short-symbol compact form or the long-phrase form?
2. **Locale**: which language/region governs the symbol style and unit structure?

These two parameters are independent. To display for a `vi-VN` user, pass `Locale.forLanguageTag("vi-VN")` rather than manually appending `K` or `M` to the number. When formatting for `en-US`, use `Locale.US`.

## 3. Basic Java 17 API

Standard factory methods:

```java
NumberFormat shortFormat = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);

NumberFormat longFormat = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.LONG);
```

Both variables have type `NumberFormat` (the return type declared by the factory API). In standard implementations, the compact formatter is an instance of `CompactNumberFormat`, but code that only uses `format` and basic options can keep the `NumberFormat` type to minimize implementation coupling.

There is also a no-argument overload:

```java
NumberFormat defaultShort = NumberFormat.getCompactNumberInstance();
```

The parameterless overload uses the **default locale for the `Locale.Category.FORMAT` category** and the `SHORT` style. In multi-user server applications, you should generally use the overload **with explicit locale and style**; otherwise, results can depend on the deployment machine's JVM configuration.

`Locale` does not automatically choose a time zone, currency, or unit of measure; `CompactNumberFormat` only formats a numeric value. If the input is 1,000,000 views, the symbol `M` means **one million according to the pattern**; it is not a currency, length, or exchange-rate converter.

### Standalone Example 1 — Same Number, Two Styles

Save to `CompactStylesDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CompactStylesDemo {
    public static void main(String[] args) {
        long count = 10_000L;

        NumberFormat shortFormat = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);

        NumberFormat longFormat = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.LONG);

        System.out.println("original=" + count);
        System.out.println("short=" + shortFormat.format(count));
        System.out.println("long=" + longFormat.format(count));
    }
}
```

With JDK 17 or later, save as UTF-8 and run:

```bash
javac -encoding UTF-8 CompactStylesDemo.java
java CompactStylesDemo
```

With standard compact data for `Locale.US`, stdout:

```text
original=10000
short=10K
long=10 thousand
```

Key observation: the variable `count` remains 10,000. Both `10K` and `10 thousand` are merely **two presentation strings** produced by the formatter, not two different business values. The examples `10K` and `10 thousand` are specific examples from the Java 17 `CompactNumberFormat` documentation; when testing across other locales/providers, do not assume every compact string resembles `Locale.US`.

## 4. Compaction Thresholds Come from Compact Number Patterns

`CompactNumberFormat` uses an array of **compact number patterns** from locale data, based on the Unicode LDML (Locale Data Markup Language) standard.

For `Locale.US` and style `SHORT`, example patterns may include:

```text
0       → regular number format when no compact pattern applies
0K      → 1K (e.g., 1000)
00K     → 10K (e.g., 10000)
000K    → 100K (e.g., 100000)
0M      → 1M (e.g., 1000000)
...
```

The `0` digits in the pattern represent the minimum number of digits for the numeric portion at that magnitude. Here `K` and `M` are **pattern suffixes**, not characters glued on by ad-hoc string concatenation.

Important points:

- Each locale can have a **different threshold/unit system**. Do not write your own algorithm dividing by 1,000 for all locales.
- Not every value gets compacted. Many locales use standard number patterns for magnitudes below a certain threshold; for example, `42` still displays as `42`.
- If a magnitude has no compact pattern, the formatter can fall back to the localized **standard number format**, rather than picking a suffix from another language.
- Negative numbers use a negative pattern if provided by the locale, or apply default negative-sign rules. Do not manually prepend `-` when the UI already uses the formatter.
- The long form may incorporate **plural rules**: the same unit can have different singular/plural forms depending on quantity and language.

Therefore, you cannot reduce all locales to a global lookup table like "from 1,000 is K; from 1,000,000 is M." The output string depends on locale data provided by the runtime/`NumberFormatProvider`.

### What Happens Near a Threshold?

For example, a number close to one million may be rounded when displaying 0 fractional digits. The formatter must coordinate **pattern selection** and **rounding**; the output can switch compact symbols when a value sits right next to the next tier. Do not try to guess the output by checking `number >= 1_000_000` and appending `M`, especially when precision is non-zero.

When a product requires an exact compaction threshold policy fixed across platforms, define and test a dedicated display contract. Locale-based compact number formatting is a **display mechanism**, not a calculation or business classification rule.

## 5. Displaying Fractional Digits and Rounding

By default, `CompactNumberFormat` typically **does not display fractional digits**. For example, `1000` in `Locale.US` with style `SHORT` displays `1K`, not `1.00K`.

A value like 1,200 may only display as `1K` by default; that is a compacted and rounded representation. If users need to distinguish 1,200 from 1,000, you can increase the fractional digits:

```java
NumberFormat shortFormat = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);

shortFormat.setMinimumFractionDigits(1);
shortFormat.setMaximumFractionDigits(1);
```

With the configuration above, a typical result is `1200 → 1.2K`. Available options:

| API | Purpose |
| --- | --- |
| `setMinimumFractionDigits(n)` | Minimum fractional digits displayed |
| `setMaximumFractionDigits(n)` | Maximum fractional digits; may round |
| `setRoundingMode(RoundingMode)` | Rounding policy |
| `setGroupingUsed(boolean)` | Enable or disable grouping separators in the representation |
| `setMinimumIntegerDigits(n)` / `setMaximumIntegerDigits(n)` | Adjust integer digits per formatter capabilities |

When setting `minimumFractionDigits` higher than the current `maximumFractionDigits` (or vice versa), `NumberFormat` adjusts the related value to maintain `minimum <= maximum`. To avoid surprises, you can inspect `getMinimumFractionDigits()` and `getMaximumFractionDigits()` after configuring.

### Standalone Example 2 — Changing Display Precision

File `CompactPrecisionDemo.java`:

```java
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.util.Locale;

public class CompactPrecisionDemo {
    public static void main(String[] args) {
        NumberFormat compact = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);

        long value = 1_200L;
        System.out.println("original=" + value);
        System.out.println("default=" + compact.format(value));

        compact.setMinimumFractionDigits(1);
        compact.setMaximumFractionDigits(1);
        compact.setRoundingMode(RoundingMode.HALF_UP);

        System.out.println("one-decimal=" + compact.format(value));
        System.out.println("still-original=" + value);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 CompactPrecisionDemo.java
java CompactPrecisionDemo
```

With standard `Locale.US` patterns, stdout:

```text
original=1200
default=1K
one-decimal=1.2K
still-original=1200
```

`setMinimumFractionDigits(1)` requires at least one fractional digit in the output; `setMaximumFractionDigits(1)` caps it at one digit. `RoundingMode.HALF_UP` only changes **how rounding is performed for display**; it does not alter the raw value in `value`.

**Default RoundingMode:** According to the Java 17 documentation, the compact formatter uses `RoundingMode.HALF_EVEN` by default for formatting. You can switch to `HALF_UP`, `DOWN`, or another mode appropriate for the UI. Do not use a mode chosen for UI display as a substitute for business-layer rounding policy.

### Information Loss After Compaction

`1.2K` conveys approximately 1,200 to the reader; with limited fractional digits, many distinct raw values produce the **exact same output**. Therefore, never use compact strings as the source for calculations, limit checks, or persisting original values.

Especially in financial products, exact quantities should be displayed using appropriate currency/number formats when making decisions; compact formatting is only suitable for **summary statistics**, and labels/tooltips showing the exact value should be considered.

## 6. Same Number Across Multiple Locales

For example, users want to view counts in `en-US`, `vi-VN`, and `fr-FR`. You can create corresponding formatters:

```java
Locale en = Locale.forLanguageTag("en-US");
Locale vi = Locale.forLanguageTag("vi-VN");
Locale fr = Locale.forLanguageTag("fr-FR");

NumberFormat shortEn = NumberFormat.getCompactNumberInstance(
        en, NumberFormat.Style.SHORT);
NumberFormat shortVi = NumberFormat.getCompactNumberInstance(
        vi, NumberFormat.Style.SHORT);
NumberFormat longFr = NumberFormat.getCompactNumberInstance(
        fr, NumberFormat.Style.LONG);
```

This is an **illustrative snippet inside a method** with imports of `java.text.NumberFormat` and `java.util.Locale`. It is not a standalone Java program.

**Why not list absolute stdout for all locales?** Linguistic data (CLDR) and locale providers can change across JDK versions, `java.locale.providers` settings, environments, and installed providers. Vietnamese forms may use words/short phrases different from English; French may use non-breaking spaces (NBSP or narrow NBSP). Comparing verbatim strings across runtimes without controlling the environment easily causes false test failures.

A runnable program to observe the output:

File `CompactLocalesDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class CompactLocalesDemo {
    public static void main(String[] args) {
        long count = 1_500_000L;

        for (String tag : new String[]{"en-US", "vi-VN", "fr-FR"}) {
            Locale locale = Locale.forLanguageTag(tag);

            NumberFormat shortFormat =
                    NumberFormat.getCompactNumberInstance(
                            locale, NumberFormat.Style.SHORT);

            NumberFormat longFormat =
                    NumberFormat.getCompactNumberInstance(
                            locale, NumberFormat.Style.LONG);

            System.out.println(tag
                    + " | SHORT=" + shortFormat.format(count)
                    + " | LONG=" + longFormat.format(count));
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 CompactLocalesDemo.java
java CompactLocalesDemo
```

The program prints **three lines**, in order `en-US`, `vi-VN`, `fr-FR`, each showing both styles for the same `count=1500000`. The exact suffix text and spacing depend on the JDK's locale data, so observe them on your runtime environment rather than assuming a single universal string across all machines.

Things worth verifying:

- `format(1_500_000L)` for `SHORT` and `LONG` may differ in length and phrasing, yet both describe the same count of 1,500,000.
- Decimal separators and magnitude words change by locale.
- The value `count` does not mutate, and the application does not change the system locale to format per user.

**Good habit:** pass `Locale` from the user context; do not call `Locale.setDefault(...)` to control individual requests because the default is JVM-wide state.

## 7. Choosing Between Compact and Regular Number Formatting

Different display goals:

| Context | Recommendation | Reason |
| --- | --- | --- |
| Small "view count" card | `SHORT` | Fewer characters, easy to scan |
| Report summary sentence | `LONG` | Expresses scale unit in words |
| Accounting/billing table | `getNumberInstance` or controlled currency formatter | Full numbers must be visible |
| JSON API sent to frontend | Send canonical numeric value + metadata | Frontend formats per locale without relying on pre-compacted strings |
| Chart tooltip | Can show both compact and full number | Reduces reader confusion over rounded figures |
| Small quantities | Formatter may keep normal form | Do not force out-of-context suffixes |

For example, a view count of `1_234_567` can be shown in compact form on a card, while clicking into details provides `1,234,567` under `Locale.US` or the corresponding locale's grouping rules.

**Common misconception:** `CompactNumberFormat` formats **numeric scale**, not "short currency." Do not call `getCompactNumberInstance` and infer a currency from the locale. If you want to produce a string like "$1.2M", you must account for currency, symbol, precision, and dedicated business policy; manually concatenating a currency symbol can break placement/spacing in many locales. Compaction of `1_200_000` neither changes currency units nor converts exchange rates.

## 8. Parsing Compact Strings Back to Numbers: Possible, with Caution

`CompactNumberFormat` supports `parse(...)`, not just `format(...)`. With `Locale.US`, for example, `"1K"` can parse to 1000, and `"12K"` to 12000. During parsing, the formatter recognizes the compact suffix and multiplies the numeric part by the suffix's factor from the locale pattern.

However, **formatting then parsing does not guarantee recovering the original value**:

- `format(1234)` with 0 fractional digits may become `1K`, which parses back to 1000—losing 234.
- Text like `1M` carries meaning dependent on the locale's pattern; parsing with the wrong locale may fail to recognize it properly.
- The parser can **partially consume** a string and stop; it does not implicitly validate the entire input.
- By default, `parse` may return `Long` or `Double`; the result and type also depend on the value and configuration. `CompactNumberFormat` provides `setParseBigDecimal(true)` to prefer `BigDecimal`, except for special values like NaN/Infinity.
- `isParseIntegerOnly` and `setGroupingUsed` affect parsing; do not assume the parser always accepts grouping separators. According to the `CompactNumberFormat` documentation, parsing by default **disallows grouping separators** unless grouping is enabled via `setGroupingUsed(true)`.

### Standalone Example 3 — Parsing and Checking the Entire Input

File `CompactParseDemo.java`:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class CompactParseDemo {
    public static void main(String[] args) {
        NumberFormat format = NumberFormat.getCompactNumberInstance(
                Locale.US, NumberFormat.Style.SHORT);

        String input = "12K";
        ParsePosition position = new ParsePosition(0);
        Number parsed = format.parse(input, position);

        if (parsed == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid compact input");
        }

        System.out.println("input=" + input);
        System.out.println("value=" + parsed.longValue());
        System.out.println("consumed=" + position.getIndex());
    }
}
```

Run with Java 17+:

```bash
javac -encoding UTF-8 CompactParseDemo.java
java CompactParseDemo
```

With `Locale.US`, stdout:

```text
input=12K
value=12000
consumed=3
```

`ParsePosition` reports how many characters the parser consumed; checking `position.getIndex() == input.length()` catches trailing leftover text. **That alone is not complete strict validation**: beyond full consumption, you must define allowed locales, allowed data types, magnitude limits, fractional parts, expected input format, and business constraints.

In systems requiring exact numeric input (such as money, orders, inventory quantities), forms/APIs should generally accept **uncompacted numbers** with a clear contract, reserving compact text for **UI output**. Accept compact numbers as primary input only when the product explicitly supports that input style and has locale-specific parser tests.

### ParseBigDecimal: When Is It Needed?

`NumberFormat.getCompactNumberInstance(...)` returns `NumberFormat`, though the standard implementation is typically `CompactNumberFormat`. When you need a subclass-specific method, check the type before casting:

```java
NumberFormat formatter = NumberFormat.getCompactNumberInstance(
        Locale.US, NumberFormat.Style.SHORT);

if (formatter instanceof java.text.CompactNumberFormat compact) {
    compact.setParseBigDecimal(true);
}
```

This is an illustrative snippet **inside a method** on Java 17. Pattern matching for `instanceof` has been a standard language feature since Java 16. When decimal precision is required, after parsing you must still check the actual runtime type, contract, and bounds; do not blindly force every `Number` into `longValue()` because that can drop fractions or overflow.

## 9. Rounding Behavior, Negatives, Large Numbers, and Special Values

### 9.1. Negatives and Signs

For example, `-1200` in compact form can receive a negative sign alongside the magnitude suffix. Sign placement (prefix/suffix, symbol) is governed by locale patterns. Do not strip the negative sign manually, divide the number, and concatenate a suffix, as doing so easily produces ungrammatical strings or misplaced signs.

### 9.2. Very Large Numbers

Compact patterns are declared across magnitude tiers. For magnitudes beyond the range of patterns supported by the provider, do not assume new suffixes like "P" or "E" always exist under the same rules. Choose standard formatting or scientific notation when required by the domain, and test output against realistic extreme values.

### 9.3. NaN and Infinity

When the input is `Double.NaN` or `Double.POSITIVE_INFINITY`, the representation may use localized symbols instead of compact suffixes like ordinary numbers. If the product only accepts finite numbers, **validate before formatting**. Never display NaN or Infinity as a valid quantity.

### 9.4. Decimals and BigDecimal

`NumberFormat` has `format(long)`, `format(double)`, and `format(Object)` overloads. `BigDecimal` can be passed to the object-based `format` API. However, display precision is bounded by the configured digit counts. For monetary calculations, use `BigDecimal` with independent business rounding policies—never parse compact strings back to obtain values.

### 9.5. Using Formatted Output in Comparison Logic

Do not write:

```java
if (compact.format(a).equals(compact.format(b))) {
    // Do NOT conclude that a and b are equal.
}
```

This is an **illustrative snippet**, not a standalone runnable example. Because output may have been rounded, two distinct values can produce identical strings. Compare `a` and `b` directly in their appropriate business type.

## 10. Locale-Dependent Formatting and Changes Across JDKs

Compact data comes from locale data and providers configured in the environment. Factors that can affect results include:

- The JDK version and its bundled CLDR data version.
- The requested `Locale`, especially language/region/script.
- `NumberFormat.Style.SHORT` vs. `LONG`.
- `minimumFractionDigits`, `maximumFractionDigits`, `RoundingMode`, and other formatter settings.
- Installed `NumberFormatProvider` implementations and `java.locale.providers` configuration (if applicable).
- Whether the locale's pattern set has plural rules or different thresholds.

Therefore, locale-based UI tests must **choose the right level of assertion**:

1. Logic tests always pass an explicit locale, explicit style, and verify the original value is not mutated.
2. With a pinned JDK/CLDR environment, you can snapshot exact strings for supported locales.
3. If running across different vendors/JDKs, tests should verify validity and semantics, or allow acceptable variations.
4. Specifically check Unicode spaces, separators, negative values, and numbers near thresholds.
5. For screen readers/accessibility, verify announcements are understandable; ultra-short symbols may need full descriptive `aria-label` text.

**Do not cast to `CompactNumberFormat` without checking** if alternative providers may be used; the factory declares `NumberFormat` as its return type, and service providers can affect the concrete implementation.

## 11. Thread Safety and Server-Side Usage

`NumberFormat` and `CompactNumberFormat` are **mutable** formatters. Calling `setMaximumFractionDigits`, `setRoundingMode`, or other setters changes the object's state. The `NumberFormat` API is not safe when multiple threads format/parse with the same instance without synchronization.

A simple server-side usage pattern:

```java
import java.text.NumberFormat;
import java.util.Locale;

public final class ViewCountFormatter {
    private ViewCountFormatter() {}

    public static String compactViewCount(long count, Locale locale) {
        NumberFormat fmt = NumberFormat.getCompactNumberInstance(
                locale, NumberFormat.Style.SHORT);
        fmt.setMaximumFractionDigits(1);
        return fmt.format(count);
    }
}
```

This is a **compilable utility class** without `main`, meant to be called by other application code. Each call creates its own formatter so mutable instances are never shared across requests; if you later optimize with caching, you must design safe synchronization, cloning, or scoping and verify with benchmarks.

Do not call `Locale.setDefault(locale)` per user because that is JVM-wide state. Pass `Locale` from the request/context into the formatter, as shown above.

## 12. Testing and Exercises

### 12.1. Valuable Test Cases

| Scenario | Expected result / criteria |
| --- | --- |
| `10000` in `Locale.US` | `SHORT = 10K` and `LONG = 10 thousand` under standard data |
| `1200` default vs. 1 fractional digit | Compact string changes granularity; `1200` value stays unchanged |
| Numbers `99`, `999`, and `1000` | Verify exact compaction threshold for the locale |
| `999_500` and `1_000_000` | Verify effect of rounding and tier transition |
| Negative numbers | Sign and suffix appropriate for the locale |
| `en-US`, `vi-VN`, `fr-FR` | Each locale uses its proper pattern and does not rely on JVM default |
| `12K` parsed in `Locale.US` | Value 12000; parser consumes entire input |
| `12Kxyz` | Detects trailing characters when strict input is required |
| Two different numbers with identical compact strings | Comparisons still rely on the raw numbers |
| Concurrent access from multiple requests | Mutable formatters are never shared improperly |

### 12.2. Self-Check Questions

**Question 1.** Do `NumberFormat.Style.SHORT` and `LONG` necessarily differ as "abbreviated" vs. "entire number written in words"?

**Answer:** No. `LONG` is a long compact form, such as `10 thousand` in `Locale.US`; the `10` portion remains digits.

**Question 2.** Why should `1.2K` not be stored in a database instead of `1200`?

**Answer:** It is a locale-specific presentation string; it can lose precision, may not parse under another locale, and is not an exact numeric contract.

**Question 3.** If more precision than the default is needed, what can be configured?

**Answer:** `setMinimumFractionDigits`, `setMaximumFractionDigits`, and `setRoundingMode`. However, this is a **display precision** policy and does not change the raw number.

**Question 4.** Why shouldn't you write `value / 1000 + "K"` for all users?

**Answer:** Each locale's patterns can differ in prefixes/suffixes, tiers, separators, phrasing, and pluralization. Manual concatenation imposes English rules and can be wrong in other languages.

**Question 5.** A parser receives `"12K more"` and returns 12000. Can the entire input be considered valid?

**Answer:** No. The parser may have only read the `12K` prefix. You must check `ParsePosition.getIndex()` against the input length and apply additional validation per contract.

**Question 6.** In a multi-user application, should you create a single static `CompactNumberFormat` and change its locale per request?

**Answer:** No. Locale is passed when creating the formatter, and a mutable formatter is not safe for concurrent use/mutation without synchronization. Create a formatter per request or manage caching/cloning carefully.

### 12.3. Hands-On Practice

1. Run `CompactStylesDemo` with `10000`. Then test `1000`, `1000000`, and `1000000000`; record `SHORT`/`LONG` for `Locale.US`.
2. Change `Locale.US` to `Locale.forLanguageTag("vi-VN")` and try both styles. Observe separators, units, and expression length; do not assume K/M suffixes like English.
3. Run `CompactPrecisionDemo` with `1200`, then `1490` and `1500`. Observe the impact of maximum fraction digits and rounding mode on nearby values.
4. Run `CompactParseDemo` with `"12K"` and `"12Kxyz"`. Add an input length check and define clear error reporting.
5. Design a KPI card showing a compact value whose tooltip formats the raw number via `NumberFormat.getNumberInstance(locale)`; ensure no calculations rely on the compact text.

## 13. Key Takeaways

- **`CompactNumberFormat` shortens number representations by locale**, supported since Java 12 and running on Java 17+.
- **`SHORT`** favors short symbols like `10K`; **`LONG`** can use phrases like `10 thousand`.
- Use `NumberFormat.getCompactNumberInstance(locale, style)` and **pass locale/style explicitly**.
- Patterns, thresholds, signs, plurals, and phrasing depend on locale data. Never manually append K/M for all languages.
- By default there are no fractional digits; configure min/max fraction digits and rounding when finer detail is needed.
- Compact formatting is a **display layer that may round**, not exact data for persistence, calculations, currency conversion, or comparisons.
- Parsing compact text requires the right locale and checking full string consumption; do not rely on a format–parse round trip to recover the original number.
- Never share a mutable `NumberFormat` instance across threads without synchronization.

**Official Java 17 Documentation:**

- [`CompactNumberFormat` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CompactNumberFormat.html)
- [`NumberFormat` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html)