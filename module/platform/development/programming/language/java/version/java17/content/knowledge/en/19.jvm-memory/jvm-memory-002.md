# Object Allocation, Reachability, and Garbage Collection in Java 17

Java manages most of an object's memory lifecycle automatically: the program creates objects, the JVM allocates appropriate memory, and the garbage collector (GC) reclaims memory when objects are no longer reachable under Java's rules. However, "having a garbage collector" does not mean an application cannot run out of memory or retain objects for too long.

To understand how the JVM manages memory, you need to connect three concepts:

1. **Object allocation:** how objects are created and how memory is reserved for them.
2. **Reachability:** which references are still keeping an object alive.
3. **Garbage collection:** how the JVM identifies and reclaims memory from objects that are no longer reachable.

This lesson explains the heap and stack model, how objects are allocated, GC roots, reachability levels, Java reference types, modern collectors available in Java 17, and how to diagnose memory behavior.

## 1. Where are objects stored?

A Java program can create many objects:

~~~java
Customer customer = new Customer("C-100");
Order order = new Order(customer);
~~~

The variables `customer` and `order` are reference variables. They allow the program to access the corresponding objects. In the JVM memory model, objects and arrays are allocated on the **heap**. Local variables and method call frames are managed on each thread's **Java stack**.

You can picture it simply:

~~~text
Thread A - Java stack                 Heap
┌─────────────────────────┐       ┌──────────────────────┐
│ main's frame            │       │ Customer object      │
│ customer ───────────────┼──────>│ id = "C-100"         │
│ order ──────────────────┼───┐   └──────────────────────┘
└─────────────────────────┘   │
                              │   ┌──────────────────────┐
                              └──>│ Order object         │
                                  │ customer ─────────────┼───┐
                                  └──────────────────────┘   │
                                                            │
                                  ┌──────────────────────┐   │
                                  │ Customer object      │<──┘
                                  └──────────────────────┘
~~~

The diagram only illustrates logical relationships. The JVM can optimize how objects are represented at runtime; you should not infer that every reference variable always corresponds to a fixed memory slot as drawn.

### 1.1. Java stack

Each Java thread has its own stack. When invoking a method, the JVM creates a stack frame to hold data for that call, for example:

- local variables;
- operands and intermediate results of bytecode;
- information supporting method return and exception handling.

When the method finishes, the corresponding frame is removed from the stack. That can remove the references in the frame from the active set of references.

~~~java
static void process() {
    Customer customer = new Customer("C-200");
    System.out.println(customer.id());
}
~~~

The local variable `customer` belongs to the execution scope of the method. The `Customer` object is allocated under the heap model; when the method finishes and no other reference path to the object remains, the object can become eligible for GC reclamation.

You should not say that "the object is automatically deleted the moment the local variable goes out of scope." GC does not guarantee it will run at that instant. What matters is whether the object is still reachable.

### 1.2. Heap

The heap is a runtime memory area used to allocate objects and arrays. Threads can access the same object on the heap if they hold a reference to it.

The heap is typically divided into areas or regions depending on the garbage collector. With generational collectors, the heap is also organized by generations to take advantage of the observation that many objects are short-lived.

Objects can reference one another, forming an object graph. GC does not inspect a single variable in isolation; it evaluates reachability from starting points that the JVM treats as GC roots.

### 1.3. The stack is not the default storage for all objects

In code:

~~~java
int count = 10;
Customer customer = new Customer("C-300");
~~~

`count` is a primitive-type variable. `customer` is a reference variable. The object created by `new Customer(...)` belongs to Java's heap model.

The JIT compiler can optimize certain allocations using escape analysis and scalar replacement. In that case, the JVM may eliminate physical object creation if unnecessary, or replace the object with individual values in the optimized machine code. This is a runtime optimization; programmers should not rely on an assumption that objects will always be stack-allocated.

## 2. How does object allocation happen?

When executing `new`, the program requests creation of an object of a class:

~~~java
Invoice invoice = new Invoice("INV-001", 250_000);
~~~

Conceptually, the process includes:

1. The JVM ensures the class is loaded and initialized as required.
2. The JVM reserves enough memory for the object according to its runtime layout.
3. Instance fields receive default values according to their data types.
4. The constructor and constructor chain execute to initialize the object.
5. A reference to the object is returned by the `new` expression.

