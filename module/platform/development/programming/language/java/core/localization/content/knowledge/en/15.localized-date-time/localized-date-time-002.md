# ofLocalizedDate, ofLocalizedTime, and ofLocalizedDateTime

When displaying dates, times, or combined date-times to users across multiple countries, Java provides three key factories on `java.time.format.DateTimeFormatter`:

- `DateTimeFormatter.ofLocalizedDate(FormatStyle)` — creates a formatter that **displays only the date** according to the locale.
- `DateTimeFormatter.ofLocalizedTime(FormatStyle)` — creates a formatter that **displays only the time** according to the locale.
- `DateTimeFormatter.ofLocalizedDateTime(FormatStyle)` and `ofLocalizedDateTime(FormatStyle, FormatStyle)` — creates a formatter that **displays both date and time**.

These factories use **localized format patterns** known to the JDK/locale provider, rather than forcing developers to write a fixed pattern string such as `"dd/MM/yyyy"` for everyone. They are typically combined with `withLocale(locale)` to specify the language and display conventions.

However, **a locale is not a time zone**. The choice of style and the value type—`LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, or `Instant`—determines whether the formatter has enough data to run. In particular, some `LONG` and `FULL` styles include a time-zone name or offset in the time portion, so they cannot always format a `LocalTime` or `LocalDateTime` that lacks a time zone.

## 1. Overview of the APIs

| Factory | What is displayed | Example suitable objects | Things to watch out for |
| --- | --- | --- | --- |
| `ofLocalizedDate(style)` | Day, month, year; possibly day of week | `LocalDate` | Relies only on date fields; does not require time |
| `ofLocalizedTime(style)` | Hour, minute, possibly second and time zone | `LocalTime` for some styles; `ZonedDateTime` for styles needing a zone | `LONG`/`FULL` often require zone information |
| `ofLocalizedDateTime(style)` | Date and time with the same level of detail | `LocalDateTime` with `SHORT`/`MEDIUM`; `ZonedDateTime` with styles needing a zone | Can fail if date/time/zone fields are missing |
| `ofLocalizedDateTime(dateStyle, timeStyle)` | Date and time with two independent styles | Appropriate `LocalDateTime` or `ZonedDateTime` | For example, `LONG` date and `SHORT` time |

These calls return an **immutable** and **thread-safe** `DateTimeFormatter`. The factory itself does not format immediately; it creates a formatter object, and the application calls `formatter.format(temporal)` or `temporal.format(formatter)` when needed.

Common imports:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.LocalDateTime;
import java.time.ZonedDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;
~~~

All three factories belong to the **Java Time API** (`java.time`), not `java.text.DateFormat` or `SimpleDateFormat` from the legacy date-time API.

## 2. What Is `FormatStyle`?

`FormatStyle` has four values:

| Style | Presentation goal | Typical characteristics |
| --- | --- | --- |
| `FULL` | Full human-readable form | Date may include weekday; time may include time-zone name |
| `LONG` | Long, though not necessarily as complete as FULL | Month may be spelled out; time may include time zone |
| `MEDIUM` | Medium length | May include spelled-out/abbreviated month and seconds, depending on locale |
| `SHORT` | Compact | Usually numeric for day/month/year; time may omit seconds |

**These are not four fixed pattern strings.** `FormatStyle.SHORT` is a **request for a presentation level**, while the JDK chooses the concrete pattern based on the locale/provider and data type. For instance, the same `SHORT` can produce `5/6/24` in `en-US` and `06.05.24` in `de-DE`.

Do not assume that:
- `SHORT` = guaranteed `dd/MM/yy`;
- `MEDIUM` = guaranteed to include seconds;
- `LONG` = guaranteed full month name in every locale;
- `FULL` = always able to format any `LocalDateTime`.

Those are only common cases in specific locale data, not an invariant output string contract across all JDKs.

## 3. `ofLocalizedDate`: Displaying Dates by Locale

Suppose an application has a pure calendar date: `LocalDate.of(2024, 5, 6)`. It represents **May 6, 2024**; it contains neither a time nor a time zone.

Create the file **`LocalizedDateDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedDateDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 5, 6);

        DateTimeFormatter usShort =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(Locale.US);

        DateTimeFormatter deShort =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(Locale.GERMANY);

        System.out.println(usShort.getLocale().toLanguageTag());
        System.out.println(deShort.getLocale().toLanguageTag());
        System.out.println(usShort.format(date));
        System.out.println(deShort.format(date));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac LocalizedDateDemo.java
