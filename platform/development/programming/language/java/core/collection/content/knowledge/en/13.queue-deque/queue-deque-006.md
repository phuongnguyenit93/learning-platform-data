# ArrayDeque: Circular Array, Resizing, and Double-Ended Operations

## 1. Why Can an Array-Backed Deque Still Operate Efficiently at the Front?

If you use a naive linear array to represent a queue, removing the first element can require shifting all remaining elements to the left. Doing that repeatedly causes the work to grow with the length of the sequence.

ArrayDeque avoids that organization. It keeps data in a resizable array and manages the two end positions circularly. When removing from the front, it mainly clears the reference in one slot and advances the front position; there is no need to shift the entire sequence after every removal.

The three core ideas of the structure are:

- **Circular array:** the logical order can wrap past the end of the array and continue at the beginning of the array.
- **Double-ended:** add, inspect, and remove at first or last using appropriate position updates.
- **Resizing:** when the current array does not have enough space, allocate a larger array and preserve the exact order of elements.

The [Java 17 ArrayDeque documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html) describes it as a resizable-array implementation of Deque with no caller-imposed capacity restrictions, prohibiting null elements, and not thread-safe when accessed concurrently without external synchronization.

This article distinguishes two layers:

1. **Usage contract:** which elements are added/removed, what order is observed, and what happens when empty.
2. **Implementation model:** the backing array, the two end positions, wraparound, and allocation during resizing.

The index diagrams are a model for understanding the mechanism. Do not use them to infer a specific internal index after an API call across all JDKs.

## 2. Logical Sequence vs. Physical Slot Order

Suppose the Deque currently represents the sequence:

```text
first -> A, B, C, D, E <- last
```

A does not have to be at slot 0, nor E at slot 4. One possible layout in an 8-slot circular array is:

```text
index:   0   1   2   3   4   5   6   7
content: C   D   E   .   .   .   A   B
                                 ^
                                head

tail = 3, the slot where the next add-last will write
. represents an empty slot in the model
```

Reading forward from head along the array:

```text
6 -> 7 -> 0 -> 1 -> 2
A    B    C    D    E
```

The logical order is still A, B, C, D, E even though it spans two segments at opposite ends of the array.

This is what “circular” means: an index wraps back to the beginning when it moves past the last slot. It does not mean the array slots in memory are physically linked into a ring.

### 2.1. head and tail Have Different Roles

In the model matching the OpenJDK 17 implementation:

- `head` is the index of the first element when the sequence is non-empty.
- `tail` is the index that will be used for the next addition at last.
- The current last element sits at the position one step behind tail.
- In a steady empty state, head equals tail.

In particular, tail is not always the index of the current last element. If tail equals 0, the position immediately preceding it circularly is the last slot of the array.

There is no need to use reflection to read those fields in application code. The API provides `peekFirst`, `peekLast`, `getFirst`, and `getLast` to read both ends according to the contract.

### 2.2. Distinguishing size from the Backing Array Length

Let:

```text
n = number of elements currently present
L = number of slots in the backing array
```

n and L are not the same quantity. The array may have spare capacity; some designs also reserve an empty slot to distinguish states.

ArrayDeque has no standard public method to query the exact length of the internal array. `size()` returns the number of elements, not the number of allocated slots.

The constructor that takes a number prepares an initial capacity; it does not promise that the physical array has that exact number of slots, nor does it set a maximum bound of that many elements.

## 3. Advancing or Retreating an Index Circularly

One way to illustrate advancing and retreating an index is:

```java
// Illustrative helper methods placed inside an enclosing class.
// Precondition: length > 0 and 0 <= index < length.
static int nextIndex(int index, int length) {
    return index + 1 == length ? 0 : index + 1;
}

static int previousIndex(int index, int length) {
    return index == 0 ? length - 1 : index - 1;
}
```

This is model code, not source code copied verbatim from ArrayDeque. It clearly expresses the boundary behavior:

