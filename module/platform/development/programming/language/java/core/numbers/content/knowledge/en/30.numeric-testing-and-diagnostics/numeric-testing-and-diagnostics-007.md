# Comparing All `RoundingMode` Values at Exact Midpoints in Java

## 1. The Problem: Why Do Results Differ for the Same “Halfway” Number?

When a decimal number must reduce its fractional digits or significant digits, **rounding** is a decision that must be made explicitly. One of the easiest situations to get wrong is when the value sits **right between two representable results** at the requested precision.

For example, rounding `2.5` to an integer:

- The nearest candidates are `2` and `3`.
- The distance from `2.5` to `2` equals the distance to `3`, both `0.5`.
- The *rounding mode* determines whether to pick `2`, `3`, or reject the operation.

For `-2.5`, the two neighboring integers are `-3` and `-2`; “rounding up” can cause confusion if you do not distinguish **toward +∞**, **toward −∞**, **toward 0**, and **away from 0**.

In Java 17+, the modes are defined by the enum `java.math.RoundingMode` and commonly used with `BigDecimal.setScale(...)`, `BigDecimal.divide(...)`, or `MathContext`.

**Objective:** compare **all eight** `RoundingMode` values at exact midpoints for both positive and negative numbers; understand the rules for non-midpoint cases; know when `UNNECESSARY` is valid; build a deterministic test suite and avoid errors caused by `double` inputs.

## 2. Defining “Exact Midpoint” Depends on Target Precision

An **exact midpoint** (*exact halfway/tie*) is a number equidistant from two neighboring representable results at the **chosen scale or precision**.

Example with `setScale(0, mode)`, targeting integers:

| Original number | Two neighboring integers | Exact tie? |
| --- | --- | --- |
| `2.5` | `2` and `3` | Yes |
| `-2.5` | `-3` and `-2` | Yes |
| `3.5` | `3` and `4` | Yes |
| `2.5000` | `2` and `3` | Yes, trailing zeros do not change value |
| `2.5001` | `2` and `3` | No, closer to `3` |
| `2.4999` | `2` and `3` | No, closer to `2` |

With `setScale(1, mode)`, steps between valid results have size `0.1`. Here `2.25` is halfway between `2.2` and `2.3`; `2.35` is halfway between `2.3` and `2.4`. Meanwhile `2.5` already has one decimal digit, so **no rounding is needed** at scale 1.

Therefore, you cannot say “a value ending in `.5` is a tie” without specifying the **target scale**. When rounding with `MathContext`, a tie also depends on the requested **number of significant digits**, not simply decimal places.

Use decimal strings to construct test values:

```java
BigDecimal value = new BigDecimal("2.5000");
BigDecimal rounded = value.setScale(0, RoundingMode.HALF_EVEN);
// rounded is 2
```

This preserves the **exact** desired decimal value. Avoid writing `new BigDecimal(2.675)` for an “exact midpoint” decimal test case, because the input `double` may only be a binary value *near* the typed decimal.

## 3. All Eight `RoundingMode` Values: Exact Meaning of Each Mode

`RoundingMode` consists of eight values: `UP`, `DOWN`, `CEILING`, `FLOOR`, `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`, `UNNECESSARY`.

| Mode | Core rule | Positive tie `+2.5` to scale 0 | Negative tie `-2.5` to scale 0 |
| --- | --- | ---: | ---: |
| `UP` | If nonzero part must be discarded, round **away from 0** | `3` | `-3` |
| `DOWN` | If nonzero part must be discarded, round **toward 0** | `2` | `-2` |
| `CEILING` | Round **toward +∞** | `3` | `-2` |
| `FLOOR` | Round **toward −∞** | `2` | `-3` |
| `HALF_UP` | Nearest neighbor; **on tie**, **away from 0** | `3` | `-3` |
| `HALF_DOWN` | Nearest neighbor; **on tie**, **toward 0** | `2` | `-2` |
| `HALF_EVEN` | Nearest neighbor; **on tie**, choose result whose kept last digit is **even** | `2` | `-2` |
| `UNNECESSARY` | **Forbid any case requiring rounding** | Error | Error |

