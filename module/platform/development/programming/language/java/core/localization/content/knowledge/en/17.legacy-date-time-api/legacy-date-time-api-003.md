# Calendar, TimeZone, and Default Values

## 1. Why do we need to understand the legacy date-time API?

In Java Core, the two long-standing classes `java.util.Calendar` and `java.util.TimeZone` appear in many systems, libraries, enterprise applications, and APIs that require backward compatibility. They can work correctly, but **they are especially prone to bugs caused by relying on shared JVM default values**.

For example, the two statements:

```java
Calendar calendar = Calendar.getInstance();
TimeZone zone = TimeZone.getDefault();
```

do not mean "get the calendar and time zone of the currently logged-in user." They obtain the default configuration of the **JVM process** at that moment. If the same server serves users in Vietnam, the United States, and Japan, uncontrolled use of those defaults can cause **the same instant** to be interpreted as an unintended date or time.

After this lesson, you will know:

- What `Calendar`, `GregorianCalendar`, and `TimeZone` represent, as well as their relationship with `Date`.
- How `Calendar.getInstance()` retrieves the **default time zone** and **default FORMAT locale**.
- The difference between `Locale`, `TimeZone`, **UTC offset**, and **point in time (instant)**.
- The risks of calling `Locale.setDefault(...)` or `TimeZone.setDefault(...)` per request/thread.
- Common traps: 0-based `MONTH`, lenient dates, `add`/`roll`, week rules, and daylight saving time (DST).
- How to use the legacy API with explicit locale/time zone and how to migrate to `java.time` on Java 17+.

## 2. Three objects with different meanings

| Component | Answers the question | Key point to remember |
| --- | --- | --- |
| `java.util.Date` | A point in time with millisecond resolution | Does not carry the user's locale or time zone |
| `java.util.TimeZone` | Rules to convert UTC to local time for a region or offset | May include historical DST changes; distinct from locale |
| `java.util.Calendar` | Calendar fields like year, month, day, hour in a calendar system, based on a time zone | Mutable; fields depend on time zone and calendar configuration |
| `java.util.Locale` | Language and cultural region conventions for display/formatting | Does not uniquely determine a time zone |
| `java.time.Instant` | Absolute point in time, accurate to nanoseconds in the Java Time model | Usually appropriate for storing timestamps |
| `java.time.ZoneId` / `ZonedDateTime` | Region ID and local time bound to region rules | Modern replacement for many `TimeZone`/`Calendar` use cases |

A `Date` can be displayed across different regions while **its epoch milliseconds remain unchanged**. `Calendar` combines a point in time with a time zone to derive year/month/day/hour fields. Locale affects how weekdays and months are named, week rules, and in some cases the calendar type, but **does not** implicitly specify the user's geographic location or time zone.

For example, two users with `Locale.forLanguageTag("en-US")` may live in New York and Tokyo. Conversely, someone living in Ho Chi Minh City may still use an English UI. Therefore, **keep `Locale` and `TimeZone`/`ZoneId` as two independent choices**.

## 3. JVM-level defaults: origin and scope

### 3.1. `TimeZone.getDefault()`

`TimeZone.getDefault()` returns the JVM's default time zone. The initial default is usually determined by the OS environment and startup settings, including the `user.timezone` system property. A program can change the default zone:

```java
TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
```

This is a **JVM-wide change**, not "the current request's time zone." Other threads calling APIs that read the default afterward may receive `UTC`. Calling `setDefault(null)` may cause the runtime to re-determine the default value; in tests you should usually save the old value and restore that exact value, rather than guessing a new one.

The `TimeZone.getDefault()` API returns a cloned default object to prevent directly mutating the default through the returned object. However, `TimeZone.setDefault(...)` mutates the **shared global default configuration**; receiving a clone does not make the default thread-local.

### 3.2. `Locale.getDefault()` and `Locale.Category.FORMAT`

Java has JVM-level locale defaults, including two categories:

- `Locale.Category.FORMAT` is for locale-sensitive formatting/calendar operations.
- `Locale.Category.DISPLAY` is for displaying language/region names and similar content.

