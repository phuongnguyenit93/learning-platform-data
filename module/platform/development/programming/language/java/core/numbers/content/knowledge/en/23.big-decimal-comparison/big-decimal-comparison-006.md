# Consequences when using BigDecimal in TreeSet or TreeMap

## 1. The problem: same numeric value but different representations

In Java, `BigDecimal` has two ways of checking equality:

- `compareTo(BigDecimal)` compares **numeric value**. If two numbers are equal in value, `compareTo()` returns `0`, even if their `scale` differs.
- `equals(Object)` requires **the same numeric value and the same scale**. Therefore, `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` is `false`.

Short example:

```java
BigDecimal a = new BigDecimal("2.0");  // unscaled=20, scale=1
BigDecimal b = new BigDecimal("2.00"); // unscaled=200, scale=2

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

In Java documentation, two objects like `a` and `b` belong to the same *cohort*: equal in numeric value, but with different decimal representations. The *natural ordering* of `BigDecimal` is defined via `compareTo()` and is **inconsistent with `equals()`**.

This difference has direct consequences when using `BigDecimal` as **elements of a `TreeSet`** or **keys of a `TreeMap`**. Both structures rely on **comparison ordering**, rather than `equals()`, to decide whether two elements/keys are treated as the same.

## 2. TreeSet: an element can be treated as a duplicate even when equals is false

`TreeSet` orders elements by natural ordering, or by a `Comparator` passed at construction. When no comparator is provided, for `BigDecimal` it uses `compareTo()`.

Operations such as `add()`, `contains()`, and `remove()` rely on the comparison result. When `compareTo() == 0`, `TreeSet` treats the two objects as equivalent when deciding if an element already exists, regardless of whether `equals()` returns `false`.

```java
TreeSet<BigDecimal> values = new TreeSet<>();
boolean first = values.add(new BigDecimal("2.0"));  // true
boolean second = values.add(new BigDecimal("2.00")); // false

System.out.println(values.size());                   // 1
System.out.println(values.contains(new BigDecimal("2.000"))); // true
```

What happens?

1. Element `2.0` is added because the set is initially empty.
2. `2.00` compares equal to `2.0` via `compareTo() == 0`, so the second `add` returns `false` and does not increase the size.
3. Calling `contains(new BigDecimal("2.000"))` returns `true`, even though `"2.000"` is not `equals()` to the stored element `"2.0"`.
4. With `remove(new BigDecimal("2.000"))`, `TreeSet` can remove element `"2.0"` because they are equal according to the set's comparison rule.

**Practical consequence:** if a developer expects `TreeSet<BigDecimal>` to store both `2.0` and `2.00` as two separate representations, the missing element is behavior *defined by the comparator*, not a random Java bug.

Under the general `Set` contract, uniqueness is defined in terms of `equals()`. Because `TreeSet` with `BigDecimal`'s natural ordering determines duplicates using `compareTo()`, this ordering is **inconsistent with the `Set` contract**; Java documentation explicitly warns about this case. `TreeSet` operations still behave according to the chosen ordering rule.

## 3. TreeMap: two keys that fail equals can point to the same entry

With `TreeMap<BigDecimal, V>` using natural ordering, if two keys compare equal (`compareTo() == 0`), `TreeMap` treats them as **one logical key**.

```java
TreeMap<BigDecimal, String> prices = new TreeMap<>();

prices.put(new BigDecimal("2.0"), "first");
prices.put(new BigDecimal("2.00"), "second");

