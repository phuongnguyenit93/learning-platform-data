# Fractional Second Formatting and Precision Impact

In the Java Date-Time API (`java.time`), the fractional part of a second is represented with nanosecond precision. However, **formatting a value with fewer digits does not automatically round or modify the original object**. Format patterns, string parsing, truncation, and storage precision are separate concerns.

For example, the same `LocalTime` value with a nanosecond part of `123_987_654` can be displayed in three ways:

~~~text
12:34:56.123          (3 decimal digits, to milliseconds)
12:34:56.123987       (6 digits, to microseconds)
12:34:56.123987654    (9 digits, to nanoseconds)
~~~

The first string only **displays** three digits of the fractional part. The value in memory still has `123_987_654` nanoseconds until the application actively transforms it or writes it to a target with lower precision.

## 1. What Do Fractional Seconds Mean?

One second is divided into decimal units:

| Unit | Parts per second | Fractional example |
|---|---:|---|
| Second | 1 | `12:34:56` |
| Millisecond (ms) | 1,000 | `.123` equals 123 ms |
| Microsecond (µs) | 1,000,000 | `.123987` equals 123,987 µs |
| Nanosecond (ns) | 1,000,000,000 | `.123987654` equals 123,987,654 ns |

In `java.time`, `LocalTime`, `LocalDateTime`, `OffsetTime`, `OffsetDateTime`, `ZonedDateTime`, and `Instant` support a nanosecond part within the range of their respective types. It can be read with `getNano()` on types that have a nanosecond component.

~~~java
LocalTime time = LocalTime.of(12, 34, 56, 123_987_654);
int nano = time.getNano(); // 123987654
~~~

`getNano()` returns **the nanoseconds within the current second**, in the range `0` to `999_999_999`. It is not the number of nanoseconds since midnight or since the epoch.

Representation precision also does not guarantee measured precision: an object may hold 9 digits while the system clock only provides values updated in larger steps. At least three concepts should be distinguished:

- **Data type precision:** how many digits of the fractional part the type is capable of holding.
- **Clock source resolution/accuracy:** at what level the actual clock can measure or return instants.
- **Formatting/storage precision:** how many digits are written to a string or database.

## 2. DateTimeFormatter Patterns Using `S`

With `DateTimeFormatter.ofPattern(...)`, the pattern letter `S` means **fraction-of-second**. The number of `S` letters determines how many fractional digits are output:

~~~java
DateTimeFormatter millis = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
DateTimeFormatter micros = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSS");
DateTimeFormatter nanos = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");
~~~

| Pattern | Fractional digits | Corresponding display level |
|---|---:|---|
| `HH:mm:ss` | 0 | Hours, minutes, seconds only |
| `HH:mm:ss.S` | 1 | 1 decimal digit |
| `HH:mm:ss.SSS` | 3 | Milliseconds |
| `HH:mm:ss.SSSSSS` | 6 | Microseconds |
| `HH:mm:ss.SSSSSSSSS` | 9 | Nanoseconds |

For example, `12:34:56.123987654` formatted with `SSS` becomes `12:34:56.123`; the digits after milliseconds do not appear. With `SSSSSS`, the string is `12:34:56.123987`. With 9 `S` letters, the full `123987654` is preserved in the string.

**Do not confuse `S` with `s`:**

- `s` is the **second-of-minute** field (0–59).
- `S` is the **fraction-of-second** field.
- `m` is minute, while `M` is month when used in date-time patterns.

Using the wrong case can produce a string that looks plausible but carries a different meaning. A pattern with a dot such as `HH:mm:ss.SSS` also hardcodes the decimal point in that pattern; if you need locale-aware formatting or flexible format handling, choose an appropriate formatter instead of concatenating strings manually.

## 3. Shorter Formatting Truncates the Display, Not Rounds

`DateTimeFormatter` converts an object to a string. It **does not modify the source object** and does not automatically apply mathematical rounding when the pattern has fewer `S` digits.

~~~java
LocalTime time = LocalTime.of(12, 34, 56, 123_987_654);
DateTimeFormatter formatter = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");

System.out.println(time.format(formatter)); // 12:34:56.123
System.out.println(time);                   // 12:34:56.123987654
~~~

The remaining nanoseconds are no longer in the short formatted string; they are still in `time`. This is different from calling a truncation operation to create a new value:

~~~java
LocalTime truncated = time.truncatedTo(ChronoUnit.MILLIS);
// truncated = 12:34:56.123
// time is still 12:34:56.123987654
~~~

In this example, both the formatted string and the truncated value print `12:34:56.123`, but **only `truncated` is an object that has lost the sub-millisecond nanoseconds**. If you need to keep the original data for calculations and only want a compact UI, just format it. If the data contract requires millisecond precision, intentionally normalize the value before storing or comparing.

### If You Actually Need Rounding

`DateTimeFormatter` does not replace business rounding rules. For time-of-day values and a requirement to round to the nearest millisecond, you must clearly define how to handle rounding that crosses a second or midnight boundary. Conceptually:

- `.1234` seconds rounded to the nearest millisecond becomes `.123`.
- `.1236` seconds rounds to `.124`.
- `.9996` seconds may need to carry over to the next second after rounding.

