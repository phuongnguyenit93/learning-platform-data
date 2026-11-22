# equals Semantics of List, Set, and Map

Two collections containing values that look alike are not necessarily equal. Java defines equality according to the structure's **data model**:

- `List` is an ordered sequence of elements.
- `Set` is a set of members with no duplicate occurrences.
- `Map` is a set of mappings from keys to values.

Therefore, "equal" must answer a different question in each group. Two lists need to have the same order; two sets do not need the same iteration order; two maps need the same key–value pairs rather than just the same keys or the same values.

This article presents the general contracts of `List`, `Set`, and `Map`, with examples for Java 17 and above. The conclusions assume that element, key, and value types have valid equality rules; structures using special equivalence relations require reading their specific contracts.

## 1. Overview of the Three Equality Models

| Structure | When Are They Equal? | Does Order Matter? |
| --- | --- | --- |
| `List` | The other object is also a `List`, with the same number of elements and each pair at the same position equal | Yes |
| `Set` | The other object is also a `Set`, containing the same members | Iteration order is ignored |
| `Map` | The other object is also a `Map`, representing the same mappings | Entry iteration order is ignored |

Short examples:

```text
List [A, B] and List [B, A]       → not equal
Set  {A, B} and Set  {B, A}       → equal
Map  A→1, B→2 and Map B→2, A→1    → equal
Map  A→1, B→2 and Map A→2, B→1    → not equal
```

Curly brace notation in the diagram merely describes sets/maps; it is not Java literal syntax.

The two objects do not need to belong to the same concrete class: an `ArrayList` can equal a `LinkedList`; a `HashMap` can equal a `TreeMap` if they have the same mappings and compatible key rules.

## 2. List.equals: Same Length, Same Order, Same Values

### 2.1. Element-by-Position Comparison

Two lists are equal when:

1. The object being compared is also a `List`.
2. The number of elements is equal.
3. At every position, the two elements are equal according to the corresponding value rule.

```java
List<String> first =
        new ArrayList<>(List.of("A", "B", "A"));

List<String> same =
        new LinkedList<>(List.of("A", "B", "A"));

List<String> reordered = List.of("A", "A", "B");

System.out.println(first.equals(same));      // true
System.out.println(first.equals(reordered)); // false
```

This is an illustrative snippet inside a method; the `java.util` types used must be imported.

`first` and `same` store their data in two different ways but contain the same sequence of values. `reordered` contains the same values with the same occurrence counts, but at different positions, so it is not equal.

List equality does not mean "having the same set of members" or "having the same occurrence counts if order is ignored". [Java 17: List.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object))

### 2.2. Duplicate Elements Matter

```java
List<String> twice = List.of("A", "A");
List<String> once = List.of("A");

System.out.println(twice.equals(once)); // false
```

A list represents every individual occurrence. Converting to a `Set` loses this information.

Therefore, the following comparison does not check list equality:

```java
new HashSet<>(first).equals(new HashSet<>(second))
```

It is asking "do the two lists have the same distinct values", discarding both order and occurrence counts. Only use this transformation when that is the exact business requirement.

Even adding a `size` check is not enough for multiset comparison: `[A, A, B]` and `[A, B, B]` have the same size and the same set of distinct values, but different occurrence counts.

### 2.3. Modifiability Does Not Participate in Equality

```java
List<String> editable =
        new ArrayList<>(List.of("A", "B"));

List<String> unmodifiable = List.of("A", "B");

System.out.println(editable.equals(unmodifiable)); // true
```

`equals` does not ask which list supports additions/removals or which factory created it. It compares the sequence of elements.

Data can change later; two lists being equal at one point in time does not mean they remain equal forever. Adding, removing, or replacing elements can change the result.

## 3. Set.equals: Same Members, Iteration Order Ignored

### 3.1. Insertion Order and Storage Mechanism Do Not Change Set Meaning

```java
Set<String> first =
        new LinkedHashSet<>(List.of("A", "B"));

Set<String> second =
        new HashSet<>(List.of("B", "A"));

System.out.println(first.equals(second)); // true
```

`LinkedHashSet` preserves insertion order for iteration. `HashSet` makes no iteration order guarantee. However, that order does not participate in `Set.equals`.

Two sets must contain the same members. Equality cannot be concluded merely from having the same size:

```java
System.out.println(
        Set.of("A", "B").equals(Set.of("A", "C"))
); // false
```

