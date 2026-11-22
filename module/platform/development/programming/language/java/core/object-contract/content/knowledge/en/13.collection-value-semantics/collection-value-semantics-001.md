# `List.equals()` Compares Elements by Order

## 1. When Are Two Lists Equal?

In Java, `java.util.List.equals(Object)` defines **value equality of an ordered sequence**. Two lists are considered equal if and only if:

1. The object being compared is also a `List`.
2. Both lists have the **same number of elements**.
3. For every valid index `i`, the element at position `i` of the first list equals the element at the **exact same position `i`** of the second list. If both elements are `null`, they are considered equal at that position; otherwise, they are compared using the element's `equals` method.

Expressed as a condition:

```text
left.equals(right)
    = right is a List
      AND left.size() == right.size()
      AND for all i in [0, size):
          Objects.equals(left.get(i), right.get(i)) == true
```

The snippet above is a **conceptual description**, not Java library source code or an optimal implementation. The API does not require calling `get(i)` on each element in this manner; iterating with an iterator is often more suitable for certain implementations, such as linked lists.

Examples:

```text
["Java", "Spring"] ==value==> ["Java", "Spring"]    true
["Java", "Spring"] ==value==> ["Spring", "Java"]    false
["Java", "Java"]   ==value==> ["Java"]             false
```

**Both order and frequency matter.** Simply having the same elements, or the same total number of elements, is not enough. This is the essential characteristic that distinguishes `List` from `Set`.

In the sections below, `list.equals(other)` is always a value comparison. The expression `list == other`, on the other hand, asks whether two variables hold the same reference.

## 2. Index-by-Index Rule

Let us compare:

```java
List<String> a = List.of("A", "B", "A");
List<String> b = List.of("A", "B", "A");
List<String> c = List.of("A", "A", "B");
```

The snippets above use the `List` type and can be placed inside a method after `import java.util.List;`; they do not form a complete file yet.

| Index | `a` | `b` | `c` | `a` vs `b` | `a` vs `c` |
| --- | --- | --- | --- | --- | --- |
| 0 | A | A | A | Equal | Equal |
| 1 | B | B | A | Equal | **Different** |
| 2 | A | A | B | Equal | Different |

Therefore, `a.equals(b)` is `true` while `a.equals(c)` is `false`. Even though `a` and `c` have the same set of values and the same occurrence count for each value, they have **different orders**. `List.equals` does not sort before comparing.

Cases to remember:

- **Empty lists:** two empty `List` instances are equal, even across different implementations; an empty list does not equal a list containing a single `null` element.
- **Different lengths:** the result is `false` even if the prefix of the longer list matches the shorter list completely.
- **Duplicate elements:** `["x","x","y"]` differs from `["x","y","x"]`. A `Set` may deduplicate elements, whereas a `List` preserves them.
- **Swapping two equal elements:** does not make the list differ in value, because the comparison at every position remains true.
- **Swapping two unequal elements:** usually changes the `equals` result, unless the positions involved still contain elements considered equal according to their own `equals`.

## 3. Independence from Specific Implementations

`List.equals` is a **contract of the `List` interface**. Therefore, two lists with the same elements and order must be equal even if one is an `ArrayList` and the other is a `LinkedList`, or an unmodifiable list created by `List.of`.

```java
// Place inside main with appropriate java.util.* imports.
List<String> array = new ArrayList<>(List.of("one", "two"));
List<String> linked = new LinkedList<>(List.of("one", "two"));

System.out.println(array == linked);       // false
System.out.println(array.equals(linked));  // true
System.out.println(linked.equals(array));  // true
```

The two variables point to **two different objects** and **two different implementation classes**, yet their sequence contents are equivalent. This demonstrates the symmetry of the `equals` contract.

You should not implement `equals` in a custom `List` class by requiring `obj.getClass() == getClass()`, because doing so could prevent a new `List` from equaling an `ArrayList` with the same elements, violating the general `List` contract.

Essentially, `List` equality **does not depend** on mutability, internal allocated capacity, element storage mechanism, or implementation class. Those properties may affect performance and the behavior of add/remove operations, but should not alter the result of value comparison.

## 4. Element Value Equality: `equals`, Types, and `null`

### Elements Are Compared by Their Own Contract

`List.equals` does not know what makes two elements "the same" in domain terms; it relies on the `equals` method of each element. For example:

```java
record Book(String isbn) {}

List<Book> first = List.of(new Book("978-1"));
List<Book> second = List.of(new Book("978-1"));

System.out.println(first.equals(second)); // true
```

