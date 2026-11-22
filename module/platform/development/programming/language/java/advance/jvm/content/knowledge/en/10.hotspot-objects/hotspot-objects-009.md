# Evaluating the Cost of Many Small Objects and Reference-Holding Data Structures in HotSpot

## Objectives

One million `int` values can be stored in a primitive array or in one million individual objects. The two structures carry the same logical data, yet have very different memory and execution costs. In HotSpot, each small object may require a **header**, **padding/alignment**, and **reference fields**; a container may also hold a **reference array**, **nodes**, or **entries**. A large number of objects can also increase allocation work, GC tracing, pointer chasing, and cache misses.

After this lesson, you will be able to:

- Distinguish **shallow size**, **object graph footprint**, **retained size**, **live heap**, **allocated bytes**, and **allocation rate**.
- Estimate the memory components of an object, reference array, primitive array, and a structure with N entries using an **assumption-based model**, without assigning fixed byte counts to all HotSpot builds.
- Identify boxing, object caches, aliasing, and why a reference slot does not automatically mean an additional object.
- Compare `int[]`, `Integer[]`, `ArrayList<Integer>`, `LinkedList<Integer>`, `HashMap<K,V>`, and custom node structures.
- Understand the impact of capacity, load factor, object lifetime, GC, CPU cache locality, and escape analysis/JIT.
- Practice on Java 17+, inspect data using JOL, JFR, `jcmd`/heap dump, and benchmark with JMH.
- Make optimization decisions based on measurements and API requirements, not solely on object count.

## 1. Counting logical elements is not enough to know the number of objects

Consider the illustrative Java snippet:

~~~java
int[] primitive = new int[1_000_000];
Integer[] boxed = new Integer[1_000_000];
~~~

The two expressions create **one array object on each side**, but:

- `int[]` directly stores 1,000,000 primitive int values defaulting to 0, without needing 1,000,000 Integer objects.
- `Integer[]` is a **reference array** containing 1,000,000 slots defaulting to `null`. The array creation statement **does not create one million Integer objects**.
- If you fill the boxed array with one million **references to the same Integer**, there is still only **one shared referent object** (aside from the array).
- If you fill it with distinct Integer values, the number of wrapper instances can grow very large; however, autoboxing/`Integer.valueOf` has a **cache**, and the JIT can optimize in valid cases.
- Two arrays with the same `length` do not mean the same amount of memory when the elements of a reference array point to different object graphs.

~~~text
int[N]
  [header][int0][int1][int2] ... [intN-1]

Integer[N] after filling with distinct referents:
  [header][ref0][ref1][ref2] ... [refN-1]
             |     |     |
             v     v     v
         [Integer][Integer][Integer]

Integer[N] when sharing a referent:
  [header][ref0][ref1][ref2] ...
             \     |     /
              \    |    /
                [Integer]
~~~

**Distinguish from the start:** a **reference value** is a value indicating the referenced object, not the entire object. Assigning `target[i] = shared;` only places a reference value into the slot; it does not clone the object.

## 2. Object header, fields, padding, and alignment

According to the JVM model, class instances and arrays reside on the **heap**. HotSpot is free to choose the physical object layout, as long as Java/JVM semantics are preserved.

A typical class instance has the conceptual structure:

~~~text
[ Object header / runtime metadata ]
[ Instance fields of the class and superclasses ]
[ Internal padding / alignment if needed ]
~~~

When there are many small objects, the repeated cost of the **object header and alignment** can be large compared to the useful data. For a class with one `byte` field, you cannot deduce a shallow instance size of one byte.

For a 64-bit HotSpot configuration with **compressed oops**, **compressed class pointers**, and **8-byte object alignment**, a common layout might have:
- Object header of about **12 bytes**.
- Compressed reference field of about **4 bytes**.
- `int` field with a 4-byte payload.
- An instance with one `int` may have a shallow size of **16 bytes** in this configuration.

**This is a conditional example, not a theorem for every JDK.** HotSpot may support compact object headers or other options; architecture, JDK version, flags, and alignment change the numbers. Compressed oops are also not required to be enabled on every 64-bit VM.

Mental formula:

~~~text
shallow_size(object)
  ~ align(header_bytes + field_bytes + padding_internal,
          alignment_bytes)
~~~

