# Choosing the Target Collection Type to Preserve Required Contracts

## 1. A Successful Conversion Does Not Guarantee Data Semantics Are Preserved

Suppose a list of order lines contains two lines with the same value. If you convert it to a `HashSet` for "faster lookup," equal lines may be merged and the order is no longer guaranteed. The program still compiles, not necessarily throwing an exception, but the meaning of the data has changed.

In another requirement, the application wants a list of unique codes, preserving the first occurrence. In that case, merging elements is intentional, and `LinkedHashSet` may be more appropriate. The same data source, used for different goals, leads to different target choices.

A **contract** is what an API promises to its callers: how elements are interpreted, ordering, duplicate rules, allowed operations, data constraints, and access patterns. Choosing a target collection means choosing a set of those commitments for the data after conversion.

Two levels must be separated:

- **Current state:** which elements the result currently contains and in what order they are currently traversed.
- **Future behavior:** when adding, removing, querying, or processing subsequent elements, what rules the structure will maintain.

For example, an `ArrayList` copied from a `TreeSet` may initially be traversed in the source's sorted order. However, appending an element to the end of the list does not automatically re-sort it. Preserving the current sequence does not mean preserving the contract of "always ordered by a comparator."

A useful mental model:

```text
Source
  -> identify the information and behavior that must be preserved
  -> choose the interface, implementation class, and target construction method
  -> transfer elements according to the chosen policy
  -> verify both the contents and subsequent operations
```

The goal is not to copy every characteristic of the source at all costs. The goal is to preserve the exact commitments that the target API and business logic actually require, while making intentional changes explicit.

## 2. Define the Contract Before Choosing a Class Name

Before performing a conversion, identify the following axes:

| Decision Axis | Specific Question |
| --- | --- |
| Multiplicity | Should two equal elements still remain two separate entries? |
| Ordering | Is encounter order, sorted order, or processing/removal order needed? |
| Equality rule | Does it use `equals/hashCode`, a comparator, or reference identity? |
| Valid values | Are there `null`s, enums, types without natural ordering, or domain bounds? |
| Mutability | Can the receiver add/remove/replace elements, or is it read-only? |
| Relationship to source | Is a live view reflecting source changes needed, or a structurally independent result? |
| Operational capabilities | Are indexing, range queries, double-ended queue operations, priority retrieval, or blocking when full/empty needed? |
| Concurrent access | Will the result be shared across multiple threads; which atomic operations are required? |

The `Collection<E>` type does not fully express these axes. It does not promise a universal order, does not require every class to allow adding elements, and does not carry a source's comparator as a type parameter.

Even a `List<String>` variable does not by itself guarantee that `add` will be permitted. An unmodifiable list and an `ArrayList` can both be viewed through the `List` interface. Declaring a variable `final` only prevents reassigning the variable, not mutating the collection object itself.

Therefore, a conversion must be evaluated by both the **target type** and the **target construction method**, not merely by whether the result can be assigned to a variable with the same type parameter. The [`Collection` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) describes differences in ordering, optional operations, and policies across implementation classes.

### 2.1. Reference Table of Common Targets

| Target | Key Characteristics | What May Change Compared to the Source |
| --- | --- | --- |
| `ArrayList` | Element sequence, preserves iteration order during copy, preserves duplicates | Does not automatically preserve the source's comparator, uniqueness, or read-only policy |
| `LinkedHashSet` | Merges elements by `equals/hashCode`, preserves insertion order | Loses multiplicity of duplicate elements; does not automatically maintain sorted order |
| `HashSet` | Set based on `equals/hashCode` | Does not guarantee iteration order |
| `TreeSet` | Sorts and detects duplicates according to comparison | May merge values that differ by `equals` if the comparator is inconsistent |
| `EnumSet` | Specialized set for a single enum type, iterates in declaration order | Does not preserve multiplicity or arbitrary source order |
| `ArrayDeque` | Double-ended operations, supports queue/stack usage | Does not accept `null`, does not inherently carry a fixed capacity limit |
| `PriorityQueue` | Retrieves elements by priority | Iteration order is not the priority-polling sequence |
| `List.copyOf(source)` | Unmodifiable list, preserves element sequence, does not reflect later structural changes to source | Does not accept `null`, does not make element objects deeply immutable |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Read-only list through the returned view, structurally copied and accepts `null` elements | Element objects themselves can still be shared |

This table is a starting point for choosing a contract, not a table for substituting APIs interchangeably. Specialized requirements such as range constraints, synchronization, or capacity must be handled additionally.

## 3. Preserving Multiplicity, Ordering, and Duplicate Rules

### 3.1. Converting a List to a Set Is a Lossy Transformation

