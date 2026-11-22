# Example of 2.0 and 2.00 under each `BigDecimal` comparison method in Java

## 1. The problem: equal in value but different in representation

In Java, both of these `BigDecimal` objects carry the numeric value 2:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
```

However, the results of each comparison method **are not the same**:

```java
a == b;             // false: two objects with different references
a.equals(b);        // false: BigDecimal checks both value and scale
a.compareTo(b);     // 0: same numeric value
a.compareTo(b) == 0; // true: equal in numeric ordering
```

It is important to define up front what "equal" means: **same object**, **same value and same scale**, or **same numeric value**. These are three separate questions, with separate checks.

This lesson uses `2.0` and `2.00` to observe each result directly, explain why, and show the impact on `HashSet`, `TreeSet`, map keys, and domain data.

## 2. Why does `BigDecimal` distinguish 2.0 and 2.00?

A `BigDecimal` represents a decimal value using a pair of components:

- **Unscaled value**: an arbitrary-precision integer (`BigInteger`).
- **Scale**: a signed decimal exponent that determines the position of the decimal point.

Formula:

```text
numeric value = unscaledValue × 10^(-scale)

2.0  = 20  × 10^(-1)
2.00 = 200 × 10^(-2)

=> Same numeric value of 2, but different (unscaledValue, scale) pairs.
```

Inspecting the actual values:

| Property | `new BigDecimal("2.0")` | `new BigDecimal("2.00")` |
|---|---:|---:|
| `toString()` | `2.0` | `2.00` |
| `unscaledValue()` | `20` | `200` |
| `scale()` | `1` | `2` |
| `precision()` | `2` | `3` |
| Numeric value | `2` | `2` |

Here `precision()` is the number of digits in the unscaled part (20 has 2 digits, 200 has 3 digits). `precision` and `scale` are not the same concept.

**Role of the input string:** `new BigDecimal("2.0")` keeps scale 1, while `new BigDecimal("2.00")` keeps scale 2. This is useful when the representation conveys meaning such as entered precision, measurement unit, or number of digits to display.

## 3. Four ways to compare: `==`, `equals`, `compareTo`, `compareTo == 0`

| Expression | Result with `a=2.0`, `b=2.00` | What is being checked? |
|---|---|---|
| `a == b` | `false` | Whether both variables point to **the same object** |
| `a.equals(b)` | `false` | Whether both numeric value **and scale** are equal |
| `a.compareTo(b)` | `0` | Ordering relationship between the two numeric values |
| `a.compareTo(b) == 0` | `true` | Whether the two values are **numerically equal** |

### 3.1. The `==` operator: reference comparison

Because `BigDecimal` is an object, `==` checks whether two variables share the same object identity in the Java reference sense, not decimal value.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
BigDecimal c = a;

System.out.println(a == b); // false
System.out.println(a == c); // true
```

This is an illustrative snippet that must be placed inside a method (such as `main`) to run. `==` can return `true` when two variables hold the same reference, but it does not satisfy numeric comparison needs.

### 3.2. `equals(Object)`: numeric value and scale must match

The `BigDecimal.equals` contract requires two `BigDecimal` objects to have the same numeric value **and the same scale**. Therefore:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00"));  // false
new BigDecimal("2.0").equals(new BigDecimal("2.0"));   // true
new BigDecimal("2.00").equals(new BigDecimal("2.00")); // true
```

Do not interpret `false` in the first example as "2.0 differs from 2.00 in magnitude." The two objects differ under the **`equals` criterion** because their scales differ. The `hashCode()` contract also aligns with `equals`, so representations with different scales usually have different hash codes; do not use hash codes to conclude whether two numbers are numerically equal.

### 3.3. `compareTo(BigDecimal)`: comparing by numeric value

`compareTo` returns:

- A **negative** number if the left object is less than the right object.
- **0** if the two numeric values are equal.
- A **positive** number if the left object is greater than the right object.

Examples:

```java
new BigDecimal("2.0").compareTo(new BigDecimal("2.00")); // 0
new BigDecimal("1.9").compareTo(new BigDecimal("2.00")); // negative
new BigDecimal("2.1").compareTo(new BigDecimal("2.00")); // positive
```

**Do not rely on the result being exactly `-1` or `1`**: the contract only guarantees the sign of the result. Write `a.compareTo(b) < 0`, `> 0`, and `== 0` for less than, greater than, and equal to.

### 3.4. Comparing `compareTo(b) == 0`: checking numeric equality

This is the common choice when business rules only care about quantity or magnitude:

```java
boolean sameNumericValue = a.compareTo(b) == 0; // true
```

`compareTo` itself is an ordering comparison; adding `== 0` yields a boolean expression. Do not write `a.compareTo(b).equals(0)`: the return type of `compareTo` is primitive `int` and has no `equals` method.

## 4. Complete Java example: printing each result

**File `BigDecimalComparisonDemo.java`** — run with Java 17+:

```java
import java.math.BigDecimal;

