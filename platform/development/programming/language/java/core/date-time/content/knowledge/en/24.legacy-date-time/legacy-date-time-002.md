# Date Mutability and Deprecated Methods

## 1. A Date-Time Object Can Be Modified from Elsewhere

`java.util.Date` represents an instant with millisecond precision, but unlike `Instant`, its value **can be modified after creation**. `setTime(long)` makes that same object represent a different instant.

If multiple places hold the same reference, a mutating call in one place can cause another place to observe an unexpected time change. The bug does not require multiple threads: a single sequence of calls on one thread can expose the shared-state problem.

Illustrative example:

```java
Date first = Date.from(Instant.parse("2026-10-25T10:00:00Z"));
Date second = first;
second.setTime(0L);
```

`first` and `second` are not two date-time copies. After the last call, both observe the object holding the epoch value. Renaming a variable or marking one variable as `final` does not create a copy of the data.

In new code, immutable types generally help reduce state-management responsibility. However, when working with legacy libraries, it is necessary to understand both the mutability of `Date` and the deprecated parts of the API so as not to accidentally alter behavior.

## 2. `final` Only Fixes the Reference, Not the Object

The following snippet is valid:

```java
final Date timestamp = Date.from(
        Instant.parse("2026-10-25T10:00:00Z"));
timestamp.setTime(0L);
```

`final` forbids reassigning `timestamp = new Date(...)` later; it does not forbid modifying the object the variable points to. A `private final Date` field in a class is therefore not enough to make the class immutable.

Distinguish between:

| Situation | What is changing |
|---|---|
| `b = a` with two `Date` variables | The reference is copied; both variables point to the same object |
| `b.setTime(...)` | The internal value of the shared object |
| `b = new Date(...)` | Variable `b` points to another object; the old object does not change on its own |
| `new Date(a.getTime())` | Creates a new plain `Date` with the same millisecond value |

When investigating bugs, ask "who owns this object and who has the right to modify it", rather than looking only at the value at initialization.

## 3. Encapsulating State with Defensive Copying

A legacy class can be affected from two directions:

### Input Reference Retained Directly

If the constructor assigns `this.timestamp = input` directly, the caller still holds `input` and can call `setTime` after the owning object has been created.

The solution for a plain `Date` is to store a copy:

```java
this.timestamp = new Date(input.getTime());
```

### Getter Returning the Internal Reference Directly

If the getter returns `this.timestamp`, the caller can mutate it even if the class does not expose a setter. An independent copy must be returned when the API contract still requires `Date`:

```java
return new Date(timestamp.getTime());
```

Copying on only one side does not seal both mutation paths. The program in Section 7 demonstrates both mutating the input after the constructor and mutating the returned value after the getter.

The statements above apply to **plain `java.util.Date` values at millisecond precision**. If the input is a subtype such as `java.sql.Timestamp`, recreating a `Date` from `getTime()` does not preserve all information/characteristics of the subtype, such as the separate nanosecond part. You must identify the type and contract at the boundary instead of applying one copy function to every subclass.

`clone()` also exists, but a clone does not by itself explain the contract regarding subtypes or ownership. In an example studying plain `Date`, recreating from the millisecond value makes it clear which data is being retained.

## 4. Impact on Collections and Multithreading

The time value participates in `Date`'s `equals`, `hashCode`, and comparison order. If an object currently used as a key in a `HashMap` or as an element in a hash/order-based set is mutated, the structure already indexed by the old value may no longer reflect the new value.

Do not rely on an accidental result of `contains` to conclude that mutating keys is safe. The contract requires keeping the key value stable while it resides in the structure, or using an immutable key such as `Instant` that matches the meaning of the data.

In multithreaded environments, `Date` has mutable state and does not itself provide a synchronization policy for the application. Defensive copying prevents callers from holding internal references, but does not by itself guarantee that a shared input object being concurrently modified is read as a consistent snapshot.

How to handle this depends on the ownership contract: do not share mutable objects, synchronize all related operations, or standardize on immutable types. Merely adding `final` to a field or copying before a single call is no substitute for determining who can mutate the source.

## 5. Deprecated `Date` APIs

