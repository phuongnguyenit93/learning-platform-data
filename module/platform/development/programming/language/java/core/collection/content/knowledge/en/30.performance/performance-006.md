# Avoid Traversing LinkedList with Indexed get

## 1. A loop with the right result can still be wrong in performance

The following snippet is very familiar when working with lists:

```java
long total = 0;
for (int i = 0; i < values.size(); i++) {
    total += values.get(i);
}
```

This is an illustrative snippet inside a method; `values` is assumed to be a list of integers that does not contain `null`.

If `values` is an `ArrayList`, accessing an element by index has constant cost, and a single traversal like this has linear cost in the number of elements. If `values` is a `LinkedList`, each `get(i)` call must locate the node at position `i`. Repeating that lookup for every index causes the total work to grow quadratically.

The issue is easy to miss because:

- The code still returns the exact result.
- Only a single loop is visible in the calling code.
- Small datasets may run fast enough to hide the flaw.
- Variables are often declared as `List`, making readers forget to check what concrete list type is actually used.

To traverse a `LinkedList` sequentially, use an appropriate `for-each` loop, `Iterator`, or `ListIterator`. These approaches retain the current position and advance along the links, rather than asking the list to relocate the position from the head or tail after every step.

## 2. Understanding the mechanism: an index is not a node address

### 2.1. Arrays and linked lists answer two different questions

With an array-based structure, knowing the index allows direct calculation of the slot holding the element. With a doubly linked list, each node holds an element along with references to the previous and next nodes:

```text
first                                              last
  |                                                  |
  v                                                  v
[10] <-> [20] <-> [30] <-> [40] <-> [50] <-> [60] <-> [70] <-> [80]
 0        1        2        3        4        5        6        7
```

The numbers `0..7` on the bottom row are logical positions. They do not form a lookup array from index to node.

`LinkedList` supports the `get(index)` API because it implements the `List` interface, but to retrieve the element at an arbitrary index, it must follow links. The existence of a method on an interface does not mean every implementation performs that method at the same cost.

