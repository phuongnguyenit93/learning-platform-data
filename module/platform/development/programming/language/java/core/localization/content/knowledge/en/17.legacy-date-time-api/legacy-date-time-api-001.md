# DateFormat and Locale-Based Factories in Java

## 1. Overview: formatting date and time for the user's language

`java.text.DateFormat` is a date and time formatting and parsing API belonging to **Java core, the legacy date-time API group (`java.text`/`java.util`)**. Before `java.time` appeared, Java applications commonly combined `java.util.Date`, `Calendar`, `TimeZone`, and `DateFormat` to display dates and times according to each language and region.

The same point in time can be displayed differently:

- In English (United States): `January 2, 2024` or `1/2/24`.
- In French (France): `2 janvier 2024`.
- With the same locale but a different **style**, the date string can be short, long, include the weekday name or not.
- With the same locale and style but a **different time zone**, a timestamp near midnight can belong to two different calendar dates.

`DateFormat` provides **factory methods** to choose a format according to `Locale` without **having to write a specific date pattern yourself for each language**. Instead of hardcoding `"dd/MM/yyyy"` or `"MM/dd/yyyy"`, you ask Java to create a formatter by purpose: date, time, or date+time.

**Lesson objectives:** master all `DateFormat` factories, the `FULL/LONG/MEDIUM/SHORT` styles, how to pass `Locale` and `TimeZone`, how to format/parse safely, recognize legacy API limitations, and know how to choose `java.time` for new code.

## 2. What class is DateFormat?

`DateFormat` is an **abstract class** extending `java.text.Format`:

- `format(Date)` converts a date-time value into a string for display.
- `parse(String)` or `parse(String, ParsePosition)` reads a string into a `java.util.Date`.
- `setTimeZone(TimeZone)` configures the time zone for the formatter.
- `setLenient(boolean)` adjusts whether the parser/calendar allows lenient handling of invalid dates.
- `getCalendar()` and `setCalendar(Calendar)` access/configure the calendar used by the formatter.
- `getNumberFormat()` and `setNumberFormat(NumberFormat)` configure number formatting for the fields.

The object returned by a factory has a **declared type of `DateFormat`**. In many environments, the implementation is `SimpleDateFormat`; however, you should not always cast to `SimpleDateFormat` if you only need to use the common APIs, because the implementation may depend on the locale provider and JDK environment.

A `Date` represents an instant in time (epoch milliseconds) and **does not carry a language-specific display format or time zone name on its own**. `DateFormat` is responsible for presenting calendar fields according to the configured `Locale` and zone. When parsing, it uses those rules to construct a `Date`. You cannot conclude with certainty from seeing the string `"02/01/2024"` whether it represents January 2 or February 1 without knowing the locale/pattern.

## 3. Main factories and how to choose them

The factories are static methods of `DateFormat`:

| API | Purpose | Important parameters |
| --- | --- | --- |
| `DateFormat.getDateInstance()` | Date only, default style. | Uses `DEFAULT` and the default locale for formatting. |
| `DateFormat.getDateInstance(int style)` | Date only by style. | `FULL/LONG/MEDIUM/SHORT`. |
| `DateFormat.getDateInstance(int style, Locale locale)` | Date only, explicit style and locale. | Suitable when the application serves multiple languages. |
| `DateFormat.getTimeInstance()` | Time only, default style. | Does not specify locale. |
| `DateFormat.getTimeInstance(int style)` | Time only by style. | Does not specify locale. |
| `DateFormat.getTimeInstance(int style, Locale locale)` | Time only by style and locale. | Can select 12h/24h layout according to locale conventions. |
| `DateFormat.getDateTimeInstance()` | Includes date and time, default style. | Both parts use `DEFAULT`. |
| `DateFormat.getDateTimeInstance(int dateStyle, int timeStyle)` | Date and time with two separate styles. | Argument order is **dateStyle first, timeStyle second**. |
| `DateFormat.getDateTimeInstance(int dateStyle, int timeStyle, Locale locale)` | Date, time, and locale are all specified. | Most explicit way when using the legacy API. |
| `DateFormat.getInstance()` | Convenience factory for short date+time. | Equivalent to using `SHORT` for date and time. |

Overloads without a `Locale` parameter rely on the JVM's default locale for formatting (related to `Locale.Category.FORMAT`). In a multi-user server environment, **do not change `Locale.setDefault(...)` per request**. Pass the user's locale to a factory with a `Locale` parameter to avoid affecting other threads.

