# Motivation for SequencedCollection, SequencedSet, and SequencedMap

## 1. The problem to solve: order already existed, but lacked a common voice

Suppose an application manages the publishing steps of a product. One place stores the full history in a list, another uses a double-ended queue for pending items, and another keeps unique steps in the order the user selected them. A preview feature only needs to ask: "What is the first element, what is the last element, and what do we see if we read in reverse?"

This is the same business need, yet before Java 21, developers had to express it using several different API families. Lists used indices; double-ended queues had methods for the head and tail; sorted sets had the concepts of smallest and largest; linked sets preserved insertion order but lacked a common API to retrieve the last element or create a stream in reverse order.

The gap lay in **contract expressiveness**: Java already had many structures that maintained order, but lacked a single interface precise enough to say "this collection has a defined encounter order and can be viewed from both ends." Three interfaces introduced in Java 21 address this gap: `SequencedCollection`, `SequencedSet`, and `SequencedMap`. The official introductory documentation describes this motivation in the context of JEP 431. [Oracle: Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html).

After this lesson, you should be able to explain why the three new types need to exist, choose the right interface for inputs/outputs where order matters, and avoid assuming that having new methods means every structure is mutable or has the same performance cost.

**Version milestone:** the `Sequenced*` APIs belong to Java 21 and later. The main program below uses Java 21 and cannot be compiled with `--release 17`. This is a standard library change already included in Java 21; examples do not require enabling preview features.

## 2. What is encounter order?

**Encounter order** is the sequence in which elements are considered to stand from first to last when an operation respects order. You can picture a row of cards on a table:

~~~text
first                                    last
build              test                  ship
~~~

In this sequence, `build` comes before `test`, and `ship` comes after `test`. Reading forward yields `build, test, ship`; reading in reverse yields `ship, test, build`. That concept describes the logical relationship between elements, not that they sit next to each other in memory. A dynamic array, a linked structure, and a tree can all provide a meaningful sequence.

`SequencedCollection` uses this sequence for operations such as iteration, converting to an array, and creating a stream source. The interface provides first/last access, operations at both ends, and `reversed()` to obtain a reverse-ordered view; mutating operations are optional. [Java 21: SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html).

### 2.1. Ordered does not mean sorted

Let us insert `ship, build, test` in turn into three structures:

| Structure and usage | Observed sequence | What determines the sequence |
| --- | --- | --- |
| `ArrayList`, appended at the end | `ship, build, test` | Position in the list |
| `LinkedHashSet`, using regular `add` | `ship, build, test` | Insertion order of distinct elements |
| `TreeSet` using the natural order of strings | `build, ship, test` | Comparison between elements |

All three structures can have an encounter order, but only the last row has an order determined by comparison. For example, "get the first element" of a linked set may mean the earliest selected step; for a sorted set, it is the smallest step according to the comparator. Sharing the same operation name does not erase the semantics of the underlying structure.

`TreeSet` sorts by natural order or by a provided `Comparator`. Changing the comparator can change which element stands first even if the input data does not change. [Java 21: TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).

### 2.2. One seemingly stable print does not create a guarantee

A `HashSet` containing a few strings might happen to print the same way across multiple runs. That does not turn it into a collection with an insertion-order contract. `HashSet` makes no guarantees as to iteration order and does not guarantee that the order will remain constant over time. [Java 21: HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html).

