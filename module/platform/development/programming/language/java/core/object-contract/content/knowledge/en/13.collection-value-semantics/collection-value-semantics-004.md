# Hash Codes of List, Set, and Map Under Their Respective Contracts

## 1. Goal: Understand the Formulas Specified by the API

In the Java Collections Framework, `List`, `Set`, and `Map` define **specific rules for `equals(Object)` and `hashCode()`** so that different implementations remain compatible when representing the same logical value.

Key point: **there is no single universal `hashCode()` formula for all collections**. These three types have different equality semantics:

- **`List`:** an ordered sequence of positioned elements, so order is part of the value.
- **`Set`:** a collection of unique elements; position and iteration order are not part of equality under the `Set` contract.
- **`Map`:** a collection of mappings from keys to values; iteration or insertion order is not part of equality under the `Map` contract.

Therefore, `List` uses a cumulative multiply-by-**31** formula; `Set` sums element hash codes; and `Map` sums *entry* hash codes, where each entry combines key and value hash codes via XOR. These are **formulas specified by the Java 17 Javadoc**, not arbitrary bucket details specific to `ArrayList`, `HashSet`, or `HashMap`.

> Type distinction: `List` and `Set` both extend `Collection`; `Map` does **not** extend `Collection`. They belong to the same Java Collections Framework but have separate contracts.

## 2. Foundation: The `equals()` and `hashCode()` Contract

Before examining the formulas, recall the `Object` contract:

1. If `a.equals(b)` returns `true`, then `a.hashCode() == b.hashCode()` **must** hold.
2. If two objects are **not** equal, they **may still** share the same hash code (a collision); a hash code is not a unique ID.
3. During a single Java execution, if no information used by `equals` changes, the result of `hashCode` on the same object must remain consistent.
4. There is no requirement that hash codes stay fixed across different JVM runs.

Each `List`/`Set`/`Map` type specifies a hash formula to ensure that **two logically equal instances, even from different implementation classes, produce the same hash code**.

For example, an `ArrayList<String>` and a `LinkedList<String>` holding the same element sequence can be equal; a `HashSet<String>` and a `LinkedHashSet<String>` holding the same element set are also equal; likewise for a `HashMap` and a `LinkedHashMap` holding the same key–value pairs.

The elements, keys, and values themselves must still implement `equals/hashCode` according to contract. A collection cannot "fix" an element whose pair of methods is broken.

## 3. `List.hashCode()`: Order-Dependent Accumulation

### 3.1. Official Rule

The `List.hashCode()` Javadoc specifies an equivalent algorithm:

```java
int hashCode = 1;
for (E element : list) {
    hashCode = 31 * hashCode
            + (element == null ? 0 : element.hashCode());
}
```

This is a **Java pseudocode snippet from the API contract**, where the variable `list` represents a list. It is not a standalone program because `E` and `list` are not declared.

Explanation:

- Starts at `1`, so **an empty list has a hash code of `1`**.
- Each element, in the **exact iteration order of the list**, contributes to the running value.
- A `null` element contributes `0`; the formula still multiplies the accumulated hash code by `31`.
- Multiplications and additions are performed using Java `int` arithmetic; if the value exceeds the 32-bit range, the integer overflows according to `int` rules. Do not convert to floating-point, strings, or random hashes.

Because multiplying by `31` occurs at every step, **order usually affects the hash code**. However, two lists with different orders *can happen to share the same hash code*; positional differences make them unequal under `List.equals`, rather than guaranteeing distinct hash codes.

### 3.2. Manual Calculation

Given `"A".hashCode() == 65`, `"B".hashCode() == 66`:

| List | Calculation | Hash Code |
| --- | --- | ---: |
| `[]` | Initial value | `1` |
| `["A"]` | `31 × 1 + 65` | `96` |
| `["A", "B"]` | `31 × 96 + 66` | `3042` |
| `["B", "A"]` | `31 × (31 + 66) + 65` | `3072` |
| `["A", null]` | `31 × (31 + 65) + 0` | `2976` |

This order matches `List.equals`: two lists are equal when the other object is also a `List`, has the same size, and each pair of elements at the **same position** is equal (handling `null` properly).

Two `List` instances with the same elements in different orders are not considered equal by default. A list can also contain duplicate elements, such as `["A", "A"]`, and every **position** is still included in the formula.

