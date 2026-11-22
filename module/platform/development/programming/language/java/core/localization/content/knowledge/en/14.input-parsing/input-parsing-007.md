# Limitations of Formatting Then Parsing to Recover Original Data

## 1. The Core Question: Does `parse(format(x))` Equal `x`?

In Java Core Localization, **formatting** turns a structured value into a human-readable string for a locale, while **parsing** attempts to interpret a string back into a structured value. The two operations are related, but they are **not automatically exact inverses**.

```text
Original value x
      |
      | format(x, locale, pattern, precision...)
      v
  Display string s
      |
      | parse(s, locale, pattern, parser options...)
      v
  Recovered value x'
```

There are two very different criteria:

- **By value:** does `x'` have the same mathematical value or instant in time as `x`?
- **By original data:** does `x'` retain the **exact type, scale, precision, time zone, offset, characters, and context** of `x`?

Even when numerically equal, objects may not be equal: `BigDecimal("1.20")` and `BigDecimal("1.2")` have the same numeric value, yet `equals` returns `false` due to differing scale. A `ZonedDateTime` in `Asia/Ho_Chi_Minh` can be reduced to an `OffsetDateTime` carrying only `+07:00`, preserving the instant while losing the region zone identity.

This lesson explains the **limitations of formatting then parsing to recover original data** in the *Input Parsing* module: root causes, Java 17+ demonstrations, common mistakes, and how to design safe data storage and interchange.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `parse(format(x))` from `format(parse(s))` and understand why neither guarantees an absolute round-trip.
2. Recognize **precision loss**, **scale loss**, **data type loss**, **time zone loss**, and **loss of original text formatting**.
3. Use `DecimalFormat`, `ParsePosition`, and `DateTimeFormatter` for their intended purpose rather than as serializers.
4. Design input pipelines with **explicit locales**, **whole-string checks**, and domain validation.
5. Choose canonical storage representations using appropriate numeric types, `BigDecimal`, and ISO 8601 forms.

## 2. Why Is Formatting Usually Not Reversible?

To parse back every piece of `x` accurately, formatting would have to lose zero required information. However, human-facing formatters are built to **omit details** or **alter representation**:

- **Rounding:** `1234.567` displays as `1,234.57` when only two fractional digits are shown.
- **Dropping trailing zeros:** `BigDecimal("1.20")` displays as `1.2` under a pattern allowing up to two optional fractional digits.
- **Date-only output:** time-of-day `08:45:37.123456789` is absent from `28/10/2026`.
- **Offset-only output:** `+07:00` does not contain the original zone name `Asia/Ho_Chi_Minh`.
- **Locale differences:** `,` can be a grouping separator in `en-US` but a decimal separator in `de-DE`.
- **Equivalent representations:** `"1,234.50"` and `"1234.50"` can parse to the same value; the parser cannot tell which form the original input used.
- **Digit, sign, or space transformations:** output may use Arabic-Indic digits, U+202F, or currency prefixes/symbols; parsing back does not always recover the original characters.

Mathematically, if two distinct values `x1` and `x2` produce **the exact same string** from a formatter, no parser inspecting only that string can faithfully recover **both**. This is the **non-injective** nature of formatting.

Example:

```text
format(1.20, pattern "#,##0.##") = "1.2"
format(1.2,  pattern "#,##0.##") = "1.2"
```

Both inputs yield `"1.2"`, so after parsing you cannot deduce whether the original dataset had scale 2 or scale 1.

**Conclusion:** a display string should never be treated as a lossless backup of original data.

## 3. Three Round-Trip Levels to Distinguish

| Goal | Example Check | What Can Still Be Lost? |
| --- | --- | --- |
| **Same numeric value** | `a.compareTo(b) == 0` for `BigDecimal` | Scale, written shape, trailing zeros |
| **Same data/object** | `a.equals(b)` for semantically rich types | Precision, scale, zone ID, nanoseconds, runtime type |
| **Exact original character/byte sequence** | `originalText.equals(formattedAgain)` | Grouping separators, Unicode whitespace, digit script, notation style, `+` sign, leading zeros |

