# Normalizing Years and Months with `Period.normalized()`

## 1. Understanding Normalization Properly

`Period` represents an amount of time in the ISO calendar using three components: years, months, and days. When entering a renewal term of 17 months, you may want to display it as 1 year and 5 months; when adding more months to a term that already has years, the months part can also exceed 11.

`normalized()` returns a `Period` value whose years–months part is normalized according to the relationship **12 months = 1 year**. The days part is preserved. The original object is not modified because `Period` is immutable. These API rules are described at [Java SE 21 — Period.normalized()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html#normalized()).

Self-constructed example in this lesson:

```text
1 year + 17 months + 40 days
          ↓ normalized()
2 years +  5 months + 40 days
```

Both representations have a years–months part corresponding to 29 months. There is no step that converts 40 days into 1 month and 10 days: knowing which months 40 days span requires a specific start date and calendar.

## 2. Calculation Mechanism: Combine Months Then Split Again

You can compute the result manually to verify API usage with the following formula. This is an explanatory model; application code should call `normalized()` directly:

```java
// Illustration inside a method; p is an existing Period.
long totalMonths = p.getYears() * 12L + p.getMonths();
int years = Math.toIntExact(totalMonths / 12);
int months = (int) (totalMonths % 12);
Period result = Period.of(years, months, p.getDays());
```

The `L` suffix ensures the multiplication is performed in `long`, avoiding intermediate `int` overflow. After successful normalization:

- Total months are preserved: `p.toTotalMonths() == p.normalized().toTotalMonths()`.
- The months part is in the range `-11` to `11`.
- If both years and months are non-zero, they have the same sign.
- The days part is identical to the original days part, even if negative or greater than 31.
- Normalizing again does not change the value: `n.equals(n.normalized())` is `true`.

You should not simply take `getMonths() / 12` and add it to the old years: that calculation can miss cancellation between positive years and negative months. For example, `(1 year, -17 months)` must first be combined into `12 - 17 = -5` months, and then split back into `(0 years, -5 months)`.

### Negative Numbers and the Sign of the Remainder

Integer division in Java truncates toward 0. Therefore, `-17 / 12` equals `-1`, and `-17 % 12` equals `-5`. The result is negative 1 year and negative 5 months, not negative 2 years and positive 7 months. Do not replace this division with `Math.floorDiv` if you want to accurately model `normalized()`.

| Created value | Total months before normalization | `normalized()` result | What to observe |
| --- | ---: | --- | --- |
| `Period.ofMonths(24)` | 24 | `P2Y` | Zero months are omitted when printed |
| `Period.ofMonths(-17)` | -17 | `P-1Y-5M` | Negative years and months share the same sign |
| `Period.of(1, -17, 4)` | -5 | `P-5M4D` | Positive days are not changed to match the sign of months |
| `Period.of(-1, 17, -4)` | 5 | `P5M-4D` | Negative days remain unchanged |
| `Period.of(1, -12, 0)` | 0 | `P0D` | Years and months cancel out completely |
| `Period.ofDays(40)` | 0 | `P40D` | 40 days do not become months |

The `P...Y...M...D` strings in the table are how `Period.toString()` formats values; `M` here stands for months. Years–months normalization is neither an absolute-value operation nor does it guarantee that all components of the entire `Period` have the same sign.

## 3. Complete Verification Program

Save the following code to `PeriodNormalizedDemo.java`. The program uses APIs available in Java 17 and later, with no external libraries required:

```java
import java.time.LocalDate;
import java.time.Period;

public class PeriodNormalizedDemo {
    public static void main(String[] args) {
        Period original = Period.of(1, 17, 40);
        Period normalized = original.normalized();
        System.out.println("original = " + original);
        System.out.println("normalized = " + normalized);
        System.out.println("total months = " + original.toTotalMonths()
                + " -> " + normalized.toTotalMonths());
        System.out.println("normalized again = "
                + normalized.equals(normalized.normalized()));

        Period[] samples = {
            Period.ofMonths(24),
            Period.ofMonths(-17),
            Period.of(1, -17, 4),
            Period.of(-1, 17, -4),
            Period.of(1, -12, 0),
            Period.of(0, 0, 40)
        };
        for (Period sample : samples) {
            System.out.println(sample + " -> " + sample.normalized());
        }

        Period a = Period.ofMonths(17);
        Period b = Period.of(1, 5, 0);
        System.out.println("equals before = " + a.equals(b));
        System.out.println("equals after = "
                + a.normalized().equals(b.normalized()));

        LocalDate start = LocalDate.of(2024, 1, 31);
        System.out.println("date before = " + start.plus(original));
        System.out.println("date after = " + start.plus(normalized));

        try {
            Period.of(Integer.MAX_VALUE, 12, 0).normalized();
        } catch (ArithmeticException ex) {
            System.out.println("overflow = ArithmeticException");
        }
    }
}
```

Compile and run in the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 PeriodNormalizedDemo.java
java PeriodNormalizedDemo
```

Expected output:

```text
original = P1Y17M40D
normalized = P2Y5M40D
total months = 29 -> 29
normalized again = true
P24M -> P2Y
P-17M -> P-1Y-5M
P1Y-17M4D -> P-5M4D
P-1Y17M-4D -> P5M-4D
P1Y-12M -> P0D
P40D -> P40D
equals before = false
equals after = true
date before = 2026-08-09
date after = 2026-08-09
overflow = ArithmeticException
```

`original` remains `P1Y17M40D`, proving that the call created a result value without modifying the input. Both representations advance `2024-01-31` to `2026-08-09` in the example: the years–months part corresponds to 29 months, followed by adding 40 days. Normalization does not require knowing a start date; adding to a date is what requires a start date.

Do not generalize this example into a rule that every sequence of separate addition calls is equivalent. For instance, chaining `plusYears` and then `plusMonths` manually can trigger end-of-month adjustments at intermediate steps. In the program, we add the entire `Period` at once using `start.plus(period)`.

## 4. When to Call It and When to Preserve the Input

### When a consistent years–months representation is needed

A screen might accept a term in months but display it in years and months. For an input of 17 months, calling `normalized()` before reading `getYears()` and `getMonths()` yields 1 year and 5 months. If you only need the total number of months, use `toTotalMonths()`; that method does not alter the `Period` and does not include the days part in the total months.

Creation or addition operations do not guarantee automatic month normalization. Example illustration inside a method:

```java
Period term = Period.ofMonths(11).plusMonths(8);
System.out.println(term);              // P19M
term = term.normalized();
System.out.println(term);              // P1Y7M
```

You must use the returned result. Writing only `term.normalized();` and continuing to use `term` will keep the old value.

### When comparing or using as a key

The verification program shows that `Period.ofMonths(17)` is not `equals` to `Period.of(1, 5, 0)` before normalization; after normalization, they are equal. When business logic treats both forms as the same term, you can normalize both before comparing or before inserting them into a set or map key. Normalizing only one side is not enough if the other side still has an unnormalized representation.

That is a decision about data representation. If you need to preserve the “17 months” term entered by the user, store the raw input separately instead of replacing every value with “1 year 5 months”. Also, do not use `normalized()` to conclude that 1 month equals 30 days: the days part remains independent.

## 5. Limitations and Common Pitfalls

**Overflow can still occur.** Each component of `Period` is stored as an `int`. The last example in the program can construct `(Integer.MAX_VALUE years, 12 months, 0 days)`, but normalizing it requires adding 1 more year and therefore throws `ArithmeticException`. Only catch the exception when the program has a clear way to handle invalid data; do not turn an overflow error into `Period.ZERO`, as doing so would corrupt the term.

**Does not compute duration in seconds.** The normalized result is still a calendar-based amount of time, not a `Duration`, and does not provide a total number of seconds. If the problem asks how many actual days elapse from a specific starting point, determine the starting point and calculate on dates; dividing the number of days by 30 is not `Period` normalization.

**Do not use it to validate whether a term is business-valid.** `P5M-4D` may be a valid normalized result yet still violate an application rule requiring “all components must be non-negative.” Business validation is a separate step after clarifying whether the rule applies to the raw data or the normalized data.

## 6. Self-Practice

Before running, predict the value of `Period.of(2, -25, 7).normalized()` and explain why the days part does not change. The answer is `P-1M7D`: `2 * 12 - 25 = -1` month, while the 7 days remain unchanged.

Next, predict `Period.of(0, 12, -365).normalized()`. The answer is `P1Y-365D`, not `P0D`: the operation only converts 12 months into 1 year and does not cancel years against 365 days. These two exercises help check whether you can distinguish normalizing the years–months representation from calculating the distance between dates.
