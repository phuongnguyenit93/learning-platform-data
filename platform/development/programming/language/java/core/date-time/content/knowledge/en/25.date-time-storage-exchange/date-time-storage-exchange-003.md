# Distinguishing Epoch Seconds from Epoch Milliseconds in Data Contracts

## 1. An integer does not carry a time unit on its own

Both of the following values can describe the same time region of an event, but they use different units:

```text
1792886400       : epoch seconds
1792886400123    : epoch milliseconds
```

If you send a field named only `timestamp` without declaring its unit, the receiver might pass seconds into an API expecting milliseconds. The result can still be a valid date, but it will fall near the year 1970 instead of the expected date. This kind of bug does not necessarily throw an exception.

For Java `Instant`, the epoch reference is `1970-01-01T00:00:00Z`. Positive values are after the epoch, and negative values are before it. The unit determines the distance measured from the epoch; the display time zone does not change the numeric value of the same instant.

An epoch number is not a day of the month, a local time, or a standalone duration. It is an encoding of **an instant in time relative to an agreed-upon epoch and unit**.

## 2. Choose the right API for the unit

| Data/API | Unit or meaning |
|---|---|
| `Instant.ofEpochSecond(value)` | Input is whole epoch seconds |
| `Instant.ofEpochMilli(value)` | Input is epoch milliseconds |
| `instant.getEpochSecond()` | The epoch seconds portion of the Instant |
| `instant.toEpochMilli()` | Epoch milliseconds representation, dropping precision finer than milliseconds |
| `Instant.ofEpochSecond(seconds, nanoAdjustment)` | Creates from seconds and a nanosecond adjustment |
| `Date.getTime()`, `new Date(long)` | Epoch milliseconds in legacy APIs |
| `Clock.millis()`, `System.currentTimeMillis()` | Epoch milliseconds from the corresponding time source |

`System.nanoTime()` is intended for measuring elapsed intervals within a process, not for producing epoch nanoseconds to send to another system. Do not divide it into seconds and treat it as a UTC date-time timestamp.

Variable names should reflect the unit, such as `createdAtEpochSeconds` or `createdAtEpochMillis`. In business logic, you can convert to `Instant` early so that unit-ambiguous `long` numbers are not passed across multiple layers.

When you need to keep a numeric representation across multiple API signatures, wrapper types such as `EpochSeconds` and `EpochMillis` help the compiler distinguish parameters. They do not replace validation of external data, but they make call sites clearer.

## 3. Loss of precision is not the same as a wrong unit conversion

Consider the instant:

```text
2026-10-25T00:00:00.123456789Z
```

Its components:

| Representation | Value | When reconstructed |
|---|---|---|
| Whole epoch seconds | `1792886400` | `2026-10-25T00:00:00Z` |
| Epoch milliseconds | `1792886400123` | `2026-10-25T00:00:00.123Z` |
| Seconds and nanoseconds | `1792886400`, `123456789` | Preserves the exact original instant |

If you store only whole seconds, you intentionally do not retain the sub-second fraction. If you store only milliseconds, you do not retain fractions smaller than a millisecond. That is a precision contract to agree upon, which is different from passing seconds to an API that expects milliseconds.

Do not write round-trip tests requiring exact equality against a nanosecond source if the storage format only guarantees milliseconds. Instead, define the precision-reduction policy explicitly and assert the corresponding result.

For an Instant that already has normalized epoch seconds and a nanosecond part in 0–999,999,999, the millisecond representation can be understood as:

```text
epochMillis = epochSeconds * 1000 + nanoOfSecond / 1_000_000
```

The formula must account for overflow and how negative values are represented. In regular application code, prefer `toEpochMilli()` rather than repeating the calculation everywhere.

## 4. Negative values expose integer division bugs

One millisecond before the epoch is:

```text
1969-12-31T23:59:59.999Z
```

`Instant` represents it with epoch second `-1` and nanosecond part `999000000`. Therefore:

```text
Instant.ofEpochMilli(-1).getEpochSecond() -> -1
```

However, Java integer division `-1 / 1000` truncates toward 0 and returns `0`, not `-1`. If you are converting a millisecond count to the seconds part the way Instant does, you must understand floor-toward-negative-infinity division, such as `Math.floorDiv(millis, 1000L)`.

Do not test only post-1970 data and conclude that division is always correct. For negative values not divisible by 1000, the two approaches differ. The simplest way to avoid implementing the rule incorrectly yourself is to construct `Instant.ofEpochMilli(millis)` and call `getEpochSecond()`.

