# Creating `Instant` from Epoch Seconds, Epoch Milliseconds, and Nanosecond Fractions

`java.time.Instant` represents **a point on the Java time-line**, without carrying a time zone, local date-time, or fixed display format. When an API, database, or device sends a numeric timestamp, we often need to construct an `Instant` from **epoch seconds**, **epoch milliseconds**, or **seconds plus a nanosecond fraction**. Choosing the right unit and understanding normalization rules are essential to avoid shifting the point in time.

Lesson objectives:

- Understand the epoch reference point and how `Instant` stores seconds and nanoseconds.
- Use `Instant.ofEpochSecond(long)`, `ofEpochMilli(long)`, and `ofEpochSecond(long, long)` accurately.
- Explain how nanosecond values exceeding one second, negative numbers, and pre-epoch instants are handled.
- Read back `getEpochSecond()`, `getNano()`, and `toEpochMilli()`, and recognize precision loss.
- Distinguish UTC representation from local time when displaying values.

## 1. What Is the Epoch?

In Java's common epoch APIs, the starting point is:

```text
1970-01-01T00:00:00Z  =  Unix/Java epoch
epochSecond           =  0
epochMilli            =  0
```

`Z` denotes the UTC+00:00 offset. For an instant **after** the epoch, the count is positive; for an instant **before** the epoch, the count is negative. For example:

| Input data | Unit and meaning | Corresponding `Instant` |
| --- | --- | --- |
| `0` seconds | Exactly at the epoch | `1970-01-01T00:00:00Z` |
| `1` second | One second after the epoch | `1970-01-01T00:00:01Z` |
| `-1` second | One second before the epoch | `1969-12-31T23:59:59Z` |
| `1000` milliseconds | One second after the epoch | `1970-01-01T00:00:01Z` |
| `-1` millisecond | One millisecond before the epoch | `1969-12-31T23:59:59.999Z` |

**A numeric timestamp is only meaningful when its unit is known.** The value `1_700_000_000` in seconds represents a point in 2023; if it is mistaken for milliseconds, the result falls near the beginning of 1970. Do not guess the unit merely from the number of digits when designing long-lived interfaces: declare explicit schema names such as `createdAtEpochSeconds` or `createdAtEpochMillis`.

### Value Structure of `Instant`

An `Instant` essentially consists of two parts:

1. **`epochSecond`** (type `long`): whole Java seconds from `1970-01-01T00:00:00Z`.
2. **`nano`** (type `int`): the nanosecond fraction *within that second*, always in the range **0 to 999,999,999**.

For example, `2023-11-14T22:13:20.123456789Z` consists of `epochSecond = 1_700_000_000` and `nano = 123_456_789`. Nanosecond representation resolution **does not guarantee** that the system clock can measure time accurately to the nanosecond.

The Java Time-Scale treats each calendar day as 86,400 nominal seconds. UTC leap seconds are not kept as a separate "second 60" field in `Instant`; if you integrate a scientific or specialized time source that requires physical leap seconds, you must handle them according to that source's time-scale rules.

## 2. Creating from Epoch Seconds: `Instant.ofEpochSecond(long)`

Use this method when the input is known to be **the number of seconds since the epoch**, with no fractional part:

```java
import java.time.Instant;

Instant epoch = Instant.ofEpochSecond(0);
Instant oneSecondLater = Instant.ofEpochSecond(1);
Instant oneSecondEarlier = Instant.ofEpochSecond(-1);
Instant event = Instant.ofEpochSecond(1_700_000_000L);

System.out.println(epoch);            // 1970-01-01T00:00:00Z
System.out.println(oneSecondLater);   // 1970-01-01T00:00:01Z
System.out.println(oneSecondEarlier); // 1969-12-31T23:59:59Z
System.out.println(event);            // 2023-11-14T22:13:20Z
```

`Instant.ofEpochSecond(seconds)` is equivalent to creating an instant with `getEpochSecond() == seconds` and `getNano() == 0` (provided the seconds value is within the supported range of `Instant`).

