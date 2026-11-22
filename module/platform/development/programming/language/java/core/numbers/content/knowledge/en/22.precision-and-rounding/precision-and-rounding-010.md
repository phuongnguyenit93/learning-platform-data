# Double Rounding and How It Differs from Rounding at the Final Step

## 1. The Problem: Same Data, Two Ways of Rounding Can Give Two Results

In decimal arithmetic, **double rounding** (*double rounding*) is the situation where a value is rounded at an intermediate level and then rounded again to the final level. The result **can differ** from keeping the necessary digits intact and rounding only once at the final step.

Consider the exact decimal number `1.245`, with the same rule `RoundingMode.HALF_UP`:

| Process | Intermediate value | Final value |
| --- | --- | --- |
| Round twice: 3 → 2 → 1 digit after decimal point | `1.245 → 1.25` | `1.3` |
| Round directly: 3 → 1 digit after decimal point | None | `1.2` |

The first rounding changed `1.245` into `1.25`, causing the second rounding to see **an exact halfway case** (`1.25` lies between `1.2` and `1.3`). Meanwhile, `1.245` is actually closer to `1.2` than `1.3`. This discrepancy comes from information lost at the intermediate step, **not a bug in `BigDecimal`**.

```java
BigDecimal value = new BigDecimal("1.245");
BigDecimal twice = value
        .setScale(2, RoundingMode.HALF_UP)
        .setScale(1, RoundingMode.HALF_UP);
BigDecimal once = value.setScale(1, RoundingMode.HALF_UP);

System.out.println(twice); // 1.3
System.out.println(once);  // 1.2
```

Standalone snippets in this lesson assume `java.math.BigDecimal` and `java.math.RoundingMode` are imported. The complete program below can be compiled and run standalone on Java 17+.

## 2. Mathematical Mechanism: Where Does the Discrepancy Arise?

Let `R_s(x)` denote the result of rounding `x` to **scale `s`**, with a given `RoundingMode`. The two processes to compare are:

```text
Intermediate rounding: R_1(R_2(x))
Single rounding:       R_1(x)
```

For `x = 1.245`, `HALF_UP`:

1. `R_2(1.245) = 1.25` because the dropped digit 5 is halfway between two levels at the hundredths place and `HALF_UP` rounds up for positive numbers.
2. `R_1(1.25) = 1.3` because `1.25` is the midpoint between `1.2` and `1.3`.
3. `R_1(1.245) = 1.2` because the original value is **less than** the midpoint `1.25`; it is not close enough to `1.3` to round up.

Thus:

```text
R_1(R_2(1.245)) = 1.3
R_1(1.245)      = 1.2
```

The discrepancy equals `0.1` — one unit at the target precision, even though intermediate rounding changed `1.245` by only `0.005`.

What to remember is that **a value originally sitting close to a rounding threshold at the final precision** can be pushed onto or past that threshold by an earlier rounding step. Not every value hits this situation, but you cannot guarantee the two processes are always equivalent just because they use the same `RoundingMode`.

### Why Does "Exact Halfway" Matter?

With `HALF_UP` and a one-decimal-place result, the threshold between `1.2` and `1.3` is `1.25`. The number `1.245` lies **below** this threshold. Rounding to two digits first pushed it to exactly `1.25`, altering the decision at the final step.

In computational algorithms, a rounding rule applied twice does not necessarily satisfy the property:

```text
R_final(R_intermediate(x)) == R_final(x)
```

Especially with nearest-rounding modes such as `HALF_UP`, `HALF_EVEN`, and `HALF_DOWN`.

## 3. Differences Can Also Occur with HALF_EVEN

`HALF_EVEN` chooses the result with an even last digit when the two candidate values are equidistant from the input. This is commonly called *banker's rounding*, yet it is **not immune to double rounding**.

Consider `1.251`:

```java
BigDecimal x = new BigDecimal("1.251");
BigDecimal intermediate = x.setScale(2, RoundingMode.HALF_EVEN);
BigDecimal twice = intermediate.setScale(1, RoundingMode.HALF_EVEN);
BigDecimal once = x.setScale(1, RoundingMode.HALF_EVEN);

System.out.println(intermediate); // 1.25
System.out.println(twice);        // 1.2
System.out.println(once);         // 1.3
```

Explanation:

- `1.251` to two digits after the decimal point is `1.25` because it is closer to `1.25` than `1.26`.
- `1.25` to one digit after the decimal point creates a tie between `1.2` and `1.3`; `HALF_EVEN` picks `1.2` because the tenths digit is 2 (even).
- `1.251` directly to one digit is `1.3` because the original value is greater than the midpoint `1.25`; this case is **not a tie**, so the even-digit rule is not used.

