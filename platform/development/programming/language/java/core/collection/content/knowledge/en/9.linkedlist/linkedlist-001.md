# Doubly Linked Lists and the Node Cost of LinkedList

## 1. LinkedList Stores a Chain of Nodes Instead of an Element Array

Java's `LinkedList<E>` is a doubly linked list. Each occurrence in the list is represented by a node. A node holds a reference to the element and links to the previous and next nodes.

The key difference from an array-backed list is that to add or remove a node at a known position, the list rewires a few links around that position. It does not need to shift the entire trailing range of elements into other array slots.

However, this benefit comes at a price:

- Reaching a middle position usually requires traversing across nodes.
- Each occurrence requires a node object and management references.
- Reading across the chain of nodes may touch many different memory locations.
- Continuous insertions and removals create allocation and garbage collection work for nodes.

Therefore, "LinkedList insertion/removal is O(1)" is only true if it is explicitly stated that the operating position has already been located. It does not fully describe a removal call by index or by value.

According to the [Java 17 LinkedList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), this class implements both List and Deque. We can use it as an indexed sequence or as a double-ended queue. Both usages rely on the same structure but lead to very different cost patterns.

This article uses Java 17 or later. The examples run in a single thread without concurrent structural modifications from elsewhere while an iterator is running.

## 2. Model of a Node: item, prev, and next

### 2.1. Three References Have Three Different Roles

Conceptual shape of a node:

```text
Node
  item ----> element object E
  prev ----> previous node
  next ----> next node
```
In the OpenJDK 17 implementation, Node is an internal private class of LinkedList, not a node type exposed by the public API for callers to hold and manipulate directly.

Distinction table:

| Component | What Does It Point To? | Purpose |
| --- | --- | --- |
| item | Element object, or null | Holds the value of the occurrence in the list |
| prev | Another node, or null at the head | Allows backward traversal and rewiring in front |
| next | Another node, or null at the tail | Allows forward traversal and rewiring behind |

item is not a deep copy of the object. If the element is an order, the node holds a reference to the order; the entire order data is not packed directly into the link fields.

When calling `getFirst()`, `get(i)`, or `iterator.next()`, we receive the **element E**, not the internal Node. Holding a reference to the element does not mean having a reference to the node containing it.

### 2.2. first and last Belong to the List Object

The LinkedList object itself holds references to the first node, the last node, and size information.

```text
                  first                         last
                    |                             |
                    v                             v
null <-prev- [node A] <-prev- [node B] <-prev- [node C]
             [      ] -next-> [      ] -next-> [      ] -next-> null

Each node also has its own item pointing to A, B, or C.
```
A more compact reading:

```text
first -> [A] <-> [B] <-> [C] <- last

[A], [B], [C] are nodes, not guaranteed memory locations.
```
In the OpenJDK 17 model, this list is not circular and does not use a fixed dummy node to represent boundaries. Some books or other linked structures use a sentinel node; do not apply that diagram verbatim to Java's LinkedList.

Implementation details in this article are cross-referenced with the [OpenJDK 17 LinkedList source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java). The API specifies public behavior; the Node shape is implementation information used to explain mechanisms and costs.

### 2.3. Why Are Both prev and next Needed?

next is enough to move forward. Adding prev allows:

- Moving backward from the tail.
- Knowing the predecessor once a node in the middle is already known.
- Removing a known node by linking its two neighbors together.
- Keeping operations at both ends free from traversing the entire chain from the head.

In exchange, each node carries an extra reference, and every linking/unlinking step must keep both directions consistent. Doubly linking is a structural trade-off, not a free capability.

## 3. Invariants That Must Always Hold

A linked structure is only useful when its links are consistent. The following invariants help with understanding algorithms and catching bugs when implementing a similar list yourself.

### 3.1. Empty List

```text
size = 0
first = null
last  = null
```
There are no element nodes in the chain. An empty LinkedList object is still a list container object; "no nodes" does not mean consuming zero memory at all.

