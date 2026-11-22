# DateTimeFormatter.ofLocalizedPattern() and Requested Date-Time Templates

When building multilingual applications, you often want to **specify which date/time fields to display** — such as year, month, day, or hour/minute — while letting each locale decide the **order, separators, month names, and natural presentation**.

Since **Java 19**, `java.time.format.DateTimeFormatter` provides:

~~~java
DateTimeFormatter.ofLocalizedPattern(String requestedTemplate)
~~~

This method accepts a **requested template**. It is not a fixed formatting pattern. Java looks up the closest localized format for the requested fields based on Unicode LDML rules and available locale data. This is useful when `FormatStyle.SHORT/MEDIUM/LONG/FULL` does not give the exact *set of fields* the product wants to display.

**Version note:** `ofLocalizedPattern(String)` was introduced to the JDK in **Java 19**, so code calling this method **will not compile with `--release 17` or JDK 17**. The full runnable code below targets **Java 19 or later**; section 10 covers alternatives for Java 17.

## 1. The Problem: Request Fields Without Imposing Ordering

Suppose you need to display the date June 16, 2020. Two users may want the same three fields—**year, month, day**—but presented differently:

~~~text
Locale.US: 6/16/2020
Locale.UK: 16/06/2020
~~~

If you use a rigid pattern `"dd/MM/yyyy"`, US users still get the day/month order imposed by the developer. If you use `"MM/dd/yyyy"`, UK users get US ordering forced upon them. Beyond ordering, locale also affects month spelling, connectors, and separators.

With `ofLocalizedPattern("yMd")`, you are saying:

- `y`: need **year**.
- `M`: need **month**.
- `d`: need **day of month**.
- The order inside the template is a **canonical order for describing the fields**, not an instruction to print year before month before day.

Java may present this as day/month/year, month/day/year, or another form suited to the locale. Providing a template requests **the field set and approximate style**; it does not guarantee a byte-for-byte fixed pattern across all JDKs/CLDR versions.

## 2. Three Easily Confused Ways to Create a DateTimeFormatter

| API | Input | Purpose | Example |
| --- | --- | --- | --- |
| `ofPattern(pattern, locale)` | **Fixed format pattern** | Control symbol positions, separators, literals | `"dd/MM/uuuu"` |
| `ofLocalizedDate(FormatStyle.MEDIUM)` | **Style level** | Let the locale choose how to display a full date at MEDIUM level | `FormatStyle.MEDIUM` |
| `ofLocalizedPattern(requestedTemplate)` | **Requested template** | Choose which fields must appear; let the locale pick the closest matching pattern | `"yMd"`, `"yMMM"`, `"Hm"` |

Both `ofLocalizedDate(...)` and `ofLocalizedPattern(...)` provide locale-dependent formatting. The key difference is that `FormatStyle` specifies a **general presentation level**, whereas a requested template specifies the **components to display**.

For example, when the UI needs only **month and year** without the day, `ofLocalizedDate(FormatStyle.MEDIUM)` is not a direct fit because it formats a complete date. `ofLocalizedPattern("yMMM")` lets you explicitly request **year + abbreviated month name** while still letting the locale arrange them.

### ofPattern("yMd") is not the same as ofLocalizedPattern("yMd")

This is the easiest mistake to make. With `ofPattern("yMd")`, the letters `y`, `M`, and `d` are interpreted as a **pattern printed in the exact sequence written**, never reordered into day/month order by locale. With `ofLocalizedPattern("yMd")`, those three letters are interpreted as a **requested template** to look up a localized pattern.

The same letters do not mean the same thing. The behavior depends on **which method** is called.

## 3. Requested Template Syntax: Fields in Canonical Order

Per the `DateTimeFormatter.ofLocalizedPattern` documentation, a template has symbol groups ordered from largest unit to smallest:

~~~text
G{0,5}             era
y*                 year
Q{0,5}             quarter
M{0,5}             month
w*                 week of week-based year
E{0,5}             day of week
d{0,2}             day of month
B{0,5}             period of day
[hHjC]{0,2}        hour / hour cycle
m{0,2}             minute
s{0,2}             second
[vz]{0,4}          zone
~~~

