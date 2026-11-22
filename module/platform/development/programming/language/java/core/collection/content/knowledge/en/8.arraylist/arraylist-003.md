# Complexity of Access, Search, Insertion, and Removal in ArrayList

## 1. From a Resizable Array to the Cost of Each Operation

`ArrayList<E>` is a resizable-array implementation of `List<E>`. Active elements are stored as a contiguous sequence by index inside an internal array. When more space is needed, the list can allocate a larger array and copy the references to the new array.

This structure explains two characteristics at the same time:

- Knowing the index allows going straight to the corresponding slot: reading or replacing an element does not require traversing the elements before it.
- Inserting or removing in the middle while preserving order requires shifting the trailing elements: the cost depends on the length of the segment that must be shifted.

Therefore, saying "ArrayList is fast" is not enough to choose an algorithm. You need to specify **fast for which operation, at which position, for a single call or across a sequence of operations**.

For example, a result list that is read sequentially, frequently appended to at the end, and occasionally accessed by index is typically a great fit for `ArrayList`. If you use the same list as a queue by repeatedly removing the first element, every removal has to shift the remaining elements to the left.

This article analyzes `ArrayList` in a single thread, with valid indices and operations that complete normally. Locking, thread contention, I/O time, memory allocation failures, and external business logic outside the operation are separated from the counting model.

The [Java 17 ArrayList documentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) confirms that index-based access runs in constant time and appending to the end runs in amortized constant time. The shifting formulas below follow from how the sequence maintains order; details regarding bulk operations will be explicitly noted when based on the OpenJDK 17 implementation.

## 2. Read the Notation Before Reading the Complexity Table

### 2.1. Variables Used in This Article

| Symbol | Meaning |
| --- | --- |
| `n` | `size()` immediately before the operation, i.e., the number of elements actually present |
| `C` | Capacity of the internal array; always `C >= n` |
| `i` | Index for insertion, reading, replacement, or removal, depending on the method |
| `k` | Number of elements in a batch being added or removed |
| `m` | Number of operations in a sequence; in two-collection problems it may also denote the size of the reference collection and will be stated explicitly |
| `E` | Cost of a single equality check via `equals` |
| `P` | Cost of a single execution of a filtering predicate |

Do not confuse `size` with `capacity`. A list may hold 20 elements while having reserved space for 1,000 elements. A call to `contains` still inspects at most the 20 active elements; it does not search through all 1,000 spare slots.

### 2.2. What Do O(1), O(n), and Θ(n) Mean?

`O(1)` means the number of elementary steps is bounded by a constant that does not grow with `n`; it does not mean a single machine instruction or that every execution takes the exact same number of nanoseconds.

`O(n)` describes an upper bound that grows linearly with `n`. When the cost grows linearly in both its upper and lower bounds for the case under consideration, this article uses `Θ(n)`. For instance, shifting exact `n - 1` references when removing the first element of a non-empty list has `Θ(n)` cost in this model.

`O(n²)` often arises when a linear operation is repeated proportionally to the list size. A loop with `n` iterations is not automatically `O(n)`: you must account for the work performed inside each iteration.

### 2.3. Worst-Case vs. Amortized Cost

- **Worst-case single call:** looks at the single invocation that performs the most work at the current size.
- **Amortized cost:** considers the total work across an entire sequence of operations and distributes it per operation.
- **Average-case cost over data:** requires assumptions about data distribution or probabilities; it is not synonymous with amortized cost.

For appending to the end, amortization does not rely on the assumption that "bad data rarely occurs." It relies on the fact that a single array expansion creates enough spare capacity so that many subsequent appends do not need to expand the array again.

## 3. Core Reference Table

The following table assumes that reading/writing a reference and comparing elements each take constant time. `n` is the size before the operation. When `equals` is expensive, you must include the comparison cost as shown in Section 5.

| Operation on ArrayList | Primary Work | Cost to Remember |
| --- | --- | --- |
| `size()`, `isEmpty()` | Read size information | `Θ(1)` |
| `get(i)` | Bounds-check the index, then read one slot | `Θ(1)` |
| `set(i, value)` | Bounds-check the index, read the old value, and replace one slot | `Θ(1)` |
| `contains(value)`, `indexOf(value)` | Scan from the start to the first match | Best case `Θ(1)`; worst case `Θ(n)` |
| `lastIndexOf(value)` | Scan backward from the end to the last match | Best case `Θ(1)`; worst case `Θ(n)` |
| `add(value)` | Write at the end; occasionally expand the array | Without expansion: `Θ(1)`; single expansion: `Θ(n)`; amortized: `O(1)` |
| `add(i, value)` | Shift `n - i` elements; may also need expansion | Without expansion: `Θ(n - i + 1)`; worst case `Θ(n)` |
| `remove(i)` | Shift `n - i - 1` elements, clear the trailing reference | `Θ(n - i)`; removing the last element is `Θ(1)`, removing the first is `Θ(n)` |
| `remove(value)` | Find the first occurrence, then shift the trailing suffix | Worst case `Θ(n)`; cannot be treated as `O(1)` tail removal even if the value is at the end |
| Full single-pass traversal | Read each element | `Θ(n)`, excluding per-element processing work |
| `clear()` in OpenJDK 17 | Clear all active references | `Θ(n)` for a non-empty list |

