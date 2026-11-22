# BigDecimal.compareTo(): comparing numeric values in Java

## 1. The problem to solve

In Java, `BigDecimal` stores an arbitrary-precision decimal value using an **unscaled integer** (`unscaledValue`) and a **scale** (a negative base-10 exponent). The mathematical value can be thought of as `unscaledValue × 10^(-scale)`. The same number can have different representations:

- `new BigDecimal("2.0")`: numeric value 2; unscaled value 20; scale 1.
- `new BigDecimal("2.00")`: numeric value 2; unscaled value 200; scale 2.
- `new BigDecimal("2")`: numeric value 2; unscaled value 2; scale 0.

When you need to answer "which value is larger?", "are they equal in **numeric value**?", or "has this number reached the threshold?", use **`BigDecimal.compareTo(BigDecimal other)`**. This method compares **numeric value**, so it treats `2.0`, `2.00`, and `2` as equal in ordering, even though their scales differ.

This is an important difference compared to `equals(Object)`, which considers both numeric value and scale. Choosing the right comparison prevents bugs when data comes from sources with inconsistent decimal formatting.

## 2. How to read compareTo results

Syntax:

~~~java
int result = left.compareTo(right);
~~~

The result falls into three groups of meaning:

| Condition | Meaning | Example |
| --- | --- | --- |
| `result < 0` | `left` is less than `right` | `1.25` vs `1.30` |
| `result == 0` | Both objects have the **same numeric value** | `2.0` vs `2.00` |
| `result > 0` | `left` is greater than `right` | `9.5` vs `9.05` |

The `Comparable.compareTo` contract requires a **negative, 0, or positive** result; when checking conditions, write `< 0` or `> 0`, without depending on whether the method returns exactly `-1` or `1`.

Comparison direction follows the **signed number line**:

- `-8.0 < -2.00` because -8 is to the left of -2.
- `-0.001 < 0` even though the absolute value is very small.
- `0.000` and `0` are equal in numeric value.
- `10.00 > 9.999` even though the number on the right has more decimal digits.

**Scale does not determine whether a number is larger or smaller.** You cannot compare two `BigDecimal` values by comparing scale, string length, number of decimal digits, or lexicographical ordering.

## 3. Runnable Java 17 example

