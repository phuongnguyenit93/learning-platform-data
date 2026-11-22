# Comparing Adding One Calendar Day vs. Adding 24 Hours Across a DST Boundary in Java

With `ZonedDateTime`, the following two seemingly equivalent expressions **can produce two different end instants**:

```java
ZonedDateTime tomorrowSameLocalTime = start.plusDays(1);
ZonedDateTime exactly24HoursLater  = start.plusHours(24);
```

The reason is that **"one calendar day"** and **"24 hours of duration"** are not the same concept. `plusDays(1)` preserves the intent of moving to **the next calendar day in local time**, whereas `plusHours(24)` moves to the point **24 hours later on the instant time-line**. When a time zone enters or leaves daylight saving time (DST), the two operations can differ by one hour — or by a different amount if the zone rule changes the offset by something other than one hour.

This lesson focuses on the mechanism in `java.time.ZonedDateTime`, experiments across spring/fall DST boundaries, how to distinguish `Period` from `Duration`, checking for nonexistent or repeated hours, and choosing the right operation based on business requirements.

## 1. The Two Time-Lines of `ZonedDateTime`

`ZonedDateTime` combines a **local date-time** (`LocalDateTime`), a **zone ID** (`ZoneId`), and a **resolved UTC offset** (`ZoneOffset`). It lets you view an event from two perspectives:

1. **Local time-line:** `2024-03-10 12:00` in New York is interpreted according to the calendar and wall-clock time in New York, which does not mean an exact 24 hours from `2024-03-09 12:00`.
2. **Instant time-line:** an `Instant` describes a unique point on the Java time-line; when adding `Duration.ofHours(24)`, the new instant is exactly 24 hours after the old instant according to `java.time` arithmetic, and is then displayed using the offset rules at the target.

Java specifies:

| Operation on `ZonedDateTime` | Time-line used | Meaning |
| --- | --- | --- |
| `plusDays(1)` | Local date-time | Moves to the next calendar day, trying to keep the local time if valid |
| `plusWeeks(1)`, `plusMonths(1)`, `plusYears(1)` | Local date-time | Advances by calendar component, resolving DST on the new date |
| `plusHours(24)` | Instant | Adds 24 × 3,600 seconds on the instant time-line |
| `plusMinutes(1)`, `plusSeconds(1)`, `plusNanos(1)` | Instant | Advances by elapsed duration rather than wall-clock time |
| `plus(Period.ofDays(1))` | Local date-time | Corresponds to the meaning of adding one calendar day |
| `plus(Duration.ofDays(1))` | Instant | A `Duration` "day" is always 86,400 seconds in the API |

`ZonedDateTime` is **immutable**: both operations return a new object without modifying `start`. Do not confuse the `ofDays(1)` method name on `Period` and `Duration`: one is an amount of time **based on calendar days**, while the other is a fixed **number of seconds**.

### DST Makes a Calendar Day Not Always 24 Hours

When a zone **springs forward**, the span between two points at the same wall-clock time on two consecutive days may be only **23 hours** on the instant time-line. When a zone **falls back**, a similar span may be **25 hours** long. That is the common example for a 1-hour offset transition. Not all countries observe DST, and not all historical offset changes are 1 hour long.

Use a real `ZoneId` such as `America/New_York`, rather than hardcoding a fixed `-05:00` offset for the entire year. `ZoneId` applies date-specific rules from the JDK's time-zone data.

## 2. Spring: Losing One Wall-Clock Hour

In `America/New_York`, on **2024-03-10**, clocks jump forward from **01:59:59 EST (UTC−05:00)** to **03:00:00 EDT (UTC−04:00)**. On this transition day, the local time range from **02:00 to 02:59:59…** does not exist.

Suppose we start at noon the day before:

```text
Start:
2024-03-09T12:00-05:00[America/New_York]
= 2024-03-09T17:00:00Z

+ 1 calendar day:
2024-03-10T12:00-04:00[America/New_York]
= 2024-03-10T16:00:00Z
=> actual elapsed time: 23 hours

+ 24 hours:
2024-03-10T13:00-04:00[America/New_York]
= 2024-03-10T17:00:00Z
=> actual elapsed time: 24 hours
```

With `plusDays(1)`, the goal is "noon the next day" on New York wall-clock time: still **12:00**. However, between the two noons the clock skipped one hour, so the instant difference is only **23 hours**.