Therefore, choosing `HALF_EVEN` to limit bias across many roundings does not mean intermediate rounding can be applied arbitrarily.

## 4. Not Every Double Rounding Produces a Different Result

For example `1.234` with `HALF_UP`:

```text
1.234 → 1.23 → 1.2
1.234 ─────────→ 1.2
```

Both paths return `1.2`. Whether a discrepancy occurs depends on the discarded digits, threshold location, intermediate scale, final scale, and rounding mode.

When only consecutively **decreasing scale on the same number** using a fixed-direction rounding mode (`DOWN` toward 0, `UP` away from 0, `FLOOR` toward negative infinity, `CEILING` toward positive infinity), the two-step result matches the direct result at the target scale: these directional roundings do not create a new "exact halfway" situation that flips the choice. However, when inserting **other operations** between roundings, or changing rounding mode, do not generalize that conclusion automatically.

Conversely, with nearest modes like `HALF_UP` and `HALF_EVEN`, you must account for double rounding risk even when the intermediate scale is finer than the final scale.

A helpful perspective: if the process turns `1.245` into `1.25`, the lost `0.005` can no longer be inferred from `1.25`. Subsequent rounding only sees the already altered number.

## 5. Distinguishing Double Rounding from Rounding Parts Before Aggregating

Another common source of discrepancy is **the order of rounding relative to addition or multiplication**. Even though it is not necessarily `setScale()` called twice on the same number, it is the same design problem: **at which step of the calculation to place rounding**.

### 5.1. Adding Two Small Amounts

Two exact amounts are `0.006` and `0.006`. If rounding each amount to two digits with `HALF_UP` before adding:

```text
round(0.006, 2) + round(0.006, 2)
= 0.01 + 0.01
= 0.02
```

If adding at the original precision and rounding the total once:

```text
round(0.006 + 0.006, 2)
= round(0.012, 2)
= 0.01
```

The results differ by `0.01`. If the contract requires each item as an accounting unit to be rounded independently, the first process may be the right one. If the rule specifies rounding only the final total, the second process is right. **There is no single formula right for all financial cases.**

### 5.2. Rounding Unit Price Before Multiplying by Quantity

Assume a unit price of `0.335` and a quantity of 3.

```text
Round unit price first:
round(0.335, 2) × 3
= 0.34 × 3
= 1.02

Multiply exactly then round line total:
round(0.335 × 3, 2)
= round(1.005, 2)
= 1.01
```

With `HALF_UP`, the two processes differ by `0.01`. This is not binary error since all values can be stored accurately in `BigDecimal`; the discrepancy comes entirely from **the rounding rule being applied at different points**.

### 5.3. Division and Intermediate Precision

A division such as `1 / 3` has an infinite decimal representation; `BigDecimal.ONE.divide(new BigDecimal("3"))` cannot have an exact finite decimal result and will throw `ArithmeticException`. When forced to round at a division step, set an appropriate intermediate scale/`MathContext` and clearly define the business rounding boundary, for example `divide(divisor, 8, RoundingMode.HALF_EVEN)`. Do not call `divide()` without a rule and expect a later `setScale()` to handle an exception that already occurred.

Although adding extra "guard digits" in the middle usually helps reduce risk, no small fixed number of extra digits automatically guarantees every calculation and every input gives the exact same result as infinite-precision arithmetic. You must understand data precision, the chain of operations, and the rounding standard to prove correctness.

## 6. Precision and MathContext: Another Form of Double Rounding

`BigDecimal.setScale(n, mode)` keeps `n` digits **after the decimal point**. `MathContext(p, mode)` limits `p` **significant digits** (*precision*) in certain operations or when calling `round(MathContext)`. These two parameters differ, yet intermediate rounding risk exists in both.

Example with `9.949`:

```java
BigDecimal x = new BigDecimal("9.949");
MathContext p3 = new MathContext(3, RoundingMode.HALF_UP);
MathContext p2 = new MathContext(2, RoundingMode.HALF_UP);

BigDecimal twice = x.round(p3).round(p2);
BigDecimal once = x.round(p2);

System.out.println(x.round(p3).toPlainString()); // 9.95
System.out.println(twice.toPlainString());       // 10
System.out.println(once.toPlainString());        // 9.9
```

`9.949` is rounded from four down to three significant digits to become `9.95`. Then, from three down to two significant digits it becomes `10`. Yet going straight from `9.949` to two significant digits yields `9.9`.

