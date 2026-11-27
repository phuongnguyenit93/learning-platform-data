# Choosing `BigDecimal` When Exact Decimal Numbers Are Needed in Java 17

**Topic:** Java 17  
**Chapter:** Floating-Point Numbers  
**Lesson:** Choosing BigDecimal When Exact Decimal Numbers Are Needed

When handling money, product prices, taxes, discounts, interest rates, or data requiring exact decimal values, `float` and `double` can introduce representation errors. Java provides `java.math.BigDecimal` to represent and compute decimal numbers with arbitrary precision, following rounding rules specified by the program.

Crucially, this is not merely changing a variable's type from `double` to `BigDecimal`. To get exact results, you must **initialize it properly**, keep data in decimal form throughout the entire calculation, choose when and how to round, and handle division and comparisons correctly.

This lesson focuses on:

- Why binary floating-point numbers may fail to represent familiar decimal numbers exactly.
- How to construct `BigDecimal` from strings, integers, and `double` values.
- The meaning of `precision`, `scale`, immutability, and operations.
- The difference between `equals()` and `compareTo()`.
- How to divide, set decimal places, and choose `RoundingMode`.
- How to use `BigDecimal` for currency, user input, and databases.

`BigDecimal` has existed since the earliest Java versions and works normally in Java 17. It is a standard API in the `java.math` package, not a preview feature.

## 1. Why Is `double` Not Always Exact for Decimal Numbers?

Computers represent `float` and `double` in binary. Much like the fraction `1/3` has an infinite decimal expansion `0.3333...`, many fractions have infinite binary expansions.

For example, the decimal `0.1` cannot be represented exactly with a finite number of bits in binary floating-point format. The actual stored value is a binary number very close to `0.1`.

```java
public class FloatingPointExample {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;

        System.out.println(a + b);
        System.out.println((0.1 + 0.2) == 0.3);
    }
}
```

Typical output:

```text
0.30000000000000004
false
```

This is not a random Java bug. It is a consequence of IEEE 754 floating-point representation. `double` behaves correctly according to that type's rules; the issue is that **some decimal values lack a finite binary representation**.

### 1.1. Errors Can Accumulate

A single calculation may deviate only slightly, yet repeated additions, subtractions, multiplications, or comparisons can cause errors to affect business results.

Example of a system summing multiple line values:

```java
double total = 0.0;

for (int i = 0; i < 10; i++) {
    total += 0.1;
}

System.out.println(total);
```

The result may not equal the exact expected decimal value `1.0`. When a system must reconcile payments, balances, invoices, or reports, multi-step drift is a risk to avoid.

### 1.2. When Is Floating-Point Error Not a Problem?

Not every program needs `BigDecimal`. `double` fits many scientific problems, graphics, simulations, signal processing, and computations where approximate error is acceptable.

For instance, when simulating an object's position, relative accuracy and performance can be more important than representing every decimal value exactly.

Choose based on your data domain's requirements:

| Need | Usually Appropriate Type | Reason |
|---|---|---|
| Product prices, monetary amounts, taxes, discounts | `BigDecimal` or integer smallest units | Requires exact control over decimal values and rounding rules |
| Rates, interest, decimal quantities requiring reconciliation | `BigDecimal` | Controls precision, scale, and rounding |
| Graphics, physics simulation, approximate computation | `double` | Good performance and an approximate model is usually appropriate |
| Indices, integer counts | `int` or `long` | No decimal fraction needed |
| Money with fixed smallest unit and simple arithmetic | Can use `long` storing smallest units | Avoids floating point, though scale and business rules must be managed manually |

**Principle:** Use `BigDecimal` when decimal exactness is part of the business requirement. You do not need to use it for every arithmetic calculation.

## 2. How Does `BigDecimal` Represent Decimal Numbers?

`BigDecimal` represents a value using an arbitrary-length integer (unscaled value) and a scale:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Examples:

| Representation | Unscaled Value | Scale | Value |
|---|---:|---:|---:|
| `123.45` | 12345 | 2 | \(12345 \times 10^{-2}\) |
| `7.00` | 700 | 2 | \(700 \times 10^{-2}\) |
| `0.001` | 1 | 3 | \(1 \times 10^{-3}\) |
| `1200` | 1200 | 0 | \(1200 \times 10^0\) |
| `1.2E+3` | 12 | -2 | \(12 \times 10^2\) |

Scale does not have to be non-negative. A number in scientific notation like `1.2E+3` can have a negative scale.

### 2.1. What Is Precision?

`precision()` returns the number of digits in the unscaled value, ignoring any minus sign and not counting the exponent as digits.

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("123.4500");

