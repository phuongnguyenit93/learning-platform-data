# Date and Time in Programs: Concepts, Roles, and Common Problems

An application must be able to answer "when did the event happen?", "what is today's date?", "how much time has elapsed?", "what instant does a user's 9:00 AM appointment in another country correspond to?", and "when does the verification code expire?". These are **different questions**, even though they all relate to date and time. Using the same data type or arbitrarily adding and subtracting hours for every case can cause bugs at day boundaries, end-of-month transitions, daylight saving time, or across multiple servers.

This lesson introduces the mental model, the role of date and time in software, how to choose `java.time` data types, and common real-world problems. The goal is to understand **the meaning of the data before choosing an API**, so that later in-depth lessons have a solid foundation.

## 1. What Is Date and Time Used For?

| Scenario | Actual Question | Core Data |
| --- | --- | --- |
| Logging, order creation, auditing | At what point on the timeline did the event occur? | Absolute instant |
| Birthdays, holidays, settlement dates | Which calendar date is it? | Calendar date |
| Opening hours 08:00–17:00 | What time is it on the local clock? | Time of day, possibly with a region |
| Meeting at 09:00 in Hanoi | Which instant does that local time correspond to? | Date-time + time zone |
| OTP valid for 5 more minutes | How long has passed, and at what point does it expire? | Duration + expiration instant |
| Running a "today" report | Whose time zone defines "today"? | Day boundaries in the business time zone |
| Task execution stats: 125 ms | How much time did the task take? | Elapsed-time clock |
| End-of-month reminder | Does the next month have the corresponding day? | Calendar rules, not just a number of seconds |

The common thread is that systems need to **determine, display, calculate, compare, and exchange** time-related data. However, a "date" is not synonymous with an "instant", "one month" is not synonymous with "30 days", and "9:00 AM" does not carry enough information to identify an instant.

## 2. Five Concepts You Must Distinguish

### 2.1. Calendar Date and Clock Time

A **calendar date** consists of year, month, and day, such as `2026-10-24`. Birthdays, public holidays, or invoice dates usually only need this concept. A date by itself **contains no time of day, offset, or time zone**.

A **local time** (time of day) such as `09:30:00` also carries no date or region. Combining the two gives a **local date-time**, for example `2026-10-24 09:30`. However, this is still just a reading on a clock in an unspecified place; it **does not uniquely determine a global instant**.

### 2.2. Absolute Point in Time (Instant)

An **instant** represents a single, unique point on the timeline. For the same event, people in two countries may look at their clocks and see two different times, yet the event's instant is the same.

For example, `2026-06-01T10:15:30Z` is an instant expressed in UTC (`Z` indicates an offset of 0). In Vietnam, that same instant is displayed as `2026-06-01 17:15:30 +07:00`. These are **two ways of displaying the same event**.

The **Unix epoch** is the instant `1970-01-01T00:00:00Z`. Numeric timestamps counting seconds or milliseconds from this epoch are common in distributed systems. You must agree on the **unit**: seconds and milliseconds differ by a factor of 1,000; do not guess solely from the number of digits. `Instant` preserves the semantics of a point in time more clearly than a raw number.

### 2.3. UTC Offset vs. Time Zone

An **offset** such as `+07:00` only indicates the difference from UTC **at a given instant**. A **time zone** such as `Asia/Ho_Chi_Minh`, `Europe/Paris`, or `America/New_York` is a region identifier together with a set of rules that determine the offset over time, including historical changes and daylight saving time (DST) in some regions.

A fixed offset does not fully describe a locality's rules across different seasons or years. A recurring meeting at "09:00 in New York every Monday" needs a **regional `ZoneId`**, not just the offset of the first day.

### 2.4. Duration and Period

A **Duration** represents an amount of elapsed time, such as 30 seconds, 15 minutes, or 24 hours. A **Period** represents a calendar-based span in years, months, and days, such as adding one month or one year.

"After exactly 24 hours" and "at the same time tomorrow" usually coincide, but can differ in regions that observe daylight saving time transitions. "Adding one month" is not always "adding 30 days". Rely on business rules to choose the right calculation.

### 2.5. Wall Clock and Elapsed-Time Clock

A **wall clock** is used to know "now" and attach timestamps to events. The system clock can be synchronized or adjusted. **Measuring duration**, such as code execution time, requires an appropriate measurement source: `System.nanoTime()` is useful for taking the difference between two readings within the **same JVM process**, but its absolute value is not a timestamp and must not be used to store date and time. Do not use the difference between two wall-clock timestamps as an accurate performance measurement for very short tasks.

## 3. Choosing the Right Java Types

