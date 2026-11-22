# BigDecimal Reference Table: precision, scale, MathContext, and RoundingMode

## 1. Concept Map

When working with decimal numbers in Java, four concepts are often confused with one another:

| Concept | Question It Answers | Represented By |
| --- | --- | --- |
| **Numerical value** | What number is this? | A `BigDecimal` with `unscaledValue` and `scale` |
| **BigDecimal Precision** | How many digits are in the unscaled integer without leading zeros? | `value.precision()` |
| **BigDecimal Scale** | Where is the decimal point relative to the unscaled integer? | `value.scale()`, can be negative |
| **MathContext** | How many **significant digits** may the operation/rounding keep? | `new MathContext(precision, roundingMode)` |
| **RoundingMode** | Which direction do we choose if digits must be dropped? | `RoundingMode.HALF_EVEN`, `HALF_UP`, etc. |

**Most important rule:** `setScale(2, mode)` asks for two digits **after the decimal point**; `round(new MathContext(2, mode))` asks for at most two **significant digits**. The two operations solve different problems and often yield different results.

```java
BigDecimal x = new BigDecimal("1234.567");

System.out.println(x.setScale(2, RoundingMode.HALF_UP)); // 1234.57
System.out.println(x.round(new MathContext(3, RoundingMode.HALF_UP))); // 1.23E+3
```

The first result keeps two decimal places; the second keeps three significant digits, corresponding to the value `1230`. Short snippets in this lesson assume `java.math.BigDecimal`, `java.math.MathContext`, and `java.math.RoundingMode` are imported; Section 11 provides a standalone Java 17+ program.

## 2. Core Formula: unscaled value, scale, and precision

According to `BigDecimal`'s model:

```text
numeric value = unscaledValue × 10^(-scale)
```

`unscaledValue` is a signed `BigInteger`; `scale` is an integer that can be positive, zero, or negative.

For example, `new BigDecimal("123.4500")` has:

- `unscaledValue() = 1234500`
- `scale() = 4`
- `precision() = 7`
- Value equals `1234500 × 10^-4 = 123.4500`

**Precision is not "digits before the decimal point" or "digits after the decimal point."** `BigDecimal`'s precision is the number of decimal digits in the unsigned unscaled integer, counted from the first nonzero digit; for zero, precision is 1.

| Construction | `toString()` | `unscaledValue()` | `scale()` | `precision()` |
| --- | --- | ---: | ---: | ---: |
| `new BigDecimal("123.4500")` | `123.4500` | 1234500 | 4 | 7 |
| `new BigDecimal("12.34")` | `12.34` | 1234 | 2 | 4 |
| `new BigDecimal("0.00120")` | `0.00120` | 120 | 5 | 3 |
| `new BigDecimal("1000")` | `1000` | 1000 | 0 | 4 |
| `new BigDecimal("1E+3")` | `1E+3` | 1 | -3 | 1 |
| `new BigDecimal("0.000")` | `0.000` | 0 | 3 | 1 |

The table shows that `1000` and `1E+3` have the **same numerical value** yet different scale/precision; `BigDecimal` does not merely hold an abstract real number, it also carries decimal representation state.

### 2.1. Negative Scale Is Not an Error

`new BigDecimal("1E+3")` has scale `-3`, meaning `1 × 10^3 = 1000`. When rounding to tens or hundreds, `setScale` can also produce a negative scale:

```java
BigDecimal x = new BigDecimal("1234.56");
BigDecimal hundreds = x.setScale(-2, RoundingMode.HALF_UP);

System.out.println(hundreds);                // 1.2E+3
System.out.println(hundreds.toPlainString()); // 1200
System.out.println(hundreds.scale());         // -2
```

**Scale = -2** means the rounding position is at the **hundreds place**, not "keep -2 digits." The rounded value is 1200.

### 2.2. Adjusted Exponent and Scientific Notation

A useful property when reading documentation is the *adjusted exponent*:

```text
adjusted exponent = precision - scale - 1
```

It indicates the order of magnitude of the first significant digit for nonzero values. For example, `123.45` has precision 5, scale 2, so adjusted exponent 2; in scientific notation it is roughly `1.2345 × 10^2`.

`toString()` may choose scientific notation; `toPlainString()` writes all digits without `E`. **Do not equate display strings with scale**: re-parsing the plain string of a `BigDecimal` with negative scale can produce an object with the same value but scale 0.

