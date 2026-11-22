# Immutability, Thread Safety, and Value-Based Comparison in `java.time`

When working with date and time in Java, three questions often go together: can an object be modified after creation, can it be shared across threads, and in what sense do two objects represent "the same point in time" or "the same value"? The standard types in `java.time` (Java 8+, working well on Java 17+) are designed to solve most of the problems previously encountered with `Date`, `Calendar`, and `SimpleDateFormat`. However, the immutability of a value **does not automatically make the entire business operation using that value thread-safe**, and "equality" must be understood according to the specific data type.

## 1. What Is Immutability?

An **immutable** object preserves its observable state after creation. For standard date-time implementations such as `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, `ZonedDateTime`, `Duration`, and `Period`, operations that modify a date or time return a **resulting value** without mutating the receiver object.

```java
LocalDate issuedAt = LocalDate.of(2026, 10, 24);
LocalDate expiresAt = issuedAt.plusDays(30);

// issuedAt is still 2026-10-24; expiresAt is 2026-11-23.
issuedAt.plusYears(1); // Result ignored: issuedAt does NOT change.
```

Practical implications:

- `plusDays`, `minusHours`, `withYear`, `atStartOfDay`, and many similar operations **return a value**; if you need the new state, you must capture the returned value (`date = date.plusDays(1)`).
- Reassigning a reference variable does not mutate the old object. If `LocalDate next = original.plusDays(1)`, places that still hold `original` will continue to see the old date.
- Do not assume every operation always allocates a new object: an implementation may return the existing object when the resulting value is unchanged. Therefore, **do not use `==` to check date-time equality**.
- Immutability is a property of the **object**, not the variable. A `LocalDate` variable can still be reassigned to another reference; `final LocalDate d` prevents reassigning `d` within its scope, but it is not what makes `LocalDate` immutable.
- Standard `DateTimeFormatter` instances are also immutable and safe to share. In contrast, `DateTimeFormatterBuilder` is a mutable builder during configuration.

Immutability makes code easier to reason about: no thread or method can "secretly" modify a date-time value that another method is using. However, not **every** class implementing `Temporal`, `TemporalAccessor`, or `Clock` has the same guarantees. When saying `java.time` is immutable, you must rely on the contract of the **concrete type**; custom implementations and wrapper objects must be evaluated separately.

## 2. Choosing the Right Type: Which Value Is Being Compared?

| Type | Represented Value | Uniquely Identifies an Instant? | Meaning When Comparing |
| --- | --- | --- | --- |
| `LocalDate` | Calendar date, e.g. `2026-10-24` | No | Compares calendar dates without time or time zone |
| `LocalTime` | Time of day | No | Compares local time |
| `LocalDateTime` | Local date and time | No | Compares date/time fields; offset/zone is unknown |
| `Instant` | Point on the UTC timeline | Yes | Compares events in absolute time |
| `OffsetDateTime` | Local date-time + UTC offset | Yes | Value includes offset, but can be converted to `Instant` |
| `ZonedDateTime` | Date-time + `ZoneId` + zone-rule offset | Yes | Value retains zone info; can be converted to `Instant` |
| `Duration` | Time span in seconds and nanoseconds | Not applicable | Length of time in time-based units |
| `Period` | Number of calendar years, months, days | Not applicable | Amount of time in calendar units |

`LocalDateTime.of(2026, 10, 24, 9, 0)` is not yet an absolute point in time: 09:00 in Vietnam and 09:00 in Tokyo are two different instants. If you must store or correlate when an event occurred across multiple regions, use `Instant` as the common representation; keep `ZoneId` as well when you need the display zone or calendar context.

Do not equate `Period.ofDays(1)` and `Duration.ofHours(24)` in every calculation on `ZonedDateTime`: adding one **local calendar day** can differ from adding exactly **24 hours** when crossing a Daylight Saving Time (DST) transition.

## 3. Why Are Immutable Values Easy to Share Across Threads?

A standard `LocalDate`, `Instant`, or `DateTimeFormatter` instance has no internal mutable state for threads to contend over. Multiple threads can concurrently read, format, parse, or compute from the same instance without locking it. Each computation produces its own result.

```java
private static final DateTimeFormatter DISPLAY =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");

