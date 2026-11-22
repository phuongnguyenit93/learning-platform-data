# Documenting When Natural Ordering Is Intentionally Inconsistent with `equals()` in Java

A Java class implementing `Comparable<T>` can define a **natural ordering** through `compareTo()`. Usually it should be designed so that two objects comparing to `0` are also equal under `equals()`. However, Java **strongly recommends but does not require** the two relations to be consistent. There are business cases that intentionally use one criterion for **identity or full value** and another criterion for **natural ordering**.

When deliberately choosing such a design, **API documentation must state the difference clearly**, precisely define what `compareTo() == 0` means, explain the impact on `TreeSet`/`TreeMap`, and guide how to preserve uniqueness by `equals()` if API consumers need it. Writing only "implements Comparable" or "sorts by priority" is not enough.

## 1. Understanding the two relations accurately

Suppose `a` and `b` both belong to class `T`:

- **Equality by `equals()`**: `a.equals(b)` means both objects share the same logical value per the class's contract. If `equals()` is overridden, `hashCode()` must be consistent: two equal objects have the same hash.
- **Equivalence in natural ordering**: `a.compareTo(b) == 0` means they belong to the same **equivalence group of the comparison**; in an ordered collection using this relation, they are treated as duplicates for sorting/key purposes.
- **Consistent with `equals()`** means for **every** pair `a`, `b`, the two expressions `(a.compareTo(b) == 0)` and `a.equals(b)` always have the same boolean value.
- **Inconsistent** requires only a single pair where the two expressions return different results. For example `compareTo() == 0` while `equals()` is `false`; the reverse direction is also a potentially harmful form of inconsistency.

Being inconsistent with `equals()` **does not mean** `compareTo()` may behave arbitrarily. `Comparable` still requires a stable and valid ordering relation: the signs of reversed comparisons must be opposite, the greater-than relation must be transitive, and elements comparing to `0` must share the same sign when compared to any third element. The negative/zero/positive result matters, not strictly `-1`, `0`, `1`.

A business example: `RankedItem(id, priority)` has a value identity comprising both `id` and `priority` (like a record), yet its natural ordering **compares only `priority`**. Two items with different IDs and the same priority level are not equal under `equals()`, yet `compareTo()` returns `0`. This design is usable, provided it is clearly documented that an ordered set will keep **at most one item per priority level**.

## 2. Why must documentation be explicit?

`Comparable<T>` defines the natural ordering used by default in several APIs:

- `Collections.sort(list)`, `List.sort(null)`, and `Arrays.sort(array)` with elements comparable by natural ordering.
- `TreeSet<E>` and `TreeMap<K,V>` when constructed **without passing a `Comparator`**.
- `PriorityQueue<E>` when constructed without passing a comparator: priority ordering relies on `compareTo()`.

Notably, **list-sorting** APIs still keep all elements even if `compareTo() == 0`. Yet `TreeSet` and `TreeMap` use **a comparison result of `0` to decide duplicate elements/keys**. This is the biggest source of surprise for API users.

| Behavior | When `a.compareTo(b) == 0` but `!a.equals(b)` |
| --- | --- |
| `HashSet.add(a); add(b)` | Normally keeps **both**, because duplicates are evaluated via `equals()` and corresponding hash |
| `TreeSet` using natural ordering | Keeps only **one**, the second add returns `false` |
| `HashMap` using `a`, `b` as two keys | Keeps **two distinct keys** per `equals()` |
| `TreeMap` using natural ordering | `put(b, value2)` may **replace the value** of the equivalent key `a` |
| `List.sort(null)` / `Collections.sort(list)` | Sorts, **does not drop records** of equal rank |
| `PriorityQueue` | Uses order to retrieve elements, **does not deduplicate** solely because `compareTo() == 0` |

Collections built on natural ordering still operate consistently with **their comparison rules**, yet `TreeSet`/`TreeMap` may diverge from intuition and the `Set`/`Map` contract defined in terms of element/key `equals()`. Documenting this helps callers choose the right collection type, comparator, and key model.