java LocalizedDateDemo
~~~

Example output with common JDK/locale data:

~~~text
en-US
de-DE
5/6/24
06.05.24
~~~

The first two lines (`en-US`, `de-DE`) reflect the **explicitly** set locale. The next two lines show the **same `LocalDate`** displayed under two different date conventions. No time-zone conversion happens here: the data is a pure calendar date.

With `FormatStyle.FULL`, the formatter can include the day-of-week name. For example, US English for the date above is typically "Monday, May 6, 2024". You should not test all locales by looking for the hardcoded string "Monday"; day names are localized.

### When to use it?

- Birthdays, release dates, calendar deadlines.
- Registration dates or event dates stored as `LocalDate`.
- Dates that do not carry a specific instant on the timeline.

If the underlying data is actually **a timestamp**, you must decide the time zone before extracting the date to display to the user; changing only the locale cannot determine the calendar date where that person lives.

## 4. `ofLocalizedTime`: Displaying Times by Locale

`LocalTime` represents a time of day **without a date and without a time zone**, such as `15:04:05`. When using styles that do not require a zone, it can be formatted directly.

Create **`LocalizedTimeDemo.java`**:

~~~java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedTimeDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(15, 4, 5);

        DateTimeFormatter shortTime =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
                        .withLocale(Locale.US);

        DateTimeFormatter mediumTime =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.MEDIUM)
                        .withLocale(Locale.US);

        System.out.println(shortTime.getLocale().toLanguageTag());
        System.out.println(time.equals(LocalTime.of(15, 4, 5)));
        System.out.println(shortTime.format(time));
        System.out.println(mediumTime.format(time));
    }
}
~~~

~~~bash
javac LocalizedTimeDemo.java
java LocalizedTimeDemo
~~~

Example output with common US English locale data:

~~~text
en-US
true
3:04 PM
3:04:05 PM
~~~

In the two time lines, the whitespace character before "PM" **may be a non-breaking Unicode space**, not necessarily a regular ASCII space. AM/PM labels, separators, whether seconds appear, and 12/24-hour representation are all influenced by the locale/provider.

`SHORT` is not required to include seconds. For `LocalTime.of(15, 4, 5)`, `SHORT` in some locales omits `:05`, while `MEDIUM` typically retains the seconds.

### Common pitfall: LONG/FULL and time zones

`LONG` and `FULL` time formats **usually require time-zone information**, such as a zone name or offset. `LocalTime` does not carry that information, so:

~~~java
DateTimeFormatter f =
        DateTimeFormatter.ofLocalizedTime(FormatStyle.FULL)
                .withLocale(Locale.US);

String text = f.format(LocalTime.of(15, 4, 5));
~~~

This is an **error-demonstrating snippet**, requiring appropriate imports. On a JDK whose FULL pattern includes a zone field for `Locale.US`, the final call throws `DateTimeException` because the temporal does not provide the required data. Do not interpret this error as "the US locale does not support FULL": the issue is that **the data type has no time zone**.

The proper fix is to provide a `ZonedDateTime` (or a temporal with an appropriate zone/offset), or intentionally choose a style that does not require a zone.

## 5. `ofLocalizedDateTime`: Combining Date and Time by Locale

`LocalDateTime` contains both date and time but **still contains no time zone**. Thus, for common styles like `SHORT` or `MEDIUM`, it can supply the required data. For time styles that require a zone, it may not be sufficient.

