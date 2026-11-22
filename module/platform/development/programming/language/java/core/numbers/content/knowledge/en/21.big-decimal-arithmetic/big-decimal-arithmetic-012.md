# `ArithmeticException` When Exactness Requirements Cannot Be Met in `BigDecimal`

## 1. The Issue to Understand

`BigDecimal` represents decimal numbers using an unscaled integer (`unscaledValue`) and a `scale`:

```text
value = unscaledValue × 10^(-scale)
1.230 = 1230 × 10^(-3)
```

Thanks to this, numbers like `0.1` and `12.34` can be represented exactly in decimal if initialized from appropriate strings. However, **not every quotient of two terminating decimals has a terminating decimal representation**. For example, `1 / 3 = 0.3333...` has infinitely many digits.

If a program demands an **exact** result when a finite representation cannot satisfy it, or forbids all rounding even though the operation requires rounding, `BigDecimal` throws `ArithmeticException`. This is a signal that *the requested exactness condition cannot be satisfied*, not that the `BigDecimal` type is inherently imprecise.

Three common scenarios:

- Calling `divide(BigDecimal)` for a non-terminating decimal quotient, such as `1 / 3`.
- Using `RoundingMode.UNNECESSARY` with `setScale`, `divide`, or `round` when producing a result requires discarding nonzero digits.
- Using a `MathContext` with a significant-digit limit (`precision`) and mode `UNNECESSARY` when the result cannot fit untouched within that limit.

**Scope:** This lesson focuses on exceptions caused by exactness/rounding requirements in `BigDecimal` operations. Division by 0 also throws `ArithmeticException`, though it is a separate root cause to distinguish during diagnosis.

## 2. Exactness, Scale, Precision, and Rounding Are Four Distinct Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Numeric value | The mathematical quantity represented | `1.230` and `1.23` have the same value |
| `scale` | Number of digits to the right of the decimal point for non-negative scale | `1.230` has scale 3 |
| `precision` | Number of digits in `unscaledValue` (excluding sign); includes trailing zeros if present in representation | `1.230` has precision 4 |
| `RoundingMode` | Rule when nonzero digits must be dropped to meet scale/precision | `HALF_UP`, `HALF_EVEN`, `DOWN`, `UNNECESSARY` |

For example, `new BigDecimal("1.230").setScale(2, RoundingMode.UNNECESSARY)` becomes `1.23` **without error**: only a zero digit is dropped and the value does not change. Conversely, `new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY)` would have to drop the nonzero digit 4, so it throws `ArithmeticException`.

`UNNECESSARY` is not a “best rounding” mode; it is a **verification check** that the transformation *needs no* rounding. Use it when losing any nonzero digit must be detected and handled.

`MathContext.UNLIMITED` has `precision = 0`, meaning no significant-digit limit is imposed. It does **not** give `1 / 3` a finite sequence of decimal digits. Therefore, dividing a non-terminating quotient with an unlimited context can still throw an exception.

## 3. Diagnosing Exact Division Failures from Quotient Nature

`divide(divisor)` succeeds only when the quotient has a terminating decimal representation. After reducing the fraction, the denominator may contain only factors of 2 and 5; thus `1/8`, `3/6` succeed, whereas `1/3`, `1/6` throw `ArithmeticException`. The lesson *Exact divide and non-terminating repeating decimals* proved this criterion.

When **handling the exception**, first check `divisor.signum() == 0` to isolate invalid input errors. If the divisor is nonzero, check whether the overload requires an exact quotient, or whether `RoundingMode.UNNECESSARY` or a `MathContext` is rejecting the loss of nonzero digits. **Do not** catch everything generically and silently default to `HALF_UP`: that alters the exactness contract.

## 4. Easily Confused Overloads of `divide`

```java
BigDecimal a = new BigDecimal("1");
BigDecimal b = new BigDecimal("3");

// Requires an exact quotient: throws ArithmeticException.
a.divide(b);

// Specifies 2 digits after the decimal point and a rounding mode.
a.divide(b, 2, RoundingMode.HALF_UP); // 0.33

// Specifies at most 5 significant digits for the result.
a.divide(b, new MathContext(5, RoundingMode.HALF_EVEN)); // 0.33333

// Forbids rounding in a scale 2 result: throws ArithmeticException.
a.divide(b, 2, RoundingMode.UNNECESSARY);
```

These lines are **standalone API illustrations**, not a sequential runnable program: if `divide(b)` executes without catching its exception, subsequent lines will not run.

Key points to remember:

1. `divide(divisor)` requires exactness and does not automatically pick a digit count or rounding policy.
2. `divide(divisor, scale, roundingMode)` controls **digits after the decimal point**. For example, scale 2 produces numbers like `0.33`.
3. `divide(divisor, mathContext)` controls **significant digits**, which differs from decimal places. For example, precision 5 gives `0.33333`, while `12345 / 1` at precision 5 still has five digits before the decimal point.
4. `divide(divisor, roundingMode)` is a different overload: **the result's scale equals the dividend's scale**. It does not default to two decimal places. Because of this distinction, in business code prefer overloads that explicitly declare scale or `MathContext`.

