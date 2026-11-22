# Historical Gregorian Calendar Differences When Migrating Legacy Data

## 1. The same date numbers are not necessarily the same day

When migrating code from `GregorianCalendar` to `LocalDate`, modern dates often look like a straightforward conversion. With historical data, copying year/month/day or converting through an instant can yield two different results.

In the example in this lesson, a default `GregorianCalendar` records the fields `1582-10-04`, whereas the corresponding instant when viewed in the ISO calendar of `LocalDate` is `1582-10-14` in UTC. Copying the three fields directly into `LocalDate.of(1582, 10, 4)` instead yields ISO October 4, which is a different choice.

You cannot conclude that a conversion is wrong simply because the numbers differ. You must know whether the source data intends to preserve the **same position on the timeline/day** or preserve the **recorded year–month–day label**. These two goals do not always align when the calendar systems differ.

## 2. The default `GregorianCalendar` is a hybrid calendar

According to [Java SE 21 — GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html), this class uses the Julian calendar by default before the cutover to Gregorian, and uses the Gregorian calendar from that cutover onward. The default cutover is the Gregorian date `1582-10-15`, which can be changed with `setGregorianChange()`.

With the default configuration in the UTC example, Julian October 4, 1582 is followed immediately by Gregorian October 15. The date-label range October 5–14 does not exist in that hybrid calendar. This is the rule of the configuration in use; it does not describe that every place in the world switched calendars on the same day.

Julian treats every year divisible by 4 as a leap year. Gregorian excludes century years not divisible by 400. Therefore, the year 1500 has February 29 in Julian, but not in Gregorian. The difference is not just skipping a few date labels in 1582; the leap-year rule before the cutover also differs.

A legacy object might also have had a custom cutover configured. Simply knowing the class name `GregorianCalendar` is not enough to conclude that its data uses the same rules as a newly created default instance.

## 3. `LocalDate` uses proleptic Gregorian

[Java SE 21 — LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html) uses the ISO calendar, which is equivalent to extending Gregorian backward with consistent rules into the past, commonly called **proleptic Gregorian**. It does not automatically switch to Julian before October 15, 1582.

Verifiable consequences:

| Scenario | Default GregorianCalendar | ISO LocalDate |
| --- | --- | --- |
| After the day labeled `1582-10-04` | Next label is `1582-10-15` | Next day is `1582-10-05` |
| Constructing `1582-10-10` | Invalid in the cutover gap under strict checking | Valid |
| Constructing `1500-02-29` | Valid in the Julian portion | Invalid under Gregorian |

`LocalDate` is not wrong just because it allows a date in the skipped label range of the hybrid calendar; it is using a different calendar model. Conversely, the proleptic Gregorian model does not by itself prove that those were the labels used by a historical document in a given locality.

## 4. Choose what to preserve before converting

### Preserving the same instant or the same encoded day

If the source data actually stores an instant, converting through `Instant` preserves the instant value. You must then choose a zone to obtain the ISO date:

```java
// Illustrated inside a method; legacy is the source GregorianCalendar.
LocalDate isoDate = legacy.toInstant()
        .atZone(ZoneOffset.UTC)
        .toLocalDate();
```

UTC is only the zone chosen for the example. Real data may need the source's zone or another business zone. Choosing a different zone can shift the local date independently of the Julian/Gregorian difference, so the two concerns must be evaluated separately.

### Preserving the recorded date fields as-is

If the contract states that the source numbers already represent an ISO date or a civil date that needs to be reinterpreted, you may need to construct `LocalDate` from the fields according to that decision. However, that is **reinterpreting the fields**, and does not guarantee preserving the instant that the legacy Calendar computed.

Copying must also handle 0-based Calendar months and the `ERA` field. For BCE data, taking `Calendar.YEAR` alone is not enough because year-of-era does not match ISO's continuous numbering with year 0. The field-copying snippet in the program only illustrates the selected CE dates, not a general-purpose function for all historical years.

