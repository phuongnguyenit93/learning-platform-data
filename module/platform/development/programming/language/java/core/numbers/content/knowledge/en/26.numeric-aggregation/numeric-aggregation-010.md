# Do Not Mix Inconsistent Units, Precision, or Scale

## 1. Problem: Syntactically Valid Math Can Be Semantically Wrong

In Java, numeric types like `BigDecimal` know how to add, subtract, multiply, and divide, yet **do not automatically know** whether numbers represent meters, centimeters, USD, seconds, or percentages. Nor do they know how many significant digits or decimal places the business contract requires, or when rounding should occur.

Three common sources of discrepancy:

1. **Inconsistent units:** adding `1.20 m + 30 cm` as `1.20 + 30 = 31.20`. The right calculation must convert `30 cm = 0.30 m`, giving `1.50 m`.
2. **Inconsistent precision:** one calculation retains full result precision, while the next uses `MathContext.DECIMAL32` keeping at most seven significant digits. Rounding error from one step can propagate to the final result.
3. **Inconsistent scale:** `1.2`, `1.20`, and `1.200` are equal in mathematical value yet have different scales; `BigDecimal.equals`, storage, or display may treat them differently.

Guiding principle: **verify quantities and units, unify the computation policy, then normalize the result at the appropriate boundary**. Never use rounding or casting merely to hide source data with mismatched units.

## 2. Do Not Mix Units Before Aggregating

A bare number `42` does not specify "42 meters", "42 seconds", "42 USD", or "42%". For addition or subtraction to make sense, operands must share the same **quantity kind** and be converted to **compatible units** beforehand.

| Input | Wrong calculation | Correct conversion |
| --- | --- | --- |
| `1.20 m` and `30 cm` | `1.20 + 30 = 31.20` | `1.20 m + 0.30 m = 1.50 m` |
| `2 kg` and `500 g` | `2 + 500 = 502` | `2 kg + 0.5 kg = 2.5 kg` |
| `2 minutes` and `30 seconds` | `2 + 30 = 32` | `120 s + 30 s = 150 s` |
| `15%` and ratio `0.10` | `15 + 0.10 = 15.10` | If sharing the same base: `0.15 + 0.10 = 0.25 = 25%` |
| `10 USD` and `10 EUR` | `20` with an arbitrary currency unit | Adding requires converting at a chosen exchange rate, timestamp, and rounding rule |

The percentage example is valid only when sharing the same denominator and when summing ratios is genuinely meaningful. A 15% rate on group A and 10% on group B usually cannot be added directly to get 25% of all customers; you must examine group sizes, their relationship, and the denominator.

Not every unit conversion is multiplying by a constant. Absolute temperature from Celsius to Kelvin has a `+273.15` offset; temperature differences follow different semantics. Price per kilogram multiplied by mass produces money and changes **dimension**. Do not write a single generic `convert(value)` function for all data types while ignoring these semantics.

### 2.1. Exact Conversion with BigDecimal

For decimal-based units, you can use `BigDecimal` without going through `double`:

~~~java
import java.math.BigDecimal;

BigDecimal meters = new BigDecimal("1.20");
BigDecimal centimeters = new BigDecimal("30");

BigDecimal centimetersAsMeters = centimeters.movePointLeft(2);
BigDecimal totalMeters = meters.add(centimetersAsMeters);
// Exact value: 1.50 meters
~~~

`movePointLeft(2)` shifts the decimal point two places left, meaning division by 100. It fits centimeters → meters, not every unit pair in general. When a conversion factor or division creates a non-terminating decimal, precision/scale and rounding-mode policies must be defined.

### 2.2. Encode Units in the Data Type

If an API accepts `BigDecimal left, BigDecimal right`, callers can pass any two quantities. One safeguard is wrapping values with their unit: `record Length(BigDecimal amount, LengthUnit unit)`.

Then a length-adding API can convert every input to meters before adding. For money, `Money(amount, currency)` can reject adding USD and EUR. This turns a silent bug into a detectable error.

At JSON, database, or file boundaries, units must be transmitted or formally specified. For instance, a `value` column sometimes holding meters and sometimes centimeters without a unit field makes accurate aggregation nearly impossible.

## 3. Distinguishing Precision and Scale

For `BigDecimal`, a value is represented as:

`value = unscaledValue × 10^(-scale)`.

