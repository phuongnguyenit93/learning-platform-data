# Overview of java.time and Legacy Date-Time APIs in Java

> Scope: Java Core, **Overview** group. This lesson helps you choose the right date-time data types, understand time zones and timelines, use the **java.time** API from Java 8 (for example, running with Java 17+), as well as identify and convert legacy APIs when maintaining systems.

## 1. Why Does Java Have Multiple Date-Time APIs?

A "date-time" value can answer different questions:

- **Calendar date**: birthday 24/10, due date, holiday; no need to pinpoint a global instant yet.
- **Local wall-clock time**: store opens at 08:30; this number alone does not indicate a date or time zone.
- **Local date and time**: meeting at 09:00 on 25/10/2026; you need to know where it takes place to resolve it to an actual instant.
- **An actual instant on the timeline**: the moment an event is recorded, which can be compared and sorted even when machines are in different time zones.
- **Elapsed time**: 90 minutes or 3600 seconds; different from "one calendar month" because months have different numbers of days.

Early APIs such as **java.util.Date**, **Calendar**, and **SimpleDateFormat** evolved across multiple versions with confusing designs, mutable state, and many inconvenient conventions. **java.time**, introduced in Java 8 under JSR-310 and continuing in Java 17+, separates these concepts into distinct types, with most classes being immutable and thread-safe.

### Three Foundational Concepts

1. **Instant**: a point on the UTC timeline, for example 2026-10-24T10:15:30Z. The letter Z denotes the UTC+00:00 offset. An Instant by itself does not contain a local time zone.
2. **Offset**: the difference from UTC at a given point in time, for example +07:00. An offset is only a difference; it does not contain seasonal time-change rules or regional history.
3. **Time zone (ZoneId)**: a region containing a set of offset rules over time, for example **Asia/Ho_Chi_Minh** or **America/New_York**. A ZoneId can use different offsets on different dates.

The same Instant 2026-10-24T10:15:30Z is displayed in Ho Chi Minh City as 17:15:30 on 24/10/2026. Changing the display time zone **does not change the Instant**. Conversely, the string "24/10/2026 17:15" alone is not enough to uniquely identify an Instant without providing an offset or time zone and resolving daylight saving time cases.

## 2. Map of java.time Types: Choosing the Right Type

| Type | Meaning | Suitable Use Cases | What It Does Not Contain |
| --- | --- | --- | --- |
| **LocalDate** | Year, month, day in the ISO calendar | Birthday, due date, delivery date | Time, offset, zone |
| **LocalTime** | Hour, minute, second, nanosecond | Opening hours, scheduled alarm time | Date, offset, zone |
| **LocalDateTime** | Local date + time | Appointment time at a known location; SQL TIMESTAMP data without a zone | Offset, zone; not an Instant on its own |
| **Instant** | A point on the timeline | Record created/updated timestamps, events, logs, token expiration | Local time, zone |
| **OffsetDateTime** | LocalDateTime + UTC offset | Exchanging instants with offsets over APIs | Regional rules such as America/New_York |
| **ZonedDateTime** | Date-time + ZoneId and resolved offset | Regional meetings, scheduling across DST | Not a recurring schedule rule itself |
| **ZoneId** | Time zone identifier and rules | Displaying in the user's region, scheduled appointments | Not a timestamp |
| **ZoneOffset** | Fixed offset such as +07:00 | Protocols with offsets, UTC conversion | Does not contain a region's DST history |
| **Duration** | Time amount based on seconds/nanoseconds | Timeouts, execution duration, distance between two Instants | Calendar months/years |
| **Period** | Calendar years/months/days | Adding one month, age in days, calendar terms | Actual elapsed hours/minutes/seconds |
| **YearMonth**, **MonthDay** | Month-year; day-month | Monthly reporting period; annual recurring anniversary | Remaining fields |
| **Clock** | Replaceable time source | Getting the current time in business logic and testing | Not a stored date-time |
| **DateTimeFormatter** | Parse/format rules | Input/output formatting, APIs, UI | Does not store an instant |

**Quick selection rules:**

