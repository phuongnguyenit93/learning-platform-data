# Object Lifetime, Reachability, and Limits of Inferring from Variable Scope

## 1. Core issue: a variable going out of scope is not an object destruction command

Consider the Java snippet:

```java
static void example() {
    Object item = new Object();
    System.out.println(item.getClass().getSimpleName());
} // item goes out of scope
```

The closing brace `}` indicates that **the local variable `item` can no longer be used by that name outside the block**. It is **not** a statement to "immediately free the object", does not promise that the garbage collector (GC) will run at this exact moment, and does not promise that the heap region will be returned to the operating system after the method returns.

In Java/JVM, what needs to be distinguished is:

1. **Variable scope (lexical scope):** the region of source code where the variable name can be used.
2. **Variable/slot lifetime:** how the compiler and JVM maintain values in local variables, fields, or registers; not identical to source braces.
3. **Object reachability:** whether there is still a way for the running program to continue accessing the object through valid references.
4. **Eligibility for reclamation:** whether the object can be reclaimed by the GC according to reference management and GC rules.
5. **When the GC performs reclamation:** depends on the runtime, GC policy, resources, and program activity.
6. **Off-heap resource lifecycle:** file descriptors, sockets, database connections, native handles… are not automatically closed at the right time just because the Java object holding a reference to the resource is no longer needed.

**Conclusion:** An `Object` can still be **reachable** after the local variable that created it has gone out of scope if there is still a reference from a field, collection, callback, or thread. Conversely, an object can be considered **no longer needed** by the compiler/JIT before the source block ends if no subsequent observable behavior requires it.

This is the foundation for analyzing memory leaks, class loader retention, cache lifecycles, `ThreadLocal`, `WeakReference`, `Cleaner`, and why `Reference.reachabilityFence` is needed.

## 2. What does the JVM Specification guarantee?

According to **JVMS `2.5.3 — Heap**, the heap is the runtime data area used for class instances and arrays. Managing/reclaiming heap objects is performed by an **automatic storage management system** commonly called a garbage collector.

The specification does not mandate:

- A specific GC such as G1, ZGC, or Shenandoah.
- That GC must run after leaving a scope.
- That an object must exist in a specific heap generation.
- That every `new` instruction always corresponds to a physical allocation that must be observable under all optimizations.
- When reclaimed memory will be returned to the OS.
- That Java provides a `free(object)` operator for the application to manually free a heap object.

What an application can rely on is **program semantics** and **guarantees in Java/JVM APIs**, not an "expected" GC schedule.

### 2.1. Do not confuse lifetime with object identity

```java
Object a = new Object();
Object b = a;
a = null;
System.out.println(b != null); // true
```

The variable `a` no longer references the object, but `b` still holds the same object. An object does not become unreachable just because one of multiple variables changes to `null`.

Similarly:

```java
Object x = new Object();
Object y = new Object();
x = y;
```

After the assignment `x = y`, the object previously pointed to by `x` **may** become no longer strongly reachable if there are no other references. The object pointed to by `y` still has two references from `x` and `y` in this conceptual example. Which one is reclaimed and when depends on reachability and the runtime, not "it must be freed immediately when the assignment occurs".

### 2.2. Java does not use pure reference counting as a GC contract

A reference cycle:

```java
class Node {
    Node next;
}

Node left = new Node();
Node right = new Node();
left.next = right;
right.next = left;
left = null;
right = null;
```

can become **unreachable** from all live sources, even though the two `Node`s still point to each other. The GC can reclaim the entire cycle if no reference source holds it and the relevant conditions are met.

**The number of references between objects is not enough to decide whether an object is "alive".** What matters is reachability from valid runtime sources/roots.

## 3. Lexical scope, local variables, frame, and object are not the same thing

In source code, the declaration block determines where a variable name can be used:

```java
void method() {
    {
        Object local = new Object();
        // Can write local here.
    }
    // Cannot write local here.
}
```

After the block, writing `local` will cause a compile-time error. However, JVM bytecode does not operate based on a "closing `}` brace will free the heap object". A method's bytecode has **local variable slots** and an **operand stack** in a frame; the compiler can reuse a slot after a value is no longer needed.

A `LocalVariableTable` (if emitted by the compiler as debug metadata) can describe name/offset ranges for a debugger to display. It is **not a GC command**; whether or not that debug table exists does not determine whether an object is reclaimed.

### 3.1. Method return is not enough to conclude an object is dead

```java
static Object create() {
    Object local = new Object();
    return local;
}

Object result = create();
```

When `create` returns, the callee's local variable `local` is no longer in the active frame. However, **the object can still be accessed from the caller's `result`**. If one assumes "the method ending means the object is dead", one has confused the lifetime of a **frame/local name** with the reachability of a **heap object**.

### 3.2. A variable is still in scope, but the object may no longer be needed

```java
static void process() {
    Object buffer = new Object();
    System.out.println(buffer.getClass());
    doIndependentWork();
    // the block has not closed yet, but buffer is no longer used
}
```

This snippet is **for illustration only**; `doIndependentWork()` must be defined in a real program. On a given execution path, the compiler/JIT may detect that no remaining operations need `buffer` and shorten the period during which the object is kept strongly reachable.

JLS `12.6.1 clearly states that optimizations can shorten reachability time compared to a naive reading of "the local is still in scope so the object lives until the end of the block". A runtime is not required to keep an object alive until the local name is no longer syntactically valid.

### 3.3. A local variable slot still holding an old value is not necessarily a strong GC root

The JVM implementation/JIT may determine which locals/registers are **live** at a safepoint differently from how a debugger might see an old bit pattern in a slot. One must not assert "if a slot still contains an old reference, the object is definitely kept alive" across all HotSpot optimizations.