`Calendar.getInstance()` does not read personal preferences from an HTTP request. When constructing a calendar with defaults, locale selection typically uses **`Locale.getDefault(Locale.Category.FORMAT)`**.

`Locale.setDefault(Locale)` changes the base default and sets the category defaults; `Locale.setDefault(Locale.Category.FORMAT, locale)` only changes that category, yet **still at the JVM scope**. Do not mutate these values at the start of each request to try to support multiple languages or time zones.

### 3.3. `Calendar.getInstance` overloads

| Creation method | Time zone | Locale |
| --- | --- | --- |
| `Calendar.getInstance()` | JVM default | JVM FORMAT default |
| `Calendar.getInstance(TimeZone zone)` | Passed time zone | FORMAT default |
| `Calendar.getInstance(Locale locale)` | Default time zone | Passed locale |
| `Calendar.getInstance(TimeZone zone, Locale locale)` | **Explicit time zone** | **Explicit locale** |

When processing user data or communicating with external systems, **prefer the overload accepting both time zone and locale** if you still must use `Calendar`.

### 3.4. Does changing the default update already-created `Calendar` objects?

Not by default. An already-constructed calendar object has its own time zone and properties. Changing the JVM default mainly affects **newly constructed instances** from code relying on defaults, rather than automatically syncing all previously created calendars.

This makes changing defaults mid-flight even harder to reason about: two components of an application may hold instances initialized at different times with different time zones/locales.

## 4. Java 17+ example: observing the effect of defaults and categories

Create the file `LegacyDefaultsDemo.java`:

```java
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyDefaultsDemo {
    public static void main(String[] args) {
        Locale beforeBase = Locale.getDefault();
        Locale beforeFormat =
                Locale.getDefault(Locale.Category.FORMAT);
        Locale beforeDisplay =
                Locale.getDefault(Locale.Category.DISPLAY);
        TimeZone beforeZone = TimeZone.getDefault();

        try {
            Locale.setDefault(Locale.US);
            Locale.setDefault(Locale.Category.FORMAT, Locale.FRANCE);
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));

            Calendar fromDefault = Calendar.getInstance();
            Calendar explicit = Calendar.getInstance(
                    TimeZone.getTimeZone("UTC"), Locale.US);

            System.out.println("base locale: "
                    + Locale.getDefault().toLanguageTag());
            System.out.println("format locale: "
                    + Locale.getDefault(Locale.Category.FORMAT)
                            .toLanguageTag());
            System.out.println("default calendar zone: "
                    + fromDefault.getTimeZone().getID());
            System.out.println("default first day: "
                    + fromDefault.getFirstDayOfWeek());
            System.out.println("default minimal days: "
                    + fromDefault.getMinimalDaysInFirstWeek());
            System.out.println("US first day: "
                    + explicit.getFirstDayOfWeek());
            System.out.println("US minimal days: "
                    + explicit.getMinimalDaysInFirstWeek());

            TimeZone.setDefault(
                    TimeZone.getTimeZone("Asia/Tokyo"));
            System.out.println("existing calendar zone: "
                    + fromDefault.getTimeZone().getID());
            System.out.println("new calendar zone: "
                    + Calendar.getInstance().getTimeZone().getID());
        } finally {
            // Only safe in experiments/tests on a non-concurrent JVM.
            Locale.setDefault(beforeBase);
            Locale.setDefault(
                    Locale.Category.FORMAT, beforeFormat);
            Locale.setDefault(
                    Locale.Category.DISPLAY, beforeDisplay);
            TimeZone.setDefault(beforeZone);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 LegacyDefaultsDemo.java
java LegacyDefaultsDemo
```

Verified output with standard JDK locale data:

```text
base locale: en-US
format locale: fr-FR
default calendar zone: UTC
default first day: 2
default minimal days: 4
US first day: 1
US minimal days: 1
existing calendar zone: UTC
new calendar zone: Asia/Tokyo
```