Real-world second counts are typically large, so use `long`; the `L` suffix in the example emphasizes the `long` type. If the data arrives as a string, validate it before parsing it into a `long`, and handle exceptions when the value falls outside the supported range.

### Do Not Infer a Time Zone from Epoch Seconds

`Instant.ofEpochSecond(1_700_000_000L)` returns the exact same instant on every machine. `toString()` outputs the ISO UTC format ending with `Z`. If you want to display local time, you must **choose a zone**:

```java
Instant event = Instant.ofEpochSecond(1_700_000_000L);
System.out.println(event.atZone(
        java.time.ZoneId.of("Asia/Ho_Chi_Minh")));
// 2023-11-15T05:13:20+07:00[Asia/Ho_Chi_Minh]
```

The `Instant` value does not change; only the zoned date-time display changes. Never add `7 * 3600` to the timestamp to "convert to Vietnam time": doing so alters the actual point in time.

## 3. Creating from Epoch Milliseconds: `Instant.ofEpochMilli(long)`

**One millisecond = 1/1,000 second = 1,000,000 nanoseconds.**

Use `ofEpochMilli` for an integer representing **milliseconds since the epoch**, commonly seen in timestamp APIs, `System.currentTimeMillis()`, and `java.util.Date.getTime()`.

```java
Instant fromMillis = Instant.ofEpochMilli(1_700_000_000_000L);
Instant fromSeconds = Instant.ofEpochSecond(1_700_000_000L);

System.out.println(fromMillis);               // 2023-11-14T22:13:20Z
System.out.println(fromMillis.equals(fromSeconds)); // true
```

Milliseconds past a whole second:

```java
Instant milliseconds = Instant.ofEpochMilli(1_700_000_000_123L);
System.out.println(milliseconds);
// 2023-11-14T22:13:20.123Z
System.out.println(milliseconds.getNano()); // 123000000
```

If `epochMillis` data is sent by a component, store or declare the field **with an explicit unit**: for example `timestampMillis`, not just `timestamp`.

### Negative Pre-Epoch Values Matter

```java
Instant beforeEpoch = Instant.ofEpochMilli(-1);

System.out.println(beforeEpoch);                 // 1969-12-31T23:59:59.999Z
System.out.println(beforeEpoch.getEpochSecond()); // -1
System.out.println(beforeEpoch.getNano());        // 999000000
```

At first glance this may look surprising: `-1 ms` is represented as **-1 whole second + 999 ms within that second**, because `getNano()` is never negative. If you split milliseconds using naive integer division/remainder that truncates toward zero, you will produce wrong results for negative instants.

For example, `Instant.ofEpochMilli(-1001)` represents `1969-12-31T23:59:58.999Z`, with `epochSecond=-2` and `nano=999_000_000`.

## 4. Creating from Epoch Seconds and Nanosecond Fraction: `ofEpochSecond(long, long)`

The second overload:

```java
Instant.ofEpochSecond(long epochSecond, long nanoAdjustment)
```

Takes a whole-second count and a **nanosecond adjustment**. The second parameter is a `long` that can be positive, negative, or greater than 999,999,999; Java **normalizes** it into a valid whole second and nanosecond fraction.

```java
Instant precise = Instant.ofEpochSecond(
        1_700_000_000L, 123_456_789L);

System.out.println(precise);
// 2023-11-14T22:13:20.123456789Z
System.out.println(precise.getEpochSecond()); // 1700000000
System.out.println(precise.getNano());        // 123456789
```

For standard inputs, `nanoAdjustment` is typically in **0–999,999,999**. Examples:

| `epochSecond` | `nanoAdjustment` | Resulting value |
| ---: | ---: | --- |
| 10 | 0 | `1970-01-01T00:00:10Z` |
| 10 | 1 | `1970-01-01T00:00:10.000000001Z` |
| 10 | 500,000,000 | `1970-01-01T00:00:10.500Z` |
| 10 | 1,500,000,000 | `1970-01-01T00:00:11.500Z` |
| 10 | -1 | `1970-01-01T00:00:09.999999999Z` |
| -1 | 500,000,000 | `1969-12-31T23:59:59.500Z` |

