# Testing Round-Trip Conversions Between Java Data, Strings, and Storage

## 1. What Must a Successful Round-Trip Preserve?

A round-trip conversion typically has the form:

```text
Java value → exchange representation → storage
           → read-back representation → Java value
```

Not throwing an exception is not enough to conclude that this path is correct. The read-back value might lose nanoseconds, shift its instant due to a time zone, lose its offset, or lose its zone name while the program still runs normally.

Before testing, you must state the **data contract**:

- Must it preserve the same calendar date?
- Must it preserve the same local date-time fields?
- Must it preserve the same instant on the timeline?
- Does it need to preserve the original offset and zone name?
- Is precision reduction or string normalization allowed?

For example, `2024-01-15T09:00+07:00` and `2024-01-15T02:00Z` are the same instant, but they do not have the same date-time fields and offset. A check that only compares `Instant` will miss the loss of the offset if the requirement is to preserve the original offset.

Therefore, you must choose the equality criterion before choosing the assertion statement.

## 2. Three Types of Round-Trip Contracts

### 2.1. Exact Value Preservation

If no information loss is allowed, the requirement is:

```text
decode(encode(value)) = value
```

The equals sign here must carry the meaning appropriate to the type, not necessarily string equality or object reference equality.

For example, a `LocalDate` of 2024-02-29 formatted and then parsed back must be that exact date. An `Instant` with a fractional second of `.123456789` must preserve both the instant and the nanosecond part if the contract requires nanosecond precision.

### 2.2. Canonicalizing Representation While Preserving Value

An input string may have multiple equivalent ways of being written:

```text
2024-01-15T02:00:00.000Z
2024-01-15T02:00:00Z
```

These two strings have different characters but represent the same `Instant`. If the output is specified to be in canonical form, the test should verify:

1. The value after parsing and reformatting still preserves the exact meaning.
2. The output string matches the published canonical form.

Do not require the input string to be preserved character-for-character unless the application truly needs to store the verbatim text. If you need to preserve verbatim text for a specific purpose, keep the original string rather than hoping the date-time object remembers how it was originally written.

### 2.3. Precision Reduction by Explicit Rules

If the storage only retains microseconds and the contract chooses **truncation below microseconds**, you can require:

```text
decode(store(encode(value))) = normalize(value)
```

For example:

```text
Original value:    2024-01-15T02:00:00.123456789Z
After micro trunc: 2024-01-15T02:00:00.123456Z
```

You must explicitly specify truncation or rounding, what precision level, and where it is applied. Do not arbitrarily add "a difference under one second is acceptable" to hide bugs. A time zone offset error or data loss should not become a passing test just because the comparison tolerance is too wide.

The normalization rule should also be idempotent: re-normalizing an already normalized value must not continue to change it.

## 3. Choosing the Comparison by Type and Requirement

| Data to preserve | Typical comparison | What might be missed if chosen wrongly |
| --- | --- | --- |
| Calendar date `LocalDate` | `expected.equals(actual)` | Must not arbitrarily add or shift the date via a time zone |
| Date-time fields `LocalDateTime` | `equals`, including nanos | Comparing instants requires a time zone that is not present |
| Instant `Instant` | `equals` or compare epoch seconds and nanos | Comparing local strings can misinterpret display formatting |
| `OffsetDateTime` needing to keep offset | `equals` | Comparing only `toInstant()` does not detect offset changes |
| Only needing the instant from `OffsetDateTime` | Compare `toInstant()`, or `isEqual` | This is not a test for preserving the full object |
| `ZonedDateTime` needing to keep zone | Check full value and `ZoneId` | An offset-only string can lose the zone name |
| Period `YearMonth` | `equals` | Do not attach an arbitrary day and equate a period with a date |
| Canonical exchange string | Compare string against expected output pattern | Value equality does not guarantee protocol format compliance |

`OffsetDateTime.equals` checks both the date-time fields and the offset, whereas `isEqual` checks only the instant. This distinction is specified in [OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html).

Do not use `==` to test value equality of date-time objects. Two objects created at different times can still represent the same data.

## 4. Testing Each Hop and the Complete Path

You should break the evidence down into hops that can isolate failures:

1. **Java → string → Java:** tests formatting, parsing, semantics, and precision.
2. **String → storage → string:** tests actual write/read, encoding, and unintended mutations.
3. **Java → storage → Java:** tests the entire actual usage path, including the driver or mapper if present.

