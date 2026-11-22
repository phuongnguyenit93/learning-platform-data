# Foundational Knowledge and Learning Sequence for Collection Groups

Learning the Java Collections Framework can easily turn into memorizing class names—`ArrayList`, `HashSet`, `HashMap`—and picking a class out of habit. That approach might help you write a few statements, but it does not answer the important question: **what rules should govern how this data is organized, and will that choice still hold when requirements change?**

This article builds the foundation and learning sequence for the collection groups in Java Core. The goal is to know what to learn first, why that order makes sense, when you can move on to the next group, and how to connect the groups into a complete solution.

The examples use APIs available in Java 17. The complete program in the demonstration section can be compiled with JDK 17 or later. The remaining short snippets illustrate a single idea; they are not standalone programs.

## 1. Start from the problem, not from class names

Suppose a program receives registration entries with codes:

```text
S2, S1, S2
```

The same input data can give rise to many different requirements:

| Requirement | Semantics to preserve | Group to explore |
| --- | --- | --- |
| Keep every registration entry in positional order | Ordered, duplicates allowed | `List` |
| Get the distinct codes that appeared | No duplicates | `Set` |
| Count registrations per code | One key associated with one count value | `Map` |
| Process sequentially in waiting order | Head-removal policy | `Queue` or `Deque` used as a queue |
| Process higher-priority tasks first | Priority-based element selection policy | `PriorityQueue` |
| Get codes in ascending order or find the closest code | Ordering and navigation relationships | `SortedSet`, `NavigableSet`, `SortedMap`, `NavigableMap` |

No single collection expresses all of the above requirements well on its own. Switching from `List` to `Set` can lose information about duplicate entries; switching to a class that does not guarantee order can lose the order required by business logic.

Before writing `new`, answer:

1. Is the unit being stored a single element or a key–value pair?
2. Do duplicate elements carry meaning?
3. Do you need positional order, insertion order, sorted order, or priority order?
4. Are the frequent operations lookup, appending to the end, removing from the front, or range queries?
5. Who is allowed to modify the data? Will multiple threads access it concurrently?

These five questions are the thread connecting the entire roadmap.

## 2. Foundational knowledge to prepare

You do not need to master all of Java before using `ArrayList`. However, certain fundamentals must be learned before diving deep into how each group works.

### 2.1. Variables, loops, methods, and arrays

You need to know how to declare variables, pass parameters, receive return values, use `if`, `for`, `while`, and read a simple method.

Arrays are a good point of comparison:

- An array has a fixed length once created.
- Arrays are zero-indexed.
- Arrays can store primitive types or reference types.
- When you want to add more elements than capacity allows, you have to create another array and copy the data manually.

Collections solve many data-organization needs that learners should not have to rebuild from scratch every time. Even so, collections are not just "resizable arrays": duplicate-free sets, key–value maps, and queues each have their own rules.

**Sign you have enough foundation:** you can write a loop to sum an array on your own and explain why accessing index `array.length` is invalid.

### 2.2. Objects, references, and mutability

For collections holding objects, you need to understand that a collection normally stores references to objects. Adding an object to a list does not automatically create a deep copy of that object.

Two variables can point to the same list; two different lists can point to the same elements in terms of object identity.

Illustration:

```java
List<StringBuilder> first = new ArrayList<>();
first.add(new StringBuilder("A"));

List<StringBuilder> second = new ArrayList<>(first);
second.get(0).append("B");
```

After these statements:

- `first` and `second` are two distinct list objects.
- Their element at index 0 points to the exact same `StringBuilder`.
- That object's content is `"AB"`.

This is why you must distinguish **copying the container structure holding references** from **deep-copying all objects inside**. This knowledge will be used when learning copy constructors, views, defensive copies, and unmodifiable collections.

### 2.3. Interfaces, implementation classes, and polymorphism

Learners should be able to read declarations like:

```java
List<String> names = new ArrayList<>();
```

Here:

- `List<String>` expresses the contract that the code requires.
- `ArrayList<>` is the implementation class chosen to fulfill that contract.
- The `names` variable only allows direct calls to methods exposed by its declared type.

