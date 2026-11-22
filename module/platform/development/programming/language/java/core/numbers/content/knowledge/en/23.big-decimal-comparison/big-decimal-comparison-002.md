# `BigDecimal.equals()` checks both value and scale

When working with `BigDecimal`, two objects can be **equal in numeric value** while `equals()` still returns `false`. The reason: `BigDecimal.equals(Object)` checks **both value and `scale`**. Therefore `new BigDecimal("2.0")` is not `equals()` to `new BigDecimal("2.00")`, even though both numbers have the value 2.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));         // false
System.out.println(a.compareTo(b) == 0); // true
```

This distinction directly affects conditional checks, `HashSet`/`TreeSet`, `HashMap`/`TreeMap` keys, and how `equals`/`hashCode` are designed for domain classes.

## 1. Numeric value and scale are two different properties

A `BigDecimal` has the form:

```text
value = unscaledValue × 10^(-scale)
```

`unscaledValue` is an integer coefficient, while `scale` determines the decimal point position in the representation.

| Creation | `unscaledValue()` | `scale()` | Numeric value |
|---|---:|---:|---:|
| `new BigDecimal("2")` | 2 | 0 | 2 |
| `new BigDecimal("2.0")` | 20 | 1 | 2 |
| `new BigDecimal("2.00")` | 200 | 2 | 2 |
| `new BigDecimal("2E+0")` | 2 | 0 | 2 |
| `new BigDecimal("1000")` | 1000 | 0 | 1000 |
| `new BigDecimal("1E+3")` | 1 | -3 | 1000 |

Rules for `equals()`:

- The argument must be a `BigDecimal`.
- The numeric values must be equal.
- **The scales must be equal**.

Consequences:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00")); // false
new BigDecimal("2.00").equals(new BigDecimal("2.00")); // true
new BigDecimal("2").equals(new BigDecimal("2E+0"));  // true
new BigDecimal("1000").equals(new BigDecimal("1E+3")); // false
```

Scale can be negative, zero, or positive. Therefore, you should not define scale simply as "how many digits follow the decimal point in the input string"; the `unscaledValue × 10^(-scale)` model covers scientific notation as well.

**Even zero has a scale**: `new BigDecimal("0.00")` has scale 2; `BigDecimal.ZERO` has scale 0. They have the same mathematical value 0, yet `equals()` returns `false`.

## 2. `equals()` and `compareTo()` answer different questions

- `a.equals(b)`: do the two representations have **the same value and the same scale**?
- `a.compareTo(b)`: in terms of **numeric value**, is `a` less than, equal to, or greater than `b`?

`compareTo()` returns a negative number, 0, or a positive number; **0** means the two numeric values are equal. It does not require matching scales.

| `a` | `b` | `a.equals(b)` | `a.compareTo(b)` |
|---|---|---|---:|
| `2.0` | `2.00` | `false` | 0 |
| `2.00` | `2.00` | `true` | 0 |
| `0.0` | `0` | `false` | 0 |
| `1000` | `1E+3` | `false` | 0 |
| `1.99` | `2.00` | `false` | Negative number |
| `2.01` | `2.00` | `false` | Positive number |

When comparing by **numeric value**:

```java
boolean sameNumericValue = a.compareTo(b) == 0;
boolean smaller = a.compareTo(b) < 0;
boolean greater = a.compareTo(b) > 0;
```

Do not assume `compareTo()` always returns exactly `-1` or `1`; the `Comparable` contract only guarantees the sign of the result.

When comparing by **both value and scale**, for example checking whether a representation has the required number of decimal digits:

```java
boolean sameRepresentationValue = a.equals(b);
```

Java explicitly states that **the natural ordering of `BigDecimal` is inconsistent with `equals()`**: there are pairs where `compareTo() == 0` yet `equals() == false`. This is intentional design behavior.

## 3. `equals()`, `hashCode()`, and consequences for collections

General rule in Java: if `a.equals(b)` then `a.hashCode() == b.hashCode()`. `BigDecimal.hashCode()` includes scale, so `2.0` and `2.00` can have different hash codes. You must not conclude the converse—that equal hash codes guarantee the two objects are `equals()`—because hash collisions can occur.

Two groups of collections use different criteria:

| Structure | Default equivalence criterion | `2.0` and `2.00` |
|---|---|---|
| `HashSet<BigDecimal>` | `equals()` / `hashCode()` | Two elements |
| `HashMap<BigDecimal, V>` | `equals()` / `hashCode()` | Two keys |
| `TreeSet<BigDecimal>` | `compareTo() == 0` | One element |
| `TreeMap<BigDecimal, V>` | `compareTo() == 0` | One equivalent key |

Example:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

Set<BigDecimal> hash = new HashSet<>(List.of(a, b));
Set<BigDecimal> tree = new TreeSet<>(List.of(a, b));