Conversely, if an object still has a reference from a field of another live object, the local going out of scope is also not enough to make it unreachable.

## 4. The concept of reachability: where do you reach the object from?

To understand GC, draw the **graph of objects and references**:

```text
Live roots / live program
             |
       +-----+------+
       |            |
  Static registry   Active frame
       |            |
       v            v
     List A        Service B
       |            |
       v            v
   Payload X      Request Y
       |
       v
   Payload Z
```

If an object can be accessed from a live source through a chain of valid **strong references**, it is **strongly reachable**. When no strong-reference path remains, it may belong to a weaker reachability level if referenced via `SoftReference`, `WeakReference`, or `PhantomReference`, or become unreachable.

The exact GC graph depends on the implementation, the roots the VM needs to consider, and reference-processing rules. The diagram is for analysis; **it does not mean the JLS lists a fixed data structure of "GC roots" across all JVMs**.

### 4.1. Common sources that can keep an object alive

In HotSpot, when analyzing the heap, reference paths to examine include:

- **Live references from frames/threads:** parameters, locals/registers that computation still needs.
- **Static fields:** static references of existing classes, by class-loader identity.
- **Objects held directly/indirectly by roots:** registries, singletons, caches, collections.
- **Threads and thread-associated state:** active tasks, thread locals, thread context class loaders, callback references.
- **JNI/native handles and VM-managed references** in appropriate contexts.
- **Class loaders/class metadata and related links:** especially in plugins/application servers.

This list is a **diagnostic guide**, not an exclusive definition for every GC. Depending on the runtime, object graphs and root categories shown in a heap dump may differ.

### 4.2. "No remaining path from a local variable" is not enough

```java
static final java.util.List<Object> ITEMS =
        new java.util.ArrayList<>();

static void add() {
    Object local = new Object();
    ITEMS.add(local);
}
```

This illustrative code snippet needs to be placed in a class. After `add()` returns, the local reference disappears, but **ITEMS still contains the object**. If the registry lives long-term, the object can live long-term.

To remove an edge in the graph, it is necessary to remove it from the appropriate collection:

```java
ITEMS.clear();
```

However, **calling clear does not mean the object must be GC'd immediately**, because the object may still have other references and the GC may not need to run yet.

### 4.3. Closures and lambdas can retain captures

```java
static Runnable task() {
    Object captured = new Object();
    return () -> System.out.println(captured.toString());
}
```

After `task()` returns, the lambda can still hold a reference to `captured`. It continues to live along with the callback object if the runtime needs to retain the captured value to preserve behavior. Where the callback is registered (executor, listener registry, timer) can extend the lifetime of the captured object.

Therefore, **"the local variable has gone out of scope"** is a weak signal in memory retention investigations.

## 5. Reachability levels of `java.lang.ref`

Java SE provides three families of **special reference objects**: soft, weak, and phantom. They allow controlled interaction with the GC. Java SE 17 `java.lang.ref` describes the reachability levels in order from strongest to weakest:

| Level | General meaning | Practical impact |
| --- | --- | --- |
| **Strongly reachable** | Can be accessed without going through special reference objects | Normally, the GC does not reclaim the object while it is still needed along a strong path |
| **Softly reachable** | Not strongly reachable, but has a path through a `SoftReference` | The collector may clear soft references to meet memory demand |
| **Weakly reachable** | Not strong/soft, but has a path through a `WeakReference` | Weak refs are processed/cleared when the collector determines the referent is weakly reachable |
| **Phantom reachable** | No stronger levels remain and satisfies phantom reference rules | Used with a reference queue/cleanup; does not provide the referent back via `get()` |
| **Unreachable** | No reachability path remains under the levels above | May be eligible for reclamation depending on GC policy/cycle |

**Caution about finalization:** historical specifications had conditions involving finalization when explaining phantom/unreachable. Finalization has been deprecated for removal and Java SE 26 allows implementations to disable it; new applications should not design cleanup based on finalizers.

### 5.1. Strong reference

```java
Object strong = new Object();
```

When `strong` is a reference still needed to continue computation, the object is kept reachable in the appropriate sense. The fact that the name `strong` is inside a block **does not by itself dictate** that it must exist as a GC root until the very end of the block; live reference status depends on execution paths and valid optimizations.

### 5.2. `SoftReference` does not give a fixed time for when it is cleared

```java
java.lang.ref.SoftReference<byte[]> soft =
        new java.lang.ref.SoftReference<>(new byte[1024]);
byte[] data = soft.get();
```

This is an illustrative snippet, not a standalone program. `soft.get()` may return the array or `null` if the soft reference has been cleared according to GC policy. There is no Java contract stating that "a soft reference definitely survives until heap free < 10%" or "the GC must clear all soft refs on every collection".

Soft references are used for **memory-sensitive caching**, but require real-world testing and a fallback to regenerate data. Do not rely on soft refs to store mandatory information that cannot be recreated.

### 5.3. `WeakReference` does not keep its referent alive on its own

```java
Object obj = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(obj);
```

If the program still holds `obj` as needed, the referent has a strong path. When the strong path no longer exists, `weak` does not guarantee that the referent lives forever.

Important:

- `weak` itself is a **reference object** that can still be strongly reachable.
- `weak.get()` retrieves the referent if it has not been cleared; if cleared, it returns `null`.
- **When the GC runs, clears, or enqueues is not determined by the source `}` brace.**
- Do not call `System.gc()` and then assert "`weak.get() == null` must be true immediately" in portable unit tests.

### 5.4. `PhantomReference` is for cleanup notification, not for reading the object back

`PhantomReference<T>` is used with `ReferenceQueue<T>` and post-reachability processing mechanisms. `PhantomReference.get()` **always returns `null`**; it is not a way to retrieve an object about to be reclaimed.