Create **`LocalizedDateTimeDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedDateTimeDemo {
    public static void main(String[] args) {
        LocalDateTime dateTime =
                LocalDateTime.of(2024, 5, 6, 15, 4, 5);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(Locale.US);

        System.out.println(formatter.getLocale().toLanguageTag());
        System.out.println(formatter.format(dateTime));
    }
}
~~~

~~~bash
javac LocalizedDateTimeDemo.java
java LocalizedDateTimeDemo
~~~

Example output on a JDK using common localized patterns:

~~~text
en-US
5/6/24, 3:04 PM
~~~

`ofLocalizedDateTime(FormatStyle.SHORT)` selects a combination of short date style and short time style for the locale. It is not necessarily a hardcoded concatenation `ofLocalizedDate(SHORT) + " " + ofLocalizedTime(SHORT)`: the connector, punctuation, and component order are determined by the locale's formatting data.

### `DateTimeFormatter` Variants Do Not Invent Missing Fields

- `ofLocalizedDate(SHORT)` needs only date fields, so `LocalDate` is sufficient.
- `ofLocalizedTime(SHORT)` typically needs hour/minute, so `LocalTime` is sufficient.
- `ofLocalizedDateTime(SHORT)` needs both date and time fields, so `LocalDate` alone or `LocalTime` alone **is not sufficient**.
- With `LONG`/`FULL` including a time-zone name/offset, a `LocalDateTime` without a zone can fail.

The formatter does not invent the current date when you pass a `LocalTime` to a date-time formatter, and it does not invent a default time zone for every temporal lacking a zone.

## 6. Two-Style Overload: Long Date, Short Time

`ofLocalizedDateTime` has **two important overloads**:

~~~java
DateTimeFormatter a =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT);

DateTimeFormatter b =
        DateTimeFormatter.ofLocalizedDateTime(
                FormatStyle.LONG, FormatStyle.SHORT);
~~~

This snippet requires importing `DateTimeFormatter` and `FormatStyle`. With the second overload:

- The **first** parameter `FormatStyle.LONG` is the **date** style.
- The **second** parameter `FormatStyle.SHORT` is the **time** style.
- The final combined pattern still follows the locale; it is not a manual concatenation of two strings.

Runnable example **`MixedStylesDemo.java`**:

~~~java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class MixedStylesDemo {
    public static void main(String[] args) {
        LocalDateTime value =
                LocalDateTime.of(2024, 5, 6, 15, 4, 5);

        DateTimeFormatter fmt =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.LONG, FormatStyle.SHORT)
                        .withLocale(Locale.US);

        System.out.println(fmt.getLocale().toLanguageTag());
        System.out.println(fmt.format(value));
    }
}
~~~

~~~bash
javac MixedStylesDemo.java
java MixedStylesDemo
~~~

Example output under common US locale patterns:

~~~text
en-US
May 6, 2024, 3:04 PM
~~~

Note that `LONG` here applies to the **date part**, while `SHORT` applies to the time part; in common US locale data, the time part does not require a zone name. Do not assume that seeing `LONG` always requires a `ZonedDateTime`: whether a zone is required depends on **the style of the time part and the resulting pattern**.

When you need different levels of detail for the two components, this overload is clearer and easier to maintain than building a combined date-time pattern manually.

## 7. Choosing the Right Time Data Type

Several classes in `java.time` have distinct meanings:

| Temporal type | Has date? | Has time? | Has zone/offset? | When to use |
| --- | --- | --- | --- | --- |
| `LocalDate` | Yes | No | No | Pure calendar date |
| `LocalTime` | No | Yes | No | Time of day without location |
| `LocalDateTime` | Yes | Yes | No | Local date-time without a zone |
| `OffsetDateTime` | Yes | Yes | Has offset | Date-time with a UTC offset |
| `ZonedDateTime` | Yes | Yes | Has `ZoneId` and offset | Time tied to a time-zone region |
| `Instant` | Instant on UTC timeline | Instant on UTC timeline | Does not carry local date/time fields directly | Absolute timestamp |

The "date/time" columns for `Instant` should be understood as **date and time can be derived once a zone is known**, rather than `Instant` directly providing calendar fields to every localized formatter.

A system handling real-world instants should determine:
1. What the source timestamp is (usually `Instant`).
2. What the display time zone is (`ZoneId`).
3. What the reader's locale is (`Locale`).
4. What the desired style is (`FormatStyle`).

Only then should it create the formatter and format the value.

**Classic example:** two viewers looking at the same event occurring at `Instant.parse("2024-05-06T23:00:00Z")` may see **two different calendar dates** because their zones differ. However, if they only differ in locale while sharing the same zone, the calendar date will be the same and only the presentation changes.

## 8. LONG/FULL for the Time Part: Use `ZonedDateTime` When Needed

Create **`ZonedLocalizedDemo.java`**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class ZonedLocalizedDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime value = ZonedDateTime.of(
                2024, 5, 6, 15, 4, 5, 0, zone);

        DateTimeFormatter time =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.FULL)
                        .withLocale(Locale.US);

        DateTimeFormatter dateTime =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.LONG)
                        .withLocale(Locale.US);

        System.out.println(value.getZone().getId());
        System.out.println(time.getLocale().toLanguageTag());
        System.out.println(time.format(value));
        System.out.println(dateTime.format(value));
    }
}
~~~

~~~bash
javac ZonedLocalizedDemo.java
java ZonedLocalizedDemo
~~~

The first two lines are **stable per the explicit code**:

~~~text
Asia/Ho_Chi_Minh
en-US
~~~

The last two lines contain the time and may include the time-zone name according to the JDK's data. For instance, US English `FULL` may display a name equivalent to "Indochina Time", while `LONG` may display an offset such as `GMT+07:00`. **Do not hardcode an exact stdout for these two localized lines**, because zone names and whitespace can change across runtime/CLDR versions.

### Why might `LocalDateTime` not be enough?

`LocalDateTime.of(2024, 5, 6, 15, 4)` **does not know** whether that time is in Hanoi, Tokyo, Berlin, or New York. A zone name cannot be inferred from date and time fields.

Therefore, for a `FULL` format that includes a zone name, the JDK can fail with `DateTimeException` due to missing data, instead of silently picking `ZoneId.systemDefault()`. The application must attach the domain-appropriate zone.

If you are working with an `Instant`, you can convert it to a `ZonedDateTime` using `instant.atZone(zone)` before formatting, or attach a zone to the formatter via `withZone(zone)` when supported by the temporal and format style.

## 9. `Locale` Differs from `ZoneId`

**Locale:** determines presentation for the reader, such as day/month order, spelling of month names, 12/24-hour clock style, and which language is used for time-zone names.

**ZoneId:** determines how a UTC instant converts to local time, including historical offset changes and daylight saving time where applicable.

| Configuration | Effect | What it does NOT do |
| --- | --- | --- |
| `withLocale(Locale.US)` | Uses US English localization conventions | Does not convert `Instant` to US time |
| `withLocale(Locale.GERMANY)` | Uses German display patterns/language | Does not select the Berlin time zone |
| `withZone(ZoneId.of("Asia/Tokyo"))` | Attaches a zone override for formatting/parsing when appropriate | Does not switch the language to Japanese |
| `Locale.forLanguageTag("vi-VN")` | Represents Vietnamese in the Vietnam context | Not synonymous with `ZoneId.of("Asia/Ho_Chi_Minh")` |

Combining `Locale.US` with `ZoneId.of("Asia/Ho_Chi_Minh")` is **completely valid**: for example, a system showing time in Vietnam to a user reading US English.

Never infer a zone by concatenating a country code into an ID. A single country can span multiple time zones, observe daylight saving time, or have distinct historical rules. Store and select `ZoneId` explicitly.

## 10. Example: Formatting an `Instant` with Separate Zone and Locale

Create **`InstantPresentationDemo.java`**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class InstantPresentationDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2024-05-06T08:04:05Z");

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(Locale.US)
                        .withZone(zone);

        System.out.println(formatter.getLocale().toLanguageTag());
        System.out.println(formatter.getZone().getId());
        System.out.println(event.atZone(zone).getHour());
        System.out.println(formatter.format(event));
    }
}
~~~

~~~bash
javac InstantPresentationDemo.java
java InstantPresentationDemo
~~~

The first three lines have deterministic output:

~~~text
en-US
Asia/Ho_Chi_Minh
15
~~~

The last line is the `SHORT` date-time string according to US locale data (typically equivalent to `5/6/24, 3:04 PM`, though the space before AM/PM may vary). The **hour 15** comes from converting the UTC instant into `Asia/Ho_Chi_Minh`, not from `Locale.US`.

`withZone` returns a **new formatter** without mutating the original formatter. `withLocale` also returns a new formatter. This allows clean chained configuration without modifying shared state:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .withLocale(userLocale)
                .withZone(userZone);
~~~

This is a **snippet**: `userLocale` and `userZone` must be validated/declared from the user context, not pre-existing JDK variables.

## 11. `withLocale` and Defaults at Formatter Creation Time

If you do not call `withLocale(...)`, the localized factory captures the environment's default formatting locale at creation time. For multi-user services, this dependency is error-prone:

~~~java
DateTimeFormatter shared =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT);
~~~

If `shared` is created when the default is `en-US`, it does not automatically become a `vi-VN` formatter when another request needs Vietnamese. `DateTimeFormatter` is immutable; it already captured its locale configuration at creation time.

Cleaner design:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(requestLocale);
~~~

The locale choice should come from the user, product configuration, or fallback rules. Do not call `Locale.setDefault(...)` per request: that is JVM-wide shared state and can cause bugs when multiple threads run concurrently.

### Example checking the attached locale without relying on text output

Create **`FormatterLocaleDemo.java`**:

~~~java
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class FormatterLocaleDemo {
    public static void main(String[] args) {
        DateTimeFormatter original =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(Locale.US);
        DateTimeFormatter german =
                original.withLocale(Locale.GERMANY);

        System.out.println(original.getLocale().toLanguageTag());
        System.out.println(german.getLocale().toLanguageTag());
        System.out.println(original == german);
    }
}
~~~

~~~bash
javac FormatterLocaleDemo.java
java FormatterLocaleDemo
~~~

Exact output:

~~~text
en-US
de-DE
false
~~~

`withLocale` returns a newly configured formatter without mutating `original`. Therefore, you can cache immutable formatters by locale/style/zone if the system truly needs performance optimization.

## 12. How to Parse Localized Dates and Times

`DateTimeFormatter` can also work in reverse: pass a **string matching the corresponding format** to `LocalDate.parse(...)`, `LocalTime.parse(...)`, or `LocalDateTime.parse(...)`.

For parsing to be reliable, you must use **the same locale, style, and compatible data type**. For example, using `SHORT` with `Locale.US`, German-style input can be misinterpreted or throw an error; the application should not guess a format from a string of unknown origin.

Create **`LocalizedParsingDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedParsingDemo {
    public static void main(String[] args) {
        Locale locale = Locale.US;

        LocalDate date = LocalDate.of(2024, 5, 6);
        LocalTime time = LocalTime.of(15, 4, 5);
        LocalDateTime dateTime =
                LocalDateTime.of(2024, 5, 6, 15, 4);

        DateTimeFormatter dateFmt =
                DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                        .withLocale(locale);
        DateTimeFormatter timeFmt =
                DateTimeFormatter.ofLocalizedTime(FormatStyle.MEDIUM)
                        .withLocale(locale);
        DateTimeFormatter dateTimeFmt =
                DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                        .withLocale(locale);

        LocalDate parsedDate =
                LocalDate.parse(dateFmt.format(date), dateFmt);
        LocalTime parsedTime =
                LocalTime.parse(timeFmt.format(time), timeFmt);
        LocalDateTime parsedDateTime =
                LocalDateTime.parse(
                        dateTimeFmt.format(dateTime), dateTimeFmt);

        System.out.println(date.equals(parsedDate));
        System.out.println(time.equals(parsedTime));
        System.out.println(dateTime.equals(parsedDateTime));
    }
}
~~~

