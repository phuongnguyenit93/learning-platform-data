# Modeling Opening Hours and Midnight-Crossing Time Windows with LocalTime in Java

## 1. Problem and Objectives

A store open **09:00–17:00** and a diner open **22:00–02:00 the next morning** are both described using two clock times, yet the way we check them differs. In the 22:00–02:00 window, both **23:00 today** and **01:00 tomorrow** can be times when the store is open.

**LocalTime** in **java.time** represents the hour, minute, second, and nanosecond on a clock within a day, but **contains no date, time zone, or UTC offset**. Therefore, to model an opening schedule, you need rules that define the start time, end time, midnight crossing, and shift start date. If you are querying an actual instant in time, you must also combine it with a date and a ZoneId.

After this lesson, you will be able to:

- Choose a clear opening/closing boundary rule.
- Check regular time windows and midnight-crossing windows using LocalTime.
- Handle **00:00**, equal opening and closing time pairs, 24-hour schedules, and closed schedules.
- Associate post-midnight hours with the correct **shift start date** when the schedule operates by day of the week.
- Calculate the closing date-time and the nominal shift duration.
- Recognize when LocalTime is not enough, especially with Daylight Saving Time (DST), holidays, and calculating actual worked hours.

## 2. LocalTime Describes a Clock Time, Not an Instant

Creating and comparing times:

~~~java
LocalTime opening = LocalTime.of(22, 0);
LocalTime closing = LocalTime.of(2, 0);
LocalTime check = LocalTime.parse("23:15");

System.out.println(opening); // 22:00
System.out.println(closing); // 02:00
System.out.println(check);   // 23:15
~~~

This is an **illustrative snippet**: you need to import **java.time.LocalTime** and place it inside a method. **LocalTime** is immutable. Operations such as **plusHours** and **minusMinutes** return a new object and can wrap around 00:00, but they do not record how many days were crossed.

For example, **LocalTime.of(23, 0).plusHours(3)** returns **02:00**, without saying which day that 02:00 belongs to. If you need to preserve the date, use **LocalDateTime**.

| Type | What does it store? | Meaning in the opening hours problem |
| --- | --- | --- |
| **LocalTime** | Hour, minute, second, nanosecond | 22:00 or 02:00 in a recurring schedule |
| **LocalDate** | Date according to the ISO calendar | Start date of a specific shift |
| **DayOfWeek** | Day of the week | Which days of the week a shift is allowed to start |
| **LocalDateTime** | Local date and time | Monday 22:00 or Tuesday 02:00 |
| **ZoneId** | Region and offset rules over time | Time zone of the location |
| **ZonedDateTime** | Date and time in a specific region | Interpreting a shift in a time zone with DST |
| **Instant** | Absolute point on the timeline | Check-in, check-out, event timestamp |
| **Duration** | Interval based on seconds/nanoseconds | Actual duration between two Instants |

**LocalTime.MIDNIGHT** is **00:00**; **LocalTime.NOON** is **12:00**. LocalTime accepts hours from 0 to 23: you cannot directly create **24:00** with `LocalTime.of(24, 0)`. If a window closes right at midnight, represent it as **00:00 of the next day** when constructing a LocalDateTime.

## 3. Choosing the Half-Open Rule [opening time, closing time)

Typically, you should use a **half-open interval**: a store is considered open at the start time and closed right at the end time.

- For **09:00–17:00**, **09:00** is open.
- **16:59:59.999999999** is still open.
- **17:00** is closed.

The **[start, end)** rule is advantageous when two shifts are back-to-back, such as 09:00–12:00 and 12:00–17:00: the 12:00 mark belongs to the second shift and is not counted twice. If the business requires serving right at the closing time, you must redefine the boundary condition; do not let each module choose on its own.

### Three Cases That Must Be Separated

| Relationship between the two marks | Example | Interpretation | Checking time t |
| --- | --- | --- | --- |
| **start < end** | 09:00–17:00 | Same-day window | t >= start **and** t < end |
| **start > end** | 22:00–02:00 | Crosses midnight | t >= start **or** t < end |
| **start = end** | 00:00–00:00 | Ambiguous data | Must have a dedicated policy |

With **start < end**, use **AND**. With **start > end**, **OR** is required because the operating window consists of the end of the current day and the beginning of the next day. With **start = end**, both interpretations—“closed all day” and “open a full 24 hours”—can appear in real-world systems, so you must not infer either from two equal times.

