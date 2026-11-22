# Calendar, GregorianCalendar, and TimeZone

## 1. The Model to Grasp Before Reading Legacy Code

A legacy system receives “09:00 on 31/01/2024 in Vietnam”. To turn this information into an instant that can be stored or compared, the program needs both calendar date-time fields and time-zone rules. In Java's legacy API group, the following three classes participate in that work:

| Component | Responsibility | Question It Helps Answer |
| --- | --- | --- |
| `Calendar` | Abstract class that converts between an instant in milliseconds from the epoch and a set of fields such as year, month, day, hour | “What calendar fields does this instant have, and how do we modify them?” |
| `GregorianCalendar` | A concrete implementation of `Calendar`, with Julian/Gregorian calendar rules | “According to which calendar are month lengths and leap years determined?” |
| `TimeZone` | Represents a time zone, its offset, and daylight saving time rules if any | “At this instant, how much does local time differ from UTC?” |

A `Calendar` object combines an instant, calendar fields, and configuration such as time zone, week rules, and data validation mode. Therefore, looking at a single `YEAR` or `HOUR_OF_DAY` value is not enough to understand the entire object. The conversion role of `Calendar` is described in [Java SE 21 Calendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html).

Mental model example: at the same instant `2024-01-31T02:00:00Z`, a clock in the `Asia/Ho_Chi_Minh` time zone reads 09:00. When changing the observation view to UTC while keeping the instant, the time read becomes 02:00. No seven hours elapsed during that time-zone change.

After this lesson, you should be able to read code that uses `Calendar` fields, proactively validate invalid dates, distinguish `set`, `add`, and `roll`, and place the conversion to `java.time` right at the boundary where your code interfaces with legacy libraries.

## 2. Why Still Learn This API Group?

In new code, types such as `LocalDate`, `Instant`, and `ZonedDateTime` express intent more clearly. However, many long-lived libraries, data contracts, and programs still use `Date`, `Calendar`, `GregorianCalendar`, and `TimeZone`. Reading and understanding them helps you fix bugs in a controlled way and write conversion layers without altering data semantics.

`Calendar`, `GregorianCalendar`, and `TimeZone` do not mean “the entire API has been marked deprecated”. This is a legacy API group; some methods on `Date` being deprecated is a separate matter. When modifying code, check the exact method being used.

One easy-to-manage way to draw the boundary is:

```text
Legacy library returns Calendar/Date
          ↓ convert immediately at input
Instant or appropriate java.time type
          ↓ business logic processing
Convert back to legacy type when required by output contract
```

For example, a transaction's timestamp fits `Instant`. A local appointment needs to preserve appropriate time-zone information. A birth date only needs a calendar date; forcing it into a `Calendar` and picking 00:00 in an arbitrary time zone can introduce assumptions that do not belong to the original data.

## 3. Initialization and Reading Fields: Avoiding Implicit Assumptions

### 3.1 Calendar Is an Abstract Type

You can obtain an instance via `Calendar.getInstance(zone, locale)`. When you need to be certain you are using `GregorianCalendar` rules, instantiate that class directly. Do not write code that casts every `Calendar.getInstance()` result to `GregorianCalendar`: the calendar type can also depend on the locale configuration.

```java
TimeZone zone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh");
GregorianCalendar calendar = new GregorianCalendar(zone, Locale.ROOT);
calendar.clear();
calendar.setLenient(false);
calendar.set(2024, Calendar.JANUARY, 31, 9, 0, 0);
calendar.set(Calendar.MILLISECOND, 0);
long epochMillis = calendar.getTimeInMillis();
```

This snippet assumes the corresponding `java.util` classes are imported. The complete program is in the runnable demonstration section.

The constructor initializes the object to the current time. `clear()` resets all fields to an unset state, ensuring that building new data does not carry over fields from a previous use. Then we explicitly set the input components we need. `clear()` does not clear the time-zone configuration and does not mean “set every field to 0”; when computing the instant, the calendar class supplies default values for unset fields.