This is a **structural estimate**, not a substitute for measurement; field ordering, inheritance, packing, and alignment are controlled by the VM. With `N` objects, the total shallow bytes is typically around `N × shallow_size` if there really are N instances with the same layout.

### Example class with a reference link

~~~java
final class Link {
    int id;
    Link next;
}
~~~

This is an illustrative class. In a hypothetical configuration with a 12-byte header + 4-byte int + 4-byte compressed ref + 8-byte alignment:

~~~text
Unaligned: 12 + 4 + 4 = 20 bytes
Aligned:   24 bytes for one Link instance
1_000_000 Link instances: about 24_000_000 bytes
~~~

The figure of **24 decimal MB** is only for the Link instances themselves under those assumptions; it does not include the structures holding them, other referents, metadata/GC overhead, and heap capacity. `int[1_000_000]` has a primitive payload of 4_000_000 bytes, plus the header/alignment of **one array**. However, a linked structure provides different functionality and identity than a primitive array.

## 3. Primitive arrays, reference arrays, and boxing

Elements in `int[]` are stored directly inside the array object. Elements in `Object[]` or `Integer[]` are reference values; the referent objects reside separately according to the runtime model.

Approximate size model, where `N` is length and `R` is the reference width of the current JVM:

~~~text
int[N]:
  array_overhead + 4*N + tail_padding

long[N]:
  array_overhead + 8*N + tail_padding

Object[N]:
  array_overhead + R*N + tail_padding
  + memory of referents if graph calculation is needed

Populated Integer[N]:
  array_overhead + R*N + tail_padding
  + M * shallow_size(Integer)
  (M is the number of distinct Integer instances actually retained)
~~~

`array_overhead` includes metadata/header/length according to the actual JVM layout, and **there is no single mandatory value** across all platforms.

### Autoboxing adds further complexity

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);
System.out.println(a == b); // true
~~~

This is a code snippet inside a method. `Integer.valueOf` has a mandatory cache for the range **-128..127**, so the two references here point to the same Integer. Outside that range, do **not** rely on identity or allocation counts not promised by the API. To compare wrapper values, use `equals` or appropriate unboxing instead of `==`.

If a structure contains one million distinct large integers and holds them as Integer objects, the boxing cost can be high. Conversely, if the entire collection references a shared object cache, the number of wrapper objects does not equal the size of the collection.

**Conditional estimation example:** suppose 1,000,000 elements, R=4, each Integer wrapper has a shallow size of 16 bytes, every wrapper is a separate object, and the backing array has capacity 1,000,000. Reference slots require about 4 MB and wrappers about 16 MB, totaling about 20 MB **not counting the header/padding of the array and container**. For `int[]` with the same N, the payload is about 4 MB plus one header. This is **not an actual application measurement**.

## 4. Shallow size, reachable footprint, retained size, and allocation rate

| Metric | Question | Notes |
| --- | --- | --- |
| **Object count** | How many instances/arrays are there? | Not equal to the number of logical elements or the number of `new` occurrences in source. |
| **Shallow size** | How many bytes does the current object itself occupy? | Does not add objects pointed to by reference fields. |
| **Reachable graph footprint** | Which objects can be reached from a root and what is their total size? | May involve sharing with other roots. |
| **Retained size** | If an owner is removed according to the dominator relationship, how many bytes can become unreachable? | Not the sum of all reachable referents if there is sharing. |
| **Allocated bytes** | Total bytes allocated during the measurement interval? | Can be large even if most objects are already dead. |
| **Live heap** | How much data is still live at the measurement time/criterion? | Not equal to committed heap or process RSS. |

Example:

~~~text
Root A ------> [List] ------> [LargePayload]
                                  ^
Root B ---------------------------+
~~~

Removing Root A/List does not make `LargePayload` die if Root B still holds a reference. Therefore, you cannot compute retained size by summing all objects reachable from List. When analyzing a heap dump, the *dominator tree* helps find the object owners that actually retain significant memory.

**Reachability is a graph property**, not a property of a single variable's scope. `x = null` may cut one edge, but the referent remains live if another root/field/array holds it. GC also does not guarantee returning committed heap immediately to the OS.

## 5. ArrayList: backing array + references + elements

In common JDK implementations, `ArrayList<E>` holds elements using a backing array of references. The array's capacity can be larger than the list's size.

~~~java
ArrayList<String> names = new ArrayList<>(100);
names.add("A");
names.add("B");
System.out.println(names.size()); // 2
~~~

