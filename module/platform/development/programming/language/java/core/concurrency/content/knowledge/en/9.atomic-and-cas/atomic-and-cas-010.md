# VarHandle: Atomic Access and Access Modes in Java

## 1. What is VarHandle and What Problem Does It Solve?

**`java.lang.invoke.VarHandle`** is a JDK API (introduced in Java 9, available in Java 17+) that describes how to access **a single variable** through a typed handle: an instance field, a static field, or an array element. Unlike a regular getter/setter, `VarHandle` allows selecting the **access mode** on each access: plain, opaque, acquire/release, volatile read/write, and—when the variable type supports it—atomic operations such as compare-and-set, compare-and-exchange, get-and-set, and get-and-add.

For example, the same `int` field can be read using `getVolatile` or atomically incremented using `getAndAdd`. The API brings low-level Java Memory Model (JMM) primitives to pure Java code without needing `sun.misc.Unsafe`.

Key points to keep in mind from the start:

- **A VarHandle is not the variable itself:** it is an object describing how to access a variable location. The actual data still resides in an instance, a static field, or an array.
- **The access mode determines the memory-ordering semantics** of *that specific access*; you should not assume every `get`/`set` automatically behaves like `volatile`.
- **A handle does not lock multiple fields at once.** The atomicity of `getAndAdd` or CAS applies to **a single variable location**; invariants spanning multiple variables require separate design.
- **Access permissions are still checked** when creating a handle via `MethodHandles.Lookup`; VarHandle is not a valid way to bypass encapsulation or module permissions.
- **Not every mode is valid for every field type.** You can check using `isAccessModeSupported(...)`; an unsupported mode throws `UnsupportedOperationException` when invoked.

In this article, we use Java 17+, standard JDK APIs, and general Java concurrency examples.

## 2. VarHandle Identifies "Which Variable" by Type and Coordinates

There are three common forms:

| Location type | How to create the handle | Coordinates on invocation | Example |
| --- | --- | --- | --- |
| **Instance** field | `lookup.findVarHandle(MyClass.class, "value", int.class)` | Receiver object | `VALUE.getVolatile(myObject)` |
| **Static** field | `lookup.findStaticVarHandle(MyClass.class, "total", int.class)` | No receiver | `TOTAL.getVolatile()` |
| **Array** element | `MethodHandles.arrayElementVarHandle(int[].class)` | Array and index | `ELEMENT.getVolatile(array, index)` |

`VarHandle.varType()` indicates the **value type** of the variable; `coordinateTypes()` indicates the **coordinate types** used to identify the location. For example, an instance field handle for `int value` has value type `int` and one coordinate for the owner object type; an `int[]` element handle has two coordinates: the `int[]` array and the `int` index.

### Creating a handle for a private field

Creating a handle within **the same class that declares the field** typically uses:

```java
private static final VarHandle VALUE;

static {
    try {
        VALUE = MethodHandles.lookup()
                .findVarHandle(MyClass.class, "value", int.class);
    } catch (ReflectiveOperationException e) {
        throw new ExceptionInInitializerError(e);
    }
}
```

This is a **snippet** of the initialization pattern; `MyClass` and imports are not declared here. Complete examples appear in later sections.

`findVarHandle` verifies the field name and its corresponding type; if the field is not found or access is not permitted, it may throw `NoSuchFieldException` or `IllegalAccessException` (both under `ReflectiveOperationException`). `MethodHandles.lookup()` carries the access rights of the calling class; across different classes or modules, do not assume permission to access private fields. `MethodHandles.privateLookupIn(...)` should only be used when the corresponding access/module openness requirements are met, not as a shortcut to bypass security.

**Note on `final` fields:** a handle can read a final field when permitted, but write access modes are generally **not supported** for final fields. Do not attempt to modify a final field through an invalid mode.

## 3. Access Modes and Memory-Ordering Guarantees

VarHandle categorizes access modes by data access semantics and ordering. The table below is a learning summary; full details are in the `VarHandle` Javadoc and the Java Memory Model.

