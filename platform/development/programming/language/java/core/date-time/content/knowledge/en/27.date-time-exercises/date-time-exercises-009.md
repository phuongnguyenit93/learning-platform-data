# Building a Boundary Case Table for Time Zones, Leap Years, Precision, and Invalid Inputs

## 1. Boundary Cases Must Test a Specific Contract

A program that runs correctly with `2025-06-15T10:00` does not yet prove it handles end-of-month dates, DST transitions, values losing fractional seconds, or malformed strings. Boundary cases are inputs where rules branch or hit limits.

Before building the table, state clearly what the system must preserve: the same instant or the same local time, whether the endpoint is inclusive or exclusive, whether the parser auto-corrects dates, and to what unit precision is stored. Without a finalized contract, the table has inputs without expected results.

A test row should contain **case ID, condition/rule, input, expected result, and what it proves**. Expected results must be determined independently of the function under test; do not treat the current output as the baseline just because the program does not report an error.

## 2. Finalizing the Sample Scope

This article uses the ISO calendar, JDK 17 or later, and the following illustrative contracts:

- Resolve local time with `ZoneId`; gaps/overlaps must be identified before choosing a policy.
- Parse dates strictly as `dd/MM/uuuu`.
- Exclusive expiration endpoint: at the exact end timestamp, it is already expired.
- Preserve nanoseconds in memory; when reducing precision, an explicit rule must be known.

This is the scope for creating verifiable test cases; products with different policies must substitute the corresponding expected results.

## 3. Time Zone Case Table

| ID | Input and Check | Expected Result | What Does It Detect? |
| --- | --- | --- | --- |
| Z01 | Berlin `2025-02-10T10:00`, count valid offsets | 1 | Normal path |
| Z02 | Berlin `2025-03-30T02:30` | 0 offsets | Non-existent hour during spring forward |
| Z03 | Berlin `2025-10-26T02:30` | 2 offsets | Hour occurring twice |
| Z04 | Both occurrences of Z03 | `00:30Z` and `01:30Z` | Same local clock time but different instants |
| Z05 | `2025-12-31T18:00Z` displayed in Vietnam | `2026-01-01T01:00` | Zone conversion changes both date and year |
| Z06 | Convert zone using `withZoneSameInstant` | `toInstant()` unchanged | Does not shift the event when only changing the view |
| Z07 | March 30, 2025 in Berlin, start of day to start of next day | 23 actual elapsed hours | A local day is not always 24 hours |
| Z08 | Non-existent zone name | Rejected with zone error | Does not silently fall back to another zone |

Use `getValidOffsets(local)` to identify the state, rather than guessing by the month of the year. Zone results must be tied to the rule data used in the runtime environment. [ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html)

If the application must operate in zones with non-whole-hour offsets or transitions not lasting one hour, add the exact zones/dates to support. Do not use Berlin alone as proof for every rule in the world.

## 4. Calendar and Leap Year Case Table

| ID | Input | Expected Result | What Does It Detect? |
| --- | --- | --- | --- |
| L01 | `LocalDate.of(2024, 2, 29)` | Valid | Standard leap year |
| L02 | `LocalDate.of(2023, 2, 29)` | `DateTimeException` | Common year |
| L03 | `Year.isLeap(2000)` | `true` | Divisible-by-400 exception |
| L04 | `Year.isLeap(2100)` | `false` | Not just checking divisibility by 4 |
| L05 | `MonthDay.of(2,29).atYear(2023)` | `2023-02-28` | Adjustment behavior of the API |
| L06 | `2024-01-31.plusMonths(1)` | `2024-02-29` | Last day of the target month |
| L07 | Result of L06 minus one month | `2024-01-29` | Adding/subtracting months is not always reversible |
| L08 | `LocalDate.MAX.plusDays(1)` | Out-of-range error | Representation limit |

L05 does not prove that a product's Feb 29 birthday policy is correct. If the requirement is to skip common years or move to March 1, the table needs test cases for that policy. [Year](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Year.html)

## 5. Precision and Boundary Case Table

