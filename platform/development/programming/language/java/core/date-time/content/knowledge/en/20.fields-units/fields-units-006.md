# with() and plus() via the Temporal Interface

## 1. From Concrete Operations to a Shared Contract

A program may need to apply the same kind of operation to multiple date-time types: adding days to a `LocalDate`, adding hours to a `LocalTime`, or adjusting the day in a `LocalDateTime`. Writing every calculation using specific methods such as `plusDays` or `plusHours` is convenient when the type is already known, but it does not provide a common entry point for general-purpose processing utilities.

The `Temporal` interface in `java.time.temporal` provides a contract for reading and manipulating date-time values that have sufficient information. Its two core method groups are:

- `with(...)`: produces a result by **setting a field** or **applying an adjustment rule**.
- `plus(...)`: produces a result by **adding an amount in a unit** or **adding an object that describes an amount of time**.

For example, given the date `2024-02-20`, setting the day of month to 1 produces `2024-02-01`; adding one day produces `2024-02-21`. Both produce valid dates, but they answer two different requirements. This is the key distinction to understand before using the overloads.

`TemporalAccessor` is the read-only interface. `Temporal` extends it to add manipulation operations such as `with`, `plus`, `minus`, and `until`. Common types implementing `Temporal` include `LocalDate`, `LocalTime`, `LocalDateTime`, `YearMonth`, `Instant`, and offset/zoned types.

Not every type carrying date-time information implements `Temporal`. For instance, `MonthDay` has no year, so it lacks sufficient information to know how many days February has in all addition operations; it does not share the same addition/subtraction contract as `LocalDate`. See the model and scope of use in [Temporal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/Temporal.html).

## 2. Four Overloads to Distinguish

The signatures below are written using the return type visible from the `Temporal` interface:

| Signature | Parameter meaning | Example |
| --- | --- | --- |
| `Temporal with(TemporalField field, long newValue)` | Sets a field to a value | `value.with(DAY_OF_MONTH, 1)` |
| `Temporal with(TemporalAdjuster adjuster)` | Applies an adjustment rule | `value.with(lastDayOfMonth())` |
| `Temporal plus(long amount, TemporalUnit unit)` | Adds an amount in a unit | `value.plus(7, DAYS)` |
| `Temporal plus(TemporalAmount amount)` | Adds an amount encapsulated in an object | `value.plus(Period.ofDays(7))` |

In the examples, `DAY_OF_MONTH` is `ChronoField.DAY_OF_MONTH`, `DAYS` is `ChronoUnit.DAYS`, and `lastDayOfMonth()` comes from `TemporalAdjusters`.

Their roles must not be mixed up:

- `TemporalField` describes a component, such as the day of month.
- `TemporalAdjuster` encapsulates an algorithm for finding an adjusted result.
- `TemporalUnit` describes a unit, such as days or hours.
- `TemporalAmount` describes an amount, such as 7 days or 2 hours.

`ChronoUnit.DAYS` is only a unit, without an amount. `Period.ofDays(7)` already contains both the unit and the amount, so it can be used with the single-parameter overload of `plus`.

## 3. with(): Setting a Field or Applying a Rule

### 3.1. with(field, value) Replaces a Single Component

With `Temporal value = LocalDate.of(2024, 2, 20)`, the expression `value.with(ChronoField.DAY_OF_MONTH, 1)` produces February 1, 2024. The year and month parts are preserved according to the rules of this operation.

`with` does not mean "add". Setting the day to 1 is different from adding one day. Similarly, setting `MONTH_OF_YEAR` to 3 is different from adding three months.

The new value must be handled according to the contract of the field and the concrete type. For a date in February 2024, setting `DAY_OF_MONTH = 30` throws `DateTimeException`. Do not assume that every invalid value will be clamped back to a valid date; some operations have their own adjustment rules, while others reject the input.

### 3.2. with(adjuster) Applies an Adjustment Algorithm

"The last day of the month" is not a fixed value: it can be 28, 29, 30, or 31. `TemporalAdjusters.lastDayOfMonth()` encapsulates that rule. Using `value.with(adjuster)` allows the code to express the requirement without rewriting month-handling branches.

An adjuster takes a `Temporal` and produces a result. Mechanically, this overload delegates to `adjuster.adjustInto(value)`. Calling `value.with(adjuster)` is usually easier to read because the value being adjusted appears at the start of the expression. The contract is described at [TemporalAdjuster](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAdjuster.html).

An adjuster does not necessarily change only one field. It can combine multiple steps, such as "move to the first day of the month, then advance to the next month". Even so, it must have a clear scope of applicability; a rule that requires date fields cannot be applied to `LocalTime`.

## 4. plus(): The Amount and Unit Must Match the Data

### 4.1. plus(amount, unit)

