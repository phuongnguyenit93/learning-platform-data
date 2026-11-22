# Limitations of toInstant() on java.sql.Date and java.sql.Time

## 1. Inheriting from Date Without Sharing the Same Time Contract

A plain `java.util.Date` represents an instant in time and can be converted to `Instant` using `toInstant()`. However, the two legacy JDBC types `java.sql.Date` and `java.sql.Time` override this method with a different contract:

| Actual type | Primary meaning | toInstant() |
|---|---|---|
| Plain `java.util.Date` | An instant at millisecond precision | Convertible |
| `java.sql.Date` | A date in the sense of SQL DATE, without a business time-of-day part | Always throws `UnsupportedOperationException` |
| `java.sql.Time` | A time in the sense of the legacy SQL TIME class, without a business date | Always throws `UnsupportedOperationException` |

This is documented API behavior, not a random bug in a specific driver version or a special time zone.

The reason lies in the meaning of the data: a single date or a single time of day is not enough to determine a unique instant. The fact that these classes inherit a millisecond-based representation from Date does not automatically supply the missing business information.

## 2. A Superclass Reference Type Does Not Change the Actual Object

Illustrative snippet:

```java
java.sql.Date sqlDate = java.sql.Date.valueOf("2026-10-25");
java.util.Date value = sqlDate;
value.toInstant(); // UnsupportedOperationException.
```

Assigning to a `java.util.Date` variable only changes the declared reference type; it does not create a new plain Date object. The method call is still dispatched based on the actual runtime type and runs the overridden version in `java.sql.Date`.

A utility method that accepts `java.util.Date` and calls `toInstant()` is therefore not contract-safe if callers can pass in SQL Date or Time. The compiler may allow the call, but runtime behavior still depends on the actual object received.

Do not try to fix this by casting to `java.util.Date` again. A cast neither changes the data nor removes the overridden method. You need to identify the column's meaning and choose the corresponding conversion.

## 3. Converting Properly to Component Types of java.time

Commonly appropriate conversions:

```java
LocalDate date = sqlDate.toLocalDate();
LocalTime time = sqlTime.toLocalTime();
```

In the reverse direction:

```java
java.sql.Date sqlDate = java.sql.Date.valueOf(date);
java.sql.Time sqlTime = java.sql.Time.valueOf(time);
```

These are illustrative snippets assuming valid input variables; the standalone program in section 6 contains full declarations.

`toLocalDate()` preserves year-month-day according to the SQL Date contract. `toLocalTime()` preserves hour-minute-second according to the legacy SQL Time contract. They do not fabricate missing time or date components and do not attach a time zone on behalf of business logic.

Use the fully qualified name `java.sql.Date` in boundary code when it is easy to confuse with `java.util.Date`. Two classes sharing the same short name does not mean their conversions can be used interchangeably.

### Note on fractional seconds in legacy SQL Time

`java.sql.Time.valueOf(LocalTime)` takes hours, minutes, and seconds; the nanosecond part of LocalTime is not preserved across that conversion. `toLocalTime()` on legacy Time is also not a promise that all fractional-second precision of a modern SQL TIME column will be preserved.

If the data requires fractional seconds, check the actual driver and column support and mapping. Do not pass it through `java.sql.Time` and assume the result remains complete just because the input LocalTime supports nanoseconds.

## 4. Creating an Instant Requires Deliberately Adding Context

### From SQL Date: you must choose a time of day and a time zone

If the feature genuinely wants the start of a day in a given zone, you can write:

```java
Instant start = sqlDate.toLocalDate()
        .atStartOfDay(businessZone)
        .toInstant();
```

`businessZone` must be a zone determined by the feature's requirements. `atStartOfDay(zone)` chooses the valid start-of-day instant according to the zone rules; you must not assume every day in every zone always has a valid 00:00.

This call adds a decision: "start of day in zone X". It does not prove that SQL Date originally contained that start-of-day instant. If the data is a birth date or a document date with no time component, keeping LocalDate is usually already the right goal and there is no need to convert to Instant.

