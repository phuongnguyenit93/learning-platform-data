# Creating `java.time` Values with `of()`, `now()`, `parse()`, and `from()`

## 1. Four factory groups solve four different problems

The types in `java.time` (Java 8+, e.g., this lesson runs on **Java 17+**) are generally **immutable** objects. Instead of modifying an object's state after instantiation, you create a new value via **static factory** methods and use that result. Four method names appear most frequently:

| Method | Data source | Question to answer | Example |
|---|---|---|---|
| `of(...)` | Known components | "I have year, month, day, hour...; how do I create a value?" | `LocalDate.of(2024, 2, 29)` |
| `now(...)` | System clock or `Clock` | "What is the date/time value at execution time?" | `LocalDate.now(clock)` |
| `parse(...)` | Text string in a defined format | "Which date/time does this string represent?" | `LocalDate.parse("2024-02-29")` |
| `from(...)` | `TemporalAccessor` or compatible temporal object | "I want to extract matching temporal fields from an existing value" | `LocalDate.from(dateTime)` |

**Not every type provides all four names.** For instance, `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`, and `ZonedDateTime` all have the corresponding factories, whereas `Instant` is created from an epoch via `ofEpochSecond(...)` or `ofEpochMilli(...)`, and from a string via `parse(...)`. `Year`, `YearMonth`, and `MonthDay` also have their own factories. Read the API signature of the target type rather than assuming every type has the same overload list.

This lesson distinguishes between **choosing the data type**, **choosing the input source**, **value precision**, and **time zone context**. Once you understand these four points, choosing a factory becomes much simpler.

## 2. Choose the right type before creating

`java.time` does not have a single type representing all temporal information:

| Type | Information contained | Not self-contained | Commonly used factories |
|---|---|---|---|
| `LocalDate` | Year–month–day in the ISO calendar | Time, offset, time zone | `of`, `now`, `parse`, `from` |
| `LocalTime` | Hour–minute–second–nanosecond | Date, offset, time zone | `of`, `now`, `parse`, `from` |
| `LocalDateTime` | Local date and time | Offset and `ZoneId` | `of`, `now`, `parse`, `from` |
| `OffsetDateTime` | Date–time + fixed UTC offset | Regional time zone rules | `of`, `now`, `parse`, `from` |
| `ZonedDateTime` | Date–time + `ZoneId` and resolved offset | Not a drop-in replacement for `Instant` | `of`, `now`, `parse`, `from` |
| `Instant` | Absolute point on the timeline | Local date/time without an attached zone | `now`, `parse`, `from`, `ofEpochSecond` |
| `YearMonth` | Year and month | Specific day | `of`, `now`, `parse`, `from` |
| `MonthDay` | Month and day, without a year | Specific year | `of`, `now`, `parse`, `from` |

For example, a **birth date** typically uses `LocalDate`; **store opening hours** use `LocalTime`; an **event log timestamp** uses `Instant`; an **appointment tied to a city** uses `ZonedDateTime` with the appropriate zone. There is no need to add an offset to a birth date just to be able to create it with `now()`.

In Java's ISO model, `LocalDate` uses the proleptic Gregorian calendar (*proleptic Gregorian*). The factories validate input: `LocalDate.of(2023, 2, 29)` is rejected because 2023 is not a leap year.

## 3. `of()`: creating from known components

### 3.1. `LocalDate.of(...)`, `LocalTime.of(...)`, `LocalDateTime.of(...)`

When the components are already determined by business data, use `of(...)` to express the intent directly:

~~~java
LocalDate date = LocalDate.of(2024, 2, 29);
LocalTime time = LocalTime.of(9, 5, 7);
LocalDateTime meeting = LocalDateTime.of(date, time);
~~~

The first line holds **2024-02-29**; the second is **09:05:07**; the third is **2024-02-29T09:05:07**. The `T` is the date-and-time separator in ISO representation. `LocalDateTime.of(2024, 2, 29, 9, 5, 7)` can also be used if all components are available in a single call.

Common overloads:

- `LocalDate.of(year, month, dayOfMonth)` or `LocalDate.of(year, Month.FEBRUARY, dayOfMonth)`.
- `LocalTime.of(hour, minute)`, `of(hour, minute, second)`, `of(hour, minute, second, nanoOfSecond)`.
- `LocalDateTime.of(year, month, dayOfMonth, hour, minute, ...)` or `of(LocalDate, LocalTime)`.
- `YearMonth.of(2024, 2)` describes an entire month; `MonthDay.of(2, 29)` describes a month/day without a specific year.

