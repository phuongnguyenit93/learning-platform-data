# Structure Selection Criteria: Duplicates, Null, Access, and Concurrency

Choosing a collection means choosing **data rules and how the program interacts with that data**. Two classes that both have `add` or `get` methods can differ completely in whether they retain duplicate elements, accept `null`, maintain iteration order, and remain safe when accessed by multiple threads concurrently.

For example, the following three requirements all refer to a "list of order IDs," yet they require three different perspectives:

- A log recording each time an order is processed must keep every occurrence, including repeats.
- A set of processed order IDs must recognize IDs that have already been seen without storing duplicates.
- A status lookup table needs to find an order by its ID, so the key–value relationship is what matters most.

This article belongs to the Java Collections Framework overview and uses APIs available in Java 17. The goal is to know how to ask the right questions before choosing `ArrayList`, `HashSet`, `HashMap`, `ArrayDeque`, or a concurrent data structure.

## 1. Start with the Data Contract

Before considering speed, briefly write down your requirements along four axes:

| Decision Axis | Questions to Answer | Consequence of Choosing Wrong |
| --- | --- | --- |
| Duplicates | What makes two elements or two keys count as the same value? Should every occurrence be kept? | Data loss or keeping data that should have been deduplicated |
| `null` | Does `null` have a valid meaning? Do you need to distinguish "absent" from "present with an unknown value"? | Runtime exceptions or misinterpreting state |
| Access | Do you mainly look up by index, by key, check existence, take from the front/back, or query in order? | Repeatedly searching or shifting data |
| Concurrency | Who reads, who writes, and which steps must happen atomically? | Lost updates, reading inconsistent state, or iteration errors |

After those four questions, add the ordering to preserve, mutability, expected size, and memory overhead. These conditions help you pick a specific class within the same family.

`Collection` does not guarantee that every implementation accepts the same element types or uses the same synchronization mechanism. A variable declared as `Collection<String>` is not enough on its own to tell whether `null` can be added or whether its contents can be modified. You need to read the contract of the implementation or the factory method that created the object. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 2. Duplicates: Keep Every Occurrence or Only One Representative?

### 2.1. List, Set, and Map Solve Different Needs

| Data Model to Represent | Common Choice | Meaning of Duplicate Elements |
| --- | --- | --- |
| Positional sequence of elements | `List<E>` | Can hold multiple equal elements |
| Set of unique values | `Set<E>` | Does not add an element considered already present |
| Key-based lookup relationship | `Map<K,V>` | Keys are unique; multiple keys may share the same value |
| Pending work with a retrieval rule | `Queue<E>` or `Deque<E>` | Implementation-dependent; usually allows duplicate elements |

Illustrative example inside a method:

```java
List<String> events = new ArrayList<>(List.of("B", "A", "B"));
Set<String> unique = new LinkedHashSet<>(events);

System.out.println(events); // [B, A, B]
System.out.println(unique); // [B, A]
```

