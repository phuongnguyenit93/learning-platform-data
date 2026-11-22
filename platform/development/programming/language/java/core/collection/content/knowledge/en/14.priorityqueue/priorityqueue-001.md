# Priority Queues and Their Relationship with the Heap Structure

## 1. From "First Come" to "Process First"

Suppose an application holds pending jobs. A is submitted first, and B is submitted later, but B is more urgent. If the application always picks the job that arrived first, A is chosen. If the rule is to pick the job with higher urgency, B must be chosen even though it arrived later.

A **priority queue** answers the question: "Among the current elements, which element comes first according to the priority rule?" In Java, `PriorityQueue<E>` is a class implementing the `Queue<E>` interface for this need.

Three layers should be distinguished:

| Layer | Question Addressed |
| --- | --- |
| Business rule | What counts as higher priority: an earlier deadline, a lower cost, a higher urgency level...? |
| Priority queue | Add elements, inspect, or remove the head element according to that rule |
| Heap structure | Data organization to maintain the priority element in an easily accessible position with reasonable update cost |

A heap is the internal organizational mechanism, whereas a priority queue is the behavior needed by the user of the data structure. A priority queue model can be built in many ways; OpenJDK uses a binary heap for `PriorityQueue`.

This lesson moves from the meaning of the queue's head to the heap property, how elements are added/removed, costs, and Java 17+ examples. The goal is to explain **why retrieving the priority element is fast even though the entire dataset does not need to be completely sorted**.

## 2. The Head of the Queue Is the Smallest Element by the Comparison Rule

### 2.1. Smallest by Comparator Is Not Necessarily the Smallest Number

With the default configuration for integers:

```java
PriorityQueue<Integer> queue = new PriorityQueue<>();
queue.offer(5);
queue.offer(1);
queue.offer(4);
```

This is an illustrative snippet placed inside a method and requires importing `java.util.PriorityQueue`. `queue.peek()` returns 1: the natural ordering of `Integer` considers 1 to come before 4 and 5.

If you use:

```java
PriorityQueue<Integer> queue =
        new PriorityQueue<>(Comparator.reverseOrder());
```

then 5 comes before 4 and 1 according to the reversed comparator. `peek()` returns 5. You also need to import `java.util.Comparator`.

Java still retrieves the smallest element **according to the ordering currently used by the queue**. From the perspective of the original numeric values, the second case behaves like a queue that retrieves the largest number first.

There is no default rule that a field named `priority` with a larger value is processed first. Define your application's convention explicitly and build the corresponding comparator.

### 2.2. FIFO Is Not a Guarantee of PriorityQueue

Adding `5, 1, 4` in sequence and then draining all elements with `poll()` on a default queue yields `1, 4, 5`, not `5, 1, 4`.

If two elements are equal in priority, `PriorityQueue` does not automatically guarantee that the one that arrived first is retrieved first. A secondary criterion such as a job submission sequence number may be needed. Priority ties also do not cause new elements to be discarded: the queue can hold multiple elements with the same value or the same priority level.

