# Converting Calendar Systems for Display and Limits in Data Exchange

## 1. Changing How a Date Is Named Does Not Change the Date Itself

A single date can be described across multiple calendar systems. For example, the ISO date `2024-02-29` has the Thai Buddhist year 2567 and falls in year 6 of the Reiwa era in the Japanese calendar. The visible components differ, yet they can still refer to **the exact same day on the timeline**.

In Java, `Chronology` describes a calendar system; types such as `ThaiBuddhistDate` or `JapaneseDate` hold a date in their respective calendar systems. Conversion supports presenting dates to users, but it must be kept clearly separate from the data exchange contract between systems.

If an API expects an ISO date and receives a string with year 2567 without context, it may interpret it as ISO year 2567. A sequence of digits does not explain which calendar system it belongs to. Therefore, never use a calendar-dependent display string as an implicit exchange protocol.

## 2. Separate Three Choices: Calendar System, Locale, and Time Zone

| Choice | What does it decide? | Typical API |
|---|---|---|
| Calendar system | How year, month, day, and era are determined | `Chronology`, `withChronology(...)` |
| Locale | Month names, day-of-week names, era names, and regional formatting | `Locale`, `withLocale(...)` |
| Time zone | Which local date/time an instant falls on | `ZoneId`, `withZone(...)` |

Changing `Locale` does not automatically switch the calendar system for all formatters. If a specific calendar system is required, choose `Chronology` explicitly. Changing the calendar system also does not automatically convert the time zone.

`LocalDate` is an ISO date without a time of day or time zone. Once you have a specific ISO date, converting to another calendar system means representing that same date under different rules. If the input is an `Instant`, you must first decide on the time zone to determine the local date for display. Two places can even be on two different calendar dates at the exact same instant.

Do not use calendar conversion to solve a time-zone problem, or use a UI language/locale to infer the calendar system and time zone of business data.

## 3. Convert by Date Information, Not by Copying Numeric Fields

How to convert an existing ISO date:

```java
LocalDate iso = LocalDate.of(2024, 2, 29);
ThaiBuddhistDate buddhist = ThaiBuddhistDate.from(iso);
JapaneseDate japanese = JapaneseDate.from(iso);
```

The `from` methods read the date information to create the equivalent date in the target system. Another option is using `Chronology.date(temporal)` or `dateEpochDay(...)` when you already have a corresponding date point.

Do not convert by calling `getYear()`, `getMonthValue()`, and `getDayOfMonth()` and passing those three raw numbers into another calendar system. That creates a date with **similar field labels**, not necessarily the same day.

For example, "year 2024" in ISO and "year 2024" in the Thai Buddhist calendar are not the same year. Some systems have different month structures or eras; adding a constant year offset must not be treated as a general algorithm for all conversions.

### Same Date, Yet Not `equals`

Calendar date types can be compared on the timeline using `isEqual`, or by comparing `toEpochDay()`. The epoch day is the count of days since the ISO epoch `1970-01-01`, not the millisecond count of an instant.

`equals` also considers the object's representation/calendar system. Therefore, a `LocalDate` and a `ThaiBuddhistDate` representing the same day can have `isEqual(...) == true` while `equals(...) == false`. Do not use this difference to conclude that the conversion shifted the date.

If a collection or data key must group representations of the same day together, normalize them to a common contract before using them as keys. Do not mix calendar types arbitrarily and expect every comparison to treat them as the same value.

## 4. Formatting for Display with a `Chronology`

You do not have to convert the source variable into another type just to produce a display label. `DateTimeFormatter.withChronology(...)` lets the formatter convert the date to the chosen calendar system before outputting the fields:

```java
DateTimeFormatter display = DateTimeFormatter
        .ofPattern("G yyyy-MM-dd", Locale.ENGLISH)
        .withChronology(ThaiBuddhistChronology.INSTANCE);
String label = display.format(iso);
```

This is an illustrative snippet inside a Java method. `G` is the era; `y` is the year-of-era. In this example, the label is `BE 2567-02-29` in the verified environment below. The `iso` object still retains its original ISO date.

For the Japanese calendar, the era year must be paired with an era such as Reiwa or Heisei. A standalone number `6` is not enough to identify a year without knowing which era it belongs to.