System.out.println(hash.size()); // 2
System.out.println(tree.size()); // 1
```

`HashSet` keeps both because `equals()` returns `false`. `TreeSet` uses natural ordering, so `compareTo() == 0` makes the two values one equivalent element in sort order.

The same applies to `Map`. If you call `map.put(new BigDecimal("2.0"), "A")` on a `HashMap`, calling `map.get(new BigDecimal("2.00"))` will not find the mapping. On a `TreeMap` using natural ordering, `put` with the second key replaces the value associated with the first equivalent key.

**Important pitfall:** switching between `HashSet` and `TreeSet`, or between `HashMap` and `TreeMap`, can change how many elements or keys are considered unique when the key type is `BigDecimal`.

## 4. Complete Java 17+ example

Create the file `BigDecimalEqualsDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalEqualsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("a.scale() = " + a.scale());
        System.out.println("b.scale() = " + b.scale());
        System.out.println("a.equals(b) = " + a.equals(b));
        System.out.println("a.compareTo(b) = " + a.compareTo(b));
        System.out.println("numeric equality = " + (a.compareTo(b) == 0));

        Set<BigDecimal> hash = new HashSet<>(List.of(a, b));
        Set<BigDecimal> tree = new TreeSet<>(List.of(a, b));
        System.out.println("HashSet size = " + hash.size());
        System.out.println("TreeSet size = " + tree.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        System.out.println("HashMap get b = " + hashMap.get(b));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");
        System.out.println("TreeMap size = " + treeMap.size());
        System.out.println("TreeMap get a = " + treeMap.get(a));

        BigDecimal normalizedA = a.stripTrailingZeros();
        BigDecimal normalizedB = b.stripTrailingZeros();
        System.out.println("normalized equals = "
                + normalizedA.equals(normalizedB));

        BigDecimal fixedScale = a.setScale(2);
        System.out.println("setScale(2) equals b = "
                + fixedScale.equals(b));

        BigDecimal normalizedZero =
                new BigDecimal("0.00").stripTrailingZeros();
        System.out.println("normalized zero = " + normalizedZero
                + ", scale=" + normalizedZero.scale());

        BigDecimal normalizedThousand =
                new BigDecimal("1000.00").stripTrailingZeros();
        System.out.println("normalized thousand = " + normalizedThousand
                + ", scale=" + normalizedThousand.scale());
    }
}
```

Compile and run:

```bash
javac BigDecimalEqualsDemo.java
java BigDecimalEqualsDemo
```

Exact stdout:

```text
a.scale() = 1
b.scale() = 2
a.equals(b) = false
a.compareTo(b) = 0
numeric equality = true
HashSet size = 2
TreeSet size = 1
HashMap get b = null
TreeMap size = 1
TreeMap get a = second
normalized equals = true
setScale(2) equals b = true
normalized zero = 0, scale=0
normalized thousand = 1E+3, scale=-3
```

The `TreeMap` section keeps only one equivalent key according to `compareTo`; the `put(b, "second")` call updates the value from `"first"` to `"second"`. Meanwhile, `HashMap.get(b)` returns `null` because the original key `a` has a different scale from `b`.

The `stripTrailingZeros()` section shows that when trailing zeros in the coefficient are removed, `2.0` and `2.00` collapse to the same representation `2`. `setScale(2)` instead converts `2.0` into `2.00` without needing to round.

## 5. Choosing a comparison method based on business rules

### Case A: only caring about numeric value

For example, two totals have the same value even though one source returns `125.0` and another returns `125.00`:

```java
BigDecimal fromA = new BigDecimal("125.0");
BigDecimal fromB = new BigDecimal("125.00");

boolean sameAmount = fromA.compareTo(fromB) == 0; // true
```

If you only need to check equality at one point in time, `compareTo() == 0` expresses the intent clearly and requires no data transformation.

### Case B: needing keys for `HashMap` or elements in `HashSet`

If you want `125`, `125.0`, and `125.00` to act as the same key, you must **normalize on insertion and on lookup**. One way is `stripTrailingZeros()`:

```java
Map<BigDecimal, String> lookup = new HashMap<>();

BigDecimal entered = new BigDecimal("125.00");
lookup.put(entered.stripTrailingZeros(), "matched");

