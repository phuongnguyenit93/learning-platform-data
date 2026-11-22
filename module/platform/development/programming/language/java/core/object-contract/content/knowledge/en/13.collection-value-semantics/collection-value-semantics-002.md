# `Set.equals()` Compares the Same Elements, Independent of Iteration Order

## 1. Core Rule of `Set.equals()`

In Java, `java.util.Set` represents a collection containing **no duplicate elements under the equality relation used by the structure**. The `Set.equals(Object)` contract defines two sets as equal when:

1. The object being compared is also a `Set`.
2. Both sets have the **same number of elements** (`size()`).
3. **Every element** of one set is contained in the other set, according to how valid sets determine element membership.

Insertion order, `iterator()` traversal order, and the specific implementation type are **not criteria** of this contract.

Conceptual example:

```text
{ "Java", "Kotlin", "Scala" }
{ "Scala", "Java", "Kotlin" }
→ Set.equals(): true (same 3 elements, even though listed in a different order)

{ "Java", "Kotlin", "Scala" }
{ "Java", "Kotlin" }
→ Set.equals(): false (different number of elements)
```

The notation in the block above is a **set illustration**, not Java `Set` initialization syntax.

**Distinction from `List`:** `List.equals()` requires the same size and that corresponding elements at **the exact same position** are equal. Therefore, two lists with the same elements in swapped positions are usually not equal, whereas two `Set` instances containing the same elements will be equal.

## 2. `HashSet`, `LinkedHashSet`, and `TreeSet` Have Different Iteration Orders but Can Still Be Equal

Three common implementations:

| Implementation | Iteration Behavior | When Compared with `equals()` |
| --- | --- | --- |
| `HashSet` | **No guarantee** on iteration order | Compares membership and size, without relying on iteration order |
| `LinkedHashSet` | Typically iterates in **insertion order** | Still applies the position-independent `Set.equals()` contract |
| `TreeSet` | Iterates in **sorted order** (natural order or `Comparator`) | Must still obey the `Set` contract when the ordering is **consistent with `equals`** |

With non-`null` `String` elements and standard natural ordering, a `HashSet`, a `LinkedHashSet`, and a `TreeSet` can be equal if they contain the same strings. For example, the iteration order observed across the three sets may differ while `equals()` still returns `true`.

Do not infer the iteration order of `HashSet` from machine output or hash function details. Java does not guarantee that `HashSet` iterates in insertion order, lexicographical order, or a stable order after operations that modify the set.

## 3. Runnable Java 17+ Program

Save the following code to `SetEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class SetEqualityDemo {
    record Tag(String code) {}

    public static void main(String[] args) {
        Set<String> hash = new HashSet<>(
                List.of("Java", "Kotlin", "Scala"));
        Set<String> linked = new LinkedHashSet<>(
                List.of("Scala", "Java", "Kotlin"));
        Set<String> sorted = new TreeSet<>(
                List.of("Kotlin", "Scala", "Java"));

        System.out.println("hash.equals(linked): " + hash.equals(linked));
        System.out.println("linked.equals(sorted): " + linked.equals(sorted));
        System.out.println("same set hashCode: "
                + (hash.hashCode() == linked.hashCode()));
        System.out.println("List order matters: "
                + List.of("Java", "Kotlin")
                        .equals(List.of("Kotlin", "Java")));
        System.out.println("missing an element: "
                + hash.equals(Set.of("Java", "Scala")));
        System.out.println("Set vs List: "
                + hash.equals(List.of("Java", "Kotlin", "Scala")));

        Set<Integer> unique = new HashSet<>(Arrays.asList(1, 2, 2, 3));
        System.out.println("unique.size(): " + unique.size());
        System.out.println("integer set hashCode: "
                + Set.of(1, 2, 3).hashCode());

        Set<String> withNull = new HashSet<>(
                Arrays.asList(null, "Java"));
        Set<String> nullInOtherOrder = new LinkedHashSet<>(
                Arrays.asList("Java", null));
        System.out.println("sets with null: "
                + withNull.equals(nullInOtherOrder));

        Set<Tag> firstTags = Set.of(new Tag("A"), new Tag("B"));
        Set<Tag> secondTags = new LinkedHashSet<>(
                List.of(new Tag("B"), new Tag("A")));
        System.out.println("record member equality: "
                + firstTags.equals(secondTags));

        Set<String> absent = null;
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(absent, null));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SetEqualityDemo.java
java SetEqualityDemo
```

