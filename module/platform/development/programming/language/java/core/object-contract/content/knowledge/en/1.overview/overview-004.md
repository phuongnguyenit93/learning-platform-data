# The Relationship Between `equals()`, `hashCode()`, `compareTo()`, and `Comparator` in Java

When working with Java objects, it is important to clearly distinguish **logical equality**, **hash codes for lookup**, and **sort ordering**. These four mechanisms are related but serve different purposes. Understanding their relationship helps prevent bugs when using `HashSet`, `HashMap`, `TreeSet`, `TreeMap`, and when sorting lists.

## 1. Four Mechanisms Answering Four Questions

| Mechanism | Typical signature | Question answered | Where commonly used |
| --- | --- | --- | --- |
| `equals()` | `boolean equals(Object other)` | Are two objects **logically equal**? | `HashSet`, `HashMap`, `List.contains()` |
| `hashCode()` | `int hashCode()` | What is the hash code used for bucketing/lookup? | `HashSet`, `HashMap` |
| `compareTo()` | `int compareTo(T other)` in `Comparable<T>` | What is the **natural ordering** between two elements? | `TreeSet`, `TreeMap`, natural sorting |
| `Comparator<T>` | `int compare(T a, T b)` | What is the **custom ordering** for a given task? | `List.sort()`, `TreeSet`, `TreeMap`, `PriorityQueue` |

Every object inherits `equals()` and `hashCode()` from `Object`. `compareTo()` is only present when a class implements `Comparable<T>`. `Comparator<T>` is an independent comparison strategy, and multiple strategies can be created for the same class.

Three statements easily confused:

- `a.equals(b) == true` **necessarily implies** `a.hashCode() == b.hashCode()`.
- `a.hashCode() == b.hashCode()` **does not imply** `a.equals(b)` because hash collisions can occur.
- `a.compareTo(b) == 0` or `comparator.compare(a,b) == 0` only means **equivalent under that comparison**; it does not necessarily equal `equals()`.

## 2. The Contract of `equals()` and `hashCode()`

### 2.1. `equals()` Defines Equality

For non-null objects `x`, `y`, `z`, a correct `equals()` implementation must satisfy:

1. **Reflexive:** `x.equals(x)` is always `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` must be the same.
3. **Transitive:** if `x.equals(y)` and `y.equals(z)`, then `x.equals(z)`.
4. **Consistent:** when relevant state does not change, comparison results must remain stable.
5. **Null comparison:** `x.equals(null)` is always `false`.

`Object.equals()` defaults to comparing references (`==`). If business rules consider two objects with the same identifier to be the same entity, `equals()` must be overridden to express that.

### 2.2. `hashCode()` Must Be Consistent With `equals()`

The most important contract rule: **two objects equal according to `equals()` must have the same hash code**. The hash of the same object must remain stable as long as the information participating in equality does not change, within a single execution.

Two different objects are allowed to have the same hash; `hashCode()` is not a unique ID. `HashMap`/`HashSet` use the hash to locate the lookup bucket, then use equality to distinguish the relevant keys. Therefore, checking only that `hashCode()` values are equal is not sufficient.

If `equals()` is based on `id`, then `hashCode()` should also be based on `id`. For example, two `Student` instances with the same `id` but different `name` values are still equal; computing the hash from both `id` and `name` would violate the contract. The practical rule is **when overriding `equals()`, also override `hashCode()`**, using the same set of attributes that define equality.

Another note: do not mutate attributes participating in `equals()`/`hashCode()` after an object has been placed into a `HashSet` or used as a `HashMap` key. If the hash changes, lookup or removal operations can fail. Prefer immutable keys.

## 3. `Comparable` and `Comparator` Define Ordering

### 3.1. Three Result Groups

For `a.compareTo(b)` or `comparator.compare(a,b)`:

- **Negative** number: `a` comes before `b`.
- **0**: `a` and `b` are equivalent under that ordering.
- **Positive** number: `a` comes after `b`.

Do not assume the result is only `-1`, `0`, or `1`; check the sign. The comparison must be consistent, antisymmetric in sign, and transitive. If `compare(a,b)==0`, comparing those two elements with a third element must have the same sign. These rules ensure sorting algorithms and tree structures work properly.

`Comparable<T>` lives inside the class to provide **a single natural ordering**, such as students by ID. `Comparator<T>` separates the sorting strategy: descending by score, ascending by name, then by ID to break ties.

Example (assuming a `Student` type with `score()` and `id()` methods as in section 5):

```java
Comparator<Student> byScore =
        Comparator.comparingInt(Student::score).reversed();

Comparator<Student> byScoreThenId =
        Comparator.comparingInt(Student::score)
                  .reversed()
                  .thenComparing(Student::id);
```