- **`precision()`:** number of digits in the unscaled integer representation of `BigDecimal`, often called the significant digits **of the representation**.
- **`scale()`:** exponent scaling by powers of 10; in ordinary decimal notation, the number of digits after the decimal point.
- **`MathContext` precision:** limit on the **total number of significant digits in the result** when an operation applies the context.
- **Rounding mode:** rule for handling dropped digits when rounding is required.

| Input string | `precision()` | `scale()` | Notes |
| --- | ---: | ---: | --- |
| `"1.2"` | 2 | 1 | Two digits |
| `"1.20"` | 3 | 2 | Numerically equal to `1.2`, different representation |
| `"1.200"` | 4 | 3 | Extra trailing zero |
| `"123.4500"` | 7 | 4 | Two trailing zeros in representation |
| `"0.00120"` | 3 | 5 | Leading zeros do not increase precision |
| `"1E+3"` | 1 | -3 | Scale can be negative; value is 1000 |

`new MathContext(2, RoundingMode.HALF_EVEN)` limits to two significant digits. `setScale(2, RoundingMode.HALF_EVEN)` sets two digits after the decimal point. The two operations **are not equivalent**.

Do not confuse measurement precision with `BigDecimal.precision()`. A meter reporting `1.200 m` may imply millimeter resolution, yet `BigDecimal` itself has no knowledge of uncertainty, confidence intervals, or measuring instruments. If the problem needs measurement uncertainty or significant-figure conventions, store metadata explicitly.

## 4. Different Scales Can Cause Discrepancies Despite Equal Numeric Values

### 4.1. `equals` Is Not the Same as `compareTo`

~~~java
BigDecimal x = new BigDecimal("1.20");
BigDecimal y = new BigDecimal("1.2");

boolean sameNumericValue = x.compareTo(y) == 0; // true
boolean sameRepresentation = x.equals(y);       // false
~~~

`compareTo` compares mathematical value, whereas `equals` checks both value and scale. This affects using `BigDecimal` as a `HashMap` key or `HashSet` element: `1.2` and `1.20` can be stored as two distinct keys. Do not convert to `double` to "fix" comparisons, as that can lose precision.

### 4.2. Exact Addition Does Not Normalize Scale Automatically

~~~java
BigDecimal first = new BigDecimal("1.20");   // scale 2
BigDecimal second = new BigDecimal("0.300"); // scale 3

BigDecimal sum = first.add(second);
// sum.toPlainString(): "1.500"
// sum.precision(): 4
// sum.scale(): 3
~~~

For addition/subtraction without `MathContext`, the preferred scale is the larger scale of the two operands. Mathematically, `1.500` and `1.50` are equal; in a JSON contract or fixed two-decimal display rule, they are distinct representations.

For multiplication without context, the preferred scale is typically the **sum of scales** of the two operands; for exact division, a finite decimal representation may not even exist, such as `1/3`. You cannot apply an identical scale rule across all arithmetic operations.

### 4.3. Controlled Normalization with `setScale`

~~~java
BigDecimal total = new BigDecimal("1.500");
BigDecimal normalized = total.setScale(2, RoundingMode.UNNECESSARY);
// 1.50: no loss of mathematical value
~~~

`UNNECESSARY` requires that rounding drops no non-zero digits. Removing an extra trailing `0` from `1.500` is exact, so it succeeds. Conversely:

~~~java
new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: cannot reduce scale without losing value
~~~

When business rules **permit rounding**, choose a mode:

~~~java
new BigDecimal("1.005").setScale(2, RoundingMode.HALF_UP);   // 1.01
new BigDecimal("1.005").setScale(2, RoundingMode.HALF_EVEN); // 1.00
~~~

`HALF_UP` rounds away from zero at midpoints. `HALF_EVEN` rounds to the even last digit at midpoints. Neither automatically fits every billing or statistical regulation. When increasing scale, `setScale` normally pads trailing zeros without changing numeric value.

`stripTrailingZeros()` can remove trailing zeros, yet it **changes scale** and can produce scientific notation or negative scale—for example, 1000 can become `1E+3`. Do not call it mechanically when a schema requires a fixed scale.

## 5. Precision Must Be Consistent with Computation Policy

### 5.1. MathContext Only Affects Operations That Use It

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

