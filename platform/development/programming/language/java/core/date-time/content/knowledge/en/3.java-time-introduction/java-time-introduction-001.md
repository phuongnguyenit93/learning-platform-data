# The `java.time`, `java.time.temporal`, `java.time.format`, `java.time.zone`, and `java.time.chrono` Packages

## 1. Objectives and Overview Map

Java 8 introduced the **Date and Time API (JSR 310)** in the `java.base` module, largely replacing the need to use `java.util.Date`, `Calendar`, and `SimpleDateFormat` for new code. In Java 17+, the API is organized into **one main package**, `java.time`, and **four subpackages** covered in this lesson: `temporal`, `format`, `zone`, and `chrono`. They solve different classes of problems, while working together through consistent interfaces and data types.

After this lesson, you will be able to:

1. Identify which package to import when handling dates, times, durations, timezones, formatting, or non-ISO calendar systems.
2. Explain how `LocalDate`/`ZonedDateTime` use `TemporalField`, `TemporalUnit`, `TemporalAdjuster`, `DateTimeFormatter`, `ZoneRules`, and `Chronology`.
3. Read an example that combines all five packages, choose the right API for real-world problems, and handle DST edge cases and formatting errors.
4. Distinguish between a **timezone** (offset/DST rules) and a **calendar system** (how year/month/day are represented, such as ISO or Japanese).

Responsibility diagram:

```text
java.base
└── java.time                 → Date, time, instant, duration, and zone ID types
    ├── temporal              → Fields, units, queries, and temporal adjusters
    ├── format                → Parsing, formatting, locales, patterns, and resolver styles
    ├── zone                  → Offset rules, transitions, and tzdb
    └── chrono                → Non-ISO calendar systems, eras, and corresponding calendar dates
```

| Package | Answers the question | Commonly used APIs | Key distinction |
| --- | --- | --- | --- |
| `java.time` | “What kind of date/time data do I have?” | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `ZonedDateTime`, `ZoneId`, `Period`, `Duration`, `Clock` | High-level data model and operations |
| `java.time.temporal` | “Which field to read, which unit to calculate with, and what rule to adjust dates by?” | `ChronoField`, `ChronoUnit`, `TemporalAdjusters`, `WeekFields`, `TemporalQueries` | Shared field/unit/query/adjuster layer |
| `java.time.format` | “How do I parse or display a date/time string?” | `DateTimeFormatter`, `DateTimeFormatterBuilder`, `FormatStyle`, `ResolverStyle`, `TextStyle` | Parsing, formatting, localization, and validation modes |
| `java.time.zone` | “In this region, which offsets are valid for a local date-time?” | `ZoneRules`, `ZoneOffsetTransition`, `ZoneOffsetTransitionRule`, `ZoneRulesProvider` | Offset transition rules and history, gaps/overlaps |
| `java.time.chrono` | “Which calendar system represents the same date?” | `Chronology`, `ChronoLocalDate`, `JapaneseDate`, `ThaiBuddhistDate`, `HijrahDate` | Non-ISO calendars, eras, and cultural representations |

**Import note:** `import java.time.*;` does **not** import classes in `java.time.temporal`, `java.time.format`, `java.time.zone`, or `java.time.chrono`. Java only imports types directly belonging to the specified package. You must import each subpackage or specific class explicitly.

## 2. The `java.time` Package — the Core Model to Learn First

`java.time` provides data types that match the semantics of an event, rather than bundling everything into a single “date” type.