### Nanosecond Normalization Is Not an Input Error

```java
Instant carry = Instant.ofEpochSecond(10, 1_500_000_000L);
Instant borrow = Instant.ofEpochSecond(10, -1);

System.out.println(carry);  // 1970-01-01T00:00:11.500Z
System.out.println(borrow); // 1970-01-01T00:00:09.999999999Z
```

`1_500_000_000` nanoseconds equals **1.5 seconds**, so 1 second is carried over and 500,000,000 nanoseconds remain. `-1` nanosecond borrows from the previous second, making the nanosecond part of that previous second 999,999,999.

You can think of the normalization rule in terms of floor division and a non-negative remainder:

```text
extraSeconds = floorDiv(nanoAdjustment, 1_000_000_000)
finalSeconds = epochSecond + extraSeconds
finalNanos   = floorMod(nanoAdjustment, 1_000_000_000)
```

This is an explanatory model; you do not need to implement it yourself instead of calling the API. For `nanoAdjustment=-1`, `floorDiv(-1, 1_000_000_000)=-1` and `floorMod(...) = 999_999_999`. Adding seconds or producing an `Instant` outside the valid range can throw an exception.

**Note:** `getNano()` always returns the normalized value (0–999,999,999); it does not echo the raw `nanoAdjustment` argument passed in. `Instant.ofEpochSecond(10, 1_000_000_000L)` and `Instant.ofEpochSecond(11)` are equal according to `equals()`.

## 5. Converting Back to Seconds, Milliseconds, and Nanoseconds

Once you have an `Instant`:

| Method | Return type | Precision / meaning |
| --- | --- | --- |
| `getEpochSecond()` | `long` | Whole seconds, may be negative |
| `getNano()` | `int` | Nanosecond fraction of the second, from 0 to 999,999,999 |
| `toEpochMilli()` | `long` | Whole milliseconds since the epoch, **discards sub-millisecond precision** |
| `toString()` | `String` | ISO-8601 UTC text representation, ending with `Z` |

```java
Instant value = Instant.ofEpochSecond(
        1_700_000_000L, 123_456_789);

long seconds = value.getEpochSecond(); // 1700000000
int nanos = value.getNano();           // 123456789
long millis = value.toEpochMilli();    // 1700000000123
```

`toEpochMilli()` cannot preserve the remaining `456_789` nanoseconds beyond 123 milliseconds. If you need to store full nanosecond precision, store **two fields** `(epochSecond, nano)`, or use standard ISO text formatting with a defined resolution.

### Precision Loss When Converting to Milliseconds

```java
Instant original = Instant.ofEpochSecond(5, 123_456_789);
Instant restored = Instant.ofEpochMilli(original.toEpochMilli());

System.out.println(original); // 1970-01-01T00:00:05.123456789Z
System.out.println(restored); // 1970-01-01T00:00:05.123Z
System.out.println(original.equals(restored)); // false
```

This happens because milliseconds hold only 3 fractional decimal digits, whereas nanoseconds hold up to 9. When exporting data from a database or API, choose the storage type and resolution based on actual requirements instead of assuming all timestamps are milliseconds.

### `toEpochMilli()` and Negative Timestamps with Fractional Parts

For the instant `1969-12-31T23:59:59.999999999Z` (one nanosecond before the epoch), `toEpochMilli()` returns **-1**, not 0: interpreted on the epoch timeline, the millisecond result falls in the unit **before** 0. Do not compute `getEpochSecond() * 1000 + getNano()/1_000_000` and assume it always has the same semantics as truncating total seconds toward zero; for negative inputs, you must define the exact rounding policy.

