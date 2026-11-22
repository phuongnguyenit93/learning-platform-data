# Value Limits and Handling DateTimeException or ArithmeticException in Java

## 1. Why Can Time Calculations Fail?

Types in `java.time` such as `LocalDate`, `LocalDateTime`, `Instant`, `Duration`, and `Period` cannot represent every infinite number. Each type has its own value range, units, and calendar rules. When input data is invalid or a calculation exceeds the supported range, the API throws an exception to prevent incorrect time results.

Two common exception groups:

- **`DateTimeException`**: errors related to invalid time data or an instant/result falling outside the range supported by the time type. This is a runtime class in the `java.time` hierarchy.
- **`ArithmeticException`**: arithmetic operation errors, usually caused by numeric overflow or when converting to a unit/numeric result that cannot fit in the target type.

An operation may throw either one depending on the cause, and some APIs document both possibilities. You should not catch only one exception type and assume all time-related errors are handled.

Lesson objectives:

1. Know the limits of Java time types and where to read limit information.
2. Distinguish between input errors, invalid calendar date results, numeric overflow, and oversized unit conversions.
3. Catch exceptions at the right boundary and preserve the original cause when translating to a business error.
4. Avoid overflow errors before a result is assigned to a wider type.
5. Test boundary values, negative data, and cumulative operations.

## 2. DateTimeException: Invalid Time Values

`DateTimeException` is the runtime exception type used by the date-time API when there is an error in a time field or when an operation cannot be performed within the supported value range. Typical scenarios:

- Calendar dates that do not exist: `LocalDate.of(2023, 2, 29)`.
- Hours out of range: `LocalTime.of(25, 0)`.
- Strings that cannot be parsed by the formatter: `LocalDate.parse("2023-02-29")`, which typically throws the subclass `DateTimeParseException`.
- Addition producing a date beyond the target type's limit: for example, adding one day to `LocalDate.MAX`.
- A field value in a time type falling outside the rules allowed by the chronology or target API.

Invalid date example:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class InvalidDateDemo {
    public static void main(String[] args) {
        try {
            LocalDate.of(2023, 2, 29);
            System.out.println("Date created");
        } catch (DateTimeException ex) {
            System.out.println("Invalid calendar date");
        }
    }
}
~~~

Compile/run with Java 17+:

~~~bash
javac InvalidDateDemo.java
java InvalidDateDemo
~~~

Stdout:

~~~text
Invalid calendar date
~~~

2023 is not a leap year, so February 29 does not exist in the ISO calendar. `LocalDate.of(...)` throws an exception immediately at creation time; it does not automatically roll over to March 1. If business logic wants to adjust invalid input, that policy must be stated explicitly rather than swallowing the error by default.

### 2.1. DateTimeParseException as a Subclass

`DateTimeParseException` extends `DateTimeException`. When parsing text, you can catch the specific class to provide better feedback:

~~~java
try {
    LocalDate parsed = LocalDate.parse(input);
} catch (DateTimeParseException ex) {
    // input does not match the format/date accepted by the formatter
}
~~~

This is an illustrative snippet; the enclosing class needs an `input` variable and imports for `java.time.LocalDate` and `java.time.format.DateTimeParseException`. If you only catch `DateTimeException`, `DateTimeParseException` is still caught due to inheritance. Catching the general exception is appropriate when the same handling applies to multiple time errors; catching the specific type is appropriate when you need to distinguish parse errors from other errors.

Do not use `catch (Exception)` for all paths just to prevent the program from reporting errors. It hides errors unrelated to date-time and makes it hard to distinguish data errors from programming bugs.

## 3. ArithmeticException: Numeric Overflow in Time Calculations

`ArithmeticException` typically occurs when an integer-based time operation overflows, or when an API converts to a unit with a narrower representation range. For example:

- `Duration.toNanos()` if the total nanoseconds do not fit in a `long`.
- `Instant.toEpochMilli()` if the milliseconds from epoch exceed `long`.
- `Period.multipliedBy(...)` or component-wise operations when an integer result no longer fits in the storage type.
- A hand-written multiplication such as `seconds * 1_000_000_000L` overflowing before assignment.

Large Duration conversion example:

~~~java
import java.time.Duration;