Expected output, independent of `Set` iteration order:

```text
hash.equals(linked): true
linked.equals(sorted): true
same set hashCode: true
List order matters: false
missing an element: false
Set vs List: false
unique.size(): 3
integer set hashCode: 6
sets with null: true
record member equality: true
Objects.equals(null, null): true
```

Explanation:

- `hash`, `linked`, and `sorted` contain the same three string values, so they are equal regardless of insertion or iteration order.
- Two `List` instances containing `"Java"` and `"Kotlin"` in opposite orders are **not equal**.
- A `Set` is not equal to a `List`, even when the exact same values appear: the condition that the other object must be a `Set` is not satisfied.
- `new HashSet<>(Arrays.asList(1, 2, 2, 3))` drops the duplicate `2`; the result has only three distinct elements.
- `HashSet` and `LinkedHashSet` allow a single `null` element; the position at which `null` is added does not change equality. Do not generalize `null` support to all `Set` implementations.
- `Tag` is a Java `record`, automatically providing `equals()`/`hashCode()` based on the `code` field. Two distinct `new Tag("A")` objects are still **equal by value**; two sets containing equivalent tags are considered equal.

## 4. Visualizing the Set Comparison Algorithm

In terms of rules, comparing two valid `Set` instances can be expressed as pseudocode:

```text
if (this == other)                 return true
if (!(other instanceof Set))      return false
if (this.size() != other.size())   return false
return this contains every element of other
```

This is **contract-illustrating pseudocode**, not mandatory source code for every implementation. In Java, membership checking typically uses `contains(...)`; `HashSet` relies on the element's `hashCode()` and `equals()` values, while `TreeSet` searches using the ordering relation provided by `compareTo`/`Comparator`.

The **same size** condition is necessary: checking `containsAll(...)` in only one direction would give the wrong result when a larger set contains an entire smaller set. Likewise, iterating over elements to put them into a `List` and then comparing the two lists with `equals` is also wrong because it accidentally introduces order into set criteria.

## 5. `Set.hashCode()` Is Also Independent of Iteration Order

The `Set.hashCode()` contract is defined as the **sum of `hashCode()` of all elements in the set**; a `null` element contributes `0` if allowed to exist. Addition happens in `int` arithmetic and may overflow. Because addition is order-independent, sets containing the same elements produce the same hash code, even if their iteration orders differ.

For example, `Set.of(1, 2, 3).hashCode()` returns `1 + 2 + 3 = 6`, because `Integer.hashCode(int)` returns the `int` value itself.

The mandatory rule remains:

```text
s1.equals(s2) == true  =>  s1.hashCode() == s2.hashCode()
s1.hashCode() == s2.hashCode()  =/=>  s1.equals(s2) == true
```

The reverse direction does not hold because hash code collisions can occur. For instance, two different integer sets `{1, 4}` and `{2, 3}` both have a hash code of `5`, yet they are **not equal** because they do not contain the same elements.

You must never write a set comparison by **only** comparing `hashCode()`. Hash codes assist lookup; they do not replace membership checking.

## 6. `Set` Equality Depends on Element Equality

Two `Set` instances can contain objects from two different memory regions and still be equal if the corresponding elements are **equal according to `equals()`** and their hash functions are consistent.

See the `record` example in the program above. For a regular custom class, you must override `equals()` and `hashCode()` consistently according to the exact data that identifies an element. Otherwise, the default `Object.equals()` checks object identity, causing two elements that look identical not to be recognized as equal.

Cases to distinguish:

- `Set.of(1).equals(Set.of(1L))` returns `false`: `Integer(1)` and `Long(1)` are not equal according to `equals()`, even though they have the same mathematical value.
- Two sets with the same number of elements but containing different values return `false`.
- Implementations with a valid `Set` contract do not require both sides to use the same concrete type; for example, a `HashSet` can still be compared with a `LinkedHashSet`.
- Placing an element whose `equals()`/`hashCode()` **depends on a mutable property** into a `HashSet`, and then modifying that property, can cause `contains()`/`remove()` to fail to find the element again. Prefer immutable elements when using hash structures.

## 7. Important Design Exception: `TreeSet` and `Comparator`

`TreeSet` uses `compareTo()` or `Comparator.compare()` to determine sorting position and detect duplicate elements in the tree. To fully satisfy the `Set` contract, **the comparison relation returning `0` must be consistent with `equals()`** of the element.

For example, `String.CASE_INSENSITIVE_ORDER` treats `"java"` and `"JAVA"` as equal in ordering (`compare(...) == 0`), whereas `"java".equals("JAVA")` is `false`. A `TreeSet<String>` using this comparator will retain only one of the two strings, unlike a standard `HashSet`.

```java
TreeSet<String> insensitive = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
insensitive.add("java");
insensitive.add("JAVA");
System.out.println(insensitive.size()); // 1
```

The code snippet above is an **illustration inside a Java method**, requiring `import java.util.TreeSet` or the fully qualified name. Using a comparator inconsistent with `equals` can make comparison results between different `Set` types unexpected, and even violate the expected symmetry of `Set.equals`. Therefore, do not mechanically apply the conclusion "same elements" when each structure is using **a different element identity relation**.

With `TreeSet` using the natural ordering of `String` as in the complete runnable example, `compareTo()` is consistent with `String.equals()`, so this issue does not occur.

## 8. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| If two sets are iterated in different orders, `equals()` must be `false` | `Set.equals()` ignores iteration order |
| `LinkedHashSet` preserves insertion order, so `equals()` also checks insertion order | Order is only an iteration property; the equality contract is still the `Set` contract |
| `HashSet` does not preserve order, so the `equals()` result is random | `equals()` has clear rules, independent of iteration order when elements and contracts are implemented properly |
| Two sets of the same size are equal | They need the **same elements**, not just the same count |
| Two sets with the same `hashCode()` are equal | Hash codes can collide; `equals()`/membership checking is required |
| Using `List.equals()` after converting a `Set` to a `List` | Wrong if iteration orders differ, especially with `HashSet` |
| Any `TreeSet` and `HashSet` containing "similar" strings are equal | The comparator in `TreeSet` must be consistent with `equals()` to preserve the set contract |
| Every `Set` accepts `null` | `HashSet` allows it, whereas `Set.of(...)` and `TreeSet` with natural ordering usually reject `null` |

Do not confuse two operations: **comparing `Set` contents** and **comparing iteration order**. If the problem needs to preserve positions, use a `List`; if it needs to check the same elements without caring about position, use a `Set` and an equality relation that matches the data domain.

## 9. Self-Check Questions

1. What does `new HashSet<>(List.of("A", "B")).equals(new LinkedHashSet<>(List.of("B", "A")))` return? **`true`**, because they have the same elements.
2. Are two `Set` instances both of size 3 guaranteed to be equal? **No**, membership of each element must still be checked.
3. Are two equal `Set` instances allowed to have different hash codes? **No**, they must satisfy the `hashCode()` contract.
4. Are two unequal `Set` instances allowed to have the same hash code? **Yes**, that is a collision.
5. Can a case-insensitive `TreeSet` have different membership semantics from `HashSet<String>`? **Yes**, because the comparator may be inconsistent with `String.equals()`.

**Takeaway:** Two `Set` instances are equal when they have **the same size and the same elements under the `Set` contract**, independent of insertion or iteration order. Ensure element `equals()`/`hashCode()` and any `Comparator` (if using `TreeSet`) are consistent with the intended equality relation.