For instance, a parser can read:

```text
"1234.50"
"1,234.50"
"001234.50"
```

into the exact same `BigDecimal("1234.50")` under certain `en-US` configurations. Yet when formatted back with `#,##0.00`, all three become `"1,234.50"`. If your goal is to recover the input string **character-for-character**, you must store the raw input string or additional presentation metadata.

Also distinguish these two expressions:

- `parse(format(x))`: value → text → value. Can lose precision or structure.
- `format(parse(s))`: text → value → text. Often **canonicalizes spelling**, so it need not equal `s` even when the value is valid.

## 4. Precision Loss from Rounding and Fractional Digit Limits

`DecimalFormat` may display only a bounded number of fractional digits:

```java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
```

The pattern `#,##0.00` requires two fractional digits. The value `1234.567` displays as `1,234.57` under the active rounding mode; when parsed back, there is no way to recover the original trailing digit `7`.

Example:

```text
BigDecimal value:  1234.567
Display string:    1,234.57
Re-parsed value:   1234.57
Difference:        0.003
```

`setMaximumFractionDigits(2)` and `setRoundingMode(...)` control **display output**; they do not make formatting lossless. Enabling `setParseBigDecimal(true)` on the parser cannot bring back digits already discarded by the formatter.

**Using `BigDecimal` to avoid binary floating-point error** is different from **preventing digit loss from formatter rounding**. A `BigDecimal` accurate to hundreds of digits can still be formatted into a string with only two fractional digits.

## 5. Losing `scale` Even When Values Remain Equal

`BigDecimal` has two notable facets: **numeric value** and **scale**.

```text
new BigDecimal("1.20") : scale 2
new BigDecimal("1.2")  : scale 1
```

The pattern `#,##0.##` allows up to two optional fractional digits, so both format as `1.2`. After parsing back:

- `compareTo(...) == 0`: still numerically equal.
- `equals(...)`: can be `false` because the original object had a different scale.

Scale can matter in monetary amounts, invoice formatting standards, measurement resolution, or audit requirements. If business logic requires preserving input scale, do not rely on a formatter that strips trailing zeros; store the value along with its scale or use a canonical decimal representation with an explicit scale policy.

Conversely, if scale is **not** a business attribute, do not require `BigDecimal.equals` after every round-trip: use `compareTo` to compare numeric values. Comparison semantics must follow data meaning rather than an arbitrary equality method.

## 6. Java 17+ Example: Same Value Context, Incomplete Recovery

Create the file `NumberRoundTripDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberRoundTripDemo {
    public static void main(String[] args) throws Exception {
        DecimalFormat rounded = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        rounded.setParseBigDecimal(true);

        BigDecimal original = new BigDecimal("1234.567");
        String shown = rounded.format(original);
        BigDecimal parsed = (BigDecimal) rounded.parse(shown);

        System.out.println("original: " + original);
        System.out.println("shown: " + shown);
        System.out.println("parsed: " + parsed);
        System.out.println("same numeric value: "
                + (original.compareTo(parsed) == 0));

        DecimalFormat optional = new DecimalFormat(
                "#,##0.##",
                DecimalFormatSymbols.getInstance(Locale.US));
        optional.setParseBigDecimal(true);

        BigDecimal scaled = new BigDecimal("1.20");
        BigDecimal scaledBack =
                (BigDecimal) optional.parse(optional.format(scaled));

        System.out.println("scaled display: " + optional.format(scaled));
        System.out.println("scaled original: " + scaled);
        System.out.println("scaled parsed: " + scaledBack);
        System.out.println("BigDecimal.equals: "
                + scaled.equals(scaledBack));
        System.out.println("BigDecimal.compareTo: "
                + scaled.compareTo(scaledBack));

        DecimalFormat percent = (DecimalFormat)
                NumberFormat.getPercentInstance(Locale.US);
        percent.setParseBigDecimal(true);
        BigDecimal fraction = new BigDecimal("0.1245");
        String percentShown = percent.format(fraction);
        System.out.println("percent display: " + percentShown);
        System.out.println("percent parsed: "
                + percent.parse(percentShown));
    }
}
```