### Three factory groups for three needs

```java
Locale locale = Locale.US;

DateFormat dateOnly =
        DateFormat.getDateInstance(DateFormat.LONG, locale);

DateFormat timeOnly =
        DateFormat.getTimeInstance(DateFormat.SHORT, locale);

DateFormat dateAndTime =
        DateFormat.getDateTimeInstance(
                DateFormat.MEDIUM, DateFormat.SHORT, locale);
```

These are illustrative statements placed inside a Java method, requiring imports for `java.text.DateFormat` and `java.util.Locale`. A complete runnable program for Java 17+ is provided in a later section.

Do not use `getTimeInstance(...)` if you need to display a date; do not use `getDateInstance(...)` when the UI needs time as well. With `getDateTimeInstance(...)`, **dateStyle** and **timeStyle** are chosen separately: for example, `MEDIUM` for the date, `SHORT` for the time.

### Do not guess the factory's pattern

A factory may produce a pattern like a specific `SimpleDateFormat`, but **the API contract is to provide a format appropriate for the locale and style**, not to promise that every JDK will always use the same pattern/string. CLDR data and locale providers can vary across JDK versions, `java.locale.providers` configuration, or environments.

Therefore, for UI tasks, style-based output should be treated as **localized for display**, not as a protocol string to pass into an API or compare strictly byte-for-byte across all JDK versions.

## 4. The four style levels and practical meaning

`DateFormat` defines the constants:

| Constant | Constant value in API | Typical role |
| --- | ---: | --- |
| `DateFormat.FULL` | `0` | Full representation, usually includes weekday and month name (for date). |
| `DateFormat.LONG` | `1` | Long date/time format, usually includes month name or zone info in time. |
| `DateFormat.MEDIUM` | `2` | Medium length; `DEFAULT` is equivalent to `MEDIUM`. |
| `DateFormat.SHORT` | `3` | Short representation, usually uses digits and minimal components. |

**A style is not a fixed character set.** For example, `FULL` with `Locale.US` might be `Tuesday, January 2, 2024`; with another locale, the weekday and month might be in different positions, use native words, or use a different numbering system. `SHORT` might not include a full four-digit year; when parsing, be careful with two-digit years and ambiguity.

For the same date Jan 2, 2024, a common Java 17 configuration for `Locale.US` produces:

| Date-only factory | Example output |
| --- | --- |
| `getDateInstance(FULL, Locale.US)` | `Tuesday, January 2, 2024` |
| `getDateInstance(LONG, Locale.US)` | `January 2, 2024` |
| `getDateInstance(MEDIUM, Locale.US)` | `Jan 2, 2024` |
| `getDateInstance(SHORT, Locale.US)` | `1/2/24` |

These examples are only meant to help read styles; **do not write business code that assumes fixed punctuation, abbreviations, or digit widths across all locales/JDKs**.

For time, `DateFormat.getTimeInstance(SHORT, Locale.US)` may render `3:04 PM`, whereas in locales that prefer 24-hour time it typically has a different form. `LONG/FULL` may additionally display a time zone or zone name, depending on the implementation and locale. Do not equate `Locale.US` with a US time zone; locale and zone are two independent configurations.

### DEFAULT and MEDIUM

`DateFormat.DEFAULT` has the same value as `DateFormat.MEDIUM`. Therefore `getDateInstance()` is the common shorthand corresponding to `getDateInstance(DEFAULT)` and the default locale; `getDateTimeInstance()` uses the default style for both components. This "default" **does not fix the language**, because the JVM default locale can differ between a developer machine and a CI machine.

## 5. Locale: language, region, and formatting data

`Locale` stores language/region/variant identity, for example:

```java
Locale us = Locale.US;
Locale france = Locale.FRANCE;
Locale vietnam = Locale.forLanguageTag("vi-VN");

DateFormat usDate =
        DateFormat.getDateInstance(DateFormat.LONG, us);
DateFormat frDate =
        DateFormat.getDateInstance(DateFormat.LONG, france);
DateFormat viDate =
        DateFormat.getDateInstance(DateFormat.LONG, vietnam);
```

