# Why the Iterator Does Not Traverse in Priority Order

## 1. Two Different Meanings of "Next Element"

An application stores tasks in a `PriorityQueue` and needs to display the list in priority order. A developer writes a `for` loop, sees a lower-priority element appear before a higher-priority one, and suspects the queue is broken.

The issue usually lies in the expectation placed on iteration.

In `PriorityQueue`:

- **The next element retrieved by `poll()`** is the head of the queue according to the priority rule.
- **The next element returned by `Iterator.next()`** is the next element in the traversal; the API does not guarantee that it has the highest priority among the remaining unvisited elements.

An iterator is not a `poll()` loop hidden under the hood. One reads the elements; the other removes the head and repairs the structure so the new head remains valid.

After this lesson, you should be able to explain the root cause of that difference, recognize coding patterns that do not sort automatically, and choose a priority-ordered view with the appropriate impact on the underlying data.

## 2. What Does PriorityQueue Guarantee?

### 2.1. Guarantee at the Head of the Queue

Under the natural ordering of `Integer`, smaller numbers come first. If the queue contains 12, 4, 9, 1, 7, 3, 6, then `peek()` returns 1. Draining it with `poll()` yields the values in this order:

```text
1, 3, 4, 6, 7, 9, 12
```

If a reversed comparator is used, larger values can come first. "Higher priority" must always be interpreted according to the active comparator or natural ordering.

`peek()` inspects the head without removing it. `poll()` removes the head and modifies the queue. These are the operations directly tied to the head-selection rule.

### 2.2. No Equivalent Guarantee for Full Traversal

