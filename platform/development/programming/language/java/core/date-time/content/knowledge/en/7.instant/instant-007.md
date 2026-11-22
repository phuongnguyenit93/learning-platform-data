# Instant — Nanosecond Precision and Data Loss When Converting to Milliseconds

## 1. The Problem to Solve

`java.time.Instant` represents **an instant on the timeline** with a resolution of up to **1 nanosecond** (ns, 10⁻⁹ seconds). Meanwhile, `toEpochMilli()`, `java.util.Date`, and many protocols or database columns represent instants only down to **milliseconds** (ms, 10⁻³ seconds). Because `1 ms = 1,000,000 ns`, reducing resolution from nanoseconds to milliseconds cannot preserve all original information.

Visual example:

~~~text
Original Instant:      1970-01-01T00:00:01.234567890Z
Instant.toEpochMilli:  1234
Restored from millis:  1970-01-01T00:00:01.234Z
Lost portion:          567890 nanoseconds
~~~

This lesson helps you clearly identify **which values are preserved**, **which values are lost**, and **the rules for handling instants before 1970**. This is an important distinction between Java's **representation** resolution and the **actual** precision of clocks, protocols, and databases.

## 2. The Second and Nanosecond Model of Instant

An `Instant` conceptually stores two components:

| Property | Type | Meaning |
|---|---|---|
| `getEpochSecond()` | `long` | Whole seconds from the `1970-01-01T00:00:00Z` epoch, can be negative |
| `getNano()` | `int` | Nanosecond fraction within the second, always from `0` to `999_999_999` |

From the epoch, each second has 1,000,000,000 nanoseconds. For example:

~~~java
Instant value = Instant.ofEpochSecond(1, 234_567_890);
System.out.println(value);
System.out.println(value.getEpochSecond());
System.out.println(value.getNano());
~~~

Stdout:

~~~text
1970-01-01T00:00:01.234567890Z
1
234567890
~~~

`getNano()` is the nanoseconds **within a second**, not the total nanoseconds from the epoch. `toEpochMilli()` is the number of milliseconds **measured from the epoch**, which can lose sub-millisecond nanoseconds.

Some units to remember:

| Unit | Nanoseconds |
|---|---:|
| 1 second | 1,000,000,000 |
| 1 millisecond | 1,000,000 |
| 1 microsecond | 1,000 |
| 1 nanosecond | 1 |

Do not pass milliseconds directly into the nanosecond parameter of `ofEpochSecond(seconds, nanoAdjustment)`. For example, `123 ms` corresponds to `123_000_000 ns`, not `123 ns`.

### 2.1. Epoch and Time Zone

`Instant.EPOCH` is the instant `1970-01-01T00:00:00Z`, where the letter `Z` denotes a UTC offset of 0. `Instant` does not contain a regional time zone or local time. `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` only converts the same instant to a representation in Vietnam time; unless passed through a precision-reducing API, nanoseconds remain preserved.

`Instant.ofEpochSecond(1)` means one **second** after the epoch, whereas `Instant.ofEpochMilli(1)` is one **millisecond** after the epoch. Confusing the units will create a timestamp that is off by a factor of 1,000.

## 3. Creating an Instant While Preserving Nanoseconds

~~~java
Instant epoch = Instant.EPOCH;
Instant secondOnly = Instant.ofEpochSecond(1);
Instant withNanos = Instant.ofEpochSecond(1, 234_567_890);
Instant fromMillis = Instant.ofEpochMilli(1_234);
Instant parsed = Instant.parse("2024-02-29T12:34:56.123456789Z");
~~~

The results:

- `withNanos` is `1970-01-01T00:00:01.234567890Z`.
- `fromMillis` is `1970-01-01T00:00:01.234Z`; it cannot retain the `567890 ns` beyond milliseconds.
- `parsed` preserves the nanosecond fraction `123456789` from the ISO string containing all nine digits.

`Instant.ofEpochSecond(long seconds, long nanoAdjustment)` can accept nanosecond counts greater than one billion or negative values and **normalize** them:

~~~java
Instant normalized = Instant.ofEpochSecond(1, 1_234_567_890);
System.out.println(normalized);
~~~

Stdout:

~~~text
1970-01-01T00:00:02.234567890Z
~~~

Because 1,234,567,890 nanoseconds = 1 second and 234,567,890 nanoseconds. The result of `getNano()` always lies in `0..999999999`.

For an instant one nanosecond before the epoch:

~~~java
Instant before = Instant.ofEpochSecond(0, -1);
System.out.println(before);
System.out.println(before.getEpochSecond());
System.out.println(before.getNano());
~~~

Stdout:

~~~text
1969-12-31T23:59:59.999999999Z
-1
999999999
~~~

**Important:** Java represents minus one nanosecond as **second -1 plus 999,999,999 nanoseconds**, rather than storing a negative nanosecond field.

### 3.1. Resolution Is Not Actual Measurement Accuracy

`Instant.now()` returns an instant from the system clock. Although the result has a nanosecond field, the actual resolution and error of the clock depend on the JVM, operating system, and time source. You cannot claim "1 ns measurement accuracy" just because the object prints nine fractional digits.

You can use `Clock.fixed(...)` in tests:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2024-02-29T12:34:56.123456789Z"),
        ZoneOffset.UTC);
Instant stable = Instant.now(fixed);
~~~

`stable` always equals the specified instant. This approach helps keep tests independent of the real clock.

## 4. Converting to Milliseconds: How Are Nanoseconds Discarded?

~~~java
Instant source = Instant.ofEpochSecond(1, 234_567_890);
long millis = source.toEpochMilli();
Instant restored = Instant.ofEpochMilli(millis);
~~~

Result: `millis == 1234`, `restored == 1970-01-01T00:00:01.234Z`.

Calculation:

~~~text
Whole seconds:        1 * 1000 = 1000 ms
234567890 ns in s:                234 ms + 567890 ns remainder
Result epochMillis:   1000 + 234 = 1234 ms
Lost nanos:           567890 ns
~~~

`toEpochMilli()` **does not round to the nearest millisecond**. `1970-01-01T00:00:01.234999999Z` also converts to `1234` ms, not `1235` ms.

Let `s = getEpochSecond()` and `n = getNano()`. Within the range where the result fits in a `long`:

~~~text
epochMillis = s * 1000 + floor(n / 1000000)
~~~

Since `n` is non-negative, integer division `n / 1_000_000` yields the same result as `floor`. However, when manually converting a **signed total nanosecond count** to milliseconds, you must pay special attention to dividing negative numbers before the epoch.

### 4.1. Condition for Exact Preservation

~~~java
boolean noSubMillis =
        source.getNano() % 1_000_000 == 0;
~~~

If `noSubMillis` is true, and `toEpochMilli()` does not overflow, the round-trip `Instant.ofEpochMilli(source.toEpochMilli())` preserves `source`. If false, the nanosecond portion not divisible by one million **cannot be represented exactly** as a whole number of milliseconds.

The difference between the original instant and the reconstructed instant can range from **0 to 999,999 ns**. It is impossible to recover the remainder from a stored millisecond count alone.

## 5. Pre-Unix Epoch Trap: Minus One Nanosecond Becomes Minus One Millisecond

The instant **1 ns before** `1970-01-01T00:00:00Z`:

~~~java
Instant negative = Instant.parse(
        "1969-12-31T23:59:59.999999999Z");

System.out.println(negative.toEpochMilli());
System.out.println(Instant.ofEpochMilli(
        negative.toEpochMilli()));
~~~

Stdout:

~~~text
-1
1969-12-31T23:59:59.999Z
~~~

Why does `-1 ns` convert to `-1 ms`?

~~~text
Time relative to epoch = -0.000001 milliseconds
Largest millisecond multiple not exceeding original instant = -1 ms
~~~

`toEpochMilli()` follows **floor rounding along the timeline**. It does not "truncate toward zero" like Java's integer division.

