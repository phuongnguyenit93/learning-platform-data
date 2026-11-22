# Identifying `JapaneseDate`, `ThaiBuddhistDate`, `HijrahDate`, and `MinguoDate`

## 1. One date, multiple calendar systems

`LocalDate` represents a date in the ISO calendar. When a data source uses Japanese imperial eras, Thai Buddhist years, the Hijrah calendar, or Minguo (Republic of China) years, changing the display language alone is not enough: the meaning of the year, month, and day fields can differ.

The four classes in `java.time.chrono` are used to represent dates in those calendar systems. They are all date types without time or time zone, immutable, and queryable via `ChronoLocalDate`.

Three choices should be kept separate:

- **Calendar system (`Chronology`):** the rules that assign year/month/day to a date.
- **Display language/region (`Locale`):** how names and text are written.
- **Time zone (`ZoneId`):** the context that converts an instant into a local date–time.

A Japanese-language user is not required to use Japanese imperial eras; nor does a `JapaneseDate` contain the Tokyo time zone. This lesson focuses on identifying and converting date representations between calendar systems, not turning them into instants with a time of day.

## 2. Quick overview of the four types

| Type | Calendar system and identifying features | What not to confuse it with |
| --- | --- | --- |
| `JapaneseDate` | Japanese calendar by imperial era; has an era such as Heisei, Reiwa and a year within the era | Not the ancient Japanese lunar calendar |
| `ThaiBuddhistDate` | Thai Buddhist calendar; continuous year is offset by +543 from the ISO year, with corresponding month/day | Not a single pan-Buddhist lunar calendar shared by all countries |
| `HijrahDate` | Hijrah calendar according to a variant; lunar months have 29 or 30 days | Cannot be converted by adding/subtracting a constant to the ISO year |
| `MinguoDate` | Minguo calendar; year 1 corresponds to ISO year 1912, with corresponding month/day | Not the Chinese lunisolar calendar |

## 3. `JapaneseDate`: you must know which year is being read

According to [Java SE 21 — JapaneseDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/JapaneseDate.html), the month/day fields follow the ISO calendar, but year numbering by imperial era differs. The class supports dates from `1873-01-01` onward; it does not model the entire ancient Japanese calendar before the adoption of the Gregorian calendar.

For the ISO date `2019-05-01`:

- `getEra()` returns the Reiwa era.
- `ChronoField.YEAR` returns the continuous year 2019.
- `ChronoField.YEAR_OF_ERA` returns year 1 within that era.

Therefore, `YEAR` and `YEAR_OF_ERA` are not interchangeable. If you only store "year 1" without storing the era, it is impossible to know which era the source date refers to.

You can create an instance with the continuous year `JapaneseDate.of(2019, 5, 1)` or with the era `JapaneseDate.of(JapaneseEra.REIWA, 1, 5, 1)`. However, `Reiwa 1-01-01` is invalid: this era began on `2019-05-01`, so you cannot treat the entire calendar year 2019 as the first year of the era while ignoring the transition date.

Do not assume a rule that every year in an era always starts on January 1. When validating dates near an era transition, let the API validate the era/year/month/day combination.

## 4. `ThaiBuddhistDate` and `MinguoDate`: same month/day, different year system

[Java SE 21 — ThaiBuddhistChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ThaiBuddhistChronology.html) defines the continuous year as the ISO year plus 543, while the month/day and leap-year rules match ISO. Thus, the ISO date `2019-05-01` is represented as Buddhist year 2562, month 5, day 1.

The numbers passed to `ThaiBuddhistDate.of(2562, 5, 1)` belong to the Thai calendar system itself. If you write `ThaiBuddhistDate.of(2019, 5, 1)`, 2019 is interpreted as a year in the Thai calendar system, not as a request to "convert ISO year 2019 to the Buddhist calendar".

[Java SE 21 — MinguoChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/MinguoChronology.html) defines the continuous year as the ISO year minus 1911. For example, `MinguoDate.of(108, 5, 1)` corresponds to `2019-05-01`. The calendar system also has a Before Minguo era; when working with dates before the epoch start, you still need to distinguish the continuous year from the year of the era.

The year-offset relationship helps identify these two types, but conversion code should use the API rather than manually adding/subtracting and copying fields. Clarifying which calendar system an input belongs to avoids mistaking a year that has already been converted.