This is a **comparison table at ties**; do not infer that `UP` and `HALF_UP` are identical for all numbers, or that `DOWN` and `HALF_DOWN` are identical for all numbers. They only agree on certain cases.

### 3.1. `UP` Is Not “Rounding Up on the Number Line”

`UP` means **away from 0** whenever nonzero digits must be dropped:

```java
new BigDecimal("2.1").setScale(0, RoundingMode.UP);   // 3
new BigDecimal("-2.1").setScale(0, RoundingMode.UP);  // -3
```

For negative numbers, `-3` is **less than** `-2.1` on the number line. Therefore do not loosely translate `UP` as “choose the larger number”.

`DOWN` means **toward 0**:

```java
new BigDecimal("2.9").setScale(0, RoundingMode.DOWN);   // 2
new BigDecimal("-2.9").setScale(0, RoundingMode.DOWN);  // -2
```

This is not `Math.floor` for negative numbers; `FLOOR` of `-2.9` is `-3`, while `DOWN` is `-2`.

### 3.2. `CEILING` and `FLOOR` Depend on Number-Line Direction

- `CEILING`: **smallest** representable number **not less than** the original.
- `FLOOR`: **largest** representable number **not greater than** the original.

At scale 0:

```java
new BigDecimal("2.5").setScale(0, RoundingMode.CEILING);   // 3
new BigDecimal("-2.5").setScale(0, RoundingMode.CEILING);  // -2

new BigDecimal("2.5").setScale(0, RoundingMode.FLOOR);     // 2
new BigDecimal("-2.5").setScale(0, RoundingMode.FLOOR);    // -3
```

For positive numbers, `CEILING` behaves like `UP` when digits must be dropped, and `FLOOR` behaves like `DOWN`. For negative numbers, it is the reverse. This rule applies not only at ties, but whenever any nonzero part must be discarded.

### 3.3. The Three `HALF_*` Modes: Nearest Neighbor, Then Tie-Breaking

`HALF_UP`, `HALF_DOWN`, and `HALF_EVEN` all **prefer the result closest to the original number**. They differ only when the distances to the two neighboring candidates are **exactly equal**:

- `HALF_UP`: tie → away from 0.
- `HALF_DOWN`: tie → toward 0.
- `HALF_EVEN`: tie → last **retained** digit is even.

`HALF_EVEN` is also called *round half to even* or *banker's rounding* in some references. The name does not mean every banking transaction mandates it; business rules, contracts, or laws dictate the mode.

For example, at scale 0:

- `2.5` → `2` with `HALF_EVEN`, because `2` is even and `3` is odd.
- `3.5` → `4` with `HALF_EVEN`, because `4` is even and `3` is odd.
- `-2.5` → `-2` with `HALF_EVEN`, because the units digit `2` is even.
- `-3.5` → `-4` with `HALF_EVEN`, because the units digit `4` is even.

Note that `HALF_EVEN` **does not always round down**: the result for `3.5` is `4`.

### 3.4. `UNNECESSARY`: A No-Information-Loss Contract

`RoundingMode.UNNECESSARY` requires the exact operation to **need no rounding**. If the number cannot be represented at the requested scale/precision without discarding significant digits, the API throws `ArithmeticException`.

```java
new BigDecimal("2.00").setScale(0, RoundingMode.UNNECESSARY);
// 2 — valid: drops only insignificant zeros.

new BigDecimal("2.50").setScale(0, RoundingMode.UNNECESSARY);
// ArithmeticException — would require dropping significant 0.5 part.
```

`UNNECESSARY` does not mean “default rounding”; it is a **prohibition on rounding**. Useful for data validation, smallest currency units, or strict exactness requirements. Replacing it with `DOWN` to avoid an exception **changes the contract**.

## 4. Complete Result Matrix at `±2.5` and `±3.5`

