# Strings with Missing Fields and Supplementary Information for Target Types

## 1. Missing information is not the same as an invalid string

A billing system receives a reconciliation month of `2025-06`; a form receives an appointment date of `2025-06-10`; a file receives a start time of `14:30`. All three strings can be valid for their original purpose, yet none of them describes a complete instant on the timeline on its own.

The issue arises when the program requires a target type that carries more information than the source data. `YearMonth` is sufficient for a reconciliation month; `LocalDate` additionally requires a day of the month; `LocalDateTime` requires both a date and a time; obtaining a specific instant also requires knowing the UTC offset or an appropriate time zone.

Therefore, before "fixing a parse error", you need to determine **whether the source actually provides that information**. Any supplementary value must come from business rules, external context, or a defined default—not from the library guessing the input's intent.

## 2. What additional information does the target type require?

| Source data | Type that preserves the exact available information | What is still missing for another type? |
| --- | --- | --- |
| `2025-06` | `YearMonth` | `LocalDate` needs a day of the month |
| `2025-06-10` | `LocalDate` | `LocalDateTime` needs a time of day |
| `14:30` | `LocalTime` | `LocalDateTime` needs a specific date |
| `2025-06-10T09:00` | `LocalDateTime` | `OffsetDateTime` needs an offset; `ZonedDateTime` needs an appropriate zone/offset |
| `09:30` in 12-hour convention | Not enough to distinguish AM/PM | Needs AM/PM information or an explicit contextual rule |

These are examples of information, not an exhaustive list of every field set that can form a date. A date can also be specified by a year and a day-of-year. What matters is whether the parsed fields are sufficient to resolve into the target type, rather than merely counting whether the string contains familiar field names.

You also need to distinguish between:

- **Missing field:** there is no day in `2025-06`.
- **Invalid field value:** there is a day 31 in `2025-02-31`.
- **Syntax error:** separators or widths do not match the pattern.

Supplying a default day can handle the first case if the contract allows it; it must not be used to replace or mask the latter two cases.

## 3. Three intentional approaches

### Keep a type that accurately reflects the data

If the business domain refers to a month, storing `YearMonth` preserves the meaning better than arbitrarily choosing day 1. When you actually need to compute the start of the month, you can call `atDay(1)` at that step. That way, readers of the code see the explicit decision to convert a month into a date.

Similarly, a birth date only needs `LocalDate`; there is no need to force it into `LocalDateTime` or `Instant` just to avoid "missing time" data. A type with fewer fields may be the exact model of the problem, not incomplete data.

### Supplement after parsing using combination methods

If the rule states that an appointment is at 09:00 on the chosen date, parse the date into `LocalDate` and then call `atTime(9, 0)`. If a file only has a time and the date is provided by the report header, parse `LocalTime` and then call `atDate(reportDate)`.

According to [Java SE 21 — LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html), a date does not contain a time or a time zone. Methods such as `atTime()` produce combined values; they make it clear where the supplementary information is introduced.

If the rule selects the start of the day, `date.atStartOfDay()` creates a `LocalDateTime` at 00:00. With `date.atStartOfDay(zone)`, the API picks the earliest valid instant of that day according to the zone rules; in zones with offset transitions, you should not assume the result is always 00:00. Choosing the start of the day is an application rule, not the default meaning of every date string.

### Put defaulting rules into the formatter

When a formal input format allows certain fields to be omitted, `DateTimeFormatterBuilder.parseDefaulting(field, value)` can supply a value for a field that was not parsed. This rule belongs to the formatter; every place that uses that formatter will apply the same defaulting behavior.