public class DurationOverflowDemo {
    public static void main(String[] args) {
        Duration longDuration = Duration.ofDays(200_000);

        try {
            System.out.println(longDuration.toNanos());
        } catch (ArithmeticException ex) {
            System.out.println("Duration does not fit in long nanos");
        }
    }
}
~~~

Run commands:

~~~bash
javac DurationOverflowDemo.java
java DurationOverflowDemo
~~~

Stdout:

~~~text
Duration does not fit in long nanos
~~~

`Duration` represents a duration in seconds and nanoseconds, so it can hold a time span longer than the limit of a single `long` nanosecond total. `toNanos()` must return a single integer and therefore can report overflow. The right solution may be keeping `Duration`, keeping the seconds/nanos pair, or converting to an appropriate unit; arithmetic casting cannot recover an overflowed value.

## 4. Type Limits Are Not the Same

A type may support a wide time range, yet a conversion to a single unit has a smaller range.

| Type/Method | Limit meaning | What to remember |
|---|---|---|
| `LocalDate.MIN` / `MAX` | ISO calendar date limits supported by the type | Adding/subtracting near boundaries can throw `DateTimeException` |
| `LocalTime` | Time within a day, down to nanoseconds | Does not represent the next day when adding past midnight |
| `LocalDateTime.MIN` / `MAX` | Local date and time range | Adding hours/days past boundaries can fail |
| `Instant.MIN` / `MAX` | Range of instants supported by the Instant type | Wider than the range of `long` epoch milliseconds |
| `Duration` | Seconds and nanoseconds | `toNanos()` can overflow even when Duration is valid |
| `Period` | Year, month, day components | Component multiplication/addition can exceed integer range |
| `Instant.toEpochMilli()` | Converts instant to milliseconds from epoch | May throw `ArithmeticException` for very distant instants |
| `DateTimeFormatter` | Parsing/formatting by pattern and resolver | Invalid data typically throws `DateTimeParseException` |

Exact limits and exceptions should be checked in the Javadoc of the specific method, rather than assuming all types share the same range or all operations always throw one exception type.

### 4.1. Adding Near Boundaries

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class DateBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("Max date: " + LocalDate.MAX);

        try {
            LocalDate.MAX.plusDays(1);
        } catch (DateTimeException ex) {
            System.out.println("Beyond LocalDate range");
        }
    }
}
~~~

Stdout:

~~~text
Max date: +999999999-12-31
Beyond LocalDate range
~~~

`LocalDate.MAX` is the last date in the `LocalDate` range. `plusDays(1)` is not allowed to produce a date outside the range, so it throws an exception. Do not convert the result to a string before calculating and try to manipulate characters; let the time API check the range, and handle the exception at a layer that can decide whether to report an error, reject the request, or use another type.

## 5. Distinguishing Data Errors from Overflow

The same "add time" operation can fail for different reasons:

| Scenario | Cause | Appropriate handling |
|---|---|---|
| `LocalDate.of(2023, 2, 29)` | Invalid calendar date | Report a validation error for the input |
| `LocalDate.MAX.plusDays(1)` | Result exceeds date range | Reject the calculation or define business limits |
| `LocalDate.parse("tomorrow")` | String is not an ISO date | Require a valid date format |
| `Duration.ofDays(200_000).toNanos()` | Total nanos do not fit in `long` | Keep Duration or choose another unit |
| `Instant.MAX.toEpochMilli()` | Epoch millis exceed `long` range | Check time range before exporting to millis |
| Hand-written `seconds * 1_000_000_000L` | Multiplication overflows before storage | Check before multiplying or use another representation |

You should not respond with "invalid date" for every `ArithmeticException`: the error may mean the value exceeded the numeric range during unit conversion, while the original date was not wrong. Conversely, do not attribute simple validation errors to overflow.

If a public API needs a unified error type, translate at the system boundary while preserving the error type and original cause in logs or the exception's `cause` field. Do not erase the original information by throwing a generic error with no cause.

## 6. Why Can Assigning to long After Multiplication Still Be Wrong?

Java evaluates expressions according to the types of the operands. Therefore:

~~~java
long nanos = seconds * 1_000_000_000;
~~~

if `seconds` is an `int`, the multiplication happens in `int` arithmetic before being assigned to `long`. If it overflows, the value is already wrong beforehand; a wider target variable cannot fix it. Adding the `L` suffix changes the multiplication type:

~~~java
long nanos = seconds * 1_000_000_000L;
~~~

However, this can still overflow `long` if `seconds` is large. Choosing a wider type does not mean skipping bounds checks.

Safety rules:

- Check ranges before multiplying/dividing when converting units.
- Use `Math.multiplyExact(a, b)` or `Math.addExact(a, b)` when writing integer arithmetic that needs overflow detection.
- Keep `Instant`/`Duration` in their original form if you do not need to reduce them to a single integer total.
- Avoid absolute nanosecond totals in `long` for very long time spans.
- When the JDK API already provides a conversion method, prefer using it over rebuilding a formula without overflow checks.

Explicit overflow detection example:

~~~java
public class ExactArithmeticDemo {
    public static void main(String[] args) {
        long seconds = Long.MAX_VALUE;

        try {
            long millis = Math.multiplyExact(seconds, 1_000L);
            System.out.println(millis);
        } catch (ArithmeticException ex) {
            System.out.println("Milliseconds overflow long");
        }
    }
}
~~~

Stdout:

~~~text
Milliseconds overflow long
~~~

This is an illustrative arithmetic calculation. It does not replace a specific time-range policy, but shows how to ask Java to **report overflow** instead of letting the result wrap around silently.

## 7. Unit Conversion Limitations

### 7.1. Instant to Epoch Milliseconds

`Instant` supports a wide time range, whereas `toEpochMilli()` returns `long` milliseconds from epoch. Instants that are too far away may not fit in `long`:

~~~java
import java.time.Instant;

public class InstantMillisBoundaryDemo {
    public static void main(String[] args) {
        try {
            System.out.println(Instant.MAX.toEpochMilli());
        } catch (ArithmeticException ex) {
            System.out.println("Instant is outside epoch-millis range");
        }
    }
}
~~~

Stdout:

~~~text
Instant is outside epoch-millis range
~~~

If a system only accepts epoch milliseconds, validation needs to cover both **supported date range** and **precision**. One `Instant` may be valid yet impossible to convert to `long` millis; another `Instant` may convert but lose sub-millisecond nanoseconds.

### 7.2. Duration to Nanoseconds

`Duration.toNanos()` returns a `long` total of nanoseconds. For long durations, the nanosecond count can exceed the `long` limit; successfully creating a `Duration` does not guarantee that converting to total nanos will succeed.

If you need long time spans:

- Keep the `Duration` object, and use `getSeconds()` together with `getNano()` if you need the two components.
- If you need total nanoseconds and a wider data range, consider `BigInteger` with a clearly defined unit convention.
- Only use `toNanos()` when business bounds guarantee the result falls within the `long` range.

Do not handle this by catching `ArithmeticException` and returning `Long.MAX_VALUE` as if it were a real value; that turns an overflow into corrupted data. Only saturate (clamp at the limit) if business rules actively require it, and name/define that behavior clearly.

### 7.3. Period and Year/Month/Day Components

`Period` stores three integer fields, not a total number of seconds. Multiplying a period can cause a field to exceed the `int` limit:

~~~java
import java.time.Period;

public class PeriodOverflowDemo {
    public static void main(String[] args) {
        try {
            Period huge = Period.ofMonths(Integer.MAX_VALUE);
            System.out.println(huge.multipliedBy(2));
        } catch (ArithmeticException ex) {
            System.out.println("Period component overflow");
        }
    }
}
~~~

Stdout:

~~~text
Period component overflow
~~~

Do not "fix" overflow by treating a month as 30 days. Months do not have a fixed length; if the problem is an absolute number of days, use start/end dates and an API like `ChronoUnit.DAYS.between`. If the problem is calendar shifting, keep `Period` or apply it to `LocalDate` with range checking.

## 8. Catching the Right Exception at the Appropriate Boundary

A good pattern is to wrap only the operation that can fail, translate it into an error matching the semantics of the handling layer, and preserve the original cause:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class DeadlineService {
    public LocalDate shiftDate(LocalDate date, long days) {
        try {
            return date.plusDays(days);
        } catch (DateTimeException | ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Requested date is outside the supported range", ex);
        }
    }
}
~~~

