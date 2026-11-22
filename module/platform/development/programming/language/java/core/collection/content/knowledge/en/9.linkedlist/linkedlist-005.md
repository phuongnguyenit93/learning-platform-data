# Why Is Middle Insertion Not Always Faster Than ArrayList?

## 1. Compare the Entire Operation the Program Actually Requires

The statement "LinkedList inserts in the middle in O(1), while ArrayList inserts in the middle in O(n)" leaves out a critical condition: **LinkedList links a node in constant time only after the target node position has already been located**.

If the program's input is an index in the middle, such as `add(50_000, value)`, LinkedList still has to traverse to that position. ArrayList accesses the slot by index directly, but has to shift the trailing portion. Given an index in the middle of a large list, both calls have linear cost with respect to the number of elements in the standard cost model.

The two list types perform different kinds of work:

| Structure | Multi-step work when inserting in the middle by index |
| --- | --- |
| LinkedList | Traverse links to locate the position; then allocate and link a node |
| ArrayList | Make room by shifting trailing references; may also need to grow the backing array |

Having the same O(n) complexity neither means equal runtime speed nor determines which one definitely wins. You must examine the kind of work performed, memory layout, allocations, and the surrounding algorithm around the call.

Consider a business example: an application holds a list of lines and wants to insert a new line at a user-selected position. If the UI only sends a line number, the cost of locating that position in a LinkedList is real work. If the processor is already traversing with an iterator and inserts directly at the current cursor, the situation is different.

This article analyzes Java 17 and above in a single-threaded context, using mutable lists where data is not concurrently modified from elsewhere while using an iterator. The demo programs illustrate correctness and model work counts rather than speed benchmarks.

## 2. Clearly Define "Middle Insertion"

### 2.1. Same Result, Multiple Ways of Knowing the Position

Suppose we start with:

```text
[A, B, C, D]

Want to insert X before C:
[A, B, X, C, D]
```
The problem might provide:

1. Index 2.
2. A value to search for, e.g., "insert before the element equal to C".
3. A ListIterator already positioned right before C.
4. A batch of elements to insert at once before C.

These are different inputs. Do not use the cost of the third case to describe every call in the first or second case.

Holding a reference to the object C is not the same as holding an internal node of LinkedList. C may appear multiple times in the list; the same element object may be referenced by multiple nodes. The LinkedList API does not expose a public Node for the caller to pass directly into an insertion method.

### 2.2. Variables Used for Counting

| Symbol | Meaning |
| --- | --- |
| n | Initial number of elements, before the insertion under consideration |
| i | Insertion index; 0 <= i <= n |
| k | Number of elements to insert in a batch |
| s = n - i | Number of existing elements after the insertion point |
| d | Number of links to traverse to locate the position in LinkedList |

When i is approximately n/2, both s and d scale linearly with n. When inserting very close to the head or tail, the relative costs can differ; do not replace every position with a vague "middle" label.

### 2.3. Operation Time Is the Sum of Multiple Parts

```text
Total work
= locate insertion point
+ make room or allocate node
+ write element / update links
+ update list state
+ auxiliary work required by the algorithm.
```
Constructing the domain element object itself can be a separate step. For instance, building a large document and then inserting it into a list should not be used to draw conclusions about the data structure's own overhead if two measurements construct the document differently.

## 3. LinkedList: Fast Linking After Arriving at the Position

### 3.1. Node Linking Is Local

LinkedList is a doubly linked list. Each node holds a reference to the element and references to its two neighboring nodes.

```text
Before: ... <-> B <-> C <-> ...
After:  ... <-> B <-> X <-> C <-> ...
```
Once node C and its predecessor are known, creating X and relinking the neighbors only requires a constant-bounded number of pointer assignments. None of the trailing nodes need to be shifted to new storage locations.

However, the condition "once the node is known" must not be ignored.

### 3.2. An Index Does Not Automatically Turn Into a Node

According to the [Java 17 LinkedList specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), indexed operations traverse from the beginning or the end, whichever is closer to the specified index.