This is an **ordered specification of allowed groups**, not a standalone Java regex to copy and run. Groups may be omitted; not every template contains all fields. Symbols outside this set, or in an invalid order, cause `ofLocalizedPattern` to throw `IllegalArgumentException`.

Some templates worth knowing:

| Requested template | Desired field set | Use case |
| --- | --- | --- |
| `yMd` | Numeric year, month, day | Short date with all three fields |
| `yMMM` | Year and short month name | Month/year labels in calendars, reports |
| `yMMMd` | Year, short month name, and day | Reader-friendly date |
| `yMMMMd` | Year, requested long month, day | Formatting emphasizing month name; closest match still depends on data |
| `Hm` | 24-hour clock hour and minute | Schedule tables with hour/minute |
| `jm` | Hour/minute, requesting locale's hour cycle | Natural time display per locale settings |
| `yMMMdHm` | Year, month, day, hour, and minute | Compact localized date-time |

In templates, `j` (and `C`) are special symbols tied to Unicode LDML hour cycles; you should **not** assume every ordinary pattern letter from `DateTimeFormatter.ofPattern` can be used in a template.

### Templates must follow canonical order, even though output need not

**Invalid** examples:

~~~text
dMy              // day-month-year: wrong order for a requested template
yyyy-MM-dd       // hyphens are pattern literals, not template symbols
dd/MM/yyyy       // both slashes and order are not a valid requested template
uMMdd            // ordinary pattern letter 'u' is not supported in templates
~~~

Choose `ofPattern("yyyy-MM-dd")` if the goal is to display or export data **precisely** according to a pattern with fixed separators. Do not strip `-` and switch to `ofLocalizedPattern` if the contract requires invariant output.

### What do repeated letters express?

Repeating a letter requests numeric vs. textual presentation (for example `M` vs. `MMM`). However, the method picks the **closest localized pattern per LDML**. Therefore, do not promise that `yMMMMd` will always yield a full month name in every locale and every JDK: the final choice depends on available patterns and the matching algorithm, which may not match the exact length you imagined.

If a specification demands **exact order, exact symbols, exact field widths, and exact separators**, `ofPattern` or a custom-built formatter with locale tests may be more suitable than a requested template.

## 4. Where Does Locale Decide the Result?

Create a formatter with:

~~~java
DateTimeFormatter f = DateTimeFormatter.ofLocalizedPattern("yMd");
~~~

The returned formatter initially uses the JVM's **default FORMAT locale**, not `Locale.US` by default. Therefore, so that the application is predictable and testable, attach the locale explicitly:

~~~java
DateTimeFormatter us = DateTimeFormatter
        .ofLocalizedPattern("yMd")
        .withLocale(Locale.US);

DateTimeFormatter uk = DateTimeFormatter
        .ofLocalizedPattern("yMd")
        .withLocale(Locale.UK);
~~~

These are **illustrative snippets** inside a method that has imported `java.time.format.DateTimeFormatter` and `java.util.Locale`. `DateTimeFormatter` is immutable and safe to share across threads; `withLocale` returns a new formatter without mutating the original object. Applications can cache formatters by requested template + locale when appropriate.

Do not call `Locale.setDefault` per request to change the output. Changing the default locale mutates global state and causes interference across concurrent requests.

### withLocale and localizedBy differ

`withLocale(locale)` sets the locale used for localized text and patterns. `localizedBy(locale)` can additionally apply information from Unicode locale extensions (such as calendar, numbering system, region override, and time zone) per the API contract; chaining order relative to other `with...` methods can affect the result. Use `withLocale` when the goal is to switch the formatter's locale while keeping chronology/zone controlled separately; use `localizedBy` when you intentionally want to honor those extended localization preferences.

When choosing `Locale.forLanguageTag("th-TH-u-ca-buddhist")`, passing the locale to a formatter **should not be assumed** to automatically convert all calendar fields: check whether the called API applies the chronology extension and test the specific calendar data.

## 5. Standalone Java 19+ Example and Verified Output

The example fixes date/time values for easy testing. It demonstrates the same template across two locales, month-year only, requesting hour/minute, using a fixed pattern, and invalid template cases.

