# VarHandle in Java: Plain, Volatile, Acquire–Release, and Atomic Access Modes

`VarHandle` (since Java 9) enables operations on **a specific variable** such as an object field, static field, or array element, while specifying **memory read/write rules**. These rules are called *access modes*: `get`/`set` (plain), `getVolatile`/`setVolatile`, `getAcquire`/`setRelease`, and atomic update operations such as `compareAndSet` and `getAndAdd`.

It is important to distinguish immediately:

- **Memory ordering/visibility**: in what order is one thread permitted to observe another thread's operations? Are writes to other fields safely published?
- **Atomicity**: does an update occur as an indivisible step that cannot be interleaved? For instance, can two threads incrementing the same counter lose an increment?
- **Access modes** specify one or both of these properties, depending on the operation. `volatile` does not automatically turn `x++` into an atomic operation; `getAndAdd` is an atomic *read-modify-write* operation.

This lesson focuses on how to choose a mode and why that choice is sound under the Java Memory Model (JMM), rather than treating `VarHandle` as an unconditional replacement for `synchronized`, `Lock`, or `AtomicInteger`.

## 1. Which Variable Does VarHandle Point To?

A `VarHandle` is a *dynamically strongly typed* reference to a storage location. It does not store the variable's value. When invoking an access mode, the program supplies **coordinates** to identify the variable to operate on.

Illustrative example:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

class Holder {
    int count;
}