| Typical Mode/API | Practical interpretation | Notes |
| --- | --- | --- |
| `get`, `set` | **Plain**: corresponds to normal variable access, adding no volatile-like cross-thread synchronization guarantees | Do not use plain to publish unsynchronized mutable state |
| `getOpaque`, `setOpaque` | **Opaque**: guarantees coherence/consistency at the level of the accessed variable, but weaker ordering than acquire/release | Does not automatically publish dependent data in other fields |
| `getAcquire` | **Acquire read**: subsequent accesses in the reading thread are not reordered before the acquire under the mode's constraints | Useful when reading a flag published by a writer via release |
| `setRelease` | **Release write**: prior accesses in the writing thread are not reordered after the release under the mode's constraints | Typically paired with `getAcquire` on **the same signal variable** |
| `getVolatile`, `setVolatile` | **Volatile**: reads/writes with `volatile` ordering/visibility guarantees | Stronger ordering, but two separate calls do not form a transaction |
| `compareAndSet`, `compareAndExchange` | **Atomic conditional update** | Used when you must check the current value and write atomically |
| `getAndSet`, `getAndAdd` | **Atomic read–modify–write** (on supported types) | Returns the value before the update; avoids lost updates like plain `x++` |
| `...Acquire`, `...Release`, `...Plain` variants | Versions with selected ordering guarantees for the corresponding atomic operation | Use only when you clearly understand that mode's memory contract |

These levels do not mean **plain = always immediately visible** or **volatile = multi-step business operations are automatically atomic**. The JMM defines relationships between actions; accidentally observing fresh data on a single run is not proof of safety.

### Plain access

`(int) VALUE.get(receiver)` and `VALUE.set(receiver, 42)` perform regular reads and writes. If one thread writes and another thread reads the same variable using plain access without another happens-before relationship, the program can have a **data race**. Do not replace `synchronized`, latches, or `volatile` with two plain calls just because they go through a `VarHandle`.

### Opaque access

`getOpaque`/`setOpaque` apply weak constraints aimed at low-level protocols that need coherence on a single location without full ordering relative to other locations. **Do not** infer that if a reader sees a flag updated via opaque, regular data fields written before the flag are guaranteed to be published under a release/acquire relationship.

If you do not yet need low-level non-blocking protocols, acquire/release or volatile is usually clearer and easier to verify.

### Acquire and release

One-time publication pattern, **writer**:

```java
payload = 42;           // Write regular data first.
READY.setRelease(this, 1); // Publish the flag.
```

**Reader**:

```java
while ((int) READY.getAcquire(this) == 0) {
    Thread.onSpinWait();
}
int local = payload; // Read data after observing the published flag.
```

These two snippets assume `payload`, `READY`, and the receiver are already declared; **they are not two standalone files**. When an acquire read observes the value published by the writer via release on the same signal variable, the release/acquire ordering allows safely reading the data written prior to publication under that protocol. See section 7 for a standalone example.

The `onSpinWait()` loop is only to illustrate the mechanism; production code usually prefers `CountDownLatch`, `BlockingQueue`, `Future`, or other waiting APIs when polling is unnecessary. Busy-waiting can waste CPU cycles and requires timeouts/cancellation if the work might never complete.

### Volatile access

`getVolatile`/`setVolatile` have semantics similar to accessing a `volatile` field. A volatile write happens-before a corresponding volatile read according to synchronization order rules, supporting cross-thread visibility and ordering.

**Common mistake:** two threads both execute `(int) VALUE.getVolatile(obj)` followed by `VALUE.setVolatile(obj, old + 1)`. Each individual get/set has volatile semantics, but **the pair of calls is not atomic**: both threads can read the same `old` and overwrite each other with the same result. To increment safely, use `getAndAdd` or a CAS loop.

## 4. Complete Java 17+ Example: Atomic Counter Using `getAndAdd`

Create `VarHandleCounter.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleCounter {
    private int count;

    private static final VarHandle COUNT;

    static {
        try {
            COUNT = MethodHandles.lookup()
                    .findVarHandle(VarHandleCounter.class, "count", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public void increment() {
        COUNT.getAndAdd(this, 1);
    }

    public int get() {
        return (int) COUNT.getVolatile(this);
    }

    public static void main(String[] args) throws InterruptedException {
        VarHandleCounter counter = new VarHandleCounter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counter.increment();
                }
            });
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Final count: " + counter.get());
    }
}
```

Compile and run:

```bash
javac VarHandleCounter.java
java VarHandleCounter
```

Output when the four workers finish normally:

```text
Final count: 4000
```

**Key takeaways:**