All inputs are exact `BigDecimal` strings; target is `scale = 0`.

| `RoundingMode` | `+2.5` | `-2.5` | `+3.5` | `-3.5` |
| --- | ---: | ---: | ---: | ---: |
| `UP` | `3` | `-3` | `4` | `-4` |
| `DOWN` | `2` | `-2` | `3` | `-3` |
| `CEILING` | `3` | `-2` | `4` | `-3` |
| `FLOOR` | `2` | `-3` | `3` | `-4` |
| `HALF_UP` | `3` | `-3` | `4` | `-4` |
| `HALF_DOWN` | `2` | `-2` | `3` | `-3` |
| `HALF_EVEN` | `2` | `-2` | `4` | `-4` |
| `UNNECESSARY` | **error** | **error** | **error** | **error** |

The two `2.5` columns test sign; the two `3.5` columns test **`HALF_EVEN` parity**. Testing only `2.5` can fail to expose a buggy custom implementation that “always picks the smaller magnitude for `HALF_EVEN`”.

Another point: `HALF_UP` at the negative tie `-2.5` yields `-3`, not `-2`. “UP” in `HALF_UP` means **away from 0 on ties**, not *ceiling*.

## 5. Testing Exact Midpoints at One Decimal Place

For `setScale(1, mode)`:

| Value | Neighboring results | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` |
| --- | --- | --- | --- | --- |
| `2.25` | `2.2` or `2.3` | `2.3` | `2.2` | `2.2` |
| `2.35` | `2.3` or `2.4` | `2.4` | `2.3` | `2.4` |
| `-2.25` | `-2.2` or `-2.3` | `-2.3` | `-2.2` | `-2.2` |
| `-2.35` | `-2.3` or `-2.4` | `-2.4` | `-2.3` | `-2.4` |

With `2.25`, the last retained digits of the two candidates are `2` and `3`; `HALF_EVEN` picks `2.2`. With `2.35`, the last digits are `3` and `4`; the result is `2.4`. You do not inspect the **whole integer part** or “digit before the decimal point” for parity when rounding to scale 1.

Likewise for negative numbers: parity of the last digit does not depend on sign. The chosen result still comes from the **two candidates closest to the original value**, never arbitrarily dropping the negative sign.

### Points Just Off the Tie (Not Exact Midpoints)

A tiny digit difference stops `HALF_*` modes from diverging:

| Value to scale 0 | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` | Explanation |
| --- | --- | --- | --- | --- |
| `2.4999` | `2` | `2` | `2` | Closer to `2` |
| `2.5000` | `3` | `2` | `2` | True tie |
| `2.5001` | `3` | `3` | `3` | Closer to `3` |
| `-2.4999` | `-2` | `-2` | `-2` | Closer to `-2` |
| `-2.5000` | `-3` | `-2` | `-2` | True tie |
| `-2.5001` | `-3` | `-3` | `-3` | Closer to `-3` |

`HALF_DOWN` **does not always move toward 0**; it chooses that direction only at an exact midpoint. For example, `2.5001` with `HALF_DOWN` gives `3`, while `DOWN` gives `2`.

That is why test suites need ties, just below ties, and just above ties—not just `.5`.

## 6. Verifying with a Complete Java 17+ Program