Programming to an interface reduces coupling to a concrete class. However, swapping implementation classes still requires checking ordering, performance, `null` rules, mutability, and synchronization requirements. Implementing the same interface does not mean all characteristics are identical.

**Sign you have enough foundation:** you can explain why `new List<String>()` cannot be written, and why a variable of type `Collection<String>` does not provide `List`'s index-based access operations.

### 2.4. Generics and element types

You need to understand `List<String>`, `Set<Integer>`, `Map<String, Integer>`, and the role of compile-time type checking.

Early essentials to know:

- Generic type arguments must be reference types: use `Integer`, not `int`, inside `List<...>`.
- Boxing and unboxing can occur when inserting integers into or retrieving them from a collection.
- Unboxing a `null` value can throw `NullPointerException`.
- Raw types like `List` weaken type checking and should be avoided in new code.
- `List<Integer>` is not a subtype of `List<Number>`.

You do not need to start with the full theory of wildcards. A good sequence is to use concrete parameterized types first, then learn `?`, `? extends T`, and `? super T` when designing methods that accept or transfer data between collections.

**Sign you have enough foundation:** you can read a method that accepts `List<String>` without having to cast each element to `String`.

### 2.5. Exceptions and method contracts

Not every error when using a collection is a bug in the data structure. You need to know how to read exception names alongside the conditions that trigger them:

| Exception or result | Question to check |
| --- | --- |
| `IndexOutOfBoundsException` | Is the index within the valid range? |
| `UnsupportedOperationException` | Does this collection support the modification operation being called? |
| `NullPointerException` | Was `null` passed where disallowed, or was `null` unboxed? |
| `ClassCastException` | Is there a raw type, an invalid cast, or non-comparable elements? |
| `ConcurrentModificationException` | Was the structure modified outside what the iterator allows while iterating? |
| `false`, `null`, or previous value | What is this method using its return value to signal? |

The word "concurrent" in the exception name does not prove the program is multithreaded. A single thread can also cause an invalid structural modification during iteration. Do not rely on this exception as a thread-safety guarantee.

### 2.6. Equality, hashing, and comparison

Three concepts must be kept separate:

- `==` on references checks whether two references point to the same object.
- `equals` expresses value equality as defined by the class.
- `Comparator` or `Comparable` expresses comparison order.

Before `HashSet` and `HashMap`, you must learn the `equals`–`hashCode` contract: two objects that are equal according to `equals` must have the same hash code; having the same hash code does not require them to be equal.

Before `TreeSet`, `TreeMap`, and `PriorityQueue`, you must learn natural ordering or `Comparator`. A negative, zero, or positive comparison result expresses ordering; do not write numeric comparators using subtraction if subtraction can overflow.

In particular, `TreeSet` treats two elements as occupying the same position in the set when comparison returns 0. `TreeMap` also uses comparison to identify equivalent keys in the tree. If you compare students only by name, two students with different IDs but the same name may be treated as duplicates in a `TreeSet`. A comparator should be consistent with `equals` so that the set or map obeys its general contract.

### 2.7. Complexity and basic data structures

You only need to start with:

- `O(1)`: the number of steps does not grow with the number of elements in the analytical model.
- `O(log n)`: the number of steps grows slowly with size.
- `O(n)`: may need to inspect a number of elements proportional to size.
- `O(n log n)`: commonly seen in comparison-based sorting algorithms.

Only after that should you study dynamic arrays, linked lists, hash tables, balanced trees, and heaps.

Complexity is not wall-clock time in milliseconds. You need to distinguish average case, worst case, and amortized cost; small data sizes, memory allocation, and access patterns also affect real-world results.

## 3. Map of the groups before diving deep

In Java 17, you can use the simplified diagram below. It shows only the main interfaces used in this roadmap, not the entire JDK type hierarchy.