```text
nextIndex(7, 8)     -> 0
previousIndex(0, 8) -> 7
```

Do not arbitrarily apply a bitmask formula such as `(index + 1) & (length - 1)` unless you have the precondition that length is a power of two. The circular array model itself does not require the array length to have that form.

When reading different JDK versions, the details of choosing the length and the index-update formula may differ. The ArrayDeque contract does not promise that every version keeps the same array length or the same growth factor.

### 3.1. Computing the Element Count in a Model with One Empty Slot

With the convention that head is the data-bearing front and tail is the next write slot, the number of elements in a steady state can be computed using circular distance:

```text
n = tail - head                  if tail >= head
n = tail - head + L              if tail < head
```

In the initial diagram:

```text
head = 6, tail = 3, L = 8
n = 3 - 6 + 8 = 5
```

This formula goes with the state convention of this model. In another circular structure that allows every slot to be filled and maintains a separate count variable, head equaling tail may need a different interpretation.

Do not take one circular-array formula and apply it blindly to every implementation.

## 4. The Four Core Double-Ended Operations

Starting again from the illustrative layout:

```text
index:   0   1   2   3   4   5   6   7
content: C   D   E   .   .   .   A   B
head = 6
tail = 3
logical = [A, B, C, D, E]
```

Assume the steps below do not yet require growing the array.

### 4.1. Add Last

To add F at last:

1. Write F into the current tail slot, slot 3.
2. Advance tail one step circularly.

```text
head = 6
tail = 4
logical = [A, B, C, D, E, F]
```

There is no need to move A, B, C, D, E to new positions.

### 4.2. Remove First

To remove first:

1. Read A at head.
2. Clear the reference in that slot.
3. Advance head one step circularly.

```text
returns A
head = 7
tail = 4
logical = [B, C, D, E, F]
```

“Clearing” here does not necessarily destroy object A in memory. It removes the reference from the Deque's slot; the object may still be held by another reference.

### 4.3. Add First

From that state, add X at first:

1. Retreat head one step circularly.
2. Write X into the new head slot.

```text
head = 6
tail = 4
logical = [X, B, C, D, E, F]
```

The order of B, C, D, E, F remains intact.

### 4.4. Remove Last

To remove last:

1. Step back from tail to the position of the last element.
2. Read F there.
3. Clear the reference and update tail to the slot just vacated.

```text
returns F
head = 6
tail = 3
logical = [X, B, C, D, E]
```

Comparison table for the entire sequence:

| Step | head | tail | Logical sequence after step |
|---|---:|---:|---|
| Initial | 6 | 3 | A, B, C, D, E |
| Add last F | 6 | 4 | A, B, C, D, E, F |
| Remove first | 7 | 4 | B, C, D, E, F |
| Add first X | 6 | 4 | X, B, C, D, E, F |
| Remove last | 6 | 3 | X, B, C, D, E |

The number of position updates per step is small and constant when no resizing is needed. That is why ArrayDeque handles both ends differently from a naive linear array that always shifts content toward slot 0.

## 5. Empty State, Empty Slots, and Null Policy

In the [OpenJDK 17 ArrayDeque source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayDeque.java), slots not holding an element are set to null; in steady state, there is an empty slot at tail. When an addition temporarily fills the array, the growth mechanism restores the necessary gap.

Those details explain the model in use, not an API for applications to manipulate directly.

### 5.1. head Equals tail in the Empty State

After removing everything, head and tail meet. They do not have to end up at slot 0 after every sequence of polls; the exact index is an internal detail.

A clear operation may reset the positions according to the implementation's choice. Callers should rely only on size being 0, isEmpty being true, and the empty-state behavior of the methods.

### 5.2. Null Is Not a Valid Element

ArrayDeque forbids adding null. As a result, null can be used unambiguously as the sentinel return value indicating no element in poll and peek.