// Threads can call DISPLAY.format(date) concurrently.
String text = DISPLAY.format(LocalDate.of(2026, 10, 24));
```

Three distinct layers of concern should be separated:

1. **Safety of an immutable value:** reading and calling methods on a standard instance does not alter the value another thread is reading.
2. **Reference publication:** if one thread creates or replaces a shared reference, use a proper publication mechanism (`static final`, synchronization, `volatile`, `AtomicReference`, concurrent structures, etc.). This ensures other threads observe the reference in a timely manner with Java Memory Model visibility guarantees. The `final` fields of an immutable object support initialization safety, but **they do not turn arbitrary reference passing or updating into a correct concurrency protocol**.
3. **Safety of the business operation:** two threads reading the same expiration date and both updating it to "add one day" can lose an update, even though each individual `LocalDate` is immutable.

Example of a lost-update bug (*illustrative* code, not a standalone program):

```java
private LocalDate deadline = LocalDate.of(2026, 10, 24);

void extendOneDay() {
    deadline = deadline.plusDays(1);
}
```

If two threads both read `2026-10-24` before writing, both may assign `2026-10-25`; the result advances by only **one day**, not two. Computing `plusDays` and assigning the result is a multi-step read-compute-write operation; `volatile` on `deadline` only provides reference visibility, **not** atomicity across all steps.

When you genuinely need shared date-time state that must be updated atomically, you can use:

```java
private final AtomicReference<LocalDate> deadline =
        new AtomicReference<>(LocalDate.of(2026, 10, 24));

void extendOneDay() {
    deadline.updateAndGet(day -> day.plusDays(1));
}
```

(Requires `import java.time.LocalDate;` and `import java.util.concurrent.atomic.AtomicReference;` in the enclosing class.) `updateAndGet` performs a compare-and-set update; the function computing the new value may be retried under contention, so the lambda must be **side-effect free**. `day -> day.plusDays(1)` fits because it only produces a resulting value. If the business logic must update both the expiration date and other fields together, you must coordinate **all related state** with an appropriate synchronization or transaction mechanism; `AtomicReference<LocalDate>` alone is not enough.

### Pay Attention to the Time Source

`LocalDate.now()`, `Instant.now()`, or `ZonedDateTime.now(zone)` produce immutable values, but **results from two separate calls can differ** because the clock keeps ticking. To make test logic deterministic, pass an appropriate `Clock`:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-10-24T12:00:00Z"), ZoneOffset.UTC);
LocalDate today = LocalDate.now(fixed); // 2026-10-24
```

`Clock` is an abstraction for a time source; the thread safety of a custom `Clock` implementation must be verified against that implementation itself. The resulting `LocalDate` values remain immutable.

## 4. Value Equality, Ordering, and Instant Equality

### 4.1. `==` vs. `equals()`

- `a == b` on two reference variables checks whether they point to the **same object**.
- `a.equals(b)` uses the **value equality** contract of the concrete type.
- When `equals()` is `true`, both values must have the same `hashCode()`. This is the basis for using them as `HashMap` keys or `HashSet` elements.
- Do not assume that two objects representing the same date are shared from a cache, or that an object returned by a computation is always distinct from the original.

```java
LocalDate a = LocalDate.of(2026, 10, 24);
LocalDate b = LocalDate.parse("2026-10-24");

boolean sameDate = a.equals(b);                 // true
boolean sameHash = a.hashCode() == b.hashCode(); // true
```

`LocalDate` compares by calendar date. `LocalDateTime` compares by local date and time fields. For `Instant`, two values are equal when they refer to the same point on the timeline.

### 4.2. `OffsetDateTime` and `ZonedDateTime`: Same Instant Does Not Imply `equals()`

A single event can be represented with different offsets or time zones. For example:

```java
OffsetDateTime inVietnam =
        OffsetDateTime.parse("2026-10-24T19:00:00+07:00");
OffsetDateTime inJapan =
        OffsetDateTime.parse("2026-10-24T21:00:00+09:00");

inVietnam.equals(inJapan);                      // false
inVietnam.isEqual(inJapan);                     // true
inVietnam.toInstant().equals(inJapan.toInstant()); // true
```

