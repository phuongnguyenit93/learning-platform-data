# HALF_UP and HALF_DOWN When a Value Lies Exactly Halfway

## The Problem to Understand

In Java, both `RoundingMode.HALF_UP` and `RoundingMode.HALF_DOWN` round toward **the nearest value**. They differ only when the original value is **equidistant from the two target levels**, called *exact halfway* (a *tie* or *halfway case*).

For example, keeping two digits after the decimal point: `2.34` and `2.35` are `0.01` apart, while `2.345` is `0.005` away from each. Then:

- `HALF_UP` chooses `2.35` (farther from 0).
- `HALF_DOWN` chooses `2.34` (closer to 0).
- `2.344` is not halfway: both choose `2.34`.
- `2.346` is not halfway: both choose `2.35`.

With the target of keeping `s` decimal places, two adjacent levels are `10^-s` apart and the midpoint is `(10^-s)/2` from each level. At `scale = 2`, the exact half-step is `0.005`.

```text
2.34           2.345           2.35
 |---------------|---------------|
       0.005           0.005
           exact halfway
```

**All discarded digits must be examined.** `2.345000` is still exact halfway because only trailing zeros are added; `2.345001` is no longer exact halfway because it is closer to `2.35`. "The first discarded digit is 5" alone is not enough to conclude there is a tie.

## Rules for Positive and Negative Numbers

| Original number, keep 2 digits | HALF_UP | HALF_DOWN | Explanation |
|---|---|---|---|
| `2.344` | `2.34` | `2.34` | Closer to lower level |
| `2.345` | `2.35` | `2.34` | Positive tie |
| `2.346` | `2.35` | `2.35` | Closer to higher level |
| `-2.344` | `-2.34` | `-2.34` | Closer to `-2.34` |
| `-2.345` | `-2.35` | `-2.34` | Negative tie |
| `-2.346` | `-2.35` | `-2.35` | Closer to `-2.35` |
| `0.005` | `0.01` | `0.00` | Tie near 0 |
| `-0.005` | `-0.01` | `0.00` | Negative tie near 0 |
| `2.34501` | `2.35` | `2.35` | Above midpoint |

Most important point: **"UP" does not mean the numeric result increases**. With `-2.345`, `HALF_UP` gives `-2.35`, which is smaller on the number line but **farther from 0**; `HALF_DOWN` gives `-2.34`, which is **closer to 0**. With `-0.005` and `HALF_DOWN`, `BigDecimal` returns `0.00` (zero with scale 2), without needing a "-0.00" result.

When a value is **not** exact halfway, both modes choose the nearest number regardless of sign; for example `-2.346` becomes `-2.35` in both modes.

## Java 17+ — Standalone Runnable Program

Create the file `HalfTieDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class HalfTieDemo {
    private static void show(String raw) {
        BigDecimal value = new BigDecimal(raw);
        BigDecimal up = value.setScale(2, RoundingMode.HALF_UP);
        BigDecimal down = value.setScale(2, RoundingMode.HALF_DOWN);

        System.out.println(raw + " | " + up.toPlainString()
                + " | " + down.toPlainString());
    }

    public static void main(String[] args) {
        System.out.println("value | HALF_UP | HALF_DOWN");
        for (String raw : new String[] {
                "2.344", "2.345", "2.346",
                "-2.344", "-2.345", "-2.346",
                "0.005", "-0.005", "2.34501"
        }) {
            show(raw);
        }

        BigDecimal one = BigDecimal.ONE;
        BigDecimal eight = new BigDecimal("8");
        System.out.println("1 / 8 | "
                + one.divide(eight, 2, RoundingMode.HALF_UP)
                + " | "
                + one.divide(eight, 2, RoundingMode.HALF_DOWN));

        BigDecimal p = new BigDecimal("12.35");
        System.out.println("precision 3 | "
                + p.round(new MathContext(3, RoundingMode.HALF_UP))
                        .toPlainString()
                + " | "
                + p.round(new MathContext(3, RoundingMode.HALF_DOWN))
                        .toPlainString());
    }
}
```

Use JDK 17 or newer:

```bash
javac HalfTieDemo.java
java HalfTieDemo
```

Exact output:

```text
value | HALF_UP | HALF_DOWN
2.344 | 2.34 | 2.34
2.345 | 2.35 | 2.34
2.346 | 2.35 | 2.35
-2.344 | -2.34 | -2.34
-2.345 | -2.35 | -2.34
-2.346 | -2.35 | -2.35
0.005 | 0.01 | 0.00
-0.005 | -0.01 | 0.00
2.34501 | 2.35 | 2.35
1 / 8 | 0.13 | 0.12
precision 3 | 12.4 | 12.3
```

Code explanation:

1. `new BigDecimal(raw)` accepts an **exact decimal representation** from a string, keeping tie cases as described.
2. `setScale(2, mode)` requires exactly 2 digits after the decimal point and applies the mode if digits must be discarded.
3. `1 / 8 = 0.125` lies between `0.12` and `0.13`; `divide(eight, 2, mode)` returns `0.13` under `HALF_UP`, `0.12` under `HALF_DOWN`.
4. `new MathContext(3, mode)` requires **3 significant digits**, so `12.35` becomes `12.4` or `12.3`.
5. `BigDecimal` is an **immutable** type. `setScale`, `divide`, and `round` return new results; they do not modify the old object. To keep it, reassign, such as `value = value.setScale(2, mode)`.

## Scale, Precision, and Step Size of One Rounding Unit

**Scale** is the number of digits to the right of the decimal point. `setScale(2, mode)` rounds to hundredths; `setScale(0, mode)` rounds to units; `setScale(-1, mode)` rounds to tens.

**Precision** in `MathContext` is **the total number of significant digits**, not only the fractional part. For example, `12.35` has 4 significant digits; rounding to precision 3 creates a tie between `12.3` and `12.4`.

| Target | Input | HALF_UP | HALF_DOWN |
|---|---|---|---|
| `setScale(2)` | `7.125` | `7.13` | `7.12` |
| `setScale(0)` | `-2.5` | `-3` | `-2` |
| `setScale(-1)` | `145` | `150` | `140` |
| `MathContext(3)` | `12.35` | `12.4` | `12.3` |

Rounding at a negative scale can produce a scientific notation representation in `BigDecimal`; `toPlainString()` displays it in ordinary form. If `setScale` needs to discard digits without a `RoundingMode` provided, the call can throw `ArithmeticException`. `RoundingMode.UNNECESSARY` also throws an error when rounding is required, useful if the data contract requires an exact result at the target scale.

## Common Misunderstandings and Misapplications

### 1. Seeing Digit 5 and Assuming It Is Exact Halfway

At scale 2, `2.34499` is below the half-step so both go to `2.34`; `2.34500` is a tie so it gives different results; `2.34501` is above the half-step so both go to `2.35`. When testing, include values just below, exactly at, and just above the midpoint.

### 2. Confusing HALF_UP with UP, CEILING, or Math.round

`RoundingMode.UP` always moves away from 0 when discarding digits; `DOWN` always moves toward 0. `CEILING` goes toward positive and `FLOOR` toward negative. They differ from `HALF_UP`/`HALF_DOWN` because the two HALF modes prioritize **the nearest level**.

`Math.round(-2.5)` returns `-2`: at a tie, `Math.round` picks toward the positive direction on the number line, unlike `BigDecimal("-2.5").setScale(0, RoundingMode.HALF_UP)` which gives `-3`. Therefore, do not substitute `RoundingMode` with `Math.round` based on name intuition.

### 3. Using double Destroys Tie Exactness

`new BigDecimal(2.675)` receives the approximate binary value currently stored by `double`, which may not equal `2.675` exactly. The decimal midpoint can shift, causing unexpected results. To express an exact decimal value, use `new BigDecimal("2.675")`; at scale 2 with `HALF_UP`, the result is `2.68`.

`BigDecimal.valueOf(2.675)` converts via `double`'s string representation and is usually closer to what humans expect than the `double` constructor, but **cannot recover precision already lost** in earlier `double` operations.

### 4. Rounding Arbitrarily at Intermediate Steps

Two items of `1.245`: rounding each item at scale 2 with `HALF_UP` and then adding gives `1.25 + 1.25 = 2.50`. Adding first and rounding once gives `1.245 + 1.245 = 2.490`, yielding `2.49`. Same mode yet different results because **when rounding happens** differs. Business rules must specify timing, scale, and mode.

### 5. Choosing a Mode Because It "Sounds Reasonable"

There is no universal rule that all monetary amounts must use `HALF_UP` or `HALF_DOWN`. Follow the requirements of the system, standard, or contract. Meanwhile `HALF_EVEN`, another common policy, selects the last retained digit that is **even** at a tie: at scale 2, `2.345` becomes `2.34` whereas `2.355` becomes `2.36`. `HALF_EVEN` is not synonymous with `HALF_DOWN`.

## Applying and Self-Checking

Before implementing, be able to answer: does the input preserve exact decimal values; is the goal scale or precision; on a tie should it go away from or toward 0; at which step should rounding occur; have negative numbers and numbers right on both sides of the tie been tested? Use an explicit `RoundingMode` in `setScale`, `divide`, or `round(MathContext)`.

**Self-check exercise:** Round `-7.1250` to 2 digits. This is a tie between `-7.12` and `-7.13`, so `HALF_UP` gives **`-7.13`**, and `HALF_DOWN` gives **`-7.12`**. If changed to `-7.1251`, both give `-7.13` since it is closer to `-7.13`.

**Takeaway:** Both modes round to the nearest level; **only at the exact halfway point**, `HALF_UP` chooses away from 0 and `HALF_DOWN` chooses toward 0.