## 3. Comparison Table of scale and precision Operations

| API | Meaning | May Require Rounding? | Modifies Source Object? |
| --- | --- | --- | --- |
| `precision()` | Counts digits of the unscaled integer | No | No |
| `scale()` | Returns the stored scale | No | No |
| `unscaledValue()` | Returns the `BigInteger` unscaled value | No | No |
| `setScale(newScale)` | Requests a specific scale, **forbidding loss of significant digits** | Throws `ArithmeticException` if rounding is needed | No |
| `setScale(newScale, mode)` | Requests a specific scale with a rounding mode | Yes if decreasing scale and nonzero digits must be dropped | No |
| `round(mathContext)` | Rounds according to the context's significant precision | Yes if `precision > 0` and digits exceed the limit | No |
| `plus(mathContext)` | Returns value according to context | Possibly | No |
| `stripTrailingZeros()` | Removes droppable trailing zeros from representation, preserving value | Does not change value | No |
| `movePointLeft(n)` | Shifts decimal point left by `n` places | No arithmetic precision loss | No |
| `movePointRight(n)` | Shifts decimal point right by `n` places | No arithmetic precision loss | No |
| `toPlainString()` | Outputs decimal text without exponent | No | No |

`BigDecimal` is **immutable**. Every operation returns a result; calling `x.setScale(2, mode);` without saving the result **does not change** `x`'s value. There is no need to assert that the JVM always allocates a brand-new physical object; what matters is **immutability semantics**.

### 3.1. Changing Scale May Simply Add or Remove Zeros

```java
BigDecimal a = new BigDecimal("12.3");
BigDecimal moreZeros = a.setScale(4);
System.out.println(moreZeros); // 12.3000

BigDecimal b = new BigDecimal("12.3400");
BigDecimal fewerZeros = b.setScale(2);
System.out.println(fewerZeros); // 12.34
```

Both single-argument calls are valid because **no nonzero digits must be discarded**. However, `new BigDecimal("12.345").setScale(2)` throws `ArithmeticException` because digit `5` would be lost. To allow rounding, pass an explicit `RoundingMode`.

## 4. MathContext: Calculation Precision and Rounding Mode

`MathContext` holds two main fields:

- `precision`: **number of significant digits** kept in calculations using the context; precision `0` means **unlimited**.
- `roundingMode`: how to choose a result when rounding is required. It does not mean "apply rounding even when no digits are lost."

```java
MathContext mc = new MathContext(3, RoundingMode.HALF_UP);

BigDecimal original = new BigDecimal("1234.567");
BigDecimal rounded = original.round(mc);

System.out.println(rounded);                // 1.23E+3
System.out.println(rounded.toPlainString()); // 1230
```

When limited to three significant digits, rounding keeps `1, 2, 3` and adjusts the exponent; hence the resulting scale can become negative. `MathContext` **does not enforce a fixed scale** and does not replace `setScale` used at display or storage boundaries.

### 4.1. Predefined MathContext Constants

| Constant | Precision | Rounding Mode | How to Interpret |
| --- | ---: | --- | --- |
| `MathContext.UNLIMITED` | 0 | `HALF_UP` (rarely relevant since no rounding is forced) | Exact decimal arithmetic if the operation has a finite representation |
| `MathContext.DECIMAL32` | 7 | `HALF_EVEN` | Limit of 7 significant digits |
| `MathContext.DECIMAL64` | 16 | `HALF_EVEN` | Limit of 16 significant digits |
| `MathContext.DECIMAL128` | 34 | `HALF_EVEN` | Limit of 34 significant digits |

The three constants `DECIMAL32`/`64`/`128` set precision and mode as shown above; **do not assume they automatically enforce all exponent limits, NaN/Infinity handling, and all encoding rules of the corresponding IEEE 754 hardware formats**. `BigDecimal` has its own data type model.

`MathContext.UNLIMITED` or `new MathContext(0, mode)` **is not magic** that turns `1 / 3` into a finite decimal. When performing exact division whose quotient is an infinite decimal sequence, `divide` can still throw `ArithmeticException`.

### 4.2. Example Showing Context Is Not Equivalent to setScale

```java
BigDecimal n = new BigDecimal("1234.567");
BigDecimal fixedDecimals = n.setScale(2, RoundingMode.HALF_UP);
BigDecimal significantDigits = n.round(
        new MathContext(3, RoundingMode.HALF_UP));

System.out.println(fixedDecimals);   // 1234.57
System.out.println(significantDigits); // 1.23E+3
```