In multi-step calculations, such as multiplying then adding with a bounded `MathContext`, each operation using the context may immediately round its own result. This affects the final result, even if there is a `setScale()` call later for display. Clearly distinguish:

- **Computation precision**: the accuracy of intermediate arithmetic step results.
- **Storage/exchange scale**: the decimal level per data contract.
- **Display scale**: the number of digits used for UI, invoices, or reports.

These three concepts should not be interchanged.

## 7. Complete, Runnable Java 17+ Example

Save the following program to `DoubleRoundingDemo.java`. Each calculation uses decimal strings to avoid noise from `double` representation.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DoubleRoundingDemo {
    public static void main(String[] args) {
        RoundingMode halfUp = RoundingMode.HALF_UP;

        BigDecimal value = new BigDecimal("1.245");
        BigDecimal intermediate = value.setScale(2, halfUp);
        BigDecimal twice = intermediate.setScale(1, halfUp);
        BigDecimal once = value.setScale(1, halfUp);

        System.out.println("original = " + value);
        System.out.println("intermediate = " + intermediate);
        System.out.println("twice = " + twice);
        System.out.println("once = " + once);

        BigDecimal halfEvenValue = new BigDecimal("1.251");
        BigDecimal halfEvenTwice = halfEvenValue
                .setScale(2, RoundingMode.HALF_EVEN)
                .setScale(1, RoundingMode.HALF_EVEN);
        BigDecimal halfEvenOnce =
                halfEvenValue.setScale(1, RoundingMode.HALF_EVEN);
        System.out.println("HALF_EVEN twice = " + halfEvenTwice);
        System.out.println("HALF_EVEN once = " + halfEvenOnce);

        BigDecimal itemA = new BigDecimal("0.006");
        BigDecimal itemB = new BigDecimal("0.006");
        BigDecimal sumOfRoundedItems =
                itemA.setScale(2, halfUp).add(itemB.setScale(2, halfUp));
        BigDecimal roundedTotal = itemA.add(itemB).setScale(2, halfUp);
        System.out.println("sum rounded items = " + sumOfRoundedItems);
        System.out.println("round sum = " + roundedTotal);

        BigDecimal unitPrice = new BigDecimal("0.335");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal roundedUnitFirst =
                unitPrice.setScale(2, halfUp).multiply(quantity);
        BigDecimal roundedLineTotal =
                unitPrice.multiply(quantity).setScale(2, halfUp);
        System.out.println("round unit first = " + roundedUnitFirst);
        System.out.println("round line total = " + roundedLineTotal);

        BigDecimal precisionInput = new BigDecimal("9.949");
        MathContext p3 = new MathContext(3, halfUp);
        MathContext p2 = new MathContext(2, halfUp);
        System.out.println("precision twice = "
                + precisionInput.round(p3).round(p2).toPlainString());
        System.out.println("precision once = "
                + precisionInput.round(p2).toPlainString());
    }
}
```

Run from the directory containing the file:

```bash
javac DoubleRoundingDemo.java
java DoubleRoundingDemo
```

Expected output:

```text
original = 1.245
intermediate = 1.25
twice = 1.3
once = 1.2
HALF_EVEN twice = 1.2
HALF_EVEN once = 1.3
sum rounded items = 0.02
round sum = 0.01
round unit first = 1.02
round line total = 1.01
precision twice = 10
precision once = 9.9
```

Key observation: the same original number and the same rounding mode can produce different results along different paths. The program keeps the original `BigDecimal` values intact because `BigDecimal` is immutable. `setScale()` and `round(MathContext)` **return results**; the calls do not mutate the source instances.

## 8. Designing Calculation Pipelines to Avoid Unnecessary Precision Loss

**Step 1 — Define the final result and rounding unit.** Explicitly state "each invoice line's amount rounds to 0.01", "total interest rounds after each period", or "format display to two decimal places only". These sentences describe three different pipelines.

**Step 2 — Keep exact decimal data at input.** If the source number is a decimal provided by user/DB, initialize `BigDecimal` from a string or exact decimal data. Avoid `new BigDecimal(0.1)` when intending exact decimal 0.1; this constructor keeps the exact approximated binary value of the `double` literal. Typically use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`.

**Step 3 — Use appropriate computation precision.** `BigDecimal.add()` and `multiply()` without `MathContext` perform exact arithmetic within decimal arithmetic capability (with the scales of the operands). `divide()` may require a rounding policy when the quotient is non-terminating. If using `MathContext` in a calculation chain, understand that intermediate results may already be rounded.

