# Strong, Soft, Weak, and Phantom References in `java.lang.ref`

**Whether an object is still reachable or not** directly affects whether the garbage collector (GC) can reclaim it. However, “there is a variable holding a reference” is not enough to conclude that the object must stay alive forever: Java distinguishes **strong**, **soft**, **weak**, and **phantom references**, with different reachability rules. These mechanisms are important for caches, weak-key maps, canonicalization, metadata management, and cleaning up resources outside the Java heap.

This article belongs to the **Reachability** section in Java Advance – JVM. The goal is to understand the object graph from the JVM's perspective, how to use `java.lang.ref` according to the Java 17 contract, when `Reference.get()` returns `null`, the roles of `ReferenceQueue` and `Cleaner`, and what **cannot be predicted accurately** because GC is asynchronous.

In particular, distinguish:

- **Strong reference** is the ordinary reference that Java code uses; an object that is still strong-reachable **is not reclaimed** just because GC runs.
- **`SoftReference<T>`** allows an object to be retained when memory permits, but GC can clear the reference due to memory demand; it is not a cache contract with a fixed retention duration.
- **`WeakReference<T>`** does not keep the referent alive when only weak reachability remains; used for metadata/canonical mappings and as the foundation of weak keys.
- **`PhantomReference<T>`** does not allow retrieving the referent via `get()`; it works with `ReferenceQueue` to receive a signal for cleanup after the referent is no longer used.
- **`ReferenceQueue<T>`** delivers information about **reference objects**, not directly “returning dead objects”.
- **`Cleaner`** (Java 9+) builds on phantom-reference processing to register cleanup actions; **`AutoCloseable` and try-with-resources** should still be the way to close resources on time.

## 1. Reachability: GC looks at the reference graph, not variable names

To understand the four reference levels, first picture **GC roots**: sources considered by the JVM as starting points for finding objects that can still be used by the program, such as live Java thread-local state, applicable static state, and special sources managed by the VM/JNI.

```text
GC roots
   │
   ├── strong ──► User ──► strong ──► Address
   │
   └── strong ──► WeakReference ── weak ──► CachedObject
                                       │
                        no other strong path?
                                       │
                                GC may clear weak
```

What matters is the **edge type on the graph**. A `WeakReference` object itself may be held by a strong reference; however, the link from `WeakReference` to the target object (**referent**) has **weak** semantics. Holding a `WeakReference` in a `static final` does not automatically turn the referent into strong-reachable.

Not all fields pointing to objects have the `WeakReference` type. Variables/fields/array elements containing ordinary Java references create strong edges, unless the API containing them has a special reachability specification.

### 1.1. Is “Strong reference” a class?

No. Java does not have `new StrongReference<>(obj)` in `java.lang.ref`. “Strong reference” describes the fact that you **directly** have a reference in Java such as:

```java
Object value = new Object();
Object alias = value;
```

Both `value` and `alias` hold ordinary references to the same object. If they are still actually used, the object does not become weakly reachable just because the code also creates a `WeakReference<>(value)`.

### 1.2. Leaving the `}` brace does not mean GC must reclaim

A local variable leaving its lexical scope **does not issue a GC command**. The JIT can even determine that an object is no longer used **earlier** than the end of the scope, while references in fields/statics/other stacks can keep the object alive longer.

Do not rely on source scope alone to measure enqueue timing or resource termination. When managing resources with observable side effects, `Reference.reachabilityFence` or explicit close may matter more than initially thought.

## 2. The order strong → soft → weak → phantom → unreachable

The Java 17 `java.lang.ref` package specification describes reachability levels in order from strongest to weakest:

| Level | Conceptual condition | Main consequence |
| --- | --- | --- |
| **Strongly reachable** | There is a path from a thread/root **without traversing reference objects** according to the reachability definition | GC must not reclaim the object just because GC is running |
| **Softly reachable** | No longer strong-reachable, but there is a path through a **soft reference** | GC may clear soft references according to memory demand |
| **Weakly reachable** | No longer strong/soft reachable, but there is a path through a **weak reference** | When GC determines weak reachability, it clears weak refs according to the rules |
| **Phantom reachable** | None of the above levels apply, has gone through finalization processing as defined, and has a phantom reference | Eligible for phantom-reference processing and notification |
| **Unreachable** | Does not belong to any of the above reachability levels | May be reclaimed by GC when appropriate |

This is a **GC-level classification**, not states that the program is allowed to set by writing an enum onto the object. A referent that is only weak-reachable can disappear from the perspective of `WeakReference.get()` when GC performs reference processing.

### 2.1. An object has only one “level” at a time based on the strongest path

Suppose an object has both a `SoftReference` and a `WeakReference` pointing to it:

```text
root ─► SoftReference ─soft─┐
                            ├──► Object
root ─► WeakReference ─weak─┘
```

If there is no strong path, it is **softly reachable**, not weakly reachable, because soft is stronger than weak. That can delay clearing the weak ref compared to the case with only weak. Once the soft references are cleared and no strong path remains, the object can become weakly reachable in an appropriate processing cycle.