Testing only the formatter does not prove that a database column retains full fractional seconds. Conversely, seeing that bytes in a file remain intact does not prove that the parser reads the meaning correctly.

When a test fails, you should inspect the intermediate outputs:

- The string actually sent.
- The type and value written.
- The raw value read back.
- The Java object after the decoding step.
- The time zone/locale and precision level used at each point.

A round-trip can also mask **two mutually compensating bugs**. For example, both the writer and the reader use the same wrong unit relative to the published protocol. The Java value might come back the same, yet another system reads it incorrectly. Therefore, you also need independently defined expected data samples, rather than only testing that two functions written in the same codebase always match each other.

## 5. Designing Testable Exchange Strings

For an exchange protocol, determine the type first and then choose the corresponding formatter. For example:

- `LocalDate`: ISO date without time.
- `LocalDateTime`: local date-time, without an offset.
- `Instant`: an instant explicitly represented in UTC, such as a string with `Z`.
- `OffsetDateTime`: preserves the offset if required by the contract.
- `ZonedDateTime`: requires a format with a zone name if `ZoneId` must be preserved.

An offset-only string like `+01:00` does not by itself store the rules of `Europe/Paris`. On a specific date they may yield the same instant, but the zone name is needed to apply rules across other dates.

If using a custom pattern, the formatter must have an explicit locale and resolver style. In the program below, the pattern `uuuu-MM-dd` with `ResolverStyle.STRICT` rejects Feb 29 in a non-leap year. `uuuu` represents the proleptic year; do not arbitrarily replace it with `yyyy`, which represents the year-of-era.

Do not test only valid data. A strict input path must reject invalid dates instead of silently adjusting them and still being considered as preserving the input. Formatters, parsing rules, and configurations are described in [DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html).

## 6. Choosing Data Likely to Expose Information Loss

| Case group | Suggested data | Bug to detect |
| --- | --- | --- |
| Leap date | 2024-02-29 and string 2023-02-29 | Invalid validation or silent adjustment |
| Pre-epoch | Late 1969, with nanos | Sign error or wrong epoch conversion |
| Long fractional seconds | `.123456789` | Unintended truncation to millis/micros |
| Near end of day | 23:59:59 with nanos | Rounding or time zone shift moving to another day |
| Non-UTC offset | Same instant in `+07:00` and `Z` | Confusing same instant with same offset |
| Zone name | Value with `[Europe/Paris]` | Losing the zone when storing only the offset |
| Equivalent strings | With and without `.000` | Confusing canonicalization with value loss |
| Invalid strings | Empty, month 13, nonexistent day | Parser accepts invalid input |
| Missing values | SQL `NULL` or absent field | Silently converted to epoch, current date, or empty string |

For missing data, the contract must explicitly specify whether it is allowed to be missing and how it is represented. `NULL`, an empty string, and `1970-01-01T00:00Z` do not automatically mean the same thing.

Do not assume every Java extreme value works as a default for every storage system. The representable range of a SQL column or external system may be narrower; test the boundaries supported by the actual contract.

## 7. Java 17+ Program Testing Real Strings and Files

Save the following code as `DateTimeRoundTrip.java`. The program requires no external libraries. It writes and reads a temporary file in UTF-8, then deletes that exact file in `finally`.

Two storage paths are tested separately:

- Preserving nanoseconds using ISO strings.
- Intentionally truncating to microseconds **in the application before writing to the file**.

The second path illustrates a precision-reduction contract; it does not simulate or assert the rounding rules of any database.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.YearMonth;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoUnit;
import java.util.Locale;
import java.util.Objects;

public class DateTimeRoundTrip {
    private static int checks;

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

    public static void main(String[] args) throws Exception {
        DateTimeFormatter strictDate = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);

        for (LocalDate date : new LocalDate[] {
                LocalDate.of(2024, 2, 29),
                LocalDate.of(1969, 12, 31),
                LocalDate.of(2000, 2, 29)}) {
            eq(LocalDate.parse(date.format(strictDate), strictDate), date);
        }
        rejects(() -> LocalDate.parse("2023-02-29", strictDate));
        rejects(() -> LocalDate.parse("2024-13-01", strictDate));
        rejects(() -> LocalDate.parse("", strictDate));