Java constrains components by type: month 1–12, hour 0–23, minute/second normally 0–59, nanosecond 0–999999999. Invalid values throw `DateTimeException` immediately upon creation. Do not expect `LocalTime.of(25, 0)` to auto-normalize to 01:00 the next day; to add hours, create a valid time first and use an operation like `plusHours(...)` with appropriate semantics.

### 3.2. Adding an offset or `ZoneId` at the right time

A local time **does not identify a global instant** without knowing the offset/time zone. You can create:

~~~java
LocalDateTime local = LocalDateTime.of(2024, 2, 29, 9, 5, 7);
OffsetDateTime offset = OffsetDateTime.of(local, ZoneOffset.ofHours(7));
ZonedDateTime zoned =
        ZonedDateTime.of(local, ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

On the illustrated date, both have offset `+07:00`, but the information they carry is **different**: `OffsetDateTime` holds a fixed offset; `ZonedDateTime` holds the region identity and looks up regional rules when needed. For example, in time zones that observe daylight saving time, a date/time in a **gap** may not exist; `ZonedDateTime.of(local, zone)` typically adjusts the time forward past the gap. A time in an **overlap** has two valid offsets and the API chooses according to default rules; for business logic requiring an exact choice, inspect `ZoneRules.getValidOffsets(local)` and use an explicit factory/handling.

For **an already-known `Instant`**, the way to convert it to a time zone is `instant.atZone(zone)`, which differs in meaning from attaching a time zone to an unresolved `LocalDateTime`.

### 3.3. `Instant` has the `ofEpoch...` group

`Instant` does not accept year/month/day via `of(year, month, day)`. It creates an instant from the UTC epoch:

~~~java
Instant epoch = Instant.ofEpochSecond(0);       // 1970-01-01T00:00:00Z
Instant next = Instant.ofEpochMilli(1_500);     // 1970-01-01T00:00:01.500Z
LocalDate epochDate = LocalDate.ofEpochDay(0);  // 1970-01-01
~~~

**Epoch seconds/milliseconds of `Instant`** differ from **epoch days of `LocalDate`**. The two creation calls use two different units. Do not pass milliseconds to `ofEpochSecond`: the value will be off by a factor of 1,000. Also, do not interpret `LocalDate.ofEpochDay(0)` as a point in time at 00:00 in every time zone.

### 3.4. Standalone runnable example for `of()`

Save as **`OfDemo.java`**:

~~~java
import java.time.*;

public class OfDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 2, 29);
        LocalTime time = LocalTime.of(9, 5, 7);
        LocalDateTime local = LocalDateTime.of(date, time);
        OffsetDateTime offset = OffsetDateTime.of(
                local, ZoneOffset.ofHours(7));
        ZonedDateTime zoned = ZonedDateTime.of(
                local, ZoneId.of("Asia/Ho_Chi_Minh"));
        Instant epoch = Instant.ofEpochSecond(0);

        System.out.println("Date: " + date);
        System.out.println("Time: " + time);
        System.out.println("Local: " + local);
        System.out.println("Offset: " + offset);
        System.out.println("Zoned: " + zoned);
        System.out.println("Epoch: " + epoch);

        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected");
        }
    }
}
~~~

~~~bash
javac OfDemo.java
java OfDemo
~~~

Stdout output in a JDK using the time zone rules for `Asia/Ho_Chi_Minh` as of the example date:

~~~text
Date: 2024-02-29
Time: 09:05:07
Local: 2024-02-29T09:05:07
Offset: 2024-02-29T09:05:07+07:00
Zoned: 2024-02-29T09:05:07+07:00[Asia/Ho_Chi_Minh]
Epoch: 1970-01-01T00:00:00Z
Invalid date rejected
~~~

`ZonedDateTime` values use the JDK's time zone rule data; for certain regions and historical dates, this data may differ across tzdb versions. For unit tests independent of that data source, choose `ZoneOffset.UTC` or a static offset when appropriate for the requirements.

## 4. `now()`: reading the clock at runtime