Conversely, if there is another strong path, soft and weak refs pointing to the same object can usually still have `get()` return the object (if not actively cleared by the program via `clear()`). A soft/weak reference **does not force GC to clear** while the target is still strongly reachable.

### 2.2. There is no countdown timer for weak/soft

GC timing depends on heap pressure, the collector, safepoints, optimizations, reference processing, CPU, and where the object is still reachable from. **There is no contract such as “weak is cleared after N seconds”** or “soft lives until heap usage reaches 80%”. Such assumptions make unit tests flaky and cache behavior unpredictable.

## 3. Strong reference: the ordinary path that keeps objects alive

Ordinary fields, local variables, array elements, and method parameters can hold strong references when they are actually reachable sources. Example:

```java
import java.lang.ref.WeakReference;

public class StrongExample {
    public static void main(String[] args) {
        Object target = new Object();               // strong
        WeakReference<Object> weak = new WeakReference<>(target);

        System.out.println("alive=" + (weak.get() == target));
        java.lang.ref.Reference.reachabilityFence(target);
    }
}
```

Run:

```bash
javac --release 17 StrongExample.java
java StrongExample
```

Stdout:

```text
alive=true
```

`target` is a strong reference and is used in the comparison; `reachabilityFence(target)` keeps strong reachability up to the fence call site. GC is not allowed to clear the weak reference to target just because there is a weak wrapper while target is still strong-reachable.

### 3.1. A Java variable can be optimized out of liveness

For example, a native handle attached to a Java wrapper:

```java
long handle = resource.getNativeHandle();
useNativeHandle(handle);
// No longer reading any field of resource.
```

The JIT may consider `resource` no longer used after obtaining `handle`, even though the native work still uses the resource attached to it. If `Cleaner` reclaims the resource too early, native code may use a closed handle.

In an appropriate design, place `Reference.reachabilityFence(resource)` **after the last operation that needs the resource alive**:

```java
long handle = resource.getNativeHandle();
try {
    useNativeHandle(handle);
} finally {
    java.lang.ref.Reference.reachabilityFence(resource);
}
```

This is a **conceptual snippet**; `resource` and `useNativeHandle` must be defined yourself. The fence does not replace closing/locking the resource; it only ensures strong reachability at least up to the call site. `reachabilityFence` does not request GC to run.

## 4. `SoftReference<T>`: a cache that GC can free based on memory demand

`SoftReference` fits the idea **“keep a value while there is room, but let GC drop the cache when memory is needed”**. Common constructor:

```java
SoftReference<Image> ref = new SoftReference<>(image);
Image cached = ref.get();
```

This snippet is **illustrative** because it requires a defined `Image` class and `image` variable.

API:

- `new SoftReference<>(value)` creates a soft reference **without registering a queue**.
- `new SoftReference<>(value, queue)` registers with a `ReferenceQueue`.
- `ref.get()` returns the referent if still present, or `null` if the reference has been cleared by GC/code.
- `ref.clear()` actively clears it; it does not mean GC decided there was memory pressure.
- According to the Java 17 Javadoc, soft references still pointing to **softly-reachable objects** are guaranteed to be cleared before the VM throws `OutOfMemoryError` under the stated mechanism. That does **not** promise every kind of OOME can be prevented by a soft cache; native memory, too many threads, or a strong heap live set can still cause OOME.

### 4.1. Example of a cache that must always have a regeneration path

```java
import java.lang.ref.SoftReference;
import java.util.Objects;
import java.util.function.Supplier;

public class SoftCacheDemo {
    private static SoftReference<String> cached = new SoftReference<>(null);

    static String getOrLoad(Supplier<String> loader) {
        String result = cached.get();
        if (result == null) {
            result = Objects.requireNonNull(loader.get());
            cached = new SoftReference<>(result);
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("first=" + getOrLoad(() -> "DATA"));
        cached.clear();    // Clear manually to test the cache miss branch.
        System.out.println("second=" + getOrLoad(() -> "DATA"));
    }
}
```

Compile/run:

```bash
javac --release 17 SoftCacheDemo.java
java SoftCacheDemo
```

Deterministic stdout:

```text
first=DATA
second=DATA
```

This is a **single-threaded** demo for the hit/miss branch; the code uses `clear()` actively to create a controlled miss, **without pretending to simulate GC's memory pressure decision**. In a multi-threaded system, the code must synchronize/cache atomically to avoid duplicate loads and data races.

### 4.2. Why shouldn't `SoftReference` be the default cache strategy?

- The clearing policy is decided by the JVM/collector; the cache may hold data too long or lose data all at once under memory pressure.
- There is no capacity limit, TTL, eviction policy, or least-recently-used selection rule at the Java API level.
- Reconstructing values can cost CPU/I/O and cause a cache stampede when many values are cleared.
- Soft refs are also **objects** and have lookup/reference processing overhead.
- A soft cache holding lots of data changes the retained heap and GC activity.

For production caches needing quota/TTL/metrics/active eviction, it is usually more appropriate to use a cache with an explicit policy (for example, a bounded cache) instead of delegating all decisions to soft reachability.

## 5. `WeakReference<T>`: does not keep the referent alive