For documents actually recorded in Julian or with a local cutover, preserve the metadata and determine the corresponding conversion. Do not rename the column to ISO and copy the labels while discarding calendar-system information.

## 5. Complete verification program

Save the code to `HistoricalGregorianMigrationDemo.java`. The program uses Java 17 or later and requires no external libraries:

```java
import java.time.*;
import java.util.*;

public class HistoricalGregorianMigrationDemo {
    private static GregorianCalendar legacy(boolean prolepticGregorian) {
        GregorianCalendar value = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        if (prolepticGregorian) {
            value.setGregorianChange(new Date(Long.MIN_VALUE));
        }
        value.clear();
        value.setLenient(false);
        return value;
    }

    private static String fields(Calendar value) {
        return String.format(Locale.ROOT, "%04d-%02d-%02d",
                value.get(Calendar.YEAR),
                value.get(Calendar.MONTH) + 1,
                value.get(Calendar.DAY_OF_MONTH));
    }

    private static LocalDate sameDay(GregorianCalendar value) {
        return value.toInstant().atZone(ZoneOffset.UTC).toLocalDate();
    }

    public static void main(String[] args) {
        GregorianCalendar beforeCutover = legacy(false);
        beforeCutover.set(1582, Calendar.OCTOBER, 4);
        System.out.println("legacy fields = " + fields(beforeCutover));
        System.out.println("same instant ISO date = " + sameDay(beforeCutover));
        LocalDate copiedFields = LocalDate.of(
                beforeCutover.get(Calendar.YEAR),
                beforeCutover.get(Calendar.MONTH) + 1,
                beforeCutover.get(Calendar.DAY_OF_MONTH));
        System.out.println("copied fields ISO date = " + copiedFields);

        beforeCutover.add(Calendar.DAY_OF_MONTH, 1);
        System.out.println("legacy plus one day = " + fields(beforeCutover));
        System.out.println("same instant after = " + sameDay(beforeCutover));

        GregorianCalendar gap = legacy(false);
        gap.set(1582, Calendar.OCTOBER, 10);
        try {
            gap.getTimeInMillis();
        } catch (IllegalArgumentException ex) {
            System.out.println("legacy cutover gap = IllegalArgumentException");
        }
        System.out.println("ISO date in gap = " + LocalDate.of(1582, 10, 10));

        GregorianCalendar julianLeap = legacy(false);
        julianLeap.set(1500, Calendar.FEBRUARY, 29);
        System.out.println("legacy 1500 leap fields = " + fields(julianLeap));
        System.out.println("same day ISO = " + sameDay(julianLeap));
        try {
            LocalDate.of(1500, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("ISO 1500-02-29 = DateTimeException");
        }

        GregorianCalendar pureGregorian = legacy(true);
        pureGregorian.set(1500, Calendar.MARCH, 1);
        System.out.println("pure Gregorian fields = " + fields(pureGregorian));
        System.out.println("pure Gregorian ISO = " + sameDay(pureGregorian));

        GregorianCalendar fromModern = GregorianCalendar.from(
                LocalDate.of(1500, 3, 1).atStartOfDay(ZoneOffset.UTC));
        System.out.println("from modern fields = " + fields(fromModern));
        System.out.println("from modern pure Gregorian = "
                + (fromModern.getGregorianChange().getTime() == Long.MIN_VALUE));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 HistoricalGregorianMigrationDemo.java
java HistoricalGregorianMigrationDemo
```

Output:

```text
legacy fields = 1582-10-04
same instant ISO date = 1582-10-14
copied fields ISO date = 1582-10-04
legacy plus one day = 1582-10-15
same instant after = 1582-10-15
legacy cutover gap = IllegalArgumentException
ISO date in gap = 1582-10-10
legacy 1500 leap fields = 1500-02-29
same day ISO = 1500-03-10
ISO 1500-02-29 = DateTimeException
pure Gregorian fields = 1500-03-01
pure Gregorian ISO = 1500-03-01
from modern fields = 1500-03-01
from modern pure Gregorian = true
```

