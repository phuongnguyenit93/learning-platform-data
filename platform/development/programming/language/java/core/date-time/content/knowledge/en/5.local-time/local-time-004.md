# Adding and Subtracting Time with LocalTime and Midnight Wrap-Around

**LocalTime** in the **java.time** package represents **a time of day**, from **00:00:00.000000000** to **23:59:59.999999999**. When adding or subtracting time causes the clock to cross midnight, the result **wraps around within a 24-hour range**. This is the core characteristic of LocalTime: it only holds the clock position within a day, carrying no date, time zone, or number of days elapsed.

For example, adding 90 minutes to **23:40** yields **01:10**. This operation is correct for **clock time**, but the LocalTime result **cannot tell you that 01:10 belongs to the next day**. If you need the actual date, deadline calculation, or elapsed time, you must supplement it with appropriate information.

This lesson uses Java 17+ and focuses on **plusHours**, **plusMinutes**, **plusSeconds**, **plusNanos**, the **minus…** methods, wrap-around behavior, how to compare time intervals that cross midnight, and how to avoid losing date information.

## 1. What Does LocalTime Represent?

The following values are all valid **LocalTime** instances:

- **00:00**: start of the clock day, available as the constants **LocalTime.MIDNIGHT** or **LocalTime.MIN**.
- **12:00**: noon, available as the constant **LocalTime.NOON**.
- **23:59:59.999999999**: the maximum time in a day, available as the constant **LocalTime.MAX**.
- **09:30**: opening hours, class start time, or a daily recurring alarm time.

LocalTime **does not contain** a date, day of the week, time zone, UTC offset, or Daylight Saving Time (DST) rules. Two **LocalTime.of(9, 0)** values are equal whether one person is in Hanoi and another is in New York: they both express **09:00 on the clock**, without identifying the same actual instant in time.

Some scenarios suited for LocalTime:

| Requirement | Is LocalTime suitable? | Why |
|---|---|---|
| Branch opening hour at 08:30 every day | Yes | Only needs time of day |
| Choosing a daily reminder time at 23:00 every night | Yes, paired with a recurrence rule if needed | A clock mark, not an absolute instant |
| Adding 45 minutes to a start time on the clock | Yes | The result is another time of day |
| Recording when an order occurred | Not sufficient | Needs **Instant** or full date-time data |
| Calculating a shift starting today and ending tomorrow | Not sufficient on its own | Needs **LocalDateTime** or start/end dates |
| Calculating 8 elapsed hours across a DST transition | Not sufficient | Needs an instant with an appropriate time zone/context |

**Rule of thumb:** only choose LocalTime when the business logic genuinely cares only about **the time on a clock face**. When the problem asks "which day", "how many actual hours later", or "when is this instant in UTC", LocalTime needs additional information.

## 2. Addition and Subtraction Methods

Common methods of LocalTime:

| Add time | Subtract time | Parameter |
|---|---|---|
| **plusHours(long)** | **minusHours(long)** | Number of hours |
| **plusMinutes(long)** | **minusMinutes(long)** | Number of minutes |
| **plusSeconds(long)** | **minusSeconds(long)** | Number of seconds |
| **plusNanos(long)** | **minusNanos(long)** | Number of nanoseconds |
| **plus(TemporalAmount)** | **minus(TemporalAmount)** | A compatible amount of time, e.g., **Duration** |
| **plus(long, TemporalUnit)** | **minus(long, TemporalUnit)** | A supported unit, e.g., **ChronoUnit.MINUTES** |

Simple example:

~~~java
LocalTime start = LocalTime.of(9, 15);

LocalTime afterOneHour = start.plusHours(1);      // 10:15
LocalTime after45Minutes = start.plusMinutes(45); // 10:00
LocalTime before20Minutes = start.minusMinutes(20); // 08:55
~~~

This snippet is **illustrative**, assuming **java.time.LocalTime** is already imported; a standalone runnable program is provided in Section 6.

**LocalTime is immutable**. Each method returns a new LocalTime value or an equivalent value; it **does not modify the original object**. You must use the returned result:

~~~java
LocalTime alarm = LocalTime.of(7, 0);
alarm.plusMinutes(30);             // Does not modify the alarm variable
alarm = alarm.plusMinutes(30);     // alarm is now 07:30
~~~

You do not need to compare references with **==** to infer behavior; use **equals()**, **isBefore()**, **isAfter()**, or **compareTo()** when comparing values.

### Negative Numbers in Addition/Subtraction

For typical small amounts of time:

- **plusMinutes(-15)** corresponds to moving backward 15 minutes.
- **minusMinutes(-15)** corresponds to moving forward 15 minutes.
- **plusHours(24)** or **minusHours(24)** returns the same clock time.
- Adding or subtracting more hours than a single day still returns only a time of day.

These methods accept **long**, but the LocalTime result always stays within **a single 24-hour cycle**. If the number of hours or days elapsed is a business result that needs to be preserved, do not use LocalTime alone.

## 3. Why Does the Clock Wrap Around Midnight?

A clock day in the LocalTime model has:

- **24 hours**;
- **1,440 minutes**;
- **86,400 seconds**;
- **86,400,000,000,000 nanoseconds**.

When adding or subtracting, LocalTime computes the result within **a one-day cycle**. You can visualize it as:

~~~text
23:00 ── +1 hour ──> 00:00
23:40 ── +90 minutes ──> 01:10
00:15 ── -45 minutes ──> 23:30
09:00 ── +25 hours ──> 10:00
09:00 ── +24 hours ──> 09:00
~~~

Starting from **23:40** and adding **90 minutes**:

1. There are **20 minutes** remaining until **00:00**.
2. **70 minutes** remain after the clock rolls into the new day.
3. **70 minutes = 1 hour 10 minutes**, so the returned LocalTime value is **01:10**.

Starting from **00:15** and subtracting **45 minutes** wraps back to **23:30** on the clock.

**Important:** the result **01:10** by itself does not prove that it moved to the next day. If you add **48 hours**, the LocalTime result is still equal to the start time even though two days may have elapsed in the process. LocalTime does not provide a **dayCarry** field, does not return the number of days crossed, and does not implicitly attach a LocalDate.

### Intuitive Formula for Wrap-Around

If you convert every time of day to minutes since midnight (**0 to 1,439**), then:

~~~text
new_minute = floorMod(old_minute + delta_minutes, 1440)
~~~

Example:

~~~text
23:40 = 23 × 60 + 40 = 1420 minutes
1420 + 90 = 1510
1510 mod 1440 = 70
70 minutes from 00:00 = 01:10
~~~

When subtracting an amount larger than the initial minutes, you must use **non-negative modulo** if computing manually: in Java, the **%** operator preserves the sign of the left operand, so **(-30) % 1440** yields **-30**, which is not a valid minute of the day. **Math.floorMod(-30, 1440)** yields **1410**, corresponding to **23:30**. In normal Java business code, prefer **LocalTime.plusMinutes(...)** or **minusMinutes(...)** rather than handling modulo manually.

The formula above describes precision down to **minutes**. LocalTime supports precision down to **nanoseconds**, so adding seconds or nanoseconds is not restricted to whole minutes.

## 4. Crossing Midnight at Each Level of Precision

### 4.1. Hours and Minutes

~~~java
LocalTime.of(23, 0).plusHours(2);      // 01:00
LocalTime.of(23, 59).plusMinutes(2);  // 00:01
LocalTime.of(0, 10).minusMinutes(20); // 23:50
~~~

The comments show the **clock time after the calculation**. If the system needs "01:00 tomorrow", you must keep track of the **start date** yourself.

### 4.2. Seconds

~~~java
LocalTime.of(23, 59, 59).plusSeconds(1); // 00:00
LocalTime.of(0, 0, 0).minusSeconds(1);   // 23:59:59
~~~

LocalTime operates on a day of **86,400 clock seconds** and does not represent **23:59:60** as a leap second. Do not use LocalTime alone to build astronomical timekeeping or real-world system time calculations that have special clock requirements.

### 4.3. Nanoseconds

~~~java
LocalTime.MIDNIGHT.minusNanos(1); // 23:59:59.999999999
LocalTime.MAX.plusNanos(1);       // 00:00
~~~

**LocalTime.MAX** sits right before midnight in the nanosecond-precision model. Do not treat **23:59:59.999999999** as a universal "end of day" representation across all databases: many systems store lower precision. When you need a time range for a day, it is standard practice to use **start-inclusive, end-exclusive** bounds with an appropriate date or timestamp.

### 4.4. Adding More Than One Day

~~~java
LocalTime.of(9, 0).plusHours(25);     // 10:00
LocalTime.of(9, 0).plusHours(48);     // 09:00
LocalTime.of(9, 0).minusHours(49);    // 08:00
~~~

The results only return the **position on the clock**. Therefore, you cannot look at **09:00** to tell whether **0**, **24**, **48**, or **72** hours were added. If "how much time has elapsed?" is a business question, store the length with **Duration** and anchor points with a date or Instant.

## 5. Adding Duration and Supported Unit Limits