Prohibiting null also aligns with using null to mark empty slots in this implementation. However, do not conclude that no circular array could theoretically support null: a different design could use count tracking or another marker.

If domain data has a field that may be missing, represent it inside a non-null object, or choose an explicit input policy. Do not use a null element as a special-purpose signal in ArrayDeque.

### 5.3. Empty State: Methods Returning null vs. Methods Throwing Exceptions

| Intent | Returns null when empty | Throws NoSuchElementException when empty |
|---|---|---|
| Inspect first only | `peekFirst()` | `getFirst()` |
| Inspect last only | `peekLast()` | `getLast()` |
| Retrieve and remove first | `pollFirst()` | `removeFirst()` |
| Retrieve and remove last | `pollLast()` | `removeLast()` |

Adding null still throws NullPointerException even when calling offer. “Returning a status value” does not mean every invalid input is converted into false or null.

## 6. Mapping the API to Queues and Stacks

From the four underlying operations, two familiar policies can be built:

```text
FIFO: add last, remove first
LIFO: add first, remove first
```

Deque's shorthand method names follow the same convention:

| Common name | Corresponding double-ended operation |
|---|---|
| `offer(e)` | `offerLast(e)` |
| `poll()` | `pollFirst()` |
| `peek()` | `peekFirst()` |
| `push(e)` | `addFirst(e)` |
| `pop()` | `removeFirst()` |

With FIFO, an element added at last waits for elements toward first to be removed ahead of it. With LIFO, a newly added first element sits right in front of older elements and is removed first.

You could also build a stack at the last end if you both add and remove at last, but the API's push/pop names place the top at first. Keep one consistent convention.

The circular mechanism does not itself decide FIFO or LIFO. It provides efficient operations at both ends; calling code selects the policy through the pair of operations it uses.

## 7. Program 1: Observing Operations at Each End

Save the file `ArrayDequeEndsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class ArrayDequeEndsDemo {
    public static void main(String[] args) {
        Deque<String> values = new ArrayDeque<>();
        values.addLast("B");
        values.addLast("C");
        values.addFirst("A");

        System.out.println("initial = " + values);
        System.out.println("peek first = " + values.peekFirst());
        System.out.println("peek last = " + values.peekLast());
        System.out.println("offer first X = " + values.offerFirst("X"));
        System.out.println("offer last D = " + values.offerLast("D"));
        System.out.println("after offers = " + values);
        System.out.println("poll first = " + values.pollFirst());
        System.out.println("poll last = " + values.pollLast());
        System.out.println("after polls = " + values);

        values.push("TOP");
        System.out.println("after push = " + values);
        System.out.println("pop = " + values.pop());
        System.out.println("remove first = " + values.removeFirst());
        System.out.println("remove last = " + values.removeLast());
        System.out.println("one member = " + values);
        System.out.println("get first = " + values.getFirst());
        System.out.println("get last = " + values.getLast());
        System.out.println("take final member = " + values.pollFirst());
        System.out.println("empty = " + values.isEmpty());
        System.out.println("empty poll = " + values.pollFirst());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ArrayDequeEndsDemo.java
java ArrayDequeEndsDemo
```

Output from the verification run:

```text
initial = [A, B, C]
peek first = A
peek last = C
offer first X = true
offer last D = true
after offers = [X, A, B, C, D]
poll first = X
poll last = D
after polls = [A, B, C]
after push = [TOP, A, B, C]
pop = TOP
remove first = A
remove last = C
one member = [B]
get first = B
get last = B
take final member = B
empty = true
empty poll = null
```

The programs in this article use language features and APIs available in Java 17 and later, compiled with `--release 17` and verified on Azul OpenJDK 24.0.2.

The output shows the logical sequence from first to last, not a printout of the physical array. You can trace:

- AddFirst places A before B, C.
- OfferFirst and offerLast add on opposite sides.
- PollFirst and pollLast remove the exact two elements just added at both ends.
- Push places TOP at first; pop retrieves TOP itself.
- When only B remains, both ends read B.
- After removing B, the next poll returns null.

