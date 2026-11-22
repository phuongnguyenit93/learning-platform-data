# Java Date-Time Learning Roadmap: From Basic Operations to Time Zones and Testing

## Objectives and How to Study

This lesson serves as a learning map for the **Java core – date-time** module. After completing the roadmap, you should be able to choose the right date-time data type on your own, perform calculations and comparisons, read/write ISO 8601 strings, convert time zones without changing the actual instant, recognize Daylight Saving Time (DST) bugs, and write tests independent of the machine's clock.

**Prerequisites:** knowledge of data types, classes, methods, exceptions, and how to run Java 17+. Study each stage below: read the concept → run the example → modify the input data → complete the exercise → check against the completion criteria. It can be completed in about 7 practice sessions; pacing depends on experience.

**Core principle:** before every operation, ask whether the data represents a **calendar date**, a **wall-clock time**, an **absolute instant**, or an **instant governed by time-zone rules**. Choosing the wrong type at this step often leads to errors even when the Java syntax is completely valid.

## 1. Map of Essential Data Types

| Type or Component | Represents | Use When |
| --- | --- | --- |
| `LocalDate` | Calendar date, without time or time zone | Birthdates, date-based deadlines, holidays |
| `LocalTime` | Time of day, without date or time zone | 09:30, opening hours |
| `LocalDateTime` | Local date + time, **does not identify a unique instant** | Appointments entered in local clock time, needing to be combined with a `ZoneId` |
| `Instant` | A point on the UTC timeline | Event timestamps, logs, start/end markers |
| `ZoneId` | Region-based time-zone rules, e.g., `Asia/Ho_Chi_Minh` | Local schedules; needing to apply historical/future DST rules |
| `ZoneOffset` | UTC offset at a point in time, e.g., `+07:00` | Reading/writing a specific offset; does not replace region-wide rules |
| `ZonedDateTime` | Local date-time + region time zone + resolved offset | Meetings in a city and time-zone conversions |
| `OffsetDateTime` | Date-time + fixed offset, without retaining region rules | APIs with offsets, audit events needing to preserve the transmitted offset |
| `Duration` | Amount of time in seconds/nanoseconds | Timeouts, session durations |
| `Period` | Distance in calendar years/months/days | Adding months, calendar-based terms |
| `DateTimeFormatter` | Formatting and parsing date-time strings | API boundaries, forms, UI |
| `Clock` | Replaceable time source | Business logic involving "today/now" and unit tests |

Most types in `java.time` are **immutable**: `plusDays()`, `withYear()`, and `atZone()` return a new object. You must assign the result; calling a method and discarding its return value will not modify the original variable.

Three concepts that are very easy to confuse:

- **Local date/time**: information on a calendar or clock; `LocalDateTime.of(2026, 11, 1, 1, 30)` alone does not pinpoint a unique `Instant` in New York during the repeated DST hour.
- **Instant**: an absolute point in time. The same `Instant` can be displayed as 19:00 in Ho Chi Minh City and 08:00 in New York during summer.
- **ZoneId and ZoneOffset**: the `America/New_York` zone can change its offset from `-05:00` to `-04:00`; the string `-05:00` by itself knows nothing about transition rules.

## 2. Sequential Practice Roadmap

| Stage | Focus | Practice Exercise | Completion Criteria |
| --- | --- | --- | --- |
| 1. Getting Started | `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`; creating fixed values | Create date 30/01/2026 and time 09:30 | Can explain which types have/do not have a time zone |
| 2. Operations | `plus`/`minus`, `with`, `isBefore`/`isAfter`, `ChronoUnit`, `Period`/`Duration` | Calculate deadline after 3 days; add 1 month | Can explain why 30/01 + 1 month = 28/02/2026 |
| 3. Strings and Formatting | `parse`, `format`, ISO 8601, `DateTimeFormatter`, and `Locale` | Convert `31/12/2026` ↔ `LocalDate` | Know how to handle invalid strings with `DateTimeParseException` |
| 4. Timeline | `Instant`, `ZoneId`, `ZoneOffset`, `ZonedDateTime` | Display the same UTC event in 2 cities | Understand that switching zones preserves the `Instant` |
| 5. DST and Boundaries | Non-existent/overlapping hours, leap days, month-end, across midnight | Handle 02:30 and 01:30 in New York | Identify cases where business rules must be clarified |
| 6. Testing | `Clock.fixed`, dependency injection, boundary testing | Write tests for a "today" function | Re-runs produce the same result on every machine/time zone |
| 7. Integration | Data design, storage, APIs, and scheduling | Mini-project for cross-timezone scheduling | Know to store `Instant` and keep `ZoneId` when business logic requires it |

### Stage 1 — Creating and Reading Data