Create **`LocalizedTemplateDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Locale;

public class LocalizedTemplateDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2020, 6, 16);
        LocalTime time = LocalTime.of(13, 45);

        DateTimeFormatter numeric =
                DateTimeFormatter.ofLocalizedPattern("yMd");
        DateTimeFormatter us = numeric.withLocale(Locale.US);
        DateTimeFormatter uk = numeric.withLocale(Locale.UK);

        System.out.println("US date: " + date.format(us));
        System.out.println("UK date: " + date.format(uk));

        System.out.println("US year-month: " + date.format(
                DateTimeFormatter.ofLocalizedPattern("yMMM")
                        .withLocale(Locale.US)));

        System.out.println("US time: " + time.format(
                DateTimeFormatter.ofLocalizedPattern("Hm")
                        .withLocale(Locale.US)));

        System.out.println("Fixed pattern: " + date.format(
                DateTimeFormatter.ofPattern(
                        "yyyy-MM-dd", Locale.US)));

        try {
            DateTimeFormatter.ofLocalizedPattern("dMy");
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong order: rejected");
        }

        try {
            DateTimeFormatter.ofLocalizedPattern("yyyy-MM-dd");
        } catch (IllegalArgumentException ex) {
            System.out.println("Literal separators: rejected");
        }

        try {
            date.format(DateTimeFormatter.ofLocalizedPattern("Hm")
                    .withLocale(Locale.US));
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("Time fields missing: rejected");
        }
    }
}
~~~

Compile and run with **JDK 19 or later** (tested on JDK 24):

~~~bash
javac --release 19 -encoding UTF-8 LocalizedTemplateDemo.java
java LocalizedTemplateDemo
~~~

Stdout observed on JDK 24 with the test runtime's locale data:

~~~text
US date: 6/16/2020
UK date: 16/06/2020
US year-month: Jun 2020
US time: 13:45
Fixed pattern: 2020-06-16
Wrong order: rejected
Literal separators: rejected
Time fields missing: rejected
~~~

**Important note:** The localized formatting lines (`US date`, `UK date`, `US year-month`, `US time`) are results from the **tested JDK 24**, not an invariant contract across all releases. Locale/CLDR data and providers can be updated. The `rejected` lines prove invalid-input and missing-field errors without relying on regional month/day phrasing.

### Explanation of each branch

1. `numeric` specifies `yMd`. Applying `Locale.US` and `Locale.UK` to two formatters clearly shows localized day/month ordering. **Both request the same three fields**, yet the presentation differs.
2. `yMMM` requests only month and year; the day **does not appear automatically** just because the input is a `LocalDate`.
3. `Hm` requests hour and minute, so `LocalTime(13,45)` provides sufficient fields to format.
4. `ofPattern("yyyy-MM-dd")` keeps a fixed pattern, unlike requesting the `yMd` template.
5. `"dMy"` is not in canonical template order; `"yyyy-MM-dd"` contains literals disallowed in templates. Both cases are rejected with `IllegalArgumentException`.
6. `LocalDate` has no hour/minute fields, so `date.format(formatter Hm)` fails with `UnsupportedTemporalTypeException`. This error is distinct from an **invalid template**.

The example needs no time zone because it formats `LocalDate` and `LocalTime` (which hold no offset/zone). For real-world date-times of a global instant, you must determine `ZoneId` and pick the appropriate temporal type.

## 6. Does a Requested Template Always Produce the Exact Requested Fields?

The idea of a requested template is to let Java select a localized pattern that satisfies the desired field set. However, the outcome relies on **available locale patterns and closest matching** per LDML. Do not equate "requested" with an invariant guarantee that every symbol, length, separator, or field will always match literally what you typed.

A notable case: in some locale data sets, `yMMMMd` may resolve to a format using an abbreviated month name even though the template requested multiple `M`s. Therefore, applications should test **actual output for supported locales** before finalizing UI designs, especially in narrow columns or regulated printouts.

When to use a requested template:

- Need month/year in a report period picker without the day.
- Need a date with year-month-day fields without forcing one country's order on the whole system.
- Need hour/minute in a scheduling UI where natural locale presentation is acceptable.
- Need the same set of fields across markets while letting localization data decide formatting.

When **not** to use it:

- An integration between two systems requires exactly `2020-06-16` or ISO 8601.
- A CSV/reconciliation contract requires a fixed pattern that must not change across JDK updates.
- Data requires exact digits, separators, or order for machine comparison.
- A specific language/region lacks a pattern meeting the requirements; you need an explicit policy, tests, and fallback.

For machine-exchange data, use built-in ISO formatters or protocol standards rather than using a localized template as a serialization format.

## 7. Choosing a Temporal Type Matching the Requested Fields

A formatter can output only fields supported by the temporal object (or derivable by the formatting mechanism). Common selection table:

| Data | Recommended `java.time` type | Suitable requested template |
| --- | --- | --- |
| Calendar date without time | `LocalDate` | `yMd`, `yMMM`, `yMMMd` |
| Time of day without date | `LocalTime` | `Hm`, `jm` |
| Local date and time without timezone | `LocalDateTime` | `yMMMdHm` |
| Date and time with timezone | `ZonedDateTime` | `yMMMdHm` or a template requesting zone `z` |
| Absolute instant to display in a region | `Instant` + `atZone(zoneId)` | Locale-bound formatter using `ZonedDateTime` |

Do not pass `LocalDate` directly into a formatter requesting `H`, `m`, or `z` expecting Java to default to the current time. Similarly, `LocalDateTime` has no `ZoneId`, so a template requesting a time-zone name cannot know which region the user is in.

Example when the data is an `Instant` and the user selects a timezone:

~~~java
Instant instant = Instant.parse("2020-06-16T06:45:00Z");
ZonedDateTime userTime =
        instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

DateTimeFormatter formatter = DateTimeFormatter
        .ofLocalizedPattern("yMMMdHm")
        .withLocale(Locale.forLanguageTag("vi-VN"));

String display = formatter.format(userTime);
~~~

This is an **illustrative snippet**, requiring imports for `java.time.Instant`, `java.time.ZonedDateTime`, `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, and `java.util.Locale`. Do not assert a fixed text output because locale data can vary by runtime.

