# When LocalDateTime Is Appropriate and When It Easily Loses Time Meaning

`LocalDateTime` in `java.time` represents a **calendar date and local wall-clock time**, for example `2024-03-01T09:00:00`. It contains year, month, day, hour, minute, second, and nanosecond, but **does not contain a time zone (`ZoneId`), a UTC offset (`ZoneOffset`), or an absolute point in time (`Instant`)**.

This is not a flaw in Java: it is an intentional data type. `LocalDateTime` is completely right when a requirement only refers to a **date and time on the calendar**, but it easily causes bugs if an application accidentally treats it as a timestamp sufficient to identify an event that occurred on the timeline.

**Decision question:** "Does this value represent a *date/time on a wall clock* or a *unique point in time worldwide*?" The two meanings require different data.

## 1. What Exactly Does LocalDateTime Contain?

Example:

```java
import java.time.LocalDateTime;

LocalDateTime appointment = LocalDateTime.of(2024, 3, 1, 9, 0);
System.out.println(appointment); // 2024-03-01T09:00
```

This is an illustrative snippet meant to be placed inside a Java method. The object above states "March 1, 2024, at 09:00", but **does not specify** whether that 09:00 is in Hanoi, New York, or somewhere else. From it, the exact UTC time **cannot** be derived.

Components:

| Field/Property | Does LocalDateTime have it? | Example |
| --- | --- | --- |
| Year–month–day | Yes | `2024-03-01` |
| Hour–minute–second–nanosecond | Yes | `09:00:00.000000000` |
| Region-based time zone (`ZoneId`) | No | Does not know `Asia/Ho_Chi_Minh` |
| Offset from UTC | No | Does not know `+07:00` |
| Absolute point in time | No | Cannot derive `Instant` |
| ISO calendar rules | Yes | Validates legal dates upon object creation |

Because it has no zone/offset, a standalone `LocalDateTime` also cannot tell whether the local clock fell into a skipped or repeated Daylight Saving Time (DST) interval.

## 2. Comparing Time Types to Choose the Right One

| Type | Contents | Use when |
| --- | --- | --- |
| `LocalDate` | Date only | Birthdays, invoice dates, holidays |
| `LocalTime` | Local time of day only | Daily opening hours |
| `LocalDateTime` | Date + time, without zone/offset | Local calendar appointment time before a zone is attached; pure "date and time" data |
| `OffsetDateTime` | Date + time + offset such as `+07:00` | Timestamps with a specific offset in protocols or data contracts |
| `ZonedDateTime` | Date + time + `ZoneId` and resolved offset | Zone-based schedules with DST/historical rules, when representing time in a specific zone |
| `Instant` | Absolute timestamp | Events that occurred, audits, `createdAt`, comparing instants |
| `Duration` | Length in seconds/nanoseconds | Measuring elapsed duration between instants |

**`OffsetDateTime`** has an offset sufficient to determine the `Instant` of the value in question, but does not retain time-zone rules for future recurrences. **`ZonedDateTime`** binds an IANA zone such as `Europe/Paris` or `America/New_York` and uses zone rules to represent local time. If the requirement is "09:00 every Monday in Paris", store the recurrence rule **and `ZoneId`**, not just an `OffsetDateTime` from the first week.

## 3. When Is LocalDateTime Truly Appropriate?

### 3.1. Local Calendar Date and Time Is the Data to Store

For example, a user enters "01/03/2024 at 09:00", but at the time of entry, the business logic has not yet determined the location/time zone for the appointment. `LocalDateTime` accurately represents the information that **is already known**:

```java
LocalDateTime requestedLocalTime = LocalDateTime.of(2024, 3, 1, 9, 0);
// Cannot compute UTC timestamp without knowing the zone or offset.
```

This illustrative snippet requires importing `java.time.LocalDateTime`. You can keep this value in the UI layer or in an "appointment pending branch selection" state. **Before creating a unique booking instant**, the system must collect the zone/offset and handle cases where the local time is ambiguous or nonexistent.

### 3.2. Editing Calendar Components Without Needing a UTC Instant Right Away

`LocalDateTime` is convenient for operations like "move the meeting on the calendar to the same time the next day", building a date/time from a form, or manipulating components:

```java
LocalDateTime original = LocalDateTime.of(2024, 3, 1, 9, 0);
LocalDateTime nextWeek = original.plusWeeks(1); // 2024-03-08T09:00
LocalDateTime newTime = original.withHour(14);  // 2024-03-01T14:00
```

This is an **operation on local date/time fields**. It does not yet determine the actual elapsed difference between two instants on the UTC timeline. If the addition crosses a DST transition, you must apply the zone afterward and handle zone policies. `plusDays(1)` on a local time is not guaranteed to equal 24 actual hours in every time zone.

### 3.3. Exchanging a Value Whose Contract Explicitly States It Is "Local Wall Time"

An API might have two fields:

```json
{
  "appointmentLocal": "2024-03-01T09:00:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

Here `appointmentLocal` fits `LocalDateTime`, but **the contract as a whole** provides enough zone context to determine the appointment's meaning. Field names should clearly indicate "local". If the business logic requires an `Instant` to place an order or send a reminder, the server side must still resolve those two fields and handle time-zone rules.

If the data truly only needs a birth date, use `LocalDate`; if it only needs daily opening hours, use `LocalTime`. Do not use `LocalDateTime` out of habit when half of the data is unnecessary.

## 4. When Does LocalDateTime Lose Time Meaning?

### 4.1. Converting a Real Event to LocalDateTime and Dropping the Zone

Suppose the same event occurs at `2024-02-29T23:30:00Z`:

```java
import java.time.*;

Instant event = Instant.parse("2024-02-29T23:30:00Z");

LocalDateTime utcView =
        LocalDateTime.ofInstant(event, ZoneOffset.UTC);
LocalDateTime vietnamView =
        LocalDateTime.ofInstant(event, ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utcView);     // 2024-02-29T23:30
System.out.println(vietnamView); // 2024-03-01T06:30
```

**Two different `LocalDateTime` values represent the same original `Instant`**, provided you keep the zone context of each conversion. When storing `2024-03-01T06:30` alone and dropping `Asia/Ho_Chi_Minh`, you no longer know whether this is Vietnam time or somewhere else, and you cannot uniquely recover the original `Instant`.

Semantically incorrect example:

```java
// This is a LocalDateTime in UTC, not an Instant with UTC information!
LocalDateTime utcLookingValue = LocalDateTime.ofInstant(
        event, ZoneOffset.UTC);

// If another machine treats the same LocalDateTime as its own local time,
// the inferred instant may differ.
Instant mistaken = utcLookingValue
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
```

This snippet requires importing `java.time.*`. `mistaken` is no longer `event` because **the UTC time was mistakenly attached to the Vietnam time zone**. Use `Instant` end-to-end to store event timestamps, and only convert to `LocalDateTime` for display in a specific zone when needed.

### 4.2. Storing Events That "Have Occurred" Using a Zone-less Local Date-Time

Fields such as `createdAt`, `paidAt`, `sentAt`, `receivedAt`, `loginAt`, and `jobStartedAt` usually mean **an actual point in time**. If machine A runs in UTC and machine B runs in Vietnam time, two records calling `LocalDateTime.now()` can be seven hours apart even though they happened at the same instant.

Example:

```java
Instant createdAt = clock.instant(); // explicit time source
ZonedDateTime display = createdAt.atZone(userZone);
```

This snippet is inside a service where `clock` (`Clock`) and `userZone` (`ZoneId`) are injected from outside. Store values with `Instant` semantics; display or determine business dates using the appropriate zone. If the database/driver lacks direct `Instant` mapping, explicitly standardize on storing in UTC with the corresponding SQL type/adapter and read logic; SQL type names and conversion rules vary by DBMS.

### 4.3. Inferring Offset From the Server or Unconditionally Assigning UTC

`LocalDateTime.now()` reads the current time in the **JVM default time zone**. `LocalDateTime.now(ZoneId.of("UTC"))` creates a **local time corresponding to UTC**, but the resulting object still carries no zone information. Calling `localDateTime.toInstant(ZoneOffset.UTC)` is only valid if the input contract **genuinely guarantees** that the value is interpreted as UTC.

**Do not manually append the letter "Z"** to a `LocalDateTime` string to turn it into a UTC timestamp. "Z" asserts a zero offset and must be backed by the true meaning of the data, not string concatenation.

## 5. From LocalDateTime to a Real Instant: Context Is Required

To turn `2024-03-01T09:00` into an `Instant`, you must specify a **zone or offset**. For an appointment in Hanoi:

```java
LocalDateTime appointment = LocalDateTime.of(2024, 3, 1, 9, 0);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = appointment.atZone(zone);
Instant instant = zoned.toInstant();