public class BigDecimalComparisonDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal sameReference = a;

        System.out.println("a=" + a + ", scale=" + a.scale()
                + ", precision=" + a.precision()
                + ", unscaled=" + a.unscaledValue());
        System.out.println("b=" + b + ", scale=" + b.scale()
                + ", precision=" + b.precision()
                + ", unscaled=" + b.unscaledValue());

        System.out.println("a == b: " + (a == b));
        System.out.println("a == sameReference: " + (a == sameReference));
        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.compareTo(b): " + a.compareTo(b));
        System.out.println("a.compareTo(b) == 0: "
                + (a.compareTo(b) == 0));
        System.out.println("a.stripTrailingZeros().equals(b.stripTrailingZeros()): "
                + a.stripTrailingZeros().equals(b.stripTrailingZeros()));
        System.out.println("a.setScale(2).equals(b): "
                + a.setScale(2).equals(b));
    }
}
```

Run commands:

```bash
javac BigDecimalComparisonDemo.java
java BigDecimalComparisonDemo
```

Exact output:

```text
a=2.0, scale=1, precision=2, unscaled=20
b=2.00, scale=2, precision=3, unscaled=200
a == b: false
a == sameReference: true
a.equals(b): false
a.compareTo(b): 0
a.compareTo(b) == 0: true
a.stripTrailingZeros().equals(b.stripTrailingZeros()): true
a.setScale(2).equals(b): true
```

There are two different ways to make `equals` return `true` in the last lines: removing unnecessary zeros with `stripTrailingZeros()`, or unifying both numbers to **the same scale 2**. Both return a new `BigDecimal` object or an adjusted result; the input objects are not mutated because `BigDecimal` is immutable.

## 5. Comparing the consequences of the four comparison operations in collections

For `2.0` and `2.00`, `equals` returns false while `compareTo` returns 0. Hash-based structures rely on **equals/hashCode**; tree-based structures under natural ordering rely on **compareTo**:

| Collection | Result when adding 2.0 then 2.00 | Reason |
| --- | --- | --- |
| `HashSet` | Two elements | Different equals |
| `HashMap` | Two keys | Different equals/hashCode |
| `TreeSet` | One element | compareTo == 0 |
| `TreeMap` | One key, later value overwrites | compareTo == 0 |

```java
Set<BigDecimal> hash = new HashSet<>();
hash.add(new BigDecimal("2.0"));
hash.add(new BigDecimal("2.00"));
Set<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("2.0"));
tree.add(new BigDecimal("2.00"));
// hash.size() == 2, tree.size() == 1
```

This snippet goes inside a method and needs imports for `BigDecimal`, `Set`, `HashSet`, and `TreeSet`. The lesson **BigDecimal.hashCode and consequences in HashSet or HashMap** analyzes key lookup; the lesson **Consequences when using TreeSet or TreeMap** analyzes `contains`, `remove`, `put`, `get`, and comparators. The current example only demonstrates the difference for **the pair 2.0 and 2.00 itself**.

## 6. Normalization can change the result of equals

If you only ask whether two numbers have the same value, use `a.compareTo(b) == 0` directly. When you need to build a consistent value-based key, you can call `stripTrailingZeros()` on both sides:

```java
BigDecimal a = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("2.00").stripTrailingZeros();
// a.equals(b) == true
```

However, `stripTrailingZeros()` can turn `1000.00` into `1E+3` (negative scale) or erase the scale of zero. A **fixed scale** policy such as `setScale(2, RoundingMode.UNNECESSARY)` preserves two digits while rejecting `2.001` because rounding would be required. Normalization is a separate domain decision for keys/storage; there is no need to do it just for numeric comparison. The lesson **Scale normalization policy before storing or comparing** goes into depth on choosing boundaries and handling rounding.
## 7. Initialization pitfall: `2.0` and `2.00` as `double`

The snippet below creates **two identical `double` literal values**:

```java
double x = 2.0;
double y = 2.00;
System.out.println(x == y); // true
```

The `double` type does not record how many zeros the author wrote after the decimal point. Therefore:

| Object creation | `BigDecimal` representation | Scale |
|---|---|---:|
| `new BigDecimal("2.0")` | `2.0` | 1 |
| `new BigDecimal("2.00")` | `2.00` | 2 |
| `BigDecimal.valueOf(2.00)` | `2.0` | 1 |
| `new BigDecimal(2.00)` | `2` | 0 |
| `BigDecimal.valueOf(2L)` | `2` | 0 |

`BigDecimal.valueOf(double)` uses the canonical decimal representation from `Double.toString(double)`. For the exact value 2.0, that string is `"2.0"`. The `BigDecimal(double)` constructor converts the exact binary value received into a `BigDecimal`; 2 is an integer that is represented exactly, so the result has scale 0 in this example.

**Do not generalize the conclusion "the double constructor is exact in base 10" to all numbers.** For example, `0.1` has no finite binary representation; `new BigDecimal(0.1)` will expose a very long discrepancy compared to the decimal value `0.1` that users normally expect. To preserve the original digits, accept input as a `String` and pass it to the `BigDecimal(String)` constructor.

## 8. Operations can change scale and `equals` results

Scale does not only affect comparisons; it can also propagate through arithmetic results:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.add(b));      // 4.00
System.out.println(a.multiply(b)); // 4.000
```

