# addAll, containsAll, removeAll, and retainAll

When working with multiple elements, we often need to merge data, verify a group of requirements, remove blocked values, or keep only accepted values. Java provides four methods under the `Collection` general contract for these scenarios: `addAll`, `containsAll`, `removeAll`, and `retainAll`.

The key point is not the word “All”, but three questions: **which collection is the receiver of the call, what role does the argument collection play, and does the result mutate the data?** Without distinguishing these three things, a program can still run while deleting the wrong data or checking requirements incorrectly.

This lesson uses Java 17 and focuses on the contracts and application of these four methods. The complete program has its filename, run commands, and output in the demonstration section. Other short Java snippets are illustrative excerpts, not standalone programs.

## 1. General Model: Receiver and Argument Collection

Consider the call:

```java
a.removeAll(b);
```

- `a` is the receiver collection, and also the one that may be modified.
- `b` provides the criteria for the elements to remove.
- The method does not create a new result collection to return.
- If the call completes normally, the returned `boolean` indicates whether `a` was modified.

With `containsAll`, the role is different: `a` is checked to see whether it contains all the values present in `b`; this method is not an operation that modifies the collection's structure.

Orientation table:

| Call | How to read it | Role of the argument | Mutates the receiver? |
| --- | --- | --- | --- |
| `a.addAll(b)` | Add the elements of `b` into `a` | Element source | Possibly |
| `a.containsAll(b)` | Does `a` contain every value that `b` requires? | Group to check | No, by operation contract |
| `a.removeAll(b)` | Remove from `a` every element belonging to `b` | Group to remove | Possibly |
| `a.retainAll(b)` | Keep in `a` only the elements belonging to `b` | Group to keep | Possibly |

Swapping `a` and `b` usually changes both the question being asked and the data being modified. For example, “granted permissions contain the required permissions” must be written in the direction `granted.containsAll(required)`.

These methods are declared in [Java 17 Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html). `List`, `Set`, `Queue`, and related classes inherit that contract through the interface hierarchy. `Map` is not a `Collection`; to operate on a map's keys, values, or entries, you must explicitly specify the corresponding view.

## 2. Read the Signatures Before Reading Examples

The four signatures are:

```java
boolean addAll(Collection<? extends E> c);
boolean containsAll(Collection<?> c);
boolean removeAll(Collection<?> c);
boolean retainAll(Collection<?> c);
```

The block above only lists the method declarations, not code to place directly inside `main`.

### 2.1. Why does addAll have ? extends E?

`addAll` inserts elements from a source into the receiver collection. Therefore, the source must provide elements compatible with type `E`.

Illustrative snippet:

```java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2, 3);

numbers.addAll(integers);
```

`Integer` is a subtype of `Number`, so those elements are accepted. This does not mean `List<Integer>` is a subtype of `List<Number>`; the wildcard on the method parameter itself allows accepting a compatible source.

### 2.2. Why do the other three methods accept Collection<?>?

They check containment or filter elements that are already in the receiver collection. They do not need to copy elements from the argument into the receiver.

For example, the following expression compiles:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2));
boolean changed = numbers.removeAll(List.of("x"));
```

With `ArrayList` in this example, no element matches, so the list remains unchanged and `changed` is `false`.

However, do not generalize this into “querying with an incompatible type always returns `false`”. Some collections restrict element types or how elements are compared and may throw an exception according to their contract. A signature allowing compilation does not prove that every collection accepts every value at runtime.

## 3. addAll: Adding Multiple Elements to the Receiver Collection

### 3.1. Adds elements, not the entire collection as a single element

Illustrative snippet:

```java
List<String> a = new ArrayList<>(List.of("A", "B"));
List<String> b = List.of("B", "C");