| ID | Input / Operation | Expected Result |
| --- | --- | --- |
| P01 | `2025-01-01T00:00:00.123456789Z` kept in Instant | 123456789 nanoseconds |
| P02 | Value P01 `truncatedTo(MILLIS)` | Fractional part `.123Z` |
| P03 | Via `java.util.Date.from(...).toInstant()` | Loses sub-millisecond part |
| P04 | Format then parse with ISO_INSTANT contract | Same Instant if precision is not reduced |
| P05 | `now = end - 1ns`, exclusive end | Still valid |
| P06 | `now = end`, exclusive end | Expired |
| P07 | `now = end + 1ns`, exclusive end | Expired |
| P08 | Write/read timestamp through real DB | Matches the declared precision rule of the schema/driver |

`truncatedTo` truncates down to the supported unit, rather than rounding to the nearest value. P02 is a model of intentional precision reduction; do not assume every DB applies the same truncation method. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#truncatedTo(java.time.temporal.TemporalUnit))

For DB/API, state the unit and rounding rule explicitly, then verify after a real round-trip. An in-memory test case does not prove the driver preserves fractional seconds or offsets as intended.

## 6. Invalid Input Case Table

| ID | Input for Date Contract | Expected Result |
| --- | --- | --- |
| I01 | `29/02/2024` | Succeeds as `2024-02-29` |
| I02 | `29/02/2023` | Non-existent date error |
| I03 | `31/04/2024` | Non-existent date error, not corrected to April 30 |
| I04 | `2024-02-29` | Format error |
| I05 | `29/02/2024xyz` | Trailing characters error |
| I06 | `null` or blank | Missing data error defined by the input layer |
| I07 | `1/2/2024` | Rejected if contract requires two digits |
| I08 | `01/01/0000` | Result depends on application year range; LocalDate's ISO calendar allows year 0 |