Do not assume the pattern letters `u` and `y` are interchangeable for every calendar type. `u` is the proleptic year of the calendar system, whereas `y` is the year-of-era. In the Japanese calendar, the proleptic year can match the ISO year while the year-of-era differs. Choose fields based on the data you want to represent and ensure there is enough information to parse it back.

Era and month names are locale data; they can vary across locales and JDK versions. Display formatters should be tested on the deployment environment if the design requires exact character-for-character output.

## 5. Parsing Back Requires the Same Calendar System and Sufficient Fields

The string `BE 2567-02-29` is parsed using a formatter configured with the Thai Buddhist calendar, not a standard ISO date formatter:

```java
ThaiBuddhistDate parsed = display.parse(text, ThaiBuddhistDate::from);
LocalDate isoAgain = LocalDate.from(parsed);
```

Here `display` must be configured appropriately, and `text` must follow that exact contract. When using `ResolverStyle.STRICT`, the fields must be provided completely and form a valid date in the active calendar system.

Converting back to `LocalDate` preserves the corresponding ISO date. It does not mean the original string was ISO, nor does it preserve the era name or the exact formatting entered by the user.

When receiving Japanese calendar data, having only the year-of-era without the era is ambiguous. When using calendar systems with variants or limited table data, you must know the supported variant and range. Do not try multiple calendar systems and pick the first one that parses: multiple systems can accept the same numbers while producing different dates.

## 6. Complete Runnable Program