Run:

```bash
javac NumberRoundTripDemo.java
java NumberRoundTripDemo
```

Output on a JDK with standard locale data:

```text
original: 1234.567
shown: 1,234.57
parsed: 1234.57
same numeric value: false
scaled display: 1.2
scaled original: 1.20
scaled parsed: 1.2
BigDecimal.equals: false
BigDecimal.compareTo: 0
percent display: 12%
percent parsed: 0.12
```

**Three mechanisms of information loss:**

1. `1234.567 → 1,234.57 → 1234.57`: digit loss due to rounding.
2. `1.20 → 1.2 → 1.2`: preserves numeric value while losing scale.
3. `0.1245 → 12% → 0.12`: percentage formatting multiplies by 100 and rounds for display; parsing does not recover the original decimal fraction.

`NumberFormat.getPercentInstance` has locale/provider-dependent rules; this example uses `Locale.US` and displays whole percentages by default on tested JDKs. In production, explicitly configure fractional digits and rounding policy.

## 7. Parse Mode Can Also Lose Precision

Even before formatting, parsing a number into `double` can drop digits:

```text
input:      12345678901234567890.123456789
Double:     an approximate binary value
BigDecimal: preserves exact parsed decimal digits
```

In Java, `NumberFormat.parse(...)` normally returns `Long` or `Double` depending on input and configuration. On `DecimalFormat`, enabling `setParseBigDecimal(true)` parses **finite** numbers into `BigDecimal`, though it cannot restore precision already discarded by prior display formatting.

Keep `BigDecimal` throughout processing; calling `BigDecimal.doubleValue()` and converting back via `new BigDecimal(double)` can corrupt values. For canonical decimal inputs without locale separators, `new BigDecimal("1234.50")` avoids `DecimalFormat` parsing altogether.

**Exceptions to `setParseBigDecimal(true)`:** `NaN` or infinity can still parse as `Double` rather than `BigDecimal`. Nor does `BigDecimal` preserve negative zero distinctly from zero. If the domain allows only finite numbers, check both the returned type and value range.

## 8. Locale Mismatch: Same String, Two Different Values

Different locales can assign **opposite roles** to `.` and `,`:

| String | Under `en-US` | Under `de-DE` |
| --- | --- | --- |
| `1,234` | one thousand two hundred thirty-four | one point two three four |
| `1.234` | one point two three four | one thousand two hundred thirty-four |
| `1,234.50` | one thousand two hundred thirty-four point five | cannot be assumed to parse accurately |
| `1.234,50` | cannot be assumed to parse accurately | one thousand two hundred thirty-four point five |

Thus if you format in `de-DE` and parse back with an `en-US` parser, you can get the **wrong number with no exception**, or the parser may read only a prefix of the string.

Similarly, the grouping separator for `fr-FR` can be U+202F (*narrow no-break space*), not a standard ASCII space. Numeral systems such as `arab`, `thai`, or BCP 47 `u-nu-*` extensions change the text appearance while representing the same numeric value. Never blindly swap dots/commas or strip all whitespace to “normalize” input; use the data source's true locale and explicit validation.

**The locales used for formatting and parsing must be passed explicitly**—usually the same locale and symbol policy when an application intentionally performs a display round-trip. Never call `Locale.setDefault(userLocale)` per request: the default locale is JVM-wide shared state, not per-user state.

## 9. `parse` Can Read Only a Prefix

Another common mistake: assuming `parse(input)` returning a number means the **entire string was validated**. In reality, `NumberFormat.parse` can match a leading prefix and stop:

```text
raw:      "1,234.50oops"
parsed:   1234.50
ignored:  "oops"
```