1. `COUNT` is a handle to the `int count` instance field of `VarHandleCounter`; every call must pass the receiver (`this`).
2. `getAndAdd(this, 1)` is **a single atomic read–modify–write operation**, unlike performing `getVolatile` followed by `setVolatile` in two steps.
3. `getVolatile(this)` reads the result with volatile semantics. `Thread.join()` also establishes a happens-before relationship from the worker's actions to the main thread after a successful join.
4. The scheduler may run the workers in any order, without losing increments; 4 × 1,000 = 4,000.

`VarHandle` is well-suited when you need fine-grained control over how a specific field is accessed. For a **simple counter**, `AtomicInteger` is usually shorter, easier to read, and leaves less room for misusing access modes. Use `VarHandle` when you genuinely need a memory layout or protocol that the standard atomic classes do not express cleanly.

## 5. Compare-and-Set: Check and Update in One Step

`compareAndSet(receiver, expected, newValue)` checks whether the variable currently equals `expected` and, if so, writes the new value **atomically**. The result is a `boolean`:

- `true`: the replacement succeeded.
- `false`: the current value did not match `expected` (or, for **weak** CAS variants, it may also experience a *spurious failure*).

For reference types, comparison in CAS primitives checks **reference identity** rather than calling the object's `equals()` method. For primitives, comparison follows the supported data type semantics.

### CAS loop to maintain a "non-negative quantity" invariant

Create `VarHandleInventory.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.atomic.AtomicInteger;

public class VarHandleInventory {
    private int remaining = 3;
    private static final VarHandle REMAINING;

    static {
        try {
            REMAINING = MethodHandles.lookup()
                    .findVarHandle(VarHandleInventory.class,
                                   "remaining", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public boolean reserveOne() {
        while (true) {
            int old = (int) REMAINING.getVolatile(this);
            if (old <= 0) {
                return false;
            }
            if (REMAINING.compareAndSet(this, old, old - 1)) {
                return true;
            }
            // Value changed: must re-read and try again.
        }
    }

    public int remaining() {
        return (int) REMAINING.getVolatile(this);
    }

    public static void main(String[] args) throws InterruptedException {
        VarHandleInventory inventory = new VarHandleInventory();
        AtomicInteger accepted = new AtomicInteger();
        Thread[] buyers = new Thread[10];

        for (int i = 0; i < buyers.length; i++) {
            buyers[i] = new Thread(() -> {
                if (inventory.reserveOne()) {
                    accepted.incrementAndGet();
                }
            });
            buyers[i].start();
        }

        for (Thread buyer : buyers) {
            buyer.join();
        }

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Remaining: " + inventory.remaining());
    }
}
```

Run:

```bash
javac VarHandleInventory.java
java VarHandleInventory
```

Output when all threads complete:

```text
Accepted: 3
Remaining: 0
```

Threads contend for the inventory, but only three transitions `3 → 2 → 1 → 0` can succeed. When CAS fails because another thread modified the value, the loop discards the stale snapshot. The `old > 0` check and the decrement are bound together by CAS at the **linearization point** of the successful update.

**Scope of atomicity:** a single CAS protects only `remaining`. If a sale operation must also append a record to a list, write to a file, or update external resources outside the JVM, CAS on one field **does not** turn the entire workflow into a transaction. Additional mechanisms must be chosen to protect related invariants.

## 6. `compareAndExchange`, Weak CAS, and Atomic Access Modes

### Differences between `compareAndSet` and `compareAndExchange`

- `compareAndSet(expected, update)` returns a `boolean` indicating success or failure.
- `compareAndExchange(expected, update)` returns **the actual value observed at the time of comparison** (*witness value*). If the witness equals `expected`, the write is performed; otherwise, the witness is the value that caused the operation to fail.
- Variants such as `compareAndExchangeAcquire` and `compareAndExchangeRelease` allow selecting weaker memory ordering on the corresponding sides of the operation; always read the exact API contract.
- `weakCompareAndSetPlain` and other weak variants can **fail spuriously** even when the current value matches `expected`. When using them in an algorithm, you typically need retries and must account for progress under contention.

Conceptual example with a `VarHandle` of value type `int` and a receiver coordinate:

```java
// Snippet: VALUE is a VarHandle for an int field of obj.
boolean swapped = VALUE.compareAndSet(obj, 5, 6);
int witness = (int) VALUE.compareAndExchange(obj, 6, 7);
```

This is a snippet, so `swapped`/`witness` cannot be predicted without knowing the actual state of `obj`. Never assume a "guaranteed" output for code with undetermined state.

### Atomic read–modify–write

