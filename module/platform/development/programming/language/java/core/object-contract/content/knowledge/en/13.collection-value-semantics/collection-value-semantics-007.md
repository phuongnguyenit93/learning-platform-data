# Array Elements in a Collection Still Use Array Equality

## 1. What Happens When You Put an Array into a Collection?

In Java, `List`, `Set`, and `Map` typically use the `equals()` or `hashCode()` methods of element or key objects to determine whether two values are equivalent. **A Collection does not automatically change an array element's comparison rule to element-by-element comparison inside the array.**

Consider two independent arrays:

```java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

System.out.println(a == b);             // false
System.out.println(a.equals(b));        // false
System.out.println(Arrays.equals(a, b)); // true
```

*This is an illustrative snippet placed inside a method with `import java.util.Arrays;`. The full program is in Section 6.*

Even though `a` and `b` contain the same integers in the same order, they are **two different array objects**. Java arrays **do not override `Object.equals()` to compare contents**. Therefore:

- `a == b` is `false` because the references differ.
- `a.equals(b)` is also `false` because it inherits reference comparison from `Object`.
- `Arrays.equals(a, b)` is `true` because this utility method **actively compares each corresponding element**.

This is the common trap: when an array becomes an element of a `Collection`, it **remains an array object with default array equality**, rather than being turned into a value object by the Collection. Same data does not mean equal elements under array `equals()`.

> **Quick rule to remember:** A Collection uses its elements' equality contract. If an element is a Java array, default equality is by array identity; to compare contents, you must choose a dedicated representation or algorithm.

## 2. Difference Between Arrays and Collections with Regular Elements

Two `List<Integer>` instances with identical numeric elements in the same order are normally `equals()` because `Integer.equals()` compares numeric values:

```java
List<Integer> numbers1 = List.of(1, 2, 3);
List<Integer> numbers2 = List.of(1, 2, 3);

System.out.println(numbers1.equals(numbers2)); // true
```

However, with a **List containing array elements**:

```java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

List<int[]> list1 = List.of(a);
List<int[]> list2 = List.of(b);

System.out.println(list1.equals(list2)); // false
System.out.println(list1.contains(b));   // false
System.out.println(list1.contains(a));   // true
```

*The snippets above illustrate code inside a method with `import java.util.List;`.*

Reason: the `List.equals()` contract requires both lists to have the same number of elements, and **the pair of elements at each position must be equal**. When the element type is `int[]`, element comparison calls the array's `equals()`. `list1` holds `a` while `list2` holds `b`, so they differ even though `Arrays.equals(a, b)` is `true`.

`List.contains(o)` also uses the equality relation to search for an element. A new array object with the same contents is not automatically recognized as the old element. Conversely, the same reference `a` is recognized.

| Expression | Meaning | For Two Independent Arrays `a` and `b` with Same Content |
| --- | --- | --- |
| `a == b` | Same reference? | `false` |
| `a.equals(b)` | Default array equality? | `false` |
| `Arrays.equals(a, b)` | Corresponding one-dimensional contents equal? | `true` |
| `List.of(a).equals(List.of(b))` | Lists have equal elements under `equals()`? | `false` |
| `List.of(a).contains(b)` | Contains an element equal to `b` under default equality? | `false` |
| `List.of(a).contains(a)` | Contains the same array object `a`? | `true` |

Distinguish **an array as a Collection element** from **data converted into value elements of a Collection**:

- `List<int[]>` holds arrays as element objects.
- `List<Integer>` holds individual `Integer` objects; each `Integer`'s equality is by value.
- `List<List<Integer>>` compares inner lists via `List.equals()`, provided the inner elements have appropriate equality.

A Collection has no built-in concept of "unwrapping arrays at arbitrary depth and comparing values".

## 3. Impact on List, Set, and Map

### 3.1. List: equals, contains, indexOf, remove

An `ArrayList<int[]>` or `List<int[]>` uses array equality when checking `contains()` or finding an index via `indexOf()`. Calling `remove(Object)` with a new array holding identical contents also fails to remove the stored array, because no equal element is found under array rules.

```java
List<int[]> rows = new ArrayList<>();
int[] oldRow = {10, 20};
rows.add(oldRow);

System.out.println(rows.contains(new int[]{10, 20})); // false
System.out.println(rows.indexOf(oldRow));               // 0
System.out.println(rows.remove(new int[]{10, 20}));     // false
```

*This is an illustrative snippet inside a method with `import java.util.ArrayList;` and `import java.util.List;`. `List`'s `remove(Object)` returns `boolean`, unlike `remove(int index)`.*