With `plusHours(24)`, the goal is "a full 24 hours from the start", so the wall-clock time at the target becomes **13:00**. The two results differ by **1 hour**.

```java
ZoneId newYork = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0, newYork);

ZonedDateTime calendarDay = start.plusDays(1);
ZonedDateTime elapsed24h = start.plusHours(24);

System.out.println(calendarDay);
// 2024-03-10T12:00-04:00[America/New_York]
System.out.println(elapsed24h);
// 2024-03-10T13:00-04:00[America/New_York]

System.out.println(Duration.between(start, calendarDay).toHours());
// 23
System.out.println(Duration.between(start, elapsed24h).toHours());
// 24
```

The snippet above is an **in-method illustration** and requires importing `java.time.ZoneId`, `ZonedDateTime`, and `Duration`.

## 3. Fall: Repeating One Wall-Clock Hour

In New York on **2024-11-03**, clocks turn back from **01:59:59 EDT (UTC−04:00)** to **01:00:00 EST (UTC−05:00)**. The range **01:00–01:59:59…** occurs **twice**, corresponding to two different offsets.

Suppose we start at noon the day before:

```text
Start:
2024-11-02T12:00-04:00[America/New_York]
= 2024-11-02T16:00:00Z

+ 1 calendar day:
2024-11-03T12:00-05:00[America/New_York]
= 2024-11-03T17:00:00Z
=> actual elapsed time: 25 hours

+ 24 hours:
2024-11-03T11:00-05:00[America/New_York]
= 2024-11-03T16:00:00Z
=> actual elapsed time: 24 hours
```

`plusDays(1)` keeps **12:00** of the next calendar day; because the 01:00 hour is experienced twice, the span between the two noons is **25 hours**. `plusHours(24)` still adds a fixed duration and arrives at **11:00** local time.

```java
ZoneId newYork = ZoneId.of("America/New_York");

ZonedDateTime start = ZonedDateTime.of(
        2024, 11, 2, 12, 0, 0, 0, newYork);

System.out.println(start.plusDays(1));
// 2024-11-03T12:00-05:00[America/New_York]
System.out.println(start.plusHours(24));
// 2024-11-03T11:00-05:00[America/New_York]

System.out.println(Duration.between(
        start, start.plusDays(1)).toHours()); // 25
```

### Comparison Table for New York in 2024

| Case | Start | `plusDays(1)` | Duration to calendar-day target | `plusHours(24)` |
| --- | --- | --- | --- | --- |
| No DST transition | 02/03 12:00 −05 | 02/04 12:00 −05 | 24 hours | 02/04 12:00 −05 |
| Spring DST transition | 03/09 12:00 −05 | 03/10 12:00 −04 | **23 hours** | 03/10 13:00 −04 |
| Fall DST transition | 11/02 12:00 −04 | 11/03 12:00 −05 | **25 hours** | 11/03 11:00 −05 |

**Key takeaway:** `plusDays(1)` **does not mean** "always add 23 or 25 hours when crossing DST". The result depends on **the start time, the target time, and the transition rules**. When the span from the initial local time to the target local time does not straddle an offset change, the two approaches can still be equal; see the special case below.

## 4. `Period.ofDays(1)` and `Duration.ofDays(1)`

Both types represent an amount of time, but with different semantics:

- **`Period`:** years, months, and days in the ISO calendar, not directly representing a fixed number of seconds. Use when the requirement speaks of **days on the calendar**.
- **`Duration`:** seconds and nanoseconds of an interval on the instant time-line. `Duration.ofDays(1)` is defined as **86,400 seconds**, even when a calendar day in a zone has 23 or 25 hours due to DST.

```java
ZonedDateTime start = ZonedDateTime.of(
        2024, 3, 9, 12, 0, 0, 0,
        ZoneId.of("America/New_York"));

ZonedDateTime byCalendar = start.plus(Period.ofDays(1));
ZonedDateTime byElapsed = start.plus(Duration.ofDays(1));

System.out.println(byCalendar.equals(start.plusDays(1))); // true
System.out.println(byElapsed.equals(start.plusHours(24))); // true
System.out.println(byCalendar.equals(byElapsed));          // false
```

