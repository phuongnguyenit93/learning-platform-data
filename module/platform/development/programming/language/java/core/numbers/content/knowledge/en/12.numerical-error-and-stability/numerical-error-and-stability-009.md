# Choosing `double` vs. `BigDecimal` Based on the Data Model in Java

## 1. The Right Question Is Not "Which Type Is More Accurate?"

When designing a Java program, choosing between `double` and `BigDecimal` must start from **the meaning and rules of the data**, not merely which type stores more digits.

- **`double`** is a 64-bit binary floating-point primitive (*IEEE 754 binary64*). It fits measurements, simulations, statistics, and numerical algorithms where **approximate error is acceptable and controlled**.
- **`BigDecimal`** is a decimal number class with an arbitrary-magnitude integer significand and a decimal *scale*. It fits data and calculation rules requiring **exact decimal representation**, especially when rounding policies carry business significance.
- **`long` (or `int`) integers storing the smallest unit** is a useful third option, such as storing money in cents when the unit and precision are always fixed, provided range and overflow are controlled.

There is no rule that "every monetary calculation must use `BigDecimal`" or "`double` is always wrong." What matters is: **is the data source exact, which operations are performed, which results must be preserved, and when must rounding occur?**

## 2. Quick Decision Table

| Scenario | Usually reasonable choice | Reason |
|---|---|---|
| Sensor temperatures, positions, measurements | `double` | Measurements inherently have error; performance and math APIs are convenient |
| Physics simulations, statistics, trigonometric functions | `double` | Numerical libraries and algorithms typically use binary floating point |
| List price `"19.90"` needing exact decimal preservation | `BigDecimal` from string | `19.90` is a decimal value with business significance |
| Taxes, discounts, exchange rates with rounding rules | `BigDecimal` with `RoundingMode` policy | Controls scale, precision, and rounding boundaries |
| Balances with strictly two decimal places, stored in cents | `long` if range suffices | Exact integer addition/subtraction, though units must be managed |
| Very large integer quantities exceeding `long` | `BigInteger` | No fractional part needed and not limited to 64 bits |
| Decimal-stored prices needing multiplication by quantity | `BigDecimal` multiplied by integer quantity | Preserves exact business decimal constants |
| JSON/API data specifying an arbitrary decimal | `BigDecimal` if decimal must be preserved | Avoids rounding through `double` before parsing |
| A specialized algorithm specified in IEEE 754 | `double`/`float` per specification | Needs exact floating-point semantics and compatibility |
| Measured values put into a report with two digits | `double` may still be suitable | Two-digit **display formatting** does not imply needing exact decimal storage |

This table is only a design guide. For instance, a financial application may still use `double` in statistical risk models; conversely, a scientific system may still use `BigDecimal` if a special measurement requires decimal arithmetic at a specified precision.

## 3. Why Doesn't `double` Represent Every Decimal Number Accurately?

`double` stores values in finite binary form. Many decimal fractions, such as \(0.1 = 1/10\), **have no finite binary representation**. The JVM stores a binary64 number close to 0.1, rather than the exact mathematical fraction 1/10.

Familiar example:

```java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
```

The `0.3` written in source code is also rounded to a binary64 pattern, yet that pattern does not equal the binary64 result of adding `0.1 + 0.2`. This is expected floating-point arithmetic behavior, **not a Java bug**.

A `double` has **53 bits of significand precision** (including the implicit bit) — roughly 15–17 significant decimal digits depending on the specific number. That does not mean every 15-digit decimal number is stored accurately. Precision in digits and the ability to represent a decimal fraction exactly are **two different issues**.

### When Is This Error Acceptable?

Suppose a sensor provides a temperature around 23.7°C with an instrument error of ±0.1°C. A discrepancy of a few units in the last binary place of `double` is typically far smaller than the measurement error; calibration and how measurements are aggregated matter far more.

Meanwhile, if a contract requires storing **exactly 0.10 currency units** and reconciling down to the cent, using `double` and directly comparing decimal values can cause trouble. An exact decimal model makes representing and enforcing business rules easier to explain.