| Type | Carries information | Example use cases | Notes |
| --- | --- | --- | --- |
| `LocalDate` | Year-month-day in the ISO calendar, without time or offset | Birthdays, calendar expiration dates | Cannot determine an `Instant` from a date alone |
| `LocalTime` | Hour-minute-second-nanosecond within a day, without date or timezone | Store opening hours | `09:00` does not identify a location by itself |
| `LocalDateTime` | Local date and time | 09:30 meeting day at an office | Not enough on its own to determine a single UTC instant |
| `Instant` | An absolute point on the timeline | Transaction timestamps, logs | Usually the best choice for storing past events |
| `OffsetDateTime` | Date-time and an offset such as `+07:00` | API payloads with an offset | An offset does not contain regional DST rules |
| `ZonedDateTime` | Date-time, `ZoneId`, and resolved offset | Meetings in `Europe/Paris` | Resolved using regional rules provided by tzdb |
| `ZoneId` / `ZoneOffset` | Region ID / fixed offset from UTC | `Asia/Ho_Chi_Minh` / `+07:00` | A region's offset may change historically |
| `Duration` / `Period` | Seconds-nanoseconds amount / years-months-days amount | Timeouts / monthly deadlines | Not interchangeable when calendar semantics are required |
| `Year`, `YearMonth`, `MonthDay` | Meaningful partial date structures | Monthly reporting periods, recurring birthdays | Avoids inserting dummy days or months |
| `DayOfWeek`, `Month` | Enums for day of week and month | Weekday-only rules | Can be used with `TemporalAdjusters` |
| `Clock` | Source of current time and optional timezone | Services depending on “now” | Inject `Clock.fixed` for testing |

Pure `java.time` usage example:

```java
import java.time.LocalDate;
import java.time.Period;

LocalDate ordered = LocalDate.of(2026, 10, 24);
LocalDate delivered = ordered.plusDays(5);
Period window = Period.between(ordered, delivered);
```

This is an **illustrative snippet** meant to be placed inside a method/class, not a standalone Java file. The result `delivered` is `2026-10-29`; `window` is a 5-day period. `ordered` does not change because the API uses immutable objects. `LocalDate` uses the ISO calendar (proleptic Gregorian) and is not aware of Daylight Saving Time.

Important conversions:

```java
import java.time.*;

Instant instant = Instant.parse("2026-10-24T02:30:00Z");
ZonedDateTime hcm = instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate localCalendarDate = hcm.toLocalDate();
Instant roundTrip = hcm.toInstant();
```

Here `hcm` represents 09:30 on 2026-10-24 in Ho Chi Minh City; `roundTrip.equals(instant)` is `true`. `toLocalDate()` keeps only the **date in the selected zone**, which can differ from the UTC date of `instant`. If the input is only a `LocalDateTime`, you must know the `ZoneId` and the DST handling policy before creating an exact instant.

## 3. The `java.time.temporal` Package — Fields, Units, and Adjustment Rules

This package adds capabilities for querying/modifying temporal fields and performing general-purpose calculations. The API uses abstract interfaces; when starting out, prefer the built-in convenience classes and reach for the interfaces when you truly need generalization.

### 3.1. Foundational Interfaces

- `TemporalAccessor`: provides **read-only** access to fields via `isSupported(TemporalField)`, `get(...)`, `getLong(...)`, and `query(...)`. It does not guarantee addition or modification operations. `DayOfWeek` and several other value types can be read this way.
- `Temporal`: extends `TemporalAccessor` to support `with(field, value)` and `plus/minus(unit)`; concrete types still return new values rather than mutating in place.
- `TemporalField`: describes **a field** such as day-of-month or hour-of-day. The commonly used enum is `ChronoField`.
- `TemporalUnit`: describes **a unit** such as days, weeks, or minutes. The commonly used enum is `ChronoUnit`.
- `TemporalAmount`: an amount of time used with `plus(TemporalAmount)`, such as `Period` or `Duration`.
- `TemporalAdjuster`: a function that adjusts a temporal object according to a rule; built-in factories are in `TemporalAdjusters`.
- `TemporalQuery<R>`: a strategy for extracting information from a `TemporalAccessor`; many built-in queries are in `TemporalQueries`.

Not every type supports every field or unit: `LocalDate` does not contain `HOUR_OF_DAY`; `LocalTime` does not contain `DAY_OF_MONTH`. Check `isSupported` or use type-specific methods before querying by field. `get(...)` returns `int` and may not fit large values; use `getLong(...)` when `long` is needed.

### 3.2. Field vs. Unit

`ChronoField.DAY_OF_MONTH` is the **position of the day within the month** (1–28/29/30/31). `ChronoUnit.DAYS` is a **unit for counting duration/days in temporal types**; the two objects answer different questions.