Save the following content as **`RoundingMidpointDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RoundingMidpointDemo {

    // Return ERROR text when rounding is forbidden.
    static String roundOrReject(
            String input, int scale, RoundingMode mode) {
        try {
            return new BigDecimal(input)
                    .setScale(scale, mode)
                    .toPlainString();
        } catch (ArithmeticException ex) {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        System.out.println(
                "Mode: +2.5, -2.5, +3.5, -3.5 (scale=0)");

        for (RoundingMode mode : RoundingMode.values()) {
            System.out.println(mode + ": "
                    + roundOrReject("2.5", 0, mode) + ", "
                    + roundOrReject("-2.5", 0, mode) + ", "
                    + roundOrReject("3.5", 0, mode) + ", "
                    + roundOrReject("-3.5", 0, mode));
        }

        System.out.println("HALF_EVEN 2.25 => "
                + roundOrReject("2.25", 1, RoundingMode.HALF_EVEN));
        System.out.println("HALF_EVEN 2.35 => "
                + roundOrReject("2.35", 1, RoundingMode.HALF_EVEN));
        System.out.println("HALF_EVEN -2.25 => "
                + roundOrReject("-2.25", 1, RoundingMode.HALF_EVEN));
        System.out.println("HALF_EVEN -2.35 => "
                + roundOrReject("-2.35", 1, RoundingMode.HALF_EVEN));

        System.out.println("HALF_DOWN 2.5001 => "
                + roundOrReject("2.5001", 0, RoundingMode.HALF_DOWN));
        System.out.println("HALF_UP 2.4999 => "
                + roundOrReject("2.4999", 0, RoundingMode.HALF_UP));

        System.out.println("UNNECESSARY 2.00 => "
                + roundOrReject("2.00", 0, RoundingMode.UNNECESSARY));
        System.out.println("UNNECESSARY 2.50 => "
                + roundOrReject("2.50", 0, RoundingMode.UNNECESSARY));

        System.out.println("String 2.675 => "
                + new BigDecimal("2.675")
                        .setScale(2, RoundingMode.HALF_EVEN));

        System.out.println("Double 2.675 => "
                + new BigDecimal(2.675)
                        .setScale(2, RoundingMode.HALF_EVEN));

        System.out.println("precision2 9.95 => "
                + new BigDecimal("9.95")
                        .round(new MathContext(
                                2, RoundingMode.HALF_UP))
                        .toPlainString());
    }
}
```

Compile and execute:

```bash
javac RoundingMidpointDemo.java
java RoundingMidpointDemo
```

Deterministic stdout on Java 17+:

```text
Mode: +2.5, -2.5, +3.5, -3.5 (scale=0)
UP: 3, -3, 4, -4
DOWN: 2, -2, 3, -3
CEILING: 3, -2, 4, -3
FLOOR: 2, -3, 3, -4
HALF_UP: 3, -3, 4, -4
HALF_DOWN: 2, -2, 3, -3
HALF_EVEN: 2, -2, 4, -4
UNNECESSARY: ERROR, ERROR, ERROR, ERROR
HALF_EVEN 2.25 => 2.2
HALF_EVEN 2.35 => 2.4
HALF_EVEN -2.25 => -2.2
HALF_EVEN -2.35 => -2.4
HALF_DOWN 2.5001 => 3
HALF_UP 2.4999 => 2
UNNECESSARY 2.00 => 2
UNNECESSARY 2.50 => ERROR
String 2.675 => 2.68
Double 2.675 => 2.67
precision2 9.95 => 10
```

The `roundOrReject(...)` helper prints `ERROR` only for **learning and comparison purposes**. In production applications, when `UNNECESSARY` fails, handle the proper exception type or return a clear validation message; never silently replace the result with 0 or swallow the exception and continue billing.

Looping over `RoundingMode.values()` ensures you **do not accidentally omit the eighth mode**. Printing both signs and both parities (`2.5`, `3.5`) catches more classes of bugs in custom implementations than a single example.

## 7. Why Can `new BigDecimal(2.675)` Break Midpoint Tests?

Many decimal numbers cannot be represented exactly in finite binary. The Java literal `2.675` has type `double` and is stored as a binary value very close to `2.675` yet **not equal to** that exact decimal number.

Therefore:

```java
BigDecimal decimalExact = new BigDecimal("2.675");
BigDecimal fromDouble  = new BigDecimal(2.675);

System.out.println(
        decimalExact.setScale(2, RoundingMode.HALF_EVEN)); // 2.68
System.out.println(
        fromDouble.setScale(2, RoundingMode.HALF_EVEN));   // 2.67
```