When a contract uses decimal seconds such as `-0.001`, you also need to specify the decimal parser and how the whole seconds and fractional parts are split. Do not convert through `double` and assume all values retain exact precision like integers or `BigDecimal`.

## 5. Overflow can happen before assigning to long

Example:

```java
int epochSeconds = 2_000_000_000;
long wrong = epochSeconds * 1000;
```

Both operands are `int`, so the multiplication is performed in `int` and can overflow **before** the result is assigned to `long`. Using a `long` target variable cannot rescue an already-wrong result.

A clearer way to express it:

```java
long epochMillis = Math.multiplyExact((long) epochSeconds, 1000L);
```

The multiplication uses `long`; `multiplyExact` throws `ArithmeticException` if the result exceeds the `long` range. If you need to add a sub-second millisecond offset, `Math.addExact` serves a similar role.

Even `long` has limits. `Instant` has a wider time range than can be converted to a `long` epoch millisecond count at both ends; `toEpochMilli()` can throw `ArithmeticException` if the result cannot be represented.

Do not fix overflow by casting back to a smaller type or silently clamping the number. If the contract's range does not allow that value, report an error at the data-ingestion boundary.

## 6. Specify the unit explicitly in data contracts

An illustrative JSON representation:

```json
{
  "occurredAtEpochMillis": 1792886400123
}
```

The field name and documentation must agree that this is an integer number of milliseconds since the declared UTC epoch. Another style can use a seconds/nanoseconds pair:

```json
{
  "occurredAt": {
    "epochSeconds": 1792886400,
    "nanoOfSecond": 123456789
  }
}
```

You must specify the valid range of the fractional part and how it is validated, rather than simply sending two numbers with no rules. These JSON examples illustrate the contract; the specific serializer mapping must be configured and tested in the application.

The contract should answer:

- What are the epoch reference and unit?
- Are only integers allowed, or are decimals also accepted?
- Are sub-unit fractions truncated, rounded, or rejected?
- Are pre-epoch values accepted?
- What are the supported time range and numeric range?
- Is `0` a real epoch timestamp, or is there a separate "no data" state?

Do not use `0` as an implicit missing value if the epoch is a valid timestamp. Also do not change the unit of a published field from seconds to milliseconds while keeping the same name and expecting receivers to adapt; use a contract version or a clearly distinct new field.

### Do not guess by digit count

Modern-era second counts are typically three digits shorter than the corresponding millisecond counts, but that is not a reliable unit-detection mechanism. Historical data, `0`, negative numbers, or far-future timestamps have different lengths. A mistakenly multiplied number can also fall within the valid range of the target type.

You can use business-domain ranges to detect anomalies, but they do not replace an explicit unit. If the contract requires milliseconds and the sender sends seconds, prefer fixing or rejecting the data at the source rather than silently multiplying based on a heuristic threshold.

### JSON numbers also have cross-language interoperability limits

A receiver may parse JSON numbers using IEEE 754 binary64, such as JavaScript's standard `Number`. Not every Java `long` integer can be represented exactly there; the contiguous safe integer range is commonly considered to be from `-(2^53-1)` to `2^53-1`.

The epoch milliseconds in the example fall within that range, but do not assume that all epoch nanoseconds or all `long` values are safe when passed through the same JSON number path. If a larger range is needed, agree on numeric strings or a seconds/fraction structure with matching parsers on both sides. Do not add quotes to the data on only one side without updating the schema.

## 7. Complete runnable program

Save the following code to `EpochUnitContractDemo.java`. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.Instant;

public class EpochUnitContractDemo {
    record EpochSeconds(long value) {
        Instant toInstant() {
            return Instant.ofEpochSecond(value);
        }
    }

    record EpochMillis(long value) {
        Instant toInstant() {
            return Instant.ofEpochMilli(value);
        }
    }

