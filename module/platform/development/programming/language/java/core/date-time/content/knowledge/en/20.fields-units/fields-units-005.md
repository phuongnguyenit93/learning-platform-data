# isSupported() before using a field or unit

## 1. Why check for support?

A date-time object only provides information that fits its semantics. `LocalDate` has a calendar date but no time of day; `Instant` represents a point on the timeline without inherently carrying a local time. Belonging to the same `java.time` family does not mean they support the same set of fields or units.

`isSupported()` helps generic code answer **“is this object capable of performing that kind of operation?”** before reading a field or adding/subtracting by a unit. It is especially useful when the input has multiple possible types or when the field/unit is chosen at runtime.

For example, a display utility only reads `HOUR_OF_DAY` if the input has that field; a calendar-addition utility only accepts `MONTHS` if the input type supports adding months. This turns the unsupported case into an explicit handling branch.

## 2. Two overloads answer two different questions

| Signature | Where declared? | Question |
| --- | --- | --- |
| `isSupported(TemporalField field)` | `TemporalAccessor` | Is the field supported for reading? |
| `isSupported(TemporalUnit unit)` | `Temporal` | Is the unit supported for adding/subtracting? |

`ChronoField.HOUR_OF_DAY` is a **field**: what is the current hour of the day? `ChronoUnit.HOURS` is a **unit**: how many hours to add/subtract? When writing a check, pass the exact object describing the operation about to be performed.

```java
LocalDate date = LocalDate.of(2024, 6, 15);
boolean canReadDay = date.isSupported(ChronoField.DAY_OF_MONTH);
boolean canAddDays = date.isSupported(ChronoUnit.DAYS);
```

