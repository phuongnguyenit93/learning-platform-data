# UP and DOWN in Java: Rounding Away From or Toward 0

## 1. Goal and Meaning

When having to reduce the number of decimal places or significant digits, Java needs to know how to handle the discarded part. The two values `RoundingMode.UP` and `RoundingMode.DOWN` of `java.math.RoundingMode` describe **the rounding direction relative to 0**, not the increasing or decreasing direction on the number line.

- **UP — away from 0:** if the discarded part has any non-zero digit, increase the **absolute magnitude** of the result by one unit at the last retained position.
- **DOWN — toward 0:** drop the part exceeding the chosen precision, **without increasing** the last retained digit; in other words, truncate the fractional part toward 0.

For example, keeping **two digits after the decimal point**:

| Original number | UP | DOWN | Why? |
| --- | ---: | ---: | --- |
| 1.231 | 1.24 | 1.23 | Discarded part is 1; UP increases magnitude, DOWN keeps the retained part as is |
| -1.231 | -1.24 | -1.23 | UP moves more negative; DOWN moves closer to 0 |
| 1.239 | 1.24 | 1.23 | UP does not wait for the discarded digit to reach 5 |
| -1.239 | -1.24 | -1.23 | Rule is based on absolute value, applied symmetrically to negative numbers |
| 1.230 | 1.23 | 1.23 | Only zeros discarded so no value change needed |
| 0.001 | 0.01 | 0.00 | Even for very small non-zero numbers, UP still moves away from 0 |
| -0.001 | -0.01 | 0.00 | DOWN can produce a result of 0 |

Key point: **UP is not synonymous with a larger number; DOWN is not synonymous with a smaller number**. For negative numbers, UP typically gives a smaller number in arithmetic order, while DOWN gives a larger number.

## 2. Mechanism by Retained Position

Suppose only two digits after the decimal point are kept. For `3.141`, the part retained before rounding is `3.14`, and the discarded part is `0.001`.

- Using UP: the discarded part is non-zero, increment by one step `0.01` **away from 0** → `3.15`.
- Using DOWN: drop `0.001` **toward 0** → `3.14`.
- With `-3.141`: UP → `-3.15`, DOWN → `-3.14`.

One step here is determined by **the resolution of the result**: keeping two decimal places gives a step of `0.01`; keeping one decimal place gives a step of `0.1`; keeping the integer part gives a step of `1`. UP **always** increases by one step at the result's resolution whenever there is a non-zero part to discard, regardless of whether the first discarded digit is `1` or `9`.

For a non-zero number needing shortening, you can picture it as:

- `DOWN`: take the absolute value → truncate to the target resolution → restore the sign.
- `UP`: take the absolute value → if any non-zero part was truncated, increment by one step at the target resolution → restore the sign.

This is a conceptual way to think about it. In programs, use `BigDecimal` with `RoundingMode` instead of manually handling signs or multiplying/dividing by hand, especially at large magnitudes, negative values, and numbers with many digits.

## 3. Practice with BigDecimal on Java 17+

`BigDecimal` represents decimal numbers accurately in base 10 and has methods accepting `RoundingMode`. Use strings such as `new BigDecimal("1.231")` to preserve the exact written decimal value; avoid taking an imprecise `double` value and converting it to `BigDecimal` afterward.

