# Counts, Measured Quantities, and Decimal Values with Rounding Rules

## 1. The Design Problem: All Numbers, Yet Not the Same Meaning

In Java, `int`, `long`, `double`, and `BigDecimal` can all store numeric data. However, choosing a type solely by asking "does this value have a decimal point?" often leads to business bugs. Distinguish three categories of information:

1. **Counts**: discrete quantities of items, typically non-negative integers, such as 12 students, 7 attempts, 300 visits.
2. **Measurements**: length, mass, duration, temperature, speed... always carrying a **unit**, resolution, and sometimes measurement uncertainty. For example, `2.5 m` differs from `2.5 cm`.
3. **Rounded decimal values**: money, tax, interest, rates computed with the required precision and then **normalized in scale and rounding mode according to business rules**.

They may all display as `"2"`, yet must follow different rules:

| Data | Meaning | Typically Suitable Java Representation | Invariants / Usage |
| --- | --- | --- | --- |
| 2 items in cart | Count | `int`, `long`, `BigInteger` | Non-negative, integer; avoid overflow when adding. |
| 2 meters in length | Measurement | `BigDecimal` or `double` **with unit** | Cannot add incompatible units; define precision and measurement error. |
| 2.00 USD payment | Agreed monetary value | `BigDecimal` **with currency and rounding policy** | Do not mix currencies; round at the right boundary and with the right mode. |
| 2.5 units sold by weight | Measured sales quantity | `BigDecimal` with `kg`, `liters`... | Do not force every "quantity" to be an integer count. |
| 2% rate | Ratio, not 2 units | `BigDecimal` or `double` depending on the problem | Clearly choose whether 2% is represented as `0.02` or `2`, do not mix. |

**The data model must express what the number means**, its value bounds, unit, mathematical rules, and rounding timing. The numeric type is only one part of the design.

## 2. Counts: Integer Domain, Constraints, and Overflow Risk

### 2.1. Why Do Counts Typically Use int or long?

Counts of indivisible entities usually belong to `0, 1, 2, ...`. Options include:

- `int`: 32-bit signed integer, range `-2^31` to `2^31 - 1`. Reasonable for loops, small quantities, or known bounded ranges.
- `long`: 64-bit signed integer, `-2^63` to `2^63 - 1`. Used for high-volume events, long-lived counters, sums across many sources.
- `BigInteger`: arbitrary-precision integer when requirements exceed the `long` range or mathematical results must never overflow.

A `long` can represent negative numbers, yet **a business domain like "item count" may forbid negatives**. Both type and validation share responsibility:

```java
record ItemCount(long value) {
    ItemCount {
        if (value < 0) {
            throw new IllegalArgumentException("Count must be non-negative");
        }
    }
}
```

This is an illustrative record snippet, placed in a valid class or source file. Because a Java `record` is a value carrier, validation in the compact constructor ensures every `ItemCount` instantiation upholds the invariant. A *delta* such as `-3` for a quantity adjustment may require **a separate `CountDelta` type**, rather than forcing it into `ItemCount`, which only allows non-negative values.

### 2.2. Overflow Is Not a Valid Business Addition

`int` and `long` have limits. Ordinary primitive addition does not throw an exception on overflow; the result wraps according to Java rules:

```java
int max = Integer.MAX_VALUE;
System.out.println(max + 1); // -2147483648
```

In quantity business logic, "turning from positive to negative" is usually a bug. `Math.addExact` detects overflow:

```java
long result = Math.addExact(1_000_000L, 2_000_000L);
System.out.println(result); // 3000000
// Math.addExact(Long.MAX_VALUE, 1L) throws ArithmeticException.
```

For data that can exceed `long`, use `BigInteger.add` or enforce valid range bounds per contract. Never use `double` to "hold any huge count": `double` has a very wide range of magnitudes, yet does not preserve every integer accurately above `2^53`.

### 2.3. Do Not Add Counts with Different Meanings

The sum of `3 users` and `5 login attempts` is not `8` meaningful units. Even though both are `long`, they should be clearly named, separated into classes, or modeled as domain records when needed:

```java
record UserCount(long value) {}
record LoginAttemptCount(long value) {}
```

