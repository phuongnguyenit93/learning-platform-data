# HALF_EVEN and Even-Digit Selection in BigDecimal

## 1. Why Is the HALF_EVEN Rule Needed?

When representing or computing decimal numbers with a limited number of digits, digits sometimes have to be discarded. Usually we round to the value **nearest to the original number**. However, there are values that lie **exactly halfway between two valid results** (called *halfway* or a *tie*): an extra rule is needed to choose one side.

**RoundingMode.HALF_EVEN** in Java is the *round to nearest, ties to even* rule: **choose the nearest result; if both sides are equidistant, choose the result whose last retained digit is even** (0, 2, 4, 6, 8). This is also known as *round half to even* or *banker's rounding*.

Scope: Java 17+, `java.math.BigDecimal`, `java.math.RoundingMode`, `java.math.MathContext`. This lesson explains exactly which digit must be even, cases that are not actually ties, handling negative numbers, differences from HALF_UP/HALF_DOWN, and choosing when to round in applications.

## 2. Mechanism: Nearest First, Even Only on a Tie

Suppose we round a value to an integer. Values with a fractional part other than 0.5 are rounded to the closer integer. If the fractional part is exactly 0.5, the two nearest integers are equidistant, so HALF_EVEN picks the even one:

| Original number | Two nearest results | HALF_EVEN | Reason |
| --- | --- | ---: | --- |
| 2.4 | 2 and 3 | 2 | Distance to 2 is smaller |
| 2.5 | 2 and 3 | 2 | Tie; 2 is even |
| 3.5 | 3 and 4 | 4 | Tie; 4 is even |
| 4.5 | 4 and 5 | 4 | Tie; 4 is even |
| 5.5 | 5 and 6 | 6 | Tie; 6 is even |
| -2.5 | -3 and -2 | -2 | Tie; digit 2 is even |
| -3.5 | -4 and -3 | -4 | Tie; digit 4 is even |
| 2.51 | 2 and 3 | 3 | Closer to 3; not a tie |

**HALF_EVEN does not mean "always round to an even integer".** When the value is not a tie, a result with an odd digit is still chosen if it is closer, such as 2.51 → 3.

When keeping decimal places, evenness applies to **the last retained digit**, not the integer part. If rounding 1.25 to one decimal place, we choose between 1.2 and 1.3: 1.2 has tenths digit 2 (even), so it is chosen. With 1.35, we choose 1.4 because the digit 4 is even.

### Checking Exact Ties

With a target scale of 2, two adjacent decimal numbers are 0.01 apart; the midpoint is 0.005 from each side.

- **1.005**: halfway between 1.00 and 1.01 → 1.00 (hundredths digit is 0, even).
- **1.015**: halfway between 1.01 and 1.02 → 1.02 (digit 2, even).
- **1.0050**: still equals 1.005, so still a tie → 1.00.
- **1.0051**: closer to 1.01 → 1.01, even though the hundredths digit is 1 (odd).
- **1.0049**: closer to 1.00 → 1.00.

If the first discarded digit is 5 but **the discarded part after the digit 5 is still non-zero**, the value does not lie exactly halfway. Do not decide by even/odd before determining distance.

## 3. Using setScale(scale, RoundingMode.HALF_EVEN)

In BigDecimal, the method `setScale(int newScale, RoundingMode roundingMode)` produces a representation with the requested scale. A scale of 0 corresponds to no digits after the decimal point; scale 1 keeps one digit; scale 2 keeps two digits. Negative scale lets you round to tens, hundreds.

For example, `x.setScale(2, RoundingMode.HALF_EVEN)` requests keeping exactly two decimal places and uses HALF_EVEN if significant digits must be discarded. If only increasing the scale such as 1.2 → 1.200, no value is discarded, so no nearest-choice rounding is performed. BigDecimal is **immutable**: the method returns a value without modifying the original object.

### Java 17 Example: Ties When Rounding Integers

