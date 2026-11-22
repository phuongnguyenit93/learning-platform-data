# Testing Year–Week, Calendar, and Time-Zone Boundaries in Java

A date-time feature can work smoothly most of the year yet fail precisely on the night of December 31, on January 1, on leap day February 29, or when the OS transitions to Daylight Saving Time (DST). These bugs easily slip past test suites that use ordinary dates, call `LocalDate.now()` and `ZoneId.systemDefault()`, or confuse **calendar year** with **week-based year**.

This Knowledge lesson belongs to **Testing and Pitfalls** in **Java core - localization**. Its goal is to build a Java 17+ test suite that accurately catches bugs at three related yet distinct boundaries:

1. **Calendar year and week-based year**: `2021-01-01` belongs to **calendar year 2021** yet falls in **ISO week 53 of week-based year 2020**.
2. **Calendar dates and month/leap-year rules**: `2024-02-29` is valid, `2023-02-29` is invalid; `STRICT` resolution can differ from `SMART`.
3. **Time zones, DST, and instants**: a local time may **not exist** or may **occur twice**, and a calendar day does not have to be exactly 24 hours long.

All examples use **Java 17+**. The programs use only the standard library—no JUnit or network dependencies—with dedicated `javac`/`java` commands. For cases that vary with tzdb or locale data, this lesson specifies a versioned testing policy rather than treating a localized format snapshot as permanent.

## 1. Choosing the Right Temporal Type Before Writing Tests

| Java type | Representation | Business example | Has zone/offset? |
| --- | --- | --- | --- |
| `LocalDate` | ISO calendar date | Birth date, date-based deadline | No |
| `LocalTime` | Local time without date | Daily opening hours | No |
| `LocalDateTime` | Local date and time | 09:00 appointment on a local calendar | No |
| `Instant` | A point on the UTC timeline | Payment timestamp, audit timestamp | UTC timeline; carries no viewer zone |
| `OffsetDateTime` | Date-time with a specific offset | Payload `2024-10-27T02:30+02:00` | Has offset, lacks full zone rules |
| `ZonedDateTime` | Date-time, zone, and resolved offset | Schedule in `Europe/Berlin` | Has `ZoneId` and offset |
| `YearWeek` | **Not a built-in Java SE 17 type** | Year and ISO week number | Must model explicitly or query `WeekFields` |

Two `LocalDate` instances on two machines share the same year-month-day when constructed from identical components. However, parameterless `LocalDate.now()` uses the default clock and zone, so the **same instant** on two machines can yield **different dates**. For deterministic tests, avoid calling `now()` directly or supply `Clock.fixed(...)`.

Never convert a zone-less date into an instant by arbitrarily picking 00:00 UTC if the business meaning is a calendar date in another region. Conversely, never store an offset-less local datetime string as a global audit timestamp.

## 2. Three Concepts Commonly Confused at Year Start and Year End

The **calendar year** of a `LocalDate` is retrieved via `getYear()` or `ChronoField.YEAR`.

The **week-based year** is defined by two rules: **first day of the week** and **minimum days in the first week of the year**. Under ISO-8601:

- Weeks start on **Monday**.
- The first week of the year must contain **at least four days of the new year**.
- Every week has **seven days**.
- An ISO week can begin in December of the previous year or extend into early January of the next year.
- A week-based year has **52 or 53 weeks**; never apply modulo 52 blindly.

**Week number within the calendar year** (`weekOfYear`) and **week of the week-based year** (`weekOfWeekBasedYear`) are not synonymous either. Under `WeekFields` rules, `weekOfYear` can be **0** on days before the first week of the calendar year; `weekOfWeekBasedYear` belongs to a specific week-based year. For ISO year-week reports, use the **pair** `weekBasedYear` + `weekOfWeekBasedYear`, never combining `date.getYear()` with the week-based week number.

### Boundary Dates That Must Be in Your Tests

| Gregorian/ISO date | Calendar year | ISO week-year | ISO week | ISO day of week |
| --- | ---: | ---: | ---: | --- |
| `2018-12-31` | 2018 | 2019 | 01 | 1 (Monday) |
| `2020-12-31` | 2020 | 2020 | 53 | 4 (Thursday) |
| `2021-01-01` | 2021 | 2020 | 53 | 5 (Friday) |
| `2022-01-01` | 2022 | 2021 | 52 | 6 (Saturday) |
| `2023-01-01` | 2023 | 2022 | 52 | 7 (Sunday) |

These values follow **ISO rules**, not week conventions for every locale. Locales whose week starts on Sunday with different first-week criteria produce different results on boundary dates. In your test suite, document explicitly whether you are testing ISO or `WeekFields.of(locale)`.

## 3. Program 1: Testing ISO Weeks at Year Boundaries

Create **`IsoWeekBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.temporal.WeekFields;

public class IsoWeekBoundaryDemo {
    public static void main(String[] args) {
        LocalDate[] dates = {
                LocalDate.of(2018, 12, 31),
                LocalDate.of(2020, 12, 31),
                LocalDate.of(2021, 1, 1),
                LocalDate.of(2022, 1, 1)
        };

        for (LocalDate date : dates) {
            int year = date.get(WeekFields.ISO.weekBasedYear());
            int week = date.get(
                    WeekFields.ISO.weekOfWeekBasedYear());
            String isoWeekDate = DateTimeFormatter
                    .ISO_WEEK_DATE.format(date);

            System.out.println(date
                    + ": calendar=" + date.getYear()
                    + ", weekYear=" + year
                    + ", week=" + week
                    + ", ISO=" + isoWeekDate);
        }
    }
}
```

```bash
javac -encoding UTF-8 IsoWeekBoundaryDemo.java
java IsoWeekBoundaryDemo
```

Stdout:

```text
2018-12-31: calendar=2018, weekYear=2019, week=1, ISO=2019-W01-1
2020-12-31: calendar=2020, weekYear=2020, week=53, ISO=2020-W53-4
2021-01-01: calendar=2021, weekYear=2020, week=53, ISO=2020-W53-5
2022-01-01: calendar=2022, weekYear=2021, week=52, ISO=2021-W52-6
```

**What this program proves:**

1. `date.getYear()` is the calendar year, while `weekBasedYear()` can differ.
2. `ISO_WEEK_DATE` records the **week-based year, week number, and weekday** per ISO, rather than concatenating `getYear()` with week number.
3. Week `2019-W01` already began on December 31, 2018.
4. `2021-01-01` belongs to `2020-W53`; analytics code computing `getYear() + "-W" + week` would wrongly record `2021-W53`.

**When persisting data:** if business logic actually tracks ISO week periods, store **(weekBasedYear, weekOfWeekBasedYear)** or a parsed/validated ISO week-date. Never store `weekNumber` alone because it does not uniquely identify a time span.

## 4. WeekFields.ISO Differs from Locale-Based WeekFields

`WeekFields.ISO` fixes Monday and at least four days for the first week. `WeekFields.of(Locale.US)` can use Sunday and one minimal day per runtime locale data; other regions apply different rules.

`WeekFields.SUNDAY_START` is a **fixed** rule set (Sunday, minimum one day). It is handy for writing illustrative tests independent of JDK locale data.

**`WeekRuleComparisonDemo.java`**:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.temporal.WeekFields;

public class WeekRuleComparisonDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        WeekFields iso = WeekFields.ISO;
        WeekFields sunday = WeekFields.SUNDAY_START;

        System.out.println("ISO start: "
                + iso.getFirstDayOfWeek());
        System.out.println("ISO minimal: "
                + iso.getMinimalDaysInFirstWeek());
        System.out.println("Sunday start: "
                + sunday.getFirstDayOfWeek());
        System.out.println("Sunday minimal: "
                + sunday.getMinimalDaysInFirstWeek());

        System.out.println("ISO year/week: "
                + date.get(iso.weekBasedYear()) + "/"
                + date.get(iso.weekOfWeekBasedYear()));
        System.out.println("Sunday year/week: "
                + date.get(sunday.weekBasedYear()) + "/"
                + date.get(sunday.weekOfWeekBasedYear()));
    }
}
```

```bash
javac -encoding UTF-8 WeekRuleComparisonDemo.java
java WeekRuleComparisonDemo
```

Stdout:

```text
ISO start: MONDAY
ISO minimal: 4
Sunday start: SUNDAY
Sunday minimal: 1
ISO year/week: 2020/53
Sunday year/week: 2021/1
```

Neither result is inherently "wrong": they answer **two different week definitions**. The right answer depends on requirements: ISO reports use `WeekFields.ISO`, while regional calendars use `WeekFields.of(userLocale)` and must be tested against the target JDK/provider data.

When building cache keys for weeks, **do not use the server's default locale** to compute the week if the schema specifies ISO. If an enterprise uses a custom weekly calendar (e.g., weeks starting Sunday with at least four days), construct `WeekFields.of(DayOfWeek.SUNDAY, 4)` and test it explicitly.

## 5. Pattern Traps: yyyy, uuuu, and YYYY

In `DateTimeFormatter`:

| Pattern | Meaning | Usage context |
| --- | --- | --- |
| `uuuu` | Proleptic calendar year | ISO `LocalDate`, `STRICT` parsing |
| `yyyy` | Year-of-era | Year within an era; `STRICT` parsing requires era handling |
| `YYYY` | Localized week-based-year | Week-year per locale rules; can differ from calendar year |
| `MM` | Month | Not minute |
| `mm` | Minute | Not month |
| `dd` | Day of month | Not day of year |
| `DD` | Day of year | Not day of month |
| `ww` | Week of week-based-year | Must pair with the right week-based year and weekday |

**Common bug:** copying `YYYY-MM-dd` to store ISO dates. Around year boundaries, `YYYY` can carry the **week-based** year while `MM-dd` holds the calendar month and day—producing a self-contradictory string. Use `DateTimeFormatter.ISO_LOCAL_DATE` for machine-readable ISO dates, or `"uuuu-MM-dd"` with an appropriate resolver.

`DateTimeFormatter.ofPattern("YYYY", locale)` formats the **localized week-based year**, not guaranteed to match ISO in every locale. For data needing ISO weeks, prefer `DateTimeFormatter.ISO_WEEK_DATE` or `WeekFields.ISO` fields; for user-facing UIs, localized formatters may be used, tested with the specific locale/provider.

### Program 3: Calendar Year vs. Week-Based Year

**`PatternYearBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class PatternYearBoundaryDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2021, 1, 1);
        DateTimeFormatter calendar = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);

        System.out.println("Calendar: "
                + calendar.format(date));
        System.out.println("ISO week: "
                + DateTimeFormatter.ISO_WEEK_DATE.format(date));

        System.out.println("yyyy year-of-era: "
                + DateTimeFormatter
                        .ofPattern("yyyy", Locale.ROOT)
                        .format(date));
    }
}
```

```bash
javac -encoding UTF-8 PatternYearBoundaryDemo.java
java PatternYearBoundaryDemo
```

Stdout:

```text
Calendar: 2021-01-01
ISO week: 2020-W53-5
yyyy year-of-era: 2021
```

Here `yyyy` and `uuuu` both print `2021` because the date falls in the modern era; they are **not strictly interchangeable** under strict parsing or for years outside the Common Era. Never replace `yyyy` with `YYYY` mistaking uppercase for "four-digit year."

## 6. Testing Across Multiple Years Instead of a Single January 1

Do not assume every year has the same number of weeks. Some ISO years have 53 weeks and others 52; how weeks span into the next year must be checked in both directions. To catch regressions, build a dataset covering:

- Dec 28–31 of the preceding year.
- Jan 1–4 of the following year.
- The last/first Monday of the year.
- Leap years and common years.
- 53-week ISO years (such as 2020) and 52-week ISO years (such as 2021).
- Other week rules if the application supports region-specific calendars.

In logic tests, check **invariants**, not just formatted strings: consecutive days within a week share the same `weekBasedYear` + `weekOfWeekBasedYear` pair; every week has seven days; `DateTimeFormatter.ISO_WEEK_DATE` round-trips cleanly across supported ranges.

### Round-Trip Testing Without Confusing Formats

When the source is already an ISO week-date, `LocalDate.parse(weekText, DateTimeFormatter.ISO_WEEK_DATE)` converts back to an ISO calendar date. Never parse `2020-W53-5` with `ISO_LOCAL_DATE` because those are **two different data formats**, not two spellings of the same date string for a parser to guess.

## 7. Leap Days, Month Ends, and Calendar Years

In the proleptic Gregorian ISO calendar, a **leap year** has February 29. Basic rule: divisible by 4, except years divisible by 100 that are not divisible by 400.

| Case | Result |
| --- | --- |
| `2024-02-29` | Valid |
| `2023-02-29` | Invalid |
| `2000-02-29` | Valid (divisible by 400) |
| `1900-02-29` | Invalid (divisible by 100, not by 400) |
| `2024-04-31` | Invalid, April has 30 days |
| `2024-12-31.plusDays(1)` | `2025-01-01` |

**`LocalDate.of(2023,2,29)` throws `DateTimeException`** instead of returning `null`. That differs from parsing text with a formatter using `ResolverStyle.SMART`, which may clamp certain out-of-range days at month end to the last valid day.

### Program 4: Leap Days and Year Rollover

**`LeapBoundaryDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDate;