Do not equate "Date is mutable" with "all methods that mutate Date are deprecated". For example, `setTime(long)` is still a supported method; the fact that it is not deprecated does not mean the object becomes immutable.

Legacy groups to recognize when reading code:

| Deprecated API group | Common misconception |
|---|---|
| Constructors `Date(int year, int month, int date, ...)` | Year uses an offset from 1900; month is 0-indexed |
| Constructor `Date(String)` and `Date.parse(String)` | Accepts strings using a legacy mechanism, not an explicit modern parsing contract |
| `getYear()` / `setYear(...)` | Uses year minus 1900, not the direct calendar year |
| `getMonth()` / `setMonth(...)` | Month 0–11 |
| `getDate()` / `setDate(...)` | Day of the month, not the full `Date` value |
| `getDay()` | Day of the week with legacy convention, not ISO `DayOfWeek` |
| `getHours/getMinutes/getSeconds` and corresponding setters | Legacy calendar fields in a time-zone context |
| `toGMTString()`, `toLocaleString()`, `Date.UTC(...)` | Legacy formatting or time-creation APIs that have been replaced |

Components may also be normalized instead of rejecting every out-of-range value the way a reader might expect. For instance, a day exceeding the number of days in a month does not necessarily fail validation like a `STRICT` parser.

Deprecated means the API is not recommended for new usage and has a replacement direction; it does not automatically mean the call has been removed or always throws an error. When reading legacy code, understand the current behavior before changing it, because a stricter-validating replacement may intentionally change inputs that were previously accepted.

### APIs Not in the Deprecated Group Above

`Date()` for the current instant, `Date(long)` taking epoch milliseconds, `getTime()`, `setTime(long)`, `before`, `after`, `compareTo`, `Date.from(Instant)`, and `toInstant()` on a plain `Date` can still be used when interfacing with legacy APIs.

The `java.util.Date` class is not deprecated as a whole. Check the exact signature flagged with a warning, rather than bulk-replacing every occurrence of `Date` based solely on the class name.

## 6. Replacing APIs According to Operation Semantics

| Goal | Usually appropriate modern choice |
|---|---|
| Store an instant | `Instant` |
| Extract the date part in a zone | `instant.atZone(zone).toLocalDate()` |
| Create a date without a time | `LocalDate.of(year, month, day)` |
| Parse or format strings | `DateTimeFormatter` with explicit pattern/locale/policy |
| Adjust a calendar date | Operations on `LocalDate` or an appropriate `TemporalAdjuster` |

Do not simply replace `setDate(getDate() + 1)` with adding 86,400,000 milliseconds and assume it is equivalent to a calendar day in every time zone. An amount of 24 hours and a calendar day can differ when a zone has a DST transition.

Nor should you read the year via `getYear()` and pass it directly as the year in `LocalDate`. Legacy conventions must be converted properly; it is better to convert a plain `Date` to `Instant`, choose the required time zone, and then extract fields via a semantically clear API.

Choosing immutable `Instant` has an important consequence: `plusSeconds(...)` returns a new value and does not modify the original object. If you need to update a field in a class, you assign a new value according to the class contract, rather than accidentally mutating a shared object.

## 7. Complete Runnable Program

Save the following code to `MutableDateDemo.java`. The program uses Java 17 or later and requires no external libraries. It uses plain `Date` and does not rely on the default time zone to produce stdout.