This is only a data representation example, without validation yet. In a complete design, validate non-negativity and prevent accidental cross-type addition. A generic `Count` object is appropriate when counts share the same unit/meaning; counts from different domains should not be added just because Java permits the `+` operator.

## 3. Measured Quantities: Values Must Accompany Units and Precision Context

"`10`" tells you nothing if it could mean `10 meters`, `10 inches`, or `10 milliseconds`. A measured quantity needs at least:

- **Quantity kind**: length, mass, duration, temperature, volume...
- **Unit**: `m`, `cm`, `kg`, `ms`... following a consistent convention.
- **Value** in that unit.
- **Resolution/measurement uncertainty** when meaningful: a millimeter-graduated ruler and a sensor with ±0.1 °C error do not share the same experimental precision.

Addition is only valid when values have compatible units, after conversion if necessary:

```text
1.25 m + 75 cm
= 1.25 m + 0.75 m
= 2.00 m
```

You cannot directly add `1.25 + 75` and slap an `m` suffix on it. Similarly, Celsius temperature is an example showing that **not every quantity kind can be added/subtracted as simply as length**: absolute temperature and temperature difference need distinct modeling in business logic.

### 3.1. Two Approaches to Representing Measurements

**Approach A — Store integers in a sufficiently small base unit.** For example, durations accurate to milliseconds can be stored as `long milliseconds`; distances accurate to mm can be stored as `long millimeters`. Advantage: discrete unit additions are exact and free of floating-point error. Unit conversions may require rounding; the rule must be specified. You must also avoid overflow.

**Approach B — Store BigDecimal or double with unit.** For example, lengths recorded to `0.001 m` can be represented by `BigDecimal("1.235")`; physical sensor measurements are sometimes better suited to `double` due to their approximate nature, computation cost, and signal processing algorithms. Choosing `BigDecimal` **does not make a physical measurement more accurate than the measuring instrument**: it only represents and computes the provided decimal digits accurately.

Fix a **consistent internal unit**, such as always storing meters and converting to cm/inches only at interfaces. When converting by exact decimal factors such as `cm → m = divide by 100`, `BigDecimal.movePointLeft(2)` performs an exact conversion:

```java
BigDecimal centimeters = new BigDecimal("125.0");
BigDecimal meters = centimeters.movePointLeft(2);
System.out.println(meters.toPlainString()); // 1.250
```

The resulting value has scale 3, reflecting the decimal-point shift on the current representation. This is not a guarantee that the measurement has three experimentally significant decimal places; measurement significance must be documented separately.

### 3.2. Measurements Have Uncertainty, Not Just Extra Digits

Suppose a sensor records `1.234 m` with a measurement error around ±`0.01 m`. Printing `1.234000000 m` only adds *presentation* digits; it does not reduce error. In scientific reporting, record uncertainty and significant digits according to industry standards, e.g. `1.23 m ± 0.01 m` if that is the chosen presentation rule.

`setScale`, `DecimalFormat`, and `MathContext` change the **representation/arithmetic result**, without evaluating or reducing experimental error.

## 4. Decimal Values and BigDecimal: Scale vs. Precision

`BigDecimal` defines a number as `unscaledValue × 10^(-scale)`. For `new BigDecimal("12.3400")`:

- `unscaledValue()` is `123400`.
- `scale()` is `4` (four digits after the decimal point in this representation).
- `precision()` is `6` (six significant digits of the unscaled value).

`scale` differs from `precision`. `setScale(2)` targets **two digits after the decimal point**, not two significant digits. `MathContext(2, mode)` limits to **two significant digits** when applied to operations. Confusing the two concepts can round by the wrong order of magnitude.

```java
BigDecimal x = new BigDecimal("123.456");
System.out.println(x.setScale(2, RoundingMode.HALF_UP)); // 123.46
System.out.println(x.round(new MathContext(2, RoundingMode.HALF_UP))); // 1.2E+2
```

The isolated snippet above requires `import java.math.BigDecimal;`, `import java.math.MathContext;`, and `import java.math.RoundingMode;`.

### 4.1. Construct from String Instead of double When Decimal Data Must Be Exact

