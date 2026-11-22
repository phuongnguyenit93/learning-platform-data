# Consequences When a Class Breaks a Contract in the Java Standard Library

When placing objects into `HashMap`, `HashSet`, `TreeMap`, `TreeSet`, or sorting algorithms, the standard library **relies on the contracts** that the class publishes via `equals`, `hashCode`, `Comparable`, and `Comparator`. If the class is implemented incorrectly, library code may still run as designed, yet the observed outcome will fail expectations: elements cannot be found again, logically duplicate elements are stored, data is lost on insertion, ordering is wrong, or sorting algorithms throw errors.

The key is to distinguish three situations: **actually violating a contract**, **mutating key state after storage**, and **two APIs using different equivalence rules that are both valid**.

## 1. Contracts That the Library Relies On

| Component | Essential rule | Where affected |
| --- | --- | --- |
| `Object.equals(Object)` | Reflexive, symmetric, transitive, consistent when comparison data does not change; `x.equals(null)` is `false` | `List.contains`, `remove`, `HashSet`, `Map` keys, duplicate handling |
| `Object.hashCode()` | If `a.equals(b)` then `a.hashCode() == b.hashCode()`; hash stable when data used to determine equality does not change | `HashMap`, `HashSet`, `LinkedHashMap`, `LinkedHashSet` |
| `Comparable.compareTo` / `Comparator.compare` | Comparison result has consistent sign, is antisymmetric in sign, transitive, and consistent when returning `0` | `TreeSet`, `TreeMap`, `Arrays.sort`, `List.sort`, `Collections.sort` |
| `Map` key rule | Do not mutate data affecting `equals`/`hashCode` of a key while it is acting as a key | Lookup, removal, updating entries in the map |

### Regarding `equals` and `hashCode`

- `x.equals(x)` must be `true` (reflexive).
- `x.equals(y)` must yield the same result as `y.equals(x)` (symmetric).
- If both `x.equals(y)` and `y.equals(z)` are true, then `x.equals(z)` must be true (transitive).
- When the data used for comparison does not change, repeated calls to `equals` must be consistent; `equals(null)` must return `false`.
- **The mandatory direction** is that `equals == true` implies **the same hash code**. The reverse direction is not required: two unequal objects may have the same hash code (hash collision).

Implementing `equals` while forgetting `hashCode`, or letting the two methods use different sets of attributes, easily breaks the mandatory implication above. `HashMap` uses the hash to select a search bucket and uses `equals` to identify equivalent keys within the matching partition; it cannot fix a contradictory comparison rule on its own.

### Regarding `Comparable`/`Comparator`

A valid ordering must be consistent enough for sorting algorithms and tree structures to operate. For instance, if comparisons state `a < b` and `b < c`, they cannot simultaneously state `a > c`. If `compare(a,b) == 0`, the comparison signs of `a` and `b` against any `c` must be consistent. Violations can cause nonsensical ordering; in some cases `List.sort`/`Arrays.sort` throws `IllegalArgumentException: Comparison method violates its general contract!`, though **not every input dataset triggers the error**.

Having `compare(a,b) == 0` while `!a.equals(b)` **does not automatically violate the `Comparator` contract**. However, for `SortedSet` and `SortedMap`, it alters the notion of "duplicate"; if full alignment with the general `Set`/`Map` contract is needed, the ordering should be consistent with `equals`, or the difference must be understood and documented.

## 2. Concrete Consequences

### 2.1. `HashSet` Can Hold Two Objects That Should Be Considered Equal

Suppose `a.equals(b) == true` yet `a.hashCode() != b.hashCode()`. The two elements may go into two different hash buckets. Then `HashSet.add(a)` followed by `add(b)` can increase the size to `2`, even though according to the class's `equals` definition, they are one logical value.

The same problem appears with `HashMap` keys: `get`, `containsKey`, `remove`, or `put` using a new equivalent object may fail to reach the stored entry. These library classes have no obligation to scan the entire table to compensate for a broken `hashCode`.

### 2.2. Mutable Keys Can Become "Unfindable" After Insertion

Even if `equals` and `hashCode` are written **correctly for the current state**, changing attributes that participate in those two methods after `map.put(key, value)` is still dangerous. The map already placed the key based on the hash at insertion time; after mutating state, lookups using the new hash may fail. The entry still exists in the map and still occupies memory, yet normal lookup APIs may fail to find it.

This is a **violation of the stable-key usage assumption**, not necessarily a violation of the `hashCode` contract: the contract allows the hash to change when data used by `equals` changes.

### 2.3. `TreeSet`/`TreeMap` Can Drop Entries From `equals`'s Perspective

