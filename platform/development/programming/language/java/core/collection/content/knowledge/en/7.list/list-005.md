# Inserting Multiple Elements with Indexed addAll

When you need to insert a group of elements into the middle of a list, `List.addAll(index, source)` expresses the intent directly: place the entire group at one position, preserve the order provided by the source, and shift the tail of the destination list to the right.

For example:

~~~text
Initial destination: [A, D]
Inserted batch:      [B, C]
Position:            1

Result:              [A, B, C, D]
~~~

This is an **insertion**, not a replacement of two elements, nor does it move the group out of the source. When the source and destination are independent, the source elements remain in the source after the operation.

This article uses examples in Java 17 or later and primarily uses a mutable `ArrayList` to make the results clear.

## 1. Signature and Three Distinct Roles

The signature in `List<E>`:

~~~java
boolean addAll(int index, Collection<? extends E> source)
~~~

This signature is shown for understanding; it is not a method you need to implement yourself when simply using a `List`.

- The receiver of the call is the **destination list**.
- `index` is the position in the destination that the first element of the batch will receive.
- `source` is the collection providing the elements of the batch.
- The return value indicates whether the destination changed as a result of the call, not the number of elements added.

For example:

~~~java
// Code snippet inside a method; requires the corresponding java.util imports.
List<String> destination = new ArrayList<>(List.of("A", "D"));
List<String> source = List.of("B", "C");

boolean changed = destination.addAll(1, source);

System.out.println(changed);     // true
System.out.println(destination); // [A, B, C, D]
~~~

The source does not have to be a `List`; the parameter accepts any compatible `Collection`. A `Set` can also provide elements, though the ordering rules of the source must still be clearly understood.

An arbitrary `Iterable` or a `Stream` does not automatically become a `Collection` just because it can produce elements. If an input API is not a `Collection`, you need to choose an appropriate collection or iteration approach before using this overload.

The contract regarding position, source ordering, and source modification during execution is documented in [List.addAll in Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#addAll(int,java.util.Collection)).

## 2. Insertion Position: From 0 to size, Inclusive

For a destination list with `n` elements:

~~~text
0 <= index <= n
~~~

is the valid range of insertion positions.

For example, if the destination `[A, D]` has size `2`:

~~~text
Positions: 0   1   2
           | A | D |
~~~

- `index == 0`: insert before `A`.
- `index == 1`: insert between `A` and `D`.
- `index == 2`: insert after `D`, i.e., append to the end.

Do not confuse this with `get` or `set`: those two methods require an existing element, so the index must be strictly less than `size`. `addAll` inserts into a boundary gap, so an index equal to `size` is permitted.

### Beginning of the List

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));
destination.addAll(0, List.of("H1", "H2"));

System.out.println(destination); // [H1, H2, A, D]
~~~

The entire batch `H1, H2` is placed at the front in the exact order of the source.

### End of the List

~~~java
destination.addAll(destination.size(), List.of("T1", "T2"));
~~~

The batch is placed at the end. There are no existing elements after the insertion point whose indices need to shift.

In terms of resulting sequence content when the operation is supported, `destination.addAll(source)` is the append-at-end form; the indexed overload lets you choose a position other than the end.

### Empty Destination

~~~java
List<String> destination = new ArrayList<>();
destination.addAll(0, List.of("first", "second"));

System.out.println(destination); // [first, second]
~~~

When the destination is empty, `0` is the only valid insertion position. Reserved capacity inside an `ArrayList` does not expose any additional public positions while `size` is still `0`.

## 3. The Prefix – New Batch – Suffix Model

Let:

- `n`: destination size before the operation.
- `p`: insertion position.
- `m`: number of elements in the stable source during the operation.

When successful, the result can be read as:

~~~text
old destination [0, p)
    + source elements in iteration order
    + old destination [p, n)
~~~

For example:

~~~text
Destination: [A, B, E, F]
p = 2
Source:      [C, D]
m = 2