`new BigDecimal(0.1)` stores the exact binary approximation of the `double` literal, which differs from the decimal number `0.1`. To intentionally represent decimal `0.1`:

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
System.out.println(exactDecimal); // 0.1
System.out.println(fromValueOf);   // 0.1
```

`BigDecimal.valueOf(double)` converts from the decimal representation of `double`, which is often reasonable for simple literals, yet **cannot recover digits already lost in a prior sequence of `double` calculations**. For API or DB inputs, use the source's exact decimal format rather than passing through `double`.

### 4.2. BigDecimal Is Immutable

`add`, `multiply`, `divide` (when rounding info is sufficient), and `setScale` all return a new `BigDecimal` result; they never mutate the original instance:

```java
BigDecimal raw = new BigDecimal("10.005");
BigDecimal rounded = raw.setScale(2, RoundingMode.HALF_UP);
System.out.println(raw);     // 10.005
System.out.println(rounded); // 10.01
```

If you merely call `raw.setScale(2, mode);` and discard the result, `raw` remains unchanged. Immutability makes value models easier to reason about, yet **BigDecimal itself carries neither currency/unit nor business rounding rules**.

## 5. Rounding Rules Must Be Part of the Data Contract

A raw value `10.005` can become `10.00` or `10.01` depending on the rounding rule. When designing decimal values, explicitly define:

1. **Input/calculation scale**: how many digits to retain so critical information is not lost before settlement.
2. **Result scale**: e.g., two decimal places for an example format, not for every currency.
3. **RoundingMode**: `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`... as specified by the contract.
4. **Rounding boundary**: after each line item, after tax calculation, after the final total, when saving to DB, or only when displaying to users.
5. **Handling negative numbers**: refunds/adjustments; `CEILING` rounds toward positive infinity, `FLOOR` toward negative infinity.
6. **When precision loss is forbidden**: `RoundingMode.UNNECESSARY` to detect values that do not conform to the scale.

Example of `HALF_UP` to scale 2:

```java
System.out.println(new BigDecimal("10.004").setScale(2, RoundingMode.HALF_UP)); // 10.00
System.out.println(new BigDecimal("10.005").setScale(2, RoundingMode.HALF_UP)); // 10.01
System.out.println(new BigDecimal("-10.005").setScale(2, RoundingMode.HALF_UP)); // -10.01
```

`HALF_EVEN` selects the even final digit when two target values are equidistant from the original value. This rule can reduce statistical bias across many rounding operations, yet must not be assumed the right policy for every transaction. Example:

```java
System.out.println(new BigDecimal("1.245").setScale(2, RoundingMode.HALF_EVEN)); // 1.24
System.out.println(new BigDecimal("1.255").setScale(2, RoundingMode.HALF_EVEN)); // 1.26
```

**Do not round early just to make "data look clean."** If the total is rounded after summing, retain sufficient precision on line items before summing; if accounting rules mandate rounding each line, that is a separate process that must be implemented deliberately.

### 5.1. Rounding Parts Differs from Rounding the Total

Suppose two exact decimal amounts are `10.005` and `0.005`, ultimately returned at scale 2 with `HALF_UP`:

```text
Round each amount:
round2(10.005) + round2(0.005)
= 10.01 + 0.01
= 10.02

