# ArrayList: Shifting Cost When Inserting or Removing at the Beginning and Middle

`ArrayList` is convenient when you need an ordered list with fast index-based access. However, "fast access to position i" does not mean "inserting or removing at i is also fast." Access only reads a single position; inserting or removing must also maintain contiguous element placement and preserve the exact order.

For example, suppose a task list is currently `[A, B, C, D]`. If we insert `X` before `B`, the result must be `[A, X, B, C, D]`; the three elements B, C, and D change their indices. If we remove `B`, the trailing elements must be compacted so the list has no gap.

This article explains that shifting work, how to calculate it by position, its impact when operations are repeated, and ways to reduce the work while preserving the exact result. The examples use Java 17 or later; where specific OpenJDK algorithmic details are analyzed, that will be stated explicitly.

## 1. Mental Model to Remember: Elements Are Contiguous in the Backing Array

An `ArrayList` has two distinct quantities:

- **Size:** the number of elements currently in the list.
- **Capacity:** the number of slots the backing array can hold before the array needs to grow.

If the size is n, the logical elements occupy positions from 0 to n−1. The capacity may be greater than n, but the spare capacity sits after the active segment, not as scattered gaps in the middle.

~~~text
size = 5, capacity = 8

index:          0   1   2   3   4   5   6   7
backing array: [A] [B] [C] [D] [E] [ ] [ ] [ ]
               <----- list ------> <--spare-->
~~~

The empty space on the right helps when appending to the end. It does not pre-allocate an empty slot between B and C. To insert there while preserving order, a gap must be opened by shifting the trailing segment.

Throughout this article, n is always the **size immediately before the operation being analyzed**, and i is the index passed in. When there are multiple operations, n may change after each step.

### 1.1. Shifting Moves References, Not Deep Copies of Objects

The backing array of `ArrayList<E>` holds object references. Moving an element from index 3 to 4 primarily copies the reference to another slot; it does not re-invoke the constructor and does not automatically create a deep copy of the object.

An object having large internal data does not mean all of its data is copied every time the list shifts. However, moving a million references is still significant work: it requires reading and writing many memory locations.

Element objects retain their identity. Their indices in the list may change; an external variable holding a reference to an element still points to that same object.

### 1.2. Order Is the Reason for Paying the Cost

If order does not need to be preserved, a different data structure or a specialized algorithm could handle gaps differently. However, `List` represents an ordered sequence. `ArrayList.remove(i)` must preserve the relative order of the remaining elements.

Manually moving the last element into the removed slot and dropping the tail can reduce work, but it changes the resulting sequence. You can only consider that algorithm when business requirements allow reordering; it is not the behavior of `ArrayList.remove(i)`.

## 2. Inserting at Index i: Shifting n−i Elements to the Right

`add(i, value)` inserts an element before the element currently at i. The old element at i and all subsequent elements have their indices incremented by 1.

Index condition:

~~~text
0 <= i <= n
~~~

i = n is appending to the end. i = 0 is inserting at the front. An empty list with n = 0 still allows inserting at i = 0.

