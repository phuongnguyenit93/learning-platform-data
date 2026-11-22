# 9.5. Plain, opaque, acquire, release, and volatile reads and writes with `VarHandle`

Java allows multiple threads to read and write the same variable, but **reading the right value in one thread** does not prove that another thread will observe the right data or the right order of operations. With `java.lang.invoke.VarHandle` (Java 9+), developers can choose **per-access memory semantics**: `plain`, `opaque`, `acquire`, `release`, and `volatile`.

These modes determine the level of guarantees regarding **atomicity**, **coherence**, and **memory access ordering between threads**. They are not five data types, nor are they value-transformation operations. This lesson focuses on Java 17+, explaining what is permitted to be read/written, the publish/consume mechanism, runnable examples, and common mistakes.

## 1. What is `VarHandle`?

A `VarHandle` is a **typed** reference to a variable or a family of variables: an instance field, a static field, an array element, or certain other kinds of memory provided by APIs. The `VarHandle` object itself is immutable; the contents of the variable it points to can still be mutable if the API and declaration allow it.

Each handle has:

- **Variable type** (`varType()`): the type of value being read/written, for example `int.class` or `String.class`.
- **Coordinate types** (`coordinateTypes()`): the types of coordinates needed to locate the variable. An instance field requires a receiver; a static field does not require a receiver; an array element requires an array reference and an index.
- **Access mode type** (`accessModeType(mode)`): the signature required for a specific mode, such as `(Cell)int` when reading an instance `int`, or `(Cell,int)void` when writing.
- **Supported modes** (`isAccessModeSupported(...)`): not every mode applies to every handle; in particular, a `final` field can be read but cannot be written via `VarHandle`.

To obtain a handle for an instance field:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Counter {
    int value;
}

// Illustrative snippet placed where there is permission to lookup field Counter.value.
VarHandle VALUE = MethodHandles.lookup()
        .findVarHandle(Counter.class, "value", int.class);

Counter c = new Counter();
VALUE.set(c, 10);               // plain write
int x = (int) VALUE.get(c);      // plain read
```

For the `int` field `Counter.value`, read modes have the logical signature `(Counter)int`, and write modes have the logical signature `(Counter,int)void`. At the `get` call, the direct `(int)` cast is necessary to describe the exact result type of a *signature-polymorphic call*. These mode methods have an apparent declaration of `Object...`, but the compiler/JVM uses a special signature; **do not** pass an `Object[]` in place of the coordinates and value out of reflection habit.

The modes here **control a single access**. For example, `VALUE.getVolatile(c)` carries volatile semantics even if the `value` field is not declared `volatile`; conversely, `VALUE.get(c)` is a plain read even if the original field declaration has `volatile`. Mixing accesses with inconsistent modes easily breaks reasoning about visibility.

## 2. Comparison table of read/write modes

| Mode | Read method | Write method | Notable guarantees | Common use |
| --- | --- | --- | --- | --- |
| **Plain** | `get` | `set` | Equivalent to normal field access, adds no inter-thread observation ordering guarantees | Internal data with other synchronization or used within a single thread |
| **Opaque** | `getOpaque` | `setOpaque` | Atomic for the value, has **coherence/ordering on the same variable**; does not publish the order of accesses to other variables | Tracking simple state that needs stronger guarantees than plain without publishing a payload |
| **Acquire** | `getAcquire` | *No `setAcquire`* | After an acquire read, subsequent loads/stores are not reordered before it; pairs with a matching release write | Consumer receives a published flag, then reads the payload |
| **Release** | *No `getRelease`* | `setRelease` | Prior loads/stores are not reordered after this write; pairs with a matching acquire read | Producer writes the payload first, publishes the flag afterward |
| **Volatile** | `getVolatile` | `setVolatile` | Semantics like a `volatile` field, with a total order across volatile accesses | Shared flags, state requiring stronger ordering/visibility |

The **strength ordering of guarantees** commonly used as a mnemonic is **plain → opaque → acquire/release → volatile**, but `acquire` is on the **read** side while `release` is on the **write** side: they are not symmetric alternatives in both directions. This is a general ordering of memory ordering constraints, **not** a conclusion about the speed of any specific CPU/JVM.

According to the Java 17 `VarHandle` Javadoc:

- Plain `get/set` is only guaranteed to be **bitwise atomic** for references and primitives no larger than 32 bits; `long`/`double` may lack guarantees against value tearing (*tearing*) on 32-bit platforms.
- Opaque read/write is bitwise atomic even for `long`/`double` and is *coherently ordered* for accesses to the **same variable**.
- Acquire and release inherit opaque guarantees and add constraints in **one direction**.
- Volatile inherits acquire/release guarantees, and volatile accesses are arranged in a **consistent total order**.

Do not infer that a volatile operation will always "run fastest/slowest" in a fixed way; the cost depends on the CPU, JIT, contention, and architecture.

## 3. Plain: `get` / `set`

`get` reads and `set` writes with semantics identical to a **non-`volatile` and non-`final`** variable. For a mutable field used within the same thread:

```java
VALUE.set(c, 1);
int n = (int) VALUE.get(c); // 1 in this thread
```

This is the natural choice when data is **thread-confined**, immutable after safe publication, or synchronized by a lock/another mechanism. If threads access it concurrently without a proper ordering relationship, **do not treat a plain read as a reliable way to observe the latest write**.

An incorrect example of thread communication:

```java
// Producer:
payload = 42;
READY.set(box, 1);           // plain write