## 4. How Does `BigDecimal` Represent Numbers?

A finite `BigDecimal` can be understood via the formula:

\[
\text{value}=\text{unscaledValue}\times 10^{-\text{scale}}
\]

For example, `new BigDecimal("12.3400")` has:

- Mathematical value **12.3400**, equal to 12.34.
- `unscaledValue()` equal to **123400**.
- `scale()` equal to **4**.
- `precision()` equal to **6** (the number of digits in the unscaled integer significand, not the number of digits after the decimal point).

With `BigDecimal`, the decimal string `"0.1"` is represented **accurately**. Adding `"0.2"` yields the exact value **0.3**, not a binary64 approximation.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b); // 0.3, exact representation
```

This is an illustrative snippet placed **inside a Java method**, not a standalone program. `BigDecimal` is an *immutable* class: `add` returns an object representing the result without modifying `a` or `b`.

**Important limitation:** `BigDecimal` does not produce "infinite-precision real numbers" for every operation. It accurately represents finite decimal numbers supplied accurately; division such as \(1/3\) yields an infinite decimal and requires a rounding rule or an allowed digit count.

## 5. The Classic Mistake: `new BigDecimal(0.1)`

The following two constructions are **not equivalent**:

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromBinaryDouble = new BigDecimal(0.1);
```

- `"0.1"` is an exact decimal string, so the `String` constructor produces the exact value 0.1.
- `0.1` without a suffix is a `double` literal, already rounded to a binary64 value close to 0.1. The `BigDecimal(double)` constructor records **that exact binary64 value** in decimal form, so it does not equal mathematical 0.1.

Therefore, when you **know a business constant in decimal form**, you should use:

```java
BigDecimal price = new BigDecimal("19.90");
BigDecimal taxRate = new BigDecimal("0.075");
```

Or in certain cases:

```java
BigDecimal decimal = BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` uses the canonical decimal representation from `Double.toString(double)`. For the literal 0.1, the result has the expected decimal value `0.1`; however, **it cannot recover lost original digits if a `double` calculation already happened beforehand**.

For example, `BigDecimal.valueOf(0.1 + 0.2)` yields the decimal value **0.30000000000000004**, without automatically fixing it to 0.3. For monetary data read from forms, files, or APIs, parse directly from the **original decimal string**, avoiding a detour through `double` before converting to `BigDecimal`.

## 6. Java 17+ Program: Comparing on Real Data

Create the file `DoubleVsBigDecimalDemo.java`:

```java
import java.math.BigDecimal;

public class DoubleVsBigDecimalDemo {
    public static void main(String[] args) {
        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));

        System.out.println("double: " + binarySum);
        System.out.println("double == 0.3: " + (binarySum == 0.3));
        System.out.println("decimal: " + decimalSum.toPlainString());

        BigDecimal direct = new BigDecimal(0.1);
        BigDecimal fromText = new BigDecimal("0.1");

        System.out.println("double constructor equals text: "
                + direct.equals(fromText));
        System.out.println("valueOf(0.1): "
                + BigDecimal.valueOf(0.1).toPlainString());
        System.out.println("valueOf(computed double): "
                + BigDecimal.valueOf(binarySum).toPlainString());
        System.out.println("double sum finite: "
                + Double.isFinite(binarySum));
    }
}
```

Compile and run:

```bash
javac DoubleVsBigDecimalDemo.java
java DoubleVsBigDecimalDemo
```

Output:

```text
double: 0.30000000000000004
double == 0.3: false
decimal: 0.3
double constructor equals text: false
valueOf(0.1): 0.1
valueOf(computed double): 0.30000000000000004
double sum finite: true
```

The final line is a very memorable point: **`Double.isFinite` returning true does not mean the decimal value is exact**. It only checks that the number is neither NaN nor ±Infinity.

