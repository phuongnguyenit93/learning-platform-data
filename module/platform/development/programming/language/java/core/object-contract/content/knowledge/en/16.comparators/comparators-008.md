# Distinguishing Display Comparators from Object Equality

## Learning Objectives

In Java, **display order** and **object equality** are two independent concepts. `Comparator<T>` defines an ordering to sort a list: by name, score, timestamp, priority, or price. Conversely, `equals(Object)` determines whether two objects are considered equal under the class's contract. A comparator used for display may consider two objects **order-equivalent** even when they are two distinct business records.

This lesson helps you:

- Distinguish `Comparator.compare(a, b) == 0`, `a.equals(b)`, `a == b`, and `a.hashCode()`.
- Explain cases where two objects share the same sort key yet are not equal.
- Understand why `List.sort` keeps every element, while `TreeSet`/`TreeMap` use `compare == 0` to identify equivalent elements or keys.
- Use `thenComparing` to create a tie-breaker without confusing it with the `equals` contract.
- Co-design business equality rules and display ordering, especially with IDs, duplicate names, null, case sensitivity, and pagination.

## 1. Checks with Different Meanings

| Expression | Meaning |
| --- | --- |
| `a == b` | Whether two references point to **the exact same object** |
| `a.equals(b)` | Whether two objects are **equal per the class contract** |
| `comparator.compare(a, b) == 0` | Whether two objects occupy **the same position in the order** defined by the comparator |
| `a.hashCode() == b.hashCode()` | Whether two objects share the same hash code; this **does not prove equality** |

`compare(a, b)` returns a **negative** number, `0`, or a **positive** number corresponding to `a` coming before, being order-equivalent to, or coming after `b`. Do not rely on specific absolute values: only examine the sign of the result.

A comparator is said to be **consistent with equals** when, for the relevant elements:

```text
comparator.compare(a, b) == 0  ⇔  a.equals(b)
```

The bidirectional equivalence means:

1. If the comparator returns `0`, then `equals` returns `true`.
2. If `equals` returns `true`, then the comparator returns `0`.

A comparator used **solely for UI sorting** can be inconsistent with `equals` and still be valid, provided it satisfies the `Comparator` ordering contract. However, when that comparator is placed into a `TreeSet` or `TreeMap`, this divergence can drop records or overwrite map values.

**Do not confuse `Comparator.equals(Object)`:** That is a method on **the comparator object itself**, not a way to compare two data elements. `compare(a,b) == 0` is how a comparator expresses that two elements are order-equivalent.

## 2. One Display Key Can Represent Multiple Objects

Consider a list of members:

| ID | Name | Score |
| ---: | --- | ---: |
| 101 | An | 90 |
| 102 | An | 90 |
| 103 | Binh | 80 |

The UI ranks by descending score and ascending name. Two members with IDs `101` and `102` share the same display key: score `90` and name `"An"`. Therefore, a comparator checking only score and name will return `0`.

Yet they can still be two different people. If a class models a member as a record:

```java
record Member(int id, String name, int score) {}
```

A record's default `equals` compares **all components**. Differing IDs make `equals` return `false` even when display keys collide.

Diagram:

```text
Member 101 ── score 90, name An ──┐
                                  ├── same position per Comparator
Member 102 ── score 90, name An ──┘

Record's equals: different because IDs differ
```

This is a normal situation in leaderboards: **same rank or same sort criteria does not mean same identity**.

## 3. Runnable Example: `List` and `TreeSet` Produce Different Results

