# Comparing LinkedList with ArrayList and ArrayDeque

## 1. Choose by the operations needed first, then choose the data structure

All three classes can hold a sequence of elements, but they do not provide the same contract:

- **ArrayList** is a List backed by a dynamic array, well-suited for indexed access and many common list processing patterns.
- **LinkedList** is a doubly-linked list that implements both List and Deque; it supports both positional operations and operations at both ends.
- **ArrayDeque** is a Deque backed by a resizable array, organized for adding and removing at both ends; it is not an indexed List.

Therefore, the first question is not "which class is always fastest", but rather:

1. Do you need indexing, access at both ends, or are you holding an iterator at the modification position?
2. What is the frequency of reading, adding, removing, and searching?
3. Are null elements allowed?
4. Under what contract do you need to compare contents?
5. How do the data scale and lifecycle create memory pressure?

Complexity helps rule out unsuitable options, while actual execution time also depends on constant factors, allocations, memory layout, and access patterns. Do not use a broad label like "frequent insertions/deletions" in place of describing the position and how the element to be modified is found.

The examples in this article use APIs available in Java 17. In Java 21, List gains some first/last operations through SequencedCollection; ArrayList still does not become a Deque, and ArrayDeque still does not have an indexed List API. Method names may expand across versions, while the underlying storage structure and operational analysis still need to be examined separately. [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), [List Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html).

## 2. Compare contracts before comparing speed

| Property | ArrayList | LinkedList | ArrayDeque |
|---|---|---|---|
| Implements List | Yes | Yes | No |
| Implements Deque and Queue | No | Yes | Yes |
| Indexed List access/insertion | Yes | Yes | Not provided |
| Double-ended Deque operations | Not part of the class's Deque contract | Yes | Yes |
| Bidirectional ListIterator with positional add/set | Yes | Yes | No ListIterator |
| Standard iterator traversal | In list order | From first to last | From head to tail |
| Allows duplicate elements | Yes | Yes | Yes |
| Allows null elements | Yes | Yes | No |
| Has RandomAccess marker | Yes | No | No |
| Automatically synchronized for concurrent modification | No | No | No |

RandomAccess is a marker for a List that supports fast random access. The fact that ArrayDeque lacks this marker does not mean it behaves like a LinkedList; it is not a List in the first place.

None of the three automatically sort or deduplicate elements. The observable order comes from the operations performed: appending to the end, prepending to the front, inserting in the middle, or modifying the sequence.

Illustrative variable types inside a method:

```java
List<String> names = new ArrayList<>();
List<String> editableSequence = new LinkedList<>();

Deque<String> pending = new ArrayDeque<>();
Deque<String> bothEnds = new LinkedList<>();
```

The corresponding imports come from `java.util`. Choose a List variable type when you need the list contract; choose Deque when you need operations at both ends. The fact that two classes implement the same interface allows sharing part of the code, but it does not guarantee identical costs or secondary characteristics.

## 3. Underlying structures explain the differences

### 3.1. ArrayList: an array of references and the number of elements in use

ArrayList uses a backing array to hold element references. The element at index i has a corresponding slot in the array; reading or replacing that element does not require traversing nodes from the beginning.

When spare capacity remains, appending to the end only requires using the next empty slot at the end. When capacity runs out, the list allocates a larger array and copies the references over.

Inserting or removing at the beginning or in the middle typically requires shifting subsequent references to keep the sequence contiguous. That is the primary cost of those operations, even when capacity is already sufficient.

### 3.2. LinkedList: individual nodes with previous/next links

Each node holds an element along with links to the previous and next nodes. The structure maintains references to both ends to operate directly at the head and tail.

To reach an index in the middle, it must follow links starting from whichever end is closer. Once it already has the target node or a ListIterator positioned at the modification point, local linking or unlinking does not require shifting a range of references like ArrayList.

However, an application must not ignore the cost of navigating to that position. `remove(index)` is not the same as "already holding a ListIterator right at the node to remove".

### 3.3. ArrayDeque: a circular array for both ends

In the OpenJDK implementation, ArrayDeque uses an array with head/tail indices managed in a circular manner. The logical head of the deque does not necessarily reside at index 0 of the array.

When removing from the head, the structure can advance the head position instead of shifting all remaining elements back to index 0. When adding at the head or tail, it uses the appropriate circular slot; if more space is needed, it can grow the array.