Access modes such as `getAndSet`, `getAndAdd`, and `getAndBitwiseOr`/`And`/`Xor` (where supported by the type) read the old value and update the variable as **a single atomic operation**.

`getAndAdd` returns **the value before addition**, not the sum after addition. For example, if the current value is 10:

```java
// Snippet: VALUE is an int-typed VarHandle of obj.
int old = (int) VALUE.getAndAdd(obj, 5); // old = 10
// The stored value is 15.
```

To check whether a mode is supported for a specific handle:

```java
boolean allowed =
        VALUE.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD);
```

The snippets above omit the declarations of `obj` and `VALUE`; the array example in section 8 is a standalone runnable program.

**Choosing the right mode for the algorithm:** `getAndAdd` for counters; CAS loops for conditional updates; `getAndSet` for swapping a value; acquire/release modes when you can prove weaker ordering is sufficient. Picking a weaker mode "to run faster" without proving happens-before can introduce bugs that are very hard to reproduce.

## 7. Java 17+: Publication with `setRelease` and `getAcquire`

A common requirement: a producer prepares data and then publishes a readiness flag; a consumer reads the data **only after observing the flag**. You do not need to lock the entire object if this one-time publication protocol is designed correctly.

Create `VarHandlePublication.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandlePublication {
    private int payload;
    private int ready;

    private static final VarHandle READY;

    static {
        try {
            READY = MethodHandles.lookup()
                    .findVarHandle(VarHandlePublication.class,
                                   "ready", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        VarHandlePublication signal = new VarHandlePublication();

        Thread producer = new Thread(() -> {
            signal.payload = 42;
            READY.setRelease(signal, 1);
        });

        Thread consumer = new Thread(() -> {
            while ((int) READY.getAcquire(signal) == 0) {
                Thread.onSpinWait();
            }
            System.out.println("Received: " + signal.payload);
        });

        consumer.start();
        producer.start();
        producer.join();
        consumer.join();
    }
}
```

Run:

```bash
javac VarHandlePublication.java
java VarHandlePublication
```

When both threads finish normally, output:

```text
Received: 42
```

**Memory-ordering analysis:**

1. The producer writes the plain field `payload = 42` **before** publishing the flag with `setRelease(signal, 1)`.
2. The consumer loops on `getAcquire(signal)` until it sees `1`. The acquire read observing the flag published by the release write establishes the necessary ordering so that the subsequent read of `payload` observes the published data.
3. `payload` itself does not need to be declared `volatile` in this **single-writer, publish-once, no-further-writes-to-payload** protocol.
4. `Thread.onSpinWait()` only hints to the JVM/CPU about a busy-spin; it **does not replace** acquire/release or create any signaling guarantees.
5. To avoid an infinite loop if the producer fails to publish due to an error, production code must have cancellation, timeouts, or use an appropriate blocking primitive.

**Limitation:** if the producer continuously mutates `payload` while the consumer is reading, or if multiple producers publish to a single flag, the protocol above **is not sufficient on its own** to provide a multi-version snapshot. In that case, you need versioning, a queue, immutable snapshots, or appropriate locking.

## 8. Java 17+: VarHandle for Array Elements

A handle for `int[]` elements requires **two coordinates**: the array and the index. No separate wrapper class field is needed. Create `VarHandleArray.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleArray {
    private static final VarHandle ELEMENT =
            MethodHandles.arrayElementVarHandle(int[].class);

    public static void main(String[] args) {
        int[] values = {10, 20};

        int old = (int) ELEMENT.getAndAdd(values, 1, 5);
        boolean replaced = ELEMENT.compareAndSet(values, 0, 10, 15);

        System.out.println("Old second: " + old);
        System.out.println("New second: "
                + (int) ELEMENT.getVolatile(values, 1));
        System.out.println("First replaced: " + replaced);
        System.out.println("New first: "
                + (int) ELEMENT.getVolatile(values, 0));
    }
}
```

Run:

```bash
javac VarHandleArray.java
java VarHandleArray
```

Output:

```text
Old second: 20
New second: 25
First replaced: true
New first: 15
```

In this example, `getAndAdd(values, 1, 5)` **atomically** adds `5` to the element at index `1` and returns the old value `20`. `compareAndSet(values, 0, 10, 15)` succeeds because the value at index `0` is `10`. An atomic operation on `values[0]` **does not** create a transaction across the entire array; if you need to update multiple elements as a consistent snapshot, you must add an appropriate protocol.

