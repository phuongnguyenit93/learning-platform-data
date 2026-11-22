# Null Policy and Lack of Iteration Order Guarantees

## 1. Two Independent Questions When Using a Hash-Based Set

When using `HashSet`, you need to distinguish between:

1. **Which values are allowed to be present?** `HashSet` allows `null`, though still with at most one occurrence of `null`.
2. **In what order are values iterated?** `HashSet` does not guarantee insertion order, sorted order, or a fixed iteration order over time.

A policy that allows `null` does not give `null` a privileged position. The fact that `null` appears first in one printout is not a contract that it will always come first.

Similarly, "hash-based" is a storage and lookup mechanism; it does not by itself determine every policy of a class. `LinkedHashSet` is also hash-based, yet it adds an insertion-order guarantee. A key set from `ConcurrentHashMap` is also hash-based, yet it does not allow adding `null`.

Therefore, accurate statements must be tied to the **specific class or creation method**, not merely to the label "hash-based Set".

The [Java 17 HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) documentation states both that `null` is permitted and that iteration order is not guaranteed. This article uses `HashSet` as the primary case, targeting Java 17 or later with sequential single-threaded operations.

## 2. `null` in `HashSet` Is a Present Value, Not an Empty Set

### 2.1. At Most One `null`

For a standard mutable `HashSet`:

| Call | Meaning |
| --- | --- |
| `add(null)` when `null` is not yet present | Adds `null`, returns `true` |
| `add(null)` when `null` is already present | Does not add a second copy, returns `false` |
| `contains(null)` | Checks whether `null` is in the set |
| `remove(null)` when currently present | Removes `null`, returns `true` |
| `remove(null)` when not present | Leaves the set unchanged, returns `false` |

A `Set` does not track occurrence counts. If a source contains ten `null` values, transferring them into a `HashSet` does not retain the information that "data was missing ten times".

`null` still counts toward `size`. A set containing only `null` has `size` equal to `1` and `isEmpty` returns `false`.

### 2.2. `null` Is Different from the Empty String and the String `"null"`

These three cases are distinct:

```text
null       : no reference to a String object.
""         : a String with empty content.
"null"     : a String containing the four characters n, u, l, l.
```
A `HashSet<String>` can contain all three simultaneously, because they are not the same value under equality.

The type parameter `String` does not mean every element is guaranteed to be non-null. Java's standard type system does not automatically forbid `null` just because a variable is declared as `Set<String>`.

Do not replace `null` with the string `"null"` or the empty string on your own without a business policy. Doing so can conflate missing data with a real text value.

### 2.3. `HashSet` Handling `null` Does Not Mean Calling Code Can Ignore `null`

`HashSet` supports storing and querying `null`. However, after retrieving an element, calling a method on a `null` reference can still throw a `NullPointerException`.

```java
// Illustrative snippet: values may contain null.
for (String value : values) {
    if (value == null) {
        handleMissingValue();
    } else {
        handleText(value);
    }
}
```
The fact that `HashSet` does not throw on `add(null)` does not guarantee that a downstream string-processing function, comparator, or collection-accepting API also accepts `null`.

If the application does not allow missing data, validate at the input boundary rather than relying on `HashSet` happening to allow storing it.

## 3. Runnable Example: Adding, Counting, and Removing `null`

Save the program to `HashSetNullSemanticsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class HashSetNullSemanticsDemo {
    public static void main(String[] args) {
        Set<String> values = new HashSet<>();

        System.out.println("add first null = " + values.add(null));
        System.out.println("add second null = " + values.add(null));
        System.out.println("size after null adds = " + values.size());
        System.out.println("contains null = " + values.contains(null));
        System.out.println("empty while containing null = " + values.isEmpty());

        values.add("");
        values.add("null");
        values.add("A");
        System.out.println("size with distinct text values = " + values.size());
        System.out.println("contains empty text = " + values.contains(""));
        System.out.println("contains literal null text = " + values.contains("null"));

        int nullCount = 0;
        int textCount = 0;
        for (String value : values) {
            if (value == null) {
                nullCount++;
            } else {
                textCount++;
            }
        }
        System.out.println("null elements seen = " + nullCount);
        System.out.println("non-null elements seen = " + textCount);

        System.out.println("remove null = " + values.remove(null));
        System.out.println("remove null again = " + values.remove(null));
        System.out.println("contains null after removal = " + values.contains(null));
        System.out.println("remaining size = " + values.size());
    }
}
```
Compile and run:

```shell
javac --release 17 HashSetNullSemanticsDemo.java
java HashSetNullSemanticsDemo
```
Output:

```text
add first null = true
add second null = false
size after null adds = 1
contains null = true
empty while containing null = false
size with distinct text values = 4
contains empty text = true
contains literal null text = true
null elements seen = 1
non-null elements seen = 3
remove null = true
remove null again = false
contains null after removal = false
remaining size = 3
```
Explanation:

- Two calls to `add(null)` produce only one presence.
- A set containing `null` is not empty.
- Adding the empty string, the string `"null"`, and `A` brings the total number of distinct values to four.
- A single traversal sees one `null` and three non-null `String`s.
- Removing `null` the first time modifies the set; the second time there is no `null` left to remove.

The program does not print the entire `HashSet` in a fixed order. The traversal counters produce the same result regardless of the order in which elements are encountered.

This is also the contract-appropriate way to verify behavior: check presence, `size`, and the count of elements matching a condition, rather than assigning meaning to the observed position of `null`.

## 4. Collection Policy and Business Meaning Are Not the Same Thing

### 4.1. Allowed Does Not Mean Required

`HashSet` allows `null`, but a business layer may require every code to be non-null. In that case, you can validate before inserting into the set.

```java
// Illustrative snippet: Objects is in java.util.
String validCode = Objects.requireNonNull(code, "code");
codes.add(validCode);
```
This is an explicit data policy; there is no need to switch to a different set type just to trigger an error on `null`.

Conversely, if `null` has an accepted meaning, that meaning must be documented: missing value, unspecified, or a particular special state. A `Set` only records presence; it does not automatically distinguish multiple different causes that are all encoded as `null`.

### 4.2. A `null` `Set` Variable Differs from `null` as an Element

```text
Set<String> values = null;
-> No Set object on which to call methods.

A created HashSet containing null:
-> There is a Set object; null is one of its members.
```
Calling `values.contains(null)` when `values` itself is `null` still throws a `NullPointerException` before any valid collection operation takes place.

A method may require a non-null `Set` argument while allowing `null` elements. Or it may require both to be non-null. The contract should state these two levels clearly.

### 4.3. Do Not Use `null` to Hold Multiple Distinct Missing Records

If each missing record needs to be tracked individually, putting all of them into the same `null` value in a `Set` collapses them into a single presence.

You may need a record type with its own identifier or a collection that preserves occurrences. This decision belongs to the data model; a `HashSet` that allows `null` does not solve the requirement of counting or distinguishing individual missing cases.

## 5. What Does "No Order Guarantee" Mean?

### 5.1. Not Insertion Order

Given inputs `z`, `a`, `m`, `HashSet` does not promise that the iterator will return `z`, then `a`, then `m`.

If you need to preserve first-appearance order while deduplicating, you must preserve that information from the source and choose a representation with the corresponding contract, such as `LinkedHashSet`.

### 5.2. Not Sorted Order

`HashSet` does not automatically sort alphabetically, numerically, by id, by priority, or by `hashCode`.

Even if a small set of numbers happens to print in ascending order, do not treat that observation as an API rule. A different dataset, a different construction path, or a different environment may not produce the same result.

If you want the smallest element, use a selection operation based on a defined ordering—do not take the first element from the iterator and call it the minimum.

### 5.3. Does Not Mean "Always Randomly Shuffled"

Having no guarantee does not mean every iteration must differ from the previous one. In a specific environment, with an unchanged state, you may observe identical printouts multiple times.

That does not create a guarantee that the program is allowed to rely on. Nor does it prove that `HashSet` is a fair random-choice generator.

If the goal is random selection, use an appropriate selection algorithm. If the goal is deterministic output, use a clearly specified ordering. `HashSet` does not provide either of those through its "first element".

