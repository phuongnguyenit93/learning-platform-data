# LocalTime in Java: Representing Time of Day Without Date or Time Zone

## 1. What is LocalTime?

`java.time.LocalTime` is a data type in the **Java Date and Time API** (`java.base` module), used to represent **wall-clock time within a day in the ISO calendar**, consisting of hour, minute, second, and nanosecond. This is a **local/wall-clock time** value: it only tells "what time the clock shows", without specifying **which date**, **where**, or **what absolute point in time it is on the UTC timeline**.

For example, `LocalTime.of(9, 30)` means **09:30**, which is useful for class start times, store opening hours, or daily reminders. You cannot infer from `09:30` that the moment is `2026-10-24T02:30:00Z`, because deriving an `Instant` requires at least **a valid date and time zone/offset**. The same 09:30 in Ho Chi Minh City, Tokyo, and New York usually corresponds to different UTC instants.

Characteristics of `LocalTime`:

- **No date:** contains no year, month, day, or day of week; it does not know whether 09:30 belongs to yesterday, today, or tomorrow.
- **No time zone or UTC offset:** contains no `ZoneId`, `ZoneOffset`, Daylight Saving Time (DST) rules, or UTC information.
- **Nanosecond precision:** up to 9 decimal digits of a second; contains no leap-day or leap-second information.
- **Immutable, thread-safe:** every operation returns a new value; the original object is never modified and can be safely shared across multiple threads.
- **Value-based:** compare values using `equals` or `compareTo`; do not rely on identity (`==`), and do not use `synchronized` on an instance as a stable identity object.
- **Valid time range:** from `00:00:00.000000000` to `23:59:59.999999999`; `24:00` is not a valid `LocalTime`. Seconds range from 0 to 59; `23:59:60` is not accepted.

### Conceptual Model

| Value | Java type | Has date? | Has time zone? | An absolute instant? |
| --- | --- | --- | --- | --- |
| `09:30` | `LocalTime` | No | No | No |
| `2026-10-24` | `LocalDate` | Yes | No | No |
| `2026-10-24T09:30` | `LocalDateTime` | Yes | No | Not necessarily |
| `2026-10-24T09:30+07:00` | `OffsetDateTime` | Yes | Offset `+07:00` | Yes |
| `2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | Yes | Zone + offset | Yes |
| `2026-10-24T02:30:00Z` | `Instant` | UTC timestamp | Not tied to a local zone | Yes |

`LocalTime` is **not** a timestamp type, cannot replace `Instant` for recording event timestamps, and is insufficient for determining cross-country appointments.

## 2. When to Use LocalTime?

Use `LocalTime` when the business domain cares about **wall-clock time**, separated from a specific date:

1. **Opening/closing hours:** a supermarket opens at 08:00 and closes at 22:00 every day.
2. **Timetables/schedules:** a class starts at 09:30 every Monday; pair with `DayOfWeek` or a recurrence schedule for the day-of-week rule.
3. **Reminder settings:** send a notification at 07:15 in the user's time zone. Store `LocalTime` together with **`ZoneId`** or the user's zone setting; the time alone is not enough to determine the actual execution time.
4. **Transaction cut-off time:** process orders before 17:00 business time; `LocalDate` and a zone are needed when calculating the actual deadline.
5. **Appointment time slot within a day:** a user selects `14:45`; when confirming the actual slot, a date and zone must be attached.

**Do not use `LocalTime` alone** for logs, `createdAt`/`updatedAt`, real-time timeouts, absolute ETAs, global meeting records, or comparing events across zones. Those cases typically require `Instant`, `Duration`, `OffsetDateTime`, or `ZonedDateTime`.

### Quick Type-Selection Questions

- Only asking "what time of day?" → `LocalTime`.
- Asking "what time on **date** X?" → `LocalDateTime`; still has no time zone.
- Asking "what time on date X **in zone** Y?" → `ZonedDateTime`; account for DST on input.
- Asking "**when exactly** did the event occur?" → `Instant`.
- Asking "how much time has elapsed?" → `Duration` between absolute instants when true elapsed time is needed.

## 3. Creating LocalTime

### 3.1. Factory Methods

```java
import java.time.LocalTime;