Index bounds:

- `get`, `set`, `remove(int)`: `0 <= i < n`.
- `add(int, E)`: `0 <= i <= n`, because inserting immediately after the last element is allowed.

The conclusions above are tied to **ArrayList**. Declaring a variable with type `List<E>` does not change the underlying runtime object, but the `List` interface does not guarantee that every implementation has the same index-based access cost.

## 4. Index-Based Access: Why Are get and set O(1)?

You can visualize the active portion of the data as follows:

```text
index:     0     1     2     3
element:  [A]   [B]   [C]   [D]
size = 4; any spare capacity slots sit after these elements
```
With `get(2)`, the list already knows which slot to read. It does not need to inspect A and then B to reach C.

`set(2, "X")` replaces the reference at slot 2, returns the old value, and leaves the size unchanged. No trailing suffix needs to be shifted either.

Distinguish three operations that are easy to confuse:

```java
// Illustrative snippet, assuming items already has at least three elements.
items.get(2);       // Read the element currently at index 2.
items.set(2, "X");  // Replace the element at index 2.
items.add(2, "X");  // Insert X, shifting the old element at index 2 to the right.
```
Even with the same index, `set` and `add` perform different work. You cannot take the cost of `set` to infer the cost of insertion.

If after calling `get(i)` you process a large document, parse a string, or call a network service, that cost belongs to using the element. The fact that `get(i)` takes constant time does not turn the entire business expression into constant time.

Similarly, casting, auto-unboxing an `Integer`, or invoking methods on the retrieved object can have their own behavior. The complexity table only describes the data structure operation itself.

## 5. Value-Based Search: Without an Index, You Must Search

### 5.1. contains Cannot Leverage "Random Access" to Instantly Locate a Value

Having index 7 and asking "what is the value at index 7?" is fundamentally different from having value X and asking "where is X located?".

`ArrayList` does not maintain an automatic lookup table from every value to its index. `contains` and `indexOf` search linearly; the fact that a list is ordered by index does not mean its elements are sorted by value.

If a forward scan finds a match at index `i`, it inspects `i + 1` positions. If the value is absent, it must inspect all `n` positions.

`lastIndexOf` searches in the opposite direction. When the last matching position is `i`, the number of inspected positions is `n - i`. That is still a linear search in the worst case.

`null` does not require a different data structure either: `ArrayList` can hold `null` and searches for `null` using the appropriate check. The cost still depends on the number of positions inspected.

### 5.2. The Cost of equals Is Not Always Constant

For a small key wrapping a single integer, comparison can be treated as constant time. However, if `equals` traverses the contents of a long string, an array, or a nested structure, each comparison may take many more steps.

A more general analysis is:

```text
Search cost
= cost of stepping through positions
+ total cost of equality checks at the inspected positions.

If each equals call is bounded by E:
the worst case has an upper bound of O(n + n * E).
```
In quick reference tables, people usually assume `E = O(1)` and write `O(n)`. When your data model does not satisfy that assumption, you must bring the comparison cost back into the formula.

### 5.3. Program Counting Comparisons

Save the following code to `ArrayListSearchCostDemo.java`. The `Key` class only compares a single integer; the counter lets us observe the number of `equals` invocations rather than measuring wall-clock execution time.

```java
import java.util.ArrayList;
import java.util.List;

public class ArrayListSearchCostDemo {
    static final class Key {
        private final int id;
        static int equalsCalls;

        Key(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof Key key && id == key.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static void checkContains(ArrayList<Key> keys, int id) {
        Key.equalsCalls = 0;
        boolean found = keys.contains(new Key(id));
        System.out.println("contains " + id + " = " + found
                + ", equals calls = " + Key.equalsCalls);
    }

    public static void main(String[] args) {
        ArrayList<Key> keys = new ArrayList<>(List.of(
                new Key(1), new Key(2), new Key(3),
                new Key(4), new Key(5)));

        checkContains(keys, 1);
        checkContains(keys, 5);
        checkContains(keys, 99);

        Key.equalsCalls = 0;
        int index = keys.indexOf(new Key(3));
        System.out.println("indexOf 3 = " + index
                + ", equals calls = " + Key.equalsCalls);

        Key.equalsCalls = 0;
        boolean removed = keys.remove(new Key(5));
        System.out.println("remove value 5 = " + removed
                + ", equals calls = " + Key.equalsCalls);

        Key.equalsCalls = 0;
        Key removedByIndex = keys.remove(0);
        System.out.println("remove index 0 id = " + removedByIndex.id
                + ", equals calls = " + Key.equalsCalls);
    }
}
```
Compile and run:

```shell
javac --release 17 ArrayListSearchCostDemo.java
java ArrayListSearchCostDemo
```
Output:

```text
contains 1 = true, equals calls = 1
contains 5 = true, equals calls = 5
contains 99 = false, equals calls = 5
indexOf 3 = 2, equals calls = 3
remove value 5 = true, equals calls = 5
remove index 0 id = 1, equals calls = 0
```
Explanation:

- Searching for 1 matches the very first element, so it performs one comparison.
- Searching for 5 at the end and searching for 99 (which does not exist) both scan all five elements.
- `indexOf(3)` returns index 2, which requires inspecting three positions.
- Removing by value 5 still has to scan all five elements, even though no trailing elements remain to be shifted once it is found.
- Removing by index 0 does not call `equals` to search. Even so, after 5 has been removed, this operation must shift the three remaining references: zero `equals` calls does not mean constant cost.

The counter illustrates the search behavior of `ArrayList` in the executed implementation, consistent with linear search in OpenJDK 17. Do not treat the exact `equals` call count from this example as a universal contract for every `List` implementation or for objects that mutate themselves during comparison.

If you repeat `contains` on an `n`-element list across `q` queries, the upper bound becomes `O(q * n)` assuming constant-time comparisons. When `q` grows with `n`, the total work can become quadratic. Always evaluate the overall usage pattern, not just an isolated call.

## 6. Appending to the End: Amortized O(1) Does Not Mean O(1) for Every Call

### 6.1. When Spare Capacity Is Available

If `n < C`, a single `add(value)` simply writes the element into the next available slot at the end and increments `size`. Existing elements do not need to be shifted.

```text
Before: [A, B, C, _, _, _]  size = 3
After:  [A, B, C, D, _, _]  size = 4

Existing elements keep their indices.
```
The `_` symbol in the diagram represents spare capacity slots, not actual elements that a user can access via `get`.

### 6.2. When the Array Is Full

If capacity is exhausted, a larger array is needed to hold the new element. Allocating the new array and transferring the existing data makes that single append operation linear in the current size during normal growth.

```text
Old array:         [A, B, C, D]         size = capacity = 4
New larger array:  [A, B, C, D, E, _, ...]
                    copied       newly added
```
The transfer here copies **references**; it does not invoke constructors to deep-clone the objects A, B, C, and D. Element objects do not change their identity simply because `ArrayList` expands its backing array.

### 6.3. Why Is the Total Cost of Appending m Elements Still Linear?

Consider an illustrative dynamic array model that doubles its capacity whenever full. This model is used to explain amortization; **it is not a guarantee that ArrayList always doubles its capacity**.

When capacities progress through `1, 2, 4, 8, 16`, the number of existing references copied to reach capacity 16 is:

```text
1 + 2 + 4 + 8 = 15
```
To store 16 elements, there are also 16 writes for the new elements themselves. The total work under this counting model is 31 units, rather than copying nearly 16 elements on all 16 insertions.

The sum of a geometric series growing by a factor greater than 1 has the same order of growth as the final number of elements. Therefore, across a sequence of pure appends starting from a new list, the expansion work is spread over many appends: the total cost of `m` appends is `O(m)`, and the amortized cost per append is `O(1)`.

The API specification does not mandate an exact capacity growth factor. Do not write algorithms that depend on "what the exact capacity will be after the next expansion." What you should rely on is the amortized guarantee of appending to the end.

If you start with an already huge list and the very next append triggers an expansion, that single call can still take `Θ(n)`. Observing a very short measurement window in isolation cannot replace analyzing the overall growth process.

### 6.4. What Does Pre-Allocating Capacity Help With?

```java
// Illustrative snippet: expectedCount estimates the number of results to be collected.
ArrayList<String> results = new ArrayList<>(expectedCount);

// size is still 0; each add increments the element count.
results.add("first");
```
Pre-allocating sufficient capacity can avoid intermediate allocations and array copies while adding elements. It does not pre-populate elements, does not allow `get(0)` on an empty list, and does not eliminate the shifting required when inserting at the front.

Allocating the backing array is also real work. If you pre-allocate a huge capacity only to store a few elements, you trade memory and initialization cost to avoid later expansions.

Do not call `trimToSize()` after every append:

```java
// Illustrative snippet showing an anti-pattern to avoid when continuously growing a list.
for (String value : input) {
    results.add(value);
    results.trimToSize();
}
```
Repeatedly shrinking the capacity back to `size` can force the very next append to reallocate and copy again. The entire sequence can degrade to `Θ(m²)`. The amortized append guarantee does not mean you can arbitrarily interleave operations that destroy spare capacity while keeping the same total cost.

## 7. Index-Based Insertion: Count the Trailing Suffix, Then Consider Expansion