Sum exactly, then round:
round2(10.005 + 0.005)
= round2(10.010)
= 10.01
```

Both results can appear in a technically valid system. The contract decides **which result is permitted**. Good design centralizes this policy in a clearly named class or method rather than scattering `setScale(2)` across calculation steps.

### 5.2. Do Not Arbitrarily Round Twice

With `1.245`, `HALF_UP`:

```text
round1(round2(1.245)) = round1(1.25) = 1.3
round1(1.245) = 1.2
```

The results differ because intermediate rounding loses digits needed to evaluate the threshold at the final step. When rounding to a target scale, round directly from a value with sufficient precision, unless an intermediate rounding step is explicitly specified as a business event.

## 6. Modeling with Value Objects Instead of Passing Ambiguous Primitives

A method like `calculate(long a, BigDecimal b, BigDecimal c)` does not reveal what `a` counts, what unit `b` uses, or what currency `c` is in. Value objects/records can embed invariants into the data type.

Contract examples:

| Value object | Internal Data | Boundary Rules |
| --- | --- | --- |
| `ItemCount` | `long value` | Non-negative; add with `Math.addExact`; do not add to measurements. |
| `Length` | `BigDecimal meters` | Convert units to meters before adding; no negative length in this example domain. |
| `Money` | `String currency`, `BigDecimal amount` | Do not add differing currencies; allow negatives if refunds exist; round per explicit policy. |

`record` from Java 16+ works well as a value carrier with immutable components like `long`, `String`, and `BigDecimal`. You can define normalizing/validating constructors, factory methods from meaningful units, and domain operations instead of letting callers assemble raw additions.

Do not confuse **"valid data"** with "valid business semantics everywhere." For example, a negative count may be valid for a *delta* yet invalid for inventory on hand; a negative length may be invalid for physical length, whereas a directed displacement can be negative. Choose names and invariants that match the domain.

## 7. Complete Java 17+ Program

The example below intentionally keeps three value objects separate: `ItemCount`, `Length`, and `Money`. It illustrates validation, overflow control, converting cm to m, rounding money at boundaries, and preserving raw results.

Save the code as **`NumericDomainModelDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class NumericDomainModelDemo {

    record ItemCount(long value) {
        ItemCount {
            if (value < 0) {
                throw new IllegalArgumentException("Negative item count");
            }
        }

        ItemCount plus(ItemCount other) {
            Objects.requireNonNull(other, "other");
            return new ItemCount(Math.addExact(value, other.value));
        }
    }

    record Length(BigDecimal meters) {
        Length {
            Objects.requireNonNull(meters, "meters");
            if (meters.signum() < 0) {
                throw new IllegalArgumentException("Negative length");
            }
        }

        static Length fromCentimeters(String centimeters) {
            return new Length(
                    new BigDecimal(centimeters).movePointLeft(2));
        }

        Length plus(Length other) {
            Objects.requireNonNull(other, "other");
            return new Length(meters.add(other.meters));
        }

        String formatMeters(int scale, RoundingMode mode) {
            return meters.setScale(scale, mode).toPlainString() + " m";
        }
    }

    record Money(String currency, BigDecimal amount) {
        Money {
            Objects.requireNonNull(currency, "currency");
            Objects.requireNonNull(amount, "amount");
            if (currency.isBlank()) {
                throw new IllegalArgumentException("Blank currency");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currency mismatch");
            }
            return new Money(currency, amount.add(other.amount));
        }

        Money rounded(int scale, RoundingMode mode) {
            return new Money(currency, amount.setScale(scale, mode));
        }

        String display() {
            return currency + " " + amount.toPlainString();
        }
    }

    public static void main(String[] args) {
        ItemCount count = new ItemCount(4).plus(new ItemCount(7));
        System.out.println("items = " + count.value());

        Length distance = Length.fromCentimeters("12.5")
                .plus(Length.fromCentimeters("7.5"));
        System.out.println("meters exact = "
                + distance.meters().toPlainString());
        System.out.println("meters display = "
                + distance.formatMeters(2, RoundingMode.HALF_UP));

        Money first = new Money("USD", new BigDecimal("10.005"));
        Money second = new Money("USD", new BigDecimal("0.005"));
        Money rawTotal = first.plus(second);

        Money roundedTotal = rawTotal.rounded(2, RoundingMode.HALF_UP);
        Money roundedLines = first.rounded(2, RoundingMode.HALF_UP)
                .plus(second.rounded(2, RoundingMode.HALF_UP));

        System.out.println("raw total = " + rawTotal.display());
        System.out.println("rounded total = " + roundedTotal.display());
        System.out.println("sum rounded lines = " + roundedLines.display());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("same numeric value = "
                + (a.compareTo(b) == 0));
        System.out.println("same representation = " + a.equals(b));

        try {
            new ItemCount(Long.MAX_VALUE).plus(new ItemCount(1));
        } catch (ArithmeticException overflow) {
            System.out.println("count overflow = detected");
        }
    }
}
```

Compile and run with JDK 17+ in the directory containing the file:

```bash
javac NumericDomainModelDemo.java
java NumericDomainModelDemo
```

Exact output:

```text
items = 11
meters exact = 0.200
meters display = 0.20 m
raw total = USD 10.010
rounded total = USD 10.01
sum rounded lines = USD 10.02
same numeric value = true
same representation = false
count overflow = detected
```

**Explanation of each output:**

- `ItemCount` adds two non-negative integers with `Math.addExact`, producing count 11 and detecting overflow in the final case.
- `12.5 cm = 0.125 m`; `7.5 cm = 0.075 m`. Exact decimal addition gives `0.200 m`. `formatMeters(2, HALF_UP)` outputs `0.20 m` without mutating the source `Length` object.
- The two monetary amounts have a raw sum of `10.010`. Rounding the sum after addition yields `10.01`, whereas rounding each line item yields `10.01 + 0.01 = 10.02`. The program does not claim either policy is universally right beyond the example assumptions.
- `BigDecimal.compareTo` compares numeric value; `equals` also considers scale. `1.0` and `1.00` are numerically equal but do not share the same representation.
- `Money.plus` checks currency so USD and EUR are not accidentally added. The example still simplifies real-world business rules: it does not encode full ISO currency rules, exchange rates, fractional currency units, or legal regulations.

The `record` declarations and operations used are valid APIs since Java 17. The code uses no external libraries. In a real system, you can upgrade to specialized classes/domain modules, use explicit currency types, and enforce length limits, value ranges, and unit kinds per the application contract.

## 8. When to Use double vs. BigDecimal?

There is no rule saying "all measurements use `double`" or "all decimals use `BigDecimal`." Base the choice on **the meaning of the data and the precision that must be preserved**.

| Criterion | `double` | `BigDecimal` |
| --- | --- | --- |
| Representation | IEEE 754 binary, finite precision. | Decimal via unscaled value and scale. |
| Decimal `0.1` | Cannot be represented exactly in finite binary. | `new BigDecimal("0.1")` represents decimal 0.1 exactly. |
| Heavy computation, scientific math | Often efficient, strongly supported by numerical libraries. | Higher object allocation and arithmetic cost; requires evaluation. |
| Money/tax requiring exact decimal and rounding policy | Usually unsuitable as the business calculation source. | Usually suitable when precision, scale, and rounding are properly managed. |
| Physical measurements with error and continuous math | Can be suitable when binary precision suffices for the goal. | Can be suitable when inputs/outputs mandate decimal; does not remove measurement error. |
| Equality comparison | `==` has caveats around rounding, `NaN`, `-0.0`. | `equals()` checks scale too; `compareTo()` checks numeric value. |

With `double`, avoid comparing complex calculation results using only `==` when rounding error is acceptable. With `BigDecimal`, avoid the misconception that arbitrary precision means division always terminates: `1 / 3` requires a rounding policy or another representation; `divide` overloads without appropriate rounding can throw `ArithmeticException`.

A retail weight of `0.5 kg` is a measurement or *measured quantity*; if business rules require storing exact grams, you can store `long grams = 500` and display `0.500 kg` at the boundary. A power-measuring device operating on noisy signals may use `double` because experimental uncertainty far exceeds binary arithmetic error. The choice must be documented.

## 9. Conversion and Formatting Boundaries

A sound numeric model defines separate **conversion steps**:

```text
Input (string / API / DB)
    ↓ Parse and validate range
