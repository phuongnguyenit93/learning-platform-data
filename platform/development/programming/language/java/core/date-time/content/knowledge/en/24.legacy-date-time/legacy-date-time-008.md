# Converting Date with Instant, Calendar with ZonedDateTime

## 1. Type conversion must start from data meaning

A legacy library returns `java.util.Date`; new business logic uses `Instant`. Another library requires `Calendar`, while the application holds `ZonedDateTime`. Conversion methods bridge the two API generations, but they do not guarantee that every piece of information passes through intact.

Before writing code, answer: does the data represent **an instant in time**, **a date-time in a time zone**, or just **a calendar date**? Then determine the precision and which configurations truly belong to the contract.

| Type | Primary information | Conversion-related characteristics |
| --- | --- | --- |
| `java.util.Date` | An instant in time, millisecond precision | Mutable via `setTime`; does not carry its own time-zone ID |
| `Instant` | An instant on the timeline | Immutable; can carry a nanosecond part |
| `Calendar` | Instant and calendar fields along with calendar/time-zone configuration | Mutable; an abstract class |
| `GregorianCalendar` | An implementation of `Calendar` | Has a direct bridge to `ZonedDateTime` |
| `ZonedDateTime` | Date-time in the ISO calendar, with resolved time zone and offset | Immutable; can carry a nanosecond part |

For example, `2024-06-15T03:20:30.123Z` and `2024-06-15T10:20:30.123+07:00[Asia/Ho_Chi_Minh]` describe the same instant. The first value does not itself carry the information that the user is viewing the time in Vietnam. That information is added when choosing a zone.

After this lesson, you should be able to use the official bridges, explain the conditions under which a round trip preserves data, and write tests according to the exact quantities that must be preserved.

## 2. Why is a clear conversion boundary needed?

If business logic accepts and passes `Date` everywhere, a distant `setTime` call can change a value held elsewhere. If each class picks `systemDefault()` on its own for conversion, local time ends up depending on the deployment machine.

A manageable way to organize this is to convert data right at the library boundary:

```text
Input from legacy API
      ↓ validate contract, null, and actual runtime type
Appropriate java.time type
      ↓ business logic processing
Convert to legacy type when required by output API
```

For transaction timestamps, `Instant` usually expresses the need accurately. When local-time display or processing is required, attach an explicitly chosen `ZoneId`. If the data is only a birth date, do not invent a time of day and time zone and claim it is an inherent instant.

Object conversion should be performed directly. Taking a detour to "format into a string and parse back" adds dependencies on format patterns, locale, and time zone, even though the problem itself does not require text.

## 3. Date → Instant: extracting the existing instant

For a standard `java.util.Date` object:

```java
Instant instant = legacyDate.toInstant();
```

If `legacyDate.getTime()` equals `1_718_421_630_123L`, the result preserves the exact instant represented by that millisecond count. The conversion does not require choosing a `ZoneId`, because both `Date` and `Instant` represent an instant.

An equivalent expression at millisecond precision can be written as:

```java
Instant instant = Instant.ofEpochMilli(legacyDate.getTime());
```

This is useful when the contract actually passes epoch millis. Do not multiply by 1,000: `Date.getTime()` already uses milliseconds, whereas `Instant.ofEpochSecond(...)` takes seconds.

