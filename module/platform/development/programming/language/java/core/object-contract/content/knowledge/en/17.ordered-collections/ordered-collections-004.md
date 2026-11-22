# Differences in Results Between HashSet and TreeSet

## 1. Both are Sets, so why can results differ?

In Java, both `HashSet<E>` and `TreeSet<E>` implement the `Set<E>` interface: a collection containing no elements considered duplicates. However, they identify “duplicate” elements and organize data through different mechanisms.

- **`HashSet`** relies on `hashCode()` to identify candidate buckets and `equals(Object)` to recognize equal elements. It **does not guarantee iteration order**, even if in one run elements happen to print in a particular order.
- **`TreeSet`** is an ordered `NavigableSet` that uses **`compareTo()`** under natural ordering or a passed-in **`Comparator.compare()`**. Two elements are treated as the same element in the tree when the comparison returns **0**.

Therefore, given the same input set, the two sets can differ in **iteration order**, differ in **element count**, and differ in `contains()` or `remove()` results, especially when `compareTo`/`Comparator` is inconsistent with `equals`.

**Key point:** You cannot conclude that “HashSet and TreeSet only differ in that TreeSet sorts automatically”. How duplicate elements are recognized is also a contractual difference.

## 2. Quick comparison of the two structures

| Criterion | `HashSet` | `TreeSet` |
| --- | --- | --- |
| Organization mechanism | Hash table, backed by `HashMap` | Balanced search tree, backed by `TreeMap` |
| Duplicate detection criterion | Same reference or equal by `equals(Object)` in hashing mechanism | `compareTo == 0` or `Comparator.compare == 0` |
| Relevant contract | `equals()` and `hashCode()` must be consistent | Ordering comparison must be valid; should be consistent with `equals()` |
| Iteration order | Not guaranteed | Ascending order of natural ordering or comparator |
| Typical add, find, remove | Average near `O(1)` with well-distributed hash | `O(log n)` |
| Finding nearest element (`lower`, `floor`, `ceiling`, `higher`) | No direct API for this | Available via `NavigableSet` |
| `null` | Allows at most one `null` element | Natural ordering typically rejects `null`; a custom comparator may define handling |
| When appropriate | Need existence checks or equality-based deduplication, no ordering needed | Need data always ordered plus range and neighbor queries |

The complexities above are general assessments, not a guarantee that every operation always takes an exact constant amount of time. Actual performance also depends on data, hash collision count, and the cost of computing hash, equality, and comparator.

If you need to preserve **insertion order** rather than sort order, consider `LinkedHashSet`. It is a different option from `TreeSet`.

## 3. Simple case: integer elements with natural ordering

For standard `Integer` values, `equals()` and `compareTo()` are consistent: two integers with the same value are equal both ways. Hence both sets deduplicate identically, though iteration order may differ.