The peek and get calls only inspect elements. They do not move head or tail to remove data.

You cannot infer what head currently equals from the printed sequence. What you should verify by contract is the order and results; the actual slot positions belong to the implementation.

## 8. What Happens When the Circular Array Runs Out of Space?

Wraparound only reuses slots that are already empty. If the element count keeps growing and no room remains under the storage convention, wrapping back to slot 0 does not create extra capacity.

ArrayDeque grows the array to continue holding existing elements and new ones. The general idea:

```text
current array lacks space
    -> compute an appropriate new size
    -> allocate a larger array
    -> transfer the references to keep
    -> adjust the two end positions
    -> continue representing the same logical sequence
```

### 8.1. Order Must Be Preserved, Even When Data Wraps Around

Suppose the old content is split into two physical segments:

```text
end of array:   A, B
start of array: C, D, E
logical order:  A, B, C, D, E
```

After growing the array, the logical order must still be A, B, C, D, E. Naively copying slots by physical index while ignoring head would produce C, D, E, A, B and corrupt the Deque.

One way to picture the new array is:

```text
[A, B, C, D, E, ., ., ., ...]
```

This is a valid illustrative layout, not a promise that ArrayDeque always packs head back to 0 after resizing. An implementation may relocate segments differently as long as it preserves order and invariants.

### 8.2. Resizing Transfers References, Not Deep Copies of Objects

The backing array holds references to elements. Resizing does not clone each domain object by default.

If an object is also referenced outside the Deque, growing capacity does not split it into a separate copy. What is reorganized are the slots holding references.

Similarly, a Deque<Integer> also has integer objects due to boxing; you should not assume the entire object data lies contiguously in the array just because the references are stored in an array.

### 8.3. Do Not Rely on a Fixed Growth Factor in Application Code

The ArrayDeque contract does not let callers configure a growth factor and does not promise a fixed sequence of internal capacities.

OpenJDK 17's source code computes growth based on the current size and the needed amount. Do not turn this into a rule that “it always doubles” or “the length is always a power of two.”

If you need to analyze the mechanism, specify the implementation version you are reading. If you are writing application code, rely on the self-growing capacity contract and appropriate costs, not on resize timing guessed from an internal number.

## 9. Why Does Insertion Have Amortized O(1) Cost Yet Occasionally Take O(n)?

A typical insertion may only need to write one slot and update one position. However, an insertion that lands right when resizing is needed has to process many existing references.

If n elements are nearly filling the array, one resize can take O(n) time. Therefore, there is no guarantee that every individual addFirst or addLast always runs in constant time.

The concept of **amortization** looks at the total work across a sequence of operations, then spreads the cost of those resizes over the insertions served by the new capacity.

### 9.1. The Idea of Proportional Growth

In a model that grows by a factor g > 1, the total amount of data copied across resizes forms a geometric series:

```text
C + gC + g²C + ... + gᵏC
```

That sum is on the same order as its largest term. If you build a sequence with m insertions starting small, the total data-movement cost is bounded by O(m), alongside the m element writes.

Thus, the total can be O(m), leading to O(1) amortized per insertion. Real-world thresholds and rounding do not require a single exact formula to understand this idea.

This is an analysis of a sequence of operations, not a probability claim that “most random data will be fast.” Nor does it mean a requirement for a tight worst-case per-operation latency bound is satisfied.

### 9.2. Setting Accurate Performance Expectations

| Operation | How to understand it in this ArrayDeque model |
|---|---|
| Add first/last | O(1) amortized; a single call needing resize can be O(n) |
| Remove first/last | Updates the end index and clears the reference, without shifting the whole sequence |
| Inspect first/last | Accesses the corresponding end position |
| size | Computed from index state, without traversing every element |
| contains by value | May have to search through n elements |
| remove by value or occurrence | May have to search and shift part of the data |
| Full traversal | O(n) in the number of elements read |

