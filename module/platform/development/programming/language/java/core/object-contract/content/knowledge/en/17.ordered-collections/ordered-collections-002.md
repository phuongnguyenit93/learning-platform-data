# Two Objects Where equals() Is False but Comparator Returns 0

## 1. The issue: “different” by equals yet “equivalent” by ordering

In Java, the following two checks can produce different results:

- `a.equals(b)`: are the two objects **equal according to the class's equality contract**?
- `comparator.compare(a, b) == 0`: are the two objects **tied (equivalent) according to the sorting criterion**?

For example, two products share the code `"P-01"` but have different variants `"red"` and `"blue"`. If the `equals` method treats the pair **(code, variant)** as identity, those two products are **not equal**. However, if the comparator only examines **code**, it returns `0` because both share `"P-01"`.

~~~text
a = Product(sku="P-01", variant="red")
b = Product(sku="P-01", variant="blue")

a.equals(b)                   -> false
compareBySku.compare(a, b)    -> 0
~~~

**There is no syntactic contradiction:** the two comparisons are answering two different questions. However, the discrepancy has major consequences in ordered collections such as `TreeSet` and `TreeMap`, because they use **an ordering comparison result of 0** to recognize duplicate elements/keys.

## 2. equals and Comparator define two separate relations

`equals(Object)` obeys `Object`'s equality contract: reflexive, symmetric, transitive, consistent, and `x.equals(null) == false` for non-`null` `x`. When overriding `equals`, a class must also override a compatible `hashCode`: two equal objects must have the same hash code.

`Comparator<T>` defines **an ordering** over objects of type `T`. A negative result means coming before, a positive result means coming after, and `0` means the two objects are **indistinguishable under the ordering chosen by the comparator**. It does not automatically call `equals` to check whether two objects are identical across all fields.

| Scenario | equals | Comparator | Interpretation |
| --- | --- | --- | --- |
| Same sku, different variant; equals checks both, comparator checks only sku | false | 0 | Different objects by full value, tied when sorted by sku |
| Same sku and variant | true | 0 | Equality and ordering equivalence coincide |
| Different sku | false | Negative or positive | Comparator distinguishes them by sku |
| Comparator checks (sku, variant), equals also checks (sku, variant) | false when variant differs | Non-zero when variant differs | The two relations are designed consistently |

Java recommends that a comparator have an ordering **consistent with equals** when used in `SortedSet`/`SortedMap`:

~~~text
compare(a, b) == 0    if and only if    a.equals(b) == true
~~~

This is an **equivalence-relation alignment** condition, not a requirement that every comparator in every context inspect all fields of an object. A comparator used for **grouping, display sorting, or sorting by a secondary key** may intentionally return 0 for two objects where `equals` is false. You simply need to understand that when you pass that comparator into `TreeSet`/`TreeMap`, you are applying a different definition of “duplicate key”.

A valid ordering must also obey sign reversal, transitivity, and consistency of the 0-result equivalence group. Confusion about equality cannot be fixed with an arbitrary comparator that violates the ordering contract.

## 3. Why does TreeSet treat two distinct objects as one?

`HashSet` uses `hashCode` combined with `equals` to manage elements. Meanwhile, `TreeSet` uses **natural ordering** (`Comparable`) or **a supplied comparator** to sort and determine whether two elements are duplicates in the tree.

Suppose:

~~~text
a.equals(b) == false
comparator.compare(a, b) == 0
~~~

If `a` is added first and then `b` is added:

1. `TreeSet` inserts `a`.
2. When examining `b`, the comparator returns `0` against the corresponding key element. `TreeSet` considers `b` equivalent to the existing element and does not add a second element.
3. `set.size()` remains `1`.
4. `set.contains(b)` may return `true` even though `a.equals(b)` is `false`: the tree's lookup relies on the comparator.

When a comparator is inconsistent with `equals`, Java can still execute operations according to the given comparison rule, but `TreeSet` **no longer preserves the expectations of the general `Set` contract regarding element equality**. This is the cause of many bugs where data appears “lost” when switching from `HashSet` to `TreeSet`.

In particular, **a `contains(b)` result does not prove that the exact object `b` is in the tree**. It only indicates that an element exists which the comparator treats as equivalent to `b`.

