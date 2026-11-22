# Why Must You Capture the Result of a Transformation in `java.time`?

In Java, a call like `date.plusDays(1)` looks like an operation that "adds one day to the variable `date`". However, the core date-time types of the modern `java.time` API such as `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime`, and `ZonedDateTime` are **immutable**: once an object is created, the date-time state of that object itself cannot be modified.

Therefore, a transformation **returns a result value**. If the call is made and the program does not use the return value, the intended change is discarded.

~~~java
LocalDate date = LocalDate.of(2026, 1, 31);

date.plusDays(1);                  // Computes 2026-02-01, but discards the result.
System.out.println(date);          // 2026-01-31

date = date.plusDays(1);           // Reassigns the result.
System.out.println(date);          // 2026-02-01
~~~

The snippet above is an example placed inside a method with `import java.time.LocalDate;`. This is one of the most important rules when working with Java date-time: **calling a transformation and updating a variable are two separate actions**.

## 1. What Does an Immutable Object Mean?

Suppose:

~~~java
LocalDate original = LocalDate.of(2026, 1, 31);
LocalDate tomorrow = original.plusDays(1);
~~~

You can visualize this as:

~~~text
original ──────> LocalDate(2026-01-31)
                         |
                  plusDays(1)
                         |
                         v
tomorrow ───────> LocalDate(2026-02-01)

original still references 2026-01-31.
~~~

`plusDays(1)` computes the new date and returns a `LocalDate` representing that date. `original` itself does not change. If you write `original = original.plusDays(1)`, Java **reassigns the reference variable** `original` so that it points to the new date value; Java does not mutate the state of the old date object.

Distinguish three concepts:

| Action | Example | Result |
| --- | --- | --- |
| Create an immutable value | `LocalDate.of(2026, 1, 31)` | Obtain an object representing 2026-01-31 |
| Transform a value | `date.plusDays(1)` | Returns a `LocalDate` representing 2026-02-01; does not modify `date` |
| Assign a variable | `date = date.plusDays(1)` | Replaces the reference stored in the `date` variable with the result |

The phrase "returns a new object" in common phrasing means **returns a result value**, not a guarantee that the JVM always allocates a physically new object. For an operation that does not change the value, such as `plusDays(0)`, the implementation may return the same existing object. Do not test date-time behavior using the `==` operator (reference identity); use `equals()` to compare values, or `isBefore()`, `isAfter()`, `isEqual()` according to the semantics of the corresponding temporal type.

## 2. Why Did the API Choose an Immutable Design?

A date-time is a **value**. If a method accidentally modified a date while multiple places were referencing the same object, calendar calculations, comparisons, and displays could change unexpectedly.

An immutable design has practical benefits:

1. **Predictable:** calling addition/subtraction on a value does not alter the original data; you can keep both before and after for comparison.
2. **Safer sharing:** multiple functions or threads can read the same immutable date-time object without locking just to prevent mutating that value itself.
3. **Easier testing and debugging:** inputs are not silently modified by helper methods; transformations are expressed through return values.
4. **Easy to chain operations:** you can write `date.plusDays(1).withDayOfMonth(1)` and obtain a clear final value.

This does not mean **every construct in the time ecosystem is immutable**. For example, `java.time.format.DateTimeFormatterBuilder` is a mutable builder while constructing a formatter. The rule in this lesson applies to the **date-time value types** mentioned above. For comparison, the legacy `java.util.Date` and `java.util.Calendar` APIs have methods that mutate object state.

## 3. How to Use the Result: Reassign, New Variable, or Return

### Approach A: Reassign the variable when advancing computation state

~~~java
LocalDate dueDate = LocalDate.of(2026, 1, 31);
dueDate = dueDate.plusDays(1);
dueDate = dueDate.plusWeeks(2);
~~~

After two transformations, `dueDate` holds the **final result**. No object is modified in place; only the variable `dueDate` is reassigned twice.

This approach fits when the program has a "current date being processed" variable, such as in a loop:

