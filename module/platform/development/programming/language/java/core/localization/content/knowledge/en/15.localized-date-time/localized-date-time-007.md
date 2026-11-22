# withZone, withChronology, and withDecimalStyle in DateTimeFormatter (Java)

## 1. Three Distinct Configuration Layers for Localized Dates and Times

`java.time.format.DateTimeFormatter` is the date/time formatting and parsing API in Java 8+ (including Java 17). Beyond patterns and `Locale`, a formatter has three important override methods:

- **`withZone(ZoneId)`**: sets a **time-zone override** so the formatter can process an instant or supply a zone in certain format/parse scenarios. It does not alter the source `Instant` and does not change the JVM's default time zone.
- **`withChronology(Chronology)`**: sets the **calendar system** used when formatting or parsing, such as ISO-8601/Gregorian, Japanese, or Thai Buddhist calendars. It is not a time-zone conversion.
- **`withDecimalStyle(DecimalStyle)`**: sets the **representation of digits and numeric symbols** (zero digit, plus sign, minus sign, decimal separator) used by the formatter. It is not a calendar or time-unit conversion.

A message expressing "the same date and time" has at least three dimensions to determine:

| Question | Mechanism | Example |
| --- | --- | --- |
| What time does the local clock show at that instant? | `ZoneId` / `withZone` | UTC `00:30`, Ho Chi Minh City `07:30` for the same `Instant`. |
| How does the calendar name the year, era, and date? | `Chronology` / `withChronology` | ISO year 2024, Thai Buddhist year 2567. |
| Which characters are used to write the digits? | `DecimalStyle` / `withDecimalStyle` | `2024` or `٢٠٢٤`. |

**Do not equate `Locale` with zone, chronology, or decimal style.** Locale can provide language context for month/weekday names and format styles, whereas zone is instant semantics, chronology is the calendar system, and decimal style is the set of display symbols. Depending on the API and formatter, some defaults may derive from a locale, but when an application needs deterministic results, configure them explicitly.

## 2. DateTimeFormatter Is Immutable: `with...` Methods Return a New Formatter

`DateTimeFormatter` is **immutable** and safe to share across threads when its configuration does not change. Methods such as `withZone`, `withChronology`, `withDecimalStyle`, `withLocale`, and `withResolverStyle` all **return a new formatter object** with the corresponding override; they do not mutate the original formatter.

```java
DateTimeFormatter base =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm", Locale.US);
DateTimeFormatter inVietnam =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
```

These two statements sit inside a Java method and require importing `java.time.ZoneId`, `java.time.format.DateTimeFormatter`, and `java.util.Locale`.

In the example, `base` still has no zone override; `inVietnam` has the Ho Chi Minh City zone. If you call `base.withZone(...)` **without capturing the return value**, `base` remains unchanged:

```java
base.withZone(ZoneId.of("UTC")); // Return value ignored!
```

With an immutable formatter, the proper way is to assign to a new variable (or reassign if the variable is not `final`). Benefit: you can keep one base formatter and derive market-specific variants without altering shared configuration.

### Distinguishing what `get...` returns

Getter APIs let you inspect state:

- `getZone()` returns the `ZoneId` override or `null` if unset.
- `getChronology()` returns the `Chronology` override or `null` if unset.
- `getDecimalStyle()` returns the active symbol set (typically defaulting to `DecimalStyle.STANDARD` on basic formatters).
- `getLocale()` returns the formatter's locale, not proof that every zone/chronology/decimal-style setting was derived from that locale.

If a formatter already has separate overrides, changing one dimension with `withZone` does not cause the remaining dimensions to shift automatically.

## 3. withZone(ZoneId): Displaying an Instant in a Time Zone

### 3.1. When the argument is an Instant

`Instant` represents a point on the UTC timeline without an attached display time zone. To format an `Instant` into local date/time fields, the formatter needs a `ZoneId`.

```java
Instant instant = Instant.parse("2024-01-02T00:30:00Z");
DateTimeFormatter base = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm VV", Locale.US);

DateTimeFormatter utc = base.withZone(ZoneId.of("UTC"));
DateTimeFormatter hcm =
        base.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(utc.format(instant));
// 2024-01-02 00:30 UTC

System.out.println(hcm.format(instant));
// 2024-01-02 07:30 Asia/Ho_Chi_Minh
```