## 4. Runnable Java 17 example with TreeSet and TreeMap

The program uses a `record Product` with two components `sku` and `variant`. The record auto-generates `equals` and `hashCode` based on **both components**. Comparator `BY_SKU` compares only `sku`; comparator `BY_SKU_AND_VARIANT` compares `variant` next when `sku` matches.

Save as **ComparatorZeroDemo.java**:

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorZeroDemo {
    record Product(String sku, String variant) {
        Product {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(variant, "variant");
        }
    }

    static final Comparator<Product> BY_SKU =
            Comparator.comparing(Product::sku);

    static final Comparator<Product> BY_SKU_AND_VARIANT =
            Comparator.comparing(Product::sku)
                    .thenComparing(Product::variant);

    public static void main(String[] args) {
        Product red = new Product("P-01", "red");
        Product blue = new Product("P-01", "blue");
        Product other = new Product("P-02", "black");

        System.out.println("equals red/blue: " + red.equals(blue));
        System.out.println("compare by sku zero: "
                + (BY_SKU.compare(red, blue) == 0));
        System.out.println("compare by full key zero: "
                + (BY_SKU_AND_VARIANT.compare(red, blue) == 0));

        Set<Product> hash = new HashSet<>();
        hash.add(red);
        hash.add(blue);
        System.out.println("HashSet size: " + hash.size());

        Set<Product> bySkuSet = new TreeSet<>(BY_SKU);
        System.out.println("TreeSet add red: " + bySkuSet.add(red));
        System.out.println("TreeSet add blue: " + bySkuSet.add(blue));
        System.out.println("TreeSet add other: " + bySkuSet.add(other));
        System.out.println("TreeSet size: " + bySkuSet.size());
        System.out.println("TreeSet contains blue: "
                + bySkuSet.contains(blue));
        System.out.println("TreeSet contains red: "
                + bySkuSet.contains(red));

        Map<Product, String> map = new TreeMap<>(BY_SKU);
        map.put(red, "red-value");
        map.put(blue, "blue-value");
        System.out.println("TreeMap size: " + map.size());
        System.out.println("TreeMap get red: " + map.get(red));
        System.out.println("TreeMap get blue: " + map.get(blue));

        Set<Product> fullSet = new TreeSet<>(BY_SKU_AND_VARIANT);
        fullSet.add(red);
        fullSet.add(blue);
        System.out.println("Full-key TreeSet size: " + fullSet.size());

        Map<Product, String> fullMap =
                new TreeMap<>(BY_SKU_AND_VARIANT);
        fullMap.put(red, "red-value");
        fullMap.put(blue, "blue-value");
        System.out.println("Full-key TreeMap size: " + fullMap.size());
    }
}
~~~

Using JDK 17 or higher:

~~~bash
javac ComparatorZeroDemo.java
java ComparatorZeroDemo
~~~

Standard output:

~~~text
equals red/blue: false
compare by sku zero: true
compare by full key zero: false
HashSet size: 2
TreeSet add red: true
TreeSet add blue: false
TreeSet add other: true
TreeSet size: 2
TreeSet contains blue: true
TreeSet contains red: true
TreeMap size: 1
TreeMap get red: blue-value
TreeMap get blue: blue-value
Full-key TreeSet size: 2
Full-key TreeMap size: 2
~~~

### Step-by-step explanation of the output

- `red.equals(blue)` is `false`: the record compares both `sku` and `variant`; the `variant` field differs.
- `BY_SKU.compare(red, blue) == 0` is `true`: the comparator looks only at `sku`. Adding `thenComparing(Product::variant)` distinguishes the two keys so the result is **non-zero**.
- `HashSet` keeps both `red` and `blue` because they differ according to `equals`; size equals `2`.
- `TreeSet` with `BY_SKU` accepts `red` but rejects adding `blue`, because both are equivalent by ordering. `other` has a different sku so it is added. The size is also `2`, but **the element set differs from HashSet**: the two elements here are `red` and `other`.
- `TreeSet.contains(blue)` returns `true` because `red` with the same sku is present; that result does not confirm that the `blue` object was successfully inserted.
- `TreeMap` treats two `Product` instances with the same sku as one key. `put(blue, "blue-value")` updates the value of the entry created with `red`, leaving size at `1`. When querying by either `red` or `blue`, both return `"blue-value"`.
- The full comparator `BY_SKU_AND_VARIANT` distinguishes both, so `TreeSet` and `TreeMap` allow keeping two separate entries.