Create file `HashSetTreeSetDemo.java`:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class HashSetTreeSetDemo {
    public static void main(String[] args) {
        int[] numbers = {4, 1, 3, 2, 3};

        Set<Integer> hash = new HashSet<>();
        TreeSet<Integer> sorted = new TreeSet<>();

        for (int n : numbers) {
            hash.add(n);
            sorted.add(n);
        }

        System.out.println(hash.size());
        System.out.println(sorted.size());
        System.out.println(sorted);
        System.out.println(sorted.first());
        System.out.println(sorted.ceiling(3));
        System.out.println(sorted.higher(3));
        System.out.println(hash.contains(3));
        System.out.println(sorted.contains(3));

        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        Set<BigDecimal> decimalHash = new HashSet<>();
        Set<BigDecimal> decimalTree = new TreeSet<>();

        decimalHash.add(a);
        decimalHash.add(b);
        decimalTree.add(a);
        decimalTree.add(b);

        System.out.println(decimalHash.size());
        System.out.println(decimalTree.size());
        System.out.println(
                decimalHash.contains(new BigDecimal("2.000")));
        System.out.println(
                decimalTree.contains(new BigDecimal("2.000")));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac HashSetTreeSetDemo.java
java HashSetTreeSetDemo
```

Output:

```text
4
4
[1, 2, 3, 4]
1
3
4
true
true
2
1
false
true
```

Explanation of the first half of the program:

1. The input sequence performs five additions, where `3` repeats twice. Both sets have size **4**.
2. `sorted` prints as `[1, 2, 3, 4]` because `TreeSet<Integer>` uses ascending order of `Integer`.
3. `first()` returns the smallest element `1`; `ceiling(3)` returns the smallest element greater than or equal to 3, i.e., `3`; `higher(3)` returns the smallest element strictly greater than 3, i.e., `4`.
4. Both `contains(3)` calls return `true`.

The example **intentionally does not print `hash` directly**: `HashSet` iteration order is not guaranteed by Java. Even if `[1, 2, 3, 4]` happens to appear, you must not rely on it in your program.

The second half of the program illustrates a deeper difference in **the definition of duplicate elements**, not merely ordering. The next section explains why.

## 4. BigDecimal: compareTo is 0 but equals is false

`BigDecimal` stores both numeric value and **scale** (the number of decimal digits in internal representation):

```java
BigDecimal a = new BigDecimal("2.0");  // scale = 1
BigDecimal b = new BigDecimal("2.00"); // scale = 2
```

The snippet above is illustrative and requires `import java.math.BigDecimal;`.

```text
a.compareTo(b) == 0  → true
a.equals(b)          → false
```

Reason: `compareTo()` treats two numbers as equal in **mathematical value**, whereas `BigDecimal.equals()` checks both **value and scale**.

This directly affects sets:

- `HashSet<BigDecimal>` uses equality via `equals/hashCode`, so `2.0` and `2.00` are **distinct**: size is **2**.
- `TreeSet<BigDecimal>` under natural ordering uses `compareTo == 0`, so these two values are treated as **equivalent in the tree**: size is **1**.
- `decimalHash.contains(new BigDecimal("2.000"))` is `false` because scale 3 differs from scales 1 and 2.
- `decimalTree.contains(new BigDecimal("2.000"))` is `true` because the numeric value is 2, so comparing with the stored element returns 0.

`BigDecimal` is a classic example with **natural ordering inconsistent with equals**, documented in the JavaDoc. It is not a bug in `HashSet` or `TreeSet`: each class is executing its own mechanism properly.

If business logic views `2.0`, `2.00`, and `2` as **the same value**, clearly choose the criterion in the data-processing layer. If using `HashSet` and wanting deduplication by numeric value, you can normalize `BigDecimal` values with `stripTrailingZeros()` before adding and looking up. However, normalization can change scale, even producing a negative scale for numbers such as `1000.00`; do not apply it indiscriminately when scale carries business meaning.

## 5. A Comparator can cause TreeSet to “lose” distinct elements

Even when an element type has consistent `equals` and natural ordering, a `TreeSet` with a **developer-supplied comparator** can still treat distinct objects as duplicates.

For example: each student has an `id` and a `score`. If the comparator compares **only** score, two students with different IDs but the same score compare as 0. `TreeSet` will keep only one representative student for that score group.

Create file `ComparatorSetDemo.java`:

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class ComparatorSetDemo {
    record Student(String id, int score) {}

    public static void main(String[] args) {
        Student a = new Student("S01", 90);
        Student b = new Student("S02", 90);

        System.out.println(a.equals(b));

        Set<Student> byEquality = new HashSet<>();
        byEquality.add(a);
        byEquality.add(b);
        System.out.println(byEquality.size());

        Comparator<Student> byScore =
                Comparator.comparingInt(Student::score);
        TreeSet<Student> byScoreOnly = new TreeSet<>(byScore);
        System.out.println(byScoreOnly.add(a));
        System.out.println(byScoreOnly.add(b));
        System.out.println(byScoreOnly.size());
        System.out.println(byScoreOnly.contains(b));

        Comparator<Student> byScoreThenId =
                Comparator.comparingInt(Student::score)
                        .thenComparing(Student::id);
        TreeSet<Student> fullOrder = new TreeSet<>(byScoreThenId);
        fullOrder.add(a);
        fullOrder.add(b);
        System.out.println(fullOrder.size());
        System.out.println(fullOrder.contains(b));
    }
}
```

Compile and run:

```bash
javac ComparatorSetDemo.java
java ComparatorSetDemo
```

Output:

```text
false
2
true
false
1
true
2
true
```

Analysis:

- Record `Student` automatically provides `equals` and `hashCode` across both `id` and `score`. `a.equals(b)` is `false`, so `HashSet` holds 2 students.
- `byScore.compare(a, b) == 0` because both scored 90. `byScoreOnly.add(b)` returns `false` even though `b` differs from `a` by `equals`. `TreeSet` has only 1 element.
- `byScoreOnly.contains(b)` returns `true` because a student **equivalent by comparator** is already present; it does not affirm that object `b` itself is stored.
- `byScoreThenId` breaks ties by `id` after `score`. Since the two objects have different IDs, `fullOrder` keeps both and preserves data ordered by score then ID.

**Design rule:** If the goal is to **sort by score while keeping every student**, the `TreeSet` comparator must break ties using criteria that properly distinguish logical objects. Or use a `List<Student>` and call `sort(byScore)` when multiple students with the same score must be kept.

Using a score-only comparator can be reasonable if **business logic genuinely wants at most one student per score level**, though in that case the deduplication policy should be stated explicitly.

## 6. Consistency requirement between compareTo and equals

For a class implementing `Comparable<T>`, Java **strongly recommends**:

```text
x.compareTo(y) == 0  ⇔  x.equals(y) == true
```

For `TreeSet` using a comparator, the corresponding requirement is:

```text
comparator.compare(x, y) == 0  ⇔  x.equals(y) == true
```

Here the `⇔` symbol means the condition holds in **both directions**. When that is guaranteed:

1. Two objects equal by `equals` are not treated by `TreeSet` as two distinct elements.
2. Two objects distinct by `equals` are not merged by `TreeSet` due to the comparator returning 0.
3. `HashSet` and `TreeSet` can agree on duplicate-element criteria, even though ordering and complexity differ.

An ordering **inconsistent with equals** can still yield a tree operating by the specified order, yet behavior may not match the general `Set` equality contract. This is why `TreeSet` documentation specifically notes that the comparator or natural ordering needs to be consistent with `equals` if full `Set` contract compliance is desired.

Also distinguish **valid comparison ordering** from **consistency with equals**. A comparator must be consistent, transitive, and sign-symmetric under `Comparator` rules. A comparator violating those rules causes even more severe issues than merely diverging from equality.

## 7. Null, comparability, and common errors when adding elements

`HashSet` allows **one `null` element**. Adding `null` a second time does not change the set size.

For `TreeSet`, the tree must know how to compare elements. Therefore:

- When using natural ordering such as `TreeSet<String>` or `TreeSet<Integer>`, adding `null` causes `NullPointerException` in standard implementations.
- A comparator such as `Comparator.nullsFirst(...)` can define an ordering for `null` if business logic needs it; in that case a `TreeSet` constructed with an appropriate comparator can hold `null`.
- If elements do not have a compatible natural ordering, or are not mutually comparable, `TreeSet` may throw `ClassCastException`. For example, the `Student` record above does not implement `Comparable`, so `new TreeSet<>(comparator)` must be used to hold multiple students.

Do not assume `TreeSet` automatically knows how to compare two arbitrary objects. For `TreeSet` to accept data, either **natural ordering** or an explicit **comparator** must be provided.

## 8. Mutating object state after adding to a set

If an object used as a set element has fields involved in equality or ordering that can change, lookup behavior can become erroneous:

- In `HashSet`, if `hashCode()`/`equals()` changes due to mutating an element's field after insertion, `contains` or `remove` may fail to find the object as expected.
- In `TreeSet`, if `compareTo` or `Comparator` criteria change after insertion, the element's position in the tree may no longer fit the order; find, remove, or traversal operations can yield unpredictable results.

For long-lived keys and elements, **prefer immutable data**. If changing identity or ordering criteria is genuinely needed, remove the element from the set **before** modifying and re-add it, or create a new immutable object.

`Comparator` also needs to rely on stable criteria. If it depends on mutable external state (e.g., dynamic configuration), the tree structure can lose consistency even if objects do not change.

## 9. Choosing HashSet or TreeSet in practical scenarios?

**Choose `HashSet` when:**

- The goal is existence checking, deduplication, and add/remove by object equality.
- Iteration order or nearest-element queries are not needed.
- You want low average cost for standard operations, with valid `equals/hashCode` and a well-distributed hash.

**Choose `TreeSet` when:**

- Elements must **always remain ordered** without re-sorting on every access.
- You need `first`, `last`, `floor`, `ceiling`, `lower`, `higher`, `headSet`, `tailSet`, `subSet`, or range queries.
- You have a valid `Comparable` or `Comparator` and clearly understand the relationship between `compare == 0` and `equals`.

**Choose `LinkedHashSet` when:** you need set uniqueness and **to preserve insertion order**. It does not replace `TreeSet`'s order-value query capabilities.

**Choose `List` then sort when:** you want to retain **every record**, including records sharing the same sort criterion, and need display ordered by a comparator. `TreeSet` is a set, so `compare == 0` causes elements to be treated as duplicates.

Neither standard `HashSet` nor `TreeSet` automatically guarantees safety when multiple threads concurrently modify the set; appropriate synchronization mechanisms or concurrent structures must be used as required.

## 10. Checklist for testing both sets

1. **Test two objects with the same logical value:** are `equals` and `hashCode` consistent? Do `compareTo` or the comparator return 0?
2. **Test two objects with different logical values:** does the comparator have sufficient tie-breaking criteria not to accidentally merge them?
3. **Test duplicate elements and counts:** after `add`, compare the `boolean` return value and `size()` of each set.
4. **Test ordering:** expect ordering only from `TreeSet` (or `LinkedHashSet` by insertion order); do not write tests assuming `HashSet` iteration order.
5. **Test contains/remove:** especially with pairs like `BigDecimal("2.0")` and `BigDecimal("2.00")`, or comparators checking a single field.
6. **Test `null` and non-comparable data:** consider element types, natural ordering, and comparator policy.
7. **Test mutable data:** keep fields participating in equality and ordering immutable while the object remains in the set.
8. **Verify business objective:** do you need a set of unique elements, an ordered set of elements, insertion order, or a list that can hold duplicate values?

**Self-check:**

- Add `2.0` and `2.00` as `BigDecimal` into `HashSet` and `TreeSet` with natural ordering: what are their respective sizes? **2 and 1.**
- Two `Student`s have different `id`s yet the same `score`; how many elements does a `TreeSet` comparing only `score` keep? **1.**
- If `HashSet` prints in ascending order on one run, is the same order guaranteed on the next run? **No.**
- Wanting to keep every record with the same score and only sort for display, what should be used? **A `List` and `sort` or a comparator fitting the requirement to retain all records.**

**Takeaway:** `HashSet` recognizes duplicate elements by `equals/hashCode`, whereas `TreeSet` uses a comparison result of 0. Therefore they do not differ only in iteration order: **element counts and lookup results can also differ**, especially with `BigDecimal` or comparators inconsistent with `equals`.