// Consumer:
while ((int) READY.get(box) == 0) {
    // No proper visibility protocol.
}
use(payload);
```

This is **illustrative pseudocode**, not a complete program: the variables `READY`, `box`, `payload`, and `use` are assumed to exist. There is no guarantee that the consumer will exit the loop under this race condition; moreover, even if `ready == 1` is seen, seeing the correct `payload` is not established either. Using `Thread.sleep`, increasing wait times, or adding `println` **does not fix the memory contract**.

### 3.1. Atomicity of a single access differs from atomicity of a whole update

Even when each `int` read/write is atomic, this snippet is **not** an atomic increment:

```java
int old = (int) VALUE.getVolatile(c);
VALUE.setVolatile(c, old + 1); // two operations, another thread can interleave
```

Use `getAndAdd`, `compareAndSet`, or a locking mechanism if an atomic read-modify-write is needed. `volatile` improves ordering/visibility, but **does not turn two separate calls into a single transaction**.

## 4. Opaque: `getOpaque` / `setOpaque`

Opaque is stronger than plain in atomicity and **coherence of the same variable**: opaque accesses to the same location are observed in a consistent order according to the API rules. It does not establish ordering constraints with accesses to other variables like a release/acquire pair.

```java
VALUE.setOpaque(c, 2);
int n = (int) VALUE.getOpaque(c); // 2 in this thread
```

Opaque can be suitable for certain low-level algorithms that only require tracking/communicating **the value of a single variable itself**, carefully designed and proven correct. For example, a simple statistics state where observation latency and coordination with other fields do not matter, though choosing opaque still requires reviewing the entire access protocol.

**Do not use opaque as a signal to publish other data without proper synchronization.** For example:

```java
// Producer:
box.payload = 42;
READY.setOpaque(box, 1);

// Consumer:
if ((int) READY.getOpaque(box) == 1) {
    int value = box.payload; // Not guaranteed to see 42 from the opaque pair alone.
}
```

This is also **pseudocode**; opaque operations on `ready` do not guarantee that normal accesses on `payload` are ordered for observation as intended. Instead of guessing based on how many times a test passes, determine whether a valid ordering relationship exists.

Opaque **does not** mean every thread sees the value immediately or that all variables are ordered in a global order. Opaque provides coherence for the variable being accessed, which differs from ordered publish/consume semantics for *dependent data*.

## 5. Acquire and release: publishing data in pairs

This is a common pair when a producer wants to **prepare data first**, then **publish a flag**; the consumer **sees the published flag**, and only then **reads the data**.

- `setRelease`: loads/stores performed **before** the release write are not moved after it.
- `getAcquire`: loads/stores performed **after** the acquire read are not moved before it.
- When an acquire read actually observes the value published by a release write **on the corresponding synchronization variable**, the producer's prior accesses and the consumer's subsequent accesses are ordered with the necessary relationship.

Minimal pattern:

```java
// Both threads share box/READY.
// Producer:
box.payload = 42;              // write data first
READY.setRelease(box, 1);       // publish flag afterward