System.out.println(zoned);
// 2024-03-01T09:00+07:00[Asia/Ho_Chi_Minh]
System.out.println(instant);
// 2024-03-01T02:00:00Z
```

This illustrative snippet requires importing `java.time.*`. `atZone(zone)` applies zone rules to the local date-time, producing a resolved `ZonedDateTime`. `toInstant()` extracts the corresponding absolute instant. For **a time that does not fall on a DST transition**, the zone rules uniquely determine the offset.

`LocalDateTime.toInstant(offset)` also exists, but you must **already have a valid offset** for that situation. `ZoneOffset.ofHours(7)` only describes `+07:00` and does not replace all historical/DST rules of an IANA zone. For appointments at a physical location where zone rules may change over time, it is usually preferable to store **`ZoneId`** alongside the local time intent.

## 6. DST: Local Time May Not Exist or May Have Two Interpretations

Every `LocalDateTime` has a valid year/month/day/time in the ISO calendar, but **that does not mean it is valid as a wall-clock time in every zone**. Some zones transition into and out of Daylight Saving Time (DST):

| State | Number of valid offsets | Meaning |
| --- | ---: | --- |
| Normal | 1 | `LocalDateTime` and zone resolve to a single `Instant` |
| *Gap* | 0 | Local time does not exist because the clock jumps forward |
| *Overlap* | 2 | A clock time occurs twice with two different offsets |

### 6.1. Gap: March 10, 2024 in New York

In `America/New_York`, clocks jump from 01:59:59 to 03:00:00 on this day. Therefore **02:30 does not exist in New York**, yet Java still allows creating the `LocalDateTime`:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);

int count = ny.getRules().getValidOffsets(gap).size(); // 0
ZonedDateTime adjusted = gap.atZone(ny);

System.out.println(adjusted);
// 2024-03-10T03:30-04:00[America/New_York]
```

`atZone` **automatically adjusts** a time in a gap forward by the length of the gap. That is the API's default rule, **not automatically the right policy for every business domain**. If a user's appointment requires exactly 02:30 and must not be silently shifted to 03:30, check `getValidOffsets(gap)` before accepting it.

### 6.2. Overlap: November 3, 2024 in New York

When clocks fall back, **01:30 occurs twice**:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);

System.out.println(ny.getRules().getValidOffsets(overlap));
// [-04:00, -05:00]

ZonedDateTime earlier = overlap.atZone(ny);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

System.out.println(earlier.toInstant()); // 2024-11-03T05:30:00Z
System.out.println(later.toInstant());   // 2024-11-03T06:30:00Z
```

Two `Instant` values **one hour apart** share the same `LocalDateTime` of `2024-11-03T01:30`. When encountering an overlap, `atZone` typically picks the **earlier** offset (usually the summer/DST offset). If this choice matters for billing, reservations, or operations, you must state the policy explicitly and store the resolved result without discarding the offset information.

You can use `ZoneRules.getValidOffsets(localDateTime)` to decide: 0 offsets → reject or adjust the gap; 1 offset → accept; 2 offsets → ask the user to choose an interpretation or apply an explicit business rule. Zone rules can be updated with the JDK's time-zone database; for future appointments, decide whether the system preserves the **09:00 local time intent** or preserves a **fixed `Instant`** if time-zone laws change.

## 7. Full Runnable Java 17+ Program

Create the file **`LocalDateTimeMeaningDemo.java`**:

```java
import java.time.*;