Even when choosing `UNNECESSARY`, division can still succeed if the exact quotient fits the requested scale/precision. For example, `new BigDecimal("1").divide(new BigDecimal("8"), 3, RoundingMode.UNNECESSARY)` returns `0.125`; at scale 2 it throws an exception.

## 5. Runnable Java 17+ Example and Exact Output

Save file `BigDecimalExactnessDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalExactnessDemo {
    private static void attempt(String label, Runnable operation) {
        try {
            operation.run();
        } catch (ArithmeticException e) {
            System.out.println(label + ": " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        BigDecimal one = new BigDecimal("1");
        BigDecimal three = new BigDecimal("3");

        System.out.println("1 / 8 exact = "
                + one.divide(new BigDecimal("8")));

        attempt("1 / 3 exact", () ->
                System.out.println(one.divide(three)));

        System.out.println("1 / 3 scale=2 = "
                + one.divide(three, 2, RoundingMode.HALF_UP));

        System.out.println("1 / 3 precision=5 = "
                + one.divide(three, new MathContext(5, RoundingMode.HALF_EVEN)));

        System.out.println("Drop trailing zero = "
                + new BigDecimal("1.230")
                        .setScale(2, RoundingMode.UNNECESSARY));

        attempt("Drop nonzero digit", () ->
                System.out.println(new BigDecimal("1.234")
                        .setScale(2, RoundingMode.UNNECESSARY)));

        attempt("Precision=2 without rounding", () ->
                System.out.println(new BigDecimal("12.345")
                        .round(new MathContext(2, RoundingMode.UNNECESSARY))));

        attempt("Division by zero", () ->
                System.out.println(one.divide(BigDecimal.ZERO)));
    }
}
```

Run:

```bash
javac BigDecimalExactnessDemo.java
java BigDecimalExactnessDemo
```

Stdout:

```text
1 / 8 exact = 0.125
1 / 3 exact: ArithmeticException
1 / 3 scale=2 = 0.33
1 / 3 precision=5 = 0.33333
Drop trailing zero = 1.23
Drop nonzero digit: ArithmeticException
Precision=2 without rounding: ArithmeticException
Division by zero: ArithmeticException
```

The example intentionally prints only the **exception class name**: the detail message of `ArithmeticException` can vary across APIs or JDK versions and should not be used as a logical contract. In real applications, do not catch every `ArithmeticException` and substitute a default value: that can mask division-by-0 bugs or invariant violations.

## 6. Why Does `MathContext` with `UNNECESSARY` Also Error?

`MathContext` is a pair of `precision` and `roundingMode`. For example:

```java
BigDecimal x = new BigDecimal("1.234");
MathContext strict = new MathContext(3, RoundingMode.UNNECESSARY);

// Needs to convert 1.234 to a number with only 3 significant digits.
// Because the trailing digit 4 is nonzero, round(strict) throws ArithmeticException.
x.round(strict);
```

Conversely, `new BigDecimal("1.230").round(new MathContext(3, RoundingMode.UNNECESSARY))` can return `1.23` because only a trailing zero is dropped without changing value.

Precision limits do not only affect `round`: several overloads of `add`, `subtract`, `multiply`, `divide`, and `pow` accept a `MathContext` and may also require rounding. For instance, `new BigDecimal("1.23").multiply(new BigDecimal("2"), new MathContext(2, RoundingMode.UNNECESSARY))` tries to fit `2.46` into two significant digits: impossible, so it throws an exception.

If a calculation must be exact, consider keeping intermediate values without precision limits and applying representation rules only at an **agreed-upon boundary**. Do not arbitrarily raise precision thinking the exception is solved: the quotient `1 / 3` will still never have an exact finite decimal representation.

## 7. Choosing a Solution by Business Requirements

**Case A — a valid rounded result is needed.** Determine the required scale or precision, then pick `RoundingMode` according to business rules:

```java
BigDecimal ratio = new BigDecimal("1")
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333
```

**Case B — losing any nonzero digit is unacceptable.** Use exact operations or `UNNECESSARY` as an intentional assertion; translate failures into a contextual business error message:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class ExactMoney {
    public static BigDecimal requireTwoDecimals(BigDecimal value) {
        try {
            return value.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException cause) {
            throw new IllegalArgumentException(
                    "Amount cannot be represented exactly with two decimals", cause);
        }
    }
}
```

This snippet is a compilable utility class with no `main`, so it does not run on its own. For `12.340`, it returns `12.34`; for `12.345`, it throws `IllegalArgumentException` while preserving the `ArithmeticException` cause for traceability. Only enforce a two-decimal constraint if that is genuinely the system's data contract.

**Case C — splitting money or units that do not divide evenly.** Rounding each share's quotient can cause the distributed total to differ from the original total. You must specify how to handle the remainder, such as assigning it to the last element:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class AllocationDemo {
    public static void main(String[] args) {
        BigDecimal total = new BigDecimal("10.00");
        BigDecimal count = new BigDecimal("3");
        BigDecimal first = total.divide(count, 2, RoundingMode.DOWN);
        BigDecimal second = first;
        BigDecimal last = total.subtract(first).subtract(second);

        System.out.println(first + ", " + second + ", " + last);
        System.out.println(first.add(second).add(last));
    }
}
```