- Use `LocalDate.of(2026, 1, 30)`, `LocalTime.of(9, 30)`, and `LocalDateTime.of(date, time)` when the data is already known. `LocalDate.parse("2026-01-30")` accepts the default ISO string.
- When getting the current date/time, **intentionally pass a `Clock` or `ZoneId`**. Default `LocalDate.now()` and `ZonedDateTime.now()` depend on the machine environment, which is disadvantageous for multi-region applications and testing.
- Understand the conversions: `LocalDate.atTime(LocalTime)` creates a `LocalDateTime`; `Instant.atZone(zone)` creates a `ZonedDateTime`; `ZonedDateTime.toInstant()` returns the absolute timestamp.

**Self-check:** "9 AM tomorrow" is not enough to send a global meeting invitation without knowing the location/time zone; whereas "2026-07-01T12:00:00Z" is already a well-defined `Instant`.

### Stage 2 — Addition/Subtraction, Comparison, and Distance Calculation

- Use `date.plusDays(3)`, `date.plusMonths(1)`, `date.minusWeeks(2)`, `date.withDayOfMonth(1)`; use `isBefore`, `isAfter`, `isEqual`, or `compareTo` for comparisons.
- Adding one month to 30/01/2026 yields **28/02/2026**, because February of that year has no 30th day. This is a calendar operation, not adding a fixed number of days.
- `Period.between(startDate, endDate)` describes the number of calendar years/months/days; `ChronoUnit.DAYS.between(startDate, endDate)` gives the whole number of days between two dates; `Duration.between(startInstant, endInstant)` calculates elapsed time on the timeline.
- Do not use `Duration.ofDays(1)` by default to represent "the next calendar day" when crossing DST: this duration is always 24 hours; a calendar day in a DST-observing zone is sometimes 23 or 25 hours long.
- For shifts spanning midnight, combine `LocalTime` with a date into `LocalDateTime`/`ZonedDateTime` before calculating; `Duration.between(LocalTime.of(23, 0), LocalTime.of(1, 0))` alone yields **-22 hours**.

**Exercise:** compute `ChronoUnit.DAYS.between(LocalDate.of(2026, 1, 30), LocalDate.of(2026, 2, 2))`; the answer is `3`. Try `Period.between(...)` and observe how its representation differs from `Duration`.

### Stage 3 — Parsing/Formatting External Data

- Prefer the ISO 8601 standard for machine-to-machine communication: `LocalDate` → `2026-01-30`; `Instant` → `2026-07-01T12:00:00Z`. Human-readable data can be formatted as needed.
- Example: `DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)`, then `LocalDate.parse("31/12/2026", formatter)` and `date.format(formatter)`. Explicitly declare `Locale` when the pattern includes text-based month/day names.
- Distinguish `MM` = month from `mm` = minute, `HH` = 0–23 hour from `hh` = 1–12 hour requiring AM/PM, and `uuuu` (proleptic calendar year) from `YYYY` (week-based year, prone to errors at year-end). For strict parsing, `uuuu` is more useful than `yyyy` (year-of-era).
- Invalid strings can throw `DateTimeParseException`. Validate at input boundaries and report field-specific errors; when strictness is required, use `withResolverStyle(ResolverStyle.STRICT)`.
- `DateTimeFormatter` is immutable and thread-safe; instances can be reused instead of recreated on every call.

**Exercise:** try parsing `31/02/2026` with a strict formatter, observe the exception, then try `28/02/2026`. Do not silently adjust invalid dates on your own.

### Stage 4 — Time Zones and Actual Instants

- Use IANA zone names such as `Asia/Ho_Chi_Minh` or `America/New_York`. `ZoneId.systemDefault()` should only be used when you truly intend to configure based on the host machine.
- For an event that already has an `Instant`: `event.atZone(zone)` changes how it is displayed; `event` itself does not change. For `ZonedDateTime`, `withZoneSameInstant(otherZone)` keeps the same instant; `withZoneSameLocal(otherZone)` keeps the wall-clock digits, **which can produce a different instant**.
- When accepting a local appointment time, you need both `LocalDateTime` **and** `ZoneId`, and you must check for DST before deciding how to convert to an `Instant`.
- For storing logs or event timestamps, use a unified reference (`Instant`/UTC). If an event recurs "Monday 09:00 in New York", you also need to store the region time zone and recurrence rule; a long-term schedule cannot be accurately represented using only an offset or only UTC.

### Stage 5 — DST: Missing Hours and Duplicate Hours

DST rules vary by region and are updated via the time-zone database (tzdb). Fixed examples in `America/New_York` for the year **2026**:

- **Gap:** On 08/03/2026, local time jumps from 01:59:59 to 03:00. `2026-03-08 02:30` **does not exist**. `LocalDateTime.atZone(zone)` shifts it forward by default to `03:30-04:00`; scheduling logic may need to return an error instead of shifting automatically.
- **Overlap:** On 01/11/2026, `01:30` occurs **twice** (offset `-04:00` then `-05:00`). `atZone(zone)` picks the earlier offset by default; `withLaterOffsetAtOverlap()` picks the later occurrence.
- To make an explicit decision, check `zone.getRules().getValidOffsets(localDateTime)`: size `0` = gap, `1` = normal, `2` = overlap. When there is exactly one offset, you can use `ZonedDateTime.ofStrict(local, offset, zone)`. When there are 0 or 2, apply your business policy: ask the user to choose, reject, or shift according to a documented rule.
- Do not subtract two local wall-clock times and conclude that is the elapsed time. To calculate elapsed time across DST, use `Duration.between(start.toInstant(), end.toInstant())`.

### Stage 6 — Reproducible Testing

Decouple reading the clock from business logic:

```java
import java.time.Clock;
import java.time.LocalDate;

final class DeadlineService {
    private final Clock clock;

    DeadlineService(Clock clock) {
        this.clock = clock;
    }

    LocalDate tomorrow() {
        return LocalDate.now(clock).plusDays(1);
    }
}
```

This is a **class snippet to put into a project**, not a standalone runnable program. In tests, pass `Clock.fixed(Instant.parse("2026-01-15T12:00:00Z"), ZoneOffset.UTC)`; calling `tomorrow()` must return `2026-01-16`. In the application, pass `Clock.system(zone)` from configuration. You can use JUnit 5 for assertions, though the pattern does not depend on any specific testing library.

Beyond the happy path, test Feb 29 of a leap year, 30/31-day month-ends, year-end, invalid parsing, times near midnight across different `ZoneId`s, DST gap/overlap, and interval start/end boundaries. Tests must pass **explicit dates/times and zones**; do not rely on `now()` or the CI machine's default time zone.

### Stage 7 — Applying to Real Applications

When designing data models, define the semantics before choosing the field type:

| Business Field | Recommended Model | Reason |
| --- | --- | --- |
| Birthdate, holiday | `LocalDate` | Independent of offset |
| Working hours, timeout | `Duration` or seconds with explicit unit | Actual elapsed time |
| Record creation timestamp | `Instant` | Consistent comparison and sorting |
| Start time of a one-off meeting | `Instant` and `ZoneId` depending on display needs | Preserves the instant while knowing the host zone |
| Opening hours/recurring local tasks | Local date/time + `ZoneId` + recurrence rule | Offset can change by date |

When using a database or JSON, document the semantics of each field: is a string without an offset local time or UTC? SQL's `TIMESTAMP WITH TIME ZONE` behaves differently depending on the DBMS and does not preserve the `ZoneId` name by default; check the documentation of the system you use. Avoid converting back and forth with legacy `Date`/`Calendar` if your API already supports `java.time`; if you must integrate with legacy APIs, keep the conversion at the boundary.

## 3. Verified Comprehensive Java 17+ Program

