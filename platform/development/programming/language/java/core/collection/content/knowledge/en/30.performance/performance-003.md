# Spare Capacity, Linked Nodes, and Per-Element Memory

## 1. Why Does the Same Element Count Take Different Memory?

A collection does not consist solely of the data that the user puts into it. It also needs structures to hold references, locate elements, and perform insertion and removal operations. Two lists holding the same 100,000 objects can differ significantly in byte count and in the number of auxiliary objects.

To interpret memory cost accurately, separate three layers:

1. **The collection object**: fields such as the element count, a reference to the backing array, or references to the head/tail nodes.
2. **The storage structure**: reference arrays, spare slots, linked nodes, or bucket tables.
3. **The data objects**: the referenced objects themselves, including objects deeper in the data graph.

This article moves from array capacity to node overhead, and then builds a method for calculating and measuring per-element memory. The goal is to explain where the memory resides, rather than memorizing a fixed byte number for every JVM.

## 2. `size`, Capacity, and Spare Slots

For an array-backed list, let:

- `n = size()`: the number of elements currently belonging to the list.
- `c`: the capacity, i.e., the number of slots in the backing array.
- `c - n`: the number of unused spare slots.
- `n / c`: the capacity utilization ratio, when `c > 0`.

For example, with `n = 100,000` and `c = 150,000`: there are 50,000 spare slots; the spare portion equals 50% of the active element count, but only about 33.3% of the total capacity. Because these two ratios have different denominators, they must not be used interchangeably.

A slot in an `Object[]` holds a **reference**, not the entire object. An unused slot typically contains `null`; it still occupies space in the array, but that does not mean a data object has been pre-created. Pre-sizing capacity to one million slots does not pre-allocate one million `String`, `Integer`, or domain objects.

Illustrative diagram (not representing actual memory addresses):

```text
ArrayList
  |
  +--> Object[]: [ref A][ref B][ref A][null][null]
                    |      |      |
                    +------|------+--> object A
                           +---------> object B

size = 3; capacity = 5; distinct data objects = 2
```

When the same reference appears multiple times, it increases the element count and the number of used slots, but does not duplicate the data object.

## 3. `ArrayList`: Trading Spare Capacity for Fewer Allocations

`ArrayList` uses a resizable array. While space remains, appending to the end mainly writes a reference into the next slot; when space runs out, growing capacity may require allocating a new array and copying references. Spare capacity helps subsequent additions avoid replacing the backing array.