Default values include `0` for integer types, `0.0` for floating-point types, `false` for boolean, and `null` for reference fields. The constructor can assign different values.

~~~java
class Account {
    int balance;          // default 0
    boolean active;       // default false
    String owner;         // default null

    Account(String owner) {
        this.owner = owner;
        this.active = true;
    }
}
~~~

You cannot read an uninitialized instance field by relying on "garbage values" as in some manually managed memory languages. Java guarantees that instance fields are initialized to default values before the constructor executes its initialization logic.

### 2.1. Thread-Local Allocation Buffer (TLAB)

In the HotSpot JVM, a common technique to speed up object allocation is the **Thread-Local Allocation Buffer (TLAB)**. Each thread can be given a small region in the heap for its own object allocations.

Instead of every object creation contending on a global allocation pointer, a thread can reserve space from its own TLAB at very low cost. When a TLAB runs out of space, the JVM can allocate a new TLAB or use another allocation path.

~~~text
Heap
┌──────────────────────────────────────────────┐
│ Thread A's TLAB   │ Thread B's TLAB          │
│ obj obj obj       │ obj obj                  │
│                   │                          │
│ remaining heap / regions managed by GC       │
└──────────────────────────────────────────────┘
~~~

TLAB is a JVM implementation detail, not a Java language rule. You do not manage TLABs in application code. Creating small objects is usually cheap; what matters more is avoiding excessive allocation on hot paths if profiling shows significant GC pressure.

### 2.2. Escape analysis and scalar replacement

The JIT compiler can analyze whether an object "escapes" its local usage scope. If the object does not escape and optimization conditions are met, the JVM can:

- eliminate the physical allocation;
- replace the object's fields with scalar values;
- eliminate certain synchronization operations on the non-escaping object.

Example:

~~~java
static int calculate() {
    Point point = new Point(3, 4);
    return point.x() + point.y();
}
~~~

If `Point` is not returned, stored in a field, or passed to code that could retain it, the JIT can optimize away the object creation in some situations.

This optimization depends on the runtime, JVM version, execution profile, and code shape. You should not write convoluted code just to force escape analysis to kick in. Write clear code first, then use a profiler to identify which allocations are genuinely costly.

## 3. Object graph and GC roots

An object remains reachable if there is a reference path from a **GC root** to that object. GC roots are the starting points that the garbage collector examines when determining which objects are still reachable.

Common types of GC roots in the JVM include:

- references in stack frames of active threads;
- references to objects in static fields of live classes;
- JNI references held by native code;
- certain internal JVM references, such as objects associated with running threads or class loaders.

The exact list and implementation depend on the JVM. The key idea is that GC starts from these roots and follows strong references through the object graph.

~~~text
GC roots
   │
   ├── static field ───────> Cache ───────> Entry
   │
   ├── thread stack ───────> Request ─────> Customer
   │
   └── JNI reference ──────> NativeBridge

Object with no path from any root
   └── can become unreachable
~~~

### 3.1. Example of a still-reachable object

~~~java
class Application {
    private static final List<String> CACHE = new ArrayList<>();

    static void remember(String value) {
        CACHE.add(value);
    }
}
~~~

Elements in `CACHE` are held by a static field. As long as the class and that field remain reachable through the class loader lifecycle, the elements remain reachable. If the cache grows without bound, memory can grow even though the application no longer needs old values.

### 3.2. Object no longer reachable

~~~java
Customer customer = new Customer("C-400");
customer = null;
~~~

If no other references point to the original object, it is no longer reachable from `customer`. It can be reclaimed by GC in a subsequent collection cycle.

Assigning `null` is not something you need to do routinely to free memory. When a variable goes out of scope or is reassigned to another object, the old reference is no longer held. Only assign `null` when it makes logical sense or helps shorten a reference's lifetime in a specific, measured scenario.

### 3.3. Reference cycles can still be collected

A common misconception is that two objects referencing each other will not be collected by GC:

~~~java
class Node {
    Node next;
}

Node first = new Node();
Node second = new Node();
first.next = second;
second.next = first;

first = null;
second = null;
~~~