This snippet requires `import java.util.ArrayList;`. `size()==2` does not mean the backing array only has two slots. With a capacity of 100, there is still the cost of reserved reference slots.

Components in memory:
1. **ArrayList instance** (metadata such as size/reference to the backing array).
2. **Backing array object** with capacity `C ≥ size`.
3. **Element objects** if elements are references to objects held by the application.
4. Possible temporary arrays during grow/copy.

A mental expression:

~~~text
ArrayList<E> graph footprint
  ~= shallow(ArrayList)
      + shallow(backing Reference[])
      + E referents belonging to the graph (without double-counting sharing)
~~~

For `ArrayList<Integer>`, **Integer wrappers** need to be considered. For `ArrayList<byte[]>`, each **byte[] payload** needs to be considered if they actually exist separately, not just the reference slots.

According to the Java API, `ArrayList.add` has amortized constant-time behavior; `get(index)` is usually fast, while inserting/removing in the middle may shift references. **Do not hardcode a specific capacity growth factor for all JDK versions**, because the detailed growth policy is an implementation detail.

### Reserving and shrinking

- `new ArrayList<>(expectedSize)` or `ensureCapacity(expectedSize)` can reduce the number of grow/copy operations if the number of elements to be added is known in advance.
- Over-reserving for **many** small lists can waste significant memory.
- `trimToSize()` reduces capacity to size; it does not destroy element objects currently held by the list.
- If there are very many lists that are often empty or hold only 1–2 elements, the **fixed overhead of the list itself and the backing array** can dominate.

**Do not use reflection on ArrayList's private fields as an API**, because module encapsulation, JVM updates, and implementation details can change.

## 6. LinkedList: many node objects and pointer chasing

A doubly linked list typically has each element in a node storing `prev`, `next`, and `item` references. In common JDKs, `LinkedList<E>` has a similar node-based mechanism.

~~~text
LinkedList instance
      |
      v
[Node item,prev,next] -> [Node] -> [Node] -> ...
      |                   |        |
      v                   v        v
   [Element]           [Element] [Element]
~~~

Approximate footprint:

~~~text
shallow(LinkedList)
+ N * shallow(Node)
+ referent elements (excluding shared parts)
~~~

Each node has a **header, multiple reference fields, and alignment**, so the total overhead per N is usually higher than the corresponding backing reference array. If the element type is Integer, you may pay **both** the node cost **and** the wrapper cost.

You cannot conclude from this that LinkedList is always slow/bad:
- Adding/removing when an iterator/node is already at the position can avoid shifting an entire array.
- If random positional access is needed, LinkedList usually has to traverse nodes, taking O(N) time to find the position.
- ArrayList can copy references in blocks efficiently and has better locality.
- Workloads handling queues/deques may be better suited to `ArrayDeque`, depending on API and thread-safety.

**Important:** Big-O describes algorithmic trends, **not including** all object allocations, CPU cache misses, and GC overhead. Choose based on workload, not a slogan like "LinkedList inserts fast".

## 7. HashMap, HashSet, and entry structures

In common HotSpot/JDK implementations, `HashMap<K,V>` has a **bucket table** which is a reference array along with **entry/node objects** for mappings. When collisions are high, some buckets may use a different representation (e.g., tree nodes).

~~~text
HashMap
  |
  v
table[capacity]
  |
  +--> bucket0: Node(keyRef, valueRef, nextRef)
  |
  +--> bucket1: null
  |
  +--> bucket2: Node --> Node ...
~~~

Cost components:
- The **HashMap object** itself.
- **Backing table** with capacity buckets, including unused buckets.
- **Entry objects** or equivalent representation depending on the JDK.
- **Key objects**, **value objects**, and the graphs behind them.
- Resize/re-hash, load factor, collision handling, and excess capacity.

One million mappings does not mean one million new key objects and one million new value objects: keys/values can be created outside the map and shared; `put` with the same key can replace the value without increasing size. For boxed keys like Integer/Long, wrappers must also be counted if they are distinct instances.

### Load factor and capacity

Load factor affects the relationship between the number of entries and the backing table capacity. A large capacity can create many unused reference slots; a small capacity can make resizing/collisions costly. It must be evaluated on the actual distribution of keys/operations, not chosen by a single number.

`HashSet<E>` in common JDKs uses similar hash-based storage at the mechanism level, so it is not "free" of nodes/table just because the API only represents a set of elements.