System.out.println(amount.precision()); // 7
System.out.println(amount.scale());     // 4
```

Here:

- Unscaled value is `1234500`, containing 7 digits.
- Scale is 4, meaning 4 digits to the right of the decimal point.
- The numeric value is still `123.45`.

### 2.2. Scale Is Not a Limit on Total Significant Digits

```java
BigDecimal a = new BigDecimal("123.45");
BigDecimal b = new BigDecimal("0.001");
BigDecimal c = new BigDecimal("1000");

System.out.println(a.scale()); // 2
System.out.println(b.scale()); // 3
System.out.println(c.scale()); // 0
```

Scale indicates the decimal point position in the representation. Precision indicates the number of digits in the unscaled part. These two concepts are distinct.

In monetary systems, a database column of type `DECIMAL(19, 2)` typically has precision 19 and scale 2. That is a storage schema constraint; `BigDecimal` itself is not limited to 19 digits.

## 3. Initializing `BigDecimal` Properly

How you create `BigDecimal` determines whether input data starts out exact. This is a critical part.

### 3.1. Prefer the `String` Constructor for Decimal Data

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal quantity = new BigDecimal("2.5");
```

`String` is parsed as a decimal representation, so `new BigDecimal("0.1")` represents the exact decimal 0.1.

This is typically the right choice when data comes from:

- Input forms.
- CSV or configuration files.
- JSON containing decimal numeric tokens.
- Database columns of type `DECIMAL`/`NUMERIC`.
- Business rules written as decimal strings.

If the string is not a valid numeric representation, the constructor throws `NumberFormatException`:

```java
BigDecimal value = new BigDecimal("12,50"); // NumberFormatException
```

`BigDecimal(String)` does not interpret locale-specific commas. Standard API input typically uses a dot as the decimal separator: `"12.50"`.

### 3.2. Use `BigDecimal.valueOf(long)` for Integers

```java
BigDecimal cents = BigDecimal.valueOf(1250);
BigDecimal count = BigDecimal.valueOf(3);

System.out.println(cents); // 1250
System.out.println(count); // 3
```

This method is convenient for creating `BigDecimal` from an already-exact `long` or `int`.

### 3.3. Avoid `new BigDecimal(double)` for Decimals Needing Exactness

The following often surprises developers:

```java
BigDecimal wrong = new BigDecimal(0.1);

System.out.println(wrong);
```

The resulting value is the exact decimal representation of **the stored binary `double` value**, not the ideal decimal `0.1`. Output can look like:

```text
0.1000000000000000055511151231257827021181583404541015625
```

The constructor did not corrupt the data; it accurately reflected the `double` input value. However, that input was already not the exact decimal `0.1`.

### 3.4. If You Already Have a `double`, Use `BigDecimal.valueOf(double)`

```java
BigDecimal decimal = BigDecimal.valueOf(0.1);

System.out.println(decimal); // 0.1
```

`BigDecimal.valueOf(double)` uses the canonical string representation from `Double.toString(double)` and constructs a `BigDecimal` from that string. Thus it usually produces a more predictable decimal result than the `double` constructor.

However, understand its limits:

- It **does not recover information lost** in prior `double` calculations.
- It uses the concise decimal representation of the double value, without proving that prior calculations were exact according to business rules.
- If the original input was a decimal entered by a user, it is best to keep that string and construct `BigDecimal` directly.

Example:

```java
double calculated = 0.1 + 0.2;

BigDecimal fromDouble = BigDecimal.valueOf(calculated);
BigDecimal fromText = new BigDecimal("0.3");

System.out.println(fromDouble); // 0.30000000000000004
System.out.println(fromText);   // 0.3
```

`valueOf` cannot turn an already-drifted double result back into the original intended business value.

### 3.5. Comparing Initialization Methods

| Creation Method | Example | Recommendation |
|---|---|---|
| Decimal string | `new BigDecimal("0.1")` | **Preferred** when original data is decimal |
| Integer | `BigDecimal.valueOf(100L)` | Good when input is an exact integer |
| double via `valueOf` | `BigDecimal.valueOf(0.1)` | Use when source is necessarily double and you want its canonical string form |
| double constructor | `new BigDecimal(0.1)` | Avoid for business decimal data |

### 3.6. Declaring Constants

```java
private static final BigDecimal ZERO = BigDecimal.ZERO;
private static final BigDecimal ONE = BigDecimal.ONE;
private static final BigDecimal HUNDRED = BigDecimal.valueOf(100);

private static final BigDecimal TAX_RATE = new BigDecimal("0.08");
```

The constants `ZERO`, `ONE`, and `TEN` are built into the API. For decimal rates, use strings to express the exact intent.

## 4. Basic Operations

`BigDecimal` provides methods for arithmetic operations instead of using the `+`, `-`, `*`, or `/` operators.

