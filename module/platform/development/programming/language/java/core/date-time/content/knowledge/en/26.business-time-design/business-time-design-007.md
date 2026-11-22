# Do Not Use Formatted Strings as Internal Date-Time Data

## 1. Date-Time Values and Display Are Two Different Things

An instant such as `2024-01-15T02:00:10.123Z` can be displayed as:

```text
15/01/2024 09:00
15 Jan 2024, 09:00
2024-01-15 02:00 UTC
```

These strings are meant for human readers; they do not share the same structure and do not necessarily preserve all of the original information. If a string only displays down to the minute, it has already dropped seconds and fractional seconds. Without an offset or time zone, a reader of the code also does not know which location's time to interpret it in.

In business logic, keep values in an appropriate type such as `LocalDate`, `YearMonth`, `LocalDateTime`, `Instant`, or a type with an offset/zone. Format only when communicating with users or exporting data under a clear contract.

The goal of this rule is to prevent a display label from becoming the data source for comparisons, calculations, or decision-making. Input and output strings still have their proper role at system boundaries.

## 2. Why Do Display Strings Break Business Logic?

### 2.1. String Comparison Differs from Date Comparison

Two dates:

```text
31/12/2024
01/01/2025
```

On the calendar, 31/12/2024 comes before 1/1/2025. In lexicographical order, the string starting with `01` comes before the string starting with `31`.

Therefore, `String.compareTo`, `sorted()` on display labels, or string comparison operators in another layer do not inherently carry calendar semantics.

The right approach is to sort `LocalDate` first, and only then format each date. If the data represents events on a timeline, sort by `Instant`, not by each user's displayed local time.

### 2.2. One Label Can Correspond to Multiple Values

Two instants `02:00:10.123Z` and `02:00:59.999Z` are both displayed as “09:00” at offset +07:00 when the pattern only includes hours and minutes.

Identical labels do not mean events happened at the same time. Therefore:

- Do not use minute-level labels to detect whether two instants are equal.
- Do not use formatted labels as event identifiers.
- Do not use rounded display results to check deadlines or ordering.

Event identifiers are a separate responsibility. Typed instants are used for calculations and filtering; display labels are used for presentation.

### 2.3. Changing Locale or Time Zone Must Not Change the Underlying Data

One user views Vietnam time while another views UTC; both may be looking at the same event. Changing the display format should not alter the `Instant` in the model.

If internal data is already a localized string, every re-display may require guessing the original locale, format, or time zone. That information may no longer be stored.

`Instant` models a point on the timeline, whereas `LocalDate` models a date without a time of day or time zone. Choosing the right type keeps what the data represents clear; see [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) and [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html).

## 3. ISO Does Not Automatically Turn Every String Comparison into a Time Comparison

Some strictly defined representations can preserve order under string comparison, such as year-month-day dates with fixed field widths and a compatible year range. However, that conclusion must not be generalized to every string that “looks like ISO”.

Factors that can break ordering:

- Strings using different offsets.
- Strings with and without fractional seconds.
- Fractional seconds of different lengths.
- Year ranges or year signs with different structures.
- Strings that include additional zone information or alternative representations.

Even with two `Instant` values:

```text
2024-01-15T02:00:00Z
2024-01-15T02:00:00.001Z
```

The first instant occurs earlier. Yet when comparing these two strings, the character `Z` of the first string is compared against `.` in the second string, resulting in a lexicographical order opposite to the intended chronological order.

Hence, `toString()` is useful for exchanging data in a defined structure, but it is not a reason to skip typed comparisons in business logic. If a system intentionally designs an order-preserving string key, it must publish the exact format and applicability conditions; that is a separate contract.

## 4. Choose Internal Types Based on Data Semantics

