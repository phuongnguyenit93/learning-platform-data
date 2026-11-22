# Combining LocalDate and LocalTime into LocalDateTime in Java

**LocalDate** represents a calendar date (year–month–day), while **LocalTime** represents a time of day (hour–minute–second–nanosecond). When a business use case has **both date and time**, Java allows combining these two objects into a **LocalDateTime**. For example, the date **24/10/2026** and the time **09:30** produce **2026-10-24T09:30**.

**Key point:** LocalDateTime is still a **local date-time without a time zone**. Combining them does not create an Instant, does not automatically choose a UTC offset, and does not automatically know whether that time is in Vietnam, Tokyo, or New York.

This lesson uses Java 17+, focusing on **LocalDate.atTime(LocalTime)**, **LocalDateTime.of(LocalDate, LocalTime)**, how to split them back, parsing input data, calculations across midnight, and adding a ZoneId when an actual instant in time needs to be determined.

## 1. Meaning of the Three Data Types

| Type | Retained Data | Example | Does Not Contain |
|---|---|---|---|
| **LocalDate** | Year–month–day | 2026-10-24 | Hour, offset, ZoneId |
| **LocalTime** | Hour–minute–second–nanosecond | 09:30:15.123 | Date, offset, ZoneId |
| **LocalDateTime** | Local date and time | 2026-10-24T09:30:15.123 | Offset, ZoneId |

Use LocalDate when you only need a birth date or a holiday. Use LocalTime when you only need a daily recurring opening hour. Use LocalDateTime when you need a **specific date + time**, such as an appointment or an exam start time. Use Instant when you need an **absolute point in time** such as createdAt, and a ZoneId is required to convert a LocalDateTime with local meaning into an Instant.

The name **Local** does not mean "automatically use the server's timezone". It states that the type **does not yet contain zone or offset information**.

## 2. Combining with LocalDate.atTime(LocalTime)

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.LocalDateTime;

LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime meeting = date.atTime(time);
~~~

This is an **illustrative snippet inside a method**, not a complete program. **meeting** has the value **2026-10-24T09:30**.

**date.atTime(time)** preserves all year/month/day components of date and all hour/minute/second/nano components of time. It does **not** attach a time zone or convert to UTC.

These three types are **immutable**:

- Combining does not modify date or time.
- The operation **meeting.plusHours(2)** returns a new LocalDateTime; if the result is not assigned, the meeting variable does not change.
- Compare contents using **equals()**, **isBefore()**, **isAfter()**; do not use **==** to compare values.

## 3. Combining with LocalDateTime.of(date, time)

Equivalent approach:

~~~java
LocalDateTime first = date.atTime(time);
LocalDateTime second = LocalDateTime.of(date, time);
boolean same = first.equals(second); // true
~~~

Both are standard APIs. **date.atTime(time)** is natural when you already have a LocalDate; **LocalDateTime.of(date,time)** is clear when starting from the target type name.

If you do not yet have two separate objects, use the overloads that accept individual fields:

~~~java
LocalDateTime simple =
        LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDateTime precise =
        LocalDateTime.of(2026, 10, 24, 9, 30, 15, 123_000_000);
~~~

The results are **2026-10-24T09:30** and **2026-10-24T09:30:15.123**.

LocalDate also has convenience methods:

~~~java
LocalDate day = LocalDate.of(2026, 10, 24);
LocalDateTime afternoon = day.atTime(17, 45);
LocalDateTime midnight = day.atStartOfDay();
~~~

**afternoon** is **2026-10-24T17:45**; **midnight** is **2026-10-24T00:00**.

**Distinguishing overloads:** **date.atStartOfDay()** returns a zoneless LocalDateTime, whereas **date.atStartOfDay(zone)** returns a ZonedDateTime and applies the start-of-day rules of that zone, which may not be exactly 00:00 in special cases.

## 4. Complete Java 17+ Program

Create the file **CombineDateTimeDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class CombineDateTimeDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30, 15, 123_000_000);

        LocalDateTime meeting = day.atTime(time);
        LocalDateTime alternative = LocalDateTime.of(day, time);

        System.out.println("meeting=" + meeting);
        System.out.println("same=" + meeting.equals(alternative));
        System.out.println("atTimeHourMinute=" + day.atTime(17, 45));
        System.out.println("midnight=" + day.atStartOfDay());
        System.out.println("date=" + meeting.toLocalDate());
        System.out.println("time=" + meeting.toLocalTime());
        System.out.println("nextDay=" + meeting.plusDays(1));
    }
}
~~~

Run:

~~~bash
javac CombineDateTimeDemo.java
java CombineDateTimeDemo
~~~

Stdout:

~~~text
meeting=2026-10-24T09:30:15.123
same=true
atTimeHourMinute=2026-10-24T17:45
midnight=2026-10-24T00:00
date=2026-10-24
time=09:30:15.123
nextDay=2026-10-25T09:30:15.123
~~~

Explanation: **123_000_000 nanoseconds** is **0.123 seconds**, so combining still preserves **09:30:15.123**. Both ways of combining produce equal values. **toLocalDate()** and **toLocalTime()** retrieve each part. **plusDays(1)** returns a new date, yet it is still a local date-time value without a known ZoneId.

## 5. Splitting Back into Two Components

~~~java
LocalDateTime event =
        LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDate datePart = event.toLocalDate();
LocalTime timePart = event.toLocalTime();

LocalDateTime restored = datePart.atTime(timePart);
boolean same = restored.equals(event); // true
~~~

This illustrative snippet is placed inside a method that has imported **java.time**.

You can use these methods when an API returns a LocalDateTime but the UI has two separate date/time pickers. Splitting and combining preserve components down to nanosecond precision. However, if the UI or database only keeps **HH:mm**, seconds and nanoseconds may be lost **at the formatting/storage layer**, not because of atTime.

For example, **LocalTime.of(9, 30, 15, 123_000_000)** differs from **LocalTime.of(9, 30)**; you need to decide at the business level whether to store precision to minutes, seconds, or nanoseconds.

## 6. LocalDateTime Has No ZoneId and Is Not an Instant

Suppose two input fields are:

~~~text
date = 2026-01-01
time = 00:30
combined = 2026-01-01T00:30
~~~

If **combined** is interpreted in UTC, the corresponding Instant is **2026-01-01T00:30:00Z**. If interpreted in **Asia/Ho_Chi_Minh**, the Instant is **2025-12-31T17:30:00Z**. The two points in time differ by 7 hours despite having the same LocalDateTime.

To convert, a valid ZoneId or ZoneOffset is required:

~~~java
LocalDateTime local =
        LocalDate.of(2026, 1, 1).atTime(LocalTime.of(0, 30));

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = local.atZone(zone).toInstant();
~~~

The snippet above requires importing **java.time.\***. **atZone(zone)** resolves the time zone rules to create a ZonedDateTime; **toInstant()** then converts it into an absolute point in time.

There is no **local.toInstant()** method without an offset. Do not automatically use **ZoneId.systemDefault()** if the business domain already knows the store's or user's zone: the JVM's default timezone can vary between developer machines, CI, and production.

### Runnable Program: Same LocalDateTime, Two Different Instants

Create the file **CombineWithZoneDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class CombineWithZoneDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 1, 1);
        LocalTime time = LocalTime.of(0, 30);
        LocalDateTime local = day.atTime(time);

        Instant utc = local.atZone(ZoneOffset.UTC).toInstant();
        Instant hcm = local.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh")
        ).toInstant();

        System.out.println("local=" + local);
        System.out.println("utc=" + utc);
        System.out.println("hcm=" + hcm);
        System.out.println("equal=" + utc.equals(hcm));
    }
}
~~~

Run:

~~~bash
javac CombineWithZoneDemo.java
java CombineWithZoneDemo
~~~

Stdout:

~~~text
local=2026-01-01T00:30
utc=2026-01-01T00:30:00Z
hcm=2025-12-31T17:30:00Z
equal=false
~~~

**LocalDateTime** holds the intended date/time; **ZonedDateTime** attaches a zone and a valid offset; **Instant** records an absolute point in time. Choose the right type depending on whether the business logic needs to store, compute, or display.

## 7. DST: Being Combinable Does Not Mean the Time Exists in a Zone

In places with **Daylight Saving Time (DST)**:

- **Gap**: the clock jumps forward, so some local times do not exist.
- **Overlap**: the clock falls back, so one local time corresponds to two offsets.
- **Normal**: there is only one valid offset.

Because **LocalDateTime** has no ZoneId, it can still create a value inside a gap. For instance, **2026-03-08T02:30** in **America/New_York** is a non-existent time.

Create the file **DstCombineDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public class DstCombineDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 3, 8);
        LocalTime time = LocalTime.of(2, 30);
        LocalDateTime local = day.atTime(time);

        ZoneId zone = ZoneId.of("America/New_York");
        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        System.out.println("requested=" + local);
        System.out.println("validOffsets=" + valid);
        System.out.println("resolved=" + local.atZone(zone));
    }
}
~~~

Run:

~~~bash
javac DstCombineDemo.java
java DstCombineDemo
~~~

Stdout according to 2026 New York time zone data:

~~~text
requested=2026-03-08T02:30
validOffsets=[]
resolved=2026-03-08T03:30-04:00[America/New_York]
~~~

