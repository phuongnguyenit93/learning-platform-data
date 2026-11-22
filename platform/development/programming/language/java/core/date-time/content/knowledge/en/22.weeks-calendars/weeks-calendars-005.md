# Chronology and the Relationship Between Calendar Systems and ISO Dates

## The Same Date Can Have Different Field Values Across Calendar Systems

A date written as `2024-06-15` in the ISO calendar can have year `2567` in the Thai Buddhist calendar. If you only see the number 2567 and create `LocalDate.of(2567, 6, 15)`, you have created a different ISO date, not converted the calendar system of the original date.

The difference lies in the **calendar system (chronology)**: the rules for organizing and naming dates using year, month, day, era, and related fields.

In Java, `LocalDate` always uses the ISO calendar system. Changing the display locale does not turn that object into a date belonging to another calendar system. When you need to support multiple calendar systems, you must clearly distinguish between converting the representation of the same date and constructing a date from the fields of a specific calendar system.

## 1. The Role of `Chronology`

`Chronology` is the interface that describes a calendar system and provides ways to create dates according to that calendar system's rules. Built-in implementations include ISO, Japanese, Minguo, Thai Buddhist, and Hijrah. [`Chronology` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/Chronology.html)

A calendar system determines the meaning of fields such as:

- `YEAR`: the year according to that calendar system's continuous numbering.
- `YEAR_OF_ERA`: the year within an era.
- `ERA`: the era.
- `MONTH_OF_YEAR`: the month of the year.
- `DAY_OF_MONTH`: the day of the month.
- Leap-year rules and month lengths.

You must not assume that every calendar system has the same number of months, the same year numbering, or the same relationship between year and era.

You can distinguish two kinds of objects:

```text
Chronology
    = calendar system rules + methods to create/convert dates

ChronoLocalDate or a concrete date type
    = a date value in that calendar system
```

For example, `ThaiBuddhistChronology.INSTANCE` represents the rules; `ThaiBuddhistDate` represents a date under those rules.

## 2. `LocalDate` Explicitly Chooses ISO

`LocalDate` is not a "date that automatically switches calendar systems based on the machine". It holds a date in the ISO system, without time of day or time zone.

This gives ordinary code stable assumptions when working with year–month–day. For example:

```java
LocalDate iso = LocalDate.of(2024, 6, 15);
```

This snippet creates the ISO date 2024-06-15. It does not mean "June 15, 2024 in any calendar system".