public class LocalDateTimeMeaningDemo {
    public static void main(String[] args) {
        Instant event = Instant.parse("2024-02-29T23:30:00Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        System.out.println("UTC wall time: "
                + LocalDateTime.ofInstant(event, ZoneOffset.UTC));
        System.out.println("VN wall time: "
                + LocalDateTime.ofInstant(event, vietnam));

        LocalDateTime appointment = LocalDateTime.of(2024, 3, 1, 9, 0);
        ZonedDateTime inVietnam = appointment.atZone(vietnam);
        System.out.println("VN appointment: " + inVietnam);
        System.out.println("VN instant: " + inVietnam.toInstant());

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("Gap valid offsets: "
                + newYork.getRules().getValidOffsets(gap).size());
        System.out.println("Gap atZone: " + gap.atZone(newYork));

        LocalDateTime overlap = LocalDateTime.of(2024, 11, 3, 1, 30);
        System.out.println("Overlap valid offsets: "
                + newYork.getRules().getValidOffsets(overlap));
        ZonedDateTime earlier = overlap.atZone(newYork);
        ZonedDateTime later = earlier.withLaterOffsetAtOverlap();
        System.out.println("Earlier occurrence: " + earlier.toInstant());
        System.out.println("Later occurrence: " + later.toInstant());
    }
}
```

Compile and run (Java 17 or later):

```bash
javac LocalDateTimeMeaningDemo.java
java LocalDateTimeMeaningDemo
```

**Actual stdout** verified when compiling the example code with `javac --release 17` and running it:

```text
UTC wall time: 2024-02-29T23:30
VN wall time: 2024-03-01T06:30
VN appointment: 2024-03-01T09:00+07:00[Asia/Ho_Chi_Minh]
VN instant: 2024-03-01T02:00:00Z
Gap valid offsets: 0
Gap atZone: 2024-03-10T03:30-04:00[America/New_York]
Overlap valid offsets: [-04:00, -05:00]
Earlier occurrence: 2024-11-03T05:30:00Z
Later occurrence: 2024-11-03T06:30:00Z
```

The program demonstrates three key distinctions:

1. **One `Instant` has multiple `LocalDateTime` representations** depending on the zone.
2. **A `LocalDateTime` can become an exact instant** when a zone is added and zone rules are resolved.
3. **A `LocalDateTime` during DST can correspond to 0 or 2 instants**: storing only local date-time loses the information needed to uniquely identify the event.

## 8. Parsing and Formatting: The T Separator Does Not Mean UTC

An ISO string like `2024-03-01T09:00:00` is the natural representation of `LocalDateTime`. The letter `T` separates the date part and the time part; **it does not indicate UTC**.

```java
LocalDateTime local = LocalDateTime.parse("2024-03-01T09:00:00");
System.out.println(local); // 2024-03-01T09:00
```

This illustrative snippet requires importing `java.time.LocalDateTime`. Compare the strings:

| String | Meaning | Appropriate type |
| --- | --- | --- |
| `2024-03-01` | Date only | `LocalDate` |
| `2024-03-01T09:00:00` | Date + local time, no offset | `LocalDateTime` |
| `2024-03-01T09:00:00+07:00` | Date + time with +07:00 offset | `OffsetDateTime` |
| `2024-03-01T02:00:00Z` | An instant in UTC | `Instant` |
| `2024-03-01T09:00:00+07:00[Asia/Ho_Chi_Minh]` | Date + time with zone and resolved offset | `ZonedDateTime` |

`LocalDateTime.parse` parses an **ISO local date-time** by default. If the input string contains an offset or zone, parse it into the corresponding type so you **do not discard data**:

```java
OffsetDateTime providedOffset =
        OffsetDateTime.parse("2024-03-01T09:00:00+07:00");
Instant absolute = providedOffset.toInstant();
// 2024-03-01T02:00:00Z

ZonedDateTime providedZone = ZonedDateTime.parse(
        "2024-03-01T09:00:00+07:00[Asia/Ho_Chi_Minh]");
```

This illustrative snippet requires importing `java.time.*`. Calling `providedOffset.toLocalDateTime()` **intentionally drops the offset**; only do this when the business logic wants to keep the local date/time components. For Vietnamese/English formatting with month or weekday names, provide an explicit `Locale` to `DateTimeFormatter`. `Locale` controls the formatting language; it **does not create a `ZoneId`** inside `LocalDateTime`.

## 9. LocalDateTime.now() and Discrepancies Across Machines

Different ways of obtaining "now" have different implications:

```java
LocalDateTime first = LocalDateTime.now(); // JVM default zone
LocalDateTime second = LocalDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDateTime third = LocalDateTime.now(clock); // uses the zone contained in Clock
```

This illustrative snippet requires importing `java.time.*`; `clock` is an externally provided `Clock` variable. The no-argument `now()` depends on the JVM's default zone and real-time clock, so it can produce different results across applications running on multiple machines or in tests near midnight.

A better design is to inject a **time source (`Clock`)** and a **business zone (`ZoneId`)** into the service, read `Instant` once, and convert intentionally:

```java
import java.time.*;
import java.util.Objects;