With the same `Date` and the same `TimeZone`, the three formatters can produce three different ways of writing the date. Locale affects ordering, vocabulary, month/weekday names, how time is written, and related rules. It **does not automatically convert** from UTC to Ho Chi Minh City time, nor does it change `Date` to a different point in time.

### Why pass locale explicitly?

- User A wants a Vietnamese UI, user B wants English; the same JVM serves both.
- A CI or Docker container may set `Locale.getDefault()` differently from a developer's machine.
- Tests become more stable with an explicit locale parameter, not depending on the execution order of other tests.
- You do not need to mutate global state with `Locale.setDefault(...)`; this is an operation that can cause races in a multithreaded application.

### Default locale for FORMAT

Java has `Locale.Category.DISPLAY` and `Locale.Category.FORMAT`. Formatting factories without a locale parameter use the default intended for formatting; this default can differ from the locale used to display language names.

Example of the risk (illustrative only, **not recommended in a web request**):

```java
Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
DateFormat df = DateFormat.getDateInstance(DateFormat.LONG);
```

This affects the JVM's global configuration. When you must test changing the default locale in a unit test, capture and fully restore the relevant defaults in a `try/finally`, and avoid uncoordinated parallel tests. Normally, using `getDateInstance(style, locale)` is a better solution.

### Which locales are supported?

`DateFormat.getAvailableLocales()` returns the set of locales that the factories can support in the Java environment. This set of locales/data is not a guarantee that all translations/month names will appear identically across JDK versions. For important product features, test the main locales your application allows; do not assume from a country name that every date and time will be formatted just as users expect.

## 6. TimeZone: a required part to control the point in time

`DateFormat` creates an object with a `Calendar`/`TimeZone`; if you do not specify a zone, it may use the JVM's default time zone at the time of configuration. For the same timestamp, the local date/time can differ by zone.

Example:

```java
Date event = Date.from(
        Instant.parse("2024-01-02T00:30:00Z"));

DateFormat clock = DateFormat.getDateTimeInstance(
        DateFormat.SHORT, DateFormat.SHORT, Locale.US);
clock.setTimeZone(TimeZone.getTimeZone("UTC"));
String inUtc = clock.format(event);

clock.setTimeZone(
        TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));
String inVietnam = clock.format(event);
```

This snippet is placed inside a Java method and requires importing `Date`, `Instant`, `DateFormat`, `TimeZone`, and `Locale`. The two strings can have different displayed times because the same instant `00:30Z` is `07:30` in Ho Chi Minh City. **You do not modify `Date event`, only change the formatter.**

**A special rule:** `Locale` determines how dates and times are written; `TimeZone` determines the local date/time fields of an instant. Do not take the user's locale and guess the timezone by appending a country code; a single country can have multiple time zones, and a person may want to display time in another region.

### TimeZone, DST, and date boundaries

For time zones with daylight saving time, the UTC offset can change by date. Do not add or subtract hours manually. When you need to display or parse timestamps, use a `TimeZone` with an explicit region ID; for new projects, prefer `ZoneId` and `ZonedDateTime` from `java.time`.

Using a single fixed timestamp in tests is not enough if the logic involves scheduled appointments; you should also test times near midnight and DST transitions in relevant regions.

### Note on invalid zone IDs

`TimeZone.getTimeZone(String)` may return `GMT` when the ID is unrecognized, instead of reporting an error as expected. With time zone data from users, do not treat this result as proof of a valid zone ID. Use the supported ID list or the `ZoneId.of(...)` API (which throws a clearer error for invalid IDs) along with validation rules at the input boundary.

## 7. Standalone Java 17+ example

Create the file **`DateFormatFactoriesDemo.java`**. The program creates independent formatters using factories, passes `Locale` explicitly, sets the `UTC` zone, and disables leniency when testing parsing. For time output under `Locale.US`, the `view(...)` helper normalizes two common forms of non-breaking spaces into regular spaces for easier log reading; it **does not turn every format across every JDK into an invariant string**.