For most applications, using `LocalDate` in the core model and converting intentionally at input/display boundaries is the simpler approach. `ChronoLocalDate` is intended for cases where you genuinely need dates with varying calendar systems; using it throughout an application requires stricter control over calendar assumptions. [Recommendations for using `ChronoLocalDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ChronoLocalDate.html)

Merely choosing a general interface does not make algorithms automatically correct for every calendar system. A calculation that assumes "adding 12 months is always adding one year" still needs to be reviewed when the input calendar system is not known in advance.

## 3. The Conversion Bridge: Absolute Date via `epochDay`

Supported dates can be related through `EPOCH_DAY`: the number of days relative to the ISO date 1970-01-01, where that epoch date has the value `0`.

Two representations in two calendar systems can have different year/month/day fields yet share the same `epochDay`. When converted properly, they point to the same position on the date timeline.

```text
ISO date 2024-06-15
          │
          │ same epochDay
          ▼
Thai Buddhist date 2567-06-15
```

Changing calendar systems means preserving the date that the value represents, not preserving all the numeric field values.

Common calls:

```java
ThaiBuddhistDate thai = ThaiBuddhistDate.from(iso);
LocalDate isoAgain = LocalDate.from(thai);
```

Or via the `Chronology` interface:

```java
ChronoLocalDate converted =
        ThaiBuddhistChronology.INSTANCE.date(iso);
```

These are illustrative snippets assuming `iso` is already defined and the corresponding imports are present.

`epochDay` is a **day** index, not the seconds or milliseconds of an `Instant`. A date without time of day and time zone still does not uniquely identify a global instant.

## 4. Complete Program

Save as `ChronologyIsoDemo.java`. The program uses Java 17 or later:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.JapaneseDate;
import java.time.chrono.MinguoDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ChronologyIsoDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 6, 15);
        ThaiBuddhistDate thai = ThaiBuddhistDate.from(iso);
        MinguoDate minguo = MinguoDate.from(iso);
        JapaneseDate japanese = JapaneseDate.from(iso);

        System.out.println("iso=" + iso);
        System.out.println("isoChronology=" + iso.getChronology().getId());
        System.out.println("thaiChronology=" + thai.getChronology().getId());
        System.out.println("thaiYear=" + thai.get(ChronoField.YEAR));
        System.out.println("minguoYear=" + minguo.get(ChronoField.YEAR));
        System.out.println("japaneseYear=" + japanese.get(ChronoField.YEAR));
        System.out.println("japaneseYearOfEra="
                + japanese.get(ChronoField.YEAR_OF_ERA));

        System.out.println("sameEpochDay="
                + (iso.toEpochDay() == thai.toEpochDay()));
        System.out.println("backToIso=" + LocalDate.from(thai));
        System.out.println("sameDay=" + thai.isEqual(iso));
        System.out.println("equalsAcrossCalendars=" + thai.equals(iso));
        System.out.println("naturalComparisonIsZero="
                + (thai.compareTo(iso) == 0));

        Chronology chronology = Chronology.of("ThaiBuddhist");
        ChronoLocalDate fromFields = chronology.date(2567, 6, 15);
        ChronoLocalDate fromIso = chronology.date(iso);

        System.out.println("createdFromThaiFields=" + LocalDate.from(fromFields));
        System.out.println("convertedFromIso=" + LocalDate.from(fromIso));

        LocalDate copiedAsIso = LocalDate.of(
                thai.get(ChronoField.YEAR),
                thai.get(ChronoField.MONTH_OF_YEAR),
                thai.get(ChronoField.DAY_OF_MONTH));
        System.out.println("copiedFieldsAsIso=" + copiedAsIso);
        System.out.println("copiedFieldsSameDay=" + copiedAsIso.isEqual(iso));

        DateTimeFormatter thaiText =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withChronology(ThaiBuddhistChronology.INSTANCE)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("formattedThai=" + thaiText.format(iso));
        LocalDate parsedIso =
                thaiText.parse("2567-06-15", LocalDate::from);
        System.out.println("parsedThaiToIso=" + parsedIso);

        JapaneseDate before =
                JapaneseDate.from(LocalDate.of(2019, 4, 30));
        JapaneseDate after =
                JapaneseDate.from(LocalDate.of(2019, 5, 1));

        System.out.println("japaneseBefore="
                + before.get(ChronoField.YEAR)
                + "/era=" + before.get(ChronoField.ERA)
                + "/yearOfEra=" + before.get(ChronoField.YEAR_OF_ERA));
        System.out.println("japaneseAfter="
                + after.get(ChronoField.YEAR)
                + "/era=" + after.get(ChronoField.ERA)
                + "/yearOfEra=" + after.get(ChronoField.YEAR_OF_ERA));
    }
}
```

Compile and run:

```shell
javac --release 17 ChronologyIsoDemo.java
java ChronologyIsoDemo
```

Stdout:

```text
iso=2024-06-15
isoChronology=ISO
thaiChronology=ThaiBuddhist
thaiYear=2567
minguoYear=113
japaneseYear=2024
japaneseYearOfEra=6
sameEpochDay=true
backToIso=2024-06-15
sameDay=true
equalsAcrossCalendars=false
naturalComparisonIsZero=false
createdFromThaiFields=2024-06-15
convertedFromIso=2024-06-15
copiedFieldsAsIso=2567-06-15
copiedFieldsSameDay=false
formattedThai=2567-06-15
parsedThaiToIso=2024-06-15
japaneseBefore=2019/era=2/yearOfEra=31
japaneseAfter=2019/era=3/yearOfEra=1
```

## 5. Creating from Fields and Converting from a Date Are Two Different Operations

Both calls in the program produce the ISO date 2024-06-15 after conversion:

```java
chronology.date(2567, 6, 15);
chronology.date(iso);
```

However, their inputs and meanings are different:

- `date(2567, 6, 15)` interprets the numbers according to the selected Thai Buddhist calendar system.
- `date(iso)` takes the date that the ISO value represents and converts its representation.

The `copiedAsIso` snippet intentionally demonstrates the bug: copying year 2567 from the Thai Buddhist date into the `LocalDate` factory produces an ISO date in year 2567. It is not the same date as the original source.

If you receive data consisting of fields and a calendar system identifier, use that calendar system to construct the date before converting to ISO. If the input is already a trusted date object, use the conversion API instead of manually copying fields.

Avoid adding or subtracting a constant year offset as a general approach. A calendar system may use eras, different month structures, or bounded conversion data. The fact that a Thai Buddhist example has a simple year relationship does not prove that every calendar system behaves the same way.

## 6. "Same Day" Differs from `equals` and Natural Ordering

The program outputs:

```text
sameDay=true
equalsAcrossCalendars=false
naturalComparisonIsZero=false
```

`ChronoLocalDate.isEqual` compares the date position, ignoring calendar system differences. `equals` includes the calendar system. The natural ordering `compareTo` for dates in different calendar systems also uses the calendar system to distinguish them when the date positions are equal. [`ChronoLocalDate` comparison documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ChronoLocalDate.html)

This matters when:

- Checking whether a conversion preserved the date.
- Using dates as keys in a set or map.
- Sorting data across multiple calendar systems.
- Deduplicating by "same actual date".

If the requirement is a unified date key, convert to `LocalDate` or use `epochDay` under an explicit contract. If you need to preserve the calendar system identity, do not strip it away just to make `equals` return true.

Do not use `==` to compare date values.

## 7. Year Within an Era Is Not Always the ISO Year

The Japanese example in the program crosses a boundary:

```text
2019-04-30: YEAR=2019, ERA=2, YEAR_OF_ERA=31
2019-05-01: YEAR=2019, ERA=3, YEAR_OF_ERA=1
```

The calendar date advances by one day; the year on the continuous axis remains 2019. However, the era changes from Heisei to Reiwa and the year within the era resets to 1.

Therefore, data such as "year 1, month 5, day 1" in the Japanese calendar also needs era information to be interpreted correctly. You cannot simply take `YEAR_OF_ERA` and treat it as the ISO year.

`JapaneseDate` uses month/day structure matching ISO within its supported range, but numbers years by era; it does not support arbitrary historical dates. [`JapaneseDate` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/JapaneseDate.html)

Similarly, `ThaiBuddhistDate` is the type for the Thai Buddhist calendar system modeled by Java; calendar names must be understood according to the specific implementation. [`ThaiBuddhistDate` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ThaiBuddhistDate.html)

Do not treat `HijrahDate`, the Thai Buddhist calendar, or another built-in calendar type as the "Vietnamese lunar calendar". Supporting a specific calendar requires verifying the exact rules and data provided by the implementation.

## 8. Calendar System, Language, and Time Zone Are Three Configuration Axes

| Component | What does it determine? | Example |
| --- | --- | --- |
| `Chronology` | How dates are organized/numbered | ISO, Thai Buddhist, Japanese |
| `Locale` | Language and related display/parsing conventions | Month names, era labels |
| `ZoneId` | Rules relating local time to an instant | `Asia/Ho_Chi_Minh` |

Changing `Locale` can change the displayed text, not perform a calendar system conversion on the date object.

Changing `ZoneId` affects how instants and local date-times are interpreted; it is not the same as changing the calendar system.

For example, the same `Instant` can fall on two different local dates in two regions. Only after choosing a zone and determining the local ISO date can you convert that date's representation to another calendar system if needed.

Conceptual sequence:

```text
Instant + ZoneId
        ↓
Local date/time, including ISO LocalDate
        ↓ choose calendar system
Corresponding date in the target chronology to display
        ↓ choose language and format
Text for the user
```

Do not substitute the zone-selection step with the language- or calendar-selection step.

## 9. Formatting with a Chronology and Parsing to an ISO Date

The `thaiText` formatter in the program uses:

```java
.withChronology(ThaiBuddhistChronology.INSTANCE)
```

When formatting the ISO date 2024-06-15, it converts to the Thai Buddhist representation and prints `2567-06-15`.

When parsing the string `2567-06-15`, the same configuration interprets the year field according to Thai Buddhist, and then queries `LocalDate::from` for the corresponding ISO date.

The key point to keep clear is that the chronology configuration must accompany the string contract. With the same text `2567-06-15`, if you use the default `LocalDate.parse`, the year is interpreted as ISO and the result differs.

If formatting with eras, consider both `G` and `y`; if using the calendar system's continuous year axis, `u` has a different meaning. For textual month/era names, choose the data's `Locale` explicitly. When strict input handling is needed, configure the resolver style and validate the target type's values rather than only checking that characters can be read.

## 10. Designing Clear Data Boundaries

For an application that primarily uses ISO but has multi-calendar interfaces, you can structure it as:

```text
Input in source calendar system
        ↓ parse/validate with source chronology
Date in source calendar system
        ↓ date-preserving conversion
ISO LocalDate used in processing
        ↓ convert when needed
Representation in target calendar system for display
```

If a source only sends three numbers for year/month/day without specifying the calendar system, the receiver should not guess from the magnitude of the year. Accept an explicit calendar system identifier or fix it per interface.

Conversion can fail when a date falls outside a calendar system's supported range. Do not assume every `LocalDate` across Java's full range can be converted to every chronology.

If you need to audit how the user entered the date, also retain the calendar system and appropriate source representation information. Storing only ISO may preserve the date, but it does not preserve the full original way the date was expressed.

For adding months or years in a source calendar, decide whether to perform the addition before or after conversion based on business meaning. Adding one month in an arbitrary calendar must not be assumed equivalent to adding one ISO month.

## 11. Verification and Self-Practice

Useful checks include:

- Convert ISO to the target calendar system and back; the ISO date must be preserved within the supported range.
- Compare `epochDay` or `isEqual`, not just the year number.
- Cross an era boundary if the calendar system has eras.
- Parse text with both the right and wrong calendar systems to observe the difference in meaning.
- Test out-of-range dates and error reporting.
- Confirm the contract uses dates, without confusing them with seconds or milliseconds of an instant.

Self-check questions:

1. Does `LocalDate.of(2567, 6, 15)` automatically interpret the year as Buddhist Era?
2. To convert a `ThaiBuddhistDate` to the corresponding ISO date, should you copy fields or use the conversion API?
3. Are two dates in different calendar systems with the same `epochDay` necessarily `equals`?
4. Does changing the display locale automatically change the calendar system of a `LocalDate`?
5. Is having only a date in a chronology sufficient to create an `Instant`?

Suggested answers:

1. No; it creates an ISO date in year 2567.
2. Use `LocalDate.from(thaiDate)` or the corresponding conversion API.
3. No; `equals` takes the calendar system into account. `isEqual` is appropriate when asking whether they represent the same date position.
4. No.
5. Not yet; you also need time-of-day and appropriate zone/offset information to determine an instant.

Treat chronology as the set of rules that gives meaning to date fields, use conversion APIs to preserve the same date, and keep clear boundaries between calendar system, language, and time zone.
