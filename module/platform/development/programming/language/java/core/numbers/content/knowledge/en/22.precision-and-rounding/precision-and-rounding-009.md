# Comparing Rounding Modes with Positive and Negative Numbers in Java

## 1. Goal and Scenario

When rounding numbers in Java, choosing a rounding mode (`RoundingMode`) must be based on **the rounding direction and the rule for handling values halfway between two levels**, especially when inputs can be negative. Names like `UP`, `DOWN`, `CEILING`, and `FLOOR` are easily misunderstood if tested only with positive numbers.

After this lesson, you will be able to:

- Explain accurately all eight values of `java.math.RoundingMode`.
- Predict rounding results for **positive and negative** numbers, both at midpoints (ties) and non-midpoints.
- Distinguish `UP/DOWN` from `CEILING/FLOOR`, and the three rules `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`.
- Use `BigDecimal.setScale(...)`, `divide(...)`, and `MathContext` for their intended purposes; detect when rounding would lose information.
- Choose a consistent rounding policy for currency, measurements, reports, and calculations per business requirements.

Important condition: **rounding only occurs when significant parts must be discarded**. If the result is already representable exactly at the requested scale/precision, every mode yields the same value; `UNNECESSARY` also succeeds.

## 2. Two Perspectives on Rounding Direction

Consider rounding to an integer (`scale = 0`):

- **Moving away from 0** (`UP`): `2.1 → 3` and `-2.1 → -3`. Absolute magnitude increases if there is a fractional part.
- **Moving toward 0** (`DOWN`): `2.9 → 2` and `-2.9 → -2`. This is *truncation* at the rounding position.
- **Moving toward +∞** (`CEILING`): `2.1 → 3` but `-2.1 → -2`. A less negative number is a **larger** number.
- **Moving toward −∞** (`FLOOR`): `2.9 → 2` but `-2.1 → -3`. A more negative number is a **smaller** number.

Therefore, `UP` is **not synonymous** with `CEILING`; `DOWN` is **not synonymous** with `FLOOR`. They match on certain inputs, but diverge when the sign flips.

For modes starting with `HALF_`, Java prioritizes the **nearest result to the original number**. If one of the two candidates is closer, `HALF_UP`, `HALF_DOWN`, and `HALF_EVEN` all choose that candidate. Differences appear only at **the exact midpoint**, such as `2.5` lying between `2` and `3` when rounding to an integer.

Remember the rounding position units:

- `setScale(0, mode)`: rounds to **units**.
- `setScale(2, mode)`: rounds to **2 digits after the decimal point**, step size is `0.01`.
- `setScale(-1, mode)`: rounds to **tens**, step size is `10`. Negative scale is valid.
- `new MathContext(4, mode)`: limits to **4 significant digits**, not 4 digits after the decimal point.

## 3. Comparison Table of All Eight Modes with Positive and Negative Numbers

The table below evaluates `new BigDecimal(input).setScale(0, mode)`. The inputs `±2.5` are **midpoints**; `±2.4` are **not** midpoints.

| `RoundingMode` | `+2.5` | `-2.5` | `+2.4` | `-2.4` | Rule |
| --- | ---: | ---: | ---: | ---: | --- |
| `UP` | `3` | `-3` | `3` | `-3` | Away from 0, whenever any digit must be dropped |
| `DOWN` | `2` | `-2` | `2` | `-2` | Toward 0, drop fractional part |
| `CEILING` | `3` | `-2` | `3` | `-2` | Toward +∞ |
| `FLOOR` | `2` | `-3` | `2` | `-3` | Toward −∞ |
| `HALF_UP` | `3` | `-3` | `2` | `-2` | Nearest; midpoint goes away from 0 |
| `HALF_DOWN` | `2` | `-2` | `2` | `-2` | Nearest; midpoint goes toward 0 |
| `HALF_EVEN` | `2` | `-2` | `2` | `-2` | Nearest; midpoint keeps retained digit even |
| `UNNECESSARY` | error | error | error | error | Forbids lossy rounding |

In the table, "error" means `ArithmeticException` because dropping a non-zero fractional part is requested while `UNNECESSARY` forbids it.

Quick guide to reading two easily confused rows:

- `CEILING(-2.4) = -2` because `-2` is greater than `-2.4`; `FLOOR(-2.4) = -3` because `-3` is less than `-2.4`.
- `UP(-2.4) = -3` because `-3` is farther from 0; `DOWN(-2.4) = -2` because `-2` is closer to 0.

The `HALF_` modes produce the same result for `±2.4` because these values are closer to `±2` than `±3`.

### Additional Table to Distinguish the Three `HALF_` Modes