**Subtle consequence:** `treeSet.contains(x)` can return `true` even when the set contains no element `equals(x)`, as long as an existing element compares to `0` against `x`. Similarly, `treeMap.get(x)` can return the value of a key that differs under `equals()` yet compares to `0` under `compareTo()`.

## 3. Minimum requirements to document in Javadoc

The Java SE 17 `Comparable` documentation recommends a standard warning sentence for intentional inconsistency:

> Note: this class has a natural ordering that is inconsistent with equals.

Include **this warning in the type's documentation** (or an easily discoverable public API doc), alongside the ordering definition. It can be reiterated in the Javadoc of `compareTo()` and collection usage guides. The warning sentence is the starting point; good documentation must answer the following:

1. **Which fields does `equals()` use?** State clearly when two objects are considered the same value.
2. **Which fields and direction does `compareTo()` use?** For example ascending `priority`; `id` is not used as a tie-breaker.
3. **When does `compareTo()` return `0` even though `equals()` is `false`?** Provide a concrete illustrative pair.
4. **Why does the design intentionally differ?** For instance, business logic wants priority-level grouping rather than merging identities.
5. **What is the effect on ordered sets/maps?** Describe element deduplication, value replacement, and `contains/get` results.
6. **How to proceed if distinct objects must be preserved?** Choose `HashSet`/`HashMap` when `equals()` should govern uniqueness, or pass a comparator consistent with equality to `TreeSet`/`TreeMap` if ordering is also genuinely needed.
7. **Other constraints**: is `null` supported, are criteria immutable while the object resides in a collection, and is the method stable across versions?

An overly long Javadoc is not necessary, yet readers must be able to predict collection behavior **before using the class as a map key or set element**.

## 4. Complete documentation example directly on the class (Java 17+)

In the following example, a `record` has `id` and `priority`:

- Auto-generated `equals()`/`hashCode()` from the record examine **both components**.
- `compareTo()` intentionally checks only `priority` to establish a priority-based natural ordering.
- Two items with the same priority yet different IDs are **different under `equals()`** and **equivalent in ordering**.
- `id` is validated non-null; `String` and `int` themselves are immutable, keeping the comparison relation stable.

Save the complete program to **`DocumentedOrderDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * An item ordered by ascending priority.
 *
 * <p>Two items are equal under equals when both id and priority
 * match. Natural ordering checks only priority; items with
 * different ids but the same priority compare to 0.
 *
 * <p>Note: this class has a natural ordering that is
 * inconsistent with equals.
 *
 * <p>TreeSet/TreeMap without a Comparator treat items with
 * the same priority as one equivalent element or key.
 * To preserve distinct ids, use HashSet/HashMap or a
 * comparator that also considers id.
 */
record RankedItem(String id, int priority)
        implements Comparable<RankedItem> {

    RankedItem {
        Objects.requireNonNull(id, "id");
    }

    /**
     * Compares natural ordering by ascending priority,
     * intentionally ignoring id. Returns 0 for different ids
     * with the same priority.
     */
    @Override
    public int compareTo(RankedItem other) {
        Objects.requireNonNull(other, "other");
        return Integer.compare(priority, other.priority);
    }
}

public class DocumentedOrderDemo {
    public static void main(String[] args) {
        RankedItem a = new RankedItem("A", 10);
        RankedItem b = new RankedItem("B", 10);
        RankedItem unseen = new RankedItem("C", 10);

        System.out.println("equals: " + a.equals(b));
        System.out.println("compareTo zero: "
                + (a.compareTo(b) == 0));

        Set<RankedItem> hashed =
                new HashSet<>(List.of(a, b));
        Set<RankedItem> ordered =
                new TreeSet<>(List.of(a, b));

        System.out.println("HashSet size: " + hashed.size());
        System.out.println("TreeSet size: " + ordered.size());
        System.out.println("TreeSet contains unseen: "
                + ordered.contains(unseen));

        List<RankedItem> list =
                new ArrayList<>(List.of(a, b));
        list.sort(null);
        System.out.println("sorted list size: " + list.size());

        Map<RankedItem, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");

        Map<RankedItem, String> treeMap = new TreeMap<>();
        treeMap.put(a, "first");
        treeMap.put(b, "second");

        System.out.println("HashMap size: " + hashMap.size());
        System.out.println("TreeMap size: " + treeMap.size());
        System.out.println("TreeMap lookup unseen: "
                + treeMap.get(unseen));
        System.out.println("TreeMap first key: "
                + treeMap.keySet().iterator().next().id());

        Comparator<RankedItem> completeOrder =
                Comparator.comparingInt(RankedItem::priority)
                          .thenComparing(RankedItem::id);
        Set<RankedItem> distinctSorted =
                new TreeSet<>(completeOrder);
        distinctSorted.add(a);
        distinctSorted.add(b);
        System.out.println("TreeSet with tiebreaker: "
                + distinctSorted.size());
    }
}
```