## 7. `BigDecimal` Arithmetic: Do Not Use `+`, `-`, `*`, `/` Directly

In Java, `BigDecimal` is an object and does not support operator overloading such as `+` or `*` for two `BigDecimal`s. Use the methods:

| Operation | API | Notes |
|---|---|---|
| Add | `a.add(b)` | Exact decimal result if no `MathContext` is passed |
| Subtract | `a.subtract(b)` | Same |
| Multiply | `a.multiply(b)` | Exact decimal product when precision is unbounded |
| Divide | `a.divide(b)` | May throw `ArithmeticException` if decimal quotient is non-terminating |
| Divide with rounding | `a.divide(b, scale, mode)` | Explicitly specifies decimal digits and rounding rule |
| Set decimal places | `a.setScale(scale, mode)` | May require rounding |
| Compare values | `a.compareTo(b)` | Compares numeric values, ignoring scale differences |
| Exact conversion to `long` | `a.longValueExact()` | Throws if fractional part exists or out of `long` range |

Example:

```java
BigDecimal subtotal = new BigDecimal("19.90")
        .multiply(BigDecimal.valueOf(3)); // 59.70

BigDecimal discount = subtotal
        .multiply(new BigDecimal("0.075")) // 4.47750
        .setScale(2, java.math.RoundingMode.HALF_UP); // 4.48

BigDecimal total = subtotal.subtract(discount); // 55.22
```

You must decide **when rounding is allowed**: rounding each invoice line, totaling before rounding, or rounding after tax calculation can yield different results. There is no single generic formula that replaces the computation policy specified by a contract or regulation.

## 8. `BigDecimal` Division and Choosing `RoundingMode`

Some decimal quotients have no finite representation. For example:

\[
\frac{1}{3} = 0.333333333\ldots
\]

If you call:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);
// BigDecimal invalid = one.divide(three);
```

The commented line will **throw `ArithmeticException` at runtime** due to a non-terminating decimal with no rounding rule. Not every `BigDecimal` division runs forever trying to find "infinite precision."

You must choose the number of digits after the decimal point or a `MathContext`:

```java
BigDecimal quotient = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        4,
        java.math.RoundingMode.HALF_UP
); // 0.3333
```

### Scale vs. Precision

- **Scale**: number of decimal places of the represented value (can be negative), e.g., `12.3400` has scale 4.
- **Precision**: number of significant digits of the unscaled integer significand, e.g., `12.3400` has precision 6.
- **`MathContext(5, RoundingMode.HALF_EVEN)`**: limits to **5 significant digits**, **not 5 digits after the decimal point**.

Thus a `MathContext` rule can suit calculations with relative precision, while `setScale(2, ...)` is usually clearer when needing monetary amounts with two decimal places.

### `HALF_UP` and `HALF_EVEN`

At an exact midpoint:

- `HALF_UP` rounds away from 0.
- `HALF_EVEN` rounds to the nearest even digit at the retained position (also called *banker's rounding*).

**Exact** decimal examples:

```java
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP);   // 2.35
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN); // 2.34
new BigDecimal("2.355").setScale(2, RoundingMode.HALF_EVEN); // 2.36
```

These three lines are illustrative expressions; to compile, place them in a method importing `java.math.BigDecimal` and `java.math.RoundingMode`, and assign/use the results. **Do not pick a mode by intuition**: the rounding rule must match product requirements and applicable regulations.

## 9. `equals` Is Not the Same as `compareTo` for `BigDecimal`

This is a common API trap:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));  // false
System.out.println(a.compareTo(b)); // 0
```

The two values are **mathematically equal**, yet differ in **scale** (1 vs. 2). `BigDecimal.equals` checks both unscaled value and scale, whereas `compareTo` checks numeric value ordering.

When checking whether **two monetary amounts have the same value**, you should usually use:

```java
boolean sameAmount = a.compareTo(b) == 0;
```