This is a snippet inside a Java method; the standalone runnable example is in section 7. The outputs differ because Ho Chi Minh City has an offset of UTC+07:00 at the example instant. **`Instant` remains the exact same moment**, without seven hours being added to the source data.

Meaning of `VV` in the pattern: prints the **zone ID**, such as `Asia/Ho_Chi_Minh`. Do not confuse it with `XXX` (formatted offset), `z` (localized zone display name), or `HH` (hour). Choose the symbol that matches your display requirement, and avoid confusing a fixed offset `+07:00` with a region zone that has historical or transition rules.

### 3.2. withZone is not manual hour addition/subtraction

Do not convert an instant to local time by adding 7 hours to epoch milliseconds or turning an `Instant` into a zone-less `LocalDateTime` and storing it as another instant. Time-zone policies can change across eras and regions; `ZoneId` together with historical rules from the TZDB database is the authoritative source.

Meaningful ways to express it:

```java
Instant instant = Instant.parse("2024-01-02T00:30:00Z");
ZonedDateTime local = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Now `local` represents the same instant with a zone attached. When multiple views of the same instant are needed, keep `Instant` (or an appropriate offset/zoned type) in the domain layer, and apply formatters per presentation target.

### 3.3. When the data is LocalDate or LocalDateTime

`LocalDate` has only a date; `LocalDateTime` has date and time but **no zone or offset**. `withZone(...)` does not assume a `LocalDateTime` is UTC and shift it to local time.

With a pattern using only local fields:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(formatter.format(
        LocalDateTime.of(2024, 1, 2, 0, 30)));
// 2024-01-02 00:30
```

The input has no `Instant` or offset to convert, so the date/time fields are taken directly from `LocalDateTime`. Conversely, formatting `Instant.parse("2024-01-02T00:30:00Z")` with that exact same formatter yields `2024-01-02 07:30`.

**Do not overgeneralize from this to conclude every pattern can format every `TemporalAccessor`.** If a pattern demands fields missing from the input (such as `VV` without an available zone, `HH` on a `LocalDate`, or an offset on data lacking an offset), you can hit `UnsupportedTemporalTypeException`/`DateTimeException`. Pick an input type with sufficient information and test the pattern in use.

### 3.4. withZone when parsing

`withZone` can supply a zone override to interpret a string **without a zone** as an instant when date and time are present:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));

Instant parsed = Instant.from(
        formatter.parse("2024-01-02 07:30"));
// 2024-01-02T00:30:00Z
```

However, **not every offset-less string can be resolved to an `Instant`**: if date or time is missing, or the time representation is invalid, the resolver may not construct all required fields. When the input already contains an offset or zone, precedence between the parsed text and the override depends on the fields and how `INSTANT_SECONDS` is resolved; test real cases. Do not treat `withZone` as an unconditional "force time zone" on arbitrary inputs.

### 3.5. Zone, Offset, and DST

A region zone like `America/New_York` transitions into and out of daylight saving time. For a `LocalDateTime` falling inside a **gap** (nonexistent hour) or **overlap** (repeated hour), mapping from local time to an absolute instant requires explicit rules. Selecting a `ZoneId` does not replace business decisions about gaps and overlaps, especially in scheduling, billing, and audit logs.

Given a known `Instant`, converting to local time is unique at that moment. Given a local wall-clock time without an offset, you must define how to resolve ambiguity.

## 4. withChronology(Chronology): Changing the Calendar System for Display and Parsing

### 4.1. What is Chronology?

`Chronology` (in `java.time.chrono`) describes how a calendar system organizes years, months, days, and eras. Built-in chronologies in Java include:

- `IsoChronology.INSTANCE`: ISO-8601 system, the default for `LocalDate`.
- `JapaneseChronology.INSTANCE`: Japanese calendar with its eras.
- `ThaiBuddhistChronology.INSTANCE`: Thai Buddhist calendar.
- `MinguoChronology.INSTANCE`: Minguo calendar.
- `HijrahChronology.INSTANCE`: a Hijrah calendar with its own data and constraints.

**Do not confuse a chronology with a time zone or a language.** Someone can read English text about a date in the Thai Buddhist calendar; choosing a chronology specifies how calendar fields are computed, while era/month names still need an appropriate locale.

### 4.2. ISO vs. Thai Buddhist example

```java
LocalDate isoDate = LocalDate.of(2024, 1, 2);
DateTimeFormatter calendar = DateTimeFormatter.ofPattern(
        "G uuuu-MM-dd", Locale.ENGLISH);