This table does not give every method on the Deque interface the same cost. `removeFirst()` and `remove(Object)` have similar names but do two different jobs.

Complexity also assumes element operations such as equals have appropriate cost. If equals is very expensive, searching by value carries that additional cost.

### 9.3. Preparing Capacity When Scale Is Known

If you expect a large number of elements, the constructor taking an initial capacity can reduce resizing during the initial phase:

```java
// Snippet: prepare for the expected scale, without setting a hard limit.
Deque<String> pending = new ArrayDeque<>(1_000);
```

In return, a large upfront allocation has a memory cost. Do not pick a huge number just to avoid every resize without understanding the actual workload.

If the scale exceeds your estimate, ArrayDeque can still grow. It does not reject the 1,001st element just because the constructor received 1000.

## 10. Program 2: Remove from Front, Add to Back, Then Keep Using Both Ends

Save the file `ArrayDequeMixedEndsDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;

public class ArrayDequeMixedEndsDemo {
    public static void main(String[] args) {
        Deque<Integer> values = new ArrayDeque<>(8);
        for (int value = 0; value < 6; value++) {
            values.addLast(value);
        }
        System.out.println("initial = " + values);

        List<Integer> removedFront = new ArrayList<>();
        for (int count = 0; count < 4; count++) {
            removedFront.add(values.removeFirst());
        }
        System.out.println("removed front = " + removedFront);
        System.out.println("after front removals = " + values);

        for (int value = 6; value <= 12; value++) {
            values.addLast(value);
        }
        System.out.println("after tail additions = " + values);

        values.addFirst(3);
        values.addFirst(2);
        System.out.println("after front additions = " + values);
        System.out.println("remove last one = " + values.removeLast());
        System.out.println("remove last two = " + values.removeLast());
        System.out.println("forward = " + new ArrayList<>(values));

        List<Integer> reverse = new ArrayList<>();
        Iterator<Integer> iterator = values.descendingIterator();
        while (iterator.hasNext()) {
            reverse.add(iterator.next());
        }
        System.out.println("reverse = " + reverse);

        List<Integer> drained = new ArrayList<>();
        Integer next;
        while ((next = values.pollFirst()) != null) {
            drained.add(next);
        }
        System.out.println("drained = " + drained);
        System.out.println("empty after drain = " + values.isEmpty());
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ArrayDequeMixedEndsDemo.java
java ArrayDequeMixedEndsDemo
```

Output from the verification run:

```text
initial = [0, 1, 2, 3, 4, 5]
removed front = [0, 1, 2, 3]
after front removals = [4, 5]
after tail additions = [4, 5, 6, 7, 8, 9, 10, 11, 12]
after front additions = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
remove last one = 12
remove last two = 11
forward = [2, 3, 4, 5, 6, 7, 8, 9, 10]
reverse = [10, 9, 8, 7, 6, 5, 4, 3, 2]
drained = [2, 3, 4, 5, 6, 7, 8, 9, 10]
empty after drain = true
```

The program creates a useful sequence of operations to test sequence continuity:

1. Add a group at last.
2. Remove some at first.
3. Add several more values at last.
4. Add at first.
5. Remove at last.
6. Traverse in both directions, then drain from first.

Sequences like this exercise advancing/retreating both end positions and reusing freed space in a circular-array implementation. However, the program does not read internal indices, so the output is not a measurement of “on which exact call did resize happen.”

### 10.1. Iteration Order Is Logical Order

`new ArrayList<>(values)` collects the sequence from first to last, producing `[2, 3, ..., 10]`.

`descendingIterator()` reads in the opposite direction, producing `[10, 9, ..., 2]`. It does not modify the Deque's contents.

Whether the data currently sits in one contiguous segment or wraps across two physical segments, the iterator and toArray must still reflect the proper logical order.