LocalTime midnight = LocalTime.MIDNIGHT;        // 00:00
LocalTime noon = LocalTime.NOON;                // 12:00
LocalTime min = LocalTime.MIN;                  // 00:00
LocalTime max = LocalTime.MAX;                  // 23:59:59.999999999

LocalTime morning = LocalTime.of(9, 30);       // 09:30
LocalTime precise = LocalTime.of(9, 30, 15);   // 09:30:15
LocalTime nanos = LocalTime.of(9, 30, 15, 123_456_789);
LocalTime fromSecond = LocalTime.ofSecondOfDay(34_200); // 09:30
LocalTime fromNano = LocalTime.ofNanoOfDay(34_200_000_000_000L);
```

*These are lines used inside a class/method, not a standalone runnable program.*

- `of(hour, minute)`: hour 0–23, minute 0–59; overloads exist to add seconds and nanoseconds.
- `ofSecondOfDay(long)`: number of seconds from the start of the day, from 0 to 86,399.
- `ofNanoOfDay(long)`: number of nanoseconds from the start of the day, from 0 to 86,399,999,999,999.
- `MIN` and `MIDNIGHT` have the same value 00:00; `MAX` is the last nanosecond of the day, not 24:00.

If you pass `LocalTime.of(24, 0)`, `LocalTime.of(10, 60)`, `ofSecondOfDay(86_400)`, or out-of-range components, Java throws `DateTimeException` (or a subclass depending on the call). This checks for a **valid time**, not whether that time exists in a specific time zone.

### 3.2. Parsing from Text

```java
import java.time.LocalTime;

LocalTime a = LocalTime.parse("09:30");                 // 09:30
LocalTime b = LocalTime.parse("09:30:15");              // 09:30:15
LocalTime c = LocalTime.parse("09:30:15.123456789");    // exact 9 nanosecond digits
```

`LocalTime.parse(text)` uses `DateTimeFormatter.ISO_LOCAL_TIME`. If the input is `9:30 AM` or `09h30`, a custom formatter is needed; do not assume user-supplied formats can always be parsed by default. Invalid values such as `"25:00"` or `"09:99"` result in `DateTimeParseException`.

### 3.3. Getting the Current Time

```java
import java.time.*;

LocalTime machineLocal = LocalTime.now(); // based on the machine's default time zone and current instant
LocalTime inTokyo = LocalTime.now(ZoneId.of("Asia/Tokyo"));

Clock fixed = Clock.fixed(
    Instant.parse("2026-01-01T12:00:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh"));
LocalTime stable = LocalTime.now(fixed); // 19:00
```

`now()` is convenient for interactive applications, but its result changes with the machine's clock and configured time zone. When building testable business services, prefer **injecting `Clock`** and calling `LocalTime.now(clock)`. The `ZoneId` parameter in `now(zone)` only means **convert the current instant to local clock time in the selected zone**; it does not make the resulting `LocalTime` object retain any zone information.

`LocalTime.ofInstant(instant, zone)` (Java 9+) also extracts the **local time** of an `Instant` in a specific `ZoneId`. The key point is that both a real instant and a zone are required. You can use `instant.atZone(zone).toLocalTime()` with the same meaning.

## 4. Reading Individual Fields and Converting to Numeric Units

| Method | Meaning | For `09:30:15.123456789` |
| --- | --- | --- |
| `getHour()` | Hour of day, 0–23 | `9` |
| `getMinute()` | Minute of hour, 0–59 | `30` |
| `getSecond()` | Second of minute, 0–59 | `15` |
| `getNano()` | Nanosecond of second, 0–999,999,999 | `123456789` |
| `toSecondOfDay()` | Total seconds since 00:00 | `34215` |
| `toNanoOfDay()` | Total nanoseconds since 00:00 | `34215123456789` |
| `get(ChronoField.HOUR_OF_DAY)` | Read field via `TemporalField` | `9` |

For example, `LocalTime.of(9,30).toSecondOfDay()` equals `9×3600 + 30×60 = 34200`. For `toNanoOfDay()`, the return type is `long` because the value can exceed the `int` limit.

`LocalTime` implements `Temporal` and `TemporalAdjuster`. Therefore, you can use `get(ChronoField...)`, `isSupported(...)`, `with(...)`, and `plus(...)` to operate by field/unit. However, it has no date fields: reading `ChronoField.DAY_OF_MONTH` from `LocalTime` is semantically invalid and throws `UnsupportedTemporalTypeException`.

## 5. Adding, Subtracting, and Modifying Time Components

`LocalTime` is immutable: methods return a new value. For example:

```java
import java.time.LocalTime;