Do not use a phantom reference as a "slightly stronger weak reference that can be dereferenced". It is designed for notification/cleanup coordination.

## 6. What does `ReferenceQueue` help you know?

`ReferenceQueue` allows a program to receive **reference objects** when they are enqueued according to GC reference-processing rules:

```java
java.lang.ref.ReferenceQueue<Object> queue =
        new java.lang.ref.ReferenceQueue<>();
Object target = new Object();
java.lang.ref.WeakReference<Object> weak =
        new java.lang.ref.WeakReference<>(target, queue);
```

This is an illustrative snippet to be placed in an appropriate method/class. When the GC determines that the referent is in the appropriate state, the weak reference may be cleared and enqueued. Afterward, `queue.poll()` may return a pending reference, or `null` if none is available yet.

**Do not infer that `queue.poll() == null` means the target is definitely still strongly reachable**: the GC may not have performed reference processing yet, the enqueue event may not have occurred yet, or another runtime situation may apply. Observable timing is not a standard clock for measuring lifetime.

### 6.1. Why shouldn't you keep a strong referent in a cleanup registry?

If you both create a weak reference to an object and keep **another strong reference to that exact same object** in a registry "for cleanup", the object can still live forever. A weak reference does not nullify other strong paths.

Dangerous conceptual example:

```text
Registry
  +-- WeakReference(target)
  +-- StrongReference(target)    <-- still keeps the object alive
```

When debugging a weak-cache that does not release, look for strong edges **outside the WeakReference itself**.

## 7. Scope of a local and actual *liveness*

A variable in source code may still be **in scope**, yet the compiler knows its last value has already been used:

```java
static void work() {
    byte[] temporary = new byte[1_000_000];
    use(temporary);
    expensiveCalculation();
}
```

This is an illustration; `use` and `expensiveCalculation` are not defined. After the last time `temporary` is needed, the compiler/JIT can shorten the live range of the reference. The object may be considered no longer strongly reachable before `work` finishes, provided the transformation is semantically valid.

Conversely, if `use` puts `temporary` into a shared registry, the array still has a strong reference path through the registry after the method returns.

### 7.1. "When a variable goes out of scope, the object is eligible for GC" is only conditionally true

Consider:

```java
static java.util.List<byte[]> storage = new java.util.ArrayList<>();

static void allocate() {
    byte[] buffer = new byte[1024];
    storage.add(buffer);
}
```

The name `buffer` goes out of scope, but the array is **still reachable from `storage`** if the registry is still alive and it has not been removed.

An accurate explanation should be:

> After a local variable no longer holds a live reference, the object **may** become no longer strongly reachable, **if no other strong paths remain**.

### 7.2. Does `local = null` necessarily reduce memory?

No. Writing:

```java
Object item = new Object();
use(item);
item = null;
```

is a way to proactively drop the local's reference, but:

- The compiler may already know the reference is no longer live before the `item = null` statement.
- The object may still be held by fields/caches/closures.
- The garbage collector may not have run yet.
- Heap used afterward may not drop immediately, and heap committed may still be kept for reuse.

In some very long methods where a local slot exists for a long time and the compiler/interpreter holds the reference longer than necessary, dropping the reference might have an effect on a specific runtime. However, **this is neither a mandatory technique nor a portable guarantee**, and it certainly does not replace designing reference lifecycles properly.

### 7.3. Debuggers and optimizations can make the situation hard to observe

In JIT mode, a variable that source code shows as still in scope may be optimized away or unavailable for a debugger to read. Conversely, a value may remain in a local slot in the interpreter even though the source name has gone out of scope.

**Do not guess reachability solely from a LocalVariableTable snapshot, stack trace, or curly brace position.** When investigating leaks, you need a heap dump, GC roots/path-to-root, and how objects are actually retained.

## 8. `Reference.reachabilityFence`: explicitly requiring a final point of use

`Reference.reachabilityFence(Object)` was added in Java 9. It establishes a **point at which the object must be considered strongly reachable at least until after the invocation**, according to the API contract.

Conceptual example:

```java
import java.lang.ref.Reference;

static void handle(NativeHandle handle) {
    long address = handle.address();
    nativeWork(address);
    Reference.reachabilityFence(handle);
}
```

This is **illustrative code**, not a standalone program: `NativeHandle` and `nativeWork` need appropriate definitions. In this kind of code, a native call might only receive a numeric `long` address, so the JVM cannot automatically know that it needs to keep the Java wrapper `handle` alive across the entire operation just by looking at the `long` value.

`Reference.reachabilityFence(handle)` indicates that the wrapper object must remain strongly reachable at least until after the call. It is very useful in code integrating native resources or cleaning mechanisms where the wrapper object controls the lifetime of a native handle.

### 8.1. `reachabilityFence` is not `free`

Things `reachabilityFence` **does not do**:

- Does not force the garbage collector to run.
- Does not "pin" the object at a fixed heap address.
- Does not extend lifetime indefinitely.
- Does not guarantee the native resource is closed.
- Does not create a permanent reference after the method returns.

It constrains the compiler/runtime regarding **reachability up to a program point**, not an API for controlling the GC schedule.

### 8.2. Placing the fence in the right position

If work with the resource completes at the end of a block, the fence should appear **after the last time the work might need the resource**:

```text
use resource / call native
            |
            v
Reference.reachabilityFence(owner)
            |
            v
no longer need to keep owner for that work
```

Do not place the fence at the very beginning of a method and expect it to keep the object alive across subsequent operations. A fence also **does not replace synchronization, ownership protocols, or explicit close** when a native resource is shared across multiple threads.

## 9. Java object lifecycle and external resource lifecycle are not identical

