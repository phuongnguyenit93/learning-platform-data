# Converting Time Zones While Preserving the Instant with ZonedDateTime.withZoneSameInstant()

In Java, `ZonedDateTime` represents a **local date and time along with a `ZoneId` and a resolved offset**. When you want to view **the same event** in the time of another country, city, or system, use:

```java
ZonedDateTime converted = original.withZoneSameInstant(targetZone);
```

The `withZoneSameInstant(ZoneId zone)` method returns a new `ZonedDateTime` in the target zone, **strictly preserving the same `Instant`** (*the point on the timeline*). Therefore, the displayed hour, calendar date, and offset may change, but the event does not "move" earlier or later in reality.

Key distinctions to make right from the start:

- **`withZoneSameInstant(zone)`:** preserves the **actual instant**, changes the **displayed date and time** according to the zone.
- **`withZoneSameLocal(zone)`:** attempts to preserve the **wall-clock date and time** when changing the zone; the **actual instant usually changes**.
- **`withFixedOffsetZone()`:** keeps the existing date-time value and offset, but replaces the region-based zone with a fixed-offset zone; it is not a tool for converting the displayed time zone to another region.

This lesson focuses on `withZoneSameInstant()`, its mechanism, runnable Java 17+ examples, DST handling, differences from local-time-preserving operations, and how to apply it in applications.

## 1. Three Layers of Meaning in ZonedDateTime

`ZonedDateTime` binds together three pieces of information:

1. **Local date-time (`LocalDateTime`):** for example, `2024-03-10T03:30`.
2. **Zone ID (`ZoneId`):** for example, `America/New_York` or `Asia/Ho_Chi_Minh`. With a region ID, its rules determine the offset for each point in time.
3. **Offset (`ZoneOffset`):** for example, `-04:00` or `+07:00`, indicating the difference from UTC at that point in time.

Once its components are resolved in accordance with the zone rules, `ZonedDateTime` identifies a **single unique `Instant`**. You can retrieve it with `toInstant()`.

Example:

```java
import java.time.*;

Instant moment = Instant.parse("2024-03-10T07:30:00Z");

ZonedDateTime newYork = moment.atZone(
        ZoneId.of("America/New_York"));
ZonedDateTime vietnam = moment.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

System.out.println(newYork);
// 2024-03-10T03:30-04:00[America/New_York]
System.out.println(vietnam);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
```

The two representations have clock times that differ by **11 hours** at this instant, yet both point to `2024-03-10T07:30:00Z`. New York had already switched to its summer offset `-04:00` on 2024-03-10. Therefore, you cannot assume the difference between two zones is a constant number of hours throughout the year.

## 2. What Does withZoneSameInstant() Actually Do?

Syntax:

```java
ZonedDateTime result = source.withZoneSameInstant(destination);
```

- `source` is a `ZonedDateTime` that already identifies an actual instant.
- `destination` is the target `ZoneId`, which can be an IANA region ID (such as `Europe/Paris`), a `ZoneOffset`, or `ZoneId.of("UTC")`.
- The result is a **new object**. `ZonedDateTime` is **immutable**; `source` is not modified.
- Key invariant: **`source.toInstant().equals(result.toInstant())` is always `true` when the conversion succeeds**.
- The target offset is looked up according to the **target zone's rules at that exact `Instant`**, rather than copying the source offset.

You can understand the algorithm conceptually as follows:

```text
source ZonedDateTime
       |
       | source.toInstant()
       v
   a single Instant
       |
       | look up ZoneRules of destination at this Instant
       v
new ZonedDateTime: local date-time + offset + destination ZoneId
```

The diagram explains the **semantics**, not Java's internal source code. Because the `Instant` is preserved, the conversion is unambiguous even when the target local time falls on a DST transition day: a single `Instant` always corresponds to a single applicable offset in the target zone, even though two different `Instant`s may display the same local time during an *overlap*.

### Equivalent Expression for Mental Verification

```java
ZonedDateTime converted = source.withZoneSameInstant(destination);

Instant originalInstant = source.toInstant();
ZonedDateTime reconstructed = originalInstant.atZone(destination);
// converted and reconstructed represent the same Instant in the same target zone.
```

This snippet assumes `source` and `destination` are already defined externally and requires `import java.time.*`. Calling `withZoneSameInstant` directly on a `ZonedDateTime` is the clearest way to express **changing the display zone for an existing zoned event**.