```java
import java.time.LocalDate;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

LocalDate d = LocalDate.of(2026, 10, 24);
int day = d.get(ChronoField.DAY_OF_MONTH); // 24
LocalDate revised = d.with(ChronoField.DAY_OF_MONTH, 1); // 2026-10-01
long days = ChronoUnit.DAYS.between(d, LocalDate.of(2026, 10, 31)); // 7
```

In simple applications, `d.getDayOfMonth()`, `d.withDayOfMonth(1)`, and `d.until(end, ChronoUnit.DAYS)` are usually easier to read. `ChronoField`/`ChronoUnit` are useful when the field/unit is chosen dynamically or when code must work across multiple `Temporal` types.

### 3.3. `TemporalAdjusters` and `WeekFields`

`TemporalAdjusters` provides common rules: `firstDayOfMonth()`, `lastDayOfMonth()`, `firstDayOfNextMonth()`, `next(DayOfWeek.MONDAY)`, `nextOrSame(...)`, `firstInMonth(...)`, `lastInMonth(...)`, and `dayOfWeekInMonth(...)`.

```java
import java.time.*;
import java.time.temporal.*;

LocalDate d = LocalDate.of(2026, 10, 24);
LocalDate firstMonday =
    d.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY)); // 2026-10-05
LocalDate nextMonday =
    d.with(TemporalAdjusters.next(DayOfWeek.MONDAY)); // 2026-10-26
```

Key distinction: `next(MONDAY)` **always advances to the following Monday** even if the starting date is already a Monday; `nextOrSame(MONDAY)` keeps the date unchanged if it already falls on Monday.

`WeekFields` lets you define which day a week starts on and the minimum number of days required in the first week of the year; for example, `WeekFields.ISO` starts on Monday and requires at least 4 days in the first week. `WeekFields.of(Locale)` depends on regional conventions. **Week-of-year** can cross into a different week-based-year near January 1, so you should not treat the “week-based year” as a regular calendar year.

`IsoFields` provides advanced ISO fields such as `QUARTER_OF_YEAR`, `WEEK_OF_WEEK_BASED_YEAR`, and `WEEK_BASED_YEAR`; `JulianFields` serves Julian/modified Julian day counting systems for specialized integrations.

### 3.4. `TemporalQueries` and Missing-Field Errors

`TemporalQueries.zone()`, `offset()`, `localDate()`, `localTime()`, and `precision()` extract available information; many queries return `null` if the input does not contain the relevant data. Do not infer a timezone from a `LocalDateTime` alone.

Some calls may throw `UnsupportedTemporalTypeException`. For example, accessing `ChronoField.HOUR_OF_DAY` on a `LocalDate` makes no sense; use `isSupported(...)` as a guard when the input has an unknown type.

## 4. The `java.time.format` Package — Converting Between Objects and Text

This package contains the logic for converting between strings and date/time objects. `DateTimeFormatter` is the starting point; `DateTimeFormatterBuilder` is used to compose custom components or optional sections. Formatters can be reused because they are immutable and thread-safe.

### 4.1. Built-in Standards and Patterns

When exchanging data between systems, prefer `DateTimeFormatter.ISO_LOCAL_DATE`, `ISO_INSTANT`, `ISO_OFFSET_DATE_TIME`, or `ISO_ZONED_DATE_TIME` matching the **field semantics**, not just a string format that looks nice.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

DateTimeFormatter strict = DateTimeFormatter
    .ofPattern("dd/MM/uuuu", Locale.ROOT)
    .withResolverStyle(ResolverStyle.STRICT);

