# Example of BigDecimal with Different Scales in Ordered Collections

## 1. Objective

`BigDecimal` represents arbitrary-precision decimal numbers with two components: **unscaled value** (an integer) and **scale** (the number of decimal digits according to its representation). Two objects having the same **numeric value** can still have different scales. This is a classic case where **equality by `equals()` is not identical to ordering equivalence by `compareTo()`**.

This lesson helps you:

- Understand why `new BigDecimal("1.0")` and `new BigDecimal("1.00")` have `equals() == false` yet `compareTo() == 0`.
- Predict accurately what happens when placing those two values into `HashSet`, `TreeSet`, `HashMap`, `TreeMap`.
- Understand that ordered collections use `compareTo` or `Comparator` to evaluate both sort position and **whether a key already exists**.
- Choose the appropriate policy when scale must be distinguished or when representations with the same numeric value should be treated as one.
- Apply `stripTrailingZeros()` or an explicit comparator for the right purpose; avoid losing scale information that carries business meaning.

## 2. BigDecimal consists of numeric value and scale

For `BigDecimal`, the value is expressed by the formula:

```text
numeric value = unscaledValue × 10^(-scale)
```

Examples:

| Construction | Unscaled value | Scale | Numeric value |
| --- | ---: | ---: | ---: |
| `new BigDecimal("1.0")` | `10` | `1` | `1` |
| `new BigDecimal("1.00")` | `100` | `2` | `1` |
| `new BigDecimal("1")` | `1` | `0` | `1` |
| `new BigDecimal("1E+2")` | `1` | `-2` | `100` |
| `new BigDecimal("0.000")` | `0` | `3` | `0` |

In Java:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.unscaledValue()); // 10
System.out.println(a.scale());         // 1
System.out.println(b.unscaledValue()); // 100
System.out.println(b.scale());         // 2
```

This is an illustrative snippet requiring `import java.math.BigDecimal;`. Distinguish **scale** from **precision**: precision is the number of digits in the unscaled value (excluding sign), whereas scale specifies the position of the decimal point. `"1.00"` has precision 3, scale 2; `"1.0"` has precision 2, scale 1.

Scale can be information worth preserving: representing measurement accuracy, recorded significant digits, or currency display policy. Hence Java provides both a way to compare “equal in decimal representation” and a way to compare “equal in numeric value”.

## 3. How do `equals()` and `compareTo()` differ?

### 3.1. `BigDecimal.equals(Object)` checks both numeric value and scale

For two `BigDecimal` values, `equals()` returns `true` only when they have **the same unscaled value and the same scale**. Therefore:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

a.equals(b);                // false
a.hashCode() == b.hashCode(); // false in this example
```

`BigDecimal`'s `hashCode()` is consistent with `equals()`: if two values are `equals`, their hashes must be equal. When only scale differs, hashes **may** differ, and in the example of `1.0` and `1.00` they indeed differ. Do not infer that a hash is a unique identifier because collisions can still occur.

### 3.2. `compareTo()` compares numeric value

`BigDecimal.compareTo(BigDecimal)` performs an ordering comparison by **numeric value**, not treating scale as a distinguishing factor when numeric values are equal:

```java
a.compareTo(b);  // 0
```

Rules:

- Negative value: `a.compareTo(b) < 0` means `a` is less than `b`.
- Returns `0`: `a` and `b` have the same numeric value for this comparison.
- Positive value: `a.compareTo(b) > 0` means `a` is greater than `b`.

Do not rely on the absolute magnitude of negative/positive results; the contract guarantees only **sign**. With `BigDecimal`, the `compareTo() == 0` relation can be broader than `equals() == true`.

`BigDecimal` is a textbook example of **natural ordering inconsistent with equals**: two elements can be equivalent in order yet not equal by `equals`.

### 3.3. Exact relationships

| Check | `1.0` vs `1.00` | Meaning |
| --- | --- | --- |
| `a == b` | `false` | Two separately created objects have different identities. |
| `a.equals(b)` | `false` | Unscaled value and scale do not match as a pair. |
| `a.compareTo(b) == 0` | `true` | Same mathematical numeric value. |
| `a.scale() == b.scale()` | `false` | One has scale 1, the other has scale 2. |
| `a.stripTrailingZeros().equals(b.stripTrailingZeros())` | `true` | Both values reduce to the same canonical form in this example. |