A sequence `[b, a, b]` has three positions, in which `b` appears twice. A standard `equals`-based set keeps only one representative of `b`. Converting that set back to a list cannot recover the lost positions and multiplicity.

If each occurrence has business meaning, keep a sequence type or a model that represents counts. Do not choose a set just to avoid linear scanning without first determining whether the data is allowed to be merged.

If you need **sorting while preserving duplicates**, you can create an `ArrayList` and sort the list with an appropriate comparator. `TreeSet` simultaneously enforces uniqueness by comparison; it is not a drop-in replacement for a "sorted list."

### 3.2. Encounter Order Is Not Recoverable History from Every Source

`new ArrayList<>(source)` retrieves elements in the source's iterator order. `LinkedHashSet` also preserves the insertion order of the accepted representatives during copying.

If the source already has a defined order, this is useful. If the source is a `HashSet` that does not guarantee order, copying to a `LinkedHashSet` only freezes the order observed during that copy. It does not recover historical insertion order that the source never provided.

For duplicate elements, re-adding an existing value to a `LinkedHashSet` does not move that value to the end. This matches the requirement to preserve the position of the first encounter under the set's equality rule.

[`ArrayList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) and [`LinkedHashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html) clearly specify how they inherit order from the source; [`HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html) provides no corresponding ordering guarantee.

### 3.3. Three Distinct Identity Rules Must Be Distinguished

- A standard hash set uses `equals` semantics combined with the `hashCode` contract.
- `TreeSet` treats two elements as duplicates from the tree's perspective when comparison returns `0`.
- A specialized reference-identity structure may treat two objects as duplicates only if they are the same object by `==`.

Two strings `"ID"` and `"id"` are not equal according to `String.equals`, yet a case-insensitive comparator considers them equivalent. Choosing that comparator for a `TreeSet` can reduce the element count.

This is a situation to spot a mismatched choice, not advice to ignore the general `Set` contract. A sorted set's comparator should be consistent with `equals` to obey the standard set contract. If the business logic requires a different canonical form, design the normalized key/value and equality rule explicitly.

A reference-identity structure is also a specialized choice. Converting it to a standard `HashSet` can merge distinct objects that happen to have equal values. Do not use such a set as a drop-in replacement for value-based sets. [`IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html) clearly explains the special case requiring reference comparison.

### 3.4. Program 1: One Source, Multiple Target Contracts

File `TargetSemanticsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class TargetSemanticsDemo {
    public static void main(String[] args) {
        List<String> source = Arrays.asList("b", "a", "b", null);
        List<String> list = new ArrayList<>(source);
        Set<String> insertionSet = new LinkedHashSet<>(source);
        Set<String> hashSet = new HashSet<>(source);

        System.out.println("source=" + source);
        System.out.println("list=" + list);
        System.out.println("insertionSet=" + insertionSet);
        System.out.println("hashSize=" + hashSet.size());
        System.out.println("hashContainsNull=" + hashSet.contains(null));
        System.out.println("roundTrip=" + new ArrayList<>(insertionSet));

        try {
            new TreeSet<>(source);
            throw new AssertionError("Natural-order TreeSet accepted null");
        } catch (NullPointerException expected) {
            System.out.println("naturalTree=NullPointerException");
        }

        TreeSet<String> nullableSorted =
                new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
        nullableSorted.addAll(source);
        System.out.println("nullableSorted=" + nullableSorted);

        List<String> sortedSequence = new ArrayList<>(source);
        sortedSequence.sort(Comparator.nullsFirst(Comparator.naturalOrder()));
        System.out.println("sortedSequence=" + sortedSequence);

        List<String> codes = List.of("ID", "id");
        Set<String> exactCodes = new LinkedHashSet<>(codes);
        TreeSet<String> foldedCodes = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        foldedCodes.addAll(codes);
        System.out.println("equalsDistinct=" + exactCodes.size());
        System.out.println("comparatorDistinct=" + foldedCodes.size());

        Set<String> identitySet =
                Collections.newSetFromMap(new IdentityHashMap<>());
        identitySet.add(new String("same"));
        identitySet.add(new String("same"));
        System.out.println("identitySize=" + identitySet.size());
        System.out.println("equalsCopySize=" + new HashSet<>(identitySet).size());

        list.add("tail");
        System.out.println("editableCopy=" + list);
        System.out.println("sourceSize=" + source.size());
    }
}
```

Compile and run with a JDK supporting Java 17 or later:

```shell
javac --release 17 -encoding UTF-8 TargetSemanticsDemo.java
java TargetSemanticsDemo
```

Output:

```text
source=[b, a, b, null]
list=[b, a, b, null]
insertionSet=[b, a, null]
hashSize=3
hashContainsNull=true
roundTrip=[b, a, null]
naturalTree=NullPointerException
nullableSorted=[null, a, b]
sortedSequence=[null, a, b, b]
equalsDistinct=2
comparatorDistinct=1
identitySize=2
equalsCopySize=1
editableCopy=[b, a, b, null, tail]
sourceSize=4
```

In the output:

- `list` keeps all four positions, including two `b`s and one `null`.
- `insertionSet` keeps the first occurrence of each value according to `equals`.
- `hashSet` is only checked for size and whether it contains `null`; the program does not assert an ordered output that the API does not guarantee.
- `nullableSorted` both sorts and deduplicates, whereas `sortedSequence` sorts while keeping both `b`s.
- `equalsDistinct` and `comparatorDistinct` show that changing the duplicate rule can change the element count.
- `identitySize` and `equalsCopySize` show that two distinct string objects can be merged when switching to value-based equality.

The source was created with `Arrays.asList`, so it has a fixed size. The `ArrayList` copy still allows adding `"tail"`; the source keeps size four. This is a change in mutability capabilities, even though before the `add` call both sequences had identical contents.

The `nullsFirst` comparator in the example is an explicit choice to handle `null`. It does not mean every `TreeSet` accepts `null` by default.

## 4. Source Comparators and Bounds Do Not Automatically Follow Every Copy

### 4.1. Same Object, Different Overload, Different Order

`TreeSet` has overloaded constructors: one accepts `Collection`, another accepts `SortedSet`. They have different contracts:

| Construction Method | Ordering Rule |
| --- | --- |
| `new TreeSet<>(collection)` | Natural ordering of elements |
| `new TreeSet<>(sortedSet)` | Preserves the ordering rule of the provided sorted set |
| `new TreeSet<>(comparator)` then `addAll` | Uses the explicitly passed comparator |

Overload resolution happens based on the static type the compiler sees in the argument expression. A `TreeSet` instance using descending order, when passed through a `Collection<Integer>` variable, does not cause the `Collection`-accepting constructor to copy its comparator.

This might only change the order if the elements have a natural ordering. For an object type that is only comparable via a custom comparator, losing the comparator can even cause adding elements to the tree to fail with a `ClassCastException`.

If a conversion method must preserve sorting, design the signature to accept an appropriate `SortedSet` or an explicit `Comparator`. Do not hide necessary information behind a `Collection` parameter and expect every constructor to guess it.

`TreeMap` has a similar pair of constructors accepting `Map` and `SortedMap`. `Map` does not belong to the `Collection` interface, but the same principles of choosing a target and preserving comparators apply when converting maps.

[`TreeSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html) and [`TreeMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) explicitly document the contract of each constructor. Always read the contract for the overload actually being called.

### 4.2. Preserving a Comparator Does Not Preserve View Bounds

A view obtained from `subSet` may only allow values within a specific range. Calling `new TreeSet<>(view)` copies the existing elements and may preserve the comparator via the `SortedSet` overload. The result is a new tree that does not automatically carry over the original view's range bounds.

If an API needs a structurally independent target that still restricts the value domain, that restriction must be applied explicitly after constructing the standalone structure, or validation rules must be placed at an appropriate API layer. A copy that currently contains only valid values does not automatically reject out-of-range values in the future.

Similarly, copying the current contents of an access-ordered map does not copy the policy of updating order on `get`. For instance, the `LinkedHashMap(Map)` constructor creates an insertion-ordered map; if an access-order policy is needed, the corresponding configuration must be chosen. The [`LinkedHashMap` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html) separates those two policies.

### 4.3. Program 2: Comparator, Overloads, and Range Bounds

File `SortedCopyContractDemo.java`:

```java
import java.util.Collection;
import java.util.Collections;
import java.util.Map;
import java.util.NavigableSet;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class SortedCopyContractDemo {
    public static void main(String[] args) {
        TreeSet<Integer> source = new TreeSet<>(Collections.reverseOrder());
        source.addAll(java.util.List.of(5, 9, 7));

        SortedSet<Integer> sortedInput = source;
        Collection<Integer> generalInput = source;
        TreeSet<Integer> preserved = new TreeSet<>(sortedInput);
        TreeSet<Integer> natural = new TreeSet<>(generalInput);
        TreeSet<Integer> explicit = new TreeSet<>(source.comparator());
        explicit.addAll(generalInput);

        preserved.add(6);
        natural.add(6);
        explicit.add(6);
        System.out.println("source=" + source);
        System.out.println("preserved=" + preserved);
        System.out.println("natural=" + natural);
        System.out.println("explicit=" + explicit);

        NavigableSet<Integer> bounded = source.subSet(9, true, 5, false);
        TreeSet<Integer> unboundedCopy = new TreeSet<>(bounded);
        try {
            bounded.add(3);
            throw new AssertionError("Range accepted an out-of-range value");
        } catch (IllegalArgumentException expected) {
            System.out.println("rangeAdd=IllegalArgumentException");
        }
        unboundedCopy.add(3);
        System.out.println("bounded=" + bounded);
        System.out.println("unboundedCopy=" + unboundedCopy);

        TreeMap<Integer, String> sortedMap =
                new TreeMap<>(Collections.reverseOrder());
        sortedMap.put(1, "one");
        sortedMap.put(3, "three");
        sortedMap.put(2, "two");

        SortedMap<Integer, String> sortedMapInput = sortedMap;
        Map<Integer, String> generalMapInput = sortedMap;
        TreeMap<Integer, String> sameOrder = new TreeMap<>(sortedMapInput);
        TreeMap<Integer, String> naturalOrder = new TreeMap<>(generalMapInput);
        System.out.println("mapSortedInput=" + sameOrder);
        System.out.println("mapGeneralInput=" + naturalOrder);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SortedCopyContractDemo.java
java SortedCopyContractDemo
```

Output:

```text
source=[9, 7, 5]
preserved=[9, 7, 6, 5]
natural=[5, 6, 7, 9]
explicit=[9, 7, 6, 5]
rangeAdd=IllegalArgumentException
bounded=[9, 7]
unboundedCopy=[9, 7, 3]
mapSortedInput={3=three, 2=two, 1=one}
mapGeneralInput={1=one, 2=two, 3=three}
```

Both `sortedInput` and `generalInput` point to `source`. They cause different constructors to be selected. When `6` is added, one target continues to maintain descending order, while the target using natural ordering maintains ascending order.

The `explicit` variable shows how to provide the comparator explicitly when the input is viewed as a general collection. When `comparator()` returns `null`, that represents natural ordering; it is not itself a missing-configuration error.

In the descending range from `9` (inclusive) to `5` (exclusive), the `bounded` view contains `9` and `7`. Adding `3` through the view is rejected. The tree copy accepts `3`, because the range bound is not part of the new tree's contract.

The map section confirms the same difference: receiving the source as a `SortedMap` preserves descending order, whereas receiving it as a `Map` creates a tree with natural ordering. The existing mappings are the same, but the ordering contract has changed.

## 5. Mutability, Independence, and Element State Are Three Different Things

When discussing an "unchangeable copy," state precisely what you want to preserve:

| Question | Meaning |
| --- | --- |
| Can `add/remove/set` be called through the result? | Structural mutability through the provided reference |
| If the source changes structure, does the result change too? | Whether the result is a live view or structurally independent |
| If an element object is mutated, is it visible through the result? | Whether elements are shared and mutable |

`Collections.unmodifiableList(source)` blocks mutating operations through the wrapper but still reads data from `source`. If another party can still modify the source, the result can change accordingly.

`List.copyOf(source)` provides an unmodifiable list that does not reflect subsequent structural changes to the source. However, it forbids `null` elements and does not deep-copy each element object.

`new ArrayList<>(readOnlySource)` creates a mutable list. This may be right when a private working copy is needed, but it must not be assumed to preserve the source API's read-only policy.

If you need to preserve an element sequence, allow `null`, and prevent the receiver from modifying the structure, you can create a private `ArrayList` and wrap it with `unmodifiableList`. Do not hand out any mutable reference to that private list if the contract requires structural stability.

[`Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)) and [`List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) serve two different relationships with the source.

### 5.1. An Unmodifiable Result Does Not Make Element Objects Immutable

Standard collection copy constructors primarily copy references. A `Customer` with a mutable address field can still be referenced by both the source and the target. Mutating that object is not the same as adding or removing elements from the collection.

If the requirement is a completely stable business-data snapshot, consider the element model as well: use immutable objects or create appropriate copies for each object. Simply changing the collection class does not satisfy that deeper requirement.

Similarly, placing a mutable object into a set/map does not fix an unstable `equals/hashCode` design. If fields participating in hashing or comparison change while the object is an element/key, the target collection may no longer support the lookups the application expects.

### 5.2. Do Not Infer Order Preservation from the Name `copyOf`

`Set.copyOf` returns an unmodifiable set and forbids `null`, but it does not promise to preserve the encounter order of a list or the insertion order of a `LinkedHashSet`. When the input contains duplicates, one representative is kept without the API promising it is the first-encountered representative.