`thenComparing()` only applies the secondary criterion when the primary criterion returns `0`. For nullable attributes, consider `Comparator.nullsFirst(...)` or `Comparator.nullsLast(...)` to specify the policy explicitly. The comparison function should not change over time or depend on state mutating while the object resides in an ordered collection.

**Common bug: comparing integers using subtraction.**

```java
// Can overflow int when the two values are too far apart:
Comparator<Integer> bad = (a, b) -> a - b;

// Safer:
Comparator<Integer> good = Integer::compare;
```

For floating-point fields, you must decide on a policy for handling `NaN`, `-0.0`, and `+0.0` matching your semantics, rather than writing subtraction and casting to `int`.

### 3.2. What Does "Consistent With `equals()`" Mean?

An ordering is called **consistent with `equals()`** if for all `a`, `b`:

```java
a.compareTo(b) == 0  // if and only if
a.equals(b)
```

This is a **very important recommendation**, especially when using `TreeSet`/`TreeMap`, though not every `Comparable` type is required to obey it. A `Comparator` used for a specific context may also intentionally group elements differently from the equality definition. When doing so, you must understand the consequences for ordered collections.

## 4. Relationship With Java Collections

| Structure/operation | Which mechanism is used? | How duplicates are determined |
| --- | --- | --- |
| `HashSet<E>` | `hashCode()` and `equals()` | According to `equals()` |
| `HashMap<K,V>` | Key's `hashCode()` and `equals()` | Keys equivalent according to `equals()` |
| `TreeSet<E>` | `compareTo()` or `Comparator` | Comparison returns `0` |
| `TreeMap<K,V>` | Key's `compareTo()` or `Comparator` | Key comparison returns `0` |
| `List.sort(comparator)` | `Comparator` | Only sorts, **does not remove** duplicate elements |
| `Collections.sort(list)` | Natural `Comparable` | Only sorts, **does not remove** duplicate elements |
| `PriorityQueue` | `Comparable`/`Comparator` | Controls priority order, **does not deduplicate** |

`TreeSet` and `TreeMap` use ordering comparison as the equivalence relation for elements/keys. Therefore:

- If `!a.equals(b)` yet `compare(a,b)==0`, `HashSet` can keep both, whereas `TreeSet` keeps only one.
- If `a.equals(b)` yet `compare(a,b)!=0`, `HashSet` keeps only one, whereas `TreeSet` can keep both.

The second case causes uniqueness in `TreeSet` to mismatch the `Set` contract based on `equals()`; this is why a comparison consistent with `equals()` should be used when standard set semantics are desired. `TreeMap` has a similar risk with keys: a second `put()` can overwrite the value of a key that compares as `0`, even if `equals()` between the two key objects is `false`.

Do not use `HashSet` if the primary requirement is sorting; do not use `TreeSet` just to sort a list by score if you need to keep all records with tied scores.

## 5. Runnable Java 17+ Example: Identity by ID, Sorted by Score

Suppose `Student` has `id`, `name`, and `score`; the business rule is that **same `id` means the same student** even if the name or score differs. Therefore `equals()`, `hashCode()`, and natural ordering are all based on `id`. Another `Comparator` sorts students in descending order of score for display in a UI.

Create the file **`ObjectContractDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.TreeSet;

record Student(String id, String name, int score)
        implements Comparable<Student> {

    Student {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof Student other
                && id.equals(other.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }

    @Override
    public int compareTo(Student other) {
        return id.compareTo(other.id);
    }
}

public class ObjectContractDemo {
    public static void main(String[] args) {
        Student a = new Student("S01", "Lan", 90);
        Student b = new Student("S01", "Lan updated", 75);
        Student c = new Student("S02", "Minh", 95);

        System.out.println("equals: " + a.equals(b));
        System.out.println("same hash: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("compareTo: " + a.compareTo(b));

        System.out.println("HashSet: "
                + new HashSet<>(List.of(a, b, c)).size());
        System.out.println("TreeSet natural: "
                + new TreeSet<>(List.of(a, b, c)).size());

        Comparator<Student> byScoreThenId =
                Comparator.comparingInt(Student::score)
                          .reversed()
                          .thenComparing(Student::id);

        List<Student> sorted =
                new ArrayList<>(List.of(a, b, c));
        sorted.sort(byScoreThenId);
        System.out.println("Sorted: "
                + sorted.stream()
                        .map(s -> s.id() + ":" + s.score())
                        .toList());

        TreeSet<Student> scoreSet = new TreeSet<>(byScoreThenId);
        scoreSet.addAll(List.of(a, b, c));
        System.out.println("TreeSet by score: "
                + scoreSet.size());
    }
}
```

Compile and run:

```bash
javac ObjectContractDemo.java
java ObjectContractDemo
```

Exact output:

```text
equals: true
same hash: true
compareTo: 0
HashSet: 2
TreeSet natural: 2
Sorted: [S02:95, S01:90, S01:75]
TreeSet by score: 3
```