The snippet above illustrates a `record` and two lists; the declarations can be placed in their proper positions in a Java 17+ file. The `Book` record automatically provides an `equals` based on `isbn`, so two `Book` objects with different references are still equal.

Conversely, if `Book` is a regular class that does not override `equals`, two `new Book(...)` calls will not automatically be equal just because their fields share identical content. Consequently, the `List.equals` result will also be `false`.

A `List<Integer>` containing `1` differs in value from a `List<Long>` containing `1L`: `Integer.equals(Long)` returns `false`. Java does not automatically convert numeric types to make them equal at the element level.

### `null` Elements

Some implementations allow `null`, such as `ArrayList`. Two positions that are both `null` are considered equal:

```java
List<String> withNull1 = new ArrayList<>(Arrays.asList("A", null));
List<String> withNull2 = new LinkedList<>(Arrays.asList("A", null));

System.out.println(withNull1.equals(withNull2)); // true
```

`List.equals` performs a comparison equivalent to `Objects.equals(elementA, elementB)`: two `null` values are equal, while one `null` and one non-`null` element are not. **`List.of(...)` does not accept `null` elements** and will throw a `NullPointerException` upon list creation; this is a limitation of the factory, not a rule that `List.equals` forbids `null`.

If the list variable itself is `null`, calling `list.equals(other)` will throw a `NullPointerException`; you can use `Objects.equals(listA, listB)` when either **list reference** may be `null`. Be sure to distinguish a `[null]` list (one element) from a `null` list reference (no `List` object).

## 5. Standalone Java 17 Example: Checking Order and Implementations

Create the file `ListEqualsOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Set;

public class ListEqualsOrderDemo {
    record Ticket(String code) {}

    public static void main(String[] args) {
        List<String> a = new ArrayList<>(List.of("A", "B", "A"));
        List<String> same = new LinkedList<>(List.of("A", "B", "A"));
        List<String> reordered = List.of("A", "A", "B");
        List<String> shorter = List.of("A", "B");

        System.out.println("same reference: " + (a == same));
        System.out.println("same sequence: " + a.equals(same));
        System.out.println("symmetric: " + same.equals(a));
        System.out.println("different order: " + a.equals(reordered));
        System.out.println("different size: " + a.equals(shorter));
        System.out.println("hash agrees: "
                + (a.hashCode() == same.hashCode()));

        List<String> withNull = new ArrayList<>(
                Arrays.asList("A", null));
        List<String> otherNull = new LinkedList<>(
                Arrays.asList("A", null));
        System.out.println("same null position: "
                + withNull.equals(otherNull));
        System.out.println("null vs nonnull: "
                + withNull.equals(List.of("A", "B")));

        List<Ticket> t1 = List.of(new Ticket("X"));
        List<Ticket> t2 = List.of(new Ticket("X"));
        System.out.println("record elements: " + t1.equals(t2));

        List<List<Integer>> nested1 =
                List.of(List.of(1, 2), List.of(3));
        List<List<Integer>> nested2 =
                List.of(List.of(1, 2), List.of(3));
        List<List<Integer>> nestedReordered =
                List.of(List.of(3), List.of(1, 2));
        System.out.println("nested same: "
                + nested1.equals(nested2));
        System.out.println("nested reordered: "
                + nested1.equals(nestedReordered));

        Set<String> leftSet =
                new HashSet<>(List.of("A", "B"));
        Set<String> rightSet =
                new HashSet<>(List.of("B", "A"));
        System.out.println("set ignores order: "
                + leftSet.equals(rightSet));
    }
}
```

Run commands:

```bash
javac ListEqualsOrderDemo.java
java ListEqualsOrderDemo
```

Output:

```text
same reference: false
same sequence: true
symmetric: true
different order: false
different size: false
hash agrees: true
same null position: true
null vs nonnull: false
record elements: true
nested same: true
nested reordered: false
set ignores order: true
```

**Explanation:** `a` is an `ArrayList`, and `same` is a `LinkedList`. The two objects do not share the same reference, yet they are equal because all three positions match. `reordered` keeps the same occurrence counts of the letters but changes the order, so it does not equal `a`. `shorter` is missing the last element, so it does not equal `a`. The remaining parts demonstrate `null` comparison, value objects as records, nested lists, and the difference between `List` and `Set`.

Note that `HashSet` at the end is only used for conceptual contrast: `Set.equals` is based on containing the same elements, **regardless of iteration order**. Do not use `new HashSet<>(listA).equals(new HashSet<>(listB))` as a substitute for `List.equals`, because converting to a `Set` can discard order **and occurrence count** information.

## 6. `List.hashCode()` Also Depends on Order

The `List` contract specifies that `hashCode()` is computed sequentially from the first element to the last. Algorithmic idea:

```java
// Algorithm illustrating the List contract; list is an existing List variable.
int hash = 1;
for (Object element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
```

This is an illustrative snippet, not a standalone program. The `int` arithmetic may overflow according to Java integer rules; that is part of the hash calculation, not a bug.

Consequences:

- Two equal `List` instances must have the same hash, even if they belong to different implementations.
- Element order can affect the hash. For example, with `String` elements, `["A","B"]` typically has a different hash from `["B","A"]`.
- Two **unequal** lists can still have the same hash due to collisions; you must never use `hashCode()` instead of `equals()` to conclude that two sequences are equal.
- A `null` element contributes `0` at its corresponding position; it still occupies a position in the sequence and affects how many times the multiplication by `31` is applied.
- If an element in the list mutates data that determines `equals/hashCode`, the hash of the list itself can change, even if you did not add or remove elements in the list.

For example, `["A","B"]` has the hash:

```text
Start h = 1
After "A": h = 31 * 1  + 65 = 96
After "B": h = 31 * 96 + 66 = 3042

For ["B","A"]:
After "B": h = 31 * 1  + 66 = 97
After "A": h = 31 * 97 + 65 = 3072
```

These calculations illustrate that **changing order leads to a different hash code** in this concrete example. They do not prove that every permutation yields a different hash code.

## 7. Differences from `Arrays.equals`, `Objects.equals`, `Set.equals`

| Comparison Method | Meaning | Key Distinction |
| --- | --- | --- |
| `listA.equals(listB)` | Compares length and each element **in order**; argument must be a `List`. | Uses the `equals` contract of each element. |
| `Objects.equals(listA, listB)` | Safely compares two possibly `null` references. | When both are non-`null` lists, delegates to `listA.equals(listB)`. |
| `Arrays.equals(arrayA, arrayB)` | Compares the contents of two arrays of matching type by position. | Must call `Arrays.equals`, because Java arrays themselves do not override `Object.equals`. |
| `Arrays.deepEquals(arrayA, arrayB)` | Deeply compares reference arrays, handling nested array elements. | Does not automatically turn a `List` comparison into an unordered set. |
| `setA.equals(setB)` | Two `Set` instances have the same elements according to element equality. | Ignores order and contains no duplicate elements. |
| `listA == listB` | Compares two `List` references. | Does not compare sequence contents. |

**Lists containing arrays are a common pitfall.** If a `List<int[]>` contains two different `new int[]{1,2}` arrays, `List.equals` will call `equals` on the array elements; arrays use the default `Object.equals` by **reference**. Thus, two lists whose array elements hold the same numbers can still be **unequal**. When you want to compare array contents, you must design element comparison using `Arrays.equals` or convert to suitable value types.

**Lists nested inside lists** behave differently: because each inner element is also a `List`, comparing each element calls `List.equals` at the next level, following the order of each sublist. This is why `nested1.equals(nested2)` in the example returns `true`.

## 8. When a List or Its Elements Change

Because `equals` and `hashCode` of a `List` depend on its **ordered contents at the time of the call**, the following operations can change the result:

- `add`, `remove`, `clear`: change the count and/or positions.
- `set(index, value)`: preserves the size but changes the element at a position.
- `Collections.sort`, `Collections.reverse`, or manual reordering: keeps the same set of elements but changes the order.
- Mutating **internal state of a mutable element** that participates in `equals/hashCode`: the sequence keeps the same reference at each position, yet equality semantics can change.
- Modifying the contents of a **sublist** inside `List<List<T>>`: the outer list can change its `equals/hashCode` result even without adding or removing outer elements.

When using a mutable `List` as a `HashMap` key or `HashSet` element, the changes above can alter the hash value while the hash structure **does not automatically re-index the entry**. Consequently, `containsKey`, `get`, `contains`, and `remove` may fail to find the stored entry. Therefore, keys must remain stable with respect to `equals/hashCode` throughout their lifetime in a hash structure.

Illustrative example using the standalone file `ListKeyDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ListKeyDemo {
    public static void main(String[] args) {
        List<String> key = new ArrayList<>(List.of("A"));
        Map<List<String>, String> map = new HashMap<>();
        map.put(key, "saved");

        int before = key.hashCode();
        System.out.println("before: "
                + map.get(List.of("A")));

        key.add("B");
        int after = key.hashCode();
        System.out.println("hash changed: " + (before != after));
        System.out.println("content after: "
                + key.equals(List.of("A", "B")));
        System.out.println("map size: " + map.size());

        List<String> safeKey = List.copyOf(key);
        Map<List<String>, String> safeMap = new HashMap<>();
        safeMap.put(safeKey, "new");
        key.add("C");

        System.out.println("safe key unchanged: "
                + safeKey.equals(List.of("A", "B")));
        System.out.println("safe lookup: "
                + safeMap.get(List.of("A", "B")));
    }
}
```