// Consumer:
while ((int) READY.getAcquire(box) == 0) {
    Thread.onSpinWait();
}
int result = box.payload;        // read after observing flag 1
```

This shows **two threads in a one-shot publication protocol**, not a standalone program; the complete example section below creates real threads and handles. After the consumer sees flag `1` via `getAcquire`, it can read the `payload` `42` that was written by the producer before `setRelease` in this case.

**Essential conditions of the pattern:**

1. The producer must write `payload` **before** calling `setRelease`.
2. The consumer only reads `payload` **after** `getAcquire` sees the published flag value.
3. Both must use the same synchronization location `ready`, not completely different variables.
4. After publication, the producer is not free to overwrite `payload` while the consumer is reading it; for continuous updates, an ownership/versioning protocol or additional synchronization is required.
5. In programs with contention or complex publish/reuse cycles, one must consider which flag writes are read, data lifetimes, and interactions with other access modes.

**What to avoid:** Using `setRelease` on the producer while the consumer reads the flag with plain `get`, or the producer using plain `set` while the consumer reads with `getAcquire`, is not the publication pair presented here. There are also no `setAcquire` or `getRelease` APIs to use with reversed roles.

### 5.1. Why are acquire/release one-way constraints?

You can visualize it (this is a conceptual diagram only, not exact CPU barriers):

```text
Producer                             Consumer
---------                            ---------
write payload = 42                   acquire-read ready == 1
write other prepared state           read payload
release-write ready = 1              read other prepared state