`OffsetDateTime.equals()` considers both the local date-time **and the offset**. `isEqual()` checks whether the two values represent the same instant. For `ZonedDateTime`, `equals()` also distinguishes the time-zone information (`ZoneId`); `isEqual()` compares on the timeline. Two objects at the same instant in `Asia/Ho_Chi_Minh` and `Asia/Tokyo` can have `isEqual() == true` and `equals() == false`.

The two zone-conversion methods also have different meanings:

- `withZoneSameInstant(otherZone)`: changes the zone representation while **preserving the instant**.
- `withZoneSameLocal(otherZone)`: tries to keep the local date-time fields, so the **instant may change** (and nonexistent or ambiguous times during DST must be resolved according to zone rules).

Therefore, when deduplicating logs, events, or timestamps originating from multiple systems, normalize via `toInstant()` and use `Instant.equals()` or an `Instant` key. When the offset or calendar zone itself is part of the business data (zone-based schedules, display), do not strip it away arbitrarily to keep only the instant.

### 4.3. Ordering: `compareTo`, `isBefore`, `isAfter`

- `LocalDate.isBefore(other)` and `isAfter(other)` check **calendar date** order.
- `Instant.isBefore(other)` and `isAfter(other)` check **instant** order.
- `OffsetDateTime.isBefore/isAfter/isEqual` and `ZonedDateTime.isBefore/isAfter/isEqual` check order/equality on the **timeline**.
- `compareTo()` defines the natural ordering used for sorting. For `OffsetDateTime` and `ZonedDateTime`, natural ordering applies tie-breakers when two instants are equal in order to distinguish local/offset/zone representations. Thus, **`isEqual() == true` does not imply `compareTo() == 0`** for these types.

If your problem requires **ordering strictly by instant**, state that intent explicitly:

```java
Comparator<ZonedDateTime> timelineOrder =
        Comparator.comparing(ZonedDateTime::toInstant);
```

(Requires `import java.time.ZonedDateTime;` and `import java.util.Comparator;`.) A `TreeSet` using this comparator treats two elements at the same instant as equivalent **according to the comparator** and may retain only one element even though `equals()` between them is `false`; consider collection contracts carefully when using a comparator inconsistent with `equals()`.

### 4.4. Value Equality of `Duration` and `Period`

```java
Duration.ofMinutes(1).equals(Duration.ofSeconds(60)); // true
Period.ofMonths(12).equals(Period.ofYears(1));         // false
```

`Duration` represents a total number of seconds/nanoseconds; factories producing the same length normalize to the same value. `Period` stores **year, month, and day components**: "12 months" and "1 year" do not have the same value structure even though in many calendar calculations they produce equivalent results. Do not extrapolate the comparison rules of one type to the other.

## 5. Standalone Java 17+ Example

Create the file **`DateTimeValueDemo.java`**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicReference;