Value object (Count / Length / Money)
    ↓ Convert to consistent internal unit
Calculation (preserve appropriate precision)
    ↓ Apply rounding policy at the right boundary
Normalized exchange / storage value
    ↓ Format by locale or protocol
Display string / exchange payload
```

Pitfall to avoid: combining parsing, unit conversion, calculation, rounding, and formatting into one ambiguous call.

### 9.1. Converting from BigDecimal to Integers Must Be Controlled

`longValue()` can discard fractional parts or overflow in primitive-cast fashion. If the contract requires an **exact integer within the `long` range**, use `longValueExact()`:

```java
System.out.println(new BigDecimal("3.00").longValueExact()); // 3
// new BigDecimal("3.5").longValueExact() -> ArithmeticException.
// new BigDecimal("999999999999999999999999").longValueExact()
// -> ArithmeticException because it exceeds long range.
```

Use `BigDecimal.toBigIntegerExact()` when you must preserve an unbounded integer while rejecting fractional parts. Such exact methods belong in the validation/conversion step instead of silent casts.

### 9.2. Strings Without Exponents, While Scale Is a Separate Matter

`toPlainString()` produces a decimal string without scientific notation. To get exactly 2 digits after the decimal point with `HALF_UP`:

```java
BigDecimal amount = new BigDecimal("3.5");
String text = amount.setScale(2, RoundingMode.HALF_UP)
        .toPlainString();