Use `ParsePosition` to check how many characters the parser consumed:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleParseLimitsDemo {
    private static DecimalFormat parser(Locale locale) {
        NumberFormat base = NumberFormat.getNumberInstance(locale);
        if (!(base instanceof DecimalFormat decimal)) {
            throw new IllegalStateException("DecimalFormat required");
        }
        decimal.setParseBigDecimal(true);
        return decimal;
    }

    public static void main(String[] args) throws Exception {
        DecimalFormat us = parser(Locale.US);
        DecimalFormat de = parser(Locale.GERMANY);

        System.out.println("US 1,234: " + us.parse("1,234"));
        System.out.println("DE 1,234: " + de.parse("1,234"));
        System.out.println("US on DE text: " + us.parse("1.234,50"));

        String input = "1,234.50oops";
        ParsePosition position = new ParsePosition(0);
        Number parsed = us.parse(input, position);
        boolean fullInput = parsed instanceof BigDecimal
                && position.getIndex() == input.length();

        System.out.println("value: " + parsed);
        System.out.println("consumed: " + position.getIndex());
        System.out.println("length: " + input.length());
        System.out.println("fully parsed: " + fullInput);

        System.out.println("wrong grouping: "
                + us.parse("12,34.5"));
    }
}
```

```bash
javac LocaleParseLimitsDemo.java
java LocaleParseLimitsDemo
```

Output:

```text
US 1,234: 1234
DE 1,234: 1.234
US on DE text: 1.234
value: 1234.50
consumed: 8
length: 12
fully parsed: false
wrong grouping: 1234.5
```

Interpretation:

- `"1,234"` has opposite meanings across the two locales.
- The US parser reads `"1.234,50"` as `1.234` and ignores `,50`.
- `ParsePosition.getIndex()` checks consumed characters; in this example only 8 of 12 characters were read.
- Many Java number parsers **do not strictly enforce grouping separator positions**, so `"12,34.5"` still parses as `1234.5`.

**Important:** checking `position.getIndex() == input.length()` alone still does not guarantee that the input is the single canonical representation for that locale. For monetary inputs or strictly controlled data, also validate permitted formatting, length, character set, decimal places, grouping, value range, and scale. Never assume `parse(format(x))` or `format(parse(s))` proves the original data is completely valid.

## 10. Loss of Data Type, Signs, and Original Written Shape

A formatter can map multiple distinct types to the same string:

- Integer `1`, floating-point `1.0`, and `BigDecimal("1.00")` can all format as `"1"`.
- `-0.0` can format as `"-0.00"`, yet a parser with `setParseBigDecimal(true)` returns `BigDecimal("0.00")` without preserving the negative sign on zero.
- Input `"0012"` can re-format as `"12"`, losing its two leading zeros.
- Input with a `+` sign, with or without grouping, or with differing Unicode whitespace gets normalized into one canonical representation.

Therefore, ask **what data truly needs to be stored**. For item quantities, an integer value may suffice. For codes with leading zeros like `0012`, **it is a string identifier**, not a number—never parse it as a number and format it back. For audit logs requiring exact original text preservation, store the canonical value **and** raw input under data/privacy governance.

The same principle applies to currency and percentage formats: a `$` symbol cannot distinguish between USD, CAD, and AUD; `12%` does not reveal whether the underlying value was ratio `0.12`, percentage `12`, or a rounded `0.1245`. Type and unit belong in the schema/domain, never guessed backward from a UI string.

## 11. Date/Time Loses Even More Information Than Numbers

`java.time.format.DateTimeFormatter` is likewise designed for **presentation** and **pattern-based parsing**, not automatically packaging every field of a temporal object.

Example object:

```text
2026-10-28T08:45:37.123456789
```

If formatted with pattern `dd/MM/uuuu HH:mm`, the string retains only:

```text
28/10/2026 08:45
```

When parsed back into `LocalDateTime`, seconds and nanoseconds were absent from the string and default to 0 (if the target type can be constructed), rather than restoring the original values. Two distinct times `08:45:01` and `08:45:59` can both format to `08:45`.

Similarly:

| Format | What Can Be Lost |
| --- | --- |
| `dd/MM/uuuu` | Hour, minute, second, nanosecond |
| `dd/MM/uuuu HH:mm` | Seconds and nanoseconds; no zone/offset |
| `HH:mm` | Date, offset, zone; cannot recover an `Instant` from this alone |
| `ISO_OFFSET_DATE_TIME` | Offset is kept, but a **region ZoneId** like `Europe/Paris` is not recorded |
| Patterns with localized month names | Locale-dependent; ambiguous or fails if parsed under a different locale |
| Two-digit year patterns `yy` | Does not preserve the full century without extra pivot assumptions |

Storing only `LocalDateTime` cannot identify an absolute instant without a time zone or offset. In regions observing Daylight Saving Time (DST), a local wall-clock time can **not exist** (a gap) or **occur twice** (an overlap); `02:30` alone may not uniquely identify an `Instant`. Never work around this by falling back to the server's default time zone.

**A Java detail:** in `DateTimeFormatter` patterns, `uuuu` represents proleptic year, whereas `yyyy` is year-of-era. Under strict parsing (`STRICT`) without an era field, `yyyy` patterns can require era info or a matching resolver. The example below uses `uuuu`.

## 12. Java 17+ Example: Losing Seconds/Nanoseconds and Time Zone Identity

Create the file `DateTimeRoundTripDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DateTimeRoundTripDemo {
    public static void main(String[] args) {
        LocalDateTime original = LocalDateTime.of(
                2026, 10, 28, 8, 45, 37, 123_456_789);

        DateTimeFormatter minutes = DateTimeFormatter.ofPattern(
                "dd/MM/uuuu HH:mm", Locale.forLanguageTag("vi-VN"));

        String shown = minutes.format(original);
        LocalDateTime parsed = LocalDateTime.parse(shown, minutes);

        System.out.println("original: " + original);
        System.out.println("shown: " + shown);
        System.out.println("parsed: " + parsed);
        System.out.println("same: " + original.equals(parsed));

        ZonedDateTime zoned = ZonedDateTime.of(
                2026, 10, 28, 8, 45, 37, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));
        String withOffset = DateTimeFormatter.ISO_OFFSET_DATE_TIME
                .format(zoned);
        OffsetDateTime offsetParsed = OffsetDateTime.parse(
                withOffset, DateTimeFormatter.ISO_OFFSET_DATE_TIME);

        System.out.println("original zone: " + zoned.getZone());
        System.out.println("offset text: " + withOffset);
        System.out.println("parsed zone: "
                + offsetParsed.toZonedDateTime().getZone());
        System.out.println("same instant: "
                + zoned.toInstant().equals(offsetParsed.toInstant()));

        String withZone = DateTimeFormatter.ISO_ZONED_DATE_TIME
                .format(zoned);
        ZonedDateTime restored = ZonedDateTime.parse(
                withZone, DateTimeFormatter.ISO_ZONED_DATE_TIME);
        System.out.println("zone kept: " + restored.getZone());
        System.out.println("zoned equal: " + zoned.equals(restored));
    }
}
```

```bash
javac DateTimeRoundTripDemo.java
java DateTimeRoundTripDemo
```

Output on the verified Java version:

```text
original: 2026-10-28T08:45:37.123456789
shown: 28/10/2026 08:45
parsed: 2026-10-28T08:45
same: false
original zone: Asia/Ho_Chi_Minh
offset text: 2026-10-28T08:45:37+07:00
parsed zone: +07:00
same instant: true
zone kept: Asia/Ho_Chi_Minh
zoned equal: true
```

Explanation:

1. `DateTimeFormatter` at minute resolution **dropped seconds and nanoseconds**.
2. `ISO_OFFSET_DATE_TIME` preserves the offset and enough information for the instant in this case, but converting `OffsetDateTime` to `ZonedDateTime` gives a zone ID of `+07:00`, not `Asia/Ho_Chi_Minh`.
3. `ISO_ZONED_DATE_TIME` can store `[Asia/Ho_Chi_Minh]` and restore the zone here, but that does not make **arbitrary custom patterns** lossless.
4. Time zone rules in tzdb can be updated over time; if an application must reproduce exact historical display under a specific rule version, design appropriate storage and data versioning.

In business systems, store `Instant` for absolute points in time, and also store `ZoneId` if you need to preserve the regional “local wall-clock” semantics for future display. For future recurring appointments, you may need `LocalDateTime` plus `ZoneId` to keep explicit local time alongside a policy for DST gaps and overlaps.

## 13. Date/Time Parsing Can “Fix” Invalid Input If Configured Too Leniently

Not only can information be lost, legacy date parsers can silently adjust out-of-range dates.

For example, `java.text.SimpleDateFormat` defaults to **lenient** mode, so a nonexistent date like `"32/01/2026"` can roll over into the next month when parsed. In new code, prefer `java.time` with `DateTimeFormatter` and `ResolverStyle.STRICT` when validating input.

**Standalone** example:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;

public class StrictDateDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

        try {
            LocalDate.parse("31/02/2026", strict);
            System.out.println("accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("invalid date rejected");
        }

        System.out.println(LocalDate.parse("28/02/2026", strict));
    }
}
```