~~~bash
javac LocalizedParsingDemo.java
java LocalizedParsingDemo
~~~

Output on common US locale patterns:

~~~text
true
true
true
~~~

Here:
- `dateFmt` preserves all date components.
- `timeFmt` uses `MEDIUM` to retain seconds for `15:04:05`.
- `dateTimeFmt` uses `SHORT`, and the source data has seconds = 0 so no information is lost in representation.

**Not every format -> parse sequence is a lossless round-trip.** If a style omits seconds/nanoseconds or time zone, that information is dropped from the string. For instance, formatting `LocalTime.of(15,4,5)` with `SHORT` may omit `:05`, so parsing it back cannot recover the exact time down to the second.

### Parse errors to handle

`DateTimeParseException` can occur when the string does not match the pattern/style/locale, or when date data is invalid under the resolver rules. For user input, catch the exception and report a clear message instead of letting the exception bubble up to the UI.

Do not detect locale just by looking at separator characters like `/` or `.`. Many regions share similar separators while assigning opposite meanings to day/month order. If users enter dates manually, publish a fixed input format or use a structured date picker, and use localized formatters only for **display**.

## 13. Comparing Localized Formatters with Custom Patterns

Two ways to create a formatter:

~~~java
DateTimeFormatter localized =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.SHORT)
                .withLocale(Locale.US);

