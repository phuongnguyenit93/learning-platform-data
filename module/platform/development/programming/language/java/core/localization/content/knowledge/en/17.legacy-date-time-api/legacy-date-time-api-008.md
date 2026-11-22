# Migrating Localization Code from the Legacy Date-Time API to java.time

## 1. Why migrate?

Java has two commonly seen families of date-time APIs in multilingual applications:

- **Legacy family**: `java.util.Date`, `java.util.Calendar`, `java.util.TimeZone`, `java.text.DateFormat`, and `java.text.SimpleDateFormat`.
- **Modern family** (Java 8+, recommended on Java 17+): `java.time.Instant`, `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, `OffsetDateTime`, `YearMonth`, `ZoneId`, and `java.time.format.DateTimeFormatter`.

The motivation is not just writing less code. Objects like `SimpleDateFormat` and `Calendar` hold mutable state; `SimpleDateFormat` is **unsafe to share across threads** without synchronization. By contrast, most `java.time` value types and `DateTimeFormatter` are **immutable and thread-safe**, while cleanly separating absolute instants, local dates, local times, time zones, and display conventions.

However, a blind "find-and-replace" from `SimpleDateFormat` to `DateTimeFormatter` can introduce bugs because **pattern letters are not completely equivalent** and **the source object's semantics may differ**.

**Lesson objective:** migrate data types, locales, timezones, patterns, parsing, and testing rules accurately without altering date-time meaning.

### Before and after

~~~java
// Legacy style: may use implicit locale/timezone if unspecified.
SimpleDateFormat old =
        new SimpleDateFormat("dd MMMM yyyy HH:mm", Locale.US);
old.setTimeZone(TimeZone.getTimeZone("UTC"));
String textOld = old.format(legacyDate);

// Modern style: immutable formatter, explicit locale and zone.
DateTimeFormatter modern = DateTimeFormatter
        .ofPattern("dd MMMM uuuu HH:mm", Locale.US)
        .withZone(ZoneId.of("UTC"));
String textNew = modern.format(instant);
~~~

These are **illustrative method snippets**. The `Date` variable `legacyDate` and `Instant` variable `instant` must represent the same point in time; imports are required for `java.text.SimpleDateFormat`, `java.util.Date`, `java.util.Locale`, `java.util.TimeZone`, `java.time.Instant`, `java.time.ZoneId`, and `java.time.format.DateTimeFormatter`.

More important than syntax: **the specified timezone must match, the locale must match, and the temporal objects must share the same meaning**. Otherwise, differing outputs are not necessarily the formatter's fault.

## 2. Choose the right java.time type before replacing the formatter

The first step is answering: *is the stored data an absolute point in time, or only a local date/time?*

| Legacy data/type | Typically suitable java.time type | Meaning |
| --- | --- | --- |
| `Date` representing a UTC instant on the timeline | `Instant` | An absolute point in time, storing neither locale nor timezone |
| `Calendar` with a timezone | `ZonedDateTime` or `Instant` + `ZoneId` | Local time value and rules per time zone |
| Birthdate / payment date without time | `LocalDate` | Calendar date, not an instant |
| Fixed daily opening hours | `LocalTime` | Hour and minute, without date or zone |
| Appointment "9:00 on March 5" not yet bound to a zone | `LocalDateTime` | Local date and time, not yet identifying an absolute instant |
| Instant with a specific UTC offset | `OffsetDateTime` | Time + UTC offset; does not hold full DST transition rules |
| Appointment in a geographic time zone | `ZonedDateTime` | Date/time + `ZoneId` such as `Europe/Berlin` |
| Month and year in a filter | `YearMonth` | Year and month, without day |
| `TimeZone` | `ZoneId` | Identifies time zone / local rules |
| `DateFormat`/`SimpleDateFormat` | `DateTimeFormatter` | Formats/parses modern temporal types |

**Do not automatically replace every `Date` with `LocalDateTime`.** `Date` carries an instant, whereas `LocalDateTime` has no zone. Converting `Date` to `LocalDateTime` requires specifying a **zone**; omitting the zone can produce the wrong hour or even the wrong day.

Conversely, a "birthdate" field containing just `2025-03-05` should normally be `LocalDate`, rather than arbitrarily forcing it into an `Instant` at midnight UTC.

### Locale is not TimeZone

- `Locale.forLanguageTag("vi-VN")`: chooses language/region for formatting month names, separators, and date layout.
- `ZoneId.of("Asia/Ho_Chi_Minh")`: chooses local clock rules.
- `Instant.parse("2025-03-05T10:15:30Z")`: chooses the **point in time**.

The same `Instant` can display different hours in Vietnam and the US; the same `ZoneId` can display different date layouts for two `Locale`s.

## 3. Controlled conversion of Date, Calendar, and TimeZone

### 3.1. Date ↔ Instant

~~~java
Date legacy = Date.from(
        Instant.parse("2025-03-05T10:15:30Z")
);
Instant modern = legacy.toInstant();

Date backToLegacy = Date.from(modern);
~~~

This is a method snippet requiring imports for `java.util.Date` and `java.time.Instant`.

- `Date.toInstant()` preserves the same **point in time**.
- `Date.from(instant)` constructs an object for legacy APIs.
- `Date` holds no display timezone. `Date.toString()` may use the JVM default time zone when building a string, but that **does not** make timezone a property of the `Date` object.

### 3.2. Calendar → ZonedDateTime/Instant

For `GregorianCalendar`, Java provides `toZonedDateTime()`:

~~~java
GregorianCalendar legacyCalendar =
        new GregorianCalendar(
                TimeZone.getTimeZone("Asia/Ho_Chi_Minh"),
                Locale.forLanguageTag("vi-VN")
        );
legacyCalendar.setTimeInMillis(
        Instant.parse("2025-03-05T10:15:30Z").toEpochMilli()
);

ZonedDateTime zoned = legacyCalendar.toZonedDateTime();
Instant instant = legacyCalendar.toInstant();
~~~

This is a method snippet requiring imports for `java.util.GregorianCalendar`, `java.util.TimeZone`, `java.util.Locale`, `java.time.ZonedDateTime`, and `java.time.Instant`.

**Note:** `Calendar` can represent various calendar systems, not necessarily `GregorianCalendar`. Do not blindly cast every `Calendar` to `GregorianCalendar`; know the chronology and conversion goal. If you only need the **instant**, `calendar.toInstant()` avoids misinterpreting calendar fields. If you need to preserve the timezone, check `calendar.getTimeZone().toZoneId()` and convert accordingly.

### 3.3. TimeZone ↔ ZoneId

~~~java
TimeZone oldZone =
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh");
ZoneId zone = oldZone.toZoneId();

TimeZone backwardCompatible = TimeZone.getTimeZone(zone);
~~~

This is a method snippet requiring imports for `java.util.TimeZone` and `java.time.ZoneId`.

**Important warning:** `TimeZone.getTimeZone("Bad/Zone")` can **silently fall back to GMT** if the ID is invalid. By contrast, `ZoneId.of("Bad/Zone")` throws an exception for an invalid ID. During migration, decide whether to catch errors to surface misconfigurations or preserve an intentional fallback. Do not write code assuming both APIs handle invalid IDs identically.

### 3.4. GregorianCalendar and 0-based months

In `Calendar`, `Calendar.JANUARY` has value `0`, and `Calendar.MARCH` has value `2`. In `java.time`, the month in `LocalDate.of(year, month, day)` takes **1–12**, and `Month.MARCH.getValue() == 3`.

~~~java
int oldMonthZeroBased = Calendar.MARCH; // 2
int newMonthOneBased = Month.MARCH.getValue(); // 3
~~~

This is a method snippet requiring imports for `java.util.Calendar` and `java.time.Month`. Never pass `calendar.get(Calendar.MONTH)` straight into the second parameter of `LocalDate.of` without `+1`, or better yet convert through the appropriate bridge APIs.

## 4. DateFormat/SimpleDateFormat → DateTimeFormatter: change the pattern, keep the meaning

### Common mappings

| Legacy API | java.time migration target | Notes |
| --- | --- | --- |
| `new SimpleDateFormat(pattern, locale)` | `DateTimeFormatter.ofPattern(patternNew, locale)` | Must **review pattern**, never copy blindly |
| `DateFormat.getDateInstance(style, locale)` | `DateTimeFormatter.ofLocalizedDate(formatStyle).withLocale(locale)` | The two API families may produce slightly different strings |
| `DateFormat.getTimeInstance(style, locale)` | `DateTimeFormatter.ofLocalizedTime(formatStyle).withLocale(locale)` | Check temporal type and zone |
| `DateFormat.getDateTimeInstance(dateStyle, timeStyle, locale)` | `DateTimeFormatter.ofLocalizedDateTime(dateStyleNew,timeStyleNew).withLocale(locale)` | Style mapping and CLDR need testing |
| `simple.setTimeZone(timeZone)` | `formatter.withZone(zoneId)` or convert `Instant.atZone(...)` | Right choice depends on input type |
| `simple.setLenient(false)` | `formatter.withResolverStyle(ResolverStyle.STRICT)` | **Not completely equivalent**, test parsing and pattern |
| `SimpleDateFormat.format(Date)` | `DateTimeFormatter.format(TemporalAccessor)` | Convert source to `Instant`/`LocalDate`/`ZonedDateTime` |
| `SimpleDateFormat.parse(text)` | `LocalDate.parse`, `ZonedDateTime.parse`, or `formatter.parse` | Pick a business-meaningful output type |

`DateFormat` uses levels like `SHORT`, `MEDIUM`, `LONG`, `FULL`; `java.time.format.FormatStyle` has matching names. However, they are not guaranteed to produce **character-for-character identical strings** across the two API families or providers.

If a product must preserve exact legacy strings due to an interface contract, pin the pattern and data policy; even better, separate **machine protocols** from **locale-based UI strings**.

## 5. Complete example: same Instant, Locale, and ZoneId across both APIs

Save `LegacyVsModernDemo.java`:

~~~java
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyVsModernDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2025-03-05T10:15:30Z");
        Locale locale = Locale.US;
        ZoneId zone = ZoneId.of("UTC");

        Date legacyValue = Date.from(instant);
        SimpleDateFormat oldFormatter =
                new SimpleDateFormat("dd MMMM yyyy HH:mm z", locale);
        oldFormatter.setTimeZone(TimeZone.getTimeZone(zone));

        DateTimeFormatter newFormatter = DateTimeFormatter
                .ofPattern("dd MMMM uuuu HH:mm z", locale)
                .withZone(zone);

        System.out.println("Old: "
                + oldFormatter.format(legacyValue));
        System.out.println("New: "
                + newFormatter.format(instant));
        System.out.println("Same instant: "
                + legacyValue.toInstant().equals(instant));
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac -encoding UTF-8 LegacyVsModernDemo.java
java LegacyVsModernDemo
~~~

Output on a JDK with common en-US month name data:

~~~text
Old: 05 March 2025 10:15 UTC
New: 05 March 2025 10:15 UTC
Same instant: true
~~~

**Why use `uuuu` instead of `yyyy` in the new formatter?** `java.time` distinguishes *proleptic year* (`u`) from *year-of-era* (`y`). For modern ISO dates in this example, both typically print `2025`. However, for strict parsing or BCE eras, the difference matters. Always review patterns before migrating.

**Why specify `withZone(UTC)`?** `Instant` is a point in time without a local timezone. To print `HH:mm` and a zone name, the formatter needs a zone. Omitting `withZone` while using a pattern requesting date/time fields from an `Instant` throws `UnsupportedTemporalTypeException`.

### Same Instant, changing zone changes displayed time

~~~java
Instant instant = Instant.parse("2025-03-05T10:15:30Z");

String vietnam = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .format(instant);
~~~

This is a method snippet requiring imports for `java.time.Instant`, `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, and `java.util.Locale`. `vietnam` evaluates to `"2025-03-05 17:15"` under Vietnam's time zone rules for that date. The point in time does not change; only the local view differs.