### 5.4. No Guaranteed Special Position for `null`

An implementation may use internal conventions to store `null`, but the `HashSet` API does not specify that "`null` is always iterated first" or "`null` is always at the end".

Do not write tests or algorithms under that assumption. Presence policy and iteration position are two separate contracts.

## 6. Why a Hash Structure Does Not Automatically Preserve Input Order

A hash set organizes values to support presence lookup, using hash information and an internal storage structure.

The observed iteration order can be influenced by:

- Hash codes and how elements are distributed in the table.
- Capacity and structural resizing operations.
- Additions, removals, and current state.
- Implementation details of the library/JVM version.

This is a mechanical explanation, not an API formula for predicting order.

You do not need to memorize how each bucket is mapped to use `HashSet` correctly. What matters is that **insertion-order information is not part of the class's guarantees**, so it cannot be used as a list that recorded input history.

Adding or removing elements may change the order, but not every operation is required to produce a different order. A test that deliberately adds an element and requires the order to change is also testing something the API does not require.

`LinkedHashSet` adds links to preserve insertion order. It shows that "hash-based" and "guaranteed iteration order" can coexist when the class provides the additional contract.

## 7. When Output Must Be Stable, Choose a Meaningful Order

### 7.1. Need to Preserve First-Appearance Order

Use an appropriately ordered source and pass it directly into a `LinkedHashSet`:

```java
// Illustrative snippet: input has an encounter order that the program needs to preserve.
Set<String> values = new LinkedHashSet<>(input);
```
[Java 17 LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) allows `null` and preserves insertion order. Therefore, `null` is positioned according to when it was first added, just like other values.

Re-adding an already present element does not automatically move it to the end. If it is removed and then re-added, that is a new insertion and should be understood separately.

If you have already discarded the source and only have a `HashSet` left, copying it into a `LinkedHashSet` only preserves the encounter order from the `HashSet` at copy time. It cannot recover the original input history that is no longer available.

### 7.2. Need a Comparison-Based Order

You can create a list from the set and sort it by an explicit rule. When `null` is present, the comparator must also handle `null`.

```java
// Illustrative snippet.
List<String> display = new ArrayList<>(values);
display.sort(Comparator.nullsLast(Comparator.naturalOrder()));
```
In this `String` example:

- Non-null `String`s are compared in natural order.
- `null` is placed after the `String`s.
- Sorting creates an intentional presentation order.
- The source `HashSet` does not thereby turn into a set with a guaranteed order.

You can choose `nullsFirst` if the requirement is to place `null` first. See [Java 17 Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) to apply the appropriate `null` comparison rule.

For complex element types, if the comparator treats multiple distinct elements as equal, a stable sort may still preserve the unguaranteed source order among those elements. If fully deterministic output is needed, provide an appropriate tie-breaking rule for cases that are equal on the primary criterion.

### 7.3. Need to Maintain a Sorted Set During Updates

An ordered structure like `TreeSet` can satisfy that requirement, but you must check its comparator, presence criterion, and `null` policy.

Do not blindly copy a `HashSet` containing `null` into a natural-order `TreeSet` and expect all data to be accepted. A new ordering requirement may entail a different input policy.

This article focuses on `HashSet`'s contract; the choice of output ordering should be decided according to specific requirements.

## 8. Runnable Example: No Need to Assume `HashSet` Order

Save to `HashSetOrderContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class HashSetOrderContractDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList("z", null, "a", "z", "m");
        Set<String> hash = new HashSet<>(input);

        System.out.println("distinct count = " + hash.size());
        System.out.println("contains every input value = " + hash.containsAll(input));

        Set<String> sameMembers = new HashSet<>(
                Arrays.asList("m", "a", null, "z"));
        System.out.println("same members from another input order = "
                + hash.equals(sameMembers));

        LinkedHashSet<String> insertionOrder = new LinkedHashSet<>(input);
        System.out.println("LinkedHashSet insertion order = " + insertionOrder);

        List<String> sortedForDisplay = new ArrayList<>(hash);
        sortedForDisplay.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("explicit sorted display = " + sortedForDisplay);

        String arbitrary = hash.iterator().next();
        System.out.println("iterator first belongs to set = "
                + hash.contains(arbitrary));
    }
}
```
Compile and run:

```shell
javac --release 17 HashSetOrderContractDemo.java
java HashSetOrderContractDemo
```
Output:

```text
distinct count = 4
contains every input value = true
same members from another input order = true
LinkedHashSet insertion order = [z, null, a, m]
explicit sorted display = [a, m, z, null]
iterator first belongs to set = true
```
What the program does intentionally:

1. Uses `Arrays.asList` to create an input containing `null`; does not use `List.of` because that factory rejects `null`.
2. `HashSet` has four distinct values from five input occurrences.
3. Two `HashSet`s constructed from different input orders are still equal in membership.
4. `LinkedHashSet` preserves `z`, `null`, `a`, `m` in first-encounter order.
5. The explicitly sorted list produces `a`, `m`, `z`, `null`.
6. The first element of the iterator is named `arbitrary`—an implementation-dependent choice from iteration order, not called the first inserted element or the minimum element.

The final line only verifies that the element returned by the iterator actually belongs to the set. The program does not print a fixed value for `arbitrary`.

Even if a particular run returns `null` first, the contract output must still not be written as "the iterator always returns `null`". This set is non-empty, so `next` has an element to return; if the set is empty, `Iterator.next` has a different failure contract and does not use `null` as a general end-of-iteration marker.

## 9. Not Every Hash-Based `Set` Accepts `null`

### 9.1. Check the Specific Class or Creation Method

| Creation method | `null` policy to understand | Ordering to understand |
| --- | --- | --- |
| `new HashSet<>()` | Allows at most one `null` | No iteration order guarantee |
| `new LinkedHashSet<>()` | Allows at most one `null` | Insertion order |
| `ConcurrentHashMap.newKeySet()` | Disallows adding `null` | Do not use as insertion-ordered or sorted |
| `Set.of(...)` / `Set.copyOf(...)` | Rejects `null` elements | Do not rely on a guaranteed iteration order |
| `Collections.unmodifiableSet(source)` | Reads through `source`; does not filter or forbid existing `null` | Reads order through `source`, does not create a new order |

The two `Set` factory entries are examples of collection contracts; you do not need to—and should not—rely on an assumption that they always share the same internal implementation as `HashSet`.

[Java 17 ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) does not allow `null` as a key; the set created by `newKeySet` is backed by that structure. This shows that `null` handling is a class policy, not a mandatory consequence of having or not having a hash table.

Do not extrapolate that "all concurrent collections have the same `null` policy". Always check the contract of the actual choice.

### 9.2. Switching Classes Can Expose Existing `null` Data

Code that uses `HashSet` may have accepted `null` for a long time. When switching to another creation method to get an unmodifiable result or a different structure, `null` may be rejected.

Therefore, changing a collection class is not just a speed change. You must check whether data policies and ordering guarantees still fit.

If you decide to drop `null`, make it clear that this is policy-based data filtering, not a content-preserving copy. If you decide to throw an error, let callers know the input preconditions.

## 10. Copies, Unmodifiable Views, and `null`

### 10.1. `HashSet` Copy Preserves `null` but Creates No Order Guarantee

`new HashSet<>(source)` can create an independent `Set` structure with the same valid values, including `null` if the source contains `null`.

Adding a new member to `source` after copying does not automatically add it to the copy. However, that copy still has no guaranteed iteration order and does not deep-copy individual element objects.

### 10.2. `Set.copyOf` Does Not Accept `null`

[Set.copyOf in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) returns a structurally unmodifiable `Set` and rejects sources containing `null`.

Therefore, intending "only to protect against add/remove" does not mean replacing every copy with `Set.copyOf` will always preserve the same data contract.

If `null` is valid data, you need an output strategy compatible with `null`. If `null` is invalid, that check can be used as part of an explicit policy, but do not hide the fact that data is being rejected.

### 10.3. `unmodifiableSet` Is a Read-Through View of the Source

According to [Java 17 Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)), the view disallows modification through itself, while queries read through to the source set.