When matching **both format/scale** per a data contract, `equals` may be the intended choice. This affects `HashSet<BigDecimal>` or `HashMap<BigDecimal, ...>`: they use `equals`/`hashCode`, so `2.0` and `2.00` are two distinct keys. A `TreeSet<BigDecimal>` ordered by natural comparison treats those two values as equivalent in ordering.

If scale normalization is needed, `setScale` can be used with an appropriate rule. `stripTrailingZeros()` also changes scale; some values like `1000.00` can receive a negative scale after stripping redundant zeros, so it is not an arbitrary formatting normalizer.

### Java 17+ Example: Scale, Compare, and Divide

Create the file `BigDecimalRulesDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalRulesDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo: " + a.compareTo(b));
        System.out.println("a scale: " + a.scale());
        System.out.println("b scale: " + b.scale());

        BigDecimal sample = new BigDecimal("12.3400");
        System.out.println("precision: " + sample.precision());
        System.out.println("scale: " + sample.scale());
        System.out.println("stripped: "
                + sample.stripTrailingZeros().toPlainString());

        try {
            System.out.println(
                    BigDecimal.ONE.divide(BigDecimal.valueOf(3)));
        } catch (ArithmeticException e) {
            System.out.println("1/3 without rounding: ArithmeticException");
        }

        System.out.println("1/3 scale 4: "
                + BigDecimal.ONE.divide(
                        BigDecimal.valueOf(3), 4, RoundingMode.HALF_UP));
        System.out.println("half up: " + new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_UP));
        System.out.println("half even: " + new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN));
    }
}
```

Run:

```bash
javac BigDecimalRulesDemo.java
java BigDecimalRulesDemo
```

Output:

```text
equals: false
compareTo: 0
a scale: 1
b scale: 2
precision: 6
scale: 4
stripped: 12.34
1/3 without rounding: ArithmeticException
1/3 scale 4: 0.3333
half up: 2.35
half even: 2.34
```

## 10. Real-World Scenario: Price, Quantity, and Discount

Suppose an invoice line has:

- Unit price **19.90**.
- Quantity **3**.
- Discount **7.5%**.
- Assumed rule: **round the discount amount to 2 decimal places using HALF_UP**.

This is a **hypothetical business rule example**, not a tax/rounding regulation applicable to every system. Calculation steps:

1. Pre-discount subtotal: 19.90 × 3 = 59.70.
2. Unrounded discount: 59.70 × 0.075 = 4.47750.
3. Rounded discount: 4.48.
4. Amount payable: 59.70 - 4.48 = 55.22.

Save `MoneyCalculationDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyCalculationDemo {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.90");
        int quantity = 3;
        BigDecimal discountRate = new BigDecimal("0.075");

        BigDecimal subtotal = unitPrice
                .multiply(BigDecimal.valueOf(quantity));

        BigDecimal discount = subtotal.multiply(discountRate)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal total = subtotal.subtract(discount)
                .setScale(2, RoundingMode.UNNECESSARY);

        long cents = total.movePointRight(2).longValueExact();

        System.out.println("subtotal: " + subtotal.toPlainString());
        System.out.println("discount: " + discount.toPlainString());
        System.out.println("total: " + total.toPlainString());
        System.out.println("cents: " + cents);
    }
}
```

Run:

```bash
javac MoneyCalculationDemo.java
java MoneyCalculationDemo
```

Output:

```text
subtotal: 59.70
discount: 4.48
total: 55.22
cents: 5522
```

`RoundingMode.UNNECESSARY` means **no rounding is allowed** at the final scale-setting step: if the total could not yet be represented in 2 decimal places without data loss, this step throws `ArithmeticException`. It is useful when asserting a data invariant at the point of persisting results.

Converting to cents at the end via `movePointRight(2).longValueExact()` requires no remaining fractional part and staying within `long` range. If a currency uses a different decimal unit magnitude, the number 2 must be replaced according to the **currency and storage contract**, rather than hardcoding it across all systems.

## 11. Third Option: Using Integers in the Smallest Unit

