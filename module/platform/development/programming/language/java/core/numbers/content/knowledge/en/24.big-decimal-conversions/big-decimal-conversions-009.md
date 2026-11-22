# BigDecimal: Distinguishing Computed Value from Display Scale

In Java, when a `BigDecimal` calculation yields `13.000` but the UI needs to display `13.00`, the question to answer is: **does the numeric value need to change, or does only the number of displayed digits need to change?** These two needs can lead to different operations, and even different stored results and equality checks.

This lesson belongs to the **BigDecimal Conversions** topic and focuses on the boundary between **computed value**, **decimal representation/`scale`**, **rounding rules**, and **display strings**. Examples use Java 17+ and decimal input strings to avoid unnecessary `double` conversion errors.

## 1. Three Conceptual Layers to Distinguish

1. **Numeric value:** the mathematical quantity that `BigDecimal` represents; for example, `13`, `13.0`, and `13.00` all have the same numeric value.
2. **`BigDecimal` representation:** the integer pair `unscaledValue` and `scale`. Different ways of writing the same value can have different `scale`s. `scale` is a property of the object, not merely a font choice or screen formatting option.
3. **Presentation string:** the characters the user sees: `13`, `13.00`, `13,00`, `1,000.00`, or `1E+3`. These rules can depend on locale, units, product conventions, and the data consumer.

Internal formula of `BigDecimal`:

~~~text
numeric value = unscaledValue × 10^(-scale)
~~~

Examples:

| Initialization | Numeric Value | `unscaledValue()` | `scale()` | `toString()` |
|---|---:|---:|---:|---|
| `new BigDecimal("13")` | 13 | 13 | 0 | `13` |
| `new BigDecimal("13.0")` | 13 | 130 | 1 | `13.0` |
| `new BigDecimal("13.00")` | 13 | 1300 | 2 | `13.00` |
| `new BigDecimal("1.3E+1")` | 13 | 13 | 0 | `13` |
| `new BigDecimal("1E+3")` | 1000 | 1 | -3 | `1E+3` |

Note the `"1.3E+1"` row: `BigDecimal` parses the scientific string into a value with `unscaledValue = 13` and `scale = 0`, so the object's `toString()` is `13`. The original input string is not retained as a separate display label.

Two `BigDecimal` objects have the same **numeric value** when `compareTo() == 0`. The `equals()` method additionally requires equal `scale`:

~~~java
BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("12.300");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
~~~

Therefore, the statement "two numbers are equal" must specify **mathematically equal** or **equal in `BigDecimal` representation**.

## 2. Computed Value and Scale After Operations

`BigDecimal` supports exact decimal arithmetic (within operator, precision/rounding, and resource limits), yet **the result of an operation still has a `scale`**. For exact operations without `MathContext`, Java specifies preferred `scale` rules:

| Operation | Preferred `scale` |
|---|---|
| `a.add(b)` | `max(a.scale(), b.scale())` |
| `a.subtract(b)` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a.scale() + b.scale()` |
| Exact `a.divide(b)` | `a.scale() - b.scale()` if sufficient; division may require a larger scale to represent an exact quotient |
| `a.scaleByPowerOfTen(n)` | `a.scale() - n` and **numeric value multiplied by `10^n`** |

These rules describe the **representation of the result**; they do not automatically decide how many digits the UI must print. For divisions with non-terminating decimal results like `1 / 3`, `divide(BigDecimal)` without rounding can throw `ArithmeticException`. In that case, choose a `divide` overload with `scale`/`RoundingMode` or `MathContext` according to the calculation's semantics.

Example:

~~~java
BigDecimal quantity = new BigDecimal("12.30"); // scale 2
BigDecimal extra = new BigDecimal("0.700");   // scale 3
BigDecimal total = quantity.add(extra);

System.out.println(total);         // 13.000
System.out.println(total.scale()); // 3
~~~

The mathematical sum is **13**, while the result object is represented at **scale 3**. That the screen needs to display `13.00` is a different requirement from the addition just performed.

**`precision()` is not `scale()`:** `precision` is the number of digits in the unscaled part of the representation, whereas `scale` indicates the decimal order. For instance, `123.4500` has `precision = 7` and `scale = 4`. `MathContext(5)` sets a significant-digit limit for context-based operations; it does not mean displaying exactly 5 digits after the decimal point.

## 3. Which APIs Change Value, and Which Change Representation?

| Operation | Can Change **Numeric Value**? | Effect on `scale` and Display |
|---|---|---|
| `value.setScale(2)` | No, if representable exactly; otherwise throws an exception | Sets `scale` to 2 |
| `value.setScale(2, RoundingMode.HALF_UP)` | **Yes** when rounding is needed | `scale = 2`, may drop or increment value digits |
| `value.stripTrailingZeros()` | **No** | Strips trailing zeros; `scale` may decrease and become negative |
| `value.toString()` | **No** | Returns canonical string, may use scientific notation |
| `value.toPlainString()` | **No** | Returns exponent-free string, does not enforce a fixed number of decimal places |
| `DecimalFormat.format(value)` | Does not modify input object | Produces formatted string, may round for display purposes |
| `value.movePointLeft(n)` | **Yes** if `n != 0` and value is non-zero | Divides by `10^n`, while also changing `scale` |
| `value.movePointRight(n)` | **Yes** if `n != 0` and value is non-zero | Multiplies by `10^n`, while also changing `scale` |
| `value.scaleByPowerOfTen(n)` | **Yes** if `n != 0` and value is non-zero | Multiplies by `10^n`, preserving negative `scale` results when needed |
| `value.round(MathContext)` | Possibly, if significant digits must be rounded | Resulting `precision` and `scale` depend on the outcome |

Do not look at the name `scaleByPowerOfTen` and assume it only controls "formatting": this method **actually multiplies/divides the numeric value** by a power of 10. Conversely, calling `toPlainString()` neither multiplies/divides nor creates a `BigDecimal` with a changed `scale`.

## 4. setScale: Preserves the Number When Possible, Rounds When Forced

`setScale(int newScale)` requests a representation with a new `scale` **without altering the numeric value**. If changing `scale` requires dropping non-zero digits, this overload throws `ArithmeticException`.

~~~java
BigDecimal source = new BigDecimal("13.000");

System.out.println(source.setScale(2)); // 13.00
System.out.println(source.setScale(1)); // 13.0
System.out.println(source.setScale(0)); // 13
~~~

All three results are mathematically equal to `source`. However, with `new BigDecimal("13.005").setScale(2)`, removing the digit 5 changes the value; thus Java **does not silently truncate** and instead throws an exception.

When business logic permits rounding, specify `RoundingMode` **explicitly**:

~~~java
BigDecimal original = new BigDecimal("2.005");

System.out.println(
        original.setScale(2, RoundingMode.HALF_UP)
); // 2.01

System.out.println(
        original.setScale(2, RoundingMode.HALF_EVEN)
); // 2.00
~~~

The results above differ from the numeric value 2.005: **rounding is a business-domain decision**, no longer purely a display choice if the result is fed into subsequent calculations.

Choose `RoundingMode.UNNECESSARY` when you want to assert that the conversion must be exact: the method will raise an error if rounding is required. For currency or measurements, never pick a rounding rule just because the output looks nice; follow the business contract.

## 5. Java 17+ Example: Same Value, Multiple Representations

Create `BigDecimalValueDisplayDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class BigDecimalValueDisplayDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("12.30");
        BigDecimal b = new BigDecimal("12.300");

        System.out.println("a: " + a + " | scale=" + a.scale());
        System.out.println("b: " + b + " | scale=" + b.scale());
        System.out.println("value equal: " + (a.compareTo(b) == 0));
        System.out.println("representation equal: " + a.equals(b));

        BigDecimal total = a.add(new BigDecimal("0.700"));
        System.out.println("sum: " + total + " | scale=" + total.scale());
        System.out.println("normalized: " + total.stripTrailingZeros()
                + " | scale=" + total.stripTrailingZeros().scale());
        System.out.println("fixed: " + total.setScale(2)
                + " | scale=" + total.setScale(2).scale());

        BigDecimal scientific = new BigDecimal("1E+3");
        System.out.println("notation: " + scientific.toString());
        System.out.println("plain: " + scientific.toPlainString());
        System.out.println("scientific scale: " + scientific.scale());

        DecimalFormat display = new DecimalFormat(
                "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
        display.setRoundingMode(RoundingMode.HALF_UP);

        BigDecimal amount = new BigDecimal("1234.5");
        System.out.println("display: " + display.format(amount));
        System.out.println("original after format: " + amount);
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac BigDecimalValueDisplayDemo.java
java BigDecimalValueDisplayDemo
~~~

Output:

~~~text
a: 12.30 | scale=2
b: 12.300 | scale=3
value equal: true
representation equal: false
sum: 13.000 | scale=3
normalized: 13 | scale=0
fixed: 13.00 | scale=2
notation: 1E+3
plain: 1000
scientific scale: -3
display: 1,234.50
original after format: 1234.5
~~~

Explanation:

- `a` and `b` are equal in numeric value but differ in `scale`. This matters if a system layer uses `equals()`, `hashCode()`, or a hash collection as keys.
- `total` is **13** mathematically. Calling `stripTrailingZeros()` gives the representation `13`; calling `setScale(2)` gives `13.00` while still keeping the value 13.
- `scientific.toString()` displays `1E+3` while `toPlainString()` displays `1000`. The original object still has `scale = -3`.
- `DecimalFormat` only builds the string `1,234.50` for display under `Locale.US` conventions in the example. After formatting, `amount` is still an object representing `1234.5` with `scale = 1`.

`BigDecimal` is immutable: conversion/rounding methods return new objects; string/formatting methods do not modify the computed object.

## 6. toString, toPlainString, and Strings with Fixed Decimal Places

These three requirements are not the same:

**A. Need the canonical BigDecimal string.** `toString()` returns a string following deterministic rules; it may choose scientific notation, and can be parsed back with the `BigDecimal(String)` constructor to recover the same `unscaledValue`/`scale` representation pair under valid conditions. For example, `new BigDecimal("1E+3").toString()` is `"1E+3"`.

**B. Need an exponent-free string.** `toPlainString()` returns a flat decimal form, such as `"1000"` instead of `"1E+3"`. It **does not automatically enforce a fixed number of decimal places**, nor does it preserve a negative `scale` if `"1000"` is subsequently parsed back. In this example, parsing `"1000"` yields `scale = 0`, different from the original object's `scale = -3`.

**C. Need exactly two digits after the decimal point.** If the policy is to produce a `BigDecimal` with `scale = 2`, use `setScale(2)` or the overload with `RoundingMode`, then `toPlainString()` to get `"1000.00"`. If only for UI display, use an appropriate presentation formatter without altering the computed data.

Example:

~~~java
BigDecimal amount = new BigDecimal("1000");
System.out.println(amount.toPlainString());           // 1000
System.out.println(amount.setScale(2).toPlainString()); // 1000.00
~~~

Note that `toPlainString()` on a number with an extremely large exponent can produce a very long string, consuming memory. Do not call it unconditionally on user-entered exponential data without bounds.

If the UI uses the Vietnamese locale, thousands grouping and decimal separators can differ from `Locale.US`; do not manually replace `.` with `,` in a canonical string and then pass that string into `new BigDecimal(...)`. Data parsing and user-facing formatting should follow **separate rules**.

## 7. stripTrailingZeros: Normalizes Value, Yet Changes Scale

`stripTrailingZeros()` returns a `BigDecimal` equal in numeric value with trailing zeros removed from the unscaled part:

~~~java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal y = x.stripTrailingZeros();

System.out.println(x);         // 1000.00
System.out.println(x.scale()); // 2
System.out.println(y);         // 1E+3
System.out.println(y.scale()); // -3
~~~

In this example, `stripTrailingZeros()` does not change the number 1000, yet the new representation has a **negative scale**. Therefore:
- If the goal is to unify numerically equal `BigDecimal` instances as keys, normalization can be helpful but must be applied consistently everywhere.
- If `scale` represents measurement resolution, significant digits, or a contractual obligation, do not strip it automatically.
- If the goal is displaying `1000.00`, `stripTrailingZeros()` is not the right tool.

`stripTrailingZeros()` on any zero value normalizes to `BigDecimal.ZERO`, which has `scale = 0`. Thus `new BigDecimal("0.000").stripTrailingZeros()` does not keep three decimal places.

## 8. Computational Scale Can Affect Subsequent Operation Results

A dangerous rule of thumb is "two numbers with `compareTo() == 0` are interchangeable in every calculation." Their numeric values before the operation are identical, yet **overloads with default rounding and scale can produce different arithmetic outcomes**.

Example:

~~~java
BigDecimal divisor = new BigDecimal("3");

System.out.println(
        new BigDecimal("2.0").divide(divisor, RoundingMode.HALF_UP)
); // 0.7

System.out.println(
        new BigDecimal("2.00").divide(divisor, RoundingMode.HALF_UP)
); // 0.67
~~~

The `divide(BigDecimal divisor, RoundingMode roundingMode)` overload returns a result with the **dividend's scale**. With `2.0`, the rounded result has one digit after the decimal point; with `2.00`, the result has two digits. Thus two objects initially equal in numeric value yield different rounded outcomes through this overload.

To avoid implicit dependencies, write the business rule explicitly:

~~~java
BigDecimal ratio = new BigDecimal("2.0")
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
System.out.println(ratio); // 0.6667
~~~

`MathContext` controls the number of **significant** digits and rounding for an operation; `scale` controls the position of the decimal point. Do not use `new MathContext(2)` to mean "two digits after the decimal point." A `precision = 2` parameter means two significant digits, so the result depends on the number's magnitude.

## 9. Display-Layer-Only Formatting: DecimalFormat and Locale

To display numbers to humans, Java provides `DecimalFormat` and `NumberFormat`. This is the **rendering** step: taking a value and producing a string per pattern/locale. Example with `Locale.US`:

~~~java
DecimalFormat formatter = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
formatter.setRoundingMode(RoundingMode.HALF_UP);

BigDecimal value = new BigDecimal("1234.5");
String label = formatter.format(value);

System.out.println(label); // 1,234.50
System.out.println(value); // 1234.5
~~~

The snippet above requires `import java.math.*; import java.text.*; import java.util.*;` or explicit imports as in the Section 5 program.

**Appropriate choices:**
- Need further computation: keep the original `BigDecimal` with appropriate precision.
- Need machine import/export in a standard format: define explicit formatting and parsing policies; `toString()` is usually suitable for canonical numeric values.
- Need user-facing display: use a formatter matching the desired locale and unit; formatted strings may contain grouping separators and cannot be passed directly to the `BigDecimal(String)` constructor.
- Need to store a **finalized value after rounding**: apply rounding to the `BigDecimal` before the business finalization point, rather than relying on the displayed number.

`DecimalFormat` is an object that is **not safe to share and use concurrently across multiple threads** without proper synchronization. You can instantiate it per use or provide a separate instance per application context.

A UI might display `12.35` from underlying data `12.3456` without changing the source data. If the user confirms a transaction at `12.35`, the application must clearly specify which **finalized value** is stored and carried forward in calculations; never implicitly assume the original value was rounded by the formatter.

## 10. Data Conversion Across Application Layers

Picture the processing flow:

~~~text
Input string / external data
        |
        v
Parse into BigDecimal with explicit convention
        |
        v
BigDecimal computation + business rounding
        |
        +----> Store finalized value per schema contract
        |
        +----> Format per locale and UI requirements
                  |
                  v
              Display string
~~~

At each boundary, distinguish the following contracts.

**Input:** For a canonical decimal string `"12.345"`, `new BigDecimal("12.345")` preserves the exact decimal value. Avoid `new BigDecimal(0.1)` when exact `0.1` is intended because `double` typically cannot represent that decimal number exactly; `BigDecimal.valueOf(0.1)` or the `String` constructor behaves more appropriately here.

**Computation:** Use `add`, `subtract`, `multiply`, `divide`, and `MathContext`/`RoundingMode` as needed. Do not mechanically round after every operation; where rounding occurs must follow policy, because rounding at different steps can produce different totals.

**Storage:** When writing to a `DECIMAL(p,s)`/`NUMERIC(p,s)` database column, `p` and `s` are the schema/database contract and do not by default match the `precision()` and `scale()` of your current object. The database/driver may enforce scale, round, or reject data depending on the RDBMS and schema. Verify actual behavior, use parameterized queries, and test digit-overflow cases. Do not treat `toPlainString()` as a schema enforcement mechanism.

**JSON communication:** Many libraries serialize `BigDecimal` as a JSON number; some offer options for scientific or plain representation. If sent as a **JSON number**, consumers may parse it as floating-point, losing significant digits and failing to preserve `scale`. If the contract requires both precision and digit count, you can define a decimal string plus `scale`/unit metadata and require consumers to honor it. Do not rely on JSON number syntax to convey "always two digits."

**Display:** Choose a formatter suitable for the user; e.g., `#,##0.00` requests two digits after the decimal point in the US locale. Thousands grouping commas are presentation symbols, not part of the numeric value.

## 11. Design Selection Examples: Money, Measurements, and Reporting Figures

### Case A — Money in Smallest Units

Suppose a system defines one major unit as 100 minor units and accepts only an **integer number of minor units**. The incoming value is `"12.345"` major units:

~~~java
BigDecimal amount = new BigDecimal("12.345");
BigDecimal minor = amount.movePointRight(2); // 1234.5
~~~

If `longValue()` is used, the fractional part is truncated and corrupts the monetary amount. Require an **exact** conversion using `longValueExact()` or `toBigIntegerExact()`; reject invalid fractions, or round according to an approved rule prior to conversion.

Example of an explicit value-finalization rule:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
long cents = rounded.movePointRight(2).longValueExact();

System.out.println(rounded); // 12.35
System.out.println(cents);   // 1235
~~~

This is a **value-changing rounding decision**, not merely a display change. The factor of 100 holds only for the unit/currency assumed in the example; do not assume every currency has two minor-unit decimal places.

### Case B — Measurements with Resolution

The two numbers `1.2` and `1.20` are arithmetically equal, yet if the measurement source uses decimal-place count to express resolution, calling `stripTrailingZeros()` can discard representation information. Explicitly decide whether **measurement precision** is modeled via `scale` or via separate metadata. `BigDecimal` preserves decimal digit count, though it does not by itself prove the real-world measurement was accurate to that degree.

### Case C — Reports Requiring Only Uniform Presentation

Data after addition is `13.000`, while a report needs exactly two decimal places. If no new value is being finalized, a formatter can produce `"13.00"`. If a decimal value with `scale = 2` must be emitted for a data exchange contract, use `setScale(2)` with explicit error handling or rounding. Both approaches produce the text `13.00`, yet their **impact on the underlying data differs**.

## 12. Common Mistakes

1. **Confusing `scale` with calculation accuracy:** `scale = 2` only specifies the decimal point position in the representation; it does not assert the number was measured or computed accurately to two decimal places.
2. **Thinking `setScale` only changes a label:** if decreasing `scale` drops non-zero digits, rounding changes the value; the non-rounding overload throws an exception.
3. **Thinking `toPlainString()` guarantees two digits:** it only removes exponential notation. `new BigDecimal("1E+3").toPlainString()` is `"1000"`, not `"1000.00"`.
4. **Calling `stripTrailingZeros()` before every operation:** can erase needed `scale` information and alter rounding results on certain overloads.
5. **Using `scaleByPowerOfTen` to "format":** this method multiplies/divides the numeric value by a power of 10, rather than just changing how the number prints.
6. **Believing a display string is canonical data:** `"1,234.50"` depends on locale and separators; keep parsing and formatting separate.
7. **Confusing `compareTo` with `equals`:** `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0`, whereas `equals()` is `false`. This can affect `HashMap` keys and sorted structures like `TreeMap`.
8. **Initializing with `new BigDecimal(double)` and blaming rounding/scale:** discrepancies may stem from the initial binary floating-point value; construct from a decimal string or `BigDecimal.valueOf(double)` when appropriate.
9. **Rounding early and repeatedly:** summing individually rounded line items can differ from rounding the final total once. Clearly define when rounding is finalized.
10. **Forgetting output limits:** scientific notation can represent numbers with huge exponents compactly, whereas `toPlainString()` can generate enormous strings. Enforce resource limits on untrusted input.

## 13. Self-Check Exercises

**Exercise 1.** Given the code:

~~~java
BigDecimal original = new BigDecimal("3.000");
BigDecimal a = original.setScale(1);
BigDecimal b = original.stripTrailingZeros();

System.out.println(a);                 // ?
System.out.println(a.scale());         // ?
System.out.println(b);                 // ?
System.out.println(b.scale());         // ?
System.out.println(original.equals(a));// ?
System.out.println(original.compareTo(b) == 0);// ?
~~~

**Answer:** `3.0`, `1`, `3`, `0`, `false`, `true`. All three are equal in numeric value, yet differ in `scale` and can differ in `equals()`.

**Exercise 2.** What does `new BigDecimal("3.005").setScale(2, RoundingMode.HALF_UP)` return? **Answer:** `3.01`. This changes the numeric value; without passing a rounding mode, the `setScale(2)` overload throws `ArithmeticException`.

**Exercise 3.** What does `new BigDecimal("1E+3").setScale(2).toPlainString()` return? **Answer:** `"1000.00"`. Setting `scale = 2` is an operation producing a new object; `toPlainString()` then converts it to a string.

**Exercise 4.** A system needs to compute the average of several numbers and display two decimal places. Should you call `setScale(2, HALF_UP)` after *each element* before summing? **Hint:** only if the contract requires per-element rounding. Normally, keep full computed precision and round at the business-defined point, then format for the UI afterward. Compare approaches on inputs with third decimal digits to inspect the discrepancy.

**Exercise 5.** A backend sends the JSON number `1.00` to a client and expects the client to always know the user typed two digits after the decimal point. Is that reliable? **Answer:** No. JSON number syntax and how receiving parsers behave do not guarantee preserving `scale` semantics. Agree on an explicit exchange contract, using decimal strings or separate metadata when digit count is business data.

## 14. Application Rules and References

Before modifying a `BigDecimal`, answer in order:

1. **Is the mathematical value allowed to change?** If not, avoid unintended rounding; use exact conversions and check exceptions.
2. **Is `scale` part of the data contract?** If so, preserve or normalize it per published rules; do not arbitrarily strip trailing zeros.
3. **Is the output for computation, storage, or display?** Use `BigDecimal` for computation, define explicit schemas for storage, and use formatters/locales for presentation.
4. **When and under what rule will rounding occur?** Encode that with `RoundingMode`/`MathContext` or the corresponding `divide` overload.

Official documentation:
- [BigDecimal — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): `scale` representation, preferred scale, `setScale`, `toString`, `toPlainString`, `stripTrailingZeros`, and operations.
- [RoundingMode — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): semantics of rounding modes.
- [DecimalFormat — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): number formatting patterns, locales, and multithreaded usage.