### From SQL Time: you must add a date and zone context

If the data is an opening time, you need a specific date and zone to compute a particular opening instant:

```java
Instant opening = selectedDate.atTime(sqlTime.toLocalTime())
        .atZone(businessZone)
        .toInstant();
```

`selectedDate` must not be arbitrarily taken from the epoch date or the machine's "today" unless the contract asks for it. A time such as 09:15:30 can occur on countless dates; there is no unique Instant from time fields alone.

In zones with DST, a local date-time may also not exist or may have two valid offsets. When the feature requires strict checking, you must choose a gap/overlap policy rather than letting a default zone attachment silently decide every case.

The steps above are **constructing an instant from component data and additional policy**, not unlocking a `toInstant()` that was disabled.

## 5. Why Working Around with getTime Does Not Solve the Meaning

Technically, you can write:

```java
Instant raw = Instant.ofEpochMilli(sqlDate.getTime());
```

This statement creates an Instant from a millisecond count, so it does not call the overridden `toInstant()` method. However, it is using the object's legacy representation, which does not prove that this is the right instant the business logic needs.

Similarly, creating `new java.util.Date(sqlTime.getTime())` and calling `toInstant()` may work at the API level, but the date part attached to Time does not become a business date just because the wrapper class was changed.

Only use such a conversion path if the source contract truly defines the instant meaning of those milliseconds and you intentionally need it. Do not use it as a general way to "dodge the exception" for all SQL Date/Time values.

The exception here helps expose a gap in the model. Returning the epoch, `null`, or an implicitly assembled instant when catching `UnsupportedOperationException` can hide a mistaken API call. Fix the type selection or require the necessary context instead of fabricating ungrounded substitute data.

## 6. Complete Runnable Program

Save the following code to `SqlDateTimeInstantDemo.java`. The program uses Java 17 or later and requires no external libraries or database connection.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

public class SqlDateTimeInstantDemo {
    private static void probe(String label, java.util.Date value) {
        try {
            System.out.println(label + "=" + value.toInstant());
        } catch (UnsupportedOperationException e) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        java.sql.Date sqlDate = java.sql.Date.valueOf("2026-10-25");
        java.sql.Time sqlTime = java.sql.Time.valueOf("09:15:30");

        probe("utilDate", new java.util.Date(0L));
        probe("sqlDate", sqlDate);
        probe("sqlTime", sqlTime);

        java.util.Date widenedDate = sqlDate;
        java.util.Date widenedTime = sqlTime;
        probe("sqlDateAsUtilDate", widenedDate);
        probe("sqlTimeAsUtilDate", widenedTime);

        LocalDate date = sqlDate.toLocalDate();
        LocalTime time = sqlTime.toLocalTime();
        System.out.println("localDate=" + date);
        System.out.println("localTime=" + time);
        System.out.println("dateRoundTrip="
                + date.equals(java.sql.Date.valueOf(date).toLocalDate()));
        System.out.println("timeRoundTrip="
                + time.equals(java.sql.Time.valueOf(time).toLocalTime()));

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant selectedDayStart = date.atStartOfDay(zone).toInstant();
        Instant chosenDateTime = date.atTime(time).atZone(zone).toInstant();
        System.out.println("selectedDayStart=" + selectedDayStart);
        System.out.println("chosenDateTime=" + chosenDateTime);

        LocalTime preciseTime = LocalTime.of(9, 15, 30, 123_456_789);
        java.sql.Time legacyTime = java.sql.Time.valueOf(preciseTime);
        System.out.println("originalNanos=" + preciseTime.getNano());
        System.out.println("afterTimeValueOfNanos="
                + legacyTime.toLocalTime().getNano());
    }
}
```

Compile and run:

```shell
javac SqlDateTimeInstantDemo.java
java SqlDateTimeInstantDemo
```

Expected output:

```text
utilDate=1970-01-01T00:00:00Z
sqlDate=UnsupportedOperationException
sqlTime=UnsupportedOperationException
sqlDateAsUtilDate=UnsupportedOperationException
sqlTimeAsUtilDate=UnsupportedOperationException
localDate=2026-10-25
localTime=09:15:30
dateRoundTrip=true
timeRoundTrip=true
selectedDayStart=2026-10-24T17:00:00Z
chosenDateTime=2026-10-25T02:15:30Z
originalNanos=123456789
afterTimeValueOfNanos=0
```

The exception name is a label printed by the program when catching the error, not the full JDK message.

`probe` accepts the superclass `java.util.Date`, yet still observes the behavior of the actual runtime object. The two assignments `widenedDate` and `widenedTime` do not change the result because no new object is created.

The two lines creating `Instant` have clear context: the chosen date is 25/10/2026, the zone is Vietnam, one case selects the start of the day and the other combines the time 09:15:30. The difference from the UTC date string is a consequence of determining the instant in that zone, not a date-shifting bug.

The Date/Time round-trip checks in the program only verify data at the chosen date and whole-second time level. The last lines show that round-tripping through Time does not preserve the nanosecond part of the source LocalTime.

## 7. Handling at the JDBC Boundary

If you already receive `java.sql.Date` or `java.sql.Time` from legacy JDBC code, converting to the appropriate component type as close to the boundary as possible helps reduce confusion inside the application.

Illustrative example inside a method that has `ResultSet rs`:

```java
java.sql.Date rawDate = rs.getDate("business_date");
LocalDate businessDate = rawDate == null ? null : rawDate.toLocalDate();