LocalDate d = LocalDate.parse("31/12/2026", strict); // 2026-12-31
String out = d.format(strict);                        // "31/12/2026"
```

This is a **snippet inside a method**, not a complete program. Given `31/02/2026`, `LocalDate.parse(..., strict)` throws `DateTimeParseException`. If you only use a formatter created with `ofPattern(...)`, the default resolver style is `SMART`; therefore, you must choose `STRICT` when all invalid dates must be rejected. `DateTimeFormatter.ISO_LOCAL_DATE` already uses strict mode according to the JDK specification.

| Pattern letter | Meaning | Common mistake |
| --- | --- | --- |
| `u` / `uuuu` | Proleptic year in the calendar | Confusing it with `y`: year-of-era |
| `M` / `MM` | Month | `mm` is minute |
| `d` / `dd` | Day of month | `D` is day of year |
| `H` / `HH` | Hour 0–23 | `h` is hour 1–12 and requires AM/PM when parsing |
| `m` / `mm` | Minute | Do not confuse with `M` |
| `s` / `ss` | Second | Do not confuse with `S`, which is fraction-of-second |
| `X` / `XXX` | UTC offset using `Z` for offset 0 | Not a zone ID |
| `V` / `VV` | Zone ID (practical patterns use `VV`) | Requires data carrying a `ZoneId` |
| `Y` / `YYYY` | Week-based-year | Can be off by a year at the end/start of a year |

Do not pair `LocalDate` with a pattern that requires hour, offset, or zone when it does not carry those fields: the formatter may throw `UnsupportedTemporalTypeException`. When an application needs to display month names in a specific language, pass `Locale` explicitly—for example `Locale.forLanguageTag("vi-VN")`—and consider `FormatStyle.SHORT/MEDIUM/LONG/FULL` via `DateTimeFormatter.ofLocalizedDate(...)`.

### 4.2. Formatter and `TemporalAccessor`

Parsing a string with `formatter.parse(text)` produces a `TemporalAccessor`, but not every string contains enough information for every type. Prefer `LocalDate.parse(text, formatter)` or `ZonedDateTime.parse(text, formatter)` when the expected type is known. You can also use `formatter.parse(text, LocalDate::from)` to obtain the exact desired type.

`ResolverStyle.STRICT` validates strictly when resolving fields into a date; `SMART` may make adjustments in certain cases; `LENIENT` accepts overflowing fields using relaxed rules. Do not confuse **validating a calendar date** with **checking whether a local time exists in a regional timezone**: the latter belongs to `java.time.zone`.

`DateTimeFormatterBuilder` is typically used when a protocol has optional sections, combines multiple fields, or needs flexible parsing modes. Do not use the builder when an ISO constant or a simple pattern suffices.

## 5. The `java.time.zone` Package — Offset Rules and DST

**`ZoneId` lives in `java.time`, while its rules live in `java.time.zone`.** A `ZoneId` usually references the timezone database (tzdb). UTC instants and local times are not synonymous; offsets can also change due to Daylight Saving Time (DST) or legal changes.

- `ZoneRules`: describes valid offsets for an instant or for a local date-time. Obtained via `zone.getRules()`.
- `ZoneOffsetTransition`: detailed information for a single offset transition, with `isGap()`, `isOverlap()`, `getOffsetBefore()`, `getOffsetAfter()`, `getDateTimeBefore()`, and `getDateTimeAfter()`.
- `ZoneOffsetTransitionRule`: a rule for generating recurring transitions (usually related to seasonal changes); this is an advanced API.
- `ZoneRulesProvider`: supplies the list of zones and rules to the runtime; usually **not called directly in business code**. Different tzdb/JDK versions may yield different historical or future rules.
- `ZoneRulesException`: an exception related to missing or unavailable zone rules.

### 5.1. Gaps and Overlaps — Distinguishing via `getValidOffsets`

When a user enters an appointment time `LocalDateTime local` in a `ZoneId zone`:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2026, 11, 1, 1, 30);
ZoneRules rules = zone.getRules();
List<ZoneOffset> offsets = rules.getValidOffsets(local);

if (offsets.isEmpty()) {
    // Gap: the local time does not exist; a handling policy is required.
} else if (offsets.size() == 2) {
    // Overlap: the same local time occurs twice.
} else {
    // Normally there is exactly one valid offset.
}
```

The snippet above targets Java 17 and assumes it runs **inside a method**; the branches only illustrate business-logic directions.