LocalTime start = LocalTime.of(9, 30);
LocalTime after = start.plusHours(2).plusMinutes(15); // 11:45
LocalTime before = start.minusMinutes(45);           // 08:45
LocalTime roundedHour = start.withMinute(0);         // 09:00
LocalTime shifted = start.withHour(13);               // 13:30
// start is still 09:30
```

Important method groups:

- `plusHours`, `plusMinutes`, `plusSeconds`, `plusNanos`, and the `minus...` variants.
- `withHour`, `withMinute`, `withSecond`, `withNano` to replace one field while keeping the rest unchanged.
- `plus(long, TemporalUnit)` or `with(TemporalField, long)` when code uses the general `java.time.temporal` API.
- `truncatedTo(ChronoUnit.MINUTES)` to zero out seconds and nanoseconds; `truncatedTo(ChronoUnit.HOURS)` to zero out minutes/seconds/nanoseconds. This is **truncating fractional parts**, not rounding to the nearest unit.

### 5.1. Important: 24-Hour Wrap-Around Arithmetic

```java
LocalTime night = LocalTime.of(23, 30);
LocalTime later = night.plusHours(2); // 01:30
LocalTime earlier = LocalTime.MIDNIGHT.minusMinutes(1); // 23:59
```

This is the **clock time** after adding/subtracting modulo 24 hours; there is no date to indicate "crossed into the next day". `night.plusHours(24)` returns 23:30 again, and `plusHours(48)` is still 23:30. If the problem requires knowing whether an event is 2 days apart or whether the date has changed, you must use `LocalDate`/`LocalDateTime` or the corresponding `Instant`.

You cannot rely on the result of `LocalTime.plusHours(...)` to determine how many days have elapsed.

### 5.2. Calculating the Difference Between Two LocalTime Values

```java
import java.time.*;
import java.time.temporal.ChronoUnit;

LocalTime start = LocalTime.of(9, 30);
LocalTime end = LocalTime.of(17, 45);

long minutes = ChronoUnit.MINUTES.between(start, end); // 495
Duration duration = Duration.between(start, end);       // PT8H15M
```

`Duration.between(LocalTime, LocalTime)` is the difference **between two times on the same local time axis**. It does not automatically assume "next day":

```java
LocalTime late = LocalTime.of(23, 30);
LocalTime early = LocalTime.of(0, 30);
Duration wrongForOvernight = Duration.between(late, early); // PT-23H
```

If business rules state that a shift starts at 23:30 and ends at 00:30 **the next day**, combine with dates:

```java
LocalDate d = LocalDate.of(2026, 10, 24);
LocalDateTime begin = d.atTime(23, 30);
LocalDateTime finish = d.plusDays(1).atTime(0, 30);

