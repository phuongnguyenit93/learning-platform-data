# `parse()` and Target-Type Data Requirements

## 1. Being able to read text does not mean an object can be created

When receiving an input field, CSV line, or JSON field containing a date or time, the program initially only has a **character string**. `parse()` parses the string according to the chosen convention and creates a temporal object of a specific type. Choosing the target type means choosing the information the application needs to store: a date, a time, a local date-time, or a specific instant on the timeline.

For example, `2025-06-10` is enough to create a `LocalDate`, but not enough to create a `LocalDateTime` because the time is missing. The string `2025-06-10T09:15:00` has both date and time, yet still lacks a UTC offset to create an `OffsetDateTime`. Missing data cannot be fixed by changing the name of the method called.

Check all three factors simultaneously:

```text
Actual string → what can the formatter read? → what does the target type need?
                       ↓                                   ↓
            valid syntax and values           enough information to create an object
```

According to [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html), parsing consists of reading fields and then resolving them into date-time values. Querying the result into a specific type is an additional requirement. Therefore, choosing the right pattern characters only solves part of the problem.

## 2. Choose the target type before choosing how to parse

The table below uses self-constructed example strings for common default `parse(text)` calls:

| Target type | Required information in the example | Matching string |
| --- | --- | --- |
| `LocalDate` | A complete date | `2025-06-10` |
| `LocalTime` | Time of day | `09:15:00` |
| `LocalDateTime` | Local date and time | `2025-06-10T09:15:00` |
| `OffsetTime` | Time and UTC offset | `09:15:00+07:00` |
| `OffsetDateTime` | Date, time, and UTC offset | `2025-06-10T09:15:00+07:00` |
| `ZonedDateTime` | Date-time with appropriate time zone information | `2025-06-10T09:15:00+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | A specific instant; example represented in UTC | `2025-06-10T02:15:00Z` |
| `YearMonth` | Year and month | `2025-06` |

The strings above are examples, not an exhaustive list of every permitted format. For instance, the time may omit the seconds part if the formatter supports it. `ZonedDateTime.parse()` also accepts an example with only the offset `+07:00` and no zone name: the result then uses that fixed offset itself as the zone, without automatically inferring `Asia/Ho_Chi_Minh`.

`LocalDateTime` does not contain a time zone; to identify an instant on the timeline, an offset or time zone must also be provided. This is the informational difference of the data type, as stated in [Java SE 21 — LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html).

Do not choose `Instant` just because a string looks like a log timestamp. If the source data is only a local time, you need to know the source's time zone convention before converting it into an instant. The default `parse()` does not automatically take the machine's zone to make up for that information.

## 3. Two common ways to call `parse()`

### Using the type's default convention

The following statements are illustrative code placed inside a method:

```java
LocalDate date = LocalDate.parse("2025-06-10");
LocalDateTime dateTime = LocalDateTime.parse("2025-06-10T09:15:00");
```

The input must follow the format accepted by the default call. Therefore, `LocalDate.parse("10/06/2025")` does not succeed just because a human reader understands it as June 10.

### Providing a `DateTimeFormatter`

When the input contract uses day/month/year, express that rule explicitly:

```java
// Demonstration inside a method, with import java.time.* and java.time.format.*.
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", java.util.Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
LocalDate date = LocalDate.parse("10/06/2025", formatter);
```

`dd` is day of month, `MM` is month, and `uuuu` is year. Letter case matters: `mm` is minute, not month; `YYYY` is week-based year, not a substitute for calendar year. For standard ISO dates and strict mode, using `uuuu` avoids needing to resolve year-of-era for `yyyy` when no era is provided.

`ResolverStyle.STRICT` requires the date to actually exist. Creating a pattern with `ofPattern()` defaults to `SMART`, which may adjust some dates to the end of the month. Thus, checking for `/` separators and digit counts does not mean `31/02/2025` has been rejected. If textual month names are present, you must also choose a `Locale` matching the source language; do not guess based on the machine running the code.

## 4. Complete runnable program: syntax, valid dates, and missing information

Save the code to `ParseTargetDemo.java`. The program uses Java 17 or later and has no external libraries:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;
import java.util.function.Supplier;

public class ParseTargetDemo {
    private static void show(String label, Supplier<?> action) {
        try {
            System.out.println(label + " = " + action.get());
        } catch (DateTimeParseException ex) {
            System.out.println(label + " = DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        show("date", () -> LocalDate.parse("2024-02-29"));
        show("time", () -> LocalTime.parse("09:15:00"));
        show("date-time", () -> LocalDateTime.parse("2025-06-10T09:15:00"));
        show("offset", () -> OffsetDateTime.parse("2025-06-10T09:15:00+07:00"));
        show("instant", () -> Instant.parse("2025-06-10T02:15:00Z"));

        show("date-only to date-time", () -> LocalDateTime.parse(
                "2025-06-10", DateTimeFormatter.ISO_LOCAL_DATE));
        show("no offset", () -> OffsetDateTime.parse(
                "2025-06-10T09:15:00", DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        show("wrong syntax", () -> LocalDate.parse("10/06/2025"));
        show("trailing space", () -> LocalDate.parse("2025-06-10 "));

        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        show("custom valid", () -> LocalDate.parse("29/02/2024", strict));
        show("custom invalid", () -> LocalDate.parse("31/02/2025", strict));
        DateTimeFormatter smart = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT);
        show("smart adjusted", () -> LocalDate.parse("31/02/2025", smart));

        TemporalAccessor fields = DateTimeFormatter.ISO_LOCAL_DATE_TIME
                .parse("2025-06-10T09:15:00");
        System.out.println("extract date = " + LocalDate.from(fields));
        System.out.println("extract time = " + LocalTime.from(fields));
        show("explicit date projection", () -> LocalDate.parse(
                "2025-06-10T09:15:00", DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        System.out.println("offset as zone = " + ZonedDateTime
                .parse("2025-06-10T09:15:00+07:00").getZone());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ParseTargetDemo.java
java ParseTargetDemo
```