If no reference path remains from GC roots to either node, the entire cycle is unreachable and can be collected. Modern GCs do not merely count references; they determine reachability from roots.

## 4. Reachability levels in Java

Java defines reachability states that are meaningful to the `java.lang.ref` API:

| State | General meaning |
| --- | --- |
| Strongly reachable | Reachable via ordinary reference paths from a GC root without passing through any special reference object. |
| Softly reachable | Not strongly reachable, but reachable through one or more SoftReferences. |
| Weakly reachable | Not strongly or softly reachable, but reachable through a WeakReference. |
| Phantom reachable | No longer strongly, softly, or weakly reachable; the object is in a state appropriate for phantom references after related lifecycle steps. |
| Unreachable | Not reachable under any of the levels above. |

These levels govern how the JVM handles different kinds of references. In ordinary application code, objects kept alive by strong references are the most common case.

### 4.1. Strong reference

Every ordinary reference assignment creates a strong reference relationship:

~~~java
Customer customer = new Customer("C-500");
Customer another = customer;
~~~

Both variables point to the same object. The object remains strongly reachable as long as at least one strong reference path from a root exists.

Java has no separate syntax named `StrongReference`; this term distinguishes ordinary references from SoftReference, WeakReference, and PhantomReference.

### 4.2. SoftReference

`SoftReference<T>` holds a soft reference to an object. When an object is no longer strongly reachable but is softly reachable, GC may decide to clear soft references to reclaim the object when memory is needed.

~~~java
import java.lang.ref.SoftReference;

byte[] imageData = loadImage();
SoftReference<byte[]> cachedImage = new SoftReference<>(imageData);

imageData = null;

byte[] value = cachedImage.get();
if (value == null) {
    value = loadImage();
    cachedImage = new SoftReference<>(value);
}
~~~

Once an object is only softly reachable, `get()` may return `null` if GC has cleared the reference. Therefore, code must always handle the case where the object is no longer in the cache.

You should not treat SoftReference as a cache mechanism with a predictable eviction policy. Clearing timing depends on GC and memory pressure; the application cannot precisely control how long the cache retains an object. For production caches, usually prefer a cache with explicit size bounds, time-to-live, and eviction policies.

### 4.3. WeakReference

`WeakReference<T>` does not keep an object alive across GC. If an object has no strong or soft references holding it, GC can clear weak references and the object can be collected.

~~~java
import java.lang.ref.WeakReference;

Customer customer = new Customer("C-600");
WeakReference<Customer> weak = new WeakReference<>(customer);

System.out.println(weak.get() != null); // true while a strong reference still holds the object

customer = null;
// From here GC may collect the object; the exact timing is not guaranteed.
~~~

`weak.get()` returns the object if the referent still exists, or `null` if the reference has been cleared. Never write logic that requires the object to remain alive after dropping strong references.

Weak references can be useful for certain registries, metadata, or associative structures where you do not want to keep the object alive. However, they do not replace an explicit lifecycle management policy.

### 4.4. WeakHashMap

`WeakHashMap<K,V>` holds keys via weak references. When a key is no longer strongly referenced elsewhere, its entry can be removed during reference processing.

~~~java
Map<Object, String> metadata = new WeakHashMap<>();

Object key = new Object();
metadata.put(key, "metadata");

System.out.println(metadata.get(key)); // metadata
key = null;
// The entry may disappear after GC processes the weak reference.
~~~

Do not assume the entry will disappear immediately after `key = null`. Collection and entry cleanup occur at non-deterministic times.

A common trap: if the value holds a strong reference back to the key, the key can remain reachable through the value inside the map, preventing the entry from being collected as expected. Examine the entire reference graph, not just the collection type.

### 4.5. PhantomReference and ReferenceQueue

`PhantomReference<T>` exists to detect when an object has reached the phantom-reachable state so post-mortem actions can be performed. `get()` on a phantom reference always returns `null`; it is never used to retrieve the object.

~~~java
import java.lang.ref.PhantomReference;
import java.lang.ref.ReferenceQueue;

ReferenceQueue<ResourceOwner> queue = new ReferenceQueue<>();
ResourceOwner owner = new ResourceOwner();
PhantomReference<ResourceOwner> phantom =
        new PhantomReference<>(owner, queue);