In `Calendar`, `Calendar.SUNDAY == 1` and `Calendar.MONDAY == 2`. `Locale.FRANCE` typically starts the week on Monday and requires a minimum of 4 days in the first week of the year; `Locale.US` typically starts on Sunday with 1 minimum day. This is why **locale can affect week numbers** even when both calendars use `UTC`.

The example intentionally changes defaults to demonstrate behavior, then restores them in `finally`. **Do not put this kind of default mutation into a multithreaded server request handler.** `finally` does not turn a mutate-default/execute/restore sequence into a per-request isolated operation.

## 5. Same instant, different local date and time

Suppose an absolute point in time is:

```text
2026-01-01T00:30:00Z
```

Here `Z` means UTC offset +00:00. At this point in time:

- `UTC`: Jan 1, 2026, 00:30.
- `America/Los_Angeles`: Dec 31, 2025, 16:30 under the active winter offset.
- `Asia/Tokyo`: Jan 1, 2026, 09:30.

If you call `Calendar.getInstance()` without passing a time zone, the result depends on the JVM default; the same timestamp data can jump to a **different day or year**.

### Runnable example: one epoch, three time zones

Create `CalendarInstantDemo.java`:

```java
import java.time.Instant;
import java.util.Calendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarInstantDemo {
    static void show(Instant instant, String zoneId) {
        Calendar calendar = Calendar.getInstance(
                TimeZone.getTimeZone(zoneId), Locale.US);
        calendar.setTimeInMillis(instant.toEpochMilli());

        System.out.printf(
                "%s => %04d-%02d-%02d %02d:%02d%n",
                zoneId,
                calendar.get(Calendar.YEAR),
                calendar.get(Calendar.MONTH) + 1,
                calendar.get(Calendar.DAY_OF_MONTH),
                calendar.get(Calendar.HOUR_OF_DAY),
                calendar.get(Calendar.MINUTE));
    }

    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-01-01T00:30:00Z");
        show(instant, "UTC");
        show(instant, "America/Los_Angeles");
        show(instant, "Asia/Tokyo");
    }
}
```

```bash
javac CalendarInstantDemo.java
java CalendarInstantDemo
```

Output (under tzdb rules for the stated timestamp):

```text
UTC => 2026-01-01 00:30
America/Los_Angeles => 2025-12-31 16:30
Asia/Tokyo => 2026-01-01 09:30
```

`setTimeInMillis(...)` sets the same epoch for all three calendars; only **how the Calendar fields are derived** differs. Conversely, if you set `2026-01-01 00:30` via `set(...)` on three different time zones, each zone will represent a different instant.

**Remember:** `Calendar.getTime()` returns a `Date` representing an instant, not a "Date carrying a timezone"; when formatting a `Date`, the formatter and zone you choose determine how it is displayed.

## 6. Familiar `Calendar` traps

### 6.1. `MONTH` starts at 0

In `Calendar`:

```text
Calendar.JANUARY  == 0
Calendar.FEBRUARY == 1
Calendar.MARCH    == 2
Calendar.DECEMBER == 11
```

Therefore:

```java
Calendar c = Calendar.getInstance(
        TimeZone.getTimeZone("UTC"), Locale.US);
c.clear();
c.set(2026, Calendar.MARCH, 8);
System.out.println(c.get(Calendar.MONTH) + 1); // 3
```

This is an **illustrative snippet inside a method**, not a standalone Java program. `clear()` clears leftover fields to avoid side effects when building a point in time; do not pass month `3` if you mean March in `set(year, month, day)`.

Other fields also have differences:

- `Calendar.DAY_OF_WEEK`: Sunday = `1`, Monday = `2`.
- `Calendar.HOUR`: hour on a 12-hour cycle, must be paired with `AM_PM`.
- `Calendar.HOUR_OF_DAY`: hour 0–23, usually better suited for timestamps.
- `Calendar.WEEK_OF_YEAR` and `Calendar.getWeekYear()` can differ from `YEAR` around year boundaries, depending on locale week rules.
- `Calendar.getActualMaximum(Calendar.DAY_OF_MONTH)` computes the maximum number of days in the month for the current calendar state, unlike assuming every month has 31 days.

