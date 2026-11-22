# Practice: Comparing `HashSet` and `TreeSet` Containing `BigDecimal`

## 1. Problem to Solve

`HashSet` and `TreeSet` both implement the `Set` interface in Java, yet with `BigDecimal`, they **do not necessarily keep the same number of elements** when given the same input list:

- `HashSet<BigDecimal>` determines duplicates using `equals()` and `hashCode()`.
- `TreeSet<BigDecimal>` uses the natural ordering `compareTo()` or a provided `Comparator`. Two elements are considered the same element if the comparison returns **0**.

The special quirk of `BigDecimal`: `equals()` checks **both value and scale**, whereas `compareTo()` compares only **mathematical value**.

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

Both numbers have value 1, but their scales are 1 and 2 respectively. Therefore `HashSet` treats them as two distinct elements, while `TreeSet` by default treats them as one equivalence class. This difference affects `add`, `size`, `contains`, `remove`, and output data.

**Goal:** run a Java 17+ program yourself, predict the output before running, explain each line, and then choose a deduplication rule matching the data contract rather than choosing a collection out of habit.

## 2. Reviewing `BigDecimal` and scale

Representation formula of `BigDecimal`:

~~~text
value = unscaledValue × 10^(-scale)
~~~

| Input data | Unscaled value | Scale | Mathematical value |
| --- | ---: | ---: | ---: |
| `"1"` | 1 | 0 | 1 |
| `"1.0"` | 10 | 1 | 1 |
| `"1.00"` | 100 | 2 | 1 |
| `"1.000"` | 1000 | 3 | 1 |
| `"1E+0"` | 1 | 0 | 1 |
| `"1000.00"` | 100000 | 2 | 1000 |

All representations with value 1 are equal under `compareTo`, yet only objects with the same value and scale are equal under `equals`. `BigDecimal.hashCode()` also takes scale into account to stay consistent with `equals`.

Therefore, when preserving the number of decimal places is part of the contract, **do not assume "same value" means "same data."** Conversely, if you only need a set of distinct numeric values, do not accidentally keep multiple representations merely because their scales differ.

Construct practice data using `new BigDecimal("1.00")` rather than going through `double`. The string constructor preserves the intended decimal value and scale; the `double` constructor can introduce binary error for many decimal numbers like 0.1.

## 3. `HashSet<BigDecimal>`: Scale-Sensitive Equality Rule

Experiment:

~~~java
HashSet<BigDecimal> hash = new HashSet<>();
System.out.println(hash.add(new BigDecimal("1.0")));   // true
System.out.println(hash.add(new BigDecimal("1.00")));  // true
System.out.println(hash.add(new BigDecimal("1.000"))); // true
System.out.println(hash.size());                       // 3
~~~

This is an illustrative snippet placed inside a method, requiring `import java.math.BigDecimal` and `import java.util.HashSet`.

All three `add` calls return `true`, because the three objects are not equal under `BigDecimal.equals`. The set size is 3 even though there is only a single mathematical value of 1.

Consequence for lookups:

~~~java
hash.contains(new BigDecimal("1.00"));   // true
hash.contains(new BigDecimal("1.0000")); // false
~~~

`1.0000` has scale 4 and has not been stored in the set. Returning `false` does not mean the set lacks a number mathematically equal to 1; it only means there is no equivalent object under `equals`.

**Do not rely on iteration order or `toString()` of `HashSet`.** `HashSet` makes no guarantee of preserving insertion or sorted order. When testing results, use `size`, `contains`, comparisons, or element-wise checks without relying on arbitrary order.

## 4. `TreeSet<BigDecimal>`: Comparator-Based Equality Rule

`TreeSet` is a `NavigableSet` that maintains ordering. When no `Comparator` is passed, `BigDecimal` uses `compareTo` as its natural ordering:

~~~java
TreeSet<BigDecimal> tree = new TreeSet<>();
System.out.println(tree.add(new BigDecimal("1.0")));   // true
System.out.println(tree.add(new BigDecimal("1.00")));  // false
System.out.println(tree.add(new BigDecimal("1.000"))); // false
System.out.println(tree.size());                       // 1
System.out.println(tree);                              // [1.0]
~~~

