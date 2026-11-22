# BigDecimal.hashCode and consequences in HashSet or HashMap

## 1. The problem: two numerically equal numbers can still be two different keys

With `BigDecimal`, it is important to distinguish **numeric value comparison** from **representation comparison**. The two objects `new BigDecimal("2.0")` and `new BigDecimal("2.00")` have the same mathematical value. However, they have different `scale` values, so `equals()` returns `false`; `hashCode()` also takes `scale` into account.

This is what surprises developers when using `BigDecimal` as an element in a `HashSet` or a key in a `HashMap`: adding `2.0` and then checking existence with `2.00` can return **not found**, even though `compareTo()` reports that the two values are equal.

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
System.out.println(a.hashCode() == b.hashCode()); // false for this pair of values
```

The snippet above illustrates three different checks and is not a standalone Java program. The full runnable example section will show the results in each collection type.

## 2. Why does BigDecimal keep both value and scale?

A `BigDecimal` fundamentally represents:

```text
value = unscaledValue × 10^(-scale)

BigDecimal("2.0")  : unscaledValue = 20,  scale = 1
BigDecimal("2.00") : unscaledValue = 200, scale = 2
```

Both represent the same number while preserving the original decimal scale information. This is useful when `scale` carries meaning for formatting, precision granularity, or data contracts.

The three methods have distinct contracts:

| Method | What is checked | `2.0` vs `2.00` |
| --- | --- | --- |
| `a.compareTo(b)` | Ordering **by numeric value**; `0` means equal value | `0` |
| `a.equals(b)` | Numeric value **and scale** must both be equal | `false` |
| `a.hashCode()` | Hash code consistent with `equals()`, accounting for scale | Two different hash codes for this pair |

Java's general contract specifies:

- If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` is **mandatory**.
- If two `hashCode()` values are equal, you **cannot conclude** that `equals()` is true: hash collisions can still occur.
- If `a.equals(b)` is `false`, hash codes **may** collide or differ. Do not check equality by comparing hash codes.
- `BigDecimal.compareTo()` defines an ordering **inconsistent with equals**: `compareTo() == 0` does not guarantee `equals() == true`.

Therefore, to ask "do two numbers have the same mathematical value?", use `compareTo() == 0`. To ask "do two BigDecimal representations have the exact same scale and value?", use `equals()`.

## 3. How does HashSet use equals and hashCode?

`HashSet<BigDecimal>` uses the equivalence rule of `equals()`, with `hashCode()` to locate candidate positions. It does not use `compareTo()` to decide whether an element already exists.

```java
Set<BigDecimal> values = new HashSet<>();
values.add(new BigDecimal("2.0"));
values.add(new BigDecimal("2.00"));

System.out.println(values.size()); // 2
System.out.println(values.contains(new BigDecimal("2.0")));   // true
System.out.println(values.contains(new BigDecimal("2.000"))); // false
```

Here, both `2.0` and `2.00` are added: they are **two distinct elements according to equals**. The value `2.000` is a third representation, so `contains` finds no equivalent object under `equals()`.

The lookup flow can be understood as follows:

```text
add(BigDecimal("2.0"))
  → compute hashCode from the representation of 2.0
  → store element

add(BigDecimal("2.00"))
  → compute hashCode from the representation of 2.00
  → no element with equals(...) == true
  → add new element

contains(BigDecimal("2.000"))
  → locate candidates via hashCode
  → require a candidate with equals(...) == true
  → none found → false
```

This describes the collection at the contract level; bucket layout, hash table implementation, or collision handling may vary. **Neither HashSet nor BigDecimal is broken**: the application must decide whether it wants uniqueness by *value* or by *representation*.

## 4. HashMap with BigDecimal keys: put and get pitfalls

`HashMap<BigDecimal, V>` identifies keys using `hashCode()` and `equals()`. If writes and reads construct `BigDecimal` from strings with different scales, `get` can return `null`.

```java
Map<BigDecimal, String> map = new HashMap<>();
map.put(new BigDecimal("2.0"), "data A");
map.put(new BigDecimal("2.00"), "data B");

System.out.println(map.size()); // 2
System.out.println(map.get(new BigDecimal("2.0")));   // data A
System.out.println(map.get(new BigDecimal("2.000"))); // null
```

Both `put` calls create two separate entries; the second `get` matches neither representation. `null` can mean either a missing key **or** a key mapped to the value `null`; use `containsKey` when you need to distinguish the two situations.

The same issue appears in caches, aggregated data, frequency counting algorithms, grouping by price, or matching decimal-formatted IDs:

- Stored input is `"2.0"` while the query is `"2.00"`.
- Data loaded from JSON, a database, or intermediate calculations has differing scales.
- A `Map<BigDecimal, List<Item>>` grouping splits into multiple groups even though the keys are equal in value.

Do not convert to `double` or call `intValue()` just to work around this: that can lose precision or fractional parts and create an incorrect key rule.

## 5. Java 17+ program demonstrating HashSet, HashMap, TreeSet, and TreeMap

