# Do Not Round After Every Operation Unless the Contract Requires It

In Java, **rounding numbers is not something that should be automatically added after every arithmetic operation**. A program may need precision for internal calculations, and only round to a specified unit when settling, posting to a ledger, or displaying. Rounding too early can lose information and cause the final total to differ from a calculation that retains precision and rounds only at the settlement boundary.

However, one cannot claim **rounding only at the end is always right** either: if a contract or regulation requires each invoice line, each transaction, or each allocation share to be rounded independently, those points are mandatory business boundaries.

This lesson distinguishes three concepts: **inherent binary rounding** of `float`/`double`; **explicit decimal rounding** using `BigDecimal`, `Math.round`, and `RoundingMode`; and **formatting results for display**. The right way to decide is to read the computation contract: **which value** should be rounded, **when**, **to how many digits**, and **by what rule**?

## 1. Rounding Each Item vs. Rounding the Total Can Differ

Suppose two items are both `0.015`, and we must round to **two decimal places** using the `HALF_UP` rule.

**Approach A — settle each item before summing:**

```text
0.015 -> 0.02
0.015 -> 0.02
Total = 0.04
```

**Approach B — sum first, settle total afterward:**

```text
0.015 + 0.015 = 0.030
round(0.030, 2) = 0.03
```

Same data, same scale, same rounding mode, yet a `0.01` difference. If **each item is an independent payment obligation** recorded at `0.02`, a total of `0.04` may be right. If **the two items are merely intermediate components of a single shared obligation** requiring one-time settlement, `0.03` is appropriate. You cannot arbitrarily pick one if the contract has not specified it.

Java example using exact `BigDecimal` from strings:

```java
BigDecimal amount = new BigDecimal("0.015");

BigDecimal roundedEach = amount.setScale(2, RoundingMode.HALF_UP);
BigDecimal sumRoundedLines = roundedEach.add(roundedEach); // 0.04

BigDecimal sumThenRound = amount.add(amount)
        .setScale(2, RoundingMode.HALF_UP); // 0.03
```

The short code snippets in this lesson assume `import java.math.BigDecimal;` and `import java.math.RoundingMode;` are present, placed inside a method. The complete standalone program is in section 9.

## 2. Do Not Confuse Explicit Decimal Rounding with Binary Precision

Java `double` has about 53 significand bits, and `float` has about 24 bits. Most decimal fractions such as `0.1` have no finite binary representation, so stored values and every floating-point operation can undergo rounding **even when you never call a round function**.

```java
double value = 0.1 + 0.2;
System.out.println(value); // 0.30000000000000004
```

Therefore, the advice "do not round after every operation" means **do not force intermediate results after each step to an arbitrary number of decimal places**, not that the computer can eliminate IEEE 754 error.

Writing:

```java
double value = 0.1 + 0.2;
String displayed = String.format(java.util.Locale.US, "%.2f", value);
// displayed is the string "0.30"; value is still 0.30000000000000004
```

only **formats a string**. It does not modify `value`. If you save the formatted string and parse it back to compute further, the program has silently introduced a rounding step into the data.

### Why Doesn't Rounding at Every Step "Fix" Floating-Point Numbers?

- Some operations have already lost precision **before** the decimal rounding step occurs.
- Rounding to a small scale after every step discards even more information.
- Subsequent steps can accumulate the newly introduced discrepancies.
- `double` holds binary values; the result of `Math.round(x * 100) / 100.0` is still a `double` and does not necessarily represent an exact multiple of `0.01`.

Use decimal rounding only when it **is genuinely part of the requirement**, not simply to make printed numbers look prettier.

## 3. Scale, Precision, and Rounding Mode in `BigDecimal`

`BigDecimal` distinguishes:

| Term | Meaning | Example |
| --- | --- | --- |
| **Scale** | Decimal point position, usually corresponding to digits after the decimal point when scale is non-negative | `12.345` has scale 3 |
| **Precision** | Total significant digits in base 10 | `12.345` has precision 5 |
| **Rounding mode** | Policy deciding what to do when significant digits must be dropped | `HALF_UP`, `HALF_EVEN`, `DOWN`, etc. |

`setScale(2, RoundingMode.HALF_UP)` asks for **two digits after the decimal point**. `round(new MathContext(4, HALF_UP))` asks for **four significant digits**:

```java
BigDecimal x = new BigDecimal("123.4567");

BigDecimal byScale = x.setScale(2, RoundingMode.HALF_UP);
// 123.46

BigDecimal byPrecision = x.round(
        new java.math.MathContext(4, RoundingMode.HALF_UP));
// 123.5
```

The two operations do not substitute for each other. `MathContext(2)` does **not** mean rounding every value to 2 decimal places.

Common modes:

| Mode | Meaning | Scale 2 example |
| --- | --- | --- |
| `HALF_UP` | Exactly halfway between two possibilities, round away from 0 | `2.345 -> 2.35` |
| `HALF_EVEN` | Exactly halfway, choose the even last retained digit | `2.345 -> 2.34`; `2.355 -> 2.36` |
| `DOWN` | Truncate remainder toward 0 | `-2.349 -> -2.34` |
| `FLOOR` | Toward negative infinity | `-2.341 -> -2.35` |
| `CEILING` | Toward positive infinity | `-2.341 -> -2.34` |
| `UNNECESSARY` | No loss of significant digits allowed; throws `ArithmeticException` if rounding is needed | `2.340 -> 2.34` valid; `2.345` rejected |

**There is no single right mode for every business domain.** You need to know the rules for negative numbers, midpoints, currency, taxes, measurements, and each settlement boundary.

## 4. Use `BigDecimal` When Exact Decimal Calculations Are Needed

For addition, subtraction, and multiplication, `BigDecimal` created from strings with APIs that do not pass a `MathContext` can preserve exact decimal results (within resource limits).

```java
BigDecimal a = new BigDecimal("0.015");
BigDecimal b = new BigDecimal("0.015");
BigDecimal sum = a.add(b); // 0.030
BigDecimal settled = sum.setScale(2, RoundingMode.HALF_UP); // 0.03
```

You should not create exact decimals from `double` literals using the constructor:

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromTextRepresentation = BigDecimal.valueOf(0.1);
BigDecimal fromBinaryApproximation = new BigDecimal(0.1);
```

`new BigDecimal(0.1)` reflects **the exact binary approximation of 0.1 sitting in `double`**, not the exact decimal `0.1`. Use decimal strings or integers with a scale if the source data belongs to a decimal model.

### Division Is an Important Exception

`1/3` has no finite decimal representation, so `BigDecimal.ONE.divide(BigDecimal.valueOf(3))` throws `ArithmeticException` if no handling rule is specified. You can use:

```java
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3), 6, RoundingMode.HALF_UP);
// 0.333333
```

This division forces choosing a working precision/scale and will have error. **Intermediate rounding may be necessary** when the result has no finite representation. The goal is to choose a working precision sufficient for the requirement and avoid shrinking it arbitrarily after every addition/multiplication.

Note also that passing a `MathContext` with finite precision into each `add`/`multiply` call can **actively round right at those steps**, unlike using the no-context API.

## 5. Round Unit Price First or Line Total First?

Suppose the exact unit price is `0.335`, quantity is `3`, mode is `HALF_UP`, and target is scale 2.

**Settle unit price first:**

```text
round(0.335, 2) = 0.34
0.34 * 3 = 1.02
```

**Compute line total first:**

```text
0.335 * 3 = 1.005
round(1.005, 2) = 1.01
```

In Java:

```java
BigDecimal price = new BigDecimal("0.335");
BigDecimal quantity = BigDecimal.valueOf(3);

BigDecimal totalFromUnit = price.setScale(2, RoundingMode.HALF_UP)
        .multiply(quantity); // 1.02

BigDecimal totalFromLine = price.multiply(quantity)
        .setScale(2, RoundingMode.HALF_UP); // 1.01
