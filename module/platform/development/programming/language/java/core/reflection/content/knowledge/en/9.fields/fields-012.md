# `volatile` fields: reading/writing and atomic updates in Java Reflection

## 1. The problem: `volatile` does not mean atomic `++`

For a Java field declared `volatile`, the Java Memory Model guarantees **volatile read/write semantics**: visibility of changes across threads, certain ordering constraints, and atomicity of **a single read or a single write**. However, `volatile` does not turn **a sequence of multiple operations** into an atomic transaction.

That remains true when reading/writing a field with Reflection:

~~~java
Field field = Counter.class.getDeclaredField("value");
int before = field.getInt(counter);
field.setInt(counter, before + 1);
~~~

This is merely an illustrative snippet and must be placed inside a method with appropriate access permissions and checked exception handling/declarations. If `Counter.value` is `volatile int`, `getInt` is one volatile read and `setInt` is one volatile write. **Two separate calls do not form an atomic increment.**

Two threads can both read `0` and then both write `1`, causing one increment to be lost (*lost update*).

> **Distinction:** An *atomic read/write* of a field differs from an *atomic read–modify–write* (RMW) such as `incrementAndGet`, `getAndAdd`, or `compareAndSet`.

## 2. Reading metadata and values of a volatile Field

Given the following class:

~~~java
class Counter {
    public volatile int value;
}
~~~

We can inspect modifiers and operate on an instance:

~~~java
Field field = Counter.class.getDeclaredField("value");
boolean declaredVolatile = Modifier.isVolatile(field.getModifiers());

int value = field.getInt(counter);
field.setInt(counter, 5);
~~~

These examples are Java excerpts, not standalone programs; they require importing `java.lang.reflect.Field` and `java.lang.reflect.Modifier`, having a `counter` variable, and handling appropriate exceptions.

- `getDeclaredField("value")` finds the field declared on the class, including private ones; `getField` only finds eligible public fields. Retrieving metadata **is not equivalent** to having read/write permission.
- `Modifier.isVolatile(field.getModifiers())` checks whether the field is declared `volatile`. `volatile` is a modifier of the field, not a "toggle mode" on an individual `Field` object.
- `getInt(counter)` and `setInt(counter, number)` read/write the `int` field. General `get`/`set` accessors also access the underlying field; they do not strip away its inherent volatile semantics.
- For **instance** fields, the receiver must be compatible with the declaring class; **static** fields can be accessed with a `null` receiver (`Field.get/set` ignores the receiver value for static fields).
- Private fields may require `trySetAccessible()` or `setAccessible(true)`; deep reflection rights are further subject to module restrictions. **Opening access permissions does not turn read–modify–write into an atomic operation.**
- `Field` provides single read/write operations, not `Field.incrementAndGet()` or `Field.compareAndSet()`.

If a field is volatile yet you execute `field.getInt(...)`, compute, and then `field.setInt(...)`, nothing prevents another thread from interleaving between the two calls.

## 3. What does `volatile` actually guarantee?

### 3.1. Visibility and happens-before

A volatile read/write is a *synchronization action*. Under the Java Memory Model, a write to a volatile variable *synchronizes-with* subsequent reads of the same volatile variable in synchronization order, establishing a *happens-before* relationship. That enables passing state via a flag:

~~~java
class Message {
    int data;
    volatile boolean ready;
}

// Sender thread:
message.data = 42;
message.ready = true;

// Receiver thread:
if (message.ready) {
    System.out.println(message.data);
}
~~~

The snippet above describes two threads, not a standalone Java program. When the receiver observes `ready == true` from the sender's write, prior writes such as `data = 42` are published to subsequent reads in the receiver thread. This is a simple *publication* protocol; if there are other competing writes, the invariants and ordering of the whole program must be reviewed.

Do not interpret this as "every field inside the object is volatile". If `volatile List<String> items`, reading/writing **the `items` reference** has volatile semantics; however, `items.add(x)` still depends on the thread safety of the collection itself. `ArrayList` does not become thread-safe simply because the reference variable is declared volatile.

### 3.2. Atomicity for a single read or a single write

A single read/write of **the volatile variable itself** has atomicity corresponding to its type. `volatile long` and `volatile double` are guaranteed not to tear into two inconsistent halves. This differs from a guarantee for a **read → compute → write** sequence.

With `volatile int count`, a statement `count = 7` is a volatile write; `int x = count` is a volatile read; yet `count++` still consists of reading the old value, computing the new value, and writing back.

### 3.3. Not a lock

`volatile` does not provide *mutual exclusion*. It does not automatically protect multi-variable invariants, such as "`available + reserved == total`". If two fields must be updated as a single transaction, consider `synchronized`/`Lock` or an immutable state object swapped atomically.

## 4. Timeline of a lost increment

Initially `value = 0`. Two threads A and B both execute:

~~~java
int oldValue = field.getInt(counter);       // volatile read
field.setInt(counter, oldValue + 1);        // volatile write
~~~