Prefix:      [A, B]
New batch:   [C, D]
Suffix:      [E, F]

Result:      [A, B, C, D, E, F]
~~~

How positions change:

| Group | Position After Insertion |
| --- | --- |
| Old destination element at j < p | Keeps position j |
| The k-th element of the source, with k starting from 0 | Receives position p + k |
| Old destination element at j >= p | Moves to j + m |

The new size is `n + m` if the entire batch was inserted successfully.

The relative order among the existing destination elements is not reversed: `E` still comes before `F`. The order of the source batch is not reversed either: `C` comes before `D`.

### This Is Insertion, Not Overwriting

If you use `set` to replace positions starting at `p`, you are writing a different algorithm—one that can lose old elements or go out of bounds when there are not enough existing slots.

`addAll` preserves the old tail by making room for the new batch. There is no need to manually remove, save, and re-append the tail just to perform a standard insertion.

## 4. Batch Order Comes from the Source Iterator

`addAll` does not sort elements on its own.

With:

~~~java
List<String> source = List.of("C", "B");
~~~

the inserted batch is `C` then `B`, not `B` then `C`.

With a source that has a well-defined insertion order:

~~~java
LinkedHashSet<String> source =
        new LinkedHashSet<>(List.of("C", "B", "C"));

List<String> destination = new ArrayList<>(List.of("A", "D"));
destination.addAll(1, source);

System.out.println(destination); // [A, C, B, D]
~~~

The source `Set` eliminated the duplicate occurrence of `C` according to its contract. The destination list receives `C` then `B` in the order provided by the source.

If the source is a `HashSet`, do not rely on a particular iteration order that happens to be observed. The fact that the destination is an `ArrayList` does not recover insertion history or sort the source in natural order.

If you need an explicit ordering rule:

~~~java
// source is an existing Collection<String>; assumed to contain no nulls.
List<String> orderedBatch = new ArrayList<>(source);
orderedBatch.sort(Comparator.naturalOrder());

destination.addAll(position, orderedBatch);
~~~

This snippet explicitly chooses natural order for `String` keys. That is an extra decision made before insertion, not the default behavior of `addAll`.

### Source List with Duplicate Elements

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));
destination.addAll(1, List.of("B", "B"));

System.out.println(destination); // [A, B, B, D]
~~~

In this `ArrayList`, both occurrences of `B` are added. Having values already present in the destination or repeated in the source does not turn `addAll` into a set union operation.

For a specialized `List` class with its own element restrictions, consult its specific contract. Do not assume every class implementing `List` accepts all data that an `ArrayList` permits.

## 5. Return Boolean and Empty Source

With a mutable `ArrayList`:

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));

boolean changed = destination.addAll(1, List.of());

System.out.println(changed);     // false
System.out.println(destination); // [A, D]
~~~

An empty source provides no new elements to insert.

The boolean return value is not:

- The number of elements added.
- The ending index of the batch.
- A resulting `List`.
- An indication that the source elements are all distinct from every value already in the destination.

If you insert `B, B` into an `ArrayList`, the destination still grows by two elements and the result is `true`. A `List` does not deduplicate like a `Set`.

### An Empty Source Does Not Bypass Every Precondition

Do not treat an empty source as an excuse to pass an arbitrary index or ignore the mutability policy of the target list.

For example, on an `ArrayList` of size `2`, index `3` is still out of the valid insertion range. A list that does not support `addAll` may still reject the call even when it would add zero elements.

Likewise, do not infer from `false` that all internal state or existing iterators are guaranteed to be unaffected. The boolean reports whether content changed under the method contract; do not use it as an iterator versioning protocol.

### A Null Collection Is Different from an Empty Collection

~~~java
destination.addAll(1, null); // NullPointerException
~~~

`null` is not a collection with zero elements.

A source containing a `null` element is a separate case. `ArrayList` allows `null` elements, so a source like `Arrays.asList("B", null)` can be inserted into it. For destinations that forbid `null`, follow their contract and validate data accordingly.