System.out.println(calendar.format(isoDate));
// AD 2024-01-02

System.out.println(calendar
        .withChronology(ThaiBuddhistChronology.INSTANCE)
        .format(isoDate));
// BE 2567-01-02
```

Both lines refer to **the same actual day mapped across calendar systems**, while the year number and era differ. `withChronology` converts the date to the selected chronology for display; it does not turn `isoDate` into year 2567 in the ISO system, nor does it shift the instant by time zone.

In the pattern:

- `G`: era.
- `uuuu`: proleptic year of the active chronology.
- `MM`: numeric month.
- `dd`: day of month.

The example uses `Locale.ENGLISH` so era names `AD` and `BE` produce verifiable output. Under other locales, era names may differ due to localization data.

### 4.3. Parsing with a chronology override

When a formatter has `withChronology(ThaiBuddhistChronology.INSTANCE)`, it can read dates written in the Thai calendar. You can extract:

```java
DateTimeFormatter thai = DateTimeFormatter
        .ofPattern("G uuuu-MM-dd", Locale.ENGLISH)
        .withChronology(ThaiBuddhistChronology.INSTANCE);

String view = thai.format(LocalDate.of(2024, 1, 2));
// "BE 2567-01-02"

ThaiBuddhistDate thaiDate =
        ThaiBuddhistDate.from(thai.parse(view));
// ThaiBuddhist BE 2567-01-02

LocalDate backToIso = LocalDate.from(thai.parse(view));
// 2024-01-02
```

This is a Java snippet inside a method requiring imports for `LocalDate`, `ThaiBuddhistDate`, `ThaiBuddhistChronology`, and `DateTimeFormatter`; the full program is in section 7. Parsing and converting back to `LocalDate` lets you keep ISO domain data consistent, while explicitly specifying the chronology whenever input belongs to another calendar system.

### 4.4. Chronology is more than adding an offset to the year

Do not write an algorithm like "Thai year = ISO year + 543" as a substitute for `Chronology` across languages and calendars. Every calendar has its own era rules, month/year lengths, reign names, historical data, or supported range; a simple arithmetic addition cannot work for Japanese or Hijrah calendars.

For date/time domains, it is usually best to store `LocalDate`/`Instant` with stable semantics and format using a chronology/locale for users when needed. Some applications must store `ChronoLocalDate` if the business genuinely operates in a specific calendar; in that case, clarify conversion and comparison rules before persisting data.

### 4.5. ResolverStyle and invalid calendar data

When parsing, `withChronology` alone does not enforce all application validation rules. It works together with `ResolverStyle` (for example `STRICT`) to validate days, eras, and calendar fields. For critical data, choose a pattern with sufficient fields, and test leap days, era boundaries, and calendar bounds. In particular, `yyyy` (year-of-era) differs from `uuuu` (proleptic year); in strict parsing, an era `G` or matching resolver configuration may be required.

## 5. withDecimalStyle(DecimalStyle): Digits and Numeric Signs

### 5.1. Four components of DecimalStyle

`java.time.format.DecimalStyle` stores the characters used by `DateTimeFormatter` for representing digits and numeric signs:

| API | Meaning | Example |
| --- | --- | --- |
| `getZeroDigit()` | Character for digit 0; subsequent digits are derived from it. | `'0'` or `'٠'` |
| `getPositiveSign()` | Plus sign character. | `'+'` |
| `getNegativeSign()` | Minus sign character. | `'-'` |
| `getDecimalSeparator()` | Decimal separator character when the formatter uses one. | `'.'` or `'٫'` |

`DecimalStyle.STANDARD` uses Latin digits `0–9`, `+`, `-`, and dot `.`. The methods `withZeroDigit(char)`, `withPositiveSign(char)`, `withNegativeSign(char)`, and `withDecimalSeparator(char)` return a new `DecimalStyle` object without mutating the original.

`DecimalStyle.of(locale)` creates a `DecimalStyle` based on JDK-supported locale data. **Do not assume** a locale always uses a single fixed numbering system: users can select another numbering system, and locale/JDK data or extensions can affect it. When exact characters matter, inspect the created `DecimalStyle` or supply an explicit style.

### 5.2. Changing digits does not change the date value

For example, an ISO date is still January 2, 2024 even when printed with Arabic-Indic digits:

```java
DecimalStyle arabicDigits = DecimalStyle.STANDARD
        .withZeroDigit('\u0660');

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US)
        .withDecimalStyle(arabicDigits);

