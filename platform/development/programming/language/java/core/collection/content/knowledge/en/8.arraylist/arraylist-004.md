# ensureCapacity and trimToSize

## 1. Two Capacity Management Operations of ArrayList

`ArrayList` uses a backing array to hold references to elements. The number of currently present elements is called `size`; the number of backing array slots available to hold elements is called `capacity`. There is often some spare space between these two quantities.

The following two methods affect capacity:

```java
public void ensureCapacity(int minCapacity)
public void trimToSize()
```

These are API signatures, not a standalone Java program.

- `ensureCapacity` prepares enough space for an expected total number of elements, growing when necessary.
- `trimToSize` shrinks the capacity down to the current number of elements.

They are not operations that add or remove elements. A list with content `[A, B, C]` still has that content after a successful call to either method.

Their purpose is to help balance the number of array allocations/copies against the amount of spare capacity retained. Used at the right time, they can be useful; calling them excessively does not automatically make a program more efficient.

| Property | ensureCapacity(minCapacity) | trimToSize() |
|---|---|---|
| Goal | Prepare space for at least the total number of elements needed | Drop spare capacity beyond the current size |
| Changes size? | No | No |
| Changes element order or values? | No | No |
| Can replace the backing array? | Yes, if growth is needed | Yes, if shrinking is needed |
| Reduces an already large capacity? | Not used for shrinking | Yes, down to size |
| Return type | `void` | `void` |
| Can elements still be added/removed afterward? | Yes | Yes |