### 3.2. Single-Element List

```text
first ----+
          v
        [node X]
          ^
last -----+

node X.prev = null
node X.next = null
size = 1
```
first and last must point to the same node. When removing the sole node, **both** must be updated to null.

If only one end is updated, the structure can report empty along one access path while retaining an old node along another path. This is a common boundary bug when writing a linked list from scratch.

### 3.3. Multi-Node List

- first.prev equals null.
- last.next equals null.
- If x.next is y, then y.prev must be x.
- If y.prev is x, then x.next must be y.
- Following next from first must visit exactly `size` nodes and then terminate.
- Following prev from last must yield the same nodes in reverse order.

LinkedList manages these invariants internally. API users do not modify prev/next directly.

Note: `item == null` is different from `node == null`. LinkedList allows a node to hold a null element; that is still an occurrence in the list and still increments size. You cannot use "the first element is null" to assert that the list is empty.

## 4. Inserting a Node: Modifying a Small Link Neighborhood

### 4.1. Inserting X Between P and Q

Before:

```text
... <-> P <-> Q <-> ...

P.next = Q
Q.prev = P
```
After:

```text
... <-> P <-> X <-> Q <-> ...

X.prev = P
X.next = Q
P.next = X
Q.prev = X
```
Once the involved nodes are known, only a constant number of node creation and reference assignment operations are required, independent of the list length.

Every node behind Q does not need to be "pushed" elsewhere. Their positions in the List order change, but there is no indexed array that needs physical shifting.

This also explains the statement in the List documentation that elements after the insertion point have their indices incremented by one: **the logical index changes**, which does not mean LinkedList copies the entire tail segment like an array-backed list.

### 4.2. Adding at the Head

For a non-empty list:

1. Create a new node with prev set to null and next set to the old first.
2. Point the old first node's prev to the new node.
3. Update first.
4. Increment size.

If the list was previously empty, the new node becomes both first and last.

There is no need to search for the head because the list object already holds first. The number of links to update is constant.

### 4.3. Adding at the Tail

Similarly:

1. Create a new node with prev set to the old last and next set to null.
2. Point the old last node's next to the new node.
3. Update last.
4. If previously empty, update first as well.
5. Increment size.

This is the mechanism of normal tail insertion. There is no backing array that must be expanded and have all old references copied, but **a new node still needs to be allocated**.

The steps above describe the relationships required after the operation in a single thread. Do not treat this sequence of link assignments as an atomic thread-safe operation.

## 5. Removing a Node: Linking Two Neighbors and Detaching the Old Node

Suppose the node X to be removed has already been located:

```text
Before: ... <-> P <-> X <-> Q <-> ...
After:  ... <-> P <------> Q <-> ...
```
We need to link P.next to Q and Q.prev to P. Boundary cases:

| Where Is X? | Boundary Update |
| --- | --- |
| In the middle | Link the two neighbors together |
| Is first, with a successor remaining | first becomes the successor; the new first's prev becomes null |
| Is last, with a predecessor remaining | last becomes the predecessor; the new last's next becomes null |
| Is the sole node | Both first and last become null |

After that, size is decremented. In OpenJDK 17, the references of the unlinked node are cleared appropriately to avoid retaining unnecessary data and node chains through that node.

Unlinking a node does not mean the element object is immediately destroyed:

- The removal method may return the element to the caller.
- The object may still reside at another position in the same list.
- The object may still be retained by another list or another variable.
- The garbage collector decides when to reclaim an object that is no longer reachable.

Java has no `free(node)` step that a LinkedList user must call after each removal. Understand reference lifecycles, and do not write programs that depend on exact garbage collection timing.

## 6. Knowing the Node Is Different from Knowing the Index or Value

### 6.1. Knowing the Index Does Not Mean Knowing the Node

With an array, the slot can be determined directly from the index. With LinkedList, `get(i)` must find the node at position `i` by following links.