String view = formatter.format(LocalDate.of(2024, 1, 2));
// "٢٠٢٤-٠١-٠٢"

LocalDate date = LocalDate.parse(view, formatter);
// 2024-01-02
```

`withDecimalStyle` changes only **how numeric characters are read and written**; it does not switch the chronology to Hijrah, shift times, translate month names, or alter literal text inside the pattern. The `-` between year/month/day in `"uuuu-MM-dd"` is **literal text**, so it still renders as ASCII `-`, even though `DecimalStyle` can change the negative sign for signed numeric fields.

### 5.3. Decimal separator: applies only where formatting uses it

Not every dot `.` in a pattern is replaced by `DecimalStyle.getDecimalSeparator()`. If you write a literal `"."` in a pattern, it remains a literal dot. `DecimalStyle`'s decimal separator is used when a formatter is built with an operation that has decimal-fraction semantics, such as `DateTimeFormatterBuilder.appendFraction(..., true)`.

```java
DecimalStyle style = DecimalStyle.STANDARD
        .withZeroDigit('\u0660')
        .withDecimalSeparator('\u066B');

DateTimeFormatter fractional = new DateTimeFormatterBuilder()
        .appendPattern("uuuu-MM-dd HH:mm:ss")
        .appendFraction(ChronoField.NANO_OF_SECOND, 3, 3, true)
        .toFormatter(Locale.US)
        .withDecimalStyle(style);

LocalDateTime t = LocalDateTime.of(
        2024, 1, 2, 3, 4, 5, 123_000_000);
String text = fractional.format(t);
// "٢٠٢٤-٠١-٠٢ ٠٣:٠٤:٠٥٫١٢٣"
```

Here, `٫` (U+066B) is the formatter's decimal separator; `-` and `:` in the pattern are literals and are not converted. If you use `DateTimeFormatter.ofPattern("HH:mm:ss.SSS")`, the dot in the pattern is a literal and is **not guaranteed** to be replaced by a custom `DecimalStyle` separator.

### 5.4. DecimalStyle can affect parsing

Once a formatter is configured for Arabic-Indic digits, an ISO string with ASCII digits can be rejected:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.US)
        .withDecimalStyle(
                DecimalStyle.STANDARD.withZeroDigit('\u0660'));

LocalDate.parse("٢٠٢٤-٠١-٠٢", formatter); // Succeeds.
LocalDate.parse("2024-01-02", formatter); // May throw DateTimeParseException.
```

Key point: the parser is governed by the **configured digit characters**, not just `ResolverStyle`. Therefore, when a UI allows multiple numbering systems, design an explicit selection/normalization policy; do not assume every digit script is accepted automatically by the parser.

Do not silently replace all Unicode digit characters with ASCII on critical inputs. If the product permits normalization, test all supported digit scripts and handle invalid inputs transparently.

## 6. Combining Overrides Together

All three methods can be chained on a single formatter:

```java
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("G uuuu-MM-dd HH:mm VV", Locale.ENGLISH)
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .withChronology(ThaiBuddhistChronology.INSTANCE)
        .withDecimalStyle(
                DecimalStyle.STANDARD.withZeroDigit('\u0660'));
```

This snippet sits inside a Java method and requires importing the relevant classes. Role of each override:

1. `withZone`: resolves the local time of an `Instant` in Ho Chi Minh City.
2. `withChronology`: displays the date in the Thai Buddhist calendar when compatible date data is present.
3. `withDecimalStyle`: prints digits in the specified numbering system.
4. `Locale.ENGLISH` in `ofPattern`: provides context for era names and any localized text elements in the pattern.

When a displayed string contains year-of-era/era, time zone, and a specific digit system, the parser must use the corresponding overrides (or receive an explicit zone/chronology) to interpret it accurately. **Do not expect a string containing only date and time, without zone or era, to always allow lossless recovery of all original information.**

If the requirement is simply a birth date (not a timestamp), `LocalDate` + desired chronology is usually more appropriate than `Instant` + zone, because a birth date is not inherently tied to a UTC instant. Conversely, event logs and timestamps should carry `Instant` along with a display zone when needed.