| `java.time` Type | Meaning | Example Usage |
| --- | --- | --- |
| `LocalDate` | Calendar date without time or time zone | Birthdays, holidays, date-based deadlines |
| `LocalTime` | Time within a day | Opening hours, fixed appointment times |
| `LocalDateTime` | Local date and time without a region | User-entered time before a location is determined |
| `Instant` | Absolute point on the timeline | `createdAt`, `updatedAt`, logs, events |
| `OffsetDateTime` | Date-time with a specific offset | API payloads carrying an offset |
| `ZonedDateTime` | Date-time with a regional time zone and rules | Events, local appointments |
| `ZoneId` / `ZoneOffset` | Region / fixed offset | Conversion and display |
| `Duration` | Time span measured in seconds/nanoseconds | Timeouts, OTP validity, processing duration |
| `Period` | Calendar span in years, months, days | Age, adding by months, calendar terms |
| `Clock` | Replaceable time source | "Now" logic, testing |

The core date-time classes in `java.time` are immutable: adding, subtracting, or converting produces a new value, which helps reduce shared-state bugs. `DateTimeFormatter` handles parsing and formatting strings. In new code, prefer `java.time`; legacy systems may use `java.util.Date` or `Calendar`, which require care during integration.

**Quick pick:** "Which date?" → `LocalDate`; "what time?" → `LocalTime`; "when did the event actually happen?" → `Instant`; "what time in which region?" → `ZonedDateTime`; "how long?" → `Duration` or `Period`.

## 4. Converting Between Instants and Local Time

Suppose a server records an order at `2026-06-01T10:15:30Z`. The UI can display 17:15:30 in Vietnam and 10:15:30 in UTC. **The `Instant` does not change**; only the local perspective changes.

The right flow is: `Instant` → `atZone(ZoneId)` → `ZonedDateTime` for display. In the reverse direction, you must have **both the local date-time and the `ZoneId`/offset** to convert back to an instant. Do not "manually add 7 hours and save it", and do not assume the server's time zone is the user's time zone.

If the data is only `LocalDateTime.of(2026, 6, 1, 9, 0)`, the system **does not yet know** whether that is 09:00 in Hanoi, Paris, or New York. Turning this value into UTC on its own alters the original meaning.

## 5. Runnable Java 17+ Example with Fixed Output

Use `Clock.fixed` so the result is independent of the real-world clock. The example shows an instant, displays the same instant in Vietnam, calculates a deadline in calendar days, and computes an expiration window in minutes.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public class DateTimeOverviewDemo {
    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-06-01T10:15:30Z"),
                ZoneOffset.UTC
        );

        Instant createdAt = Instant.now(clock);
        ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime displayedTime = createdAt.atZone(userZone);

        LocalDate today = LocalDate.now(clock.withZone(userZone));
        LocalDate dueDate = LocalDate.of(2026, 6, 15);
        Period untilDue = Period.between(today, dueDate);

        Instant expiresAt = createdAt.plus(Duration.ofMinutes(30));
        long minutes = Duration.between(createdAt, expiresAt).toMinutes();

        DateTimeFormatter fmt =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss XXX");

        System.out.println("Thoi diem UTC: " + createdAt);
        System.out.println("Gio Viet Nam: " + displayedTime.format(fmt));
        System.out.println("Ngay den han: " + dueDate);
        System.out.println("So ngay lich: " + untilDue.getDays());
        System.out.println("So phut hieu luc: " + minutes);
        System.out.println("Het han UTC: " + expiresAt);
    }
}
~~~

Save it with the exact name `DateTimeOverviewDemo.java`. Compile and run:

~~~bash
javac DateTimeOverviewDemo.java
java DateTimeOverviewDemo
~~~

Output:

~~~text
Thoi diem UTC: 2026-06-01T10:15:30Z
Gio Viet Nam: 2026-06-01 17:15:30 +07:00
Ngay den han: 2026-06-15
So ngay lich: 14
So phut hieu luc: 30
Het han UTC: 2026-06-01T10:45:30Z
~~~

`createdAt` and `expiresAt` are absolute instants. `displayedTime` is only for presenting to the user. `dueDate` is a calendar date, not UTC midnight. `Period.between` returns year/month/day **components**; `getDays()` gives 14 here because both dates are in the same month. If you want the **total number of days between two dates** across multiple months, use `ChronoUnit.DAYS.between(startDate, endDate)` instead of taking only `Period.getDays()`.

## 6. Common Problems

### 6.1. Recording Creation/Update Times and Expiration

Use `Instant` for events that need to be pinned on the timeline:

~~~java
Instant createdAt = Instant.now();
Instant expiresAt = createdAt.plus(Duration.ofMinutes(15));
Instant now = Instant.now();
boolean expired = !now.isBefore(expiresAt);
~~~

This snippet requires `import java.time.Instant;` and `import java.time.Duration;`. The rule `!now.isBefore(expiresAt)` means that **at the exact expiration instant, it is already expired**. In an operation with multiple related checks, capture `now` once so decisions remain consistent. For security-sensitive expirations, rely on a trustworthy server-side clock; do not rely solely on a client-supplied timestamp.

