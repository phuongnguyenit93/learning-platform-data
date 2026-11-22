# Map.equals() Compares the Same Key–Value Mappings

## 1. When Are Two Maps Considered Equal?

In Java, `Map<K, V>` represents a collection of **key–value mappings**. Two `Map` instances are considered equal when they contain **the same key–value mappings**, even if they were created from different implementation classes or populated in different orders.

The `Map.equals(Object)` contract can be stated by these rules:

```text
m1.equals(m2) is true if:
  1. m2 is also a Map;
  2. m1 and m2 have the same number of mappings;
  3. for every key in m1, m2 contains an equivalent key
     and the value associated with that key is also equivalent.
```

According to the `Map` specification, the formal definition relates to the set of entries: two maps are equal if their `entrySet()` views are equal. An **entry** is a key–value pair.

For example, two maps both containing `"A" -> 10` and `"B" -> 20` are equal. If one map changes `"B" -> 21`, they are no longer equal. If the value 20 is present but associated with a different key, they are also not equal.

**Key point:** `Map.equals()` compares **mapping contents**, not whether two references point to the same object, not just the list of keys, and not just the list of values.

## 2. Distinguishing Three Commonly Confused Cases

| Case | `Map.equals()` | Explanation |
| --- | --- | --- |
| Same keys and same corresponding values, different insertion order | `true` | Insertion order is not part of `Map` equality criteria |
| Same set of keys but one value differs | `false` | A key → value mapping differs |
| Same set of values but values are bound to different keys | `false` | The mapping relationships differ |
| Same mapping pairs, but `HashMap` and `LinkedHashMap` | `true` | Different implementations do not change equality, provided they obey the `Map` contract |
| One map has an extra entry | `false` | Number of mappings differs |
| Two variables referencing the same map | `true` | An object is always equal to itself if the `equals` contract is followed |

Ordered collections such as `LinkedHashMap` can preserve insertion order when iterating, and `TreeMap` can iterate in key order. However, **iteration order is not a direct component of the `Map.equals()` contract**. Do not use `map.toString()` or entry iteration output as the criterion for map equality.

## 3. How `Map.equals()` Coordinates with Key and Value `equals()`

A helpful way to view it: a mapping `(key, value)` is considered equivalent to `(otherKey, otherValue)` when:

```java
Objects.equals(key, otherKey)
        && Objects.equals(value, otherValue)
```

This is an **illustrative expression snippet**, not a standalone program; it requires `import java.util.Objects;`. `Objects.equals(a, b)` handles `null`: if both are `null`, they are equal; if only one object is `null`, the result is `false`; otherwise, it uses `a.equals(b)`.

When keys or values are custom types you define:

- Two key objects that are **different instances** can still represent the same logical key if `equals(Object)` determines they are equal.
- Two value objects that are **different instances** can still be equivalent if the value type's `equals(Object)` returns `true`.
- If two maps share the same keys but their values are not equal, the two maps as a whole are not equal.
- The `equals(Object)` and `hashCode()` methods of types used as keys must obey the Java contract; otherwise, hash-based maps may behave unexpectedly.

Note: two pairs with the **same value but different keys** do not become the same mapping. A map represents the relationship "which value is bound to this key", not an independent set of values.

## 4. Java 17+ Example: Same Content Despite Different Implementations and Order

Create the file `MapEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class MapEqualityDemo {
    public static void main(String[] args) {
        Map<String, Integer> first = new HashMap<>();
        first.put("A", 10);
        first.put("B", 20);

        Map<String, Integer> second = new LinkedHashMap<>();
        second.put("B", 20);
        second.put("A", 10);

        Map<String, Integer> third = new TreeMap<>();
        third.put("B", 20);
        third.put("A", 10);

        System.out.println(first.equals(second));
        System.out.println(second.equals(first));
        System.out.println(first.equals(third));
        System.out.println(first.hashCode() == second.hashCode());

        second.put("B", 21);
        System.out.println(first.equals(second));

        second.put("B", 20);
        second.remove("A");
        System.out.println(first.equals(second));

        Map<String, Integer> withNull = new HashMap<>();
        withNull.put("missing", null);
        System.out.println(withNull.get("missing") == null);
        System.out.println(withNull.containsKey("missing"));
        System.out.println(withNull.equals(Map.of()));
    }
}
```

Compile and run:

```bash
javac MapEqualityDemo.java
java MapEqualityDemo
```

Output:

```text
true
true
true
true
false
false
true
true
false
```

Explanation:

1. `first`, `second`, and `third` all have `A -> 10`, `B -> 20`. Despite different implementation classes and insertion orders, `equals` returns `true` between them.
2. Two equal maps must have the same `hashCode()`. Therefore, the hash code comparison returns `true`. The converse is not true: having the same hash does not prove two maps are equal.
3. Changing `B` from 20 to 21 alters one entry, so `first.equals(second)` becomes `false`.
4. Restoring `B`'s value and removing entry `A` leaves the map with one entry; the sizes differ, so it remains `false`.
5. `withNull.get("missing") == null` is `true`, yet `containsKey("missing")` is also `true`: the map has the entry `"missing" -> null`. The empty map `Map.of()` does not equal this map containing one entry.

The example uses `HashMap`, `LinkedHashMap`, and `TreeMap` with `String` keys in natural order. A `TreeMap` using a comparator that is **inconsistent with key `equals`** can break equality expectations when comparing across implementations; see the caveats section below.

## 5. When Both Keys and Values Are Custom Objects

A Java record can represent a simple immutable value type and automatically provide `equals(Object)` and `hashCode()` based on its record components.

Create the file `MapObjectValueDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class MapObjectValueDemo {
    record ProductId(String code) {}
    record PriceTag(int amount, String currency) {}

    public static void main(String[] args) {
        ProductId keyOne = new ProductId("P-001");
        ProductId keyTwo = new ProductId("P-001");

        PriceTag priceOne = new PriceTag(120, "VND");
        PriceTag priceTwo = new PriceTag(120, "VND");

        System.out.println(keyOne == keyTwo);
        System.out.println(keyOne.equals(keyTwo));
        System.out.println(priceOne.equals(priceTwo));

        Map<ProductId, PriceTag> left = new HashMap<>();
        left.put(keyOne, priceOne);

        Map<ProductId, PriceTag> right = new HashMap<>();
        right.put(keyTwo, priceTwo);

        System.out.println(left.equals(right));

        right.put(keyTwo, new PriceTag(130, "VND"));
        System.out.println(left.equals(right));

        right.clear();
        right.put(new ProductId("P-002"), priceOne);
        System.out.println(left.equals(right));
    }
}
```

Run on JDK 17+:

```bash
javac MapObjectValueDemo.java
java MapObjectValueDemo
```

Stdout:

```text
false
true
true
true
false
false
```

`keyOne` and `keyTwo` are two distinct object references (first line `false`) with the same `code`, so they are equal by value (`true`). `priceOne` and `priceTwo` behave the same way. Because both maps contain the same logical mapping `P-001 -> (120, VND)`, `left.equals(right)` is `true`.

Changing the corresponding value to 130 makes the two maps unequal. Next, even though the value `priceOne` is used again, replacing the key with `P-002` still makes the two maps unequal. This clearly shows that equality requires **both the key and the value associated with that key**.

A record does not automatically make mutable components stored inside it deeply immutable. For example, `record DataKey(List<String> parts) {}` still holds a reference to a mutable list. When using a record as a key, ensure that state participating in `equals/hashCode` remains stable while stored in the map.

## 6. `Map.hashCode()` Is Also Based on Entries

According to the `Map.hashCode()` contract, the hash code of a map equals the **sum of the hash codes of the entries** in `entrySet()`. The hash code of a `Map.Entry` by contract is:

```text
entryHash = hashCode(key) XOR hashCode(value)
            (null is treated as 0)

mapHash = sum of entryHash for all entries
```

This explains why two equal maps must have the same hash **regardless of entry iteration order**: addition is order-independent. Nevertheless, two unequal maps can still have matching hashes due to collisions; never use `map1.hashCode() == map2.hashCode()` as a substitute for `map1.equals(map2)`.

You can verify this contract on a simple map:

```java
Map<String, Integer> m = Map.of("A", 10, "B", 20);
int sumOfEntries = m.entrySet().stream()
        .mapToInt(Map.Entry::hashCode)
        .sum();
boolean sameHash = m.hashCode() == sumOfEntries;
```

This is an **illustrative code snippet**, requiring `import java.util.Map;`. `sameHash` must be `true` for an implementation that complies with the `Map` contract.

A map's hash code is not a unique ID, digital signature, or durable value to persist in another system. If mutable keys or values change fields participating in equality, the map's hash code can also change.

## 7. Null, Empty Maps, and the Difference Between "Missing Key" and "Key Mapped to Null"

The following three maps are not equal:

```text
{}                   (no entries)
{"x" -> null}        (one entry with a null value)
{null -> "x"}        (one entry with a null key)
```

`HashMap` allows at most one `null` key and can have multiple distinct keys carrying a `null` value. `Map.of(...)` and `Map.ofEntries(...)` do not allow `null` keys or values; many other implementations also have their own policies.