## 3. Converting from New York to Vietnam at a Specific Instant

Suppose a notification occurs at `2024-03-10T07:30:00Z`. In New York, that is 03:30 after DST starts; in Vietnam, it is 14:30 on the same day.

```java
ZoneId newYork = ZoneId.of("America/New_York");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime ny = Instant
        .parse("2024-03-10T07:30:00Z")
        .atZone(newYork);

ZonedDateTime vn = ny.withZoneSameInstant(vietnam);

System.out.println(ny);
// 2024-03-10T03:30-04:00[America/New_York]
System.out.println(vn);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]

System.out.println(ny.toInstant().equals(vn.toInstant()));
// true
```

This snippet requires `import java.time.*`. Observations:

- **The clock time changes** from 03:30 to 14:30 because the zones have different offsets.
- **The offset changes** from `-04:00` to `+07:00`, taken from each zone's rules at that instant.
- **The Zone ID changes** from `America/New_York` to `Asia/Ho_Chi_Minh`.
- **The `Instant` stays the same**: no new event is created and 11 hours are not added to the actual event.

This conversion is suitable for systems that store a single event and display it to users in multiple locations: transaction detail pages, notifications, activity histories, dashboards, or operational logs.

## 4. Comparison with withZoneSameLocal(): Two Different Needs

These two APIs are easy to confuse because both start with `withZone…`, yet their choices of **what to preserve** are opposites.

| Requirement | Method to Use | What Is Preserved |
| --- | --- | --- |
| "Display the same transaction in Vietnam time" | `withZoneSameInstant(vietnam)` | `Instant` |
| "Change the appointment location while still keeping 09:00 local time at the new location" | `withZoneSameLocal(newZone)` or create the appointment from local time with an appropriate policy | `LocalDateTime` if that time is valid in the target zone |
| "Show me the UTC time of this event" | `withZoneSameInstant(ZoneOffset.UTC)` | `Instant` |
| "Only change the zone without changing the wall-clock time" | `withZoneSameLocal(newZone)` | Wall-clock time is the goal, while `Instant` usually differs |

Starting from the same New York source `2024-03-10T03:30-04:00[America/New_York]`:

```java
ZonedDateTime sameInstant = ny.withZoneSameInstant(vietnam);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]

ZonedDateTime sameLocal = ny.withZoneSameLocal(vietnam);
// 2024-03-10T03:30+07:00[Asia/Ho_Chi_Minh]
```

The `sameInstant` result is still `2024-03-10T07:30Z`. The `sameLocal` result is `2024-03-09T20:30Z`: the same `03:30` digits in Vietnam correspond to a **different** point in time.

**Important note:** `withZoneSameLocal` cannot always preserve the exact local time. If that wall-clock time falls into a **DST gap** in the target zone, the API may automatically adjust it to a valid time; if it falls in a **DST overlap**, the API resolves the offset according to its rules. Therefore, for appointments with a strict requirement of "exactly 02:30", you need a policy that checks `ZoneRules` before applying. When the requirement is to **preserve the instant**, `withZoneSameInstant` is exact and avoids ambiguous offset choices.

### Do Not Confuse with withFixedOffsetZone()

`source.withFixedOffsetZone()` creates a representation whose zone ID is the **current offset** of `source`. This is typically used to "freeze" the zone so region rules do not affect subsequent calculations; it does **not** mean "convert to UTC" or "convert to another country".

For example, at an instant when New York has offset `-04:00`, `withFixedOffsetZone()` keeps `-04:00` as a fixed zone. Another instant during winter in New York might require `-05:00`, but an object converted to a fixed-offset zone will not automatically switch to `-05:00`.

## 5. The Calendar Date Can Change While Preserving the Instant

Changing zones can shift the displayed time **to the previous day or the next day**. This is expected and correct behavior.

For example, an event occurring at 00:30 on 2024-01-01 in Vietnam:

```java
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime vietnamNewYear = ZonedDateTime.of(
        2024, 1, 1, 0, 30, 0, 0, vietnam);

ZonedDateTime utcView = vietnamNewYear
        .withZoneSameInstant(ZoneOffset.UTC);

System.out.println(vietnamNewYear);
// 2024-01-01T00:30+07:00[Asia/Ho_Chi_Minh]
System.out.println(utcView);
// 2023-12-31T17:30Z
```