DateTimeFormatter explicit =
        DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.US);
~~~

This snippet requires importing `DateTimeFormatter`, `FormatStyle`, and `Locale`.

- `localized` requests a pattern matching the US locale's `SHORT` level: it may place month before day and use a two-digit year.
- `explicit` forces the day/month/year order and field widths specified in `dd/MM/uuuu`, even though the US locale does not normally use that order.

`ofPattern` is suitable when **business specifications require a specific layout**, such as a standardized form. `ofLocalizedDate` is suitable when the goal is **following the user's/locale's conventions**.

### Do not use localized formatters as machine communication standards

For APIs, machine logs, integration CSVs, or stable data formats, use ISO formatters or an explicit schema:

~~~java
String iso = LocalDate.of(2024, 5, 6).toString();
System.out.println(iso);
~~~

Output:

~~~text
2024-05-06
~~~

`LocalDate.toString()` uses ISO-8601 and does not change just because a user has a different locale. Localized formats are meant for reports, notifications, or human-facing documents.

## 14. Locale Providers, Pattern Data, and Output Stability

The `ofLocalized...` methods rely on locale data supplied by the runtime/provider. Month names, weekdays, AM/PM formats, whitespace, date-time layout, and time-zone names can change depending on:

- The JDK/CLDR version or locale service provider.
- The specific locale and any relevant Unicode locale extensions.
- Attached formatter settings (zone, chronology, decimal style where applicable).
- Runtime time-zone data when converting instants.