The snippet above is illustrative code inside a method and requires importing the used types. There is no zero-argument overload meaning “this type supports all date-time operations.” [TemporalAccessor.isSupported](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html#isSupported(java.time.temporal.TemporalField))

If a variable is declared as `TemporalAccessor`, only the overload taking a field appears on that type. To check a unit and call `plus`, the input contract must be `Temporal`. Do not cast blindly just to call a method, because some objects such as `MonthDay` are not `Temporal`.

## 3. Field reading support does not imply unit addition support

| Object | Read `HOUR_OF_DAY` | Add `HOURS` | Explanation |
| --- | --- | --- | --- |
| `LocalDate` | No | No | Describes only a date |
| `LocalTime` | Yes | Yes | Describes a time of day |
| `Instant` | No | Yes | Can advance by one hour on the timeline without choosing a local time |

With `Instant`, choosing `HOUR_OF_DAY` requires a rule to convert to a time zone, such as `instant.atZone(zone)`. `isSupported` does not automatically pick the OS time zone and does not fill in missing data. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Conversely, a type that has month information does not necessarily support general month addition. Check the right overload instead of guessing from the type name or from another field that was read successfully.

## 4. Handling strategies when unsupported

There are two common policies; choose according to the business contract:

- **Optional information:** return a result representing absence, such as `OptionalLong.empty()`, or omit displaying the field.
- **Required capability:** reject the input with a clear error before performing the operation.

Do not return `0` in place of an unsupported field: hour 0, second 0, or epoch day 0 can all be real data. Do not automatically turn “hour not supported” into “default to midnight” unless the business rules specify it.

Checking `isSupported(unit)` only rules out the cause **unsupported unit**. It does not replace checking result bounds or business conditions. [Temporal.isSupported](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/Temporal.html#isSupported(java.time.temporal.TemporalUnit))

## 5. Demonstration program and handling missing support

Save as `SupportedDemo.java`. The example uses fixed data and does not depend on the machine's current date and time.

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalField;
import java.time.temporal.TemporalUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Objects;
import java.util.OptionalLong;

public class SupportedDemo {
    static OptionalLong readIfSupported(
            TemporalAccessor value, TemporalField field) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(field, "field");
        if (!value.isSupported(field)) {
            return OptionalLong.empty();
        }
        return OptionalLong.of(value.getLong(field));
    }

    static Temporal addRequired(
            Temporal value, long amount, TemporalUnit unit) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
        if (!value.isSupported(unit)) {
            throw new IllegalArgumentException("Unsupported unit: " + unit);
        }
        return value.plus(amount, unit);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 6, 15);
        LocalTime time = LocalTime.of(14, 30);
        Instant moment = Instant.parse("2024-06-15T00:00:00Z");

        System.out.println("dateHour="
                + date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("timeHour="
                + time.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("instantHour="
                + moment.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("instantHours="
                + moment.isSupported(ChronoUnit.HOURS));

        System.out.println("dateRead="
                + readIfSupported(date, ChronoField.HOUR_OF_DAY));
        System.out.println("timeRead="
                + readIfSupported(time, ChronoField.HOUR_OF_DAY));
        System.out.println("instantPlus="
                + addRequired(moment, 2, ChronoUnit.HOURS));
        try {
            addRequired(date, 1, ChronoUnit.HOURS);
        } catch (IllegalArgumentException ex) {
            System.out.println("dateRejectsHours");
        }

        System.out.println("epochDaySupported="
                + date.isSupported(ChronoField.EPOCH_DAY));
        try {
            date.get(ChronoField.EPOCH_DAY);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("epochDayNeedsGetLong");
        }
        System.out.println("epochDay=" + date.getLong(ChronoField.EPOCH_DAY));

        System.out.println("monthSupported="
                + date.isSupported(ChronoField.MONTH_OF_YEAR));
        try {
            date.with(ChronoField.MONTH_OF_YEAR, 13);
        } catch (DateTimeException ex) {
            System.out.println("month13Invalid");
        }

        System.out.println("maxSupportsDays="
                + LocalDate.MAX.isSupported(ChronoUnit.DAYS));
        try {
            LocalDate.MAX.plus(1, ChronoUnit.DAYS);
        } catch (DateTimeException ex) {
            System.out.println("beyondMaxDate");
        }
    }
}
```

Compile and run with JDK 17 or later:

```shell
javac --release 17 SupportedDemo.java
java SupportedDemo
```

Exact stdout:

```text
dateHour=false
timeHour=true
instantHour=false
instantHours=true
dateRead=OptionalLong.empty
timeRead=OptionalLong[14]
instantPlus=2024-06-15T02:00:00Z
dateRejectsHours
epochDaySupported=true
epochDayNeedsGetLong
epochDay=19889
monthSupported=true
month13Invalid
maxSupportsDays=true
beyondMaxDate
```

`readIfSupported` keeps the missing-data case separate. It uses `getLong`, avoiding the `int` limit when reading a field with a large range. `addRequired` treats unit addition support as a mandatory input precondition, while still letting the addition fail if the result exceeds bounds.

The `try/catch` blocks at the end of the program are used to demonstrate the limits of the check. They are not advice to catch every error in every date addition.

## 6. true does not mean every subsequent call will succeed

### 6.1. Field support differs from being readable as int

`LocalDate` supports `EPOCH_DAY`, but the field's range exceeds `int`. Therefore `get(EPOCH_DAY)` fails even when a specific date's number is currently small; use `getLong(EPOCH_DAY)`. Checking support is not checking the output numeric type. [LocalDate: read field](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#get(java.time.temporal.TemporalField))

### 6.2. Field support differs from a valid new value

`MONTH_OF_YEAR` being supported does not make month 13 valid. Similarly, day 31 does not exist in every month. When setting a field, you need to understand the field's range and specific adjustment rules. If accepting user input, validate the data and respond according to the business contract.

### 6.3. Unit support differs from the result being within range

`LocalDate.MAX` still supports `DAYS`; that describes the data type's ability to calculate in days. Adding one more day exceeds the `LocalDate` range, so it throws an exception. Other large calculations may also encounter `ArithmeticException` due to numeric overflow.

### 6.4. A supported unit does not define business meaning

A `ZonedDateTime` may support both `DAYS` and `HOURS`, but adding one calendar day differs from adding 24 hours across a daylight saving time transition. `isSupported` does not answer “which unit fits the scheduling requirement?” You must determine beforehand whether the intent is local calendar days or actual elapsed duration.

### 6.5. Support on one endpoint does not guarantee a two-endpoint calculation will succeed

For `until`/`between`, you must also ensure the other endpoint can be converted to the required data type. Do not merely check the unit on the first endpoint and conclude that an arbitrary pair such as `LocalDate` and `LocalTime` can compute a distance.

## 7. null, declared types, and unnecessary checks

For the contract overloads, a `null` field/unit argument returns `false`. However, `date.isSupported(null)` does not compile when the variable has both overloads: the compiler cannot choose between `TemporalField` and `TemporalUnit`.

Illustrative snippet inside a method:

```java
TemporalField missingField = null;
TemporalUnit missingUnit = null;
System.out.println(date.isSupported(missingField)); // false
System.out.println(date.isSupported(missingUnit));  // false
// date.isSupported(null);                         // Ambiguous overload.
```

`null` here does not mean “choose a default field.” The two utility methods in the program proactively reject `null` using `Objects.requireNonNull`, helping catch argument-passing bugs instead of treating them as an unsupported choice. If the receiver object itself is `null`, calling the method still causes a `NullPointerException`.

There is no need to scatter checks before every line when the type and operation are already known for certain. For example, business logic that takes a `LocalDate` and always reads `getYear()` can use the specific API directly. Checking is most useful when there is genuine variation in type or field/unit selection.

For custom fields or units, support may be determined by that implementation itself. Do not hardcode a list of only `ChronoField`/`ChronoUnit` and conclude that extended objects are unsupported; call the API contract and follow the implementation's specification.

## 8. Self-check

1. A method taking `TemporalAccessor` only needs to read the minute if present: which overload should be chosen and what should be returned when missing?
2. Why does `Instant` not support `HOUR_OF_DAY` yet still allow adding `HOURS`?
3. After `isSupported(MONTH_OF_YEAR) == true`, can you set the month to 13?
4. Why should you reconsider `get` when a field is supported yet still throws `UnsupportedTemporalTypeException`?
5. Is it necessary to check `isSupported(DAYS)` before every `LocalDate.plusDays(1)`?

Answers: (1) the field-taking overload, with an absent result having an explicit representation; (2) local hour requires a time zone, whereas adding hours on the timeline does not; (3) no; (4) the field's range may exceed `int`, so use `getLong` when appropriate; (5) not needed when the type contract is already clear, though result bounds must still be considered when near the limits.