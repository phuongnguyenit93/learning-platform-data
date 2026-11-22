# Combining a Date with a Time Using `LocalDate.atTime()` in Java

Suppose a scheduling system stores an **appointment date** of `2025-03-08` and an **appointment time** of `09:30`. These two pieces of information are independent: `LocalDate` knows the date without a time, while `LocalTime` knows the time of day without knowing which date it belongs to. To represent **09:30 on 08/03/2025**, use `LocalDate.atTime(...)`:

```java
LocalDate date = LocalDate.of(2025, 3, 8);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime appointment = date.atTime(time);
// 2025-03-08T09:30
```

This snippet requires `import java.time.*;` inside a Java method. The result type is **`LocalDateTime`**: a date + wall-clock time, **without a time zone, offset, or UTC instant**. This is an important distinction when designing appointments, job schedules, deadlines, and UI data.

## 1. What Does `atTime()` Do Exactly?

`LocalDate.atTime(...)` combines **the date of the calling `LocalDate` object** with **the time passed in** to create a new date-time value. There is no calculation of elapsed real time, no reading of the system clock, and no automatic time-zone conversion.

For example:

| Component | Type | Value |
| --- | --- | --- |
| Calendar date | `LocalDate` | `2025-03-08` |
| Time of day | `LocalTime` | `09:30` |
| Result of `date.atTime(time)` | `LocalDateTime` | `2025-03-08T09:30` |

**Key characteristics:**

- The method belongs to `LocalDate` and is called as `date.atTime(...)`; it is **not** a method on `Instant` or a duration type.
- Java uses the ISO-8601 calendar system for `LocalDate` and `LocalDateTime`. The result contains the exact date, hour, minute, and selected second/nanosecond components.
- The combination does not depend on `ZoneId.systemDefault()`, does not read the current time, and does not automatically detect DST.
- Classes in `java.time` are **immutable**. `atTime()` returns a new object; it does not mutate `date` or `time`.
- The result itself **does not identify a unique `Instant`**. You must attach an appropriate zone/offset before converting it to a global timestamp.

Note the distinction between `LocalDate.atTime(...)` and `LocalDateTime.of(date, time)`: both can create the same `LocalDateTime` from a given date and time. `date.atTime(time)` is often more readable when you **already have a `LocalDate`** and want to add a time component.

## 2. Commonly Used Overloads

`LocalDate` provides several overloads to create a date-time. Choose one based on how the time information is represented.

| Call | Return Type | When Appropriate |
| --- | --- | --- |
| `date.atTime(LocalTime.of(9, 30))` | `LocalDateTime` | You already have a `LocalTime` object from a form, configuration, or business logic. |
| `date.atTime(9, 30)` | `LocalDateTime` | You only need hours and minutes. Seconds/nanoseconds default to 0. |
| `date.atTime(9, 30, 45)` | `LocalDateTime` | You need hours, minutes, and seconds. Nanoseconds default to 0. |
| `date.atTime(9, 30, 45, 123_000_000)` | `LocalDateTime` | You also need nanoseconds; `123_000_000` ns is 123 ms. |
| `date.atTime(OffsetTime.of(9, 30, 0, 0, ZoneOffset.ofHours(7)))` | **`OffsetDateTime`** | The provided time already carries a UTC offset. |

**Note on return type:** the overload taking `OffsetTime` produces **`OffsetDateTime`**, not `LocalDateTime`. The result has an offset and can resolve an `Instant` via `toInstant()`. An offset like `+07:00` still **does not fully replace a region time zone** such as `Asia/Ho_Chi_Minh`, because a region has historical rules and can change over time.

Integer parameters must be within valid ranges:

- `hour`: **0–23**;
- `minute`: **0–59**;
- `second`: **0–59**;
- `nanoOfSecond`: **0–999,999,999**.

Values such as hour 24, minute 60, second 60, or nanosecond 1,000,000,000 are invalid and will throw `DateTimeException`. `atTime(24, 0)` **is not automatically interpreted as 00:00 of the next day**. If you want midnight of the next day, write `date.plusDays(1).atTime(LocalTime.MIDNIGHT)` so the date change is explicit.