### 3.2. HashSet: Does Not Deduplicate Arrays with Identical Contents

`HashSet` relies on element `hashCode()/equals()`. Array objects inherit `hashCode()` and `equals()` from `Object`, so two arrays with different references are treated as **two distinct elements**, even when all inner elements are equal.

```java
Set<int[]> set = new HashSet<>();
set.add(new int[]{1, 2});
set.add(new int[]{1, 2});

System.out.println(set.size()); // 2
```

Do not infer from `Arrays.equals(first, second)` being `true` that `HashSet<int[]>` will treat them as duplicates. Even if two objects happen to share a hash value, that does not merge them into one element: `HashSet` still checks equality. On the other hand, adding the **exact same array instance** twice keeps only one element in `HashSet`.

### 3.3. HashMap: Arrays Used as Keys Are Still Compared by Identity

With `HashMap<int[], String>`, a new key array with identical contents generally cannot look up a mapping stored under another array:

```java
Map<int[], String> map = new HashMap<>();
int[] key = {1, 2};

map.put(key, "stored");

System.out.println(map.get(new int[]{1, 2})); // null
System.out.println(map.get(key));              // stored
```

*Illustrative snippet using `java.util.Map` and `java.util.HashMap`.*

This still conforms to the `HashMap` contract: the new key does not equal the old key under array `equals()`. To make the map use **the array's value as identity**, wrap the array data in a key type defining content-based `equals()/hashCode()`, or convert the array into another key type with clear value semantics.

If the array is a **value** rather than a key, such as `Map<String, int[]>`, whether `get("id")` succeeds depends on `String` as the key. However, comparing two `Map<String, int[]>` instances with `Map.equals()` still checks `equals()` of the corresponding **values**; two value arrays with different references and identical contents will not automatically be considered equal.

## 4. Which `Arrays` Methods Actually Compare Contents?

`java.util.Arrays` provides explicit comparison operations for arrays:

| Method | Applicable Scenario | Key Point to Remember |
| --- | --- | --- |
| `Arrays.equals(int[], int[])` and primitive overloads | Comparing two 1D primitive arrays | Compares elements at matching positions using rules for that data type. |
| `Arrays.equals(Object[], Object[])` | Comparing 1D object arrays | Compares each element using its equality; if an element **is itself an array**, it still defaults to inner array identity. |
| `Arrays.deepEquals(Object[], Object[])` | Comparing nested object arrays, including subarrays | When encountering a subarray, recurses by content; suitable for many multidimensional array cases. |
| `Arrays.hashCode(array)` | Computing 1D content-based hash | Must pair with the matching `Arrays.equals(...)` when creating a value key type. |
| `Arrays.deepHashCode(Object[])` | Hash based on nested array contents | Pairs with `Arrays.deepEquals(...)` when choosing deep equality policy. |
| `Arrays.toString(array)` | Printing a 1D array readably | Representation only; does not define equality. |
| `Arrays.deepToString(Object[])` | Printing nested arrays readably | Also for representation only; does not alter equality. |

For example, a two-dimensional array in Java is actually an **array of arrays**, so:

```java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};

System.out.println(Arrays.equals(a, b));     // false
System.out.println(Arrays.deepEquals(a, b)); // true
```

Here `Arrays.equals(a, b)` resolves to the `Object[]` overload because `int[][]` is an array of `int[]` elements. The two independent `int[]` elements are not equal under `Object.equals()`. `Arrays.deepEquals(a, b)` recognizes the subarrays and compares their corresponding primitive contents.

Note the differences among the cases:

- `Arrays.equals(new int[]{1,2}, new int[]{1,2})` → `true`.
- `Arrays.equals(new int[][]{{1}}, new int[][]{{1}})` → `false` because it compares the two subarrays by reference.
- `Arrays.deepEquals(new int[][]{{1}}, new int[][]{{1}})` → `true`.

If you only handle one-dimensional primitive arrays, `Arrays.equals()` is the direct, clear choice. For nested arrays, use `deepEquals` when business semantics genuinely require comparing contents across levels. The `Arrays.equals` methods do not turn arrays into objects with content-based `equals()` for other code to use.

## 5. Why Wrapping with `List.of`, `Arrays.asList`, or `List.copyOf` Is Not Enough

A common mistake is thinking that simply placing arrays inside an unmodifiable list turns array equality into content-based equality. In reality:

```java
int[] a = {1, 2};
int[] b = {1, 2};

List<int[]> first = List.of(a);
List<int[]> second = List.of(b);

System.out.println(first.equals(second)); // false
```

`List.of(...)` creates a structurally unmodifiable list; it **does not deep-copy array elements** and does not override `int[]`'s methods. If `a[0]` is modified, the contents of the array stored inside `first` also change. Similarly, `List.copyOf(...)` creates a structurally unmodifiable list of the source's elements, yet can still hold mutable objects.

`Arrays.asList(...)` also causes confusion with primitive arrays. Specifically:

```java
List<int[]> oneElement = Arrays.asList(new int[]{1, 2, 3});
System.out.println(oneElement.size()); // 1
```

This is a list **with one element of type `int[]`**, not a `List<Integer>` with three elements. A primitive `int[]` is not automatically unpacked and boxed into three `Integer` objects for this varargs call.

For a reference array `String[]`, `Arrays.asList(stringArray)` normally creates a list of `String` elements because `String[]` matches the `T...` varargs parameter directly. The two cases behave very differently, so always check the generic type and exact meaning of the data.

If you want a `List<Integer>` from `int[]`, you can box explicitly:

```java
int[] source = {1, 2, 3};
List<Integer> values = Arrays.stream(source)
        .boxed()
        .toList();

System.out.println(values.equals(List.of(1, 2, 3))); // true
```

In Java 17+, `Stream.toList()` creates a structurally unmodifiable list. The elements are now `Integer`, so element equality checks values. This conversion changes the data model and incurs boxing overhead; use it only when you truly need a value-based list of integers.

## 6. Complete, Standalone Runnable Java 17+ Program

The program demonstrates a concrete sequence of behaviors: array identity, `List.contains()`, `HashSet`, `HashMap`, nested array comparison, the `Arrays.asList` distinction, and a **content-comparing wrapper**.

Create the file `ArrayCollectionEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ArrayCollectionEqualityDemo {

    // Value wrapper: protects snapshot and defines content-based equality.
    record IntArrayKey(int[] values) {
        IntArrayKey {
            Objects.requireNonNull(values, "values");
            values = Arrays.copyOf(values, values.length);
        }

        @Override
        public int[] values() {
            return Arrays.copyOf(values, values.length);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof IntArrayKey that
                    && Arrays.equals(values, that.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(Arrays.equals(a, b));

        List<int[]> listA = List.of(a);
        List<int[]> listB = List.of(b);
        System.out.println(listA.equals(listB));
        System.out.println(listA.contains(b));
        System.out.println(listA.contains(a));

        Set<int[]> rawSet = new HashSet<>();
        rawSet.add(a);
        rawSet.add(b);
        System.out.println(rawSet.size());
        System.out.println(rawSet.contains(new int[]{1, 2, 3}));

        Map<int[], String> rawMap = new HashMap<>();
        rawMap.put(a, "stored");
        System.out.println(rawMap.get(b));
        System.out.println(rawMap.get(a));

        int[][] nested1 = {{1, 2}, {3}};
        int[][] nested2 = {{1, 2}, {3}};
        System.out.println(Arrays.equals(nested1, nested2));
        System.out.println(Arrays.deepEquals(nested1, nested2));

        System.out.println(
                List.of(1, 2, 3).equals(List.of(1, 2, 3)));
        System.out.println(Arrays.asList(new int[]{1, 2, 3}).size());

        List<IntArrayKey> valueList = List.of(new IntArrayKey(a));
        System.out.println(valueList.contains(new IntArrayKey(b)));

        Set<IntArrayKey> valueSet = new HashSet<>();
        valueSet.add(new IntArrayKey(a));
        valueSet.add(new IntArrayKey(b));
        System.out.println(valueSet.size());

        Map<IntArrayKey, String> valueMap = new HashMap<>();
        valueMap.put(new IntArrayKey(a), "number-sequence");
        System.out.println(valueMap.get(new IntArrayKey(b)));

        int[] source = {5, 6};
        IntArrayKey snapshot = new IntArrayKey(source);
        source[0] = 9;               // Mutate input after constructor.
        int[] exported = snapshot.values();
        exported[0] = 10;            // Mutate array returned from accessor.
        System.out.println(Arrays.toString(snapshot.values()));
    }
}
```

Compile and run:

```bash
javac ArrayCollectionEqualityDemo.java
java ArrayCollectionEqualityDemo
```

Stdout in exact order:

```text
false
false
true
false
false
true
2
false
null
stored
false
true
true
1
true
1
number-sequence
[5, 6]
```

Explanation of results:

1. The first three lines show respectively that the two array instances differ, array `Object.equals()` still compares references, whereas `Arrays.equals` compares contents and returns `true`.
2. `listA.equals(listB)` and `listA.contains(b)` are both `false` because array elements `a` and `b` are not `equals()`. `listA.contains(a)` is `true` because it is the same object.
3. `rawSet.size() == 2`: identical contents are not deduplicated when elements are two distinct array objects. Searching with a new array continues to fail.
4. `rawMap.get(b)` is `null` while `rawMap.get(a)` is `stored`: using a raw array as a `HashMap` key defaults to **array identity**, not contents.
5. For two 2D arrays, `Arrays.equals` yields `false` because the subarrays have different references; `Arrays.deepEquals` yields `true` because nested contents match.
6. Two `List<Integer>` instances with the same value sequence are equal; `Arrays.asList(new int[]{...})` still has only one `int[]` element.
7. `valueList.contains(new IntArrayKey(b))` is `true`: the wrapper provides content-based equality. `valueSet.size()` is `1` because the two wrappers have the same key content. Looking up `valueMap` with a newly created wrapper succeeds.
8. `snapshot` still prints `[5, 6]` even though the input array was mutated and the array returned by the accessor was mutated: the wrapper actively performs **defensive copying** both on input and on output.

The output does not depend on specific numeric values of `Object.hashCode()`, because the program prints neither identity hashes nor `HashSet` iteration order.

## 7. Building a Proper Value Wrapper: equals, hashCode, and Immutability

When you genuinely need an array **as a value key**, a wrapper class is usually clearer than trying to use `int[]` directly. `IntArrayKey` in the program has three responsibilities:

**(1) Content-based equality:** `Arrays.equals(values, that.values)` determines whether two keys have the same sequence of numbers and order.

**(2) Compatible hash:** `Arrays.hashCode(values)` reflects contents consistently with `Arrays.equals(...)`. If two wrappers are equal, they have the same hash. Never override `equals()` alone while keeping `Object`'s default hash.

**(3) Stable snapshot:** the constructor calls `Arrays.copyOf(...)` to prevent external code from mutating the passed-in array, and the accessor also returns a copy. If you only have `private final int[] values` yet store the input array directly, external code can still alter its elements. When used as a `HashMap` key or `HashSet` element, mutable contents changing the hash can break lookup operations.

A plain `record` such as:

```java
record BadArrayKey(int[] values) {}
```

**does not automatically get content-based array equality**. A record computes equality across its components by default, yet an array component is still compared using array equality; `new BadArrayKey(new int[]{1,2})` and another `BadArrayKey` holding a separate `{1,2}` array are not automatically equal. A `record` also does not automatically deep-copy referenced objects. When using a record as a wrapper, override compatible `equals()/hashCode()` and protect mutable data as in the full example.

### Object Arrays, Nested Arrays, and General Wrappers

If an array contains `String` or value objects with proper `equals()`, using `Arrays.equals(Object[], Object[])` can suffice because it compares each element using element equality.

If each element is itself an array, `Arrays.equals(Object[], Object[])` will still compare subarray identity. When the problem requires comparing the entire nested structure, consider pairing `Arrays.deepEquals` and `Arrays.deepHashCode`. Determine beforehand whether order and `null` distinction at each level matter; `deepEquals` is not a universal policy for arbitrary object graphs.

If array elements are other mutable objects, even if the wrapper runs `Arrays.copyOf` on the outer array, **the inner referenced elements remain shared**. To get a truly stable snapshot, apply defensive copying or immutable design to elements that affect equality/hash. Java has no built-in mechanism to automatically deep-copy every object graph.

## 8. When Is Array Identity Fine, and When Is Value Comparison Needed?

Using an array as a Collection element or key is not always wrong. The decision depends on what the data means:

| Need | Approach |
| --- | --- |
| Tracking **the specific array instance** as a buffer or dedicated resource | Keeping the array reference directly may be appropriate, because identity is desired. |
| Only needing to print or compare two independent arrays once | Use `Arrays.toString` or `Arrays.equals`/`Arrays.deepEquals` directly, without a wrapper. |
| `List` holding number sequences where `contains` should match a different instance with the same contents | Use a value wrapper or represent as `List<Integer>` if the model and boxing cost fit. |
| `HashSet` needing to deduplicate arrays with identical contents | Wrap in a type with content-based equality/hash and a stable snapshot. |
| `HashMap` using an array as a logical key | Use an immutable wrapper with matching `equals()` and `hashCode()`, or encode the key as a suitable value type. |
| Multi-level array structures needing deep comparison | Pair `Arrays.deepEquals/deepHashCode` when appropriate for the required semantics. |