System.out.println(prices.size());                      // 1
System.out.println(prices.get(new BigDecimal("2.000"))); // second
```

On the first `put`, the map creates an entry. On the second `put`, it finds an equivalent key according to the comparator, so **the existing entry's value is replaced with `"second"`**; no new entry is created. The stored key in this example remains the `2.0` object inserted first. You can observe this via `firstKey()` or iterating `keySet()`; replacing the value does not replace the stored key object.

Lookup operations such as `get()`, `containsKey()`, and `remove()` also rely on comparison ordering. A new key with value `2.000` can access or remove the entry created with `2.0`.

This is especially important if a `BigDecimal` key represents a value whose **scale carries business meaning** (such as measurement precision or decimal formatting that must be distinguished). In that scenario, two keys can be unexpectedly merged, causing data overwrites.

## 4. Runnable Java 17 program: comparing TreeSet, TreeMap, HashSet, and HashMap

Create the file **`BigDecimalSortedCollectionsDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalSortedCollectionsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal probe = new BigDecimal("2.000");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareToZero=" + (a.compareTo(b) == 0));
        System.out.println("scales=" + a.scale() + "," + b.scale());

        Set<BigDecimal> treeSet = new TreeSet<>();
        System.out.println("treeAddA=" + treeSet.add(a));
        System.out.println("treeAddB=" + treeSet.add(b));
        System.out.println("treeSize=" + treeSet.size());
        System.out.println("treeContainsProbe=" + treeSet.contains(probe));
        System.out.println("treeStored=" + treeSet.iterator().next());

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        System.out.println("mapPutA=" + treeMap.put(a, "first"));
        System.out.println("mapPutB=" + treeMap.put(b, "second"));
        System.out.println("mapSize=" + treeMap.size());
        System.out.println("mapGetProbe=" + treeMap.get(probe));
        System.out.println("mapStoredKey=" + treeMap.keySet().iterator().next());

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");
        System.out.println("hashSetSize=" + hashSet.size());
        System.out.println("hashMapSize=" + hashMap.size());
        System.out.println("hashMapGetProbe=" + hashMap.get(probe));

        Comparator<BigDecimal> byValueThenScale = (left, right) -> {
            int result = left.compareTo(right);
            return result != 0 ? result
                    : Integer.compare(left.scale(), right.scale());
        };
        Set<BigDecimal> strictTreeSet = new TreeSet<>(byValueThenScale);
        strictTreeSet.add(a);
        strictTreeSet.add(b);
        System.out.println("strictTreeSize=" + strictTreeSet.size());
        System.out.println("strictContainsProbe=" + strictTreeSet.contains(probe));

        Set<BigDecimal> normalizedSet = new TreeSet<>();
        normalizedSet.add(a.stripTrailingZeros());
        normalizedSet.add(b.stripTrailingZeros());
        System.out.println("normalizedSize=" + normalizedSet.size());
        System.out.println("normalizedValue=" + normalizedSet.iterator().next());
    }
}
```

Compile and run:

```bash
javac BigDecimalSortedCollectionsDemo.java
java BigDecimalSortedCollectionsDemo
```

Output (actually run after compiling with `javac --release 17`):

```text
equals=false
compareToZero=true
scales=1,2
treeAddA=true
treeAddB=false
treeSize=1
treeContainsProbe=true
treeStored=2.0
mapPutA=null
mapPutB=first
mapSize=1
mapGetProbe=second
mapStoredKey=2.0
hashSetSize=2
hashMapSize=2
hashMapGetProbe=null
strictTreeSize=2
strictContainsProbe=false
normalizedSize=1
normalizedValue=2
```

Key points to read in the output:

- `treeAddB=false`: `TreeSet` ignores the second element because the numeric comparison is equal.
- `treeContainsProbe=true`: the queried element `2.000` is reported as present in the set even though its scale differs from the stored element `2.0`.
- `mapPutB=first`: `Map.put` returns the previous value, proving the second insertion updated an existing entry; `mapGetProbe=second` shows the new value.
- `mapStoredKey=2.0`: the existing entry still holds the key from the first insertion in this scenario.
- `hashSetSize=2` and `hashMapSize=2`: hash structures treat `a` and `b` as distinct because they rely on `equals()` and `hashCode()`.
- `strictTreeSize=2`: a comparator designed to distinguish scale retains both objects.
- `normalizedSize=1`: actively normalizing data collapses two representations with the same value into one stored form.

## 5. Comparing what "duplicate" means across collections

| Structure | Rule for treating elements/keys as duplicates | `2.0` vs `2.00` by default |
| --- | --- | --- |
| `HashSet<BigDecimal>` | `equals()` and `hashCode()` | Two separate elements (size 2) |
| `HashMap<BigDecimal, V>` | `equals()` and `hashCode()` | Two separate keys (size 2) |
| `TreeSet<BigDecimal>` | `compareTo() == 0` under natural ordering | One element (size 1) |
| `TreeMap<BigDecimal, V>` | `compareTo() == 0` under natural ordering | One key (size 1), later value overwrites |
| `TreeSet/TreeMap` with custom `Comparator` | `comparator.compare(a, b) == 0` | Depends on comparator |

For `HashSet`/`HashMap`, `BigDecimal`'s `hashCode()` reflects the unscaled value and scale. Thus `2.0` and `2.00` can have different hash codes; the decisive factor remains that `equals()` returns `false`. Do not deduce from two numbers having the same numeric value that they will act as the same key in a `HashMap`.

For `TreeSet`/`TreeMap`, **the key/element's `equals()` method is not the primary criterion** used to determine equivalence. Sorted structures use the comparison result as the identity criterion during lookup operations.

## 6. How to choose the right design for your data requirements

### Case A — Two representations of the same number must be treated as one value

For example, the business logic only cares about `2`, `2.0`, and `2.00` as **the same numeric value**.

Using `TreeSet`/`TreeMap` with natural ordering **can be intentionally appropriate** if you accept that keys/elements are identified by `compareTo() == 0` and understand the limitation regarding consistency with `equals()`. Document this rule clearly in the API to avoid confusion with `HashSet`/`HashMap`.

Another option is to **normalize keys before storing and before querying**, especially when you want hash structures and sorted structures to agree on uniqueness:

```java
static BigDecimal numericKey(BigDecimal value) {
    return value.stripTrailingZeros();
}