Note that `Objects.equals(a,b)` still calls `a.equals(b)` when both are non-null; it **does not automatically switch to `compareTo()`**.

## 4. Why do `HashSet` and `TreeSet` give different results?

### 4.1. HashSet relies on `equals` and `hashCode`

`HashSet` uses hashes to distribute elements and uses the `equals` relation to distinguish potentially colliding keys. With:

```java
Set<BigDecimal> hashed = new HashSet<>();
hashed.add(new BigDecimal("1.0"));
hashed.add(new BigDecimal("1.00"));
```

`hashed.size()` is **2** because the two `BigDecimal` objects are not `equals()`. These are two distinct elements under **`BigDecimal`'s equality relation**.

### 4.2. TreeSet relies on `compareTo` or `Comparator` ordering

`TreeSet` is a `SortedSet`; if no comparator is supplied, it uses the **natural ordering** of its elements, here `BigDecimal.compareTo`.

```java
TreeSet<BigDecimal> sorted = new TreeSet<>();
boolean first = sorted.add(new BigDecimal("1.0"));
boolean second = sorted.add(new BigDecimal("1.00"));
```

Results:

- `first` is `true`: the first element is added.
- `second` is `false`: the second object has `compareTo(...) == 0` with the existing element.
- `sorted.size()` is **1**: `TreeSet` treats the two values as the same ordering key, even though `equals` returns `false`.
- `sorted.contains(new BigDecimal("1.000"))` is `true`: lookup also relies on the ordering relation.
- If `1.0` is added first, the retained element has form `1.0` (scale 1); if `1.00` is added first, the retained element has form `1.00` (scale 2). Keep this in mind if application code inspects `scale()` of the stored element.

The general rule of `TreeSet` is **comparator returns 0 ⇒ the element is treated as a duplicate for the tree structure**, regardless of what their `equals` returns.

### 4.3. Does this violate the `Set` contract?

The general `Set` contract defines duplicates according to `equals`. Java documentation states that the ordering used for a sorted set **should be consistent with `equals`** if the sorted set is to fully obey the general `Set` contract. When ordering is inconsistent like `BigDecimal`, `TreeSet` still has well-defined behavior determined by the comparator, yet its treatment of duplicate elements **differs** from a `HashSet` holding the same values.

Do not conclude that `TreeSet` has a bug or `BigDecimal.compareTo` is implemented wrongly. It is the result of **two different equivalence definitions**. The designer must choose which equality relation applies to the collection.

## 5. `TreeMap`: a new key can replace the old key's value

`TreeMap` likewise relies on `compareTo` or a comparator to sort and identify equivalent keys:

```java
TreeMap<BigDecimal, String> map = new TreeMap<>();
map.put(new BigDecimal("1.0"), "first");
map.put(new BigDecimal("1.00"), "second");
```

Results:

- `map.size() == 1`: the two keys compare as 0.
- The value of the equivalent key is updated to `"second"`.
- When added in the exact order above, the key kept in the entry is `1.0` (scale 1), because updating the value does not replace the stored key object.
- `map.get(new BigDecimal("1.000"))` returns `"second"`.

In contrast, `HashMap<BigDecimal, String>` with these two keys will have **two entries** when using `BigDecimal`'s `equals/hashCode`.

Practical scenario: If you store price levels `1.0` and `1.00` as two separate tiers needing to preserve precision/scale, `TreeMap` under natural ordering may **merge them into one key**. If you store thresholds based solely on numeric value, merging may be precisely the intended behavior.

## 6. Runnable Java 17+ program

