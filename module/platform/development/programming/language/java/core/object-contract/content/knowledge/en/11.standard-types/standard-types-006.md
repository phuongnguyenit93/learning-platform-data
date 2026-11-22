# Why can `BigDecimal.compareTo()` be 0 when `equals()` is `false`?

## 1. Two different questions: arithmetically equal or object-equal?

`java.math.BigDecimal` stores decimal numbers with arbitrary precision. A key characteristic is that each `BigDecimal` consists of an **unscaled integer value** (`unscaledValue`) and a **scale**. Its mathematical value is computed by:

```text
value = unscaledValue × 10^(-scale)
```

Examples:

| Representation | `unscaledValue()` | `scale()` | Mathematical value |
| --- | ---: | ---: | ---: |
| `new BigDecimal("2.0")` | 20 | 1 | 2 |
| `new BigDecimal("2.00")` | 200 | 2 | 2 |
| `new BigDecimal("2")` | 2 | 0 | 2 |
| `new BigDecimal("2E+1")` | 2 | -1 | 20 |

Therefore, two `BigDecimal` instances can represent the **same number** yet differ in **scale**. Java intentionally uses two different rules:

- **`a.compareTo(b) == 0`**: equal in **numeric value**; 2.0 and 2.00 are treated as equivalent.
- **`a.equals(b)`**: equal under the `BigDecimal.equals(Object)` contract; **both numeric value and scale** must match.

This is behavior defined in the `BigDecimal` API, not a rounding bug or floating-point error. `BigDecimal` stores exact decimal digits from the input string.

**Direct conclusion:** `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` is `true`, whereas `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` is `false`.

## 2. Signature and contract of each method

```java
int compareTo(BigDecimal val)
boolean equals(Object obj)
int hashCode()
```

The declarations above are **illustrative signatures**; this is not a standalone Java program.

### `compareTo(BigDecimal)` compares numeric ordering

The return value is:

- **Negative** if the receiver is less than the argument.
- **0** if both numbers are equal in mathematical value.
- **Positive** if the receiver is greater than the argument.

Do not check specifically for `-1` or `1`; the API only guarantees the sign of the result. For `BigDecimal`, `compareTo` ignores differences that do not change the numeric value, such as trailing zeros in the fractional part.

### `equals(Object)` additionally requires equal scale

For two `BigDecimal` instances, `equals` checks both **value and scale**. Hence `2.0`, `2.00`, and `2` are three distinct representations under `equals`, even though `compareTo` returns 0 between every pair.

`equals` also does not consider a `BigDecimal` equal to another numeric type such as `Integer` or `Double`, even if they represent the same mathematical value. `compareTo` is a comparison method **against `BigDecimal`**, not an arbitrary comparison tool across `Number` subclasses.

### `hashCode()` must be compatible with equals

If `a.equals(b)` is `true`, they must have the same hash code. However, `BigDecimal` instances with **the same numeric value but different scales** may have different hashes. Because `equals` already treats them as unequal, that is completely valid.

Never use `compareTo == 0` to conclude that two objects are the same key in a `HashMap`, because `HashMap` uses the `equals` and `hashCode` contract, not the natural ordering from `compareTo`.

## 3. Java 17+ example: seeing the difference clearly

Create the file `BigDecimalEqualityDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println(a.scale());
        System.out.println(b.scale());
        System.out.println(a.compareTo(b) == 0);
        System.out.println(a.equals(b));

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        System.out.println(hashSet.size());

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);
        System.out.println(treeSet.size());

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "A");
        hashMap.put(b, "B");
        System.out.println(hashMap.size());
        System.out.println(hashMap.get(new BigDecimal("2.000")));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "A");
        treeMap.put(b, "B");
        System.out.println(treeMap.size());
        System.out.println(treeMap.get(new BigDecimal("2.000")));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
```

Result:

```text
1
2
true
false
2
1
2
null
1
B
```

Step-by-step explanation:

1. `a.scale()` is 1; `b.scale()` is 2.
2. `a.compareTo(b) == 0` is `true` because both represent the number 2.
3. `a.equals(b)` is `false` because their scales differ.
4. `HashSet` has **2 elements**: the hash-based structure distinguishes them via the `equals/hashCode` contract.
5. `TreeSet` has **1 element**: under natural ordering, `compareTo == 0` is used to identify duplicate elements in the tree.
6. `HashMap` has **2 keys**. Key `2.000` (scale 3) is not `equals` to the added scale-1 or scale-2 keys, so `get` returns `null`.
7. `TreeMap` has **1 key under natural ordering**: inserting `b` updates the value to `"B"` for the key equivalent to `a` under `compareTo`. Looking up `2.000` still retrieves `"B"`.