```java
import java.text.DateFormat;
import java.text.ParsePosition;
import java.time.Instant;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class DateFormatFactoriesDemo {

    private static DateFormat utc(DateFormat format) {
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);
        return format;
    }

    private static String view(DateFormat format, Date date) {
        // Normalize whitespace of the demo output:
        // narrow no-break space and no-break space.
        return format.format(date)
                .replace('\u202F', ' ')
                .replace('\u00A0', ' ');
    }

    private static void tryParse(DateFormat format, String input) {
        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(input, position);

        boolean complete = parsed != null
                && position.getIndex() == input.length();

        System.out.println("parse(" + input + ")="
                + (complete ? "OK" : "REJECTED")
                + "; consumed=" + position.getIndex()
                + "/" + input.length());
    }

    public static void main(String[] args) {
        Date fixed = Date.from(
                Instant.parse("2024-01-02T15:04:05Z"));

        Locale us = Locale.US;
        Locale fr = Locale.FRANCE;

        System.out.println("us.full=" + view(utc(
                DateFormat.getDateInstance(DateFormat.FULL, us)),
                fixed));
        System.out.println("us.long=" + view(utc(
                DateFormat.getDateInstance(DateFormat.LONG, us)),
                fixed));
        System.out.println("us.medium=" + view(utc(
                DateFormat.getDateInstance(DateFormat.MEDIUM, us)),
                fixed));
        System.out.println("us.short=" + view(utc(
                DateFormat.getDateInstance(DateFormat.SHORT, us)),
                fixed));

        System.out.println("us.time=" + view(utc(
                DateFormat.getTimeInstance(DateFormat.SHORT, us)),
                fixed));
        System.out.println("us.both=" + view(utc(
                DateFormat.getDateTimeInstance(
                        DateFormat.MEDIUM,
                        DateFormat.SHORT, us)),
                fixed));

        System.out.println("fr.long=" + view(utc(
                DateFormat.getDateInstance(DateFormat.LONG, fr)),
                fixed));

        DateFormat parser = utc(
                DateFormat.getDateInstance(DateFormat.LONG, us));

        tryParse(parser, "January 2, 2024");
        tryParse(parser, "January 2, 2024junk");
        tryParse(parser, "February 30, 2024");
    }
}
```

Compile and run with JDK 17+ in the directory containing the file:

```bash
javac -encoding UTF-8 DateFormatFactoriesDemo.java
java DateFormatFactoriesDemo
```

**Stdout verified on a Java 17 environment with corresponding locale data:**

```text
us.full=Tuesday, January 2, 2024
us.long=January 2, 2024
us.medium=Jan 2, 2024
us.short=1/2/24
us.time=3:04 PM
us.both=Jan 2, 2024, 3:04 PM
fr.long=2 janvier 2024
parse(January 2, 2024)=OK; consumed=15/15
parse(January 2, 2024junk)=REJECTED; consumed=15/19
parse(February 30, 2024)=REJECTED; consumed=0/17
```

**Note on reproducibility:** date-time text strings such as weekday/month names, punctuation, `SHORT` style, and abbreviations may differ across locale provider/JDK configurations. The example uses a fixed Java runtime and sample data to produce the output above; in a real project, if you want to assert every exact character across all JDK versions, do not rely on locale factories with default styles as a data contract. Test against your deployment version, or use a clearly specified formatter/pattern when fixed machine-to-machine strings are needed.

### Explaining the output

1. `us.full`, `us.long`, `us.medium`, and `us.short` show four ways of presenting the same date across styles.
2. `us.time` takes only the time part; `us.both` combines the date in `MEDIUM` with the time in `SHORT`. Non-breaking spaces in some locales/JDKs are normalized for demo readability.
3. `fr.long` illustrates **the same timestamp and zone** with a different locale, hence using French month names and a different date order.
4. `parse(...)=OK` for a string matching the pattern and consumed **all 15 characters**.
5. `January 2, 2024junk` is parsed into a date from the leading part, leaving four `junk` characters, so the demo's validation function rejects it even though `parsed != null`.
6. `February 30, 2024` does not exist on the calendar; because `setLenient(false)` was called, the parser does not roll the date into March and rejects it instead.

The program does not modify the JVM's default locale or time zone. Each factory is created for a specific purpose; mutable formatters are not shared across threads.

## 8. Parsing is a different operation from formatting

`DateFormat.format(...)` takes a `Date` and produces a **display string**. `DateFormat.parse(...)` tries to read an **input string** and returns a `Date`. These two directions are not necessarily strictly symmetrical:

- `SHORT` may omit the century or seconds, so the string does not preserve all details of the source timestamp.
- `getDateInstance(...)` only represents the date and cannot preserve hours/minutes/seconds when formatted and parsed back.
- When parsing date-only into a `Date`, the time of day is determined by the resolver/calendar according to rules and zone; it should not be treated as the timestamp of the original event.
- An input string without a time zone will be interpreted using the formatter's zone, which may differ from the time zone the user had in mind.
- The parser may accept a valid prefix of the string and ignore the trailing portion if the final position is not checked.

### parse(String) and ParseException

`DateFormat.parse(String)` can throw `java.text.ParseException` when it cannot read the string. If the application needs to detect **ignored trailing characters**, it is usually better to use `parse(String, ParsePosition)` and then verify:

```java
ParsePosition pos = new ParsePosition(0);
Date parsed = formatter.parse(input, pos);

boolean valid = parsed != null
        && pos.getIndex() == input.length();
```

This is an illustrative snippet placed inside a Java method (with `formatter` and `input` already defined, and `ParsePosition`/`Date` imported); the standalone example was presented in section 7.

On a failed parse, `parse(String, ParsePosition)` may return `null` and update `errorIndex`. However, **consuming the entire string only proves the parser accepted a structure it understands**, not that the date lies within the business domain or that the input matches the exact format the form requires.

### setLenient(false): do not silently fix nonexistent dates

`DateFormat` uses a `Calendar` in its parsing mechanism. If the parser is lenient, it may adjust `31/02` to another date instead of reporting an error. When you want users to enter a genuinely valid calendar date, set:

```java
DateFormat formatter =
        DateFormat.getDateInstance(DateFormat.SHORT, Locale.US);
formatter.setTimeZone(TimeZone.getTimeZone("UTC"));
formatter.setLenient(false);
```

This snippet is placed inside a Java method with appropriate imports. Afterward, you **still need** to check that parsing consumed the entire string and perform domain validation. Choosing `SHORT` allows inputs with a two-digit year, so in new applications you should use a pattern that explicitly requires a full year if the data is important.

### Two-digit years and ambiguity

`SHORT` factories may use the year `24` instead of `2024`. When parsing, some implementations have a two-digit year window rule; the result may depend on when the formatter was created, the provider configuration, and the implementation. Avoid storing birthdates, contract expiration dates, or financial schedules as two-digit years. For user input, define a full-year format and prefer `java.time.DateTimeFormatter` with a strict resolver.

## 9. Limitations of the legacy date-time API

### 9.1. Date and Calendar have different purposes

`java.util.Date` describes an instant in time, while `Calendar` manages calendar fields according to time zone/locale and can be mutated. `DateFormat` combines them during formatting/parsing. This easily leads to confusion: seeing `DateFormat` print a different date does not mean the source `Date` was modified.

`DateFormat.setCalendar(Calendar)` is a deep configuration operation; when changing the calendar, you should re-verify the time zone, lenient mode, and chronology semantics in use. Do not use `Calendar` as an immutable data type across all business logic.

### 9.2. Factories do not guarantee always returning SimpleDateFormat

Do not write:

```java
SimpleDateFormat df = (SimpleDateFormat)
        DateFormat.getDateInstance(DateFormat.SHORT, locale);
```

without a requirement and guarantee about the implementation. This code snippet **illustrates a risky cast**, not a recommendation. For general APIs, keep the `DateFormat` type. If you truly need a specific pattern and are working with a legacy library, you can intentionally instantiate `new SimpleDateFormat(pattern, locale)`, while remembering to control calendar, timezone, leniency, and thread safety.

### 9.3. DateFormat is mutable and not thread-safe

`DateFormat` and `SimpleDateFormat` are **mutable** and are not guaranteed to be thread-safe when multiple threads use the same instance without synchronization. `setTimeZone`, `setLenient`, `setCalendar`, and formatting/parsing operations can depend on internal state.

Suitable options:

1. Create a new formatter instance within the method or request scope.
2. Clone a template formatter when a shared configuration is needed and ensure separate copies.
3. Synchronize all access if sharing is mandatory, while understanding contention costs and avoiding missed access points.

**Do not create a `static DateFormat` and mutate its locale/timezone on every request.** For new projects, `java.time.format.DateTimeFormatter` is immutable and thread-safe, solving many of these issues.

### 9.4. Dependence on default locale and TZDB

A formatter created by a factory without a `Locale` and without an assigned zone can produce different output when run on a machine with a different JVM/OS configuration. Zone names, typography, and local rules are also affected by the Java environment's locale data and time zone database. In tests, pass locale and zone explicitly and use fixed timestamps; do not use the current date/time as a baseline if you want stable test stdout.