BigDecimal query = new BigDecimal("125.0");
String found = lookup.get(query.stripTrailingZeros());
// found = "matched"
```

`stripTrailingZeros()` preserves the mathematical value while normalizing the representation:

- `2.0` and `2.00` both become `2`.
- Zero at any scale becomes `BigDecimal.ZERO`, scale 0.
- `1000.00` can become `1E+3`, scale -3. Negative scale is valid, and the display form may switch to scientific notation.

`stripTrailingZeros()` does not modify the original object because `BigDecimal` is immutable; use the returned value.

### Case C: needing to normalize to an exact domain scale

If the convention requires monetary amounts to have **scale 2**, you can normalize to scale 2:

```java
BigDecimal a = new BigDecimal("125.0").setScale(2);
BigDecimal b = new BigDecimal("125.00").setScale(2);
System.out.println(a.equals(b)); // true
```

**Increasing** scale by adding trailing zeros does not change the value. However, **decreasing** scale is not always exact:

```java
new BigDecimal("125.000").setScale(2); // 125.00: exact
new BigDecimal("125.001").setScale(2); // ArithmeticException
```

To allow discarding excess digits, an explicit rounding rule is needed, such as `setScale(2, RoundingMode.HALF_UP)`. Do not round automatically if the goal is to evaluate whether **two original numbers** are equal: after rounding, two different numbers can become the same number.

### Case D: application needs to preserve scale

In measurement data, contracts, or input formats, `1.0` and `1.00` sometimes carry different representational meaning. If business rules require distinguishing them, use `equals()` and do not normalize away the scale. This decision must be consistent across comparison, storage, and indexing.

## 6. When `BigDecimal` is a field in another class's `equals()`/`hashCode()`

A subtle bug: a domain class uses `amount.compareTo(other.amount) == 0` in `equals()`, but calls unnormalized `amount.hashCode()` in `hashCode()`. When `2.0` and `2.00` are considered equal by `equals()` yet have different hash codes, that class violates Java's hash contract. `HashMap` and `HashSet` can behave unexpectedly.

A simple approach is to **normalize once when creating the key**, then let `equals()` and `hashCode()` automatically use the same canonical representation:

```java
import java.math.BigDecimal;

public record AmountKey(BigDecimal value) {
    public AmountKey {
        value = value.stripTrailingZeros();
    }
}
```

This is a standalone example of a `record` in Java 17. For a non-null `value`, the two keys `new AmountKey(new BigDecimal("2.0"))` and `new AmountKey(new BigDecimal("2.00"))` have the same normalized state; the `record` generates consistent `equals()` and `hashCode()`. If `null` must be accepted, the class must specify and handle that case separately.

If the application needs to distinguish scale, do not use this normalization approach: preserve the original value and scale in comparisons.

## 7. Common mistakes and how to avoid them

1. **Using `==` with two `BigDecimal` objects.** `==` compares references, not values. Use `equals()` or `compareTo()` depending on your intent.
2. **Confusing `equals()` with `compareTo() == 0`.** One checks scale as well; the other checks only numeric value.
3. **Using `HashMap` with inconsistent input scales.** Storing key `5.00` and looking up `5.0` may fail to find a match. Normalize at both ends if you only care about value.
4. **Switching from `HashSet` to `TreeSet` and thinking data is lost randomly.** The difference in element count comes from the equivalence mechanisms of the two collections.
5. **Assuming `stripTrailingZeros()` preserves scale or `toString()`.** The value does not change, but `1000.00` can become `1E+3` with scale -3.
6. **Calling `setScale` without handling cases that require rounding.** If decreasing scale must discard non-zero digits, the call throws `ArithmeticException` when no rounding mode is supplied.
7. **Converting to `doubleValue()` to compare.** `double` can lose precision; keep comparisons in the `BigDecimal` domain.
8. **Assuming every way of creating 2 produces the same scale.** `BigDecimal.valueOf(2.0)` has scale 1, whereas `BigDecimal.valueOf(2L)` has scale 0.
9. **Forgetting the `null` case.** `a.compareTo(b)` requires valid arguments. `Objects.equals(a, b)` handles `null` but still uses `equals()` semantics, so it still checks scale when both are `BigDecimal`.

## 8. Self-check

**1.** What does `new BigDecimal("0.00").equals(BigDecimal.ZERO)` return?  
**Answer:** `false`, because scale 2 differs from scale 0. However, `compareTo() == 0`.

**2.** What does `new BigDecimal("1E+3").equals(new BigDecimal("1000"))` return?  
**Answer:** `false`, because scale -3 differs from scale 0, even though both have value 1000.

**3.** If you add `"1"`, `"1.0"`, and `"1.00"` to a default `HashSet<BigDecimal>` and `TreeSet<BigDecimal>`, what are their sizes?  
**Answer:** `HashSet` has size 3, `TreeSet` has size 1.

**4.** Why should a domain class not use `compareTo() == 0` for `equals()` while using the raw `BigDecimal.hashCode()`?  
**Answer:** Numbers with different scales can have `equals() == true` yet different hash codes, violating Java's contract.

**5.** When you need to distinguish whether a user entered `"2.0"` or `"2.00"`, what should you use?  
**Answer:** `equals()`, because scale is part of the comparison requirement.

**Key takeaway:** `BigDecimal.equals()` requires **the same numeric value and the same scale**. `BigDecimal.compareTo() == 0` only requires **the same numeric value**. Choose the criterion based on your goal before comparing or selecting a `Set`/`Map` implementation.