Create the file **`DisplayComparatorDemo.java`** (Java 17+):

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class DisplayComparatorDemo {
    record Member(int id, String name, int score) {}

    public static void main(String[] args) {
        Member an101 = new Member(101, "An", 90);
        Member an102 = new Member(102, "An", 90);
        Member binh103 = new Member(103, "Binh", 80);

        Comparator<Member> forDisplay =
                Comparator.comparingInt(Member::score)
                        .reversed()
                        .thenComparing(Member::name);

        System.out.println("same object: " + (an101 == an102));
        System.out.println("equals: " + an101.equals(an102));
        System.out.println("display compare == 0: "
                + (forDisplay.compare(an101, an102) == 0));

        List<Member> members =
                new ArrayList<>(List.of(an101, an102, binh103));
        members.sort(forDisplay);

        System.out.println("sorted list size: " + members.size());
        System.out.println("sorted IDs: "
                + members.stream().map(Member::id).toList());

        Set<Member> hashSet =
                new HashSet<>(List.of(an101, an102, binh103));

        Set<Member> treeSet = new TreeSet<>(forDisplay);
        treeSet.addAll(List.of(an101, an102, binh103));

        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet size: " + treeSet.size());

        Member anotherAn = new Member(999, "An", 90);
        System.out.println("TreeSet contains anotherAn: "
                + treeSet.contains(anotherAn));
        System.out.println("HashSet contains anotherAn: "
                + hashSet.contains(anotherAn));
    }
}
```

Compile and run:

```bash
javac DisplayComparatorDemo.java
java DisplayComparatorDemo
```

**Exact output:**

```text
same object: false
equals: false
display compare == 0: true
sorted list size: 3
sorted IDs: [101, 102, 103]
HashSet size: 3
TreeSet size: 2
TreeSet contains anotherAn: true
HashSet contains anotherAn: false
```

**Explanation:**

- `List.sort(forDisplay)` only changes the **order** of elements in the list; it does not drop elements for which the comparator returns `0`. Hence the list still has three members.
- `List.sort` in Java is a **stable** sort. Two elements considered tied by the comparator keep their relative order from before sorting: here `101` before `102`.
- `HashSet` uses `Member`'s `equals` and `hashCode`. Because IDs differ, both `an101` and `an102` are retained.
- `TreeSet` constructed with `forDisplay` uses `compare(a,b) == 0` to determine equivalent elements, thus merging two members with different IDs but the same name/score.
- `treeSet.contains(new Member(999,"An",90))` returns `true` because the comparison rule considers that element equivalent to an existing element. `HashSet.contains` returns `false` because the ID differs.

**Takeaway:** A display comparator fits sorting a `List`; if used to define an ordered set, be fully aware that elements may be treated as duplicates.

## 4. Which Structure Uses Which Rule?

| Structure / Operation | Rule used | Consequence when `compare == 0` but `equals == false` |
| --- | --- | --- |
| `List.sort(comparator)` | Comparator determines order only | Keeps both elements |
| `Collections.sort(list, comparator)` | Comparator determines order only | Keeps both elements |
| `stream.sorted(comparator)` | Comparator determines result order | Does not automatically drop elements |
| `HashSet` | `equals` and `hashCode` | Does not use comparator; both objects can coexist |
| `HashMap` | `equals` and `hashCode` on keys | Does not use comparator; two keys differing by `equals` can coexist |
| `TreeSet(comparator)` | `compare == 0` determines equivalence | Keeps only one representative |
| `TreeMap(comparator)` | `compare == 0` determines key equivalence | `put` of a later key can update the previous entry's value |

A comparator comparing only part of an object is very common for UI display: name, score, price, timestamp… But when choosing `TreeSet`/`TreeMap`, the comparator becomes part of **element/key identification semantics** rather than merely a sorting tool.

Java documentation specifies that the ordering used by a sorted set/map should be **consistent with equals** so these structures properly fulfill the general `Set`/`Map` contracts. They still have well-defined behavior under the comparator when inconsistent, but can easily surprise client code.

## 5. `TreeMap` Example: Colliding Display Keys Can Overwrite Values

Suppose an application displays content by case-insensitive title. A suitable comparator for presentation purposes is:

```java
Comparator<Article> byDisplayTitle =
        Comparator.comparing(
                Article::title,
                String.CASE_INSENSITIVE_ORDER);
```

This is an illustrative snippet, assuming type `Article` has accessor `title()`. The comparator considers titles `"Java"` and `"JAVA"` equivalent, even though the two articles have different IDs.

Run the following full example.

**File `ComparatorMapDemo.java`:**

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorMapDemo {
    record Article(int id, String title) {}

    public static void main(String[] args) {
        Article a = new Article(1, "Java");
        Article b = new Article(2, "JAVA");
        Article c = new Article(3, "Spring");

        Comparator<Article> displayOrder =
                Comparator.comparing(
                        Article::title,
                        String.CASE_INSENSITIVE_ORDER);

        Comparator<Article> strictOrder =
                displayOrder
                        .thenComparing(Article::title)
                        .thenComparingInt(Article::id);

        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("display compare zero: "
                + (displayOrder.compare(a, b) == 0));
        System.out.println("strict compare zero: "
                + (strictOrder.compare(a, b) == 0));

        Set<Article> displaySet = new TreeSet<>(displayOrder);
        displaySet.add(a);
        displaySet.add(b);
        displaySet.add(c);

        Set<Article> strictSet = new TreeSet<>(strictOrder);
        strictSet.add(a);
        strictSet.add(b);
        strictSet.add(c);

        System.out.println("display TreeSet size: "
                + displaySet.size());
        System.out.println("strict TreeSet size: "
                + strictSet.size());

        Map<Article, String> displayMap =
                new TreeMap<>(displayOrder);
        displayMap.put(a, "first");
        displayMap.put(b, "second");

        Map<Article, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");

        System.out.println("display TreeMap size: "
                + displayMap.size());
        System.out.println("display TreeMap get(a): "
                + displayMap.get(a));
        System.out.println("HashMap size: " + hashMap.size());
    }
}
```

