# Nested Collections Depend on Each Element's `equals()`

In Java, whether two collections have the same **logical content** depends first on the `equals(Object)` rule of the collection type at **each nesting level**, and then on the `equals()` of the innermost leaf elements. A collection **does not automatically guess** that two objects sharing a few fields, two arrays with identical contents, or two lists with identical elements in reverse order should be considered equal.

For example, with the type `List<Set<Product>>`:

- The outer level is `List`: the order of **the nested sets** matters.
- Each inner level is `Set`: the listing order of **products within a set** does not matter.
- Each element is `Product`: whether a pair of products is equal depends on how the `Product` class overrides `equals(Object)`.
- If any levels use hashing (`HashSet` or `HashMap`), the element's `hashCode()` computation must also be consistent with `equals()`.

**Main idea:** collection `equals()` does not replace designing proper equality on the element type; it uses the equality already provided by the inner types.

## 1. Equality Rules of Common Collections

| Type | Condition for Two Collections to Be Equal | Does Order Matter? | What Matters at the Child Level |
| --- | --- | --- | --- |
| `List<E>` | Same number of elements and each corresponding position is equal | **Yes** | Elements are compared using `equals()` |
| `Set<E>` | Same number of elements and each element in one set has an equal element in the other set | **No** | `equals()` defines duplicate elements; `hashCode()` must be compatible with hash sets |
| `Map<K,V>` | Same set of key → value mappings | **No** dependency on insertion order | Keys use appropriate `equals()/hashCode()`; values are compared using `equals()` |
| `Collection<E>` in general | No single universal `equals()` rule for all implementations | Depends on concrete type | Do not assume all collections are compared by the same criteria |

The contracts of `List`, `Set`, and `Map` are defined on their respective interfaces; for example, an `ArrayList` and a `List.of(...)` can be equal if their order, size, and corresponding elements match. Conversely, a `List` does not become equal to a `Set` merely by containing values that look similar. `Collection` is only a common superinterface and does not impose a uniform value-comparison rule on every implementation.

### Level-by-Level Reasoning Example

Suppose:

~~~java
List<Set<String>> left = List.of(
    Set.of("A", "B"),
    Set.of("C")
);
List<Set<String>> right = List.of(
    Set.of("B", "A"),
    Set.of("C")
);
~~~

`left.equals(right)` is `true`: the two `List` instances have two matching positions, where `Set.of("A", "B")` equals `Set.of("B", "A")` because sets ignore order.

If you swap **the positions of the two sets** in `right` to `List.of(Set.of("C"), Set.of("A", "B"))`, the result will be `false` because the outer list is ordered.

If the outer level is `Set<List<String>>`, the order of the **member lists** does not matter, yet the order of strings **inside each list** still matters:

~~~java
Set<List<String>> a = Set.of(List.of("A", "B"), List.of("C"));
Set<List<String>> b = Set.of(List.of("C"), List.of("A", "B"));
Set<List<String>> c = Set.of(List.of("C"), List.of("B", "A"));

// a.equals(b) == true; a.equals(c) == false.
~~~

These conclusions follow from the contract at each level, not from Java using a separate "deep comparison" mechanism.

## 2. The Leaf Level Depends on Object `equals()`

Suppose `Product` has two fields:

- `sku`: unique product code per business rules, fixed over the object's lifetime.
- `displayName`: presentation name; two records with the same `sku` may use different names while still representing **the same product**.

If product equality is defined as "same SKU", then the two instances `new Product("P-1", "Bút")` and `new Product("P-1", "Pen")` must be treated as equal by `Product.equals()`. When they appear in two corresponding lists or sets, the collection must also treat them as equal elements.

This implements **a specific business rule**, not a default for all classes: for another value type, the name or other attributes might be part of the equality definition. If `Product` **does not override `equals()`**, it inherits `Object.equals()`, which compares reference identity; two instances created by two separate `new` calls are normally unequal even if their `sku` fields are identical.

A class defining a custom `equals()` must also override `hashCode()`: if `a.equals(b)` is true, `a.hashCode() == b.hashCode()` must be true. This is especially important because a `Set` level or `Map` key may use hashing even when the outer level is a `List`.

## 3. Runnable Java 17 Example: `List<Set<T>>`, `Set<List<T>>`, and `Map<String,List<T>>`