        LocalDateTime local = LocalDateTime.parse("2024-06-30T23:59:59.123456789");
        eq(LocalDateTime.parse(local.toString()), local);
        YearMonth period = YearMonth.of(2024, 2);
        eq(YearMonth.parse(period.toString()), period);

        Instant original = Instant.parse("2024-01-15T02:00:00.123456789Z");
        for (Instant value : new Instant[] {
                Instant.EPOCH,
                Instant.parse("1969-12-31T23:59:59.999999999Z"),
                original}) {
            eq(Instant.parse(value.toString()), value);
        }

        String suppliedText = "2024-01-15T02:00:00.000Z";
        String canonicalText = Instant.parse(suppliedText).toString();
        eq(canonicalText, "2024-01-15T02:00:00Z");
        eq(Instant.parse(canonicalText), Instant.parse(suppliedText));
        eq(canonicalText.equals(suppliedText), false);

        OffsetDateTime suppliedOffset =
                OffsetDateTime.parse("2024-01-15T09:00:00+07:00");
        OffsetDateTime utc = OffsetDateTime.parse("2024-01-15T02:00:00Z");
        eq(suppliedOffset.toInstant(), utc.toInstant());
        eq(suppliedOffset.equals(utc), false);
        eq(OffsetDateTime.parse(suppliedOffset.toString()), suppliedOffset);

        ZonedDateTime zoned =
                ZonedDateTime.parse("2024-01-15T09:00:00+01:00[Europe/Paris]");
        eq(ZonedDateTime.parse(zoned.toString()), zoned);
        ZonedDateTime offsetOnly =
                ZonedDateTime.parse(zoned.toOffsetDateTime().toString());
        eq(offsetOnly.toInstant(), zoned.toInstant());
        eq(offsetOnly.getZone().equals(zoned.getZone()), false);

        Path file = Files.createTempFile("date-time-round-trip-", ".txt");
        boolean fileExact;
        boolean fileNormalized;
        Instant normalized = original.truncatedTo(ChronoUnit.MICROS);
        try {
            Files.writeString(file, original.toString(), StandardCharsets.UTF_8);
            String storedText = Files.readString(file, StandardCharsets.UTF_8);
            eq(storedText, original.toString());
            Instant restored = Instant.parse(storedText);
            eq(restored, original);
            fileExact = restored.equals(original);

            // Explicit application policy: truncate to microseconds.
            Files.writeString(file, normalized.toString(), StandardCharsets.UTF_8);
            Instant restoredMicros =
                    Instant.parse(Files.readString(file, StandardCharsets.UTF_8));
            eq(restoredMicros, normalized);
            eq(restoredMicros.equals(original), false);
            eq(restoredMicros.truncatedTo(ChronoUnit.MICROS), normalized);
            fileNormalized = restoredMicros.equals(normalized);
        } finally {
            Files.deleteIfExists(file);
        }