- **Gap:** On 2026-03-08, New York transitions from `-05:00` to `-04:00`, so **02:30** does not exist; `getValidOffsets(...)` returns an empty list. `local.atZone(zone)` shifts the time forward to 03:30 by default, so for critical bookings you should consider rejecting it upfront.
- **Overlap:** On 2026-11-01, New York has **01:30** twice; the list contains two offsets (`-04:00` and `-05:00`). `local.atZone(zone)` prefers the earlier offset by default; to select the second occurrence, you can call `withLaterOffsetAtOverlap()`.
- **Normal case:** the list has one offset. Once you have chosen a valid offset, `ZonedDateTime.ofStrict(local, selectedOffset, zone)` verifies consistency and rejects invalid offsets.

When `getValidOffsets(local)` returns 0 or 2, do not silently pick an arbitrary offset for financial transactions or scheduling; the selection rule must come from business requirements. `zone.getRules().getTransition(local)` returns transition details for a gap/overlap, and is normally `null` at ordinary times.

### 5.2. Absolute Instants and Display Views

A single `Instant` can be displayed in different zones:

```java
import java.time.*;

Instant event = Instant.parse("2026-07-01T12:00:00Z");
ZonedDateTime hcm = event.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
ZonedDateTime ny = event.atZone(ZoneId.of("America/New_York"));
boolean sameInstant = hcm.toInstant().equals(ny.toInstant()); // true
```

At this illustrative instant, Ho Chi Minh City is **19:00 +07:00**, and New York is **08:00 -04:00**. Do not use `ZoneOffset.of("-05:00")` in place of `America/New_York` for seasonal schedules, because a fixed offset has no transition schedule.

To convert a `ZonedDateTime` between two zones while preserving the event instant, use `withZoneSameInstant`; `withZoneSameLocal` keeps the local clock digits and **may change the actual instant**.

## 6. The `java.time.chrono` Package — Non-ISO Calendar Systems

**A chronology is a calendar system, not a timezone.** ISO 8601/Gregorian is the default calendar for most `java.time` types. Other calendar systems have their own year/era numbering and may have different calendar structures. `java.time.chrono` provides abstractions when dates must be displayed or entered according to cultural conventions.

| API | Responsibility | Notes |
| --- | --- | --- |
| `Chronology` | Identifies a calendar system; creates dates in that system | `Chronology.of(id)`, `Chronology.from(temporal)` |
| `ChronoLocalDate` | A date belonging to a chronology | Calendar-neutral interface; distinct from ISO `LocalDate` |
| `ChronoLocalDateTime<D>` | Local date-time in a chronology | Used when UI handles non-ISO calendars |
| `ChronoZonedDateTime<D>` | Zoned date-time in a chronology | Requires both calendar and timezone rules |
| `Era` / `ChronoPeriod` | Era / period in the selected calendar | Do not mix periods from different chronologies |
| `IsoChronology` | Default ISO system | `IsoChronology.INSTANCE` |
| `JapaneseChronology` / `JapaneseDate` | Japanese calendar with eras | For example, the Reiwa era |
| `ThaiBuddhistChronology` / `ThaiBuddhistDate` | Thai Buddhist calendar | Different year numbering from ISO |
| `MinguoChronology` / `MinguoDate` | Minguo calendar | Different year numbering |
| `HijrahChronology` / `HijrahDate` | Hijrah calendar system | Be aware of range limits and calendar data versions |

Example working with the same **date** in two calendars:

```java
import java.time.LocalDate;
import java.time.chrono.JapaneseDate;
import java.time.chrono.JapaneseChronology;

LocalDate iso = LocalDate.of(2026, 10, 24);
JapaneseDate jp = JapaneseDate.from(iso);
LocalDate sameIsoDay = LocalDate.from(jp);
String chronologyId = JapaneseChronology.INSTANCE.getId(); // "Japanese"
```

`jp` represents the date in the Japanese system with its corresponding era; `sameIsoDay` is still `2026-10-24`. Here `JapaneseDate` and `LocalDate` refer to **the same calendar day**, unrelated to changing hours or offsets.