- To store **when an event happened**: prefer **Instant**; convert to **ZonedDateTime** at the display boundary.
- To store a **business date** (without time): **LocalDate**.
- To store a **daily 09:00 appointment in a region**: store **LocalTime** + **ZoneId** (and the recurrence rule); generate the instant only when resolving a specific date.
- To send a **date-time with an offset**: **OffsetDateTime** or an ISO 8601 string with an offset; to reconstruct the exact appointment region, also store **ZoneId**.
- **LocalDateTime** is suitable for describing local calendar time, but inappropriate if intended as a global timestamp.

## 3. Creation, Transformation, Comparison

Factory methods make code express intent clearly:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime meeting = LocalDateTime.of(date, time);
Instant timestamp = Instant.parse("2026-10-24T10:15:30Z");
ZoneId region = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime inVietnam = timestamp.atZone(region);
OffsetDateTime withOffset = inVietnam.toOffsetDateTime();
~~~

This is an **illustrative snippet**: to compile it standalone, place it inside a method and import the classes from java.time.

- **plusDays**, **minusWeeks**, **plusMonths**, **withDayOfMonth** return a **new object** without modifying the original. If you call date.plusDays(1) without assigning or using the result, date does not change.
- **isBefore**, **isAfter**, **isEqual** compare compatible values; **equals** on ZonedDateTime also checks date-time/zone information. To compare **the same global instant** between two ZonedDateTime values in different zones, use **toInstant().equals(...)** or **isEqual(...)**.
- **plusMonths(1)** follows calendar months: 31/01/2026 plus one month becomes 28/02/2026, not adding 30 days' worth of seconds.
- **TemporalAdjusters.lastDayOfMonth()** and other adjusters help express calendar policies without manually counting days and months.

Do not convert LocalDateTime to Instant by assuming it is implicitly in UTC. You must have a **ZoneId/ZoneOffset** determined by business rules, for example **meeting.atZone(region).toInstant()**; at daylight saving time boundaries, also consider the rules in section 6.

## 4. Standalone Runnable Java 17+ Example

Create the file **DateTimeOverview.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.TemporalAdjusters;

public class DateTimeOverview {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-10-24T00:00:00Z"), vietnam);

        LocalDate today = LocalDate.now(fixedClock);
        LocalDate dueDate = today.plusMonths(1)
                .with(TemporalAdjusters.lastDayOfMonth());

        Instant event = Instant.parse("2026-10-24T10:15:30Z");
        ZonedDateTime localEvent = event.atZone(vietnam);
        DateTimeFormatter display =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm VV");

        DateTimeFormatter strictDate =
                DateTimeFormatter.ofPattern("dd/MM/uuuu")
                        .withResolverStyle(ResolverStyle.STRICT);
        LocalDate parsed = LocalDate.parse("31/12/2026", strictDate);

        long elapsedMinutes = Duration.between(
                event, event.plusSeconds(5_400)).toMinutes();

        System.out.println("Hôm nay: " + today);
        System.out.println("Hạn: " + dueDate);
        System.out.println("Giờ địa phương: " + localEvent.format(display));
        System.out.println("Ngày đọc: " + parsed);
        System.out.println("Phút trôi qua: " + elapsedMinutes);
    }
}
~~~

Compile/run with JDK 17+ (using a UTF-8-capable terminal to display Vietnamese):

~~~bash
javac -encoding UTF-8 DateTimeOverview.java
java DateTimeOverview
~~~

Expected output:

~~~text
Hôm nay: 2026-10-24
Hạn: 2026-11-30
Giờ địa phương: 24/10/2026 17:15 Asia/Ho_Chi_Minh
Ngày đọc: 2026-12-31
Phút trôi qua: 90
~~~

Because **Clock.fixed** is used, the output does not depend on the run date or the machine's clock. 10:15Z converts to 17:15 in the Vietnam time zone; the due date is the last day of the next month. **Duration** measures 5400 seconds = 90 minutes; **LocalDate** and **Period** are more suitable when the problem is calculated by calendar.

## 5. Parsing, Formatting, and Data Validation

**DateTimeFormatter** is immutable and thread-safe; it can be reused as a constant. Prefer ISO 8601 at system boundaries:

- **DateTimeFormatter.ISO_LOCAL_DATE** for 2026-10-24.
- **DateTimeFormatter.ISO_INSTANT** for 2026-10-24T10:15:30Z.
- **DateTimeFormatter.ISO_OFFSET_DATE_TIME** for strings with an offset, for example 2026-10-24T17:15:30+07:00.
- Custom patterns, such as **dd/MM/uuuu**, serve user-facing display formats. A Locale can be specified when using month or weekday names.