These are `ArrayList`-specific methods and do not belong to the `List` interface. [ArrayList.ensureCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#ensureCapacity(int)), [ArrayList.trimToSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#trimToSize()).

## 2. ensureCapacity Takes a Minimum Total Capacity

### 2.1. Not the Number of Slots to Add to Capacity

Illustrative snippet inside a method, requiring `import java.util.ArrayList`:

```java
ArrayList<String> names = new ArrayList<>(2);
names.add("An");
names.add("Binh");

names.ensureCapacity(100);

// names.size() is still 2.
// names still contains [An, Binh].
```

The number 100 means preparing space so the list can hold at least 100 elements in total; it does not mean "add 100 more slots on top of the current capacity".

The method also does not mean "set capacity to exactly 100". If the capacity is already large enough, no growth is needed; when growth is required, the implementation's policy may choose an array larger than the minimum requested.

Conceptual examples:

| Before Call | Call | Appropriate Conclusion |
|---|---|---|
| Capacity is currently 20 | `ensureCapacity(100)` | Prepares enough space for at least 100 elements in total |
| Capacity is currently 200 | `ensureCapacity(100)` | Does not shrink down to 100 |
| Size is currently 50 | `ensureCapacity(10)` | Does not remove 40 elements; size remains 50 |
| Empty list | `ensureCapacity(100)` | Does not create 100 `null` elements; size remains 0 |

The capacity numbers in the table are hypothetical values to explain the parameter's meaning, not results read via a public method.

### 2.2. When About to Add a Batch of Data, Compute the Required Total

Suppose there are currently `currentSize` elements and `incomingCount` elements are about to be added. The target is:

```text
requiredTotal = currentSize + incomingCount
```

Illustrative snippet:

```java
int requiredTotal = Math.addExact(rows.size(), incoming.size());
rows.ensureCapacity(requiredTotal);
```

Here `rows` is an existing `ArrayList` and `incoming` is an independent data source that remains stable during loading. `Math.addExact` checks for `int` overflow; if the sum cannot be represented, it throws `ArithmeticException` instead of silently turning into an incorrect value.

For example, if there are currently 8,000 items and 5,000 items are about to be added, the required total is 13,000. Calling only `ensureCapacity(5_000)` does not express the need to hold the total number of items after the batch addition.

The fact that the sum fits within `int` does not guarantee that enough memory is available to allocate that array. These are two different conditions: the count calculation does not overflow, and actual resources can satisfy the request. [Math.addExact(int, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)).

If you only need to append a collection directly, `ArrayList`'s `addAll` already has a mechanism to prepare space based on the number of elements to add. Do not assume that calling an extra `ensureCapacity` before every `addAll` is always necessary or always faster. Explicit reservation usually makes sense when you know in advance the scale of a multi-step loading or processing sequence.

### 2.3. Reserving Space Does Not Make Indices Valid

Illustrative snippet:

```java
ArrayList<String> rows = new ArrayList<>();
rows.ensureCapacity(50);

rows.set(0, "first"); // IndexOutOfBoundsException
```

The list still has a size of 0. `set` only replaces an existing element, whereas capacity is merely storage space. To create the first element, use `rows.add("first")`.

Index bounds are still based on size:

- `get(i)`, `set(i, value)`: `0 <= i < size()`.
- `add(i, value)`: `0 <= i <= size()`.
- Reserving more space does not automatically create intermediate elements.

### 2.4. Capacity Is Not Business Input Validation

If a system allows at most 100 items, `ensureCapacity(100)` does not enforce that limit. A 101st element can still be added; a separate validation rule is required.

Similarly, if an expected count comes from input, validate it yourself. Do not use `ensureCapacity` as a quantity validation function. For example, in OpenJDK 17, a negative request does not enter the array-growth branch; you cannot rely on it always throwing an error to catch a miscalculation.

By contrast, a negative initial capacity argument to the `ArrayList(int)` constructor is specified to throw `IllegalArgumentException`. The two APIs have different purposes; do not infer the validation rules of one method from the other.

## 3. trimToSize Shrinks Spare Capacity and Preserves Elements

Suppose a list currently has:

```text
size = 3
capacity = 10
logical content = [A, B, C]
```

After `trimToSize()`:

```text
size = 3
capacity = 3
logical content = [A, B, C]
```

If shrinking is needed, the implementation creates smaller storage just sufficient for the existing references. It does not call `remove` to drop elements and does not make the last element disappear.

Illustrative snippet:

```java
ArrayList<String> names = new ArrayList<>(1_000);
names.add("An");
names.add("Binh");

names.trimToSize();

// names is still [An, Binh].
// names.size() is still 2.
```

### 3.1. Elements Can Still Be Added After Trimming

`trimToSize` does not turn the list into a fixed-size or unmodifiable list.

If capacity equals size and `add` is called, the list must obtain more space for the new element again. Therefore, trimming early and then continuing to load many elements can cause extra allocations/copies that would not have been needed otherwise.

Also, do not use trim as a way to set a "hard limit" equal to the current size. It is a storage adjustment at the time of the call.

### 3.2. clear and trim Address Two Different Goals

| Operation | Logical Elements | Backing Storage in OpenJDK Implementation |
|---|---|---|
| `clear()` | Removes all elements, size becomes 0 | Retains the backing array for reuse |
| `trimToSize()` | Preserves elements | Shrinks capacity down to size |
| `clear(); trimToSize();` | Removes all elements | Also drops the excess storage of the empty list |

If the list holds data and you only call trim, the data is still retained by the list. Trimming is not a way to "free the element objects".

If you call clear and then trim, whether the old objects remain alive still depends on other references. Even when the old array is no longer retained, garbage collection reclamation or an observable memory reduction at the OS level is not guaranteed to happen immediately at the call site.

A processing batch followed by another batch of similar scale can benefit from keeping the array after clear. A very large batch followed by long-term retention of a small list may be a reason to consider trimming. Base the decision on the data lifecycle, not just the current size.

## 4. The Cost of Both Methods Lies in Array Allocation and Copying

Java arrays have a fixed length. When the backing array length needs to change, `ArrayList` does not directly modify the `length` property of the old array; it uses a different array.

### 4.1. Cost When Growing

When `ensureCapacity` must grow:

1. Compute a new array length sufficient to satisfy the request.
2. Allocate a new reference array.
3. Copy the contents of the old array into the new array.
4. Have the same `ArrayList` object use the new array.

In OpenJDK, the copy operation may traverse the spare slots of the old array as well, not just the logical elements. Therefore, do not describe every reservation as having an exact cost of `O(size)` when the old capacity could be much larger than size.

Beyond the copying cost, there is also the cost of allocating and initializing the new array, which depends on the requested size. Increasing capacity is a real memory management operation, not merely updating a number.

### 4.2. Cost When Shrinking

When trim actually shrinks the array and size is non-zero, new storage for `size` references is needed along with copying the references in use. If size is 0, the implementation can switch to a shared empty array.

During array replacement, the old array and the new array coexist temporarily. Trimming aims to reduce space retained afterward, but the operation itself may require an additional allocation before the old array becomes eligible for reclamation.

### 4.3. Does Not Create a New List or Deep-Copy Elements

Both methods return `void` and adjust the same list object. If two variables reference the same `ArrayList`, they still reference that same list after the call.

Element objects are not duplicated automatically. Replacing the backing array only replaces where the references are held; an element object may still be referenced from multiple places. Do not use these two methods to create an independent copy or make data immutable.

## 5. Choosing When to Reserve and Shrink

A lifecycle that is often easy to manage is:

```text
Estimate the number of elements to hold
        |
        v
Provide initial capacity or call ensureCapacity
        |
        v
Load/add/process data
        |
        v
Complete the major modification phase
        |
        v
If retained long-term with few further additions: consider trimToSize
        |
        v
Create iterators/views or hand off data for reading
```

Not every list needs a reservation or trim step. This flow places capacity management operations at easy-to-control boundaries when there is a clear reason for them.

| Scenario | How to Consider |
|---|---|
| Creating a new list with a fairly certain total item count | `new ArrayList<>(expectedTotal)` usually expresses this directly |
| Existing list, about to load many more items | Compute the required total and consider `ensureCapacity` |
| Small count or no reasonable estimate | Letting automatic growth work is usually sufficient |
| Just removed many items, and the small list will be kept long-term | Consider trimming after removals are finished |
| Loading continuously | Keep spare capacity; avoid trimming between every addition |
| Calling clear and about to load a similar batch right after | Retaining the backing array can be beneficial |
| Iterators or views are currently in use | Complete capacity management at an appropriate boundary before traversing/recreating views |

Overestimating too much can cause a lot of unused space to be retained. Underestimating still does not corrupt data; the list can grow automatically, though the benefit of avoiding reallocations may be reduced.

## 6. Complete Program: Reserving for a Batch and Then Shrinking

The short snippets above are in-method illustrations and require appropriate imports. The following program is a standalone file using APIs available in Java 17.

Save as `CapacityLifecycleDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CapacityLifecycleDemo {
    private static void appendBatch(
            ArrayList<String> target, List<String> batch) {
        int requiredTotal = Math.addExact(target.size(), batch.size());
        target.ensureCapacity(requiredTotal);
        System.out.println("required total = " + requiredTotal);
        System.out.println("size after reserve = " + target.size());

        for (String value : batch) {
            target.add(value);
        }
    }

    public static void main(String[] args) {
        ArrayList<String> rows = new ArrayList<>(2);
        rows.add("seed");
        ArrayList<String> alias = rows;

        appendBatch(rows, List.of("A", "B", "C"));
        System.out.println("after append = " + rows);
        System.out.println("size after append = " + rows.size());

        rows.remove(1);
        List<String> beforeTrim = new ArrayList<>(rows);
        rows.trimToSize();
        System.out.println("after trim = " + rows);
        System.out.println("trim preserved content = " + rows.equals(beforeTrim));
        System.out.println("same list object = " + (rows == alias));

        rows.add("D");
        System.out.println("after append following trim = " + rows);
        System.out.println("size = " + rows.size());

        rows.clear();
        System.out.println("after clear = " + rows + "; size = " + rows.size());

        rows.ensureCapacity(50);
        System.out.println("after reserve on empty = " + rows
                + "; size = " + rows.size());
        try {
            rows.set(0, "X");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("set(0) after reserve -> IndexOutOfBoundsException");
        }

        rows.trimToSize();
        rows.add("again");
        System.out.println("after empty trim and reuse = " + rows);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CapacityLifecycleDemo.java
java CapacityLifecycleDemo
```

Standard output:

```text
required total = 4
size after reserve = 1
after append = [seed, A, B, C]
size after append = 4
after trim = [seed, B, C]
trim preserved content = true
same list object = true
after append following trim = [seed, B, C, D]
size = 4
after clear = []; size = 0
after reserve on empty = []; size = 0
set(0) after reserve -> IndexOutOfBoundsException
after empty trim and reuse = [again]
```

The `appendBatch` method has a precondition in this example: `batch` is independent of `target` and is not modified during loading. If the data source is the target list itself, iterating and adding simultaneously becomes a different problem; do not apply this loop verbatim to that case.

Key steps to note:

1. The initial list has one element `seed`; the batch has three elements. The required total capacity is 4, not 3.
2. After reserving, size is still 1. Only the `add` calls inside the loop increase size to 4.
3. After removing `A`, trimming preserves `[seed, B, C]`.
4. Comparing against a content copy created before trimming yields `true`; the `alias` variable is still the exact same list object.
5. Adding `D` after trimming still succeeds, showing that trimming does not freeze the list.
6. Reserving space on an empty list does not create element 0; `set(0, ...)` is still rejected.
7. After trimming when empty, the list can still be reused with `add`.

The example verifies content, size, and list reference identity. It does not print capacity by guessing.

## 7. No Public API Exists to Read and Print Capacity

`ArrayList` has `size()`, `ensureCapacity`, and `trimToSize`, but does not provide a public `capacity()` method.

Therefore, a program using only public APIs should verify facts such as:

- Reserving and trimming do not change size or element order.
- Reserving does not make `set` at a non-existent position valid.
- Further additions are still possible after trimming.
- Two variables referencing the same list preserve that relationship.

`toArray().length` is the length of the resulting array containing logical elements, not the capacity of the backing array. Using it as a measure of capacity is both semantically wrong and creates an unnecessary extra array.

Numbers regarding growth factors, shared empty arrays, or modification-tracking fields can be studied in the source code of the specific JDK version under consideration. They must be clearly noted as implementation analysis, not turned into mandatory assumptions in business code.

## 8. OpenJDK 17 Implementation Details to Distinguish from the Contract

### 8.1. Small Reservations on a Default Empty List May Not Allocate a Dedicated Array Yet

OpenJDK 17 uses deferred array allocation for an empty list created with `new ArrayList<>()`. A small capacity request within the default range may not immediately allocate a dedicated array; the initial allocation policy will be applied when elements are actually added.

Therefore, do not use an `ensureCapacity(5)` call on a default empty list as proof that "a physical array of exactly five slots was immediately allocated". Understand the meaning of preparing capacity and separate it from the specific allocation mechanics.

### 8.2. Growth May Exceed the Request

The growth policy in OpenJDK 17 combines a preferred growth increment with the minimum capacity currently needed. The number passed to `ensureCapacity` is not a mandate to choose that exact array length.

Do not rely on a fixed factor such as "always doubles" or "always exactly 1.5x" to validate program correctness. Small increments, batch requests, and array limits can make actual progression differ from a simple formula.

### 8.3. Methods That Appear Content-Preserving Can Still Affect Traversal

OpenJDK 17 maintains a modification counter to check iterators and related views:

- `ensureCapacity`, when it actually enters the growth branch, updates the modification-tracking state.
- `trimToSize` updates the counter even when capacity already equals size and no array replacement is needed.

The second point is very easy to miss if you only reason that "content did not change, so the iterator can definitely still be used". This is an implementation detail mentioned to explain the behavior; you neither need nor should access that counter directly from application code. [ensureCapacity, trimToSize, and grow in OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

## 9. Impact on Iterators and subList

### 9.1. Same Size Does Not Mean Same Structural State

The `ArrayList` documentation explicitly counts resizing the backing array among structural modifications. Consequently, growing or shrinking the array can invalidate a previously created iterator, even though the size and element contents remain the same as before.

A subsequent call such as `iterator.next()` may throw `ConcurrentModificationException`. The exception's name does not require two threads; a single thread can also create an iterator, change capacity, and then reuse the old iterator.

A better structure is to finish reserving/trimming before starting a traversal that requires a stable iterator, and then create the iterator after those operations.

Do not build program correctness around always seeing the exception at the exact same spot. The modification detection mechanism primarily aids bug hunting; respect iterator lifecycles and modification rules instead of catching the exception and continuing.

### 9.2. A subList View Also Remains Tied to the Backing List

A `subList` is a view of its source. If the source is structurally modified outside the view's own operations, the contract does not guarantee the semantics of the old view.

Therefore, do not create `part = list.subList(...)`, call `list.ensureCapacity(...)` causing the source array to grow or shrink, and assume the old view is guaranteed to be safe because "only memory changed".

Place capacity management before creating the view you need, or finish using the view before structurally modifying the source. If recreating the view, compute its bounds according to the current state and data selection intent. [Modification rules of ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [usage limits of List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

### 9.3. Program Observing OpenJDK's Detection Mechanism

The following program uses APIs available in Java 17 and illustrates the branches compared against the OpenJDK 17 implementation. The exception outcomes below demonstrate that mechanism, not a requirement that every JVM must detect every change at these exact calls.

Save as `CapacityTraversalDemo.java`:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class CapacityTraversalDemo {
    private static void readNext(String label, Iterator<String> iterator) {
        try {
            System.out.println(label + " -> " + iterator.next());
        } catch (ConcurrentModificationException ex) {
            System.out.println(label + " -> ConcurrentModificationException");
        }
    }

    public static void main(String[] args) {
        ArrayList<String> growing = new ArrayList<>(2);
        growing.add("A");
        Iterator<String> beforeGrowth = growing.iterator();
        growing.ensureCapacity(100);
        readNext("reserve that grows", beforeGrowth);
        readNext("new iterator after reserve", growing.iterator());

        ArrayList<String> shrinking = new ArrayList<>(10);
        shrinking.add("B");
        Iterator<String> beforeShrink = shrinking.iterator();
        shrinking.trimToSize();
        readNext("trim that shrinks", beforeShrink);

        ArrayList<String> alreadyTight = new ArrayList<>(1);
        alreadyTight.add("C");
        Iterator<String> beforeNoOpTrim = alreadyTight.iterator();
        alreadyTight.trimToSize();
        readNext("trim when capacity equals size", beforeNoOpTrim);

        ArrayList<String> sufficient = new ArrayList<>(4);
        sufficient.add("D");
        Iterator<String> beforeNoOpReserve = sufficient.iterator();
        sufficient.ensureCapacity(2);
        readNext("reserve with sufficient capacity", beforeNoOpReserve);

        ArrayList<String> root = new ArrayList<>(2);
        root.add("X");
        root.add("Y");
        List<String> part = root.subList(0, 1);
        root.ensureCapacity(100);
        try {
            System.out.println("old subList size -> " + part.size());
        } catch (ConcurrentModificationException ex) {
            System.out.println("old subList -> ConcurrentModificationException");
        }
        System.out.println("root content = " + root);
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 CapacityTraversalDemo.java
java CapacityTraversalDemo
```

Observed output with the described OpenJDK mechanism:

```text
reserve that grows -> ConcurrentModificationException
new iterator after reserve -> A
trim that shrinks -> ConcurrentModificationException
trim when capacity equals size -> ConcurrentModificationException
reserve with sufficient capacity -> D
old subList -> ConcurrentModificationException
root content = [X, Y]
```

Explanation of the cases:

- `growing` has an initial capacity of 2 and one element. Requesting 100 forces preparing a larger array; the old iterator is rejected, while a new iterator created after the reservation reads `A`.
- `shrinking` has plenty of spare capacity. Trimming shrinks the array and the previously created iterator is rejected.
- `alreadyTight` already has capacity equal to size. Even though no array shrinking is needed, trim still updates the counter in the implementation under consideration, so the old iterator is also rejected.
- `sufficient` already has capacity 4 and only requests 2. The reserve branch does not need to grow, so the iterator in the example still reads `D`.
- `part` is a view created before `root`'s array grew. Reusing the old view is detected, while the source still contains `[X, Y]`.

Do not infer from the non-growing reserve case that capacity management calls should be interleaved into the middle of every traversal. To keep code easy to understand and less dependent on implementation details, manage capacity at boundaries before or after traversal.

## 10. Usage Patterns That Defeat the Benefits of Dynamic Arrays

### 10.1. Trimming After Every Addition

Illustrative snippet of a pattern to avoid during a large loading batch:

```java
for (String value : incoming) {
    rows.add(value);
    rows.trimToSize();
}
```

After each iteration, capacity is forced tight against size. On the next iteration, adding an element requires more space again; then trim immediately drops the spare capacity just acquired.

Over a sufficiently long loop, copying can accumulate as `1 + 2 + ... + n`, leading to quadratic cost instead of leveraging the amortized growth of a normal sequence of appends. It also creates many intermediate arrays.

If trimming is genuinely needed, do it after the major batch of additions/removals has finished and there is a reason to keep the structure compact going forward.

### 10.2. Reserve and Trim Pulling Against Each Other

Illustrative snippet:

```java
rows.ensureCapacity(10_000);
rows.trimToSize();
```

If `rows` is currently small, the first statement prepares a large amount of space while the second drops the spare capacity. With no loading batch in between, these two goals conflict and can cause redundant allocations/copies.

Calls should be tied to a specific data phase: prepare before loading, shrink after stabilizing if necessary.

### 10.3. Overly Large Reservations or Optimizing by Guesswork

Reserving a very large capacity can increase retained memory, allocation pressure, and temporary memory during array replacement. It does not speed up element object creation, linear search, or element shifting when inserting in the middle.

When evaluating benefits, measure actual usage patterns: data size, number of reload batches, number of removals, list retention duration, and allocation volume. Do not conclude from a single very short run that every list needs reserving or trimming.

## 11. Variable Types and Design Boundaries

The following snippet intentionally does not compile:

```java
List<String> rows = new ArrayList<>();
rows.ensureCapacity(100);
```

The variable has a declared type of `List`, so only methods belonging to that interface are visible. If you are building data with an `ArrayList` and genuinely need capacity management, you can keep a concrete local variable:

```java
ArrayList<String> building = new ArrayList<>(100);
building.add("A");
building.trimToSize();

List<String> result = building;
```

This is an illustrative snippet requiring `import java.util.List` and `java.util.ArrayList`. Assigning to `List` does not copy or make the list immutable; `result` still references the same object.

Do not cast an arbitrary `List` to `ArrayList` just to call trim. A list received from outside might be a different implementation or have its own data ownership policy. Capacity management should reside where the construction and usage of that structure are actually owned.

Neither method provides synchronization for multiple threads. Reserving enough space does not make additions or traversals safe under concurrent modification.

## 12. Self-Check and Correcting Misconceptions

| Misconception | Correct Understanding |
|---|---|
| `ensureCapacity(100)` adds 100 elements | It manages storage capacity; size does not change |
| The parameter is the number of slots to add | It is the minimum total capacity to satisfy |
| Reserving sets capacity to the exact parameter | It does not shrink and may choose a size larger than requested |
| `trimToSize` removes elements | It drops spare capacity while preserving logical content |
| Cannot add elements after trimming | The list still grows its capacity if more elements are added |
| Once enough space is reserved, `set` works at any index | `set` still requires an existing element within `size` |
| Content didn't change, so iterators are guaranteed to remain valid | Capacity methods can affect structural modification tracking state |
| `clear` and trim are the same operation | One removes elements; the other shrinks storage capacity |
| Trimming immediately returns all memory to the OS | It adjusts storage structure; actual reclamation has its own lifecycle |
| Calling both methods after every loop is always good | Calling them at the wrong time can cause repeated array copies and allocations |

Predict the following scenarios before running:

1. A list has size 20 and a hypothetical capacity of 100; `ensureCapacity(50)` is called. Are 50 slots removed to make capacity 50?
2. There are currently 200 items, and 80 items are about to be added. Should the requested total be 80, 200, or 280?
3. After `trimToSize` on a three-element list, will calling `add` be rejected just because it was trimmed?
4. On an empty list that has reserved 100, is `set(99, value)` valid?
5. Multiple batches of 10,000 items need to be reloaded repeatedly. Is calling clear and then trim after every batch guaranteed to be better than calling clear and reusing the array?
6. In OpenJDK 17, is trimming when capacity already equals size guaranteed not to affect an existing iterator?

Answers:

1. No; `ensureCapacity` is not responsible for shrinking.
2. 280, computed with appropriate overflow checking; the parameter is the total required capacity.
3. No; adding can cause the array to grow again.
4. No; size is still 0.
5. Not necessarily; trimming can force the next batch to reallocate space it already had.
6. No; that implementation still updates the modification counter when trim is called.

Choose these two methods according to the data usage phase: reserve when there is a solid basis for the total number of elements soon needed, and shrink when the structure has stabilized and the benefit of retaining less spare space outweighs the copying cost. Keep questions of content, storage capacity, and iterator/view lifecycles separate so you do not trade correctness for an unverified optimization.