Create file **`BigDecimalSortedSetDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalSortedSetDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("a scale: " + a.scale());
        System.out.println("b scale: " + b.scale());
        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo: " + a.compareTo(b));
        System.out.println("hash equals: "
                + (a.hashCode() == b.hashCode()));

        Set<BigDecimal> hashed = new HashSet<>();
        hashed.add(a);
        hashed.add(b);
        System.out.println("HashSet size: " + hashed.size());

        TreeSet<BigDecimal> sorted = new TreeSet<>();
        System.out.println("TreeSet add a: " + sorted.add(a));
        System.out.println("TreeSet add b: " + sorted.add(b));
        System.out.println("TreeSet size: " + sorted.size());
        System.out.println("TreeSet stored: "
                + sorted.first().toPlainString());
        System.out.println("TreeSet contains 1.000: "
                + sorted.contains(new BigDecimal("1.000")));

        TreeMap<BigDecimal, String> sortedMap = new TreeMap<>();
        sortedMap.put(a, "first");
        sortedMap.put(b, "second");
        System.out.println("TreeMap size: " + sortedMap.size());
        System.out.println("TreeMap key scale: "
                + sortedMap.firstKey().scale());
        System.out.println("TreeMap lookup 1.000: "
                + sortedMap.get(new BigDecimal("1.000")));

        Map<BigDecimal, String> hashedMap = new HashMap<>();
        hashedMap.put(a, "first");
        hashedMap.put(b, "second");
        System.out.println("HashMap size: " + hashedMap.size());

        BigDecimal cleanA = a.stripTrailingZeros();
        BigDecimal cleanB = b.stripTrailingZeros();
        System.out.println("canonical equals: "
                + cleanA.equals(cleanB));
        System.out.println("canonical hash equals: "
                + (cleanA.hashCode() == cleanB.hashCode()));

        Comparator<BigDecimal> byValueThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        TreeSet<BigDecimal> strict = new TreeSet<>(byValueThenScale);
        strict.add(a);
        strict.add(b);
        System.out.println("strict TreeSet size: " + strict.size());

        BigDecimal large = new BigDecimal("600.0")
                .stripTrailingZeros();
        System.out.println("600.0 canonical: " + large.toString());
        System.out.println("0.000 canonical: "
                + new BigDecimal("0.000")
                        .stripTrailingZeros().toString());
    }
}
```

Compile and run:

```bash
javac BigDecimalSortedSetDemo.java
java BigDecimalSortedSetDemo
```

Output:

```text
a scale: 1
b scale: 2
equals: false
compareTo: 0
hash equals: false
HashSet size: 2
TreeSet add a: true
TreeSet add b: false
TreeSet size: 1
TreeSet stored: 1.0
TreeSet contains 1.000: true
TreeMap size: 1
TreeMap key scale: 1
TreeMap lookup 1.000: second
HashMap size: 2
canonical equals: true
canonical hash equals: true
strict TreeSet size: 2
600.0 canonical: 6E+2
0.000 canonical: 0
```

Explanation of key points:

1. `a` and `b` represent the same numeric value but have scales 1 and 2, so `equals()` is `false` and `compareTo()` is 0.
2. `HashSet` and `HashMap` keep two distinct entries because they rely on `BigDecimal` equality.
3. Default `TreeSet` adds `a` successfully and rejects `b` because natural ordering treats the two values as equivalent; it also `contains` the value `1.000`.
4. `TreeMap` retains the first key with scale 1 and updates the equivalent key's value to `"second"`.
5. The two normalized versions via `stripTrailingZeros()` have identical `equals` and hash.
6. Custom comparator `byValueThenScale` further separates keys having the same numeric value but different scales, so `strict` has two elements.
7. `stripTrailingZeros()` can return a power-of-10 scientific notation form such as `6E+2`; zero is normally normalized to `0`. This is a change in **representation**, even though the numeric value is unchanged.

The output above does not print hash iteration order or unnecessary hash integers directly; the example only checks whether the hashes are equal.

## 7. Which comparator should be used if TreeSet needs to distinguish scale?

If business logic requires treating `1.0` and `1.00` as **two distinct values**, the ordered set's comparator must return non-zero when scales differ:

```java
Comparator<BigDecimal> byValueThenScale =
        Comparator.<BigDecimal>naturalOrder()
                .thenComparingInt(BigDecimal::scale);

TreeSet<BigDecimal> values = new TreeSet<>(byValueThenScale);
values.add(new BigDecimal("1.0"));
values.add(new BigDecimal("1.00"));
// size() == 2
```

First the comparator compares numeric value, then if numeric values match it compares scale. For `BigDecimal`, same numeric value **and** same scale is equivalent to `equals()` being true, so this comparator is **consistent with equals** within the domain of `BigDecimal` objects.