In the OpenJDK 17 implementation, for i < n, the number of link hops to reach the node at index i can be modeled as:

```text
d = min(i, n - 1 - i)
```
To insert before that node, the total work is locating the node plus allocating and linking the new node:

```text
T_LinkedList(add(i, x))
= O(1 + d) + O(1)
= O(1 + d).
```
When i is approximately n/2, the total is O(n), and the number of search hops grows linearly. The case i = n is an append at the end, which uses `last` directly, so the element index formula for i < n does not apply to the trailing insertion point.

If you create `listIterator(i)` in the middle, initializing the iterator must also traverse to that position. Calling the iterator constructor before the measured line does not make the lookup cost disappear from the overall task; it only changes which part of the task is being measured.

### 3.3. When Holding a Valid Iterator

When an algorithm is already traversing the list with a ListIterator and inserts right at the current cursor, LinkedList does not need to restart an index lookup. At that point, a single `ListIterator.add` call can allocate and link a node with a constant number of structural operations.

This is a genuine advantage in a matching access pattern. However:

- You must account for the cost of reaching the initial position or traversing sequentially to it.
- The iterator must remain valid according to its usage contract.
- If a new iterator is created in the middle each time, the lookup cost is repeated.
- If the insertion point jumps far across the list repeatedly, holding a cursor does not make moving to every new point constant time.

Do not call the lookup cost "unfair" if the application requirement genuinely supplies the position as an index. Conversely, do not force repeated lookups if the algorithm genuinely already holds a valid cursor. Describe the actual inputs and available state accurately.

## 4. ArrayList: Direct Index Access, but Must Make Room

### 4.1. Number of Elements to Shift

ArrayList stores a sequence of references in an internal array. Inserting x at index i requires shifting existing references from i through n - 1 one slot to the right.

```text
Number of references shifted due to insertion = n - i = s.
```
If the backing array already has sufficient capacity:

```text
T_ArrayList(add(i, x)) = O(1 + n - i).
```
Inserting in the middle shifts a linearly growing number of references. Inserting near the end shifts fewer. If i = n, there is no trailing segment to shift.

### 4.2. When Capacity Is Exhausted

If resizing is needed, ArrayList must also allocate a larger array and copy the existing references. A single insertion may incur both the capacity growth cost and the suffix shifting cost.

Pre-sizing capacity can reduce array expansions, but it does not eliminate shifting the elements after the insertion point.

The [Java 17 ArrayList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) guarantees that appending at the end runs in amortized constant time. Do not use that guarantee to claim that inserting at a middle index also runs in amortized constant time: the work of shifting the suffix still repeats on every middle insertion.

When accounting for the total task, the cost of pre-sizing capacity should also be attributed to the appropriate phase. If you only want to measure insertion when sufficient capacity is already available, state that condition explicitly.

### 4.3. Shifting References Is Not Cloning Objects

Suppose the elements are very large document objects. ArrayList does not deep-copy the contents of all trailing documents upon insertion. It shifts object references inside the array.

```text
Array before: [ref A, ref B, ref C, ref D]
Array after:  [ref A, ref B, ref X, ref C, ref D]

Objects A, B, C, D remain the exact same objects.
```
The deep size of a document does not directly translate into the number of document payload bytes copied during this shift operation.

That does not mean large objects have no effect on whole-program performance. Reading or processing them can affect CPU caches and overall execution time; just keep that separate from shifting reference slots.

In the [OpenJDK 17 ArrayList source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), shifting is performed via an array copy operation, and the new element reference is written into the insertion slot.

## 5. Both Are Linear, but the Elementary Steps Differ

### 5.1. Traversing Nodes Differs From Copying a Contiguous Reference Region

When LinkedList traverses to a middle position, each step reads a reference to discover the next node. Nodes are separate heap objects; the API makes no guarantee that they reside near one another in memory.

When ArrayList shifts its suffix, the reference slots belong to a contiguous array region. Moving such a contiguous block can be executed very efficiently by the JVM and underlying hardware.