Here, `LinkedHashSet` both deduplicates and preserves insertion order. If you only need membership checks without requiring a specific iteration order, `HashSet` is another option. Do not rely on any incidental order observed when printing a `HashSet`. [Java 17: LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

`Map` does not extend `Collection`: it represents a mapping. When calling `put` with a key that already exists, the existing mapping for that key has its value replaced rather than creating another identical key.

```java
Map<String, Integer> quantities = new HashMap<>();
quantities.put("BOOK", 2);
Integer previous = quantities.put("BOOK", 5);

System.out.println(previous);             // 2
System.out.println(quantities.get("BOOK")); // 5
System.out.println(quantities.size());    // 1
```

If the requirement is "each customer has multiple orders," you can use `Map<CustomerId, List<Order>>`; if you only use `Map<CustomerId, Order>`, writes with the same key will overwrite one another. The structure must accurately express the one-to-many relationship. [Java 17: Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 2.2. Define "Equality" Before Deduplicating

For `HashSet` and the keys of `HashMap`, the design of `equals` and `hashCode` must be consistent:

- If two objects are equal according to `equals`, they must have the same `hashCode`.
- Two objects having the same hash code are not necessarily equal; hash collisions do not mean duplicate data.
- Do not mutate fields involved in `equals`/`hashCode` while the object is being used as a key or an element in a hash-based collection.

For example, a customer object looked up by customer ID whose ID is mutated after being added to a `HashSet` may no longer be found at the bucket where the structure stored it. Using immutable keys or creating a dedicated value key is usually easier to control.

`String` and suitable immutable value types generally help reduce this risk. For custom classes, decide clearly whether "same ID" or "all fields match" defines equality. A `record` automatically generates comparisons based on its components; this fits your requirement only when those exact components define value identity. [Java 17: HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

### 2.3. Ordered Trees Detect Duplicates via Comparison

`TreeSet` and the keys of `TreeMap` use natural ordering or a `Comparator`. Two elements or keys whose comparison result is `0` are treated as occupying the same position in the structure.

Suppose two products have different IDs but the same name `"Pen"`. If the comparator only checks the name, `TreeSet` will keep only one element even though `equals` between the two products returns `false`.

```java
Comparator<Product> byName =
        Comparator.comparing(Product::name);

// If you want to distinguish products with the same name:
Comparator<Product> byNameThenId =
        Comparator.comparing(Product::name)
                  .thenComparing(Product::id);
```

This is an illustrative snippet; the `Product` type is defined in the complete program at the end of the article. Only deduplicate by name if "one name is one unique value" is truly the requirement. If you want the collection to fully obey the `Set`/`Map` contract based on `equals`, the comparison order must be consistent with `equals`. Also, do not mutate the fields used for ordering while the object is in the tree. [Java 17: TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

Another point: `Set.of("A", "A")` throws `IllegalArgumentException`; this factory method does not silently keep one copy the way repeated `add` calls on a `HashSet` do. Do not infer factory method behavior from `add` behavior. [Java 17: Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html)

## 3. Null: A Data Modeling Choice, Not a Minor Detail

### 3.1. Null Policy Depends on the Concrete Class

The following table describes common choices in Java 17, not a universal rule for every class implementing the same interface.

| Structure or Factory | `null` Element / Key | `null` Map Value |
| --- | --- | --- |
| `ArrayList`, `LinkedList` | Allows `null` elements | Not applicable |
| `HashSet`, `LinkedHashSet` | Allows one `null` element | Not applicable |
| `HashMap`, `LinkedHashMap` | Allows one `null` key | Allowed |
| `TreeSet` | Disallowed with natural ordering; a comparator may support it | Not applicable |
| `TreeMap` | Disallowed for `null` keys with natural ordering; a comparator may support it | Allowed |
| `ArrayDeque`, `PriorityQueue` | Disallows `null` elements | Not applicable |
| `ConcurrentHashMap` | Disallows `null` keys | Disallowed |
| `CopyOnWriteArrayList` | Allows `null` elements | Not applicable |
| `List.of`, `Set.of`, `Map.of` | Disallows `null` elements/keys | `Map.of` disallows it |

The respective contracts are documented at [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), and [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

Using a tree does not mean `null` is strictly impossible. The following illustrative example sets an explicit `null` comparison rule:

```java
Set<String> names =
        new TreeSet<>(Comparator.nullsFirst(Comparator.naturalOrder()));
names.add("Lan");
names.add(null);
System.out.println(names); // [null, Lan]
```

However, "can support" does not mean "should allow." If `null` has no business meaning, reject it up front. Switching implementations later is also easier when your data model does not rely on a quirk of the current class.

### 3.2. `get` Returning `null` Is Not Enough to Know Whether a Key Exists

In a `HashMap` that permits `null` values, two different states can produce the same result:

```java
Map<String, String> notes = new HashMap<>();
notes.put("A", null);

System.out.println(notes.get("A"));         // null: key present, value is null
System.out.println(notes.get("B"));         // null: key absent
System.out.println(notes.containsKey("A")); // true
System.out.println(notes.containsKey("B")); // false
```

If you need to distinguish them, use `containsKey` or design a value type that expresses state more clearly. `getOrDefault("A", "unknown")` still returns `null` because key `A` actually has a mapping; the default value is only used when no mapping exists.

With concurrently modified data, calling `containsKey` followed by `get` does not form an atomic snapshot either: the data can change between the two calls. You must address concurrency conditions separately, not just resolve the `null` ambiguity.

### 3.3. Queues Often Use `null` to Signal No Element

`poll()` can return `null` when the queue is empty. If `null` is allowed into the data, that result is hard to distinguish from a real element.

`ArrayDeque` does not accept `null`, making the result of `poll()` easier to interpret. `LinkedList` allows `null`, even when used through `Queue`; that capability is one reason to enforce a stricter data policy yourself.

For `BlockingQueue`, `null` is not accepted. If you need to signal the end of work, use a typed termination message or a dedicated convention; do not use `null` as a sentinel element. [Java 17: BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

### 3.4. Converting to an Unmodifiable Version Can Change Input Constraints

`List.of` and `List.copyOf` create unmodifiable lists and reject `null`. You cannot assume that an `ArrayList` currently containing `null` can always be converted with `List.copyOf`.

Conversely, `Collections.unmodifiableList` creates a view that disallows modification through itself; if the underlying list changes, the view reflects those changes. Nor does it make the element objects themselves immutable.

Distinguish three separate requirements: disallowing mutation through a reference, keeping the data structure immutable, and keeping element state immutable. [Java 17: List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html), [Collection: views and modifiability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

## 4. Access: Optimize for the Operations That Actually Happen

### 4.1. Choose by Primary Access Path

| Primary Need | Starting Choice | What Else to Check |
| --- | --- | --- |
| Index access, appending at the end, and sequential iteration | `ArrayList` | Are there frequent insertions/removals in the middle? |
| Membership check, no ordering needed | `HashSet` | Are `equals`/`hashCode` implemented properly? |
| Deduplication while keeping insertion order | `LinkedHashSet` | Do you need value-based sorting instead of insertion order? |
| Key-based lookup | `HashMap` | Do you need ordering or key-range queries? |
| Ordered key traversal, neighbor/range lookups | `TreeMap` | Does the comparator reflect the true meaning of the key? |
| Ordered set and neighbor lookups | `TreeSet` | Is the uniqueness criterion consistent with comparison? |
| Adding/removing at both ends; standard stack or queue | `ArrayDeque` | Are multiple threads involved or do you need to wait for data? |
| Retrieving the highest-priority element by rule | `PriorityQueue` | Do you truly need to iterate over everything in sorted order? |

An interface that expresses intent makes calling code easier to read:

```java
List<String> labels = new ArrayList<>();
Set<String> processedIds = new HashSet<>();
Map<String, Integer> countsById = new HashMap<>();
Deque<String> pendingJobs = new ArrayDeque<>();
```

This is an illustrative declaration snippet; the corresponding types must be imported. Declaring by interface does not make every implementation interchangeable with respect to `null`, ordering, performance, or concurrency. When you need operations like `floorKey` or `ceilingKey`, `NavigableMap` is what expresses the required capabilities.

### 4.2. Understand Complexity Together with Assumptions

With `n` as the number of elements, the characteristics commonly used for comparison are:

| Structure | Operation | Cost Characteristic |
| --- | --- | --- |
| `ArrayList` | `get(index)`, `set(index, value)` | Constant time |
| `ArrayList` | Append at end | Amortized constant; a resize may require copying |
| `ArrayList` | Insert/remove in the middle, search by value | Linear in the general case |
| `LinkedList` | `get(index)` | Must traverse nodes; linear in the general case |
| `LinkedList` | Add/remove at head or tail | Constant time |
| `HashMap`, `HashSet` | Basic lookup, insertion | Typically constant when hash codes distribute well |
| `TreeMap`, `TreeSet` | Basic lookup, insertion, deletion | Logarithmic in the number of elements |
| `ArrayDeque` | Add/remove at both ends | Most operations have amortized constant cost |
| `PriorityQueue` | Insert or poll priority head | Logarithmic; peeking at the head is constant |

Specific guarantees and bounds are in the documentation for [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html), and [PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

"Amortized constant" describes the average cost over a sequence of operations; it does not promise that every single call takes the same amount of time. Moreover, complexity notation does not capture everything about memory usage, allocation overhead, data locality, or the cost of comparisons.

Do not choose `LinkedList` just because you think "middle insertion is fast": first you have to reach that position. Inserting directly at a `ListIterator`'s current position is different from calling index-based insertion when you still have to traverse to that index.

A loop like `for (int i = 0; i < list.size(); i++) list.get(i)` behaves very differently depending on the class. With a linked list, repeated indexed accesses can make the entire loop quadratic. If you only need to iterate, use a `for-each` loop or an iterator.

### 4.3. Insertion Order, Sorted Order, and Priority Order Are Different

- `ArrayList` preserves the positional order of the list.
- `LinkedHashSet` preserves insertion order.
- `TreeSet` sorts according to natural ordering or a comparator.
- `PriorityQueue` guarantees the head element follows priority order; its iterator does not guarantee traversing the entire queue in sorted order.

Therefore, printing a `PriorityQueue` is not proof that the entire queue is sorted like a list. When you need elements in priority order, call `poll` repeatedly; doing so also removes elements from the queue. If you only want to output an ordered report while keeping the original data, make a copy or sort a separate list.

## 5. Concurrency: Per-Method Safety Is Not Enough for a Workflow

### 5.1. Determine Whether Data Is Truly Shared

A collection used only within a single thread generally does not need a concurrent structure. This is the simplest option when you can keep data ownership within a single task.

If multiple threads only read after the data has been completely built, is no longer mutated, and is safely published through an appropriate synchronization mechanism, a standard structure can be shared. However, `final` on a reference variable does not prevent mutating the collection; "not seeing any writes here" also does not prove that no other party holds a reference and mutates it.

When concurrent writes exist, the choice of mechanism must be based on the **invariants that must hold**. For example, "every increment must be counted" differs from "it is acceptable to read a near-current overview."

### 5.2. Three Common Protection Approaches

| Approach | Suitable When | What You Must Control Yourself |
| --- | --- | --- |
| Keep data thread-local or share an immutable copy | You can avoid sharing mutable data | Safe publication, references to mutable elements |
| Use the same external lock or a synchronized wrapper | You want to guard an entire sequence of operations with one lock | Every caller using the same locking protocol, including during iteration |
| Use classes in `java.util.concurrent` | Multiple threads need direct access with an appropriate contract | Atomicity of each API, iteration semantics, and multi-step invariants |

`Collections.synchronizedList` creates a synchronized wrapper. When using an iterator, stream, or spliterator, you must manually synchronize on the wrapper throughout the entire traversal. Do not keep a reference to the backing list and bypass the wrapper.

```java
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());

synchronized (shared) {
    if (!shared.contains("A")) {
        shared.add("A");
    }
}

synchronized (shared) {
    for (String value : shared) {
        System.out.println(value);
    }
}
```

This is an illustrative snippet inside a method. The same lock covers both the check and the addition. If multiple places write `contains` followed by `add` outside a shared lock, two threads can still both observe "not present" and add duplicates.

With `synchronizedMap`, when iterating over `keySet` or `entrySet`, synchronize on the map wrapper itself, not on the view object. [Java 17: Collections, synchronized wrappers](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)

### 5.3. Choose the Concurrent Class Based on Usage Pattern

| Need | Usually Suitable Class or Family | Key Trade-off |
| --- | --- | --- |
| Key-based lookup/update across multiple threads | `ConcurrentHashMap` | Rejects `null`; does not provide multi-key transactions |
| Concurrent map with ordered keys | `ConcurrentSkipListMap` | Different cost and contract from hash maps |
| List read/iterated very often, modified rarely | `CopyOnWriteArrayList` | Copies array on write; iterator holds a snapshot |
| Concurrent set without ordering | `ConcurrentHashMap.newKeySet()` | Follows the characteristics of a concurrent-map-backed set |
| Work handoff between producers and consumers | `BlockingQueue`, such as `ArrayBlockingQueue` | Must choose capacity and full/empty handling |
| Non-blocking concurrent queue | `ConcurrentLinkedQueue` | Does not automatically bound load like a fixed-capacity queue |

`ConcurrentSkipListMap` fits when you need both concurrency and ordered access; it rejects `null` keys and `null` values. [Java 17: ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)

A bounded-capacity queue helps limit the number of pending tasks. Choose `put` to block, `offer` to attempt immediately, or timed `offer` depending on your processing flow. An unbounded concurrent queue does not automatically protect the application when task production outpaces consumption.

### 5.4. Compound Operations Need the Right Atomic API

The following code is **wrong when multiple threads increment the same key**, even if `counts` is a `ConcurrentHashMap`:

```java
Integer oldValue = counts.get("requests");
counts.put("requests", oldValue == null ? 1 : oldValue + 1);
```

Two threads can both read `10` and both write `11`, losing an increment. Use an atomic per-key update operation:

```java
counts.merge("requests", 1, Integer::sum);
```

Similarly, consider `putIfAbsent`, `compute`, `computeIfAbsent`, or conditional replace methods instead of manually combining read–check–write.

The mapping function should be short, avoid long blocking operations, and must not modify the map itself during computation. Single-key atomicity does not protect multi-key invariants: transferring money between two balances requires its own synchronization or transaction design.

A `ConcurrentHashMap<String, ArrayList<String>>` only protects the map's structure. Two threads calling `add` on the same `ArrayList` retrieved from the map are still not protected by the map itself. Choose immutable values, a concurrent value structure, or an appropriate locking mechanism. [Java 17: ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)

### 5.5. Collection Iteration Has Several Different Contracts

- Fail-fast iterators in many standard collections may throw `ConcurrentModificationException` when they detect invalid structural modification. This is a best-effort bug-detection mechanism, not a synchronization guarantee and not a way to make a program thread-safe.
- `ConcurrentHashMap` iterators are weakly consistent: they may reflect some changes that occur during traversal, and do not promise an atomic snapshot of the entire map.
- `CopyOnWriteArrayList` iterators use the array as it existed when the iterator was created. Subsequent changes do not appear in that iterator. The cost is that modifications must copy the array, and iterators can keep old arrays alive.

Do not lump together every traversal that does not throw `ConcurrentModificationException` as "fail-safe" and assume they all mean the same thing.

The snapshot of `CopyOnWriteArrayList` is also only a snapshot of element references. If an element object has its state mutated, the list does not automatically deep-copy or protect that state. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

## 6. Complete Program: Observing the Criteria

Save the following complete program as `CollectionCriteriaDemo.java`. The program uses `record`, standard collections, and concurrent classes available in Java 17.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

public class CollectionCriteriaDemo {
    record Product(String id, String name) {}

    public static void main(String[] args) throws InterruptedException {
        List<String> events = new ArrayList<>(List.of("B", "A", "B"));
        System.out.println("list = " + events);
        System.out.println("unique by insertion = " + new LinkedHashSet<>(events));
        System.out.println("unique sorted = " + new TreeSet<>(events));

        Product p1 = new Product("P1", "Pen");
        Product p2 = new Product("P2", "Pen");
        Set<Product> byEquals = new HashSet<>(List.of(p1, p2));
        Set<Product> byName = new TreeSet<>(Comparator.comparing(Product::name));
        byName.add(p1);
        byName.add(p2);
        System.out.println("hash size = " + byEquals.size());
        System.out.println("tree by name size = " + byName.size());

        Map<String, String> notes = new HashMap<>();
        notes.put("A", null);
        System.out.println("get(A) = " + notes.get("A"));
        System.out.println("get(B) = " + notes.get("B"));
        System.out.println("contains A/B = "
                + notes.containsKey("A") + "/" + notes.containsKey("B"));

        ArrayDeque<String> queue = new ArrayDeque<>();
        System.out.println("poll empty = " + queue.poll());
        try {
            queue.add(null);
        } catch (NullPointerException expected) {
            System.out.println("ArrayDeque rejects null");
        }

        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        List<Thread> workers = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            Thread worker = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counts.merge("requests", 1, Integer::sum);
                }
            });
            workers.add(worker);
            worker.start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("requests = " + counts.get("requests"));

        CopyOnWriteArrayList<String> listeners =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> beforeChange = listeners.iterator();
        listeners.add("C");
        List<String> snapshot = new ArrayList<>();
        beforeChange.forEachRemaining(snapshot::add);
        System.out.println("iterator snapshot = " + snapshot);
        System.out.println("current list = " + listeners);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectionCriteriaDemo.java
java CollectionCriteriaDemo
```

Expected output:

```text
list = [B, A, B]
unique by insertion = [B, A]
unique sorted = [A, B]
hash size = 2
tree by name size = 1
get(A) = null
get(B) = null
contains A/B = true/false
poll empty = null
ArrayDeque rejects null
requests = 4000
iterator snapshot = [A, B]
current list = [A, B, C]
```

How to read the output:

1. `List` keeps all three occurrences; `LinkedHashSet` keeps only the two values in insertion order, while `TreeSet` sorts them lexicographically.
2. The two `Product` instances have different IDs, so they are distinct according to the record-generated `equals`. The name-only comparator returns `0`, causing the tree set to keep one product.
3. Map `get` returns `null` for both a key mapped to `null` and an absent key; `containsKey` distinguishes the two states.
4. `poll` on an empty queue returns `null`, yet `null` cannot be inserted into `ArrayDeque`.
5. Four threads increment the same key using `merge`. Each thread increments 1,000 times; `join` waits for all of them to finish before reading, so the total is 4,000.
6. The copy-on-write list iterator was created before adding `C`, so it still traverses only `A` and `B`.

The example does not directly print the iteration order of `HashSet` or `ConcurrentHashMap`, so the output does not depend on an iteration order those classes do not promise. Never use a "usually runs fine" example of a racy update to prove thread safety.

## 7. Workflow for Applying This to a Real Problem

Suppose you need to accept job IDs, avoid duplicate processing, and hand them off to worker threads:

1. **Define what duplicate means:** does the same job ID mean one job or a new retry attempt? If a job can validly be re-run, you may need an attempt identifier.
2. **Set a null policy:** reject `null` IDs on intake, since they do not represent valid work.
3. **Choose the access path:** you need to check whether an ID was already seen and retrieve jobs in order, so a single collection may not express both well.
4. **Identify atomicity:** "marking as received" and "enqueuing" are two separate mutations. A concurrent set plus a concurrent queue does not automatically form a transaction between them.
5. **Check system boundaries:** multiple processes or multiple machines require durable coordination; an in-JVM collection does not guarantee system-wide deduplication.
6. **Choose a failure strategy:** if the process stops after marking but before enqueuing, you need a recovery mechanism instead of losing work.

This example shows that concurrency criteria must be evaluated at the workflow level. Choosing the right class is the foundation; preserving business invariants also requires coordinating the steps in between.

Before optimizing, write a small requirements table for each piece of data: are duplicates allowed, is `null` allowed, what order is needed, which operations are frequent, who can mutate it, and what must be atomic. Only then measure on representative sizes and access patterns.

## 8. Common Mistakes to Self-Check

| Mistake | Why It Is Wrong | How to Fix It |
| --- | --- | --- |
| Picking `Set` just to "avoid duplicates" without defining equality | May keep or drop the wrong data | Design `equals`/`hashCode` or a comparator according to requirements |
| Treating a duplicate key in a Map as a new entry | `put` replaces the existing mapping | Use a list/set value if the relationship is one-to-many |
| Assuming every `List` accepts `null` and is modifiable | The interface does not require all implementations to behave identically | Check the concrete class or factory method |
| Using `get(key) == null` to conclude a key is absent | It could be a mapping to `null` | Use a clear data contract or an appropriate existence check |
| Choosing `LinkedList` for "O(1) middle insertion" | You may still pay O(n) to find the position | Account for the cost of locating the position |
| Relying on `HashMap` order or `PriorityQueue` iterator order | Neither provides the ordering guarantee you need | Choose a structure with an ordering contract or create a separate sorted copy |
| Assuming `ConcurrentHashMap` makes every sequence of operations atomic | Read-then-write still has an interleaving window | Use atomic APIs or appropriate coordination mechanisms |
| Assuming a thread-safe collection makes element objects thread-safe | Collections usually only manage references | Design element state and mutation mechanisms separately |
| Catching `ConcurrentModificationException` to retry as a concurrency mechanism | Fail-fast is only a bug-detection aid | Fix data ownership or synchronization protocols |
| Using copy-on-write for frequent writes on a large list | Copying incurs time and memory overhead | Use it only when a read-heavy, write-rarely pattern fits |

## 9. Self-Practice

1. You need to deduplicate customer IDs while preserving the order users entered them. Why is `LinkedHashSet` a better fit than `TreeSet`?  
   **Hint:** the requirement is to preserve insertion order, not to sort by value.

2. Two products with different IDs but the same selling price are added to a `TreeSet` whose comparator only checks price. How many elements does the set keep?  
   **Hint:** a comparison result of `0` makes them equivalent to the tree set. To keep both, add an appropriate tie-breaking criterion.

3. A `HashMap` contains key `A` mapped to `null`. What does `getOrDefault("A", "unknown")` return?  
   **Answer:** `null`, because a mapping exists for key `A`.

4. Replace `merge` in the example with `get` followed by `put`. Should you expect to always see 4,000?  
   **Answer:** no. Two threads can compute from the same stale value and lose updates.

5. You need to pass work between multiple threads, cap pending jobs at 100, and let consumers wait when empty. Which structure should you evaluate first?  
   **Hint:** a bounded `BlockingQueue`, such as `ArrayBlockingQueue`; then decide behavior on full, interruption handling, and shutdown.

When answering, always explain both the data rules and the access pattern. Class names are only meaningful when tied to those conditions.