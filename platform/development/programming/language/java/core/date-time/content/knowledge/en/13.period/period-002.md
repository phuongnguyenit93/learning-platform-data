# Creating a Period and Parsing ISO-8601 Strings

## 1. How Calendar Periods Are Represented

When a requirement says “extend by 3 months” or “add 1 year and 10 days”, the units that need to be preserved are **calendar years, months, and days**. `java.time.Period` represents a date-based amount of time in the ISO calendar using those three components. The object does not contain a start date, end date, time of day, or time zone.

For example, `Period.of(1, 2, 3)` means an amount of 1 year, 2 months, and 3 days. It cannot answer “how many exact seconds does this last?”, because you need to know which date this amount is applied to. In an application, you can use it to carry a renewal configuration or a date-based period across layers while keeping the units explicit.

`Period` is immutable: once created, the object's value does not change. Factory methods return a value that can be safely stored and passed around. Adding a period to a specific date is the next step in using it; this lesson focuses on **creating values, reading components, and converting to and from strings**.

## 2. Choosing a Factory Method Based on Input Data

Do not use `new Period(...)`; the class provides static factory methods to create objects.

| Available data | How to create | String value when printed |
|---|---|---|
| No period yet | `Period.ZERO` | `P0D` |
| 2 years | `Period.ofYears(2)` | `P2Y` |
| 15 months | `Period.ofMonths(15)` | `P15M` |
| 10 days | `Period.ofDays(10)` | `P10D` |
| 2 weeks | `Period.ofWeeks(2)` | `P14D` |
| 1 year, 2 months, 3 days | `Period.of(1, 2, 3)` | `P1Y2M3D` |
| String with units | `Period.parse("P1Y2M3D")` | `P1Y2M3D` |

`ofWeeks` immediately converts the number of weeks into days by multiplying by 7. `Period` does not store a separate weeks field, so creating one from 2 weeks and reading it back only shows 14 days. Similarly, parsing `P2W` produces a value with 14 days. When the number of weeks is too large and the multiplication overflows the `int` range, `ofWeeks` throws `ArithmeticException`.

The `of`, `ofYears`, `ofMonths`, and `ofDays` methods accept `int` components, which may be zero or negative. Inputs like 15 months or 40 days are valid: these are **quantities**, not month/day fields of a specific calendar date.

Illustrative example inside a Java method:

```java
Period grace = Period.ofDays(10);
Period renewal = Period.ofMonths(15);
Period mixed = Period.of(1, 2, 3);
```

You need `import java.time.Period;` when using the short name. The snippet above only shows illustrative statements; the full runnable program is in section 5.

### Reading Components Without Automatic Unit Conversion

Use `getYears()`, `getMonths()`, and `getDays()` to retrieve the exact stored components. For `Period.of(1, 15, 40)`, the three values are `1`, `15`, and `40`, respectively.

`getMonths()` does not return the total number of months, and `getDays()` does not return the total number of days for the entire period. If you need the total months from the years/months parts, you can use `toTotalMonths()`; the days part is not added to that result. There is no general rule converting a month to 30 days or a year to 365 days.

Creating values and calling `parse` do not automatically normalize months into years. Therefore, `Period.ofMonths(15)` has the string representation `P15M`, and does not automatically become `P1Y3M`. Only if you explicitly call `normalized()` are the years and months normalized; days remain separate. The two objects `Period.ofMonths(15)` and `Period.of(1, 3, 0)` have different component structures, so `equals` returns `false`. Keep this in mind when checking values received from configuration.

## 3. Reading the PnYnMnD String Structure

The string `P1Y2M3D` can be read from left to right:

| Part | Meaning |
|---|---|
| `P` | Starts a period representation |
| `1Y` | 1 year |
| `2M` | 2 months |
| `3D` | 3 days |

The order is years (`Y`), months (`M`), weeks (`W`), and then days (`D`). Unused components can be omitted, but at least one component must be present. To represent a zero period, write `P0D` or another valid zero component; `P` alone is incomplete.