`WeakReference` is often used when an application **wants to remember an object as long as somewhere else still uses it**; when no strong/soft paths remain, GC can clear weak references according to the rules.

Conceptual example:

```text
App ──strong──► WeakReference<W>
                     │
                   weak
                     │
                     ▼
                Widget@123

If the app has no strong/soft path to Widget@123:
GC can detect weak reachability and clear the reference.
App still holds the WeakReference object, but get() later may be null.
```

### 5.1. `WeakReference` tests must not rely on fixed timing

A commonly seen example:

```java
Object obj = new Object();
WeakReference<Object> weak = new WeakReference<>(obj);
obj = null;
System.gc();
System.out.println(weak.get());
```

This is a **snippet WITHOUT fixed stdout**. `System.gc()` is a request; GC may not happen immediately or may be disabled; JIT liveness and other references also affect it. The result can be `null` or the object depending on execution timing.

Do not write unit tests like `assertNull(weak.get())` after a single `System.gc()`. To test logic when the referent disappears, use `weak.clear()` to create the scenario deterministically or separate the queuing part into an appropriate test.

### 5.2. Atomic read pattern: always store the result of `get()` in a strong local

```java
WeakReference<Resource> weak = obtainWeakRef();
Resource resource = weak.get();
if (resource != null) {
    resource.use();
}
```

This is an **illustrative snippet**; `Resource`/`obtainWeakRef` need to be declared in the application.

**Why store in a local?** If you call `weak.get()` multiple times, the first call may return the object, and the next call may return `null` when the referent is only weakly reachable in between. Reading once into the local `resource` creates a strong reference for the duration it needs to be used semantically; you can add `Reference.reachabilityFence(resource)` if work with the resource lies outside Java usage paths that the optimizer can easily observe.

Do not write:

```java
if (weak.get() != null) {
    weak.get().use();  // Risk: the second get() may be null.
}
```

`WeakReference` does not provide a contract that “between two `get()` calls there is never a GC”; using a strong local is the right way.

## 6. `WeakHashMap`: weak keys, but values are usually strong

`java.util.WeakHashMap<K,V>` is a very useful example of weak references:

- The map holds **keys via weak references**.
- Values are held via **strong references**.
- A key can be removed by GC if there is no longer ordinary strong/soft reachability from other paths.
- A mapping can disappear **even if code does not call `remove`**, so size/iteration behavior depends on GC.
- The map is **not automatically thread-safe**.
- `WeakHashMap` is not a `WeakReference` wrapping the entire Map object; it applies weak semantics to **keys**.

### 6.1. Runnable example with stable output

Create the file **`WeakMapDemo.java`**:

```java
import java.util.WeakHashMap;

public class WeakMapDemo {
    static class Key {
        final String code;
        Key(String code) { this.code = code; }
    }

    static class Value {
        final Key owner;  // Intentionally holds a strong reference back to key.
        Value(Key owner) { this.owner = owner; }
    }

    public static void main(String[] args) {
        WeakHashMap<Key, Value> map = new WeakHashMap<>();
        Key key = new Key("A");
        map.put(key, new Value(key));

        key = null;  // Only clears the strong local reference.
        System.out.println("size=" + map.size());
        map.clear();
        System.out.println("afterClear=" + map.size());
    }
}
```

Run:

```bash
javac --release 17 WeakMapDemo.java
java WeakMapDemo
```

Deterministic stdout:

```text
size=1
afterClear=0
```

**Why is there still 1 entry?** The map holds `Value` strongly; `Value.owner` in turn holds `Key` strongly. Even though the map itself uses weak keys, the graph has the chain:

```text
GC root → WeakHashMap → Value (strong)
                         │
                         └── owner (strong) → Key

WeakHashMap → weak key ──────────────► Key
```

This prevents the key from being only weakly reachable. When `map.clear()` is called, the application actively removes the mapping; the output `0` does not prove GC processed the key.

### 6.2. Common leak case with weak-key maps

A cache value can often accidentally reference back to the key—for example, the value is a `ListenerRegistration` holding the listener object that is also the key. The key remains reachable from the map value; the mapping does not disappear on its own.

Solutions depending on design:

- Value stores only information **that does not reference back to the key**.
- Use explicit `remove` when the business lifecycle ends.
- If weak values are needed instead of weak keys, design separately with `WeakReference<V>` or an appropriate cache library.
- If the key is a String literal/interned String, the key can live long; weak key **does not** act like a “TTL”.

## 7. `PhantomReference<T>`: receive notification without retrieving the object

`PhantomReference` is designed for end-of-lifecycle processing (post-mortem cleanup scheduling). The clearest difference compared to soft/weak:

**`PhantomReference.get()` always returns `null`**, even right after you create the reference while the referent is still strongly reachable.

A phantom reference needs a `ReferenceQueue` to have a useful notification channel:

```java
ReferenceQueue<Object> queue = new ReferenceQueue<>();
Object target = new Object();
PhantomReference<Object> phantom = new PhantomReference<>(target, queue);
```

With Java 17:

- `phantom.get() == null` is always true.
- `phantom.refersTo(target)` can check whether the phantom reference currently points to the object `target` (the `Reference.refersTo` method has existed since Java 16).
- When the collector determines the object is phantom-reachable by definition and the reference has not been cleared, the JVM can clear and enqueue the phantom reference according to the rules.
- `queue.poll()` receives the **PhantomReference object**, without letting you retrieve the referent that is no longer accessible via `get()`.
- If the constructor receives `queue = null`, the reference will **not be enqueued**.

### 7.1. Why not allow `get()` to read the referent?

If Java code were allowed to retrieve the referent via a phantom reference, retrieving it could make the object strong-reachable again and complicate cleanup. By always returning `null`, a phantom reference is used only as a **lifecycle signal**, not as a “backdoor” to access the object again.

For that reason, do not design a phantom cleanup action like:

```java
Object obj = phantom.get();
obj.close();    // Wrong: get() is always null.
```

You need to keep **separate cleanup information** (such as a file descriptor, native handle, resource id) without creating a strong path from the registry/callback back to the tracked object.

### 7.2. Do not confuse Java 8 phantom reference rules with Java 17

Java 17 documentation describes GC **clearing phantom references** when an object is phantom-reachable and then enqueuing them concurrently or afterward. Some very old documents (before the JDK 9 change) say phantom references are not automatically cleared upon enqueuing; **do not apply that legacy description verbatim to Java 17**.

In addition, semantics related to finalization do not guarantee that every program actually runs finalizers on time. Finalization has been strongly discouraged due to unpredictability, risks, and inheritance design; use `Cleaner` or explicit resource management instead of relying on `finalize()`.

## 8. Complete Java 17 program comparing the four reference types

Create the file **`ReferenceKindsDemo.java`**:

```java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;
import java.lang.ref.SoftReference;
import java.lang.ref.WeakReference;

public class ReferenceKindsDemo {
    public static void main(String[] args) {
        Object target = new Object();         // Strong reference.
        ReferenceQueue<Object> queue = new ReferenceQueue<>();

        SoftReference<Object> soft = new SoftReference<>(target);
        WeakReference<Object> weak = new WeakReference<>(target);
        PhantomReference<Object> phantom =
                new PhantomReference<>(target, queue);

        System.out.println("soft.same=" + (soft.get() == target));
        System.out.println("weak.same=" + (weak.get() == target));
        System.out.println("phantom.null=" + (phantom.get() == null));
        System.out.println("phantom.refersTo=" + phantom.refersTo(target));

        // Keep target strongly reachable throughout the checks above.
        Reference.reachabilityFence(target);

        // Create a cleared scenario WITHOUT depending on GC timing.
        weak.clear();
        soft.clear();
        System.out.println("weak.cleared=" + (weak.get() == null));
        System.out.println("soft.cleared=" + (soft.get() == null));
        System.out.println("queue.empty=" + (queue.poll() == null));
    }
}
```

Compile/run JDK 17:

```bash
javac --release 17 ReferenceKindsDemo.java
java ReferenceKindsDemo
```

**Deterministic stdout:**

```text
soft.same=true
weak.same=true
phantom.null=true
phantom.refersTo=true
weak.cleared=true
soft.cleared=true
queue.empty=true
```

Explanation:

1. `target` is kept strong up to `reachabilityFence`, so `soft.get()` and `weak.get()` both point to that object during the check.
2. `phantom.get()` is `null` **by API contract**, not because GC reclaimed the object.
3. `phantom.refersTo(target)` is `true` before being cleared, because it points to the `target` object.
4. `weak.clear()` and `soft.clear()` are **active clears**, not indicating GC decided the two referents were unreachable.
5. `Reference.clear()` **does not automatically enqueue the reference**, so the phantom queue remains empty in the example; target had no reason to be phantom-enqueued before the fence point. Do not use this result to infer GC will always run at another time.

### 8.1. `System.gc()` experiments are only for observation, not as deterministic tests

You can try creating many short-lived objects, dropping strong refs, and calling `System.gc()` to observe `WeakReference.get()` or the queue. However:

- `System.gc()` is a request/hint; JVMs have different rights regarding how to handle it.
- The compiler can end an object's strong reachability earlier than intuition suggests.
- There is no SLA for GC completing within 10 ms, 1 s, or a fixed number of iterations.
- Queue notification may arrive later than clearing references.
- Therefore, the learning example with fixed stdout above **actively uses `clear()` and `reachabilityFence`**, rather than promising a GC schedule.

## 9. `ReferenceQueue<T>`: receives registered references, does not retrieve dead objects

Reference queues support **reactive** programming on reachability changes.

Common constructor:

```java
ReferenceQueue<Resource> queue = new ReferenceQueue<>();
WeakReference<Resource> ref = new WeakReference<>(resource, queue);
```

The snippet above is illustrative and requires appropriate `Resource` and `resource`. The queue receives the **reference object** after it is enqueued by the JVM; it is not a queue containing a copy of the referent.

Important Java 17 APIs:

| API | Meaning |
| --- | --- |
| `new ReferenceQueue<T>()` | Creates a queue |
| `queue.poll()` | Immediately retrieves an enqueued reference or `null` if the queue is empty |
| `queue.remove()` | Waits until a reference is available; can be interrupted |
| `queue.remove(timeout)` | Waits at most timeout milliseconds, returns reference or `null` |
| `new WeakReference<>(obj, queue)` | Registers a weak reference with the queue |
| `new SoftReference<>(obj, queue)` | Registers a soft reference with the queue |
| `new PhantomReference<>(obj, queue)` | Registers a phantom reference with the queue |
| `ref.clear()` | Clears the referent, does **not** automatically enqueue |
| `ref.enqueue()` | **Actively** clears and enqueues a registered reference, if applicable |
| `ref.refersTo(obj)` | Checks referent identity, including for phantom references |

Do not rely on `Reference.isEnqueued()`: Java 17 **deprecated** this method due to race behavior/testing; use `poll`/`remove` results and your own management structure.

### 9.1. Collector-independent queue demo

Create the file **`ReferenceQueueDemo.java`**:

```java
import java.lang.ref.ReferenceQueue;
import java.lang.ref.WeakReference;

public class ReferenceQueueDemo {
    public static void main(String[] args) {
        Object target = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();
        WeakReference<Object> ref = new WeakReference<>(target, queue);

        System.out.println("before=" + (queue.poll() == null));
        System.out.println("manualEnqueue=" + ref.enqueue());
        System.out.println("cleared=" + (ref.get() == null));
        System.out.println("sameRef=" + (queue.poll() == ref));
        System.out.println("emptyAfterPoll=" + (queue.poll() == null));
        java.lang.ref.Reference.reachabilityFence(target);
    }
}
```

Commands:

```bash
javac --release 17 ReferenceQueueDemo.java
java ReferenceQueueDemo
```

Stdout:

```text
before=true
manualEnqueue=true
cleared=true
sameRef=true
emptyAfterPoll=true
```

Point to emphasize: `ref.enqueue()` is a **manual operation** to test the queue mechanism, not simulating that the collector actually confirmed target is weakly reachable. That `ref.get()==null` here is the result of explicit enqueue/clearing, even though `target` is still strongly reachable.

### 9.2. Must keep the reference object itself alive

The package specification emphasizes: `ReferenceQueue` **does not automatically track and retain every registered reference**. If the `WeakReference`/`PhantomReference` object becomes unreachable before GC wants to enqueue it, the application **has nothing left to observe**.

Therefore, tracking code usually must hold the reference objects in a strong collection until processing finishes:

```java
ReferenceQueue<Resource> queue = new ReferenceQueue<>();
Set<PhantomReference<Resource>> liveRefs = new HashSet<>();
PhantomReference<Resource> ref = new PhantomReference<>(resource, queue);
liveRefs.add(ref);
```

This is a **snippet**; it needs imports, `Resource`, and the `resource` variable. When retrieving a reference from the queue, the program looks up the corresponding cleanup info, removes the entry from `liveRefs`, and performs the resource work (without calling `get()` on the phantom to obtain the resource).

Be very careful: **the map from phantom ref to cleanup state must not accidentally hold a strong reference to the referent** — if it does, the object will not reach the phantom-reachable state to trigger cleanup.

## 10. `Cleaner`: instead of manually managing a low-level phantom queue

`java.lang.ref.Cleaner` (Java 9+) manages **phantom references + reference queue + cleaning actions** to reduce boilerplate. `Cleaner.register(object, action)` returns a `Cleanable` with a `clean()` method.

According to the Javadoc:

- The cleaning action may run **after the referent becomes phantom-reachable**, unless already run via explicit `clean()`.
- An action is run **at most once** through `Cleanable`.
- The action **must not strong-capture the registered object**; if it captures the object itself, that object can no longer become phantom-reachable and automatic cleanup will not occur.
- `Cleaner` has its own thread to run cleanup as configured; automatic cleanup timing is not guaranteed, and behavior on `System.exit` is implementation-specific.
- **Actively calling `clean()` inside `close()`** is a useful approach, but you still must design resource lifetime/ownership properly.

### 10.1. Runnable `Cleaner` and `AutoCloseable` example, independent of GC

Create the file **`CleanerDemo.java`**:

```java
import java.lang.ref.Cleaner;

public class CleanerDemo {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        @Override
        public void run() {
            System.out.println("released");
        }
    }

    static final class Resource implements AutoCloseable {
        private final Cleaner.Cleanable cleanable =
                CLEANER.register(this, new State());

        @Override
        public void close() {
            cleanable.clean();
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("using");
        }
        System.out.println("closed");
    }
}
```

Run:

```bash
javac --release 17 CleanerDemo.java
java CleanerDemo
```

Exact stdout:

```text
using
released
closed
```

`Resource` is closed **explicitly** by try-with-resources, so `close()` calls `cleanable.clean()` at a clear time and the action prints once. It does not rely on GC timing to determine stdout.

The program only **prints a line simulating cleanup**; it does not demonstrate releasing an actual socket/file descriptor. In production, `State` needs to hold the required resource state (for example, a native handle), and the action must be safe, idempotent, and hold no strong reference to `Resource`.

### 10.2. Mistake of capturing `this` in the cleaning action

**Wrong**:

```java
cleanable = CLEANER.register(this, () -> closeNativeField());
```