Do not simply format with `SSS` and call that "rounding"; formatting will not automatically turn `.1236` into `.124`. If the system needs rounding, define and test a dedicated rounding operation, including cases that carry over to the next second/day and the tie-breaking rule at the exact midpoint between two values.

## 4. Parsing Strings Also Affects Precision

When parsing a string with a pattern that only has three fractional digits, the resulting value only provides millisecond precision:

~~~java
DateTimeFormatter millis = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
LocalTime parsed = LocalTime.parse("12:34:56.123", millis);
System.out.println(parsed.getNano()); // 123000000
~~~

The string `.123` can represent the nanosecond value `123_000_000`; there is no data in the string to recover the subsequent digits of an original value like `123_987_654`. That is **information loss due to the input representation**, not Java discarding data that existed in another object.

Comparison:

| Operation | Source value | Result |
|---|---|---|
| Format with `SSS` | `12:34:56.123987654` | String `12:34:56.123`, source object unchanged |
| Parse string `.123` | `12:34:56.123` | New object with `getNano() == 123000000` |
| `truncatedTo(MILLIS)` | `12:34:56.123987654` | New object `12:34:56.123` |
| Round-trip through 3-digit format | `12:34:56.123987654` | Cannot recover the `987654` ns that were not output |

When exchanging data between services, explicitly choose the protocol's precision. ISO-8601 can represent fractional parts with varying numbers of digits; sender and receiver should agree on whether up to 3, 6, or 9 digits are allowed, whether normalization is applied, and whether all input data must be preserved verbatim.

### Fixed-Digit Formatting vs. ISO Formatting

`DateTimeFormatter.ISO_LOCAL_TIME` and corresponding ISO formatters are convenient choices when standard date-time formatting is needed. They typically output only as many fractional digits as necessary, not always 9 digits. The `SSSSSSSSS` pattern is appropriate when a fixed 9 digits are explicitly required; the string will include trailing zeros if needed to fill the width.