```bash
javac StrictDateDemo.java
java StrictDateDemo
```

```text
invalid date rejected
2026-02-28
```

`STRICT` catches invalid calendar dates, yet it does not supply missing zones/offsets or restore fields omitted from the pattern. **Strict parsing and lossless serialization are two different requirements.**

## 14. Re-Formatted Strings Do Not Necessarily Match Input Strings

Suppose a user enters:

```text
1234.50
```

An `en-US` parser produces `BigDecimal("1234.50")`. When formatted back with grouping enabled, display output becomes:

```text
1,234.50
```

Numerically the two strings are equivalent; character-by-character they differ. Even whitespace can differ (`U+0020` vs `U+202F`), or a locale might use `latn`, `arab`, or `thai` numeral scripts. Therefore:

- **Do not compare UI strings** to decide whether two numbers or temporal values are equal.
- **Do not use UI strings as signatures, identifiers, or cache keys** unless the contract defines every single representation property.
- **Do not rely on `format(parse(s)).equals(s)` as your sole validator**: it can reject valid inputs written slightly differently, or accept inputs from which the parser already dropped information.

If you need to verify the **canonical form of an input format**, parse strictly and check against an explicit schema—but treat that as an application policy, **not** a general guarantee of every formatter.

## 15. Other Cases That Do Not Round-Trip Automatically