Both operations have step counts that grow linearly with n, but they neither share the same constant factors nor exhibit the same memory access patterns.

Do not deduce:

```text
50,000 references to shift
> 49,999 links to traverse
=> LinkedList is definitely faster.
```
One shifted reference slot and one dependent pointer-chasing hop through a node are not equal units of time. The counting model explains growth trends; actual measurements evaluate concrete execution time.

### 5.2. LinkedList Also Incurs Node Allocation Cost

In the [OpenJDK 17 LinkedList implementation](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java), each insertion allocates a `Node` holding `item`, `prev`, and `next`.

Each node carries object header overhead and alignment depending on the JVM. Inserting many elements allocates many nodes, even if the elements point to existing domain objects.

ArrayList can insert into an array with sufficient capacity without allocating a wrapper node per element. When it does need to grow capacity, it incurs array allocation cost, so comparisons must be based on realistic growth patterns.

Small allocations can be very fast on modern JVMs, but they are not free. Node allocation rate, node lifetime, and garbage collection can affect total runtime and memory footprint.

### 5.3. There Is No Fixed Crossover Point for Every Application

You cannot deduce a universal rule like "beyond n = X, LinkedList always wins" from class names alone while ignoring:

- The insertion position and how that position is determined.
- How many elements are inserted per operation.
- The current capacity of the ArrayList.
- Whether an iterator is retained or recreated.
- Element types and surrounding workload.
- JVM version, hardware, load, and memory state.

A specific benchmark result can be useful for a specific workload. It must be reported together with its conditions rather than turned into a universal law of the `List` interface.

## 6. Runnable Example: A Single Middle Insertion by Index

Save as `MiddleInsertCostModelDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class MiddleInsertCostModelDemo {
    public static void main(String[] args) {
        List<String> seed = List.of("A", "B", "C", "D");
        ArrayList<String> array = new ArrayList<>(16);
        array.addAll(seed);
        LinkedList<String> linked = new LinkedList<>(seed);

        int index = 2;
        array.add(index, "X");
        linked.add(index, "X");

        System.out.println("ArrayList result = " + array);
        System.out.println("LinkedList result = " + linked);
        System.out.println("same result = " + array.equals(linked));

        int n = 100_000;
        int middle = n / 2;
        int arraySuffix = n - middle;
        int linkedHops = Math.min(middle, n - 1 - middle);
        System.out.println("model n = " + n + ", index = " + middle);
        System.out.println("ArrayList suffix references = " + arraySuffix);
        System.out.println("LinkedList locating links = " + linkedHops);
    }
}
```
Compile and run:

```shell
javac --release 17 MiddleInsertCostModelDemo.java
java MiddleInsertCostModelDemo
```
Output:

```text
ArrayList result = [A, B, X, C, D]
LinkedList result = [A, B, X, C, D]
same result = true
model n = 100000, index = 50000
ArrayList suffix references = 50000
LinkedList locating links = 49999
```
The first part performs an actual insertion on two small lists and verifies that they produce the exact same order.

The second part computes model quantities at n = 100,000; it does not populate a 100,000-element list and does not measure elapsed time:

- ArrayList must shift a suffix of 50,000 references when inserting at index 50,000.
- LinkedList in the model traverses 49,999 links from the tail to reach the node at that index before linking.

These two numbers demonstrate that LinkedList's lookup phase is not a constant number of steps in this scenario. They do not determine which one runs faster in wall-clock time.

The small ArrayList in the program is pre-sized to capacity 16, whereas after insertion it holds only five elements. Therefore, this illustration is not an example of measuring an array resize event.

## 7. Inserting Multiple Elements: The Algorithm Can Matter More Than the Class Name

### 7.1. Inserting Elements One by One at Increasing Indexes

Suppose we want to insert X, Y, Z before C while preserving batch order:

```text
Initial: [A, B, C, D]
After X: [A, B, X, C, D]
After Y: [A, B, X, Y, C, D]
After Z: [A, B, X, Y, Z, C, D]
```
With ArrayList, the original trailing segment `C, D` is shifted three times. The total number of reference shifts across those suffix moves is 3 * 2 = 6.