class Example {
    static void demo() throws ReflectiveOperationException {
        VarHandle countHandle = MethodHandles.lookup()
                .findVarHandle(Holder.class, "count", int.class);
        Holder holder = new Holder();

        countHandle.set(holder, 10);              // Coordinate: holder
        int n = (int) countHandle.get(holder);      // n = 10
    }
}
```

- `findVarHandle` looks up an **instance field**, so the call needs the `holder` object as a coordinate; `findStaticVarHandle` applies to static fields and takes no instance.
- `MethodHandles.arrayElementVarHandle(int[].class)` creates a handle for array elements, with coordinates `(array, index)`.
- `VarHandle` does not bypass access permissions. `MethodHandles.lookup()` and other lookup mechanisms must hold appropriate permissions when creating the handle.
- `get`/`set`, `getAcquire`/`setRelease`, and atomic operations have actual signatures matching the variable type and coordinates, even though API docs display `Object...`. Wrong types/coordinates can cause `WrongMethodTypeException` or cast errors.
- A handle pointing to a `final` field does not support write or atomic update modes; invoking an unsupported mode throws `UnsupportedOperationException`.

## 2. Comparing Access Mode Groups

| Group | Read | Write/Update | Key Guarantees | When Appropriate |
| --- | --- | --- | --- | --- |
| **Plain** | `get` | `set` | Adds no cross-thread ordering constraints like `volatile` | Data used in a single thread or already synchronized by another mechanism |
| **Opaque** (intermediate level) | `getOpaque` | `setOpaque` | Atomic for the variable's value and coherent in access order on that same variable; does **not** publish other fields via release/acquire | Very specialized cases needing only single-variable observation |
| **Acquire–Release** | `getAcquire` | `setRelease` | One-way ordering for accesses before/after a value is properly handed off | Publishing/consuming data via a state flag |
| **Volatile** | `getVolatile` | `setVolatile` | Read/write effects like a `volatile` field; volatile operations have a corresponding total order in the memory model | Shared flags, state requiring volatile semantics |
| **Atomic update** | Reads and modifies in one operation | `compareAndSet`, `compareAndExchange`, `getAndSet`, `getAndAdd`… | Update cannot be interleaved; each API has its own memory ordering | Counters, state machines, contended updates |

Do not read the table as a single axis where "atomic is stronger than volatile". **Atomicity and ordering are two orthogonal dimensions**: `compareAndSet` has volatile effects, whereas `compareAndExchangeAcquire` or `getAndAddRelease` intentionally uses weaker ordering on one side.

### 2.1. Plain: `get` and `set`

`get(receiver)`/`set(receiver, value)` have the semantics of reading/writing an ordinary non-`volatile` field.

```java
// Suppose COUNT is a VarHandle to the int field count on counter.
COUNT.set(counter, 10);
int x = (int) COUNT.get(counter);
```

If `counter` is only used by one thread, or all accesses across threads sit inside a proper synchronization protocol, plain is usually sufficient. If two threads exchange data without synchronization using plain reads/writes, the JMM **does not guarantee** the reading thread sees the new update or observes other fields in the expected order.

Regarding atomicity of a single operation: object references and primitives up to 32 bits have intact read/write guarantees; plain `long`/`double` has exceptions on some 32-bit platforms. Even when a single `get` is atomic, pairing `get` followed by `set` **does not** become an atomic read-modify-write.

**Important caveat:** the mode governs access semantics **even when the field is declared `volatile`**. Calling `get` through a VarHandle on a volatile field is not equivalent to `getVolatile`. Mixing different modes on the same variable without a clear design easily causes hard-to-reproduce memory bugs.

### 2.2. Opaque Is Only a Reference Point

`getOpaque`/`setOpaque` provide stronger guarantees than plain for the accessed variable alone, but do not establish a publish/consume protocol for related data. Do not replace `setRelease` with `setOpaque` when you need to publish a payload in another field. This lesson mentions opaque only to place acquire/release and volatile in proper context.

## 3. Volatile: Observing State and Cross-Thread Ordering

`setVolatile` and `getVolatile` have memory effects corresponding to writing/reading a `volatile` field:

```java
// FLAG is a VarHandle for the boolean field ready.
FLAG.setVolatile(message, true);
boolean ready = (boolean) FLAG.getVolatile(message);
```

Like a volatile write/read pair on the same variable, a volatile write preceding a matching volatile read in *synchronization order* creates a synchronization edge so prior writes are properly observed via happens-before. This is very useful for `shutdown` or `ready` flags, or a state value replaced wholesale.

However:

- `volatile` **does not** make `value++` or `getVolatile` followed by `setVolatile` an atomic operation. Two threads can both read 4 and both write 5, losing an increment.
- Volatile does not guarantee that another thread always sees the new value within a specific bounded time, nor does it solve check-then-act race logic.
- Marking **every** field volatile does not create a consistent multi-field transaction; maintaining invariants across multiple variables may still require locks or proper state encapsulation.

Broken increment example under contention:

```java
int current = (int) COUNT.getVolatile(counter);
COUNT.setVolatile(counter, current + 1); // Two separate operations; updates can be lost.
```

The proper replacement, if the handle supports `int`, is `COUNT.getAndAdd(counter, 1)`.

## 4. Acquire–Release: Publishing and Consuming Data

`setRelease` has **release** semantics: prior reads/writes in the same thread are not reordered after it under the guaranteed memory constraints. `getAcquire` has **acquire** semantics: subsequent reads/writes are not reordered before it. When an acquiring thread observes the value published via release **on the same synchronization variable**, payload writes before the release can be safely consumed after the acquire according to that communication protocol.

Diagram of a one-time published message:

```text
Producer                         Consumer
---------                        ---------------------------
message.payload = 42             while (!READY.getAcquire(message))
READY.setRelease(message, true)       wait for flag true
                                 int x = message.payload
                                 // x = 42 by protocol