Easily confused pattern symbols:

| Pattern | Meaning | Common Mistake |
| --- | --- | --- |
| **uuuu** | Proleptic year in the ISO system | When parsing with STRICT, uuuu is commonly used instead of yyyy (year-of-era) when era is absent |
| **MM** | Month | **mm** is minute |
| **dd** | Day of month | **DD** is day of year |
| **HH** | Hour 0–23 | **hh** is hour 1–12, requiring AM/PM |
| **XXX** | Offset in +07:00 format | An offset does not replace a regional ZoneId |
| **VV** | ZoneId | Only formats when the value has an appropriate zone |

When receiving dates from users, clearly define the pattern/Locale, parse with **ResolverStyle.STRICT** when nonexistent dates (such as 31/02) must be rejected, handle **DateTimeParseException**, and report input field errors. Do not infer the time zone of data solely from its text format. If an API transmits timestamps, require strings with Z or an offset and parse them into Instant/OffsetDateTime.

## 6. Time Zones, DST, and Two Different Kinds of Addition

Regional time zones depend on historical rule sets (tzdb), whereas an offset is just a number. Especially in regions with **daylight saving time (DST)**:

- **Gap**: there are local times that do not exist because the clock jumps forward. For example, in **America/New_York**, 02:30 on 08/03/2026 falls into the skipped-hour gap. When resolving LocalDateTime with **atZone**, Java typically pushes the invalid time forward past the gap.
- **Overlap**: there are local times that occur twice when the clock falls back. For example, 01:30 on 01/11/2026 in New York corresponds to two offsets; atZone normally picks the earlier offset by default. If strict disambiguation is required, you must provide an offset/Instant or check **ZoneRules.getValidOffsets(localDateTime)** and handle the choice.
- **A calendar day is not always equal to 24 real hours**. **plusDays(1)** on ZonedDateTime follows the local calendar; **plusHours(24)** shifts 24 hours on the timeline. Across a DST start date, the two results can differ by one hour on the clock.

Standalone illustration; the following statements assume they are placed in a method with java.time imported:

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime noon = ZonedDateTime.of(
        2026, 3, 7, 12, 0, 0, 0, newYork);
System.out.println(noon.plusDays(1));
// 2026-03-08T12:00-04:00[America/New_York]
System.out.println(noon.plusHours(24));
// 2026-03-08T13:00-04:00[America/New_York]
~~~

For recurring schedules in local time, store **time + zone + recurrence rule**; compute the next occurrence based on the date and handle gaps/overlaps according to business policy. Do not hardcode +07:00/+01:00 for regions that have time-varying transition rules. Always test transition dates for the regions you actually support.

## 7. Duration, Period, and Date Calculations

**Duration** represents seconds and nanoseconds, typically applied between two Instants (or compatible temporal types). **Period** represents calendar years/months/days, typically applied between LocalDates.

~~~java
Instant start = Instant.parse("2026-10-24T00:00:00Z");
Instant end = start.plusSeconds(3_600);
Duration elapsed = Duration.between(start, end); // PT1H

LocalDate birth = LocalDate.of(2000, 10, 24);
LocalDate reference = LocalDate.of(2026, 10, 24);
Period age = Period.between(birth, reference);     // P26Y
~~~

These are snippets that can be placed in a method after importing java.time.

If asking **how many full calendar days** are between two dates, use **ChronoUnit.DAYS.between(date1, date2)**. If asking **how many hours have elapsed** between two instants, use **Duration.between(instant1, instant2)**. **Period.getDays()** only returns the *days* component of the Period (not the total number of days including years and months): for example, an interval of 1 month and 6 days has getDays() equal to 6.

You should clearly define boundary rules for time intervals. For event intervals, the **[start, end)** form (inclusive start, exclusive end) generally prevents adjacent intervals from overlapping at boundaries; check **!time.isBefore(start) && time.isBefore(end)** for Instant.

## 8. Legacy APIs: History, Limitations, and Mapping