```java
import java.time.Instant;
import java.util.Date;
import java.util.Objects;

public class MutableDateDemo {
    static final class LegacySnapshot {
        private final Date timestamp;

        LegacySnapshot(Date timestamp) {
            Objects.requireNonNull(timestamp);
            this.timestamp = new Date(timestamp.getTime());
        }

        Date timestamp() {
            return new Date(timestamp.getTime());
        }
    }

    public static void main(String[] args) {
        Instant originalInstant = Instant.parse("2026-10-25T10:00:00Z");
        final Date original = Date.from(originalInstant);
        Date alias = original;
        Date copy = new Date(original.getTime());
        LegacySnapshot snapshot = new LegacySnapshot(original);

        System.out.println("before=" + original.toInstant());
        alias.setTime(originalInstant.plusSeconds(3600).toEpochMilli());
        System.out.println("originalAfter=" + original.toInstant());
        System.out.println("aliasAfter=" + alias.toInstant());
        System.out.println("copyAfter=" + copy.toInstant());
        System.out.println("snapshotAfterInputChange="
                + snapshot.timestamp().toInstant());

        Date returned = snapshot.timestamp();
        returned.setTime(0L);
        System.out.println("returnedAfterChange=" + returned.toInstant());
        System.out.println("snapshotAfterOutputChange="
                + snapshot.timestamp().toInstant());

        Instant immutable = copy.toInstant();
        Instant later = immutable.plusSeconds(3600);
        System.out.println("immutableOriginal=" + immutable);
        System.out.println("immutableLater=" + later);
        System.out.println("sameStoredValue="
                + copy.equals(snapshot.timestamp()));
    }
}
```

Compile and run:

```shell
javac MutableDateDemo.java
java MutableDateDemo
```

Expected output:

```text
before=2026-10-25T10:00:00Z
originalAfter=2026-10-25T11:00:00Z
aliasAfter=2026-10-25T11:00:00Z
copyAfter=2026-10-25T10:00:00Z
snapshotAfterInputChange=2026-10-25T10:00:00Z
returnedAfterChange=1970-01-01T00:00:00Z
snapshotAfterOutputChange=2026-10-25T10:00:00Z
immutableOriginal=2026-10-25T10:00:00Z
immutableLater=2026-10-25T11:00:00Z
sameStoredValue=true
```

Explanation:

- `original` is declared `final`, yet it still changes from 10:00 to 11:00 through `alias`.
- `copy` has the same initial value as `original` but is an independent object.
- `LegacySnapshot` is not modified along with the input because it made a copy on receipt.
- The `Date` value obtained from the getter can be mutated, but it does not change `snapshot` because the getter returns a copy.
- `Instant.plusSeconds` creates a new value `later`; the original `immutable` value remains unchanged.

The program intentionally avoids deprecated methods to prove mutability. The supported `setTime` alone is enough to cause mutation, so eliminating deprecation warnings does not by itself solve the shared-state issue.

## 8. Reading and Modifying Legacy Code in a Controlled Manner

When encountering `Date` in a class, determine in order:

1. Is this a plain `java.util.Date` or a subtype with its own contract?
2. Is the value truly an instant, or is the system using it to simulate a civil date?
3. Does any constructor/getter retain or return a mutable reference directly?
4. Are there deprecated methods using year/month under legacy conventions?
5. Which default time zone or normalization mechanism do the transformations rely on?
6. Does switching to a new type preserve the exact precision and allowed inputs?

The compiler can help find deprecated calls via `-Xlint:deprecation` when compiling files containing those calls. Warnings are places to inspect, not an automatic solution for the business contract.

Do not merely add `@SuppressWarnings("deprecation")` and consider the issue handled. If the legacy API must be kept due to compatibility constraints, document the boundary clearly and convert appropriately; for new processing paths, choose types according to their actual semantics.

When testing modifications, test mutating the input after the constructor, mutating the value returned from the getter, verify the chosen time zone, and check boundary conditions that were normalized in the old code. A correct result on an ordinary day is not enough to prove that the API replacement preserves all behavior.

## 9. Self-Practice

1. In the example, temporarily remove the copy in the `LegacySnapshot` constructor. Observe `snapshotAfterInputChange` changing along with `original`, then restore the copy.
2. Temporarily make the getter return `timestamp` directly. Observe that mutating `returned` changes `snapshot`; identify why copying the input does not prevent this mutation path.
3. Replace the internal field with `Instant` in a new version of the class, converting plain `Date` at the input/output boundary. Explain why an immutable source avoids internal shared mutation, while compatibility requirements at the boundary must still be handled properly.
4. Given a legacy snippet using `getMonth() == 0`, state its meaning as January before replacing it with `Month.JANUARY`; do not turn it into a month `0` comparison in the new API.

References: [java.util.Date — setTime and list of deprecated methods](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Date.html) and [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) in Java SE 21.