Among the three numbers, `compareTo` returns 0. Only the first added element (`1.0`) becomes the **stored representative**. Subsequent additions of numbers with the same value but different scales do not replace the old representative. `TreeSet` does not automatically call `setScale` or `stripTrailingZeros`.

### 4.1. `contains` and `remove` can be surprising

~~~java
TreeSet<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("1.0"));

System.out.println(tree.contains(new BigDecimal("1.0000"))); // true
System.out.println(tree.remove(new BigDecimal("1.0000")));   // true
System.out.println(tree.isEmpty());                          // true
~~~

`contains` returns `true` because there is an element comparing as 0, **not because the set stored a scale-4 object**. Similarly, `remove` deletes the `1.0` representative by finding an equivalent key according to the comparator.

If a `HashSet` only contains `1.0`, `remove(new BigDecimal("1.0000"))` returns `false`. Thus the two `Set` types must not be treated as semantically interchangeable in this problem.

### 4.2. The retained representative depends on insertion order

~~~java
TreeSet<BigDecimal> first = new TreeSet<>();
first.add(new BigDecimal("6.0"));
first.add(new BigDecimal("6.00"));

TreeSet<BigDecimal> second = new TreeSet<>();
second.add(new BigDecimal("6.00"));
second.add(new BigDecimal("6.0"));

System.out.println(first);  // [6.0]
System.out.println(second); // [6.00]
~~~

Both sets have only **one distinct mathematical value**, yet the scale of the stored representative differs. If an API requires exact-scale representations, do not use a default `TreeSet` as a "normalization" step because insertion order can determine the resulting string.

## 5. Main Practice: Predicting Results for the Same Data

Given input:

~~~java
List<BigDecimal> data = List.of(
        new BigDecimal("2.0"),
        new BigDecimal("1.0"),
        new BigDecimal("1.00"),
        new BigDecimal("2.00"),
        new BigDecimal("1.000"));
~~~

In terms of **numeric value**, the data has only two values: 1 and 2. In terms of **(value, scale) pairs**, there are five distinct elements.

| Check | `HashSet` | Default `TreeSet` |
| --- | --- | --- |
| `size()` after adding five elements | 5 | 2 |
| Merges `1.0` and `1.00` into one? | No | Yes |
| `contains(1.0000)` | `false` | `true` |
| Element identity | `equals/hashCode` | `compareTo == 0` |
| Maintains ascending numeric order | Not guaranteed | Yes |
| Automatically normalizes scale | No | No |

With this exact data order, `TreeSet.toString()` gives `[1.0, 2.0]`. That happens because the two representatives `1.0` and `2.0` were encountered before their other representations; not because `TreeSet` deliberately picks the shortest representation.

## 6. Standalone Java 17+ Program

Create the file **BigDecimalSetsLab.java**:

~~~java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class BigDecimalSetsLab {
    private static final Comparator<BigDecimal> VALUE_THEN_SCALE =
            (a, b) -> {
                int byValue = a.compareTo(b);
                return byValue != 0
                        ? byValue
                        : Integer.compare(a.scale(), b.scale());
            };

    public static void main(String[] args) {
        List<BigDecimal> data = List.of(
                new BigDecimal("2.0"),
                new BigDecimal("1.0"),
                new BigDecimal("1.00"),
                new BigDecimal("2.00"),
                new BigDecimal("1.000"));

        HashSet<BigDecimal> hash = new HashSet<>(data);
        TreeSet<BigDecimal> tree = new TreeSet<>(data);

        BigDecimal one = new BigDecimal("1.0");
        BigDecimal oneHundredths = new BigDecimal("1.00");
        BigDecimal lookup = new BigDecimal("1.0000");

        System.out.println("equals 1.0 / 1.00: "
                + one.equals(oneHundredths));
        System.out.println("compareTo 1.0 / 1.00: "
                + one.compareTo(oneHundredths));

        System.out.println("hash size: " + hash.size());
        System.out.println("tree size: " + tree.size());
        System.out.println("tree values: " + tree);

        System.out.println("hash contains 1.0000: "
                + hash.contains(lookup));
        System.out.println("tree contains 1.0000: "
                + tree.contains(lookup));

        TreeSet<BigDecimal> scaleAware =
                new TreeSet<>(VALUE_THEN_SCALE);
        scaleAware.addAll(data);
        System.out.println("scale-aware tree size: "
                + scaleAware.size());
        System.out.println("scale-aware tree values: "
                + scaleAware);

        HashSet<BigDecimal> normalized = data.stream()
                .map(BigDecimal::stripTrailingZeros)
                .collect(Collectors.toCollection(HashSet::new));
        System.out.println("normalized hash size: "
                + normalized.size());

        System.out.println("1000.00 stripped: "
                + new BigDecimal("1000.00")
                        .stripTrailingZeros());

        System.out.println("tree remove 1.0000: "
                + tree.remove(lookup));
        System.out.println("tree after remove: " + tree);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac BigDecimalSetsLab.java
java BigDecimalSetsLab
~~~

Output:

~~~text
equals 1.0 / 1.00: false
compareTo 1.0 / 1.00: 0
hash size: 5
tree size: 2
tree values: [1.0, 2.0]
hash contains 1.0000: false
tree contains 1.0000: true
scale-aware tree size: 5
scale-aware tree values: [1.0, 1.00, 1.000, 2.0, 2.00]
normalized hash size: 2
1000.00 stripped: 1E+3
tree remove 1.0000: true
tree after remove: [2.0]
~~~

The lines above do not print `HashSet` directly, because a hash set's element order is not guaranteed. Default `TreeSet` sorts by mathematical value, whereas `scaleAware` uses a custom comparator to distinguish representations with the same value but different scales.

## 7. Clarifying `add`, `contains`, `remove`, and Equivalent Sets

In `HashSet`, adding `BigDecimal("7.00")` after `BigDecimal("7.0")` increases the element count because `equals` is `false`. In default `TreeSet`, the same addition does not increase the element count because `compareTo == 0`.

~~~java
HashSet<BigDecimal> hash = new HashSet<>();
hash.add(new BigDecimal("7.0"));
System.out.println(hash.add(new BigDecimal("7.00"))); // true

TreeSet<BigDecimal> tree = new TreeSet<>();
tree.add(new BigDecimal("7.0"));
System.out.println(tree.add(new BigDecimal("7.00"))); // false
~~~

`Set.add` returns `true` when the set changes, `false` if the element is considered already present. With the `TreeSet` above, `false` **does not replace representative `7.0` with `7.00`**.

`TreeSet` maintains ascending order per the comparator and supports `first()`, `last()`, `ceiling()`, `floor()`, `subSet()`. `HashSet` focuses on hash-based lookup without ordering guarantees. Yet the primary issue with `BigDecimal` is not merely performance/sorting, but **the definition of "duplicate."**

## 8. When You Need Sorting While Still Distinguishing Scale

Natural `TreeSet<BigDecimal>` treats `1.0` and `1.00` as one. When the contract requires **two objects that differ under `BigDecimal.equals` to remain two separate elements**, use a comparator that distinguishes scale when values are equal:

~~~java
Comparator<BigDecimal> valueThenScale = (a, b) -> {
    int byValue = a.compareTo(b);
    return byValue != 0 ? byValue
            : Integer.compare(a.scale(), b.scale());
};

TreeSet<BigDecimal> scaleAware = new TreeSet<>(valueThenScale);
scaleAware.add(new BigDecimal("1.0"));
scaleAware.add(new BigDecimal("1.00"));
System.out.println(scaleAware.size()); // 2
~~~

The comparator sorts by **mathematical value** first; if values are equal, scale breaks the tie. For valid `BigDecimal` objects, the comparator returns 0 precisely when `equals` returns `true`, so the set's equality relation is consistent with `equals`.

Do not use `a.toString().compareTo(b.toString())` as a numeric comparator just because it is short to write: lexicographical string comparison can differ from mathematical order (especially for negative numbers, integer-part lengths, and exponential notation).

If sorting is not needed but **insertion order** must be preserved, `LinkedHashSet` may be suitable. It still uses `equals`/`hashCode` to detect duplicates, just like `HashSet`. Ordering and equality are two separate decisions.

## 9. When You Want to Deduplicate by Numeric Value

If you only need distinct mathematical values, default `TreeSet` may fit. However, if you use `HashSet` for hash lookup and want to merge `BigDecimal` values with different scales, you can **explicitly normalize the keys**:

~~~java
HashSet<BigDecimal> canonical = new HashSet<>();

canonical.add(new BigDecimal("1.0").stripTrailingZeros());
canonical.add(new BigDecimal("1.00").stripTrailingZeros());

System.out.println(canonical.size()); // 1
~~~

`stripTrailingZeros()` preserves the **mathematical value** while potentially changing the scale. For example:

~~~java
BigDecimal raw = new BigDecimal("1000.00");
BigDecimal compact = raw.stripTrailingZeros();

System.out.println(compact);         // 1E+3
System.out.println(compact.scale()); // -3
~~~

Key point to remember: normalizing this way can produce a negative scale; **unsuitable when output must preserve a fixed scale**.

If the contract requires every key to have exact scale 2 without rounding, you can normalize via:

~~~java
BigDecimal key = raw.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
~~~

This is an **illustrative snippet with a `BigDecimal` variable `raw`**. `1.0` and `1.00` both become `1.00` and yield the same hash key. `1.234` cannot be converted exactly to scale 2, so it throws `ArithmeticException`. If business logic allows rounding, choose the rounding mode deliberately: rounding can cause **two originally distinct values** to merge into one key.

## 10. The `Set` Contract and Impact on APIs

`BigDecimal` is a famous case where natural ordering is **inconsistent with `equals`**. This is explicitly noted in Java documentation.

An API declaring only `Set<BigDecimal>` while assuming `contains` always follows `BigDecimal.equals` can behave differently depending on whether callers pass `HashSet` or `TreeSet`. With `TreeSet`, the set uses its comparator to determine element equivalence; relative to the general `equals`-based `Set` contract, the result can be surprising.

For example, if a set contains `1.0`:

~~~java
boolean present = set.contains(new BigDecimal("1.00"));
~~~

If `set` is a `HashSet`, the result is `false`. If it is a natural `TreeSet`, the result is `true`. Therefore, document the equivalence relation clearly in the API, especially when data is used for deduplication, duplicate detection, lookup, or testing.

Similarly, `HashMap<BigDecimal, V>` uses `equals`/`hashCode` for keys, whereas `TreeMap<BigDecimal, V>` uses the comparator. Switching map implementations can change key counts or `get`/`put` behavior. Do not switch between hash maps and tree maps without reviewing `BigDecimal` semantics.

## 11. Self-Study Exercises and Answers

### Exercise 1 — Predict the number of elements

~~~java
List<BigDecimal> input = List.of(
        new BigDecimal("3"),
        new BigDecimal("3.0"),
        new BigDecimal("3.00"),
        new BigDecimal("4.0"),
        new BigDecimal("4.00"));

System.out.println(new HashSet<>(input).size());
System.out.println(new TreeSet<>(input).size());
~~~

**Answer:** `5` then `2`. The hash set distinguishes both value and scale; the natural tree set only distinguishes the two values 3 and 4.

### Exercise 2 — Lookup by value or by scale

~~~java
Set<BigDecimal> hash = new HashSet<>();
Set<BigDecimal> tree = new TreeSet<>();
hash.add(new BigDecimal("0.50"));
tree.add(new BigDecimal("0.50"));

System.out.println(hash.contains(new BigDecimal("0.5")));
System.out.println(tree.contains(new BigDecimal("0.5")));
~~~

**Answer:** `false` then `true`, because scale 2 differs from scale 1 while `compareTo == 0`.

### Exercise 3 — How does insertion order affect the representative?

~~~java
TreeSet<BigDecimal> one = new TreeSet<>();
one.add(new BigDecimal("6.0"));
one.add(new BigDecimal("6.00"));

TreeSet<BigDecimal> two = new TreeSet<>();
two.add(new BigDecimal("6.00"));
two.add(new BigDecimal("6.0"));

System.out.println(one); // [6.0]
System.out.println(two); // [6.00]
~~~

**Explanation:** each set keeps the representative inserted first. Both sets hold the same numeric value yet differ in the element's representation.

### Exercise 4 — Keeping all three scales while staying sorted

Requirement: given `6.0`, `6.00`, `6.000`, a sorted set must retain all **3** elements. Use the `valueThenScale` comparator from Section 8. Using `compareTo` alone leaves only one element.

### Exercise 5 — Choosing a structure for unit price data

A system treats `15.0` and `15.00` as **the same unit price**, yet must output results at **scale 2**. Do not simply use a default `TreeSet` and print the retained element: the representative could be `15.0`. Normalize inputs with `setScale(2, UNNECESSARY)` when appropriate, then choose a set based on ordering/lookup needs. If an input has more than two non-zero fractional digits, handle the error or apply the defined rounding policy.

## 12. Testing in Java

With JUnit 5, the following illustrative assertions should be placed in a test method with `import static org.junit.jupiter.api.Assertions.*;` (or `org.junit.jupiter.api.Assertions.*`):

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

assertNotEquals(a, b);
assertEquals(0, a.compareTo(b));
assertEquals(2, new HashSet<>(List.of(a, b)).size());
assertEquals(1, new TreeSet<>(List.of(a, b)).size());
~~~

Note that `assertEquals(a, b)` uses `equals` and will fail. If the contract only checks numeric value, assert `compareTo == 0` instead of an `equals` assertion that does not match the requirement.

Additional cases worth testing:

| Input | What to verify |
| --- | --- |
| `1.0`, `1.00`, `1.000` | Duplicate by value vs. value+scale |
| `0`, `0.00` | Zero still carries a scale in `BigDecimal` |
| `-2.0`, `-2.00` | Rule does not depend on sign |
| `1000.00`, `1E+3` | `stripTrailingZeros` can produce negative scale |
| `1.01`, `1.010`, `1.02` | Truly distinct values are not merged |
| `1.234` normalized to scale 2 | `UNNECESSARY` errors if rounding would be needed |
| Inserting elements in reverse order | `TreeSet` may retain a different representative |
| Iterating `HashSet` multiple times | Do not assert unguaranteed order |

If `TreeSet` contains the right count of results but must output scale-2 representations, add an assertion checking `scale() == 2` for each element. **Right count does not prove right data representation.**

## 13. Common Mistakes

| Misconception | Reality |
| --- | --- |
| Two numerically equal `BigDecimal`s mean a hash set keeps only one | `HashSet` relies on `equals`, which also checks scale |
| `TreeSet` uses `equals` to detect duplicates | `TreeSet` uses its comparator and treats `compare(...) == 0` as equivalent |
| `TreeSet` merely adds sorting to `HashSet` | For `BigDecimal`, it also changes the identity rule |
| `TreeSet.contains(1.000)` proves the exact scale-3 object is stored | It only proves an equivalent-value representative exists under the comparator |
| Adding `1.00` after `1.0` into a tree set replaces the representative | `add` returns `false` and keeps the old representative |
| `HashSet` prints elements in insertion order | There is no guarantee on iteration order |
| `stripTrailingZeros` always resets scale to 0 | It can create negative scales, such as `1E+3` |
| A `toString` string comparator equals numeric comparison | Lexicographical and numerical orders can differ |
| Converting to `double` before deduplicating is more accurate | Binary conversion can round and conflate distinct values |
| Choosing `HashSet` vs. `TreeSet` is purely a performance decision | It can change both results and the data contract |

**Conclusion:** Clearly define whether "duplicate" means **same numeric value** or **same value and scale**. Default `HashSet<BigDecimal>` matches the `equals` relation; default `TreeSet<BigDecimal>` matches `compareTo == 0`. If you need a different relation, normalize inputs or provide an explicit comparator, then test `size`, `contains`, `remove`, ordering, and output scale.