An array `VarHandle` is a good choice when you need atomic access to individual slots of a primitive or reference array. Do not infer from this that `ArrayList` or other complex mutable data structures are safe for concurrent manipulation.

## 9. Relationship to the JMM: Visibility, Atomicity, and Ordering

You must distinguish three independent questions:

1. **Visibility:** can the reading thread observe the data published by the writer?
2. **Ordering:** are dependent operations ordered properly relative to each other according to the synchronization protocol?
3. **Atomicity:** does the check-and-update occur as a single uninterruptible step on that location?

For example:

- `VALUE.getVolatile(obj)` satisfies a volatile read, but reading and then calling `setVolatile` in a subsequent step is **not** an atomic read–modify–write.
- `VALUE.getAndAdd(obj, 1)` is an atomic addition on one location, but it does not protect an invariant involving another field.
- `setRelease(flag, 1)` and `getAcquire(flag)` are suitable for publishing data written **before** the signal to a reader that reads the data only **after** observing the signal; they do not guarantee that subsequent writes by the writer will form a consistent snapshot.
- `getOpaque`/`setOpaque` are weaker in ordering than acquire/release, so they cannot substitute for a dependent-data publication protocol.
- Plain `get`/`set` on the same mutable field from different threads without proper synchronization can create a data race.

### Does VarHandle make a regular field permanently volatile?

**No.** A `VarHandle` allows invoking **different modes** on the same location. The strength of a mode is a property of each individual call. If one code path uses `setRelease` while another path uses plain `get` when reading published data, you cannot claim safety merely because "the field is accessed via VarHandle."

The design must specify **matching mode pairs** across all access paths, along with invariants and synchronization relationships. A single accessor using the wrong mode can break the entire reasoning.

### Fences

`VarHandle` also provides static methods such as `fullFence()`, `acquireFence()`, `releaseFence()`, `loadLoadFence()`, and `storeStoreFence()` to express certain memory-ordering constraints independently of a specific variable access. These are low-level tools for specialized concurrent algorithms.

**Do not** use a stray fence as a magic fix for a data race or a check-then-act bug. You must have a complete reader/writer interaction protocol, prove its validity under the JMM, and place the fences accurately. Unless you have a very specific reason, using acquire/release/volatile access modes or higher-level concurrency APIs is much easier to verify.

## 10. Types, Signatures, and Errors When Calling VarHandle

Methods like `get`, `set`, and `compareAndSet` are **signature-polymorphic**. The compiler and JVM check parameter/coordinate types and return types according to the access mode. Therefore:

- Instance field handles require a properly typed receiver and arguments matching `varType()`.
- Static field handles do **not** take a receiver.
- Array handles require **array** and **index** coordinates before the new value or expected/new values.
- Read results typically require an explicit cast, e.g. `int n = (int) HANDLE.getVolatile(obj)`.
- Do not omit the `(int)` cast in `(int) HANDLE.getVolatile(...)` in expressions where Java type inference might otherwise mislead or fail.
- Calling with incompatible types or signatures can cause method-type errors such as `WrongMethodTypeException`; a receiver of the wrong type can cause corresponding runtime errors.
- A mode unsupported by the variable type or handle can throw `UnsupportedOperationException`.
- When accessing fields with restricted permissions, handle creation can fail with `IllegalAccessException`; you cannot bypass this by switching access modes.

### Checking capabilities before selecting a mode

```java
// Snippet: handle is validly created elsewhere.
boolean atomicAddSupported =
        handle.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD);
Class<?> valueType = handle.varType();
```

This snippet is not a standalone program. Capability checking is especially useful when writing generic utilities that accept handles of various types. For the `int` demos above, `GET_AND_ADD` is supported.

**Design note:** `VarHandle` does not automatically compose arbitrary operations into higher-level primitives. If a mode is not supported, do not emulate it with `get` followed by `set` when the algorithm requires atomicity.

## 11. Comparing VarHandle with `AtomicInteger`, `AtomicReference`, and Locks