## 7. Standalone Java 17+ Example: Comparing Zone, Chronology, and Decimal Style

Create the file **`DateTimeFormatterOverridesDemo.java`** below. The example fixes input data, locale, and overrides so the output is verifiable. Do not mutate the JVM's `Locale.setDefault(...)` or `TimeZone.setDefault(...)`.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.DecimalStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class DateTimeFormatterOverridesDemo {

    public static void main(String[] args) {
        Instant instant = Instant.parse("2024-01-02T00:30:00Z");

        DateTimeFormatter zoned = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm VV", Locale.US);

        System.out.println("utc=" + zoned
                .withZone(ZoneId.of("UTC")).format(instant));
        System.out.println("hcm=" + zoned
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .format(instant));

        LocalDate date = LocalDate.of(2024, 1, 2);
        DateTimeFormatter calendar = DateTimeFormatter
                .ofPattern("G uuuu-MM-dd", Locale.ENGLISH);
        System.out.println("iso=" + calendar.format(date));

        DateTimeFormatter thai = calendar
                .withChronology(ThaiBuddhistChronology.INSTANCE);
        String thaiText = thai.format(date);
        System.out.println("thai=" + thaiText);
        System.out.println("thaiParsed="
                + ThaiBuddhistDate.from(thai.parse(thaiText)));
        System.out.println("isoParsed="
                + LocalDate.from(thai.parse(thaiText)));

        DecimalStyle arabicDigits = DecimalStyle.STANDARD
                .withZeroDigit('\u0660');
        DateTimeFormatter numbers = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.US)
                .withDecimalStyle(arabicDigits);
        String text = numbers.format(date);
        System.out.println("digits=" + text);
        System.out.println("parsed=" + LocalDate.parse(text, numbers));

        try {
            LocalDate.parse("2024-01-02", numbers);
            System.out.println("ascii=accepted");
        } catch (DateTimeParseException ex) {
            System.out.println("ascii=rejected");
        }

        DateTimeFormatter clock = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.US)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("local="
                + clock.format(LocalDateTime.of(2024, 1, 2, 0, 30)));
        System.out.println("instant=" + clock.format(instant));

        DecimalStyle fractionalStyle = DecimalStyle.STANDARD
                .withZeroDigit('\u0660')
                .withDecimalSeparator('\u066B');
        DateTimeFormatter fraction = new DateTimeFormatterBuilder()
                .appendPattern("uuuu-MM-dd HH:mm:ss")
                .appendFraction(ChronoField.NANO_OF_SECOND, 3, 3, true)
                .toFormatter(Locale.US)
                .withDecimalStyle(fractionalStyle);
        String fractionalText = fraction.format(LocalDateTime.of(
                2024, 1, 2, 3, 4, 5, 123_000_000));
        System.out.println("fraction=" + fractionalText);
        System.out.println("fractionParsed="
                + LocalDateTime.parse(fractionalText, fraction));
    }
}
```

Compile and run with JDK 17 or newer in the directory containing the file:

```bash
javac -encoding UTF-8 DateTimeFormatterOverridesDemo.java
java DateTimeFormatterOverridesDemo
```

**Exact stdout:**

```text
utc=2024-01-02 00:30 UTC
hcm=2024-01-02 07:30 Asia/Ho_Chi_Minh
iso=AD 2024-01-02
thai=BE 2567-01-02
thaiParsed=ThaiBuddhist BE 2567-01-02
isoParsed=2024-01-02
digits=٢٠٢٤-٠١-٠٢
parsed=2024-01-02
ascii=rejected
local=2024-01-02 00:30
instant=2024-01-02 07:30
fraction=٢٠٢٤-٠١-٠٢ ٠٣:٠٤:٠٥٫١٢٣
fractionParsed=2024-01-02T03:04:05.123
```

### Reading the output properly

- The two lines `utc`/`hcm` reflect **different zones of the same `Instant`**, not two different events.
- `iso` and `thai` use the same `LocalDate` with different chronologies, so the year number and era differ.
- `thaiParsed` is a Thai Buddhist calendar date type; `isoParsed` converts that same date back to an ISO `LocalDate`.
- `digits` prints Arabic-Indic digits, while the hyphens in the pattern remain ASCII literal hyphens.
- `parsed` recovers the original `LocalDate` when using the same formatter; `ascii=rejected` highlights the need to account for the parser's digit characters.
- `local` and `instant` show that `LocalDateTime` does not shift time just because the formatter has a zone, whereas `Instant` is converted according to the zone.
- `fraction` and `fractionParsed` demonstrate that the decimal separator comes from `DecimalStyle` when the formatter is built with `appendFraction(..., true)`.

## 8. Common Mistakes

| Mistake | Why it is wrong | Proper approach |
| --- | --- | --- |
| Calling `formatter.withZone(zone)` and discarding the result | `DateTimeFormatter` is immutable. | Assign the returned formatter. |
| Changing locale and assuming the timezone also changed | Locale and zone are two separate concepts. | Select `ZoneId` separately from context. |
| Treating `LocalDateTime` as an implicit UTC `Instant` | `LocalDateTime` has no zone or offset. | Determine the region/time zone before mapping to `Instant`. |
| Manually adding hours to "switch zones" | DST and historical rules can be complex. | Use `ZoneId`/`ZonedDateTime`. |
| Treating `withChronology` as adding 543 to the ISO year | Each calendar system has its own rules. | Use `Chronology`/`ChronoLocalDate`. |
| Thinking `ThaiBuddhistDate` is permanently mutated ISO year data | It is a date representation in its own chronology. | Define storage format and conversions explicitly. |
| Using `yyyy` in strict parsing without an era | Year-of-era differs from proleptic year. | Use `uuuu` if appropriate or supply an era. |
| Thinking `withDecimalStyle` changes every literal `.` character | `DecimalStyle` applies only to numeric symbols handled by the formatter. | Use `appendFraction(..., true)` when decimal-separator styling is needed. |
| Thinking `DecimalStyle` switches the calendar to Arabic/Hijrah | `DecimalStyle` covers only digit and sign symbols. | Choose `Chronology` independently. |
| Formatting with Arabic-Indic digits yet parsing with an ASCII formatter | The two formatters have different input grammars. | Use the matching style/locale; test Unicode digits. |
| Mutating `TimeZone.setDefault` or `Locale.setDefault` per request | JVM-wide shared state that can affect other threads. | Pass formatter/zone/locale explicitly. |
| Using one pattern on every `TemporalAccessor` | Not every type carries all fields. | Pick the right type and test every field in the pattern. |

## 9. Choosing the Right Data Type Before Formatting

| Application data | Typical Java type | When overrides are needed |
| --- | --- | --- |
| Date without time/timezone, e.g., birthday | `LocalDate` | `withChronology`/`withDecimalStyle` if the UI needs another calendar or digit script. |
| Local appointment time without an attached zone | `LocalDateTime` + `ZoneId` stored/resolved separately | `withZone` is not enough to disambiguate gaps/overlaps; need rules to convert to `ZonedDateTime`. |
| Absolute event instant | `Instant` | `withZone` to display local date/time, combined with chronology/decimal style as needed. |
| Date-time with a time-zone region | `ZonedDateTime` | Formatter can keep the data's zone or override it; decide intentionally. |
| Date in a non-ISO calendar | `ChronoLocalDate`/specific chronology type | Choose chronology explicitly and control conversion to ISO if needed. |
| Localized date/time input | `String` + clearly configured formatter | Parse with the right zone, chronology, decimal style, resolver style, and domain constraints. |

Do not use `Instant` for a pure calendar date that has no time of day; do not use `LocalDateTime` as a global timestamp. Choosing the data type is a domain responsibility before thinking about formatting patterns.

## 10. Validation and Testing of Overrides

When parsing or accepting UI input:

1. **Syntax and locale check:** does the string match the pattern, digits, and signs of the chosen `DecimalStyle`? Is there trailing text?
2. **Chronology check:** is the date/era valid in the user's chosen calendar, and within the supported range?
3. **Zone and instant semantics check:** if the input is a local date-time, is there a DST gap/overlap and what policy applies? Never assume input is UTC.
4. **Domain check:** is the date within the allowed range, has a deadline passed, and is the year/era meaningful in the domain?
5. **Reproducibility check:** pin `Instant`, `ZoneId`, `Locale`, `Chronology`, `DecimalStyle`, Java version, and TZDB data when exact output matters.

`DateTimeFormatter.parse` can throw `DateTimeParseException` when a string does not match the pattern or cannot be resolved, yet successful parsing does not guarantee all business policies are satisfied. With a pattern lacking enough data for the target type, `Instant.from(...)`/`LocalDate.from(...)` can still fail.

### Short test matrix

| Scenario | Expectation |
| --- | --- |
| Same `Instant` with UTC and `Asia/Ho_Chi_Minh` | Same instant, different local times. |
| `LocalDateTime` formatted by a formatter with a zone | Does not infer a conversion from UTC without an instant/offset. |
| `ThaiBuddhistChronology` and ISO | Same day, different year/era displayed. |
| Parsing `ThaiBuddhist` text into ISO `LocalDate` | Converts to the exact ISO date when data is complete. |
| Arabic-Indic digits + matching `DecimalStyle` | Formatting/parsing matches when using the same style. |
| ASCII digits with a formatter expecting Arabic-Indic | Rejected or handled per defined policy. |
| Decimal separator via `appendFraction(..., true)` | Uses `DecimalStyle`'s separator, not literal `.`. |
| Valid Feb 29 and nonexistent dates | `ResolverStyle` configured to validate properly. |
| DST overlap/gap in a zone with clock transitions | Applies an explicit local-time resolution policy. |

## 11. Practice Exercises

**Exercise 1 — Local time:** format `Instant.parse("2024-01-02T00:30:00Z")` with `"uuuu-MM-dd HH:mm VV"` using `UTC` and `Asia/Ho_Chi_Minh`. Try replacing `Instant` with `LocalDateTime`. Explain why you cannot take any `LocalDateTime` and treat it as UTC to shift hours.

**Exercise 2 — Non-ISO calendar:** format `LocalDate.of(2024, 1, 2)` in `ThaiBuddhistChronology` with pattern `"G uuuu-MM-dd"`, and parse it back into `ThaiBuddhistDate` and `LocalDate`. Try switching `Locale.ENGLISH` to another locale and inspect how the era text changes.

**Exercise 3 — Digits:** create a `DecimalStyle` starting at `'٠'` and format `LocalDate.of(2024, 1, 2)`. Try parsing with the Arabic-Indic digit formatter and with a standard formatter. State what input rule a form should enforce if both numbering systems must be supported.

**Exercise 4 — Fractional seconds:** use `DateTimeFormatterBuilder.appendFraction(NANO_OF_SECOND, 3, 3, true)` and set `withDecimalStyle` using U+066B. Compare the result with a pattern using a literal dot; explain why not every `.` is replaced.

**Exercise 5 — Combined configuration:** create a formatter with `withZone` Ho Chi Minh City, `withChronology` Thai Buddhist, and `withDecimalStyle` Arabic-Indic. Given the same `Instant`, toggle each override individually and identify which output fields are affected.

**Exercise 6 — Parsing with zone:** parse `"2024-01-02 07:30"` using a formatter with `withZone(Asia/Ho_Chi_Minh)` and convert to `Instant`. Verify the expected result `2024-01-02T00:30:00Z`. Then examine a local time falling in a DST overlap/gap in an appropriate zone and design a way to detect non-unique instants.

## 12. Completion Checklist

- [ ] Clearly distinguish `ZoneId`, `Chronology`, and `DecimalStyle`.
- [ ] Know that `withZone`, `withChronology`, and `withDecimalStyle` return new formatters without mutating the old one.
- [ ] Know when `withZone` converts an instant (with `Instant`/offset) and when there is not enough semantics to convert (pure `LocalDateTime`).
- [ ] Understand that chronology can change era/year without changing the actual calendar day.
- [ ] Know that a formatter's digits and decimal separator can be controlled by `DecimalStyle`, unlike literal characters in the pattern.
- [ ] Choose the right data type—`Instant`/`LocalDate`/`LocalDateTime`/`ChronoLocalDate`—before formatting.
- [ ] Format and parse with explicit locale, chronology, decimal style, and zone; also verify resolver/domain constraints.
- [ ] Write tests for Unicode digits, non-ISO calendar dates, UTC vs. local time, and DST where required by the domain.

**Conclusion:** `withZone` determines the **time zone for expressing an instant**, `withChronology` determines the **calendar system**, and `withDecimalStyle` determines **numeric symbols**. They can be combined, yet cannot replace one another; a formatter does not mutate source data or JVM-global settings. The essence of localization is choosing the right **temporal data type** and passing complete context before rendering or parsing.