### 6.2. Default `lenient` mode

`Calendar` is usually **lenient** by default: it can accept out-of-range calendar fields and normalize them into a valid date. If you set **Feb 30, 2026**, the result can roll over to **Mar 2, 2026** in the Gregorian calendar.

```java
Calendar calendar = new java.util.GregorianCalendar(
        TimeZone.getTimeZone("UTC"), Locale.US);
calendar.clear();
calendar.set(2026, Calendar.FEBRUARY, 30);
// Because lenient=true by default, accessing the time will normalize.
```

When input must be strict, use `calendar.setLenient(false)` and force computation via `getTimeInMillis()` or `getTime()` to detect invalid values. `setLenient(false)` does not usually throw immediately on `set(...)`; validation can occur when accessing the time/computed fields.

### Java 17+ example: lenient and strict

Create `CalendarLeniencyDemo.java`:

```java
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarLeniencyDemo {
    public static void main(String[] args) {
        GregorianCalendar c = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.US);

        c.clear();
        c.set(2026, Calendar.FEBRUARY, 30);
        System.out.printf(
                "lenient: %04d-%02d-%02d%n",
                c.get(Calendar.YEAR),
                c.get(Calendar.MONTH) + 1,
                c.get(Calendar.DAY_OF_MONTH));

        c.setLenient(false);
        c.clear();
        c.set(2026, Calendar.FEBRUARY, 30);
        try {
            c.getTimeInMillis();
            System.out.println("accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict invalid date rejected");
        }
    }
}
```

```bash
javac CalendarLeniencyDemo.java
java CalendarLeniencyDemo
```

```text
lenient: 2026-03-02
strict invalid date rejected
```

### 6.3. `add`, `roll`, and adding milliseconds differ

- `calendar.add(Calendar.DAY_OF_MONTH, 1)` means **adding one day to the calendar field**; across DST, the actual elapsed time may differ from 24 hours.
- `calendar.roll(field, amount)` changes a field within its range **without altering larger fields** according to `roll` rules. Do not use it as ordinary date/month addition.
- `calendar.setTimeInMillis(calendar.getTimeInMillis() + 86_400_000L)` adds **exactly 24 hours** on the epoch timeline, which does not necessarily keep the same local wall-clock time on the next day.

If the requirement is "tomorrow at 12:00 in a region", add **days** in that time zone; if it is "24 hours later", add a **Duration** or milliseconds. These two requirements are different.

## 7. DST: adding one day does not always equal 24 hours

Time zones with **daylight saving time (DST) transition rules** can cause a calendar day to be 23 or 25 real hours long. For example, in `America/New_York`, the spring transition in 2026 occurs in March.

Starting from **12:00 on March 7, 2026** and adding one calendar day, 12:00 on March 8, 2026 is only **23 real hours** away, because the UTC offset changes from `-05:00` to `-04:00`.

Create `CalendarDstDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarDstDemo {
    public static void main(String[] args) {
        ZoneId zoneId = ZoneId.of("America/New_York");
        Calendar calendar = new GregorianCalendar(
                TimeZone.getTimeZone(zoneId), Locale.US);
        calendar.clear();
        calendar.setLenient(false);
        calendar.set(2026, Calendar.MARCH, 7, 12, 0, 0);

        long start = calendar.getTimeInMillis();
        calendar.add(Calendar.DAY_OF_MONTH, 1);
        long end = calendar.getTimeInMillis();

        System.out.println("start: "
                + Instant.ofEpochMilli(start).atZone(zoneId));
        System.out.println("end: "
                + Instant.ofEpochMilli(end).atZone(zoneId));
        System.out.println("elapsed hours: "
                + Duration.ofMillis(end - start).toHours());
    }
}
```

```bash
javac CalendarDstDemo.java
java CalendarDstDemo
```

```text
start: 2026-03-07T12:00-05:00[America/New_York]
end: 2026-03-08T12:00-04:00[America/New_York]
elapsed hours: 23
```

This is the result according to tzdb time zone data for 2026. DST rules can change by legislation and tzdb version, so when a system handles future schedules, you must manage the appropriate timezone data version and test against target regions.