`now()` with no arguments is a request for **the current moment**. The result depends on the clock and the time zone context:

~~~java
LocalDate date = LocalDate.now();
LocalTime time = LocalTime.now();
LocalDateTime local = LocalDateTime.now();
Instant instant = Instant.now();

LocalDate inTokyo = LocalDate.now(ZoneId.of("Asia/Tokyo"));
~~~

Overloads to remember:

| Call | Clock/zone used | Testability |
|---|---|---|
| `LocalDate.now()` | System clock, JVM default time zone | Depends on environment and run date |
| `LocalDate.now(zone)` | System clock, date computed in `zone` | Still depends on real time |
| `LocalDate.now(clock)` | Clock and zone contained in `clock` | Can be fixed |
| `LocalDateTime.now(clock)` | Selected clock; converted to local date/time via clock's zone | Can be fixed |
| `Instant.now(clock)` | Instant provided by `clock` | Can be fixed; zone does not change the instant itself |

`ZoneId.systemDefault()` is a system configuration, **not always UTC**. A program running on CI/CD, a developer machine, and a server in different time zones can produce different dates when calling `LocalDate.now()`. `Instant.now()` represents an instant; when called with two clocks having the **same instant**, the resulting `Instant` values are equal even if the clocks use different zones.

### 4.1. Using `Clock` to control `now()` in tests

`Clock` is the standard way to avoid depending on wall-clock time. `Clock.fixed(instant, zone)` freezes a single instant in the chosen zone. Standalone runnable example, save as **`NowDemo.java`**:

~~~java
import java.time.*;

public class NowDemo {
    public static void main(String[] args) {
        Instant fixedInstant = Instant.parse("2024-02-29T23:30:00Z");

        Clock utc = Clock.fixed(fixedInstant, ZoneOffset.UTC);
        Clock hcm = Clock.fixed(
                fixedInstant, ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("UTC date: " + LocalDate.now(utc));
        System.out.println("HCM date: " + LocalDate.now(hcm));
        System.out.println("HCM local: " + LocalDateTime.now(hcm));
        System.out.println("Instant: " + Instant.now(hcm));
    }
}
~~~

~~~bash
javac NowDemo.java
java NowDemo
~~~

Fixed stdout for the chosen instant and zones:

~~~text
UTC date: 2024-02-29
HCM date: 2024-03-01
HCM local: 2024-03-01T06:30
Instant: 2024-02-29T23:30:00Z
~~~

**Why is UTC still in February while HCM is already in March?** Because the same instant `23:30Z` with a `+07:00` offset is **06:30 the next day**. This is the fundamental difference between a local date and an `Instant`.

In application code, you can **inject `Clock` via the constructor** instead of calling no-argument `now()` everywhere:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

public final class DateProvider {
    private final Clock clock;