`Duration.between(start.toInstant(), byCalendar.toInstant())` gives the actual difference on the instant time-line: 23 hours in the spring example. If you need to measure elapsed time, compute it from `Instant` values or use `Duration.between` on objects that carry full zone/offset information — do not take two `LocalDateTime` values and infer real elapsed seconds.

### `ChronoUnit.DAYS` Differs from `ChronoUnit.HOURS`

You can equivalently write:

```java
ZonedDateTime nextCalendarDay = start.plus(1, ChronoUnit.DAYS);
ZonedDateTime after24Hours = start.plus(24, ChronoUnit.HOURS);
```

(Requires importing `java.time.temporal.ChronoUnit`.) Under `ZonedDateTime` rules, `DAYS` is a calendar-day unit; `HOURS` is an instant-based unit. Do not mechanically swap the two expressions to "optimize" when using a time zone with DST.

## 5. Special Case: Crossing DST Yet Both Results Still Match

Saying "crossing DST means `plusDays(1)` **always** differs from `plusHours(24)`" is also wrong.

For example, suppose you start at **02:30 AM on 2024-03-09** in New York. The next day, `02:30` is a **nonexistent** time because clocks jump from 02:00 to 03:00. The `ZonedDateTime.plusDays(1)` rule attempts to place `02:30` on 03/10, then **pushes the local time forward across the gap** to `03:30-04:00`.

```java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime beforeGap = ZonedDateTime.of(
        2024, 3, 9, 2, 30, 0, 0, newYork);

System.out.println(beforeGap.plusDays(1));
// 2024-03-10T03:30-04:00[America/New_York]
System.out.println(beforeGap.plusHours(24));
// 2024-03-10T03:30-04:00[America/New_York]
```

Both calculations in this case land on the **same instant**, even though the calculation **rules differ**. The reason is not that every day is always 24 hours, but that Java's handling of an invalid date-time at the target happens to make the two results coincide.

Similarly, during a fall DST overlap, a local time has **two valid offsets**. When adding by calendar days, `ZonedDateTime` tries to retain the previous offset if it is still valid; otherwise, it typically picks the earlier (pre-transition) offset. When adding by hours, Java advances on the instant time-line and then derives the local time. Therefore, you must test with **specific times of day**, not just the DST transition date.

## 6. Gap and Overlap: Resolution Mechanism in `ZonedDateTime`

A `ZoneId` has a set of rules (`ZoneRules`). For a given `LocalDateTime`, the number of valid offsets can be:

| Number of valid offsets | Type | Meaning |
| ---: | --- | --- |
| 1 | Normal | The local time matches only one instant |
| 0 | Gap | The local time does not exist because clocks jumped forward |
| 2 | Overlap | The local time occurs twice when clocks fall back |

With `plusDays(1)`, Java adds days on the local time-line and then resolves according to the zone rules:

- **Normal:** uses the valid offset of the new date-time.
- **Gap:** pushes the local date-time forward by the length of the gap; for example, `02:30` becomes `03:30`.
- **Overlap:** retains the old offset if applicable; otherwise, chooses the earlier offset according to the API's default rule.

`plusHours(24)`, by contrast, adds duration on the instant time-line, where each instant determines a single offset in the zone, so there is no need to "choose one of two instants" at the target from an ambiguous local time.

### Detecting Whether a Target Time Is Valid

If business logic needs to reject an appointment scheduled during a nonexistent hour or require the user to choose the first/second 01:30 during an overlap:

```java
ZoneId zone = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

System.out.println(zone.getRules().getValidOffsets(gap).size()); // 0
System.out.println(zone.getRules().getValidOffsets(overlap).size()); // 2
```

This is an **in-method illustration** and requires importing `java.time.ZoneId` and `LocalDateTime`. The list of offsets from `getValidOffsets` helps determine the state before saving a schedule. For an overlap, you can use `withEarlierOffsetAtOverlap()` / `withLaterOffsetAtOverlap()`. For logic that must validate a specified offset, use `ZonedDateTime.ofStrict(localDateTime, offset, zone)` and handle `DateTimeException` if it is invalid.

Note that DST does not necessarily shift by exactly one hour, not every region observes DST, and historical data or future regulations may differ. Do not compute the "lost/gained" hours using a hardcoded constant of 1 for all zones.

