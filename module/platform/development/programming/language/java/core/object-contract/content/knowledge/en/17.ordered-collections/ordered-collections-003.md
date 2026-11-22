# Two Objects Where `equals()` Is True but `Comparator` Distinguishes Them

A surprising situation in Java: **two objects considered equal by `equals()`, yet `Comparator.compare(a, b)` returns a non-`0` number**. When placed into a `HashSet`, only one element may remain; when placed into a `TreeSet` using that comparator, both coexist.

This is not because `TreeSet` skips duplicate-key checks due to a bug. **`TreeSet` determines element equivalence by ordering comparison result**, whereas `HashSet` identifies elements by `equals` and `hashCode`. If the two definitions of equivalence do not agree, the two structures can yield different results. For a `SortedSet` intended to fully comply with the general `Set` contract, the ordering used to determine duplicate elements **must be consistent with `equals`**.

This lesson focuses on the easily overlooked direction: **`a.equals(b) == true` yet `comparator.compare(a, b) != 0`**, the reasons it arises, the consequences when using ordered sets/maps, and how to design to avoid business bugs.

## 1. Two different “equality” relations

In Java there are two separate questions:

- `a.equals(b)`: are the two objects considered **the same logical value** by the data type?
- `comparator.compare(a, b)`: do the two objects **come before, rank equivalent to, or come after** one another under a specific sorting rule?

`Comparator<T>.compare(a, b)` returns a negative number if `a` precedes `b`, `0` if they are equivalent in **order**, or a positive number if `a` follows `b`. Not every comparator has to use the same fields as `equals`. That can be appropriate when **only sorting a `List`**. However, when a comparator serves as the key-distinguishing rule in `TreeSet` or `TreeMap`, the discrepancy can change the meaning of “duplicate”.

An ordering relation is **consistent with `equals`** when, for two valid objects:

~~~text
comparator.compare(a, b) == 0  ⇔  a.equals(b) == true
~~~

The `⇔` symbol means **both directions must hold**: if `equals` is true then `compare` is `0`, and if `compare` is `0` then `equals` is true. Distinction table:

| `a.equals(b)` | `compare(a, b) == 0` | Interpretation |
| --- | --- | --- |
| `true` | `true` | Both relations treat the objects as equivalent. |
| `false` | `false` | Both relations distinguish the objects. |
| **`true`** | **`false`** | **Focus case:** `equals` merges them, yet the comparator splits them. |
| `false` | `true` | Opposite direction: the comparator merges two objects that `equals` treats as distinct. |

A comparator that is **inconsistent with `equals`** is not necessarily wrong in ordering. It can still be valid for sorting lists. The risk appears when that ordering is used as the basis for determining **uniqueness** in an ordered set or keys in an ordered map.

## 2. Java 17+ example: `equals` true, `compare` non-zero

Suppose `Item` has `id` and `revision`:

- Two `Item`s with **the same `id`** are considered the same logical entity by the system. Therefore, `equals` and `hashCode` inspect only `id`.
- A screen, however, wants to sort by `id`, then by `revision` to see which version comes first. This comparator inspects **both fields**.

Complete file **`ComparatorEqualsMismatchDemo.java`**, compilable and runnable on Java 17+:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorEqualsMismatchDemo {
    static final class Item {
        private final int id;
        private final int revision;

        Item(int id, int revision) {
            this.id = id;
            this.revision = revision;
        }

        int id() {
            return id;
        }

        int revision() {
            return revision;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Item that)) {
                return false;
            }
            return id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return "Item(" + id + "," + revision + ")";
        }
    }

    public static void main(String[] args) {
        Item first = new Item(7, 1);
        Item second = new Item(7, 2);
        Item query = new Item(7, 3);

        Comparator<Item> byIdThenRevision =
            Comparator.comparingInt(Item::id)
                      .thenComparingInt(Item::revision);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(byIdThenRevision.compare(first, second));
        System.out.println(byIdThenRevision.compare(second, first));

        Set<Item> hashSet = new HashSet<>();
        hashSet.add(first);
        hashSet.add(second);
        System.out.println(hashSet.size());
        System.out.println(hashSet.contains(query));

        Set<Item> treeSet = new TreeSet<>(byIdThenRevision);
        treeSet.add(first);
        treeSet.add(second);
        System.out.println(treeSet.size());
        System.out.println(treeSet);
        System.out.println(treeSet.contains(second));
        System.out.println(treeSet.contains(query));

        Comparator<Item> byIdOnly = Comparator.comparingInt(Item::id);
        Set<Item> consistentTreeSet = new TreeSet<>(byIdOnly);
        consistentTreeSet.add(first);
        consistentTreeSet.add(second);
        System.out.println(consistentTreeSet.size());
        System.out.println(consistentTreeSet.contains(query));
    }
}
~~~