### A UTC offset is not a time zone ID

- `-05:00` and `-04:00` are merely **offsets** at specific points in time.
- `America/New_York` is a **ZoneId** containing rules for offsets over time.
- `TimeZone.getRawOffset()` reflects the base offset and is **insufficient** to determine the effective offset at an instant when DST applies; you can call `getOffset(long epochMillis)` or use `ZoneId.getRules().getOffset(instant)`.
- Do not build timestamps by manually adding a "year-round fixed" offset if the region observes DST.

`java.time` provides distinct operations: `zoned.plusDays(1)` for local calendar days and `instant.plus(Duration.ofHours(24))` for absolute elapsed time. Choose the right business semantics.

## 8. Risk of changing the default `TimeZone` per request

A multi-user system may handle two requests concurrently:

1. A chooses `UTC`, code calls `TimeZone.setDefault(UTC)`.
2. Before A constructs its `Calendar` or formatter, thread B sets `TimeZone.setDefault(Asia/Tokyo)`.
3. A proceeds to read `TimeZone.getDefault()` or `Calendar.getInstance()` and gets `Asia/Tokyo`, violating A's choice.

This is a race condition on **global state**, not merely a statement-ordering bug. It cannot be solved by calling `setDefault` and restoring it in each request's `finally`: two requests can still interleave between them.

### Java 17+ example with explicit ordering

File `DefaultZoneRaceDemo.java`:

```java
import java.util.TimeZone;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class DefaultZoneRaceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        TimeZone before = TimeZone.getDefault();

        CountDownLatch aHasSet = new CountDownLatch(1);
        CountDownLatch bHasSet = new CountDownLatch(1);
        AtomicReference<String> aObserved = new AtomicReference<>();

        Thread a = new Thread(() -> {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
            aHasSet.countDown();
            try {
                bHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            aObserved.set(TimeZone.getDefault().getID());
        });

        Thread b = new Thread(() -> {
            try {
                aHasSet.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }
            TimeZone.setDefault(
                    TimeZone.getTimeZone("Asia/Tokyo"));
            bHasSet.countDown();
        });

        try {
            a.start();
            b.start();
            a.join();
            b.join();
            System.out.println("A expected UTC but read "
                    + aObserved.get());
        } finally {
            TimeZone.setDefault(before);
        }
    }
}
```

```bash
javac DefaultZoneRaceDemo.java
java DefaultZoneRaceDemo
```

```text
A expected UTC but read Asia/Tokyo
```

`CountDownLatch` forces thread B to change the default after A sets it and before A reads it. This is an **experiment reproducing the risk**, not a pattern to use in a server. Restoring in `finally` is only to avoid leaving the process's default configuration altered after the two threads finish. Do not run this experiment concurrently with other tasks relying on the JVM default.

## 9. The right approach with the legacy API: pass `TimeZone` and `Locale`

If a project must use `Calendar`, pass the configuration explicitly:

```java
TimeZone userZone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh");
Locale userLocale = Locale.forLanguageTag("vi-VN");

Calendar calendar = Calendar.getInstance(
        userZone, userLocale);
calendar.setTimeInMillis(epochMillis);
```

This is an **illustrative snippet inside a method**, requiring `import java.util.*;` and an `epochMillis` variable populated from a data source. Notes:

- `userZone` should come from a validated preference or business data, not inferred from `userLocale`.
- `epochMillis` represents the instant; date/time fields are computed in `userZone`.
- Do not change `TimeZone.setDefault(...)` or `Locale.setDefault(...)` when handling requests.
- `Calendar` is mutable and **not thread-safe**; do not share a single `Calendar` object across concurrent requests.
- `DateFormat`/`SimpleDateFormat` are also mutable and not thread-safe. In legacy code, create a dedicated formatter and call `setTimeZone(userZone)` if the API/format requires it, instead of relying on defaults.

### `TimeZone.getTimeZone(String)` can silently fall back

`TimeZone.getTimeZone("Not/A_Zone")` can return **`GMT`** instead of throwing an exception. If the zone sent from a client is invalid, continuing with `GMT` will display the wrong time without surfacing an error.

