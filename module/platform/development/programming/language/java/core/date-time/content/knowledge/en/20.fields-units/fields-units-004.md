# get(), getLong(), range(), and Field Bounds

## 1. Which Fields Does a Date-Time Object Provide?

A **temporal field** (`TemporalField`) is a piece of information that can be read as a number: year, month, day of month, hour of day, or number of days from an epoch. `ChronoField` contains standard fields such as `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, and `EPOCH_DAY`.

For example, in `LocalDate.of(2024, 2, 29)`:

| Field | Meaning | Value |
| --- | --- | --- |
| `YEAR` | Proleptic ISO year | `2024` |
| `MONTH_OF_YEAR` | Month of year | `2` |
| `DAY_OF_MONTH` | Day of month | `29` |
| `EPOCH_DAY` | Number of days since 1970-01-01 in the ISO calendar | `19782` |

`DAY_OF_MONTH` is not the number of days elapsed from an epoch; `EPOCH_DAY` is not the day number within the month. Having the same numeric return type does not mean the same interpretation.

`TemporalAccessor` is the interface for reading this information. Many familiar types such as `LocalDate`, `LocalTime`, and `YearMonth` implement it. According to the [TemporalAccessor contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html), `get` returns an `int`, `getLong` returns a `long`, and `range` returns the range of valid values for the field on that object.

In application code where the concrete type is known, `date.getDayOfMonth()` is usually easier to read than `date.get(ChronoField.DAY_OF_MONTH)`. Reading via a field is useful when handling a field selected at runtime or writing a generic component for multiple date-time types. There is no need to convert every specific getter to the generic interface.

## 2. Three Questions That Must Be Separated

Before reading a field, distinguish between:

1. **Does the object support that field?** Use `isSupported(field)`.
2. **Which numeric type should be used to read it?** Use `get(field)` or `getLong(field)` according to the field's contract.
3. **What range of values is valid in the current context?** Use `range(field)`.

For example, `LocalDate` supports the day of month but does not support the hour of day. Switching from `get(HOUR_OF_DAY)` to `getLong(HOUR_OF_DAY)` does not create the missing hour information.

Conversely, `LocalDate` does support `EPOCH_DAY`, but it must be read using `getLong`. `isSupported` returning `true` does not guarantee that `get` will succeed, because field support and representability as an `int` are two separate conditions.

| Case | `isSupported` | `get` | `getLong` |
| --- | --- | --- | --- |
| `LocalDate` with `DAY_OF_MONTH` | `true` | Readable | Readable |
| `LocalDate` with `EPOCH_DAY` | `true` | Not readable as `int` | Readable |
| `LocalDate` with `HOUR_OF_DAY` | `false` | Unsupported | Unsupported |
| `LocalTime` with `NANO_OF_DAY` | `true` | Not readable as `int` | Readable |
| `YearMonth` with `DAY_OF_MONTH` | `false` | Unsupported | Unsupported |

This table applies to the standard types and `ChronoField` fields listed, not as a guarantee for every custom `TemporalField` implementation.

## 3. get(): Reading a Field Under the int Contract

The short example below assumes a `date` variable of type `LocalDate` already exists:

```java
int year = date.get(ChronoField.YEAR);
int month = date.get(ChronoField.MONTH_OF_YEAR);
int day = date.get(ChronoField.DAY_OF_MONTH);
```

`get` does not perform a narrowing cast from an arbitrary `long` value. It reads according to the field's `int` access contract. Fields whose value domain is wider than `int` can be rejected even when the value of a specific object happens to be small.

For example, the date 2024-02-29 has `EPOCH_DAY = 19782`, which fits well within `int`. However:

```java
LocalDate date = LocalDate.of(2024, 2, 29);