Therefore, snapshot tests comparing localized strings character-for-character across all environments can be brittle. For example:
- Regular space `U+0020`,
- non-breaking space `U+00A0`,
- narrow no-break space `U+202F`,

look nearly identical visually yet have different Unicode code points. The space before "PM" is a common example.

If a product requires strictly stable output, pin the deployment/JDK/provider environment in tests, or use custom patterns/data schemas where appropriate. If the goal is culturally appropriate display, do not hardcode characters just because one current JDK version produces that exact string.

**Note:** `getLocale()` tells you which locale the formatter uses; it does not guarantee that all locale data was eagerly copied into the object at construction time. The runtime may cache or look up details by implementation, but a formatter with an assigned locale does not follow new default-locale changes on every format call.

## 15. When to Use Each Factory?

Several scenarios:

| Requirement | Suggested factory | Suitable temporal |
| --- | --- | --- |
| "Due: 6/5" in the reader's locale | `ofLocalizedDate(SHORT)` | `LocalDate` |
| "Date of birth" in full form | `ofLocalizedDate(FULL)` | `LocalDate` |
| "Opening time: 15:30" by locale | `ofLocalizedTime(SHORT)` | `LocalTime` |
| "Starts at 15:04:05" needing seconds | `ofLocalizedTime(MEDIUM)` (verify per locale) | `LocalTime` |
| Appointment with short date and time | `ofLocalizedDateTime(SHORT)` | `LocalDateTime` or `ZonedDateTime` |
| Report with long date, short time | `ofLocalizedDateTime(LONG, SHORT)` | `LocalDateTime` |
| Event with date/time and time-zone name | `ofLocalizedDateTime(FULL)` | `ZonedDateTime` |
| UTC timestamp displayed for a user | `ofLocalizedDateTime(style).withLocale(...).withZone(...)` | `Instant` and `ZoneId` |

If you only have a `LocalTime` yet need to display a **full zone**, you must clarify the zone source and possibly a specific date; a region's offset can depend on the date due to historical or DST rules. Do not invent a date or zone when the data has not been provided.

## 16. Thread Safety, Caching, and Multi-User Applications

`DateTimeFormatter` is immutable and thread-safe, so you can share a **fully configured instance** across threads. However, a single formatter with locale `en-US` does not become multi-locale simply because it is thread-safe.

Example caching by locale and style:

~~~java
record FormatterKey(Locale locale, FormatStyle style) {}

Map<FormatterKey, DateTimeFormatter> cache =
        new ConcurrentHashMap<>();

DateTimeFormatter formatter = cache.computeIfAbsent(
        new FormatterKey(locale, FormatStyle.SHORT),
        key -> DateTimeFormatter.ofLocalizedDate(key.style())
                .withLocale(key.locale()));
~~~

This is a **snippet inside a method**, not a standalone program. It requires importing `java.util.Locale`, `java.util.Map`, `java.util.concurrent.ConcurrentHashMap`, `java.time.format.FormatStyle`, and `java.time.format.DateTimeFormatter`; the variable `locale` is an already validated locale.

