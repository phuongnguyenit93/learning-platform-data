# Sorting Date-Times and Choosing a Comparator by Intended Semantics

## Goal

In Java, "sorting date-times" can mean several different things: by calendar date and wall-clock time, by actual instant on the timeline, by offset, or by a secondary business key. Choosing the wrong comparison order can produce schedules or reports that look plausible but are wrong in real time.

This lesson explains the natural ordering of `java.time` types, how to build a `Comparator`, how to handle `null` values, secondary criteria, reversed ordering, and the right choices for data without a time zone or with an offset/zone. Examples use Java 17+.

## 1. First, define what "correct order" means

| Data type | Business question | Usually appropriate comparison |
|---|---|---|
| `LocalDate` | Which calendar date comes first? | Natural order of dates |
| `LocalDateTime` | Which local wall-clock date-time comes first? | Natural order of local date-times |
| `Instant` | Which event occurred earlier on the timeline? | Natural order of `Instant` |
| `OffsetDateTime` | Compare the actual timestamp or also the offset representation? | Compare `toInstant()` if timeline order is needed; natural order if the type's own rules are needed |
| `ZonedDateTime` | Which event occurred earlier, or is the time zone also significant? | Compare `toInstant()` for timeline order; add a secondary key if representations must be distinguished |
| Appointment object | Sort by instant, then by priority or code? | `Comparator.comparing(...).thenComparing(...)` |

Before writing a comparator, answer three questions:

1. Does the data already represent an absolute instant? `Instant`, `OffsetDateTime`, and `ZonedDateTime` identify an instant; `LocalDateTime` does not.
2. When two values represent the same instant with different offsets/zones, should the business logic treat them as equivalent?
3. If the times are equal, what secondary criterion is needed to produce a stable and meaningful order?

## 2. Natural ordering of `java.time` types

Common date-time types all support natural comparison, but their semantics differ.

### `LocalDate` and `LocalDateTime`

`LocalDate` compares year, month, and then day in the ISO calendar. `LocalDateTime` compares local components from date down to nanoseconds. Neither type has an offset or zone, so a UTC instant cannot be inferred from the value alone.

```java
LocalDate firstDay = LocalDate.parse("2025-02-01");
LocalDate secondDay = LocalDate.parse("2025-01-31");

System.out.println(firstDay.compareTo(secondDay) > 0);
```

Output:

```text
true
```

`LocalDateTime` can sort wall-clock times within the same local calendar. However, if values come from multiple time zones, comparing local fields directly does not give the actual event order. For example, 09:00 in Tokyo and 08:00 in New York cannot be globally ordered using only two local date-times when the associated zones/offsets are missing.

### `Instant`

`Instant` is the most natural choice for real-time ordering. `compareTo()` and natural sorting compare points on the timeline, regardless of which time zone a user views them in.

```java
Instant a = Instant.parse("2025-01-15T03:30:00Z");
Instant b = Instant.parse("2025-01-15T04:00:00Z");

System.out.println(a.isBefore(b));
```

Output:

```text
true
```

### `OffsetDateTime` and `ZonedDateTime`

Both types contain enough information to determine an `Instant`, while also carrying local representation, offset, or zone data. Their natural ordering should not be conflated with the assumption that they "always just compare wall-clock time". If the business logic cares only about which event occurred before or after another, express that explicitly with a comparator based on `toInstant()`.

The following two values represent the same instant:

```text
2025-01-15T10:30+07:00
2025-01-15T03:30Z
```

They differ in representation, but their `toInstant()` values are identical. A timeline comparator treats their time keys as equal; when a total order over representations is needed, add a secondary criterion.

## 3. Timeline-order Comparator

If the input is already `OffsetDateTime` or `ZonedDateTime`, use `toInstant()` as the time key:

```java
Comparator<OffsetDateTime> timelineOrder =
        Comparator.comparing(OffsetDateTime::toInstant);
```

For `ZonedDateTime`:

```java
Comparator<ZonedDateTime> timelineOrder =
        Comparator.comparing(ZonedDateTime::toInstant);
```

This expresses the exact intent: comparing **absolute instants**. If you simply sort `OffsetDateTime` / `ZonedDateTime` using natural order, the result still follows each type's `Comparable` contract, which may use secondary representation details when two inputs share the same instant. A dedicated timeline comparator tells readers of the code precisely what a tie means.

If two events share the same timestamp and need a deterministic order, add a secondary key such as ID:

```java
Comparator<Event> order = Comparator
        .comparing(Event::occurredAt)
        .thenComparing(Event::id);
```

This assumes `occurredAt` returns an `Instant` and `id` has a natural order. When timestamps match, the ID determines the remaining order.

## 4. Building Comparators with `comparing()` and `thenComparing()`

`Comparator.comparing(keyExtractor)` creates a comparator from a comparable key. `thenComparing` uses the next key only when preceding keys are equal.

For example, sorting appointments by time and then by title:

```java
Comparator<Appointment> order = Comparator
        .comparing(Appointment::start)
        .thenComparing(Appointment::title);
```

For this comparator to be valid and well-behaved, the getters should return non-null values, or you must specify a null-handling policy. If `start` is an `Instant`, the primary key is timeline order. If `start` is a `LocalDateTime`, it is local wall-clock order.

Secondary criteria should reflect business requirements. Do not add unrelated fields just to "make the comparator more thorough". A criterion like ID is often useful when reproducible output is needed if multiple events occur at the same time.

## 5. Complete Java example: sorting appointments by `Instant`, then ID

Create `AppointmentSortingDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class AppointmentSortingDemo {
    record Appointment(String id, String title, Instant start) {}

    public static void main(String[] args) {
        List<Appointment> appointments = new ArrayList<>(List.of(
                new Appointment("A3", "Review", Instant.parse("2025-01-15T04:00:00Z")),
                new Appointment("A2", "Planning", Instant.parse("2025-01-15T03:30:00Z")),
                new Appointment("A1", "Stand-up", Instant.parse("2025-01-15T03:30:00Z"))
        ));

        Comparator<Appointment> order = Comparator
                .comparing(Appointment::start)
                .thenComparing(Appointment::id);

        appointments.sort(order);

        for (Appointment appointment : appointments) {
            System.out.println(appointment.id() + " | "
                    + appointment.start() + " | " + appointment.title());
        }
    }
}
```

Compile and run with Java 17+:

```bash
javac AppointmentSortingDemo.java
java AppointmentSortingDemo
```

Output:

```text
A1 | 2025-01-15T03:30:00Z | Stand-up
A2 | 2025-01-15T03:30:00Z | Planning
A3 | 2025-01-15T04:00:00Z | Review
```

Events A1 and A2 share the same instant; the secondary ID key places A1 before A2. `List.sort` sorts the list in place. If you do not want to mutate the original list, copy it first or use a stream and collect the result into a new list.

## 6. Sorting `OffsetDateTime`: by timeline or by representation?

Suppose two timestamps are recorded with different offsets:

```java
OffsetDateTime tokyo =
        OffsetDateTime.parse("2025-01-15T12:30+09:00");
OffsetDateTime utc =
        OffsetDateTime.parse("2025-01-15T03:30Z");

System.out.println(tokyo.toInstant().equals(utc.toInstant()));
System.out.println(Comparator.comparing(OffsetDateTime::toInstant)
        .compare(tokyo, utc));
```

Output:

```text
true
0
```

With the timeline comparator, they are equal because they have the same `Instant`. This is useful when sorting real-world events chronologically, even when offsets are stored differently.

If you need a unique order for each representation object, add explicit secondary keys such as local date-time and then offset:

```java
Comparator<OffsetDateTime> deterministicRepresentationOrder =
        Comparator.comparing(OffsetDateTime::toInstant)
                .thenComparing(OffsetDateTime::toLocalDateTime)
                .thenComparing(OffsetDateTime::getOffset);
```

Do not accidentally use representation order in place of timeline order. Name your comparators according to their semantics, such as `timelineOrder` or `representationOrder`, to prevent misuse elsewhere.

## 7. Sorting `LocalDateTime` vs. sorting `Instant`

`LocalDateTime` does not identify an actual instant because it lacks an offset/zone. If records come from a single region and need to be scheduled by local wall-clock time, sorting `LocalDateTime` directly is usually appropriate.

If the data contains events from multiple zones, convert them using the appropriate `ZoneId` to obtain an `Instant` before sorting on the timeline. Do not blindly attach `ZoneId.systemDefault()` to every local value if the actual source belongs to another zone.

This is especially important when DST creates nonexistent or repeated local times. A local value such as 01:30 in an overlap zone cannot uniquely determine timeline order without an offset or disambiguation choice. Before constructing a `ZonedDateTime`, a scheduling system may need to inspect `ZoneRules.getValidOffsets(local)` and apply an explicit policy.

## 8. Reversed ordering

`reversed()` creates a comparator with the reverse order. It can be used to put the newest events first:

```java
Comparator<Event> newestFirst =
        Comparator.comparing(Event::occurredAt).reversed();
```

If you need to keep a secondary criterion ascending while the time is descending, place `reversed()` on the exact comparator part that should be reversed. For example:

```java
Comparator<Event> newestThenId =
        Comparator.comparing(Event::occurredAt)
                .reversed()
                .thenComparing(Event::id);
```

Here, time is descending while ID is ascending for events with the same timestamp. If you wrote `Comparator.comparing(Event::occurredAt).thenComparing(Event::id).reversed()`, the entire composite comparator would be reversed, including the ID order. The placement of `reversed()` changes the meaning.

## 9. Explicit `null` handling

`Comparator.comparing` generally assumes the extracted key is comparable and non-null. If data may be missing a timestamp, explicitly declare whether it comes first or last:

```java
Comparator<Appointment> nullStartsLast = Comparator
        .comparing(
                Appointment::start,
                Comparator.nullsLast(Comparator.naturalOrder()))
        .thenComparing(Appointment::id);
```

This assumes the `start` getter can return a null `Instant`. `nullsLast` places records without a time at the end; `nullsFirst` does the opposite. If the object being sorted can itself be null, you need a null policy at the object level as well, such as `Comparator.nullsLast(order)`.

Do not replace `null` with `Instant.now()` just to avoid sorting errors. Doing so fabricates a timestamp, which can place records in the wrong position and make results non-reproducible. Depending on the business rules, reject the data, sort nulls according to a defined rule, or represent an "unscheduled" state separately.

## 10. Does `sort()` mutate the list or create a new one?

`List.sort(comparator)` sorts the existing list in place. If callers still hold a reference to that list, its element order changes. `Stream.sorted(comparator)` produces a sorted stream; it does not mutate the source by itself, while the final result depends on the terminal operation and collection type you create.

```java
List<Instant> source = List.of(
        Instant.parse("2025-01-15T04:00:00Z"),
        Instant.parse("2025-01-15T03:00:00Z"));

List<Instant> sorted = source.stream()
        .sorted()
        .toList();

System.out.println(source.get(0));
System.out.println(sorted.get(0));
```

Output:

```text
2025-01-15T04:00:00Z
2025-01-15T03:00:00Z
```

In Java 17, `Stream.toList()` returns an unmodifiable list. Therefore, if you need to sort the result further, create `new ArrayList<>(sorted)` before calling a mutating list method. With `Collections.sort(list, comparator)`, the source list is also sorted in place.

## 11. Comparators must be consistent

A `Comparator` should satisfy its contract: the sign of `compare(a, b)` must invert when the arguments are swapped; the relation must be transitive; if the comparator returns 0, comparisons with any third element must also agree. A comparator with arbitrary conditions or one that uses the current time as a key during comparison can violate stability and produce hard-to-explain results.

Do not create a comparator that uses values changing between calls, for example:

```java
// Bad design: "now" differs across calls.
Comparator<Event> unstable = Comparator.comparing(
        event -> Duration.between(event.occurredAt(), Instant.now()));
```

If you need to sort by event age at a reference point, capture that reference point once as an immutable key or compare the timestamps directly. A `now` that changes during sorting can make the comparison relation inconsistent.

Also avoid subtracting two timestamps or epoch millis to build a comparator via `(int) (a - b)`: subtraction can overflow, and casting to `int` loses most of the precision. Use `compareTo`, `Comparator.comparing`, or `Long.compare(a, b)`.

## 12. Comparator selection guide

| Goal | Approach |
|---|---|
| Calendar dates ascending | `Comparator.naturalOrder()` or `Comparator.comparing(Event::date)` |
| Local date-times ascending in the same context | `Comparator.comparing(Event::localDateTime)` |
| Global events by instant | `Comparator.comparing(Event::instant)` |
| `OffsetDateTime` / `ZonedDateTime` by timeline | `Comparator.comparing(value -> value.toInstant())` |
| Time first, ID ascending on ties | `comparing(time).thenComparing(id)` |
| Newest first | `comparing(time).reversed()` |
| Null times last | `Comparator.nullsLast(Comparator.naturalOrder())` as the key comparator |
| Keep original order intact | Use stream `sorted` or copy before sorting |
| Distinguish representations of the same `Instant` | Intentionally add local date-time/offset/zone as secondary keys |

## 13. Self-check

**Question 1.** How should two `OffsetDateTime` values with different offsets but the same `toInstant()` be ordered on the timeline?

**Answer:** A timeline comparator returns 0 for the time key. If the two representations must be distinguished, add a separate secondary key.

**Question 2.** Can `LocalDateTime` be used directly to sort events from all time zones around the world?

**Answer:** No. It holds only local wall-clock time and does not identify an `Instant`; the source zone or offset is needed to convert to timeline order before global sorting.

**Question 3.** Is placing `reversed()` after `thenComparing(id)` different from placing it before `thenComparing(id)`?

**Answer:** Yes. Reversing the entire comparator also reverses the secondary key's order; reversing only the time key and then chaining the secondary key keeps ID in ascending order.

**Question 4.** When a time field can be `null`, how do you explicitly place nulls last?

**Answer:** Use `Comparator.nullsLast(...)` as the key comparator, or wrap the entire comparator with `Comparator.nullsLast(order)` if the object itself can be null.

**Question 5.** Why should you avoid using `(int) (timeA - timeB)` as a comparator?

**Answer:** Subtraction can overflow, and casting to `int` loses data, violating the intended order. Use standard comparison APIs instead.

---

**Takeaway:** Correct sorting starts with choosing the right time semantics. Use local order for local schedules, timeline order for events with absolute instants, and explicit secondary criteria for ties, nulls, or deterministic ordering.