long epoch = date.getLong(ChronoField.EPOCH_DAY); // 19782
// date.get(ChronoField.EPOCH_DAY) will throw an exception.
```

`LocalDate.get(EPOCH_DAY)` throws `UnsupportedTemporalTypeException` and requires using `getLong`. The entire `EPOCH_DAY` range of `LocalDate` does not fit within the `int` range; the fact that a particular date has a small value does not change that access contract.

Similarly, `NANO_OF_DAY` is the number of nanoseconds from the start of the day. It can be much larger than `Integer.MAX_VALUE`. Even when the time is near the beginning of the day and the value is small, use `getLong(NANO_OF_DAY)` according to `LocalTime`'s contract.

## 4. getLong(): Wider Numeric Range, Not Wider Access

`getLong` is the appropriate choice when writing a generic field reader because many fields are modeled with `long`. It can also read fields that fit in `int`, such as `DAY_OF_MONTH`.

However, `getLong` still requires the object to support the field:

```java
LocalDate date = LocalDate.of(2024, 2, 29);

long day = date.getLong(ChronoField.DAY_OF_MONTH); // 29
// date.getLong(ChronoField.HOUR_OF_DAY) is still invalid.
```

`LocalDate` only has a date, not a time. Nor does it infer `INSTANT_SECONDS` on its own: pinpointing an instant on the timeline also requires appropriate time and offset or time-zone information. `getLong` should not be understood as a way to "force" an object to provide any arbitrary field.

If you genuinely need to pass a `long` value into a system that only accepts `int`, this must be a separate conversion decision:

```java
long value = date.getLong(ChronoField.EPOCH_DAY);
int narrowed = Math.toIntExact(value);
```

`Math.toIntExact` checks the **actual value**, throwing `ArithmeticException` if it exceeds the `int` range. It does not change the field's value range and does not make `date.get(EPOCH_DAY)` valid.

Avoid `(int) value` when there is no range guarantee: integer casting can drop high-order bits and return a different number. A field-reading error should not be "fixed" by producing a truncated value.

## 5. range(): General Range and Context-Aware Range

`ValueRange` describes the bounds of a field. There are two common sources for a range:

| Call | Question |
| --- | --- |
| `ChronoField.DAY_OF_MONTH.range()` | What are the general bounds of the day-of-month field? |
| `date.range(ChronoField.DAY_OF_MONTH)` | For this specific date, what are the bounds for day of month? |

[ChronoField](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoField.html) defines the semantics of standard fields. The general range of `DAY_OF_MONTH` prints as `1 - 28/31`: the lower bound is `1`, and the upper bound varies from `28` to `31` depending on the month and year. This is not the division `28/31`, nor is it a list containing only the three numbers 1, 28, and 31.

With `LocalDate`, the object has enough month and year information to narrow the range:

| Context | `range(DAY_OF_MONTH)` |
| --- | --- |
| February 2024, leap year | `1 - 29` |
| February 2023 | `1 - 28` |
| April 2024 | `1 - 30` |
| January 2024 | `1 - 31` |

The selected day within the month does not make the upper bound equal to that day. For example, `2024-02-01` still has a day-of-month range of `1 - 29`, because the entire month of February 2024 has 29 days.

For other types or fields, the degree of narrowing depends on the information the object actually holds and its implementation contract. Never assume `range` always produces the exact range for a full date if the object does not represent that date.

### 5.1. Methods for Reading Bounds

Given a `ValueRange range`:

- `getMinimum()`: the smallest minimum bound.
- `getLargestMinimum()`: the largest possible minimum bound when the minimum varies.
- `getSmallestMaximum()`: the smallest possible maximum bound.
- `getMaximum()`: the largest maximum bound.
- `isFixed()`: both the minimum and maximum bounds are fixed.

For the general range of `DAY_OF_MONTH`, both minimum bounds are `1`; the smallest maximum is `28` and the largest maximum is `31`; `isFixed()` is `false`. For the narrowed range of February 2024, both maximum bounds are `29`, so `isFixed()` is `true`.

`isFixed()` does not ask whether the object is immutable. Both a range with a varying maximum and a fixed range are immutable `ValueRange` values; this method only describes the structure of the range.

### 5.2. Checking a Value and Checking the int Range

[ValueRange](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ValueRange.html) provides checks with distinct purposes:

| Method | Meaning |
| --- | --- |
| `isValidValue(value)` | Does the value fall within the outer bounds of the range? |
| `checkValidValue(value, field)` | Checks as above; returns `long` or throws an exception |
| `isIntValue()` | Does the entire range fit within the `int` range? |
| `isValidIntValue(value)` | Does the range fit in `int` and is the value within the range? |
| `checkValidIntValue(value, field)` | Checks the `int` contract above; returns `int` or throws an exception |

A common point of confusion: `isValidIntValue` does not merely check whether the number itself fits in an `int`. It also requires `isIntValue()` of the entire range to be `true`.

Therefore, for `EPOCH_DAY` on 2024-02-29:

- `range.isValidValue(19782)` is `true`.
- `range.isIntValue()` is `false`.
- `range.isValidIntValue(19782)` is `false`.
- `Math.toIntExact(19782L)` still succeeds because it is a conversion check for a single individual value.

The `field` parameter in `checkValidValue` and `checkValidIntValue` helps describe the error in terms of the field; it does not automatically supply a month or year to narrow the range. You must obtain the right `ValueRange` before checking.

## 6. Complete Java 17+ Program

Save the file as `TemporalFieldReadDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.ValueRange;
import java.util.function.LongSupplier;

