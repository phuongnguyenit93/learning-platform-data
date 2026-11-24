# Testing Nonexistent Dates, Leap Years, and Clock Transitions in Spring

## 1. Objective: testing format, calendar, and time zone together

Date and time data entering a Spring application via query parameters, path variables, forms, JSON, or configuration typically starts as a string. A string that matches the expected pattern is not necessarily a **real calendar date**, and a calendar-valid local date-time is not necessarily a **uniquely defined instant** in a time zone.

Three examples with fundamentally different failure modes:

- `2025-02-29` matches `yyyy-MM-dd` syntax, yet February 29, 2025 does not exist because 2025 is not a leap year.
- `2024-02-29` exists because 2024 is a leap year; an overly loose parser or faulty check might wrongly reject it.
- `2024-03-10T02:30` is a valid date and time in `LocalDateTime`, yet **does not exist** in `America/New_York`: clocks jumped from 01:59:59 to 03:00 on the start of daylight saving time (DST) that year.

Another case is even trickier: `2024-11-03T01:30` occurs **twice** in `America/New_York` when clocks fall back. It can map to two `Instant` values 60 minutes apart. If a scheduling system or transaction store picks one arbitrarily, it creates hard-to-explain behavior.

This lesson covers building a test case table, writing a Java 17+ test suite, handling inputs via Spring MVC, distinguishing parse errors from DST gaps/overlaps, and ensuring consistent results across developer machines, CI, and servers.

## 2. Choosing the data type before testing

| Type | Description | Affected by DST when constructed on its own? |
| --- | --- | --- |
| `LocalDate` | Calendar date, e.g. `2024-02-29` | No: no time or zone |
| `LocalTime` | Local time, e.g. `01:30` | No: no date or zone |
| `LocalDateTime` | Local date + time, e.g. `2024-11-03T01:30` | Not yet: no zone to evaluate against |
| `ZoneId` | Region with historical rules, e.g. `America/New_York` | Used to evaluate DST transitions |
| `ZoneOffset` | Fixed UTC offset, e.g. `-04:00` | Contains no clock-change schedule |
| `OffsetDateTime` | Local date-time + fixed offset | Identifies an `Instant`, though offset must be valid if region zone is also known |
| `ZonedDateTime` | Date/time + region zone + resolved offset | Yes; zone rules govern local-time-to-instant resolution |
| `Instant` | Absolute point on the UTC timeline | Unambiguous; local clock display depends on zone |

**Design rule:** date-only birth dates, holidays, and expiration dates should usually be `LocalDate`. Meetings scheduled in a city require `ZoneId` as well (and sometimes an offset choice during repeated hours). Event logs or finalized transaction times should store `Instant`.

`ZoneId.of("America/New_York")` uses the time zone rules database (tzdb); `ZoneOffset.of("-05:00")` is only a fixed offset. Never use a fixed offset to derive local times year-round in New York.

## 3. Nonexistent dates and leap year rules

In the proleptic ISO/Gregorian calendar used by `java.time`:

1. Years divisible by 4 are normally leap years.
2. Years divisible by 100 are not leap years.
3. Exception: years divisible by 400 are still leap years.

Examples: 2024 and 2000 are leap years; 2025 and 1900 are not. Java provides `Year.isLeap(year)` and `Year.of(year).isLeap()`, so never re-implement the formula in production code.

Minimum calendar boundary cases:

| ISO string | Correct outcome | Reason |
| --- | --- | --- |
| `2024-02-29` | Valid | Leap year |
| `2025-02-29` | Invalid | 2025 is not a leap year |
| `2000-02-29` | Valid | Century year divisible by 400 |
| `1900-02-29` | Invalid | Century year not divisible by 400 |
| `2024-04-30` | Valid | April has 30 days |
| `2024-04-31` | Invalid | April has no day 31 |
| `2024-13-01` | Invalid | Month 13 does not exist |
| `2024-00-10` | Invalid | Month 0 does not exist |
| `2024-01-32` | Invalid | Day 32 does not exist |
| `2024-12-31` | Valid | Year-end date |
| `2025-01-01` | Valid | Across year boundary |

