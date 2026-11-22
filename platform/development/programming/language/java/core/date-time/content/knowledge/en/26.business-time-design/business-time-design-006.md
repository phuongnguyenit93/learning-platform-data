# Separating Display Time from Stored Instant

## 1. One Instant, Many Views

A transaction occurs at `2025-12-31T18:00:45.123456789Z`. Someone in Vietnam sees early morning on 1/1/2026; someone in New York still sees the afternoon of 31/12/2025. The data is not contradictory: both people are looking at **the same instant** through two time zones.

For data representing an event on the timeline, keep a timestamp with clear semantics, such as `Instant occurredAt`, and format it by zone and locale at the display boundary. Do not modify the original value whenever a user changes their time zone or language.

```text
Original instant
    + ZoneId of the view
    + Locale and presentation format
    → display string
```

`Instant` does not contain a display zone name. It is an instant value, while a UTC string with `Z` is a standard representation of that value. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

## 2. What Responsibility Does Each Data Layer Hold?

| Component | Information to Keep |
| --- | --- |
| Event business data | Actual timestamp, e.g. `Instant` |
| Storage/exchange data | Contract specifying a clear instant and precision |
| Display preferences | `ZoneId`, `Locale`, format style |
| UI string | Formatted result reproducible from the original data |

For example, `occurredAt = 2025-12-31T18:00:45Z` should not be replaced by a `LocalDateTime` with “7 hours added” and then written back as if it were UTC. When the event's zone is needed for traceability, store the source zone/offset information separately according to the contract.

The exact SQL representation depends on the DB and driver. Setting the connection session to UTC does not automatically make every `TIMESTAMP` column an instant with correct semantics. Always verify the mapping, configuration, and values after writing and reading.

## 3. ZoneId and Locale Solve Two Different Problems

`ZoneId` determines the local time and date at an instant. `Locale` determines language and presentation conventions, such as month names, component order, or time formatting according to the chosen formatter.

Choosing Vietnamese does not automatically select `Asia/Ho_Chi_Minh`; choosing English does not automatically select a US time zone either. A Vietnamese-speaking user can still live in New York. Accept both choices separately or apply clearly documented defaults.

`DateTimeFormatter.withZone(zone)` applies the zone when formatting an `Instant`; `withLocale(locale)` selects the locale conventions. Formatters are immutable, so these methods return a new formatter. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Example snippet inside a method:

```java
DateTimeFormatter display = DateTimeFormatter.ofLocalizedDateTime(
        java.time.format.FormatStyle.MEDIUM)
        .withLocale(Locale.forLanguageTag("vi-VN"))
        .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
String label = display.format(occurredAt);
```

Language-specific strings may change across JDK locale data versions. Do not use them as machine-to-machine wire formats or business keys.

## 4. Changing the Display Must Preserve the Same Instant

With `ZonedDateTime`, distinguish between two operations:

| Method | Preserved Component | Meaning |
| --- | --- | --- |
| `withZoneSameInstant(zone)` | Same instant | Change the view of an event |
| `withZoneSameLocal(zone)` | Attempts to keep local date/time | Reinterpret the local wall-clock time in another zone, which may change the instant |

To display a transaction to someone in another zone, use `instant.atZone(viewZone)` or `withZoneSameInstant`. Do not use `withZoneSameLocal`, because it often shifts the event to a different instant.

`withZoneSameLocal` also has to handle gap/overlap rules in the target zone; thus even preserving local fields follows the API's rules. It is an operation with its own distinct semantics, not a function for relabeling a time zone. [ZonedDateTime: zone conversion](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#withZoneSameInstant(java.time.ZoneId))

## 5. Program: Changing the Displayed Date While Preserving Data