### 10.2. Draining Without Knowing head/tail Yourself

Looping pollFirst until null extracts the same sequence `[2, 3, ..., 10]` and then stops.

Because ArrayDeque forbids null elements, null here signals the end of data. Calling code does not need to know whether the next element sits at the end of the array or has wrapped back to slot 0.

That is the value of using a standard collection: index mechanics are encapsulated, while application code works with order and the meaning of the two ends.

### 10.3. Do Not Test Against a Guessed Array Shape

A test asserting “after this sequence head must equal 6” depends on an internal layout that is not part of the API. The same output sequence can be produced by implementation versions with different capacities and indices.

What you should protect is no lost elements, no unintended duplicates, the right order, and the right return values after each operation.

## 11. Program 3: Growing Through Multiple Levels While Preserving All Data

Save the file `ArrayDequeGrowthDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class ArrayDequeGrowthDemo {
    public static void main(String[] args) {
        Deque<Integer> values = new ArrayDeque<>(1);
        int count = 10_000;

        for (int value = 0; value < count; value++) {
            values.addLast(value);
        }

        System.out.println("size after additions = " + values.size());
        System.out.println("first = " + values.getFirst());
        System.out.println("last = " + values.getLast());

        int expected = 0;
        long checksum = 0L;
        Integer next;
        while ((next = values.pollFirst()) != null) {
            if (next != expected) {
                throw new AssertionError("Order differs at " + expected);
            }
            checksum += next;
            expected++;
        }
        if (expected != count) {
            throw new AssertionError("Element count differs");
        }

        System.out.println("verified elements = " + expected);
        System.out.println("checksum = " + checksum);
        System.out.println("empty after drain = " + values.isEmpty());

        values.addFirst(1);
        values.addFirst(2);
        values.addFirst(3);
        System.out.println("reuse at front = " + values);
        values.clear();
        System.out.println("size after clear = " + values.size());
        values.addLast(7);
        System.out.println("reuse after clear = " + values);
    }
}
```

Compile and run from the directory containing the file:

```shell
javac --release 17 -encoding UTF-8 ArrayDequeGrowthDemo.java
java ArrayDequeGrowthDemo
```

Output from the verification run:

```text
size after additions = 10000
first = 0
last = 9999
verified elements = 10000
checksum = 49995000
empty after drain = true
reuse at front = [3, 2, 1]
size after clear = 0
reuse after clear = [7]
```

The requested initial capacity is small, yet the program adds 10,000 values. It verifies every element upon removal, not just size at the end.

### 11.1. Verifying Order and Count Separately

In the removal loop:

- Each element must equal expected.
- Expected increments after each removal.
- After stopping, the total element count must equal count.

If you only checked the checksum, some missing/duplicate or order-swapping bugs could go undetected. Therefore, the program also checks each value sequentially.

Checksum `49,995,000` is the sum from 0 to 9999. Using a long variable keeps the pattern easy to scale up without relying on an int accumulator that is too small when growing the test size.

### 11.2. This Is a Correctness Check, Not a Benchmark

The program does not measure time and does not inspect internal capacity. It confirms that across scale growth, the sequence is preserved and the Deque can be reused after draining.

You cannot infer from a single passing run a latency bound for each add, a specific growth factor, or the maximum usable capacity on every machine.

### 11.3. Reusable After drain and clear

After draining, the program adds 1, 2, 3 at first so the sequence becomes `[3, 2, 1]`. Clear sets size back to 0; adding 7 at last afterward still works.

The empty state is a normal usage state, not a sign that the ArrayDeque instance has been destroyed.

## 12. Memory After Removing Elements and After clear

On each removal from first/last, the implementation clears the reference in the vacated slot. That prevents the backing array from continuing to hold an object merely because an old slot was not cleared.

However, two kinds of memory must be distinguished:

1. Element objects and the objects they reference.
2. The backing array containing the Deque's reference slots.

