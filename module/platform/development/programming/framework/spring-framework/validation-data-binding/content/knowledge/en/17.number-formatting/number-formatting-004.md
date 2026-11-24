# BigDecimal, Precision, and Rounding Rules

`java.math.BigDecimal` represents signed decimal numbers with arbitrary precision. It is essential when calculating money, taxes, ratios, unit prices, measurements, and other data where binary floating-point errors or ambiguous rounding can alter business outcomes.

However, using `BigDecimal` does not automatically guarantee every calculation is correct. Developers still need to decide:

- Should values be constructed from a decimal string or from a `double`?
- How do `precision` and `scale` differ?
- Should two numbers with the same numeric value but different decimal digit counts be treated as equal?
- When division yields a non-terminating decimal, where do we round and by which rule?
- Should we use `MathContext` or `setScale(...)`?
- Should we round after each operation or retain precision until the final step?
- How do we preserve rules as data moves through JDBC, JSON, Spring binding, and the database?

This article uses Java 17+ to explain the arithmetic mechanics, complete runnable examples, expected outputs, and how to design rounding rules in applications.

## 1. Why do we need BigDecimal?

`float` and `double` store floating-point numbers using IEEE 754 binary representation. Many finite decimal fractions have no exact finite binary representation. Consequently, a visible value like `0.1` cannot be stored accurately as a `double`.

~~~java
System.out.println(0.1 + 0.2);
~~~

Typical output:

~~~text
0.30000000000000004
~~~

In financial operations, accumulating inaccuracies across multiple calculations can cause monetary discrepancies. `BigDecimal` stores a value using an unscaled integer and a scale, thereby representing finite decimal numbers such as `0.1`, `12.3400`, or `999999999999.99` exactly without converting them to binary floating-point.

Example:

~~~java
BigDecimal price = new BigDecimal("0.10");
BigDecimal tax = new BigDecimal("0.20");
BigDecimal total = price.add(tax);

System.out.println(total); // 0.30
~~~

The arithmetic result is exact and the scale matches the operands. `BigDecimal` does not restrict significant digits to a fixed format like `double`, though practical limits still exist for memory, execution time, `int` scale bounds, and storage size.

**First rule:** if the data source is already a decimal number written in digits, construct `BigDecimal` from that decimal representation itself, typically a `String` or a `BigInteger` with scale.

## 2. Internal structure: unscaledValue and scale

A `BigDecimal` is defined by:

- `unscaledValue`: a signed integer value.
- `scale`: the number of decimal digits, which may be positive, zero, or negative.

Formula:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Examples:

| Representation | Unscaled value | Scale | Value |
| --- | ---: | ---: | ---: |
| `12.34` | 1234 | 2 | 1234 × 10⁻² |
| `12.3400` | 123400 | 4 | 123400 × 10⁻⁴ |
| `1234` | 1234 | 0 | 1234 |
| `1.23E+3` | 123 | -1 | 123 × 10¹ = 1230 |
| `0.00123` | 123 | 5 | 123 × 10⁻⁵ |

You can inspect the structure directly:

~~~java
BigDecimal amount = new BigDecimal("12.3400");

System.out.println(amount.unscaledValue()); // 123400
System.out.println(amount.scale());         // 4
System.out.println(amount.precision());     // 6
~~~

An important point: **negative scale is valid**. For example, `new BigDecimal("1.23E+3")` can have a negative scale; not every `BigDecimal` has a scale equal to the number of digits after the decimal point in standard printing.

`BigDecimal` is immutable. Operations like `add`, `multiply`, `setScale`, and `round` return a new `BigDecimal`; they never mutate the original object. Always reassign the result:

~~~java
BigDecimal value = new BigDecimal("1.235");
value.setScale(2, RoundingMode.HALF_UP); // Result discarded: value is still 1.235.

value = value.setScale(2, RoundingMode.HALF_UP); // value is now 1.24.
~~~