// Example inside a method:
Set<BigDecimal> keys = new HashSet<>();
keys.add(numericKey(new BigDecimal("2.0")));
keys.add(numericKey(new BigDecimal("2.00")));
// keys.size() == 1

boolean found = keys.contains(numericKey(new BigDecimal("2.000")));
// found == true
```

The `numericKey` method is an **illustrative snippet** and must be placed inside a Java class. The normalization rule must be applied **consistently on both writes and reads**. `stripTrailingZeros()` can return scientific notation with a negative scale (for instance `600.0` becomes `6E+2`), and zero is normalized to `BigDecimal.ZERO`. If scale carries meaning, this normalization does not satisfy the requirement.

### Case B — Two representations with different scales must be two distinct elements/keys

For example, requirements demand distinguishing `2.0` (scale 1) and `2.00` (scale 2). When sorting is not needed, `HashSet`/`HashMap` already follow `BigDecimal.equals()`.

If sorting is still required, provide a comparator: **compare value first, then compare scale when numeric values are equal**.

```java
Comparator<BigDecimal> byValueThenScale = (left, right) -> {
    int result = left.compareTo(right);
    return result != 0 ? result
            : Integer.compare(left.scale(), right.scale());
};

TreeSet<BigDecimal> distinctScales = new TreeSet<>(byValueThenScale);
distinctScales.add(new BigDecimal("2.0"));
distinctScales.add(new BigDecimal("2.00"));
// distinctScales.size() == 2