Argument 2 of `setScale` is **scale**, whereas argument 3 of `MathContext` is **precision**. Those two numbers do not have the same unit.

## 5. RoundingMode: Complete Table of All Eight Values

`java.math.RoundingMode` is an enum of eight modes. The table below rounds `+2.5` and `-2.5` to **scale 0**; both numbers lie exactly halfway between two adjacent integers.

| RoundingMode | Rule | `+2.5 → scale 0` | `-2.5 → scale 0` |
| --- | --- | ---: | ---: |
| `UP` | **Away from 0** if discarded part is nonzero | 3 | -3 |
| `DOWN` | **Toward 0**, drop remainder | 2 | -2 |
| `CEILING` | Toward **positive infinity** | 3 | -2 |
| `FLOOR` | Toward **negative infinity** | 2 | -3 |
| `HALF_UP` | Nearest; ties **away from 0** | 3 | -3 |
| `HALF_DOWN` | Nearest; ties **toward 0** | 2 | -2 |
| `HALF_EVEN` | Nearest; ties choose result with **even** last digit | 2 | -2 |
| `UNNECESSARY` | Requires **exact result, no digit loss** | Exception | Exception |

### 5.1. Distinguishing UP/DOWN vs. CEILING/FLOOR

The name `UP` in `RoundingMode` **does not mean increasing numerical value**: for `-2.5`, `UP` gives `-3` (away from 0), whereas `CEILING` gives `-2` (toward +∞).

For `+2.5`: `UP == CEILING` and `DOWN == FLOOR`.

For `-2.5`: `UP == FLOOR` and `DOWN == CEILING`.

That is why every rounding function accepting signed values needs tests for both positive and negative numbers.

### 5.2. The Three HALF Modes Differ Only at Exact Midpoints

For `2.4` to scale 0, `HALF_UP`, `HALF_DOWN`, and `HALF_EVEN` all produce 2.

For `2.6`, all three produce 3.

For `2.5`:

- `HALF_UP` → 3 (away from 0).
- `HALF_DOWN` → 2 (toward 0).
- `HALF_EVEN` → 2 (chooses the even number).

For `3.5`, `HALF_EVEN` → 4 (not always downward). "Even" checks the last digit of the **result** at the rounding position.

### 5.3. UNNECESSARY Is a Validation Tool

`RoundingMode.UNNECESSARY` does not mean "round down" or "do nothing." It states: if the operation requires rounding away nonzero digits, **throw `ArithmeticException`**.

```java
System.out.println(new BigDecimal("1.2300")
        .setScale(2, RoundingMode.UNNECESSARY)); // 1.23

// Throws ArithmeticException because digit 4 must be discarded:
new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
```

Use it when data formatting **must already match** the specified scale; for example, a unit price field allows at most two decimal places and the program must not silently round it.

## 6. API Selection Table by Requirement

| Practical Requirement | Suggested API | What to Watch |
| --- | --- | --- |
| Read significant digit count of a value | `value.precision()` | Zero has precision 1. |
| Read scale position | `value.scale()` | Scale can be negative. |
| Display exactly 2 decimal places | `value.setScale(2, mode).toPlainString()` | Mode is determined by business rules. |
| Accept at most 2 decimal places, no rounding | `value.setScale(2, UNNECESSARY)` | Fails if nonzero decimal digits exceed limit. |
| Round to 3 significant digits | `value.round(new MathContext(3, mode))` | Does not fix digits after decimal point. |
| Compute exact decimals when possible | `add`, `subtract`, `multiply` without context | Still mind memory/scale limits and non-terminating division. |
| Add/multiply with limited precision | `add(other, mc)`, `multiply(other, mc)` | Intermediate step results may be rounded. |
| Divide to exactly 2 decimal places | `divide(divisor, 2, mode)` | Choose rounding mode. |
| Divide to at most p significant digits | `divide(divisor, new MathContext(p, mode))` | Result scale is not fixed. |
| Divide completely exactly | `divide(divisor)` | Throws exception if decimal quotient is infinite. |
| Remove trailing zeros irrelevant to numeric value | `stripTrailingZeros()` | Can make scale negative. |
| Output decimal text without exponent | `toPlainString()` | Does not pick scale or rounding automatically. |
| Compare decimal numerical values | `a.compareTo(b) == 0` | `equals` also considers scale. |