### 6.2. Birthdays, Holidays, and Delivery Dates

Use `LocalDate` if the data only needs a **calendar date**. A person born on October 24 should not see October 23 in a UI in a negative-offset region just because their birthday was stored as a UTC timestamp.

Only when asking "all transactions on October 24 in Vietnam time" do we need to **convert day boundaries** into instants for the business region:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate date = LocalDate.of(2026, 10, 24);

Instant fromInclusive = date.atStartOfDay(zone).toInstant();
Instant toExclusive = date.plusDays(1)
        .atStartOfDay(zone).toInstant();

boolean inDay = !eventInstant.isBefore(fromInclusive)
        && eventInstant.isBefore(toExclusive);
~~~

This is an **illustrative snippet**; the `eventInstant` variable needs to be declared from context. The half-open interval **[start of day, start of next day)** avoids overlapping events between two consecutive days without guessing the "last second of the day" based on millisecond precision. In regions with DST transitions, two consecutive day boundaries may not be exactly 24 hours apart.

### 6.3. Regional Meeting Schedules

A meeting at "09:00 on June 15, 2026 in Hanoi" needs both a local date-time and a `ZoneId`:

~~~java
LocalDateTime localStart = LocalDateTime.of(2026, 6, 15, 9, 0);
ZoneId meetingZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime meeting = localStart.atZone(meetingZone);
Instant actualMoment = meeting.toInstant();
~~~

This is also an illustrative snippet; import `LocalDateTime`, `ZoneId`, `ZonedDateTime`, and `Instant`. You can store `actualMoment` for a single specific meeting occurrence. If the meeting **repeats at 09:00 every Monday in local regional time**, store both the recurrence rule and the `ZoneId`; simply adding 24 hours to the first session's instant will produce the wrong local time in regions that switch DST.

### 6.4. "Add One Day", "Add One Month", and Durations

- `Duration.ofHours(24)`: exactly 24 elapsed hours.
- `ZonedDateTime.plusDays(1)`: the next calendar day in the region, usually preserving the local wall-clock time.
- `LocalDate.plusMonths(1)`: adds one calendar month; for example, 2026-01-31 plus one month becomes 2026-02-28.
- `Duration.between(startInstant, endInstant)`: computes the elapsed length between two instants.
- `Period.between(startDate, endDate)`: computes the difference in calendar year/month/day components.

Do not replace `Period.ofMonths(1)` with `Duration.ofDays(30)` when the business rule genuinely means "the next month". In regions with daylight saving time, "same time tomorrow" and "24 hours later" can yield two different instants.

### 6.5. Parsing and Formatting Strings

Prefer clear, stable formats at system boundaries and locale-aware formats in the user interface:

~~~java
LocalDate date = LocalDate.parse("2026-10-24"); // ISO date
Instant event = Instant.parse("2026-06-01T10:15:30Z");

DateTimeFormatter viDate =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
String text = date.format(viDate); // "24/10/2026"
~~~

This illustrative snippet requires importing `LocalDate`, `Instant`, and `DateTimeFormatter`. `LocalDate.parse` understands ISO date strings by default; to parse `"24/10/2026"`, you must pass an explicit formatter. In patterns, `MM` is **month** and `mm` is **minute**; `HH` is 0–23 hour and `hh` is 12-hour clock. Use `uuuu` when you need the ISO calendar year. When formatting textual month or day names, set an explicit `Locale`; do not rely on the server's default locale.

### 6.6. Data Across APIs and Databases

For absolute events, ISO-8601 format with an explicit UTC or offset designator (e.g., `2026-06-01T10:15:30Z`) avoids ambiguity. When you need to preserve "09:00 at the venue", also store the time zone and calendar rules in the business domain.

Be careful with SQL `DATE`, `TIMESTAMP`, and `TIMESTAMP WITH TIME ZONE` types. **How offsets/time zones are preserved and converted depends on the DBMS, driver, and ORM**—do not guess from the type name alone. Check precision (seconds, milliseconds, microseconds, etc.) when reading and writing. When data is purely a calendar date, use a date type rather than forcing it into an instant.

When sending numeric epochs over JSON, the API documentation must state the unit clearly. If multiple services write logs, configure time zones and synchronize clocks; timestamps do not guarantee absolute ordering of distributed events when machine clocks drift. Complex ordering problems may require a dedicated sequence or logical ID.

### 6.7. Recurring Schedules

Distinguish "run again every 24 hours" from "run at 08:00 every day in the store's local time". The former is a duration; the latter is a **calendar rule + `ZoneId`**. A monthly schedule on the 31st must specify how to handle months without 31 days. "Next business day" also requires weekend rules and a holiday list; `LocalDate.plusDays(1)` does not know about business days on its own.