This snippet requires `import java.time.*`. It is **the exact same real-world event**, yet in Vietnam it is **2024-01-01** and in UTC it is **2023-12-31**. Depending on whether you call `toLocalDate()` before or after the conversion, you can get different dates:

```java
LocalDate vietnamDate = vietnamNewYear.toLocalDate(); // 2024-01-01
LocalDate utcDate = utcView.toLocalDate();             // 2023-12-31
```

This snippet requires `import java.time.LocalDate` and uses the two variables from the previous example. When computing **accounting dates**, **expiration dates**, **report grouping**, or **end-of-day deadlines**, you must determine the business zone before extracting the date. Do not take the UTC date and merely reformat the display string if the actual rule is "the date in Hanoi".

## 6. DST: Why Can't You Just Add a Fixed Number of Hours?

`ZoneId.of("America/New_York")` and `ZoneId.of("Europe/Paris")` are not simply numbers like `-05:00` or `+01:00`. They use a time-zone rules database (`ZoneRules`) that can vary by date, time, and historical changes.

In New York in 2024:

- On `2024-01-15T12:00:00Z`: the offset is `-05:00`.
- On `2024-07-15T12:00:00Z`: the offset is `-04:00`.

If you write:

```java
// Design flaw when the offset must follow New York rules:
ZonedDateTime newYorkLike = instant.atZone(ZoneOffset.of("-05:00"));
```

Java will always use `-05:00` because it is a **fixed offset**, even when summer time in New York is actually `-04:00`. To handle a **city's** time properly, use:

```java
ZonedDateTime accurateNewYork = instant.atZone(
        ZoneId.of("America/New_York"));
```

Both snippets above assume an `instant` variable of type `Instant` is already declared and require `import java.time.*`. Even if a country rarely changes its offset today, a region `ZoneId` better captures geographic intent for future scheduling rules.

### Converting Zones on a DST Transition Day

On 2024-03-10 in New York, clocks sprang forward from 01:59:59 to 03:00:00. The local time `2024-03-10T02:30` does not exist in this zone. However, we can start from a **real `Instant`**:

```java
Instant moment = Instant.parse("2024-03-10T07:30:00Z");
ZonedDateTime ny = moment.atZone(
        ZoneId.of("America/New_York"));
// 2024-03-10T03:30-04:00[America/New_York]
```

Then `ny.withZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"))` simply looks up the offset at **the same instant**, producing 14:30 in Vietnam. There is no "guessing" an offset inside a gap: the input value already identifies a valid `Instant`.

Conversely, if you only have a **`LocalDateTime`** of 02:30 in New York on that day, `LocalDateTime.of(2024, 3, 10, 2, 30).atZone(newYork)` will **adjust** the nonexistent time to 03:30 according to Java's default rules. That is a matter of **resolving a local date-time against a zone**, which is different from converting a `ZonedDateTime` that already has an `Instant` using `withZoneSameInstant`.

### Overlap: Two Identical Wall-Clock Times Can Still Be Two Different Instants

On 2024-11-03 in New York, 01:30 occurred twice: once with `-04:00` and once with `-05:00`. Those two `ZonedDateTime` instances have different `Instant`s despite having the same `LocalDateTime`.

```java
ZoneId newYork = ZoneId.of("America/New_York");
LocalDateTime local = LocalDateTime.of(2024, 11, 3, 1, 30);

ZonedDateTime earlier = local.atZone(newYork);
ZonedDateTime later = earlier.withLaterOffsetAtOverlap();

System.out.println(earlier.toInstant());
// 2024-11-03T05:30:00Z
System.out.println(later.toInstant());
// 2024-11-03T06:30:00Z
```

This snippet requires `import java.time.*`. If you convert both values to Vietnam using `withZoneSameInstant(vietnam)`, Java preserves the **two distinct `Instant`s**, so in Vietnam they are one hour apart rather than accidentally collapsing into one. This is crucial when handling timestamps for transactions, logs, or distributed systems.

## 7. Complete, Directly Runnable Java 17+ Example

Create a file named **`ZoneSameInstantDemo.java`**:

```java
import java.time.*;

public class ZoneSameInstantDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

        Instant moment = Instant.parse("2024-03-10T07:30:00Z");
        ZonedDateTime ny = moment.atZone(newYork);
        ZonedDateTime vn = ny.withZoneSameInstant(vietnam);
        ZonedDateTime utc = ny.withZoneSameInstant(ZoneOffset.UTC);

        System.out.println("NY: " + ny);
        System.out.println("VN same instant: " + vn);
        System.out.println("UTC same instant: " + utc);
        System.out.println("Same instant? " + ny.toInstant().equals(vn.toInstant()));
        System.out.println("Same local time? "
                + ny.toLocalDateTime().equals(vn.toLocalDateTime()));

        ZonedDateTime sameLocal = ny.withZoneSameLocal(vietnam);
        System.out.println("VN same local: " + sameLocal);
        System.out.println("Same instant after sameLocal? "
                + ny.toInstant().equals(sameLocal.toInstant()));

        ZonedDateTime vnMidnight = ZonedDateTime.of(
                2024, 1, 1, 0, 30, 0, 0, vietnam);
        System.out.println("VN New Year: " + vnMidnight);
        System.out.println("UTC New Year: "
                + vnMidnight.withZoneSameInstant(ZoneOffset.UTC));

        LocalDateTime gap = LocalDateTime.of(2024, 3, 10, 2, 30);
        ZonedDateTime adjustedNY = gap.atZone(newYork);
        System.out.println("NY gap resolved: " + adjustedNY);
        System.out.println("VN from resolved: "
                + adjustedNY.withZoneSameInstant(vietnam));
    }
}
```

Compile and run:

```bash
javac ZoneSameInstantDemo.java
java ZoneSameInstantDemo
```

**Exact stdout** (verified with `javac --release 17` and `java`):

```text
NY: 2024-03-10T03:30-04:00[America/New_York]
VN same instant: 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
UTC same instant: 2024-03-10T07:30Z
Same instant? true
Same local time? false
VN same local: 2024-03-10T03:30+07:00[Asia/Ho_Chi_Minh]
Same instant after sameLocal? false
VN New Year: 2024-01-01T00:30+07:00[Asia/Ho_Chi_Minh]
UTC New Year: 2023-12-31T17:30Z
NY gap resolved: 2024-03-10T03:30-04:00[America/New_York]
VN from resolved: 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
```

**Output breakdown:**

1. The first three lines view the same `2024-03-10T07:30:00Z` from New York, Vietnam, and UTC. The point in time does not change.
2. Comparing `toInstant()` returns `true` even though `toLocalDateTime()` returns `false`. That is the exact purpose of `withZoneSameInstant`.
3. `withZoneSameLocal(vietnam)` keeps the same `03:30` clock time but shifts the `Instant` to a different point in time. Do not use it to display the same event.
4. Converting a near-midnight Vietnam time to UTC produces **the previous day and previous year**, which is a valid result for the same `Instant`.
5. New York DST gap day: `LocalDateTime` 02:30 is resolved to 03:30, and then converting with the same `Instant` to Vietnam gives 14:30.

## 8. Comparing ZonedDateTime Instances After Zone Conversion

There are at least three ways of "comparing" that are frequently confused:

```java
ZonedDateTime a = Instant
        .parse("2024-03-10T07:30:00Z")
        .atZone(ZoneId.of("America/New_York"));
ZonedDateTime b = a.withZoneSameInstant(
        ZoneId.of("Asia/Ho_Chi_Minh"));

boolean sameInstant = a.toInstant().equals(b.toInstant()); // true
boolean equalInstant = a.isEqual(b);                       // true
boolean sameObjectValue = a.equals(b);                    // false
```

This snippet requires `import java.time.*`.

- `toInstant().equals(...)` and `ZonedDateTime.isEqual(...)` check for the **same point in time**.
- `ZonedDateTime.equals(...)` requires the date-time, offset, and zone to all be identical; changing the `ZoneId` usually makes this comparison `false` even when both values occur at the exact same instant.
- `toLocalDateTime().equals(...)` only checks whether the **calendar/clock times look the same**, not whether they represent the same `Instant`.

When sorting **events in chronological order**, use `Instant` or an instant-based comparator; do not sort solely by local date-time values obtained from different zones. If you want to compare records based on the same UTC instant, convert them to `Instant` first. Do not use `equals` on two `ZonedDateTime` instances with different zones as a sole check to conclude "different events".

## 9. Formatting by Zone and Locale: Two Independent Dependencies