**Explanation:**

1. `a` and `b` share the ID `S01`, so `equals()` is true, hashes are equal, and `compareTo()` returns `0`.
2. `HashSet` retains only two distinct IDs; `TreeSet` with natural ordering by ID also retains two.
3. `List.sort(byScoreThenId)` sorts `95, 90, 75` while **keeping all three** records.
4. `TreeSet` with the comparator by score then ID retains all three: `a` and `b` have different scores, so the comparator does not return `0` even though `equals()` considers them equal. This is an intentional example of a comparator that is **inconsistent with `equals()`**.

By default, a record generates `equals()` and `hashCode()` from **all components**. Here both are overridden to express the rule that ID is the business identity. `compareTo()` also uses ID so that natural ordering is consistent with that definition. For a pure *value object*, the right approach may be keeping the record's default `equals()`/`hashCode()` to consider all components; not every type should be identified by ID.

## 6. A Real Special Case: `BigDecimal`

`BigDecimal("2.0")` and `BigDecimal("2.00")` have the same numerical value, so `compareTo()` returns `0`. However, `equals()` also considers *scale*, so it returns `false`. This is a well-known example of natural ordering being **inconsistent with `equals()`**.

Create the file **`BigDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");

        System.out.println(x.equals(y));
        System.out.println(x.compareTo(y));
        System.out.println(new HashSet<>(List.of(x, y)).size());
        System.out.println(new TreeSet<>(List.of(x, y)).size());
    }
}
```

Run:

```bash
javac BigDecimalDemo.java
java BigDecimalDemo
```

Output:

```text
false
0
2
1
```

`HashSet` treats them as two values according to `equals()`, while `TreeSet` treats them as equivalent under natural ordering and keeps only one. When handling currency amounts or measurements, you need to decide whether the application requires the same **numerical value** or the same **value and scale** before choosing how to normalize/compare.

## 7. Design Workflow for an Object Type

**Step 1 — Define "equality".** Choose the attributes that form logical identity. For an entity, that may be a stable ID; for a value object, those are typically its value attributes. Avoid equality relations that depend on mutable attributes when used as keys.

**Step 2 — Implement `equals()` and `hashCode()` as a pair.** Use the exact same chosen attributes in both. You can have your IDE generate the code, use `Objects.equals()` for null handling, and `Objects.hash()` when combining multiple fields; keep in mind the array-allocation overhead of `Objects.hash()` on performance-sensitive paths.

**Step 3 — Choose a natural ordering if meaningful.** Implement `Comparable<T>` when there is a clear default order; try to keep `compareTo()==0` corresponding to `equals()`. There is no need to force every type to implement `Comparable`.

**Step 4 — Use `Comparator` for each distinct need.** For example, by name, score, or creation date; chain `thenComparing()` if secondary criteria are needed. For ordered sets/trees, explicitly determine how the comparator decides uniqueness.

**Step 5 — Choose the right data structure.** `HashMap`/`HashSet` for lookups and deduplication by equality; `TreeMap`/`TreeSet` when ordering, range queries, and an appropriate comparison rule are needed; `List.sort()` to sort while keeping all records.

## 8. Common Mistakes and Verification Checklist

- **Overriding `equals()` without overriding `hashCode()`:** two equal objects may fail to find each other in hash-based structures.
- **Computing hash using a field that does not participate in `equals()`:** violates the contract when two objects are equal yet have different hashes.
- **Modifying key data after inserting into `HashSet`/`HashMap`:** risks failing to look up or remove the key under its new state.
- **Assuming `compareTo()==0` always means `equals()`:** false for `BigDecimal` and many custom comparators.
- **Assuming `TreeSet` only sorts:** in fact, the comparison also determines whether two elements are retained simultaneously.
- **Comparator considering only score/name without a distinguishing tie-breaker:** elements with the same score/name may be merged by `TreeSet`; review business rules and secondary criteria.
- **Using `a - b` to compare `int` values:** risks overflow; use `Integer.compare(...)` or `Comparator.comparingInt(...)`.
- **Giving `equals()` between a superclass and subclass flawed semantics:** easily breaks symmetry/transitivity; consider `final`, `record`, or a simple value model design and test thoroughly.
- **Confusing a hash with a unique identifier:** hash codes are allowed to collide; correctness comes from the contract of both methods.
- **Testing only on "nice" data:** test same ID with different attributes, same score with different IDs, null fields if allowed, extreme values, and different collections.

**Takeaway:** `equals()` defines equality; `hashCode()` must be compatible with that definition; `compareTo()` provides natural ordering; `Comparator` provides contextual ordering. Ordering and equality relations should be consistent whenever possible, especially if used to determine unique elements in `TreeSet` or keys in `TreeMap`.