Compile and run:

~~~bash
javac ComparatorEqualsMismatchDemo.java
java ComparatorEqualsMismatchDemo
~~~

Exact output:

~~~text
false
true
true
-1
1
1
true
2
[Item(7,1), Item(7,2)]
true
false
1
true
~~~

**Reading the output in three parts:**

1. `first == second` is `false`: they are two distinct objects. `first.equals(second)` is `true`: `equals` checks only `id = 7`. Because `hashCode` also uses `id`, two equal objects have the same hash, satisfying the `equals`/`hashCode` contract.
2. `byIdThenRevision.compare(first, second)` is `-1` because `1 < 2` on the `revision` field; the reverse direction is `1`. **The comparator distinguishes two objects that `equals` considers equal.**
3. `HashSet` uses `equals`/`hashCode` semantics, so after two `add` calls there is only **1 element**; `contains(query)` returns `true` because `query.id` is also `7`.
4. `TreeSet` uses `byIdThenRevision`: because `compare(first, second) != 0`, both are kept. Size becomes **2**; the set iterates in order `Item(7,1)`, then `Item(7,2)`.
5. `treeSet.contains(second)` is `true`. Yet `treeSet.contains(query)` is **`false`** even though both `query.equals(first)` and `query.equals(second)` are `true`: according to the comparator, `Item(7,3)` is a different ordering value.
6. When replacing the comparator with **`byIdOnly`**, two `Item`s with `id = 7` compare as `0`, matching how `equals` defines equality. `TreeSet` then has only **1 element**, and searching for `query` returns `true`.

In the example `Item` is `final`, its fields are `final`, and `hashCode` is stable; therefore the difference between the two sets here **comes solely from the comparator's equivalence rule**, not from mutating objects after insertion or a hashing bug.

## 3. Why can `TreeSet` hold two elements where `equals() == true`?

The `Set` interface describes a collection with no two duplicate elements according to `equals`. However, `SortedSet` and `TreeSet` must use **sort order** to find the proper position when inserting, searching, or removing.

For `TreeSet`:

1. If passed a `Comparator`, the set uses `comparator.compare(x, y)` to sort and distinguish elements.
2. If no `Comparator` is given, the set uses natural ordering from the element's `Comparable.compareTo`.
3. When the comparison result is `0`, the set treats the two objects as **equivalent in order**, so adding the subsequent object does not increase the size.
4. When the comparison result is non-`0`, the set can store two elements at two distinct positions, **even when `equals` returns `true`**.

This is why `SortedSet` documentation requires **the ordering to be consistent with `equals` if the structure is to obey the general `Set` contract properly**. The behavior of a sorted set with an inconsistent comparator is still well-defined by the comparator, but expectations from a standard `Set` are violated.

### Illustrating the difference in “unit of uniqueness”

| Structure | Two items `Item(7,1)` and `Item(7,2)` |
| --- | --- |
| `HashSet<Item>` | Treats as duplicate because `equals` is by `id`; keeps one element. |
| `TreeSet<Item>` with comparator `id` then `revision` | Treats as distinct because comparison result is non-`0`; keeps two elements. |
| `TreeSet<Item>` with comparator only by `id` | Treats as duplicate because comparison result is `0`; keeps one element. |

Do not explain this phenomenon with “`TreeSet` uses `hashCode` differently from `HashSet`”. `TreeSet` is an order-based structure and **does not use `hashCode` to determine equivalent elements**. A completely correct `hashCode` still cannot fix a comparator that mismatches set semantics.

## 4. What happens with `TreeMap` and keys that are equal by `equals`?

The same situation occurs in `TreeMap`: a `Comparator` inconsistent with `equals` can cause two logically equal keys to become **two entries**.

File **`TreeMapComparatorDemo.java`**, independently compilable on Java 17+:

~~~java
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