The `PriorityQueue` documentation explicitly states that the iterator is not guaranteed to return elements in any particular order. The spliterator and traversal methods based on it also provide no priority-order guarantee. See [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html#iterator()).

This does not mean the iterator is allowed to arbitrarily skip elements or invent new ones. During a normal read traversal, when the queue is not modified, the iterator visits the occurrences currently held in the queue. What is not promised here is **the order among those occurrences**.

Nor should you assume that the iterator always returns insertion order, always returns ascending order, or always has a fixed layout across implementation versions.

"No guaranteed order" does not mean "every traversal must be random." A program may observe the same order repeatedly. Observed repetition does not become an API contract.

## 3. Structural Cause: A Heap Only Maintains Per-Branch Order

### 3.1. Having the Smallest Root Does Not Make the Whole Array Sorted

A valid min-heap model:

```text
             1
           /   \
          4     3
         / \   / \
        12  7 9   6
```

The key invariant is that each parent node is no greater than its child nodes:

```text
1 ≤ 4 and 1 ≤ 3
4 ≤ 12 and 4 ≤ 7
3 ≤ 9 and 3 ≤ 6
```

By transitivity of ordering, 1 is no greater than any element beneath it. Thus, the heap has enough information to know that the smallest element is at the root.

However, there is no requirement that the left child 4 be smaller than the right child 3. Nor is there any requirement forcing leaf 7 in the left subtree to precede leaf 6 in the right subtree by value.

### 3.2. Reading by Storage Position Is Not Reading by Priority Rank

A binary heap can be represented as a level-order array:

```text
Index:     0  1  2   3  4  5  6
Value:    [1, 4, 3, 12, 7, 9, 6]
```

If you read the array from left to right, immediately after 1 you encounter 4, even though 3 has higher priority than 4. That single counterexample is enough to show:

```text
valid heap property
    does not imply
ascending order of the entire read sequence
```

The diagram and array above explain the mechanism. The heap array is not a public indexed API of `PriorityQueue`, and a specific layout is not a required output of the iterator.

### 3.3. A Single Pass Does Not Automatically Pick the Best Across All Branches

To read in priority order, after selecting the root 1, you must determine the best remaining element across the branches. Simply advancing the index to element 4 does not perform that decision.

A min-heap is designed to update the head efficiently after insertions and removals, rather than maintaining all data as a sorted list. If the iterator were required to return everything in priority order, it would have to do extra work such as maintaining an auxiliary structure or sorting a copy. The current iterator contract does not require that work.

In OpenJDK 17u, a normal read-only iterator traversal walks the positions of the heap array. The class also handles removal via the iterator separately; therefore, you should not generalize a description of the normal read path into a formula that applies to every modifying traversal. You can check the [iterator class in the OpenJDK 17u PriorityQueue source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java).

## 4. Why Does Repeatedly Polling Produce Priority Order?

With the heap model above, removing 1 is not as simple as skipping past the first slot of the array.

One way to maintain the heap performs these steps:

1. Keep 1 as the result.
2. Move the last element, 6, to the root and vacate the old last position.
3. Compare and sift 6 down to a valid position.
4. Place the appropriate element at the new root.

Intermediate state and post-repair state:

```text
Before polling:                 [1, 4, 3, 12, 7, 9, 6]
Move last element to root:      [6, 4, 3, 12, 7, 9]
Restore parent-child invariant: [3, 4, 6, 12, 7, 9]
```

Afterward, the element selected for the next `poll()` call is 3. Polling again repairs the heap so that 4 becomes the head.

| Operation | Finds current priority head? | Removes the element? | Repairs the heap after removal? |
| --- | --- | --- | --- |
| `peek()` | Inspects the existing head | No | Not needed since read-only |
| `poll()` | Yes | Yes | Yes, when elements remain |
| `Iterator.next()` | No priority-selection contract | No | Does not perform head removal |

It is precisely this combination of "remove the head, then repair the structure" that produces the priority sequence when looping `poll()`. The iterator does neither of those two steps, so it does not share the same guarantee.

This guarantee assumes that the comparison rule and priority keys are not mutated arbitrarily while elements remain in the queue. If mutating keys directly breaks the heap invariant, the resulting output cannot be used to evaluate normal traversal rules.

## 5. Observation Program: Same Data, Two Different Orders

Save the following code to **PriorityIterationObservation.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;

public class PriorityIterationObservation {
    private static List<Integer> pollAll(PriorityQueue<Integer> queue) {
        List<Integer> result = new ArrayList<>();
        Integer value;
        while ((value = queue.poll()) != null) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(12, 4, 9, 1, 7, 3, 6);
        PriorityQueue<Integer> queue = new PriorityQueue<>();
        queue.addAll(input);

        System.out.println("insertion order: " + input);
        System.out.println("head before iteration: " + queue.peek());

        List<Integer> visited = new ArrayList<>();
        Iterator<Integer> iterator = queue.iterator();
        while (iterator.hasNext()) {
            visited.add(iterator.next());
        }
        System.out.println("observed iterator order: " + visited);
        System.out.println("size after iteration: " + queue.size());
        System.out.println("head after iteration: " + queue.peek());

        List<Integer> sortedVisited = new ArrayList<>(visited);
        Collections.sort(sortedVisited);
        List<Integer> sortedInput = new ArrayList<>(input);
        Collections.sort(sortedInput);
        System.out.println("same elements: " + sortedVisited.equals(sortedInput));

        PriorityQueue<Integer> copy = new PriorityQueue<>(queue);
        System.out.println("poll order on copy: " + pollAll(copy));
        System.out.println("original size after copy: " + queue.size());
        System.out.println("poll order on original: " + pollAll(queue));
        System.out.println("original size after polling: " + queue.size());

        Iterator<Integer> empty = queue.iterator();
        System.out.println("empty iterator hasNext: " + empty.hasNext());
        try {
            empty.next();
        } catch (NoSuchElementException ex) {
            System.out.println("empty iterator next: " + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 PriorityIterationObservation.java
java PriorityIterationObservation
```

The program was compiled with `--release 17` and run on OpenJDK 24.0.2. Exact stdout observed during the test run:

```text
insertion order: [12, 4, 9, 1, 7, 3, 6]
head before iteration: 1
observed iterator order: [1, 4, 3, 12, 7, 9, 6]
size after iteration: 7
head after iteration: 1
same elements: true
poll order on copy: [1, 3, 4, 6, 7, 9, 12]
original size after copy: 7
poll order on original: [1, 3, 4, 6, 7, 9, 12]
original size after polling: 0
empty iterator hasNext: false
empty iterator next: NoSuchElementException
```

The `observed iterator order` line is the observed result in the stated environment, **not an order that every Java 17+ runtime must produce**. The `--release 17` flag checks usage of the target language/API and generates matching bytecode; it does not turn the running JVM into Java 17.

Key takeaways:

- The insertion order starts with 12, yet the head is 1.
- In the observed output, the iterator returns 4 before 3 and 12 before 7. That sequence is not sorted by priority.
- Both size and head remain unchanged after a read-only iterator pass.
- Sorting the visited elements matches the sorted input: the iterator still reads all the data.
- Polling everything from a copy produces priority order without shrinking the original queue.
- Polling everything from the original also produces that order, but leaves the queue empty.
- An empty iterator returns `false` from `hasNext()`; calling `next()` when no elements remain throws `NoSuchElementException`, rather than returning `null`.

The `pollAll` helper uses `null` as a sentinel because `PriorityQueue` forbids `null` elements. Do not generalize this stopping condition blindly to every collection or iterator type.

## 6. Forms That Look Different but Do Not Sort Automatically

### 6.1. Enhanced-for Only Hides the Iterator Call

The following snippet illustrates a traversal:

```java
// queue is a PriorityQueue<Integer> that already contains data.
for (Integer value : queue) {
    System.out.println(value);
}
```

Enhanced-for does not translate into a priority-head polling algorithm. For an `Iterable` object such as a queue, it uses the iterator to step through the elements.

Therefore, switching from a `while (iterator.hasNext())` loop to a `for` loop does not satisfy a requirement to display elements in ascending order.

### 6.2. forEach, toArray, and toString Are Also Not Enough

| Reading approach | Automatically sorts by priority? |
| --- | --- |
| `queue.iterator()` | No |
| `for (E e : queue)` | No |
| `queue.forEach(action)` | No |
| `queue.toArray()` | No |
| `new ArrayList<>(queue)` | No |
| `System.out.println(queue)` | No |
| `queue.stream().toList()` | No |

"No" in the table means there is no priority-sorting step and no priority-sorting contract. The output may still happen to look right on some inputs.

Moving data into another container type does not automatically attach an ordering rule. If the UI requires a sorted list, there must be an explicit sorting step or a clear priority-polling approach.

### 6.3. forEachOrdered Is Not an Alias for sorted

In streams, `forEachOrdered` preserves the stream's encounter order when the stream has a defined encounter order. It does not inspect the `PriorityQueue`'s comparator and sort the elements.

Because this queue source does not promise a priority-based encounter order, calling:

```java
// Does not add a priority-order guarantee:
queue.stream().forEachOrdered(System.out::println);
```

does not solve the requirement. If sorting is needed, use `sorted(comparator)`. If combining with a parallel stream and printing in order after sorting, use a terminal operation that respects that order.

These semantics are described in the [Java 17 Stream documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).

## 7. Three Correct Ways to View in Priority Order While Preserving the Original

### 7.1. Copy the PriorityQueue and Poll the Copy

A utility method you can place in an application class:

```java
static <E> List<E> orderedByPolling(PriorityQueue<E> source) {
    PriorityQueue<E> copy = new PriorityQueue<>(source);
    List<E> result = new ArrayList<>();
    while (!copy.isEmpty()) {
        result.add(copy.poll());
    }
    return result;
}
```

This is an illustrative method requiring imports for `List`, `ArrayList`, and `PriorityQueue`; the complete program below includes an equivalent variant.

The constructor taking a `PriorityQueue` preserves the source's comparison rule. The `poll()` loop acts on the copy, so the source queue structure is not drained.

This approach directly answers the question: "If I repeatedly take the head, what will the order be?" It is especially intuitive when you only want to view the top few priority elements rather than all of them.

### 7.2. Copy to a List and Sort with the Same Comparator

If the active comparator `order` is already known:

```java
// Illustrative snippet; queue, order, and the Task type are already defined.
List<Task> ordered = new ArrayList<>(queue);
ordered.sort(order);
```

A separate list lets you sort without removing data from the queue. Keep the business comparator as a reusable value rather than writing a similar rule in multiple places and letting them drift apart.

For a `PriorityQueue<Integer>` using natural ordering, you can use:

```java
List<Integer> ordered = new ArrayList<>(queue);
ordered.sort(Comparator.naturalOrder());
```

The two snippets above are separate contexts; do not declare both `ordered` variables in the same scope.

### 7.3. Stream with an Explicit sorted Step

With an explicit comparator:

```java
List<Task> ordered = queue.stream()
        .sorted(order)
        .toList();
```

`sorted(order)` is the step that requests ordering. `toList()` collects the results; it does not read the comparator from the queue.

If you call `sorted()` with no arguments, Java uses natural ordering. This can differ from the queue's rule:

```java
// Illustrative snippet:
PriorityQueue<Integer> highestFirst =
        new PriorityQueue<>(Comparator.reverseOrder());
highestFirst.addAll(List.of(8, 1, 5));

List<Integer> natural = highestFirst.stream().sorted().toList();
List<Integer> priority = highestFirst.stream()
        .sorted(Comparator.reverseOrder())
        .toList();

// natural  is [1, 5, 8]
// priority is [8, 5, 1]
// highestFirst.peek() is still 8
```

An object type that does not implement `Comparable` can even throw a `ClassCastException` if natural sorting is requested instead of supplying an appropriate comparator.

### 7.4. If Retrieving the Comparator from the Queue, Handle null

`queue.comparator()` returns `null` when the queue uses natural ordering. Do not pass this value directly to `stream.sorted(comparator)`: that stream method requires a non-null comparator.

A safe, readable approach is to branch based on the element type context or keep an explicit comparator around from when the queue was created. Copying the `PriorityQueue` and calling `poll()` also avoids having to re-implement the logic that chooses between natural ordering and a custom comparator.

With `List.sort(null)`, by contrast, the contract is to use natural ordering; see [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)). Do not generalize the meaning of `null` across APIs just because both perform sorting.

## 8. Runnable Program: Three Approaches Yielding the Same Result

Save as **PriorityOrderedViews.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class PriorityOrderedViews {
    record Task(String label, int rank, long ticket) {
        @Override
        public String toString() {
            return label + ":" + rank + ":" + ticket;
        }
    }

    private static <E> List<E> pollCopy(PriorityQueue<E> source) {
        PriorityQueue<E> copy = new PriorityQueue<>(source);
        List<E> ordered = new ArrayList<>();
        E value;
        while ((value = copy.poll()) != null) {
            ordered.add(value);
        }
        return ordered;
    }

    public static void main(String[] args) {
        Comparator<Task> order =
                Comparator.comparingInt(Task::rank)
                          .reversed()
                          .thenComparingLong(Task::ticket);
        PriorityQueue<Task> queue = new PriorityQueue<>(order);
        queue.addAll(List.of(
                new Task("report", 2, 0),
                new Task("alert", 9, 1),
                new Task("repair", 9, 2),
                new Task("backup", 4, 3)));

        List<Task> byPolling = pollCopy(queue);
        List<Task> bySorting = new ArrayList<>(queue);
        bySorting.sort(order);
        List<Task> byStream = queue.stream().sorted(order).toList();

        System.out.println("copy plus poll: " + byPolling);
        System.out.println("list plus sort: " + bySorting);
        System.out.println("stream plus sorted: " + byStream);
        System.out.println("all equal: "
                + (byPolling.equals(bySorting) && bySorting.equals(byStream)));
        System.out.println("source size: " + queue.size());
        System.out.println("source head: " + queue.peek());

        PriorityQueue<Integer> duplicates =
                new PriorityQueue<>(List.of(5, 2, 5, 1));
        System.out.println("duplicates preserved: " + pollCopy(duplicates));
        System.out.println("duplicate source size: " + duplicates.size());
    }
}
```

Run commands:

```shell
javac --release 17 -encoding UTF-8 PriorityOrderedViews.java
java PriorityOrderedViews
```

Exact stdout:

```text
copy plus poll: [alert:9:1, repair:9:2, backup:4:3, report:2:0]
list plus sort: [alert:9:1, repair:9:2, backup:4:3, report:2:0]
stream plus sorted: [alert:9:1, repair:9:2, backup:4:3, report:2:0]
all equal: true
source size: 4
source head: alert:9:1
duplicates preserved: [1, 2, 5, 5]
duplicate source size: 4
```

Here the convention is that a higher `rank` comes first. If ranks tie, a smaller `ticket` comes first. Thus `alert` precedes `repair`, followed by `backup` and `report`.

All three approaches return the same result because they use an ordering that fully distinguishes the sample tasks:

1. The `PriorityQueue` copy retains the source comparator and polls the head.
2. The separate list is sorted using the `order` comparator.
3. The stream applies `sorted(order)`.

All three only read the source structure. The size remains 4 and the head remains `alert`. The numeric example at the end preserves both 5s; no step converts the data into a set and drops duplicate occurrences.

`Stream.toList()` has been available since before Java 17 (introduced in Java 16), so it works in this lesson. The list returned by that method does not support structural modification, whereas the two lists created with `ArrayList` in the program are modifiable. That difference does not affect the content comparison being performed.

## 9. Priority Ties: Valid Sorting Can Still Differ in Identity Order

### 9.1. A Comparator Returning 0 Does Not Create a First-Come Rule

Suppose a comparator only inspects the priority level. A and B both have level 1. When polling the head, either is valid to be chosen before a level-2 element, but there is no guarantee that A will be polled before B just because A was added first.

Sorting a list copy does not restore insertion history either. Even a stable sort can only preserve the input order of tied elements; the input copied from the iterator already had no arrival-order guarantee.

Do not rely on sort stability to infer FIFO behavior for `PriorityQueue`.

### 9.2. Tie-Breakers Must Be Real Data

If FIFO ordering is needed within each priority group, assign a sequence number upon arrival and include it in the comparator, like the `ticket` field in the program:

```java
Comparator.comparingInt(Task::rank)
          .reversed()
          .thenComparingLong(Task::ticket)
```

This expression is written in the context of the `Task` type defined earlier. The sequence number must accurately express the application's rule and sufficiently distinguish the elements to be ordered. If both `rank` and `ticket` still tie, the ordering between those elements remains unresolved.

The uniqueness of `ticket` in the example is provided by the application, not an inherent property of `PriorityQueue`.

### 9.3. Do Not Use TreeSet Just to Produce a Sorted Printout

Converting to a `TreeSet` can drop elements that the comparator considers equivalent. Given numeric data `[5, 2, 5, 1]`, a sorted list keeps `[1, 2, 5, 5]`; a set keeps only a single 5.

If the requirement is to view every task and every occurrence, choose a result structure that preserves them. Being "ordered" is not enough if the conversion operation also alters the element count.

## 10. Choosing an Approach by Cost and Data Impact

The following table assumes n elements, a constant-time comparator, and no concurrent modification during reading:

| Need | Suitable approach | Impact on original | Primary cost |
| --- | --- | --- | --- |
| Visit every element, order not needed | Iterator | Preserved if read-only | O(n) |
| Inspect only the highest-priority element | `peek()` | Preserved | O(1) |
| Consume all in priority order for processing | `poll()` loop | Drained | O(n log n) |
| View all in priority order | Copy then `poll()` | Preserved | O(n log n), extra memory |
| View all in priority order as a list | Copy then `sort` | Preserved | O(n log n), extra memory |
| View the top k elements | Copy then poll up to k times | Preserved | Copy cost plus poll steps |

In typical OpenJDK implementations, copying a queue of n elements takes O(n) time and memory; polling k elements afterward takes O(k log n). Therefore, do not call the entire "copy then poll k" approach O(k log n) while ignoring the copy step.

A read-only iterator loop does not need to allocate a list holding all n elements. If you want to compute a sum, count items, or search by a predicate without needing order, do not force sorting just because the data happens to live in a `PriorityQueue`.

Conversely, a UI displaying items by priority must include an explicit ordering step; do not "optimize" by dropping the requirement and using an iterator.

### Taking Only the First Few Elements from a Copy

Illustrative snippet where `queue` is a populated `PriorityQueue<Integer>` and `k` is non-negative:

```java
PriorityQueue<Integer> copy = new PriorityQueue<>(queue);
List<Integer> first = new ArrayList<>();

for (int count = 0; count < k && !copy.isEmpty(); count++) {
    first.add(copy.poll());
}
```

Do not write `queue.stream().limit(k)` and assume those are the k highest-priority elements. `limit` does not sort the source before selecting.

## 11. A Read-Only Iterator Is Not an Independent Snapshot

### 11.1. Do Not Mix next with poll on the Same Queue

An error-prone example:

```java
// Incorrect example of modifying the source while iterating:
Iterator<Integer> iterator = queue.iterator();
while (iterator.hasNext()) {
    System.out.println(iterator.next());
    queue.poll();
}
```

An iterator does not mean "read an element, remove the head, and automatically turn into a priority traversal." Modifying the source outside the iterator breaks normal traversal usage. You may encounter `ConcurrentModificationException`; do not rely on whether an exception happens to be thrown in a given run to judge the code as correct.

If you want to consume in priority order, use a separate `poll()` loop. If you want to conditionally remove elements while iterating, use the removal mechanism supported by the iterator and understand that it still does not produce priority order.

According to the [Iterator contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html#remove()), the iterator's `remove()` deletes the element most recently returned by `next()`; it does not mean "remove the priority head." For an iterator that supports removal, each successful `next()` allows at most one corresponding removal.

### 11.2. Structural Copies Still Share Element Objects

`new PriorityQueue<>(queue)`, `new ArrayList<>(queue)`, and the stream in the examples retain references to the element objects. They do not automatically deep-copy those objects.

Adding or removing elements in the copy does not add or remove them in the source structure. However, mutating a mutable object referenced by both can still be observed from both places. In particular, mutating a priority key can invalidate ordering assumptions.

The sample `Task` records use primitive fields and `String` to keep comparison keys immutable.

### 11.3. Copying Does Not Solve Concurrent Access by Itself

`PriorityQueue` is not thread-safe for concurrent access when a thread modifies it without proper synchronization. A single line creating a copy does not automatically take an atomic snapshot of a source being mutated concurrently.

In a concurrent application, you must first determine how to obtain a valid read according to your synchronization design or the concurrent data structure in use. Only then should you choose a sorting or display strategy. The examples in this lesson run on a single thread with data that is not modified externally.

## 12. Test Against the Contract Instead of Hardcoding Heap Layout

### 12.1. Testing a Read-Only Iterator Pass

You can verify these properties:

- The expected number of occurrences is read.
- The values and per-value counts match the source.
- Size and head remain unchanged after read-only traversal.
- The iterator exhausts at the right time; calling `next()` afterward throws the contracted exception.

Do not write production tests that assert a specific iterator sequence such as `[1, 4, 3, ...]` simply because that sequence was observed on your machine. Such tests couple to layout details rather than business requirements.

In the observation example, stdout prints the actual sequence to demonstrate a counterexample. It is not a recommendation to treat that sequence as a cross-version contract.

### 12.2. Testing a Priority-Ordered List

When testing a method that builds a priority-ordered list, verify all of the following together:

1. The list contains all occurrences.
2. No adjacent pair violates the comparator.
3. The source is preserved if the contract is read-only.
4. Tie-breaking rules are specified if business logic requires a specific identity order.

Do not convert both sides to a `Set` to check "same elements," because that discards occurrence counts. Sorting both lists or using an appropriate frequency map preserves that information.

If the comparator only inspects part of the data and allows ties, do not require every valid implementation to return the exact same identity order. If you want to assert one exact order as in the `Task` program, include a sufficiently distinguishing tie-breaker first.

## 13. Common Mistakes and Fixes

| Symptom | Wrong assumption | How to fix |
| --- | --- | --- |
| Iterator returns 4 before 3 | The queue must be broken | Check the head and understand the heap invariant |
| `for` loop is not ascending | Switching to `forEach` will fix it | Add a sort step or poll from a copy |
| Printing `queue` looks jumbled | `toString` should print in priority order | Treat it as displaying contents with no sort contract |
| `toArray` is still not ascending | Converting to an array sorts automatically | Sort the array or list with the appropriate rule |
| `forEachOrdered` is not in priority order | "Ordered" means it uses the comparator | Use `sorted` with an explicit comparator |
| Larger-first queue streams smaller-first | `sorted()` uses the queue's order | `sorted()` defaults to natural ordering |
| Displaying items loses pending work | Polling the original when only viewing | Poll a copy or sort a separate list |
| Two tied tasks swap positions | A stable sort restores FIFO | Add an arrival sequence number to the comparator |
| Some tasks vanish after conversion | Using `TreeSet` to sort all occurrences | Use a duplicate-preserving result like `List` |
| Mixing iterator with `poll` errors | Thinking iterator syncs with head polling | Separate the read pass from the consuming pass |

## 14. Self-Check Exercises with Solutions

### Exercise 1: Heap or Sorted List?

A heap has the model array `[1, 4, 3, 12, 7, 9, 6]`. Why is 4 appearing before 3 still valid?

**Solution:** 4 and 3 are the two children of 1. A min-heap only requires 1 to be no greater than each child; it does not require the left child to be smaller than the right child. Reading the array by index can therefore encounter 4 before 3.

### Exercise 2: next and poll

An integer queue uses natural ordering. Both an iterator loop and a `poll` loop read seven values. Which loop must produce a non-decreasing sequence? What is the state of the queue after each loop?

**Solution:** The `poll` loop produces a non-decreasing sequence and empties the queue. The read-only iterator loop leaves the queue intact, but has no guarantee of a non-decreasing sequence. Both loops can read all elements while differing in both order and data impact.

### Exercise 3: The First Two Elements

You want to view the two highest-priority tasks while preserving the source. Can you use `queue.stream().limit(2).toList()`?

**Solution:** That approach does not request priority sorting, so it is not guaranteed to pick the right two elements. You can copy the `PriorityQueue` and poll up to twice, or call `sorted` with the comparator before `limit`. Both the copy cost and sorting cost must be considered.

### Exercise 4: Reversed Comparator

A queue contains 8, 1, 5 and uses `Comparator.reverseOrder()`. What does `queue.stream().sorted().toList()` return? Does it match the `poll` order?

**Solution:** `sorted()` uses natural ordering, so it returns `[1, 5, 8]`. Polling according to the queue's rule returns `[8, 5, 1]`. Use `sorted` with the reversed comparator if you want the same priority order.

### Exercise 5: Priority Ties and Stability

A and B have the same priority. A list is created from the iterator and then sorted with a stable sort. Does that prove A, which arrived first, will precede B?

**Solution:** No. A stable sort preserves the input order among tied elements, but the iterator order does not guarantee insertion history. You need arrival-order data and an appropriate tie-breaking criterion.

### Exercise 6: Preserving Occurrences

A queue contains `[5, 2, 5, 1]` based on its current values. Both `[1, 2, 5]` and `[1, 2, 5, 5]` are sorted. Which result is the complete, correct view?

**Solution:** `[1, 2, 5, 5]`. The view must preserve both occurrences of 5. A sorted result that drops data still fails the requirement.

### Exercise 7: A Single Sorted Run

A small input causes the iterator to happen to return `[1, 2, 3]`. Can you omit the sorting step in the display feature?

**Solution:** No. One observation does not establish an ordering guarantee for other inputs or implementations. A feature that requires ordering must express it with an operation that provides the appropriate contract.

### Exercise 8: null Comparator

A queue uses natural ordering, so `queue.comparator()` is `null`. Is calling `queue.stream().sorted(queue.comparator())` a valid general approach?

**Solution:** No. The `sorted` overload that takes a comparator requires a non-null argument. Handle the natural-ordering case explicitly, or copy the `PriorityQueue` and poll from the copy.

## 15. References

- [PriorityQueue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html): distinguish the queue-head contract from the traversal contract.
- [OpenJDK 17u PriorityQueue Source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/PriorityQueue.java): inspect the heap layout and the normal iterator read path.
- [Iterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): read operations, exhaustion behavior, and removal rules.
- [Stream Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): distinguish `sorted`, `limit`, and `forEachOrdered`.

When you need priority order, choose an operation that actually produces that order. The name `PriorityQueue` guarantees how the head is selected; the iterator serves to walk the contents and does not perform a full priority-head traversal on its own.
