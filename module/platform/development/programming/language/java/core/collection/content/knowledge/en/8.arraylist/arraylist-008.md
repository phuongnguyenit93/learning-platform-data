# When Is ArrayList the Right Choice?

`ArrayList` is often a good starting point for an ordered, resizable sequence of data built primarily by appending to the end and then reading or iterating over it multiple times. However, it is not the default choice for every dataset just because it has an `add` method.

To choose properly, you need to answer two groups of questions: **what meaning the data must preserve** and **how the program will manipulate the data**. Preserving order, keeping duplicate records, accessing by index, looking up by key, removing from the head of a queue, and concurrent modification are distinct requirements.

This article explains how to evaluate those needs, describes the mechanisms that make `ArrayList` suitable or unsuitable, and applies them to a complete Java 17 example.

## 1. First, Determine Whether You Really Need a List

A `List` models a sequence of elements with positions. For example:

~~~text
index:      0       1       2       3
data:      Lan:8   Lan:8   An:9    Ha:7
~~~

The two `Lan:8` entries may represent two separate recorded events that both need to be retained. Position also carries meaning: unless reordered, the sequence reflects the order in which the program added the data.

An `ArrayList`:

- Preserves the order of elements in the list.
- Allows multiple elements that are equal according to `equals`.
- Allows reading or replacing an element at a given index.
- Allows growing and shrinking the number of elements.
- Allows `null`, even though an application may actively prohibit `null`.

These characteristics differ from "a set of unique elements" or "a key-based lookup table".

### 1.1. Preserving Order Does Not Mean Automatic Sorting

If you add B, A, C, the list is `[B, A, C]`; it does not automatically become `[A, B, C]`. To order elements by name, score, or timestamp, you must perform an explicit sorting step.

After inserting in the middle or removing elements, subsequent indices can change. Therefore, an index is the current position in the sequence and should not be used as a substitute for a record's persistent identifier.

### 1.2. Allowing Duplicates May Be a Requirement, Not a Bug

In transaction histories, sensor readings, invoice line items, or registration logs, two equal values are not necessarily redundant data to be discarded. Switching to a `Set` merely for "faster lookup" can lose information about occurrence counts.

Conversely, if the core requirement is "each code appears at most once", using a list and calling `contains` before every `add` both obscures the rule and introduces repeated linear searches. Uniqueness should be defined directly in the data model.

### 1.3. Positional Access Differs from Key Lookup

`scores.get(200)` retrieves the element currently at position 200. It does not search for a person with ID 200.

If the frequent question is "which object has code X?", a structure mapping keys to objects usually expresses the intent much more clearly. A sequence for presentation and an index for lookup can coexist if the application genuinely needs both; in that case, consistency between them must be managed.

## 2. Why Does the Array Mechanism Make ArrayList Suitable for Certain Operations?

`ArrayList` implements `List` using an array that can be replaced by a larger array when necessary. The slots of the backing array hold references to elements.

A simple model:

~~~text
size = 4, capacity = 6

array index:    0     1     2     3     4     5
               [A]   [B]   [C]   [D]   [ ]   [ ]
               <--- existing elems --> <reserve>
~~~

**Size** is the number of elements actually present. **Capacity** is the number of slots the backing array can hold. Capacity is not the number of elements that have been created.

The [Java SE 17 ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) documentation describes index-based access operations as running in constant time and appending to the end as running in amortized constant time; other operations should be evaluated based on their specific access patterns.

### 2.1. Reading an Index Does Not Require Traversing Preceding Elements

To retrieve the element at `i`, the structure accesses the corresponding array slot directly. `get(i)` and `set(i, value)` have O(1) cost for a valid index.

This is why `ArrayList` is useful when an algorithm needs to access many non-contiguous positions, process index ranges, read a selected row, or look up preloaded elements.

O(1) here describes the work of accessing the list itself. If the application subsequently parses a document, makes a network call, or processes a complex object, the overall application work includes those additional costs.

### 2.2. Appending to the End Fits Accumulating Results

When the array still has free space, appending to the end mainly writes a reference and increments the size. When it is full, a larger array must be allocated and the old references copied over.

Because array growth happens in bursts, that cost is spread across a sequence of appends: amortized O(1) per operation. A single append can still take O(n) when resizing occurs.