With `add(i, value)`, existing elements at indices `i` through `n - 1` must be shifted one position to the right to make room.

The number of references shifted due to the insertion is:

```text
n - i
```
For example, given `[A, B, C, D]` with `n = 4`, inserting X at `i = 2`:

```text
Before: [A, B, C, D]
Shift:        C -> index 3
                 D -> index 4
After:  [A, B, X, C, D]

Number of elements in the shifted suffix: 4 - 2 = 2.
```
The arrows illustrate the before-and-after index mapping; the internal copy routine properly handles overlapping memory regions rather than running a naive left-to-right assignment loop.

| Insertion Position | Elements to Shift | Result When No Expansion Is Needed |
| --- | --- | --- |
| Front, `i = 0` | `n` | `Θ(n)` |
| Middle, `i` around `n / 2` | Approximately `n / 2` | Still `Θ(n)` |
| Immediately before the last element | 1 | `Θ(1)` for the shifting portion |
| After the last element, `i = n` | 0 | Same as appending to the end |

If the backing array needs to expand, you must add the cost of allocating and copying into a larger array. Consequently, inserting near the end takes constant time **only when no expansion is required**; the worst case of a single insertion can still be linear.

Pre-allocating capacity only eliminates expansions. It does not eliminate the `n - i` elements that must be shifted to preserve list order.

A common analytical mistake is assuming that knowing the index makes insertion `O(1)`. Knowing the index only locates the insertion point quickly; making room for the new element is separate work.

## 8. Removal: Distinguish Index, Value, and the Last Element

### 8.1. remove(int index)

After removing the element at index `i`, elements from `i + 1` through `n - 1` must be shifted one position to the left.

The number of references that must be shifted is:

```text
n - i - 1
```
In addition, there is constant work to update `size`, return the removed element, and clear the leftover reference in the last slot.

Example:

```text
Before: [A, B, X, C, D, E]  n = 6
Remove i = 2:
After:  [A, B, C, D, E]

C, D, E must change positions: 6 - 2 - 1 = 3 elements.
```
Removing the last element via `remove(size() - 1)` has no trailing elements to shift, so it runs in constant time in `ArrayList`. Removing the first element via `remove(0)` shifts `n - 1` elements and is therefore linear.

In the OpenJDK 17 implementation, removing elements does not automatically shrink the internal array. Clearing the trailing reference prevents the list from retaining an obsolete reference to the removed object. It does not guarantee immediate garbage collection: the object might still be referenced elsewhere.

### 8.2. remove(Object value)

This method must first find the first occurrence using equality, and only then remove the element at that matched position.

If the element is found at index `i`:

```text
Cost = search up to i + shift the suffix after i + update the list.

With constant-time comparisons:
searching inspects i + 1 positions;
shifting moves n - i - 1 references.
```
When a match is found near the front, the search is short but the shifted suffix is long. When a match is found at the end, no shifting is needed but the search scans the entire list. Therefore, never write "`remove(value)` at the end is `O(1)`": that confuses it with `remove(int)` when the last index is already known.

If no match is found, the list remains unchanged, yet all `n` elements have been inspected. When `equals` has cost `E`, the general upper bound is `O(n * E + n)`.

### 8.3. Be Careful with List<Integer>

```java
// Illustrative snippet of the two overloads, starting from two separate copies.
ArrayList<Integer> byIndex = new ArrayList<>(List.of(10, 20, 10));
byIndex.remove(1);                 // Removes index 1: leaves [10, 10].

ArrayList<Integer> byValue = new ArrayList<>(List.of(10, 20, 10));
byValue.remove(Integer.valueOf(10)); // Removes the first value 10: leaves [20, 10].
```
This is both a correctness issue and a complexity issue: one overload jumps straight to the index, while the other must search by value.

### 8.4. Program Observing State and Shifted Suffix Length

Save to `ArrayListMovementDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ArrayListMovementDemo {
    public static void main(String[] args) {
        ArrayList<String> items = new ArrayList<>(16);
        System.out.println("size after capacity reservation = " + items.size());

        items.addAll(List.of("A", "B", "C", "D"));
        System.out.println("initial = " + items);
        System.out.println("get(2) = " + items.get(2));

        String previous = items.set(1, "B*");
        System.out.println("set returned = " + previous);
        System.out.println("after set = " + items);

        int index = 2;
        int shiftedForInsert = items.size() - index;
        items.add(index, "X");
        System.out.println("insert suffix length = " + shiftedForInsert);
        System.out.println("after insert = " + items);

        items.add("E");
        System.out.println("after append = " + items);

        int shiftedForRemove = items.size() - index - 1;
        String removed = items.remove(index);
        System.out.println("removed at index 2 = " + removed);
        System.out.println("remove suffix length = " + shiftedForRemove);
        System.out.println("after remove = " + items);

        String removedLast = items.remove(items.size() - 1);
        System.out.println("removed last = " + removedLast);
        System.out.println("final = " + items);
    }
}
```
Compile and run:

```shell
javac --release 17 ArrayListMovementDemo.java
java ArrayListMovementDemo
```
Output:

```text
size after capacity reservation = 0
initial = [A, B, C, D]
get(2) = C
set returned = B
after set = [A, B*, C, D]
insert suffix length = 2
after insert = [A, B*, X, C, D]
after append = [A, B*, X, C, D, E]
removed at index 2 = X
remove suffix length = 3
after remove = [A, B*, C, D, E]
removed last = E
final = [A, B*, C, D]
```
The variables `shiftedForInsert` and `shiftedForRemove` calculate the length of the shifted suffix using our formulas. The program does not inspect the internal array, does not measure machine instructions, and does not count copies caused by capacity expansion.

Because the list pre-allocates a capacity of 16 and the example uses at most six elements, no expansion occurs during this sequence. That lets us focus purely on the difference between replacing a slot, inserting, appending, and removing.

## 9. From a Single Operation to a Complete Algorithm

### 9.1. Appending n Elements to the End

```java
// Illustrative snippet; input has n elements.
ArrayList<String> output = new ArrayList<>();
for (String value : input) {
    output.add(value);
}
```
The total cost of appending is `O(n)` amortized, assuming retrieving each element from `input` has proportional cost and you do not repeatedly shrink the capacity inside the loop.

### 9.2. Inserting at the Front n Times

```java
// Illustrative snippet building a list by inserting at the front.
ArrayList<String> output = new ArrayList<>();
for (String value : input) {
    output.add(0, value);
}
```
Each step shifts `0, 1, 2, ..., n - 1` elements in turn. The sum is:

```text
0 + 1 + ... + (n - 1) = n * (n - 1) / 2 = Θ(n²)
```
Amortized array expansion cannot rescue this quadratic shifting cost. Furthermore, the resulting order is reversed relative to `input`. If you want to reverse an existing list, choose an algorithm that expresses that goal directly rather than accidentally incurring repeated front-insertion costs.

### 9.3. Removing from the Front Until Empty

```java
// Illustrative snippet.
while (!items.isEmpty()) {
    items.remove(0);
}
```
The number of shifted elements is `n - 1, n - 2, ..., 0`, which totals `Θ(n²)`. If the goal is simply to discard all elements, `clear()` expresses the intent directly and traverses the active references once in OpenJDK 17.

If the goal is to consume elements in queue order (FIFO), choose a data structure designed for front operations, such as a `Deque`. Do not use `clear()` to replace business logic that needs to process each element.

### 9.4. Removing from the End Until Empty

```java
// Illustrative snippet.
while (!items.isEmpty()) {
    items.remove(items.size() - 1);
}
```
Each removal from the end takes constant time; `n` removals take `Θ(n)`. Elements are removed from back to front, so only use this pattern when reverse order matches your requirements.

### 9.5. Is Traversing with get Linear?

```java
// Illustrative snippet; processing each element in O(1).
for (int i = 0; i < items.size(); i++) {
    String value = items.get(i);
    consume(value);
}
```
On an `ArrayList`, both `size` and `get` take constant time, so a single pass like this is `Θ(n)`, excluding `consume`. A `for-each` loop or `Iterator` traversal is likewise linear for a full pass over the data.

Do not generalize this conclusion to every `List`. In particular, do not write an algorithm that makes repeated `get(i)` calls solely because a parameter is typed as `List`; either know the implementation characteristics or use an iterator/for-each traversal.

## 10. Bulk Operations: A Single Call Can Still Do Significant Work

The detailed analyses in this section are based on the [OpenJDK 17 ArrayList source code](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), assuming a standard source collection that is not concurrently modified. They help explain the internal mechanics, not a universal guarantee across every `Collection` implementation or future JDK release.

### 10.1. addAll at the End

Suppose we append a batch of `k` elements. At a minimum, `k` new elements must be obtained and written:

- Sufficient capacity available: typically `O(k)`.
- Capacity expansion required: typically `O(n + k)`.

You must also account for extracting the elements from the source collection. If the source collection has an expensive array conversion or special traversal behavior, that part cannot be treated as free.

Do not write `addAll(batch)` as `O(1)` just because it is a single method call. The amortized constant-time guarantee of `add(value)` applies to appending **one** element at the end; it does not mean appending an arbitrary batch is constant time.

### 10.2. addAll(i, batch)

When no capacity expansion is needed, inserting the entire batch requires:

```text
obtaining and writing k new elements
+ shifting n - i existing elements after the insertion point.

Typical cost: O(k + n - i).
```
When expansion is needed, the typical upper bound is `O(n + k)`.

Inserting a whole batch at once typically avoids shifting the same trailing suffix over and over, which is what happens when calling `add(i + offset, value)` repeatedly in a loop. Always preserve the required batch order; never trade correctness away just to save shifts.