prior reads/writes do not move       subsequent reads/writes do not move
past after release                   before acquire
```

Acquire **does not** guarantee that all operations before it must complete in the same way as volatile; release **does not** guarantee that all operations after it are held back. They restrict the reordering directions needed for publish/consume, which can allow the compiler/hardware more optimization than volatile in some cases.

`Thread.onSpinWait()` is only a hint to the runtime when spinning, **not** a memory fence or a visibility solution. An unbounded spin loop can consume CPU and is not a proper timeout/cancellation design in real applications.

## 6. Volatile: `getVolatile` / `setVolatile`

`getVolatile` and `setVolatile` access a location with semantics equivalent to **reading/writing a field declared `volatile`**, regardless of the original field declaration. In addition to acquire/release guarantees, volatile accesses are placed in a total order consistent with the Java Memory Model.

```java
VALUE.setVolatile(c, 4);
int n = (int) VALUE.getVolatile(c); // 4 in the current thread
```

Typical applications:

- A stop flag `stopRequested` updated by a producer and read by a worker between loop iterations.
- State observed by multiple threads that needs `volatile` field semantics.
- One-way signaling accompanied by previously prepared data, when application rules require stronger consistency than simple acquire/release.
- Lock-free algorithms with a well-defined memory ordering contract.

In ordinary Java, when you only need a simple `volatile` field, you can write it directly:

```java
class WorkerState {
    volatile boolean stopRequested;
}
```

You do not need a VarHandle just to read/write this field; VarHandle is useful when you want to choose the **access mode at each call site**, or build concurrency/generic runtime libraries.

**Do not confuse volatile with:**

- **Atomic increment:** `getVolatile` followed by `setVolatile` still does not create an atomic `++` operation.
- **Mutual exclusion:** it does not prevent two threads from executing a critical section at the same time.
- **Multi-field snapshot:** two separate volatile reads do not automatically turn the entire object into a transactional snapshot.
- **Specific timing guarantees:** volatile does not guarantee that a worker will be scheduled immediately, or within a millisecond bound to read the new state.
- **Safety when mixing modes:** if the producer uses volatile on the flag but the consumer uses plain, you cannot infer from volatile on one side that the entire protocol is fully synchronized.

**Relationship with fields declared `volatile`:** The `VarHandle` Javadoc states that the call's access mode **overrides the memory ordering of the declaration site**. This means `handle.get(s)` is a plain access even if the field is `volatile`, and `handle.getVolatile(s)` is a volatile access even if the field is not declared `volatile`. Mixing access styles with ordinary code requires special care; use a consistent policy throughout the algorithm.

## 7. Complete, runnable Java 17+ example

This example creates `VarHandle`s for instance fields, a handle for array elements, demonstrates **all five mode groups** with easily verifiable results, confirms that write modes are unsupported for `final` fields, and simulates publishing a payload using a release/acquire pair.

Save the entire program as **`VarHandleModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleModesDemo {
    static final class Cell {
        int value;
        int payload;
        int ready;
        final int fixed = 9;
    }

    private static final VarHandle VALUE;
    private static final VarHandle READY;
    private static final VarHandle FIXED;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            VALUE = lookup.findVarHandle(Cell.class, "value", int.class);
            READY = lookup.findVarHandle(Cell.class, "ready", int.class);
            FIXED = lookup.findVarHandle(Cell.class, "fixed", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Cell cell = new Cell();
        System.out.println("variable=" + VALUE.varType().getSimpleName());
        System.out.println("coordinates=" + VALUE.coordinateTypes().size());

        VALUE.set(cell, 1);
        System.out.println("plain=" + (int) VALUE.get(cell));

        VALUE.setOpaque(cell, 2);
        System.out.println("opaque=" + (int) VALUE.getOpaque(cell));

        VALUE.setRelease(cell, 3);
        System.out.println("acquire=" + (int) VALUE.getAcquire(cell));

        VALUE.setVolatile(cell, 4);
        System.out.println("volatile=" + (int) VALUE.getVolatile(cell));

        VarHandle elements = MethodHandles.arrayElementVarHandle(int[].class);
        int[] data = {5, 6};
        elements.setVolatile(data, 1, 8);
        System.out.println("array=" + (int) elements.getVolatile(data, 1));

        System.out.println("final.get="
                + FIXED.isAccessModeSupported(VarHandle.AccessMode.GET));
        System.out.println("final.set="
                + FIXED.isAccessModeSupported(VarHandle.AccessMode.SET));

        try {
            FIXED.set(cell, 10);
        } catch (UnsupportedOperationException e) {
            System.out.println("final.write=" + e.getClass().getSimpleName());
        }

        Cell shared = new Cell();
        Thread consumer = new Thread(() -> {
            while ((int) READY.getAcquire(shared) == 0) {
                Thread.onSpinWait();
            }
            System.out.println("published=" + shared.payload);
        });

        consumer.start();
        shared.payload = 42;
        READY.setRelease(shared, 1);
        consumer.join();
        System.out.println("done");
    }
}
```

Run from the directory containing the file:

```bash
javac --release 17 VarHandleModesDemo.java
java VarHandleModesDemo
```

Program `stdout`:

```text
variable=int
coordinates=1
plain=1
opaque=2
acquire=3
volatile=4
array=8
final.get=true
final.set=false
final.write=UnsupportedOperationException
published=42
done
```

**Step-by-step explanation:**

1. `VALUE.varType()` is `int`; `VALUE.coordinateTypes()` has one coordinate, the `Cell` instance. This is an instance field, not a static field.
2. `plain=1`, `opaque=2`, `acquire=3`, `volatile=4` verify that the same variable can be accessed through different modes. These sequential lines **do not measure** and **do not prove** ordering differences across multiple threads; ordering is a property of the contract and protocol, not a difference in the printed numbers.
3. `array=8` shows that an array VarHandle has coordinates **array + index**; volatile access can be used on an array element according to the `int` element type.
4. `FIXED` points to `final int fixed`: read mode is supported, write mode `SET` is not. Calling `FIXED.set(...)` throws `UnsupportedOperationException`; `VarHandle` is not a backdoor to mutate final fields.
5. The consumer waits on the `ready` flag using `getAcquire`; the producer writes `payload` then `setRelease`. When the consumer reads the published flag value, it prints `published=42`. `join()` makes main wait for the consumer to finish printing before `done`; `join` **is not used to establish visibility of `payload` before the consumer reads it** — that role belongs to the release/acquire pair.

On real machines, the spin loop can wait depending on scheduling, so do not turn this example into a deadline or latency guarantee. Production systems should consider stopping conditions, backoff, `LockSupport`, blocking queues, or higher-level synchronization primitives suited to the use case. The example focuses on memory ordering semantics rather than optimal waiting utilities.

## 8. Instance fields, static fields, and array elements use different coordinates

Mode signatures depend on **the handle's coordinates**, not just whether the variable has type `int` or `String`.

| Variable kind | Handle creation | Read coordinates | Write coordinates |
| --- | --- | --- | --- |
| Instance field `int value` of `Cell` | `lookup.findVarHandle(Cell.class, "value", int.class)` | `(cell)` | `(cell, newValue)` |
| Static field `static int total` of `Totals` | `lookup.findStaticVarHandle(Totals.class, "total", int.class)` | *No receiver* | `(newValue)` |
| Array element `int[] arr` | `MethodHandles.arrayElementVarHandle(int[].class)` | `(arr, index)` | `(arr, index, newValue)` |

Syntactic standalone snippet (assuming classes/variables are already declared in the project):

```java
VarHandle FIELD = MethodHandles.lookup()
        .findVarHandle(Cell.class, "value", int.class);
int instanceValue = (int) FIELD.getVolatile(cell);
FIELD.setRelease(cell, 10);