After converting the zone, you can format the `ZonedDateTime` for the user:

```java
ZonedDateTime userView = event.withZoneSameInstant(userZone);
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm XXX '['VV']'", displayLocale);

String label = formatter.format(userView);
```

This snippet represents **service-layer code**, assuming `event` is a `ZonedDateTime`, `userZone` is a `ZoneId`, and `displayLocale` is a `Locale`; it requires `import java.time.*`, `java.time.format.DateTimeFormatter`, and `java.util.Locale`.

- **`ZoneId`** determines **which date, time, and offset** apply where the user wants to view the event.
- **`Locale`** determines the language and formatting conventions when the pattern contains locale-sensitive fields.
- **`DateTimeFormatter`** determines how the value is rendered as a string; it should not be the place that implicitly re-decides the business time.

If the data comes from an `Instant`, you can also call `instant.atZone(userZone)`. For data that is already a `ZonedDateTime`, `withZoneSameInstant(userZone)` accurately expresses "change the display, keep the event".

Do not infer the target time zone from `Locale`. A Vietnamese-speaking user might be viewing New York time; an English-speaking user might need Vietnam time. Language and time-zone settings must be kept independent.

## 10. Storage, API, and Distributed Systems Design

In multi-zone systems, distinguish clearly between whether a data field represents an **instant that already occurred** or a **future scheduled appointment intent**.

### 10.1. Event Instants: Store Instant, Convert Zone at Display Time

For `createdAt`, `paidAt`, `sentAt`, `completedAt`, or log timestamps:

```java
Instant stored = Instant.parse("2024-03-10T07:30:00Z");

ZoneId viewerZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime displayed = stored.atZone(viewerZone);
// 2024-03-10T14:30+07:00[Asia/Ho_Chi_Minh]
```

This snippet requires `import java.time.*`. Using `Instant` stores a location-independent point in time. If you already have a `ZonedDateTime`, `withZoneSameInstant` changes the display zone and `toInstant()` gives the absolute value for storage.

For JSON, a field representing an absolute timestamp should explicitly include an offset or UTC:

```json
{
  "createdAt": "2024-03-10T07:30:00Z",
  "viewerZoneId": "Asia/Ho_Chi_Minh"
}
```

You can pass an additional `ZoneId`/zone field when genuinely needed. Do not treat `"2024-03-10T07:30:00"` without an offset as a UTC timestamp unless the contract explicitly specifies so. A standalone `LocalDateTime` does not carry enough information to derive an `Instant`.

### 10.2. Local Appointment Intent: Preserve the Zone and Business Rules

A future appointment for "09:00 on July 15 in Paris" is different from displaying a past event in Paris. Here, **09:00 Paris** is the business intent; you should combine `LocalDateTime` and `ZoneId.of("Europe/Paris")` to create or store the appointment, rather than converting from another `ZonedDateTime` with `withZoneSameInstant` if you want to keep the digits `09:00`.

For a recurring schedule such as "09:00 every Monday in Paris", you must preserve the recurrence rule, local time, and zone. DST causes the **corresponding UTC instant** to shift seasonally. Locking in a fixed offset or a single `Instant` and repeatedly adding 7×24 hours can cause the local time to drift over time.

### 10.3. Do Not Depend on the JVM Default Zone

Avoid writing:

```java
ZonedDateTime now = ZonedDateTime.now();
// Time rules now depend on the host machine's default time zone.
```

Instead, use a time source and zone with an explicit contract:

```java
Clock clock = Clock.systemUTC(); // created at system configuration
Instant now = clock.instant();

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime businessView = now.atZone(businessZone);
```

This snippet requires `import java.time.*`. In a real service, `Clock` and `ZoneId` are typically **injected**; tests pass `Clock.fixed(...)` to keep results deterministic. When a single transaction needs multiple display views, capture **one `Instant`**, then convert it to each zone. Do not call `now()` multiple times and assume each call returns the exact same instant.

## 11. Common Mistakes