```text
Iterable<E>
└── Collection<E>
    ├── List<E>
    ├── Set<E>
    │   └── SortedSet<E>
    │       └── NavigableSet<E>
    └── Queue<E>
        └── Deque<E>

Map<K, V>
└── SortedMap<K, V>
    └── NavigableMap<K, V>
```

`Map` belongs to the Java Collections Framework but does not extend `Collection`. It organizes key–value pairs; `keySet()`, `values()`, and `entrySet()` provide collection-style views. Therefore, do not assume a method accepting `Collection<E>` will directly accept a `Map<K, V>`. See the [Java 17 Collections Framework Overview](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html).

Three easily confused names:

| Name | Role |
| --- | --- |
| "collection" in prose | General term for a structure holding multiple elements |
| `Collection<E>` | Base interface for `List`, `Set`, `Queue`, and related branches |
| `Collections` | Utility class with static methods such as sorting, reversing, or creating wrappers |

Do not learn `Collections` under the assumption that it is simply the plural version of the `Collection` interface.

## 4. Recommended learning sequence

This sequence is designed for beginners: moving from easily observable operations to contracts that are easy to misuse. Basic `Queue` and `Deque` can be learned right after `List`; priority queues should be learned after comparison concepts. There is no requirement that everyone follow a single rigid order.

### Stage 1: Collection and iteration

Learn common operations such as `size`, `isEmpty`, `add`, `contains`, `remove`, `clear`, and the `for-each` loop.

The goal is not yet to analyze internal mechanics. The goal is to understand "holding elements," read return values, and know which operations mutate data.

Next, learn `Iterable`, `Iterator`, `hasNext()`, `next()`, and removing through an iterator when supported. `for-each` is convenient for sequential reading; it is not permission to call arbitrary collection-mutating methods directly inside the loop body.

Stage milestone exercise: take a list of numbers, count the positive numbers using a loop, then remove negative numbers using an appropriate approach such as `removeIf` on a modifiable list.

**Ready to advance when:** you can explain why the return value of `add` or `remove` must be interpreted according to the specific contract, and why a variable of a collection type does not by itself guarantee support for every mutating operation.

### Stage 2: List, starting with ArrayList

`List` is appropriate when position and duplicate elements matter. Learn:

1. Appending to the end, inserting at an index, reading with `get`, replacing with `set`.
2. Removing by index versus removing by value.
3. Iterating in order and searching.
4. The relationship between logical size and internal array capacity in `ArrayList`.
5. Element-shifting cost when inserting or removing in the middle.

Start with `ArrayList` because it connects naturally to array knowledge. Then compare `LinkedList` to see how two `List` implementations can have very different access mechanics.

Do not conclude "use `LinkedList` when doing many insertions and deletions" without asking how the target position is located. `LinkedList.get(i)` must traverse nodes; calling `get(i)` on every iteration of a loop can turn a linear scan into quadratic cost.

Stage milestone exercise: manage registration entries while keeping entries with the same code. Clearly distinguish replacing one position from removing all entries for a given code.