A set does not represent duplicate occurrence counts. If the input contains `A` multiple times, once placed into a set with appropriate equality rules, only a single member `A` remains. [Java 17: Set.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#equals(java.lang.Object))

### 3.2. Identical Printed Output Does Not Make a List Equal a Set

```java
List<String> list = List.of("A", "B");
Set<String> set = new LinkedHashSet<>(list);

System.out.println(list.equals(set)); // false
System.out.println(set.equals(list)); // false
```

Lists and sets are two different models. Even though both may look like `[A, B]` when printed, they are not equal under these two contracts.

Symmetry is preserved because `List.equals` only accepts a `List` object for content comparison, while `Set.equals` only accepts a `Set`.

Do not compare collections via their `toString()` strings: display formatting and ordering cannot adequately express the structure type or its equality contract.

## 4. Map.equals: Key–Value Pairs Must Match

### 4.1. Mapping Equality Does Not Depend on Put Order

```java
Map<String, Integer> first = new LinkedHashMap<>();
first.put("A", 1);
first.put("B", 2);

Map<String, Integer> second = new TreeMap<>();
second.put("B", 2);
second.put("A", 1);

System.out.println(first.equals(second)); // true
```

The illustrative snippet requires importing the corresponding types.

The two maps represent the same mappings: `A` maps to 1 and `B` maps to 2. They do not need the same insertion order, iteration order, or implementation class.

One way the contract expresses this is that the two `entrySet` views are equal. Each entry associates a key with its corresponding value. [Java 17: Map.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object))

### 4.2. Having the Same Keys or the Same Value Set Is Not Enough

```java
Map<String, Integer> first = Map.of("A", 1, "B", 2);
Map<String, Integer> swapped = Map.of("A", 2, "B", 1);

System.out.println(first.keySet().equals(swapped.keySet())); // true
System.out.println(first.equals(swapped));                  // false
```

The two maps have the same keys and the same values 1 and 2, but paired differently.

Comparing only `keySet` checks the key domain, not the mapping content. Putting `values()` into a set for comparison also loses information about duplicate values and their relationship to keys.

For example, the map `A→1, B→1` has two mappings even though the set of distinct values has only one value. The number of mappings and the number of distinct values are two different quantities.

### 4.3. A Null Value Does Not Erase the Meaning of Its Key

For maps that support `null`:

```java
Map<String, String> first = new HashMap<>();
first.put("A", null);

Map<String, String> second = new HashMap<>();
second.put("B", null);

System.out.println(first.equals(second)); // false
```

Both have the same size and both have a `null` value, but the keys are different.

Do not hand-write a map comparison using only `other.get(key)` and treating `null` as sufficient proof of equivalence. `get` can return `null` when a key is absent; the mapping "key present with null value" differs from "key absent".

When comparing properly according to the map contract, both the presence of the key and its corresponding value must be preserved.

## 5. Each Structure's hashCode Must Match Its equals Semantics

If two objects are equal, they must have the same hash. Therefore, the interfaces specify hash calculation formulas that match their equality models.

### 5.1. List Has an Order-Dependent Hash

The list formula can be expressed as:

```java
int hash = 1;
for (Object element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
```

This is a description of the formula, not a standalone program. It does not promise that the hash is unique.

With `Integer` elements:

```text
List [1, 2]:
  start at 1
  after 1: 31 × 1 + 1 = 32
  after 2: 31 × 32 + 2 = 994
```

Order affects the accumulation. However, two different lists can still have a hash collision; do not use hash comparison as a substitute for `equals`.

### 5.2. Set Has an Order-Independent Hash

The hash of a set is the sum of the hashes of its elements; a `null` element, if supported, contributes 0.

Because addition is order-independent, two sets with the same members have the same hash even if iterated in different orders. For instance, the integer set `{1, 2}` has a total hash of 3 under the hash rules of these elements.

You cannot infer from equal hash sums that the sets are the same. `{1, 2}` and `{3}` may have the same sum while clearly having different members.

### 5.3. Map Has an Entry-Based Hash

The hash of a map is the sum of the hashes of its entries. The hash of an entry is defined by the XOR between the key hash and the value hash, using 0 for a `null` component when permitted:

```text
entryHash = keyHash XOR valueHash
mapHash   = sum of entryHash across all mappings
```