Explicitly setting milliseconds to 0 in the example makes the intent of second-level precision clear. After calling `clear()`, the unset millisecond field of `GregorianCalendar` also defaults to 0.

### 3.2 Do Not Use One Numbering Rule for Every Field

| Field in GregorianCalendar | How to Interpret |
| --- | --- |
| `MONTH` | January is `JANUARY = 0`, December is `DECEMBER = 11` |
| `DAY_OF_MONTH` | Day of month starts at 1 |
| `DAY_OF_WEEK` | Uses constants `SUNDAY` through `SATURDAY`; Sunday has value 1 |
| `HOUR_OF_DAY` | Hour in 24-hour clock, from 0 to 23 |
| `HOUR` | Hour in 12-hour clock, from 0 to 11; must be considered together with `AM_PM` |
| `MILLISECOND` | Millisecond fraction within the second, from 0 to 999 |

Write `Calendar.JANUARY` instead of the number 0 in inputs. When displaying the month as a conventional number, use `calendar.get(Calendar.MONTH) + 1`. Do not add 1 to `DAY_OF_MONTH`.

For example, 15:00 has `HOUR_OF_DAY = 15`, whereas `HOUR = 3` and `AM_PM = PM`. If you read `HOUR` and ignore `AM_PM`, afternoon data easily turns into morning data.

For `DAY_OF_WEEK`, do not take its numeric value and pass it directly to `DayOfWeek.of(...)`: `java.time.DayOfWeek` numbers Monday as 1. Convert through modern date types or map using constant names to avoid mixing up conventions.

### 3.3 Locale and Time Zone Have Different Effects

A time zone converts between an instant and local time. A locale can affect which calendar is selected by factory methods and week configuration such as the first day of the week and the minimal days in the first week. Choosing a Vietnam locale does not automatically substitute for choosing `Asia/Ho_Chi_Minh`.

In this lesson, `Locale.ROOT` keeps the example configuration explicit and independent of the machine's default locale. We do not infer ISO weeks from this locale. If legacy code needs ISO weeks with `GregorianCalendar`, you must check `firstDayOfWeek`, `minimalDaysInFirstWeek`, and the week-based year.

## 4. `set` Does Not Guarantee the Data Is Valid

### 4.1 Lenient Mode Can Adjust Out-of-Range Dates

By default, a new calendar uses a permissive mode called `lenient`. In this mode, an out-of-range value can be normalized. For instance, January 32 becomes February 1.

This is useful when legacy code intentionally expresses offsets using out-of-range fields. However, with user input, silently turning “31/02” into March often hides input errors.

```java
calendar.clear();
calendar.setLenient(false);
calendar.set(2024, Calendar.FEBRUARY, 31, 0, 0, 0);
calendar.getTimeInMillis(); // IllegalArgumentException
```

The key point is on the last line: `set(...)` records the fields, while interpreting them into an instant can happen lazily. `getTimeInMillis()`, `getTime()`, or reading a field can trigger computation and detect errors. Therefore, putting `try/catch` only around `set(...)` may not catch an invalid date.

For input that requires strict validation, set `setLenient(false)` and proactively call `getTimeInMillis()` within the same error-handling scope. When computation fails, do not continue treating the object as holding a validated date. For each attempt, you can create a new object or clear and re-set all fields.

### 4.2 Order of Operations Matters

Suppose a calendar is currently at 31/01/2024. Calling `set(MONTH, FEBRUARY)` creates the field combination “February 31” before recomputing. In lenient mode, if you read the instant immediately, the result may roll into March. If you then set the day to 29 before reading, the input combination is different again.