public final class EventClock {
    private final Clock clock;
    private final ZoneId businessZone;

    public EventClock(Clock clock, ZoneId businessZone) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone = Objects.requireNonNull(businessZone, "businessZone");
    }

    public Instant nowInstant() {
        return clock.instant();
    }

    public LocalDateTime nowBusinessLocal() {
        Instant instant = clock.instant();
        return LocalDateTime.ofInstant(instant, businessZone);
    }
}
```

This is a standalone class that compiles as `EventClock.java`, but it **has no `main` method**, so it is only used as a component in an application or test. Production can supply `Clock.systemUTC()`; tests can supply `Clock.fixed(Instant.parse("2024-02-29T23:30:00Z"), ZoneOffset.UTC)` for reproducible results.

**Note:** If you need both `nowInstant()` and `nowBusinessLocal()` for **the same event**, do not call the two methods separately and assume they represent the exact same instant. Capture one `Instant` at the transaction boundary and pass it through the steps that need it.

## 10. Adding Date-Time: "One Calendar Day" Can Differ From "24 Real Hours"

`LocalDateTime.plusDays(1)` increments the date/time in the ISO calendar domain without DST awareness. When a zone is applied, the actual elapsed duration between the two values can differ from 24 hours.

Example of an appointment at **12:00** on March 9 and March 10, 2024 in New York:

```java
ZoneId ny = ZoneId.of("America/New_York");
LocalDateTime saturdayNoon = LocalDateTime.of(2024, 3, 9, 12, 0);
LocalDateTime sundayNoon = saturdayNoon.plusDays(1);