If the requirement is "unique, preserve first encounter, deterministic order from source, unmodifiable through the result," you can deliberately create a `LinkedHashSet` and wrap it with `Collections.unmodifiableSet`. If a sorted/navigable interface is also needed, choose a wrapper that preserves that interface rather than returning a general set.

[`Set.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)) defines its own contract. A method named "copy" does not promise to preserve every characteristic of the source, nor is it required to allocate a new object if it can satisfy the contract otherwise.

## 6. Specialized Capabilities Must Be Chosen Explicitly

### 6.1. `EnumSet`: Enum Type and Empty Input

`EnumSet` is suitable when the value domain is an enum type and set semantics are needed. It does not preserve duplicates and iterates in enum constant declaration order, not in an arbitrary source list order.

With a general empty collection, `EnumSet.copyOf(collection)` has no elements from which to infer the enum type and throws `IllegalArgumentException`. You can provide the type explicitly via `EnumSet.noneOf(Permission.class)`, then add the elements.

Do not interpret this as "no empty `EnumSet` can be copied." An `EnumSet` already retains its type information even when empty. The `copyOf` contract also handles a source that is an `EnumSet` appropriately, even when received via the `Collection` overload.

The [`EnumSet` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html) specifies element typing, ordering, and the distinction for empty sources.

### 6.2. Priority Queues: Preserve Polling Order, Not Just Iteration Order

`PriorityQueue` holds elements to be retrieved according to a comparator. Its iterator does not guarantee traversal in sorted order. Therefore, `new ArrayList<>(priorityQueue)` does not produce a list in `poll` order.

If you need a copy that still processes by priority, the constructor accepting another `PriorityQueue` preserves the corresponding ordering rule. If you want a list in processing order, you can drain from a copy of the queue so you do not exhaust the source.

Nor should you generalize that every constructor accepting `Collection` drops the comparator. `PriorityQueue(Collection)` has specific rules when the actual source is a `SortedSet` or `PriorityQueue`. This is why you must read the API of the specific target type.

If elements with equal priority must also be processed in arrival order, a secondary rule and sufficient information to distinguish that order are required. Choosing `PriorityQueue` alone does not create a stability guarantee for equal-priority pairs.

The [`PriorityQueue` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html) distinguishes retrieval order from iteration order and describes its constructors.

### 6.3. Capacity, Blocking, and Concurrent Access Do Not Live Inside Elements

Converting a full `ArrayBlockingQueue` to an `ArrayDeque` may preserve the currently observed sequence of elements, but it loses the fixed capacity limit and the blocking operations of a blocking queue.

Passing an initial capacity value to `ArrayDeque` also does not turn it into a fixed-capacity bounded queue like `ArrayBlockingQueue`. Both types can serve a FIFO workflow, yet they have different insertion contracts.

Similarly, creating an `ArrayList` from a thread-safe collection does not make the new list synchronized. The target's policy must be chosen anew based on how threads will use the result.

If a bounded target is needed, choose the capacity, full-queue policy, and appropriate operations. If concurrent access is needed, also consider atomic operation sequences, not just whether a single method has synchronization.

[`ArrayDeque`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) and [`ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html) publish very different policies even though both can hold a sequence of tasks.

### 6.4. Program 3: Read-Only, Enum, Priority, and Capacity

