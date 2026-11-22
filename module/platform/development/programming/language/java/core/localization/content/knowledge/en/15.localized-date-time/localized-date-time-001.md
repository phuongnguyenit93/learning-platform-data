# DateTimeFormatter with an Explicit Locale in Java

## 1. Why Must You Choose a Locale When Formatting Dates and Times?

The same date `2026-10-28` can be read by users in different regions in different representations:

- US English: **Wednesday, 28 October 2026**.
- Vietnamese: **Thứ Tư, 28 tháng 10 2026**.
- French: **mercredi, 28 octobre 2026**.

All three phrases describe the **same date**, yet the day-of-week name, month name, capitalization, component order, and punctuation can differ. If Java manually concatenates `day + " October " + year`, the message depends on the language hardcoded in the source code and is hard to use for an international audience.

Java 8+ provides `java.time.format.DateTimeFormatter` to format and *parse* dates/times. The API supports choosing an **explicit `Locale`** right when creating the formatter or creating a copy with `withLocale(locale)`. In applications running Java 17+, this is the preferred approach for `java.time` date-time types.

**Goals:** know how to use `DateTimeFormatter.ofPattern(pattern, locale)`, `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)`, and `LocalDate.parse(text, formatter)`; understand how locale affects text, why **a locale is not a time zone**, how to write programs with reproducible output, and how to avoid depending on the server's `Locale.getDefault()`.

## 2. Distinguishing Three Layers of Information

An application may need three separate pieces of information:

| Concept | Example | What does it decide? |
| --- | --- | --- |
| Date/time to represent | `LocalDate.of(2026, 10, 28)` | Calendar value: day, month, year |
| Viewer's locale | `Locale.forLanguageTag("vi-VN")` | Language of month names, day names, localized formatting rules |
| Viewer's time zone | `ZoneId.of("Asia/Ho_Chi_Minh")` | How a global instant is converted to local wall-clock time |

Do not use `Locale` as a `ZoneId`. Choosing `vi-VN` **does not automatically convert an `Instant` to Vietnam time**. Similarly, choosing `Asia/Ho_Chi_Minh` does not mean the text in the sentence must be written in Vietnamese.

Nor should you equate a locale with an invariant API format:

- **Dates displayed to users** need a formatter tied to the locale and product requirements.
- **Dates used as exchange data** typically use ISO 8601 or a protocol-defined format; they do not depend on the viewer's language.
- **Dates/times in logs or events** typically need an offset/zone and an unambiguous representation.

In modern Java, you typically use `LocalDate` for a date without time, `LocalTime` for a time without date, `LocalDateTime` for a date and time **without a time zone**, `ZonedDateTime` when a time zone is needed, `OffsetDateTime` when an offset is present, and `Instant` for a point on the UTC timeline.

## 3. Essential API and Syntax

### 3.1. Formatter from a Pattern with a Locale

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", Locale.US);
```

The pattern consists of these components:

- `EEEE`: full day-of-week name, for example `Wednesday`.
- `d`: day of month, for example `28`.
- `MMMM`: full month name, for example `October`.
- `uuuu`: calendar year as proleptic year (*year*, including year 0 in the ISO calendar system).
- Commas and spaces are pattern literals.

When calling `formatter.format(date)`, the day-of-week and month names are looked up from locale data, not from a hardcoded English string. The pattern `EEEE, d MMMM uuuu` **still fixes the field order and punctuation**, because the developer specified them. If you want the system to choose a natural date style for the locale, use the localized style formatters in the next section.

### 3.2. Creating a Copy for Another Locale

```java
DateTimeFormatter english =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", Locale.US);

DateTimeFormatter vietnamese =
        english.withLocale(Locale.forLanguageTag("vi-VN"));