Removing an element drops one reference from the Deque. The object may become eligible for garbage collection if no other reference holds it elsewhere. You cannot conclude the object is collected immediately.

### 12.1. Shrinking size Does Not Mean the Array Shrinks Immediately

In the OpenJDK 17 implementation under discussion, removing elements does not automatically shrink the array after each deletion; clear nulls out references and resets state without automatically allocating a smaller array.

Therefore, a Deque that once reached a very high peak may still hold a large backing array when the current element count is small.

You can express storage cost in terms of the backing array length L, rather than always tying it to the current n. L can be significantly larger than n after a high-load period.

### 12.2. When You Need to Detach from the Old Backing Array

If you need to keep the remaining data in a fresh container, you can create:

```java
// Snippet: create a separate container from the current order.
ArrayDeque<String> compactCopy = new ArrayDeque<>(remaining);
```

The constructor builds a new Deque from the elements of the source collection in iterator order. It is not a public call to directly modify the old object's capacity.

Afterward, you must manage references to the old container if the goal is to stop retaining it. If other parts of the code still hold the old object, reassigning a variable in one place does not make it go away.

The copy still shares the element objects; this is not a deep copy of domain data.

### 12.3. Do Not Treat Auto-Growth as Infinite Memory

ArrayDeque has no caller-set fixed capacity bound like a bounded queue, but it is still subject to JVM array and memory limits.

If a producer thread generates work faster than a consumer thread processes it over a long period, auto-growth does not replace load control or application-level bounding policies.

Requirements to block when full, reject on overload, or coordinate multiple threads need structures and workflows with the right contracts. The constructor taking an initial capacity does not provide those capabilities.

## 13. Common Mistakes When Reasoning from a Circular Array

| Claim or practice | Problem | Correct understanding |
|---|---|---|
| The first element is always at slot 0 | Ignores head | First is the current logical position |
| tail always points to the last element | Confuses the next-write-slot convention | Last sits one step behind tail |
| head greater than tail is a broken state | Data can wrap around | Read past the end of the array and continue at the start |
| Removing first must shift all elements | Confuses with a naive linear array | Advance head and clear the vacated slot |
| Wraparound means overwriting unremoved data | Forgets the out-of-space condition | ArrayDeque grows the array when needed |
| Every resize doubles capacity | Not an API contract | Growth mechanics are an implementation detail |
| Array length is always a power of two | Cannot be inferred from the circular model | Use the index formula matching the design |
| Amortized O(1) means every add is O(1) | Ignores resize steps | One call can be O(n); the sequence total has the amortized bound |
| `new ArrayDeque<>(n)` caps at n elements | Confuses initial capacity with a bound | It prepares initial capacity |
| Clear always returns the large array to the JVM | Not true for the implementation examined | Distinguish clearing element references from replacing the backing array |
| Remove by value is as cheap as removeFirst | Requires searching and shifting content | Choose the right double-ended operation |
| Use null to mark a special element | ArrayDeque does not accept null | Use an explicit valid type or value |

A usage-level mistake is iterating with an iterator while structurally modifying the Deque through another method. The iterator is not a snapshot; concurrent modification may be detected and throw ConcurrentModificationException.

If you need to consume from one end, use an appropriate poll/remove loop. If you only need an independent stable read, consider a copy. Do not rely on fail-fast behavior as a multithreaded synchronization mechanism.

ArrayDeque is not safe for uncoordinated concurrent access. Correctness of circular index arithmetic and consistency across multiple threads are two separate concerns.

## 14. Choosing ArrayDeque and What to Test

ArrayDeque is often a good fit when you need to hold a non-null sequence, add/remove primarily at both ends, and do not need index-based access through the API.

Before choosing it, determine:

- Do you only need FIFO, only LIFO, or genuinely both ends?
- Is empty a normal state or an assumption violation?
- How large can the pending workload grow?
- Do you need a hard bound, blocking, or multithreaded coordination?
- Are there frequent mid-sequence search/removal operations?
- Is there a maximum latency requirement that amortized analysis does not satisfy?