If all data always resides in one fixed unit, such as monetary amounts having strictly **two decimal places**, storing `long cents` is also a model that can be **strictly exact within the integer range**:

```java
long unitPriceCents = 1_990L;
int quantity = 3;
long subtotalCents = Math.multiplyExact(
        unitPriceCents, quantity); // 5970 cents
```

Advantages:

- Addition, subtraction, and equality checks are **exact integer operations** when there is no overflow.
- Does not depend on binary64 representation of 0.1.
- Stored/transmitted data has clear units when named `amountInCents` instead of `amount`.

Risks:

- When decimal discount rates, taxes, or exchange rates exist, rules for **multiplication/division and rounding** must still be defined.
- Different currencies have different decimal digit conventions; "cent" is not a universal unit for every currency.
- `long` can overflow; use `Math.addExact`/`Math.multiplyExact` or appropriate range checks.
- If the business needs variable precision or decimal numbers with multiple scales, fixed-cent storage can be too rigid.

**A sensible combination:** use `BigDecimal` to compute and round according to business policy, then convert accurately to integer units at the storage boundary if the model specifies that unit. Or use integers from the start if the system is designed entirely in smallest units.

## 12. `double` Remains a Great Choice for Scientific Computing

In many applications, using `BigDecimal` instead of `double` is not only unnecessary, it makes algorithms more complex:

- `Math.sin`, `Math.cos`, `Math.sqrt`, and many scientific APIs accept/return `double`.
- Numerical analysis, simulation, and statistical methods normally accept controlled approximate error.
- `double` has a **very wide magnitude range**, supporting subnormal numbers, ±Infinity, NaN, and IEEE 754 arithmetic rules.
- `BigDecimal` can be more resource-intensive due to object allocation and arbitrary-precision decimal arithmetic.

However, `double` does not guarantee algebraic properties like infinite-precision mathematical real numbers. For example, addition order can affect error:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

Explanation: `b + c` rounds to `-1.0e16` in `double` because 1 is too small relative to the magnitude of `b`; then `a + (b+c)` becomes 0.0. Meanwhile, `(a+b)+c` gives 1.0. Thus with `double`, you must pay attention to **numerical stability**, accumulation order, value scale, and error, not just checking NaN/Infinity.

When summing many measurements, consider a stable summation algorithm such as **Kahan summation** or an appropriate computation strategy rather than automatically switching the entire system to `BigDecimal`.

## 13. Input, JSON, Database, and API Contracts

The data type is not just a Java variable decision. Agree on **numeric semantics at every boundary**:

### Receiving Data from UI or Files

If the source has an exact decimal string, such as `"123.45"`, pass it directly into `BigDecimal`:

```java
String input = "123.45";
BigDecimal amount = new BigDecimal(input);
```

Parsing into `double` first can lose the intended decimal representation. For user input, also validate empty strings, syntax, magnitude limits, maximum scale, and `NumberFormatException` parsing errors.

### JSON and APIs

A JSON number token such as `19.90` typically **carries no metadata about units or scale policy**. Depending on the parsing library, it may pass through `double` or be read directly into `BigDecimal`. Never assume every JSON library automatically preserves decimal precision or trailing zeros.

If a financial API needs reliable communication, clearly specify which fields are:

- Decimal numbers parsed accurately.
- Integers in the smallest unit (along with currency/unit).
- Approximate measurements.
- Or decimal strings to avoid losing meaning across systems.

### Database

`DECIMAL`/`NUMERIC` columns generally fit `BigDecimal` when the database and ORM have matching precision/scale configurations; `DOUBLE`/`FLOAT` generally fit approximate values. However, details depend on the engine, driver, and actual mapping. Check **schema, precision, scale, database rounding, and ORM mapping**, not just the Java type.

A system using `BigDecimal` in code yet writing to a floating-point column can still lose precision; conversely, a decimal column with too narrow precision/scale can round or reject values.

## 14. Comparison, Equality, and Invalid Values

### With `double`