| Operation | Method | Example |
|---|---|---|
| Addition | `add()` | `a.add(b)` |
| Subtraction | `subtract()` | `a.subtract(b)` |
| Multiplication | `multiply()` | `a.multiply(b)` |
| Exact division | `divide()` | `a.divide(b)` |
| Division with rounding | `divide(divisor, scale, roundingMode)` | `a.divide(b, 2, RoundingMode.HALF_UP)` |
| Remainder | `remainder()` | `a.remainder(b)` |
| Change scale | `setScale()` | `a.setScale(2, RoundingMode.HALF_UP)` |
| Numeric comparison | `compareTo()` | `a.compareTo(b)` |

Example:

```java
BigDecimal a = new BigDecimal("12.50");
BigDecimal b = new BigDecimal("2.25");

System.out.println(a.add(b));      // 14.75
System.out.println(a.subtract(b)); // 10.25
System.out.println(a.multiply(b)); // 28.1250
```

### 4.1. Addition and Subtraction Preserve Exactness

```java
BigDecimal total = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

System.out.println(total); // 0.3
```

There is no binary representation error like the corresponding `double` addition.

Results of addition/subtraction do not automatically round to two decimal places. The result's scale depends on the operands' scales; apply business rounding rules when needed.

### 4.2. Multiplication Can Produce More Decimal Places

```java
BigDecimal unitPrice = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("2.5");

BigDecimal total = unitPrice.multiply(quantity);

System.out.println(total); // 49.975
```

Exact multiplication does not automatically round to two digits. If business rules require a monetary result of scale 2, explicitly decide when and how to round:

```java
BigDecimal rounded = total.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 49.98
```

### 4.3. Do Not Use Arithmetic Operators Directly

You cannot write:

```java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("2.30");

// Invalid:
// BigDecimal total = a + b;
```

Use `a.add(b)`. Java does not define the `+` operator for `BigDecimal` objects.

## 5. `BigDecimal` Is Immutable

`BigDecimal` objects are **immutable**. Every operation returns a new object; it never modifies the original object.

```java
BigDecimal amount = new BigDecimal("10.00");

amount.add(new BigDecimal("5.00"));

System.out.println(amount); // 10.00
```

The line `amount.add(...)` does not modify `amount`. To keep the result, you must reassign it:

```java
amount = amount.add(new BigDecimal("5.00"));

System.out.println(amount); // 15.00
```

Similarly with `setScale`:

```java
BigDecimal price = new BigDecimal("12.345");

price.setScale(2, RoundingMode.HALF_UP);
System.out.println(price); // 12.345

price = price.setScale(2, RoundingMode.HALF_UP);
System.out.println(price); // 12.35
```

This is a common mistake when starting with `BigDecimal`: calling a method without saving the returned value.

## 6. Distinguishing `equals()` and `compareTo()`

This is one of the most important distinctions when working with `BigDecimal`.

- `equals()` compares **value and scale**.
- `compareTo()` compares **numeric value**, ignoring scale differences.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));        // false
System.out.println(a.compareTo(b));    // 0
System.out.println(a.compareTo(b) == 0); // true
```

`2.0` and `2.00` both represent the numeric value 2, yet have scales 1 and 2, respectively. Because `equals` checks scale as well, it returns `false`.

### 6.1. Greater-Than and Less-Than Comparisons

Do not use `>`, `<`, or `==` operators on two `BigDecimal` objects:

```java
BigDecimal balance = new BigDecimal("100.00");
BigDecimal limit = new BigDecimal("50.00");

if (balance.compareTo(limit) > 0) {
    System.out.println("Balance exceeds limit");
}
```

Results of `compareTo`:

| Result | Meaning |
|---:|---|
| Negative number | Left value is less than right value |
| 0 | Both values are numerically equal |
| Positive number | Left value is greater than right value |

Do not rely on specific negative/positive values beyond the sign and zero.

### 6.2. Impact in `Set` and `Map`

Because `equals()` and `hashCode()` consider scale, `2.0` and `2.00` are two distinct keys in a `HashMap` or two distinct elements in a `HashSet`:

```java
var values = new java.util.HashSet<BigDecimal>();
values.add(new BigDecimal("2.0"));
values.add(new BigDecimal("2.00"));

System.out.println(values.size()); // 2
```

Conversely, order-based structures like `TreeSet` use `compareTo` by default:

```java
var sorted = new java.util.TreeSet<BigDecimal>();
sorted.add(new BigDecimal("2.0"));
sorted.add(new BigDecimal("2.00"));

System.out.println(sorted.size()); // 1
```

Because `compareTo` returns 0, `TreeSet` considers the two values to be the same element under natural ordering.

**Practice:** If the business domain treats `2.0` and `2.00` as the same value, use `compareTo(...) == 0` for comparisons. If used as keys, standardize scale before inserting into collections or design an appropriate comparator/equals policy.

### 6.3. Scale Can Be Normalized When Needed

```java
BigDecimal normalizedA = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal normalizedB = new BigDecimal("2.00").stripTrailingZeros();