java.sql.Time rawTime = rs.getTime("opening_time");
LocalTime openingTime = rawTime == null ? null : rawTime.toLocalTime();
```

`null` in the example represents SQL NULL according to the data contract being handled; do not replace it with the epoch or midnight. If the field is required, validate and report missing data at the appropriate layer.

With drivers and JDBC versions that support `java.time` types, you can use direct get/set methods matching the column. However, you still need to verify the mapping, precision, and session/driver time zone by reading and writing against the real system. This article only demonstrates the behavior of the Java classes; it does not verify any specific database, ORM, or driver.

Do not build a generic converter based solely on `instanceof java.util.Date` and treat every subtype as a timestamp. You must choose based on column semantics and the API contract. An output structure can hold LocalDate for a date field and LocalTime for a time field, rather than forcing everything into Instant for superficial uniformity.

## 8. Do Not Generalize to Timestamp

`java.sql.Timestamp` is another legacy type, with a nanosecond part and its own `toInstant()` behavior. The fact that Date and Time always reject it does not prove that Timestamp rejects it as well.

Conversely, Timestamp being convertible to Instant at the API level does not automatically confirm that a database column is a global instant. A date-time column without a zone still needs to be interpreted according to the driver/application contract. You must separate **what the API allows converting** from **what instant meaning the data actually has**.

The legacy SQL classes also inherit mutability from Date. Converting to immutable LocalDate/LocalTime helps isolate state inside new processing logic, but it does not replace checking inputs that are mutated elsewhere or data already interpreted by the driver beforehand.

## 9. Self-Practice

1. Write a method that accepts `java.util.Date` and test it with plain Date, SQL Date, and SQL Time. Explain the behavior in each case using the actual runtime type rather than the parameter type.
2. Change the added time zone in the Instant creation section to UTC. The component date/time stays the same, while the resulting Instant changes; identify this as a change in business decision, not a fix for `toInstant()`.
3. Pass a `LocalTime` with fractional seconds into `Time.valueOf`, then compare before and after. Choose an appropriate mapping if the contract requires preserving that precision.
4. Given a "birth date" column, show the proper conversion to LocalDate and explain why you should not pick a time zone to fabricate an Instant.

References: [java.sql.Date — toInstant and toLocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Date.html) and [java.sql.Time — toInstant, toLocalTime and valueOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Time.html) in Java SE 21.