Creating a Java object can simultaneously open a file/socket/native allocation:

```java
java.io.InputStream in =
        java.nio.file.Files.newInputStream(path);
```

This is an illustrative snippet; `path` must be declared. The Java reference to the stream is an object on the heap, but the associated file descriptor/native handle has an **off-heap resource lifecycle**.

If the variable `in` goes out of scope without being closed, there is no guarantee the operating system will reclaim the file descriptor immediately. The GC might not run in time, and cleaner/finalization (if present) is not a deterministic cleanup mechanism for critical resources.

### 9.1. `try-with-resources` is the primary choice for closeable resources

```java
try (java.io.InputStream in =
         java.nio.file.Files.newInputStream(path)) {
    // Process data from the stream.
}
```

The compiler arranges to call `close()` when exiting try-with-resources according to Java's rules, even when the body terminates with an exception (with suppressed exceptions mechanism where appropriate).

This is **different from** "the object is GC'd": the resource is closed **proactively by control flow**, without waiting for the object to become unreachable.

### 9.2. `AutoCloseable` does not mean the heap object destroys itself

An `AutoCloseable` object after `close()` may still be reachable and may still be accessed (depending on the API). `close` manages the **resource lifecycle**, not "freeing Java object memory".

Conversely, an object may become unreachable before `close` is called if the code uses an incorrect pattern. Clear ownership needs to be designed.

## 10. `Cleaner` and `PhantomReference`: safety net, not a replacement for explicit close

Java `Cleaner` manages cleaning actions tied to the reachability of a registered object. It is used to help release resources when the caller forgets to close, but **does not guarantee when the cleanup action will occur** before the process terminates or before a business deadline.

### 10.1. Correct pattern: the action does not retain the referent

Illustrative pattern:

```java
import java.lang.ref.Cleaner;

final class ManagedHandle implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private boolean cleaned;

        @Override
        public synchronized void run() {
            if (cleaned) return;
            cleaned = true;
            // Release the native resource managed by State.
        }
    }

    private final State state = new State();
    private final Cleaner.Cleanable cleanable =
            CLEANER.register(this, state);

    @Override
    public void close() {
        cleanable.clean(); // explicit cleanup, idempotent by state
    }
}
```

This is an **illustrative class**, not opening a real resource. Most importantly: `State` is a static nested class, so it does not accidentally capture `ManagedHandle.this`. If the cleaning action holds a strong reference to the referent, it can prevent the referent from **ever becoming phantom reachable**, causing cleanup not to be triggered by the GC.

### 10.2. What `Cleaner` does not guarantee

- Does not guarantee the callback runs immediately after the `}` brace.
- Does not guarantee the callback runs within a fixed deadline.
- Does not guarantee the callback runs before the process is killed.
- Does not replace transaction management, locks, or filesystem sync mechanisms.
- Not suitable for executing critical business logic where missing cleanup would cause loss of correctness.

Designs should make **`close()` the primary path**; Cleaner is only a secondary safety layer when appropriate.

### 10.3. Do not use `finalize` for new code

`Object.finalize()` has been deprecated for removal since JDK 18, and JEP 421 describes the roadmap for removing finalization. Java SE 26 allows implementations to disable finalization, so new code should not be built relying on finalizers being run.

Limitations of finalization include:

- Execution timing and thread are indeterminate.
- Cleanup may be delayed for a long time or never happen before the JVM exits.
- Finalizer code can cause concurrency/security issues.
- Can cause object resurrection or retain objects longer than expected.
- Error paths and dependencies between finalizers are hard to control.

Preferred replacement: **`AutoCloseable` + try-with-resources**; for cases needing a non-deterministic fallback, `Cleaner` or `PhantomReference` following official API guidelines.

## 11. Standalone Java 17+ example: scope ends but object is still usable

Create the file **`ObjectReachabilityDemo.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

public final class ObjectReachabilityDemo {
    private static final List<Object> REGISTRY = new ArrayList<>();

    static final class Ticket {
        final String name;
        Ticket(String name) { this.name = name; }
    }

    static Ticket makeTicket() {
        Ticket local = new Ticket("returned");
        return local;
    }

    static void saveFromBlock() {
        {
            Ticket local = new Ticket("stored");
            REGISTRY.add(local);
        }
    }

    static Runnable makeCallback() {
        Ticket captured = new Ticket("callback");
        return () -> System.out.println("captured: " + captured.name);
    }

    static final class Resource implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) throw new IllegalStateException("closed");
            System.out.println("resource used");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("resource closed");
        }
    }

    public static void main(String[] args) {
        Ticket returned = makeTicket();
        System.out.println("returned local survives: " + returned.name);

        saveFromBlock();
        System.out.println("stored outside block: "
                + ((Ticket) REGISTRY.get(0)).name);

        Runnable callback = makeCallback();
        callback.run();

        try (Resource resource = new Resource()) {
            resource.use();
        }

        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);
        System.out.println("weak while strongly reachable: "
                + (weak.get() != null));
        Reference.reachabilityFence(strong);

        REGISTRY.clear();
        System.out.println("registry size after clear: " + REGISTRY.size());
        System.out.println("collection time: not guaranteed");
    }
}
```

Compile and run on **JDK 17 or later**:

```bash
javac --release 17 ObjectReachabilityDemo.java
java ObjectReachabilityDemo
```

**Exact stdout:**

```text
returned local survives: returned
stored outside block: stored
captured: callback
resource used
resource closed
weak while strongly reachable: true
registry size after clear: 0
collection time: not guaranteed
```

This code is designed **not to depend on GC timing**. It does not assert that the weak reference must become null after `System.gc()` or that the object has been reclaimed immediately after `REGISTRY.clear()`.

### 11.1. `returned local survives: returned`

