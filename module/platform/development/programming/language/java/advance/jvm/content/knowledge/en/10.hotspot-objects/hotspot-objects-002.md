# Fast Bump-Pointer Allocation and Thread-Local Allocation Buffer (TLAB) in HotSpot

## 1. Goal and Problem to Solve

In Java, the expression `new Item(...)` looks very simple. However, at the JVM level, the runtime must allocate enough space for the object, ensure alignment and initial field state, initialize the object, and then return a valid reference. If **every** object creation by **every thread** had to acquire a global heap lock, the rate of object creation in multithreaded applications could be severely limited.

**HotSpot** typically solves this problem using two cohesive techniques:

1. **Bump-the-pointer allocation**: within a suitable heap region with contiguous free space, maintain a `top` pointer pointing to the start of the unallocated portion. To allocate an object of aligned size `size`, check `top + size <= end` and then advance `top`.
2. **Thread-Local Allocation Buffer (TLAB)**: assign an execution thread a **slice of the heap** to self-allocate objects via a fast path, reducing the need for contention whenever an object is created.

This lesson helps you explain:

- TLAB **resides in the Java heap**, **not the JVM stack**, **not `ThreadLocal<T>`**, and is not "permanent private memory" holding every object of a thread.
- Why each allocation in a TLAB typically only needs a bounds check, a pointer bump, and initialization steps.
- When a TLAB does not have enough space, HotSpot can attempt to **refill/retire the TLAB**, allocate outside the TLAB, or enter the **slow path** depending on the collector, object size, and runtime policy.
- Why an object allocated in a TLAB can still **be read by another thread** once the reference is safely published.
- Why `new` in source code **does not guarantee** that a heap allocation always exists at runtime: JIT escape analysis/scalar replacement can eliminate the allocation.
- How to observe `-XX:+UseTLAB`, `-XX:-UseTLAB`, and `-Xlog:gc+tlab=...` in HotSpot, along with the limitations of logging/benchmarking.

**Scope limitation:** TLAB and the bump-pointer fast path are **HotSpot implementation details**, not a requirement that every Java Virtual Machine implementation in the JVMS must use the same structure or the same flags.

## 2. From Java Source to the Allocation Operation

Source code:

~~~java
final class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}

// Inside a method:
Point p = new Point(3, 4);
~~~

The snippet above **illustrates** a class and statement; it is not yet a standalone file with `main`. With standard `javac`, the bytecode path to create an object typically consists of:

~~~text
new           #...   // class Point
dup
iconst_3
iconst_4
invokespecial #...   // Point.<init>:(II)V
astore_1
~~~

Explanation:

1. `new` is the opcode requesting allocation of an object of the corresponding class (after appropriate class resolution and initialization requirements).
2. `dup` keeps a reference on the operand stack so that the `new Point(...)` expression still has the reference after the constructor is called.
3. `iconst_3`/`iconst_4` prepare the arguments.
4. `invokespecial Point.<init>` runs the constructor. **The constructor is not the allocation operation itself**: it initializes the already-allocated object.
5. `astore_1` stores the reference into a local-variable slot. **The reference is in the frame; according to the JVM model, the object is allocated in the heap.**

This is the **abstract bytecode** level. When the interpreter or JIT processes `new`, HotSpot may choose among several allocation paths. You **do not see TLAB pointer arithmetic directly through `javap -c`**, because `javap` only displays JVM bytecode, not JIT machine code or C++ runtime helpers.

### What Does JVMS Guarantee, and What Does HotSpot Choose?

| Layer | What is guaranteed/described | What should not be inferred |
| --- | --- | --- |
| Java language/JVMS | Semantics of `new`, reference types, object initialization, Java heap as a shared run-time data area | Every VM must allocate via TLAB |
| HotSpot allocator | Common optimizations: TLAB, bump pointer, allocation slow path | Every object goes through the same fast path |
| Garbage collector | Manages free/used regions, moves or reclaims objects depending on the collector | The heap always has only a single contiguous Eden |
| JIT compiler | Can inline, eliminate allocations via scalar replacement, adjust machine code | Seeing `new` is sufficient to count actual heap allocations |

## 3. Bump-the-pointer: From `top` to the Object Location

Suppose HotSpot has a heap region currently used for sequential allocation. Let:

- `start`: start of the region allocated to the allocator.
- `top`: position of the next available free memory.
- `end`: limit of the allocatable region.
- `size`: size of the object **already including header, fields, padding/alignment** according to the specific layout.

~~~text
Contiguous memory segment reserved for allocation:

start                        top                         end
  |                           |                           |
  v                           v                           v
  +---------------------------+---------------------------+
  |     allocated objects     |        free space         |
  +---------------------------+---------------------------+