System.out.println(text); // 3.50
```

However, `toPlainString()` does not add grouping separators, locale-specific decimal marks, or currency symbols. Use a formatter like `NumberFormat` with a `Locale` when presenting to human readers. Rounding inside a formatter is a separate decision: align it with business policy to avoid discrepancies between actual values and displayed values.

Note that `stripTrailingZeros()` can change scale; for a `BigDecimal` with negative scale, calling `toPlainString()` and re-parsing **may not preserve the original scale** even though the numeric value is unchanged. If preserving the unscaledValue/scale pair during transfer is required, use canonical `toString()` or store components explicitly per contract.

## 10. Database, API, and Multi-Unit Data Design

If a database stores money and decimals, `DECIMAL(p, s)`/`NUMERIC(p, s)` is usually more appropriate than floating-point types for business values requiring exact decimal representation; however, capabilities, precision/scale limits, defaults, and overflow/rounding behavior **depend on the DBMS**. Configure the schema according to actual constraints rather than assuming the DBMS will always "silently" round properly.

Design principle example (not a SQL statement portable to every DBMS):

```sql
CREATE TABLE invoice_line (
    id BIGINT PRIMARY KEY,
    quantity BIGINT NOT NULL,
    unit_price DECIMAL(19, 4) NOT NULL,
    currency_code CHAR(3) NOT NULL
);
```

The illustrative table stores `quantity` as an integer, unit price as a decimal with scale 4, and a separate currency code. If the business sells goods by kg in fractional quantities, `quantity BIGINT` **is insufficient**; you need `quantity_value DECIMAL(...)` and `unit_code`, or an integer in a defined smallest unit. Likewise, different currencies have different fractional rules, so the settlement policy must be specified.

In APIs, explicitly state the meaning of each field:

```json
{
  "quantity": 3,
  "unitPrice": "12.3450",
  "currency": "USD",
  "amountRounding": "HALF_UP",
  "settlementScale": 2
}
```

This JSON only **illustrates a possible contract design**, not a mandatory schema. The string `"12.3450"` preserves the intended decimal text/scale across systems that do not handle JSON Numbers with compatible precision; parse and validate it into `BigDecimal` on the Java side. Whether to use a JSON number or a decimal string depends on the protocol agreed with clients. **Do not blindly trust `roundingMode` and `scale` sent by clients if those rules are governed by the server/business**; the server must enforce the approved policy.

For measurement APIs, keep `value` and `unit` separate or use a clearly documented internal unit. For example:

```json
{
  "length": "125.0",
  "unit": "cm"
}
```

The server converts this to `1.250 m` according to unit rules. If a client sends `125.0` without stating a unit, guessing a default unit easily leads to severe unit-conversion bugs.

## 11. Common Numeric Data Design Mistakes

1. **Using `double` for all decimals needing exact money/tax.** Binary floating-point has representation error; use `BigDecimal` or integers in the smallest currency unit when matching the contract.
2. **Using `BigDecimal` unnecessarily for every number.** If counts are always integers within bounds, `int`/`long` is simpler and more efficient; if a measurement has physical uncertainty, infinite decimal precision adds no real accuracy.
3. **Not storing units for measurements.** `10` cannot distinguish meters from cm; add a unit or a type guaranteeing the base unit.
4. **Allowing negative counts outside the business domain.** Use constructor validation; distinguish absolute counts from count deltas.
5. **Ignoring overflow when adding counts.** `Math.addExact` or `BigInteger` helps detect/prevent wrong results.
6. **Adding different units or currencies.** Check compatibility before calculating; convert units accurately or convert currencies per exchange policy.
7. **Using `new BigDecimal(0.1)` to represent exact decimal 0.1.** Construct from a string or exact decimal source instead.
8. **Confusing precision with scale.** `MathContext(2)` and `setScale(2)` answer two different requirements.
9. **Rounding arbitrarily after every operation.** Intermediate rounding can alter sums; define clear business boundaries.
10. **Calling `setScale(2)` on a number requiring rounding without specifying a mode.** The single-argument overload throws `ArithmeticException` when non-zero digits must be discarded; choose a mode or use `UNNECESSARY` to check proactively.
11. **Comparing BigDecimals incorrectly.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` due to differing scale; use `compareTo() == 0` when only numeric equality is needed.
12. **Assuming measured data with many digits is infinitely accurate.** Preserve measurement error and resolution in models/reports when needed.
13. **Mixing formatting rules with monetary rules.** Currency symbols and locale separators are presentation; contract rounding is a business decision.
14. **Failing to control external data boundaries.** Negative inputs where disallowed, unknown units, overly long strings, `double` NaN/Infinity, or decimals exceeding DB precision must be handled properly.
15. **Turning display scale into storage scale too early.** If you store `amount` rounded before computing tax/totals, lost digits cannot be recovered afterward.