```

`withLocale(...)` **returns a new formatter**; it does not mutate the `english` object. `DateTimeFormatter` is **immutable and thread-safe**. This is very useful in web services serving many users with different locales.

### 3.3. Formatter by Localized Format Style

```java
DateTimeFormatter localized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(Locale.US);
```

Instead of writing the order `d MMMM uuuu` manually, `ofLocalizedDate` uses each locale's length rules; `withLocale` determines the locale used when formatting.

`FormatStyle` has the values `FULL`, `LONG`, `MEDIUM`, and `SHORT`. They represent the **level of detail**, without guaranteeing the same pattern across locales. For example, `LONG` in the US may use `October 28, 2026`, whereas another locale may place the day before the month.

### 3.4. Parsing with the Matching Formatter

```java
LocalDate parsed = LocalDate.parse(text, formatter);
```

When a pattern contains month names in words, the locale must match the language of the input string. When a pattern consists only of digits and separators, the locale may have less visible impact, but resolver style, `DecimalStyle`, and the calendar system still need to be considered.

## 4. Complete Java 17+ Example: One Date, Three Locales

Create the file `ExplicitLocaleDemo.java`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ExplicitLocaleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "EEEE, d MMMM uuuu", Locale.US);

        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        DateTimeFormatter vi = base.withLocale(vietnamese);
        DateTimeFormatter fr = base.withLocale(Locale.FRANCE);

        System.out.println("US: " + base.format(date));
        System.out.println("VI: " + vi.format(date));
        System.out.println("FR: " + fr.format(date));
    }
}
```

Compile with Java 17+ (save the file as UTF-8):

```bash
javac -encoding UTF-8 ExplicitLocaleDemo.java
java ExplicitLocaleDemo
```

Stdout verified with OpenJDK 24 locale data:

```text
US: Wednesday, 28 October 2026
VI: Thứ Tư, 28 tháng 10 2026
FR: mercredi, 28 octobre 2026
```

Notice these characteristics:

1. `LocalDate` and the date value **do not change**.
2. `base` still uses `Locale.US`; `withLocale` does not mutate the original formatter.
3. Day-of-week and month names change by locale; **the field order remains as specified in the fixed pattern**.
4. With different CLDR/JDK data, capitalization or month-name details may vary slightly. Do not treat the exact day/month name output of one JDK version as a fixed contract across all JDK releases.

This is an example of **formatting with an explicit locale**, unlike:

```java
DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu")
```

The overload without a locale uses the appropriate default locale at the time the formatter is created, risking different strings between a development machine and a server.

## 5. `ofLocalizedDate` for Natural Localized Date Layouts

If the goal is "display the date in the user's style" rather than "enforce a developer-defined layout", prefer a localized style:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedDateStyleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 28);

        DateTimeFormatter us =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(Locale.US);

        DateTimeFormatter vi =
                us.withLocale(Locale.forLanguageTag("vi-VN"));

        System.out.println("US: " + us.format(date));
        System.out.println("VI: " + vi.format(date));
    }
}
```

Save as `LocalizedDateStyleDemo.java` and run:

```bash
javac -encoding UTF-8 LocalizedDateStyleDemo.java
java LocalizedDateStyleDemo
```

Illustrative stdout verified on OpenJDK 24:

```text
US: October 28, 2026
VI: 28 tháng 10, 2026
```

With `ofLocalizedDate`, the output is a **layout chosen by locale data**, not just translating field names inside a pattern written in code. This differs from `ofPattern("MMMM d, uuuu", Locale.FRANCE)`: even though `MMMM` is translated, the `month -> day -> year` order is still imposed by the programmer.

Other factories:

| API | Appropriate input data | Notes |
| --- | --- | --- |
| `ofLocalizedDate(style)` | `LocalDate` | Date without time |
| `ofLocalizedTime(style)` | `LocalTime` or a temporal with appropriate time fields | For some styles (e.g. FULL/LONG), time-zone data may be required |
| `ofLocalizedDateTime(style)` | `LocalDateTime` or an appropriate temporal | Required detail depends on the formatter style |
| `ofLocalizedDateTime(dateStyle, timeStyle)` | temporal with sufficient date and time fields | Allows different detail levels for date and time |

**Warning:** not every time `FormatStyle` can format a `LocalTime` without a time zone, especially if the locale data uses a time-zone name. You must choose a temporal type that matches the fields required by the formatter.

## 6. Passing Locale in Multi-Request Applications

Many systems obtain the locale from an account, a configuration cookie, or `Accept-Language`. Wherever the input comes from, you should:

1. Restrict/select a locale actually supported by the product.
2. Convert it to a `Locale` using `Locale.forLanguageTag(tag)` or an existing `Locale` object.
3. Pass the locale into the formatter or `withLocale`.
4. Do not mutate the JVM-wide default locale to serve individual requests.

Example of a **standalone** method you can place in a `DateView` class:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public final class DateView {
    private DateView() {}

    public static String display(LocalDate date, Locale locale) {
        if (date == null || locale == null) {
            throw new IllegalArgumentException(
                    "date and locale must not be null");
        }
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale);
        return formatter.format(date);
    }
}
```