Design note from the JDK documentation: use ISO types (`LocalDate`, `Instant`, etc.) for your core domain model, storage boundaries, and network transport **whenever possible**; use `chrono` mainly when local calendar input or display is required. Using `ChronoLocalDate` as a general type across the business layer increases complexity and can lead to incorrect operations or comparisons when chronologies are mixed. Do not assume the Hijrah calendar produces identical results across all runtimes or data sets; verify support and valid date ranges for the specific calendar system.

**Distinguishing by example:** “A meeting in Tokyo at 09:00 in `Asia/Tokyo`” is a **`zone`** concern; “Displaying that date in the Reiwa era” is a **`chrono`** concern; “Formatting it as a Japanese string” is a **`format`** concern. An application can use all three independently.

## 7. A Java 17+ Program Combining All Five Packages

Create a file named **`TimePackagesDemo.java`**. The code below runs standalone and exercises core date types, adjusters/units, strict parsing, zone rules, and chronology in sequence:

```java
import java.time.*;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.time.temporal.TemporalAdjusters;
import java.time.zone.ZoneRules;
import java.util.Locale;

public class TimePackagesDemo {
    public static void main(String[] args) {
        LocalDate base = LocalDate.of(2026, 10, 24);
        LocalDate firstMonday =
                base.with(TemporalAdjusters.firstInMonth(DayOfWeek.MONDAY));
        long remaining = ChronoUnit.DAYS.between(base, LocalDate.of(2026, 10, 31));

        DateTimeFormatter strictDate = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        LocalDate parsed = LocalDate.parse("31/12/2026", strictDate);

        ZoneId ny = ZoneId.of("America/New_York");
        ZoneRules rules = ny.getRules();
        LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);

        JapaneseDate japanese = JapaneseDate.from(base);

        System.out.println("Ngay goc: " + base);
        System.out.println("Thu hai dau thang: " + firstMonday);
        System.out.println("So ngay den cuoi thang: " + remaining);
        System.out.println("Parse: " + parsed);
        System.out.println("Offset hop le (gap): " + rules.getValidOffsets(gap).size());
        System.out.println("Offset hop le (overlap): " +
                rules.getValidOffsets(overlap).size());
        System.out.println("Chronology: " + JapaneseChronology.INSTANCE.getId());
        System.out.println("Ngay ISO tu JapaneseDate: " + LocalDate.from(japanese));
    }
}
```

Run it in the directory containing the file with JDK 17 or later:

```bash
javac -encoding UTF-8 TimePackagesDemo.java
java TimePackagesDemo
```

Corresponding stdout for the example (New York zone rules match tzdb data for 2026):

```text
Ngay goc: 2026-10-24
Thu hai dau thang: 2026-10-05
So ngay den cuoi thang: 7
Parse: 2026-12-31
Offset hop le (gap): 0
Offset hop le (overlap): 2
Chronology: Japanese
Ngay ISO tu JapaneseDate: 2026-10-24
```

**Line-by-line explanation:**

1. `LocalDate.of(...)` belongs to **`java.time`** and creates an ISO date. `2026-10-24` remains unchanged; `with` returns a new date for the first Monday of the month.
2. `TemporalAdjusters.firstInMonth(...)` and `ChronoUnit.DAYS.between(...)` belong to **`java.time.temporal`**. The first Monday of October 2026 is October 5; from the 24th to the 31st is 7 days.
3. `DateTimeFormatter` and `ResolverStyle.STRICT` belong to **`java.time.format`**. The Vietnamese-style string `31/12/2026` is parsed into a `LocalDate` and printed in default ISO format as `2026-12-31`.
4. `ZoneRules` belongs to **`java.time.zone`**; `ZoneId` and `LocalDateTime` belong to **`java.time`**. The March DST transition has 0 valid offsets; the November repeated hour has 2.
5. `JapaneseDate` and `JapaneseChronology` belong to **`java.time.chrono`**. Converting from ISO to the Japanese calendar does not change the actual day; converting back to `LocalDate` yields the original date.

Ways to experiment: change `base` to `2026-02-28` and compare the adjuster and day count; change `ny` to `Asia/Ho_Chi_Minh` and observe `getValidOffsets` at the two sample times—for normal valid times in Ho Chi Minh City the result is 1; add `LocalDate.parse("31/02/2026", strictDate)` and catch `DateTimeParseException`.