Create `ZoneValidationDemo.java`:

```java
import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.TimeZone;

public class ZoneValidationDemo {
    public static void main(String[] args) {
        System.out.println("legacy: "
                + TimeZone.getTimeZone("Not/A_Zone").getID());

        try {
            ZoneId.of("Not/A_Zone");
            System.out.println("accepted");
        } catch (DateTimeException ex) {
            System.out.println("invalid ZoneId rejected");
        }

        ZoneId accepted = ZoneId.of("Asia/Ho_Chi_Minh");
        TimeZone legacy = TimeZone.getTimeZone(accepted);
        System.out.println("validated: " + legacy.getID());
    }
}
```

```bash
javac ZoneValidationDemo.java
java ZoneValidationDemo
```

```text
legacy: GMT
invalid ZoneId rejected
validated: Asia/Ho_Chi_Minh
```

**Recommendation:** for externally supplied zones, validate with `ZoneId.of(...)` (optionally combined with an allowlist of supported zones), then convert with `TimeZone.getTimeZone(zoneId)` when calling legacy APIs. Do not validate a zone merely by comparing `getTimeZone(id).getID()` against the input, because aliases/normalized IDs can also affect behavior.

## 10. Other defaults that affect formatters

In the legacy date-time API, `java.text.DateFormat` and `java.text.SimpleDateFormat` can depend on **locale, timezone, and pattern**.

Example:

```java
DateFormat df = DateFormat.getDateTimeInstance(
        DateFormat.MEDIUM, DateFormat.SHORT, userLocale);
df.setTimeZone(userZone);
String text = df.format(date);
```

This is a **code snippet inside a method** with appropriate imports, where `date` is a `java.util.Date` and `userLocale`/`userZone` are already declared. `DateFormat` is created with the passed locale, then explicitly given a time zone before formatting. If you simply call `DateFormat.getDateTimeInstance()` with no arguments, the code depends on the default locale and default time zone at the moment the formatter is constructed.

What to avoid:

```java
// Not suitable for multi-timezone applications:
TimeZone.setDefault(userZone);
Locale.setDefault(userLocale);
String text = DateFormat.getDateTimeInstance().format(date);
```

Although it may occasionally print the right result in a single-user program, this mutates JVM state and can break other requests.

Another trap of `SimpleDateFormat` is that its pattern and internal `Calendar` can be mutated during parsing/formatting; the class is not thread-safe. Do not create a `static` instance to serve all requests concurrently. For new code, prefer `java.time.format.DateTimeFormatter` because it is immutable and thread-safe once created.

## 11. `GregorianCalendar` and the concept of a default calendar

Not every `Calendar.getInstance(...)` call always creates the exact same `GregorianCalendar` type for every locale. Depending on the provider, locale, and calendar-related Unicode extensions (`u-ca-*`), the runtime may choose another calendar system, such as the Buddhist or Japanese calendar. Therefore:

- If business data assumes the **Gregorian/ISO calendar**, declare the calendar system explicitly or move to `java.time.LocalDate`/`LocalDateTime`.
- Do not assume `Calendar.YEAR` always has the same chronological meaning across all calendars.
- Legacy `GregorianCalendar` has a Julian/Gregorian cutover mechanism; this can affect historical dates, unlike the ISO proleptic Gregorian system of `java.time.LocalDate`.
- Week-of-year is also governed by locale configuration (`getFirstDayOfWeek`, `getMinimalDaysInFirstWeek`), so do not treat `Calendar.WEEK_OF_YEAR` as a "global standard week index" without defining the standard.

For ISO 8601 week reporting, Java Time provides `java.time.temporal.IsoFields.WEEK_OF_WEEK_BASED_YEAR` and `WEEK_BASED_YEAR`; for locale-based weeks, there is `WeekFields.of(locale)`. Week calculation and calendar display rules must be agreed upon before implementation.

## 12. Migrating from the legacy API to `java.time`

Java 8+ provides the `java.time` package with immutable objects and clearer separation of roles:

| Legacy API | Java Time choice | Migration notes |
| --- | --- | --- |
| `Date` | `Instant` | `date.toInstant()`, though `Date` precision is milliseconds |
| `TimeZone` | `ZoneId` | `timeZone.toZoneId()` and `TimeZone.getTimeZone(zoneId)` |
| `Calendar` at an instant | `Instant` + `ZoneId` or `ZonedDateTime` | Distinguish the instant from local fields |
| `GregorianCalendar` | `ZonedDateTime`, `LocalDateTime`, `LocalDate` depending on semantics | Not a 1:1 field transfer for all calendar types |
| `SimpleDateFormat` | `DateTimeFormatter` | Patterns look similar but are not fully compatible; check every token |
| `Calendar.getInstance()` | `ZonedDateTime.now(zoneId)` or `Instant.now()` | Pass zone explicitly when local date/time is needed |

A pure Java Time example:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ModernTimeDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-01-01T00:30:00Z");
        ZoneId zone = ZoneId.of("Asia/Tokyo");
        ZonedDateTime local = instant.atZone(zone);

        System.out.println("instant: " + instant);
        System.out.println("local: " + local);
    }
}
```

```bash
javac ModernTimeDemo.java
java ModernTimeDemo
```

```text
instant: 2026-01-01T00:30:00Z
local: 2026-01-01T09:30+09:00[Asia/Tokyo]
```

Migration notes:

- For storing event timestamps, `Instant` is usually clearer. If users need to store a **future appointment at 09:00 in a region**, the model may require `LocalDateTime + ZoneId` and a DST handling policy.
- `LocalDateTime` carries no time zone, so it does not identify an instant on its own.
- When legacy data holds a `Calendar` from a non-Gregorian calendar system, do not assume you can map `YEAR/MONTH/DAY_OF_MONTH` directly to `LocalDate` without knowing the chronology.
- `DateTimeFormatter` is immutable and thread-safe; you still need to pass `Locale` in `withLocale(locale)` and the appropriate `ZoneId` in `withZone(zoneId)` when formatting an `Instant` or data requiring a zone.

## 13. Multi-user design: isolate state per request

Recommended flow:

```text
Request / user profile
       |
       +--> display locale (vi-VN / en-US / ...)
       |
       +--> zone ID (Asia/Ho_Chi_Minh / America/New_York / ...)
       |
       v
Check supported list, determine temporal policy
       |
       +--> Instant or domain time data
       |
       +--> Locale / ZoneId passed explicitly
       |
       v
Formatter, legacy Calendar adapter, or java.time
       |
       v