### 3.3. Independent of Storage Class

An `ArrayList<>(List.of("A", "B"))` and a `LinkedList<>(List.of("A", "B"))` are equal and both have `hashCode() == 3042`. Regardless of one class using an array and the other a linked list, **the `List` contract determines their hash code**.

If you implement `List` yourself, you must follow this contract; overriding only `equals` while computing an arbitrary hash value based on memory location will break compatibility with other implementations.

## 4. `Set.hashCode()`: Sum of Element Hash Codes

### 4.1. Official Rule

According to the `Set` Javadoc, a set's hash code is the **sum of the hash codes of its elements**, with `null` treated as `0`:

```java
int hashCode = 0;
for (E element : set) {
    hashCode += (element == null ? 0 : element.hashCode());
}
```

This is a **contract pseudocode snippet**, not a standalone Java file.

- **An empty set has hash code `0`.**
- The order of addition does not change the integer result; a set's hash code **does not depend on insertion or iteration order**.
- Each element present in the set is added once; equal values are not stored as two distinct elements under the `Set` contract.
- Hash codes can match between different sets, even when they have no elements in common.

For example, `Set.of("A", "B")` evaluates to `65 + 66 = 131`. A `HashSet` adding A then B and a `LinkedHashSet` adding B then A both represent the same set and have hash code `131`. A set containing `"A"` and `null`, in an implementation allowing `null` like `HashSet`, has hash code `65 + 0 = 65`.

### 4.2. Why Is the `List` Formula Not Applied to `Set`?

A `Set` has no *element position* in its definition of equality. If the hash code depended on iteration order, two equal sets with different iteration orders could receive different hash codes, violating `equals => hashCode`.

The definition of `Set.equals` checks whether two sets have the same size and equivalent elements, **without comparing positions**. Therefore, summation is a commutative combination operation suited to set semantics.

Distinguish between `LinkedHashSet` maintaining an iteration order and that order **not participating** in `Set.equals/hashCode`. A class with a deterministic iteration order must still adhere to the same `Set` contract.

### 4.3. Collisions Do Not Violate the Contract

Suppose two distinct elements have hash codes `10` and `20`, while a third element has hash code `30`. Then a set containing the first two elements and a set containing the third element **can share the same hash code `30`** without being equal.

Do not conclude that two sets are equal solely from their hash codes. When exact comparison is needed, use `set1.equals(set2)`.

## 5. `Map.hashCode()`: Sum of Mapping Hash Codes

### 5.1. Official `Map` Rule

According to the `Map.hashCode()` contract:

> The hash code of a map equals the sum of the hash codes of the entries in `entrySet()`.

Written as a formula:

```text
hashCode(map) = Σ hashCode(entry) for each entry ∈ map.entrySet()
```

This is a formula of the `Map` interface and does not require the map to be implemented with a hash table. Different implementations with the same logical mappings must produce the same hash code.

### 5.2. Hash Code of a `Map.Entry`

`Map.Entry.hashCode()` specifies:

```java
int entryHash = (key == null ? 0 : key.hashCode())
              ^ (value == null ? 0 : value.hashCode());
```

This is a **formula illustration snippet**, in which `key` and `value` are undeclared variables. The `^` symbol in Java is **bitwise XOR** on two integers, **not exponentiation**.

Then `Map.hashCode()` sums the entry hash codes:

```java
int mapHash = 0;
for (Map.Entry<K, V> entry : map.entrySet()) {
    K key = entry.getKey();
    V value = entry.getValue();
    mapHash += (key == null ? 0 : key.hashCode())
            ^ (value == null ? 0 : value.hashCode());
}
```

**Operator precedence note:** in the final Java expression above, compound assignment `+=` has low assignment precedence; to make it explicit that each entry is XORed first and then added to the sum, parenthesize it as in the following version:

```java
mapHash += ((key == null ? 0 : key.hashCode())
         ^  (value == null ? 0 : value.hashCode()));
```

If copying into runnable code, always include these parentheses to avoid misreading the expression and to help readers.

### 5.3. Manual Calculation Example

For a map containing `"A" -> 1` and `"B" -> 2`:

| Mapping | Key Hash Code | Value Hash Code | Entry Hash Code (XOR) |
| --- | ---: | ---: | ---: |
| `"A" -> 1` | `65` | `1` | `65 ^ 1 = 64` |
| `"B" -> 2` | `66` | `2` | `66 ^ 2 = 64` |

The sum of the two entries is `64 + 64 = 128`. Because addition is commutative, a map adding B before A and a map adding A before B still have hash code `128` if they represent the same mappings.

Special cases:

- **Empty map:** no entries to sum, hence `hashCode() == 0`.
- **`null` key or `null` value:** that component's hash code contributes `0` if allowed by the implementation. For instance, a `HashMap` with `"A" -> null` and `null -> "B"` has total hash `(65 ^ 0) + (0 ^ 66) = 131`.
- **Changing the value for the same key:** the logical mapping has changed, so the resulting hash code may change. However, not every mapping change is guaranteed to yield a different hash code; collisions can still occur.

`Map.equals` compares **mappings**: two maps are equal if they contain the same set of key–value pairs under the respective equality semantics, regardless of insertion order. Hence the hash code is based on entries, not keys alone.

## 6. Java 17 Program: Comparing the Three Contracts

A complete example using two different implementations for each type. The checks rely on interface formulas and use `String`/`Integer` data with deterministic hash codes; they do not infer anything from buckets or unguaranteed ordering of `HashMap`/`HashSet`.

Create the file **`CollectionHashContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionHashContractDemo {
    public static void main(String[] args) {
        List<String> arrayList = new ArrayList<>(List.of("A", "B"));
        List<String> linkedList = new LinkedList<>(List.of("A", "B"));
        List<String> reversedList = List.of("B", "A");
        System.out.println("list equals: " + arrayList.equals(linkedList));
        System.out.println("list hashes: " + arrayList.hashCode()
                + ", " + linkedList.hashCode());
        System.out.println("reversed list hash: " + reversedList.hashCode());
        System.out.println("list with null hash: "
                + Arrays.asList("A", null).hashCode());

        Set<String> hashSet = new HashSet<>(List.of("A", "B"));
        Set<String> linkedSet = new LinkedHashSet<>(List.of("B", "A"));
        System.out.println("set equals: " + hashSet.equals(linkedSet));
        System.out.println("set hashes: " + hashSet.hashCode()
                + ", " + linkedSet.hashCode());
        Set<String> nullSet = new HashSet<>();
        nullSet.add("A");
        nullSet.add(null);
        System.out.println("set with null hash: " + nullSet.hashCode());

        Map<String, Integer> hashMap = new HashMap<>();
        hashMap.put("A", 1);
        hashMap.put("B", 2);
        Map<String, Integer> linkedMap = new LinkedHashMap<>();
        linkedMap.put("B", 2);
        linkedMap.put("A", 1);
        System.out.println("map equals: " + hashMap.equals(linkedMap));
        System.out.println("map hashes: " + hashMap.hashCode()
                + ", " + linkedMap.hashCode());
        System.out.println("map entry A hash: "
                + ("A".hashCode() ^ Integer.hashCode(1)));
        System.out.println("map entry B hash: "
                + ("B".hashCode() ^ Integer.hashCode(2)));
        Map<String, String> nullMap = new HashMap<>();
        nullMap.put("A", null);
        nullMap.put(null, "B");
        System.out.println("map with null hash: " + nullMap.hashCode());

        System.out.println("empty hashes: " + List.of().hashCode()
                + ", " + Set.of().hashCode()
                + ", " + Map.of().hashCode());
    }
}
```

Run with JDK 17+:

```bash
javac --release 17 CollectionHashContractDemo.java
java CollectionHashContractDemo
```

**Verified output:**

```text
list equals: true
list hashes: 3042, 3042
reversed list hash: 3072
list with null hash: 2976
set equals: true
set hashes: 131, 131
set with null hash: 65
map equals: true
map hashes: 128, 128
map entry A hash: 64
map entry B hash: 64
map with null hash: 131
empty hashes: 1, 0, 0
```

Analysis:

1. **`List`:** `ArrayList` and `LinkedList` containing the same `["A","B"]` are equal; both have hash code `3042`. Reversing the order for this concrete example produces hash code `3072`, matching the position-dependent formula. `Arrays.asList("A", null)` illustrates the rule that a `null` element contributes `0`.
2. **`Set`:** `HashSet` and `LinkedHashSet` are equal despite different insertion orders; both have hash sum `65+66=131`. The set with `null` uses element hash `0`; `HashSet` permits `null`.
3. **`Map`:** `HashMap` and `LinkedHashMap` have the same two mappings so they are equal, with hash `128`. Each entry in the sample data has XOR equal to `64`, totaling `128`. The `null` case uses `HashMap` because `HashMap` permits `null` keys/values.
4. **Empty:** the `List` formula initializes to `1`, whereas `Set` and `Map` take an empty sum of `0`. Hence the three hash codes of empty collections are `1`, `0`, and `0`, respectively.

**Factory API note:** `List.of(...)`, `Set.of(...)`, and `Map.of(...)` **do not accept `null` elements, keys, or values**. The example uses `Arrays.asList`, `HashSet`, and `HashMap` for the `null` cases; do not replace those lines with `List.of(null)` or `Map.of("A", null)`, as that will throw a `NullPointerException`.

## 7. Quick Comparison of the Formulas

| Type | Main `equals` Condition | `hashCode` Formula | Order-Sensitive? | Hash When Empty |
| --- | --- | --- | --- | ---: |
| `List` | Same size, corresponding elements at matching positions are equal | Start at `1`; for each element: `h = 31*h + elementHash` | Yes, by list order | `1` |
| `Set` | Same logical set of elements, position ignored | Sum of `elementHash` of each element | No | `0` |
| `Map` | Same logical key → value mappings | Sum of `(keyHash ^ valueHash)` of each entry | No | `0` |

In the table, `elementHash`, `keyHash`, or `valueHash` is `0` when the corresponding component is `null` (and the collection type permits `null`).

Do not confuse **order participating in hashing** with **iteration order**: a `LinkedHashSet` has a specific iteration order, yet its hash code still follows the order-insensitive `Set` formula. Similarly, a `LinkedHashMap` can iterate in insertion order, yet `Map.hashCode` does not depend on entry order.

Additionally, a `List` does not have to equal a `Set` just because they contain the same element names. The two interfaces define equality **within the same logical structure type**; do not mix formulas to compare across different types.

## 8. Relationship Between `Map.hashCode()` and `entrySet()`

By the two contracts:

```text
Map.hashCode()
  = sum of hashCode of the Map.Entry instances in entrySet()
  = entrySet().hashCode()
```

This holds for any compliant `Map` implementation, because `entrySet()` is a `Set<Map.Entry<K,V>>` and `Set.hashCode` is the sum of element hash codes. Note that equivalence **of hash codes** here does not mean a `Map` equals a `Set` under `equals`.

Distinguish the three views on a map:

- `keySet()` is a `Set<K>`: hashed based on **the keys**, excluding value hash codes.
- `values()` is a `Collection<V>`: the `Collection` interface does not mandate a universal `hashCode` formula like `List` or `Set`; do not assume it equals the sum of value hash codes.
- `entrySet()` is a `Set<Map.Entry<K,V>>`: hashed based on **key–value mappings**, so its sum is the map's hash code.

Choose the right view when working with keys, values, or full mappings; do not derive the map's hash from `keySet().hashCode()`.

## 9. Common Mistakes When Implementing or Using

### 9.1. Using the Same Hash Formula for All Types

Using summation for `List` ignores the role of position and fails the algorithm required by the `List` interface. Using multiply-by-`31` in iteration order for `Set` risks generating different hash codes for two equal sets. For `Map`, hashing only keys omits values and violates the `Map.hashCode` formula.

Do not check only the general rule "equal ⇒ same hash"; when implementing a specific interface, follow **the exact formula that interface specifies**.

### 9.2. Thinking Equal Hash Codes Mean Equal Collections

Collisions happen in all three types. For example, `Map.Entry("A", 1)` and `Map.Entry("B", 2)` in this lesson share the same hash code `64`, yet are not the same mapping. Never use `hashCode` instead of `equals` to decide equality.

In fact, matching `Set` or `Map` hash sums can occur quite easily across different element configurations. A hash code is a hint for lookup, **not proof of content equivalence**.

### 9.3. Depending on the Order of `HashSet` or `HashMap`

Do not incorporate the iterator order of `HashSet`/`HashMap` into custom hash calculations. The `Set`/`Map` contracts are order-independent. If business logic requires order, use an appropriate collection with ordering guarantees; do not write `equals/hashCode` based on the bucket order of the current implementation.