Compile and run:

```bash
javac DocumentedOrderDemo.java
java DocumentedOrderDemo
```

Output:

```text
equals: false
compareTo zero: true
HashSet size: 2
TreeSet size: 1
TreeSet contains unseen: true
sorted list size: 2
HashMap size: 2
TreeMap size: 1
TreeMap lookup unseen: second
TreeMap first key: A
TreeSet with tiebreaker: 2
```

**Explanation of less-intuitive results:**

- `HashSet` and `HashMap` distinguish `"A"` from `"B"` using record equality.
- `TreeSet` keeps only `a` because `b.compareTo(a) == 0`. `contains(unseen)` also returns `true` since `"C"` shares `priority = 10`, even though it was never added and is not `equals()` to `"A"`.
- `TreeMap` treats `a`, `b`, `unseen` as equivalent keys by `priority`. Calling `put(b, "second")` replaces the value of the prior mapping, so the map has size `1`. The retained key object remains `a`, so `"TreeMap first key"` is `"A"`; looking up with `unseen` retrieves `"second"`.
- `List.sort(null)` merely sorts by natural ordering; the list **loses no elements**. For two elements equal in ordering, `List`'s stable sort algorithm also preserves relative order.
- `completeOrder` checks `priority` then `id`, so items with equal priority yet different IDs are distinguished. For the record in this example, comparing both fields matches the equality definition based on both components.

**Important:** the `completeOrder` comparator can align with `equals()` **for this specific data type**, because record equality checks precisely `id` and `priority`. If another type's equality relies only on `id` while a comparator checks mutable secondary state, merely adding `thenComparing(id)` might not produce an ordering consistent with equality. You must verify the pair of relations across **all cases**, not just two illustrative examples.

## 5. Standard library example: `BigDecimal`

`BigDecimal` is a standard case mentioned by the JDK in `Comparable` documentation:

- `new BigDecimal("2.0")` has scale `1`, `new BigDecimal("2.00")` has scale `2`.
- They have the same numerical value, so `compareTo()` returns `0`.
- `BigDecimal`'s `equals()` inspects both **unscaled value and scale**, so two representations with different scales can be unequal.

Create file **`BigDecimalOrderDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.TreeSet;

public class BigDecimalOrderDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");

        System.out.println("x scale: " + x.scale());
        System.out.println("y scale: " + y.scale());
        System.out.println("equals: " + x.equals(y));
        System.out.println("compareTo zero: "
                + (x.compareTo(y) == 0));
        System.out.println("HashSet size: "
                + new HashSet<>(List.of(x, y)).size());
        System.out.println("TreeSet size: "
                + new TreeSet<>(List.of(x, y)).size());
    }
}
```

Commands:

```bash
javac BigDecimalOrderDemo.java
java BigDecimalOrderDemo
```

Stdout:

```text
x scale: 1
y scale: 2
equals: false
compareTo zero: true
HashSet size: 2
TreeSet size: 1
```