Therefore, do not assume that "using an array means removing from the front must shift elements like ArrayList". How data is organized inside the array is different.

Conversely, having a backing array does not automatically expose a `get(index)` API. ArrayDeque is designed and published as a Deque; callers must not treat it as an ArrayList just because both use arrays. [OpenJDK 17 ArrayDeque source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayDeque.java).

## 4. Cost tables must be tied to specific operations

The table below considers typical structural costs for a structure with n elements. "Amortized" refers to the aggregate cost over a sequence of operations; an individual array resize may still need to copy many elements.

| Operation | ArrayList | LinkedList | ArrayDeque |
|---|---|---|---|
| Read/replace at index i | `O(1)` | `O(n)` worst case | No indexed API |
| Add at the end | `O(1)` amortized | `O(1)` | `O(1)` amortized |
| Remove from the end | `O(1)` via last index | `O(1)` | `O(1)` |
| Add at the front | `O(n)` due to shifting elements | `O(1)` | `O(1)` amortized |
| Remove from the front | `O(n)` due to shifting elements | `O(1)` | `O(1)` |
| Insert/remove at a middle index | `O(n)` worst case | `O(n)` including node lookup | No indexed API |
| Contains or search/remove by value | `O(n)` worst case | `O(n)` worst case | `O(n)` worst case |
| Full traversal via iterator | `O(n)` | `O(n)` | `O(n)` |
| Add via ListIterator already at a middle position | `O(n)` due to shifting | `O(1)` node linking | No ListIterator |
| Valid remove via iterator already at a middle position | `O(n)` worst case | `O(1)` node unlinking | `O(n)` worst case |

Reading the first/last elements on a non-empty structure is also fast, though the API and behavior when empty may differ. For example, in Java 17: `arrayList.get(0)` uses an index and throws an index exception if empty, whereas `deque.peekFirst()` returns null when empty.