Benefit: you get both numeric order for traversal and preservation of `BigDecimal.equals()`'s scale distinction. Drawback: two representations of the same numeric value occupy two different positions; whether this is right or wrong depends on the problem. The comparator does not alter `BigDecimal.equals()` outside `TreeSet`.

**Warning:** do not use `Comparator.comparing(BigDecimal::scale)` alone if you need to distinguish all values. Two numbers `1.00` and `2.00` both have scale 2 yet different numeric values; comparing only scale will treat them as duplicates and lose an element.

## 8. Want the same numeric value to be the same key across all collections?

Sometimes business logic defines `1.0`, `1.00`, and `1` as one. In that case you can normalize before storing:

```java
static BigDecimal canonical(BigDecimal input) {
    return java.util.Objects.requireNonNull(
            input, "input").stripTrailingZeros();
}
```

This is an illustrative method placed in a Java class. From there:

```java
Set<BigDecimal> numericKeys = new HashSet<>();
numericKeys.add(canonical(new BigDecimal("1.0")));
numericKeys.add(canonical(new BigDecimal("1.00")));
// size() == 1
```

The normalized keys have `equals()`/`hashCode()` matching the chosen “same numeric value” relation; `HashSet` and `TreeSet` (using natural ordering) now agree more closely on key grouping.

However, this rule **erases scale differences**. If `1.00` carries measurement, display, or invoice formatting information, it must not be silently discarded. You can retain the original value in a separate field for display and use the canonical key for lookup, provided the two roles are cleanly separated.

Another approach is using a value object that defines equality by numeric value:

```java
record NumericKey(BigDecimal canonicalValue) {
    public NumericKey {
        canonicalValue = java.util.Objects.requireNonNull(
                canonicalValue, "canonicalValue")
                .stripTrailingZeros();
    }
}
```

With this record, the field is normalized right at construction, so the record generates `equals`/`hashCode` based on the canonical value. If `NumericKey` needs to be sorted, an appropriate comparator must be supplied or `Comparable` implemented; being a record **does not automatically give it a natural ordering**.

### Notes on `stripTrailingZeros()`

- `new BigDecimal("600.0").stripTrailingZeros()` can become `6E+2` with a negative scale; if printing in decimal form without scientific notation is needed, use `toPlainString()` or format as required.
- `BigDecimal.ZERO` has scale 0; normalizing a zero value like `new BigDecimal("0.000")` with `stripTrailingZeros()` can yield zero with scale 0.
- If a fixed scale such as 2 digits for currency is needed, consider `setScale(2, ...)` with an explicit rounding policy. This operation is not equivalent to “dropping trailing insignificant zeros” in all cases.
- Avoid creating `new BigDecimal(0.1)` from `double` when an exact decimal representation `0.1` is needed; it reflects the binary value of `double`. Prefer decimal strings or `BigDecimal.valueOf(0.1)` when appropriate.
- For money, currency is also part of the business value's identity: `1.00 USD` is not the same as `1.00 EUR` merely because both have the same `BigDecimal`.

## 9. Applying to concrete problems

### Scenario A: list of numeric thresholds

You use `TreeSet<BigDecimal>` to store comparison thresholds. Equal numeric values `1.0` and `1.00` represent only **one threshold**, so `BigDecimal`'s natural ordering is appropriate. Even so, remember that when retrieving an element, scale may reflect **whichever value was inserted first** rather than a single canonical representation.

### Scenario B: measurement data where precision matters

You need to keep `1.0` (one digit after the decimal point) distinct from `1.00` (two digits). If both must reside in an ordered set, use a comparator comparing **numeric value first, scale second** so neither record is lost.

### Scenario C: unified cache key across HashMap and TreeMap

If the same numeric value must look up the same key in both `HashMap` and `TreeMap`, normalize data at the **input boundary** before creating keys. Ensure both writes and reads use the same rule. Do not mix normalized keys and raw keys arbitrarily across places, as that easily produces unpredictable behavior.

### Scenario D: testing and bug detection