The following example combines calendar dates, adding days/months, day differences, two time zones, `Clock.fixed`, and both DST cases. Create the file **`DateTimeRoadmapDemo.java`**:

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class DateTimeRoadmapDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2026, 1, 30);
        LocalDate deadline = start.plusDays(3);
        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX", Locale.ROOT);

        Instant event = Instant.parse("2026-07-01T12:00:00Z");
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId ny = ZoneId.of("America/New_York");

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-15T12:00:00Z"),
                ZoneOffset.UTC
        );

        System.out.println("Cong 1 thang: " + start.plusMonths(1));
        System.out.println("Han chot: " + deadline);
        System.out.println("So ngay: " + ChronoUnit.DAYS.between(start, deadline));
        System.out.println("HCM: " + event.atZone(hcm).format(formatter));
        System.out.println("New York: " + event.atZone(ny).format(formatter));
        System.out.println("Ngay co dinh: " + LocalDate.now(fixedClock));
        System.out.println("DST gap: " +
                LocalDateTime.of(2026, 3, 8, 2, 30).atZone(ny));
        System.out.println("DST overlap som: " +
                LocalDateTime.of(2026, 11, 1, 1, 30).atZone(ny).getOffset());
        System.out.println("DST overlap muon: " +
                LocalDateTime.of(2026, 11, 1, 1, 30)
                        .atZone(ny).withLaterOffsetAtOverlap().getOffset());
    }
}
```

Compile and run in the terminal with JDK 17 or newer:

```bash
javac -encoding UTF-8 DateTimeRoadmapDemo.java
java DateTimeRoadmapDemo
```

**Exact output (with tzdb data and rules applicable to the dates in the example):**

```text
Cong 1 thang: 2026-02-28
Han chot: 2026-02-02
So ngay: 3
HCM: 2026-07-01 19:00 +07:00
New York: 2026-07-01 08:00 -04:00
Ngay co dinh: 2026-01-15
DST gap: 2026-03-08T03:30-04:00[America/New_York]
DST overlap som: -04:00
DST overlap muon: -05:00
```

Output explanation: adding one month to 30/01 is normalized to the last day of February; `ChronoUnit.DAYS` returns `3` calendar days; `event` is represented in two time zones while remaining **a single instant**; the fixed clock helps test the current date; the missing hour is shifted forward automatically and the overlapping hour has two valid offsets. This is also why scheduling applications must define their DST policy before saving.

## 4. Capstone Exercise: Multi-Timezone Meeting Scheduler

Build a function that takes `LocalDateTime requestedLocal`, `ZoneId organizerZone`, and `ZoneId attendeeZone`, and returns the `Instant` along with the display times in both zones.

**Business requirements:**

1. Check `organizerZone.getRules().getValidOffsets(requestedLocal)`. If **0** offsets, reject the non-existent time with a specific error message. If **2** offsets, ask the user to choose "earlier/later occurrence" to determine a single instant; if **1**, use that offset.
2. Create a `ZonedDateTime` using `ZonedDateTime.ofStrict(requestedLocal, selectedOffset, organizerZone)` and convert it to `Instant` for storage.
3. Display the time for the attendee using `instant.atZone(attendeeZone)`. Verify that `instant.equals(attendeeZoned.toInstant())` is always `true`.
4. Inject `Clock` into the service when there is a rule such as "do not allow scheduling in the past"; test with `Clock.fixed` rather than reading the machine's real-time clock.
5. Pass zones as `ZoneId` (such as `America/New_York`), not just the `-04:00` offset, so that winter schedules remain accurate.

**Minimum test suite:**

| Scenario | Test Data | Expected Result |
| --- | --- | --- |
| Valid leap day | `2028-02-29` | Parses and adds 1 day to become 01/03 |
| Invalid date | `2026-02-29` with strict parsing | Throws an error |
| Year-end rollover | `2026-12-31` + 1 day | `2027-01-01` |
| Month-end | `2026-01-30` + 1 month | `2026-02-28` |
| Same instant, different zones | `2026-07-01T12:00:00Z` in HCM/NY | 19:00 +07:00 / 08:00 -04:00 |
| New York gap | `2026-03-08T02:30` | 0 valid offsets; do not schedule silently |
| New York overlap | `2026-11-01T01:30` | 2 valid offsets; require selection |
| "In the past" rule | Clock `2026-01-15T12:00:00Z` | Consistent results across machines |
| Duration across DST | Two `Instant`s around transition | Calculated in actual seconds, not by subtracting wall-clock hours |

**Definition of done:** all test cases run automatically; stored data points to a single point in time for a specific meeting; DST flows are handled explicitly; changing the display time zone does not alter the `Instant`; the service allows swapping the clock in tests.

## 5. Common Pitfalls and How to Self-Check

- **Using `LocalDateTime` as a UTC timestamp:** it lacks a zone/offset, so a unique instant cannot be inferred. Use `Instant` when recording absolute events.
- **Confusing `ZoneId` and `ZoneOffset`:** an offset like `+07:00` does not contain history, DST, or regional legal changes.
- **Treating 24 hours as 1 calendar day everywhere:** across DST this can differ; choose `Period`/`plusDays` for calendar math and `Duration` for actual elapsed time.
- **Forgetting immutability:** `date.plusDays(1);` does not modify `date`; you must assign `date = date.plusDays(1);`.
- **Using `YYYY` to format a regular year:** `YYYY` is the week-based year; use `uuuu` for the ISO calendar year in example patterns.
- **Letting the system time zone leak into tests:** results will differ between a laptop and CI; pass `Clock.fixed` and `ZoneId` explicitly.
- **Accepting unvalidated date strings:** the default formatter may apply the `SMART` resolver style; use `STRICT` when business rules require rejecting invalid dates.
- **Testing only the happy path:** prone to breaking on Feb 29, across midnight, month-ends, and gaps/overlaps; turn boundary cases into fixed tests.

## 6. Post-Roadmap Checklist

- [ ] Can classify inputs into `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, or `ZonedDateTime` before writing code.
- [ ] Can calculate calendar dates and durations; can explain the difference between `Period` and `Duration`.
- [ ] Can parse/format ISO and custom patterns with `Locale`/strict validation.
- [ ] Can convert an `Instant` into two zones using `ZoneId` without changing the point in time.
- [ ] Can identify DST gaps/overlaps and establish explicit business rules.
- [ ] Can test "now"-dependent logic using `Clock.fixed`; can test boundary cases.
- [ ] Can design appropriate storage models for calendar dates, absolute events, and zone-based recurring schedules.

Standard JDK 17 reference documentation: [`java.time` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html), [`ZonedDateTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html), [`Clock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html), and [`DateTimeFormatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).