Avoid expecting `0.1 + 0.2 == 0.3`. When comparing approximate results, use an error criterion suited to the value scale and context. Simple near-equality example for finite numbers with not-too-large absolute values:

```java
static boolean approximatelyEqual(double a, double b,
                                  double tolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(tolerance) || tolerance < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= tolerance;
}
```

This is an **illustrative method**. A fixed absolute error does not fit every numeric domain; an application may need to combine relative error, ULP-based comparison, or domain-specific criteria. Moreover, subtraction can overflow to Infinity if two huge finite numbers have opposite signs, causing the check above to return false even when the threshold does not permit that difference; thus you must understand the limits of your comparison strategy.

With `double`, you must also handle **NaN, ±Infinity, and -0.0** when the input contract forbids or requires distinguishing special values.

### With `BigDecimal`

To compare mathematical value, use `compareTo`:

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");
boolean sameNumber = a.compareTo(b) == 0; // true
```

`equals` also checks scale, so it can return false. `BigDecimal` has no NaN or Infinity values in its class model; `BigDecimal.valueOf(Double.NaN)` does not turn it into a "decimal NaN" object and will fail during conversion.

This helps the decimal model avoid a class of NaN/Infinity bugs, yet you still must check for other errors such as **division by 0**, exceeding business bounds, or non-terminating decimal division.

## 15. Performance and the Cost of Precision

`double` is a 64-bit primitive, well suited to primitive array data structures, repetitive arithmetic, and many optimized computing libraries. `BigDecimal` is an immutable object that typically allocates a new result after each operation and must manage significand/scale.

In a loop of millions of operations, the difference in allocation and CPU **can be significant**, yet you cannot conclude with a universal speed number without benchmarking in the concrete application.

One way to decide:

1. Confirm what kind of precision the problem needs: **binary approximation**, **exact decimal**, or **fixed-unit integer**.
2. Use the right type first, verify results and edge cases.
3. If performance is an issue, run a real benchmark (such as JMH) on the hot path rather than optimizing by guesswork.
4. Never switch types solely for performance if doing so breaks rounding rules or corrupts business data.

In practice, **multiple numeric models can coexist in the same system**: transaction amounts in `BigDecimal`, integer aggregations in `long`, and statistical forecasts in `double`. What matters is that conversions between models are explicit and validated.

## 16. Common Design Mistakes

| Mistake | Why it is wrong/risky | How to fix |
|---|---|---|
| "`double` has 15 digits so 0.1 must be exact" | 1/10 has no finite binary representation | Recognize approximation or use decimal when needed |
| `new BigDecimal(0.1)` to represent 0.1 accurately | The argument is an already-approximated `double` | Use `new BigDecimal("0.1")` |
| Converting a corrupted `double` to `BigDecimal` to "fix" it | Previously lost digits are not recovered | Parse from decimal source if available |
| Calling `divide` for 1/3 without rounding | Infinite decimal quotient, may throw an exception | Choose scale/mode or `MathContext` |
| Using `equals` to compare `BigDecimal` values | `2.0` and `2.00` have different scales | Use `compareTo(...) == 0` when comparing values |
| Arbitrarily calling `setScale(2)` at every step | Early rounding can change final monetary amounts | Specify business rounding boundaries |
| Thinking `BigDecimal` has free infinite precision | Object/decimal arithmetic has cost, division needs policy | Choose precision and requirements properly |
| Thinking a finite `double` is an exact number | Finite only rules out NaN/Infinity | Control error, domain, and precision |
| Using smallest currency unit without recording the unit | Easy to confuse cents with main currency unit | Name clearly, store currency/scale metadata |
| Using `long` for money and forgetting overflow | Integers still have finite bounds | `Math.addExact`, `multiplyExact`, or bounds checks |
| Storing `BigDecimal` in a `DOUBLE` DB column | Target column can lose decimal precision | Use appropriate `DECIMAL/NUMERIC` mapping |
| Calling `toString` as a scale-normalization mechanism | Representation may use scientific notation and different scale | Use `toPlainString`/`setScale` per contract |
| Using decimal for all sensors to "guarantee accurate measurement" | Physical source error does not vanish on its own | Keep appropriate measurement, error, and precision model |

## 17. Self-Check Exercises

**Question 1.** Why can `double x = 0.1 + 0.2;` print `0.30000000000000004`?  
**Answer:** 0.1 and 0.2 are stored as approximate binary64 values; addition undergoes binary rounding again.

**Question 2.** For a decimal literal price `"19.90"`, how should `BigDecimal` be created?  
**Answer:** `new BigDecimal("19.90")` (or parse directly from the source decimal string).

**Question 3.** Does `BigDecimal.valueOf(0.1 + 0.2)` become exact 0.3?  
**Answer:** No. The input is already the `double` 0.30000000000000004, so the method represents that value in decimal.

**Question 4.** Why does `BigDecimal.ONE.divide(BigDecimal.valueOf(3))` throw an exception?  
**Answer:** 1/3 has a non-terminating decimal representation; without a rounding rule, an exact finite decimal result cannot be produced.

**Question 5.** What do `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` and `compareTo` return?  
**Answer:** `equals` is false, `compareTo` returns 0; the scales differ while the mathematical values are equal.

**Question 6.** Two values are used for a physics simulation whose measurement error is many times larger than binary64 error: which type should be preferred?  
**Answer:** Usually `double` if algorithms/APIs fit, while controlling numerical stability and special values.

**Question 7.** If storing 59.70 as cents in `long`, how is it represented?  
**Answer:** 5970 cents, assuming the currency has exactly 100 cents per major unit and `long` range suffices.

**Question 8.** What are the `scale` and `precision` of `new BigDecimal("12.3400")`?  
**Answer:** Scale 4, precision 6. Stripping trailing zeros can change scale.

**Question 9.** When does `HALF_UP` differ from `HALF_EVEN`?  
**Answer:** At an exact midpoint, e.g., rounding 2.345 to two decimal places: `HALF_UP` gives 2.35, `HALF_EVEN` gives 2.34.

**Question 10.** Should every multiplication/discount be rounded immediately?  
**Answer:** Only when business policy requires it; rounding timing affects the result and must be specified and tested.

**Question 11.** Does storing `BigDecimal` into a `DOUBLE` database column guarantee decimal accuracy?  
**Answer:** No; you must verify column type, precision/scale, and actual mapping.

**Question 12.** If `double` is used for scientific computing, what should you care about besides `isFinite`?  
**Answer:** Representation error, error accumulation, numerical stability of the algorithm, data range, and approximate comparison criteria.

## 18. Type Selection Process and References

**Step 1 — identify source nature:** measurement, integer count, or decimal with legal/business meaning? Must the exact input decimal string be preserved?

**Step 2 — identify invariants to preserve:** exact mathematical value, allowable error magnitude, decimal digit count, significant digit count, or storage unit.

**Step 3 — identify operations and rounding rules:** summation, proportional division, taxes, percentages, unit conversion; at which step to round, under which mode, and whether overflow/NaN is acceptable?

**Step 4 — choose the model:**
- **`double`** if the problem is binary approximate computation with controlled error.
- **`BigDecimal`** if exact-policy decimal representation and computation are required.
- **`long`/`BigInteger`** if the data is integers or smallest units and exact integer arithmetic is needed.

**Step 5 — test at boundaries:** decimals with trailing zeros, 0.1 + 0.2, negative/positive, very large values, non-terminating division, multi-step rounding, type conversion, serialization, database, and overflow.

**Takeaway:** Do not choose `BigDecimal` solely because `double` has error; choose it when **the data requires exact decimal representation and controlled rounding**. Do not choose `double` for money merely for syntactic convenience if the contract requires preserving decimals. And if the data truly consists of integers in a fixed unit, `long` with overflow checking may be the simplest model.

Official references:
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html)
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)
- [Java SE 17 — Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)