Duration actualByLocalCalendar = Duration.between(begin, finish); // PT1H
```

The last example yields one hour because the dates are specified, yet **`LocalDateTime` still does not handle time zones/DST**. If calculating actual duration in a region with Daylight Saving Time transitions, determine the `ZoneId`, resolve the offset for each instant, and use `Duration.between(startZoned.toInstant(), endZoned.toInstant())`. Two `Instant` values give an unambiguous elapsed time.

**Note:** if calculating "time until the next occurrence of closing time within at most 24 hours", modular arithmetic can be used for a well-defined recurring schedule. However, modulo discards day-count information, and the span from 00:00 to 00:00 can mean **0 hours or 24 hours** depending on requirements; define the business policy upfront.

## 6. Comparison and Equality

Typical usage:

- `a.equals(b)`: equal in hour/minute/second/nanosecond values.
- `a.isBefore(b)`: clock time comes earlier within the same one-day cycle.
- `a.isAfter(b)`: clock time comes later within the same cycle.
- `a.compareTo(b)`: negative/0/positive for sorting by time of day.

```java
LocalTime opening = LocalTime.of(9, 30);
LocalTime closing = LocalTime.of(17, 45);

boolean earlier = opening.isBefore(closing);          // true
boolean identical = opening.equals(LocalTime.parse("09:30")); // true
```

Do not infer real-world event order by comparing `LocalTime` values across different dates or different zones. For example, 23:45 today can be **earlier** than 00:15 tomorrow in absolute time, yet `LocalTime.of(23,45).isAfter(LocalTime.of(0,15))` still returns `true` because it only compares "time of day".

`LocalTime` objects are value-based, so **do not rely on `==`** to check value equality, even though some values might be reused by the JVM. Prefer `equals`.

## 7. Controlled Formatting and Parsing

### 7.1. ISO Standard

`LocalTime.toString()` produces an ISO representation, automatically choosing the minimal precision needed to preserve the value, for example:

| Value | Output string |
| --- | --- |
| `LocalTime.of(9,30)` | `09:30` |
| `LocalTime.of(9,30,15)` | `09:30:15` |
| `LocalTime.of(9,30,15,123_000_000)` | `09:30:15.123` |
| `LocalTime.of(9,30,15,123_456_789)` | `09:30:15.123456789` |

Although Java supports nanosecond precision, hardware/OS clocks do not necessarily provide equivalent observable resolution. Do not use nanoseconds just because the type supports them; choose precision based on actual data and business requirements.

### 7.2. HH:mm and 12-Hour Patterns

```java
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter hhmm = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
String text = LocalTime.of(9, 30).format(hhmm); // "09:30"
LocalTime parsed = LocalTime.parse(text, hhmm); // 09:30
```

Key pattern symbols to know:

| Pattern | Meaning | Example |
| --- | --- | --- |
| `HH` | Hour 00–23 | `09`, `17` |
| `H` | Hour 0–23, minimum one digit | `9`, `17` |
| `mm` | Minute 00–59 | `03`, `30` |
| `ss` | Second 00–59 | `05`, `15` |
| `S` to `SSSSSSSSS` | Fraction of second | `SSS` → 3 digits |
| `hh` | Hour 01–12 | `09`, `11` |
| `a` | AM/PM | `AM`/`PM` depending on locale |

`MM` is **month**, not minute. With `hh:mm a`, pass `Locale.ENGLISH` if the input string contains English `AM`/`PM`, to avoid depending on the machine's locale. When a 12-hour UI is not required, `HH:mm` is generally easier to use and less error-prone.

### 7.3. Invalid Parsing and Data Boundaries

```java
import java.time.LocalTime;
import java.time.format.DateTimeParseException;