Save under the name `HalfEvenIntegerDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenIntegerDemo {
    public static void main(String[] args) {
        String[] inputs = {
            "2.4", "2.5", "3.5", "4.5",
            "5.5", "-2.5", "-3.5", "2.51"
        };

        for (String input : inputs) {
            BigDecimal x = new BigDecimal(input);
            BigDecimal rounded = x.setScale(0, RoundingMode.HALF_EVEN);
            System.out.println(input + " -> " + rounded.toPlainString());
        }
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac HalfEvenIntegerDemo.java
java HalfEvenIntegerDemo
~~~

Exact output:

~~~text
2.4 -> 2
2.5 -> 2
3.5 -> 4
4.5 -> 4
5.5 -> 6
-2.5 -> -2
-3.5 -> -4
2.51 -> 3
~~~

The 2.5/3.5 pair proves HALF_EVEN does not default to always rounding up or down. The two negative values prove it is also not a rule that always rounds toward 0.

## 4. Decimal Cases, Negative Signs, and Carrying

With a target scale of 1, the last retained digit is in the tenths place. Similarly, with a target scale of 2, the hundredths place is examined. Even digits can appear after the decimal point, whether the integer part is even or odd.

| Value | Target scale | HALF_EVEN result | Reason |
| --- | ---: | --- | --- |
| 1.25 | 1 | 1.2 | Tie, digit 2 is even |
| 1.35 | 1 | 1.4 | Tie, digit 4 is even |
| 1.2500 | 1 | 1.2 | Trailing zeros do not break the tie |
| 1.2501 | 1 | 1.3 | Greater than midpoint; closer to 1.3 |
| 1.2499 | 1 | 1.2 | Less than midpoint; closer to 1.2 |
| -1.25 | 1 | -1.2 | Tie, digit 2 is even |
| -1.35 | 1 | -1.4 | Tie, digit 4 is even |
| 9.95 | 1 | 10.0 | Tie between 9.9 and 10.0; digit 0 is even |
| 8.235 | 2 | 8.24 | Tie between 8.23 and 8.24; 4 is even |
| 8.245 | 2 | 8.24 | Tie between 8.24 and 8.25; 4 is even |

Create `HalfEvenDecimalDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenDecimalDemo {
    static void show(String source) {
        BigDecimal number = new BigDecimal(source);
        System.out.println(source + " -> "
                + number.setScale(1, RoundingMode.HALF_EVEN).toPlainString());
    }

    public static void main(String[] args) {
        show("1.25");
        show("1.35");
        show("1.2500");
        show("1.2501");
        show("1.2499");
        show("-1.25");
        show("-1.35");
        show("9.95");
    }
}
~~~

~~~bash
javac HalfEvenDecimalDemo.java
java HalfEvenDecimalDemo
~~~

Output:

~~~text
1.25 -> 1.2
1.35 -> 1.4
1.2500 -> 1.2
1.2501 -> 1.3
1.2499 -> 1.2
-1.25 -> -1.2
-1.35 -> -1.4
9.95 -> 10.0
~~~

With 9.95 → 10.0, pay attention to **carrying**: incrementing digits to the left is valid. When keeping one fractional digit, the last digit of 10.0 is 0, satisfying the even criterion.

## 5. Comparing HALF_EVEN, HALF_UP, and HALF_DOWN

All three belong to the group that picks the nearest number when not tied. When exactly tied:

- **HALF_UP**: picks the option farther from 0.
- **HALF_DOWN**: picks the option closer to 0.
- **HALF_EVEN**: picks the option whose last retained digit is even.

| Value → scale 0 | HALF_UP | HALF_DOWN | HALF_EVEN |
| --- | ---: | ---: | ---: |
| 2.5 | 3 | 2 | 2 |
| 3.5 | 4 | 3 | 4 |
| -2.5 | -3 | -2 | -2 |
| -3.5 | -4 | -3 | -4 |
| 2.6 | 3 | 3 | 3 |

Do not confuse **HALF_UP** with **UP**: `RoundingMode.UP` rounds away from 0 whenever discarding any non-zero part, even without a tie. Similarly, `RoundingMode.DOWN` rounds toward 0 and is not like `HALF_DOWN`.