## 12. Self-Check Questions

**Question 1.** An application counts page views into the billions, and the number can grow continuously. Choose `int` or `long`?

**Answer:** `long` when the `int` limit can be exceeded; if totals can exceed `long`, use `BigInteger` or an explicit valid range policy. Use `Math.addExact` when overflow must be detected rather than wrapping around.

**Question 2.** Why shouldn't `2.5 kg` be stored as `ItemCount(2)`?

**Answer:** It is a measured quantity in kg, not a discrete integer count of items. It requires a decimal value or an integer in a base unit like grams, along with the unit.

**Question 3.** What is `125.0 cm` converted to meters using exact decimal arithmetic?

**Answer:** `1.250 m` via `new BigDecimal("125.0").movePointLeft(2)`. The displayed digits reflect the representation, without claiming extra experimental precision.

**Question 4.** Why do `new BigDecimal("12.3400").scale()` and `precision()` differ?

**Answer:** Scale is 4 places after the decimal point; precision is 6 significant digits in the unscaled value. They measure two different properties.

**Question 5.** Two amounts `10.005` and `0.005`, `HALF_UP` to scale 2: how does rounding the total at the end compare to rounding each item?

**Answer:** Rounding the total gives `10.01`; summing individually rounded items gives `10.02`. Contract policy determines which is used.

**Question 6.** If you want to reject a decimal with a fractional part when converting to `long`, which method do you choose?

**Answer:** `longValueExact()`; it throws `ArithmeticException` if there is a non-zero fractional part or if it exceeds the `long` range.

**Question 7.** Why can't `Money("USD", x)` and `Money("EUR", y)` be added directly?

**Answer:** Currency is part of the value's meaning. You need a currency-conversion process with an effective date and specific rounding rule, or you must reject the addition.

**Question 8.** When is `double` still a reasonable choice for measurements?

**Answer:** When the data is inherently approximate, processing/algorithm cost matters, floating-point error is within acceptable bounds, and the contract does not require exact decimals.

**Question 9.** If a measured length is `1.234 m` with uncertainty ±`0.01 m`, is displaying `1.234000 m` more accurate?

**Answer:** No. Appending trailing zeros does not reduce measurement uncertainty; reports must follow significant-digit and uncertainty rules.

**Question 10.** Why are value objects/records useful in numeric data design?

**Answer:** They name the data domain, enforce invariants, prevent invalid operations such as cross-unit or cross-currency addition, and centralize conversion and rounding logic in a clear place.

## 13. Official Java Documentation

- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal representation, precision, scale, immutable operations, and rounding.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): definitions of rounding modes.
- [Java SE 17 — Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): detecting integer overflow.
- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): arbitrary-precision integers.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): locale-aware number formatting, separated from business calculations.

**Key takeaway:** **Counts** require rules for integrality and range; **measurements** require values paired with units and error semantics; **rounded decimal values** require precision, scale, rounding mode, and clear application boundaries. Design the domain model right first, then choose `int`/`long`/`BigInteger`/`double`/`BigDecimal` to match the meaning of the data.