~~~java
LocalTime time = LocalTime.of(12, 34, 56, 120_000_000);
System.out.println(time.format(DateTimeFormatter.ISO_LOCAL_TIME));
System.out.println(time.format(DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS")));
~~~

Output:

~~~text
12:34:56.120
12:34:56.120000000
~~~

Both strings represent the same time, but follow different digit-count conventions. If the receiver treats string length as an indicator of precision, specify the protocol rule explicitly; do not leave the two sides to infer differently.

## 5. Impact When Converting to Epoch Milliseconds

For `Instant`, `toEpochMilli()` returns a number of milliseconds from the epoch. Precision finer than one millisecond is discarded:

~~~java
Instant event = Instant.parse("2024-01-01T00:00:00.123987654Z");
long millis = event.toEpochMilli();
Instant restored = Instant.ofEpochMilli(millis);
~~~

In this example, `event` has the fractional part `.123987654`, while a round-trip through epoch milliseconds only keeps `.123`:

~~~text
event = 2024-01-01T00:00:00.123987654Z
millis = 1704067200123
restored = 2024-01-01T00:00:00.123Z
~~~

Losing `987_654` nanoseconds beyond the millisecond part is a consequence of the storage unit. If the original data requires nanosecond precision, do not store only an epoch milliseconds number and expect to recover the lost digits.

Also be mindful of finite-range arithmetic conversions: converting a very distant `Instant` to `long` milliseconds or nanoseconds can exceed the representable range and throw `ArithmeticException`. Lower precision not only affects the fractional part, it can sometimes also affect the range of storable values.

## 6. Formatting in APIs and Databases

Choose precision by **contract**, not by guesswork:

- **Logs and event timestamps:** determine the clock source, actual required precision, and communication format. Outputting 9 digits does not guarantee the clock measures accurately to nanoseconds.
- **JSON APIs:** specify the ISO-8601 representation field, offset, and allowed fractional level; test 0-, 3-, 6-, and 9-digit strings if the protocol supports them.
- **Databases:** some timestamp types store to milliseconds or microseconds, while other types/engines support different precisions. Check the precision of the column type, driver, and parameter binding; do not assume every database preserves all nanoseconds of an `Instant`.
- **Comparing/keying events:** if one system rounds to milliseconds while the other keeps nanoseconds, two timestamps may no longer be equal after a round-trip. If comparison at a shared precision is needed, normalize both according to a documented rule.
- **Local date-times:** do not combine a fractional second with a default time zone to infer a timestamp if the required offset or zone is missing.

For example, if the system only stores milliseconds, decide upfront whether to **truncate**, **round**, or **reject data with higher precision**. These three policies produce different results; do not let the driver or string format implicitly decide the business policy.

## 7. Complete Java 17 Program

Save as **`FractionalSecondDemo.java`**:

~~~java
import java.time.Instant;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;

public class FractionalSecondDemo {
    public static void main(String[] args) {
        LocalTime time = LocalTime.of(12, 34, 56, 123_987_654);
        DateTimeFormatter millis = DateTimeFormatter.ofPattern("HH:mm:ss.SSS");
        DateTimeFormatter micros = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSS");
        DateTimeFormatter nanos = DateTimeFormatter.ofPattern("HH:mm:ss.SSSSSSSSS");

        System.out.println("stored nano = " + time.getNano());
        System.out.println("millis display = " + time.format(millis));
        System.out.println("micros display = " + time.format(micros));
        System.out.println("nanos display = " + time.format(nanos));
        System.out.println("original = " + time);
        System.out.println("truncated millis value = " +
                time.truncatedTo(ChronoUnit.MILLIS));
        LocalTime parsed = LocalTime.parse("12:34:56.123", millis);
        System.out.println("parsed nano = " + parsed.getNano());
        System.out.println("parsed value = " + parsed);

        Instant event = Instant.parse("2024-01-01T00:00:00.123987654Z");
        System.out.println("instant original = " + event);
        System.out.println("epoch millis = " + event.toEpochMilli());
        System.out.println("instant after millis roundtrip = " +
                Instant.ofEpochMilli(event.toEpochMilli()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac FractionalSecondDemo.java
java FractionalSecondDemo
~~~

Output verified with `javac --release 17`:

~~~text
stored nano = 123987654
millis display = 12:34:56.123
micros display = 12:34:56.123987
nanos display = 12:34:56.123987654
original = 12:34:56.123987654
truncated millis value = 12:34:56.123
parsed nano = 123000000
parsed value = 12:34:56.123
instant original = 2024-01-01T00:00:00.123987654Z
epoch millis = 1704067200123
instant after millis roundtrip = 2024-01-01T00:00:00.123Z
~~~

**How to read the output:**

1. The original object has `123_987_654` nanoseconds.
2. The `SSS` formatter outputs only `.123`; the 6- and 9-digit formatters output `.123987` and `.123987654`, respectively.
3. The original `time` variable still retains its full nanoseconds after formatting.
4. When parsing a string with only `.123`, the new object has `123_000_000` nanoseconds because the input carries no sub-millisecond part.
5. The `Instant → epoch milliseconds → Instant` round-trip loses the sub-millisecond part and cannot recover the exact original timestamp.

## 8. Common Mistakes

| Mistake | Why it is wrong | Correct approach |
|---|---|---|
| Thinking `SSS` rounds to milliseconds | Formatting only outputs three fractional digits | Use a dedicated rounding operation if business rules require it |
| Thinking short formatting modifies the object | `DateTimeFormatter` only produces a string | Use `truncatedTo(...)` when you want a truncated value |
| Thinking parsing `.123` can recover `.123987654` | The string does not contain the missing digits | If the protocol needs to preserve fractional parts, transmit them in full |
| Confusing `S` and `s` | One is fraction-of-second, the other is second-of-minute | Check the pattern letter table |
| Always outputting 9 digits even when the API only requires milliseconds | A longer string does not guarantee a more accurate source | Agree on precision by contract |
| Storing nanosecond `Instant` into a ms-precision column | Data loses precision on write/read | Verify column and driver precision |
| Looking only at `getNano()` to determine precision | It is the nanosecond component within the second, not proof of the real clock | Check the time source, precision, and contract |
| Comparing timestamps from different systems after one side truncated | The two sides may represent different granularities | Normalize to a common precision and document the rule |
| Assuming a fractional part is milliseconds based on 3 digits | Unit and format must be stated in the protocol | Define the pattern and unit explicitly |
| Assuming ISO formatters always output 9 digits | ISO formatters may use only as many digits as needed | Use a fixed pattern if the format requires a fixed length |

## 9. Self-Check

1. For a nanosecond value of `123_987_654`, what fractional part does the `SSS` pattern display? **`.123`**.
2. How many digits does `SSSSSS` display? **6**, for example `.123987`.
3. Does formatting with `SSS` modify the original object? **No**.
4. What `getNano()` value does parsing `12:34:56.123` with the millisecond formatter produce? **123000000**.
5. Does `getNano()` return total nanoseconds since the epoch? **No**, only nanoseconds within the current second.
6. Does a round-trip through epoch milliseconds preserve `.123987654`? **No**; the result only has `.123` in the example.
7. If you need to round rather than truncate fractional seconds, is using the `SSS` formatter enough? **No**, a dedicated rounding operation must be defined.
8. Why do 9 fractional digits not prove a clock has nanosecond accuracy? **The data type and string can hold 9 digits, while the clock source has lower resolution**.
9. If a database column has 3-digit precision and the application needs nanoseconds, what should you check? **Column type, driver, conversion rules, and round-trip capability**.
10. Where should truncation or rounding be decided? **In the data contract or tested business logic**, not implicitly left to the display pattern or driver.

**Key takeaway:** `S` is the fraction of a second; the number of `S` letters controls the granularity **displayed/parsed**. Short formatting does not alter the object itself, whereas parsing a string with fewer digits or converting to a lower-precision storage unit loses information. Distinguish **formatting, truncation, rounding, and storage precision**; choose clear rules to avoid incorrect timestamps or inconsistent comparisons.

### References

- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 17 — DateTimeFormatter pattern letters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Java SE 17 — LocalTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