Create `HalfEvenModesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenModesDemo {
    static void compare(String text) {
        BigDecimal x = new BigDecimal(text);
        String up = x.setScale(0, RoundingMode.HALF_UP).toPlainString();
        String down = x.setScale(0, RoundingMode.HALF_DOWN).toPlainString();
        String even = x.setScale(0, RoundingMode.HALF_EVEN).toPlainString();
        System.out.println(text + ": UP=" + up
                + ", DOWN=" + down + ", EVEN=" + even);
    }

    public static void main(String[] args) {
        compare("2.5");
        compare("3.5");
        compare("-2.5");
        compare("-3.5");
        compare("2.6");
    }
}
~~~

~~~bash
javac HalfEvenModesDemo.java
java HalfEvenModesDemo
~~~

Output:

~~~text
2.5: UP=3, DOWN=2, EVEN=2
3.5: UP=4, DOWN=3, EVEN=4
-2.5: UP=-3, DOWN=-2, EVEN=-2
-3.5: UP=-4, DOWN=-3, EVEN=-4
2.6: UP=3, DOWN=3, EVEN=3
~~~

Two modes can produce identical results in an isolated case without being equivalent. Always test both kinds of ties (old last digit even/odd) and non-tie values.

## 6. HALF_EVEN with MathContext: Distinguishing Precision from Scale

`setScale(2, HALF_EVEN)` keeps **two digits after the decimal point**. `MathContext(4, HALF_EVEN)` keeps at most **four significant digits** counting from the first non-zero digit. These are two completely different limiting rules:

- 12.345 with scale 2 → 12.34.
- 12.345 with precision 4 → 12.34, coincidentally matching because the fourth significant digit happens to be the hundredths place.
- 123.45 with scale 2 → 123.45; with precision 4 → 123.4.
- 123.55 with precision 4 → 123.6: the two results 123.5 and 123.6 are equidistant from 123.55, digit 6 is even.

`BigDecimal.round(MathContext)` rounds according to precision and rounding mode; operations supporting `MathContext` can also round results according to this context. Precision 0 in `MathContext.UNLIMITED` denotes unlimited significant digits; the rounding rule is not applied merely for precision. If `UNNECESSARY` is used and non-zero digits actually need to be discarded, Java throws `ArithmeticException`.

Create `HalfEvenPrecisionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class HalfEvenPrecisionDemo {
    public static void main(String[] args) {
        BigDecimal first = new BigDecimal("12.345");
        BigDecimal second = new BigDecimal("12.355");
        BigDecimal large = new BigDecimal("123.45");
        MathContext mc = new MathContext(4, RoundingMode.HALF_EVEN);

        System.out.println("first scale 2  = "
                + first.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("second scale 2 = "
                + second.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("first prec 4   = " + first.round(mc));
        System.out.println("second prec 4  = " + second.round(mc));
        System.out.println("large prec 4   = " + large.round(mc));
    }
}
~~~

~~~bash
javac HalfEvenPrecisionDemo.java
java HalfEvenPrecisionDemo
~~~

Output:

~~~text
first scale 2  = 12.34
second scale 2 = 12.36
first prec 4   = 12.34
second prec 4  = 12.36
large prec 4   = 123.4
~~~

Choose `setScale` when there is a rule on the number of fractional digits; choose `MathContext` when limiting the number of **significant** digits in a calculation. Do not swap one API for the other just because both support HALF_EVEN.

## 7. HALF_EVEN in BigDecimal Division

Some divisions cannot be represented as a finite decimal number (for example 1/3). `BigDecimal.divide(divisor)` can throw `ArithmeticException` when there is no exact finite decimal result. You can specify scale and rounding mode in the `divide(divisor, scale, roundingMode)` overload.

For example: 1/8 = 0.125 lies halfway between 0.12 and 0.13 → 0.12 (2 is even). 3/8 = 0.375 lies halfway between 0.37 and 0.38 → 0.38 (8 is even).

Create `HalfEvenDivisionDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenDivisionDemo {
    public static void main(String[] args) {
        BigDecimal eight = new BigDecimal("8");
        BigDecimal first = BigDecimal.ONE.divide(
                eight, 2, RoundingMode.HALF_EVEN);
        BigDecimal second = new BigDecimal("3").divide(
                eight, 2, RoundingMode.HALF_EVEN);
        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_EVEN);

        System.out.println("1 / 8 = " + first);
        System.out.println("3 / 8 = " + second);
        System.out.println("1 / 3 = " + third);
    }
}
~~~

~~~bash
javac HalfEvenDivisionDemo.java
java HalfEvenDivisionDemo
~~~

Output:

~~~text
1 / 8 = 0.12
3 / 8 = 0.38
1 / 3 = 0.33
~~~

1/3 is rounded to 0.33 because it is closer to 0.33 than 0.34, independent of evenness. To know how many digits to keep and when to round, you must rely on output/consistency requirements of the business logic.

## 8. Why Is It Also Called Banker's Rounding?

If data has many positive values landing exactly at the midpoint, always rounding away from 0 via HALF_UP can create an upward bias in the sum. HALF_EVEN chooses the upward or downward direction based on the evenness of the last retained digit. With a balanced distribution of ties, this approach **can reduce accumulated bias**.

For example, consider four values to be rounded to integers:

| Calculation | Values | Sum |
| --- | --- | ---: |
| Unrounded | 1.5, 2.5, 3.5, 4.5 | 12 |
| HALF_UP | 2, 3, 4, 5 | 14 |
| HALF_EVEN | 2, 2, 4, 4 | 12 |

This is an illustration, **not a proof that HALF_EVEN always preserves the sum or is completely unbiased**. Results depend on the data, especially when ties cluster around a group of digits. The name "banker's rounding" also does not mean all banks, accounting standards, or tax rules mandate HALF_EVEN; you must follow actual business rules.

### Rounding Each Item Differs from Rounding the Total

If there are three items of 1.005 and an amount with two fractional digits is needed:

- Round each item with HALF_EVEN: each item is 1.00; the total equals **3.00**.
- Sum the original values and round once: 3.015 → **3.02**.

Create `HalfEvenTotalsDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenTotalsDemo {
    public static void main(String[] args) {
        BigDecimal[] items = {
            new BigDecimal("1.005"),
            new BigDecimal("1.005"),
            new BigDecimal("1.005")
        };

        BigDecimal rawTotal = BigDecimal.ZERO;
        BigDecimal roundedEachTotal = BigDecimal.ZERO;

        for (BigDecimal item : items) {
            rawTotal = rawTotal.add(item);
            roundedEachTotal = roundedEachTotal.add(
                    item.setScale(2, RoundingMode.HALF_EVEN));
        }

        BigDecimal roundedAtEnd =
                rawTotal.setScale(2, RoundingMode.HALF_EVEN);

        System.out.println("raw total        = " + rawTotal);
        System.out.println("round each, sum  = " + roundedEachTotal);
        System.out.println("sum, round once  = " + roundedAtEnd);
    }
}
~~~

~~~bash
javac HalfEvenTotalsDemo.java
java HalfEvenTotalsDemo
~~~

Output:

~~~text
raw total        = 3.015
round each, sum  = 3.00
sum, round once  = 3.02
~~~

Both roundings follow HALF_EVEN. Choosing **when rounding occurs** (per line, per transaction, or on the total) affects the result and must be clearly specified from business rules. Avoid intermediate roundings when not mandatory, so as not to lose precision needed for later calculations.

## 9. Avoid Creating BigDecimal from double When Exact Decimal Ties Matter

Many decimal numbers cannot be represented exactly in the binary system of `double`. Thus, `new BigDecimal(2.675)` creates a BigDecimal representing the exact **received binary double value**, which is slightly less than 2.675. When rounding to two digits, this number is closer to 2.67; HALF_EVEN does not apply tie-breaking because in fact there is no tie.

Conversely, `new BigDecimal("2.675")` keeps 2.675 exactly: it is halfway between 2.67 and 2.68, so HALF_EVEN picks 2.68. `BigDecimal.valueOf(2.675)` uses the canonical decimal representation of double and therefore also gives 2.68 in the example, though that approach cannot recover any precision already lost from earlier data.

Create `HalfEvenInputDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class HalfEvenInputDemo {
    public static void main(String[] args) {
        BigDecimal exact = new BigDecimal("2.675");
        BigDecimal fromDouble = new BigDecimal(2.675);
        BigDecimal viaValueOf = BigDecimal.valueOf(2.675);

        System.out.println("String  = "
                + exact.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("double  = "
                + fromDouble.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("valueOf = "
                + viaValueOf.setScale(2, RoundingMode.HALF_EVEN));
    }
}
~~~

~~~bash
javac HalfEvenInputDemo.java
java HalfEvenInputDemo
~~~

Output:

~~~text
String  = 2.68
double  = 2.67
valueOf = 2.68
~~~

When decimal digit control is needed (especially for monetary amounts), prefer BigDecimal data created from exact decimal strings or clearly scaled integer sources, avoiding injecting binary error into ties.

## 10. Common Mistakes

1. **Assuming a first discarded digit of 5 is guaranteed to be a tie.** For example, 1.2501 has non-zero digits after 5 so the closer number must be chosen, i.e., 1.3 at scale 1.
2. **Checking evenness before determining distance.** 2.51 → 3, even though 3 is odd; the reason is nearest.
3. **Checking evenness of the integer part regardless of scale.** 1.25 → 1.2 at scale 1 because the tenths digit is 2, not because the integer part is 1.
4. **Thinking HALF_EVEN always rounds down.** 3.5 → 4, 1.35 → 1.4, and 9.95 → 10.0.
5. **Thinking negative numbers always round toward 0.** -3.5 → -4, whereas -2.5 → -2.
6. **Confusing HALF_UP with UP, HALF_DOWN with DOWN.** The two modes without HALF do not require a tie to round in that direction.
7. **Confusing precision with scale.** MathContext precision counts significant digits; setScale specifies fractional decimal digits.
8. **Using `new BigDecimal(double)` for decimal constants.** The binary value may differ very slightly yet enough to alter boundary results.
9. **Rounding across multiple steps without a policy.** The sum after rounding each item can differ from rounding the total once.
10. **Forgetting to save the return value.** BigDecimal is immutable: `value.setScale(...)` does not update `value`; use a new variable or appropriate assignment.
11. **Using HALF_EVEN for all money out of habit.** You must verify transaction type requirements, reporting standards, and current system regulations.

## 11. Self-Check Questions

**Question 1.** Round `4.5` and `5.5` to scale 0 using HALF_EVEN. Why do the results go in opposite directions?

**Answer:** 4 and 6. Both are ties, but the two adjacent pairs are (4, 5) and (5, 6) respectively; the even digit is chosen.

**Question 2.** Round `8.235` and `8.245` to scale 2 using HALF_EVEN.

**Answer:** Both are 8.24: the first value lies between 8.23 and 8.24, the second lies between 8.24 and 8.25; the last digit 4 is even.

**Question 3.** Why does `1.2500` → `1.2` while `1.2501` → `1.3` at scale 1?

**Answer:** 1.2500 equals 1.25 exactly so it is a tie; 1.2501 is closer to 1.3 so the nearest rule decides.

**Question 4.** For `new BigDecimal("12.345")`, how does `setScale(2, HALF_EVEN)` differ from `round(new MathContext(2, HALF_EVEN))`?

**Answer:** The results are 12.34 and 12 respectively; the first keeps two fractional digits, the second keeps two significant digits.

**Question 5.** Does HALF_EVEN guarantee that the sum of line-rounded values equals the original sum rounded once?

**Answer:** No. Three values of 1.005 illustrate that the result can be 3.00 or 3.02 depending on when the rule is applied.

## 12. Takeaways

- **HALF_EVEN chooses the nearest result; on a tie, it chooses the last retained digit that is even.**
- Evenness **only resolves ties**, not replacing the distance rule.
- Use `setScale(scale, RoundingMode.HALF_EVEN)` to control digits after the decimal point; use `MathContext` to control significant digits.
- Accept exact decimal inputs and choose when rounding occurs according to business requirements.
- HALF_EVEN can reduce directional bias when processing many balanced ties, though it does not guarantee that every summed result matches unrounded data.

Official API documentation: Java SE 17 `java.math.RoundingMode`, `java.math.BigDecimal`, and `java.math.MathContext`.