**Do not assign fixed byte counts to `HashMap$Node` or `LinkedList$Node`** as a Java SE standard. The layout of inner classes is a JDK-version detail, and VM headers/field packing further affect it.

## 8. Reference-storing structures with sharing or deep object graphs

A structure containing 2 references can point to:
- **The same object** → two edges, one referent.
- **Two different objects** → two edges, two referents.
- **Two different objects holding the same payload** → multiple objects at the outer layer, one shared payload.
- **Two independent payloads** → multiple referents and multiple data arrays.

Model:

~~~text
Owner A ---+
           +---> [SharedPayload byte[]]
Owner B ---+

Owner C ------> [SeparatePayload C]
Owner D ------> [SeparatePayload D]
~~~

### Standalone runnable Java 17+ example: sharing

Create file **`ReferenceSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReferenceSharingDemo {
    public static void main(String[] args) {
        byte[] shared = new byte[4];

        List<byte[]> reused = new ArrayList<>();
        reused.add(shared);
        reused.add(shared);

        List<byte[]> independent = new ArrayList<>();
        independent.add(new byte[4]);
        independent.add(new byte[4]);

        System.out.println("reusedSame=" +
                (reused.get(0) == reused.get(1)));
        System.out.println("independentSame=" +
                (independent.get(0) == independent.get(1)));

        reused.get(0)[0] = 9;
        System.out.println("aliasValue=" + reused.get(1)[0]);
        System.out.println("independentValue=" + independent.get(1)[0]);
        System.out.println("reusedSlots=" + reused.size());
        System.out.println("independentSlots=" + independent.size());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac --release 17 ReferenceSharingDemo.java
java ReferenceSharingDemo
~~~

**Exact stdout:**

~~~text
reusedSame=true
independentSame=false
aliasValue=9
independentValue=0
reusedSlots=2
independentSlots=2
~~~

Both lists logically hold two entries; `reused` holds **one shared byte[] referent**, whereas `independent` holds two separate byte[] objects. Aliasing changes the graph's footprint but also impacts **mutation semantics**: modifying the shared payload through one reference will be visible through the other reference.

**Object sharing is not always appropriate.** If owners need to mutate independently, sharing causes unintended side effects. Memory-saving decisions must preserve correctness and ownership.

## 9. Java 17+ example: same five numbers, multiple representations

Create file **`ContainerShapeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;
import java.util.List;

public class ContainerShapeDemo {
    static final class Node {
        int value;
        Node next;

        Node(int value, Node next) {
            this.value = value;
            this.next = next;
        }
    }

    static int sumNodes(Node head) {
        int sum = 0;
        for (Node n = head; n != null; n = n.next) {
            sum += n.value;
        }
        return sum;
    }

    static int sumList(List<Integer> values) {
        int sum = 0;
        for (int v : values) {
            sum += v;
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] values = {10, 20, 30, 40, 50};

        Integer[] boxed = new Integer[values.length];
        ArrayList<Integer> arrayList =
                new ArrayList<>(values.length);
        LinkedList<Integer> linkedList = new LinkedList<>();

        Node head = null;
        for (int i = values.length - 1; i >= 0; i--) {
            head = new Node(values[i], head);
        }

        int primitiveSum = Arrays.stream(values).sum();

        for (int i = 0; i < values.length; i++) {
            boxed[i] = Integer.valueOf(values[i]);
            arrayList.add(boxed[i]);
            linkedList.add(boxed[i]);
        }

        int boxedSum = 0;
        for (Integer v : boxed) {
            boxedSum += v;
        }

        System.out.println("primitiveSum=" + primitiveSum);
        System.out.println("boxedSum=" + boxedSum);
        System.out.println("arrayListSum=" + sumList(arrayList));
        System.out.println("linkedListSum=" + sumList(linkedList));
        System.out.println("nodeSum=" + sumNodes(head));
        System.out.println("arrayLength=" + values.length);
        System.out.println("listSize=" + arrayList.size());
        System.out.println("sameFirstRef=" +
                (arrayList.get(0) == boxed[0]));
    }
}
~~~

Commands:

~~~bash
javac --release 17 ContainerShapeDemo.java
java ContainerShapeDemo
~~~

**Exact stdout:**

~~~text
primitiveSum=150
boxedSum=150
arrayListSum=150
linkedListSum=150
nodeSum=150
arrayLength=5
listSize=5
sameFirstRef=true
~~~