Request for a new object with aligned size = S:

  if top + S <= end:
       objectAddress = top
       top = top + S
       prepare memory/header/object fields per semantics
       return reference to object

  otherwise:
       cannot use that fast path
       -> handle refill/slow path/other appropriate path
~~~

This is **modeling pseudo-code**, not verbatim HotSpot machine code. Implementations also handle overflow, alignment, memory ordering, JFR/JVMTI instrumentation, barriers, GC state, zeroing, and other requirements.

### Illustrative Arithmetic Example, Not Actual Object Layout

Suppose a region has `top = 1_000`, `end = 1_128`, and needs to allocate an object with **aligned size = 24 bytes**:

~~~text
1_000 + 24 = 1_024 <= 1_128  -> can allocate
object starts at hypothetical offset 1_000
new top = 1_024

Next time 112 bytes are needed:
1_024 + 112 = 1_136 > 1_128 -> not enough space in this region
~~~

The numbers 1_000, 1_128, 24, and 112 are **hypothetical numbers to understand the algorithm**. They do not say that every Java object always has a 12/16-byte header or that `Point` always occupies exactly 24 bytes. Layout depends on the JDK, compressed oops/class pointers, object alignment, object type, and JVM configuration.

### Why Is Bump Pointer Fast?

If there is a **contiguous free heap portion**, the allocator does not need to search for a suitable block in a freelist for each object. The main operations can be optimized into a few comparisons and pointer additions. However, if **multiple threads simultaneously update a single heap `top` pointer**, the VM needs to synchronize using atomic operations, CAS, or another mechanism; this is where TLAB helps reduce contention.

**Do not confuse** the allocator's bump pointer with a Java object reference: applications are not allowed to add or subtract `Object` references like C pointers. `top` is internal allocation management data inside HotSpot.

## 4. What Is a TLAB and Where Is It Located?

**TLAB = Thread-Local Allocation Buffer**: a **sub-region of the Java heap** that HotSpot assigns to an execution thread to create most small objects on a fast path. You can picture a heap consisting of multiple segments, in which some segments are currently "granted allocation rights" to specific threads:

~~~text
                    JAVA HEAP (shared JVM-wide)
+----------------------------------------------------------------+
| Collector-managed regions / allocation space                   |
|                                                                |
| +----------------+  +----------------+  +--------------------+ |
| | TLAB thread A  |  | TLAB thread B  |  | Other heap space   | |
| | start/top/end  |  | start/top/end  |  | large allocations  | |
| +----------------+  +----------------+  | objects from past  | |
|                                          | TLABs, GC regions  | |
|                                          +--------------------+ |
+----------------------------------------------------------------+

Thread A has the right to bump the pointer in TLAB A while owning that region.
Thread B has the right to bump the pointer in TLAB B.
Objects created in a TLAB are still objects in the HEAP and can escape.
~~~

**Three important points:**

1. **A TLAB is not a private memory region in Java semantics.** It is only an allocation region reserved for one thread at a given time. Once an object has been properly published, other threads can still access it.
2. **A TLAB is not a thread stack**: a local `Foo f` is typically a reference in a frame; `new Foo()` itself is a heap object (unless the JIT eliminates the allocation). An object does not "move from the stack to the heap" just because its reference escapes from the allocating thread.
3. **A TLAB is not `ThreadLocal<Foo>`**: `ThreadLocal` is a Java API storing per-thread values; TLAB is an internal VM buffer managing allocation memory. The two have partially similar names, but their functions are completely different.

### Per-thread, but Not Necessarily Per-virtual-thread

In HotSpot, a TLAB is tied to the **execution thread context** that the allocator uses. With **virtual threads**, work can run across multiple carrier platform threads according to the scheduler. Therefore, **one must not rigidly claim** "each virtual thread has a single fixed TLAB for its entire lifetime." Such TLAB/OS-thread/carrier details are implementation-specific and may change across releases.

## 5. Fast Path Mechanism in a TLAB

Each typical TLAB has bounds/management fields such as `start`, `top`, and `end`. OpenJDK HotSpot keeps the related internal components in the `ThreadLocalAllocBuffer` code.

### Conceptual Allocation Path

~~~text
Java code: new SmallObject(...)
                  |
                  v
             allocation needed?
                  |
                  +-- No (optimized away via EA/scalar replacement)
                  |       -> no actual heap object allocated on this path
                  |
                  +-- Yes
                        |
                        v
                 TLAB fast path enabled?
                        |
             +----------+----------+
             |                     |
            Yes                    No
             |                     |
             v                     v
       aligned size fit?       collector/VM
             |                allocation path
       +-----+-----+
       |           |
      Yes          No
       |           |
       v           v
  bump TLAB top   refill TLAB
  init object     or outside-TLAB/slow path
  return ref          |
                      v
                enough memory?
                 |        |
                Yes      No
                 |        |
               init/ref   may GC/allocate
                          or throw OOME