## 5. `HijrahDate`: variant and data range must be known

[Java SE 21 — HijrahDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/HijrahDate.html) represents a date tied to a specific `HijrahChronology`. Convenience methods such as `HijrahDate.from()` and `of()` use the Umm Al-Qura calendar; the calendar ID commonly seen at runtime is `Hijrah-umalqura`.

According to [HijrahChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/HijrahChronology.html), the Hijrah calendar has multiple variants, with months of 29 or 30 days, common years of 354 days, and leap years of 355 days. A variant may rely on configured calendar data for a specific range of years, so you must not assume that every date far in the past or future is supported or that every variant produces the same result.

What sets it apart from the two year-offset types above is that Hijrah months and days do not stay aligned with ISO. The ISO date `2019-05-01` in the Umm Al-Qura data used in the example corresponds to year 1440, month 8, day 26.

Adding one Hijrah month means advancing according to the months of the Hijrah calendar system; it is not adding one ISO month and then changing the formatting. When a source contract says "Islamic calendar", you must identify the required variant rather than assuming it is a single unconfigured calendar.

## 6. Verification program: same date, different fields

Save the code to `CalendarTypesDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.time.chrono.*;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class CalendarTypesDemo {
    private static void describe(ChronoLocalDate date) {
        System.out.printf(Locale.ROOT,
                "%s | year=%d | yearOfEra=%d | month=%d | day=%d | ISO=%s%n",
                date.getChronology().getId(),
                date.get(ChronoField.YEAR),
                date.get(ChronoField.YEAR_OF_ERA),
                date.get(ChronoField.MONTH_OF_YEAR),
                date.get(ChronoField.DAY_OF_MONTH),
                LocalDate.from(date));
    }

    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2019, 5, 1);
        JapaneseDate japanese = JapaneseDate.from(iso);
        ThaiBuddhistDate buddhist = ThaiBuddhistDate.from(iso);
        HijrahDate hijrah = HijrahDate.from(iso);
        MinguoDate minguo = MinguoDate.from(iso);

        System.out.println("source = " + iso);
        describe(japanese);
        describe(buddhist);
        describe(hijrah);
        describe(minguo);
        System.out.println("Japanese era = " + japanese.getEra());
        System.out.println("same epoch day = "
                + (iso.toEpochDay() == hijrah.toEpochDay()));
        System.out.println("equals across calendars = " + iso.equals(japanese));
        System.out.println("isEqual across calendars = " + iso.isEqual(japanese));

        JapaneseDate byEra = JapaneseDate.of(JapaneseEra.REIWA, 1, 5, 1);
        System.out.println("era constructor -> ISO = " + LocalDate.from(byEra));
        try {
            JapaneseDate.of(JapaneseEra.REIWA, 1, 1, 1);
        } catch (DateTimeException ex) {
            System.out.println("before Reiwa start = DateTimeException");
        }

        DateTimeFormatter japaneseText = DateTimeFormatter
                .ofPattern("G y-MM-dd", Locale.ENGLISH)
                .withChronology(JapaneseChronology.INSTANCE);
        System.out.println("formatted ISO via Japanese = "
                + japaneseText.format(iso));
        System.out.println("Thai year constructor -> ISO = "
                + LocalDate.from(ThaiBuddhistDate.of(2562, 5, 1)));
        System.out.println("Minguo year constructor -> ISO = "
                + LocalDate.from(MinguoDate.of(108, 5, 1)));

        ChronoLocalDate later = hijrah.plus(1, java.time.temporal.ChronoUnit.MONTHS);
        System.out.println("Hijrah plus one month -> ISO = "
                + LocalDate.from(later));
        System.out.println("ISO plus one month = " + iso.plusMonths(1));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CalendarTypesDemo.java
java CalendarTypesDemo
```

Verified output with the calendar data of the runtime used in this lesson:

```text
source = 2019-05-01
Japanese | year=2019 | yearOfEra=1 | month=5 | day=1 | ISO=2019-05-01
ThaiBuddhist | year=2562 | yearOfEra=2562 | month=5 | day=1 | ISO=2019-05-01
Hijrah-umalqura | year=1440 | yearOfEra=1440 | month=8 | day=26 | ISO=2019-05-01
Minguo | year=108 | yearOfEra=108 | month=5 | day=1 | ISO=2019-05-01
Japanese era = Reiwa
same epoch day = true
equals across calendars = false
isEqual across calendars = true
era constructor -> ISO = 2019-05-01
before Reiwa start = DateTimeException
formatted ISO via Japanese = Reiwa 1-05-01
Thai year constructor -> ISO = 2019-05-01
Minguo year constructor -> ISO = 2019-05-01
Hijrah plus one month -> ISO = 2019-05-31
ISO plus one month = 2019-06-01
```

Fixed reference dates avoid dependence on the execution date. For Hijrah and localized text, the output also reflects the variant/runtime data in use; do not extrapolate a single run into a guarantee for all other calendar data sources.

## 7. Converting a date vs. copying year/month/day numbers

`JapaneseDate.from(iso)`, `ThaiBuddhistDate.from(iso)`, `HijrahDate.from(iso)`, and `MinguoDate.from(iso)` represent the same source date in the target calendar system. The line `same epoch day = true` shows that the ISO date and the Hijrah date have the same day count since the ISO epoch `1970-01-01`.

`LocalDate.from(otherCalendarDate)` does the reverse: it obtains the ISO representation of that date. It does not take the raw year number 1440 or 2562 and use it as an ISO year. That is the difference between **converting the same date** and **constructing a new date from numbers interpreted in a calendar system**.

The flow can be visualized as:

```text
ISO date 2019-05-01
      ↓ convert as the same date
Japanese / ThaiBuddhist / Hijrah / Minguo
      ↓ LocalDate.from(...)
ISO date 2019-05-01
```

If the initial input is an `Instant`, you must choose a zone to determine the local date before performing the calendar conversion. The four types in this lesson do not themselves provide a start-of-day time or a zone for an instant.

## 8. Comparisons, arithmetic, and formatting must preserve calendar semantics

### Object equality vs. same date on the linear timeline

`iso.equals(japanese)` is `false` even though they represent the same date, because `equals` also distinguishes the calendar system. `iso.isEqual(japanese)` is `true` because the question here is whether they fall on the same day on the date timeline. When comparing across calendar systems, choose the operation that matches the question you are asking, and do not treat a `false` from `equals()` as proof that two dates are different days.

In the example, `ChronoLocalDate` only helps the `describe()` method read common fields and demonstrate comparison. For business code that only uses ISO dates, a `LocalDate` signature is usually easier to understand than converting every variable to the general type and accidentally applying ISO assumptions to data from another calendar.

### Adding months according to the object's calendar

The last two lines show that adding one Hijrah month from the source date yields the ISO date `2019-05-31`, whereas adding one ISO month yields `2019-06-01`. There is no rounding error here: the two "month" units belong to two different calendar systems.

Therefore, when a requirement says "after one month", you must clarify which calendar's month is meant. If you only convert to another calendar for display, it is usually best to keep business calculations in a single agreed-upon calendar system and convert at the display boundary. If the business logic truly depends on Hijrah months or imperial eras, you must explicitly preserve the calendar system in the calculation.

### Choosing the display calendar separately from Locale

The program uses the pattern `G y-MM-dd` and `withChronology(JapaneseChronology.INSTANCE)` to format the ISO date as `Reiwa 1-05-01`. In the pattern, `G` is the era and `y` is the year of the era. `Locale.ENGLISH` only selects how text is written; the `withChronology()` call is what specifies the calendar system to use.

Do not just switch to a Japanese Locale and assume every formatter will automatically pick Japanese imperial eras. When parsing a string with a year of an era, you need sufficient era information and the appropriate calendar configuration; a string containing only a year number may not be enough to tell which calendar system it belongs to.

## 9. Self-check on identification

Before accepting a non-ISO date, clarify: which calendar system, which era if applicable, which variant if applicable, the supported date range, and whether the original string must be preserved. A string `108-05-01` does not by itself say that it is Minguo year 108; if calendar metadata is dropped, the information can become ambiguous.

Exercise: convert `LocalDate.of(2020, 2, 29)` to `ThaiBuddhistDate` and `MinguoDate`. The year parts are 2563 and 109 respectively, while the month/day remain 2/29; when converting back with `LocalDate.from()`, you should get `2020-02-29` again. Then explain why you cannot predict the month/day fields of `HijrahDate` by keeping `2/29` unchanged and only adjusting the year.