If the lambda calls an instance method/field of the registered object, it typically **captures `this`**. `Cleaner` holds the action, the action holds the object, and the object cannot become phantom-reachable; automatic cleanup therefore never runs as expected.

**Better**: create a `static` nested `State implements Runnable` containing the handle/metadata independent of the owner; register `new State(handle)` and ensure the reference graph does not lead back to the owner.

### 10.3. Explicit resource management is still the standard

`Cleaner` is a useful fallback mechanism when a resource is forgotten; it **does not replace**:

- `try-with-resources` for streams, files, sockets, DB connections, and `AutoCloseable`.
- `finally` to release resources in a deterministic scope.
- An idempotent/thread-safe `close` policy and clearly defined ownership transfer.
- Managing native handles so there is no use-after-close.

Waiting for GC to close network connections can exhaust file descriptors before the collector decides to process them. Do not design business correctness to depend on `Cleaner` running before a deadline.

## 11. Major mistake: a living reference object does not mean the referent is alive

One of the common graphs:

```text
static Set<WeakReference<Client>> tracked
       │
       ├─ strong ──► WeakReference #1 ── weak ──► Client A
       ├─ strong ──► WeakReference #2 ── weak ──► Client B
       └─ strong ──► WeakReference #3 ── weak ──► Client C
```

The application **holds wrapper refs strongly** to track the queue, but that does not force GC to keep Client objects alive. If there are no other strong paths to `Client B`, the weak reference can be cleared. That is precisely the goal of weak tracking.

However, if a value in a side map, listener list, or cleanup state points strongly back to Client, the situation changes to:

```text
static trackingData ──strong──► CleanupState
                                   │
                                   └─strong──► Client B
```

At this point Client B is still strongly reachable despite having weak/phantom refs. To find a memory leak, **read all incoming reference chains to the object**, not just whether the author used `WeakReference` in one field.

## 12. Distinguishing `Reference.get()`, `clear()`, `enqueue()`, and `refersTo()`

| Method | Soft/Weak | Phantom | Key point to remember |
| --- | --- | --- | --- |
| `get()` | Returns referent or `null` after clear | **Always `null`** | Does not prove the object was reclaimed or GC ran |
| `refersTo(obj)` | Compares referent identity per API | Also supported, Java 16+ | Usable when `phantom.get()` does not let you retrieve the object |
| `clear()` | Actively clears referent | Actively clears referent | Does not enqueue when calling `clear()` |
| `enqueue()` | Actively clears and enqueues if the reference is registered/applicable | Same per general API | Manual action; does not prove collector detected the state |
| `queue.poll()` | Retrieves an enqueued reference | Retrieves an enqueued reference | Does not retrieve the referent |
| `queue.remove(timeout)` | Waits for notification with a limit | Waits for notification with a limit | Can time out; does not guarantee the event occurs |

**Do not write an infinite wait loop yourself**:

```java
while (weak.get() != null) {
    System.gc();
}
```

The snippet above may never terminate, burns CPU, causes GC pressure, and still proves nothing about reclamation timing. GC tests should be separated from unit tests requiring deterministic stdout and must have explicit timeouts/acceptance of non-determinism.

## 13. Can an object “resurrect” after finalization?

In the historical finalization mechanism, a finalizer could create a new strong reference to the object, causing **resurrection**. This complicates reachability and lifecycle; Java finalization was deprecated since Java 9 and deprecated for removal by JEP 421 in JDK 18, for many safety/performance reasons.

With Java 17:

- Do not design new code based on `Object.finalize()` or an assumed finalizer invocation order.
- Accept that GC/ref-processing semantics are affected by lifecycle states described in the JVMS/Javadoc.
- `PhantomReference.get()` is always `null`, so it provides no way to resurrect the referent.
- `Cleaner` and `AutoCloseable` are more reliable in design, where **explicit close** provides a clear time for important resources.
- When reading Java 8 documentation, be cautious with `PhantomReference` descriptions that may differ from Java 17 regarding clear/enqueue.

If a program contains legacy finalization, check for strong-reference resurrection paths before explaining why an object still exists or why queue notification is delayed.

## 14. Practical diagnosis: memory leak or legitimate GC?

### 14.1. The difference between GC not running and an object still being strong-reachable

If `WeakReference.get()` still returns the object, it may be because:

- The object actually has a **strong path** from a static cache, thread, event listener, or JNI global reference.
- There is another **soft reference** keeping the object at the softly reachable level.
- GC has not yet performed weak ref processing under suitable conditions.
- A strong local created by `weak.get()` is holding the object while it is being used.
- The test itself holds the object in a variable/lambda/log statement to check identity and accidentally prevents collection.

Do not conclude “WeakReference is buggy” just because after one `System.gc()` you still see `get() != null`.

### 14.2. When `WeakHashMap` does not shrink

Check:

- **Values → keys** reference cycles originating from the map root.
- Are keys in another static collection?
- Are keys String literals/interned values or other long-lived objects?
- Is code holding an iterator/list snapshot and temporary references?
- Are weak keys actually needed, or does the business logic need explicit removal/TTL?