## 7. Daylight Saving Time (DST) and Invalid Local Times

In some regions, the offset changes seasonally. This creates:

1. **Gap:** the clock jumps forward, so a range of local times does not exist (for example, 02:30 on the night of a spring-forward transition in an observing region).
2. **Overlap:** the clock falls back, so a local hour can occur **twice**, corresponding to two different instants.

Therefore, converting `LocalDateTime` to `ZonedDateTime` is not always a one-to-one mapping. `atZone` has a default resolution rule, but critical ticketing or booking schedules need an explicit policy: reject the invalid time, shift the time, or select a specific offset.

You can use `ZoneId.getRules().getValidOffsets(localDateTime)`: a list with 0 offsets means a gap; 1 means normal; 2 means an overlap. Do not replace `ZoneId.of("America/New_York")` with `ZoneOffset.ofHours(-5)` for all months. Time zone rules can be updated when governments change regulations; the system's runtime and `tzdb` must also be kept up to date.

## 8. Testing and Time Measurement

Code that calls `Instant.now()` everywhere is hard to test for expirations, midnight rollovers, or end-of-month boundaries. Use an injectable `Clock` in tests:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-06-01T10:15:30Z"),
        ZoneOffset.UTC
);
Instant now = Instant.now(fixed);
Instant deadline = Instant.parse("2026-06-01T10:15:30Z");
boolean expired = !now.isBefore(deadline); // true
~~~

This illustrative snippet requires importing `Clock`, `Instant`, and `ZoneOffset`. You should test **before**, **exactly at**, and **after** the deadline; end-of-month and leap years; different time zones; and DST gaps/overlaps if the problem involves local schedules.

To measure execution time within the same JVM:

~~~java
long started = System.nanoTime();
// Run the work to be measured.
long elapsedNanos = System.nanoTime() - started;
~~~

`elapsedNanos` is a **measured time difference**; do not convert it to a date-time or compare it against an epoch. For timeouts in real systems, consider timers/schedulers, clock skew, and the consistency of the time source.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Storing a birthday as UTC midnight | Users in other regions may see the previous day | Use `LocalDate` |
| Storing `LocalDateTime` as an absolute instant | Lacks time zone/offset to identify an instant | Use `Instant` or data with a zone/offset |
| Using a fixed offset for long-term local schedules | Breaks when time zone rules/DST change | Keep the regional `ZoneId` |
| Assuming "tomorrow" is always 24 hours later | Wrong across DST transition boundaries | Distinguish calendar addition from `Duration` |
| Using `Period.getDays()` as total days across months | It is only the day component of the period | Use `ChronoUnit.DAYS.between` |
| Confusing epoch seconds and milliseconds | Massive timestamp skew | Specify the unit; use the `Instant` API |
| Using `MM` for minutes | Confuses month with minute | Use `mm` and test the formatter |
| "Changing time zone" by manually adding hours | Corrupts the instant's meaning and breaks DST | Use `atZone` and `ZoneId` |
| Trusting client timestamps for expiration checks | Clients can alter their own clock | Use a trustworthy server-side time source |
| Using `23:59:59` as the end of a day | Misses sub-second fractions | Use `[start of day, start of next day)` |
| Benchmarking with normal wall-clock differences | The system clock can be adjusted | Use `System.nanoTime()` differences |

## 10. Process for Choosing a Solution for a New Requirement

1. **Identify the meaning:** calendar date, time of day, local date-time, instant, or duration/period?
2. **Identify the time zone owner:** the user, the branch, the event venue, or the system?
3. **Choose what to preserve:** the same instant, or the same local time upon recurrence?
4. **Define the calculation:** add 24 real hours, add one calendar day, or move to the next business day?
5. **Choose the boundaries:** does expiration include the exact end instant? Range queries should use an inclusive start and an exclusive end where appropriate.
6. **Standardize communication:** ISO strings with offset, epoch with documented unit, or pure calendar date?
7. **Test the edges:** end of month, Feb 29, time zone differences, DST, time-zone-transition dates, and expiration boundaries.

### Self-Check Questions

- Should the birthday `24/10/2000` be stored as a `LocalDate` or an `Instant`, and why?
- Two servers log the same event using their local clock time. Is `LocalDateTime` alone enough to compare them?
- How does a daily meeting at 09:00 New York time differ from a task that runs every 24 hours?
- Does an order occurring at exactly 00:00 on the next day fall within "yesterday" when the end boundary is exclusive?
- An API sends the number `1792848000`: what else do you need to know before converting it to a time?

**Remember:** date and time are data with **business semantics**. Choosing the right model from the start ensures consistent storage, accurate regional display, correct expiration checks, and safe scheduling across multiple systems.