## 3. Constructing BigDecimal properly

### 3.1. Prefer the String constructor

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("123.4500");
BigDecimal c = new BigDecimal("-0.005");
~~~

`String` lets `BigDecimal` parse the decimal representation directly. `new BigDecimal("0.1")` produces the exact decimal value one-tenth with scale 1.

This is the right approach when reading from forms, CSV files, configuration, databases, or an API whose contract represents numbers as strings.

### 3.2. Avoid the BigDecimal(double) constructor for exact decimal values

~~~java
BigDecimal wrong = new BigDecimal(0.1);
System.out.println(wrong);
~~~

The output shows the exact binary `double` value received, not the decimal value a reader typically expects:

~~~text
0.1000000000000000055511151231257827021181583404541015625
~~~

The cause is not `BigDecimal` rounding incorrectly. This constructor converts **the exact binary double value** into its exact decimal equivalent. The `double` itself never represented one-tenth accurately.

### 3.3. When forced to accept a double, consider valueOf

~~~java
BigDecimal value = BigDecimal.valueOf(0.1);
System.out.println(value); // 0.1
~~~

`BigDecimal.valueOf(double)` converts using the canonical string representation of `Double.toString(double)`. This usually produces the result users expect compared to the direct `new BigDecimal(double)` constructor.

Even so, if the input source is originally decimal digits, **do not convert through double first and then call valueOf**. The better path is to read a `String` from the start.

### 3.4. Do not use new BigDecimal(float) for money

~~~java
float rate = 0.1f;
BigDecimal value = new BigDecimal(rate);
~~~

`float` has lower precision than `double`; inaccuracies already occurred before creating `BigDecimal`. `valueOf` has no `float` overload; casting to `double` only widens the already-stored `float` value without recovering the original decimal number.

### 3.5. Validate values before construction

Empty or non-numeric strings throw `NumberFormatException`:

~~~java
BigDecimal amount = new BigDecimal("abc"); // NumberFormatException
~~~

In input-handling code, validate or let the converter report errors clearly; never silently replace invalid data with 0. **Missing data**, **zero value**, and **unparseable value** are three distinct states.

## 4. Precision and scale: two different concepts

`precision()` returns the number of digits in the unscaled value; for non-zero values, it is the number of significant digits in the decimal representation. The precision of zero is 1.

`scale()` describes the number of digits to the right of the decimal point in the internal representation; positive scale is the count of fractional digits, zero scale has no fractional part, and negative scale represents multiples of powers of 10.

Example:

~~~java
BigDecimal a = new BigDecimal("123.45");
BigDecimal b = new BigDecimal("123.4500");
BigDecimal c = new BigDecimal("1000");
BigDecimal d = new BigDecimal("1.23E+3");

System.out.println(a.precision() + "/" + a.scale()); // 5/2
System.out.println(b.precision() + "/" + b.scale()); // 7/4
System.out.println(c.precision() + "/" + c.scale()); // 4/0
System.out.println(d.precision() + "/" + d.scale()); // 3/-1
~~~

| Value | Precision | Scale |
| --- | ---: | ---: |
| `123.45` | 5 | 2 |
| `123.4500` | 7 | 4 |
| `1000` | 4 | 0 |
| `1.23E+3` | 3 | -1 |

The first two values are numerically equal yet differ in precision/scale and representation. This matters greatly when comparing, storing data, serializing, or checking a `DECIMAL(p,s)` database schema.

### DECIMAL(p,s) in databases

Typically:

- `p` is the maximum precision (total number of digits).
- `s` is the declared scale (number of digits after the decimal point).

For example, `DECIMAL(12,2)` allows at most 12 digits total, with 2 fractional digits, leaving at most 10 integer digits. Values exceeding bounds may be rejected or converted depending on database/driver behavior.

`BigDecimal` in Java does not force every value to have scale 2. Applications should validate and normalize at the domain/persistence boundary per contract, rather than letting the database silently round without Java code knowing.