Do not validate strings solely with a regex like `\\d{4}-\\d{2}-\\d{2}`. A regex accepts the shape of `2025-02-29` without knowing the date does not exist. Parsing into `LocalDate` with a strict parser enforces full calendar limits.

### 3.1. STRICT, SMART, and LENIENT

JDK `DateTimeFormatter` has three date resolution styles:

- `ResolverStyle.STRICT`: rejects invalid dates such as Feb 29 in a non-leap year.
- `ResolverStyle.SMART`: may clamp an out-of-range day to the month's last day; e.g. 2025-02-29 can become 2025-02-28.
- `ResolverStyle.LENIENT`: allows field overflow and rollover, suited to specialized math but dangerous for user inputs requiring exact accuracy.

An easy-to-miss detail: `DateTimeFormatter.ofPattern("uuuu-MM-dd")` has **SMART as its default resolver style**. By contrast, `DateTimeFormatter.ISO_LOCAL_DATE` is an ISO formatter with **STRICT resolver style**. Do not assume all date parsing in Java is strict just because `LocalDate.parse("2025-02-29")` fails by default.

Java fragment example:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

DateTimeFormatter smart = DateTimeFormatter.ofPattern("uuuu-MM-dd");
DateTimeFormatter strict = smart.withResolverStyle(ResolverStyle.STRICT);

System.out.println(LocalDate.parse("2025-02-29", smart));
// 2025-02-28: SMART adjusts to the end of the month

LocalDate.parse("2025-02-29", strict);
// Throws DateTimeParseException: STRICT rejects that date
```

If a custom pattern such as `dd/MM/uuuu` is needed, build a strict formatter explicitly:

```java
DateTimeFormatter dateFormat = DateTimeFormatter
        .ofPattern("dd/MM/uuuu")
        .withResolverStyle(ResolverStyle.STRICT);
```

In `java.time.DateTimeFormatter`, `uuuu` is the proleptic year; `yyyy` is *year-of-era*. Using `yyyy` with strict resolver without supplying an era can cause ordinary dates to fail parsing. For strict Java Time patterns with standard years, `uuuu` usually avoids surprises.

Note: Spring's `@DateTimeFormat(pattern = "...")` applies its own pattern handling and parser semantics depending on target type and Spring version; test the real Spring contract rather than extrapolating verbatim from every JDK factory method.

## 4. DST: gap, overlap, and normal time

`ZoneRules.getValidOffsets(LocalDateTime)` returns the offsets actually permitted at a local date-time in a `ZoneId`:

| Result | Meaning | Action for precision scheduling apps |
| --- | --- | --- |
| 0 offsets | **Gap**: local time does not exist because clocks jumped forward | Reject and ask for another time, or apply a documented adjustment policy |
| 1 offset | **Normal**: uniquely identifies one instant | Convert directly with the valid offset |
| 2 offsets | **Overlap**: local time occurs twice when clocks fall back | Prompt user/accept offset in request, or apply an explicit earlier/later policy |

The fixed examples below use `America/New_York` rules for 2024, avoiding dependence on the host machine's current time:

- **Gap:** on 2024-03-10, after 01:59:59 local time comes 03:00:00. `2024-03-10T02:30` has no valid offset.
- **Overlap:** on 2024-11-03, clocks fall back from 02:00 daylight time to 01:00 standard time. `2024-11-03T01:30` has offsets `-04:00` and `-05:00`.
- **Normal:** `2024-03-10T01:30` has offset `-05:00`; `2024-03-10T03:30` has offset `-04:00`.

### 4.1. Why is calling atZone() alone not enough to catch errors?

`LocalDateTime.atZone(zone)` attempts to resolve the date-time: for a gap, it **pushes the time forward** by the transition duration; for an overlap, it typically picks the **earlier offset**. That is:

```java
var zone = java.time.ZoneId.of("America/New_York");
var gap = java.time.LocalDateTime.of(2024, 3, 10, 2, 30);
System.out.println(gap.atZone(zone).toLocalDateTime());
// 2024-03-10T03:30
```

This is JDK-defined behavior, yet not necessarily what your business contract wants. For a 02:30 booking, silently shifting it to 03:30 can be wrong. To **avoid auto-shifting times** and **avoid guessing during overlaps**, inspect `getValidOffsets(local)` before constructing a `ZonedDateTime`.

### 4.2. Two instants for one repeated hour

In `America/New_York`:

| Local datetime | Offset | UTC Instant |
| --- | --- | --- |
| `2024-11-03T01:30` | `-04:00` | `2024-11-03T05:30:00Z` |
| `2024-11-03T01:30` | `-05:00` | `2024-11-03T06:30:00Z` |

The two UTC instants differ by **60 minutes**. For a system needing a unique instant, the client can send an `OffsetDateTime` containing the offset or send an `early/later` selection; the application must verify the offset against `ZoneRules` for the chosen zone.

**Not every region observes DST.** `Asia/Ho_Chi_Minh` currently has no annual DST transitions, yet using `America/New_York` in tests proves gap/overlap logic even when CI runs in Vietnam. Zone rules can change in tzdb updates; record the JDK/tzdb version if tests involve the distant future or countries modifying clock laws.

## 5. Standalone Java 17+ example with deterministic output

Create **`TemporalEdgeCaseDemo.java`** with the complete code below (JDK libraries only):

```java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.zone.ZoneRules;
import java.util.Locale;