Meaning:
1. `int[]` contains 5 primitive values in one array object.
2. `Integer[]` contains 5 reference slots. The values 10,20,30,40,50 are in the mandatory Integer cache range, so do not use this program to count 5 wrapper allocations.
3. `ArrayList<Integer>` and `LinkedList<Integer>` both hold **the provided reference values** from the boxed array; they do not automatically deep-copy element objects.
4. LinkedList can add node instances, whereas ArrayList uses a backing array.
5. The custom Node chain consists of **5 separate Node instances**, each with an int field and a link reference.
6. The sums are equal, but the footprint and memory-access shape differ.

The example illustrates semantics, **not** a throughput benchmark or byte-measuring tool.

## 10. Object locality, pointer chasing, and CPU cache

Data in a primitive array tends to support sequential traversal well thanks to contiguous layout. In a reference array, **reference slots** are contiguous, but **referents** are not guaranteed to be contiguous. Linked nodes require reading `next` before knowing where the next node is located.

~~~text
int[]:
  read element0 -> element1 -> element2 -> ...

ArrayList<E>:
  read ref0 -> dereference E0
  read ref1 -> dereference E1
  ...

LinkedList<E>:
  read node0.next -> node1.next -> node2.next ...
~~~

Possible impacts include:
- CPU cache misses, TLB pressure.
- Poor hardware prefetching capability for dependent pointer chasing.
- More object headers/metadata for GC to manage.
- Allocation churn if nodes are continuously created/destroyed.
- Time to find a position when accessing by index.

However, locality is not an invariant guarantee. The collector can move objects, and HotSpot may allocate them close together at one time without guaranteeing they stay adjacent. If the workload is mainly hash key lookup, a good algorithm can matter more than pure locality; if only very few entries are traversed, structural costs may differ.

## 11. Allocation rate differs from retained heap

Two applications may both have 100 MB of live objects yet have very different allocation rates:
- A creates data once and keeps it for a long time.
- B creates millions of temporary wrappers per second and discards them.

B can cause greater GC/CPU load even if at the end of the measurement interval its live heap equals A's. Conversely, many small long-lived objects can increase GC tracing/live-set footprint even when the allocation rate is low.

| Metric | Used to |
| --- | --- |
| **Bytes allocated per operation** | Know whether each request/task allocates a lot. |
| **Allocation rate bytes/s** | See total pressure at steady state. |
| **Live heap after appropriate GC** | Estimate the data set that needs to survive. |
| **Retained heap/dominator** | Find owners holding objects that are no longer needed. |
| **GC pauses, frequency, CPU** | Evaluate impact on latency/throughput. |
| **Process RSS / committed heap** | Inspect system footprint, without equating them with live objects. |

Memory leak issues in Java are often **reference retention**: caches without eviction, unregistered listeners, growing static collections, thread-locals holding data too long, or incorrect key/value lifecycles. GC does not automatically collect objects that remain reachable from roots.

## 12. JIT and escape analysis: number of `new` does not equal physical allocations

Example:

~~~java
static int calculate(int a, int b) {
    Pair p = new Pair(a, b);
    return p.first + p.second;
}
~~~

This is a snippet requiring a suitable `Pair` class. If the JVM JIT proves the object does not escape and eliminating the allocation does not change observable behavior, it **may** use **scalar replacement** instead of creating a physical object.

Things you **cannot** conclude from source alone:
- Every `new` definitely consumes a physical heap object on every JIT run.
- Every small object is definitely stack-allocated.
- The JIT definitely eliminates this specific allocation in this example across all Java versions/tiers.
- Because bytecode still has the `new` opcode, a profiler must count an allocation in optimized execution.

To evaluate object churn, it is necessary to observe in the actual context: warmup, compiler tier, escape, inlining, garbage collector, and profiler overhead. A test that does not consume the result may undergo dead-code elimination, making measurements nearly meaningless.

## 13. Measuring object layout with JOL

**Java Object Layout (JOL)** is an OpenJDK tool for studying actual object layout/footprint and simulating VM modes. JOL helps confirm headers, alignment, field offsets, and how references contribute to the graph.

Example commands (assuming the appropriate JOL CLI JAR has been downloaded and named `jol-cli.jar`):

