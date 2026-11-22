# Do Not Infer Business Rounding Rules from Data Types Alone

A field declared as `int`, `double`, `BigDecimal`, `DECIMAL(18, 2)`, or "currency type" **cannot by itself answer** the business questions: *when to round, to what level, in which direction, and on which unit of calculation?*

A data type describes **how a value is represented and the platform's processing bounds**. Rounding rules belong to the **business contract** and must be defined independently, stated explicitly, tested, and maintained consistently throughout the entire processing flow.

For example, take the same exact decimal value `1.005`:

```java
BigDecimal amount = new BigDecimal("1.005");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 1.01
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 1.00
```

Both results come from the **same `BigDecimal` type**, the same **target scale of 2**, yet different **rounding modes**. Knowing which result is right requires checking the specific business requirements; Java cannot infer that from the type name.

## 1. Separating Three Decision Layers: Representation, Arithmetic, and Business Rules

| Decision Layer | Questions to Answer | Examples |
|---|---|---|
| **Data representation** | Which values are stored, to what accuracy, with what limits? | `BigDecimal`, `long` minor units, `DECIMAL(18, 4)` |
| **Arithmetic operations** | How are add/multiply/divide performed, and must precision be bounded? | Exact `multiply`; `divide` needs scale/mode if quotient is non-terminating |
| **Business rules** | When to round, what to round, how many digits, which direction, how to handle remainders? | Round tax per line or per invoice; apply discount before or after tax |

A decision at the representation layer **does not replace** a decision at the business layer:

- Choosing `BigDecimal` supports decimal representation and decimal arithmetic, yet **does not specify** `HALF_UP`, `HALF_EVEN`, or the target scale.
- Choosing `double` does not imply banker's rounding. It uses binary floating-point, which has representation error for many decimal fractions.
- Choosing `long` to store "minor units" can avoid some decimal issues at storage time, yet **converting from subdivided values to integer units still requires a rounding policy**.
- Declaring `DECIMAL(p, s)` in a database describes the column's precision and scale limits. Auto-conversion, rounding, or rejection of out-of-scale/out-of-range values depends on the DBMS and configuration; a `DECIMAL(18, 2)` column **cannot tell** whether a fee must be rounded per line or at period-end.

If the business rule is unstated, **never treat the number of decimal digits in the storage type as the policy**.

## 2. Precision, Scale, and RoundingMode Are Tools, Not Policies

`BigDecimal` has `unscaledValue`, `scale()`, and `precision()`; its value equals `unscaledValue × 10^(-scale)`. `setScale(2, mode)` selects two decimal places, while `MathContext(4, mode)` bounds four significant digits across the entire number. Both are programmer tools, not statements about where the system **should** round.

```java
BigDecimal value = new BigDecimal("123.456");
System.out.println(value.setScale(2, RoundingMode.HALF_UP)); // 123.46
System.out.println(value.round(new MathContext(4, RoundingMode.HALF_UP))); // 123.5
```

The article `Putting Precision, Scale, and Rounding into the Numeric Data Design Contract in Java` presents the definitions, controlling scale and precision, and division rules. Here we examine **the business policy decision** of which step applies those operations.

## 3. RoundingMode Does Not Choose When Rounding Happens

Common modes include `HALF_UP` (ties away from 0), `HALF_EVEN` (ties to even digit), `DOWN` (toward 0), `UP` (away from 0), `FLOOR` (toward negative infinity), `CEILING` (toward positive infinity); `HALF_DOWN` and `UNNECESSARY` handle ties or forbid rounding per contract.

```java
System.out.println(new BigDecimal("-1.235").setScale(2, RoundingMode.FLOOR)); // -1.24
System.out.println(new BigDecimal("-1.235").setScale(2, RoundingMode.DOWN));  // -1.23
```

The difference between these two lines reflects rounding direction for negative numbers. Yet even with the same mode and same scale, rounding **per line**, **per operation**, or **at the final total** can yield different results. This article focuses on settlement rules and operation order, rather than inferring them from Java types.

## 4. Same Mode and Same Scale, Yet Different Rounding Timing Gives Different Results

This is one of the strongest reasons why rounding rules cannot be inferred from data types.

Suppose three independent lines each have the exact value `0.335`. Under `HALF_UP` and a result at scale 2, there are at least two options:

**Option A: round each line, then sum**

```text
0.335 → 0.34
0.335 → 0.34
0.335 → 0.34
Total = 1.02
```

**Option B: sum unrounded values, then round the total**

```text
0.335 + 0.335 + 0.335 = 1.005
1.005 → 1.01
```

The difference here is **0.01** even though:

- Both use `BigDecimal`.
- Both target scale 2.
- Both use `RoundingMode.HALF_UP`.
- Neither has binary representation error like `double`.