public class TemporalEdgeCaseDemo {

    private static final DateTimeFormatter STRICT_DMY =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static void checkDate(String text) {
        try {
            System.out.println(text + " -> "
                    + LocalDate.parse(text, STRICT_DMY));
        } catch (DateTimeParseException ex) {
            System.out.println(text + " -> INVALID");
        }
    }

    public static void main(String[] args) {
        System.out.println("2024 leap=" + Year.isLeap(2024));
        System.out.println("2025 leap=" + Year.isLeap(2025));
        System.out.println("1900 leap=" + Year.isLeap(1900));
        System.out.println("2000 leap=" + Year.isLeap(2000));

        checkDate("29/02/2024");
        checkDate("29/02/2025");
        checkDate("31/04/2024");

        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneRules rules = newYork.getRules();

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("gap-offset-count="
                + rules.getValidOffsets(gap).size());
        System.out.println("atZone-adjusted="
                + gap.atZone(newYork).toLocalDateTime());

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        System.out.println("overlap-offsets="
                + rules.getValidOffsets(overlap));

        ZonedDateTime early = overlap.atZone(newYork);
        ZonedDateTime late = early.withLaterOffsetAtOverlap();

        System.out.println("overlap-early=" + early.getOffset());
        System.out.println("overlap-late=" + late.getOffset());
        System.out.println("instant-difference-minutes="
                + Duration.between(early.toInstant(), late.toInstant())
                        .toMinutes());
    }
}
```

Compile/run on JDK 17 or newer:

```bash
javac TemporalEdgeCaseDemo.java
java TemporalEdgeCaseDemo
```

Expected stdout with standard 2024 New York tzdb rules:

```text
2024 leap=true
2025 leap=false
1900 leap=false
2000 leap=true
29/02/2024 -> 2024-02-29
29/02/2025 -> INVALID
31/04/2024 -> INVALID
gap-offset-count=0
atZone-adjusted=2024-03-10T03:30
overlap-offsets=[-04:00, -05:00]
overlap-early=-04:00
overlap-late=-05:00
instant-difference-minutes=60
```

Explanation: `checkDate` uses the strict resolver so **no auto-correction occurs**. The two `getValidOffsets` checks distinguish gap and overlap explicitly. `atZone` in the example is solely to **demonstrate the Java API's auto-adjust/offset-selection behavior**; in business code needing rejection, never rely on it as the sole check.

When preserving an exact local datetime and offset, `ZonedDateTime.ofStrict(local, offset, zone)` verifies that the offset is permitted by zone rules; it throws `DateTimeException` if the combination is invalid.

## 6. Designing a reusable validator class

For appointment scheduling, we can proactively reject both gaps and overlaps, forcing the caller to provide an unambiguous value. This is **one specific business policy**, not the only default policy of Spring or Java.

**File `src/main/java/com/example/calendar/StrictAppointmentTime.java`:**

```java
package com.example.calendar;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