~~~

It is necessary to distinguish the "allocation fast path" from the entire constructor. The allocator reserves memory and initializes object state per the contract; constructor code may execute complex logic, or even throw an exception. A slow constructor **does not prove** that bump-pointer allocation is slow.

### Pseudo-code Model

~~~text
allocateInTLAB(thread, objectSize):
    tlab = thread.currentTLAB
    size = align(objectSize)

    if tlab is usable and size <= tlab.end - tlab.top:
        address = tlab.top
        tlab.top = tlab.top + size
        prepare_memory_and_object_header(address, size)
        return address

    return slowAllocationPath(thread, size)
~~~

**The pseudo-code above intentionally omits JVM details.** In real HotSpot, allocation paths also include sampling/observability checks, zeroing, GC barriers, headroom reserve, and other conditions. `tlab.end` does not necessarily correspond to `allocation_end` in every implementation; do not memorize internal field layouts as a Java API contract.

### Why Is a Global Lock Not Needed for Every Object?

Only the **thread holding the TLAB** updates that TLAB's allocation pointer on the fast path, so consecutive bumps usually do not have to contend on the same global pointer with other threads. The VM still needs to coordinate to grant a **new TLAB**, reclaim unused portions, and manage the heap and GC.

Therefore, the accurate statement is:

> TLAB reduces contention **across many small allocations on the fast path**; it does not mean the application uses no synchronization at all or that allocation is always lock-free on every branch.

## 6. Full TLAB: Refill, Retire, Outside-TLAB, and Slow Path

A TLAB is not a bottomless box. Each allocation moves `top` closer to `end`. When there is not enough space for the next object, HotSpot may take several approaches:

1. **Refill TLAB**: request another suitable heap region, retire the old region, and continue allocating from the new buffer.
2. **Allocate outside TLAB**: for an object that is relatively large compared to the remaining free space / TLAB sizing calculation, the VM may allocate the object directly through the heap allocator instead of discarding a large amount of free space in the TLAB.
3. **Slow allocation path**: contact the collector, inspect allocation regions, coordinate allocation, attempt GC or another mechanism; if memory is still insufficient, it may end with **`OutOfMemoryError`**.
4. **TLAB resize**: HotSpot adjusts the desired TLAB size based on allocation profile and policy, rather than using a single fixed size across the entire application.

OpenJDK `ThreadLocalAllocBuffer` tracks the number of refills, outside-TLAB/slow allocations, and the amount of remaining space discarded when retiring a TLAB. This information helps analyze the trade-off between throughput and fragmentation/waste.

### Why Is Allocating Outside TLAB Sometimes More Efficient?

Suppose TLAB A has 48 bytes remaining, and a new object needs 256 bytes. If forced to retire the TLAB immediately, those 48 bytes might not be usable for another allocation inside that TLAB. Under certain conditions, the VM may allocate the **larger object outside the TLAB** and continue using the remaining space for smaller objects. The decision depends on the **refill waste limit** and HotSpot policy, not a Java statement that can choose directly.

~~~text
TLAB A:
+-------------------------+----------+
| allocated objects       | 48B free |
+-------------------------+----------+

Request 256B:
  Possible options:
  - outside-TLAB allocation, keep TLAB for small objects
  - retire/refill TLAB then allocate using new TLAB
  - slow path depending on collector, heap state, and policy
~~~

Do not interpret the example as a rule that "any object larger than 48B is always allocated outside the TLAB." This is only **one policy branch**. TLAB size, alignment, headroom, and GC allocation interfaces are more complex than the example.

### Where Does the Leftover TLAB Space Go?

When retiring a TLAB, there may be leftover space insufficient for the requested object. HotSpot needs to keep the heap **parsable** for the collector and heap walks; implementations may insert **filler/dummy objects** or adjust accounting accordingly. Unused space is recorded under the corresponding waste metrics.

TLAB waste is **not a Java memory leak** in the sense of references keeping objects alive indefinitely. It is an internal cost of the allocation partitioning strategy. The collector can reclaim/reuse the space at an appropriate time.

### Is TLAB Size Fixed for Every Thread?

**No.** HotSpot has parameters such as desired size, initial size, refills/alloc fraction, and alignment limits. The VM can automatically adjust according to each execution thread's **allocation rate**, workload, and GC policy. One must not conclude that every thread always holds an exact "1 MB TLAB" or that creating 1 million objects must cause exactly N refills.