Do not use `List.of("B", null)` to construct the source for this case, because `List.of` itself rejects `null` before `addAll` is even called.

## 6. Why Does Looping add at the Same Index Reverse the Order?

Consider this code:

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));

for (String value : List.of("B", "C")) {
    destination.add(1, value);
}

System.out.println(destination); // [A, C, B, D]
~~~

Step-by-step progression:

~~~text
Initially:     [A, D]
add(1, "B"):   [A, B, D]
add(1, "C"):   [A, C, B, D]
~~~

The second iteration still inserts at index `1`, right before the `B` that was just added. Therefore, this loop is not equivalent to `addAll(1, [B, C])`.

If you must write an order-preserving loop, you need to advance the insertion point:

~~~java
int insertion = 1;
for (String value : List.of("B", "C")) {
    destination.add(insertion, value);
    insertion++;
}
~~~

This snippet assumes we start from the initial destination `[A, D]`. The result is `[A, B, C, D]`.

However, when the source is already a `Collection` and the goal is to insert the entire batch, a single `addAll` call usually expresses the intent more directly. In some implementations, it can also avoid repeatedly shifting the tail.

Do not use the correctness of a loop on a small `ArrayList` to conclude that both approaches have the same cost across all `List` implementations.

## 7. An Independent Source Is Neither Consumed Nor Linked as a View

For example:

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));
List<String> source = new ArrayList<>(List.of("B", "C"));

destination.addAll(1, source);

System.out.println(source); // [B, C]

source.set(0, "source-only");

System.out.println(source);      // [source-only, C]
System.out.println(destination); // [A, B, C, D]
~~~

The destination does not retain a live link of the form "this slice always reflects the slots of `source`." It simply added the elements supplied during that operation.

Replacing the element held by `source` after insertion does not replace the corresponding element in `destination`. Removing elements from `source` is not a way to remove the inserted batch from the destination either.

### But Objects Are Not Deep-Copied

Object elements are added by reference. If both the source and the destination hold references to the same mutable object, mutating the internal state of that object will be visible through both collections.

Distinguish between:

- Replacing a slot in `source` via `source.set(...)`: changes the reference stored in `source`.
- Mutating the state of an object held by both sides: the same shared object instance is modified.
- Deep copying: requires an application-specific copying policy; `addAll` does not perform deep copies automatically.

The `String` examples use immutable objects to observe ordering and structural independence of the lists; they do not imply that every element type is immutable.

## 8. When Source and Destination Share Data: Snapshot the Batch First

Do not write general-purpose algorithms that rely on inserting a list into itself directly:

~~~java
// Do not rely on this call as a general self-copy contract.
destination.addAll(position, destination);
~~~

The contract leaves general behavior undefined if the source collection is modified while the operation is in progress. Passing a non-empty destination as its own source is a situation where you must avoid relying on implementation-specific behavior. Even if a particular implementation copies the source into a temporary array and produces an intuitive result in one run, that does not make it a general guarantee.

Similarly, a `subList` can be a view backed by the destination itself. Modifying the destination can invalidate or alter the backing structure that the source view depends on.

### Snapshot the Slice Before Modifying the Destination

~~~java
List<String> destination =
        new ArrayList<>(List.of("A", "B", "C", "D"));

List<String> captured =
        new ArrayList<>(destination.subList(0, 2));

destination.addAll(2, captured);

System.out.println(destination); // [A, B, A, B, C, D]
~~~

The batch `A, B` is captured into a structurally independent collection before `destination` is modified.

In this single-threaded program, there is no concurrent modification of the source while capturing. A copy constructor call does not by itself solve concurrent modifications from another thread; if data is shared across threads, proper synchronization or thread-safe snapshotting is required.

After the backing structure changes, do not keep using an old `subList` view under the assumption that its positions remain valid. Here, `captured` is independent, so there is no need to access the view again after creating the batch.