### Currency and Units

A string `"$1,234.50"` contains a `$` sign without unambiguously conveying currency code, rounding rules, or unit. `NumberFormat.getCurrencyInstance(locale)` uses the locale's default currency, which may not match the transaction's currency. When storing money, use a structure like **amount + currency code** instead of inferring currency from a symbol.

### Percentages

Percentage formatting typically multiplies by 100 and appends `%`; `0.1245` may render as `12%`. Parsing back yields only `0.12`. Never mix ratio data (`0.12`) and percentage-point data (`12`) without standardizing the domain representation.

### Compact Numbers

Strings like `1K`, `1,2 nghìn`, or language-specific abbreviations contain rounded values and suffixes; you cannot reliably reconstruct the exact original number. Use `NumberFormat.getCompactNumberInstance` for display when appropriate, never as a storage format.

### Special Symbols and Negative Zero

`DecimalFormat` can format `Double.NaN`, infinity, or `-0.0`; after parsing, `BigDecimal` has no representation for NaN/infinity and does not distinguish negative zero like `double` does. If such special states are part of your domain, model them explicitly in your schema/types rather than relying on display strings.

## 16. Proper Design: Separating Domain Values, Storage, and Presentation

Define clear responsibilities for each layer:

| Layer | Recommended Representation | Responsibilities Only |
| --- | --- | --- |
| **Domain** | `BigDecimal`, `long`, `Instant`, `ZonedDateTime`, or well-typed business objects | Calculations, validation, interpretation |
| **Storage / API** | `DECIMAL`/`NUMERIC` columns, schema-typed JSON numbers, canonical decimal strings, ISO 8601, and needed metadata | Retaining all fields required for round-trip fidelity |
| **Presentation** | `NumberFormat`, `DecimalFormat`, `DateTimeFormatter` with `Locale` | Rendering text for human readers |
| **Input** | Locale-aware parser + validator with explicit policy | Interpreting user-entered text and rejecting invalid input |