**Ready to advance when:** you can choose an appropriate iteration approach, explain the cost of middle insertion in `ArrayList`, and avoid confusing list order with sorted order. See the core contract in [Java 17 List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

### Stage 3: Set and what "unique" means

Learn `Set` after you already understand `equals` and `hashCode`.

Compare:

- `HashSet`: checks membership and removes duplicates, with no guaranteed iteration order.
- `LinkedHashSet`: removes duplicates and preserves insertion order in typical usage.
- `TreeSet`: manages elements in comparison order; save navigation queries for a later stage.

The key question is **what counts as two duplicate elements in the problem's model?** For `String`, the answer is relatively straightforward. For a `Student` class, you must decide whether equality is based on student ID or on both ID and name.

Stage milestone exercise: from registration entries, extract unique codes under three requirements in turn: order does not matter, preserve first-seen order, and ascending order. Show which implementation class change satisfies each requirement.

**Ready to advance when:** you can explain why a set can encounter two distinct object references yet keep only one element based on value equality, and why a set's ordering cannot be inferred from a few sample printouts. See the [Set contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### Stage 4: Map and organizing data by key

Learning `Map` after `Set` lets you reuse equality and hashing knowledge for keys.

Master `put`, `get`, `containsKey`, `remove`, `getOrDefault`, and iterating over `entrySet`. Once you understand the loop-based version, add `merge`, `computeIfAbsent`, and other function-taking operations.

Rules to observe:

- Keys are unique according to the map's key-equality rules.
- Values may be duplicated.
- Calling `put` with an existing key normally replaces the value associated with that key.
- A key can be mapped to a collection, such as `Map<String, List<String>>`, when the problem needs multiple values per key.
- `get(key) == null` is not always enough to conclude a key is absent in a map that permits `null` values.

Compare `HashMap`, `LinkedHashMap`, and `TreeMap` in terms of lookup, ordering, and cost.

Stage milestone exercise: count registrations by code. Then change to grouping registration entries into lists by code; explain why the two tasks require different value types.

**Ready to advance when:** you can distinguish "key not yet present" from "existing value replaced," and use `entrySet` to process each pair. See the [Map contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### Stage 5: Queue and Deque by processing policy

In earlier stages, the main question was "how should it be stored?" With queues, you must also ask "which element is taken next?"

Learn `Deque` with `ArrayDeque` to see:

- Adding at the tail and removing from the head gives FIFO usage.
- Adding and removing at the same end gives LIFO usage.
- `Deque` provides operations at both ends.
- Method pairs can differ in how they report failure: throwing an exception versus returning a special value.

For example, when a queue is empty, `remove()` throws an exception while `poll()` returns `null`. Avoid putting `null` into a queue because it creates ambiguity with the empty result; `ArrayDeque` forbids `null` elements.

Next, learn `PriorityQueue`. This is not a FIFO queue. With the natural ordering of integers, the smallest element is removed first. A different comparator can define a different priority. Iterating directly over a `PriorityQueue` does not guarantee full sorted order; to observe processing order, remove elements one by one from the head.

Stage milestone exercise: simulate a waiting queue and a prioritized task list. Demonstrate that insertion order and processing order can differ.

**Ready to advance when:** you can distinguish FIFO, LIFO, and priority ordering, and choose the right empty-reporting method. See [Java 17 Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

### Stage 6: Sorted and navigable groups

Revisit `TreeSet` and `TreeMap` after studying `Comparable` and `Comparator` thoroughly.

Distinguish:

- `SortedSet` and `SortedMap`: maintain ordering along with range-based operations.
- `NavigableSet` and `NavigableMap`: add queries such as strictly less than, less than or equal to, greater than or equal to, and strictly greater than.

You do not need to memorize every method name immediately. First connect requirements to the meaning of `lower`, `floor`, `ceiling`, and `higher`.

Stage milestone exercise: given the score set `{50, 70, 90}`, distinguish the closest score not exceeding 80 from the smallest score that is 80 or above. The results are 70 and 90, respectively.

**Ready to advance when:** you can express boundary conditions accurately and understand how a comparator affects both ordering and element/key identity in a tree structure.

### Stage 7: Modifiability, views, and copying

This is essential before designing APIs that return collections outside a class.

Distinguish:

| Way to create or obtain a list | Key meaning to remember |
| --- | --- |
| `new ArrayList<>(source)` | Creates a new modifiable list; does not deep-copy elements |
| `List.of(...)` | Unmodifiable list that rejects `null` elements |
| `List.copyOf(source)` | Returns an unmodifiable list with the source's elements at call time; does not deep-copy elements |
| `Arrays.asList(array)` | Fixed-size list backed by the array; elements can be replaced via `set`, cannot add or remove |
| `Collections.unmodifiableList(source)` | Unmodifiable view wrapper; changes to the source may still be visible |
| `list.subList(from, to)` | View of a portion of a list; must respect the backing list's contract |

Being unmodifiable through a reference does not mean the entire data graph is deeply immutable. If the elements are mutable objects, the contents of those elements can still change. With `List.copyOf`, do not rely on it always allocating a brand-new instance; rely on the contract of the returned list.

Stage milestone exercise: expose a list from a data-management class; choose among allowing direct modification, returning a read-only view, and returning a structural snapshot. Explain the impact when the source or an element mutates.

### Stage 8: Utility algorithms and Stream processing

Learn sorting, reversing, searching, and copying after understanding whether the source collection is modifiable.

Conditions you must check:

- Sorting requires a valid comparison mechanism.
- Binary search requires data sorted in the corresponding order.
- In-place sorting differs from creating a new result list.
- Deduplication still depends on equality semantics.
- Transformed results may have a different modifiability contract than the source.

After loops, learn lambdas, method references, and Streams to write filtering, mapping, grouping, and counting. Distinguish a collection that stores data from a stream that represents a processing pipeline; a stream is not a second collection and cannot be reused after a terminal operation.

Do not use Streams to mask a lack of understanding of data types, ordering, or duplicate rules. First write a working solution with loops, then compare the clarity of both approaches.

### Stage 9: Collections shared across multiple threads

Learn this part only after basic knowledge of threads, synchronization, memory visibility, and atomic operations.

Areas to explore include synchronized wrappers, `ConcurrentHashMap`, `BlockingQueue`, `CopyOnWriteArrayList`, and specialized concurrent collections.

You must distinguish:

- A single thread-safe method call.
- An atomic sequence of business operations.
- The iteration semantics supported by a specific structure.
- Visibility of changes across threads.

For instance, "insert if absent" written as two separate calls does not automatically become atomic just because the map supports concurrent access. You must choose an appropriate atomic operation or synchronization mechanism.

`parallelStream()` likewise does not make arbitrary collection mutations inside a lambda thread-safe.

**Sign of mastery:** you can explain why swapping the collection class is not enough to fix every concurrency bug. Synchronization guarantees must be read in each class's documentation; the `Collection` interface does not provide a universal synchronization guarantee across all implementations. See [Collection: synchronization, views, and modifiability contracts](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

## 5. Performance comes after semantics

Once you know the right data model, compare the costs of options that satisfy the same requirements.

| Structure and operation | Common cost model | Caveat to keep in mind |
| --- | --- | --- |
| `ArrayList.get(i)` | `O(1)` | Valid index |
| Append to end of `ArrayList` | Amortized `O(1)` | Growing capacity can copy many elements at once |
| Insert or remove in middle of `ArrayList` | `O(n)` | Shifts subsequent elements |
| `LinkedList.get(i)` | `O(n)` | Must traverse nodes to the position |
| Insert or remove at an iterator position in a linked list | Linking/unlinking the node is `O(1)` | Reaching that position beforehand still has cost |
| Basic hash-table lookup | Expected near `O(1)` with proper hashing | Not an unconditional guarantee for every input |
| Lookup in a balanced tree | `O(log n)` | Comparison cost also matters |
| Insert or remove head in `PriorityQueue` | Typically taught as `O(log n)` | Same conclusion does not apply to finding an arbitrary element |

This table builds intuition; it does not replace per-method documentation. Benchmark performance only after ensuring two solutions produce the same results, uphold the same contract, and run on representative workloads.

For example, a `HashSet` being faster than scanning a list has no value if the problem requires keeping duplicates that the set discards.

## 6. Capstone program: one input, multiple ways to organize

The following program connects the foundational stages. It has no multithreading or external dependencies.

Save the exact content to `CollectionLearningPathDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CollectionLearningPathDemo {
    public static void main(String[] args) {
        List<String> registrations =
                new ArrayList<>(List.of("S2", "S1", "S2"));

        Set<String> uniqueCodes = new LinkedHashSet<>(registrations);

        Map<String, Integer> counts = new TreeMap<>();
        for (String code : registrations) {
            counts.put(code, counts.getOrDefault(code, 0) + 1);
        }

        Set<String> sortedCodes = new TreeSet<>(uniqueCodes);

        Deque<String> waiting = new ArrayDeque<>(uniqueCodes);
        List<String> processed = new ArrayList<>();
        while (!waiting.isEmpty()) {
            processed.add(waiting.removeFirst());
        }

        PriorityQueue<Integer> priorities =
                new PriorityQueue<>(List.of(30, 10, 20));
        List<Integer> priorityOrder = new ArrayList<>();
        while (!priorities.isEmpty()) {
            priorityOrder.add(priorities.remove());
        }

        List<String> snapshot = List.copyOf(registrations);
        registrations.add("S3");

        System.out.println("Unique codes: " + uniqueCodes);
        System.out.println("Counts by code: " + counts);
        System.out.println("Sorted codes: " + sortedCodes);
        System.out.println("FIFO order: " + processed);
        System.out.println("Priority order: " + priorityOrder);
        System.out.println("Source size: " + registrations.size());
        System.out.println("Snapshot size: " + snapshot.size());
    }
}
```

Compile and run:

```shell
javac --release 17 CollectionLearningPathDemo.java
java CollectionLearningPathDemo
```

Expected output:

```text
Unique codes: [S2, S1]
Counts by code: {S1=1, S2=2}
Sorted codes: [S1, S2]
FIFO order: [S2, S1]
Priority order: [10, 20, 30]
Source size: 4
Snapshot size: 3
```

Explanation by requirement rather than line by line:

1. `registrations` initially holds three entries, with `"S2"` appearing twice. `List` preserves this information.
2. `uniqueCodes` keeps only two codes and preserves first-seen order via `LinkedHashSet`.
3. `counts` uses the code as key and the count as value. `TreeMap` gives a stable print order following natural string order.
4. `sortedCodes` represents a sorted set, so `"S1"` comes before `"S2"`.
5. `waiting` is populated in the order of `uniqueCodes`, then drained from the head with `removeFirst()`; this is FIFO usage.
6. `priorities` receives 30, 10, 20 but yields 10, 20, 30. The program removes elements one by one with `remove()`, rather than relying on the heap's iterator order.
7. `snapshot` is taken from the initial three entries. Adding `"S3"` to the source list changes the source size to 4 while the snapshot size remains 3.

The program uses `String` and `Integer` to avoid defining equality and comparability for a domain class in an introductory example. When moving to custom objects, you must revisit `equals`, `hashCode`, and `Comparator`.

## 7. Common mistakes when learning and using collections

### 7.1. Confusing insertion order with sorted order

`List` has positional order but does not automatically sort values. `LinkedHashSet` preserves insertion order, not ascending order. `HashSet` guarantees no order even if one printout happens to look sorted.

State explicitly which kind of order the problem requires before choosing a class.

### 7.2. Using Set and later discovering duplicate data was lost

If a student can register multiple times and each entry is an event that needs to be counted, converting everything immediately into a `Set` loses information.

You can keep a `List` as the source of truth and build a `Set` for a specific need. Choosing a collection for one view does not have to replace the original data source.

### 7.3. Confusing the two remove methods of List<Integer>

Illustration:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
numbers.remove(1);
numbers.remove(Integer.valueOf(30));
```

The first call passes an `int` argument, so it removes the element at index 1, which is 20. The second call passes an `Integer`, so it removes by value 30. The final list is `[10]`.

This is method overloading and boxing applied to collections, not an arbitrary quirk of lists.

### 7.4. Mutating a key after inserting it into a HashMap

If a field used in `equals` or `hashCode` changes after the object is already a key, the hash structure does not automatically relocate the key to match its new value. Lookups may stop working as expected.

Design keys with stable values. A similar issue occurs when mutating state used for comparison of an element inside a sorted set or map.

### 7.5. Treating a view as a copy

Calling `map.keySet()` or `list.subList(...)` does not create an independent copy by default. Removing through a modifiable view can affect the backing structure.

Before every API that returns a collection, ask: **is this a new independent object, a live view backed by the source, or a wrapper restricting operations?**

### 7.6. Treating unmodifiable as deeply immutable

`List.of` forbids adding, removing, or replacing elements in the list. It does not lock mutable objects that the list references.

If you need a result that cannot change from a business perspective, consider the element types, data ownership, and whether other code still holds references to those elements.

### 7.7. Learning Streams too early

A `filter`–`map`–`collect` chain may be shorter than a loop, but it does not explain duplicates, ordering, equality, or mutability on your behalf.

The right sequence is to understand the data and contracts, get the logic right with basic operations, and then choose whether to express it with Streams.

### 7.8. Picking a structure based on a performance rule of thumb

Claims like "Map is always fast," "LinkedList is always better for insertions and deletions," or "concurrent collections solve all threading bugs" are all missing conditions.

State the operations, data, required guarantees, and associated costs. When you cannot justify a choice, go back to the contract and the problem instead of swapping classes at random.

## 8. Sequenced exercises and completion criteria

| Exercise | Core concept | Evidence of understanding |
| --- | --- | --- |
| Keep a list of registrations and edit one entry by position | `List` | Does not accidentally remove all entries with the same code |
| Extract unique codes under three ordering requirements | `Set` | Distinguishes no order guarantee, insertion order, and comparison order |
| Count entries by code and group entries by code | `Map` | Chooses the right value type (count vs. list) |
| Simulate a waiting queue, undo stack, and prioritized tasks | `Deque`, `PriorityQueue` | Clearly explains FIFO, LIFO, and priority |
| Find the closest threshold not exceeding a given value | `NavigableSet` or `NavigableMap` | Handles equal, strictly less, and strictly greater cases properly |
| Return data from a manager class to external callers | View, copy, unmodifiable | Knows which caller operations can affect the source |
| Rewrite summary statistics using Streams | Lambda, Stream, collector | Output and data rules remain unchanged |
| Multiple tasks concurrently updating a counter | Concurrency | Chooses an atomic operation and explains iteration behavior |

For each exercise, test at least these inputs: empty, single element, duplicate elements, missing data, and multiple elements that compare equal under business criteria.

Test `null` only when the problem or API allows it. Do not put `null` into every structure by default and expect uniform behavior.

## 9. Self-assessment questions

1. Why does `Map` belong to the framework yet cannot be passed directly to a `Collection` parameter?
2. Does an ordered `List` mean its values are sorted in ascending order?
3. What requirement makes `LinkedHashSet` a better fit than `HashSet`?
4. Can two objects with different references be treated as duplicates by `HashSet`? What conditions determine this?
5. Why can a comparator that checks only names cause a student to be lost in a `TreeSet`?
6. When does a `put` call on a map replace data instead of adding a new key?
7. Why can't you use the direct print order of a `PriorityQueue` to prove priority order?
8. How do `List.copyOf` and `Collections.unmodifiableList` differ when the source list is modified?
9. Does copying an `ArrayList` of objects create copies of each individual object?
10. Why can modifying a collection during iteration fail even in a single-threaded program?
11. Why must you understand the cost of locating a position before claiming insertions or deletions in a linked list are fast?
12. Does a thread-safe collection class guarantee atomicity for every sequence of business operations?

Learners are ready to dive deeper into each group when they can answer with rules, examples, or a small program; memorizing method names alone is not enough.

## 10. How to use documentation to keep learning

Whenever you encounter a new class, read in this order:

1. Interface contract: what does the structure represent?
2. Class-specific guarantees: ordering, `null` handling, modifiability, synchronization.
3. Method contracts: inputs, return values, exceptions.
4. Costs and usage conditions.
5. A small example to verify what you just read.

Pages to use alongside this lesson:

- [Collections Framework Overview — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/doc-files/coll-overview.html): map of interfaces, implementations, and algorithms.
- [Collection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): common foundation, optional operations, views, and modifiability.
- [List — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Set — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html), [Map — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): contracts for each data-organization model.
- [Queue — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html): head-element policy and failure-reporting method pairs.

For other JDK versions, open the documentation matching the version you use. A single version's diagram should not be treated as an immutable list of all interfaces or APIs in later releases.

The roadmap succeeds when a learner can go from business requirements to a data contract, pick the right structure, write a small verification example, and explain the limits of that choice.