| Mechanism | When it fits | Limitations / reasoning cost |
| --- | --- | --- |
| `AtomicInteger`/`AtomicLong` | Counters, single primitive state with CAS and atomic updates | Creates a wrapper object with an API tied to a specific atomic variable |
| `AtomicReference` | Replacing a reference (often pointing to an immutable snapshot) via CAS | Atomic only for the **reference**, does not automatically make the referenced object immutable |
| `AtomicIntegerFieldUpdater` | Atomic access to a field within the updater's constraints | Type/field restrictions and its own access rules |
| **`VarHandle`** | Need specific access modes for instance/static/array slots, building concurrent primitives, or controlling memory semantics | Low-level API; you must design matching mode pairs, casts, and protocols yourself |
| `synchronized`/`ReentrantLock` | Need critical sections or invariants spanning multiple fields | Lock contention and deadlock risk, but often simpler than complex CAS logic |
| Immutable snapshot via `volatile`/atomic reference | Many read-only readers, writer replaces the full snapshot | Writer may need to allocate new snapshots; readers must not mutate snapshot contents |

**`VarHandle` is not mandatory for faster code.** If `AtomicInteger.incrementAndGet()` expresses the business logic cleanly, it is usually the clearer choice. `VarHandle` shines when implementing data-structure libraries, non-blocking algorithms, atomic arrays, or cases requiring coordinated ordering modes. Always benchmark realistic workloads before drawing performance conclusions.

## 12. Common Concurrency Pitfalls

1. **"VarHandle = volatile on every access."** False: plain, opaque, acquire/release, and volatile have distinct semantics.
2. **"`getVolatile` followed by `setVolatile` is a CAS."** False: they remain two separate operations; another thread can interleave between them.
3. **"`getAndAdd` returns the new value."** False: it returns the value **before** the update.
4. **"`compareAndSet` can be replaced by separate get/set calls."** False: split check-then-act is not atomic.
5. **"A `false` return from weak CAS means the value definitely did not match."** False: weak CAS can fail spuriously.
6. **"`setOpaque`/`getOpaque` publish all previously written fields."** False: their ordering is weaker than the release/acquire protocol required for dependent data.
7. **"The writer uses `setRelease`, so a plain `get` on the reader is enough."** You cannot rely on a safe publication protocol without matching acquire semantics on the reader.
8. **"CAS on one field protects an entire multi-field object."** False: cross-field invariants require other mechanisms or encapsulating state into a single atomic reference.
9. **"A handle to a private field bypasses the Java module system."** False: handle creation checks access permissions.
10. **"Every mode is valid for every type."** False: check `isAccessModeSupported` when writing generic utilities.
11. **"Using `VarHandle` is always faster than `synchronized`."** False: performance depends on contention, read/write ratios, CPU/JVM, retry overhead, and cache effects.
12. **"One passing test run means the memory ordering is correct."** False: JMM bugs may only surface under a different schedule, JVM, or hardware architecture.

## 13. Checklist for Applying VarHandle in Production Code

1. **Choose the variable:** instance field, static field, or array element? What is its value type? What are the coordinates identifying the location?
2. **Verify access rights:** is the handle created with a valid `Lookup` without violating module encapsulation?
3. **State the invariant:** is atomicity needed for a single field, or must multiple fields be protected together?
4. **Select the weakest provably correct access mode:** plain/opaque only when another mechanism guarantees safety, acquire/release for publication protocols, volatile when stronger semantics are required, and CAS/`getAndAdd` for atomic RMW.
5. **Prove reader/writer cooperation:** is the reader's mode compatible with the writer's mode? Is dependent data written before publication and read only after acquire?
6. **Handle CAS failure:** if using a loop, re-read state; define a progress policy and retry/timeout limits if required by the business logic.
7. **Avoid unintended repeated side effects:** a CAS loop can execute multiple times; never send emails or write files inside a retry body without idempotency.
8. **Verify types and mode support:** are receiver, array index, return cast, and `AccessMode` all valid?
9. **Test concurrency thoroughly:** assert invariants, test controlled interleavings, run stress tests, and use `jcstress` for specialized JMM litmus tests when appropriate.
10. **Consider higher-level APIs:** an `AtomicInteger`, lock, queue, or immutable snapshot may be more readable, easier to review, and safer.
11. **Measure instead of guessing:** benchmark with JVM warm-up and a representative workload; separate performance from correctness.
12. **Document the policy:** every access to the same state should adhere to the chosen access mode and memory-ordering rules.

**Conclusion:** `VarHandle` is a JDK tool for accessing a variable with **explicitly chosen access modes**, including plain, opaque, acquire/release, volatile, and various atomic operations. Its power lies in expressing the exact memory semantics a concurrent algorithm needs; the author's responsibility is to prove the cross-thread protocol, protect invariants, and never confuse multiple separate accesses with a single atomic operation.