Save as `DateView.java` and compile:

```bash
javac -encoding UTF-8 DateView.java
```

This is a compilable **utility class** without a `main` method, so `java DateView` is not a run step. The code calling `DateView.display(date, requestLocale)` in a controller/service is responsible for choosing the appropriate locale.

Do not write this in a controller:

```java
Locale.setDefault(requestLocale);
String text = DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
        .format(date);
```

This is **code illustrating an anti-pattern to avoid**: `Locale.setDefault` mutates JVM-wide shared state; concurrent requests can affect one another, as well as other libraries that rely on the default locale.

An immutable `DateTimeFormatter` lets you reuse a base formatter and call `withLocale` to obtain the right instance for each language. For APIs with an `ofPattern(pattern, locale)` overload, passing the locale directly also makes the intent clear.

## 7. Locale Does Not Automatically Change Time Zones: Instant and ZoneId Example

`Instant` is a point on the UTC timeline; it does not carry "10:30 in Vietnam" or "03:30 in UTC" as a user-facing representation. To format a time in a specific time zone, you need `ZoneId`, `ZonedDateTime`, or a formatter with `withZone`.

Standalone program:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class TimeZoneDisplayDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-10-28T03:30:00Z");

        DateTimeFormatter base =
                DateTimeFormatter.ofPattern(
                        "uuuu-MM-dd HH:mm VV", Locale.US);

        DateTimeFormatter utc =
                base.withZone(ZoneId.of("UTC"));
        DateTimeFormatter vietnam =
                base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC: " + utc.format(instant));
        System.out.println("VN: " + vietnam.format(instant));
    }
}
```

Run:

```bash
javac -encoding UTF-8 TimeZoneDisplayDemo.java
java TimeZoneDisplayDemo
```

Stdout:

```text
UTC: 2026-10-28 03:30 UTC
VN: 2026-10-28 10:30 Asia/Ho_Chi_Minh
```

**Core point:** `Instant` still represents the exact same moment; `withZone` chooses how to express the time for a region. `withLocale` is not responsible for converting offsets. The pattern uses `VV` to print the **time-zone ID**; if you use time-zone names such as `zzzz`, the wording may vary by locale/data provider.

If a formatter only has `"HH:mm"` and formats an `Instant` directly **without providing a zone**, it can throw `UnsupportedTemporalTypeException` because the temporal lacks hour/minute fields. The right approach is to create a formatter with a zone (`withZone`) or convert `instant.atZone(zoneId)` and then format the `ZonedDateTime`.

In international interfaces, locale and time zone should be **two independent choices**. A Vietnamese speaker located in Paris may want Vietnamese month names and time in `Europe/Paris`; using `Locale.forLanguageTag("vi-VN")` with `ZoneId.of("Europe/Paris")` is completely valid.

## 8. Parsing Strings with Month Names: You Must Use the Matching Language

Formatting and parsing are two directions of the same contract over pattern and locale. For example, the French string `"28 octobre 2026"` needs a formatter that reads the month name `octobre` using a French locale:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ParseFrenchDateDemo {
    public static void main(String[] args) {
        DateTimeFormatter french =
                DateTimeFormatter.ofPattern(
                        "d MMMM uuuu", Locale.FRANCE);

        LocalDate date = LocalDate.parse(
                "28 octobre 2026", french);

        System.out.println(date);
        System.out.println(french.format(date));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ParseFrenchDateDemo.java
java ParseFrenchDateDemo
```