public class LeapBoundaryDemo {
    public static void main(String[] args) {
        LocalDate leap = LocalDate.of(2024, 2, 29);

        System.out.println("Leap: " + leap);
        System.out.println("Next day: " + leap.plusDays(1));
        System.out.println("Year end: "
                + LocalDate.of(2024, 12, 31).plusDays(1));
        System.out.println("2024 leap: "
                + java.time.Year.isLeap(2024));
        System.out.println("1900 leap: "
                + java.time.Year.isLeap(1900));
        System.out.println("2000 leap: "
                + java.time.Year.isLeap(2000));

        try {
            LocalDate.of(2023, 2, 29);
            System.out.println("Unexpected acceptance");
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected");
        }
    }
}
```

```bash
javac -encoding UTF-8 LeapBoundaryDemo.java
java LeapBoundaryDemo
```

Stdout:

```text
Leap: 2024-02-29
Next day: 2024-03-01
Year end: 2025-01-01
2024 leap: true
1900 leap: false
2000 leap: true
Invalid date rejected
```

Do not use legacy `new Date(year, month, day)` (deprecated constructor and 0-based months) in new tests. `java.time.LocalDate` expresses calendar-date semantics clearly and fails fast on invalid inputs.

## 8. ResolverStyle: SMART Is Not STRICT

A critical class of bugs occurs when a parser **accepts invalid date strings** and quietly adjusts them without notifying the caller. `DateTimeFormatter.ofPattern(...)` defaults to `ResolverStyle.SMART`; `DateTimeFormatter.ISO_LOCAL_DATE` uses `STRICT`.

For `2023-02-29`:

- `SMART` can resolve it to `2023-02-28`.
- `STRICT` rejects it because February 29 does not exist in 2023.
- `LENIENT` applies relaxed field overflow arithmetic; avoid it for machine-readable contracts that forbid silent adjustment.

**Important regarding year symbols:** `yyyy` is *year-of-era*, whereas `uuuu` is proleptic year. Under `STRICT` without an era field, `"yyyy-MM-dd"` can fail to resolve to `LocalDate` even for valid dates. Therefore, for strict ISO year parsing, use `uuuu-MM-dd` or `ISO_LOCAL_DATE`.

### Program 5: SMART vs. STRICT

**`ResolverBoundaryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverBoundaryDemo {
    public static void main(String[] args) {
        String invalid = "2023-02-29";

        DateTimeFormatter smart = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);
        DateTimeFormatter strict = smart.withResolverStyle(
                ResolverStyle.STRICT);

        System.out.println("SMART: "
                + LocalDate.parse(invalid, smart));

        try {
            LocalDate.parse(invalid, strict);
            System.out.println("Unexpected strict acceptance");
        } catch (DateTimeParseException ex) {
            System.out.println("STRICT: rejected");
        }

        System.out.println("Valid leap day: "
                + LocalDate.parse("2024-02-29", strict));
    }
}
```

```bash
javac -encoding UTF-8 ResolverBoundaryDemo.java
java ResolverBoundaryDemo
```

Stdout:

```text
SMART: 2023-02-28
STRICT: rejected
Valid leap day: 2024-02-29
```

**Safe testing:** for API payloads, financial schedules, and data requiring accuracy, decide explicitly whether clamping invalid dates is permitted. Usually you should **reject** bad input with a validation error rather than silently adjusting it.

## 9. ZoneId, ZoneOffset, Instant, and Local Datetime

These four concepts require separate tests:

| Concept | Example | Meaning |
| --- | --- | --- |
| `Instant` | `2024-01-01T00:30:00Z` | An absolute point in time |
| `ZoneOffset` | `+07:00` | Offset from UTC at a given moment |
| `ZoneId` | `Europe/Berlin` | Regional rules, whose offset can change over time |
| `LocalDateTime` | `2024-10-27T02:30` | Local wall-clock time; not yet anchored to an instant |

`ZoneId.of("Asia/Ho_Chi_Minh")` is not equivalent to `ZoneOffset.ofHours(7)` for **all historical moments**: `ZoneId` carries tzdb regional rules, whereas a fixed offset cannot represent historical changes or DST transitions of another zone.

**A single `Instant` can map to two different calendar dates in two zones.** Thus, if a system filters "today's transactions" for a user, compute the date in **`userZone`** and derive the time bounds for that day; never take the UTC date and assume it is the same calendar date in every country.

### Program 6: Same Instant, Two Calendar Dates

**`ZoneCalendarBoundaryDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class ZoneCalendarBoundaryDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse(
                "2024-01-01T00:30:00Z");
        ZoneId losAngeles = ZoneId.of("America/Los_Angeles");
        ZoneId tokyo = ZoneId.of("Asia/Tokyo");

        System.out.println("UTC date: "
                + instant.atZone(ZoneOffset.UTC).toLocalDate());
        System.out.println("LA date: "
                + instant.atZone(losAngeles).toLocalDate());
        System.out.println("Tokyo date: "
                + instant.atZone(tokyo).toLocalDate());
        System.out.println("Same instant: "
                + instant.equals(
                        instant.atZone(losAngeles).toInstant()));
    }
}
```

```bash
javac -encoding UTF-8 ZoneCalendarBoundaryDemo.java
java ZoneCalendarBoundaryDemo
```

Stdout under standard tzdb historical rules:

```text
UTC date: 2024-01-01
LA date: 2023-12-31
Tokyo date: 2024-01-01
Same instant: true
```

This test **never calls `ZoneId.systemDefault()`** and does not use the current wall-clock time; results are reproducible across machines with matching tzdb. For systems needing multi-year reproducibility, log the tzdb version in CI and integration tests.

## 10. DST Gap: A Local Time That Does Not Exist

In `Europe/Berlin` on **2024-03-31**, clocks spring forward from 02:00 to 03:00. Hence local time **2024-03-31T02:30** has no valid offset in this zone: it is a **gap**.

`LocalDateTime.of(2024,3,31,2,30)` still **constructs cleanly**: the object holds date-time fields with no zone rules. When calling `atZone(berlin)`, however, `ZonedDateTime` defaults to shifting the local time forward past the gap to form a valid instant, turning 02:30 into 03:30 at offset `+02:00`.

**Do not assume the default adjustment is the right business policy.** A medical booking system might need to **reject nonexistent times** and ask the user to pick another slot, rather than silently moving the appointment forward one hour.

### Program 7: Observing a DST Gap

File **`DstGapDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class DstGapDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime input = LocalDateTime.of(
                2024, 3, 31, 2, 30);
        ZoneRules rules = berlin.getRules();

        System.out.println("Valid offsets: "
                + rules.getValidOffsets(input).size());
        System.out.println("Gap: "
                + rules.getTransition(input).isGap());

        ZonedDateTime resolved = input.atZone(berlin);
        System.out.println("Resolved local: "
                + resolved.toLocalDateTime());
        System.out.println("Resolved offset: "
                + resolved.getOffset());
    }
}
```

```bash
javac -encoding UTF-8 DstGapDemo.java
java DstGapDemo
```

Stdout per 2024 Berlin tzdb rules:

```text
Valid offsets: 0
Gap: true
Resolved local: 2024-03-31T03:30
Resolved offset: +02:00
```

**Why:** `ZoneRules.getValidOffsets(localDateTime)` returns a list containing **0**, **1**, or **2** offsets. Inside a gap, it returns 0 offsets; `getTransition` provides the transition when one applies. For an ordinary non-transition time, `getTransition(...)` normally returns `null` — never call `isGap()` without a null check in general-purpose code.

### Defining a Gap-Handling Policy

Pick one product-documented rule:

- **Reject:** refuse nonexistent local times.
- **Shift forward:** move to the next valid time after the gap under an explicit rule, such as `atZone`'s default behavior.
- **Use explicit instant/offset:** only when the source already specified a concrete instant; never fabricate offsets for ambiguous data.

For user-chosen appointments, rejecting is usually easier to explain than silent shifting. For recurring scheduled jobs, define clearly what happens when a run falls in a gap: skip, shift, or run on elapsed intervals.

## 11. DST Overlap: One Local Time with Two Instants

In `Europe/Berlin` on **2024-10-27**, clocks fall back from 03:00 summer time to 02:00 winter time. Local time **2024-10-27T02:30** occurs **twice**:

- With offset `+02:00`, corresponding to instant `2024-10-27T00:30:00Z`.
- With offset `+01:00`, corresponding to instant `2024-10-27T01:30:00Z`.

Storing only `LocalDateTime` makes it **impossible to distinguish** the two 02:30 occurrences. `ZonedDateTime.ofLocal` or `LocalDateTime.atZone` defaults to the **earlier offset across the transition** during an overlap (`+02:00` here); `withLaterOffsetAtOverlap()` selects the later offset.

### Program 8: Two Instants in an Overlap

File **`DstOverlapDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstOverlapDemo {
    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        LocalDateTime input = LocalDateTime.of(
                2024, 10, 27, 2, 30);

        System.out.println("Valid offsets: "
                + berlin.getRules().getValidOffsets(input).size());

        ZonedDateTime earlier = input.atZone(berlin);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

        System.out.println("Earlier offset: "
                + earlier.getOffset());
        System.out.println("Later offset: "
                + later.getOffset());
        System.out.println("Same local time: "
                + earlier.toLocalDateTime().equals(
                        later.toLocalDateTime()));
        System.out.println("Instant difference (min): "
                + Duration.between(
                        earlier.toInstant(),
                        later.toInstant()).toMinutes());
    }
}
```

```bash
javac -encoding UTF-8 DstOverlapDemo.java
java DstOverlapDemo
```

Stdout per 2024 Berlin tzdb rules:

```text
Valid offsets: 2
Earlier offset: +02:00
Later offset: +01:00
Same local time: true
Instant difference (min): 60
```

**Testing trap:** if two appointments share the same `LocalDateTime` during an overlap, they may represent two different instants. Store the offset/zone and resolution policy, or the confirmed instant. A bare `ZoneOffset` records the offset at that moment without capturing the full regional rules over time.

## 12. Validating Local Times via ZoneRules

A useful validation helper classifies times as **NORMAL**, **GAP**, or **OVERLAP** instead of returning only true/false. Below is a standalone Java 17 program.

**`LocalTimeClassificationDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.time.ZoneOffset;