TreeMap<BigDecimal, String> details = new TreeMap<>(byValueThenScale);
details.put(new BigDecimal("2.0"), "scale 1");
details.put(new BigDecimal("2.00"), "scale 2");
// details.size() == 2
```

Why is this comparator consistent with `BigDecimal.equals()`? If two values have the same numeric value **and the same scale**, their unscaled parts are also identical, so `equals()` returns `true`. Therefore, the comparator returns 0 precisely when `equals()` returns `true`. The comparator also satisfies antisymmetry, transitivity, and consistent ordering.

However, this comparator allows two numbers with the same value but different scales to coexist. If the application needs uniqueness **by numeric value**, choose the rule in Case A; do not apply this comparator merely to "silence" a warning.

### Case C — Multiple attributes form business identity

If a record carries an amount, currency code, precision level, timestamp, and identifier, choosing `BigDecimal` as the sole key can lose semantics. Create an explicit domain key, for example a record containing the currency code and the monetary value converted to minor units according to a predefined rule:

```java
record MoneyKey(String currencyCode, long minorUnits) {}
```

This is an example of a **key type**; converting `BigDecimal` to `minorUnits` must separately check scale, rounding, `long` range, and currency unit rules. When larger values are needed, `BigInteger` can be used instead of `long`. Do not convert via `double` and cast because precision may be lost.

## 7. Consequences often overlooked during implementation

**Data merging and lost records:** a statistics program inserting `2.0` and `2.00` into a `TreeMap<BigDecimal, Result>` may end up with only one entry. If each input string is a separate measurement that must be stored, the key needs another identifier or a different comparator.

**Reading via a key that was never stored:** querying `treeMap.get(new BigDecimal("2.000"))` can return data stored under key `2.0`. This is convenient for numeric lookups, yet dangerous when users assume scale is part of the identifier.

**Unintended overwrites:** calls to `put`, `putIfAbsent`, `computeIfAbsent`, and `merge` may treat `BigDecimal` keys with different scales as the same key. Depending on the method, the outcome is keeping the previous value, updating, or merging data. Check business logic instead of assuming every new object is a new key.

**Different results between two collection types:** data placed in a `HashSet` may have 2 elements, while switching to a default `TreeSet` leaves only 1. Changing the collection type can alter the duplication policy, not just sorting capability.

**Impact on `contains` and `remove`:** with `TreeSet`, a lookup object with a different scale can still match or remove a stored object. This matters for code performing permission checks, existence checks, or deletions based on keys reconstructed from input strings.

**Formatting preservation issues:** when `TreeMap.put` updates the value for a key with `compareTo() == 0`, the original entry may still expose the scale of the earlier inserted key. Do not rely on `keySet().iterator().next().toString()` to infer how the user entered the latest data. If you need to keep the original input text, store it in a separate data field.

## 8. Common mistakes and how to avoid them

1. **Assuming `compareTo() == 0` implies `equals() == true`.** For `BigDecimal` this is false when scales differ. Decide whether you need numeric comparison or full representation comparison.
2. **Believing `TreeSet` calls `equals()` when adding elements.** It relies on ordering, so two objects with `equals=false` can still be treated as duplicates.
3. **Using `TreeMap` as a table of distinct records with only the decimal value as key.** Keys with the same numeric value will merge entries. Add an identifier or an appropriate comparator.
4. **Switching `HashMap` to `TreeMap` for sorting without checking the duplicate policy.** The size can change. Test with a dataset containing `2.0`, `2.00`, and `2.000`.
5. **Using a `toString()`-based comparator when wanting numeric BigDecimal comparison.** Lexicographical string order does not match numeric order and also depends on representation form (for example `"10"` vs `"2"`). Use `compareTo()` and, when needed, add scale as a secondary criterion.
6. **Normalizing with `stripTrailingZeros()` without considering consequences.** Zero and negative scales are important cases; normalization can erase the original decimal digit count. Define separate storage for the original format if needed.
7. **Creating `BigDecimal` from `double` and being confused by the result.** `new BigDecimal(0.1)` reflects the binary approximation of `0.1` in `double`. For decimal inputs, prefer constructing from a string `new BigDecimal("0.1")`, or consider `BigDecimal.valueOf(0.1)`.
8. **Ignoring comparator consistency constraints.** A comparator for `TreeSet`/`TreeMap` must ensure a valid ordering (such as antisymmetry and transitivity); to fully satisfy the `Set`/`Map` contract, `compare(a,b) == 0` must also be equivalent to `a.equals(b)`.

## 9. Decision checklist

Before putting `BigDecimal` into a `TreeSet` or using it as a `TreeMap` key, answer these questions:

1. Does "duplicate" mean **same numeric value** or **same value and scale**?
2. Does the application need to preserve trailing zeros, raw input text, or measurement units?
3. Is sorting actually needed? If not, `HashSet`/`HashMap` may fit better when using `equals()` semantics.
4. Is a comparator consistent with `equals()` needed, such as numeric comparison followed by scale comparison?
5. If normalizing, do all write, search, update, and delete paths apply the exact same rule?
6. Have edge cases like `0.0`/`0.00`, `2.0`/`2.00`, negative scale, and negative values been tested?

## 10. Self-check

**Question 1.** A `TreeSet<BigDecimal>` receives `"1.0"`, `"1.00"`, and `"2.0"` in order. What is its size?  
**Answer:** 2, because the two representations of 1 compare equal via `compareTo()`.

**Question 2.** A `TreeMap<BigDecimal, String>` stores `"1.0" -> "A"` and then `"1.00" -> "B"`. What does querying key `"1.000"` return?  
**Answer:** `"B"`. All of those keys are equal under natural ordering, and the second `put` replaces the first entry's value.

**Question 3.** With the same two values `"1.0"` and `"1.00"`, how many elements does a `HashSet` have?  
**Answer:** 2, because `equals()` distinguishes scale.

**Question 4.** If an application needs both scales in a single `TreeSet`, what should it do?  
**Answer:** pass a comparator that compares by numeric value and then by scale to avoid `compare()==0` when `equals()==false`.

**Question 5.** Does `stripTrailingZeros()` always preserve the input formatting?  
**Answer:** no; `600.0` can become `6E+2` and lose its original scale/display string.

## 11. Key takeaways

- `BigDecimal.compareTo()` compares **numerically**; `BigDecimal.equals()` compares **numerically and by scale**.
- `TreeSet` and `TreeMap` determine duplicates based on **`compareTo()` or `Comparator.compare()` returning 0**, so `2.0` and `2.00` are merged by default.
- `HashSet` and `HashMap` use `equals()`/`hashCode()`, so those two representations are two distinct elements/keys.
- The right solution depends on key semantics: **numeric consistency** can use normalization; **distinguishing scale** can use a value-then-scale comparator; **complex domain identity** requires an explicit key type.

Official documentation (Java SE 17):
- [`BigDecimal` — compareTo, equals, hashCode, stripTrailingZeros](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [`Comparable` — natural ordering and consistency with equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html)
- [`TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)
- [`TreeMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)
- [`Comparator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