public final class StrictAppointmentTime {
    private StrictAppointmentTime() {}

    public static ZonedDateTime resolve(
            LocalDateTime local, ZoneId zone) {

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets = rules.getValidOffsets(local);

        if (offsets.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local time does not exist in zone: " + local);
        }
        if (offsets.size() > 1) {
            throw new IllegalArgumentException(
                    "Local time is ambiguous in zone: " + local);
        }

        // Single valid offset, verified by ZoneRules.
        return ZonedDateTime.ofStrict(local, offsets.get(0), zone);
    }
}
```

Here:
- `offsets.isEmpty()` represents a nonexistent hour caused by a DST gap.
- `offsets.size() > 1` represents a repeated hour caused by a DST overlap.
- `ofStrict` enforces the valid combination of local datetime, zone, and offset.
- The code avoids calling `LocalDateTime.now()` and avoids the JVM default time zone; tests are deterministic.

When you want to **support** repeated hours instead of rejecting them, change the API to accept an offset or explicit choice. For example, offsets `-04:00` and `-05:00` are both valid for `2024-11-03T01:30` in New York; the client must indicate one of them. If the supplied offset is not in `rules.getValidOffsets(local)`, fail rather than silently substituting another offset.

## 7. JUnit 5 unit tests: covering impossible dates, leap years, gaps, overlaps

**File `src/test/java/com/example/calendar/TemporalRulesTest.java`:**

```java
package com.example.calendar;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Year;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.List;
import java.util.Locale;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TemporalRulesTest {

    private static final DateTimeFormatter STRICT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    @Test
    void leapYearAndCenturyRules() {
        assertTrue(Year.isLeap(2024));
        assertFalse(Year.isLeap(2025));
        assertFalse(Year.isLeap(1900));
        assertTrue(Year.isLeap(2000));

        assertEquals(LocalDate.of(2024, 2, 29),
                LocalDate.parse("29/02/2024", STRICT));
        assertEquals(LocalDate.of(2000, 2, 29),
                LocalDate.parse("29/02/2000", STRICT));
    }

    @Test
    void rejectsImpossibleCalendarDates() {
        for (String input : List.of(
                "29/02/2025",
                "29/02/1900",
                "31/04/2024",
                "32/01/2024",
                "10/13/2024")) {

            assertThrows(DateTimeParseException.class,
                    () -> LocalDate.parse(input, STRICT),
                    "Should reject: " + input);
        }
    }

    @Test
    void detectsDaylightSavingGap() {
        var gap = LocalDateTime.of(2024, 3, 10, 2, 30);

        assertTrue(NEW_YORK.getRules()
                .getValidOffsets(gap).isEmpty());

        assertThrows(IllegalArgumentException.class,
                () -> StrictAppointmentTime.resolve(gap, NEW_YORK));

        // atZone() automatically shifts the time forward to 03:30,
        // so atZone() alone cannot be used to prove the time is valid.
        assertEquals(LocalDateTime.of(2024, 3, 10, 3, 30),
                gap.atZone(NEW_YORK).toLocalDateTime());
    }

    @Test
    void detectsDaylightSavingOverlap() {
        var overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        var offsets = NEW_YORK.getRules().getValidOffsets(overlap);

        assertEquals(List.of(
                ZoneOffset.ofHours(-4),
                ZoneOffset.ofHours(-5)), offsets);

        assertThrows(IllegalArgumentException.class,
                () -> StrictAppointmentTime.resolve(overlap, NEW_YORK));

        ZonedDateTime early = overlap.atZone(NEW_YORK);
        ZonedDateTime late = early.withLaterOffsetAtOverlap();

        assertEquals(Instant.parse("2024-11-03T05:30:00Z"),
                early.toInstant());
        assertEquals(Instant.parse("2024-11-03T06:30:00Z"),
                late.toInstant());
        assertEquals(60,
                Duration.between(early.toInstant(), late.toInstant())
                        .toMinutes());
    }

    @Test
    void resolvesUnambiguousTime() {
        var local = LocalDateTime.of(2024, 3, 10, 1, 30);
        var resolved = StrictAppointmentTime.resolve(local, NEW_YORK);

        assertEquals(ZoneOffset.ofHours(-5), resolved.getOffset());
        assertEquals(Instant.parse("2024-03-10T06:30:00Z"),
                resolved.toInstant());
    }
}
```

This is JUnit 5 running in a **project with the JUnit Jupiter dependency**; the package name must match `StrictAppointmentTime` above. The tests need no server or database. If using Gradle with standard JUnit Platform configuration, run the corresponding test task; in a simple Java project, JUnit must still be on the test classpath.

Group assertions by layer:
- **Calendar** tests verify real dates and leap-year boundaries.
- **DST** tests verify 0/1/2 offsets and the gap/overlap rejection policy.
- **Instant** tests verify exact UTC instants, not just formatted strings.
- **Environment-independent** tests never mutate the machine time zone; always pass `ZoneId` and use fixed dates.

## 8. Testing when data flows through Spring MVC

When a query parameter has type `LocalDate` or `LocalDateTime`, Spring MVC parses the string through its formatting/data binding pipeline. `@DateTimeFormat(iso = ...)` can be used to state the input contract explicitly.

Example controller with two endpoints illustrating a **calendar date** and an **appointment time in a specified zone**.

**File `src/main/java/com/example/calendar/CalendarController.java`:**

```java
package com.example.calendar;