In general, if k elements are inserted one by one at indexes i, i + 1, ..., i + k - 1, the original trailing suffix of length s = n - i must be shifted on every call:

```text
Total original references shifted = k * s.
```
This does not yet include writing the k new elements or any array resizes that might occur.

With LinkedList, if you also call `add(index, value)` individually for each element, every call has to locate the index again. When the insertion point is in the middle and the distance to the original tail remains large, the total lookup work can be O(k * n) rather than automatically dropping to O(k).

### 7.2. Retaining a LinkedList ListIterator

If you create an iterator at the insertion point once and then call `iterator.add` for the entire batch:

```text
Locate position once: O(n) in the middle.
k node allocations and linkings: O(k).
Total: O(n + k).
```
In the formula above, O(n) bounds the middle lookup step; if you already hold the iterator from a required prior traversal pass, you can report the k insertions themselves as O(k) while clearly stating the cost of the traversal pass.

Both ArrayList and LinkedList provide a `ListIterator` implementation, but using the same API does not equalize their costs. ArrayList's iterator tracks a logical index; inserting in the middle via its iterator still shifts the trailing suffix on every call.

### 7.3. ArrayList Also Has a Bulk Insertion Operation

`addAll(i, batch)` can shift the trailing segment to the right once by k slots, and then write the k new elements.

If capacity is sufficient and extracting the source batch has standard linear cost:

```text
Cost of ArrayList.addAll(i, batch)
= O((n - i) + k).
```
If resizing is required, the standard upper bound is O(n + k), accounting for copying the existing elements as well.

`LinkedList.addAll` can likewise locate the position once and then link a chain of k new nodes. For a standard source collection, the total cost is O(lookup cost + k), which is O(n + k) when inserting in the middle.

Therefore, comparing an element-by-element insertion loop on ArrayList against a bulk insertion call on LinkedList without explaining the algorithmic difference can lead to false conclusions about the data structures themselves.

### 7.4. Preserving Batch Order Is a Functional Requirement

If you call `add(i, value)` with the **exact same index i** for each value X, Y, Z, the resulting order at that position will be Z, Y, X. That is not the same task as inserting a batch while preserving the order X, Y, Z.

When comparing performance, first verify that all candidate approaches produce the exact same result. Never choose an approach that runs faster by producing the wrong order.

Furthermore, "inserting at the middle of the current list each time" differs from "inserting the entire batch before the initially chosen element C". Because the list size changes after each insertion, the calculated middle indexes can diverge. Define the positioning rule explicitly.

## 8. Runnable Example: Five Ways to Produce the Same Result

Save as `MiddleInsertBatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class MiddleInsertBatchDemo {
    static void insertByIndexes(
            List<String> target, int index, List<String> batch) {
        int offset = 0;
        for (String value : batch) {
            target.add(index + offset, value);
            offset++;
        }
    }

    public static void main(String[] args) {
        List<String> seed = List.of("A", "B", "C", "D");
        List<String> batch = List.of("X", "Y", "Z");
        int index = 2;

        ArrayList<String> arrayRepeated = new ArrayList<>(16);
        arrayRepeated.addAll(seed);
        insertByIndexes(arrayRepeated, index, batch);

        LinkedList<String> linkedRepeated = new LinkedList<>(seed);
        insertByIndexes(linkedRepeated, index, batch);

        LinkedList<String> linkedCursor = new LinkedList<>(seed);
        ListIterator<String> cursor = linkedCursor.listIterator(index);
        for (String value : batch) {
            cursor.add(value);
        }

        ArrayList<String> arrayBulk = new ArrayList<>(16);
        arrayBulk.addAll(seed);
        arrayBulk.addAll(index, batch);

        LinkedList<String> linkedBulk = new LinkedList<>(seed);
        linkedBulk.addAll(index, batch);

        System.out.println("ArrayList repeated = " + arrayRepeated);
        System.out.println("LinkedList repeated = " + linkedRepeated);
        System.out.println("LinkedList one cursor = " + linkedCursor);
        System.out.println("ArrayList addAll = " + arrayBulk);
        System.out.println("LinkedList addAll = " + linkedBulk);

        List<String> expected = List.of("A", "B", "X", "Y", "Z", "C", "D");
        boolean allMatch = arrayRepeated.equals(expected)
                && linkedRepeated.equals(expected)
                && linkedCursor.equals(expected)
                && arrayBulk.equals(expected)
                && linkedBulk.equals(expected);
        System.out.println("all results match = " + allMatch);

        long repeatedSuffixCount = (long) batch.size() * (seed.size() - index);
        long bulkSuffixCount = seed.size() - index;
        System.out.println("ArrayList repeated suffix model = "
                + repeatedSuffixCount);
        System.out.println("ArrayList addAll suffix model = " + bulkSuffixCount);
    }
}
```
Compile and run:

```shell
javac --release 17 MiddleInsertBatchDemo.java
java MiddleInsertBatchDemo
```
Output:

```text
ArrayList repeated = [A, B, X, Y, Z, C, D]
LinkedList repeated = [A, B, X, Y, Z, C, D]
LinkedList one cursor = [A, B, X, Y, Z, C, D]
ArrayList addAll = [A, B, X, Y, Z, C, D]
LinkedList addAll = [A, B, X, Y, Z, C, D]
all results match = true
ArrayList repeated suffix model = 6
ArrayList addAll suffix model = 2
```
The program demonstrates five approaches:

1. Element-by-element indexed insertion on ArrayList.
2. Element-by-element indexed insertion on LinkedList.
3. Using a single LinkedList `ListIterator` for the entire batch.
4. Using `ArrayList.addAll`.
5. Using `LinkedList.addAll`.

All five approaches insert X, Y, Z before C while preserving order. The `allMatch` check confirms functional equivalence on the sample data.

The two suffix model lines compute how many existing suffix reference shifts are required in the ArrayList model:

- Repeated three times: C and D are shifted three times, totaling 6.
- Single `addAll`: C and D only need to be shifted once past the entire batch, totaling 2.

These numbers do not count writing the new elements, temporary arrays produced from the source collection, or all JVM operations. Do not refer to the values 6 and 2 as allocation counts or speed ratios.