```bash
javac ComparatorMapDemo.java
java ComparatorMapDemo
```

**Exact output:**

```text
a.equals(b): false
display compare zero: true
strict compare zero: false
display TreeSet size: 2
strict TreeSet size: 3
display TreeMap size: 1
display TreeMap get(a): second
HashMap size: 2
```

Because `displayOrder` compares only case-insensitive titles, `a` and `b` are treated as equivalent by `TreeSet`; `TreeMap.put(b,"second")` finds the equivalent key and replaces `"first"` with `"second"`. `HashMap` still retains both keys because the records differ in ID and title under `equals`.

`strictOrder` has three levels:

1. Case-insensitive title.
2. Case-sensitive title.
3. ID.

With the `Article(int id, String title)` record in the example and non-`null` titles, `strictOrder.compare(a,b) == 0` holds only when **both ID and title components match**. This is consistent with the record's default `equals`, so `strictSet` keeps all three articles.

**Important warning:** Appending ID at the end of a comparator does not automatically guarantee consistency with `equals` for every class. You must check precisely which fields determine equality for that class.

## 6. The Opposite Direction: `equals` True Yet `Comparator` Non-Zero

Inconsistency can occur in **both directions**:

- `compare(a,b) == 0` yet `a.equals(b) == false`: a sorted set/map may treat two distinct records as one key.
- `a.equals(b) == true` yet `compare(a,b) != 0`: a sorted set/map may retain two representatives that `equals` considers equal.

Example: a `Product` entity defines equality **solely by ID**, while name is a display attribute. Two versions of the same ID with different names are still equal under `equals` yet differ under a comparator that compares only names.

**File `IdEqualityComparatorDemo.java`:**

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class IdEqualityComparatorDemo {
    static final class Product {
        private final long id;
        private final String label;

        Product(long id, String label) {
            this.id = id;
            this.label = label;
        }

        long id() {
            return id;
        }

        String label() {
            return label;
        }

        @Override
        public boolean equals(Object obj) {
            return this == obj
                    || (obj instanceof Product other && id == other.id);
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Product oldVersion = new Product(5L, "A");
        Product newVersion = new Product(5L, "Z");

        Comparator<Product> forDisplay =
                Comparator.comparing(Product::label);
        Comparator<Product> byIdentity =
                Comparator.comparingLong(Product::id);

        Set<Product> hashSet = new HashSet<>();
        hashSet.add(oldVersion);
        hashSet.add(newVersion);

        Set<Product> displaySet = new TreeSet<>(forDisplay);
        displaySet.add(oldVersion);
        displaySet.add(newVersion);

        Set<Product> identitySet = new TreeSet<>(byIdentity);
        identitySet.add(oldVersion);
        identitySet.add(newVersion);

        System.out.println("equals by id: "
                + oldVersion.equals(newVersion));
        System.out.println("display comparator nonzero: "
                + (forDisplay.compare(oldVersion, newVersion) != 0));
        System.out.println("identity comparator zero: "
                + (byIdentity.compare(oldVersion, newVersion) == 0));
        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet by display size: "
                + displaySet.size());
        System.out.println("TreeSet by id size: "
                + identitySet.size());
    }
}
```

```bash
javac IdEqualityComparatorDemo.java
java IdEqualityComparatorDemo
```

**Exact output:**

```text
equals by id: true
display comparator nonzero: true
identity comparator zero: true
HashSet size: 1
TreeSet by display size: 2
TreeSet by id size: 1
```

Here `forDisplay` is still useful for **sorting a list by name**. However, if used in a `TreeSet`, the set can accept two representatives with the same ID. `byIdentity` is the one consistent with `Product`'s `equals`, because both care only about ID.

To have both **uniqueness by ID** and **display by name**, you can hold records in a `Map<Long,Product>` (keyed by ID), extract the values into a list, and sort the list by name. The two responsibilities are cleanly separated and easier to test.

## 7. Tie-Breakers Make Order Deterministic Without Replacing `equals`

`thenComparing`, `thenComparingInt`, and `thenComparingLong` add secondary ordering when preceding criteria tie. Example with `Member`:

```java
Comparator<Member> ranking =
        Comparator.comparingInt(Member::score)
                .reversed()
                .thenComparing(Member::name)
                .thenComparingInt(Member::id);