import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class CalendarController {

    @GetMapping("/calendar/date")
    public String date(
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate day) {
        return day.toString();
    }

    @GetMapping("/calendar/appointment")
    public String appointment(
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME)
            LocalDateTime local,
            @RequestParam String zone) {

        ZoneId zoneId;
        try {
            zoneId = ZoneId.of(zone);
        } catch (DateTimeException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid zone");
        }

        try {
            ZonedDateTime resolved =
                    StrictAppointmentTime.resolve(local, zoneId);
            return resolved.toInstant().toString();
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Nonexistent or ambiguous local time", ex);
        }
    }
}
```

This controller requires a Spring MVC project with the Web dependency and component scanning covering the package above; it is **not** a standalone program runnable with `javac`. Together with `StrictAppointmentTime`, the expected contract is:

| Request | Result |
| --- | --- |
| `GET /calendar/date?day=2024-02-29` | 200, body `2024-02-29` |
| `GET /calendar/date?day=2025-02-29` | 400 due to invalid date parse/bind |
| `GET /calendar/date?day=2024-04-31` | 400 due to invalid date parse/bind |
| `GET /calendar/appointment?local=2024-03-10T01:30:00&zone=America/New_York` | 200, body `2024-03-10T06:30:00Z` |
| `GET /calendar/appointment?local=2024-03-10T02:30:00&zone=America/New_York` | 400 due to gap, caught by business logic |
| `GET /calendar/appointment?local=2024-11-03T01:30:00&zone=America/New_York` | 400 due to overlap, caught by business logic |
| `GET /calendar/appointment?local=2024-11-03T01:30:00&zone=Invalid/Zone` | 400 due to invalid zone |

**Distinguishing two error layers:** When `@DateTimeFormat` cannot construct a `LocalDate`, Spring MVC handles the type-conversion failure at binding time (normally HTTP 400 for `@RequestParam`). By contrast, `2024-03-10T02:30:00` **is still a valid `LocalDateTime`**; the date-time parser binds it successfully, and the application itself must inspect `ZoneRules` and return 400 for the gap. Likewise, a repeated hour is not a syntax error: you need a policy to choose or reject overlaps.

### 8.1. When using @ModelAttribute and BindingResult

Suppose a form has a `LocalDate`: if the string has bad syntax or a nonexistent date, the conversion error can be recorded in `BindingResult` with a code like `typeMismatch`. Bean Validation annotations `@NotNull`, `@Future`, or `@Past` validate values **after conversion succeeds**; they do not detect gaps/overlaps on a zone-less `LocalDateTime`.

For example, `@Future` on `LocalDateTime` also depends on the current clock, so do not treat it as proof of valid calendar dates or zones. To test `@Future` reliably, control the clock/validation setup rather than relying on real wall time in CI.

### 8.2. Does JSON use the same parse logic?

Not by default. JSON `@RequestBody` is typically deserialized by Jackson according to `ObjectMapper` and Java Time module settings. `@DateTimeFormat` belongs to Spring formatting for binding; `@JsonFormat` belongs to Jackson. Therefore, maintain a **separate JSON test suite** if endpoints accept JSON.

JSON containing `{"local":"2024-03-10T02:30:00","zone":"America/New_York"}` can deserialize into valid `LocalDateTime` and `String` values; DST validation still has to be invoked at the business layer.

## 9. Building a test matrix before writing code

A thorough test matrix should cover at least three independent dimensions:

### Dimension A: calendar date validity

| Partition | Examples | Assertion |
| --- | --- | --- |
| Normal date | 15/06/2024 | Parses to `LocalDate.of(2024,6,15)` |
| Month-end boundary | 30/04/2024; 31/04/2024 | One passes, one fails |
| Leap year | 29/02/2024 | Pass |
| Non-leap year | 29/02/2025 | Fail |
| 100/400 rule | 29/02/1900; 29/02/2000 | Fail then pass |
| Out-of-range fields | Month 00, 13; day 00, 32 | Fail |
| Wrong pattern | 2024/02/29 when only `dd/MM/uuuu` is allowed | Fail |
| Empty / null | `""`, `null` | Test separately per API contract |
| Extra whitespace | `" 29/02/2024 "` | Explicitly test `trim`/no-trim policy |

### Dimension B: pairing local time with time zone

| Partition | Examples | Assertion |
| --- | --- | --- |
| Normal hour before DST change | New York 2024-03-10 01:30 | One offset `-05:00` |
| Gap | New York 2024-03-10 02:30 | Zero offsets; rejected per strict policy |
| Normal hour after gap | New York 2024-03-10 03:30 | One offset `-04:00` |
| Overlap | New York 2024-11-03 01:30 | Two offsets, `-04:00` and `-05:00` |
| Normal hour after overlap | New York 2024-11-03 02:30 | One offset `-05:00` |
| Region without current annual DST | Ho Chi Minh 2024-03-10 02:30 | Evaluated by region rules, not New York rules |
| Invalid Zone ID | `Invalid/Zone` | Clear error, never substitutes a default |

### Dimension C: data ingestion points

- **Unit:** direct calls to `LocalDate.parse`, `Year.isLeap`, and `ZoneRules.getValidOffsets`.
- **Spring formatting:** verify the actually configured `ConversionService`/`@DateTimeFormat`.
- **MVC integration:** verify HTTP status/body with `MockMvc` for query/form, especially 400 when parsing or validation fails.
- **JSON integration:** verify Jackson deserialization and business policies for JSON bodies.
- **Persistence:** verify storing `Instant`/offset/zone loses no necessary info, and reading it back reproduces the appointment accurately.

The matrix should share fixed test fixtures across layers, with each layer verifying its own responsibility. Never write tests that merely mirror implementation code without proving rules or user-visible behavior.

## 10. Tips for testing with system clock, locale, and time zone

### 10.1. Avoid current date/time

Never use `LocalDate.now()` or `ZonedDateTime.now()` as test assertions for calendar/DST boundaries: the same test may behave differently today, past midnight, or when CI has a different time zone. Use fixed dates like 2024 or inject `Clock.fixed(Instant.parse(...), zone)` into clock-aware code.

### 10.2. Do not rely on the default time zone

`ZoneId.systemDefault()` depends on the host. In business tests, pass `ZoneId.of("America/New_York")` or the contracted zone. Mutating `TimeZone.setDefault(...)` globally during parallel tests can break other cases. Avoid it whenever possible.

### 10.3. Note tzdb data limitations

Clock-change laws are set by governments and can change. JDKs ship a tzdb version; New York's 2024 historical rules are a stable fixture for teaching gaps/overlaps. If a system schedules years into the future, store the zone ID and plan how to handle rule updates; do not store only a precomputed offset years in advance.

### 10.4. Locale and patterns

`05/11/2024` can be read as Nov 5 or May 11 depending on pattern/locale. Choose ISO `yyyy-MM-dd` for machine communication and explicit patterns for agreed UIs. `DateTimeFormatter.ofPattern(..., Locale.ROOT)` reduces locale dependence in some patterns, though it does not replace specifying day/month/year order. Styles tied to locale/JDK data can shift; use stable formats for APIs and assertions.

### 10.5. DateFormatter (legacy) differs from java.time

When legacy layers use `java.util.Date` or `SimpleDateFormat`, remember `SimpleDateFormat` defaults to **lenient=true** unless configured otherwise. It can silently roll over invalid dates. To reject nonexistent dates, set `setLenient(false)`, specify an explicit time zone, and never share a mutable `SimpleDateFormat` instance across threads. For modern Java code, prefer immutable `java.time` and strict resolvers.

Do not assume from legacy parser tests that your `LocalDate` converters or Spring MVC behave identically. Test the actual input path.

## 11. Common mistakes

1. **Checking only with regex:** `2025-02-29` slips right past a `yyyy-MM-dd` pattern check.
2. **Forgetting century years:** `year % 4 == 0` misclassifies 1900.
3. **Using a SMART formatter to validate user input:** bad dates silently clamp to month-end without error.
4. **Using `yyyy` with strict Java Time resolver without an era:** valid dates can fail; consider `uuuu`.
5. **Believing `LocalDateTime` knows the time zone:** `LocalDateTime` carries no zone/offset, so it cannot detect DST gaps/overlaps.
6. **Calling `atZone()` and treating every result as valid:** the API can push gap times forward or pick one overlap offset.
7. **Storing a fixed offset instead of a region zone:** a region's DST/history can differ in the future.
8. **Letting CI rely on the default time zone:** tests vary across machines and become hard to reproduce.
9. **Testing Spring queries while skipping JSON:** MVC formatters and Jackson are separate decoding pipelines.
10. **Treating every failure as Bean Validation:** invalid calendar dates fail during conversion, whereas DST requires zone-aware validation/business logic.
11. **Failing to check both instants in an overlap:** comparing the string `01:30` hides a 60-minute gap.
12. **Testing only one Feb 29 date:** include a common year, a year divisible by 100, and one divisible by 400 to verify the full leap-year rule.

## 12. Checklist for completing a date/time test suite

1. Identify whether the value is a calendar date, local time, offset date-time, or instant.
2. Specify accepted formats, `Locale`, `ZoneId`, and policies for blank/malformed strings.
3. Test valid dates, month ends, nonexistent dates, and all special leap-year cases.
4. When strict parsing is needed, use `ResolverStyle.STRICT` or a standard formatter verified as strict; never let SMART rewrite bad dates.
5. For region-zoned schedules, call `ZoneRules.getValidOffsets` to detect normal/gap/overlap separately; implement an explainable and testable business policy.
6. Compare `Instant` values when verifying points in time; check both offset and zone ID if the UI must preserve the scheduler's intent.
7. Write JDK unit tests and Spring MVC/JSON integration tests matching real data sources.
8. Keep tests independent of run date, default time zone, and host locale; record JDK/tzdb for tests tied to future calendar changes.

### References

- [Java 21 — Year.isLeap (leap year rules)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html).
- [Java 21 — ResolverStyle: STRICT, SMART, LENIENT](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html).
- [Java 21 — DateTimeFormatter: parsing and resolver styles](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).
- [Java 21 — ZoneRules.getValidOffsets and getTransition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html).
- [Java 21 — ZonedDateTime and handling gaps/overlaps](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html).
- [Spring Framework — @DateTimeFormat](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html).
- [Spring Framework — Type Conversion in MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html).
- [Spring Framework — Date and Time Formatting with JDK 20 and higher](https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher).
