# Combining and Converting Types with `at...()` and `to...()` in `java.time`

When programming with dates and times, we often have separate pieces of data: a user selects a date, enters an appointment time, chooses a location, and then the application needs to store the actual point in time of the appointment. Java provides methods such as `atTime()`, `atDate()`, `atZone()`, `atOffset()`, `toLocalDate()`, `toLocalTime()`, and `toInstant()` to **combine information or convert between representations**.

The `at...()` and `to...()` names are a helpful mnemonic, not two interchangeable syntax rules. Each method belongs to **a specific class**, accepts specific parameters, and returns a specific type. What matters is understanding what information the conversion **adds, preserves, and whether it loses any information**.

This lesson belongs to the **Getting Started with `java.time`** section and focuses on common combination/conversion operations, how to interpret results, time-zone pitfalls, and how to verify them with Java 17+.

## 1. Review of Data Types to Combine/Convert

| Type | What information does it contain? | What information is missing? |
| --- | --- | --- |
| `LocalDate` | Year, month, day | Time, offset, time zone |
| `LocalTime` | Hour, minute, second, nanoseconds if present | Date, offset, time zone |
| `LocalDateTime` | Local date + time | Offset/time zone to uniquely identify a point in time |
| `ZoneOffset` | A specific UTC offset, e.g., `+07:00` | Regional time-zone rules |
| `ZoneId` | A zone identifier, e.g., `Asia/Ho_Chi_Minh` | A specific time; must be combined with a date/time or instant |
| `OffsetDateTime` | Date-time + a specific offset | Regional time-zone identifier/rules |
| `ZonedDateTime` | Date-time + `ZoneId` and resolved offset | Nothing missing to derive an instant |
| `Instant` | A single point on the timeline | Calendar/time-zone presentation for the user |

For example, the string `2026-10-24 09:30` is only a local date and time. If we know it is in `Asia/Ho_Chi_Minh`, Java can apply the zone rules to derive `2026-10-24T02:30:00Z`. Conversely, once you have an `Instant`, you must provide a time zone to display the correct date and time to the user.

There are two important conversion directions:

~~~text
LocalDate + LocalTime
         │ atTime() / atDate()
         ▼
   LocalDateTime + ZoneId
         │ atZone()
         ▼
    ZonedDateTime
         │ toInstant()
         ▼
       Instant
         │ atZone(ZoneId)
         ▼
    ZonedDateTime
         │ toLocalDate() / toLocalTime() / toLocalDateTime()
         ▼
   Calendar components for display
~~~

The arrows do **not** mean that every step retains enough information to be reversible. `toLocalDate()` discards the time and zone; you cannot rely on a standalone date to get back to the same instant.

## 2. `at...()`: Combining Information or Placing a Value in Context

### 2.1. `LocalDate.atTime()` and `LocalTime.atDate()`

When you have a separate date and time, combine them into a `LocalDateTime`:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalTime time = LocalTime.of(9, 30);

LocalDateTime a = date.atTime(time);
LocalDateTime b = time.atDate(date);

// Both a and b are 2026-10-24T09:30.
~~~

Both ways produce the same **local date-time**. Even though one method starts from the date and the other starts from the time, **neither creates an instant yet**. The program still needs to specify a zone or offset if it wants to know which point on the timeline that `09:30` corresponds to.

`LocalDate` also has overloads `atTime(int hour, int minute)`, `atTime(int hour, int minute, int second)`, and `atTime(OffsetTime)`. With `OffsetTime`, the result is `OffsetDateTime` because the time already contains an offset; a method named `atTime` does not always return `LocalDateTime`.

### 2.2. `atStartOfDay()` and `atStartOfDay(ZoneId)`

A date does not contain a time. Sometimes you need the start-of-day boundary:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

LocalDateTime localMidnight = date.atStartOfDay();
ZonedDateTime firstValidTime =
        date.atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

`atStartOfDay()` with no arguments returns a `LocalDateTime` at `00:00`. Meanwhile, `atStartOfDay(ZoneId)` returns a **`ZonedDateTime` at the first valid start of the day according to the zone rules**. There are places/historical periods where midnight falls inside a skipped hour; therefore, the zoned variable does not necessarily show `00:00`.