```

This is an illustrative snippet assuming `Member` is declared as in section 3. It sorts by descending score, then ascending name, and finally ascending ID.

If `Member` is a record consisting of exactly `id`, `name`, and `score` with non-`null` names, the comparator above is consistent with the record's `equals`: `compare == 0` if and only if all three components match.

However, for an entity class whose `equals` **checks only ID**, a comparator checking name first then ID is **not necessarily** consistent: two entities with the same ID after a name change can still compare non-zero. Always examine the specific class's contract instead of applying a blanket "append ID at the end" trick everywhere.

**When is no tie-breaker needed?** When the UI intentionally displays two people with the same score/name at the same rank or accepts the original order. In that case, keeping the display comparator and using `List.sort` makes sense.

**When should a tie-breaker be used?** When you want reproducible ordering across multiple data loads, report exports, or pagination. A stable key like ID guarantees deterministic order even when multiple elements share the same name and score.

### 7.1. Stable sort differs from globally deterministic order

`List.sort` preserves the relative order of elements with `compare == 0` in the **source list**. However, if the input list comes from a source without a guaranteed order (such as a hash set), the order of tied elements is not necessarily stable across separate data fetches.

If consistent pagination is required, add a secondary criterion sufficient to determine order. That is an **ordering** concern, not a reason to change `equals`.

## 8. Comparator Does Not Determine `hashCode`

The `hashCode` contract is tied to `equals`:

```text
a.equals(b) == true
    ⇒ a.hashCode() == b.hashCode()