The contract regarding the head element, priority ties, and iteration order is documented in the [Java 17 PriorityQueue documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

### 2.3. The Queue Does Not Execute Work on Its Own

Retrieving a task from a `PriorityQueue` does not make Java automatically create a thread or run that task. The application must still decide when to call `poll()`, where to run the job, and how to handle errors.

If high-priority jobs are continuously added, low-priority jobs may wait for a long time. That is a matter of the application's scheduling policy; the heap itself does not add fairness mechanisms or increase priority over time.

## 3. Binary Heap: Complete Shape, Per-Branch Ordering

### 3.1. Two Conditions to Maintain

For a min-heap (smallest element at the root), the two conditions are:

1. **Shape:** a complete binary tree. All levels before the last are completely filled; the last level is filled from left to right.
2. **Heap order:** each parent node does not come after its child nodes according to the comparison rule.

An integer min-heap can look like this:

```text
          2
        /   \
       5     3
      / \   /
     9   6 8
```

All edges satisfy the condition: 2 ≤ 5, 2 ≤ 3, 5 ≤ 9, 5 ≤ 6, 3 ≤ 8. Because the comparison relation is transitive, the root 2 is not greater than any descendant, so 2 is a smallest element of the entire heap.

This tree has a complete shape because the last level has three positions filled contiguously from the left. It does not need to have an equal number of left and right child nodes at every node.

### 3.2. A Heap Is Not a Binary Search Tree

In the illustrative tree, the left child 5 is greater than the root 2. This is completely valid for a min-heap. There is no condition that "every value on the left is smaller than the root," as learners often remember for binary search trees.

Between sibling nodes 5 and 3, a heap also does not require 5 to be smaller than 3. Between 6 and 8 in different branches, no fixed position is determined solely by their global order.

The heap invariant only establishes enough relationships to know that the root is the highest-priority element. It does not create a search path for an arbitrary value like an ordered search tree.

### 3.3. A Heap Is Not a Sorted Array

Reading the tree above level by level from left to right gives:

```text
[2, 5, 3, 9, 6, 8]
```

This sequence is a valid heap representation, yet it is not in ascending order: 5 appears before 3, and 9 appears before 6 and 8. You cannot conclude a heap is invalid merely because its array representation is not sorted.

An ascending sequence also satisfies the min-heap condition under standard indexing, but the converse is not true. A heap permits many different arrangements for the same set of elements.

In this lesson, heap diagrams and arrays are **algorithmic models for explanation**. They are not claims about the order of `toString()`, `iterator()`, or the internal array that a specific JDK build must return.

## 4. Why Is a Heap Tree Usually Stored in an Array?

### 4.1. Parent and Child Positions Are Computed from Indices

With a 0-indexed array, a node at index `i` has:

| Relationship | Formula |
| --- | --- |
| Parent, when `i > 0` | `(i - 1) / 2`, integer division |
| Left child | `2 * i + 1` |
| Right child | `2 * i + 2` |

A child index exists only if it is less than the number of elements `n`.

For the illustrative heap:

```text
Index:    0  1  2  3  4  5
Value:   [2, 5, 3, 9, 6, 8]
```

- The parent of element 8 at index 5 is index 2, with value 3.
- The children of index 1 are indices 3 and 4, with values 9 and 6.
- Index 2 has a left child at 5, while a right child at 6 does not exist.

Because the tree is filled contiguously level by level, no gaps are needed between active nodes. Nor is it necessary to allocate a node object with two child references for every element.

`PriorityQueue` does not provide an API to read elements by heap array index. These formulas are for understanding the implementation, not for turning the queue into a `List`.

### 4.2. Height Grows Slowly as the Number of Elements Increases

A complete binary tree has a number of levels that grows logarithmically with `n`. When adding an element or removing the head of the queue, the element needing repositioning usually travels along a single path between the root and a leaf.

This is the source of the O(log n) cost for maintaining the heap: it is not necessary to re-sort every pair of elements after each change.

"Heap" in this data structure is also not synonymous with the JVM heap memory region. A `PriorityQueue` object and its elements may be allocated on the JVM heap, but the parent–child property being studied here is an algorithmic property, not a memory allocation rule.

## 5. Adding an Element: Moving Up to Restore Order

### 5.1. Place at the End to Preserve Shape

Start with:

```text
[2, 5, 3, 9, 6, 8]
```

We need to add 1. Place 1 in the next available position at the end of the array:

```text
[2, 5, 3, 9, 6, 8, 1]
```

The tree shape remains complete. Existing relationships remain valid, but the edge between 3 and 1 currently violates min-heap order.

### 5.2. Sift Up: Repairing Along the Path to the Root

Compare 1 with its parent 3; swap them because 1 comes before 3:

```text
[2, 5, 1, 9, 6, 8, 3]
```

Continue comparing 1 with its parent 2; swap them:

```text
[1, 5, 2, 9, 6, 8, 3]
```

1 has reached the root. Each step only needs to examine the moving node and its parent; there is no need to re-sort both branches. This process is commonly called **sift up**.

If a value greater than or equal to its parent is added initially, the process can stop early. If a new smallest value is added, it may have to travel all the way to the root.

### 5.3. Pseudocode of the Model

This is illustrative pseudocode on an abstract array, not standalone runnable Java code or source code copied from the JDK:

```text
append x to the end
i = index of x

while i > 0:
    p = parent index of i
    if compare(heap[i], heap[p]) >= 0:
        stop
    swap heap[i] with heap[p]
    i = p
```

Actual implementations may keep `x` in a temporary variable and shift parent nodes downward instead of swapping pairs at every step. The invariant-maintenance semantics remain the same.

## 6. Removing the Root: Use the Last Element, Then Sift Down

### 6.1. Do Not Leave a Hole at the Root

Continue with the heap after adding 1:

```text
[1, 5, 2, 9, 6, 8, 3]
```

When removing 1:

1. Save 1 as the result to return.
2. Move the last element 3 to the root.
3. Decrement the element count, discarding the old last position.
4. Repair the heap relationship starting at the root.

Temporary state:

```text
[3, 5, 2, 9, 6, 8]
```

The complete shape is preserved, but 3 at the root is greater than its right child 2.

### 6.2. Sift Down: Choose the Child That Comes First

Compare the two children 5 and 2; choose 2 because it is smaller under min-heap order. Swap 3 with 2:

```text
[2, 5, 3, 9, 6, 8]
```

At its new position, 3 only has child 8; since 3 ≤ 8, stop. The heap is valid again and the method returns the 1 saved earlier.

You must choose the child that comes first between the existing children. If you arbitrarily swapped with 5, the new root could still be greater than 2, leaving the invariant broken right at the root.

This process is called **sift down**. Pseudocode:

```text
if heap is empty:
    return empty result per the method's contract

result = root element
x = last element
remove last element

if elements still remain:
    place x at the root
    i = 0
    while i has a child:
        c = index of the child that comes first by compare
        if compare(heap[i], heap[c]) <= 0:
            stop
        swap heap[i] with heap[c]
        i = c

return result
```

When there is only one element, no sift-down is needed after removing it. When there is only one child, use that child without reading a non-existent right child index.

The array storage, `siftUp`, `siftDown`, and heap construction operations can be cross-referenced in the [OpenJDK 17u PriorityQueue source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java). When using the API, rely on the public contract rather than depending on a specific internal layout.

## 7. From the Heap Mechanism to Java Methods

### 7.1. Inspecting, Removing, and Deleting by Value Are Different Operations

| Method | Meaning | When Empty or Not Found |
| --- | --- | --- |
| `offer(e)`, `add(e)` | Add e, maintaining priority queue order | For a valid element, succeeds and returns `true` |
| `peek()` | Inspect head without removing | `null` |
| `element()` | Inspect head without removing | `NoSuchElementException` |
| `poll()` | Retrieve and remove head | `null` |
| `remove()` | Retrieve and remove head | `NoSuchElementException` |
| `remove(Object)` | Find and remove an element by value | `false` if not present |
| `contains(Object)` | Check whether an element exists by value | `false` if not present |

`PriorityQueue` does not allow `null` elements, so `null` returned from `peek()` or `poll()` indicates that the queue is empty. Do not assign the result directly into a primitive type via auto-unboxing without checking for `null`: unboxing a `null` `Integer` throws a `NullPointerException`.

Distinguish no-argument `remove()` from `remove(Object)` with an argument. Removing the head can exploit the heap root directly; finding a specific value must locate its position first.

### 7.2. Initial Capacity Is Not a Limit on Element Count

`new PriorityQueue<Integer>(2)` does not create a queue that "holds at most two elements." The number 2 is the initial capacity. The queue grows its capacity when needed; the exact growth policy is not something to rely on in application logic.

The class is described as unbounded. That does not mean infinite memory is available, nor does it make it a blocking queue when full.

### 7.3. Complexity Table and Rationale

| Operation | Typical Analysis Cost | Rationale |
| --- | --- | --- |
| `peek()`, `element()`, `size()` | O(1) | Inspect root or counter field |
| `offer()`, `add()` | O(log n) for heap maintenance | Sift up along a single path |
| `poll()`, `remove()` | O(log n) | Sift down along a single path |
| `contains(Object)` | O(n) | Heap provides no search path for an arbitrary value |
| `remove(Object)` | O(n) | Linear search before repairing the heap |
| Drain all via `poll()` | O(n log n) | Repeatedly remove head over decreasing size |
| Memory for n elements | O(n) | Array and element references |

This is the class analysis described in the [PriorityQueue API documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html). When the array must grow in capacity, that particular insertion can also cost O(n) to copy element references. One should not state that every individual `offer()` call is strictly bounded by O(log n) regardless of allocation; the sift-up portion is O(log n), while array growth cost is accounted for when analyzing a sequence of operations.

These costs generally assume an O(1) comparison operation. If the comparator performs expensive work, that cost also contributes to total execution time.

### 7.4. Building from Existing Data Differs from Adding One by One

You can construct directly:

```java
PriorityQueue<Integer> queue =
        new PriorityQueue<>(List.of(9, 2, 6, 1, 5));
```

This illustrative snippet requires importing `List` and `PriorityQueue`. The created queue contains all the data; there is no requirement for the input to be pre-sorted.

Algorithmically, bottom-up heap construction by sifting down non-leaf nodes can achieve O(n). Not every node travels from the root down a height of log n: many nodes sit near the leaves and require little or no adjustment. OpenJDK 17u has such a `heapify` step for the appropriate initialization path from a regular collection.

By contrast, calling `offer()` n times has an O(n log n) upper bound for the heap-maintenance steps. The fact that both approaches produce a valid queue does not require them to produce the exact same internal array.

Do not turn an observation about one implementation path into a guarantee that every constructor in every implementation has the same cost, or that building a heap has sorted the entire array.

## 8. Runnable Program: Min-Priority and Max-Priority

Save as **PriorityQueueBasicsDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;

public class PriorityQueueBasicsDemo {
    private static <E> List<E> drain(PriorityQueue<E> queue) {
        List<E> result = new ArrayList<>();
        while (!queue.isEmpty()) {
            result.add(queue.poll());
        }
        return result;
    }

    public static void main(String[] args) {
        PriorityQueue<Integer> minQueue = new PriorityQueue<>(2);
        for (int value : List.of(5, 1, 4, 2, 3, 1)) {
            minQueue.offer(value);
        }
        System.out.println("size: " + minQueue.size());
        System.out.println("peek: " + minQueue.peek());
        System.out.println("size after peek: " + minQueue.size());
        System.out.println("ordered copy: " + drain(new PriorityQueue<>(minQueue)));
        System.out.println("original size: " + minQueue.size());

        System.out.println("remove value 4: " + minQueue.remove(Integer.valueOf(4)));
        System.out.println("contains 4: " + minQueue.contains(4));
        System.out.println("remove value 99: " + minQueue.remove(Integer.valueOf(99)));
        System.out.println("poll order: " + drain(minQueue));
        System.out.println("empty peek: " + minQueue.peek());
        System.out.println("empty poll: " + minQueue.poll());

        try {
            minQueue.element();
        } catch (NoSuchElementException ex) {
            System.out.println("empty element: " + ex.getClass().getSimpleName());
        }
        try {
            minQueue.remove();
        } catch (NoSuchElementException ex) {
            System.out.println("empty remove: " + ex.getClass().getSimpleName());
        }
        try {
            minQueue.offer(null);
        } catch (NullPointerException ex) {
            System.out.println("null offer: " + ex.getClass().getSimpleName());
        }

        PriorityQueue<Integer> maxQueue =
                new PriorityQueue<>(Comparator.reverseOrder());
        maxQueue.addAll(List.of(5, 1, 4, 2, 3));
        System.out.println("reverse-order peek: " + maxQueue.peek());
        System.out.println("reverse-order poll: " + drain(maxQueue));
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 PriorityQueueBasicsDemo.java
java PriorityQueueBasicsDemo
```

Exact stdout:

```text
size: 6
peek: 1
size after peek: 6
ordered copy: [1, 1, 2, 3, 4, 5]
original size: 6
remove value 4: true
contains 4: false
remove value 99: false
poll order: [1, 1, 2, 3, 5]
empty peek: null
empty poll: null
empty element: NoSuchElementException
empty remove: NoSuchElementException
null offer: NullPointerException
reverse-order peek: 5
reverse-order poll: [5, 4, 3, 2, 1]
```

Outputs to be able to explain:

- The initial capacity is 2, yet six elements were added. Both occurrences of 1 are retained.
- `peek()` returns 1 without reducing the size.
- Draining the copy with `poll()` produces ascending order; the original queue still has six elements.
- `remove(Integer.valueOf(4))` removes the value 4, not the head element and not index 4.
- When empty, the two pairs of inspect/remove-head methods differ in how they signal failure: `null` versus an exception.
- The reversed comparator puts 5 at the head and produces the poll order 5, 4, 3, 2, 1.

The programs in this lesson are compiled with `--release 17` and run on OpenJDK 24.0.2. This flag checks the code against the Java 17 language/API and generates corresponding bytecode; the JVM used to run the examples is still the version noted.

## 9. Limitations Stemming from the Heap Invariant

A heap only knows for certain which element is at the head according to the comparison rule. Therefore, `iterator()` is not equivalent to repeated `poll()`; to inspect the full ordering while preserving the source queue, you can drain a copy or sort a list using the same comparator.

A heap also has no value-based search path like a binary search tree: `contains(Object)` and `remove(Object)` must first search for the element using `equals`. Two elements with `compare(a,b) == 0` can still coexist; tied priority does not imply FIFO by default.

Finally, an established ordering is not automatically rebuilt if a field read by the comparator is mutated directly. When changing a priority key, the application must organize a controlled remove/update/re-insert step or build a new structure. Dedicated lessons on Comparator, search/removal, iterators, ties, and mutable keys analyze each of these limitations in detail.
## 10. When Should You Choose a Priority Queue?

### 10.1. Suitable for Repeatedly Picking the Current Best Element

Typical scenarios take the form:

- Repeatedly picking the event with the earliest timestamp among pending events.
- Repeatedly picking the job with the earliest deadline or lowest cost by convention.
- Maintaining a pool of candidates and frequently retrieving the top-ranked candidate.
- Inside an algorithm, new elements appear interleaved with retrieving the current priority element.

The common thread is that the data changes and the application needs the priority head repeatedly. The entire sorted list is not needed every time.

If you only have a fixed batch of data and need to output everything in order once, sorting a list may be simpler to understand. If you need retrieval in exact arrival order, use an appropriate FIFO queue. If you need to search for an arbitrary value or run frequent range queries, the heap property alone does not satisfy those requirements efficiently.

### 10.2. Single-Ended Priority Limitation

A min-heap enables fast inspection of the smallest element; it does not simultaneously place the largest element at a fixed public position. There is no `getLast()` to retrieve the "lowest-priority" element merely because the structure is named queue.

With `Comparator.reverseOrder()`, the largest element by natural order is placed at the head, but then the smallest element by natural order is no longer at the head. Choose the direction according to the primary question of the application.

### 10.3. Concurrent Access Is a Separate Requirement

`PriorityQueue` is not synchronized. If multiple threads access it concurrently and at least one thread modifies the data, synchronization or a concurrent data structure suited to the requirement is needed. A correct comparator does not make queue operations thread-safe.

This is a boundary to recognize when moving from single-threaded algorithmic examples to real applications. One should not infer blocking, thread-wakeup, or task-execution properties from the heap structure.

## 11. Checklist When Analyzing a Heap

| Question | How to Self-Check |
| --- | --- |
| Is the root truly the highest priority? | Check the parent–child relationship along each branch under the active comparator |
| Must the heap array be ascending? | Not required; only the heap invariant and complete tree shape are needed |
| How does adding a new value repair the heap? | Place at the end, then sift up along the path to the root |
| How does removing the root repair the heap? | Move the last element to the root, then sift down with the higher-priority child |
| Why are heap repair operations typically O(log n)? | The height of a complete binary heap grows logarithmically with element count |
| Why is peek typically O(1)? | The head element is already maintained at the root; peek does not re-sort |

Do not write tests that require a specific internal heap array across all JDKs. Check the head element, the set of remaining elements, and the order of `poll()` results when the comparison rule distinguishes them.
## 12. Exercises on the Heap Invariant (With Solutions)

**Exercise 1.** Is `[2, 5, 3, 9, 6, 8]` a valid min-heap, and is it in ascending order?

**Solution:** Valid because each parent is no greater than its children; not in ascending order because 5 precedes 3. A heap is not a sorted sequence.

**Exercise 2.** Where does `[2, 5, 1, 9, 6, 8]` violate the invariant?

**Solution:** Root 2 is greater than its right child 1; a single invalid edge is enough to conclude the invariant is broken.

**Exercise 3.** Given the heap `[2, 5, 3, 9, 6, 8]`, add 1 and then remove the head. What is the model array after each repair?

**Solution:** Sift-up produces `[1, 5, 2, 9, 6, 8, 3]`; removing 1, replacing it with 3, and sifting down produces `[2, 5, 3, 9, 6, 8]`. This is a trace of the chosen model, not an internal array contract.

**Exercise 4.** Why does knowing the root is the smallest not imply `contains(8)` runs in O(log n)?

**Solution:** The parent–child invariant does not indicate which branch holds 8; branches are not partitioned by value like a search tree. The worst case must check linearly.
## 13. Reference Materials

- [Java 17 PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html): class and method contracts.
- [Java 17 Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): comparison rules, reversal, and criterion composition.
- [PriorityQueue in OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java): reference for binary heap organization and structure-maintenance steps.

The key takeaways to keep in mind when using it are: the comparator decides who comes first; the heap maintains enough relationships to keep the priority head at the root; and repeated head-removal operations produce the priority order one by one. Do not replace the head-removal step with an assumption that all internal data is already sorted.