`value.plus(7, ChronoUnit.DAYS)` asks the object to add 7 days according to that type's rules. For `LocalDate`, this corresponds to `plusDays(7)`.

Standard units are typically `ChronoUnit`. However, the interface accepts `TemporalUnit`, so it can accept other units if the type and unit work together to support them. For a custom unit, the temporal class may delegate processing to `unit.addTo(...)`; do not assume that every addition is implemented inside the `ChronoUnit` enum itself. See the mechanism at [TemporalUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalUnit.html).

Supporting an operation does not mean all types have the same storage semantics. Adding two hours to `LocalTime` at 23:30 produces 01:30; this type does not retain next-day information. If the requirement needs both date and time, choose a type that holds both components from the start.

### 4.2. plus(TemporalAmount)

Two common implementations of `TemporalAmount` are:

- `Period`: a calendar-based amount consisting of years, months, and days.
- `Duration`: a time-based amount storing seconds and nanoseconds.

This overload delegates to `amount.addTo(value)`. The amount object decides how to add its components; it is not a scalar number usable on every type. See the contract in [TemporalAmount](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalAmount.html).

For `LocalDate`, `plus(Period.ofDays(7))` can add 7 days. However, `plus(Duration.ofDays(1))` reports unsupported: that `Duration` amount is represented in seconds, and `LocalDate` does not support adding seconds. Having the word "Days" in the factory method name is not enough to conclude that it is compatible with a calendar date.

For `LocalDateTime`, adding `Duration.ofHours(2)` is valid because the type has a time part. For zoned data, choosing between a calendar-based amount and a time-based amount can also affect the result when the UTC offset changes; do not assume a calendar day is always equivalent to 24 hours in every context.

## 5. Calling Through the Interface Still Runs the Concrete Object's Behavior

Consider the following illustration inside a Java method:

```java
LocalDate concrete = LocalDate.of(2024, 2, 20);
Temporal general = concrete;

LocalDate a = concrete.plus(1, ChronoUnit.DAYS);
Temporal b = general.plus(1, ChronoUnit.DAYS);
```

Both `a` and `b` hold the date `2024-02-21`. In this case, the actual runtime result object of both is still `LocalDate`.

The difference lies in the static type of the expression:

- From the `LocalDate` variable, the compiler sees the overload declared by the concrete class with return type `LocalDate`.
- From the `Temporal` variable, the compiler only guarantees that the result is a `Temporal`.

Therefore, you cannot assign `general.plus(1, DAYS)` directly to a `LocalDate` variable just because you know the runtime input object is a `LocalDate`. Similarly, a `Temporal` variable does not have convenience methods like `plusDays` or `getYear` in its contract.

If the business domain is definitely an ISO date, you can keep the concrete type from the start. When receiving a general result and genuinely needing to convert it to a date, `LocalDate.from(result)` expresses an explicit extraction/conversion. However, this conversion also accepts some other types that carry date information, such as `LocalDateTime`, and discards the time part. Do not use it to mask a flawed type design or as a substitute for verifying that the actual result type matches what was promised.

Using the interface does not give an object extra capabilities: a `LocalDate` referenced through `Temporal` still has no time part and cannot add `HOURS`.

## 6. Immutability, Return Types, and Retaining Results

The standard `java.time` types in use, such as `LocalDate`, `LocalTime`, and `LocalDateTime`, are immutable. They are not modified after a `with` or `plus` call.

The following illustration discards the result:

```java
Temporal value = LocalDate.of(2024, 2, 20);
value.plus(1, ChronoUnit.DAYS);
// value still represents 2024-02-20.
```

If you need the variable to point to the new value, you must reassign it:

```java
value = value.plus(1, ChronoUnit.DAYS);
// value now represents 2024-02-21.
```

Do not conflate two different things: "reassigning a variable" and "mutating an object". After the assignment, the variable references the new result; the original date value remains unchanged.

The `Temporal` interface itself does not force every custom implementation to be immutable. Therefore, do not interpret the phrase "read-write" in the documentation as a guarantee that all operations mutate objects in place. With standard types, work with the return-value model; with custom types, read that type's specific contract.

The contract of `with`/`plus` requires the result to have the same observable type as the input. In particular, custom adjusters or amounts must also preserve that type and must not mutate the input. Do not write an adjuster that accepts a `LocalDateTime` and returns a `LocalDate`, as that both changes the type and loses the time part. When an operation does not change the value, the library may also return the existing object itself; compare values with `equals`, not `==`.

## 7. Chaining Operations: Order Is Part of the Rule

Starting from `2024-02-20`, the two chains below differ:

```text
with(lastDayOfMonth()) then plus(1, DAYS)
2024-02-20 → 2024-02-29 → 2024-03-01

plus(1, DAYS) then with(lastDayOfMonth())
2024-02-20 → 2024-02-21 → 2024-02-29
```