Common cases:

| Input string | Result of `Period.parse(...)` when printed | Explanation |
|---|---|---|
| `P2Y` | `P2Y` | 2 years |
| `P6M` | `P6M` | 6 months |
| `P3W` | `P21D` | Weeks are converted to days |
| `P10D` | `P10D` | 10 days |
| `P1Y0M3D` | `P1Y3D` | Zero components are omitted when printed |
| `P0M` | `P0D` | Zero value has a unified string representation |
| `P15M` | `P15M` | Not automatically normalized into years/months |

This is period syntax, not a date. A date string like `2026-10-25` requires a type such as `LocalDate`, whereas `P3M` is an amount of 3 months. `Period.parse` does not parse natural language like `3 months` and does not depend on locale settings to infer units.

### The Letter M in the Date Part vs. the Time Part

In a `Period` string, `M` means **months**. A string with a time part such as `PT15M` represents 15 minutes and belongs to `Duration`; it is not accepted by `Period.parse`. Do not add `T`, `H`, `S`, or fractional seconds to values intended for `Period`.

Similarly, `P1D` and `PT24H` should retain their distinct calendar-based and duration-based meanings. They are not interchangeable forms across all time-zone calculations.

### Forms Java Accepts Beyond the Basic Syntax

`Period.parse` accepts uppercase or lowercase letters, a leading sign, and individual component signs. Quantities must use ASCII digits and fit within the range that the method can represent as an `int`.

For example:

```java
Period a = Period.parse("p2m");      // P2M
Period b = Period.parse("-P1Y2M");   // P-1Y-2M
Period c = Period.parse("P-1Y2M");   // P-1Y2M
Period d = Period.parse("P1W2D");    // P9D
```

In `-P1Y2M`, the leading minus sign negates both the years and months parts. In `P-1Y2M`, only the years part is negative; the months part remains positive. Do not interpret these two strings as the same value.

Forms with per-component signs or mixing weeks with other units are supported by Java, but you should not assume every system claiming ISO-8601 support will accept them. When exchanging data, agree on the syntax subset both sides accept. In typical configuration, prefer uppercase letters and simple forms like `P3M`, `P1Y2M`, and `P10D` so readers can immediately see the meaning.

## 4. Converting Objects to Strings and Validating Bad Input

`toString()` returns a representation that can be parsed back by `Period.parse`. For example:

```java
Period original = Period.of(1, 2, 3);
String encoded = original.toString();
Period decoded = Period.parse(encoded);
boolean sameValue = original.equals(decoded); // true
```

The value is preserved across the object → string → object round trip. **The original string formatting is not necessarily preserved**: `P2W` becomes `P14D`, lowercase becomes uppercase, and zero components may disappear. If you need to preserve the exact text the user entered, store the original string separately; do not use `toString()` to recover the original formatting.

`Period.parse` throws `DateTimeParseException` when the string is syntactically invalid or cannot represent the requested value. Some typical invalid inputs:

| Input | Why it cannot be used with Period |
|---|---|
| `P` | No components present |
| `3M` | Missing `P` prefix |
| `P1D2M` | Wrong unit order |
| `P1.5M` | Non-integer component |
| `PT15M` | Contains a time part, not part of `Period` |
| `2026-10-25` | A date string, not a calendar amount |
| ` P3M ` | Leading/trailing whitespace; the parser does not trim it |

`null` is a separate case and causes `NullPointerException`. For external input, check that a value is present first, then handle syntax errors with an appropriate exception. If an interface allows ignoring leading/trailing whitespace, calling `strip()` should be an explicit choice in the input-handling layer, not behavior assumed of `Period.parse`.

**Successful parsing alone is not enough to satisfy business rules.** For example, `P-3M`, `P0D`, and `P1Y-2M` may be valid `Period` values, yet violate a rule stating “a renewal period must be positive and have no negative components”. When that is the rule, you can check `isZero()` and `isNegative()` after parsing. `isNegative()` returns `true` when at least one component is negative; it does not compute a hypothetical total number of days to determine the sign.

