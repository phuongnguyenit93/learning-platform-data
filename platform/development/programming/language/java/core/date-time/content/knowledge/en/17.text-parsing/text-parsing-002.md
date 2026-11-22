# Parse ISO Strings Before Building Custom Patterns

## Start from the data, not from `ofPattern()`

When receiving a string like `2024-06-15T09:30:45+07:00`, the reflex to immediately write a pattern such as `"yyyy-MM-dd'T'HH:mm:ssXXX"` often makes the job more complicated than necessary. The `java.time` library already has parsers for common ISO formats.

The first step is to determine whether the string carries a **date**, a **time**, a **local date-time**, or an **instant with a UTC offset/time zone**. Then choose the Java type that preserves that exact information and try the built-in `parse` method. Only build a custom pattern when the data contract genuinely differs from the already supported formats.

In this lesson, "parsing" means converting text into a typed temporal value. It differs from "formatting," which means converting a value back into text. The input text format and the output display format do not necessarily match character for character.

## 1. Read the structure first, then the meaning

Break the example string into meaningful parts:

```text
2024-06-15 T 09:30:45 +07:00
──────────   ──────── ──────
date         time     offset from UTC
           ↑
      date and time separator
```

Cues that help identify the parts:

- `2024-06-15`: date in year–month–day order.
- `09:30:45`: hour–minute–second, which does not by itself indicate a date or time zone.
- `T`: separator between the date part and the time part.
- `.123` after seconds: fractional seconds.
- `Z`: zero UTC offset.
- `+07:00`: positive seven-hour UTC offset; this is not yet a time-zone region name.
- `[Asia/Ho_Chi_Minh]`: time-zone region ID in the extended format that Java supports for zoned date-times.

The `Z` and `+07:00` markers are not decorative parts to strip away for readability. They contribute to determining the instant in time.

A pattern that looks almost like ISO does not necessarily match the default parser: `2024-06-15 09:30:45` has a space instead of `T`. Conversely, ISO is not a single format either: the library also has formatters for basic (compact) dates, ordinal dates, or week dates. Check the exact variant being communicated, rather than assuming every "ISO" string is accepted by a single method.

## 2. Choose the target type that matches the input information

| Example string | Usually appropriate target type | Initial call |
| --- | --- | --- |
| `2024-06-15` | `LocalDate` | `LocalDate.parse(text)` |
| `09:30:45` | `LocalTime` | `LocalTime.parse(text)` |
| `2024-06-15T09:30:45` | `LocalDateTime` | `LocalDateTime.parse(text)` |
| `2024-06-15T09:30:45+07:00` | `OffsetDateTime` | `OffsetDateTime.parse(text)` |
| `2024-06-15T02:30:45Z` | `Instant` if a point on the timeline is needed | `Instant.parse(text)` |
| `2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | `ZonedDateTime.parse(text)` |

The default methods use the corresponding ISO formatter; for example, `LocalDate.parse` uses `ISO_LOCAL_DATE`, while `OffsetDateTime.parse` uses `ISO_OFFSET_DATE_TIME`. [`LocalDate.parse` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#parse(java.lang.CharSequence)), [`OffsetDateTime.parse` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html#parse(java.lang.CharSequence))

A few points to keep clear when choosing a type:

- `LocalDate` holds no time or time zone; suitable for a study date or birth date.
- `LocalDateTime` does not have enough information to uniquely identify a global instant on its own.
- `OffsetDateTime` holds a date-time together with a UTC offset. Convert it to `Instant` when you need to compare or store a point in time without keeping the original offset.
- `ZonedDateTime` additionally holds a zone ID and time-zone rules.
- `Instant` represents a point on the timeline; a UTC string ending in `Z` is a common format when transmitting event timestamps. [`Instant` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

For example, if an assignment submission notification arrives at `09:30:45+07:00`, dropping `+07:00` and storing a `LocalDateTime` loses the instant information. Convenience during parsing must not alter the meaning of the data.

## 3. A complete program: using the built-in parsers

Save as `IsoParsingDemo.java`. The program runs on Java 17 or later:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class IsoParsingDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.parse("2024-06-15");
        LocalTime time = LocalTime.parse("09:30:45");
        LocalDateTime local =
                LocalDateTime.parse("2024-06-15T09:30:45.123");

        OffsetDateTime offset =
                OffsetDateTime.parse("2024-06-15T09:30:45+07:00");
        Instant instant = Instant.parse("2024-06-15T02:30:45Z");

        ZonedDateTime zoned = ZonedDateTime.parse(
                "2024-06-15T09:30:45+07:00[Asia/Ho_Chi_Minh]");

        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("local=" + local);
        System.out.println("offset=" + offset);
        System.out.println("instant=" + instant);
        System.out.println("sameInstant=" + offset.toInstant().equals(instant));
        System.out.println("zone=" + zoned.getZone().getId());

        LocalDate basic =
                LocalDate.parse("20240615", DateTimeFormatter.BASIC_ISO_DATE);
        System.out.println("basic=" + basic);

        try {
            LocalDate.parse("2023-02-29");
            System.out.println("invalidDateAccepted");
        } catch (DateTimeParseException ex) {
            System.out.println("invalidDateRejected");
        }

        try {
            LocalDateTime.parse("2024-06-15 09:30:45");
            System.out.println("spaceAcceptedByDefault");
        } catch (DateTimeParseException ex) {
            System.out.println("spaceRejectedByDefault");
        }

        DateTimeFormatter spaceSeparated =
                DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                        .withResolverStyle(ResolverStyle.STRICT);

        LocalDateTime imported = LocalDateTime.parse(
                "2024-06-15 09:30:45", spaceSeparated);
        System.out.println("custom=" + imported);

        LocalTime shortTime = LocalTime.parse("09:30:00");
        System.out.println("shortTime=" + shortTime);
    }
}
```