| Meaning | Type to Consider | What Not to Add or Drop Implicitly |
| --- | --- | --- |
| Birth date or specific holiday | `LocalDate` | Do not attach a time and time zone if not yet needed |
| Monthly reporting period | `YearMonth` | Do not add day 1 as if a day of month existed |
| Local date-time without a zone | `LocalDateTime` | Do not treat it as a UTC instant |
| Event fixed on the timeline | `Instant` | Do not turn it into a local string and lose the zone |
| Data that must preserve its offset | `OffsetDateTime` | Keeping only `Instant` drops the original offset |
| Schedule tied to a zone with rules | `ZonedDateTime` or date-time + `ZoneId` per model | Do not replace all zone rules with a single time label |

Choosing `LocalDateTime` does not by itself solve the instant problem: it contains neither an offset nor a time zone. Choosing a type merely because it is easy to format is not enough; the type must match the semantics.

Nor is it necessary to replace strings with a bare epoch number everywhere. If numbers are used in a protocol, the unit and conversion rules must be specified; in Java, temporal types still help avoid confusing seconds with milliseconds.

## 5. Processing Flow: Parse at Input, Format at Output

A flow with clear responsibilities:

```text
String from form / JSON / file
            ↓ parse according to input contract
Typed value in Java
            ↓ validate, compare, sort, calculate
Typed business result
            ↓ choose locale, time zone, and display pattern
String on screen / report
```

### 5.1. Input

External strings must follow a convention. For example:

- A form accepts dates in `dd/MM/uuuu`.
- An API accepts instants with an explicit offset.
- A monthly period field accepts `uuuu-MM`.

Parse once at the boundary where data enters, then pass typed objects into business functions. When input is invalid, report an error according to the contract; do not silently fall back to the current date, the epoch, or an arbitrary time zone to fill in missing parts.

With custom patterns used for validation, you should specify the date resolution mode. For example, this article uses `ResolverStyle.STRICT` to reject `29/02/2023`.

### 5.2. Business Logic

Processing functions accept and return temporal types:

- Compare dates using `isBefore`, `isAfter`, `equals`.
- Perform calendar arithmetic using APIs such as `plusDays`, `plusMonths`.
- Sort events by their `Instant` field.
- Group by `LocalDate` or `YearMonth` determined under the proper zone/rules.

Do not format and then split with `substring` to extract the month or year. Those fields already have direct APIs on the objects.

### 5.3. Output

At the presentation layer or in response objects built for the UI, formatted strings are appropriate. An `Event` model can hold `Instant startsAt`, while `EventView` holds `String displayStart`.

The key point is that `displayStart` must not flow back in as the source for calculating deadlines or sorting events. Keep typed data or interchange data with a dedicated contract for those operations.

