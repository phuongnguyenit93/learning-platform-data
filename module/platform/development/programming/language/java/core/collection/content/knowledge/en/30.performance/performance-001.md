# Comparing the Complexity of Access, Search, Insertion, Removal, and Iteration

## 1. Start from the Specific Operation

A data structure does not have a single "overall complexity." You must ask: which method is being called, what is already known about the element to be processed, and how many times is that operation repeated?

For example, with a list:

- Knowing the index `i`: retrieve the element using `get(i)`.
- Knowing the value `x`: search using `contains(x)` or `indexOf(x)`.
- Knowing the current position via an iterator: you can remove the element just read.
- Knowing only "remove the element with value x": it must first be found.

The last two requirements can produce the same result at different costs. This article compares common structures in Java 17: `ArrayList`, `LinkedList`, `ArrayDeque`, `PriorityQueue`, and sets and maps based on hash tables or trees. Concurrent structures and bulk operations require their own models.

## 2. Reading Notation and Assumptions

Let:

- `n`: the number of current elements; for a `Map`, the number of key–value pairs.
- `c`: the hash table capacity, i.e., the number of buckets.
- `i`: a valid index in a list.
- A single reference read/write, comparison, `equals`, and `hashCode` are tentatively treated as O(1). Section 7 explains when this assumption does not hold.

| Notation | Growth Meaning as Data Scales |
| --- | --- |
| O(1) | Number of steps does not grow with n |
| O(log n) | Each step eliminates a significant portion of the search domain |
| O(n) | May have to process a number of elements proportional to n |
| O(n log n) | Commonly seen when sorting or polling n elements one by one from a heap |
| O(n²) | Commonly appears when repeating a linear operation n times |

Big O describes growth rate and ignores constant factors. O(1) can still involve multiple steps; O(n) can be very fast when n is small. Writing log n in tables is standard shorthand for sufficiently large n; do not take log 0 to interpret an empty collection.

Distinguish three ways of evaluating cost:

1. **Worst case:** the cost bound of a single operation on unfavorable input.
2. **Average/expected:** requires assumptions about the data, such as well-distributed hash codes.
3. **Amortized:** divides the total cost of a sequence of operations by the number of operations; it is not a probabilistic average over inputs.

For instance, appending to the end of an `ArrayList` has O(1) amortized cost. A single append when the array is full may still require O(n) to copy elements into a larger array. Conversely, the expected O(1) of a hash table lookup depends on the quality of key distribution. These two statements rely on different conditions.

## 3. Lists: Index, Value, and Iterator Position

Cells below not marked "amortized" represent worst-case bounds for a single operation under the assumptions in Section 2.

| Operation | ArrayList | LinkedList |
| --- | --- | --- |
| `get(i)`, `set(i, x)` | O(1) | O(n); traverses from whichever end is closer |
| `contains(x)`, `indexOf(x)` | O(n) | O(n) |
| Append to end with `add(x)` | O(1) amortized; single array resize O(n) | O(1) |
| Insert at head with `add(0, x)` | O(n) | O(1) |
| Insert at internal position with `add(i, x)` | O(n) | O(n), including the step to locate the position |
| Remove from end with `remove(size() - 1)` | O(1) | O(1) |
| Remove from head with `remove(0)` | O(n) | O(1) |
| Remove at internal position with `remove(i)` | O(n) | O(n), including the step to locate the position |
| Remove by value with `remove(Object)` | O(n) | O(n) |
| Iterate through all n elements via iterator | O(n) | O(n) |

### 3.1. Why Is ArrayList Fast for Access but Slow for Middle Insertion?

`ArrayList` stores elements in an array of references. Knowing the index immediately identifies the array slot to read. Conversely, inserting at position `i` requires shifting subsequent elements to make room; removing at `i` requires filling the gap.

Ignoring capacity expansion, the number of elements to shift is approximately:

- Inserting at `i`: `n - i`.
- Removing at `i`: `n - i - 1`.