public class LocalTimeClassificationDemo {
    static String classify(
            LocalDateTime local, ZoneId zone) {
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);
        return switch (offsets.size()) {
            case 0 -> "GAP";
            case 1 -> "NORMAL";
            case 2 -> "OVERLAP";
            default -> throw new IllegalStateException(
                    "Unexpected number of offsets");
        };
    }

    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Europe/Berlin");
        System.out.println(classify(
                LocalDateTime.of(2024, 3, 31, 2, 30), zone));
        System.out.println(classify(
                LocalDateTime.of(2024, 7, 15, 12, 0), zone));
        System.out.println(classify(
                LocalDateTime.of(2024, 10, 27, 2, 30), zone));
    }
}
```

```bash
javac -encoding UTF-8 LocalTimeClassificationDemo.java
java LocalTimeClassificationDemo
```

Stdout per 2024 Berlin tzdb rules:

```text
GAP
NORMAL
OVERLAP
```

When building scheduling APIs, add an **overlap policy**: let the user pick the offset, pick earlier/later by contract, or require an explicit offset in the timestamp. Checking `getValidOffsets.size() >= 1` and silently picking element 0 is an implicit **pick-earlier-instant** policy that users may not agree with.

**Do not call `rules.getOffset(localDateTime)` and treat it as a uniqueness check:** that method returns a "best matching" offset by contract even inside gaps and overlaps, so it does not indicate whether a local time is unique. Use `getValidOffsets` to classify.

## 13. Transition Days Are Not Always 24 Hours Long

If business logic requests "all transactions on March 31, 2024 in Berlin," the true interval is:

```text
start = 2024-03-31 atStartOfDay(Europe/Berlin)
end   = 2024-04-01 atStartOfDay(Europe/Berlin)
Interval = [start.toInstant(), end.toInstant())
```

This span is only **23 hours** long because of the DST gap. Conversely, October 27, 2024 in Berlin is **25 hours** long due to the overlap.

**Do not use `startInstant.plus(24, HOURS)` as "tomorrow" on a local calendar** across zones, because that adds 24 hours of elapsed time rather than finding the start of the next calendar day across DST.

### Program 10: 23 Hours and 25 Hours

**`DstDayLengthDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstDayLengthDemo {
    private static long hours(
            LocalDate day, ZoneId zone) {
        ZonedDateTime start = day.atStartOfDay(zone);
        ZonedDateTime end = day.plusDays(1)
                .atStartOfDay(zone);
        return Duration.between(
                start.toInstant(),
                end.toInstant()).toHours();
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");

        System.out.println("Spring hours: "
                + hours(LocalDate.of(2024, 3, 31), berlin));
        System.out.println("Autumn hours: "
                + hours(LocalDate.of(2024, 10, 27), berlin));

        ZonedDateTime springStart =
                LocalDate.of(2024, 3, 31)
                        .atStartOfDay(berlin);
        System.out.println("Spring +24h local: "
                + springStart.plusHours(24).toLocalTime());
    }
}
```

```bash
javac -encoding UTF-8 DstDayLengthDemo.java
java DstDayLengthDemo
```

Stdout per 2024 Berlin tzdb rules:

```text
Spring hours: 23
Autumn hours: 25
Spring +24h local: 01:00
```

**Distinguish:**

- `plusDays(1)` on `LocalDate` is a **calendar** step.
- `Instant.plus(Duration.ofDays(1))` is **24 absolute hours**.
- `ZonedDateTime.plusDays(1)` operates on the **local timeline** with zone resolution; `plusHours(24)` operates on the **instant timeline**.
- For daily reports, compute **start-of-day for two consecutive calendar dates** and convert to instants rather than blindly adding 86,400 seconds.

**Some zones transition right at midnight:** `LocalDate.atStartOfDay(zone)` returns the first valid instant of the day in that zone, which may not be `00:00` if a gap occurs at midnight. Some zones have even skipped an entire calendar date when shifting across the International Date Line; do not assume every region has continuous historical days.

## 14. Correct Time Intervals for Database Queries

Suppose a user wants records for a `LocalDate` in a given `ZoneId`. The standard approach is a **half-open** interval:

```text
Instant startInclusive = day.atStartOfDay(zone).toInstant();
Instant endExclusive =
    day.plusDays(1).atStartOfDay(zone).toInstant();