File `TargetCapabilitiesDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.EnumSet;
import java.util.List;
import java.util.PriorityQueue;
import java.util.concurrent.ArrayBlockingQueue;

public class TargetCapabilitiesDemo {
    private enum Permission {
        READ, WRITE
    }

    private static void failsWith(String name,
            Class<? extends RuntimeException> expected, Runnable operation) {
        try {
            operation.run();
        } catch (RuntimeException failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(name + " threw the wrong exception", failure);
            }
            System.out.println(name + "=" + failure.getClass().getSimpleName());
            return;
        }
        throw new AssertionError(name + " did not fail");
    }

    private static void ownership() {
        List<String> source = new ArrayList<>(List.of("alpha"));
        List<String> live = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);
        List<String> editable = new ArrayList<>(snapshot);

        source.add("beta");
        editable.add("local");
        System.out.println("live=" + live);
        System.out.println("snapshot=" + snapshot);
        System.out.println("editable=" + editable);
        failsWith("snapshotAdd", UnsupportedOperationException.class,
                () -> snapshot.add("other"));

        List<String> nullable = Arrays.asList("value", null);
        failsWith("copyOfNull", NullPointerException.class,
                () -> List.copyOf(nullable));
        List<String> nullableSnapshot =
                Collections.unmodifiableList(new ArrayList<>(nullable));
        System.out.println("nullableSnapshot=" + nullableSnapshot);
    }

    private static void enumTarget() {
        List<Permission> input =
                List.of(Permission.WRITE, Permission.READ, Permission.WRITE);
        System.out.println("enumInput=" + input);
        System.out.println("enumTarget=" + EnumSet.copyOf(input));

        List<Permission> empty = List.of();
        failsWith("enumEmptyList", IllegalArgumentException.class,
                () -> EnumSet.copyOf(empty));
        EnumSet<Permission> safeEmpty = EnumSet.noneOf(Permission.class);
        safeEmpty.addAll(empty);
        System.out.println("enumExplicitEmpty=" + safeEmpty);
        System.out.println("enumEmptySetCopy=" + EnumSet.copyOf(safeEmpty));
    }

    private static void queueTarget() {
        PriorityQueue<Integer> priority =
                new PriorityQueue<>(Collections.reverseOrder());
        priority.addAll(List.of(2, 9, 4));
        PriorityQueue<Integer> priorityCopy = new PriorityQueue<>(priority);
        List<Integer> processingOrder = new ArrayList<>();
        while (!priorityCopy.isEmpty()) {
            processingOrder.add(priorityCopy.remove());
        }
        System.out.println("priorityProcessing=" + processingOrder);
        System.out.println("prioritySourceSize=" + priority.size());

        failsWith("dequeNull", NullPointerException.class,
                () -> new ArrayDeque<>(Arrays.asList("job", null)));

        ArrayBlockingQueue<String> bounded =
                new ArrayBlockingQueue<>(2, false, List.of("first", "second"));
        ArrayDeque<String> unboundedCopy = new ArrayDeque<>(bounded);
        System.out.println("boundedOffer=" + bounded.offer("third"));
        System.out.println("unboundedOffer=" + unboundedCopy.offerLast("third"));
        System.out.println("unboundedCopy=" + unboundedCopy);
    }

    public static void main(String[] args) {
        ownership();
        enumTarget();
        queueTarget();
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 TargetCapabilitiesDemo.java
java TargetCapabilitiesDemo
```

Output:

```text
live=[alpha, beta]
snapshot=[alpha]
editable=[alpha, local]
snapshotAdd=UnsupportedOperationException
copyOfNull=NullPointerException
nullableSnapshot=[value, null]
enumInput=[WRITE, READ, WRITE]
enumTarget=[READ, WRITE]
enumEmptyList=IllegalArgumentException
enumExplicitEmpty=[]
enumEmptySetCopy=[]
priorityProcessing=[9, 4, 2]
prioritySourceSize=3
dequeNull=NullPointerException
boundedOffer=false
unboundedOffer=true
unboundedCopy=[first, second, third]
```

`live` sees `beta` added to the source; `snapshot` retains the original sequence. The `editable` copy is allowed to add its own element. The three results satisfy three different needs.

`nullableSnapshot` shows that a structurally unmodifiable result can still retain `null` when the construction method is chosen intentionally. `List.copyOf` does not satisfy that element policy.

The enum target turns `[WRITE, READ, WRITE]` into `[READ, WRITE]`: both deduplicating and using declaration order. The empty part demonstrates the difference between an empty general collection and an `EnumSet` that already knows its type.

`priorityProcessing` is built by draining a copy of the priority queue, so it reflects the descending processing order. The source still has three elements. The program does not rely on any internal ordering of the iterator.

Finally, while both currently hold two jobs, the bounded queue rejects the third `offer` whereas the `ArrayDeque` copy accepts it. Preserving the initial two elements does not preserve the capacity policy.

## 7. Using Streams Still Requires Choosing a Target Contract

### 7.1. A Collector Method Is Not a Promise About Every Implementation Detail

The following approaches do not share the same contract:

| Result Collection Method | Commitments to Understand |
| --- | --- |
| `collect(Collectors.toList())` | Returns a `List`, with no guarantees on concrete class, mutability, serializability, or thread-safety |
| `collect(Collectors.toSet())` | Returns a `Set`, with no guarantees on order or concrete class |
| `stream.toList()` | Unmodifiable list, preserves the stream's encounter order if the stream is ordered |
| `collect(Collectors.toCollection(factory))` | Explicitly chooses the collection via the supplied factory |

Do not cast the result of `Collectors.toList()` to `ArrayList` and treat an observed implementation class as an API contract. If you need a guaranteed mutable `ArrayList`, request it via a factory.

Similarly, `Collectors.toSet()` is not the way to express a requirement for preserving first-encounter order. You need a target with the appropriate contract such as `LinkedHashSet`, and the source/stream itself must have an order to preserve.

[`Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html) states the limitations of general-purpose collectors; [`Stream.toList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()) guarantees an unmodifiable result.

### 7.2. Choose a Factory When You Need Control