Therefore, removing the last element is clearly different from removing the first element even though both call `remove(int)`. `set(i, x)` only replaces a single reference and is not an insertion operation. The specific capacity growth policy is not a condition that application code should rely upon. [Java 17 ArrayList Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 3.2. What Condition Is Missing from "LinkedList Insertion/Removal Is O(1)"?

`LinkedList` is a doubly linked list. Once already positioned at the node to modify, linking or unlinking nodes takes only O(1). However, `add(i, x)` or `remove(i)` must first traverse to that node.

For `get(i)`, the number of traversal steps is approximately `min(i, n - 1 - i)`; adding constant processing overhead yields O(1 + min(i, n - 1 - i)). Accessing near the head or tail is cheap, while accessing the middle can be O(n).

A `ListIterator` of `LinkedList` that is already at the target position can validly execute `add(x)` or `remove()` in O(1). If a new `listIterator(i)` is created before each modification, the cost of locating the position reappears. The iterator's `remove()` may only be called in a valid state, such as after `next()`, and cannot be called twice consecutively without moving again. [Java 17 LinkedList Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

### 3.3. Same Loop, Different Total Cost

The following snippet is an illustrative method that should be placed inside a Java class:

~~~java
static long sumByIndex(java.util.List<Integer> values) {
    long sum = 0;
    for (int i = 0; i < values.size(); i++) {
        sum += values.get(i);
    }
    return sum;
}
~~~

With `ArrayList`, n calls to O(1) `get(i)` give a total of O(n). With `LinkedList`, the total number of steps traversing across nodes grows with n², even though each access chooses the closer end.

Sequential iteration using an iterator avoids re-locating the position from the head or tail:

~~~java
static long sumSequentially(java.util.List<Integer> values) {
    long sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}
~~~

For both implementations above, the second method is O(n), assuming each addition and element read has constant cost. Changing the variable type from `LinkedList` to the `List` interface does not change the underlying structure or the cost of `get(i)`.

## 4. Double-Ended Queues and Priority Queues

These two structures solve two different requirements:

- `ArrayDeque`: retrieves/inserts at the head or tail by sequence position.
- `PriorityQueue`: retrieves the highest-priority element according to a comparison rule; with ascending natural ordering, that is the smallest element.

| Operation | ArrayDeque | PriorityQueue |
| --- | --- | --- |
| Read head with `peek()` | O(1) | O(1) |
| Read tail with `peekLast()` | O(1) | No equivalent operation |
| Insert at head/tail | O(1) amortized | Does not support double-ended semantics |
| Insert with `offer(x)` | O(1) amortized, appends to tail | O(log n) for heap adjustment; see array resize note |
| Retrieve and remove head with `poll()` | O(1) | O(log n) |
| Search with `contains(x)` | O(n) | O(n) |
| Remove value with `remove(x)` | O(n) | O(n) |
| Full iteration via iterator | O(n), in sequence order | O(n), priority order not guaranteed |
| Arbitrary index access | No `get(i)` | No `get(i)` |

`ArrayDeque` uses a circular array: advancing the head or tail typically only updates an index. When an insertion fills the array, a capacity expansion can take O(n). Its `iterator.remove()` can also take O(n); do not apply the `LinkedList` iterator removal conclusion to every collection. [Java 17 ArrayDeque Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

`PriorityQueue` uses a heap. The path from leaf to root or vice versa has length O(log n), but a heap does not guarantee that the entire array is sorted. Consequently, searching for an arbitrary value still requires scanning; a fast `peek()` does not imply a fast `contains(x)`. Calling `poll()` until all n elements are exhausted has a total cost of O(n log n) and empties the queue. [Java 17 PriorityQueue Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html)

**Note on a single offer:** the API note states O(log n) for heap insertion. If copying the backing array during capacity expansion is included, a single `offer` in OpenJDK can take O(n); O(log n) is the amortized bound when spreading array resize costs across a sequence of insertions. This is an implementation-level analysis, not a real-time guarantee for every individual call. [PriorityQueue Source Code in OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java)

## 5. Set: Membership Testing and Iteration Order

`Set` does not provide positional access like `get(i)`. "Accessing an element" must be translated into an explicit requirement: membership testing, retrieving the first element in order, or finding an element near a boundary.

| Implementation | `contains(x)` | `add(x)` | `remove(x)` | Full Iteration | Order |
| --- | --- | --- | --- | --- | --- |
| `HashSet` | O(1) expected | O(1) expected, amortized | O(1) expected | O(n + c) | Not guaranteed |
| `LinkedHashSet` | O(1) expected | O(1) expected, amortized | O(1) expected | O(n) | Insertion order |
| `TreeSet` | O(log n) | O(log n) | O(log n) | O(n) | By comparator/natural ordering |

Hash tables require well-distributed hash codes; insertion may trigger capacity expansion. For trees, the O(log n) bounds are worst-case bounds for basic operations under the O(1) comparison assumption.

`HashSet` must traverse across the buckets in the backing table during iteration. If a very large capacity was allocated but only a few elements are stored, c cannot be ignored. When c is on the same order as n, O(n + c) simplifies to O(n). [Java 17 HashSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

`LinkedHashSet` maintains links across existing elements, so iteration cost does not depend on table capacity. In return, it requires extra memory and work to maintain the links. [Java 17 LinkedHashSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

`TreeSet` maintains order using a tree. It is suitable when neighbor queries like `floor`, `ceiling`, or range-based processing are needed. The comparator determines whether two elements are considered to occupy the same position in the tree; designing a comparator inconsistent with `equals` can violate user expectations regarding uniqueness. [Java 17 TreeSet Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

## 6. Map: Key Lookup vs. Value Search

`map.get(k)` is a key lookup, not retrieving the element at index k. Even when the key is an `Integer`, `get(5)` still means "the key equal to 5."

| Operation | HashMap | LinkedHashMap | TreeMap |
| --- | --- | --- | --- |
| `get(k)`, `containsKey(k)` | O(1) expected | O(1) expected | O(log n) |
| `put(k, v)` | O(1) expected, amortized when adding a new key | O(1) expected, amortized when adding a new key | O(log n) |
| `remove(k)` | O(1) expected | O(1) expected | O(log n) |
| `containsValue(v)` | O(n + c) worst case | O(n) | O(n) |
| Full `entrySet()` iteration | O(n + c) | O(n) | O(n) |
| Iteration order | Not guaranteed | Typically insertion order; has access-order mode | Key order |

`HashMap` indexes by key, so looking up a value does not benefit from the same path. To perform reverse queries by value frequently, you must consider an auxiliary index and the cost of keeping that index synchronized. In typical usage where c = O(n), the bound for `containsValue` or iterating over a hash table is written concisely as O(n). [Java 17 HashMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [containsValue Implementation in OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java)

`LinkedHashMap` links existing entries for O(n) iteration. In access-order mode, a successful `get(k)` may update the entry's position in the sequence; there is still no full sorting of the map on each read. [Java 17 LinkedHashMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

`TreeMap` organizes its tree by key. It guarantees O(log n) for lookup, insertion, and removal by key, but does not create a secondary index by value. Knowing a key near a certain value also does not mean knowing the rank index of the key in O(1). [Java 17 TreeMap Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html)

## 7. Hidden Costs Behind an O(1) Cell

### 7.1. Hash Collisions and Capacity Expansion

Multiple keys sharing the same hash code can make operations slower than O(1). Java has mechanisms to mitigate collision impact in certain situations, but one should not deduce that "every HashMap operation is always O(log n) in the worst case" merely from the existence of tree bins. The API specifies well-distributed hashes as the condition for constant-time basic operations.

When resizing the table, a new table must be allocated and entries redistributed; the cost also depends on table capacity. In a model where capacity is proportional to the number of entries, a single table resize is linear in n. Pre-allocating a reasonable capacity can reduce the number of resizes, whereas over-allocating wastes memory and makes `HashMap`/`HashSet` iteration more expensive.

Keys in a hash table must keep the information used for `hashCode` and `equals` stable while stored. Mutating them can prevent lookups from finding an already inserted entry; that is a correctness bug before it is a speed issue.

### 7.2. HashCode, Equals, and Comparator Are Not Free

If a key is a large structure, a single hash computation or equality check may have to process many fields or characters. If each comparison costs O(L), a tree search path can cost O(L log n). Sequentially searching for a value in a list can cost O(nL).

The cost of a hash table lookup can be thought of as: cost of computing the hash code + cost of locating the bucket + cost of comparing candidates. The O(1) notation with respect to n does not say that the size of the key itself has no impact.

### 7.3. Iteration Includes the Work Inside the Loop

O(n) iteration only counts the cost of stepping through the collection. If each element performs an O(n) query, the entire code block can become O(n²).

For example, given two lists of sizes n and m, calling `otherList.contains(x)` for each x in the first list has a bound of O(nm). If the second list is converted into a hash set first, the total expected cost can be O(m + n), along with additional memory and the requirement of a valid equality/hash contract.

Conversion also has a cost. For just a single small query, building a new set may not yield any benefit.

### 7.4. Pre-Sorting Only Pays Off When Reused

`contains` on a sorted `ArrayList` still searches sequentially; it does not automatically switch to binary search. To perform a binary search, you must use the appropriate algorithm and ensure the data is sorted according to the exact same rule.

`Collections.binarySearch` on a random-access list like `ArrayList` is O(log n). For a large linked list, Java uses an iterator-based approach, which takes O(n) link-traversal steps despite performing only O(log n) comparisons. If you have to sort from scratch for a single search, the preparation cost must still be included in the total. [Java 17 Collections.binarySearch Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T))

## 8. Runnable Illustrative Program

The following example clarifies three types of operations: index-based access, modification at an iterator position, and priority-based retrieval. It illustrates behavior and outcomes; do not use the runtime of a few elements to prove Big O.

Save as `CollectionCostDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Map;
import java.util.PriorityQueue;

public class CollectionCostDemo {
    public static void main(String[] args) {
        List<Integer> numbers =
                new ArrayList<>(List.of(10, 20, 30, 40));

        System.out.println("get(2) = " + numbers.get(2));
        System.out.println("contains(30) = " + numbers.contains(30));

        // Selects remove(Object), not remove(int index).
        numbers.remove(Integer.valueOf(20));
        System.out.println("after remove value = " + numbers);

        LinkedList<String> tasks =
                new LinkedList<>(List.of("A", "B", "C", "D"));

        // Creating an iterator at index 2 also incurs position-lookup cost.
        ListIterator<String> cursor = tasks.listIterator(2);
        String removed = cursor.next();
        cursor.remove();
        cursor.add("X");

        System.out.println("removed by iterator = " + removed);
        System.out.println("tasks = " + tasks);

        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("Lan", 9);
        scores.put("Minh", 7);

        System.out.println("get key = " + scores.get("Minh"));
        System.out.println("contains value = " + scores.containsValue(7));

        PriorityQueue<Integer> queue =
                new PriorityQueue<>(List.of(7, 2, 5, 1));
        List<Integer> ordered = new ArrayList<>();

        while (!queue.isEmpty()) {
            ordered.add(queue.poll());
        }

        System.out.println("poll order = " + ordered);
        System.out.println("remaining size = " + queue.size());
    }
}
~~~

Compile and run on JDK 17 or later:

~~~shell
javac --release 17 CollectionCostDemo.java
java CollectionCostDemo
~~~

Exact stdout:

~~~text
get(2) = 30
contains(30) = true
after remove value = [10, 30, 40]
removed by iterator = C
tasks = [A, B, X, D]
get key = 7
contains value = true
poll order = [1, 2, 5, 7]
remaining size = 0
~~~

Comparing against the model:

- `get(2)` on `ArrayList` goes directly to the position; `contains(30)` must search by value.
- Removing the number 20 requires finding it and shifting the trailing portion. Writing `remove(20)` would select the index-taking overload, which could throw `IndexOutOfBoundsException`.
- Creating `listIterator(2)` must locate the position. Once the iterator is standing there, removing C and inserting X does not require searching from the beginning again.
- `scores.get("Minh")` looks up by key; `containsValue(7)` may need to scan entries.
- The retrieval order from `poll()` is guaranteed by priority. Do not replace this loop with printing `queue` and assuming the result is already in ascending order.

## 9. Choosing a Structure by Dominant Workload

| Primary Workload | Option to Consider | Rationale |
| --- | --- | --- |
| Read by index, append to end, frequent iteration | `ArrayList` | Positional access O(1), append to end amortized O(1) |
| FIFO or stack processing, double-ended operations | `ArrayDeque` | Insert at both ends amortized O(1), remove from both ends O(1) |
| Iterate and repeatedly modify at an existing cursor position | `LinkedList` with `ListIterator` | Relinking at position O(1); traversal to position still counts |
| Frequent duplicate/membership checks | `HashSet` | Expected O(1) for membership testing |
| Look up data by key | `HashMap` | Expected O(1) for key lookup |
| Preserve insertion order during iteration | `LinkedHashSet` or `LinkedHashMap` | O(n) iteration with deterministic order |
| Require ordered data and neighbor queries | `TreeSet` or `TreeMap` | Basic operations O(log n) |
| Repeatedly select the highest-priority element | `PriorityQueue` | Read head O(1), remove head O(log n) |

Do not use this table as an absolute speed ranking. You must consider data size, read/write ratio, memory, ordering, uniqueness, and concurrency requirements. Two structures with the same O(n) iteration bound can still differ in object count, CPU cache locality, and garbage collection pressure.

## 10. Self-Check on Analysis

1. **Removing from the head of an ArrayList n times until empty:** O(n²), because the number of shifted elements is approximately n - 1, n - 2, …, 0 in turn. With `ArrayDeque.pollFirst()`, the total is O(n).
2. **Iterating over a LinkedList using get(i):** O(n²). Iterating with an iterator is O(n).
3. **Finding a value in a TreeMap using containsValue:** O(n), even though `get(key)` is O(log n).
4. **Iterating over a HashSet after allocating a very large capacity:** must account for O(n + c); a small element count does not guarantee cheap iteration.
5. **Retrieving all PriorityQueue elements in order using poll:** O(n log n), not O(n) like iterator traversal.
6. **Appending to the end of an ArrayList one million times:** total O(n) under the amortized model; does not guarantee every individual call has identical latency.

When reading a piece of code, explicitly note the method, concrete implementation, evaluation condition, and repetition count. Those four pieces of information turn a vague remark like "this collection is fast" into a verifiable argument.