    public DateProvider(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate today() {
        return LocalDate.now(clock);
    }
}
~~~

The `DateProvider` snippet is a separate class: save it in **`DateProvider.java`** when compiling. Production can pass `Clock.system(ZoneId.of("Asia/Ho_Chi_Minh"))` or `Clock.systemUTC()` as required; tests pass `Clock.fixed(...)`. Choosing the zone is a business decision, not a default assumption that "UTC is always right" for every `LocalDate`.

### 4.2. Common pitfalls with `now()`

- Using `LocalDate.now()` for log timestamps: a date cannot store hours/minutes/seconds or exact ordering; choose `Instant.now(clock)` when you need a point in time.
- Calling `now()` twice on two lines around a minute/day boundary and assuming the same time snapshot: they can diverge. Capture one `Instant` or one `now(clock)` result as the reference for the operation and derive related values from it.
- Relying on the server's time zone when checking expiration dates/deadlines: specify the business zone explicitly.
- Writing tests that expect today's date to be fixed: use `Clock.fixed`, rather than relying on the real clock or mutating global machine settings.

## 5. `parse()`: converting text into temporal values

`parse()` decodes **structured strings**. It does not mean "try every kind of date string"; each type uses a default ISO formatter or a formatter passed by the caller.

~~~java
LocalDate date = LocalDate.parse("2024-02-29");
LocalTime time = LocalTime.parse("09:05:07");
LocalDateTime local = LocalDateTime.parse("2024-02-29T09:05:07");
OffsetDateTime offset =
        OffsetDateTime.parse("2024-02-29T09:05:07+07:00");
Instant instant = Instant.parse("2024-02-29T02:05:07Z");
~~~

The calls above have different semantics:

- `LocalDate.parse` creates a date, **without attaching a time zone**.
- `LocalDateTime.parse` reads date–time parts, **without carrying an offset**; the `T` in the ISO example is the required separator for that format.
- `OffsetDateTime.parse` requires an offset in the input under the default formatter.
- `ZonedDateTime.parse` can read a zone id and offset, e.g., `2024-02-29T10:15:30+07:00[Asia/Ho_Chi_Minh]`; the zone id can carry regional rules.
- `Instant.parse` reads an instant. `Z` represents UTC; local date-time data lacks enough information to become an `Instant`.

**Example of a data-type mismatch error:** `LocalDateTime.parse("2024-02-29T09:05:07+07:00")` with its default ISO formatter does not represent an offset as a field of `LocalDateTime`. When the input has an offset, parse into `OffsetDateTime` first and only call `toLocalDateTime()` if you intentionally want to discard the offset.

### 5.1. Parsing custom formats with `DateTimeFormatter`

When a user enters `29/02/2024`, the default ISO formatter of `LocalDate.parse(String)` does not understand the `dd/MM/uuuu` format. You must pass an explicit formatter:

~~~java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu")
        .withResolverStyle(ResolverStyle.STRICT);

LocalDate value = LocalDate.parse("29/02/2024", formatter);
~~~

**Why use `uuuu`?** In `DateTimeFormatter` patterns:

| Symbol | Meaning | Consequence |
|---|---|---|
| `u` | Proleptic year, including year 0 or negative years | Suitable for ISO dates and strict parsing |
| `y` | Year of era | In `STRICT`, missing the era may not provide enough data to build a `LocalDate` |
| `Y` | Week-based-year | Easy to get wrong at year start/end if confused with calendar year |
| `M` | Month of year | Different from minute |
| `m` | Minute of hour | Different from month |
| `d` | Day of month | Different from day of year (`D`) |

`ResolverStyle.STRICT` rejects nonexistent dates; `SMART` may adjust certain invalid end-of-month dates; `LENIENT` allows broader normalization. A formatter created with `DateTimeFormatter.ofPattern(...)` defaults to `SMART` resolver style, so if business logic requires exact date validation, set `STRICT` and use the appropriate fields. Formatters are immutable and safe to reuse across threads.

Complete example, save as **`ParseDemo.java`**:

~~~java
import java.time.*;
import java.time.format.*;

public class ParseDemo {
    public static void main(String[] args) {
        DateTimeFormatter vn = DateTimeFormatter
                .ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT);

        LocalDate iso = LocalDate.parse("2024-02-29");
        LocalDate custom = LocalDate.parse("29/02/2024", vn);
        OffsetDateTime offset = OffsetDateTime.parse(
                "2024-02-29T10:15:30+07:00");
        Instant instant = offset.toInstant();

        System.out.println("Same date: " + iso.equals(custom));
        System.out.println("Parsed date: " + custom);
        System.out.println("Instant: " + instant);