System.out.println(normalizedA.equals(normalizedB)); // true
```

However, `stripTrailingZeros()` can produce a negative scale. For instance, `new BigDecimal("1000").stripTrailingZeros()` may have representation `1E+3`. When outputting strings without scientific notation, consider `toPlainString()`.

## 7. Division and the Non-Terminating Decimal Problem

Division requires special attention. Some results have a finite decimal representation:

```java
BigDecimal a = new BigDecimal("1");
BigDecimal b = new BigDecimal("4");

System.out.println(a.divide(b)); // 0.25
```

However, `1 / 3` has an infinite decimal expansion:

```java
BigDecimal a = BigDecimal.ONE;
BigDecimal b = new BigDecimal("3");

System.out.println(a.divide(b)); // ArithmeticException
```

`BigDecimal.divide(divisor)` requires an exact result when no rounding rule is supplied. If the quotient has a non-terminating decimal expansion, Java cannot return a finite exact `BigDecimal`, so it throws `ArithmeticException`.

### 7.1. Dividing with Scale and Rounding Mode

When business rules allow limiting decimal places, specify scale and rounding mode:

```java
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        2,
        RoundingMode.HALF_UP
);

System.out.println(result); // 0.33
```

Reading the arguments:

- Divisor: `3`.
- Result scale: `2`, meaning two digits to the right of the decimal point.
- Rounding mode: `HALF_UP`.

### 7.2. Dividing with `MathContext`

You can limit total significant digits using `MathContext`:

```java
import java.math.MathContext;
import java.math.RoundingMode;

MathContext context = new MathContext(5, RoundingMode.HALF_UP);

BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"),
        context
);

System.out.println(result); // 0.33333
```

Difference from scale:

- `scale = 2` sets the number of digits after the decimal point to 2.
- `precision = 5` in `MathContext` limits the total number of significant digits to 5.

For example, `12345.6` with precision 5 will be rounded to 5 significant digits, not 5 digits after the decimal point.

### 7.3. Divide Exactly When Possible, Round When Business Rules Require

Do not pick a scale and rounding mode just to avoid an exception. Determine:

- In what unit is the result stored?
- How many decimal places are needed?
- Is rounding applied per line item, on the invoice total, or only on display?
- Which contract, accounting standard, or business rule governs rounding?

If exactness is strictly required and the division has a terminating result, you can use `divide(divisor)`. If the result is non-terminating or scale must be bounded, choose an explicit rounding rule.

## 8. `RoundingMode` Rounding Modes

`java.math.RoundingMode` specifies how values with more digits than the target scale are adjusted to the required digits.

Standard modes in Java 17:

| Mode | Rule |
|---|---|
| `UP` | Round away from 0 if digits must be discarded |
| `DOWN` | Truncate toward 0 |
| `CEILING` | Round toward positive infinity |
| `FLOOR` | Round toward negative infinity |
| `HALF_UP` | Nearest neighbor; on exact tie, round away from 0 |
| `HALF_DOWN` | Nearest neighbor; on exact tie, round toward 0 |
| `HALF_EVEN` | Nearest neighbor; on exact tie, choose the even last digit |
| `UNNECESSARY` | Require no rounding; throw an exception if rounding is needed |

### 8.1. Examples with `HALF_UP` and `HALF_EVEN`

```java
BigDecimal a = new BigDecimal("2.345");
BigDecimal b = new BigDecimal("2.355");

System.out.println(a.setScale(2, RoundingMode.HALF_UP));   // 2.35
System.out.println(b.setScale(2, RoundingMode.HALF_UP));   // 2.36

System.out.println(a.setScale(2, RoundingMode.HALF_EVEN)); // 2.34
System.out.println(b.setScale(2, RoundingMode.HALF_EVEN)); // 2.36
```

With `HALF_EVEN`:

- `2.345` is halfway between `2.34` and `2.35`; the last digit of `2.34` is 4 (even), so `2.34` is chosen.
- `2.355` is halfway between `2.35` and `2.36`; the last digit of `2.36` is 6 (even), so `2.36` is chosen.

`HALF_EVEN` is often called *banker's rounding*, though not every financial system uses it. You must follow the specific business rule.

### 8.2. Rounding Negative Numbers

Rules for toward 0, away from 0, and toward positive/negative infinity behave differently:

```java
BigDecimal value = new BigDecimal("-1.231");