If `source` is a `HashSet` containing `null`, the view can observe `null`. If another reference continues to add to or remove from `source`, the view reflects those changes.

It is not an independent snapshot.

If you need both structural isolation from the source and immutability of the returned view while still accepting `null`, you can create a private copy and wrap it:

```java
// Illustrative snippet: the copy is not exposed externally through another reference.
Set<String> result = Collections.unmodifiableSet(new HashSet<>(source));
```
This pattern still does not create a guaranteed iteration order or deep immutability of elements. If ordering is needed, choose a copy with the corresponding order contract directly in the design.

## 11. Runnable Example: Policy Changes When Copying or Wrapping

Save to `HashSetNullCopyPolicyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class HashSetNullCopyPolicyDemo {
    public static void main(String[] args) {
        Set<String> source = new HashSet<>();
        source.add("B");
        source.add(null);
        source.add("A");

        Set<String> independent = new HashSet<>(source);
        System.out.println("HashSet copy contains null = "
                + independent.contains(null));

        try {
            Set.copyOf(source);
        } catch (NullPointerException ex) {
            System.out.println("Set.copyOf nullable source = "
                    + ex.getClass().getSimpleName());
        }

        Set<String> readOnlyView = Collections.unmodifiableSet(source);
        System.out.println("read-only view contains null = "
                + readOnlyView.contains(null));

        source.add("C");
        System.out.println("view sees later C = " + readOnlyView.contains("C"));
        System.out.println("independent copy sees later C = "
                + independent.contains("C"));

        try {
            readOnlyView.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("read-only view add = "
                    + ex.getClass().getSimpleName());
        }

        List<String> display = new ArrayList<>(readOnlyView);
        display.sort(Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("sorted nullable view = " + display);

        Set<String> concurrent = ConcurrentHashMap.newKeySet();
        try {
            concurrent.add(null);
        } catch (NullPointerException ex) {
            System.out.println("concurrent key set add null = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```
Compile and run:

```shell
javac --release 17 HashSetNullCopyPolicyDemo.java
java HashSetNullCopyPolicyDemo
```
Output:

```text
HashSet copy contains null = true
Set.copyOf nullable source = NullPointerException
read-only view contains null = true
view sees later C = true
independent copy sees later C = false
read-only view add = UnsupportedOperationException
sorted nullable view = [A, B, C, null]
concurrent key set add null = NullPointerException
```
Reading the output by contract:

- The `HashSet` copy accepts `null`.
- `Set.copyOf` on a source containing `null` throws `NullPointerException`.
- The `unmodifiableSet` view reads `null` from the source.
- Adding `C` to the source appears through the view, but not in the independent copy.
- Attempting to add `D` through the view is rejected.
- The display list is explicitly sorted with `null` last.
- The concurrent key set in the example rejects `null`.

The program does not run multiple threads; the `newKeySet` lines only illustrate the `null` policy of a specific `Set` creation method.

By separating the output lines for membership, mutability, and display order, the example avoids lumping them into a vague property like "this Set is safer" or "this Set is better".

## 12. Comparing and Verifying Exactly What the Contract Guarantees

### 12.1. Comparing Set Contents When Order Is Not a Requirement

Two `Set`s adhering to the same equality relation can be `equals` even if they iterate in different orders. To check whether they have the same members, use the `Set.equals` contract or appropriate presence/size checks.

Do not convert both `HashSet`s into `List`s and compare with `List.equals` to decide whether set contents match. `List.equals` takes position into account.

Similarly, `toArray` or `new ArrayList<>(set)` only collects elements in encounter order; it does not sort them or restore insertion history.

### 12.2. When Order Is Required, Verify on Policy-Ordered Output

If the API output must be sorted ascending with `null` last, verify the resulting list after sorting with the chosen comparator.

If the API output must preserve insertion order, retain an ordered source and corresponding structure, and verify that order.

Do not test for an ordering that `HashSet` was never required to provide.

### 12.3. Do Not Rely on Printed Appearance to Distinguish `null`

A `null` and a `String` with content `"null"` can look identical when printing a standard collection. That does not make them equal.

