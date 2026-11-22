# BigDecimal: natural ordering inconsistent with equals

In Java, `BigDecimal` has an error-prone characteristic: **two numerically equal values can be considered equal by `compareTo()` yet unequal by `equals()`**. For example, `new BigDecimal("2.0")` and `new BigDecimal("2.00")` both represent the number 2, but differ in the number of digits after the decimal point (`scale`). This difference directly affects sorting, deduplication, `contains()` checks, and key operations in `Set`/`Map`.

Lesson objectives:
- Accurately explain `Comparable`'s concept of **natural ordering consistent with equals** and why `BigDecimal` is an intentional exception.
- Predict the results of `compareTo()`, `equals()`, and `hashCode()` along with their impact on `HashSet`, `TreeSet`, `HashMap`, and `TreeMap`.
- Choose an appropriate comparison/normalization rule depending on whether the application treats **numeric value** or **representation with `scale`** as identity.
- Avoid losing `scale` data or unintentionally merging keys.

## 1. What does "natural ordering consistent with equals" mean?

A class implementing `Comparable<T>` has a **natural ordering** defined by the `compareTo(T other)` method. According to the `Comparable` contract, `compareTo()` returns a negative integer when the object comes before, a positive integer when it comes after, and `0` when the two objects are **order-equivalent**. Do not depend on the absolute magnitude of the return value, as other classes may return integers other than -1, 0, and 1.

A natural ordering is said to be **consistent with `equals`** if for *every* valid pair `a`, `b`:

~~~text
(a.compareTo(b) == 0)  ==  a.equals(b)
~~~

Here the outer `==` expresses equality between two `boolean` values: both statements must be true together or false together.

Java recommends this consistency because the `Set`/`Map` interfaces define identity via `equals()`, whereas sorted structures like `TreeSet`/`TreeMap` rely on **a comparison result of 0**. However, this is a strong recommendation rather than a mandatory condition to implement `Comparable`. The API documentation explicitly identifies `BigDecimal` as an exception because it uses one rule for **numeric ordering** and another rule for **representational equality**.

**Two statements that must be distinguished:**

1. `a.compareTo(b) == 0`: same numeric value; `scale` may differ.
2. `a.equals(b)`: same numeric value **and** same `scale`.

For `BigDecimal`, if `equals()` is `true`, then `compareTo() == 0` is also true; the converse is not necessarily true. This is an **inconsistency in equivalence relation**, not a bug in ascending/descending sorting or a violation of transitivity by `compareTo()`.

## 2. Origin: unscaled value and scale

`BigDecimal` represents a decimal number using an integer `unscaledValue` and a `scale`:

~~~text
numeric value = unscaledValue × 10^(-scale)
~~~

| Initialization string | `unscaledValue()` | `scale()` | Numeric value |
|---|---:|---:|---:|
| `"2"` | 2 | 0 | 2 |
| `"2.0"` | 20 | 1 | 2 |
| `"2.00"` | 200 | 2 | 2 |
| `"2E+0"` | 2 | 0 | 2 |
| `"0.00"` | 0 | 2 | 0 |
| `"0.000"` | 0 | 3 | 0 |

`compareTo()` looks at the **numeric value**, so it treats `2`, `2.0`, and `2.00` as equivalent. In contrast, `equals()` also checks `scale`, so `2.0` differs from `2.00` under this method. An easy way to remember this: adding trailing zeros after the decimal part can preserve *value* while changing *representation*.

Two values with the same `scale` and the same numeric value have the same `unscaledValue`, so `equals()` returns `true`. Formatting whitespace from input strings does not become a separate property in `BigDecimal` either; two different strings can produce `equals()` objects if they yield the exact same value/exponent pair.

## 3. Clear comparison of three checks

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
System.out.println(a == b);              // false
~~~

This is an *illustrative snippet placed inside a method* and requires `import java.math.BigDecimal;`. The full standalone runnable program is in section 5.

| Check | Criterion | `2.0` vs `2.00` |
|---|---|---|
| `a.compareTo(b) == 0` | Equal numeric value | `true` |
| `a.equals(b)` | Equal numeric value and `scale` | `false` |
| `a == b` | Same object reference | `false` with two separate `new` calls |
| `a.compareTo(b) < 0` | Less in numeric value | `false` |
| `a.compareTo(b) > 0` | Greater in numeric value | `false` |