```

If the contract defines **the unit price as settled at 0.34**, multiplying by the settled unit price may be right. If the contract defines the original unit price 0.335 as used to compute **the line amount** before rounding, the result is 1.01.

The key point is distinguishing **intermediate values**, **settled values**, and **values formatted solely for display**. When an amount has been settled by rule, subsequent totals must be based on the settled data if the contract requires it, rather than recomputing differently.

## 6. Cases Where Intermediate Rounding Is Necessary

This guideline **does not forbid purposeful rounding**. Examples:

- **Independent invoice lines:** if tax per line must be rounded, the regulatory total tax may be the sum of **the settled line taxes**.
- **Independently settled transactions:** each actually transferred amount is an obligation in the smallest currency unit. One cannot recompute from "unrounded" amounts and overwrite transaction history.
- **Splitting a total into multiple shares:** each share must lie on the payment unit grid; remainder distribution must be resolved to preserve the sum.
- **Measurement data:** when ingesting results from a fixed-resolution device, rounding/quantization may be part of the measurement itself.
- **Algorithms with specified quantization:** if each iteration is required to round, omitting that step changes the algorithm.

For example, splitting `10.00` into three shares at scale 2: `10 / 3` gives 3.333...; rounding each share to `3.33` and summing yields only `9.99`. A sum-preserving policy might allocate `3.34 + 3.33 + 3.33 = 10.00`. You must specify who receives the remainder, the allocation method, and how negative amounts are handled.

**Business boundaries** matter more than the number of calculation steps or an intuition that "money only has two digits after the decimal point."

## 7. `Math.round` Is Not Automatically Equivalent to an Accounting Rule

A commonly seen trick:

```java
double x = 12.345;
double twoPlaces = Math.round(x * 100.0) / 100.0;
```

It has limitations:

- `x` and the multiplication `x*100` may already be binary approximations.
- `Math.round(double)` returns `long` and rounds ties toward positive infinity: `Math.round(1.5)` is 2, but `Math.round(-1.5)` is -1.
- For extremely large values or NaN/infinity, converting to `long` has specific clamping behaviors.
- `twoPlaces` is still a `double`; binary representation does not guarantee exact multiples of 0.01.
- If you place this trick at **every intermediate step**, you discard even more information.

```java
System.out.println(Math.round(1.5));  // 2
System.out.println(Math.round(-1.5)); // -1
```

Whereas `new BigDecimal("-1.5").setScale(0, RoundingMode.HALF_UP)` gives -2. The two APIs do not share the same rule at negative midpoints. Business rules must state the exact rounding mode rather than using "round" as a vague concept.

If you only need to print, `String.format` returns a string without changing the variable. If you need exact decimals for further computation, choose an appropriate decimal model from the start.

## 8. Deferring Rounding Alone Does Not Guarantee Numerical Stability

Even without adding decimal rounding, `double` still carries risks: loss of significant digits, accumulated error, and order-dependent results.

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double first = (a + b) + c; // 1.0
double second = a + (b + c); // 0.0
```

Real-number math gives the same result 1, yet `b + c` loses the contribution of 1 around magnitude 1e16 because `double` precision is insufficient. This is **the non-associativity of floating-point arithmetic**.

When requirements are strict, consider numerically stable algorithms, summation order, error compensation methods, `BigDecimal`, or another suitable type. **Avoiding premature rounding** is just one principle for preserving information, not a substitute for numerical algorithm design.

## 9. Complete Java 17+ Program

Save the content below as **`RoundingBoundaryDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class RoundingBoundaryDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("0.015");
        BigDecimal each = amount.setScale(2, RoundingMode.HALF_UP);
        System.out.println("roundEach=" + each.add(each).toPlainString());
        System.out.println("roundTotal=" +
                amount.add(amount).setScale(2, RoundingMode.HALF_UP));

        BigDecimal unit = new BigDecimal("0.335");
        BigDecimal quantity = BigDecimal.valueOf(3);
        System.out.println("unitRounded=" +
                unit.setScale(2, RoundingMode.HALF_UP)
                        .multiply(quantity).toPlainString());
        System.out.println("lineRounded=" +
                unit.multiply(quantity)
                        .setScale(2, RoundingMode.HALF_UP).toPlainString());

        System.out.println("halfUpTie=" +
                new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP));
        System.out.println("halfEvenTie=" +
                new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("halfEvenOther=" +
                new BigDecimal("2.355").setScale(2, RoundingMode.HALF_EVEN));

        try {
            new BigDecimal("2.345").setScale(2, RoundingMode.UNNECESSARY);
            System.out.println("unnecessary=missed");
        } catch (ArithmeticException ex) {
            System.out.println("unnecessary=detected");
        }

        try {
            BigDecimal.ONE.divide(BigDecimal.valueOf(3));
            System.out.println("divideExact=unexpected");
        } catch (ArithmeticException ex) {
            System.out.println("divideExact=requiresRounding");
        }

        BigDecimal third = BigDecimal.ONE.divide(
                BigDecimal.valueOf(3), 6, RoundingMode.HALF_UP);
        System.out.println("third=" + third.toPlainString());
        System.out.println("thirdTimesThree=" +
                third.multiply(BigDecimal.valueOf(3)).toPlainString());
        System.out.println("thirdAtBoundary=" +
                third.multiply(BigDecimal.valueOf(3))
                        .setScale(2, RoundingMode.HALF_UP).toPlainString());

        double binarySum = 0.1 + 0.2;
        System.out.println("binarySum=" + binarySum);
        System.out.println("display=" +
                String.format(Locale.US, "%.2f", binarySum));
        System.out.println("rawValue=" + binarySum);

        System.out.println("mathRoundPositive=" + Math.round(1.5));
        System.out.println("mathRoundNegative=" + Math.round(-1.5));

        double first = (1e16 + -1e16) + 1.0;
        double second = 1e16 + (-1e16 + 1.0);
        System.out.println("associationFirst=" + first);
        System.out.println("associationSecond=" + second);
    }
}
```