According to the [Java 17 ListIterator.add contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html#add(E)), the new element is inserted immediately before the element that would be returned by `next()`. The cursor advances past the newly added element, so the sequence of `add` calls in the example preserves the order X, Y, Z without ever re-locating C.

Once the entire batch to insert is already known, `addAll` usually expresses intent more clearly than a loop of individual `add` calls. The cost of obtaining data from the source collection and the requirement that the source data not be concurrently modified during the operation must still be taken into account.

## 9. Runnable Example: Element Objects Are Not Deep-Copied

Save as `MiddleInsertReferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class MiddleInsertReferenceDemo {
    static final class Document {
        static int constructed;
        final String name;

        Document(String name) {
            this.name = name;
            constructed++;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        Document a = new Document("A");
        Document b = new Document("B");
        Document c = new Document("C");
        Document d = new Document("D");
        Document inserted = new Document("X");

        List<Document> seed = List.of(a, b, c, d);
        ArrayList<Document> array = new ArrayList<>(16);
        array.addAll(seed);
        LinkedList<Document> linked = new LinkedList<>(seed);

        System.out.println("documents before insertion = " + Document.constructed);
        array.add(2, inserted);
        linked.add(2, inserted);
        System.out.println("documents after insertion = " + Document.constructed);
        System.out.println("ArrayList values = " + array);
        System.out.println("LinkedList values = " + linked);
        System.out.println("ArrayList retained C identity = " + (array.get(3) == c));
        System.out.println("LinkedList retained C identity = " + (linked.get(3) == c));
        System.out.println("both contain the same X = "
                + (array.get(2) == linked.get(2)));
    }
}
```
Compile and run:

```shell
javac --release 17 MiddleInsertReferenceDemo.java
java MiddleInsertReferenceDemo
```
Output:

```text
documents before insertion = 5
documents after insertion = 5
ArrayList values = [A, B, X, C, D]
LinkedList values = [A, B, X, C, D]
ArrayList retained C identity = true
LinkedList retained C identity = true
both contain the same X = true
```
Five `Document` instances are constructed prior to insertion: A, B, C, D, and X. After inserting X into both lists, the number of `Document` instances constructed remains five.

Reference equality checks (`==`) show that C at its new index is still the exact same `c` instance as before. The X element in both lists is also the exact same provided instance.

Key distinctions to keep in mind:

- The counter tracks only `Document` instances constructed by the program, not internal `Node` objects allocated by LinkedList or backing arrays inside ArrayList.
- ArrayList can shift many references without constructing new `Document` instances.
- LinkedList allocates a new `Node` to hold a reference to an existing `Document`.
- The program does not measure total allocated bytes or execution time.

Do not multiply the deep memory footprint of a `Document` to estimate how many bytes of `Document` body are copied during `ArrayList.add`. The shifting work here operates on reference slots.

## 10. Hidden Costs in Locating the Insertion Point

### 10.1. Searching by Value and Then Inserting by Index

A common pattern to write is:

```java
// Illustrative snippet; handle the case where target is absent appropriately.
int index = items.indexOf(target);
if (index >= 0) {
    items.add(index, inserted);
}
```
`indexOf` performs a linear search on both list types.

With LinkedList, after `indexOf` traverses the nodes and returns an integer index, `add(index, inserted)` has to locate the node by index all over again. The internal node reached during the search is not carried across through the primitive integer `index`.

An algorithm that searches using a `ListIterator` and inserts directly upon finding the target can avoid that second traversal. However, if the requirement is "insert before the first occurrence equal to target", you must position the cursor properly according to the `next` / `previous` / `add` contract. Do not alter search semantics in the name of optimization.

The overall asymptotic upper bound for a single search-and-insert in the middle remains linear for both implementations, though the concrete work and number of traversal passes can differ.

### 10.2. Locating a Position via Repeated get(i) Calls

If you search for an element in a LinkedList using a loop from `i = 0` to `n - 1` calling `get(i)` on each iteration, you can create quadratic work before even performing the insertion.

That is a flaw in the search algorithm, not proof that linking a node takes quadratic time. Traversing with an iterator when sequential access is all that is needed preserves position instead of restarting from an end of the list on every step.

### 10.3. Index Lookup Tables Are Not Free Either

A `Map` from element ID to list index might reduce some searches, but inserting before other elements shifts all their subsequent indexes. Updating the secondary index map can become substantial work in itself.

With a standard `LinkedList`, storing elements in a `Map` still does not give you access to internal `Node` objects. Do not base an analysis on a hypothetical public "insert before this Node" operation that the standard API does not offer.

If a workload requires many stable handles and modifications at distant points, you may need to reconsider the data model or use a specialized data structure. First define whether "position" means a numeric index, an element identifier, or a traversal cursor.

## 11. Comparison Table Under Realistic Conditions

The table below summarizes typical structural work; `k` is the batch size and `s` is the length of the existing suffix after the insertion point. It does not prescribe fixed wall-clock time ratios between cells.

| Scenario | LinkedList | ArrayList |
| --- | --- | --- |
| Single `add(i, x)` with `i` in the middle, given only `i` | Linear traversal, then link node | Linear shift; may resize backing array |
| Single insertion when a valid iterator is already at the position | Allocate/link node in constant structural work | Still shifts the trailing suffix |
| Initializing an iterator in the middle given only `i` | Must traverse links to reach position | Holds the numeric index directly |
| Inserting `k` elements via a single iterator in the middle | Locate once, then O(k) node operations | May shift the same suffix `s` repeatedly, totaling O(k * s + k), excluding resizes |
| Bulk insertion via `addAll(i, batch)` | Locate once, allocate `k` nodes | Shift suffix once, write `k` references; may resize |
| Must find target by value first | Add search cost | Add search cost |
| Heavy indexed read access after insertion | Must pay traversal cost on indexed reads | Direct indexed access |
| Continuous insertions and removals | Account for node allocations and lifetimes | Account for capacity, shifts, and array replacements |

A pattern well-suited to LinkedList is: the algorithm is already traversing sequentially, holds a valid iterator, and performs multiple in-place edits during that pass. The advantage lies in reusing the current cursor position and modifying only local links.

A pattern that yields no clear advantage from node-linking theory alone is: receiving many independent middle indexes, calling `add(index, value)` each time, and frequently reading back elements via `get(i)`.

Both observations still need to be evaluated within the overall application requirements and verified with performance measurements when the cost matters.

## 12. Measure the Right Question Instead of a Skewed Comparison

### 12.1. Choose the Measurement Scope

The following two questions are both valid, yet distinct:

- How long does it take to fulfill the request "here is an index, insert an element at it"?
- How long does it take to insert at an existing iterator because the program has already traversed to this point?

The first question must include the required position lookup. The second question can measure insertion at the cursor separately, but must report the pre-existing cursor state and account for the traversal phase when discussing the end-to-end task.

Do not publish a single undifferentiated "middle insertion" label for two fundamentally different conditions.

### 12.2. What to Keep Consistent

1. **Result:** identical data ordering, identical number of new elements, and identical insertion point rules.
2. **Size:** insertion increases `size`; specify the starting size for each measured operation.
3. **Setup:** explicitly state whether list construction, element creation, iterator initialization, and capacity pre-sizing are inside or outside the measured region.
4. **Capacity:** does the ArrayList already have sufficient capacity, or does the measurement include resize overhead?
5. **Positioning method:** receiving an index, searching by value, or continuing from an existing cursor?
6. **Extraneous work:** avoid inadvertently measuring console printing, string concatenation, or random number generation when the question is purely about insertion cost.

If you insert and immediately remove an element inside the measured loop to restore list size, the measurement reflects an **insert-remove pair**, not insertion alone. If you clone a fresh list before every single insertion inside the timed block, you may primarily be measuring list construction.

Those setups are not inherently wrong; they just need to match the question being asked and be labeled accurately.

### 12.3. JVM and Hardware Affect Results

Warm up the code sufficiently so the JIT compiler can optimize it, run multiple iterations, prevent dead-code elimination, and record the execution environment. A single `System.nanoTime()` call on a tiny list is insufficient to draw conclusions across all sizes.

[OpenJDK JMH](https://github.com/openjdk/jmh) helps build sound JVM microbenchmarks. To see why memory layout and reference ordering affect measurements, review the [JMH MemoryAccess sample](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_39_MemoryAccess.java).

The standalone runnable examples in this article do not run JMH benchmarks or measure hardware cache misses. Accordingly, this article does not fabricate speedup ratios, crossover list sizes, or synthetic nanosecond figures from the analytical model.

### 12.4. Evaluate the Real Workload as a Whole

An application might insert rarely but read very frequently. Saving a fraction of insertion cost does not necessarily offset the cost of millions of subsequent indexed lookups.

Another application might scan sequentially and make frequent local edits within the same region. Retaining a valid cursor in that scenario substantially changes the positioning cost.

Weigh the relative frequency of operations and data lifetimes rather than picking a data structure from a single cell in a complexity cheat sheet.

## 13. Common Misconceptions

| Claim | Overlooked Condition or Work |
| --- | --- |
| "LinkedList middle insertion is always O(1)" | Omits the step of locating the position when the input is only an index or value |
| "ArrayList copies all trailing objects" | It shifts object references, not deep copies of the elements |
| "Both are O(n), so their performance is identical" | Object counts, dependent pointer chasing, and contiguous array copying behave very differently |
| "With an iterator, every List inserts in O(1)" | An iterator does not change how ArrayList shifts its backing array to make room |
| "Pre-sizing capacity makes ArrayList middle insertion O(1)" | The trailing suffix still has to be shifted |
| "Inserting a batch and inserting one by one have the same cost" | The number of suffix shifts or position lookups can differ dramatically |
| "Relinking a few references allocates nothing" | LinkedList typically allocates a new `Node` object for each inserted element |
| "After `indexOf`, LinkedList already remembers the node for `add(index)`" | A primitive integer index does not carry internal node state from the prior search |
| "A benchmark that pre-creates a cursor proves indexed insertion is faster" | It may have moved the lookup cost outside the timed region |
| "ArrayList always wins because array copying is fast" | Cursor patterns, insertion frequency, list size, and surrounding operations still matter |
| "Swapping the class name is sufficient optimization" | Batch insertion algorithms, cursor retention, and search strategy often dominate the work |
| "There is a single threshold `n` that applies to every machine" | Empirical crossover points depend heavily on the workload and runtime environment |

## 14. Self-Check With Concrete Scenarios

### Exercise 1: A Single Index in the Middle

A list has one million elements, you are given only index 500,000, and you need to insert one element.

LinkedList must traverse to the node near the middle; ArrayList must shift roughly half a million references and possibly resize. Both perform linear work in the analytical model. You cannot conclude LinkedList runs in constant time by looking solely at the node-linking step.

### Exercise 2: Traversing and Inserting at the Cursor

An algorithm has already traversed to the target region using a LinkedList `ListIterator` and inserts 100 elements at that cursor.

It can leverage the current cursor position: 100 node allocations and linkings take O(100) structural work in total. When reporting the end-to-end task, still account for the traversal pass required to reach that region.

If the entire batch of 100 elements is known upfront, also compare `addAll` and appropriate data organization rather than assuming 100 separate calls are mandatory on every structure.

### Exercise 3: Bulk Insertion Into an ArrayList With Sufficient Capacity

An ArrayList has n = 10,000 elements, and you insert k = 200 elements before index i = 2,000 while preserving order.

The existing suffix after the insertion point has s = 8,000 elements:

- Inserting one by one at increasing indexes: shifting the existing suffix references alone accounts for 200 * 8,000 = 1,600,000 reference moves.
- `addAll`: the existing suffix of 8,000 references is shifted past the batch once; the remaining work is writing the 200 new references and reading the batch source.

These are analytical model work counts, not a literal 200x wall-clock time ratio.

### Exercise 4: Does Holding a Reference to C Let You Insert Before C in O(1)?

Not with standard Java `LinkedList`. A reference to C is a reference to the domain element, not the internal `Node`. Moreover, if C appears multiple times in the list, you must still specify which occurrence is targeted.

### Exercise 5: Does a Very Large Document Force ArrayList Shifts to Copy the Entire Document?

No. The shifted slots hold object references. Processing the contents of a `Document` may take significant time, but that is separate work.

### Exercise 6: Verify Functional Equivalence Before Comparing Times

One program repeatedly calls `add(2, value)` with X, Y, Z. Another calls `addAll(2, List.of("X", "Y", "Z"))`. Are they performing the exact same task?

No. Repeatedly inserting at the exact same index reverses the order of the newly inserted group, whereas `addAll` preserves the batch order. Always verify the output before interpreting timing numbers.

### Exercise 7: Is a Proposed Optimization Sound Across the Entire Workflow?

A proposal suggests replacing ArrayList with LinkedList because there are a few middle insertions, even though the rest of the code calls `get(i)` inside several loops. You should examine operation frequencies, insertion positions, and traversal patterns across the entire workflow; switching the structure may shift heavy costs onto indexed reads or still incur repeated position lookups on insertion.

The essential questions to answer are always: **what does the program already know before the insertion, what work is required to reach that position, is it inserting a single element or a batch, and how will the data be accessed afterward?** When these parts are clearly separated, LinkedList's node-linking advantage is placed in proper context, and choosing between ArrayList and LinkedList rests on a verifiable foundation.