A transparent model:

- **CLOSED**: no operating window, or has an explicit closed status.
- **ALL_DAY**: open a full 24 hours, has an explicit status.
- **NORMAL_WINDOW**: two distinct opening/closing times, with a nominal duration greater than 0 and less than 24 hours.

In the Java example below, the constructor **rejects two equal times**. This forces the caller to explicitly choose between 24-hour open or closed all day. For stores operating continuously across multiple days, you should have an `ALL_DAY` status type or model specific date-time intervals.

## 4. The Contains Function: Two Simple Branches

~~~java
static boolean contains(
        LocalTime opens, LocalTime closes, LocalTime t) {
    if (opens.equals(closes)) {
        throw new IllegalArgumentException(
                "Use explicit CLOSED or ALL_DAY status");
    }
    if (opens.isBefore(closes)) {
        return !t.isBefore(opens) && t.isBefore(closes);
    }
    return !t.isBefore(opens) || t.isBefore(closes);
}
~~~

The snippet above is an **illustrative method**: it needs to be placed inside a class and import LocalTime. Because LocalTime does not define `>=` and `<` comparison operators in Java, we use **isBefore**, **isAfter**, or **equals**.

A common mistake is using the condition:

~~~java
// WRONG for a window that crosses midnight.
boolean open = !t.isBefore(opens) && t.isBefore(closes);
~~~

If it opens at **22:00** and closes at **02:00**, no time on the same clock cycle is both `>= 22:00` and `< 02:00`. The result is always `false`. For overnight shifts, you must use **OR** in the second branch.

### Boundary Check Table

| Window | Time being checked | Result |
| --- | --- | --- |
| 09:00–17:00 | 08:59 | Closed |
| 09:00–17:00 | 09:00 | Open |
| 09:00–17:00 | 16:59 | Open |
| 09:00–17:00 | 17:00 | Closed |
| 22:00–02:00 | 21:59 | Closed |
| 22:00–02:00 | 22:00 | Open |
| 22:00–02:00 | 23:59 | Open |
| 22:00–02:00 | 00:00 | Open |
| 22:00–02:00 | 01:59 | Open |
| 22:00–02:00 | 02:00 | Closed |
| 22:00–02:00 | 12:00 | Closed |
| 22:00–00:00 | 23:00 | Open |
| 22:00–00:00 | 00:00 | Closed |

Midnight **00:00** can be included in the 22:00–02:00 window because the closing time is **02:00**. However, the 22:00–00:00 window ends **right at 00:00 the next day**, so 00:00 is no longer within the window.

## 5. Which Day Does an Overnight Shift Belong To?

Checking **LocalTime** alone is not enough for a day-of-week schedule. Suppose a shop is only open from **Monday 22:00 to Tuesday 02:00**.

- **Monday 23:00**: open.
- **Tuesday 01:00**: open, because it still belongs to the shift that started Monday night.
- **Tuesday 23:00**: closed if there is no shift starting on Tuesday, even though 23:00 falls within the 22:00–02:00 time window when ignoring the date.
- **Tuesday 02:00**: closed because it is the excluded endpoint.

You should define the days of the week as the **shift start date** (opening date, anchor date). When the time being checked falls within a midnight-crossing window:

1. If **t >= opens**, the shift start date is the date of the LocalDateTime being checked.
2. If **t < closes**, the shift start date is the **previous day**.
3. If **t** does not fall within the window, the result is not open under this window.

Example for a 22:00–02:00 shift:

| Time checked | Within time window? | Shift start date |
| --- | --- | --- |
| Monday 26/10/2026 23:00 | Yes | 26/10/2026 |
| Tuesday 27/10/2026 00:00 | Yes | 26/10/2026 |
| Tuesday 27/10/2026 01:00 | Yes | 26/10/2026 |
| Tuesday 27/10/2026 02:00 | No | Not applicable |
| Tuesday 27/10/2026 23:00 | Yes if checking time only | 27/10/2026: not in a Monday-only schedule |

Note that holiday schedules may be applied based on the **shift start date** or the **actual calendar date in progress**. For example, a rule mandating closure starting at 00:00 on a holiday may cut short the previous evening's shift. This policy must be defined independently of LocalTime operations.

## 6. Complete Java 17+ Example

Save the code to **OpeningHoursDemo.java**:

~~~java
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public class OpeningHoursDemo {
    record DailyWindow(LocalTime opens, LocalTime closes) {
        DailyWindow {
            Objects.requireNonNull(opens, "opens");
            Objects.requireNonNull(closes, "closes");

            if (opens.equals(closes)) {
                throw new IllegalArgumentException(
                        "Choose explicit CLOSED or ALL_DAY mode");
            }
        }

        boolean crossesMidnight() {
            return opens.isAfter(closes);
        }

        // Opening time is inclusive, closing time is exclusive.
        boolean contains(LocalTime value) {
            Objects.requireNonNull(value, "value");

            if (!crossesMidnight()) {
                return !value.isBefore(opens)
                        && value.isBefore(closes);
            }
            return !value.isBefore(opens)
                    || value.isBefore(closes);
        }

        // Call only when the time being checked falls within this window.
        LocalDate openingDateFor(LocalDateTime at) {
            if (!contains(at.toLocalTime())) {
                throw new IllegalArgumentException(
                        "Outside the opening window");
            }

            if (crossesMidnight()
                    && at.toLocalTime().isBefore(closes)) {
                return at.toLocalDate().minusDays(1);
            }
            return at.toLocalDate();
        }

        // operatingDays is the shift's opening day of the week.
        boolean isOpenOn(
                LocalDateTime at, Set<DayOfWeek> operatingDays) {
            return contains(at.toLocalTime())
                    && operatingDays.contains(
                            openingDateFor(at).getDayOfWeek());
        }

        LocalDateTime closingDateTimeFor(LocalDate openingDate) {
            LocalDate endDate = crossesMidnight()
                    ? openingDate.plusDays(1)
                    : openingDate;
            return LocalDateTime.of(endDate, closes);
        }

        // NOMINAL duration on the clock, without accounting for DST.
        Duration nominalDuration() {
            Duration value = Duration.between(opens, closes);
            return crossesMidnight()
                    ? value.plusDays(1)
                    : value;
        }
    }

    public static void main(String[] args) {
        DailyWindow office = new DailyWindow(
                LocalTime.of(9, 0), LocalTime.of(17, 0));
        DailyWindow night = new DailyWindow(
                LocalTime.of(22, 0), LocalTime.of(2, 0));

        System.out.println("Office 09:00: " +
                office.contains(LocalTime.of(9, 0)));
        System.out.println("Office 17:00: " +
                office.contains(LocalTime.of(17, 0)));
        System.out.println("Night 23:00: " +
                night.contains(LocalTime.of(23, 0)));
        System.out.println("Night 01:00: " +
                night.contains(LocalTime.of(1, 0)));
        System.out.println("Night 02:00: " +
                night.contains(LocalTime.of(2, 0)));
        System.out.println("Nominal night duration: " +
                night.nominalDuration());

        Set<DayOfWeek> mondayOnly =
                EnumSet.of(DayOfWeek.MONDAY);
        LocalDateTime monday2300 =
                LocalDateTime.of(2026, 10, 26, 23, 0);
        LocalDateTime tuesday0100 =
                LocalDateTime.of(2026, 10, 27, 1, 0);
        LocalDateTime tuesday2300 =
                LocalDateTime.of(2026, 10, 27, 23, 0);

        System.out.println("Monday 23:00: " +
                night.isOpenOn(monday2300, mondayOnly));
        System.out.println("Tuesday 01:00: " +
                night.isOpenOn(tuesday0100, mondayOnly));
        System.out.println("Tuesday 23:00: " +
                night.isOpenOn(tuesday2300, mondayOnly));
        System.out.println("Opening date for Tuesday 01:00: " +
                night.openingDateFor(tuesday0100));
        System.out.println("Closing date-time for Monday shift: " +
                night.closingDateTimeFor(
                        LocalDate.of(2026, 10, 26)));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 OpeningHoursDemo.java
java OpeningHoursDemo
~~~

**Standard output:**

~~~text
Office 09:00: true
Office 17:00: false
Night 23:00: true
Night 01:00: true
Night 02:00: false
Nominal night duration: PT4H
Monday 23:00: true
Tuesday 01:00: true
Tuesday 23:00: false
Opening date for Tuesday 01:00: 2026-10-26
Closing date-time for Monday shift: 2026-10-27T02:00
~~~

Analysis:

- Both shifts use the same **DailyWindow** type, but **crossesMidnight()** selects different formulas.
- The opening boundary is inclusive; the closing boundary is exclusive.
- **PT4H** is four nominal hours, calculated after adding one day for the 22:00–02:00 window.
- **26/10/2026** is a Monday, so the shift starting Monday 22:00 is still open at **Tuesday 01:00**.
- **Tuesday 23:00** is not in the Monday-only schedule.
- **closingDateTimeFor(2026-10-26)** returns **2026-10-27T02:00**: the closing date has moved to the next day. This is still a **LocalDateTime**, without a time zone or Instant specified.

The code rejects two equal times; to add **CLOSED** and **ALL_DAY** in a real application, use separate business statuses rather than implicitly changing the meaning of the time pair.

## 7. Duration Between Two LocalTime Values Can Be Negative

**Duration.between(LocalTime.of(22, 0), LocalTime.of(2, 0))** returns **PT-20H**, because the arguments are evaluated within the same clock day. Java does not automatically infer that it means "02:00 tomorrow."

~~~java
LocalTime opens = LocalTime.of(22, 0);
LocalTime closes = LocalTime.of(2, 0);

Duration raw = Duration.between(opens, closes);  // PT-20H
Duration nominal = raw.plusDays(1);              // PT4H
~~~

This snippet requires importing `java.time.*` and placing it inside a method.

For a regular window **09:00–17:00**, `Duration.between` returns **PT8H**, with no need to add a day. With **start = end**, Duration is **PT0S**, which **cannot distinguish** between closed all day and open 24 hours; an explicit status is required.

The nominal duration above is valid for **a recurring window shorter than 24 hours**. When you need to model a shift lasting 26 hours, two LocalTime values alone are not enough: you must also store the end date or a separate Duration.

### Clock Hours Differ from Actual Elapsed Hours

In regions with Daylight Saving Time transitions, a 22:00–03:00 shift can be 4, 5, or 6 actual hours long depending on the date. Only **Duration** between two specific **Instant** values accurately reflects the elapsed duration on the timeline.

## 8. When Must You Attach a ZoneId and Account for DST?

Clock-based opening hours are usually rules **at the business location**, so store an IANA **ZoneId**, such as **Asia/Ho_Chi_Minh** or **America/New_York**.

**ZoneId** holds offset rules over dates; **ZoneOffset** is only a fixed offset from UTC at a given point in time. You should not store only **-04:00** to represent New York opening hours year-round because that region observes DST.

In New York on **08/03/2026**, the clock jumps from just before **02:00** to **03:00**. Consider a shift from 22:00 on 07/03 to 03:00 on 08/03:

- Nominal duration on the clock: **5 hours**.
- Actual duration in UTC: **4 hours** because the hour from 02:00 to before 03:00 does not exist.

Place the following snippet inside a method and import `java.time.*`:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime starts = LocalDateTime.of(
        2026, 3, 7, 22, 0).atZone(zone);
ZonedDateTime ends = LocalDateTime.of(
        2026, 3, 8, 3, 0).atZone(zone);
Duration actual = Duration.between(
        starts.toInstant(), ends.toInstant());
// actual = PT4H
~~~

On a fall-back DST transition day, the same clock time such as **01:30** can occur twice with two different offsets, producing two distinct Instants. During a **gap**, a local time may not exist at all. **LocalDateTime.atZone(zone)** has default selection/adjustment rules; payroll or reservation confirmation applications should have an explicit policy rather than implicitly relying on defaults.

**ZoneRules.getValidOffsets(localDateTime)** tells you whether there are 0, 1, or 2 valid offsets; where needed, you can check **ZoneRules.getTransition(localDateTime)** and decide to reject the time, shift the time, or pick the earlier/later offset. Once both endpoints are resolved to Instants, use `Duration.between` to measure actual elapsed time.

An opening rule of **LocalTime 09:00** at a location will remain 09:00 on the zone's clock across DST changes, but its corresponding Instant can change. Therefore, do not use a fixed Instant to store the rule "opens every day at 09:00."

## 9. Multi-Window Schedules in a Single Day

A store schedule might look like this:

~~~text
Monday:
  09:00–12:00
  13:00–17:00
  22:00–02:00 (closes Tuesday)
~~~

**09:00–02:00** cannot replace all three windows because doing so would claim the store is open at **12:30**, even though it is closed for lunch. Instead, store a **list of windows**; for each window, check the time and the shift start date. If **at least one window matches** and it is not overridden by a closure exception, the location is considered open.

Issues that need additional rules:

- **Overlapping windows:** for the same store, you may need to normalize/merge them or report an error; for different counters, overlap might be allowed.
- **Shift start date:** Monday night's 22:00–02:00 shift must still be valid on Tuesday morning.
- **Holidays:** specify whether closures apply by shift start date or by the current time being checked; a closure order starting at 00:00 can cut off the previous night's shift.
- **Schedule exceptions:** holidays, maintenance, grand openings, and seasonal schedules should be entries with **specific dates** or effective date ranges.
- **Multiple locations:** each branch must have its own ZoneId and schedule.
- **24/7 schedules:** use an **ALL_DAY** type or continuous-open policy rather than relying on a confusing 00:00–00:00 pair.

When sorting **actual** shifts across days, convert each shift into a **LocalDateTime** or **ZonedDateTime** pair with specific dates. Sorting by LocalTime alone will place 01:00 before 22:00 even though it is the **later part of the same night shift**.

## 10. Data Model and API

An illustrative configuration:

~~~json
{
  "zone": "Asia/Ho_Chi_Minh",
  "openingDays": ["MONDAY", "TUESDAY", "FRIDAY"],
  "windows": [
    { "opens": "09:00", "closes": "12:00" },
    { "opens": "13:00", "closes": "17:00" },
    { "opens": "22:00", "closes": "02:00" }
  ],
  "boundaryRule": "start-inclusive-end-exclusive",
  "overnightOwnership": "opening-date",
  "equalTimeRule": "reject; use CLOSED or ALL_DAY"
}
~~~

This is an **illustrative contract JSON**, not a built-in standard Java format.

You should standardize:

1. **opens** and **closes** in ISO **HH:mm** format, or `HH:mm:ss` if second-level precision is needed.
2. Days of the week represent the **shift start date**, not by default the query date.
3. **CLOSED** and **ALL_DAY** statuses are passed explicitly.
4. The location's IANA ZoneId is stored separately from LocalTime.
5. Rules for handling holidays, DST gaps/overlaps, and schedule effective dates are documented.
6. Timestamps recording check-in/check-out use **Instant**; recurring schedule records use LocalTime.

An SQL **TIME** column is often mapped to LocalTime, but it contains no date, no ZoneId, and does not represent "closing time is on the next day." If using JDBC/ORM, verify the actual mapping and store the shift date/day of the week alongside the business rules.

## 11. Input Validation and Formatting

**LocalTime.parse("22:00")** supports common ISO representations. If receiving times as text, you can configure a formatter:

~~~java
DateTimeFormatter format =
        DateTimeFormatter.ofPattern("HH:mm");
LocalTime opens = LocalTime.parse("22:00", format);
LocalTime closes = LocalTime.parse("02:00", format);
~~~

This is a snippet; you need to import `LocalTime` and `java.time.format.DateTimeFormatter`, and place it inside a method. If the input is invalid, such as **25:00** or **12:90**, `LocalTime.parse` throws a **DateTimeParseException**.

Note that **HH** uses hours 0–23, **mm** is minutes, and **MM** is months. Do not compare times as unnormalized strings like `"9:00"` and `"22:00"`, because lexicographical order does not necessarily match clock order.

If the UI only accepts minute-level precision, apply the same rule to all windows; when the system compares against timestamps with seconds/nanoseconds, the half-open condition remains accurate: **01:59:59.999999999** is before 02:00; **02:00:00** is closed.

## 12. Using Clock to Check "Currently Open" for the Right Location

The server's clock may differ from the store's time. Therefore:

- Obtain **Instant.now(clock)** from an injected/configured Clock.
- Use **instant.atZone(storeZone)** to get the branch's local date and time.
- From **ZonedDateTime**, call **toLocalDateTime()** to evaluate the list of windows and shift start dates.
- After determining the valid schedule, apply exception/holiday policies.

Example snippet assuming you already have a `DailyWindow` object, the necessary imports, and a `Clock`:

~~~java
Instant current = Instant.now(clock);
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime storeNow =
        current.atZone(storeZone).toLocalDateTime();
boolean open = window.isOpenOn(storeNow, openingDays);
~~~

When testing, use **Clock.fixed(...)** for repeatable results. If checking payroll or waiting times, take `Instant` at the two specific points; if only checking the clock-based opening schedule, the location's `LocalDateTime` is appropriate.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using AND for a 22:00–02:00 shift | Always reports closed | Use OR in the overnight branch |
| Including the closing time | Exactly 02:00 still reports open | Use the **[start, end)** interval |
| Treating 00:00–00:00 as 24-hour open without a contract | Other systems interpret it as closed all day | Use explicit CLOSED/ALL_DAY |
| Using `Duration.between(22:00, 02:00)` directly to get 4 hours | Actually returns -20 hours | Add 1 nominal day when known to cross midnight |
| Checking the day of week of the query timestamp | Tuesday 01:00 is excluded from Monday's shift | Find the **shift start date** |
| Using `LocalTime.plusHours` to get tomorrow's closing time | Loses date information | Use LocalDateTime and the end date |
| Using a fixed UTC offset for a recurring New York schedule | Time drifts when DST changes | Store the ZoneId |
| Treating nominal Duration as actual worked hours | Wrong across DST transitions | Measure Duration between Instants |
| Merging shifts with a lunch break into one window | Reports open while the store is on break | Store a list of windows |
| Ignoring holidays or unexpected closures | Wrongly concludes "open" | Apply an exceptions layer |
| Trying to store 24:00 in LocalTime | Invalid value | Use 00:00 of the next day |
| Comparing unnormalized time strings | Wrong comparisons | Parse into LocalTime |
| Using LocalTime instead of a timestamp | Missing date/zone | Use Instant when recording events |

## 14. Recommended Test Cases

| Case | Data | Expected per lesson policy |
| --- | --- | --- |
| Before opening | 09:00–17:00, 08:59 | Closed |
| Exactly at opening | 09:00–17:00, 09:00 | Open |
| Exactly at closing | 09:00–17:00, 17:00 | Closed |
| Before midnight | 22:00–02:00, 23:59 | Open |
| After midnight | 22:00–02:00, 00:01 | Open |
| Exactly at overnight closing | 22:00–02:00, 02:00 | Closed |
| Closing at midnight | 22:00–00:00, 00:00 | Closed |
| Monday shift, Tuesday 01:00 | 22:00–02:00, MONDAY | Open |
| Monday shift, Tuesday 23:00 | 22:00–02:00, MONDAY | Closed |
| Two equal times | 00:00–00:00 | Require CLOSED/ALL_DAY |
| Invalid input time | 25:00 | Report error |
| Lunch break gap | 09:00–12:00 and 13:00–17:00, query 12:30 | Closed |
| Ad-hoc holiday | Valid weekly shift but on a holiday | Follow exception policy |
| DST starts | Shift crosses skipped hour | Check zone rules and actual length |
| DST ends | Shift crosses repeated hour | Check offset selection |

In particular, test **exact boundaries**, **shift start date**, **midnight**, **multi-shift schedules**, and **DST** if the location observes time changes.

## 15. Self-Check Questions

**1. Why does checking opening hours with AND always fail for 22:00–02:00?**

Because no time in a single clock day is both `>= 22:00` and `< 02:00`. You must choose **OR** for the midnight-crossing case.

**2. Does a 22:00–00:00 shift include exactly 00:00?**

No. Under the **[open, close)** interval, 00:00 is the closing time on the next day.

**3. Is a shift that only opens Monday night 22:00–02:00 open at Tuesday 01:00?**

Yes, because Tuesday 01:00 still belongs to the shift that started on Monday. You need to compute the shift start date before checking DayOfWeek.

**4. Does 00:00–00:00 definitely mean open 24 hours?**

No. Equal timestamps cannot distinguish between closed all day and open all day. Use an explicit status.

**5. Does `LocalTime.of(23, 0).plusHours(3)` automatically return the next day?**

No. The result is only LocalTime **02:00**. To preserve date information, you must combine it with LocalDate/LocalDateTime.

**6. How many hours does `Duration.between(22:00, 02:00)` return?**

**-20 hours**; it does not automatically infer crossing to the next day. For an overnight shift with a nominal duration under 24 hours, add one nominal day to get **4 hours**.

**7. Is a 22:00–03:00 shift in New York always exactly 5 actual hours long?**

No. Across DST start/end dates, the actual duration can differ. You need a specific date, a ZoneId, a policy for resolving ambiguous times, and two Instants.

## Official References

- [Java SE 17 — LocalTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html): representing clock time, comparisons, and addition/subtraction.
- [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html): local date and time.
- [Java SE 17 — DayOfWeek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DayOfWeek.html): day-of-week schedules.
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): measuring time intervals.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): attaching a zone and resolving an instant.
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offsets, gaps, and overlaps.
