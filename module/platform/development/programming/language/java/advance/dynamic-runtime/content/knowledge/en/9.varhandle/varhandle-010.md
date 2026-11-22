# 9.10 Relationship with the Java Memory Model, memory fences, and risks of mixing multiple access modes

`VarHandle` allows accessing a variable (instance field, static field, or array element) with **multiple memory consistency modes** right at each call site: `get`/`set` (plain), `getOpaque`/`setOpaque` (opaque), `getAcquire`/`setRelease` (acquire/release), `getVolatile`/`setVolatile` (volatile), along with atomic update operations such as `compareAndSet` and `getAndAdd`. The methods `VarHandle.fullFence()`, `acquireFence()`, `releaseFence()`, `loadLoadFence()`, and `storeStoreFence()` provide memory ordering constraints independent of a specific VarHandle.

This flexibility comes at a cost: **reading/writing the same address using different modes does not automatically produce the same guarantees**. A flag written with `setOpaque` and read with `getVolatile` cannot be treated as a `setRelease`–`getAcquire` pair to publish accompanying data. A call to `fullFence()` also **does not automatically turn** two plain variables into a safe communication protocol.

This article clarifies how the VarHandle API connects to the Java Memory Model (JMM), the meaning of fences, how to design publish/consume protocols, the risks of *mixed-mode access*, the differences between **atomicity**, **visibility**, **ordering**, and **progress**, as well as how to test. The examples compile with Java 17+.

## 1. Four questions that must be separated

When designing concurrent data access, do not ask broadly “is this statement thread-safe?”. Answer the following four questions:

1. **Atomicity**: can a read/write or read-modify-write operation be split/torn or interleaved by another thread mid-operation?
2. **Visibility**: what values can a thread see that were written by another thread? What enables writes to be published to readers?
3. **Ordering**: are other accesses allowed to appear as if reordered before/after this operation?
4. **Progress/liveness**: is a reader guaranteed to eventually see the new flag or exit the loop? This is a different question from memory ordering and also depends on scheduling, protocols, and other conditions.

For example, `counter++` consists of a read, an addition, and a write. Even if each read and write uses `volatile` mode, **the read–write pair** is not an atomic read-modify-write operation; two writers can read the same old value and overwrite each other's results. To increment a counter concurrently, use `getAndAdd` or an appropriate CAS loop.

Conversely, `getOpaque`/`setOpaque` guarantees bitwise-atomic access to a single variable according to the API documentation, but **has no ordering guarantee for other payload variables** like a release/acquire pair. One cannot infer “since it is atomic, it is safe to publish the entire object”.

### 1.1. The JMM allows compiler/CPU optimizations within defined limits