Passing `null` to an overload expecting `LocalTime` or `OffsetTime` does not produce a default time; you must validate input data. Furthermore, calling `date.atTime(null)` directly causes an overload resolution ambiguity in Java because there are two reference parameter types (`LocalTime` and `OffsetTime`); it is best **never to use `null` as a time value**.

## 3. Complete Java 17+ Example: Combining, Overloads, Immutability, and Input Validation

Create the file `AtTimeBasicsDemo.java` with the **exact** public class name below:

```java
import java.time.*;

public class AtTimeBasicsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 3, 8);
        LocalTime time = LocalTime.of(9, 30);

        LocalDateTime scheduled = date.atTime(time);

        System.out.println("Date                : " + date);
        System.out.println("Time                : " + time);
        System.out.println("atTime(LocalTime)   : " + scheduled);
        System.out.println("atTime(9, 30)       : " + date.atTime(9, 30));
        System.out.println("With seconds+nanos  : "
                + date.atTime(9, 30, 45, 123_000_000));
        System.out.println("At midnight         : "
                + date.atTime(LocalTime.MIDNIGHT));
        System.out.println("At max time         : "
                + date.atTime(LocalTime.MAX));

        OffsetTime fixedOffset = OffsetTime.of(
                9, 30, 0, 0, ZoneOffset.ofHours(7)
        );
        OffsetDateTime offsetDateTime = date.atTime(fixedOffset);

        System.out.println("At offset time      : " + offsetDateTime);
        System.out.println("As instant          : " + offsetDateTime.toInstant());
        System.out.println("Date unchanged      : " + date);

        try {
            date.atTime(24, 0);
        } catch (DateTimeException ex) {
            System.out.println("Invalid hour        : DateTimeException");
        }
    }
}
```

Compile and run on **JDK 17 or later**:

```bash
javac AtTimeBasicsDemo.java
java AtTimeBasicsDemo
```

Verified output from running the program:

```text
Date                : 2025-03-08
Time                : 09:30
atTime(LocalTime)   : 2025-03-08T09:30
atTime(9, 30)       : 2025-03-08T09:30
With seconds+nanos  : 2025-03-08T09:30:45.123
At midnight         : 2025-03-08T00:00
At max time         : 2025-03-08T23:59:59.999999999
At offset time      : 2025-03-08T09:30+07:00
As instant          : 2025-03-08T02:30:00Z
Date unchanged      : 2025-03-08
Invalid hour        : DateTimeException
```

Output analysis:

1. `date.atTime(time)` and `date.atTime(9, 30)` produce the same `LocalDateTime` value. One takes a `LocalTime` object, while the other passes numeric values directly.
2. `date.atTime(9, 30, 45, 123_000_000)` preserves seconds and nanoseconds, displaying `.123` in ISO format since only three fractional digits are needed.
3. `LocalTime.MIDNIGHT` is `00:00`. `LocalTime.MAX` is the last time of the day represented at nanosecond precision, which is `23:59:59.999999999`.
4. `OffsetTime` with `+07:00` produces `OffsetDateTime` `2025-03-08T09:30+07:00`. When converted to UTC, the instant is `2025-03-08T02:30:00Z` because 09:30 minus seven hours is 02:30.
5. `date` at the end is still `2025-03-08`, confirming that the source object **is not modified**.
6. `atTime(24, 0)` is rejected. Java does not automatically adjust out-of-range input values; the application must validate user input.

## 4. Using `atTime()` in Business Operations

### A. Combining Data from Date and Time Form Fields

A scheduling form has two separate fields: “Date” and “Time”. When the user submits:

```text
Date : 2025-03-08
Time : 09:30
```

You can parse the ISO strings:

```java
LocalDate appointmentDate = LocalDate.parse("2025-03-08");
LocalTime appointmentTime = LocalTime.parse("09:30");
LocalDateTime localAppointment = appointmentDate.atTime(appointmentTime);
```