**Step 4 — Round at defined boundaries.** If the contract requires rounding each line item, do so intentionally; if the contract requires rounding once after summing, defer `setScale()` until the end of the sum. Avoid rounding "to make data tidy" in steps that still have operations after them.

**Step 5 — Choose rounding mode by business rules.** `HALF_EVEN`, `HALF_UP`, `FLOOR`, and `CEILING` serve different needs. Pay special attention to negative numbers, refunds, transaction reversals, and exact midpoints.

**Step 6 — Test at boundaries.** Besides normal numbers, test values just below/above midpoints, negative numbers, zero, and very small cases. Test multi-item sums and operator order as well. Small discrepancies per transaction can accumulate when processing high transaction volumes.

A function with a clear boundary can be written as follows:

```java
static BigDecimal totalRoundedAtEnd(
        BigDecimal first,
        BigDecimal second,
        int resultScale,
        RoundingMode mode) {
    return first.add(second).setScale(resultScale, mode);
}
```

This is an **illustrative method snippet** placed inside a Java class; it enforces the round-after-addition policy. If the requirement is that both lines must be rounded independently, this function does not satisfy that policy and must be replaced with the corresponding workflow.

## 9. False Assumptions and How to Verify

| Misconception | Fact to remember |
| --- | --- |
| "With the same `RoundingMode`, rounding any number of times is the same." | False for many nearest-rounding modes; `1.245` with `HALF_UP` is a counterexample. |
| "`HALF_EVEN` completely eliminates double-rounding error." | False; `1.251` with `HALF_EVEN` is a counterexample. |
| "`BigDecimal` always guarantees correct results regardless of where rounding occurs." | It represents decimals accurately and follows the specified rounding policy; a policy placed at the wrong time still gives a different result. |
| "Rounding each item is always wrong." | Right or wrong depends on the required accounting/tax/invoicing rules. |
| "Storing two decimal places is enough for all monetary calculations." | Intermediates may need extra digits; distinguish computation precision from final result scale. |
| "Just compute with `double` then call `setScale()` to clear errors." | Converting an approximated binary value to decimal does not automatically reconstruct the desired original decimal number. |
| "Call `setScale(2)` after every calculation for consistency." | Can lose information and change the values of subsequent calculations. |

Technically, also remember that `BigDecimal.equals()` checks scale too: `new BigDecimal("1.2").equals(new BigDecimal("1.20"))` is `false` even though `compareTo()` returns 0. When comparing calculation results by **numeric value**, use `compareTo() == 0` or normalize under a consistent rule; when testing formatted strings, compare string content as a separate check.

## 10. Self-Check Exercises

**Question 1.** `new BigDecimal("1.245").setScale(2, HALF_UP).setScale(1, HALF_UP)` compared to `new BigDecimal("1.245").setScale(1, HALF_UP)`?

**Answer:** `1.3` and `1.2`. The first step turned `1.245` into the midpoint `1.25` for the second rounding.

**Question 2.** Why does `HALF_EVEN` not completely prevent discrepancies from double rounding?

**Answer:** `1.251` → `1.25` → `1.2`, yet rounding directly to one digit gives `1.3`. The intermediate step created a spurious tie.

**Question 3.** Two amounts `0.006` and `0.006`, `HALF_UP` to 2 decimal places: what is the sum after rounding each amount, and what is the final sum rounded?

**Answer:** `0.02` and `0.01`. Which result to choose depends on the rounding boundary defined by business rules.

**Question 4.** With unit price `0.335`, quantity 3, `HALF_UP` to 2 digits: do rounding unit price before multiplying and rounding line total after multiplying differ?

**Answer:** `0.34 × 3 = 1.02`, while `round(0.335 × 3, 2) = 1.01`.

**Question 5.** Are `setScale(2)` and `round(new MathContext(2, mode))` the same?

**Answer:** No. `setScale(2)` specifies 2 digits after the decimal point (and will error if rounding is required without a mode), whereas `MathContext(2, mode)` uses 2 significant digits.

**Question 6.** To reduce the risk of discrepancies from double rounding in a pipeline, what is the practical principle?

**Answer:** Maintain sufficient intermediate precision; round only at defined boundaries; avoid two consecutive nearest-rounding steps when you can compute and round directly from full values; test values near thresholds. If business rules require rounding per item, follow that requirement strictly.

**Takeaway:** Rounding is a potentially lossy transformation. **`R_final(R_intermediate(x))` does not necessarily equal `R_final(x)`**; likewise, rounding components before adding/multiplying can differ from rounding the final result. Computing with `BigDecimal` avoids `double` decimal representation errors, yet does not replace choosing the right **precision, rule, and rounding timing**.