~~~bash
java -jar jol-cli.jar internals java.lang.Integer
java -jar jol-cli.jar internals-estimates java.lang.Integer
java -jar jol-cli.jar footprint java.util.HashMap
~~~

This is guidance for a tool **outside Java SE**, with no guarantee of a fixed output. JOL CLI version, VM mode, flags, class structure, and access permissions can affect available commands/results.

- **internals**: shows header/field/padding and object layout.
- **internals-estimates**: estimates certain layouts in supported VM modes.
- **footprint**: inspects the object graph; must distinguish reachable graph from retained dominator ownership.
- Some JOL heapdump modes help gather statistics on objects/wrappers/duplicates at the heap level.

Project page: https://openjdk.org/projects/code-tools/jol/ and documentation: https://github.com/openjdk/jol.

### State assumptions clearly when reporting results

A memory measurement report should include:
- Exact JDK version/build, HotSpot architecture, VM flags/compressed references/alignment.
- GC collector and relevant heap flags.
- Size N, array capacity, load factor, key/value data, and level of object sharing.
- Whether measuring **shallow** or **graph/retained**.
- Whether results include or exclude wrapper objects, backing arrays, and secondary indexes.
- Number of runs, noise level, and verification method.

Simply saying "Integer weighs 16 bytes" without stating VM assumptions is not reliable enough for implementation decisions.

## 14. Using JFR, jcmd, and heap dumps for real-world investigation

**JFR (Java Flight Recorder)** can provide information on allocation hotspots, event samples, and VM activity; **jcmd** can obtain heap info, histograms, heap dumps, or control JFR on supported HotSpot VMs.

Some command templates for a **running Java process** (replace `PID` with the actual PID number):

~~~bash
jcmd PID GC.heap_info
jcmd PID GC.class_histogram
jcmd PID JFR.start name=MemStudy settings=profile duration=60s filename=memory.jfr
jcmd PID JFR.check
~~~

`PID` is a **placeholder symbol in command-line instructions**, not a string to keep literally when running. Diagnostic commands can have significant impact, especially class histogram on a large heap; do not enable arbitrarily in production.

When a dump is needed:

~~~bash
jcmd PID GC.heap_dump filename=memory.hprof
~~~

**Security warning:** a heap dump may contain passwords, tokens, session data, PII, or other sensitive data. Only collect, store/share with proper authorization, file protection, and retention policies. Dumps can be very large and affect throughput/GC while running.

### What does a histogram tell you and what does it not?

A class histogram groups objects by runtime class, showing instance counts and recorded shallow bytes. It is useful for spotting too many `Integer`, `HashMap$Node`, `byte[]`, or domain records.

However, a histogram **does not fully determine**:
- Who is keeping those objects reachable?
- The retained heap of a cache/owner?
- Temporary allocations that died before the snapshot time?
- CPU cache misses or traversal latency?

To find the cause of **retention**, use a heap dump with **dominator tree and paths to GC roots**. To find the cause of **churn**, use JFR/allocation profiler. If performance is needed, time and throughput must be measured separately.

## 15. Benchmarking with JMH

You cannot conclude performance from a single loop measured with `System.nanoTime()`. HotSpot JIT can:
- Warm up and inline differently across iterations.
- Use scalar replacement to make object allocations disappear.
- Eliminate code whose results are not used.
- Use CPU caches differently depending on whether data is reused.
- Have noise from GC, scheduling, CPU frequency, contention, and profilers.

**JMH (Java Microbenchmark Harness)** is an OpenJDK project for microbenchmarks, supporting warmup, measurement iterations, forks, state, and result consumption to reduce bias.

A fair test plan:

| Measurement | What to keep constant |
| --- | --- |
| Traversing `int[]` vs `ArrayList<Integer>` | Same N and values; consume sum; record boxing/cache setup |
| Traversing `ArrayList<E>` vs `LinkedList<E>` | Same referents, set up data outside measurement region if only measuring iteration |
| Insert/remove middle | Include how position is located or separate search cost according to intent |
| `HashMap` lookup vs array scan | Same keys, query distribution, load factor, and cardinality |
| Creating N objects per request | Measure throughput, bytes/op, and GC together |
| Structure-of-arrays vs object-per-entry | Ensure same semantics and access pattern |

**Do not treat a JMH score as the end-to-end score** of a web application/service: network, DB, serialization, locks, and tail latency can matter more than a micro-operation.