## 5. Equals and compareTo: equality in two senses

`BigDecimal.equals(Object)` compares **value and representation (scale)**. `compareTo(BigDecimal)` compares numeric value.

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));         // false
System.out.println(a.compareTo(b) == 0); // true
~~~

Both represent the number one, yet `1.0` has scale 1 and `1.00` has scale 2. Therefore:

- Use `compareTo(...) == 0` when comparing two numbers by mathematical value.
- Use `equals(...)` when scale is also part of the representation's meaning.
- Be careful when using `BigDecimal` as a `HashMap`/`HashSet` key: `equals` and `hashCode` factor in scale, so `1.0` and `1.00` are different keys.

If the domain treats `1.0` and `1.00` as identical, normalize representations consistently before using them as keys or comparing. For example, `stripTrailingZeros()` can normalize trailing decimal zeros, though the result may carry a negative scale; do not assume it always returns scale 0 or 2.

## 6. Basic arithmetic and resulting scale

`BigDecimal` supports exact arithmetic operations:

~~~java
BigDecimal a = new BigDecimal("10.25");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.add(b));      // 12.25
System.out.println(a.subtract(b)); // 8.25
System.out.println(a.multiply(b)); // 20.5000
~~~

Preferred scale of exact results follows these rules:

| Operation | Preferred Scale |
| --- | --- |
| `add` | Larger of the two operands' scales |
| `subtract` | Larger of the two operands' scales |
| `multiply` | Sum of the two operands' scales |
| `divide` | Dividend's scale minus divisor's scale (in exact division when applicable) |

Because `multiply` adds scales, `10.25` (scale 2) times `2.00` (scale 2) yields the representation `20.5000` (scale 4). This is not a bug; it preserves scale information across the operation.

**Do not automatically round after every addition or multiplication.** Operations without a `MathContext` generally compute the exact result and retain scale under preferred scale rules. The decision to reduce scale should live at an agreed business boundary, such as finalizing a payable amount.

## 7. Dividing decimals: why does ArithmeticException happen?

Some divisions have finite decimal results:

~~~java
new BigDecimal("1").divide(new BigDecimal("4")); // 0.25
~~~

But `1 / 3` has a non-terminating repeating decimal expansion. `BigDecimal` does not arbitrarily pick a digit count to truncate at, because that choice is a business decision:

~~~java
new BigDecimal("1").divide(new BigDecimal("3"));
// ArithmeticException: Non-terminating decimal expansion
~~~

You must supply a scale/rounding rule or precision context:

~~~java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal byScale = one.divide(
        three, 2, RoundingMode.HALF_UP);

BigDecimal byContext = one.divide(
        three, new MathContext(4, RoundingMode.HALF_UP));

System.out.println(byScale);   // 0.33
System.out.println(byContext); // 0.3333
~~~

The two results differ because the rules differ:

- `divide(divisor, 2, roundingMode)` fixes **scale 2**, i.e., two digits after the decimal point.
- `divide(divisor, MathContext(4, ...))` limits **precision to 4 significant digits**, not four digits after the decimal point.

Do not pick an overload merely because it is shorter. Determine whether the requirement calls for fixed decimal places or fixed significant digits.

### Dividing with the current scale

~~~java
a.divide(b, RoundingMode.HALF_UP)
~~~

This overload uses the scale of `this` as the result scale. In many monetary scenarios, using an overload with an explicit scale is easier to read and less error-prone.

### Division by zero

`BigDecimal` does not represent infinity like floating-point numbers do. Dividing by zero throws `ArithmeticException`. Validate the divisor before computing or let the caller translate the exception into an appropriate business error.

## 8. RoundingMode: eight ways to handle discarded digits

`java.math.RoundingMode` has eight modes. Choosing the wrong mode can introduce systematic bias or violate financial regulations.