`DateTimeFormatter` allows configuring the pattern, locale, and time zone; the formatter itself is immutable and safe to share according to its contract. These operations belong to the presentation/parsing responsibility, not as a substitute for the business model; see [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 6. Java 17+ Program Demonstrating the Bug and the Fix

Save the following code as `TypedDateTimeInside.java`. The program requires no external libraries.

`Event` stores the instant as `Instant`; `EventView` holds a string solely for display. `readInput` parses the input, while `toView` only formats at the output.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class TypedDateTimeInside {
    public record Event(String id, Instant startsAt) {
        public Event {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(startsAt, "startsAt");
        }
    }

    public record EventView(String id, String displayStart) {}

    private static final DateTimeFormatter INPUT_DATE =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);
    private static int checks;

    private static Event readInput(String id, String rawInstant) {
        return new Event(id, Instant.parse(rawInstant));
    }

    private static EventView toView(Event event, DateTimeFormatter display) {
        return new EventView(event.id(), display.format(event.startsAt()));
    }

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Runnable action) {
        try {
            action.run();
        } catch (DateTimeParseException expected) {
            checks++;
            return;
        }
        throw new AssertionError("Expected DateTimeParseException");
    }

    public static void main(String[] args) {
        LocalDate last = LocalDate.parse("31/12/2024", INPUT_DATE);
        LocalDate next = LocalDate.parse("01/01/2025", INPUT_DATE);
        List<LocalDate> dates = List.of(next, last);
        List<String> textOrder = dates.stream().map(INPUT_DATE::format)
                .sorted().toList();
        List<String> dateOrder = dates.stream().sorted()
                .map(INPUT_DATE::format).toList();
        eq(last.isBefore(next), true);
        eq(textOrder, List.of("01/01/2025", "31/12/2024"));
        eq(dateOrder, List.of("31/12/2024", "01/01/2025"));
        eq(last.plusDays(1), next);
        rejects(() -> LocalDate.parse("29/02/2023", INPUT_DATE));

        Event first = readInput("A", "2024-01-15T02:00:10.123Z");
        Event second = readInput("B", "2024-01-15T02:00:59.999Z");
        DateTimeFormatter display = DateTimeFormatter
                .ofPattern("dd/MM/uuuu HH:mm", Locale.ROOT)
                .withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        EventView firstView = toView(first, display);
        EventView secondView = toView(second, display);
        eq(first.startsAt().isBefore(second.startsAt()), true);
        eq(firstView.displayStart(), "15/01/2024 09:00");
        eq(firstView.displayStart(), secondView.displayStart());
        eq(first.startsAt().equals(second.startsAt()), false);
        eq(toView(first, display.withZone(ZoneOffset.UTC)).displayStart(),
                "15/01/2024 02:00");
        eq(first.startsAt(), Instant.parse("2024-01-15T02:00:10.123Z"));

        List<String> eventOrder = List.of(second, first).stream()
                .sorted(Comparator.comparing(Event::startsAt))
                .map(Event::id).toList();
        eq(eventOrder, List.of("A", "B"));
        rejects(() -> readInput("C", "2024-01-15T09:00:00"));

        Instant whole = Instant.parse("2024-01-15T02:00:00Z");
        Instant fraction = whole.plusMillis(1);
        eq(whole.isBefore(fraction), true);
        eq(whole.toString().compareTo(fraction.toString()) > 0, true);
        eq(Instant.parse(first.startsAt().toString()), first.startsAt());

        System.out.println("textOrder=" + textOrder);
        System.out.println("dateOrder=" + dateOrder);
        System.out.println("sharedDisplay=" + firstView.displayStart());
        System.out.println("differentInstants="
                + !first.startsAt().equals(second.startsAt()));
        System.out.println("eventOrder=" + eventOrder);
        System.out.println("wholeBeforeFraction=" + whole.isBefore(fraction));
        System.out.println("wholeTextBeforeFractionText="
                + (whole.toString().compareTo(fraction.toString()) < 0));
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TypedDateTimeInside.java
java TypedDateTimeInside
```

Stdout:

```text
textOrder=[01/01/2025, 31/12/2024]
dateOrder=[31/12/2024, 01/01/2025]
sharedDisplay=15/01/2024 09:00
differentInstants=true
eventOrder=[A, B]
wholeBeforeFraction=true
wholeTextBeforeFractionText=false
PASS checks=16
```

Explanation of the results:

- `textOrder` sorts character by character and produces the wrong calendar order.
- `dateOrder` sorts the typed dates first, and formats them afterward.
- `sharedDisplay` is identical for two different instants because the pattern drops seconds.
- `eventOrder` still puts A before B because it uses `Instant`.
- The last two lines prove that comparing strings from `Instant.toString()` is not automatically right for every pair of instants.

The `eq` helper actively throws `AssertionError` on mismatch, so the `-ea` flag is not needed. The `rejects` helper verifies that invalid data is rejected. The program also checks that switching the display time zone to UTC does not change the instant in the model.

In this example, the form date is `LocalDate` data, whereas the event input is an instant. The string `2024-01-15T09:00:00` is rejected when parsed as `Instant` because it lacks an offset; the program does not guess whether it is UTC or Vietnam time.

## 7. Strings Still Have a Role at Boundaries and in Storage

This article's rule does not forbid using strings in JSON, CSV, logs, configuration files, or well-designed storage columns. What must be avoided is using **a string formatted for human reading** as if it were a validated internal date-time value.

Distinguish among:

| String Type | Purpose | Proper Usage |
| --- | --- | --- |
| Input string | External data awaiting validation | Parse according to the published format |
| Protocol string | Exchange between systems | Explicit semantic type, offset/zone, and precision |
| Display string | Human reading by locale/time zone | Format from a typed value |
| Raw string to retain | Keep original input for a specific purpose | Store separately; do not treat it as validated data |

If a store persists date-times as text, the reading layer must convert them to the appropriate type before computation. Round-trip tests must prove that information is preserved according to the contract, including sub-second parts and zone context when needed.

A serializer can let the Java model continue using `Instant` while JSON emits a string. That is not a contradiction: the wire representation and the model type belong to two different layers. The exact mapping must be configured and verified for the library in use.

## 8. Places Where Display Strings Accidentally Become Data Sources

### Date Filtering and Searching

If a user picks a date, parse it into `LocalDate`. If you need to find events on that day, compute the instant range in the appropriate time zone and compare temporal values. Do not filter by a prefix of a locale-formatted display string.

### Report Grouping

Group by `YearMonth` or a typed date, then generate the label for each group. If you use a label like “February 2024” as the key from the start, changing the language or formatting style can create multiple keys for the same period.

### Caching and Identifiers

A string like “15/01/2024 09:00” can collide across multiple events. Use real identifiers for objects and keep typed times for temporal criteria. If you intentionally use a canonical time key, define its semantics and precision—do not use a screen label as an ad-hoc key.

### Deadline Checks

Do not compare `deadlineText` with `todayText`. For date-based deadlines, compare `LocalDate` values under the same business date rules. For instant-based deadlines, compare `Instant` values. The two kinds of deadlines have different semantics even when the UI prints a date for both.

## 9. Migrating String-Based Code to a Typed Model

You can improve the code step by step:

1. **Identify the meaning of each field.** Does the string represent a calendar date, a local time, an instant, or a monthly period?
2. **Choose the right type.** Do not pick `LocalDateTime` for every field just because it has many components.
3. **Centralize parsing at the input boundary.** Publish the expected format and error handling.
4. **Update computation method signatures.** Pass temporal types instead of display strings.
5. **Replace string comparisons and slicing.** Use calendar APIs and comparators on typed fields.
6. **Move formatting to the output boundary.** Each display site selects the locale/time zone it needs without modifying the underlying value.
7. **Audit legacy data and information loss.** If only minutes were stored previously, the original seconds/nanoseconds cannot be recovered automatically.
8. **Verify protocols and storage.** Ensure conversions do not alter meaning as data crosses layers.

Do not fix historical data by guessing. If a string lacks a time zone but the business domain requires an instant, there must be an authoritative rule for interpreting it; merely renaming the field to `Instant` does not supply the missing information.

## 10. Common Pitfalls and Practice

Pitfalls to avoid:

- Treating lexicographical sorting as chronological sorting for all formats.
- Formatting too early, then re-parsing multiple times in internal functions.
- Using a label that dropped seconds as the source of truth.
- Using the same string simultaneously as a display label, a key, and a filter condition.
- Assuming every ISO-like format preserves order under character comparison.
- Implicitly picking a time zone from the environment when decoding a local string.
- Substituting the current date/time for invalid data without a requirement to do so.
- Assuming that replacing a string with any temporal type is already semantically correct.

Practice:

1. **A deadline list contains “31/01/2025”, “01/02/2025”, “15/12/2024”.** Parse into `LocalDate`, sort, and then format. The correct result is 15/12/2024, 31/01/2025, 01/02/2025.

2. **The UI only wants to display down to the minute, but event ordering needs millisecond accuracy.** Keep the full `Instant` in the model; the output pattern can omit seconds while sorting still uses the original value.

3. **The user changes their display time zone.** Generate a new label from the same instant; do not add/subtract hours on the event data just to change what the screen shows.

4. **A report groups by month and supports two languages.** Group by `YearMonth`, then label each group in the target language after grouping. Do not let the same period split into two groups because of different labels.

5. **An instant input is missing an offset.** If the contract requires an explicit instant, return an error or require the specified context. Do not use an incomplete string to assert an `Instant`.

Let temporal types hold the semantics and power computations; let formatters decide how users see the result. When these two responsibilities are kept separate, changing the display format will not alter business rules.