This is a **code snippet inside a method** and requires `import java.time.*;`. If the source is a Vietnamese-formatted date/time, such as `08/03/2025` and `09:30`, you need a `DateTimeFormatter` with an appropriate pattern to parse the date. Do not alter the date information by manually concatenating strings and inferring a zone. For example:

```java
DateTimeFormatter dateFormatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
LocalDate parsedDate = LocalDate.parse("08/03/2025", dateFormatter);
LocalTime parsedTime = LocalTime.parse("09:30");
LocalDateTime parsedAppointment = parsedDate.atTime(parsedTime);
```

The snippet above additionally requires `import java.time.format.DateTimeFormatter;`. After parsing, you must clearly determine **which time zone this schedule belongs to** if the task is to execute at a specific instant.

### B. Choosing a Time to Run a Task on a Given Day

Suppose you need to send a reminder at 18:00 **tomorrow in the business time zone**. You should determine the current date in the chosen zone, then add the time:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate tomorrow = LocalDate.now(businessZone).plusDays(1);
LocalDateTime nextReminderLocal = tomorrow.atTime(18, 0);
ZonedDateTime reminder = nextReminderLocal.atZone(businessZone);
Instant reminderInstant = reminder.toInstant();
```

This is an **illustrative snippet inside a method** requiring `import java.time.*;`, without a standalone `main`. `LocalDate.now(businessZone)` avoids accidentally using “today” in the server's time zone. `atTime(18, 0)` creates **18:00 on the local clock of the chosen date**; `atZone(businessZone)` then applies time-zone rules to convert it to an `Instant`.

If the requirement is “exactly 24 hours from now”, working directly with an `Instant` plus `Duration.ofHours(24)` expresses the requirement more clearly. `atTime()` is meant for the **calendar date plus local wall-clock time** model.

### C. Start/End of a Day for a Filter Range

When a user selects an entire day on a calendar, a timestamp range is typically expressed from the start of the selected day **up to (but excluding) the start of the next day** in a specific zone:

```java
LocalDate selected = LocalDate.of(2025, 3, 8);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant inclusiveStart = selected.atStartOfDay(zone).toInstant();
Instant exclusiveEnd = selected.plusDays(1).atStartOfDay(zone).toInstant();
```

This is an **illustrative snippet**, not a standalone `main` class. Using a half-open interval `[inclusiveStart, exclusiveEnd)` avoids guessing the “end of day” in milliseconds or nanoseconds. `date.atTime(LocalTime.MIDNIGHT)` creates a `LocalDateTime` at 00:00; `date.atStartOfDay(zone)` finds **the earliest valid start of day in the zone**. These two approaches are related, but they should not be treated as completely identical on every date and in every time zone; some zones have offset transitions right around midnight.

## 5. Crucial Boundary: `atTime()` Does Not Attach a Time Zone

`LocalDate.atTime(9, 30)` produces `2025-03-08T09:30`, **not** “09:30 UTC”, “09:30 Vietnam time”, or a “Unix timestamp”. `LocalDateTime` only represents the digits of a calendar date and wall-clock time.

To anchor this local time to a specific place:

```java
LocalDateTime local = LocalDate.of(2025, 3, 8).atTime(9, 30);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = local.atZone(vietnam);
Instant moment = zoned.toInstant();
```

This is an **illustrative snippet requiring `import java.time.*;`**. `zoned` will be `2025-03-08T09:30+07:00[Asia/Ho_Chi_Minh]`, and `moment` will be `2025-03-08T02:30:00Z`.

A local date-time value can fall into a **missing hour (gap)** or a **repeated hour (overlap)** due to DST in time zones that observe daylight saving transitions. `atTime()` itself does not check DST rules because it has not received a `ZoneId`.

| Situation | `LocalDateTime` from `atTime()` | When Interpreted with `ZoneId` |
| --- | --- | --- |
| Normal local time | Valid | Usually has exactly one valid offset. |
| Missing hour (*gap*) | Still creates the requested value | No corresponding instant exists; a handling policy is needed. |
| Repeated hour (*overlap*) | Still creates the requested value | Can correspond to two different instants. |

### Java 17+ Example: `atTime()` and DST Gaps/Overlaps

Create the file `AtTimeDstDemo.java`:

```java
import java.time.*;