try {
    LocalTime input = LocalTime.parse("25:00");
} catch (DateTimeParseException ex) {
    System.out.println("Gio khong hop le");
}
```

The string `25:00` is outside the 0–23 hour range, so the example prints `Gio khong hop le`. Catch `DateTimeParseException` at input boundaries to return a user-friendly error. In APIs, you can choose to store a normalized string such as `HH:mm` or ISO with seconds, depending on the required precision.

**Precision note when formatting:** `LocalTime.of(9,30,15).format(DateTimeFormatter.ofPattern("HH:mm"))` produces `09:30` and **loses second information**; if parsed back into `LocalTime`, `:15` cannot be recovered. Choose a format that does not unintentionally drop precision when used for storage or synchronization.

## 8. LocalTime Has No Date or Time Zone: Practical Consequences

### 8.1. Cannot Directly Convert LocalTime to Instant

A standalone time like 09:30 **does not have enough data to produce a UTC timestamp**. You need at least a date and a zone/offset, plus a policy if that date has DST.

```java
import java.time.*;

LocalTime appointmentTime = LocalTime.of(9, 30);
LocalDate appointmentDate = LocalDate.of(2026, 10, 24);
ZoneId city = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDateTime wallTime = appointmentDate.atTime(appointmentTime);
ZonedDateTime zoned = wallTime.atZone(city);
Instant instant = zoned.toInstant();
```

In this example, `instant` is `2026-10-24T02:30:00Z` because Ho Chi Minh City uses offset `+07:00` on the chosen date. **Do not** mistakenly pair `LocalTime` with `ZoneOffset.UTC` when the actual business meaning is local time in Ho Chi Minh City.

### 8.2. DST Can Make the Same Local Time Invalid or Ambiguous

In `America/New_York` in 2026:

- **2026-03-08 at 02:30:** the local time does not exist because the clock jumps from 02:00 to 03:00. `getValidOffsets(local)` returns an empty list.
- **2026-11-01 at 01:30:** the time occurs twice, once at offset `-04:00` and once at `-05:00`. `getValidOffsets(local)` returns two options.
- **A normal time:** returns one offset.

Example handling user-selected time:

```java
import java.time.*;
import java.time.zone.ZoneRules;
import java.util.List;

LocalDateTime local = LocalDateTime.of(
        LocalDate.of(2026, 11, 1),
        LocalTime.of(1, 30));
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();
List<ZoneOffset> options = rules.getValidOffsets(local);

if (options.isEmpty()) {
    // Time does not exist; reject or ask the user to choose another time.
} else if (options.size() == 2) {
    // Time occurs twice; ask the user to choose the offset/occurrence.
} else {
    // Normal time, exactly one valid offset.
}
```

This is **an illustration of handling inside a method**. Once the user has selected a valid offset, you can use `ZonedDateTime.ofStrict(local, selectedOffset, zone)` to construct an exact instant.

`LocalTime` itself **has no knowledge of DST** because it has no date or zone. It can still represent `02:30`; the question "does 02:30 exist on that day in New York?" must be answered using **`LocalDateTime + ZoneId + ZoneRules`**.

### 8.3. "09:00 Every Day" Differs from "Every 24 Hours"

If a system needs to send a reminder at **09:00 every day in New York**, repeating by local time must keep `LocalTime.of(9,0)` + `ZoneId`, find the **next date**, and then resolve DST. Advancing an `Instant` by `Duration.ofHours(24)` can shift the local time on DST transition days (e.g., 09:00 becomes 10:00 or 08:00 depending on the zone/rule). Choose the data model based on the requirement: **local wall-clock time** or **true elapsed time interval**.

## 9. Complete Runnable Java 17+ Example

Create a file named **`LocalTimeDemo.java`**. This program demonstrates: creating and reading `LocalTime`, converting to seconds of day, adding hours, comparing, formatting, truncating seconds, calculating a same-day duration, resolving an overnight shift with `LocalDateTime`, and reading time from `Clock.fixed` for deterministic results.

```java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.Locale;