Save the following code as `BigDecimalCompareDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalCompareDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("equals = " + a.equals(b));
        System.out.println("scales = " + a.scale() + ", " + b.scale());

        BigDecimal negative = new BigDecimal("-1.25");
        System.out.println("negative < zero = "
                + (negative.compareTo(BigDecimal.ZERO) < 0));
        System.out.println("3.50 > 3.05 = "
                + (new BigDecimal("3.50")
                        .compareTo(new BigDecimal("3.05")) > 0));
        System.out.println("1.20 < 1.3 = "
                + (new BigDecimal("1.20")
                        .compareTo(new BigDecimal("1.3")) < 0));

        List<BigDecimal> values = new ArrayList<>(List.of(
                new BigDecimal("10.0"),
                new BigDecimal("2.00"),
                new BigDecimal("-1.2"),
                new BigDecimal("2.0")
        ));
        values.sort(BigDecimal::compareTo);
        System.out.println("sorted = " + values);

        Set<BigDecimal> hashSet = new HashSet<>(List.of(a, b));
        Set<BigDecimal> treeSet = new TreeSet<>(List.of(a, b));
        System.out.println("HashSet size = " + hashSet.size());
        System.out.println("TreeSet size = " + treeSet.size());

        BigDecimal representedZero = new BigDecimal("0.000");
        System.out.println("numeric zero = "
                + (representedZero.compareTo(BigDecimal.ZERO) == 0));
        System.out.println("normalized b = "
                + b.stripTrailingZeros().toPlainString());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac BigDecimalCompareDemo.java
java BigDecimalCompareDemo
~~~

Output:

~~~text
compareTo = 0
equals = false
scales = 1, 2
negative < zero = true
3.50 > 3.05 = true
1.20 < 1.3 = true
sorted = [-1.2, 2.00, 2.0, 10.0]
HashSet size = 2
TreeSet size = 1
numeric zero = true
normalized b = 2
~~~

Explanation by group:

1. `a.compareTo(b) == 0`: `2.0` and `2.00` have the same **numeric value**.
2. `a.equals(b) == false`: the two objects represent the same number 2, but have scales 1 and 2 respectively.
3. Negative/positive comparisons use `< 0` or `> 0`, with no need to convert to `double`.
4. `values.sort(BigDecimal::compareTo)` sorts in ascending numeric order. The two elements `2.00` and `2.0` have equal ordering under the comparator; `List.sort` is stable so it preserves their original relative order.
5. `HashSet` treats `2.0` and `2.00` as two distinct elements based on `equals` and `hashCode`; `TreeSet` uses natural ordering via `compareTo` and treats them as duplicates.
6. `stripTrailingZeros()` reduces `2.00` to a representation without trailing zeros; `toPlainString()` prints it as `2`. This operation does not modify `b` because `BigDecimal` is immutable.

## 4. compareTo and equals: where do they differ?

The two methods answer two different questions:

| Method | Question | `2.0` and `2.00` |
| --- | --- | --- |
| `compareTo` | Are two numbers greater, smaller, or **numerically equal**? | `compareTo(...) == 0` |
| `equals` | Do two `BigDecimal` objects have the same value and the same **scale**? | `equals(...) == false` |
| `hashCode` | Does the hash code follow the equality contract of `equals`? | May differ; do not use hash codes to compare numbers |

For `BigDecimal`, `equals` returns true only if the represented numbers have equal value **and equal scale**; `compareTo` does not require the same scale. Java explicitly documents this: the natural ordering of `BigDecimal` is **inconsistent with `equals`**.

~~~java
BigDecimal priceA = new BigDecimal("19.9");
BigDecimal priceB = new BigDecimal("19.90");

boolean sameNumericValue = priceA.compareTo(priceB) == 0; // true
boolean sameRepresentation = priceA.equals(priceB);         // false
~~~

Do not replace `compareTo` with `equals` when you only need to check whether two **numbers** are equal. Conversely, when program requirements treat scale as an important part of the information (for example, checking whether an object has the exact representation to be stored), `equals` may be an intentional choice.

### A surprising case during operations

The same number can produce results from `divideToIntegralValue` or representation-dependent operations with different output scales depending on the operand scales. Therefore, "`compareTo == 0`" **does not guarantee that every operation on the two objects will produce results with the same scale**. Do not infer identical representation from numeric equality.

## 5. Comparing with 0, thresholds, and ranges

`BigDecimal.ZERO` is a constant representing the number 0; comparing against it is clear and avoids creating unnecessary objects.

~~~java
BigDecimal balance = new BigDecimal("-0.01");

boolean isNegative = balance.compareTo(BigDecimal.ZERO) < 0;
boolean isZero = balance.compareTo(BigDecimal.ZERO) == 0;
boolean isPositive = balance.compareTo(BigDecimal.ZERO) > 0;
~~~

Common comparisons:

| Requirement | Expression |
| --- | --- |
| `x < y` | `x.compareTo(y) < 0` |
| `x <= y` | `x.compareTo(y) <= 0` |
| `x == y` in numeric value | `x.compareTo(y) == 0` |
| `x >= y` | `x.compareTo(y) >= 0` |
| `x > y` | `x.compareTo(y) > 0` |
| `x != y` in numeric value | `x.compareTo(y) != 0` |

Example accepting an order if the amount reaches a minimum of `100.00`:

~~~java
BigDecimal amount = new BigDecimal("100.0");
BigDecimal minimum = new BigDecimal("100.00");

if (amount.compareTo(minimum) >= 0) {
    System.out.println("Threshold reached");
}
~~~

The result is `Threshold reached` because the numeric values are equal, even though the scales differ. If you need to check a closed range `[min, max]`, use:

~~~java
boolean inRange = value.compareTo(min) >= 0
        && value.compareTo(max) <= 0;
~~~

These are **illustrative code snippets**, where the variables `value`, `min`, and `max` are assumed to be non-null `BigDecimal` values with the range `min <= max`. To actually run them, place these snippets inside a method or program with all variables declared.

## 6. Sorting and collections: consequences of the difference

`BigDecimal` implements `Comparable<BigDecimal>`, so Java uses `compareTo` as its **natural ordering**:

~~~java
List<BigDecimal> values = new ArrayList<>(List.of(
        new BigDecimal("9.00"),
        new BigDecimal("1.1"),
        new BigDecimal("1.10")
));
values.sort(BigDecimal::compareTo);
~~~

The result is sorted in ascending numeric order: `[1.1, 1.10, 9.00]`. The two values `1.1` and `1.10` have `compareTo == 0`, so they do not differ in numeric order; a stable sort keeps their order as it was before sorting.

However, **how each collection determines "duplicates"** matters a great deal:

- `HashSet<BigDecimal>` and `HashMap<BigDecimal, ...>` rely on the key's `equals` and `hashCode`. `new BigDecimal("2.0")` differs from `new BigDecimal("2.00")` by this criterion, so both keys can coexist.
- `TreeSet<BigDecimal>` and `TreeMap<BigDecimal, ...>` under natural ordering use `compareTo` (or the supplied comparator) to identify two keys at the same comparison position. `2.0` and `2.00` are treated as the same key because `compareTo == 0`.
- If a `TreeMap` is given key `2.00` after already containing `2.0`, the value is written to the existing key entry according to the comparator's criteria; do not expect two independent entries to be kept automatically.
- `Stream.distinct()` uses `equals`, so this operation alone can still retain both representations `2.0` and `2.00`. Sorting with `compareTo` beforehand does not automatically change the rule of `distinct()`.

If the business logic considers decimal numbers with the same value to have the same identity, define how to **normalize** keys before using collections based on `equals`, or choose `TreeMap`/`TreeSet` with an appropriate comparator. Avoid mixing multiple identity rules without clear documentation.

### Stripping trailing zeros

`stripTrailingZeros()` returns a numerically equivalent `BigDecimal` with any trailing zeros removed from the unscaled value:

~~~java
BigDecimal first = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal second = new BigDecimal("2.00").stripTrailingZeros();

System.out.println(first.equals(second)); // true
~~~

Notes:

- Normalization does not lose **numeric value**, but it can change the **scale** and display form.
- For example, `new BigDecimal("600.0").stripTrailingZeros()` may be represented as `6E+2` with a negative scale, instead of the string `600.0`. Use `toPlainString()` when you need printing without scientific notation.
- `stripTrailingZeros()` on numeric value 0 returns the canonical zero representation, which can lose the original scale of `0.000`.
- If a fixed scale is a business requirement or data contract, do not automatically normalize every number without evaluating the impact. When data is required to have scale 2, `setScale(2)` succeeds without a rounding mode only if scale 2 can be achieved **without rounding**; other values may require an explicit rounding rule.

## 7. Input data and accuracy

Construct `BigDecimal` from exact decimal data such as JSON strings or input strings:

~~~java
BigDecimal expected = new BigDecimal("0.3");
BigDecimal actual = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

System.out.println(actual.compareTo(expected) == 0); // true
~~~

If you go through `double` first, decimal values such as `0.1` and `0.2` often cannot be represented exactly in binary floating point. `BigDecimal.valueOf(double)` converts from the canonical decimal string representation of the `double` value, which is useful when the input is already in that form; however, it cannot recover precision already lost in prior `double` arithmetic.

Avoid using:

~~~java
double x = 0.1 + 0.2;
double y = 0.3;
boolean equal = (x == y); // Often false due to binary representation.
~~~

This case illustrates the issue specifically for `double`. With `BigDecimal` constructed from strings and exact addition without `MathContext`, the numeric comparison produces the accurate result shown in the example above.

In principle, `compareTo` **does not round** the two numbers to compare them and does not require both sides to have the same scale. If you want to compare numbers *after* rounding them according to business rules, you must round each value first, then call `compareTo`; that is a different requirement from comparing the original values.

## 8. API design considerations

### Null is not a numeric value

`BigDecimal` is a reference type. If the receiving object is `null`, the expression `amount.compareTo(other)` throws `NullPointerException`; passing `null` as the comparison argument also throws `NullPointerException`. Handle null according to your data contract before comparing:

~~~java
if (amount == null || minimum == null) {
    throw new IllegalArgumentException("Missing monetary amount");
}
boolean accepted = amount.compareTo(minimum) >= 0;
~~~

The snippet above is an input validation example, where `amount` and `minimum` are supplied from elsewhere.

### BigDecimal is immutable

`compareTo` only **observes the ordering** between two values; it does not modify either `BigDecimal`. Methods like `stripTrailingZeros`, `setScale`, and `add` also return a new result object (or a reusable object) without changing the value of the receiver.

### Do not use < or > operators

The operators `<`, `>`, `<=`, and `>=` work on primitive numeric types and applicable conversions; they are **not** overloaded for `BigDecimal`. Writing `a > b` with two `BigDecimal` references is a compile error. Use `a.compareTo(b) > 0`.

### Do not subtract and convert to int to compare

An expression like `a.subtract(b).intValue()` can return 0 even when two numbers are not equal, or lose information due to truncating the fractional part or overflowing the `int` range. `compareTo` expresses the intent directly and avoids unnecessary intermediate calculations.

### Ordering is transitive

If `a.compareTo(b) < 0` and `b.compareTo(c) < 0`, then `a.compareTo(c) < 0`. This is an essential part of the comparison contract, allowing use with sorting and ordered data structures. When writing a custom comparator instead, preserve sign symmetry and transitivity; avoid comparators based on `doubleValue()` if doing so loses the distinction between very close or very large `BigDecimal` values.

## 9. Common mistakes and how to fix them

**Mistake: using `equals` for numbers entered with inconsistent scales.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is false. If you only want to know whether two numbers are equal, use `compareTo(...) == 0`.

**Mistake: comparing via `toString()`.** `"10.0".compareTo("2.0") < 0` because strings are compared character-by-character, even though 10.0 is greater than 2.0. Always use `BigDecimal.compareTo` for numeric ordering.

**Mistake: assuming `compareTo == 0` implies `equals == true`.** This is why `HashSet` and `TreeSet` behave differently. Choose identity criteria, collections, and normalization consistently.

**Mistake: writing `compareTo(...) == 1`.** It is best to compare with `> 0` or `< 0` per the `Comparable` contract; this also applies to custom comparators.

**Mistake: converting to `double` or `long` to compare.** Type conversion can cause precision loss, fractional truncation, or range overflow. `BigDecimal.compareTo` preserves the arbitrary-precision decimal domain.

**Mistake: defaulting null to 0.** Null represents missing data, which is different from `BigDecimal.ZERO`. Convert null to 0 only if the application specification permits it.

**Mistake: sorting and then calling `distinct()` to merge equal numbers.** `distinct()` still relies on `equals`; `2.0` and `2.00` can still coexist after that operation.

## 10. Self-check questions

Before running the code, determine the sign of `left.compareTo(right)`:

| left | right | Sign of result | `left.equals(right)` |
| --- | --- | --- | --- |
| `3.0` | `3.00` | `0` | `false` |
| `-3.00` | `-2.99` | `< 0` | `false` |
| `0.000` | `0` | `0` | `false` |
| `0.100` | `0.10` | `0` | `false` |
| `100.01` | `100.001` | `> 0` | `false` |
| `7.00` | `7.00` | `0` | `true` |

To practice, write expressions yourself to check "negative", "positive", "equal to 0", and "at least equal to threshold", and try inputs with differing trailing zeros. Then insert `2.0` and `2.00` into `HashSet` and `TreeSet` to observe the difference firsthand.

**Key takeaway:** `BigDecimal.compareTo` compares **by numeric value**; a negative/0/positive result indicates less than/equal/greater than. When you need numeric equality, use `compareTo(other) == 0`. `equals` also considers scale, so choosing between the two methods directly affects collections, keys, and application logic.