Entry iteration order does not affect the sum. Two maps equal in their mappings have the same hash.

Once again, having the same hash does not prove that the key–value pairs are equal. [Java 17: List.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()), [Set.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#hashCode()), [Map.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#hashCode()), [Map.Entry.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html#hashCode())

These formulas ensure equality across implementation classes sharing the same model. An `ArrayList` equal to a `LinkedList` must have the same hash, rather than computing a hash from its own internal storage address.

## 6. Nested Equality Follows the Type of Each Component

When an element or value is another collection, the rules apply layer by layer according to each structure.

### 6.1. Map Containing a List

```java
Map<String, List<Integer>> first =
        Map.of("scores", List.of(1, 2));

Map<String, List<Integer>> second =
        Map.of("scores", List.of(2, 1));

System.out.println(first.equals(second)); // false
```

A map ignores the iteration order of its keys, but the value at key `"scores"` is a list. That list considers element order, so the two values are not equal.

### 6.2. List Containing Sets

Two lists can be equal if each pair of sets at the same position has the same members, even if the iteration order inside the sets differs.

However, swapping the positions of two different sets within the list can still make the two lists unequal. The "order-ignoring" nature of a set does not spread outward to erase the ordering semantics of the enclosing list.

### 6.3. Set Containing Lists

In a set of lists, `[1, 2]` and `[2, 1]` are two distinct elements because lists compare by order.

The outer set does not care in what order the two lists are iterated; it still uses each list's own equality to determine membership.

Read the structure from the outside in: each layer has its own rules, and there is no default "deep compare and ignore all ordering" mode.

## 7. Arrays Inside Collections Are Not Automatically Compared by Content

A common point of surprise:

```java
int[] firstArray = {1, 2};
int[] secondArray = {1, 2};

List<int[]> first = List.of(firstArray);
List<int[]> second = List.of(secondArray);

System.out.println(first.equals(second)); // false
System.out.println(Arrays.equals(firstArray, secondArray)); // true
```

Both lists contain one element, but the elements are two distinct array objects. Arrays do not override `equals` to perform element-content comparison, and `List.equals` does not automatically call `Arrays.equals` as a substitute.

Using the primitive array `int[]` in the example also makes it clear that each array is a single element of `List<int[]>`.

If the model requires equality based on array content, you can:

- Compare explicitly with `Arrays.equals` in the appropriate check.
- Choose a value type with content-based `equals`/`hashCode`.
- Convert to an appropriate value structure such as a list of elements, if that fits the requirement.

A wrapper that overrides only `equals` by array content while keeping identity-based hashing still violates the contract. If used in a hash-based set or map, it must compute the corresponding content hash, for example via the `Arrays.hashCode` API. [Java 17: Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

"Nested" does not mean a collection automatically understands every arbitrary structure to perform deep equality.

## 8. Collection Does Not Define a Single Content Contract for All Classes

`Collection` is the root interface for many groups, but it does not impose a single content-based `equals` across all implementations.

`List` and `Set` add their own specific contracts. If a variable is declared as `Collection<String>` but the actual object is an `ArrayList`, calling `equals` still uses the list object's behavior; the declared type does not change the runtime model.

Conversely, you must not assume that every queue, deque, or arbitrary wrapper compares content like a `List`. Read the contract of the specific class.

If a custom class that is neither a `List` nor a `Set` wants to define content equality, it must take special care to preserve symmetry when compared with existing models. Do not design a class that claims to "equal any collection containing the same elements" while those collections do not consider it equal. [Java 17: Collection, equals and hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 9. Boundaries to Keep in Mind

### 9.1. Comparator Ordering Must Be Consistent with Equality When Using Tree Sets

`TreeSet` locates members using natural ordering or a comparator. If the comparator treats two elements as equivalent while `equals` treats them as different, comparing with another set can violate the expectations of the set contract.

For example, one side treats uppercase and lowercase letters as the same, while the other uses case-sensitive string equality. Do not conclude that "having the same displayed content is enough"; ensure the structures are using compatible value equivalence relations.

The `TreeSet` documentation requires the ordering to be consistent with `equals` in order to fully obey the `Set` contract. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

### 9.2. IdentityHashMap Is an Intentional Special Case

`IdentityHashMap` uses reference equality for keys and values instead of ordinary logical equality. The class documentation explicitly states that it intentionally differs from the general map contract in this respect.

Do not pass an identity-based structure into a content comparison with a regular map and assume all properties will behave equivalently. Only use that special type when the requirement is specifically tracking object identity. [Java 17: IdentityHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html)

### 9.3. Null as an Element Differs from the Absence of an Element

Two lists having `null` at the same position can be equal if the implementation accepts that data. A list containing a single `null` is not equal to an empty list.

Similarly, a set containing `null` differs from an empty set; a map with a mapping to `null` differs from a map without that mapping.

Factories such as `List.of` or `Map.of` have their own input policies. Do not attempt to create `null` data with a factory that rejects it and confuse a construction error with an `equals` result.

## 10. Mutable Data Causes Equality Results to Change

A list used as an element of a `HashSet` has a hash that depends on its content. If the program mutates the list after adding it to the set, the element's hash and equality can change.

That can prevent the hash structure from finding the element as expected. Similar risks exist with:

- Lists or sets used as map keys.
- A map used as an element in a set.
- An outer collection containing elements whose `equals`/`hashCode` depend on mutable state.
- An unmodifiable list that contains mutable element objects.

When content-based keys are needed, use a sufficiently stable value representation and protect component data as well. Merely wrapping a structure in an unmodifiable layer does not necessarily freeze all internal state.

Two collections being equal at one moment does not promise that they share the same owner, the same lifecycle, or immutable data.

Furthermore, do not invoke equality comparisons on data being modified concurrently without proper synchronization mechanisms. A single `equals` call does not automatically create a shared transactional snapshot across two structures.

Self-referential or cyclic structures should also be avoided in simple equality models: recursive comparisons or hash computations may not be well-defined or may fail to terminate as expected.

## 11. Complete Java 17 Program

Save as `CollectionEqualityDemo.java`:

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
import java.util.TreeMap;

public class CollectionEqualityDemo {
    public static void main(String[] args) {
        List<String> firstList =
                new ArrayList<>(List.of("A", "B", "A"));
        List<String> sameList =
                new LinkedList<>(List.of("A", "B", "A"));
        List<String> reordered = List.of("A", "A", "B");

        System.out.println("different list classes equal = "
                + firstList.equals(sameList));
        System.out.println("list order matters = "
                + firstList.equals(reordered));
        System.out.println("equal list hashes = "
                + (firstList.hashCode() == sameList.hashCode()));

        Set<String> firstSet =
                new LinkedHashSet<>(List.of("A", "B"));
        Set<String> secondSet =
                new HashSet<>(List.of("B", "A"));
        System.out.println("set order ignored = "
                + firstSet.equals(secondSet));
        System.out.println("equal set hashes = "
                + (firstSet.hashCode() == secondSet.hashCode()));
        System.out.println("list equals set = "
                + List.of("A", "B").equals(firstSet));
        System.out.println("set equals list = "
                + firstSet.equals(List.of("A", "B")));

        Map<String, Integer> firstMap = new LinkedHashMap<>();
        firstMap.put("A", 1);
        firstMap.put("B", 2);
        Map<String, Integer> secondMap = new TreeMap<>();
        secondMap.put("B", 2);
        secondMap.put("A", 1);
        System.out.println("different map classes equal = "
                + firstMap.equals(secondMap));
        System.out.println("equal map hashes = "
                + (firstMap.hashCode() == secondMap.hashCode()));
        System.out.println("same values wrong keys = "
                + firstMap.equals(Map.of("A", 2, "B", 1)));

        Map<String, String> nullAtA = new HashMap<>();
        nullAtA.put("A", null);
        Map<String, String> nullAtB = new HashMap<>();
        nullAtB.put("B", null);
        System.out.println("null values different keys = "
                + nullAtA.equals(nullAtB));

        Map<String, List<Integer>> nestedA =
                Map.of("scores", List.of(1, 2));
        Map<String, List<Integer>> nestedB =
                Map.of("scores", List.of(2, 1));
        System.out.println("nested list order matters = "
                + nestedA.equals(nestedB));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        List<int[]> arraysA = List.of(arrayA);
        List<int[]> arraysB = List.of(arrayB);
        System.out.println("list of distinct arrays equal = "
                + arraysA.equals(arraysB));
        System.out.println("array contents equal explicitly = "
                + Arrays.equals(arrayA, arrayB));

        List<String> editable = new ArrayList<>(List.of("A", "B"));
        System.out.println("mutability ignored by list equals = "
                + editable.equals(List.of("A", "B")));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectionEqualityDemo.java
java CollectionEqualityDemo
```

Stdout:

```text
different list classes equal = true
list order matters = false
equal list hashes = true
set order ignored = true
equal set hashes = true
list equals set = false
set equals list = false
different map classes equal = true
equal map hashes = true
same values wrong keys = false
null values different keys = false
nested list order matters = false
list of distinct arrays equal = false
array contents equal explicitly = true
mutability ignored by list equals = true
```

Labels such as `list order matters` are followed by the result of the `equals` check: `false` on that line means the two reordered lists **are not equal**.

How to read the demonstration:

1. Lists of different classes are still equal if they have the same element sequence, and they produce the same hash.
2. Reordering a list changes the comparison result.
3. Sets with the same members are equal even if their storage mechanisms and insertion orders differ.
4. A list does not equal a set in either direction.
5. Maps of different classes are equal if they have the same mappings, but swapping value pairings makes them unequal.
6. Two `null` values under two different keys do not make two maps equal.
7. A map containing a list is still subject to the list's ordering rules at the value layer.
8. Two separate arrays with the same content do not automatically make the two lists containing them equal.
9. List modifiability is not a criterion of `List.equals`.

The program does not directly compare the printed strings of unordered maps/sets. The boolean results rely on the model contracts.

## 12. Choosing the Right Comparison for Your Requirement

Before calling `equals`, state the requirement in a single sentence:

| Requirement | Approach |
| --- | --- |
| Same sequence by position and occurrence count | `List.equals` |
| Same distinct members, ignoring order and repetition count | Compare sets constructed with appropriate rules |
| Same occurrence counts, ignoring order | Build a frequency table using the desired equality relation |
| Same key-to-value mappings | `Map.equals` |
| Only the same keys are required | Compare `keySet` |
| Compare arrays by content | `Arrays.equals` API or an appropriate value type |
| Compare by specific business attributes | Explicitly designed comparator/predicate or value key |

Do not replace `equals` with comparing hashes, comparing `size`, checking one-way `containsAll`, or comparing `toString`. Each of those provides only partial information.

For example, `first.containsAll(second)` does not prove that two lists are equal: it ignores order and does not count occurrences. To perform a multiset comparison, you must track frequencies.

## 13. Common Mistakes

| Misconception | What to Remember |
| --- | --- |
| Different implementation classes cannot be equal | Classes sharing the same model can be equal under the interface contract |
| All collections with the same elements are equal | `List`, `Set`, and other groups have different contracts |
| If a Set preserves insertion order, equals also checks insertion order | A set's iteration order does not participate in `Set.equals` |
| Maps are equal when they have the same values | Each key must map to the matching value |
| Same hash means same content | Hashes can collide |
| Deduplicating and comparing as a Set works for comparing any List | Doing so loses order and occurrence counts |
| Nested collections always perform arbitrary deep comparison | Each layer uses its elements' `equals`; arrays remain a distinct case |
| An unmodifiable list has a permanently stable hash | Its internal elements may still be mutable |
| Concurrently mutating data can still be compared as an atomic snapshot | A proper consistent observation mechanism is required |
| TreeSet and HashSet always use the same equivalence relation | A comparator inconsistent with equals can break expectations |

## 14. Self-Practice

1. Is `[A, B, A]` equal to `[A, A, B]` under `List.equals`?  
   **Answer:** No, because the order differs.

2. Are two `LinkedHashSet` instances—one with A then B added, the other with B then A added—equal?  
   **Answer:** Yes, provided they contain the same two members under valid equality rules.

3. Is the map `A→1, B→2` equal to the map `A→2, B→1`?  
   **Answer:** No. Having the same key set and value set is not sufficient.

4. Are two lists, each containing a new `int[]` array with the same numbers inside, automatically equal?  
   **Answer:** No; a list does not automatically replace array `equals` with `Arrays.equals`.

5. Why must an `ArrayList` and a `LinkedList` that are equal have the same hash?  
   **Answer:** Both adhere to the same `List` equality and hashing contract; internal storage differences must not violate the requirement that equal objects have equal hash codes.

Once you understand the model properly, `equals` becomes a precise question: same sequence, same members, or same mappings. Choose that question first, then verify the equality rules of the inner components.