Save the file `BigDecimalCollectionsDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class BigDecimalCollectionsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal lookup = new BigDecimal("2.000");

        System.out.println("compareTo == 0: " + (a.compareTo(b) == 0));
        System.out.println("equals: " + a.equals(b));
        System.out.println("hashCode equal: "
                + (a.hashCode() == b.hashCode()));

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(a);
        hashSet.add(b);
        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("HashSet contains 2.000: "
                + hashSet.contains(lookup));

        Map<BigDecimal, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");
        System.out.println("HashMap size: " + hashMap.size());
        System.out.println("HashMap get 2.0: " + hashMap.get(a));
        System.out.println("HashMap get 2.000: " + hashMap.get(lookup));

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(a);
        treeSet.add(b);
        System.out.println("TreeSet size: " + treeSet.size());
        System.out.println("TreeSet contains 2.000: "
                + treeSet.contains(lookup));

        Map<BigDecimal, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");
        System.out.println("TreeMap size: " + treeMap.size());
        System.out.println("TreeMap get 2.000: " + treeMap.get(lookup));
    }
}
```

Compile and run:

```bash
javac BigDecimalCollectionsDemo.java
java BigDecimalCollectionsDemo
```

Stdout:

```text
compareTo == 0: true
equals: false
hashCode equal: false
HashSet size: 2
HashSet contains 2.000: false
HashMap size: 2
HashMap get 2.0: first
HashMap get 2.000: null
TreeSet size: 1
TreeSet contains 2.000: true
TreeMap size: 1
TreeMap get 2.000: second
```

The program does not print the entire collections directly because iteration order of `HashSet` and `HashMap` is not guaranteed.

Notable point: `TreeSet` and `TreeMap` default to natural ordering via `compareTo()`, so they treat `2.0`, `2.00`, and `2.000` as occupying the same ordering position. `TreeMap.put(b, "second")` updates the value of the existing entry because key comparison returns `0`; `get(lookup)` finds `"second"`.

## 6. Why do TreeSet and TreeMap produce different results?

Hash collections and sorted collections use different rules to identify keys:

| Collection | Default rule to treat as the same element/key | `2.0` and `2.00` |
| --- | --- | --- |
| `HashSet<BigDecimal>` | `hashCode` + `equals` | Two elements |
| `HashMap<BigDecimal, V>` | `hashCode` + `equals` | Two keys |
| `TreeSet<BigDecimal>` | `compareTo` returns `0` | One element |
| `TreeMap<BigDecimal, V>` | `compareTo` returns `0` | One key; later put updates value |
| `TreeSet/TreeMap` with custom `Comparator` | Comparator returns `0` | Depends on comparator |

`TreeSet` and `TreeMap` behave consistently with `compareTo()`, but because `BigDecimal`'s natural ordering is **inconsistent with equals**, sorted collections using it do not fully obey the general `equals`-based contract of `Set`/`Map`. Sorted collection behavior remains defined in terms of the comparator.

Practical consequence: switching code from `HashMap` to `TreeMap` can change both **the number of keys** and **the overwrite rule**, not just iteration order. Choose the collection based on business requirements, and ensure every part of the application uses the same definition of uniqueness.

No `Comparator` can be passed to `HashMap` or `HashSet` to change the `equals` behavior of keys. If you use a hash collection and want different scales to map to a single key, you must normalize keys or design a dedicated key type.

## 7. Three key policies for three data requirements

**Preserve scale:** use `BigDecimal` as-is as a hash key if `2.0` and `2.00` must be distinguished. This directly uses the existing `equals/hashCode` contract.

**Same numeric value means same key:** normalize values before `put`, `get`, `containsKey`, and `remove`, including when reloading from storage:

```java
static BigDecimal numericKey(BigDecimal input) {
    return java.util.Objects.requireNonNull(input).stripTrailingZeros();
}
```

```java
Map<BigDecimal, String> map = new HashMap<>();
map.put(numericKey(new BigDecimal("2.00")), "two");
String result = map.get(numericKey(new BigDecimal("2.000"))); // "two"
```

These snippets belong inside a class/method with imports for `BigDecimal`, `Map`, and `HashMap`. `stripTrailingZeros` preserves the number but can make the scale negative (`1000.0 → 1E+3`) and reduces every zero to scale 0. Collapsing multiple representations into one canonical key requires the application to have a policy for duplicate entries (keep, reject, overwrite, merge). Store the original text or scale in a separate field if auditing is needed.

**Fixed scale:** if the data domain truly requires two decimal digits and no data loss is allowed, use `setScale(2, RoundingMode.UNNECESSARY)`. Values that cannot be represented exactly throw `ArithmeticException`. If rounding is permitted, you need an explicit rounding mode and clear rules for merged keys; two different numeric values can become the same value after rounding. The lesson **Scale normalization policy before storing or comparing** covers database, JSON, precision, negative scale, and those boundaries separately.

## 8. Encoding the policy in an immutable key type

```java
public record NumericDecimalKey(BigDecimal value) {
    public NumericDecimalKey {
        value = java.util.Objects.requireNonNull(value)
                .stripTrailingZeros();
    }
}
```