        System.out.println("canonicalText=" + canonicalText);
        System.out.println("sameInstant=" + suppliedOffset.toInstant().equals(utc.toInstant()));
        System.out.println("sameOffsetDateTime=" + suppliedOffset.equals(utc));
        System.out.println("zoneRetainedByOffsetOnly="
                + offsetOnly.getZone().equals(zoned.getZone()));
        System.out.println("fileExact=" + fileExact);
        System.out.println("normalized=" + normalized);
        System.out.println("fileNormalized=" + fileNormalized);
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 DateTimeRoundTrip.java
java DateTimeRoundTrip
```

Stdout:

```text
canonicalText=2024-01-15T02:00:00Z
sameInstant=true
sameOffsetDateTime=false
zoneRetainedByOffsetOnly=false
fileExact=true
normalized=2024-01-15T02:00:00.123456Z
fileNormalized=true
PASS checks=25
```

The `eq` method explicitly throws `AssertionError` on failure, so the `-ea` flag is not needed. The `rejects` method verifies that invalid strings are rejected with `DateTimeParseException`.

Meaning of the output lines:

- `canonicalText` shows that the representation can be normalized without changing the value.
- `sameInstant=true` together with `sameOffsetDateTime=false` demonstrates two different comparison criteria.
- `zoneRetainedByOffsetOnly=false` is the **expected result of the zone-loss detection case**, not a successful zone-preserving save.
- `fileExact` verifies that the raw string storage path preserves the exact `Instant`.
- `fileNormalized` verifies that the microsecond truncation path matches the stated policy, while the program also confirms it differs from the original nanosecond value.

File operations are described in [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html). The epoch-second and nanosecond model of an instant is described in [Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html).

## 8. Re-running Under Different Environments

Because the program uses well-defined representations and data types, the output should remain stable when the default time zone changes. You can run it twice:

```shell
java "-Duser.timezone=UTC" DateTimeRoundTrip
java "-Duser.timezone=GMT+07:00" DateTimeRoundTrip
```

Quoting the configuration argument also helps avoid argument-parsing quirks in some shells. Both runs must produce the same stdout as above and pass all 25 checks.

This is an environment-dependence detection test for the given program. When the actual path involves a driver, serializer, or another service, you must re-run that exact path. The file example passing in two time zones does not by itself prove the entire system has no hidden dependencies.

If the protocol includes month names in text, also test all supported locales. For regional time zones with offset transitions, you need test cases for gaps and overlaps; preserving an instant and preserving a local wall-clock schedule may require different policies.

## 9. Extending to Database Testing

Testing SQL storage requires actually writing and reading through the driver, not just converting to `Timestamp` in memory. An integration test should include these steps:

1. Create test data and expected results from the published contract.
2. Write to the exact column type using the exact path the application uses.
3. Complete the necessary commit/flush steps so that the read actually sees the data.
4. Read it back using JDBC or the actual mapper.
5. Compare according to the chosen semantics and precision level.
6. Clean up test data or use an appropriately isolated transaction.

If using an ORM, ensure the read does not merely return an object cached in the session. You need to observe a real storage read to test transformations performed by the column and driver.

A read-check snippet for local data might look like this:

```java
// Illustrative code in an integration test, not a standalone program.
// expected has been created from a fixture; rs points to the newly written row.
// local_value is a column contracted to preserve local date-time.
LocalDateTime actual =
        rs.getObject("local_value", LocalDateTime.class);
if (!Objects.equals(actual, expected)) {
    throw new AssertionError("Local date-time changed during storage");
}
```

Converting from a column to a Java type requires driver support; see [ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html). For instants, use a mapping path that preserves the instant and compare `Instant`, while documenting how the column's time zone is interpreted.

For columns with lower precision than Java, do not immediately use the original nanosecond `expected` value if the contract has chosen precision reduction. Compute the expected value using an independent rule, with specific samples that distinguish truncation from rounding. For example, a value near the threshold of rolling over to the next second helps detect rounding versus truncation.

This lesson does not configure a specific DBMS or driver, so the program only demonstrates the string and file paths. SQL tests are something that must be executed in a real storage environment.

## 10. Common Mistakes

- **Only checking that no exception is thrown:** the operation may succeed while losing precision or shifting the instant.
- **Comparing strings instead of semantics:** the representation may be validly canonicalized.
- **Comparing only instants when preserving offset/zone is required:** information loss still passes the test.
- **Comparing only local date-time when preserving an instant is required:** may miss time zone misinterpretation.
- **Using the conversion code itself to generate all expected results:** two corresponding bugs can mask each other.
- **Skipping negative pre-epoch cases and nanoseconds:** testing only whole-second values often fails to expose bugs.
- **Allowing overly wide tolerances:** hides bugs instead of verifying the precision policy.
- **Replacing `NULL` with an unrequested default value:** loses the distinction between missing and present data.
- **Testing in memory but claiming storage is correct:** real write/read through the integration path is required.

## 11. Practice

1. **Add the sample `2024-12-31T23:59:59.999999999Z`.** The nanosecond-preserving path must read it back accurately. If switching to a policy that rounds to a different precision, explicitly state the expected result, including the possibility of rolling over to the next year when rounding.

2. **Require preserving the original offset of an `OffsetDateTime`.** Change the test criterion to full value equality; comparing only `Instant` is not enough.

3. **Require preserving the zone name.** Use an exchange path containing `ZoneId` or store a separate zone field. Demonstrate that an offset-only case fails this contract.

4. **Input string has `.000Z`, output has no fractional part.** Verify the same `Instant` and the correct canonical form; do not flag value loss just because the character count decreased.

5. **Column stores microseconds while input has nanoseconds.** Create at least two samples that distinguish truncation from rounding, then compare against the chosen actual rule; do not treat any result returned by storage as the ground truth without evaluating it.

A round-trip conversion test is valuable when it proves the exact information that must be preserved, over the actual data path, with any allowed changes explicitly stated.