public class TemporalFieldReadDemo {
    static void attempt(String label, LongSupplier operation) {
        try {
            System.out.println(label + " = " + operation.getAsLong());
        } catch (DateTimeException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    static void describe(TemporalAccessor temporal, ChronoField field) {
        if (!temporal.isSupported(field)) {
            System.out.println(field + " = unsupported");
            return;
        }
        System.out.println(field + " = " + temporal.getLong(field)
                + "; range=" + temporal.range(field));
    }

    public static void main(String[] args) {
        LocalDate leap = LocalDate.of(2024, 2, 29);
        ValueRange general = ChronoField.DAY_OF_MONTH.range();
        ValueRange refined = leap.range(ChronoField.DAY_OF_MONTH);

        System.out.println("day = " + leap.get(ChronoField.DAY_OF_MONTH));
        System.out.println("epoch supported = "
                + leap.isSupported(ChronoField.EPOCH_DAY));
        attempt("epoch getLong", () -> leap.getLong(ChronoField.EPOCH_DAY));
        attempt("epoch get", () -> leap.get(ChronoField.EPOCH_DAY));
        attempt("hour getLong", () -> leap.getLong(ChronoField.HOUR_OF_DAY));

        System.out.println("general day range = " + general);
        System.out.println("leap day range = " + refined);
        System.out.println("common February range = "
                + LocalDate.of(2023, 2, 1).range(ChronoField.DAY_OF_MONTH));
        System.out.println("April range = "
                + LocalDate.of(2024, 4, 1).range(ChronoField.DAY_OF_MONTH));
        System.out.println("general fixed = " + general.isFixed());
        System.out.println("refined fixed = " + refined.isFixed());
        System.out.println("general accepts 31 = " + general.isValidValue(31));
        System.out.println("refined accepts 31 = " + refined.isValidValue(31));

        ValueRange epochRange = leap.range(ChronoField.EPOCH_DAY);
        long epoch = leap.getLong(ChronoField.EPOCH_DAY);
        System.out.println("epoch range fits int = " + epochRange.isIntValue());
        System.out.println("epoch valid as long = "
                + epochRange.isValidValue(epoch));
        System.out.println("epoch valid for int range = "
                + epochRange.isValidIntValue(epoch));
        System.out.println("explicit exact narrowing = "
                + Math.toIntExact(epoch));

        LocalTime time = LocalTime.of(12, 34, 56, 789);
        attempt("nano getLong", () -> time.getLong(ChronoField.NANO_OF_DAY));
        attempt("nano get", () -> time.get(ChronoField.NANO_OF_DAY));

        YearMonth month = YearMonth.of(2024, 2);
        describe(month, ChronoField.MONTH_OF_YEAR);
        describe(month, ChronoField.DAY_OF_MONTH);
        System.out.println("month length = " + month.lengthOfMonth());
        System.out.println("original date = " + leap);
    }
}
```

Compile and run:

```shell
javac --release 17 TemporalFieldReadDemo.java
java TemporalFieldReadDemo
```

Stdout:

```text
day = 29
epoch supported = true
epoch getLong = 19782
epoch get -> UnsupportedTemporalTypeException
hour getLong -> UnsupportedTemporalTypeException
general day range = 1 - 28/31
leap day range = 1 - 29
common February range = 1 - 28
April range = 1 - 30
general fixed = false
refined fixed = true
general accepts 31 = true
refined accepts 31 = false
epoch range fits int = false
epoch valid as long = true
epoch valid for int range = false
explicit exact narrowing = 19782
nano getLong = 45296000000789
nano get -> UnsupportedTemporalTypeException
MonthOfYear = 2; range=1 - 12
DayOfMonth = unsupported
month length = 29
original date = 2024-02-29
```

The program catches `DateTimeException` in `attempt` so it can observe invalid reads while continuing to run the remaining examples. It only prints the exception class name; it does not depend on the exact error message text of a specific JDK build.

The `describe` method checks support first, then reads `getLong` and `range`. If the field is unsupported, it explicitly states that status instead of substituting `0`. `0` can be a valid value for many fields, so using it to represent "no information" blurs the distinction.

The last line shows that the original date is still `2024-02-29`. Reading fields and reading ranges do not mutate the object.

## 7. Limits of range(): It Does Not Replace All Validation

### 7.1. A General Range Is Not Enough to Validate a Date

Suppose you are processing `year = 2024`, `month = 2`, and `day = 31`. The general range of `DAY_OF_MONTH` accepts `31` because some months have 31 days. That does not make `2024-02-31` a valid date.

If you already have a `LocalDate` representing the month of interest, use its narrowed range. If you are receiving three separate components from external input, you can let `LocalDate.of(year, month, day)` validate the combination. Do not treat each field passing its general range as proof that the whole date is valid.

Validation also depends on order and context. A form with January selected may allow day 31; when the user switches to February, the bounds must be updated or invalid input must be reported. A range tied to an old context does not automatically update with another variable.

### 7.2. Having Information to Infer Month Length Does Not Mean Supporting Day of Month

`YearMonth.of(2024, 2)` knows that the month has 29 days via `lengthOfMonth()`. However, it does not hold a selected day of month; `DAY_OF_MONTH` is not a field supported by `YearMonth` for access.

Therefore, `month.get(DAY_OF_MONTH)`, `month.getLong(DAY_OF_MONTH)`, and `month.range(DAY_OF_MONTH)` are all inappropriate ways to obtain that information. Use `lengthOfMonth()` if you need the number of days; use `month.atDay(day)` if you need to create a specific date with validation.

This is why you must read the type's contract rather than assuming "having a year and a month guarantees all day fields can be read."

### 7.3. A Numeric Range Does Not Express Every Business Rule

A custom field may accept only a few discrete values within its minimum–maximum bounds. `ValueRange` describes the bounds, not every excluded value in between. Similarly, the `DAY_OF_MONTH` range does not tell you whether a day is a holiday or whether booking is allowed on it.

Range checks answer only part of the validation problem. Cross-field constraints, calendar-specific rules, and business rules still require their own checks.

### 7.4. Numeric Domains and Calendar Semantics Must Not Be Separated

Two year numbers may belong to different calendar systems; `YEAR` and `YEAR_OF_ERA` are not completely interchangeable either. A method accepting a generic `TemporalAccessor` should clearly state which type or calendar it expects when that affects business logic.

There is no need to turn all information into a `Map<TemporalField, Long>` and lose the original type. In many situations, keeping `LocalDate` or `YearMonth` at the method boundary clearly expresses what information the input contains.

## 8. Exceptions and Meaningful Handling

For the standard types used here:

| Situation | Typical Behavior |
| --- | --- |
| `LocalDate.getLong(HOUR_OF_DAY)` | `UnsupportedTemporalTypeException` due to missing field |
| `LocalDate.get(EPOCH_DAY)` | `UnsupportedTemporalTypeException` because `long` access is required |
| Checking a number outside `ValueRange` via `check...` | `DateTimeException` |
| Creating a non-existent date with `LocalDate.of` | `DateTimeException` |
| `Math.toIntExact` with a number outside the `int` range | `ArithmeticException` |

`UnsupportedTemporalTypeException` is a subclass of `DateTimeException`. Catching the superclass in the demo program helps keep the experiment running, but when designing an application, avoid lumping all errors into "invalid date" if you need to distinguish field-selection errors from input-data errors.

If the user can choose a field at runtime, `isSupported` helps report a "not applicable to this type" status. If a method already strictly requires `LocalDate` and `DAY_OF_MONTH`, an unexpected read failure may indicate a programming bug and should not be silently masked with a default value.

For custom fields, `isSupported` is only the support check; retrieving the value still follows the contract of the corresponding field and type. Do not treat it as a guarantee that any subsequent read cannot throw an exception.

## 9. Common Mistakes

| Mistake | Why It Is Wrong | Appropriate Approach |
| --- | --- | --- |
| Using `get` for every field | Some fields require a `long` range | Use `getLong` when handling fields generically |
| Seeing `isSupported = true` and assuming `get` will work | Ignores the `int` contract | Check the field's range or read with `getLong` |
| Using `getLong` to read the hour from `LocalDate` | A wider numeric range does not create an hour | Choose a type that has the information needed |
| Treating `1 - 28/31` as meaning every month has 31 days | That is the general range | Obtain the range from a specific context |
| Treating `range.getMaximum()` as the current value | That is the field's upper bound | Use `get` or `getLong` to read the value |
| Taking `DAY_OF_MONTH.range()` and concluding Feb 31 is valid | Individual fields do not validate combinations | Construct a `LocalDate` or use the proper context |
| Using `isValidIntValue` as a standalone cast check | The method also checks the entire range | Use `Math.toIntExact` if you truly need to narrow the value |
| Returning `0` when a field is unsupported | Can be confused with a valid value | Represent missing information explicitly |
| Calling `range(DAY_OF_MONTH)` on `YearMonth` | That field is not supported for access | Use `lengthOfMonth` or `atDay` |

## 10. Self-Verification and Practice

1. Change the date in the example from `2024-02-29` to `2024-02-01`. The value of `get(DAY_OF_MONTH)` becomes `1`, but the day-of-month range remains `1 - 29`. Explain the difference between the current value and the bounds.
2. Change it to `2023-02-01`. The upper bound narrows to `28`. The algorithm does not need a manually maintained month table.
3. Use `LocalTime.MIDNIGHT` with `NANO_OF_DAY`. The `getLong` value is `0`, yet `get` is still rejected according to `LocalTime`'s field contract. This is an important test to disprove the assumption that "a small current value is enough."
4. Compare `isValidValue(31)` on the general range versus the range for February 2024. Predict the results before running.
5. Write a method that takes a `TemporalAccessor` and a `ChronoField`, returning the `long` value if supported or a clearly named missing-information state. Test it with `LocalDate`, `LocalTime`, and `YearMonth`; avoid using `0` as an error signal.
6. Try `ValueRange.of(0, Long.MAX_VALUE)`. Compare `isValidValue(1)`, `isIntValue()`, and `isValidIntValue(1)`. Explain why `1` fits in an `int` yet the third check still returns `false`.
7. Accept year, month, and day inputs as three separate numbers and validate them with `LocalDate.of`. Compare this with checking only the three general ranges to see the invalid combinations that separate checks miss.

When reading date-time information, always keep three things clear: whether the object has the field, whether the numeric access method matches the field's range, and whether the bounds being used are general or narrowed to the context.