`TreeSet` and `TreeMap` use comparison results (`compareTo` or `Comparator`) to find positions and decide whether two keys are equivalent: `compare(a,b) == 0` is treated as an existing key. Therefore:

- `TreeSet.add` can return `false` for an element that `equals` considers different.
- `TreeMap.put` with a key comparing as `0` can **overwrite the value of the old key** instead of adding a new entry.
- `contains`, `remove`, and sorted ranges reflect the comparison rule, so they may differ from assumptions based on `equals`.

Do not jump to the conclusion that the library lost data due to a bug: first check the exact equivalence rule that the data structure is using.

### 2.4. Bugs Can Propagate to the Business Layer

For account identifiers, task queues, caches, or deduplication filters, contract bugs can cause duplicate data not to be eliminated; cache lookups to miss; removal operations to fail to delete expected elements; size statistics to be wrong; or a key to be overwritten according to a sorting rule. Output sometimes varies with operation order, datasets, and object state, making bugs hard to reproduce if testing only a single happy-path case.

## 3. Java 17+ Example: Three Different Phenomena

The file `ContractConsequencesDemo.java` below runs standalone and intentionally contains two poorly designed or misused key classes to observe the consequences. The `BigDecimal` case at the end is a **documented difference in Java**, not a `BigDecimal` bug.

```java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ContractConsequencesDemo {
    // WRONG: equals compares id, yet hashCode depends on independent hint.
    static final class BadKey {
        final String id;
        final int hint;

        BadKey(String id, int hint) {
            this.id = id;
            this.hint = hint;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BadKey that && Objects.equals(id, that.id);
        }

        @Override
        public int hashCode() {
            return hint;
        }
    }

    // Correct for the current state, yet unsafe when used as a key and then mutating id.
    static final class MutableKey {
        String id;

        MutableKey(String id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey that && Objects.equals(id, that.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    public static void main(String[] args) {
        BadKey a = new BadKey("X", 1);
        BadKey b = new BadKey("X", 2);
        Set<BadKey> brokenSet = new HashSet<>();
        brokenSet.add(a);
        brokenSet.add(b);

        System.out.println(a.equals(b));                   // true
        System.out.println(a.hashCode() == b.hashCode());   // false
        System.out.println(brokenSet.size());               // 2

        MutableKey key = new MutableKey("A");
        Map<MutableKey, String> map = new HashMap<>();
        map.put(key, "stored");
        System.out.println(map.get(key));                   // stored
        key.id = "B";
        System.out.println(map.get(key));                   // null
        System.out.println(map.size());                     // 1

        List<BigDecimal> numbers = List.of(
                new BigDecimal("1.0"),
                new BigDecimal("1.00")
        );
        System.out.println(new HashSet<>(numbers).size());  // 2
        System.out.println(new TreeSet<>(numbers).size());  // 1
        System.out.println(numbers.get(0).equals(numbers.get(1)));   // false
        System.out.println(numbers.get(0).compareTo(numbers.get(1))); // 0
    }
}
```

Compile and run:

```bash
javac --release 17 ContractConsequencesDemo.java
java ContractConsequencesDemo
```

Standard output:

```text
true
false
2
stored
null
1
2
1
false
0
```

Group-by-group explanation:

1. Both `BadKey` instances have the same `id`, so `equals` returns `true`, yet their hash codes differ (`1` and `2`). `HashSet` stores both: the `BadKey` class broke the contract, not `HashSet`.
2. `MutableKey` initially has `id = "A"`, so the string `stored` is found. After changing it to `"B"`, the string's hash code changes; `HashMap.get(key)` does not find the old entry, even though `size()` remains `1`. The example uses strings `"A"`/`"B"` so the output is deterministic on standard Java's `HashMap`.
3. `BigDecimal("1.0")` and `BigDecimal("1.00")` differ under `equals` due to different scales, yet `compareTo` returns `0` because of the same numerical value. `HashSet` treats them as two elements; `TreeSet` treats them as one under natural ordering. This is intentional behavior, showing that choosing a data structure is also choosing an equivalence criterion.

## 4. Common Bug Patterns When Implementing Yourself

### Mistakenly Overloading `equals` Instead of Overriding It

```java
// WRONG: only creates an overload, does not override Object.equals(Object).
public boolean equals(UserId other) {
    return other != null && value.equals(other.value);
}
```

`HashSet`/`HashMap` invoke the `equals(Object)` signature. If a class only has `equals(UserId)`, they still use the method inherited from `Object` (comparing reference identity), causing two values with the same code to still be treated as different. Use `@Override` and declare `public boolean equals(Object other)` properly so the compiler catches signature mistakes.

### Ignoring Symmetry or Transitivity Under Inheritance