JMH project page: https://openjdk.org/projects/code-tools/jmh/.

## 16. Which structure to choose?

| Workload | Option usually considered first | Trade-off |
| --- | --- | --- |
| Many integers and sequential traversal | `int[]`, `long[]`, or primitive-specialized collections | Good packing, but API/resizing differs from generic List |
| List of objects accessed by index | `ArrayList<E>` | Backing array/capacity + referents |
| FIFO/LIFO | `ArrayDeque<E>` or suitable queue | Data stored via references, synchronization depends on API |
| Lookup by key | `HashMap<K,V>` | Table, nodes, load factor, key/value graphs |
| Sorted/range queries | `TreeMap<K,V>` or sorted array depending on workload | Tree-node overhead vs array update cost |
| Removing/inserting with iterator already in position | `LinkedList<E>` when truly appropriate | Node overhead/pointer chasing, expensive random get |
| Very many uniform small records | Object array vs **structure-of-arrays** | Packing and locality vs identity/API complexity |
| Cache that can grow unboundedly | Bounded cache/eviction policy | Requires clear owner retention limits |

### When to use structure-of-arrays?

Instead of N instances like:

~~~java
class Entry {
    int id;
    long timestamp;
}
~~~

you can keep two primitive arrays:

~~~java
int[] ids = new int[n];
long[] timestamps = new long[n];
~~~

The snippets above are **illustrations requiring a valid context declaring variable n and the class**. The second representation eliminates many object headers and can improve cache locality for scans. However, it changes semantics:
- No longer an object identity per entry in the original sense.
- Easy to introduce index mismatches when deleting/reordering.
- Requires controlling concurrent updates, growth, and invariants between the two arrays.
- Not better by default for every access pattern.

Use real measurement data and maintainability to decide, rather than forcing all domain models into arrays.

## 17. Verifiable optimization checklist

1. State the problem clearly: memory budget, GC pauses, throughput, tail latency, or allocation CPU?
2. Quantify the number of elements **N**, size distribution, lifetime, access pattern, null/sharing ratio.
3. Draw the object graph: container, backing arrays, nodes/entries, keys/values, wrappers, payload arrays.
4. Separate **data cost** from **reference-holding structure cost**.
5. Choose the appropriate metric: shallow, graph, retained, bytes/op, or latency.
6. Record JDK/VM flags/alignment/compressed-oops/collector before comparing bytes.
7. Measure baseline with JOL/JFR/heap dump/profiler/JMH depending on the question.
8. Change one factor: reserve capacity, primitive storage, node count, cache policy, reuse.
9. Verify **correctness** after the change: aliasing, identity, equals/hashCode, null, concurrency.
10. Re-measure on real workload, document pros/cons, and roll back if the trade-off is unsuitable.

**Proper optimization** is not always having the fewest objects, but meeting SLAs and memory budgets **while maintaining functionality, correctness, and maintainability**.

## 18. Common misconceptions

| Claim | Correct understanding |
| --- | --- |
| “An object with an int field occupies 4 bytes.” | Header, alignment, and other fields also contribute to shallow size. |
| “On a 64-bit JVM, every reference must be 8 bytes.” | Compressed oops can use a smaller width. |
| “An object array with N slots means N element objects have been created.” | Slots only hold references, initially null. |
| “Every autoboxing definitely creates a new object.” | Caches/optimizer can affect object identity/allocation. |
| “ArrayList size is its capacity.” | Capacity can have excess, increasing the backing array footprint. |
| “LinkedList saves memory because it has no backing array.” | It has many node objects and prev/next/item refs. |
| “HashMap only costs key + value.” | There are also table, entries/nodes, capacity, and collision handling. |
| “Reachable footprint always equals retained size.” | If graphs share objects, the numbers can differ. |
| “Low live heap means low allocation rate.” | Short-lived objects can be created and discarded very quickly. |
| “Committed heap not shrinking means a leak.” | The VM may retain committed memory for reuse. |
| “GC sees a large object and will automatically delete it if business logic doesn't use it.” | If still reachable from roots, GC does not know business logic. |
| “The JOL byte count on my machine is standard for every JVM.” | Layout depends on JDK/HotSpot options/architecture. |
| “TLAB belongs to the stack.” | TLAB is an allocation mechanism in the heap. |
| “Every `new` definitely creates a physical allocation.” | JIT can eliminate allocations while preserving semantics. |
| “ArrayList is always faster than LinkedList in every operation.” | Must consider algorithm, search, mutation, and workload. |
| “Heap dumps can be shared freely.” | They risk containing secrets/PII; access must be controlled. |