Save as `DisplayTimeDemo.java`. The example uses a fixed numeric pattern for easy stdout comparison; a real UI can use an appropriate localized pattern.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class DisplayTimeDemo {
    static String display(Instant value, ZoneId zone, Locale locale) {
        return DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX VV", locale)
                .withZone(zone)
                .format(value);
    }

    public static void main(String[] args) {
        Instant stored = Instant.parse("2025-12-31T18:00:45.123456789Z");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId newYork = ZoneId.of("America/New_York");

        System.out.println("vietnam="
                + display(stored, vietnam, Locale.forLanguageTag("vi-VN")));
        System.out.println("newYork=" + display(stored, newYork, Locale.US));
        System.out.println("stored=" + stored);

        ZonedDateTime vietnamView = stored.atZone(vietnam);
        ZonedDateTime sameInstant = vietnamView.withZoneSameInstant(newYork);
        ZonedDateTime sameLocal = vietnamView.withZoneSameLocal(newYork);
        System.out.println("sameInstantEqual="
                + stored.equals(sameInstant.toInstant()));
        System.out.println("sameLocalEqual="
                + stored.equals(sameLocal.toInstant()));
        System.out.println("sameLocalInstant=" + sameLocal.toInstant());

        String wire = DateTimeFormatter.ISO_INSTANT.format(stored);
        Instant readBack = Instant.parse(wire);
        System.out.println("wire=" + wire);
        System.out.println("wireRoundTrip=" + stored.equals(readBack));
    }
}
```

Run with JDK 17 or later:

```shell
javac --release 17 DisplayTimeDemo.java
java DisplayTimeDemo
```

Stdout with IANA rules for the zones and dates in the example:

```text
vietnam=2026-01-01 01:00 +07:00 Asia/Ho_Chi_Minh
newYork=2025-12-31 13:00 -05:00 America/New_York
stored=2025-12-31T18:00:45.123456789Z
sameInstantEqual=true
sameLocalEqual=false
sameLocalInstant=2026-01-01T06:00:45.123456789Z
wire=2025-12-31T18:00:45.123456789Z
wireRoundTrip=true
```

The display string only includes minutes, yet `stored` still retains seconds and nanoseconds. Omitting details from the label does not mean truncating details in the original data.

`sameLocalInstant` shows the consequence of changing the zone while keeping local 01:00: the new instant differs from the originally stored data. This changes the temporal meaning, not just the display.

## 6. Read Flows and Input Flows Are Asymmetric

Formatting an instant into a human-readable string can lose information: dropping seconds, offset, zone, or year. There is no guarantee that parsing that string back will reconstruct the exact original data.

If an API receives an instant, use a contract with an explicit UTC/offset and an agreed-upon precision. If a user enters a local time for an appointment, capture the zone as well and handle gaps/overlaps before creating an `Instant`.

The string `01/02/2026 09:00` does not indicate which day/month convention is used and has no time zone. Do not parse it using the server's default locale/time zone and treat that as every user's intent.

Likewise, do not convert a zoneless `LocalDateTime` into an `Instant` simply by appending `Z` to the string. That injects an assumption of UTC, which can shift the instant by several hours.

## 7. Sorting, Filtering, and Grouping Must Rely on Appropriate Data

Sort events by their original instant, not by a `dd/MM/yyyy HH:mm` string; lexicographical order of labels does not reflect chronological order. Two labels with the same minute can represent two different events; local times can also occur twice during a daylight saving fallback.

For a filter like “today's events in the user's local time”, the display zone becomes a meaningful input for filtering. Determine the start of the day and the start of the next day in that zone, convert both boundaries to `Instant`, and filter using a half-open interval (start inclusive, end exclusive).

This is a projection by local day; it does not alter the stored event instant. Do not split days by fixing 24-hour UTC segments if the requirement is a day in another zone.

When exporting reports, clearly state the zone used. A “time” column without a zone label can mislead readers even when the stored values are completely accurate.

## 8. Scope: Not All Date-Time Data Is an Instant

Birthdays, holidays, or a purely calendar-based effective date are usually `LocalDate`; there is no need to convert them to UTC midnight just to fit an event model. A recurring opening hour can be a `LocalTime` paired with calendar and zone rules.

For future appointments that must stay at 09:00 at a location, storing the local intent and `ZoneId` may be necessary; do not discard them just because an `Instant` has been computed. The “keep the original instant, format at the UI” rule applies when the source data is genuinely an instant.

Verify precision across DB/API boundaries, choose a clear default zone, and define how invalid zone inputs are handled. A display preference must never accidentally become a data-mutating operation.

## 9. Practice

1. Format the same `Instant` in Vietnam and New York; check whether the two `toInstant()` results are equal.
2. Switch from `withZoneSameInstant` to `withZoneSameLocal` and explain why the instant changes.
3. Restrict display formatting to minutes while still confirming the original data retains fractional seconds.
4. Design a filter for a local day using two `Instant` boundaries.

Check your work: (1) same instant despite different date/time; (2) local clock was preserved instead of the instant; (3) do not write back the truncated string; (4) derive start-of-day and start-of-next-day boundaries from the right `ZoneId`.