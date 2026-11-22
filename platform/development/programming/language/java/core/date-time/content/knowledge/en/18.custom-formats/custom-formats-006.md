# parseBest() to Choose the Appropriate Result Type

## 1. One formatter, but inputs can carry different levels of information

Suppose a feature receives the following strings:

```text
2026-10-25T09:05
2026-10-25T09:05+07:00
2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]
```

All three have a date and time. The first string only has local date-time; the second adds a UTC offset; the third also includes a region-based time zone ID. If you always force the result to `LocalDateTime`, the offset and time zone information may be discarded. If you always require `ZonedDateTime`, an input containing only local date-time lacks sufficient data to construct that result.

`DateTimeFormatter.parseBest()` addresses this need: **it parses the string with one formatter and then tries ways to construct the result type in the order you specify**.

The name `Best` does not mean Java scores the options to pick the "most accurate type." You define the priority via the list of queries; the first result that can be constructed is returned.

## 2. Signature and how to read the call

Common usage:

```java
TemporalAccessor result = formatter.parseBest(
        text,
        ZonedDateTime::from,
        LocalDateTime::from);
```

The method references `ZonedDateTime::from` and `LocalDateTime::from` act as temporal queries (`TemporalQuery`). Each query attempts to construct a specific value from the parsed and resolved data.

The flow can be visualized as follows:

```text
String
  |
  v
Parse and resolve with formatter
  |
  +-- Syntax/date-time/unparsed-text error --> DateTimeParseException
  |
  v
Try ZonedDateTime::from
  |
  +-- Success --> return ZonedDateTime
  |
  v
Try LocalDateTime::from
  |
  +-- Success --> return LocalDateTime
  |
  v
No query can construct a result --> DateTimeParseException
```

The queries do not re-select the text pattern. The formatter has already defined the input grammar beforehand. For example, `parseBest` on an ISO formatter will not automatically accept `25/10/2026` by guessing a different pattern.

At least two queries are required; passing only one query throws `IllegalArgumentException`. When you only want a single exact type, using `formatter.parse(text, LocalDateTime::from)` or `LocalDateTime.parse(text, formatter)` expresses the intent more clearly.

## 3. Why query order determines whether information is preserved

For a string with a time zone, both of the following constructions can succeed:

- `ZonedDateTime::from`: preserves the date, time, and time zone.
- `LocalDateTime::from`: extracts the local date-time part, without keeping the time zone in the result.

If you place `LocalDateTime::from` first, the method immediately returns that type and does not try subsequent queries. It does not continue searching for a result that carries more information.

Therefore, when the requirement is to prioritize preserving the time zone, write:

```java
formatter.parseBest(text, ZonedDateTime::from, LocalDateTime::from);
```

Do not reverse the order just because `LocalDateTime` seems like a more "basic" type.

Similarly, when using a formatter that allows both a standalone date and a date with time, you typically prioritize `LocalDateTime::from` before `LocalDate::from` if you want to preserve the time when present. `LocalDate::from` can succeed on data that includes a time, so placing it first can cause the time component to disappear from the result.

The order should reflect the contract of your feature, not necessarily a list of all Java date-time classes in a fixed hierarchy.

## 4. The result type is not a verbatim record of the source syntax

An easy point of confusion: `ZonedDateTime` does not have to use a region-based time zone such as `Asia/Ho_Chi_Minh`. It can also use a fixed-offset zone such as `+07:00`.

Consequently, with the list `ZonedDateTime::from, LocalDateTime::from`:

| Input | First constructible type | Time zone in result |
|---|---|---|
| `2026-10-25T09:05` | `LocalDateTime` | None |
| `2026-10-25T09:05+07:00` | `ZonedDateTime` | `+07:00`, fixed offset |
| `2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | `Asia/Ho_Chi_Minh`, region-based time zone |

Do not see a `ZonedDateTime` result and conclude that the original string definitely contained a region ID in square brackets.

If the output requirement only distinguishes "has a UTC offset" from "no offset," you can choose `OffsetDateTime::from` and `LocalDateTime::from`. However, if the source data contains a region ID, an `OffsetDateTime` result does not preserve that region ID. You need to decide which information must be preserved before writing the query list.

Putting `ZonedDateTime::from` followed by `OffsetDateTime::from` also does not create a rule of "region ID gives Zoned, offset-only gives Offset": an offset-only input can already succeed on the first Zoned query. If you truly need to classify by source components, you must inspect the appropriate source information rather than relying solely on the order of these two queries.

Configurations such as an override zone or formatter defaults can also supply information that was not typed directly. The result reflects the data after parsing and resolving; it does not automatically retain the history of each individual input component.

## 5. Handling TemporalAccessor safely

`parseBest` returns `TemporalAccessor` because the queries can produce different types. After calling it, use `instanceof` against the types you have allowed:

```java
if (result instanceof ZonedDateTime zoned) {
    // Handle value with time zone.
} else if (result instanceof LocalDateTime local) {
    // Handle local date-time, not yet identifying a unique instant.
}
```

The branches above are only an illustrative structure. In a real program, the zoned branch can convert to `Instant` if an instant is needed; the local branch needs the feature's time zone policy applied before doing so.

Do not cast directly to `ZonedDateTime` just because it is first in the list: the very point of `parseBest` is that this query may fail and another type may be returned. An unchecked cast can cause a `ClassCastException` after a parse that actually succeeded.

The queries used with this method must produce a result of type `TemporalAccessor`; the `from` method references of standard date-time classes are the common choice. It is not a general-purpose method for trying arbitrary conversions to strings or numbers.

## 6. Complete runnable program

Save the following code to `ParseBestDemo.java`. The program requires Java 17 or later and no external libraries.

```java
import java.time.LocalDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.TemporalAccessor;