This is a standalone `record` in Java 17 and needs `import java.math.BigDecimal`. `equals` and `hashCode` are automatically generated from the **normalized** component. When you need to keep the original input string or scale, store them separately; the canonical key exists solely for numeric-value identity.
## 9. Edge cases and common mistakes

**1. Comparing with compareTo but looking up in a HashMap.** If code checks `compareTo() == 0` first and then queries `map.get(otherBigDecimal)`, the two steps are using two different definitions of equality. A numeric check does not guarantee a hash lookup will succeed.

**2. Comparing only hashCode to decide duplicates.** Hash collisions can occur. Always follow the `equals()` contract, or normalize and let the collection perform the comparison.

**3. Calling `stripTrailingZeros()` on the stored key but not on the query key.** This easily leads to cache misses or missing records. Normalize consistently at all operations, including write, read, delete, and state restoration.

**4. Mistaking negative scale after normalization for an error.** `1000.0.stripTrailingZeros()` produces `1E+3` with scale `-3`. The number is still exact. If a consumer forbids this form, handle formatting/scale at the output boundary according to a separate contract.

**5. Unintentionally merging data after normalization.** For instance, `2.0` and `2.00` were originally two distinct keys. After normalization, they collide. When using `Collectors.toMap`, duplicate keys without a merge function cause the collector to throw `IllegalStateException`. In a loop with `HashMap.put`, the later value overwrites the earlier one. Choose an explicit policy.

**6. Using rounding to create keys when identity requires exact values.** Rounding can equate two numbers that were originally numerically distinct. `stripTrailingZeros()` only removes redundant zeros and preserves the value; `setScale(..., HALF_UP)` can alter the value.

**7. Constructing BigDecimal from a double literal.** `new BigDecimal(0.1)` represents the exact binary approximation of `double`, not exact decimal `0.1`. When exact decimal input is required, use `new BigDecimal("0.1")`; if the source is already a `double`, `BigDecimal.valueOf(double)` is usually more appropriate than the `double` constructor, though it cannot recover errors introduced earlier.

**8. Assuming BigDecimal mutates itself after becoming a key.** `BigDecimal` is **immutable**, so the key object itself cannot have its scale or value altered in place. However, a wrapper object containing a mutable field and implementing `equals/hashCode` based on that field can break hash collection behavior if the field is mutated after `put`. Prefer immutable keys.

**9. Confusing storage data with display representation.** The number `2.00` may need to display exactly two digits to the user, while the cache policy only cares about the value `2`. Keep these rules in separate steps: key identification, validation, and formatting.

## 10. Which approach should you choose in practice?

| Requirement | Approach | Additional checks needed |
| --- | --- | --- |
| Scale is part of identity | Use `BigDecimal` directly in `HashMap/HashSet` | Do data producers keep scales stable? |
| All numerically equivalent representations map to one key | Use `stripTrailingZeros()` consistently or a normalized key type | Handling duplicate entries after normalization and serialization |
| Keys must have a fixed number of decimal digits | `setScale(fixedScale, UNNECESSARY)` | Which values should be rejected when inexact? |
| Need ascending/descending order by numeric value | Default `TreeMap/TreeSet` using `compareTo()` | Is treating different scales as one key acceptable? |
| Need to store smallest integer units | Convert exactly to `BigInteger`/`long` if range permits | Units, overflow, and exact conversion |

A `TreeMap` can naturally satisfy sorting and collapsing different scales, but it cannot be treated as a transparent drop-in replacement for `HashMap`: key identification behavior also changes.

## 11. Self-check questions

1. What does `new BigDecimal("0.0").equals(BigDecimal.ZERO)` return? **False**: scale 1 differs from scale 0, even though `compareTo(BigDecimal.ZERO) == 0`.
2. Adding `new BigDecimal("3.0")` and `new BigDecimal("3.00")` to a `HashSet` yields how many elements? **Two**: `equals()` distinguishes scale.
3. Adding the same two values to a default `TreeSet` yields how many elements? **One**: `compareTo()` treats both numbers as equal.
4. Why might two different objects with the same `hashCode` not be the same `HashMap` key? **Because** the collection still needs `equals()` to distinguish keys whose hash codes collide.
5. Should you use `setScale(2, HALF_UP)` or `stripTrailingZeros()` to build a key based on exact numeric value? **`stripTrailingZeros()`**: it does not alter the numeric value; `HALF_UP` can merge distinct values.
6. At which steps must normalization occur for consistent lookup? **At every key-creation boundary**, especially `put`, `get`, `containsKey`, `remove`, and when reading back from stored data.

## 12. Conclusion

`BigDecimal.compareTo()` compares **numeric value**, whereas `BigDecimal.equals()` and `hashCode()` consider both **numeric value and scale**. As a result, `HashSet` and `HashMap` can keep `2.0` and `2.00` as two separate elements/keys, while default `TreeSet` and `TreeMap` treat them as one under `compareTo()`.

The deciding factor is **your application's definition of uniqueness**. If representation matters, use `BigDecimal` directly; if only numeric value matters, normalize accurately and consistently; if the domain requires a fixed scale, validate and reject non-conforming data before creating keys. Always define a duplicate-handling policy when mapping multiple representations to a single shared key.