Filter: instant >= startInclusive AND instant < endExclusive
```

This is **Java-like pseudocode**, assuming `day` of type `LocalDate` and `zone` of type `ZoneId`. Half-open intervals never overlap adjacent days and avoid guessing the final nanosecond of the day.

**Do not use** `BETWEEN start AND end` when an exclusive upper bound is intended, as SQL `BETWEEN` is inclusive at both ends. Use separate `>=` and `<` predicates; parameterize instants via the appropriate driver/type rather than concatenating locale-formatted strings.

If a database stores timestamps without zones, define the instant-mapping contract explicitly: never casually assume a `TIMESTAMP WITHOUT TIME ZONE` is UTC or the server's local time. Storing `Instant`, UTC, or an explicit time-zone ID must be agreed upon up front.

## 15. Never Depend on the Real Clock or CI's Default Time Zone

A dangerous unit test:

```java
// Anti-pattern: result changes depending on when the test machine runs.
LocalDate today = LocalDate.now();
ZoneId zone = ZoneId.systemDefault();
```

This fragment illustrates an anti-pattern. When CI runs at year-end, in a UTC container, or when a developer machine changes time zones, results fluctuate unpredictably.

**`Clock`** can be injected to control time, and **`ZoneId`** must be chosen explicitly per business requirements. `Clock.fixed(...)` ensures every machine tests the exact same instant.

### Program 11: Same Instant, Different Dates in Two Zones

**`FixedClockBoundaryDemo.java`**:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class FixedClockBoundaryDemo {
    public static void main(String[] args) {
        Instant fixed = Instant.parse(
                "2020-12-31T23:30:00Z");
        Clock utc = Clock.fixed(fixed, ZoneOffset.UTC);
        Clock tokyo = utc.withZone(ZoneId.of("Asia/Tokyo"));

        System.out.println("UTC today: "
                + LocalDate.now(utc));
        System.out.println("Tokyo today: "
                + LocalDate.now(tokyo));
        System.out.println("Same instant: "
                + utc.instant().equals(tokyo.instant()));
    }
}
```