Compile and run:

```shell
javac --release 17 IsoParsingDemo.java
java IsoParsingDemo
```

Stdout:

```text
date=2024-06-15
time=09:30:45
local=2024-06-15T09:30:45.123
offset=2024-06-15T09:30:45+07:00
instant=2024-06-15T02:30:45Z
sameInstant=true
zone=Asia/Ho_Chi_Minh
basic=2024-06-15
invalidDateRejected
spaceRejectedByDefault
custom=2024-06-15T09:30:45
shortTime=09:30
```

Reading the output by group:

1. Common ISO strings are converted directly into meaningful types without hand-written patterns.
2. The two strings `09:30:45+07:00` and `02:30:45Z` identify the same instant; `sameInstant=true` proves that parsing preserves the offset accurately.
3. The compact date string `20240615` requires `BASIC_ISO_DATE`, but still does not require `ofPattern`.
4. February 29, 2023 does not exist, so it is rejected.
5. The space-separated form is rejected by `LocalDateTime`'s default parser; a custom pattern is used because the input contract here specifies a space.
6. `shortTime=09:30` shows that the time value is preserved accurately even though printing it does not retain the `:00` from the input.

## 4. Having built-in ISO formatters does not mean every variant is accepted

The lookup process should follow three steps:

```text
Know the temporal type and default ISO format?
    └─ Yes: try Type.parse(text)

Differs from the default format, but a matching DateTimeFormatter constant exists?
    └─ Yes: use Type.parse(text, builtInFormatter)

Contract genuinely has custom syntax?
    └─ Build an appropriate pattern or DateTimeFormatterBuilder
```

Examples of commonly useful constants:

| Constant | Purpose |
| --- | --- |
| `ISO_LOCAL_DATE` | Date in `2024-06-15` format |
| `ISO_LOCAL_TIME` | Local time |
| `ISO_LOCAL_DATE_TIME` | Local date-time, with `T` |
| `ISO_OFFSET_DATE_TIME` | Date-time with UTC offset |
| `ISO_ZONED_DATE_TIME` | Date-time with time-zone region information |
| `BASIC_ISO_DATE` | Compact date such as `20240615` |

The full list of built-in constants and detailed syntax are in the [`DateTimeFormatter` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html).

Built-in ISO formatters also handle components that are optional in each format, such as seconds or fractional seconds. A manual fixed pattern like `HH:mm:ss.SSS`, on the other hand, expresses a requirement for a specific number of digits. Do not copy a long pattern from a single sample string and assume it covers the entire contract.

Nor should you switch to a broader `ISO_DATE_TIME` just to make a single parse stop failing. If an interface requires a mandatory UTC offset, ensure that the target type and parser actually preserve and validate that information.

## 5. When is a custom pattern clearly justified?

A custom pattern makes sense when the data source explicitly specifies it, for example:

- Legacy import files use `15/06/2024`.
- Date-times use a fixed space separator: `2024-06-15 09:30:45`.
- Month names in a specific language appear in the data.
- Input requires syntax rules that built-in formatters do not satisfy.

For the space-separated example, the program declared:

```java
DateTimeFormatter spaceSeparated =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
```

Intentional choices:

- `uuuu` is proleptic year; `yyyy` is year-of-era, which are not synonymous in all situations.
- `MM` is month, `mm` is minute.
- `HH` is hour-of-day (24-hour clock).
- `STRICT` requires field combinations to produce a valid date and time.
- `Locale.ROOT` expresses a language-independent configuration for the numeric pattern in the example; if a pattern contains month names, choose the locale that matches the data.

Patterns created by `ofPattern` default to the `SMART` resolver style; therefore, do not assume they have the same handling for nonexistent dates as the strict ISO formatters. [Pattern creation and resolution documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#ofPattern(java.lang.String))

These are only the essentials needed to decide whether a custom pattern is necessary. Before expanding a pattern to accept multiple formats, clearly document which formats must be accepted and which must be rejected.

## 6. Handle errors according to the data contract

A `DateTimeParseException` does not by itself prove that another pattern is needed. It may indicate:

- Syntax error: a space instead of `T`, an incorrect separator, or trailing extra characters.
- Invalid date or time: month 13, nonexistent day.
- Wrong target type: the string only has a date, but the code requests `LocalDateTime`.
- Missing required information: the contract requires a UTC offset, but the string has none.
- Empty data or something completely different from the agreed format.

Before changing code, take a representative input string and ask in order: what format does the source guarantee, does this string match that guarantee, is the target type appropriate, and only then inspect the parser.

The handling skeleton below is an illustrative snippet requiring imports for `LocalDate` and `DateTimeParseException`:

```java
static LocalDate parseLearningDate(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("Ngay hoc khong duoc rong");
    }

    try {
        return LocalDate.parse(text);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Ngay hoc phai la ngay hop le dang ISO nam-thang-ngay", ex);
    }
}
```

This snippet requires the string to match the chosen ISO format, does not call `trim()` automatically, and does not fall back to the current date on failure. If an interface allows leading or trailing whitespace, you can normalize it according to a documented rule before calling the method. If it is a protocol that requires exact strings, keep the input as-is to catch errors.

Do not use `substring`, `replace("T", " ")`, or strip `Z` as a general fix. Those operations can make a string match a pattern more easily while losing data or masking input errors.

## 7. Verify the meaning, not just "no exception thrown"

For the date-time with offset example, successful parsing is only part of verification. Also check:

- Whether the result type retains enough information.
- Whether the date, time, and fractional components are accurate.
- When an offset is present, whether `toInstant()` yields the expected instant.
- Whether invalid data is properly rejected.
- Whether inputs with optional components permitted by the contract work.

A small test suite for a `LocalDate` contract in `2024-06-15` format might include:

| Input | Expected result |
| --- | --- |
| `2024-02-29` | Accepted |
| `2023-02-29` | Rejected |
| `2024-13-01` | Rejected |
| `15/06/2024` | Rejected if the contract only allows this ISO format |
| `20240615` | Rejected with default parse; accepted only when explicitly choosing the basic format |
| `2024-06-15abc` | Rejected |

Additionally, "parse and then print" does not always reproduce the input verbatim. In the program, `09:30:00` became `09:30`. If you need to keep the verbatim string to trace source data, store the original text separately; if you need output with an exact number of digits, format the output according to an explicit contract.

## 8. Self-practice

1. An API sends `2024-06-15T09:30:45+07:00`. Which call should you try before writing a custom pattern?
2. A file sends `20240615`. Is `ofPattern("uuuuMMdd")` strictly necessary?
3. Why can stripping `+07:00` and using `LocalDateTime` corrupt the data?
4. The string `2023-02-29` is rejected. Should you add a fallback pattern so it can be "read"?

Suggested answers:

1. `OffsetDateTime.parse(text)`; if a pure point in time is needed, convert the result to `Instant`.
2. No. You can use `LocalDate.parse(text, DateTimeFormatter.BASIC_ISO_DATE)`.
3. Because the offset helps determine the instant in time; `LocalDateTime` does not retain that information.
4. No. That date does not exist; invalid data should be handled according to the contract.

The habit to build is to read the structure and meaning of the string, choose the target type, leverage built-in ISO parsers, and only add custom patterns when there is a specific input difference that needs to be supported.