**Duration** represents an amount of time in seconds and nanoseconds; it is well suited for describing adding 75 minutes or subtracting 2 hours on a clock.

~~~java
import java.time.Duration;
import java.time.LocalTime;

LocalTime time = LocalTime.of(23, 30);
LocalTime later = time.plus(Duration.ofMinutes(75)); // 00:45
~~~

**Duration.ofHours(26)** can be added to LocalTime and the result will still be the wrapped-around time. However, LocalTime does not record "one day plus two hours".

Not every **TemporalUnit** or **TemporalAmount** is supported by LocalTime. It handles time-based units from nanoseconds up to half-days under the **Temporal** contract, whereas day/month/year units belong to the calendar:

~~~java
LocalTime.NOON.plus(1, ChronoUnit.DAYS);
~~~

The last statement throws **UnsupportedTemporalTypeException** because LocalTime has no date information. **Period.ofDays(1)** is also not a way to add days to LocalTime. If you need "tomorrow at 12:00", use **LocalDate.plusDays(1)** combined with LocalTime, or **LocalDateTime.plusDays(1)**.

## 6. Runnable Java 17+ Program: Wrap-Around Addition/Subtraction

Create a file named **LocalTimeWrapDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class LocalTimeWrapDemo {
    public static void main(String[] args) {
        LocalTime start = LocalTime.of(23, 40);

        System.out.println("start=" + start);
        System.out.println("plus90m=" + start.plusMinutes(90));
        System.out.println("minus45m=" +
                LocalTime.of(0, 15).minusMinutes(45));
        System.out.println("plus25h=" +
                LocalTime.of(9, 0).plusHours(25));
        System.out.println("plus24h=" +
                LocalTime.of(9, 0).plusHours(24));
        System.out.println("minusNano=" +
                LocalTime.MIDNIGHT.minusNanos(1));

        System.out.println("addDuration=" +
                start.plus(Duration.ofMinutes(90)));
        System.out.println("rawBetween=" +
                Duration.between(start, start.plusMinutes(90))
                        .toMinutes());

        LocalDateTime first =
                LocalDate.of(2026, 10, 24).atTime(start);
        LocalDateTime next = first.plusMinutes(90);

        System.out.println("dateTime=" + next);
        System.out.println("elapsed=" +
                Duration.between(first, next).toMinutes());
    }
}
~~~

Compile and run:

~~~bash
javac LocalTimeWrapDemo.java
java LocalTimeWrapDemo
~~~

Output:

~~~text
start=23:40
plus90m=01:10
minus45m=23:30
plus25h=10:00
plus24h=09:00
minusNano=23:59:59.999999999
addDuration=01:10
rawBetween=-1350
dateTime=2026-10-25T01:10
elapsed=90
~~~

**Explanation of key outputs:**

- **plus90m=01:10** proves that LocalTime wraps around midnight.
- **plus24h=09:00** shows that a full 24-hour cycle does not change the clock time value.
- **minusNano** shows that LocalTime supports boundaries at nanosecond precision.
- **rawBetween=-1350** is a commonly misunderstood result: **Duration.between(23:40, 01:10)** when both are just LocalTime computes the difference between two values on **the same assumed day**, so **01:10 comes before 23:40** by 1,350 minutes. The API does not automatically guess that the end time belongs to tomorrow.
- **dateTime=2026-10-25T01:10** preserves the fact that it crossed into the next day.
- **elapsed=90** is the actual length of adding 90 minutes on LocalDateTime in a calendar model without a time zone. If a zone with DST is attached, you need a separate real-instant model as shown in Section 9.

## 7. Comparing Times and Computing Intervals Across Midnight

**isBefore**, **isAfter**, and **compareTo** on LocalTime compare **time of day**, without inferring real-world event order.

~~~java
LocalTime begin = LocalTime.of(23, 30);
LocalTime end = LocalTime.of(1, 0);

System.out.println(end.isBefore(begin)); // true
~~~

The **true** result is right for clock-face values: **01:00** is less than **23:30**. But if a shift starts at **23:30 today** and ends at **01:00 tomorrow**, the end event actually occurs **after** the start event.

Similarly:

~~~java
Duration.between(LocalTime.of(23, 30),
                 LocalTime.of(1, 0)).toMinutes(); // -1350
~~~

**Duration.between** does not automatically deduce "90 minutes". To calculate it accurately, you must determine the **end date** or have an explicit business rule for crossing midnight.

### Rule for Shifts Under 24 Hours

If a contract specifies that:

1. The shift starts on the specified date;
2. The shift is **no longer than 24 hours**;
3. If the end time is less than the start time, it is **the next day**;
4. If the end time equals the start time, it must explicitly state whether that means **0 hours or a full 24 hours**;