In `makeTicket()`, the local `local` exists in a method frame and returns the reference to the caller. After the frame ends, the caller's `returned` still points to the same `Ticket`. The scope of the `local` variable ending **does not destroy the Ticket**.

### 11.2. `stored outside block: stored`

`saveFromBlock()` puts the Ticket into `REGISTRY`, which is a static collection. Even though `local` is no longer in scope, the registry still has a reference. When `main` reads `REGISTRY.get(0)`, the object is still accessible.

This is a small example of a retention path causing memory retention when caches/listeners/registries store data longer than intended.

### 11.3. `captured: callback`

`makeCallback()` returns a lambda that uses `captured`. The callable object retains the data needed to execute the callback after the method has returned. As long as the callback is alive, the captured object can remain alive.

When registering callbacks to an event bus or scheduler, consider when to **unsubscribe/cancel**, because if the registry holds the callback long-term, the objects captured by the callback can also be retained long-term.

### 11.4. `resource used`, `resource closed`

The resource is conceptually opened, used within try-with-resources, and then `close()` is called, observable via the stdout lines. This is an example of **deterministic release** of a resource lifecycle; it is not a Java heap GC event.

### 11.5. `weak while strongly reachable: true`

In the code region containing `strong` and the `Reference.reachabilityFence(strong)` call afterward, the object must remain strongly reachable during the corresponding observation segment. `weak.get()` returns the uncleared referent, so this line is true.

Note that `WeakReference` does **not** by itself cause the object to live longer once no strong path remains. The code does not attempt to measure when the GC will clear the weak reference.

### 11.6. `registry size after clear: 0`

`REGISTRY.clear()` leaves the list with no elements. This is determinable by Java semantics. It **does not prove all Ticket objects have been reclaimed**, because the objects might be held elsewhere, and the GC might not have run yet.

## 12. Demonstrations that should not be turned into unit tests with fixed stdout

Quick test pattern:

```java
Object o = new Object();
WeakReference<Object> ref = new WeakReference<>(o);
o = null;
System.gc();
System.out.println(ref.get() == null);
```

**This is an unreliable test example, not a standard practice.** The last line may print true or false depending on JIT, GC, heap pressure, timing, and reachability. No Java specification states that `System.gc()` forces all weak references to be processed immediately before the next line.

Another incorrect example:

```java
void test() {
    byte[] block = new byte[10_000_000];
} // Conclusion: heap used must drop by exactly 10MB right here.
```

This reasoning is **invalid**; the collector may not have reclaimed it yet, heap used/committed levels have noise, objects have overhead, and the runtime may optimize.

### 12.1. `System.gc()` is a request/hint, not a mandatory schedule

The `System.gc()` documentation describes **suggesting** that the VM expend effort toward recycling unused objects. The VM may limit/ignore the request under appropriate configurations; effectiveness depends on the collector/JVM.

Even when GC runs, that is not proof that all resources have been closed or that memory has been returned to the OS.

### 12.2. Do not use `Thread.sleep` to "wait for GC for sure"

```java
System.gc();
Thread.sleep(1000);
// No guarantee the object has been reclaimed.
```

One second is only a thread wait time. It creates no guarantee about collection timing, enqueuing weak references, or running a Cleaner. Unit tests should rely on **specified behavior**, not lucky timing.

## 13. ThreadLocal and thread pools: short scope, long retention

`ThreadLocal<T>` holds data attached to **a thread** rather than following the lexical scope of the method calling `set()`. In a thread pool environment, worker threads typically live across many requests.

Illustrative example:

```java
private static final ThreadLocal<byte[]> BUFFER =
        new ThreadLocal<>();

static void handleRequest() {
    BUFFER.set(new byte[1024 * 1024]);
    try {
        // Handle request using BUFFER.get() when needed.
    } finally {
        BUFFER.remove();
    }
}
```

This snippet is **not standalone**; it needs to be placed in a class and called appropriately. Key takeaways:

- Local variables in `handleRequest()` disappearing after return **do not guarantee the ThreadLocal value is removed**.
- A continuing worker thread in a thread pool can retain the entry/value across requests.
- `BUFFER.remove()` in `finally` is an appropriate cleanup strategy when the request finishes, if there is no need to retain state across requests.

Do not infer "ThreadLocal keys are weak references so all values are removed immediately when the key is gone" — thread-local map entries/cleanup behavior and specific retention paths must be analyzed according to the runtime.

### 13.1. Similar retention patterns

- Global static collections holding request contexts.
- Uncancelled scheduled tasks holding callbacks and captures.
- `CompletableFuture` chains holding lambda closures or intermediate results.
- Unregistered event listeners holding owner objects.
- Thread context class loaders holding plugin loaders.
- Unbounded caches or caches with incorrect eviction policies.
- Native references/JNI handles holding Java objects or native resources.

In every case, the issue is not the variable's braces, but **which reference edges still exist**.

## 14. Class loaders and class metadata lifetime

In HotSpot, class metadata is tied to runtime classes and class loader data. A loader can define many classes; if the host continues to keep the loader or its classes/instances reachable, **class unloading** may be prevented.

Plugin example:

```text
Host static registry
       |
       v
Listener (plugin class)
       |
       v
Plugin ClassLoader
       |
       v
Plugin class metadata
```

If plugin code returns from a method and all local variables have gone out of scope, yet the host still holds the listener, the class loader can still survive long-term. Therefore, **Metaspace growth** can be related to object reachability on the heap and class loader retention.

To unload a plugin cleanly, you need to:
 
- Unregister listeners/callbacks.
- Cancel tasks/executors and release thread context class loaders appropriately.
- Clear cached plugin instances/references.
- Close plugin resources according to the ownership contract.
- Ensure the host does not retain reflection `Class`/`Method` or closures when no longer needed.