Save the following code to `CalendarDisplayDemo.java`. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class CalendarDisplayDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 2, 29);
        ThaiBuddhistDate buddhist = ThaiBuddhistDate.from(iso);
        JapaneseDate japanese = JapaneseDate.from(iso);

        System.out.println("iso=" + iso);
        System.out.println("buddhistYear="
                + buddhist.get(ChronoField.YEAR));
        System.out.println("japaneseYearOfEra="
                + japanese.get(ChronoField.YEAR_OF_ERA));
        System.out.println("sameEpochDay="
                + (iso.toEpochDay() == buddhist.toEpochDay()));
        System.out.println("isEqual=" + iso.isEqual(buddhist));
        System.out.println("equals=" + iso.equals(buddhist));

        DateTimeFormatter thaiDisplay = DateTimeFormatter
                .ofPattern("G yyyy-MM-dd", Locale.ENGLISH)
                .withChronology(ThaiBuddhistChronology.INSTANCE)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter japaneseDisplay = DateTimeFormatter
                .ofPattern("G y-MM-dd", Locale.ENGLISH)
                .withChronology(JapaneseChronology.INSTANCE)
                .withResolverStyle(ResolverStyle.STRICT);

        String displayed = thaiDisplay.format(iso);
        System.out.println("display=" + displayed);
        System.out.println("japaneseDisplay=" + japaneseDisplay.format(iso));
        System.out.println("sameDisplay=" + displayed.equals(
                thaiDisplay.format(buddhist)));

        ThaiBuddhistDate parsed = thaiDisplay.parse(
                displayed, ThaiBuddhistDate::from);
        System.out.println("roundTripIso=" + LocalDate.from(parsed));

        System.out.println("wireFromIso="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(iso));
        System.out.println("wireFromBuddhist="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(buddhist));

        try {
            JapaneseDate.from(LocalDate.of(1800, 1, 1));
        } catch (DateTimeException e) {
            System.out.println("unsupportedJapaneseDate=ERROR");
        }
    }
}
```

Compile and run:

```shell
javac CalendarDisplayDemo.java
java CalendarDisplayDemo
```

Verified output on Zulu OpenJDK 24.0.2:

```text
iso=2024-02-29
buddhistYear=2567
japaneseYearOfEra=6
sameEpochDay=true
isEqual=true
equals=false
display=BE 2567-02-29
japaneseDisplay=Reiwa 6-02-29
sameDisplay=true
roundTripIso=2024-02-29
wireFromIso=2024-02-29
wireFromBuddhist=2024-02-29
unsupportedJapaneseDate=ERROR
```

The era names on the two display lines depend on locale/JDK data; the conversion and date-checking logic should be verified against the API contract. `ERROR` is a label printed by the program when catching the exception, not a default Java message.

Key takeaways from the output:

- The year and year-of-era change, yet `sameEpochDay` remains `true`.
- `sameDisplay` shows that a formatter with a chronology can format from either an ISO source or the corresponding target date type.
- `roundTripIso` returns to the exact original date using date-based conversion, not manual year subtraction.
- `ISO_LOCAL_DATE` has an overriding ISO chronology, so it formats a Thai Buddhist date as its corresponding ISO date. Do not generalize this behavior to arbitrary custom patterns.
- A Japanese calendar date outside the library's supported range is rejected; era data is not extrapolated to arbitrary dates in the past.

## 7. Designing Data Exchange Contracts

### When Another Calendar System Is Only for Display

You can keep the canonical date in business logic and APIs as ISO, while storing the display calendar choice in UI configuration. Example exchange payload:

```json
{
  "date": "2024-02-29",
  "displayCalendar": "ThaiBuddhist"
}
```

In this illustrative contract, the `date` field is always an ISO date; `displayCalendar` only specifies how to present it. Document this meaning explicitly rather than expecting the receiver to guess from field names.

If transmitting an instant rather than a civil date, use an appropriate instant/offset/time-zone contract. An ISO date string is not an `Instant` by itself and does not need to be converted to UTC midnight just for storage.

### When the Source Calendar System Is Business Data

If a feature needs to know which calendar system the user used when entering the date, keeping only an ISO string may not be enough to recover the original intent. The contract may also need:

- The supported calendar system identifier and variant.
- Original fields such as era, year-of-era, month, and day according to well-defined rules.
- The corresponding ISO date if both sides agree to use it for cross-referencing.
- Calendar data version information when results depend on data sources or variants.

Do not send `"2567-02-29"` and assume the receiver will interpret it as Thai Buddhist. Likewise, do not treat `toString()` of a Java class as a universal JSON contract readable by every language.

If the receiver does not support a calendar system, agree on either a meaning-preserving normalization or an explicit rejection. Do not silently substitute a similar-looking calendar, because "parsable numbers" is not the same as "the same day".

## 8. Limits of Conversion and Arithmetic

### Non-Uniform Calendar Ranges

Calendar systems can have different supported date ranges or data. `JapaneseDate` supports dates from 1873-01-01 onward, not the entire wide range of `LocalDate`. Calendars backed by table data or variants must also be checked individually before accepting a large date range.

Sharing year-month-day fields does not prove that every arithmetic operation is equivalent across two calendar systems. "Adding one month" in calendar system A may not yield the same result as converting to B and adding one month in B. If the other calendar is only for display, perform calculations in the canonical business calendar and convert at the presentation boundary. If the business logic is defined in the source calendar, design the arithmetic according to that calendar.

### Do Not Conflate Similarly Named Calendars

The Thai Buddhist calendar in Java is not the Vietnamese lunar calendar. A specific Hijrah calendar does not automatically represent every Islamic calendar variant. Features such as leap months, observational rules, or published tables require appropriate data sources and models; do not treat a built-in chronology as a universal converter for unsupported calendars.

### Keep Dates and Instants Distinct

`toEpochDay()` provides a date reference, not second-level precision. If you need to attach a time of day and a time zone, handle the local date-time rules of that zone separately. Do not multiply the epoch day by 86,400 and assume you have the right instant for every local day.

## 9. Self-Practice

1. Change the ISO date to `2024-03-01` and verify that the ISO → Thai Buddhist → ISO round-trip preserves the same day.
2. Change the display locale and observe how the era name changes; confirm that `toEpochDay()` remains unchanged.
3. Try parsing a Thai Buddhist date string using the formatter configured with the chronology and using an ISO formatter. Explain why the same year digits do not carry the same meaning.
4. Design data structures for two separate requirements: "display in the Japanese calendar only" and "preserve the user's Japanese calendar input". Identify which fields are UI preferences and which fields must be preserved as source data.

References: [Chronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/Chronology.html), [JapaneseDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/JapaneseDate.html), and [DateTimeFormatter — withChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#withChronology(java.time.chrono.Chronology)) in Java SE 21.