MathContext mc = new MathContext(7, RoundingMode.HALF_EVEN);
BigDecimal a = new BigDecimal("123456.789");
BigDecimal b = new BigDecimal("0.0012345");

BigDecimal exact = a.add(b);
BigDecimal bounded = a.add(b, mc);
~~~

`exact` preserves the exact sum, while `bounded` rounds to **7 significant digits**. Declaring `mc` does not automatically affect subsequent operations; you must pass the context to each operation that should be bounded.

| Context | Max precision | Rounding mode |
| --- | ---: | --- |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` |
| `MathContext.UNLIMITED` | Unlimited (precision value is 0) | Stores `HALF_UP`; applies no precision-limit rounding |

`UNLIMITED` does not give `1/3` a finite representation: exact division without an appropriate scale/mode can still throw `ArithmeticException`.

If layer A uses `DECIMAL32` and layer B uses `DECIMAL128` or no context, results can become inconsistent. Establish a **single arithmetic policy per quantity**, rather than picking different contexts ad hoc in each method.

### 5.2. Timing of Rounding Changes the Result

Consider:

~~~java
BigDecimal a = new BigDecimal("0.005");
BigDecimal b = new BigDecimal("0.005");

BigDecimal roundEach = a.setScale(2, RoundingMode.HALF_UP)
        .add(b.setScale(2, RoundingMode.HALF_UP)); // 0.02

BigDecimal roundSum = a.add(b)
        .setScale(2, RoundingMode.HALF_UP);       // 0.01
~~~

When rounding each part, `0.005` becomes `0.01` and the sum equals `0.02`. When summing exactly to `0.010` and then rounding, the result is `0.01`. Both use the same rounding mode and target scale yet yield different answers.

For invoices, fees, taxes, or reports, regulations may require rounding per line item or on the final total. Therefore, the policy must state clearly **which values are rounded and when**. No "always round at the end" rule holds across every business domain.

### 5.3. Avoid Precision Loss from double Inputs

~~~java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromBinaryDouble = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` receives a pre-approximated binary `double` value, leading to unexpectedly long decimal digits. `new BigDecimal("0.1")` captures the exact specified decimal value. `BigDecimal.valueOf(0.1)` is generally safer to use than the `double` constructor, though it cannot accurately restore information already lost in earlier floating-point calculations.

If units or exchange rates are defined as exact decimals, use decimal strings or validated decimal data. When measurements natively arrive as `float`/`double` from sensors, evaluate actual sensor error rather than assuming converting to `BigDecimal` fixes measurement error.

## 6. Complete Java 17+ Program

The program below demonstrates both an **intentionally wrong** addition lacking unit conversion and the proper handling. It also checks precision/scale, rounding modes, and rejecting addition of two different currencies.