`decimalExact` lies squarely between `2.67` and `2.68`; the last digit `8` is even, so `HALF_EVEN` yields `2.68`. Meanwhile `fromDouble` represents the **exact binary value stored from the literal**, slightly less than `2.675`, so it is closer to `2.67` and yields `2.67`. This does not mean `HALF_EVEN` behaves inconsistently; **the inputs were already different**.

If you must start from a `double`, `BigDecimal.valueOf(2.675)` uses the decimal representation from `Double.toString` and is usually preferable to `new BigDecimal(double)` for general conversion. Still, `valueOf` cannot recover an original decimal value if prior approximate arithmetic was done in `double`. For decimal tie test cases, prefer constructing from **strings** or `BigDecimal.valueOf(long, scale)` when you have a scaled integer.

### How to Construct Standard Test Data

```java
// Two exact ways to construct 2.675:
BigDecimal a = new BigDecimal("2.675");
BigDecimal b = BigDecimal.valueOf(2675L, 3);

System.out.println(a.compareTo(b) == 0); // true
```

For midpoint cases requiring decimal exactness, do not use intermediate `double` arithmetic to compute expected values. Do not use `Math.round(double)` as a general oracle to verify the eight `RoundingMode`s: it has its own rules and is subject to floating-point representation.

## 8. Distinguishing `setScale` from `MathContext`: Two Kinds of Rounding Problems

### 8.1. `setScale`: Digits After the Decimal Point

`setScale(targetScale, mode)` rounds to a **target scale**:

```java
BigDecimal value = new BigDecimal("123.45");

BigDecimal fixed = value.setScale(1, RoundingMode.HALF_UP);
// fixed = 123.5
```

With scale 0, the result is an integer; with scale 2, the result has two decimal places (possibly padding trailing zeros). `BigDecimal` values can have a **negative scale**, so this is not merely a formatting option; it defines the decimal quantization unit.

### 8.2. `MathContext`: Total Significant Digits

`new MathContext(precision, mode)` controls **precision** (number of significant digits), not digits after the decimal point:

```java
BigDecimal input = new BigDecimal("9.95");
BigDecimal rounded = input.round(
        new MathContext(2, RoundingMode.HALF_UP));

// Numerical result is 10, with 2 significant digits.
System.out.println(rounded.toPlainString()); // 10
```

Exact midpoints in a precision problem also depend on input magnitude and which digit is dropped. If you need money with two decimal places, do not replace `setScale(2, mode)` with `round(new MathContext(2, mode))`.

### 8.3. Rounding at Intermediate Steps Differs from Rounding Once at the End

```java
BigDecimal a = new BigDecimal("0.005");
BigDecimal b = new BigDecimal("0.005");
BigDecimal c = new BigDecimal("0.005");

BigDecimal roundTotal = a.add(b).add(c)
        .setScale(2, RoundingMode.HALF_UP); // 0.02

BigDecimal roundEach = a.setScale(2, RoundingMode.HALF_UP)
        .add(b.setScale(2, RoundingMode.HALF_UP))
        .add(c.setScale(2, RoundingMode.HALF_UP)); // 0.03
```

Same mode yet **different rounding boundaries** yield different totals. This is a business decision (round per line item or per invoice total), not an arbitrary optimization choice.

## 9. Recommended Test Matrix for All `RoundingMode` Values

A single test case at `2.5` is insufficient. Design an **axis-based matrix**, especially when verifying custom rounding functions or DB/API integrations.