This is an important distinction when the same dataset passes through different collection structures.

## 4. Why can HashSet and TreeSet give different results?

`HashSet` determines whether an element already exists using hashing and equality (same reference or `equals`). `HashMap` uses the same basis to identify **keys**.

In contrast, `TreeSet` and `TreeMap` maintain order via `Comparable.compareTo` or a supplied `Comparator`. They treat two elements or keys as **order-equivalent** when comparison returns 0.

For `BigDecimal`:

```text
a = 2.0 (scale 1)         b = 2.00 (scale 2)
        |                          |
        +---- compareTo == 0 ------+     same numeric value
        |                          |
        +---- equals == false -----+     different representation/scale

HashSet / HashMap: treat as two distinct keys/elements
TreeSet / TreeMap: treat as the same key/element under natural ordering
```

`BigDecimal` is a prominent example of **natural ordering inconsistent with equals**: its natural order does not align with `equals`. Normally, the `Comparable` API recommends ensuring `compareTo(a, b) == 0` matches `a.equals(b)`, but that is not a strict requirement satisfied by every `Comparable` class. For `BigDecimal`, the difference is explicitly stated in the Java documentation.

Consequence: a `TreeSet<BigDecimal>` using natural ordering may not obey the general equality semantics you expect from `Set`, because "duplicates" are decided by `compareTo` rather than `equals`. Calling code must know the collection's equivalence criterion.

If the requirement is **each numeric value appears only once**, `TreeSet` with natural ordering may fit. If the requirement is **preserve scale distinctions**, `HashSet` using default `equals` behaves differently; or you must define a comparator compatible with `equals` if ordering is still needed.

Example of a comparator that distinguishes scale after comparing numeric values:

```java
Comparator<BigDecimal> byValueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
```

This is an **illustrative code snippet**, requiring `import java.math.BigDecimal;` and `import java.util.Comparator;`. For finite `BigDecimal` values, this comparator returns 0 when both numeric value and scale match, corresponding to `BigDecimal.equals`. When used with `TreeSet<>(byValueThenScale)`, the two elements `2.0` and `2.00` are stored separately.

## 5. Why does preserving scale matter?

Scale is not always meaningless formatting trivia. It can indicate precision or a convention on the number of decimal places:

- `2.0` and `2.00` are the same number, yet may come from two different measurements or display rules.
- In decimal arithmetic, the choice of scale can affect **the result's scale**, division behavior, and rounding needs.
- In monetary representation, data may require exactly two decimal places; `2.00` fits better than `2` if the storage format expects scale 2.

For example, exact division can preserve differences in scale:

```java
new BigDecimal("2.0").divide(new BigDecimal("3"),
                            2, RoundingMode.HALF_UP);
```

The illustrative snippet above requires `import java.math.BigDecimal;` and `import java.math.RoundingMode;`, returning the mathematical value 0.67 with scale 2. The scale and rounding mode parameters are specified explicitly to avoid implicit dependence on input precision.

Note that **scale does not by itself prove business meaning**. If the system treats 2.0 and 2.00 as the same value, define that rule explicitly in the API or at data boundaries rather than relying on default `equals` when it does not match.

## 6. How to get equality by numeric value

Before using `BigDecimal` as a key or set element, clearly choose the **equivalence relation**. The two representations `2.0` and `2.00` share the same numeric value yet differ under `equals`. There are three approaches for three goals, which should not be mixed:

### Approach A — Only need to ask whether two numbers have the same value

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
boolean numericallyEqual = a.compareTo(b) == 0; // true
~~~

This is a direct comparison; it **does not change** `equals` or `hashCode`. When two unnormalized numbers are used as `HashMap` keys, they remain two distinct keys. `compareTo(null)` throws `NullPointerException`; handle `null` beforehand according to your data rules.

### Approach B — Want one hash key per numeric value

Normalize at **both storage and lookup time**, before placing the numbers into a `HashMap` or `HashSet`:

~~~java
BigDecimal first = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal second = new BigDecimal("2.00").stripTrailingZeros();
Set<BigDecimal> values = new HashSet<>();
values.add(first);
values.add(second);
System.out.println(values.size()); // 1
~~~