Separate format, calendar validity, and business rules. `STRICT` checks validity when resolving fields; it does not automatically know that a birth date cannot be in the future or whether the application forbids year 0. [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

## 7. Program Turning Part of the Table into Automated Checks

The program below uses explicitly written conditions and does not require enabling `-ea`. It intentionally catches only the required exception class; if no exception is thrown or a different exception type occurs, the check fails.

Save as `DateTimeBoundaryChecks.java`:

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.MonthDay;
import java.time.Year;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class DateTimeBoundaryChecks {
    private static final DateTimeFormatter INPUT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    static void check(String id, boolean condition) {
        if (!condition) {
            throw new AssertionError("Failed: " + id);
        }
        System.out.println(id + " PASS");
    }

    static void expect(String id, Class<? extends Throwable> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable error) {
            if (!type.isInstance(error)) {
                throw new AssertionError("Wrong exception: " + id, error);
            }
            System.out.println(id + " PASS");
            return;
        }
        throw new AssertionError("Expected exception: " + id);
    }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        check("Z01", berlin.getRules().getValidOffsets(
                LocalDateTime.of(2025, 2, 10, 10, 0)).size() == 1);
        check("Z02", berlin.getRules().getValidOffsets(
                LocalDateTime.of(2025, 3, 30, 2, 30)).isEmpty());
        LocalDateTime overlap = LocalDateTime.of(2025, 10, 26, 2, 30);
        var offsets = berlin.getRules().getValidOffsets(overlap);
        check("Z03", offsets.size() == 2);
        Instant first = ZonedDateTime.ofStrict(overlap, offsets.get(0), berlin).toInstant();
        Instant second = ZonedDateTime.ofStrict(overlap, offsets.get(1), berlin).toInstant();
        check("Z04", first.equals(Instant.parse("2025-10-26T00:30:00Z"))
                && second.equals(Instant.parse("2025-10-26T01:30:00Z")));

        check("L01", LocalDate.of(2024, 2, 29).getDayOfMonth() == 29);
        expect("L02", DateTimeException.class, () -> LocalDate.of(2023, 2, 29));
        check("L03", Year.isLeap(2000));
        check("L04", !Year.isLeap(2100));
        check("L05", MonthDay.of(2, 29).atYear(2023)
                .equals(LocalDate.of(2023, 2, 28)));
        LocalDate monthEnd = LocalDate.of(2024, 1, 31).plusMonths(1);
        check("L06", monthEnd.equals(LocalDate.of(2024, 2, 29)));
        check("L07", monthEnd.minusMonths(1).equals(LocalDate.of(2024, 1, 29)));

        Instant precise = Instant.parse("2025-01-01T00:00:00.123456789Z");
        Instant millis = Instant.parse("2025-01-01T00:00:00.123Z");
        check("P01", precise.getNano() == 123456789);
        check("P02", precise.truncatedTo(ChronoUnit.MILLIS).equals(millis));
        check("P03", Date.from(precise).toInstant().equals(millis));
        Instant end = Instant.parse("2025-01-01T01:00:00Z");
        List<Boolean> expired = List.of(end.minusNanos(1), end, end.plusNanos(1))
                .stream().map(now -> !now.isBefore(end)).toList();
        check("P05-P07", expired.equals(List.of(false, true, true)));

        check("I01", LocalDate.parse("29/02/2024", INPUT)
                .equals(LocalDate.of(2024, 2, 29)));
        expect("I02", DateTimeParseException.class,
                () -> LocalDate.parse("29/02/2023", INPUT));
        expect("I03", DateTimeParseException.class,
                () -> LocalDate.parse("31/04/2024", INPUT));
        expect("I05", DateTimeParseException.class,
                () -> LocalDate.parse("29/02/2024xyz", INPUT));

        LocalDate day = LocalDate.of(2025, 3, 30);
        Duration elapsed = Duration.between(day.atStartOfDay(berlin).toInstant(),
                day.plusDays(1).atStartOfDay(berlin).toInstant());
        check("Z07", elapsed.equals(Duration.ofHours(23)));
    }
}
```

Compile and run:

```shell
javac --release 17 DateTimeBoundaryChecks.java
java DateTimeBoundaryChecks
```

Exact stdout with IANA time zone data under Berlin rules in 2025:

```text
Z01 PASS
Z02 PASS
Z03 PASS
Z04 PASS
L01 PASS
L02 PASS
L03 PASS
L04 PASS
L05 PASS
L06 PASS
L07 PASS
P01 PASS
P02 PASS
P03 PASS
P05-P07 PASS
I01 PASS
I02 PASS
I03 PASS
I05 PASS
Z07 PASS
```

Rows not yet automated in the program still need to be tested at the appropriate layer. In particular, P08 requires a real DB/driver/schema; I06 and year limits require the application's input function.

## 8. Adding Invariant Relations to Strengthen Testing

Besides concrete outputs, you can test invariant relations:

- Changing the zone to view the same event must preserve `toInstant()`.
- Formatting/parsing under a contract that does not reduce precision must preserve the value.
- Concatenating adjacent half-open intervals must not put a boundary point into two intervals.
- Computing actual elapsed duration from two Instants does not depend on a zone used only for display.

Do not apply a relation that is not in the contract. For example, "adding one month then subtracting one month must return to the original date" is false at the end of a month; L07 exists to prevent that exact assumption.

## 9. Managing Environments and Reading Test Failures

Record the JDK, time zone data, explicit locale, and DB/driver versions whenever those factors affect results. Do not let tests use the current date or default zone unless you are intentionally testing that dependency.

When testing errors, verify the exact exception type or application error code; do not just accept "any exception". When testing success, verify the value and the meaning that must be preserved; "did not throw" is not enough.

Do not relax expected results just to make every environment green. First determine whether the difference comes from policy, rule data, precision, or a real bug.

## 10. Extended Practice

1. Convert the table into JUnit test cases for a specific business function.
2. Add before/at/after pairs around the expiration boundary using the system's actual precision.
3. Add checks for non-existent zones and understandable input error messages.
4. Add a real DB write/read round-trip, checking Instant, fractional seconds, and SQL NULL according to the chosen schema.

A complete table should allow someone else to understand the reason for each case and decide pass/fail directly from the contract, rather than guessing after seeing the output.