Output:

```text
date = 2024-02-29
time = 09:15
date-time = 2025-06-10T09:15
offset = 2025-06-10T09:15+07:00
instant = 2025-06-10T02:15:00Z
date-only to date-time = DateTimeParseException
no offset = DateTimeParseException
wrong syntax = DateTimeParseException
trailing space = DateTimeParseException
custom valid = 2024-02-29
custom invalid = DateTimeParseException
smart adjusted = 2025-02-28
extract date = 2025-06-10
extract time = 09:15
explicit date projection = 2025-06-10
offset as zone = +07:00
```

The `show` method intentionally prints only the exception name so that the output is easy to compare across JDKs; it is a demonstration technique, not an error-handling policy for an application. `Supplier<?>` simply lets the operation to run be passed into this method.

### Reading the output by cause

- `wrong syntax`: the string uses `/`, whereas the default formatter expects an ISO date with `-`.
- `trailing space`: the trailing space at the end of the string was not consumed; a call that parses the entire string does not ignore it by default.
- `custom invalid`: the pattern can read the numbers, but `STRICT` mode rejects February 31.
- `date-only to date-time`: `ISO_LOCAL_DATE` can read the date, but the result lacks a time to create a `LocalDateTime`.
- `no offset`: `ISO_LOCAL_DATE_TIME` can read the date-time, but the result lacks a UTC offset to create an `OffsetDateTime`.

The first three groups relate to syntax or date validity; the last two show that **a valid format can still lack data for the target type**. Catching the same `DateTimeParseException` does not mean every case has the same cause.

The lines printing times without `:00` reflect how the object chooses to represent its string form when seconds are 0. The data was created accurately, though there is no guarantee that `parsed.toString()` matches the input verbatim. To output in a fixed format, call `format()` with an appropriate output formatter.

## 5. `DateTimeFormatter.parse()` and obtaining a specific type

In the program, `DateTimeFormatter.ISO_LOCAL_DATE_TIME.parse(text)` returns a `TemporalAccessor`. You can think of this as an interface for accessing the parsed and resolved temporal fields; you should not cast it directly to `LocalDateTime`.

We used `LocalDate.from(fields)` and `LocalTime.from(fields)` to extract the date and time separately. You can combine the parsing and querying steps by writing the following inside a method:

```java
LocalDateTime value = DateTimeFormatter.ISO_LOCAL_DATE_TIME.parse(
        "2025-06-10T09:15:00", LocalDateTime::from);
```

`LocalDateTime::from` specifies the desired type. If the parsed data does not contain enough information for that query, the operation still fails.

A notable detail in the program is `explicit date projection`: `LocalDate.parse(text, ISO_LOCAL_DATE_TIME)` succeeds with a string containing both date and time, because the formatter reads the entire string and then the target type extracts the date portion. By contrast, the default `LocalDate.parse(text)` will not automatically accept the leftover `T09:15:00` part. Therefore, you cannot conclude that every `parse()` on a simpler type automatically discards extra data.

Extracting only the date loses the time information in the resulting value. Choose this approach only when the business contract genuinely requires just a date; if you need to preserve the transaction timestamp, keep a type that holds sufficient information.

## 6. Filling in missing data must be an explicit decision

If a form only asks for a date but the business rules specify that appointments start at 09:00, parse the date and then add the time in a readable way:

```java
// Demonstration inside a method.
LocalDate date = LocalDate.parse("2025-06-10");
LocalDateTime appointment = date.atTime(9, 0);
OffsetDateTime withOffset = appointment.atOffset(ZoneOffset.of("+07:00"));
Instant instant = withOffset.toInstant();
```

Here, 09:00 and `+07:00` come from known application rules. They are not inferred from the date string. Do not pick midnight or the machine's default zone just to avoid an exception: the same string with missing data can have multiple technically valid interpretations that differ in business meaning.

A formatter can also be configured to provide default values, but that is still a rule the designer must decide on. Before using that mechanism, clearly identify which fields are genuinely provided by the source and which are supplied by the application.

## 7. Error handling and self-check

When user-supplied input cannot be parsed, you can catch `DateTimeParseException` at the input boundary and report the expected format. `getParsedString()` and `getErrorIndex()` aid diagnosis; the error position does not replace checking for missing fields required by the target type. Do not rely on the exact wording of the exception message for business classification, as messages may change.

Do not use `null` or "the current time" as a silent fallback for all parsing errors. Absent input, malformed strings, and non-existent dates are different situations that should be modeled according to application requirements. A format pattern miswritten by a developer should also be fixed in configuration/code, rather than telling the user that the date they entered is wrong.

Before finalizing a `parse()` call, ask yourself:

1. What format is specified for the string, and are whitespace or month names in a specific language allowed?
2. Does the formatter read the entire string and validate the date with the required strictness?
3. Does the result have enough data for the target type, especially time, offset, and time zone?
4. If extracting a subset or supplying defaults, is that loss or addition of information permitted by the business requirements?

Exercise: replace `ISO_LOCAL_DATE_TIME` with `ISO_LOCAL_DATE` in the `LocalDateTime::from` query example and pass only `2025-06-10`. Predict that the date string is read properly, but the target query fails because the time is missing. Then fix it using `LocalDate.parse(text).atTime(9, 0)` and clearly explain that 09:00 comes from the application's rules, not from the input data.