## 8. How the Packages Work Together in Real-World Design

### 8.1. Accepting Scheduled Appointments from Users

For example, an organizer picks `01/11/2026 01:30` in New York (an overlapping hour). The flow should be unambiguous:

1. **`format`:** parse the date and time string into a `LocalDateTime` using the appropriate pattern, locale, and resolver style.
2. **`time`:** obtain `ZoneId.of("America/New_York")` from the organizer's actual location or selection; do not infer the zone from the UI language.
3. **`zone`:** query `zone.getRules().getValidOffsets(local)`. If 0, report that the time does not exist; if 2, ask the user to choose the first or second occurrence; if 1, use the single offset.
4. **`time`:** convert to an `Instant` to store a single meeting timestamp; when displaying it to attendees, apply their respective zones.
5. **`temporal`:** when computing actual elapsed duration, use `Duration.between(startInstant, endInstant)` or `ChronoUnit.MINUTES.between(...)` on the two instants. When you need “first Monday of the month,” use `TemporalAdjusters` on the appropriate calendar date.
6. **`chrono` (if needed):** format the same date in the Japanese or Thai calendar at the UI layer; do not alter the meaning of the stored `Instant`.

In systems with recurring schedules (“every Monday at 09:00 in New York”), store **the local-time rule, `ZoneId`, and recurrence rule**; a single UTC timestamp cannot represent all future occurrences because winter/summer offsets may differ. When storing audit/tracking events, prefer `Instant` or a timestamp with an explicit offset.

### 8.2. API Response Payloads

- Absolute events: ISO strings with `Z` or an offset, such as `2026-10-24T02:30:00Z`; map to `Instant` in Java.
- Timezone-independent dates: `2026-10-24`; map to `LocalDate`.
- Local appointment times: require both a local date-time string and an **IANA zone ID**, such as `2026-11-01T01:30:00` + `America/New_York`; for overlaps, include an offset choice or explicit disambiguation input.
- When using SQL/JDBC/ORM, verify driver/database behavior: `TIMESTAMP WITH TIME ZONE` in many databases does not preserve the exact `ZoneId` name supplied, so store the zone separately if business logic requires it.

### 8.3. Testing Along Package Boundaries

| Package | Useful tests |
| --- | --- |
| `time` | Month-end, Feb 29, year boundaries, `Period` vs. `Duration`; use `Clock.fixed` when reading “now” |
| `temporal` | First/last day of month, `next` vs. `nextOrSame`, week-based-year near year-start |
| `format` | Valid/invalid dates, ISO formats, strict patterns, locales, `MM` vs. `mm` |
| `zone` | Gap on 2026-03-08 and overlap on 2026-11-01 in New York; controlled timezone rules/JDK in test environments |
| `chrono` | ISO ↔ Japanese/ThaiBuddhist round trips, eras, and date boundaries supported by the calendar system |

Tests involving `now()` must use an injected time source (`Clock.fixed(...)`), not the CI system clock or `ZoneId.systemDefault()`. Test values should attach an explicit `ZoneId`. Because tzdb can be updated across JDK versions, future DST schedule results depend on the active rules.

## 9. Rules for Choosing a Package by Need and Common Mistakes

| Need | Start with | Sign of a wrong choice |
| --- | --- | --- |
| Compute a deadline 3 calendar days later | `java.time.LocalDate.plusDays` | Adding milliseconds or `Duration` to an arbitrary timestamp |
| Measure elapsed time of a task | `java.time.Instant` + `Duration` | Subtracting local times across a DST transition |
| Find the first Monday of the month | `java.time.temporal.TemporalAdjusters` | Writing custom loops over days of the week |
| Parse dates formatted as `dd/MM/uuuu` | `java.time.format.DateTimeFormatter` | Using `SimpleDateFormat` shared across threads |
| Detect that 02:30 does not exist | `java.time.zone.ZoneRules` | Assuming every `LocalDateTime` has a unique offset |
| Display dates in the Japanese calendar | `java.time.chrono.JapaneseDate` | Thinking changing `ZoneId` changes the calendar system |
| Translate month names by language | `java.time.format` + `Locale` | Using `Chronology` to localize text |
| Send a meeting invite across regions | `Instant` + `ZoneId` | Storing a time string without a zone or offset |