~~~java
LocalDate cursor = LocalDate.of(2026, 1, 1);
for (int i = 0; i < 3; i++) {
    System.out.println(cursor);
    cursor = cursor.plusDays(1); // Without reassigning, it prints the same date.
}
~~~

### Approach B: Keep the original and use a new result variable

~~~java
LocalDate bookingDate = LocalDate.of(2026, 1, 31);
LocalDate checkoutDate = bookingDate.plusDays(3);
~~~

If business logic needs to keep both the booking date and the checkout date, leave `bookingDate` unchanged and use `checkoutDate`. This is often clearer than repeatedly reassigning a single variable.

### Approach C: Return the result from a method

~~~java
static LocalDate extendDeadline(LocalDate current, int days) {
    return current.plusDays(days);
}
~~~

The method does not modify the object provided by the caller. **The caller must use the return value**:

~~~java
LocalDate deadline = LocalDate.of(2026, 1, 31);
deadline = extendDeadline(deadline, 3);
~~~

If you only call `extendDeadline(deadline, 3);` and discard the result, the caller's variable still holds the old date.

### Approach D: Use the result in a transformation chain

~~~java
LocalDate firstMonday = LocalDate.of(2026, 1, 15)
        .plusMonths(1)
        .withDayOfMonth(1)
        .with(java.time.temporal.TemporalAdjusters.nextOrSame(
                java.time.DayOfWeek.MONDAY));
~~~

Each call returns a value for the next call to transform further; the final result is assigned to `firstMonday`. This snippet illustrates method chaining in Java 17+, not a standalone program.

**Note on `final`:** declaring `final LocalDate date = ...;` prevents you from reassigning the `date` variable, but does not prevent calling `date.plusDays(1)`. When a variable is `final`, store the result under a different variable name. `final` is a constraint on the **reference variable**, whereas immutability is a property of the **object**.

## 4. Run a Java 17+ Program and Inspect the Output

Create a file `ImmutableDateTimeDemo.java` with the following content:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;