Closing a `URLClassLoader` does not by itself force the VM to unload classes immediately. Class unloading also depends on GC, VM, and reachability.

## 15. Distinguishing memory leaks, intended retention, and reachable objects

### 15.1. What does "memory leak" usually mean in Java?

In a managed heap, a common type of leak is **objects no longer needed for business logic that are still reachable through references**. The GC is doing its job: it does not reclaim objects that the program still has a path to use, even though by design those references should have been dropped.

Example:

```java
static final java.util.List<byte[]> HISTORY =
        new java.util.ArrayList<>();

static void onRequest() {
    HISTORY.add(new byte[1024 * 1024]);
}
```

This is an illustrative class fragment. If `onRequest()` is called continuously while `HISTORY` has no size limit/no eviction, the heap can grow until `OutOfMemoryError`. The bug is not in the local scope of `onRequest`; it is in **the static root and collection retention**.

### 15.2. Reachable does not necessarily mean a leak

A bounded cache, a queue with consumers, or a data store holding objects for business purposes may be **intended retention**. Do not treat all objects surviving GC as a "memory leak".

An investigation needs to answer:

1. Who owns the object?
2. Is the object still needed for later work?
3. What is the eviction/release policy?
4. Is growth proportional to valid workload?
5. After the workload finishes, does retained heap drop or stabilize?

### 15.3. Unreachable yet memory has not dropped does not necessarily mean a leak either

If an object is no longer reachable but the GC has not run yet, heap used may remain high. If the GC has reclaimed it, heap **committed** may still be retained to serve subsequent allocations; RSS does not necessarily drop immediately.

Therefore, do not just look at **`Runtime.totalMemory()`** or an RSS chart and conclude objects are still alive. One must distinguish between allocated, live/retained, committed, and resident.

## 16. Escape analysis, scalar replacement, and limits of inferring from `new`

HotSpot can optimize allocations using techniques like **escape analysis** and **scalar replacement** when conditions allow:

```java
static int sumPoint() {
    Point p = new Point(3, 4);
    return p.x + p.y;
}
```

This is illustrative code; `Point` needs to be defined. If the compiler proves that object `p` does not escape the method and the operations can be represented by scalar values, the VM can avoid materializing a full heap object on some execution paths.

This does not change logic: the caller still receives the sum according to Java semantics. However, it shows that the claim "every `new` always causes heap usage to increase by an observable number of bytes" **is not a guarantee**.

### 16.1. Escape analysis is not a proof of business correctness

Optimizations must preserve observable semantics. It does not promise to occur for every object or every JDK, nor does it prevent leaks when the application actually stores the object in a static registry.

### 16.2. Source object lifetime differs from runtime lifetime

With optimizations, an object may:

- Be materialized on the heap.
- Have its allocation eliminated by scalar replacement when appropriate.
- Be retained due to another callback/field/GC root.
- Become no longer needed earlier than the source brace.
- Be reclaimed by the GC in a later cycle.

Therefore, one cannot deduce the GC schedule backward from block syntax or declaration order.

## 17. Investigation techniques using GC logs, JFR, and heap dumps

When an application experiences memory pressure, **runtime evidence** is needed instead of guessing variable scopes.

### 17.1. GC logging in HotSpot

Example:

```bash
java -Xlog:gc* -jar application.jar
```

This is an illustrative command for a runnable JAR. HotSpot Unified Logging supports tags/levels depending on the version. Logs help observe GC cycles, heap occupancy, and information provided by the collector, but **do not by themselves show which reference edge is holding a specific object**.

### 17.2. JFR: allocations and pressure

**Java Flight Recorder (JFR)** helps observe allocation patterns, GC pauses, heap summaries, and some stack traces according to recording configuration. Specific events and sampling options vary across JDKs/builds.

Use JFR to ask: "Where are many objects being created?", "What is the allocation rate?", "Is the GC keeping up with the workload?". To ask "Who is still holding the object long-term?", you may need to combine it with a heap dump or retention analysis tool.

### 17.3. Heap dump and path to GC root

A tool such as Eclipse Memory Analyzer or a heap dump analyzer can show:

- **Shallow heap:** the size of the object itself.
- **Retained heap:** the amount of memory that the object's retention path can keep according to dominator/reachability analysis.
- **Paths to GC roots:** the reference paths through which the object remains reachable.
- Instance counts by class, collection entries, retained listeners, and class loaders.

Example workflow:

1. Capture a heap dump after the workload has stabilized.
2. Repeat the workload suspected of leaking.
3. Capture the next heap dump after appropriate GCs/conditions.
4. Compare counts/retained sizes.
5. Inspect paths to GC roots for groups of objects growing abnormally.
6. Identify the owner that needs to release them in code.

Heap dumps contain sensitive data that may reside in objects, so you must protect the file, restrict access permissions, and delete it properly. Taking a dump in production can consume disk, I/O, pause time, and memory; proper operational planning is required.

### 17.4. `jcmd` on HotSpot

Diagnostic example (substitute a specific PID):

```bash
jcmd -l
jcmd <pid> GC.class_histogram
jcmd <pid> GC.heap_dump /path/to/heap.hprof
```

`<pid>` and the path are placeholders used during actual operation, not commands already run on the reader's system. `GC.class_histogram` can incur significant overhead and some related modes require a safepoint/GC; a heap dump can be very large.

Do not use a histogram alone to conclude exactly who is holding an object. A histogram tells **how many instances exist by type**, whereas path-to-root helps answer **why they are still reachable**.

## 18. Reachability and the Java Memory Model in concurrency

Objects can be shared across threads via fields/queues. However, **reachability does not replace memory visibility or synchronization**.

Example:

```java
class Holder {
    Object value;
}
```

If thread A writes `holder.value = object` and thread B reads `holder.value` without a happens-before relationship or appropriate synchronization, the program can have a data race. The GC/JVM must still manage references safely according to runtime rules, but that **does not make object publication thread-safe**.

To share properly, use mechanisms such as:

- `final` fields with proper initialization discipline.
- `volatile` references for visibility when appropriate.
- `synchronized` or locks.
- Concurrent collections, blocking queues.
- Safe publication rules according to the Java Memory Model.

**The GC keeping an object alive** and **thread B seeing the correct object state** are two different issues. Do not use "the object is still reachable" as proof that data in its fields has been safely published.

### 18.1. Callback scheduling

If a callback runs asynchronously, the callback can retain captured references until the task completes or is cancelled and removed from the scheduler. This is a retention path independent of the lexical scope of the method that created the callback.

For example, an uncancelled scheduled task can retain an object graph for hours after the original HTTP request has already returned a response.

## 19. Classification table of common scenarios

| Scenario | Can you infer for sure from scope? | Correct understanding |
| --- | --- | --- |
| Method returns object created in local | **Cannot** conclude object is dead | Caller holds the returned reference |
| Local exits block but static list still contains object | **Cannot** conclude reclamation | Strong reference from registry remains |
| Local still in block but no longer used | **Not** guaranteed to keep object until `}` | JIT may shorten live range |
| `local = null` | **Does not** force collection | Only drops one reference edge; other edges may remain |
| `System.gc()` | **Does not** guarantee all objects are reclaimed immediately | GC scheduling/behavior depends on runtime |
| `WeakReference.get() == null` | Can know the weak referent has been cleared | Cannot measure exact time of death or external cleanup |
| `WeakReference.get() != null` | There is a reference retrievable at that moment | Does not promise the referent survives forever without a strong reference |
| `PhantomReference.get()` | **Always null** | Use queue/cleanup, do not dereference |
| `Reference.reachabilityFence(x)` | Guarantees live reachability across the call | Does not auto-close/free or pin address |
| `AutoCloseable.close()` | Resource cleanup per API contract | Java object may still be reachable after close |
| `Cleaner` registered action | Does not promise when the action runs automatically | Explicit close should still be the primary path |
| `ThreadLocal` in a thread pool | Request scope does not determine retention | Thread lifetime/value removal matters |
| Object cycle with no root | May be eligible for GC | Not immortal due to reference count > 0 |
| Static collection growing indefinitely | Likely retention/leak | Check owner, eviction, and path-to-root |
| Heap committed does not drop immediately | Does not prove a leak | GC/allocator may retain heap for reuse |

## 20. Common misconceptions

### Misconception 1: "Leaving scope calls a destructor"
Java does not have C++-style scope-bound destructors for Java heap objects. Block closing braces control variable scope, not direct heap memory reclamation. For closeable resources, use try-with-resources.

### Misconception 2: "`local = null` will immediately reduce RSS"
No. The object may still have references, the GC may not have run yet, and committed heap may not be returned to the OS.

### Misconception 3: "If an object is still in scope, the GC cannot reclaim it"
Incorrect. The compiler/JIT can shorten the strong-reachability period when no computation needs the object anymore; `Reference.reachabilityFence` exists precisely to indicate a final use when needed.

### Misconception 4: "A cycle of self-referencing objects prevents GC from reclaiming them"
No. If the entire cycle is no longer reachable through appropriate roots, a tracing collector can reclaim those objects.

### Misconception 5: "`WeakReference` automatically destroys the object when no references remain"
No. WeakReference participates in the collector's reference processing; it does not call "delete object" at a deterministic Java instruction.

### Misconception 6: "`SoftReference` has a fixed TTL defined by Java"
No. Soft reference clearing is decided by the VM/GC within the specification and memory pressure.

### Misconception 7: "`PhantomReference.get()` returns the object right before it dies"
False. `get()` returns null. Phantom references are not used to resurrect/dereference an object.

### Misconception 8: "`Cleaner` is a deterministic replacement for `close`"
False. Cleaner has no deadline guarantee; explicit close should be preferred.

### Misconception 9: "Finalizers are guaranteed to be called before process exit"
False. Finalization is deprecated for removal, can be disabled/removed, and provides no guarantee on timely cleanup needed.

### Misconception 10: "A static reference only holds an object while the method is running"
False. A static reference can hold an object across many requests, depending on class-loader lifetime and where it is cleared.

### Misconception 11: "ThreadLocal keys are weak, so values always disappear automatically"
False. ThreadLocal value retention in thread pools needs explicit handling; `remove()` in `finally` is an appropriate design.

### Misconception 12: "A memory leak in Java means the GC is not working"
No. The GC may be working properly, yet unable to reclaim objects that remain reachable because the application holds unnecessary references.

### Misconception 13: "A heap dump contains every object ever created"
No. A heap dump is a snapshot of objects recorded by the runtime according to the specific dump mechanism, not a complete log of all allocations that have occurred.

### Misconception 14: "Running a test 100 times and seeing a weak ref cleared is a timing guarantee"
No. GC and reference processing do not have a corresponding simple portable deadline.

### Misconception 15: "`Reference.reachabilityFence` pins an object at a fixed address"
No. It guarantees reachability past the call site, not preventing a moving GC.

## 21. Self-check exercises with answers

**Question 1.** A local `User user` exits its block, but `cache.put(key, user)` was executed. Can you conclude that User is GC'd immediately?

**Answer:** No. The cache may still hold a strong reference to User; you must examine paths to root and the eviction policy.

**Question 2.** `method()` returns a newly created object. After the method finishes, must the object disappear?

**Answer:** No. The caller receives the reference and can continue using the object.