**atZone** has a default policy: for a gap, it usually pushes the time forward into the next valid interval; for an overlap, it picks one offset according to the API rules. If the business logic must **reject non-existent times**, or **ask the user to choose an offset** during an overlap, you must check **getValidOffsets** and apply custom rules rather than relying solely on atZone.

DST rules depend on IANA time zone data and can change according to local laws.

## 8. Adding Hours Across Midnight: Combine First, Calculate Later

**LocalTime** only exists within a single day, so:

~~~java
LocalTime.of(23, 30).plusMinutes(90); // 01:00
~~~

The result does not know that the date has changed. When you have a start date:

~~~java
LocalDate day = LocalDate.of(2026, 12, 31);
LocalTime time = LocalTime.of(23, 30);

LocalDateTime begin = day.atTime(time);
LocalDateTime end = begin.plusMinutes(90);
// end = 2027-01-01T01:00
~~~

Create the file **CrossMidnightDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

public class CrossMidnightDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 12, 31);
        LocalTime time = LocalTime.of(23, 30);

        LocalDateTime begin = day.atTime(time);
        LocalDateTime end = begin.plusMinutes(90);

        System.out.println("begin=" + begin);
        System.out.println("end=" + end);
        System.out.println("timeOnly=" + time.plusMinutes(90));
        System.out.println("elapsed=" +
                Duration.between(begin, end).toMinutes());
    }
}
~~~

Run:

~~~bash
javac CrossMidnightDemo.java
java CrossMidnightDemo
~~~

Stdout:

~~~text
begin=2026-12-31T23:30
end=2027-01-01T01:00
timeOnly=01:00
elapsed=90
~~~

Note that **Duration.between** on two LocalDateTime instances does not reflect DST offset changes. If the question is "how many **actual** minutes elapsed in this zone?", you must resolve both points into Instants using the ZoneId/offset and then measure Duration on those Instants.

## 9. Parsing from Forms and Formatting for Display

An illustrative request:

~~~json
{
  "date": "2026-10-24",
  "time": "09:30",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

Parse date and time separately:

~~~java
LocalDate date = LocalDate.parse("2026-10-24");
LocalTime time = LocalTime.parse("09:30");
LocalDateTime combined = date.atTime(time);
~~~

**LocalDate.parse** and **LocalTime.parse** handle their respective ISO formats by default. If an API receives the string **24/10/2026 09:30**, you must provide a DateTimeFormatter:

~~~java
DateTimeFormatter f =
        DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");
LocalDateTime parsed =
        LocalDateTime.parse("24/10/2026 09:30", f);
~~~

The two snippets above are **illustrative** and require imports from **java.time** and **java.time.format**.

### Complete Program

Create the file **ParseAndCombineDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

public class ParseAndCombineDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.parse("2026-10-24");
        LocalTime time = LocalTime.parse("09:30");
        LocalDateTime combined = day.atTime(time);

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm");

        System.out.println("combined=" + combined);
        System.out.println("formatted=" +
                combined.format(formatter));
        System.out.println("parsed=" +
                LocalDateTime.parse("24/10/2026 09:30", formatter));
    }
}
~~~

Run:

~~~bash
javac ParseAndCombineDemo.java
java ParseAndCombineDemo
~~~

Stdout:

~~~text
combined=2026-10-24T09:30
formatted=24/10/2026 09:30
parsed=2026-10-24T09:30
~~~

If the form only records **HH:mm**, it must be established by contract that seconds/nanos are set to 0. If the data needs to retain sub-second precision, storage and display must preserve all components.

## 10. Validation and Edge Cases

- **LocalDate.of(2026,2,30)** throws **DateTimeException** because the date does not exist.
- **LocalTime.of(24,0)** or **LocalTime.of(25,0)** throws **DateTimeException** because the hour is out of range.
- **LocalDate.parse("24/10/2026")** with the default ISO parser throws **DateTimeParseException** due to an invalid format.
- **date.atTime(null)** is invalid; missing data and null checks must be handled.
- Being able to combine into a LocalDateTime **does not prove** that the time is valid under booking policies or under a ZoneId.

If the UI accepts **24:00** to mean "end of day", it must not be passed directly into LocalTime. The application contract must normalize it to **00:00 of the next day**; simply changing it to 00:00 without incrementing the date will lose information.

Separate validation into four levels:

1. **Syntax**: does the string match the expected format?
2. **Calendar and clock**: are the date and time valid?
3. **Business rules**: holidays, shifts, opening hours, and booking limits?
4. **Time zone**: is there a DST gap/overlap in the ZoneId?

Do not swallow all exceptions and assign a default date/time; doing so can create an incorrect appointment that appears valid.

## 11. API Design and Storage

An actual appointment can be represented by the following fields:

~~~text
date       = 2026-10-24
time       = 09:30
zoneId     = Asia/Ho_Chi_Minh
local      = 2026-10-24T09:30
instant    = 2026-10-24T02:30:00Z
~~~

**date/time** hold the user's selection, **local** is the combined result, **zoneId** identifies the zone, and **instant** is the absolute point in time after applying zone rules. It is not necessary to store all four fields in every application, but you must define the **source of truth** and the conversion policy.

Example utility class:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;

public class BookingTime {
    public static Instant toInstant(
            LocalDate date, LocalTime time, ZoneId zone) {
        LocalDateTime local = date.atTime(time);
        return local.atZone(zone).toInstant();
    }
}
~~~

This is a compilable class **without a main method**. It illustrates how to combine and convert using atZone's default policy. In production, check for DST before converting if automatic gap/overlap adjustment is not permitted.

For timestamps of events that have already occurred, **Instant** is typically stored. For a future appointment meaning "09:30 in zone X", keep the intended **local date–time and ZoneId** according to policy so that time zone rule updates can be handled.

## 12. Quick Reference Table

| Need | API | Return Type |
|---|---|---|
| Combine two objects | **date.atTime(time)** | LocalDateTime |
| Combine via factory | **LocalDateTime.of(date,time)** | LocalDateTime |
| Create from fields | **LocalDateTime.of(2026,10,24,9,30)** | LocalDateTime |
| Attach time to date | **date.atTime(9,30)** | LocalDateTime |
| Get zoneless 00:00 | **date.atStartOfDay()** | LocalDateTime |
| Extract date | **local.toLocalDate()** | LocalDate |
| Extract time | **local.toLocalTime()** | LocalTime |
| Attach zone | **local.atZone(zone)** | ZonedDateTime |
| Determine UTC | **local.atZone(zone).toInstant()** | Instant |

**Do not get "now" by combining LocalDate.now() and LocalTime.now() in two separate calls**. They can occur on opposite sides of midnight. For the current time, use **LocalDateTime.now(clock)** or take a single Instant and convert it to a ZoneId:

~~~java
Instant sampled = Instant.now(clock);
LocalDateTime localNow =
        sampled.atZone(zone).toLocalDateTime();
~~~

This is an illustrative snippet with **clock** and **zone** already provided. The resulting date and time then come from a single observed instant.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking combining creates an Instant | Missing ZoneId/offset | Attach a zone when an absolute point in time is needed |
| Using systemDefault() for all customers | Deploying to another region shifts times | Explicit business ZoneId |
| Adding LocalTime across midnight then combining with the old date | Loses the new date | Combine into LocalDateTime before adding |
| Assuming atStartOfDay() returns ZonedDateTime | Has no zone | Choose the atStartOfDay(zone) overload |
| Not handling DST | Gap/overlap is resolved implicitly | getValidOffsets and an explicit policy |
| Comparing with **==** | Reference comparison | Use equals/isBefore/isAfter |
| Form truncating seconds/nanos without confirmation | Loss of precision | Define a format/storage contract |
| Storing LocalDateTime as an audit timestamp | Contains no offset/ZoneId | Use Instant |
| Combining two separate now() calls | May differ by a day at midnight | Take one Instant or now(clock) |
| Passing 24:00 into LocalTime | Exception | 00:00 of the next day if the contract allows |

## 14. Checklist and Self-Check Questions

Before shipping to production: have you defined the semantics of the date/time, parsing format, precision, midnight rollover handling, the event's ZoneId, DST gap/overlap handling, data storage strategy, and tests at day/year boundaries?

**1. Do date.atTime(time) and LocalDateTime.of(date,time) produce the same value?**  
Yes, given the same valid values.

**2. Does combining 24/10/2026 with 09:30 know the Vietnam timezone?**  
No. The result is **2026-10-24T09:30**, lacking a ZoneId.

**3. If LocalTime has 09:30:15.123, does atTime preserve the nano part?**  
Yes. It preserves all time components.

**4. Starting at 31/12/2026 23:30, what is adding 90 minutes on LocalDateTime?**  
**2027-01-01T01:00**.

**5. Can New York 08/03/2026 02:30 be created as a LocalDateTime?**  
Yes, but it is a non-existent time in the New York zone during a DST gap.

**6. How do you convert LocalDateTime to Instant?**  
A valid ZoneId or offset is required, for example **local.atZone(zone).toInstant()**.

**7. Why not combine LocalDate.now() and LocalTime.now() when you need the same "now"?**  
Two separate reads can cross a day boundary; take a single observed instant from Clock and convert it to the desired form.

**Remember:** The two APIs **date.atTime(time)** and **LocalDateTime.of(date,time)** combine date and time without losing any components, but **do not create a time zone**. Use LocalDateTime to preserve the date in calculations; add a ZoneId/offset to determine an Instant when the business logic requires it.