System.out.println(value.setScale(2, RoundingMode.DOWN));    // -1.23
System.out.println(value.setScale(2, RoundingMode.UP));      // -1.24
System.out.println(value.setScale(2, RoundingMode.CEILING));  // -1.23
System.out.println(value.setScale(2, RoundingMode.FLOOR));    // -1.24
```

- `DOWN` moves toward 0.
- `UP` moves away from 0.
- `CEILING` moves toward greater values on the number line.
- `FLOOR` moves toward smaller values on the number line.

Do not interpret `CEILING` as "always increase absolute magnitude"; for negative numbers, the result can be less negative.

### 8.3. `UNNECESSARY` for Scale Validation

When data must have at most two decimal places and must not be rounded, use `UNNECESSARY`:

```java
BigDecimal valid = new BigDecimal("12.30")
        .setScale(2, RoundingMode.UNNECESSARY);

BigDecimal invalid = new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY); // ArithmeticException
```

This is a useful way to catch inputs exceeding the specified scale rather than silently rounding them.

### 8.4. `setScale` Does Not Mutate the Object

```java
BigDecimal amount = new BigDecimal("10.999");

BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);

System.out.println(amount);  // 10.999
System.out.println(rounded); // 11.00
```

Because `BigDecimal` is immutable, the rounded result must be stored in a new variable or reassigned.

## 9. Scale and Displaying Results

`BigDecimal` stores both value and scale. Two values can be numerically equal while formatting differently.

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.toString()); // 10.0
System.out.println(b.toString()); // 10.00
```

This is helpful when scale represents significant decimal places in business logic, such as currency displayed with two digits after the decimal point.

### 9.1. `setScale` to Standardize Decimal Places

```java
BigDecimal amount = new BigDecimal("10");

BigDecimal twoDecimals = amount.setScale(2);

System.out.println(twoDecimals); // 10.00
```

If only adding trailing zeros without changing numeric value, `setScale(2)` can be used without specifying a rounding mode. However, if significant non-zero digits must be dropped, Java throws `ArithmeticException` unless a rounding rule is given.

```java
BigDecimal amount = new BigDecimal("10.125");

// Throws ArithmeticException because digits must be dropped without a rounding mode:
amount.setScale(2);
```

### 9.2. `toString()` and `toPlainString()`

```java
BigDecimal value = new BigDecimal("1E+3");

System.out.println(value.toString());      // 1E+3
System.out.println(value.toPlainString()); // 1000
```

- `toString()` may use scientific notation when applicable.
- `toPlainString()` produces a decimal string without an exponent.
- `toEngineeringString()` uses engineering notation.

When displaying currency, fixed scale and locale-aware formatting are usually needed rather than simply calling `toString()`.

### 9.3. `stripTrailingZeros()` Can Change Scale

```java
BigDecimal value = new BigDecimal("1000.00");
BigDecimal stripped = value.stripTrailingZeros();

System.out.println(stripped); // may print 1E+3
System.out.println(stripped.scale()); // -3
```

`stripTrailingZeros()` removes unnecessary trailing zeros and can make the scale negative. If the system must always keep two currency decimal digits, do not call it indiscriminately in display paths.

## 10. Business Example: Calculating Line Items and Tax

Suppose an order has:

- Unit price: `19.99`.
- Quantity: `3`.
- Illustrative tax rate: `8%`.

Calculate subtotal, tax, and total using `BigDecimal`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class InvoiceCalculation {
    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.99");
        BigDecimal quantity = BigDecimal.valueOf(3);
        BigDecimal taxRate = new BigDecimal("0.08");

        BigDecimal subtotal = unitPrice.multiply(quantity);

        BigDecimal tax = subtotal
                .multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal total = subtotal.add(tax)
                .setScale(2, RoundingMode.HALF_UP);

        System.out.println("Subtotal: " + subtotal.toPlainString());
        System.out.println("Tax: " + tax.toPlainString());
        System.out.println("Total: " + total.toPlainString());
    }
}
```

Output:

```text
Subtotal: 59.97
Tax: 4.80
Total: 64.77
```

Subtotal multiplication is exact: `19.99 × 3 = 59.97`. Unrounded tax is `59.97 × 0.08 = 4.7976`; setting scale 2 with `HALF_UP` gives `4.80`.

This is a technical illustration. Real systems must comply with tax regulations and rounding rules applicable to each transaction type; some round per line item, while others sum lines first and then round.

### 10.1. Line-Level Rounding vs. Total-Level Rounding Can Differ

Suppose there are multiple small lines. The following two policies can produce different results:

1. Round each line then sum.
2. Sum exact values of all lines then round once.

```java
BigDecimal line1 = new BigDecimal("0.005");
BigDecimal line2 = new BigDecimal("0.005");

BigDecimal eachRounded =
        line1.setScale(2, RoundingMode.HALF_UP)
        .add(line2.setScale(2, RoundingMode.HALF_UP));

BigDecimal totalRounded =
        line1.add(line2).setScale(2, RoundingMode.HALF_UP);