The right choice depends on the **unit of the requirement**: "2 digits after the decimal point" is scale, "2 significant digits" is precision, "round half up" is mode, and "round only at final settlement" is **timing of application**.

## 7. Table of Operation Effects on precision and scale

When using `BigDecimal` without passing a `MathContext`, basic operations generally yield **exact decimal results**. The "preferred" scale of operations helps readers predict the representation:

| Operation | Mathematical Value | Preferred Scale of Exact Result |
| --- | --- | --- |
| `a.add(b)` | `a + b` | `max(a.scale(), b.scale())` |
| `a.subtract(b)` | `a - b` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a × b` | `a.scale() + b.scale()` |
| `a.divide(b)` | `a / b` | `a.scale() - b.scale()` is the preferred scale, though actual result scale may increase to represent an exact finite quotient |
| `a.setScale(s, mode)` | Rounded value if needed | Exactly `s` |
| `a.round(mc)` | Precision-limited value | Scale determined by rounding result |

Example:

```java
BigDecimal a = new BigDecimal("1.20");  // scale 2
BigDecimal b = new BigDecimal("3.456"); // scale 3

System.out.println(a.add(b));      // 4.656 (scale 3)
System.out.println(a.multiply(b)); // 4.14720 (scale 5)
```

`multiply` keeps the sum of operand scales and may print trailing zeros. Value `4.14720` equals `4.1472` numerically, though the two objects can have different scales.

### Division Must Distinguish "Exact" vs. "Rounded"

```java
System.out.println(new BigDecimal("1")
        .divide(new BigDecimal("8"))); // 0.125

System.out.println(new BigDecimal("1")
        .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP)); // 0.33

// Throws ArithmeticException because 1/3 cannot be an exact finite decimal:
new BigDecimal("1").divide(new BigDecimal("3"));
```

`BigDecimal` does not automatically divide into an infinite-digit result. The rounding rule is part of the API and must be explicitly specified for division.

### When Using MathContext at Every Step

`a.add(b, mc)`, `a.multiply(b, mc)`, and `a.divide(b, mc)` can return values **already rounded at that step**. Rounding after each step and then adding can produce a different final total from computing at sufficiently high precision and rounding once at the end.

Example with `RoundingMode.HALF_UP` at scale 2:

```text
round2(0.006) + round2(0.006) = 0.01 + 0.01 = 0.02
round2(0.006 + 0.006) = round2(0.012) = 0.01
```

This is not a `BigDecimal` bug: the two workflows have **different rounding points**. If business rules require rounding each invoice line, the first way may be right; if only the grand total is rounded, the second fits. Decide before passing a context to every operation.

## 8. Table of Negative Signs, Midpoints, and Boundaries

Tests with only positive numbers easily miss rounding bugs.

| Original Value | Target Scale | Mode | Result | Reason |
| --- | ---: | --- | --- | --- |
| `2.5` | 0 | `HALF_UP` | `3` | Midpoint, away from 0 |
| `-2.5` | 0 | `HALF_UP` | `-3` | Midpoint, away from 0 |
| `2.5` | 0 | `HALF_DOWN` | `2` | Midpoint, toward 0 |
| `-2.5` | 0 | `HALF_DOWN` | `-2` | Midpoint, toward 0 |
| `2.5` | 0 | `HALF_EVEN` | `2` | Midpoint, even result |
| `3.5` | 0 | `HALF_EVEN` | `4` | Midpoint, even result |
| `-2.5` | 0 | `CEILING` | `-2` | Toward +∞ |
| `-2.5` | 0 | `FLOOR` | `-3` | Toward -∞ |
| `1.2300` | 2 | `UNNECESSARY` | `1.23` | Drops zero, no value loss |
| `1.234` | 2 | `UNNECESSARY` | Error | Drops nonzero digit |
| `1234.56` | -2 | `HALF_UP` | `1200` | Rounds to hundreds |

**Contrast with `Math.round`:** `Math.round(-2.5)` returns `-2` because `Math.round`'s midpoint rule favors positive infinity, whereas `new BigDecimal("-2.5").setScale(0, HALF_UP)` returns `-3`. Do not interchange the two APIs simply because both are called "rounding."

## 9. Precision/Scale After stripTrailingZeros and During Comparison

`stripTrailingZeros()` removes trailing zeros that do not alter numerical value. However, representation/scale can change markedly:

```java
BigDecimal before = new BigDecimal("1000.00");
BigDecimal after = before.stripTrailingZeros();

