# Mutating Elements in a HashSet and the Possibility of Duplicate Values

## 1. Symptom: elements no longer preserve their equality condition

In Java, `HashSet<E>` implements the `Set<E>` interface and uses `equals(Object)` together with `hashCode()` to check whether an element is already present during operations such as `add` and `contains`. For elements whose equality-defining state is stable, `add(e)` does not add a second element equal to `e`.

However, `HashSet` stores **references to objects**. When an element is a mutable object, calling a setter or modifying a nested object can change the condition that determines equality, while the set receives no notification to rescan and rebuild its internal structure.

The `java.util.Set` specification emphasizes: **the behavior of a set is not specified if the value of an object is changed in a manner that affects `equals` comparisons while the object is an element in the set**.

Confusing consequences:

- Two elements that were distinct when added later become **equal** according to `equals`, while `size()` remains unchanged.
- `contains` or `remove` may fail to find an element that was previously added.
- A subsequent `add` operation may create the appearance of duplicate elements.
- Business operations that rely on the count of unique elements may return results inconsistent with the current meaning of the data.

This is **not a bug in `HashSet`** if the object was modified contrary to the stability condition the data structure relies upon. Rather, the caller failed to uphold an important assumption when storing elements in a set.

Conversely, modifying a field that **does not participate** in equality and hashing, such as a display note when the equality-defining ID is kept immutable, does not cause this kind of bug.

## 2. Connection to the Object contract

When overriding `equals` and `hashCode`, a class must ensure:

1. `equals` is reflexive, symmetric, and transitive; results are consistent as long as the data used for comparison does not change; for any non-`null` object, comparing with `null` returns `false`.
2. If `a.equals(b)` returns `true`, then `a.hashCode() == b.hashCode()` must hold.
3. If `a.equals(b)` returns `false`, the two hash codes **are allowed to collide**; collisions do not violate the contract.
4. During a single execution, `hashCode()` must remain stable provided the information used in equality comparisons does not change.

Contract rule (2) is written as:

`a.equals(b) ⇒ a.hashCode() == b.hashCode()`

The converse is **not required**: having the same hash does not prove two elements are equal.

An object can change its `id`, after which `equals` and `hashCode` change with `id` while remaining consistent with each other. The class itself does not necessarily violate the `Object` contract. The bug occurs when this object **is currently inside a `HashSet`**, because the data structure was built around the equality/hash relationship from before the change.

## 3. Runnable Java 17 example: two elements become duplicates

The example below compares `MutableItem` by `id`; `label` is only for display and does not participate in equality.

```java
import java.util.HashSet;
import java.util.Set;

public class HashSetMutationDemo {
    static final class MutableItem {
        private int id;
        private String label;

        MutableItem(int id, String label) {
            this.id = id;
            this.label = label;
        }

        void changeId(int newId) {
            id = newId;
        }

        void changeLabel(String newLabel) {
            label = newLabel;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof MutableItem that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        MutableItem first = new MutableItem(101, "Đầu");
        MutableItem second = new MutableItem(202, "Hai");

        Set<MutableItem> items = new HashSet<>();
        System.out.println(items.add(first));
        System.out.println(items.add(second));
        System.out.println(items.size());
        System.out.println(first.equals(second));

        // Mutate equality state while first is still in the set.
        first.changeId(202);

        System.out.println(first.equals(second));
        System.out.println(items.size());

        // Count by sequential iteration, independent of hash buckets.
        long equalNow = items.stream()
                .filter(item -> item.equals(second))
                .count();
        System.out.println(equalNow);

        // Modify only description; equality and hash do not use the label field.
        first.changeLabel("Đổi mô tả");
        System.out.println(first.equals(second));
    }
}
```

Save the file `HashSetMutationDemo.java` as UTF-8, compile, and run:

```bash
javac -encoding UTF-8 HashSetMutationDemo.java
java HashSetMutationDemo
```

Output:

```text
true
true
2
false
true
2
2
true
```

Interpretation:

- Initially `first.id = 101`, `second.id = 202`: two distinct elements. Both `add` calls return `true`; the set has 2 elements and `first.equals(second)` is `false`.
- Setting `first.id = 202` makes `first.equals(second)` flip to `true`. At this point, two objects with different references are equal under the business rule currently defined by the class.
- `items.size()` remains `2` because modifying an element's field does not automatically invoke `remove`/`add` on the set.
- `stream().filter(...)` inspects the two elements still in the set one by one and counts `2` elements that currently share the same `id`. No assumptions are made about iteration order or bucket distribution.
- Changing `label` does not affect `equals`, because `label` is not used in comparisons.

This concretely answers how **a `HashSet` can hold two elements that are currently equal**: they were added while still distinct and only became equal after mutation. No `add` call in the example was invoked with two objects that were already equal at insertion time.

## 4. Why doesn't HashSet fix itself when ID changes?

In common implementations, `HashSet` uses an internal hash structure to determine where elements are stored and looked up. When an object is inserted, its current hash code is used to organize lookup. If a field contributing to the hash changes, the new hash code may direct searches to a different region from where the object is currently held.

This mechanism helps explain why a mutated element can appear "lost" when calling `contains` or `remove`. However, **there is no fixed outcome that applies across all versions and states**, because the `Set` specification leaves behavior unspecified after an element is mutated in a way that affects equality.

Illustrative snippet (place the following inside a method that has the `MutableItem` definition above):

```java
Set<MutableItem> set = new HashSet<>();
MutableItem item = new MutableItem(1, "Một");
set.add(item);

item.changeId(2);

boolean found = set.contains(item);
boolean removed = set.remove(item);
```

You should not write down stdout asserting that `found` or `removed` is **always** `false`. The result can depend on hash values, collisions, and implementation details. The lesson to learn is: **after a mutation affecting equality, there is no longer a basis to trust lookup and removal to behave as they did when the key was stable**.

Similarly, if you subsequently call:

```java
// Still an illustrative snippet inside a method.
set.add(new MutableItem(2, "Hai"));
```

Depending on whether the old element is still found under the current hash, the add call may or may not detect an equal object. There is no universally guaranteed return value once the condition of keeping element objects stable has been violated.

## 5. Distinguishing mutation from hash collisions

These two phenomena are fundamentally different:

| Phenomenon | Meaning | Does it break the contract by itself? |
| --- | --- | --- |
| Two distinct objects have the same `hashCode` but `equals` returns `false` | Hash collision | **No**. `HashSet` resolves this using equality. |
| Two objects have `equals == true` but different hash codes | The two methods are inconsistent | **Yes**, violates the `Object` contract. |
| An already-added object mutates a field used in equality/hash | Changes the lookup condition of a stored element | **Unspecified** by `Set`; do not treat as a safe operation. |
| Two objects added while distinct, then one mutates to equal the other | Two references that are now equal in equality may both remain in the set | **Can happen** because the set does not re-check automatically. |

Even a class that intentionally returns a constant hash code `1` for every object can encounter the situation where two objects added while distinct later become equal. A constant hash code does not help the set detect changes in `equals`. The stability of the **entire equality relation** is the key point.

## 6. Which fields are allowed to change?

Suppose class `Product` defines "same product" by `productId`:

| Field | Purpose | Used in equality/hash? | Effect when modified inside a set |
| --- | --- | --- | --- |
| `productId` | Product identifier | Yes | Dangerous if modified |
| `displayName` | Display name | No | Does not change equality/hash in this model |
| `description` | Description | No | Does not change equality/hash in this model |
| `cachedLabel` | Computed display result | No | Cache can be refreshed without changing equality |
| `quantity` | Stock quantity | No, if identity is strictly by ID | Does not change identity; still requires controlling inventory logic |

The table above is only appropriate when the business contract truly defines equality by `productId`. For a value object `OrderLine(productId, quantity, price)`, `quantity` or `price` might be important components of equality; in that case, modifying quantity/price will alter duplicate detection.

A field declared `final` does not necessarily guarantee deep immutability of the object. For example, `final List<String> tags` only prevents reassigning the list reference; it **does not prevent modifying elements inside the list**. If list contents participate in `equals`/`hashCode`, the object's hash can still change after insertion into a set.

Likewise, annotations, the `transient` keyword, or whether a field has a setter do not by themselves decide whether a field belongs to equality. You must base that on the actual `equals`/`hashCode` logic and the semantics of the model.