Consequently, a logging statement calling `getTime()` between two `set(...)` calls can cause normalization to happen earlier than a reader expects. The safe approach is to populate all fields upfront and validate in one clear place. Lazy computation and normalization rules are explained in [Calendar: Field Manipulation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html#field-manipulation).

## 5. `set`, `add`, and `roll` Answer Three Different Needs

All three mutate the object itself. If you need to keep the original, make a copy before operating on it.

| Call from 31/01/2024 | Meaning to Understand | Result in Example |
| --- | --- | --- |
| `set(DAY_OF_MONTH, 1)` | Assigns the day field to a specific value | 01/01/2024 |
| `add(DAY_OF_MONTH, 1)` | Adds one calendar day; allows month rollover | 01/02/2024 |
| `roll(DAY_OF_MONTH, 1)` | Wraps the day field within the current month | 01/01/2024 |
| `add(MONTH, 1)` | Adds one month and clamps the day to a valid value | 29/02/2024 |

The `roll` example shows that even though the day field increases, the month does not advance as with `add`. Do not use `roll` to compute “tomorrow”. For other fields, the effect on smaller fields requires reading the specific contract; do not extrapolate from one day-of-month example into a simple rule for all fields.

From 31/01, adding one month yields 29/02 in leap year 2024. If you then add another month, the result is 29/03; the original day 31 is not automatically remembered. If business logic requires “always the last day of the month”, express that rule explicitly.

Calendar day addition should also not be replaced by adding `86_400_000L` milliseconds. In places with daylight saving time transitions, a local day may not be exactly 24 hours long. Whether you want to advance by a calendar day or by elapsed duration is a choice that must be decided before writing the calculation.

## 6. TimeZone: Region IDs, Offsets, and Configuration Pitfalls

### 6.1 Prefer Explicit Region IDs

`Asia/Ho_Chi_Minh` and `America/New_York` are region IDs. A region's offset is determined by the instant and the rule data provided by the JDK. A fixed configuration such as `GMT+07:00` only expresses a fixed offset; it does not carry the same historical semantics as a region ID.

Abbreviations such as `CST` are ambiguous across regions. Use full region IDs when business requirements call for local time at a specific location.

A memorable trap: `TimeZone.getTimeZone(String)` can return GMT when it does not recognize the given ID. For example, a typo like `Asia/Ho_Chi_Min` can silently shift the time. The GMT fallback behavior and the difference between raw offset and offset at an instant are documented in [Java SE 21 TimeZone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html).

When input configuration uses region IDs supported by `java.time`, you can validate them first:

```java
ZoneId zoneId = ZoneId.of(configuredZoneId);
TimeZone legacyZone = TimeZone.getTimeZone(zoneId);
```

`ZoneId.of(...)` rejects invalid IDs or IDs without corresponding rules by throwing an exception instead of silently returning GMT. This is a validation choice for configurations following the `ZoneId` contract; do not automatically assume every legacy custom syntax is equivalent. See [ZoneId.of](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html#of(java.lang.String)).

### 6.2 `getRawOffset` Differs from `getOffset(epochMillis)`

`getRawOffset()` does not include daylight saving time adjustments. `getOffset(epochMillis)` returns the offset in effect at the given instant. Both return values in milliseconds.

In the test later in this lesson, New York at `2024-07-01T12:00:00Z` has an offset of -4 hours; the raw offset in the test JDK data is -5 hours. If you use the raw offset to compute summer time, the result is off by one hour. Do not treat this result as a rule guarantee for all future years: time-zone data also depends on the JDK/TZDB version.

Similarly, changing the ID via `TimeZone.setID(...)` does not reload the rules of the new time zone. When you need a different time zone, obtain the proper `TimeZone` from a validated ID.

### 6.3 Does Changing the Time Zone Preserve the Instant?

If a `Calendar` already holds a valid instant, changing its time zone with `setTimeZone(...)` lets you read local fields in the new time zone while preserving that instant. For example, 09:00 in Vietnam becomes 02:00 UTC.

If the requirement is “keep 09:00 on the wall clock and move the appointment to another time zone”, that is a different operation: you must take the local fields and construct a new instant according to the target time zone's rules, while deciding how to handle nonexistent or repeated local times. Do not use changing the time-zone configuration as a stand-in for this requirement.

## 7. GregorianCalendar and Historical Boundaries

The name `GregorianCalendar` can mislead readers into thinking every date follows an infinitely extended Gregorian calendar. The default configuration actually has a cutover point: Julian before it, Gregorian from it onward; the default cutover is October 15, 1582 (Gregorian). This is the API's transition model, not a claim that every country switched calendars on the same day.

`LocalDate` and `ZonedDateTime` use the ISO calendar with proleptic Gregorian rules extending into the past. For modern dates in our examples, this difference does not change date labels. For historical records, the same instant converted to a different calendar system can have a different date label.

`GregorianCalendar.toZonedDateTime()` preserves the instant and uses the ISO calendar system in the result. Conversely, `GregorianCalendar.from(zdt)` creates a proleptic Gregorian calendar with ISO week configuration; it does not automatically restore every original calendar property. The contract is described in [GregorianCalendar: Conversion and Cutover](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html).

If data requires proleptic Gregorian while you still must use the legacy class, you can configure `setGregorianChange(new Date(Long.MIN_VALUE))`. Only do this when that is the chosen rule for the data. Do not silently change the cutover date during a routine bug fix because it can alter how historical dates are interpreted.

## 8. Runnable Demonstration

The following program uses fixed dates and times, explicit time zones, and does not read the current clock to produce business results. It checks 0-based months, strict validation, `add`/`roll` operations, time-zone switching, and bridging to `java.time`.

Save as `LegacyCalendarDemo.java`, compile, and run with Java 17 or later:

```text
javac --release 17 LegacyCalendarDemo.java
java LegacyCalendarDemo
```

```java
import java.util.Calendar;
import java.util.Date;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRulesException;

public class LegacyCalendarDemo {
    private static GregorianCalendar create(
            int year, int month, int day, int hour, TimeZone zone) {
        GregorianCalendar c = new GregorianCalendar(zone, Locale.ROOT);
        c.clear();
        c.setLenient(false);
        c.set(year, month, day, hour, 0, 0);
        c.set(Calendar.MILLISECOND, 0);
        c.getTimeInMillis();
        return c;
    }

    private static String date(Calendar c) {
        return String.format(Locale.ROOT, "%04d-%02d-%02d",
                c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1,
                c.get(Calendar.DAY_OF_MONTH));
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        TimeZone vietnam = TimeZone.getTimeZone(
                ZoneId.of("Asia/Ho_Chi_Minh"));
        GregorianCalendar original = create(
                2024, Calendar.JANUARY, 31, 9, vietnam);

        System.out.println("month-index=" + original.get(Calendar.MONTH));
        System.out.println("original=" + date(original));
        check(original.get(Calendar.MONTH) == 0, "January index");

        GregorianCalendar added = (GregorianCalendar) original.clone();
        added.add(Calendar.DAY_OF_MONTH, 1);
        GregorianCalendar rolled = (GregorianCalendar) original.clone();
        rolled.roll(Calendar.DAY_OF_MONTH, 1);
        GregorianCalendar nextMonth = (GregorianCalendar) original.clone();
        nextMonth.add(Calendar.MONTH, 1);
        check(date(added).equals("2024-02-01"), "add day");
        check(date(rolled).equals("2024-01-01"), "roll day");
        check(date(nextMonth).equals("2024-02-29"), "add month");
        check(date(original).equals("2024-01-31"), "original unchanged");
        System.out.println("add-day=" + date(added));
        System.out.println("roll-day=" + date(rolled));
        System.out.println("add-month=" + date(nextMonth));

        GregorianCalendar invalid = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        invalid.clear();
        invalid.setLenient(false);
        invalid.set(2024, Calendar.FEBRUARY, 31, 0, 0, 0);
        boolean rejected = false;
        try {
            invalid.getTimeInMillis();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "invalid date rejected");
        System.out.println("strict-rejected=" + rejected);

        GregorianCalendar normalized = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        normalized.clear();
        normalized.setLenient(true);
        normalized.set(2024, Calendar.JANUARY, 32, 0, 0, 0);
        check(date(normalized).equals("2024-02-01"), "lenient date");
        System.out.println("lenient=" + date(normalized));

        long millis = original.getTimeInMillis();
        GregorianCalendar utcView = (GregorianCalendar) original.clone();
        utcView.setTimeZone(TimeZone.getTimeZone("UTC"));
        check(utcView.getTimeInMillis() == millis, "same instant");
        check(utcView.get(Calendar.HOUR_OF_DAY) == 2, "UTC hour");
        System.out.println("utc-hour=" + utcView.get(Calendar.HOUR_OF_DAY));
        System.out.println("instant=" + Instant.ofEpochMilli(millis));

        Date oldDate = original.getTime();
        ZonedDateTime modern = original.toZonedDateTime();
        GregorianCalendar restored = GregorianCalendar.from(modern);
        check(oldDate.toInstant().equals(modern.toInstant()), "Date bridge");
        check(restored.getTimeInMillis() == millis, "round trip millis");
        check(modern.getZone().equals(vietnam.toZoneId()), "zone bridge");
        System.out.println("bridge-instant=" + modern.toInstant());

        String unknown = "Invalid/DefinitelyMissing";
        check(TimeZone.getTimeZone(unknown).getID().equals("GMT"),
                "legacy fallback");
        boolean zoneRejected = false;
        try {
            ZoneId.of(unknown);
        } catch (ZoneRulesException expected) {
            zoneRejected = true;
        }
        check(zoneRejected, "unknown zone rejected");
        System.out.println("unknown-zone="
                + TimeZone.getTimeZone(unknown).getID());
        System.out.println("modern-zone-rejected=" + zoneRejected);

        TimeZone newYork = TimeZone.getTimeZone(
                ZoneId.of("America/New_York"));
        long summer = Instant.parse("2024-07-01T12:00:00Z").toEpochMilli();
        int offsetHours = newYork.getOffset(summer) / 3_600_000;
        int rawHours = newYork.getRawOffset() / 3_600_000;
        check(offsetHours == -4, "summer offset");
        check(rawHours == -5, "raw offset in test JDK");
        System.out.println("new-york-summer-offset=" + offsetHours);
        System.out.println("new-york-raw-offset=" + rawHours);
        System.out.println("PASS");
    }
}
```

Output:

```text
month-index=0
original=2024-01-31
add-day=2024-02-01
roll-day=2024-01-01
add-month=2024-02-29
strict-rejected=true
lenient=2024-02-01
utc-hour=2
instant=2024-01-31T02:00:00Z
bridge-instant=2024-01-31T02:00:00Z
unknown-zone=GMT
modern-zone-rejected=true
new-york-summer-offset=-4
new-york-raw-offset=-5
PASS
```

The clones in the program let each test start from the same original date. The `check` helper throws `AssertionError` directly, so the program does not depend on the `-ea` flag. Converting to `Instant` for printing output also avoids depending on the default time zone when calling `Date.toString()`.

## 9. Converting While Preserving Semantics

### 9.1 Calendar to Instant

For any valid `Calendar`, use `calendar.toInstant()` or `Instant.ofEpochMilli(calendar.getTimeInMillis())`. If you also need to preserve the observation zone, get `calendar.getTimeZone().toZoneId()` and call `instant.atZone(zoneId)`.

`toZonedDateTime()` is a method on `GregorianCalendar`. Do not call it on a variable declared as `Calendar` or perform an unchecked cast just to convert; going through `Instant` is usually enough for a timestamp value.

### 9.2 Date Does Not Carry Its Own Time Zone

`calendar.getTime()` returns a `Date` representing an instant in milliseconds. The calendar's time zone is not packaged as a separate zone property inside `Date`. When you need to preserve the time zone for an appointment, pass or store the zone information via another contract.

`Date.toInstant()` converts that instant to the modern type. The official conversion methods are documented in [Java SE 21 Date](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html#toInstant()).

### 9.3 The Return Path Can Lose Precision and Configuration

`GregorianCalendar` stores instants to millisecond precision; `ZonedDateTime` can represent nanoseconds. If you convert a value with a sub-millisecond fraction to `GregorianCalendar`, that fraction is not preserved. The test above starts with exact milliseconds, so comparing round-trip milliseconds is appropriate.

Having the same instant does not mean all properties of the two calendars are equal. `GregorianCalendar.from(...)` also chooses calendar and week settings according to its contract. Do not use a single round-trip conversion as proof that `lenient`, the Julian/Gregorian cutover, and all old settings are restored.

## 10. Mutable State and Ownership Scope

`Calendar` and `TimeZone` have methods that mutate state. Do not share a mutable calendar object as a shared variable and let multiple threads concurrently call `set`, `add`, and `getTime` without coordination.

A practical convention is for each operation to own its own legacy object and convert to immutable `java.time` values upon entering internal processing. If an API receives a caller's `Calendar` and needs to modify fields, consider copying it first and documenting the contract clearly.

Even a `get` call can trigger computation of pending fields. Therefore, treating it as “just reading an independent number” overlooks this class's state model.

Do not mutate the JVM-wide default time zone to fix a single business case. Passing the time-zone configuration to the exact object that needs it makes the operation's requirements explicit in code and avoids affecting other parts of the application.

## 11. Exercises and Suggested Solutions

### Exercise 1 — Fixing a Month Bug

A method wants to construct 10/01/2024 and calls `calendar.set(2024, 1, 10)`. Which month is the result in `GregorianCalendar`?

**Suggested solution:** 1 is February. Change it to `Calendar.JANUARY`. If input from a UI numbers months 1–12, validate the range first and then convert to the API convention at the data-ingestion boundary.

### Exercise 2 — Catching Errors in the Right Place

A snippet calls `setLenient(false)`, sets February 31, exits the `try` block, and then calls `getTime()` to save. Why can an exception still occur outside the expected scope?

**Suggested solution:** computation can be deferred until the instant is read. Put both field setup and `getTimeInMillis()` inside the error-handling scope. Only proceed to the save step after validation succeeds.

### Exercise 3 — Checking Addition Operations

Starting from 31/12/2024, predict `add(DAY_OF_MONTH, 1)` and `roll(DAY_OF_MONTH, 1)`.

**Suggested solution:** `add` yields 01/01/2025. Rolling the day within December yields 01/12/2024. Write two separate clones and check year, month, and day to clearly see which parts change.

### Exercise 4 — Detecting Misconfigured Time Zones

An application receives `Asia/Ho_Chi_Min` and passes it directly to `TimeZone.getTimeZone(...)`. No exception is thrown, yet the computed instant is off by seven hours. What should you check?

**Suggested solution:** check whether the returned ID is GMT due to a misspelled name. For configurations using `ZoneId` region names, validate with `ZoneId.of(...)` before creating `TimeZone`. Do not blame the server's clock or data just because the method did not throw an exception.

### Exercise 5 — Choosing Which Quantity to Preserve

You convert a 09:00 schedule in Vietnam to UTC. Requirement A is to preserve the transaction instant; requirement B is to keep the appointment at 09:00 in the new location. Are they implemented the same way?

**Suggested solution:** A preserves epoch millis, so reading the UTC hour gives 02:00 in the example. B keeps the local date-time fields and constructs a new instant in the target zone; it also requires a rule for handling nonexistent or repeated local times.

### Exercise 6 — Comparing After Conversion

A `ZonedDateTime` with nanoseconds `123456789` is converted to `GregorianCalendar` and back. Should you compare for exact equality down to nanoseconds?

**Suggested solution:** no, if the target contract only stores milliseconds. The sub-millisecond fraction is no longer preserved. Decide precision requirements upfront; if preserving nanoseconds is mandatory, change the storage/transport contract rather than expecting the legacy API to keep them.

## 12. Self-Check Before Modifying Legacy Code

You have understood this lesson when you can explain why January has index 0, why `set(...)` does not prove a date is valid, why `roll` is not a “tomorrow” calculation, and why changing a time zone can change the hour read without changing the instant.

When applying this, clearly identify the calendar type, time zone, and data that must be preserved; populate all fields, force validation at data ingestion, and then convert to the appropriate modern type. For historical dates or sub-millisecond data, add dedicated tests matching the actual contract.