Therefore, the pattern "read each record, and if valid, append it to the result" is typically a good fit. However, if there is an extremely strict latency bound on every individual write, the word "amortized" alone is not enough to prove the deadline is met.

### 2.3. Single-Pass Iteration Fits Data Gathered in Memory

Iterating over `n` elements has an iteration management cost of O(n), plus the work performed for each element. The array of references is laid out in contiguous slots, avoiding the need to allocate a separate node object for every position as in a linked list model.

You should not infer that the element objects themselves are laid out contiguously in memory, or that `ArrayList` always beats every other structure in every benchmark. It stores references; how objects are allocated and how the JVM manages memory still affect performance.

### 2.4. Inserting or Removing at the Beginning or Middle Must Preserve Order

If there are `n` elements and you insert at `i`, the tail of length `n - i` must be shifted to make room. Removing at `i` must shift `n - i - 1` subsequent elements down.

Pre-sizing capacity can avoid array reallocations, but it does not eliminate the work of shifting the tail. This is an important limitation when the primary access pattern involves continuous modifications at the front or middle of a large list.

## 3. Common Situations Where ArrayList Is a Good Fit

| Situation | Why ArrayList Makes Sense | Additional Conditions to Consider |
|---|---|---|
| Collecting valid records from a finite source | Appends to the end, preserves order and occurrence count | The entire result must fit within the memory budget |
| Building a result list for display | Ordered, positional access | Must define who is allowed to mutate the list |
| Loading a batch for processing or sorting | Easy to iterate, access, and update by index | Account for sorting time and copy creation |
| Holding a working list inside a single method | Clear ownership, no cross-thread write coordination needed | Do not let internal references escape unintentionally |
| Needing a mutable copy of a collection | Collection-accepting constructor creates an independent list structure | Element objects themselves may still be shared |
| Moderate growth/shrinkage where mid-list edits do not dominate | Simple code that fits many common operations | Measure under realistic load if edits become a bottleneck |

### 3.1. Result List of a Filtering Operation

Given a source of `m` records where those meeting a condition must be kept, using a result `ArrayList` and appending each kept record to the end helps:

- Preserve the source order.
- Retain all occurrences when deduplication is not desired.
- Leave the input list unmodified.
- Avoid repeatedly removing elements from the middle of the source just to produce a new output.

The cost of the filtering loop is O(m) plus the condition evaluation cost; the result memory depends on the number of retained records. If you only need a sum or a count, you may not need to store the result list at all.

### 3.2. Data Built Once and Read Many Times

An application can use an `ArrayList` during the construction phase and then publish a structurally unmodifiable list. This cleanly separates the mutation phase from the consumption phase.

This does not require the final returned object to have the concrete implementation class `ArrayList`. For instance, `List.copyOf` may create a different internal representation. Design around the contract you need to provide rather than forcing callers to know the internal class.

### 3.3. Replacing Values at Existing Positions

If the requirement is updating the element at `i` without adding or removing positions, `set(i, value)` does not shift the tail. A working list with frequent index-based reads and replacements fits `ArrayList` well.

However, if you must search for the right record by an ID before every replacement, that search step can still be linear. You must analyze both locating the position and performing the update, not just `set` in isolation.

### 3.4. Occasional Mid-List Modifications May Still Be Acceptable

A list of 30 elements that a user occasionally reorders does not necessarily require a complex data structure just because mid-list insertion is O(n). The actual element count and operation frequency determine whether that cost matters.

This example illustrates how to reason about trade-offs; it does not establish a hard rule like "under 30 elements, always use ArrayList". No universal threshold replaces requirements, runtime environment, and measurement.

## 4. Requirements That Should Prompt Considering Other Structures

### 4.1. Queues: Continuous Appending to the End and Polling/Removing from the Front

If you repeatedly call `add(value)` followed by `remove(0)`, every removal from the front of an `ArrayList` must shift all remaining elements.

Draining `n` elements by removing from the front shifts a total number of references equal to:

~~~text
(n - 1) + (n - 2) + ... + 1 + 0 = n(n - 1)/2
~~~