## 9. Generic Types: Collection<? extends E>

If the destination is a `List<Number>`, it can accept a `List<Integer>` as the source:

~~~java
List<Number> destination =
        new ArrayList<>(List.of(0.5, 1.5));

List<Integer> integers = List.of(10, 20);
destination.addAll(1, integers);

System.out.println(destination); // [0.5, 10, 20, 1.5]
~~~

The destination accepts `Integer` elements because every `Integer` is a `Number`.

`? extends E` on the source parameter allows reading elements of any subtype compatible with the destination. It does not turn the source itself into a `List<Number>`, nor do you need to cast the collection to pass it.

Conversely, a `List<Object>` is not automatically accepted as a valid source for a `List<String>` just because the caller believes all current elements happen to be `String` instances. Static type checking verifies what the collection contract permits it to hold, not just a runtime snapshot of its current contents.

### add Is Not addAll

With a `List<String>`, calling `add(sourceList)` is not how you add the `String` elements of `sourceList`; the element type `String` does not match a `List` object.

With a wider destination type such as `List<Object>`, `add(sourceList)` adds **the `List` object itself as a single element**. In contrast, `addAll(sourceList)` adds each direct element of the source collection.

`addAll` does not recursively flatten arbitrary nesting levels either. It processes the direct elements supplied by `source`; if those direct elements are sublists compatible with the destination element type, they remain sublist elements.

## 10. Mutability and Exceptions

| Aspect | What to Check |
| --- | --- |
| Insertion position | Must be from `0` to `size` of the destination at the time of the operation. |
| Structural support | The destination must support operations that increase its size. |
| Source reference | Must not be a `null` reference. |
| Element types and values | Must satisfy the destination's rules, including its `null` policy if any. |
| Source modified during operation | Must be avoided or governed by a clearly documented concurrent policy. |

Standard mutable `ArrayList` and `LinkedList` instances support indexed `addAll`. A fixed-size list backed by `Arrays.asList` does not support insertions; unmodifiable lists created by `List.of` or `List.copyOf` do not support them either.

A valid index does not make an unsupported operation valid:

~~~java
List<String> fixed = Arrays.asList("A", "D");

// Position 1 is valid, but the list does not allow changing its size.
fixed.addAll(1, List.of("B", "C")); // UnsupportedOperationException
~~~

Do not try to predict exception precedence when multiple preconditions are violated simultaneously. Separate test cases for index bounds, `null` source, and unsupported destination operations so it is clear which condition is being verified.

### One Method Call Does Not Imply a Transaction

There is no universal guarantee across all `List` implementations that `addAll` validates everything upfront and either inserts all elements atomically or leaves the list untouched upon failure.

Different implementations, specialized collections, or custom sources may fail differently midway through. Do not catch an exception mid-operation and assume by default that the destination was left completely unmodified.

If your requirement is to preserve the original data intact whenever building the result fails, construct a separate result list, validate it, and adopt it only after preparation succeeds completely.

Doing so still does not automatically create a multi-threaded or multi-resource transaction; the scope of any atomicity guarantee must be designed for the actual requirement.

## 11. Producing a Result List Without Modifying the Original

A helper method can clearly express the choice to produce a new result list:

~~~java
// Place this method inside a class; requires importing List, Collection, and ArrayList.
static <T> List<T> withInserted(
        List<? extends T> original,
        int index,
        Collection<? extends T> incoming
) {
    List<T> result = new ArrayList<>(original);
    List<T> batch = new ArrayList<>(incoming);
    result.addAll(index, batch);
    return result;
}
~~~

For example:

~~~java
List<String> original = List.of("A", "D");
List<String> result = withInserted(original, 1, List.of("B", "C"));

System.out.println(result);   // [A, B, C, D]
System.out.println(original); // [A, D]
~~~

This method makes several explicit choices:

- The returned list is a new mutable `ArrayList`.
- It does not modify the structure of `original`.
- It snapshots `incoming` into `batch` before inserting into `result`.
- It applies the standard insertion index rules of `result`.

This is still a shallow copy. The method also does not preserve special invariants of any custom `List` subclass that `original` might belong to, because the return container is chosen to be an `ArrayList`. If an application needs those custom constraints, it must validate them or construct an appropriate target type.

When data is shared across threads, reading `original` and `incoming` to build copies must still follow a consistent concurrency policy for those sources.

## 12. Performance Cost: Why Batch Insertion Can Outperform Repeated Single Insertions

Let `n` be the destination size, `p` the insertion position, and `m` the batch size.

In a typical `ArrayList` implementation, a batch insertion can make room for `m` elements by shifting the tail once and then copying the batch into the opened gap. If the internal array needs to grow, there is also allocation and reallocation copy cost.

A common cost model looks like:

~~~text
Read/prepare m source elements
+ shift n - p tail elements
+ place m elements into the insertion gap
+ expansion cost if capacity growth is needed
~~~

By contrast, inserting elements one by one into the middle may shift the tail repeatedly on every iteration. Even when the final contents match (assuming the insertion index is incremented properly), the total amount of data movement is not necessarily the same.

See the implementation details and specifications of [ArrayList.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#addAll(int,java.util.Collection)) and [LinkedList.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html#addAll(int,java.util.Collection)).

For `LinkedList`, execution relies on traversing to the indexed position and allocating/linking nodes rather than shifting a contiguous tail array. However, locating the position by index still incurs traversal cost.

Do not treat the `List` interface as a guarantee that every `addAll` uses the same algorithm or is always faster than every loop. Consider the concrete implementation, batch size, insertion position, and source preparation cost. For very large sources, snapshotting a batch also has its own memory footprint.

## 13. Complete Program

Save as **IndexedAddAllDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

public class IndexedAddAllDemo {
    public static void main(String[] args) {
        List<String> destination = new ArrayList<>(List.of("A", "D"));
        List<String> incoming = new ArrayList<>(List.of("B", "C"));

        boolean changed = destination.addAll(1, incoming);
        System.out.println("Changed = " + changed);
        System.out.println("Inserted = " + destination);
        System.out.println("Size = " + destination.size());
        System.out.println("Source after insertion = " + incoming);

        incoming.set(0, "source-only");
        System.out.println("Source after set = " + incoming);
        System.out.println("Destination after source set = " + destination);

        boolean emptyChanged = destination.addAll(2, List.of());
        System.out.println("Empty source changed = " + emptyChanged);
        System.out.println("After empty insertion = " + destination);

        destination.addAll(0, List.of("H1", "H2"));
        destination.addAll(destination.size(), List.of("T1", "T2"));
        System.out.println("Head and tail batches = " + destination);

        List<String> empty = new ArrayList<>();
        empty.addAll(0, List.of("first", "second"));
        System.out.println("Empty destination = " + empty);

        List<String> repeated = new ArrayList<>(List.of("A", "D"));
        for (String value : List.of("B", "C")) {
            repeated.add(1, value);
        }
        System.out.println("Repeated same-index add = " + repeated);

        LinkedHashSet<String> orderedSource =
                new LinkedHashSet<>(List.of("C", "B", "C"));
        List<String> fromSet = new ArrayList<>(List.of("A", "D"));
        fromSet.addAll(1, orderedSource);
        System.out.println("Ordered set source = " + fromSet);

        List<String> duplicates = new ArrayList<>(List.of("A", "D"));
        duplicates.addAll(1, List.of("B", "B"));
        System.out.println("Duplicate source elements = " + duplicates);

        List<String> original = List.of("A", "D");
        List<String> result = withInserted(original, 1, List.of("B", "C"));
        System.out.println("Copy result = " + result);
        System.out.println("Original unchanged = " + original);

        List<String> overlap =
                new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> captured = new ArrayList<>(overlap.subList(0, 2));
        overlap.addAll(2, captured);
        System.out.println("Captured overlapping range = " + overlap);

        List<Number> numbers = new ArrayList<>(List.of(0.5, 1.5));
        List<Integer> integers = List.of(10, 20);
        numbers.addAll(1, integers);
        System.out.println("Subtype source = " + numbers);

        List<String> validTarget = new ArrayList<>(List.of("A", "D"));
        expect("Negative index", IndexOutOfBoundsException.class,
                () -> validTarget.addAll(-1, List.of("B")));
        expect("Index beyond size", IndexOutOfBoundsException.class,
                () -> validTarget.addAll(3, List.of("B")));
        expect("Null source", NullPointerException.class,
                () -> validTarget.addAll(1, null));

        List<String> fixed = Arrays.asList("A", "D");
        expect("Fixed-size destination", UnsupportedOperationException.class,
                () -> fixed.addAll(1, List.of("B", "C")));
    }

    private static <T> List<T> withInserted(
            List<? extends T> original,
            int index,
            Collection<? extends T> incoming
    ) {
        List<T> result = new ArrayList<>(original);
        List<T> batch = new ArrayList<>(incoming);
        result.addAll(index, batch);
        return result;
    }

    private static void expect(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable operation
    ) {
        try {
            operation.run();
            throw new AssertionError("Expected " + expected.getSimpleName());
        } catch (RuntimeException exception) {
            if (!expected.isInstance(exception)) {
                throw exception;
            }
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 IndexedAddAllDemo.java
java IndexedAddAllDemo
~~~

Stdout:

~~~text
Changed = true
Inserted = [A, B, C, D]
Size = 4
Source after insertion = [B, C]
Source after set = [source-only, C]
Destination after source set = [A, B, C, D]
Empty source changed = false
After empty insertion = [A, B, C, D]
Head and tail batches = [H1, H2, A, B, C, D, T1, T2]
Empty destination = [first, second]
Repeated same-index add = [A, C, B, D]
Ordered set source = [A, C, B, D]
Duplicate source elements = [A, B, B, D]
Copy result = [A, B, C, D]
Original unchanged = [A, D]
Captured overlapping range = [A, B, A, B, C, D]
Subtype source = [0.5, 10, 20, 1.5]
Negative index -> IndexOutOfBoundsException
Index beyond size -> IndexOutOfBoundsException
Null source -> NullPointerException
Fixed-size destination -> UnsupportedOperationException
~~~

The `expect` helper catches only the specific exception type being verified. If it catches a different `RuntimeException`, it rethrows it so the test case is not falsely recorded as passing; if no exception is thrown as expected, it throws an `AssertionError`.

The program does not test the undefined behavior of self-`addAll` or modifying the source while `addAll` is running. For overlapping data, it snapshots the batch first.

## 14. Explaining the Output

**Changed, Inserted, and Size**

Inserting `B, C` at position `1` of `[A, D]` produces `[A, B, C, D]` with size `4`. The boolean `true` indicates that the destination changed, not that exactly one element was added.

**Source after insertion**

The source remains `[B, C]`. `addAll` does not remove or transfer elements out of the source collection.

**Source after set**

Replacing the first slot of the source with `source-only` does not turn the corresponding slot of the destination into `source-only`. The destination is not a dynamically linked view over the source.

**Empty source**

No new elements are provided to insert; `ArrayList` returns `false` and the contents remain `[A, B, C, D]`. The program does not infer anything about old iterators from this return value.

**Head and tail**

The batch `H1, H2` is inserted at the front, while `T1, T2` is appended at the end. The internal order of each batch is preserved.

**Repeated same-index add**

Inserting `B` and then `C` always at index `1` puts `C` before `B`. It is not equivalent to calling `addAll` at index `1` with source `[B, C]`.

**Ordered set source**

The `LinkedHashSet` source yields `C` then `B`, so the inserted batch has the order `C` then `B`. The destination does not sort automatically.

**Duplicate source elements**

Both `B` elements appear in the destination `List`. There is no automatic deduplication when inserting into this `ArrayList`.

**Copy result**

The helper method produces `[A, B, C, D]` while `original` remains `[A, D]`, because the insertion happens on the new `result` list.

**Captured overlapping range**

`A, B` is captured from a slice of the destination before insertion. The result `[A, B, A, B, C, D]` does not rely on a source mutating while being read during insertion.

**Subtype source**

The `Integer` values `10` and `20` are added into a `List<Number>` between two `Double` values. The source wildcard permits this subtype relationship without casting the collection.

**Error cases**

Negative indices and indices greater than `size` are rejected; a `null` source is rejected; a fixed-size destination cannot insert a batch. Each case is isolated so the exact condition under test is clear.

## 15. Testing and Common Pitfalls

Verify a batch insertion by checking three parts:

1. The prefix before the insertion position remains unchanged.
2. The batch appears in the exact iteration order and multiplicity of the source.
3. The old suffix keeps its relative order and starts right after the batch.

Additionally, verify the new size, the boolean return value, and whether you intended to mutate the original list in place or produce a new list.

Important test cases:

- Empty destination and non-empty source.
- Empty source at a valid index.
- Insertion at the head, middle, and tail.
- Source with one element, multiple elements, and duplicate elements.
- Source whose order differs from natural order.
- Indices `-1`, `size()`, and `size() + 1`.
- A `null` source reference versus a source containing `null` elements.
- Fixed-size or unmodifiable destination lists.
- Overlapping source range captured into a separate collection before use.
- Source using a subtype of the destination element type.

| Misconception | Correct Understanding |
| --- | --- |
| `addAll` overwrites elements at the insertion position | It makes room and shifts the tail to the right. |
| `addAll` returns the count of added elements | It returns a boolean indicating whether the destination changed. |
| The source must be a `List` | Any compatible `Collection` can be used; element order follows the source's iteration order. |
| Because the destination is an `ArrayList`, the batch is automatically sorted | No automatic sorting takes place. |
| Repeatedly inserting at the same index preserves source order | Each call inserts in front of the current element at that index, reversing the batch order. |
| An empty source is the same as `null` | They are two completely different states. |
| The source is consumed or dynamically linked into the destination | For independent collections, the source retains its elements and the destination does not become a live view of the source's slots. |
| `addAll` deep-copies every object | Object elements still share references between source and destination. |
| Self-insertion or overlapping views are always guaranteed to work | Avoid relying on a source being modified during execution; snapshot the batch first when appropriate. |
| A single call guarantees all-or-nothing transactional behavior on failure | There is no universal transactional guarantee across all `List` implementations and sources. |

## 16. Exercises

1. Starting from `[A, F]`, insert `[B, C, D, E]` at the appropriate position. Write down the index of `F` before and after the operation.
2. Predict the result when the source is `[C, B]` versus when the source is a `LinkedHashSet` created from `[C, B, C]`.
3. Write an element-by-element `add` loop that produces the same content as `addAll`, then demonstrate the bug that occurs when the insertion index is not incremented.
4. Write a method that inserts a batch while leaving `original` untouched. Verify the returned list, `original`, and the fact that mutable object elements may still be shared by reference.
5. Snapshot a prefix slice of a list and insert that snapshot into the middle of the same list. Explain why snapshotting beforehand is important.
6. Test an empty source, a `null` source, insertion at `size`, and insertion at `size + 1` on a mutable `ArrayList`.
7. For a data import task, identify where the batch order comes from, whether the source could be mutated while being read, and what invariants need to be checked before using the result.

A batch insertion combines a destination, a position, and a source order. Once those three factors are clear, you can derive the entire result using the prefix – batch – suffix model, and then evaluate mutability, shared data, and implementation cost separately.