```

Why are both sides needed?

1. Producer writes `payload` first and then releases the `ready` flag.
2. Consumer checks the flag with acquire. Once it reads the value published by the release, it gains the memory ordering required to read `payload`.
3. `payload` can be an ordinary (**plain**) field if it is written before the release and not concurrently modified outside the protocol. This is a case of *safe publication*, not a license to read arbitrary unsynchronized fields.

Some limitations:

- `getAcquire` **does not** force reading "the latest version" of an arbitrary variable; it only establishes the corresponding ordering effects. Reading the flag may still see `false` and have to retry.
- `setRelease` does not automatically make data visible to every thread without a matching read side, nor does it force the reader thread to be scheduled in bounded time.
- When a flag is reused across multiple message lifecycles, an additional protocol is required to avoid overwriting `payload` while the consumer is reading. The simple example here publishes **only once**.
- A release read or acquire write is not the pair to use here: in this pattern, **release write** pairs with **acquire read**.
- The spin loop is solely to demonstrate memory ordering; production code typically uses `BlockingQueue`, `CountDownLatch`, `Lock`/`Condition`, or built-in synchronizers to avoid burning CPU and to simplify cancellation/waiting.

### How Does Acquire–Release Differ from Volatile?

A release/acquire pair primarily constrains ordering around **one-way handoff of information** (publish → consume); volatile adds stronger guarantees, including a total order among volatile accesses. Therefore, if a producer simply needs to publish a payload and a consumer needs to receive it, acquire/release can be an appropriate choice. Do not assume they are equivalent to volatile in algorithms with multiple variables and interleaved operation types.

## 5. Atomic Access Modes: Read–Modify–Write in One Step

`VarHandle` provides atomic update methods. Common ones include:

| Method | Return Value | Meaning |
| --- | --- | --- |
| `compareAndSet(receiver, expected, update)` | `boolean` | Writes only if current value equals `expected` per the variable's equality; has volatile effects |
| `compareAndExchange(receiver, expected, update)` | Observed value (*witness*) | Returns the actual value at CAS time; writes when witness equals expected |
| `getAndSet(receiver, update)` | Old value | Atomically replaces value and returns the old one |
| `getAndAdd(receiver, delta)` | Old value | Atomically adds for supported numeric types such as `int`/`long` |
| `getAndBitwiseOr` / `getAndBitwiseAnd` / `getAndBitwiseXor` | Old value | Atomic bitwise updates for supported types |
| `weakCompareAndSetPlain` and `weakCompareAndSet...` variants | `boolean` | Weak CAS, **can fail spuriously** even when the comparison matches; requires appropriate checking/retry |

**Reading CAS results properly:**

```java
boolean updated = COUNT.compareAndSet(counter, 4, 5); // true if currently 4
int observed = (int) COUNT.compareAndExchange(counter, 5, 6);
// observed = 5 if CAS succeeded; if currently another value, does not write and returns that value
```

For reference-typed variables, CAS's expected comparison uses **reference identity (`==`)**, not `equals()`. For example, two distinct objects whose `equals` returns true will still not match in CAS.

### Why Does CAS Often Need a Loop?

When multiple threads update state that depends on the previous value, one thread may read the old value and have another thread change it before the CAS. A failed `compareAndSet` is the signal to retry with the new state:

```java
static void addTen(VarHandle handle, Counter counter) {
    for (;;) {
        int before = (int) handle.getVolatile(counter);
        int after = before + 10;
        if (handle.compareAndSet(counter, before, after)) {
            return;
        }
    }
}
```

This is an **illustrative snippet**, assuming a `Counter` class with an `int value` field and a `VarHandle` pointing to that field. For simple addition, `getAndAdd(counter, 10)` is shorter and usually preferable. For complex computations, consider side effects, contention, and re-evaluating the expression after a CAS failure.

**ABA:** CAS only checks whether the current value equals expected. If a variable changes A → B → A in between, a CAS comparing against A can still succeed despite the intermediate changes. Algorithms that must detect this need to store an extra version/stamp or apply another suitable mechanism.

### Memory Ordering of Atomic Operations

- `compareAndSet`, `compareAndExchange`, `getAndSet`, and `getAndAdd` (the unsuffixed forms) have volatile read/write effects per their specifications.
- `...Acquire` variants generally apply acquire ordering only on the read side; `...Release` variants generally apply release ordering only on the write side. Do not assume every variant carries full volatile effects.
- `weakCompareAndSetPlain` uses plain semantics and may fail spuriously; other variants have the effects indicated by their names.
- Atomicity does not mean an algorithm is contention-free, automatically guarantees fairness, or always finishes in a fixed number of steps.

If you are unsure whether a weaker mode suffices for your algorithm's invariants and happens-before edges, prefer standard atomic APIs or operations with volatile semantics that are easier to reason about, then optimize based on evidence.

## 6. Java 17+ Program: Comparing Modes and Running Multi-Threaded

Create **`VarHandleModesDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandleModesDemo {
    static class Cell {
        int value;
    }

    static class Message {
        int payload;
        boolean ready;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException, InterruptedException {
        VarHandle value = MethodHandles.lookup()
                .findVarHandle(Cell.class, "value", int.class);
        VarHandle ready = MethodHandles.lookup()
                .findVarHandle(Message.class, "ready", boolean.class);

        Cell cell = new Cell();

        // 1. Plain: single-threaded operation, no sharing yet.
        value.set(cell, 3);
        System.out.println("plain=" + (int) value.get(cell));

        // 2. Volatile: individual read/write with volatile effects.
        value.setVolatile(cell, 4);
        System.out.println("volatile=" + (int) value.getVolatile(cell));

        // 3. Atomic compare-and-set and read-modify-write.
        boolean updated = value.compareAndSet(cell, 4, 5);
        System.out.println("CAS=" + updated
                + ", value=" + (int) value.getVolatile(cell));

        int old = (int) value.getAndAdd(cell, 2);
        System.out.println("getAndAdd old=" + old
                + ", value=" + (int) value.getVolatile(cell));

        int witness = (int) value.compareAndExchange(cell, 7, 9);
        System.out.println("exchange witness=" + witness
                + ", value=" + (int) value.getVolatile(cell));

        // 4. Multiple threads incrementing the same variable via atomic operation.
        value.setVolatile(cell, 0);
        Thread[] workers = new Thread[4];
        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 10_000; j++) {
                    value.getAndAdd(cell, 1);
                }
            });
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("atomic counter="
                + (int) value.getVolatile(cell));

        // 5. Producer/consumer: publish a payload with release/acquire.
        Message message = new Message();
        Thread reader = new Thread(() -> {
            while (!(boolean) ready.getAcquire(message)) {
                Thread.onSpinWait(); // Spin used solely for demonstration.
            }
            System.out.println("published payload=" + message.payload);
        });
        reader.start();

        message.payload = 42;
        ready.setRelease(message, true);
        reader.join();
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac VarHandleModesDemo.java
java VarHandleModesDemo
```

Output:

```text
plain=3
volatile=4
CAS=true, value=5
getAndAdd old=5, value=7
exchange witness=7, value=9
atomic counter=40000
published payload=42
```

**Why is the output correct?**

1. Plain and volatile at the start run sequentially in `main`, so each read sees the value just written. Do not use those plain operations to infer cross-thread sharing rules.
2. CAS sees `4` and changes it to `5`. `getAndAdd` adds `2`, returning old value `5`; `compareAndExchange` sees `7` and changes it to `9`.
3. Four workers each increment `10_000` times using `getAndAdd` on the same field. No updates are lost, so the total is `40_000` after `join`ing all four threads.
4. Producer writes `message.payload = 42` before `ready.setRelease(message, true)`. Reader reads `payload` only after `getAcquire` sees the `true` flag. This is a one-time publish/consume protocol; the flag defaults to `false`.
5. `Thread.join()` makes the main thread wait for the workers and reader to finish, ensuring no output is missed. The reader's wait loop is not intended as a production pattern.

The code uses `Thread.onSpinWait()` from Java 9 and `VarHandle` from Java 9 without external libraries.

## 7. Choosing a Mode for the Problem

| Scenario | Suggestion | Reason |
| --- | --- | --- |
| Thread-local data | `get`/`set` (or direct field access) | No extra synchronization needed |
| Stop flag or simple shared state | `getVolatile`/`setVolatile`, or a `volatile` field | Volatile effects are easy to reason about |
| Producer publishes a payload once | `setRelease` + `getAcquire` on the flag | Establishes the needed ordering when the consumer sees the flag published |
| Multiple threads adding to a shared counter | `getAndAdd` or `AtomicInteger` | Each addition is atomic; no lost updates |
| Update if state has not changed | `compareAndSet`, or `compareAndExchange` if the witness is needed | Checks and writes in one atomic operation |
| Must synchronize invariants across multiple fields or a critical section | `synchronized`/`Lock` or immutable state design | Single-field atomicity cannot protect the whole group |

`VarHandle` is valuable in low-level library code and building synchronization primitives. Typical applications should prefer `AtomicInteger`, `AtomicReference`, `BlockingQueue`, `Lock`, `synchronized`, or `java.util.concurrent` constructs when they meet the need directly. They are easier to review and reduce the risk of misusing memory semantics.

## 8. Common Mistakes and How to Check

**Mistake 1 — Assuming `volatile` makes `++` atomic.** A single volatile access only guarantees semantics for that individual read or write. For safe increments under contention, use `getAndAdd` or a proper CAS update.

**Mistake 2 — Using plain access to signal between threads.** If the consumer only calls `get` to check a flag without another synchronization mechanism, the program lacks the desired visibility/ordering guarantees. Use acquire/release or volatile according to the protocol.

**Mistake 3 — Writing payload after release.** If the producer calls `setRelease(ready, true)` first and assigns `payload` afterward, the consumer may observe the flag without the new payload value. Always set the data to publish **before** releasing.

**Mistake 4 — Acquiring from variable A while releasing variable B.** The intended synchronization relationship does not arise automatically. A protocol must connect the exact same variable and publish/consume events.

**Mistake 5 — Mixing modes on the same variable on intuition.** `get` via `VarHandle` does not inherit `volatile` from the field declaration. Pick a consistent protocol and check the specification when combining modes.

**Mistake 6 — Assuming a successful CAS means the state never changed.** The ABA phenomenon shows that state can change in between and return to the expected value.

**Mistake 7 — Calling an unsupported mode.** A handle for a `final` field forbids writes; not every arithmetic/bitwise operation is valid for every type. Check `isAccessModeSupported(VarHandle.AccessMode.XXX)` when handling abstract handles.

**Mistake 8 — Wrong return type on signature-polymorphic calls.** For an `int` field, write `(int) handle.get(obj)`; for a `boolean` field, write `(boolean) handle.getAcquire(obj)`. Mismatched types/coordinates can fail at runtime.

### Self-Check

1. Why can two threads using `getVolatile` + `setVolatile` to increment a counter still lose updates?
2. When the consumer observes `ready == true` via `getAcquire`, which writes by the producer are published through `setRelease`?
3. How do `compareAndSet` and `compareAndExchange` differ in their return values?
4. If an algorithm must protect `balance` and `version` together, is updating one field atomically enough?
5. Why can a plain `payload` field be used in the producer/consumer example, yet `payload` must not be arbitrarily overwritten after publication?
6. When low-level tuning is unnecessary, why is `AtomicInteger` usually easier to use than managing a `VarHandle` manually?

### Reference Documentation

- [Java SE 17 — `VarHandle` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): list of access modes, atomicity, and memory ordering.
- [Java SE 17 — `MethodHandles` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): creating handles and lookup permission requirements.
- [Java Language Specification `17.4 — Memory Model](https://docs.oracle.com/en/java/javase/17/docs/specs/jls/se17/html/jls-17.html#jls-17.4): `happens-before`, `synchronization order`, and related memory rules.