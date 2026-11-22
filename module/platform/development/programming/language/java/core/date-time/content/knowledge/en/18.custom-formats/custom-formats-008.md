# Reusing Immutable Formatters and Explicit `Locale` or `ZoneId` Configuration

## 1. A Formatter Is a Reusable Configuration

A service may output thousands of date-time values using the same rules. If the rules are fixed, there is no need to rebuild a `DateTimeFormatter` for every value. You can create a shared formatter and call `format()` or `parse()` repeatedly with different data.

What makes this usage pattern suitable is that `DateTimeFormatter` is **immutable** and **thread-safe**, according to [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html). Methods such as `withLocale()` and `withZone()` return a new resulting configuration; they do not modify the original formatter.

However, being safe to share does not automatically mean the data semantics are right. If one place needs English and UTC, while another place needs a different language or the user's time zone, those configurations must be kept distinct. The two parameters to read carefully are:

- `Locale`: the language/region conventions for localized parts, such as month names.
- `ZoneId`: the time zone used to interpret or display an instant when required by the configuration and data type.

Do not infer the time zone from the language. Someone who chooses English may be in Vietnam; French month names do not mean the data must be in Paris time either.

## 2. How Immutability Changes Code Organization

For stable application configurations, you can place the formatter in a `static final` field, or a `final` field of a service object initialized with a known configuration. Processing methods only use the formatter without modifying it.

An illustrative example inside a class body:

```java
private static final DateTimeFormatter EXPORT_DATE = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT);
```

`final` prevents reassigning the reference field; the immutability of `DateTimeFormatter` itself ensures that the configuration contents are not modified when another thread calls methods on it. There is no need to add `synchronized` or create a `ThreadLocal<DateTimeFormatter>` just to share this formatter.

Conversely, a `DateTimeFormatterBuilder` while building rules is a mutable object meant for use in a single thread, as described in [Java SE 21 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html). If you need a builder, use it during initialization, obtain the resulting `DateTimeFormatter`, and share that result.

Another configuration can be derived from a base configuration:

```java
DateTimeFormatter french = EXPORT_DATE.withLocale(Locale.FRENCH);
```

This statement does not change `EXPORT_DATE`. If you only call `EXPORT_DATE.withLocale(...)` and discard the result, subsequent uses of `EXPORT_DATE` still keep the old configuration. With a pattern that only has numeric fields as above, changing the Locale might not even produce an easily visible difference; the full example below uses month names for clearer observation.

## 3. `Locale`: Choosing Language Conventions Instead of Relying on the Environment

With `ofPattern(pattern)` without passing a Locale, the library uses the default Locale from the `FORMAT` category at the time the formatter is created. A `static final` constant created with that default does not become an explicit language policy just because it is reused.

If an export contract uses English month names, write `ofPattern(pattern, Locale.ENGLISH)`. If it is a neutral interchange format with well-defined numeric fields, `Locale.ROOT` is the choice that clearly expresses intent. For a user interface, the Locale can come from the user's language/region preference.

Distinguish between two styles of configuration:

| Creation method | What is decided |
| --- | --- |
| `ofPattern("dd MMM uuuu", locale)` | Keeps the day–month–year order of the pattern; month names depend on the Locale |
| `ofLocalizedDate(style).withLocale(locale)` | Lets the localized style determine the appropriate display pattern |

Changing the Locale does not automatically reorder the fields of a fixed pattern, nor does it translate literal text placed in the pattern. If you use digits or decimal separators according to custom rules, there is also `DecimalStyle`; you should not treat `withLocale()` as a command that changes every aspect of the data.

Month names and localized formatting depend on the runtime's locale data. For an interchange format that requires strict stability across systems, prefer standard conventions or explicit numeric patterns rather than relying on localized text.

## 4. `ZoneId`: The Same Instant Can Be Displayed Differently

An `Instant` represents a point on the timeline; it does not carry a local time on its own to populate pattern fields such as day, hour, or minute. When a formatter has `withZone(zone)`, it has the context to represent that instant in the chosen zone.

For the instant `2025-06-10T02:00:00Z`:

```text
UTC                  → 2025-06-10 02:00
Asia/Ho_Chi_Minh      → 2025-06-10 09:00
```

It is still the same instant; the formatter only produces a view according to the zone. It does not modify the original `Instant`. When exporting date-times for a report, you must determine the report's zone before formatting, because near a day boundary, two zones can even produce two different calendar dates.

`ofPattern()` by itself does not attach a default zone. If you want the machine's current zone, you must deliberately choose `ZoneId.systemDefault()`. If the application has a fixed business zone, configure that zone ID; if the zone is chosen by the user, pass that choice to the display point. Do not implicitly use the server configuration to represent all users.

## 5. Full Verification Program