Create the file **`NestedCollectionEqualityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class NestedCollectionEqualityDemo {

    static final class Product {
        private final String sku;
        private final String displayName;

        Product(String sku, String displayName) {
            this.sku = Objects.requireNonNull(sku, "sku");
            this.displayName = Objects.requireNonNull(displayName, "displayName");
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof Product other)) {
                return false;
            }
            return sku.equals(other.sku);
        }

        @Override
        public int hashCode() {
            return sku.hashCode();
        }
    }

    public static void main(String[] args) {
        List<Set<Product>> groupsA = List.of(
            Set.of(new Product("A", "Pen"), new Product("B", "Pencil")),
            Set.of(new Product("C", "Book"))
        );

        List<Set<Product>> groupsB = List.of(
            Set.of(new Product("B", "New name"), new Product("A", "Other name")),
            Set.of(new Product("C", "Renamed"))
        );

        List<Set<Product>> reversedGroups = List.of(
            Set.of(new Product("C", "Book")),
            Set.of(new Product("A", "Pen"), new Product("B", "Pencil"))
        );

        System.out.println("list of sets equal: "
            + groupsA.equals(groupsB));
        System.out.println("list of sets same hash: "
            + (groupsA.hashCode() == groupsB.hashCode()));
        System.out.println("outer list order matters: "
            + groupsA.equals(reversedGroups));

        Set<List<Product>> listsA = Set.of(
            List.of(new Product("A", "Pen"), new Product("B", "Pencil")),
            List.of(new Product("C", "Book"))
        );
        Set<List<Product>> listsB = Set.of(
            List.of(new Product("C", "New")),
            List.of(new Product("A", "Different"), new Product("B", "Different"))
        );
        Set<List<Product>> changedInnerOrder = Set.of(
            List.of(new Product("C", "Book")),
            List.of(new Product("B", "Pencil"), new Product("A", "Pen"))
        );

        System.out.println("set of lists equal: "
            + listsA.equals(listsB));
        System.out.println("inner list order matters: "
            + listsA.equals(changedInnerOrder));

        Map<String, List<Product>> mapA = new LinkedHashMap<>();
        mapA.put("front", List.of(
            new Product("A", "Pen"), new Product("B", "Pencil")));
        mapA.put("back", List.of(new Product("C", "Book")));

        Map<String, List<Product>> mapB = new LinkedHashMap<>();
        mapB.put("back", List.of(new Product("C", "Renamed")));
        mapB.put("front", List.of(
            new Product("A", "Another name"),
            new Product("B", "Another name")));

        Map<String, List<Product>> mapC = new LinkedHashMap<>(mapB);
        mapC.put("front", List.of(
            new Product("B", "Pencil"), new Product("A", "Pen")));

        System.out.println("map insertion order irrelevant: "
            + mapA.equals(mapB));
        System.out.println("map value list order matters: "
            + mapA.equals(mapC));

        List<int[]> arraysA = List.of(new int[] {1, 2});
        List<int[]> arraysB = List.of(new int[] {1, 2});
        System.out.println("array elements equal by content: "
            + arraysA.equals(arraysB));
        System.out.println("nested value lists equal: "
            + List.of(List.of(1, 2)).equals(List.of(List.of(1, 2))));

        List<String> inner = new ArrayList<>(List.of("A"));
        List<List<String>> outer = List.of(inner);
        Set<List<List<String>>> indexed = new HashSet<>();
        indexed.add(outer);
        int before = outer.hashCode();
        inner.add("B");
        System.out.println("nested hash changed after mutation: "
            + (before != outer.hashCode()));
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac NestedCollectionEqualityDemo.java
java NestedCollectionEqualityDemo
~~~

**Standard output:**

~~~text
list of sets equal: true
list of sets same hash: true
outer list order matters: false
set of lists equal: true
inner list order matters: false
map insertion order irrelevant: true
map value list order matters: false
array elements equal by content: false
nested value lists equal: true
nested hash changed after mutation: true
~~~

Explanation of each output group:

1. `groupsA` and `groupsB` are equal because each set at the same position contains equivalent SKUs; declaration order inside the sets and differing `displayName` values do not change the result.
2. When both outer lists are equal under the contract, their hashes must also be equal. `List.hashCode()` relies on the hashes of its elements, which in this example are `Set<Product>` instances.
3. `reversedGroups` swaps the order of **the two sets in the outer list**, so it does not equal `groupsA`.
4. `listsA` and `listsB` are both sets containing two equal lists; swapping the listing order of **the two lists in the outer set** has no effect. However, swapping `A` and `B` **inside a list** makes the result `false`.
5. The two `LinkedHashMap` instances have entries with the same keys and equivalent value lists, so they are equal even though inserted in different orders. `mapC` differs from `mapA` because the list value for key `"front"` has reversed order.
6. The two `int[]` arrays containing `1, 2` are two distinct array objects. Java arrays do not override `Object.equals()` by content; `List<int[]>` calls the array's `equals()` and yields `false`. Replacing each array with `List<Integer>` yields equality by each integer value.
7. `outer` is a list **whose direct structure cannot be modified**, yet it holds a reference to the mutable `inner`. When `"B"` is added to `inner`, the hash computed across the levels of `outer` changes. Having inserted `outer` into `HashSet` beforehand creates a dangerous situation: the current hash lookup path may no longer match the inserted slot. The example only prints that the hash changed, **not relying on a `contains()` result after the structure has been destabilized**.

`displayName` in `Product` is kept to make clear that differing values in a field **outside the equality definition** between two instances do not alter collection equality.

## 4. How Does `equals()` Propagate Through Levels?

You can read `List<Set<Product>>` as a diagram:

~~~text
List.equals(otherList)
  ├─ check size and first position
  │    └─ Set.equals(otherSet)
  │         └─ find equivalent element
  │              └─ Product.equals(otherProduct)
  └─ check second position
       └─ Set.equals(otherSet)
            └─ Product.equals(otherProduct)
~~~

Each layer invokes the equality method according to **the contract of the object type at that layer**. For `List<List<Product>>`, both list layers require order. For `Set<Set<Product>>`, both set layers ignore element order. For `Map<Key,List<Set<Product>>>`, the map ignores entry order; the value is a list so it preserves the order of the sets; each set ignores the order of products inside it.

This leads to two important consequences:

- **Different container types mean different semantics:** changing an outer layer from `List` to `Set` can discard order distinction; changing a layer from `Set` to `List` can make order part of equality.
- **Different element types mean different semantics:** replacing `Product` (which has SKU-based equality) with a class that does not override `equals()` causes two instances with the same SKU to stop being equal; changing the implementation of `Product.equals()` also affects every structure containing it.

Not every nested object is a collection. If an element is a `LocalDate`, `String`, `BigDecimal`, array, record, or domain class, the outer layer uses the exact `equals()` defined by that element type. For example, `BigDecimal("1.0")` and `BigDecimal("1.00")` are not equal under `BigDecimal.equals()` even though they compare numerically equal via `compareTo() == 0`; placing them into two corresponding lists **does not automatically switch** to numeric comparison. Choose and normalize value types according to business requirements before using them as elements.

## 5. `hashCode()` of Nested Structures Must Be Consistent

`List`, `Set`, and `Map` all have hash code rules tied to their equality contracts:

- `List.hashCode()` combines each element's hash code **in order**.
- `Set.hashCode()` sums the hash codes of its elements; by nature, it is **order-independent**.
- `Map.hashCode()` sums the hash codes of its entries; each entry combines key and value hashes, **independent of entry order**.

Therefore, a change in the `hashCode()` of the innermost element can propagate to the set's hash, then to the list's hash, and then to another object containing that list.

Suppose `Product.equals()` compares only `sku`, yet `Product.hashCode()` includes `displayName` in the hash calculation. Then two `Product` instances with the same SKU and different names could be **equal yet have different hashes**. A `Set<Product>` may no longer obey the contract for lookup, deduplication, and equality comparison; two `List<Set<Product>>` instances that appear equal could also receive different hashes. The problem originates in `Product` and propagates up to the outer nested collections.

Remember the **one-way** condition:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
~~~

The converse is not required: two unequal elements are permitted to share the same hash. Never use `hashCode() == hashCode()` as proof that two objects or two collections are equal. To test equality, you must call `equals()`.

For `Map<K,V>`, hash and equality depend not only on keys but also on **values**. If a value is a mutable collection, the map as a whole can change its `equals()/hashCode()` along with the value even when keys remain unchanged. This is a particular risk when the map itself (or a collection containing the map) is used as a key or element in another hash structure.

## 6. Arrays and Null at the Leaf Element Level

A `List` layer does not automatically deep-compare `int[]` elements:

~~~java
List<int[]> a = List.of(new int[] {1, 2});
List<int[]> b = List.of(new int[] {1, 2});
// a.equals(b) == false: the two elements are two separate arrays.
~~~

To treat arrays as values, you must choose content-based comparison (`Arrays.equals`/`Arrays.deepEquals` as appropriate) and a wrapper type with matching `equals/hashCode` if used as an element or hash key. The lesson on **array elements in Collections** provides a full program and defensive copying techniques.

`null` is accepted by some types such as `ArrayList`, `HashSet`, and `HashMap` and handled according to each layer's equality contract; `List.of`, `Set.of`, and `Map.of` reject `null` elements, keys, and values. Do not use `Set` iteration order to infer equality of nested collections.

## 7. Mutable Elements Can Change Even the Outer Structure's Hash

An outer collection that forbids structural modification can still hold a reference to a mutable inner collection:

~~~java
List<String> inner = new ArrayList<>(List.of("A"));
List<List<String>> outer = List.of(inner);
inner.add("B"); // outer still has one element, but the element's value has changed.
~~~

If `outer` is currently an element of a `HashSet`, `outer.hashCode()` can change after insertion, causing `contains` or `remove` to fail to find the data properly. With immutable `String` elements, calling `List.copyOf(inner)` before nesting isolates the **structure** of the inner list from `inner`; with mutable objects, you must copy or transform element state separately.

Choose data participating in `equals/hashCode` that stays stable throughout its time as a key or element in a hash structure. The final lesson of the chapter carefully distinguishes `Collections.unmodifiableXxx`, shallow copies, and deep immutability.

## 8. Common Cognitive Mistakes

| Common Misconception | What to Remember |
| --- | --- |
| "Two collections with the same number of elements and the same visible data are equal." | Still depends on collection type, order, and each element's `equals()` |
| "Set ignores order, so Set<List<T>> also ignores order inside each list." | Wrong: the outer set ignores the order of lists, **the inner lists remain ordered** |
| "Maps inserted in different orders will not be equal." | `Map.equals()` does not rely on insertion order; it compares key–value mappings |
| "Products with the same SKU are naturally equal." | You must implement `Product.equals()` by SKU if that is the business contract |
| "Just use `equals()`, no need to care about `hashCode()`." | Wrong for hash collections and hashes of nested collections |
| "Arrays with the same contents are equal inside a List." | Arrays use identity equality unless wrapped or converted |
| "`List.of(...)` makes everything inside immutable." | Only the outer list structure cannot be modified; mutable elements can still change |
| "Two identical hashes mean the two collections are equal." | Matching hashes can result from collisions; you must check `equals()` |

## 9. Design and Testing Checklist

When working with a type like `List<Set<T>>`, `Set<List<T>>`, or `Map<K,List<V>>`:

1. Sketch out **each layer** and mark clearly which layers preserve order (lists) and which do not (sets/maps).
2. Define `equals()` and `hashCode()` for the leaf element/key type; if using a custom class, verify equality matches business requirements.
3. Construct **two separate structures** with the same logical data, rather than only comparing an object with itself.
4. Change order at a `Set` layer and confirm equality stays unchanged; change order at a `List` layer and confirm equality changes **when element positions actually differ**.
5. Provide two element objects with equal keys but different display fields; confirm the collections are still equal and their hashes are also equal.
6. Test arrays, `null`, numeric types with special `equals()` rules, and mutable element cases as needed.
7. For structures stored as keys in hash collections, ensure no deeply nested value affecting equality or hash is silently mutated.

**Takeaway:** Equality of nested collections is the result of **multiple `equals()` contracts applied in sequence**. `List` compares by position, `Set` compares by membership, and `Map` compares by entry; each layer uses the equality of the objects it contains. Properly designing element `equals()/hashCode()` and keeping key values stable are prerequisites for the entire nested structure to behave correctly.