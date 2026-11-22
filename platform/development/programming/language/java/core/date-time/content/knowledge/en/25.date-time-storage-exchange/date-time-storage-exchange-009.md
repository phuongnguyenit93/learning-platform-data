# Column Precision and Nanosecond Loss During Read/Write

## 1. Java Retaining Nanoseconds Does Not Mean the Column Retains Them

Suppose an application has the value:

```text
2024-01-01T12:00:00.123456789Z
```

The part after the decimal point has nine digits, meaning it can distinguish down to nanoseconds. If a storage path only retains six fractional-second digits, it cannot represent every such value intact.

There are three common contract outcomes:

- Reject the input because its granularity exceeds storage capacity.
- Truncate to `.123456`.
- Round to `.123457`.

Reading it back and appending three `0`s to form `.123456000` does not recover the three lost digits `789`. That is simply a way of writing a new, less granular value.

Therefore, the question to answer is not just “Does Java have a nano field?” but rather: **to what precision does the entire write–store–read path preserve values, and by what rule does it handle the remainder?**

This lesson uses the term “fractional-second precision” to refer to the number of digits that can be stored. It differs from clock measurement accuracy: a type capable of storing nine digits does not prove that the hardware actually measures accurately to the nanosecond.

## 2. Fractional-Second Digits and Representation Steps

In many SQL temporal types, the parameter `p` denotes the number of fractional-second digits. The exact meaning and range of `p` must be checked against the DBMS, but the following table illustrates the mathematical relationship:

| Fractional-second digits | Corresponding smallest unit | Example fractional seconds after truncation |
| --- | --- | --- |
| `0` | Second | No fractional part |
| `3` | Millisecond, `10^-3` seconds | `.123` |
| `6` | Microsecond, `10^-6` seconds | `.123456` |
| `9` | Nanosecond, `10^-9` seconds | `.123456789` |