When diagnosing data, use a representation clear enough to distinguish an absent reference from a text value. For example, you can use quotes for strings and a distinct marker for `null` in the presentation layer.

However, a display marker should not be fed back as a data key in place of `null` if doing so collides with a real string.

### 12.4. Things You Should Not Assert in `HashSet` Tests

- Do not assert that `null` is always first or always last.
- Do not assert that two iterations must differ.
- Do not assert that adding or removing an element must change the order.
- Do not assume `HashSet`s with identical contents must have identical `toString` strings.
- Do not treat the absence of `ConcurrentModificationException` as proof of thread safety.

The contract is the basis for choosing what must hold. An internal observation or a single run does not extend that contract.

## 13. Common Mistakes and Mental-Model Fixes

| Misconception | Correct understanding |
| --- | --- |
| "`Set<String>` means `null` is impossible" | Reference types can still accept `null` if the implementation allows it |
| "Adding `null` twice should increase `size` twice" | `HashSet` holds at most one presence of `null` |
| "A set containing only `null` is an empty set" | It has one member |
| "`null` and the string `'null'` are the same data" | They differ in value and meaning |
| "`HashSet` supports `null`, so every element-handling function supports `null`" | Check the contract of each downstream function |
| "`null` has a hash convention, so it definitely comes first during iteration" | There is no such positional guarantee in the `HashSet` API |
| "Unordered means it must reshuffle every time" | Stability may be observed, but cannot be relied upon as a contract |
| "`HashSet` is currently printing in insertion order, so just use it" | When insertion order is needed, choose a structure with that guarantee |
| "Wrapping with `unmodifiableSet` creates a fixed copy" | It is a read-through view of the source |
| "`Set.copyOf` only changes mutability, not `null` policy" | It rejects `null` elements |
| "Converting `HashSet` to `LinkedHashSet` restores insertion history" | It only preserves encounter order from the source at copy time |
| "Sorting `String` data always handles `null` automatically" | An appropriate comparator or `null` policy is required |
| "Since they all use hashing, all `Set`s accept `null`" | The policy belongs to the specific class or creation method |

## 14. Practice: Defining the Output Contract

### Exercise 1: Counting Missing Data

The source has `null`, `null`, `A`. Putting them into a `HashSet` and checking `size` cannot tell you there were two missing records. The set only represents the presence of `null` and `A`. To track how many times data was missing, retain or count occurrences.

### Exercise 2: Printed Output Shows Two `null`s

A `Set` holding both `null` and the `String` `"null"` does not necessarily violate deduplication, even though printed output may make them look alike. Check using `value == null` or an unambiguous diagnostic format instead of just eyeballing printed text.

### Exercise 3: Insertion Order Needed

The source has `B`, `null`, `A`, `B`. If you want the output `B`, `null`, `A` by first appearance, use an order-preserving structure directly from that source. Do not collect into a `HashSet` and then try to reconstruct insertion order afterward.

### Exercise 4: Sorting Needed with `null` Last

Given values `B`, `null`, `A`, create a list copy and use `Comparator.nullsLast` with a comparator for non-null values. The resulting presentation `A`, `B`, `null` comes from the comparator, not from `HashSet` inherently having that order.

### Exercise 5: Unmodifiable Result Needed, but `null` Is Valid

`Set.copyOf` does not satisfy a policy that accepts `null`. You can create a private copy using a `null`-permitting structure and wrap it as unmodifiable, while explicitly deciding whether an order guarantee is needed. Mutable elements still require their own policy.

### Exercise 6: Switching to a `ConcurrentHashMap` Key Set

Do not assume `null` is still accepted just because both the old and new structures use hashing. Check and decide how to handle `null` before switching. The example program confirmed that `newKeySet` rejects adding `null`.

### Exercise 7: Picking the First Element

A `HashSet` is non-empty and `iterator.next` returns an element. That does not prove it is the minimum value, the first inserted value, or a fair random choice. Use an algorithm matching your actual goal.

Before using a hash-based `Set`, state separately **what `null` means, which collection accepts it, how downstream functions handle it, and what ordering (if any) the output requires**. Both the data policy and the ordering policy must remain clear from input all the way to result presentation.