Stdout:

```text
2026-10-28
28 octobre 2026
```

If you use the same pattern with `Locale.US`, the parser will not recognize `octobre` as `October` under normal rules and will throw `DateTimeParseException`.

When parsing user-supplied strings, you need to know:

- What language is the string in? If it contains month names in words, you must know the string's locale.
- Does the pattern match the structure the user enters?
- Does the resolver style accept or adjust invalid dates?
- Does the string include a zone/offset? If not, you cannot infer a unique UTC instant on its own.
- For free-form multilingual input, a single formatter is usually not enough. Restrict the accepted input formats or use controlled recognizers with clear error messages.

**Do not use `DateTimeFormatter` to manually translate an arbitrary string.** If you have `"28 octobre 2026"`, the right approach is to parse it into a `LocalDate` with a French formatter, then format that same `LocalDate` with a Vietnamese formatter; do not string-replace `octobre` with `tháng 10` directly on the text.

## 9. ResolverStyle: Do Not Confuse Invalid Date Errors with Locale Errors

By default, `DateTimeFormatter.ofPattern` uses resolver style `SMART`. For certain invalid dates, `SMART` may adjust the day to the last day of the month. If the application requires entering an actual valid calendar date, configuring `ResolverStyle.STRICT` is the explicit choice.

Standalone runnable example:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictDateParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict =
                DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println(
                LocalDate.parse("28/10/2026", strict));

        try {
            LocalDate.parse("31/02/2026", strict);
        } catch (DateTimeParseException error) {
            System.out.println("Invalid date");
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 StrictDateParseDemo.java
java StrictDateParseDemo
```

Stdout:

```text
2026-10-28
Invalid date
```

To parse years strictly when working with the standard ISO calendar, use `uuuu` instead of `yyyy` if you want the proleptic year field and want to avoid `year-of-era` issues where the era is missing. Even so, `uuuu` has different semantics from `yyyy` for BCE years, so choose based on your data model.

**Distinction:** `Locale` determines localized names and conventions; `ResolverStyle` determines how date/time fields are validated and resolved during parsing. These are two independent policies.

## 10. Pattern Characters That Are Easy to Confuse

Some frequently used characters:

| Character | Meaning | Notes |
| --- | --- | --- |
| `u` / `uuuu` | Proleptic year | Usually appropriate for strict parsing in ISO |
| `y` / `yyyy` | Year of era | May require an era in strict parsing |
| `M`, `MM` | Numeric month | One or two digits depending on the pattern |
| `MMM`, `MMMM` | Short/full month name | Locale-dependent |
| `L` | Stand-alone month | May differ from in-context form in some languages |
| `d`, `dd` | Day of month | `dd` requires two digits |
| `E`, `EEEE` | Day-of-week name | Locale-dependent |
| `H`, `HH` | Hour 0–23 | Do not confuse with `h` (1–12) |
| `h` | 12-hour clock hour | Usually used together with `a` (AM/PM) |
| `m` | Minute | Different from `M` (month) |
| `s` | Second | Do not confuse seconds units when parsing |
| `X`, `XXX` | ISO-style UTC offset | Different from a time-zone ID |
| `V`, `VV` | Time-zone ID | `VV` is the common pattern for the ID |
| `z`, `zzzz` | Time-zone name | Dependent on locale/data provider |

**Note on uppercase `YYYY`:** in `DateTimeFormatter`, `Y` is the *week-based-year*, **not the ordinary calendar year**. Using `YYYY-MM-dd` can produce a seemingly wrong year on dates near the start or end of a year. For ISO calendar dates, use `uuuu-MM-dd` or a dedicated ISO formatter.

In patterns, single quotes are used to quote literal text. For example, `"d 'tháng' M uuuu"` prints the literal word `tháng`, which is only appropriate when the product fixes that wording for one language. If you want localized month names across multiple locales, use `MMMM` or a localized style.

## 11. Not Every Formatter Depends on Locale

Many formatters with numeric-only patterns can produce the same string across different locales, for example:

```java
DateTimeFormatter format =
        DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.FRANCE);