VarHandle STATIC = MethodHandles.lookup()
        .findStaticVarHandle(Totals.class, "total", int.class);
int total = (int) STATIC.getVolatile();
STATIC.setVolatile(11);

VarHandle ARRAY = MethodHandles.arrayElementVarHandle(int[].class);
int element = (int) ARRAY.getOpaque(arr, 0);
ARRAY.setOpaque(arr, 0, 12);
```

`FIELD`, `STATIC`, and `ARRAY` are illustrative variables; the snippet above is **not** a runnable program because `Cell`, `Totals`, `cell`, and `arr` are not provided here. The complete program in Section 7 demonstrates imports, handle initialization, and using a real array.

If you pass a receiver of the wrong type, omit coordinates, use an out-of-bounds array index, or use a return type incompatible with the access mode, the call can cause errors such as `WrongMethodTypeException`, `ClassCastException`, `NullPointerException`, or `ArrayIndexOutOfBoundsException` depending on the case. These are **type/coordinate/data** errors, not automatically memory ordering issues.

## 9. `isAccessModeSupported` and the difference from atomic updates

`VarHandle` supports many operations beyond reads/writes, such as `compareAndSet`, `getAndSet`, `getAndAdd`, and acquire/release variants. However, **you cannot assume** a handle supports every mode, and you cannot treat `getVolatile` + `setVolatile` as a unified atomic operation.

Check before using:

```java
boolean writable = VALUE.isAccessModeSupported(
        VarHandle.AccessMode.SET_VOLATILE);
boolean canAdd = VALUE.isAccessModeSupported(
        VarHandle.AccessMode.GET_AND_ADD);