```

A comparator used solely for display does not alter the `hashCode` method. Two records sharing a sort key may have different hash codes if they are not equal under `equals`. There is no rule requiring `compare(a,b) == 0` to imply equal `hashCode`.

`TreeSet` and `TreeMap` also **do not use `hashCode`** when deciding element/key equivalence; they rely on `compare == 0`. Hence changing `hashCode` cannot fix a bug where a `TreeSet` accidentally merges different IDs because a comparator looks only at name.

Make the distinction clear:

```text
UI sorting               -> Comparator with List.sort / Stream.sorted
Object equality          -> equals
Hash set or hash map     -> equals + hashCode
Ordered set or map       -> Comparator / Comparable
```

## 9. Common Issues with Comparators Used for UI

### 9.1. Case-insensitive string sorting

`String.CASE_INSENSITIVE_ORDER` sorts names case-insensitively. Yet `"java"` and `"JAVA"` can be treated as equivalent in a `TreeSet<String>` using that comparator, even though `String.equals` returns `false`.

If the UI must follow linguistic rules, consider `java.text.Collator` with an appropriate `Locale`. A collator can also treat different strings as equivalent at a given comparison strength, so specify clearly whether it is used solely for display sorting or also allowed to govern keys.

### 9.2. Null values

When sort keys can be `null`, many comparators built with `Comparator.comparing` need a null-supporting comparator. Example:

```java
Comparator<Article> byTitle =
        Comparator.comparing(
                Article::title,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

This is an illustration using the `Article` record from section 5. Null titles sort last, yet multiple records with `null` still share the same sort key. That is fine when sorting a `List`, but requires caution when used as a comparator for `TreeSet`.

### 9.3. Numeric comparisons

Avoid writing integer comparators using subtraction:

```java
// Can overflow for large int values:
(a, b) -> a - b
```

Use `Integer.compare(a,b)` or `Comparator.comparingInt(...)` to preserve proper order. For `double`, use `Double.compare` or `comparingDouble` and understand the NaN/signed-zero rules when needed. A comparator does not turn floating-point comparison into an approximate tolerance check.

### 9.4. Mutable fields

If an object is added to a `TreeSet`/`TreeMap` and a field governing its order is later mutated, the tree structure may no longer look up the entry correctly at its initial key position. Avoid modifying fields used by the comparator while the key resides in an ordered structure. With a list, you can update data and re-sort as required by the UI.

## 10. Workflow for Choosing a Solution

1. **Define equality from business semantics:** unique ID, all record components, SKU code, combination of value fields, or another explicit rule.
2. **Define display keys independently:** score, name, date, price, status… and ascending/descending direction.
3. **Choose the collection:** `List` for full display; `HashSet`/`HashMap` for uniqueness by `equals/hashCode`; `TreeSet`/`TreeMap` only when you truly want equivalence per the comparator.
4. **Consider a tie-breaker:** add a stable key if deterministic ordering is needed, especially for pagination.
5. **Check both consistency directions** if using a sorted set/map: the case `compare == 0` yet `equals == false`, and `equals == true` yet `compare != 0`.
6. **Test edge data:** `null` keys, varying case, duplicate names, state mutations, or inputs without a stable source order.

| Need | Suitable implementation |
| --- | --- |
| Sort member list by score/name, keep all IDs | `List.sort(displayComparator)` |
| Reproducible sorted output | Add a sufficiently stable tie-breaker |
| Unique products by ID | Use ID as map key or define `equals/hashCode` by ID |
| Unique set by `equals` | `HashSet` |
| Ordered set unique by the same `equals` | `TreeSet` with a consistent-with-equals comparator |
| Intentionally merge strings case-insensitively | `TreeSet`/`TreeMap` with that comparator when merging policy is accepted |
| Group objects sharing a display key without losing records | `Map<GroupKey, List<Item>>` or an equivalent grouping operation |

## 11. Common Conceptual Pitfalls

| Misconception | Correct understanding |
| --- | --- |
| "Comparator returning `0` means `equals` returns `true`." | Only true for a comparator **consistent with equals**. |
| "Two elements with the same sort key are the same object." | They can have two different IDs. |
| "`List.sort` drops tied records." | No, it only changes order. |
| "`TreeSet` uses `equals` to check duplicates." | It uses `compare == 0` via comparator/natural ordering. |
| "Appending ID at the end always creates a comparator consistent with equals." | It depends on which fields govern the class's `equals`. |
| "If a comparator is for display, TreeMap also just sorts." | In `TreeMap`, the comparator also defines key equivalence and can overwrite values. |
| "Fixing `hashCode` fixes TreeSet over-merging." | TreeSet does not use hashCode to detect duplicate elements. |
| "To sort by name, you must override equals by name." | No, a comparator can be defined independently without changing equality. |

## 12. Self-Check

**Question 1.** Two employees have different IDs but the same score and name. A score/name comparator returns `0`. Can we conclude `equals` is `true`?

**Answer:** No. The comparator only confirms they share the display sort key; `equals` depends on the class contract.

**Question 2.** When sorting a `List` by score, will one of two people with the same score be lost?

**Answer:** No. `List.sort` retains every element, and because it is stable, it preserves the relative order of elements for which the comparator returns `0`.

**Question 3.** Why can a `TreeSet` end up with only one element after adding two objects that differ under `equals`?

**Answer:** Because the TreeSet's comparator may return `0` for both, causing TreeSet to treat them as one equivalent element.

**Question 4.** A `TreeMap` compares article keys by case-insensitive title. What happens when inserting `"Java"` and then `"JAVA"`?

**Answer:** If the comparator compares only case-insensitive titles, the two keys are equivalent; the second `put` updates the existing entry's value without creating a second entry.

**Question 5.** `Product.equals` compares only ID; the comparator compares name then ID. Is it consistent with equals?

**Answer:** Not necessarily. Two versions with the same ID but different names are equal under `equals`, whereas the comparator can return non-`0`.

**Question 6.** An application needs products unique by ID and displayed sorted by name. How should this be handled?

**Answer:** Manage keys by ID in a map or suitable collection, then create a list of data to sort by name. If stable pagination is needed, append ID to the list sorting criteria.

## Conclusion

**`Comparator` defines ordering, while `equals` defines object equality.** A comparator used for display can return `0` for records that differ under `equals` without data loss if used solely with `List.sort`. However, `TreeSet`/`TreeMap` treat `compare == 0` as element/key equivalence, so a display comparator can merge records or unintentionally update values. Whenever you need a sorted set/map that respects object equality, check both directions of the **consistent with equals** condition. Keep business equality policy separate from UI sorting requirements.