| Legacy API | Reality / Issues | Modern Equivalent |
| --- | --- | --- |
| **java.util.Date** | Tied to an instant with millisecond precision; mutable; **toString()** displays in the machine's default zone, which does not mean Date "stores a timezone" | **Instant** |
| **java.util.Calendar**, **GregorianCalendar** | Manages date-time fields + TimeZone; mutable, many implicit rules; **Calendar.JANUARY = 0** | **ZonedDateTime** / **LocalDate** depending on need |
| **java.text.SimpleDateFormat** | Pattern-based parse/format, **mutable and not thread-safe**; lenient parsing by default | **DateTimeFormatter** |
| **java.sql.Date** | Represents SQL DATE (date, no time) | **LocalDate** |
| **java.sql.Time** | Represents SQL TIME (time, no date) | **LocalTime** |
| **java.sql.Timestamp** | JDBC timestamp with nanoseconds; timezone semantics depend on SQL type/driver | **LocalDateTime**, **Instant**, or **OffsetDateTime** depending on column and contract |
| **System.currentTimeMillis()** | Milliseconds since the Unix epoch; convenient in system APIs but easily loses type semantics | **Instant.now(clock)** |

**Practical notes on Calendar:** Calendar months are 0–11, whereas LocalDate uses months 1–12. Getting **Calendar.HOUR** (12-hour) differs from **Calendar.HOUR_OF_DAY** (24-hour); Calendar and SimpleDateFormat have lenient settings and mutable state. Avoid sharing a single SimpleDateFormat instance across multiple threads.

**Joda-Time** was widely used before Java 8. For new code on Java 17+, prefer java.time; for legacy projects, migrate one functional boundary at a time and re-verify time zones, date addition, formatting, and parsing rules rather than mechanically replacing class names.

### Converting When Integrating with Legacy Libraries

The following snippets assume java.time.*, java.util.Date, java.util.GregorianCalendar, and java.sql.Timestamp are imported; place them inside a method:

~~~java
Instant instant = Instant.parse("2026-10-24T10:15:30Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

// java.util.Date stores an instant with millisecond precision.
Date oldDate = Date.from(instant);
Instant backToInstant = oldDate.toInstant();

// GregorianCalendar preserves the object's zone.
GregorianCalendar oldCalendar =
        GregorianCalendar.from(instant.atZone(zone));
ZonedDateTime restored = oldCalendar.toZonedDateTime();

// SQL DATE and TIME carry local date/time semantics.
java.sql.Date sqlDate =
        java.sql.Date.valueOf(LocalDate.of(2026, 10, 24));
LocalDate fromSqlDate = sqlDate.toLocalDate();

java.sql.Time sqlTime =
        java.sql.Time.valueOf(LocalTime.of(9, 30));
LocalTime fromSqlTime = sqlTime.toLocalTime();

// Timestamp supports conversion via Instant; verify DB/driver mapping.
Timestamp sqlTimestamp = Timestamp.from(instant);
Instant fromTimestamp = sqlTimestamp.toInstant();
~~~

Distinguish **java.util.Date** from **java.sql.Date** in imports. In particular, **java.sql.Date.toInstant()** and **java.sql.Time.toInstant()** **throw UnsupportedOperationException**: they lack the time/date portion needed to determine an Instant on their own; use **toLocalDate()** / **toLocalTime()** and only attach a zone/date when business logic actually has that information. Converting from java.time to legacy types may lose nanosecond precision when the target only stores milliseconds.

Do not use **new Date().getYear()**, **getMonth()**, **getDate()**, or legacy Date constructors: most are deprecated and have offset conventions (year counted from 1900, month starting at 0). Do not use **SimpleDateFormat** as a static field shared across multiple threads; replace it with **DateTimeFormatter**.

## 9. Interacting with Databases, REST, and Other Systems

**Design according to data semantics before choosing SQL types**:

- Birthdays/business dates: SQL **DATE** ↔ **LocalDate**.
- Date-independent opening hours: SQL **TIME** ↔ **LocalTime**.
- Explicit date-time without offset: SQL **TIMESTAMP** (without time zone) usually ↔ **LocalDateTime**, though the meaning must be defined in the application.
- Global event timestamps: the application uses **Instant**; in the database, choose a type with clear UTC/timezone semantics, and verify the driver, database, and session zone. JDBC 4.2 supports many java.time types; support for **Instant**, **OffsetDateTime**, and handling of SQL TIMESTAMP WITH TIME ZONE can vary by driver/database. Do not assume every database stores a regional ZoneId.

For REST/JSON, standardize contracts such as **2026-10-24T10:15:30Z** for events or **2026-10-24** for pure dates. Explicitly specify the time zone in the API if sending local date-time; avoid ambiguous strings like **24/10/26 10:15**. When regional appointments need to be reconstructed, store **ZoneId** separately because today's offset may differ from the offset on the appointment date.

The JVM's default time zone (**ZoneId.systemDefault()**) can change depending on the server/container/configuration. Only use it when the system intentionally relies on the environment; if logic requires a specific region, obtain ZoneId from configuration/contracts. tzdb rules can be updated via the JDK, so long-term scheduling applications need a policy for when governments change time rules.

## 10. Designing Testable Code

Avoid scattering calls to **Instant.now()** and **LocalDate.now()** in logic, which makes unit tests depend on execution time. Inject **Clock** from the outside:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

public class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }

    public LocalDate businessToday(ZoneId zone) {
        return LocalDate.now(clock.withZone(zone));
    }
}
~~~