Even when Map entries disappear, that does not prove there are no leaks in other objects. Memory leak analysis must look at **retained paths** in a heap dump.

### 14.3. Commonly used Java 17 tools

```bash
# View JVM version:
java -version

# HotSpot heap class histogram at the time of inspection:
jcmd <pid> GC.class_histogram

# When permitted and in a suitable environment, create a heap dump:
jcmd <pid> GC.heap_dump /path/to/heap.hprof

# View actual VM flags in use:
java -XX:+PrintFlagsFinal -version

# GC logging by available tags on HotSpot:
java -Xlog:gc*=info YourApp
```

Notes:

- Heap dumps/histograms have significant overhead and can cause pauses; choose appropriate timing and access permissions.
- Heap dumps contain **sensitive** object data; do not share indiscriminately.
- There is no universal `-Xlog:weakreferencealways=true` flag across all JVMs; check the supported tags of the actual VM version if you need to analyze reference processing.
- `System.gc()` is a request, not a tool to control the GC schedule with an absolute deadline.
- G1, ZGC, Shenandoah, and different collectors/JDK releases have different reference processing strategies; **public Javadoc semantics** remain a more reliable source than a specific HotSpot timing.

## 15. Selection table by use case

| Use case | Should consider | Why | What to avoid |
| --- | --- | --- | --- |
| Business data currently in use, must remain alive | **Strong reference** | Keeps object reachable when needed | Switching to weak just to “save RAM” |
| Regenerable cache, can be lost when memory is low | **SoftReference** or a cache with an explicit policy | Soft gives GC a chance to drop values | Treating soft as a reliable TTL/eviction policy |
| Metadata map following the key object's lifecycle | **WeakHashMap** / weak keys | Does not retain keys just for metadata | Value holding a strong reference back to key |
| Canonicalization without wanting to keep all objects alive | **WeakReference** and an appropriate management table | Canonical entries can be dropped | Mixing with the JVM's `String.intern()` contract |
| Notification when the referent is no longer accessible | **PhantomReference + ReferenceQueue** | Gets cleanup signal without retrieving the object | `phantom.get()` or action holding strong referent |
| Lifecycle cleanup of native/file resources | **AutoCloseable + try-with-resources**, optionally supplemented by Cleaner | Explicit close is deterministic; Cleaner fallback | Waiting for GC as the sole closing policy |
| Reclaiming native buffers managed by the application | Explicit release, `Cleaner` when appropriate | Clear ownership | Expecting GC to arbitrarily `free` all native memory |
| Cache with TTL, LRU, metrics, max size | Bounded cache/explicit lifecycle | Has controllable policies | Using soft refs as a full cache framework |

There is no “best reference type”. The first question must be **until when does the object need to stay alive for business reasons?** Only then choose a compatible GC policy.

## 16. Common misconceptions

1. **“StrongReference is a class in `java.lang.ref`.”** False: a strong reference is an ordinary reference.
2. **“Having a `WeakReference` pointing to an object means the object will be GC'd immediately.”** False: other strong/soft paths and GC timing decide.
3. **“A soft reference is only cleared right at OOME.”** False: GC can clear it earlier depending on memory demand/policy.
4. **“A soft cache guarantees OOME will never happen.”** False: strong live data, native memory, and many other causes still trigger OOME.
5. **“`WeakReference` automatically calls `clear()` after exactly N seconds.”** False: there is no fixed time.
6. **“`System.gc()` definitely clears all weak refs before returning.”** False: there is no such timing guarantee.
7. **“If `weak.get()` returns an object, calling it again any number of times is safe.”** False: always hold a strong local while using it.
8. **“`WeakHashMap` uses weak for both keys and values.”** False: values are usually strong.
9. **“`WeakHashMap` always removes a key even if the value points back to the key.”** False: the value can maintain a strong path to the key.
10. **“`PhantomReference.get()` sometimes returns the object before GC.”** False: Java 17 always returns `null`.
11. **“A phantom reference can hold onto a resource to call `close()` when GC arrives.”** False: you cannot retrieve the referent via `get()`.
12. **“`ReferenceQueue` directly returns the reclaimed object.”** False: the queue contains **reference objects**.
13. **“`clear()` and `enqueue()` are the same operation.”** False: `clear()` alone does not enqueue.
14. **“When the queue is empty, all referents are still alive.”** False: GC may not have enqueued yet, the reference may not be registered, or the queue may have already been read.
15. **“No need to keep the reference wrapper because the queue holds it automatically.”** False: you must ensure the reference object stays reachable.
16. **“`Cleaner` always runs at JVM shutdown.”** False: there is no guarantee.
17. **“Letting a Cleaner lambda capture `this` is the most convenient.”** False: it can keep the referent alive forever.
18. **“`Cleaner` completely replaces `close()` and try-with-resources.”** False: GC-driven cleanup has no deadline.
19. **“A local variable leaving scope means the resource always lives until the closing brace.”** False: compiler/JIT liveness can end before that.
20. **“`reachabilityFence` is a command to run GC.”** False: it only establishes strong-reachability up to the fence point.
21. **“Using weak ref is the fix for every memory leak.”** False: the object graph may still hold other strong paths.
22. **“JDK 8 and 17 have identical PhantomReference clearing details.”** Incorrect when applying historical descriptions; read the docs for the right JDK.