public class LocalTimeDemo {
    public static void main(String[] args) {
        LocalTime opening = LocalTime.of(9, 30);
        LocalTime closing = LocalTime.of(17, 45);
        LocalTime precise = LocalTime.parse("09:30:15.123456789");

        DateTimeFormatter hhmm = DateTimeFormatter.ofPattern("HH:mm", Locale.ROOT);
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T12:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("Mo cua: " + opening.format(hhmm));
        System.out.println("Do chinh xac: " + precise);
        System.out.println("Gio: " + opening.getHour());
        System.out.println("Giay tu dau ngay: " + opening.toSecondOfDay());
        System.out.println("Dong cua sau mo cua: " + closing.isAfter(opening));
        System.out.println("Phut mo cua: " + ChronoUnit.MINUTES.between(opening, closing));
        System.out.println("Cong 17 gio: " + opening.plusHours(17));
        System.out.println("Lam tron phut: " + precise.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("Qua nua dem (chi gio): " + LocalTime.of(23, 30).plusHours(2));
        System.out.println("Duration nguoc: " +
                Duration.between(LocalTime.of(23, 30), LocalTime.of(0, 30)).toHours());
        LocalDate today = LocalDate.of(2026, 10, 24);
        LocalDateTime start = today.atTime(23, 30);
        LocalDateTime end = today.plusDays(1).atTime(0, 30);
        System.out.println("Duration qua ngay: " + Duration.between(start, end).toHours());
        System.out.println("Clock co dinh (HCM): " + LocalTime.now(fixed));
    }
}
```

Run in the directory containing the file using JDK 17+:

```bash
javac -encoding UTF-8 LocalTimeDemo.java
java LocalTimeDemo
```

The stdout output is deterministic based on the fixed data in the program:

```text
Mo cua: 09:30
Do chinh xac: 09:30:15.123456789
Gio: 9
Giay tu dau ngay: 34200
Dong cua sau mo cua: true
Phut mo cua: 495
Cong 17 gio: 02:30
Lam tron phut: 09:30
Qua nua dem (chi gio): 01:30
Duration nguoc: -23
Duration qua ngay: 1
Clock co dinh (HCM): 19:00
```

**Output breakdown:**

- `opening.format(hhmm)` produces `09:30`; `LocalTime.parse` preserves `.123456789` exactly.
- `09:30` equals `34200` seconds since 00:00; from `09:30` to `17:45` is `8h15m = 495` minutes.
- Adding `17` hours to `09:30` wraps past midnight and returns `02:30` without storing "next day".
- `truncatedTo(MINUTES)` drops the seconds/nanoseconds part and returns `09:30`; the printed label “Lam tron phut” is just a display label—the operation itself is **truncate**, not round.
- `Duration.between(23:30,00:30)` between two `LocalTime` instances returns `-23` hours because there is no date; when paired with Oct 24 and Oct 25, the difference is `1` hour in the local calendar.
- `Clock.fixed` fixes the UTC instant at 12:00 and zone to HCM; thus `LocalTime.now(fixed)` is always 19:00, independent of the machine's real clock.

## 10. Storage, APIs, and Testing

### 10.1. Storing in Databases and JSON

When the data genuinely represents daily opening hours or recurring daily times, an SQL **`TIME` column without time zone** is usually more appropriate than a timestamp. With JDBC supporting Java 8+ date-time mappings, you can pass `LocalTime` using `PreparedStatement.setObject(index, localTime)` or read via `ResultSet.getObject(column, LocalTime.class)`; **check your specific driver** because support and precision can vary.

In JSON, agree on an explicit format, for example:

```json
{
  "opensAt": "09:30",
  "closesAt": "22:00",
  "businessZone": "Asia/Ho_Chi_Minh"
}
```

The string `09:30` represents `LocalTime`. The `businessZone` field is **domain-specific metadata**, needed when turning opening hours into a date-specific event. Never append `Z` to `"09:30"`; `Z` denotes a UTC offset on appropriate datetime/time types, not a built-in component of `LocalTime`.

In JSON frameworks like Jackson, `LocalTime` serialization/deserialization depends on the Java Time module and mapper/format configuration; verify actual integration behavior rather than assuming all frameworks parse identically by default.

### 10.2. Decoupling the Clock from Business Logic

Code that depends on "now" should accept `Clock` via its constructor:

```java
import java.time.Clock;
import java.time.LocalTime;

final class OpeningHoursService {
    private final Clock clock;