Do not choose it based on a blanket claim that “arrays are always faster than linked lists.” The structure, operation mix, memory, and environment all affect the evaluation.

### 14.1. Useful Test Sequences

Cases worth testing directly through the API:

1. Empty, one element, then empty again.
2. Repeated add/remove at first.
3. Repeated add/remove at last.
4. Add at last while removing at first across many wraparounds.
5. Interleaved additions at both ends, followed by removals at both ends.
6. Start small then add many, verifying full order and count.
7. Drain, clear, then reuse.
8. Duplicate values are retained in the exact count.
9. Null is rejected at the designed boundary.
10. Forward and reverse iteration produce corresponding orders.

You do not need to know the exact moment the array grows to test the contract of calling code. If your specific goal is to analyze a JDK version, use the appropriate source code and measurement tools, and state the version explicitly.

### 14.2. Do Not Use Deque's equals Like List's equals

ArrayDeque does not define equals by sequence content the way List does. When you need to compare order, collect removed values into a List or compare element by element using an explicit procedure like Program 3.

Using a Set to check output also discards both order and duplicate counts. Such a check can miss the very bugs a circular array is meant to avoid.

## 15. Practice Exercises

### Exercise 1: Reading a Wrapped Sequence

An illustrative array has `L = 8`, head = 6, tail = 3, and slots 6, 7, 0, 1, 2 hold A, B, C, D, E respectively.

What are the logical sequence and size?

**Answer hint:** A, B, C, D, E; size equals `3 - 6 + 8 = 5`.

### Exercise 2: Where Is the last Element?

In the same model, tail equals 0 and the Deque is non-empty. Is the last element at slot 0?

**Answer hint:** Not under the convention in use. It sits one step behind circularly, which is slot 7 if L = 8.

### Exercise 3: Does Removing the Front Require Copying?

If the Deque has 1000 elements and pollFirst is called without needing to replace the array, must the remaining 999 elements be shifted left?

**Answer hint:** No. The structure can read and clear the head slot, then advance head. That is the benefit of circular management.

### Exercise 4: Adding When Full

If head has moved past many slots but the element count still fills the storage region under the convention, does wrapping back to the start of the array create more room?

**Answer hint:** No. Only slots that are actually empty can be reused. ArrayDeque must grow the array when there is no longer enough space, rather than overwriting unremoved elements.

### Exercise 5: Reading Amortized O(1)

One addLast call takes much longer than previous calls because it needs to grow the array. Does that contradict amortized O(1)?

**Answer hint:** No. Amortization describes the total work of a sequence; an individual operation can still cost O(n).

### Exercise 6: Constructor and Bounds

Does initializing ArrayDeque with 16 guarantee that the 17th element will be rejected?

**Answer hint:** No. The number is an initial capacity request, not a fixed limit on the collection.

### Exercise 7: Small size After a Large Load Peak

A Deque once held very many elements, and later has only a few left. Can you conclude that the backing array has shrunk correspondingly?

**Answer hint:** Not for the implementation examined. Size reflects the current element count; the backing array may still retain capacity from earlier.

### Exercise 8: Does Resizing Clone Objects?

A Customer object is held both in the Deque and in an external variable. After resizing, does it automatically become two independent Customers?

**Answer hint:** No. Resizing reorganizes references; it does not deep-copy objects by default.

### Exercise 9: Output Alone Is Not Enough to Read Indices

Two JDK versions both print `[A, B, C]`. Can you conclude they have the same head, tail, and array length?

**Answer hint:** No. That is the same logical sequence; multiple internal layouts can represent the same result.

When using ArrayDeque, keep clear the distinction between the logical sequence, circular positions, and allocated capacity. Doing so lets you take advantage of double-ended operations while properly understanding resize points, amortized cost, and memory lifecycle.