## 7. Object Layout and the Actual Cost of an Allocation

An object needs more than field data. The allocated size typically involves:

- **Object header** and metadata needed by the runtime/GC.
- **Instance fields** and their arrangement/alignment.
- **Padding** to satisfy object alignment.
- For arrays: length information, elements, and padding.
- HotSpot choices such as compressed oops, compressed class pointers, compact object headers in supported releases, and address size.

~~~text
Conceptual illustration:

+--------------------+
| object header      |
+--------------------+
| field int x        |
| field int y        |
+--------------------+
| optional padding   |
+--------------------+

allocation size = aligned total bytes
~~~

Do not use a specific object size example as a rule for every JDK/architecture. For instance, the statement "`new Point(3,4)` is always 24 bytes" is incorrect if layout configurations differ. You can use specialized object layout analysis tools in an appropriate environment, but results are **implementation- and build-specific**.

**Zero initialization:** Java requires fields to have their proper default values before constructor code assigns values. HotSpot can achieve this via zeroed memory from TLAB refill, zeroing on the allocation path, or equivalent optimizations. One must not infer that bump pointer "only needs to add to an address and never needs to prepare memory/header."

## 8. TLAB and GC: Scope and Collector Matter Greatly

A common traditional HotSpot description is that each thread allocates most new objects in the **young generation/Eden** through a TLAB. However, **do not turn this picture into a law for every collector in every release**:

- Collectors manage the heap using different regions/spaces and fast allocation interfaces.
- Some large objects or objects with special conditions may go **outside TLAB**, into a special allocation region, or onto another path.
- A collector can move objects to another region while GC runs; an object does not "belong to a TLAB forever" after creation.
- Refilling a TLAB requires coordinating with the collector's allocation source; that can create GC pressure or trigger a GC request when the heap lacks space.

### A TLAB Is Not a "GC-Exempt" Region

An object allocated in a TLAB:

1. Is a **Java heap object** if materialized.
2. Can become unreachable once no live references remain.
3. Can be reclaimed or moved by GC depending on the collector.
4. Can be accessed from another thread if the reference is shared according to the JMM.

Fast allocation via TLAB does **not** make an object belong to a "stack-local heap that is never scanned." The collector still must ensure correctness of the object graph, roots, barriers, and metadata.

### TLAB and ThreadLocal Are Different

| Concept | TLB? | Purpose | Can the object be shared? |
| --- | --- | --- | --- |
| **TLAB** | Not CPU TLB | Optimizes **heap allocation** per thread context | **Yes**, once the reference is shared |
| **`ThreadLocal<T>`** | Not TLAB | Stores **values tied to a Java thread** across calls | The value is still a Java object and can escape |
| **CPU TLB (Translation Lookaside Buffer)** | MMU hardware | Caches virtual → physical address mappings | Not a Java allocation mechanism |
| **JVM stack** | Not heap TLAB | Chain of frames, locals/operand stacks | Frames are private per thread |

Because the abbreviations look similar, read them out in full: **Thread-Local Allocation Buffer** is different from the CPU's **Translation Lookaside Buffer**.

## 9. Escape Analysis: Seeing `new` Does Not Always Mean an Allocation

The JIT compiler can analyze whether an object **escapes a method/thread** and can replace the object with individual field values (**scalar replacement**) or eliminate the allocation operation when a materialized object is not needed.

Example (illustrative method snippet):

~~~java
static int compute(int input) {
    Point point = new Point(input, input + 1);
    return point.x + point.y;
}
~~~

If there is no observable escape, the JIT can transform the execution path into equivalent arithmetic:

~~~text
compute(input):
    result = input + (input + 1)
    return result
~~~

At the **`javap` bytecode** level, `new Point` may still appear. At the optimized machine code level, the allocation **may not exist**. However, this is an **optimization possibility**, not a guarantee that the JIT always eliminates every allocation of a non-escaping object.

**Specifically on HotSpot:** Oracle's performance documentation describes scalar replacement as an optimization that eliminates heap allocation; **one should not claim HotSpot by default "moves all non-escaping objects onto the stack."** Escape analysis can help eliminate the allocation completely; if it still needs to be materialized, the allocator may use a TLAB or another path.

### Distinguishing JIT Results from Source Interpretation