## 6. LocalizedDate/Time: adapt formatting by locale, not just copying patterns

Multilingual applications should normally let the locale decide day-month-year order and month spelling instead of enforcing one fixed pattern across every region.

In the legacy API:

~~~java
DateFormat old = DateFormat.getDateInstance(
        DateFormat.LONG, Locale.US
);
String text = old.format(new Date());
~~~

This is a method snippet requiring imports for `java.text.DateFormat`, `java.util.Locale`, and `java.util.Date`. Using `new Date()` here only illustrates syntax; **never** use it as expected test output because runtime changes.

In `java.time`, use a fixed date:

~~~java
LocalDate day = LocalDate.of(2025, 3, 5);

DateTimeFormatter usLong = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(Locale.US);

String shown = day.format(usLong);
~~~

This snippet requires imports for `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.FormatStyle`, and `java.util.Locale`. With common en-US locale data, `shown` is `"March 5, 2025"`.

### Complete example

Create `LocalizedStyleDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedStyleDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 3, 5);

        for (Locale locale : new Locale[] {
                Locale.US, Locale.GERMANY
        }) {
            DateTimeFormatter formatter = DateTimeFormatter
                    .ofLocalizedDate(FormatStyle.LONG)
                    .withLocale(locale);

            System.out.println(locale.toLanguageTag()
                    + ": " + date.format(formatter));
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 LocalizedStyleDemo.java
java LocalizedStyleDemo
~~~

Typical output:

~~~text
en-US: March 5, 2025
de-DE: 5. März 2025
~~~

In the example, `DateTimeFormatter` is **immutable**. Calling `withLocale` returns a formatter with the new locale configuration, **without** mutating the original formatter. Note that exact output (punctuation, capitalization, spacing) can differ from legacy `DateFormat` if JDK versions or locale/provider data differ.

## 7. Patterns requiring careful review: not every letter is equivalent

This is the common bug category when "copying a pattern verbatim" from `SimpleDateFormat` to `DateTimeFormatter`.

| Function | Legacy `SimpleDateFormat` | Modern `DateTimeFormatter` | What to watch out for |
| --- | --- | --- | --- |
| Year of era | `y` / `yyyy` | `y` / `yyyy` | Modern adds `u` for *proleptic year*; usually pick `uuuu` for strict ISO date parsing |
| ISO/proleptic year | Does not use `u` for year | `u` / `uuuu` | **`u` in SimpleDateFormat is day number of week** |
| Week-based year | `Y` | `Y` | Can differ from calendar year at year-end/start; do not use in place of `yyyy`/`uuuu` |
| Month | `M` / `MM` / `MMM` / `MMMM` | Similar | Text form also depends on locale |
| Stand-alone month name | `L` | `L` | Useful in calendar headers for inflected languages |
| Day of month | `d` | `d` | Generally same meaning |
| Day of year | `D` | `D` | Distinct from `d` |
| 24-hour hour | `H` | `H` | 0–23 |
| 12-hour hour | `h` | `h` | Usually paired with `a` (AM/PM) |
| Minute | `m` | `m` | `mm` is minute, `MM` is month |
| Second | `s` | `s` | Same role |
| Milli/fraction | `S` (milli-of-second) | `S` (*fraction-of-second*) | **Never blindly copy the width of S**; check precision |
| Text time zone | `z` | `z` | Display name depends on locale and provider |
| UTC offset | `Z`, `X` | `Z`, `X`, `x`, `O` | Formatting of zero/colons/offsets must be tested |
| Day of week | `E` | `E` | May depend on week numbering/locale |
| Quotes in pattern | `'...'` | `'...'` | Literals must be properly escaped for single quotes |

### 7.1. Critical trap: `u` means different things in the two APIs

In `SimpleDateFormat`, the `u` symbol is **day number of week (1–7)**, not year. In `DateTimeFormatter`, `u` is **proleptic year**. Therefore, a legacy pattern containing `u` cannot be moved verbatim to the modern API.

Conversely, converting `"yyyy-MM-dd"` to `"uuuu-MM-dd"` in java.time is often a good choice for ISO dates under strict parsing (to supply an explicit `YEAR` field). Still, test BCE years or special chronologies if your application handles them.

### 7.2. Trap of `Y` vs. `y`/`u`

`Y` is **week-based-year**, governed by locale week conventions; near the start/end of a year, it can differ from the calendar year. For ISO civil dates, use `uuuu-MM-dd` or a standard ISO formatter instead of `YYYY-MM-dd`.

### 7.3. Trap of `S`: milliseconds vs. fraction

`SimpleDateFormat` treats `S` as **milliseconds** with values 0–999, where the letter count controls numeric zero-padding. `DateTimeFormatter` treats `S` as **fraction of second**, where the letter count sets precision (up to 9 digits for nanoseconds). For instance, `SSS` normally expresses three-digit milliseconds in everyday cases, yet `S`/`SS` when parsing/formatting can behave differently from the legacy API. Never rewrite fractional-second patterns automatically via find-and-replace.

When storing timestamps for machine communication, prefer ISO-8601 or protocol-defined formatters rather than relying on default locale patterns.

### 7.4. `M` and `L` in languages with stand-alone month forms

When a month name appears inside a full date, use contextual `MMMM`; when printing a month name alone in a calendar header, `LLLL` can yield the grammatically appropriate form. For example, `ru-RU` with standard CLDR data uses `марта` inside a date, but `март` when the month stands alone. If a legacy pattern hardcoded a month form, review where it appears in the UI.

## 8. Parsing: migrating from DateFormat.parse to java.time without losing validation

Legacy code may look like:

~~~java
SimpleDateFormat parser =
        new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
parser.setLenient(false);
parser.setTimeZone(TimeZone.getTimeZone("UTC"));
Date parsed = parser.parse("2025-03-05");
~~~

This is a method snippet requiring `ParseException` handling and imports for `java.text.SimpleDateFormat`, `java.util.Locale`, `java.util.TimeZone`, and `java.util.Date`. A date without a time, when parsed to `Date`, must map to **a point in time**, so the parsing timezone matters.

If the data is inherently just a date, java.time expresses it more clearly:

~~~java
DateTimeFormatter parser = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate parsed = LocalDate.parse("2025-03-05", parser);
~~~

This snippet requires imports for `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle`, and `java.util.Locale`. `LocalDate` does not apply a timezone, because the input contains only a date.

### DateTimeFormatter ResolverStyle

- `ResolverStyle.STRICT`: strictly checks that fields resolve to a valid date/time.
- `ResolverStyle.SMART`: may adjust certain invalid date cases per API rules; this is the default for pattern-built formatters.
- `ResolverStyle.LENIENT`: permits flexible calculation, such as overflowing day/month numbers into other dates.

**`SimpleDateFormat.setLenient(false)` and `ResolverStyle.STRICT` are not a 1-to-1 equivalent replacement.** The modern parser also separates field parsing and field resolution stages; input rules can differ. Tests on real inputs are required.

### Why does strict mode commonly use `uuuu`?

In `java.time`, `yyyy` is **year-of-era**, and with only `yyyy-MM-dd` and no era, a strict-mode formatter cannot resolve to `LocalDate` as expected. `uuuu` supplies the proleptic year field directly for simple ISO dates.

### Java 17+ example validating valid and invalid dates

Save `StrictDateParseDemo.java`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class StrictDateParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        for (String input : new String[]{
                "2025-03-05", "2025-02-30"
        }) {
            try {
                LocalDate value = LocalDate.parse(input, strict);
                System.out.println(input + " => " + value);
            } catch (DateTimeParseException ex) {
                System.out.println(input + " => invalid");
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StrictDateParseDemo.java
java StrictDateParseDemo
~~~

Output:

~~~text
2025-03-05 => 2025-03-05
2025-02-30 => invalid
~~~

`LocalDate.parse` with this formatter checks the input against the pattern and resolves it; if you need to accept accents, Unicode characters, or special locale date notations, design the form's pattern/locale/validation accordingly. Do not use default `LocalDate.parse` to arbitrarily guess every date notation around the world.

### Checking trailing characters in the legacy API

`SimpleDateFormat.parse(String)` can accept a valid prefix and ignore trailing characters. If legacy code only checked "parse didn't throw an exception", malformed inputs may have slipped through. Treat migration as an opportunity to design explicit validation.

With a legacy parser, `ParsePosition` indicates how much was consumed:

~~~java
ParsePosition pos = new ParsePosition(0);
Date value = parser.parse(input, pos);

if (value == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Invalid date input");
}
~~~

This is a method snippet requiring `parser` as a `SimpleDateFormat` and `input` as the string to parse, plus imports for `java.text.ParsePosition` and `java.util.Date`. This check does **not** replace calendar, timezone, or business-rule validation.

## 9. DST: do not attach a timezone to LocalDateTime assuming the instant is always unique

This is a major risk when moving from `Calendar`/`Date` to `java.time`.

For example, in regions with daylight saving time (DST), a local hour can:

- **Not exist** when clocks spring forward (*gap*).
- **Occur twice** when clocks fall back (*overlap*).

`LocalDateTime.of(...)` only describes a wall-clock date and time; on its own, it does not guarantee a unique instant. When attaching a `ZoneId` to create a `ZonedDateTime`, Java must apply DST rules and make a default choice for gaps/overlaps.

If the system stores events as absolute timestamps, use `Instant`. If the system stores appointments like "9 AM local time in Berlin", you may need to store `LocalDateTime`, `ZoneId`, and a well-defined DST policy.

### Converting Instant to local time

~~~java
Instant instant = Instant.parse("2025-03-05T10:15:30Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime viewed = instant.atZone(zone);
LocalDate localDate = viewed.toLocalDate();
LocalTime localTime = viewed.toLocalTime();
~~~

This is a method snippet requiring imports for `java.time.Instant`, `java.time.ZoneId`, `java.time.ZonedDateTime`, `java.time.LocalDate`, and `java.time.LocalTime`.

Converting an `Instant` to local time is deterministic; converting an arbitrary `LocalDateTime` to an `Instant` may require explicit gap/overlap handling if the application demands high accuracy.

**Never accidentally use `ZoneId.systemDefault()` in multi-user server code** when the transaction/user's zone is known. The server's default configuration is an environment choice, not necessarily the data's true timezone.

## 10. Default locale and language-specific formatting

`SimpleDateFormat` and `DateFormat` have constructors/factories that use the JVM's default locale when none is passed explicitly. In `java.time`, pass the `Locale` from the recipient's context.

~~~java
Locale viewer = Locale.forLanguageTag("vi-VN");
DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.LONG)
        .withLocale(viewer);
~~~

This is a method snippet requiring imports for `java.util.Locale`, `java.time.format.DateTimeFormatter`, and `java.time.format.FormatStyle`.

Benefits of passing locale explicitly:

1. One server concurrently serves Vietnamese, German, and US users without calling `Locale.setDefault` per request.
2. Unit tests depend less on the developer machine's or CI's locale.
3. Each formatter renders the viewer's conventions accurately.
4. Locale and zone are managed **separately**.

**Note:** `java.time`'s `DateTimeFormatter` does not derive every rule from `Locale`. If the string displays an `Instant`, you still must provide a zone. If the application supports non-ISO calendars, consider `Chronology`, Unicode locale extensions, and formatter support. Changing locale alone does not automatically change chronology, timezone, or currency.

### Cases with context-sensitive month spellings

In some languages, months have contextual and stand-alone forms. The `MMMM` pattern gives the contextual month; `LLLL` gives the stand-alone form, such as month headers on a calendar. When migrating code with localized month names, do not check only English results; test `ru-RU` or `pl-PL` if your product supports them.

## 11. Thread safety, state, and performance

### Legacy SimpleDateFormat

`SimpleDateFormat` can mutate its pattern, timezone, calendar, and leniency. It is **not internally synchronized for safe shared use**. Using a single static instance across all requests is a source of data races and sometimes hard-to-reproduce bugs.

~~~java
// Unsafe if multiple threads concurrently use/modify this instance.
private static final SimpleDateFormat SHARED =
        new SimpleDateFormat("yyyy-MM-dd", Locale.US);
~~~

This is a class-field declaration snippet requiring imports for `java.text.SimpleDateFormat` and `java.util.Locale`.

### Modern DateTimeFormatter

`DateTimeFormatter` is **immutable and thread-safe**. It can be pre-created and reused when the locale/zone/pattern **match the same purpose**:

~~~java
private static final DateTimeFormatter ISO_DAY =
        DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
~~~

This is a class-field declaration snippet requiring imports for `java.time.format.DateTimeFormatter`, `java.time.format.ResolverStyle`, and `java.util.Locale`.

**Point to keep distinct:** `withLocale`, `withZone`, `withChronology`, and `withDecimalStyle` return a newly configured formatter without mutating the original instance. However, caching formatters per user can increase object counts if designed without bounds; only cache combinations actually used.

Types like `LocalDate`, `Instant`, and `ZonedDateTime` are also immutable, convenient for multithreaded code.

## 12. Differences that easily break tests or business logic

| Scenario | Migration mistake | Right approach |
| --- | --- | --- |
| `Date` holding an instant | Replacing with `LocalDateTime` without a zone | Convert via `Date.toInstant()`, then apply a zone if needed |
| Legacy code using server timezone | Running in another environment shifts date/time | Specify `ZoneId` from the request/application |
| Legacy pattern with `u` | Copying to java.time thinking it is still day of week | Review every pattern letter, especially `u` |
| Legacy pattern with `YYYY` | Treating as calendar year | Distinguish week-based-year from `uuuu` |
| Legacy pattern with `S` | Copying `S` count without checking precision | Check millisecond vs. fraction difference |
| Legacy lenient parser | Switching API without testing abnormal inputs | Choose `ResolverStyle` and test real cases |
| Pattern `yyyy` with STRICT parsing | Fails to resolve `LocalDate` due to missing era | Consider `uuuu-MM-dd` with ISO chronology |
| Formatting localized dates with a fixed pattern | Ignoring the locale's day/month order | Use `ofLocalizedDate`/`ofLocalizedDateTime` |
| Right locale, wrong hour | Forgetting timezone | Manage locale and zone independently |
| `Calendar.MONTH` | Keeping 0-based months in `LocalDate.of` | Convert to 1–12 months |
| Inflected month names | Using `MMMM` for stand-alone month labels | Use `LLLL` when context calls for it |
| Sharing `SimpleDateFormat` across threads | Random corrupted outputs | Replace with `DateTimeFormatter` or isolate the legacy formatter |
| Comparing exact output across different JDKs | Tests break due to CLDR/provider differences | Pin environment or assert semantics |
| UI strings used as API data | Parsing errors across locales | Use ISO-8601 / machine data types |
| Shifting dates/times while ignoring DST rules | Appointments drift off target instant | Define policies for gaps/overlaps |

## 13. Date-time types in data, databases, and JSON

When migrating, do not fix only the display layer. Audit **input/output data contracts**:

- **Dates without time**: use `LocalDate`, represented as ISO `2025-03-05` in machine exchange.
- **Absolute instants**: use `Instant` with ISO-8601 such as `2025-03-05T10:15:30Z`.
- **Date-times with offset**: use `OffsetDateTime` if the offset is part of the data.
- **Events tied to a DST region**: use `ZonedDateTime` or store `Instant` + `ZoneId` depending on business rules.
- **Dates in UI text**: format at render time with explicit locale and zone; never use UI strings as data-transfer keys.

### JDBC and java.sql types

In legacy systems, you may encounter `java.sql.Date` or `java.sql.Timestamp`:

~~~java
java.sql.Date legacySqlDate =
        java.sql.Date.valueOf("2025-03-05");
LocalDate date = legacySqlDate.toLocalDate();

java.sql.Timestamp legacyTimestamp =
        java.sql.Timestamp.from(
                Instant.parse("2025-03-05T10:15:30Z")
        );
Instant instant = legacyTimestamp.toInstant();
~~~

This is a method snippet requiring imports for `java.time.LocalDate` and `java.time.Instant`.

**Note:** `java.sql.Date` represents SQL's date concept and should not be treated like a UTC timestamp. In JDBC/ORM, mapping for `DATE`/`TIME`/`TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` varies by driver and database. Never assume every `TIMESTAMP` column carries a timezone or can be converted to `Instant` without rules. Check actual mapping and schema before migrating.

For JSON, configuring the library to serialize/deserialize `java.time` may require a module/adapter depending on the library. Never assume UI `DateTimeFormatter` dictates how all JSON is produced; UI formatters and serializers are two separate layers.

## 14. Step-by-step migration plan

A safe roadmap:

1. **Inventory:** locate all uses of `Date`, `Calendar`, `DateFormat`, `SimpleDateFormat`, and `TimeZone`; determine whether they handle business data or only presentation.
2. **Classify types:** instant, date, time, month/year, or zoned appointment. Choose `Instant`/`LocalDate`/`ZonedDateTime`... matching semantics.
3. **Identify locale/zone:** read from profile, request, data contract, or official configuration; avoid implicit JVM reliance.
4. **Review patterns:** check `u`, `y`, `Y`, `S`, `M`/`L`, `X`/`Z`, and quoted literals; never copy blindly.
5. **Separate parsers from formatters:** define user display formatting and input parsing separately, with explicit strictness.
6. **Side-by-side testing:** same input, same locale, same zone; verify semantics first, then strings that must match exactly.
7. **Boundary date testing:** year-end, leap years, invalid dates like Feb 30, DST transitions, zone offsets, and BCE dates if applicable.
8. **Unicode/CLDR testing:** month names, AM/PM, separators, and spelling across supported locales.
9. **Migrate layer by layer:** build bridges at legacy API boundaries, migrate domain models and services, and finally remove legacy formatters.
10. **Monitor and clean up:** avoid keeping two formatting mechanisms with different defaults long-term; document intentional differences in tests and docs.

### Proper boundary while the system cannot switch all at once

~~~text
Legacy API / Database
        |
        v
Convert at the boundary
Date -> Instant
Calendar -> ZonedDateTime
java.sql.Date -> LocalDate
        |
        v
Domain and services use java.time
        |
        +------> Formatter for UI
        |        Explicit Locale + ZoneId
        |
        +------> Serializer for API
                 ISO-8601 / defined schema
~~~

Do not mix `Date` and `LocalDateTime` indiscriminately inside the domain when the two variables carry different meanings without clear documentation. The goal is **a consistent temporal model**, not merely renaming classes.

## 15. Hands-on exercises

1. Create a `Date` from `Instant.parse("2025-03-05T10:15:30Z")`, then format it with `SimpleDateFormat` and `DateTimeFormatter` in UTC with `Locale.US`. Compare outputs and explain why `withZone` is required.
2. Replace `DateFormat.getDateInstance(DateFormat.LONG, Locale.US)` with an appropriate `java.time` formatter and test it on `LocalDate.of(2025,3,5)`.
3. Convert a `GregorianCalendar` in `Asia/Ho_Chi_Minh` to `ZonedDateTime`, comparing `toInstant()` and local time.
4. Write two formatters for `Locale.US` and `Locale.GERMANY` on the same date. Why is calling `Locale.setDefault` unnecessary?
5. Explain why the pattern `"uuuu-MM-dd"` in `DateTimeFormatter` does not mean the same thing as `"uuuu-MM-dd"` in `SimpleDateFormat`.
6. Parse `2025-02-30` with `ResolverStyle.STRICT` and `ResolverStyle.SMART`. Inspect the results to see why migration can alter input validation behavior.
7. An application passes `Calendar.MONTH` into `LocalDate.of`. Identify the off-by-one bug when converting March.
8. In a Russian calendar, test `"d MMMM uuuu"` and `"LLLL uuuu"`. Which is used for a full date, and which for a month header?
9. A system receives appointment times in `Europe/Berlin` near a DST transition. Identify what data must be stored to avoid ambiguity and test both repeated and nonexistent hours.
10. If a locale-based date string test fails after a JDK upgrade, distinguish CLDR/provider updates from semantic data changes.
11. Convert a SQL DATE column to `LocalDate` and an event timestamp column to `Instant`; explain why the two conversions should not use the same timezone approach.

**Key takeaway:** Migrating from `Date`/`Calendar`/`SimpleDateFormat` to `java.time` changes **both the temporal model and formatting**, not just API names. Keep **Instant/LocalDate/ZonedDateTime**, **Locale**, and **ZoneId** separate; review `u/y/Y/S/M/L` patterns; validate input with the appropriate `ResolverStyle`; prefer immutable `DateTimeFormatter` over mutable `SimpleDateFormat`. Test with fixed data, boundary dates, real locales, and timezones/DST to prevent unintended behavior changes.

### References

- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — patterns, localized styles, locale, zone, and immutability.
- [Java SE 17 — ResolverStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html) — STRICT, SMART, and LENIENT when parsing.
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) — absolute instants and conversion from `Date`.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html) — zones and DST rules.
- [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html) — legacy API, patterns, and thread safety.
- [Java SE 17 — GregorianCalendar](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/GregorianCalendar.html) — converting to `ZonedDateTime`.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html) — dates without time or timezone.