Each step uses the result of the immediately preceding step. Moving to the end of the month first and then adding a day has a different meaning from adding a day first and then finding the end of the month.

When writing a chain, state the rule in the exact order and use test cases where the two orders can produce different results. Do not only check that "the final date obtained is valid", because both March 1 and February 29 are valid, yet only one matches the specific requirement.

## 8. A Temporal Utility Needs a Narrow and Clear Contract

The signature `shift(Temporal value, long amount, TemporalUnit unit)` allows accepting many types, but that does not mean it allows every combination of inputs.

Such a utility should:

1. Require the input and unit to be non-`null`.
2. Check `value.isSupported(unit)` if the unit is chosen dynamically.
3. Invoke the addition and retain the result.
4. Let out-of-range or overflow errors surface clearly; do not turn every error into "unsupported".
5. Return `Temporal` if that is the actual contract, or use a concrete type when the business domain is fixed.

For `with(field, value)`, the corresponding check is `isSupported(field)`. It only indicates that the field type is supported; it does not confirm that every value placed into it is valid.

There is no general `isSupported(adjuster)` or `isSupported(amount)` method on `Temporal`. An adjuster may require multiple fields/units, and an amount may contain multiple components. You must know the requirements of the strategy object or handle errors according to the contract. Do not just check a `DAYS` constant and infer that every `Duration` can be used.

## 9. Standalone Java 17+ Program

Save the following code as `TemporalOperations.java`. It demonstrates all four overloads, calling through the interface, discarding/retaining results, chaining order, a custom adjuster, and error cases. The program requires no external libraries.

`FIRST_OF_NEXT_MONTH` is the "first day of the next month" rule. The lambda only uses `with` and `plus` on the input, so it preserves the concrete temporal type. This lesson verifies it with `LocalDate` and `LocalDateTime`; it is not advertised as a rule compatible with every type or every calendar system.

```java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.Period;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;
import java.time.temporal.TemporalUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Objects;

public class TemporalOperations {
    private static int checks;

    private static final TemporalAdjuster FIRST_OF_NEXT_MONTH =
            value -> value.with(ChronoField.DAY_OF_MONTH, 1)
                          .plus(1, ChronoUnit.MONTHS);

    private static Temporal shift(Temporal value, long amount, TemporalUnit unit) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
        if (!value.isSupported(unit)) {
            throw new IllegalArgumentException("Unsupported unit: " + unit);
        }
        return value.plus(amount, unit);
    }

    private static void eq(Object actual, Object expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError("expected=" + expected + ", actual=" + actual);
        }
        checks++;
    }

    private static void rejects(Class<? extends RuntimeException> type,
                                Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError("Unexpected exception", ex);
            }
            checks++;
            return;
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2024, 2, 20);
        Temporal value = original;
        Temporal first = value.with(ChronoField.DAY_OF_MONTH, 1);
        Temporal monthEnd = value.with(TemporalAdjusters.lastDayOfMonth());
        Temporal nextWeek = value.plus(7, ChronoUnit.DAYS);
        Temporal plusPeriod = value.plus(Period.ofDays(7));
        eq(first, LocalDate.of(2024, 2, 1));
        eq(monthEnd, LocalDate.of(2024, 2, 29));
        eq(nextWeek, LocalDate.of(2024, 2, 27));
        eq(plusPeriod, nextWeek);
        eq(first.getClass(), LocalDate.class);
        eq(value, original);
        value.plus(1, ChronoUnit.DAYS); // Result intentionally discarded.
        eq(value, LocalDate.of(2024, 2, 20));

        Temporal reassigned = value;
        reassigned = reassigned.plus(1, ChronoUnit.DAYS);
        eq(reassigned, LocalDate.of(2024, 2, 21));
        eq(LocalDate.from(reassigned), LocalDate.of(2024, 2, 21));

        Temporal monthThenDay = value.with(TemporalAdjusters.lastDayOfMonth())
                .plus(1, ChronoUnit.DAYS);
        Temporal dayThenMonth = value.plus(1, ChronoUnit.DAYS)
                .with(TemporalAdjusters.lastDayOfMonth());
        eq(monthThenDay, LocalDate.of(2024, 3, 1));
        eq(dayThenMonth, LocalDate.of(2024, 2, 29));

        Temporal nextMonth = value.with(FIRST_OF_NEXT_MONTH);
        eq(nextMonth, LocalDate.of(2024, 3, 1));
        LocalDateTime dateTime = LocalDateTime.of(2024, 2, 20, 10, 15);
        Temporal adjustedDateTime = dateTime.with(FIRST_OF_NEXT_MONTH);
        eq(adjustedDateTime, LocalDateTime.of(2024, 3, 1, 10, 15));
        eq(adjustedDateTime.getClass(), LocalDateTime.class);
        eq(dateTime.plus(Duration.ofHours(2)),
                LocalDateTime.of(2024, 2, 20, 12, 15));

        eq(shift(original, 2, ChronoUnit.DAYS), LocalDate.of(2024, 2, 22));
        eq(shift(LocalTime.of(23, 30), 2, ChronoUnit.HOURS),
                LocalTime.of(1, 30));
        eq(value.isSupported(ChronoUnit.HOURS), false);
        rejects(UnsupportedTemporalTypeException.class,
                () -> value.plus(1, ChronoUnit.HOURS));
        rejects(UnsupportedTemporalTypeException.class,
                () -> value.with(ChronoField.HOUR_OF_DAY, 9));
        rejects(UnsupportedTemporalTypeException.class,
                () -> value.plus(Duration.ofDays(1)));
        rejects(UnsupportedTemporalTypeException.class,
                () -> LocalTime.NOON.with(FIRST_OF_NEXT_MONTH));
        rejects(IllegalArgumentException.class,
                () -> shift(original, 1, ChronoUnit.HOURS));
        rejects(DateTimeException.class,
                () -> value.with(ChronoField.DAY_OF_MONTH, 30));

        System.out.println("original=" + original);
        System.out.println("first=" + first);
        System.out.println("monthEnd=" + monthEnd);
        System.out.println("nextWeek=" + nextWeek);
        System.out.println("monthThenDay=" + monthThenDay);
        System.out.println("dayThenMonth=" + dayThenMonth);
        System.out.println("adjustedDateTime=" + adjustedDateTime);
        System.out.println("PASS checks=" + checks);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TemporalOperations.java
java TemporalOperations
```