This snippet uses imports `java.math.BigDecimal`, `java.util.Set`, and `java.util.HashSet`; it can be placed inside `main`. Both normalized values have scale 0. If you write a custom key whose `equals` uses `compareTo == 0`, **`hashCode` must also be based on the normalized representation**, rather than directly using `BigDecimal.hashCode` on values with arbitrary scale.

Remember that `stripTrailingZeros()` can produce a **negative scale**: `1000.00` becomes `1E+3`, and `0.000` normalizes to zero with scale 0. Therefore, this approach is **unsuitable if the original scale is business data that must be kept**.

### Approach C — Business domain mandates a fixed scale

For example, an application mandates exactly two decimal places:

~~~java
BigDecimal amount = new BigDecimal("2.0")
        .setScale(2, RoundingMode.UNNECESSARY); // 2.00
~~~

Requires `import java.math.RoundingMode`. The `UNNECESSARY` mode causes the program to throw `ArithmeticException` if an input like `2.001` cannot be converted to scale 2 without rounding. If rounding is allowed, choose `RoundingMode` according to business policy rather than defaulting to `HALF_UP`.

**Quick guide:** compare two individual numbers → `compareTo`; deduplicate by value in hash collections → normalize keys consistently; need to preserve exact specified precision/representation → fixed scale and controlled rounding. Sections 3 and 4 above already include complete programs verifying the difference between hash-based and sorted structures.

## 7. Common mistakes when working with BigDecimal

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| Using `equals` to ask "do two numbers have the same mathematical value?" | `equals` also compares scale | Use `compareTo(...) == 0` |
| Using `compareTo == 0` and assuming `HashSet` will merge elements | HashSet relies on `equals/hashCode` | Normalize before inserting or choose the appropriate collection/comparison |
| Treating `compareTo == 0` as a sign that `hashCode` must match | The hash contract only requires matching hashes when `equals == true` | Understand the two distinct equality conditions |
| Using `==` to compare two `BigDecimal` objects | `==` checks reference identity | Choose `equals` or `compareTo` per purpose |
| Creating a decimal via `new BigDecimal(0.1)` and expecting exact 0.1 | `0.1` as `double` is a binary approximation | Prefer `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` |
| Calling `stripTrailingZeros` and expecting `toString()` to keep plain decimal form | Can switch to scientific notation with negative scale | Use `toPlainString` to display without exponents when appropriate |
| Switching equality criteria across different parts of a system | Lookup keys and set results diverge | Document scale, rounding, and normalization policies at boundaries |

Note that `BigDecimal` is immutable: `setScale` and `stripTrailingZeros` return a `BigDecimal` result without mutating the original object. To use the normalized result, you must reassign the variable or store the returned value.

## 8. Checklist before using BigDecimal as a key or set element

1. Define the "duplicate" criterion: **same numeric value** or **same value and scale**?
2. If only comparing two numbers for business logic, use `compareTo` and check for **a result of 0**.
3. If using `HashMap<BigDecimal, ...>` or `HashSet<BigDecimal>`, remember that scale is part of equality; normalize inputs if the goal is numeric deduplication.
4. If using `TreeMap`/`TreeSet`, understand that the comparator or natural ordering decides when two keys/elements are equivalent. If scale must be distinguished, add scale as a criterion in the comparator.
5. For data with fixed decimal rules, specify scale and rounding mode explicitly, especially before storing and looking up keys.
6. When normalizing with `stripTrailingZeros`, test **0** and numbers with many trailing zeros like `1000.00`, because the result may have a negative scale.
7. Write tests covering `2.0`, `2.00`, `2`, `0.000`, and cases requiring rounding. Test the difference between `HashSet` and `TreeSet` if the system uses both.

**Self-check:**

- What does `new BigDecimal("5.0").compareTo(new BigDecimal("5.00"))` return? **0**.
- What does `new BigDecimal("5.0").equals(new BigDecimal("5.00"))` return? **`false`**, because the scales are 1 and 2.
- If you add both objects to a `HashSet`, how many elements will it have? **2**.
- If you add them to a `TreeSet` using natural ordering, how many elements will it have? **1**.
- How do you make them equal under `equals` when used as hash keys by numeric value? **Normalize with the same rule**, for example using `stripTrailingZeros()` before adding and looking up.

**Remember:** For `BigDecimal`, **`compareTo == 0` is about numeric value**, while **`equals == true` is about numeric value together with scale**. This difference determines how `HashMap`, `HashSet`, `TreeMap`, and `TreeSet` identify duplicate values; choose a criterion consistent with your application's needs.