**Timezone differs from locale:** `Locale.forLanguageTag("vi-VN")` describes language/region presentation; it does not decide that `ZoneId.of("Asia/Ho_Chi_Minh")` is the right time zone for every Vietnamese speaker.

## 8. 12/24-Hour Rules, Day Period, and Time Zones

For hour/minute, a template can explicitly request 24-hour clock via `H`, or locale-preferred hour cycle via `j` (and `C` in suitable LDML contexts). Example:

~~~java
DateTimeFormatter twentyFour = DateTimeFormatter
        .ofLocalizedPattern("Hm")
        .withLocale(Locale.US);

DateTimeFormatter localHourCycle = DateTimeFormatter
        .ofLocalizedPattern("jm")
        .withLocale(Locale.US);
~~~

This is a Java 19+ illustrative snippet, requiring imports for `DateTimeFormatter` and `Locale`. Time formats using the locale's hour cycle may display AM/PM and special whitespace characters depending on data. Do not write parsers that assume a fixed `"PM"` string when supporting multiple languages.

Requesting a time zone via `z` or `v` does not derive a timezone from the locale. If the input is an `Instant`, attach a `ZoneId` or use an appropriate `withZone` formatter. For textual time-zone names, rendering depends on the locale and the JDK's timezone data.

`DateTimeFormatter.ofLocalizedPattern` creates an ISO chronology formatter; if business logic requires Japanese, Buddhist, or another calendar system, evaluate the chronology and API version explicitly. Do not assume changing the language changes the calendar system.

## 9. Parsing: The Same Formatter Can Parse, Provided Fields Are Sufficient

`DateTimeFormatter` works for both **formatting** and **parsing**, with a few caveats:

- `yMd` requests a date with year/month/day and can parse into `LocalDate` when the string matches the resolved pattern.
- `yMMM` has no day of month. Using `LocalDate.parse(text, formatter yMMM)` will fail for lack of a `day-of-month` field to build a complete date. Use `YearMonth.parse(...)` when targeting month/year with an appropriate pattern.
- Localized textual patterns, such as month names, depend on locale. Parsing strings rendered in another locale can fail.
- The formatter's default resolution mode is `ResolverStyle.SMART` per the API contract. For inputs requiring strict validation, evaluate `withResolverStyle(ResolverStyle.STRICT)` alongside year/era field choices and business requirements.
- Localized patterns can change across locale data versions; therefore, do not use them as an input schema or long-term data format that external systems must parse unchanged.

Illustrative snippet:

~~~java
DateTimeFormatter f = DateTimeFormatter
        .ofLocalizedPattern("yMd")
        .withLocale(Locale.US);

LocalDate date = LocalDate.parse("6/16/2020", f);
~~~

In real applications, handle `DateTimeParseException` and test with the locale data of the JDK where the app is deployed. The `/` separator is merely an example from one runtime, not a mandated symbol of the requested template.

Do not use localized formats as database keys; store `LocalDate`, `Instant`, `OffsetDateTime`, or the corresponding canonical value, and format at the UI boundary.

## 10. What If the Product Still Runs on Java 17?

This must be checked **before choosing an architecture**. `ofLocalizedPattern` **does not exist in Java SE 17**. Source code calling this method **will not compile** when targeting Java 17, even if you have a newer JDK installed locally and run `javac --release 17`.

Options available in Java 17:

### A. Use FormatStyle-based formatting if it meets requirements