then you can use **LocalDateTime** to retain the end date. For shifts longer than 24 hours or shifts where start/end dates are explicitly provided by the user, you must store an **explicit end date** instead of guessing.

## 8. Practical Example: Work Shift from 22:30 to 01:15 the Next Day

Create a file named **OvernightShiftDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class OvernightShiftDemo {
    public static void main(String[] args) {
        LocalDate businessDay = LocalDate.of(2026, 10, 24);
        LocalTime opens = LocalTime.of(22, 30);
        LocalTime closes = LocalTime.of(1, 15);

        LocalDateTime openedAt = businessDay.atTime(opens);

        // Only valid for shifts shorter than 24 hours per contract.
        LocalDate closeDay = closes.isBefore(opens)
                ? businessDay.plusDays(1)
                : businessDay;

        LocalDateTime closedAt = closeDay.atTime(closes);

        System.out.println("opened=" + openedAt);
        System.out.println("closed=" + closedAt);
        System.out.println("minutes=" +
                Duration.between(openedAt, closedAt).toMinutes());
    }
}
~~~

Run:

~~~bash
javac OvernightShiftDemo.java
java OvernightShiftDemo
~~~

Output:

~~~text
opened=2026-10-24T22:30
closed=2026-10-25T01:15
minutes=165
~~~

**Why is LocalDateTime needed?** For clock times, **01:15** is "less than" **22:30**; for shifts anchored with a **date**, **01:15 on Oct 25** occurs after **22:30 on Oct 24**. **Duration.between** on the two LocalDateTime instances returns **165 minutes**, which corresponds to 2 hours and 45 minutes in a continuous local timeline model.

If a shift can last **24 hours**, **36 hours**, or span multiple days, comparing two LocalTimes **does not tell you** how many days have elapsed. In that case, you need explicit **startDateTime** and **endDateTime** data or a business-supplied **Duration**.

**Important exception:** LocalDateTime also does not automatically represent offset changes due to DST. To calculate elapsed working time in a region with Daylight Saving Time, you must resolve the start/end instants in the ZoneId and then compute using **Instant** or an appropriate ZonedDateTime; see Section 9.

## 9. Midnight, Calendar Dates, and DST Are Three Different Concerns

The wrap-around behavior of **LocalTime** is a **24-hour mathematical rule**. It has **no direct relation** to the fact that real time zones can have days that are 23, 24, or 25 hours long.

For example:

- **LocalTime.of(23, 30).plusHours(2)** gives **01:30**, regardless of location or date. With no time zone, it cannot know whether that span crosses a DST transition.
- **LocalDateTime.of(2026, 10, 24, 23, 30).plusHours(2)** gives **2026-10-25T01:30**, preserving the local calendar date but still without determining a UTC offset.
- When an event has a **ZoneId**, local clock times may not exist or may repeat on a DST transition day. To measure **2 actual elapsed hours**, you typically take **start Instant + Duration.ofHours(2)** and display it in the desired zone.
- If the business requirement is to **preserve the clock time**, such as "09:00 every day in New York", you must use local calendar rules + ZoneId; do not add a fixed 24 hours to the previous Instant.

**Do not conflate them:**

| Question | Appropriate data/calculation |
|---|---|
| "After 120 minutes, what time does the clock show?" | **LocalTime.plusMinutes(120)** |
| "What date and time is it 120 minutes later?" | **LocalDateTime.plusMinutes(120)** if adding on a local calendar |
| "What exact instant is 120 real minutes later?" | **Instant.plus(Duration.ofMinutes(120))** |
| "Does the store open tomorrow at 09:00 local time?" | **LocalDate + LocalTime + ZoneId** |
| "How many actual hours did a shift last on a DST transition day?" | Two instants resolved with ZoneId/offset → **Instant** → **Duration.between** |

DST rules belong to **ZonedDateTime**, **ZoneRules**, and the full calendar model. **LocalTime does not automatically adjust for time zones and does not throw a DST exception just because it wraps past 00:00**.

## 10. Handling Midnight in Data Models and APIs

### 10.1. How to Represent Daily Recurring Schedules

An alarm at **06:30** or a recurring closing time at **01:00** fits **LocalTime**. However, if the **01:00 closing time belongs to the next morning** relative to the **22:00** opening time, you should make this rule explicit in the business model, for example:

~~~json
{
  "openingTime": "22:00",
  "closingTime": "01:00",
  "closingDayOffset": 1,
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

This is an **example API contract**, not a default Java structure. **closingDayOffset=1** captures the "next day" intent; **zoneId** identifies the zone if the application needs to materialize actual occurrences. This payload does not automatically cover holidays, exception days, or DST; those factors must be modeled separately if required by the business.

### 10.2. Time Intervals Crossing 00:00

An actual time interval should have **start/end timestamps** with full context:

~~~json
{
  "startLocal": "2026-10-24T22:30:00",
  "endLocal": "2026-10-25T01:15:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

When you need to store **absolute instants**, after resolving the zone and validating the local time, you can also store the Instant; if you need to preserve the scheduled intent, keep **local time + zone**.

### 10.3. End-of-Day Boundaries

There is no **LocalTime.of(24, 0)** in standard LocalTime values. **24:00** is often a way of expressing "00:00 of the next day" in some display conventions, whereas LocalTime represents midnight as **00:00**.

To define the interval "[today, tomorrow)", use **LocalDate.atStartOfDay(zone)** for the start of the day and the start of the next day as **endExclusive**; do not try to construct **24:00** or hardcode "23:59:59.999999999" as an upper bound for every database.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming **23:40.plusMinutes(90)** includes the next day | LocalTime only returns **01:10**; date info is lost | Use LocalDateTime if you need the date |
| Thinking **plusHours(24)** indicates a day has passed | Result is the exact same time | Track the date or duration separately |
| Using **isBefore()** to conclude an overnight shift ends before it starts | Clock-face comparison differs from event order | Compare timestamps that include dates |
| Using **Duration.between(23:40, 01:10)** expecting 90 minutes | Returns **-1350 minutes** | Determine the end date or apply a <24h shift contract |
| Seeing end time equals start time and always assuming 24 hours | Could be 0 hours; could also be multiple days | Explicitly specify dates or length |
| Adding **ChronoUnit.DAYS** directly to LocalTime | Unsupported unit | Use LocalDate/LocalDateTime |
| Adding hours without assigning the returned value | LocalTime is immutable | **time = time.plusHours(...)** |
| Computing actual hours across DST using plain LocalTime or LocalDateTime | Actual hour count may be off | Resolve the zone and compute using Instant |
| Storing closing time **01:00** without keeping the "next day" rule | Cannot tell if the shift crosses midnight | Store an explicit day offset or end date |
| Accepting **24:00** as a normal LocalTime | Invalid data for the model | Interpret as **00:00 next day** if required by the contract |

## 12. Checklist Before Using LocalTime for Addition/Subtraction

1. Does the problem only need **clock time**, or does it also need a **date**?
2. Can the operation cross **00:00** or exceed **24 hours**?
3. Does the result need the **number of days elapsed**? If so, do not use LocalTime alone.
4. Are you calculating a **displayed clock time** or **actual elapsed duration**?
5. If calculating an overnight shift, is the **end date** entered directly or inferred from a bounded rule?
6. Does **start == end** mean a 0-hour shift, a 24-hour shift, or require extra data?
7. Are **ZoneId** and DST involved in the business logic?
8. Have you properly tested boundaries like **23:59:59**, **00:00**, negative minutes, values over 24 hours, and nanoseconds?

### Self-Check Questions

**1.** What is **23:50.plusMinutes(20)**?  
**Answer:** **00:10**, without any date information.

**2.** What is **00:10.minusMinutes(20)**?  
**Answer:** **23:50**, without automatically indicating the previous day.

**3.** What is **09:00.plusHours(49)**?  
**Answer:** **10:00**, because 49 hours = two 24-hour cycles plus 1 hour.

**4.** What does **LocalTime.of(22, 0).until(LocalTime.of(1, 0), ChronoUnit.HOURS)** return?  
**Answer:** **-21**, because it computes between two clock times on the same assumed day and does not automatically assume an overnight shift.

**5.** What should you use to find how long "a shift starting at 22:00 on Oct 24 and ending at 01:00 on Oct 25" lasts?  
**Answer:** Two **LocalDateTime** instances and **Duration.between**, which gives 3 hours on the local calendar; if you want actual elapsed hours in a zone with DST, you must resolve the zone/offset and compute on Instant.

**6.** Can you add 90 minutes to a LocalTime without knowing the time zone?  
**Answer:** Yes, if you only need the clock-face time. You cannot determine the UTC instant or DST rules from that result.

**Key takeaway:** **LocalTime.plus… / minus… wraps around within 24 hours** and does not store elapsed days. Use LocalTime for **clock-time** operations, LocalDateTime for **local date + time**, and Instant/ZonedDateTime when you need **real instants with time zone context**. Bugs usually do not lie in the addition itself, but in a data model that dropped the date or zone rules required by the business logic.