**`hashCode()` follows `equals()`, not `compareTo()`.** Two objects with `equals() == true` must have the same `hashCode()`. Two objects that are only numerically equal with different `scale` are not guaranteed by `BigDecimal` to have the same hash; its hash function also incorporates `scale`. Therefore, hash-based structures do not automatically treat `2.0` and `2.00` as the same key.

Do not use `a.hashCode() == b.hashCode()` as an equality test: hash collisions can still happen, and hashes are only a bucket-selection mechanism while `equals()` confirms identity.

## 4. Why does this affect Set and Map?

The two families of data structures use different "duplicate" rules:

| Structure | Default duplicate rule | Do `2.0` and `2.00` coexist? |
|---|---|---|
| `HashSet<BigDecimal>` | `hashCode()` combined with `equals()` | **Yes**, two elements |
| `TreeSet<BigDecimal>` | `compareTo() == 0` if no comparator is specified | **No**, one element |
| `HashMap<BigDecimal, V>` | `hashCode()` combined with `equals()` on keys | **Yes**, two keys |
| `TreeMap<BigDecimal, V>` | `compareTo() == 0` if no comparator is specified | **No**, later `put` updates the value of the equivalent key |

`TreeSet`/`TreeMap` have behavior **well-defined by the sorting contract**, even though using `BigDecimal` with its natural ordering makes tree-based identity incompatible with how `Set`/`Map` normally express identity via `equals`.

This leads to two common bug patterns:
- A system needs to distinguish `2.0` and `2.00`, but switching from `HashSet` to `TreeSet` causes the second element not to be added.
- A system uses `TreeMap` to store data by unit price. Key `2.00` is treated as equivalent to `2.0`, causing a later `put` to **replace the old value** rather than creating a new entry.

Sorting by `compareTo()` is not "wrong" in itself; the problem arises when the business logic implicitly treats **each representation** as a separate identity while choosing a collection that merges by **numeric value**.

## 5. Standalone runnable Java 17+ program