```

If `LocalDate` is `2026-10-28`, the output is typically still `2026-10-28`: there are no month or day names to translate, and a formatter created by `ofPattern` defaults to `DecimalStyle.STANDARD` unless customized. That does not mean locale is useless: once you switch to `MMMM`, `EEEE`, localized patterns, or controlled chronologies, the differences become apparent.

Formatters such as `DateTimeFormatter.ISO_LOCAL_DATE` are designed for stable ISO representations and are usually appropriate for technical data. Do not use localized month names as JSON keys or date identifiers in data payloads.

**DecimalStyle and digits:** `withLocale` does not automatically convert digits into a desired numbering system. When you need to change the digit system, check `DecimalStyle` and `withDecimalStyle`; you must verify the corresponding locale/JDK data. This is a separate concern from translating month names.

## 12. Effect of Locale on Formatter Objects

`DateTimeFormatter` is immutable: the following calls each create a new formatter:

```java
DateTimeFormatter fr = base.withLocale(Locale.FRANCE);
DateTimeFormatter zoned = fr.withZone(ZoneId.of("Europe/Paris"));
DateTimeFormatter strict = fr.withResolverStyle(
        ResolverStyle.STRICT);
```

This is an **illustrative snippet**, assuming a `base` variable of type `DateTimeFormatter` and the corresponding imports. It does not mutate `base`, `fr`, or other requests. Because formatters are immutable and thread-safe, you can cache base formatters or formatters configured with the exact locale/zone, provided the cache key reflects every relevant attribute.

If a system serves many regions and formats, you can use a dedicated service for building formatters:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public final class DateTimeView {
    private DateTimeView() {}

    public static String displayDate(
            LocalDate date, Locale locale) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                        .withLocale(locale);
        return formatter.format(date);
    }

    public static String displayInstant(
            java.time.Instant instant, Locale locale,
            ZoneId zone) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.MEDIUM)
                        .withLocale(locale)
                        .withZone(zone);
        return formatter.format(instant);
    }
}
```

Save into `DateTimeView.java` and run `javac -encoding UTF-8 DateTimeView.java`. This is a **compilable utility class without a main method**, not a self-printing stdout example. In a real project, validate nulls, define the policy for allowed locales/time zones, and check input data types.

For multi-tenant applications, what matters is not creating a brand-new formatter everywhere at all costs, but **never letting one user's locale/timezone choice mutate global state** for other users.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `ofPattern(pattern)` without a locale | Depends on the JVM's default locale | Use `ofPattern(pattern, locale)` |
| Using the same US pattern for every language | Month names are translated, but field order is hardcoded | Use `ofLocalizedDate(style)` when a localized layout is needed |
| Calling `Locale.setDefault` per request | Mutates global state, can affect other requests | Pass the locale explicitly |
| Assuming locale changes the time zone | Displayed time is offset from the user's zone | Pass `ZoneId` separately |
| Formatting `Instant` with `"HH:mm"` without a zone | Can fail due to missing time fields | `withZone` or `instant.atZone(zone)` |
| Parsing French month names with `Locale.US` | Cannot recognize the text | Use the locale matching the input |
| Using `YYYY` instead of `uuuu` | Week-based year can be wrong at year boundaries | Use an appropriate calendar-year pattern |
| Parsing invalid input dates with default `SMART` | Can silently adjust the date | `ResolverStyle.STRICT` when business rules require it |
| Using `yyyy` without considering era in `STRICT` | May fail to build `LocalDate` | Use `uuuu` when appropriate for the ISO calendar |
| Using localized text as API data | API changes when server/language changes | Use ISO or a fixed protocol format |
| Assuming localized style output is invariant | Varies across CLDR/JDK/providers | Test on the target environment |
| Confusing `withLocale` with `withDecimalStyle` | Digits may not change as expected | Configure `DecimalStyle` when a digit system is needed |
| Formatting time messages via string concatenation | Wrong order, punctuation, or grammar | Use formatters and proper localized message bundles |