    public static void main(String[] args) {
        Instant original = Instant.parse("2026-10-25T00:00:00.123456789Z");
        long seconds = original.getEpochSecond();
        long millis = original.toEpochMilli();

        System.out.println("original=" + original);
        System.out.println("epochSeconds=" + seconds);
        System.out.println("epochMillis=" + millis);
        System.out.println("fromSeconds="
                + new EpochSeconds(seconds).toInstant());
        System.out.println("fromMillis="
                + new EpochMillis(millis).toInstant());
        System.out.println("wrongUnit=" + Instant.ofEpochMilli(seconds));
        System.out.println("fullPrecision="
                + Instant.ofEpochSecond(seconds, original.getNano()));
        System.out.println("millisecondsMatchFormula="
                + (millis == Math.addExact(
                        Math.multiplyExact(seconds, 1000L),
                        original.getNano() / 1_000_000L)));

        long beforeEpochMillis = -1L;
        System.out.println("negativeInstant="
                + Instant.ofEpochMilli(beforeEpochMillis));
        System.out.println("naiveNegativeSeconds="
                + beforeEpochMillis / 1000L);
        System.out.println("floorNegativeSeconds="
                + Math.floorDiv(beforeEpochMillis, 1000L));
        System.out.println("apiNegativeSeconds="
                + Instant.ofEpochMilli(beforeEpochMillis).getEpochSecond());

        int largeSeconds = 2_000_000_000;
        long overflowedBeforeAssignment = largeSeconds * 1000;
        long correctMillis = Math.multiplyExact((long) largeSeconds, 1000L);
        System.out.println("intMultiply=" + overflowedBeforeAssignment);
        System.out.println("longMultiply=" + correctMillis);

        try {
            Math.multiplyExact(Long.MAX_VALUE, 1000L);
        } catch (ArithmeticException e) {
            System.out.println("overflow=ArithmeticException");
        }
    }
}
```

Compile and run:

```shell
javac EpochUnitContractDemo.java
java EpochUnitContractDemo
```

Expected output:

```text
original=2026-10-25T00:00:00.123456789Z
epochSeconds=1792886400
epochMillis=1792886400123
fromSeconds=2026-10-25T00:00:00Z
fromMillis=2026-10-25T00:00:00.123Z
wrongUnit=1970-01-21T18:01:26.400Z
fullPrecision=2026-10-25T00:00:00.123456789Z
millisecondsMatchFormula=true
negativeInstant=1969-12-31T23:59:59.999Z
naiveNegativeSeconds=0
floorNegativeSeconds=-1
apiNegativeSeconds=-1
intMultiply=-1454759936
longMultiply=2000000000000
overflow=ArithmeticException
```

`wrongUnit` intentionally passes epoch seconds into `ofEpochMilli` to demonstrate that a value with the wrong unit can still construct an `Instant` without throwing an error. Do not use that call in valid data-processing code.

The two records in the program encode the unit name at the type level. They allow writing a method that accepts `EpochMillis` separately from a method that accepts `EpochSeconds`, instead of seeing only an unannotated `long` parameter. These records do not yet enforce business-domain ranges: if a feature only accepts dates within a specific range, additional validation is needed.

The `overflow` line is a label printed by the program when `multiplyExact` detects overflow, not the full JDK message. Overflow in the earlier `int` multiplication does not throw an exception on its own, so a negative result is printed even though the inputs are positive.

## 8. Testing a real storage/exchange path

When putting a contract into an API or database, test both directions:

1. The sender converts from `Instant` to the right unit and precision.
2. The written/serialized data does not change numeric type or lose digits unexpectedly.
3. The receiver uses the matching API to read that unit.
4. The read-back value matches the instant at the declared level of precision.

Maintain separate test datasets for: epoch 0, positive timestamps with fractional parts, negative values near the epoch, business-domain boundaries, numbers exceeding the target type's capacity, and an intentionally wrong-unit value.

Do not directly compare an epoch-seconds value with an epoch-milliseconds value to check event ordering. Normalize to `Instant` or to the same unit first. Similarly, a sum like `timestamp + TTL` only makes sense when `TTL` is a duration in the same unit and addition is checked for overflow; using `Instant.plus(Duration)` can express this more clearly.

Changing the display time zone does not fix a unit mismatch. An instant that falls near 1970 because seconds were interpreted as milliseconds remains wrong whether printed in UTC, Vietnam, or any other zone.

## 9. Practice exercises

1. Call `Instant.ofEpochMilli(0)` and `Instant.ofEpochSecond(0)`. Both produce the epoch; explain why testing only with `0` does not catch unit mismatches.
2. Test `-1001` milliseconds: the epoch seconds part is `-2`, whereas Java division `/ 1000` returns `-1`. Compare this with `Math.floorDiv`.
3. Replace the source with an instant that has no fractional part. An epoch-seconds round trip can preserve it accurately; explain why that does not prove all `Instant` values pass through whole seconds without data loss.
4. Design the signature for a method that reads an expiration time from epoch milliseconds. Name the field/parameter or choose a wrapper type so the reader does not have to guess the unit.

References: [Instant — epoch APIs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html), [Math — floorDiv and Exact operations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html), and [RFC 8259, Section 6 — Numbers in JSON](https://www.rfc-editor.org/rfc/rfc8259#section-6).