public class DateTimeValueDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalDate next = date.plusDays(1);

        System.out.println("date = " + date);
        System.out.println("next = " + next);
        System.out.println("value equals = "
                + date.equals(LocalDate.parse("2026-10-24")));

        Instant event = Instant.parse("2026-10-24T12:00:00Z");
        OffsetDateTime vietnam = event.atOffset(ZoneOffset.ofHours(7));
        OffsetDateTime japan = event.atOffset(ZoneOffset.ofHours(9));

        System.out.println("vietnam = " + vietnam);
        System.out.println("japan = " + japan);
        System.out.println("offset equals = " + vietnam.equals(japan));
        System.out.println("same instant = " + vietnam.isEqual(japan));

        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu");
        System.out.println("formatted = " + formatter.format(date));

        AtomicReference<LocalDate> sharedDate = new AtomicReference<>(date);
        sharedDate.updateAndGet(d -> d.plusDays(2));
        System.out.println("sharedDate = " + sharedDate.get());
        System.out.println("original unchanged = " + date);
    }
}
```

Compile and run:

```bash
javac DateTimeValueDemo.java
java DateTimeValueDemo
```

Expected output:

```text
date = 2026-10-24
next = 2026-10-25
value equals = true
vietnam = 2026-10-24T19:00+07:00
japan = 2026-10-24T21:00+09:00
offset equals = false
same instant = true
formatted = 24/10/2026
sharedDate = 2026-10-26
original unchanged = 2026-10-24
```

Explanation: `plusDays` does not mutate `date`; creating an independent `LocalDate` for the same day still compares equal with `equals`; two `OffsetDateTime` values have different offsets yet represent the same `Instant`; `AtomicReference` replaces the reference atomically while the original `date` value remains unchanged. The example only demonstrates a single update; safety under multi-threaded contention relies on the atomic contract of `AtomicReference.updateAndGet`, not on the number of runs in the demo.

## 6. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Calling `date.plusDays(1)` and assuming `date` changed | `LocalDate` values are immutable | Capture the result: `date = date.plusDays(1)` |
| Comparing two dates with `==` | Only compares references | Use `equals()`; use `isBefore/isAfter` for ordering |
| Using `LocalDateTime` to compare global events | Lacks offset/zone, so no instant is defined | Convert zone-aware data to `Instant` |
| Expecting two timestamps at the same instant to be `equals()` | `OffsetDateTime` and `ZonedDateTime` also retain offset/zone | Use `isEqual()` or compare `toInstant()` |
| Sharing a `SimpleDateFormat` in a `static` field | `SimpleDateFormat` is mutable and not thread-safe | Use `static final DateTimeFormatter` for standard formatting/parsing |
| Thinking `shared = shared.plusDays(1)` is atomic because `LocalDate` is immutable | Two threads can lose an update | Use `AtomicReference.updateAndGet`, locks, or transactions as needed |
| Thinking `volatile` makes read-modify-write atomic | `volatile` does not combine multiple steps into one operation | Use an appropriate atomic update mechanism |
| Equating a calendar day with 24 hours in every zone | DST can produce 23- or 25-hour calendar days | Distinguish `Period`, `Duration`, `plusDays`, and `plusHours` |
| Keying by `ZonedDateTime` while expecting instant-based deduplication | `equals/hashCode` also inspect zone and value fields | Use `Instant` keys when identity is the occurrence instant |

When working with legacy APIs, remember that `java.util.Date` and `Calendar` are mutable; `SimpleDateFormat` is not safe to share across threads without synchronization. You can convert a `Date` to an immutable snapshot via `date.toInstant()`, though the original `Date` object itself can still be mutated by other code.

## 7. Decision Rules in Applications

1. **Model the right quantity:** birthday/holiday → `LocalDate`; local opening hours → `LocalTime`; an event that occurred → `Instant`; schedule tied to zone rules → `ZonedDateTime` with `ZoneId`; fixed elapsed time → `Duration`; calendar shift → `Period`.
2. **Pass immutable values freely, manage mutable state explicitly:** date-time objects and standard formatters can be shared; any variable or container being updated needs its own concurrency mechanism.
3. **Choose comparison operations by semantics:** identical represented value → `equals`; same instant → `isEqual`/`toInstant`; before/after → `isBefore`/`isAfter`; sorting → `compareTo` or an explicit comparator.
4. **Specify zone rules and time sources:** the same local clock time does not guarantee the same instant; for time-sensitive logic, accept a `Clock` for testing and state input zone/offset clearly.
5. **Do not substitute immutability for atomicity:** when updating deadlines, quotas, bookings, or concurrent state, evaluate which steps belong to the transaction and protect the entire operation.

### Self-Check

- Two `LocalDate` instances for the same date created in different ways: how should they be compared? → `equals()`.
- 19:00 at UTC+07 and 21:00 at UTC+09 on the same date: are they the same instant? → Yes, because both are 12:00 UTC; `isEqual()` is `true`, while `OffsetDateTime.equals()` is `false`.
- Two threads concurrently increment an expiration date stored in a `LocalDate` variable: do immutable objects prevent lost updates? → No; atomic updates or synchronization are required.
- A `DateTimeFormatter` is used by multiple threads: must you create a separate formatter per thread? → No, for standard immutable and thread-safe implementations.
- Does `LocalDateTime` 09:00 provide enough information to compute the UTC instant? → No; zone rules or an offset are required.

**Takeaway:** `java.time` cleanly separates **immutable values** from **mutable state**, and **representation equality** from **same-instant equality**. Pick the right type, capture computation results, and choose concurrency and comparison mechanisms that match your business semantics.