Use tests containing at least the values `1`, `1.0`, `1.00`, `2.00`, `0.000`, and a number with negative scale. Test add, contains, remove, and map key lookup; verify **which key object is retained** and **the value after duplicate put**. If using a custom comparator, test reflexivity, sign symmetry, transitivity, and consistency with equality requirements.

## 10. Common mistakes

| Mistake | What happens | How to prevent |
| --- | --- | --- |
| Thinking `BigDecimal.equals()` checks only numeric value | `1.0` and `1.00` are treated as distinct | Remember `equals` checks both unscaled value and scale. |
| Thinking `TreeSet` detects duplicates using `equals()` | `TreeSet` unexpectedly shrinks in size | Check `compareTo`/`Comparator` because returning 0 counts as duplicate. |
| Using `TreeMap` and expecting to keep two keys of different scales | Later `put` updates the equivalent key's entry | Use a scale-distinguishing comparator if business logic requires it. |
| Looking at `HashSet.size()` and assuming `TreeSet.size()` is identical | The two sets use different equivalence relations | Determine the expected equality rule before choosing the structure. |
| Sorting only by scale | Different numeric values with the same scale are treated as duplicates | Sort by numeric value first, then use scale as tie-breaker. |
| Normalizing with `stripTrailingZeros` while still needing original scale | Loses initial representation information | Keep the original value separately for display/auditing. |
| Comparing `hashCode` to conclude two numbers are equal | Hash collisions can occur | Use `equals` or `compareTo` depending on semantics, never hash as an equality criterion. |
| Constructing `BigDecimal` from `double` carelessly | Decimal value may differ from expectations | Use exact strings or `valueOf` according to intent. |
| Using `setScale` with an implicit rounding policy | May lose numeric information or throw `ArithmeticException` when rounding is needed | Specify scale and `RoundingMode` explicitly when applying. |

## 11. Checklist when choosing SortedSet/SortedMap for BigDecimal

1. Determine **duplicate by numeric value** vs **duplicate by numeric value and scale**.
2. Check whether data sources can send representations like `1.0`, `1.00`, `1E+0`.
3. If using natural ordering, understand that `compareTo() == 0` determines duplicates in `TreeSet`/`TreeMap`.
4. If consistency with `BigDecimal.equals()` is needed, use a comparator by numeric value then by scale.
5. If numeric-value equality is needed across hash collections too, use a consistently normalized canonical key.
6. Do not use hash, ordinal, or display formatting in place of comparison rules.
7. Write tests for `add`, `contains`, `put`, `get`, `remove`, and duplicate-insertion rules.
8. Preserve scale when it carries business meaning; normalize only when permitted.

## 12. Self-check questions

**Question 1.** What does `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` return? What about `compareTo`?

**Answer:** `equals` returns `false` because scales differ; `compareTo` returns `0` because numeric values are equal.

**Question 2.** Adding those two numbers to a default `HashSet` and `TreeSet` yields what sizes?

**Answer:** `HashSet` has 2; `TreeSet` has 1.

**Question 3.** Why can `TreeMap.put(1.00, value2)` replace the value attached to key `1.0`?

**Answer:** Because `TreeMap` recognizes equivalent keys via ordering comparison. `1.0.compareTo(1.00) == 0`.

**Question 4.** Need to keep two values with the same numeric value but different scales in `TreeSet`; which comparator should be chosen?

**Answer:** Compare numeric value by natural order, then compare scale with `thenComparingInt(BigDecimal::scale)`.

**Question 5.** When should `stripTrailingZeros` be used for keys?

**Answer:** When business logic wants representations with the same numeric value to be the same key, and accepts dropping scale differences. Normalization must be applied uniformly on both writes and lookups.

**Question 6.** Is `BigDecimal` buggy because `compareTo` is inconsistent with `equals`?

**Answer:** No. These are two relations defined in the API documentation. Developers need to understand that sorted collections use the comparator as the equivalence basis and choose the appropriate structure/comparison.

**Takeaway:** `BigDecimal.equals()` inspects **numeric value and scale**, whereas `BigDecimal.compareTo()` inspects **numeric value**. Because `TreeSet`/`TreeMap` treat a comparison result of **0** as the same element/key, `1.0` and `1.00` occupy only one slot under natural ordering.