## 5. Complete Runnable Program

Save the following into `PeriodCreationDemo.java`. The program uses Java 17 or later and requires no external libraries.

```java
import java.time.Period;
import java.time.format.DateTimeParseException;

public class PeriodCreationDemo {
    public static void main(String[] args) {
        Period plan = Period.of(1, 2, 3);
        System.out.println("created=" + plan);
        System.out.printf("parts=%d,%d,%d%n",
                plan.getYears(), plan.getMonths(), plan.getDays());

        Period weeks = Period.ofWeeks(2);
        System.out.println("weeks=" + weeks);
        System.out.println("parsedWeeks=" + Period.parse("P2W"));
        System.out.println("months=" + Period.ofMonths(15));
        System.out.println("parsed=" + Period.parse("P1Y2M3D"));
        System.out.println("zero=" + Period.ZERO);

        String encoded = plan.toString();
        System.out.println("roundTrip=" + plan.equals(Period.parse(encoded)));
        System.out.println("leadingSign=" + Period.parse("-P1Y2M"));
        System.out.println("componentSign=" + Period.parse("P-1Y2M"));

        try {
            Period.parse("PT15M");
        } catch (DateTimeParseException e) {
            System.out.println("invalid=DateTimeParseException");
        }

        System.out.println("renewal=" + parseRenewal("P3M"));
        try {
            parseRenewal("P1Y-2M");
        } catch (IllegalArgumentException e) {
            System.out.println("rejected=" + e.getMessage());
        }
    }

    static Period parseRenewal(String text) {
        if (text == null) {
            throw new IllegalArgumentException("missing period");
        }
        Period value = Period.parse(text);
        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException("period must be positive");
        }
        return value;
    }
}
```

Compile and run in the directory containing the file:

```shell
javac PeriodCreationDemo.java
java PeriodCreationDemo
```

Expected output:

```text
created=P1Y2M3D
parts=1,2,3
weeks=P14D
parsedWeeks=P14D
months=P15M
parsed=P1Y2M3D
zero=P0D
roundTrip=true
leadingSign=P-1Y-2M
componentSign=P-1Y2M
invalid=DateTimeParseException
renewal=P3M
rejected=period must be positive
```

`parseRenewal` demonstrates two independent steps: parsing the string structure, then applying the rules of a specific feature. The policy “no negative components and not zero” is a choice made for this example; `Period` itself still allows negative components. For syntactically invalid strings, `DateTimeParseException` is still propagated so the input layer can report a formatting error.

## 6. Practice Exercises

Before running, predict the output of the following expressions and then verify:

```java
System.out.println(Period.of(0, 15, 0));
System.out.println(Period.parse("P3W2D"));
System.out.println(Period.parse("P0Y0M0D"));
System.out.println(Period.parse("-P2M5D"));
System.out.println(Period.parse("P15M").getMonths());
```

Answers:

```text
P15M
P23D
P0D
P-2M-5D
15
```

Explain in your own words why the second result no longer has a week unit and why the last result is `15` instead of `3`. Then try `P1D2M` and verify that this is a syntax error, distinct from a valid value rejected by `parseRenewal`.

## 7. Key Takeaways

- Choose the factory method based on the units you have; keep the meaning of years/months/days clear from the moment data is received.
- `Period` has exactly three components—years, months, and days; weeks are converted to days upon creation or parsing.
- `P3M` is 3 months; `PT3M` is not part of the syntax that `Period` parses.
- `parse` does not automatically normalize months, trim whitespace, or enforce business rules.
- `toString()` preserves the value for round-trip parsing, though it may change the formatting compared to the input string.
- Reading a component is not the same as converting the entire period into a single unit.

Refer to the method contracts and supported syntax at [Java SE 21 — Period](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html).