The zoned version is suitable for defining query boundaries such as "events on day D in locality X".

### 2.3. `LocalDateTime.atZone(ZoneId)`

When you have a scheduled local date-time and **know the location/time zone**, attach it with `ZoneId`:

~~~java
LocalDateTime appointment = LocalDateTime.of(2026, 10, 24, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localAppointment = appointment.atZone(zone);
Instant eventTime = localAppointment.toInstant();
~~~

In this example, `eventTime` is `2026-10-24T02:30:00Z`. `atZone` uses the zone rules to choose a valid offset for the supplied date-time; it does not simply attach a time-zone name string to the value.

**Note:** in zones with Daylight Saving Time (DST), a local time may be skipped or repeated. `atZone` has default handling, so scheduling systems need to consider the DST policy discussed below.

### 2.4. `LocalDateTime.atOffset(ZoneOffset)`

When you **know the exact offset** of a local date-time, you can create an `OffsetDateTime`:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);
OffsetDateTime datedWithOffset =
        local.atOffset(ZoneOffset.ofHours(7));

Instant sameMoment = datedWithOffset.toInstant();
~~~

The result `datedWithOffset` is `2026-10-24T09:30+07:00`, which resolves to the same instant `2026-10-24T02:30:00Z`. `ZoneOffset` states a fixed offset, but it **does not prove** that the offset is valid for a region like New York on the given date. When the business requirement only provides a region name, use `atZone(ZoneId)`.

### 2.5. Other Useful Combinations

`LocalTime.atOffset(ZoneOffset)` creates an `OffsetTime`, which is a clock time with an offset but **no date yet**. When a date is added, `OffsetTime.atDate(LocalDate)` returns an `OffsetDateTime`.

~~~java
LocalTime opening = LocalTime.of(8, 0);
OffsetTime timeWithOffset = opening.atOffset(ZoneOffset.ofHours(7));

LocalDate date = LocalDate.of(2026, 10, 24);
OffsetDateTime fullValue = timeWithOffset.atDate(date);

// fullValue = 2026-10-24T08:00+07:00
~~~

Similarly, `date.atTime(timeWithOffset)` also produces an `OffsetDateTime`. Having both combination directions lets you choose the clearest style depending on which date/time component you start with.

`Instant.atZone(ZoneId)` and `Instant.atOffset(ZoneOffset)` are a different case: they start from an **already-known instant** and produce a zoned/offset representation, thereby **preserving the absolute point in time**.

~~~java
Instant recorded = Instant.parse("2026-10-24T02:30:00Z");

ZonedDateTime vnView =
        recorded.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
OffsetDateTime offsetView = recorded.atOffset(ZoneOffset.ofHours(7));

// vnView    = 2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]
// offsetView = 2026-10-24T09:30+07:00
~~~

Even though both share the name `atZone`, **`LocalDateTime.atZone` must interpret a local time**, whereas **`Instant.atZone` only changes the view of an already-determined instant**.

## 3. `to...()`: Extracting Components or Changing Representation

### 3.1. From `LocalDateTime` to Date and Time

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);

LocalDate day = local.toLocalDate(); // 2026-10-24
LocalTime time = local.toLocalTime(); // 09:30
~~~

`toLocalDate()` and `toLocalTime()` **extract one part** of `LocalDateTime`. If you keep only `day`, `09:30` is lost; if you keep only `time`, you no longer know the date `2026-10-24`. These two extractions are for presentation and calendar-component processing, not time-zone conversion.

### 3.2. From `ZonedDateTime` to `Instant`

~~~java
ZonedDateTime scheduled =
        LocalDateTime.of(2026, 10, 24, 9, 30)
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

Instant moment = scheduled.toInstant();
~~~

`toInstant()` preserves the **exact point on the timeline**, but the result no longer carries the zone name or local time. When displaying it back to a user, you need to supply a `ZoneId`.

From a `ZonedDateTime`, you can call:

- `toLocalDate()` to get the calendar date.
- `toLocalTime()` to get the wall-clock time.
- `toLocalDateTime()` to get both date and time, while **discarding zone/offset information**.
- `toOffsetDateTime()` to get the date-time and the **currently applied offset**, while discarding the zone-rule identifier.
- `toInstant()` to get the absolute timestamp, discarding the calendar representation and zone.

Calls like `toLocal...()` or `toOffsetDateTime()` can lose context needed to reconstruct recurring schedules in the future. Do not treat them as "lossless" conversions.

### 3.3. From `OffsetDateTime` to `Instant` and Other Types

~~~java
OffsetDateTime input =
        OffsetDateTime.parse("2026-10-24T09:30:00+07:00");

Instant stored = input.toInstant();
LocalDateTime shownWithoutOffset = input.toLocalDateTime();
ZonedDateTime withFixedOffsetZone = input.toZonedDateTime();
~~~

`input.toInstant()` gives `2026-10-24T02:30:00Z`. `input.toLocalDateTime()` gives `2026-10-24T09:30` and **loses the offset**. `toZonedDateTime()` creates a `ZonedDateTime` using the value's offset itself as the zone; it **does not automatically recover** the original geographic region such as `Asia/Ho_Chi_Minh`.

`OffsetDateTime` knows the instant because it has an offset, but it does not know the original locality from `+07:00` alone. To attach a real zone **while keeping the same instant**, use `input.atZoneSameInstant(zone)`.

### 3.4. `LocalDateTime.toInstant(ZoneOffset)`

`LocalDateTime` **does not have** a no-argument `toInstant()`. When a specific offset is known, Java allows:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 30);

Instant moment = local.toInstant(ZoneOffset.ofHours(7));
long epochSeconds = local.toEpochSecond(ZoneOffset.ofHours(7));
~~~

`toInstant(ZoneOffset)` directly uses the offset supplied by the caller; it **does not consult `ZoneId` rules**. If the input is a local time in a zone with DST, you must confirm the offset for that date, usually via `atZone(zone).toInstant()`.

## 4. Quick Reference Table of Combination and Conversion Operations

| Starting from | Method | Return type | Effect on information |
| --- | --- | --- | --- |
| `LocalDate` | `atTime(LocalTime)` | `LocalDateTime` | Adds time to date |
| `LocalTime` | `atDate(LocalDate)` | `LocalDateTime` | Adds date to time |
| `LocalDate` | `atStartOfDay()` | `LocalDateTime` | Picks local 00:00, no zone yet |
| `LocalDate` | `atStartOfDay(ZoneId)` | `ZonedDateTime` | Finds valid start of day in the zone |
| `LocalTime` | `atOffset(ZoneOffset)` | `OffsetTime` | Adds offset to time, no date yet |
| `OffsetTime` | `atDate(LocalDate)` | `OffsetDateTime` | Adds date to offset time |
| `LocalDateTime` | `atOffset(ZoneOffset)` | `OffsetDateTime` | Attaches caller-supplied offset |
| `LocalDateTime` | `atZone(ZoneId)` | `ZonedDateTime` | Resolves offset using zone rules |
| `Instant` | `atZone(ZoneId)` | `ZonedDateTime` | Preserves instant, presents in zone |
| `Instant` | `atOffset(ZoneOffset)` | `OffsetDateTime` | Preserves instant, presents with offset |
| `ZonedDateTime` | `toInstant()` | `Instant` | Preserves instant; drops display/zone |
| `ZonedDateTime` | `toOffsetDateTime()` | `OffsetDateTime` | Preserves instant and current offset; drops `ZoneId` |
| `ZonedDateTime` | `toLocalDateTime()` | `LocalDateTime` | Preserves wall-clock date-time; drops zone/offset |
| `ZonedDateTime` | `toLocalDate()` / `toLocalTime()` | `LocalDate` / `LocalTime` | Keeps only the extracted component |
| `OffsetDateTime` | `toInstant()` | `Instant` | Preserves instant; drops time/offset presentation |
| `OffsetDateTime` | `toLocalDateTime()` | `LocalDateTime` | Preserves local date-time; drops offset |
| `LocalDateTime` | `toInstant(ZoneOffset)` | `Instant` | Derives instant using the specified offset |