Similarly, do not take a current `HashMap` result as proof that the first key is always the one inserted first. `HashMap` provides no guarantees about the order of the map. [Java 21: HashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

Distinguish between two statements:

- "On this run, the iterator returned `A` before `B`" is an observation.
- "The structure's API specifies that `A` must appear before `B` according to the stated rule" is a contract.

Designing features for exporting reports, building UIs, or handling priorities must rely on the second statement if order affects the outcome.

## 3. Before Java 21: same intent, many ways to write it

The table below illustrates the API fragmentation before Java 21, given non-empty data:

| Type | Get first | Get last | Read in reverse |
| --- | --- | --- | --- |
| `List` | `get(0)` | `get(size() - 1)` | Index loop or backward `ListIterator` |
| `Deque` | `getFirst()` | `getLast()` | `descendingIterator()` |
| `SortedSet` | `first()` | `last()` | If `NavigableSet`, `descendingSet()` is available |
| `LinkedHashSet` | Iterator to get the first element | Usually must iterate to the end | Usually must reorganize iteration or copy manually |
| `LinkedHashMap` | Iterate `entrySet()` for the first entry | Usually must iterate to the end | No unified reverse view on this map type |

The inconvenience is not just character count. Readers have to recognize that all these different expressions are dealing with **the ends of a sequence**. A shared utility easily splits into multiple branches based on concrete types.

The following example is **a method snippet illustrating Java 17-compatible code**, placed inside a class with the corresponding imports; it is not a standalone runnable program:

~~~java
static <E> E lastOfList(java.util.List<E> items) {
    if (items.isEmpty()) {
        throw new java.util.NoSuchElementException();
    }
    return items.get(items.size() - 1);
}

static <E> E lastByTraversal(java.util.Collection<E> items) {
    var it = items.iterator();
    if (!it.hasNext()) {
        throw new java.util.NoSuchElementException();
    }
    E last = it.next();
    while (it.hasNext()) {
        last = it.next();
    }
    return last;
}
~~~

The second method retrieves the last element **of the current traversal**. It cannot create an "insertion-order last" guarantee for every `Collection`. If a `HashSet` is passed in, the code still runs, but the business meaning the caller expects may not exist.

For `Deque`, its existing contract already clearly defined both ends and had API pairs returning special values when operations fail. Starting in Java 21, `Deque` also belongs to the `SequencedCollection` branch; its specific capabilities such as `offerFirst`, `peekFirst`, and `pollFirst` still retain their meaning. [Java 21: Deque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Deque.html).

## 4. Why not use Collection or List for everything?

### 4.1. Collection is too broad if order is part of the requirement

Consider this hypothetical signature:

~~~java
static void printRoute(java.util.Collection<String> stops) {
    for (String stop : stops) {
        System.out.println(stop);
    }
}
~~~

The method only asks for "a collection of elements." Callers can pass in a structure with no guaranteed order. If the function actually needs stops in route order, the signature does not capture that condition; documentation and user care must make up for it.

Switching to `SequencedCollection<String>` directly expresses that the input has a sequence. A `HashSet<String>` cannot be passed directly to that signature. The compiler can catch the mismatch before the program runs.

However, this type only states that **there is a defined sequence**. It does not state that the sequence is the correct business route. A `TreeSet` sorting stop names still has an order, yet it may be the wrong route. You must further specify the domain semantics—for example, "stops in travel order"—and choose a structure that satisfies it.

### 4.2. List is too narrow if indices and duplicates are not needed

If you use `List` as a parameter, you are saying that a list is the appropriate model. This is convenient when positional access or preserving duplicate occurrences is needed. But a function that only prints the first/last elements and iterates in reverse does not necessarily need those characteristics.

A deduplicated linked set or a sorted set can also satisfy the need. Forcing callers to convert them into a `List` just to pass the API boundary causes unnecessary copying, allocation, and an extra data-interpretation step.

From Java 21 onward, `List` keeps its list contract while also extending `SequencedCollection` and having `reversed()` return a `List`. Adding the interface layer does not replace `List` with a weaker model. [Java 21: List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html).

### 4.3. Concrete types tie utilities to one storage representation

A signature accepting `LinkedHashSet` describes the exact storage class, which may be overly restrictive. If only uniqueness and sequence are needed, `SequencedSet` expresses the requirement more accurately. Callers can supply another suitable implementation without the utility having to branch on class names.

This is a key design benefit of the three interfaces: **choose the contract you need, and keep implementation choices outside the processing function**. It is not that replacing every class name with a new interface is automatically better; you must accurately identify the capabilities the function truly needs.

## 5. How do the three interfaces divide responsibilities?

The diagram below shows only the relevant branches, not the entire Java Collections Framework hierarchy. Arrows indicate "is a subtype of":

~~~text
List ----------------------> SequencedCollection ------> Collection
Deque ---------------------> SequencedCollection

SequencedSet --------------> SequencedCollection
SequencedSet --------------> Set ----------------------> Collection
SortedSet -----------------> SequencedSet
LinkedHashSet implements --> SequencedSet

SequencedMap --------------> Map
SortedMap -----------------> SequencedMap
LinkedHashMap implements --> SequencedMap
~~~

### 5.1. SequencedCollection: needing a sequence of elements

Use this interface when you need to express first/last access and traversal direction without requiring indices or uniqueness.

Core operation groups:

| Intent | Methods |
| --- | --- |
| View first/last | `getFirst()`, `getLast()` |
| Add at first/last if supported | `addFirst(e)`, `addLast(e)` |
| Remove first/last if supported | `removeFirst()`, `removeLast()` |
| Obtain a reverse-ordered view | `reversed()` |

This provides a shared vocabulary for writing generic operations across multiple data families. You do not need to ask whether an object is a `List` or a `Deque` just to get its first and last elements.

### 5.2. SequencedSet: uniqueness plus sequence

`SequencedSet` is both a `Set` and a `SequencedCollection`. It lets an API state that the data contains no duplicate elements per the set contract, while also having an encounter order.

An important point to keep in mind is equality: the `Set.equals` contract still ignores order. Two sets containing the same elements can be equal even if they iterate in opposite directions. The new type does not turn set equality into list equality. [Java 21: SequencedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedSet.html).

For example, "unique filter tags, shown in the order selected" fits a linked set. "Unique codes, always in comparison order" fits a sorted set. Both can be handled via `SequencedSet` when a function only cares about their common capabilities, while the site creating the data must decide the ordering policy.

### 5.3. SequencedMap: sequence of key–value mappings

`Map` is not a `Collection`. The unit of `SequencedMap` is a key–value mapping, so this interface extends `Map` separately.

It provides `firstEntry()`, `lastEntry()`, `pollFirstEntry()`, `pollLastEntry()`, `putFirst(k, v)`, `putLast(k, v)`, and `reversed()`. When the map is empty, the methods that retrieve or remove an entry at either end return `null`. Entries returned by the first four methods are snapshots of the mapping at the time of the call and do not support `setValue` to modify the underlying map. [Java 21: SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html).

A problem like "counts per stage, displayed in workflow order" needs both key lookup and order. Using a sequenced map avoids splitting this into a lookup map plus a list of keys and manually keeping both data sources synchronized.

### 5.4. Why do we need views named sequenced?

The familiar map view return types are `Set<K>`, `Collection<V>`, and `Set<Map.Entry<K,V>>`. They can iterate in the map's sequence, but those signatures do not directly expose the full first/last/reverse vocabulary.

The new methods express this more clearly:

~~~java
java.util.SequencedSet<String> keys = counts.sequencedKeySet();
java.util.SequencedCollection<Integer> values = counts.sequencedValues();
java.util.SequencedSet<java.util.Map.Entry<String, Integer>> entries =
        counts.sequencedEntrySet();
~~~

This is an illustrative snippet inside a method, assuming `counts` is a `SequencedMap<String,Integer>`.

Values can repeat, so `sequencedValues()` returns `SequencedCollection` rather than `SequencedSet`. A key view lacks the value information needed to insert a new mapping; do not assume from the return type name that calling `addFirst` will succeed on every view.

## 6. Unification lies in the contract, not in replacing everything with one class

The familiar classes still have their roles. For instance, `ArrayList` remains a resizable-array list with positional access and support for `null`. It is used through the new interface thanks to the added type relationship, not because a copy is automatically created. [Java 21: ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

A function that reports the first and last elements can be written in Java 21 as follows:

~~~java
static String describeEnds(java.util.SequencedCollection<?> items) {
    if (items.isEmpty()) {
        return "empty";
    }
    return items.getFirst() + " -> " + items.getLast();
}
~~~

The function does not know whether the object is backed by an array, linked nodes, or a tree. Nor does it need to know whether duplicate elements are allowed. It relies solely on the first/last contract.

Conversely, if an algorithm needs `get(i)`, `SequencedCollection` is not enough. If an algorithm needs a capacity-bounded queue with `offer`/`poll`, `Deque` or another appropriate type is still necessary. New names are not a reason to downgrade every signature to the same level of abstraction.

The snippet above that checks `isEmpty` and then reads both ends is intended for contexts without concurrent modifications during the operation. Two separate method calls do not automatically form an atomic snapshot. If multiple threads mutate the data, you must design synchronization or snapshotting appropriate to the implementation.

## 7. reversed(): changing the viewing direction, distinct from copying

Picture the original data:

~~~text
original:      A   B   C
reverse view:  C   B   A

view.getFirst()  <->  original.getLast()
view.getLast()   <->  original.getFirst()
~~~

`reversed()` returns a **reverse-ordered view**. For a `List` such as `ArrayList`, permitted mutations through the view can write through to the original list. For example:

~~~java
java.util.List<String> original =
        new java.util.ArrayList<>(java.util.List.of("A", "B", "C"));
java.util.List<String> backwards = original.reversed();
backwards.addFirst("D");
// original: [A, B, C, D]
// backwards: [D, C, B, A]
~~~

This is a Java 21 illustrative snippet inside a method. Adding at the front of the reverse view corresponds to adding at the end of the original direction. No "physical array reversal" command is required here.

You must read the specific contract when relying on observing changes from the underlying structure. The general interface states that the extent to which changes from the backing source are visible depends on the implementation. It does not promise that every `SequencedCollection` implementation has the same update, iterator, or thread-safety characteristics.

For `LinkedHashMap`, the class documentation explicitly specifies that changes through the reverse view propagate to the backing map and changes to the backing map are visible through the view; access order may also be affected if the map was created in access-order mode. [Java 21: LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html).

### 7.1. When do you need to copy?

If a feature needs to preserve the sequence at a specific point in time, create structurally independent data:

~~~java
java.util.List<String> saved =
        new java.util.ArrayList<>(original.reversed());
~~~

`saved` receives the elements in reverse order at the time of copying, and its structure will not change when elements are added to or removed from `original`. This is still a shallow copy: if the elements are mutable objects, both structures can hold references to the same objects. If a deep snapshot is needed, you must apply an appropriate policy for the element type.

Do not use `reversed()` just because the initial output looks like a reversed copy. The two choices have different data-ownership semantics.

### 7.2. Reverse streams become more natural

One practical benefit is pushing the traversal direction into the data source:

~~~java
var display = original.reversed().stream().toList();
~~~

You no longer need to manually copy into a list and reverse that list just to obtain a reverse stream. If you switch to a parallel stream, encounter order remains a property of the source; task execution order in `forEach` is not guaranteed to follow that sequence. When side effects must follow encounter order, look at `forEachOrdered`; do not infer from `reversed()` that every parallel stream will print in the expected order. [Java 21: Stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html).

## 8. Having an order does not mean arbitrary placement is allowed

A common interface needs to describe mutable structures, unmodifiable structures, and structures whose order is governed by another rule. Therefore, many mutating operations are optional and may throw `UnsupportedOperationException`.

### 8.1. Linked sets can reposition an element

In `LinkedHashSet`, a regular `add` with an already-present element does not change its order. `addFirst` and `addLast` can move an existing element to the front or back without creating a duplicate.

For example, suppose a set of tags is `[ship, build, test]`. Calling `addFirst("test")` produces `[test, ship, build]`; calling `add("ship")` afterward keeps that sequence. A "pin to top" feature is expressed directly instead of removing and re-adding with extra side rules. [Java 21: LinkedHashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashSet.html).

### 8.2. Sorted sets must preserve comparison rules

Suppose a `TreeSet<Integer>` currently holds `[10, 20, 30]` in natural order. Allowing `25` to be placed at the front would contradict the sorting requirement. For this reason, `SortedSet` does not support explicit positioning via `addFirst` and `addLast`; these methods throw `UnsupportedOperationException`.

This remains true even when the value you intend to add happens to fit the first or last position. Do not test-call with an "in-order" value and treat it as valid usage; add via `add` so the structure determines the position itself. [Java 21: SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html).

### 8.3. Sorted maps have the same boundary

`SortedMap` determines its sequence by key comparison. It can be used as a `SequencedMap` to view the first, last, and reverse order, but `putFirst` and `putLast` are not supported because they attempt to impose a position. `put` remains the way to insert or update according to the map's rules. [Java 21: SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html).

A `TreeMap` sorts by key, not by value. If the input is key `2` then key `1`, the natural iteration order is `1, 2`; using `SequencedMap` does not turn it into insertion order. [Java 21: TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

### 8.4. Unmodifiable wrappers should still preserve order information

Previously, using a wrapper that returned `Set` could cause the signature to lose its ability to express order, even when the underlying object was a linked set.

Java 21 provides the following methods:

- `Collections.unmodifiableSequencedCollection(...)`;
- `Collections.unmodifiableSequencedSet(...)`;
- `Collections.unmodifiableSequencedMap(...)`.

They preserve the sequenced contract type and block modifications through the wrapper. They are views, not a promise that the backing source will never change; query operations read through to the backing data. [Java 21: Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

This is useful for APIs returning read-only data: callers still know they can get the first/last elements and read in reverse. If an independent snapshot is required, create a copy with a clear ordering policy and wrap the copy; merely wrapping a live source does not satisfy that requirement.

## 9. Equality and complexity are not unified under the new names

### 9.1. Sequence may matter for iteration without participating in equals

`List.equals` compares both elements and their corresponding positions. A list `[A, B]` differs from `[B, A]`. Meanwhile, `Set.equals` is about having the same members; adding sequenced capability does not change this contract. [Java 21: Set](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html).

Similarly, `Map.equals` checks for the same mappings, not iteration order. A `LinkedHashMap` and its reverse view can be equal even though they report two different orders. [Java 21: Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html).

Therefore, if a test needs to verify **sequence**, compare the collected sequence—for example, a list of keys. A test that only calls `expectedSet.equals(actualSet)` can miss an interface ordering bug.

Likewise, do not assume a `SequencedCollection<?>` parameter has list-style equality: it could be referencing a set or another type. The common interface does not impose a single `equals` definition that conflicts with its sub-branches.

### 9.2. Same operation name does not mean same cost

`getLast` or `addFirst` helps clarify intent. It does not automatically change the object's underlying storage algorithm into another one.

For example, adding to the front of an `ArrayList` must shift existing elements backward. As the number of elements grows, that work grows accordingly; changing `add(0, value)` to `addFirst(value)` mainly improves expressiveness. An algorithm that frequently adds/removes at both ends must still choose a structure suited to the actual workload.

Do not write a general-purpose function accepting `SequencedCollection` and promise that every operation at either end runs in constant time. To make performance commitments, you must rely on the documentation of the specific implementation and usage.

## 10. Full program: same contract, different policies

Save the entire code below into **`SequencedMotivationDemo.java`**. The program uses ASCII strings for stdout so that output does not depend on how diacritics are rendered in the terminal.

It verifies four things: one function can accept multiple sequenced types; reverse viewing differs from copying; sets/maps retain their own contracts; and positioning operations may be unsupported.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.SequencedCollection;
import java.util.SequencedMap;
import java.util.SequencedSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class SequencedMotivationDemo {
    static String ends(SequencedCollection<?> items) {
        if (items.isEmpty()) {
            return "empty";
        }
        return items.getFirst() + " -> " + items.getLast();
    }

    static String failure(Runnable action) {
        try {
            action.run();
            return "no exception";
        } catch (UnsupportedOperationException | java.util.NoSuchElementException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        List<String> stages = new ArrayList<>(List.of("build", "test", "ship"));
        Deque<String> jobs = new ArrayDeque<>(List.of("build", "test", "ship"));
        SequencedSet<String> unique =
                new LinkedHashSet<>(List.of("ship", "build", "test", "build"));
        SequencedSet<String> sorted =
                new TreeSet<>(List.of("ship", "build", "test", "build"));

        System.out.println("list ends: " + ends(stages));
        System.out.println("deque ends: " + ends(jobs));
        System.out.println("linked set ends: " + ends(unique));
        System.out.println("sorted set ends: " + ends(sorted));
        System.out.println("reverse stream: " + stages.reversed().stream().toList());

        List<String> backwards = stages.reversed();
        List<String> snapshot = new ArrayList<>(backwards);
        backwards.addFirst("archive");
        System.out.println("list after reverse addFirst: " + stages);
        System.out.println("reverse view now: " + backwards);
        System.out.println("reverse copy stays: " + snapshot);

        unique.addFirst("test");
        unique.add("ship");
        System.out.println("set after reposition: " + unique);
        System.out.println("set equals reverse: " + unique.equals(unique.reversed()));
        System.out.println("list equals reverse: " + stages.equals(stages.reversed()));

        SequencedMap<String, Integer> counts = new LinkedHashMap<>();
        counts.put("build", 1);
        counts.put("test", 2);
        counts.put("ship", 3);
        System.out.println("map first: " + counts.firstEntry());
        System.out.println("map reverse first: " + counts.reversed().firstEntry());
        counts.putFirst("test", 20);
        System.out.println("map after putFirst: " + counts);
        System.out.println("map keys: " + counts.sequencedKeySet());
        System.out.println("map values: " + counts.sequencedValues());
        System.out.println("reverse map keys: " + counts.reversed().sequencedKeySet());
        System.out.println("map equals reverse: " + counts.equals(counts.reversed()));

        LinkedHashSet<String> colors =
                new LinkedHashSet<>(List.of("red", "blue"));
        SequencedSet<String> readOnly =
                Collections.unmodifiableSequencedSet(colors);
        colors.addLast("green");
        System.out.println("read-only view sees: " + readOnly);
        System.out.println("read-only add: " + failure(() -> readOnly.addFirst("black")));

        System.out.println("sorted addFirst: " + failure(() -> sorted.addFirst("alpha")));
        SequencedMap<Integer, String> orderedByKey = new TreeMap<>();
        orderedByKey.put(2, "two");
        orderedByKey.put(1, "one");
        System.out.println("sorted map keys: " + orderedByKey.sequencedKeySet());
        System.out.println("sorted map putLast: "
                + failure(() -> orderedByKey.putLast(0, "zero")));

        SequencedCollection<String> empty = new ArrayList<>();
        System.out.println("empty getFirst: " + failure(() -> empty.getFirst()));
        SequencedMap<String, Integer> emptyMap = new LinkedHashMap<>();
        System.out.println("empty map first: " + emptyMap.firstEntry());
    }
}
~~~

Compile with JDK 21 or later, setting the target API/language level to 21, then run on Java 21 or later:

~~~shell
javac --release 21 -encoding UTF-8 SequencedMotivationDemo.java
java SequencedMotivationDemo
~~~

No `--enable-preview` is needed. If compiling with a newer JDK, `--release 21` helps catch accidental use of APIs introduced after Java 21. This example was compiled with release level 21 and ran successfully on OpenJDK 24.0.2.

Exact stdout:

~~~text
list ends: build -> ship
deque ends: build -> ship
linked set ends: ship -> test
sorted set ends: build -> test
reverse stream: [ship, test, build]
list after reverse addFirst: [build, test, ship, archive]
reverse view now: [archive, ship, test, build]
reverse copy stays: [ship, test, build]
set after reposition: [test, ship, build]
set equals reverse: true
list equals reverse: false
map first: build=1
map reverse first: ship=3
map after putFirst: {test=20, build=1, ship=3}
map keys: [test, build, ship]
map values: [20, 1, 3]
reverse map keys: [ship, build, test]
map equals reverse: true
read-only view sees: [red, blue, green]
read-only add: UnsupportedOperationException
sorted addFirst: UnsupportedOperationException
sorted map keys: [1, 2]
sorted map putLast: UnsupportedOperationException
empty getFirst: NoSuchElementException
empty map first: null
~~~

### 10.1. Reading the output groups by meaning

**First four lines:** the same `ends` function handles `List`, `Deque`, a linked set, and a sorted set. Both sets receive the same initial data, yet their first/last elements differ because their ordering policies differ. The repeated string `build` does not create two elements in the sets.

**Three lines after view mutation:** `backwards.addFirst("archive")` places the element at the end of the original list. The view reflects the new reversed order; `snapshot` remains the sequence copied earlier. The program does not create an iterator and then mutate the data during iteration.

**Lines about sets:** `test` is moved to the front; calling `add("ship")` does not move an already-present element. The set remains equal to its reverse view by membership. The list is not equal to its reverse view for this data because corresponding positions do not match.

**Lines about maps:** the map starts in insertion order. `putFirst("test", 20)` both updates the existing key's value and moves that mapping to the front. The key view and value view follow the same mapping sequence; the reverse view flips the direction of both.

**Final group:** the backing source of the read-only wrapper has `green` added, so the view sees that element. Modifying through the wrapper is blocked. The sorted set and sorted map reject explicit positioning, even though they still have an order for reading. Empty collections and empty maps use different return conventions on the illustrated methods.

### 10.2. Why didn't the program try printing HashSet order?

The goal is to demonstrate a contract you can rely on, not to pick an accidental result and memorize it. A single `HashSet` print is not enough to prove or disprove a business ordering requirement. Here, the difference shows up immediately in what can be passed to `ends`: a `HashSet` does not conform to this parameter type.

## 11. Bringing this into real-world API design

Start from what the business domain wants to say, and only then choose the interface:

| Function need | Potentially suitable type | What still must be specified |
| --- | --- | --- |
| Iterate elements, order irrelevant | `Collection<E>` | Duplicates, mutability, element constraints |
| View first/last, read in both directions | `SequencedCollection<E>` | Sequence semantics, empty data, mutability |
| Need index `i` or list semantics | `List<E>` | Access and update cost of implementation |
| Unique, with a sequence | `SequencedSet<E>` | Insertion order, comparison, or another policy |
| Key lookup and mapping sequence | `SequencedMap<K,V>` | Ordering policy, `null` key/value handling |
| Double-ended queue workflow | `Deque<E>` | Empty behavior, capacity bounds, concurrency |

An example returning "selected filters, unique and displayed in the order chosen by the user" can use `SequencedSet<Filter>` backed by a `LinkedHashSet`, then wrap it in a read-only view of the same type if appropriate for its lifecycle.

An example reporting "metrics by ascending key" can use `SortedMap` or `NavigableMap` if API callers also need the comparator or range queries. If only first/last access and iteration are needed, `SequencedMap` may be a sufficient contract level. Do not hide a capability callers genuinely need just to use a new name.

If you change the signature of an already published API, that is still a compatibility decision to evaluate. The fact that a JDK class gained a type relationship does not give you license to arbitrarily change every parameter, return type, or version requirement of a library others depend on.

### 11.1. Do not cast to "create" order

The snippet below is an **invalid runtime example**, not part of the main program:

~~~java
java.util.Collection<String> source = new java.util.HashSet<>();
java.util.SequencedCollection<String> ordered =
        (java.util.SequencedCollection<String>) source;
~~~

A cast does not add a contract that the object does not implement. This `HashSet` instance will throw a `ClassCastException` at the cast.

If the input truly has no business order, you must decide on a conversion policy. Copying into an `ArrayList` only preserves the iteration order observed at copy time; copying into a `TreeSet` creates an order by comparison and deduplicates. The two conversions have different meanings and are not interchangeable type fixes.

### 11.2. Define empty behavior explicitly

A function returning "first/last" must decide whether empty input is valid, returns a no-data result, or reports a domain error. The demo's `ends` method returns the string `empty`; that is the function's choice, not a mandatory rule of `SequencedCollection`.

Do not write every helper by catching `Exception` and returning `null`. That approach can mask unsupported-operation errors, data errors, and programming bugs alike. A sequenced input type helps express one aspect; the failure policy still needs to be designed explicitly.

## 12. Misconceptions that lead to poor design

1. **"Java 21 is the first version with ordered collections."** Ordered structures existed long before. What is new is the unified interface layer and operation set to express and use what they share.
2. **"Sequenced means ascending."** A list in user-selected order is also sequenced. Comparison-based rules are a specific capability of the sorted family.
3. **"Every Set becomes a SequencedSet."** Only appropriate types provide that contract. Do not rely on the incidental order of a structure that guarantees none.
4. **"If addFirst exists, calling it always works."** Mutating operations may be rejected by a wrapper or by sorting rules.
5. **"reversed copies the data."** A view and a copy have different ownership and lifecycles. Create a copy yourself when you need structurally independent data.
6. **"Having an order is enough, no need to worry about duplicates."** `SequencedCollection` does not guarantee uniqueness; `SequencedSet` is what combines the set contract.
7. **"equals will check the order of sets and maps too."** The new types preserve the `equals` contracts of their respective branches. Verify order using an appropriately ordered representation.
8. **"Cleaner methods make every operation faster."** API names do not change the underlying array, linked, or tree structure.
9. **"Read-only means a fixed snapshot."** A wrapper view blocks mutation through one access path; the underlying source can continue to change.
10. **"Using the new interfaces still runs on Java 17."** The target standard library must contain those types. You must align the compile JDK, release target, and runtime version.

## 13. Practice with answers

### Exercise 1 — Choosing a signature for a utility

A function only needs to display the first element, the last element, and the elements in reverse order. It must accept lists, double-ended queues, and linked sets. Choose one general parameter type in Java 21, and state two things that type does not promise.

**Answer:** use `SequencedCollection<? extends E>` or `SequencedCollection<?>` depending on how elements are used. The type does not state that the sequence is insertion order, nor does it promise mutability; it also does not promise uniqueness, complexity bounds, or thread safety. If the function is read-only, do not add mutability requirements to the contract.

### Exercise 2 — Order and business logic

A function that prints bus route stops accepts `SequencedCollection<String>`. A caller passes a `TreeSet` of stop names sorted alphabetically. The compiler accepts it. Can you conclude the route is correct?

**Answer:** no. The type guarantees a sequence, but does not specify that the sequence is the travel schedule. You need a domain contract and the right data source; the parameter name or documentation must state "in route order," and you must choose a structure that preserves that rule.

### Exercise 3 — Predicting views and copies

Start with `List<Integer> a = new ArrayList<>(List.of(2, 4, 6))`. Take `r = a.reversed()` and `saved = new ArrayList<>(r)`. Then call `r.addFirst(8)`. What are the three sequences?

**Answer:** `a` is `[2, 4, 6, 8]`; `r` is `[8, 6, 4, 2]`; `saved` is `[6, 4, 2]`. These are immutable `Integer` elements, so the example has no shared mutable-object issue.

### Exercise 4 — Uniqueness and positioning

A `LinkedHashSet` contains `[A, B, C]`. Call `add("B")` and then `addLast("A")`. Are there four elements? What is the final sequence?

**Answer:** still three elements. `add("B")` keeps `B`'s position; `addLast("A")` moves `A` to the end, resulting in `[B, C, A]`. Do not carry this rule over to `TreeSet`; explicit positioning operations are rejected on sorted sets.

### Exercise 5 — Testing map order

Two maps have the same mappings, but their keys iterate in two different orders. A test using `expected.equals(actual)` still passes. What must be added if order is an interface requirement?

**Answer:** compare the sequence of keys or entries—for example, create `new ArrayList<>(actual.sequencedKeySet())` and compare it against the expected list. Do not mentally redefine `Map.equals`; directly test what the business logic cares about.

### Exercise 6 — Fixing an operation choice bug

A `SequencedMap<Integer,String>` is actually a `TreeMap`. A developer calls `putFirst(0, "start")` because `0` is the smallest key and hits an error. What is the appropriate fix?

**Answer:** use `put(0, "start")` so the map sorts by key. `putFirst` remains unsupported even when the key happens to fit the front. If the business logic needs to pin an arbitrary key to the front, revisit the choice of structure and ordering policy, such as a linked map; do not catch the error and pretend the operation succeeded.

### Exercise 7 — Read-only or snapshot?

An API creates `Collections.unmodifiableSequencedSet(source)` and returns it to the UI. Another part of the application adds elements to `source`. Can you promise the returned result will not change?

**Answer:** you cannot make that promise from the wrapper alone. If a structurally independent ordered snapshot is needed, create a separate copy with the right policy and wrap the copy; if elements have mutable state, also address the required level of copying.

### Exercise 8 — Verifying version levels yourself

Try compiling the main program with `javac --release 17`, then with `javac --release 21` on a supporting JDK. Why is the first unsuitable, and why is upgrading only the runtime not enough for a pipeline compiling with target 17?

**Answer:** the `Sequenced*` APIs are not part of the Java 17 standard library. `--release` controls the target API/language level at compile time; a newer runtime does not make Java 21 types appear in release target 17. You must align the Java 21+ requirement for code using these APIs, while checking the compatibility the project needs to maintain.

When modifying the program yourself, add a new structure to the `ends` function and explain the source of its first/last order before running it. The result has learning value when you can predict which contract is being enforced, not just when stdout happens to match what you expected.