According to [Java SE 21 — parseDefaulting()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html#parseDefaulting(java.time.temporal.TemporalField,long)), the value is only inserted if the field is not already present at that point in the builder chain. The defaulting takes effect immediately, so defaulting calls are usually placed after the corresponding parsing step.

## 4. Complete verification program

Save the following code to `MissingFieldsDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.ChronoField;
import java.util.Locale;
import java.util.function.Supplier;

public class MissingFieldsDemo {
    private static void show(String label, Supplier<?> action) {
        try {
            System.out.println(label + " = " + action.get());
        } catch (DateTimeParseException ex) {
            System.out.println(label + " = DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        show("missing time", () -> LocalDateTime.parse(
                "2025-06-10", DateTimeFormatter.ISO_LOCAL_DATE));
        show("missing day", () -> LocalDate.parse(
                "2025-06", DateTimeFormatter.ofPattern("uuuu-MM")));

        YearMonth billingMonth = YearMonth.parse("2025-06");
        System.out.println("month kept = " + billingMonth);
        System.out.println("chosen first day = " + billingMonth.atDay(1));
        LocalDate date = LocalDate.parse("2025-06-10");
        LocalDateTime appointment = date.atTime(9, 0);
        System.out.println("chosen time = " + appointment);
        System.out.println("time plus date = "
                + LocalTime.parse("14:30").atDate(date));

        DateTimeFormatter monthOrDate = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM[-dd]")
                .parseDefaulting(ChronoField.DAY_OF_MONTH, 1)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        show("default day", () -> LocalDate.parse("2025-06", monthOrDate));
        show("provided day", () -> LocalDate.parse("2025-06-15", monthOrDate));
        show("invalid day", () -> LocalDate.parse("2025-02-31", monthOrDate));

        DateTimeFormatter dateOrDateTime = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd['T'HH:mm]")
                .parseDefaulting(ChronoField.HOUR_OF_DAY, 9)
                .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                .toFormatter(Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        show("default clock", () -> LocalDateTime.parse(
                "2025-06-10", dateOrDateTime));
        show("provided clock", () -> LocalDateTime.parse(
                "2025-06-10T14:30", dateOrDateTime));

        ZoneId sourceZone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime zoned = appointment.atZone(sourceZone);
        System.out.println("chosen zone = " + zoned);
        System.out.println("instant = " + zoned.toInstant());
        show("formatter zone", () -> ZonedDateTime.parse(
                "2025-06-10T09:00:00",
                DateTimeFormatter.ISO_LOCAL_DATE_TIME.withZone(sourceZone)));
        show("zone without time", () -> ZonedDateTime.parse(
                "2025-06-10",
                DateTimeFormatter.ISO_LOCAL_DATE.withZone(sourceZone)));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 MissingFieldsDemo.java
java MissingFieldsDemo
```

Output:

```text
missing time = DateTimeParseException
missing day = DateTimeParseException
month kept = 2025-06
chosen first day = 2025-06-01
chosen time = 2025-06-10T09:00
time plus date = 2025-06-10T14:30
default day = 2025-06-01
provided day = 2025-06-15
invalid day = DateTimeParseException
default clock = 2025-06-10T09:00
provided clock = 2025-06-10T14:30
chosen zone = 2025-06-10T09:00+07:00[Asia/Ho_Chi_Minh]
instant = 2025-06-10T02:00:00Z
formatter zone = 2025-06-10T09:00+07:00[Asia/Ho_Chi_Minh]
zone without time = DateTimeParseException
```

The `show` helper is only used to display errors with a stable exception name. In a real application, errors should be preserved or translated into appropriate input feedback rather than treating an exception name as a time value.

The first two calls chose formatters that correctly parsed the date or year-month portion, yet the target type still could not be created because fields were missing. This shows that successfully consuming the entire string does not guarantee there is enough data to construct the desired object.

## 5. A closer look at optional parts and default values

### A month with or without a day

The pattern `uuuu-MM[-dd]` consists of a mandatory year-month part and an optional `-dd` part. The `[]` brackets are formatter control syntax, not two literal characters that must appear in the input.

The `.parseDefaulting(ChronoField.DAY_OF_MONTH, 1)` call comes after the pattern. In the program:

- `2025-06` has no day, so day 1 is supplied and we get `2025-06-01`.
- `2025-06-15` already has day 15, so day 15 is kept.
- `2025-02-31` already has day 31, so it is not replaced with day 1; `STRICT` mode rejects the nonexistent date.

Simply placing `parseDefaulting(DAY_OF_MONTH, 1)` after a **mandatory** pattern `uuuu-MM-dd` does not make the day part optional. The parser still demands the day characters and will fail before reaching the defaulting step. To accept missing fields, you must design both the optional syntax and the value needed to complete the result.

Do not place a default before a formatter section that can parse that same field and expect a later value to always overwrite it. Once a default has been entered into the parse state, data parsed later may conflict with it. Builder order matters.

### A date with or without a time

The pattern `uuuu-MM-dd['T'HH:mm]` allows both the `T` and the hour-minute part to be omitted together. Then the two defaulting calls supply 09 hours and 00 minutes if they are not yet present. Therefore, a plain date produces a `LocalDateTime` at 09:00, while an input with `T14:30` preserves 14:30.

In this example, seconds and nanoseconds do not appear; resolving hours and minutes completes the smaller units with 0. Do not infer that the API automatically fills in larger units: omitting the entire time does not automatically generate 09:00, and omitting the date does not automatically use the current date. The 09:00 values in this article come from explicit defaulting calls or `atTime(9, 0)`.

The pattern used here only accepts time down to the minute. A string with `:ss` appended is outside this contract unless a rule for parsing seconds is added. A defaulting declaration does not ignore extra characters or fix syntax that differs from the pattern.

## 6. Time zone as separate supplementary information

`appointment` in the program is only a local date-time. When the source is known to belong to `Asia/Ho_Chi_Minh`, we use `atZone(sourceZone)` to create a `ZonedDateTime`, then call `toInstant()` to obtain the instant. For the date and time in the example, 09:00 at offset `+07:00` corresponds to 02:00 UTC.

If the source directly specifies a fixed offset rather than a zone name, you can use `localDateTime.atOffset(ZoneOffset.of("+07:00"))`. A fixed offset and a zone name are not always interchangeable: a zone name carries offset rules over dates, whereas a `ZoneOffset` only represents one specific offset.

The program also demonstrates `ISO_LOCAL_DATE_TIME.withZone(sourceZone)`: the string does not record a zone, but the formatter supplies the configured zone, so there is enough information to create a `ZonedDateTime`. This is an explicit application configuration; the parser is not auto-detecting a location from the numbers.

The `zone without time` line still fails because there is only a date and a zone, with no time. `withZone()` is not a default for every missing field. To get the start of the day in a known zone, explicitly choose `LocalDate.parse(text).atStartOfDay(sourceZone)`; if you want an appointment at 09:00, combine the time before attaching the zone.

In zones with daylight saving transitions, a local time can fall into a gap or correspond to two offsets. Having a zone name does not mean every business requirement is solved; you need to decide how to handle those cases when they fall within your application's data range.

## 7. Things to keep in mind when using supplementary values

**Do not use the machine clock to fill in missing parts arbitrarily.** If a report only records the time, the date must come from the reporting period or a deterministic context. Calling `LocalDate.now()` can cause the same file imported on two different days to produce two different results.

**Do not change the resolver mode expecting it to invent missing data.** `SMART` or `LENIENT` adjust how parsed fields are resolved; they cannot know a year, day, or zone that the source omitted. Defaults must be described by explicit contracts and code.

**Keep a record if you need to distinguish real data from defaulted data.** Once a `LocalDateTime` has been created, the object does not remember whether 09:00 was entered by the user or supplied by the program. If the distinction affects business logic, store separately whether the field was provided rather than trying to infer it from the final value.

**Still validate after supplementing.** For example, a default day of 31 is not valid for every month. The formatters in the program use `STRICT` to catch nonexistent combinations; beyond that, the application still needs to check domain constraints such as allowed scheduling date ranges.

Exercise: if the reconciliation month contract changes to "take the last day of the month", parse `YearMonth` and call `atEndOfMonth()` instead of defaulting to day 31. For `2025-02`, the result is `2025-02-28`; for `2024-02`, the result is `2024-02-29`. Since the supplementary value now depends on the month and year, a constant `parseDefaulting(DAY_OF_MONTH, 31)` cannot express the rule properly.