`Date.toInstant()` and `Date.from(Instant)` are bridges introduced in Java 8. The contract is specified in [Java SE 21 Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html#toInstant()).

### 3.1 No need to "subtract seven hours" when converting

A common mistake is receiving a `Date`, seeing `toString()` display Vietnam time, and subtracting seven hours before calling `toInstant()`. Doing so shifts the instant.

The display string may depend on the time zone used for presentation; it does not prove that `Date` itself stored a "wrong local time that needs fixing". Compare using `getTime()` or `Instant` when investigating an instant.

If the input data was previously interpreted under the wrong time zone, fix it at that interpretation step according to the original contract. A correct type conversion cannot guess and repair an offset error introduced by an earlier ingestion step.

### 3.2 The result is an independent value

After obtaining an `Instant`, modifying the `Date` via `setTime(...)` does not modify the created `Instant`. Conversely, creating a new `Date` from an `Instant` and modifying that `Date` does not alter the `Instant`.

This makes the conversion boundary a place to snapshot the value. However, do not read a legacy object while another thread is mutating it without coordination; immutability of the result does not automatically make reading the source safe against concurrent mutation.

## 4. Instant → Date: accepting the millisecond limit

Use the standard method:

```java
Date legacyDate = Date.from(instant);
```

For `instant = 2024-06-15T03:20:30.123456789Z`, `Date` only retains up to milliseconds. Converting back yields:

```text
2024-06-15T03:20:30.123Z
```

This truncates the sub-millisecond part rather than rounding up to `.124`. If you need to compare after a round trip, define the expected contract first:

```java
Instant expected = instant.truncatedTo(ChronoUnit.MILLIS);
boolean ok = Date.from(instant).toInstant().equals(expected);
```

The example above requires importing `java.time.temporal.ChronoUnit` and assumes `instant` is within the range of `Date`.

### 4.1 Be careful with instants before the epoch

Consider `1969-12-31T23:59:59.999999999Z`, just one nanosecond before the epoch. After converting to `Date`, the epoch millis value is `-1`, not `0`; when converted back, the result is `1969-12-31T23:59:59.999Z`.

Do not compute this manually by taking a negative total nanosecond count and integer-dividing by one million assuming it follows the same rule. Integer division can truncate toward 0, causing an off-by-one error on negative values. Use the standard method instead of reimplementing the conversion.

`Instant.toEpochMilli()` can throw `ArithmeticException` if the value cannot be represented as a `long`. The precision and range contract is described in [Java SE 21 Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#toEpochMilli()).

### 4.2 Not every Instant can be converted

The range of `Instant` is wider than the epoch-millis range of `Date`. `Date.from(...)` rejects out-of-range values with `IllegalArgumentException`. In addition to checking for `null`, a conversion layer that accepts very distant instants needs a range-error policy.

In modern business data, range limits occur less often than losing nanoseconds, but they are two distinct issues. Do not use a single test in the year 2024 to conclude that every valid `Instant` can be converted.

## 5. Calendar → ZonedDateTime: two paths

### 5.1 When you have a GregorianCalendar

This class has a direct method:

```java
ZonedDateTime modern = gregorianCalendar.toZonedDateTime();
```

This path converts the instant to the ISO calendar system and uses the source calendar's time zone. It does not require manually copying year, month, day, and hour fields.

You should not reconstruct it using `ZonedDateTime.of(calendar.get(YEAR), ...)` just to convert an existing instant. Doing so makes it easy to get the month index wrong, drop milliseconds, and reinterpret local time in zones with repeated hours.

### 5.2 When the variable is only typed as Calendar

`Calendar` has `toInstant()`, but does not declare `toZonedDateTime()`. Use the instant and time zone:

```java
Instant instant = calendar.toInstant();
ZoneId zone = calendar.getTimeZone().toZoneId();
ZonedDateTime modern = instant.atZone(zone);
```

`Calendar.toInstant()` and converting `TimeZone` to `ZoneId` provide a bridge without casting every `Calendar` to `GregorianCalendar`. See [Calendar.toInstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html#toInstant()) and [TimeZone.toZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html#toZoneId()).

Going through `Instant` preserves the instant and then views it in the ISO calendar at that zone. It does not preserve another calendar system of a `Calendar` subclass, nor does it automatically copy week rules.

If the target requirement wants a different zone from the source, specify the target zone explicitly:

```java
ZonedDateTime utc = calendar.toInstant().atZone(ZoneId.of("UTC"));
```

The instant is still preserved; the local hour value may change. If you want to keep the wall-clock hour and change the zone, that is a different business requirement, which requires constructing a new instant and resolving nonexistent or overlapping times.

### 5.3 Calendar must represent a valid instant

A calendar in strict (non-lenient) mode may hold an invalid combination of fields from earlier `set(...)` calls. Conversion will need to compute the instant and may surface the error. Do not treat the bridge as a tool that automatically fixes invalid fields.

Objects should be validated when received. If legacy data intentionally relies on lenient mode, normalization is part of the contract that must be understood before converting.

## 6. ZonedDateTime → Calendar: the method lives on GregorianCalendar

Use:

```java
GregorianCalendar legacy = GregorianCalendar.from(modern);
Calendar requiredByOldApi = legacy;
```

The concrete return type is `GregorianCalendar`, which can be passed anywhere a `Calendar` is expected. There is no corresponding `Calendar.from(ZonedDateTime)` method.

During conversion, the instant is truncated to millisecond precision. For standard commonly used zones, the time zone is bridged via `TimeZone`. Verify ID mapping if using custom zones or fixed offsets with second-level precision against the target JDK/API; do not assume every representation capability of `java.time` has an equivalent in every legacy environment.

`GregorianCalendar.from(...)` creates a proleptic Gregorian calendar, with Monday as the first day of the week and four minimal days in the first week per ISO. Its job is not to restore the configuration of an earlier `Calendar` object. Inputs exceeding the legacy calendar's representable range can throw `IllegalArgumentException`. See [GregorianCalendar.from and toZonedDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html#from(java.time.ZonedDateTime)).

If the legacy API requires a specific week configuration or leniency mode, apply that configuration after conversion and test against the API's requirements. Do not turn it into a hidden assumption of every conversion.

## 7. Round trips: specify at what level "preserved" is meant

There are at least four different levels of comparison:

| Quantity to check | Appropriate way to check |
| --- | --- |
| Exact same instant | Compare the two `Instant` values |
| Same instant at millisecond precision | Compare epoch millis or `Instant` truncated per contract |
| Observed zone preserved | Compare `ZoneId`, or rules/offset if the contract allows equivalent IDs |
| Full legacy calendar configuration preserved | Separately check lenient mode, week rules, calendar system, and cutover point |

A `GregorianCalendar` converted to `ZonedDateTime` and back may preserve epoch millis while `equals` still returns `false`. For example, the source calendar uses Sunday as the first day of the week and strict mode; the calendar built from the modern type uses a different configuration.

Similarly, two `ZonedDateTime` values can share the same `Instant` while having different zones. If a test only compares display strings or only compares the date, it may miss contract information that needs to be preserved.

### 7.1 Historical dates can change calendar labels

A default `GregorianCalendar` uses the Julian/Gregorian cutover in 1582, whereas `ZonedDateTime` uses the ISO calendar following proleptic Gregorian rules into the past. Therefore, conversion can preserve the instant while changing the displayed year/month/day for historical data.

Do not copy date fields to "fix it back to match" when the goal is to preserve the instant. If the real goal is to preserve a historical date label in the source calendar system, a dedicated data model and calendar-system conversion rules are needed.

## 8. Complete verification program

The following program uses fixed values and an explicitly specified zone. It checks bidirectional conversion, loss of sub-millisecond precision, pre-epoch cases, independence from legacy objects, and configuration differences after a round trip.

Save as `LegacyTimeBridgeDemo.java` and run with Java 17 or later:

```text
javac --release 17 LegacyTimeBridgeDemo.java
java LegacyTimeBridgeDemo
```

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class LegacyTimeBridgeDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Instant precise = Instant.parse("2024-06-15T03:20:30.123456789Z");
        Instant millisPrecision = precise.truncatedTo(ChronoUnit.MILLIS);
        Date oldDate = Date.from(precise);
        Instant returned = oldDate.toInstant();
        check(returned.equals(millisPrecision), "Date millisecond precision");
        check(!returned.equals(precise), "sub-millisecond part lost");
        check(oldDate.getTime() == precise.toEpochMilli(), "same epoch millis");
        System.out.println("instant-original=" + precise);
        System.out.println("date-round-trip=" + returned);

        oldDate.setTime(0);
        check(returned.equals(millisPrecision), "Instant is independent");
        System.out.println("date-after-mutation=" + oldDate.toInstant());
        System.out.println("snapshot-after-mutation=" + returned);

        Date anotherDate = Date.from(returned);
        check(anotherDate.toInstant().equals(returned), "exact Date round trip");
        Instant beforeEpoch = Instant.parse("1969-12-31T23:59:59.999999999Z");
        Date oldBeforeEpoch = Date.from(beforeEpoch);
        check(oldBeforeEpoch.getTime() == -1L, "negative epoch millis");
        check(oldBeforeEpoch.toInstant().equals(
                beforeEpoch.truncatedTo(ChronoUnit.MILLIS)), "negative precision");
        System.out.println("before-epoch-millis=" + oldBeforeEpoch.getTime());
        System.out.println("before-epoch-returned=" + oldBeforeEpoch.toInstant());

        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = precise.atZone(vietnam);
        GregorianCalendar oldCalendar = GregorianCalendar.from(zoned);
        check(oldCalendar.toInstant().equals(millisPrecision), "calendar precision");
        check(oldCalendar.getTimeZone().toZoneId().equals(vietnam), "zone retained");
        check(oldCalendar.get(Calendar.MONTH) == Calendar.JUNE, "month index");
        ZonedDateTime zonedReturned = oldCalendar.toZonedDateTime();
        check(zonedReturned.equals(millisPrecision.atZone(vietnam)), "zoned result");
        System.out.println("zoned-original=" + zoned);
        System.out.println("calendar-round-trip=" + zonedReturned);

        Calendar generic = oldCalendar;
        ZonedDateTime genericReturned = generic.toInstant()
                .atZone(generic.getTimeZone().toZoneId());
        check(genericReturned.equals(zonedReturned), "generic Calendar bridge");
        ZonedDateTime utcView = generic.toInstant().atZone(ZoneId.of("UTC"));
        check(utcView.toInstant().equals(genericReturned.toInstant()), "same instant");
        check(utcView.getHour() == 3, "UTC hour");
        check(genericReturned.getHour() == 10, "Vietnam hour");
        System.out.println("generic-path-matches=" + genericReturned.equals(zonedReturned));
        System.out.println("utc-view=" + utcView);

        GregorianCalendar configured = new GregorianCalendar(
                TimeZone.getTimeZone(vietnam), Locale.ROOT);
        configured.setTimeInMillis(millisPrecision.toEpochMilli());
        configured.setLenient(false);
        configured.setFirstDayOfWeek(Calendar.SUNDAY);
        configured.setMinimalDaysInFirstWeek(1);
        GregorianCalendar rebuilt = GregorianCalendar.from(
                configured.toZonedDateTime());
        boolean sameMillis = configured.getTimeInMillis()
                == rebuilt.getTimeInMillis();
        boolean equalCalendars = configured.equals(rebuilt);
        check(sameMillis, "same millis after rebuilding");
        check(!equalCalendars, "configuration differs");
        check(rebuilt.getFirstDayOfWeek() == Calendar.MONDAY, "ISO first weekday");
        check(rebuilt.getMinimalDaysInFirstWeek() == 4, "ISO first week");
        check(rebuilt.getGregorianChange().getTime() == Long.MIN_VALUE,
                "pure Gregorian calendar");
        System.out.println("rebuilt-same-millis=" + sameMillis);
        System.out.println("rebuilt-calendar-equals=" + equalCalendars);

        Instant snapshot = configured.toInstant();
        configured.add(Calendar.DAY_OF_MONTH, 1);
        check(snapshot.equals(millisPrecision), "calendar snapshot independent");
        check(!configured.toInstant().equals(snapshot), "calendar changed");
        System.out.println("calendar-snapshot=" + snapshot);

        boolean rangeRejected = false;
        try {
            Date.from(Instant.MAX);
        } catch (IllegalArgumentException expected) {
            rangeRejected = true;
        }
        check(rangeRejected, "Date range checked");
        System.out.println("date-range-rejected=" + rangeRejected);
        System.out.println("PASS");
    }
}
```

Output:

```text
instant-original=2024-06-15T03:20:30.123456789Z
date-round-trip=2024-06-15T03:20:30.123Z
date-after-mutation=1970-01-01T00:00:00Z
snapshot-after-mutation=2024-06-15T03:20:30.123Z
before-epoch-millis=-1
before-epoch-returned=1969-12-31T23:59:59.999Z
zoned-original=2024-06-15T10:20:30.123456789+07:00[Asia/Ho_Chi_Minh]
calendar-round-trip=2024-06-15T10:20:30.123+07:00[Asia/Ho_Chi_Minh]
generic-path-matches=true
utc-view=2024-06-15T03:20:30.123Z[UTC]
rebuilt-same-millis=true
rebuilt-calendar-equals=false
calendar-snapshot=2024-06-15T03:20:30.123Z
date-range-rejected=true
PASS
```

The `check` helper explicitly throws `AssertionError`, so enabling `-ea` is not required. The program prints `Instant` and `ZonedDateTime` rather than using `Date.toString()`, which depends on default time-zone formatting.

In particular, `rebuilt-calendar-equals=false` does not indicate an incorrect instant conversion: the preceding line already confirmed that the epoch millis are identical. It illustrates the loss/change of configuration when converting through a type that does not carry all source calendar settings.

## 9. Date names that are easily confused

In this lesson, `Date` mainly refers to standard `java.util.Date`. JDBC has other classes that extend it but follow different contracts.

### 9.1 java.sql.Date is an SQL date

`java.sql.Date.toInstant()` always throws `UnsupportedOperationException`, because SQL `DATE` represents a date without a time component according to the type's contract. Use `toLocalDate()` and, in the reverse direction, `java.sql.Date.valueOf(localDate)` for date-only data.

Even when a variable is declared as `java.util.Date`, an actual `java.sql.Date` instance still invokes the overridden method. Therefore, a function that "accepts any `Date` and calls `toInstant()`" should be reviewed if data comes from JDBC. See [java.sql.Date.toInstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html#toInstant()).

Do not use `Instant.ofEpochMilli(sqlDate.getTime())` just to dodge the exception and treat it as a semantically valid SQL date conversion. It introduces assumptions about an instant that date-only data may never have defined.

### 9.2 Timestamp can hold nanoseconds

`java.sql.Timestamp` supports a nanosecond component and has its own `toInstant()` / `from(Instant)` methods. Do not automatically downgrade every `Timestamp` to `new java.util.Date(timestamp.getTime())` if the contract requires higher than millisecond precision. See [Java SE 21 Timestamp](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Timestamp.html#toInstant()).

With databases, you must also understand the column type, driver, and data time-zone contract. The bridges in this lesson do not determine the meaning of an SQL column based solely on a Java class name.

## 10. Common mistakes and deliberate fixes

| Mistake | Why it is wrong or error-prone | How to fix |
| --- | --- | --- |
| Format `Date` to a string then parse into `Instant` | Adds unnecessary pattern, locale, and time-zone rules | Call `toInstant()` when the data type is appropriate |
| Subtract/add an offset to "convert Date to UTC" | Alters the already-existing instant | Convert directly; only choose a zone for presentation |
| Use `ofEpochSecond(date.getTime())` | Confuses milliseconds with seconds | Use `ofEpochMilli` |
| Call `calendar.toZonedDateTime()` | Method does not belong to `Calendar` | Use `toInstant().atZone(...)` or an actual `GregorianCalendar` |
| Cast every `Calendar` to `GregorianCalendar` | The runtime class may differ | Use the general path if only instant and zone are needed |
| Compare exact nanoseconds after going through `Date` | Target only retains milliseconds | Check according to the agreed precision |
| Compare only `Calendar.equals` when checking the instant | Configuration also participates in equality | Compare `toInstant()` or epoch millis |
| Use the machine's default time zone for all source calendars | Can change the business zone | Preserve the source zone or specify the target zone explicitly |
| Convert `java.sql.Date` as a timestamp | Violates the SQL date contract; may throw an exception | Use `LocalDate` for date-only contracts |

For `null`, choose a clear policy: reject at the boundary, use `Optional` if appropriate, or represent missing values per an agreed convention. Do not turn `null` into "now" or the epoch unless the contract asks for it; doing so produces data that looks valid but has the wrong meaning.

## 11. Practice exercises

### Exercise 1 — Choosing the right bridge

A method returns a `java.util.Date` representing a payment time. The business logic only needs the chronological order of events, not local-time display yet. Choose the target type and conversion method.

**Solution hint:** use `Instant` and call `date.toInstant()`. No time zone needs to be chosen at this step. If the source could be a JDBC subclass, verify the type and contract first.

### Exercise 2 — Finding the precision loss bug

A test takes `Instant.parse("2024-01-01T00:00:00.000000001Z")`, converts it to `Date` and back to `Instant`, and then checks exact equality. Why does it fail?

**Solution hint:** one nanosecond cannot be represented in `Date`'s milliseconds. The result becomes `2024-01-01T00:00:00Z`. The test must assert truncation according to the contract, or require the system to use a target type that preserves nanoseconds.

### Exercise 3 — Checking negative values

Predict the epoch millis when converting `1969-12-31T23:59:59.999999999Z` to `Date`.

**Solution hint:** `-1`. Add tests for the exact epoch and one millisecond before the epoch; this group of values catches hand-rolled integer-division bugs in the negative range.

### Exercise 4 — Preserving the source zone

You have a `Calendar` variable in the `Asia/Ho_Chi_Minh` time zone and want to preserve this zone in the modern result. Write the expression without casting.

**Solution hint:** `calendar.toInstant().atZone(calendar.getTimeZone().toZoneId())`. Ensure the source is not mutated concurrently while reading the instant and zone. If the contract requires a consistent snapshot under multithreading, use the chosen ownership/synchronization mechanism.

### Exercise 5 — Defining round-trip conditions

A strict source calendar with Sunday as the first day of the week is converted to `ZonedDateTime` and back via `GregorianCalendar.from(...)`. `equals` returns `false`. Can you conclude that the instant changed?

**Solution hint:** not yet. Compare epoch millis separately. Then check week configuration, leniency, and the calendar cutover point. Distinguish instant-data failures from configuration differences.

### Exercise 6 — Distinguishing date from instant

A `java.sql.Date` value represents a birth date. Should you wrap it into a `java.util.Date` to call `toInstant()`?

**Solution hint:** no, when the requirement is date-only. Choose `toLocalDate()`. If the system must convert a date into an instant, it must additionally define a time zone and a time of day; that is an additional business decision.

## 12. Criteria for proper application

A good conversion clearly identifies the actual source type, data meaning, required time zone, and any precision that may be lost. Tests should verify the instant, zone, and configuration according to each separate requirement.

When bridging legacy and modern APIs, use the direct conversion methods and place them at the integration boundary. For standard `Date`/legacy calendars, an instant at millisecond precision is the common baseline; any stricter preservation requirement must be explicitly specified and tested.