For exact unrounded addition, the result scale is usually `max(scale(a), scale(b))`; here `max(1, 2) = 2`. For exact multiplication, the result scale is usually the sum of the two scales; here `1 + 2 = 3`.

Consequence: two sequences of operations can produce `BigDecimal` values with the same numeric value but different scales, so `equals` differs from `compareTo == 0`. When verifying computed values in financial, measurement, or test scenarios, define comparison criteria independent of formatting.

## 9. Choosing the right comparison for your goal

| Goal | Recommended approach | Reason |
|---|---|---|
| Check whether two variables point to the same object | `a == b` | Checks reference identity only |
| Check whether value **and scale** are identical | `a.equals(b)` | Follows the `BigDecimal.equals` contract |
| Check whether two numeric values are equal | `a.compareTo(b) == 0` | Ignores trailing zero/scale differences |
| Check less than / greater than | `a.compareTo(b) < 0` or `> 0` | Numeric ordering |
| Have `HashSet`/`HashMap` keys merge numerically equivalent forms | Normalize keys using one consistent convention | `HashSet` and `HashMap` use `equals`/`hashCode` |
| Store both `2.0` and `2.00` in an ordered set | `TreeSet` with a comparator that also checks scale | Natural ordering only checks numeric value |
| Keep exactly 2 digits for display/bookkeeping | `setScale(2, mode)` per policy | Scale is part of formatting and domain contract |

**Null handling:** `a.equals(b)` and `a.compareTo(b)` will fail if `a == null`. If `null` is allowed, check beforehand; do not assume `null` is equivalent to 0. `Objects.equals(a,b)` handles null safely but still uses `equals` semantics, meaning it still returns `false` for `2.0` and `2.00`.

**Testing:** With `assertEquals(expected, actual)` (for example in JUnit), frameworks usually rely on `equals`, so an expected object `2.00` may not equal an actual result `2.0`. If a test requires numeric equality, check `expected.compareTo(actual) == 0` with an appropriate assertion. Only use `equals` when scale itself is a requirement under test.

## 10. Exercises and solutions

1. **Given `a = 2.0`, `b = 2.00` (both initialized from strings). What do `a.equals(b)` and `a.compareTo(b) == 0` return?**  
   Answer: `false` and `true`. The scales differ, but the numeric values are equal.
2. **Create `c = new BigDecimal("2.0")`. What do `a.equals(c)` and `a == c` return?**  
   Answer: `true` and `false` if `a` and `c` were created by two separate `new` calls: same value/scale, but different objects.
3. **If a `HashSet` adds `2.0` and then `2.00`, how many elements does it have? What about a natural-order `TreeSet`?**  
   Answer: `HashSet` has 2; `TreeSet` has 1. The two sets use different criteria to determine duplicates.
4. **What is `new BigDecimal("2.00").stripTrailingZeros().scale()`?**  
   Answer: `0`, because the normalized representation is `2`.
5. **After `new BigDecimal("2.0").setScale(2)`, what is `equals(new BigDecimal("2.00"))`?**  
   Answer: `true`: both value and scale match.
6. **Why does `BigDecimal.valueOf(2.00)` not preserve 2 decimal digits?**  
   Answer: `2.00` was already converted into a `double`, losing information about how it was written; `Double.toString` represents it as `"2.0"`.

## 11. Key takeaways

`2.0` and `2.00` have the **same numeric value** but are **two `BigDecimal` representations with different scales** when created from strings. Choose the criterion according to your intent:

- Use `compareTo() == 0` for **numeric equality**.
- Use `equals()` when **scale is also part of equality**.
- Use `==` only when you genuinely need to ask **whether two references point to the same object**.
- For collections, remember `HashSet`/`HashMap` follow `equals`, whereas natural-order `TreeSet`/`TreeMap` follow `compareTo`.
- Normalize with `stripTrailingZeros` or `setScale` only when data rules allow changing the representation.

Official documentation:

- [Java 21 — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java 21 — `Comparable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html)
- [Java 21 — `TreeSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html)