```

Here `VALUE` is a mutable `int` handle. For a `final` field, write and update modes are not supported; the API throws `UnsupportedOperationException` when an unsupported mode is called. Some numeric/bitwise update modes also depend on the variable type; for example, `getAndAdd` does not meaningfully apply to every reference type.

When you want `count++` to be linearizable across multiple threads, you can use:

```java
VALUE.getAndAdd(cell, 1); // atomic update for int if the mode is supported
```

If you want to know the value before incrementing:

```java
int oldValue = (int) VALUE.getAndAdd(cell, 1);
```

This is an **atomic read-modify-write** API; unlike `VALUE.setVolatile(cell, (int) VALUE.getVolatile(cell) + 1)`, where two threads can still read the same old value and lose an increment.

## 10. Common mistakes when choosing a mode

| Symptom or misconception | Cause | Fix |
| --- | --- | --- |
| "Plain read always sees the latest write after a few loop iterations" | No synchronization protocol between threads | Use a lock/volatile/release-acquire pair or an appropriate synchronization primitive |
| "An opaque flag is enough to publish data in other fields" | Opaque only guarantees coherence for **the same variable**; it does not create cross-variable ordering like publication | Use `setRelease` on the flag and `getAcquire` on the consumer, with the right payload order |
| "Using `setRelease` is enough, the consumer can just do a plain read" | No matching acquire to observe the publication | Consumer uses `getAcquire` on the same flag |
| "Using `getAcquire` and writing payload after `setRelease` is fine" | One-way ordering; publishing before the data is a protocol bug | Producer writes payload **before** the release write |
| "`volatile` makes every `++` atomic" | Read then write are two operations | Use `getAndAdd`, CAS, or a lock |
| "Using `get` on a field declared volatile is still volatile" | The VarHandle access mode determines the semantics of **that access** | Use `getVolatile`/`setVolatile` consistently per the protocol |
| "`setOpaque` can modify a final field" | Final fields are read-only via VarHandle | Check `isAccessModeSupported`, redesign the state |
| "`setRelease` can be paired with `getRelease`" | `getRelease` does not exist | Pair `setRelease` with `getAcquire` |
| "`getAcquire`/`setRelease` is always faster than volatile" | Performance depends on JIT, architecture, and contention | Benchmark the whole protocol; prioritize correctness |
| "Ran many times without seeing a bug, so plain/opaque is safe" | Concurrency bugs do not have to reproduce every run | Reason from the memory model; stress tests are supplementary |
| "VarHandle is a method taking `Object...`, so just skip the int cast" | Mode methods are signature-polymorphic | Use the exact type/cast and coordinates matching the handle type |

**Beware of mixed modes:** Using plain reads mixed with opaque/volatile writes on the same variable does not automatically inherit the strongest properties of the other calls. When reviewing concurrency logic, inspect **all** read and write paths to that shared location, including both ordinary field accesses and accesses via VarHandle.

## 11. Choosing a mode by need

Start from the **invariant that must be guaranteed**, and only then choose the mode:

1. **Used only in one thread or already protected by a lock:** plain `get/set` is usually sufficient. Do not add volatile unnecessarily if synchronization is already clear, but also do not drop the lock just because plain reads appear to work.
2. **Need single-variable coherence without publishing other variables' state:** you can consider opaque, if the algorithm is proven correct and you understand the ordering limitations.
3. **Producer prepares data then notifies consumer:** typically use `setRelease` on the flag and `getAcquire` on the same flag; ensure the producer writes the payload before and the consumer reads the payload after seeing the flag.
4. **Need semantics equivalent to a volatile field:** use `getVolatile/setVolatile`, or declare `volatile` directly when per-call mode switching is not needed.
5. **Need to update a variable under contention via addition/CAS:** use `getAndAdd`, `compareAndSet`, `getAndSet`, locks, or higher-level concurrency primitives. Memory ordering and atomic updates are **two different requirements**.

Do not choose a mode solely by a "weaker is faster" chart: each choice must preserve the visibility/ordering contract, access permissions, atomicity, and liveness that the system requires.

## 12. Self-check exercises

**A.** Two threads share `ready` and `payload`. The producer writes `payload=7` then `readyHandle.setOpaque(state,1)`, and the consumer reads `getOpaque(state)==1` and accesses `payload`. Is seeing `7` guaranteed by the two opaque accesses?

**B.** Replace `setOpaque` with `setRelease` and `getOpaque` with `getAcquire` on **the same flag**, and the producer does not overwrite `payload` after publication. Why is this a proper publication pattern?

**C.** A `VarHandle` points to `final long id`. Can `getVolatile` read it if the lookup is valid? Is `setVolatile` supported?

**D.** `int x = (int) HANDLE.get(box);` where `HANDLE` points to an instance `int` field. Why must `box` be passed? If it were a static `int` field, how would the call need to change?

**E.** Two threads both want to increment `count`, each using `getVolatile` then `setVolatile`. Can an increment be lost? Which API is appropriate?

**F.** On a 32-bit JVM, does plain `get/set` of `long` guarantee absolute bitwise atomicity? Does opaque guarantee that?

**G.** A field is declared `volatile int flag`, but the code uses `handle.get(instance)` instead of `getVolatile`. Can you assume it is a volatile read?

**Answers:**

- **A:** No; opaque only provides coherence for the flag variable, not ordering guarantees to publish another payload.
- **B:** `setRelease` keeps preparation operations before publication, and `getAcquire` keeps payload reads after receiving publication; the matched access pair on the same flag establishes the ordering needed for the example.
- **C:** It can read if permissions are sufficient. `setVolatile` is an unsupported write mode on a final field; calling it throws `UnsupportedOperationException`.
- **D:** An instance VarHandle needs the `box` receiver to locate the field; a static VarHandle needs no receiver, using `(int) STATIC_HANDLE.get()`.
- **E:** Increments can be lost because read and write are separate. Use `getAndAdd`, CAS, or a lock.
- **F:** No; plain may lack bitwise atomicity guarantees for `long`/`double` on 32-bit. Opaque guarantees bitwise atomicity.
- **G:** No. The `get` access mode is plain according to VarHandle rules, even if the declaration has `volatile`.

## 13. References

- [Oracle Java SE 17 — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): describes `get/set`, `getOpaque/setOpaque`, `getAcquire/setRelease`, `getVolatile/setVolatile` modes, atomicity, coherence, and memory ordering.
- [JEP 193 — Variable Handles](https://openjdk.org/jeps/193): design motivation for VarHandle and access mode categories.
- [Java Language Specification SE 17 — `17.4 Memory Model](https://docs.oracle.com/en/java/javase/17/docs/specs/jls/se17/html/jls-17.html#jls-17.4): data races, ordering, and happens-before in Java.
- [Oracle Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle`, `findStaticVarHandle`, and lookup permissions.

**Key takeaway:** `plain` creates no cross-thread visibility; `opaque` adds atomicity/coherence of the variable itself; `release` writes a signal after prepared data, `acquire` reads the signal before using data; `volatile` has stronger ordering semantics and a total order across volatile accesses. These are **per-access modes**, not a substitute for designing a proper inter-thread synchronization protocol.