Response for the right user
```

**Do not conflate information sources:**

- `Accept-Language` does not determine the time zone.
- `TimeZone.getDefault()` does not indicate where the user lives.
- `Locale.getDefault()` does not represent the request's preference.
- Date/time values sent from a client without an offset/zone must be handled according to a defined contract, rather than silently assuming the server's zone.

If a legacy adapter must be kept, create short-lived `Calendar`/`DateFormat` instances per operation from the selected `Locale` and `TimeZone`. Do not pass a mutable `Calendar` across threads; do not mutate JVM defaults as a context-propagation mechanism.

**Multi-zone testing:** pick an instant near UTC midnight, DST transition days, year-end days, and cases where a local wall time is ambiguous. Assert output based on specific `Instant` and `ZoneId` values rather than relying on the CI runner's environment.

## 14. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Calling `Calendar.getInstance()` and treating it as the user's calendar | Uses JVM defaults | Pass zone/locale explicitly |
| Calling `TimeZone.setDefault(userZone)` per request | Race conditions across users | Use `Calendar.getInstance(zone, locale)` or `java.time` |
| Calling `Locale.setDefault(userLocale)` per request | Mutates global config, affects weeks/formatters | Pass `Locale` explicitly |
| Inferring time zone from `Locale("vi","VN")` | Locale does not determine the user's zone | Use preference/ZoneId |
| Using `Calendar.set(2026, 3, 1)` to represent March 1 | `MONTH=3` is April | Use `Calendar.MARCH` or `LocalDate.of(2026,3,1)` |
| Reading `Calendar.HOUR` thinking it is 0–23 | It is a 12-hour value | Use `HOUR_OF_DAY` |
| Setting Feb 30 with default leniency | Normalized into another month | `setLenient(false)` and validation |
| Using `roll` to add days across months | Larger fields do not change as expected | Use `add` or Java Time |
| Adding `24*60*60*1000` to mean "tomorrow" | Wrong on 23/25-hour DST days | Add days in the time zone |
| Using `getRawOffset()` instead of offset at instant | Ignores DST | `getOffset(millis)`/ZoneRules |
| Calling `TimeZone.getTimeZone(invalidId)` without validation | Silently returns `GMT` | Validate with `ZoneId.of(...)` |
| Sharing mutable `SimpleDateFormat`/`Calendar` | Not thread-safe | Separate instances or `java.time` |
| Converting `Date` to string to store an instant | Depends on formatter/locale/zone | Store epoch/ISO timestamp per schema |
| Mixing US and ISO week rules | Wrong week numbers near year-end | Specify WeekFields/IsoFields |
| Changing defaults in parallel tests | Causes flaky test failures | Isolate tests/JVM or avoid mutating defaults |

## 15. Self-check questions

1. **Where does `Calendar.getInstance()` get its time zone and locale?** From the JVM defaults: `TimeZone.getDefault()` and the default FORMAT locale, not automatically from an HTTP request.
2. **Does `TimeZone.setDefault(...)` apply only to a single thread?** No, it changes the shared JVM-wide default.
3. **If a calendar was created with UTC and the JVM default is later changed to Tokyo, does the existing calendar automatically switch to Tokyo?** Not by default; the instance's time zone was already stored.
4. **Why does `Calendar.MONTH` equal to 2 represent March?** Because month indices in `Calendar` start at 0.
5. **Can `Locale.US` and `Locale.FRANCE` give different `getFirstDayOfWeek` values?** Yes: typically Sunday = 1 and Monday = 2.
6. **Why can Feb 30, 2026 turn into Mar 2, 2026?** Because a lenient `Calendar` normalizes out-of-range fields.
7. **Is `add(DAY_OF_MONTH, 1)` equal to adding 86,400,000 milliseconds?** Not necessarily, because a DST day can be 23 or 25 hours long.
8. **Is `TimeZone.getRawOffset()` always the effective offset of a zone at every point in time?** No, DST and historical changes must be considered.
9. **Is `TimeZone.getTimeZone("Not/A_Zone")` guaranteed to throw an error?** No; it typically returns `GMT`, so the source must be validated.
10. **Is `Locale.forLanguageTag("en-US")` enough to determine `America/New_York`?** No, locale and time zone are two independent choices.
11. **Is storing `LocalDateTime` sufficient to represent an absolute instant?** No, it lacks an offset/zone.
12. **Which modern APIs should be preferred for Java 17+ code?** `java.time.Instant`, `ZoneId`, `ZonedDateTime`, `LocalDate`/`LocalDateTime`, and `DateTimeFormatter` according to semantics.
13. **When should `Calendar` be used?** When integrating with legacy systems or APIs that require it; pass time zone/locale explicitly and isolate mutable objects.
14. **How do you write tests independent of the CI machine's time zone?** Use fixed instants and explicit zones/locales, rather than relying on environment defaults.

## References

- [Java SE 21 — Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html): `getInstance`, lenient, add/roll, week fields, and field ranges.
- [Java SE 21 — TimeZone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html): `getDefault`, `setDefault`, `getOffset`, and ID lookup.
- [Java SE 21 — GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html): legacy Gregorian calendar, cutover, and conversions.
- [Java SE 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html): `Category.FORMAT`/`DISPLAY` and default locale.
- [Java SE 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html): locale/time zone dependencies of the legacy formatter.
- [Java SE 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): IANA region validation, time zone rules.
- [Java SE 21 — ZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html): zone, offset, DST, date and time arithmetic.
- [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html): immutable formatting/parsing with explicit locale/zone.