The API guarantees that capacity is sufficient for the element count; it does not mandate a fixed growth factor across all versions. Do not build application logic on the assumption that it "always grows by exactly 1.5x". [`ArrayList` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

### 3.1. Choosing When to Allocate

- When the final element count is roughly known: pass an initial capacity or call `ensureCapacity` before a large batch of additions.
- When the scale is unknown: letting the list grow automatically is usually simpler; measure before setting a large spare capacity across all lists.
- When there are many small or empty lists: the fixed overhead of each collection instance and each array can matter more than the per-element cost in a large list.

In OpenJDK 21, the no-argument constructor uses a shared empty array and defers allocating a dedicated backing array until needed. Therefore, do not infer from descriptions of "default capacity" that every empty list already holds its own ten-slot array. This is an implementation detail that should be tied to a specific JDK version when analyzing heap dumps.

### 3.2. Removing Elements and Shrinking the Array Are Separate Operations

In OpenJDK 21, removing an element from an `ArrayList` clears the unused trailing reference after shifting; `clear()` clears the element references but keeps the existing array. Thus, `size() == 0` does not prove that the backing array has been released.

`trimToSize()` requests that capacity be reduced to the current element count. It may allocate and copy into a smaller array; it should not be called after every `add` inside a loop. Doing so can defeat the benefit of amortized growth with spare capacity and cause total copying work to spike.

Shrinking after a large data burst can make sense if the list will live a long time with few elements. If it is about to be reloaded to a similar scale, retaining the array can save allocations. [OpenJDK 21 `ArrayList` source code](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayList.java).

### 3.3. Steady-State Memory vs. Peak Memory During Expansion

Suppose an old array of capacity `c` needs to be replaced by a new array of capacity `c'`. While references are being copied, both arrays coexist. Peak storage during expansion is therefore close to the sum of both arrays, plus associated objects, rather than just the new array alone.

After the operation, the old array merely becomes eligible for garbage collection once no longer reachable; the OS process memory does not necessarily drop immediately. Distinguish between:

- **Retained live memory**: structures that remain alive after the operation completes.
- **Allocation volume over a time window**: includes old arrays that were replaced.
- **Peak memory**: the amount of memory required simultaneously during the transition phase.

Pre-sizing capacity appropriately can reduce array replacements and temporary allocation volume, whereas over-provisioning increases unused retained space.

## 4. `LinkedList`: No Spare Array Slots, but One Node per Element

In OpenJDK 21, each `LinkedList` element is wrapped in a separate node object. A node holds a data reference, a next-node reference, and a previous-node reference. Beyond those three references, it also carries an object header and alignment padding. [`LinkedList` source code](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/LinkedList.java).

```text
LinkedList
  first -------------------------------------------+
  last ---------------------------------------+    |
                                              |    v
null <--> [prev | item A | next] <--> [prev | item B | next] <--> null
             node object 1               node object 2
                     |                           |
                     v                           v
                 object A                    object B
```

Even if `item` is `null`, the node holding that element still exists. If the same object is added `n` times, the list still requires `n` nodes; only the data object is shared.

"No spare slots" does not imply "less memory". An array-backed list typically pays a few bytes for a reference slot; a linked list pays the cost of a full node object for every element. Having many small objects also increases allocation and tracking work for the garbage collector.

Array slots are contiguous in the array layout, even though the referenced data objects are not necessarily adjacent. With a linked list, traversal must follow pointers from node to node, so memory locality is generally less favorable. This is a factor to measure under realistic workloads, not a fixed runtime guarantee across all machines.

Likewise, do not choose `LinkedList` merely because you hear "O(1) insertion/deletion": you must already have the node position via an appropriate handle, such as an iterator positioned at that spot. Indexed access still has to traverse to find the position first. [`LinkedList` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html).

## 5. `HashMap`: Paying for Both the Bucket Table and Entry Nodes

A key–value mapping is different from a single list element. When reporting per-element memory for a map, specify the unit clearly as **per mapping** (or per entry).

In OpenJDK 21, the typical structure comprises the map object itself, a bucket reference array, and node objects holding the hash code, key, value, and next-node link. An empty bucket still occupies one array slot. Because a single bucket can hold multiple nodes, the number of empty buckets cannot be calculated simply as `bucket count - mapping count` the way spare slots are calculated in `ArrayList`. [`HashMap` source code](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/HashMap.java).

Let `b` be the number of buckets, `n` be the number of mappings, and `f` be the load factor. The ratio `n / b` describes the average load, not the fraction of non-empty buckets. Under normal assumptions and before hitting size limits, exceeding the threshold `b × f` triggers table expansion. The default value of `f` is `0.75`.

Model example: `b = 1,024` and `f = 0.75` yield a threshold of 768 mappings. Calling `new HashMap<>(1_000)` does not guarantee that the map can hold 1,000 mappings without resizing; the constructor parameter specifies a capacity request, not the expected number of mappings. Java 19+ provides `HashMap.newHashMap(expectedMappings)` specifically for an expected mapping count; code targeting Java 17 must compute and pass an appropriate initial capacity to the constructor.

Choosing an overly large table reduces resizing pressure but retains extra bucket slots, and iterating over a map is affected by both the bucket count and the mapping count. Do not arbitrarily lower the load factor just to make it "faster". [`HashMap` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

A standard node model also does not cover every case: collided buckets may convert to tree nodes with additional fields, and order-preserving maps (such as `LinkedHashMap`) require extra before/after links. To know the true cost, identify the exact implementation class and the node types currently present.

## 6. Building a Per-Element Memory Model

### 6.1. Formulas First, Byte Counts Second

Let:

- `S_list`, `S_linked`, `S_map`: the shallow size of the respective collection object itself.
- `A(c)`: the total size of an array of `c` references, including array header and alignment.
- `N_linked`: the size of a single linked-list node.
- `N_map`: the size of a single regular map node.
- `D`: the total size of the distinct data objects that the calculation chooses to include.

For an already-allocated structure, ignoring other auxiliary objects, the simplified model is:

```text
ArrayList:   M_structure ≈ S_list   + A(c)
LinkedList:  M_structure ≈ S_linked + n × N_linked
HashMap:     M_structure ≈ S_map    + A(b) + n × N_map

M_graph ≈ M_structure + D
bytes_per_element = M_structure / n       (n > 0)
```

This model applies to normal states of standard structures; it is not an exact formula for every empty-state optimization, auxiliary view, tree node, or custom collection. You must define `D` carefully before adding it so that shared objects are not double-counted.

The average cost (`M_structure / n`) differs from the marginal cost of a single `add` operation. One insertion may allocate nothing; the very next insertion may trigger the allocation of a large backing array. When `n = 0`, do not report "bytes per element" via this division; instead, report the total footprint of the empty collection.

### 6.2. Worked Example with Explicit Assumptions

Consider an **illustrative model**, not a measurement taken from every reader's machine:

- Reference size: 4 bytes; object header: 12 bytes; reference array header: 16 bytes.
- Object and array sizes are rounded up to a multiple of 8 bytes.
- A `LinkedList` node consists of an object header and three references, totaling 24 bytes in this model.
- `n = 100,000`, and the `ArrayList` capacity is assumed to be `c = 150,000`.
- Data objects and the fixed shallow size of the two collection objects are excluded here.

| Component Calculated | Model Calculation | Result |
| --- | --- | --- |
| `ArrayList` reference array | Rounded `16 + 150,000 × 4` | 600,016 bytes |
| Of which, spare slots | `50,000 × 4` | 200,000 bytes |
| `LinkedList` nodes | `100,000 × 24` | 2,400,000 bytes |
| Array divided by active element count | `600,016 / 100,000` | ~6 bytes/element |
| Nodes divided by element count | `2,400,000 / 100,000` | 24 bytes/element |

Even though the array has substantial spare capacity, its structural cost in this model is still much lower than that of linked nodes. Do not turn this example into the blanket rule "every `ArrayList` costs exactly 6 bytes/element": changing capacity, element count, reference width, or object alignment will change the result.

Alignment also means byte size does not always grow smoothly with every single reference. Adding one slot to an array might fit within existing alignment padding, whereas adding the next slot crosses over to the next alignment boundary. JOL demonstrates how to inspect object headers, fields, and alignment in the [official basic sample](https://raw.githubusercontent.com/openjdk/jol/master/jol-samples/src/main/java/org/openjdk/jol/samples/JOLSample_01_Basic.java).

### 6.3. Data Cost and Autoboxing

`ArrayList<Integer>` holds references to `Integer` objects; `int[]` stores primitive `int` values directly. Consequently, two structures holding the same quantity of integers do not share the same memory model.

With autoboxing, do not assume every position always allocates a brand-new `Integer`. `Integer.valueOf` caches values within a certain range, and references can also be shared explicitly. Conversely, rich domain elements may each own multiple distinct sub-objects. [`Integer` documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

If each element holds multiple strings, arrays, or a large sub-graph, `D` can dominate total memory. In that case, shaving off a few reference slots will unlikely solve a memory problem. Measure both the collection structure and the payload data to know which part is worth optimizing.

## 7. Java 17+ Experiment: Capacity Is Not Element Count

Save the following complete program as `CapacityDemo.java`:

```java
import java.util.ArrayList;

public class CapacityDemo {
    public static void main(String[] args) {
        ArrayList<StringBuilder> values = new ArrayList<>(8);
        System.out.println("initial size=" + values.size());

        StringBuilder shared = new StringBuilder("A");
        values.add(shared);
        values.add(shared);
        values.add(shared);

        values.ensureCapacity(100);
        System.out.println("after reserve size=" + values.size());
        System.out.println("same object=" + (values.get(0) == values.get(1)));

        values.remove(2);
        shared.append("B");
        System.out.println("after remove size=" + values.size());
        System.out.println("values=" + values);

        values.clear();
        System.out.println("after clear size=" + values.size());

        values.trimToSize();
        System.out.println("after trim size=" + values.size());
        System.out.println("outside reference=" + shared);
    }
}
```

Compile and run:

```shell
javac --release 17 CapacityDemo.java
java CapacityDemo
```

Stdout output:

```text
initial size=0
after reserve size=3
same object=true
after remove size=2
values=[AB, AB]
after clear size=0
after trim size=0
outside reference=AB
```

Explanation strictly matching what was observed:

- Constructing with an initial capacity of 8 still creates a list with `size() == 0`.
- `ensureCapacity(100)` does not add elements; the list still has three positions.
- Calling `add(shared)` three times reuses the same object. After removing one position and mutating `shared`, the remaining two positions both display `AB`.
- Both `clear()` and `trimToSize()` result in `size() == 0`; looking only at `size()` cannot tell whether the backing array is still large or has been shrunk.
- The external variable `shared` still retains the object after it is cleared from the list. Removing a reference from a collection does not mean the data object itself is eligible for garbage collection.

`ArrayList` has no public `capacity()` method. The program above verifies element-count and reference semantics; it does not print byte counts, measure the actual backing array size, or prove when the garbage collector reclaims objects.

## 8. Measuring Properly: Shallow Size, Reachable Graph, and Retained Size

Distinguish three concepts when reading profiling and layout tools:

| Concept | Question It Answers | Common Pitfall |
| --- | --- | --- |
| Shallow size | How many bytes does this single object instance occupy by itself? | Measuring only the `ArrayList` instance excludes its backing array |
| Reachable graph size | Which objects can be reached by following references starting from the collection? | Shared data objects are included in the reachable graph total |
| Retained size | Which objects would become eligible for reclamation if this root object were removed, considering all other live roots? | Cannot be deduced solely from the reachable graph total of a single collection |

JOL helps inspect object layout and the footprint of a reachable object graph. To compare structural overhead in isolation, you can populate two collections with the same shared object reference repeated many times. This prevents distinct data objects from overshadowing the cost of arrays and nodes, though it does not represent all real-world data workloads. [OpenJDK JOL project](https://github.com/openjdk/jol).

### 8.1. Measurement Program Using JOL

The complete example below requires `org.openjdk.jol:jol-core` on the classpath. The commands assume the library JAR has been prepared under the name `jol-core.jar`. Save the code as `MemoryProbe.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import org.openjdk.jol.info.ClassLayout;
import org.openjdk.jol.info.GraphLayout;
import org.openjdk.jol.vm.VM;

public class MemoryProbe {
    public static void main(String[] args) {
        int count = 10_000;
        Object shared = new Object();
        ArrayList<Object> array = new ArrayList<>(20_000);
        LinkedList<Object> linked = new LinkedList<>();

        for (int i = 0; i < count; i++) {
            array.add(shared);
            linked.add(shared);
        }

        System.out.println(VM.current().details());
        System.out.println("ArrayList object only:");
        System.out.println(ClassLayout.parseInstance(array).toPrintable());
        System.out.println("ArrayList reachable graph:");
        System.out.println(GraphLayout.parseInstance((Object) array).toFootprint());
        System.out.println("LinkedList reachable graph:");
        System.out.println(GraphLayout.parseInstance((Object) linked).toFootprint());

        array.trimToSize();
        System.out.println("ArrayList reachable graph after trim:");
        System.out.println(GraphLayout.parseInstance((Object) array).toFootprint());
    }
}
```

On Windows:

```shell
javac --release 17 -cp jol-core.jar MemoryProbe.java
java -cp ".;jol-core.jar" MemoryProbe
```

On Linux/macOS, use `:` as the classpath separator:

```shell
java -cp ".:jol-core.jar" MemoryProbe
```

There is no single fixed byte table on stdout that applies to every environment. Interpret the output using the following checks:

1. The `ClassLayout` section describes only the root `ArrayList` instance; do not mistake it for the total cost of the list.
2. In the array list's footprint, locate the `[Ljava.lang.Object;` reference array and its size; compare it before and after `trimToSize`.
3. In the linked list's footprint, locate the node object count; with 10,000 elements, a standard OpenJDK structure has 10,000 `LinkedList$Node` instances.
4. The `shared` object is counted only once within each individual graph footprint despite having 10,000 reference paths pointing to it. Adding the two separate reports together would double-count `shared` if you wanted the combined union footprint of both graphs.
5. If JOL prints warnings that it could not accurately detect JVM specifics or is estimating certain layout properties, read the warnings and verify your configuration before treating the output as exact measurements.

Because both `array` and `linked` hold references to `shared`, that object is not exclusively kept alive by either list alone. The total reachable graph reported by JOL does not automatically equal retained size. Analyzing retained size requires a heap analyzer that has the full context of live roots and dominator trees.

### 8.2. Recording Measurement Conditions for Reproducibility

Record the JDK/JVM version, architecture, compressed references settings (`UseCompressedOops`), object alignment, tool name, and tool version; also record `n`, requested capacity, removal ratio, whether data objects are shared or distinct, and whether payload data is included or only collection structure. Run comparisons under identical conditions.

Do not compute `Runtime.totalMemory() - Runtime.freeMemory()` before and after a single `add` call and conclude that the difference is the byte size of one element. The heap is simultaneously affected by background JVM activity, libraries, GC timing, and TLAB/region reservations kept for reuse. Calling `System.gc()` does not turn that subtraction into an accurate object-size measurement either.

If the problem is high allocation rate along a processing path, monitor allocation volume and GC activity under a representative workload. If the problem is an excessively large live heap after processing finishes, inspect the retained structures and reference chains. These two problems often require different optimizations.

## 9. Choosing Structures and Capacity by Scenario

| Scenario | What to Check | Trade-off to Remember |
| --- | --- | --- |
| Final element count is roughly known; mostly appending and iterating | Pre-size `ArrayList` capacity to a reasonable scale | Reduces array copies during growth, but retains spare slots if overestimated |
| List was once very large, then shrinks and stays alive for a long time | Measure retained backing array; consider `trimToSize` after the shrink phase | Trimming allocates and copies; if the list will soon grow again, the benefit may be lost |
| Currently using `LinkedList` to avoid spare array slots | Compare node overhead, object count, and actual access patterns | Avoids spare array slots, but pays full node overhead for every single position |
| Queue/stack workload that does not need to store `null` elements | Benchmark and measure an array-backed `ArrayDeque` alternative | Needs no per-element node objects, though it still manages array capacity and expansion |
| Map holding many key–value mappings | Account for both the bucket table and entry nodes; size capacity based on expected mappings | Bucket count and resize threshold do not mean the same thing as a list's element count |
| Large volume of primitive numeric data | Compare primitive arrays (or specialized primitive collections) against boxed collections | Must preserve required API contracts, operations, and data representation semantics |

The `ArrayDeque` option mentioned here relies on a circular array implementation; it does not permit `null` elements. Ensure functional requirements are satisfied before comparing memory footprints. [`ArrayDeque` source code](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayDeque.java).

## 10. Self-Check

1. An `ArrayList` has 1,000 elements and a capacity of 1,600. How many spare slots does it have? Can we conclude that 1,600 data objects exist?
2. Why can a linked list require no spare capacity yet still consume significantly more memory than an array-backed list?
3. Two collections both reference the same large object: can you add their two separate reachable-graph totals together to determine the combined distinct memory they occupy?
4. After calling `clear()`, the element count is 0. What must you check before concluding that memory has been reclaimed?
5. A report claims "8 bytes/element" without stating the JVM, capacity, or whether payload data objects are included. Why is that insufficient for making engineering decisions?

Reference answers:

1. There are 600 spare slots; the number of distinct data objects depends on duplicate references, `null` entries, and the actual payload data.
2. Every node requires an object header, prev/next/item references, and alignment padding; those per-element costs can easily exceed the cost of spare reference slots in an array.
3. No; objects must be deduplicated by object identity to avoid double-counting, and you must distinguish total reachable graph size from exclusively retained memory.
4. Check whether the backing array/bucket table is still retained by the collection, whether the data objects are still referenced elsewhere, and whether "memory" refers to live heap, committed JVM heap, or OS process memory.
5. The number leaves the denominator, measurement scope, and layout assumptions undefined, making a fair comparison against another data structure impossible.