**Question 3.** An object is no longer used after line 20, but the variable is declared at the start of the method and `}` is on line 200. Is the object guaranteed to stay alive until line 200?

**Answer:** No. The compiler/JIT can end the live range earlier when valid. Do not infer lifetime from lexical scope.

**Question 4.** Does writing `x = null; System.gc();` prove that x's object has been reclaimed immediately?

**Answer:** No. Other references may exist; `System.gc()` provides no such guarantee.

**Question 5.** Two Nodes hold references to each other, but no root path remains. Can they be eligible for GC?

**Answer:** Yes. Cyclic references do not keep objects alive on their own if the entire cycle is unreachable from roots.

**Question 6.** `WeakReference` is used as a key in a map, but the map's value holds a strong reference back to the key. What problem can occur?

**Answer:** A strong path through the value can keep the key reachable, preventing the expected GC-based cleanup. The reference graph of the entire map must be analyzed.

**Question 7.** `SoftReference.get()` returns null on one run; must it return null on the next run at the same amount of free heap?

**Answer:** No. Clearing policy/timing depends on the collector and runtime.

**Question 8.** When should `Reference.reachabilityFence(owner)` be used?

**Answer:** When you need to ensure the owner wrapper remains strongly reachable until after a segment of work, especially native-resource code that might only use an address/handle detached from the Java reference.

**Question 9.** Can `reachabilityFence` replace `close()`?

**Answer:** No. It does not release resources; it only ensures reachability at the call site.

**Question 10.** Why should try-with-resources be used for a file stream?

**Answer:** Because deterministic closing by program control flow is needed, without waiting for the GC to decide when the resource wrapper is unreachable.

**Question 11.** A `ThreadLocal` retains byte arrays across HTTP requests on the same worker thread. How can this be fixed?

**Answer:** Use `try/finally` with `ThreadLocal.remove()` if the data scope is only within the request; avoid retaining object graphs for too long.

**Question 12.** Does an object appearing in a heap dump mean there is a memory leak?

**Answer:** No. It could be valid live data. You need to look at ownership, retained size, path to root, and growth trend.

**Question 13.** An object has a `final` field holding a reference to a child. Does this mean the child lives forever?

**Answer:** No. The child can be kept while the parent is reachable; if the entire parent-child graph is no longer reachable, `final` does not make it immortal.

**Question 14.** Should you test GC by asserting `weak.get() == null` after `Thread.sleep(500)`?

**Answer:** No. This is a timing-dependent test with no portable guarantee.

**Question 15.** Does increasing `-Xmx` cure all memory leaks?

**Answer:** No. It may delay an OOME for a retention problem, but it does not fix the path retaining the objects. Native memory/resource leaks are also a separate issue.

## 22. Checklist for analyzing object lifetime in real projects

1. Identify **which object** needs to be managed and what "no longer needed" means in business terms.
2. Distinguish **source scope**, **reference liveness**, and **heap reachability**.
3. Draw **strong reference paths** from owners/roots.
4. Check static registries, caches, listeners, callbacks, ThreadLocals, executors, and class loaders.
5. Identify explicit ownership/release APIs: `remove`, `clear`, `cancel`, `close`.
6. For resources, use try-with-resources and define exception handling paths.
7. For weak/soft/phantom references, do not rely on timing/number of GC runs.
8. For Cleaner, ensure the cleaning action does not accidentally capture the referent; do not treat it as primary cleanup.
9. If a native resource wrapper has a sensitive lifetime, study placing `Reference.reachabilityFence` in the right spot.
10. Use heap dumps/JFR/GC logs for their proper purposes; protect sensitive data.
11. Compare memory trends across multiple workloads/GCs, not a single snapshot.
12. Check Java heap, Metaspace, thread stacks, and native resources when RSS grows.
13. Do not use `System.gc()`, `finalize`, or `Thread.sleep` as lifecycle design.
14. Test paths for unregistering listeners, closing pools/executors, unloading plugins, and shutting down the application.
15. Separate **correctness**, **resource safety**, and **performance** into independently observable requirements.

### Summary

```text
Source variable scope
     |  specifies where the variable name can be used
     X  NOT a lifetime contract for the heap object
     |
     v
Reference graph (strong / soft / weak / phantom)
     |
     v
Object reachability per VM/reference processing
     |
     v
Eligible for reclamation when conditions are met
     |
     v
GC may reclaim according to runtime schedule

Additionally:
  AutoCloseable / try-with-resources
       → deterministic resource cleanup
  Reference.reachabilityFence
       → guarantees strong reachability up to a point
  WeakReference / Cleaner
       → GC interaction, no reclamation deadline
```

**Key takeaway:** **Do not infer when an object dies or is reclaimed solely from the scope of a Java variable.** Analyze the reference graph, actual live range, optimization behavior, and the JVM's reference/GC contracts. For critical resources, manage lifecycles proactively instead of waiting for the collector.

### Official documentation

- [JVMS `2.5.3 — Heap (Java SE 26)](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html#jvms-2.5.3): heap objects and automatic storage management.
- [JLS `12.6.1 — Implementing Finalization (Java SE 26)](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.6.1): reachability, optimizer can reduce live references, finalization history.
- [java.lang.ref — Package Specification (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): reachability levels and meaning of soft/weak/phantom references.
- [Reference.reachabilityFence (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)): guaranteeing reachability up to a specific point.
- [Cleaner (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): cleaning actions and limitations of non-deterministic cleanup.
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): why not to build new lifecycles on `finalize`.
- [JLS `14 — Blocks and Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html): scope and control flow in Java source.
- [Oracle JDK 17 — HotSpot GC Tuning, Other Considerations](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html): soft, weak, phantom references and GC mechanisms.