```bash
javac -encoding UTF-8 FixedClockBoundaryDemo.java
java FixedClockBoundaryDemo
```

Stdout:

```text
UTC today: 2020-12-31
Tokyo today: 2021-01-01
Same instant: true
```

This demonstrates that a system can simultaneously require a **fixed `Instant`** and a **calendar date in the user's zone**. If business reporting follows Vietnam dates, the time zone must be part of the contract—never inferred from `Locale` or the backend host.

## 16. Library-Free Unit Tests: Automated Condition Checks

A test program should **fail intentionally** when rules break, not merely print output for a developer to inspect. Java has `assert`, yet Java assertions **can be disabled by default unless `-ea` is passed**. To ensure our example always checks, we use a helper that throws `AssertionError`.

**`CalendarRegressionTest.java`**:

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.temporal.WeekFields;

public class CalendarRegressionTest {
    private static void check(
            boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        LocalDate newYear = LocalDate.of(2021, 1, 1);
        check(newYear.getYear() == 2021,
                "calendar year");
        check(newYear.get(
                WeekFields.ISO.weekBasedYear()) == 2020,
                "ISO week-year");
        check(newYear.get(
                WeekFields.ISO.weekOfWeekBasedYear()) == 53,
                "ISO week 53");

        check(LocalDate.of(2024, 2, 29)
                .plusDays(1)
                .equals(LocalDate.of(2024, 3, 1)),
                "leap day rollover");

        ZoneId berlin = ZoneId.of("Europe/Berlin");
        check(berlin.getRules().getValidOffsets(
                LocalDateTime.of(2024, 3, 31, 2, 30))
                .size() == 0, "spring gap");
        check(berlin.getRules().getValidOffsets(
                LocalDateTime.of(2024, 10, 27, 2, 30))
                .size() == 2, "autumn overlap");

        long springHours = Duration.between(
                LocalDate.of(2024, 3, 31)
                        .atStartOfDay(berlin).toInstant(),
                LocalDate.of(2024, 4, 1)
                        .atStartOfDay(berlin).toInstant())
                .toHours();
        check(springHours == 23, "DST day duration");

        System.out.println("All calendar checks passed");
    }
}
```

```bash
javac -encoding UTF-8 CalendarRegressionTest.java
java CalendarRegressionTest
```

Stdout if tzdb supports the 2024 Berlin rules:

```text
All calendar checks passed
```

If any assertion fails, the program throws `AssertionError` and exits with a non-zero status; that is the desired test behavior. In projects using JUnit 5, equivalent cases can be written with `@ParameterizedTest`/`@MethodSource`, though that requires JUnit dependencies and a test runner. This lesson chooses pure Java SE so every example runs on JDK 17.

## 17. Property-Based and Metamorphic Tests for Calendars

Beyond fixed boundary dates, test **general invariants** across generated dates (using a fixed seed):

- **Date round-trip:** `LocalDate.parse(date.toString())` equals `date` for ISO dates.
- **Consecutive days:** `date.plusDays(1).minusDays(1).equals(date)` within valid range.
- **ISO week-date:** `LocalDate.parse(ISO_WEEK_DATE.format(date), ISO_WEEK_DATE).equals(date)`.
- **Calendar year invariant across UI formatters:** the underlying `LocalDate` remains unchanged after formatting.
- **Zone round-trip on instants:** `instant.atZone(zone).toInstant().equals(instant)` for valid zones.
- **Overlap:** two distinct valid offsets yield two distinct instants with the same local datetime.
- **Gap:** the valid-offsets list has length 0, and every resolution path follows an explicit business policy.
- **Regional day bounds:** `[startOfDay, nextStartOfDay)` never overlaps an adjacent day's interval, even on 23- or 25-hour days.
- **Displayed timestamps:** formatting/parsing must use the same zone/offset/locale/resolver and precision when the contract promises round-trip.

Do not generate random dates with an unseeded RNG so failures become unreproducible. Fix a seed, and log both the seed and failing input (without PII) on failure. For distant dates or regions with complex historical rules, do not assume every property holds outside the defined domain bounds.

## 18. Test Ordering: Unit, Integration, and Locale Snapshots

**Deterministic unit tests** should use:

- Fixed `LocalDate.of(...)` / `Instant.parse(...)`.
- Fixed `WeekFields.ISO` or `WeekFields.of(firstDay,minimalDays)`.
- Explicit `ZoneId` and known tzdb transitions.
- `ResolverStyle.STRICT` for API grammars needing strict contracts.
- `Clock.fixed` instead of the system clock.

**Integration tests** should verify:

- The exact tzdb used by the production runtime.
- Locale/CLDR data and localized formatters for product-supported `Locale`s.
- Database/JDBC mapping of `Instant`/timestamps.
- JSON/CSV serialization and time-zone metadata.
- Execution on Windows/Linux/containers or alternate JDK vendors if supported.
- Legacy `java.util.Calendar`/`SimpleDateFormat` behavior during migrations.

**Snapshot strings** from `DateTimeFormatter.ofLocalizedDate(...)`, month names, zone names, or `WeekFields.of(Locale)` can change across CLDR/JDK upgrades. Snapshots should pin the environment or assert semantic invariants rather than treating values copied from one machine as eternal constants.

Never mix "locale number/date formatting" tests with "instant correctness" tests. Locale affects presentation; it **does not** determine time zones or turn calendar years into week-based years.

## 19. Migration Pitfalls from Date, Calendar, and SimpleDateFormat

In legacy Java code, these patterns frequently cause regressions:

| Legacy API / habit | Migration risk | Tests to add |
| --- | --- | --- |
| `SimpleDateFormat("YYYY-MM-dd")` | Week-year diverges from calendar year around Jan 1 | Dec 31, Jan 1, multiple locales |
| `SimpleDateFormat("yyyy-MM-dd")` | Legacy formatter calendar/leniency/timezone | Invalid dates, explicit zones |
| `Calendar.WEEK_OF_YEAR` | Depends on first day / minimal days and `Calendar.getWeekYear()` | 53-week ISO years and year start |
| Deprecated `new Date(...)` constructor | 0-indexed months, offset years | Replace with `LocalDate.of` |
| `DateFormat.parse` | Prefix parsing, lenient normalization | Full-input validation and strict mode |
| `Calendar.add(DATE, 1)` | Local date vs. elapsed instant diverges across DST | 23/25-hour days around transitions |
| `Date.getTime()` | Epoch millis carrying no display zone | Convert explicitly with `Instant` and `ZoneId` |
| `TimeZone.getDefault()` | Depends on JVM/host | Test with injected zones |
| Static `SimpleDateFormat` across threads | Mutable, not thread-safe | Do not share, or migrate to `java.time` |
| Non-ISO locale calendars | Calendar/era rules can differ | Pick `Chronology` explicitly for domain |

**Gregorian cutover:** legacy `GregorianCalendar` defaults to a Julian/Gregorian cutover date, whereas `LocalDate` uses proleptic Gregorian per ISO. For distant historical dates, the two APIs do not necessarily yield the same date across every era. Do not treat a handful of modern-year tests as proof that a migration preserves all historical data.

### Week-Based Year in SimpleDateFormat

In `SimpleDateFormat`, `Y` also denotes *week-year* in calendars that support it. Yet `Calendar` mechanics and locale week rules can vary by JDK provider/chronology, so never swap `Y`/`y` in a pattern and assume the migration is done. If business data follows ISO, specify ISO explicitly on both sides during migration and cross-check boundary dates.

## 20. Prioritized Test Matrix

A compact matrix still catches many bugs when inputs are chosen well:

| Category | Input | Outcome to verify |
| --- | --- | --- |
| ISO week-year | `2018-12-31` | `2019-W01-1` |
| ISO week-year | `2020-12-31` | `2020-W53-4` |
| ISO week-year | `2021-01-01` | `2020-W53-5` |
| ISO week-year | `2022-01-01` | `2021-W52-6` |
| Differing week rules | `2021-01-01` | ISO `2020/53`, `SUNDAY_START` `2021/1` |
| Leap day | `2024-02-29` | Valid |
| Common year | `2023-02-29` | Rejected by `STRICT` |
| Month without 31st | `2024-04-31` | Rejected by `STRICT` |
| `SMART` parser | `2023-02-29` | May clamp to `2023-02-28` |
| Berlin DST gap | `2024-03-31 02:30` | 0 valid offsets |
| Berlin DST overlap | `2024-10-27 02:30` | 2 valid offsets |
| DST gap day | `2024-03-31` | Span between midnights is 23 hours |
| DST overlap day | `2024-10-27` | Span between midnights is 25 hours |
| Date boundary across zones | `2024-01-01T00:30Z` | LA date = `2023-12-31` |
| Fixed clock | `2020-12-31T23:30Z` | UTC Dec 31, Tokyo Jan 1 |
| Query interval | Berlin `2024-03-31` | `[start,end)` computed by zone, not +24h |
| ISO format | `2021-01-01` | `ISO_LOCAL_DATE`; do not confuse `YYYY` |
| Legacy compatibility | `Date`/`Calendar` | Test time zone, leniency, historical dates |

When filing production bug reports, record the **input `Instant`/`LocalDateTime`, zone ID, offset if present, tzdb/JDK version, and locale/week rule**. Without these details, two engineers in different environments can observe conflicting reproductions with no clear cause.

## 21. Real-World Testing Scenarios

### Scenario A — Year-End Weekly Report

Requirement: compute weekly revenue per ISO week. An event occurs on `2021-01-01`. If code writes `getYear()=2021` and `week=53`, the report groups it under **`2021-W53`**, which does not exist in ISO. Fix by reading the **pair** `WeekFields.ISO.weekBasedYear()` and `weekOfWeekBasedYear()`, and test year-start/year-end dates.

### Scenario B — Disappearing 02:30 Appointment

A customer books `02:30` on `2024-03-31` in Berlin. `LocalDateTime` accepts the values, yet that time does not exist across the DST transition. If the system silently calls `atZone`, the appointment shifts to `03:30`. Instead of relying on silent shifting, use `ZoneRules.getValidOffsets`, report an invalid time and prompt for another slot, or apply a documented shift policy.

### Scenario C — Two Jobs Running at 02:30

On `2024-10-27` in Berlin, `02:30` occurs twice. If logs record only `"2024-10-27 02:30"` without an offset, later analysis cannot determine which job ran first. Store `Instant` for auditing, plus `ZoneId` or offset when reconstructing what the user saw.

### Scenario D — Daily Report Missing an Hour

A report filters for local date `2024-03-31` in Berlin. If the query takes `startInstant` and adds 24 hours, it spills into `2024-04-01`. On a DST overlap day, adding 24 hours misses the day's final hour. Always use `day.atStartOfDay(zone)` and `day.plusDays(1).atStartOfDay(zone)`.

### Scenario E — CI Failing Only in Japan

Tests call `LocalDate.now()`, with developer laptops in UTC and CI runners in `Asia/Tokyo`. Around midnight UTC, the same instant falls on different dates. Fix by injecting `Clock.fixed` and explicit zones; separate "date in user zone" tests from "UTC instant" tests.

## 22. Exercises

**Exercise 1 — Week-year:** Produce the ISO week-date table for `2018-12-31`, `2020-12-31`, `2021-01-01`, and `2022-01-01` using `ISO_WEEK_DATE`. Compare against `getYear()` and explain two dates whose `weekBasedYear` differs from their calendar year.

**Exercise 2 — Week rules:** Create `WeekFields.of(DayOfWeek.SUNDAY, 1)` and `WeekFields.ISO`. Test `2021-01-01`; change `minimalDaysInFirstWeek` to 4 and observe the change.

**Exercise 3 — Strict parser:** Attempt to parse `2023-02-29`, `2024-02-29`, and `2024-04-31` with `ISO_LOCAL_DATE`. Compare against `SMART` `DateTimeFormatter.ofPattern("uuuu-MM-dd")`; write assertions that only valid dates are accepted per contract.

**Exercise 4 — Gap/overlap:** Using `Europe/Berlin`, check `getValidOffsets` at `2024-03-31 02:30` and `2024-10-27 02:30`. Inside the overlap, call `withLaterOffsetAtOverlap()` and compare the two instants.

**Exercise 5 — Hours in a day:** Compute `Duration` between consecutive `atStartOfDay(zone)` calls for March 31 and October 27, 2024. Why is the result not 24h? Write the half-open query interval.

**Exercise 6 — Fixed clock:** Create `Clock.fixed(Instant.parse("2020-12-31T23:30:00Z"), ZoneOffset.UTC)`. Convert the clock to `Asia/Tokyo` and compare `LocalDate.now(clock)` without using the current host time.

**Exercise 7 — Multi-zone system:** Design a storage contract for transaction events and appointments: which fields are `Instant`, `LocalDate`, `LocalDateTime`, `ZoneId`, or `ZoneOffset`? How are gaps and overlaps handled?

**Exercise 8 — Legacy:** Map a migration plan from `Calendar.getWeekYear`/`SimpleDateFormat` to `WeekFields.ISO` and `DateTimeFormatter.ISO_WEEK_DATE`; include test cases for historical dates if the system relies on Julian/Gregorian cutovers.

## 23. Official Documentation and Verification

- [Java SE 17 — WeekFields](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/WeekFields.html): ISO and localized week rules, `weekBasedYear`, `weekOfWeekBasedYear`, week 0.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): `uuuu`/`yyyy`/`YYYY`, `ISO_WEEK_DATE`, `ISO_LOCAL_DATE`, and resolver styles.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): gap/overlap handling, `withLaterOffsetAtOverlap`, calendar vs. instant timeline.
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): `getValidOffsets`, `getTransition`, and time-zone rules.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): ISO dates, leap days, `atStartOfDay(zone)`.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): `Clock.fixed` and wall-clock-independent testing.
- [Java SE 17 — ResolverStyle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/ResolverStyle.html): `STRICT`, `SMART`, `LENIENT`.
- [IANA Time Zone Database](https://www.iana.org/time-zones): time-zone rule data used by the JDK/tzdb provider; updates can alter rules when national policies change.

## 24. Key Takeaways

- **Calendar year ≠ week-based year.** ISO week-year can diverge from calendar year at year start/end; compute `weekBasedYear` and `weekOfWeekBasedYear` as a pair.
- **`yyyy`, `uuuu`, and `YYYY` are not interchangeable.** Avoid `YYYY-MM-dd` for ISO dates; use `ISO_LOCAL_DATE` or `uuuu-MM-dd` with strict parsing.
- **Calendar dates obey leap rules.** Test February 29, month-end boundaries, and `STRICT` parsing; `SMART` can clamp invalid dates.
- **A local datetime may not exist or may occur twice during DST.** Use `ZoneRules.getValidOffsets` to distinguish 0/1/2 offsets.
- **A local day is not necessarily 24 hours.** Compute `[startOfDay(day), startOfDay(day+1))` via `ZoneId`, never adding a fixed 24 hours for daily reports.
- **Avoid default time zones and `now()` in deterministic unit tests.** Inject `Clock.fixed`, explicit zones, and explicit locale/week rules; record tzdb/JDK versions for historical boundaries.
- **Unit tests must fail automatically when wrong.** Use assertion helpers or JUnit with boundary inputs rather than running and eyeballing an ordinary date.

A reliable boundary test suite does not need thousands of random dates; it needs **the exact boundary cases that separate easily confused concepts**, confirming business contracts hold across calendars, week-years, and the timeline.