### 10.3. Removing a Range via subList(...).clear()

For a range `[from, to)`, the number of elements removed is `k = to - from`. When `k > 0`, the OpenJDK 17 implementation shifts the trailing suffix after `to` to the left in one step and then clears the leftover references.

The work is proportional to:

```text
(n - to) + k
= trailing suffix to compact + reference slots to clear.
```
This can be much better than removing elements one by one at the same index and repeatedly shifting the tail. For an empty range, do not assume the entire list is still shifted; handle the zero-element case distinctly.

`subList` returns a view backed by the original list. Calling `clear` on this view mutates the underlying list; it does not create an independent copy of the range.

### 10.4. removeIf

In OpenJDK 17's `ArrayList`, `removeIf` identifies which positions to remove and then compacts the remaining elements in a single pass, avoiding shifting the entire tail after each individual removal.

If the filtering predicate has cost `P`, the typical analysis is `O(n * P + n)`; when `P = O(1)`, the operation is linear. The implementation may allocate temporary bitset storage to mark elements when removals occur. Do not assume that a `removeIf` call always uses zero extra memory.

The predicate should only decide whether to keep or remove an element; it must not structurally modify the very list being filtered. If the predicate calls `otherList.contains(value)` and `otherList` is long, that nested linear lookup can still make the overall filtering operation quadratic.

This complexity reflects how `ArrayList` implements `removeIf`, not a general guarantee that `removeIf` on every `Collection` is linear.

### 10.5. removeAll and retainAll Depend on the Reference Collection

Both operations must check whether each element of the list belongs to the specified collection. If that reference collection is also a list of length `m` whose `contains` performs a linear search, the upper bound can reach `O(n * m)` assuming constant-time equality checks.

Do not conclude that "bulk removal is always `O(n)`" solely from the method name. You must consider both the collection receiving the operation and the collection queried for membership.

If membership checks will be performed repeatedly, consider building an appropriate lookup structure first. Remember to factor in the construction cost, memory footprint, and equality semantics of that lookup structure; do not inadvertently alter how elements are matched.

## 11. Removal Correctness and Removal Cost Are Two Separate Questions

When removing by index in a forward loop, the next element shifts left into the index that was just removed. If the loop still increments the index, it will skip right past that shifted element.

An `Iterator` allows safe removal during traversal via `iterator.remove()`. On an `ArrayList`, however, it still has to perform the underlying array removal and shifting work. The iterator manages the traversal cursor correctly; it does not turn mid-list removal in an `ArrayList` into a constant-time operation.

Save the following program to `ArrayListRemovalPatternsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class ArrayListRemovalPatternsDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 6, 1, 3, 8);

        ArrayList<Integer> skipped = new ArrayList<>(source);
        for (int i = 0; i < skipped.size(); i++) {
            if (skipped.get(i) % 2 == 0) {
                skipped.remove(i);
            }
        }
        System.out.println("incorrect forward removal = " + skipped);

        ArrayList<Integer> byIterator = new ArrayList<>(source);
        for (Iterator<Integer> it = byIterator.iterator(); it.hasNext();) {
            if (it.next() % 2 == 0) {
                it.remove();
            }
        }
        System.out.println("iterator removal = " + byIterator);

        ArrayList<Integer> byPredicate = new ArrayList<>(source);
        int[] tested = {0};
        byPredicate.removeIf(value -> {
            tested[0]++;
            return value % 2 == 0;
        });
        System.out.println("removeIf = " + byPredicate);
        System.out.println("predicate calls = " + tested[0]);

        ArrayList<String> letters = new ArrayList<>(
                List.of("A", "B", "C", "D", "E", "F"));
        letters.subList(1, 4).clear();
        System.out.println("after clearing [1, 4) = " + letters);

        ArrayList<Integer> fromFront = new ArrayList<>(source);
        long frontShiftCount = 0;
        while (!fromFront.isEmpty()) {
            frontShiftCount += fromFront.size() - 1L;
            fromFront.remove(0);
        }

        ArrayList<Integer> fromEnd = new ArrayList<>(source);
        long endShiftCount = 0;
        while (!fromEnd.isEmpty()) {
            int last = fromEnd.size() - 1;
            endShiftCount += fromEnd.size() - last - 1L;
            fromEnd.remove(last);
        }
        System.out.println("front removal suffix total = " + frontShiftCount);
        System.out.println("end removal suffix total = " + endShiftCount);
    }
}
```
Compile and run:

```shell
javac --release 17 ArrayListRemovalPatternsDemo.java
java ArrayListRemovalPatternsDemo
```
Output:

```text
incorrect forward removal = [4, 1, 3]
iterator removal = [1, 3]
removeIf = [1, 3]
predicate calls = 6
after clearing [1, 4) = [A, E, F]
front removal suffix total = 15
end removal suffix total = 0
```
Read the output from five angles:

1. **Correctness:** the faulty forward loop leaves `4` behind. After removing `2` at index 0, `4` shifts into index 0, but the next iteration advances straight to index 1.
2. **Removal mechanism:** `iterator.remove` produces the correct result `[1, 3]`, though each removal may still shift the trailing suffix.
3. **Bulk filtering:** `removeIf` also produces `[1, 3]`; with a simple predicate, `ArrayList` processes the removal in linear passes rather than shifting the tail after every single match.
4. **Range removal:** `subList(1, 4).clear()` removes B, C, and D; the upper bound index 4 is exclusive.
5. **Total elements shifted:** six removals from the front shift `5 + 4 + 3 + 2 + 1 + 0 = 15` suffix elements in total, whereas removing from the end shifts zero elements.

The totals in the program count the references belonging to shifted suffixes using our formula, not actual wall-clock runtime. Removing from the end still performs work to update `size` and clear references, so a shift count of 0 does not mean the overall algorithm does zero work.

Iterating backward from the end to the front can avoid skipping elements when removing by index, but it does not guarantee that every removal pattern becomes linear. If you remove many elements near the middle while many retained elements sit after them, that trailing suffix can still be shifted repeatedly.

## 12. Capacity, Memory, and Real-World Timing Measurements

### 12.1. clear Does Not Necessarily Free the Backing Array

In OpenJDK 17, `clear` nulls out the references of active elements and resets `size` to 0, but retains the internal array so its capacity can be reused. Therefore:

- `clear` allows the removed element objects to become eligible for garbage collection if no other references to them exist.
- You cannot assume that the memory allocated for the backing array itself is immediately returned.
- You may consider calling `trimToSize()` when you genuinely need to shrink the retained capacity; keep in mind that this operation copies the array and should not be called repeatedly inside an insertion loop.

If you reassign the variable to a brand-new `ArrayList`, the old backing array can be garbage-collected only when no references hold onto the old list. Active `subList` views or other objects referencing the list can extend the data's lifetime longer than expected.

### 12.2. Big O Does Not Replace Benchmarking, and Benchmarking Does Not Replace Big O

Two operations that are both `O(n)` can have very different constant factors. Copying a contiguous block of references is heavily optimized by the JVM, yet its work still grows with the number of references copied. Factors such as memory layout, CPU caches, allocation rate, garbage collection, and JIT compilation all affect measured wall-clock time.

Do not wrap a single `System.nanoTime()` call around an operation on a tiny list to draw conclusions about asymptotic complexity. At small sizes, measurement noise and call overhead can easily obscure the growth trend.

A sound evaluation workflow is:

1. Identify the exact operation, position, and input size.
2. Count the work using the analytical model to predict how cost scales as `n` grows.
3. If timing measurements are needed, prepare controlled test data and execution environments; separate data generation and output printing from the timed region when they are not part of the work being evaluated.
4. Measure across multiple input sizes and verify whether the empirical trend matches the analytical prediction.
5. Use a dedicated JVM benchmarking tool (such as JMH) whenever reliable performance comparisons are required.

The demonstration programs in this article intentionally print outputs and count comparisons or suffix lengths to illustrate internal mechanics. They are not benchmarks for comparing execution speed across collections.

## 13. Choosing an Algorithm Based on Operation Patterns

| Requirement | Assessment with ArrayList |
| --- | --- |
| Frequent reads by index, replacing values at an index | Well suited because `get`/`set` are constant time |
| Collecting results by appending to the end | Well suited; consider initial capacity and amortized cost |
| Traversing all elements in one or a few passes | Linear per pass; include per-element processing in your analysis |
| Frequent insertions or removals in the middle | Must account for the trailing suffix shifted on each operation |
| Repeated value-based lookups over large datasets | Linear search can easily become the dominant bottleneck |
| Frequently polling and removing the first element | Repeated front removals lead to quadratic total cost; consider a queue/deque structure |
| Removing all elements matching a condition | Prefer `removeIf` over multiple individual `remove` calls |
| Inserting a batch or removing a contiguous range | Bulk operations can avoid shifting the same suffix repeatedly |

A sorted `ArrayList` can be searched with a logarithmic number of comparisons using binary search via the appropriate API. The strict prerequisite is that the data must be sorted according to the exact same ordering rule used by the search; you must also account for the cost of sorting and maintaining that order when data changes. `contains` and `indexOf` do not automatically switch to binary search just because the elements happen to be in ascending order. See the preconditions of [Collections.binarySearch in Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T)).

Do not rush to switch to a linked list based solely on the claim that "insertions and removals are faster." If you have to traverse the list to locate the position before every insertion or removal, that search cost is part of the algorithm too. Always compare total work against your actual access pattern while preserving requirements around ordering, duplicates, and positional access.

If you maintain an auxiliary lookup index alongside an `ArrayList` for fast searches, adding or removing elements in the list can shift the indices of subsequent elements. That auxiliary index must be kept in sync; saving lookup time is no excuse for letting secondary state drift out of sync with the list.