The Java Memory Model (JLS `17.4) defines observable behaviors between threads. **Program order** is the order of actions of each thread according to source semantics; **synchronization order** is the total order of synchronization actions; **synchronizes-with** and the transitive **happens-before** (HB) relation define inter-thread constraints.

Imagine two threads:

```java
// Thread A
payload = 42;
ready = true;

// Thread B
if (ready) {
    System.out.println(payload);
}
```

This is illustrative code only: if `ready` and `payload` are both accessed plain without other synchronization, one cannot deduce that whenever B sees `ready == true`, B must see `payload == 42`. Observed behaviors can differ from the order in which we read the source code, because the program has not established appropriate inter-thread constraints.

**Happens-before is not simply “source statement A appears before B”**. Order within a single thread creates an intra-thread HB edge; to bridge to another thread, an appropriate inter-thread mechanism is needed, such as matching `volatile` operations, monitor lock/unlock, thread start/join, or a memory access protocol with release/acquire effects as specified by the VarHandle documentation.

If the program already has another synchronization mechanism (for example, both threads execute inside the same monitor), plain access can be safe within the scope of that monitor. One should not conclude that all plain accesses are wrong; what is wrong is **using plain access without a sufficiently strong synchronization protocol**.

## 2. Map of VarHandle access modes by memory effect

A `VarHandle` is a typed reference to a variable. **The mode resides in the invoked method**, not fixed simply by how the VarHandle object was created.

| API pair/group | Key guarantees | When appropriate |
| --- | --- | --- |
| `get` / `set` | *Plain*: non-volatile access semantics; does not create volatile inter-thread ordering constraints | Data used by only one thread, or already protected by other synchronization |
| `getOpaque` / `setOpaque` | Bitwise-atomic and coherent access for **the same variable**, with program-order consistency for that variable itself; **does not** publish payload like release/acquire | Some independent state/flags that only need limited coherent visibility |
| `getAcquire` | Read with *acquire* effect: subsequent loads/stores are not observed as occurring before this read | Receiving publication from a matching release |
| `setRelease` | Write with *release* effect: preceding loads/stores are not observed as occurring after this write | Publishing previously prepared payload |
| `getVolatile` / `setVolatile` | Semantics like reading/writing a `volatile` field; volatile operations have a total order with each other, stronger than acquire/release | Flags or state needing an explicit volatile contract, coordinating multiple volatile operations |
| `compareAndSet`, `getAndSet`, `getAndAdd` | Atomic read-modify-write with memory effects like corresponding volatile accesses | CAS, atomic counters/state transitions |
| `...Acquire` / `...Release` variants of RMW | Atomic update remains atomic; read/write ordering effects can be **asymmetric** and weaker than default mode | Algorithms proven to only need the acquire or release side |
| `weakCompareAndSetPlain` | Weak atomic CAS that can fail spuriously even when the value matches; plain memory order effect | Algorithms with retry and self-managed ordering |

**Not every mode can be used on every variable.** For example, a `VarHandle` pointing to a `final` field does not support writes/atomic updates; calling an unsupported mode results in `UnsupportedOperationException`. You can query `isAccessModeSupported(VarHandle.AccessMode.…)` before use.

### 2.1. Plain has different atomicity limits than Opaque

As of JDK 17, plain `get`/`set` are guaranteed to be bitwise atomic for references and primitives up to 32 bits; for `long`/`double` on some 32-bit platforms, it may not be guaranteed as with stronger modes. Other read/write modes such as opaque, acquire/release, and volatile guarantee bitwise atomicity per the VarHandle documentation. This is **atomicity of a single variable access**, not meaning a read–modify–write combination is atomic.

The phrase “coherently ordered” for opaque only relates to **the same variable**. It does not allow inferring that all fields in an object are observed by a reader as a monolithic transaction.

### 2.2. Atomicity and ordering are two independent axes

Examples:

- `getAndAdd(counter, 1)` is an atomic RMW, avoiding lost updates on the counter and using the memory effect of the corresponding mode.
- `getVolatile(counter)` followed by `setVolatile(counter, old + 1)` are **two separate operations**. Strong volatile ordering does not turn this pair into an atomic increment.
- `setRelease(flag, true)` has the effect of publishing preceding writes when a consumer reads with a matching acquire, but does not prevent another writer from concurrently overwriting the same flag/payload; the ownership protocol must still be designed.
- `getOpaque(flag)` can read a coherent value of the flag, but is not sufficient to read a plain payload set by the writer before `setOpaque(flag, true)` as a published record.

## 3. Release → acquire: the correct publish/consume pattern

Suppose there is only **one writer**, publishing **once**, after which the payload is not modified. Writer thread:

```java
message.id = 17;
message.text = "confirmed";
PUBLISHED.setRelease(message, true);
```

Reader thread:

```java
while (!(boolean) PUBLISHED.getAcquire(message)) {
    Thread.onSpinWait();
}
int id = message.id;
String text = message.text;
```

These two snippets are illustrative, where `PUBLISHED` is a VarHandle to the `boolean published` field. Order:

```text
WRITER                          READER
message.id = 17
message.text = "confirmed"
PUBLISHED.setRelease(true)  ──>  PUBLISHED.getAcquire() == true
                                 read message.id
                                 read message.text

publish writes before release    consume after matching acquire
```

According to the VarHandle specification, **an acquire read paired with a corresponding release write** establishes ordering so that reader accesses *after acquire* do not observe the payload as if executed before writer writes *before release*. The condition that **the reader actually observes the matching publication** is central; not just any `getAcquire` immediately guarantees seeing a future write.

### 3.1. Conditions that must not be overlooked

- The writer finishes writing the payload **before** `setRelease`.
- The reader only reads the payload **after** `getAcquire` confirms the publication flag, not reading beforehand and hoping a fence fixes it.
- On the same flag, the parties use compatible mode pairs and the same ownership mechanism. If the writer keeps modifying the payload concurrently after publishing, the flag itself does not protect the new modifications.
- If there are multiple writers, readers, or multiple publish/reuse rounds, a state machine, sequence number, ownership, CAS, or appropriate lock is needed. A plain `ready` boolean is prone to ABA or reading data from another round.
- `Thread.onSpinWait()` is only an optimization hint for a spin loop; it is **not a fence**, does not create HB, and does not guarantee fairness/liveness. Infinite spinning also wastes CPU, so real programs should consider blocking, timeouts, or higher-level primitives.

### 3.2. Runnable Java 17+ program: two threads

Create the file **`VarHandlePublicationDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class VarHandlePublicationDemo {
    static final class Message {
        int id;
        String text;
        boolean published;
    }

    static final VarHandle PUBLISHED;
    static {
        try {
            PUBLISHED = MethodHandles.lookup()
                    .findVarHandle(Message.class, "published", boolean.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Message message = new Message();
        AtomicReference<String> observed = new AtomicReference<>();
        AtomicReference<Throwable> error = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
            while (!(boolean) PUBLISHED.getAcquire(message)) {
                if (System.nanoTime() >= deadline) {
                    error.set(new IllegalStateException("publication timed out"));
                    return;
                }
                Thread.onSpinWait();
            }
            observed.set(message.id + ":" + message.text);
        }, "reader");
        Thread writer = new Thread(() -> {
            message.id = 17;
            message.text = "confirmed";
            PUBLISHED.setRelease(message, true);
        }, "writer");

        reader.start();
        writer.start();
        writer.join();
        reader.join();
        if (error.get() != null) {
            throw new IllegalStateException("reader did not observe publication", error.get());
        }
        System.out.println("published=" + observed.get());
    }
}
```

Run commands:

```bash
javac --release 17 VarHandlePublicationDemo.java
java VarHandlePublicationDemo
```

In a successful run, `stdout` is:

```text
published=17:confirmed
```

**Clarification of synchronization types:** transferring the payload from writer to reader relies on `PUBLISHED.setRelease` / `PUBLISHED.getAcquire`. `Thread.join()` makes **main** wait for both threads to finish before printing the result; it is not a synchronization mechanism replacing the release/acquire pair between writer and reader. `AtomicReference` is used to pass the result and error from reader to main without introducing a new race on the result state.

The timeout in the example is a safeguard against abnormal errors/scheduling, **not** a progress guarantee from VarHandle: if a thread is not scheduled to run, it may fail with a timeout instead of producing the output line. A single passing test run does not prove all interleavings are safe; sound conclusions rely on the memory model contract.

## 4. Volatile: where is it stronger than acquire/release?

`getVolatile` and `setVolatile` carry the semantics of a Java field declared `volatile`. Volatile operations belong to a total **synchronization order** and are consistent with program order; volatile operations on a variable also have read/write relationships under the JMM. The JDK VarHandle documentation states that volatile mode adds total ordering guarantees among volatile operations, in addition to the effects of acquire/release.

For a simple data publication flag, both of these pairs can usually express an appropriate protocol:

```java
// Option A: release/acquire
READY.setRelease(box, true);
boolean ready = (boolean) READY.getAcquire(box);

// Option B: volatile/volatile
READY.setVolatile(box, true);
boolean ready2 = (boolean) READY.getVolatile(box);
```

These are two **independent illustrative** pairs, not four statements to run sequentially in place of a real protocol. In Option B, other accesses must still be placed properly before publish and after consume; a strong mode **does not** automatically turn business operations into an atomic transaction.

**Do not describe volatile as “every thread sees it immediately”**: scheduling latency, blocking, or progress are not guaranteed merely because a variable is volatile. Volatile provides visibility/ordering rules you can rely on, not a deadline commitment.

### 4.1. Access mode overrides the field's modifier

A detail very easy to miss from the JDK 17 Javadoc: **the VarHandle access mode overrides the memory ordering implied by the variable declaration**. If a field is declared `volatile int marker` but you call `VH.get(instance)`, that access carries **plain semantics**; calling `VH.setRelease(instance, x)` carries release semantics; whereas direct reading/writing via the Java expression `instance.marker` still carries `volatile` field semantics.

Do not assume:

> “I declared the field as volatile, so every VarHandle call to it is also volatile.”

This is false. What needs to be reviewed is **every actual access path**, including source-level access, Reflection, VarHandle, and anywhere that might alias the same address.

## 5. Standalone Java 17+ example: same VarHandle, multiple modes and fences

Create the file **`VarHandleModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleModesDemo {
    static final class State {
        int payload;
        boolean ready;
        volatile int marker;
        int counter;
    }

    static final VarHandle READY;
    static final VarHandle MARKER;
    static final VarHandle COUNTER;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            READY = lookup.findVarHandle(State.class, "ready", boolean.class);
            MARKER = lookup.findVarHandle(State.class, "marker", int.class);
            COUNTER = lookup.findVarHandle(State.class, "counter", int.class);
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static void main(String[] args) {
        State state = new State();
        state.payload = 42;
        READY.setRelease(state, true);
        System.out.println("ready/acquire=" + (boolean) READY.getAcquire(state));
        System.out.println("payload=" + state.payload);

        READY.setOpaque(state, false);
        System.out.println("ready/opaque=" + (boolean) READY.getOpaque(state));

        MARKER.set(state, 7);       // Plain despite 'volatile' declaration.
        System.out.println("marker/plain=" + (int) MARKER.get(state));
        MARKER.setVolatile(state, 8);
        System.out.println("marker/volatile=" + (int) MARKER.getVolatile(state));

        int old = (int) COUNTER.getAndAdd(state, 3);
        System.out.println("counter/old=" + old);
        System.out.println("counter/now=" + (int) COUNTER.getVolatile(state));

        VarHandle.loadLoadFence();
        VarHandle.storeStoreFence();
        VarHandle.acquireFence();
        VarHandle.releaseFence();
        VarHandle.fullFence();
        System.out.println("fences=5");
    }
}
```

Compile and run:

```bash
javac --release 17 VarHandleModesDemo.java
java VarHandleModesDemo
```

Exact `stdout`:

```text
ready/acquire=true
payload=42
ready/opaque=false
marker/plain=7
marker/volatile=8
counter/old=0
counter/now=3
fences=5
```

**Note the limitation of the example:** all operations in `VarHandleModesDemo` execute on **a single thread**. Therefore it demonstrates how to look up a VarHandle, mode syntax, signature-polymorphic return casts, and that fence operations exist in the API; it is **not proof** of cross-thread visibility. Differences between memory modes only matter when there are interleavings and access paths from other threads.

Each VarHandle here points to an instance field, so each call receives the `state` receiver before the new value (if it is a write). Because the return type of `READY` is `boolean` and of `COUNTER` is `int`, the read expressions have `(boolean)` / `(int)` casts respectively. A mode whose call-site signature does not match the VarHandle type can cause a `WrongMethodTypeException`.

## 6. What is a memory fence, and what is it not?

A memory fence specifies **ordering constraints** between loads/stores before and after the fence in the current thread, according to the fence type. VarHandle provides the following **five static methods**:

| Fence | Ordering constraint per JDK 17 Javadoc | Avoid misinterpretation |
| --- | --- | --- |
| `VarHandle.loadLoadFence()` | Loads **before** are not reordered with loads **after** | Does not fully constrain stores or create publication |
| `VarHandle.storeStoreFence()` | Stores before are not reordered with stores after | Does not replace the reader's acquire |
| `VarHandle.acquireFence()` | Loads before are not reordered with loads **and stores** after | Does not necessarily constrain all stores before the fence |
| `VarHandle.releaseFence()` | Loads and stores before are not reordered with stores after | Does not automatically bind a specific reader/flag to the fence |
| `VarHandle.fullFence()` | Loads and stores before are not reordered with loads and stores after | Does not automatically create locks, CAS, or a global HB protocol |

These describe **observable reordering constraints**, not a promise that the JVM will always emit an exact hardware fence instruction in every case. The JIT may use a specific mechanism suited to the CPU architecture, or even omit an instruction if the guarantee is already satisfied by other means.

### 6.1. Two critically important facts

**First, a fence does not come with a synchronization variable.** For example:

```java
// Not a safe publish protocol just because a fence is present.
payload = 42;
VarHandle.fullFence();
ready = true;                 // plain write

// Another thread:
if (ready) {                 // plain read
    VarHandle.fullFence();
    use(payload);
}
```

The snippets above are *illustrative anti-patterns* only: there is no guarantee that a pair of plain flag accesses establishes safe publication/consumption. A fence constrains reordering in each thread, but **does not itself create** a synchronization event between two threads, does not guarantee the reader sees the new flag in time, and does not automatically attach a happens-before edge through the `ready` variable.

**Second, a fence is not an atomic read-modify-write operation.** `fullFence` before and after `counter++` does not turn `counter++` into `getAndAdd`. Lost updates can still happen if two threads both read the old number and both write the incremented number.

### 6.2. If you already have the right mode, do you need an extra fence?

In the standard publish/consume pattern, `setRelease` and `getAcquire` **already carry the necessary memory effects**. Inserting `fullFence` before/after both sides out of habit can make code harder to understand and add overhead without improving the protocol.

Conceptually correct example:

```java
// Writer: prepare data, publish once.
box.payload = 42;
READY.setRelease(box, true);

// Reader: only read payload after seeing ready.
if ((boolean) READY.getAcquire(box)) {
    consume(box.payload);
}
```

This is an illustrative snippet with `READY` and `consume` appropriately defined; to run standalone, use `VarHandlePublicationDemo` above. In a single-writer/single-publication protocol, there is no need to manually add `releaseFence` or `acquireFence` outside these operations.

When standalone fences are needed in complex lock-free algorithms, **you must prove** where they create what constraints, which variables are read/written in which modes, and which mechanism links the threads. Do not extrapolate mechanically from C/C++ instruction names or x86/ARM architectures: the VarHandle documentation explicitly states that the effects are compatible in some respects but **differ in semantics** from the memory models of those languages.

## 7. Risks of mixing multiple modes on the same variable

The `VarHandle` Javadoc warns directly: access modes **override** the memory-ordering effect of the declaration; when accessing the same variable with multiple modes, the JMM may allow unexpected results. The focus of review is not “the strongest mode that appeared somewhere”, but whether **the publishing write path and the consuming read path pair properly**.

### 7.1. Four combinations that can cause misunderstandings

| Writer of flag | Reader of flag | Can plain payload publication before writer's write be assumed? |
| --- | --- | --- |
| `setRelease` | `getAcquire`, reading the matching publication | **Yes**, provided the publish/consume protocol is sound and payload is not concurrently overwritten |
| `setVolatile` | `getVolatile`, reading the matching publication | **Yes**, per volatile semantics and the JMM |
| `setOpaque` | `getVolatile` | **Cannot be inferred**: writer lacks a release effect protecting payload |
| `setRelease` | `getOpaque` | **Cannot be inferred**: reader lacks an acquire effect for subsequent payload reads |
| `setVolatile` | `get` (plain) | **Cannot be inferred**: reader does not perform a volatile/acquire read |
| `set` (plain) | `getVolatile` | **Cannot be inferred**: writer does not perform a release/volatile write |
| `setOpaque` | `getOpaque` | Coherent on the same flag, **insufficient** to publish payload in other variables |

The table considers **a protocol relying solely on a VarHandle flag**, without considering other synchronization mechanisms that may already protect the data. If the entire critical section is properly protected by a lock, the evaluation must account for that lock/unlock as well.

Do not read the “No / Cannot be inferred” cells as “guaranteed to run wrong”; the exact meaning is **there is no specification basis to prove safety under this assumption**. A specific JDK, CPU, or schedule may produce the desired result billions of times without turning an anti-pattern into correct code.

### 7.2. Anti-pattern: opaque write, volatile read

```java
// Suppose Holder has int payload; volatile boolean ready;
// and READY is a VarHandle to Holder.ready.

// Writer thread
holder.payload = 42;
READY.setOpaque(holder, true);

// Reader thread
if ((boolean) READY.getVolatile(holder)) {
    int value = holder.payload; // Not guaranteed to be properly published.
}
```

This is a non-standalone illustrative snippet; **do not use it as a synchronization pattern**. Even though the reader uses `getVolatile`, the writer uses `setOpaque`, so there is no corresponding release write under the protocol. Similarly, changing the writer to `setRelease` while the reader reverts to `getOpaque` still lacks the acquire link.

Fix it with **an explicit pair**, for example:

```java
// Writer
holder.payload = 42;
READY.setRelease(holder, true);

// Reader (after observing ready)
if ((boolean) READY.getAcquire(holder)) {
    int value = holder.payload;
}
```

Using `setVolatile`/`getVolatile` is also a valid protocol when the remaining assumptions are met. **Do not “upgrade” one end while ignoring the other**.

### 7.3. Pitfall: field declared volatile but read plain via VarHandle

```java
final class Status {
    volatile int code;
}

// Suppose CODE is a VarHandle pointing to Status.code:
int a = status.code;           // Java source volatile read.
int b = (int) CODE.get(status); // VarHandle plain read.
int c = (int) CODE.getVolatile(status); // Volatile mode.
```

This is an illustrative snippet; `Status`, `status`, and `CODE` must be declared/looked up before running. Although `a`, `b`, and `c` read the same field, **`b` does not inherit volatile semantics** just because the field has the `volatile` modifier. If a library/framework uses a plain VarHandle on a field that the application reads/writes directly via `volatile`, the entire protocol must be reviewed. This is especially dangerous in serializers, agents, mappers, or instrumentation tools that use VarHandle in place of normal Java access paths.

### 7.4. Speculative reading with getOpaque does not become acquire because of a later fence

A temptation is to use `getOpaque(flag)`, and if true is seen, call `acquireFence()` and then read the payload. Do not assume this is equivalent to `getAcquire(flag)` or forms a standard synchronization pair under all JMM conditions. A full analysis of reads, writes, fences, and inter-thread relations is required; one must not take the C/C++ model and apply it directly to Java.

At the application level, the clearer and easier-to-prove approach is to call `getAcquire` directly at the consumption point, paired with `setRelease` at the publication point. Standalone fences are for low-level algorithms with dedicated proofs and tests.

## 8. Atomic updates, CAS, and the difference between atomicity and visibility

### 8.1. Lost updates despite volatile load/store

The following code is **not an atomic increment**:

```java
int old = (int) COUNTER.getVolatile(state);
COUNTER.setVolatile(state, old + 1);
```

If two threads both read `old==5`, both can write `6`; the result that should have been `7` has lost one increment. Each individual operation has volatile semantics, but **the sequence of two operations** is not atomic.

Replace with:

```java
int previous = (int) COUNTER.getAndAdd(state, 1);
```

`getAndAdd` reads the old value and updates atomically; with the default mode it has memory effects like a volatile read/write as described by the JDK. Another solution is a `compareAndSet` loop capable of retrying under contention. Do not replace CAS with an unsynchronized get/set combination.

### 8.2. Acquire/Release variants of RMW

`getAndSetAcquire`, `getAndSetRelease`, `compareAndExchangeAcquire`, `compareAndExchangeRelease`, `getAndAddAcquire`, and `getAndAddRelease` still perform the update **atomically**, but choose ordering effects for the read or write side that differ from the default volatile mode. For example, an `…Acquire` variant prioritizes the acquire effect on **the read side**, while the write side may be only like plain; `…Release` has a release effect on **the write side** while the read side may be only like plain.

Therefore:

- Do not see the word “atomic” and infer that both read and write paths of an RMW are volatile.
- For a CAS used to **publish** data, ensure the successful write branch has an appropriate release memory effect; an acquire-only variant does not substitute for release on the writer.
- For an RMW used to **consume** published data, ensure the read part has an acquire effect; a release-only variant does not automatically help the reader.
- Check the specification of **the specific method**, because the read and write sides can be asymmetric.
- `weakCompareAndSetPlain` can also **fail spuriously**, so you must retry or handle `false`; do not use it as a check for “definitely modified by another thread”.

### 8.3. Mixing atomic RMW and plain write on the same state

If one thread uses `COUNTER.getAndAdd(state,1)` while another thread uses `COUNTER.set(state,0)` without a protocol, the plain reset can interleave and break assumptions about the increments. The atomicity of `getAndAdd` **does not turn all operations of other threads into a single shared transaction**.

A contended counter design must specify **all update paths**: use CAS, atomic RMW, locks, or replace state with a consistent mechanism. Do not optimize a “fast path” with `set` because it looks like just a “simple reset”.

## 9. Relationship with other Java synchronization mechanisms

| Mechanism | Principle |
| --- | --- |
| `synchronized`/monitor | Lock/unlock establishes a `synchronizes-with` relation; protects multiple fields in a critical section |
| `volatile` field | Source-level access with volatile semantics; establishes corresponding HB rules on the same volatile variable |
| `VarHandle.getVolatile/setVolatile` | Expresses volatile access mode for the variable pointed to by the handle |
| `VarHandle.getAcquire/setRelease` | Directional ordering to publish/consume in matching pairs, often lighter than full volatile |
| `VarHandle.getOpaque/setOpaque` | Coherence/bitwise atomicity of a single variable without providing payload publication like acquire/release |
| `VarHandle.*Fence` | Constrains reordering between adjacent accesses within a thread; not a mutex, CAS, or notification |
| `java.util.concurrent.atomic.*` | Ready-made APIs for common atomic types; often easier to review than building custom protocols |
| `CountDownLatch`, `BlockingQueue`, `CompletableFuture` | High-level primitives providing clear communication/handoff mechanisms; many applications do not need manual fence management |

You should not “convert all” code using `synchronized` to VarHandle just hoping it will be faster. A critical section protecting complex invariants across multiple variables may require a lock. `VarHandle` is ideal when you need per-variable access control or are building lock-free algorithms with a clear **proof of invariants, ordering, and progress**.

### 9.1. Immutable/final does not solve every situation

`final` fields are given special initialization rules by the JMM, but an object containing mutable references or non-final fields still requires a proper publication and access protocol. For instance, publishing an object and then continuing to mutate an internal mutable `List` from the writer thread while a reader iterates unsynchronized can cause a race even if the reference to the list is stored in a final field.

When using message passing, prefer creating a completely immutable object and then publishing **the reference** via volatile/release-acquire; lifecycle management is still required and mutable state must not be modified after publish.

## 10. Checklist for designing a safe VarHandle protocol

Before shipping to a library or production, write down these invariants explicitly:

1. **Which shared variables?** List fields, array slots, and all aliases. Do not list only where VarHandles exist; include direct field access paths, Reflection, JNI, and other libraries.
2. **Who owns write permission?** Single writer or multi-writer? Can readers write back to state? Which fields remain mutable after publish?
3. **Mode on each edge?** For every read/write path of the same variable, write the exact name `get`, `setRelease`, `getAcquire`, `setVolatile`, `compareAndSet`… Do not replace everything with the word “atomic”.
4. **What data is published?** Payload writes happen before publication; readers only consume after seeing a valid publication.
5. **Where is the inter-thread relation?** Point out the explicit release/acquire pair or volatile/monitor/concurrent primitive. Standalone fences by themselves do not answer this question.
6. **Atomicity of combined operations?** If read-modify-write is needed, use atomic RMW/CAS or a mutex. A sequence of volatile accesses does not automatically form an atomic transaction.
7. **Recycling and ABA?** If flags are reset/reused, a sequence number or state machine is needed; a single flag turning true is not enough to distinguish data generations.
8. **Progress and CPU?** How long to spin, is there backoff/park/block, how are timeouts handled? `Thread.onSpinWait` does not create an HB condition.
9. **Mode support and types?** Final fields are read-only, VarHandle types have coordinate types, and certain modes/atomic updates may not be supported. Check `isAccessModeSupported`; verify exact types and casts at the call site.
10. **Tested on which platforms?** CI across multiple JDKs/OSes/CPUs, testing interleavings and load; use concurrency stress tools (e.g., JCStress). A test that “runs a million times without error” does not by itself prove JMM correctness.

### 10.1. Review with a diagram instead of only reading code sequentially

A review note can be written following this template:

```text
Protocol: one-shot single-writer publication
Shared state: data (plain), ready (boolean accessed via VarHandle)
Writer owner: exactly one
  W1: write data
  W2: READY.setRelease(true)
Reader:
  R1: READY.getAcquire() observes true from W2
  R2: read data
Ordering argument:
  W1 before W2; matching release/acquire links W2 to R1; R2 after R1
Other writes to data: none after W2
Potential hazards: reader races before R1? no; reset/reuse? no
```

If you cannot fill in **“other writes”**, **“matching read/write”**, or **“recycle policy”**, the algorithm is not yet clear enough to be considered safe.

## 11. Testing JMM: do not treat stdout as absolute proof

An example succeeding on one thread or in a single two-thread run does not prove all interleavings. Concurrency hazards sometimes appear only on another CPU or when the JIT optimizes under different conditions.

- **Do not use `Thread.sleep` for synchronization**. Sleeping for an interval does not create an HB edge between plain writes/reads.
- **Avoid “tests that pass by accident”**: adding `join`, a latch, or logging with locks in the right place can introduce extra synchronization, masking the original race. Analyze the HB graph of both **the code under test** and the test logic.
- **Do not rely on x86 generally being stronger than ARM** to omit acquire/release on paths that need guarantees. Code must be correct according to the Java specification, not just on one architecture.
- **Use structured stress tests**, such as JCStress, explicitly documenting which outcome states are allowed/forbidden by the specification. Stress tests are supporting empirical evidence, not a substitute for reasoning.
- **For non-deterministic results**, describe the set of valid outcomes rather than publishing a fixed `stdout` for a data race. This article intentionally avoids giving a “guaranteed to read 0” example for a race, because doing so would fabricate unguaranteed behavior.
- **Progress conditions** must be considered separately: a spin loop can be poorly scheduled or time out even when ordering logic is correct, so bound the time and have a handling policy.

## 12. Common mistakes and how to fix them

| Symptom / misconception | Real issue | How to fix |
| --- | --- | --- |
| “`volatile` field so `vh.get` is a volatile read” | Access mode overrides modifier ordering | Use `getVolatile` or proper acquire protocol, audit all access paths |
| Writer `setOpaque`, reader `getVolatile` | Missing release effect on writer side | Use a consistent release/acquire or volatile/volatile pair |
| Writer `setRelease`, reader `getOpaque` | Reader lacks acquire for payload | Change reader to `getAcquire` |
| Calling `fullFence` after plain write is enough to publish | Fence does not build an inter-thread sync edge by itself | Establish a communication protocol with release/acquire, volatile, lock, or concurrent primitive |
| Writer has CAS so plain reader always sees payload | Writer atomicity does not replace reader synchronization | Review the read side and appropriate mode of state/flag |
| `getVolatile` then `setVolatile` is an atomic increment | Two operations can be interleaved | Use `getAndAdd` or a CAS loop |
| `getOpaque` will surely see updates immediately | No deadline/liveness guarantee | Design notification, blocking/backoff/timeout |
| `releaseFence` then `set` is equivalent in all cases to `setRelease` | Fences and modes should not be substituted mechanically in the JMM | Use the mode directly; if using a fence, provide a protocol proof |
| Only `final` fields so object is always deeply immutable | Referenced objects can be mutable | Defensive copy, do not mutate after publication, synchronize when needed |
| Using plain on `long`/`double` is atomic on all platforms | Plain does not guarantee bitwise atomicity on some 32-bit platforms | Use opaque/acquire/volatile or appropriate atomic |
| Test passes means no race | A few schedules do not cover the JMM | HB reasoning, stress tests, and invariant review |
| `WrongMethodTypeException` from `vh.get...` | Wrong coordinate type passed or wrong return type cast | Check `varType()`, `coordinateTypes()`, `accessModeType(...)` |

## 13. Self-check exercises

**Exercise A.** Two threads both increment `count` using `getVolatile` then `setVolatile`. Is every increment guaranteed to be counted?

**Answer:** No. Two separate operations are not atomic when combined; use `getAndAdd` or a CAS loop.

**Exercise B.** A field is `volatile boolean done`, but the writer calls `DONE.setOpaque(obj,true)` and the reader calls `DONE.getVolatile(obj)` and then reads plain payload. Can one rely on the declaration to guarantee the payload is published?

**Answer:** No. The VarHandle writer uses opaque mode, lacking the corresponding release effect. The protocol must be made consistent.

**Exercise C.** Does `VarHandle.fullFence()` in both threads automatically create synchronizes-with for a plain flag?

**Answer:** No. Fences place individual reordering constraints and do not automatically create inter-thread communication. Use volatile or release/acquire on an appropriate shared variable.

**Exercise D.** Write the modes for a producer preparing an object that is immutable after publish, and a consumer reading the flag and then reading the payload.

**Answer:** The producer writes the payload then `FLAG.setRelease(holder,true)`; the consumer waits for `(boolean)FLAG.getAcquire(holder)` to be `true` from the matching publication before reading the payload. Proper ownership/reuse conditions must be in place.

**Exercise E.** What do `getOpaque` and `setOpaque` allow concluding about payload in **other variables**?

**Answer:** One cannot conclude that payload has been properly published like a release/acquire pair. Opaque provides bitwise atomicity and coherence for **that variable** but does not create inter-thread ordering for other payload.

**Exercise F.** Which direction does `VarHandle.releaseFence()` constrain? Is it the same as `acquireFence()`?

**Answer:** A release fence prevents **preceding loads/stores** from reordering with **subsequent stores**; an acquire fence prevents **preceding loads** from reordering with **subsequent loads/stores**. They are not the same.

**Exercise G.** Why can `weakCompareAndSetPlain` return `false` when the value matches? Can one rely on `false` to conclude another writer intervened?

**Answer:** Because weak CAS can fail spuriously; `false` is not sufficient to prove contention or that the value changed. Retry or appropriate `false`-handling logic is required.

**Exercise H.** A single-use setRelease/getAcquire protocol is correct, but the writer continues modifying `payload` after setRelease without synchronization. Is the reader safe?

**Answer:** Safety cannot be inferred. Publication protects writes **before release**; new writes by the writer after publication can race with the reader. Ownership/handshake/locking must be added or mutation after publish must be avoided.

## Authoritative references

- [JDK 17 — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes table, plain/opaque/acquire/release/volatile guarantees, mixed-mode warning, CAS, and the five fence methods.
- [JDK 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `findVarHandle`, `findStaticVarHandle`, and handle creation factories.
- [JLS 17 — `17.4 Memory Model`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): program order, synchronization order, synchronizes-with, happens-before, valid read/write behaviors.
- [JDK 17 — `java.util.concurrent.atomic`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html): common atomic classes and synchronization semantics that can be used instead of custom algorithms.
- [JDK 17 — `Thread.onSpinWait`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait()): performance hint for spin loops, not a synchronization primitive.

**Key takeaway:** use modes according to **the exact data transfer path**. `setRelease` combined with `getAcquire` has publish/consume meaning; `setVolatile`/`getVolatile` carry stronger volatile semantics; opaque is only coherent for the variable being accessed; fences limit reordering rather than building happens-before on their own; atomic RMW protects a single update but does not fix a broken visibility protocol. **Mixing modes without a specific ordering argument is a correctness risk, not merely a performance risk.**