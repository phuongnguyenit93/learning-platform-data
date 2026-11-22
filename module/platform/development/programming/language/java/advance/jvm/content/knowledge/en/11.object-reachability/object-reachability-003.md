# Why Does Assigning null or Leaving Variable Scope Not Guarantee Immediate Collection?

## 1. Key Takeaways

In Java, you can write:

~~~java
Object object = new Object();
object = null;
~~~

Or let a local variable leave a block:

~~~java
{
    Object object = new Object();
}
// object is no longer within variable name scope here
~~~

However, **neither operation guarantees that the newly created object will be reclaimed by GC immediately at that moment**. The reasons consist of three different layers:

1. **A variable is not an object.** Assigning `null` only changes the value of **one reference variable**; the object may still be referenced from elsewhere.
2. **Ending lexical scope is not a "reclamation event".** The Java compiler/JIT and garbage collector analyze **reachability**, not executing a `free` instruction upon encountering `}`.
3. **Even when an object is no longer reachable, GC is still not forced to reclaim it at a specific time.** The automatic memory manager decides when to work; in many cases, the program may terminate before the object is collected.

Distinguish carefully:

~~~text
Assign null to a variable / variable leaves scope
                 |
                 v
One reference path may no longer be usable
                 |
                 v
Are there other access paths from live roots?
        +-----------------------+
        |                       |
       YES                      NO
        |                       |
        v                       v
The object may still be   The object may become
strongly reachable        no longer strongly reachable
        |                       |
        v                       v
Not eligible for          May be eligible for
collection in the         reference/GC processing
usual way                 steps
                                 |
                                 v
                          Has GC actually run,
                          processed, and reclaimed it?
                                 |
                         NO FIXED SCHEDULE
~~~

From **"eligible for reclamation"** to **"collected/reclaimed"** is an important gap. **Eligibility for reclamation does not mean the reclamation operation has taken place.**

## 2. A Reference Variable Is Not the Object Itself

Consider the Java snippet:

~~~java
final class Box {
    final int id;

    Box(int id) {
        this.id = id;
    }
}
~~~

This is an illustrative class, without `main` yet. An object is created with:

~~~java
Box first = new Box(7);
Box second = first;
first = null;
~~~

It can be drawn as:

~~~text
Before first = null:

first  ----+
           |
           v
        Box(id=7)
           ^
           |
second ----+

After first = null:

first  ----> null

        Box(id=7)
           ^
           |
second ----+
~~~

**The object is not deleted** just because `first` is assigned `null`. `second` still holds a reference to that exact object, so the program can read `second.id`.

In terms of data types:

- `first` and `second` are **reference variables** in the program.
- `new Box(7)` creates an object according to Java semantics.
- Both can carry the **same reference value**, so `first == second` was `true` before `first` was assigned null.
- Assigning `first = null` **does not turn the object into null**, nor does it automatically change `second` to null.

**JIT note:** if the compiler sees that the `second` reference is no longer used in the future, actual liveness may differ from the source drawing earlier. However, as long as the program still has observable operations through `second`, the object must exist strictly according to Java semantics. Do not use alias diagrams to predict the exact time GC will run.

## 3. Java 17+ Example: Nulling an Alias Does Not Delete the Object

Create the file **`AliasReachability.java`**:

~~~java
public class AliasReachability {
    static final class Box {
        final int id;