## 17. Self-check and answers

**Question 1.** If an object is still referenced through an ordinary static field, does a `WeakReference` pointing to it allow GC to reclaim the object?

**Answer:** Not just because of the weak wrapper. The live static strong path keeps the referent strongly reachable.

**Question 2.** Both soft and weak refs point to an object, with no strong path. What is the reachability level?

**Answer:** **Softly reachable**, because soft is stronger than weak. GC may clear soft according to policy and then process the weaker state.

**Question 3.** Does `SoftReference.get()` returning `null` mean an OOME just occurred?

**Answer:** No. Soft may be cleared before OOME or actively cleared by the program via `clear()`.

**Question 4.** Can `WeakReference.get()` return an object one time and return `null` the next time?

**Answer:** Yes. If no strong reference to the referent is held between the two calls and GC processes it, the reference can be cleared.

**Question 5.** Why does `WeakMapDemo` still print `size=1` after `key=null`?

**Answer:** The map holds `Value` strongly, and `Value.owner` holds `key` strongly, so the weak key is not the only living path. The map's `clear()` removes the entry actively.

**Question 6.** What does `PhantomReference.get()` return when target is still strongly reachable?

**Answer:** **`null`**, because that is the fixed contract of `PhantomReference.get()` in Java 17.

**Question 7.** Why must you keep the `PhantomReference` object in a collection when using `ReferenceQueue`?

**Answer:** If the reference wrapper object itself becomes unreachable, the program may not receive notification. The queue does not automatically manage strong registration for all refs.

**Question 8.** Does `Reference.clear()` make the reference appear immediately in the queue?

**Answer:** No. `clear()` alone does not enqueue; `enqueue()` or collector processing enqueues according to the contract.

**Question 9.** In `CleanerDemo`, why is stdout deterministic without calling `System.gc()`?

**Answer:** Because try-with-resources calls `Resource.close()`, and `close()` calls `Cleanable.clean()` synchronously. Automatic GC cleanup is only a fallback.

**Question 10.** Why can the cleanup lambda `() -> closeNativeField()` prevent `Cleaner` from ever running automatically?

**Answer:** It typically captures `this` (the owner), while `Cleaner` holds the cleanup action strongly, creating a strong path to the referent.

**Question 11.** When native code uses a resource handle but the Java wrapper is no longer read, which API can help maintain strong reachability until after the native call?

**Answer:** `Reference.reachabilityFence(wrapper)` placed after the native operation, at the right place to ensure the wrapper remains strongly reachable.

**Question 12.** Does using `WeakReference` automatically make a collection thread-safe?

**Answer:** No. The managing data structure still needs its own synchronization/concurrency policy.

## 18. Summary in one diagram

```text
An object O on the heap
    ▲
    │
    ├── strong edge  → stays alive while a strong path remains
    │
    ├── soft edge    → GC may clear on memory demand
    │
    ├── weak edge    → does not keep O alive after strong/soft paths are gone
    │
    └── phantom edge → lifecycle notification only; get() is always null

ReferenceQueue:
    Weak/Soft/Phantom ref ──(enqueued when applicable)──► Queue
                                                            │
                                                  poll()/remove()
                                                            │
                                                  process reference object
                                                  DO NOT retrieve referent

Cleaner:
    Phantom/reference processing + cleanup action
      ├─ auto cleanup: no timing guarantee
      └─ explicit clean(): can run right at close()

Reference.reachabilityFence:
    Keeps strong reachability up to the call site,
    does not force GC or replace closing resources.
```

**Remember:** Strong refs are for objects still in use; Soft refs can serve as caches dependent on memory demand; Weak refs are suitable for metadata/canonical mappings that must not keep objects alive; Phantom refs are signals after an object is no longer ordinarily accessible, **not a backdoor to call methods on the object**. `ReferenceQueue` connects reference wrappers to a notification channel, `Cleaner` provides a cleanup abstraction, while `try-with-resources` is the reliable way to close resources deterministically. Always distinguish **reachability of the referent**, **lifetime of the reference object**, **lifetime of off-heap resources**, and **when GC executes**.

### Standard references

- [Java SE 17 — `java.lang.ref` package / Reachability](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html): strong, soft, weak, phantom levels and notification.
- [Java SE 17 — `Reference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html): `get`, `clear`, `enqueue`, `refersTo`, `reachabilityFence`.
- [Java SE 17 — `SoftReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/SoftReference.html): memory demand and OOME caveat.
- [Java SE 17 — `WeakReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): clear/enqueue semantics.
- [Java SE 17 — `PhantomReference` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html): `get() == null` and phantom reachability.
- [Java SE 17 — `ReferenceQueue` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/ReferenceQueue.html): polling and blocking notification.
- [Java SE 17 — `Cleaner` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): phantom-backed cleanup and action capture risk.
- [Java SE 17 — `WeakHashMap` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong values, cycles.
- [JLS Java SE 17 — Finalization of Class Instances (§12.6)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6).
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421).