LinkedList chooses to start from the head or from the tail depending on which end is closer. For a valid element index:

```text
n = size before operation
0 <= i < n

Number of link steps to reach i:
d(i) = min(i, n - 1 - i)

Cost to locate the node:
O(1 + d(i))
```
Adding 1 ensures that even the first or last cases represent constant work.

For example, in a list of 1,000 elements:

- `get(0)`: already has first.
- `get(999)`: already has last.
- `get(998)`: steps backward one link from last.
- `get(500)`: still has to traverse hundreds of links.

Therefore, `get` near either end can be cheap, whereas `get` in the middle has linear cost with respect to `n`.

### 6.2. Insertion and Removal by Index Must Include the Search Step

```text
Cost of add(i, value)
= locate insertion position
+ create node
+ update a few links.

Cost of remove(i)
= locate node at i
+ unlink a few links.
```
`add(size(), value)` is the tail case and can use last directly. Inserting before an element in the middle still requires finding that node first.

A `remove(i)` call does not become O(1) just because the unlinking part after locating the node is O(1).

### 6.3. Removal by Value Must Also Search by Equality

`remove(value)` searches for the first occurrence by equality and only then unlinks the node. If the value is absent or far from the head, the entire list may need to be examined.

When treating each comparison as constant, the worst case is O(n). If `equals` inspects a large structure, that comparison cost must be added. Doubly linking does not create a value lookup table.

With `LinkedList<Integer>`, you must also distinguish two overloads:

```java
// Illustrative snippet; both lists start with identical data.
LinkedList<Integer> byIndex = new LinkedList<>(List.of(10, 20, 10));
byIndex.remove(1);                   // Removes index 1: [10, 10].

LinkedList<Integer> byValue = new LinkedList<>(List.of(10, 20, 10));
byValue.remove(Integer.valueOf(10)); // Removes first value equal to 10: [20, 10].
```
Distinguish the intended removal requirement first before analyzing how many links must be traversed.

### 6.4. Cost Tables Must Carry Conditions

The table considers the standard structural operation model of LinkedList, excluding business logic work and assuming constant-time equality comparisons.

| Operation | Cost | Reason |
| --- | --- | --- |
| size(), isEmpty() | O(1) | Stored size information is available |
| getFirst(), getLast(), peekFirst(), peekLast() | O(1) | first/last references are available |
| addFirst(), addLast(), add(E) | O(1) structural operation | Creates one node and links it at a known end |
| removeFirst(), removeLast(), pollFirst(), pollLast() | O(1) | Unlinks the node at a known end |
| get(i), set(i, value), remove(i) | O(1 + min(i, n - 1 - i)) | Must reach the node at i |
| add(i, value), for i < n | Cost to find node at i plus O(1) | Cannot skip the locating step |
| add(n, value) | O(1) structural operation | Appends after last |
| contains(value), remove(value) | O(n) worst case | Linear search |
| Full traversal via iterator | O(n) | Each step advances from the current position |
| clear() in OpenJDK 17 | O(n) for non-empty list | Walks through nodes to clear references |

The O(1) notation for structural operations is not a guarantee of maximum latency in nanoseconds. Allocation, garbage collection, scheduling, and the memory subsystem still affect actual wall-clock time.

## 7. What Does the Cost of a Node Consist Of?

### 7.1. Not Just item

An element occurrence requires space for:

1. The `item` reference.
2. The `prev` reference.
3. The `next` reference.
4. JVM object header / management metadata.
5. Alignment padding to satisfy memory alignment requirements, if any.

Beyond the nodes, the LinkedList object itself has list container state. And the element object itself may occupy another amount of memory.

Do not simply sum three references and call that the full size of a Node. Likewise, do not take a measurement from one JVM and treat it as a constant of the Java language.

### 7.2. Separating Structural Memory from Element Payload Memory

A conceptual estimation model:

```text
LinkedList structural memory
approximately equals
container memory
+ n * memory per Node.

Memory per Node
includes three reference fields, object header metadata, and alignment.

Memory of the entire object graph under consideration
may also include the element objects and whatever they reference.
```
Here `n` is the number of occurrences, not the number of distinct element objects.

If the same object is added 1,000 times to a LinkedList under the OpenJDK 17 implementation, we have 1,000 nodes holding references to that same object. It does not duplicate the object into 1,000 deep copies, nor does it collapse 1,000 nodes into a single node.

If `null` is added multiple times, each addition still gets its own node. An `item` equal to `null` does not eliminate the space needed for `prev`, `next`, and node object overhead.

### 7.3. Counting Reference Fields Is Different from Counting Bytes

With `n` nodes, there are `3n` reference fields inside the nodes. The two boundary links hold `null` when the list is non-empty, but a field holding `null` still occupies space in the node's representation.

The exact byte count depends on the JVM and its configuration, such as reference representation, object headers, and alignment. If numbers are needed for a specific environment, measure in that environment and record the measurement conditions.

[OpenJDK JOL](https://github.com/openjdk/jol) is a tool for inspecting object layouts. When using results from the tool, distinguish between:

- The shallow size of an object.
- Objects reachable via references in an object graph.
- Payload data shared with other list objects.
- Memory exclusively retained under a specific lifecycle analysis.

Do not count the entire element graph twice just because two lists point to those same objects.

### 7.4. "No Spare Capacity" Does Not Mean "Always Uses Less Memory"

An array-backed list typically has a block of reference slots, which may include spare capacity. LinkedList does not need a capacity array of that kind, but it pays the cost for every individual Node object.

When element payloads are small or heavily shared, node overhead can represent a significant proportion of total memory. When element payloads are very large, node overhead may be smaller in relative terms, yet it still exists.

Do not assert a fixed memory ratio between LinkedList and ArrayList. Pre-allocated capacity in ArrayList, how the JVM represents nodes, and the element graph all influence the comparison.

## 8. Allocation, Garbage Collection, and Memory Locality

### 8.1. Retained Size Is Different from Total Nodes Created

Suppose an application repeatedly adds one element and then removes it. `size` may rarely exceed 1, yet after a million iterations, a large number of nodes have been created and discarded under LinkedList's implementation.

This distinguishes:

- **Memory retained at a point in time:** depends on the number of nodes still inside the structure and live references.
- **Allocation throughput over time:** depends on how many times nodes are created.
- **Garbage collection work:** depends on the JVM, object lifetimes, workload, and configuration.

Creating a small node can be performed quickly by the JVM. Even so, "small" does not mean free; a heavy insertion/removal workload can make allocation and garbage collection a substantial factor in performance.

`set(i, value)` replaces the element on an already located node; it does not need to allocate a new list node just to replace `item`. If the `value` argument is created with `new` on the caller side, the cost of creating that object is separate work.

### 8.2. Following Links Can Cause Multiple Data Stalls

Nodes are separate objects. The API does not promise that they sit next to each other in memory. To advance, the program must read `next` or `prev` before it knows the address of the next node.

If the next node's data is not yet in the CPU cache, the traversal may have to wait. An array-backed list has the advantage that its sequence of reference slots is contiguous within the same backing array region.

That is one reason to be cautious about claims like "both are O(n), so traversal speed is the same." Big-O does not capture the number of objects, the levels of reference indirection, or how data moves across the memory hierarchy.

Conversely, do not flip this into an absolute claim that all LinkedList nodes are always far apart or that LinkedList is always slower. Actual memory layout, per-element work, and JVM behavior all need to be considered.

### 8.3. clear Does Not Just Drop Both Ends

In OpenJDK 17, `clear` walks through the nodes and nulls out `item`/`next`/`prev` before resetting `first`, `last`, and `size`. Therefore, `LinkedList.clear()` should not be analyzed as merely two assignments `first = last = null`.

Clearing the links helps avoid retaining an unnecessary chain of data through an old reference to a node and assists the implementation's memory management. When actual memory is reclaimed is still decided by the GC.

Do not call `System.gc()` and take the memory difference from a single run as the canonical size of a Node. Process-wide measurements are affected by many objects and internal JVM decisions.

## 9. Runnable Example: Both Ends, Reverse Traversal, and Boundary States

Save the program as `LinkedListEndsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;

public class LinkedListEndsDemo {
    public static void main(String[] args) {
        Deque<String> items = new LinkedList<>();
        System.out.println("initially empty = " + items.isEmpty());

        items.addLast("B");
        items.addFirst("A");
        items.addLast("C");
        System.out.println("forward = " + items);
        System.out.println("first = " + items.getFirst());
        System.out.println("last = " + items.getLast());

        List<String> reversed = new ArrayList<>();
        for (Iterator<String> it = items.descendingIterator(); it.hasNext();) {
            reversed.add(it.next());
        }
        System.out.println("reverse traversal = " + reversed);

        System.out.println("removed first = " + items.removeFirst());
        System.out.println("removed last = " + items.removeLast());
        System.out.println("one item remains = " + items);
        System.out.println("removed only item = " + items.removeLast());
        System.out.println("empty again = " + items.isEmpty());
        System.out.println("pollFirst on empty = " + items.pollFirst());

        try {
            items.removeFirst();
        } catch (NoSuchElementException ex) {
            System.out.println("removeFirst on empty = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```
Compile and run:

```shell
javac --release 17 LinkedListEndsDemo.java
java LinkedListEndsDemo
```
Output:

```text
initially empty = true
forward = [A, B, C]
first = A
last = C
reverse traversal = [C, B, A]
removed first = A
removed last = C
one item remains = [B]
removed only item = B
empty again = true
pollFirst on empty = null
removeFirst on empty = NoSuchElementException
```
Structural explanation:

- Adding B to an empty list creates a node that is both head and tail.
- Adding A at the head and C at the tail creates the chain A ↔ B ↔ C.
- `descendingIterator` traverses in reverse order, returning C, B, A.
- After removing A and C, only node B remains, so both ends point to that same node.
- Removing B brings both ends back to the empty state.
- `pollFirst` returns `null` when empty; `removeFirst` throws `NoSuchElementException` when empty.

According to the [Java 17 Deque contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), method pairs typically differ in how they signal the absence of an element. Choose the reporting style that fits the processing flow; do not treat `poll` and `remove` as having the same failure contract.

LinkedList also permits storing `null`. If `null` is inserted, `poll` returning `null` could be the element just removed rather than an indication that the list was previously empty. For a queue that needs to use `null` as an end-of-stream signal, enforce a non-null policy or choose an appropriate state management mechanism. Do not write processing loops based on ambiguous signals.

The variable is declared as `Deque` because the example only needs double-ended operations. This declaration expresses the caller's requirements; the concrete backing structure is still `LinkedList`.

## 10. Position-Holding Iterators Avoid Re-Locating Nodes

### 10.1. An Iterator Knows Its Current Position in the Chain

A LinkedList iterator maintains enough state to advance to the next node and operate on the element just returned. It does not have to call `get(i)` from the beginning on every iteration.

When positioned at the right place, `iterator.remove()` unlinks the node just returned by simply rewiring neighbors. `ListIterator.add()` inserts at the current cursor without starting a new index search either.

This is a case that can take advantage of the linked mechanism:

```text
Locate / reach the position once
-> read nodes sequentially
-> modify near the cursor position
-> continue advancing.
```
Conversely, creating `listIterator(i)` at a middle position still requires traversing to that position during initialization. Re-creating an iterator in the middle on every step can negate the benefit of holding position.

### 10.2. Single-Pass In-Place Editing Program

Save as `LinkedListCursorEditDemo.java`:

```java
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListCursorEditDemo {
    public static void main(String[] args) {
        LinkedList<Integer> values = new LinkedList<>(
                List.of(10, -1, 20, -2, 30));
        int visited = 0;
        int removed = 0;
        int inserted = 0;

        for (ListIterator<Integer> it = values.listIterator(); it.hasNext();) {
            int value = it.next();
            visited++;

            if (value < 0) {
                it.remove();
                removed++;
            } else if (value == 20) {
                it.add(21);
                inserted++;
            }
        }

        System.out.println("result = " + values);
        System.out.println("visited original values = " + visited);
        System.out.println("removed nodes = " + removed);
        System.out.println("inserted nodes = " + inserted);
    }
}
```
Compile and run:

```shell
javac --release 17 LinkedListCursorEditDemo.java
java LinkedListCursorEditDemo
```
Output:

```text
result = [10, 20, 21, 30]
visited original values = 5
removed nodes = 2
inserted nodes = 1
```
The program reads the five original elements:

- Nodes containing `-1` and `-2` are unlinked via `iterator.remove()`.
- Upon encountering `20`, a new node containing `21` is inserted at the cursor position.
- The newly inserted element sits after the element just read and before the element that will be read next. By the rules of `ListIterator.add`, the subsequent `next()` call still returns the element that originally stood next, so `21` is not counted again as a visited original element.

With a single sequential pass, constant-time conditions, and each element causing only a constant-bounded number of node operations, total structural work is linear in the number of initial elements plus the number of inserted nodes.

The counters in the program are algorithmic behavior counters, not byte or GC counters. Printing the entire list at the end also incurs a traversal cost, which should not be included inside a benchmark intended strictly to isolate a single node-linking operation.

### 10.3. Modification Rules During Iteration Must Still Be Respected

- `remove` requires an element that was just returned by `next` or `previous` and has not yet been removed.
- `add`/`remove` through the iterator itself must follow the iterator's state rules.
- Do not invoke other structural modification methods on the list directly and assume the existing iterator remains valid.
- Fail-fast behavior helps detect certain invalid concurrent/out-of-band modifications on a best-effort basis; it is not a synchronization mechanism.

Holding an iterator does not mean holding a stable public node reference that can be used arbitrarily across arbitrary external changes. Do not design algorithms assuming Java's LinkedList lets you pass a `Node` directly into a public method for deletion.

## 11. Runnable Example: Separate Nodes, Shared Elements

Save as `LinkedListPayloadSharingDemo.java`:

```java
import java.util.LinkedList;
import java.util.List;

public class LinkedListPayloadSharingDemo {
    static final class Task {
        String title;

        Task(String title) {
            this.title = title;
        }

        @Override
        public String toString() {
            return title;
        }
    }

    public static void main(String[] args) {
        Task shared = new Task("draft");
        LinkedList<Task> original = new LinkedList<>(List.of(shared, shared));
        LinkedList<Task> copy = new LinkedList<>(original);

        System.out.println("original size = " + original.size());
        System.out.println("same payload at two positions = "
                + (original.getFirst() == original.getLast()));

        original.removeFirst();
        System.out.println("original size after removal = " + original.size());
        System.out.println("copy size after original removal = " + copy.size());
        System.out.println("same payload across containers = "
                + (original.getFirst() == copy.getFirst()));

        shared.title = "approved";
        System.out.println("original values = " + original);
        System.out.println("copy values = " + copy);

        copy.clear();
        System.out.println("copy empty = " + copy.isEmpty());
        System.out.println("original size after copy.clear = " + original.size());
    }
}
```
Compile and run:

```shell
javac --release 17 LinkedListPayloadSharingDemo.java
java LinkedListPayloadSharingDemo
```
Output:

```text
original size = 2
same payload at two positions = true
original size after removal = 1
copy size after original removal = 2
same payload across containers = true
original values = [approved]
copy values = [approved, approved]
copy empty = true
original size after copy.clear = 1
```
Read the output across two layers:

1. **Structural layer:** removing from `original` does not decrease `copy`'s size. Calling `clear` on `copy` does not remove the remaining occurrence in `original`.
2. **Element payload layer:** the occurrences hold references to the same `Task`, so mutating `Task.title` is visible when traversing both lists.

In OpenJDK 17, constructing a new LinkedList from a collection builds a new chain of nodes for the elements retrieved from the source collection. It does not reuse a single `Node` chain as a shared backbone between the two lists.

However, the `Task` objects themselves are not deep-copied. Initially `original` has two nodes and `copy` has two nodes, while all four `item` references point to the exact same `Task`.

After `original.removeFirst()`, one node is no longer in `original`. This does not destroy the `Task` because the other nodes and the `shared` variable still hold references to it.

The program does not directly inspect internal `Node` instances and does not measure memory. It verifies the independent behavior of the two list objects and the shared behavior of the element payload. How new nodes are constructed is explained from the OpenJDK 17 structure rather than inferring node addresses from stdout.

One design consequence: if you create your own element class with `prev`/`next` fields and insert it into `java.util.LinkedList`, `LinkedList` does not automatically use those two fields as its internal links. It still wraps the element inside its own `Node`. An intrusive "element carries its own links" structure is a different design and is not the contract of Java's LinkedList.

## 12. Using the Node Model to Evaluate Data Structure Choices

### 12.1. Patterns That Can Leverage Doubly Linking

- Working at the head/tail without needing random index access.
- Sequential traversal with modifications at an already-positioned cursor.
- Needing insertion/removal operations that do not shift a contiguous range of array slots.

However, every pattern still incurs node overhead, allocation costs, and memory access costs. Evaluate against the total workload requirements, not just a single link-rewiring operation.

### 12.2. Patterns Prone to Misuse

| Code Pattern | Issue to Consider |
| --- | --- |
| `for i` from `0` to `size - 1` calling `get(i)` | Each iteration re-locates the node; total cost can become quadratic |
| Repeated `remove(i)` in the middle | Unlinking is cheap, but re-locating the position can be expensive |
| Frequent `remove(value)` calls | Value search remains linear in the worst case |
| Continuous add/remove with a small `size` | Retained memory is small, but node allocation throughput can be large |
| Adding the same object many times | Does not duplicate the element, but still allocates many nodes |
| Choosing LinkedList solely for "no spare capacity slots" | Overlooks object headers and three references on every single node |
| Sharing LinkedList across threads without synchronization | Doubly linking does not provide thread safety |

If you only need a general-purpose `Deque` and do not need `null` elements, consider [Java 17 ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), which uses an array structure and has no separate linked `Node` per occurrence. This choice should be evaluated per workload; do not extrapolate it into a fixed speed ratio or assume 100% behavioral compatibility with LinkedList.

If most of the workload is indexed reads or steady traversal, an array-backed list should also be considered. Before switching data structures, clearly document requirements around ordering, `null` handling, duplicate elements, cursor-based edits, and threading model.

### 12.3. Evaluating by Step Count and by Goal-Aligned Measurements

Step-count analysis answers "how does cost grow as `n` grows?" Performance measurement answers "in this environment, how does this workload actually run?"

To evaluate actual node cost, you may need to:

- Measure structural memory using the same set of element objects, avoiding unintentional data duplication.
- Measure allocation rate during insertions/removals alongside retained memory.
- Separate business element creation from node insertion if the goal is strictly to measure the list structure.
- Benchmark an actual traversal pass and modification pattern representative of the application.
- Record the JVM version, relevant flags, dataset size, and measurement conditions.

Do not conclude from a small functional demo printing correct output that allocation or cache costs have been measured. The programs in this article demonstrate functional behavior and reference models.

## 13. Common Misconceptions When Explaining LinkedList

| Misconception | Correction |
| --- | --- |
| "Each node embeds the entire element object inside itself" | A Node holds an `item` reference; the element object lives at a separate layer |
| "A doubly linked list is two separate lists" | It is a single chain of nodes linked in both directions |
| "Having `prev` makes `get(i)` O(1)" | It only allows starting from the closer end; links must still be traversed |
| "Knowing the element value means knowing the node" | The same object can appear multiple times; the API returns the element, not the Node |
| "Removing in the middle is always O(1)" | Only the unlinking step at an already located node is constant time |
| "Decreasing indices after removal requires shifting every node" | Indices are logical positions; the structure only rewires links |
| "No spare capacity means it always uses less memory" | Every node incurs object header overhead plus three references |
| "Unlinking a node destroys the element immediately" | The element may still be referenced elsewhere; the GC decides reclamation |
| "`clear` only drops `first`/`last`, so it is always O(1)" | OpenJDK 17 walks the chain to clear references inside the nodes |
| "A Node always costs exactly X bytes on every JVM" | Reference representation, headers, and alignment depend on the runtime environment |
| "An iterator holds a node so modification rules don't apply" | The iterator has its own state machine and modification contract |
| "LinkedList is ready for multi-threaded use out of the box" | The class is not synchronized; proper concurrent access design is required |

## 14. Practice with Links, Costs, and Lifecycles

### Exercise 1: Does Inserting in the Middle Require Updating Distant Elements?

Given the chain A ↔ B ↔ C ↔ D, insert X between B and C assuming the position is already known.

The new relationships are `B.next = X`, `X.prev = B`, `X.next = C`, and `C.prev = X`. There is no need to update the links of A and D just to insert at this position. `size` increases by one.

The logical positions of C and D increase by one, but there is no index field stored inside each Node that needs to be incremented.

### Exercise 2: Removing the Sole Node

The list contains only X, with both `first` and `last` pointing to X. Removing X must set both `first` and `last` to `null` and `size` to `0`. Forgetting one end is a bug even if certain inspection operations might not expose it immediately.

### Exercise 3: Three References per Node

A list has five nodes, all with non-null `item` references. How many reference fields exist across the nodes, and how many `prev`/`next` links are non-null?

There are 15 reference fields across the five nodes. The non-null `prev`/`next` links number `2 * (5 - 1) = 8`; the two boundary link fields hold `null`. In addition, there are five non-null `item` references. Do not use the number 15 to immediately deduce a byte count without knowing the JVM representation.

### Exercise 4: The Same Object Appears 100 Times

Under the OpenJDK 17 model, there are 100 nodes and 100 `item` fields pointing to the same object. There are not 100 deep copies of the element.

Removing one occurrence only removes one node. The object can still be retained by the remaining 99 occurrences and other external references.

### Exercise 5: Removing by Middle Index in a Large List

Why shouldn't `remove(500_000)` on a list of one million elements simply be called O(1)?

Because the node at that index must first be located by traversing links. Rewiring the neighbors is only the step performed after arriving at that position.

### Exercise 6: Small Retained Memory at Any Moment, Large Allocation Over Time

A loop that continually calls `addLast` followed by `removeFirst`, without retaining elements, may hold very few nodes at any given instant. Nevertheless, running many iterations creates many nodes over time. The two metrics "retained memory" and "allocation rate" answer two different questions.

### Exercise 7: Recognizing a Quadratic Sum

If you traverse a LinkedList by calling `get(i)` from `0` to `n - 1`, each call starts locating from one end of the list. The total number of traversed links is Θ(n²). Using a position-holding iterator for a single pass avoids re-locating the position for every element.

### Exercise 8: Do a Node and Its Element Share the Same Lifecycle?

Not necessarily. An unlinked node may no longer be held by the list, while the returned element remains stored in a caller's variable. Conversely, multiple nodes across different lists can point to the exact same element.

When analyzing LinkedList, separate **locating the position → linking/unlinking references → allocating/discarding nodes → element lifecycle**. These four parts explain why doubly linking is advantageous for certain operation patterns yet still carries time and memory costs that the phrase "fast insertion/removal" fails to capture.