The insertion rules and valid index range are described in the [Java 17 ArrayList add(int, E) contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#add(int,E)).

### 2.1. Middle Insertion Example

Given `[A, B, C, D, E]`, n = 5, insert X at i = 2:

~~~text
before:
index:      0   1   2   3   4
           [A] [B] [C] [D] [E]

open slot at i = 2:
index:      0   1   2   3   4   5
           [A] [B] [ ] [C] [D] [E]
                      C,D,E shifted right

write X:
           [A] [B] [X] [C] [D] [E]
~~~

The segment that must move consists of the old positions 2, 3, and 4, so the number of shifted references is:

~~~text
n - i = 5 - 2 = 3
~~~

Afterward, there is one write for the new element and a size update. If the array already has enough space, the work model is **Θ(n−i+1)**. The Θ notation here expresses an amount of work of the same order of growth as the length of the segment to process, including the constant-time bookkeeping.

### 2.2. How Do the Front, Middle, and End Differ?

| Insertion Position | Old Elements Shifted | When Capacity Is Sufficient |
|---|---:|---|
| Front, i = 0 | n | Θ(n+1) |
| Middle, i ≈ n/2 | Approximately n/2 | Θ(n) |
| Near the end, before a fixed number of elements | That fixed number | Θ(1) with respect to n |
| End, i = n | 0 | Θ(1) |

If a list has 100,000 elements, inserting right in the middle requires shifting about 50,000 references. "Only moving half" is still linear: the 1/2 factor does not change the order of growth.

One should not say that every call to `add(i, x)` shifts n elements. The number depends on i. Saying "index-based insertion is O(n) in the worst case" is accurate, while the formula n−i helps distinguish individual positions.

### 2.3. Insertion Differs from Replacement

Illustrative method body snippet:

~~~java
ArrayList<String> values = new ArrayList<>(List.of("A", "B", "C"));
values.set(1, "X");  // [A, X, C]: replace, size does not change
values.add(1, "Y");  // [A, Y, X, C]: insert, trailing part changes indices
~~~

`set` overwrites an existing position; it does not open a gap and does not shift the tail. If the requirement is merely to replace the value at a position, use `set` instead of removing and re-inserting.

With `set`, the index must be strictly less than n. Spare capacity does not make `set(n, x)` valid.

## 3. Removing at Index i: Shifting n−i−1 Elements to the Left

`remove(i)` returns the removed element and preserves the order of the remaining elements. Elements after i have their indices decremented by 1.

Index condition:

~~~text
0 <= i < n
~~~

Because there must be an element to remove, i = n is invalid and an empty list has no valid removal index. See the [Java 17 ArrayList remove(int) contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#remove(int)).

### 3.1. Middle Removal Example

Given `[A, B, C, D, E]`, n = 5, remove i = 2:

~~~text
before:
index:      0   1   2   3   4
           [A] [B] [C] [D] [E]

remove C and compact the tail:
index:      0   1   2   3   4
           [A] [B] [D] [E] [ ]
                    D,E shifted left

new size = 4
~~~

The segment that must move starts at i+1 and ends at n−1, so the number of shifted elements is:

~~~text
n - i - 1 = 5 - 2 - 1 = 2
~~~

In the OpenJDK implementation used in this article, after compacting the tail segment, the old last slot is assigned `null` so that no stale reference is retained. Updating the size, returning the removed element, and clearing the trailing reference constitute constant-time work beyond the shifted segment.

The cost model of index-based removal is **Θ(n−i)**. For the last element, n−i = 1, so the work is still constant even though the number of shifted references is 0.

### 3.2. Removal Position Table

| Removal Position | Elements Shifted | Order of Work with Respect to n |
|---|---:|---|
| Front, i = 0 | n−1 | Θ(n) for large n |
| Middle, i ≈ n/2 | Approximately n/2 | Θ(n) |
| Second to last, i = n−2 | 1 | Θ(1) |
| Last, i = n−1 | 0 | Θ(1) |

There is no "traverse from the beginning to index i" step in `ArrayList.remove(int)`: array access by index is direct. The linear part comes from compacting the tail, not from searching for the indexed slot.

### 3.3. Zero Shifts Does Not Mean Doing Nothing

Removing from the end still requires fetching the old value, decrementing the size, and clearing the reference in the last slot. Removing an element does not guarantee that the object is garbage-collected immediately:

- Another part of the program may still hold a reference to it.
- The return value of `remove` might be retained by the calling code.
- When the garbage collector runs is decided by the JVM.

Removing elements also does not mean shrinking the backing array after every removal. Clearing content, compacting order, and adjusting capacity are separate concerns.

## 4. Shifting the Tail and Growing Capacity Are Two Different Kinds of Work

During insertion, two kinds of work may occur at the same time:

1. **Growing the array:** a larger backing storage is needed if space runs out.
2. **Shifting the tail segment:** the exact insertion slot must be opened in the ordered sequence.

Pre-sizing capacity helps avoid the first kind within the reserved range. It does not eliminate the second kind.

For example, `new ArrayList<>(1_000_000)` currently holding 100,000 elements still has to shift 100,000 references if inserting at the front. The empty space after index 99,999 cannot substitute for a gap before index 0.

In the [OpenJDK 17 ArrayList source code, build jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayList.java), index-based insertion performs the growth step if needed and then shifts the tail segment; index-based removal compacts the tail segment and clears the last reference. This serves as the concrete implementation basis for the analytical model in this article.

### 4.1. Amortized End-Appending Does Not Generalize to Front-Insertion

A sequence of appends to the end starting from an empty list has a linear total array-management cost under the normal growth policy: expensive resizes are amortized across many cheap appends. Therefore, appending to the end has amortized constant cost.

With front insertion, however, **every single call** must shift all existing elements. The spare capacity created by an array resize does not make the shifting requirement disappear on the next front insertion. Consequently, do not use the amortized conclusion for end appends to conclude that front insertion is also O(1).

### 4.2. A Fast arraycopy Still Has to Process a Long Segment

An implementation can use `System.arraycopy` instead of a hand-written Java loop. This method supports copying between overlapping segments of the same array with correct results, as described in [System.arraycopy in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

JVM optimizations for bulk copying can improve the constant factor. They do not turn moving a segment of k references into an amount of work independent of k.

"When shifting right, write from back to front" is a helpful mental model when writing a manual loop so you avoid overwriting unread data. With `ArrayList`, the library already handles overlapping segments properly; application code does not need to manipulate a backing array directly.

## 5. When Operations Repeat, the Cost Can Become Quadratic

Evaluating a single statement in isolation is not enough. You must sum the number of elements moved across the entire loop.

### 5.1. Building a List by Repeatedly Inserting at the Front

Building a list from empty via n calls to `add(0, value)`:

~~~text
step 1:  currently 0 elements -> shift 0
step 2:  currently 1 element  -> shift 1
step 3:  currently 2 elements -> shift 2
...
step n:  currently n-1 elements -> shift n-1
~~~

Total references shifted:

~~~text
0 + 1 + 2 + ... + (n - 1) = n(n - 1)/2
~~~

The segment shifting alone is already Θ(n²), even if enough capacity was pre-allocated so that the array never resizes.

For n = 8, the total is 28. For n = 100,000, the total is 4,999,950,000 shifts under the model. This is the count of slot moves, not nanoseconds.

If you write the calculation using `int`, the product `n * (n - 1)` can overflow before dividing by 2. The practical example uses `long` starting from the very first operand. You should distinguish arithmetic overflow in the example's counter from the actual size limit of the list.

Inserting values 1, 2, 3 one by one at the front also reverses their order to `[3, 2, 1]`. Changing the algorithm to make it faster must preserve the exact order required by the final output.

If the goal is to produce a reversed order, consider appending to the end and reversing once, or traversing the source in the appropriate direction while appending to the end. The benefit comes from avoiding repeated tail shifts, not merely from changing a method name.

### 5.2. Removing from the Front Until Empty

Starting with n elements and repeatedly calling `remove(0)`:

~~~text
(n - 1) + (n - 2) + ... + 1 + 0 = n(n - 1)/2
~~~

Therefore, using `ArrayList` as a queue by appending to the end and polling/removing from the front can incur a quadratic total number of shifts when draining a large batch.

Switching to reading via `get(cursor++)` can avoid array compaction in certain single-pass designs, but the already-read portion remains retained by the list unless released in another way. This is not a drop-in equivalent replacement for every long-lived queue.

### 5.3. Removing from the End Until Empty

Repeatedly removing at `size()-1` shifts zero references. There are n constant-time operations, so the total removal work is Θ(n).

The two "remove until empty" loops share the same end state but differ drastically in the amount of work performed. If you only want to discard all content, `clear()` expresses the intent even more directly; there is no need to write a loop just to empty a list.

### 5.4. Repeated Removals Near the Middle Also Need to Be Summed

If you repeatedly remove at a position near the front while many elements remain behind it, many surviving elements will be shifted over and over. If each removal occurs at the middle of the current list, the length of the shifted segment remains proportional to the remaining size; repeating this enough times can yield a quadratic total.

Not every sequence of k removals costs k×n. A coarse upper bound is O(kn), but the exact sum depends on the index and list size at each step. When removing from the very end, the shift count can be 0 throughout the entire sequence.

## 6. Batching Insertions to Shift the Tail Fewer Times

Suppose the initial list has n elements, and we need to insert k elements at position p while preserving the batch order.

### 6.1. Inserting One by One at Advancing Positions

An illustrative snippet:

~~~java
for (int offset = 0; offset < block.size(); offset++) {
    values.add(p + offset, block.get(offset));
}
~~~

After each insertion, the list size increases by 1 and the insertion index also increases by 1. The old tail segment after p still has n−p elements and gets shifted k times.

The number of shifts of the old tail is:

~~~text
k * (n - p)
~~~

If both k and n−p are large, this is a substantial source of work. This formula counts only segment shifts, excluding any array growth, source reading, and writing of the k new elements.

If instead you insert every element at the same index p in source traversal order, previously inserted elements from the batch are also pushed right and the batch order becomes reversed. In that case, the number of shifts is:

~~~text
k * (n - p) + k(k - 1)/2
~~~

Both are "loops inserting k elements," yet the insertion index affects both the resulting order and the cost.

### 6.2. Using addAll(p, block)

With a separate, stable source collection, `addAll(p, block)` expresses the requirement of inserting the entire batch in source order.

In the OpenJDK implementation considered here, space is opened in the old tail for the entire batch in a single step, rather than shifting repeatedly for each element. When no array growth is required and the source can be processed linearly, the main work consists of:

~~~text
read/convert k source elements
+ shift n-p tail elements once
+ write k elements into the opened gap
~~~

The cost takes the form O(k + n−p), instead of the O(k(n−p)) shifting cost of element-by-element insertion. If the array must grow, add the cost of allocating the new array and copying elements into it.

For example, given `[10, 20, 30, 40]`, p = 1, and batch `[7, 8, 9]`:

- Inserting one by one at p+offset: shifts 3 tail references each time, for a total of 9.
- Inserting as a batch: shifts 3 tail references once, then places the 3 new elements.
- Both produce `[10, 7, 8, 9, 20, 30, 40]`.

Do not misread "3 shifts" as the entire cost of `addAll`: the method still has to process the batch, may allocate an intermediate array, and may grow the backing array. The comparison here isolates only the work caused by shifting the old tail.

Use a separate source that does not mutate during the operation. If the batch is a view sharing structure with the target list, create a stable copy of the source first rather than guessing how concurrent structural mutation behaves.

## 7. Removing Multiple Elements: Distinguishing Range Removal from Conditional Removal

### 7.1. Removing a Contiguous Range

To remove indices from a up to (but excluding) b, you can use:

~~~java
values.subList(a, b).clear();
~~~

Condition: `0 <= a <= b <= size()`. `subList` is a view of the original list, so calling `clear` on the view actually removes the corresponding elements from the original list; it does not merely clear a copy.

For a non-empty range of length k = b−a, an array-backed implementation can:

1. Shift the n−b elements after the range to the left in a single step.
2. Clear the k references at the old tail end.
3. Update the size and related structural state.

The main work has order O((n−b)+k), which simplifies to O(n−a). The removed range and the trailing elements determine the amount of work; removing k elements is not simply k position-independent operations.

For example, with n = 10, removing `[2, 6)`:

~~~text
before: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
              <--remove--> <keep & shift>

after:  [0, 1, 6, 7, 8, 9]
~~~

Only the four elements 6, 7, 8, 9 need to be shifted once, followed by clearing the four old trailing references.

If you called `remove(2)` four times instead, the number of shifts would be 7 + 6 + 5 + 4 = 22. The result is identical, but the tail was moved multiple times.

A view is not an independent list to hold onto while freely mutating the structure of the backing list. After removing a range, continue operating through a clear design on the original list; do not rely on stale views or iterators to preserve previous indices.

### 7.2. Conditional Removal

To remove all elements matching a predicate, you can use:

~~~java
values.removeIf(value -> value % 2 == 0);
~~~

This example assumes a list of integers that does not contain `null`. When data may contain `null`, the predicate must handle that case appropriately.

In OpenJDK 17, `ArrayList` provides its own `removeIf` implementation: it identifies which elements to drop and then compacts the surviving elements. This avoids removing elements one by one and shifting the same tail repeatedly.

With an O(1) predicate, filtering the entire list takes O(n) time under this implementation. You must add the cost of the predicate itself if it performs lookups, I/O, or heavy computation. The implementation also uses auxiliary memory to mark elements; do not assume every filter operation uses O(1) extra space.

Do not generalize this detail into a guarantee that `removeIf` on every `Collection` uses the same algorithm. When evaluating cost, you need to know the concrete data structure in use.

The predicate should only decide whether to keep or remove an element based on the data, without inserting into or removing from the list currently being filtered. A shifting optimization does not replace the requirement for operational correctness.

### 7.3. clear Is Not Repeated Front Removal

In the `ArrayList` implementation considered here, `clear()` nulls out the active references in a single pass and sets the size to 0. It does not need to preserve surviving elements because no elements are kept.

Consequently, discarding all n elements can be done linearly rather than calling `remove(0)` n times with quadratic total shifting. Even without tail shifting, there is still O(n) work to clear references; do not count only shifts and conclude that `clear` is always O(1).

## 8. Correctness When Removing During Iteration

### 8.1. Forward Traversal with Index Increment Can Skip Elements

Consider `[2, 4, 6, 7, 8]`. When at index 0 and removing 2, the value 4 shifts into index 0. If the loop immediately increments the index to 1, it never inspects 4.

The following snippet **intentionally illustrates this bug**:

~~~java
for (int index = 0; index < values.size(); index++) {
    if (values.get(index) % 2 == 0) {
        values.remove(index);
    }
}
~~~

It is not that "removing inside an index loop is always wrong"; the problem is that the index update rule must account for the tail having just shifted left. One could avoid incrementing the index after a removal, but that approach still pays the shifting cost on every single removal.

### 8.2. Backward Traversal Preserves Indices of Uninspected Elements

If you only remove positions that have already been inspected, iterating with a decreasing index ensures that earlier, uninspected elements never change their indices. This is a correct way to write many conditional removal loops.

However, it does not guarantee that every case becomes O(n). For example, suppose a list has n elements, and we want to remove the first k elements while keeping the last n−k elements. Even if we remove the target indices from right to left, the surviving tail is still shifted k times, producing k(n−k) shifts. When k is around n/2, the total work remains quadratic.

Backward traversal solves an index-management problem; batch compaction solves a repeated-work problem.

### 8.3. Iterator.remove Makes Mutation Legal, Not a Linked List

Using `Iterator.remove()` properly allows removing the current element while keeping the iterator state coordinated. With `ArrayList`, however, the underlying array still has to compact the tail segment on each individual removal.

Therefore, an iterator loop that removes many elements can still incur quadratic total cost. Preventing `ConcurrentModificationException` and reducing the number of shifted references are two separate goals.

Do not mutate list structure directly inside a `for-each` loop and rely on whether an exception is thrown to judge correctness. Fail-fast behavior only helps detect certain usage bugs; it is neither a synchronization mechanism nor a way to bypass shifting costs.

### 8.4. remove(1) Might Not Remove the Value 1

With `ArrayList<Integer>`:

~~~java
values.remove(1);                   // selects remove(int): removes index 1
values.remove(Integer.valueOf(1));  // selects remove(Object): finds and removes value 1
~~~

The two overloaded methods differ in both semantics and cost model. Removing by value must first search for a matching element; only if one is found does it compact the tail after it. You must not look solely at the final element's position and conclude that a find-and-remove operation is O(1).

For instance, removing a value located at the very end via `remove(Object)` requires zero reference shifts, yet it still has to scan through the preceding elements to find it. If the element's `equals` method is expensive, you must include that comparison cost as well.

## 9. Complete Program: Verifying Results and Counting Model Shifts

The following program runs real operations on `ArrayList` while calculating the number of shifts from the size and index prior to each operation.

The `shifts` variables are **counters based on the formulas in this article**, not readings from an internal JVM profiler. The program does not use reflection and does not measure wall-clock time. For the small insertion cases, capacity is pre-reserved so that shifting is isolated from array resizing.

### 9.1. Source Code

Save as `ArrayListShiftDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ArrayListShiftDemo {
    static <E> ArrayList<E> reservedCopy(List<E> source) {
        ArrayList<E> result = new ArrayList<>(32);
        result.addAll(source);
        return result;
    }

    static <E> void addAt(ArrayList<E> list, int index, E value) {
        int before = list.size();
        int logicalShifts = before - index;
        list.add(index, value);
        System.out.printf("add(%d, %s): shifts=%d, values=%s%n",
                index, value, logicalShifts, list);
    }

    static <E> void removeAt(ArrayList<E> list, int index) {
        int before = list.size();
        int logicalShifts = before - index - 1;
        E removed = list.remove(index);
        System.out.printf("remove(%d): removed=%s, shifts=%d, values=%s%n",
                index, removed, logicalShifts, list);
    }

    static ArrayList<Integer> numbers(int n) {
        ArrayList<Integer> result = new ArrayList<>(n);
        for (int value = 0; value < n; value++) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        ArrayList<String> trace = reservedCopy(List.of("A", "B", "C", "D", "E"));
        System.out.println("start: " + trace);
        addAt(trace, 0, "X");
        addAt(trace, 3, "Y");
        removeAt(trace, 0);
        removeAt(trace, 2);
        removeAt(trace, trace.size() - 1);

        ArrayList<Integer> front = new ArrayList<>(8);
        long frontInsertShifts = 0;
        for (int value = 1; value <= 8; value++) {
            frontInsertShifts += front.size();
            front.add(0, value);
        }
        System.out.printf("prepend 8: shifts=%d, values=%s%n",
                frontInsertShifts, front);
        long frontRemoveShifts = 0;
        while (!front.isEmpty()) {
            frontRemoveShifts += front.size() - 1;
            front.remove(0);
        }
        System.out.printf("drain front: shifts=%d, remaining=%s%n",
                frontRemoveShifts, front);

        ArrayList<Integer> back = numbers(8);
        long backRemoveShifts = 0;
        while (!back.isEmpty()) {
            int index = back.size() - 1;
            backRemoveShifts += back.size() - index - 1;
            back.remove(index);
        }
        System.out.printf("drain back: shifts=%d, remaining=%s%n",
                backRemoveShifts, back);
        long n = 100_000L;
        System.out.println("formula only, n=100000: " + n * (n - 1) / 2);

        List<Integer> base = List.of(10, 20, 30, 40);
        List<Integer> block = List.of(7, 8, 9);
        ArrayList<Integer> repeated = reservedCopy(base);
        long repeatedShifts = 0;
        for (int offset = 0; offset < block.size(); offset++) {
            int index = 1 + offset;
            repeatedShifts += repeated.size() - index;
            repeated.add(index, block.get(offset));
        }
        ArrayList<Integer> bulk = reservedCopy(base);
        int bulkTailShifts = bulk.size() - 1;
        bulk.addAll(1, block);
        System.out.printf("insert one by one: shifts=%d, values=%s%n",
                repeatedShifts, repeated);
        System.out.printf("insert addAll: tailShifts=%d, values=%s%n",
                bulkTailShifts, bulk);
        System.out.println("same insert result: " + repeated.equals(bulk));

        ArrayList<Integer> repeatedRemoval = numbers(10);
        long repeatedRemovalShifts = 0;
        for (int count = 0; count < 4; count++) {
            repeatedRemovalShifts += repeatedRemoval.size() - 2 - 1;
            repeatedRemoval.remove(2);
        }
        ArrayList<Integer> rangeRemoval = numbers(10);
        int rangeTailShifts = rangeRemoval.size() - 6;
        rangeRemoval.subList(2, 6).clear();
        System.out.printf("remove one by one: shifts=%d, values=%s%n",
                repeatedRemovalShifts, repeatedRemoval);
        System.out.printf("remove range: tailShifts=%d, values=%s%n",
                rangeTailShifts, rangeRemoval);
        System.out.println("same remove result: " + repeatedRemoval.equals(rangeRemoval));

        ArrayList<Integer> wrong = new ArrayList<>(List.of(2, 4, 6, 7, 8));
        for (int index = 0; index < wrong.size(); index++) {
            if (wrong.get(index) % 2 == 0) {
                wrong.remove(index);
            }
        }
        System.out.println("buggy forward i++: " + wrong);
        ArrayList<Integer> backward = new ArrayList<>(List.of(2, 4, 6, 7, 8));
        for (int index = backward.size() - 1; index >= 0; index--) {
            if (backward.get(index) % 2 == 0) {
                backward.remove(index);
            }
        }
        ArrayList<Integer> filtered = new ArrayList<>(List.of(2, 4, 6, 7, 8));
        boolean changed = filtered.removeIf(value -> value % 2 == 0);
        System.out.println("backward removal: " + backward);
        System.out.printf("removeIf: changed=%s, values=%s%n", changed, filtered);

        ArrayList<Integer> byIndex = new ArrayList<>(List.of(1, 2, 3));
        ArrayList<Integer> byValue = new ArrayList<>(List.of(1, 2, 3));
        byIndex.remove(1);
        byValue.remove(Integer.valueOf(1));
        System.out.println("remove(int 1): " + byIndex);
        System.out.println("remove(Integer 1): " + byValue);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListShiftDemo.java
java ArrayListShiftDemo
~~~

### 9.2. Standard Output

~~~text
start: [A, B, C, D, E]
add(0, X): shifts=5, values=[X, A, B, C, D, E]
add(3, Y): shifts=3, values=[X, A, B, Y, C, D, E]
remove(0): removed=X, shifts=6, values=[A, B, Y, C, D, E]
remove(2): removed=Y, shifts=3, values=[A, B, C, D, E]
remove(4): removed=E, shifts=0, values=[A, B, C, D]
prepend 8: shifts=28, values=[8, 7, 6, 5, 4, 3, 2, 1]
drain front: shifts=28, remaining=[]
drain back: shifts=0, remaining=[]
formula only, n=100000: 4999950000
insert one by one: shifts=9, values=[10, 7, 8, 9, 20, 30, 40]
insert addAll: tailShifts=3, values=[10, 7, 8, 9, 20, 30, 40]
same insert result: true
remove one by one: shifts=22, values=[0, 1, 6, 7, 8, 9]
remove range: tailShifts=4, values=[0, 1, 6, 7, 8, 9]
same remove result: true
buggy forward i++: [4, 7]
backward removal: [7]
removeIf: changed=true, values=[7]
remove(int 1): [1, 3]
remove(Integer 1): [2, 3]
~~~

### 9.3. Reading Each Output Group

The group from `start` to `remove(4)` shows that n is taken immediately before each operation, rather than staying fixed at the initial size:

- Inserting at the front when there are 5 elements: shifts 5.
- Next, inserting at index 3 when there are 6 elements: shifts 6−3 = 3.
- Removing from the front when there are 7 elements: shifts 7−0−1 = 6.
- Removing at index 2 when there are 6 elements: shifts 6−2−1 = 3.
- Removing from the end when there are 5 elements: shifts 5−4−1 = 0.

The front-prepend and front-drain groups both yield a total of 28 shifts for 8 elements. Draining from the back yields 0 shifts. Both draining approaches leave the list empty, but the amount of work differs.

The line with n = 100,000 only evaluates the formula using `long`; the program does not actually run a loop performing billions of shifts. That keeps the example from turning into a slow benchmark just to demonstrate an arithmetic sum.

The two `same ... result: true` pairs confirm that the element-by-element approach and the bulk approach produce identical content and order on the test data. The `tailShifts` counter for the bulk approach counts only the old tail segment, excluding source copying or clearing trailing references.

The line `buggy forward i++: [4, 7]` shows that an even number was skipped. Backward traversal and `removeIf` both produce `[7]`; the fact that two correct approaches produce the same output does not mean they have the same cost across all inputs.

The last two lines distinguish method overloads: `remove(1)` removes the element 2 at index 1, whereas `remove(Integer.valueOf(1))` removes the value 1.

### 9.4. Scope of the Evidence

The execution output verifies the resulting contents, indices, and arithmetic sums for the given cases. It does not directly measure bytes read/written, CPU instructions, or wall-clock time per operation.

The order-of-growth conclusions come from analyzing the length of the segment that must be processed. Actual runtime performance is also affected by the JVM, CPU caches, data size, allocations, and machine load. To compare execution times, you need a dedicated, controlled benchmark; do not extrapolate a fixed speed ratio from these logical counters.

## 10. Choosing a Representation That Matches Your Access Pattern

### 10.1. Heavy Index-Based Reads, End Appends, and Iteration

This is the usage pattern where `ArrayList` fits naturally. Occasional modifications in the middle can be perfectly acceptable, especially when the data size is small or changes are batched.

There is no need to switch data structures merely because a single operation is O(n). Consider the frequency of calls, the actual scale, and which part of the overall algorithm dominates the work.

### 10.2. Frequent Insertions and Removals at Both Ends

If the problem models a queue or double-ended queue, consider `ArrayDeque` and use operations such as `addLast`, `pollFirst`, `addFirst`, and `pollLast`. This structure avoids shifting the entire sequence back to index 0 after every front removal.

`ArrayDeque` performs most operations in amortized constant time, but it does not provide arbitrary index-based element access like `List` and does not permit `null` elements. Consequently, switching structures must match both your API and data requirements, as documented in the [Java 17 ArrayDeque documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

### 10.3. Middle Insertions and Removals: Do Not Blindly Switch to LinkedList

`LinkedList` can update node links in constant time once it is positioned via an appropriate iterator. However, `linkedList.add(i, x)` or `remove(i)` still has to traverse to the node at index i.

The [Java 17 LinkedList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) states that index-based operations traverse from either the beginning or the end, whichever is closer. Therefore, replacing `ArrayList` with `LinkedList` while keeping an index-based loop may simply trade array shifting cost for node-pointer chasing cost.

You need to consider how positions are located, the traversal style, node allocations, memory overhead, and real workload behavior. "O(1) middle insertion" is meaningful only when you specify how direct access to the target position was already obtained.

### 10.4. Many Modifications When Building a New Result Is Allowed

If the input list does not need to be mutated in place, a single pass that builds a new result list via end appends is often simpler and faster than a series of middle insertions or removals. This approach trades the memory of a new result list for avoiding repeated shifts of the same elements.

Be sure to check the semantics: do callers holding references to the old list need to see the changes directly? Must the identity of the list object itself be preserved? Optimizing by creating a new list cannot automatically substitute for an in-place update.

### 10.5. Finding a Position Quickly Does Not Make the Update Step Equally Fast

In a sorted list, finding the insertion point via binary search takes O(log n) comparisons. Once the index is found, however, `ArrayList` still has to open a gap by shifting the tail.

Therefore, a search-then-insert operation can still be O(n) due to the update step. Keep **locating the position**, **shifting data**, and **processing elements** separate during analysis; do not take the complexity of the fastest step as the complexity of the entire operation.

## 11. Common Reasoning Pitfalls

| Misconception | Correction |
|---|---|
| Index access is O(1), so inserting at an index is also O(1) | Insertion must open a gap and preserve element order |
| Pre-allocating capacity means front insertion does not need to shift | Spare capacity at the end is not located at the insertion index |
| Middle insertion only shifts half the list, so it is not linear | Half of n still has order Θ(n) |
| Removing the last element by value is guaranteed to be O(1) | Searching by value may require scanning the entire list |
| Using arraycopy makes block shifting O(1) | The number of processed slots still grows with the block length |
| Using Iterator.remove makes bulk removal always O(n) | Each individual removal on an ArrayList still compacts the tail |
| Backward traversal makes all removals run in linear time | It preserves uninspected indices, but can still shift a surviving tail repeatedly |
| addAll does not shift anything because it inserts in bulk | It still opens space; the benefit is shifting the tail once instead of repeatedly |
| Removing a range via subList only affects a copy | subList is a view; calling clear mutates the backing list |
| Shifting references means deep-copying objects | The identities of element objects are preserved |
| Amortized O(1) end appends imply front insertions are also O(1) | Front shifting happens on every call, unlike periodic capacity growth |
| Zero shifted references means the entire operation has zero cost | Searching, state updates, writing/clearing references, and other bookkeeping still occur |

## 12. Self-Check Exercises

### Exercise 1: Counting by Index

A list has n = 12. How many elements must be shifted when inserting at i = 4? On a separate list that also has n = 12, how many elements must be shifted when removing at i = 4?

**Explanation:** Insertion shifts 12−4 = 8 elements. Removal shifts 12−4−1 = 7 elements. Two independent lists are used in the question so that n does not change between the two calculations.

### Exercise 2: Does Large Capacity Help?

A list has size = 1,000 and reserved capacity = 10,000. Does inserting an element at the front require shifting?

**Explanation:** Yes, all 1,000 existing references must be shifted. Having sufficient capacity only avoids growing the backing array on this insertion.

### Exercise 3: Removing a Range

A list has 20 elements. Removing the range `[5, 12)` as a batch operation requires shifting how many tail elements and clearing how many old trailing references?

**Explanation:** There are 20−12 = 8 tail elements to shift, and 12−5 = 7 old trailing slots whose references must be cleared. These are two distinct parts of the work; both should be accounted for.

### Exercise 4: Backward Traversal

Can we conclude that "removing elements at even indices using a decreasing-index loop on an ArrayList is always O(n)"?

**Explanation:** No. Iterating backward avoids skipping elements due to index shifts in the uninspected prefix, but many surviving elements toward the back can still be shifted repeatedly. You must sum the tail lengths across all removals, or use an appropriate single-pass filter/compaction approach.

### Exercise 5: Batch Insertion

A list has n = 1,000, and we insert k = 100 elements at p = 200. If we insert one by one at p+offset, how many total shifts does the old tail undergo? What if we open space for the entire batch in a single step?

**Explanation:** The old tail has length 800. Inserting one by one causes 100×800 = 80,000 shifts of the old tail. Opening space for the batch shifts the 800 tail references once. Both approaches also have to process the 100 source elements, plus any array-growth work if capacity is exceeded.

### Exercise 6: Preserving Requirements When Optimizing

If a requirement states that `[A, B, C, D]` must keep its order `[A, C, D]` after removing B, can we overwrite B with D and remove the last element to get `[A, D, C]` in order to avoid shifting?

**Explanation:** No, the resulting order differs from what is required. An optimization is valid only when it preserves the observable behavior required by the application.

When you encounter a loop that inserts or removes at the beginning or middle, identify which tail segment must shift, determine its length at each step, and sum across the entire sequence. That is how you see the true cost of an array-backed structure and choose batching, an algorithmic change, or a different data structure for a concrete reason.