System.out.println(before.scale());         // 2
System.out.println(after);                  // 1E+3
System.out.println(after.scale());           // -3
System.out.println(after.toPlainString());  // 1000
```

For `new BigDecimal("0.000").stripTrailingZeros()`, the result is a canonicalized zero with scale 0, no longer scale 3.

**Note that `equals` differs from `compareTo`:**

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));             // false
System.out.println(a.compareTo(b) == 0);     // true
```

`equals` distinguishes scale because the two representations differ. `compareTo` compares **numerical value**. This affects `HashMap`/`HashSet` keys when `BigDecimal` values have different scales: collections relying on `equals` do not treat them as the same object by value.

If the identity contract is "same decimal value," choose an input normalization rule or suitable key structure. However, do not call `stripTrailingZeros` indiscriminately on data where the number of decimal digits carries domain meaning (e.g., unit formats or standard formatting).

## 10. Practical Design Choices

### 10.1. Money and Invoices

For decimal values requiring rule-based calculations, typical choices are:

1. Read exact decimals from strings or database decimal types, without passing unnecessarily through `double`.
2. Preserve intermediate precision according to operations and contracts.
3. Apply `setScale(targetScale, roundingMode)` only at the **designated rounding boundary**.
4. Format strings with `toPlainString` or a locale-aware formatter; formatting does not replace a rounding policy.

`BigDecimal.valueOf(0.1)` usually produces the expected `0.1` representation from that `double` literal, whereas `new BigDecimal(0.1)` preserves the exact approximate binary value of the `double`. It is best to parse decimals directly from strings when the original data is available as decimal text.

Do not assume every currency uses scale 2 or the same rounding mode. Regulations, contracts, currency types, and rounding points determine them.

### 10.2. Measurements and Scientific Data

A measurement like `1.230 m` may carry information about instrument resolution. `precision()` is a **`BigDecimal` representation** property, not automatically measurement uncertainty or sensor significant figures. A separate unit and error model may be needed.

If data is inherently approximate and algorithms need speed, `double` may be reasonable. If exact decimals and rounding rules are required, `BigDecimal` is more suitable. Do not choose a numeric type solely by habit.

### 10.3. Storing in Databases or APIs

When a database specifies `DECIMAL(p,s)`, `p` and `s` are typically **total precision** and **scale**, though enforcement, rounding, overflow, and limits depend on the DBMS. You must check the actual schema contract; do not assume `new MathContext(p)` replaces validating all `DECIMAL(p,s)` constraints.

For instance, a number with precision ≤9 **and** scale 2 may require checking integer-part digit count, target scale, and specified rounding behavior. A precision-9 context does not automatically guarantee scale 2.

### 10.4. Errors from Dividing Twice or Rounding Twice

`round(finalScale, round(intermediateScale, value))` can differ from `round(finalScale, value)` under nearest-rounding modes. For example, `1.245`:

```text
setScale(2, HALF_UP) => 1.25
then setScale(1, HALF_UP) => 1.3

setScale(1, HALF_UP) directly => 1.2
```

An early rounding step can lose information about relative position to the final midpoint. When auditable results are required, retain full values and apply rounding only at permitted business points.

## 11. Complete Java 17+ Program (Verified Output)

Save as **`PrecisionScaleReferenceDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class PrecisionScaleReferenceDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("123.4500");
        BigDecimal z = new BigDecimal("0.000");
        BigDecimal e = new BigDecimal("1E+3");
        BigDecimal stripped = new BigDecimal("1000.00")
                .stripTrailingZeros();

        System.out.println("a precision=" + a.precision()
                + ", scale=" + a.scale());
        System.out.println("z precision=" + z.precision()
                + ", scale=" + z.scale());
        System.out.println("e precision=" + e.precision()
                + ", scale=" + e.scale());
        System.out.println("stripped=" + stripped
                + ", precision=" + stripped.precision()
                + ", scale=" + stripped.scale());

        BigDecimal x = new BigDecimal("1234.567");
        System.out.println("setScale="
                + x.setScale(2, RoundingMode.HALF_UP));
        BigDecimal rounded = x.round(
                new MathContext(3, RoundingMode.HALF_UP));
        System.out.println("mathContext=" + rounded);
        System.out.println("contextPlain=" + rounded.toPlainString());

        System.out.println("exactAdd="
                + new BigDecimal("1.20")
                        .add(new BigDecimal("3.456")));
        System.out.println("exactMultiply="
                + new BigDecimal("1.20")
                        .multiply(new BigDecimal("3.456")));
        System.out.println("divideRounded="
                + new BigDecimal("1")
                        .divide(new BigDecimal("3"), 2,
                                RoundingMode.HALF_UP));

        System.out.println("halfUpPositive="
                + new BigDecimal("2.5")
                        .setScale(0, RoundingMode.HALF_UP));
        System.out.println("halfUpNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.HALF_UP));
        System.out.println("halfEvenPositive="
                + new BigDecimal("2.5")
                        .setScale(0, RoundingMode.HALF_EVEN));
        System.out.println("halfEvenNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.HALF_EVEN));
        System.out.println("ceilingNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.CEILING));
        System.out.println("floorNegative="
                + new BigDecimal("-2.5")
                        .setScale(0, RoundingMode.FLOOR));

        BigDecimal hundreds = new BigDecimal("1234.56")
                .setScale(-2, RoundingMode.HALF_UP);
        System.out.println("negativeScale=" + hundreds);
        System.out.println("negativeScalePlain="
                + hundreds.toPlainString());

        System.out.println("unlimitedPrecision="
                + MathContext.UNLIMITED.getPrecision());
        System.out.println("decimal64Precision="
                + MathContext.DECIMAL64.getPrecision());
        System.out.println("trailingZeroScale="
                + z.stripTrailingZeros().scale());
    }
}
```

Run in the file's directory with JDK 17 or later:

```bash
javac PrecisionScaleReferenceDemo.java
java PrecisionScaleReferenceDemo
```

**Verified output from running the program:**

```text
a precision=7, scale=4
z precision=1, scale=3
e precision=1, scale=-3
stripped=1E+3, precision=1, scale=-3
setScale=1234.57
mathContext=1.23E+3
contextPlain=1230
exactAdd=4.656
exactMultiply=4.14720
divideRounded=0.33
halfUpPositive=3
halfUpNegative=-3
halfEvenPositive=2
halfEvenNegative=-2
ceilingNegative=-2
floorNegative=-3
negativeScale=1.2E+3
negativeScalePlain=1200
unlimitedPrecision=0
decimal64Precision=16
trailingZeroScale=0
```

Key observations in the output:

- `a` has precision 7 even though the displayed fractional part has four places; `z` has precision 1 despite three zeros after the decimal point.
- `setScale` and `MathContext` yield different numbers because their constraints differ.
- Negative scale produces scientific notation from `toString()`, whereas `toPlainString()` writes out all zeros.
- `HALF_UP` moves away from 0 at midpoints; `HALF_EVEN` chooses the even result.
- `MathContext.UNLIMITED.getPrecision() == 0` denotes **unlimited precision**, not "0 digits kept."

## 12. Short Code Patterns for Business Validation

### Pattern A: Require Exactly Two Decimal Places, No Rounding Allowed

```java
static BigDecimal requireTwoDecimals(BigDecimal value) {
    return value.setScale(2, RoundingMode.UNNECESSARY);
}
```

If `value` is `1.2300`, the result is `1.23`; if it is `1.234`, `ArithmeticException` is thrown. This method merely illustrates a validation policy and must be placed inside a Java class.

### Pattern B: Round Only at Settlement

```java
static BigDecimal sumThenRound(
        java.util.List<BigDecimal> values) {
    BigDecimal total = BigDecimal.ZERO;
    for (BigDecimal value : values) {
        total = total.add(value);
    }
    return total.setScale(2, RoundingMode.HALF_UP);
}
```

This is a sample policy; it is unsuitable if rules mandate rounding **each line item before summing**. Document why scale 2 and the mode are chosen rather than scattering these constants across the codebase.

### Pattern C: Compare by Numerical Value

```java
static boolean numericallyEqual(
        BigDecimal left, BigDecimal right) {
    return left.compareTo(right) == 0;
}
```

`new BigDecimal("1.0")` and `new BigDecimal("1.00")` compare numerically equal, while `equals` returns false due to different scales. If used as hash keys, normalize upfront per contract rather than mixing different comparison strategies across classes.