The example does not put mutable fields into the key; the record has two immutable `String` fields. Consequently, the results are not affected by modifying keys after insertion.

## 5. How does TreeMap handle “duplicate keys” under a comparator?

Similar to `TreeSet`, `TreeMap` uses the comparator (or natural ordering of the key) to organize the tree and locate an equivalent key. If `compare(k1, k2) == 0`, the two keys are treated as the same lookup slot. When calling `put(k2, value2)` after `put(k1, value1)`, the operation normally updates **the value for the equivalent key** instead of creating a second entry.

Consequences:

| Operation | Comparator checking only sku | Meaning |
| --- | --- | --- |
| `put(red, "red-value")` | Adds entry for sku P-01 | Initial value |
| `put(blue, "blue-value")` | Updates entry with same sku | Does not create a second key |
| `size()` | 1 | Only one equivalence class by sku |
| `get(red)` | `"blue-value"` | Updated value |
| `get(blue)` | `"blue-value"` | Same equivalence class by comparator |

This is dangerous if business logic needs to distinguish each `variant`. A write operation can accidentally overwrite previous data even though `equals` indicates two keys are distinct. If you truly want each sku to have only **one** record, a sku-based comparator may fit, though in that case modeling the key directly as `String sku` or a key type containing only `sku` makes the rule easier to understand.

Do not rely on iteration order to distinguish two keys whose comparator returns 0: under the tree's policy, they are inherently one entry. To store multiple variants under the same sku, you can use `Map<String, List<Product>>`, `Map<String, Set<Product>>`, or a composite key comprising `(sku, variant)` according to business needs.

## 6. When is a comparator returning 0 for equals-false objects intentional?

Such a comparator is not always a bug. A comparator ranking students **only by score** may treat two students with the same score as tied, even though they are two different people according to `equals`. When using the comparator solely to group or sort a list by score, tying has a clear meaning.

For example:

~~~java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score);
~~~

This is an **illustrative declaration** with a hypothetical `Student` class having a `score()` method, not a standalone program. It yields `0` when two students have the same score. If used with `List.sort(byScore)`, the list still contains both students; sorting does not remove elements by itself. However, if that list is transferred into `TreeSet<>(byScore)`, the set will keep only one element from each group deemed equivalent by score.

Similarly, `String.CASE_INSENSITIVE_ORDER.compare("Java", "java") == 0`, while `"Java".equals("java")` is `false`. A case-insensitive comparator may be suitable for display sorting or case-insensitive lookup, yet a `TreeSet` using that comparator will not keep both strings as two separate elements.

Therefore, before using a comparator, ask yourself: **am I sorting for display, grouping by a criterion, or defining unique element/key identity in an ordered collection?** These three purposes may require three different policies.

## 7. How to design the right Comparator when using TreeSet/TreeMap

### 7.1. Add secondary keys to distinguish objects that must remain separate

If `Product`'s `equals` inspects sku and variant, you should use:

~~~java
Comparator<Product> byFullKey =
        Comparator.comparing(Product::sku)
                .thenComparing(Product::variant);
~~~

This is a **comparator declaration expression in a context having the Product type as in the main program**, not a standalone program. When both strings are equal, `compare == 0`; for the given `Product` record, that also implies `equals == true`. The secondary key prevents products of different variants from being merged into one entry.

If `equals` compares even more fields, a comparator meant to be consistent must ensure it **does not return 0 for two objects that equals considers different**, nor split two equal objects into two ranks. Hence, you cannot arbitrarily pick a random secondary key while ignoring actual equality fields.

### 7.2. Use the right collection type for the desired contract

- Need to identify elements by `equals` without maintaining sorted order: use `HashSet`/`HashMap` with properly implemented `equals` and `hashCode`.
- Need elements/keys traversed in order while fully distinguishing objects by `equals`: use `TreeSet`/`TreeMap` with a comparator consistent with `equals`.
- Need to retain all objects while displaying them by an attribute: store in a `List` and `sort` with a comparator on that attribute; sorting a list does not drop tied elements.
- Need to group multiple objects by an attribute: use a structure mapping from the grouping attribute to a list/set of elements, instead of using a single-value `TreeMap` and accidentally overwriting the group.