| RoundingMode | Rule |
| --- | --- |
| `UP` | Rounds away from zero; increments magnitude if any discarded digit is non-zero. |
| `DOWN` | Truncates toward zero; discards the remainder. |
| `CEILING` | Rounds toward positive infinity; for negative numbers this may be closer to zero. |
| `FLOOR` | Rounds toward negative infinity; for negative numbers this may be farther from zero. |
| `HALF_UP` | Nearest neighbor; ties round away from zero. |
| `HALF_DOWN` | Nearest neighbor; ties round toward zero. |
| `HALF_EVEN` | Nearest neighbor; ties round to the even final digit (banker's rounding). |
| `UNNECESSARY` | Rounding disallowed; throws `ArithmeticException` if precision would be lost. |

### Positive and negative examples

With scale 2:

~~~java
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP);   // 2.35
new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN); // 2.34
new BigDecimal("-2.345").setScale(2, RoundingMode.HALF_UP);  // -2.35
new BigDecimal("-2.345").setScale(2, RoundingMode.DOWN);     // -2.34
new BigDecimal("-2.345").setScale(2, RoundingMode.FLOOR);    // -2.35
~~~

`HALF_EVEN` does not always "round down." It picks the nearest result; only when equidistant between two choices does it pick the value whose last retained digit is even. This can reduce cumulative bias across large volumes of calculations, though it should only be used when business rules permit.

### Example checking HALF_EVEN on both sides

~~~java
System.out.println(
        new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN));
System.out.println(
        new BigDecimal("2.355").setScale(2, RoundingMode.HALF_EVEN));
~~~

Output:

~~~text
2.34
2.36
~~~

In the first case, the last retained digit is 4 (even), whereas in the second case it is 5 (odd), so the second result is incremented to 6.

### UNNECESSARY to detect wrong scale

~~~java
BigDecimal value = new BigDecimal("12.340");
BigDecimal exact = value.setScale(2, RoundingMode.UNNECESSARY);
System.out.println(exact); // 12.34
~~~

Reducing scale from 3 to 2 does not alter the value because the discarded digit is 0. However:

~~~java
new BigDecimal("12.345")
        .setScale(2, RoundingMode.UNNECESSARY);
~~~

throws `ArithmeticException` because a non-zero digit must be discarded. This is useful when a contract requires values to have at most two decimal digits and the application wants to **reject** over-scaled input instead of silently rounding it.

## 9. MathContext: precision and rounding for operations

`MathContext` encapsulates two settings:

- `precision`: number of significant digits in the result.
- `roundingMode`: rounding rule if the exact result has too many digits.

Example:

~~~java
MathContext mc = new MathContext(5, RoundingMode.HALF_EVEN);

BigDecimal result = new BigDecimal("123.4567").round(mc);
System.out.println(result); // 123.46
~~~

Precision 5 means retaining 5 significant digits, not scale 5. The result `123.46` has precision 5 and scale 2.

`MathContext.DECIMAL32`, `DECIMAL64`, and `DECIMAL128` are useful configurations matching standard decimal precisions; however, they do not automatically impose database-style scale limits. For money needing two digits after the decimal point, `setScale(2, ...)` expresses the requirement more directly than `MathContext(2, ...)`.

### MathContext.UNLIMITED

`MathContext.UNLIMITED` has precision 0. This performs unlimited-precision operations and computes exact results whenever a finite representation exists. For divisions without a finite decimal expansion, it still will not generate an infinite string; results that cannot be represented exactly throw `ArithmeticException`.

### Applying MathContext per operation

~~~java
MathContext mc = new MathContext(6, RoundingMode.HALF_EVEN);

BigDecimal a = new BigDecimal("123.456");
BigDecimal b = new BigDecimal("7.89");

BigDecimal sum = a.add(b, mc);
BigDecimal product = a.multiply(b, mc);
BigDecimal quotient = a.divide(b, mc);
~~~