### Pattern D: Divide with Explicit Scale

```java
static BigDecimal divideToTwoDecimals(
        BigDecimal numerator, BigDecimal denominator) {
    return numerator.divide(denominator, 2,
            RoundingMode.HALF_EVEN);
}
```

You must check that the denominator is nonzero and pick the mode per business rules. This too is only an illustrative method.

## 13. Quick Diagnosis of Common Symptoms

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| `setScale(2)` throws `ArithmeticException` | Nonzero digits must be dropped but no mode passed | Pass a mode **if rounding is allowed**, or use `UNNECESSARY` to reject intentionally |
| `divide()` throws error on `1/3` | Non-terminating decimal quotient | Specify scale + mode or `MathContext` per requirements |
| Result `1.23E+3` instead of `1230` | Negative scale and `toString()` formatting | Use `toPlainString()` if decimal text without exponent is needed |
| `precision()` returns 1 for `0.000` | Precision of zero is defined as 1 | Do not equate precision with decimal digit count |
| `setScale(2)` and `round(mc)` give different numbers | Fixed-scale differs from significant digits | Re-check the true requirement: decimal places or significant digits? |
| `equals` is false even though numbers look identical | Different scales | Use `compareTo() == 0` if only numerical equality is needed |
| `1E+3` appears after `stripTrailingZeros()` | Trailing zeros stripped, scale became negative | Review requirements for preserving scale/trailing zeros and output strings |
| Sum differs when parallelized/rounded step-by-step | Intermediate rounding changes result | Establish clear rounding boundaries; do not round arbitrarily |
| `MathContext.UNLIMITED` still fails dividing `1/3` | Unlimited precision does not make infinite decimals finite | Define an approximate/rounding policy or fractional representation |
| `new BigDecimal(0.1)` has many strange digits | Input `double` is a binary approximation | Use a decimal string or suitable conversion API |

## 14. Quick Reference Questions

**Question 1.** What are the precision and scale of `new BigDecimal("0.00120")`?

**Answer:** Precision 3 (significant digits 1, 2, 0), scale 5.

**Question 2.** What is the scale of `new BigDecimal("1E+3")`?

**Answer:** Scale `-3`, precision 1. Value is 1000.

**Question 3.** What should you use to get `"12.30"` from `new BigDecimal("12.3")`?

**Answer:** `setScale(2).toPlainString()`, because adding zeros loses no significant digits.

**Question 4.** Is `setScale(2, HALF_UP)` the same as `round(new MathContext(2, HALF_UP))`?

**Answer:** No. One keeps two decimal places; the other keeps two significant digits.

**Question 5.** Which modes turn `-2.5` into `-3` at scale 0?

**Answer:** `UP`, `FLOOR`, and `HALF_UP`; `HALF_EVEN` chooses `-2` because it is even.

**Question 6.** When is `RoundingMode.UNNECESSARY` used?

**Answer:** When the operation must be exact at the requested scale/precision; if nonzero digits would have to be dropped, the API throws `ArithmeticException`.

**Question 7.** What precision/mode does `MathContext.DECIMAL64` have?

**Answer:** Precision 16 and `HALF_EVEN`.

**Question 8.** Can `stripTrailingZeros()` produce a negative scale?

**Answer:** Yes; `new BigDecimal("1000.00").stripTrailingZeros()` becomes representation `1E+3`, scale `-3`.

**Question 9.** Does `BigDecimal.ONE.divide(new BigDecimal("3"))` return an exact decimal?

**Answer:** No. It throws `ArithmeticException` because `1/3` has no finite decimal representation.

**Question 10.** When must you round the sum instead of each item?

**Answer:** When the business contract places the rounding boundary at the final total. You cannot infer the policy from the `BigDecimal` or `MathContext` type alone; the two choices can yield different results.

## 15. Official Documentation

- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `precision`, `scale`, `setScale`, `round`, `stripTrailingZeros`, and operations.
- [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): significant precision, rounding mode, and constant contexts.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): full behavior table of rounding modes.

**Summary for lookup:** `precision()` measures **significant digits of the representation**, `scale()` determines **the decimal point position**, `MathContext` limits **precision during calculation/rounding**, `RoundingMode` decides **which direction to round**, and `setScale` applies a **specific target scale**. Always determine both **when rounding occurs** and its **business meaning** before combining these APIs.