A superclass allowing any subclass with the same `id` to be equal, while a subclass additionally requires `region`, can produce `parent.equals(child) == true` while `child.equals(parent) == false`. Adding more objects can also break transitivity. Structures using `equals` cannot define a consistent set when the "equality" relation contradicts itself.

When designing value objects, prefer immutable values, `final` classes, or a comparison model with a clear inheritance strategy. Avoid altering `equals` in a way that makes two sides disagree.

### Comparator Using Subtraction or Mutable Data

```java
// Dangerous: a - b can overflow integers.
Comparator<Integer> bad = (a, b) -> a - b;

// Correct and avoids overflow:
Comparator<Integer> good = Integer::compare;
```

This is an illustrative snippet, not a standalone Java program. Integer subtraction can overflow, flipping the sign and making ordering inconsistent. A `Comparator` reading a mutable attribute that changes while the object sits in `TreeSet`/`TreeMap` can also cause lookups or tree ordering to no longer match current state.

### Confusing `toString` With Object Identity

`Object.toString()` serves text representation, debugging, and logging; it does not replace `equals`/`hashCode`. Two objects with the same `toString()` string are not automatically equal, and the displayed string itself is not necessarily stable or unique. Do not use a log format as a key criterion without explicitly defining semantics.

## 5. How to Design and Prevent Issues

1. **Define logical identity before writing code.** For `UserId`, perhaps only `id` participates in equality; for a business domain object, you must clearly decide whether version, status, object type, or inheritance cases are included.
2. **Implement `equals` and `hashCode` with the exact same set of attributes.** Update both when changing the equality definition. Use `Objects.equals` and `Objects.hash` when appropriate; hash codes with collisions remain semantically valid, though they may affect performance.
3. **Prefer immutable keys.** For example, `record UserId(String value) {}` in Java 17 automatically generates `equals`/`hashCode` from the `value` component. However, a record does not make referenced objects inside immutable: if a component is an array or mutable collection, you still must design it so comparison and hashing remain stable. For arrays, record-generated `equals`/`hashCode` use the array's reference semantics rather than deep element comparison.
4. **Choose sorting rules deliberately.** When using `TreeSet`/`TreeMap`, inspect the meaning of `compare == 0`. If two objects differing in business identity must coexist, the comparator needs a sufficiently distinguishing key, such as comparing a stable identifier as well. If intentionally grouping by a single value, you must accept sorted set/map semantics.
5. **Do not modify attributes affecting ordering/keys after insertion.** To update, remove using the old state first, create a new value or update while the object is not in the collection, and then reinsert; for map keys that can no longer be looked up, you may need to rebuild the structure from a trusted data source.
6. **Test the contract, not just a single `put/get` call.** Create at least three objects representing equal values, different values, superclass/subclass or different states if applicable. Test reflexivity, symmetry, transitivity, `equals(null)`, the implication from `equals` to `hashCode`, and lookup/removal using a new equivalent object. For comparators, test three elements, reversed order, and `0` cases, especially boundary numbers.

One very important test: if `a.equals(b)` returns `true`, then `a.hashCode() == b.hashCode()` is **mandatory**. Testing the reverse direction (`hashCode` equality implies `equals`) is **wrong** and should not be written.

## 6. Diagnostic Checklist When Collections Behave Strangely

| Symptom | First check | Targeted resolution |
| --- | --- | --- |
| `HashSet` keeps two elements that appear to be duplicates | Does `equals` actually override `Object.equals`? Do the two objects' hashes match when `equals` is true? | Fix the equality relation and hash function; rebuild the set after fixing |
| `HashMap.get`/`remove` fails to find an inserted key | Were fields participating in `equals`/`hashCode` mutated on the key after `put`? | Use immutable keys; restore or rebuild the map from source data |
| `TreeSet` drops elements or `TreeMap` overwrites values | Does `compareTo`/`Comparator.compare` return `0` for two keys meant to be distinct? | Design a comparator reflecting the exact identity to be stored |
| Unusual sort results or occasional `IllegalArgumentException` | Is the comparator transitive, antisymmetric in sign, and consistent when returning `0`? Is there integer overflow or mutating state? | Use safe comparisons, stable sort keys, and add triple-element tests |
| `HashSet` and `TreeSet` have different sizes | Do `equals` and natural ordering share the same equivalence definition? E.g., `BigDecimal` | Clarify business needs: compare with scale or numerical value only |

**Conclusion:** Java collections rely on contracts supplied by **the element/key class or comparator**. Breaking a contract exposes bugs in seemingly harmless operations (`contains`, `get`, `add`, `remove`, `sort`). Prevention means defining a valid equality relation, generating compatible hashes, keeping keys stable, and clearly understanding the separate equivalence criteria of ordered collections.