Not every type has every method in the table. Rely on the variable type on the **left-hand side** of the call rather than guessing from a method name and applying it to another type.

## 5. Complete Runnable Java 17+ Example

The following program demonstrates combining date + time, attaching a zone, converting to an instant, converting to another zone, and extracting components back out:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class AtToConversionDemo {
    public static void main(String[] args) {
        LocalDate day = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30);

        LocalDateTime local = day.atTime(time);
        LocalDateTime sameLocal = time.atDate(day);

        ZoneId vietnamZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime vietnam = local.atZone(vietnamZone);
        Instant instant = vietnam.toInstant();

        ZonedDateTime tokyo =
                instant.atZone(ZoneId.of("Asia/Tokyo"));
        OffsetDateTime withOffset = vietnam.toOffsetDateTime();

        System.out.println("local=" + local);
        System.out.println("sameLocal=" + sameLocal);
        System.out.println("vietnam=" + vietnam);
        System.out.println("instant=" + instant);
        System.out.println("tokyo=" + tokyo);
        System.out.println("date=" + vietnam.toLocalDate());
        System.out.println("time=" + vietnam.toLocalTime());
        System.out.println("offset=" + withOffset);
        System.out.println("roundTrip=" +
                instant.atZone(vietnamZone).toLocalDateTime());
    }
}
~~~

Save the file as `AtToConversionDemo.java` and run:

~~~bash
javac AtToConversionDemo.java
java AtToConversionDemo
~~~

Expected output when using the corresponding standard time-zone data:

~~~text
local=2026-10-24T09:30
sameLocal=2026-10-24T09:30
vietnam=2026-10-24T09:30+07:00[Asia/Ho_Chi_Minh]
instant=2026-10-24T02:30:00Z
tokyo=2026-10-24T11:30+09:00[Asia/Tokyo]
date=2026-10-24
time=09:30
offset=2026-10-24T09:30+07:00
roundTrip=2026-10-24T09:30
~~~

**Explanation of the conversion chain:**

1. `day.atTime(time)` and `time.atDate(day)` create the same `LocalDateTime`; at this step **there is no instant yet**.
2. `local.atZone(vietnamZone)` applies the zone rules and creates a `ZonedDateTime` with offset `+07:00` on the chosen date.
3. `vietnam.toInstant()` converts that point in time to a time-zone-independent representation: `02:30 UTC`.
4. `instant.atZone(Asia/Tokyo)` gives `11:30` in Tokyo at **the same point in time**, instead of keeping `09:30`.
5. `toLocalDate()`, `toLocalTime()`, and `toOffsetDateTime()` extract different views/subsets of information from the same value.
6. Converting back to Vietnam with `instant.atZone(vietnamZone)` yields the original local date and time because the example uses a valid time and a zone without DST on that date.

The program does not call `now()`, so the output does not depend on when it is executed.

## 6. Two Operations That Look Similar but Have Different Business Semantics

### 6.1. Changing Zone While Keeping the Same Instant

From `ZonedDateTime`, use `withZoneSameInstant(newZone)`:

~~~java
ZonedDateTime vietnam =
        LocalDateTime.of(2026, 10, 24, 9, 30)
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime sameMomentInTokyo =
        vietnam.withZoneSameInstant(ZoneId.of("Asia/Tokyo"));

// 2026-10-24T11:30+09:00[Asia/Tokyo]
~~~

Changing the zone here changes the wall-clock time while preserving the actual point in time. This is what we usually want when displaying transaction history, events, or appointments to a user in another time zone. An equivalent approach is `vietnam.toInstant().atZone(targetZone)`.

### 6.2. Changing Zone While Trying to Keep the Local Date and Time

`withZoneSameLocal(newZone)` tries to keep the same **wall-clock date and time**, then interprets them in the new zone:

~~~java
ZonedDateTime sameClockTimeInTokyo =
        vietnam.withZoneSameLocal(ZoneId.of("Asia/Tokyo"));

// 2026-10-24T09:30+09:00[Asia/Tokyo]
~~~

`09:30` in Tokyo is a **different instant** from `09:30` in Vietnam. This is only appropriate if the requirement genuinely intends to change the location of a scheduled time while keeping the wall-clock time. In zones with gaps/overlaps, Java may have to adjust the time/offset to produce a valid point in time.

Similarly, `OffsetDateTime.atZoneSameInstant(zone)` preserves the instant; `atZoneSimilarLocal(zone)` tries to keep the local time if possible. Do not use `atZoneSimilarLocal` to display an already-recorded event to someone in a new time zone.

## 7. Why `atZone()` Requires Attention to DST

When attaching a `ZoneId` to a `LocalDateTime`, Java must resolve the date-time according to **time-zone rules**. For regions that observe Daylight Saving Time:

- **Gap:** a range of local time does not exist because the clock springs forward. By default, `atZone` pushes the local time forward by the length of the gap.
- **Overlap:** a range of local time occurs twice when the clock falls back. By default, `atZone` chooses the earlier offset in the overlap; the application can choose the later offset.

Example in New York (under current DST rules for 2026):

~~~java
ZoneId ny = ZoneId.of("America/New_York");

LocalDateTime gap = LocalDateTime.of(2026, 3, 8, 2, 30);
ZonedDateTime shifted = gap.atZone(ny);
// 2026-03-08T03:30-04:00[America/New_York]

LocalDateTime overlap = LocalDateTime.of(2026, 11, 1, 1, 30);
ZonedDateTime earlier = overlap.atZone(ny);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

// earlier: 2026-11-01T01:30-04:00[America/New_York]
// later:   2026-11-01T01:30-05:00[America/New_York]
~~~

These are illustrative snippets; you need to import `java.time.*` in a standalone program. For the gap, the input `02:30` becomes `03:30`; for the overlap, the same `01:30` can correspond to two instants one hour apart. The rule `ZoneRules.getValidOffsets(localDateTime)` returns the list of valid offsets: 0 elements = gap, 1 = normal, 2 = overlap.

**Consequence:** `local.atZone(zone).toInstant()` is the API-correct conversion, but if the input is a user-entered appointment in a DST zone, the business logic must decide whether to accept the shifted time or require the user to explicitly choose which `01:30` occurrence they mean. Do not assume that every `LocalDateTime` corresponds to a unique `Instant`.

## 8. Error-Prone Conversions

### 8.1. Losing Information and Assuming It Can Be Recovered

~~~java
ZonedDateTime original = /* appointment with ZoneId */;
LocalDateTime localOnly = original.toLocalDateTime();
~~~

This is an **illustrative snippet, not a standalone program**. `localOnly` does not retain the `ZoneId`, offset, or offset choice during a DST overlap. If converted back using `atZone(ZoneId.systemDefault())`, the result may be a different instant when the machine runs in another zone or when the user changes their zone.

If you need to preserve an event, store `Instant`. If you need to preserve "09:00 Monday in Paris", keep the local date-time, zone identifier, and corresponding scheduling rules.

### 8.2. Using the Wrong Offset for a Locality

~~~java
LocalDateTime newYorkWinter =
        LocalDateTime.of(2026, 12, 1, 9, 0);

Instant byZone = newYorkWinter
        .atZone(ZoneId.of("America/New_York"))
        .toInstant();

Instant byWrongOffset =
        newYorkWinter.toInstant(ZoneOffset.ofHours(-4));
~~~

In December 2026, New York uses `-05:00` under current rules. The value `byWrongOffset` is off by **one hour** compared to `byZone` because the caller mistakenly assumed `-04:00`. If a region name is provided, resolve it using `ZoneId` at that specific date and time.

### 8.3. Thinking `toLocalDate()` Means "Get the Date in the User's Time Zone"

`Instant` is a global point in time and has no concept of a local date. To get **the date the user sees**, do:

~~~java
Instant createdAt = Instant.parse("2026-10-24T23:30:00Z");

LocalDate vietnamDate =
        createdAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toLocalDate();

// vietnamDate = 2026-10-25
~~~

`toLocalDate()` takes the date of a **value that already has zone context**; the result depends on the previously selected zone. You cannot derive a user's display date from an `Instant` without knowing the user's zone or business zone.

### 8.4. Confusing `parse/format` with `at/to`

`LocalDate.parse("2026-10-24")` converts a **properly formatted string** into a date value. `date.format(formatter)` converts a date value into a **string for display**. By contrast, `date.atTime(time)` creates another Java value by combining information; `zoned.toInstant()` changes the time representation model. Calling `toString()` or formatting a value **does not replace** resolving offsets/time zones.

### 8.5. Unintentionally Depending on `ZoneId.systemDefault()`

If data is tied to a business time zone, obtain `ZoneId` from configuration, user profile, or event location. `ZoneId.systemDefault()` can differ across laptops, servers, and containers. Calling `atZone` on the same `LocalDateTime` under two different default zones can produce two different instants.

## 9. Design Rules for Date-Time Data

**Receiving a local appointment:** read `LocalDate`, `LocalTime`, and the business-determined `ZoneId` → use `atTime` then `atZone` → check DST → store an instant if an absolute event needs to be identified, or preserve the zone/rules if the schedule recurs.

**Displaying a stored timestamp:** read `Instant` → `atZone(userZone)` → format the date-time for the user. Do not modify the original instant just to change the time zone.

**Filtering transactions by local day:** take the start of the day and the start of the next day using `LocalDate.atStartOfDay(zone).toInstant()`; query the half-open interval **[startInclusive, endExclusive)** to avoid missing the last nanoseconds of the day or duplicating boundary transactions.

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate reportingDay = LocalDate.of(2026, 10, 24);

Instant startInclusive =
        reportingDay.atStartOfDay(businessZone).toInstant();
Instant endExclusive =
        reportingDay.plusDays(1).atStartOfDay(businessZone).toInstant();
~~~

**Storing "created at":** `Instant.now(clock)` is the timestamp; `Instant.atZone(...)` is only for display. Do not convert to `LocalDateTime` and try to guess the zone again after storing.

**Writing tests:** use fixed dates as in the examples, test results before and after changing zones; test gaps/overlaps if the business handles local schedules; test across multiple zones; verify that conversions claimed to "preserve the instant" actually produce equal `toInstant()` values. Avoid checking only `toString()` strings if the real goal is computing the exact point in time.

## 10. Self-Practice

1. Given `LocalDate.of(2026, 10, 24)` and `LocalTime.of(9, 30)`. Write two ways to create a `LocalDateTime` using `atTime` and `atDate`; explain why there is no instant yet.
2. Given `Instant.parse("2026-10-24T02:30:00Z")`. Display the time in `Asia/Ho_Chi_Minh` and `Asia/Tokyo` using `atZone`; use `toInstant` to prove both values refer to the same point in time.
3. Given a `ZonedDateTime` in Vietnam. Compare `withZoneSameInstant(Asia/Tokyo)` with `withZoneSameLocal(Asia/Tokyo)`. Which one is appropriate when displaying a transaction to a user in Tokyo?
4. Given an appointment at `09:00` in New York on `2026-12-01`. Why is using `LocalDateTime.toInstant(ZoneOffset.ofHours(-4))` risky?
5. After `zoned.toLocalDateTime()`, can you reliably recover the exact original instant without storing the zone/offset? Consider DST overlaps as well.
6. Do the start of day `2026-10-24` in Vietnam and the start of day `2026-10-24` in Tokyo have the same instant? Use `atStartOfDay(zone).toInstant()` to prove it.

**Key takeaway:** `at...()` generally helps **combine or place a value in context**; `to...()` generally extracts **another representation or component**. Before every call, identify the **input type, return type, what information is added or removed, and whether the instant is preserved**. With `LocalDateTime`, an absolute point on the timeline can only be derived once you have an appropriate offset or `ZoneId` rules.