public class TreeMapComparatorDemo {
    record Key(int id, int revision) {
        @Override
        public boolean equals(Object obj) {
            return obj instanceof Key that && id == that.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Key first = new Key(7, 1);
        Key second = new Key(7, 2);

        Comparator<Key> byBoth =
            Comparator.comparingInt(Key::id)
                      .thenComparingInt(Key::revision);

        Map<Key, String> hash = new HashMap<>();
        System.out.println(hash.put(first, "old"));
        System.out.println(hash.put(second, "new"));
        System.out.println(hash.size());
        System.out.println(hash.get(first));

        Map<Key, String> tree = new TreeMap<>(byBoth);
        System.out.println(tree.put(first, "old"));
        System.out.println(tree.put(second, "new"));
        System.out.println(tree.size());
        System.out.println(tree.get(first));
        System.out.println(tree.get(second));
        System.out.println(tree.containsKey(new Key(7, 3)));
    }
}
~~~

Run:

~~~bash
javac TreeMapComparatorDemo.java
java TreeMapComparatorDemo
~~~

Standard output:

~~~text
null
old
1
new
null
null
2
old
new
false
~~~

In `HashMap`, `second` shares the logical key with `first`, so `put(second, "new")` replaces the value `"old"`, and the size stays `1`.

In `TreeMap` using comparator `id` then `revision`, the two keys differ under the ordering relation, so `put(second, "new")` adds a new entry, making the size `2`. Querying with `new Key(7,3)` does not find a key at the same ordering position, even though that key `equals` both stored keys.

This can affect update-by-ID, deduplication, lookup, and removal features: **choosing the comparator rule for `TreeMap` is a decision about key identity in that structure**, not merely a display choice.

In the example, the `Key` record **overrode both `equals` and `hashCode`** to use `id` as the logical key; this is an intentional difference from the default record-generated `equals` that checks both `id` and `revision`.

## 5. When is a comparator inconsistent with `equals` still useful?

There is no rule that **every** comparator used for sorting must be consistent with `equals`. A comparator can sort by multiple criteria for better presentation, provided it satisfies the **ordering** contract such as sign symmetry, transitivity, and consistency of `compare == 0` groups.

For instance, if you want to display all revisions of objects having the same `id`, you can sort **a list** with a comparator checking `id` and `revision`:

~~~java
List<Item> items = new ArrayList<>();
items.add(new Item(7, 2));
items.add(new Item(7, 1));

items.sort(
    Comparator.comparingInt(Item::id)
              .thenComparingInt(Item::revision)
);
System.out.println(items);
~~~

The snippet above uses the `Item` class defined in section 2 and needs imports `java.util.List`, `java.util.ArrayList`, `java.util.Comparator`. When placed in a `main` method alongside `Item`, the output is:

~~~text
[Item(7,1), Item(7,2)]
~~~

A list **does not remove elements that are duplicates by `equals`**, so keeping both revisions is normal behavior and the multi-criteria comparator helps display as intended. The problem arises when **this very same comparator** is passed into `TreeSet`/`TreeMap` while the program expects the set or map to enforce duplication by `id`.

### “Object equality” vs “presentation distinction”

If `id` identifies the entity while `revision` is a version attribute, it can be reasonable to:

- Use `equals` by `id` for the entity object.
- Use a `Comparator` by `id` then `revision` to **order display representations in a list**.
- Use `TreeSet`/`TreeMap` **by `id`** if you need to store exactly one element/key per logical entity.
- Or design a separate key type `(id, revision)` if the real goal is to retain **each version as a distinct key**.

Thus, you must separate “in what order do I want to view the objects” from “how many distinct values do I want to store under which rule”.

## 6. How to fix when you need a `TreeSet` consistent with `equals`

With `Item.equals` checking only `id`, the corresponding comparator can be:

~~~java
Comparator<Item> byLogicalIdentity =
    Comparator.comparingInt(Item::id);

Set<Item> set = new TreeSet<>(byLogicalIdentity);
set.add(new Item(7, 1));
set.add(new Item(7, 2));

System.out.println(set.size()); // 1
~~~

Here `compare(a, b) == 0` if and only if the two objects have the same `id`, matching how `equals` is defined. The comparator no longer distinguishes revisions that share the same `id`.

Depending on business requirements, there are three reasonable fixes:

1. **Keep `equals` by ID, adjust the sorted set/map comparator to ID.** Appropriate when you want one entry per entity.
2. **If revision is truly part of identity**, include revision in **both `equals`, `hashCode`, and the comparator**. Then `Item(7,1)` and `Item(7,2)` truly are two distinct values, fitting keeping both.
3. **If only display ordering is needed**, keep the ID + revision comparator for `List` sorting operations. Use another collection for deduplication by `equals`, or separate a key type representing each revision.

Do not patch by changing `hashCode` while keeping the old `equals` and comparator: `TreeSet` does not rely on hashes to decide duplicates. Also do not casually prepend `if (a.equals(b)) return 0;` to an arbitrary comparator without proving transitivity and consistency of equivalence groups. A comparator mixing rules arbitrarily can break the comparison contract.

## 7. The `Comparator` contract is still mandatory even when inconsistent with `equals`

Consistency with `equals` is strongly desirable for sorted sets/maps, yet `Comparator` must still satisfy the rules of an ordering relation:

- **Sign reversal:** `sgn(compare(a,b)) == -sgn(compare(b,a))`.
- **Transitivity:** if `a > b` and `b > c`, then `a > c`.
- **Consistent equivalence groups:** if `compare(a,b) == 0`, then the comparison sign of `a` with an object `z` must equal the comparison sign of `b` with `z`.
- **Stability:** results should not change when the fields used for comparison do not change.

`Comparator.comparingInt(Item::id).thenComparingInt(Item::revision)` in the example is a valid ordering that does not violate the above properties. It is merely **inconsistent with `Item.equals`** because it additionally checks `revision`.

Avoid writing `return a.id() - b.id();`: integer subtraction can overflow `int` and flip the sign of the result, breaking the comparator. `Integer.compare` or `Comparator.comparingInt` handles integer comparison more safely.

For objects placed in `TreeSet` or used as `TreeMap` keys, do not mutate fields participating in the comparator after adding them to the structure. If the ordering changes silently without rebuilding the tree, `contains`, `get`, or `remove` operations may return unexpected results. The examples in this lesson use `final` fields to avoid this phenomenon.

## 8. Spotting faulty situations in real code

Several signs worth checking:

- `HashSet.size()` differs from `TreeSet.size()` despite inserting the same values. Check whether the comparator properly returns `0` for every pair where `equals == true`.
- `TreeSet.contains(x)` is `false` even though you find an element `y` in the set where `x.equals(y) == true`. The comparator may be distinguishing `x` and `y`.
- `TreeMap.put(k2, v2)` creates a new entry even though `k1.equals(k2) == true`. If using a comparator inconsistent with `equals`, the two keys can reside at two different positions in the tree.
- A `thenComparing(...)` comparator added “to break ties when criteria match”, yet the secondary criterion is **not in `equals`**. This is a point to review when the comparator serves a sorted set/map.
- A comparator compares only one field while `equals` compares multiple fields, creating the reverse situation: `compare == 0` despite `equals == false`, causing the sorted set/map to merge business-distinct values.

Seeing `equals == true` and `compare != 0` does not automatically mean every comparator must be rewritten. Check whether the comparator is used **only for sorting** or also used to **determine uniqueness and lookup**.

## 9. Verification exercises

With `Item.equals` checking only `id`, `hashCode` by `id`, and a comparator checking `id` then `revision`, answer on your own before running code:

1. What does `new Item(7,1).equals(new Item(7,2))` return? What sign does the comparator return for those two objects?
2. Add the two `Item`s above to a `HashSet` and a `TreeSet` using the two-field comparator. What is the size of each set? Why?
3. What does `TreeSet.contains(new Item(7,3))` return if the set holds `Item(7,1)` and `Item(7,2)`? Meanwhile, what does `HashSet.contains(new Item(7,3))` return?
4. If you change `TreeSet` to compare by `id` alone, does the size change? Which behavior becomes consistent with `equals`?
5. If the real requirement is to store each revision as an independent element, should `equals`/`hashCode` be updated to inspect both `id` and `revision`? Which business rule does this depend on?
6. Why does changing only `hashCode` fail to solve the case where `TreeSet` keeps two objects with `equals == true`?

**Takeaway:** **`equals(a,b) == true` does not automatically force a custom comparator to return `0`**. However, `TreeSet` and `TreeMap` use **the `compare == 0` result** to determine equivalent elements/keys, so a comparator inconsistent with `equals` can produce “duplicates by `equals` yet distinct in the tree”. When a sorted set/map must adhere strictly to value-based set/map semantics, ensure **`compare(a,b) == 0` if and only if `a.equals(b)`**; if you only need finer sorting, use that comparator with a list.