When passing a context, each operation produces a result using the chosen precision/rounding. That means applying context at every step can produce intermediate rounding drift compared to computing steps exactly and rounding at the end. Which option is right depends on the applicable accounting/pricing rules.

## 10. setScale, round, and stripTrailingZeros

These three APIs are frequently mixed up:

### setScale

Use when you need a specific number of decimal digits:

~~~java
BigDecimal price = new BigDecimal("19.987");
BigDecimal amount = price.setScale(2, RoundingMode.HALF_UP);

System.out.println(amount); // 19.99
~~~

### round(MathContext)

Use when you need a specific number of significant digits:

~~~java
BigDecimal value = new BigDecimal("12345.67");
BigDecimal rounded = value.round(
        new MathContext(4, RoundingMode.HALF_UP));

System.out.println(rounded); // 1.235E+4
~~~

When displaying, if you want to avoid scientific notation, you can use `toPlainString()`; do not turn output formatting into another calculation or rounding pass.

### stripTrailingZeros

Use when you want to remove trailing decimal zeros without changing the numeric value:

~~~java
BigDecimal value = new BigDecimal("12.3400");
BigDecimal stripped = value.stripTrailingZeros();

System.out.println(stripped); // 12.34
System.out.println(stripped.scale()); // 2
~~~

For `1000`, `stripTrailingZeros()` can yield a negative-scale representation, such as printing in scientific form. If you want a plain string, use `toPlainString()`; if you want a fixed scale (e.g., two digits), use `setScale(2, ...)` instead of `stripTrailingZeros()`.

## 11. Complete Java 17+ example: pricing, VAT, and rounding

The following program runs with no external libraries. It demonstrates:

- Creating monetary amounts from strings.
- Multiplying quantity by unit price.
- Computing VAT by rate.
- Rounding amounts to two digits with `HALF_EVEN`.
- Comparing `equals` and `compareTo`.
- Distinguishing the `double` constructor from `valueOf`.
- Dividing repeating decimals with an explicit scale.

### Structure

~~~text
bigdecimal-demo/
└── BigDecimalDemo.java
~~~

### BigDecimalDemo.java

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDemo {

    private static BigDecimal money(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_EVEN);
    }

    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.99");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal vatRate = new BigDecimal("0.10");

        BigDecimal subtotal = unitPrice.multiply(quantity);
        BigDecimal vatExact = subtotal.multiply(vatRate);
        BigDecimal vat = money(vatExact);
        BigDecimal total = money(subtotal.add(vat));

        System.out.println("subtotal=" + subtotal.toPlainString());
        System.out.println("vatExact=" + vatExact.toPlainString());
        System.out.println("vatRounded=" + vat.toPlainString());
        System.out.println("total=" + total.toPlainString());

        BigDecimal first = new BigDecimal("1.0");
        BigDecimal second = new BigDecimal("1.00");

        System.out.println("equals=" + first.equals(second));
        System.out.println("compareTo="
                + (first.compareTo(second) == 0));

        System.out.println("fromString="
                + new BigDecimal("0.1").toPlainString());
        System.out.println("fromDouble="
                + new BigDecimal(0.1).toPlainString());
        System.out.println("fromValueOf="
                + BigDecimal.valueOf(0.1).toPlainString());

        BigDecimal third = BigDecimal.ONE.divide(
                new BigDecimal("3"),
                4,
                RoundingMode.HALF_UP);
        System.out.println("oneThird=" + third.toPlainString());

        BigDecimal significant = new BigDecimal("12345.67").round(
                new MathContext(4, RoundingMode.HALF_UP));
        System.out.println("fourSignificantDigits="
                + significant.toPlainString());
    }
}
~~~

### Compile and run

JDK 17+:

~~~bash
javac BigDecimalDemo.java
java BigDecimalDemo
~~~

Exact stdout:

~~~text
subtotal=59.97
vatExact=5.9970
vatRounded=6.00
total=65.97
equals=false
compareTo=true
fromString=0.1
fromDouble=0.1000000000000000055511151231257827021181583404541015625
fromValueOf=0.1
oneThird=0.3333
fourSignificantDigits=12350
~~~

Explanation:

1. `19.99 × 3 = 59.97` is computed exactly. Since the operands have scales 2 and 0, the result has scale 2.
2. VAT is `59.97 × 0.10 = 5.9970`. This is the exact result, scale 4 from adding both scales.
3. `money(...)` applies the two-digit rounding rule using `HALF_EVEN`. `5.9970` becomes `6.00`.
4. Total `59.97 + 6.00 = 65.97`, normalized to two digits.
5. `1.0` and `1.00` have the same numeric value yet different representations; `equals` returns `false`, while `compareTo == 0` returns `true`.
6. The `double` constructor exposes the exact binary double value; `String` and `valueOf` in the example both create the decimal value `0.1`.
7. `1 / 3` is rounded to scale 4 as `0.3333`.
8. `MathContext(4, HALF_UP)` keeps four significant digits of `12345.67`, producing the equivalent value `12350`; `toPlainString()` prints it in non-scientific form.

This is a standalone program requiring no Maven, Spring, or database. Changing the scale, rounding mode, or inputs changes stdout according to the corresponding rules.

## 12. Where to round in a business workflow?

A decision just as important as the rounding mode is **when to round**. Do not arbitrarily round every intermediate value.

Sales example:

~~~text
Unit price × quantity
        |
        v
   Line subtotal
        |
        v
  Discount / tax
        |
        v
   Order total
        |
        v
Round per payment rules
~~~

There are at least two common policies:

- **Per-line rounding:** compute line amounts/taxes for each line and sum the rounded results.
- **Exact sum then round total:** retain per-line precision, sum the values, and round only at the total level.

The two approaches can yield different totals. There is no single right rule for every system; follow financial contracts, tax regulations, country/currency rules, and partner reconciliation practices. Document the rule clearly so frontend, backend, reports, and database never round differently.

### Currencies do not always have two decimal digits

Some currencies have different fraction digit counts, and cash-payment rounding rules may differ from ledger accounting rules. Do not hardcode `setScale(2)` for every currency if the application supports multiple currencies. Use currency metadata (e.g., `Currency.getDefaultFractionDigits()` if aligned with policy) and explicit business configuration; still distinguish ledger digits from cash rounding steps.

### Discounts and rates

Percentage rates may require higher precision than monetary units:

~~~java
BigDecimal discountRate = new BigDecimal("0.075");
BigDecimal discount = subtotal.multiply(discountRate);
~~~

Do not round `discountRate` down to two decimal places when a 7.5% rate must be preserved accurately. Usually you keep precision for the rate, compute the discount amount, and then round to the currency unit at the designated point.

## 13. BigDecimal with input data, databases, and JSON

### 13.1. Form/API input

When users enter numbers as strings, convert directly:

~~~java
BigDecimal amount = new BigDecimal(rawAmount);
~~~

In Spring MVC, default converters support `String` to `BigDecimal`; for custom rules, register a converter or validator. Always handle `NumberFormatException`/binding errors instead of replacing bad input with zero.

### 13.2. JDBC and DECIMAL/NUMERIC

JDBC provides APIs such as `PreparedStatement.setBigDecimal(...)` and `ResultSet.getBigDecimal(...)`:

~~~java
preparedStatement.setBigDecimal(1, amount);
BigDecimal loaded = resultSet.getBigDecimal("amount");
~~~

Use `DECIMAL(p,s)` or `NUMERIC(p,s)` columns matching domain limits. Check overflow and scale before writing, as databases may reject or convert values depending on engine/configuration. Never rely solely on Java object creation succeeding to conclude data fits the schema.

### 13.3. JSON numbers and strings