System.out.println(eachRounded); // 0.02
System.out.println(totalRounded); // 0.01
```

Different results:

- Each line `0.005` rounds to `0.01`, totaling `0.02`.
- Exact sum `0.010` rounds to `0.01`.

There is no single right policy for every business domain. Agree on rounding timing during design and testing.

## 11. Parsing Locale-Specific Decimal Input

`BigDecimal(String)` uses a dot as the decimal separator in its numeric syntax. Users, however, may enter numbers according to locale:

- Vietnamese locale typically uses a comma as the decimal separator and a dot as the thousands separator by formatting convention.
- US locale typically uses a dot as the decimal separator and a comma as the thousands separator.

Do not arbitrarily replace commas and dots, since a string like `"1.234"` can mean different things depending on locale.

Use `NumberFormat`/`DecimalFormat` with `setParseBigDecimal(true)` when locale-aware parsing is needed:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParseException;
import java.util.Locale;

public class LocalizedNumberInput {
    public static void main(String[] args) throws ParseException {
        NumberFormat numberFormat =
                NumberFormat.getNumberInstance(Locale.GERMANY);

        DecimalFormat decimalFormat = (DecimalFormat) numberFormat;
        decimalFormat.setParseBigDecimal(true);

        BigDecimal amount =
                (BigDecimal) decimalFormat.parse("1.234,56");

        System.out.println(amount.toPlainString()); // 1234.56
    }
}
```

In real applications, handle partial string parsing or malformed input per UI requirements. For standard data interchange APIs, dot-decimal conventions like JSON are simpler; preserve decimal tokens and deserialize directly into `BigDecimal` with an appropriate library.

## 12. Using `BigDecimal` with Databases

In relational databases, `DECIMAL` or `NUMERIC` types are commonly used for exact decimal values with declared precision and scale.

Schema example:

```sql
CREATE TABLE product_price (
    product_id BIGINT PRIMARY KEY,
    price DECIMAL(19, 2) NOT NULL
);
```

In JDBC, use `setBigDecimal` and `getBigDecimal`:

```java
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

static void updatePrice(
        PreparedStatement statement,
        long productId,
        BigDecimal price
) throws SQLException {
    statement.setBigDecimal(1, price);
    statement.setLong(2, productId);
    statement.executeUpdate();
}

static BigDecimal readPrice(ResultSet resultSet) throws SQLException {
    return resultSet.getBigDecimal("price");
}
```

The code assumes the SQL statement has placeholders in the matching parameter order. In real systems, always use parameterized statements; do not concatenate values into SQL strings.

### 12.1. Matching Scale to the Schema

If the column is `DECIMAL(19, 2)`, the application must decide how to handle values with more than two decimal places:

```java
BigDecimal input = new BigDecimal("12.345");

BigDecimal amountForStorage =
        input.setScale(2, RoundingMode.HALF_UP);
```

Some database engines have rules to round or reject values when storing into the column. Do not rely on implicit database behavior; define rules in the business layer and ensure the schema aligns.

### 12.2. Do Not Use `FLOAT`/`DOUBLE` Columns for Money Requiring Exactness

If a column stores monetary values using an approximate floating-point type, reading them back into `BigDecimal` cannot recover the original decimal data. Choose exact storage types such as `DECIMAL`/`NUMERIC` from the start when business requirements demand it.

## 13. Designing Functions and APIs with `BigDecimal`

### 13.1. Accept and Return `BigDecimal` End-to-End

```java
static BigDecimal calculateDiscount(
        BigDecimal price,
        BigDecimal rate
) {
    return price.multiply(rate);
}
```

If a system already uses `BigDecimal`, maintain this type across service and repository layers. Converting to `double` and back can inject binary errors into the calculation chain.

### 13.2. Check Null and Negative Values per Business Rules

`BigDecimal` does not decide on its own whether negative values are valid. For example, product prices are usually non-negative, while adjustments or refunds may carry negative signs.

```java
static BigDecimal requireNonNegative(BigDecimal value) {
    if (value == null) {
        throw new IllegalArgumentException("value is required");
    }
    if (value.signum() < 0) {
        throw new IllegalArgumentException("value must be non-negative");
    }
    return value;
}
```

`signum()` returns:

- `-1` if the value is negative.
- `0` if equal to 0.
- `1` if the value is positive.

The helper above only illustrates validation. Rules for each data item must follow the business domain.

### 13.3. Do Not Use `doubleValue()` for Exact Comparisons

```java
BigDecimal amount = new BigDecimal("0.10");

// Not recommended if the goal is exact decimal comparison:
if (amount.doubleValue() == 0.10) {
    // ...
}
```

Converting to `double` puts the data back into an approximate model. Use `compareTo`:

```java
if (amount.compareTo(new BigDecimal("0.10")) == 0) {
    // Numeric value equals 0.10
}
```

