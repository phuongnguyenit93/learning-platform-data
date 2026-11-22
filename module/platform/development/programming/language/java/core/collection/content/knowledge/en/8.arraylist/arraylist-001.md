# Dynamic Array Structure and Distinguishing Size from Capacity

## 1. What Array Problem Does ArrayList Solve?

A Java array has a fixed length once created. With `new String[4]`, the array object has exactly four slots; you cannot change the `length` property of that same array to eight.

`ArrayList<E>` provides a list that allows adding and removing elements without requiring the user to manage the backing array manually. When more space is needed, it can create another array, move the references over, and use the new array as storage.

The word "dynamic" describes how the list structure manages capacity during use. It does not mean that a Java array object itself can change its length.

There are two distinct quantities:

- **Logical size, `size`**: the number of elements currently belonging to the list.
- **Backing array capacity, `capacity`**: the number of slots the internal array reserves to hold elements before having to grow its storage.

One way to visualize this is as a sequence of reserved slots where only an initial segment currently belongs to the list. Having spare capacity does not mean the spare slots have become elements.

`ArrayList` is an implementation of `List`; `size()`, element ordering, and index-based access are part of the list interface. Capacity is tied to the array-based implementation of `ArrayList`, not a concept that every `List` must expose. [ArrayList in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

## 2. How Do size and capacity Differ?

| Question | size | capacity |
|---|---|---|
| How many elements are currently in the list? | Answers this question | Does not answer this question |
| Used to determine valid indices for reading/replacing elements? | Yes | No |
| Direct read API in ArrayList? | Yes: `size()` | No public `capacity()` method |
| Counts elements with `null` values? | Yes | Counts storage slots, not non-`null` values |
| Does adding elements increase it? | Increases by the number of elements added | Only needs to increase if current capacity is insufficient |
| Does removing elements decrease it? | Decreases by the number of elements removed | Does not necessarily decrease accordingly |
| Does reserving spare space create elements? | No | May increase storage capacity |
| Does trimming spare space remove elements? | No | Can decrease down to size |

The invariant that must hold is:

```text
0 <= size <= capacity
```

Conceptual example: a list has `size = 3`, and the backing array has `capacity = 6`.

```text
Array index:       0       1       2       3       4       5
                 +-------+-------+-------+-------+-------+-------+
Backing array:   |  A    | null  |  C    | empty | empty | empty |
                 +-------+-------+-------+-------+-------+-------+
List portion:    <---------- size = 3 ---------->
Entire array:    <---------------- capacity = 6 ---------------->
```

In the diagram, "empty" is merely an explanatory label for slots outside the logical portion of the list. It is not a special Java value. Spare slots in a reference array may also hold `null`; `ArrayList` distinguishes the element region using `size`, not by scanning for the first `null` slot.

Therefore, `[A, null, C]` has three elements. The `null` at index 1 is still a genuine element of the list and still occupies a logical position.

## 3. What Does the Backing Array Hold?

In OpenJDK 17, `ArrayList` uses an `Object[]` array to hold references and an integer field to track the number of elements. This is an implementation description that helps explain the mechanism, not direct access rights to internal fields.

With `ArrayList<Person>`, the array slots hold references to `Person` objects; the entire `Person` objects themselves are not packed directly into each slot as a contiguous block of inline data. When saying an array has contiguous positions, one must distinguish the contiguous slots holding references from the actual locations of the referenced objects on the heap.

With `ArrayList<Integer>`, numeric values are represented by `Integer` wrapper objects when boxing is required. This structure is not equivalent to an `int[]` in terms of storage layout and memory overhead.

When the backing array is replaced with a larger array:

- The logical order of the elements is preserved.
- Element references are copied to the new storage.
- The element objects themselves are not deep-copied or recreated.
- Other variables referencing the same element objects still reference those exact objects.

An important consequence: capacity is measured in **number of reference slots**, not in bytes, and it does not indicate the total memory consumed by all objects in the list. Total memory also depends on object layout, references, alignment, and the element objects themselves. [OpenJDK 17 ArrayList Implementation](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

## 4. Pre-allocating Capacity Does Not Create Elements

### 4.1. new ArrayList<>(n) Still Has a Size of 0

Illustrative snippet inside a method:

```java
ArrayList<String> names = new ArrayList<>(100);

System.out.println(names.size());    // 0
System.out.println(names.isEmpty()); // true
```

The argument 100 is the initial capacity, not the initial number of elements. The following calls are still invalid at this point:

```java
names.get(0);      // IndexOutOfBoundsException
names.set(0, "An"); // IndexOutOfBoundsException
```

These are independent lines illustrating errors, not code that continues running after the first line has already thrown an exception. An index for reading or replacing must satisfy `0 <= index < size()`; capacity does not widen this range.

To create the first element, call `names.add("An")`. Only after that is `size()` equal to 1, making `get(0)` and `set(0, ...)` valid.

The constructor's `initialCapacity` argument must be non-negative. A value of 0 creates an empty list to which elements can still be added later; a negative value throws `IllegalArgumentException`.

Initial capacity is also not a maximum element limit. A `new ArrayList<>(2)` can still hold more than two elements; the list will grow its storage when needed, provided the allocation can be performed.

### 4.2. add and set Have Different Responsibilities

| Operation | Role | Impact on size |
|---|---|---|
| `add(value)` | Append an element at the end | Increases by one |
| `add(index, value)` | Insert an element at a valid position | Increases by one |
| `set(index, value)` | Replace an existing element | Unchanged |
| `get(index)` | Read an existing element | Unchanged |

For `add(index, value)`, the insertion position allows `0 <= index <= size()`. Allowing insertion right after the last element does not mean allowing insertion at any arbitrary index smaller than capacity.

For example, an empty list with capacity 100 allows `add(0, "A")`, but does not allow `add(50, "A")`. It does not automatically create 50 intermediate elements to fill the gap.

### 4.3. If You Truly Need n Logical Positions

Some problems require pre-populating a list with `n` `null` elements and then replacing individual positions. In that case, you must create actual elements, not just allocate capacity.

Illustrative snippet, requiring an import of `java.util.Collections`:

```java
ArrayList<String> slots =
        new ArrayList<>(Collections.nCopies(3, (String) null));

slots.set(2, "LAST");

// slots = [null, null, LAST]
// slots.size() = 3
```

Here, the list genuinely has three elements. The `ArrayList(Collection)` constructor accepts a collection to populate initial elements, unlike the `ArrayList(int)` constructor, which only accepts an initial capacity.

There is no need to fill a list with `null` just to prepare for appending data at the end. If the goal is to load items sequentially using `add`, allocating a reasonable capacity and then adding elements usually expresses the intent much better.

## 5. Array Growth Mechanism When Adding Elements

### 5.1. When Spare Space Is Available

If `size < capacity`, appending at the end can simply use the slot at index `size` of the backing array:

```text
Before: size = 3, capacity = 6
        [A, B, C, empty, empty, empty]

Add D:
        [A, B, C, D, empty, empty]
After:  size = 4, capacity = 6
```

The logical size increases, but there is no need to replace the array just because one element was added.

### 5.2. When the Array Is Full

If `size == capacity` and an element needs to be added:

1. Compute a new capacity sufficient to satisfy the requirement.
2. Allocate the new array.
3. Copy the slots that need to be retained from the old array to the new array.
4. Switch the list to use the new array.
5. Place the new element at the end position and update `size`.

This is a conceptual description of the mechanism, not the full source code of `ArrayList`. The actual implementation also handles bulk additions, array length limits, and cases where allocation cannot be satisfied.

```text
Before adding:
size = 4
old array, capacity = 4: [A, B, C, D]

After growing storage and adding E:
size = 5
new array, e.g., capacity = 6: [A, B, C, D, E, empty]
```

The number 6 in the diagram illustrates one possible growth outcome; it is not a guarantee that every growth step produces that exact number.

While replacing the array, the old array and the new array coexist temporarily. Consequently, growing incurs allocation and copying costs, and peak temporary memory usage can exceed the size of the final array alone.

### 5.3. Growth Policy Is an Implementation Detail

The `ArrayList` API guarantees automatic capacity growth and amortized constant cost for appending at the end. The API does not mandate that capacity must double or always increase by exactly 50%.

In the referenced OpenJDK 17 branch, the preferred growth increment is typically half of the old capacity. The new size must also satisfy the minimum required capacity and other bounds. For small values, adding elements one by one starting from capacity 4 typically progresses as follows:

| State | size | Capacity under the described OpenJDK 17 policy |
|---|---|---|
| Just created `new ArrayList<>(4)` | 0 | 4 |
| Added four elements | 4 | 4 |
| Added the fifth element | 5 | 6 |
| Added the sixth element | 6 | 6 |
| Added the seventh element | 7 | 9 |

This is an implementation analysis table, not output from a public method reading capacity. Do not write business tests that force intermediate capacities to equal 4, 6, and 9. [Grow mechanism in OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), [new length calculation in ArraysSupport](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/jdk/internal/util/ArraysSupport.java).

The no-arg constructor also needs to be read at the right level of abstraction: the Javadoc describes a default initial capacity of 10, but OpenJDK 17 defers array allocation for the default empty instance. The first regular addition is what actually applies that initial capacity policy. Do not infer from the number 10 that every list immediately upon calling `new ArrayList<>()` already owns a dedicated ten-slot array.

This lazy allocation detail does not change what a caller observes through `List`: before the first addition, the list is still empty and its size is still 0.

## 6. Why Is Appending at the End Amortized O(1)?

Appending at the end when spare capacity exists normally only requires writing a reference and incrementing `size`. Appending when the array must grow has to copy a number of slots proportional to the old array, so that single addition can take `O(n)`.

**Amortized analysis** looks at the total cost across an entire sequence of operations; it does not claim that every individual call has the exact same cost.

If the array grows by a factor greater than 1 instead of growing by just a single slot, many additions occur without copying between two consecutive growth events. The total amount of copying across a long sequence of additions is bounded by a constant multiplied by the number of added elements, under normal analytical conditions.

An easy-to-visualize mathematical model is doubling: the sum of previous capacities `1 + 2 + 4 + ...` is less than a constant times the final capacity. This is a model to explain total cost, not a claim that Java's `ArrayList` doubles its size.

Results:

- Appending `n` elements at the end has a total cost of `O(n)` under the amortized guarantee.
- The average amortized cost per append at the end is `O(1)`.
- An individual append can still be slower due to allocation and copying.
- Amortization is not a fixed latency guarantee for every single call.

Spare capacity trades some extra memory for a lower frequency of array reallocations. If the array grew by only one slot whenever full, almost every addition would have to copy an ever-growing list, leading to a total cost of the form `1 + 2 + ... + n`, which is `O(n²)`.

### 6.1. Spare Capacity Does Not Eliminate Element-Shifting Costs

| Operation on ArrayList | Primary Mechanism | Typical Analytical Cost |
|---|---|---|
| `size()`, `isEmpty()` | Read size state | `O(1)` |
| `get(i)`, `set(i, value)` | Direct slot access after bounds check | `O(1)` |
| `add(value)` at the end | Write at end; occasionally grow array | Amortized `O(1)`, single call up to `O(n)` |
| Insert at beginning or middle | Shift subsequent elements; may grow array | `O(n)` in the worst case |
| Remove at beginning or middle by index | Shift subsequent elements left | `O(n)` in the worst case |
| Remove last element by index | Clear last reference and decrement size | `O(1)` |
| `clear()` | Clear references in the logical region | `O(n)` where `n = size` before clearing |

If you pre-allocate a capacity of 10,000 and then insert at the beginning of a list containing 5,000 elements, the work of shifting 5,000 elements still remains. Pre-allocating capacity avoids growing the array; it does not turn a middle insertion into a single write operation.

Similarly, removing by value may require searching for the element before removing it. Do not use the complexity of removing the last element by index to describe all forms of `remove`.

## 7. ensureCapacity: Reserving Space Without Changing Content

Illustrative snippet:

```java
ArrayList<String> names = new ArrayList<>();
names.ensureCapacity(1_000);

// names.size() is still 0
// names is still []
```

`ensureCapacity(minCapacity)` requests that the list prepare space for at least the specified number of elements when necessary. It does not add `null` elements, does not return a new list, and does not change the order of existing elements.

Do not interpret it as "set the capacity to equal the parameter exactly." If the list already has a larger capacity, it does not shrink; when it does need to grow, the implementation may choose a capacity larger than the requested minimum.

Reasonable use cases:

- When you know with reasonable certainty how many elements will be loaded in a batch, you can allocate capacity via the constructor.
- When you already have an `ArrayList` and know many elements are about to be added, you can call `ensureCapacity` before the batch addition.
- When you want to reduce the number of array reallocations and copies during data loading.

Do not call `ensureCapacity` with an arbitrarily huge number just "so it never has to grow again." Reserved slots still consume memory and can cause allocation failure. Estimates should be grounded in reasonable data volumes, not based on maximum integer limits.

Capacity is not a business limit. If at most 100 items are allowed, you must validate that rule before adding; `new ArrayList<>(100)` will not block the 101st item. [ArrayList.ensureCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#ensureCapacity(int)).

### 7.1. Capacity Methods Belong to the ArrayList Type

If you declare:

```java
List<String> names = new ArrayList<>();
```

then through the `List` type, you cannot directly call `names.ensureCapacity(...)` or `names.trimToSize()`; those two methods are not part of the `List` interface.

When a piece of code genuinely needs to control the capacity of an `ArrayList`, it can keep the local variable typed as `ArrayList`. At API boundaries where only general list operations are needed, the `List` type still expresses the required capabilities cleanly. Do not cast every list to `ArrayList` just to tweak capacity, because the actual runtime object might be a different implementation.

## 8. Removing Elements and Shrinking the Array Are Separate Operations

### 8.1. remove Decreases size

Conceptual example:

```text
Before:
size = 4, capacity = 6
[A, B, C, D, empty, empty]

Remove B at index 1:
size = 3, capacity is still = 6
[A, C, D, empty, empty, empty]
```

Subsequent elements are shifted to the left. In the OpenJDK implementation, the trailing slot that no longer belongs to the logical region is set to `null` so the array does not retain an obsolete reference to the element.

Clearing a reference from the list does not mean the object is destroyed immediately. If another place still holds a reference, the object continues to be used normally; if no live references remain, reclamation is managed by the garbage collector.

### 8.2. clear Resets size to 0 but Keeps Storage for Reuse

In OpenJDK 17, `clear()` nulls out the element references and sets `size` to 0, but it does not automatically replace the backing array with a smaller one just because the list has become empty.

This is useful if the list will be repopulated repeatedly at a similar scale. Retaining the capacity avoids having to reallocate the array from scratch after every cycle.

However, if a list was once very large, after `clear()` it may still hold onto a large backing array. You should distinguish two kinds of data:

- The old element objects are no longer retained by the list merely because they were once inside it.
- The backing array containing the spare slots may still be retained by the list.

Do not treat `clear()` as a promise that all associated memory has been returned immediately. [remove, clear, and trimToSize in OpenJDK 17 source](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

### 8.3. trimToSize Shrinks Capacity to the Current Size

`trimToSize()` shrinks the capacity of an `ArrayList` down to its current logical size. Its content and `size` remain unchanged.

Illustrative snippet:

```java
ArrayList<String> names = new ArrayList<>(1_000);
names.add("An");
names.add("Binh");

names.trimToSize();

// size is still 2; content is still [An, Binh].
// Capacity after trim equals the current size.
```

This operation may need to allocate a new array and copy the active references. It does not make the list immutable, nor does it set a permanent limit on the number of elements. If you continue adding elements when the array is full, the list will grow its storage again.

Do not call `trimToSize()` after every `add`. Repeatedly forcing capacity down to `size` and then adding again can force repeated allocations and copies, defeating the benefit of spare capacity.

A reasonable time to consider it is after a large load or removal phase, when you know the list will be retained for a long time with few further additions. The decision should balance memory footprint, copy overhead, and usage patterns. [ArrayList.trimToSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#trimToSize()).

## 9. Complete Program: Size, Indices, and Capacity Operations

The short snippets above illustrate code inside a method and require appropriate imports. The following program is a standalone file using APIs available in Java 17.

Save as `SizeCapacityDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;

public class SizeCapacityDemo {
    private static void show(String step, ArrayList<String> values) {
        System.out.println(step + ": size = " + values.size()
                + ", values = " + values);
    }

    public static void main(String[] args) {
        ArrayList<String> values = new ArrayList<>(5);
        show("new ArrayList<>(5)", values);
        System.out.println("empty = " + values.isEmpty());

        try {
            values.get(0);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("get(0) -> IndexOutOfBoundsException");
        }
        try {
            values.set(0, "A");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("set(0) -> IndexOutOfBoundsException");
        }

        values.ensureCapacity(12);
        show("after ensureCapacity(12)", values);

        values.add("A");
        values.add(null);
        values.add("C");
        show("after three adds", values);
        System.out.println("toArray().length = " + values.toArray().length);

        String old = values.set(1, "B");
        System.out.println("set returned = " + old);
        show("after set(1, B)", values);

        values.add(1, "X");
        show("after add(1, X)", values);

        String removed = values.remove(2);
        System.out.println("removed = " + removed);
        show("after remove(2)", values);

        values.trimToSize();
        show("after trimToSize()", values);

        values.clear();
        show("after clear()", values);

        values.trimToSize();
        values.add("Z");
        show("after empty trim and add", values);

        ArrayList<String> slots =
                new ArrayList<>(Collections.nCopies(3, (String) null));
        show("three real null elements", slots);
        slots.set(2, "LAST");
        show("after slots.set(2, LAST)", slots);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 SizeCapacityDemo.java
java SizeCapacityDemo
```

Standard output:

```text
new ArrayList<>(5): size = 0, values = []
empty = true
get(0) -> IndexOutOfBoundsException
set(0) -> IndexOutOfBoundsException
after ensureCapacity(12): size = 0, values = []
after three adds: size = 3, values = [A, null, C]
toArray().length = 3
set returned = null
after set(1, B): size = 3, values = [A, B, C]
after add(1, X): size = 4, values = [A, X, B, C]
removed = B
after remove(2): size = 3, values = [A, X, C]
after trimToSize(): size = 3, values = [A, X, C]
after clear(): size = 0, values = []
after empty trim and add: size = 1, values = [Z]
three real null elements: size = 3, values = [null, null, null]
after slots.set(2, LAST): size = 3, values = [null, null, LAST]
```

Key observations to draw:

1. The initial capacity is 5, yet the list is empty. `get(0)` and `set(0, ...)` are not permitted.
2. After `ensureCapacity(12)`, both the content and `size` remain unchanged.
3. Three `add` calls create three elements, including the `null` element.
4. `set` replaces `null` with `B`, returns the old value `null`, and does not increase `size`.
5. `add(1, "X")` inserts a new element, so `size` increases.
6. `remove(2)` removes an element, so `size` decreases.
7. `trimToSize` does not alter content. After being cleared and trimmed, the list can still accept new elements.
8. A list constructed from three `null` copies genuinely has three elements, so `set(2, ...)` is valid.

The program intentionally does not print internal capacity because `ArrayList` provides no public API to read it. The output verifies what callers can rely on: element count, content, and operation validity.

### 9.1. toArray().length Is Not a Way to Read Capacity

In the program, `values.toArray().length` is 3 because the list has three elements. `toArray()` returns a newly allocated array containing the logical elements; it does not expose the backing array to inspect spare capacity.

Therefore, do not write `list.toArray().length` and label it "capacity." That operation also allocates a separate result array, incurring unnecessary overhead if you only want to know the element count.

Likewise, do not count non-`null` values to infer `size` or `capacity`. A list may legitimately contain multiple `null` elements.

## 10. Complete Program: Replacing the Array Does Not Clone Elements

Save as `ArrayListReferenceDemo.java`:

```java
import java.util.ArrayList;

public class ArrayListReferenceDemo {
    private static final class Item {
        private String name;

        private Item(String name) {
            this.name = name;
        }

        private void rename(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        ArrayList<Item> items = new ArrayList<>(1);
        Item first = new Item("A");
        items.add(first);

        items.ensureCapacity(100);
        System.out.println("after reserve: same first = "
                + (items.get(0) == first));
        System.out.println("after reserve: size = " + items.size());

        items.add(new Item("B"));
        items.trimToSize();
        System.out.println("after trim: same first = "
                + (items.get(0) == first));
        System.out.println("after trim: items = " + items);

        first.rename("A*");
        System.out.println("after rename: items = " + items);

        Item removed = items.remove(0);
        System.out.println("removed is first = " + (removed == first));
        System.out.println("remaining items = " + items);

        items.clear();
        System.out.println("after clear: size = " + items.size());
        System.out.println("external reference = " + first);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 ArrayListReferenceDemo.java
java ArrayListReferenceDemo
```

Standard output:

```text
after reserve: same first = true
after reserve: size = 1
after trim: same first = true
after trim: items = [A, B]
after rename: items = [A*, B]
removed is first = true
remaining items = [B]
after clear: size = 0
external reference = A*
```

Here, the initial capacity is only 1; `ensureCapacity(100)` reserves larger storage. Even though the backing array is replaced, the first element is still the exact same `first` object, as shown by `==` evaluating to `true`.

After adding a second element and trimming, the reference to the first element is still preserved. Renaming it through the `first` variable causes the list to see the new name as well, because both access paths point to the same object.

Finally, `remove` and `clear` do not make the external `first` variable disappear. That variable still references the `Item` object named `A*`. This demonstrates reference semantics, not a measurement of when the garbage collector runs.

## 11. Reading and Using Capacity Properly in Practice

### 11.1. When the Number of Items to Load Is Known

Illustrative snippet:

```java
int expectedCount = 5_000;
ArrayList<String> rows = new ArrayList<>(expectedCount);

for (int i = 0; i < expectedCount; i++) {
    rows.add("row-" + i);
}
```

Pre-allocating capacity helps reduce array growth during the loading phase. It does not pre-create the strings, does not avoid the cost of creating each individual string, and does not guarantee that the entire task performs only a single memory allocation. Beyond the backing array, there are still the element objects and other allocations.

If the count is only an estimate, the list can still grow further when the actual count exceeds expectations. If the estimate is far too high, many reserved slots may be wasted.

### 11.2. When Reusing Across Multiple Batches

If each batch has a similar scale, keeping an `ArrayList` and calling `clear()` between batches can reuse the already allocated array. If later batches are much smaller and the list is retained for a long time, consider trimming at an appropriate boundary.

There is no single "always trim" or "never trim" rule that is right for every program. Observe data volume, list lifetime, and allocation overhead before optimizing.

### 11.3. Capacity Does Not Provide Thread Safety or Error-Free Guarantees

Having spare slots available does not make `ArrayList` safe for concurrent modification by multiple threads. `size`, array elements, and structural modifications still must be managed under an appropriate concurrency policy.

Increasing capacity also does not guarantee that every future addition will succeed: elements may continue to grow, resources are finite, and surrounding code may fail for other reasons. Do not treat a capacity reservation number as complete proof of performance or correctness.

## 12. Misconceptions to Correct

| Misconception | What Actually Happens | How to Write or Read Correctly |
|---|---|---|
| `new ArrayList<>(100)` has 100 elements | Initial size is 0 | Use `add` to create elements |
| With capacity 100, `get(99)` is always valid | Valid read range depends on `size` | Check `0 <= index < size()` |
| You can use `set` to add into a spare slot | `set` only replaces an existing element | Use `add` when you need to increase `size` |
| Capacity is the maximum element limit | It is the current storage capacity, which can grow | Write a separate limit check if needed |
| A `null` slot means the list has no element there | `null` can be a valid element | `size` is the logical element count, not the non-`null` count |
| Every addition is strict worst-case `O(1)` | Some additions must grow and copy the array | Distinguish a single call from amortized cost |
| Spare capacity makes middle insertion `O(1)` | Subsequent elements still must be shifted | Analyze both element shifting and array growth |
| Removing elements automatically shrinks capacity accordingly | `size` decreases, but the array may stay the same size | Only trim when there is a suitable reason |
| `clear()` immediately returns all used memory | Clears element references and keeps the backing array for reuse | Distinguish elements, the backing array, and GC reclamation |
| `trimToSize()` prevents the list from accepting more elements | The list still grows when new elements are added | Trimming optimizes storage at the moment it is called |
| `toArray().length` is the capacity | It is the length of the resulting array of logical elements | Use `size()` when you need the number of elements |
| Java's capacity always doubles or always multiplies by 1.5 | The exact growth factor is not part of the API guarantee | Rely on the API contract rather than intermediate numbers |

## 13. Self-Check with a Sequence of Operations

Suppose we start with `ArrayList<String> values = new ArrayList<>(8);`. Do not use reflection or access the internal array.

| Step | Operation | Size After Step | What Can Be Concluded About Storage |
|---|---|---|---|
| 1 | Create list | 0 | Has initial capacity 8; no elements yet |
| 2 | Add three elements | 3 | Does not need to exceed capacity 8 |
| 3 | Replace element at index 1 using `set` | 3 | No array growth needed just to replace a reference |
| 4 | Remove element at index 0 | 2 | Removal does not automatically shrink the array per element |
| 5 | `ensureCapacity(12)` | 2 | Prepares at least the requested capacity; creates no new elements |
| 6 | `trimToSize()` | 2 | Capacity is shrunk down to 2 |
| 7 | Add one element | 3 | Must have room for at least three elements; do not rely on a fixed growth factor |
| 8 | `clear()` | 0 | No logical elements remain; the backing array may still be retained |

Additional review questions:

1. After step 1, is `values.set(0, "A")` valid?
2. After step 2, if one element is `null`, is `size` still 3?
3. After step 5, is `values.get(10)` valid?
4. After step 6, why might adding a new element require replacing the array?
5. If another variable still holds an object that was removed from the list, does that object disappear immediately on its own?

Answers:

1. No, because there is no element at index 0 yet.
2. Yes; `null` is still counted as an element.
3. No; `size` is still 2 even though spare space was reserved.
4. Because capacity equals the current size of 2, leaving no spare slot for a third element.
5. No; the object can still be used through the external reference.

When analyzing an operation on an `ArrayList`, separate three questions: does the logical element count change, does the backing array need to change its capacity, and do elements need to shift positions? Reading code this way helps accurately predict both index behavior and the performance characteristics of the dynamic array structure.