~~~

When GC processes the reference and enqueues the phantom reference, the application can poll the queue and perform appropriate cleanup. In real code, you must manage the queue and reference lifecycle carefully; a phantom reference itself does not automatically close files, sockets, or native handles.

Phantom references are a low-level API. For off-heap resource cleanup, prefer `AutoCloseable` and try-with-resources; `Cleaner` can serve as a fallback mechanism when specifically needed.

## 5. When does an object become eligible for GC?

An object becomes eligible for GC reclamation when it is no longer reachable under Java's rules, taking special reference levels into account. That does not mean the memory is reclaimed immediately.

Example:

~~~java
static void createTemporaryObject() {
    byte[] buffer = new byte[10_000_000];
    // Process buffer.
}

public static void main(String[] args) {
    createTemporaryObject();
    // buffer is no longer in createTemporaryObject's frame.
    // The object can become eligible for GC if no other references remain.
}
~~~

GC may run later when the JVM deems it appropriate. If the heap still has enough space, the JVM may not collect right away. Consequently:

- You cannot rely on GC to trigger a business action at a specific time.
- You cannot rely on GC to close sockets or files on time.
- You should not use `System.gc()` to control when objects are reclaimed.

### 5.1. System.gc() is not a mandatory free command

~~~java
System.gc();
~~~

This call only suggests that the JVM consider running garbage collection. The JVM may ignore it, delay it, or handle it according to runtime policy; the `-XX:+DisableExplicitGC` flag can even disable explicit GC requests.

Do not call `System.gc()` in application logic to "fix" memory leaks or ensure an object is gone. Fix the reference paths retaining the object and size/investigate the heap based on measured data.

## 6. How does the garbage collector collect memory?

Modern GCs are typically based on reachability tracing: starting from GC roots, following references to mark live objects; unmarked objects can be reclaimed. Depending on the collector, the process may include:

- mark: identify objects that are still reachable;
- sweep: reclaim memory occupied by dead objects;
- compact: move live objects to reduce fragmentation;
- copy/evacuate: move live objects to another memory area.

Not every collector performs every step in the same way or in the same phase. This is a conceptual model to understand GC, not an exact description of every JVM's algorithms.

### 6.1. Stop-the-world pause

Some GC phases need to pause application threads so the JVM can perform work consistently. That pause is commonly called a **stop-the-world (STW) pause**.

~~~text
Time ───────────────────────────────────────────────>
Application threads:  run run run | pause | run run
GC work:                   prepare |  GC   | resume
~~~

Modern collectors strive to reduce pause duration and/or frequency, but no general-purpose collector guarantees the application will never pause. Throughput, latency, and footprint goals involve trade-offs.

### 6.2. Generational collection

Many collectors leverage the generational hypothesis: most newly created objects have short lifetimes. The heap is divided into areas representing young objects and longer-lived objects.

Classic generational model:

~~~text
Young generation
┌─────────────────────────────────┐
│ Eden │ Survivor 0 │ Survivor 1  │
└─────────────────────────────────┘
                  │ objects surviving multiple collections
                  v
Old generation
┌─────────────────────────────────┐
│ longer-lived retained objects   │
└─────────────────────────────────┘
~~~

New objects are usually allocated in an area for young objects. During a young collection, surviving objects are kept or moved; objects surviving multiple cycles can be promoted to an area for long-lived objects.

This is a useful model for understanding G1 and generational collectors. The exact physical organization varies by collector; do not assume every Java 17 collector has the exact Eden/Survivor/Old areas shown in the diagram.

### 6.3. Allocation rate and live set

Two metrics to distinguish:

- **Allocation rate:** the rate at which the program creates new objects.
- **Live set:** the volume of objects still reachable after GC has reclaimed dead objects.

A high allocation rate can cause GC to run frequently even when the live set is small. Conversely, a large live set means each GC cycle must process many live objects and increases heap pressure.

If a program creates many short-lived objects, inspect the allocation profile. If the heap grows steadily and the live set does not drop after GC cycles, investigate reference paths retaining objects longer than expected.

## 7. Garbage collectors available in Java 17

Java 17 offers several collectors to choose from. Each has different goals; availability can depend on the JVM distribution and platform.