Run `javac AllocationDemo.java` then `java AllocationDemo`; stdout is:

```text
3.33, 3.33, 3.34
10.00
```

This example only illustrates preserving the sum; remainder distribution order, currency, smallest unit, tax rules, and audit requirements must be specified separately. `RoundingMode.DOWN` is used here for easy tracking of positive allocation, not as a universal mode for all transactions.

## 8. How to Diagnose When Seeing `ArithmeticException`

1. **Identify the failing operation**: `divide`, `setScale`, `round`, or an overload using `MathContext`. Inspect the stack trace and operand values rather than catching and swallowing the exception.
2. **Check the denominator**: if equal to 0, handle the input condition; rounding rules do not fix division by 0.
3. **Check exactness requirements**: `divide(divisor)` on a non-terminating decimal quotient will fail; decide whether to permit rounding or reject the division.
4. **Check `UNNECESSARY`**: is reducing scale/precision forcing a nonzero digit to be dropped? If so, that is a true violation of the exactness policy.
5. **Distinguish precision from scale**: `MathContext(2, ...)` is two significant digits, not two digits after the decimal point; `setScale(2, ...)` controls two decimal places.
6. **Verify against the business contract**: is approximation allowed, which rounding mode applies, is rounding done once or multiple times, and how must remainders be allocated?
7. **Write tests for edge cases**: terminating quotient (`1/8`), non-terminating quotient (`1/3`), dropping zeros (`1.230 → 1.23`), dropping nonzero digits (`1.234 → 1.23`), and zero divisor.

Do not “quick fix” using `double`: binary floating-point numbers can introduce additional representation errors. Nor should you silently round inside shared utilities when callers have not agreed to a rounding policy.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Replace with |
| --- | --- | --- |
| Thinking `BigDecimal` makes exact `1/3` a terminating decimal | `divide` throws an exception | Accept intentional rounding or reject the business operation |
| Using `divide(divisor, RoundingMode.HALF_UP)` thinking the result has two decimal places | Result scale depends on dividend | Use `divide(divisor, 2, RoundingMode.HALF_UP)` if scale 2 is needed |
| Confusing `MathContext(2, ...)` with `setScale(2, ...)` | Precision applies to significant digits, scale applies to fractional places | Choose the parameter matching the intended meaning |
| Using `UNNECESSARY` as a way to avoid thinking about rounding policy | Exception whenever real rounding is needed | Choose a business policy or confirm intentional exactness |
| Using `new BigDecimal(0.1)` to enter an exact decimal | Copies the binary value of the `double` literal | Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` when given a `double` |
| Rounding across multiple steps without checking the total | Accumulated discrepancies, lost remainders | Define rounding boundaries and a remainder allocation rule |
| Catching `ArithmeticException` and returning `BigDecimal.ZERO` | Hides division-by-0 / invalid rounding bugs | Attach context, report errors, or handle per explicit policy |

Note: `BigDecimal.valueOf(0.1)` uses the decimal string representation of the input `double` value and thus normally produces `0.1`, yet it cannot restore accuracy lost earlier during `double` calculations.

## 10. Self-Check

- Why does `new BigDecimal("1").divide(new BigDecimal("40"))` succeed while dividing by `30` fails? **Because** `1/40 = 0.025` is terminating (denominator has only 2 and 5), whereas `1/30` has factor 3 in its reduced denominator.
- Does `new BigDecimal("1.200").setScale(2, RoundingMode.UNNECESSARY)` error? **No**; result `1.20` preserves the value.
- Does `new BigDecimal("1.201").setScale(2, RoundingMode.UNNECESSARY)` error? **Yes**; the nonzero digit 1 would have to be dropped.
- Is increasing `MathContext` to 100 digits a way to compute `1/3` exactly? **No**; precision 100 is still only an approximation if rounding is allowed, while exactness still cannot be represented finitely.
- When is `UNNECESSARY` a reasonable choice? **When exactness is an established invariant**, such as a value sent to a storage field with fixed scale where dropping nonzero digits is disallowed.

## 11. Takeaways

`ArithmeticException` in exact `BigDecimal` operations protects the exactness contract: it occurs when an operation cannot produce an exact finite decimal result, or when scale/precision limits force rounding while `RoundingMode.UNNECESSARY` forbids it. Distinguish **scale** from **precision**, choose `divide` overloads explicitly, derive rounding policies from business requirements, and treat catching the exception as deliberate handling only after understanding the root cause.