public class ImmutableDateTimeDemo {
    public static void main(String[] args) {
        LocalDate payday = LocalDate.of(2026, 1, 31);

        // Valid call, but the result is discarded.
        payday.plusDays(1);
        System.out.println("no assignment = " + payday);

        // Capture the result in another variable.
        LocalDate nextDay = payday.plusDays(1);
        System.out.println("captured = " + nextDay);
        System.out.println("source = " + payday);

        // Reassign the variable (does not mutate the old object).
        payday = payday.plusMonths(1);
        System.out.println("reassigned = " + payday);

        // with(...) must also capture the result.
        LocalDate monday = nextDay.with(
                TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
        System.out.println("monday = " + monday);

        LocalDateTime meeting =
                LocalDateTime.of(2026, 1, 31, 23, 30);
        meeting.plusHours(2);
        System.out.println("meeting unchanged = " + meeting);
        meeting = meeting.plusHours(2);
        System.out.println("meeting updated = " + meeting);

        // Reassigning a parameter does not update the caller's variable.
        LocalDate birthday = LocalDate.of(2026, 1, 15);
        shiftIgnored(birthday);
        System.out.println("after void call = " + birthday);
        birthday = shiftReturned(birthday);
        System.out.println("after return = " + birthday);
    }

    private static void shiftIgnored(LocalDate input) {
        input = input.plusDays(1);
    }

    private static LocalDate shiftReturned(LocalDate input) {
        return input.plusDays(1);
    }
}
~~~

Compile and run:

~~~bash
javac ImmutableDateTimeDemo.java
java ImmutableDateTimeDemo
~~~

Output:

~~~text
no assignment = 2026-01-31
captured = 2026-02-01
source = 2026-01-31
reassigned = 2026-02-28
monday = 2026-02-02
meeting unchanged = 2026-01-31T23:30
meeting updated = 2026-02-01T01:30
after void call = 2026-01-15
after return = 2026-01-16
~~~

Key observations:

- The **`no assignment`** line shows that `plusDays(1)` was executed, yet `payday` still holds 2026-01-31.
- The **`captured`** line is the new date value; the **`source`** line confirms the original value did not change.
- `plusMonths(1)` goes from 2026-01-31 to **2026-02-28**: the result can be **adjusted to the last valid day of the month** according to API rules, rather than trying to keep a non-existent day 31.
- `with(TemporalAdjusters.nextOrSame(...))` is another transformation that returns the matching date: 2026-02-02.
- `LocalDateTime.plusHours(2)` adds across midnight, but `meeting` only holds the new date-time **after reassignment**.
- `shiftIgnored` reassigns the **local parameter** variable. Java passes the value of the reference into the method; reassigning `input` does not update the `birthday` variable at the call site. The right way is to `return` the new value and capture the result in the caller's variable.

The date and time calculation results above have been verified with Java. The code does not depend on system time, default time zone, or current data, so it can be re-run and compared against stdout.

## 5. Which Transformations Require Capturing the Return Value?

Do not memorize only `plusDays()`. For immutable date-time objects, many common methods follow this principle:

| Operation group | Example | Result that must be used |
| --- | --- | --- |
| Add time | `date.plusDays(2)`, `time.plusMinutes(15)` | Date/time after addition |
| Subtract time | `date.minusMonths(1)`, `instant.minusSeconds(10)` | Date/time after subtraction |
| Replace date-time field | `date.withYear(2027)`, `dateTime.withHour(9)` | Value with the new field |
| Adjust by rule | `date.with(TemporalAdjusters.next(DayOfWeek.MONDAY))` | Adjusted date |
| Truncate precision | `time.truncatedTo(ChronoUnit.MINUTES)` | Time with seconds/nanoseconds truncated |
| Apply time zone | `localDateTime.atZone(zone)` | `ZonedDateTime` |
| Convert time zone | `zoned.withZoneSameInstant(otherZone)` | `ZonedDateTime` in another zone, same instant |
| Convert to instant | `zoned.toInstant()` | An `Instant` |
| Format | `date.format(formatter)` | A `String` |

The last two rows show that some operations **return a different data type**. You cannot assign `ZonedDateTime.toInstant()` back to the same `ZonedDateTime` variable; instead, declare `Instant timestamp = zoned.toInstant();`. Similarly, `date.format(formatter)` produces a **string** without modifying `date` or the input formatter variable.

**Do not confuse transformations with query/observation methods.** Methods such as `getYear()`, `getMonthValue()`, `isBefore()`, and `equals()` only read or compare and return a number/boolean; there is no new date-time object to capture. The point is not that "every method must be reassigned", but that **when you want to use the computed result, you must use the returned value**.

## 6. Time Zone Conversion Is an Error-Prone Example

Even when you only want to change how a value is displayed in another zone, the object does not mutate itself:

~~~java
ZonedDateTime inUtc =
        ZonedDateTime.parse("2026-01-15T09:00:00Z[UTC]");

inUtc.withZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"));
// inUtc still represents 09:00 in UTC.

ZonedDateTime inVietnam =
        inUtc.withZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"));
// inVietnam represents 16:00 in Asia/Ho_Chi_Minh.
// inUtc still represents 09:00 in UTC.
~~~

This snippet is intended to be placed inside a method with `import java.time.ZonedDateTime;` and `import java.time.ZoneId;`. `withZoneSameInstant` **preserves the instant** and changes the zone for display; the result must be captured in `inVietnam` or reassigned if the variable allows it.

Note the distinction with `withZoneSameLocal`: that method tries to **preserve the local wall-clock time**, so it usually **changes the instant** and may have to resolve gaps/overlaps in the new zone. Whichever operation you choose, capturing the result is still required if you want to use the transformation.

## 7. Common Mistakes in Methods, Collections, and Loops

### Wrong: assuming a method has a side effect on the input object

~~~java
void moveBooking(LocalDate bookedDate) {
    bookedDate.plusDays(3); // Result is discarded; caller does not see the new date.
}
~~~

If the method needs to return the shifted date, the signature should state it clearly:

~~~java
LocalDate moveBooking(LocalDate bookedDate) {
    return bookedDate.plusDays(3);
}
~~~

If the design stores a date inside an entity with a setter, you must **capture the new value and assign it to the entity's property**. For example, `booking.setDate(booking.getDate().plusDays(3))` updates the **mutable entity**, while still not mutating the old `LocalDate` object. These are two different layers of state.

### Wrong: using `forEach` and discarding transformations

~~~java
List<LocalDate> dates = List.of(
        LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 1, 2));