| Test group | Sample values | What to verify |
| --- | --- | --- |
| Positive integer tie | `2.5`, `3.5` to scale 0 | Parity choice in `HALF_EVEN`, away/toward |
| Negative integer tie | `-2.5`, `-3.5` to scale 0 | Distinguish `UP` vs `CEILING`; `DOWN` vs `FLOOR` |
| Scale-1 tie | `2.25`, `2.35`, `-2.25`, `-2.35` | Even/odd retained digit |
| Just below tie | `2.4999`, `-2.4999` | `HALF_*` picks nearest candidate |
| Just above tie | `2.5001`, `-2.5001` | Not misclassified as tie |
| No rounding needed | `2.00` to scale 0 | All modes give `2`; `UNNECESSARY` succeeds |
| Rounding forced | `2.50` to scale 0 | `UNNECESSARY` must throw |
| Zero values | `0`, `0.000`, `-0.000` | No spurious result; note `BigDecimal` does not preserve negative zero |
| Large/small values | `999.95`, `0.00005` at suitable scales | Carry into new digit place, scale range |
| Finite precision | `9.95` with precision 2 | Distinguish `MathContext` from scale |
| Inputs from `double` | `2.675` literal vs `"2.675"` | Do not confuse input error with rounding bug |
| Fractions from division | `1/3`, `1/8` | Needs appropriate mode/context; `UNNECESSARY` if non-exact |
| Negative data | `-0.1`, `-9.9` | Correct directions toward +∞, −∞, and 0 |

### 9.1. Testing Cases Requiring No Rounding

If the number already lies exactly on the target scale's “grid”, every mode must preserve the **numerical value**:

```java
BigDecimal input = new BigDecimal("5.000");

for (RoundingMode mode : RoundingMode.values()) {
    BigDecimal result = input.setScale(0, mode);
    if (result.compareTo(new BigDecimal("5")) != 0) {
        throw new AssertionError("Wrong when rounding is unnecessary: " + mode);
    }
}
```

With `BigDecimal`, `equals` also checks scale, so `new BigDecimal("5.000")` does not equal `new BigDecimal("5")` via `equals`, even though they are numerically equal. Choose the comparison matching the test case contract.

### 9.2. Useful Invariants for Property-Based Testing

If `x` is a finite `BigDecimal` value and `r = x.setScale(scale, mode)` succeeds without range/resource errors:

- **Fixed scale:** `r.scale() == scale`.
- **Idempotence at the same scale:** `r.setScale(scale, mode).equals(r)`; after the first call, no digits remain to drop.
- **No wrong-direction `UP`/`DOWN`:** `UP` never produces a smaller absolute magnitude than the original when digits are dropped; `DOWN` never produces a larger absolute magnitude than the original.
- **No wrong-order `CEILING`/`FLOOR`:** `CEILING` never returns a number smaller than `x`; `FLOOR` never returns a number larger than `x`.
- **When no rounding is needed:** all modes, including `UNNECESSARY`, produce the same numerical value.
- **Within `HALF_*`:** if the input is not an exact tie, all three modes pick the same nearest candidate (when rounding is needed).
- **When significant digits must be dropped:** `UNNECESSARY` must throw `ArithmeticException`.

Invariants do not replace specific **expected values** for all tie cases. Combine them with an oracle (the tables in sections 4/5), exception checks, and positive/negative value tests.

### 9.3. Exact Exception Testing

Do not write tests like:

```java
// Bad: silently swallows every error and treats it as success.
try {
    computation();
} catch (Exception ignored) {
}
```

If the rule specifies that `UNNECESSARY` throws `ArithmeticException`, check the **exact exception type**. In JUnit 5, use `assertThrows(ArithmeticException.class, ...)`; using only core Java, use an explicit flag and `try/catch(ArithmeticException)` and throw `AssertionError` if the exception does not occur.

Testing “does not throw” on `2.00` is just as important as testing “must throw” on `2.50`.

## 10. Library-Free Testing Example

You can place these methods in a Java test class using standard APIs directly:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

static void expectRounded(
        String input, int scale,
        RoundingMode mode, String expected) {

    BigDecimal actual = new BigDecimal(input).setScale(scale, mode);

    // Also compare toPlainString to verify the example's scale/formatting.
    if (!actual.toPlainString().equals(expected)) {
        throw new AssertionError(
                input + " with " + mode + " => "
                + actual.toPlainString() + ", expected " + expected);
    }
}