`TreeSet` and `TreeMap` require the comparator to provide a stable, properly sign-reversing, and transitive ordering. Adding tie-breakers must preserve these properties; `Comparator.comparing(...).thenComparing(...)` with standard-ordered keys is usually easier to verify than manual logic.

### 7.3. Keep sort keys stable

If you modify a field participating in the comparator after placing the object into a `TreeSet` or using it as a `TreeMap` key, the tree does not restructure itself for the new value. Failures in `contains`, `get`, or traversal no longer following the expected order can occur. Use immutable keys, or remove the key from the structure before modifying it and reinsert it under the new state.

Note the distinction: `HashSet` relies on the stability of `equals`/`hashCode`; `TreeSet` additionally relies on the stability of the ordering comparison criterion. A class with a stable hash code whose comparator reads a mutable field still carries risk in `TreeSet`.

## 8. Common pitfalls

### Pitfall 1: Assuming TreeSet uses equals to check duplicates

When `comparator.compare(a, b) == 0`, `TreeSet` treats the two elements as equivalent even if `a.equals(b)` is `false`. Checking `set.contains(b)` can return `true` in a situation where `b` was never successfully inserted.

### Pitfall 2: Comparing only the primary key when the real key has multiple fields

If a record is identified by `(userId, orderId)` yet the comparator compares only `userId`, orders belonging to the same user will be collapsed into one key. Clearly define the composite key and apply `thenComparing` in the appropriate priority order.

### Pitfall 3: Forcing the comparator to return 1 when two objects have different references

A “workaround” such as `if (a != b) return 1;` does not guarantee sign reversal: for two distinct objects, both `compare(a,b)` and `compare(b,a)` can be positive. This violates the Comparator contract. A secondary criterion **with deterministic ordering** is needed, not an arbitrary return value.

### Pitfall 4: Adding a random or time-based parameter to the result

If the comparator returns different results for the same pair of objects across calls, the sorted tree may fail to locate the stored position properly. Ordering criteria must be consistent with the allowed state of the object, and ideally based on immutable keys.

### Pitfall 5: Using a grouping comparator and assuming every element was preserved

`TreeSet` stores only one representative for each equivalence group under the comparator. `TreeMap` stores only one entry for each equivalent key. To keep all members of a group, use a `List`, or `Map<GroupKey, List<Member>>` to clearly express a one-to-many relationship.

## 9. Testing before putting a Comparator into SortedSet or SortedMap

With business-meaningful values, test the following cases:

1. Pick two objects `a`, `b` where `!a.equals(b)`. Check the result of `compare(a,b)`; if it is `0`, verify whether treating them as one key in the tree is intentional.
2. Pick two objects that are equal according to `equals`. If compatibility with the `Set`/`Map` contract is required, verify `compare(a,b) == 0`.
3. Test `TreeSet.add(a)`, `TreeSet.add(b)`, `size()`, and `contains(b)`; do not infer separate existence based solely on `contains`.
4. Test `TreeMap.put(a,v1)`, `put(b,v2)`, `size()`, and `get`; clarify whether overwriting values because the comparator treats both keys as one is acceptable.
5. Add necessary tie-breakers and re-test with objects sharing the primary key but differing in secondary keys.
6. Test transitivity, sign reversal, and stability of the comparator; especially with boundary values, nullable properties, and mutable keys.
7. Test all `null` cases: `Comparator.nullsFirst`/`nullsLast` when wanting to support `null` objects or keys compatible with the collection, noting that **TreeMap/TreeSet may reject null depending on the comparator**; verify the actual policy rather than guessing.

**Takeaway:** `a.equals(b) == false` and `comparator.compare(a,b) == 0` can both be true at the same time because the two comparisons serve different purposes. However, when a comparator is used by `TreeSet` or `TreeMap`, **0 means the same element/key according to the tree**. If two objects must be kept as two separate values, define an ordering criterion consistent with `equals`, typically by adding the necessary secondary keys.