Every Calendar in the example is configured to UTC and cleared of existing fields before setting a date. The `fields()` method prints the label from the Calendar fields, while `sameDay()` gets the ISO date of the same instant in UTC. The two methods intentionally answer different questions so the difference is not hidden behind a single formatting style.

## 6. Reading the migration scenarios in the output

### Legacy and ISO labels differ yet can represent the same instant

`legacy fields` is `1582-10-04`; `same instant ISO date` is `1582-10-14`. These are the corresponding Julian date and proleptic Gregorian date under the test configuration. `copied fields ISO date` remains `1582-10-04`, showing that copying the three numbers picked a different ISO day.

After adding one day on the Calendar, the label becomes `1582-10-15`. When converting the same instant to ISO, the date is also October 15. You cannot fix an entire dataset by adding a fixed number of days to every record: the offset depends on the era and the calendar configuration.

### Strict mode detects the source calendar's cutover gap

A non-lenient Calendar rejects the label `1582-10-10` when computing milliseconds. The preceding `set()` call may have returned without checking, so the program explicitly calls `getTimeInMillis()` to force computation.

Those same numbers successfully construct a `LocalDate`. Thus, "legacy input was previously rejected" does not mean `LocalDate` must also reject it for the same cutover gap. Conversely, do not use lenient mode to silently normalize invalid data and then assume you know its historical meaning.

### Legacy leap years can also change which dates are valid

The default Calendar accepts `1500-02-29` in the Julian portion and converts the same day to ISO `1500-03-10`. `LocalDate.of(1500, 2, 29)` rejects it because Gregorian rules do not treat 1500 as a leap year.

If migrating by reconstructing `LocalDate` from fields hits such an error, do not silently change day 29 to 28 just to make the program run. First determine whether the data is a meaningful Julian date or an invalid value in a source that was already defined as ISO.

## 7. Pure Gregorian configuration and conversion from the new API

`setGregorianChange(new Date(Long.MIN_VALUE))` is used in the example to select pure Gregorian across the time range supported by Calendar. The object is configured **before** setting the date fields, so the input year/month/day are interpreted under that choice.

When constructing `1500-03-01`, the fields and the ISO date of the same instant match. This is a specific configuration, not proof that every default Calendar used pure Gregorian.

`GregorianCalendar.from(zonedDateTime)` in the program also creates an object using pure Gregorian, confirmed by the cutover `Long.MIN_VALUE`. Therefore, converting from `java.time` to Calendar via this API does not mean returning to the hybrid calendar configuration of a default legacy Calendar.

Do not use changing the cutover on source objects as a bulk "data fix" operation without a contract. If labels were already read under one calendar, changing the interpretation rules can alter the meaning that needs to be preserved. Choose the configuration before interpreting the data and verify both the read and write paths.

## 8. What to check when handling legacy data?

A migration plan can start from concrete questions:

1. Does the source store an instant/milliseconds or only fields/raw date label strings?
2. Which calendar class, cutover date, leniency mode, and time zone did the source use?
3. Does the target need to preserve the same instant or preserve/reinterpret the date label, and does the source calendar need to be kept for interpretation?
4. Does the data contain dates around the cutover, century years with differing leap-year rules, or BCE eras?

Verifying with records on both sides of the cutover and a year like 1500 reveals differences much more easily than testing only modern dates. Also, preserve the raw source string or appropriate metadata if reconciliation is needed; once only the converted ISO date remains, it may be impossible to recover the original historical label.

Do not infer a country's historical calendar practice solely from an object's Locale or time zone. `GregorianCalendar` only supports a single Julian/Gregorian cutover for that configuration; complex historical data may require specialized rules or models outside the scope of this class.

Exercise: take a default Calendar representing `1582-10-04`, convert it via the same instant to an ISO date, and compare it with `LocalDate.of(1582, 10, 4)`. Explain why the difference between the two results must not be fixed by arbitrarily changing the time zone. Then test a post-cutover date such as `1600-03-01` with the same UTC zone to see that both models share the Gregorian rules in that period.