Therefore, a complete rule must specify **the rounding unit**: per unit price, per quantity times unit price, per line tax, invoice total, per transaction, month-end, or another milestone. Stored figures should also distinguish **unrounded values** from **settled values** if business reconciliation requires it.

Similarly, the order of discounts, taxes, allocations, and adjustments can change the calculation base. Never decide the order unilaterally or assume that whatever runs first in code is the standard requirement.

## 5. Standalone Runnable Java 17+ Example

Save the file `BusinessRoundingDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

public class BusinessRoundingDemo {
    record RoundingPolicy(int scale, RoundingMode mode) {
        RoundingPolicy {
            if (scale < 0) {
                throw new IllegalArgumentException("scale must be nonnegative");
            }
            Objects.requireNonNull(mode, "mode");
        }

        BigDecimal apply(BigDecimal value) {
            return Objects.requireNonNull(value, "value")
                    .setScale(scale, mode);
        }
    }

    static BigDecimal roundEachLine(
            List<BigDecimal> lines, RoundingPolicy policy) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal line : lines) {
            total = total.add(policy.apply(line));
        }
        return total;
    }

    static BigDecimal roundOnlyTotal(
            List<BigDecimal> lines, RoundingPolicy policy) {
        BigDecimal rawTotal = BigDecimal.ZERO;
        for (BigDecimal line : lines) {
            rawTotal = rawTotal.add(line);
        }
        return policy.apply(rawTotal);
    }

    public static void main(String[] args) {
        BigDecimal midpoint = new BigDecimal("1.005");

        RoundingPolicy halfUp =
                new RoundingPolicy(2, RoundingMode.HALF_UP);
        RoundingPolicy halfEven =
                new RoundingPolicy(2, RoundingMode.HALF_EVEN);

        System.out.println("HALF_UP 1.005 = "
                + halfUp.apply(midpoint));
        System.out.println("HALF_EVEN 1.005 = "
                + halfEven.apply(midpoint));
        System.out.println("negative HALF_UP = "
                + halfUp.apply(new BigDecimal("-1.005")));

        List<BigDecimal> lines = List.of(
                new BigDecimal("0.335"),
                new BigDecimal("0.335"),
                new BigDecimal("0.335"));

        System.out.println("round each line = "
                + roundEachLine(lines, halfUp));
        System.out.println("round only total = "
                + roundOnlyTotal(lines, halfUp));

        BigDecimal base = new BigDecimal("19.99");
        BigDecimal rate = new BigDecimal("0.075");
        BigDecimal exactProduct = base.multiply(rate);
        System.out.println("unrounded product = " + exactProduct);
        System.out.println("product rounded = "
                + halfUp.apply(exactProduct));

        BigDecimal thirds = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println("1 / 3 to scale 2 = " + thirds);

        BigDecimal value = new BigDecimal("1234.567");
        System.out.println("scale 2 = " + halfUp.apply(value));
        System.out.println("precision 3 = "
                + value.round(new MathContext(3, RoundingMode.HALF_UP)));

        try {
            new BigDecimal("3.1415")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY rejected rounding");
        }
    }
}
```

Compile and run:

```bash
javac BusinessRoundingDemo.java
java BusinessRoundingDemo
```

**Stdout:**

```text
HALF_UP 1.005 = 1.01
HALF_EVEN 1.005 = 1.00
negative HALF_UP = -1.01
round each line = 1.02
round only total = 1.01
unrounded product = 1.49925
product rounded = 1.50
1 / 3 to scale 2 = 0.33
scale 2 = 1234.57
precision 3 = 1.23E+3
UNNECESSARY rejected rounding
```

The program intentionally accepts `RoundingPolicy` as an **explicit business parameter**. `RoundingPolicy` describes scale and mode, while the two functions `roundEachLine` and `roundOnlyTotal` represent **two different rounding points**. A complete policy in a real application must also document the unit, calculation stage, version, and source of the rule.

`roundOnlyTotal` uses exact `BigDecimal` addition before setting the target scale. In divisions whose decimal result is non-terminating, such as `1 / 3`, the program specifies scale and mode right at the division. You cannot ask `BigDecimal` to represent an infinite decimal expansion exactly in a value with finitely many digits.

The `MathContext(3, ...)` part shows that precision by **significant digits** differs from rounding by **decimal places**; picking the wrong tool can also change figures substantially.

## 6. Designing a Controllable and Testable Rounding Policy

If a system has multiple workflows, scattering `setScale(2, RoundingMode.HALF_UP)` across controllers, services, mappers, and report generators makes consistency hard to guarantee. Model a policy that can be invoked at the exact **business boundary**.

A clear rounding contract typically answers these questions:

1. **What is the quantity?** Money, mass, count, ratio, interest rate, loyalty points, measurement, or statistical metric?
2. **What are the unit and smallest unit?** E.g., currency unit, thousandths, grams, microseconds. Never assume "every currency has 2 decimal places."
3. **How many digits are kept?** Decimal places (scale), significant digits (precision), or rounding to a specific step like 0.05.
4. **Which rounding mode?** `HALF_UP`, `HALF_EVEN`, `FLOOR`, specific rules for negatives, or rejecting any value requiring rounding?
5. **At which step does it run?** On data ingestion, multiplying unit price, tax calculation, proportional allocation, line settlement, total calculation, or display?
6. **Can rounding happen multiple times?** Round early and feed that result to the next step, or keep full calculation precision until a single boundary?
7. **How are remainders handled?** Allocate the discrepancy to one line, an adjustment account, the first recipient, or retain it as a traceable remainder?
8. **Who/what decides?** Customer contract, applicable laws, approved business specification, or internal standard?
9. **Which policy version/effective period applies?** There must be a way to re-explain historical numbers when rules change later.
10. **Which results must be persisted?** Raw values, quantized components, rounded totals, and reconciliation data.

Not every application needs ten fields in one Java object. Yet any decision that affects outcomes **must be explicitly defined** rather than implicitly relying on data types or default behavior.

### Example Verbal Description Before Writing Code

> Each line's cost is calculated as quantity × unit price in `BigDecimal`. After multiplying, apply scale 2 and `HALF_UP` to **each line**. The line subtotal equals the sum of the rounded results. Tax (if applicable) is calculated and rounded per the separate system-published policy. The final result is stored with currency unit, policy effective timestamp, and version code.

This is only **an illustrative policy**, not a universal tax or accounting rule. Another system might require summing before rounding, retaining four internal digits, or applying discount steps differently.

## 7. Distinguishing Calculation Rounding from Display Formatting

Formatters like `DecimalFormat`, `NumberFormat`, or displaying "2 decimal places" serve the **user interface**. They do not declare official settlement rules.

For instance, the original number is `1.005`. A UI may display `1.01` per UI-configured mode while the accounting system keeps unquantized `1.005` for a subsequent total. Using the formatted string as **a new calculation value** without an explicit rule turns a presentation choice into a business choice.

Avoid two confusions:

- **Displaying 2 digits** differs from **officially storing a value rounded to 2 digits**.
- **Current scale is 2** differs from **having been rounded at the right time and with the mode required by business rules**.

Do not automatically call `setScale(2, ...)` in every mapper/serializer merely because the UI displays two digits. When data crosses an API, clarify which field is the full-precision calculation value, which is the quantized settlement number, and which is display-only.

## 8. Storage and Boundaries Between Systems

### BigDecimal, double, and Input Data

When business logic needs controllable decimal arithmetic, prefer an explicit decimal source:

```java
BigDecimal fromString = new BigDecimal("0.1");
BigDecimal fromDoubleValue = BigDecimal.valueOf(0.1);
BigDecimal binaryExact = new BigDecimal(0.1);
```

`new BigDecimal("0.1")` represents the exact decimal 0.1. `BigDecimal.valueOf(0.1)` uses the decimal representation from `Double.toString(0.1)`, so it is usually more appropriate than the `double` constructor when input is unavoidably `double`; whereas `new BigDecimal(0.1)` represents the exact binary value near 0.1 stored inside `double`, which can yield an unexpectedly long digit string.

Using `BigDecimal` does not solve **business logic** automatically. Even without binary representation error, using the wrong mode or rounding at the wrong step still produces wrong results.

### Databases and APIs

A `DECIMAL(18, 2)` column preserves two decimal places within its supported range, yet does not record **why** the data has scale 2. When writing a value with more digits, DBMSs and drivers can have differing rounding, conversion, or rejection rules. Verify the contract of the system in use, especially at read/write boundaries and during data migrations.

Design should prevent persistence from accidentally becoming an unconfirmed "business rounding event." Decide the policy before saving, and test that reads/writes do not silently alter approved values.

Examples of information useful to store or derive from records: unit, raw value, computed value, quantized value, rule code, and applied version. Storage granularity depends on audit/reconciliation requirements; no single default schema fits every system.

### Rules Are Not Necessarily "2 Decimal Places"

Some domains need integers, some use three digits, and some must round to steps such as 0.05 or 5 units. For a "nearest multiple of a step" requirement, setting `scale` alone is insufficient; you must quantize by **step**.

Mathematical formula example for value `v`, positive step `s`, and mode `m`:

```text
rounded = round(v / s, mode) × s
```

In Java, with `BigDecimal`, use a division with a specific rounding rule, typically an integer quotient rounded to scale 0:

```java
static BigDecimal roundToStep(
        BigDecimal value, BigDecimal step, RoundingMode mode) {
    if (step.signum() <= 0) {
        throw new IllegalArgumentException("step must be positive");
    }
    BigDecimal count = value.divide(step, 0, mode);
    return count.multiply(step);
}
```