    OpeningHoursService(Clock clock) {
        this.clock = clock;
    }

    boolean isOpen(LocalTime opens, LocalTime closes) {
        LocalTime now = LocalTime.now(clock);
        return !now.isBefore(opens) && now.isBefore(closes);
    }
}
```

This is **an illustrative class**, not a file with `main`. The `isOpen` method uses the half-open interval **[opens, closes)** and only works when `opens` is before `closes` on **the same calendar day in a single zone**. If opening hours span past midnight, a separate policy and algorithm are required; for example, adding a wrap-around comparison branch or combining `LocalDateTime`/`ZonedDateTime`. When the business time zone is configured, pass `Clock.system(businessZone)`; in tests, use `Clock.fixed(..., businessZone)`.

### 10.3. Essential Test Cases

| Case | Input | Expected |
| --- | --- | --- |
| Start of day | `00:00` | `LocalTime.MIDNIGHT` |
| End of day | `23:59:59.999999999` | `LocalTime.MAX` |
| Out-of-range hour | `24:00` | `DateTimeException` when using `of(24,0)` |
| Invalid minute | `09:60` | `DateTimeParseException` on ISO parse |
| Precision | `09:30:15.123456789` | Preserves all 9 nanosecond digits |
| Wrap-around arithmetic | `23:30` + 2 hours | `01:30` |
| Immutability | `09:30` + 1 hour | New value 10:30; original remains 09:30 |
| Same-day span | 09:30 → 17:45 | `495` minutes |
| Overnight span | 23:30 on Oct 24 → 00:30 on Oct 25 | `60` minutes when paired with dates |
| Testable current time | `Clock.fixed` in HCM | Value remains deterministic for the configured zone |
| DST gap/overlap | 02:30 on 2026-03-08 and 01:30 on 2026-11-01, New York | Can only be verified once date + `ZoneId` are present |

**Do not test using no-arg `LocalTime.now()`** if the test expects a fixed value. Also, comparing times around DST using `LocalTime` only compares wall-clock numbers, not true elapsed durations.

## 11. Common Pitfalls and Fixes

1. **Confusing `LocalTime` with `LocalDateTime`:** `LocalTime.of(9,30)` has no date information. When an appointment needs a date, combine with `LocalDate.atTime(time)`.
2. **Thinking `LocalTime` stores a time zone:** in reality, the time zone is only used when creating the time from `Clock`/`Instant`; the resulting instance does not store `ZoneId`.
3. **Storing `createdAt` as `LocalTime`:** the same `09:30` occurs every day; use `Instant` to identify event timestamps.
4. **Using `plusHours` to count elapsed days:** `LocalTime` wraps around every 24 hours; date or timestamp data is needed.
5. **Calculating overnight shifts with `Duration.between(LocalTime,LocalTime)`:** the result can be negative; attach start/end dates, and attach a zone/instant when true elapsed time is needed.
6. **Confusing `mm` with `MM`:** `mm` is minute, `MM` is month. Use pattern `HH:mm` for a 24-hour clock.
7. **Using `HH:mm` to serialize times with seconds/nanoseconds:** loses information; transmit an ISO format with sufficient precision or define the unit explicitly in the API contract.
8. **Using `==` to compare instances:** use `equals` or `isBefore`/`isAfter`.
9. **Calling a mutator-like method without using the return value:** `time.plusMinutes(5);` does not modify the original variable. Assign `time = time.plusMinutes(5);`.
10. **Forgetting DST when combining `LocalTime` with a date/zone:** `01:30` can occur twice, `02:30` might not exist; use `ZoneRules` and a business policy.
11. **Using a fixed dummy date to create an `Instant`:** if the meaning is recurring opening hours, attaching a dummy date can produce the wrong offset for the actual date; keep `LocalTime + ZoneId` and only resolve to an instant once the date is known.

## 12. Practice Exercises

### Exercise 1 — Reading and Creating Times

Create `LocalTime` values representing 06:05, 12:00, and 23:59:30.250000000. Print each value using `toString()` and inspect them with `getHour`/`getMinute`/`getNano`. Try creating `LocalTime.of(24,0)` and explain why an exception is thrown.

**Result hint:** `LocalTime.of(6,5).toString()` is `06:05`; `LocalTime.of(23,59,30,250_000_000).toString()` is `23:59:30.250`.

### Exercise 2 — Same-Day Opening Hours Window

A store opens at `08:15` and closes at `20:45`. Write a function to check whether a `LocalTime` falls within **[08:15,20:45)** and calculate the total open minutes. Test cases: `08:15` is open, `20:44` is open, `20:45` is closed.

**Difference answer:** `ChronoUnit.MINUTES.between(08:15,20:45)` = `750` minutes. This exercise does **not** handle times spanning across midnight.

### Exercise 3 — Overnight Shift

An employee starts at `22:30` on 2026-10-24 and finishes at `06:00` on 2026-10-25. Combine with the proper `LocalDateTime` dates and compute `Duration.between`; the duration is **7 hours 30 minutes** when considering local date-time alone. If the shift takes place in a DST zone on a transition day, convert to `ZonedDateTime`/`Instant` and compare true elapsed time.

### Exercise 4 — Zoned Appointment Time

Given `LocalTime.of(9,30)`, date `2026-10-24`, and `ZoneId.of("Asia/Ho_Chi_Minh")`, create a `ZonedDateTime` and convert it to `Instant`. Expect `2026-10-24T02:30:00Z`. Explain why `09:30` alone cannot yield this result.

### Exercise 5 — Machine-Independent Current Time

Write a service that accepts a `Clock` and retrieves `LocalTime.now(clock)`. Test with a fixed clock at `2026-01-01T12:00:00Z` in `Asia/Ho_Chi_Minh` and verify the result is **19:00**; repeating 100 times must yield the exact same result.

### Exercise 6 — Design Question

For three fields: "daily opening time 09:00", "event created at 09:00 yesterday", and "appointment at 09:00 on Oct 24 in Tokyo", choose the appropriate data types:

- Daily opening time: `LocalTime`, optionally paired with the facility's `ZoneId`.
- Event creation timestamp: `Instant` (or a datetime with an explicit offset).
- Appointment in Tokyo: `LocalDate` + `LocalTime` + `ZoneId` → `ZonedDateTime`/`Instant` after resolving zone rules.

## 13. Self-Assessment Checklist

- [ ] State that `LocalTime` represents **time of day**, without **date**, **`ZoneId`**, **`ZoneOffset`**, or `Instant`.
- [ ] Know how to create instances with `of`, `parse`, `ofSecondOfDay`, and understand the 00:00 to 23:59:59.999999999 range.
- [ ] Know how to read hour/minute/second/nanosecond and convert to seconds/nanoseconds since start of day.
- [ ] Use `plus`/`minus`/`with` and understand immutability and 24-hour wrap-around behavior.
- [ ] Compare two `LocalTime` values without inferring event order across different dates.
- [ ] Format/parse with `DateTimeFormatter` and handle invalid strings via `DateTimeParseException`.
- [ ] Know that a date and `ZoneId` are required to convert an appointment time into an `Instant`; recognize DST edge cases.
- [ ] Calculate overnight spans accurately using proper dates; use `Instant` when true elapsed time is needed.
- [ ] Write deterministic tests using `Clock.fixed` instead of the system clock.

## Official References (JDK 17)

- [`LocalTime` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [`LocalDateTime` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html)
- [`DateTimeFormatter` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [`Duration` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
- [`ZoneRules` — API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html)