One valid interleaving:

| Step | Thread A | Thread B | Shared value |
| --- | --- | --- | --- |
| 1 | Reads `0` | — | 0 |
| 2 | — | Reads `0` | 0 |
| 3 | Writes `1` | — | 1 |
| 4 | — | Writes `1` | 1 |

The final result is **1**, despite two increment requests; each individual volatile read/write obeys JMM rules. Whether the code is `x++`, `x += 1`, `getInt`/`setInt`, or `getVolatile`/`setVolatile`, without CAS, an atomic RMW operation, or a lock, *lost updates* can still happen.

## 5. Java 17+ program reproducing the bug deterministically

Save as **`VolatileReflectionDemo.java`**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public class VolatileReflectionDemo {
    public static class Counter {
        public volatile int value;
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter();
        Field field = Counter.class.getDeclaredField("value");

        System.out.println("volatile: "
                + Modifier.isVolatile(field.getModifiers()));

        // Force both threads to read 0 before either writes.
        CyclicBarrier bothRead = new CyclicBarrier(2);
        Runnable unsafe = () -> {
            try {
                int snapshot = field.getInt(counter);
                bothRead.await();
                field.setInt(counter, snapshot + 1);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        };

        Thread a = new Thread(unsafe, "unsafe-A");
        Thread b = new Thread(unsafe, "unsafe-B");
        a.start();
        b.start();
        a.join();
        b.join();
        System.out.println("Field get+set: " + field.getInt(counter));

        // Same field, but using an atomic increment.
        counter.value = 0;
        AtomicIntegerFieldUpdater<Counter> updater =
                AtomicIntegerFieldUpdater.newUpdater(
                        Counter.class, "value");

        Runnable safe = () -> {
            for (int i = 0; i < 1000; i++) {
                updater.incrementAndGet(counter);
            }
        };

        Thread c = new Thread(safe, "safe-C");
        Thread d = new Thread(safe, "safe-D");
        c.start();
        d.start();
        c.join();
        d.join();
        System.out.println("AtomicIntegerFieldUpdater: "
                + field.getInt(counter));

        // An atomic RMW operation via VarHandle.
        VarHandle handle = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class);

        int oldValue = (int) handle.getAndAdd(counter, 1);
        int newValue = (int) handle.getVolatile(counter);
        System.out.println("VarHandle old=" + oldValue
                + ", new=" + newValue);
    }
}
~~~

Compile and run:

~~~bash
javac VolatileReflectionDemo.java
java VolatileReflectionDemo
~~~

Exact output:

~~~text
volatile: true
Field get+set: 1
AtomicIntegerFieldUpdater: 2000
VarHandle old=2000, new=2001
~~~

**Part 1 — lost update:** `CyclicBarrier` forces both threads to complete `field.getInt(counter)` before either calls `setInt`. Both store `snapshot = 0`; both subsequent writes store 1. The result is **always 1 in this experiment**; we do not rely on random thread scheduling to observe the race.

**Part 2 — atomic update:** Two threads each increment 1000 times using `AtomicIntegerFieldUpdater.incrementAndGet`. Each increment is an atomic read–modify–write on the same field, totaling exactly **2000**.

**Part 3 — VarHandle:** `getAndAdd(counter, 1)` returns the pre-update value (2000) and adds 1 as an atomic operation; `getVolatile(counter)` reads 2001. Both APIs enforce proper field type rules and access permissions.

Do not use `Thread.sleep` to "try your luck"; the barrier clearly demonstrates the bug. The program uses a public field to isolate concurrency bugs from Java access control errors.

## 6. Three options to fix the bug

### 6.1. `AtomicIntegerFieldUpdater`

When you want to keep a `volatile int` instance field in an existing class, use:

~~~java
AtomicIntegerFieldUpdater<Counter> updater =
        AtomicIntegerFieldUpdater.newUpdater(Counter.class, "value");

int incremented = updater.incrementAndGet(counter);
int previous = updater.getAndIncrement(counter);
boolean swapped = updater.compareAndSet(counter, previous + 1, 50);
~~~

This illustrative snippet uses the `Counter` class from the full example and needs an appropriate Java context. `compareAndSet` only returns `true` if the current value exactly equals `expected`; the example does not assert that CAS must succeed under contention.

Conditions: the field must be an **instance** `volatile int` (not static), with permitted access rights. `AtomicLongFieldUpdater` and `AtomicReferenceFieldUpdater` exist for the corresponding types. The factory can throw an error if the field has the wrong type, is not volatile, or is inaccessible.

An updater only helps update paths that use the proper atomic operations. If the rest of the application still reads and writes back via `setInt` without coordination, data can still lose updates.

### 6.2. `VarHandle`: avoid confusing access modes with atomic operations

You can obtain a `VarHandle` for the field if `Lookup` has permission:

~~~java
VarHandle vh = MethodHandles.lookup().findVarHandle(
        Counter.class, "value", int.class);

// Two SEPARATE operations: not an atomic increment.
int before = (int) vh.getVolatile(counter);
vh.setVolatile(counter, before + 1);

// One atomic RMW operation:
int previous = (int) vh.getAndAdd(counter, 1);
boolean success = vh.compareAndSet(counter, previous + 1, 10);
~~~

This is an illustrative snippet, not a standalone runnable program. `compareAndSet` only succeeds if the current value matches `expected`.

`VarHandle` also offers access modes such as `get`/`set` (plain), `getOpaque`/`setOpaque`, `getAcquire`/`setRelease`, and `getVolatile`/`setVolatile`, alongside atomic RMW modes. Different modes have different memory ordering: **do not assume every access through a VarHandle automatically has volatile semantics**. If volatile field reads/writes and cross-thread coordination are needed, choose an access mode with the matching memory ordering contract.

`VarHandle.getAndAdd` or `compareAndSet` is the right tool for a single variable; it does not mean an entire multi-field operation is protected.

### 6.3. `AtomicInteger` or locks

If the object model can be changed, an `AtomicInteger` field expresses the intent more clearly:

~~~java
private final java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

void increase() {
    count.incrementAndGet();
}
~~~

This is an illustrative snippet inside a class. When multiple variables must be updated consistently, a `synchronized` block or `Lock` can be more convenient than CAS on individual variables.

## 7. Reflection: access permissions and thread safety are two separate axes

Commonly confused scenarios:

| Scenario | What actually happens |
| --- | --- |
| `Modifier.isVolatile(field.getModifiers()) == true` | The field is declared volatile; does not prove read–compute–write operations are atomic. |
| `field.trySetAccessible() == true` | Permitted to bypass Java access checks on that `Field`; does not create a lock. |
| `field.getInt(target)` then `field.setInt(target, x)` | Two separate operations; another thread can interleave between them. |
| `getVolatile` then `setVolatile` on a VarHandle | Each operation has volatile semantics, yet the pair is still not an atomic RMW. |
| `getAndAdd` or `compareAndSet` | Atomic update on the target variable per API contract. |
| `volatile List<?> items` | Publishes/reads the reference with volatile semantics; does not guarantee collection mutations are thread-safe. |
| `volatile int x; volatile int y;` | Does not automatically preserve a joint invariant between `x` and `y`. |

Do not confuse Reflection access errors (`IllegalAccessException`, `IllegalArgumentException` on invalid receiver) with race conditions. Fixing access permissions with `setAccessible` does not cure a *lost update*.

**Type limitations:** a field cannot be both `final` and `volatile`; Java forbids combining those two modifiers. `AtomicIntegerFieldUpdater` requires an instance field and does not apply directly to `static volatile int`. For static fields, you can use `static final AtomicInteger`, locks, or an appropriate static `VarHandle`.

## 8. Checklist for choosing a solution

1. Only need one thread to signal a status flag to other threads? `volatile` can suffice when a proper visibility/ordering protocol is designed.
2. Need to read/write **a single standalone value** with cross-thread visibility? A volatile field and compatible accessor are a simple choice.
3. Need `count++`, `count += delta`, or "if still equal to X, change to Y"? Choose `AtomicInteger`, `AtomicIntegerFieldUpdater`, `VarHandle.getAndAdd`/`compareAndSet`, or a lock.
4. Need to update multiple fields together under an invariant? Consider a lock or an immutable state object replaced atomically.
5. Field name only known at runtime? Inspect `getType()`, `getModifiers()`, instance/static, and access permissions, then select the right tool; `Field.get/set` has no CAS.
6. Writing concurrency tests? Aim to create controllable interleavings like `CyclicBarrier`, rather than relying on a stress run that happens not to fail.

### Self-check

- Two threads execute `volatileCount++` when initially 0. Is the result guaranteed to be 2? **No**, it may be 1 due to lost updates.
- Do `Field.getInt`/`setInt` on `volatile int` bypass volatile visibility? **No**, yet the two calls remain independent.
- Can `VarHandle.getVolatile` followed by `setVolatile` replace `getAndAdd`? **No**, because it is not an atomic RMW.
- Does `AtomicIntegerFieldUpdater` work on `static volatile int`? **No**, only on qualifying instance fields.
- Does `volatile List` make `ArrayList.add` thread-safe? **No**, thread safety of the collection or separate synchronization is required.

**Conclusion:** `volatile` guarantees semantics for **each individual field read/write** and cross-thread visibility/ordering relationships. Reflection respects that property. To update without losing values, you must use **atomic read–modify–write** or appropriate **synchronization**.

### Standard references

- [Java Language Specification 17 — §17.4 Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4)
- [JDK 17 — `java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [JDK 17 — `AtomicIntegerFieldUpdater`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerFieldUpdater.html)
- [JDK 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [JDK 17 — `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)