| Collector | General characteristics | Typical considerations |
| --- | --- | --- |
| Serial GC | Collects primarily with a single GC thread; simple, low footprint, though pauses can be long on large heaps. | Small applications, resource-constrained environments. |
| Parallel GC | Uses multiple threads to speed up GC work and optimize throughput. | Batch jobs or workloads prioritizing total work completed. |
| G1 GC | Region-based generational collector balancing throughput and pauses; default collector on common Java 17 server-class configurations. | General-purpose server applications, medium to large heaps. |
| ZGC | Low-latency collector performing most work concurrently with the application; production-ready in Java 17. | Workloads requiring short pauses with sufficient resources for the collector. |
| Shenandoah | Low-latency collector with mostly concurrent collection work; availability depends on JVM distribution. | Latency-sensitive applications on a supported runtime. |

There is no single "fastest" choice for every workload. Measure pause times, throughput, heap occupancy, allocation rate, and GC CPU usage in a production-like environment.

### 7.1. G1 GC

G1 divides the heap into many regions of roughly uniform size. Regions can be used for young objects, long-lived objects, or other GC purposes. G1 prioritizes collecting regions with high reclaimable garbage to meet the configured pause target.

Characteristics:

- has young collection and mixed collection cycles;
- performs some marking work concurrently with the application;
- can select regions based on expected reclaimable memory;
- strives to meet a pause goal, though the goal is not a hard guarantee.

Selecting G1 explicitly:

~~~bash
java -XX:+UseG1GC -Xms2g -Xmx2g -jar app.jar
~~~

In many Java 17 server environments, G1 is already the default by ergonomics; there is no need to add the flag without a reason.

### 7.2. Parallel GC

Parallel GC prioritizes throughput. It uses multiple GC threads for collection phases, shortening GC time compared to single-threaded collection on multi-core machines. However, stop-the-world pauses can be longer than with latency-oriented options.

~~~bash
java -XX:+UseParallelGC -Xms2g -Xmx2g -jar batch-job.jar
~~~

This collector can suit batch tasks where overall throughput matters more than short pauses.

### 7.3. Serial GC

Serial GC uses a single GC thread and has a simple footprint. For small heaps or low-CPU environments, low coordination overhead can be beneficial.

~~~bash
java -XX:+UseSerialGC -Xms128m -Xmx512m -jar small-tool.jar
~~~

For multi-threaded server workloads or large heaps, measure carefully because one GC thread may not keep up with allocation rates and pause requirements.

### 7.4. ZGC

ZGC is designed to keep pause times very low by performing most heavy work concurrently with the application. In Java 17, ZGC is a production collector; generational mode is not yet a feature of ZGC in this version.

~~~bash
java -XX:+UseZGC -Xms4g -Xmx4g -jar latency-sensitive-app.jar
~~~

ZGC can help when long pauses directly hurt latency. It still requires CPU and memory to perform concurrent work; workload, heap configuration, and hardware determine actual effectiveness.

### 7.5. Shenandoah

Shenandoah also targets low latency by performing most GC work concurrently with the application. Availability of this collector depends on the OpenJDK/vendor build and platform in use.

Do not assume every JDK 17 distribution provides the same collectors or flags. Check your distribution's documentation and runtime information before configuring.

## 8. Resource management is not garbage collection

GC manages memory for objects on the heap. It is no substitute for closing operating system resources such as:

- file descriptors;
- sockets and network connections;
- database connections;
- native locks or handles;
- streams and resources managed by external libraries.

These resources should be closed deterministically using `AutoCloseable` and try-with-resources:

~~~java
import java.io.BufferedReader;
import java.nio.file.Files;
import java.nio.file.Path;

try (BufferedReader reader =
        Files.newBufferedReader(Path.of("data.txt"))) {
    String line = reader.readLine();
    System.out.println(line);
}
~~~

When leaving the block, `close()` is invoked automatically. You do not wait for GC to collect the `reader` object before closing the file.

### 8.1. finalize() is an obsolete mechanism that should not be used

`Object.finalize()` has been deprecated for removal. Finalization has no timing guarantees, can resurrect objects, and causes performance, security, and reliability issues.

Do not write resource management code using `finalize()`. Instead use:

- `AutoCloseable` and try-with-resources for deterministic resource closing;
- `Cleaner` as a fallback mechanism in specific cases where needed, not as the primary way to close resources;
- explicit lifecycle management APIs provided by libraries or frameworks.

### 8.2. Cleaner

`java.lang.ref.Cleaner` allows registering a cleanup action to execute when an object becomes phantom-reachable and the cleaner processes the task.

Cleaner is a safety net. There is no guarantee that the cleanup action will run promptly or even run before process exit. If a resource must be closed on time, you still must call `close()` explicitly.

## 9. Memory leaks in a garbage-collected language

A memory leak in Java is usually not completely forgotten memory, but **objects that are no longer needed yet remain reachable**. Because GC sees a reference path from a root, it must keep those objects alive.

Some common causes:

### 9.1. Unbounded collections

~~~java
class EventHistory {
    private final List<Event> events = new ArrayList<>();

    void record(Event event) {
        events.add(event);
    }
}
~~~

If `events` is never bounded or pruned, all events remain reachable through the list. Use caches with size bounds, TTL, or an appropriate eviction policy.

### 9.2. Unremoved listeners

An object that registers a listener with a publisher can be retained by the publisher. Even when code no longer uses the listener, the publisher's reference keeps it reachable.

Unregister when the component ends its lifecycle:

~~~java
publisher.removeListener(listener);
~~~

Frameworks usually provide lifecycle hooks to clean up subscriptions; use the proper hook rather than relying on GC.

### 9.3. ThreadLocal in thread pools

Thread pools keep worker threads alive for a long time. A value stored in a ThreadLocal can continue to be held by the worker after a task completes if the application neither calls `remove()` nor overwrites the value.

~~~java
private static final ThreadLocal<RequestContext> CONTEXT =
        new ThreadLocal<>();

void handle(Request request) {
    try {
        CONTEXT.set(new RequestContext(request));
        processRequest();
    } finally {
        CONTEXT.remove();
    }
}
~~~

Calling `remove()` in `finally` prevents retaining request contexts across different tasks running on the same worker.

### 9.4. Static fields and class loaders

Static collections, registries, or callbacks can keep objects alive for a very long time. In applications with plugins, application servers, or hot reload, references from a long-lived class loader into the class loader of a stopped application can retain both the classes and related objects.

When unloading a module/plugin, clean up listeners, threads, ThreadLocals, registries, and static references registered by that plugin.

### 9.5. Unbounded caches

A cache without eviction can become a memory leak even though every entry is technically "in use" in the reachability sense. Always define:

- entry count or capacity limits;
- time-to-live;
- eviction policy;
- synchronization and reload behavior.

WeakReference does not automatically turn a cache into a good cache; the timing when GC clears weak references is not a predictable eviction policy for applications.

## 10. Heap, Metaspace, and native memory

Not all memory of a Java process resides in the Java heap.

| Area | Contents (overview) | Management |
| --- | --- | --- |
| Java heap | Objects and arrays. | Garbage collector. |
| Java stacks | Per-thread stack frames. | Frames pushed/popped on calls; stack tied to thread lifecycle. |
| Metaspace | Class metadata and certain class-loader-related data. | Managed by JVM; metadata can be reclaimed when class loader becomes eligible to unload. |
| Code cache | Machine code compiled by the JIT compiler. | Managed by JVM. |
| Direct/native memory | Off-heap buffers, native libraries, runtime structures, and OS-allocated regions. | Managed by the JVM, libraries, and respective native mechanisms. |

Therefore, an `OutOfMemoryError` does not necessarily mean the Java heap is full. There are error types such as:

- `Java heap space`;
- `Metaspace`;
- `Direct buffer memory`;
- `unable to create native thread`;
- other native allocation failures.

When investigating, identify which memory region is exhausted before increasing `-Xmx`.

## 11. Configuring the heap and observing GC in Java 17

### 11.1. -Xms and -Xmx

- `-Xms` sets the initial/minimum heap size as configured for the JVM.
- `-Xmx` sets the maximum heap limit.

Example:

~~~bash
java -Xms512m -Xmx2g -jar app.jar
~~~

Do not set `-Xmx` without accounting for the total memory limit of the container or machine. The process still needs thread stacks, metaspace, code cache, direct buffers, native libraries, and other runtime regions.