Save the code to `ReusableFormatterDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.time.format.*;
import java.util.Locale;
import java.util.concurrent.*;

public class ReusableFormatterDemo {
    private static final DateTimeFormatter DAY_TEXT = DateTimeFormatter
            .ofPattern("dd MMM uuuu", Locale.ENGLISH);
    private static final DateTimeFormatter MOMENT_BASE = DateTimeFormatter
            .ofPattern("uuuu-MM-dd HH:mm:ss XXX '['VV']'", Locale.ROOT);
    private static final ZoneId SOURCE_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
    private static final DateTimeFormatter MOMENT_HCM =
            MOMENT_BASE.withZone(SOURCE_ZONE);
    private static final DateTimeFormatter MOMENT_UTC =
            MOMENT_BASE.withZone(ZoneId.of("UTC"));

    public static void main(String[] args) throws Exception {
        LocalDate day = LocalDate.of(2025, 6, 10);
        DateTimeFormatter french = DAY_TEXT.withLocale(Locale.FRENCH);
        System.out.println("English = " + DAY_TEXT.format(day));
        System.out.println("French = " + french.format(day));
        System.out.println("English again = " + DAY_TEXT.format(day));

        Instant event = Instant.parse("2025-06-10T02:00:00Z");
        System.out.println("HCM = " + MOMENT_HCM.format(event));
        System.out.println("UTC = " + MOMENT_UTC.format(event));
        System.out.println("instant unchanged = " + event);

        DateTimeFormatter sourceInput = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT)
                .withZone(SOURCE_ZONE);
        Instant parsed = sourceInput.parse(
                "2025-06-10 09:00:00", Instant::from);
        System.out.println("source local -> instant = " + parsed);
        System.out.println("plain local = "
                + LocalDateTime.parse("2025-06-10 09:00:00", sourceInput));

        try {
            MOMENT_HCM.format(day);
        } catch (DateTimeException ex) {
            System.out.println("date without time = DateTimeException");
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<String> job = () -> MOMENT_HCM.format(event);
            Future<String> first = pool.submit(job);
            Future<String> second = pool.submit(job);
            System.out.println("shared formatter = "
                    + first.get().equals(second.get()));
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ReusableFormatterDemo.java
java ReusableFormatterDemo
```

Output:

```text
English = 10 Jun 2025
French = 10 juin 2025
English again = 10 Jun 2025
HCM = 2025-06-10 09:00:00 +07:00 [Asia/Ho_Chi_Minh]
UTC = 2025-06-10 02:00:00 Z [UTC]
instant unchanged = 2025-06-10T02:00:00Z
source local -> instant = 2025-06-10T02:00:00Z
plain local = 2025-06-10T09:00
date without time = DateTimeException
shared formatter = true
```

The month-name lines illustrate the output with the selected Locale. The time patterns use `XXX` to output the offset in `+07:00` or `Z` form, while `VV` outputs the zone ID. The `[` and `]` characters are placed inside single quotes in the pattern to become literal characters; they do not open an optional section in this pattern.

The section using `ExecutorService` submits two independent tasks sharing `MOMENT_HCM`, retrieves the results sequentially via `Future.get()`, and compares them. This illustrates shared usage; the thread-safety guarantee comes from the API contract and should not be inferred merely from the fact that two test tasks produced equal results. `shutdown()` stops accepting new tasks once the thread pool is no longer needed.

## 6. What the Program Demonstrates

### Derived Configurations Do Not Modify the Original

`french` is created using `DAY_TEXT.withLocale(Locale.FRENCH)`. After using it, `DAY_TEXT` still prints `Jun` as before. Similarly, `MOMENT_HCM` and `MOMENT_UTC` both start from `MOMENT_BASE` but have different zones; neither call silently changes the zone of the other formatter.

Because of this, you can build a base configuration and create variants as needed. If the configuration comes from each user request, keep the variant within the request scope or an appropriate configuration object; there is no need to reassign a global variable to switch languages/zones back and forth.

### A Zone Provides Context When the String Has No Zone

`sourceInput` parses a date-time without a zone in the string, but it is configured with `withZone(SOURCE_ZONE)`. The result has enough context to query `Instant::from`, so 09:00 from the source is interpreted as 02:00 UTC in the example.

That is a rule stating the source belongs to `Asia/Ho_Chi_Minh`, not a zone the formatter discovers from the text. If the text directly provides a zone ID, the zone parsed from the text is used instead of the override zone during the parse step. When the text contains an offset, the offset also participates in determining the instant. Therefore, do not use `withZone()` as an operation to erase or rewrite all zone/offset information in the input.

The call creating `LocalDateTime` on the next line still returns a type without a zone. Configuring a formatter does not turn every target type into a zoned type; to preserve or use that information, you need to choose a target type such as `ZonedDateTime` or query an `Instant` as intended.

### Having a Zone Does Not Automatically Supply Missing Time

`MOMENT_HCM.format(day)` fails because `day` is a `LocalDate` and the pattern requires a time as well. A time zone does not automatically add a default time of day. To create a start-of-day instant or a specific time, you must choose explicitly, such as `date.atStartOfDay(zone)` or `date.atTime(hour, minute).atZone(zone)`, before the step that requires an instant.

When the source uses a zone with daylight saving time transitions, interpreting a local date-time must also follow the zone's rules on that date. Do not replace a zone ID with a fixed offset just because the current offset happens to be the same.

## 7. Choosing an Appropriate Reuse Scope

| Case | How to organize the configuration |
| --- | --- |
| Fixed application format | A `static final DateTimeFormatter` constant named after its purpose |
| Fixed zone/Locale from service configuration | A `final` field, created after reading the configuration |
| Per-user display | Create a variant from a base formatter with the user's Locale/zone |
| Reading files from a specific source | A dedicated formatter describing the source's contract and zone if specified by the source |

Reusing avoids unnecessarily rebuilding the same rules, but it is not a reason to merge different semantics into a single global formatter. An input formatter may use `STRICT`, whereas an output formatter serves only one presentation format; names and configurations should reflect that purpose.

If, after measuring in practice, you need a cache for many configurations, the cache key must fully describe all relevant differences, not just the pattern string: Locale, zone, resolver mode, and other customizations that can change behavior. There is no need to add an unbounded cache for every user-supplied combination when there is no clear need.

Exercise: from `MOMENT_BASE`, create a variant using `ZoneId.of("Asia/Tokyo")` and format the same `event`. For the instant in the program, the hour part will be 11:00 and the offset `+09:00`; `MOMENT_HCM` must still output 09:00. Then explain why merely changing the `Locale` to Japanese is not enough to perform this zone change.