- `get(key) == null` **does not distinguish** between a non-existent key and a key mapped to `null`.
- `containsKey(key)` answers whether the key exists.
- Two maps are equal only when both **key presence** and the **associated value** match. An entry `"x" -> null` must be matched against an entry with the same key that also has the value `null`.

When handling `null`, check the specific implementation's contract before calling `put(null, value)` or `put(key, null)`. Do not assume every `Map` supports null just because `HashMap` does.

## 8. How `Map` Differs from `List` and `Set` in Equality Conditions

Each collection has its own equality contract:

| Type | Primary Equality Condition | Does Order Matter? |
| --- | --- | --- |
| `List` | Same length, equivalent elements at matching positions | **Yes** |
| `Set` | Same logical elements | Normally **no** |
| `Map` | Same key–value mappings | **No** under the Map contract |

For example, `List.of("A", "B")` does not equal `List.of("B", "A")`. However, a map containing `A -> 1` then `B -> 2` still equals a map built with `B -> 2` then `A -> 1`.

At the same time, a map is **not merely a set of keys**: two maps with the same `keySet` but different values are not equal. Nor is it merely a collection of values: swapping two values between two keys changes the mappings.

## 9. Exceptions and Situations Requiring Care

### Comparator Inconsistent with `equals`

`TreeMap` uses a comparator or natural ordering to determine when two keys occupy the same position in the tree structure. If the comparator returns 0 for two keys while `equals` returns `false`, the map may treat them as the same key during `put/get`, whereas maps using standard equality distinguish them.

For instance, a case-insensitive comparator may treat `"A"` and `"a"` as equal in ordering, while `String.equals` distinguishes them. The `TreeMap` Javadoc requires that the ordering be **consistent with equals** if full compliance with the `Map` contract is desired when comparing across implementations.

A `TreeMap<BigDecimal, ...>` using natural ordering requires the same consideration, because `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0`, whereas `equals` returns `false`.

### `IdentityHashMap` Does Not Use Standard Equality

`IdentityHashMap` intentionally considers two keys equal only when they share the **same reference (`==`)** rather than `equals`. This is a specialized implementation whose Java documentation explicitly states that it **violates `Map`'s general contract for object equality**. Therefore, it should not be used as a drop-in replacement for `HashMap` if callers rely on value-based `Map.equals()`.

### Mutable Values and Mutable Keys

Two maps may be equal now and later become unequal if an internal value object is mutated in a way that changes `equals`. If a key object is mutated in a way that changes `hashCode` or `equals` after being added to a `HashMap`, lookups and `Map.equals()` can also become unreliable relative to the original intent.

In particular, avoid **putting a map itself as its own key or value in a self-referential structure** and expecting `equals/hashCode/toString` to handle it safely; some operations may no longer be well-defined on such recursive structures.

## 10. How to Apply This in Code and Testing

1. **Define key equality:** if two keys are considered the same logical entity, implement compatible `equals(Object)` and `hashCode()`. Consider using records or immutable types for keys.
2. **Define value equality:** verify whether the value's `equals` accurately reflects business conditions. For example, `BigDecimal.equals` distinguishes scale; `List.equals` distinguishes order.
3. **Test different insertion orders:** create a `HashMap` and a `LinkedHashMap` with the same mappings in reverse order; they must still be equal.
4. **Test single-component changes:** change the value of a key or swap a key, and verify `Map.equals` becomes `false`.
5. **Test null and missing keys:** distinguish a map with `"x" -> null` from an empty map; use `containsKey` when needed.
6. **Check hashes:** two equal maps must have the same `hashCode`; do not use matching hashes to infer map equality.
7. **Check collections with custom comparators:** avoid assuming a comparator returning 0 means key `equals` also returns `true`.
8. **Do not compare via display strings:** instead of comparing `map.toString()`, use `map.equals(other)` when the goal is identical mapping content.
9. **Keep state stable during comparison:** do not mutate the map or key/value objects concurrently during equality operations; standard collections are not thread-safe by default.

**Self-check:**

- Are two maps with `A -> 1`, `B -> 2` inserted in opposite orders equal? **Yes.**
- Are two maps with the same `keySet()`, where one has `B -> 3` instead of `B -> 2`, equal? **No.**
- Are two maps with the same list of values mapped to different keys equal? **No.**
- Does a map containing the entry `A -> null` equal an empty map? **No.**
- Must two equal maps have equal `hashCode()`? **Yes.**

**Takeaway:** `Map.equals(Object)` expresses **equivalence across all key–value mappings**. Having the same number of entries, the same logical keys, and equal corresponding values makes two maps equal; insertion order, iteration order, and typical implementation classes do not determine the result.