static void expectRoundingRejected(
        String input, int scale) {

    try {
        new BigDecimal(input)
                .setScale(scale, RoundingMode.UNNECESSARY);
    } catch (ArithmeticException expected) {
        return;
    }
    throw new AssertionError(
            "Should reject rounding for " + input);
}
```

These are **two embedded helper methods**, not a standalone Java file. Example calls inside a test method:

```java
expectRounded("2.5", 0, RoundingMode.HALF_UP, "3");
expectRounded("-2.5", 0, RoundingMode.HALF_UP, "-3");
expectRounded("3.5", 0, RoundingMode.HALF_EVEN, "4");
expectRounded("2.25", 1, RoundingMode.HALF_EVEN, "2.2");
expectRounded("2.35", 1, RoundingMode.HALF_EVEN, "2.4");
expectRounded("-2.5", 0, RoundingMode.CEILING, "-2");
expectRounded("-2.5", 0, RoundingMode.FLOOR, "-3");
expectRounded("2.00", 0, RoundingMode.UNNECESSARY, "2");
expectRoundingRejected("2.50", 0);
```

A recommended next step is implementing **data-driven tests** to verify the eight-mode matrix across many inputs, rather than writing separate `if` branches per mode. Never compute the expected value using the same production function under test and compare it against itself; that detects no algorithmic bugs.

## 11. Real-World Applications: Money, Taxes, Cross-System Testing

APIs such as `BigDecimal.divide(scale, mode)`, `setScale`, and `round(MathContext)` can all perform rounding, yet their **timing** and **purpose** differ.

For monetary data, one policy might state: “Store amounts to two decimal places, rejecting inputs not exact at scale 2.” That is a valid reason to use `setScale(2, UNNECESSARY)` at the storage boundary. Another policy might compute tax at high precision and round `HALF_UP` at settlement; that is a different choice. There is no default mode “right for every currency”.

When integrating with `DECIMAL(p,s)` databases, JSON serializers, accounting software, or external systems, test not only `BigDecimal` inside the JVM, but the entire pipeline:

1. Parse the input string into an exact decimal number.
2. Apply rounding, scale, or precision rules at the defined boundary.
3. Persist via JDBC/ORM or serialize to JSON in the published format.
4. Read back and compare both **numerical value** and **scale/formatting**, if required by the contract.
5. Test positive/negative ties and overflow/exception policies on both sides.

A database or driver may have its own rounding rules. Do not let database casting silently override decisions in the business layer; clarify each system's responsibility and use integration tests for exact midpoint values.

If an exchange protocol mandates preserving “`2.50`” instead of “`2.5`”, distinguish numeric value from string representation and scale. `BigDecimal.toPlainString()` preserves the current scale, whereas `stripTrailingZeros()` can drop trailing zeros that are meaningful for formatting or the contract.

## 12. Common Misconceptions

| Misconception | Consequence | Corrective rule |
| --- | --- | --- |
| “`UP` means increasing on the number line” | Rounds negative numbers wrongly | `UP` means **away from 0** |
| “`DOWN` is always the same as `FLOOR`” | Wrong for negative numbers | `DOWN` toward 0; `FLOOR` toward −∞ |
| “`CEILING` always increases magnitude” | Wrong for negative numbers | `CEILING` toward +∞ |
| “`HALF_UP` rounds every remainder up” | Wrong below the tie | Pick nearest; only ties go away from 0 |
| “`HALF_DOWN` always rounds down” | Wrong above the tie | Pick nearest; only ties go toward 0 |
| “`HALF_EVEN` always goes down” | `3.5` wrongly becomes `3` | Tie picks even **retained** digit |
| “`HALF_EVEN` checks the digit right before the decimal point” | Wrong when scale > 0 or negative | Inspect the last digit of the **target result** |
| “`UNNECESSARY` is a no-op mode” | Swallows errors that must be thrown | Valid only when no rounding is needed |
| Testing only `+2.5`, skipping `-2.5` | Misses directional bugs with negative numbers | Test both signs |
| Testing only `2.5`, skipping `3.5` | Misses even/odd bugs | Test both parities |
| Testing with `new BigDecimal(2.675)` | Input is not a decimal tie | Construct from string, use exact values |
| Confusing `MathContext(2)` with `setScale(2)` | Wrong precision scope | Use the API matching the contract |
| Rounding per line instead of at the total | Can change total amount | Preserve the specified rounding boundary |
| Using old integer `BigDecimal.ROUND_*` constants | Hard-to-read, deprecated API | Use the `RoundingMode` enum |
| Using `equals` when only numerical equality matters | Fails for `2.0` vs `2.00` | Use `compareTo` if scale does not matter |

## 13. Exercises and Solutions

**Exercise 1.** Fill in the `setScale(0, ...)` results for `+7.5` and `-7.5` across all eight modes. Then explain why `HALF_EVEN` picks `8` and `-8`.

*Hint:* candidates are `7`, `8`, `-7`, `-8`; at the tie, the results with an even last digit are ±8. `UNNECESSARY` throws an error.

**Exercise 2.** For inputs `-2.4999`, `-2.5000`, `-2.5001`, compare `HALF_UP`, `HALF_DOWN`, `HALF_EVEN`, `UP`, `DOWN`, `CEILING`, and `FLOOR`. Do the two off-midpoint values behave identically across the `HALF_*` modes?

*Hint:* `HALF_*` all yield `-2` at `-2.4999`, diverge at `-2.5000`, and all yield `-3` at `-2.5001`. Directional modes (UP/DOWN/CEILING/FLOOR) do not depend on the tie condition.

**Exercise 3.** A system stores at most two exact decimal places and must not auto-round. How are `1.2300`, `1.234`, and `1.200` handled with `setScale(2, UNNECESSARY)`?

*Hint:* `1.2300` → `1.23`; `1.234` is rejected; `1.200` → `1.20`. Trailing zeros can be dropped exactly, yet nonzero digits must be preserved.

**Exercise 4.** Why can `new BigDecimal("2.675")` and `new BigDecimal(2.675)` give different `HALF_EVEN` results at scale 2? Which way of creating inputs should be used for decimal midpoint tests?

*Hint:* the first is exact decimal; the second holds the true binary value of `double`, not exact `2.675`. Construct from string or unscaled integer with scale.

**Exercise 5.** A result `9.95` is rounded using `new MathContext(2, HALF_UP)`. Does that mean keeping two decimal places or two significant digits? Why is the result `10`?

*Hint:* precision 2 is **two significant digits**, not scale 2. Rounding up propagates a carry into the next digit place.

**Exercise 6.** Design a test table for `RoundingMode` across the two dimensions of **sign** and **parity**, adding at least three non-tie boundary cases. How do you test both success and failure paths of `UNNECESSARY`?

*Hint:* use the matrices from sections 4 and 5 plus `2.4999`, `2.5001`, `-2.4999`; check the exact `ArithmeticException` type.

## 14. Practical Conclusions

To test rounding properly, **always start from the contract on scale/precision and when rounding occurs**. Build a matrix with **both positive and negative numbers**, **even and odd last digits**, **exact ties, just below ties, and just above ties**, along with cases requiring **no rounding** and cases where `UNNECESSARY` must reject.

Use `BigDecimal` from strings to construct exact decimal midpoints; do not use `double` and treat an approximate value as a true tie. `UP`, `DOWN`, `CEILING`, and `FLOOR` are **directional** rules; `HALF_UP`, `HALF_DOWN`, and `HALF_EVEN` are **nearest-neighbor + tie-breaking** rules; `UNNECESSARY` is a **no-rounding-allowed** rule.

Standard Java SE 17 documentation:
- [`RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): description of each mode and positive/negative case diagrams.
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `setScale`, `divide`, `round`, precision/scale, and `ArithmeticException` handling.
- [`MathContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision and rounding mode for operations.
