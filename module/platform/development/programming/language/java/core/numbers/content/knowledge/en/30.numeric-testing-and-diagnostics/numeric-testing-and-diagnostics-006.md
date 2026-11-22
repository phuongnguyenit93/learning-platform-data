# Checking `BigDecimal` Value and Scale When Required by Contract

## 1. Why Must `BigDecimal` Testing Clearly Define the Contract?

A `BigDecimal` holds a **decimal value** and a **scale** (decimal point position). Two objects can share the same mathematical value yet have different scales:

~~~java
BigDecimal a = new BigDecimal("12.0");
BigDecimal b = new BigDecimal("12.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
System.out.println(a.scale());            // 1
System.out.println(b.scale());            // 2
~~~

Arithmetically, both equal 12. However, `12.0` stores unscaled value 120 and scale 1; `12.00` stores unscaled value 1200 and scale 2. These two representations can carry different meanings for output formatting, fractional policies, data contracts, or testing.

**Key rule:** Before writing a check, ask what the contract requires:

1. Equal **mathematical value** only?
2. Equal **value and scale**?
3. A **specific canonical scale**, such as exactly 2, even if sources pass other scales?
4. Exact **text representation**, including trailing zeros, plus sign, exponential notation, or locale formatting?

These are distinct requirements. No single comparison method fits all cases.

## 2. Understanding Value, Scale, and Precision

Structurally:

~~~text
Value = unscaledValue × 10^(-scale)
~~~

Examples:

| Construction | Mathematical value | Unscaled value | Scale | Precision |
| --- | --- | ---: | ---: | ---: |
| `new BigDecimal("12")` | 12 | 12 | 0 | 2 |
| `new BigDecimal("12.0")` | 12 | 120 | 1 | 3 |
| `new BigDecimal("12.00")` | 12 | 1200 | 2 | 4 |
| `new BigDecimal("0.000")` | 0 | 0 | 3 | 1 |
| `new BigDecimal("1E+3")` | 1000 | 1 | -3 | 1 |

**Scale** is not precision:

- Scale can be **positive, zero, or negative**. A negative scale represents a positive power-of-10 multiple; for example `1E+3` has scale -3.
- Precision is the number of decimal digits in the unscaled integer value, ignoring sign; for zero, precision is 1.
- Two numerically equal values can differ in both precision and scale.
- `BigDecimal` does not retain the exact original text: the characters `+0012.00` and `12.00` create objects with the same value and scale, even though the source strings differ.

If tests require preserving **every character** of the input, comparing `BigDecimal` alone is insufficient. You must also retain and test the raw text or a separate representation record.

## 3. `compareTo()` Checks Mathematical Value

The method:

~~~java
int comparison = expected.compareTo(actual);
~~~

returns a negative number, 0, or a positive number depending on whether `expected` is less than, equal to, or greater than `actual`. When checking equality **solely by numerical value**, use:

~~~java
boolean sameNumericValue = expected.compareTo(actual) == 0;
~~~

Example pairs:

| First value | Second value | `compareTo(...) == 0` |
| --- | --- | --- |
| `1.0` | `1.00` | `true` |
| `0` | `0.000` | `true` |
| `1000` | `1E+3` | `true` |
| `12.00` | `12.01` | `false` |
| `-2.50` | `-2.5` | `true` |

`compareTo` is appropriate when the contract requires only **equal numerical results**, such as totals 10.0 and 10.00 being equivalent in value.

**Do not compare `BigDecimal` values by converting to `double` and using approximate comparison** when decimal exactness is the goal. Casting to `double` can round or overflow range and collapse two distinct values into the same binary value.

However, `compareTo` **intentionally ignores differences in scale**. It does not prove that an output satisfies a requirement like “must have exactly two decimal places as a `BigDecimal`”.

## 4. `equals()` Checks Both Value and Scale

`BigDecimal.equals(Object)` requires both value and scale to match. You can use:

~~~java
BigDecimal expected = new BigDecimal("12.00");
BigDecimal actual = new BigDecimal("12.0");

System.out.println(expected.equals(actual)); // false
System.out.println(expected.compareTo(actual) == 0); // true
~~~

If both objects are valid `BigDecimal` instances, `equals` is `true` when they have the **same value and same scale**. An explicit equivalent expression is:

~~~java
boolean sameValueAndScale =
        expected.compareTo(actual) == 0
        && expected.scale() == actual.scale();
~~~

If `expected` and `actual` can be `null`, an explicit null policy is needed. `Objects.equals(expected, actual)` provides null-safe comparison yet still uses `BigDecimal.equals` semantics; two null values will be treated as equal, which may be **invalid** if the contract requires a non-null value.

### 4.1. `equals` Is Not a String Format Check

These two strings differ character by character:

~~~java
String rawA = "+0012.00";
String rawB = "12.00";
~~~

Yet `new BigDecimal(rawA).equals(new BigDecimal(rawB))` is `true`. The constructor parses the string into a number and does not preserve the plus sign or leading zeros.

Therefore:

- **Value only:** check `compareTo == 0`.
- **Value and scale:** use `equals` or two explicit assertions.
- **Display/interchange string:** check the `String` after formatting/serializing per contract, in addition to numeric checks where needed.

## 5. Writing Clear Assertions in Tests

### 5.1. Tests Requiring Only Value

Using JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.math.BigDecimal;

BigDecimal expected = new BigDecimal("12.00");
BigDecimal actual = new BigDecimal("12.0");

assertEquals(0, expected.compareTo(actual));
~~~

This is a **snippet placed inside a JUnit 5 test method**, not a standalone runnable program. The assertion clearly states that **different scales are allowed**.

If you want a business-meaningful failure message:

~~~java
assertEquals(0, expected.compareTo(actual),
        "Decimal values must be equal");
~~~

### 5.2. Tests Requiring Both Value and Scale

~~~java
BigDecimal expected = new BigDecimal("12.00");
BigDecimal actual = new BigDecimal("12.0");

assertEquals(0, expected.compareTo(actual), "Wrong value");
assertEquals(expected.scale(), actual.scale(), "Wrong scale");
~~~

This snippet will **fail on the scale assertion**: expected scale = 2, actual scale = 1. Splitting into two assertions helps quickly diagnose whether the **value is wrong** or **only the scale representation is wrong**.

If only a single assertion is desired, JUnit's `assertEquals(expected, actual)` uses `equals` and checks both. Splitting assertions is valuable when error messages need to highlight the two distinct aspects.

In production, avoid using Java's `assert condition;` statement to enforce contracts because Java assertions may be disabled by default unless run with `-ea`. In tests, use the framework's assertion APIs; at production data boundaries, use explicit checks and exceptions.

### 5.3. When a Fixed Scale Is Required

Some contracts do not require matching an expected object's scale, instead specifying that **every result must have scale = 2**:

~~~java
BigDecimal actual = new BigDecimal("12.00");

assertEquals(0, actual.compareTo(new BigDecimal("12")));
assertEquals(2, actual.scale());
~~~

This expresses **value equal to 12 and scale exactly 2**. Separating the two checks is the clearest way to verify the contract.

Do not replace the scale assertion with `actual.toPlainString().endsWith("00")`: checking trailing characters does not prove the exact number of digits after the decimal point or the intended numeric value.

## 6. Normalizing Scale: `setScale` Must Have a Clear Policy

When input sources have different scales but the contract mandates a canonical scale, you can normalize at the **input/output boundary or domain layer**:

~~~java
BigDecimal raw = new BigDecimal("12.0");
BigDecimal canonical = raw.setScale(2, RoundingMode.UNNECESSARY);

System.out.println(canonical); // 12.00
System.out.println(canonical.scale()); // 2
~~~

`setScale(2, UNNECESSARY)` requires the result to preserve the exact value when converted to scale 2. Scenarios:

| Input value | `setScale(2, UNNECESSARY)` | Reason |
| --- | --- | --- |
| `12` | `12.00` | Adds zeros, value unchanged |
| `12.0` | `12.00` | Adds zero |
| `12.000` | `12.00` | Drops redundant zero |
| `12.345` | `ArithmeticException` | Cannot drop digit 5 while keeping exact value |
| `-0.000` | `0.00` | `BigDecimal` does not preserve IEEE 754 negative zero |

If the contract **permits rounding**, you can choose `HALF_UP` or `HALF_EVEN`, for example:

~~~java
BigDecimal rounded =
        new BigDecimal("12.345").setScale(2, RoundingMode.HALF_UP);
// 12.35
~~~

At this point the value has changed according to the chosen rule. **Check the rounded value** as well as the scale. Do not normalize with `HALF_UP` just to turn a failing test green, because doing so can hide a violation of a “no rounding allowed” contract.

### 6.1. Do Not Transform Both `expected` and `actual` the Same Way and Call It Done

An anti-pattern:

~~~java
// Masks scale bugs if the contract demands scale = 2:
BigDecimal e = expected.stripTrailingZeros();
BigDecimal a = actual.stripTrailingZeros();
assertEquals(e, a);
~~~

This discards scale differences before checking. It is appropriate **only when** the contract truly means value comparison, in which case use `compareTo` to express that directly.

Conversely, if the contract allows any input representation yet requires the API to output scale 2, normalize **at the exact place producing the result** and assert that the output has scale 2. Tests should not alter `actual` before asserting, as that can hide bugs in the code under test.

## 7. The `stripTrailingZeros()` Pitfall: Scale Can Become Negative

`stripTrailingZeros()` removes trailing zeros in `BigDecimal`'s representation, which can reduce the scale, even into **negative values**:

~~~java
BigDecimal x = new BigDecimal("1000.00");
BigDecimal stripped = x.stripTrailingZeros();

System.out.println(stripped);         // 1E+3
System.out.println(stripped.scale()); // -3
~~~

The value is still 1000, yet the representation `1E+3` has scale -3. If the contract requires scale 2, calling `stripTrailingZeros` causes the output to **violate the contract** even though the mathematical value did not change.

For zero:

~~~java
BigDecimal zero = new BigDecimal("0.000");
System.out.println(zero.scale()); // 3
System.out.println(zero.stripTrailingZeros().scale()); // 0
~~~

Zero after `stripTrailingZeros()` is normalized to `BigDecimal.ZERO` with scale 0. When testing a contract that “zero must be represented as `0.00`”, intentionally construct or assert scale 2, e.g., `BigDecimal.ZERO.setScale(2)`.

**Do not treat `stripTrailingZeros` as a way to normalize to a fixed scale.** It is a redundant-zero removal operation whose resulting scale depends on the specific value.

## 8. Which Operations Change Scale?

When testing calculation pipelines, do not assume output scale always matches one of the inputs' scales. `BigDecimal` has preferred-scale rules:

| Exact operation | Typical preferred scale |
| --- | --- |
| `a.add(b)`, `a.subtract(b)` | `max(a.scale(), b.scale())` |
| `a.multiply(b)` | `a.scale() + b.scale()` |
| `a.divide(b)` when exact result has finite decimal representation | `a.scale() - b.scale()` is preferred scale; result may need a larger scale |
| `a.setScale(target, mode)` | `target` when successful |
| `a.stripTrailingZeros()` | Can decrease, to 0 or negative |

Example:

~~~java
BigDecimal first = new BigDecimal("1.20"); // scale 2
BigDecimal second = new BigDecimal("3.0"); // scale 1

System.out.println(first.add(second));      // 4.20, scale 2
System.out.println(first.multiply(second)); // 3.600, scale 3
~~~

Division with `MathContext`, `round(context)`, or operations with specific rounding rules can yield different scales than simple exact operations. Therefore, if an API promises a specific scale, assert scale **at the return point**, rather than deducing it solely from input scales.

**Precision is also a separate concept:** `new MathContext(3, HALF_UP)` limits to three significant digits. It does **not** guarantee scale 3 or scale 2. If both precision and scale are contract requirements, check both under an explicitly ordered policy.

## 9. Behavior in Collections and Lookup Structures

`BigDecimal.compareTo` and `BigDecimal.equals` define equality differently. This affects collections:

~~~java
BigDecimal a = new BigDecimal("12.0");
BigDecimal b = new BigDecimal("12.00");

Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
Set<BigDecimal> treeSet = new TreeSet<>(List.of(a, b));

System.out.println(hashSet.size()); // 2
System.out.println(treeSet.size()); // 1
~~~

This is an illustrative snippet requiring `import java.math.BigDecimal` and `import java.util.*`.

- `HashSet` relies on `equals`/`hashCode`, so it keeps two `BigDecimal` values with different scales as **two elements**.
- `TreeSet` uses natural ordering `compareTo` to determine element equality in the comparator, so it treats two numerically equal values as **one element**.

When using `BigDecimal` as keys in `HashMap` or `TreeMap`, pick a collection with the right semantics: are objects with different scales distinct keys or not? Do not assume switching from a hash map to a sorted map only affects iteration order.

If values with different scales should map to the same key, design an explicit normalization rule; if scale differences are meaningful, keep `equals` semantics and test the corresponding data structures.

## 10. Testing Data Across APIs, JSON, and Databases

### 10.1. API/JSON

Suppose an API publishes:

~~~json
{
  "amount": "12.00",
  "currency": "USD"
}
~~~

If `amount` is a canonical string with **exactly two digits after the decimal point**, two assertion layers may be needed:

1. Parse `"12.00"` into `BigDecimal` and verify **value** and **scale**.
2. Check that the wire string matches the pattern, e.g., **exactly two fractional digits, dot decimal separator, no grouping**.

`BigDecimal.equals` does not guarantee the original string lacked a `+` sign or leading zeros. Even with the same value and scale, `"+0012.00"` and `"12.00"` differ textually. If the contract requires canonical text representation, inspect the string field as well.

If the contract requires only **equal decimal value**, do not impose stricter scale assertions than specified. A producer might serialize the same value as `12`, `12.0`, or `12.00` and still satisfy the value requirement. JSON numbers and JSON strings also parse differently depending on library and consumer; test the exact data type specified by the contract.

### 10.2. JDBC and `DECIMAL`/`NUMERIC` Columns

Database decimal columns typically declare precision/scale in the schema, such as `DECIMAL(12,2)`. However, **how a driver/database returns `BigDecimal` can be affected by the schema and specific DBMS**. Do not assume a particular Java scale from sample data without verifying against the real system.

If the contract requires returned numbers to have scale 2, verify at the JDBC/repository boundary. If the requirement is only equal mathematical value, avoid failing tests merely because of differing scales permitted by the schema or driver.

Do not convert `BigDecimal` to `double` as an intermediate when comparing database results if decimal exactness is required. Binary rounding can mask or introduce discrepancies.

### 10.3. Display Formatting

`DecimalFormat` or `NumberFormat` can print `12.0` as `12.00` without **modifying the input `BigDecimal`**. If the contract only says “the UI must display two decimal places”, test the formatted string. If the contract says “the domain returns `BigDecimal` with scale 2”, test `scale()`. The two checks are different.

## 11. Standalone Runnable Java 17+ Example: Two Kinds of Contracts

Create file **BigDecimalContractDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalContractDemo {
    private static void requireNumeric(
            BigDecimal expected, BigDecimal actual) {
        if (expected.compareTo(actual) != 0) {
            throw new AssertionError("Numeric value differs");
        }
    }

    private static void requireValueAndScale(
            BigDecimal expected, BigDecimal actual) {
        requireNumeric(expected, actual);
        if (expected.scale() != actual.scale()) {
            throw new AssertionError("Scale differs");
        }
    }

    private static boolean passes(Runnable assertion) {
        try {
            assertion.run();
            return true;
        } catch (AssertionError ex) {
            return false;
        }
    }

    public static void main(String[] args) {
        BigDecimal expected = new BigDecimal("12.00");
        BigDecimal actual = new BigDecimal("12.0");

        System.out.println("compareTo zero: "
                + (expected.compareTo(actual) == 0));
        System.out.println("equals: " + expected.equals(actual));
        System.out.println("numeric assertion: "
                + passes(() -> requireNumeric(expected, actual)));
        System.out.println("value and scale assertion: "
                + passes(() -> requireValueAndScale(expected, actual)));

        BigDecimal normalized =
                actual.setScale(2, RoundingMode.UNNECESSARY);
        System.out.println("normalized: " + normalized.toPlainString());
        System.out.println("normalized assertion: "
                + passes(() -> requireValueAndScale(expected, normalized)));

        System.out.println("HashSet size: "
                + new HashSet<>(List.of(expected, actual)).size());
        System.out.println("TreeSet size: "
                + new TreeSet<>(List.of(expected, actual)).size());

        BigDecimal stripped =
                new BigDecimal("1000.00").stripTrailingZeros();
        System.out.println("stripped: " + stripped
                + ", scale: " + stripped.scale());

        BigDecimal zero =
                new BigDecimal("0.000").stripTrailingZeros();
        System.out.println("zero stripped scale: " + zero.scale());

        try {
            new BigDecimal("12.345")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("strict scale: ArithmeticException");
        }
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalContractDemo.java
java BigDecimalContractDemo
~~~

Exact output:

~~~text
compareTo zero: true
equals: false
numeric assertion: true
value and scale assertion: false
normalized: 12.00
normalized assertion: true
HashSet size: 2
TreeSet size: 1
stripped: 1E+3, scale: -3
zero stripped scale: 0
strict scale: ArithmeticException
~~~

The program uses `AssertionError` to simulate an active assertion; `passes` simply prints `true`/`false` without halting the entire demo. In real tests, **do not wrap assertion failures with `passes` and ignore the result**: let JUnit report the test failure with the case name and expected/actual details.

## 12. Required Test Cases

Build the test suite directly from the contract, covering these groups:

| Case | Sample values | What to verify |
| --- | --- | --- |
| Equal value, different scale | `12.0` vs `12.00` | Choose `compareTo` or `equals` per requirement |
| Equal to 0, different scale | `0` vs `0.000` | Zero still has scale |
| Exponential notation | `1E+3` vs `1000.00` | `compareTo` is 0; scales differ |
| Increasing scale | `12` to `12.00` | No value loss |
| Reducing scale via trailing zeros | `12.000` to `12.00` | Exact conversion |
| Reducing scale losing digits | `12.345` to scale 2 | Exception with `UNNECESSARY`, or rounding if permitted |
| `stripTrailingZeros` | `1000.00` | Scale can become negative |
| Sum calculation | `1.20 + 2.345` | Exact value and preferred scale |
| Serialize/parse pipeline | `"12.00"` via JSON/JDBC | Value, scale, string per respective contract |
| Null input | `null` | Reject or accept intentionally |
| Negative, large, and tiny numbers | `-0.0010`, `1E+20` | Do not assume scale from magnitude |

A strong test suite may include **numeric tests**, **value-and-scale tests**, **canonical string tests**, and **lossless scale-conversion tests**, depending on the contract. Do not force every use case to check scale: doing so can turn harmless representation differences into false failures.

## 13. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Two `BigDecimal`s with the same number always have `equals` `true` | `equals` also checks scale |
| `compareTo == 0` proves scales are equal | It only proves equal mathematical value |
| `setScale(2, UNNECESSARY)` always succeeds | It fails if keeping the value requires dropping nonzero digits |
| `stripTrailingZeros` normalizes to scale 0 | Scale can become negative, like `1000.00 -> 1E+3` |
| `precision == scale` | Precision and scale are independent concepts |
| Testing display string `12.00` proves domain scale 2 | A formatter can produce that string from domain scale 1 |
| `HashSet` and `TreeSet` treat `BigDecimal` equality the same way | Hash uses `equals`/`hashCode`; tree uses `compareTo` |
| Converting to `double` makes comparison simpler | Can lose precision and corrupt results |
| Data from SQL `DECIMAL` always has the Java scale we guess | Must rely on actual contract, schema, and driver behavior |
| Java `assert` always runs in deployment | `assert` statements can be disabled if assertions are not enabled |

## 14. Self-Check

1. What does `new BigDecimal("1.00").equals(new BigDecimal("1.0"))` return? **`false`**, because the scales are 2 and 1 respectively.
2. Does the pair above have `compareTo == 0`? **Yes**, because their mathematical values are equal.
3. When a DTO promises `amount` has exact scale 2, is `compareTo` alone enough? **No**; you must also verify scale 2.
4. Why is `new BigDecimal("1000.00").stripTrailingZeros().scale()` equal to -3? **Because the resulting form `1E+3` preserves the value with unscaled value 1 and scale -3**.
5. Does `new BigDecimal("12.340").setScale(2, UNNECESSARY)` succeed? **Yes**, yielding `12.34`, because only a redundant zero is dropped.
6. Does `new BigDecimal("12.345").setScale(2, UNNECESSARY)` succeed? **No**, because the value cannot be preserved at scale 2.
7. When is `assertEquals(expected, actual)` more appropriate than `assertEquals(0, expected.compareTo(actual))`? **When the contract requires both value and scale to match**.
8. If an API requires preserving the exact text `"0012.00"`, is checking `BigDecimal.equals` enough? **No**, you must check the source string or output string against representation rules.

**Takeaway:** For `BigDecimal`, **numerical equality** (`compareTo == 0`) and **value-plus-scale equality** (`equals`, or two explicit checks) are not synonymous. Write assertions matching the data contract; normalize scale only when policy allows, and do not inadvertently strip scale with `stripTrailingZeros` before testing a requirement that depends on scale.