With `setScale(0, mode)`:

| Input | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` |
| --- | ---: | ---: | ---: |
| `2.5` | `3` | `2` | `2` |
| `-2.5` | `-3` | `-2` | `-2` |
| `3.5` | `4` | `3` | `4` |
| `-3.5` | `-4` | `-3` | `-4` |
| `4.5` | `5` | `4` | `4` |
| `-4.5` | `-5` | `-4` | `-4` |

`HALF_EVEN` chooses **the candidate whose last retained digit is even** at midpoints: `2.5 → 2` yet `3.5 → 4`; `-2.5 → -2` yet `-3.5 → -4`. "Even" checks **the digit at the rounding position**, not the sign of the original number. This is also called *banker's rounding* and can reduce bias from repeated midpoints in some datasets; that does not mean it is always suitable for every business case.

## 4. How Does Each Mode Work?

### `UP` — Away from 0

When the result cannot be represented exactly at the requested position, `UP` increases the **absolute magnitude**:

- `3.01 → 4`, `-3.01 → -4` when `scale = 0`.
- `3.00 → 3`, `-3.00 → -3` because the discarded part consists only of zeros.

Use when required to round quantities or units so magnitude is always sufficient, though you must verify whether the actual policy applies appropriately to negative numbers.

### `DOWN` — Toward 0

`DOWN` discards digits exceeding the requested precision:

- `3.99 → 3`, `-3.99 → -3` when `scale = 0`.
- Does not always mean "round down" on the number line: for negative numbers, `-3` is **greater** than `-3.99`.

### `CEILING` — Toward Positive Infinity

- `3.01 → 4`, `-3.01 → -3`.
- `CEILING` does not mean "increase the digits" of every number; it means **pick the candidate greater than or equal to the input**.

### `FLOOR` — Toward Negative Infinity

- `3.99 → 3`, `-3.01 → -4`.
- `FLOOR` does not mean "decrease the absolute magnitude"; for negative numbers, the result can be farther from 0.

### `HALF_UP` — Nearest, Tie Away from 0

- `2.49 → 2`, `2.50 → 3`; `-2.49 → -2`, `-2.50 → -3`.
- This is the rule commonly meant when a spec says "5 rounds up", yet you **must verify** the rule for negative numbers: `HALF_UP` rounds `-2.5` to `-3`.

### `HALF_DOWN` — Nearest, Tie Toward 0

- `2.49 → 2`, `2.50 → 2`, `2.51 → 3`.
- `-2.49 → -2`, `-2.50 → -2`, `-2.51 → -3`.

`HALF_DOWN` does not mean always toward 0: when distance moves away from the midpoint, it still chooses the closer result.

### `HALF_EVEN` — Nearest, Tie to Even Digit

- `2.5 → 2`, `3.5 → 4`, `-2.5 → -2`, `-3.5 → -4`.
- With two digits after the decimal point: `1.245 → 1.24` because the hundredths digit **4** is even; `1.255 → 1.26` because the candidate has hundredths digit **6**, which is even.

Only an exact **half unit** at the rounding position is a tie. For instance, `1.2451` rounded to scale 2 will be `1.25` in all three `HALF_` modes because it is **greater** than the midpoint `1.245`, since there is a non-zero digit after `5`.

### `UNNECESSARY` — Must Lose No Information

- `new BigDecimal("2.00").setScale(0, UNNECESSARY)` becomes `2`: drops trailing zeros, **no** value lost.
- `new BigDecimal("2.01").setScale(0, UNNECESSARY)` throws `ArithmeticException`.
- Used to enforce an invariant: if the value cannot be represented exactly in the requested format, treat it as an input error instead of silently rounding.

## 5. Standalone Runnable Java 17+ Program

Create the file `SignedRoundingModesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class SignedRoundingModesDemo {
    private static String round(String raw, int scale, RoundingMode mode) {
        try {
            return new BigDecimal(raw)
                    .setScale(scale, mode)
                    .toPlainString();
        } catch (ArithmeticException ex) {
            // "ERROR" represents the case where UNNECESSARY forbids rounding.
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        String[] values = {"2.5", "-2.5", "2.4", "-2.4"};
        System.out.println("mode ` +2.5 ` -2.5 ` +2.4 ` -2.4");

        for (RoundingMode mode : RoundingMode.values()) {
            System.out.printf("%s ` %s ` %s ` %s ` %s%n",
                    mode,
                    round(values[0], 0, mode),
                    round(values[1], 0, mode),
                    round(values[2], 0, mode),
                    round(values[3], 0, mode));
        }

        System.out.println("HALF_EVEN (+3.5,-3.5): "
                + round("3.5", 0, RoundingMode.HALF_EVEN)
                + "; " + round("-3.5", 0, RoundingMode.HALF_EVEN));

        System.out.println("HALF_UP (+1.235,-1.235): "
                + round("1.235", 2, RoundingMode.HALF_UP)
                + "; " + round("-1.235", 2, RoundingMode.HALF_UP));

        System.out.println("HALF_EVEN (1.245,1.255): "
                + round("1.245", 2, RoundingMode.HALF_EVEN)
                + "; " + round("1.255", 2, RoundingMode.HALF_EVEN));

        System.out.println("CEILING/FLOOR (-1.231): "
                + round("-1.231", 2, RoundingMode.CEILING)
                + "; " + round("-1.231", 2, RoundingMode.FLOOR));

        System.out.println("HALF_EVEN tens (145,155): "
                + round("145", -1, RoundingMode.HALF_EVEN)
                + "; " + round("155", -1, RoundingMode.HALF_EVEN));

        System.out.println("UNNECESSARY exact: "
                + round("2.00", 0, RoundingMode.UNNECESSARY));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac SignedRoundingModesDemo.java
java SignedRoundingModesDemo
~~~

Stdout:

~~~text
mode ` +2.5 ` -2.5 ` +2.4 ` -2.4
UP ` 3 ` -3 ` 3 ` -3
DOWN ` 2 ` -2 ` 2 ` -2
CEILING ` 3 ` -2 ` 3 ` -2
FLOOR ` 2 ` -3 ` 2 ` -3
HALF_UP ` 3 ` -3 ` 2 ` -2
HALF_DOWN ` 2 ` -2 ` 2 ` -2
HALF_EVEN ` 2 ` -2 ` 2 ` -2
UNNECESSARY ` ERROR ` ERROR ` ERROR ` ERROR
HALF_EVEN (+3.5,-3.5): 4; -4
HALF_UP (+1.235,-1.235): 1.24; -1.24
HALF_EVEN (1.245,1.255): 1.24; 1.26
CEILING/FLOOR (-1.231): -1.23; -1.24
HALF_EVEN tens (145,155): 140; 160
UNNECESSARY exact: 2
~~~

The program uses **exact decimal strings** and `BigDecimal.setScale`, avoiding noise from `double`'s binary representation. It intentionally catches `ArithmeticException` to illustrate `UNNECESSARY`; in business code, this error should normally be handled according to validation policy rather than just logging a generic "ERROR".

Calculations verified with Java: `HALF_EVEN` with `3.5/-3.5` gives `4/-4`, with `1.245/1.255` at scale 2 gives `1.24/1.26`, with `145/155` at scale -1 gives `140/160`. Negative `-1.231` is rounded at scale 2 to `-1.23` under `CEILING` and `-1.24` under `FLOOR`.

## 6. Under `setScale`: Scale, Precision, Ties, and Signs

### Scale Is Not Identical to Precision

With `BigDecimal`, **scale** controls the number of digits after the decimal point under `unscaledValue × 10^(-scale)`. **Precision** is the total significant digits of the representation.

Example:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal x = new BigDecimal("1234.567");

System.out.println(
        x.setScale(4, RoundingMode.HALF_UP).toPlainString()
); // 1234.5670: four digits AFTER the decimal point

System.out.println(
        x.round(new MathContext(4, RoundingMode.HALF_UP)).toPlainString()
); // 1235: four SIGNIFICANT digits
~~~

This is an **illustrative snippet of Java expressions**, runnable in `jshell` or placed inside a `main` method; it is not a standalone Java file as shown here.

When `MathContext` specifies `precision = 0`, it means unlimited precision, so normal operations are not forced to round due to a precision cap. `MathContext.UNLIMITED` also specifies `RoundingMode.HALF_UP`, yet because precision is unlimited, that rule is not normally used to truncate digits.

### Ties Are Computed at the Retained Position, Not by Digit 5 Alone

Rounding with `scale = 2` has step `0.01`, so:

| Input | Two adjacent candidates | `HALF_EVEN` result |
| --- | --- | --- |
| `1.245` | `1.24` and `1.25` | `1.24` (4 is even) |
| `1.255` | `1.25` and `1.26` | `1.26` (6 is even) |
| `-1.245` | `-1.24` and `-1.25` | `-1.24` (4 is even) |
| `-1.255` | `-1.25` and `-1.26` | `-1.26` (6 is even) |
| `1.2451` | `1.24` and `1.25` | `1.25` (closer) |

Do not mechanically apply `HALF_EVEN` as "whenever you see digit 5, round to even" when there are still non-zero digits after 5. Only when the discarded part is **exactly half** a rounding unit is even/odd checked.

### Negative Scale Can Also Be Used for Rounding

To round to tens, you can call `setScale(-1, mode)`:

~~~java
BigDecimal first = new BigDecimal("145");
BigDecimal second = new BigDecimal("155");

System.out.println(
        first.setScale(-1, RoundingMode.HALF_EVEN).toPlainString()
); // 140
System.out.println(
        second.setScale(-1, RoundingMode.HALF_EVEN).toPlainString()
); // 160
~~~

Both lie exactly halfway between two consecutive multiples of 10. For `145`, the tens digit `4` is even, so `140` is chosen; for `155`, the tens digit `6` is even, so `160` is chosen. `toPlainString()` is used to print `140` or `160` instead of the exponential form that `toString()` can produce with negative scale.

## 7. When an Operation Itself Needs a Rounding Mode

### Division May Not Have a Finite Decimal Expansion

Not every division can be represented as a finite `BigDecimal`. For example, `1 / 3` has an infinite expansion. Calling `divide(BigDecimal)` without precision/rounding mode can throw `ArithmeticException` when the decimal result does not terminate.

Declare the result's precision explicitly:

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal eight = new BigDecimal("8");

System.out.println(
        one.divide(eight, 2, RoundingMode.HALF_UP)
); // 0.13

System.out.println(
        one.negate().divide(eight, 2, RoundingMode.HALF_UP)
); // -0.13
~~~

Both examples round `±0.125` to scale 2, halfway between `±0.12` and `±0.13`. `HALF_UP` chooses `±0.13` because it is farther from 0 at a tie.

Note: `divide(BigDecimal divisor, int scale, RoundingMode mode)` rounds **by scale**. Another overload is `divide(BigDecimal divisor, MathContext mc)`, which rounds **by precision** declared in `MathContext`. With `divide` and `UNNECESSARY`, the division must be exact within the allowed precision/scale, or an exception is thrown.

### Accumulating Operations: Where to Round?

Executing a calculation chain with rounding **after each step** can differ from rounding **once at the final step**. A concrete example:

- Round each `0.125` to 2 digits with `HALF_UP` to get `0.13`; three rounded values summed together give `0.39`.
- Sum the three original values first: `0.125 + 0.125 + 0.125 = 0.375`; then round once to 2 digits with `HALF_UP` to get `0.38`.

Neither way is universally right for every business domain. If the requirement is to round **each invoice line**, the result can differ from summing unrounded values and rounding at checkout. The rule must be specified along with operation order; it must not be changed arbitrarily while optimizing code.

## 8. Negative Numbers and the Java Ecosystem: Dangerous Confusions

### `Math.round` Is Not `BigDecimal` + `HALF_UP`

`Math.round(double)` is a different API from the rule in `RoundingMode.HALF_UP`. With exact representable values such as `±2.5`:

~~~java
System.out.println(Math.round(2.5));  // 3
System.out.println(Math.round(-2.5)); // -2

System.out.println(
        new BigDecimal("-2.5").setScale(0, RoundingMode.HALF_UP)
); // -3
~~~

`Math.round(-2.5)` chooses `-2`, whereas `HALF_UP` chooses `-3`. When migrating code from `Math.round` to `BigDecimal`, compare behavior on negative numbers and ties, not only positive numbers.

### Do Not Create `BigDecimal` from a `double` Literal If Exact Decimals Are Desired

~~~java
BigDecimal exact = new BigDecimal("2.675");
BigDecimal fromDouble = new BigDecimal(2.675);

System.out.println(exact.setScale(2, RoundingMode.HALF_EVEN)); // 2.68
~~~

`2.675` has no finite binary representation in `double`, so `fromDouble` holds the approximated binary value converted to decimal; when rounding at a tie position, the result may differ from the decimal number you thought you entered. Use the `String` constructor or follow your input contract; when already receiving a `double` and wanting a decimal representation based on `Double.toString`, consider `BigDecimal.valueOf(double)`.

### Negative Signs and Zero

`BigDecimal` does not keep a separate "negative zero" value in terms of arithmetic comparison. Thus, rounding a very small negative number **toward 0** can display `0`, not `-0`:

~~~java
System.out.println(
        new BigDecimal("-0.1").setScale(0, RoundingMode.CEILING)
); // 0

System.out.println(
        new BigDecimal("-0.1").setScale(0, RoundingMode.FLOOR)
); // -1
~~~

Do not infer the original sign from a result that has been rounded to 0. If business logic needs to distinguish the direction of change, store that information separately.

## 9. Choosing a Mode by Business Requirement

| Specific requirement | Suitable implementation | Further confirmation needed |
| --- | --- | --- |
| Symmetric nearest rounding, midpoint away from 0 | `HALF_UP` | Policy for negative values and rounding position |
| Nearest rounding, midpoint toward 0 | `HALF_DOWN` | Is this rule actually required by the contract |
| Nearest rounding, midpoint to even digit | `HALF_EVEN` | Is it allowed when computing totals/line items |
| Always pick higher level on the number line | `CEILING` | Must apply accurately to negative numbers too |
| Always pick lower level on the number line | `FLOOR` | Must apply accurately to negative numbers too |
| Always increase absolute magnitude when digits are dropped | `UP` | Intended to apply symmetrically for negative numbers |
| Discard excess beyond rounding position toward 0 | `DOWN` | Is dropping information acceptable |
| Data required to be exact at given scale | `UNNECESSARY` | At which layer errors should be reported or rejected |

For currency and accounting data, **do not arbitrarily impose** `HALF_UP` or `HALF_EVEN` just because it is popular. A country, transaction standard, tax rule, bank, or system may require a specific policy per calculation. At a minimum, the specification should state: rounding position, mode, rounding timing, summation method, and handling of negative values/refunds.

For statistics or simulation, `HALF_EVEN` can reduce directional bias on tie cases when data conditions fit, yet it **does not fix** errors from sampling, input precision, or operation order.

For inputs required to have exactly two decimal places, for example instead of silently rounding `12.345`, you can validate:

~~~java
BigDecimal submitted = new BigDecimal("12.345");
BigDecimal checked = submitted.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: rounding would be required, so value is invalid under this rule.
~~~

## 10. Common Mistakes and Self-Check Checklist

1. **Confusing `UP` with "toward +∞".** `-2.4` under `UP` gives `-3`, under `CEILING` gives `-2`.
2. **Confusing `DOWN` with "toward −∞".** `-2.4` under `DOWN` gives `-2`, under `FLOOR` gives `-3`.
3. **Thinking every `HALF_` differs on all data.** For `±2.4`, all three give `±2`; they differ only on ties.
4. **Interpreting `HALF_EVEN` as "if the original number is even, keep it".** It inspects the retained digit at **the position being rounded**: `3.5 → 4` is valid.
5. **Assuming `UNNECESSARY` always throws when changing scale.** Changing `2.00` to `2` is exact, so it does not throw.
6. **Confusing scale and precision.** `setScale(2, mode)` and `MathContext(2, mode)` specify two different things.
7. **Forgetting negative numbers in tests.** A minimal test suite for each mode should include `+2.5`, `-2.5`, `+2.4`, `-2.4`, and `±3.5`, plus cases requiring no rounding.
8. **Using `double` so ties are no longer exact.** Construct `BigDecimal` from decimal strings if that is the source data.

### Self-Check Exercises

Without running the program right away, predict the results first:

1. `new BigDecimal("-7.1").setScale(0, FLOOR)` vs `...CEILING`?
2. `new BigDecimal("-7.5").setScale(0, HALF_UP)` vs `...HALF_DOWN`?
3. `new BigDecimal("6.5").setScale(0, HALF_EVEN)` and `new BigDecimal("7.5").setScale(0, HALF_EVEN)`?
4. `new BigDecimal("-2.345").setScale(2, HALF_EVEN)`?
5. Does `new BigDecimal("12.000").setScale(0, UNNECESSARY)` throw an error?
6. `new BigDecimal("145").setScale(-1, HALF_UP).toPlainString()` and `new BigDecimal("-145").setScale(-1, HALF_UP).toPlainString()`?

**Answers and reasons:**

1. `FLOOR = -8` (toward −∞); `CEILING = -7` (toward +∞).
2. `HALF_UP = -8` (tie away from 0); `HALF_DOWN = -7` (tie toward 0).
3. `6.5 → 6` and `7.5 → 8` under `HALF_EVEN` because the chosen candidate has an even units digit.
4. `-2.345 → -2.34`: both candidates are equidistant; hundredths digit `4` is even.
5. **No error**, result `12`, because dropping zeros in the fractional part does not change value.
6. `145 → 150` and `-145 → -150` under `HALF_UP` when rounding to tens, because both are ties and must choose the side away from 0.

**Takeaway:** With negative values, "up/down" must be defined by **the number line** or **distance to 0**. Only when candidate results are equally close do the three `HALF_` modes differ. Decide on scale or precision together with the mode policy, test negative signs, and handle zero-precision-loss requirements separately.