One way to convert `int[]` into `List<Integer>` in Java 17+ is:

```java
int[] input = {1, 2, 3};

List<Integer> values = Arrays.stream(input)
        .boxed()
        .toList();

System.out.println(values.equals(List.of(1, 2, 3))); // true
```

*Illustrative snippet inside a method with `Arrays` and `List` imported.* This is a **model conversion from a primitive array to a list of boxed elements**, not changing the equality of `int[]`. It has boxing and collection memory overhead, so weigh it against your goal. If you need to process a primitive sequence without Collection semantics, continuing to use arrays and `Arrays.equals` may be simpler.

## 9. Common Mistakes

**Mistake 1 — Thinking `Collection.equals()` automatically deep-compares all element types.** Collection equality normally delegates to each element's equality. For array elements of different instances, default `equals()` does not compare contents.

**Mistake 2 — Using `array.toString()` to build keys.** Arrays typically produce a string showing class/type name and hash, not contents like `Arrays.toString(array)`. Even when using `Arrays.toString` for printing, do not casually treat formatted strings as keys instead of a value type with a clear contract.

**Mistake 3 — Using `Arrays.equals` on multidimensional arrays and assuming deep comparison.** For `int[][]`, the outer elements are `int[]`, so `Arrays.equals` only checks default equality of the subarrays. To compare nested values, use `Arrays.deepEquals`.

**Mistake 4 — Wrapping an array in a `record` and assuming content equality.** Record equality still uses each component's semantics, and an array component is a reference type with identity equality. For content equality, override `equals()/hashCode()` properly.

**Mistake 5 — Forgetting the wrapper's `hashCode`.** `HashSet` and `HashMap` rely on both `hashCode` and `equals`. A wrapper with content equality but identity hash breaks the contract and causes lookups to fail.

**Mistake 6 — Only marking the array field `final`.** `final` prevents reassigning another array to the field, not `values[0] = ...`. If contents participate in hashing, protect the snapshot.

**Mistake 7 — Confusing `Arrays.asList(int[])` with `List<Integer>`.** It creates a list with a single `int[]` element. To treat each integer as a Collection element, explicit boxing/conversion is required.

**Mistake 8 — Treating all Map types identically under `equals()`.** `IdentityHashMap` intentionally uses identity; `TreeMap` determines key equivalence via `Comparator`/`Comparable`; this lesson covers standard collections/maps using element/key equality contracts, especially `List`, `HashSet`, and `HashMap`.

## 10. Self-Check

**Q1.** Are two separate `int[]` arrays both containing `{4,5}` equal under `Object.equals()`?  
**Answer:** No. Arrays use reference equality by default; `Arrays.equals` is what compares 1D contents.

**Q2.** Can `new HashSet<int[]>()` adding two new arrays with identical data end up with `size() == 1` because of duplicate contents?  
**Answer:** No. Since both are separate instances, the Set treats them as two distinct elements; `size() == 2`.

**Q3.** What does `List.of(new int[]{1}).equals(List.of(new int[]{1}))` return?  
**Answer:** `false`, because each list has one element that is an array with a different reference.

**Q4.** How do `Arrays.deepEquals` and `Arrays.equals` differ for `int[][]`?  
**Answer:** `Arrays.equals` compares each subarray using default array equality, whereas `deepEquals` recurses into the contents of subarrays.

**Q5.** Does Java automatically generate content-based array equality for a record with an `int[]` component?  
**Answer:** No. You must define equality/hash using `Arrays.equals/Arrays.hashCode` and protect immutability if used as a key.

**Q6.** What should you do if you want to look up a `HashMap` using an array of a different instance with the same contents?  
**Answer:** Use an immutable value wrapper with content-based `equals()` and `hashCode()`, or convert the key representation to an appropriate value type; do not use `int[]` directly when content equality is needed.

**Q7.** Why must a wrapper copy the array in both the constructor and accessor when its contents are used as a key?  
**Answer:** So external code cannot alter values participating in equality/hash while the object resides in a hash collection.

Point to remember: **A Collection obeys the equality contract of its element objects. Java arrays themselves use identity equality; `Arrays.equals/deepEquals` compares contents only when you call it explicitly.** If business logic requires separate array instances with identical contents to be treated as the same value in a `List`, `Set`, or `Map`, represent them with a key or element type that has content-based equality and a compatible hash.