For ArrayDeque, important exceptions to the amortized constant-time operations are searching/removing by value and `iterator.remove()`, which can be linear. Do not apply the cost of `pollFirst` to every method with `remove` in its name. [ArrayList performance costs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [ArrayDeque operation costs and exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

### 4.1. "LinkedList has O(1) insertion/deletion" comes with conditions

If you need to remove at index 50,000, LinkedList still has to locate that node. Once found, fast unlinking does not erase the cost already spent finding it.

If you are traversing with a ListIterator and decide to insert or remove right at that current position, the iterator already holds the position around the node. This is the scenario that genuinely demonstrates the local modification advantage of a linked list.

Recreating `listIterator(index)` for each modification in the middle may still end up traversing repeatedly. Analyze the entire workflow, not just an isolated `iterator.remove()` line.

### 4.2. "All are O(n)" does not mean identical execution time

Linear traversal of all three has O(n) notation, but the CPU and memory access paths differ:

- An array stores reference slots in a more contiguous, concentrated structure.
- A linked list must dereference links to reach the next node.
- LinkedList involves additional node objects and allocation activity when adding elements.
- An array has spare capacity and occasional resizes that require copying.

These factors affect constant factors and memory locality. It is neither necessary nor advisable to assign a fixed speedup ratio across all JVMs and workloads.

## 5. Choosing by common usage patterns

### 5.1. Lists frequently read by index

If you need `get(i)`, `set(i, value)`, retaining results for repeated indexed access, or primarily appending to the end and then reading, ArrayList is usually the appropriate starting point.

An index-based loop on a LinkedList can cause problems:

```java
for (int i = 0; i < values.size(); i++) {
    process(values.get(i));
}
```

This is an illustrative snippet, assuming `values` and `process` are already defined. If `values` is a LinkedList, each `get` may traverse many nodes again, turning the total cost into O(n²). If only sequential traversal is needed, a for-each loop or an iterator avoids re-seeking each index.

That does not mean you must immediately replace the data structure in every case; sometimes fixing the traversal method resolves the primary bottleneck.

### 5.2. FIFO queues or LIFO stacks

If you only need to add/remove at the ends and do not need null elements, ArrayDeque is usually the appropriate initial choice:

```java
Deque<String> queue = new ArrayDeque<>();
queue.offerLast("A");
queue.offerLast("B");
String first = queue.pollFirst(); // A

Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");
String lastPushed = stack.pop(); // B
```

This is an illustrative snippet inside a method, requiring the corresponding type imports. LinkedList also fulfills these Deque contracts properly, but it has node allocation overhead and a different memory profile.

The ArrayDeque documentation notes that it is likely to be faster than LinkedList when used as a queue. That is practical guidance from the API documentation, not a guarantee that it wins every benchmark. If performance dictates the choice, measure the actual queue/stack access pattern of your program. [ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Avoid calling `ArrayList.remove(0)` repeatedly to dequeue from the front of a large queue; shifting elements after every removal can accumulate significant cost.

### 5.3. Modifying near the position held by an iterator

If an algorithm traverses sequentially and repeatedly inserts or removes right at the current position, LinkedList with a ListIterator can be suitable:

```java
ListIterator<String> iterator = values.listIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("obsolete".equals(value)) {
        iterator.remove();
    }
}
```

This is an illustrative snippet, where `values` is assumed to be a LinkedList. It does not re-seek the node by index for each removal.

If the problem is simply bulk filtering by a predicate, consider batch-processing APIs and the actual algorithm as well. Do not infer from the cost of a single `ArrayList.iterator().remove()` call that every way of filtering an ArrayList must suffer repeated element shifting.

### 5.4. Needing both List and Deque on the same structure

LinkedList can serve when a piece of code genuinely needs to combine positional operations and double-ended operations on the same sequence of data.

Illustrative snippet:

```java
LinkedList<String> storage = new LinkedList<>();
List<String> indexed = storage;
Deque<String> ended = storage;
```

The two variables do not create two copies. Operating through one variable mutates the data observed by the other.

This is a useful API capability to know, but it does not automatically prove LinkedList is the best choice if indexed access dominates execution time. You need to characterize the frequency of each group of operations.

## 6. Complete program: the same contract yields corresponding results

Save as `CollectionWorkloadDemo.java`. The program uses APIs available in Java 17:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class CollectionWorkloadDemo {
    private static void editList(String name, List<String> values) {
        values.addAll(List.of("A", "B", "C"));
        System.out.println(name + " get(1): " + values.get(1));

        ListIterator<String> iterator = values.listIterator(1);
        iterator.add("X");
        String selected = iterator.next();
        iterator.remove();
        System.out.println(name + " selected: " + selected);
        System.out.println(name + " edited: " + values);
    }

    private static void useDeque(String name, Deque<String> values) {
        values.offerLast("A");
        values.offerLast("B");
        values.offerFirst("URGENT");
        System.out.println(name + " first: " + values.pollFirst());

        values.push("TOP");
        System.out.println(name + " stack: " + values.pop());
        System.out.println(name + " last: " + values.pollLast());
        System.out.println(name + " remaining: " + values);
    }

    public static void main(String[] args) {
        editList("ArrayList", new ArrayList<>());
        editList("LinkedList", new LinkedList<>());

        useDeque("ArrayDeque", new ArrayDeque<>());
        useDeque("LinkedList deque", new LinkedList<>());
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectionWorkloadDemo.java
java CollectionWorkloadDemo
```

Standard output:

```text
ArrayList get(1): B
ArrayList selected: B
ArrayList edited: [A, X, C]
LinkedList get(1): B
LinkedList selected: B
LinkedList edited: [A, X, C]
ArrayDeque first: URGENT
ArrayDeque stack: TOP
ArrayDeque last: B
ArrayDeque remaining: [A]
LinkedList deque first: URGENT
LinkedList deque stack: TOP
LinkedList deque last: B
LinkedList deque remaining: [A]
```

Both List implementations return B at index 1. After inserting X at the cursor, calling `next` to select B, and calling `remove`, both retain `[A, X, C]`.

Both Deque implementations properly handle the same head/tail conventions:

- Adding URGENT at the front means `pollFirst` retrieves URGENT.
- Pushing TOP and then popping retrieves TOP.
- `pollLast` retrieves B from the back, leaving A.

This example demonstrates behavior through interfaces, not a benchmark. Identical printed output does not mean identical internal costs; printing also adds traversal and I/O overhead.

The program also shows that ArrayDeque cannot be passed to `editList` (which expects a List), while ArrayList cannot be passed to `useDeque` (which expects a Deque). That is a contract difference, not an optimization choice that can be bypassed with arbitrary casting.

## 7. Null is a difference to check before switching classes

ArrayList and LinkedList allow null elements. ArrayDeque rejects null, even via `offer`; `offer` does not mean every invalid argument is converted into a `false` return value.

If you switch a LinkedList containing null elements to `new ArrayDeque<>(source)`, constructing the result can fail with a `NullPointerException`. You must determine the meaning of null in your data and establish a conversion policy rather than silently dropping elements just to make the constructor succeed.

When using LinkedList through Deque, null can also cause ambiguity:

```java
Deque<String> values = new LinkedList<>();
values.addLast(null);
values.addLast("A");

String first = values.pollFirst(); // null, but an element was removed.
// values still contains [A].
```

This is an illustrative snippet. A null result from `poll` could either be a null element or an indicator that the deque is empty. Therefore, even when a data structure permits null, a queue processing model that stops when `poll` returns null should still enforce a policy against using null as data.

ArrayDeque prohibits null and therefore avoids that ambiguity. Be sure to distinguish element constraints from empty-deque behavior: `poll`/`peek` return null, whereas `removeFirst`/`getFirst` throw `NoSuchElementException` on both Deque implementations.

## 8. List equals differs from ArrayDeque equals

ArrayList and LinkedList follow the List content-equality contract: the same number of elements and corresponding elements equal in order.

Therefore:

```java
List<String> a = new ArrayList<>(List.of("A", "B"));
List<String> b = new LinkedList<>(List.of("A", "B"));

boolean equal = a.equals(b); // true
```

This illustrative snippet does not mean the two lists are the same object; `a == b` is still false.

ArrayDeque inherits object identity comparison from Object and does not provide element-sequence equality like List. Two separate ArrayDeque instances both containing `[A, B]` may print identically, yet `equals` returns false.

If the goal is to compare two sequences of elements in traversal order, you can convert them to a List representation for comparison within a controlled scope:

```java
boolean sameSequence =
        new ArrayList<>(leftDeque).equals(new ArrayList<>(rightDeque));
```

This is an illustrative expression assuming two previously declared deques. It creates new container instances to leverage the List contract; it is not a zero-cost check and does not perform a deep copy of the elements.

A LinkedList held in a Deque variable still uses LinkedList's own `equals` implementation. Choosing a Deque variable type does not turn the object into an ArrayDeque or change how `equals` is implemented.

This is a correctness difference when swapping classes, not merely a speed difference. If a program relies on container `equals`/`hashCode`, you must verify the contract rather than just matching method names. [Deque and equals/hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), [ArrayDeque inherits equals from Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

## 9. Complete program: interfaces, null, and equals

Save as `CollectionContractDifferencesDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.RandomAccess;

public class CollectionContractDifferencesDemo {
    private static void capabilities(String name, Object value) {
        System.out.println(name + ": List=" + (value instanceof List<?>)
                + ", Deque=" + (value instanceof Deque<?>)
                + ", RandomAccess=" + (value instanceof RandomAccess));
    }

    public static void main(String[] args) {
        capabilities("ArrayList", new ArrayList<>());
        capabilities("LinkedList", new LinkedList<>());
        capabilities("ArrayDeque", new ArrayDeque<>());

        List<String> arrayList =
                new ArrayList<>(Arrays.asList("A", null, "A"));
        List<String> linkedList = new LinkedList<>(arrayList);
        System.out.println("ArrayList with null: " + arrayList);
        System.out.println("LinkedList with null: " + linkedList);

        Deque<String> arrayDeque = new ArrayDeque<>();
        try {
            arrayDeque.offerLast(null);
        } catch (NullPointerException ex) {
            System.out.println("ArrayDeque null: NullPointerException");
        }
        System.out.println("ArrayDeque size after rejected null: "
                + arrayDeque.size());

        List<String> leftList = new ArrayList<>(List.of("A", "B"));
        List<String> rightList = new LinkedList<>(List.of("A", "B"));
        System.out.println("ArrayList equals LinkedList: "
                + leftList.equals(rightList));

        Deque<String> firstDeque =
                new ArrayDeque<>(List.of("A", "B"));
        Deque<String> secondDeque =
                new ArrayDeque<>(List.of("A", "B"));
        System.out.println("two ArrayDeque instances equal: "
                + firstDeque.equals(secondDeque));
        System.out.println("compare encounter order as lists: "
                + new ArrayList<>(firstDeque)
                        .equals(new ArrayList<>(secondDeque)));

        Deque<String> linkedAsDeque =
                new LinkedList<>(List.of("A", "B"));
        System.out.println("LinkedList held as Deque equals List: "
                + linkedAsDeque.equals(leftList));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CollectionContractDifferencesDemo.java
java CollectionContractDifferencesDemo
```

Standard output:

```text
ArrayList: List=true, Deque=false, RandomAccess=true
LinkedList: List=true, Deque=true, RandomAccess=false
ArrayDeque: List=false, Deque=true, RandomAccess=false
ArrayList with null: [A, null, A]
LinkedList with null: [A, null, A]
ArrayDeque null: NullPointerException
ArrayDeque size after rejected null: 0
ArrayList equals LinkedList: true
two ArrayDeque instances equal: false
compare encounter order as lists: true
LinkedList held as Deque equals List: true
```

Key observations:

1. ArrayList is a List with RandomAccess; LinkedList is both a List and a Deque; ArrayDeque only belongs to the Deque/Queue side of the two roles considered here.
2. Null and the duplicate value A are preserved in both lists.
3. ArrayDeque rejects null without adding a new entry.
4. An ArrayList and a LinkedList with the same sequence evaluate `equals` to true.
5. Two separate ArrayDeque instances with the same sequence do not have content-based equality.
6. Converting their encounter orders into ArrayLists allows comparing the sequences under the List contract.
7. A Deque variable pointing to a LinkedList still invokes LinkedList's `equals` implementation.

## 10. Memory and allocation: more than just Big O

### 10.1. Both array-backed structures have spare capacity

ArrayList and ArrayDeque hold reference arrays that can be larger than the logical number of elements. Spare capacity reduces the frequency of array growth, but it still occupies memory.

When the array needs to grow, there is the cost of allocating a new array and transferring data. During resize, the old and new arrays co-exist temporarily. "Amortized O(1) append" does not promise that there will never be a large allocation or copy.

ArrayList provides `ensureCapacity` and `trimToSize`. ArrayDeque does not expose that same pair of public methods. Do not treat ArrayList's capacity management API as if it were part of every array-backed data structure.

Constructors taking an initial capacity on the two array-backed classes prepare storage space; they do not pre-populate that many elements and do not impose a hard business limit.

### 10.2. LinkedList has per-node overhead

LinkedList does not maintain a spare-capacity array for the whole sequence the way the other two classes do, but every element requires a node object with links and object header overhead.

With many small elements, the memory and allocation cost of nodes can be substantial. Traversing the list requires following node references, which has a different memory access pattern than stepping through slots in a single array.

Do not equate "no unused array capacity" with "always uses less memory". The two organizations make different trade-offs.

### 10.3. Do not assign a fixed byte count across all JVMs

Total memory footprint depends on reference size, object layout, alignment, JVM configuration, spare capacity, and the element objects themselves.

All three structures hold references to elements; they do not inline copies of the full element objects inside the container. Converting between containers via a constructor also does not automatically create a deep copy of the data.

When memory footprint is a critical requirement, measure under realistic configurations and workloads. Descriptions such as "LinkedList adds two links per node" help explain the mechanism, but they do not replace measuring total memory with a universally fixed byte number.

## 11. Switching implementations requires checking call semantics too

There are two distinct kinds of changes:

- Switching `new ArrayList<>()` to `new LinkedList<>()` inside a List variable: the List contract remains valid, though performance costs change.
- Switching a design from List to Deque: the available method set—and potentially overload resolution at call sites—changes.

For example, through `List<Integer>`, `remove(1)` selects removal at index 1. Through `Deque<Integer>`, there is no `remove(int)`; the argument `1` is autoboxed to search by value via `remove(Object)`.

That difference comes from the variable type and the visible overload set, not because ArrayDeque or LinkedList guesses intent from the contained values.

Before changing classes, check at least the following points:

| Point to check | Reason |
|---|---|
| Are indexed `get`/`set`/`add` methods called? | ArrayDeque does not provide that API |
| Can the data contain null? | ArrayDeque rejects null |
| Does the code rely on container content equality (`equals`)? | ArrayDeque does not use the `List.equals` contract |
| Are `ListIterator` or `subList` used? | Those APIs belong to the List role |
| Does `remove` take an `int`, an `Object`, or no arguments? | Semantics may differ |
| Is data accessed by index inside a loop? | Can cause repeated lookup costs on LinkedList |
| Is the collection mutated across multiple references or threads? | Switching classes does not automatically handle mutation ownership or thread safety |

## 12. Iteration and concurrency: all three require clear rules

Iterators of all three classes have mechanisms to detect certain modifications outside the active iteration, but this must not be used as a thread-safety mechanism or a guarantee of correctness.

If you need to modify while iterating, use the operations explicitly supported by the iterator contract. LinkedList has a ListIterator allowing insertion and removal at the cursor; ArrayDeque does not have a ListIterator for arbitrary insertion at the current traversal position.

An iterator is not a copy of the data. Mutating through another variable referencing the same container still mutates the same underlying structure; variable names or interface types do not create independent ownership.

None of ArrayList, LinkedList, or ArrayDeque are automatically synchronized for concurrent mutating access across multiple threads. Choosing one of the three for operation cost does not satisfy concurrency or blocking-queue requirements. Those requirements must be addressed separately before selecting the appropriate data structure.

## 13. How to evaluate a choice on real workloads

A meaningful evaluation should keep the same processing goal and examine:

1. The ratio of indexed reads, full traversals, head/tail operations, and middle modifications.
2. Typical sizes and sudden traffic spikes.
3. The cost of locating the position before inserting or removing.
4. The number of allocated objects and long-lived retained memory.
5. Array growth time, reuse, and element lifecycles.
6. Contract requirements such as null handling, ordering, `equals`, and mutation permissions.

Do not print every element inside a timed region and conclude that the measurement reflects container speed. Do not compare an iterator-based algorithm against an algorithm that repeatedly re-seeks by index and call that a pure data-structure comparison.

If the same goal can be expressed with a more appropriate batch-processing algorithm, evaluate the algorithmic choice as well. Changing the container is not the only lever.

## 14. Selection and explanation exercises

| Scenario | Reasonable initial choice | Primary reason |
|---|---|---|
| Load data once and read repeatedly via `get(i)` | ArrayList | Constant-time indexed access |
| Maintain FIFO, only appending at the back and polling from the front, no nulls | ArrayDeque via Deque/Queue | Direct contract and efficient double-ended operations |
| Single-threaded stack, no nulls | ArrayDeque via Deque | Push/pop following Deque conventions |
| Traversing and making frequent local edits via an already held ListIterator | Consider LinkedList | Leverages existing node position while still accounting for traversal cost |
| Need the same object to expose both List and Deque | Consider LinkedList | Supports both API roles |
| Frequently searching for elements by value in a large sequence | Cannot decide from these three class names alone | All three perform linear value search; must examine full requirements |

Self-check questions:

1. Why is "frequent additions/removals" not enough to conclude you should use LinkedList?
2. Why does ArrayDeque use an array without needing to shift the entire sequence when removing from the front like ArrayList?
3. Do two ArrayDeque instances that print the same contents necessarily return `true` for `equals`?
4. Is switching a LinkedList containing nulls to an ArrayDeque purely a performance change?
5. If a loop over a LinkedList calls `get(i)` for every `i`, what can be fixed before changing the class?
6. Does inserting via a ListIterator on ArrayList and LinkedList have the same contract meaning and the same cost?

Answers:

1. You need to know the position, how it is located, and whether an iterator is already held; the cost of finding the node can dominate.
2. A circular array manages logical head and tail positions with indices rather than forcing the head to stay at index 0.
3. No; ArrayDeque uses object-identity `equals`.
4. No; the difference in null handling can cause operations to fail.
5. If only sequential traversal is needed, switch to a for-each loop or an iterator to avoid re-seeking each index.
6. The contract meaning is the same, but ArrayList may need to shift elements whereas LinkedList updates links at the already reached node.

Choose based on the contract and operation pattern: ArrayList for List needs oriented around indexed access, ArrayDeque for standard double-ended needs without null elements, and LinkedList for cases with specific reasons involving node position or combined List/Deque roles. Then verify costs and data characteristics against your program's actual workflow.