boolean changed = a.addAll(b);
```

Output:

```text
a = [A, B, B, C]
b = [B, C]
changed = true
```

Here `a` is an `ArrayList`, so the two elements of `b` are appended to the end in the source's order. `b` does not lose its elements.

If you want to hold an entire list as a single element, you need a nested type like `List<List<String>>` and to use `add(b)`. That is a different data model.

### 3.2. List and Set handle duplicate elements differently

With a `List`, adding a value that already exists can still modify the list, because a list allows multiple occurrences.

With a set:

```java
Set<String> codes = new LinkedHashSet<>(List.of("A", "B"));
boolean first = codes.addAll(List.of("B", "C", "C"));
boolean second = codes.addAll(List.of("A", "B"));
```

Output:

```text
codes = [A, B, C]
first = true
second = false
```

The first call adds the new value `"C"`; the remaining occurrences do not create duplicates in the set. The second call has no new values, so it does not modify the set.

Do not infer that every `Set` prints in insertion order. The example chooses `LinkedHashSet` so the observed order is deterministic. A `HashSet` does not provide the same iteration-order guarantee.

### 3.3. The returned boolean expresses mutation

`false` does not mean the operation failed. It can indicate that all elements from the source were already present in a set.

If the operation is unsupported, an element is invalid, or an element cannot be added due to other restrictions, the method may throw an exception. Do not use `false` as a catch-all branch for data-insertion errors.

With a modifiable `ArrayList` and an independent, non-empty source, calling `addAll` increases the size. With a set, a non-empty source can still produce no change.

### 3.4. Ordering depends on the collection type

The `Collection` contract does not turn every structure into a list. `List.addAll` has rules for appending elements; a sorted or priority-based structure continues organizing data according to its own rules.

Do not call `addAll` and assume the iteration order of the entire collection matches the source's order. You need to read the contract of the interface and class being used.

## 4. containsAll: Checking the Presence of Every Required Value

### 4.1. This is a directional question

Illustrative snippet:

```java
Set<String> granted = Set.of("READ", "WRITE");
Set<String> required = Set.of("READ");

boolean allowed = granted.containsAll(required);
```

`allowed` is `true`. If reversed, `required.containsAll(granted)` is `false` because `required` does not contain `"WRITE"`.

You can use the following mental model:

```text
for each value x in the argument collection:
    if the receiver collection does not contain x:
        return false