This key is sufficient when **caching only date formatters** by style and locale. If you also cache date-time formatters with zones, add the zone to the key whenever a zone is attached to the formatter, along with any other options that affect configuration.

Do not use `Locale.setDefault(...)` per request. The default locale is JVM-wide shared state; mutating it can create race conditions when multiple threads construct formatters concurrently. It is better to store the effective locale per request and pass `withLocale(...)` explicitly.

With async tasks/thread pools, if a framework provides a request locale context, you must understand how context propagates across threads; do not assume it travels automatically with tasks under every execution mechanism.

## 17. Practical Service Example: Formatting Contextual Data

Create the file **`LocalizedPresentationService.java`**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public class LocalizedPresentationService {
    public static String date(LocalDate value, Locale locale) {
        return DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)
                .withLocale(locale)
                .format(value);
    }

    public static String event(
            Instant instant, Locale locale, ZoneId zone) {
        return DateTimeFormatter.ofLocalizedDateTime(FormatStyle.SHORT)
                .withLocale(locale)
                .withZone(zone)
                .format(instant);
    }

    public static void main(String[] args) {
        Locale language = Locale.US;
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate date = LocalDate.of(2024, 5, 6);
        Instant event = Instant.parse("2024-05-06T08:04:05Z");

        String localizedDate = date(date, language);
        String localizedEvent = event(event, language, zone);

        System.out.println(localizedDate.isBlank());
        System.out.println(localizedEvent.isBlank());
        System.out.println(event.atZone(zone).getHour());
    }
}
~~~

~~~bash
javac LocalizedPresentationService.java
java LocalizedPresentationService
~~~

Exact output independent of month-name spelling:

~~~text
false
false
15
~~~

The example intentionally avoids pinning localized strings in stdout; what needs verification is that both formatters produce non-blank strings and the event is properly converted to hour 15 in the specified zone.

**Service contract:**
- `date(...)` accepts only `LocalDate`, so it does not involve time zones.
- `event(...)` accepts an explicit `Instant` and `ZoneId`; date-time formatting has full context.
- `Locale` comes from the user/product configuration, never guessed from the zone.
- In a real application, validate nulls, supported locales, and configuration errors before invoking the helpers.

## 18. Common Mistakes and Fixes

1. **Using `ofLocalizedDate` to format time as well.** That factory is for the date part only. If you need both, use `ofLocalizedDateTime`.
2. **Using `ofLocalizedTime` for `LocalDate`.** `LocalDate` lacks the hour/minute fields required by a time formatter.
3. **Using `ofLocalizedDateTime(SHORT)` with `LocalTime`.** There is no date; the formatter will not invent the missing part.
4. **Using `FULL` or `LONG` time with `LocalTime` and hitting `DateTimeException`.** The style may require a time zone; provide an appropriate temporal and zone, or choose another style.
5. **Assuming `LocalDateTime` already has a time zone.** It contains a local date and time, but no `ZoneId` or offset.
6. **Thinking `Locale.US` implies a US time zone.** Locale controls presentation, not where the event occurred.
7. **Hardcoding "SHORT = dd/MM/yyyy".** The `SHORT` pattern is chosen by the locale/provider and can look completely different.
8. **Using `ofPattern("dd/MM/yyyy")` and expecting `withLocale` to reorder day/month.** A custom pattern fixes field order; locale mainly affects localized text and symbols.
9. **Parsing a localized string with a formatter for another locale.** This can misinterpret values or fail; use the matching locale and style.
10. **Expecting round-trips to preserve seconds when using `SHORT`.** If the formatter does not print seconds, that data is lost in the string.
11. **Using localized formatters for machine-to-machine communication between services.** Use ISO-8601 or an agreed schema instead of depending on a user's locale.
12. **Changing `Locale.setDefault` on every request.** JVM-wide state can leak locales across users.
13. **Hardcoding the AM/PM whitespace character in tests.** Some locales/providers use a narrow no-break space.
14. **Sharing an `en-US` formatter for every user just because it is thread-safe.** Safe sharing does not mean the locale is right.

## 19. Testing Properly

Build tests aligned with each layer of information:

| Test | What to verify |
| --- | --- |
| `ofLocalizedDate` with `LocalDate` | Formats successfully; does not require time/zone |
| `ofLocalizedTime(SHORT)` with `LocalTime` | Formats successfully under supported locales/providers |
| `ofLocalizedDateTime(SHORT)` with `LocalDateTime` | Contains both date and time fields |
| `ofLocalizedDateTime(LONG, SHORT)` | Long date + short time per locale pattern |
| `FULL` time with `ZonedDateTime` | Has a zone to express the required name/offset |
| `FULL` time with `LocalTime` | Handles missing-zone errors according to pattern/runtime |
| Switching `Locale.US` to `Locale.GERMANY` | Formatter locale changes; output matches local conventions |
| Using `Instant` with `withZone` | Timestamp converts to local time accurately |
| Parsing with matching locale/style | Verifies round-trips only to the precision preserved by the style |
| Upgrading JDK/locale provider | Checks critical strings and Unicode characters |

For **data-level** tests, asserting `formatter.getLocale()`, `formatter.getZone()`, `LocalDate`, or the hour of a `ZonedDateTime` is much more stable than asserting a long text pattern tied to CLDR.

For **display-output** tests, controlled snapshots are still useful to catch unintended regressions, provided you document the runtime/provider and handle intentional Unicode differences.

## 20. Exercises with Answers

**Question 1.** You want to display a birth date by locale, with no time needed. Which factory do you use?

**Answer:** `DateTimeFormatter.ofLocalizedDate(style).withLocale(locale)` with `LocalDate` data.

**Question 2.** You want to display an opening time `15:30` in the reader's language using `LocalTime`. What should you start with?

**Answer:** `ofLocalizedTime(FormatStyle.SHORT).withLocale(locale)`; do not default to `FULL` when there is no zone.

**Question 3.** What are the two parameters of `ofLocalizedDateTime(FormatStyle.LONG, FormatStyle.SHORT)` for?

**Answer:** The first parameter chooses the **date** style; the second chooses the **time** style.

**Question 4.** Why can `ofLocalizedDateTime(FormatStyle.FULL).format(LocalDateTime.now())` throw an error?

**Answer:** The `FULL` time pattern may require time-zone information that `LocalDateTime` does not provide.

**Question 5.** Does calling `withLocale(Locale.JAPAN)` convert a UTC instant to Japanese time?

**Answer:** No. You need the corresponding zone, such as `ZoneId.of("Asia/Tokyo")`, when converting an `Instant` to local time.

**Question 6.** Why can formatting `LocalTime.of(15,4,5)` with `SHORT` and parsing it back fail to preserve seconds?

**Answer:** Some `SHORT` patterns print only hours and minutes, so the seconds information is not present in the string.

**Question 7.** When should you use `ISO_LOCAL_DATE` or `LocalDate.toString()` instead of a localized date?

**Answer:** When you need stable data exchange between programs, independent of the reader's language.

**Question 8.** How does `DateTimeFormatter` immutability help a server?

**Answer:** Properly configured formatters can be safely shared across threads; however, you must still choose the right locale, zone, and style for each user context.

## 21. Summary

You can remember the three factories with a short diagram:

~~~text
DateTimeFormatter.ofLocalizedDate(style)
    → Date

DateTimeFormatter.ofLocalizedTime(style)
    → Time

DateTimeFormatter.ofLocalizedDateTime(style)
DateTimeFormatter.ofLocalizedDateTime(dateStyle, timeStyle)
    → Date + time
~~~

**Workflow for proper usage in an application:**

1. Identify the **data type**: date, time, local date-time, or timestamp.
2. Choose the required **style**: `SHORT`, `MEDIUM`, `LONG`, `FULL`.
3. Attach the **effective locale** with `withLocale(locale)`.
4. If formatting a timestamp or zoned time, provide a **`ZoneId`** via the temporal or `withZone(...)`.
5. Verify that the chosen pattern has all required fields, especially with `FULL`/`LONG`.
6. Keep exchange data in structured/ISO form; use localized formatters for the **human UI**.
7. Test across all product-supported locales and JDK/providers.

**Key takeaway:** `ofLocalizedDate` is for dates only, `ofLocalizedTime` is for times only, and `ofLocalizedDateTime` is for both. **Locale determines phrasing and conventions; zone determines the local time of a timestamp; FormatStyle determines the desired level of detail.** Three independent concepts that must be coordinated properly.

Java SE 17 documentation: [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html), [FormatStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/FormatStyle.html), [ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).