## 10. When to use factories vs. when a specific pattern is needed?

| Requirement | Recommended option | Reason |
| --- | --- | --- |
| Display date to users by locale | `DateFormat.getDateInstance(style, locale)` | Provides localized formatting without writing a pattern for every language. |
| Display time to users | `DateFormat.getTimeInstance(style, locale)` | Follows the locale's time presentation rules. |
| Display date+time together | `DateFormat.getDateTimeInstance(dateStyle, timeStyle, locale)` | Allows separate date and time styles. |
| Format used in logs / machine-to-machine communication | `DateTimeFormatter.ISO_INSTANT` / suitable ISO formatter | Does not depend on UI locale wording. |
| Birthdates, date-only schedules | `LocalDate` + `DateTimeFormatter` | Avoids forcing a pure date into a time-zone-dependent timestamp. |
| Absolute timestamp for storage/exchange | `Instant` or appropriate offset date-time type | Clearly defines a point on the timeline. |
| Date input with a product-specified pattern | `DateTimeFormatter` + `ResolverStyle.STRICT` | Catches nonexistent dates and avoids many legacy parsing ambiguities. |
| Maintaining legacy API accepting/returning `Date` | `DateFormat` + explicit locale/zone/lenient | Preserves compatibility while managing risks. |
| Formatter shared across multiple threads | `DateTimeFormatter` | Immutable, suited for modern Java code. |

`DateFormat` factories are a useful choice when **maintaining legacy systems** or integrating with libraries that only use `Date`/`Calendar`. In new code, preferring `java.time` does not mean eliminating every factory immediately, but choosing semantically clear APIs for the domain and avoiding adding dependencies on mutable state.

### Interoperating between Date and Instant

When legacy code takes `Date` while the new domain uses `Instant`:

```java
Instant instant = Instant.parse("2024-01-02T15:04:05Z");
Date date = Date.from(instant);
Instant back = date.toInstant();
```

This snippet can run inside a Java method with `Instant` and `Date` imported. This conversion preserves the point-in-time meaning at `Date`'s millisecond precision; it **does not attach a timezone or Locale to the Instant**. For timestamps with nanoseconds, consider the precision loss when passing through `Date`.

## 11. Common mistakes and how to fix them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `getDateInstance()` for all users | Output depends on JVM default, not each user's locale. | Pass `Locale` explicitly. |
| Using `getDateInstance(...)` when time is needed | Format contains only the date. | Use `getDateTimeInstance(...)`. |
| Swapping `dateStyle` and `timeStyle` | Date and time receive unintended styles. | Always double-check parameter order. |
| Assuming `SHORT` is always `dd/MM/yyyy` | Locales can flip day/month and shorten the year. | Let factories handle UI; use explicit input patterns when needed. |
| Assuming locale automatically determines zone | Users sharing a language may span multiple time zones. | Choose `TimeZone`/`ZoneId` based on context. |
| Using `TimeZone.getTimeZone` with unverified IDs | Invalid IDs can fall back to GMT. | Validate zone IDs; consider `ZoneId.of`. |
| Assuming parse success means clean input | The parser can ignore trailing characters. | Use `ParsePosition` and verify full consumption. |
| Not calling `setLenient(false)` for input dates | Nonexistent dates may be silently adjusted. | Disable leniency and add domain validation. |
| Storing `MM/dd/yy` dates in a database | Two-digit years and ambiguous date formatting. | Use date types/ISO standards with an explicit schema. |
| Casting every factory result to `SimpleDateFormat` | Implementation dependence. | Keep `DateFormat` type or intentionally construct a dedicated instance. |
| Using a static `DateFormat` in a web server | Races and cross-request state leakage. | Create new/clone/synchronize, or migrate to `DateTimeFormatter`. |
| Comparing FULL output across all JDKs by exact text | CLDR data and providers may differ. | Test behaviorally; pin the environment if snapshot testing is needed. |

## 12. Recommended test suite

To be confident that localization with `DateFormat` works properly, test at minimum:

- **Date/time/dateTime:** each factory displays only the needed components, and the two separate styles of `getDateTimeInstance` are applied correctly.
- **Different locales:** the same timestamp and time zone are rendered in different languages/formats without altering the source value.
- **FULL/LONG/MEDIUM/SHORT:** verify against supported locales; do not rely on a single hardcoded pattern across all JDKs.
- **TimeZone:** test UTC and other region zones, especially timestamps near date boundaries.
- **Successful parse:** structurally valid input is fully consumed; after parsing, the resulting instant has the exact expected value.
- **Parse with trailing characters:** reject strings like `January 2, 2024junk` when the form requires the entire input to be valid.
- **Nonexistent dates:** `February 30, 2024` must be rejected when `setLenient(false)` is set.
- **Two-digit years:** define a policy rather than silently accepting ambiguous dates.
- **DST gaps/overlaps:** if the domain includes scheduled times in DST regions, test specific business decisions rather than just comparing formatted strings.
- **Concurrency:** do not share unsynchronized mutable formatters across tests/threads.
- **Abnormal inputs:** null, empty strings, length limits, inputs containing Unicode whitespace, or date symbols from other locales.

For code that parses user input, beyond consuming the entire string, domain validation is still required: birthdates not in the future if required by the product, due dates within allowed ranges, and appointment times valid in the user's time zone. **`DateFormat` is not a validator for all business rules.**

## 13. Hands-on exercises

**Exercise 1 — Three factories:** with the same `Date.from(Instant.parse("2024-01-02T15:04:05Z"))`, try `getDateInstance`, `getTimeInstance`, and `getDateTimeInstance` in `Locale.US`. Set `UTC` on all formatters. Explain the differences between date, time, and date+time.

**Exercise 2 — Four styles:** with `FULL`, `LONG`, `MEDIUM`, and `SHORT` for date, try `Locale.US` and `Locale.FRANCE`. Note how the date formatting changes; do not guess patterns from English abbreviations.

**Exercise 3 — Zone configuration:** format `2024-01-02T00:30:00Z` in `UTC` and `Asia/Ho_Chi_Minh` with the same locale/style. Confirm that `Date` does not change, only the displayed time changes. Try a zone with DST on a transition day and explain why fixed offset arithmetic should not be used.

**Exercise 4 — Parsing and trailing-character checks:** parse `January 2, 2024`, `January 2, 2024junk`, and `February 30, 2024` with `getDateInstance(LONG, Locale.US)`, `UTC`, and `setLenient(false)`. Print the result, `ParsePosition.getIndex()`, and `getErrorIndex()`; distinguish technical parse success from policy-valid input.

**Exercise 5 — Default locale:** run tests with different FORMAT defaults (isolated and restored with `try/finally`), comparing a factory without a locale to a factory with an explicit `Locale.US`. Why should a multi-user application not change the default locale on each request?

**Exercise 6 — Migrating to java.time:** write the same feature using `Instant`/`ZoneId`/`DateTimeFormatter.ofLocalizedDateTime(...)`. Compare the immutable API with mutable `DateFormat`; identify how to handle date-time strings stored in a database versus strings displayed to users.

## 14. Knowledge checklist

- [ ] Distinguish `DateFormat` from `Date`, `Calendar`, `TimeZone`, and `Locale`.
- [ ] Correctly use `getDateInstance`, `getTimeInstance`, `getDateTimeInstance`, and `getInstance`.
- [ ] Know the meaning of `FULL`, `LONG`, `MEDIUM`, and `SHORT`; `DEFAULT` corresponds to `MEDIUM`.
- [ ] Choose and pass `Locale` explicitly, avoiding reliance on default `FORMAT` in multi-user systems.
- [ ] Configure `TimeZone` explicitly when reproducible results are needed; do not add/subtract hours manually.
- [ ] Recognize that `parse` can accept a prefix, and use `ParsePosition` to verify full consumption.
- [ ] Use `setLenient(false)` when nonexistent dates must be rejected and perform additional business validation.
- [ ] Understand why a locale factory is not a fixed-string serialization contract.
- [ ] Do not share mutable `DateFormat` instances across threads without proper synchronization.
- [ ] Know when to use `java.time`/`DateTimeFormatter` instead of the legacy API.

**Conclusion:** `DateFormat` factories are tools for creating date-time formatters by **purpose (date/time/dateTime)**, **granularity (style)**, and **language context (Locale)**. When using them, separate time zone, parsing, and validation; choose the legacy API only when compatibility is required, and prefer `java.time` with its explicit temporal model in new code.