        try {
            LocalDate.parse("31/02/2024", vn);
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid date text rejected");
        }
    }
}
~~~

~~~bash
javac ParseDemo.java
java ParseDemo
~~~

Stdout:

~~~text
Same date: true
Parsed date: 2024-02-29
Instant: 2024-02-29T03:15:30Z
Invalid date text rejected
~~~

The `+07:00` part makes local `10:15:30` correspond to `03:15:30Z`. `DateTimeParseException` is a subclass of `DateTimeException`, containing details about the unparseable data. When reporting input errors in an API, return a safe, helpful message to the user; do not arbitrarily swallow the exception and substitute the current date.

### 5.2. Built-in formatters and supported domains

| Formatter | Example | Purpose |
|---|---|---|
| `ISO_LOCAL_DATE` | `2024-02-29` | ISO date without offset |
| `BASIC_ISO_DATE` | `20240229` | Basic ISO date format |
| `ISO_LOCAL_DATE_TIME` | `2024-02-29T10:15:30` | Local date and time |
| `ISO_OFFSET_DATE_TIME` | `2024-02-29T10:15:30+07:00` | Date and time with offset |
| `ISO_ZONED_DATE_TIME` | `2024-02-29T10:15:30+07:00[Asia/Ho_Chi_Minh]` | Date and time with zone |
| `ISO_INSTANT` | `2024-02-29T03:15:30Z` | Instant |
| `ISO_WEEK_DATE` | `2020-W53-5` | ISO week-based year, week, and day of week |
| `ISO_ORDINAL_DATE` | `2024-060` | Day of year |

Do not concatenate strings manually to replace a formatter when you need to support negative years, years above 9999, locales, offsets, or optional fields. Built-in formatters have clear semantics and help avoid case-sensitivity mistakes in patterns.

## 6. `from()`: extracting from `TemporalAccessor`

`TemporalAccessor` is an interface that provides read access to temporal fields (`ChronoField`) and compatible queries. Many `java.time` types implement this interface; `DateTimeFormatter.parse(String)` also returns a `TemporalAccessor`.

The `from(TemporalAccessor)` factory **does not parse directly from a `String`**. It attempts to obtain the required fields from an existing temporal object and construct the target type. The difference from `of()` is that you **do not pass individual components**; from `parse()`, you **do not pass a string** to `from()`.

### 6.1. Extracting date, time, and instant from the same offset input

Save as **`FromDemo.java`**:

~~~java
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.TemporalAccessor;

public class FromDemo {
    public static void main(String[] args) {
        TemporalAccessor parsed =
                DateTimeFormatter.ISO_OFFSET_DATE_TIME.parse(
                        "2024-02-29T10:15:30+07:00");

        LocalDate date = LocalDate.from(parsed);
        LocalTime time = LocalTime.from(parsed);
        OffsetDateTime dateTime = OffsetDateTime.from(parsed);
        Instant instant = Instant.from(parsed);

        System.out.println("Date: " + date);
        System.out.println("Time: " + time);
        System.out.println("Offset: " + dateTime);
        System.out.println("Instant: " + instant);

        try {
            LocalDate.from(Instant.parse("2024-02-29T03:15:30Z"));
        } catch (DateTimeException ex) {
            System.out.println("Instant has no local date by itself");
        }

        LocalDate utcDate = instant.atZone(ZoneOffset.UTC).toLocalDate();
        System.out.println("UTC date: " + utcDate);
    }
}
~~~

~~~bash
javac FromDemo.java
java FromDemo
~~~

Stdout:

~~~text
Date: 2024-02-29
Time: 10:15:30
Offset: 2024-02-29T10:15:30+07:00
Instant: 2024-02-29T03:15:30Z
Instant has no local date by itself
UTC date: 2024-02-29
~~~

The same `TemporalAccessor` containing an offset and date-time can produce multiple views: `LocalDate`, `LocalTime`, `OffsetDateTime`, or `Instant`. However, a **pure `Instant`** does not know which time zone it is being displayed in, so `LocalDate.from(instant)` fails. To obtain a date, you must choose a zone explicitly: `instant.atZone(zone).toLocalDate()` or `LocalDate.ofInstant(instant, zone)`.

### 6.2. Using `from()` in generic code

When an API accepts a `TemporalAccessor`, you can request the target type:

~~~java
static LocalDate extractDate(TemporalAccessor temporal) {
    return LocalDate.from(temporal);
}
~~~

This is only **an illustrative method**; it needs to be placed inside a Java class and import `java.time.LocalDate` and `java.time.temporal.TemporalAccessor` if you want to compile it. It works when `temporal` has enough ISO date information; otherwise, `DateTimeException` is the expected result.

Passing a converter to a formatter:

~~~java
LocalDate date = DateTimeFormatter.ISO_LOCAL_DATE
        .parse("2024-02-29", LocalDate::from);
~~~

The expression `LocalDate::from` acts as a `TemporalQuery<LocalDate>`. This can be shortened to `LocalDate.parse("2024-02-29")` when the input is simply an ISO string and you do not need to keep the intermediate `TemporalAccessor`.

Several conversions look similar but **are not completely interchangeable**:

- `LocalDate.from(localDateTime)`: extracts the date part, discarding the time.
- `LocalTime.from(localDateTime)`: extracts the time part, discarding the date.
- `Instant.from(offsetDateTime)`: uses date, time, and offset to determine the instant.
- `LocalDate.from(instant)`: lacks zone context, so it fails.
- `OffsetDateTime.from(localDateTime)`: lacks an offset, so it fails.
- `ZonedDateTime.from(zonedDateTime)`: obtains the same zone/instant information per the source's representation, when supported by the source.

**Do not use `from()` as a Java type cast** like `(LocalDate) temporal`; the actual object might be an `OffsetDateTime` or a formatter parse result, not a `LocalDate`. `from()` requests field extraction, whereas a cast only checks whether the object has the same runtime type.

## 7. Four ways to create the same date, with different meanings

Suppose you need the date **2024-02-29**:

~~~java
LocalDate explicit = LocalDate.of(2024, 2, 29);
LocalDate parsed = LocalDate.parse("2024-02-29");
LocalDate extracted = LocalDate.from(
        LocalDateTime.of(2024, 2, 29, 12, 0));
LocalDate fromClock = LocalDate.now(Clock.fixed(
        Instant.parse("2024-02-29T12:00:00Z"),
        ZoneOffset.UTC));
~~~

All four variables have **equal `LocalDate` values**, but their origins are different:

| Variable | Where does the value come from? | Appropriate when |
|---|---|---|
| `explicit` | Validated literal/configuration components | Scheduling for a specific date |
| `parsed` | String received via API/file/input | Converting text input |
| `extracted` | Existing `LocalDateTime` | Extracting a date from a temporal object |
| `fromClock` | Clock provided by the application | Current date in a controllable environment/zone |

In real applications, do not use `now()` to "recover" a historical date from a string, and do not parse a `toString()` string when you already have a suitable typed temporal object to extract fields from.

### 7.1. Quick selection diagram

~~~text
Need to create a date/time value
          |
          +-- Already have year/month/day/hour components? --> of(...)
          |
          +-- Need time from the current clock? -------------> now(clock/zone)
          |
          +-- Input source is a String? ---------------------> parse(text, formatter?)
          |
          +-- Already have a TemporalAccessor? --------------> from(temporal)
          |
          +-- Source is an epoch or Instant? ----------------> ofEpoch... / atZone(...) / ofInstant(...)
~~~

This diagram is a guide for choosing common factories; some types provide other methods such as `atStartOfDay(zone)`, `ofInstant(instant, zone)`, `atOffset(offset)`, or `atZone(zone)`. Prefer the method that conveys the exact semantics rather than forcing every transformation into one of these four names.

## 8. Common mistakes and how to fix them

### 8.1. Using the wrong time zone

**Wrong intent:** `LocalDate.now()` in a system calculating promotion dates in Vietnam time when the JVM runs in UTC. **Fix:** `LocalDate.now(clock)` with a clock configured for `Asia/Ho_Chi_Minh`, or `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` for a simple operation. In tests, use `Clock.fixed`.

### 8.2. Assuming `LocalDateTime` always pinpoints an instant

`LocalDateTime.of(2024, 2, 29, 10, 0)` **does not by itself identify an `Instant`**. Attaching a `+07:00` offset yields a different instant than attaching `Z`. Attaching a `ZoneId` via `atZone(zone)` applies regional rules, including DST gaps/overlaps. To know the instant, you need a resolved offset/zone.

### 8.3. Using the wrong formatter pattern or missing strict validation

`LocalDate.parse("29/02/2024")` does not automatically recognize arbitrary day/month orders. Use `DateTimeFormatter.ofPattern("dd/MM/uuuu").withResolverStyle(ResolverStyle.STRICT)`. Do not confuse `MM` (month) with `mm` (minute), or `yyyy` (year of era) with `uuuu` (proleptic year) and `YYYY` (ISO week-based year).

### 8.4. Using `from()` when fields are missing

`Instant` is a point in time and does not carry a local date; `LocalDate.from(instant)` cannot pick a time zone on its own and throws an error. **Fix:** `instant.atZone(zone).toLocalDate()`. Similarly, `OffsetDateTime.from(localDateTime)` does not guess an offset; you must provide an offset or `ZoneId` according to business rules.

### 8.5. Using `now()` in tests or across multiple independent steps

Two calls to `now()` can fall at two different moments. When processing a transaction, capture `Instant timestamp = Instant.now(clock)` once and derive date/time representations from it. Using a fixed clock in tests keeps them deterministic.

### 8.6. Swallowing invalid-input exceptions

`of(...)` can throw `DateTimeException`; `parse(...)` can throw `DateTimeParseException`; `from(...)` can throw `DateTimeException` when the source lacks information. Do not silently replace errors with "today", as this easily corrupts data. Validate input at system boundaries and return a meaningful error.

### 8.7. Confusing immutable objects with self-updating objects

`LocalDate.of(...)`, `LocalDate.now(...)`, and `LocalDate.parse(...)` produce immutable values. Calling `date.plusDays(1)` **returns a different `LocalDate`**; it does not mutate the original `date` object. `now()` also does not make a `LocalDate` variable automatically change with the clock after it has been created.

## 9. Applying this in code design

An API that accepts a **calendar date** should take a `LocalDate` after the input has been parsed and validated, avoiding passing date strings deep into the business layer. An API that records **when an event occurred** should accept an `Instant` or a `Clock` for testability. An API that reuses **temporal objects** may accept `TemporalAccessor` when it genuinely needs to support multiple input types, but it must document which fields are required.

Example of a service that computes a deadline seven calendar days from the current date:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

public final class DeadlineService {
    private final Clock clock;