The Java documentation clearly states that indexed operations on `LinkedList` traverse from the beginning or the end, choosing whichever is closer to the specified index. [Java 17 LinkedList Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

### 2.2. Starting from the closer end still does not yield constant-time access

Suppose the list has `n` elements and `0 <= i < n`. The number of link hops required to reach node `i` under this mechanism is:

```text
h(i) = min(i, n - 1 - i)
```

Adding a constant amount of work to validate the index and read the value, the cost of a single call can be described as:

```text
get(i): Θ(1 + min(i, n - 1 - i))
```

For example, with `n = 8`:

| Index `i` | Starting end | Link hops |
| --- | --- | --- |
| 0 | Head | 0 |
| 1 | Head | 1 |
| 2 | Head | 2 |
| 3 | Head | 3 |
| 4 | Tail | 3 |
| 5 | Tail | 2 |
| 6 | Tail | 1 |
| 7 | Tail | 0 |

`get(0)` and `get(n - 1)` take constant time. Positions near the middle require a number of steps proportional to `n`. Therefore, saying "every `get(i)` traverses all `n` nodes" is inaccurate; saying "arbitrary indexed access on a LinkedList has a linear worst case" is accurate.

More importantly, `get(4)` does not reuse the node that the preceding `get(3)` call just located. Every call locates the node anew from one end of the list. This is the crucial difference compared to an iterator. You can verify this lookup mechanism in the OpenJDK 17 source code, inside the internal `node(index)` method. [OpenJDK 17 LinkedList Source Code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java)

## 3. Why does a single for loop have quadratic total cost?

### 3.1. Summing the hidden work inside each get

Consider a loop that calls `get(0)`, `get(1)`, ..., `get(n - 1)` exactly once on a list that is not modified during traversal.

The total number of link hops is:

```text
H(n) = sum of min(i, n - 1 - i), for i from 0 to n - 1
```

For `n = 8`, the sum is:

```text
0 + 1 + 2 + 3 + 3 + 2 + 1 + 0 = 12
```

For larger numbers of elements:

- If `n = 2k`, the sum is `k(k - 1)`.
- If `n = 2k + 1`, the sum is `k²`.

Both cases can be written concisely as:

```text
H(n) = floor((n - 1)² / 4), for n >= 1
```

In addition to link hops, there are still `n` element reads and loop condition checks. The total traversal cost is:

```text
T(n) = Θ(n + H(n)) = Θ(n²)
```

This conclusion applies to a full indexed traversal loop, not a claim that every use of `LinkedList` is quadratic.

### 3.2. Reading the growth table

| Element count `n` | Number of `get(i)` calls | Total link hops `H(n)` |
| --- | --- | --- |
| 8 | 8 | 12 |
| 1,000 | 1,000 | 249,500 |
| 2,000 | 2,000 | 999,000 |
| 4,000 | 4,000 | 3,998,000 |
| 10,000 | 10,000 | 24,995,000 |

Doubling the list size causes the number of link hops to nearly quadruple. Starting from the closer end reduces the work compared to always starting from the head, but it does not change the order of growth.

The table counts steps according to the node-locating model, not nanoseconds, machine instructions, or actual memory accesses. It explains the algorithmic cause; it does not predict exact wall-clock times on every machine.

### 3.3. Hoisting size out of the loop does not solve the root problem

Changing the loop to:

```java
int n = values.size();
for (int i = 0; i < n; i++) {
    process(values.get(i));
}
```

does not make traversing a `LinkedList` linear. In this implementation, the size is already stored in a field; the dominant cost is locating the node in `get(i)`, not recounting the entire list in `size()`.

The snippet above is illustrative code; `process` represents the work done per element. If each processing step has a large cost of its own, the total runtime must include that part as well. However, the redundant node-locating work still exists and can be avoided.

## 4. Sequential traversal with an iterator

### 4.1. Only reading each element: use for-each

```java
long total = 0;
for (int value : values) {
    total += value;
}
```

For an object implementing `Iterable` such as `LinkedList`, the `for-each` loop traverses via an iterator. It does not compile into a sequence of `get(0)`, `get(1)`, ... calls like the indexed loop at the start of this article.

A linked list iterator holds a reference to the next node to be read. Each `next()` call retrieves the value and advances to the immediately following node. A single pass over `n` elements costs `Θ(n)`, assuming the work done per element is constant.

This is usually the clearest option when the algorithm only needs the values and does not need to modify the list structure during traversal.

### 4.2. Controlling the traversal: use an explicit Iterator

```java
long total = 0;
Iterator<Integer> iterator = values.iterator();
while (iterator.hasNext()) {
    total += iterator.next();
}
```

This illustrative snippet requires importing `java.util.Iterator` and assumes `values` does not contain `null` when performing addition by unboxing `Integer` to `int`.

The difference in mechanism:

```text
Traversing with get(i):
    request position 0 -> locate node
    request position 1 -> relocate node
    request position 2 -> relocate node
    ...

Traversing with an iterator:
    start at head of list
    read current node -> advance to next node
    read current node -> advance to next node
    ...
```

Retaining the current position is what saves work. Merely changing the syntax while still calling `get(i)` inside the body fails to achieve that goal.

### 4.3. Needing an ordinal index: increment a counter alongside the iterator

You do not have to use indexed access just because the output needs a sequence number.

An illustrative example inside a method that does not modify the list structure during the loop:

```java
int index = 0;
for (String value : names) {
    System.out.println(index + ": " + value);
    index++;
}
```

The `index` variable tracks the current traversal order; it is not used to look up the element. As a result, this remains a linear pass over a `LinkedList`.

If the algorithm needs cursor positions or bidirectional traversal, `ListIterator` provides those operations directly.

## 5. Reverse traversal and updates with ListIterator

### 5.1. Reverse traversal should not call get with a decrementing index either

This loop still has quadratic total cost on a `LinkedList`:

```java
for (int i = values.size() - 1; i >= 0; i--) {
    process(values.get(i));
}
```

It merely reverses the order of the very same node lookups. Using a `ListIterator` positioned at the end preserves the cursor position while moving backward:

```java
ListIterator<Integer> iterator = values.listIterator(values.size());
while (iterator.hasPrevious()) {
    int value = iterator.previous();
    process(value);
}
```

Alternatively, when the variable is typed as `LinkedList` or `Deque`, you can use `descendingIterator()` for reverse traversal. Choose the API that fits the declared type of your method rather than casting just to write a shorter expression.

### 5.2. Create the iterator once and keep advancing

A `ListIterator` maintains a cursor positioned between elements, allowing `next()`, `previous()`, and querying the index relative to the cursor position. `set()` modifies the element last returned by `next()` or `previous()`, according to the API contract. [Java 17 ListIterator Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html)

Example of updating every value in a modifiable list:

```java
ListIterator<Integer> iterator = values.listIterator();
while (iterator.hasNext()) {
    int current = iterator.next();
    iterator.set(current * 10);
}
```

Traversing once and updating right at the already located node avoids the following pattern:

```java
for (int i = 0; i < values.size(); i++) {
    values.set(i, values.get(i) * 10);
}
```

In the indexed pattern, both `get(i)` and `set(i, ...)` must locate the node. Two lookups per index still produce a quadratic total.

You should also avoid recreating `values.listIterator(i)` at every step. Initializing an iterator at an intermediate index may require walking to that position. Linear efficiency comes from **reusing the same iterator to move sequentially**, not from the `ListIterator` type name alone.

## 6. Complete runnable Java 17+ program

The following program serves three purposes:

1. Demonstrate that the different traversal approaches return the same sum.
2. Output the modeled node-locating hop counts instead of relying on noisy wall-clock timing measurements.
3. Illustrate reverse traversal and safe modification through the loop's own iterator.

Save as `LinkedListTraversalDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListTraversalDemo {
    private static long sumByIndex(List<Integer> values) {
        long total = 0;
        for (int i = 0; i < values.size(); i++) {
            total += values.get(i);
        }
        return total;
    }

    private static long sumByForEach(List<Integer> values) {
        long total = 0;
        for (int value : values) {
            total += value;
        }
        return total;
    }

    private static long sumByIterator(List<Integer> values) {
        long total = 0;
        Iterator<Integer> iterator = values.iterator();
        while (iterator.hasNext()) {
            total += iterator.next();
        }
        return total;
    }

    private static List<Integer> reverseValues(List<Integer> values) {
        List<Integer> result = new ArrayList<>();
        ListIterator<Integer> iterator = values.listIterator(values.size());
        while (iterator.hasPrevious()) {
            result.add(iterator.previous());
        }
        return result;
    }

    private static long modeledIndexHops(int size) {
        long hops = 0;
        for (int i = 0; i < size; i++) {
            hops += Math.min(i, size - 1 - i);
        }
        return hops;
    }

    public static void main(String[] args) {
        List<Integer> values = new LinkedList<>(
                List.of(10, 20, 30, 40, 50, 60, 70, 80));
        System.out.println("input = " + values);
        System.out.println("sum by index = " + sumByIndex(values));
        System.out.println("sum by for-each = " + sumByForEach(values));
        System.out.println("sum by iterator = " + sumByIterator(values));
        System.out.println("reverse = " + reverseValues(values));

        for (int size : new int[] {8, 1000, 2000, 4000}) {
            System.out.println("n=" + size
                    + ", modeled index hops=" + modeledIndexHops(size));
        }

        List<Integer> odds = new LinkedList<>(List.of(1, 2, 3, 4, 5, 6));
        Iterator<Integer> removalIterator = odds.iterator();
        while (removalIterator.hasNext()) {
            int value = removalIterator.next();
            if (value % 2 == 0) {
                removalIterator.remove();
            }
        }
        System.out.println("after removing even values = " + odds);

        ListIterator<Integer> updateIterator = odds.listIterator();
        while (updateIterator.hasNext()) {
            int value = updateIterator.next();
            updateIterator.set(value * 10);
        }
        System.out.println("after multiplying by ten = " + odds);
        System.out.println("input remains = " + values);
    }
}
```

Compile and run:

```shell
javac --release 17 LinkedListTraversalDemo.java
java LinkedListTraversalDemo
```

Stdout:

```text
input = [10, 20, 30, 40, 50, 60, 70, 80]
sum by index = 360
sum by for-each = 360
sum by iterator = 360
reverse = [80, 70, 60, 50, 40, 30, 20, 10]
n=8, modeled index hops=12
n=1000, modeled index hops=249500
n=2000, modeled index hops=999000
n=4000, modeled index hops=3998000
after removing even values = [1, 3, 5]
after multiplying by ten = [10, 30, 50]
input remains = [10, 20, 30, 40, 50, 60, 70, 80]
```

`modeledIndexHops()` sums the distances according to the model analyzed earlier; it does not instrument Java's internal nodes and does not measure time. The model-calculation function itself runs linearly in the `size` parameter, even though the number it computes represents the quadratic total work of another traversal method.

The three sum functions produce identical results on this dataset. The difference lies in the amount of work spent locating elements. A test that only asserts the sum equals `360` will not catch the performance problem in `sumByIndex()`.

## 7. Syntax changes that still keep the same bug

### 7.1. Streaming over a range of indices

This illustrative snippet still calls `get(i)` for every index:

```java
long total = IntStream.range(0, values.size())
        .mapToLong(i -> values.get(i))
        .sum();
```

It requires importing `java.util.stream.IntStream`. When `values` is a `LinkedList`, replacing `for` with an index stream does not change the cost of locating nodes. The total work remains quadratic.

If you only need to traverse the values, use a `for-each` loop or an element stream:

```java
long total = values.stream()
        .mapToLong(Integer::longValue)
        .sum();
```

A sequential element stream over `LinkedList` traverses the structure through the collection's own spliterator/iterator mechanism rather than generating a sequence of indexed lookups as in the first example. You do not need to use Stream just to get linear complexity; a `for-each` loop already achieves that.

Both sum examples assume there are no `null` elements. The fact that `LinkedList` permits storing `null` does not make integer unboxing accept `null`.

### 7.2. Keeping an index variable in for-each and calling get again

```java
int index = 0;
for (Integer ignored : values) {
    process(values.get(index++));
}
```

The snippet above already uses an iterator to read each element, but discards the received value and looks it up again by index. Process the loop element variable directly instead.

### 7.3. Calling indexOf on each value to obtain its ordinal position

If you call `values.indexOf(value)` on every iteration, each call launches a new search. The total work can become quadratic; furthermore, when duplicate elements exist, the returned index is always the first occurrence rather than necessarily the position currently being visited.

Use a counter variable or `ListIterator.nextIndex()` as appropriate for your goal instead of re-searching the index from the value.

## 8. Modifying a list during traversal: keep the right iterator and semantics

### 8.1. Reading with for-each does not grant permission to remove directly from the list

The following snippet is an example of a bug, not a recommended way to remove elements:

```java
for (Integer value : values) {
    if (value < 0) {
        values.remove(value);
    }
}
```

Removing directly through `values` mutates the list structure behind the back of the `for-each` loop's iterator. With `LinkedList`'s standard iterator, this can throw a `ConcurrentModificationException`. Fail-fast detection is on a best-effort basis; never treat "I haven't seen an exception yet" as proof that this traversal pattern is safe. [Java 17 LinkedList Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html)

When filtering in place with a loop, call `remove()` on the iterator itself after `next()` returns the element. The complete program above demonstrates this pattern. Do not call `remove()` twice for a single `next()` call.

Unlinking a node already reached by an iterator does not require relocating the index. Even so, do not generalize this into "every removal on a LinkedList is constant-time": removing by index or searching for a value to remove may still require traversal to locate the target node.

### 8.2. Reverse traversal is not the same as removing elements

A backward-moving `ListIterator` or `descendingIterator()` can read from tail to head while leaving the collection intact. If you use `removeFirst()`, `pollFirst()`, or similar retrieve-and-remove operations, the source structure is consumed.

Consuming elements from the front may suit a queue workload, but it is not an equivalent replacement for a read pass that preserves the list. When refactoring code for performance, you must preserve both the return value and the side effects on the source data.

### 8.3. Using an iterator does not make a collection thread-safe

The benefit discussed here is retaining cursor position during traversal under valid access conditions. It does not provide synchronization for a list being mutated concurrently by another thread. Concurrent data access must be handled separately rather than treating an iterator as a protective lock.

## 9. When to use ArrayList or create a copy?

### 9.1. Distinguish sequential traversal from random positional access

If an algorithm only needs a sequential read pass, changing the loop to `for-each` or an iterator is sufficient; you do not necessarily need to change the data structure.

If an algorithm frequently accesses arbitrary positions, such as repeated `get(randomIndex)` calls, choose a structure that supports fast indexed access. This is a decision based on access patterns, not a slogan that `LinkedList` is always good or always bad.

The `List` type does not promise constant-time positional access for every implementation. The `RandomAccess` marker interface helps generic algorithms recognize lists that support fast random access and choose an appropriate strategy. `ArrayList` implements this interface, whereas `LinkedList` does not. [Java 17 RandomAccess Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html)

For a simple sequential traversal, there is no need to add an `instanceof RandomAccess` branch: an iterator already expresses sequential traversal directly.

### 9.2. A copy has its own cost and semantics

When many subsequent indexed accesses are required, creating a copy can be worthwhile:

```java
List<String> indexed = new ArrayList<>(linkedNames);
```

This illustrative snippet requires importing `java.util.ArrayList` and `java.util.List`; `linkedNames` is the source list.

With a `LinkedList` source, copying the references takes linear work and allocates linear extra memory. Afterward, indexed access on the copy supports array-backed access patterns.

Check the following:

- Are there enough subsequent indexed accesses to justify the copying cost?
- Does the program need to observe later structural modifications to the source list?
- Is allocating `O(n)` extra memory acceptable?

This is a shallow structural copy of references. The element objects themselves are not deep-copied. Adding or removing elements in the source list does not automatically update the target list, but if both hold references to the same mutable object, mutations inside that object remain visible through both lists.

If you only read the list once, copying before traversing usually adds unnecessary work compared to traversing directly with an iterator.

## 10. How to verify an optimization change

### 10.1. Verify correctness first

When changing a loop, confirm that:

- Elements are still processed in the exact same order.
- Every required element is processed the exact right number of times.
- The source list is preserved or mutated according to the original requirement.
- Empty inputs, single-element lists, duplicate elements, and `null` values are handled under the same contract.
- Any additions or removals during traversal follow the contract of the iterator in use.

For the summation example, `null` must be excluded or handled by an explicit policy; changing the loop style does not automatically resolve that issue.

### 10.2. Verify mechanism and growth

Look for repeated node-locating operations inside traversal loops: `get(i)`, `set(i, ...)`, `listIterator(i)`, and `indexOf(...)`. Inspect methods called inside the loop body as well, rather than only counting loop statements in the outer code.

Measure across multiple input sizes if you need to confirm the impact in a real application. Avoid treating a single wall-clock reading on a small list as proof of complexity. The JVM also involves warm-up, JIT compilation, memory allocation, GC, and system noise.

When the loop body performs only constant work:

- Full indexed traversal on a `LinkedList`: doubling the input size nearly quadruples the node-locating work for large `n`.
- Single iterator pass: the work grows linearly with the number of elements.

These ratios describe asymptotic growth order, not a guarantee that measured runtime will be an exact multiple of four or two on every run.

## 11. Selection guide by requirement

| Requirement | Appropriate approach on LinkedList | What to avoid |
| --- | --- | --- |
| Read all values in order | `for-each` | `get(i)` for every index |
| Read with ordinal index | `for-each` + counter variable, or `ListIterator` | Repeated `indexOf(value)` |
| Reverse traversal preserving the list | A `ListIterator` starting at the end, or `descendingIterator()` | Decrementing `get(i)` loop |
| Remove selected elements during traversal | The iterator's own `remove()` | Direct removal on the list inside `for-each` |
| Replace the value of the element being visited | `ListIterator.set()` right after reading the element | `get(i)` followed by `set(i, ...)` at every index |
| Process a contiguous slice starting at position `k` | Position the iterator once, then keep advancing | Recreating an iterator at every index |
| Access many arbitrary positions | Consider an indexed-access structure or an appropriate copy | Assuming every `List.get()` is constant-time |

## 12. Self-check and exercises

### Question 1: Is indexed traversal still quadratic even though LinkedList picks the closer end?

Yes. The total hop distance is `floor((n - 1)² / 4)` for `n >= 1`, so it still grows as `Θ(n²)`. Picking the closer end improves the constant factor, not the order of growth.

### Question 2: I cached values.size() in a variable—why is it still slow?

Because every `get(i)` still has to locate the node. Eliminating repeated `size()` calls does not remove the total work spent walking links to find nodes.

### Question 3: If I need to print ordinal numbers, must I use get(i)?

No. Maintain a counter variable alongside `for-each`, or query the cursor index via `ListIterator` when appropriate. Needing a sequence number during traversal does not require accessing elements by index.

### Question 4: Does switching to IntStream.range(...).mapToObj(values::get) fix the problem?

No. The `get(i)` calls still happen. Traverse the values directly rather than recreating indexed lookups in different syntax.

### Exercises

1. Add a method to the complete program that sums only the odd numbers using a single `for-each` pass while leaving the source list unchanged.
2. Write a function that finds the first index whose value exceeds a threshold, using an iterator with a counter variable and stopping as soon as a match is found.
3. Explain the cost of creating `listIterator(k)` once and then reading `r` consecutive elements, assuming valid bounds and no external structural modifications.
4. Review a method in your own codebase that accepts `List<T>`: does it inadvertently assume fast indexed access?

Reference hint for exercise 3: the cost consists of a single initial lookup to reach position `k` plus the work of advancing across `r` consecutive elements. On a `LinkedList`, the overall bound is `O(n + r)`; if expressed in terms of the distance from the nearer end to the starting index, it can be stated even more tightly using that distance. Crucially, it does not perform `r` independent node lookups as repeating `get(k + j)` would.

When the goal is to walk through consecutive elements, keep your position and move forward. That is why an iterator fits `LinkedList` far better than a sequence of requests that relocate indices from scratch.