### 11.2. Enabling GC logging

Java 17 uses unified logging. Enable GC logs with:

~~~bash
java -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags \
    -Xms512m -Xmx2g -jar app.jar
~~~

Logs help observe:

- when GC starts/finishes;
- GC cycle type;
- pause duration;
- heap occupancy before and after GC;
- involved regions or generations, depending on the collector.

Do not look only at GC count. Read occupancy, allocation, and pause trends across the same load window.

### 11.3. Using jcmd

`jcmd` is a JVM diagnostic tool. Example:

~~~bash
jcmd
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

`jcmd` does not automatically explain the cause of a memory leak, but it provides useful data to guide an investigation. Some diagnostic commands can cause pauses or consume resources; check a command's impact before running it on latency-sensitive systems.

### 11.4. Heap dumps and profilers

When the heap grows abnormally, a heap dump reveals which objects occupy memory and why they remain reachable. You can use:

- Java Flight Recorder (JFR) to observe allocations, GC, and runtime behavior;
- Java Mission Control to analyze JFR recordings;
- heap dump analyzers such as Eclipse MAT to inspect dominator trees and paths to GC roots;
- IDE profilers or APM tools supporting allocation profiling.

An effective investigation strategy is to find classes with high instance counts or retained heap, then trace reference paths back to GC roots to identify which component is retaining the objects.

## 12. Example: distinguishing high allocation from a memory leak

### Case A: many short-lived objects

~~~java
static long calculate() {
    long total = 0;
    for (int i = 0; i < 1_000_000; i++) {
        String value = "item-" + i;
        total += value.length();
    }
    return total;
}
~~~

This snippet creates many temporary objects. If they are not retained after each iteration, GC can reclaim them. The allocation rate may be high, while the live set remains stable.

### Case B: objects retained indefinitely in a collection

~~~java
static final List<byte[]> RETAINED = new ArrayList<>();

static void allocate() {
    RETAINED.add(new byte[1024 * 1024]);
}
~~~

Each call to `allocate()` appends a 1 MB array to the static list. The arrays remain reachable from a GC root via the static field and list. GC cannot reclaim them until the application removes the entries or drops the reference path.

Both cases allocate objects, yet their causes and fixes differ:

| Symptom | Allocation pressure | Retained-memory leak |
| --- | --- | --- |
| New objects created | High | Can be high or moderate. |
| Post-GC live set | Can remain stable | Tends to climb if the leak continues. |
| Does GC reclaim many objects? | Usually yes | Cannot reclaim objects that remain reachable. |
| Investigation direction | Allocation profile, reduce unnecessary allocations. | Heap dump, dominator tree, GC roots, bound caches/lifecycles. |

## 13. Common mistakes and how to handle them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Assigning `null` to a variable does not drop heap immediately | GC does not run the instant an object loses a reference. | Understand eligibility vs. collection timing; observe GC and live set. |
| Two mutually referencing objects are not collected as expected | A reference path from a GC root may still exist. | Analyze the full object graph and GC roots; a cycle itself does not block GC. |
| Calling `System.gc()` does not reduce memory | It is only a request/hint that the JVM may ignore; objects may still be reachable. | Fix retention paths and use GC logs/heap dumps. |
| Heap fills up even though no objects are "in use" by business logic | Static collections, caches, or listeners still keep objects reachable. | Bound caches, remove listeners, and clean up lifecycles. |
| Using SoftReference as a cache yields unpredictable hit rates | GC decides when to clear soft references. | Use a bounded cache with an explicit eviction policy. |
| Thread pool retains old request context | ThreadLocal is not removed after task completion. | Call `ThreadLocal.remove()` in `finally`. |
| File/socket stays open even though the object has no reference variable | GC is not a deterministic resource-closing mechanism. | Use AutoCloseable and try-with-resources. |
| `OutOfMemoryError: Metaspace` while heap has free space | Class metadata/metaspace is exhausted, possibly due to class loaders or metaspace limits. | Inspect class loading/unloading and class loader retention. |
| `OutOfMemoryError: Direct buffer memory` | Off-heap direct buffer memory is exhausted. | Check buffer lifecycle, direct memory limits, and native memory. |
| Long GC pauses | Large heap/live set, unsuitable collector or settings, or high allocation pressure. | Read GC logs, measure workload, review collector and heap sizing. |
| Increasing `-Xmx` only delays the error | Objects are retained without bound or another memory region is exhausted. | Identify the OOME type and find the retention/allocation cause. |
| `finalize()` does not run on time | Finalization has no timing guarantee and is deprecated for removal. | Use try-with-resources; use Cleaner only as a fallback. |