```bash
javac ListKeyDemo.java
java ListKeyDemo
```

Stdout:

```text
before: saved
hash changed: true
content after: true
map size: 1
safe key unchanged: true
safe lookup: new
```

We do not print `map.get(key)` after modifying it because the result depends on how the hash table performs lookups; the example focuses on what is guaranteed: **the list is modified, the hash changes, yet the old entry still exists**. `List.copyOf(key)` creates an unmodifiable list that is unaffected by subsequent element additions to `key`. With immutable `String` elements, the value of `safeKey` is also stable.

Be sure to distinguish an **unmodifiable list** from **deep immutability**. If `List.copyOf` contains mutable objects, mutating an element's state can still alter the `equals/hashCode` result of the copied list. If you need a stable hash key, you must ensure that both the elements and any nested data on which equality depends are also stable.

## 9. Complexity, Contracts, and Common Real-World Mistakes

For two lists of the same size `n`, comparison may have to inspect up to `n` pairs of elements; the overall complexity of a linear pass is **O(n)** plus the cost of each element's `equals`. It can short-circuit as soon as a difference is found at any position. If the sizes differ, they can be rejected immediately. `List.equals` itself requires neither sorting nor set analysis, so you should not manually convert data to a `Set` to compare when order matters.

Common misconceptions:

1. **Checking only `containsAll`:** `a.containsAll(b)` and `b.containsAll(a)` do not prove two lists are equal; they miss order and repetition count checks.
2. **Converting to `HashSet` then comparing:** loses order and duplicate element information, leading to `true` for unequal lists.
3. **Comparing with `==`:** compares only references, ignoring two lists that are different instances with identical contents.
4. **Comparing via `toString()`:** string representation is for display, not an equality contract. Two different data types may produce similar strings; some elements have `toString` implementations unsuitable for identity.
5. **Comparing hashes alone:** having the same `hashCode` does not prove `equals` is `true`.
6. **Writing custom `List` `equals` but forgetting symmetry/type rules:** an `ArrayList` and a custom list with the same sequence must obey the `List` contract; a custom implementation bug can cause the two directions to produce different results.
7. **Using `List.of` with `null`:** this factory forbids `null`, even though many other implementations allow it.
8. **Assuming `List.copyOf` makes all child objects immutable:** the copy is unmodifiable at the list level, but mutable elements can still be modified.
9. **Comparing two lists while they are being concurrently modified:** if the collection is not properly synchronized, unstable results or exceptions may occur; you must take a stable snapshot or use an appropriate coordination mechanism before comparing.

If an element object implements `equals` in violation of its contract (for instance, lacking symmetry or transitivity), list-level comparison may also exhibit inconsistencies. `List.equals` **relies on** element `equals` and does not automatically fix element-level bugs.

## 10. Checklist and Self-Check

Before deciding whether two lists are equal, ask:

- Do they have the same number of elements? `[]` differs from `[null]`.
- Does each index have a pair of elements that are equal according to `equals`?
- Do element repetition and position of appearance matter to the business logic?
- Do the elements define an appropriate `equals`, especially for custom classes or arrays?
- Do you need to compare possibly `null` `List` references? If so, use `Objects.equals` for the **list references**.
- Can the list or its elements be mutated? If used as a hash key, stability must be guaranteed.
- Is the true requirement "same ordered sequence" or "same set of elements"? Choose `List.equals` or `Set.equals` according to **business semantics**.

**Self-practice questions:**

1. What does `List.of(1, 2, 1).equals(List.of(1, 1, 2))` return? Why?
2. What does `new ArrayList<>(List.of("a")).equals(new LinkedList<>(List.of("a")))` return?
3. Do two `List` instances of the same size and same hash necessarily have `equals == true`?
4. Are `[null, "x"]` and `["x", null]` equal if both implementations allow `null`?
5. Why does `List<int[]>` usually not compare the contents of each array as expected?
6. Can swapping two elements change `List.hashCode`? Must every swap produce a different hash?
7. Why might a `List.copyOf` containing mutable elements still be unsuitable as a hash key?
8. When an application does not care about order but needs to eliminate duplicate elements, should it represent the data with a `List` or a `Set`?

**Takeaway:** `List.equals()` compares **length and each pair of elements at the same index**, independent of implementation. **Both order and occurrence count matter.** `List.hashCode()` is also computed by order, so keep equality-relevant data stable when using lists in hash structures.