**Mistakes to remember:**

- Confusing **`temporal` with `chrono`**: `ChronoUnit` and `ChronoField` **live in `java.time.temporal`** even though their names start with “Chrono”; `Chronology` and `ChronoLocalDate` belong to `java.time.chrono`.
- Confusing **`ZoneId` with `ZoneRules`**: `ZoneId` is in `java.time`; `ZoneRules` is in `java.time.zone`. Application users usually pick a `ZoneId`, and business code queries `ZoneRules` when validation is needed.
- Confusing **a zone with an offset**: `America/New_York` has changing rules; `-05:00` is a fixed offset.
- Confusing **a calendar with a timezone**: converting to `JapaneseDate` does not shift the UTC instant; converting an `Instant` to a zone does not change the default chronology.
- Calling `LocalDateTime.now()` in business logic or tests without specifying a zone; the result depends on the system timezone, making tests hard to reproduce.
- Using the `YYYY-MM-dd` pattern for regular calendar dates; `YYYY` is the **week-based year**, not the calendar year. Use `uuuu-MM-dd` or a standard ISO formatter.
- Calling `date.plusDays(1)` without assigning the result; `java.time` objects are immutable.
- Using `ChronoUnit.DAYS` on an unsupported temporal or expecting calendar days for quantities measured in seconds; check the input type and business intent.
- Using `ChronoLocalDate` across the entire domain when non-ISO calendars are not required; this makes storage APIs and consistency checks unnecessarily complex.
- Importing `java.time.*` and expecting classes from the four subpackages to be available; import them explicitly.

## 10. Practice Exercises and Completion Criteria

**Exercise 1 — Identify packages:** Determine the package for `LocalDate`, `ChronoUnit`, `DateTimeFormatter`, `ZoneRules`, and `JapaneseChronology`. Answers in order: `time`, `temporal`, `format`, `zone`, `chrono`. Explain why `ChronoUnit` is not in `chrono`.

**Exercise 2 — Working days:** Given `LocalDate.of(2026, 10, 24)`, find `TemporalAdjusters.next(DayOfWeek.MONDAY)` and `firstDayOfNextMonth()`. The results must be **2026-10-26** and **2026-11-01**. Prove that the original date is unchanged.

**Exercise 3 — Strict parsing:** Parse `29/02/2028` successfully and make `29/02/2026` fail using pattern `dd/MM/uuuu` + `ResolverStyle.STRICT`. Distinguish syntax errors from invalid calendar dates, and catch `DateTimeParseException` at the input boundary.

**Exercise 4 — DST:** Query `ZoneRules.getValidOffsets(...)` for New York at `2026-03-08 02:30` and `2026-11-01 01:30`. Write a function that returns `GAP`, `NORMAL`, or `OVERLAP` based on the offset count; do not pick an offset automatically on overlap.

**Exercise 5 — Chronology conversion:** Create `JapaneseDate.from(LocalDate.of(2026, 10, 24))`, read `JapaneseChronology.INSTANCE.getId()`, convert back to `LocalDate`, and assert the same ISO date. Explain why this is not a timezone conversion.

**Exercise 6 — Application design:** A user schedules an appointment using a `dd/MM/uuuu HH:mm` string, a `ZoneId`, and an offset preference for overlaps. Outline the steps: parse → verify `ZoneRules` → determine `ZonedDateTime` → store `Instant` → display per viewer zone; use `chrono` only if the UI requires a non-ISO calendar.

**You have mastered this lesson when** you can redraw the five-package diagram, choose the right package for all six exercises, run the full example with the expected output, and explain the differences among **field/unit**, **format**, **zone rules**, and **chronology**.

## Official JDK 17 Documentation

- [`java.time`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [`java.time.temporal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/package-summary.html)
- [`java.time.format`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/package-summary.html)
- [`java.time.zone`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/package-summary.html)
- [`java.time.chrono`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/chrono/package-summary.html)