| Source | HotSpot optimization possibility | Not guaranteed |
| --- | --- | --- |
| `new Point(a,b)` only reads fields then returns sum | Scalar replacement/allocation elimination | Every call is JIT-compiled immediately |
| `new Point(a,b)` and returns reference outward | May need to materialize object | Always allocated in TLAB; may take another path |
| `new HugeArray[...]` | May allocate outside TLAB/large-object path | Every array goes into TLAB |
| `new Foo()` in a loop | May be many allocations or optimized away | Number of source `new` = exact number of TLAB allocations |

## 10. Java 17+ Program: Allocating from Two Threads

The example below helps distinguish **objects on the shared heap** from **thread-local allocation rights**. It has deterministic output and does **not** require accessing internal TLAB structures.

Create file **`AllocationLab.java`**:

~~~java
public class AllocationLab {
    static final class Item {
        final int number;

        Item(int number) {
            this.number = number;
        }
    }

    private static long buildAndSum(int start) {
        Item[] items = new Item[2_000];

        for (int i = 0; i < items.length; i++) {
            items[i] = new Item(start + i);
        }

        long total = 0;
        for (Item item : items) {
            total += item.number;
        }
        return total;
    }

    public static void main(String[] args) throws InterruptedException {
        long[] result = new long[2];

        Thread first = new Thread(() -> result[0] = buildAndSum(0));
        Thread second = new Thread(() -> result[1] = buildAndSum(2_000));

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("first=" + result[0]);
        System.out.println("second=" + result[1]);
        System.out.println("sum=" + (result[0] + result[1]));
    }
}
~~~

Compile and run:

~~~bash
javac -g AllocationLab.java
java AllocationLab
~~~

**Exact stdout when the program runs normally:**

~~~text
first=1999000
second=5999000
sum=7998000
~~~

Explanation:

- The first thread sums integers 0..1999: `(0 + 1999) * 2000 / 2 = 1_999_000`.
- The second thread sums 2000..3999: `(2000 + 3999) * 2000 / 2 = 5_999_000`.
- Main `join`s both threads before reading `result[]`; thus output order depends only on main, and the workers' writes have completed.
- `Item[]` and each `Item` have **heap object semantics**. In HotSpot, TLAB may optimize many of these allocations, but **stdout does not measure TLAB refills or bytes allocated**.
- Nor should one infer that every `new Item` actually creates an independent allocation: JIT optimization depends on code shape and execution profile.

### Comparing Runs with TLAB Enabled and Disabled

On HotSpot (if the JVM build supports these flags), try:

~~~bash
java -XX:+UseTLAB AllocationLab
java -XX:-UseTLAB AllocationLab
~~~

Both runs must preserve **program semantics** and print the exact same three lines of values mentioned above under normal execution. However:

- Execution time differences **do not necessarily reflect TLAB benefits**, because a small program is affected by JIT warmup, startup, scheduling, and escape analysis.
- `-XX:-UseTLAB` only changes the allocation strategy; it does **not** change the fact that objects belong to the Java heap.
- Do not use the program's pass/fail output to claim which collector path HotSpot chose for each object.

For serious benchmarking, use **JMH**, prepare warmup/forks, control GC, allocation rate, hardware, and profiling. Do not draw performance conclusions from a single manual timing measurement.

## 11. A Second Example: JIT Can Eliminate Allocation of a Non-Escaping Object

Create file **`ScalarCandidate.java`**:

~~~java
public class ScalarCandidate {
    static final class Pair {
        final int left;
        final int right;

        Pair(int left, int right) {
            this.left = left;
            this.right = right;
        }
    }

    static int compute(int value) {
        Pair pair = new Pair(value, value + 1);
        return pair.left + pair.right;
    }

    public static void main(String[] args) {
        System.out.println("result=" + compute(7));
    }
}
~~~

~~~bash
javac ScalarCandidate.java
java ScalarCandidate
javap -c -p ScalarCandidate
~~~

**Program stdout (excluding `javap` output):**

~~~text
result=15
~~~

`javap` may still display the bytecode `new ScalarCandidate$Pair` inside `compute`. However, when the method is "hot" enough for JIT optimization, the compiler **may** scalar-replace `Pair` and eliminate the allocation in machine code.

**You cannot prove scalar replacement solely from the `result=15` output or from `javap -c`**. To measure actual allocations, you need a profiler, JFR, or appropriately configured tooling and to examine the compilation state. Do not claim this simple method is guaranteed to be optimized after a single call.

## 12. Observing TLAB with HotSpot Flags and Unified Logging

Modern Oracle JDK/HotSpot supports:

| Flag or tool | Purpose | Notes |
| --- | --- | --- |
| `-XX:+UseTLAB` | Enables Thread-Local Allocation Buffers | On HotSpot, usually **enabled by default** |
| `-XX:-UseTLAB` | Disables this mechanism for comparison/investigation | Can make allocation slower; not a recommended default production configuration |
| `-Xlog:gc+tlab=trace` | Requests detailed logging of TLAB events/statistics if the tag/level is supported by the JVM | Output depends on collector, workload, version; very verbose logs |
| `-Xlog:gc+tlab=debug` | Requests a less detailed log level | No log lines guaranteed if no corresponding GC event/checkpoint occurs |
| `-XX:+PrintFlagsFinal` | Lists HotSpot flags and current values | Does not measure specific allocations |
| **JFR** | Collects allocation events depending on configuration | Event selection/sampling must be understood properly; does not count every single object by default |
| **JMH** | Benchmarks the JVM with warmup/forks | Does not measure TLAB directly from a single ns/op number |

Commands to try on HotSpot JDK 17+:

~~~bash
java -Xlog:help
java -XX:+PrintFlagsFinal -version
java -Xlog:gc+tlab=trace AllocationLab
~~~

**Note:** flags/logging are not portable APIs of the Java language. On non-HotSpot JVMs, the commands may be rejected. When `-Xlog:gc+tlab=trace` produces a lot of output, do not confuse diagnostic logs with the program's three lines of stdout.

To filter `UseTLAB` in the terminal:

~~~bash
# Linux/macOS shell:
java -XX:+PrintFlagsFinal -version 2>&1 | grep UseTLAB
~~~

PowerShell/Windows:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 | Select-String "UseTLAB"
~~~

### Interpreting TLAB Statistics

Depending on the HotSpot version, `gc+tlab` logs may mention:

- **Refills**: how many times a TLAB needed to be replaced.
- **Slow allocs**: allocations that needed the slow branch according to how the VM tracks statistics.
- **Refill waste**: remaining capacity discarded when a TLAB is retired/refilled.
- **GC waste**: unused space when GC collects statistics/closes the appropriate TLAB.
- **Desired size**: the TLAB capacity the VM is targeting according to policy.

Do not infer that a line `refills: 3` means the JVM created only **three objects**. Each TLAB holds many allocations, and outside TLAB there may be other paths. TLAB statistics may also be printed **per GC/event** rather than as a single process-lifetime total, and JIT elimination can reduce observed allocations.

### JFR and Allocation Events

Java Flight Recorder has allocation-related event names, such as **`jdk.ObjectAllocationInNewTLAB`** and **`jdk.ObjectAllocationOutsideTLAB`** on supported JDK builds. Recording configuration determines which events are enabled and what sampling or threshold applies. Do not interpret the event count as "exactly equal to the number of source `new` expressions executed" without checking the settings.

One option to explore event support:

~~~bash
jfr help
java -XX:StartFlightRecording=duration=10s,filename=allocation.jfr AllocationLab
~~~

**With `AllocationLab` running so briefly**, a 10-second recording may not have a long enough workload to observe many allocation samples. This command only illustrates how to enable recording on a JDK with JFR; it does not guarantee that all allocation event types are automatically captured and should not be used to conclude TLAB size. Use a sufficiently long/warmed-up workload and appropriate event configuration when doing actual profiling.

## 13. When Does the Fast Path Not Represent All Allocations?

Conditions that can cause an allocation **not** to go through the fast bump pointer in a TLAB:

1. **Object is too large** or does not fit the TLAB size/refill policy.
2. **TLAB has insufficient space**, requiring refill/retire.
3. **Collector-specific slow path**: allocation region unavailable, requiring GC/refill coordination or allocation outside the default region.
4. **Instrumentation/profiling**: JVMTI/JFR sampling and observability requirements can affect the allocation path.
5. **Not yet JIT-compiled or deoptimized**: interpreter, C1, and C2 may have different execution paths.
6. **Escape analysis eliminates the allocation**: when no actual allocation remains, "fast vs slow" no longer applies to that object.
7. **VM flags**: `UseTLAB` disabled or other collector policies.

Do not conclude from the remaining free bytes of a TLAB that "the heap has no memory left." A TLAB can run out of space while the overall heap still has plenty of capacity; refilling obtains a new buffer from a suitable heap portion. Conversely, having a few bytes left in a TLAB does not guarantee the JVM can accommodate a very large object.

## 14. HotSpot's "Pointer" Is Not a Java Code Pointer

The bump pointer `top` is an address/offset that **the VM allocator manages internally**. Java source code does not have pointer arithmetic operators like C/C++. Java references are typed values with operations valid under the JVM, and may undergo GC relocation/barriers.

Observe:

~~~java
Object a = new Object();
Object b = new Object();
System.out.println(a == b);
~~~