A queue is typically better modeled with the `Queue` or `Deque` interface. `ArrayDeque` supports operations at both ends with most operations running in amortized constant time; it does not provide `get(i)` and does not allow `null` elements. See [Java 17 ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

The choice must reflect both the data and the operations: do not replace a list with a deque if the application genuinely requires arbitrary index access and has no better alternative design.

### 4.2. Very Frequent Membership Checks

`ArrayList.contains` may have to compare against many elements. Calling it for every element of another large collection can cause the number of comparisons to grow proportionally to the product of the two sizes.

If you need uniqueness and membership testing, consider `HashSet`. Its basic operations offer constant-time performance when the hash function distributes elements well; this set does not guarantee iteration order. That is a property of hash-based structures, not an absolute O(1) guarantee for every hash function and dataset, as noted in [Java 17 HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

If the list is small, checks are infrequent, or duplicates must be preserved, the overhead of creating and maintaining an auxiliary set may be unnecessary. Evaluate actual needs rather than habitually replacing every `contains` call with another structure.

### 4.3. Looking Up Objects by Key

If the primary operation is "find customer by ID", a `Map<Id, Customer>` usually expresses the requirement more directly than a `List<Customer>` scanned linearly.

`HashMap` provides efficient `get` and `put` operations when the hash function distributes keys well, and it makes no guarantee about iteration order, as stated in [Java 17 HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

You must define the rule when two records share the same key. Using a map may overwrite an existing value with a new one; that is a data modeling decision, not merely a time optimization.

### 4.4. Frequent Mid-List Insertions/Removals When Already Positioned at an Iterator

A linked list can be advantageous in certain operation sequences when an iterator is already positioned at the target location. However, switching to `LinkedList` while still calling `get(i)`, `add(i, x)`, and `remove(i)` does not automatically make those operations O(1): the list still has to traverse to the corresponding node.

The [Java 17 LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) documentation notes that index-based operations traverse from either the beginning or the end, whichever is closer. Therefore, you must account for finding the position, not just updating node links.

If mid-list modifications can be batched or expressed as building a new result list in a single pass, changing the algorithm can be more effective than changing the data structure.

### 4.5. Fixed Size or Very Large Primitive Datasets

When the size is fixed, when interoperating with APIs that expect arrays, or when storing integers in an `int[]`, an array may be more appropriate.

`ArrayList<Integer>` holds `Integer` references, not an auto-growing primitive `int` buffer. Boxing, object headers, and reference overhead can be substantial for large numeric datasets. Primitive arrays avoid that representation overhead, at the cost of managing logical size manually or accepting a fixed length.

Do not apply a single fixed byte formula across all JVMs to compare memory usage; reference compression, object headers, and alignment can vary.

### 4.6. Data Without a Practical In-Memory Bound

`ArrayList` keeps its elements in memory. It is not a mechanism that automatically pages data from disk, a database, or the network.

If a data source is huge or an unbounded stream, consider processing it incrementally, in batches, as a stream, or via external storage. Calling a collection "dynamic" does not mean it has infinite capacity.

Similarly, you can use a list for a single loaded page of results, but displaying one page should not require loading millions of records into a list just to slice a page in memory.

### 4.7. Concurrent Modification by Multiple Threads

`ArrayList` is not thread-safe. Multiple threads writing to the same list, or mixing reads and writes concurrently, require proper synchronization design; never treat "I haven't seen a ConcurrentModificationException yet" as proof of thread safety.

A list confined to a single thread, or built completely and then shared for read-only access via safe publication, has very different requirements from a list modified concurrently by multiple threads.

Synchronized wrappers, defensive copies, ownership partitioning, or concurrent collections are options depending on the access pattern. No capacity-preallocation method or type keyword automatically solves concurrency on its own.

## 5. Step-by-Step Decision Process

Instead of starting with "Is ArrayList or LinkedList faster?", walk through these questions in order:

1. **Is the data an ordered sequence with meaningful positions?** If not, reconsider whether you need a `List` at all.
2. **Must duplicate elements be preserved?** If yes, do not replace it with a set just to speed up one operation.
3. **What are the dominant operations?** Appending to the end, iterating, and reading by index favor `ArrayList`; continuous front removal or key-based lookup suggest other models.
4. **Does the result fit in memory, and how long does it live?** Account for spare capacity, element objects, and any coexisting copies.
5. **Who is allowed to mutate it, and how many threads access it?** Choose the handoff and synchronization strategy right in the contract.
6. **Is there evidence that this part is a bottleneck?** If optimization is needed, measure under meaningful load and verify both correctness and cost.

The answers may lead to using `ArrayList` internally while exposing a different public type externally. "Choosing a structure to build data" and "granting mutation rights to consumers of that data" are related but distinct decisions.

## 6. Declaring List, Using ArrayList, and Designing Mutation Rights

### 6.1. The Interface Does Not Automatically Dictate Mutability

An illustrative method body snippet:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
~~~

The variable has type `List`, but the actual object is an `ArrayList`, so adding elements is supported.

Using `List` where only the list contract is needed reduces coupling to a concrete implementation class. However, a method accepting a `List` must not assume that every passed list supports adding, removing, or replacing elements: read-only lists and fixed-size lists exist.

If a method needs to mutate its input, it must state that requirement clearly or create its own working copy. Never silently sort a list that the caller expects to remain unchanged.

### 6.2. When You Specifically Need ArrayList's Own API

`ensureCapacity` and `trimToSize` are not part of the `List` interface. If a data-building routine needs to call them, the local variable can be typed as `ArrayList`:

~~~java
ArrayList<String> building = new ArrayList<>(expectedCount);
building.ensureCapacity(nextExpectedTotal);
~~~

This is an illustrative snippet assuming validated count variables. Pre-allocating capacity does not increase the list's logical size and does not allow calling `get` on indices that have not been added yet.

Do not cast an arbitrary `List` to `ArrayList` merely hoping the underlying object is an `ArrayList`. A public contract returning `List` is free to change its concrete implementation while still fulfilling the contract.

### 6.3. Mutable Copies, Unmodifiable Views, and Immutable Snapshots Are Not the Same

| Creation Method | Structural Mutation Allowed via Returned Reference? | Reflects Subsequent Structural Changes to the Source? |
|---|---|---|
| `new ArrayList<>(source)` | Yes | No, independent list structure |
| `Collections.unmodifiableList(source)` | No | Yes, this is a view backed by the source |
| `List.copyOf(source)` | No | Does not reflect updates to the source after creation |

`List.copyOf` rejects `null` elements and does not guarantee a specific implementation class. It may reuse a suitable unmodifiable list; do not assume every call allocates a brand-new `ArrayList`. See [Java 17 List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

An unmodifiable view retains a reference to the backing source, per [Java 17 Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)). If the source continues to be modified elsewhere, holders of the view can observe the data changing.

None of the above methods automatically perform a deep copy of each element object. If elements are mutable, a list that forbids adding or removing can still contain objects whose internal state is mutated through other references. Achieving completely stable values requires designing the elements themselves and how they are shared.

### 6.4. Not Every List Factory Can Replace a Working ArrayList

`List.of(...)` produces an unmodifiable list. `Arrays.asList(array)` creates a fixed-size list backed directly by the array: you can replace elements via `set`, but you cannot add or remove positions like an independent `ArrayList`. See [Java 17 Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Therefore, if you need to keep adding or removing elements after receiving such a source, you can create `new ArrayList<>(source)`. The reason for choosing `ArrayList` here is structural mutability and ownership, not just algorithmic complexity.

## 7. Complete Example: Collecting Data, Positional Access, Sorting, and Handing Off Results

Assumed requirements:

- The input is a finite batch of scores.
- Discard records with negative scores.
- Preserve all occurrences; two `Lan:8` records are both meaningful.
- Maintain a working list for index-based reading and sorting.
- Once the result is prepared, create an unmodifiable snapshot for handoff.
- Leave the input list unmodified.

`ArrayList` fits the working phase: building by appending to the end, iterating, index access, and sorting. The handoff phase has its own contract and uses `List.copyOf`.

### 7.1. Source Code

Save as `ArrayListChoiceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class ArrayListChoiceDemo {
    record Score(String name, int points) {
        Score {
            Objects.requireNonNull(name, "name");
        }

        @Override
        public String toString() {
            return name + ":" + points;
        }
    }

    static List<Score> collectValidScores(List<Score> input) {
        Objects.requireNonNull(input, "input");
        List<Score> result = new ArrayList<>();
        for (Score score : input) {
            Objects.requireNonNull(score, "score");
            if (score.points() >= 0) {
                result.add(score);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<Score> input = List.of(
                new Score("Lan", 8),
                new Score("Minh", -1),
                new Score("Lan", 8),
                new Score("An", 9),
                new Score("Ha", 7));

        List<Score> working = collectValidScores(input);
        System.out.println("accepted: " + working);
        System.out.println("duplicate Lan:8 count: "
                + Collections.frequency(working, new Score("Lan", 8)));
        System.out.println("get(2): " + working.get(2));
        long total = 0;
        for (Score score : working) {
            total += score.points();
        }
        System.out.println("total: " + total);

        working.sort(Comparator.comparingInt(Score::points)
                .reversed().thenComparing(Score::name));
        System.out.println("sorted: " + working);
        List<Score> snapshot = List.copyOf(working);
        List<Score> view = Collections.unmodifiableList(working);

        working.add(new Score("Binh", 6));
        System.out.printf("after append: working=%d, snapshot=%d, view=%d%n",
                working.size(), snapshot.size(), view.size());
        System.out.println("snapshot: " + snapshot);
        try {
            snapshot.add(new Score("Chi", 10));
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot.add: UnsupportedOperationException");
        }

        List<Score> mutableCopy = new ArrayList<>(snapshot);
        mutableCopy.set(0, new Score("An", 10));
        System.out.println("mutable copy: " + mutableCopy);
        System.out.println("snapshot after copy.set: " + snapshot);
        System.out.println("input unchanged: " + input);

        List<String> nullable = new ArrayList<>();
        nullable.add(null);
        System.out.println("ArrayList accepts null: " + nullable);
        try {
            List.copyOf(nullable);
        } catch (NullPointerException exception) {
            System.out.println("List.copyOf null: NullPointerException");
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListChoiceDemo.java
java ArrayListChoiceDemo
~~~

### 7.2. Standard Output

~~~text
accepted: [Lan:8, Lan:8, An:9, Ha:7]
duplicate Lan:8 count: 2
get(2): An:9
total: 32
sorted: [An:9, Lan:8, Lan:8, Ha:7]
after append: working=5, snapshot=4, view=5
snapshot: [An:9, Lan:8, Lan:8, Ha:7]
snapshot.add: UnsupportedOperationException
mutable copy: [An:10, Lan:8, Lan:8, Ha:7]
snapshot after copy.set: [An:9, Lan:8, Lan:8, Ha:7]
input unchanged: [Lan:8, Minh:-1, Lan:8, An:9, Ha:7]
ArrayList accepts null: [null]
List.copyOf null: NullPointerException
~~~

### 7.3. What Does Each Output Line Demonstrate?

`accepted` preserves the order of valid records from the input. Both `Lan:8` records remain, and `Collections.frequency` returns 2. This satisfies the requirement to preserve occurrence counts.

`get(2)` retrieves `An:9` by position prior to sorting. It does not search by name. The total score of 32 is computed in a single iteration pass.

The `sort` step actively reorders the list in descending order of points, breaking ties by name. The list does not automatically maintain this order simply because it uses `ArrayList`. The comparator operates on the fields of `Score`, not on its `toString` display representation.

After appending Binh to `working`, the sizes of `working` and `view` both become 5, whereas `snapshot` remains 4. This is the observable difference between an unmodifiable view and an independent snapshot.

`snapshot.add` is rejected. Creating `new ArrayList<>(snapshot)` restores mutability on the new copy; calling `set` on the copy replaces the reference at index 0 without altering `snapshot`.

`Score` in this example has two components, `String` and `int`, with no mutable nested collections. Replacing an element with `new Score(...)` is different from mutating the internal state of a mutable element object. Do not generalize that every `record` is deeply immutable just because it is a record.

The input list remains unchanged because the filtering helper creates a separate list. The fact that `input` was created with `List.of` also highlights that receiving a `List` does not guarantee you can mutate it in place.

Finally, `ArrayList` accepts `null`, whereas converting a list containing `null` via `List.copyOf` is rejected. Data policies must be consistent across boundaries, not just valid inside the working structure.

### 7.4. Why Does collectValidScores Return List?

The code in the example needs a mutable result list so it can subsequently sort it; the helper builds it using `ArrayList` and returns it typed as `List`. Mutability here comes from the helper's contract and implementation within the program, not from the interface name.

In a real API, clearly document whether the returned list is mutable or read-only, whether it is independent of the source, and whether it allows `null`. Callers should never have to guess by trying `add` and catching an exception.

This example mutates data within a single thread only. It does not demonstrate concurrent multi-threaded write behavior, nor is it a performance benchmark comparing collection types.

## 8. Cost Analysis of the Complete Example

Let `m` be the number of input records and `n` be the number of retained records, with `n <= m`.

### 8.1. Filtering Phase

Each record is inspected once. With a constant-time score check, the filtering loop performs O(m) total work; appending to the result contributes amortized O(n) work, which falls within O(m).

The result list holds `n` references plus any spare capacity. It does not re-instantiate `Score` objects on every append: the retained elements are references to the matching input objects.

If a list were not needed and only the total score mattered, you could accumulate the sum during iteration and avoid storing the result. However, the example also needs positional access and sorting, so keeping a sequence is justified.

### 8.2. Access and Aggregation Phase

A single `get(2)` is O(1) on the actual structure in use. Computing the sum once is O(n).

If you called a sum-computing method that re-traversed the list for every element, the overall design cost could rise to O(n²), even though each individual `get` remained O(1). Choosing the right data structure does not automatically fix an algorithm that repeats unnecessary work.

### 8.3. Sorting Phase

Sorting a list requires comparing elements and moving references; it cannot be treated as O(1) just because `sort` is a single line of code.

With a constant-time comparator and Java's general-purpose object sorting algorithm, complexity analysis uses O(n log n) for the general case. Partially ordered data or specific input distributions can change the actual amount of work performed.

In this example, comparing names also depends on string lengths; treating each comparison as O(1) is an assumption made when separating list size from name length. When a comparator performs expensive computations, both the number of comparisons and the cost per comparison matter. Do not attribute all execution time solely to the collection. See the default sorting algorithm description in [Java 17 List.sort](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

### 8.4. Copying Phase and Memory Lifecycle

When creating a snapshot from a mutable working list, you must account for the work of preserving `n` elements and the memory footprint of the resulting representation. In the example, `input`, `working`, `snapshot`, and `mutableCopy` coexist at the same time.

These lists share the `Score` objects while maintaining their own internal storage arrays. Thus, "copying `n` references" and "copying `n` domain objects" are two very different memory models.

Do not create a new snapshot after every single append just because you want "data to always be immutable"; doing so can dramatically increase total copying overhead. Choose handoff boundaries that match your actual requirements.

## 9. Practical Decisions for Using ArrayList Effectively

### 9.1. Pre-Size Capacity When You Have a Reliable Estimate

If you know you will retain roughly `k` elements and `k` is reasonable for memory, `new ArrayList<>(k)` can reduce array reallocations. If you only know that the input size is huge while the retention rate is tiny, pre-allocating for the entire input size may waste memory.

In the filtering example, using the default constructor avoids assuming every input record is valid. That choice keeps the illustration simple; it is not a rule forbidding filter routines from ever pre-sizing capacity.

Pre-sizing capacity does not create elements, does not guarantee sufficient memory for arbitrary `k`, and does not make front insertion constant-time.

### 9.2. Keep Ownership Clear

An internal list can be mutated freely during its construction phase as long as it is not unintentionally shared. When exposing it externally, decide whether the recipient is allowed to mutate it and whether changes should propagate back to the source.

Returning an internal `ArrayList` directly can allow callers to violate invariants maintained by the owning class. Returning an unmodifiable view, on the other hand, allows callers to observe future changes made by the owner. Choose based on data semantics, not just the name of a wrapper method.

### 9.3. Retain Only Necessary Data

A long-lived list keeps strong references to all elements still inside it. If data is only needed for the scope of a single request, do not store it in an application-wide field just to reuse capacity.

If reusing a large list is necessary, carefully evaluate its lifecycle, retained memory, and thread-safety requirements. Reuse can be beneficial or harmful depending on the workload pattern.

### 9.4. Prefer Batch Algorithms When Possible

Multiple mid-list insertions can often be grouped into `addAll`. Multiple removals can be expressed as range removal, filtering, or building a new result list in one pass, rather than shifting the same tail repeatedly.

Such transformations are valid only when they preserve the required order, occurrence counts, ownership, and the point in time at which other components observe the result. Optimizations must never break the data contract.

### 9.5. Measure the Right Question When Performance Truly Matters

A meaningful comparison must clearly specify:

- Data size and distribution.
- Ratios of reads, appends, insertions/removals, and searches.
- Whether construction, element allocation, sorting, and copying are included.
- Whether memory footprint and resize latency spikes are measured.
- Whether lists are freshly allocated or reused across iterations.

A single stopwatch run on a busy machine or a single-loop test is not enough to declare one structure universally faster. The JVM must be evaluated with warm-up, JIT compilation, optimizations, and garbage collection in mind; element processing time can easily dwarf list operation time.

You do not need to benchmark every small list. Use contracts and complexity analysis to make a sensible initial choice, then measure when you have concrete performance goals or evidence of a bottleneck.

## 10. Common Misconceptions to Avoid

| Misconception | Accurate View |
|---|---|
| Every collection can be replaced by ArrayList | Semantics for ordering, duplicates, keys, and mutability differ |
| List means a read-only list | List is an interface; mutability depends on the backing object and contract |
| ArrayList sorts elements automatically | It preserves current sequence order; sorting is an explicit step |
| ArrayList<Integer> is equivalent to an auto-growing int[] | It involves reference representation and boxing overhead |
| contains is fast because get is fast | contains may have to scan and compare many elements |
| Spare capacity makes mid-list insertion O(1) | The tail slice still has to be shifted |
| Amortized O(1) append means no allocation ever happens | It is amortized O(1); occasional array growth still occurs |
| ArrayList is always best for small or read-heavy data | That is an operation-based heuristic, not an absolute law |
| Switching to LinkedList makes every mid-list insert/remove O(1) | Traversing to the target position must still be counted |
| Wrapping with unmodifiableList creates an independent snapshot | It creates a live view backed by the source |
| copyOf makes contained element objects deeply immutable | It does not deep-copy element objects |
| No exception observed means concurrent multi-threaded use is safe | Proper synchronization and safe publication rules are required |
| Dynamic means it can hold an unlimited amount of data | Memory and runtime environment limits are still finite |

## 11. Self-Check Scenarios

### Scenario 1: Single Page of Search Results

An application receives at most 50 records for a single page, needs to preserve the order returned by the source, and reads a record by position when the user selects a row.

**Assessment:** `ArrayList` is a suitable candidate for the page's data. You still need to decide whether the list can be mutated after being returned. Do not infer that the entire database must be loaded into a list to perform pagination.

### Scenario 2: Work Queue

A program continuously appends items to the end and polls/removes items from the front of a large list.

**Assessment:** This is a clear signal to consider a `Queue`/`Deque` model instead of paying the array-shifting cost on every front removal. If multiple threads are involved, you must also choose appropriate concurrency coordination; a standard deque does not automatically handle concurrent access.

### Scenario 3: Product Catalog by Code

There are 100,000 products, and the most frequent operation is looking up a product by its unique code.

**Assessment:** A key-based map fits the primary access pattern. If an ordered display list is also needed, a separate representation can be maintained, provided update timing and consistency are defined. Never use a list index as a substitute for a product code.

### Scenario 4: Duplicate Sensor Readings

Two measurements have the exact same value but occurred at two different recording times; the report must keep both and preserve recording order.

**Assessment:** `List` and `ArrayList` fit those semantics well. Converting to a set just to reduce element count would discard information that the requirement mandates keeping.

### Scenario 5: Unmodifiable Result Handoff

A method uses `ArrayList` to build a result, and then wants to ensure callers cannot add, remove, or replace elements in the returned list and cannot observe any subsequent additions made by the builder.

**Assessment:** Consider `List.copyOf` if the data policy forbids `null`. If the elements themselves are mutable, you must also address element stability; an unmodifiable list does not automatically make the entire object graph immutable.

### Scenario 6: Only a Sum Is Needed

A source has a huge number of records, and the program only needs to compute a single sum without reading individual records again afterward.

**Assessment:** Accumulate the sum on the fly during iteration without storing the entire source in an `ArrayList`. Re-evaluating whether data needs to be retained at all often yields a much bigger win than choosing between two list implementations.

### Scenario 7: Frequent Index-Based Updates

A list is already loaded, and subsequent operations frequently read and replace elements at known indices with very few insertions or removals.

**Assessment:** This access pattern favors `ArrayList`. Make sure indices remain valid after any structural modifications, and do not allow multiple threads to mutate the list concurrently without synchronization.

A well-founded decision to choose `ArrayList` is one that can explain **the meaning of the sequence**, **the dominant operations**, **the memory constraints**, and **the data mutation rights**. When those conditions align, this structure provides a simple, readable implementation with a clear cost model.