Use JDK 17 or newer:

```bash
javac RoundingBoundaryDemo.java
java RoundingBoundaryDemo
```

Expected output:

```text
roundEach=0.04
roundTotal=0.03
unitRounded=1.02
lineRounded=1.01
halfUpTie=2.35
halfEvenTie=2.34
halfEvenOther=2.36
unnecessary=detected
divideExact=requiresRounding
third=0.333333
thirdTimesThree=0.999999
thirdAtBoundary=1.00
binarySum=0.30000000000000004
display=0.30
rawValue=0.30000000000000004
mathRoundPositive=2
mathRoundNegative=-1
associationFirst=1.0
associationSecond=0.0
```

`roundEach` and `roundTotal` produce different results despite identical scale/mode rules. The two unit-price examples demonstrate that boundary choice is critical. `display=0.30` does not alter `rawValue`, and the two association lines serve as an independent example of floating-point algorithmic error.

## 10. How to Specify a Rounding Contract for an Application

A good specification should answer:

| Question | Information to specify |
| --- | --- |
| Are inputs exact decimals or approximate measurements? | Decimal strings, smallest integer units, measurement float/double |
| What are the units and value domain? | Currency, cents, percentages, physical units, valid ranges |
| Which values are **settled**? | Unit price, each line, each tax item, invoice total, payment amount |
| Where are the rounding boundaries? | After each item, after total, on result return, or on display |
| Which scale and mode are used? | `scale=2`, `HALF_UP`, or another rule |
| Must the total preserve the sum of settled items? | Remainder addition/distribution method |
| How is non-terminating decimal division handled? | Working precision, rounding mode, and error policy |
| Which values are stored for reconciliation? | Settlement records and (if needed) original values for auditing |

A typical flow is: **validate data → compute with appropriate precision → round only at meaningful boundaries → store settled values → format for display**. Subsequent computations must use the settled values if the contract requires it. Never accidentally parse rounded display data and feed it into new calculations.

## 11. Common Mistakes and Checklist

| Misconception | Correct understanding |
| --- | --- |
| "Rounding after every operation makes results more accurate." | Can alter totals and lose intermediate data. |
| "Rounding once at the end is always right." | False if individual lines or transactions have independent settlement obligations. |
| "If `Math.round` isn't called, `double` is never rounded." | False; finite binary floating-point numbers inherently undergo roundoff. |
| "`String.format("%.2f", x)` modifies `x`." | False; it returns a formatted string. |
| "`setScale(2)` is the same as `MathContext(2)`." | False; scale differs from total significant digits. |
| "`BigDecimal` divides 1/3 exactly on its own." | False; requires precision/rounding or exception handling. |
| "Using `new BigDecimal(0.1)` gets exact decimal 0.1." | False; it takes the binary approximation already stored in `double`. |
| "`Math.round` always matches `HALF_UP`." | False, especially for negative ties. |
| "Three shares of `3.33` add up to `10.00`." | False; the sum is `9.99`; remainder must be allocated per contract. |
| "Avoiding early rounding guarantees error-free calculation." | False; you must still consider algorithms and data type precision. |

Before writing a new rounding operation, ask yourself: **(1)** what requirement mandates it, **(2)** which value must be settled, **(3)** which scale/mode applies, **(4)** does the total use raw values or settled items, **(5)** must totals/reconciliation be preserved, and **(6)** is this a calculation or merely display formatting?

**Conclusion:** Do not round after every operation just to make numbers look "tidy." Round **at the exact specified boundaries**, using **the appropriate numeric type and rounding mode**. When needed, retain internal precision to avoid information loss; when the contract requires settling individual items, enforce it and preserve those exact settled items.