### 13.4. Keep Rounding Rules in an Intentional Central Place

Instead of letting each class round arbitrarily, you can define explicit rules:

```java
static final int MONEY_SCALE = 2;
static final RoundingMode MONEY_ROUNDING = RoundingMode.HALF_UP;

static BigDecimal normalizeMoney(BigDecimal amount) {
    return amount.setScale(MONEY_SCALE, MONEY_ROUNDING);
}
```

The name `MONEY_ROUNDING` here is only an example. A product may have different rules depending on currency, transaction type, country, contract, or accounting rules. Do not assume every currency has two decimal places.

## 14. When Should You Avoid Choosing `BigDecimal`?

`BigDecimal` solves decimal exactness needs, but has its own costs and limitations:

- Objects typically use more memory and processing overhead than primitive `double`.
- Operations allocate new objects due to immutability.
- Scale, precision, and rounding must be managed explicitly.
- There is no `NaN` or infinity like floating-point numbers; non-finite data needs a separate model.
- If the domain only needs integers, `long` or `int` is simpler.

### 14.1. Using Integers in the Smallest Unit When Appropriate

A system handling money solely in a fixed smallest unit can store `long`:

```java
long priceInCents = 1999;
long quantity = 3;
long totalInCents = priceInCents * quantity;

System.out.println(totalInCents); // 5997
```

This approach has the advantages of speed and avoiding floating-point error. However, you must manage:

- Whether the stored unit is cents, dong, xu, or another smallest unit.
- Overflow when multiplying or adding.
- Exchange rate conversions and decimal ratios.
- Division rules, rounding, and currencies with different units.

When calculating ratios, interest rates, or conversions with many decimal places, `BigDecimal` is generally more flexible.

### 14.2. Using `double` in Approximate Models

For example, calculating distance, graphics, or simulation:

```java
double distance = Math.sqrt(x * x + y * y);
```

You do not need to convert all these calculations to `BigDecimal` if the requirement is an approximate result under the floating-point model.

**Choose data types according to data semantics**, not the idea that one type is always superior to the other.

## 15. Common Mistakes

### Mistake 1. Initializing from `double`

```java
BigDecimal price = new BigDecimal(0.1);
```

This captures the exact binary value of the double. For business decimals, use:

```java
BigDecimal price = new BigDecimal("0.1");
```

### Mistake 2. Forgetting to Reassign Operation Results

```java
BigDecimal total = new BigDecimal("10.00");
total.add(new BigDecimal("5.00")); // Result is ignored
```

Fix:

```java
total = total.add(new BigDecimal("5.00"));
```

### Mistake 3. Using `equals` When Numeric Comparison Is Intended

```java
new BigDecimal("1.0").equals(new BigDecimal("1.00")); // false
```

Use `compareTo(...) == 0` if scale differences do not matter.

### Mistake 4. Dividing Without Specifying Rounding

```java
BigDecimal.ONE.divide(new BigDecimal("3")); // ArithmeticException
```

If business rules accept bounding the scale:

```java
BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
```

### Mistake 5. Calling `setScale` Without Saving the Result

```java
amount.setScale(2, RoundingMode.HALF_UP);
```

You must save the returned value because `BigDecimal` is immutable.

### Mistake 6. Confusing `precision` with `scale`

`precision` is the number of significant digits in the unscaled value; `scale` specifies the decimal point position. `setScale(2)` does not mean "keep two significant digits".

### Mistake 7. Rounding Across Multiple Layers Without a Policy

One layer rounding per line, another layer rounding the total, and the UI layer formatting again can cause discrepancies. Clearly define where and when rounding happens.

### Mistake 8. Passing Through `double` Mid-Calculation

`BigDecimal -> double -> BigDecimal` can reintroduce binary errors. Keep `BigDecimal` throughout the calculation path when decimal exactness is needed.

### Mistake 9. Using a Hardcoded System Scale to Format Money

Not every currency has two decimal places. Digit counts depend on the currency and business rules. Do not default to `setScale(2)` for every financial value.

## 16. Comprehensive Practice Example