That is **intentional API behavior**, not a Java bug. In financial problems, numerical value and decimal representation sometimes carry different meanings; developers must know which relation is requested. Do not automatically call `stripTrailingZeros()` to "fix" every case: normalization can alter scale and representation (including scientific notation), impacting business logic that needs to preserve original scale.

Official documentation: [Java SE 17 – Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) and [Java SE 17 – BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

## 6. Where should Javadoc be placed and how detailed should it be?

### 6.1. Class/record-level documentation is the primary location

Users typically see information when inspecting the class before using it as a key. The class level should state:

- The equality relation (which components determine equality).
- The natural ordering relation (which components, ascending/descending direction).
- The standard warning sentence on inconsistency.
- Consequences for sorted collections and alternative choices.

If the public API exposes multiple overloads or helper comparators, class documentation should also point to the appropriate options. For instance: `Comparator.comparing(RankedItem::id)` is consistent with equality only when ID **by itself suffices** as identity. For a record containing `id` and `priority`, a comparator based solely on ID will merge records with the same ID yet different priorities, remaining inconsistent with equality; all relevant fields must be checked if full consistency is the goal.

### 6.2. `compareTo()` documentation clearly states the `0`-returning relation

On the method, describe negative/0/positive values and especially explain when 0 is returned, for example:

> Compares by ascending priority. Two items with different IDs yet the same priority are considered equivalent in ordering and `compareTo()` returns 0.

To match Javadoc standards, add `@param other`, `@return`, `@throws NullPointerException`, and `@see` sections where helpful. Avoid writing only "compares two objects" or giving a single example that fails to state the condition for returning `0`.

Regarding `null`: for `Comparable.compareTo(null)`, the standard and contractual behavior is throwing `NullPointerException`, even though `equals(null)` is always `false`. If nullable elements in a **collection** need sorting, normally use `Comparator.nullsFirst()` or `Comparator.nullsLast()` at the call site, rather than making the class accept null objects in natural ordering.

### 6.3. README, user guides, and examples must all state the same rule

Javadoc helps only if examples and integration docs are not misleading. A guide section can state:

- **To deduplicate by full value (`equals`)**: use `HashSet`/`HashMap` with a consistent `hashCode()`.
- **To group/keep at most one value per rank**: `TreeSet`/`TreeMap` with that natural ordering can fit, yet retained-element selection and map updates must be clear.
- **To both sort and preserve distinct elements**: use `List.sort()` if duplicates are allowed, or pass a comparator whose `0` result matches the equality relation to `TreeSet`/`TreeMap`.
- **To order by rank while keeping uniqueness by ID**: it is usually better to store in a map by ID and sort values when needed, or choose a suitable structure; do not use `TreeSet` with a rank-only comparison expecting it to retain every ID.

You must distinguish **uniqueness** from **display ordering**. A comparator grouping by rank can work well for grouping, yet is not automatically a good identity definition for keys.

## 7. When should you genuinely choose intentional inconsistency?

Situations to consider:

1. **Value models with multiple valid representations of the same magnitude**, like `BigDecimal` and scale: equality preserves representation details, while natural ordering inspects only magnitude.
2. **Domain models defining primary rank by a single criterion**, while objects store extra distinguishing information: use `compareTo()` to express rank equivalence classes if this is truly the single natural concept.
3. **Published API compatibility**: changing `equals()` or `compareTo()` semantics on a public type can be a breaking change; transparent documentation of the existing relation is required.

Do not default to an inconsistent design just to save one extra secondary comparison. If a class has multiple sensible sorting ways (by ID, score, name, time...), consider **not implementing `Comparable`** and requiring callers to supply a `Comparator`. This lowers the risk of users defaulting to natural ordering with unintended semantics.

Another option is making natural ordering match `equals()` (e.g., `priority` then `id` when record equality uses both fields), and offering a separate `BY_PRIORITY` comparator for priority-level grouping. Even then, documentation must still warn that **this Comparator is inconsistent with equality** if used in `TreeSet`, despite the class's own natural ordering being consistent.

## 8. The `compareTo()` contract must still be obeyed

Permitted inconsistency covers only a difference between **the definition of ordering equivalence groups** and **the definition of equality**. It does not allow:

- Non-transitive comparisons, such as `a < b`, `b < c`, yet `a > c`.
- Two objects comparing to `0` yet returning different signs when compared against a third object.
- Results varying by clock, random numbers, or mutable state uncontrolled by the collection.
- Using subtraction `return a.priority - b.priority;` as an `int` criterion when overflow is possible. Use `Integer.compare(a.priority, b.priority)` as shown.
- Evaluating `compareTo()` using completely different criteria from one call to the next or mutating criteria while the object sits in `TreeSet`/`TreeMap`.

Also do not alter `hashCode()` to force equality according to `compareTo()`: `hashCode()` must align with **`equals()`**, not necessarily with groups defined by natural ordering. For two objects with `compareTo() == 0` yet `equals() == false`, their hashes **may be equal or different**.

If an object has fields participating in natural ordering that can mutate while already inside a sorted collection, tree lookups/ordering can become invalid. Keep sorting keys/criteria stable throughout storage; records and immutable classes generally make this easier to guarantee.

## 9. Contract testing and documentation verification

A test suite should verify not only that a list is sorted properly. It must test **cases demonstrating intentional inconsistency** and mandatory ordering rules:

| Case | Expectation when natural ordering checks only `priority` |
| --- | --- |
| Same `id`, same `priority` | `equals() == true`, `compareTo() == 0`, equal hashes |
| Different `id`, same `priority` | `equals() == false`, `compareTo() == 0` |
| Different `priority` | `compareTo()` negative/positive in proper direction |
| Compared to itself | `compareTo() == 0`, `equals() == true` |
| Sequence of three priority levels 1, 2, 3 | Transitive and stable order |
| `compareTo(null)` | `NullPointerException` per contract |
| Two elements with different IDs and same priority in `TreeSet` | `size()` is 1 |
| Two keys with different IDs and same priority in `TreeMap` | Equivalent key is used for the same mapping |
| Same two elements in `HashSet` | `size()` is 2 |
| Same two elements in `List.sort(null)` | Still has 2 elements after sorting |

For complex data types, add property-based tests for sign symmetry, transitivity, and consistency when comparing against a third object. If the class is a public API, a regression test can use the exact example pair from the Javadoc to ensure documentation and behavior do not drift during refactoring.

If a developer later "fixes" `compareTo()` by adding `id` as a tie-breaking criterion, two objects that used to compare to `0` can become distinct groups. This is **not merely a display change**, as it can cause `TreeSet` to retain extra elements or `TreeMap` to create additional keys. Such a change requires compatibility evaluation, documentation updates, and tests rather than being treated as an internal optimization.

## 10. Pre-release checklist template

- [ ] Class Javadoc explicitly declares **natural ordering intentionally inconsistent with equals** with the standard warning or an equivalent prominent notice.
- [ ] Accurately describes criteria and sort direction; specifically clarifies **when `compareTo()` returns `0`**.
- [ ] Clearly describes which attributes determine `equals()` and `hashCode()`; does not alter hash based on separate comparison criteria.
- [ ] Includes an example of two objects where `equals()` differs yet `compareTo() == 0`, or the actual inconsistency direction supported by the class.
- [ ] States the impact on `TreeSet` (`add`/`contains`) and `TreeMap` (`put`/`get`) when no comparator is passed.
- [ ] Guides choosing `HashSet`/`HashMap`, `List.sort()`, or an equality-consistent comparator depending on intent.
- [ ] Tests valid ordering, transitivity, `null`, criterion stability, and key immutability in collections.
- [ ] If the API changes comparison rules, updates Javadoc, README, tests, and assesses compatibility impact.

**Remember:** a natural ordering can be intentionally inconsistent with `equals()` while still fulfilling the `Comparable` contract. When choosing that design, documentation must explain **the definitions of both relations, why they differ, and which collection behaviors are affected**. Avoid letting users discover the difference only after `TreeSet` drops an element or `TreeMap` overwrites a value.