Create `UnitPrecisionScaleDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class UnitPrecisionScaleDemo {
    enum LengthUnit {
        METER, CENTIMETER
    }

    record Length(BigDecimal amount, LengthUnit unit) {
        public Length {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(unit, "unit");
        }

        BigDecimal inMeters() {
            return switch (unit) {
                case METER -> amount;
                case CENTIMETER -> amount.movePointLeft(2);
            };
        }
    }

    enum CurrencyCode {
        USD, EUR
    }

    record Money(BigDecimal amount, CurrencyCode currency) {
        public Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }

        Money add(Money other) {
            if (currency != other.currency) {
                throw new IllegalArgumentException("Currency mismatch");
            }
            return new Money(amount.add(other.amount), currency);
        }
    }

    public static void main(String[] args) {
        Length a = new Length(new BigDecimal("1.20"), LengthUnit.METER);
        Length b = new Length(new BigDecimal("30"), LengthUnit.CENTIMETER);

        System.out.println("raw lengths (WRONG): "
                + a.amount().add(b.amount()));
        System.out.println("sum normalized: "
                + a.inMeters().add(b.inMeters())
                        .setScale(2, RoundingMode.UNNECESSARY)
                        .toPlainString()
                + " m");

        BigDecimal p = new BigDecimal("1.20");
        BigDecimal q = new BigDecimal("0.300");
        BigDecimal sum = p.add(q);

        System.out.println("raw sum: " + sum.toPlainString()
                + " (precision=" + sum.precision()
                + ", scale=" + sum.scale() + ")");
        System.out.println("display scale: "
                + sum.setScale(2, RoundingMode.UNNECESSARY)
                        .toPlainString());

        System.out.println("compareTo equal: "
                + (new BigDecimal("1.20").compareTo(
                        new BigDecimal("1.2")) == 0));
        System.out.println("equals equal: "
                + new BigDecimal("1.20").equals(
                        new BigDecimal("1.2")));

        try {
            new BigDecimal("1.234")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY: ArithmeticException");
        }

        System.out.println("HALF_UP: "
                + new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN: "
                + new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_EVEN));

        Money usdA = new Money(new BigDecimal("1.50"), CurrencyCode.USD);
        Money usdB = new Money(new BigDecimal("2.00"), CurrencyCode.USD);

        System.out.println("same currency: "
                + usdA.add(usdB).amount().toPlainString() + " USD");

        try {
            usdA.add(new Money(new BigDecimal("2.00"), CurrencyCode.EUR));
        } catch (IllegalArgumentException ex) {
            System.out.println("mixed currency: IllegalArgumentException");
        }
    }
}
~~~

Compile and run:

~~~bash
javac UnitPrecisionScaleDemo.java
java UnitPrecisionScaleDemo
~~~

Output:

~~~text
raw lengths (WRONG): 31.20
sum normalized: 1.50 m
raw sum: 1.500 (precision=4, scale=3)
display scale: 1.50
compareTo equal: true
equals equal: false
UNNECESSARY: ArithmeticException
HALF_UP: 1.01
HALF_EVEN: 1.00
same currency: 3.50 USD
mixed currency: IllegalArgumentException
~~~

`raw lengths` illustrates **wrong behavior to avoid**; the code only runs because raw numbers were extracted from the records and added manually. `Length.inMeters()` is the right path to add lengths with different units. `Money.add` adds within the same currency and rejects mismatched currencies. If currency conversion is genuinely desired, build a separate conversion method with an explicit exchange rate, timestamp, and rounding rule.

`setScale(2, UNNECESSARY)` in the example confirms the meter result can be normalized to two decimal places **without losing value**. If a millimeter-level measurement like `1.234 m` appears, that normalization throws an exception; deciding whether to reject or round depends on measurement data policy.

## 7. Unifying Policies at Data Boundaries

### 7.1. On APIs and Messages

A well-defined JSON payload can carry both the decimal value and its unit:

~~~json
{
  "value": "125.50",
  "unit": "CENTIMETER"
}
~~~

A string `value` field prevents client and server from guessing binary representations when the contract requires exact decimals. The receiver validates unit name, value range, allowed resolution, and conversion to the canonical unit.

Do not rely on trailing `0` digits as sufficient metadata for measurement precision. If the problem requires uncertainty, absolute/relative error, or resolution, specify those attributes separately.

### 7.2. In the Database

SQL `DECIMAL(p,s)` defines schema storage precision/scale limits, where `p` and `s` typically represent total digits and digits after the decimal point. Specific rules for range, overflow handling, and rounding vary across database engines. A `DECIMAL(12,2)` column **is not equivalent** to applying `new MathContext(12, ...)` in Java, because `MathContext` limits significant digits per operation and does not fix scale at 2.

The schema must also document or store the canonical unit and, for money, currency code. `1000` could mean 1000 grams or 1000 kilograms; setting scale 2 in SQL does not resolve that ambiguity.

### 7.3. When Displaying

Separate computation data from UI presentation. You can use `toPlainString()` when you need to avoid scientific notation from `BigDecimal.toString()`. If the display contract specifies two digits, normalize **the presentation result** rather than stripping resolution from the underlying source data.

Some systems round at the invoice line-item level, others at the final total, or both at distinct stages. Document and test the policy thoroughly. When changing it, assess the impact on historical data instead of only changing a formatter.

## 8. Design Checklist for Aggregations

| Question | Decision needed | Example |
| --- | --- | --- |
| Do both operands have the same quantity kind? | Forbid mixing dimensions | Do not add meters and kilograms |
| What is the canonical unit? | Convert before computing | Centimeters → meters, grams → kilograms |
| Which currency? | Keep currency code; exchange rates must be explicit | Do not add USD and EUR directly |
| What intermediate precision? | Choose exact or `MathContext` | Use `DECIMAL64` if acceptable |
| What result scale? | Define per data kind | Money stored with 2 digits per its own rule |
| When is rounding allowed? | Define the timing | Per line item or final total |
| Which rounding mode? | Agree explicitly | `HALF_EVEN`, `HALF_UP`, `UNNECESSARY` |
| Is data loss permitted? | Round explicitly or throw error | `setScale(2, UNNECESSARY)` if fractional loss is forbidden |
| Is measurement confidence needed? | Store error metadata separately | `1.200 m ± 0.005 m` |

When monetary amounts are needed in the smallest unit (cents), integer representation can work after **clearly defining conversion and rounding policies**. For instance, 1 USD = 100 cents, yet do not generalize that "every currency has two decimal places".

In ratio and unit calculations, also check extreme value ranges, overflow in underlying arithmetic, division remainders, and how precision is applied to avoid unintended intermediate rounding.

## 9. Common Mistakes

1. **Adding values while dropping unit labels:** arithmetic succeeds but produces the wrong quantity.
2. **Adding USD and EUR as the same currency:** conversion requires an exchange rate, effective date, and rounding policy.
3. **Treating percentages like decimal ratios:** 15% is 0.15; even after converting, add rates only when denominators/bases match.
4. **Confusing precision and scale:** `MathContext(2)` does not keep two digits after the decimal point.
5. **Using `equals` when numeric comparison is needed:** `1.20` and `1.2` match under `compareTo` but not under `equals`.
6. **Rounding step by step without a policy:** results differ from exact addition followed by final rounding.
7. **Forcing scale too early:** can lose measurement details such as millimeters inside meters.
8. **Using `new BigDecimal(double)` for decimal inputs:** can inject binary floating-point error into the pipeline.
9. **Calling `stripTrailingZeros()` to fix every scale mismatch:** can alter scale/string format unexpectedly.
10. **Applying one scale to all quantities:** money, mass, time, and ratios have distinct requirements.
11. **Believing high precision means reliable measurement:** representational precision says nothing about measurement error.
12. **Skipping unit/scale checks at API boundaries:** invalid data leaks into aggregations and is hard to trace.

## 10. Practice Exercises

**Question 1.** Given `2.50 kg` and `750 g`, what is the total in kilograms?

**Answer:** `750 g = 0.750 kg`, so the exact sum is `3.250 kg`. If the contract requires scale 2 without value loss, it can be normalized to `3.25 kg` via `setScale(2, UNNECESSARY)`.

**Question 2.** Is `new BigDecimal("12.0").equals(new BigDecimal("12.00"))` true or false? How do you compare numeric value?

**Answer:** False, because their scales differ. Use `compareTo(...) == 0` to check numeric equality.

**Question 3.** What do you get when adding `0.005 + 0.005` and rounding the sum using `HALF_UP` to two decimal places? What if you round each part first?

**Answer:** Rounding after exact addition yields `0.01`. Rounding each `0.005` to `0.01` first and then adding yields `0.02`.

**Question 4.** An API accepts lengths up to two decimal places in meters and receives `1.234 m`. Does `setScale(2, UNNECESSARY)` silently turn it into `1.23`?

**Answer:** No, it throws `ArithmeticException` because reducing scale would lose a non-zero digit. Whether to convert exactly to centimeters or round to centimeters must be explicitly specified.

**Question 5.** One value `15` represents 15%, while `0.05` represents a 5% ratio. How is the 20% total computed?

**Answer:** Convert 15% to `0.15`; when sharing the same base and rate addition is valid, the sum is `0.20` = 20%.

**Question 6.** Why does `DECIMAL128` not replace a two-decimal-place policy?

**Answer:** `DECIMAL128` limits significant digits to 34 with default `HALF_EVEN`; it does not set scale to 2. You need `setScale(2, mode)` or an appropriate formatting rule at the designated boundary.

## 11. Official Java Documentation

- [BigDecimal — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision()`, `scale()`, `setScale()`, `compareTo()`, `equals()`, `movePointLeft()`.
- [MathContext — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): significant-digit limits and rounding modes.
- [RoundingMode — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding rules.
- [Record declarations — JLS Java SE 17](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record data modeling.

**Remember:** Correct numeric aggregation starts with **same quantity kind and same unit**, followed by **operation precision policy**, and then **scale and rounding mode at defined boundaries**. `BigDecimal` enables exact decimal arithmetic, but it cannot automatically know your system's units, currencies, measurement uncertainty, or rounding rules.