## 19. Self-check questions

**Question 1.** Why can't you take `4 × N` bytes to calculate N instances with one int field?

**Answer:** Because each instance also has a header, alignment/padding, and possibly inherited fields; actual shallow size needs to be measured.

**Question 2.** How many Integer objects does `new Integer[1000]` create?

**Answer:** It creates no Integer referents, only one Integer[] array with 1000 null reference slots.

**Question 3.** How do multiple reference slots pointing to the same object affect the graph?

**Answer:** There are multiple references but one referent, avoiding multiplying the object footprint by the number of slots; however, sharing has its own mutation semantics.

**Question 4.** Why can `ArrayList<Integer>` cost more than `int[]`?

**Answer:** ArrayList object + backing reference array + Integer wrappers (if many distinct objects), whereas int[] stores primitive values in one array.

**Question 5.** Do Integer values in the cache range definitely allocate a new object on every boxing?

**Answer:** No. `Integer.valueOf` has a mandatory cache for -128..127.

**Question 6.** What per-element overhead does LinkedList typically have?

**Answer:** A Node object with header, references, and padding, plus the referenced elements.

**Question 7.** What overhead does HashMap add besides keys and values?

**Answer:** Table, entry nodes, excess capacity, and collision/tree structures depending on the implementation.

**Question 8.** Is retained size equal to the sum of all objects reachable from an owner?

**Answer:** No, when there is object sharing from other GC roots. Retained size relates to the dominator relationship.

**Question 9.** Can a high allocation rate with a small live heap happen?

**Answer:** Yes. Temporary objects with very short lifetimes still create GC/allocation churn.

**Question 10.** What do you use to measure object layout? What do you use to measure allocation hotspots?

**Answer:** JOL to inspect layout/footprint; JFR/profiler to investigate allocations; heap dump/dominator for retention.

**Question 11.** Can you use a `System.nanoTime()` loop without consuming the result to prove a data structure is faster?

**Answer:** No; JIT can eliminate code/allocations, and warmup and GC cause noise; use JMH and valid benchmarks.

**Question 12.** When might struct-of-arrays be appropriate?

**Answer:** For many records with a uniform schema, sequential/analytical access, and when memory/locality is a bottleneck, after considering identity, API, and measurement.

## 20. Mind map

~~~text
                   N LOGICAL ELEMENTS
                         |
         +---------------+----------------+
         |                                |
    PRIMITIVE                         REFERENCE
      int[N]                         Object[N] / List<E>
         |                                |
    1 array header                    array slots R*N
    + 4*N payload                         |
                                    element referents
                                         |
                               +---------+----------+
                               |         |          |
                             wrappers   nodes      key/value
                               |         |          |
                               +---------+----------+
                                         |
                               OBJECT GRAPH FOOTPRINT
                                         |
                    +--------------------+------------------+
                    |                    |                  |
                SHALLOW SIZE        RETAINED SIZE     ALLOCATION RATE
                layout/headers      dominator graph   churn/GC impact
                    |                    |                  |
                    +--------------------+------------------+
                                         |
                             latency / throughput / cache
                                         |
                                MEASURE ON REAL HOTSPOT

JOL = layout       JFR = allocation       Heap dump = retainers
JMH = performance  jcmd = VM diagnostics
~~~

**Conclusion:** the cost of many small objects can accumulate from **headers, alignment, nodes/entries, and references**, not just the bytes of fields. You must account for **reference-holding structures** along with the **referent graph**, and separate **retained/live heap** from **allocation churn**. Estimation models are useful for guidance, but engineering decisions must be based on measurements on the **right JDK/HotSpot, right configuration, and right workload**.

## References

- [JVMS Java SE 21 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.3).
- [JLS Java SE 21 — Types, Values and Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html).
- [OpenJDK — Java Object Layout (JOL)](https://openjdk.org/projects/code-tools/jol/).
- [OpenJDK — JOL README (layout/footprint)](https://github.com/openjdk/jol).
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://openjdk.org/projects/code-tools/jmh/).
- [Java SE 21 — ArrayList API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).
- [Java SE 21 — LinkedList API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedList.html).
- [Java SE 21 — HashMap API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