## 7. The safest approach: use immutable keys

For data representing a set's key, prefer immutable types. In Java 17, a `record` with primitive components is a concise, easy-to-understand choice:

```java
import java.util.HashSet;
import java.util.Set;

public class ImmutableKeyDemo {
    record ItemKey(int id) {}

    public static void main(String[] args) {
        Set<ItemKey> ids = new HashSet<>();
        System.out.println(ids.add(new ItemKey(101)));
        System.out.println(ids.add(new ItemKey(101)));
        System.out.println(ids.size());
        System.out.println(ids.contains(new ItemKey(101)));
    }
}
```

Save `ImmutableKeyDemo.java` and run:

```bash
javac ImmutableKeyDemo.java
java ImmutableKeyDemo
```

Output:

```text
true
false
1
true
```

Because the `id` component is an `int` and a record does not allow replacing components after creation, using `ItemKey(101)` as an element cannot be turned into `ItemKey(202)` through a setter. The record's `equals`/`hashCode` methods are based on its components, so the second `add` is recognized as an already existing value.

If you need to "change the key" from 101 to 202, express it as a collection-level operation:

```java
// Illustrative snippet inside a method that has Set<ItemKey> ids.
boolean removed = ids.remove(new ItemKey(101));
if (removed) {
    boolean added = ids.add(new ItemKey(202));
    if (!added) {
        // Handle conflict: key 202 already exists.
    }
}
```

**Business conflicts must be handled:** if the new key already exists, you must decide whether to reject, merge data, replace, or restore the old key. The two statements `remove` and `add` are not automatically an atomic transaction in a multithreaded program.

Another design style can be applied: store `Set<Id>` instead of `Set<MutableEntity>` and maintain a separate entity metadata table. This keeps keys in the set stable while mutable metadata has its own lifecycle.

## 8. If you are forced to modify an object currently in a set

An approach that is only viable when you control the entire lifecycle is:

1. **Remove the element from the set while the equality/hash fields are still in their old state**.
2. Modify the state after the element has been removed successfully.
3. Re-add it with the new state.
4. Check the result of `add` and handle it if another element equal to the new key already exists.

Mental example:

```java
// Only safe if removal happens BEFORE modifying the key.
if (set.remove(item)) {
    item.changeId(2);
    boolean added = set.add(item);
    // If added == false: there must be a policy for the duplicate case.
}
```

This snippet does not by itself solve concurrent operations from multiple threads; the entire workflow must be synchronized or protected by a transactional mechanism as required by the system. If adding fails and requires rollback, information about the old state must be retained for a controlled recovery.

Do **not** favor a technique of "mutate first, then call `remove`": once the hash has changed, `remove` may fail to locate the old element. If a bug has already occurred, the recovery workflow differs from a normal change.

## 9. Recovering a HashSet whose elements were mutated

If data is already in a state that no longer satisfies uniqueness under current equality:

1. Prevent or coordinate concurrent mutating operations during remediation.
2. Iterate over the actual elements and collect the information to keep; do not rely solely on `contains` to conclude whether an element is present or absent.
3. Identify pairs/groups of elements that are now equal and how to resolve conflicts: which object to keep, how to merge data, and whether a business error needs to be reported.
4. Build a new structure using immutable keys or value objects after resolving duplicates.
5. Replace the reference to the old structure in a controlled process; add safeguards to prevent mutating keys again.

You can construct `new HashSet<>(oldSet)`, but it will drop elements considered duplicates under current equality. If those elements hold different descriptive information or data, dropping them can cause meaningful data loss. Therefore, **rebuild the collection after establishing a duplicate-resolution policy**, rather than blindly treating the copy constructor as a universal fix.

Do not rely on temporarily reverting the ID to its old value to `remove` and then changing it back as a general solution. You may not know the old value; conflicts that have already arisen may also be hard to restore.

## 10. Does an unmodifiable set prevent the problem?

Not automatically.

`Collections.unmodifiableSet(source)` returns a view that disallows adding/removing through that view itself. If other code still holds a reference to a mutable element or to the source set, the data and elements can still change.