This is an illustrative class for shifting a date based on user input; in a real project, you need to decide the appropriate public error type. Both exception types are caught explicitly in a multi-catch, then preserved as the **cause** when throwing the business error. If the contract wants to distinguish date errors from arithmetic overflow, create two separate handling branches instead of combining them.

Do not catch `Throwable` or `Error` to handle time limits. Serious JVM errors are not normal input data. Nor should you catch `RuntimeException` too broadly at a low layer because it can hide programming bugs.

## 9. Validate Early, But Do Not Replace Checks at the Final Operation

Input validation is useful when you want early feedback:

~~~java
static LocalDate parseDate(String text) {
    try {
        return LocalDate.parse(text);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Expected an ISO date such as 2024-02-29", ex);
    }
}
~~~

This snippet is intended for a class that imports `java.time.LocalDate` and `java.time.format.DateTimeParseException`. It distinguishes unparseable strings from subsequent calculations exceeding the range.

Even after pre-validating, you must still keep exception handling for the final calculation. For example, the input `LocalDate.MAX` is valid, but `plusDays(1)` is not. Validating the initial fields cannot guarantee that every subsequent calculation will stay within range.

If the input consists of separate components, you can validate valid ranges before creating the object; however, to ensure calendar rules are respected, use the `LocalDate.of` or `LocalTime.of` factory itself rather than only checking each field individually. February 29 is an example: the month and day individually fall within common bounds, yet the combination may be invalid for that year.

## 10. Standalone Summary Program