Create the file `RoundingUpDownDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RoundingUpDownDemo {
    private static void show(String input) {
        BigDecimal value = new BigDecimal(input);
        BigDecimal up = value.setScale(2, RoundingMode.UP);
        BigDecimal down = value.setScale(2, RoundingMode.DOWN);

        System.out.println(input
                + " -> UP=" + up.toPlainString()
                + ", DOWN=" + down.toPlainString());
    }

    public static void main(String[] args) {
        for (String input : new String[]{
                "1.231", "-1.231", "1.239",
                "1.230", "0.001", "-0.001"}) {
            show(input);
        }

        BigDecimal seven = new BigDecimal("7");
        BigDecimal three = new BigDecimal("3");
        System.out.println("7 / 3 UP="
                + seven.divide(three, 2, RoundingMode.UP));
        System.out.println("7 / 3 DOWN="
                + seven.divide(three, 2, RoundingMode.DOWN));

        BigDecimal number = new BigDecimal("17.89");
        System.out.println("Precision 3 UP="
                + number.round(new MathContext(3, RoundingMode.UP)));
        System.out.println("Precision 3 DOWN="
                + number.round(new MathContext(3, RoundingMode.DOWN)));
    }
}
~~~

Run:

~~~bash
javac RoundingUpDownDemo.java
java RoundingUpDownDemo
~~~

Output:

~~~text
1.231 -> UP=1.24, DOWN=1.23
-1.231 -> UP=-1.24, DOWN=-1.23
1.239 -> UP=1.24, DOWN=1.23
1.230 -> UP=1.23, DOWN=1.23
0.001 -> UP=0.01, DOWN=0.00
-0.001 -> UP=-0.01, DOWN=0.00
7 / 3 UP=2.34
7 / 3 DOWN=2.33
Precision 3 UP=17.9
Precision 3 DOWN=17.8
~~~

Observations:

1. `setScale(2, mode)` keeps **two digits after the decimal point**, not two significant digits.
2. `1.230` becomes `1.23` in both modes: the trailing zero only affected the initial representation, not changing the value.
3. `-0.001` with DOWN becomes `0.00`; `BigDecimal` does not maintain a separate negative value for zero.
4. `7 / 3` has a non-zero remainder: at scale 2, UP is `2.34`, DOWN is `2.33`.
5. `MathContext(3, ...)` rounds by **three significant digits**. For `17.89`, UP becomes `17.9`, DOWN becomes `17.8`.

## 4. Scale and Precision Are Two Different Requirements

### Scale: Number of Digits After the Decimal Point

`BigDecimal.setScale(int newScale, RoundingMode mode)` changes the scale. With `newScale = 2`:

- `new BigDecimal("123.456").setScale(2, UP)` → `123.46`.
- `new BigDecimal("123.456").setScale(2, DOWN)` → `123.45`.
- `new BigDecimal("-123.456").setScale(2, UP)` → `-123.46`.
- `new BigDecimal("-123.456").setScale(2, DOWN)` → `-123.45`.

If **increasing the scale**, for example `1.2` to scale 3, the result `1.200` simply has zeros appended; there is no need to choose up or down since no non-zero digits are lost. If decreasing scale when all discarded digits are 0, UP and DOWN also yield the same value.

Scale can be negative: `new BigDecimal("124").setScale(-1, RoundingMode.DOWN)` represents `1.2E+2`, i.e. **120**; using UP gives **130**. To display in plain decimal form, you can call `toPlainString()`.

### Precision: Total Number of Significant Digits

`MathContext(precision, mode)` constrains **the total significant digits of the result**, used with `round(context)` or an operation taking `MathContext`:

| Original value | Target | UP | DOWN |
| --- | --- | ---: | ---: |
| 17.89 | 3 significant digits | 17.9 | 17.8 |
| 0.01234 | 3 significant digits | 0.0124 | 0.0123 |
| -987.65 | 3 significant digits | -988 | -987 |

Do not confuse `setScale(3, ...)` with `MathContext(3, ...)`: scale 3 keeps **three digits after the decimal point**, while precision 3 keeps **three significant digits** depending on the number's magnitude. A `MathContext` with precision 0 means **unlimited precision**; in that case the rounding rule is not used to truncate digits.

## 5. How Do UP/DOWN and CEILING/FLOOR Differ?

Similar names easily cause bugs. `RoundingMode.CEILING` points toward **positive infinity**, `RoundingMode.FLOOR` points toward **negative infinity**; they are defined along the number line. UP and DOWN are defined by distance from 0.

Example rounding to integer (scale 0):

| Value | UP (away from 0) | DOWN (toward 0) | CEILING (+∞) | FLOOR (-∞) |
| --- | ---: | ---: | ---: | ---: |
| 2.1 | 3 | 2 | 3 | 2 |
| -2.1 | -3 | -2 | -2 | -3 |
| 2.0 | 2 | 2 | 2 | 2 |
| -2.0 | -2 | -2 | -2 | -2 |

For positive numbers, UP matches CEILING and DOWN matches FLOOR **when rounding at the same resolution**. For negative numbers, the pairing reverses. Therefore, a requirement to "always round up on the number line" must use CEILING, whereas a requirement to "always push magnitude away from 0" uses UP.

`RoundingMode.HALF_UP` is instead a rule for rounding **to the nearest value**, moving away from 0 in exact-half cases. For example, keeping two digits of `1.231`: UP → `1.24`, but HALF_UP → `1.23`. The word UP in HALF_UP does **not** make this rule behave like `RoundingMode.UP`.

## 6. Applying Properly to Division and Multi-Step Calculations

A decimal division may not terminate: `1 / 3` cannot be represented in finitely many decimal digits. With `BigDecimal`, you can specify scale and rounding mode:

~~~java
BigDecimal result = new BigDecimal("1")
        .divide(new BigDecimal("3"), 2, RoundingMode.UP);
// result = 0.34
~~~

If using `divide(BigDecimal divisor)` when the decimal result does not terminate, `BigDecimal` may throw `ArithmeticException`. Choosing the mode is a business decision: UP ensures the magnitude is not cut short at the target representation level, whereas DOWN truncates the excess.

For negative values, the rules remain the same: `-7 / 3` to scale 2 becomes `-2.34` with UP and `-2.33` with DOWN. Do not write logic like "add a small fraction to round up" across all signs, because for negative numbers, away from 0 is actually more negative.

Avoid rounding after **every intermediate step** if the problem requires an exact result at the end. For instance:

- First compute `1.234 + 1.234 = 2.468`, then use DOWN at scale 2 → `2.46`.
- If each number is truncated down to `1.23` before adding, the sum becomes `2.46`; same result in this example, though not always so.
- With `1.239 + 1.239 = 2.478`, applying UP **once at the end** gives `2.48`, while applying UP to each number gives `1.24 + 1.24 = 2.48`; also matching in this case.
- A case showing a clear difference: `1.231 + 1.231 = 2.462`; UP at the end gives `2.47`, whereas UP on each number gives `1.24 + 1.24 = 2.48`.

Therefore, you must specify **when rounding occurs**, **resolution**, and **mode**. Addition, subtraction, and multiplication between `BigDecimal` values can preserve decimal exactness without forced rounding; round only at the required boundaries. If you pass `MathContext` directly into an operation, the result of that specific operation will be rounded according to the context.

## 7. How to Choose UP or DOWN in Practice

Choose the mode from the specification rather than from how the name feels:

- **UP** when explicitly required that a non-zero value, after shortening, must have **magnitude no smaller than** the original magnitude at the target resolution; for example, a convention rounding resource quantities to ensure sufficient capacity. Verify both negative signs and business intent.
- **DOWN** when required to **truncate** excess digits so the result moves toward 0; useful for algorithms that need to discard digits beyond target precision.
- If the requirement is **nearest**, evaluate modes like `HALF_UP`, `HALF_EVEN`, etc. UP/DOWN both introduce a one-way bias in magnitude when rounding repeatedly.
- In finance, billing, and taxes, never assume on your own that UP or DOWN is the default standard. The rounding rule must follow the corresponding contract, policy, or regulation; operations with negative values (adjustments, refunds, credits) are especially prone to inverting meaning.

A check question before coding: **"When the discarded digits contain a non-zero digit, should the absolute value of the result increase or decrease (stay on the side closer to 0)?"** If magnitude should increase, choose UP; if truncating toward 0, choose DOWN.

## 8. Common Mistakes

**Mistake 1 — Assuming UP always increases the numeric value.** `-1.231` with UP at scale 2 becomes `-1.24`, which is **smaller** than `-1.231` on the number line. For increasing along the number line, consider CEILING.

**Mistake 2 — Thinking UP only rounds when the discarded digit is 5 or greater.** UP applies whenever **any** non-zero part is discarded. `2.001` at scale 2 with UP is still `2.01`. The threshold-5 rule belongs to nearest-rounding modes.

**Mistake 3 — Using `double` to store decimal values and assuming they are exact.** Many base-10 numbers cannot be represented accurately in binary floating-point. For business decimal values, construct `BigDecimal` from a string or from `BigDecimal.valueOf(double)` when the data is already a `double`, and confirm data source and precision requirements.

**Mistake 4 — Forgetting `BigDecimal` is immutable.** The `setScale` method returns **a result object**, without modifying the original object:

~~~java
BigDecimal original = new BigDecimal("1.231");
original.setScale(2, RoundingMode.UP); // Discards the returned result.
System.out.println(original);          // 1.231

BigDecimal rounded = original.setScale(2, RoundingMode.UP);
System.out.println(rounded);           // 1.24
~~~

**Mistake 5 — Confusing decimal places with significant digits.** `setScale(2, ...)` and `round(new MathContext(2, ...))` can give very different results. Choose the right API for the requirement.

**Mistake 6 — Not accounting for a zero result.** DOWN can turn `-0.001` into `0.00` when keeping two decimal places; if you need to know the sign of the input data, record that information **before rounding**.

**Mistake 7 — Rounding too early or inconsistently across steps.** Applying UP to parts and then summing can diverge from summing exact values and applying UP to the total. Document clearly which calculation boundaries are permitted to round.

## 9. Self-Check

Try calculating by hand before running Java; every row rounds to scale 2:

| Input | UP | DOWN |
| --- | ---: | ---: |
| 12.000 | 12.00 | 12.00 |
| 12.001 | 12.01 | 12.00 |
| -12.001 | -12.01 | -12.00 |
| 0.0001 | 0.01 | 0.00 |
| -9.999 | -10.00 | -9.99 |

If still unsure with negative numbers, compare **the distance from each candidate to 0**: UP picks the result farther from 0, DOWN picks the result closer to 0. If no non-zero digits are discarded, both modes give the same numeric value.

**Takeaway:** In Java, `RoundingMode.UP` = **away from 0** and `RoundingMode.DOWN` = **toward 0**. The decision is independent of sign, though the result's position on the number line depends on sign. Always pair the mode with an appropriate scale or precision and a clearly defined rounding point.