    public DeadlineService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public LocalDate deadlineAfterDays(long days) {
        return LocalDate.now(clock).plusDays(days);
    }
}
~~~

Save this standalone class in **`DeadlineService.java`**. Production injects `Clock.system(zone)`, while tests inject `Clock.fixed(instant, zone)`. For deadlines calculated in **calendar days**, `plusDays` expresses the intent more accurately than rigidly adding `days * 86400` seconds to a timestamp and then converting time zones.

If you need to parse a date string into a deadline, parse it at the input layer:

~~~java
LocalDate specifiedDate =
        LocalDate.parse("2024-02-29", DateTimeFormatter.ISO_LOCAL_DATE);
~~~

This is an illustrative snippet placed inside a method/class that imports `java.time.LocalDate` and `java.time.format.DateTimeFormatter`. There is no need for `from()` when the input is already a plain ISO date string.

## 10. Self-check

**Q1.** Given year, month, and day passed separately from three API fields, should you use `of()`, `parse()`, or `now()`?  
**Answer:** `LocalDate.of(year, month, day)`. Use `parse()` if the source is a formatted string; use `now()` when you need the current date.

**Q2.** Why can `LocalDate.now()` differ between a developer's machine and a CI machine at the same instant?  
**Answer:** Because the JVMs have different default time zones, resulting in different local dates. Use an explicitly chosen `Clock` or `ZoneId`.

**Q3.** Which factory should be used to read `29/02/2024`?  
**Answer:** `LocalDate.parse(text, DateTimeFormatter.ofPattern("dd/MM/uuuu").withResolverStyle(ResolverStyle.STRICT))`.

**Q4.** Why is `LocalDate.from(Instant.now())` not a valid conversion?  
**Answer:** `Instant` does not provide a local date without a zone. Use `instant.atZone(zone).toLocalDate()` (or `LocalDate.ofInstant(instant, zone)`).

**Q5.** Given an `OffsetDateTime`, how do you get the date, and how do you get the absolute point in time?  
**Answer:** `offsetDateTime.toLocalDate()` or `LocalDate.from(offsetDateTime)` for the date; `offsetDateTime.toInstant()` or `Instant.from(offsetDateTime)` for the instant. The two results contain different information.

**Q6.** In a unit test, if the system date must always be `2024-02-29` UTC, how do you create it?  
**Answer:** `Clock.fixed(Instant.parse("2024-02-29T12:00:00Z"), ZoneOffset.UTC)`, then `LocalDate.now(clock)`.

## 11. Key takeaways

- **`of()`**: creates from known components; validates ranges and validity.
- **`now()`**: obtains a value from a clock; explicitly choose a zone when you need a local date/time, and use `Clock.fixed` for testing.
- **`parse()`**: converts a string using ISO or a custom formatter; ensure the right pattern and validation mode.
- **`from()`**: extracts fields from a `TemporalAccessor`; succeeds only if the source has enough data for the target type.
- **Choose the right type first**: `LocalDate` for calendar dates, `LocalDateTime` for local date-times, `OffsetDateTime`/`ZonedDateTime` when an offset/zone is present, and `Instant` for instants. The same string or point in time can yield different representations depending on the information provided.