        Box(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(7);
        Box second = first;

        System.out.println("same-before-null=" + (first == second));

        first = null;

        System.out.println("first-is-null=" + (first == null));
        System.out.println("still-readable=" + second.id);

        second = null;
        System.out.println("references-cleared");
        System.out.println("collection-is-not-guaranteed");
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac -g AliasReachability.java
java AliasReachability
~~~

**Exact stdout:**

~~~text
same-before-null=true
first-is-null=true
still-readable=7
references-cleared
collection-is-not-guaranteed
~~~

What the program **proves**: after `first` becomes null, the alias `second` still accesses `Box.id`. The last two lines are **fixed messages of the program**, **not GC signals confirming whether collection has occurred or not**.

What the program **does not prove**: right after the line `second = null`, the garbage collector has processed the object. There is no GC measurement in the example, and the specification does not allow turning the assumption "there are probably no references left" into the conclusion "the heap has been freed".

### If an object has many other reference paths

Another reference may reside in:

- A field of another object that is still reachable.
- A `static` field of a runtime class still retained according to reachability rules.
- An element of an array or `List`/`Map`/cache.
- A local variable/runtime structure that executing threads are still using.
- A value captured by a closure/lambda or callback.
- JNI references/native-runtime handles or other reference management systems.

The items above are **common sources/components of access paths**, not a fixed list of GC roots applying identically to every collector/JVM. When investigating a leak, one must find **paths from GC roots to the object**, rather than just seeing a local variable that received `null`.

## 4. Reachability Is a Property of the Object Graph, Not the Number of Null Assignments

A common learning model is the **object graph**:

- **Nodes**: runtime objects.
- **Edges**: references from object to object; there are also references from roots/runtime state.
- **Roots**: starting points that the VM considers live when determining which objects must be kept, depending on the runtime and GC.
- **Reachable**: there is a suitable access path from the computation part of live threads to the object.

~~~text
Root/heap model diagram:

GC root: thread's active state
   |
   v
CustomerService
   |
   +--> Repository ---------> Cache Map
   |                             |
   |                             +--> Customer #42
   |
   +--> Listener ---------> Customer #99

Local "temp" -------> Customer #42

temp = null:
  the path temp -> Customer #42 is gone,
  but Cache Map -> Customer #42 still remains.
~~~

The object `Customer #42` **is not considered unreachable just because the `temp` reference is gone**, because the cache map can still retain it through another path.

### Strong reachability and other levels

The JDK `java.lang.ref` documentation defines levels of reachability, from strongest to weakest:

| Conceptual state | Meaning |
| --- | --- |
| **Strongly reachable** | Can be reached without traversing the referent of a special `Reference` object |
| **Softly reachable** | Not strongly reachable, but can be reached through a `SoftReference` |
| **Weakly reachable** | Not strongly/softly reachable, but can be reached through a `WeakReference` |
| **Phantom reachable** | Special case for `PhantomReference` and post-mortem cleanup per API semantics |
| **Unreachable** | Not reachable through paths recognized by the reference processing system; eligible for reclamation per relevant rules |

**Do not equate "no strong references left" with "memory has been freed".** When using `SoftReference`/`WeakReference`/`PhantomReference`, the garbage collector may perform reference processing according to API rules; the resulting clearing/enqueueing and reclamation still have no timing arbitrarily set by the application.

A subtle point: **`PhantomReference.get()` always returns null**, even if the referent has not been processed by GC to the point of notification; it is not a way to check "is the object still alive" with a `get()` call like WeakReference.

## 5. Lexical Scope: Closing a Brace Does Not Run the Garbage Collector

Java has syntactic variable name scope. For example:

~~~java
static void example() {
    {
        byte[] buffer = new byte[1024];
        System.out.println("bytes=" + buffer.length);
    }

    System.out.println("after-block");
}
~~~

This is an **illustrative method that must be inside a class** to run. After the block, the name `buffer` **can no longer be validly accessed by source code**. However, the JVM has no corresponding opcode for "closing brace; free the array now".

### Three types of "lifetime" to separate

| Concept | Nature | Guarantees immediate GC? |
| --- | --- | --- |
| **Lexical scope** | The range where a variable name is validly used according to the JLS | **No** |
| **Runtime/JIT liveness** | The VM/compiler evaluates whether a reference is still needed for future computations | **No** |
| **Object reachability + GC decision** | Whether the object still has sufficient access paths per rules, then GC chooses when to process/reclaim | **No** |

Lexical scope may end before the method returns. Conversely, a variable whose name is still in scope may **no longer be used further**, so the compiler/JIT may consider the reference value dead earlier than you think.

### Once a method has returned, is the object guaranteed to be GC'd?

If the object was only referenced by locals of the finished frame, those references are no longer access paths from the old frame. However, there are still two possibilities:

1. The object escaped to another field/array/return value/callback/thread, so it is still reachable.
2. The object is indeed no longer reachable, but **GC may not have performed reclamation yet**.

Therefore, "the method has returned" **is not enough** to conclude that memory is immediately reclaimed. GC timing and heap management belong to the runtime.

### `LocalVariableTable` is not the final map of GC

In a class file, the debug `LocalVariableTable` may describe the name `buffer`, local slot, `Start`, and `Length` in bytecode indexes. It serves the debugger, **not a command forcing GC to collect**.

- The compiler can reuse the same local slot for multiple non-overlapping variables.
- The JIT can hold references in registers, eliminate intermediate variables, or optimize code.
- GC uses liveness/roots information based on runtime state, not taking `}` as a signal that "the object is definitely dead and can be collected immediately".

Use `javap -c -l -p ClassName` to **observe bytecode and debug ranges**, but **do not infer actual collection timing directly from `-l` output**.

## 6. Liveness Can End Earlier Than Lexical Scope

Example:

~~~java
static void process() {
    byte[] data = new byte[1024];
    int length = data.length;

    // data is not used again after this.
    performOtherWork();

    System.out.println(length);
}
~~~

This is an **illustration**; `performOtherWork` needs to be declared in the class containing the method. You may look at the source and think `data` stays alive until the end of the method. However, if the compiler/JIT proves the object is not needed for any subsequent observable behavior, reachability may end earlier than "end of method". JLS `12.6.1` acknowledges that optimizing transformations can make the set of reachable objects smaller than a naive reading of the source.

**The opposite direction:** if `performOtherWork()` writes `data` into another object's field or creates an asynchronous task holding the reference, the object may **live longer than the method**. Scope and reachability are related but not identical.

### Escape analysis and scalar replacement

The HotSpot JIT may notice that an object does not need to materialize as a separate heap allocation and optimize:

~~~java
static int sum() {
    Pair pair = new Pair(2, 3);
    return pair.left + pair.right;
}
~~~

`Pair` here is an **illustrative class** that must be defined in the program. The JIT can scalar-replace the object into field values, **without needing to create a physical heap object** in optimized code. In that case, asking "when is the object GC'd?" may be meaningless for an allocation that has been optimized away.

**Do not claim** that every `new` is eliminated or that HotSpot moves all non-escaping objects to the stack. This is an optimization possibility, depending on code, profile, flags, and compiler tier.

## 7. Eligible for GC Differs from GC Having Run and Differs from Memory Having Been Reused

Even when an object no longer has access paths requiring it to be kept, the following events are distinct:

~~~text
T0: The application no longer needs the object
T1: The object is actually no longer reachable per runtime state
T2: GC performs appropriate reachability/reference processing
T3: GC reclaims/marks memory for reuse, possibly compacting/moving
T4: The runtime allocates another object and reuses the corresponding memory region

There is no mandatory condition that T1 == T2 == T3 == T4.
There is no deadline set by Java source from the = null statement.
~~~

This is a logical diagram. In different garbage collectors, steps may occur concurrently/overlapping or be organized differently, not necessarily having exactly four sequential physical phases.

### Why doesn't the collector immediately collect each object?

GC is a trade-off between throughput, latency, memory usage, and overhead. Common realities:

- When the heap still has sufficient capacity, immediately collecting a small object may **not yield a large enough benefit**.
- GC typically performs work by regions/cycles, which may be concurrent or stop-the-world depending on the collector and phase.
- It must consider objects currently used by threads, the reference graph, and memory barrier requirements.
- Memory becoming reusable **within the heap** does not mean the operating system immediately sees RSS/process memory decrease.
- GC may keep heap committed/regions for later allocation, rather than immediately returning every memory page to the OS.

Therefore, "memory usage did not drop right after `obj = null`" **is not enough** to prove a Java memory leak. One must observe multiple GC cycles, live-set, and reference retention.

## 8. `System.gc()` Is Not a Promise to Reclaim an Object

Java has:

~~~java
System.gc();
Runtime.getRuntime().gc();
~~~

These are **requests suggesting the VM expend effort toward recycling unused objects**, not operations with the postcondition "every unreachable object immediately disappears".

The JDK 25 `Runtime.gc()` API explicitly states that the VM **does not guarantee** reclaiming a number of objects, an amount of memory, or completing at a specific time, including clearing/enqueueing reference objects. Additionally, the runtime may be affected by VM settings (such as HotSpot `-XX:+DisableExplicitGC`).

**Do not use** `System.gc()` in a loop to "guarantee freeing memory step by step" or to fix a memory leak. It can worsen latency/throughput and does not solve the issue of strong references still keeping objects reachable.

Do not test GC behavior with:

~~~java
object = null;
System.gc();
// assertion: object has been collected
~~~

The final conclusion **is not guaranteed**. If the object still has another reference, it is still not eligible accordingly; if it is already unreachable, GC is still not forced to execute according to your timing assumption.

## 9. Runnable Java 17+: Leaving Scope Does Not Generate a "GC Event"

Create the file **`ScopeDemo.java`**:

~~~java
public class ScopeDemo {
    static final class ResourceHolder {
        final String name;

        ResourceHolder(String name) {
            this.name = name;
        }
    }

    static void work() {
        {
            ResourceHolder scoped = new ResourceHolder("temporary");
            System.out.println("inside=" + scoped.name);
        }
        System.out.println("scope-ended");
    }

    public static void main(String[] args) {
        work();
        System.out.println("method-returned");
        System.out.println("collection-timing-unspecified");
    }
}
~~~

Run:

~~~bash
javac -g ScopeDemo.java
java ScopeDemo
~~~

**Exact stdout:**

~~~text
inside=temporary
scope-ended
method-returned
collection-timing-unspecified
~~~

**Meaning:** the name `scoped` cannot be accessed after the block's `}`, `work()` then completes, and `main` continues. The line `collection-timing-unspecified` is **proactively printed** by the programmer to emphasize that no GC event is measured in the program.

**Do not infer from the output** that the object has or has not been collected. If the JIT optimizes it away, even a separate physical allocation may not exist. The sole goal is to distinguish control flow, lexical scope, and GC.

### Using `javap`

~~~bash
javap -c -l -p ScopeDemo
~~~

You can see:

- Bytecode creating `ResourceHolder` and calling the constructor.
- `LineNumberTable` if the compiler retains line information.
- `LocalVariableTable` for `scoped` because it was compiled with `-g`.

**Do not turn `LocalVariableTable.Length` into "number of instructions until the object dies"**. Debug scope does not necessarily reflect JIT liveness or GC timing.

## 10. Important Example: Field/Static/Cache Retains Object After Method Return

Consider the Java 17+ program **`RetainedObjectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RetainedObjectDemo {
    private static final List<byte[]> CACHE = new ArrayList<>();

    static void populateCache() {
        byte[] data = new byte[1024];
        CACHE.add(data);
        data = null;
    }

    public static void main(String[] args) {
        populateCache();

        System.out.println("retained=" + CACHE.size());
        System.out.println("length=" + CACHE.get(0).length);

        CACHE.clear();
        System.out.println("after-clear=" + CACHE.size());
        System.out.println("collection-still-not-guaranteed");
    }
}
~~~

Compile:

~~~bash
javac -g RetainedObjectDemo.java
java RetainedObjectDemo
~~~

**Exact stdout:**

~~~text
retained=1
length=1024
after-clear=0
collection-still-not-guaranteed
~~~

Detailed explanation:

1. `populateCache` creates a `byte[]` on the heap per the model, then stores the reference into `CACHE` (a `static` field pointing to `ArrayList`).
2. `data = null` only drops the local reference, **it does not remove the element from the list**.
3. When the method ends, `CACHE` still holds the reference to the array, so `CACHE.get(0).length` is still 1024.
4. `CACHE.clear()` drops the element; per the `ArrayList` API, the list no longer retains that element after the operation succeeds. However, whether the array object is immediately GC'd still **has no guarantee**.
5. `CACHE.size() == 0` proves the collection does not retain elements in API logic, **not** confirming that the array object's memory has been reclaimed.

If there is another alias to the array, even after `CACHE.clear()`, the array may still be reachable. One must find **all relevant roots/paths** when debugging memory retention.

### Places that hold references longer than expected

In large applications, common object-retaining paths are:

- A `static Map/List` or cache without an eviction policy.
- A registered listener/callback that is never unregistered.
- A thread pool task/queue holding objects, `CompletableFuture` callbacks, or lambda captures.
- A `ThreadLocal` still holding a reference on a long-lived platform thread.
- A session map, HTTP request context, or long-lived registry.
- A ClassLoader/plugin framework still holding old objects/Classes/Methods or context loaders.
- JNI global references, native handles in native integrations.

An object **is not a leak just because it is still on the heap**. A practical leak occurs when the application retains objects **longer than intended**, causing the live-set to grow continuously or resources not to be freed. To conclude, one needs to cross-check ownership logic and measure memory over time.

## 11. WeakReference: Observing Without Holding a Strong Reference

`java.lang.ref.WeakReference<T>` can reference an object without **the weak reference itself keeping the object strongly reachable**. When GC determines the referent is only weakly reachable per the rules, it may clear weak references and enqueue them if registered with a queue.

**Important:** `weak.get() == null` is not a timer; and `weak.get() != null` at the time of checking does not prove GC will never happen. Do not write unit tests requiring a weak reference to clear within a few milliseconds.

### Java 17+ example with completely deterministic output

Create the file **`WeakReferenceDemo.java`**:

~~~java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceDemo {
    static final class Node {
        final int id;

        Node(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Node keeper = new Node(42);
        WeakReference<Node> weak = new WeakReference<>(keeper);

        System.out.println("id=" + keeper.id);
        System.out.println("same-while-strong="
                + (weak.get() == keeper));

        // Ensure keeper remains strongly reachable up to this point.
        Reference.reachabilityFence(keeper);

        keeper = null;
        System.gc();

        // Do not print weak.get() after GC because the result is not guaranteed.
        System.out.println("gc-requested");
        System.out.println("weak-clear-time-unspecified");
    }
}
~~~

Run:

~~~bash
javac -g WeakReferenceDemo.java
java WeakReferenceDemo
~~~

**Exact stdout:**

~~~text
id=42
same-while-strong=true
gc-requested
weak-clear-time-unspecified
~~~

Because `Reference.reachabilityFence(keeper)` ensures the referent is strongly reachable at least up to that point, the comparison `weak.get() == keeper` before the fence is `true` in a valid program. After `keeper = null` and `System.gc()`, the code **deliberately does not print the result of `weak.get()`**: the result can vary due to GC/JIT/runtime and is not a timing contract.

### Do not accidentally hold a strong reference

If you test:

~~~java
Node keeper = new Node(42);
WeakReference<Node> weak = new WeakReference<>(keeper);
List<Node> list = new ArrayList<>();
list.add(keeper);
keeper = null;
~~~

This is an **illustrative snippet**, missing imports/class frame. `list` still holds a **strong reference** to Node (if list is still reachable); therefore, do not wait for `WeakReference` to clear itself just because `keeper` was assigned null.

### ReferenceQueue does not turn GC into a synchronous callback

`ReferenceQueue<T>` allows receiving notifications **after GC processes references** per API conditions. This is not an "immediately when variable leaves scope" callback system. `queue.poll()` may return `null` if no notification is available yet, even if the application has set locals to null.

With `PhantomReference`, `get()` always returns null; it should be combined with a proper queue/cleanup design rather than used to count live objects by trying `get()`.

## 12. When Is `Reference.reachabilityFence` Used?

Since Java 9, the method:

~~~java
java.lang.ref.Reference.reachabilityFence(object);
~~~

**Ensures that the passed object remains strongly reachable at least until after the fence call** regardless of optimizations the JVM may perform. This is a very useful mechanism for cases where **a Java object holds ownership of a native resource** or Cleaner/finalization-like processing where the time at which the object is considered unreachable has observable consequences.

### Theoretical scenario with a native resource

~~~java
final class NativeHolder implements AutoCloseable {
    private final long handle;

    NativeHolder(long handle) {
        this.handle = handle;
    }

    void use() {
        nativeUse(handle);
        java.lang.ref.Reference.reachabilityFence(this);
    }

    private static native void nativeUse(long handle);

    @Override
    public void close() {
        nativeClose(handle);
    }

    private static native void nativeClose(long handle);
}
~~~

**This is an illustrative design, not a standalone runnable program:** the two native methods need appropriate JNI/FFM implementations, idempotent close logic, and real concurrency control. The point of `reachabilityFence(this)`: do not let the compiler consider the Java wrapper object no longer strongly reachable **before** completing the native operation that the wrapper owns, when cleanup depends on reachability.

**Clear limitations:**

- `reachabilityFence` **does not invoke GC**, **does not allocate memory**, and **does not force keeping the object alive forever**.
- It does not automatically synchronize `close`/`use` operations across multiple threads; a separate resource ownership protocol must be designed.
- Do not use fences on every object to "fix GC bugs": normally GC already guarantees valid uses of Java code.

## 13. Off-Heap Resources Need Lifecycle Closing, Not Waiting for GC

There are things more critical than Java heap memory: file descriptors, sockets, streams, database connections, locks, or native handles. A wrapper object becoming unreachable **does not mean** those resources have been closed in time.

The Java-recommended way is **`try-with-resources`** with `AutoCloseable`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

public class CloseDemo {
    public static void main(String[] args) throws IOException {
        byte[] bytes = {1, 2, 3};

        try (InputStream input = new ByteArrayInputStream(bytes)) {
            System.out.println("first=" + input.read());
        }

        System.out.println("resource-scope-ended");
    }
}
~~~

Compile:

~~~bash
javac CloseDemo.java
java CloseDemo
~~~

**Stdout:**

~~~text
first=1
resource-scope-ended
~~~

In this example, `try-with-resources` guarantees calling `close()` according to Java semantics when leaving the block, including on appropriate exception paths. `ByteArrayInputStream` does not represent a real file descriptor, but illustrates control flow without needing an external file.

**Do not infer** `close()` = GC object. `close()` is a resource-lifecycle operation in the Java API; the wrapper object may still remain on the heap while the resource has been closed. If an OS resource needs to be illustrated, use `Files.newBufferedReader`/`FileInputStream` in an exercise with a specific file and exception handling.

### Can Finalization and Cleaner replace try-with-resources?

- Java finalization is **deprecated for removal**, and per Java SE 25 implementation finalization may be disabled. Do not write logic that requires `finalize()` to definitely be called to release resources on time.
- `Cleaner` can assist with fallback cleanup when an object becomes phantom reachable per semantics, but **has no deadline** sufficient to replace explicit `close()` operations for critical file/socket/database resources.
- **Prefer explicit resource ownership**, closing in `finally`/`try-with-resources` or a specific lifecycle protocol.

## 14. How to Distinguish a Memory Leak from GC Not Having Run Yet?

If you see the heap grow after a request, do not rush to assign null everywhere. Evaluate:

### Diagnostic sequence

1. **Check the live-set:** does memory after appropriate GC cycles continue to grow under comparable load?
2. **Check GC logs/metrics:** has the collector run; what are heap used before/after GC, allocation rate, and pause/throughput?
3. **Use a heap dump when there is evidence of retention:** find object dominators and reference paths from GC roots.
4. **Find long-lived owners:** static caches, maps, event listeners, task queues, ThreadLocal, long-lived services, classloader references.
5. **Prove the specific path retaining the object:** if a local alias is dropped while a static map remains, GC cannot collect the object because the map still retains it.
6. **Fix ownership/eviction:** remove entries, unregister listeners, close resources, bound cache size, drop unnecessary references.
7. **Verify after the fix** with a reproducible workload, heap profiling, and comparable GC metrics.

### Distinguishing examples

| Observation | What can be concluded | What cannot yet be concluded |
| --- | --- | --- |
| `obj = null` just ran | One variable was assigned null | The object has been reclaimed |
| Method containing `obj` just returned | The old frame ended semantically | No references remain in fields/callbacks/other threads |
| `WeakReference.get() != null` | At that moment the referent was still returned by weak.get | GC has never run, the object will always remain |
| `WeakReference.get() == null` | The weak ref was cleared or explicitly cleared by code | Memory has definitely been returned to the OS |
| Heap used did not drop immediately | No decrease observed by that metric yet | A memory leak definitely exists |
| After multiple GCs the live-set still grows | There are signs of retention needing investigation | Exactly which class is leaking without viewing the graph |
| `CACHE.clear()` | The collection does not retain entries per API | All other aliases are gone or GC just ran |
| `System.gc()` has returned | The VM processed the best-effort request per API | Every unreachable object has been collected |

**A large heap dump is not automatically a memory leak**: it may be due to legitimate workloads/caches. What decides it is objects that are no longer needed but are still kept reachable via unintended owners.

### Observing HotSpot

Some options/tools:

~~~bash
java -version
java -Xlog:gc* -jar app.jar
jcmd <pid> GC.heap_info
jcmd <pid> GC.class_histogram
~~~

These are **templates** for a real application and PID, **do not run verbatim without `app.jar`**. `jcmd` is a JDK tool for querying supported JVM information with access permissions; specific commands/outputs may vary by VM version, and `GC.class_histogram` can be costly. Use observation tools in test/staging environments before impacting production.

With **JFR**, you can observe allocation rate, GC, object count/old object sample per recording configuration. **Do not confuse high allocation rate** with a memory leak: objects can be created quickly and also quickly become unreachable; a leak lies in live retention.

## 15. Scope Exit Timing and Compiler/JIT Optimizations

Example:

~~~java
static void mainWork() {
    Object a = new Object();
    consume(a);

    // In source, a can still be referenced by scope.
    doSomethingElse();
}
~~~

This is an **illustrative snippet needing `consume`, `doSomethingElse` declared in the class**. If `consume` does not keep an alias and `doSomethingElse` no longer uses `a`, the optimizer may conclude `a` is not needed for continuing execution. Conversely, `consume` may retain the reference by storing it in a field, array, or callback, making the object live longer than the method.

**Special depth:** JLS `12.6.1` notes that reachability is tied to **potential continuing computation**. Determining whether a value is still reachable is more complex than "the variable is still in source scope". GC is not required to wait until the closing brace to consider an object no longer needed.

### Do not force `null` everywhere to "optimize GC"

For a short-lived local:

~~~java
void handle() {
    byte[] data = computeData();
    process(data);
    data = null;
    continueWork();
}
~~~

This snippet is illustrative and needs `computeData`/`process`/`continueWork` methods. The assignment `data = null` may be pointless because the JIT already knows the reference is dead after `process`. In some specific code and memory pressure situations, dropping a long-held reference is meaningful; however, **dropping a reference does not mean forcing GC to run**, and writing null for every local makes code harder to read.

A more effective example is usually **removing the reference from a long-lived container** at the moment the owner no longer needs it, or splitting a method with large data scopes into clear steps. Actual benefits need to be measured, not guessed from source.

## 16. Distinguishing Strong/Weak/Soft/Phantom in Practice

| Mechanism | Purpose | Keeps object strongly reachable? | Guarantees immediate collection? |
| --- | --- | --- | --- |
| Local/field/array **strong reference** | Normal object access | Yes, while that path is reachable and needed | No |
| **`SoftReference<T>`** | Memory-pressure-sensitive caches | Not a strong reference | No |
| **`WeakReference<T>`** | Mappings/caches without holding referent via strong ref | Not a strong reference | No |
| **`PhantomReference<T>`** | Post-mortem tracking and cleanup patterns via queue | Not a strong reference | No |
| **`ReferenceQueue<T>`** | Receiving notification after reference processing | Queue does not itself guarantee keeping any referent | No |
| **`Cleaner`** | Managing cleanup actions when referent meets relevant conditions | Not used as a deadline to replace resource closing | No |
| **`Reference.reachabilityFence`** | Keeping argument strongly reachable at least until fence | Yes, up to fence per semantics | Does not request collection |

**Note on `WeakHashMap`:** keys are weakly referenced, but if a **value holds a strong reference back to the key**, the entry may still indirectly keep the key alive. In practice, designing weak caching requires inspecting the entire object graph.

Do not create a busy-wait loop (`while (weak.get() != null) { System.gc(); }`) to demand GC by a deadline; this approach may not terminate as expected, wastes CPU, and violates semantics.

## 17. Common Misconceptions

| Misconception | What is true |
| --- | --- |
| "`x = null` deletes the object immediately." | Only changes **one reference variable**; other aliases may remain. |
| "Closing `}` invokes GC." | Scope is a variable naming rule, not a reclamation instruction. |
| "When a method returns, all objects created in the method die." | Objects can escape via return, fields, static collections, callbacks, other threads. |
| "An unreachable object means it has been reclaimed." | **Eligibility differs from actual reclamation**. |
| "GC is an action that happens immediately when reference count hits 0." | Java GC is not defined as reference counting and has no such deadline. |
| "Assigning null immediately reduces heap used." | GC may not have run yet; heap memory may still be committed even if reusable. |
| "`System.gc()` forces the JVM to collect every unused object." | The API is only best-effort/hint, with no quantity/timing guarantees. |
| "While the variable name is in scope, the object is guaranteed to live until the end of the block." | The optimizer can shorten liveness if there is no observable use left. |
| "Leaving scope guarantees the object is unreachable." | Other references may exist in the graph. |
| "LocalVariableTable length tells when GC collects." | The debug table is not a GC liveness timeline. |
| "An existing WeakReference will keep the object forever." | A weak reference does not keep the referent strongly reachable. |
| "WeakReference.clear happens at the exact moment `System.gc()` runs." | Reference processing has no schedule set by source code. |
| "`PhantomReference.get() == null` proves the object was GC'd." | `PhantomReference.get()` returns null per API. |
| "`reachabilityFence` forces GC to run." | It only guarantees strong reachability up to the fence point. |
| "Cleaner/finalize always runs on time to close files." | No; finalization is even deprecated for removal, and GC cleanup has no deadline. |
| "Memory leaks only happen when developers use native allocation." | The Java object graph can retain references too long via static caches/listeners/ThreadLocal. |
| "Any single heap increase is a leak." | One must observe live-set after GC, allocation load, and owners. |
| "Closing `AutoCloseable` means the wrapper object is GC'd." | `close` manages resource lifecycle; the object may still be reachable. |

## 18. Self-Check

**1.** `Box a = new Box(7); Box b = a; a = null;` — does the object disappear?  
**Answer:** No. `b` still holds a reference to the object; `b.id` can be read.

**2.** Why does the `}` ending a block not guarantee GC?  
**Answer:** It ends the **lexical scope of the variable name**, does not automatically clear other aliases, and does not force GC to run immediately.

**3.** Is "Eligible for GC" equal to "GC has reclaimed memory"?  
**Answer:** No. Being eligible for reclamation and actually being reclaimed are two different states/times.

**4.** `static List<byte[]> CACHE` holds an array; does local `data=null` in the method that created the array remove the reference in CACHE?  
**Answer:** No. The entry in the cache must be removed if the owner truly no longer needs it.

**5.** Does `System.gc()` guarantee that all WeakReferences are cleared right when it returns?  
**Answer:** No. The API does not promise the number of references processed or a deadline.

**6.** Why is using `WeakReference.get()` in a unit test and waiting for it to become null within milliseconds unreliable?  
**Answer:** GC timing and reference processing are not time-guaranteed by the API.

**7.** Is there a case where GC is allowed to consider an object no longer reachable before the source variable leaves scope?  
**Answer:** Yes. The optimizing compiler/JIT can shorten liveness when no observable use remains.

**8.** What guarantee does `Reference.reachabilityFence(x)` provide?  
**Answer:** Keeps `x` strongly reachable at least until after the call, despite certain optimizations; does not force collection.

**9.** What is a more reliable way to close a socket/database connection than waiting for GC?  
**Answer:** `close()` or `try-with-resources` according to the API and application lifecycle.

**10.** Is heap memory not decreasing after one `null` assignment definitive proof of a leak?  
**Answer:** No. One must check GC cycles, live set, and graph retention.

**11.** Why does `weak.get() == null` not yet indicate that heap space has been returned to the OS?  
**Answer:** Reference clearing, object reclamation, heap reuse, and returning memory to the OS are mechanisms not guaranteed to be simultaneous.

**12.** In a class using JIT, does `new Pair()` always create a real heap object?  
**Answer:** No. Escape analysis/scalar replacement can eliminate the allocation while preserving program semantics.

## 19. Official Sources

- [JLS Java SE 25 — §12.6 Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.6): foundation on object reachability/finalization; especially **`12.6.1`** and the impact of optimizing transformations.
- [JDK 25 — `java.lang.ref` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/package-summary.html): strong/soft/weak/phantom reachability types and ReferenceQueue.
- [JDK 25 — `java.lang.ref.Reference.reachabilityFence`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): keeping strong reachability up to a specific point.
- [JDK 25 — `java.lang.ref.WeakReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): clearing semantics of weak references.
- [JDK 25 — `java.lang.ref.PhantomReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/PhantomReference.html): phantom reachability and `get()`.
- [JDK 25 — `Runtime.gc()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runtime.html#gc()): best effort, no guarantee on reclaim/count/timing.
- [JDK 25 — `System.gc()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#gc()): shorthand to Runtime.gc.
- [JVMS Java SE 25 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5.3): class instances/arrays in the heap, GC managed by VM.
- [JLS Java SE 25 — §14.4 Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): local variables and syntactic scope.
- [JDK 25 — `AutoCloseable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): closing resources with managed lifecycle.
- [JDK 25 — `Cleaner`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/Cleaner.html): assistive cleanup when reachability changes; no guaranteed deadline.
- [JDK 25 — `jcmd`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): diagnostics related to heap/histogram and supported VM commands.

**Conclusion:** **`= null` and leaving scope only affect one way of holding a reference/variable name address; they do not prove that all access paths to the object are gone, and even less do they force the garbage collector to reclaim the object immediately.** Identify the object graph and ownership, distinguish reachability from reclamation, use `AutoCloseable` to close bounded resources, and evaluate GC through actual observation rather than relying on braces or null assignments.