`Set.copyOf(source)` creates a set that disallows structural modification through its API, yet it **does not deep copy** every element. A `MutableItem` placed inside such a set is still the same mutable object if a reference is held elsewhere. Changing equality fields can still break assumptions about stable elements.

Distinguish:

- **Unmodifiable collection:** callers cannot modify the collection's structure through the returned interface.
- **Immutable element:** the data defining an element's equality/hash does not change.
- **Stable set semantics:** requires elements to maintain proper equality/hash conditions throughout their time in the set.

A record with a mutable `List` component does not automatically become deeply immutable either. Appropriate defensive copying such as `List.copyOf` in the constructor can be used for components that need to stay stable.

## 11. Iterators, fail-fast, and multithreading

Modifying a field of an object referenced inside a set is normally not a **structural modification of the collection**. Therefore, you cannot count on `ConcurrentModificationException` to detect every case of changing `id` or `hashCode`. An iterator's fail-fast mechanism is also best-effort anyway.

If multiple threads concurrently modify, look up, or iterate over mutable objects, synchronization design and memory visibility guarantees are also required. A concurrent collection can protect its own structural operations, yet it **does not automatically make elements' equality-defining data stable**.

An ORM entity whose ID is assigned after saving also requires careful thought. If `equals`/`hashCode` relies on an ID changing from `null` to a real value after the object has already been placed in a set, that lifecycle change can affect the exact assumptions being studied here. Do not mechanically apply a "use ID" rule while ignoring when the ID stabilizes and ORM semantics.

## 12. Checklist before choosing a class as a HashSet element

- **Equality definition:** when are two elements equal according to the business domain?
- **Hash compatibility:** does every equal pair have the same `hashCode`?
- **State stability:** can fields used directly or indirectly in equality/hash change?
- **Nested references:** can lists, arrays, or child objects inside the key change contents?
- **Lifecycle:** is there any setter or automatic event that modifies the ID while the object is still in the set?
- **Change strategy:** if a key must change, is there a workflow to remove first, mutate second, re-add, and handle conflicts?
- **Test regime:** have you tested the scenario where two distinct elements become equal, without relying on bucket order or specific `contains` values?

## 13. Self-practice questions

**Question 1.** Two elements are added with IDs 1 and 2 respectively. Afterward, the first element's ID is changed to 2. Does the set automatically shrink `size()` to 1?

**Answer:** There is no mandatory mechanism to re-check equality after an element's field is modified. In the Java 17 example we ran, the set kept 2 references even though the two objects became equal according to `equals`.

**Question 2.** Two objects have the same hash code, yet `equals` returns `false`. Can `HashSet` keep both?

**Answer:** Yes. Hash collisions are permitted; in a valid state, equality comparison identifies the two elements as distinct.

**Question 3.** A class compares by `immutableId` while allowing `displayName` to be modified. Does changing the name while the object is in a set cause the bug discussed here?

**Answer:** No, provided the name does not participate directly or indirectly in equality/hash. Business and concurrency concerns must still be handled separately.

**Question 4.** If `hashCode` always returns `1`, can elements still become duplicates after mutation?

**Answer:** Yes. A constant hash does not make the set re-evaluate equality automatically. Two elements can switch from unequal to equal after a field used in `equals` changes.

**Question 5.** Why shouldn't you write a test requiring `set.contains(mutatedItem)` to always be `false`?

**Answer:** Because `Set` does not specify behavior when an element is modified in a way that affects equality while belonging to the set. Different states and implementations may yield different results. You should test **preventing key mutation**, rather than treating a specific JVM's side effect as a contract.

## 14. Takeaways

1. `HashSet` determines duplicates via `equals` and `hashCode` when operating on elements.
2. **Do not modify data participating in equality/hash while the element is in the set**. The `Set` specification provides no guarantees for this situation.
3. Two objects distinct when added can **become equal** after mutation; the set can still hold two references, as shown in the concrete example.
4. `contains`, `remove`, or `add` after mutation is no longer reliable proof of uniqueness.
5. Prefer immutable keys; if a key must change, manage remove/modify/add along with a conflict resolution policy.
6. An unmodifiable set does not make mutable elements immutable; `final` does not automatically guarantee deep immutability.

Reference documentation: [`Set` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html), [`Object.equals/hashCode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html), and [`Collections.unmodifiableSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)).