Example of a safe flow:

```text
User input: "1.234,50" (de-DE)
    |
    | DecimalFormat de-DE; setParseBigDecimal(true)
    | ParsePosition + domain validation
    v
BigDecimal("1234.50")
    |
    +--> Store in DECIMAL(14,2) or schema decimal string
    |
    +--> Display "1,234.50" for en-US
    |
    +--> Display "1.234,50" for de-DE
```

If you need to preserve **how the user typed the input**, store raw input as a separate field (subject to privacy, security, and retention controls). You cannot reconstruct raw input text from a canonical `BigDecimal` once presentation characters have been discarded.

### Canonical Decimal Storage and Restoration Example

Create the file `CanonicalDecimalDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class CanonicalDecimalDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1234.50");

        String stored = original.toPlainString();
        BigDecimal restored = new BigDecimal(stored);

        NumberFormat display = NumberFormat.getNumberInstance(
                Locale.GERMANY);
        display.setMinimumFractionDigits(2);
        display.setMaximumFractionDigits(2);

        System.out.println("stored: " + stored);
        System.out.println("restored: " + restored.toPlainString());
        System.out.println("same BigDecimal: "
                + original.equals(restored));
        System.out.println("display: " + display.format(restored));
    }
}
```

```bash
javac CanonicalDecimalDemo.java
java CanonicalDecimalDemo
```

```text
stored: 1234.50
restored: 1234.50
same BigDecimal: true
display: 1.234,50
```

Here `BigDecimal.toPlainString()` preserves the decimal digits and scale for this example. It suits well-defined decimal-string storage contracts; for `BigDecimal` values with negative scale, `toPlainString()` can alter scale representation upon restoration, so if **preserving every scale in all cases** is a strict requirement, use `toString()` with `new BigDecimal(String)` or store `unscaledValue` + `scale` explicitly. Do not treat `toPlainString` as an absolute contract for every representation property of all `BigDecimal`s.

Canonical form means more than “stripping grouping separators”: you must also define type, negative sign, bounds, precision, scale, and time zone/currency where applicable.

## 17. Checklist for Checking Round-Trips in Java

Before choosing `parse(format(x))`, answer these questions:

1. **Goal:** do you need to preserve the mathematical value, exact object identity, exact instant, or exact original string?
2. **Is rounding involved?** What are the maximum fraction digits, precision, and rounding mode?
3. **Can scale be lost?** How does `BigDecimal.equals` differ from `compareTo` in your domain?
4. **Are fields dropped?** Does the date/time formatter omit seconds, nanos, zone, offset, era, or chronology?
5. **Which locale is used in both directions?** Is it stable across requests and different hosts?
6. **Are symbols or grouping ambiguous?** How are `,`, `.`, U+202F, and non-Latin digits handled?
7. **Does the parser consume the full string?** Check `ParsePosition`/unresolved state or use an appropriate strict parse API.
8. **Is the parser lenient?** Will it accept invalid grouping or silently fix nonexistent dates?
9. **Are there special values?** NaN, infinity, signed zero, DST gaps/overlaps, currency?
10. **Must raw text be preserved verbatim?** If so, it cannot be reconstructed from a parsed value.
11. **Have all runtime versions/locale providers been tested?** CLDR data, patterns, and Unicode symbols can evolve.
12. **Does serialization have a schema?** Persist type/scale, currency, zone, and required metadata rather than a display string.

For round-trip tests, separate assertions clearly:

- `assertNumericEquals`: check numeric equality when scale loss is acceptable.
- `assertEquals`: verify full identity/scale/zone when that is the contract.
- `assertTextEquals`: use only when **exact text preservation** is required.
- `assertRejectsInvalid`: verify rejection of trailing text, wrong grouping, invalid dates, and disallowed special numbers.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `format(x)` as the default serialization mechanism | Rounding, locale, and pattern can lose data | Store canonical schema/domain values |
| Re-parsing a rounded display number and expecting the original | Discarded digits are gone from the string | Never use display strings as the source of truth |
| Thinking `setParseBigDecimal(true)` restores lost precision | It only preserves the **string actually parsed** | Preserve precision before formatting |
| Calling `BigDecimal.equals` without considering scale | Inequality despite identical arithmetic value | Choose equality semantics per business logic |
| Parsing with a different locale than formatting | Wrong value or partial parse | Pass locale and settings explicitly |
| Not checking trailing input | `parse` accepts prefix and ignores bad tail | Use `ParsePosition` and validation |
| Treating full-string consumption as grouping validation | Parser may be lenient about separator placement | Validate syntax per contract |
| Formatting dates to minutes and expecting nanoseconds back | Sub-minute fields were discarded | Persist full temporal precision |
| Storing offset without region zone ID | Cannot recover `Asia/Ho_Chi_Minh` | Store `ZoneId` when needed |
| Storing `LocalDateTime` and converting to instant via default timezone | Wrong across DST or regions | Store `Instant` or zone plus DST policy |
| Assuming `NaN`/infinity becomes `BigDecimal` | `ClassCastException` or invalid data | Validate runtime type and domain |
| Storing code `0012` as a number | Leading zeros are lost | Identifiers must be `String` |
| Sharing a mutable `DecimalFormat` singleton across threads | Race conditions and config corruption | Use per-operation formatters |
| Inferring currency from a localized display string | Currency symbols can be ambiguous | Store currency code separately |

## 19. Self-Check

1. **What can `parse(format(new BigDecimal("1234.567")))`** produce under a two-decimal-digit pattern? **`1234.57`**, not `1234.567`.
2. **`1.20` and `1.2`** both format as `1.2`: can you recover the original scale? **No**, because two distinct values mapped to the exact same string.
3. If you enable `parseBigDecimal`, do digits rounded off by the formatter come back? **No**; the parser only sees the current input string.
4. Does `"1,234"` have the same value in `en-US` and `de-DE`? **No**; the locales interpret it as `1234` vs `1.234`.
5. Why can `parse("1,234.50oops")` return a number without throwing? **The parser can accept a prefix**; inspect `ParsePosition`.
6. If a display string stops at minutes, can original nanoseconds be recovered from it? **No**.
7. Does `ISO_OFFSET_DATE_TIME` keeping offset `+07:00` restore `ZoneId.of("Asia/Ho_Chi_Minh")`? **Not automatically**; an offset is not a region ID.
8. Can you derive an exact `Instant` from `LocalDateTime` without knowing zone/offset? **No**, especially across DST gaps/overlaps.
9. For `BigDecimal("1.20")` and `BigDecimal("1.2")`, how do `compareTo` and `equals` differ? **`compareTo == 0` while `equals == false`**.
10. To preserve the exact bytes/characters typed by a user like `"001234.50"`, is storing `BigDecimal` alone sufficient? **No**; store the raw text or extra presentation metadata.
11. When storing monetary data, does formatting `"$10.00"` carry enough information? **No**; you need the currency code and amount in a proper schema.
12. What is the cleanest separation of responsibilities? **Domain/storage keeps exact types and data, presentation formats per locale, and input parser + validator converts text into domain values.**

## References

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): locale-aware formatting/parsing and parser boundaries.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): patterns, rounding, `setParseBigDecimal`, and `NaN`/infinity handling.
- [Java SE 21 — ParsePosition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ParsePosition.html): inspecting consumed length.
- [Java SE 21 — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): numeric value, scale, precision, and canonical strings.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): patterns, ISO formatters, and resolver styles.
- [Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html): zones, offsets, instants, and DST.
- [Unicode CLDR — Date/Number Formats](https://cldr.unicode.org/): locale data that influences symbols and format styles.