JSON has a number token, though frameworks may parse through intermediate types and differing configurations. If exact decimal preservation is required, configure serializers/deserializers to map directly to `BigDecimal` and test round-trips. For APIs that must preserve exact representation (such as user-submitted decimal digit counts), choose a controlled string contract:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Strings preserve the `1234.50` representation across transport; however, format and length validation are needed. If the contract chooses JSON numbers, do not let a JavaScript client pass oversized values or excess precision through `Number` (IEEE 754 double) and expect the backend to recover the original number.

## 14. Common mistakes

1. **Using `new BigDecimal(0.1)`:** converts the exact binary `double` value, usually producing long trailing fractions. Use decimal strings or `BigDecimal.valueOf` when the source truly is a `double`.
2. **Using `double` in monetary calculations:** errors accumulate before converting to `BigDecimal`; switching types at the end cannot fix it.
3. **Confusing precision with scale:** `MathContext(2, ...)` gives two significant digits, not two decimal digits. Use `setScale(2, ...)` when two fractional digits are needed.
4. **Using `equals` for value comparison:** `1.0` does not `equals` `1.00`. Use `compareTo == 0` when only numeric value matters.
5. **Dividing without specifying rounding:** `1/3` has no finite decimal result; the exact overload throws `ArithmeticException`. Choose scale or `MathContext` explicitly.
6. **Using the wrong rounding mode:** `DOWN` rounds toward zero, which is not equivalent to `FLOOR`; for negative numbers the two differ.
7. **Rounding at every step without a rule:** intermediate rounding can accumulate and cause the total to diverge from end-of-calculation rounding.
8. **Forgetting to assign the result of `setScale`:** `BigDecimal` is immutable, so the call does not modify the old variable.
9. **Assuming every currency has scale 2:** monetary data and payment rules need proper metadata/policy.
10. **Calling `stripTrailingZeros` and assuming scale is always non-negative:** results can have negative scale; use `toPlainString` for printing and `setScale` when a contract mandates fixed scale.
11. **Rounding negatives without tests:** `HALF_UP`, `DOWN`, `FLOOR`, and `CEILING` behave differently for negative numbers.
12. **Storing `BigDecimal` without checking database precision/scale:** values may overflow `DECIMAL(p,s)` or lose precision at the persistence boundary.
13. **Confusing `canConvert`/parse with business validation:** parsing into `BigDecimal` only verifies numeric syntax; min/max, scale, and domain rules still need checks.
14. **Accepting scientific notation strings outside the contract:** `BigDecimal` accepts exponents, though UIs/APIs may forbid that format. Validate formats against the contract instead of relying on constructor defaults.

## 15. Decimal design checklist

Before introducing `BigDecimal` into a use case:

- Identify the data source and construction method; prefer `String`, avoid intermediate `double`.
- Define the value domain, maximum precision, and scale for each field.
- Distinguish value equality (`compareTo`) from representation equality (`equals`).
- Determine which operations must be exact and which divisions require rounding.
- Choose a rounding mode per business/legal rules and document it explicitly in code.
- Decide whether rounding occurs per line, per tax item, or on the total.
- Place rounding at meaningful boundaries; avoid arbitrary rounding at every step.
- Test negative numbers, zero, tie values, trailing zeros, division by zero, and non-terminating quotients.
- Verify compatibility with `DECIMAL(p,s)`, JSON, and the frontend.
- Record unit and currency alongside the value; `BigDecimal` only represents a number, not a currency unit.

**Remember:** `BigDecimal` provides exact decimal arithmetic and controlled rounding; choosing precision, scale, rounding mode, and rounding timing remains an application design responsibility.

### Official references

- [Java SE 17 — BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — RoundingMode API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)
- [Java SE 17 — MathContext API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html)
- [Java SE 17 — Currency API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html)
- [JDBC — PreparedStatement.setBigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html#setBigDecimal(int,java.math.BigDecimal))