| Mistake | Why Is It Wrong? | Correct Approach |
| --- | --- | --- |
| Using `withZoneSameLocal` to display the same transaction in a new zone | It tries to keep the wall-clock time, which can change the actual event | `withZoneSameInstant(targetZone)` |
| Manually adding/subtracting offsets with `plusHours` to convert times | Arithmetic changes the `Instant` and ignores DST | `withZoneSameInstant` with a region `ZoneId` |
| Using a city's current offset for all dates | DST or historical zone rules may change | Use `ZoneId.of("Area/City")` |
| Assuming `withZoneSameInstant` keeps the same calendar date | One event can fall on two different dates in two zones | Convert the zone before extracting the business `LocalDate` |
| Comparing `ZonedDateTime.equals` to check for the same instant | `equals` also checks date/time and zone | Use `isEqual` or compare `Instant`s |
| Treating `LocalDateTime` as a global timestamp | It has no offset or `ZoneId` | Store `Instant` or specify a full zone/offset |
| Extracting the date first and then converting to the target zone | The UTC date can differ from the local date | Convert `ZonedDateTime` first, then call `toLocalDate()` |
| Guessing the zone from `Locale` | Language does not determine geographic location | Manage `Locale` and `ZoneId` separately |
| Ignoring the return value of `withZoneSameInstant` | `ZonedDateTime` is immutable; the original object does not change | Assign or pass the returned value |
| Using an instant-preserving conversion to relocate an appointment while keeping 09:00 | The local time at the new location will change | Use local time + target zone and handle DST |
| Not validating externally supplied zone IDs | `ZoneId.of` can throw `DateTimeException` | Validate input and only accept supported zones |

**Additional note:** Abbreviated time-zone names like `CST` are often ambiguous. Exchange standard IANA IDs such as `America/New_York` or `Asia/Ho_Chi_Minh` instead. An offset string like `+07:00` is a fixed offset, not a substitute for an entire region's rules.

## 12. Recommended Tests

| Test Case | What to Verify |
| --- | --- |
| Convert New York → Vietnam using `withZoneSameInstant` | `toInstant()` remains unchanged |
| Convert the same value to UTC | Still equals the original event instant |
| Convert across midnight or year-end | Date may change; `Instant` does not |
| Compare `withZoneSameLocal` and `withZoneSameInstant` | For zones with different offsets, `withZoneSameLocal` usually yields a different instant |
| DST gap day | `Instant` converts to a valid time; does not invent a nonexistent local time |
| DST overlap day | Two events with the same local time still preserve different `Instant`s |
| Convert zone and compare `equals` / `isEqual` | `isEqual` is `true` for the same `Instant`; `equals` is usually `false` |
| Use `Clock.fixed` for "now" values | Results do not depend on when the test runs |

Example in a **JUnit 5 test method** (assuming `source` is a valid `ZonedDateTime` and `targetZone` is a provided `ZoneId`):

```java
ZonedDateTime converted = source.withZoneSameInstant(targetZone);

assertEquals(source.toInstant(), converted.toInstant());
assertTrue(source.isEqual(converted));
assertEquals(targetZone, converted.getZone());
```

This snippet requires `import java.time.*;` and `import static org.junit.jupiter.api.Assertions.*;`, and runs inside a JUnit test; **it is not a standalone `main` program**. For the requirement "do not mutate the original object", a test can save `source` and verify its value is unchanged after the call.

## 13. Decision Flow for Choosing the Right API

1. **Do you already have an actual instant (`Instant` or `ZonedDateTime`) and need to display it in another zone?** Use `instant.atZone(zone)` or `zonedDateTime.withZoneSameInstant(zone)`.
2. **Do you want to keep the same calendar/wall-clock time when changing locations?** Work with `LocalDateTime` and the target `ZoneId`; consider `withZoneSameLocal` only when you clearly understand its DST handling rules.
3. **Do you want to convert a time to UTC without changing the instant?** Use `withZoneSameInstant(ZoneOffset.UTC)` or `toInstant()` if you only need the absolute timestamp.
4. **Do you want to preserve the intent "09:00 every day in a city"?** Store `LocalTime` along with the recurrence rule and `ZoneId`, then resolve each occurrence.
5. **Do you need to measure the actual elapsed time between two events?** Obtain two `Instant`s and use `Duration.between(start, end)`; avoid subtracting local times from two different zones.

**Remember:** `withZoneSameInstant()` **changes the displayed time zone without changing the actual instant**. Verify this with `source.toInstant().equals(converted.toInstant())`. If your problem requires preserving the local date-time digits rather than preserving an event, that is a different problem requiring `LocalDateTime`/`withZoneSameLocal` and an explicit DST policy.