Not every database supports `p = 9`. For example, [PostgreSQL](https://www.postgresql.org/docs/current/datatype-datetime.html) describes its timestamp/time types as having microsecond resolution and allows a precision parameter from `0` to `6`.

A value does not need to use the maximum number of digits to be represented accurately. `.123` can be stored intact in a column allowing six digits as `.123000`. These two notations represent the same fractional second.

Conversely, `.123456789` does not land exactly on microsecond boundaries. Within Java's nanosecond range, the microsecond-alignment condition is:

```java
value.getNano() % 1_000 == 0
```

If `p` digits are allowed with `0 <= p <= 9` and the representation steps are uniform, the size of each step in nanoseconds is `10^(9-p)`. This explains the divisibility condition, not a guarantee that every DBMS uses that exact model or range of `p`.

## 3. Information Can Be Lost at Multiple Layers

The path of a value typically includes:

```text
Java value
    → conversion layer / ORM
    → JDBC driver and parameter binding
    → column type, precision, DBMS mode
    → JDBC driver on read
    → Java type after read
    → formatting / output data
```

If even one step discards the fractional seconds, a subsequent step with higher storage capacity cannot recover the information on its own.

| Point in the path | Example risk |
| --- | --- |
| Converting to epoch milliseconds | Loss of sub-millisecond fraction |
| Converting `LocalTime` through the `java.sql.Time` bridge | May drop the nanosecond part through legacy conversion methods |
| Column with only `p = 3` | Cannot store microseconds/nanoseconds that are not multiples of a millisecond intact |
| Binding a value with an unsuitable type | The driver may have to convert or reject it |
| Reading into `java.util.Date` | The representation type is millisecond-based |
| Formatting with only three fractional-second digits | The output string does not carry the sub-millisecond part |
| Serializer sending epoch numbers in milliseconds | The receiver only gets millisecond-level data |

Distinguish **value loss** from **hidden on display**. If a tool only prints three digits while the underlying value still has nanoseconds, the data may not be lost yet. You must read and compare the actual value; looking at a database administration UI is not enough to draw a conclusion.

Similarly, trailing `0`s may be omitted on display without losing data. `.123456` and `.123456000` are equal in fractional seconds.

## 4. java.sql.Timestamp Has Nanoseconds, but getTime() Only Returns Milliseconds

[java.sql.Timestamp](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Timestamp.html) stores the nanosecond part separately from its `java.util.Date`-based part. It has `getNanos()` and can convert from/to `Instant` while preserving nanoseconds within the appropriate representation range.

```java
Instant original = Instant.parse(
        "2024-01-01T12:00:00.123456789Z");

Timestamp timestamp = Timestamp.from(original);
Instant exact = timestamp.toInstant();
```

For this input, `exact.equals(original)` is `true`.

However, the following path carries only milliseconds:

```java
Instant reduced =
        Instant.ofEpochMilli(timestamp.getTime());
```

The result is `2024-01-01T12:00:00.123Z`. `getTime()` returned a whole number of milliseconds; the sub-millisecond part is not in that number.

Similarly, taking `timestamp.getTime()` to construct a new `java.util.Date` will not copy the separate nanosecond part of `Timestamp`. Do not assume “it's a `long`, so it must keep all detail”: the unit of the `long` determines its meaning and granularity.

The fact that `Timestamp` holds nanoseconds in memory also does not prove that a DBMS timestamp column holds nine digits. The two limits live at two different layers.

## 5. Three Policies for Values Exceeding Column Capacity

### 5.1. Reject

Appropriate when even a tiny time discrepancy must not be masked. For a column assumed to store up to microseconds, you can require `getNano() % 1000 == 0`.

If not satisfied, report that the input exceeds the supported precision. This policy preserves a strong contract: any accepted value must be representable intact at the declared level.

### 5.2. Truncate to Boundary

For `Instant`, [truncatedTo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html#truncatedTo(java.time.temporal.TemporalUnit)) supports truncating to appropriate units:

```java
Instant micros = original.truncatedTo(ChronoUnit.MICROS);
Instant millis = original.truncatedTo(ChronoUnit.MILLIS);
```

For example, `.123456789` becomes `.123456` when truncated to microseconds. The result is no later than the input. In `Instant`'s representation, truncating to a unit produces the preceding boundary on the timeline, even before the epoch; you should not manually take a signed epoch number and perform integer division without accounting for negative-number rules.

Normalizing with the same truncation twice must yield the same result as doing it once. This property ensures that passing through multiple layers adhering to the same contract does not keep altering the value.

### 5.3. Round

Rounding picks the nearest boundary. You must specify how exact half-steps are handled, such as rounding toward the future, rounding to even, or another rule.

In the Java example below, the rule is defined as:

**Round to the nearest microsecond; on an exact half-microsecond tie, choose the future boundary.**

The implementation adds `500` nanoseconds and then truncates down to the microsecond boundary. The method name `roundToMicrosTiesForward` intentionally states the rule clearly. This simulates an application policy and does not claim to match the rounding behavior of every DBMS.

Rounding can push a value into the next second or next day. `23:59:59.999999700` can become `00:00:00` of the following day. If the value is near the bounds of `Instant`, the intermediate addition can also overflow the range; it must not silently wrap around to another value.

### 5.4. Do Not Assume the DBMS Always Truncates

[The MySQL 8.4 documentation on fractional seconds](https://dev.mysql.com/doc/refman/8.4/en/fractional-seconds.html) states that the corresponding temporal types support up to six digits; when writing to a column with fewer digits, the default behavior is described as rounding. The `TIME_TRUNCATE_FRACTIONAL` mode can switch it to truncation.

The same documentation also states that the default precision when `fsp` is omitted is `0`. Therefore, a column created without explicitly specifying fractional seconds may not satisfy an expectation of preserving microseconds.

The takeaway is to check the **actual column type, configuration, and version in use**. Do not infer storage behavior from the Java type names `Instant` or `LocalDateTime`, or from an example on a different DBMS.

## 6. Complete Java 17+ Program

Save as `TemporalColumnPrecisionDemo.java`. The program uses only the standard library and does not connect to a database.

```java
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public class TemporalColumnPrecisionDemo {
    static Instant truncateToMicros(Instant value) {
        return Objects.requireNonNull(value).truncatedTo(ChronoUnit.MICROS);
    }

    static Instant roundToMicrosTiesForward(Instant value) {
        return Objects.requireNonNull(value)
                .plusNanos(500)
                .truncatedTo(ChronoUnit.MICROS);
    }

    static Instant requireMicroAligned(Instant value) {
        Objects.requireNonNull(value);
        if (value.getNano() % 1_000 != 0) {
            throw new IllegalArgumentException("More than 6 fractional digits");
        }
        return value;
    }

    public static void main(String[] args) {
        Instant original = Instant.parse("2024-01-01T12:00:00.123456789Z");
        Timestamp timestamp = Timestamp.from(original);
        Instant viaMillis = Instant.ofEpochMilli(timestamp.getTime());
        Instant micros = truncateToMicros(original);
        Instant rounded = roundToMicrosTiesForward(original);

        System.out.println("original = " + original);
        System.out.println("Timestamp nanos = " + timestamp.getNanos());
        System.out.println("Timestamp exact = "
                + original.equals(timestamp.toInstant()));
        System.out.println("via milliseconds = " + viaMillis);
        System.out.println("millisecond loss = "
                + !original.equals(viaMillis));
        System.out.println("truncate micros = " + micros);
        System.out.println("round micros = " + rounded);
        System.out.println("truncate loss nanos = "
                + Duration.between(micros, original).toNanos());
        System.out.println("round forward nanos = "
                + Duration.between(original, rounded).toNanos());

        System.out.println("truncate idempotent = "
                + micros.equals(truncateToMicros(micros)));
        Instant later = original.plusNanos(100);
        System.out.println("distinct originals = " + !original.equals(later));
        System.out.println("same stored bucket = "
                + truncateToMicros(original).equals(truncateToMicros(later)));

        Instant nearMidnight =
                Instant.parse("2024-01-01T23:59:59.999999700Z");
        System.out.println("round crosses date = "
                + roundToMicrosTiesForward(nearMidnight));

        Instant beforeEpoch =
                Instant.parse("1969-12-31T23:59:59.999999999Z");
        System.out.println("before epoch truncate = "
                + truncateToMicros(beforeEpoch));

        try {
            requireMicroAligned(original);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict = " + ex.getMessage());
        }
        System.out.println("strict aligned = " + requireMicroAligned(micros));
    }
}
```

Compile and run:

```shell
javac --release 17 TemporalColumnPrecisionDemo.java
java TemporalColumnPrecisionDemo
```

Stdout:

```text
original = 2024-01-01T12:00:00.123456789Z
Timestamp nanos = 123456789
Timestamp exact = true
via milliseconds = 2024-01-01T12:00:00.123Z
millisecond loss = true
truncate micros = 2024-01-01T12:00:00.123456Z
round micros = 2024-01-01T12:00:00.123457Z
truncate loss nanos = 789
round forward nanos = 211
truncate idempotent = true
distinct originals = true
same stored bucket = true
round crosses date = 2024-01-02T00:00:00Z
before epoch truncate = 1969-12-31T23:59:59.999999Z
strict = More than 6 fractional digits
strict aligned = 2024-01-01T12:00:00.123456Z
```

The program demonstrates the Java behaviors and simulated policies described above:

- `Timestamp.from`/`toInstant` preserves the nanoseconds of the sample input.
- Going through epoch milliseconds loses the sub-millisecond part.
- Truncating to microseconds loses `789` nanoseconds in the example.
- Rounding by the sample rule advances by `211` nanoseconds.
- Two distinct instants can fall into the same bucket after normalization.
- Rounding can cross a date boundary.
- The rejection policy does not silently discard data.

The program **does not prove how a real driver or column handles input**. That requires separate integration verification using the exact schema, driver, and deployment configuration.

## 7. Reading Back Must Be Compared Against the Storage Contract

Suppose the application has explicitly chosen a contract: every instant is truncated to microseconds before writing.

We have three values:

| Name | Meaning |
| --- | --- |
| `original` | Initial application value, which may contain nanoseconds |
| `expectedStored` | `original.truncatedTo(MICROS)` according to the policy |
| `readBack` | Actual value read back from the DB |

In this case, what needs to be verified is `expectedStored.equals(readBack)`. Comparing `original` directly with `readBack` will rightly fail if the policy already allows truncation.

However, you must not truncate the read-back value as well before comparing if doing so hides bugs. If the DB unexpectedly returns a value not at the declared precision, that also needs to be caught.

If the contract is to preserve the input intact, the comparison must be `original.equals(readBack)`. Do not change the verification to “allow a one-second difference” just to make the write–read look successful.

If the contract chooses rounding, you must compute `expectedStored` using the exact rule verified for the system, including exact half-steps and second rollovers. Do not use Java's truncation as the expectation for a rounding DBMS.

## 8. Designing a Meaningful Integration Verification

When a specific DBMS and driver are involved, a verification test needs to go through the entire real path:

1. Confirm the column's DDL and the actual precision created.
2. Write using the exact parameter-binding mechanism the application uses.
3. Read back using the Java type the application actually receives.
4. Compare the value against the chosen policy.
5. Observe the nanosecond part, second boundaries, and date boundaries if anything changes.

Test data should include:

| Fractional-second input or position | Verification purpose |
| --- | --- |
| `.123000000` | Already millisecond-aligned |
| `.123456000` | Already microsecond-aligned |
| `.123456789` | Has a sub-microsecond part |
| `.123456499` | Just below the microsecond rounding half-step |
| `.123456500` | Exact half-step |
| `.123456501` | Just above the microsecond rounding half-step |
| `23:59:59.999999700` | May round into a new date |
| Pre-epoch value | Detect incorrect sign handling |
| SQL `NULL` | Distinguish missing data from the epoch instant |

If a column or driver does not support a time range, out-of-range inputs should be clearly rejected. Do not confuse loss of fractional-second precision with year-range overflow or incorrect time-zone semantics.

An embedded database used in testing may have different precision from the production system. It is useful for testing parts of the code, but it cannot replace verifying the storage behavior of the target DBMS.

### 8.1. Choose the Right Temporal Semantics Before Choosing Precision

`LocalDateTime` has no offset or zone; `Instant` is an instant on the timeline. A write–read path with the wrong time zone can be off by hours, not just a few nanoseconds.

First determine whether the column represents an instant or a local date-time, how the driver maps that type, and how zones are configured. Only then verify fractional seconds. Increasing from `p = 3` to `p = 6` does not fix a broken time-zone mapping.

Nor should you assume every driver accepts `Instant` directly via `setObject`. Choose the mapping path documented by the driver and use that exact path in verification.

### 8.2. ORM and Migrations Need the Same Contract

Changing a Java field from a legacy type to `Instant` does not automatically ensure the existing column has the right precision. Annotations, test-generated DDL, and production migrations may differ.

You must inspect the schema after migrations, not just the entity declarations in code. If the driver or DBMS is upgraded, rounding and fractional-second reading behavior should also be re-verified when relevant changes occur.

## 9. Consequences for Querying, Ordering, and Concurrency

### 9.1. Equality Comparisons May Not Match Expectations

If stored values are normalized while query parameters still carry the original nanoseconds, equality comparisons may fail to match. How parameters are coerced depends on the system, so verify rather than guess.

You should apply the same normalization rule to business values used as temporal keys, or look up records by a stable identifier key if the instant is not truly an identifier.

### 9.2. Two Events Can Share the Same Time After Storage

The program creates two `Instant`s `100` nanoseconds apart that land on the same microsecond boundary after truncation. Thus, lower storage precision can erase the ordering distinction between them.

Do not use a timestamp as the sole guarantee that records have a total order or are unique. If stable pagination is needed when multiple records share the same time, you can add a stable identifier key as a secondary sort criterion in a defined order.

This does not recover the lost nanosecond order; it merely provides an unambiguous processing order for records that share the same stored boundary.

### 9.3. A Timestamp as a Version May Not Distinguish Updates

If two updates fall within the same representation step of the column, using time alone as a version marker may fail to distinguish them. When concurrency control is needed, a separately incremented version number usually expresses the contract more clearly than relying on the clock to always produce distinct values.

The specific choice depends on the application model, but “having many fractional-second digits” should not be treated as an automatic guarantee of uniqueness or causal ordering.

### 9.4. Interval Boundaries Also Need a Contract

Half-open intervals `[fromInclusive, toExclusive)` help avoid boundary overlaps, but they do not by themselves solve all precision loss. Truncating or rounding both endpoints can narrow or widen the interval relative to the original intent.

You must define the granularity at which both the data and the boundaries are interpreted. Do not mechanically normalize every parameter just because the column has `p = 6`; verify values just before, right at, and just after the desired boundary.

## 10. If You Truly Need to Keep Full Nanoseconds

Options depend on requirements:

- Use a column type and driver that support the required granularity, and verify the read-back value.
- If the target system only supports microseconds but the original data must be preserved, store the original time additionally in a declared exact representation.
- One custom representation is two components, `epochSecond` and `nanoOfSecond`; this requires range constraints and consistent comparison logic.

Do not rush to pack every instant into a single `long` “epoch nanos”. The range of `Instant` is wider than what can hold every nanosecond in a `long`. Multiplying `epochSecond * 1_000_000_000` can overflow unless you restrict the range and check arithmetic.

If using a string or multi-component numbers to preserve original data, you must design querying, sorting, constraints, and interoperability. That is a storage decision, not just changing the Java type of one field.

Nor should you use a local display string as a long-term exact representation. It can lose fractional seconds, omit the offset, or depend on locale.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Seeing Java has nanos and assuming the DB keeps them | Read-back differs from the original value | Inspect the entire storage path |
| Assuming every timestamp column has the same precision | Wrong assumptions across DBMSs | Check DDL and target system documentation |
| Using `getTime` or epoch milliseconds mid-path | Loses the sub-millisecond part | Keep a nanosecond-capable type when needed |
| Assuming the DB always truncates | Wrong expectations when the DB rounds | Verify the rule and configuration |
| Comparing only strings printed by a DB tool | Confusing display with stored value | Read the temporal type and check nanoseconds |
| Appending `0`s to “restore nanos” | Does not recover lost data | Preserve the original data before reducing granularity |
| Using an arbitrary tolerance to make tests pass | Masks mapping bugs | Compare against a specific normalization contract |
| Using a timestamp as a unique key | Collisions after quantization | Use an appropriate identifier |
| Changing only the entity without checking migrations | The actual column still has the old precision | Inspect the deployed schema |
| Changing precision to fix a time-zone offset bug | Fails to address the root cause | Check temporal semantics separately |

## 12. Self-Check and Practice

1. Run the program and explain each remaining digit after the epoch-millisecond path, the microsecond-truncation path, and the microsecond-rounding path.
2. Replace the input with `.123456000`. The sub-microsecond rejection policy must accept it, and truncation must leave the value unchanged.
3. Test an exact half-microsecond to verify whether the name `TiesForward` matches the implementation.
4. Test a value near the end of the day and confirm that rounding can change the date.
5. Test two events with different nanoseconds that land on the same stored boundary. Explain why nanosecond order cannot be inferred from a truncated timestamp.
6. Write a policy that accepts only milliseconds, with the corresponding alignment condition, and does not auto-truncate invalid input.
7. If a target DBMS is available, build an integration test using the boundary dataset above. Record the driver version, column type, `p`, and rounding/truncation mode.
8. Inspect your application's actual conversion path and JSON formatting to find any point that converts to epoch milliseconds.
9. Design read-back comparisons for two contracts: preserving input intact and truncating before write. The two comparisons must reflect the two different requirements.
10. Explain why a column with nanosecond precision still does not automatically guarantee an accurate clock, unique records, or causal ordering.

A temporal storage contract must clearly state the type semantics, the smallest unit, how remainders are handled, and how read-backs are verified. When these are explicitly specified, nanosecond loss stops being a mysterious discrepancy that surfaces only after the data has been saved.