### 9.4. Mutating Elements or Keys When a Collection Serves as a Key

Suppose a `List<String>` is used as a key in a `HashMap`. If the list's contents change, `List.hashCode` may change. The outer hash table does not automatically relocate the stored entry under the new hash code; lookups can fail.

Similarly:

- In a `HashSet<Person>`, modifying a `Person` field used in `equals/hashCode` can prevent `contains` from finding the element.
- For a `Map` used as a key in another map, modifying its inner mappings can change the hash code of the Map-typed key.
- In a `Map<Key, Value>`, mutating the **key** while stored risks breaking lookup in that map itself; mutating a mutable value can change the hash code of the Map object **if that value's `hashCode` changes**, even if the map can still be queried by the old key.

Prefer immutable data when using collections or elements as hash keys; if mutation is unavoidable, consider creating a new key.

### 9.5. Confusing Java Arrays with Value Lists

`int[]` and `String[]` are Java arrays, **not `List`**. Arrays do not automatically use the `List.hashCode` formula; content-based comparison and hashing for arrays must use `Arrays.equals`/`Arrays.hashCode` (or `deepEquals`/`deepHashCode` as appropriate for nested arrays).

For instance, `List.of(new int[]{1,2})` has *an array* as its element, and that element's hash code is based on `int[].hashCode()`, not by default on the values `[1,2]`. If you want content-based equality, model the data appropriately and define consistent `equals/hashCode`.

### 9.6. Forgetting `null` Handling and Integer Overflow

The contract states that `null` contributes a hash code of `0`. However, whether **a collection allows `null`** depends on the specific class or factory. `HashSet` and `HashMap` accept `null`, whereas `Set.of` and `Map.of` do not.

When hash codes grow large, `int` addition and multiplication can overflow. That is well-defined behavior of Java integer arithmetic and part of these formulas' semantics; **do not change the formula to `long` and cast using a different scheme** if you are implementing the interface contract.

### 9.7. Optimizing Hashes While Ignoring the Contract

A "well-distributed" `hashCode` that differs from the interface formula is still wrong when implementing `List`/`Set`/`Map`. The primary goal is API correctness; bucket and performance optimization belong at the data structure layer or element type choice.

## 10. What to Check During Code Review

For a custom class implementing `List`, `Set`, or `Map`, you can run the following checks:

1. Compare instances against a standard equivalent implementation: `ArrayList` ↔ `LinkedList`, `HashSet` ↔ `LinkedHashSet`, `HashMap` ↔ `LinkedHashMap`. If `equals` is `true`, the hash codes must match.
2. Compute by hand using the interface formula: `List` starts at `1` and multiplies by `31` per position; `Set` sums each element; `Map` sums each entry's key/value XOR.
3. Test **empty** and **`null`** cases using classes that permit `null`.
4. Change order **while keeping the same logical content**: `Set`/`Map` must keep the same hash code, while `List` may change (do not require it to always change due to collisions).
5. Verify whether elements/keys/values comply with `equals/hashCode` and whether they are mutated while the collection acts as a hash key.
6. Verify `hashCode` stability when information used for `equals` does not change; do not use time sources or non-deterministic state.

When needing standard reference specifications, consult the Oracle Java 17 documentation:

- [`List.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()) — order-based multiply-by-31 formula.
- [`Set.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#hashCode()) — sum of element hash codes.
- [`Map.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#hashCode()) — sum of entry hash codes.
- [`Map.Entry.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html#hashCode()) — XOR of key and value hash codes.

## 11. Takeaways

- **`List`:** `h = 1`, then for each position `h = 31*h + elementHash`; an empty list has hash `1`.
- **`Set`:** sum of `elementHash`, order-independent; an empty set has hash `0`.
- **`Map`:** sum of `entryHash`, with `entryHash = keyHash ^ valueHash`, order-independent; an empty map has hash `0`.
- A `null` component contributes hash code `0`, though not every collection permits `null`.
- The contract guarantees **equal ⇒ same hash**, not **same hash ⇒ equal**.
- When implementing the `List`/`Set`/`Map` interfaces, follow **the interface's official formula**, while keeping elements and keys stable when they participate in hash-table lookups.