Create the file `BigDecimalOrderDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalOrderDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("compareTo: " + a.compareTo(b));
        System.out.println("equals: " + a.equals(b));
        System.out.println("same scale: " + (a.scale() == b.scale()));

        HashSet<BigDecimal> hashSet = new HashSet<>();
        System.out.println("hash add a: " + hashSet.add(a));
        System.out.println("hash add b: " + hashSet.add(b));
        System.out.println("hash size: " + hashSet.size());

        TreeSet<BigDecimal> treeSet = new TreeSet<>();
        System.out.println("tree add a: " + treeSet.add(a));
        System.out.println("tree add b: " + treeSet.add(b));
        System.out.println("tree size: " + treeSet.size());
        System.out.println("tree contains b: " + treeSet.contains(b));

        HashMap<BigDecimal, String> hashMap = new HashMap<>();
        System.out.println("hash first put: " + hashMap.put(a, "first"));
        System.out.println("hash second put: " + hashMap.put(b, "second"));
        System.out.println("hash map size: " + hashMap.size());
        System.out.println("hash get a: " + hashMap.get(a));

        TreeMap<BigDecimal, String> treeMap = new TreeMap<>();
        System.out.println("tree first put: " + treeMap.put(a, "first"));
        System.out.println("tree second put: " + treeMap.put(b, "second"));
        System.out.println("tree map size: " + treeMap.size());
        System.out.println("tree get a: " + treeMap.get(a));
        System.out.println("tree first key: " + treeMap.firstKey());

        Comparator<BigDecimal> valueThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        TreeSet<BigDecimal> representationSet = new TreeSet<>(valueThenScale);
        representationSet.add(a);
        representationSet.add(b);
        System.out.println("representation size: " + representationSet.size());
        System.out.println("representation contents: " + representationSet);
    }
}
~~~

Compile and run:

~~~bash
javac BigDecimalOrderDemo.java
java BigDecimalOrderDemo
~~~

Output:

~~~text
compareTo: 0
equals: false
same scale: false
hash add a: true
hash add b: true
hash size: 2
tree add a: true
tree add b: false
tree size: 1
tree contains b: true
hash first put: null
hash second put: null
hash map size: 2
hash get a: first
tree first put: null
tree second put: first
tree map size: 1
tree get a: second
tree first key: 2.0
representation size: 2
representation contents: [2.0, 2.00]
~~~

Explanation of output:

1. `compareTo: 0` does not imply `equals: true` because `a.scale() == 1` while `b.scale() == 2`.
2. `HashSet` adds both. `TreeSet` adds `a` first, then rejects `b` because `compareTo() == 0`; `treeSet.contains(b)` still returns `true`. This does not mean element `b` itself was stored intact in the tree.
3. `HashMap.put(a, "first")` and `put(b, "second")` create two separate keys. `TreeMap.put(b, "second")` updates the entry matching in sort order, so it returns `"first"` and the size stays 1.
4. When `TreeMap` already has an equivalent key under the comparator, the second write replaces the existing entry's value; in the example `firstKey()` still prints `2.0`, the key object inserted first.
5. The custom comparator `valueThenScale` sorts by numeric value **and then compares `scale` if values are equal**, so it treats `a` and `b` as distinct and keeps both in `TreeSet`.

The program prints only sizes and lookup checks for `HashSet`/`HashMap`, avoiding any assumption that hash collection iteration order is fixed. This example does not use `double` to initialize input values.

## 6. Sorted collections use "comparator equality"

In `TreeSet`, `add()`, `contains()`, and `remove()` determine equivalent objects via `compareTo() == 0` when using natural ordering. In `TreeMap`, `put()`, `get()`, `containsKey()`, and `remove()` likewise use comparator equivalence for keys. A custom `Comparator` replaces `compareTo()` in those decisions.

Look closely at these two operations:

~~~java
TreeSet<BigDecimal> prices = new TreeSet<>();
prices.add(new BigDecimal("8.0"));

boolean found = prices.contains(new BigDecimal("8.00")); // true
boolean added = prices.add(new BigDecimal("8.00"));      // false
~~~

`found == true` only says that the set contains an element **equal in ordering** to `8.00`; it does not prove that an `8.00` object with that exact `scale` was stored. If you proceed to call `prices.remove(new BigDecimal("8.000"))`, that operation can remove the stored `"8.0"` element even though `equals()` between them is `false`.

For `TreeMap`, the same risk is especially important when a key represents **a business item that must be distinguished by formatting specification**: a second write can overwrite the first key's payload. The comparison rule must be explicitly chosen before creating the collection.

## 7. Sorting Lists, searching, and min/max

`Collections.sort(list)`, `List.sort(null)`, and `Arrays.sort(array)` use `BigDecimal`'s natural ordering when no comparator is provided. That means they sort **by numeric value**. Objects equal under `compareTo` are not forced to become the same object or dropped from a `List`. A `List` preserves all elements.

If you use `Collections.binarySearch(sortedList, target)` under natural ordering, the result can point to an element equal in **numeric value** but with a different `scale` than `target`. When multiple elements are equivalent under the comparator, the API makes no guarantee about which one is returned. To find an **exact representation**, use a criterion that checks `scale` or scan using `equals()`.

Similarly, `BigDecimal.min()` and `BigDecimal.max()` choose according to `compareTo()`. If the comparison returns 0, they return the receiver object (`this`), so `min`/`max` do not normalize `scale`:

~~~java
BigDecimal one = new BigDecimal("2.0");
BigDecimal two = new BigDecimal("2.00");

System.out.println(one.min(two)); // 2.0
System.out.println(two.min(one)); // 2.00
~~~

This is not a bug in min/max; the two objects are equal in numeric order, and which representation is chosen is part of the method contract.

## 8. Strategy A: identity based on numeric value

If business rules state that `2.0`, `2.00`, and `2.000` must be **the same value** for deduplication, aggregation, or lookup, you can **normalize before using as keys**. A common approach is `stripTrailingZeros()`:

~~~java
BigDecimal a = new BigDecimal("2.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("2.00").stripTrailingZeros();

System.out.println(a);            // 2
System.out.println(b);            // 2
System.out.println(a.equals(b));  // true
~~~

When both sides are normalized by the same rule, `HashSet`/`HashMap` can enforce numeric identity consistent with `TreeSet`/`TreeMap` for normalized values. Normalization must happen **at the data ingestion boundary or before every `put`, `get`, `contains`, and `remove`**. Normalizing on insertion without normalizing on lookup will continue to produce confusing behavior.

Example normalization helper:

~~~java
private static BigDecimal numericKey(BigDecimal value) {
    return value.stripTrailingZeros();
}
~~~

The snippet above must be placed inside a Java class. `stripTrailingZeros()` preserves **numeric value**, though it can change display form and `scale`. For example, `new BigDecimal("1000.00").stripTrailingZeros()` may display as `1E+3` with `scale = -3`; all zero values after normalization yield an equivalent of `BigDecimal.ZERO` (`scale = 0`).

**Important limitation:** Do not apply normalization if `scale` expresses contracted decimal places, measurement resolution, or currency digit rules that must be preserved. In such cases `2.0` and `2.00` may need to be distinguished.

## 9. Strategy B: identity combining numeric value and scale

When you must keep both representations in a sorted collection, use a comparator that sorts by **numeric value and then by `scale`**:

~~~java
Comparator<BigDecimal> valueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);

TreeSet<BigDecimal> values = new TreeSet<>(valueThenScale);
values.add(new BigDecimal("2.0"));
values.add(new BigDecimal("2.00"));

System.out.println(values.size()); // 2
~~~

This comparison is consistent with `BigDecimal.equals()`:

- If the numeric values differ, the comparator distinguishes them.
- If the numeric values are equal but `scale` differs, the `thenComparingInt` step distinguishes them.
- If both numeric value and `scale` are equal, the two `BigDecimal` objects are also equal under `equals()`, so the comparator returns 0.

**Do not** use `Comparator.comparing(BigDecimal::stripTrailingZeros)` if your goal is to keep each `scale` separate: that still merges numerically equal values. Also do not compare only by `scale`, because two different numeric values with the same `scale` would be treated as duplicates. The "value first, `scale` second" order is the essential condition of this strategy.

Note that this comparator matches the exact semantics of `BigDecimal.equals()`, not every business requirement. For example, if a system has transaction IDs, two `2.00` amounts coming from **two different transactions** must still both be kept; a set of `BigDecimal` values cannot carry full transaction identity. In that case, store an entity or a key that includes its own identifier.

## 10. Strategy C: domain-enforced fixed scale

If the entire system requires **two decimal places**, normalize to `scale = 2` upon input validation. Then `2`, `2.0`, and `2.00` can all become `BigDecimal("2.00")`, provided the conversion does not lose data.

~~~java
BigDecimal first = new BigDecimal("2.0").setScale(2);
BigDecimal second = new BigDecimal("2.00").setScale(2);
System.out.println(first.equals(second)); // true
~~~

`setScale(2)` is **not** multiplying by 100; it requests representing the value at two decimal places. If non-zero digits would be discarded, the overload without a rounding mode throws `ArithmeticException`:

~~~java
// Throws ArithmeticException because 2.005 cannot be represented exactly with scale 2:
new BigDecimal("2.005").setScale(2);
~~~

If business logic permits rounding, specify the rule explicitly, for example `setScale(2, RoundingMode.HALF_EVEN)`. Rounding can change the **numeric value**, so `scale` normalization cannot automatically be treated as a harmless operation.

Strategies can be combined: use normalized numbers for monetary calculations, while keeping the original input string or separate metadata when auditing the user-declared precision. Do not use a single `BigDecimal` object to satisfy two conflicting definitions of identity at the same time.

## 11. Why does scale sometimes truly matter?

`BigDecimal.equals()` distinguishes representations for reasons beyond "trailing zeros." Some operations produce results that depend on the operand's `scale`. JavaDoc gives an example of two versions of the number 2 when using the division overload with `RoundingMode`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal divisor = new BigDecimal("3");

System.out.println(
        new BigDecimal("2.0").divide(divisor, RoundingMode.HALF_UP)
); // 0.7

System.out.println(
        new BigDecimal("2.00").divide(divisor, RoundingMode.HALF_UP)
); // 0.67
~~~

The overload `divide(BigDecimal, RoundingMode)` uses the **dividend's `scale`** as the result `scale`, then rounds according to `RoundingMode`. Two numbers with the same value 2 but different `scale` retain different numbers of digits. The snippet above belongs inside a Java method; it illustrates a practical reason to understand `scale` before normalizing.

For division requiring precision via `MathContext`, or a specific result `scale` via `divide(divisor, requestedScale, roundingMode)`, choose the appropriate overload deliberately. Do not assume that `compareTo() == 0` lets you substitute any object for another without changing representation outcomes across the arithmetic API.

## 12. Common mistakes to avoid

1. **Using `equals()` to compare monetary amounts for magnitude or numeric equality:** with `BigDecimal`, `amount.compareTo(other) == 0` expresses numeric equality. To check less/greater, use `< 0` or `> 0` on the `compareTo()` result.
2. **Using `HashSet` and later switching to `TreeSet` without re-evaluating identity:** the same input data can yield different sizes and `contains()` results.
3. **Using `TreeMap` to store two keys that differ only in `scale`:** the second `put` will update the value instead of increasing the map size.
4. **Assuming `TreeSet.contains(x)` implies there is an element `equals(x)`:** the tree's `contains()` applies the ordering comparison rule; with default `BigDecimal`, the two rules can disagree.
5. **Comparing `BigDecimal` with `==`:** this operator compares references in Java, not numeric value or `scale` equality.
6. **Relying solely on `hashCode()`:** equal hashes do not guarantee `equals()` is true; if you want numeric identity in hash collections, normalize keys by convention.
7. **Thinking `stripTrailingZeros()` is purely a display change:** the result can have a negative `scale`, and `equals()` against the original object may differ.
8. **Using `new BigDecimal(0.1)` to build examples or keys:** the `double` constructor introduces the exact binary value of the `double`, which is usually not equal to the written decimal. Use strings like `"0.1"` or consider `BigDecimal.valueOf(0.1)` when the original data is a standard decimal value.
9. **Checking comparator rules visually but forgetting lookups:** with custom `TreeMap`/`TreeSet`, the same comparator must apply throughout the collection's lifecycle; data shared across multiple collections needs an explicit equivalence policy.
10. **Assuming adding a comparator always preserves every record:** if two records have the same number and the same `scale` yet are two distinct entities, the comparator in section 9 still treats them as equivalent. Use an appropriate entity identity key.

## 13. Comprehension exercises

### Exercise 1: predict the counts

~~~java
BigDecimal x = new BigDecimal("0.0");
BigDecimal y = new BigDecimal("0.00");

HashSet<BigDecimal> h = new HashSet<>();
TreeSet<BigDecimal> t = new TreeSet<>();
h.add(x);
h.add(y);
t.add(x);
t.add(y);
~~~

**Answer:** `h.size() == 2`, `t.size() == 1`. `x.compareTo(y) == 0` while `x.equals(y) == false`. If you call `stripTrailingZeros()` on both `x` and `y` **before adding**, both become the canonical zero form and `HashSet` ends up with only one element.

### Exercise 2: which Map overwrites?

~~~java
BigDecimal first = new BigDecimal("10.0");
BigDecimal second = new BigDecimal("10.00");

TreeMap<BigDecimal, String> map = new TreeMap<>();
map.put(first, "A");
String old = map.put(second, "B");
~~~

**Answer:** `old` is `"A"`, `map.size() == 1`, `map.get(first)` is `"B"`, and `map.get(second)` is also `"B"`. If `HashMap` were used instead with the same keys, the size would be 2 because they differ under `equals()`.

### Exercise 3: consistent comparator?

Consider three ways to create a comparator:

~~~java
Comparator<BigDecimal> c1 = Comparator.naturalOrder();
Comparator<BigDecimal> c2 =
        Comparator.comparing(BigDecimal::stripTrailingZeros);
Comparator<BigDecimal> c3 =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);
~~~

**Answer:** `c1` and `c2` both treat `2.0` and `2.00` as equivalent; they are **inconsistent with `BigDecimal.equals()`**. `c3` sorts by numeric value and also distinguishes `scale`, so it is consistent with `equals()` on `BigDecimal` objects.

### Exercise 4: choose a design

A system receives prices `12.0` and `12.00` from two different files. Requirement (A) is to count the number of **unique numeric values**, while requirement (B) is to count the number of **numeric representations distinct by `scale`**.

**Suggested answer:** For (A), normalize with `stripTrailingZeros()` and use `HashSet`, or use a natural-order `TreeSet` if only the set of numeric values is needed. For (B), use `HashSet` with default `equals()`, or `TreeSet` with a value-then-`scale` comparator. If you also need to distinguish **each input row**, you must use a row ID rather than relying only on `BigDecimal`.

## 14. Key takeaways and official documentation

- `BigDecimal.compareTo()` is a **numeric comparison**; `equals()` checks **both value and `scale`**.
- "Natural ordering inconsistent with `equals`" means there exist pairs where `compareTo() == 0` yet `equals() == false`. This can cause sorted and hashed sets/maps to disagree on duplicate elements/keys.
- **Numeric value**, **representation with `scale`**, and **domain record identity** are three distinct concepts. Choose one specific rule and apply it consistently on both writes and reads.

References (Java SE 17/21):
- [`BigDecimal` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): sections on `compareTo`, `equals`, `hashCode`, `divide`, and `stripTrailingZeros`.
- [`Comparable` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html): definition of natural ordering consistent with `equals` and notes on `BigDecimal`.
- [`Comparator` — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Comparator.html): consistency between comparator and `equals` for sorted collections.