Instant start = saturdayNoon.atZone(ny).toInstant();
Instant end = sundayNoon.atZone(ny).toInstant();
long hours = Duration.between(start, end).toHours();
// 23 hours (due to DST transition)
```

This illustrative snippet requires importing `java.time.*`. If the user asks for **"12:00 tomorrow local time"**, calendar-day arithmetic makes sense. If they ask for **"after exactly 24 hours"**, use `Duration.ofHours(24)` on an `Instant` to represent actual elapsed time. Do not equate calendar `Period.ofDays(1)` with `Duration.ofDays(1)` being exactly 24 real hours in all zones.

For a recurring schedule such as "every day at 09:00 in Paris", keep `LocalTime`, the date recurrence rule, and `ZoneId` to compute each occurrence, because the UTC offset can change across seasons.

## 11. Storage and APIs: Avoiding Silent Loss of Offset/Zone

Each database management system has its own rules for `TIMESTAMP`, `DATETIME`, `TIMESTAMP WITH TIME ZONE`, and JDBC drivers. **Do not assume from a SQL type name that it reliably stores IANA time-zone information**. Verify the contract of your DBMS, driver, ORM layer, and read/write behavior.

Application-level design rules:

| Data | What should be stored? | Why |
| --- | --- | --- |
| `createdAt`/`paidAt`/`sentAt` | `Instant` or a UTC timestamp with a clear contract | Preserves the actual point in time |
| Branch appointment in local time | `LocalDateTime` + `ZoneId`, DST policy; also store resolved instant if needed | Preserves local time intent and actual instant |
| Recurring schedule "09:00 every Monday" | Recurrence rule + `LocalTime` + `ZoneId` | Allows computing future occurrences per zone rules |
| Birthdays/holidays | `LocalDate` | Avoids arbitrarily turning calendar dates into timestamps |
| Event with offset sent over an API | `OffsetDateTime` or `Instant`, keeping offset if business logic needs it | Does not lose the source's offset |
| Opening hours only | `LocalTime` | No need to attach an arbitrary date |

Example of an ambiguous JSON contract:

```json
{
  "createdAt": "2024-03-01T09:00:00"
}
```

The field name suggests an event that occurred, but the string has no offset/zone. One client might interpret this as UTC; another client might interpret it as machine local time. Choose a contract like:

```json
{
  "createdAt": "2024-03-01T02:00:00Z"
}
```

If preserving the local time intent of an appointment is required:

```json
{
  "appointmentLocal": "2024-03-01T09:00:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

When reading legacy data that only has `LocalDateTime`, you cannot reliably recover the zone/offset by guessing if no prior contract existed: you must establish migration rules based on the data source, configuration, and historical records, and flag cases that cannot be uniquely determined.

## 12. Common Mistakes

1. **Treating `LocalDateTime` as UTC.** The object itself has no UTC context. Use `Instant` or an offset/zone guaranteed by contract.
2. **Storing `LocalDateTime.now()` into `createdAt`.** The result depends on the machine's default zone. Use a `Clock` source and an `Instant`.
3. **Keeping `toLocalDateTime()` after parsing `OffsetDateTime` and discarding the offset.** That loses the absolute timestamp. Only extract local date/time when the business logic genuinely requires it.
4. **Calling `atZone` without understanding gaps/overlaps.** The API has default adjustment/offset-selection rules; business logic may need to reject, explicitly choose an offset, or inform the user.
5. **Treating a fixed offset as equivalent to a city time zone.** Offsets can change due to DST and historical changes; use `ZoneId` for zone rules.
6. **Using `LocalDateTime` for birth dates or opening hours only.** Excess fields easily lead to wrong assumptions. Use `LocalDate` or `LocalTime`.
7. **Assuming adding one calendar day is always exactly 24 hours apart.** Across DST transitions, the difference between `Instant` values can be 23 or 25 hours.
8. **Appending `Z` to a local date-time string in an API response.** This corrupts the data's meaning. Only attach UTC after determining the instant and properly converting to UTC.
9. **Relying on the default zone/locale for parsing or formatting.** Pass explicit context if input/output depends on zone and language.
10. **Assuming two equal `LocalDateTime` values represent the same event.** `equals` only compares date/time fields and knows nothing about time zones or real instants.

## 13. Test Cases to Catch Semantic Bugs

| Scenario | How to test | Expected |
| --- | --- | --- |
| One event displayed in two zones | `LocalDateTime.ofInstant(event, UTC/Vietnam)` | Different local times, same underlying `Instant` |
| Appointment in Vietnam | `2024-03-01T09:00` + `Asia/Ho_Chi_Minh` | `2024-03-01T02:00:00Z` |
| DST gap in New York | `2024-03-10T02:30` + `America/New_York` | 0 valid offsets |
| DST overlap in New York | `2024-11-03T01:30` + `America/New_York` | 2 offsets: `-04:00` and `-05:00` |
| Two occurrences of 01:30 in overlap | Two resolved offsets | `Instant` values differ by one hour |
| Testing "now" | `Clock.fixed` + specified zone | Fixed expected date/time across all runs |
| Adding one day across DST | Noon New York 09–10/03/2024 | `LocalDateTime` differs by 1 calendar day, `Instant` differs by 23 hours |
| Event payload | `createdAt` string with `Z` parsed with `Instant` | Uniquely identifies a single point in time |

In JUnit 5, use `assertEquals` on `Instant` for logic that determines a point in time; use `assertEquals` on `LocalDateTime` for logic that determines a calendar time. For gaps/overlaps, check `getValidOffsets(...).size()` before invoking conversion handling. Testing these two semantics separately is how you catch "works on the developer's machine but has the wrong time in production" bugs.

## 14. Quick Selection Rules

1. **Date only?** Choose `LocalDate`.
2. **Time of day only?** Choose `LocalTime`.
3. **Calendar date + time, zone not yet chosen or only representing local intent?** `LocalDateTime` is appropriate.
4. **An event with a definite point in time?** Choose `Instant`; convert to local time for display.
5. **Date + time with an offset specified by the source?** Choose `OffsetDateTime`.
6. **Date + time following a zone's rules, especially with DST/appointments?** Choose `ZonedDateTime`, or store the local date-time intent together with `ZoneId` and a resolution policy.
7. **Measuring real elapsed time?** Choose `Duration` between `Instant` values.

**Core takeaway:** `LocalDateTime` is very useful when "date and time on the wall clock" is the source data. It starts losing meaning when a real point in time or time-zone rule is replaced by a context-free date/time. Store enough **instant, zone, or offset** information to match your actual need, and never infer information that `LocalDateTime` does not have.