`DateTimeFormatter` does not handle all i18n work. If a sentence contains natural-language prose such as "Your order will be delivered on {date}", use a complete resource message and insert the formatted date into the placeholder at the appropriate position; do not concatenate prefixes/suffixes from multiple fixed fragments.

## 14. Testing Checklist

For localized date/time display features, at minimum you should test:

1. **Explicit locale:** the same `LocalDate` displays month/day names matching `en-US`, `vi-VN`, `fr-FR`.
2. **Component order:** with `FormatStyle.LONG`, layouts across locales can differ; do not hardcode expectations from another locale's pattern.
3. **Formatter immutability:** `base.withLocale(locale)` does not change the formatting result of `base`.
4. **Time zones:** with the same `Instant`, compare `UTC` with `Asia/Ho_Chi_Minh`; verify the underlying instant does not change.
5. **Input with text month names:** parse French using `Locale.FRANCE`, and verify errors with a different locale.
6. **Strict parsing:** `28/10/2026` is valid, while `31/02/2026` must fail in `STRICT`.
7. **Year boundaries:** test dates near Jan 1 and Dec 31 if any pattern includes a year, avoiding confusion between `Y` and `u`.
8. **Zone-less data:** ensure `Instant` is formatted with an explicit zone, and `LocalDateTime` is not arbitrarily interpreted as UTC.
9. **Technical data:** serialized dates follow the API format, not localized UI output.
10. **Localized data:** output can be affected by JDK/CLDR versions, so test against the deployed runtime/locale data.
11. **Concurrency:** never call `Locale.setDefault` per request; immutable formatters can be reused in a controlled way.

### Practice Exercises

- Write a formatter `DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", Locale.GERMANY)`, format `LocalDate.of(2026, 10, 28)`, and compare the month name with `Locale.FRANCE`.
- Replace `FormatStyle.LONG` with `FULL` and `SHORT` in the section 5 example; inspect how the date is written and check whether output depends on the provider.
- Try parsing `"28 octobre 2026"` with a `Locale.US` formatter; catch and explain `DateTimeParseException`.
- Create a fixed `Instant` and format it for UTC, `Asia/Ho_Chi_Minh`, and `Europe/Paris`; verify the difference comes from the time zone rather than the locale.
- Write a test with `ResolverStyle.STRICT` for `29/02/2024` (valid) and `29/02/2025` (invalid).
- Design a `deliveryTime` field for an API: decide to use `Instant`/`OffsetDateTime` and ISO format, then render it for users in the UI layer according to their locale/timezone.

## 15. Conclusion

**`DateTimeFormatter` + an explicit `Locale`** helps Java display day/month names and presentation styles accurately for readers, without accidentally depending on the server's default locale configuration.

Remember the three independent decisions: **time value** (`LocalDate`, `Instant`, `ZonedDateTime`…), **display locale** (`Locale`), and **time zone** (`ZoneId`). Use `ofLocalizedDate(...).withLocale(locale)` when you want a locale-appropriate date layout, use `ofPattern(..., locale)` when a specific template is required, and use `ResolverStyle.STRICT` when parsing input that must represent a valid date. For APIs and storage, keep clear technical formats instead of translated date strings.

## Official References

- [Oracle Java 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java 21 — FormatStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/FormatStyle.html)
- [Oracle Java 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)
- [Oracle Java 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)