public class ParseBestDemo {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ISO_DATE_TIME;

    public static void main(String[] args) {
        inspect("2026-10-25T09:05");
        inspect("2026-10-25T09:05+07:00");
        inspect("2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]");
        inspect("2026-10-25");
        inspect("2026-02-30T09:05");
        inspect("2026-10-25T09:05junk");

        TemporalAccessor firstLocal = FORMAT.parseBest(
                "2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]",
                LocalDateTime::from, ZonedDateTime::from);
        System.out.println("reversed="
                + firstLocal.getClass().getSimpleName() + " " + firstLocal);

        LocalDateTime knownType = FORMAT.parse(
                "2026-10-25T09:05", LocalDateTime::from);
        System.out.println("singleQuery=" + knownType);

        try {
            FORMAT.parseBest("2026-10-25T09:05", LocalDateTime::from);
        } catch (IllegalArgumentException e) {
            System.out.println("oneQuery=IllegalArgumentException");
        }
    }

    private static void inspect(String text) {
        try {
            TemporalAccessor parsed = FORMAT.parseBest(
                    text, ZonedDateTime::from, LocalDateTime::from);

            if (parsed instanceof ZonedDateTime zoned) {
                System.out.println("ZonedDateTime=" + zoned
                        + " zone=" + zoned.getZone());
            } else if (parsed instanceof LocalDateTime local) {
                System.out.println("LocalDateTime=" + local);
            } else {
                throw new IllegalStateException("unexpected result type");
            }
        } catch (DateTimeParseException e) {
            System.out.println("ERROR=" + text);
        }
    }
}
```

Compile and run:

```shell
javac ParseBestDemo.java
java ParseBestDemo
```

Verified expected output:

```text
LocalDateTime=2026-10-25T09:05
ZonedDateTime=2026-10-25T09:05+07:00 zone=+07:00
ZonedDateTime=2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh] zone=Asia/Ho_Chi_Minh
ERROR=2026-10-25
ERROR=2026-02-30T09:05
ERROR=2026-10-25T09:05junk
reversed=LocalDateTime 2026-10-25T09:05
singleQuery=2026-10-25T09:05
oneQuery=IllegalArgumentException
```

`ERROR` is a label printed by the program when catching `DateTimeParseException`, not Java's default message. Each test case serves a distinct purpose:

- The standalone date is rejected because `ISO_DATE_TIME` requires both date and time parts; adding a `LocalDate::from` query will not make this formatter accept a standalone date.
- February 30 is rejected when resolving fields against the calendar.
- The `junk` suffix is rejected because `parseBest` requires consuming the entire string.
- The `reversed` line shows that reversing the order loses time zone information in the result type.
- The last line distinguishes a configuration error (insufficient number of queries) from an input data error.

The zone/offset cases in the program were chosen to be consistent. Handling a string containing an offset that conflicts with the time zone is a separate contract of the date-time resolving step; `parseBest` does not turn trying multiple types into a validation that all source information is consistent according to your desired business policy.

## 7. Boundaries to keep in mind

### Do not invent missing data

If the input only has local date-time, with no offset or time zone, do not assume it is UTC just because the Zoned query failed. A `LocalDateTime` result does not yet identify a unique instant. Rules for supplying a time zone belong to a processing layer with the appropriate context.

### Not a mechanism for validating all business rules

A successful parse does not prove that an appointment falls within business hours, that a deadline is in the future, or that a time zone belongs to an allowed list. Those conditions must be checked on the result after its type is known.

### Does not preserve original formatting

`toString()` on the result may omit zero seconds or use the canonical representation of the type. If you need to keep the source string for auditing or reconciliation, store it separately. Choosing a type that holds enough information is not equivalent to preserving the exact character-by-character spelling.

### Does not extend syntax by adding queries

To accept an additional text structure, you must modify the formatter or design separate formatters with clear contracts. Adding types to the list only expands the ways to construct results from the same parsed data.

## 8. Practice on your own

1. Add the input `2026-10-25T02:05Z`. With the current order, it returns `ZonedDateTime`; the resulting zone is `Z`, not a region ID.
2. Put `LocalDateTime::from` first and observe the same input becoming a local date-time, with no offset left in the result type.
3. Keep only the Zoned query with `FORMAT.parse(text, ZonedDateTime::from)`: inputs without a time zone/offset will fail to construct that result. This call is appropriate when the contract requires a zoned type.

Before each use of `parseBest`, define separately the input grammar, the result priority order, and how to handle cases where the input carries less information than the feature requires. These three clear decisions help the method preserve the right information instead of silently narrowing the data.

References: [DateTimeFormatter — parseBest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseBest(java.lang.CharSequence,java.time.temporal.TemporalQuery...)) and [ZonedDateTime — from](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#from(java.time.temporal.TemporalAccessor)) in Java SE 21.