Stdout:

```text
original=2024-02-20
first=2024-02-01
monthEnd=2024-02-29
nextWeek=2024-02-27
monthThenDay=2024-03-01
dayThenMonth=2024-02-29
adjustedDateTime=2024-03-01T10:15
PASS checks=24
```

The check helpers actively throw `AssertionError` on failure, so the `-ea` flag is not needed. The `rejects` helper does not ignore arbitrary exceptions: it verifies the exact expected exception class and fails the program if the call does not throw.

Key evidence to observe from the example:

- `first.getClass()` is `LocalDate.class` even though the variable `first` is declared as `Temporal`.
- Calling `plus` and discarding the result does not change the date of `value`.
- The first-of-next-month rule preserves 10:15 when applied to `LocalDateTime`.
- `LocalTime` cannot apply a rule that requires the day of month.
- `LocalDate` cannot add hours or `Duration.ofDays(1)`.
- Checking unit support in `shift` does not replace checking whether a field's value is valid.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `with(DAY_OF_MONTH, 1)` to advance by one day | That sets the field to 1 | Use `plus(1, DAYS)` |
| Discarding the return value | Standard types are immutable | Reassign or return the result to the caller |
| Using `Temporal` and then calling `plusDays` | The method is not part of the interface | Use `plus(amount, DAYS)`, or keep the `LocalDate` type |
| Assuming the interface lets `LocalDate` add hours | The actual type still lacks a time part | Choose `LocalDateTime` if the domain requires date and time |
| Returning `LocalDate` from an adjuster that receives `LocalDateTime` | Violates the type-preservation contract and loses the time | Adjust through the input and preserve its type |
| Forcing the same adjuster onto every `Temporal` | Not every type has the required fields | Document the required types/capabilities |
| Catching every `RuntimeException` and returning the input | Hides both rule errors and overflows | Handle intended error types or let errors propagate |
| Reordering a chain assuming it is equivalent | Each step depends on the previous step's date | Write test cases that distinguish the two orders |

## 11. Practice Checks for Understanding

1. **Change the original date to `2024-12-20` and apply `FIRST_OF_NEXT_MONTH`.** The result must be `2025-01-01`. This tests that the rule crosses the year boundary.

2. **Apply the same rule to `2024-12-20T23:45`.** The result must be `2025-01-01T23:45`. The time part is preserved; do not convert the input to `LocalDate` mid-way.

3. **Receive the result from `shift` in a `Temporal` variable.** Explain why `getYear()` cannot be called directly on that variable even though the runtime object is `LocalDate`: the compiler only allows using the contract of the declared type.

4. **Try setting day 30 in February 2024.** `isSupported(DAY_OF_MONTH)` is still true, but the operation must throw an invalid day value error. Distinguish between "supporting a field" and "accepting a value".

5. **Design a function solely for payment due dates as ISO dates.** If the input/output are always `LocalDate`, use concrete signatures. Only widen to `Temporal` when there is a need to handle multiple types and the required capabilities have been clearly defined.

When reading a call through `Temporal`, check four things: which overload is selected, whether the runtime type supports the operation, whether the result is retained, and whether the order of operations matches the required rule.