This is a **compilable class** when saved as ExpiryPolicy.java. In production you can inject **Clock.systemUTC()**; in unit tests use **Clock.fixed(Instant.parse("2026-10-24T00:00:00Z"), ZoneId.of("UTC"))**. That way, calculations for today's date and expiration instants can be reproduced accurately. For performance timing (elapsed monotonic time) within a single process, consider **System.nanoTime()** to measure intervals; it does not represent a storable/exchangeable timestamp.

## 11. Common Mistakes to Avoid

1. **Using LocalDateTime as a UTC timestamp**: it lacks a zone/offset, so two systems may interpret it as two different Instants.
2. **Storing 09:00 as an Instant to model a recurring schedule**: after a DST change, 09:00 on the local clock may become 08:00 or 10:00. Store the calendar rule + ZoneId.
3. **Mixing up Period and Duration**: a calendar day across a DST transition can be 23 or 25 hours long; a month does not have a fixed number of seconds.
4. **Relying on the default time zone** when formatting/parsing/logging or converting from LocalDateTime to Instant.
5. **Confusing MM and mm; yyyy and uuuu; HH and hh**, especially when using strict parsing or BC years.
6. **Confusing java.util.Date and java.sql.Date**: similar names, but different meanings and toInstant support.
7. **Using SimpleDateFormat across multiple threads** or keeping a shared mutable Calendar.
8. **Assuming a fixed offset represents an entire region** or failing to test gaps/overlaps.
9. **Comparing date-time strings** instead of parsing into appropriate data types (especially when day/month order varies by locale).
10. **Assuming nanoseconds are preserved across Date/milliseconds or databases** even when the storage layer loses precision.

## 12. How to Make Decisions When Maintaining Systems

For each data field, answer in order:

1. Is the data a **calendar date**, **local time**, **local date-time**, **global instant**, or **duration/period**?
2. Is a **regional ZoneId** needed, or just an offset? If it is a recurring schedule, how must DST rules be applied?
3. When serializing over JSON/SQL, does the data contract preserve the original meaning? Does the SQL column/driver map it appropriately?
4. Should calculations follow the **calendar** (Period, plusDays) or **real seconds** (Duration, Instant)?
5. Have tests pinned **Clock**, time zones, end-of-month dates, leap years, and gap/overlap cases?

### Self-Practice

- **Date of birth**: choose LocalDate, not Instant, because a birthday is not a UTC instant.
- **Payment completion timestamp**: choose Instant; format using ZoneId on the user's screen.
- **Daily job running at 09:00 in New York**: store LocalTime 09:00 + ZoneId America/New_York + recurrence rule; determine each run's Instant individually.
- **30-second timeout**: use Duration.ofSeconds(30), not Period.
- **Reading legacy java.util.Date data**: use toInstant() then pick a zone for display; do not pass toString() directly into an API as a standard string.
- **Reading java.sql.Date**: use toLocalDate(), do not call toInstant().

## References

- [Oracle Java SE 17 — java.time package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): Instant, LocalDate, LocalDateTime, ZonedDateTime models.
- [Oracle Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): patterns, resolvers, and thread safety.
- [Oracle Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): zone rules and arithmetic across DST.
- [Oracle Java SE 17 — java.sql.Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Date.html): DATE mapping and limitations of toInstant().