If you need to store a single integer of total nanoseconds since the epoch, multiplying `epochSecond * 1_000_000_000L + nano` can **overflow `long`** for many valid `Instant` values. Store a pair of integers or use `BigInteger` when the data range genuinely requires it; never let multiplication overflow silently.

## 6. Distinguishing Seconds, Millis, Micros, and Nanos When Receiving Data

| Timestamp unit | Common labels | Units per second | How to create `Instant` |
| --- | --- | ---: | --- |
| Seconds | `s`, `seconds` | 1 | `ofEpochSecond(seconds)` |
| Milliseconds | `ms`, `millis` | 1,000 | `ofEpochMilli(millis)` |
| Microseconds | `µs`, `micros` | 1,000,000 | Split into seconds + nanos |
| Nanoseconds | `ns`, `nanos` | 1,000,000,000 | Split into seconds + nanos |

For example, if a partner sends timestamps in **microseconds** since the epoch:

```java
long epochMicros = -1L;

long seconds = Math.floorDiv(epochMicros, 1_000_000L);
long microsWithinSecond = Math.floorMod(epochMicros, 1_000_000L);

Instant instant = Instant.ofEpochSecond(
        seconds, microsWithinSecond * 1_000L);

System.out.println(instant);
// 1969-12-31T23:59:59.999999Z
```

For negative numbers, `floorDiv`/`floorMod` ensure a non-negative nanosecond part. Similarly, when receiving a `long` storing **nanoseconds since epoch**:

```java
long epochNanos = -1L;
Instant instant = Instant.ofEpochSecond(
        Math.floorDiv(epochNanos, 1_000_000_000L),
        Math.floorMod(epochNanos, 1_000_000_000L));
```

A value of `-1` nanosecond produces `1969-12-31T23:59:59.999999999Z`. Note that a `long` representing total nanoseconds since the epoch only covers a few hundred years around 1970, which is much narrower than the range of `Instant`.

**Do not guess** whether an input number is microseconds or nanoseconds solely from its digit count: this is part of the data source's contract and must be confirmed via documentation, schema, and boundary tests.

## 7. Supported Range and Error Handling

`Instant` has a wide representation range (approximately one billion years before to one billion years after the modern era), but **not every `long` is a valid epoch second**. Creation methods can throw `DateTimeException` if the result is outside the `Instant` range; during certain large normalization or arithmetic operations, `ArithmeticException` can occur on overflow. `toEpochMilli()` can also throw `ArithmeticException` when the millisecond result exceeds the `long` range.

For example, a valid `Instant` may still fail to convert to `long` milliseconds:

```java
Instant farFuture = Instant.MAX;

try {
    long millis = farFuture.toEpochMilli();
    System.out.println(millis);
} catch (ArithmeticException ex) {
    System.out.println("out of long millisecond range");
}
```

The snippet above is an illustrative example meant to run inside a `main` method or a method with `import java.time.Instant`. Do not "fix" overflows by casting or truncating digits: doing so alters the point in time. Define your business domain's valid date range and validate inputs before storing them.

### `int`, `long`, and JSON Numbers

- Modern epoch milliseconds exceed the `int` limit, so always use `long`.
- JavaScript/JSON clients using floating-point numbers can lose integer precision beyond **2^53 - 1**. Modern epoch nanosecond timestamps in particular far exceed this limit; agree on transmitting them as a `string`, a `seconds + nanos` pair, or an appropriate timestamp format.
- If your system stores timestamps in milliseconds while clients send nanoseconds, choose an explicit **rounding or truncation policy** and document it, rather than implicitly assuming both sides use the same unit.

## 8. Standalone Java 17+ Program

Create the file **`InstantEpochDemo.java`**:

```java
import java.time.Instant;
import java.time.ZoneId;

public class InstantEpochDemo {
    public static void main(String[] args) {
        Instant epoch = Instant.ofEpochSecond(0);
        Instant fromSeconds = Instant.ofEpochSecond(1_700_000_000L);
        Instant fromMillis = Instant.ofEpochMilli(1_700_000_000_000L);
        Instant precise = Instant.ofEpochSecond(
                1_700_000_000L, 123_456_789L);

        System.out.println("epoch = " + epoch);
        System.out.println("seconds = " + fromSeconds);
        System.out.println("millis = " + fromMillis);
        System.out.println("seconds match millis = "
                + fromSeconds.equals(fromMillis));
        System.out.println("precise = " + precise);
        System.out.println("precise seconds = " + precise.getEpochSecond());
        System.out.println("precise nanos = " + precise.getNano());
        System.out.println("precise epoch millis = " + precise.toEpochMilli());

        Instant carry = Instant.ofEpochSecond(10, 1_500_000_000L);
        Instant borrow = Instant.ofEpochSecond(10, -1L);
        System.out.println("carry = " + carry);
        System.out.println("borrow = " + borrow);

        Instant minusOneMilli = Instant.ofEpochMilli(-1);
        System.out.println("minus one millis = " + minusOneMilli);
        System.out.println("minus one second part = "
                + minusOneMilli.getEpochSecond());
        System.out.println("minus one nano part = "
                + minusOneMilli.getNano());

        Instant source = Instant.ofEpochSecond(5, 123_456_789);
        Instant roundedMillis = Instant.ofEpochMilli(source.toEpochMilli());
        System.out.println("original nanos = " + source);
        System.out.println("restored from millis = " + roundedMillis);
        System.out.println("exact round trip = "
                + source.equals(roundedMillis));

        System.out.println("Vietnam display = "
                + fromSeconds.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));
    }
}
```

Compile and run:

```bash
javac InstantEpochDemo.java
java InstantEpochDemo
```

Expected output:

```text
epoch = 1970-01-01T00:00:00Z
seconds = 2023-11-14T22:13:20Z
millis = 2023-11-14T22:13:20Z
seconds match millis = true
precise = 2023-11-14T22:13:20.123456789Z
precise seconds = 1700000000
precise nanos = 123456789
precise epoch millis = 1700000000123
carry = 1970-01-01T00:00:11.500Z
borrow = 1970-01-01T00:00:09.999999999Z
minus one millis = 1969-12-31T23:59:59.999Z
minus one second part = -1
minus one nano part = 999000000
original nanos = 1970-01-01T00:00:05.123456789Z
restored from millis = 1970-01-01T00:00:05.123Z
exact round trip = false
Vietnam display = 2023-11-15T05:13:20+07:00[Asia/Ho_Chi_Minh]
```

This program does not use the current system clock or default time zone. All values are constants, so the output is deterministic on JDK 17+ with time-zone rules containing `Asia/Ho_Chi_Minh` for 2023.

## 9. Comparing with Familiar Timestamp Sources

### `System.currentTimeMillis()`

```java
long nowMillis = System.currentTimeMillis();
Instant instant = Instant.ofEpochMilli(nowMillis);
```

This converts the **millisecond count reported by the system clock** into an `Instant`. The returned value is not guaranteed to have true millisecond accuracy on all platforms, and the system clock can be adjusted. If you only need the current instant using the modern API, use `Instant.now()` or `Instant.now(clock)`.

### `java.util.Date`

```java
java.util.Date legacy = new java.util.Date(1_700_000_000_123L);
Instant instant = legacy.toInstant();
Instant same = Instant.ofEpochMilli(legacy.getTime());

System.out.println(instant.equals(same)); // true
```

`Date.getTime()` is in milliseconds; converting to `Instant` **does not invent nanosecond precision that did not exist** in the `Date` value.

### `LocalDateTime` Is a Different Quantity

`LocalDateTime` stores a local date-time **without an offset**. Therefore, you cannot compute an exact "epoch seconds" value from a `LocalDateTime` without knowing the event's offset or zone. For example:

```java
Instant instant = Instant.ofEpochSecond(1_700_000_000L);
LocalDateTime vietnamTime = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDateTime();
```