## 14. Common Analysis Pitfalls

| Misconception | Correct Analysis |
| --- | --- |
| "`ArrayList.add` is always `O(1)`" | Appending to the end is amortized `O(1)`; a single expansion can take `O(n)`; inserting in the middle also shifts elements |
| "Knowing `i` makes both `add(i, x)` and `remove(i)` run in `O(1)`" | Knowing the position does not eliminate the work of shifting the trailing suffix to preserve order |
| "`set(i, x)` also has to shift elements" | `set` replaces a single slot; `size` and the indices of all other elements remain unchanged |
| "`contains` is `O(1)` because `ArrayList` implements `RandomAccess`" | `RandomAccess` relates to index-based lookup; searching by value is still linear |
| "Removing a value located at the end is `O(1)`" | `remove(value)` must scan from the beginning to find the match; only `remove(size() - 1)` jumps directly to the last slot |
| "Using `iterator.remove` avoids shifting when removing from the middle" | The iterator tracks traversal state, but the backing array still has to compact remaining elements |
| "A single `for` loop always means `O(n)`" | You must multiply/add the work performed inside each iteration, including searches and shifts |
| "`removeIf` is always `O(n)`, regardless of the predicate" | Include the predicate's cost; a predicate performing a nested linear search can make the total cost quadratic |
| "`new ArrayList<>(1000)` already contains 1,000 elements" | It only reserves capacity; the initial `size` is still 0 |
| "`clear` only sets `size = 0`, so it is `O(1)`" | In OpenJDK 17, `clear` also nulls out all active element references |
| "Amortized means average case over random data" | Amortization bounds the total cost over a sequence of operations without assuming random input distributions |
| "A tiny example running very fast proves `O(1)`" | Execution time at a single small size does not prove how the cost scales as `n` grows |

## 15. Self-Check by Counting the Work

### Exercise 1: Same Index, Different Operations

An `ArrayList` has `n = 1,000` and enough spare capacity for insertions. Analyze:

- `get(400)`: reads one slot directly, constant time.
- `set(400, x)`: replaces one slot, constant time.
- `add(400, x)`: shifts `1,000 - 400 = 600` elements; linear in `n` when keeping the same relative position.
- `remove(400)` on the original list: shifts `1,000 - 400 - 1 = 599` elements.

Always use the exact size at the moment the operation runs. If you execute these calls consecutively on the same list, the `add` call increases `n` before `remove` executes; do not mechanically plug the old size into subsequent steps.

### Exercise 2: Do You Have the Last Index or Only the Last Value?

Compare `remove(size() - 1)` with `remove(Integer.valueOf(999))` on an `ArrayList` containing the numbers `0` through `999`.

Answer: removing by the last index neither searches nor shifts, so it takes constant time. Removing by the value `999` must scan from the front all the way to the end, making it linear even though no elements need to be shifted after the match is found.

### Exercise 3: Total Cost of Front Insertions

Starting from an empty list, insert 1,000 elements using `add(0, value)`. How many element-shift steps occur from shifting alone?

Answer: `1,000 * 999 / 2 = 499,500` reference moves across the shifted suffixes. This does not yet include initial allocation, capacity expansions, or writing the new elements. The overall order of growth remains quadratic.

### Exercise 4: A Batch in the Middle

A list has 10,000 elements and sufficient spare capacity; a batch of 200 elements is inserted at index 2,000. What work must be accounted for?

Answer: retrieving/writing the 200 new elements and shifting the 8,000 existing elements after the insertion point. This cannot be called `O(1)`. If extracting data from the source collection is expensive, that cost must be added as well.

### Exercise 5: Nested Search Inside a Filtering Predicate

An `ArrayList` has `n` elements, and `removeIf` tests each element using `blockedList.contains(value)`; `blockedList` also has `n` elements, and values rarely match. Why can the overall filtering operation take `O(n²)`?

Answer: the predicate runs `n` times, and each search can inspect up to `n` elements in `blockedList`. Even though `ArrayList` compacts retained elements in linear passes, that does not eliminate the quadratic comparison work performed inside the predicate.

### Exercise 6: Proving Amortization with a Model

Using the capacity-doubling model, start with capacity 1 and append up to 32 elements. The total number of old references copied across capacity expansions is:

```text
1 + 2 + 4 + 8 + 16 = 31
```
Adding 32 writes for the new elements yields a total of 63 work units in this simplified counting model. Do not use the number 31 to claim that the real `ArrayList` uses those exact capacity milestones; the takeaway is that a geometric series sums to a value that grows linearly with the final number of elements.

When analyzing real code, always note **the size at each step, the operation position, the portion searched, the portion shifted, and when expansion can occur**. Those details allow you to derive the complexity directly instead of memorizing a table stripped of its preconditions.