return true
```

This is a model for understanding semantics, not a guarantee that every class executes that exact loop.

### 4.2. Does not check occurrence counts

Illustrative snippet:

```java
List<String> available = List.of("A");
boolean result = available.containsAll(List.of("A", "A", "A"));
```

`result` is `true`: each check for the value `"A"` sees that the value exists.

There is no mechanism to “consume one occurrence and look for the next”. Therefore, do not use `containsAll` to prove that inventory has three units of an item just because the shopping cart contains the same item code three times.

When quantity is a condition, you must count by value—for example, using a `Map<String, Integer>`—and compare the required quantity against the available quantity.

### 4.3. Does not check order, contiguous sublists, or list equality

The expression:

```java
List.of("A", "B").containsAll(List.of("B", "A"))
```

returns `true`. It does not require elements to appear in the same order as in the argument.

Even two lists of the same size that contain all of each other's values are not guaranteed to have the same duplicate counts:

```text
a = [A, A, B]
b = [A, B, B]
```

Both `containsAll` calls in either direction return `true`, yet the two lists are not equal.

Choose the check according to your need:

| Need | Approach |
| --- | --- |
| Every required value is present | `containsAll` |
| Two lists have the same element at each position | `List.equals` |
| Same values and same occurrence counts, regardless of order | Compare frequency tables |
| A group is a contiguous segment in a list | Check sublist or use an appropriate subsequence search |
| At least one value in common | Check for non-empty intersection, do not use `containsAll` instead |

### 4.4. Empty argument collection

A collection contains every element of an empty collection because there are no values to check. Thus `a.containsAll(empty)` is `true` for any valid empty argument, even when `a` itself is empty.

In business validation, that may be expected or it may mask an input data error. If a list of required permissions is not allowed to be empty by workflow rules, you must verify that condition separately. `containsAll` does not know whether “no requirements” is a valid application configuration.

## 5. removeAll: Removing Every Occurrence of Specified Values

### 5.1. Removal by membership

Given:

```text
a = [A, B, A, C]
b = [A, X]
```

after `a.removeAll(b)`, list `a` is `[B, C]`; the return value is `true`.

Both occurrences of `"A"` are removed. `"X"` is not in `a`, so it has no additional effect. The argument does not need to contain `"A"` twice to remove both occurrences from the list.

Mental model:

```text
keep each element x of a when x is not in b
```

### 5.2. Difference from single-element remove

Given an `ArrayList<String>` containing `[A, B, A]`:

- `remove("A")` removes one matching occurrence.
- `removeAll(List.of("A"))` removes all occurrences of `"A"`.

`removeAll` is not a quantity-aware subtraction. If you have three units of an item and only want to subtract one unit, use an algorithm or data type suited for representing quantities.

### 5.3. Calling it again may return false

Once all `"A"` elements have been removed, calling `removeAll` again with the same removal group no longer modifies the list.

This is useful when you only need to know whether a change occurred in order to update a UI or record state. However, do not use it as proof that an external business operation also happened exactly once.

### 5.4. Use cases

`removeAll` fits requirements such as:

- Removing item codes that belong to a discontinued list.
- Removing blocked tags from an existing tag group.
- Computing elements present in a first group but not in a second group.
- Filtering out already-processed values when processing counts do not matter.

If you need to preserve the original data, create a separate result structure before calling it.

## 6. retainAll: Filtering the Receiver Collection by a Keep Group

### 6.1. Keeps only existing elements

Given:

```text
a = [A, B, A, C]
b = [A, C, X]
```

after `a.retainAll(b)`, `a` is `[A, A, C]`; the return value is `true`.

Three points to observe:

1. `"B"` is removed because it is not in the keep group.
2. Both occurrences of `"A"` remain because a list allows duplicates.
3. `"X"` is not added: the argument is a filter criterion, not a source for adding missing elements.

Mental model:

```text
keep each element x of a when x is in b
```

### 6.2. For List, this is not a quantity-aware intersection

If `a = [A, A, A]` and `b = [A]`, `retainAll` keeps all three `"A"` elements in `a`.

If the problem requires the intersection of two groups taking the minimum count on each side, the result needs one `"A"`; `retainAll` does not perform that operation.

For two sets with consistent equality, `retainAll` expresses set intersection in the familiar way. For lists, read it as **filtering by presence**, taking care not to overlook duplicate elements.

### 6.3. Preserves the order of remaining elements in a List

Filtering a list does not sort it by the argument. If the initial list is `[C, A, B, A]` and the argument is `[A, C]`, after filtering it becomes `[C, A, A]`.

The criteria source does not impose its order on the receiver list.

### 6.4. An empty argument removes all existing elements

With a modifiable list:

```java
List<String> selected = new ArrayList<>(List.of("A", "B"));
selected.retainAll(List.of());
```

the `selected` list becomes empty.

This is the correct behavior: no value is in the keep group. If an application treats an empty allowed-list as “configuration not yet loaded”, calling `retainAll` immediately can wipe out selected data. You must distinguish a load failure from a legitimately empty allowed set.

## 7. Side-by-Side Comparison on the Same Initial Data

In the table below, each row starts from an independent `ArrayList` containing `[A, B, A, C]`. The argument is `[A, D]`.

| Method | Return value | Contents after call | Interpretation |
| --- | --- | --- | --- |
| `addAll` | `true` | `[A, B, A, C, A, D]` | Appends elements from the source |
| `containsAll` | `false` | `[A, B, A, C]` | Missing `D` |
| `removeAll` | `true` | `[B, C]` | Removes every element in the argument |
| `retainAll` | `true` | `[A, A]` | Keeps only elements in the argument |

Do not feed the output of one row into the next row and expect it to still match this table. Three of the four methods can mutate the receiver.

## 8. Empty Cases and Boolean Values

The table below applies to a modifiable `ArrayList` with independent, valid inputs:

| Scenario | Result | Receiver state |
| --- | --- | --- |
| `a.addAll(empty)` | `false` | Unchanged |
| `a.containsAll(empty)` | `true` | Unchanged |
| `empty.containsAll(nonEmpty)` | `false` | Unchanged |
| `a.removeAll(empty)` | `false` | Unchanged |
| `nonEmpty.retainAll(empty)` | `true` | Becomes empty |
| `empty.retainAll(empty)` | `false` | Remains empty |
| `empty.addAll(nonEmpty)` | `true` | Contains the source elements |
| `empty.removeAll(nonEmpty)` | `false` | Remains empty |

Separate the two meanings of `boolean`:

- `containsAll`: the answer to the containment condition.
- `addAll`, `removeAll`, `retainAll`: whether the receiver collection was modified when the call completed normally.

Do not call these methods just to test “would it change?” if you do not yet want to mutate the data. The mutating methods perform the modification before returning the result.

## 9. Using with Set Operations and Preserving Original Data

When both inputs are truly sets, you can compute:

```text
union:           copy of A then addAll(B)
intersection:    copy of A then retainAll(B)
difference A−B:  copy of A then removeAll(B)
```

Illustrative snippet:

```java
Set<String> union = new LinkedHashSet<>(a);
union.addAll(b);
```

The name `union` is chosen because this variable represents a new result. Writing `Set<String> union = a;` only creates another reference to the same set; calling `addAll` afterward still mutates `a`.

With lists, choose explicitly:

- Want to keep duplicates: create a result `ArrayList`.
- Want to remove duplicates: create a result `Set`.
- Want to preserve encounter order while deduplicating: choose an implementation with that guarantee, such as `LinkedHashSet`.
- Want to process by occurrence count: use a frequency map or an appropriate multiset algorithm.

Copying a collection in these ways does not deep-copy the individual objects inside it. It separates the container structure, while mutability of the element objects themselves must still be considered separately.

## 10. Equality, Comparator, and Custom Objects

The four methods do not understand concepts like “same person”, “same item code”, or “same permission” unless the data model expresses them.

### 10.1. equals and hashCode

For collections that use value-based equality, results depend on how the element class defines `equals`. When using hash-based structures, `hashCode` must be consistent with `equals`.

If two objects share the same business code but still rely on `Object` reference-identity equality, `containsAll` may fail to find an object that a developer assumes is “the same”.

Decide on equality criteria before using collections as a data-matching tool.

### 10.2. Ordered comparison collections

A `TreeSet` determines equivalence through comparison. If the comparator is inconsistent with `equals`, cross-collection matching operations can produce results that contradict intuition from the set contract.

Do not arbitrarily mix a case-insensitive sorted set with a collection using `String.equals` and assume they share the same equality relation. You can normalize data into consistent comparison keys before performing operations.

### 10.3. Do not depend on the number of equals calls

For explanation, you can picture a membership-checking loop. However, never design business code around the assumption that `equals` will be called a specific number of times or in a fixed order. Implementations are free to optimize in any way that satisfies the contract.

The base classes [AbstractCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractCollection.html) and [AbstractSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractSet.html) illustrate different implementation strategies. They are helpful for understanding mechanics, but they do not replace the contract of the actual class in use.

## 11. Mutability, Exceptions, and Partial Effects

### 11.1. The three mutating operations are optional

`addAll`, `removeAll`, and `retainAll` are not supported by every collection.

Example:

```java
List<String> fixed = List.of("A", "B");
fixed.removeAll(List.of("A"));
```

The mutating call above throws `UnsupportedOperationException`. To modify it, you can create `new ArrayList<>(fixed)` and operate on the new copy.

A fixed-size list from `Arrays.asList` is not a list that supports adding or removing. The fact that it supports `set` does not imply it supports size-changing operations.

### 11.2. Do not rely on empty inputs to avoid exceptions

For an unsupported operation, the collection contract allows even no-op calls to throw `UnsupportedOperationException`. Do not design code around the assumption “there is nothing to remove, so it definitely won't fail”.

The empty-input table above explicitly specified a modifiable `ArrayList`. It is not a promise for arbitrary collections.

### 11.3. null and invalid element types

Distinguish between:

1. Passing `null` instead of the argument collection itself.
2. Passing a valid collection that contains `null` elements.

The four methods do not treat a `null` collection argument as an empty collection; that is an error that may throw `NullPointerException` by contract.

For `null` elements, behavior depends on the capabilities of the participating collections. In `removeAll` and `retainAll`, membership checks may query the argument; therefore, both the receiver collection and the criteria collection must be considered.

Also remember that `List.of(null)` throws an exception immediately when creating the list. That error occurs before calling the bulk method, so do not use it to conclude how the method under test handles `null`.

Other cases may throw `ClassCastException`, `IllegalArgumentException`, or, when capacity is bounded, `IllegalStateException`. Read the exception documentation for the exact method and class.

### 11.4. No all-or-nothing transactional guarantee

The word “All” does not mean atomic.

If an insertion or a membership check throws an exception partway through, the general contract does not guarantee that prior changes will be rolled back. The state after an error depends on the implementation and where the failure occurred.

Do not write logic like:

```text
try mutating the original data with a bulk operation
if an error occurs, assume the original data is unchanged
```

If you need to protect the original structure from partial effects, you can:

1. Create a separate working structure with the appropriate type and semantics.
2. Apply the operation to that structure.
3. Publish the result only after checks succeed.
4. Use appropriate synchronization or transactional mechanisms if publication must be atomic.

This approach does not automatically deep-copy elements and does not undo external side effects of user code, such as a custom `equals` with side effects.

## 12. Aliases, Views, and Unintended Mutation

### 12.1. Two variables pointing to the same collection

Illustrative snippet:

```java
List<String> original = new ArrayList<>(List.of("A", "B"));
List<String> filtered = original;
filtered.retainAll(List.of("A"));
```

`original` also becomes `[A]`, because both variables point to the same object. A new variable name does not create new data.

### 12.2. Views backed by an underlying structure

Views such as `Map.keySet()`, `Map.values()`, or `List.subList(...)` can share data with the backing structure. When removal is supported, `removeAll` or `retainAll` through a view can remove corresponding data in the backing source.

For example, filtering a map's key set with `retainAll` can also remove the map entries whose keys were excluded. This may be the intended goal, but it must be stated clearly in the design.

Do not assume every view allows adding elements just because it is a `Collection`. In particular, adding a new key through a key set typically lacks the value information needed to create a map entry.

### 12.3. Do not use addAll with the same non-empty collection as the source

The general `Collection.addAll` contract leaves behavior undefined if the source is modified while the operation is in progress; it explicitly notes the case where the source is the receiver collection itself and that collection is non-empty.

Therefore, do not write `a.addAll(a)` as a general way to duplicate elements. A specific class might produce a seemingly reasonable result, but that is not a guarantee applicable to every `Collection`.

If you need to repeat a list's contents, create an independent source first:

```java
List<String> extra = new ArrayList<>(a);
a.addAll(extra);
```

Similarly, do not pass a view that overlaps with the receiver as the source without reading the contract. Creating an appropriate snapshot avoids many alias dependencies, though concurrent access must still be addressed if another thread can modify the data.

## 13. Processing Cost and Choosing the Criteria Collection

There is no single time complexity across all implementations of the four methods.

Let:

- `n` be the size of the receiver collection.
- `m` be the size of the argument collection.

If an algorithm iterates over one side and calls `contains` on the other side, the cost depends heavily on the structure used for membership testing.

### 13.1. Intuition with lists

When both sides are lists and existence checks must scan linearly:

- Checking every element of the argument can take roughly `O(n × m)` work.
- Filtering the receiver's elements against a criteria list can have the same order of cost.

Actual time also depends on early termination, duplicate data, and the cost of `equals`. Do not translate complexity expressions into fixed millisecond numbers.

### 13.2. Preparing a Set as criteria

If the equality relation is preserved and the operation genuinely performs repeated membership checks, you can convert the criteria into a `HashSet`:

```java
Set<String> allowed = new HashSet<>(allowedValues);
List<String> result = new ArrayList<>(source);
result.retainAll(allowed);
```

With a well-distributed hash table, membership lookup has near-constant expected cost. Combining building the criteria set and scanning the source can bring the cost model close to linear in total size in suitable cases.

Conditions to consider:

- There is extra cost for building the set and using memory.
- A set drops duplicates; that fits membership filtering, but does not fit if business logic needs counts.
- `equals`–`hashCode` must be implemented correctly.
- Do not switch to `HashSet` if doing so changes the comparison relation the problem relies on.
- For small data or one-off calls, the preparation cost may not be worthwhile.
- An implementation class may have its own algorithm, so check documentation or measure under realistic load.

### 13.3. A HashSet as the receiver is not enough to conclude the operation is always fast

A `removeAll` implementation may choose its iteration direction based on the sizes of both sides. One direction calls `remove` on the receiver set; another iterates over the set and calls `contains` on the argument.

Therefore, looking only at the type of `a` in `a.removeAll(b)` is not enough to claim all work is `O(n + m)`. The `AbstractSet.removeAll` implementation contract is a good example to read to understand the difference.

The documentation for [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) and [HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) helps identify class characteristics, while measurements must use data matching the required result semantics.

## 14. Complete Java Program

The following program uses independent copies so the four groups of results do not accidentally depend on each other's mutations. The data consists of strings, so no custom business equality needs to be defined in the example.

Save to `BulkCollectionDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class BulkCollectionDemo {
    public static void main(String[] args) {
        List<String> source = List.of("A", "B", "A", "C");
        List<String> incoming = List.of("B", "D");

        List<String> appended = new ArrayList<>(source);
        boolean added = appended.addAll(incoming);
        System.out.println("addAll changed: " + added);
        System.out.println("appended: " + appended);

        System.out.println("contains A and D: "
                + appended.containsAll(List.of("A", "D")));
        System.out.println("contains repeated A: "
                + List.of("A").containsAll(List.of("A", "A", "A")));
        System.out.println("contains reversed order: "
                + List.of("A", "B").containsAll(List.of("B", "A")));

        List<String> removed = new ArrayList<>(source);
        boolean removedAny = removed.removeAll(List.of("A", "X"));
        System.out.println("removeAll changed: " + removedAny);
        System.out.println("removed: " + removed);
        System.out.println("removeAll again: "
                + removed.removeAll(List.of("A", "X")));

        List<String> retained = new ArrayList<>(source);
        boolean retainedChanged = retained.retainAll(List.of("A", "C", "X"));
        System.out.println("retainAll changed: " + retainedChanged);
        System.out.println("retained: " + retained);
        System.out.println("retainAll again: "
                + retained.retainAll(List.of("A", "C", "X")));

        Set<String> codes = new LinkedHashSet<>(List.of("A", "B"));
        System.out.println("set addAll changed: "
                + codes.addAll(List.of("B", "C", "C")));
        System.out.println("set: " + codes);
        System.out.println("set existing only: "
                + codes.addAll(List.of("A", "B")));

        Set<String> union = new LinkedHashSet<>(source);
        union.addAll(incoming);
        Set<String> intersection = new LinkedHashSet<>(source);
        intersection.retainAll(incoming);
        Set<String> difference = new LinkedHashSet<>(source);
        difference.removeAll(incoming);

        System.out.println("union: " + union);
        System.out.println("intersection: " + intersection);
        System.out.println("difference: " + difference);
        System.out.println("source unchanged: " + source);

        List<String> emptyCase = new ArrayList<>(List.of("A"));
        System.out.println("contains empty: " + emptyCase.containsAll(List.of()));
        System.out.println("retain empty changed: "
                + emptyCase.retainAll(List.of()));
        System.out.println("after retain empty: " + emptyCase);

        List<Number> numbers = new ArrayList<>();
        numbers.addAll(List.of(1, 2));
        System.out.println("numbers: " + numbers);
    }
}
```

Compile and run:

```shell
javac --release 17 BulkCollectionDemo.java
java BulkCollectionDemo
```

Expected output:

```text
addAll changed: true
appended: [A, B, A, C, B, D]
contains A and D: true
contains repeated A: true
contains reversed order: true
removeAll changed: true
removed: [B, C]
removeAll again: false
retainAll changed: true
retained: [A, A, C]
retainAll again: false
set addAll changed: true
set: [A, B, C]
set existing only: false
union: [A, B, C, D]
intersection: [B]
difference: [A, C]
source unchanged: [A, B, A, C]
contains empty: true
retain empty changed: true
after retain empty: []
numbers: [1, 2]
```

Lines to verify:

- `appended` still has duplicate `B` elements because the receiver is a list.
- `contains repeated A` is `true` even though the checked collection has only one `A` element.
- `contains reversed order` is `true`, demonstrating that the check does not express ordering.
- `removed` has no remaining occurrences of `A`.
- `retained` still keeps both occurrences of `A`.
- Repeated filter calls make no changes, so they return `false`.
- `union`, `intersection`, and `difference` are new sets, while the source list remains unchanged.
- The sets use `LinkedHashSet` so the printed output has a deterministic order.
- `numbers` demonstrates that an `Integer` source can be added to a receiver with element type `Number`.

## 15. When Is a Different Approach Needed?

### 15.1. Filtering by a condition on an attribute

If you want to remove all products whose price is below a threshold, the argument is not a pre-existing group of values. `removeIf` with an appropriate predicate usually expresses this more clearly than `removeAll`.

If you only want to match by product code while the object has multiple fields, define a matching key and filtering algorithm; do not arbitrarily modify `equals` just to serve one query.

### 15.2. Preserving the source and creating a new result

You can create a new collection and call a mutating method on that copy. Streams can also express filtering to produce a separate output, provided you choose the right ordering, duplicate handling, and mutability for the result.

`retainAll` itself does not return the filtered list. Assigning `List<String> result = a.retainAll(b)` is a type error because the method returns `boolean`.

### 15.3. Replacing the entire contents

If the goal is to “synchronize the receiver to match the source data”, `retainAll` alone is not enough because it does not add missing values; `addAll` alone does not remove extra values either.

Design a replacement operation or compute additions and removals as required. If data can be read concurrently, also define a publication boundary so readers do not observe intermediate states.

### 15.4. Collections shared across multiple threads

The four calls do not automatically create a transaction across two collections.

Even if a class supports concurrent access, do not assume every bulk operation or sequence of operations across multiple structures is atomic. The argument can also change while being iterated.

Read the guarantees of the exact class and organize synchronization, snapshots, or data ownership as required. A fail-fast iterator only helps detect certain invalid modifications; it does not replace concurrency control.

## 16. Self-Check Exercises

### Exercise 1: Predict before running

Given `a = [red, blue, red, green]` and `b = [red, yellow]`. For each method, recreate `a` from the initial data.

Write down beforehand:

- The `boolean` value.
- The contents of `a` after the call.
- The contents of `b`.
- Whether duplicates are preserved.

Answers to compare against:

| Method | Boolean | a after call |
| --- | --- | --- |
| `addAll` | `true` | `[red, blue, red, green, red, yellow]` |
| `containsAll` | `false` | `[red, blue, red, green]` |
| `removeAll` | `true` | `[blue, green]` |
| `retainAll` | `true` | `[red, red]` |

`b` remains unchanged when both collections are independent and have no special side effects.

### Exercise 2: Checking required permissions

Given `granted = {READ, EXPORT}` and `required = {READ, WRITE}`.

Write the check expression in the right direction. The result must be `false`. Then find the set of missing permissions by copying `required` and removing the granted permissions; the remaining set contains `WRITE`.

Follow-up question: if `required` is empty, what does the check return, and does the application's business policy accept that?

### Exercise 3: Distinguishing quantity from presence

Suppose inventory has one unit of item `A`, and the cart requests three units of item `A`. Prove that `containsAll` is insufficient with a small example, then rewrite the check using a frequency table.

Do not mutate the source data while merely verifying stock availability.

### Exercise 4: Protecting original data

Write a method that takes a source list and a blocked group, and returns a new result list. Verify:

- The source remains unchanged.
- All occurrences of blocked codes are removed.
- The order of remaining elements is preserved.
- Empty blocked group.
- Empty source.
- No matching elements.

Then explain why this only copies the list structure if the elements are mutable objects.

### Exercise 5: Choosing the criteria structure

Compare filtering a large list with a list as criteria versus with a hash set as criteria. Measure only after verifying that both approaches use the same equality relation and produce the same result.

Your conclusion must address set preparation cost, memory usage, and how many times the criteria are reused.

## 17. Key Questions You Should Be Able to Answer

1. In `a.retainAll(b)`, which side is modified and which side serves only as criteria?
2. Why can `containsAll` return `true` when the argument contains more occurrences of a value than the receiver?
3. How does `removeAll` differ from calling `remove` once?
4. Why does `retainAll` not add missing elements from the argument?
5. Is `false` from `addAll` on a set an error?
6. How does an empty input differ from a `null` input?
7. Can you rely on a “no-op” call to avoid `UnsupportedOperationException` on every collection?
8. After a method throws an exception, why can you not assume the original data is intact?
9. Why is copying needed before computing a difference or intersection if the source must be preserved?
10. Where can mutations propagate when using views and two variables referencing the same data?
11. Why is a `HashSet` on one side not enough to know the complexity of the entire call?
12. When element counts or comparison relations differ, how must the data model be changed?

What to remember when applying these methods: identify the receiver, understand whether the argument is a source or criteria, choose the right duplicate semantics, and verify mutability and result validity. Bulk methods are only accurate when the data model and contracts the program relies on are also accurate.