To go in the reverse direction, you must provide a valid offset/zone for that date-time; if the zone observes DST, you must also handle non-existent or ambiguous local times. **Never assume an epoch timestamp is local time**.

## 10. Common Mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Calling `ofEpochSecond(epochMillis)` | Timestamp shifts by many years or goes out of range | Use `ofEpochMilli` when the source is in milliseconds |
| Calling `ofEpochMilli(epochSeconds)` | Instant is pulled back close to 1970 | Use `ofEpochSecond` when the source is in seconds |
| Passing `123` as nano adjustment to represent 123 ms | Creates only **123 nanoseconds** | 123 ms = `123_000_000` nanos |
| Assuming nano adjustment must be in 0–999,999,999 | Ignores normalization rules | `ofEpochSecond` supports negative adjustments or values over 1 billion nanos |
| Assuming `getNano()` can be negative before the epoch | Wrong value-storage model | `getNano()` is always 0–999,999,999 |
| Splitting negative epoch values with wrong rounding | Off by 1 second or 1 ms near the epoch | Use `ofEpochMilli`, `floorDiv`/`floorMod` |
| Converting nanos to `long` millis and expecting lossless storage | Sub-millisecond precision is lost | Store a `seconds + nanos` pair if round-trip fidelity is required |
| Multiplying `epochSecond * 1_000_000_000L` unconditionally | Can overflow `long` | Check bounds or use `BigInteger` |
| Assuming `Instant` carries a time zone | Incorrect local date/time display | Use `atZone(ZoneId)` when displaying |
| Using a partner's numeric timestamp without checking its unit | Widespread data corruption | Explicitly define s/ms/µs/ns in schemas and tests |
| Assuming `Instant.now()` is always nanosecond-accurate | Confuses storage resolution with clock quality | Check the actual time source and clock precision |

## 11. Self-Check Exercises

**1.** Do these two calls point to the same instant?

```java
Instant.ofEpochSecond(1_700_000_000L)
Instant.ofEpochMilli(1_700_000_000_000L)
```

→ **Yes, the same instant**, because 1 second = 1,000 milliseconds.

**2.** What are `epochSecond` and `nano` for `Instant.ofEpochSecond(10, -1)`?

→ `epochSecond = 9`, `nano = 999_999_999`.

**3.** Does `Instant.ofEpochMilli(-1)` have `getEpochSecond() == 0`?

→ **No**. Its value is `-1`, and `getNano() = 999_000_000`; the total value equals minus one millisecond.

**4.** Why can't `Instant.ofEpochSecond(5, 123_456_789)` round-trip intact through `toEpochMilli()`?

→ The `456_789` nanoseconds beyond millisecond resolution are discarded; you need to keep the seconds and nanoseconds pair to avoid losing information.

**5.** Can you call `LocalDateTime.of(...)` and get epoch seconds without an offset?

→ No, an absolute instant cannot be determined without an offset or zone. You must specify the proper time-zone context.

**6.** If an API sends timestamps in microseconds, should you pass that raw value directly to `ofEpochMilli`?

→ No. You must convert to the proper unit, for example splitting into `floorDiv(micros, 1_000_000)` seconds and `floorMod(micros, 1_000_000) * 1_000` nanoseconds.

### References

- [Oracle Java SE 21 — `Instant`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): `ofEpochSecond`, `ofEpochMilli`, `getEpochSecond`, `getNano`, `toEpochMilli`, and supported range.
- [Oracle Java SE 21 — `ZoneId`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): representing an instant in a time zone.
- [Oracle Java SE 21 — `Date`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html): interoperability between legacy `Date` and `Instant`.

**Key takeaway:** Epoch seconds count in **seconds**, epoch milliseconds count in **milliseconds**, and the `ofEpochSecond(seconds, nanoAdjustment)` overload represents **nanosecond fractions** accurately, including normalizing negative values or values exceeding one second. When converting to milliseconds, sub-millisecond data is lost; when displaying local time, you must choose a time zone explicitly.