dates.forEach(d -> d.plusDays(1)); // Does not produce a result list.

List<LocalDate> nextDates = dates.stream()
        .map(d -> d.plusDays(1))
        .toList(); // [2026-01-02, 2026-01-03]
~~~

The snippet above goes inside a method and requires `import java.util.List;` and `import java.time.LocalDate;`. `map` takes the lambda's return value to build a new list; `dates` does not change. `Stream.toList()` is available from Java 16 and the result is a list that does not support structural or element modifications.

If you actually want to **replace element references in a modifiable `List`**, `replaceAll(d -> d.plusDays(1))` updates the list. It does not make `LocalDate` mutable. With `List.of(...)`, do not use `replaceAll` to replace elements because that list does not allow modifications.

### Wrong: a date loop that does not advance

~~~java
LocalDate day = LocalDate.of(2026, 1, 1);
while (day.isBefore(LocalDate.of(2026, 1, 5))) {
    // Process day...
    day.plusDays(1); // day does not advance: risk of an infinite loop.
}
~~~

You need to write `day = day.plusDays(1)`. For a bounded loop, also check the termination condition and valid date range.

## 8. Checklist When Reviewing or Editing `java.time` Code

1. **Do you want the value after transformation?** Check whether calls to `plus...`, `minus...`, `with...`, `truncatedTo`, `atZone`, `withZoneSameInstant` are assigned, returned, passed along, or chained.
2. **Do you want to keep the original date?** Use a new variable, e.g., `LocalDate next = start.plusDays(1)`, and keep `start` for later calculations.
3. **Is `final` used?** You cannot reassign a `final` variable; capture the result under a different variable name.
4. **Inside a method?** Reassigning a parameter only changes the local reference; you must return the result or update the state holder according to the API contract.
5. **Processing a List/Stream?** `forEach` discards results and does not transform elements. Use `map` to create a new list of values or `replaceAll` when the list allows modification.
6. **Crossing month-end/year-end/DST?** Check the **actual return value**; besides having to assign the result, transformations also follow date-time and time zone rules.
7. **Using `==` to test variables?** For date-time values, prefer `equals`/temporal comparison methods; do not rely on whether the API allocates a new object or returns an existing one.
8. **Do tests cover the discarded-result case?** Verify both the initial value and the value after assignment; this is the shortest way to demonstrate the difference between transformation and mutation.

### Self-Check Questions

- Does calling `date.plusDays(7);` change `date`? **No.** The return value is not used.
- Does calling `date = date.plusDays(7);` mutate the old date object? **No.** The variable `date` is assigned a reference to the new value.
- Given `LocalDate a = date; LocalDate b = a.plusDays(1);`, does `date` change? **No.** `a` and `date` still reference the original value.
- Inside a `void` method, does reassigning a `LocalDate` parameter update the caller's variable? **No.** You must return the result or modify the state of a container object (if the contract allows it).
- Must `date.plusDays(0)` return a different reference from `date`? **No.** Care about the value, not object identity.
- Does `date.format(formatter)` modify `date`? **No.** It returns a `String`.

**Takeaway:** Java's modern date-time value types are designed to be immutable. Calls like `plusDays()`, `minusHours()`, `with...`, and `withZoneSameInstant()` are **computations that produce a result**. Only when you **reassign, pass along, return, or use the result** will the program observe the intended transformation.