## 14. Practice exercises

### Exercise 1 — Identify reachable objects

~~~java
static List<Object> cache = new ArrayList<>();

static void run() {
    Object first = new Object();
    Object second = new Object();
    cache.add(first);
    first = null;
    second = null;
}
~~~

After `run()` finishes, which object can be collected by GC? Explain the reference path for each object.

**Hint:** the first object is still held via the static list; the second object has no saved reference path from a root after the frame exits.

### Exercise 2 — Reference cycles

Create two Node objects referencing each other. Then drop all references from local variables. Explain why GC can still collect both.

### Exercise 3 — WeakReference

Create a WeakReference to an object, drop the strong reference, and read `weak.get()`. Why can you not write a test requiring `get()` to return null immediately after setting the variable to null?

### Exercise 4 — Find a memory leak in ThreadLocal

Write a task that puts RequestContext into a ThreadLocal inside a thread pool. Add `try/finally` and `remove()` so workers do not retain the previous request's context.

### Exercise 5 — Distinguish allocation rate and live set

An application creates millions of short-lived Strings per minute, yet post-GC heap always returns to roughly the same level. Is this necessarily a memory leak? State the metrics to inspect to distinguish allocation pressure from retained memory.

### Exercise 6 — Choose a collector

A batch job prioritizing throughput; an API needing consistent latency with short pauses; a small tool running on a resource-constrained machine. Consider Parallel GC, G1/ZGC, and Serial GC respectively. Explain why benchmarking on a real workload is necessary.

### Exercise 7 — Resource management

Write code to read a file using try-with-resources. Explain why you should not wait for the garbage collector to collect FileInputStream to close the file.

## 15. Takeaways on allocation, reachability, and GC

- Objects and arrays belong to the heap model; local variables and stack frames belong to each thread's Java stack.
- The JVM can optimize allocations via TLAB, escape analysis, or scalar replacement; these are runtime details, not guarantees code may assume.
- GC determines live objects by tracing references from GC roots.
- Unreachable objects become eligible for GC, but immediate reclamation is not guaranteed.
- Reference cycles do not prevent GC if the entire cycle has no path from any root.
- Strong references keep objects alive; SoftReference, WeakReference, and PhantomReference have distinct semantics and do not replace explicit cache/lifecycle policies.
- Memory leaks in Java are usually unneeded objects that remain reachable through static fields, collections, listeners, ThreadLocals, or class loaders.
- GC manages the heap; resources such as files, sockets, and database connections must be closed explicitly via AutoCloseable/try-with-resources.
- Avoid finalize() because it is deprecated for removal; Cleaner is only a fallback.
- G1, Parallel, Serial, ZGC, and Shenandoah have different goals; choose a collector based on workload metrics, not a universal rule.
- Read GC logs, JFR, heap dumps, and paths to GC roots to distinguish allocation pressure from retained-memory leaks.

### References

- [Java SE 17 — Java Virtual Machine Specification, Runtime Data Areas](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5) — heap, stacks, and runtime data areas.
- [Java SE 17 API — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html) — object lifecycle and deprecated status of finalization.
- [Java SE 17 API — java.lang.ref](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html) — SoftReference, WeakReference, PhantomReference, ReferenceQueue, and Cleaner.
- [Java SE 17 API — Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html) — fallback cleanup actions.
- [Java SE 17 G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html) — G1 structure and tuning.
- [Java SE 17 ZGC](https://docs.oracle.com/en/java/javase/17/gctuning/z-garbage-collector.html) — low-latency collector.
- [Java SE 17 Shenandoah GC](https://wiki.openjdk.org/display/shenandoah/Main) — Shenandoah collector information; availability depends on distribution.
- [Java SE 17 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/17/troubleshoot/) — diagnostic tools, GC logging, and memory analysis.