| Source value relative to epoch | `toEpochMilli()` | Restored relative to epoch |
|---|---:|---|
| +1.234567890 seconds | +1234 | +1.234 seconds |
| +0.000000001 seconds | 0 | 0 seconds |
| -0.000000001 seconds | -1 | -0.001 seconds |
| -0.001000000 seconds | -1 | -0.001 seconds |

If you compute `signedEpochNanos / 1_000_000` manually in Java, `-1 / 1_000_000` evaluates to `0` (truncated toward 0), which **differs from `toEpochMilli() == -1`**. If you need to divide negative integers using floor semantics, consider `Math.floorDiv` and check for overflow, or prefer calling the standard method directly.

For `negative` above, `getEpochSecond() == -1` and `getNano() == 999999999`. This exact model guarantees that the formula `s * 1000 + n / 1000000` produces -1 ms.

## 6. Java 17+ Program Reproducing Both Positive and Negative Cases

Save as **`InstantPrecisionDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

public class InstantPrecisionDemo {
    public static void main(String[] args) {
        Instant precise = Instant.ofEpochSecond(1, 234_567_890);
        long millis = precise.toEpochMilli();
        Instant restored = Instant.ofEpochMilli(millis);

        System.out.println("Source: " + precise);
        System.out.println("Epoch millis: " + millis);
        System.out.println("Restored: " + restored);
        System.out.println("Lost nanos: "
                + Duration.between(restored, precise).toNanos());
        System.out.println("Equal: " + precise.equals(restored));
        System.out.println("Truncated: "
                + precise.truncatedTo(ChronoUnit.MILLIS));

        Instant negative = Instant.parse(
                "1969-12-31T23:59:59.999999999Z");
        long negativeMillis = negative.toEpochMilli();
        Instant negativeRestored =
                Instant.ofEpochMilli(negativeMillis);

        System.out.println("Negative source: " + negative);
        System.out.println("Negative millis: " + negativeMillis);
        System.out.println("Negative restored: " + negativeRestored);
        System.out.println("Negative lost nanos: "
                + Duration.between(
                        negativeRestored, negative).toNanos());

        System.out.println("Through Date: "
                + Date.from(precise).toInstant());
    }
}
~~~

Compile and run:

~~~bash
javac InstantPrecisionDemo.java
java InstantPrecisionDemo
~~~

Stdout:

~~~text
Source: 1970-01-01T00:00:01.234567890Z
Epoch millis: 1234
Restored: 1970-01-01T00:00:01.234Z
Lost nanos: 567890
Equal: false
Truncated: 1970-01-01T00:00:01.234Z
Negative source: 1969-12-31T23:59:59.999999999Z
Negative millis: -1
Negative restored: 1969-12-31T23:59:59.999Z
Negative lost nanos: 999999
Through Date: 1970-01-01T00:00:01.234Z
~~~

Result explanation:

1. The initial positive `Instant` has 234,567,890 nanoseconds; converting to milliseconds keeps only `234,000,000` nanoseconds, losing `567,890` nanoseconds.
2. `truncatedTo(MILLIS)` produces the same value in this case: the method retains only points spaced 1 ms apart.
3. The pre-epoch instant of minus one nanosecond converts to minus one millisecond; the difference between the original and restored instant is `999,999` nanoseconds.
4. `Date.from(precise).toInstant()` also retains only milliseconds, because `java.util.Date` represents time in epoch milliseconds.

## 7. truncatedTo(MILLIS) and Other Resolutions

`Instant.truncatedTo(ChronoUnit.MILLIS)` truncates the nanosecond fraction below one millisecond; it **does not round to the nearest value**.

~~~java
Instant input = Instant.parse(
        "2024-02-29T12:34:56.123456789Z");
Instant micros = input.truncatedTo(ChronoUnit.MICROS);
Instant millis = input.truncatedTo(ChronoUnit.MILLIS);
Instant seconds = input.truncatedTo(ChronoUnit.SECONDS);
~~~

Result:

~~~text
micros  = 2024-02-29T12:34:56.123456Z
millis  = 2024-02-29T12:34:56.123Z
seconds = 2024-02-29T12:34:56Z
~~~

| Target resolution | Representable nanosecond multiple | Lost fraction |
|---|---:|---|
| `NANOS` | 1 | None |
| `MICROS` | 1,000 | Sub-microsecond |
| `MILLIS` | 1,000,000 | Sub-millisecond |
| `SECONDS` | 1,000,000,000 | Sub-second |

`truncatedTo(MILLIS)` before the epoch also places the value at the lower millisecond boundary within that second. The case of minus one nanosecond becoming minus one millisecond is a typical example.

A **round-to-nearest**, **half-up**, or **half-even** policy requires a different rule and can produce different results. Do not document `toEpochMilli()` as a round-to-nearest method.

## 8. Two Ways to Round-Trip

**Lossless approach: seconds + nanos pair**

~~~java
Instant original = Instant.parse(
        "2024-02-29T12:34:56.123456789Z");

long seconds = original.getEpochSecond();
int nanos = original.getNano();

Instant exact = Instant.ofEpochSecond(seconds, nanos);
System.out.println(exact.equals(original)); // true
~~~

**Potentially lossy approach: a single millisecond integer**

~~~java
Instant approximate =
        Instant.ofEpochMilli(original.toEpochMilli());
System.out.println(approximate.equals(original)); // false
~~~

In both approaches, the instants may still fall within the same second, but `equals` compares all nanoseconds. Equivalence at the millisecond level does not mean two `Instant` objects are equal.

To demonstrate when a millisecond round-trip is exact:

~~~java
Instant millisecondAligned = Instant.parse(
        "2024-02-29T12:34:56.123000000Z");

Instant rebuilt = Instant.ofEpochMilli(
        millisecondAligned.toEpochMilli());

System.out.println(rebuilt.equals(millisecondAligned)); // true
~~~

The deciding condition is that the nanosecond part is divisible by 1 million. If the backend has already dropped the last six digits, the frontend cannot "guess" to reconstruct the old nanosecond timestamp.

### 8.1. Why Not Store epochNanos in a long for All Dates?

~~~java
// Can overflow long when far from the epoch:
long epochNanos = instant.getEpochSecond() * 1_000_000_000L
        + instant.getNano();
~~~

A `long` ranges around ±9.22×10¹⁸, which only suffices for total nanoseconds from the epoch spanning roughly **292 years** in each direction. `Instant`'s range is much wider because it stores seconds and nanoseconds separately. If you need an absolute epochNanos number for very distant dates, you must use `BigInteger` or a storage format with an equivalent range; do not cast and accept overflowed values.

## 9. Date, JDBC, JSON, and Storage Systems

`java.util.Date` stores milliseconds since the epoch; passing through `Date` loses sub-millisecond data:

~~~java
Instant nanos = Instant.parse(
        "2024-02-29T12:34:56.123456789Z");
Date legacy = Date.from(nanos);
Instant back = legacy.toInstant();
// back = 2024-02-29T12:34:56.123Z
~~~

`java.sql.Timestamp` supports a nanosecond field, but when writing to a database, behavior also depends on column precision, the JDBC driver, the ORM, and system configuration. A timestamp column might support only 3 or 6 fractional digits; some systems round while others truncate, so you cannot assume the behavior from the SQL type name alone.

| Type or path | Ability to preserve nanoseconds |
|---|---|
| `Instant` directly | Yes, down to 1 ns |
| `Instant → epochMillis` | Accurate only to 1 ms |
| `Instant → java.util.Date` | Accurate only to 1 ms |
| `Instant → seconds + nanos` | Yes, if both fields remain intact |
| `Instant → ISO string with full fraction` | Yes, if serializer/parser preserve precision |
| `Instant → database column` | Depends on DB, column precision, driver, mapping |

**To know whether nanoseconds are actually preserved, a round-trip check is mandatory**:

~~~text
Original Instant
  → serialize / JDBC binding
  → transport and storage
  → parse / JDBC read
  → Read-back Instant
  → compare equals(), getNano()
~~~

If the original is `.123456789` and the final data has only `.123456`, at least three nanosecond digits were lost. If the final data has only `.123`, six digits were lost. Do not assume all databases truncate: some will round to a different value. The policy must be verified on the deployed system.

## 10. Data Contracts When High Precision Is Needed

### 10.1. Accepting Milliseconds

If requirements only need millisecond precision, you can pass an integer with a field name that indicates the unit:

~~~json
{
  "epochMillis": 1234
}
~~~

The receiver uses `Instant.ofEpochMilli(1234)`. The contract should explicitly document potential data loss below 1 ms.

Avoid ambiguous names like `timestamp: 1234` without specifying whether it is seconds, milliseconds, microseconds, or nanoseconds. The same number under different units represents vastly different points in time.

### 10.2. Preserving Nanoseconds with ISO Text

~~~json
{
  "occurredAt": "2024-02-29T12:34:56.123456789Z"
}
~~~

The receiver uses `Instant.parse(...)`. The string can hold up to nine fractional second digits, provided intermediate serializers, parsers, and databases also preserve full precision. `Instant.toString()` may output 3, 6, or 9 digits as needed; omitting trailing zeros does not mean data was lost.

### 10.3. Preserving Nanoseconds with Two Fields

~~~json
{
  "epochSecond": 1,
  "nanoOfSecond": 234567890
}
~~~

The receiver constructs `Instant.ofEpochSecond(seconds, nanos)`. This numeric contract is sufficient for lossless round-tripping if seconds and nanoseconds have the right units, bounds, and valid storage types. `nanoOfSecond` must be understood as nanoseconds **within a second**, not total nanoseconds from the epoch.

If using numeric types in JavaScript or languages with limited integer precision, evaluate the specific transport types and value ranges before using very large epochNanos or boundary epochMillis; do not assume every `long` integer can be represented exactly by a floating-point number type.

## 11. Overflow Errors When Converting to Milliseconds

`Instant` allows a wider time range than the `long` millisecond range. Consequently, `toEpochMilli()` can throw `ArithmeticException`:

~~~java
try {
    System.out.println(Instant.MAX.toEpochMilli());
} catch (ArithmeticException ex) {
    System.out.println("out of long millis range");
}
~~~

Stdout:

~~~text
out of long millis range
~~~

If an application must store epochMillis, define the supported date range. Do not manually multiply `getEpochSecond() * 1000` and ignore overflow. Conversely, `Instant.ofEpochMilli(long)` can represent any `long` millisecond input within `Instant`'s range, but that does not mean every `Instant` can be converted to `long` milliseconds.

When measuring only **nanoseconds lost after a millisecond round-trip**, `Duration.between(restored, original).toNanos()` is safe because the lost portion is less than 1 ms. When computing very long durations, `Duration.toNanos()` can also overflow `long`; check the range before converting.

## 12. Exact Conversion Policy

A system that does not allow losing sub-millisecond nanoseconds can reject the conversion:

~~~java
static long toEpochMilliExact(Instant instant) {
    if (instant.getNano() % 1_000_000 != 0) {
        throw new IllegalArgumentException(
                "Instant has sub-millisecond precision");
    }
    return instant.toEpochMilli();
}
~~~

This is an **illustrative method**, placed inside a Java class that imports `java.time.Instant` to compile. It rejects inputs whose nanosecond fraction cannot be represented in milliseconds. If the instant is already millisecond-exact but too far from the epoch, `toEpochMilli()` can still throw an overflow error; that is a separate range check.

If the business domain **intentionally accepts precision reduction**, name it clearly and document the policy—for example, recording audit data at millisecond granularity. Do not describe precision reduction as "lossless" or "unchanged" when residual nanoseconds actually exist.

## 13. Do Not Confuse with System.nanoTime()

`System.nanoTime()` returns a relative counter from an arbitrary origin, used to measure **elapsed duration**. It is **not** nanoseconds since the Unix epoch.

~~~java
long startedAt = System.nanoTime();
// Run a task
long elapsedNanos = System.nanoTime() - startedAt;
~~~

Meanwhile, `Instant.now()` reads a wall-clock instant. An `Instant` object has nanosecond representation resolution, but it is not a performance timer guaranteed to have 1 ns physical accuracy. Do not pass `System.nanoTime()` values directly into `ofEpochSecond()` or divide them into epochMillis: their origins are incompatible.

Use `Instant` for event timestamps; for measuring short execution times, use an appropriate relative duration tool. For testing, inject a `Clock` to fix `Instant.now(clock)`.

## 14. Common Mistakes

1. **Confusing ms with ns:** `ofEpochSecond(seconds, 123)` adds 123 nanoseconds, not 123 milliseconds.
2. **Assuming toEpochMilli() preserves nanoseconds:** any sub-millisecond remainder is permanently lost.
3. **Assuming round-to-nearest:** the API floors down to the millisecond level.
4. **Dividing negative epochNanos with `/`:** Java truncates toward 0, unlike `-1 ns → -1 ms`.
5. **Using getNano() as total nanoseconds from epoch:** it is only the nanosecond fraction within a second.
6. **Computing epochNanos into a long without range checks:** this can overflow when far from the epoch.
7. **Passing through java.util.Date to keep nanoseconds:** `Date` only has millisecond precision.
8. **Believing java.sql.Timestamp guarantees nine digits in the DB:** schema, driver, and mapping may reduce precision.
9. **Inferring clock accuracy from Instant.now()'s digit count:** storage resolution does not prove measurement accuracy.
10. **Treating System.nanoTime() as a UTC timestamp:** it uses an arbitrary origin.
11. **Forgetting toEpochMilli() can overflow:** `Instant`'s range is wider than `long` epochMillis.
12. **Sending unitless timestamps:** this can cause confusion among seconds, milliseconds, microseconds, and nanoseconds.
13. **Confusing time zone changes with precision reduction:** converting to `ZonedDateTime` preserves nanoseconds.
14. **Skipping round-trip checks after serialization/DB writes:** data may be truncated or rounded in the pipeline.

## 15. Self-Check

**Question 1.** What does `Instant.ofEpochSecond(1, 234_567_890).toEpochMilli()` return?  
**Answer:** `1234`, losing `567890` nanoseconds when reconstructed via `ofEpochMilli(1234)`.

**Question 2.** Why does `1969-12-31T23:59:59.999999999Z` convert to `-1` ms instead of `0`?  
**Answer:** Because `toEpochMilli()` floors down to the lower millisecond mark; minus 1 ns lies between minus 1 ms and the epoch.

**Question 3.** When is a round-trip through milliseconds exact?  
**Answer:** When `getNano() % 1_000_000 == 0` and `toEpochMilli()` does not overflow.

**Question 4.** Can you recover `456789` nanoseconds from a string that the database truncated to `.123`?  
**Answer:** No; that information was lost during the precision-reduction step.

**Question 5.** How can you transmit full nanoseconds over JSON?  
**Answer:** Use an ISO UTC string preserving up to nine fractional second digits, or an `epochSecond` / `nanoOfSecond` pair, with consistent serializers and parsers.

**Question 6.** Does `Date.from(instant).toInstant()` always equal the original value?  
**Answer:** No, `Date` only retains milliseconds.

**Question 7.** Does `Instant.MAX.toEpochMilli()` always succeed?  
**Answer:** No; the result exceeds `long` range, so it throws `ArithmeticException`.

**Question 8.** Is `System.nanoTime()` the total nanoseconds since `1970-01-01T00:00Z`?  
**Answer:** No, it is a counter for measuring relative elapsed time against an unspecified origin.

## 16. Key Takeaways

`Instant` describes an instant down to **1 nanosecond** resolution, whereas epochMillis retains only **1 millisecond**. Converting down to milliseconds drops any nanosecond fraction not divisible by one million; that information cannot be reconstructed. For instants before the epoch, the floor rule produces an easily misunderstood result: **minus one nanosecond becomes minus one millisecond**. If full precision must be preserved, use `Instant` end-to-end, ISO text with full fractional digits, or a seconds–nanoseconds pair. If epochMillis must be used, explicitly document the precision-reduction policy, validate numeric ranges, and verify reads and writes across integration layers.