~~~java
DateTimeFormatter fullDate = DateTimeFormatter
        .ofLocalizedDate(FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"));
~~~

This snippet uses `DateTimeFormatter`, `FormatStyle`, and `Locale`, available prior to Java 19. Suitable when you only need a date/time style and **do not need an arbitrary custom field subset**.

### B. Use ofPattern if order and separators are explicitly decided

~~~java
DateTimeFormatter fixed = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", Locale.forLanguageTag("vi-VN"));
~~~

This is a concrete, easy-to-control pattern; it is **not** an equivalent multi-locale replacement for `ofLocalizedPattern("yMd")`. If using `ofPattern` per market, maintain patterns per locale and verify with native speakers.

### C. Use an internationalization library supporting skeletons/templates

If Java 17 must display **flexible field sets across many locales**, a library using Unicode CLDR/LDML data with a skeleton API (such as the ICU4J ecosystem) can solve this. External libraries are outside Java Core; verify compatible versions, licenses, and APIs, and do **not** assume a library's skeleton behaves identically to the newer JDK's `ofLocalizedPattern`.

### D. Upgrade the minimum runtime to Java 19+ when possible

If the product can upgrade Java, `ofLocalizedPattern` is a direct API for requested templates. Still test on the target JDK, as matching algorithms and locale pattern data can be updated across releases.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `ofLocalizedPattern` on Java 17 | Compilation error because the API does not exist | Require Java 19+ or use a compatible alternative |
| Passing `"dd/MM/yyyy"` to `ofLocalizedPattern` | `IllegalArgumentException` | Use `ofPattern` when fixed separators are needed |
| Passing `"dMy"` instead of `"yMd"` | Wrong canonical template order | Order symbols canonically |
| Treating a requested template as an output pattern | Wrong expectations about order, width, or separators | Treat templates as field requests and test output per locale |
| Not passing an explicit locale | Result depends on server's default FORMAT locale | Use `withLocale(locale)` |
| Expecting `yMMM` to produce full day/month/year | Missing day-of-month | Add the `d` field if day is needed |
| Formatting `LocalDate` with `Hm` | No hour/minute data | Use `LocalTime`/`LocalDateTime` |
| Formatting a timezone from `LocalDateTime` without a zone | No timezone to display | Convert to `ZonedDateTime` with the proper zone |
| Using localized text as machine exchange data | Results vary by locale/CLDR | Use ISO or a machine-readable contract |
| Mixing up `Locale` and `ZoneId` | Wrong region for actual date/time | Select the time zone separately |
| Drawing conclusions for all runtimes from one JDK's output | Regressions when upgrading locale data | Test multiple locales and verify upgrades |
| Assuming `withLocale` and `localizedBy` are always synonymous | May overlook calendar/numbering extensions | Pick the right API for your needs |

## 12. Practical Testing Matrix

For production deployment, do not test only `Locale.US`. Build tests covering:

| Test axis | Scenarios |
| --- | --- |
| Runtime | Java 19+, deployed JDK, actual locale provider/data |
| Locale | `en-US`, `en-GB`, `vi-VN`, `fr-FR`, and all actually supported locales |
| Template | `yMd`, `yMMM`, `yMMMd`, `Hm`, `jm`, templates with zone if needed |
| Temporal type | `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime` |
| Boundary data | End of month, leap year, midnight, 12:00, timezone/DST |
| Invalid data | Misordered template, disallowed literals, missing time fields |
| Compatibility | `javac --release 19` vs. `--release 17` |
| UI | Long/short strings, special whitespace, month names and field order |
| Serialization | Never use localized text in place of standard date types |

When writing assertions, separate **domain invariants** (which fields must be present, which errors must occur) from **CLDR-governed presentation** (which may change on JDK upgrades). Snapshot tests on localized strings are helpful, but when JDK/CLDR updates occur, review them as language-data changes rather than blindly updating snapshots.

## 13. Self-Check Questions

**Question 1.** You need to display month/year without day, letting each locale decide the ordering. Which API and template should you choose if the runtime is Java 21?

**Answer:** `DateTimeFormatter.ofLocalizedPattern("yMMM").withLocale(locale)` is appropriate; the input date can be `LocalDate` or `YearMonth` if the formatter needs the requested fields. Always test the actual output.

**Question 2.** Why is `ofLocalizedPattern("yMd")` not equivalent to `ofPattern("yMd")`?

**Answer:** `ofPattern` treats the letters as a **pattern printed in the exact order written**; `ofLocalizedPattern` treats them as a **requested template** to look up the closest localized format.

**Question 3.** Can you use `ofLocalizedPattern("yyyy-MM-dd")` to output dates in fixed ISO format?

**Answer:** No. The `-` character is invalid in templates. Use `DateTimeFormatter.ISO_LOCAL_DATE` (or a fixed pattern if a special protocol requires it).

**Question 4.** Why can `ofLocalizedPattern("yMMMd")` produce different month/day ordering between `Locale.US` and `Locale.UK`?

**Answer:** A requested template describes which fields are wanted, while the locale decides the closest pattern including order, month names, and separators. Template order must be canonical to be accepted by the parser, without forcing display order.

**Question 5.** If a formatter requests `Hm` time but the input is `LocalDate`, is the error caused by the locale or the input?

**Answer:** It is caused by the input lacking hour/minute fields. You must supply an appropriate `LocalTime`, `LocalDateTime`, or `ZonedDateTime`.

**Practice exercise:** Create three formatters for `yMMM`, `yMMMd`, and `jm`, and apply them to `en-US`, `en-GB`, and `vi-VN`. Compare the requested field sets, display order, separators, 12/24-hour cycles, and string lengths. Try the error cases `"dMy"`, `"yyyy-MM-dd"`, and formatting time using `LocalDate`. Finally, write a check verifying the codebase does not depend on Java 19 APIs when the project still targets Java 17.

## 14. Official Documentation

- [DateTimeFormatter — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/format/DateTimeFormatter.html): `ofLocalizedPattern(String)`, requested templates, syntax, `withLocale`, `ofPattern`, and the **Since: 19** note.
- [DateTimeFormatterBuilder — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html): `appendLocalized(String)` and formatter builder options.
- [DateTimeFormatter — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): APIs available on Java 17 runtimes such as `ofPattern` and `ofLocalizedDate`.
- [Unicode LDML Dates](https://unicode.org/reports/tr35/tr35-dates.html): foundation of localized date-time patterns and skeletons.

**Key takeaway:** `ofLocalizedPattern("yMd")` means "display **year, month, day** in the locale's natural way", not "print the literal characters `yMd`". Choose a temporal type with sufficient fields, pass the locale explicitly, test against your runtime's locale data, and remember that this API **requires Java 19 or later**.