Save as **`DateTimeExceptionsDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;
import java.time.format.DateTimeParseException;

public class DateTimeExceptionsDemo {
    public static void main(String[] args) {
        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected");
        }

        try {
            LocalDate.parse("not-a-date");
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid text rejected");
        }

        try {
            LocalDate.MAX.plusDays(1);
        } catch (DateTimeException ex) {
            System.out.println("LocalDate boundary rejected");
        }

        try {
            Duration.ofDays(200_000).toNanos();
        } catch (ArithmeticException ex) {
            System.out.println("Duration-to-nanos overflow");
        }

        try {
            Instant.MAX.toEpochMilli();
        } catch (ArithmeticException ex) {
            System.out.println("Instant-to-millis overflow");
        }

        try {
            Period.ofMonths(Integer.MAX_VALUE).multipliedBy(2);
        } catch (ArithmeticException ex) {
            System.out.println("Period component overflow");
        }
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac DateTimeExceptionsDemo.java
java DateTimeExceptionsDemo
~~~

Stdout:

~~~text
Invalid date rejected
Invalid text rejected
LocalDate boundary rejected
Duration-to-nanos overflow
Instant-to-millis overflow
Period component overflow
~~~

The program demonstrates three categories of scenarios: invalid calendar fields, malformed parse strings, and conversions/additions exceeding the representation range. Each case is caught according to the exception type of its API. When handling in production, write structured logs (operation, sanitized input, exception type), avoiding logging sensitive data or relying on exception messages that may not be stable across versions.

## 11. Boundary Testing Strategy

Testing "one normal value" is not enough to verify limit handling. You should have tests for:

| Group | Test example | Expected result |
|---|---|---|
| Normal valid value | `LocalDate.of(2024, 2, 29)` | Succeeds |
| Invalid calendar date | `LocalDate.of(2023, 2, 29)` | `DateTimeException` |
| Invalid parse | `LocalDate.parse("nope")` | `DateTimeParseException` |
| Range boundary value | `LocalDate.MAX` | Can be created/read |
| Addition beyond boundary | `LocalDate.MAX.plusDays(1)` | Appropriate API exception |
| Overflowing unit conversion | `Duration.ofDays(200_000).toNanos()` | `ArithmeticException` |
| Converting too-distant instant | `Instant.MAX.toEpochMilli()` | `ArithmeticException` |
| Overflowing period multiplication | `Period.ofMonths(Integer.MAX_VALUE).multipliedBy(2)` | `ArithmeticException` |
| Precision reduction | `Instant` with fractional nanos → epochMillis | Result truncates sub-ms part if no overflow |
| Negative data | Instants before epoch | Verify sign and rounding rules |

In unit tests, assert the **exception type** and expected outcome, without necessarily matching the entire exception message since wording can change. For input APIs, verify the public error contract, such as HTTP 400 for invalid data if that is the application's convention.

## 12. Common Mistakes and How to Avoid Them

1. **Catching only DateTimeException:** fails to handle certain overflows when converting to total millis/nanos.
2. **Catching only ArithmeticException:** fails to handle invalid dates/months or unparseable strings.
3. **Catching Exception too broadly:** hides programming bugs, IO errors, or unrelated failures.
4. **Assigning to long after int multiplication has already overflowed:** use long operands from the start, while still checking for overflow.
5. **Using the maximum value as a fallback:** turns errors into fake timestamps; only clamp at the limit when business logic explicitly defines it.
6. **Assuming a valid object means every operation on it is valid:** adding one day near the boundary can still fail.
7. **Assuming every Instant can convert to epochMillis:** the `Instant` range is wider than `long` milliseconds.
8. **Calling Duration.toNanos() on arbitrary durations:** total nanoseconds can exceed `long`; keep `Duration` if possible.
9. **Treating Period as a number of days:** do not convert months/years to 30/365 days to work around range issues.
10. **Swallowing exceptions and continuing:** resulting data loses its provenance and hides the real cause.
11. **Testing only normal dates:** test non-leap dates, MIN/MAX values, pre-epoch instants, and cumulative calculations.
12. **Relying on exception messages for logic:** prefer the exception class and input conditions; messages are for diagnostics.

## 13. Self-Check Questions

**Question 1.** What is the main difference between `DateTimeException` and `ArithmeticException`?

**Answer:** `DateTimeException` relates to invalid date-time values/operations or exceeding a time type's range. `ArithmeticException` typically signals numeric arithmetic or unit conversion overflow. Check the specific API because a single operation may document multiple exception types.

**Question 2.** Why is `LocalDate.of(2023, 2, 29)` different from `LocalDate.MAX.plusDays(1)`?

**Answer:** The first case constructs an invalid calendar date combination; the second starts from a valid date, but the result exceeds `LocalDate`'s representation limit.

**Question 3.** Why can `Duration.ofDays(200_000)` be valid while `toNanos()` fails?

**Answer:** `Duration` stores seconds and nanoseconds separately. Total nanoseconds require a single `long`, which can exceed that type's range.

**Question 4.** Why can `Instant.MAX` exist while `Instant.MAX.toEpochMilli()` fails?

**Answer:** `Instant` has a wider time range than what `long` milliseconds can represent.

**Question 5.** Why can a multiplication assigned to `long` still be wrong?

**Answer:** If the operands are `int`, the multiplication happens in `int` arithmetic and can overflow before the result is assigned to `long`. Use `long` operands or `Math.multiplyExact`, and also check for `long` overflow.

**Question 6.** Should you catch `DateTimeException` and return "today" as a default value?

**Answer:** No, unless the public business specification explicitly requires it. Silently substituting the current date can hide invalid input and cause silent data corruption.

**Question 7.** Does pre-validating date fields eliminate the need for exception handling on addition?

**Answer:** No. Valid input values can still produce an out-of-range result during calculation.

**Question 8.** Should you return `Long.MAX_VALUE` when `Duration.toNanos()` overflows?

**Answer:** Do not do so on your own if business logic has not defined a clamping policy; that value is not the exact duration and can cause downstream bugs.

## 14. Practical Rules

- Use date-time factories to validate date/time combinations right at the input boundary.
- Catch `DateTimeParseException` for string data, `DateTimeException` for calendar/time-range errors, and `ArithmeticException` for overflow/unit conversions that do not fit the target type.
- Read the Javadoc of the specific method; do not assume all time errors throw the same type.
- Keep `Instant` and `Duration` in their original forms if you do not yet need to reduce them to `epochMillis` or total `nanos`.
- Use `Math.addExact`/`multiplyExact` for hand-written integer arithmetic and define a clear policy if overflow occurs.
- Test MIN/MAX, leap days, negative inputs, unparseable data, and unit conversions that may exceed range.
- When translating an exception into a business error, preserve the cause and useful diagnostic info; do not swallow exceptions or fabricate fake time values.

In summary, safe time handling is more than just catching exceptions. It requires understanding **type limits**, **calendar rules**, **intermediate numeric types**, and **conversion semantics**. That is how you distinguish genuinely invalid data from a valid calculation that cannot be represented in the target type.