public class AtTimeDstDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDateTime missing =
                LocalDate.of(2024, 3, 10).atTime(2, 30);
        LocalDateTime repeated =
                LocalDate.of(2024, 11, 3).atTime(1, 30);

        System.out.println("Missing local       : " + missing);
        System.out.println("Valid offsets       : "
                + newYork.getRules().getValidOffsets(missing));
        System.out.println("Resolved gap        : " + missing.atZone(newYork));

        System.out.println("Repeated local      : " + repeated);
        System.out.println("Repeated offsets    : "
                + newYork.getRules().getValidOffsets(repeated));
        System.out.println("Default overlap     : " + repeated.atZone(newYork));
        System.out.println("Later overlap       : "
                + repeated.atZone(newYork).withLaterOffsetAtOverlap());
    }
}
```

```bash
javac AtTimeDstDemo.java
java AtTimeDstDemo
```

Verified output:

```text
Missing local       : 2024-03-10T02:30
Valid offsets       : []
Resolved gap        : 2024-03-10T03:30-04:00[America/New_York]
Repeated local      : 2024-11-03T01:30
Repeated offsets    : [-04:00, -05:00]
Default overlap     : 2024-11-03T01:30-04:00[America/New_York]
Later overlap       : 2024-11-03T01:30-05:00[America/New_York]
```

Explanation:

- `LocalDate.of(2024, 3, 10).atTime(2, 30)` **does not throw an exception**. It simply creates the `LocalDateTime` 02:30 on 2024-03-10.
- In `America/New_York`, 02:30 on this date does not exist because clocks spring forward to daylight saving time. `getValidOffsets` returns an empty list; the default behavior of `atZone` shifts it forward to 03:30 with offset `-04:00`.
- `LocalDate.of(2024, 11, 3).atTime(1, 30)` also creates a `LocalDateTime` normally. However, when the zone transitions from daylight saving time back to standard time, 01:30 occurs **twice**, with offsets `-04:00` and `-05:00`.
- `atZone` selects the earlier offset by default during an overlap; `withLaterOffsetAtOverlap()` selects the other offset. Both `ZonedDateTime` values have the same date and clock digits, but point to **two different `Instant`s**.

If an application has strict rules (flight tickets, payroll, jobs scheduled at a specific time), check `zone.getRules().getValidOffsets(local)` and define how gaps and overlaps should be handled. Do not assume the result of `atTime()` has already been verified for existence in a time zone.

## 6. `atTime()` vs. Similar-Looking Methods

| Expression | Returns | Difference |
| --- | --- | --- |
| `date.atTime(time)` | `LocalDateTime` | Combines a specific date with an existing time. |
| `LocalDateTime.of(date, time)` | `LocalDateTime` | Equivalent way to construct the object from two components. |
| `date.atTime(0, 0)` | `LocalDateTime` | Local midnight, without a time zone. |
| `date.atStartOfDay()` | `LocalDateTime` | Start of day without a time zone; typically 00:00. |
| `date.atStartOfDay(zone)` | `ZonedDateTime` | **Earliest valid** start of day according to zone rules. |
| `date.atTime(offsetTime)` | `OffsetDateTime` | Combines a date with a time that already holds a fixed offset. |
| `date.atTime(time).atZone(zone)` | `ZonedDateTime` | Interprets the local time according to a zone's rules. |
| `date.plusDays(1).atTime(time)` | `LocalDateTime` | Selects the next day, then attaches the desired time. |

Java does not implicitly treat every `LocalDateTime` as UTC. If you only use `date.atTime(...)` and store it in a distributed system, there must be a data contract specifying the zone or offset at an appropriate place; otherwise, two machines may interpret the scheduled instant differently.

## 7. Common Pitfalls and How to Avoid Them

1. **Calling `atTime()` to get the “current time”:** the method does not read the clock. If you want the current instant, use `Instant.now()`; if you want the current date-time in a zone, use `LocalDateTime.now(zone)`, keeping in mind that it is still not a zoned type.
2. **Assuming the result is UTC:** `2025-03-08T09:30` cannot be converted directly to a UTC instant without knowing the required zone or offset.
3. **Assuming the method rolls over to the next day when hour ≥ 24:** `atTime(24, 0)` is invalid. Use `plusDays(1).atTime(0, 0)` if you want midnight of the next day.
4. **Ignoring numeric bounds:** minutes/seconds are 0 to 59, nanoseconds are 0 to 999,999,999; parse and validate user input.
5. **Confusing milliseconds and nanoseconds:** `atTime(9, 30, 45, 123)` means 123 **nanoseconds**, not 123 ms; for 123 ms, use `123_000_000`.
6. **Assuming the operation mutates the original date:** `LocalDate` is immutable. To change the date, reassign `date = date.plusDays(1)` or create a new variable.
7. **Ignoring DST when attaching a `ZoneId`:** “02:30” may be missing; “01:30” may occur twice. The issue lies in interpreting it as a real instant, not in `atTime()` itself.
8. **Using a fixed offset for recurring schedules at a location:** an offset describes a UTC difference, not the full region time-zone rules for future dates.
9. **Creating a full-day range using “23:59:59.999”:** this can easily miss data with nanosecond precision. Prefer a half-open interval from the start of the selected day to the start of the next day.
10. **Confusing a calendar day with a 24-hour duration:** adding calendar days and calling `atTime(time)` preserves the target calendar date and wall-clock time; adding `Duration.ofHours(24)` to an `Instant` preserves elapsed duration. Across a DST transition, these two goals can yield different results.

## 8. Practice Exercises and Answers

**Exercise 1.** The exam date is `2025-06-15` and the start time is `08:45`. Create the date-time in two ways.

```java
LocalDate examDate = LocalDate.of(2025, 6, 15);
LocalDateTime a = examDate.atTime(8, 45);
LocalDateTime b = examDate.atTime(LocalTime.of(8, 45));
// a.equals(b) == true; both are 2025-06-15T08:45
```

**Exercise 2.** An appointment runs from `23:30` today to `00:30` tomorrow. Is calling `atTime(0, 30)` on the same `LocalDate` sufficient?

**Answer:** No, because it creates 00:30 on **the same date**. You must use `LocalDateTime end = date.plusDays(1).atTime(0, 30);`. If you need the actual elapsed duration between the two points, attach the business zone/offset and compute it from the two `Instant`s.

**Exercise 3.** You want to combine `2025-06-15` with `09:00+07:00` and output an `Instant`. Which overload is appropriate?

**Answer:** Use `OffsetTime` and call `date.atTime(offsetTime)` to get an `OffsetDateTime`, then call `toInstant()`. If the schedule recurs in a city rather than at a fixed offset, prefer keeping a `ZoneId` so region rules are applied.

**Exercise 4.** Does every result of `date.atTime(2, 30)` exist in `America/New_York`?

**Answer:** No. The method creates a valid `LocalDateTime` in terms of calendar/clock fields, but on certain DST transition dates, 02:30 does not exist in that zone. You must check zone rules before locking in a real instant.

**Exercise 5.** In the call `date.atTime(9, 30, 0, 1_000_000)`, how many milliseconds does the nanosecond argument represent?

**Answer:** 1 ms, because 1,000,000 ns = 1 ms. This is a valid value.

### Key Takeaway

**`LocalDate.atTime(...)` = known calendar date + wall-clock time → local date-time.** For a `LocalTime` input or numeric arguments, the result is `LocalDateTime`; for an `OffsetTime` input, the result is `OffsetDateTime`. Only when the application provides an appropriate offset or time zone can the value identify a point on the timeline. Use `atTime()` when your problem genuinely starts from **a date** and needs **the time of day** added to it.