The following snippet is an illustrative body, not a standalone program; it requires the corresponding collection types, `Comparator`, and `Collectors`:

```java
List<Integer> input = List.of(3, 1, 3, 2);

List<Integer> sequence = input.stream()
        .collect(Collectors.toCollection(ArrayList::new));

Set<Integer> firstEncounter = input.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));

NavigableSet<Integer> descending = input.stream()
        .collect(Collectors.toCollection(
                () -> new TreeSet<Integer>(Comparator.reverseOrder())));
```

The three results represent respectively:

- `sequence`: `[3, 1, 3, 2]`, preserving all positions and order.
- `firstEncounter`: `[3, 1, 2]`, merging duplicates by `equals` and preserving first-encounter order.
- `descending`: `[3, 2, 1]`, merging duplicates and maintaining descending order.

The factory must supply a new, empty collection suitable for accumulating results. Do not return a collection object that already contains externally shared data and expect the collect operation to turn it into an independent workspace.

The example uses a sequential stream originating from an ordered list. If an earlier step in the pipeline removed the ordering commitment, choosing `LinkedHashSet` at the end cannot recover the lost historical order.

### 7.3. When the Target Is a Map, Define the Duplicate-Key Policy

Converting records into a map also requires defining keys. If two records produce the same key, you must know what is allowed to happen: throw an error, keep the first record, keep the last record, aggregate, or store a list of records under that key.

The `Collectors.toMap(keyMapper, valueMapper)` overload throws `IllegalStateException` on duplicate keys by contract. Adding a merge function is a business decision, not merely a way to make the exception disappear.

The following snippet chooses to **keep the first word of each length** and uses `LinkedHashMap` to preserve the encounter order of keys in the example:

```java
List<String> words = List.of("ax", "cat", "by");
Map<Integer, String> firstWordByLength = words.stream().collect(
        Collectors.toMap(
                String::length,
                Function.identity(),
                (first, later) -> first,
                LinkedHashMap::new));
```

With the given data, the result is `{2=ax, 3=cat}`. The word `"by"` has the same length as `"ax"`, so it is discarded according to the written policy. If every word must be retained, this policy is wrong even though the map is constructed successfully; a target model such as `Map<Integer,List<String>>` or another suitable structure is needed.

When key order is required, choose a map factory with the corresponding ordering contract. When sorted order is required, also define the comparator and key-identity rule. Do not treat map type, key mapper, and merge policy as three decisions independent of data semantics.

## 8. A Testable Target-Selection Workflow

### 8.1. Write Requirements as Concrete Statements

Instead of a vague requirement like "return a collection copy," you can write:

- Every line must be kept, including lines with equal values.
- The resulting sequence follows the input order.
- `null` elements are accepted or rejected according to the stated policy.
- The receiver must not add, remove, or replace an element of the structure.
- Subsequent structural changes to the source must not alter the result.
- Permission to mutate the state of individual element objects is specified separately.

Given these requirements and an ordered source, a private `ArrayList` wrapped with `unmodifiableList` may be suitable. Choosing a `Set` would violate the requirement to keep every line; choosing `List.copyOf` would not fit if `null` must be kept; wrapping the source directly would not satisfy structural independence.

If the requirement changes to "remove duplicates, keep first encounter," a different target may be appropriate. When requirements change, re-evaluate the target structure instead of adding casts to keep an old choice.

### 8.2. Separate Data Transformation from the Result Container Policy

Case normalization, type conversion, `null` removal, record merging, or filtering out-of-range values are all transformations that can change data semantics. They must be stated explicitly, not hidden under an operation called "copy."

A clear processing flow can look like:

```text
Input
  -> validate input preconditions
  -> intentional transformation, if required by business logic
  -> accumulate into the chosen target structure
  -> apply required constraints/mutability policy
  -> publish the result after completion
```

If constructing the target fails due to `null`, incomparable elements, or capacity limits, do not publish a half-built result as if it had fulfilled the full contract. When adding to an existing collection, also do not assume `addAll` is a transaction that automatically rolls back all changes on an exception.

Building a private result before publishing helps control the state observable by the receiver. It does not by itself create atomicity for external side effects or for a source being concurrently modified.

### 8.3. Verify the Exact Properties of the Chosen Contract

Checking only `containsAll` is not enough to prove that a conversion preserves a sequence. That check does not reflect positions and does not fully count multiplicities.

More appropriate checks can be chosen:

| Requirement | Appropriate Observation/Verification |
| --- | --- |
| Preserve entire sequence | Compare lists for exact order and multiplicity |
| Preserve counts without order | Compare frequencies under the chosen equality rule |
| Preserve set iteration order | Observe a sequence built from the iterator; `Set.equals` does not check order |
| Preserve sorting rule | Test representative values and adding new elements, not just the initial snapshot |
| Preserve range bounds | Test one in-range value and one out-of-range value through the provided API |
| Preserve read-only policy | Test mutation paths exposed by the interface |
| Preserve independence from source | Mutate source structure in a controlled way and observe the result |
| Preserve priority processing order | Drain from a queue copy rather than inferring from the iterator |
| Preserve empty/null/capacity policy | Test these edge cases specifically |

Do not inspect the order of a class that does not promise order and hardcode the output of one run as a requirement. Nor should you use internal class names or reference comparison in place of testing the contract of a constructor that is permitted to reuse results.

### 8.4. A Thread-Safe Source Does Not Guarantee a Global Atomic Snapshot

A source may provide an iterator with a consistency level suitable for concurrent traversal, yet that traversal does not necessarily correspond to a point-in-time snapshot of all data.

Choosing a thread-safe target addresses the **target's** access policy. It does not automatically strengthen the consistency level of **reading the source**. If the output data must reflect a consistent business state, a coordination protocol or a source-supported snapshot mechanism is required.

For example, [`ConcurrentHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) separately describes the behavior of aggregate operations and iterators during concurrent updates. Do not infer from individual map operations being thread-safe that "copying all entries is an atomic transaction."

A single run without exceptions is also not proof that concurrency requirements have been met.

### 8.5. Consider Cost After Choosing the Right Semantics

Different structures have different access, update, sorting, and memory costs. However, a faster target is not a valid substitute if it loses multiplicity, order, or capabilities that the API requires.

If you need both to keep every line in order and to look up a piece of information quickly, you may need a list as primary data and a separate index. In that case, there must be a consistent update rule between the two structures. Replacing the entire list with a set does not solve the requirement to keep all lines.

Similarly, creating a `TreeSet` just to obtain a sorted sequence can both waste effort maintaining a tree and lose duplicate elements. Choosing a list and sorting it may express the requirement more accurately. Performance decisions should be evaluated on the real set of operations, after data-preservation conditions have been satisfied.

## 9. Practice: Choosing and Explaining

### Scenario 1: Transaction Sequence with Equal Lines

The input has two transactions with the same value, but they are two distinct occurrences. The API needs to keep every line and the input order.

**Analysis:** Do not convert to a set just because two lines are equal as current objects. A list fits sequence semantics better. If business identity must be distinguished, represent it with an appropriate transaction ID rather than relying on two objects happening to have different memory addresses.

### Scenario 2: Deduplicated Tag List, Preserving First Encounter

The input is an ordered list with repeated tags and allows a `null` tag. The receiver only needs to read the result.

**Analysis:** Choose `equals`-based deduplication, accumulate into a `LinkedHashSet`, then provide an unmodifiable wrapper if needed. `HashSet` does not keep an ordering commitment; `Set.copyOf` does not satisfy the `null` policy and does not promise to preserve encounter order.

### Scenario 3: Need to Sort All Lines Without Dropping Records

The input consists of academic records, with multiple records receiving the same score. You want to return a sequence ordered by score while still keeping every record.

**Analysis:** A sorted list preserves multiple records with the same sort key. If a `TreeSet` with a score-only comparator is used, records comparing as `0` may be merged. If an ordering requirement exists among records with the same score, a secondary rule must also be defined.

### Scenario 4: API Copying a Descending Sorted Set

A method accepts `Collection<Integer>`, yet the caller expects the target to remain descending and support range queries.

**Analysis:** The input contract is hiding necessary information. You can require an appropriate `SortedSet`/`NavigableSet` or accept an explicit comparator. Choosing `ArrayList` only preserves the current sequence; calling the `TreeSet(Collection)` constructor picks natural ordering instead. If view bounds must also be preserved, apply those bounds separately.

### Scenario 5: Potentially Empty Enum Permission Result

The input is a collection of enum permissions; there are cases with no permissions.

**Analysis:** Provide the enum type explicitly to create an empty target, then add the data. Do not rely on a first element that may not exist. State clearly that the result is an enum-based set, not preserving duplicates or arbitrary input order.

### Scenario 6: Copying a Full Queue for Processing Handover

The source has a capacity limit and uses blocking when full/empty. The receiver will continue adding jobs.

**Analysis:** Simply copying elements into an `ArrayDeque` does not preserve capacity limits or blocking mechanisms. You must choose the target queue policy, capacity, and handover protocol. If only a report of current jobs is needed, a separate list may be appropriate because operational queue guarantees are not needed.

A target choice can be explained clearly when the author can point out **what is preserved, what is intentionally changed, and which future operations prove that contract**.