Problem: calculate the amount after discount. Inputs include original price, quantity, and discount rate; the result requires two decimal places under the example's `HALF_UP` rule.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DiscountCalculator {

    private static final int MONEY_SCALE = 2;
    private static final RoundingMode ROUNDING = RoundingMode.HALF_UP;

    static BigDecimal calculate(
            String unitPriceText,
            long quantity,
            String discountRateText
    ) {
        BigDecimal unitPrice = new BigDecimal(unitPriceText);
        BigDecimal discountRate = new BigDecimal(discountRateText);
        BigDecimal count = BigDecimal.valueOf(quantity);

        if (unitPrice.signum() < 0 || discountRate.signum() < 0
                || discountRate.compareTo(BigDecimal.ONE) > 0
                || quantity < 0) {
            throw new IllegalArgumentException("Invalid input");
        }

        BigDecimal subtotal = unitPrice.multiply(count);
        BigDecimal discount = subtotal.multiply(discountRate);

        return subtotal.subtract(discount)
                .setScale(MONEY_SCALE, ROUNDING);
    }

    public static void main(String[] args) {
        BigDecimal result = calculate("19.99", 3, "0.10");
        System.out.println(result.toPlainString()); // 53.97
    }
}
```

Explanation:

1. Unit price `19.99` is parsed directly from a decimal string.
2. Quantity `3` converts from `long` to `BigDecimal` via `valueOf`.
3. Subtotal is `59.97`.
4. Discount rate `0.10` means 10%; discount is `5.997`.
5. Amount after discount is `53.973`.
6. Applying `setScale(2, HALF_UP)` yields `53.97`.

The code assumes inputs have been syntax-validated and the rounding policy is approved for the business domain. In real products, validate quantity limits, unit prices, rates, and currency rules per domain.

## 17. Practice Exercises

**Exercise 1.** What is the output of this snippet?

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b));
```

**Answer:** `0.3`. Both operands are constructed from exact decimal strings.

**Exercise 2.** Why do these two expressions differ?

```java
new BigDecimal(0.1)
new BigDecimal("0.1")
```

**Answer:** The first receives an already-approximated binary double value and represents that exact value. The second directly parses the decimal `0.1`.

**Exercise 3.** What value is printed?

```java
BigDecimal amount = new BigDecimal("12.345");
amount.setScale(2, RoundingMode.HALF_UP);
System.out.println(amount);
```

**Answer:** `12.345`. `setScale` returns a new object; the result was not reassigned.

**Exercise 4.** Compare:

```java
BigDecimal a = new BigDecimal("5.0");
BigDecimal b = new BigDecimal("5.00");
```

**Answer:** `a.equals(b)` is `false`, while `a.compareTo(b) == 0` is `true`.

**Exercise 5.** What happens?

```java
BigDecimal.ONE.divide(new BigDecimal("8"));
```

**Answer:** The division has a terminating decimal result `0.125`, so exact division succeeds without a rounding mode.

**Exercise 6.** What happens?

```java
BigDecimal.ONE.divide(new BigDecimal("6"));
```

**Answer:** Repeating non-terminating decimal result; exact division without a rounding rule throws `ArithmeticException`.

**Exercise 7.** You need to verify a value can be represented exactly with two decimal places without rounding. What do you use?

**Answer:** `amount.setScale(2, RoundingMode.UNNECESSARY)`. If rounding is required, Java throws `ArithmeticException`.

**Exercise 8.** A system sums monetary amounts using `double`, then calls `BigDecimal.valueOf(total)`. Does this guarantee business exactness?

**Answer:** No. Errors may have already appeared in the prior `double` operations. Construct `BigDecimal` from the original decimal inputs and keep this type throughout the entire calculation.

## 18. Key Takeaways and Official References

**Principles to remember:**

1. Use `BigDecimal` when exact decimal numbers and controlled rounding rules are needed.
2. Prefer `new BigDecimal("...")` for decimal input; use `BigDecimal.valueOf(long)` for integers.
3. Avoid `new BigDecimal(double)` when ideal decimal values are desired.
4. `BigDecimal` is immutable; always use the return values of `add`, `multiply`, `setScale`, and other methods.
5. `equals` considers scale; `compareTo` compares numeric value.
6. `divide` without a rounding mode succeeds only when the quotient has a terminating decimal representation.
7. `scale` is the number of digits to the right of the decimal point; `precision` is the number of significant digits in the unscaled value.
8. Rounding rules must come from business requirements; do not choose them arbitrarily.
9. Keep `BigDecimal` consistently across input, business logic, and persistence layers when exactness is required.
10. Use `DECIMAL`/`NUMERIC` and JDBC `setBigDecimal`/`getBigDecimal` when working with exact decimal data in databases.

### Official Documentation

- [JDK 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): constructors, operations, scale, precision, rounding, equals, and compareTo.
- [JDK 17 API — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): meanings of rounding modes.
- [JDK 17 API — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): precision limits and rounding mode for operations.
- [JLS 17 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): characteristics of floating-point types and representable values.
- [JDK 17 API — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): JDBC parameter binding methods, including `setBigDecimal`.
- [JDK 17 API — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): reading `BigDecimal` values via `getBigDecimal`.

**Selection Principle:** If decimal values must remain exact relative to input data and business rules, use `BigDecimal` from end to end. Choose scale and rounding mode intentionally, do not pass through `double` mid-way, and use `compareTo` when numeric comparison is needed.