This method is an **illustrative snippet** placed inside a class with the appropriate imports. With `value = 1.03`, `step = 0.05`, and `HALF_UP`, the result is `1.05`; a plain "scale 2" requirement would keep `1.03`. Thus even the rounding unit is a business rule that must be stated.

## 9. Testing Business Rules Instead of Testing Types Alone

Tests should be built from **approved policy outputs** and include boundary examples:

| Scenario | Test Data | Question to Verify |
|---|---|---|
| Midpoint | `1.005` at scale 2 | `HALF_UP` or `HALF_EVEN`? |
| Negative midpoint | `-1.005` at scale 2 | Is negative-value direction right? |
| Off-midpoint | `1.004`, `1.006` | Rounds to the right neighbor? |
| Multi-line sum | `0.335` repeated 3 times | Round per line or whole total? |
| Tax and discount | Amount × rate | Correct calculation order, base, and rounding point? |
| Proportional split | Split 1 unit across 3 targets | Is remainder handled/reconciled explicitly? |
| No data loss allowed | `3.1415` → scale 2 | Rejected as required? |
| System boundaries | JSON/DB/UI | Are official settled values preserved? |
| Rule version change | Transactions before/after effective date | Are historical results reproduced accurately? |

In `BigDecimal` tests, pay attention to the comparison goal:

- `assertEquals(new BigDecimal("1.00"), actual)` checks equality via `BigDecimal.equals()`, including **scale**. Appropriate when the contract requires a scale-2 result.
- `expected.compareTo(actual) == 0` compares only **numeric value**, ignoring scale differences. Appropriate when the contract does not mandate representation form.

Do not replace every comparison with `compareTo()==0` or every comparison with `equals()` without checking whether scale is part of the result contract.

## 10. Common Design Mistakes

1. **"It's `BigDecimal`, so rounding is already handled properly."** `BigDecimal` only provides tools; mode, scale, rounding timing, and business order still must be declared.
2. **"The DB column has scale 2, so the policy is `HALF_UP` two digits."** Column types do not establish mode, unit, or business timing.
3. **"Every monetary amount always has two digits."** Not true across all currencies, units, and calculation rules; even within one domain, calculation precision may exceed display precision.
4. **Rounding every time data crosses an application layer.** This causes double rounding, data loss, and reconciliation drift. Round only at the defined boundary.
5. **Using `MathContext(2)` to request "two decimal places."** `MathContext` limits significant digits; `setScale(2, mode)` adjusts decimal scale.
6. **Using `RoundingMode.HALF_EVEN` because it sounds like "banker's rounding."** A nickname is not enough to choose a policy. Obtain formal requirements.
7. **Failing to test negative numbers, values near midpoints, and split remainders.** These cases easily expose wrong rounding direction or calculation order.
8. **Converting to `double` in the middle of a decimal calculation.** Can introduce unintended binary error.
9. **Equating UI formatting with settled results.** A display string may not be the value to feed back into formulas.
10. **Not storing rule rationale or version.** When policy changes, it becomes hard to explain why two transactions with identical inputs produced different results.

## 11. Self-Check

**Question 1.** Knowing only that a field has type `BigDecimal`, can you infer whether it must use `HALF_UP` or `HALF_EVEN`?  
**Answer:** No. Data types do not dictate business rules.

**Question 2.** A system uses `DECIMAL(18, 2)`. Is that enough information to choose per-line rounding vs. total rounding?  
**Answer:** No. Storage scale does not specify rounding timing or scope.

**Question 3.** With three `0.335` values and `HALF_UP` at scale 2, why can the result be `1.02` or `1.01`?  
**Answer:** Rounding each line first then summing yields `1.02`; summing exactly first then rounding once yields `1.01`.

**Question 4.** What does `new BigDecimal("1.005").setScale(2, HALF_EVEN)` return?  
**Answer:** `1.00`, because on a tie it chooses the even retained digit. With `HALF_UP`, the result is `1.01`.

**Question 5.** You need to round to multiples of `0.05`. Is `setScale(2)` alone enough?  
**Answer:** No. Scale 2 only guarantees two decimal places; you need a quantization rule with step 0.05.

**Question 6.** If an application displays two decimal places in the UI while keeping unquantized internal data for subsequent calculations, should the UI string be used as calculation input?  
**Answer:** No, unless the business contract intentionally selects the quantized number. Separate calculation values, settled results, and presentation formatting.

**Question 7.** When is `RoundingMode.UNNECESSARY` useful?  
**Answer:** When you want to **detect and reject** cases where a scale change or operation would require lossy rounding.

**Key takeaway:** Data types answer *how a value is represented*; business rules answer *what is rounded, at which step, with which mode, and to which unit*. Both decisions must be designed, documented, and tested **separately yet consistently**.