## 7. Complete Java 17+ Example with Deterministic Output

Create the file **`CalendarDayVs24HoursDemo.java`**:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class CalendarDayVs24HoursDemo {
    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    private static void compare(
            String label, int year, int month, int day) {
        ZonedDateTime start = ZonedDateTime.of(
                year, month, day, 12, 0, 0, 0, NEW_YORK);
        ZonedDateTime byDay = start.plusDays(1);
        ZonedDateTime byHours = start.plusHours(24);

        System.out.println(label + " start = " + start);
        System.out.println(label + " +1 day = " + byDay);
        System.out.println(label + " +24 hours = " + byHours);
        System.out.println(label + " day elapsed hours = "
                + Duration.between(start, byDay).toHours());
        System.out.println(label + " fixed elapsed hours = "
                + Duration.between(start, byHours).toHours());
    }

    public static void main(String[] args) {
        compare("Spring", 2024, 3, 9);
        compare("Fall", 2024, 11, 2);
        compare("Normal", 2024, 2, 3);

        ZonedDateTime start = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, NEW_YORK);
        System.out.println("Period equals plusDays = "
                + start.plus(Period.ofDays(1))
                        .equals(start.plusDays(1)));
        System.out.println("Duration equals plusHours = "
                + start.plus(Duration.ofDays(1))
                        .equals(start.plusHours(24)));

        ZonedDateTime beforeGap = ZonedDateTime.of(
                2024, 3, 9, 2, 30, 0, 0, NEW_YORK);
        System.out.println("Gap +1 day = " + beforeGap.plusDays(1));
        System.out.println("Gap +24 hours = "
                + beforeGap.plusHours(24));

        LocalDateTime missing = LocalDateTime.of(
                2024, 3, 10, 2, 30);
        LocalDateTime repeated = LocalDateTime.of(
                2024, 11, 3, 1, 30);
        System.out.println("Gap valid offsets = "
                + NEW_YORK.getRules().getValidOffsets(missing).size());
        System.out.println("Overlap valid offsets = "
                + NEW_YORK.getRules().getValidOffsets(repeated).size());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CalendarDayVs24HoursDemo.java
java CalendarDayVs24HoursDemo
```

Output with standard time-zone data for New York in 2024:

```text
Spring start = 2024-03-09T12:00-05:00[America/New_York]
Spring +1 day = 2024-03-10T12:00-04:00[America/New_York]
Spring +24 hours = 2024-03-10T13:00-04:00[America/New_York]
Spring day elapsed hours = 23
Spring fixed elapsed hours = 24
Fall start = 2024-11-02T12:00-04:00[America/New_York]
Fall +1 day = 2024-11-03T12:00-05:00[America/New_York]
Fall +24 hours = 2024-11-03T11:00-05:00[America/New_York]
Fall day elapsed hours = 25
Fall fixed elapsed hours = 24
Normal start = 2024-02-03T12:00-05:00[America/New_York]
Normal +1 day = 2024-02-04T12:00-05:00[America/New_York]
Normal +24 hours = 2024-02-04T12:00-05:00[America/New_York]
Normal day elapsed hours = 24
Normal fixed elapsed hours = 24
Period equals plusDays = true
Duration equals plusHours = true
Gap +1 day = 2024-03-10T03:30-04:00[America/New_York]
Gap +24 hours = 2024-03-10T03:30-04:00[America/New_York]
Gap valid offsets = 0
Overlap valid offsets = 2
```

The printed strings are produced by `ZonedDateTime.toString()`. The code uses **fixed dates and a specific `ZoneId`**, independent of the machine's clock or default time zone. Zone rules are provided by TZDB/JDK; if time-zone data changes historically or comes from a different provider, verify the output against your deployment environment.

## 8. Choosing the Addition Operation Based on Business Requirements

### 8.1. "Every day at 09:00 in a location"

For example, a system sends notifications every day at **09:00 New York time**. The requirement is **wall-clock local time**, not sending once every 86,400 seconds.

```java
ZoneId location = ZoneId.of("America/New_York");

ZonedDateTime scheduled = ZonedDateTime.of(
        2024, 3, 9, 9, 0, 0, 0, location);

ZonedDateTime next = scheduled.plusDays(1);
System.out.println(next);
// 2024-03-10T09:00-04:00[America/New_York]
```

Use `plusDays(1)`, or store `LocalTime` and `ZoneId` separately and resolve each calendar day. You need a dedicated rule when the scheduled time falls directly in a gap/overlap. **Do not** repeatedly use `plusHours(24)` for a recurring wall-clock schedule, because after each DST transition it can drift away from the time the user chose.

### 8.2. "Access session expires after exactly 24 hours"

If a token, session, cache, or service specifies a lifetime of **24 hours of elapsed time from creation**, compute it on the instant time-line:

```java
Instant createdAt = Instant.parse("2024-03-09T17:00:00Z");
Instant expiresAt = createdAt.plus(Duration.ofHours(24));
```

This snippet requires importing `java.time.Instant` and `Duration`. Convert to `ZonedDateTime` when displaying local time, but do not use `plusDays(1)` because it can shorten or extend the actual lifetime around DST. When measuring internal in-process timeouts, consider a monotonic clock; `Instant.now()` relies on the system clock, which can also be adjusted.

### 8.3. "Tomorrow at the same time" vs. "24 hours from now"

These are two different requirements:

| User says | Primary intent | Appropriate API |
| --- | --- | --- |
| "Tomorrow at 12:00, local time" | Next calendar day, 12:00 wall-clock time | `plusDays(1)` or build new date + `LocalTime` + `ZoneId` |
| "In exactly 24 hours" | Fixed elapsed duration | `plusHours(24)`, `plus(Duration.ofHours(24))`, or `Instant.plus` |
| "After one business day" | Work calendar rules, holidays, weekends | Requires a business calendar, not just `plusDays(1)` |
| "End of tomorrow at 23:59 local" | Calendar-based point in the zone | Build target time from date and `ZoneId`; do not infer from 48 hours |
| "After exactly 1 × 86,400 seconds" | Duration in seconds | `Duration.ofDays(1)` / `Duration.ofSeconds(86_400)` |

For financial, SLA, or billing domains, clarify what "one day" means in the contract: **calendar day**, **24 hours**, or **business day**. Do not pick one just because the API call is shorter.

### 8.4. Crossing DST Near Midnight

```text
New York 2024-03-09T23:30-05:00
  + 1 calendar day → 2024-03-10T23:30-04:00
  + 24 hours       → 2024-03-11T00:30-04:00
```

In this example, the results **even differ in calendar date**, not just time of day. If an application computes an "expiration date" by adding a fixed number of seconds and then calling `toLocalDate()`, it may return a different date than intended.

## 9. Things You Should Not Infer from the Results

**A `LocalDate` day does not have a fixed number of hours.** `LocalDate.plusDays(1)` only increments the date in the ISO calendar, without considering DST. Only after combining with `LocalTime` and `ZoneId` and converting both dates to instants does the 23/24/25-hour difference appear. Therefore, computing the number of hours between two `LocalDate` values without knowing the zone and start/end times lacks sufficient information.

**`LocalDateTime.plusDays(1)` does not handle time zones on its own.** It increments calendar fields without a zone/offset; the result may correspond to a nonexistent local time. If you need a valid instant, you still have to attach a `ZoneId` and resolve DST afterwards. `ZonedDateTime.plusDays(1)` already has the zone context to do this.

**UTC or fixed offsets have no zone-rule DST transitions.** For example, `ZoneOffset.UTC` and `ZoneOffset.ofHours(7)` inherently have a constant offset; both additions usually match for normal intervals in those offsets. Use `Asia/Ho_Chi_Minh` for Vietnam schedules rather than assuming everywhere observes DST.

**A `Duration` difference does not equal the number of calendar days.** `Duration.between(start, end).toHours()` returns whole hours on the instant time-line. To determine "which local calendar date", use `toLocalDate()`; to compute business schedules, you need additional business rules.

**Different-looking `ZonedDateTime` values can point to the same instant.** If you need to compare points in time, use `toInstant()` or `isEqual`; comparing only local date-times can ignore the offset.

**Do not predict DST transition times with a fixed formula.** Each `ZoneId` has its own rules, varying across regions and historical periods. Governments can change rules in the future, so test around transition dates for your business zones and keep tzdb data up to date.

## 10. Common Mistakes and Fixes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Assuming `plusDays(1) == plusHours(24)` in all zones | Wrong across offset-change boundaries | Choose local calendar or elapsed time per business intent |
| Replacing `Period.ofDays(1)` with `Duration.ofDays(1)` | Turns a calendar day into 86,400 seconds | Use `Period` when adding calendar days |
| Using `plusHours(24)` for a "daily at 09:00" schedule | Displayed time drifts after DST | Use `plusDays(1)` / build local date + time in the zone |
| Using `plusDays(1)` to create a 24-hour timeout | May time out after 23 or 25 hours | Use `Instant.plus(Duration.ofHours(24))` |
| Applying a fixed `-05:00` offset for New York year-round | Fails to reflect summer `-04:00` DST rule | Use `ZoneId.of("America/New_York")` |
| Claiming crossing DST **always** gives different results | Can match when target is adjusted over a gap or valid offset | Test specific times, do not generalize |
| Thinking `plusDays` always preserves exact wall-clock hour/minute | Target time may fall in a gap and be pushed forward | Check `getValidOffsets` and choose a policy |
| Not handling repeated hours during an overlap | Two instants for one local time | Allow selecting offset or resolve per explicit requirement |
| Computing `Duration` from `LocalDateTime` as real elapsed time | Missing zone to reflect offset changes | Compute from `Instant` or resolved `ZonedDateTime` |
| Testing only normal days | Misses DST transition bugs | Test before/after both transitions, gaps, and overlaps |
| Assuming DST is always ±1 hour worldwide | Wrong for non-standard or historical offset changes | Rely on the specific zone's `ZoneRules` |

## 11. Testing and Operations Checklist

1. **Clarify the intent:** "next calendar day" or "N elapsed hours"? Make it explicit in method names, such as `nextDailyOccurrence` vs. `expiresAfterDuration`.
2. **Use a location-based `ZoneId`:** avoid storing only the current offset for future schedules.
3. **Test three types of days:** normal day, spring-forward DST day, fall-back DST day.
4. **Test sensitive times:** right before/after the boundary, nonexistent hours, repeated hours, and times near midnight.
5. **Verify both perspectives:** the `toLocalDateTime()` result and `Duration.between(start.toInstant(), end.toInstant())`.
6. **Define a gap/overlap policy:** auto-shift or reject; earlier or later offset; whether to prompt the user for repeated hours.
7. **Keep time-zone data synchronized:** use an updated tzdb, and account for legal rule changes after a schedule is created.

### Self-Check Questions

**1.** Noon on 2024-03-09 in New York plus one calendar day lands on what time, and how many hours have elapsed?  
→ `2024-03-10T12:00-04:00`, **23 hours**.

**2.** What about adding 24 hours to the same start time?  
→ `2024-03-10T13:00-04:00`, **24 hours** elapsed.

**3.** Noon on 2024-11-02 plus one calendar day in New York has how many elapsed hours?  
→ **25 hours** because one wall-clock hour is repeated.

**4.** Is `Duration.ofDays(1)` the next calendar day?  
→ No. It is **86,400 seconds**, which can differ from `Period.ofDays(1)` on a `ZonedDateTime`.

**5.** Does `plusDays(1)` necessarily preserve the exact wall-clock time when the target falls in a DST gap?  
→ No. Java may **push the target time forward** across the gap.

**6.** Why do adding one day and adding 24 hours sometimes produce the same result despite a DST boundary?  
→ Gap/overlap resolution rules and the positions of the two points can cause both paths to land on the same instant; you must check the specific time.

### Official API Documentation

- [Oracle Java SE 17 — `ZonedDateTime.plusDays` and `plusHours`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): clearly describes the local time-line and instant time-line, along with gap/overlap handling.
- [Oracle Java SE 17 — `Duration`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): second-based duration where each `Duration` "day" is 86,400 seconds.
- [Oracle Java SE 17 — `Period`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): calendar-based years, months, and days.
- [Oracle Java SE 17 — `ZoneRules`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offset rules, gaps, and overlaps.

**Remember:** `ZonedDateTime.plusDays(1)` adds **one local calendar day**; `plusHours(24)` adds **24 hours of elapsed time**. They only match when the zone rules and the time in question yield the same instant. If the requirement is "tomorrow at the same time", prefer calendar days; if the requirement is "in exactly 24 hours", prefer `Duration`/`Instant`.