When placed in a program with `main`, this line prints `false` because two `new Object()` calls create two distinct identities under Java semantics, even though the VM may optimize in specific cases without changing the result. **Do not infer address distance between a and b** from `==`. Nor should you read `System.identityHashCode` and treat it as a memory address.

### TLAB Does Not Break the Java Memory Model

If Thread A creates and publishes an object to Thread B:

~~~text
Thread A:
  - allocate object (possibly via TLAB A)
  - initialize fields
  - publish reference via a thread-safe mechanism

Thread B:
  - receive reference
  - access the same object
~~~

TLAB only optimizes **where the initial allocation happens**. It does not allow B to automatically read fields written by A if publication/synchronization does not follow the rules. Use `volatile`, `synchronized`, concurrent collections, final field semantics, or appropriate happens-before mechanisms.

Nor does TLAB guarantee that an object is only allowed to be used from the allocating thread; the Java heap is **shared among all JVM threads**, per JVMS `2.5.3.

## 15. Practical Optimization: When Should You Pay Attention to TLAB?

Worthwhile questions before intervening with VM flags:

- Is the allocation rate genuinely high? Where is the bottleneck: GC pauses, object churn, or CPU?
- Are there large objects or many small objects? Are there bursty allocation patterns across threads?
- Does profiling show significant TLAB refill/waste or outside-TLAB allocations?
- Has the JIT warmed up, and has the allocation been scalar-replaced?
- Do the Java version, GC, and host architecture match the benchmark assumptions?
- Is the real issue allocation throughput, GC memory pressure, or synchronization on a shared object?

**You should not automatically disable TLAB when seeing a bit of "waste."** The typical trade-off is: giving each thread a private allocation region to avoid contention, in exchange for possible unused tail space/refill overhead. Actual effectiveness must be evaluated with a real workload, not a single metric.

### Comparison Model

| Allocation via TLAB fast path | Allocation outside TLAB / slow path |
| --- | --- |
| Per-execution-thread region has enough space | TLAB out of space, large object, TLAB disabled, or other policy |
| Local bump pointer, usually low contention | May require coordination/CAS, refill, collector-specific logic |
| Fast path can be aggressively inlined | Usually more checks and bookkeeping |
| Still requires object initialization and GC correctness | Must also comply with object initialization and GC correctness |
| Still an object on the Java heap | **Also an object on the Java heap** |

Do not interpret the table as a fixed speed measurement, such as "TLAB is always N times faster"; JDK, collector, CPU, object sizes, and contention all have an impact.

## 16. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "TLAB is part of a thread's JVM stack." | TLAB is a **buffer in the Java heap** reserved for an execution thread context to allocate. |
| "An object allocated in a TLAB cannot be accessed by another thread." | The reference can still be shared and the object accessed according to the Java Memory Model. |
| "`ThreadLocal<T>` uses TLAB to hold private values." | `ThreadLocal` is a per-Java-thread value API, not synonymous with TLAB. |
| "TLAB is CPU TLB." | TLAB = Thread-Local Allocation Buffer; CPU TLB is Translation Lookaside Buffer. |
| "TLAB means every `new` needs no synchronization on any branch." | TLAB fast path reduces contention; refill/slow path/GC still require coordination. |
| "Whenever a TLAB is full, the JVM is out of heap." | It can refill from the heap when memory sources remain. |
| "Large objects always reside in TLAB." | They can be allocated outside TLAB or via another path. |
| "TLAB only allocates objects in young Eden across every JVM and every GC." | Different collectors have different policies/regions; not a JVMS rule. |
| "TLAB size is fixed for all threads." | HotSpot has adaptive sizing and thresholds. |
| "Bump pointer only increments `top`; there is no object header/zeroing." | Valid allocation also includes preparation/header/alignment and GC requirements. |
| "Seeing `new` in `javap` guarantees there is a heap allocation." | JIT may scalar-replace or eliminate allocations. |
| "HotSpot escape analysis moves all non-escaping objects onto the stack." | HotSpot typically uses scalar replacement to eliminate allocation; it does not promise general stack allocation. |
| "Disabling TLAB changes Java source output." | `-XX:-UseTLAB` changes allocation strategy, not Java semantics. |
| "A single `System.nanoTime` measurement tells how much TLAB helps." | Must account for warmup, JIT, GC, benchmark framework, and workload. |
| "`System.identityHashCode` is the object's address after allocation." | No; identity hash is not a native address. |
| "A virtual thread always keeps a single unchanging private TLAB." | The mechanism ties to execution/carrier threads depending on HotSpot; should not be absolutized. |
| "TLAB waste is an un-GC-able memory leak." | It is typically internal allocation fragmentation/accounting, not equivalent to a Java reference leak. |
| "Bump pointer exists in the JVMS as an opcode." | No; it is an implementation detail beneath the `new` bytecode. |

## 17. Self-Check Questions

**Question 1.** Does TLAB belong to the JVM stack or heap?  
**Answer:** It belongs to the **Java heap** under HotSpot's allocation strategy; it is a region **temporarily used by a thread to allocate objects**, not the call stack.

**Question 2.** What two key pieces of information does the bump-pointer fast path need?  
**Answer:** The current position `top` and the limit `end`, along with the object's aligned size to check if enough space remains and update `top`.

**Question 3.** Why does TLAB reduce contention in multithreading?  
**Answer:** Threads use local allocation pointers for many small objects, instead of contending on a single global pointer for every object.

**Question 4.** When a TLAB has 48B left and an object needs 256B, is the VM guaranteed to throw OOME?  
**Answer:** No. The VM can refill the TLAB or allocate outside the TLAB if the heap has a suitable allocation source.

**Question 5.** Can an object allocated from TLAB A be shared with Thread B?  
**Answer:** Yes. The object belongs to the Java heap; proper JMM publication/synchronization is needed to ensure visibility and safety when sharing mutable data.

**Question 6.** Does every `new` always go through TLAB?  
**Answer:** No. There is outside-TLAB allocation, slow path, TLAB disabled, or the JIT may eliminate the allocation.

**Question 7.** Why does `javap -c` not prove TLAB allocation is being used?  
**Answer:** `javap` displays JVM bytecode, not the internal allocation path in HotSpot/JIT machine code.

**Question 8.** Can the interpreter or compiler call the Java constructor before memory for the object has been validly allocated?  
**Answer:** The constructor can only run after the object has been created/prepared appropriately per semantics; allocation and constructor invocation are distinct steps.

**Question 9.** Is `UseTLAB` a JVMS requirement for every JVM implementation?  
**Answer:** No. It is a HotSpot flag/technique; other JVMs may choose different allocators.

**Question 10.** Does `ScalarCandidate.compute(7)` always create a real `Pair` object?  
**Answer:** Cannot be guaranteed: the JIT may scalar-replace it if conditions are met, but may also create the object depending on compilation state.

**Question 11.** Does JFR recording 100 allocation events mean the source executed only 100 `new` expressions?  
**Answer:** No. Event configuration/sampling and allocation elimination mean the event count is not synonymous with the number of `new` expressions executed.

**Question 12.** Should `-XX:-UseTLAB` be changed in production just because some refill waste is observed?  
**Answer:** No. Real workload, GC, throughput, and contention must be measured before intervening in allocation policy.

## 18. Official Sources for Deeper Study

- [JVMS Java SE 25 — `2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): Java heap holds shared instances/arrays, does not prescribe the TLAB allocation algorithm.
- [JVMS Java SE 25 — `6.5 Instructions](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-6.html): opcodes `new`, `newarray`, `anewarray` and JVM instruction/initialization semantics.
- [Oracle JDK 25 — `java` launcher command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): documented HotSpot flags `-XX:+UseTLAB` and `-XX:-UseTLAB`.
- [OpenJDK HotSpot — `threadLocalAllocBuffer.hpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/threadLocalAllocBuffer.hpp): TLAB internal interface and state.
- [OpenJDK HotSpot — `threadLocalAllocBuffer.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/threadLocalAllocBuffer.cpp): refill, resize, accounting, waste, and logging.
- [OpenJDK HotSpot — `memAllocator.cpp`](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/shared/memAllocator.cpp): inside/outside TLAB allocation paths, slow path.
- [Oracle — Memory Management in Java HotSpot VM](https://www.oracle.com/technetwork/java/javase/tech/memorymanagement-whitepaper-1-150020.pdf): historical explanation of bump-pointer allocation and why TLAB reduces contention; collector details in the old whitepaper should not be treated as the current state of every JDK.
- [Oracle — Java HotSpot VM Performance Enhancements](https://docs.oracle.com/en/java/javase/22/vm/java-hotspot-virtual-machine-performance-enhancements.html): escape analysis and scalar replacement, allocation optimizations.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): JVM benchmarking framework with proper warmup/forks methodology.
- [JDK 25 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/25/jfapi/): flight recording tool and API, observing events when enabled.

**One-sentence summary:** HotSpot typically allocates objects quickly using a **bump pointer in a TLAB — a slice of the heap granted to an execution thread**, so most small allocations do not have to contend on a global allocation pointer; when space runs out or conditions are not met, the VM switches to refill/outside-TLAB/slow path, while GC, object initialization, and the Java Memory Model must still be respected.